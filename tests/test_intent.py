from datetime import datetime, timedelta, timezone

import pytest

from smartcopy.intent import IntentClusteringPolicy, IntentReconstructor
from smartcopy.models import IntentKind, ObservationMode, WalletActivity


BASE = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def _trade(second: int, *, asset: str = "yes", outcome: str = "Yes", side: str = "BUY", size: float = 10, price: float = 0.4, observed_delay: float = 1.0, observation_mode: ObservationMode = ObservationMode.LIVE_OBSERVED) -> WalletActivity:
    source = BASE + timedelta(seconds=second)
    return WalletActivity(
        proxy_wallet="0xabc",
        source_event_time=source,
        first_observed_time=source + timedelta(seconds=observed_delay),
        condition_id="condition",
        activity_type="TRADE",
        side=side,
        size=size,
        usdc_size=size * price,
        price=price,
        asset=asset,
        transaction_hash=f"tx-{asset}-{side}-{second}",
        title="Bitcoin Up or Down",
        slug="btc-updown-5m-123",
        event_slug=None,
        outcome=outcome,
        observation_mode=observation_mode,
    )


def test_clusters_related_fills_and_seals_after_observation_gap() -> None:
    reconstructor = IntentReconstructor(IntentClusteringPolicy(max_source_gap=timedelta(seconds=5)))
    clusters = reconstructor.cluster([_trade(0, size=10, price=0.4), _trade(2, size=20, price=0.5)])
    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.fill_count == 2
    assert cluster.total_size == 30
    assert round(cluster.vwap_price or 0, 6) == round((10 * 0.4 + 20 * 0.5) / 30, 6)
    assert cluster.observed_end_time == BASE + timedelta(seconds=3)
    assert cluster.sealed_at == BASE + timedelta(seconds=8)


def test_causal_clustering_rejects_historical_backfill() -> None:
    reconstructor = IntentReconstructor()
    with pytest.raises(ValueError, match="LIVE_OBSERVED"):
        reconstructor.cluster([_trade(0, observation_mode=ObservationMode.BACKFILL)])


def test_gap_larger_than_policy_creates_new_episode() -> None:
    reconstructor = IntentReconstructor(IntentClusteringPolicy(max_source_gap=timedelta(seconds=5)))
    assert len(reconstructor.cluster([_trade(0), _trade(6)])) == 2


def test_known_position_supports_enter_add_reduce_exit() -> None:
    reconstructor = IntentReconstructor(IntentClusteringPolicy(max_source_gap=timedelta(seconds=1)))
    clusters = reconstructor.cluster([
        _trade(0, size=10, side="BUY"),
        _trade(3, size=5, side="BUY"),
        _trade(6, size=4, side="SELL"),
        _trade(9, size=11, side="SELL"),
    ])
    intents = reconstructor.reconstruct(clusters, initial_positions={("condition", "yes"): 0.0})
    assert [x.kind for x in intents] == [IntentKind.ENTER, IntentKind.ADD, IntentKind.REDUCE, IntentKind.EXIT]
    assert intents[-1].position_after == 0.0


def test_unknown_initial_position_fails_closed() -> None:
    reconstructor = IntentReconstructor()
    cluster = reconstructor.cluster([_trade(0)])[0]
    intent = reconstructor.reconstruct([cluster])[0]
    assert intent.kind is IntentKind.UNKNOWN
    assert intent.directional_evidence is False


def test_sell_larger_than_known_position_fails_closed() -> None:
    reconstructor = IntentReconstructor()
    cluster = reconstructor.cluster([_trade(0, side="SELL", size=11)])[0]
    intent = reconstructor.reconstruct([cluster], initial_positions={("condition", "yes"): 10.0})[0]
    assert intent.kind is IntentKind.UNKNOWN
    assert intent.position_after is None


def test_paired_outcome_buys_are_flagged_as_non_directional() -> None:
    reconstructor = IntentReconstructor(IntentClusteringPolicy(max_source_gap=timedelta(seconds=5)))
    clusters = reconstructor.cluster([
        _trade(0, asset="yes", outcome="Yes", side="BUY"),
        _trade(2, asset="no", outcome="No", side="BUY", price=0.6),
    ])
    flags = reconstructor.paired_activity_flags(clusters)
    assert len(flags) == 1
    assert flags[0].directional_safe is False
    assert "hedge/arbitrage" in flags[0].reason


def test_late_observation_cannot_retroactively_merge_sealed_episode() -> None:
    reconstructor = IntentReconstructor(IntentClusteringPolicy(max_source_gap=timedelta(seconds=5)))
    first = _trade(0, observed_delay=1)
    late = _trade(2, observed_delay=20)
    clusters = reconstructor.cluster([first, late])
    assert len(clusters) == 2
    assert clusters[0].sealed_at == BASE + timedelta(seconds=6)


def test_paired_flag_requires_observable_time_proximity_too() -> None:
    reconstructor = IntentReconstructor(IntentClusteringPolicy(max_source_gap=timedelta(seconds=5)))
    clusters = reconstructor.cluster([
        _trade(0, asset="yes", outcome="Yes", side="BUY", observed_delay=1),
        _trade(2, asset="no", outcome="No", side="BUY", price=0.6, observed_delay=20),
    ])
    assert reconstructor.paired_activity_flags(clusters) == ()
