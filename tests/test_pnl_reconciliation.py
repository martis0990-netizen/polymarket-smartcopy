from datetime import datetime, timezone

import pytest

from smartcopy.models import ClosedPosition, MarketFamily
from smartcopy.paired_inventory import LegInventory, MarketInventoryDecomposition
from smartcopy.pnl_reconciliation import reconcile_condition_pnl, summarize_reconciliation


T0 = datetime(2026, 8, 25, tzinfo=timezone.utc)


def _market(condition: str, *, pair_cost: float = 0.9, edge: float = 1.0, valid: bool = True):
    leg = LegInventory(
        asset=f"asset-{condition}",
        outcome="Up",
        buy_rows=1,
        buy_size=10,
        buy_notional=4,
        vwap=0.4,
        first_source_time=T0,
        last_source_time=T0,
    )
    return MarketInventoryDecomposition(
        condition_id=condition,
        market_family=MarketFamily.CRYPTO_UPDOWN_5M,
        title="Bitcoin Up or Down 5m",
        slug=f"btc-updown-5m-{condition}",
        event_slug=f"btc-updown-5m-{condition}",
        legs=(leg, leg) if valid else (leg,),
        valid_binary_pair=valid,
        matched_size=10 if valid else None,
        paired_cost_per_unit=pair_cost if valid else None,
        matched_pair_cost=10 * pair_cost if valid else None,
        gross_pair_value_at_resolution=10 if valid else None,
        gross_pair_edge=edge if valid else None,
        residual_sizes=(0, 0) if valid else (),
        directional_residual_notional=0 if valid else None,
        first_leg_gap_seconds=1 if valid else None,
    )


def _closed(condition: str, pnl: float, *, slug: str | None = None):
    slug = slug or f"btc-updown-5m-{condition}"
    return ClosedPosition(
        proxy_wallet="0xabc",
        condition_id=condition,
        asset=f"asset-{condition}",
        avg_price=0.4,
        total_bought=10,
        realized_pnl=pnl,
        closed_time=T0,
        title="Bitcoin Up or Down 5m",
        slug=slug,
        event_slug=slug,
        outcome="Up",
        end_date=None,
    )


def test_reconciliation_joins_exact_condition_and_sums_closed_rows() -> None:
    rows = reconcile_condition_pnl(
        [_market("a", pair_cost=0.9, edge=1.0)],
        [_closed("a", 2.0), _closed("a", -0.5), _closed("b", 10.0)],
    )
    assert len(rows) == 1
    assert rows[0].condition_id == "a"
    assert rows[0].closed_row_count == 2
    assert rows[0].closed_realized_pnl == pytest.approx(1.5)
    assert rows[0].matched_pair_edge == pytest.approx(1.0)
    assert rows[0].reconciliation_residual == pytest.approx(0.5)


def test_invalid_pair_is_joined_for_coverage_but_has_no_pair_edge() -> None:
    row = reconcile_condition_pnl([_market("a", valid=False)], [_closed("a", 1.0)])[0]
    assert row.valid_pair is False
    assert row.matched_pair_edge is None
    assert row.reconciliation_residual is None


def test_summary_reports_exact_join_coverage_and_frozen_lt1_split() -> None:
    activity = [
        _market("a", pair_cost=0.90, edge=1.0),
        _market("b", pair_cost=1.10, edge=-1.0),
        _market("activity-only", pair_cost=0.95, edge=0.5),
    ]
    closed = [
        _closed("a", 2.0),
        _closed("b", -3.0),
        _closed("closed-only", 4.0),
    ]
    summary = summarize_reconciliation(activity, closed)
    assert summary.activity_market_count == 3
    assert summary.closed_market_count == 3
    assert summary.joined_market_count == 2
    assert summary.activity_only_market_count == 1
    assert summary.closed_only_market_count == 1
    assert summary.pair_cost_lt_1.condition_count == 1
    assert summary.pair_cost_lt_1.closed_realized_pnl_total == pytest.approx(2.0)
    assert summary.pair_cost_lt_1.matched_pair_edge_total == pytest.approx(1.0)
    assert summary.pair_cost_ge_1.condition_count == 1
    assert summary.pair_cost_ge_1.closed_realized_pnl_total == pytest.approx(-3.0)
    assert summary.pair_cost_ge_1.matched_pair_edge_total == pytest.approx(-1.0)


def test_summary_excludes_non_target_closed_market_from_closed_coverage() -> None:
    politics = _closed("politics", 10.0, slug="presidential-election-2028")
    politics = ClosedPosition(
        proxy_wallet=politics.proxy_wallet,
        condition_id=politics.condition_id,
        asset=politics.asset,
        avg_price=politics.avg_price,
        total_bought=politics.total_bought,
        realized_pnl=politics.realized_pnl,
        closed_time=politics.closed_time,
        title="Who will win the presidential election?",
        slug=politics.slug,
        event_slug=politics.event_slug,
        outcome=politics.outcome,
        end_date=politics.end_date,
    )
    summary = summarize_reconciliation([_market("a")], [_closed("a", 1.0), politics])
    assert summary.closed_market_count == 1
    assert summary.joined_market_count == 1


def test_pearson_requires_at_least_20_joined_valid_pairs() -> None:
    summary = summarize_reconciliation([_market("a")], [_closed("a", 1.0)])
    assert summary.pearson_matched_edge_vs_closed_pnl is None


def test_sign_agreement_uses_zero_epsilon() -> None:
    activity = [_market("a", edge=1.0), _market("b", edge=-1.0)]
    closed = [_closed("a", 2.0), _closed("b", 3.0)]
    summary = summarize_reconciliation(activity, closed)
    assert summary.sign_agreement_share == 0.5
