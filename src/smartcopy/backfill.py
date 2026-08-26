"""Deterministic historical wallet-activity backfill artifacts.

This module is deliberately small: it turns a *proven complete* timestamp-range response
from :mod:`smartcopy.polymarket` into immutable local evidence files plus a manifest. It
never observes live wallets, never estimates latency, and never makes a copy decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Sequence

from .models import ObservationMode, WalletActivity
from .polymarket import PolymarketDataAPI


Clock = Callable[[], datetime]
_WALLET_RE = re.compile(r"^0x[a-fA-F0-9]{40}$")
_SOURCE_ROWS = "activity_source_rows.jsonl"
_NORMALIZED_ROWS = "activity_normalized.jsonl"
_MANIFEST = "backfill_manifest.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _normalize_wallet(value: str) -> str:
    if not _WALLET_RE.fullmatch(value):
        raise ValueError("wallet must be a 0x-prefixed 40-hex address")
    return value.lower()


def _json_line(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _normalized_activity(item: WalletActivity) -> dict[str, Any]:
    return {
        "proxy_wallet": item.proxy_wallet,
        "source_event_time": _iso(item.source_event_time),
        "first_observed_time": _iso(item.first_observed_time),
        "observation_mode": item.observation_mode.value,
        "condition_id": item.condition_id,
        "activity_type": item.activity_type,
        "side": item.side,
        "size": item.size,
        "usdc_size": item.usdc_size,
        "price": item.price,
        "asset": item.asset,
        "transaction_hash": item.transaction_hash,
        "title": item.title,
        "slug": item.slug,
        "event_slug": item.event_slug,
        "outcome": item.outcome,
    }


def _write_jsonl(path: Path, rows: Sequence[Any]) -> None:
    with path.open("xb") as handle:
        for row in rows:
            handle.write(_json_line(row))
        handle.flush()


def _artifact_record(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return {"path": path.name, "bytes": size, "sha256": digest.hexdigest()}


def write_activity_backfill(
    *,
    client: PolymarketDataAPI,
    wallet: str,
    start: int,
    end: int,
    output_dir: str | Path,
    page_size: int = 500,
    max_split_depth: int = 24,
    clock: Clock = _utc_now,
) -> dict[str, Any]:
    """Collect one complete historical range and materialize immutable evidence.

    Existing evidence files are rejected before network collection begins. If range
    completeness cannot be proven, ``collect_activity_range`` raises and this function
    leaves no success-looking manifest behind.
    """

    normalized_wallet = _normalize_wallet(wallet)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    source_path = root / _SOURCE_ROWS
    normalized_path = root / _NORMALIZED_ROWS
    manifest_path = root / _MANIFEST
    for target in (source_path, normalized_path, manifest_path):
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing backfill artifact: {target}")

    generated_at = clock()
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("backfill manifest clock must be timezone-aware")

    history = client.collect_activity_range(
        normalized_wallet,
        start=start,
        end=end,
        page_size=page_size,
        max_split_depth=max_split_depth,
    )
    if any(item.observation_mode != ObservationMode.BACKFILL for item in history):
        raise ValueError("historical backfill contains non-BACKFILL observation mode")

    _write_jsonl(source_path, [item.raw for item in history])
    _write_jsonl(normalized_path, [_normalized_activity(item) for item in history])

    manifest: dict[str, Any] = {
        "schema_version": "smartcopy-activity-backfill-v1",
        "wallet": normalized_wallet,
        "range": {"start": start, "end": end},
        "source": "https://data-api.polymarket.com/activity",
        "completeness": "PROVEN_WITHIN_REQUESTED_RANGE",
        "observation_mode": ObservationMode.BACKFILL.value,
        "row_count": len(history),
        "first_source_event_time": _iso(history[0].source_event_time) if history else None,
        "last_source_event_time": _iso(history[-1].source_event_time) if history else None,
        "generated_at": _iso(generated_at),
        "page_size": page_size,
        "max_split_depth": max_split_depth,
        "artifacts": [
            _artifact_record(source_path),
            _artifact_record(normalized_path),
        ],
    }
    with manifest_path.open("xb") as handle:
        handle.write(_json_line(manifest))
        handle.flush()
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write a complete SmartCopy wallet activity backfill")
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--start", required=True, type=int, help="inclusive Unix second")
    parser.add_argument("--end", required=True, type=int, help="inclusive Unix second")
    parser.add_argument("--output", required=True)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--max-split-depth", type=int, default=24)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    manifest = write_activity_backfill(
        client=PolymarketDataAPI(),
        wallet=args.wallet,
        start=args.start,
        end=args.end,
        output_dir=args.output,
        page_size=args.page_size,
        max_split_depth=args.max_split_depth,
    )
    print(json.dumps(manifest, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
