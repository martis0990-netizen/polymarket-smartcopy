from smartcopy.correction_overlay import market_spec
from smartcopy.external_signal import BinanceKline
from smartcopy.preopen_model_analysis import build_model_rows


def _bar(second: int, close: float, interval_ms: int) -> BinanceKline:
    return BinanceKline(
        symbol="BTCUSDT",
        interval="1s" if interval_ms == 1_000 else "5m",
        open_time_ms=second * 1_000,
        close_time_ms=second * 1_000 + interval_ms - 1,
        open=close,
        high=close + 0.1,
        low=close - 0.1,
        close=close,
        volume=1,
        quote_volume=close,
        trade_count=1,
        taker_buy_base=0.5,
        taker_buy_quote=close / 2,
    )


def test_precontract_bundle_can_smoke_but_never_enter_v4_count() -> None:
    start = 10_000
    spec = market_spec(
        condition_id="condition",
        slug=f"btc-updown-5m-{start}",
        title="BTC",
    )
    decision = start - 10
    seconds = tuple(_bar(second, 100 + second / 10_000, 1_000) for second in range(decision - 20, decision))
    htf = tuple(_bar(index * 300, 100 + index, 300_000) for index in range(33))
    rows = build_model_rows(
        specs={"condition": spec},
        episodes={
            "condition": (
                {
                    "role": "TAKER",
                    "source_second": decision,
                    "outcome": "Up",
                    "source_notional": 10,
                },
            )
        },
        chainlink={"btc/usd": (), "eth/usd": ()},
        binance={("BTCUSDT", "1s"): seconds, ("BTCUSDT", "5m"): htf},
        capture_started_ms=(start - 700) * 1_000,
        capture_ended_ms=(start + 1) * 1_000,
        confirmatory_capture=False,
    )
    assert rows[0]["MOM15"] == "Up"
    assert rows[0]["confirmatory_eligible"] is False
    assert "PRECONTRACT_CAPTURE" in rows[0]["exclusion_reasons"]


def test_insufficient_capture_excludes_even_contract_bound_row() -> None:
    start = 10_000
    spec = market_spec(
        condition_id="condition",
        slug=f"btc-updown-5m-{start}",
        title="BTC",
    )
    decision = start - 10
    seconds = tuple(
        _bar(second, 100 + second / 10_000, 1_000)
        for second in range(decision - 20, decision)
    )
    rows = build_model_rows(
        specs={"condition": spec},
        episodes={
            "condition": (
                {
                    "role": "TAKER",
                    "source_second": decision,
                    "outcome": "Up",
                    "source_notional": 10,
                },
            )
        },
        chainlink={"btc/usd": (), "eth/usd": ()},
        binance={("BTCUSDT", "1s"): seconds},
        capture_started_ms=(start - 100) * 1_000,
        capture_ended_ms=(start + 1) * 1_000,
        confirmatory_capture=True,
    )
    assert rows[0]["confirmatory_eligible"] is False
    assert rows[0]["exclusion_reasons"] == ["INSUFFICIENT_11M_CAPTURE"]
