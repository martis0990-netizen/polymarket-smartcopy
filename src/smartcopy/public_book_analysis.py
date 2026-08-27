"""SHA-bound confirmatory analysis for prospective public-book bundle v3 captures."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from smartcopy.prospective_signal import wilson_lower_bound
from smartcopy.public_book import classify_captured_level

_SCHEMA = "smartcopy-bonereaper-public-book-analysis-v1"
_BUNDLE_SCHEMA = "smartcopy-bonereaper-prospective-bundle-v3"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_ROWS = "public_book_ladder_rows.jsonl"
_SUMMARY = "public_book_ladder_summary.json"
_MANIFEST = "public_book_analysis_manifest.json"


class PublicBookAnalysisError(RuntimeError):
    """Raised when a bundle cannot satisfy the frozen confirmatory analysis."""


def analyze_bound_fills(
    decoded_rows: Iterable[dict[str, Any]],
    *,
    book_records: Sequence[dict[str, Any]],
    gaps: Sequence[dict[str, Any]],
    token_metadata: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tokens = {str(row["token_id"]): row for row in token_metadata}
    output: list[dict[str, Any]] = []
    excluded_unbound = 0
    for source in decoded_rows:
        token_id = str(source.get("asset_id"))
        metadata = tokens.get(token_id)
        if metadata is None:
            excluded_unbound += 1
            continue
        role = str(source.get("schema_corrected_role"))
        if role == "MAKER":
            ladder = classify_captured_level(
                book_records,
                token_id=token_id,
                side="BUY",
                fill_price=str(source.get("source_price")),
                source_timestamp_ms=int(source.get("source_second")) * 1_000,
                gaps=gaps,
            )
        elif role == "TAKER":
            ladder = "NOT_APPLICABLE"
        else:
            ladder = "AMBIGUOUS_ROLE"
        output.append(
            {
                **source,
                "bound_asset": metadata["asset"],
                "bound_window_seconds": metadata["window_seconds"],
                "bound_slug": metadata.get("slug"),
                "ladder_classification": ladder,
            }
        )
    summary = _summarize(output, excluded_unbound=excluded_unbound)
    return output, summary


def _summarize(rows: Sequence[dict[str, Any]], *, excluded_unbound: int) -> dict[str, Any]:
    counts: Counter[tuple[str, str]] = Counter()
    notionals: defaultdict[tuple[str, str], float] = defaultdict(float)
    for row in rows:
        key = (str(row["schema_corrected_role"]), str(row["ladder_classification"]))
        counts[key] += 1
        notionals[key] += float(row["source_notional"])

    conditions: dict[str, Any] = {}
    strata = Counter()
    for condition_id in sorted({str(row["condition_id"]) for row in rows}):
        condition_rows = [row for row in rows if str(row["condition_id"]) == condition_id]
        eligible = [
            row
            for row in condition_rows
            if row["schema_corrected_role"] == "MAKER"
            and row["ladder_classification"]
            in {"PRE_POSITIONED_LEVEL", "LATE_OR_UNSEEN_LEVEL"}
        ]
        if not eligible:
            continue
        total = sum(float(row["source_notional"]) for row in eligible)
        pre = sum(
            float(row["source_notional"])
            for row in eligible
            if row["ladder_classification"] == "PRE_POSITIONED_LEVEL"
        )
        share = pre / total if total else None
        classification = (
            "PRE_POSITIONED_DOMINANT"
            if share is not None and share >= 0.80
            else "LATE_DOMINANT"
            if share is not None and share <= 0.20
            else "MIXED_CONDITION"
        )
        asset = str(eligible[0]["bound_asset"])
        window = int(eligible[0]["bound_window_seconds"])
        stratum = f"{asset}_{window}"
        strata[stratum] += 1
        conditions[condition_id] = {
            "slug": eligible[0].get("bound_slug"),
            "asset": asset,
            "window_seconds": window,
            "eligible_maker_fills": len(eligible),
            "eligible_maker_notional": total,
            "pre_positioned_notional": pre,
            "pre_positioned_notional_share": share,
            "classification": classification,
        }

    total_conditions = len(conditions)
    pre_dominant = sum(
        item["classification"] == "PRE_POSITIONED_DOMINANT" for item in conditions.values()
    )
    late_dominant = sum(item["classification"] == "LATE_DOMINANT" for item in conditions.values())
    required_strata = ("BTC_300", "BTC_900", "ETH_300", "ETH_900")
    stopping_met = total_conditions >= 30 and all(strata[name] >= 5 for name in required_strata)
    if not stopping_met:
        verdict = "COLLECTING"
    else:
        pre_share = pre_dominant / total_conditions
        late_share = late_dominant / total_conditions
        if pre_share >= 0.65 and wilson_lower_bound(pre_dominant, total_conditions) > 0.50:
            verdict = "LONG_STANDING_LADDER_SUPPORTED"
        elif late_share >= 0.65 and wilson_lower_bound(late_dominant, total_conditions) > 0.50:
            verdict = "RAPID_QUOTING_SUPPORTED"
        else:
            verdict = "MIXED_OR_INCONCLUSIVE"

    return {
        "schema_version": _SCHEMA,
        "bound_fill_rows": len(rows),
        "excluded_unbound_rows": excluded_unbound,
        "role_ladder_breakdown": [
            {
                "role": role,
                "ladder_classification": ladder,
                "fills": counts[(role, ladder)],
                "notional": notionals[(role, ladder)],
            }
            for role, ladder in sorted(counts)
        ],
        "conditions": conditions,
        "confirmatory_progress": {
            "eligible_conditions": total_conditions,
            "target_conditions": 30,
            "strata": {name: strata[name] for name in required_strata},
            "required_per_stratum": 5,
            "pre_positioned_dominant": pre_dominant,
            "late_dominant": late_dominant,
            "mixed": total_conditions - pre_dominant - late_dominant,
            "stopping_rule_met": stopping_met,
            "verdict": verdict,
        },
    }


def run_analysis(
    *,
    bundle_dir: str | Path,
    decoded_rows_path: str | Path,
    expected_decoded_sha256: str,
    output_dir: str | Path,
    code_commit: str,
) -> dict[str, Any]:
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing analysis directory: {output}")
    bundle = Path(bundle_dir)
    root_manifest_path = bundle / "prospective_bundle_manifest.json"
    root_manifest = _load_json(root_manifest_path)
    if root_manifest.get("schema_version") != _BUNDLE_SCHEMA or root_manifest.get("clean_finalize") is not True:
        raise PublicBookAnalysisError("analysis requires a clean prospective bundle v3")
    book_info = root_manifest.get("public_book")
    if not isinstance(book_info, dict):
        raise PublicBookAnalysisError("bundle is missing public-book binding")
    book_manifest_path = bundle / str(book_info["manifest"])
    _require_sha(book_manifest_path, str(book_info["sha256"]), "public-book manifest")
    token_path = bundle / str(book_info["token_metadata"])
    _require_sha(token_path, str(book_info["token_metadata_sha256"]), "token metadata")
    book_manifest = _load_json(book_manifest_path)
    book_root = book_manifest_path.parent
    levels_path = book_root / "book_levels.jsonl"
    gaps_path = book_root / "book_gaps.jsonl"
    for path in (levels_path, gaps_path):
        artifact = book_manifest.get("artifacts", {}).get(path.name)
        if not isinstance(artifact, dict):
            raise PublicBookAnalysisError(f"public-book manifest is missing {path.name}")
        _require_sha(path, str(artifact["sha256"]), path.name)

    decoded_path = Path(decoded_rows_path)
    decoded_sha = _require_sha(decoded_path, expected_decoded_sha256, "decoded receipt rows")
    token_payload = _load_json(token_path)
    token_metadata = token_payload.get("tokens")
    if not isinstance(token_metadata, list):
        raise PublicBookAnalysisError("token metadata must contain a tokens list")
    rows, summary = analyze_bound_fills(
        _load_jsonl(decoded_path),
        book_records=_load_jsonl(levels_path),
        gaps=_load_jsonl(gaps_path),
        token_metadata=token_metadata,
    )

    output.mkdir(parents=True)
    rows_path = output / _ROWS
    summary_path = output / _SUMMARY
    manifest_path = output / _MANIFEST
    _write_jsonl(rows_path, rows)
    _write_json(summary_path, summary)
    manifest = {
        "schema_version": _SCHEMA,
        "code_commit": code_commit,
        "bundle_manifest": {"path": str(root_manifest_path), "sha256": _sha256(root_manifest_path)},
        "decoded_rows": {"path": str(decoded_path), "sha256": decoded_sha},
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in (rows_path, summary_path)
        },
    }
    _write_json(manifest_path, manifest)
    return {"manifest": manifest, "summary": summary, "output_dir": str(output)}


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PublicBookAnalysisError(f"{path} must contain a JSON object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise PublicBookAnalysisError(f"{path} contains a non-object row")
    return rows


def _require_sha(path: Path, expected: str, label: str) -> str:
    actual = _sha256(path)
    if actual != expected.lower():
        raise PublicBookAnalysisError(f"{label} SHA256 mismatch: expected {expected.lower()}, got {actual}")
    return actual


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--decoded-rows", required=True)
    parser.add_argument("--expected-decoded-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--code-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_analysis(
        bundle_dir=args.bundle_dir,
        decoded_rows_path=args.decoded_rows,
        expected_decoded_sha256=args.expected_decoded_sha256,
        output_dir=args.output_dir,
        code_commit=args.code_commit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
