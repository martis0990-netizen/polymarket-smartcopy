from datetime import datetime, timedelta, timezone

import pytest

from smartcopy.models import ClosedPosition
from smartcopy.polymarket import PaginationTruncatedError
from smartcopy.settlement_backfill import collect_closed_positions_interval


T0 = datetime(2026, 8, 25, tzinfo=timezone.utc)


def _row(second: int | None, *, condition: str) -> ClosedPosition:
    closed = None if second is None else T0 + timedelta(seconds=second)
    return ClosedPosition(
        proxy_wallet="0xabc",
        condition_id=condition,
        asset=f"asset-{condition}",
        avg_price=0.4,
        total_bought=10,
        realized_pnl=1.0,
        closed_time=closed,
        title="Bitcoin Up or Down 5m",
        slug="btc-updown-5m-1",
        event_slug="btc-updown-5m-1",
        outcome="Up",
        end_date=None,
    )


class _Client:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def closed_positions_page(self, user, *, limit, offset, sort_by, sort_direction):
        self.calls.append((user, limit, offset, sort_by, sort_direction))
        return tuple(self.pages.get(offset, ()))


def test_interval_pages_desc_until_lower_boundary_crossed() -> None:
    start = T0
    end = T0 + timedelta(seconds=99)
    client = _Client({
        0: [_row(150, condition="new"), _row(90, condition="in-a")],
        2: [_row(20, condition="in-b"), _row(-1, condition="old")],
    })
    evidence = collect_closed_positions_interval(client, "0xabc", start=start, end=end, page_size=2)
    assert [row.condition_id for row in evidence.rows] == ["in-b", "in-a"]
    assert evidence.pages_fetched == 2
    assert evidence.last_offset == 2
    assert evidence.lower_boundary_crossed is True
    assert client.calls[0][3:] == ("TIMESTAMP", "DESC")


def test_short_final_page_proves_history_exhaustion() -> None:
    client = _Client({0: [_row(10, condition="only")]})
    evidence = collect_closed_positions_interval(
        client,
        "0xabc",
        start=T0,
        end=T0 + timedelta(seconds=20),
        page_size=2,
    )
    assert len(evidence.rows) == 1
    assert evidence.lower_boundary_crossed is True


def test_missing_timestamp_is_counted_not_silently_included() -> None:
    client = _Client({0: [_row(None, condition="missing"), _row(-1, condition="old")]})
    evidence = collect_closed_positions_interval(client, "0xabc", start=T0, end=T0 + timedelta(days=1), page_size=2)
    assert evidence.rows == ()
    assert evidence.missing_timestamp_count == 1


def test_offset_exhaustion_fails_closed() -> None:
    client = _Client({
        0: [_row(10, condition="a"), _row(11, condition="b")],
        2: [_row(12, condition="c"), _row(13, condition="d")],
    })
    with pytest.raises(PaginationTruncatedError, match="completeness cannot be proven"):
        collect_closed_positions_interval(
            client,
            "0xabc",
            start=T0,
            end=T0 + timedelta(days=1),
            page_size=2,
            max_offset=2,
        )


def test_rejects_invalid_range_and_page_size() -> None:
    client = _Client({})
    with pytest.raises(ValueError, match="start must be <= end"):
        collect_closed_positions_interval(client, "0xabc", start=T0 + timedelta(days=1), end=T0)
    with pytest.raises(ValueError, match="page_size"):
        collect_closed_positions_interval(client, "0xabc", start=T0, end=T0, page_size=51)
