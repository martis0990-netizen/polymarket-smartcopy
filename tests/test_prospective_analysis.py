from smartcopy.correction_overlay import market_spec
from smartcopy.external_signal import BinanceKline
from smartcopy.prospective_analysis import (
    _momentum_15s,
    build_condition_rows,
    group_receipt_episodes,
    summarize_interim,
)


def test_grouped_receipt_episodes_collapse_partial_price_levels() -> None:
    rows = [
        {
            "condition_id": "condition",
            "outcome": "Up",
            "source_second": 100,
            "schema_corrected_role": "TAKER",
            "source_size": 2,
            "source_notional": 0.8,
        },
        {
            "condition_id": "condition",
            "outcome": "Up",
            "source_second": 100,
            "schema_corrected_role": "TAKER",
            "source_size": 3,
            "source_notional": 1.5,
        },
    ]
    episode = group_receipt_episodes(rows)["condition"][0]
    assert episode["fill_rows"] == 2
    assert episode["source_size"] == 5
    assert episode["source_notional"] == 2.3


def test_momentum_uses_t_minus_one_and_t_minus_sixteen() -> None:
    def bar(second):
        return BinanceKline(
            symbol="BTCUSDT",
            interval="1s",
            open_time_ms=second * 1000,
            close_time_ms=second * 1000 + 999,
            open=float(second),
            high=float(second),
            low=float(second),
            close=float(second),
            volume=1,
            quote_volume=1,
            trade_count=1,
            taker_buy_base=0.5,
            taker_buy_quote=0.5,
        )
    bars = tuple(bar(second) for second in range(80, 100))
    assert _momentum_15s(bars, 100) > 0
    same_second = BinanceKline(
        symbol="BTCUSDT", interval="1s", open_time_ms=100_000,
        close_time_ms=100_999, open=1, high=1, low=1, close=1,
        volume=1, quote_volume=1, trade_count=1,
        taker_buy_base=0.5, taker_buy_quote=0.5,
    )
    assert _momentum_15s(bars + (same_second,), 100) == _momentum_15s(bars, 100)


def test_condition_requires_full_pre_open_capture_and_defers_gate() -> None:
    spec = market_spec(
        condition_id="condition",
        slug="btc-updown-5m-1000",
        title="Bitcoin Up or Down",
    )
    episodes = {
        "condition": (
            {
                "condition_id": "condition",
                "outcome": "Up",
                "source_second": 1010,
                "role": "TAKER",
                "source_notional": 1.0,
            },
        )
    }
    chainlink = {
        "btc/usd": (
            {"source_timestamp_ms": 1_000_000, "value_decimal": 100},
            {"source_timestamp_ms": 1_009_000, "value_decimal": 101},
        )
    }
    bars = []
    for second in range(990, 1010):
        bars.append(
            BinanceKline(
                symbol="BTCUSDT", interval="1s", open_time_ms=second*1000,
                close_time_ms=second*1000+999, open=second, high=second, low=second,
                close=second, volume=1, quote_volume=1, trade_count=1,
                taker_buy_base=0.5, taker_buy_quote=0.5,
            )
        )
    rows = build_condition_rows(
        specs={"condition": spec},
        episodes=episodes,
        chainlink=chainlink,
        binance={"BTCUSDT": tuple(bars)},
        capture_started_ms=939_000,
        capture_ended_ms=1_020_000,
    )
    assert rows[0]["eligible"] is True
    assert rows[0]["barrier_direction"] == "Up"
    summary = summarize_interim(rows)
    assert summary["study_status"] == "COLLECTING"
    assert summary["stopping_rule"]["gate_evaluation_deferred"] is True
