from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from smartcopy.models import ObservationMode
from smartcopy.polymarket import PolymarketDataAPI


FROZEN_TYPES = "REDEEM,REWARD,MAKER_REBATE,TAKER_REBATE,SPLIT,MERGE"


def test_complete_range_passes_frozen_comma_separated_activity_types() -> None:
    seen = []

    def transport(url: str, _headers: dict[str, str]):
        query = parse_qs(urlparse(url).query)
        seen.append(query)
        assert query["type"] == [FROZEN_TYPES]
        assert query["sortDirection"] == ["ASC"]
        assert query["start"] == ["10"]
        assert query["end"] == ["20"]
        return []

    client = PolymarketDataAPI(
        transport=transport,
        clock=lambda: datetime(2026, 8, 26, tzinfo=timezone.utc),
    )
    assert client.collect_activity_range(
        "0x1111111111111111111111111111111111111111",
        start=10,
        end=20,
        activity_type=FROZEN_TYPES,
    ) == ()
    assert len(seen) == 1


def test_non_trade_activity_rows_remain_backfill_and_preserve_raw() -> None:
    rows = [
        {
            "proxyWallet": "0x1111111111111111111111111111111111111111",
            "timestamp": 10,
            "conditionId": "0xcondition",
            "type": "REDEEM",
            "size": 25,
            "usdcSize": 25,
            "transactionHash": "0xtx",
            "price": None,
            "asset": "token-up",
            "outcome": "Up",
        },
        {
            "proxyWallet": "0x1111111111111111111111111111111111111111",
            "timestamp": 11,
            "conditionId": "",
            "type": "MAKER_REBATE",
            "size": 0,
            "usdcSize": 1.25,
            "transactionHash": "0xrebate",
            "price": None,
            "asset": "",
            "outcome": "",
        },
    ]

    client = PolymarketDataAPI(
        transport=lambda _url, _headers: rows,
        clock=lambda: datetime(2026, 8, 26, tzinfo=timezone.utc),
    )
    items = client.collect_activity_range(
        "0x1111111111111111111111111111111111111111",
        start=10,
        end=20,
        activity_type=FROZEN_TYPES,
    )
    assert [item.activity_type for item in items] == ["REDEEM", "MAKER_REBATE"]
    assert all(item.observation_mode is ObservationMode.BACKFILL for item in items)
    assert items[0].usdc_size == 25
    assert items[0].raw["type"] == "REDEEM"
    assert items[1].condition_id == ""
    assert items[1].asset is None


def test_empty_activity_type_filter_is_rejected() -> None:
    client = PolymarketDataAPI(transport=lambda _url, _headers: [])
    with pytest.raises(ValueError, match="activity_type"):
        client.collect_activity_range(
            "0x1111111111111111111111111111111111111111",
            start=10,
            end=20,
            activity_type="   ",
        )
