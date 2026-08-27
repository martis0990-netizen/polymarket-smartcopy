from datetime import datetime, timedelta, timezone

import pytest

from smartcopy.models import ObservationMode, WalletActivity
from smartcopy.settlement import SETTLEMENT_TOLERANCE, _decompose_market


BASE = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _market(*, up_size=10.0, down_size=8.0, up_price=0.4, down_price=0.5):
    matched = min(up_size, down_size)
    return {
        "condition_id": "condition",
        "symbol": "BTC",
        "market_family": "crypto_updown_5m",
        "up": {
            "total_size": up_size,
            "total_usdc": up_size * up_price,
            "vwap_price": up_price,
            "last_source_event_time": (BASE + timedelta(seconds=4)).isoformat().replace("+00:00", "Z"),
        },
        "down": {
            "total_size": down_size,
            "total_usdc": down_size * down_price,
            "vwap_price": down_price,
            "last_source_event_time": (BASE + timedelta(seconds=5)).isoformat().replace("+00:00", "Z"),
        },
        "matched_size": matched,
        "excess_up": max(up_size - down_size, 0.0),
        "excess_down": max(down_size - up_size, 0.0),
        "matched_average_cost": matched * (up_price + down_price),
    }


def _event(kind: str, second: int, *, usdc: float = 0.0, size: float = 0.0):
    source = BASE + timedelta(seconds=second)
    return WalletActivity(
        proxy_wallet="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30",
        source_event_time=source,
        first_observed_time=source + timedelta(days=1),
        condition_id="condition",
        activity_type=kind,
        side=None,
        size=size,
        usdc_size=usdc,
        price=None,
        asset=None,
        transaction_hash=f"tx-{kind}-{second}",
        title=None,
        slug=None,
        event_slug=None,
        outcome=None,
        observation_mode=ObservationMode.BACKFILL,
        raw={"type": kind},
    )


def test_excess_won_reconciles_matched_and_directional_cashflow() -> None:
    market = _market()
    redeem = _event("REDEEM", 20, usdc=10.0, size=10.0)  # matched 8 + excess 2
    row = _decompose_market(market, same_day=[redeem], grace=[], combined=[redeem])
    assert row.status == "SIMPLE_SETTLEMENT_ELIGIBLE"
    assert row.settlement_state == "EXCESS_WON"
    assert row.buy_outflow == pytest.approx(8.0)
    assert row.gross_settlement_cashflow == pytest.approx(2.0)
    assert row.matched_pair_cashflow == pytest.approx(0.8)
    assert row.excess_directional_cashflow == pytest.approx(1.2)
    assert abs(row.reconciliation_error or 0.0) <= SETTLEMENT_TOLERANCE


def test_excess_lost_reconciles() -> None:
    market = _market()
    redeem = _event("REDEEM", 20, usdc=8.0, size=8.0)
    row = _decompose_market(market, same_day=[redeem], grace=[], combined=[redeem])
    assert row.status == "SIMPLE_SETTLEMENT_ELIGIBLE"
    assert row.settlement_state == "EXCESS_LOST"
    assert row.gross_settlement_cashflow == pytest.approx(0.0)
    assert row.matched_pair_cashflow == pytest.approx(0.8)
    assert row.excess_directional_cashflow == pytest.approx(-0.8)
    assert abs(row.reconciliation_error or 0.0) <= SETTLEMENT_TOLERANCE


def test_intermediate_redeem_payout_is_excluded_not_forced_into_directional() -> None:
    market = _market()
    redeem = _event("REDEEM", 20, usdc=9.0, size=9.0)
    row = _decompose_market(market, same_day=[redeem], grace=[], combined=[redeem])
    assert row.status == "INCOMPLETE_OR_INCONSISTENT_REDEMPTION"
    assert row.excess_directional_cashflow is None


def test_merge_evidence_excludes_market_before_profit_decomposition() -> None:
    market = _market()
    redeem = _event("REDEEM", 20, usdc=10.0)
    merge = _event("MERGE", 15, size=1.0)
    row = _decompose_market(market, same_day=[merge, redeem], grace=[], combined=[merge, redeem])
    assert row.status == "TRANSFORMED_EXCLUDED"
    assert row.gross_settlement_cashflow is None


def test_buy_after_redeem_is_temporal_inconsistency() -> None:
    market = _market()
    redeem = _event("REDEEM", 1, usdc=10.0)
    row = _decompose_market(market, same_day=[redeem], grace=[], combined=[redeem])
    assert row.status == "TEMPORAL_INCONSISTENCY"
    assert row.matched_pair_cashflow is None


def test_no_redeem_remains_unresolved_without_extending_window() -> None:
    row = _decompose_market(_market(), same_day=[], grace=[], combined=[])
    assert row.status == "UNRESOLVED_IN_FROZEN_EVIDENCE"
