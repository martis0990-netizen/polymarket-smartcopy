from datetime import datetime, timezone

import pytest

from smartcopy.inventory_pnl_allocation import allocate_inventory_pnl, summarize_inventory_pnl_allocations
from smartcopy.models import ClosedPosition, MarketFamily
from smartcopy.paired_inventory import LegInventory, MarketInventoryDecomposition


T0 = datetime(2026, 8, 25, tzinfo=timezone.utc)


def _leg(asset: str, size: float) -> LegInventory:
    return LegInventory(
        asset=asset,
        outcome=asset,
        buy_rows=1,
        buy_size=size,
        buy_notional=size * 0.5,
        vwap=0.5,
        first_source_time=T0,
        last_source_time=T0,
    )


def _market(condition: str, a: float, b: float, pair_cost: float = 0.9) -> MarketInventoryDecomposition:
    matched = min(a, b)
    return MarketInventoryDecomposition(
        condition_id=condition,
        market_family=MarketFamily.CRYPTO_UPDOWN_5M,
        title="Bitcoin Up or Down 5m",
        slug=f"btc-updown-5m-{condition}",
        event_slug=f"btc-updown-5m-{condition}",
        legs=(_leg("up", a), _leg("down", b)),
        valid_binary_pair=True,
        matched_size=matched,
        paired_cost_per_unit=pair_cost,
        matched_pair_cost=matched * pair_cost,
        gross_pair_value_at_resolution=matched,
        gross_pair_edge=matched * (1 - pair_cost),
        residual_sizes=(a - matched, b - matched),
        directional_residual_notional=0.0,
        first_leg_gap_seconds=1,
    )


def _closed(condition: str, asset: str, total_bought: float, pnl: float) -> ClosedPosition:
    return ClosedPosition(
        proxy_wallet="0xabc",
        condition_id=condition,
        asset=asset,
        avg_price=0.5,
        total_bought=total_bought,
        realized_pnl=pnl,
        closed_time=T0,
        title="Bitcoin Up or Down 5m",
        slug=f"btc-updown-5m-{condition}",
        event_slug=f"btc-updown-5m-{condition}",
        outcome=asset,
        end_date=None,
    )


def test_allocation_splits_matched_and_unmatched_by_asset_unit_pnl() -> None:
    allocation = allocate_inventory_pnl(
        [_market("a", 10, 6)],
        [_closed("a", "up", 10, 5), _closed("a", "down", 6, -1.2)],
    )[0]
    assert allocation.eligible is True
    # unit PnL up=.5, down=-.2; matched 6 => +1.8; residual 4 up => +2
    assert allocation.matched_inventory_realized_pnl == pytest.approx(1.8)
    assert allocation.unmatched_inventory_realized_pnl == pytest.approx(2.0)
    assert allocation.allocated_realized_pnl == pytest.approx(3.8)
    assert allocation.closed_realized_pnl == pytest.approx(3.8)
    assert allocation.allocation_error == pytest.approx(0.0)


def test_duplicate_closed_rows_are_aggregated_by_exact_asset() -> None:
    allocation = allocate_inventory_pnl(
        [_market("a", 10, 10)],
        [
            _closed("a", "up", 4, 0.4),
            _closed("a", "up", 6, 0.6),
            _closed("a", "down", 10, 2.0),
        ],
    )[0]
    assert allocation.eligible is True
    assert allocation.closed_realized_pnl == pytest.approx(3.0)
    assert allocation.matched_inventory_realized_pnl == pytest.approx(3.0)


def test_missing_closed_asset_fails_closed() -> None:
    allocation = allocate_inventory_pnl([_market("a", 10, 10)], [_closed("a", "up", 10, 1)])[0]
    assert allocation.eligible is False
    assert allocation.reason == "missing_closed_asset"


def test_size_mismatch_above_frozen_tolerance_is_ineligible() -> None:
    allocation = allocate_inventory_pnl(
        [_market("a", 10, 10)],
        [_closed("a", "up", 10.01, 1), _closed("a", "down", 10, 1)],
    )[0]
    assert allocation.eligible is False
    assert allocation.reason == "size_mismatch"


def test_small_size_mismatch_is_reported_as_allocation_error_not_rescaled() -> None:
    allocation = allocate_inventory_pnl(
        [_market("a", 10, 10)],
        [_closed("a", "up", 10.0005, 1), _closed("a", "down", 10, 1)],
    )[0]
    assert allocation.eligible is True
    assert abs(allocation.allocation_error or 0) > 0


def test_summary_uses_only_frozen_lt1_vs_ge1_partition() -> None:
    allocations = allocate_inventory_pnl(
        [_market("a", 10, 10, pair_cost=0.95), _market("b", 10, 10, pair_cost=1.05)],
        [
            _closed("a", "up", 10, 1), _closed("a", "down", 10, 2),
            _closed("b", "up", 10, -1), _closed("b", "down", 10, -2),
        ],
    )
    summary = summarize_inventory_pnl_allocations(allocations)
    assert summary.eligible_conditions == 2
    assert summary.pair_cost_lt_1.condition_count == 1
    assert summary.pair_cost_ge_1.condition_count == 1
    assert summary.pair_cost_lt_1.closed_realized_pnl == pytest.approx(3)
    assert summary.pair_cost_ge_1.closed_realized_pnl == pytest.approx(-3)
