"""Across-bundle v5 stopping rule and frozen four-way model competition."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Sequence

from smartcopy.cross_asset_intake import _bound_json, _jsonl, _line, _sha256
from smartcopy.preopen_model_competition import _CANDIDATES, _wilson_lower

_SCHEMA = "smartcopy-bonereaper-cross-asset-study-v1"
_CONTRACT = "a696cf068dcb5b4555073d1d5636eec7efa05050"
_MODEL = "smartcopy-bonereaper-cross-asset-model-v1"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def summarize_v5_study(rows: Sequence[dict[str, Any]], *, as_of: datetime) -> dict[str, Any]:
    if as_of.tzinfo is None:
        raise ValueError("as_of must have timezone")
    current = as_of.astimezone(timezone.utc)
    if current > datetime.now(timezone.utc) + timedelta(minutes=1):
        raise ValueError("as_of cannot be a future reporting time")
    eligible = sorted((row for row in rows if row["eligible"] and row["cohort"] == "CORE"),
                      key=lambda row: (row["market_start"], row["condition_id"]))
    if any(datetime.fromtimestamp(row["market_start"], timezone.utc) > current for row in eligible):
        raise ValueError("as_of predates a scored market")
    first = datetime.fromtimestamp(eligible[0]["market_start"], timezone.utc) if eligible else None
    # Seven *complete* UTC calendar days follow the day containing the first
    # eligible condition; deadline is midnight after those seven days.
    deadline = (first.replace(hour=0, minute=0, second=0, microsecond=0)
                + timedelta(days=8)) if first else None
    before_deadline = [row for row in eligible if deadline is None or
                       datetime.fromtimestamp(row["market_start"], timezone.utc) < deadline]
    selected = before_deadline[:60]
    if len(selected) >= 60:
        status = "STOPPING_RULE_REACHED"
    elif deadline and current >= deadline:
        status = "UNDERPOWERED"
    else:
        status = "COLLECTING"
    stopped = status != "COLLECTING"

    def scores(values: Sequence[dict[str, Any]], *, asset_verdict: bool = True) -> dict[str, Any]:
        answer = {}
        for candidate in _CANDIDATES:
            observed = [row for row in values if row.get(candidate) in {"Up", "Down"}]
            wins = sum(row[candidate] == row["label"] for row in observed)
            total = len(observed)
            share = wins / total if total else None
            lower = _wilson_lower(wins, total) if total else None
            if not stopped or (not asset_verdict and len(values) < 10):
                verdict = "DEFERRED_UNTIL_STOPPING_RULE" if not stopped else "INSUFFICIENT_ASSET_CONDITIONS"
            elif total == 0:
                verdict = "INCONCLUSIVE"
            elif share >= .65 and lower > .50:
                verdict = "SUPPORTED_DESCRIPTIVELY"
            elif share <= .55:
                verdict = "NOT_SUPPORTED"
            else:
                verdict = "INCONCLUSIVE"
            answer[candidate] = {"eligible_conditions": total, "aligned_conditions": wins,
                                 "alignment_share": share, "wilson_95_lower": lower, "verdict": verdict}
        return answer

    pairwise = {}
    for i, left in enumerate(_CANDIDATES):
        for right in _CANDIDATES[i + 1:]:
            discordant = [row for row in selected if row.get(left) in {"Up", "Down"}
                          and row.get(right) in {"Up", "Down"} and row[left] != row[right]]
            left_wins = sum(row["label"] == row[left] for row in discordant)
            n = len(discordant)
            winner = None
            if not stopped:
                verdict = "DEFERRED_UNTIL_STOPPING_RULE"
            elif n < 10:
                verdict = "UNDERPOWERED_COMPARISON"
            elif left_wins / n >= .65 and (2 * left_wins - n) / n >= .20:
                verdict, winner = "DOMINANT_CANDIDATE", left
            elif (n - left_wins) / n >= .65 and (n - 2 * left_wins) / n >= .20:
                verdict, winner = "DOMINANT_CANDIDATE", right
            else:
                verdict = "NO_DOMINANT_CANDIDATE"
            pairwise[f"{left}__vs__{right}"] = {"discordant_conditions": n,
                "left_wins": left_wins, "right_wins": n - left_wins, "winner": winner, "verdict": verdict}
    assets = ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE")
    return {"schema_version": _SCHEMA, "contract_commit": _CONTRACT, "study_status": status,
            "eligible_conditions": len(selected), "target_conditions": 60,
            "first_eligible_utc": first.isoformat() if first else None,
            "seven_complete_days_deadline_utc": deadline.isoformat() if deadline else None,
            "as_of_utc": current.isoformat(), "candidates": scores(selected),
            "pairwise_disagreements": pairwise,
            "per_asset": {asset: {"conditions": sum(r["asset"] == asset for r in selected),
                                   "candidates": scores([r for r in selected if r["asset"] == asset],
                                                        asset_verdict=False)} for asset in assets},
            "leave_one_asset_out": {asset: {"conditions": sum(r["asset"] != asset for r in selected),
                                             "candidates": scores([r for r in selected if r["asset"] != asset])}
                                    for asset in assets},
            "duplicate_or_late_conditions_excluded": len(eligible) - len(selected)}


def run_v5_study(*, model_dirs: Sequence[str | Path], expected_manifest_sha256: Sequence[str],
                 output_dir: str | Path, as_of: datetime, code_commit: str) -> dict[str, Any]:
    if not _COMMIT.fullmatch(code_commit) or not model_dirs or len(model_dirs) != len(expected_manifest_sha256):
        raise ValueError("supply a commit and equal nonempty model directory/hash lists")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(output)
    seen: dict[str, dict[str, Any]] = {}
    bindings = []
    capture_hashes = set()
    for directory, digest in zip(model_dirs, expected_manifest_sha256):
        root = Path(directory)
        manifest = _bound_json(root / "cross_asset_model_manifest.json", digest)
        if manifest.get("schema_version") != _MODEL or manifest.get("contract_commit") != _CONTRACT:
            raise ValueError("not a frozen v5 model manifest")
        capture = manifest["capture_manifest_sha256"]
        if capture in capture_hashes:
            raise ValueError("duplicate capture bundle")
        capture_hashes.add(capture)
        path = root / "cross_asset_model_rows.jsonl"
        artifact = manifest["artifacts"][path.name]
        if path.stat().st_size != artifact["bytes"] or _sha256(path) != artifact["sha256"]:
            raise ValueError("model rows artifact changed")
        values = tuple(_jsonl(path))
        if len(values) != manifest["row_count"] or sum(bool(row["eligible"]) for row in values) != manifest["eligible_core_conditions"]:
            raise ValueError("model row counts changed")
        for row in values:
            condition = row["condition_id"]
            if condition in seen and seen[condition] != row:
                raise ValueError("conflicting condition across bundles")
            seen[condition] = row
        bindings.append({"manifest_sha256": digest, "capture_manifest_sha256": capture})
    result = summarize_v5_study(tuple(seen.values()), as_of=as_of)
    output.mkdir(parents=True)
    path = output / "cross_asset_study_summary.json"
    path.write_bytes(_line(result))
    manifest = {"schema_version": _SCHEMA, "contract_commit": _CONTRACT,
                "code_commit": code_commit, "inputs": bindings,
                "unique_condition_count": len(seen),
                "artifacts": {path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}}}
    (output / "cross_asset_study_manifest.json").write_bytes(_line(manifest))
    return result


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", action="append", required=True)
    parser.add_argument("--expected-manifest-sha256", action="append", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--as-of-utc", required=True, help="ISO UTC time at which study status is assessed")
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args(argv)
    instant = datetime.fromisoformat(args.as_of_utc.replace("Z", "+00:00"))
    print(json.dumps(run_v5_study(model_dirs=args.model_dir,
        expected_manifest_sha256=args.expected_manifest_sha256, output_dir=args.output_dir,
        as_of=instant, code_commit=args.code_commit), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
