from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import median

from .classify import classify_market
from .models import (
    ClosedPosition,
    MarketFamily,
    SkillSlice,
    StrategyArchetype,
    WalletActivity,
    WalletMetrics,
    WalletProfile,
    WatchlistStatus,
)


@dataclass(frozen=True, slots=True)
class ResearchEligibilityPolicy:
    min_closed_events: int = 20
    min_markets: int = 10
    min_active_days: int = 3
    max_top1_positive_pnl_share: float = 0.50


class WalletIntelligenceEngine:
    """Deterministic Stage-1 wallet research profiler.

    The score ranks *research priority*. It is not a copy score, alpha estimate,
    or authorization to trade.
    """

    def __init__(self, policy: ResearchEligibilityPolicy | None = None) -> None:
        self.policy = policy or ResearchEligibilityPolicy()

    def profile(
        self,
        *,
        wallet: str,
        activities: tuple[WalletActivity, ...] | list[WalletActivity],
        closed_positions: tuple[ClosedPosition, ...] | list[ClosedPosition],
    ) -> WalletProfile:
        activities = tuple(activities)
        closed_positions = tuple(closed_positions)
        metrics = self._metrics(activities, closed_positions)
        skills = self._skills(closed_positions)
        status, notes = self._status(metrics)
        return WalletProfile(
            proxy_wallet=wallet.lower(),
            metrics=metrics,
            skills=skills,
            watchlist_status=status,
            strategy_archetype=StrategyArchetype.UNKNOWN,
            strategy_confidence=0.0,
            notes=notes + ("strategy archetype intentionally left UNKNOWN until Stage 2 intent reconstruction",),
        )

    def _metrics(self, activities: tuple[WalletActivity, ...], closed_positions: tuple[ClosedPosition, ...]) -> WalletMetrics:
        trade_activities = tuple(a for a in activities if a.activity_type.upper() == "TRADE")
        markets = {x.condition_id for x in (*trade_activities, *closed_positions) if x.condition_id}
        active_days = len({a.source_event_time.date() for a in trade_activities})
        pnls = [p.realized_pnl for p in closed_positions]
        positive = [x for x in pnls if x > 0]
        negative = [x for x in pnls if x < 0]
        top1, top5, effective = _profit_concentration(positive)
        drawdown = _max_drawdown(closed_positions)
        trade_usdc = [a.usdc_size for a in trade_activities if a.usdc_size > 0]

        p = self.policy
        sample_score = min(1.0, len(closed_positions) / p.min_closed_events) if p.min_closed_events else 1.0
        diversity_score = min(1.0, len(markets) / p.min_markets) if p.min_markets else 1.0
        activity_score = min(1.0, active_days / p.min_active_days) if p.min_active_days else 1.0
        concentration_score = 0.0 if top1 is None else max(0.0, 1.0 - top1)
        consistency_score = (len(positive) / len(pnls)) if pnls else 0.0
        components = {
            "sample": sample_score,
            "diversity": diversity_score,
            "activity": activity_score,
            "concentration": concentration_score,
            "consistency": consistency_score,
        }
        research_priority = (
            0.25 * sample_score
            + 0.20 * diversity_score
            + 0.15 * activity_score
            + 0.25 * concentration_score
            + 0.15 * consistency_score
        )

        return WalletMetrics(
            realized_pnl=sum(pnls),
            trade_count=len(trade_activities),
            market_count=len(markets),
            active_days=active_days,
            closed_event_count=len(closed_positions),
            positive_closed_events=len(positive),
            negative_closed_events=len(negative),
            max_drawdown=drawdown,
            top1_positive_pnl_share=top1,
            top5_positive_pnl_share=top5,
            effective_profitable_events=effective,
            average_trade_usdc=(sum(trade_usdc) / len(trade_usdc)) if trade_usdc else None,
            median_trade_usdc=median(trade_usdc) if trade_usdc else None,
            research_priority_score=research_priority,
            score_components=components,
        )

    def _skills(self, closed_positions: tuple[ClosedPosition, ...]) -> tuple[SkillSlice, ...]:
        grouped: dict[MarketFamily, list[ClosedPosition]] = defaultdict(list)
        for position in closed_positions:
            classification = classify_market(title=position.title, slug=position.slug, event_slug=position.event_slug)
            grouped[classification.family].append(position)

        slices: list[SkillSlice] = []
        for family, positions in grouped.items():
            positive = [p.realized_pnl for p in positions if p.realized_pnl > 0]
            top1, _top5, effective = _profit_concentration(positive)
            slices.append(
                SkillSlice(
                    market_family=family,
                    closed_event_count=len(positions),
                    market_count=len({p.condition_id for p in positions if p.condition_id}),
                    realized_pnl=sum(p.realized_pnl for p in positions),
                    positive_event_rate=(sum(p.realized_pnl > 0 for p in positions) / len(positions)) if positions else None,
                    top1_positive_pnl_share=top1,
                    effective_profitable_events=effective,
                )
            )
        return tuple(sorted(slices, key=lambda s: (-s.closed_event_count, s.market_family.value)))

    def _status(self, metrics: WalletMetrics) -> tuple[WatchlistStatus, tuple[str, ...]]:
        p = self.policy
        deficiencies: list[str] = []
        if metrics.closed_event_count < p.min_closed_events:
            deficiencies.append(f"closed_event_count<{p.min_closed_events}")
        if metrics.market_count < p.min_markets:
            deficiencies.append(f"market_count<{p.min_markets}")
        if metrics.active_days < p.min_active_days:
            deficiencies.append(f"active_days<{p.min_active_days}")
        if deficiencies:
            return WatchlistStatus.INSUFFICIENT_SAMPLE, tuple(deficiencies)
        if metrics.top1_positive_pnl_share is None:
            return WatchlistStatus.WATCH_ONLY, ("no positive closed-event PnL",)
        if metrics.top1_positive_pnl_share > p.max_top1_positive_pnl_share:
            return WatchlistStatus.WATCH_ONLY, ("profit concentration above research-eligibility cap",)
        return WatchlistStatus.RESEARCH_ELIGIBLE, ()


def _profit_concentration(positive_pnls: list[float]) -> tuple[float | None, float | None, float | None]:
    if not positive_pnls:
        return None, None, None
    ordered = sorted(positive_pnls, reverse=True)
    total = sum(ordered)
    shares = [x / total for x in ordered]
    top1 = shares[0]
    top5 = sum(shares[:5])
    hhi = sum(x * x for x in shares)
    effective = 1.0 / hhi if hhi > 0 else None
    return top1, top5, effective


def _max_drawdown(positions: tuple[ClosedPosition, ...]) -> float:
    ordered = sorted((p for p in positions if p.closed_time is not None), key=lambda p: p.closed_time)
    cumulative = 0.0
    peak = 0.0
    max_dd = 0.0
    for position in ordered:
        cumulative += position.realized_pnl
        peak = max(peak, cumulative)
        max_dd = max(max_dd, peak - cumulative)
    return max_dd
