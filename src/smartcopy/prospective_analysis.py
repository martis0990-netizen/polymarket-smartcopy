"""Join prospective Bonereaper first-taker labels to strict-pre Chainlink and Binance data."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence

from smartcopy.correction_overlay import MarketSpec, market_spec
from smartcopy.external_signal import BinanceKline, BinanceSpotAPI, normalize_binance_response
from smartcopy.prospective_signal import collapse_primary_taker

_SCHEMA = "smartcopy-bonereaper-prospective-analysis-v2"
_CONTRACT_COMMIT = "0065f7ca8c38e435e0a859b06724040cfd01a900"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_BINANCE_RAW = "binance_1s_raw.jsonl"
_CONDITIONS = "condition_signal_rows.jsonl"
_SUMMARY = "prospective_signal_summary.json"
_MANIFEST = "prospective_analysis_manifest.json"


def run_analysis(
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
    bundle_manifest = _load_json_sha(
        bundle_manifest_path,
        expected_bundle_manifest_sha256,
        "bundle manifest",
    )
    if bundle_manifest.get("contract_commit") != _CONTRACT_COMMIT:
        raise ValueError("bundle contract commit mismatch")
    if bundle_manifest.get("clean_finalize") is not True:
        raise ValueError("bundle did not cleanly finalize")
    started_ms = _iso_ms(bundle_manifest.get("started_at"), "bundle started_at")
    ended_ms = _iso_ms(bundle_manifest.get("ended_at"), "bundle ended_at")

    chainlink_manifest_path = bundle / "chainlink" / "chainlink_twap_manifest.json"
    chainlink_manifest = _load_json_sha(
        chainlink_manifest_path,
        str(bundle_manifest["chainlink"]["sha256"]),
        "Chainlink manifest",
    )
    if chainlink_manifest.get("reconnect_count") != 0:
        raise ValueError("v2 analysis currently requires zero Chainlink reconnects")
    gap_path = bundle / "chainlink" / "chainlink_twap_gaps.jsonl"
    if gap_path.read_bytes().strip():
        raise ValueError("v2 analysis currently requires an empty Chainlink gap artifact")
    chainlink = load_chainlink_events(bundle / "chainlink" / "chainlink_twap_raw.jsonl")

    receipt_rows_path = Path(receipts_dir) / "maker_taker_rows.jsonl"
    receipt_rows = _load_jsonl_sha(
        receipt_rows_path,
        expected_receipt_rows_sha256,
        "receipt rows",
    )
    receipt_summary = json.loads((Path(receipts_dir) / "maker_taker_summary.json").read_text())
    specs = {
        condition_id: market_spec(
            condition_id=condition_id,
            slug=str(values["slug"]),
            title=str(values["slug"]),
        )
        for condition_id, values in receipt_summary["per_market"].items()
    }

    # The immutable bundle can contain delayed fills from markets which opened
    # before capture.  Those markets are deliberately ineligible; extending the
    # Binance request back to their opens would both waste data and can exceed
    # the API's 1,000-bar limit.  One pre-capture minute is sufficient for every
    # condition that can pass the prospective pre-open coverage gate.
    start_external_ms = started_ms - 60_000
    end_external_ms = ended_ms + 1_000
    envelopes, binance = collect_binance_1s(
        api or BinanceSpotAPI(),
        start_time_ms=start_external_ms,
        end_time_ms=end_external_ms,
    )
    episodes = group_receipt_episodes(receipt_rows)
    condition_rows = build_condition_rows(
        specs=specs,
        episodes=episodes,
        chainlink=chainlink,
        binance=binance,
        capture_started_ms=started_ms,
        capture_ended_ms=ended_ms,
    )
    eligible = [row for row in condition_rows if row["eligible"]]
    summary = summarize_interim(condition_rows)

    output.mkdir(parents=True)
    binance_path = output / _BINANCE_RAW
    conditions_path = output / _CONDITIONS
    summary_path = output / _SUMMARY
    manifest_path = output / _MANIFEST
    _write_jsonl(binance_path, envelopes)
    _write_jsonl(conditions_path, condition_rows)
    _write_json(summary_path, summary)
    manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "collection_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "bundle_manifest": {
            "path": str(bundle_manifest_path),
            "sha256": expected_bundle_manifest_sha256,
        },
        "receipt_rows": {
            "path": str(receipt_rows_path),
            "sha256": expected_receipt_rows_sha256,
            "rows": len(receipt_rows),
        },
        "condition_count": len(condition_rows),
        "eligible_condition_count": len(eligible),
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in (binance_path, conditions_path, summary_path)
        },
    }
    _write_json(manifest_path, manifest)
    return {"manifest": manifest, "summary": summary, "output_dir": str(output)}


def collect_binance_1s(
    api: BinanceSpotAPI,
    *,
    start_time_ms: int,
    end_time_ms: int,
) -> tuple[tuple[dict[str, Any], ...], dict[str, tuple[BinanceKline, ...]]]:
    if end_time_ms <= start_time_ms:
        raise ValueError("invalid Binance collection interval")
    if math.ceil((end_time_ms - start_time_ms) / 1_000) > 1_000:
        raise ValueError("one bounded v2 analysis supports at most 1000 Binance seconds")
    envelopes: list[dict[str, Any]] = []
    normalized: dict[str, tuple[BinanceKline, ...]] = {}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        url, payload = api.klines(
            symbol=symbol,
            interval="1s",
            start_time_ms=start_time_ms,
            end_time_ms=end_time_ms - 1,
            limit=1_000,
        )
        envelope = {
            "collection_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "request": {
                "symbol": symbol,
                "interval": "1s",
                "start_time_ms": start_time_ms,
                "end_time_ms": end_time_ms - 1,
                "limit": 1_000,
                "url": url,
            },
            "response": payload,
        }
        bars = normalize_binance_response(envelope)
        if not bars:
            raise ValueError(f"empty Binance response for {symbol}")
        envelopes.append(envelope)
        normalized[symbol] = bars
    return tuple(envelopes), normalized


def load_chainlink_events(path: str | Path) -> dict[str, tuple[dict[str, Any], ...]]:
    by_symbol: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line_number, line in enumerate(Path(path).read_bytes().splitlines(), start=1):
        payload = json.loads(line)
        row = payload.get("normalized")
        if not isinstance(row, dict):
            raise ValueError(f"Chainlink line {line_number}: missing normalized event")
        symbol = str(row.get("symbol"))
        if symbol not in {"btc/usd", "eth/usd"}:
            continue
        row = dict(row)
        row["value_decimal"] = Decimal(str(row["value"]))
        by_symbol[symbol].append(row)
    for symbol in ("btc/usd", "eth/usd"):
        values = sorted(by_symbol[symbol], key=lambda item: int(item["source_timestamp_ms"]))
        if not values:
            raise ValueError(f"no Chainlink events for {symbol}")
        by_symbol[symbol] = values
    return {symbol: tuple(values) for symbol, values in by_symbol.items()}


def group_receipt_episodes(rows: Sequence[dict[str, Any]]) -> dict[str, tuple[dict[str, Any], ...]]:
    grouped: dict[tuple[str, str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        role = str(row.get("schema_corrected_role"))
        if role not in {"MAKER", "TAKER"}:
            raise ValueError("prospective receipt row has unresolved role")
        key = (
            str(row["condition_id"]),
            str(row["outcome"]),
            int(row["source_second"]),
            role,
        )
        grouped[key].append(row)
    by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (condition_id, outcome, second, role), parts in grouped.items():
        by_condition[condition_id].append(
            {
                "condition_id": condition_id,
                "outcome": outcome,
                "source_second": second,
                "role": role,
                "fill_rows": len(parts),
                "source_size": sum(float(row["source_size"]) for row in parts),
                "source_notional": sum(float(row["source_notional"]) for row in parts),
            }
        )
    return {
        condition_id: tuple(sorted(values, key=lambda row: (row["source_second"], row["outcome"], row["role"])))
        for condition_id, values in by_condition.items()
    }


def build_condition_rows(
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
        reasons: list[str] = []
        start_ms = spec.window_start * 1_000
        if capture_started_ms > start_ms - 60_000:
            reasons.append("INCOMPLETE_PRE_OPEN_CHAINLINK_COVERAGE")
        if capture_ended_ms <= start_ms:
            reasons.append("CAPTURE_ENDED_BEFORE_MARKET_OPEN")
        label = collapse_primary_taker(episodes.get(condition_id, ()))
        if label is None:
            reasons.append("NO_UNAMBIGUOUS_FIRST_TAKER")
        decision_ms = int(label["source_second"]) * 1_000 if label is not None else None
        if decision_ms is not None and decision_ms < start_ms:
            # K is only bound at market start.  Comparing a pre-open decision
            # with that later value would leak future information.
            reasons.append("PRE_OPEN_PRIMARY_TAKER")
        symbol = "btc/usd" if spec.asset == "BTC" else "eth/usd"
        opening = _latest_at_or_before(chainlink[symbol], start_ms)
        if opening is None:
            reasons.append("OPENING_CHAINLINK_UPDATE_MISSING")
        current = None
        momentum = None
        if label is not None and decision_ms is not None:
            current = _latest_strict_pre(chainlink[symbol], decision_ms)
            if current is None:
                reasons.append("STRICT_PRE_CHAINLINK_MISSING")
            momentum = _momentum_15s(
                binance[f"{spec.asset}USDT"],
                int(label["source_second"]),
            )
            if momentum is None:
                reasons.append("STRICT_PRE_BINANCE_15S_MISSING")
        barrier_bps = None
        barrier_direction = None
        if opening is not None and current is not None and decision_ms is not None and decision_ms >= start_ms:
            barrier_bps = 10_000 * math.log(float(current["value_decimal"] / opening["value_decimal"]))
            barrier_direction = _direction(barrier_bps)
        momentum_direction = _direction(momentum) if momentum is not None else None
        output.append(
            {
                "condition_id": condition_id,
                "slug": spec.slug,
                "asset": spec.asset,
                "horizon": spec.horizon,
                "market_start": spec.window_start,
                "eligible": not reasons,
                "ineligibility_reasons": reasons,
                "primary_taker": label,
                "opening_chainlink_timestamp_ms": int(opening["source_timestamp_ms"]) if opening else None,
                "opening_chainlink_value": format(opening["value_decimal"], "f") if opening else None,
                "strict_pre_chainlink_timestamp_ms": int(current["source_timestamp_ms"]) if current else None,
                "strict_pre_chainlink_value": format(current["value_decimal"], "f") if current else None,
                "barrier_bps": barrier_bps,
                "barrier_direction": barrier_direction,
                "momentum_15s_log_return": momentum,
                "momentum_15s_direction": momentum_direction,
                "barrier_aligned": (
                    label["outcome"] == barrier_direction if label and barrier_direction else None
                ),
                "momentum_15s_aligned": (
                    label["outcome"] == momentum_direction if label and momentum_direction else None
                ),
            }
        )
    return tuple(output)


def summarize_interim(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    eligible = [row for row in rows if row["eligible"]]
    def candidate(field: str) -> dict[str, Any]:
        values = [row for row in eligible if row[field] is not None]
        return {
            "eligible_conditions": len(values),
            "aligned_conditions": sum(bool(row[field]) for row in values),
            "alignment_share": (
                sum(bool(row[field]) for row in values) / len(values) if values else None
            ),
        }
    taker_conditions = len(eligible)
    return {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "study_status": "COLLECTING",
        "stopping_rule": {
            "eligible_conditions_target": 40,
            "taker_conditions_target": 20,
            "eligible_conditions_observed_this_bundle": len(eligible),
            "taker_conditions_observed_this_bundle": taker_conditions,
            "gate_evaluation_deferred": True,
        },
        "barrier": candidate("barrier_aligned"),
        "momentum_15s": candidate("momentum_15s_aligned"),
        "ineligible_conditions": [
            {
                "condition_id": row["condition_id"],
                "slug": row["slug"],
                "reasons": row["ineligibility_reasons"],
            }
            for row in rows
            if not row["eligible"]
        ],
    }


def _latest_at_or_before(rows: Sequence[dict[str, Any]], timestamp_ms: int) -> dict[str, Any] | None:
    eligible = [row for row in rows if int(row["source_timestamp_ms"]) <= timestamp_ms]
    return eligible[-1] if eligible else None


def _latest_strict_pre(rows: Sequence[dict[str, Any]], timestamp_ms: int) -> dict[str, Any] | None:
    eligible = [row for row in rows if int(row["source_timestamp_ms"]) < timestamp_ms]
    return eligible[-1] if eligible else None


def _momentum_15s(bars: Sequence[BinanceKline], source_second: int) -> float | None:
    by_second = {bar.source_second: bar.close for bar in bars}
    current = by_second.get(source_second - 1)
    previous = by_second.get(source_second - 16)
    if current is None or previous is None:
        return None
    return math.log(current / previous)


def _direction(value: float | None) -> str | None:
    if value is None or value == 0:
        return None
    return "Up" if value > 0 else "Down"


def _load_json_sha(path: Path, expected: str, label: str) -> dict[str, Any]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected.lower():
        raise ValueError(f"{label} SHA256 mismatch: expected {expected.lower()}, got {digest}")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return value


def _load_jsonl_sha(path: Path, expected: str, label: str) -> tuple[dict[str, Any], ...]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected.lower():
        raise ValueError(f"{label} SHA256 mismatch: expected {expected.lower()}, got {digest}")
    values = tuple(json.loads(line) for line in raw.splitlines())
    if any(not isinstance(value, dict) for value in values):
        raise ValueError(f"{label} must contain objects")
    return values


def _iso_ms(value: Any, label: str) -> int:
    if not isinstance(value, str):
        raise ValueError(f"{label} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    with path.open("xb") as handle:
        for row in rows:
            handle.write((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())


def _write_json(path: Path, value: Any) -> None:
    with path.open("xb") as handle:
        handle.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    result = run_analysis(
        bundle_dir=args.bundle_dir,
        expected_bundle_manifest_sha256=args.expected_bundle_manifest_sha256,
        receipts_dir=args.receipts_dir,
        expected_receipt_rows_sha256=args.expected_receipt_rows_sha256,
        output_dir=args.output,
        code_commit=args.code_commit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
