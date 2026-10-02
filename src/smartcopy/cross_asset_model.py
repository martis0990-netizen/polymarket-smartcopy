"""Strict-prior, provenance-bound v5 model rows; no per-bundle verdicts."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from smartcopy.cross_asset_intake import _bound_json, _jsonl, _line, _millis, _sha256
from smartcopy.correction_overlay import market_spec
from smartcopy.external_signal import BinanceSpotAPI
from smartcopy.preopen_model_analysis import collect_v4_binance
from smartcopy.preopen_model_competition import evaluate_preopen_candidates
from smartcopy.preopen_signal import collapse_preopen_taker
from smartcopy.prospective_analysis import group_receipt_episodes

_SCHEMA = "smartcopy-bonereaper-cross-asset-model-v1"
_CONTRACT = "a696cf068dcb5b4555073d1d5636eec7efa05050"
_AMENDMENT = "0dd7a371b13f278383f1d81eba44bf88fbb6c3cc"
_CORE = frozenset(("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"))
_ASSETS = tuple(sorted(_CORE | {"HYPE"}))
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def load_v5_chainlink(path: Path) -> dict[str, tuple[dict[str, Any], ...]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for frame in _jsonl(path):
        if frame.get("kind") != "live":
            continue
        row = frame["normalized"]
        symbol = row["symbol"]
        if symbol not in {asset.lower() + "/usd" for asset in _ASSETS}:
            raise ValueError("unrecognized v5 Chainlink symbol")
        value = Decimal(str(row["full_accuracy_value"]))
        if not value.is_finite() or value <= 0:
            raise ValueError("nonpositive Chainlink price")
        by_symbol[symbol].append({
            "source_timestamp_ms": int(row["source_timestamp_ms"]),
            "receive_timestamp_ms": _millis(row["receive_timestamp"]),
            "value_decimal": value,
        })
    return {key: tuple(value) for key, value in by_symbol.items()}


def build_v5_model_rows(*, candidates: Sequence[dict[str, Any]],
                        episodes: dict[str, tuple[dict[str, Any], ...]],
                        chainlink: dict[str, tuple[dict[str, Any], ...]],
                        binance: dict[tuple[str, str], tuple[Any, ...]],
                        capture_started_ms: int, capture_ended_ms: int,
                        first_live_receive_ms: dict[str, int],
                        wallet_baseline_finished_ms: int) -> tuple[dict[str, Any], ...]:
    output = []
    for entry in sorted(candidates, key=lambda row: (row["market_start"], row["condition_id"])):
        condition = entry["condition_id"]
        spec = market_spec(condition_id=condition, slug=entry["slug"], title=entry["slug"],
                           allowed_assets=tuple(asset.lower() for asset in _ASSETS))
        if (spec.asset != entry["asset"] or spec.horizon != entry["horizon"]
                or spec.window_start != entry["market_start"]):
            raise ValueError("candidate condition metadata mismatch")
        if entry["cohort"] != ("CORE" if spec.asset in _CORE else "HYPE_ENGINEERING"):
            raise ValueError("candidate cohort mismatch")
        symbol = spec.asset.lower() + "/usd"
        warm = (capture_started_ms <= spec.window_start * 1000 - 660_000
                and first_live_receive_ms.get(symbol, 10**20) <= spec.window_start * 1000 - 660_000
                and wallet_baseline_finished_ms <= spec.window_start * 1000 - 660_000
                and capture_ended_ms >= spec.window_start * 1000)
        if warm != entry["capture_warmup_satisfied"]:
            raise ValueError("intake warm-up decision changed")
        label = collapse_preopen_taker(episodes.get(condition, ()), market_start=spec.window_start)
        reasons = []
        if spec.asset not in _CORE:
            reasons.append("HYPE_ENGINEERING_ONLY")
        if not warm:
            reasons.append("INSUFFICIENT_CAPTURE_WARMUP")
        if label is None:
            reasons.append("NO_UNAMBIGUOUS_PREOPEN_TAKER")
        result: dict[str, Any] = {}
        if label and spec.asset in _CORE and warm:
            t = int(label["source_second"])
            one = binance.get((spec.asset + "USDT", "1s"), ())
            htf = binance.get((spec.asset + "USDT", spec.horizon), ())
            # Strictly require uninterrupted native bars, including the 600s oracle basis.
            seconds = {bar.open_time_ms // 1000 for bar in one if bar.close_time_ms < t * 1000}
            duration = 300 if spec.horizon == "5m" else 900
            closed = {bar.open_time_ms // 1000 for bar in htf if bar.close_time_ms < t * 1000}
            latest = (t // duration) * duration - duration
            if not all(s in seconds for s in range(t - 601, t)) or not all(
                    latest - i * duration in closed for i in range(100)):
                reasons.append("INCOMPLETE_NATIVE_BINANCE_HISTORY")
            oracle = [row for row in chainlink.get(symbol, ())
                      if row["source_timestamp_ms"] < t * 1000
                      and row["receive_timestamp_ms"] < t * 1000]
            if not oracle or oracle[0]["source_timestamp_ms"] > (t - 600) * 1000:
                reasons.append("INCOMPLETE_STRICT_PRIOR_CHAINLINK")
            if not reasons:
                result = evaluate_preopen_candidates(
                    label=label["outcome"], source_second=t, market_end=spec.window_end,
                    one_second_bars=one, htf_bars=htf, chainlink_rows=oracle)
        output.append({"condition_id": condition, "slug": spec.slug, "asset": spec.asset,
                       "horizon": spec.horizon, "market_start": spec.window_start,
                       "cohort": entry["cohort"], "eligible": not reasons,
                       "exclusion_reasons": reasons, "primary_preopen_taker": label, **result})
    return tuple(output)


def run_v5_model(*, bundle_dir: str | Path, intake_dir: str | Path,
                 expected_intake_sha256: str, receipts_dir: str | Path,
                 expected_receipts_sha256: str, output_dir: str | Path,
                 code_commit: str, api: BinanceSpotAPI | None = None) -> dict[str, Any]:
    if not _COMMIT.fullmatch(code_commit):
        raise ValueError("code_commit must be a full lowercase Git SHA")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(output)
    intake_root = Path(intake_dir)
    intake = _bound_json(intake_root / "cross_asset_intake_manifest.json", expected_intake_sha256)
    receipts_root = Path(receipts_dir)
    receipts = _bound_json(receipts_root / "cross_asset_receipts_manifest.json", expected_receipts_sha256)
    bundle = Path(bundle_dir)
    capture = _bound_json(bundle / "cross_asset_capture_manifest.json", intake["capture_manifest_sha256"])
    if (intake.get("schema_version") != "smartcopy-bonereaper-cross-asset-intake-v1"
            or receipts.get("schema_version") != "smartcopy-bonereaper-cross-asset-receipts-v1"
            or capture.get("clean_finalize") is not True
            or capture.get("contract_commit") != _CONTRACT
            or capture.get("transport_amendment_commit") != _AMENDMENT
            or receipts.get("intake_manifest_sha256") != expected_intake_sha256
            or receipts.get("capture_manifest_sha256") != intake["capture_manifest_sha256"]
            or receipts.get("wallet_activity_sha256") != intake["wallet_activity_sha256"]):
        raise ValueError("v5 provenance chain mismatch")
    for directory, manifest, name in ((intake_root, intake, "preopen_buy_candidates.jsonl"),
                                      (receipts_root, receipts, "maker_taker_rows.jsonl"),
                                      (receipts_root, receipts, "maker_taker_summary.json")):
        binding = manifest["artifacts"][name]
        path = directory / name
        if path.stat().st_size != binding["bytes"] or _sha256(path) != binding["sha256"]:
            raise ValueError(f"artifact mismatch: {name}")
    oracle_path = bundle / "chainlink" / "chainlink_twap_raw.jsonl"
    oracle_manifest = _bound_json(bundle / "chainlink" / "chainlink_twap_manifest.json", capture["chainlink"]["sha256"])
    if _sha256(oracle_path) != oracle_manifest["artifacts"][oracle_path.name]["sha256"]:
        raise ValueError("Chainlink raw changed since intake")
    candidates = tuple(_jsonl(intake_root / "preopen_buy_candidates.jsonl"))
    receipt_rows = tuple(_jsonl(receipts_root / "maker_taker_rows.jsonl"))
    candidate_ids = {row["condition_id"] for row in candidates}
    if len(candidate_ids) != len(candidates):
        raise ValueError("duplicate intake condition")
    # Receipt collection covers every BUY, including markets outside the
    # decision window. Only intake's prospective conditions enter this study.
    episodes = group_receipt_episodes([row for row in receipt_rows if row["condition_id"] in candidate_ids])
    labels = []
    for entry in candidates:
        label = collapse_preopen_taker(episodes.get(entry["condition_id"], ()), market_start=entry["market_start"])
        if label and entry["cohort"] == "CORE" and entry["capture_warmup_satisfied"]:
            labels.append({"asset": entry["asset"], "horizon": entry["horizon"],
                           "source_second": label["source_second"]})
    envelopes, binance = collect_v4_binance(api or BinanceSpotAPI(), labels)
    rows = build_v5_model_rows(
        candidates=candidates, episodes=episodes, chainlink=load_v5_chainlink(oracle_path),
        binance=binance, capture_started_ms=_millis(capture["started_at"]),
        capture_ended_ms=_millis(capture["ended_at"]),
        first_live_receive_ms=intake["first_live_receive_ms"],
        wallet_baseline_finished_ms=intake["wallet_baseline_finished_ms"])
    output.mkdir(parents=True)
    artifacts = {"binance_v5_raw.jsonl": envelopes, "cross_asset_model_rows.jsonl": rows}
    for name, values in artifacts.items():
        (output / name).write_bytes(b"".join(_line(row) for row in values))
    manifest = {"schema_version": _SCHEMA, "contract_commit": _CONTRACT,
                "transport_amendment_commit": _AMENDMENT, "code_commit": code_commit,
                "collection_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "capture_manifest_sha256": intake["capture_manifest_sha256"],
                "intake_manifest_sha256": expected_intake_sha256,
                "receipts_manifest_sha256": expected_receipts_sha256,
                "row_count": len(rows), "eligible_core_conditions": sum(row["eligible"] for row in rows),
                "artifacts": {name: {"bytes": (output / name).stat().st_size,
                                      "sha256": _sha256(output / name)} for name in artifacts}}
    (output / "cross_asset_model_manifest.json").write_bytes(_line(manifest))
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ("bundle-dir", "intake-dir", "expected-intake-sha256", "receipts-dir",
                "expected-receipts-sha256", "output-dir", "code-commit"):
        parser.add_argument("--" + key, required=True)
    args = parser.parse_args(argv)
    print(json.dumps(run_v5_model(**vars(args)), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
