from smartcopy.discovery import WalletDiscoveryService
from smartcopy.models import LeaderboardEntry


class FakeAPI:
    def leaderboard(self, *, category: str, time_period: str, order_by: str, limit: int):
        assert category == "CRYPTO"
        assert limit == 50
        if time_period == "WEEK" and order_by == "PNL":
            return (
                LeaderboardEntry(1, "0xa", "A", 10, 5, category, time_period),
                LeaderboardEntry(2, "0xb", "B", 20, 4, category, time_period),
            )
        if time_period == "MONTH" and order_by == "VOL":
            return (LeaderboardEntry(3, "0xa", "A", 100, 6, category, time_period),)
        return ()


def test_discovery_deduplicates_wallets_but_preserves_evidence() -> None:
    service = WalletDiscoveryService(FakeAPI())
    candidates = service.discover(time_periods=("WEEK", "MONTH"), order_bys=("PNL", "VOL"))
    assert [c.proxy_wallet for c in candidates] == ["0xa", "0xb"]
    assert len(candidates[0].evidence) == 2
    assert candidates[0].best_rank == 1
