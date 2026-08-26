"""Matched-vs-unmatched closed-position PnL allocation under a frozen accounting contract."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable

from .models import ClosedPosition
from .paired_inventory import MarketInventoryDecomposition


_SIZE_TOLERANCE = 1e-4


@dataclass(frozen=True, slots=True)
class InventoryPnlAllocation:
    condition_id: str
    eligible: bool
    reason: str | None
    paired_cost_per_unit: float | None
    closed_realized_pnl: float | None
    matched_inventory_realized_pnl: float | None
    unmatched_inventory_realized_pnl: float | None
    allocated_realized_pnl: float | None
    allocation_error: float | None


@dataclass(frozen=True, slots=True)
class AllocationSlice:
    condition_count: int
    closed_realized_pnl: float
    matched_inventory_realized_pnl: float
    unmatched_inventory_realized_pnl: float
    allocation_error: float
    matched_median: float | None
    unmatched_median: float | None
    matched_positive: int
    matched_negative: int
    matched_zero: int
    unmatched_positive: int
    unmatched_negative: int
    unmatched_zero: int


@dataclass(frozen=True, slots=True)
class InventoryPnlAllocationSummary:
    joined_valid_pair_conditions: int
    eligible_conditions: int
    ineligible_conditions: int
    ineligible_missing_asset: int
    ineligible_size_mismatch: int
    all_eligible: AllocationSlice
    pair_cost_lt_1: AllocationSlice
    pair_cost_ge_1: AllocationSlice


def allocate_inventory_pnl(
    markets: Iterable[MarketInventoryDecomposition],
    closed_positions: Iterable[ClosedPosition],
) -> tuple[InventoryPnlAllocation, ...]:
    closed: dict[tuple[str, str], list[ClosedPosition]] = {}
    for row in closed_positions:
        if row.condition_id and row.asset:
            closed.setdefault((row.condition_id, row.asset), []).append(row)

    results: list[InventoryPnlAllocation] = []
    for market in markets:
        if not market.valid_binary_pair or len(market.legs) != 2:
            continue
        leg_data = []
        failure: str | None = None
        for leg in market.legs:
            rows = closed.get((market.condition_id, leg.asset))
            if not rows:
                failure = "missing_closed_asset"
                break
            closed_size = sum(row.total_bought for row in rows)
            if leg.buy_size <= 0 or closed_size <= 0:
                failure = "invalid_size"
                break
            relative_error = abs(closed_size - leg.buy_size) / max(closed_size, leg.buy_size)
            if relative_error > _SIZE_TOLERANCE:
                failure = "size_mismatch"
                break
            closed_pnl = sum(row.realized_pnl for row in rows)
            leg_data.append((leg, closed_size, closed_pnl / closed_size, closed_pnl))

        if failure is not None:
            results.append(InventoryPnlAllocation(
                condition_id=market.condition_id,
                eligible=False,
                reason=failure,
                paired_cost_per_unit=market.paired_cost_per_unit,
                closed_realized_pnl=None,
                matched_inventory_realized_pnl=None,
                unmatched_inventory_realized_pnl=None,
                allocated_realized_pnl=None,
                allocation_error=None,
            ))
            continue

        left, right = leg_data
        matched = min(left[0].buy_size, right[0].buy_size)
        unmatched_left = left[0].buy_size - matched
        unmatched_right = right[0].buy_size - matched
        matched_pnl = matched * (left[2] + right[2])
        unmatched_pnl = unmatched_left * left[2] + unmatched_right * right[2]
        allocated = matched_pnl + unmatched_pnl
        closed_pnl = left[3] + right[3]
        results.append(InventoryPnlAllocation(
            condition_id=market.condition_id,
            eligible=True,
            reason=None,
            paired_cost_per_unit=market.paired_cost_per_unit,
            closed_realized_pnl=closed_pnl,
            matched_inventory_realized_pnl=matched_pnl,
            unmatched_inventory_realized_pnl=unmatched_pnl,
            allocated_realized_pnl=allocated,
            allocation_error=closed_pnl - allocated,
        ))
    return tuple(sorted(results, key=lambda item: item.condition_id))


def summarize_inventory_pnl_allocations(
    allocations: Iterable[InventoryPnlAllocation],
) -> InventoryPnlAllocationSummary:
    records = tuple(allocations)
    eligible = tuple(item for item in records if item.eligible)
    lt1 = tuple(item for item in eligible if item.paired_cost_per_unit is not None and item.paired_cost_per_unit < 1.0)
    ge1 = tuple(item for item in eligible if item.paired_cost_per_unit is not None and item.paired_cost_per_unit >= 1.0)
    return InventoryPnlAllocationSummary(
        joined_valid_pair_conditions=len(records),
        eligible_conditions=len(eligible),
        ineligible_conditions=len(records) - len(eligible),
        ineligible_missing_asset=sum(item.reason == "missing_closed_asset" for item in records),
        ineligible_size_mismatch=sum(item.reason == "size_mismatch" for item in records),
        all_eligible=_slice(eligible),
        pair_cost_lt_1=_slice(lt1),
        pair_cost_ge_1=_slice(ge1),
    )


def _slice(rows: tuple[InventoryPnlAllocation, ...]) -> AllocationSlice:
    closed = [float(item.closed_realized_pnl) for item in rows if item.closed_realized_pnl is not None]
    matched = [float(item.matched_inventory_realized_pnl) for item in rows if item.matched_inventory_realized_pnl is not None]
    unmatched = [float(item.unmatched_inventory_realized_pnl) for item in rows if item.unmatched_inventory_realized_pnl is not None]
    errors = [float(item.allocation_error) for item in rows if item.allocation_error is not None]
    return AllocationSlice(
        condition_count=len(rows),
        closed_realized_pnl=sum(closed),
        matched_inventory_realized_pnl=sum(matched),
        unmatched_inventory_realized_pnl=sum(unmatched),
        allocation_error=sum(errors),
        matched_median=median(matched) if matched else None,
        unmatched_median=median(unmatched) if unmatched else None,
        matched_positive=sum(x > 1e-9 for x in matched),
        matched_negative=sum(x < -1e-9 for x in matched),
        matched_zero=sum(abs(x) <= 1e-9 for x in matched),
        unmatched_positive=sum(x > 1e-9 for x in unmatched),
        unmatched_negative=sum(x < -1e-9 for x in unmatched),
        unmatched_zero=sum(abs(x) <= 1e-9 for x in unmatched),
    )
