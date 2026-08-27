"""Fee-aware maker/taker study over the targeted Bonereaper lifecycle."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from smartcopy.correction_overlay import WalletFill
from smartcopy.maker_taker import PolygonReceiptAPI, _role_metrics, collect_receipts
from smartcopy.prospective_receipts import decode_prospective_rows

_SCHEMA = "smartcopy-bonereaper-lifecycle-maker-taker-v1"
_CONTRACT_COMMIT = "781e09bbfeea93aca8acfcfdf80028bd4515efac"
_SOURCE_SHA256 = "1a6989f9465b9ea7e4721038602dd1252ffa4a35395d50da0c3a9a90323d9576"
_CHAIN_ID = 137
_SLUG = re.compile(r"^(?:btc|eth)-updown-(?:5m|15m)-(\d+)$")
_RAW = "receipt_responses_raw.jsonl"
_ROWS = "lifecycle_maker_taker_rows.jsonl"
_SUMMARY = "lifecycle_maker_taker_summary.json"
_MANIFEST = "lifecycle_maker_taker_manifest.json"


def load_targeted_activity(
    path: str | Path,
    *,
    expected_sha256: str = _SOURCE_SHA256,
) -> tuple[tuple[WalletFill, ...], tuple[dict[str, Any], ...], dict[str, str]]:
    source = Path(path)
    raw = source.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256.lower():
        raise ValueError(f"targeted activity SHA256 mismatch: expected {expected_sha256}, got {actual}")

    fills: list[WalletFill] = []
    redemptions: list[dict[str, Any]] = []
    slugs: dict[str, str] = {}
    for number, line in enumerate(raw.splitlines(), start=1):
        row = json.loads(line)
        activity_type = row.get("activity_type")
        if activity_type == "REDEEM":
            redemptions.append(row)
            continue
        if activity_type != "TRADE" or row.get("side") != "BUY":
            raise ValueError(f"line {number}: expected TRADE/BUY or REDEEM")
        condition = str(row["condition_id"])
        slug = str(row["slug"])
        if _SLUG.fullmatch(slug) is None:
            raise ValueError(f"line {number}: unsupported slug {slug}")
        previous = slugs.setdefault(condition, slug)
        if previous != slug:
            raise ValueError(f"line {number}: condition has inconsistent slug")
        timestamp = datetime.fromisoformat(str(row["source_event_time"]).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            raise ValueError(f"line {number}: source time must be timezone-aware")
        size = float(row["size"])
        notional = float(row["usdc_size"])
        fills.append(
            WalletFill(
                condition_id=condition,
                source_second=int(timestamp.timestamp()),
                source_event_time=timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
                outcome=str(row["outcome"]),
                price=notional / size,
                size=size,
                notional=notional,
                asset_id=str(row["asset"]),
                transaction_hash=str(row["transaction_hash"]).lower(),
            )
        )
    fills.sort(
        key=lambda fill: (
            fill.condition_id,
            fill.source_second,
            fill.transaction_hash,
            fill.asset_id,
            fill.price,
            fill.size,
        )
    )
    if len(fills) != 289 or len({fill.transaction_hash for fill in fills}) != 285:
        raise ValueError("frozen population requires 289 fills and 285 unique transactions")
    if len(redemptions) != 5 or len(slugs) != 5:
        raise ValueError("frozen population requires five redemptions and five conditions")
    return tuple(fills), tuple(redemptions), slugs


def label_lifecycle_rows(
    decoded_rows: Sequence[dict[str, Any]],
    *,
    slugs: dict[str, str],
) -> tuple[dict[str, Any], ...]:
    pre_outcomes: dict[str, set[str]] = defaultdict(set)
    starts = {condition: _market_start(slug) for condition, slug in slugs.items()}
    for row in decoded_rows:
        condition = str(row["condition_id"])
        if int(row["source_second"]) < starts[condition]:
            pre_outcomes[condition].add(str(row["outcome"]))
    directional = {
        condition: next(iter(outcomes))
        for condition, outcomes in pre_outcomes.items()
        if len(outcomes) == 1
    }

    output: list[dict[str, Any]] = []
    for row in decoded_rows:
        condition = str(row["condition_id"])
        phase = "PRE_OPEN" if int(row["source_second"]) < starts[condition] else "POST_OPEN"
        pre_side = directional.get(condition)
        if pre_side is None:
            relation = "NO_UNIQUE_PREOPEN_SIDE"
        elif phase == "PRE_OPEN":
            relation = "PRE_OPEN_DIRECTIONAL"
        elif row["outcome"] == pre_side:
            relation = "POST_OPEN_SAME_SIDE"
        else:
            relation = "POST_OPEN_COMPLEMENT"
        output.append(
            {
                **row,
                "slug": slugs[condition],
                "lifecycle_phase": phase,
                "pre_open_directional_side": pre_side,
                "lifecycle_relation": relation,
            }
        )
    return tuple(output)


def summarize_lifecycle(
    rows: Sequence[dict[str, Any]],
    *,
    redemptions: Sequence[dict[str, Any]],
    slugs: dict[str, str],
) -> dict[str, Any]:
    ambiguous = [row for row in rows if row["schema_corrected_role"] == "AMBIGUOUS"]
    groups = {
        relation: [row for row in rows if row["lifecycle_relation"] == relation]
        for relation in (
            "PRE_OPEN_DIRECTIONAL",
            "POST_OPEN_SAME_SIDE",
            "POST_OPEN_COMPLEMENT",
            "NO_UNIQUE_PREOPEN_SIDE",
        )
    }
    metrics = {
        name: _role_metrics(group, role_field="schema_corrected_role")
        for name, group in groups.items()
    }
    pre = metrics["PRE_OPEN_DIRECTIONAL"]["notional"]
    complement = metrics["POST_OPEN_COMPLEMENT"]["notional"]
    same = metrics["POST_OPEN_SAME_SIDE"]["notional"]
    pre_verdict = _dominance(pre)
    complement_verdict = _dominance(complement)
    complete = len(rows) == 289 and not ambiguous
    joint = (
        "SUPPORTED"
        if complete and pre_verdict == "TAKER_DOMINANT" and complement_verdict == "MAKER_DOMINANT"
        else "NOT_SUPPORTED"
        if complete
        else "INCONCLUSIVE"
    )
    if not complete or complement["maker_share"] is None or same["maker_share"] is None:
        asymmetry = {"verdict": "INCONCLUSIVE", "maker_share_difference": None}
    else:
        difference = complement["maker_share"] - same["maker_share"]
        asymmetry = {
            "verdict": "SUPPORTED" if difference >= 0.20 else "NOT_SUPPORTED",
            "maker_share_difference": difference,
            "minimum_difference": 0.20,
        }

    redemption_by_condition = defaultdict(float)
    for row in redemptions:
        redemption_by_condition[str(row["condition_id"])] += float(row["usdc_size"])
    economics: dict[str, Any] = {}
    for condition, slug in sorted(slugs.items(), key=lambda item: item[1]):
        market_rows = [row for row in rows if row["condition_id"] == condition]
        source_cost = sum(float(row["source_notional"]) for row in market_rows)
        base_cost = sum(float(row["maker_amount_filled"]) for row in market_rows) / 1_000_000
        fees = sum(float(row["fee"]) for row in market_rows) / 1_000_000
        redemption = redemption_by_condition[condition]
        economics[condition] = {
            "slug": slug,
            "source_fee_aware_buy_cost": source_cost,
            "decoded_base_buy_cost": base_cost,
            "decoded_event_fees": fees,
            "redemption_cash": redemption,
            "public_cash_result": redemption - source_cost,
        }

    return {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "decoder_semantics": "CTF_EXCHANGE_V2_FEE_AWARE",
        "completeness": {
            "source_rows": 289,
            "decoded_rows": len(rows),
            "ambiguous_rows": len(ambiguous),
            "unique_transactions": len({row["transaction_hash"] for row in rows}),
        },
        "hypotheses": {
            "pre_open_active_conviction": {"verdict": pre_verdict, "metrics": metrics["PRE_OPEN_DIRECTIONAL"]},
            "post_open_passive_complement": {"verdict": complement_verdict, "metrics": metrics["POST_OPEN_COMPLEMENT"]},
            "inventory_aware_role_asymmetry": asymmetry,
            "joint_active_entry_passive_complement": {"verdict": joint},
        },
        "groups": metrics,
        "all_rows": _role_metrics(rows, role_field="schema_corrected_role"),
        "per_market": {
            condition: {
                "slug": slug,
                "roles": _role_metrics(
                    [row for row in rows if row["condition_id"] == condition],
                    role_field="schema_corrected_role",
                ),
            }
            for condition, slug in sorted(slugs.items(), key=lambda item: item[1])
        },
        "economics": {
            "per_market": economics,
            "total_event_fees": sum(float(row["fee"]) for row in rows) / 1_000_000,
            "total_public_cash_result": sum(item["public_cash_result"] for item in economics.values()),
            "exclusions": "maker rewards/rebates, gas, funding, transfers, and positions outside source",
        },
        "interpretation_limit": "maker role proves passive execution at fill time, not order placement time",
    }


def run_lifecycle_study(
    *,
    targeted_activity_path: str | Path,
    output_dir: str | Path,
    api: PolygonReceiptAPI,
    code_commit: str,
    batch_size: int = 25,
) -> dict[str, Any]:
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output}")
    if re.fullmatch(r"[0-9a-f]{40}", code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    fills, redemptions, slugs = load_targeted_activity(targeted_activity_path)
    chain_id, envelopes = collect_receipts(
        api, (fill.transaction_hash for fill in fills), batch_size=batch_size
    )
    if chain_id != _CHAIN_ID:
        raise ValueError(f"expected Polygon chain id {_CHAIN_ID}, got {chain_id}")
    decoded = decode_prospective_rows(fills, envelopes)
    rows = label_lifecycle_rows(decoded, slugs=slugs)
    summary = summarize_lifecycle(rows, redemptions=redemptions, slugs=slugs)

    output.mkdir(parents=True)
    raw_path, rows_path = output / _RAW, output / _ROWS
    summary_path, manifest_path = output / _SUMMARY, output / _MANIFEST
    _write_jsonl(raw_path, envelopes)
    _write_jsonl(rows_path, rows)
    _write_json(summary_path, summary)
    manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "collection_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "rpc_url": api.rpc_url,
        "chain_id": chain_id,
        "source": {"path": str(targeted_activity_path), "sha256": _SOURCE_SHA256},
        "source_rows": 294,
        "selected_trade_rows": len(fills),
        "unique_transactions": len({fill.transaction_hash for fill in fills}),
        "receipt_count": len(envelopes) - 1,
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in (raw_path, rows_path, summary_path)
        },
    }
    _write_json(manifest_path, manifest)
    return {"summary": summary, "manifest": manifest, "output_dir": str(output)}


def _market_start(slug: str) -> int:
    match = _SLUG.fullmatch(slug)
    if match is None:
        raise ValueError(f"unsupported slug {slug}")
    return int(match.group(1))


def _dominance(notional: dict[str, Any]) -> str:
    maker = notional["maker_share"]
    taker = notional["taker_share"]
    if maker is None or taker is None:
        return "INCONCLUSIVE"
    if maker >= 0.80:
        return "MAKER_DOMINANT"
    if taker >= 0.80:
        return "TAKER_DOMINANT"
    return "MIXED"


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    with path.open("xb") as handle:
        for row in rows:
            handle.write((json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode())


def _write_json(path: Path, value: Any) -> None:
    with path.open("xb") as handle:
        handle.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--targeted-activity", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_lifecycle_study(
        targeted_activity_path=args.targeted_activity,
        output_dir=args.output,
        api=PolygonReceiptAPI(rpc_url=args.rpc_url),
        code_commit=args.code_commit,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
