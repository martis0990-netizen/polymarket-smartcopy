from datetime import datetime, timedelta, timezone

import pytest

from smartcopy.models import ClosedPosition, ObservationMode, WalletActivity
from smartcopy.unmatched_outcome_alignment import (
    analyze_unmatched_outcome_alignment,
    summarize_unmatched_outcome_alignment,
)

START = 1787616000
T0 = datetime.fromtimestamp(START, tz=timezone.utc)


def _buy(second: int, *, asset: str, outcome: str, size: float, usdc: float, condition: str = "c", mode=ObservationMode.BACKFILL):
    source = T0 + timedelta(seconds=second)
    return WalletActivity(
        proxy_wallet="0xabc", source_event_time=source, first_observed_time=T0 + timedelta(days=1),
        condition_id=condition, activity_type="TRADE", side="BUY", size=size, usdc_size=usdc,
        price=usdc / size, asset=asset, transaction_hash=f"tx-{condition}-{asset}-{second}",
        title="Bitcoin Up or Down 5m", slug=f"btc-updown-5m-{START}", event_slug=f"btc-updown-5m-{START}",
        outcome=outcome, observation_mode=mode,
    )


def _closed(*, asset: str, outcome: str, total_bought: float, pnl: float, condition: str = "c"):
    return ClosedPosition(
        proxy_wallet="0xabc", condition_id=condition, asset=asset, avg_price=0.5,
        total_bought=total_bought, realized_pnl=pnl, closed_time=T0 + timedelta(hours=1),
        title="Bitcoin Up or Down 5m", slug=f"btc-updown-5m-{START}", event_slug=f"btc-updown-5m-{START}",
        outcome=outcome, end_date=None,
    )


def test_final_unmatched_asset_uses_exact_closed_unit_pnl() -> None:
    activities = [
        _buy(10, asset="up", outcome="Up", size=10, usdc=4),
        _buy(20, asset="down", outcome="Down", size=6, usdc=3.6),
    ]
    closed = [
        _closed(asset="up", outcome="Up", total_bought=10, pnl=5),
        _closed(asset="down", outcome="Down", total_bought=6, pnl=-3),
    ]
    row = analyze_unmatched_outcome_alignment(activities, closed)[0]
    assert row.unmatched_asset == "up"
    assert row.unmatched_outcome == "Up"
    assert row.unmatched_size == pytest.approx(4)
    assert row.unit_closed_realized_pnl == pytest.approx(0.5)
    assert row.unmatched_inventory_realized_pnl == pytest.approx(2)
    assert row.sign == "positive"


def test_last_residual_increasing_buy_uses_frozen_market_quartile() -> None:
    activities = [
        _buy(10, asset="up", outcome="Up", size=10, usdc=4),
        _buy(100, asset="down", outcome="Down", size=10, usdc=6),
        _buy(250, asset="up", outcome="Up", size=2, usdc=1.2),
    ]
    closed = [
        _closed(asset="up", outcome="Up", total_bought=12, pnl=2),
        _closed(asset="down", outcome="Down", total_bought=10, pnl=-1),
    ]
    row = analyze_unmatched_outcome_alignment(activities, closed)[0]
    assert row.last_residual_increasing_bucket == "Q4"


def test_size_mismatch_is_excluded_by_previously_frozen_consistency_gate() -> None:
    activities = [
        _buy(10, asset="up", outcome="Up", size=10, usdc=4),
        _buy(20, asset="down", outcome="Down", size=6, usdc=3.6),
    ]
    closed = [
        _closed(asset="up", outcome="Up", total_bought=20, pnl=5),
        _closed(asset="down", outcome="Down", total_bought=6, pnl=-3),
    ]
    assert analyze_unmatched_outcome_alignment(activities, closed) == ()


def test_equal_final_inventory_has_no_unmatched_alignment_row() -> None:
    activities = [
        _buy(10, asset="up", outcome="Up", size=10, usdc=4),
        _buy(20, asset="down", outcome="Down", size=10, usdc=6),
    ]
    closed = [
        _closed(asset="up", outcome="Up", total_bought=10, pnl=5),
        _closed(asset="down", outcome="Down", total_bought=10, pnl=-5),
    ]
    assert analyze_unmatched_outcome_alignment(activities, closed) == ()


def test_backfill_boundary_is_enforced() -> None:
    with pytest.raises(ValueError, match="BACKFILL"):
        analyze_unmatched_outcome_alignment([
            _buy(10, asset="up", outcome="Up", size=10, usdc=4, mode=ObservationMode.LIVE_OBSERVED)
        ], [])


def test_summary_keeps_frozen_pair_cost_partition_and_size_weighted_positive_share() -> None:
    activities = [
        _buy(10, asset="up", outcome="Up", size=10, usdc=4, condition="a"),
        _buy(20, asset="down", outcome="Down", size=6, usdc=3, condition="a"),
        _buy(10, asset="up", outcome="Up", size=8, usdc=5.6, condition="b"),
        _buy(20, asset="down", outcome="Down", size=4, usdc=2, condition="b"),
    ]
    closed = [
        _closed(asset="up", outcome="Up", total_bought=10, pnl=5, condition="a"),
        _closed(asset="down", outcome="Down", total_bought=6, pnl=-2, condition="a"),
        _closed(asset="up", outcome="Up", total_bought=8, pnl=-4, condition="b"),
        _closed(asset="down", outcome="Down", total_bought=4, pnl=1, condition="b"),
    ]
    rows = analyze_unmatched_outcome_alignment(activities, closed)
    summary = summarize_unmatched_outcome_alignment(rows)
    assert summary.all_markets.market_count == 2
    assert summary.pair_cost_lt_1.market_count == 1
    assert summary.pair_cost_ge_1.market_count == 1
    assert summary.all_markets.positive_count == 1
    assert summary.all_markets.negative_count == 1
    assert summary.all_markets.size_weighted_positive_share == pytest.approx(0.5)
