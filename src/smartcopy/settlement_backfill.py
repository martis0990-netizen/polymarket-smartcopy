"""Bounded closed-position evidence collection for frozen historical intervals."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import ClosedPosition
from .polymarket import PaginationTruncatedError, PolymarketDataAPI


@dataclass(frozen=True, slots=True)
class ClosedPositionIntervalEvidence:
    rows: tuple[ClosedPosition, ...]
    pages_fetched: int
    last_offset: int
    missing_timestamp_count: int
    lower_boundary_crossed: bool


def collect_closed_positions_interval(
    client: PolymarketDataAPI,
    user: str,
    *,
    start: datetime,
    end: datetime,
    page_size: int = 50,
    max_offset: int = 100_000,
) -> ClosedPositionIntervalEvidence:
    """Collect a complete closed-position interval from DESC timestamp pagination.

    Completeness is proven only after pagination encounters a row older than ``start``.
    If the offset budget is exhausted first, fail closed.
    """

    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("start/end must be timezone-aware")
    if start > end:
        raise ValueError("start must be <= end")
    if not 1 <= page_size <= 50:
        raise ValueError("page_size must be 1..50")
    if max_offset < 0:
        raise ValueError("max_offset must be non-negative")

    kept: list[ClosedPosition] = []
    missing = 0
    pages = 0
    offset = 0
    crossed = False

    while offset <= max_offset:
        page = client.closed_positions_page(
            user,
            limit=page_size,
            offset=offset,
            sort_by="TIMESTAMP",
            sort_direction="DESC",
        )
        pages += 1
        if not page:
            crossed = True
            break

        for row in page:
            if row.closed_time is None:
                missing += 1
                continue
            if row.closed_time < start:
                crossed = True
                continue
            if row.closed_time <= end:
                kept.append(row)

        if crossed:
            break
        if len(page) < page_size:
            # Exhausted history without an older row. This still proves there are no
            # additional rows below this page.
            crossed = True
            break
        offset += page_size

    if not crossed:
        raise PaginationTruncatedError(
            f"closed-position interval did not cross lower boundary before offset cap {max_offset}; "
            "completeness cannot be proven"
        )

    ordered = tuple(sorted(kept, key=lambda row: (row.closed_time, row.condition_id, row.asset or "")))
    return ClosedPositionIntervalEvidence(
        rows=ordered,
        pages_fetched=pages,
        last_offset=offset,
        missing_timestamp_count=missing,
        lower_boundary_crossed=True,
    )
