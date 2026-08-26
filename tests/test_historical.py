from datetime import datetime, timedelta, timezone

import pytest

from smartcopy.historical import HistoricalEvidenceError, analyze_paired_legs
from smartcopy.models import ObservationMode, WalletActivity


START = datetime(2026, 8, 25, 0, 0, tzinfo=timezone.utc)
END = datetime(2026, 8, 25, 23, 59, 59, tzinfo=timezone.utc)


def _trade(
    second: int,
    *,
    condition: str = "condition",
    outcome: str = "Up",
    side: str = "BUY",
    size: float = 10.0,
    price: float = 0.4,
    title: str = "Bitcoin Up or Down",
    slug: str = "btc-updown-5m-123",
    observed_delay: int = 100,
    mode: ObservationMode = ObservationMode.BACKFILL,
) -> WalletActivity:
    source = START + timedelta(seconds=second)
    return WalletActivity(
        proxy_wallet="0xabc",
        source_event_time=source,
        first_observed_time=source + timedelta(seconds=observed_delay),
        condition_id=condition,
        activity_type="TRADE",
        side=side,
        size=size,
        usdc_size=size * price,
        price=price,
        asset=f"{condition}-{outcome}",
        transaction_hash=f"tx-{condition}-{outcome}-{side}-{second}-{size}",
        title=title,
        slug=slug,
        event_slug=slug,
        outcome=outcome,
        observation_mode=mode,
    )


def test_paired_market_uses_buy_inventory_without_netting_sell() -> None:
    rows = [
        _trade(0, outcome="Up", size=10, price=0.40),
        _trade(2, outcome="Up", size=20, price=0.50),
        _trade(5, outcome="Down", size=20, price=0.45),
        _trade(8, outcome="Down", size=5, price=0.55),
        _trade(10, outcome="Up", side="SELL", size=3, price=0.60),
    ]
    records, summary = analyze_paired_legs(rows, start=START, end=END)

    assert len(records) == 1
    record = records[0]
    assert record.buy_row_count == 4
    assert record.sell_row_count == 1
    assert record.up.total_size == 30
    assert record.down.total_size == 25
    assert record.matched_size == 25
    assert record.excess_up == 5
    assert record.excess_down == 0
    assert record.paired_fraction == pytest.approx(50 / 55)
    assert record.up.vwap_price == pytest.approx((10 * 0.40 + 20 * 0.50) / 30)
    assert record.down.vwap_price == pytest.approx((20 * 0.45 + 5 * 0.55) / 25)
    assert record.pair_vwap_sum == pytest.approx(record.up.vwap_price + record.down.vwap_price)
    assert record.gross_pair_margin_per_unit == pytest.approx(1 - record.pair_vwap_sum)
    assert record.matched_average_cost == pytest.approx(25 * record.pair_vwap_sum)
    assert record.first_leg_gap_seconds == 5
    assert record.first_leg_order == "UP_FIRST"
    assert record.market_activity_span_seconds == 10
    assert summary.buy_row_count == 4
    assert summary.sell_row_count == 1


def test_one_buy_leg_is_included_but_has_no_pair_cost_or_timing() -> None:
    records, summary = analyze_paired_legs([_trade(0, outcome="Down", size=7, price=0.6)], start=START, end=END)
    record = records[0]
    assert record.matched_size == 0
    assert record.excess_down == 7
    assert record.pair_vwap_sum is None
    assert record.first_leg_gap_seconds is None
    assert record.first_leg_order is None
    assert summary.markets_with_one_buy_leg_only == 1
    assert summary.markets_with_both_buy_legs == 0


def test_ambiguous_outcome_is_excluded_not_guessed() -> None:
    records, summary = analyze_paired_legs([_trade(0, outcome="Yes")], start=START, end=END)
    assert records == ()
    assert summary.excluded_ambiguous_market_count == 1
    assert summary.included_market_count == 0


def test_non_target_market_is_ignored() -> None:
    rows = [_trade(0, title="Bitcoin above 100000", slug="bitcoin-above-100000")]
    records, summary = analyze_paired_legs(rows, start=START, end=END)
    assert records == ()
    assert summary.included_market_count == 0
    assert summary.excluded_ambiguous_market_count == 0


def test_backfill_boundary_fails_closed_for_live_observed_rows() -> None:
    with pytest.raises(HistoricalEvidenceError, match="BACKFILL"):
        analyze_paired_legs(
            [_trade(0, mode=ObservationMode.LIVE_OBSERVED)],
            start=START,
            end=END,
        )


def test_source_activity_outside_frozen_interval_fails_closed() -> None:
    row = _trade(0)
    with pytest.raises(HistoricalEvidenceError, match="outside"):
        analyze_paired_legs([row], start=START + timedelta(seconds=1), end=END)


def test_first_observed_time_does_not_change_historical_output() -> None:
    early = [
        _trade(0, outcome="Up", observed_delay=1),
        _trade(2, outcome="Down", observed_delay=1),
    ]
    late = [
        _trade(0, outcome="Up", observed_delay=10_000),
        _trade(2, outcome="Down", observed_delay=20_000),
    ]
    early_records, early_summary = analyze_paired_legs(early, start=START, end=END)
    late_records, late_summary = analyze_paired_legs(late, start=START, end=END)
    assert early_records == late_records
    assert early_summary == late_summary


def test_aggregate_frozen_thresholds_and_gap_quantiles() -> None:
    rows = [
        _trade(0, condition="a", outcome="Up", price=0.40),
        _trade(10, condition="a", outcome="Down", price=0.50),  # sum .90, gap 10
        _trade(20, condition="b", outcome="Down", price=0.50),
        _trade(40, condition="b", outcome="Up", price=0.49),  # sum .99, gap 20
        _trade(50, condition="c", outcome="Up", price=0.60),
        _trade(80, condition="c", outcome="Down", price=0.50),  # sum 1.10, gap 30
        _trade(100, condition="d", outcome="Up", price=0.50),
        _trade(100, condition="d", outcome="Down", price=0.50),  # sum 1.00, gap 0
    ]
    _records, summary = analyze_paired_legs(rows, start=START, end=END)
    assert summary.markets_with_both_buy_legs == 4
    assert summary.pair_vwap_sum_lt_1_count == 2
    assert summary.pair_vwap_sum_lt_1_share == pytest.approx(0.5)
    assert summary.pair_vwap_sum_le_099_count == 2
    assert summary.pair_vwap_sum_le_099_share == pytest.approx(0.5)
    assert summary.median_first_leg_gap_seconds == 15
    assert summary.p25_first_leg_gap_seconds == pytest.approx(7.5)
    assert summary.p75_first_leg_gap_seconds == pytest.approx(22.5)
    assert summary.up_first_count == 2
    assert summary.down_first_count == 1
    assert summary.same_second_count == 1
