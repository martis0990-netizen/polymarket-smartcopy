"""Source-time-only paired inventory decomposition for historical wallet backfills.

This module intentionally does not infer live observation latency, maker/taker status,
profitability, or copyability. Historical BACKFILL rows are accounting evidence only.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from math import isclose
from statistics import median
from typing import Iterable

from .classify import classify_market
from .models import MarketFamily, ObservationMode, WalletActivity


_TARGET_FAMILIES = {
    MarketFamily.CRYPTO_UPDOWN_5M,
    MarketFamily.CRYPTO_UPDOWN_15M,
}


@dataclass(frozen=True, slots=True)
class LegInventory:
    asset: str
    outcome: str | None
    buy_rows: int
    buy_size: float
    buy_notional: float
    vwap: float | None
    first_source_time: datetime
    last_source_time: datetime


@dataclass(frozen=True, slots=True)
class MarketInventoryDecomposition:
    condition_id: str
    market_family: MarketFamily
    title: str | None
    slug: str | None
    event_slug: str | None
    legs: tuple[LegInventory, ...]
    valid_binary_pair: bool
    matched_size: float | None
    paired_cost_per_unit: float | None
    matched_pair_cost: float | None
    gross_pair_value_at_resolution: float | None
    gross_pair_edge: float | None
    residual_sizes: tuple[float, ...]
    directional_residual_notional: float | None
    first_leg_gap_seconds: float | None


@dataclass(frozen=True, slots=True)
class PairedInventorySummary:
    market_count: int
    valid_two_leg_market_count: int
    both_outcome_market_share: float | None
    buy_rows: int
    buy_notional: float
    matched_size: float
    matched_pair_cost: float
    residual_notional: float
    residual_size_share: float | None
    paired_cost_mean: float | None
    paired_cost_median: float | None
    paired_cost_p10: float | None
    paired_cost_p25: float | None
    paired_cost_p75: float | None
    paired_cost_p90: float | None
    paired_cost_lt_1_share: float | None
    paired_cost_le_099_share: float | None
    paired_cost_le_098_share: float | None
    paired_cost_le_095_share: float | None
    first_leg_gap_median_seconds: float | None
    first_leg_gap_le_1s_share: float | None
    first_leg_gap_le_5s_share: float | None
    first_leg_gap_le_15s_share: float | None
    first_leg_gap_le_30s_share: float | None
    first_leg_gap_le_60s_share: float | None


def decompose_backfill(
    activities: Iterable[WalletActivity],
    *,
    target_families_only: bool = True,
) -> tuple[MarketInventoryDecomposition, ...]:
    rows = tuple(activities)
    if any(row.observation_mode != ObservationMode.BACKFILL for row in rows):
        raise ValueError("paired historical decomposition requires BACKFILL evidence only")

    grouped: dict[str, list[WalletActivity]] = {}
    for row in rows:
        if row.activity_type.upper() != "TRADE" or (row.side or "").upper() != "BUY":
            continue
        if not row.condition_id or not row.asset:
            continue
        family = classify_market(title=row.title, slug=row.slug, event_slug=row.event_slug).family
        if target_families_only and family not in _TARGET_FAMILIES:
            continue
        grouped.setdefault(row.condition_id, []).append(row)

    results = [_decompose_market(condition_id, market_rows) for condition_id, market_rows in grouped.items()]
    return tuple(sorted(results, key=lambda item: item.condition_id))


def summarize_decomposition(
    markets: Iterable[MarketInventoryDecomposition],
) -> PairedInventorySummary:
    records = tuple(markets)
    pairs = tuple(item for item in records if item.valid_binary_pair and item.paired_cost_per_unit is not None)

    buy_rows = sum(leg.buy_rows for item in records for leg in item.legs)
    buy_notional = sum(leg.buy_notional for item in records for leg in item.legs)
    total_leg_size = sum(leg.buy_size for item in records for leg in item.legs)
    matched_size = sum(item.matched_size or 0.0 for item in pairs)
    matched_cost = sum(item.matched_pair_cost or 0.0 for item in pairs)
    residual_notional = sum(item.directional_residual_notional or 0.0 for item in pairs)
    residual_size = sum(sum(item.residual_sizes) for item in pairs)

    costs = [float(item.paired_cost_per_unit) for item in pairs]
    gaps = [float(item.first_leg_gap_seconds) for item in pairs if item.first_leg_gap_seconds is not None]

    return PairedInventorySummary(
        market_count=len(records),
        valid_two_leg_market_count=len(pairs),
        both_outcome_market_share=_share(len(pairs), len(records)),
        buy_rows=buy_rows,
        buy_notional=buy_notional,
        matched_size=matched_size,
        matched_pair_cost=matched_cost,
        residual_notional=residual_notional,
        residual_size_share=_share(residual_size, total_leg_size),
        paired_cost_mean=(sum(costs) / len(costs)) if costs else None,
        paired_cost_median=median(costs) if costs else None,
        paired_cost_p10=_quantile(costs, 0.10),
        paired_cost_p25=_quantile(costs, 0.25),
        paired_cost_p75=_quantile(costs, 0.75),
        paired_cost_p90=_quantile(costs, 0.90),
        paired_cost_lt_1_share=_predicate_share(costs, lambda x: x < 1.0 and not isclose(x, 1.0, abs_tol=1e-12)),
        paired_cost_le_099_share=_predicate_share(costs, lambda x: _leq(x, 0.99)),
        paired_cost_le_098_share=_predicate_share(costs, lambda x: _leq(x, 0.98)),
        paired_cost_le_095_share=_predicate_share(costs, lambda x: _leq(x, 0.95)),
        first_leg_gap_median_seconds=median(gaps) if gaps else None,
        first_leg_gap_le_1s_share=_predicate_share(gaps, lambda x: _leq(x, 1.0)),
        first_leg_gap_le_5s_share=_predicate_share(gaps, lambda x: _leq(x, 5.0)),
        first_leg_gap_le_15s_share=_predicate_share(gaps, lambda x: _leq(x, 15.0)),
        first_leg_gap_le_30s_share=_predicate_share(gaps, lambda x: _leq(x, 30.0)),
        first_leg_gap_le_60s_share=_predicate_share(gaps, lambda x: _leq(x, 60.0)),
    )


def _decompose_market(condition_id: str, rows: list[WalletActivity]) -> MarketInventoryDecomposition:
    first = min(rows, key=lambda item: item.source_event_time)
    family = classify_market(title=first.title, slug=first.slug, event_slug=first.event_slug).family
    by_asset: dict[str, list[WalletActivity]] = {}
    for row in rows:
        assert row.asset is not None
        by_asset.setdefault(row.asset, []).append(row)

    legs = tuple(sorted((_build_leg(asset, leg_rows) for asset, leg_rows in by_asset.items()), key=lambda leg: leg.asset))
    valid = len(legs) == 2 and all(leg.buy_size > 0 and leg.vwap is not None for leg in legs)
    if not valid:
        return MarketInventoryDecomposition(
            condition_id=condition_id,
            market_family=family,
            title=first.title,
            slug=first.slug,
            event_slug=first.event_slug,
            legs=legs,
            valid_binary_pair=False,
            matched_size=None,
            paired_cost_per_unit=None,
            matched_pair_cost=None,
            gross_pair_value_at_resolution=None,
            gross_pair_edge=None,
            residual_sizes=tuple(),
            directional_residual_notional=None,
            first_leg_gap_seconds=None,
        )

    left, right = legs
    matched = min(left.buy_size, right.buy_size)
    pair_cost = float(left.vwap) + float(right.vwap)
    residuals = (left.buy_size - matched, right.buy_size - matched)
    residual_notional = residuals[0] * float(left.vwap) + residuals[1] * float(right.vwap)
    first_gap = abs((left.first_source_time - right.first_source_time).total_seconds())
    matched_cost = matched * pair_cost
    return MarketInventoryDecomposition(
        condition_id=condition_id,
        market_family=family,
        title=first.title,
        slug=first.slug,
        event_slug=first.event_slug,
        legs=legs,
        valid_binary_pair=True,
        matched_size=matched,
        paired_cost_per_unit=pair_cost,
        matched_pair_cost=matched_cost,
        gross_pair_value_at_resolution=matched,
        gross_pair_edge=matched - matched_cost,
        residual_sizes=residuals,
        directional_residual_notional=residual_notional,
        first_leg_gap_seconds=first_gap,
    )


def _build_leg(asset: str, rows: list[WalletActivity]) -> LegInventory:
    ordered = sorted(rows, key=lambda item: (item.source_event_time, item.transaction_hash or ""))
    size = sum(item.size for item in ordered)
    notional = sum(item.usdc_size for item in ordered)
    return LegInventory(
        asset=asset,
        outcome=ordered[0].outcome,
        buy_rows=len(ordered),
        buy_size=size,
        buy_notional=notional,
        vwap=(notional / size) if size > 0 else None,
        first_source_time=ordered[0].source_event_time,
        last_source_time=ordered[-1].source_event_time,
    )


def _share(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def _predicate_share(values: list[float], predicate) -> float | None:
    return (sum(1 for value in values if predicate(value)) / len(values)) if values else None


def _leq(value: float, threshold: float) -> bool:
    return value < threshold or isclose(value, threshold, abs_tol=1e-12)


def _quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lo = int(position)
    hi = min(lo + 1, len(ordered) - 1)
    fraction = position - lo
    return ordered[lo] * (1.0 - fraction) + ordered[hi] * fraction
