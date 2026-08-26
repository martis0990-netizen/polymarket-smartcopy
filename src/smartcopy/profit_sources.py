"""Stage 2P-A public non-TRADE activity sufficiency evidence.

This module proves what public activity fields are observable for a frozen wallet/day.
It deliberately does not calculate profit or infer reward causality.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from .models import ObservationMode, WalletActivity
from .polymarket import PolymarketDataAPI

FROZEN_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
FROZEN_START = 1787616000
FROZEN_END = 1787702399
FROZEN_TYPES = "REDEEM,REWARD,MAKER_REBATE,TAKER_REBATE,SPLIT,MERGE"
FROZEN_TYPE_SET = tuple(FROZEN_TYPES.split(","))
FROZEN_STAGE2H_MARKETS_SHA256 = "90bd0ebaad300545f2f9aab2ef713ac40d33eb26ec3da42bd6dc0fbe8669d0f7"
_SCHEMA = "smartcopy-stage2p-a-profit-source-sufficiency-v1"
_RAW = "stage2p_activity_raw.jsonl"
_NORMALIZED = "stage2p_activity_normalized.jsonl"
_SUMMARY = "stage2p_summary.json"

Clock = Callable[[], datetime]


class ProfitSourceEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class TypeSummary:
    row_count: int
    size_total: float
    usdc_size_total: float
    distinct_condition_ids: int
    distinct_transaction_hashes: int
    first_source_event_time: str | None
    last_source_event_time: str | None
    target_condition_row_count: int


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def write_profit_source_sufficiency(
    *,
    client: PolymarketDataAPI,
    target_markets_path: str | Path,
    output_dir: str | Path,
    wallet: str = FROZEN_WALLET,
    start: int = FROZEN_START,
    end: int = FROZEN_END,
    activity_types: str = FROZEN_TYPES,
    expected_target_markets_sha256: str = FROZEN_STAGE2H_MARKETS_SHA256,
    clock: Clock = _utc_now,
) -> dict[str, Any]:
    """Collect and materialize the frozen Stage 2P-A public activity evidence."""

    if wallet.lower() != FROZEN_WALLET:
        raise ProfitSourceEvidenceError("Stage 2P-A wallet differs from frozen wallet")
    if (start, end) != (FROZEN_START, FROZEN_END):
        raise ProfitSourceEvidenceError("Stage 2P-A timestamp range differs from frozen range")
    if activity_types != FROZEN_TYPES:
        raise ProfitSourceEvidenceError("Stage 2P-A activity type set differs from frozen contract")

    target_path = Path(target_markets_path)
    target_digest = _sha256(target_path)
    if target_digest != expected_target_markets_sha256:
        raise ProfitSourceEvidenceError(
            f"Stage 2H markets SHA256 mismatch: expected {expected_target_markets_sha256}, got {target_digest}"
        )
    target_conditions = _load_target_conditions(target_path)
    if len(target_conditions) != 763:
        raise ProfitSourceEvidenceError(f"expected 763 Stage 2H target conditions, got {len(target_conditions)}")

    generated_at = clock()
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ProfitSourceEvidenceError("manifest clock must be timezone-aware")

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    raw_path, normalized_path, summary_path = root / _RAW, root / _NORMALIZED, root / _SUMMARY
    for target in (raw_path, normalized_path, summary_path):
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing Stage 2P-A artifact: {target}")

    rows = client.collect_activity_range(
        wallet,
        start=start,
        end=end,
        activity_type=activity_types,
    )
    _validate_rows(rows, wallet=wallet, start=start, end=end)

    _write_jsonl(raw_path, (item.raw for item in rows))
    _write_jsonl(normalized_path, (_normalized(item) for item in rows))

    type_summaries = {activity_type: _summarize_type(rows, activity_type, target_conditions) for activity_type in FROZEN_TYPE_SET}
    requested_count = len(rows)
    target_overlap_count = sum(item.condition_id in target_conditions for item in rows if item.condition_id)
    redeem_target_conditions = {
        item.condition_id
        for item in rows
        if item.activity_type == "REDEEM" and item.condition_id in target_conditions
    }
    verdict = "PUBLIC_PROFIT_SOURCE_ACTIVITY_PRESENT" if requested_count else "PUBLIC_PROFIT_SOURCE_ACTIVITY_EMPTY"

    payload: dict[str, Any] = {
        "schema_version": _SCHEMA,
        "verdict": verdict,
        "wallet": wallet,
        "range": {"start": start, "end": end},
        "requested_types": list(FROZEN_TYPE_SET),
        "observation_mode": ObservationMode.BACKFILL.value,
        "completeness": "PROVEN_WITHIN_REQUESTED_RANGE",
        "generated_at": _iso(generated_at),
        "target_stage2h": {
            "market_count": len(target_conditions),
            "artifact_sha256": target_digest,
        },
        "total_requested_type_rows": requested_count,
        "target_condition_overlap_rows": target_overlap_count,
        "target_conditions_with_redeem": len(redeem_target_conditions),
        "target_conditions_with_redeem_share": len(redeem_target_conditions) / len(target_conditions),
        "redeem_usdc_total": type_summaries["REDEEM"].usdc_size_total,
        "redeem_target_usdc_total": sum(
            item.usdc_size
            for item in rows
            if item.activity_type == "REDEEM" and item.condition_id in target_conditions
        ),
        "reward_usdc_total": type_summaries["REWARD"].usdc_size_total,
        "maker_rebate_usdc_total": type_summaries["MAKER_REBATE"].usdc_size_total,
        "taker_rebate_usdc_total": type_summaries["TAKER_REBATE"].usdc_size_total,
        "split_size_total": type_summaries["SPLIT"].size_total,
        "merge_size_total": type_summaries["MERGE"].size_total,
        "by_type": {key: _type_summary_dict(value) for key, value in type_summaries.items()},
        "artifacts": {
            "raw": _artifact_record(raw_path),
            "normalized": _artifact_record(normalized_path),
        },
        "interpretation": "DATA_SUFFICIENCY_ONLY_NOT_PNL",
    }
    with summary_path.open("xb") as handle:
        handle.write(_json_line(payload))
        handle.flush()
    return payload


def _validate_rows(rows: Sequence[WalletActivity], *, wallet: str, start: int, end: int) -> None:
    allowed = set(FROZEN_TYPE_SET)
    for item in rows:
        if item.observation_mode != ObservationMode.BACKFILL:
            raise ProfitSourceEvidenceError("Stage 2P-A received non-BACKFILL activity")
        if item.proxy_wallet != wallet:
            raise ProfitSourceEvidenceError("Stage 2P-A row wallet mismatch")
        if item.activity_type not in allowed:
            raise ProfitSourceEvidenceError(f"unexpected activity type: {item.activity_type}")
        timestamp = int(item.source_event_time.timestamp())
        if not start <= timestamp <= end:
            raise ProfitSourceEvidenceError("Stage 2P-A row outside frozen interval")


def _load_target_conditions(path: Path) -> set[str]:
    conditions: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                condition_id = str(row["condition_id"])
            except Exception as exc:
                raise ProfitSourceEvidenceError(f"invalid Stage 2H market row {line_number}: {exc}") from exc
            if not condition_id:
                raise ProfitSourceEvidenceError(f"empty Stage 2H condition_id at line {line_number}")
            conditions.add(condition_id)
    return conditions


def _summarize_type(
    rows: Sequence[WalletActivity], activity_type: str, target_conditions: set[str]
) -> TypeSummary:
    selected = [item for item in rows if item.activity_type == activity_type]
    times = [item.source_event_time for item in selected]
    return TypeSummary(
        row_count=len(selected),
        size_total=sum(item.size for item in selected),
        usdc_size_total=sum(item.usdc_size for item in selected),
        distinct_condition_ids=len({item.condition_id for item in selected if item.condition_id}),
        distinct_transaction_hashes=len({item.transaction_hash for item in selected if item.transaction_hash}),
        first_source_event_time=_iso(min(times)) if times else None,
        last_source_event_time=_iso(max(times)) if times else None,
        target_condition_row_count=sum(item.condition_id in target_conditions for item in selected if item.condition_id),
    )


def _normalized(item: WalletActivity) -> dict[str, Any]:
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


def _type_summary_dict(value: TypeSummary) -> dict[str, Any]:
    return {
        "row_count": value.row_count,
        "size_total": value.size_total,
        "usdc_size_total": value.usdc_size_total,
        "distinct_condition_ids": value.distinct_condition_ids,
        "distinct_transaction_hashes": value.distinct_transaction_hashes,
        "first_source_event_time": value.first_source_event_time,
        "last_source_event_time": value.last_source_event_time,
        "target_condition_row_count": value.target_condition_row_count,
    }


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    with path.open("xb") as handle:
        for row in rows:
            handle.write(_json_line(row))
        handle.flush()


def _json_line(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_record(path: Path) -> dict[str, Any]:
    return {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run frozen SmartCopy Stage 2P-A public profit-source sufficiency test")
    parser.add_argument("--target-markets", required=True, help="frozen Stage 2H paired markets JSONL")
    parser.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_profit_source_sufficiency(
        client=PolymarketDataAPI(),
        target_markets_path=args.target_markets,
        output_dir=args.output,
    )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
