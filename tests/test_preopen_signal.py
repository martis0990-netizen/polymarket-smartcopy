from decimal import Decimal

from smartcopy.correction_overlay import market_spec
from smartcopy.external_signal import BinanceKline
from smartcopy.preopen_signal import (
    build_preopen_rows,
    chainlink_momentum_15s,
    collapse_preopen_taker,
    summarize_preopen,
)


def _bar(second: int, close: float | None = None, symbol: str = "BTCUSDT") -> BinanceKline:
    value = float(second if close is None else close)
    return BinanceKline(
        symbol=symbol, interval="1s", open_time_ms=second * 1000,
        close_time_ms=second * 1000 + 999, open=value, high=value, low=value,
        close=value, volume=1, quote_volume=1, trade_count=1,
        taker_buy_base=0.5, taker_buy_quote=0.5,
    )


def test_collapse_preopen_taker_uses_window_and_rejects_opposing_tie() -> None:
    episodes = (
        {"source_second": 939, "outcome": "Down", "role": "TAKER", "source_notional": 1},
        {"source_second": 950, "outcome": "Up", "role": "MAKER", "source_notional": 1},
        {"source_second": 990, "outcome": "Up", "role": "TAKER", "source_notional": 2},
    )
    assert collapse_preopen_taker(episodes, market_start=1000)["source_second"] == 990
    tied = episodes + ({"source_second": 990, "outcome": "Down", "role": "TAKER", "source_notional": 1},)
    assert collapse_preopen_taker(tied, market_start=1000) is None


def test_chainlink_momentum_is_strict_pre_at_both_ends() -> None:
    rows = (
        {"source_timestamp_ms": 984_000, "value_decimal": Decimal("100")},
        {"source_timestamp_ms": 985_000, "value_decimal": Decimal("1000")},
        {"source_timestamp_ms": 999_000, "value_decimal": Decimal("101")},
        {"source_timestamp_ms": 1_000_000, "value_decimal": Decimal("1")},
    )
    assert chainlink_momentum_15s(rows, source_second=1000) > 0


def test_preopen_condition_is_independent_and_gate_is_deferred() -> None:
    spec = market_spec(condition_id="condition", slug="btc-updown-5m-1000", title="Bitcoin")
    bars = tuple(_bar(second) for second in range(900, 1001))
    chainlink = tuple(
        {"source_timestamp_ms": second * 1000, "value_decimal": Decimal(second)}
        for second in range(900, 1001)
    )
    rows = build_preopen_rows(
        specs={"condition": spec},
        episodes={"condition": ({"source_second": 990, "outcome": "Up", "role": "TAKER", "source_notional": 2},)},
        chainlink={"btc/usd": chainlink},
        binance={"BTCUSDT": bars},
        capture_started_ms=900_000,
        capture_ended_ms=1_001_000,
    )
    assert rows[0]["eligible"] is True
    assert rows[0]["binance_momentum_15s_aligned"] is True
    assert rows[0]["chainlink_momentum_15s_aligned"] is True
    summary = summarize_preopen(rows)
    assert summary["study_status"] == "COLLECTING"
    assert summary["stopping_rule"]["gate_evaluation_deferred"] is True

