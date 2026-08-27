"""Frozen public lifecycle ledger for the first five prospective conditions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

from .models import ObservationMode, WalletActivity
from .polymarket import PolymarketDataAPI

_SCHEMA = "smartcopy-bonereaper-lifecycle-ledger-v1"
_CONTRACT_COMMIT = "cced633d551aa294cc458083009cb238b2e0a5a6"
_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_START = 1787841600
_END = 1787855700
_TYPES = "TRADE,SPLIT,MERGE,REDEEM"
_TYPE_SET = frozenset(_TYPES.split(","))
_ECONOMICS_SHA = "8c848d320e2cc53e931fb408d493166f7ccb784416a56bcc4e8bdfdb745fb32f"
_SETTLEMENT_SHA = "76e1dbae9cd9ef7708cde1976afa6ec13bc9018134483b87c5b91f9c599617b8"
_DECODED_SHA = "1cbbe07f740682e1f6542d1ed70d7d2b8b63a9099a3366382aa3e3b1bff2ab31"
_MICRO = Decimal("1000000")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class LifecycleLedgerError(RuntimeError):
    """Raised when lifecycle evidence violates the frozen contract."""


def build_ledgers(
    activity: Sequence[WalletActivity],
    *,
    target_conditions: dict[str, dict[str, Any]],
    captured_buy_sizes: dict[tuple[str, str], Decimal],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build outcome ledgers, condition summaries and capture-share comparisons."""

    accumulator: dict[tuple[str, str], dict[str, Decimal]] = {}
    condition_cash: dict[str, dict[str, Any]] = {}
    condition_counts: dict[str, defaultdict[str, int]] = {}
    for condition_id in target_conditions:
        condition_cash[condition_id] = {
            "buy": Decimal(0),
            "sell": Decimal(0),
            "split": Decimal(0),
            "merge": Decimal(0),
            "redeem": Decimal(0),
            "cash_complete": True,
        }
        condition_counts[condition_id] = defaultdict(int)
        for outcome in ("Up", "Down"):
            accumulator[(condition_id, outcome)] = {
                "buy_tokens": Decimal(0),
                "buy_usdc": Decimal(0),
                "sell_tokens": Decimal(0),
                "sell_usdc": Decimal(0),
                "split_tokens": Decimal(0),
                "merge_tokens": Decimal(0),
                "redeem_tokens": Decimal(0),
                "redeem_usdc": Decimal(0),
            }

    for item in activity:
        condition_id = item.condition_id.lower()
        if condition_id not in target_conditions:
            continue
        kind = item.activity_type
        condition_counts[condition_id][kind] += 1
        size = _raw_decimal(item, "size")
        usdc = _raw_decimal(item, "usdcSize", allow_missing=kind in {"SPLIT", "MERGE"})
        if kind in {"SPLIT", "MERGE"}:
            for outcome in ("Up", "Down"):
                accumulator[(condition_id, outcome)][f"{kind.lower()}_tokens"] += size
            if usdc is None:
                condition_cash[condition_id]["cash_complete"] = False
            else:
                condition_cash[condition_id][kind.lower()] += usdc
            continue
        outcome = str(item.outcome or "")
        if outcome not in {"Up", "Down"}:
            raise LifecycleLedgerError(f"target {kind} row has unsupported outcome")
        ledger = accumulator[(condition_id, outcome)]
        if kind == "TRADE":
            side = str(item.side or "").upper()
            if side not in {"BUY", "SELL"}:
                raise LifecycleLedgerError("target TRADE row requires BUY or SELL side")
            ledger[f"{side.lower()}_tokens"] += size
            ledger[f"{side.lower()}_usdc"] += _required(usdc, "TRADE usdcSize")
            condition_cash[condition_id][side.lower()] += _required(usdc, "TRADE usdcSize")
        elif kind == "REDEEM":
            ledger["redeem_tokens"] += size
            ledger["redeem_usdc"] += _required(usdc, "REDEEM usdcSize")
            condition_cash[condition_id]["redeem"] += _required(usdc, "REDEEM usdcSize")
        else:  # pragma: no cover - validated before entry
            raise LifecycleLedgerError(f"unsupported target activity type {kind}")

    ledgers: list[dict[str, Any]] = []
    comparisons: list[dict[str, Any]] = []
    summaries: list[dict[str, Any]] = []
    for condition_id, identity in sorted(target_conditions.items()):
        outcome_rows = []
        for outcome in ("Up", "Down"):
            values = accumulator[(condition_id, outcome)]
            pre_redeem = (
                values["buy_tokens"]
                + values["split_tokens"]
                - values["sell_tokens"]
                - values["merge_tokens"]
            )
            balance = pre_redeem - values["redeem_tokens"]
            row = {
                "schema_version": _SCHEMA,
                "condition_id": condition_id,
                "slug": identity["slug"],
                "winning_outcome": identity["winning_outcome"],
                "outcome": outcome,
                **{key: _text(value) for key, value in values.items()},
                "public_flow_delta_before_redeem": _text(pre_redeem),
                "post_redeem_flow_balance": _text(balance),
                "minimum_unexplained_inflow": _text(max(Decimal(0), -balance)),
            }
            ledgers.append(row)
            outcome_rows.append(row)
            captured = captured_buy_sizes.get((condition_id, outcome), Decimal(0))
            lifecycle = values["buy_tokens"]
            comparisons.append(
                {
                    "schema_version": _SCHEMA,
                    "condition_id": condition_id,
                    "slug": identity["slug"],
                    "outcome": outcome,
                    "captured_buy_size": _text(captured),
                    "lifecycle_buy_size": _text(lifecycle),
                    "capture_share": _ratio(captured, lifecycle),
                }
            )
        cash = condition_cash[condition_id]
        cash_flow = cash["sell"] + cash["merge"] + cash["redeem"] - cash["buy"] - cash["split"]
        summaries.append(
            {
                "schema_version": _SCHEMA,
                "condition_id": condition_id,
                "slug": identity["slug"],
                "winning_outcome": identity["winning_outcome"],
                "activity_counts": {kind: condition_counts[condition_id][kind] for kind in sorted(_TYPE_SET)},
                "trade_buy_usdc": _text(cash["buy"]),
                "trade_sell_usdc": _text(cash["sell"]),
                "split_usdc": _text(cash["split"]) if cash["cash_complete"] else None,
                "merge_usdc": _text(cash["merge"]) if cash["cash_complete"] else None,
                "redeem_usdc": _text(cash["redeem"]),
                "public_pre_fee_cash_flow": _text(cash_flow) if cash["cash_complete"] else None,
                "cash_reconciliation_complete": cash["cash_complete"],
                "post_redeem_flow_balance": {
                    row["outcome"]: row["post_redeem_flow_balance"] for row in outcome_rows
                },
            }
        )
    return ledgers, summaries, comparisons


def run_analysis(
    *,
    economics_conditions_path: str | Path,
    settlement_rows_path: str | Path,
    decoded_rows_path: str | Path,
    output_dir: str | Path,
    code_commit: str,
    client: PolymarketDataAPI | None = None,
) -> dict[str, Any]:
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing analysis directory: {output}")
    economics_path = Path(economics_conditions_path)
    settlement_path = Path(settlement_rows_path)
    decoded_path = Path(decoded_rows_path)
    _require_sha(economics_path, _ECONOMICS_SHA, "economics conditions")
    _require_sha(settlement_path, _SETTLEMENT_SHA, "settlement rows")
    _require_sha(decoded_path, _DECODED_SHA, "decoded receipt rows")

    economics = _load_jsonl(economics_path)
    settlements = _load_jsonl(settlement_path)
    decoded = _load_jsonl(decoded_path)
    targets = _target_identities(economics, settlements)
    captured = _captured_buy_sizes(decoded, targets)

    activity_client = client or PolymarketDataAPI()
    activity = activity_client.collect_activity_range(
        _WALLET, start=_START, end=_END, activity_type=_TYPES
    )
    _validate_activity(activity)
    target_activity = [item for item in activity if item.condition_id.lower() in targets]
    ledgers, summaries, comparisons = build_ledgers(
        target_activity, target_conditions=targets, captured_buy_sizes=captured
    )
    aggregate = _aggregate(activity, target_activity, ledgers, summaries, comparisons)

    output.mkdir(parents=True)
    raw_path = output / "activity_all_raw.jsonl"
    target_path = output / "target_activity.jsonl"
    ledger_path = output / "outcome_ledgers.jsonl"
    conditions_path = output / "condition_summaries.jsonl"
    comparison_path = output / "capture_comparison.jsonl"
    summary_path = output / "lifecycle_summary.json"
    manifest_path = output / "lifecycle_manifest.json"
    _write_jsonl(raw_path, (item.raw for item in activity))
    _write_jsonl(target_path, (_normalized(item) for item in target_activity))
    _write_jsonl(ledger_path, ledgers)
    _write_jsonl(conditions_path, summaries)
    _write_jsonl(comparison_path, comparisons)
    _write_json(summary_path, aggregate)
    artifacts = (raw_path, target_path, ledger_path, conditions_path, comparison_path, summary_path)
    manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "inputs": {
            "economics_conditions": {"path": str(economics_path), "sha256": _ECONOMICS_SHA},
            "settlement_rows": {"path": str(settlement_path), "sha256": _SETTLEMENT_SHA},
            "decoded_rows": {"path": str(decoded_path), "sha256": _DECODED_SHA},
        },
        "activity_contract": {
            "wallet": _WALLET,
            "start": _START,
            "end": _END,
            "types": _TYPES,
            "observation_mode": ObservationMode.BACKFILL.value,
        },
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)} for path in artifacts
        },
    }
    _write_json(manifest_path, manifest)
    return {"manifest": manifest, "summary": aggregate, "output_dir": str(output)}


def _aggregate(
    all_activity: Sequence[WalletActivity],
    target_activity: Sequence[WalletActivity],
    ledgers: Sequence[dict[str, Any]],
    summaries: Sequence[dict[str, Any]],
    comparisons: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    complete = [row for row in summaries if row["cash_reconciliation_complete"]]
    cash = sum((_decimal(row["public_pre_fee_cash_flow"], "cash flow") for row in complete), Decimal(0))
    negative = [row for row in ledgers if _decimal(row["post_redeem_flow_balance"], "flow balance", signed=True) < 0]
    positive = [row for row in ledgers if _decimal(row["post_redeem_flow_balance"], "flow balance", signed=True) > 0]
    weighted_captured = sum((_decimal(row["captured_buy_size"], "captured") for row in comparisons), Decimal(0))
    weighted_lifecycle = sum((_decimal(row["lifecycle_buy_size"], "lifecycle") for row in comparisons), Decimal(0))
    return {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "study_status": "COLLECTING",
        "resolved_condition_progress": {"observed": len(summaries), "target": 30},
        "activity": {
            "all_rows": len(all_activity),
            "target_rows": len(target_activity),
            "all_by_type": {kind: sum(item.activity_type == kind for item in all_activity) for kind in sorted(_TYPE_SET)},
            "target_by_type": {kind: sum(item.activity_type == kind for item in target_activity) for kind in sorted(_TYPE_SET)},
        },
        "capture": {
            "captured_buy_size": _text(weighted_captured),
            "lifecycle_buy_size": _text(weighted_lifecycle),
            "size_weighted_capture_share": _ratio(weighted_captured, weighted_lifecycle),
        },
        "flow_reconciliation": {
            "negative_outcome_balances": len(negative),
            "positive_outcome_balances": len(positive),
            "zero_outcome_balances": len(ledgers) - len(negative) - len(positive),
            "minimum_unexplained_inflow": _text(
                sum((_decimal(row["minimum_unexplained_inflow"], "inflow") for row in ledgers), Decimal(0))
            ),
        },
        "public_cash": {
            "complete_conditions": len(complete),
            "pre_fee_cash_flow_complete_conditions": _text(cash),
            "interpretation": "PUBLIC_DATA_API_CASH_FLOW_NOT_FEE_ADJUSTED_PNL",
        },
    }


def _target_identities(
    economics: Sequence[dict[str, Any]], settlements: Sequence[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if len(economics) != 5 or len(settlements) != 5:
        raise LifecycleLedgerError("expected exact five economics and settlement conditions")
    econ = {str(row.get("condition_id", "")).lower(): str(row.get("slug", "")) for row in economics}
    targets: dict[str, dict[str, Any]] = {}
    for row in settlements:
        condition_id = str(row.get("condition_id", "")).lower()
        slug = str(row.get("slug", ""))
        winner = str(row.get("winning_outcome", ""))
        if row.get("resolution_status") != "RESOLVED" or winner not in {"Up", "Down"}:
            raise LifecycleLedgerError("all settlement targets must be unambiguously resolved")
        if condition_id not in econ or econ[condition_id] != slug:
            raise LifecycleLedgerError("economics and settlement identities differ")
        targets[condition_id] = {"slug": slug, "winning_outcome": winner}
    if len(econ) != 5 or len(targets) != 5 or set(econ) != set(targets):
        raise LifecycleLedgerError("target identities are not five unique matching conditions")
    return targets


def _captured_buy_sizes(
    decoded: Sequence[dict[str, Any]], targets: dict[str, dict[str, Any]]
) -> dict[tuple[str, str], Decimal]:
    sizes: defaultdict[tuple[str, str], Decimal] = defaultdict(Decimal)
    for row in decoded:
        condition_id = str(row.get("condition_id", "")).lower()
        if condition_id not in targets:
            continue
        outcome = str(row.get("outcome", ""))
        if outcome not in {"Up", "Down"}:
            raise LifecycleLedgerError("captured receipt outcome is not Up/Down")
        size = Decimal(int(row["taker_amount_filled"])) / _MICRO
        sizes[(condition_id, outcome)] += size
    return dict(sizes)


def _validate_activity(rows: Sequence[WalletActivity]) -> None:
    seen: set[tuple[Any, ...]] = set()
    for item in rows:
        timestamp = int(item.source_event_time.timestamp())
        if item.observation_mode is not ObservationMode.BACKFILL:
            raise LifecycleLedgerError("activity evidence is not BACKFILL")
        if item.proxy_wallet.lower() != _WALLET:
            raise LifecycleLedgerError("activity wallet mismatch")
        if item.activity_type not in _TYPE_SET:
            raise LifecycleLedgerError(f"unexpected activity type {item.activity_type}")
        if not _START <= timestamp <= _END:
            raise LifecycleLedgerError("activity row outside frozen interval")
        identity = (
            timestamp,
            item.transaction_hash,
            item.condition_id.lower(),
            item.activity_type,
            item.side,
            item.asset,
            item.outcome,
            str(item.raw.get("size")),
            str(item.raw.get("usdcSize")),
        )
        if identity in seen:
            raise LifecycleLedgerError("duplicate exact activity identity after collection")
        seen.add(identity)


def _raw_decimal(item: WalletActivity, field: str, *, allow_missing: bool = False) -> Decimal | None:
    value = item.raw.get(field)
    if value is None and allow_missing:
        return None
    return _decimal(value, field)


def _required(value: Decimal | None, label: str) -> Decimal:
    if value is None:
        raise LifecycleLedgerError(f"missing {label}")
    return value


def _decimal(value: Any, label: str, *, signed: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise LifecycleLedgerError(f"invalid {label}") from exc
    if not result.is_finite() or (not signed and result < 0):
        raise LifecycleLedgerError(f"{label} must be finite" + ("" if signed else " and non-negative"))
    return result


def _ratio(numerator: Decimal, denominator: Decimal) -> str | None:
    return _text(numerator / denominator) if denominator else None


def _text(value: Decimal) -> str:
    return format(value, "f")


def _normalized(item: WalletActivity) -> dict[str, Any]:
    return {
        "condition_id": item.condition_id.lower(),
        "activity_type": item.activity_type,
        "source_event_time": item.source_event_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "transaction_hash": item.transaction_hash,
        "side": item.side,
        "size": item.raw.get("size"),
        "usdc_size": item.raw.get("usdcSize"),
        "asset": item.asset,
        "outcome": item.outcome,
        "slug": item.slug,
        "observation_mode": item.observation_mode.value,
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise LifecycleLedgerError(f"{path} contains a non-object row")
    return rows


def _require_sha(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise LifecycleLedgerError(f"{label} SHA256 mismatch: expected {expected}, got {actual}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--economics-conditions", required=True)
    parser.add_argument("--settlement-rows", required=True)
    parser.add_argument("--decoded-rows", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--code-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_analysis(
        economics_conditions_path=args.economics_conditions,
        settlement_rows_path=args.settlement_rows,
        decoded_rows_path=args.decoded_rows,
        output_dir=args.output_dir,
        code_commit=args.code_commit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
