from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import (
    ClosedPosition,
    LeaderboardEntry,
    ObservationMode,
    WalletActivity,
    utc_from_unix,
)


class PolymarketAPIError(RuntimeError):
    pass


class PaginationTruncatedError(PolymarketAPIError):
    """Raised instead of silently scoring an incomplete wallet history."""


Transport = Callable[[str, dict[str, str]], Any]
Clock = Callable[[], datetime]


def _default_clock() -> datetime:
    return datetime.now(timezone.utc)


def _default_transport(url: str, headers: dict[str, str]) -> Any:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=20) as response:  # noqa: S310 - fixed HTTPS host by caller
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network boundary
        raise PolymarketAPIError(f"GET {url} failed: {exc}") from exc


@dataclass(slots=True)
class PolymarketDataAPI:
    base_url: str = "https://data-api.polymarket.com"
    transport: Transport = _default_transport
    clock: Clock = _default_clock
    user_agent: str = "polymarket-smartcopy/0.1"
    activity_offset_cap: int = 5_000

    def __post_init__(self) -> None:
        if self.activity_offset_cap < 0:
            raise ValueError("activity_offset_cap must be non-negative")

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        clean = {k: str(v).lower() if isinstance(v, bool) else str(v) for k, v in params.items() if v is not None}
        query = urlencode(clean)
        url = f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"
        if query:
            url = f"{url}?{query}"
        payload = self.transport(url, {"Accept": "application/json", "User-Agent": self.user_agent})
        if not isinstance(payload, list):
            raise PolymarketAPIError(f"expected list response from {path}, got {type(payload).__name__}")
        return payload

    def leaderboard(
        self,
        *,
        category: str = "CRYPTO",
        time_period: str = "MONTH",
        order_by: str = "PNL",
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[LeaderboardEntry, ...]:
        if not 1 <= limit <= 50:
            raise ValueError("leaderboard limit must be 1..50")
        rows = self._get(
            "/v1/leaderboard",
            {"category": category, "timePeriod": time_period, "orderBy": order_by, "limit": limit, "offset": offset},
        )
        return tuple(
            LeaderboardEntry(
                rank=_to_int(row.get("rank")),
                proxy_wallet=str(row["proxyWallet"]).lower(),
                username=_to_optional_str(row.get("userName")),
                volume=float(row.get("vol") or 0.0),
                pnl=float(row.get("pnl") or 0.0),
                category=category.upper(),
                time_period=time_period.upper(),
            )
            for row in rows
        )

    def activity_page(
        self,
        user: str,
        *,
        limit: int = 500,
        offset: int = 0,
        activity_type: str | None = "TRADE",
        sort_direction: str = "DESC",
        start: int | None = None,
        end: int | None = None,
        observation_mode: ObservationMode = ObservationMode.BACKFILL,
    ) -> tuple[WalletActivity, ...]:
        if not 0 <= limit <= 500:
            raise ValueError("activity limit must be 0..500")
        if offset < 0 or offset > self.activity_offset_cap:
            raise ValueError(f"activity offset must be 0..{self.activity_offset_cap}")
        _validate_timestamp_window(start, end)
        observation_mode = ObservationMode(observation_mode)
        rows = self._get(
            "/activity",
            {
                "user": user,
                "limit": limit,
                "offset": offset,
                "type": activity_type,
                "sortBy": "TIMESTAMP",
                "sortDirection": sort_direction,
                "start": start,
                "end": end,
            },
        )
        observed = self.clock()
        items: list[WalletActivity] = []
        for row in rows:
            source_time = utc_from_unix(row.get("timestamp"))
            if source_time is None:
                continue
            items.append(
                WalletActivity(
                    proxy_wallet=str(row.get("proxyWallet") or user).lower(),
                    source_event_time=source_time,
                    first_observed_time=observed,
                    condition_id=str(row.get("conditionId") or ""),
                    activity_type=str(row.get("type") or "UNKNOWN"),
                    side=_to_optional_str(row.get("side")),
                    size=float(row.get("size") or 0.0),
                    usdc_size=float(row.get("usdcSize") or 0.0),
                    price=_to_optional_float(row.get("price")),
                    asset=_to_optional_str(row.get("asset")),
                    transaction_hash=_to_optional_str(row.get("transactionHash")),
                    title=_to_optional_str(row.get("title")),
                    slug=_to_optional_str(row.get("slug")),
                    event_slug=_to_optional_str(row.get("eventSlug")),
                    outcome=_to_optional_str(row.get("outcome")),
                    observation_mode=observation_mode,
                    raw=dict(row),
                )
            )
        return tuple(items)

    def closed_positions_page(
        self,
        user: str,
        *,
        limit: int = 50,
        offset: int = 0,
        sort_by: str = "TIMESTAMP",
        sort_direction: str = "DESC",
    ) -> tuple[ClosedPosition, ...]:
        if not 0 <= limit <= 50:
            raise ValueError("closed-position limit must be 0..50")
        rows = self._get(
            "/closed-positions",
            {
                "user": user,
                "limit": limit,
                "offset": offset,
                "sortBy": sort_by,
                "sortDirection": sort_direction,
            },
        )
        return tuple(
            ClosedPosition(
                proxy_wallet=str(row.get("proxyWallet") or user).lower(),
                condition_id=str(row.get("conditionId") or ""),
                asset=_to_optional_str(row.get("asset")),
                avg_price=float(row.get("avgPrice") or 0.0),
                total_bought=float(row.get("totalBought") or 0.0),
                realized_pnl=float(row.get("realizedPnl") or 0.0),
                closed_time=utc_from_unix(row.get("timestamp")),
                title=_to_optional_str(row.get("title")),
                slug=_to_optional_str(row.get("slug")),
                event_slug=_to_optional_str(row.get("eventSlug")),
                outcome=_to_optional_str(row.get("outcome")),
                end_date=_to_optional_str(row.get("endDate")),
            )
            for row in rows
        )

    def collect_activity(self, user: str, *, max_pages: int = 11) -> tuple[WalletActivity, ...]:
        """Collect the offset-addressable activity prefix, failing closed if incomplete.

        High-frequency wallets can exceed the Activity API's offset budget. Call
        ``collect_activity_range`` when a complete historical interval is required.
        """

        return tuple(
            self._paginate(
                lambda offset: self.activity_page(user, limit=500, offset=offset),
                page_size=500,
                max_pages=max_pages,
                max_offset=self.activity_offset_cap,
                resource="activity",
            )
        )

    def collect_activity_range(
        self,
        user: str,
        *,
        start: int,
        end: int,
        page_size: int = 500,
        max_split_depth: int = 24,
    ) -> tuple[WalletActivity, ...]:
        """Collect a provably complete historical activity interval.

        Each timestamp window consumes its own offset budget. If a window still fills the
        final addressable page, it is bisected deterministically and retried. Inclusive
        integer-second windows are split as ``[start, midpoint]`` and
        ``[midpoint + 1, end]`` so no second is duplicated or omitted. A single second that
        still exceeds the API capacity fails closed rather than silently dropping rows.

        Returned rows are explicitly ``BACKFILL`` evidence. Their ``first_observed_time``
        is ingestion provenance and must not be used as historical live-observation latency.
        """

        _validate_timestamp_window(start, end)
        if start is None or end is None:  # defensive for type checkers/runtime callers
            raise ValueError("activity range requires start and end")
        if not 1 <= page_size <= 500:
            raise ValueError("activity range page_size must be 1..500")
        if max_split_depth < 0:
            raise ValueError("max_split_depth must be non-negative")

        max_pages = self.activity_offset_cap // page_size + 1

        def collect_window(window_start: int, window_end: int, depth: int) -> tuple[WalletActivity, ...]:
            resource = f"activity[{window_start},{window_end}]"
            try:
                return tuple(
                    self._paginate(
                        lambda offset: self.activity_page(
                            user,
                            limit=page_size,
                            offset=offset,
                            sort_direction="ASC",
                            start=window_start,
                            end=window_end,
                            observation_mode=ObservationMode.BACKFILL,
                        ),
                        page_size=page_size,
                        max_pages=max_pages,
                        max_offset=self.activity_offset_cap,
                        resource=resource,
                    )
                )
            except PaginationTruncatedError as exc:
                if window_start == window_end:
                    raise PaginationTruncatedError(
                        f"activity single-second window {window_start} exceeds API pagination capacity; "
                        "completeness cannot be proven"
                    ) from exc
                if depth >= max_split_depth:
                    raise PaginationTruncatedError(
                        f"activity window [{window_start},{window_end}] remained too dense at "
                        f"max_split_depth={max_split_depth}; completeness cannot be proven"
                    ) from exc
                midpoint = (window_start + window_end) // 2
                return collect_window(window_start, midpoint, depth + 1) + collect_window(
                    midpoint + 1, window_end, depth + 1
                )

        collected = collect_window(start, end, 0)
        unique: dict[tuple[Any, ...], WalletActivity] = {}
        for item in collected:
            unique.setdefault(_activity_identity(item), item)
        return tuple(sorted(unique.values(), key=_activity_sort_key))

    def collect_closed_positions(self, user: str, *, max_pages: int = 200) -> tuple[ClosedPosition, ...]:
        return tuple(
            self._paginate(
                lambda offset: self.closed_positions_page(user, limit=50, offset=offset),
                page_size=50,
                max_pages=max_pages,
                max_offset=100_000,
                resource="closed-positions",
            )
        )

    @staticmethod
    def _paginate(
        fetch_page: Callable[[int], Iterable[Any]],
        *,
        page_size: int,
        max_pages: int,
        max_offset: int,
        resource: str,
    ) -> Iterable[Any]:
        if max_pages < 1:
            raise ValueError("max_pages must be >= 1")
        last_was_full = False
        for page in range(max_pages):
            offset = page * page_size
            if offset > max_offset:
                raise PaginationTruncatedError(
                    f"{resource} history exceeds API offset limit {max_offset}; completeness cannot be proven"
                )
            rows = tuple(fetch_page(offset))
            yield from rows
            last_was_full = len(rows) == page_size
            if not last_was_full:
                return
        if last_was_full:
            raise PaginationTruncatedError(
                f"{resource} history reached configured max_pages={max_pages} with a full final page; "
                "refusing to treat the sample as complete"
            )


def _validate_timestamp_window(start: int | None, end: int | None) -> None:
    for field, value in (("start", start), ("end", end)):
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"activity {field} must be an integer Unix second")
        if value < 0:
            raise ValueError(f"activity {field} must be non-negative")
    if start is not None and end is not None and start > end:
        raise ValueError("activity start must be <= end")


def _activity_identity(item: WalletActivity) -> tuple[Any, ...]:
    """Immutable source identity used only to collapse exact duplicate API rows."""

    return (
        item.proxy_wallet,
        item.source_event_time,
        item.condition_id,
        item.activity_type,
        item.side,
        item.size,
        item.usdc_size,
        item.price,
        item.asset,
        item.transaction_hash,
        item.outcome,
    )


def _activity_sort_key(item: WalletActivity) -> tuple[Any, ...]:
    return (
        item.source_event_time,
        item.transaction_hash or "",
        item.condition_id,
        item.asset or "",
        item.activity_type,
        item.side or "",
        item.outcome or "",
        item.price if item.price is not None else -1.0,
        item.size,
        item.usdc_size,
    )


def _to_optional_str(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _to_optional_float(value: Any) -> float | None:
    return None if value is None or value == "" else float(value)


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
