from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from smartcopy.prospective_signal import (
    CoverageGap,
    ChainlinkTwapRecorder,
    ProspectiveSignalError,
    TwapSeries,
    classify_visible_level,
    collapse_primary_taker,
    directional_gate,
    discordant_gate,
    normalize_rtds_twap_message,
)


NOW = datetime(2026, 8, 27, tzinfo=timezone.utc)


def _message(*, symbol: str = "btc/usd", timestamp: int = 1_000, exact: str = "65000500000000000000000") -> dict[str, object]:
    return {
        "topic": "crypto_prices_twap_sixty",
        "type": "update",
        "timestamp": timestamp + 10,
        "payload": {
            "symbol": symbol,
            "value": 1.0,
            "full_accuracy_value": exact,
            "timestamp": timestamp,
            "window_s": 60,
        },
    }


def test_chainlink_normalization_preserves_exact_e18_value() -> None:
    event = normalize_rtds_twap_message(_message(), receive_timestamp=NOW)
    assert event is not None
    assert event.value == Decimal("65000.5")
    assert event.full_accuracy_value == "65000500000000000000000"
    assert event.record()["value"] == "65000.5"


def test_chainlink_normalization_rejects_wrong_window() -> None:
    message = _message()
    message["payload"]["window_s"] = 30  # type: ignore[index]
    with pytest.raises(ProspectiveSignalError, match="expected 60-second"):
        normalize_rtds_twap_message(message, receive_timestamp=NOW)


def test_chainlink_normalization_ignores_documented_control_frames() -> None:
    assert normalize_rtds_twap_message("", receive_timestamp=NOW) is None
    assert normalize_rtds_twap_message("PONG", receive_timestamp=NOW) is None


def test_strict_pre_excludes_same_time_and_any_intersecting_gap() -> None:
    series = TwapSeries()
    first = normalize_rtds_twap_message(_message(timestamp=1_000), receive_timestamp=NOW)
    second = normalize_rtds_twap_message(_message(timestamp=2_000), receive_timestamp=NOW)
    assert first is not None and second is not None
    series.add(first)
    series.add(second)
    assert series.strict_pre("btc/usd", 2_000) == first
    series.add_gap(CoverageGap("btc/usd", 1_500, 1_900, "TEST_GAP"))
    assert series.strict_pre("btc/usd", 2_000, required_from_ms=1_000) is None


def test_primary_taker_is_one_condition_label_and_ties_are_ambiguous() -> None:
    episodes = [
        {"role": "MAKER", "outcome": "Down", "source_second": 99, "source_notional": 10},
        {"role": "TAKER", "outcome": "Up", "source_second": 100, "source_notional": 3},
        {"role": "TAKER", "outcome": "Up", "source_second": 100, "source_notional": 2},
        {"role": "TAKER", "outcome": "Down", "source_second": 101, "source_notional": 8},
    ]
    label = collapse_primary_taker(episodes)
    assert label == {"source_second": 100, "outcome": "Up", "episode_count": 2, "source_notional": 5.0}
    episodes.append({"role": "TAKER", "outcome": "Down", "source_second": 100, "source_notional": 1})
    assert collapse_primary_taker(episodes) is None


def test_frozen_wilson_gate_requires_more_than_raw_65_percent() -> None:
    assert directional_gate(13, 20)["verdict"] == "INCONCLUSIVE"
    assert directional_gate(30, 40)["verdict"] == "SUPPORTED_DESCRIPTIVELY"
    assert directional_gate(11, 20)["verdict"] == "NOT_SUPPORTED"


def test_discordant_comparison_uses_frozen_minimum_and_margin() -> None:
    assert discordant_gate(barrier_wins=1, momentum_wins=8)["verdict"] == "UNDERPOWERED_COMPARISON"
    assert discordant_gate(barrier_wins=3, momentum_wins=7)["verdict"] == "MOMENTUM_DOMINATES_BARRIER"
    assert discordant_gate(barrier_wins=6, momentum_wins=4)["verdict"] == "NO_DOMINANT_CANDIDATE"


def test_visible_level_requires_one_second_of_continuous_strict_pre_presence() -> None:
    updates = [
        {"source_timestamp_ms": 8_500, "price": "0.42", "size": "10"},
        {"source_timestamp_ms": 9_900, "price": "0.42", "size": "8"},
    ]
    assert classify_visible_level(updates, fill_price="0.42", source_timestamp_ms=10_000) == "PRE_POSITIONED_LEVEL"
    late = [{"source_timestamp_ms": 9_500, "price": "0.42", "size": "8"}]
    assert classify_visible_level(late, fill_price="0.42", source_timestamp_ms=10_000) == "LATE_OR_UNSEEN_LEVEL"
    removed = updates + [{"source_timestamp_ms": 9_950, "price": "0.42", "size": "0"}]
    assert classify_visible_level(removed, fill_price="0.42", source_timestamp_ms=10_000) == "LATE_OR_UNSEEN_LEVEL"


def test_bounded_recorder_finalizes_both_symbols_and_refuses_overwrite(tmp_path) -> None:
    class FakeRecorder(ChainlinkTwapRecorder):
        async def _messages(self, deadline):
            yield json.dumps(_message(symbol="btc/usd", timestamp=1_000)), NOW, False
            yield json.dumps(_message(symbol="eth/usd", timestamp=1_000)), NOW, False

    output = tmp_path / "capture"
    manifest = asyncio.run(FakeRecorder().run(output_dir=output, duration_seconds=1))
    assert manifest["event_counts"] == {"btc/usd": 1, "eth/usd": 1}
    assert manifest["clean_finalize"] is True
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        asyncio.run(FakeRecorder().run(output_dir=output, duration_seconds=1))


def test_reconnect_records_a_gap_for_each_previously_seen_symbol(tmp_path) -> None:
    class FakeRecorder(ChainlinkTwapRecorder):
        async def _messages(self, deadline):
            yield json.dumps(_message(symbol="btc/usd", timestamp=1_000)), NOW, False
            yield json.dumps(_message(symbol="eth/usd", timestamp=1_000)), NOW, False
            received = NOW + timedelta(seconds=1)
            yield json.dumps(_message(symbol="btc/usd", timestamp=2_000)), received, True
            yield json.dumps(_message(symbol="eth/usd", timestamp=2_000)), received, False

    output = tmp_path / "capture"
    manifest = asyncio.run(FakeRecorder().run(output_dir=output, duration_seconds=1))
    gaps = [json.loads(line) for line in (output / "chainlink_twap_gaps.jsonl").read_text().splitlines()]
    assert {row["symbol"] for row in gaps} == {"btc/usd", "eth/usd"}
    assert manifest["reconnect_count"] == 1
