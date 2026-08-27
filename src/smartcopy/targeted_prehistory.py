"""Targeted pre-epoch lifecycle reconstruction for five frozen Bonereaper markets."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Sequence

from .lifecycle_ledger import build_ledgers
from .models import ObservationMode, WalletActivity
from .polymarket import PolymarketDataAPI

_SCHEMA = "smartcopy-bonereaper-targeted-prehistory-v1"
_CONTRACT_COMMIT = "14ff7231b27b2f8e4526ded6c28b2ec4f497f5dd"
_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_START = 1787755662
_OLD_START = 1787841600
_END = 1787855700
_TYPES = "TRADE,SPLIT,MERGE,REDEEM"
_TYPE_SET = frozenset(_TYPES.split(","))
_MARKET = (
    "0x3117cfe02c20d02daf2d4e30addbe7d188c42e191e51437eef1022ffb56e3fbe,"
    "0x52156b9f8f14c0c15022bb2187be136415341382b92f63e6de059f0db74f3aa3,"
    "0x7021e760b33268e406766a7077a7571d8fd3935bc1ced475dc1e9d406ce81b7c,"
    "0x9bb775834f30a9014bd48b28e72ac73b187ba7b61c6cbe6050bd79da20ab3e04,"
    "0xa0201d069b577fbeb1b31967db06be613bd825b6e9acc656ebd58e17eb1d3809"
)
_GAMMA_SHA = "d28c1fa9de96766c8828238a1f8f49c9d2cb63a182bb9f76e4c320d20fc9ef24"
_ECONOMICS_SHA = "8c848d320e2cc53e931fb408d493166f7ccb784416a56bcc4e8bdfdb745fb32f"
_SETTLEMENT_SHA = "76e1dbae9cd9ef7708cde1976afa6ec13bc9018134483b87c5b91f9c599617b8"
_DECODED_SHA = "1cbbe07f740682e1f6542d1ed70d7d2b8b63a9099a3366382aa3e3b1bff2ab31"
_OLD_ACTIVITY_SHA = "97887d7905a03967fe574d6e4ee8b2af34bf1d0d03c133ba9a559834bb9891c2"
_MICRO = Decimal("1000000")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class TargetedPrehistoryError(RuntimeError):
    """Raised when evidence violates the frozen targeted-prehistory contract."""


def compare_histories(
    old_rows: Sequence[dict[str, Any]], current_rows: Sequence[dict[str, Any]]
) -> dict[str, Any]:
    """Compare canonical normalized activity identities without fuzzy matching."""

    old = {_identity(row) for row in old_rows}
    current = {_identity(row) for row in current_rows}
    if len(old) != len(old_rows) or len(current) != len(current_rows):
        raise TargetedPrehistoryError("duplicate normalized activity identity")
    return {
        "old_rows": len(old),
        "extended_rows": len(current),
        "overlap_rows": len(old & current),
        "missing_old_rows": len(old - current),
        "new_rows": len(current - old),
    }


def run_analysis(
    *,
    gamma_rows_path: str | Path,
    economics_conditions_path: str | Path,
    settlement_rows_path: str | Path,
    decoded_rows_path: str | Path,
    old_target_activity_path: str | Path,
    output_dir: str | Path,
    code_commit: str,
    client: PolymarketDataAPI | None = None,
) -> dict[str, Any]:
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing analysis directory: {output}")

    paths = {
        "gamma_rows": (Path(gamma_rows_path), _GAMMA_SHA),
        "economics_conditions": (Path(economics_conditions_path), _ECONOMICS_SHA),
        "settlement_rows": (Path(settlement_rows_path), _SETTLEMENT_SHA),
        "decoded_rows": (Path(decoded_rows_path), _DECODED_SHA),
        "old_target_activity": (Path(old_target_activity_path), _OLD_ACTIVITY_SHA),
    }
    for label, (path, expected) in paths.items():
        _require_sha(path, expected, label)

    gamma = _load_jsonl(paths["gamma_rows"][0])
    economics = _load_jsonl(paths["economics_conditions"][0])
    settlements = _load_jsonl(paths["settlement_rows"][0])
    decoded = _load_jsonl(paths["decoded_rows"][0])
    old_normalized = _load_jsonl(paths["old_target_activity"][0])
    targets = _target_identities(economics, settlements)
    _validate_gamma(gamma, targets)
    captured = _captured_buy_sizes(decoded, targets)

    activity_client = client or PolymarketDataAPI()
    activity = activity_client.collect_activity_range(
        _WALLET,
        start=_START,
        end=_END,
        activity_type=_TYPES,
        market=_MARKET,
    )
    _validate_activity(activity, targets)
    normalized = [_normalized(item) for item in activity]
    history_comparison = compare_histories(old_normalized, normalized)
    if history_comparison["missing_old_rows"]:
        raise TargetedPrehistoryError("extended activity is missing frozen lifecycle-v1 rows")

    old_activity = [_wallet_from_normalized(row) for row in old_normalized]
    old_ledgers, old_conditions, _old_capture = build_ledgers(
        old_activity, target_conditions=targets, captured_buy_sizes=captured
    )
    ledgers, conditions, capture = build_ledgers(
        activity, target_conditions=targets, captured_buy_sizes=captured
    )
    pre_epoch = [row for row in normalized if _unix(row["source_event_time"]) < _OLD_START]
    comparison = _comparison(old_ledgers, old_conditions, ledgers, conditions)
    summary = _summary(activity, pre_epoch, ledgers, conditions, history_comparison, comparison)

    output.mkdir(parents=True)
    raw_path = output / "targeted_activity_raw.jsonl"
    normalized_path = output / "targeted_activity.jsonl"
    pre_epoch_path = output / "pre_epoch_activity.jsonl"
    ledger_path = output / "outcome_ledgers.jsonl"
    condition_path = output / "condition_summaries.jsonl"
    capture_path = output / "capture_comparison.jsonl"
    comparison_path = output / "prehistory_comparison.jsonl"
    summary_path = output / "targeted_prehistory_summary.json"
    manifest_path = output / "targeted_prehistory_manifest.json"
    _write_jsonl(raw_path, (item.raw for item in activity))
    _write_jsonl(normalized_path, normalized)
    _write_jsonl(pre_epoch_path, pre_epoch)
    _write_jsonl(ledger_path, ledgers)
    _write_jsonl(condition_path, conditions)
    _write_jsonl(capture_path, capture)
    _write_jsonl(comparison_path, comparison)
    _write_json(summary_path, summary)
    artifacts = (
        raw_path,
        normalized_path,
        pre_epoch_path,
        ledger_path,
        condition_path,
        capture_path,
        comparison_path,
        summary_path,
    )
    manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "inputs": {
            label: {"path": str(path), "sha256": expected}
            for label, (path, expected) in paths.items()
        },
        "activity_contract": {
            "wallet": _WALLET,
            "start": _START,
            "end": _END,
            "types": _TYPES,
            "market": _MARKET,
            "observation_mode": ObservationMode.BACKFILL.value,
        },
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)} for path in artifacts
        },
    }
    _write_json(manifest_path, manifest)
    return {"manifest": manifest, "summary": summary, "output_dir": str(output)}


def _comparison(
    old_ledgers: Sequence[dict[str, Any]],
    old_conditions: Sequence[dict[str, Any]],
    ledgers: Sequence[dict[str, Any]],
    conditions: Sequence[dict[str, Any]],
) -> list[dict[str, Any]]:
    old_ledger = {(row["condition_id"], row["outcome"]): row for row in old_ledgers}
    old_condition = {row["condition_id"]: row for row in old_conditions}
    condition = {row["condition_id"]: row for row in conditions}
    output = []
    for row in ledgers:
        key = (row["condition_id"], row["outcome"])
        before = old_ledger[key]
        prehistory_buy = _decimal(row["buy_tokens"], "buy tokens") - _decimal(
            before["buy_tokens"], "old buy tokens"
        )
        prehistory_usdc = _decimal(row["buy_usdc"], "buy usdc") - _decimal(
            before["buy_usdc"], "old buy usdc"
        )
        output.append(
            {
                "schema_version": _SCHEMA,
                "condition_id": row["condition_id"],
                "slug": row["slug"],
                "outcome": row["outcome"],
                "prehistory_buy_tokens": _text(prehistory_buy),
                "prehistory_buy_usdc": _text(prehistory_usdc),
                "old_minimum_unexplained_inflow": before["minimum_unexplained_inflow"],
                "extended_minimum_unexplained_inflow": row["minimum_unexplained_inflow"],
                "old_post_redeem_flow_balance": before["post_redeem_flow_balance"],
                "extended_post_redeem_flow_balance": row["post_redeem_flow_balance"],
                "old_condition_cash_flow": old_condition[row["condition_id"]]["public_pre_fee_cash_flow"],
                "extended_condition_cash_flow": condition[row["condition_id"]]["public_pre_fee_cash_flow"],
            }
        )
    return output


def _summary(
    activity: Sequence[WalletActivity],
    pre_epoch: Sequence[dict[str, Any]],
    ledgers: Sequence[dict[str, Any]],
    conditions: Sequence[dict[str, Any]],
    history_comparison: dict[str, Any],
    comparison: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    gap = sum(
        (_decimal(row["minimum_unexplained_inflow"], "minimum unexplained inflow") for row in ledgers),
        Decimal(0),
    )
    old_gap = sum(
        (_decimal(row["old_minimum_unexplained_inflow"], "old unexplained inflow") for row in comparison),
        Decimal(0),
    )
    cash = sum(
        (_decimal(row["public_pre_fee_cash_flow"], "cash flow", signed=True) for row in conditions),
        Decimal(0),
    )
    prehistory_buys = [
        row for row in pre_epoch if row["activity_type"] == "TRADE" and row["side"] == "BUY"
    ]
    return {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "study_status": "COLLECTING",
        "resolved_condition_progress": {"observed": len(conditions), "target": 30},
        "prehistory_verdict": "PREHISTORY_GAP_CLOSED" if gap == 0 else "PREHISTORY_GAP_REMAINS",
        "activity": {
            "rows": len(activity),
            "by_type": {kind: sum(item.activity_type == kind for item in activity) for kind in sorted(_TYPE_SET)},
            "history_comparison": history_comparison,
        },
        "pre_epoch": {
            "rows": len(pre_epoch),
            "buy_rows": len(prehistory_buys),
            "buy_tokens": _text(sum((_decimal(row["size"], "prehistory size") for row in prehistory_buys), Decimal(0))),
            "buy_usdc": _text(sum((_decimal(row["usdc_size"], "prehistory usdc") for row in prehistory_buys), Decimal(0))),
        },
        "flow_reconciliation": {
            "old_minimum_unexplained_inflow": _text(old_gap),
            "extended_minimum_unexplained_inflow": _text(gap),
            "negative_outcome_balances": sum(
                _decimal(row["post_redeem_flow_balance"], "balance", signed=True) < 0 for row in ledgers
            ),
        },
        "public_cash": {
            "pre_fee_cash_flow": _text(cash),
            "interpretation": "PUBLIC_DATA_API_CASH_FLOW_NOT_FEE_ADJUSTED_PNL",
        },
    }


def _target_identities(
    economics: Sequence[dict[str, Any]], settlements: Sequence[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    if len(economics) != 5 or len(settlements) != 5:
        raise TargetedPrehistoryError("expected exact five target conditions")
    econ = {str(row.get("condition_id", "")).lower(): str(row.get("slug", "")) for row in economics}
    targets = {}
    for row in settlements:
        condition_id = str(row.get("condition_id", "")).lower()
        slug = str(row.get("slug", ""))
        winner = str(row.get("winning_outcome", ""))
        if condition_id not in econ or econ[condition_id] != slug or winner not in {"Up", "Down"}:
            raise TargetedPrehistoryError("target identity or winner mismatch")
        targets[condition_id] = {"slug": slug, "winning_outcome": winner}
    if set(targets) != set(_MARKET.split(",")):
        raise TargetedPrehistoryError("target set differs from frozen condition filter")
    return targets


def _validate_gamma(gamma: Sequence[dict[str, Any]], targets: dict[str, dict[str, Any]]) -> None:
    if len(gamma) != 5:
        raise TargetedPrehistoryError("expected exact five Gamma responses")
    starts = []
    seen = set()
    for row in gamma:
        response = row.get("response")
        if not isinstance(response, dict):
            raise TargetedPrehistoryError("Gamma response row is malformed")
        condition_id = str(response.get("conditionId", "")).lower()
        slug = str(response.get("slug", ""))
        if condition_id not in targets or targets[condition_id]["slug"] != slug:
            raise TargetedPrehistoryError("Gamma identity differs from frozen targets")
        starts.append(_unix(response.get("createdAt")))
        seen.add(condition_id)
    if seen != set(targets) or min(starts) != _START:
        raise TargetedPrehistoryError("Gamma earliest createdAt differs from frozen start")


def _captured_buy_sizes(
    decoded: Sequence[dict[str, Any]], targets: dict[str, dict[str, Any]]
) -> dict[tuple[str, str], Decimal]:
    sizes: dict[tuple[str, str], Decimal] = {}
    for row in decoded:
        condition_id = str(row.get("condition_id", "")).lower()
        if condition_id not in targets:
            continue
        outcome = str(row.get("outcome", ""))
        if outcome not in {"Up", "Down"}:
            raise TargetedPrehistoryError("decoded target outcome is not Up/Down")
        key = (condition_id, outcome)
        sizes[key] = sizes.get(key, Decimal(0)) + Decimal(int(row["taker_amount_filled"])) / _MICRO
    return sizes


def _validate_activity(
    rows: Sequence[WalletActivity], targets: dict[str, dict[str, Any]]
) -> None:
    seen = set()
    for item in rows:
        timestamp = int(item.source_event_time.timestamp())
        if item.observation_mode is not ObservationMode.BACKFILL:
            raise TargetedPrehistoryError("activity is not BACKFILL")
        if item.proxy_wallet.lower() != _WALLET or item.condition_id.lower() not in targets:
            raise TargetedPrehistoryError("activity wallet or condition differs from frozen query")
        if item.activity_type not in _TYPE_SET or not _START <= timestamp <= _END:
            raise TargetedPrehistoryError("activity type or timestamp differs from frozen query")
        identity = _identity(_normalized(item))
        if identity in seen:
            raise TargetedPrehistoryError("duplicate targeted activity identity")
        seen.add(identity)


def _wallet_from_normalized(row: dict[str, Any]) -> WalletActivity:
    source = datetime.fromisoformat(str(row["source_event_time"]).replace("Z", "+00:00"))
    return WalletActivity(
        proxy_wallet=_WALLET,
        source_event_time=source,
        first_observed_time=datetime.fromtimestamp(_END, tz=timezone.utc),
        condition_id=str(row["condition_id"]),
        activity_type=str(row["activity_type"]),
        side=row.get("side"),
        size=float(row.get("size") or 0),
        usdc_size=float(row.get("usdc_size") or 0),
        price=None,
        asset=row.get("asset"),
        transaction_hash=row.get("transaction_hash"),
        title=None,
        slug=row.get("slug"),
        event_slug=None,
        outcome=row.get("outcome"),
        observation_mode=ObservationMode.BACKFILL,
        raw={"size": row.get("size"), "usdcSize": row.get("usdc_size")},
    )


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


def _identity(row: dict[str, Any]) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"))


def _unix(value: Any) -> int:
    if not isinstance(value, str):
        raise TargetedPrehistoryError("timestamp must be an ISO string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise TargetedPrehistoryError("timestamp must be timezone-aware")
    return int(parsed.timestamp())


def _decimal(value: Any, label: str, *, signed: bool = False) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise TargetedPrehistoryError(f"invalid {label}") from exc
    if not result.is_finite() or (not signed and result < 0):
        raise TargetedPrehistoryError(f"{label} has invalid sign or value")
    return result


def _text(value: Decimal) -> str:
    return format(value, "f")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise TargetedPrehistoryError(f"{path} contains a non-object row")
    return rows


def _require_sha(path: Path, expected: str, label: str) -> None:
    actual = _sha256(path)
    if actual != expected:
        raise TargetedPrehistoryError(f"{label} SHA256 mismatch: expected {expected}, got {actual}")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gamma-rows", required=True)
    parser.add_argument("--economics-conditions", required=True)
    parser.add_argument("--settlement-rows", required=True)
    parser.add_argument("--decoded-rows", required=True)
    parser.add_argument("--old-target-activity", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--code-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_analysis(
        gamma_rows_path=args.gamma_rows,
        economics_conditions_path=args.economics_conditions,
        settlement_rows_path=args.settlement_rows,
        decoded_rows_path=args.decoded_rows,
        old_target_activity_path=args.old_target_activity,
        output_dir=args.output_dir,
        code_commit=args.code_commit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
