from __future__ import annotations

from dataclasses import replace

import pytest

from smartcopy.correction_overlay import market_spec
from smartcopy.external_signal import (
    BinanceKline,
    ExternalSignalError,
    _primary_verdict,
    _rsi,
    _technical_verdict,
    external_features,
    group_live_episodes,
    load_collected_binance_klines,
    normalize_binance_response,
    summarize,
)


CONDITION = "0xcondition"


def _bar(symbol: str, interval: str, second: int, close: float) -> BinanceKline:
    duration_ms = 1_000 if interval == "1s" else 60_000
    return BinanceKline(
        symbol=symbol,
        interval=interval,
        open_time_ms=second * 1_000,
        close_time_ms=second * 1_000 + duration_ms - 1,
        open=close,
        high=close,
        low=close,
        close=close,
        volume=10.0,
        quote_volume=10.0 * close,
        trade_count=1,
        taker_buy_base=6.0,
        taker_buy_quote=6.0 * close,
    )


def _bars() -> dict[tuple[str, str], tuple[BinanceKline, ...]]:
    seconds = tuple(_bar("BTCUSDT", "1s", second, 100.0 + second / 10_000) for second in range(900, 1_101))
    minutes = tuple(_bar("BTCUSDT", "1m", second, 99.0 + second / 10_000) for second in range(0, 1_081, 60))
    return {
        ("BTCUSDT", "1s"): seconds,
        ("BTCUSDT", "1m"): minutes,
    }


def test_binance_normalization_requires_canonical_contiguous_rows() -> None:
    def row(second: int) -> list[object]:
        return [
            second * 1_000,
            "100",
            "101",
            "99",
            "100.5",
            "10",
            second * 1_000 + 999,
            "1000",
            5,
            "6",
            "600",
            "0",
        ]

    envelope = {
        "request": {"symbol": "BTCUSDT", "interval": "1s"},
        "response": [row(100), row(101)],
    }
    bars = normalize_binance_response(envelope)
    assert [bar.source_second for bar in bars] == [100, 101]

    envelope["response"] = [row(100), row(102)]
    with pytest.raises(ExternalSignalError, match="non-contiguous"):
        normalize_binance_response(envelope)


def test_binance_normalization_accepts_frozen_higher_timeframes() -> None:
    for interval, duration in (("5m", 300_000), ("15m", 900_000)):
        envelope = {
            "request": {"symbol": "BTCUSDT", "interval": interval},
            "response": [
                [
                    0,
                    "100",
                    "101",
                    "99",
                    "100",
                    "1",
                    duration - 1,
                    "100",
                    1,
                    "0.5",
                    "50",
                    "0",
                ]
            ],
        }
        bars = normalize_binance_response(envelope)
        assert bars[0].interval == interval


def test_same_second_external_price_is_never_used() -> None:
    bars = _bars()
    first = external_features(
        asset="BTC",
        horizon="5m",
        market_start=1_000,
        market_end=1_300,
        source_second=1_100,
        bars=bars,
    )
    mutated = dict(bars)
    mutated[("BTCUSDT", "1s")] = tuple(
        replace(bar, open=1_000_000, high=1_000_000, low=1_000_000, close=1_000_000)
        if bar.source_second == 1_100
        else bar
        for bar in bars[("BTCUSDT", "1s")]
    )
    second = external_features(
        asset="BTC",
        horizon="5m",
        market_start=1_000,
        market_end=1_300,
        source_second=1_100,
        bars=mutated,
    )
    assert first == second
    assert first["strict_pre_second"] == 1_099
    expected_barrier = sum(100.0 + second / 10_000 for second in range(940, 1_000)) / 60
    assert first["proxy_opening_twap"] == pytest.approx(expected_barrier)


def test_reused_external_tape_is_sha_bound(tmp_path) -> None:
    path = tmp_path / "external.jsonl"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ExternalSignalError, match="SHA256 mismatch"):
        load_collected_binance_klines(path, expected_sha256="0" * 64)


def test_grouping_collapses_partial_fills_and_preserves_role_boundary() -> None:
    spec = market_spec(
        condition_id=CONDITION,
        slug="btc-updown-5m-1000",
        title="Bitcoin Up or Down",
    )
    base = {
        "condition_id": CONDITION,
        "source_second": 1_100,
        "outcome": "Up",
        "schema_corrected_role": "TAKER",
        "opposite_fill": False,
        "source_size": 2.0,
        "source_notional": 0.8,
        "transaction_hash": "0x1",
    }
    rows = [base, {**base, "source_size": 3.0, "source_notional": 1.2, "transaction_hash": "0x2"}]
    episode = group_live_episodes(rows, specs={CONDITION: spec})[0]
    assert episode["fill_rows"] == 2
    assert episode["source_size"] == pytest.approx(5.0)
    assert episode["source_notional"] == pytest.approx(2.0)
    assert episode["role"] == "TAKER"

    mixed = group_live_episodes(
        [base, {**base, "schema_corrected_role": "MAKER", "transaction_hash": "0x2"}],
        specs={CONDITION: spec},
    )[0]
    assert mixed["role"] == "MIXED_ROLE"


def test_wilder_rsi_uses_recursive_smoothing_after_seed() -> None:
    closes = [1, 2, 3, 2, 4, 3]
    # Period 3 seed: avg gain 2/3, avg loss 1/3. Then apply +2 and -1 recursively.
    expected_gain = (((2 / 3) * 2 + 2) / 3 * 2 + 0) / 3
    expected_loss = (((1 / 3) * 2 + 0) / 3 * 2 + 1) / 3
    expected = 100 - 100 / (1 + expected_gain / expected_loss)
    assert _rsi(closes, period=3) == pytest.approx(expected)


def test_frozen_gates_are_deterministic() -> None:
    assert _primary_verdict({"notional_alignment_share": 0.70, "episode_alignment_share": 0.60}) == "SUPPORTED_DESCRIPTIVELY"
    assert _primary_verdict({"notional_alignment_share": 0.55, "episode_alignment_share": 0.90}) == "NOT_SUPPORTED"

    supported = {
        "notional_alignment_share": 0.70,
        "episode_alignment_share": 0.60,
        "by_asset": {
            "BTC": {"notional_alignment_share": 0.60},
            "ETH": {"notional_alignment_share": 0.60},
        },
    }
    assert _technical_verdict(supported) == "SUPPORTED_DESCRIPTIVELY"
    supported["by_asset"]["ETH"]["notional_alignment_share"] = 0.59
    assert _technical_verdict(supported) == "INCONCLUSIVE"


def test_recovered_pilot_cannot_claim_a_frozen_commit() -> None:
    summary = summarize([], inventory_rows=[], gross_taker_fee=0.0)
    assert summary["evidence_status"] == "DESCRIPTIVE_PILOT_MISSING_FROZEN_COMMIT"
    assert summary["contract_frozen_commit"] is None
    assert summary["specification_correction_commit"] is None
    assert summary["unverified_claimed_commits"]["contract"]
