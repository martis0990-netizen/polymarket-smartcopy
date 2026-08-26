import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from smartcopy.backfill import write_activity_backfill
from smartcopy.models import ObservationMode, WalletActivity
from smartcopy.polymarket import PaginationTruncatedError


WALLET = "0x1111111111111111111111111111111111111111"
T0 = datetime(2026, 8, 26, 9, 0, tzinfo=timezone.utc)


def _activity(timestamp: int, tx: str) -> WalletActivity:
    source = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    return WalletActivity(
        proxy_wallet=WALLET,
        source_event_time=source,
        first_observed_time=T0,
        condition_id="0xcondition",
        activity_type="TRADE",
        side="BUY",
        size=10,
        usdc_size=4,
        price=0.4,
        asset=f"asset-{tx}",
        transaction_hash=tx,
        title="test",
        slug="test-slug",
        event_slug="event-slug",
        outcome="Up",
        observation_mode=ObservationMode.BACKFILL,
        raw={"timestamp": timestamp, "transactionHash": tx, "asset": f"asset-{tx}"},
    )


class _CompleteClient:
    def collect_activity_range(self, user, *, start, end, page_size, max_split_depth):
        assert user == WALLET
        assert (start, end) == (10, 20)
        assert page_size == 500
        assert max_split_depth == 24
        return (_activity(10, "tx-a"), _activity(20, "tx-b"))


class _IncompleteClient:
    def collect_activity_range(self, *args, **kwargs):
        raise PaginationTruncatedError("cannot prove completeness")


class _WrongModeClient:
    def collect_activity_range(self, *args, **kwargs):
        item = _activity(10, "tx-a")
        return (
            WalletActivity(
                proxy_wallet=item.proxy_wallet,
                source_event_time=item.source_event_time,
                first_observed_time=item.first_observed_time,
                condition_id=item.condition_id,
                activity_type=item.activity_type,
                side=item.side,
                size=item.size,
                usdc_size=item.usdc_size,
                price=item.price,
                asset=item.asset,
                transaction_hash=item.transaction_hash,
                title=item.title,
                slug=item.slug,
                event_slug=item.event_slug,
                outcome=item.outcome,
                observation_mode=ObservationMode.LIVE_OBSERVED,
                raw=item.raw,
            ),
        )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_backfill_writes_source_normalized_and_manifest_last(tmp_path) -> None:
    manifest = write_activity_backfill(
        client=_CompleteClient(),  # type: ignore[arg-type]
        wallet=WALLET.upper().replace("0X", "0x"),
        start=10,
        end=20,
        output_dir=tmp_path,
        clock=lambda: T0,
    )

    source = tmp_path / "activity_source_rows.jsonl"
    normalized = tmp_path / "activity_normalized.jsonl"
    manifest_path = tmp_path / "backfill_manifest.json"
    assert source.is_file() and normalized.is_file() and manifest_path.is_file()

    assert manifest["wallet"] == WALLET
    assert manifest["completeness"] == "PROVEN_WITHIN_REQUESTED_RANGE"
    assert manifest["observation_mode"] == "backfill"
    assert manifest["row_count"] == 2
    assert manifest["first_source_event_time"] == "1970-01-01T00:00:10Z"
    assert manifest["last_source_event_time"] == "1970-01-01T00:00:20Z"

    records = {item["path"]: item for item in manifest["artifacts"]}
    assert records[source.name]["sha256"] == _sha256(source)
    assert records[normalized.name]["sha256"] == _sha256(normalized)
    assert records[source.name]["bytes"] == source.stat().st_size
    assert records[normalized.name]["bytes"] == normalized.stat().st_size

    normalized_rows = [json.loads(line) for line in normalized.read_text().splitlines()]
    assert [row["observation_mode"] for row in normalized_rows] == ["backfill", "backfill"]
    assert [row["transaction_hash"] for row in normalized_rows] == ["tx-a", "tx-b"]


def test_backfill_produces_no_success_artifacts_when_completeness_fails(tmp_path) -> None:
    with pytest.raises(PaginationTruncatedError, match="cannot prove completeness"):
        write_activity_backfill(
            client=_IncompleteClient(),  # type: ignore[arg-type]
            wallet=WALLET,
            start=10,
            end=20,
            output_dir=tmp_path,
        )

    assert not (tmp_path / "backfill_manifest.json").exists()
    assert not (tmp_path / "activity_source_rows.jsonl").exists()
    assert not (tmp_path / "activity_normalized.jsonl").exists()


def test_backfill_refuses_to_relabel_live_observed_rows_as_history(tmp_path) -> None:
    with pytest.raises(ValueError, match="non-BACKFILL"):
        write_activity_backfill(
            client=_WrongModeClient(),  # type: ignore[arg-type]
            wallet=WALLET,
            start=10,
            end=20,
            output_dir=tmp_path,
        )
    assert not (tmp_path / "backfill_manifest.json").exists()


def test_backfill_refuses_overwrite(tmp_path) -> None:
    (tmp_path / "activity_source_rows.jsonl").write_text("existing\n")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        write_activity_backfill(
            client=_CompleteClient(),  # type: ignore[arg-type]
            wallet=WALLET,
            start=10,
            end=20,
            output_dir=tmp_path,
            clock=lambda: T0,
        )


def test_backfill_rejects_invalid_wallet(tmp_path) -> None:
    with pytest.raises(ValueError, match="40-hex"):
        write_activity_backfill(
            client=_CompleteClient(),  # type: ignore[arg-type]
            wallet="0x123",
            start=10,
            end=20,
            output_dir=tmp_path,
        )
