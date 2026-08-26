"""Condition-level reconciliation of paired inventory accounting with closed-position PnL.

The residual produced here is intentionally neutral. It is not directional PnL, rewards,
rebates, fees, or copyable edge unless a later contract proves that attribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from statistics import mean, median
from typing import Iterable

from .classify import classify_market
from .models import ClosedPosition, MarketFamily
from .paired_inventory import MarketInventoryDecomposition


_TARGET_FAMILIES = {
    MarketFamily.CRYPTO_UPDOWN_5M,
    MarketFamily.CRYPTO_UPDOWN_15M,
}
_SIGN_EPSILON = 1e-9


@dataclass(frozen=True, slots=True)
class ConditionPnlReconciliation:
    condition_id: str
    market_family: MarketFamily
    closed_row_count: int
    closed_realized_pnl: float
    valid_pair: bool
    paired_cost_per_unit: float | None
    matched_pair_edge: float | None
    reconciliation_residual: float | None


@dataclass(frozen=True, slots=True)
class ReconciliationSlice:
    condition_count: int
    closed_realized_pnl_total: float
    closed_realized_pnl_mean: float | None
    closed_realized_pnl_median: float | None
    matched_pair_edge_total: float
    reconciliation_residual_total: float


@dataclass(frozen=True, slots=True)
class PnlReconciliationSummary:
    activity_market_count: int
    closed_market_count: int
    joined_market_count: int
    activity_only_market_count: int
    closed_only_market_count: int
    joined_activity_share: float | None
    joined_closed_share: float | None
    joined_valid_pair_count: int
    all_valid_pairs: ReconciliationSlice
    pair_cost_lt_1: ReconciliationSlice
    pair_cost_ge_1: ReconciliationSlice
    pearson_matched_edge_vs_closed_pnl: float | None
    sign_agreement_share: float | None


def reconcile_condition_pnl(
    activity_markets: Iterable[MarketInventoryDecomposition],
    closed_positions: Iterable[ClosedPosition],
    *,
    target_families_only: bool = True,
) -> tuple[ConditionPnlReconciliation, ...]:
    activity = {item.condition_id: item for item in activity_markets}
    closed_grouped: dict[str, list[ClosedPosition]] = {}
    for row in closed_positions:
        if not row.condition_id:
            continue
        family = classify_market(title=row.title, slug=row.slug, event_slug=row.event_slug).family
        if target_families_only and family not in _TARGET_FAMILIES:
            continue
        closed_grouped.setdefault(row.condition_id, []).append(row)

    joined: list[ConditionPnlReconciliation] = []
    for condition_id in sorted(set(activity) & set(closed_grouped)):
        market = activity[condition_id]
        rows = closed_grouped[condition_id]
        closed_pnl = sum(row.realized_pnl for row in rows)
        valid = bool(market.valid_binary_pair and market.gross_pair_edge is not None)
        pair_edge = float(market.gross_pair_edge) if valid else None
        joined.append(
            ConditionPnlReconciliation(
                condition_id=condition_id,
                market_family=market.market_family,
                closed_row_count=len(rows),
                closed_realized_pnl=closed_pnl,
                valid_pair=valid,
                paired_cost_per_unit=market.paired_cost_per_unit if valid else None,
                matched_pair_edge=pair_edge,
                reconciliation_residual=(closed_pnl - pair_edge) if pair_edge is not None else None,
            )
        )
    return tuple(joined)


def summarize_reconciliation(
    activity_markets: Iterable[MarketInventoryDecomposition],
    closed_positions: Iterable[ClosedPosition],
) -> PnlReconciliationSummary:
    activity_records = tuple(activity_markets)
    closed_records = tuple(closed_positions)
    activity_ids = {item.condition_id for item in activity_records}

    target_closed_ids = {
        row.condition_id
        for row in closed_records
        if row.condition_id
        and classify_market(title=row.title, slug=row.slug, event_slug=row.event_slug).family in _TARGET_FAMILIES
    }
    joined = reconcile_condition_pnl(activity_records, closed_records)
    valid = tuple(item for item in joined if item.valid_pair and item.matched_pair_edge is not None)
    lt1 = tuple(
        item for item in valid if item.paired_cost_per_unit is not None and item.paired_cost_per_unit < 1.0
    )
    ge1 = tuple(
        item for item in valid if item.paired_cost_per_unit is not None and item.paired_cost_per_unit >= 1.0
    )

    xs = [float(item.matched_pair_edge) for item in valid]
    ys = [item.closed_realized_pnl for item in valid]
    correlation = _pearson(xs, ys) if len(valid) >= 20 else None
    agreements = [
        _sign(float(item.matched_pair_edge)) == _sign(item.closed_realized_pnl)
        for item in valid
    ]

    return PnlReconciliationSummary(
        activity_market_count=len(activity_ids),
        closed_market_count=len(target_closed_ids),
        joined_market_count=len(joined),
        activity_only_market_count=len(activity_ids - target_closed_ids),
        closed_only_market_count=len(target_closed_ids - activity_ids),
        joined_activity_share=(len(joined) / len(activity_ids)) if activity_ids else None,
        joined_closed_share=(len(joined) / len(target_closed_ids)) if target_closed_ids else None,
        joined_valid_pair_count=len(valid),
        all_valid_pairs=_slice(valid),
        pair_cost_lt_1=_slice(lt1),
        pair_cost_ge_1=_slice(ge1),
        pearson_matched_edge_vs_closed_pnl=correlation,
        sign_agreement_share=(sum(agreements) / len(agreements)) if agreements else None,
    )


def summarize_by_family(
    reconciled: Iterable[ConditionPnlReconciliation],
) -> dict[MarketFamily, ReconciliationSlice]:
    grouped: dict[MarketFamily, list[ConditionPnlReconciliation]] = {}
    for item in reconciled:
        if not item.valid_pair:
            continue
        grouped.setdefault(item.market_family, []).append(item)
    return {family: _slice(tuple(rows)) for family, rows in sorted(grouped.items(), key=lambda x: x[0].value)}


def _slice(rows: tuple[ConditionPnlReconciliation, ...]) -> ReconciliationSlice:
    closed = [item.closed_realized_pnl for item in rows]
    pair_edges = [float(item.matched_pair_edge) for item in rows if item.matched_pair_edge is not None]
    residuals = [float(item.reconciliation_residual) for item in rows if item.reconciliation_residual is not None]
    return ReconciliationSlice(
        condition_count=len(rows),
        closed_realized_pnl_total=sum(closed),
        closed_realized_pnl_mean=mean(closed) if closed else None,
        closed_realized_pnl_median=median(closed) if closed else None,
        matched_pair_edge_total=sum(pair_edges),
        reconciliation_residual_total=sum(residuals),
    )


def _sign(value: float) -> int:
    if abs(value) < _SIGN_EPSILON:
        return 0
    return 1 if value > 0 else -1


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    mx = mean(xs)
    my = mean(ys)
    dx = [x - mx for x in xs]
    dy = [y - my for y in ys]
    denom = sqrt(sum(x * x for x in dx) * sum(y * y for y in dy))
    if denom == 0:
        return None
    return sum(x * y for x, y in zip(dx, dy)) / denom
