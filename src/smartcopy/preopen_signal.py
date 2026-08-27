"""Evaluate frozen Bonereaper v3 pre-open signals without using the future opening K."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from smartcopy.correction_overlay import MarketSpec, market_spec
from smartcopy.external_signal import BinanceKline, BinanceSpotAPI
from smartcopy.prospective_analysis import (
    _iso_ms,
    _latest_strict_pre,
    _load_json_sha,
    _load_jsonl_sha,
    _momentum_15s,
    _sha256,
    _write_json,
    _write_jsonl,
    collect_binance_1s,
    group_receipt_episodes,
    load_chainlink_events,
)

_SCHEMA = "smartcopy-bonereaper-preopen-signal-v3"
_CONTRACT_COMMIT = "82988de50befd9d970ceb36929512b8caf78fadf"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def collapse_preopen_taker(
    episodes: Sequence[dict[str, Any]],
    *,
    market_start: int,
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in episodes
        if row["role"] == "TAKER" and market_start - 60 <= int(row["source_second"]) < market_start
    ]
    if not candidates:
        return None
    first_second = min(int(row["source_second"]) for row in candidates)
    first = [row for row in candidates if int(row["source_second"]) == first_second]
    outcomes = {str(row["outcome"]) for row in first}
    if len(outcomes) != 1:
        return None
    return {
        "source_second": first_second,
        "lead_seconds": market_start - first_second,
        "outcome": outcomes.pop(),
        "episode_count": len(first),
        "source_notional": sum(float(row["source_notional"]) for row in first),
    }


def chainlink_momentum_15s(
    rows: Sequence[dict[str, Any]],
    *,
    source_second: int,
) -> float | None:
    current = _latest_strict_pre(rows, source_second * 1_000)
    previous = _latest_strict_pre(rows, (source_second - 15) * 1_000)
    if current is None or previous is None:
        return None
    return math.log(float(current["value_decimal"] / previous["value_decimal"]))


def build_preopen_rows(
    *,
    specs: dict[str, MarketSpec],
    episodes: dict[str, tuple[dict[str, Any], ...]],
    chainlink: dict[str, tuple[dict[str, Any], ...]],
    binance: dict[str, tuple[BinanceKline, ...]],
    capture_started_ms: int,
    capture_ended_ms: int,
) -> tuple[dict[str, Any], ...]:
    output: list[dict[str, Any]] = []
    for condition_id, spec in sorted(specs.items(), key=lambda item: item[1].window_start):
        start_ms = spec.window_start * 1_000
        reasons: list[str] = []
        if capture_started_ms > start_ms - 76_000:
            reasons.append("INCOMPLETE_PRE_OPEN_CAPTURE")
        if capture_ended_ms < start_ms:
            reasons.append("CAPTURE_ENDED_BEFORE_MARKET_START")
        label = collapse_preopen_taker(
            episodes.get(condition_id, ()),
            market_start=spec.window_start,
        )
        if label is None:
            reasons.append("NO_UNAMBIGUOUS_PRE_OPEN_TAKER")

        asset_symbol = "btc/usd" if spec.asset == "BTC" else "eth/usd"
        binance_momentum = None
        chainlink_momentum = None
        btc_lead = None
        if label is not None:
            second = int(label["source_second"])
            binance_momentum = _momentum_15s(binance[f"{spec.asset}USDT"], second)
            chainlink_momentum = chainlink_momentum_15s(chainlink[asset_symbol], source_second=second)
            if spec.asset == "ETH":
                btc_lead = _momentum_15s(binance["BTCUSDT"], second)
            if binance_momentum is None:
                reasons.append("STRICT_PRE_BINANCE_15S_MISSING")
            if chainlink_momentum is None:
                reasons.append("STRICT_PRE_CHAINLINK_15S_MISSING")

        binance_direction = _direction(binance_momentum)
        chainlink_direction = _direction(chainlink_momentum)
        btc_lead_direction = _direction(btc_lead)
        output.append(
            {
                "condition_id": condition_id,
                "slug": spec.slug,
                "asset": spec.asset,
                "horizon": spec.horizon,
                "market_start": spec.window_start,
                "eligible": not reasons,
                "ineligibility_reasons": reasons,
                "primary_preopen_taker": label,
                "binance_momentum_15s_log_return": binance_momentum,
                "binance_momentum_15s_direction": binance_direction,
                "binance_momentum_15s_aligned": (
                    label["outcome"] == binance_direction if label and binance_direction else None
                ),
                "chainlink_momentum_15s_log_return": chainlink_momentum,
                "chainlink_momentum_15s_direction": chainlink_direction,
                "chainlink_momentum_15s_aligned": (
                    label["outcome"] == chainlink_direction if label and chainlink_direction else None
                ),
                "btc_lead_15s_log_return": btc_lead,
                "btc_lead_15s_direction": btc_lead_direction,
                "btc_lead_15s_aligned": (
                    label["outcome"] == btc_lead_direction if label and btc_lead_direction else None
                ),
            }
        )
    return tuple(output)


def summarize_preopen(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row["eligible"]]

    def candidate(field: str) -> dict[str, Any]:
        values = [row for row in eligible if row[field] is not None]
        aligned = sum(bool(row[field]) for row in values)
        return {
            "eligible_conditions": len(values),
            "aligned_conditions": aligned,
            "alignment_share": aligned / len(values) if values else None,
        }

    lead_distribution = [int(row["primary_preopen_taker"]["lead_seconds"]) for row in eligible]
    return {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "study_status": "COLLECTING",
        "stopping_rule": {
            "eligible_conditions_target": 30,
            "eligible_conditions_observed_this_bundle": len(eligible),
            "gate_evaluation_deferred": True,
        },
        "binance_momentum_15s": candidate("binance_momentum_15s_aligned"),
        "chainlink_momentum_15s": candidate("chainlink_momentum_15s_aligned"),
        "btc_lead_15s_descriptive": candidate("btc_lead_15s_aligned"),
        "lead_seconds": sorted(lead_distribution),
        "ineligible_conditions": [
            {"condition_id": row["condition_id"], "slug": row["slug"], "reasons": row["ineligibility_reasons"]}
            for row in rows
            if not row["eligible"]
        ],
    }


def run_preopen_analysis(
    *,
    bundle_dir: str | Path,
    expected_bundle_manifest_sha256: str,
    receipts_dir: str | Path,
    expected_receipt_rows_sha256: str,
    output_dir: str | Path,
    code_commit: str,
    api: BinanceSpotAPI | None = None,
) -> dict[str, Any]:
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output}")
    bundle = Path(bundle_dir)
    bundle_manifest_path = bundle / "prospective_bundle_manifest.json"
    bundle_manifest = _load_json_sha(bundle_manifest_path, expected_bundle_manifest_sha256, "bundle manifest")
    if bundle_manifest.get("clean_finalize") is not True:
        raise ValueError("bundle did not cleanly finalize")
    started_ms = _iso_ms(bundle_manifest.get("started_at"), "bundle started_at")
    ended_ms = _iso_ms(bundle_manifest.get("ended_at"), "bundle ended_at")

    chainlink_manifest = _load_json_sha(
        bundle / "chainlink" / "chainlink_twap_manifest.json",
        str(bundle_manifest["chainlink"]["sha256"]),
        "Chainlink manifest",
    )
    if chainlink_manifest.get("reconnect_count") != 0:
        raise ValueError("v3 analysis currently requires zero Chainlink reconnects")
    if (bundle / "chainlink" / "chainlink_twap_gaps.jsonl").read_bytes().strip():
        raise ValueError("v3 analysis currently requires an empty Chainlink gap artifact")

    receipt_rows_path = Path(receipts_dir) / "maker_taker_rows.jsonl"
    receipt_rows = _load_jsonl_sha(receipt_rows_path, expected_receipt_rows_sha256, "receipt rows")
    receipt_summary = json.loads((Path(receipts_dir) / "maker_taker_summary.json").read_text())
    specs = {
        condition_id: market_spec(condition_id=condition_id, slug=str(values["slug"]), title=str(values["slug"]))
        for condition_id, values in receipt_summary["per_market"].items()
    }
    envelopes, binance = collect_binance_1s(
        api or BinanceSpotAPI(),
        start_time_ms=started_ms,
        end_time_ms=ended_ms + 1_000,
    )
    rows = build_preopen_rows(
        specs=specs,
        episodes=group_receipt_episodes(receipt_rows),
        chainlink=load_chainlink_events(bundle / "chainlink" / "chainlink_twap_raw.jsonl"),
        binance=binance,
        capture_started_ms=started_ms,
        capture_ended_ms=ended_ms,
    )
    summary = summarize_preopen(rows)

    output.mkdir(parents=True)
    binance_path = output / "binance_1s_raw.jsonl"
    rows_path = output / "preopen_condition_rows.jsonl"
    summary_path = output / "preopen_signal_summary.json"
    manifest_path = output / "preopen_analysis_manifest.json"
    _write_jsonl(binance_path, envelopes)
    _write_jsonl(rows_path, rows)
    _write_json(summary_path, summary)
    manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "collection_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "bundle_manifest": {"path": str(bundle_manifest_path), "sha256": expected_bundle_manifest_sha256},
        "receipt_rows": {"path": str(receipt_rows_path), "sha256": expected_receipt_rows_sha256},
        "condition_count": len(rows),
        "eligible_condition_count": sum(bool(row["eligible"]) for row in rows),
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in (binance_path, rows_path, summary_path)
        },
    }
    _write_json(manifest_path, manifest)
    return {"manifest": manifest, "summary": summary, "output_dir": str(output)}


def _direction(value: float | None) -> str | None:
    if value is None or value == 0:
        return None
    return "Up" if value > 0 else "Down"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--expected-bundle-manifest-sha256", required=True)
    parser.add_argument("--receipts-dir", required=True)
    parser.add_argument("--expected-receipt-rows-sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--code-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(json.dumps(run_preopen_analysis(
        bundle_dir=args.bundle_dir,
        expected_bundle_manifest_sha256=args.expected_bundle_manifest_sha256,
        receipts_dir=args.receipts_dir,
        expected_receipt_rows_sha256=args.expected_receipt_rows_sha256,
        output_dir=args.output,
        code_commit=args.code_commit,
    ), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())

