from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from smartcopy.live_observer import LiveWalletObserver, ObservationGapError, activity_identity
from smartcopy.models import ObservationMode, WalletActivity


BASE = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
WALLET = "0xabc"


def _trade(second: int, *, tx: str, asset: str = "up", outcome: str = "Up", observed_delay: float = 2.0):
    source = BASE + timedelta(seconds=second)
    return WalletActivity(
        proxy_wallet=WALLET,
        source_event_time=source,
        first_observed_time=source + timedelta(seconds=observed_delay),
        condition_id="condition",
        activity_type="TRADE",
        side="BUY",
        size=10,
        usdc_size=4,
        price=0.4,
        asset=asset,
        transaction_hash=tx,
        title="Bitcoin Up or Down 5m",
        slug="btc-updown-5m-1787731200",
        event_slug="btc-updown-5m-1787731200",
        outcome=outcome,
        observation_mode=ObservationMode.LIVE_OBSERVED,
        raw={"tx": tx, "asset": asset},
    )


class FakeClient:
    def __init__(self, cycles, *, cap=4):
        self.cycles = cycles
        self.activity_offset_cap = cap
        self.cycle = -1
        self.calls = []

    def activity_page(self, user, *, limit, offset, activity_type, sort_direction, observation_mode):
        assert user == WALLET
        assert activity_type == "TRADE"
        assert sort_direction == "DESC"
        assert observation_mode == ObservationMode.LIVE_OBSERVED
        if offset == 0:
            self.cycle += 1
        self.calls.append((self.cycle, offset))
        return tuple(self.cycles[self.cycle].get(offset, ()))


def test_first_poll_seeds_baseline_without_emitting_old_rows() -> None:
    old2 = _trade(-2, tx="old2")
    old1 = _trade(-1, tx="old1")
    client = FakeClient([{0: [old1, old2]}])
    observer = LiveWalletObserver(client, wallet=WALLET, page_size=2, clock=lambda: BASE)

    cycle = observer.poll()

    assert cycle.baseline is True
    assert cycle.baseline_rows == 2
    assert cycle.emitted_rows == ()


def test_second_poll_emits_only_rows_not_known_before_cycle() -> None:
    old = _trade(-1, tx="old")
    new = _trade(1, tx="new")
    client = FakeClient([{0: [old]}, {0: [new, old]}])
    observer = LiveWalletObserver(client, wallet=WALLET, page_size=2, clock=lambda: BASE)

    observer.poll()
    cycle = observer.poll()

    assert [row.transaction_hash for row in cycle.emitted_rows] == ["new"]
    assert cycle.reached_prior_evidence is True


def test_multi_page_catchup_does_not_treat_same_cycle_overlap_as_prior_watermark() -> None:
    old1 = _trade(-2, tx="old1")
    old2 = _trade(-1, tx="old2")
    new1 = _trade(1, tx="new1")
    new2 = _trade(2, tx="new2")
    new3 = _trade(3, tx="new3")
    client = FakeClient([
        {0: [old2, old1]},
        {0: [new3, new2], 2: [new2, new1], 4: [new1, old2]},
    ], cap=4)
    observer = LiveWalletObserver(client, wallet=WALLET, page_size=2, clock=lambda: BASE)

    observer.poll()
    cycle = observer.poll()

    assert [row.transaction_hash for row in cycle.emitted_rows] == ["new1", "new2", "new3"]
    assert client.calls[-3:] == [(1, 0), (1, 2), (1, 4)]
    assert cycle.reached_prior_evidence is True


def test_offset_cap_without_prior_evidence_fails_closed() -> None:
    old1 = _trade(-2, tx="old1")
    old2 = _trade(-1, tx="old2")
    client = FakeClient([
        {0: [old2, old1]},
        {
            0: [_trade(5, tx="a"), _trade(4, tx="b")],
            2: [_trade(3, tx="c"), _trade(2, tx="d")],
            4: [_trade(1, tx="e"), _trade(0, tx="f")],
        },
    ], cap=4)
    observer = LiveWalletObserver(client, wallet=WALLET, page_size=2, clock=lambda: BASE)

    observer.poll()
    with pytest.raises(ObservationGapError, match="final addressable page"):
        observer.poll()


def test_same_transaction_different_assets_are_distinct_identities() -> None:
    up = _trade(1, tx="same", asset="up", outcome="Up")
    down = _trade(1, tx="same", asset="down", outcome="Down")
    assert activity_identity(up) != activity_identity(down)


def test_non_live_row_fails_closed() -> None:
    row = _trade(1, tx="bad")
    row = WalletActivity(
        proxy_wallet=row.proxy_wallet,
        source_event_time=row.source_event_time,
        first_observed_time=row.first_observed_time,
        condition_id=row.condition_id,
        activity_type=row.activity_type,
        side=row.side,
        size=row.size,
        usdc_size=row.usdc_size,
        price=row.price,
        asset=row.asset,
        transaction_hash=row.transaction_hash,
        title=row.title,
        slug=row.slug,
        event_slug=row.event_slug,
        outcome=row.outcome,
        observation_mode=ObservationMode.BACKFILL,
        raw=row.raw,
    )
    client = FakeClient([{0: [row]}])
    observer = LiveWalletObserver(client, wallet=WALLET, page_size=2, clock=lambda: BASE)
    with pytest.raises(ValueError, match="non-LIVE_OBSERVED"):
        observer.poll()


def test_clean_run_writes_manifest_and_only_prospective_rows(tmp_path: Path) -> None:
    old = _trade(-1, tx="old")
    new = _trade(1, tx="new", observed_delay=3)
    client = FakeClient([{0: [old]}, {0: [new, old]}])
    mono_values = iter([0.0, 0.0, 2.0])
    observer = LiveWalletObserver(
        client,
        wallet=WALLET,
        page_size=2,
        clock=lambda: BASE + timedelta(seconds=10),
        monotonic=lambda: next(mono_values),
        sleeper=lambda _seconds: None,
    )

    manifest = observer.run(output_dir=tmp_path / "run", duration_seconds=1.0)

    assert manifest["poll_cycle_count"] == 2
    assert manifest["baseline_row_count"] == 1
    assert manifest["emitted_prospective_row_count"] == 1
    assert manifest["gap_failures"] == 0
    assert manifest["observation_delay_seconds"]["p50"] == pytest.approx(3.0)
    live_lines = (tmp_path / "run" / "live_activity.jsonl").read_text().splitlines()
    assert len(live_lines) == 1
    assert '"transaction_hash":"new"' in live_lines[0]
    assert (tmp_path / "run" / "observer_manifest.json").is_file()


def test_run_refuses_to_overwrite_before_polling(tmp_path: Path) -> None:
    root = tmp_path / "existing"
    root.mkdir()
    (root / "live_activity.jsonl").write_text("evidence\n")
    client = FakeClient([{0: []}])
    observer = LiveWalletObserver(client, wallet=WALLET, page_size=2, clock=lambda: BASE)

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        observer.run(output_dir=root, duration_seconds=1.0)
    assert client.calls == []
