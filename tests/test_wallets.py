from datetime import datetime, timedelta, timezone

from smartcopy.models import ClosedPosition, MarketFamily, WalletActivity, WatchlistStatus
from smartcopy.wallets import ResearchEligibilityPolicy, WalletIntelligenceEngine


def _closed(i: int, pnl: float, *, family: str = "5m") -> ClosedPosition:
    return ClosedPosition(
        proxy_wallet="0xabc",
        condition_id=f"c{i}",
        asset=f"a{i}",
        avg_price=0.5,
        total_bought=100,
        realized_pnl=pnl,
        closed_time=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i),
        title="Bitcoin Up or Down",
        slug=f"btc-updown-{family}-{i}",
        event_slug=None,
        outcome="Up",
        end_date=None,
    )


def _activity(i: int) -> WalletActivity:
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=i)
    return WalletActivity(
        proxy_wallet="0xabc",
        source_event_time=ts,
        first_observed_time=ts,
        condition_id=f"c{i}",
        activity_type="TRADE",
        side="BUY",
        size=10,
        usdc_size=5,
        price=0.5,
        asset="a",
        transaction_hash=f"tx{i}",
        title="Bitcoin Up or Down",
        slug=f"btc-updown-5m-{i}",
        event_slug=None,
        outcome="Up",
    )


def test_wallet_profile_is_conditional_and_research_only() -> None:
    policy = ResearchEligibilityPolicy(min_closed_events=4, min_markets=4, min_active_days=2, max_top1_positive_pnl_share=0.6)
    engine = WalletIntelligenceEngine(policy)
    closed = [_closed(0, 2), _closed(1, 2), _closed(2, -1), _closed(3, 1)]
    activities = [_activity(0), _activity(1), _activity(2), _activity(3)]
    profile = engine.profile(wallet="0xABC", activities=activities, closed_positions=closed)

    assert profile.watchlist_status is WatchlistStatus.RESEARCH_ELIGIBLE
    assert profile.strategy_archetype.value == "unknown"
    assert profile.skills[0].market_family is MarketFamily.CRYPTO_UPDOWN_5M
    assert profile.skills[0].closed_event_count == 4
    assert 0 <= profile.metrics.research_priority_score <= 1


def test_single_lucky_event_is_not_research_eligible() -> None:
    policy = ResearchEligibilityPolicy(min_closed_events=3, min_markets=3, min_active_days=1, max_top1_positive_pnl_share=0.5)
    engine = WalletIntelligenceEngine(policy)
    closed = [_closed(0, 100), _closed(1, -1), _closed(2, -1)]
    profile = engine.profile(wallet="0xabc", activities=[_activity(0), _activity(1), _activity(2)], closed_positions=closed)
    assert profile.watchlist_status is WatchlistStatus.WATCH_ONLY
    assert profile.metrics.top1_positive_pnl_share == 1.0


def test_max_drawdown_from_chronological_realized_pnl() -> None:
    policy = ResearchEligibilityPolicy(min_closed_events=1, min_markets=1, min_active_days=1)
    profile = WalletIntelligenceEngine(policy).profile(
        wallet="0xabc",
        activities=[_activity(0)],
        closed_positions=[_closed(0, 5), _closed(1, -3), _closed(2, 1), _closed(3, -4)],
    )
    assert profile.metrics.max_drawdown == 6


def test_non_profitable_wallet_stays_watch_only_even_with_sample() -> None:
    policy = ResearchEligibilityPolicy(min_closed_events=3, min_markets=3, min_active_days=1)
    profile = WalletIntelligenceEngine(policy).profile(
        wallet="0xabc",
        activities=[_activity(0), _activity(1), _activity(2)],
        closed_positions=[_closed(0, 1), _closed(1, -2), _closed(2, -2)],
    )
    assert profile.watchlist_status is WatchlistStatus.WATCH_ONLY
    assert profile.metrics.realized_pnl < 0
