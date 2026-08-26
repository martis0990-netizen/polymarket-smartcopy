from datetime import datetime, timedelta, timezone

import pytest

from smartcopy.models import ObservationMode, WalletActivity
from smartcopy.residual_buildup import decompose_residual_buildup


START = 1787616000
T0 = datetime.fromtimestamp(START, tz=timezone.utc)


def _buy(second: int, *, asset: str, outcome: str, size: float, mode=ObservationMode.BACKFILL):
    source = T0 + timedelta(seconds=second)
    return WalletActivity(
        proxy_wallet="0xabc",
        source_event_time=source,
        first_observed_time=T0 + timedelta(days=1),
        condition_id="condition",
        activity_type="TRADE",
        side="BUY",
        size=size,
        usdc_size=size * 0.5,
        price=0.5,
        asset=asset,
        transaction_hash=f"tx-{asset}-{second}",
        title="Bitcoin Up or Down 5m",
        slug=f"btc-updown-5m-{START}",
        event_slug=f"btc-updown-5m-{START}",
        outcome=outcome,
        observation_mode=mode,
    )


def test_state_machine_partitions_fill_into_balancing_and_residual_quantity() -> None:
    item = decompose_residual_buildup([
        _buy(0, asset="up", outcome="Up", size=10),
        _buy(10, asset="down", outcome="Down", size=6),
        _buy(20, asset="down", outcome="Down", size=8),
    ])[0]
    # first up 10 residual; down 6 balances; next down 4 balances then 4 residual
    assert item.total_buy_size == pytest.approx(24)
    assert item.pair_balancing_quantity == pytest.approx(10)
    assert item.residual_increasing_quantity == pytest.approx(14)
    assert item.final_matched_size == pytest.approx(10)
    assert item.final_residual_size == pytest.approx(4)
    assert item.imbalance_sign_flips == 1
    assert item.dominant_outcome == "Down"


def test_market_clock_uses_frozen_quartiles_and_reports_outside() -> None:
    item = decompose_residual_buildup([
        _buy(10, asset="up", outcome="Up", size=1),
        _buy(80, asset="down", outcome="Down", size=0.5),
        _buy(160, asset="down", outcome="Down", size=1),
        _buy(310, asset="up", outcome="Up", size=1),
    ])[0]
    assert item.residual_quantity_q1 > 0
    assert item.residual_quantity_q3 > 0
    assert item.residual_quantity_outside > 0


def test_backfill_only_boundary_is_enforced() -> None:
    with pytest.raises(ValueError, match="BACKFILL"):
        decompose_residual_buildup([
            _buy(0, asset="up", outcome="Up", size=1, mode=ObservationMode.LIVE_OBSERVED)
        ])


def test_one_leg_market_is_not_coerced_into_dynamic_pair() -> None:
    assert decompose_residual_buildup([_buy(0, asset="up", outcome="Up", size=1)]) == ()


def test_equal_final_balances_have_no_dominant_outcome() -> None:
    item = decompose_residual_buildup([
        _buy(0, asset="up", outcome="Up", size=10),
        _buy(5, asset="down", outcome="Down", size=10),
    ])[0]
    assert item.final_residual_size == pytest.approx(0)
    assert item.dominant_outcome is None
