"""Historical unmatched-inventory outcome association under a frozen contract."""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median
from typing import Iterable

from .classify import classify_market
from .models import ClosedPosition, MarketFamily, ObservationMode, WalletActivity
from .paired_inventory import decompose_backfill

_SIZE_TOLERANCE = 1e-4
_TARGET = {MarketFamily.CRYPTO_UPDOWN_5M, MarketFamily.CRYPTO_UPDOWN_15M}
_SLUG = re.compile(r"^(btc|eth)-updown-(5m|15m)-(\d+)$", re.I)
_BUCKETS = ("Q1", "Q2", "Q3", "Q4", "OUTSIDE")


@dataclass(frozen=True, slots=True)
class UnmatchedOutcomeAlignment:
    condition_id: str
    market_family: MarketFamily
    coin: str | None
    paired_cost_per_unit: float
    unmatched_asset: str
    unmatched_outcome: str | None
    unmatched_size: float
    unit_closed_realized_pnl: float
    unmatched_inventory_realized_pnl: float
    sign: str
    last_residual_increasing_bucket: str


@dataclass(frozen=True, slots=True)
class AlignmentSlice:
    market_count: int
    positive_count: int
    negative_count: int
    zero_count: int
    positive_share: float | None
    negative_share: float | None
    zero_share: float | None
    unmatched_inventory_realized_pnl: float
    unmatched_pnl_median: float | None
    positive_pnl_magnitude: float
    negative_pnl_magnitude: float
    size_weighted_positive_share: float | None
    dominant_up: int
    dominant_down: int
    positive_pnl_by_bucket: dict[str, float]
    negative_pnl_by_bucket: dict[str, float]


@dataclass(frozen=True, slots=True)
class UnmatchedOutcomeAlignmentSummary:
    all_markets: AlignmentSlice
    pair_cost_lt_1: AlignmentSlice
    pair_cost_ge_1: AlignmentSlice
    by_segment: dict[str, AlignmentSlice]


def analyze_unmatched_outcome_alignment(
    activities: Iterable[WalletActivity],
    closed_positions: Iterable[ClosedPosition],
) -> tuple[UnmatchedOutcomeAlignment, ...]:
    activity_rows = tuple(activities)
    if any(row.observation_mode != ObservationMode.BACKFILL for row in activity_rows):
        raise ValueError("unmatched outcome alignment requires BACKFILL activity evidence only")

    target_rows = tuple(row for row in activity_rows if _is_target_buy(row))
    activity_by_condition: dict[str, list[WalletActivity]] = {}
    for row in target_rows:
        activity_by_condition.setdefault(row.condition_id, []).append(row)

    market_map = {market.condition_id: market for market in decompose_backfill(target_rows)}
    closed_map: dict[tuple[str, str], list[ClosedPosition]] = {}
    for row in closed_positions:
        if row.condition_id and row.asset:
            closed_map.setdefault((row.condition_id, row.asset), []).append(row)

    results: list[UnmatchedOutcomeAlignment] = []
    for condition_id, market in market_map.items():
        if not market.valid_binary_pair or len(market.legs) != 2 or len(market.residual_sizes) != 2:
            continue
        if market.paired_cost_per_unit is None:
            continue

        residuals = tuple(float(value) for value in market.residual_sizes)
        positive_indices = [index for index, value in enumerate(residuals) if value > 1e-9]
        if len(positive_indices) != 1:
            continue
        unmatched_index = positive_indices[0]
        unmatched_leg = market.legs[unmatched_index]
        unmatched_size = residuals[unmatched_index]

        eligible = True
        for leg in market.legs:
            closed = closed_map.get((condition_id, leg.asset))
            if not closed:
                eligible = False
                break
            closed_size = sum(row.total_bought for row in closed)
            if leg.buy_size <= 0 or closed_size <= 0:
                eligible = False
                break
            relative_error = abs(closed_size - leg.buy_size) / max(closed_size, leg.buy_size)
            if relative_error > _SIZE_TOLERANCE:
                eligible = False
                break
        if not eligible:
            continue

        unmatched_closed = closed_map[(condition_id, unmatched_leg.asset)]
        closed_size = sum(row.total_bought for row in unmatched_closed)
        closed_pnl = sum(row.realized_pnl for row in unmatched_closed)
        unit_pnl = closed_pnl / closed_size
        allocated = unmatched_size * unit_pnl
        sign = "positive" if unit_pnl > 1e-9 else "negative" if unit_pnl < -1e-9 else "zero"
        rows = activity_by_condition[condition_id]
        first = min(rows, key=lambda row: row.source_event_time)
        slug = first.slug or first.event_slug or ""
        match = _SLUG.match(slug)

        results.append(UnmatchedOutcomeAlignment(
            condition_id=condition_id,
            market_family=market.market_family,
            coin=match.group(1).upper() if match else None,
            paired_cost_per_unit=float(market.paired_cost_per_unit),
            unmatched_asset=unmatched_leg.asset,
            unmatched_outcome=unmatched_leg.outcome,
            unmatched_size=unmatched_size,
            unit_closed_realized_pnl=unit_pnl,
            unmatched_inventory_realized_pnl=allocated,
            sign=sign,
            last_residual_increasing_bucket=_last_residual_bucket(rows, match, market.market_family),
        ))

    return tuple(sorted(results, key=lambda item: item.condition_id))


def summarize_unmatched_outcome_alignment(
    rows: Iterable[UnmatchedOutcomeAlignment],
) -> UnmatchedOutcomeAlignmentSummary:
    records = tuple(rows)
    lt1 = tuple(item for item in records if item.paired_cost_per_unit < 1.0)
    ge1 = tuple(item for item in records if item.paired_cost_per_unit >= 1.0)
    segments = {
        "BTC_5M": tuple(item for item in records if item.coin == "BTC" and item.market_family == MarketFamily.CRYPTO_UPDOWN_5M),
        "BTC_15M": tuple(item for item in records if item.coin == "BTC" and item.market_family == MarketFamily.CRYPTO_UPDOWN_15M),
        "ETH_5M": tuple(item for item in records if item.coin == "ETH" and item.market_family == MarketFamily.CRYPTO_UPDOWN_5M),
        "ETH_15M": tuple(item for item in records if item.coin == "ETH" and item.market_family == MarketFamily.CRYPTO_UPDOWN_15M),
    }
    return UnmatchedOutcomeAlignmentSummary(
        all_markets=_slice(records),
        pair_cost_lt_1=_slice(lt1),
        pair_cost_ge_1=_slice(ge1),
        by_segment={name: _slice(values) for name, values in segments.items()},
    )


def _is_target_buy(row: WalletActivity) -> bool:
    if row.activity_type.upper() != "TRADE" or (row.side or "").upper() != "BUY":
        return False
    if not row.condition_id or not row.asset:
        return False
    return classify_market(title=row.title, slug=row.slug, event_slug=row.event_slug).family in _TARGET


def _last_residual_bucket(
    rows: list[WalletActivity],
    slug_match: re.Match[str] | None,
    family: MarketFamily,
) -> str:
    assets = sorted({row.asset for row in rows if row.asset})
    if len(assets) != 2:
        return "OUTSIDE"
    balances = {assets[0]: 0.0, assets[1]: 0.0}
    last_residual_time = None
    ordered = sorted(rows, key=lambda row: (row.source_event_time, row.transaction_hash or "", row.asset or ""))
    for row in ordered:
        assert row.asset is not None
        own = row.asset
        other = assets[1] if own == assets[0] else assets[0]
        deficit = max(0.0, balances[other] - balances[own])
        balancing = min(row.size, deficit)
        if row.size - balancing > 1e-12:
            last_residual_time = row.source_event_time
        balances[own] += row.size
    if last_residual_time is None or slug_match is None:
        return "OUTSIDE"
    start = int(slug_match.group(3))
    duration = 300 if family == MarketFamily.CRYPTO_UPDOWN_5M else 900
    timestamp = last_residual_time.timestamp()
    end = start + duration
    if timestamp < start or timestamp > end:
        return "OUTSIDE"
    fraction = (timestamp - start) / duration
    if fraction < 0.25:
        return "Q1"
    if fraction < 0.50:
        return "Q2"
    if fraction < 0.75:
        return "Q3"
    return "Q4"


def _slice(rows: tuple[UnmatchedOutcomeAlignment, ...]) -> AlignmentSlice:
    count = len(rows)
    positive = tuple(item for item in rows if item.sign == "positive")
    negative = tuple(item for item in rows if item.sign == "negative")
    zero = tuple(item for item in rows if item.sign == "zero")
    pnls = [item.unmatched_inventory_realized_pnl for item in rows]
    total_size = sum(item.unmatched_size for item in rows)
    positive_size = sum(item.unmatched_size for item in positive)
    positive_by_bucket = {bucket: 0.0 for bucket in _BUCKETS}
    negative_by_bucket = {bucket: 0.0 for bucket in _BUCKETS}
    for item in rows:
        bucket = item.last_residual_increasing_bucket
        if item.unmatched_inventory_realized_pnl > 0:
            positive_by_bucket[bucket] += item.unmatched_inventory_realized_pnl
        elif item.unmatched_inventory_realized_pnl < 0:
            negative_by_bucket[bucket] += item.unmatched_inventory_realized_pnl
    return AlignmentSlice(
        market_count=count,
        positive_count=len(positive),
        negative_count=len(negative),
        zero_count=len(zero),
        positive_share=(len(positive) / count) if count else None,
        negative_share=(len(negative) / count) if count else None,
        zero_share=(len(zero) / count) if count else None,
        unmatched_inventory_realized_pnl=sum(pnls),
        unmatched_pnl_median=median(pnls) if pnls else None,
        positive_pnl_magnitude=sum(item.unmatched_inventory_realized_pnl for item in positive),
        negative_pnl_magnitude=-sum(item.unmatched_inventory_realized_pnl for item in negative),
        size_weighted_positive_share=(positive_size / total_size) if total_size else None,
        dominant_up=sum(item.unmatched_outcome == "Up" for item in rows),
        dominant_down=sum(item.unmatched_outcome == "Down" for item in rows),
        positive_pnl_by_bucket=positive_by_bucket,
        negative_pnl_by_bucket=negative_by_bucket,
    )
