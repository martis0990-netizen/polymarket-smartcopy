"""Stage 2H source-time-only historical paired-leg decomposition.

This module intentionally does not reconstruct causal intent. Historical BACKFILL
``first_observed_time`` values are ingestion provenance and are never used by the
analysis below.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable, Sequence

from .classify import classify_market
from .models import MarketFamily, ObservationMode, WalletActivity


STAGE2H_SCHEMA_VERSION = "smartcopy-stage2h-paired-leg-v1"
FROZEN_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
FROZEN_START = datetime(2026, 8, 25, 0, 0, 0, tzinfo=timezone.utc)
FROZEN_END = datetime(2026, 8, 25, 23, 59, 59, tzinfo=timezone.utc)
FROZEN_NORMALIZED_SHA256 = "5fd68d01a6768818303f288c9a61285c3ebc848f90566e2c05380c1bd895b5b4"
_TARGET_FAMILIES = {MarketFamily.CRYPTO_UPDOWN_5M, MarketFamily.CRYPTO_UPDOWN_15M}
_BTC = re.compile(r"\b(?:bitcoin|btc)\b", re.I)
_ETH = re.compile(r"\b(?:ethereum|eth)\b", re.I)
_MARKETS_FILE = "stage2h_paired_markets.jsonl"
_SUMMARY_FILE = "stage2h_summary.json"


class HistoricalEvidenceError(ValueError):
    """Raised when historical evidence cannot satisfy the frozen Stage 2H contract."""


@dataclass(frozen=True, slots=True)
class LegStats:
    fill_count: int
    total_size: float
    total_usdc: float
    vwap_price: float | None
    first_source_event_time: datetime | None
    last_source_event_time: datetime | None


@dataclass(frozen=True, slots=True)
class PairedMarketRecord:
    condition_id: str
    symbol: str
    market_family: MarketFamily
    title: str | None
    slug: str | None
    event_slug: str | None
    buy_row_count: int
    sell_row_count: int
    up: LegStats
    down: LegStats
    matched_size: float
    excess_up: float
    excess_down: float
    paired_fraction: float | None
    pair_vwap_sum: float | None
    gross_pair_margin_per_unit: float | None
    matched_average_cost: float | None
    first_leg_gap_seconds: float | None
    first_leg_order: str | None
    market_activity_span_seconds: float


@dataclass(frozen=True, slots=True)
class PairedSummary:
    schema_version: str
    included_market_count: int
    excluded_ambiguous_market_count: int
    markets_with_both_buy_legs: int
    markets_with_one_buy_leg_only: int
    buy_row_count: int
    sell_row_count: int
    matched_token_size_total: float
    excess_up_token_size_total: float
    excess_down_token_size_total: float
    median_paired_fraction: float | None
    median_pair_vwap_sum: float | None
    mean_pair_vwap_sum: float | None
    pair_vwap_sum_lt_1_count: int
    pair_vwap_sum_lt_1_share: float | None
    pair_vwap_sum_le_099_count: int
    pair_vwap_sum_le_099_share: float | None
    median_first_leg_gap_seconds: float | None
    p25_first_leg_gap_seconds: float | None
    p75_first_leg_gap_seconds: float | None
    up_first_count: int
    down_first_count: int
    same_second_count: int


def analyze_paired_legs(
    activities: Iterable[WalletActivity],
    *,
    start: datetime,
    end: datetime,
) -> tuple[tuple[PairedMarketRecord, ...], PairedSummary]:
    """Apply the frozen Stage 2H decomposition to BACKFILL activity rows."""

    start = _aware_utc(start, "start")
    end = _aware_utc(end, "end")
    if start > end:
        raise HistoricalEvidenceError("start must be <= end")

    scoped: dict[str, list[WalletActivity]] = {}
    for item in activities:
        if item.observation_mode != ObservationMode.BACKFILL:
            raise HistoricalEvidenceError("Stage 2H accepts BACKFILL evidence only")
        source_time = _aware_utc(item.source_event_time, "source_event_time")
        if not start <= source_time <= end:
            raise HistoricalEvidenceError("source activity lies outside the frozen requested interval")
        if item.activity_type.upper() != "TRADE":
            continue
        classification = classify_market(title=item.title, slug=item.slug, event_slug=item.event_slug)
        if classification.family not in _TARGET_FAMILIES:
            continue
        symbol = _target_symbol(item)
        if symbol is None:
            continue
        scoped.setdefault(item.condition_id, []).append(item)

    records: list[PairedMarketRecord] = []
    excluded_ambiguous = 0
    for condition_id, rows in scoped.items():
        observed_outcomes = {_canonical_outcome(row.outcome) for row in rows}
        if None in observed_outcomes or not observed_outcomes.issubset({"Up", "Down"}):
            excluded_ambiguous += 1
            continue
        records.append(_market_record(condition_id, rows))

    records.sort(key=lambda row: (row.condition_id, row.symbol, row.market_family.value))
    return tuple(records), _summary(records, excluded_ambiguous)


def load_normalized_activity_jsonl(path: str | Path) -> tuple[WalletActivity, ...]:
    """Load normalized Stage 1 activity evidence without using observation time analytically."""

    items: list[WalletActivity] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                items.append(
                    WalletActivity(
                        proxy_wallet=str(row["proxy_wallet"]).lower(),
                        source_event_time=_parse_datetime(row["source_event_time"]),
                        first_observed_time=_parse_datetime(row["first_observed_time"]),
                        condition_id=str(row.get("condition_id") or ""),
                        activity_type=str(row.get("activity_type") or "UNKNOWN"),
                        side=_optional_str(row.get("side")),
                        size=float(row.get("size") or 0.0),
                        usdc_size=float(row.get("usdc_size") or 0.0),
                        price=_optional_float(row.get("price")),
                        asset=_optional_str(row.get("asset")),
                        transaction_hash=_optional_str(row.get("transaction_hash")),
                        title=_optional_str(row.get("title")),
                        slug=_optional_str(row.get("slug")),
                        event_slug=_optional_str(row.get("event_slug")),
                        outcome=_optional_str(row.get("outcome")),
                        observation_mode=ObservationMode(row.get("observation_mode", ObservationMode.BACKFILL.value)),
                        raw={},
                    )
                )
            except Exception as exc:
                raise HistoricalEvidenceError(f"invalid normalized activity at line {line_number}: {exc}") from exc
    return tuple(items)


def write_stage2h_artifacts(
    *,
    normalized_activity_path: str | Path,
    output_dir: str | Path,
    start: datetime = FROZEN_START,
    end: datetime = FROZEN_END,
    expected_sha256: str = FROZEN_NORMALIZED_SHA256,
) -> dict[str, Any]:
    """Materialize deterministic Stage 2H output for the frozen evidence file."""

    source = Path(normalized_activity_path)
    digest = _sha256(source)
    if digest != expected_sha256:
        raise HistoricalEvidenceError(
            f"normalized activity SHA256 mismatch: expected {expected_sha256}, got {digest}"
        )

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    markets_path = root / _MARKETS_FILE
    summary_path = root / _SUMMARY_FILE
    for target in (markets_path, summary_path):
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing Stage 2H artifact: {target}")

    activities = load_normalized_activity_jsonl(source)
    records, summary = analyze_paired_legs(activities, start=start, end=end)

    with markets_path.open("xb") as handle:
        for record in records:
            handle.write(_json_line(_market_to_dict(record)))
        handle.flush()

    payload: dict[str, Any] = _summary_to_dict(summary)
    payload.update(
        {
            "wallet": FROZEN_WALLET,
            "range": {"start": _iso(start), "end": _iso(end)},
            "input": {"path": source.name, "sha256": digest, "bytes": source.stat().st_size},
            "artifacts": {"markets": _artifact_record(markets_path)},
            "claims": "SOURCE_TIME_DESCRIPTIVE_ONLY",
        }
    )
    with summary_path.open("xb") as handle:
        handle.write(_json_line(payload))
        handle.flush()
    return payload


def _market_record(condition_id: str, rows: list[WalletActivity]) -> PairedMarketRecord:
    first = rows[0]
    classification = classify_market(title=first.title, slug=first.slug, event_slug=first.event_slug)
    symbol = _target_symbol(first)
    if symbol is None:
        raise HistoricalEvidenceError("target market lost symbol classification")

    buys = [row for row in rows if (row.side or "").upper() == "BUY"]
    sells = [row for row in rows if (row.side or "").upper() == "SELL"]
    up = _leg_stats([row for row in buys if _canonical_outcome(row.outcome) == "Up"])
    down = _leg_stats([row for row in buys if _canonical_outcome(row.outcome) == "Down"])

    matched = min(up.total_size, down.total_size)
    total_buy_size = up.total_size + down.total_size
    paired_fraction = (2.0 * matched / total_buy_size) if total_buy_size > 0 else None
    pair_vwap_sum = None
    gross_margin = None
    matched_average_cost = None
    if up.vwap_price is not None and down.vwap_price is not None:
        pair_vwap_sum = up.vwap_price + down.vwap_price
        gross_margin = 1.0 - pair_vwap_sum
        matched_average_cost = matched * pair_vwap_sum

    gap = None
    order = None
    if up.first_source_event_time is not None and down.first_source_event_time is not None:
        delta = (up.first_source_event_time - down.first_source_event_time).total_seconds()
        gap = abs(delta)
        order = "UP_FIRST" if delta < 0 else "DOWN_FIRST" if delta > 0 else "SAME_SECOND"

    source_times = [row.source_event_time for row in rows]
    span = (max(source_times) - min(source_times)).total_seconds() if source_times else 0.0
    return PairedMarketRecord(
        condition_id=condition_id,
        symbol=symbol,
        market_family=classification.family,
        title=first.title,
        slug=first.slug,
        event_slug=first.event_slug,
        buy_row_count=len(buys),
        sell_row_count=len(sells),
        up=up,
        down=down,
        matched_size=matched,
        excess_up=max(up.total_size - down.total_size, 0.0),
        excess_down=max(down.total_size - up.total_size, 0.0),
        paired_fraction=paired_fraction,
        pair_vwap_sum=pair_vwap_sum,
        gross_pair_margin_per_unit=gross_margin,
        matched_average_cost=matched_average_cost,
        first_leg_gap_seconds=gap,
        first_leg_order=order,
        market_activity_span_seconds=span,
    )


def _leg_stats(rows: list[WalletActivity]) -> LegStats:
    total_size = sum(row.size for row in rows)
    total_usdc = sum(row.usdc_size for row in rows)
    priced = [row for row in rows if row.price is not None and row.size > 0]
    priced_size = sum(row.size for row in priced)
    vwap = (sum(float(row.price) * row.size for row in priced) / priced_size) if priced_size > 0 else None
    source_times = [row.source_event_time for row in rows]
    return LegStats(
        fill_count=len(rows),
        total_size=total_size,
        total_usdc=total_usdc,
        vwap_price=vwap,
        first_source_event_time=min(source_times) if source_times else None,
        last_source_event_time=max(source_times) if source_times else None,
    )


def _summary(records: list[PairedMarketRecord], excluded_ambiguous: int) -> PairedSummary:
    both = [row for row in records if row.up.total_size > 0 and row.down.total_size > 0]
    one = [row for row in records if (row.up.total_size > 0) ^ (row.down.total_size > 0)]
    pair_sums = [row.pair_vwap_sum for row in both if row.pair_vwap_sum is not None]
    gaps = [row.first_leg_gap_seconds for row in both if row.first_leg_gap_seconds is not None]
    fractions = [row.paired_fraction for row in records if row.paired_fraction is not None]
    lt_1 = sum(value < 1.0 for value in pair_sums)
    le_099 = sum(value <= 0.99 for value in pair_sums)
    orders = [row.first_leg_order for row in both if row.first_leg_order is not None]
    return PairedSummary(
        schema_version=STAGE2H_SCHEMA_VERSION,
        included_market_count=len(records),
        excluded_ambiguous_market_count=excluded_ambiguous,
        markets_with_both_buy_legs=len(both),
        markets_with_one_buy_leg_only=len(one),
        buy_row_count=sum(row.buy_row_count for row in records),
        sell_row_count=sum(row.sell_row_count for row in records),
        matched_token_size_total=sum(row.matched_size for row in records),
        excess_up_token_size_total=sum(row.excess_up for row in records),
        excess_down_token_size_total=sum(row.excess_down for row in records),
        median_paired_fraction=median(fractions) if fractions else None,
        median_pair_vwap_sum=median(pair_sums) if pair_sums else None,
        mean_pair_vwap_sum=mean(pair_sums) if pair_sums else None,
        pair_vwap_sum_lt_1_count=lt_1,
        pair_vwap_sum_lt_1_share=(lt_1 / len(pair_sums)) if pair_sums else None,
        pair_vwap_sum_le_099_count=le_099,
        pair_vwap_sum_le_099_share=(le_099 / len(pair_sums)) if pair_sums else None,
        median_first_leg_gap_seconds=median(gaps) if gaps else None,
        p25_first_leg_gap_seconds=_linear_quantile(gaps, 0.25),
        p75_first_leg_gap_seconds=_linear_quantile(gaps, 0.75),
        up_first_count=orders.count("UP_FIRST"),
        down_first_count=orders.count("DOWN_FIRST"),
        same_second_count=orders.count("SAME_SECOND"),
    )


def _target_symbol(item: WalletActivity) -> str | None:
    text = " ".join(part for part in (item.title, item.slug, item.event_slug) if part)
    btc = bool(_BTC.search(text))
    eth = bool(_ETH.search(text))
    if btc == eth:
        return None
    return "BTC" if btc else "ETH"


def _canonical_outcome(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized == "up":
        return "Up"
    if normalized == "down":
        return "Down"
    return None


def _linear_quantile(values: list[float], probability: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _parse_datetime(value: Any) -> datetime:
    if not isinstance(value, str) or not value:
        raise HistoricalEvidenceError("timestamp must be a non-empty ISO-8601 string")
    return _aware_utc(datetime.fromisoformat(value.replace("Z", "+00:00")), "timestamp")


def _aware_utc(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise HistoricalEvidenceError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _market_to_dict(record: PairedMarketRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["market_family"] = record.market_family.value
    for leg_name in ("up", "down"):
        payload[leg_name]["first_source_event_time"] = _iso(getattr(record, leg_name).first_source_event_time)
        payload[leg_name]["last_source_event_time"] = _iso(getattr(record, leg_name).last_source_event_time)
    return payload


def _summary_to_dict(summary: PairedSummary) -> dict[str, Any]:
    return asdict(summary)


def _json_line(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_record(path: Path) -> dict[str, Any]:
    return {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _optional_str(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _optional_float(value: Any) -> float | None:
    return None if value is None or value == "" else float(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run frozen SmartCopy Stage 2H paired-leg decomposition")
    parser.add_argument("--activity", required=True, help="normalized Stage 1 activity JSONL")
    parser.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_stage2h_artifacts(normalized_activity_path=args.activity, output_dir=args.output)
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
