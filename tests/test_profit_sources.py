import hashlib
import json
from datetime import datetime, timezone

import pytest

from smartcopy.models import ObservationMode, WalletActivity
from smartcopy.profit_sources import (
    FROZEN_END,
    FROZEN_START,
    FROZEN_TYPES,
    FROZEN_WALLET,
    ProfitSourceEvidenceError,
    write_profit_source_sufficiency,
)


OBSERVED = datetime(2026, 8, 26, tzinfo=timezone.utc)


def _targets(path):
    rows = [
        {"condition_id": f"condition-{i}", "symbol": "BTC", "market_family": "crypto_updown_5m"}
        for i in range(763)
    ]
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _activity(kind: str, second: int, *, condition: str = "", usdc: float = 0.0, size: float = 0.0):
    return WalletActivity(
        proxy_wallet=FROZEN_WALLET,
        source_event_time=datetime.fromtimestamp(second, tz=timezone.utc),
        first_observed_time=OBSERVED,
        condition_id=condition,
        activity_type=kind,
        side=None,
        size=size,
        usdc_size=usdc,
        price=None,
        asset=None,
        transaction_hash=f"tx-{kind}-{second}-{condition}",
        title=None,
        slug=None,
        event_slug=None,
        outcome=None,
        observation_mode=ObservationMode.BACKFILL,
        raw={"type": kind, "timestamp": second, "conditionId": condition, "usdcSize": usdc, "size": size},
    )


class _Client:
    def __init__(self, rows):
        self.rows = tuple(rows)
        self.calls = []

    def collect_activity_range(self, user, *, start, end, activity_type):
        self.calls.append((user, start, end, activity_type))
        return self.rows


def test_stage2p_summary_is_data_sufficiency_not_pnl(tmp_path) -> None:
    target_path = tmp_path / "stage2h.jsonl"
    digest = _targets(target_path)
    rows = [
        _activity("REDEEM", FROZEN_START + 1, condition="condition-1", usdc=25, size=25),
        _activity("REDEEM", FROZEN_START + 2, condition="other", usdc=0, size=25),
        _activity("REWARD", FROZEN_START + 3, usdc=2.5),
        _activity("MAKER_REBATE", FROZEN_START + 4, usdc=1.25),
        _activity("TAKER_REBATE", FROZEN_START + 5, usdc=0.5),
        _activity("SPLIT", FROZEN_START + 6, condition="condition-2", size=10),
        _activity("MERGE", FROZEN_START + 7, condition="condition-2", size=4),
    ]
    client = _Client(rows)
    payload = write_profit_source_sufficiency(
        client=client,  # type: ignore[arg-type]
        target_markets_path=target_path,
        output_dir=tmp_path / "out",
        expected_target_markets_sha256=digest,
        clock=lambda: OBSERVED,
    )

    assert client.calls == [(FROZEN_WALLET, FROZEN_START, FROZEN_END, FROZEN_TYPES)]
    assert payload["verdict"] == "PUBLIC_PROFIT_SOURCE_ACTIVITY_PRESENT"
    assert payload["interpretation"] == "DATA_SUFFICIENCY_ONLY_NOT_PNL"
    assert payload["total_requested_type_rows"] == 7
    assert payload["target_condition_overlap_rows"] == 3
    assert payload["target_conditions_with_redeem"] == 1
    assert payload["redeem_usdc_total"] == 25
    assert payload["redeem_target_usdc_total"] == 25
    assert payload["reward_usdc_total"] == 2.5
    assert payload["maker_rebate_usdc_total"] == 1.25
    assert payload["taker_rebate_usdc_total"] == 0.5
    assert payload["split_size_total"] == 10
    assert payload["merge_size_total"] == 4
    assert payload["by_type"]["REDEEM"]["row_count"] == 2


def test_stage2p_empty_complete_interval_is_explicit(tmp_path) -> None:
    target_path = tmp_path / "stage2h.jsonl"
    digest = _targets(target_path)
    payload = write_profit_source_sufficiency(
        client=_Client(()),  # type: ignore[arg-type]
        target_markets_path=target_path,
        output_dir=tmp_path / "out",
        expected_target_markets_sha256=digest,
        clock=lambda: OBSERVED,
    )
    assert payload["verdict"] == "PUBLIC_PROFIT_SOURCE_ACTIVITY_EMPTY"
    assert payload["total_requested_type_rows"] == 0
    assert payload["target_conditions_with_redeem_share"] == 0


def test_stage2p_rejects_unfrozen_activity_type_set(tmp_path) -> None:
    target_path = tmp_path / "stage2h.jsonl"
    digest = _targets(target_path)
    with pytest.raises(ProfitSourceEvidenceError, match="activity type set"):
        write_profit_source_sufficiency(
            client=_Client(()),  # type: ignore[arg-type]
            target_markets_path=target_path,
            output_dir=tmp_path / "out",
            expected_target_markets_sha256=digest,
            activity_types="REDEEM",
        )


def test_stage2p_rejects_non_backfill_or_unexpected_type(tmp_path) -> None:
    target_path = tmp_path / "stage2h.jsonl"
    digest = _targets(target_path)
    bad = _activity("REWARD", FROZEN_START + 1)
    bad = WalletActivity(
        proxy_wallet=bad.proxy_wallet,
        source_event_time=bad.source_event_time,
        first_observed_time=bad.first_observed_time,
        condition_id=bad.condition_id,
        activity_type=bad.activity_type,
        side=bad.side,
        size=bad.size,
        usdc_size=bad.usdc_size,
        price=bad.price,
        asset=bad.asset,
        transaction_hash=bad.transaction_hash,
        title=bad.title,
        slug=bad.slug,
        event_slug=bad.event_slug,
        outcome=bad.outcome,
        observation_mode=ObservationMode.LIVE_OBSERVED,
        raw=bad.raw,
    )
    with pytest.raises(ProfitSourceEvidenceError, match="non-BACKFILL"):
        write_profit_source_sufficiency(
            client=_Client((bad,)),  # type: ignore[arg-type]
            target_markets_path=target_path,
            output_dir=tmp_path / "out",
            expected_target_markets_sha256=digest,
        )
