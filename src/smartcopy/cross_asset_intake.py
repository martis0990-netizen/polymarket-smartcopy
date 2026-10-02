"""Fail-closed provenance and warm-up check for a prospective v5 capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

_SCHEMA = "smartcopy-bonereaper-cross-asset-intake-v1"
_CAPTURE_SCHEMA = "smartcopy-bonereaper-cross-asset-capture-v2"
_CONTRACT = "a696cf068dcb5b4555073d1d5636eec7efa05050"
_AMENDMENT = "0dd7a371b13f278383f1d81eba44bf88fbb6c3cc"
_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_SYMBOLS = ("btc/usd", "eth/usd", "sol/usd", "xrp/usd", "bnb/usd", "doge/usd", "hype/usd")
_CORE = frozenset(("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE"))
_SLUG = re.compile(r"^(btc|eth|sol|xrp|bnb|doge|hype)-updown-(5m|15m)-(\d+)$")
_SHA = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def inspect_v5_capture(*, bundle_dir: str | Path, expected_manifest_sha256: str,
                       output_dir: str | Path, code_commit: str) -> dict[str, Any]:
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    if _SHA.fullmatch(expected_manifest_sha256) is None:
        raise ValueError("expected capture manifest SHA256 must be lowercase hex")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing intake directory: {output}")
    root = Path(bundle_dir)
    manifest_path = root / "cross_asset_capture_manifest.json"
    manifest = _bound_json(manifest_path, expected_manifest_sha256)
    if (manifest.get("schema_version") != _CAPTURE_SCHEMA
            or manifest.get("contract_commit") != _CONTRACT
            or manifest.get("transport_amendment_commit") != _AMENDMENT
            or manifest.get("feed_protocol") != "polybolt-v1"
            or manifest.get("clean_finalize") is not True
            or manifest.get("wallet") != _WALLET
            or manifest.get("symbols") != list(_SYMBOLS)):
        raise ValueError("capture is not a clean amended v5 bundle")
    started = _millis(manifest.get("started_at"))
    ended = _millis(manifest.get("ended_at"))
    if ended - started < 960_000 or not 960 <= manifest.get("requested_duration_seconds", 0) <= 14_400:
        raise ValueError("v5 capture did not run for the minimum duration")

    oracle_binding = manifest["chainlink"]
    wallet_binding = manifest["wallet_observer"]
    oracle_dir, wallet_dir = root / "chainlink", root / "wallet"
    oracle = _bound_json(oracle_dir / "chainlink_twap_manifest.json", oracle_binding["sha256"])
    wallet = _bound_json(wallet_dir / "observer_manifest.json", wallet_binding["sha256"])
    if (oracle.get("feed_protocol") != "polybolt-v1" or oracle.get("clean_finalize") is not True
            or oracle.get("symbols") != list(_SYMBOLS)
            or oracle.get("reconnect_count") != 0 or wallet.get("gap_failures") != 0):
        raise ValueError("capture child did not cleanly finalize")
    _verify_artifacts(oracle_dir, oracle)
    _verify_artifacts(wallet_dir, wallet)
    if (oracle_dir / "chainlink_twap_gaps.jsonl").stat().st_size:
        raise ValueError("v5 amended transport cannot have a gap artifact")

    first_live: dict[str, int] = {}
    counts: Counter[str] = Counter()
    last_source: dict[str, int] = {}
    last_seq = 0
    snapshots: set[str] = set()
    for row in _jsonl(oracle_dir / "chainlink_twap_raw.jsonl"):
        raw = row.get("raw")
        if not isinstance(raw, dict) or raw.get("channel") != "price.crypto.twap":
            raise ValueError("unexpected TWAP frame")
        seq = raw.get("seq")
        if type(seq) is not int or seq != last_seq + 1 or raw.get("dropped", 0) != 0:
            raise ValueError("TWAP channel sequence is incomplete")
        last_seq = seq
        if row.get("kind") == "snapshot":
            payload = raw.get("payload")
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ValueError("malformed TWAP snapshot")
            wire_symbol = payload.get("symbol")
            symbol = _symbol(wire_symbol)
            if symbol in snapshots:
                raise ValueError("duplicate TWAP snapshot")
            snapshots.add(symbol)
            continue
        if row.get("kind") != "live" or raw.get("snapshot") is True:
            raise ValueError("TWAP raw frame must be live or snapshot")
        event = row.get("normalized")
        if not isinstance(event, dict) or event.get("feed_protocol") != "polybolt-v1":
            raise ValueError("missing PolyBolt normalization")
        symbol = _symbol(event.get("symbol"))
        payload = raw.get("payload")
        if (not isinstance(payload, dict) or _symbol(payload.get("symbol")) != symbol
                or payload.get("timestamp") != event.get("source_timestamp_ms")
                or payload.get("window_seconds") != 60
                or str(payload.get("full_accuracy_value", payload.get("value"))) != event.get("full_accuracy_value")):
            raise ValueError("TWAP raw payload differs from normalized event")
        if symbol not in snapshots or event.get("channel_seq") != seq:
            raise ValueError("live TWAP predates its snapshot or has wrong sequence")
        source = event.get("source_timestamp_ms")
        if type(source) is not int or source <= last_source.get(symbol, 0):
            raise ValueError("TWAP source time repeated or regressed")
        receive = _millis(event.get("receive_timestamp"))
        if receive < source:
            raise ValueError("TWAP receive time predates producer time")
        last_source[symbol] = source
        first_live.setdefault(symbol, receive)
        counts[symbol] += 1
    if (snapshots != set(_SYMBOLS) or set(counts) != set(_SYMBOLS)
            or dict(counts) != oracle["event_counts"]
            or dict(counts) != oracle_binding["event_counts"]):
        raise ValueError("TWAP stream counts or symbol coverage do not match manifests")

    cycles = list(_jsonl(wallet_dir / "poll_cycles.jsonl"))
    if not cycles or cycles[0].get("baseline") is not True:
        raise ValueError("wallet capture lacks an initial baseline poll")
    wallet_ready = _millis(cycles[0].get("finished_at"))
    activity_path = wallet_dir / "live_activity.jsonl"
    raw_candidates: dict[str, list[dict[str, Any]]] = defaultdict(list)
    all_wallet_rows = 0
    for row in _jsonl(activity_path):
        all_wallet_rows += 1
        if (row.get("proxy_wallet") != _WALLET or row.get("observation_mode") != "live_observed"
                or row.get("activity_type") != "TRADE"):
            raise ValueError("wallet activity identity or observation mode mismatch")
        observed = _millis(row.get("first_observed_time"))
        source = _millis(row.get("source_event_time"))
        if observed < source:
            raise ValueError("wallet trade observed before its source event")
        match = _SLUG.fullmatch(str(row.get("slug", "")))
        if row.get("side") != "BUY" or match is None:
            continue
        asset, horizon, market_start_text = match.groups()
        market_start = int(market_start_text)
        if not (market_start - 60 <= source // 1_000 < market_start):
            continue
        if row.get("outcome") not in {"Up", "Down"}:
            raise ValueError("candidate BUY has no unambiguous outcome")
        raw_candidates[str(row["condition_id"])].append({
            "slug": row["slug"], "asset": asset.upper(), "horizon": horizon,
            "market_start": market_start, "source_second": source // 1_000,
        })
    if all_wallet_rows != wallet.get("emitted_prospective_row_count") or all_wallet_rows != wallet_binding["prospective_rows"]:
        raise ValueError("wallet activity count does not match manifests")

    candidates = []
    for condition_id, rows in sorted(raw_candidates.items()):
        first = rows[0]
        if any((row["slug"], row["asset"], row["horizon"]) !=
               (first["slug"], first["asset"], first["horizon"]) for row in rows):
            raise ValueError("conflicting condition metadata")
        start_ms = first["market_start"] * 1_000
        symbol = first["asset"].lower() + "/usd"
        candidates.append({
            "condition_id": condition_id, "slug": first["slug"],
            "asset": first["asset"], "horizon": first["horizon"],
            "market_start": first["market_start"],
            "preopen_buy_rows": len(rows),
            "earliest_buy_second": min(row["source_second"] for row in rows),
            "cohort": "CORE" if first["asset"] in _CORE else "HYPE_ENGINEERING",
            "capture_warmup_satisfied": (first_live[symbol] <= start_ms - 660_000
                                         and wallet_ready <= start_ms - 660_000
                                         and ended >= start_ms),
            "receipt_label_status": "PENDING_FEE_AWARE_POLYGON_RECEIPT",
        })

    output.mkdir(parents=True)
    candidate_path = output / "preopen_buy_candidates.jsonl"
    candidate_path.write_bytes(b"".join(_line(row) for row in candidates))
    result = {
        "schema_version": _SCHEMA,
        "code_commit": code_commit,
        "capture_manifest_sha256": expected_manifest_sha256,
        "wallet_activity_sha256": _sha256(activity_path),
        "wallet_rows": all_wallet_rows,
        "first_live_receive_ms": first_live,
        "wallet_baseline_finished_ms": wallet_ready,
        "candidate_conditions": len(candidates),
        "warmup_satisfied_core_candidates": sum(row["cohort"] == "CORE" and row["capture_warmup_satisfied"] for row in candidates),
        "confirmed_labels": 0,
        "artifacts": {candidate_path.name: {"bytes": candidate_path.stat().st_size, "sha256": _sha256(candidate_path)}},
    }
    (output / "cross_asset_intake_manifest.json").write_bytes(_line(result))
    return result


def _symbol(value: Any) -> str:
    if value not in _SYMBOLS:
        # Wire format uses btcusd; normalized format uses btc/usd.
        if isinstance(value, str) and value.endswith("usd"):
            value = value[:-3] + "/usd"
    if value not in _SYMBOLS:
        raise ValueError("unexpected TWAP symbol")
    return value


def _bound_json(path: Path, digest: str) -> dict[str, Any]:
    if not isinstance(digest, str) or _SHA.fullmatch(digest) is None or _sha256(path) != digest:
        raise ValueError(f"SHA256 mismatch: {path.name}")
    value = json.loads(path.read_bytes())
    if not isinstance(value, dict):
        raise ValueError("manifest must be an object")
    return value


def _verify_artifacts(directory: Path, manifest: dict[str, Any]) -> None:
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ValueError("child has no artifacts")
    for name, binding in artifacts.items():
        if not isinstance(name, str) or Path(name).name != name or not isinstance(binding, dict):
            raise ValueError("unsafe artifact binding")
        path = directory / name
        if path.stat().st_size != binding.get("bytes") or _sha256(path) != binding.get("sha256"):
            raise ValueError(f"artifact mismatch: {name}")


def _jsonl(path: Path):
    with path.open("rb") as handle:
        for number, line in enumerate(handle, start=1):
            try:
                value = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise ValueError(f"invalid JSONL {path.name}:{number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"JSONL row must be an object: {path.name}:{number}")
            yield value


def _millis(value: Any) -> int:
    if not isinstance(value, str):
        raise ValueError("timestamp must be ISO-8601")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must carry a timezone")
    return int(parsed.astimezone(timezone.utc).timestamp() * 1_000)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _line(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--expected-manifest-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args(argv)
    result = inspect_v5_capture(
        bundle_dir=args.bundle_dir,
        expected_manifest_sha256=args.expected_manifest_sha256,
        output_dir=args.output_dir,
        code_commit=args.code_commit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
