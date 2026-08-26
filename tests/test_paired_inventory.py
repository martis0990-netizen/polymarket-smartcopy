from datetime import datetime, timedelta, timezone

import pytest

from smartcopy.models import ObservationMode, WalletActivity
from smartcopy.paired_inventory import decompose_backfill, summarize_decomposition


T0 = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _buy(
    second: int,
    *,
    asset: str,
    outcome: str,
    size: float,
    price: float,
    condition: str = "condition",
    slug: str = "btc-updown-5m-123",
    mode: ObservationMode = ObservationMode.BACKFILL,
) -> WalletActivity:
    source = T0 + timedelta(seconds=second)
    return WalletActivity(
        proxy_wallet="0xabc",
        source_event_time=source,
        first_observed_time=T0 + timedelta(hours=1),
        condition_id=condition,
        activity_type="TRADE",
        side="BUY",
        size=size,
        usdc_size=size * price,
        price=price,
        asset=asset,
        transaction_hash=f"tx-{condition}-{asset}-{second}",
        title="Bitcoin Up or Down 5m",
        slug=slug,
        event_slug=slug,
        outcome=outcome,
        observation_mode=mode,
    )


def test_decomposition_separates_matched_pair_from_directional_residual() -> None:
    markets = decompose_backfill([
        _buy(0, asset="up", outcome="Up", size=10, price=0.40),
        _buy(5, asset="down", outcome="Down", size=6, price=0.55),
    ])
    assert len(markets) == 1
    item = markets[0]
    assert item.valid_binary_pair is True
    assert item.matched_size == 6
    assert item.paired_cost_per_unit == pytest.approx(0.95)
    assert item.matched_pair_cost == pytest.approx(5.7)
    assert item.gross_pair_value_at_resolution == pytest.approx(6.0)
    assert item.gross_pair_edge == pytest.approx(0.3)
    assert sorted(item.residual_sizes) == [0.0, 4.0]
    assert item.directional_residual_notional == pytest.approx(1.6)
    assert item.first_leg_gap_seconds == 5


def test_leg_vwap_uses_source_notional_and_size() -> None:
    item = decompose_backfill([
        _buy(0, asset="up", outcome="Up", size=5, price=0.40),
        _buy(2, asset="up", outcome="Up", size=15, price=0.60),
        _buy(3, asset="down", outcome="Down", size=20, price=0.45),
    ])[0]
    by_outcome = {leg.outcome: leg for leg in item.legs}
    assert by_outcome["Up"].vwap == pytest.approx(0.55)
    assert by_outcome["Down"].vwap == pytest.approx(0.45)
    assert item.paired_cost_per_unit == pytest.approx(1.0)


def test_single_leg_market_is_reported_but_not_forced_into_pair() -> None:
    item = decompose_backfill([_buy(0, asset="up", outcome="Up", size=10, price=0.4)])[0]
    assert item.valid_binary_pair is False
    assert item.matched_size is None
    assert item.directional_residual_notional is None


def test_three_asset_market_is_not_coerced_into_binary_pair() -> None:
    item = decompose_backfill([
        _buy(0, asset="a", outcome="A", size=1, price=0.2),
        _buy(1, asset="b", outcome="B", size=1, price=0.3),
        _buy(2, asset="c", outcome="C", size=1, price=0.4),
    ])[0]
    assert len(item.legs) == 3
    assert item.valid_binary_pair is False


def test_historical_decomposition_rejects_live_observed_rows() -> None:
    with pytest.raises(ValueError, match="BACKFILL"):
        decompose_backfill([
            _buy(0, asset="up", outcome="Up", size=1, price=0.4, mode=ObservationMode.LIVE_OBSERVED)
        ])


def test_non_buy_rows_do_not_create_inventory() -> None:
    row = _buy(0, asset="up", outcome="Up", size=1, price=0.4)
    sell = WalletActivity(
        proxy_wallet=row.proxy_wallet,
        source_event_time=row.source_event_time,
        first_observed_time=row.first_observed_time,
        condition_id=row.condition_id,
        activity_type=row.activity_type,
        side="SELL",
        size=row.size,
        usdc_size=row.usdc_size,
        price=row.price,
        asset=row.asset,
        transaction_hash=row.transaction_hash,
        title=row.title,
        slug=row.slug,
        event_slug=row.event_slug,
        outcome=row.outcome,
        observation_mode=row.observation_mode,
    )
    assert decompose_backfill([sell]) == ()


def test_summary_uses_frozen_pair_cost_thresholds_and_gap_buckets() -> None:
    markets = decompose_backfill([
        _buy(0, asset="up-a", outcome="Up", size=10, price=0.40, condition="a"),
        _buy(1, asset="down-a", outcome="Down", size=10, price=0.55, condition="a"),
        _buy(0, asset="up-b", outcome="Up", size=10, price=0.50, condition="b"),
        _buy(40, asset="down-b", outcome="Down", size=10, price=0.50, condition="b"),
    ])
    summary = summarize_decomposition(markets)
    assert summary.market_count == 2
    assert summary.valid_two_leg_market_count == 2
    assert summary.both_outcome_market_share == 1.0
    assert summary.paired_cost_lt_1_share == 0.5
    assert summary.paired_cost_le_099_share == 0.5
    assert summary.paired_cost_le_098_share == 0.5
    assert summary.paired_cost_le_095_share == 0.5
    assert summary.first_leg_gap_le_1s_share == 0.5
    assert summary.first_leg_gap_le_30s_share == 0.5
    assert summary.first_leg_gap_le_60s_share == 1.0


def test_target_scope_excludes_unsupported_market_family() -> None:
    unsupported = _buy(
        0,
        asset="up",
        outcome="Up",
        size=1,
        price=0.4,
        slug="will-bitcoin-be-above-100k",
    )
    unsupported = WalletActivity(
        proxy_wallet=unsupported.proxy_wallet,
        source_event_time=unsupported.source_event_time,
        first_observed_time=unsupported.first_observed_time,
        condition_id=unsupported.condition_id,
        activity_type=unsupported.activity_type,
        side=unsupported.side,
        size=unsupported.size,
        usdc_size=unsupported.usdc_size,
        price=unsupported.price,
        asset=unsupported.asset,
        transaction_hash=unsupported.transaction_hash,
        title="Will Bitcoin be above 100k?",
        slug=unsupported.slug,
        event_slug=unsupported.event_slug,
        outcome=unsupported.outcome,
        observation_mode=unsupported.observation_mode,
    )
    assert decompose_backfill([unsupported], target_families_only=True) == ()
