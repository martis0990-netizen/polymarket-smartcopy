from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from smartcopy.executable_state_join import JoinDataError, run_join


def _write(path: Path, rows: list[dict]) -> str:
    raw = "".join(json.dumps(row) + "\n" for row in rows).encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def _wallet() -> dict:
    return {
        "proxy_wallet": "0xabc",
        "source_event_time": "2026-08-26T12:00:00Z",
        "first_observed_time": "2026-08-26T12:00:02Z",
        "observation_mode": "live_observed",
        "condition_id": "condition-1",
        "activity_type": "TRADE",
        "side": "BUY",
        "size": 10.0,
        "usdc_size": 4.0,
        "price": 0.40,
        "asset": "token-a",
        "transaction_hash": "0xtx",
        "outcome": "Up",
    }


def _market() -> dict:
    return {
        "venue": "polymarket",
        "event_type": "market_snapshot",
        "ts": "2026-08-26T12:00:02.500000Z",
        "receive_ts": "2026-08-26T12:00:03Z",
        "instrument": "token-a",
        "metrics": {"best_ask_price": 0.45, "best_ask_size": 5.0},
    }


def test_matching_expected_hashes_are_preserved_in_manifest(tmp_path: Path) -> None:
    wallet_path = tmp_path / "live_activity.jsonl"
    market_path = tmp_path / "events.jsonl"
    wallet_sha = _write(wallet_path, [_wallet()])
    market_sha = _write(market_path, [_market()])

    manifest = run_join(
        wallet_activity_path=wallet_path,
        market_events_path=market_path,
        output_dir=tmp_path / "out",
        expected_wallet_sha256=wallet_sha.upper(),
        expected_market_sha256=market_sha,
    )

    assert manifest["inputs"]["wallet_activity"]["sha256"] == wallet_sha
    assert manifest["inputs"]["wallet_activity"]["expected_sha256"] == wallet_sha
    assert manifest["inputs"]["market_events"]["sha256"] == market_sha
    assert manifest["inputs"]["market_events"]["expected_sha256"] == market_sha


def test_wrong_wallet_hash_fails_before_market_scan_or_output(tmp_path: Path) -> None:
    wallet_path = tmp_path / "live_activity.jsonl"
    wallet_sha = _write(wallet_path, [_wallet()])
    missing_market = tmp_path / "missing-events.jsonl"
    output = tmp_path / "out"

    wrong = ("0" if wallet_sha[0] != "0" else "1") + wallet_sha[1:]
    with pytest.raises(JoinDataError, match="wallet activity SHA256 mismatch"):
        run_join(
            wallet_activity_path=wallet_path,
            market_events_path=missing_market,
            output_dir=output,
            expected_wallet_sha256=wrong,
        )

    assert not (output / "executable_state_join.jsonl").exists()
    assert not (output / "join_manifest.json").exists()


def test_wrong_market_hash_fails_before_any_output_artifact(tmp_path: Path) -> None:
    wallet_path = tmp_path / "live_activity.jsonl"
    market_path = tmp_path / "events.jsonl"
    wallet_sha = _write(wallet_path, [_wallet()])
    market_sha = _write(market_path, [_market()])
    output = tmp_path / "out"
    wrong = ("0" if market_sha[0] != "0" else "1") + market_sha[1:]

    with pytest.raises(JoinDataError, match="market events SHA256 mismatch"):
        run_join(
            wallet_activity_path=wallet_path,
            market_events_path=market_path,
            output_dir=output,
            expected_wallet_sha256=wallet_sha,
            expected_market_sha256=wrong,
        )

    assert not (output / "executable_state_join.jsonl").exists()
    assert not (output / "join_manifest.json").exists()


@pytest.mark.parametrize(
    "value",
    ["abc", "g" * 64, " " + "a" * 64, "a" * 63],
)
def test_invalid_expected_hash_is_rejected_before_input_io(tmp_path: Path, value: str) -> None:
    with pytest.raises(JoinDataError, match="expected wallet SHA256"):
        run_join(
            wallet_activity_path=tmp_path / "missing-wallet.jsonl",
            market_events_path=tmp_path / "missing-market.jsonl",
            output_dir=tmp_path / "out",
            expected_wallet_sha256=value,
        )
