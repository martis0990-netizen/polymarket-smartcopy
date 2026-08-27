"""SHA-bound FIFO pair economics and maker/taker markout for clean bundle v5."""

from __future__ import annotations

import argparse
import bisect
import hashlib
import json
import re
from collections import defaultdict, deque
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Sequence


_SCHEMA = "smartcopy-bonereaper-prospective-economics-v1"
_BUNDLE_SCHEMA = "smartcopy-bonereaper-prospective-bundle-v5"
_CONTRACT_COMMIT = "e1cd5f307185ee564758cf296385933027ce3889"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_HORIZONS = (10, 30, 60)
_PAIR_ROWS = "pair_chunks.jsonl"
_MARKOUT_ROWS = "fill_markouts.jsonl"
_CONDITIONS = "condition_economics.jsonl"
_SUMMARY = "prospective_economics_summary.json"
_MANIFEST = "prospective_economics_manifest.json"
_MICRO = Decimal("1000000")


class ProspectiveEconomicsError(RuntimeError):
    """Raised when immutable evidence cannot satisfy the economics contract."""


def build_fifo_pairs(
    rows: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    chunks: list[dict[str, Any]] = []
    conditions: list[dict[str, Any]] = []
    by_condition: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for source in rows:
        role = str(source.get("schema_corrected_role"))
        if role not in {"MAKER", "TAKER"}:
            raise ProspectiveEconomicsError("decoded receipt row has ambiguous corrected role")
        outcome = str(source.get("outcome"))
        if outcome not in {"Up", "Down"}:
            raise ProspectiveEconomicsError("decoded receipt row has unsupported outcome")
        by_condition[str(source["condition_id"])].append(_lot(source))

    for condition_id, source_lots in sorted(by_condition.items()):
        queues: dict[str, deque[dict[str, Any]]] = {"Up": deque(), "Down": deque()}
        ordered = sorted(source_lots, key=_lot_order)
        condition_chunks: list[dict[str, Any]] = []
        for lot in ordered:
            other = "Down" if lot["outcome"] == "Up" else "Up"
            while lot["remaining_size"] > 0 and queues[other]:
                opposite = queues[other][0]
                size = min(lot["remaining_size"], opposite["remaining_size"])
                up = lot if lot["outcome"] == "Up" else opposite
                down = lot if lot["outcome"] == "Down" else opposite
                gross_cost = up["base_unit_cost"] + down["base_unit_cost"]
                adjusted_cost = up["adjusted_unit_cost"] + down["adjusted_unit_cost"]
                role_composition = (
                    "MAKER_MAKER"
                    if up["role"] == down["role"] == "MAKER"
                    else "TAKER_TAKER"
                    if up["role"] == down["role"] == "TAKER"
                    else "MIXED"
                )
                chunk = {
                    "schema_version": _SCHEMA,
                    "condition_id": condition_id,
                    "slug": lot.get("bound_slug") or opposite.get("bound_slug"),
                    "asset": lot.get("bound_asset") or opposite.get("bound_asset"),
                    "window_seconds": lot.get("bound_window_seconds") or opposite.get("bound_window_seconds"),
                    "matched_size": _text(size),
                    "gross_pair_cost_per_unit": _text(gross_cost),
                    "fee_adjusted_pair_cost_per_unit": _text(adjusted_cost),
                    "gross_edge_per_unit": _text(Decimal(1) - gross_cost),
                    "fee_adjusted_edge_per_unit": _text(Decimal(1) - adjusted_cost),
                    "gross_cost_class": _cost_class(gross_cost),
                    "fee_adjusted_cost_class": _cost_class(adjusted_cost),
                    "role_composition": role_composition,
                    "up": _chunk_leg(up, size),
                    "down": _chunk_leg(down, size),
                }
                condition_chunks.append(chunk)
                chunks.append(chunk)
                lot["remaining_size"] -= size
                opposite["remaining_size"] -= size
                if opposite["remaining_size"] == 0:
                    queues[other].popleft()
            if lot["remaining_size"] > 0:
                queues[lot["outcome"]].append(lot)

        matched_size = sum(Decimal(row["matched_size"]) for row in condition_chunks)
        gross_cost_total = sum(
            Decimal(row["matched_size"]) * Decimal(row["gross_pair_cost_per_unit"])
            for row in condition_chunks
        )
        adjusted_cost_total = sum(
            Decimal(row["matched_size"]) * Decimal(row["fee_adjusted_pair_cost_per_unit"])
            for row in condition_chunks
        )
        residuals = {}
        for outcome in ("Up", "Down"):
            remaining = list(queues[outcome])
            residuals[outcome] = {
                "size": _text(sum((row["remaining_size"] for row in remaining), Decimal(0))),
                "base_cost": _text(
                    sum((row["remaining_size"] * row["base_unit_cost"] for row in remaining), Decimal(0))
                ),
                "fee_adjusted_cost": _text(
                    sum(
                        (row["remaining_size"] * row["adjusted_unit_cost"] for row in remaining),
                        Decimal(0),
                    )
                ),
            }
        first = ordered[0]
        conditions.append(
            {
                "schema_version": _SCHEMA,
                "condition_id": condition_id,
                "slug": first.get("bound_slug"),
                "asset": first.get("bound_asset"),
                "window_seconds": first.get("bound_window_seconds"),
                "fill_rows": len(ordered),
                "matched_chunks": len(condition_chunks),
                "matched_size": _text(matched_size),
                "gross_pair_cost_total": _text(gross_cost_total),
                "fee_adjusted_pair_cost_total": _text(adjusted_cost_total),
                "gross_pair_cost_per_unit": _optional_ratio(gross_cost_total, matched_size),
                "fee_adjusted_pair_cost_per_unit": _optional_ratio(adjusted_cost_total, matched_size),
                "gross_edge_total": _text(matched_size - gross_cost_total),
                "fee_adjusted_edge_total": _text(matched_size - adjusted_cost_total),
                "residuals": residuals,
            }
        )
    return chunks, conditions


def reconstruct_book_states(
    records: Sequence[dict[str, Any]],
) -> dict[str, tuple[tuple[int, Decimal, Decimal], ...]]:
    by_token: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in records:
        by_token[str(row["token_id"])].append(row)
    result: dict[str, tuple[tuple[int, Decimal, Decimal], ...]] = {}
    for token_id, token_rows in by_token.items():
        bids: dict[Decimal, Decimal] = {}
        asks: dict[Decimal, Decimal] = {}
        initialized = False
        states: list[tuple[int, Decimal, Decimal]] = []
        current_timestamp: int | None = None

        def flush() -> None:
            if current_timestamp is not None and initialized and bids and asks:
                states.append((current_timestamp, max(bids), min(asks)))

        for row in token_rows:
            timestamp = int(row["source_timestamp_ms"])
            if current_timestamp is not None and timestamp < current_timestamp:
                raise ProspectiveEconomicsError(f"token {token_id} book timestamp regressed")
            if current_timestamp is not None and timestamp != current_timestamp:
                flush()
            current_timestamp = timestamp
            if row.get("record_type") == "snapshot":
                bids.clear()
                asks.clear()
                initialized = bool(row.get("coverage_valid"))
                continue
            if not bool(row.get("coverage_valid")):
                bids.clear()
                asks.clear()
                initialized = False
                continue
            if not initialized:
                continue
            side = str(row.get("side"))
            if side not in {"BUY", "SELL"}:
                continue
            price = Decimal(str(row["price"]))
            size = Decimal(str(row["size"]))
            levels = bids if side == "BUY" else asks
            if size > 0:
                levels[price] = size
            else:
                levels.pop(price, None)
        flush()
        result[token_id] = tuple(states)
    return result


def build_markouts(
    rows: Sequence[dict[str, Any]],
    *,
    states: dict[str, tuple[tuple[int, Decimal, Decimal], ...]],
    gaps: Sequence[dict[str, Any]],
    capture_started_ms: int,
    capture_ended_ms: int,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    gaps_by_token: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for gap in gaps:
        gaps_by_token[str(gap.get("token_id"))].append(gap)
    for source in rows:
        token_id = str(source["asset_id"])
        size = Decimal(int(source["taker_amount_filled"])) / _MICRO
        adjusted_unit_cost = (
            Decimal(int(source["maker_amount_plus_fee"])) / _MICRO / size
        )
        fill_ms = int(source["source_second"]) * 1_000
        token_states = states.get(token_id, ())
        timestamps = [state[0] for state in token_states]
        for horizon in _HORIZONS:
            target_ms = fill_ms + horizon * 1_000
            reason = None
            selected = None
            if target_ms < capture_started_ms or target_ms > capture_ended_ms:
                reason = "TARGET_OUTSIDE_CAPTURE"
            elif _gap_intersects(gaps_by_token[token_id], fill_ms, target_ms):
                reason = "COVERAGE_GAP"
            else:
                index = bisect.bisect_right(timestamps, target_ms) - 1
                if index < 0 or token_states[index][0] < fill_ms:
                    reason = "NO_POST_FILL_VALID_STATE"
                else:
                    selected = token_states[index]
            if selected is None:
                output.append(_markout_row(source, horizon, eligible=False, reason=reason))
                continue
            timestamp, bid, ask = selected
            if bid <= 0 or ask <= 0 or bid > ask:
                output.append(
                    _markout_row(source, horizon, eligible=False, reason="INVALID_TWO_SIDED_BOOK")
                )
                continue
            mid = (bid + ask) / Decimal(2)
            markout = mid - adjusted_unit_cost
            output.append(
                _markout_row(
                    source,
                    horizon,
                    eligible=True,
                    state_timestamp_ms=timestamp,
                    best_bid=bid,
                    best_ask=ask,
                    mid=mid,
                    fee_adjusted_unit_cost=adjusted_unit_cost,
                    markout_per_unit=markout,
                    markout_usdc=markout * size,
                )
            )
    return output


def summarize_economics(
    pair_chunks: Sequence[dict[str, Any]],
    conditions: Sequence[dict[str, Any]],
    markouts: Sequence[dict[str, Any]],
    *,
    decoded_rows: int,
    bound_rows: int,
) -> dict[str, Any]:
    paired_conditions = [row for row in conditions if Decimal(row["matched_size"]) > 0]
    matched_size = sum((Decimal(row["matched_size"]) for row in pair_chunks), Decimal(0))

    def pair_distribution(field: str) -> dict[str, Any]:
        units = {
            label: sum(
                (Decimal(row["matched_size"]) for row in pair_chunks if row[field] == label),
                Decimal(0),
            )
            for label in ("LT_1", "EQ_1", "GT_1")
        }
        return {
            "matched_size": _text(matched_size),
            "unit_sizes": {label: _text(value) for label, value in units.items()},
            "unit_shares": {
                label: _optional_ratio(value, matched_size) for label, value in units.items()
            },
        }

    markout_summary = {}
    for role in ("MAKER", "TAKER"):
        markout_summary[role] = {}
        for horizon in _HORIZONS:
            selected = [
                row
                for row in markouts
                if row["role"] == role and row["horizon_seconds"] == horizon and row["eligible"]
            ]
            size = sum((Decimal(row["source_size"]) for row in selected), Decimal(0))
            total = sum((Decimal(row["markout_usdc"]) for row in selected), Decimal(0))
            notional = sum((Decimal(row["source_notional"]) for row in selected), Decimal(0))
            markout_summary[role][str(horizon)] = {
                "eligible_fills": len(selected),
                "eligible_size": _text(size),
                "eligible_notional": _text(notional),
                "markout_usdc": _text(total),
                "size_weighted_markout_per_unit": _optional_ratio(total, size),
            }

    return {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "study_status": "COLLECTING" if len(paired_conditions) < 30 else "STOPPING_TARGET_MET",
        "stopping_rule": {
            "paired_condition_target": 30,
            "paired_conditions_observed_this_bundle": len(paired_conditions),
            "gate_evaluation_deferred": len(paired_conditions) < 30,
        },
        "coverage": {
            "decoded_rows": decoded_rows,
            "bound_rows": bound_rows,
            "excluded_unbound_rows": decoded_rows - bound_rows,
        },
        "pair_chunks": len(pair_chunks),
        "gross_pair_cost": pair_distribution("gross_cost_class"),
        "fee_adjusted_pair_cost": pair_distribution("fee_adjusted_cost_class"),
        "role_composition_matched_size": {
            role: _text(
                sum(
                    (Decimal(row["matched_size"]) for row in pair_chunks if row["role_composition"] == role),
                    Decimal(0),
                )
            )
            for role in ("MAKER_MAKER", "MIXED", "TAKER_TAKER")
        },
        "markout": markout_summary,
    }


def run_analysis(
    *,
    bundle_dir: str | Path,
    expected_bundle_sha256: str,
    decoded_rows_path: str | Path,
    expected_decoded_sha256: str,
    output_dir: str | Path,
    code_commit: str,
) -> dict[str, Any]:
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing analysis directory: {output}")
    bundle = Path(bundle_dir)
    root_path = bundle / "prospective_bundle_manifest.json"
    _require_sha(root_path, expected_bundle_sha256, "bundle manifest")
    root = _load_json(root_path)
    if root.get("schema_version") != _BUNDLE_SCHEMA or root.get("clean_finalize") is not True:
        raise ProspectiveEconomicsError("economics analysis requires a clean bundle v5")
    capture_started_ms = _iso_ms(root.get("started_at"), "bundle started_at")
    capture_ended_ms = _iso_ms(root.get("ended_at"), "bundle ended_at")

    books = root.get("public_books")
    if not isinstance(books, dict) or set(books) != {"current", "safe"}:
        raise ProspectiveEconomicsError("bundle requires current and safe public-book bindings")
    tokens: dict[str, dict[str, Any]] = {}
    book_records: list[dict[str, Any]] = []
    gaps: list[dict[str, Any]] = []
    for group in ("current", "safe"):
        binding = books[group]
        if not isinstance(binding, dict):
            raise ProspectiveEconomicsError(f"{group} book binding must be an object")
        manifest_path = bundle / str(binding["manifest"])
        _require_sha(manifest_path, str(binding["sha256"]), f"{group} book manifest")
        token_path = bundle / str(binding["token_metadata"])
        _require_sha(token_path, str(binding["token_metadata_sha256"]), f"{group} token metadata")
        manifest = _load_json(manifest_path)
        book_root = manifest_path.parent
        levels_path = book_root / "book_levels.jsonl"
        gaps_path = book_root / "book_gaps.jsonl"
        for path in (levels_path, gaps_path):
            artifact = manifest.get("artifacts", {}).get(path.name)
            if not isinstance(artifact, dict):
                raise ProspectiveEconomicsError(f"{group} manifest is missing {path.name}")
            _require_sha(path, str(artifact["sha256"]), f"{group} {path.name}")
        metadata = _load_json(token_path).get("tokens")
        if not isinstance(metadata, list):
            raise ProspectiveEconomicsError(f"{group} token metadata must contain a tokens list")
        for row in metadata:
            token_id = str(row.get("token_id"))
            if token_id in tokens:
                raise ProspectiveEconomicsError(f"token {token_id} is bound more than once")
            tokens[token_id] = {**row, "book_group": group}
        book_records.extend(_load_jsonl(levels_path))
        gaps.extend(_load_jsonl(gaps_path))

    decoded_path = Path(decoded_rows_path)
    decoded_sha = _require_sha(decoded_path, expected_decoded_sha256, "decoded receipt rows")
    decoded = _load_jsonl(decoded_path)
    bound: list[dict[str, Any]] = []
    for row in decoded:
        metadata = tokens.get(str(row.get("asset_id")))
        if metadata is None:
            continue
        if str(row.get("condition_id")) != str(metadata.get("condition_id")):
            raise ProspectiveEconomicsError("receipt condition does not match bound token")
        if str(row.get("outcome")) != str(metadata.get("outcome")):
            raise ProspectiveEconomicsError("receipt outcome does not match bound token")
        bound.append(
            {
                **row,
                "bound_slug": metadata.get("slug"),
                "bound_asset": metadata.get("asset"),
                "bound_window_seconds": metadata.get("window_seconds"),
                "book_group": metadata["book_group"],
            }
        )

    pair_chunks, conditions = build_fifo_pairs(bound)
    states = reconstruct_book_states(book_records)
    markouts = build_markouts(
        bound,
        states=states,
        gaps=gaps,
        capture_started_ms=capture_started_ms,
        capture_ended_ms=capture_ended_ms,
    )
    summary = summarize_economics(
        pair_chunks,
        conditions,
        markouts,
        decoded_rows=len(decoded),
        bound_rows=len(bound),
    )

    output.mkdir(parents=True)
    pair_path = output / _PAIR_ROWS
    markout_path = output / _MARKOUT_ROWS
    conditions_path = output / _CONDITIONS
    summary_path = output / _SUMMARY
    manifest_path = output / _MANIFEST
    _write_jsonl(pair_path, pair_chunks)
    _write_jsonl(markout_path, markouts)
    _write_jsonl(conditions_path, conditions)
    _write_json(summary_path, summary)
    manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "bundle_manifest": {"path": str(root_path), "sha256": expected_bundle_sha256.lower()},
        "decoded_rows": {"path": str(decoded_path), "sha256": decoded_sha},
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in (pair_path, markout_path, conditions_path, summary_path)
        },
    }
    _write_json(manifest_path, manifest)
    return {"manifest": manifest, "summary": summary, "output_dir": str(output)}


def _lot(source: dict[str, Any]) -> dict[str, Any]:
    size = Decimal(int(source["taker_amount_filled"])) / _MICRO
    if size <= 0:
        raise ProspectiveEconomicsError("receipt fill size must be positive")
    base = Decimal(int(source["maker_amount_filled"])) / _MICRO
    fee = Decimal(int(source["fee"])) / _MICRO
    adjusted = Decimal(int(source["maker_amount_plus_fee"])) / _MICRO
    if base + fee != adjusted:
        raise ProspectiveEconomicsError("receipt base cost plus fee does not equal adjusted cost")
    return {
        **source,
        "role": str(source["schema_corrected_role"]),
        "outcome": str(source["outcome"]),
        "size": size,
        "remaining_size": size,
        "base_unit_cost": base / size,
        "adjusted_unit_cost": adjusted / size,
        "fee_unit_cost": fee / size,
    }


def _lot_order(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        int(row["source_second"]),
        int(row.get("block_number", 0)),
        int(row.get("event_log_index", 0)),
        str(row.get("transaction_hash", "")),
    )


def _chunk_leg(lot: dict[str, Any], size: Decimal) -> dict[str, Any]:
    return {
        "transaction_hash": lot.get("transaction_hash"),
        "source_second": int(lot["source_second"]),
        "role": lot["role"],
        "allocated_size": _text(size),
        "base_unit_cost": _text(lot["base_unit_cost"]),
        "fee_unit_cost": _text(lot["fee_unit_cost"]),
        "fee_adjusted_unit_cost": _text(lot["adjusted_unit_cost"]),
    }


def _cost_class(value: Decimal) -> str:
    return "LT_1" if value < 1 else "GT_1" if value > 1 else "EQ_1"


def _markout_row(
    source: dict[str, Any],
    horizon: int,
    *,
    eligible: bool,
    reason: str | None = None,
    state_timestamp_ms: int | None = None,
    best_bid: Decimal | None = None,
    best_ask: Decimal | None = None,
    mid: Decimal | None = None,
    fee_adjusted_unit_cost: Decimal | None = None,
    markout_per_unit: Decimal | None = None,
    markout_usdc: Decimal | None = None,
) -> dict[str, Any]:
    return {
        "schema_version": _SCHEMA,
        "condition_id": source["condition_id"],
        "asset_id": source["asset_id"],
        "outcome": source["outcome"],
        "role": source["schema_corrected_role"],
        "transaction_hash": source["transaction_hash"],
        "source_second": int(source["source_second"]),
        "source_size": _text(Decimal(int(source["taker_amount_filled"])) / _MICRO),
        "source_notional": _text(Decimal(int(source["maker_amount_plus_fee"])) / _MICRO),
        "horizon_seconds": horizon,
        "eligible": eligible,
        "ineligibility_reason": reason,
        "state_timestamp_ms": state_timestamp_ms,
        "best_bid": _maybe_text(best_bid),
        "best_ask": _maybe_text(best_ask),
        "mid": _maybe_text(mid),
        "fee_adjusted_unit_cost": _maybe_text(fee_adjusted_unit_cost),
        "markout_per_unit": _maybe_text(markout_per_unit),
        "markout_usdc": _maybe_text(markout_usdc),
    }


def _gap_intersects(gaps: Sequence[dict[str, Any]], start_ms: int, target_ms: int) -> bool:
    for gap in gaps:
        start = gap.get("start_source_timestamp_ms")
        recovered = gap.get("recovered_source_timestamp_ms")
        if start is None:
            return True
        start_value = int(start)
        recovered_value = int(recovered) if recovered is not None else None
        if start_value <= target_ms and (recovered_value is None or recovered_value >= start_ms):
            return True
    return False


def _iso_ms(value: Any, label: str) -> int:
    if not isinstance(value, str):
        raise ProspectiveEconomicsError(f"{label} must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ProspectiveEconomicsError(f"{label} must be timezone-aware")
    return int(parsed.timestamp() * 1_000)


def _optional_ratio(numerator: Decimal, denominator: Decimal) -> str | None:
    return _text(numerator / denominator) if denominator else None


def _text(value: Decimal) -> str:
    return format(value, "f")


def _maybe_text(value: Decimal | None) -> str | None:
    return _text(value) if value is not None else None


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProspectiveEconomicsError(f"{path} must contain a JSON object")
    return value


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ProspectiveEconomicsError(f"{path} contains a non-object row")
    return rows


def _require_sha(path: Path, expected: str, label: str) -> str:
    actual = _sha256(path)
    if actual != expected.lower():
        raise ProspectiveEconomicsError(
            f"{label} SHA256 mismatch: expected {expected.lower()}, got {actual}"
        )
    return actual


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows)
    )


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--expected-bundle-sha256", required=True)
    parser.add_argument("--decoded-rows", required=True)
    parser.add_argument("--expected-decoded-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--code-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    print(
        json.dumps(
            run_analysis(
                bundle_dir=args.bundle_dir,
                expected_bundle_sha256=args.expected_bundle_sha256,
                decoded_rows_path=args.decoded_rows,
                expected_decoded_sha256=args.expected_decoded_sha256,
                output_dir=args.output_dir,
                code_commit=args.code_commit,
            ),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
