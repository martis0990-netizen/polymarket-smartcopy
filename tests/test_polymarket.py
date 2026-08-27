from datetime import datetime, timezone
from email.message import Message
from io import BytesIO
from urllib.error import HTTPError
from urllib.parse import parse_qs, urlparse

import pytest

from smartcopy.models import ObservationMode
from smartcopy.polymarket import PaginationTruncatedError, PolymarketAPIError, PolymarketDataAPI, _request_json


def _activity_row(
    timestamp: int,
    *,
    tx: str,
    asset: str = "token",
    outcome: str = "Up",
    condition_id: str = "0x1",
):
    return {
        "proxyWallet": "0xABC",
        "timestamp": timestamp,
        "conditionId": condition_id,
        "type": "TRADE",
        "side": "BUY",
        "size": 10,
        "usdcSize": 4,
        "price": 0.4,
        "asset": asset,
        "transactionHash": tx,
        "outcome": outcome,
    }


def test_leaderboard_maps_public_api_fields() -> None:
    def transport(url: str, _headers: dict[str, str]):
        query = parse_qs(urlparse(url).query)
        assert query["category"] == ["CRYPTO"]
        return [{"rank": "1", "proxyWallet": "0xABC", "userName": "x", "vol": 12, "pnl": 3}]

    client = PolymarketDataAPI(transport=transport)
    row = client.leaderboard(limit=1)[0]
    assert row.rank == 1
    assert row.proxy_wallet == "0xabc"
    assert row.pnl == 3


def test_activity_stamps_actual_observation_time_as_backfill_by_default() -> None:
    observed = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    source_ts = int(datetime(2026, 8, 25, 11, 59, tzinfo=timezone.utc).timestamp())

    def transport(_url: str, _headers: dict[str, str]):
        return [_activity_row(source_ts, tx="tx")]

    client = PolymarketDataAPI(transport=transport, clock=lambda: observed)
    activity = client.activity_page("0xabc")[0]
    assert activity.first_observed_time == observed
    assert activity.source_event_time < activity.first_observed_time
    assert activity.observation_mode == ObservationMode.BACKFILL


def test_activity_range_params_and_live_observation_mode_are_explicit() -> None:
    observed = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    source_ts = int(datetime(2026, 8, 25, 11, 59, tzinfo=timezone.utc).timestamp())

    def transport(url: str, _headers: dict[str, str]):
        query = parse_qs(urlparse(url).query)
        assert query["start"] == [str(source_ts - 10)]
        assert query["end"] == [str(source_ts + 10)]
        assert query["sortDirection"] == ["ASC"]
        return [_activity_row(source_ts, tx="live-tx")]

    client = PolymarketDataAPI(transport=transport, clock=lambda: observed)
    activity = client.activity_page(
        "0xabc",
        start=source_ts - 10,
        end=source_ts + 10,
        sort_direction="ASC",
        observation_mode=ObservationMode.LIVE_OBSERVED,
    )[0]
    assert activity.observation_mode == ObservationMode.LIVE_OBSERVED
    assert activity.first_observed_time == observed


def test_complete_range_passes_condition_filter_unchanged() -> None:
    condition_filter = "0xaaa,0xbbb"
    seen = []

    def transport(url: str, _headers: dict[str, str]):
        query = parse_qs(urlparse(url).query)
        seen.append(query)
        assert query["market"] == [condition_filter]
        return []

    client = PolymarketDataAPI(transport=transport)
    assert client.collect_activity_range(
        "0xabc", start=10, end=20, market=condition_filter
    ) == ()
    assert len(seen) == 1


def test_activity_rejects_source_timestamp_after_actual_observation() -> None:
    observed = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    source_ts = int(datetime(2026, 8, 25, 12, 0, 1, tzinfo=timezone.utc).timestamp())

    def transport(_url: str, _headers: dict[str, str]):
        return [_activity_row(source_ts, tx="tx")]

    client = PolymarketDataAPI(transport=transport, clock=lambda: observed)
    with pytest.raises(ValueError, match="cannot precede"):
        client.activity_page("0xabc")


def test_activity_enforces_runtime_verified_offset_cap() -> None:
    client = PolymarketDataAPI(transport=lambda _url, _headers: [])
    with pytest.raises(ValueError, match="0..5000"):
        client.activity_page("0xabc", offset=5001)


def test_request_json_retries_429_with_retry_after() -> None:
    calls = 0
    delays = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'[{"ok":true}]'

    def opener(request, *, timeout):
        nonlocal calls
        calls += 1
        assert timeout == 20
        if calls == 1:
            headers = Message()
            headers["Retry-After"] = "0.25"
            raise HTTPError(request.full_url, 429, "rate limited", headers, BytesIO())
        return Response()

    assert _request_json(
        "https://data-api.polymarket.com/activity",
        {},
        opener=opener,
        sleeper=delays.append,
    ) == [{"ok": True}]
    assert calls == 2
    assert delays == [0.25]


def test_request_json_exhausts_bounded_retries() -> None:
    def opener(request, *, timeout):
        raise HTTPError(request.full_url, 503, "unavailable", Message(), BytesIO())

    with pytest.raises(PolymarketAPIError, match="503"):
        _request_json(
            "https://data-api.polymarket.com/activity",
            {},
            opener=opener,
            sleeper=lambda _delay: None,
            max_attempts=2,
        )


def test_pagination_fails_closed_when_configured_cap_is_full() -> None:
    client = PolymarketDataAPI(transport=lambda _url, _headers: [])

    def full_page(_offset: int):
        return (1, 2)

    with pytest.raises(PaginationTruncatedError, match="refusing to treat the sample as complete"):
        tuple(client._paginate(full_page, page_size=2, max_pages=2, max_offset=100, resource="test"))


def test_collect_activity_range_splits_dense_window_and_sorts_source_time() -> None:
    rows = [
        _activity_row(3, tx="tx3"),
        _activity_row(1, tx="tx1"),
        _activity_row(0, tx="tx0"),
        _activity_row(2, tx="tx2"),
    ]
    calls: list[tuple[int, int, int]] = []

    def transport(url: str, _headers: dict[str, str]):
        query = parse_qs(urlparse(url).query)
        start = int(query["start"][0])
        end = int(query["end"][0])
        offset = int(query["offset"][0])
        limit = int(query["limit"][0])
        calls.append((start, end, offset))
        in_window = [row for row in rows if start <= int(row["timestamp"]) <= end]
        return in_window[offset : offset + limit]

    client = PolymarketDataAPI(
        transport=transport,
        clock=lambda: datetime(2026, 8, 25, tzinfo=timezone.utc),
        activity_offset_cap=2,
    )
    history = client.collect_activity_range("0xabc", start=0, end=3, page_size=2)

    assert [int(item.source_event_time.timestamp()) for item in history] == [0, 1, 2, 3]
    assert all(item.observation_mode == ObservationMode.BACKFILL for item in history)
    assert (0, 3, 0) in calls and (0, 3, 2) in calls
    assert any(start == 0 and end == 1 for start, end, _offset in calls)
    assert any(start == 2 and end == 3 for start, end, _offset in calls)


def test_collect_activity_range_fails_closed_for_too_dense_single_second() -> None:
    rows = [_activity_row(10, tx=f"tx{i}", asset=f"token{i}") for i in range(4)]

    def transport(url: str, _headers: dict[str, str]):
        query = parse_qs(urlparse(url).query)
        offset = int(query["offset"][0])
        limit = int(query["limit"][0])
        return rows[offset : offset + limit]

    client = PolymarketDataAPI(
        transport=transport,
        clock=lambda: datetime(2026, 8, 25, tzinfo=timezone.utc),
        activity_offset_cap=2,
    )
    with pytest.raises(PaginationTruncatedError, match="single-second window 10"):
        client.collect_activity_range("0xabc", start=10, end=10, page_size=2)


def test_collect_activity_range_deduplicates_exact_rows_but_not_same_tx_different_token() -> None:
    duplicate = _activity_row(10, tx="shared", asset="token-a", outcome="Up")
    different_leg = _activity_row(10, tx="shared", asset="token-b", outcome="Down")

    def transport(_url: str, _headers: dict[str, str]):
        return [duplicate, dict(duplicate), different_leg]

    client = PolymarketDataAPI(
        transport=transport,
        clock=lambda: datetime(2026, 8, 25, tzinfo=timezone.utc),
    )
    history = client.collect_activity_range("0xabc", start=10, end=10, page_size=500)

    assert len(history) == 2
    assert {(item.asset, item.outcome) for item in history} == {
        ("token-a", "Up"),
        ("token-b", "Down"),
    }


def test_collect_activity_range_rejects_invalid_window_and_split_depth() -> None:
    client = PolymarketDataAPI(transport=lambda _url, _headers: [])
    with pytest.raises(ValueError, match="start must be <= end"):
        client.collect_activity_range("0xabc", start=11, end=10)
    with pytest.raises(ValueError, match="start must be non-negative"):
        client.collect_activity_range("0xabc", start=-1, end=10)
    with pytest.raises(ValueError, match="max_split_depth"):
        client.collect_activity_range("0xabc", start=0, end=10, max_split_depth=-1)
