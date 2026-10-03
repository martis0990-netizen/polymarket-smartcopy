"""Stage 2P-B frozen historical settlement decomposition.

This is outcome accounting over already-observed historical evidence. It does not
estimate live copyability, causal skill, or net wallet PnL.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Sequence

from .historical import load_normalized_activity_jsonl
from .models import ObservationMode, WalletActivity
from .polymarket import PolymarketDataAPI

FROZEN_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
FROZEN_STAGE2H_SHA256 = "90bd0ebaad300545f2f9aab2ef713ac40d33eb26ec3da42bd6dc0fbe8669d0f7"
FROZEN_STAGE2P_A_SHA256 = "6e34113cd17665caa7d333ab35cb49b9beb989ba5c18f5054d438bcc4ce2c10b"
GRACE_START = 1787702400
GRACE_END = 1787875199
GRACE_TYPES = "REDEEM,SPLIT,MERGE"
SETTLEMENT_TOLERANCE = 0.0001
_SCHEMA = "smartcopy-stage2p-b-settlement-decomposition-v1"

_GRACE_RAW = "stage2p_b_grace_raw.jsonl"
_GRACE_NORMALIZED = "stage2p_b_grace_normalized.jsonl"
_MARKETS = "stage2p_b_markets.jsonl"
_SUMMARY = "stage2p_b_summary.json"


class SettlementEvidenceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class SettlementMarket:
    condition_id: str
    symbol: str
    market_family: str
    status: str
    reason: str
    buy_outflow: float
    redeem_inflow: float
    matched_size: float
    excess_size: float
    matched_cost: float | None
    excess_cost: float | None
    gross_settlement_cashflow: float | None
    matched_pair_cashflow: float | None
    excess_directional_payout: float | None
    excess_directional_cashflow: float | None
    reconciliation_error: float | None
    settlement_state: str | None
    same_day_redeem_rows: int
    grace_redeem_rows: int
    split_rows: int
    merge_rows: int


def write_settlement_decomposition(
    *,
    client: PolymarketDataAPI,
    stage2h_markets_path: str | Path,
    stage2p_a_activity_path: str | Path,
    output_dir: str | Path,
    expected_stage2h_sha256: str = FROZEN_STAGE2H_SHA256,
    expected_stage2p_a_sha256: str = FROZEN_STAGE2P_A_SHA256,
) -> dict[str, Any]:
    stage2h_path = Path(stage2h_markets_path)
    stage2p_a_path = Path(stage2p_a_activity_path)
    if _sha256(stage2h_path) != expected_stage2h_sha256:
        raise SettlementEvidenceError("Stage 2H markets SHA256 mismatch")
    if _sha256(stage2p_a_path) != expected_stage2p_a_sha256:
        raise SettlementEvidenceError("Stage 2P-A activity SHA256 mismatch")

    market_rows = _load_stage2h_markets(stage2h_path)
    if len(market_rows) != 763:
        raise SettlementEvidenceError(f"expected 763 Stage 2H markets, got {len(market_rows)}")
    target_ids = {str(row["condition_id"]) for row in market_rows}

    same_day = load_normalized_activity_jsonl(stage2p_a_path)
    _validate_activity(same_day, allowed={"REDEEM", "REWARD", "MAKER_REBATE", "TAKER_REBATE", "SPLIT", "MERGE"})

    grace = client.collect_activity_range(
        FROZEN_WALLET,
        start=GRACE_START,
        end=GRACE_END,
        activity_type=GRACE_TYPES,
    )
    _validate_activity(grace, allowed={"REDEEM", "SPLIT", "MERGE"}, start=GRACE_START, end=GRACE_END)

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    grace_raw = root / _GRACE_RAW
    grace_normalized = root / _GRACE_NORMALIZED
    markets_path = root / _MARKETS
    summary_path = root / _SUMMARY
    for path in (grace_raw, grace_normalized, markets_path, summary_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite existing Stage 2P-B artifact: {path}")

    _write_jsonl(grace_raw, (item.raw for item in grace))
    _write_jsonl(grace_normalized, (_normalized(item) for item in grace))

    same_settlement = [item for item in same_day if item.activity_type in {"REDEEM", "SPLIT", "MERGE"}]
    combined = tuple(same_settlement) + tuple(grace)
    records = tuple(_decompose_market(row, same_day=same_settlement, grace=grace, combined=combined) for row in market_rows)

    with markets_path.open("xb") as handle:
        for record in records:
            handle.write(_json_line(_record_dict(record)))
        handle.flush()

    summary = _build_summary(records, same_day=same_day, grace=grace, target_ids=target_ids)
    summary["inputs"] = {
        "stage2h_markets": {"sha256": expected_stage2h_sha256, "bytes": stage2h_path.stat().st_size},
        "stage2p_a_activity": {"sha256": expected_stage2p_a_sha256, "bytes": stage2p_a_path.stat().st_size},
    }
    summary["grace"] = {
        "start": GRACE_START,
        "end": GRACE_END,
        "types": GRACE_TYPES.split(","),
        "raw": _artifact_record(grace_raw),
        "normalized": _artifact_record(grace_normalized),
    }
    summary["artifacts"] = {"markets": _artifact_record(markets_path)}
    with summary_path.open("xb") as handle:
        handle.write(_json_line(summary))
        handle.flush()
    return summary


def _decompose_market(
    market: dict[str, Any],
    *,
    same_day: Sequence[WalletActivity],
    grace: Sequence[WalletActivity],
    combined: Sequence[WalletActivity],
) -> SettlementMarket:
    condition = str(market["condition_id"])
    same_rows = [item for item in same_day if item.condition_id == condition]
    grace_rows = [item for item in grace if item.condition_id == condition]
    rows = [item for item in combined if item.condition_id == condition]
    redeems = [item for item in rows if item.activity_type == "REDEEM"]
    splits = [item for item in rows if item.activity_type == "SPLIT"]
    merges = [item for item in rows if item.activity_type == "MERGE"]

    up = market["up"]
    down = market["down"]
    up_size = float(up["total_size"])
    down_size = float(down["total_size"])
    buy_outflow = float(up["total_usdc"]) + float(down["total_usdc"])
    matched_size = float(market["matched_size"])
    excess_up = float(market["excess_up"])
    excess_down = float(market["excess_down"])
    excess_size = excess_up + excess_down
    matched_cost = _optional_float(market.get("matched_average_cost"))
    excess_cost = _excess_cost(excess_up, excess_down, up.get("vwap_price"), down.get("vwap_price"))
    redeem_inflow = sum(item.usdc_size for item in redeems)

    base = dict(
        condition_id=condition,
        symbol=str(market["symbol"]),
        market_family=str(market["market_family"]),
        buy_outflow=buy_outflow,
        redeem_inflow=redeem_inflow,
        matched_size=matched_size,
        excess_size=excess_size,
        matched_cost=matched_cost,
        excess_cost=excess_cost,
        same_day_redeem_rows=sum(item.activity_type == "REDEEM" for item in same_rows),
        grace_redeem_rows=sum(item.activity_type == "REDEEM" for item in grace_rows),
        split_rows=len(splits),
        merge_rows=len(merges),
    )

    if splits or merges:
        return SettlementMarket(status="TRANSFORMED_EXCLUDED", reason="SPLIT/MERGE evidence present", gross_settlement_cashflow=None, matched_pair_cashflow=None, excess_directional_payout=None, excess_directional_cashflow=None, reconciliation_error=None, settlement_state=None, **base)
    if not redeems:
        return SettlementMarket(status="UNRESOLVED_IN_FROZEN_EVIDENCE", reason="no REDEEM evidence in same-day or frozen grace window", gross_settlement_cashflow=None, matched_pair_cashflow=None, excess_directional_payout=None, excess_directional_cashflow=None, reconciliation_error=None, settlement_state=None, **base)
    if matched_size > 0 and matched_cost is None:
        return SettlementMarket(status="MISSING_COST_FIELDS", reason="matched inventory lacks average cost", gross_settlement_cashflow=None, matched_pair_cashflow=None, excess_directional_payout=None, excess_directional_cashflow=None, reconciliation_error=None, settlement_state=None, **base)
    if excess_size > 0 and excess_cost is None:
        return SettlementMarket(status="MISSING_COST_FIELDS", reason="excess inventory lacks VWAP cost", gross_settlement_cashflow=None, matched_pair_cashflow=None, excess_directional_payout=None, excess_directional_cashflow=None, reconciliation_error=None, settlement_state=None, **base)

    last_buy = _last_buy_time(market)
    first_redeem = min(item.source_event_time for item in redeems)
    if last_buy is not None and last_buy > first_redeem:
        return SettlementMarket(status="TEMPORAL_INCONSISTENCY", reason="BUY evidence occurs after first REDEEM", gross_settlement_cashflow=None, matched_pair_cashflow=None, excess_directional_payout=None, excess_directional_cashflow=None, reconciliation_error=None, settlement_state=None, **base)

    lose_payout = matched_size
    win_payout = matched_size + excess_size
    if abs(redeem_inflow - lose_payout) <= SETTLEMENT_TOLERANCE:
        settlement_state = "EXCESS_LOST" if excess_size > SETTLEMENT_TOLERANCE else "PAIRED_ONLY"
    elif abs(redeem_inflow - win_payout) <= SETTLEMENT_TOLERANCE:
        settlement_state = "EXCESS_WON" if excess_size > SETTLEMENT_TOLERANCE else "PAIRED_ONLY"
    else:
        return SettlementMarket(status="INCOMPLETE_OR_INCONSISTENT_REDEMPTION", reason="redeem payout is not a frozen binary settlement state", gross_settlement_cashflow=None, matched_pair_cashflow=None, excess_directional_payout=None, excess_directional_cashflow=None, reconciliation_error=None, settlement_state=None, **base)

    matched_cost_value = matched_cost or 0.0
    excess_cost_value = excess_cost or 0.0
    gross = redeem_inflow - buy_outflow
    matched_cash = matched_size - matched_cost_value
    excess_payout = redeem_inflow - matched_size
    excess_cash = excess_payout - excess_cost_value
    reconciliation = gross - (matched_cash + excess_cash)
    return SettlementMarket(
        status="SIMPLE_SETTLEMENT_ELIGIBLE",
        reason="frozen settlement and transform checks passed",
        gross_settlement_cashflow=gross,
        matched_pair_cashflow=matched_cash,
        excess_directional_payout=excess_payout,
        excess_directional_cashflow=excess_cash,
        reconciliation_error=reconciliation,
        settlement_state=settlement_state,
        **base,
    )


def _build_summary(
    records: Sequence[SettlementMarket],
    *,
    same_day: Sequence[WalletActivity],
    grace: Sequence[WalletActivity],
    target_ids: set[str],
) -> dict[str, Any]:
    eligible = [row for row in records if row.status == "SIMPLE_SETTLEMENT_ELIGIBLE"]
    same_redeem_ids = {item.condition_id for item in same_day if item.activity_type == "REDEEM" and item.condition_id in target_ids}
    grace_redeem_ids = {item.condition_id for item in grace if item.activity_type == "REDEEM" and item.condition_id in target_ids}
    combined_redeem = same_redeem_ids | grace_redeem_ids
    transformed = [row for row in records if row.status == "TRANSFORMED_EXCLUDED"]
    incomplete = [row for row in records if row.status == "INCOMPLETE_OR_INCONSISTENT_REDEMPTION"]
    unresolved = [row for row in records if row.status == "UNRESOLVED_IN_FROZEN_EVIDENCE"]
    other_bad = [row for row in records if row.status in {"MISSING_COST_FIELDS", "TEMPORAL_INCONSISTENCY"}]
    errors = [abs(row.reconciliation_error or 0.0) for row in eligible]
    reconciliation_ok = all(error <= SETTLEMENT_TOLERANCE for error in errors)

    if not reconciliation_ok or other_bad:
        verdict = "DATA_INSUFFICIENT"
    elif len(eligible) == len(records):
        verdict = "SETTLEMENT_DECOMPOSITION_RECONCILED"
    else:
        verdict = "SETTLEMENT_DECOMPOSITION_PARTIAL"

    matched_values = [float(row.matched_pair_cashflow) for row in eligible if row.matched_pair_cashflow is not None]
    excess_values = [float(row.excess_directional_cashflow) for row in eligible if row.excess_directional_cashflow is not None]
    matched_positive = sum(value > 0 for value in matched_values)
    excess_positive = sum(value > 0 for value in excess_values)
    excess_won = sum(row.settlement_state == "EXCESS_WON" for row in eligible)

    def incentive(kind: str) -> float:
        return sum(item.usdc_size for item in same_day if item.activity_type == kind)

    return {
        "schema_version": _SCHEMA,
        "verdict": verdict,
        "interpretation": "HISTORICAL_GROSS_SETTLEMENT_ACCOUNTING_NOT_NET_PNL",
        "settlement_tolerance": SETTLEMENT_TOLERANCE,
        "target_market_count": len(records),
        "same_day_redeem_coverage": len(same_redeem_ids),
        "grace_redeem_coverage": len(grace_redeem_ids),
        "combined_redeem_coverage": len(combined_redeem),
        "simple_settlement_eligible_count": len(eligible),
        "simple_settlement_eligible_share": len(eligible) / len(records),
        "transformed_excluded_count": len(transformed),
        "incomplete_inconsistent_redemption_count": len(incomplete),
        "unresolved_after_grace_count": len(unresolved),
        "other_data_integrity_exclusion_count": len(other_bad),
        "eligible_buy_outflow_total": sum(row.buy_outflow for row in eligible),
        "eligible_redeem_inflow_total": sum(row.redeem_inflow for row in eligible),
        "eligible_gross_settlement_cashflow_total": sum(float(row.gross_settlement_cashflow) for row in eligible),
        "matched_pair_cashflow_total": sum(matched_values),
        "excess_directional_cashflow_total": sum(excess_values),
        "absolute_reconciliation_error_total": sum(errors),
        "max_per_market_reconciliation_error": max(errors) if errors else 0.0,
        "matched_pair_positive_count": matched_positive,
        "matched_pair_positive_share": matched_positive / len(matched_values) if matched_values else None,
        "excess_directional_positive_count": excess_positive,
        "excess_directional_positive_share": excess_positive / len(excess_values) if excess_values else None,
        "median_matched_pair_cashflow": median(matched_values) if matched_values else None,
        "median_excess_directional_cashflow": median(excess_values) if excess_values else None,
        "excess_leg_won_count": excess_won,
        "excess_leg_won_share": excess_won / len(eligible) if eligible else None,
        "unallocated_wallet_incentive_activity": {
            "reward_usdc": incentive("REWARD"),
            "maker_rebate_usdc": incentive("MAKER_REBATE"),
            "taker_rebate_usdc": incentive("TAKER_REBATE"),
        },
        "status_counts": _status_counts(records),
    }


def _validate_activity(
    rows: Sequence[WalletActivity],
    *,
    allowed: set[str],
    start: int | None = None,
    end: int | None = None,
) -> None:
    for item in rows:
        if item.proxy_wallet != FROZEN_WALLET:
            raise SettlementEvidenceError("activity wallet mismatch")
        if item.observation_mode != ObservationMode.BACKFILL:
            raise SettlementEvidenceError("settlement evidence must be BACKFILL")
        if item.activity_type not in allowed:
            raise SettlementEvidenceError(f"unexpected settlement activity type: {item.activity_type}")
        timestamp = int(item.source_event_time.timestamp())
        if start is not None and timestamp < start:
            raise SettlementEvidenceError("grace activity before frozen start")
        if end is not None and timestamp > end:
            raise SettlementEvidenceError("grace activity after frozen end")


def _load_stage2h_markets(path: Path) -> list[dict[str, Any]]:
    rows = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception as exc:
                raise SettlementEvidenceError(f"invalid Stage 2H market row {line_number}: {exc}") from exc
    return rows


def _excess_cost(excess_up: float, excess_down: float, up_vwap: Any, down_vwap: Any) -> float | None:
    total = 0.0
    if excess_up > 0:
        if up_vwap is None:
            return None
        total += excess_up * float(up_vwap)
    if excess_down > 0:
        if down_vwap is None:
            return None
        total += excess_down * float(down_vwap)
    return total


def _last_buy_time(market: dict[str, Any]) -> datetime | None:
    values = []
    for leg in (market["up"], market["down"]):
        raw = leg.get("last_source_event_time")
        if raw:
            values.append(_parse_iso(raw))
    return max(values) if values else None


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SettlementEvidenceError("source timestamp must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


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


def _record_dict(record: SettlementMarket) -> dict[str, Any]:
    return {field: getattr(record, field) for field in record.__dataclass_fields__}


def _status_counts(records: Sequence[SettlementMarket]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in records:
        counts[row.status] = counts.get(row.status, 0) + 1
    return dict(sorted(counts.items()))


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    with path.open("xb") as handle:
        for row in rows:
            handle.write(_json_line(row))
        handle.flush()


def _json_line(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("utf-8")


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
    parser = argparse.ArgumentParser(description="Run frozen SmartCopy Stage 2P-B settlement decomposition")
    parser.add_argument("--stage2h-markets", required=True)
    parser.add_argument("--stage2p-a-activity", required=True)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_settlement_decomposition(
        client=PolymarketDataAPI(),
        stage2h_markets_path=args.stage2h_markets,
        stage2p_a_activity_path=args.stage2p_a_activity,
        output_dir=args.output,
    )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
