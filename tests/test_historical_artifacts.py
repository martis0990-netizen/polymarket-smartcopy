import hashlib
import json
from datetime import datetime, timezone

import pytest

from smartcopy.historical import HistoricalEvidenceError, load_normalized_activity_jsonl, write_stage2h_artifacts


BASE_ROW = {
    "proxy_wallet": "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30",
    "source_event_time": "2026-08-25T00:00:00Z",
    "first_observed_time": "2026-08-26T00:00:00Z",
    "condition_id": "condition",
    "activity_type": "TRADE",
    "side": "BUY",
    "size": 10.0,
    "usdc_size": 4.0,
    "price": 0.4,
    "asset": "asset-up",
    "transaction_hash": "tx",
    "title": "Bitcoin Up or Down",
    "slug": "btc-updown-5m-123",
    "event_slug": "btc-updown-5m-123",
    "outcome": "Up",
    "observation_mode": "backfill",
}


def _write(path, row):
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_loader_requires_explicit_observation_mode(tmp_path) -> None:
    row = dict(BASE_ROW)
    row.pop("observation_mode")
    path = tmp_path / "activity.jsonl"
    _write(path, row)
    with pytest.raises(HistoricalEvidenceError, match="observation_mode is required"):
        load_normalized_activity_jsonl(path)


def test_frozen_writer_rejects_wrong_wallet_even_with_matching_supplied_sha(tmp_path) -> None:
    row = dict(BASE_ROW)
    row["proxy_wallet"] = "0x1111111111111111111111111111111111111111"
    path = tmp_path / "activity.jsonl"
    digest = _write(path, row)
    with pytest.raises(HistoricalEvidenceError, match="frozen wallet mismatch"):
        write_stage2h_artifacts(
            normalized_activity_path=path,
            output_dir=tmp_path / "out",
            expected_sha256=digest,
        )
