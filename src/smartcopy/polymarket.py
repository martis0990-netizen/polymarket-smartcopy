from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Iterable
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import ClosedPosition, LeaderboardEntry, WalletActivity, utc_from_unix


class PolymarketAPIError(RuntimeError):
    pass


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
    ) -> tuple[WalletActivity, ...]:
        if not 0 <= limit <= 500:
            raise ValueError("activity limit must be 0..500")
        rows = self._get(
            "/activity",
            {
                "user": user,
                "limit": limit,
                "offset": offset,
                "type": activity_type,
                "sortBy": "TIMESTAMP",
                "sortDirection": sort_direction,
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

    def collect_activity(self, user: str, *, max_pages: int = 20) -> tuple[WalletActivity, ...]:
        return tuple(self._paginate(lambda offset: self.activity_page(user, limit=500, offset=offset), page_size=500, max_pages=max_pages))

    def collect_closed_positions(self, user: str, *, max_pages: int = 200) -> tuple[ClosedPosition, ...]:
        return tuple(self._paginate(lambda offset: self.closed_positions_page(user, limit=50, offset=offset), page_size=50, max_pages=max_pages))

    @staticmethod
    def _paginate(fetch_page: Callable[[int], Iterable[Any]], *, page_size: int, max_pages: int) -> Iterable[Any]:
        if max_pages < 1:
            raise ValueError("max_pages must be >= 1")
        for page in range(max_pages):
            rows = tuple(fetch_page(page * page_size))
            yield from rows
            if len(rows) < page_size:
                return


def _to_optional_str(value: Any) -> str | None:
    return None if value is None or value == "" else str(value)


def _to_optional_float(value: Any) -> float | None:
    return None if value is None or value == "" else float(value)


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
