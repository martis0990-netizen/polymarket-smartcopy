from datetime import datetime, timezone
from decimal import Decimal

import pytest

from smartcopy.lifecycle_ledger import LifecycleLedgerError, _aggregate, build_ledgers
from smartcopy.models import ObservationMode, WalletActivity


def _activity(kind, *, outcome=None, side=None, size="1", usdc="0.4"):
    raw = {"size": size, "usdcSize": usdc, "type": kind}
    return WalletActivity(
        proxy_wallet="0xeebde7a0e019a63e6b476eb425505b7b3e6eba30",
        source_event_time=datetime(2026, 8, 27, 14, 40, tzinfo=timezone.utc),
        first_observed_time=datetime(2026, 8, 27, 18, 0, tzinfo=timezone.utc),
        condition_id="0xc",
        activity_type=kind,
        side=side,
        size=float(size),
        usdc_size=float(usdc),
        price=None,
        asset=None,
        transaction_hash=f"0x{kind}{outcome}{side}",
        title=None,
        slug="btc-updown-5m-1",
        event_slug=None,
        outcome=outcome,
        observation_mode=ObservationMode.BACKFILL,
        raw=raw,
    )


TARGETS = {"0xc": {"slug": "btc-updown-5m-1", "winning_outcome": "Up"}}


def test_trade_and_redeem_ledger_reconciles_tokens_and_cash() -> None:
    rows = [
        _activity("TRADE", outcome="Up", side="BUY", size="10", usdc="4"),
        _activity("TRADE", outcome="Up", side="SELL", size="3", usdc="2"),
        _activity("REDEEM", outcome="Up", size="7", usdc="7"),
    ]
    ledgers, conditions, comparisons = build_ledgers(
        rows,
        target_conditions=TARGETS,
        captured_buy_sizes={("0xc", "Up"): Decimal("2")},
    )
    up = next(row for row in ledgers if row["outcome"] == "Up")
    assert up["post_redeem_flow_balance"] == "0"
    assert conditions[0]["public_pre_fee_cash_flow"] == "5"
    assert next(row for row in comparisons if row["outcome"] == "Up")["capture_share"] == "0.2"


def test_split_and_merge_apply_equal_tokens_to_both_outcomes() -> None:
    rows = [
        _activity("SPLIT", size="10", usdc="10"),
        _activity("MERGE", size="4", usdc="4"),
    ]
    ledgers, conditions, _comparisons = build_ledgers(
        rows, target_conditions=TARGETS, captured_buy_sizes={}
    )
    assert {row["post_redeem_flow_balance"] for row in ledgers} == {"6"}
    assert conditions[0]["public_pre_fee_cash_flow"] == "-6"


def test_negative_balance_reports_minimum_unexplained_inflow() -> None:
    ledgers, _conditions, _comparisons = build_ledgers(
        [_activity("REDEEM", outcome="Down", size="12", usdc="0")],
        target_conditions=TARGETS,
        captured_buy_sizes={},
    )
    down = next(row for row in ledgers if row["outcome"] == "Down")
    assert down["post_redeem_flow_balance"] == "-12"
    assert down["minimum_unexplained_inflow"] == "12"


def test_condition_cash_flow_may_be_negative() -> None:
    ledgers, conditions, comparisons = build_ledgers(
        [_activity("TRADE", outcome="Up", side="BUY", size="10", usdc="7")],
        target_conditions=TARGETS,
        captured_buy_sizes={},
    )
    assert conditions[0]["public_pre_fee_cash_flow"] == "-7"
    assert _aggregate([], [], ledgers, conditions, comparisons)["public_cash"][
        "pre_fee_cash_flow_complete_conditions"
    ] == "-7"


def test_trade_requires_supported_outcome_and_side() -> None:
    with pytest.raises(LifecycleLedgerError, match="unsupported outcome"):
        build_ledgers(
            [_activity("TRADE", outcome="Yes", side="BUY")],
            target_conditions=TARGETS,
            captured_buy_sizes={},
        )
    with pytest.raises(LifecycleLedgerError, match="BUY or SELL"):
        build_ledgers(
            [_activity("TRADE", outcome="Up", side=None)],
            target_conditions=TARGETS,
            captured_buy_sizes={},
        )
