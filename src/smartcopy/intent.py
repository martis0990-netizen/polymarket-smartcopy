from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from math import isclose

from .classify import classify_market
from .models import IntentKind, MarketFamily, ObservationMode, WalletActivity


@dataclass(frozen=True, slots=True)
class IntentClusteringPolicy:
    """Predeclared fill-clustering rule.

    `max_source_gap` is a research parameter and must be frozen before any
    outcome/copyability evaluation. Changing it after outcome inspection creates
    a new research contract version.
    """

    max_source_gap: timedelta = timedelta(seconds=5)
    position_tolerance: float = 1e-9

    def __post_init__(self) -> None:
        if self.max_source_gap <= timedelta(0):
            raise ValueError("max_source_gap must be positive")
        if self.position_tolerance < 0:
            raise ValueError("position_tolerance must be non-negative")


@dataclass(frozen=True, slots=True)
class FillCluster:
    proxy_wallet: str
    condition_id: str
    asset: str | None
    outcome: str | None
    side: str
    market_family: MarketFamily
    source_start_time: datetime
    source_end_time: datetime
    observed_start_time: datetime
    observed_end_time: datetime
    sealed_at: datetime
    fill_count: int
    total_size: float
    total_usdc: float
    vwap_price: float | None
    transaction_hashes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReconstructedIntent:
    cluster: FillCluster
    kind: IntentKind
    position_before: float | None
    position_after: float | None
    directional_evidence: bool
    reason: str


@dataclass(frozen=True, slots=True)
class PairedActivityFlag:
    proxy_wallet: str
    condition_id: str
    left_asset: str | None
    right_asset: str | None
    start_time: datetime
    end_time: datetime
    reason: str
    directional_safe: bool = False


class IntentReconstructor:
    def __init__(self, policy: IntentClusteringPolicy | None = None) -> None:
        self.policy = policy or IntentClusteringPolicy()

    def cluster(self, activities: tuple[WalletActivity, ...] | list[WalletActivity]) -> tuple[FillCluster, ...]:
        """Cluster only prospectively observed fills.

        Causal clustering depends on when SmartCopy could actually observe each fill.
        Historical ``BACKFILL`` rows carry API-ingestion provenance rather than historical
        live latency, so admitting them here would manufacture episode boundaries from
        page-fetch timing. Historical research must use a separate source-time-only path
        and must not claim causal observability from this method.
        """

        trades = [a for a in activities if a.activity_type.upper() == "TRADE" and a.side is not None]
        if any(a.observation_mode != ObservationMode.LIVE_OBSERVED for a in trades):
            raise ValueError(
                "causal intent clustering requires LIVE_OBSERVED activities; "
                "BACKFILL is historical ingestion evidence"
            )
        trades.sort(
            key=lambda a: (
                a.proxy_wallet,
                a.condition_id,
                a.asset or "",
                a.outcome or "",
                a.side or "",
                a.source_event_time,
                a.transaction_hash or "",
            )
        )

        groups: dict[tuple[str, str, str | None, str | None, str], list[WalletActivity]] = {}
        for activity in trades:
            side = activity.side.upper()
            if side not in {"BUY", "SELL"}:
                continue
            key = (activity.proxy_wallet, activity.condition_id, activity.asset, activity.outcome, side)
            groups.setdefault(key, []).append(activity)

        clusters: list[FillCluster] = []
        for rows in groups.values():
            # Process in the order SmartCopy could actually observe fills. Source
            # timestamps may arrive out of order and must not retroactively merge
            # an episode that was already sealable from the observer's perspective.
            rows.sort(key=lambda a: (a.first_observed_time, a.source_event_time, a.transaction_hash or ""))
            current: list[WalletActivity] = []
            for row in rows:
                if current and not self._can_join_causally(current, row):
                    clusters.append(self._build_cluster(current))
                    current = []
                current.append(row)
            if current:
                clusters.append(self._build_cluster(current))

        return tuple(
            sorted(clusters, key=lambda c: (c.source_start_time, c.proxy_wallet, c.condition_id, c.asset or "", c.side))
        )

    def reconstruct(
        self,
        clusters: tuple[FillCluster, ...] | list[FillCluster],
        *,
        initial_positions: dict[tuple[str, str | None], float] | None = None,
    ) -> tuple[ReconstructedIntent, ...]:
        positions = dict(initial_positions or {})
        results: list[ReconstructedIntent] = []
        for cluster in sorted(
            clusters, key=lambda c: (c.source_start_time, c.source_end_time, c.condition_id, c.asset or "")
        ):
            key = (cluster.condition_id, cluster.asset)
            if key not in positions:
                results.append(
                    ReconstructedIntent(
                        cluster=cluster,
                        kind=IntentKind.UNKNOWN,
                        position_before=None,
                        position_after=None,
                        directional_evidence=False,
                        reason="initial token position is unknown",
                    )
                )
                continue

            before = positions[key]
            if before < -self.policy.position_tolerance:
                raise ValueError("initial token position cannot be negative")
            kind, after, safe, reason = self._classify_change(before, cluster)
            if after is not None:
                positions[key] = after
            results.append(
                ReconstructedIntent(
                    cluster=cluster,
                    kind=kind,
                    position_before=before,
                    position_after=after,
                    directional_evidence=safe,
                    reason=reason,
                )
            )
        return tuple(results)

    def paired_activity_flags(
        self,
        clusters: tuple[FillCluster, ...] | list[FillCluster],
    ) -> tuple[PairedActivityFlag, ...]:
        ordered = sorted(clusters, key=lambda c: (c.proxy_wallet, c.condition_id, c.source_start_time, c.asset or ""))
        flags: list[PairedActivityFlag] = []
        for i, left in enumerate(ordered):
            for right in ordered[i + 1 :]:
                if right.proxy_wallet != left.proxy_wallet or right.condition_id != left.condition_id:
                    if (right.proxy_wallet, right.condition_id) > (left.proxy_wallet, left.condition_id):
                        break
                    continue
                if left.asset == right.asset:
                    continue
                if left.side != "BUY" or right.side != "BUY":
                    continue
                source_gap = _interval_gap(
                    left.source_start_time,
                    left.source_end_time,
                    right.source_start_time,
                    right.source_end_time,
                )
                observed_gap = _interval_gap(
                    left.observed_start_time,
                    left.observed_end_time,
                    right.observed_start_time,
                    right.observed_end_time,
                )
                if source_gap > self.policy.max_source_gap or observed_gap > self.policy.max_source_gap:
                    continue
                flags.append(
                    PairedActivityFlag(
                        proxy_wallet=left.proxy_wallet,
                        condition_id=left.condition_id,
                        left_asset=left.asset,
                        right_asset=right.asset,
                        start_time=min(left.source_start_time, right.source_start_time),
                        end_time=max(left.source_end_time, right.source_end_time),
                        reason=(
                            "near-simultaneous BUY activity in different outcome assets; "
                            "hedge/arbitrage cannot be excluded"
                        ),
                    )
                )
        return tuple(flags)

    def _can_join_causally(self, current: list[WalletActivity], row: WalletActivity) -> bool:
        observed_end = max(item.first_observed_time for item in current)
        if row.first_observed_time > observed_end + self.policy.max_source_gap:
            return False

        source_min = min(item.source_event_time for item in current)
        source_max = max(item.source_event_time for item in current)
        if row.source_event_time < source_min - self.policy.max_source_gap:
            return False
        if row.source_event_time > source_max + self.policy.max_source_gap:
            return False
        return True

    def _build_cluster(self, rows: list[WalletActivity]) -> FillCluster:
        if not rows:
            raise ValueError("cannot build an empty fill cluster")
        first = rows[0]
        prices = [(row.price, row.size) for row in rows if row.price is not None and row.size > 0]
        priced_size = sum(size for _price, size in prices)
        vwap = (sum(price * size for price, size in prices) / priced_size) if priced_size > 0 else None
        observed_start = min(row.first_observed_time for row in rows)
        observed_end = max(row.first_observed_time for row in rows)
        classification = classify_market(title=first.title, slug=first.slug, event_slug=first.event_slug)
        return FillCluster(
            proxy_wallet=first.proxy_wallet,
            condition_id=first.condition_id,
            asset=first.asset,
            outcome=first.outcome,
            side=(first.side or "UNKNOWN").upper(),
            market_family=classification.family,
            source_start_time=min(row.source_event_time for row in rows),
            source_end_time=max(row.source_event_time for row in rows),
            observed_start_time=observed_start,
            observed_end_time=observed_end,
            sealed_at=observed_end + self.policy.max_source_gap,
            fill_count=len(rows),
            total_size=sum(row.size for row in rows),
            total_usdc=sum(row.usdc_size for row in rows),
            vwap_price=vwap,
            transaction_hashes=tuple(row.transaction_hash for row in rows if row.transaction_hash),
        )

    def _classify_change(self, before: float, cluster: FillCluster) -> tuple[IntentKind, float | None, bool, str]:
        tol = self.policy.position_tolerance
        if cluster.side == "BUY":
            after = before + cluster.total_size
            kind = IntentKind.ENTER if isclose(before, 0.0, abs_tol=tol) else IntentKind.ADD
            return kind, after, True, "known token position increased by BUY cluster"

        if cluster.side == "SELL":
            if cluster.total_size > before + tol:
                return (
                    IntentKind.UNKNOWN,
                    None,
                    False,
                    "SELL size exceeds known token position; history is incomplete or inconsistent",
                )
            after = max(0.0, before - cluster.total_size)
            if isclose(after, before, abs_tol=tol):
                return IntentKind.HOLD, after, False, "SELL change is within position tolerance"
            if isclose(after, 0.0, abs_tol=tol):
                return IntentKind.EXIT, 0.0, True, "known token position reduced to zero"
            return IntentKind.REDUCE, after, True, "known token position reduced by SELL cluster"

        return IntentKind.UNKNOWN, None, False, "unsupported side"


def _interval_gap(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> timedelta:
    if a_end < b_start:
        return b_start - a_end
    if b_end < a_start:
        return a_start - b_end
    return timedelta(0)
