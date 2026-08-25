from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from smartcopy.polymarket import PolymarketDataAPI


def test_leaderboard_maps_public_api_fields() -> None:
    def transport(url: str, _headers: dict[str, str]):
        query = parse_qs(urlparse(url).query)
        assert query["category"] == ["CRYPTO"]
        return [{"rank": "1", "proxyWallet": "0xABC", "userName": "x", "vol": 12, "pnl": 3}]

    client = PolymarketDataAPI(transport=transport)
    row = client.leaderboard(limit=1)[0]
    assert row.rank == 1
    assert row.proxy_wallet == "0xabc"
    assert row.pnl == 3


def test_activity_stamps_actual_observation_time() -> None:
    observed = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    source_ts = int(datetime(2026, 8, 25, 11, 59, tzinfo=timezone.utc).timestamp())

    def transport(_url: str, _headers: dict[str, str]):
        return [{
            "proxyWallet": "0xABC",
            "timestamp": source_ts,
            "conditionId": "0x1",
            "type": "TRADE",
            "side": "BUY",
            "size": 10,
            "usdcSize": 4,
            "price": 0.4,
            "asset": "token",
            "transactionHash": "tx",
        }]

    client = PolymarketDataAPI(transport=transport, clock=lambda: observed)
    activity = client.activity_page("0xabc")[0]
    assert activity.first_observed_time == observed
    assert activity.source_event_time < activity.first_observed_time


def test_activity_rejects_source_timestamp_after_actual_observation() -> None:
    observed = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)
    source_ts = int(datetime(2026, 8, 25, 12, 0, 1, tzinfo=timezone.utc).timestamp())

    def transport(_url: str, _headers: dict[str, str]):
        return [{
            "proxyWallet": "0xabc",
            "timestamp": source_ts,
            "conditionId": "0x1",
            "type": "TRADE",
            "side": "BUY",
            "size": 1,
            "usdcSize": 0.5,
            "price": 0.5,
        }]

    client = PolymarketDataAPI(transport=transport, clock=lambda: observed)
    with pytest.raises(ValueError, match="cannot precede"):
        client.activity_page("0xabc")
