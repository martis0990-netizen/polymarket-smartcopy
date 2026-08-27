import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone

import pytest

from smartcopy.public_book import (
    GammaMarketDiscovery,
    PublicBookError,
    PublicBookRecorder,
    classify_captured_level,
    normalize_clob_market_message,
)


NOW = datetime(2026, 8, 27, 12, 0, tzinfo=timezone.utc)
TOKEN = "123456789"


def test_gamma_discovery_moves_only_near_expiry_window_to_next_slot():
    calls = []

    def transport(url, headers):
        calls.append(url)
        slug = url.rsplit("/", 1)[-1]
        asset, _, label, epoch_text = slug.split("-")
        window = 300 if label == "5m" else 900
        end = datetime.fromtimestamp(int(epoch_text) + window, timezone.utc)
        return {
            "slug": slug,
            "conditionId": f"condition-{slug}",
            "active": True,
            "closed": False,
            "endDate": end.isoformat().replace("+00:00", "Z"),
            "outcomes": '["Up","Down"]',
            "clobTokenIds": json.dumps([f"{slug}-up", f"{slug}-down"]),
        }

    at = datetime(2026, 8, 27, 12, 4, 50, tzinfo=timezone.utc)
    rows = GammaMarketDiscovery(transport=transport).token_metadata(
        at=at, min_remaining_seconds=30
    )
    slugs = {row["slug"] for row in rows}
    assert "btc-updown-5m-1787832300" in slugs
    assert "btc-updown-15m-1787832000" in slugs
    assert len(rows) == 8
    assert len(calls) == 4


def test_gamma_discovery_fetches_four_independent_markets_concurrently():
    barrier = threading.Barrier(4, timeout=2)

    def transport(url, headers):
        barrier.wait()
        slug = url.rsplit("/", 1)[-1]
        asset, _, label, epoch_text = slug.split("-")
        window = 300 if label == "5m" else 900
        end = datetime.fromtimestamp(int(epoch_text) + window, timezone.utc)
        return {
            "slug": slug,
            "conditionId": f"condition-{slug}",
            "active": True,
            "closed": False,
            "endDate": end.isoformat().replace("+00:00", "Z"),
            "outcomes": ["Up", "Down"],
            "clobTokenIds": [f"{slug}-up", f"{slug}-down"],
        }

    rows = GammaMarketDiscovery(transport=transport).token_metadata(
        at=NOW, min_remaining_seconds=30
    )
    assert len(rows) == 8


def test_gamma_discovery_rejects_inconsistent_slot_end():
    def transport(url, headers):
        slug = url.rsplit("/", 1)[-1]
        return {
            "slug": slug,
            "conditionId": "condition",
            "active": True,
            "closed": False,
            "endDate": "2026-08-27T00:00:00Z",
            "outcomes": ["Up", "Down"],
            "clobTokenIds": ["up", "down"],
        }

    with pytest.raises(PublicBookError, match="endDate does not match"):
        GammaMarketDiscovery(transport=transport).token_metadata(
            at=NOW, min_remaining_seconds=30
        )


def _book(*, timestamp=1_000):
    return {
        "event_type": "book",
        "asset_id": TOKEN,
        "market": "0xcondition",
        "timestamp": str(timestamp),
        "hash": "abc",
        "bids": [{"price": "0.42", "size": "10.50"}],
        "asks": [{"price": "0.58", "size": "9"}],
    }


def _change(*, timestamp=2_000, size="7"):
    return {
        "event_type": "price_change",
        "market": "0xcondition",
        "timestamp": str(timestamp),
        "price_changes": [
            {"asset_id": TOKEN, "price": "0.42", "size": size, "side": "BUY", "hash": "def"}
        ],
    }


def _metadata():
    return [
        {
            "token_id": TOKEN,
            "condition_id": "0xcondition",
            "asset": "BTC",
            "window_seconds": 300,
            "outcome": "Up",
        }
    ]


def test_normalizes_direct_book_with_snapshot_marker():
    records = normalize_clob_market_message(_book(), receive_timestamp=NOW)
    assert [record.record_type for record in records] == ["snapshot", "level", "level"]
    assert records[1].side == "BUY"
    assert str(records[1].price) == "0.42"
    assert str(records[1].size) == "10.50"
    assert records[2].side == "SELL"
    assert all(record.source_timestamp_ms == 1_000 for record in records)


def test_normalizes_absolute_change_and_zero_removal():
    record = normalize_clob_market_message(_change(size="0"), receive_timestamp=NOW)[0]
    assert record.event_type == "price_change"
    assert record.side == "BUY"
    assert record.size == 0


def test_normalizes_sdk_camel_case_shape():
    message = {
        "topic": "market",
        "type": "price_change",
        "payload": {
            "timestamp": 2_000,
            "market": "0xcondition",
            "priceChanges": [
                {"tokenId": TOKEN, "price": "0.60", "size": "1.25", "side": "SELL"}
            ],
        },
    }
    record = normalize_clob_market_message(message, receive_timestamp=NOW)[0]
    assert record.token_id == TOKEN
    assert record.side == "SELL"
    assert str(record.size) == "1.25"


@pytest.mark.parametrize(
    ("message", "match"),
    [
        ({**_book(), "timestamp": None}, "source timestamp"),
        (_change(size="-1"), "non-negative"),
        (
            {**_change(), "price_changes": [{"asset_id": TOKEN, "price": "0.4", "size": "1", "side": "HOLD"}]},
            "unsupported CLOB side",
        ),
    ],
)
def test_invalid_market_data_fails_closed(message, match):
    with pytest.raises(PublicBookError, match=match):
        normalize_clob_market_message(message, receive_timestamp=NOW)


def test_heartbeat_and_irrelevant_event_are_ignored():
    assert normalize_clob_market_message("PONG", receive_timestamp=NOW) == []
    assert normalize_clob_market_message({"event_type": "last_trade_price"}, receive_timestamp=NOW) == []


def test_list_frame_preserves_equal_timestamp_arrival_order():
    records = normalize_clob_market_message(
        [_change(timestamp=2_000, size="2"), _change(timestamp=2_000, size="3")],
        receive_timestamp=NOW,
    )
    assert [str(record.size) for record in records] == ["2", "3"]


def test_naive_receive_time_is_rejected():
    with pytest.raises(PublicBookError, match="timezone-aware"):
        normalize_clob_market_message(_book(), receive_timestamp=NOW.replace(tzinfo=None))


def _normalized_row(line, timestamp, *, record_type="level", size="5", price="0.42", valid=True):
    return {
        "line_number": line,
        "record_type": record_type,
        "event_type": "book" if record_type == "snapshot" else "price_change",
        "token_id": TOKEN,
        "source_timestamp_ms": timestamp,
        "side": None if record_type == "snapshot" else "BUY",
        "price": None if record_type == "snapshot" else price,
        "size": None if record_type == "snapshot" else size,
        "coverage_valid": valid,
    }


def test_captured_level_requires_one_second_continuity():
    rows = [_normalized_row(1, 8_000, record_type="snapshot"), _normalized_row(2, 8_500)]
    assert (
        classify_captured_level(
            rows, token_id=TOKEN, side="BUY", fill_price="0.42", source_timestamp_ms=10_000
        )
        == "PRE_POSITIONED_LEVEL"
    )
    late = [_normalized_row(1, 8_000, record_type="snapshot"), _normalized_row(2, 9_001)]
    assert (
        classify_captured_level(
            late, token_id=TOKEN, side="BUY", fill_price="0.42", source_timestamp_ms=10_000
        )
        == "LATE_OR_UNSEEN_LEVEL"
    )


def test_full_snapshot_clears_a_level_that_is_not_repeated():
    rows = [
        _normalized_row(1, 8_000, record_type="snapshot"),
        _normalized_row(2, 8_000),
        _normalized_row(3, 9_500, record_type="snapshot"),
    ]
    assert (
        classify_captured_level(
            rows, token_id=TOKEN, side="BUY", fill_price="0.42", source_timestamp_ms=10_000
        )
        == "LATE_OR_UNSEEN_LEVEL"
    )


def test_same_source_second_update_is_not_used_in_fill_favour():
    rows = [
        _normalized_row(1, 9_000, record_type="snapshot"),
        _normalized_row(2, 10_001),
    ]
    assert (
        classify_captured_level(
            rows, token_id=TOKEN, side="BUY", fill_price="0.42", source_timestamp_ms=10_000
        )
        == "LATE_OR_UNSEEN_LEVEL"
    )


def test_intersecting_reconnect_gap_makes_level_ineligible():
    rows = [_normalized_row(1, 8_000, record_type="snapshot"), _normalized_row(2, 8_000)]
    gap = {
        "token_id": TOKEN,
        "start_source_timestamp_ms": 9_200,
        "recovered_source_timestamp_ms": 9_800,
    }
    assert (
        classify_captured_level(
            rows,
            token_id=TOKEN,
            side="BUY",
            fill_price="0.42",
            source_timestamp_ms=10_000,
            gaps=[gap],
        )
        == "INELIGIBLE"
    )


def test_recorder_marks_pre_snapshot_delta_ineligible_and_closes_gap(tmp_path):
    class FakeRecorder(PublicBookRecorder):
        async def _messages(self, deadline, token_ids):
            yield json.dumps(_book()), NOW, False
            yield json.dumps(_change(timestamp=2_000)), NOW + timedelta(seconds=1), True
            yield json.dumps(_book(timestamp=3_000)), NOW + timedelta(seconds=2), False

    output = tmp_path / "capture"
    manifest = asyncio.run(
        FakeRecorder().run(
            output_dir=output,
            duration_seconds=1,
            token_metadata=_metadata(),
            code_commit="a" * 40,
        )
    )
    levels = [json.loads(line) for line in (output / "book_levels.jsonl").read_text().splitlines()]
    delta = next(row for row in levels if row["event_type"] == "price_change")
    gaps = [json.loads(line) for line in (output / "book_gaps.jsonl").read_text().splitlines()]
    assert delta["coverage_valid"] is False
    assert gaps[0]["reason"] == "CLOB_RECONNECT"
    assert manifest["reconnect_count"] == 1
    assert manifest["initialized_at_finalize"] == {TOKEN: True}


def test_recorder_rejects_source_timestamp_regression(tmp_path):
    class FakeRecorder(PublicBookRecorder):
        async def _messages(self, deadline, token_ids):
            yield json.dumps(_book(timestamp=2_000)), NOW, False
            yield json.dumps(_change(timestamp=1_999)), NOW + timedelta(seconds=1), False

    output = tmp_path / "capture"
    with pytest.raises(PublicBookError, match="timestamp regressed"):
        asyncio.run(
            FakeRecorder().run(
                output_dir=output,
                duration_seconds=1,
                token_metadata=_metadata(),
                code_commit="a" * 40,
            )
        )
    assert not (output / "public_book_manifest.json").exists()


def test_recorder_rejects_regression_inside_one_list_frame(tmp_path):
    class FakeRecorder(PublicBookRecorder):
        async def _messages(self, deadline, token_ids):
            yield json.dumps([_book(timestamp=2_000), _change(timestamp=1_999)]), NOW, False

    with pytest.raises(PublicBookError, match="timestamp regressed"):
        asyncio.run(
            FakeRecorder().run(
                output_dir=tmp_path / "capture",
                duration_seconds=1,
                token_metadata=_metadata(),
                code_commit="a" * 40,
            )
        )


def test_recorder_refuses_overwrite_and_requires_bound_metadata(tmp_path):
    output = tmp_path / "capture"
    output.mkdir()
    with pytest.raises(FileExistsError):
        asyncio.run(
            PublicBookRecorder().run(
                output_dir=output,
                duration_seconds=1,
                token_metadata=_metadata(),
                code_commit="a" * 40,
            )
        )
    with pytest.raises(ValueError, match="missing fields"):
        asyncio.run(
            PublicBookRecorder().run(
                output_dir=tmp_path / "other",
                duration_seconds=1,
                token_metadata=[{"token_id": TOKEN}],
                code_commit="a" * 40,
            )
        )
