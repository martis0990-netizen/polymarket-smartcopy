import math

from smartcopy.external_signal import BinanceKline
from smartcopy.preopen_model_competition import (
    bos_direction,
    evaluate_preopen_candidates,
    momentum_15s,
    oracle_fair_value,
    summarize_model_competition,
    supertrend_direction,
)


def bar(second: int, close: float, *, interval_ms: int = 1_000, high=None, low=None):
    return BinanceKline(
        symbol="BTCUSDT",
        interval="1s" if interval_ms == 1_000 else "5m",
        open_time_ms=second * 1_000,
        close_time_ms=second * 1_000 + interval_ms - 1,
        open=close,
        high=high if high is not None else close + 0.1,
        low=low if low is not None else close - 0.1,
        close=close,
        volume=1,
        quote_volume=close,
        trade_count=1,
        taker_buy_base=0.5,
        taker_buy_quote=close / 2,
    )


def test_momentum_excludes_same_second() -> None:
    bars = [bar(second, 100 + second) for second in range(20)]
    assert momentum_15s(bars, source_second=18) == math.log(117 / 102)
    changed = bars + [bar(18, 1)]
    assert momentum_15s(changed, source_second=18) == math.log(117 / 102)


def test_supertrend_uses_only_fully_closed_bars() -> None:
    bars = [bar(index * 300, 100 + index, interval_ms=300_000) for index in range(20)]
    before_leak = supertrend_direction(bars, source_second=20 * 300)
    leaking = bars + [bar(20 * 300, 1, interval_ms=300_000)]
    assert before_leak == "Up"
    assert supertrend_direction(leaking, source_second=20 * 300) == before_leak


def test_bos_requires_confirmed_pivot_and_close_break() -> None:
    highs = [1, 2, 5, 2, 1, 2, 3, 6]
    lows = [0, 0, 1, 0, 0, 0, 0, 0]
    closes = [0.5, 1, 4, 1, 0.5, 1, 2, 5.5]
    bars = [
        bar(index * 300, closes[index], interval_ms=300_000, high=highs[index], low=lows[index])
        for index in range(len(highs))
    ]
    assert bos_direction(bars, source_second=len(bars) * 300) == "Up"


def test_oracle_fair_value_is_strict_pre_and_basis_corrected() -> None:
    source = 1_000
    bars = [bar(second, 100 + 0.01 * (second - 300)) for second in range(399, source + 1)]
    chainlink = [
        {"source_timestamp_ms": second * 1_000 - 1, "value": 99 + 0.005 * (second - 400)}
        for second in range(399, source)
    ]
    result = oracle_fair_value(bars, chainlink, source_second=source, market_end=source + 300)
    assert result is not None
    assert result.direction in {"Up", "Down"}
    leaked = bars + [bar(source, 1_000_000)]
    same = oracle_fair_value(leaked, chainlink, source_second=source, market_end=source + 300)
    assert same == result


def test_summary_uses_disagreement_gate_not_correlated_votes() -> None:
    rows = []
    for index in range(12):
        label = "Up" if index < 9 else "Down"
        rows.append(
            {
                "label": label,
                "MOM15": "Up",
                "SUPERTREND_HTF_10_3": "Down",
                "BOS_HTF_2": None,
                "ORACLE_FV": None,
            }
        )
    summary = summarize_model_competition(rows)
    comparison = summary["pairwise_disagreements"]["MOM15__vs__SUPERTREND_HTF_10_3"]
    assert comparison["discordant_conditions"] == 12
    assert comparison["winner"] == "MOM15"
    assert comparison["verdict"] == "DOMINANT_CANDIDATE"


def test_evaluator_keeps_missing_oracle_candidate_local() -> None:
    source_second = 6_001
    seconds = [
        bar(second, 100 + second / 1000)
        for second in range(source_second - 20, source_second + 1)
    ]
    htf = [bar(index * 300, 100 + index, interval_ms=300_000) for index in range(20)]
    row = evaluate_preopen_candidates(
        label="Up",
        source_second=source_second,
        market_end=source_second + 300,
        one_second_bars=seconds,
        htf_bars=htf,
        chainlink_rows=[],
    )
    assert row["MOM15"] == "Up"
    assert row["SUPERTREND_HTF_10_3"] == "Up"
    assert row["ORACLE_FV"] is None
