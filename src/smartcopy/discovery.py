from __future__ import annotations

from dataclasses import dataclass

from .models import LeaderboardEntry, WalletProfile
from .polymarket import PolymarketDataAPI
from .wallets import WalletIntelligenceEngine


@dataclass(frozen=True, slots=True)
class WalletCandidate:
    proxy_wallet: str
    username: str | None
    evidence: tuple[LeaderboardEntry, ...]

    @property
    def best_rank(self) -> int | None:
        ranks = [entry.rank for entry in self.evidence if entry.rank is not None]
        return min(ranks) if ranks else None


class WalletDiscoveryService:
    """Discover research candidates, then build evidence-gated profiles.

    Leaderboard appearance is discovery evidence only. It never authorizes copy.
    """

    def __init__(self, api: PolymarketDataAPI, engine: WalletIntelligenceEngine | None = None) -> None:
        self.api = api
        self.engine = engine or WalletIntelligenceEngine()

    def discover(
        self,
        *,
        category: str = "CRYPTO",
        time_periods: tuple[str, ...] = ("WEEK", "MONTH", "ALL"),
        order_bys: tuple[str, ...] = ("PNL", "VOL"),
        limit: int = 50,
    ) -> tuple[WalletCandidate, ...]:
        by_wallet: dict[str, list[LeaderboardEntry]] = {}
        usernames: dict[str, str | None] = {}
        for period in time_periods:
            for order_by in order_bys:
                for row in self.api.leaderboard(
                    category=category,
                    time_period=period,
                    order_by=order_by,
                    limit=limit,
                ):
                    by_wallet.setdefault(row.proxy_wallet, []).append(row)
                    usernames.setdefault(row.proxy_wallet, row.username)

        candidates = [
            WalletCandidate(
                proxy_wallet=wallet,
                username=usernames.get(wallet),
                evidence=tuple(entries),
            )
            for wallet, entries in by_wallet.items()
        ]
        return tuple(sorted(candidates, key=_candidate_sort_key))

    def profile_candidate(
        self,
        candidate: WalletCandidate,
        *,
        activity_pages: int = 20,
        closed_position_pages: int = 200,
    ) -> WalletProfile:
        activities = self.api.collect_activity(candidate.proxy_wallet, max_pages=activity_pages)
        closed_positions = self.api.collect_closed_positions(candidate.proxy_wallet, max_pages=closed_position_pages)
        return self.engine.profile(
            wallet=candidate.proxy_wallet,
            activities=activities,
            closed_positions=closed_positions,
        )


def _candidate_sort_key(candidate: WalletCandidate) -> tuple[int, int, str]:
    best_rank = candidate.best_rank if candidate.best_rank is not None else 10**9
    return (best_rank, -len(candidate.evidence), candidate.proxy_wallet)
