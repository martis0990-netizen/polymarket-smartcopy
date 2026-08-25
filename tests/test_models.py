from datetime import datetime, timedelta, timezone

import pytest

from smartcopy.models import WalletActivity


def test_observability_contract_rejects_future_leakage() -> None:
    source = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="cannot precede"):
        WalletActivity(
            proxy_wallet="0xabc",
            source_event_time=source,
            first_observed_time=source - timedelta(seconds=1),
            condition_id="c",
            activity_type="TRADE",
            side="BUY",
            size=1,
            usdc_size=0.5,
            price=0.5,
            asset="a",
            transaction_hash="tx",
            title=None,
            slug=None,
            event_slug=None,
            outcome="Yes",
        )
