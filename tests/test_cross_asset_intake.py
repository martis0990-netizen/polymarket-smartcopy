import hashlib
import json
from datetime import datetime, timezone

import pytest

from smartcopy.cross_asset_intake import inspect_v5_capture

SYMBOLS = ("btc", "eth", "sol", "xrp", "bnb", "doge", "hype")
START = 1_780_000_000
MARKET = START + 800
WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"


def iso(second):
    return datetime.fromtimestamp(second, timezone.utc).isoformat().replace("+00:00", "Z")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.write_text(json.dumps(data) + "\n")


def artifact(path):
    return {"bytes": path.stat().st_size, "sha256": sha(path)}


def fixture_bundle(tmp_path, *, asset="sol", candidate=True, oracle_start=START + 10,
                   include_sell=False):
    root = tmp_path / "capture"
    chain, wallet = root / "chainlink", root / "wallet"
    chain.mkdir(parents=True)
    wallet.mkdir()
    lines = []
    for i, asset_symbol in enumerate(SYMBOLS, 1):
        raw = {"v": 1, "channel": "price.crypto.twap", "seq": i,
               "snapshot": True, "payload": {"symbol": asset_symbol + "usd", "data": [], "window_seconds": 60}}
        lines.append({"kind": "snapshot", "raw": raw, "receive_timestamp": iso(oracle_start)})
    for i, asset_symbol in enumerate(SYMBOLS, 8):
        raw = {"v": 1, "channel": "price.crypto.twap", "seq": i,
               "payload": {"symbol": asset_symbol + "usd", "timestamp": (oracle_start - 1) * 1000,
                           "window_seconds": 60, "full_accuracy_value": "123.000000000000000001"}}
        lines.append({"kind": "live", "raw": raw, "normalized": {
            "feed_protocol": "polybolt-v1", "symbol": asset_symbol + "/usd", "channel_seq": i,
            "source_timestamp_ms": (oracle_start - 1) * 1000,
            "receive_timestamp": iso(oracle_start), "value": "123.000000000000000001",
            "full_accuracy_value": "123.000000000000000001",
        }})
    raw_path, gap_path = chain / "chainlink_twap_raw.jsonl", chain / "chainlink_twap_gaps.jsonl"
    raw_path.write_text("".join(json.dumps(line) + "\n" for line in lines))
    gap_path.write_bytes(b"")
    counts = {symbol + "/usd": 1 for symbol in SYMBOLS}
    chain_manifest = {"feed_protocol": "polybolt-v1", "clean_finalize": True,
                      "symbols": list(counts), "event_counts": counts, "reconnect_count": 0,
                      "artifacts": {raw_path.name: artifact(raw_path), gap_path.name: artifact(gap_path)}}
    chain_path = chain / "chainlink_twap_manifest.json"
    write_json(chain_path, chain_manifest)

    wallet_path, cycle_path = wallet / "live_activity.jsonl", wallet / "poll_cycles.jsonl"
    row = {"proxy_wallet": WALLET, "observation_mode": "live_observed", "activity_type": "TRADE",
           "side": "BUY", "slug": f"{asset}-updown-5m-{MARKET}", "condition_id": "condition-1",
           "outcome": "Up", "source_event_time": iso(MARKET - 10),
           "first_observed_time": iso(MARKET - 9), "title": "Crypto Up or Down",
           "price": 0.4, "size": 2.0, "usdc_size": 0.8, "asset": "10001",
           "transaction_hash": "0x" + "1" * 64}
    wallet_lines = [row] if candidate else []
    if include_sell:
        wallet_lines.append({**row, "side": "SELL", "transaction_hash": "0x" + "2" * 64})
    wallet_path.write_text("".join(json.dumps(item) + "\n" for item in wallet_lines))
    cycle_path.write_text(json.dumps({"baseline": True, "finished_at": iso(START + 20)}) + "\n")
    wallet_manifest = {"gap_failures": 0, "emitted_prospective_row_count": len(wallet_lines),
                       "artifacts": {wallet_path.name: artifact(wallet_path), cycle_path.name: artifact(cycle_path)}}
    wallet_manifest_path = wallet / "observer_manifest.json"
    write_json(wallet_manifest_path, wallet_manifest)
    root_manifest = {"schema_version": "smartcopy-bonereaper-cross-asset-capture-v2",
                     "contract_commit": "a696cf068dcb5b4555073d1d5636eec7efa05050",
                     "transport_amendment_commit": "0dd7a371b13f278383f1d81eba44bf88fbb6c3cc",
                     "feed_protocol": "polybolt-v1", "clean_finalize": True,
                     "wallet": WALLET, "symbols": list(counts),
                     "requested_duration_seconds": 1100, "started_at": iso(START), "ended_at": iso(START + 1100),
                     "chainlink": {"sha256": sha(chain_path), "event_counts": counts},
                     "wallet_observer": {"sha256": sha(wallet_manifest_path), "prospective_rows": len(wallet_lines)}}
    manifest_path = root / "cross_asset_capture_manifest.json"
    write_json(manifest_path, root_manifest)
    return root, sha(manifest_path)


def inspect(tmp_path, root, digest):
    return inspect_v5_capture(bundle_dir=root, expected_manifest_sha256=digest,
                              output_dir=tmp_path / "intake", code_commit="a" * 40)


def test_core_candidate_requires_receipts_and_warmup(tmp_path):
    root, digest = fixture_bundle(tmp_path)
    summary = inspect(tmp_path, root, digest)
    assert summary["candidate_conditions"] == 1
    assert summary["warmup_satisfied_core_candidates"] == 1
    assert summary["confirmed_labels"] == 0
    row = json.loads((tmp_path / "intake" / "preopen_buy_candidates.jsonl").read_text())
    assert row["asset"] == "SOL" and row["receipt_label_status"] == "PENDING_FEE_AWARE_POLYGON_RECEIPT"


def test_empty_wallet_bundle_is_valid_and_hype_is_engineering_only(tmp_path):
    root, digest = fixture_bundle(tmp_path, candidate=False)
    assert inspect(tmp_path, root, digest)["candidate_conditions"] == 0
    other = tmp_path / "other"
    other.mkdir()
    root, digest = fixture_bundle(other, asset="hype")
    summary = inspect(other, root, digest)
    assert summary["candidate_conditions"] == 1
    assert summary["warmup_satisfied_core_candidates"] == 0


def test_late_oracle_start_does_not_pass_warmup(tmp_path):
    root, digest = fixture_bundle(tmp_path, oracle_start=MARKET - 200)
    summary = inspect(tmp_path, root, digest)
    assert summary["candidate_conditions"] == 1
    assert summary["warmup_satisfied_core_candidates"] == 0


@pytest.mark.parametrize("target", ["oracle", "wallet"])
def test_modified_child_raw_bytes_fail_before_output(tmp_path, target):
    root, digest = fixture_bundle(tmp_path)
    path = (root / "chainlink" / "chainlink_twap_raw.jsonl" if target == "oracle"
            else root / "wallet" / "live_activity.jsonl")
    with path.open("ab") as handle:
        handle.write(b"{}\n")
    with pytest.raises(ValueError, match="artifact mismatch"):
        inspect(tmp_path, root, digest)
    assert not (tmp_path / "intake").exists()


def test_foreign_capture_schema_cannot_enter_v5(tmp_path):
    root, digest = fixture_bundle(tmp_path)
    path = root / "cross_asset_capture_manifest.json"
    manifest = json.loads(path.read_text())
    manifest["feed_protocol"] = "rtds"
    write_json(path, manifest)
    with pytest.raises(ValueError, match="amended v5"):
        inspect(tmp_path, root, sha(path))
