from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any


class MarketFamily(StrEnum):
    CRYPTO_UPDOWN_5M = "crypto_updown_5m"
    CRYPTO_UPDOWN_15M = "crypto_updown_15m"
    CRYPTO_UPDOWN_1H = "crypto_updown_1h"
    CRYPTO_PRICE_THRESHOLD = "crypto_price_threshold"
    FOOTBALL_MATCH_WINNER = "football_match_winner"
    SPORTS_OVER_UNDER = "sports_over_under"
    ESPORTS_MATCH_WINNER = "esports_match_winner"
    POLITICS_LONG_DATED = "politics_long_dated"
    UNKNOWN = "unknown"


class StrategyArchetype(StrEnum):
    DIRECTIONAL = "directional"
    MARKET_MAKER = "market_maker"
    ARBITRAGE = "arbitrage"
    PAIRED_HEDGE = "paired_hedge"
    SCALPER = "scalper"
    UNKNOWN = "unknown"


class IntentKind(StrEnum):
    ENTER = "enter"
    ADD = "add"
    HOLD = "hold"
    REDUCE = "reduce"
    EXIT = "exit"
    FLIP = "flip"
    HEDGE = "hedge"
    UNKNOWN = "unknown"


class WatchlistStatus(StrEnum):
    RESEARCH_ELIGIBLE = "research_eligible"
    WATCH_ONLY = "watch_only"
    INSUFFICIENT_SAMPLE = "insufficient_sample"


class ObservationMode(StrEnum):
    """How an activity row entered SmartCopy's evidence set.

    ``BACKFILL`` means the row was fetched after the historical source event and its local
    observation time is ingestion provenance only. ``LIVE_OBSERVED`` is reserved for a
    prospective path where the row is first seen while monitoring and may later support
    latency analysis.
    """

    BACKFILL = "backfill"
    LIVE_OBSERVED = "live_observed"


@dataclass(frozen=True, slots=True)
class LeaderboardEntry:
    rank: int | None
    proxy_wallet: str
    username: str | None
    volume: float
    pnl: float
    category: str
    time_period: str


@dataclass(frozen=True, slots=True)
class WalletActivity:
    proxy_wallet: str
    source_event_time: datetime
    first_observed_time: datetime
    condition_id: str
    activity_type: str
    side: str | None
    size: float
    usdc_size: float
    price: float | None
    asset: str | None
    transaction_hash: str | None
    title: str | None
    slug: str | None
    event_slug: str | None
    outcome: str | None
    observation_mode: ObservationMode = ObservationMode.BACKFILL
    raw: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        if self.first_observed_time < self.source_event_time:
            raise ValueError("first_observed_time cannot precede source_event_time")
        if self.size < 0 or self.usdc_size < 0:
            raise ValueError("activity sizes must be non-negative")
        if self.price is not None and not 0 <= self.price <= 1:
            raise ValueError("prediction-market price must be within [0, 1]")


@dataclass(frozen=True, slots=True)
class ClosedPosition:
    proxy_wallet: str
    condition_id: str
    asset: str | None
    avg_price: float
    total_bought: float
    realized_pnl: float
    closed_time: datetime | None
    title: str | None
    slug: str | None
    event_slug: str | None
    outcome: str | None
    end_date: str | None


@dataclass(frozen=True, slots=True)
class SkillSlice:
    market_family: MarketFamily
    closed_position_count: int
    market_count: int
    realized_pnl: float
    positive_position_rate: float | None
    top1_positive_pnl_share: float | None
    effective_profitable_positions: float | None


@dataclass(frozen=True, slots=True)
class WalletMetrics:
    realized_pnl: float
    trade_count: int
    market_count: int
    active_days: int
    closed_position_count: int
    positive_closed_positions: int
    negative_closed_positions: int
    realized_pnl_drawdown_proxy: float
    top1_positive_pnl_share: float | None
    top5_positive_pnl_share: float | None
    effective_profitable_positions: float | None
    average_trade_usdc: float | None
    median_trade_usdc: float | None
    research_priority_score: float
    score_components: dict[str, float]


@dataclass(frozen=True, slots=True)
class WalletProfile:
    proxy_wallet: str
    metrics: WalletMetrics
    skills: tuple[SkillSlice, ...]
    watchlist_status: WatchlistStatus
    strategy_archetype: StrategyArchetype = StrategyArchetype.UNKNOWN
    strategy_confidence: float = 0.0
    notes: tuple[str, ...] = ()


def utc_from_unix(value: int | float | str | None) -> datetime | None:
    if value is None or value == "":
        return None
    return datetime.fromtimestamp(float(value), tz=timezone.utc)
