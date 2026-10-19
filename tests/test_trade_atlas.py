from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from smartcopy.historical import FROZEN_WALLET
from smartcopy.models import ObservationMode, WalletActivity
from smartcopy.trade_atlas import (
    ActionRole,
    AtlasEvidenceError,
    MarketPhase,
    build_trade_atlas,
    write_trade_atlas_artifacts,
)


START_UNIX = 1787616000
START = datetime.fromtimestamp(START_UNIX, tz=timezone.utc)
SLUG = f"bitcoin-up-or-down-5m-{START_UNIX}"
CONDITION = "condition-a"


def _activity(
    *,
    seconds: int,
    outcome: str,
    asset: str,
    size: float,
    price: float,
    tx: str,
    mode: ObservationMode = ObservationMode.BACKFILL,
    condition: str = CONDITION,
    slug: str = SLUG,
) -> WalletActivity:
    source = START + timedelta(seconds=seconds)
    return WalletActivity(
        proxy_wallet=FROZEN_WALLET,
        source_event_time=source,
        first_observed_time=source + timedelta(hours=1),
        condition_id=condition,
        activity_type="TRADE",
        side="BUY",
        size=size,
        usdc_size=size * price,
        price=price,
        asset=asset,
        transaction_hash=tx,
        title="Bitcoin Up or Down 5 Minutes",
        slug=slug,
        event_slug=slug,
        outcome=outcome,
        observation_mode=mode,
    )


def _sequence() -> list[WalletActivity]:
    return [
        _activity(seconds=10, outcome="Up", asset="up-token", size=10, price=0.40, tx="a"),
        _activity(seconds=20, outcome="Down", asset="down-token", size=5, price=0.58, tx="b"),
        _activity(seconds=30, outcome="Down", asset="down-token", size=10, price=0.59, tx="c"),
        _activity(seconds=40, outcome="Up", asset="up-token", size=5, price=0.43, tx="d"),
    ]


def test_trade_atlas_reconstructs_inventory_state_and_roles() -> None:
    steps, markets, summary = build_trade_atlas(
        _sequence(),
        start=START,
        end=START + timedelta(minutes=5),
    )

    assert len(steps) == 4
    assert len(markets) == 1
    assert [step.action_role for step in steps] == [
        ActionRole.RESIDUAL_INCREASE,
        ActionRole.PAIR_BALANCE,
        ActionRole.BALANCE_THEN_RESIDUAL,
        ActionRole.PAIR_BALANCE,
    ]

    first, second, third, fourth = steps
    assert first.matched_before == 0
    assert first.residual_outcome_after == "Up"
    assert first.residual_size_after == 10

    assert second.balancing_quantity == 5
    assert second.residual_increasing_quantity == 0
    assert second.matched_after == 5
    assert second.residual_outcome_after == "Up"
    assert second.residual_size_after == 5
    assert second.pair_vwap_sum_after == pytest.approx(0.98)

    assert third.balancing_quantity == 5
    assert third.residual_increasing_quantity == 5
    assert third.matched_after == 10
    assert third.residual_outcome_after == "Down"
    assert third.residual_size_after == 5

    assert fourth.matched_after == 15
    assert fourth.residual_outcome_after is None
    assert fourth.residual_size_after == 0
    assert fourth.market_phase == MarketPhase.Q1

    market = markets[0]
    assert market.final_matched_size == 15
    assert market.final_residual_outcome is None
    assert market.imbalance_sign_flips == 1
    assert market.role_sequence_signature == (
        "RESIDUAL_INCREASE>PAIR_BALANCE>BALANCE_THEN_RESIDUAL>PAIR_BALANCE"
    )
    assert market.outcome_sequence_signature == "Up>Down*2>Up"
    assert dict(market.transition_counts) == {
        "BALANCE_THEN_RESIDUAL->PAIR_BALANCE": 1,
        "PAIR_BALANCE->BALANCE_THEN_RESIDUAL": 1,
        "RESIDUAL_INCREASE->PAIR_BALANCE": 1,
    }
    assert summary["step_count"] == 4
    assert summary["market_count"] == 1


def test_same_timestamp_order_is_deterministic_by_transaction_hash_then_asset() -> None:
    rows = [
        _activity(seconds=10, outcome="Down", asset="z-token", size=2, price=0.55, tx="b"),
        _activity(seconds=10, outcome="Up", asset="a-token", size=3, price=0.45, tx="a"),
    ]
    steps, _, _ = build_trade_atlas(rows, start=START, end=START + timedelta(minutes=5))
    assert [step.transaction_hash for step in steps] == ["a", "b"]
    assert [step.fill_index for step in steps] == [1, 2]


def test_live_observed_input_is_rejected() -> None:
    rows = _sequence()
    rows[0] = _activity(
        seconds=10,
        outcome="Up",
        asset="up-token",
        size=10,
        price=0.40,
        tx="a",
        mode=ObservationMode.LIVE_OBSERVED,
    )
    with pytest.raises(AtlasEvidenceError, match="BACKFILL"):
        build_trade_atlas(rows, start=START, end=START + timedelta(minutes=5))


def test_one_sided_market_is_excluded_not_invented() -> None:
    rows = [
        _activity(seconds=10, outcome="Up", asset="up-token", size=3, price=0.45, tx="a")
    ]
    steps, markets, summary = build_trade_atlas(
        rows, start=START, end=START + timedelta(minutes=5)
    )
    assert steps == ()
    assert markets == ()
    assert summary["excluded_non_two_asset_market_count"] == 1


def test_conflicting_asset_outcome_mapping_fails_closed() -> None:
    rows = [
        _activity(seconds=10, outcome="Up", asset="same-token", size=2, price=0.45, tx="a"),
        _activity(seconds=20, outcome="Down", asset="same-token", size=2, price=0.55, tx="b"),
        _activity(seconds=30, outcome="Down", asset="other-token", size=2, price=0.55, tx="c"),
    ]
    with pytest.raises(AtlasEvidenceError, match="conflicting outcomes"):
        build_trade_atlas(rows, start=START, end=START + timedelta(minutes=5))


def test_market_phase_preserves_pre_and_post_window_rows() -> None:
    rows = [
        _activity(seconds=-1, outcome="Up", asset="up-token", size=1, price=0.40, tx="a"),
        _activity(seconds=301, outcome="Down", asset="down-token", size=1, price=0.60, tx="b"),
    ]
    steps, _, _ = build_trade_atlas(
        rows,
        start=START - timedelta(seconds=2),
        end=START + timedelta(seconds=302),
    )
    assert [step.market_phase for step in steps] == [MarketPhase.PRE_WINDOW, MarketPhase.POST_WINDOW]


def _write_normalized(path: Path, rows: list[WalletActivity]) -> str:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = {
                "proxy_wallet": row.proxy_wallet,
                "source_event_time": row.source_event_time.isoformat().replace("+00:00", "Z"),
                "first_observed_time": row.first_observed_time.isoformat().replace("+00:00", "Z"),
                "condition_id": row.condition_id,
                "activity_type": row.activity_type,
                "side": row.side,
                "size": row.size,
                "usdc_size": row.usdc_size,
                "price": row.price,
                "asset": row.asset,
                "transaction_hash": row.transaction_hash,
                "title": row.title,
                "slug": row.slug,
                "event_slug": row.event_slug,
                "outcome": row.outcome,
                "observation_mode": row.observation_mode.value,
            }
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_artifacts_are_hash_bound_create_only_and_byte_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "activity.jsonl"
    digest = _write_normalized(source, _sequence())

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"
    summary1 = write_trade_atlas_artifacts(
        normalized_activity_path=source,
        output_dir=out1,
        expected_sha256=digest,
        start=START,
        end=START + timedelta(minutes=5),
    )
    summary2 = write_trade_atlas_artifacts(
        normalized_activity_path=source,
        output_dir=out2,
        expected_sha256=digest,
        start=START,
        end=START + timedelta(minutes=5),
    )

    for name in ("trade_atlas_steps.jsonl", "trade_atlas_markets.jsonl", "trade_atlas_summary.json"):
        assert (out1 / name).read_bytes() == (out2 / name).read_bytes()
    assert summary1["input"]["sha256"] == digest
    assert summary2["artifacts"] == summary1["artifacts"]

    with pytest.raises(FileExistsError):
        write_trade_atlas_artifacts(
            normalized_activity_path=source,
            output_dir=out1,
            expected_sha256=digest,
            start=START,
            end=START + timedelta(minutes=5),
        )


def test_artifact_writer_rejects_wrong_input_hash(tmp_path: Path) -> None:
    source = tmp_path / "activity.jsonl"
    _write_normalized(source, _sequence())
    with pytest.raises(AtlasEvidenceError, match="SHA256 mismatch"):
        write_trade_atlas_artifacts(
            normalized_activity_path=source,
            output_dir=tmp_path / "out",
            expected_sha256="0" * 64,
            start=START,
            end=START + timedelta(minutes=5),
        )
