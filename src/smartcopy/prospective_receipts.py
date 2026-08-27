"""Decode prospective Bonereaper BTC/ETH receipts without Stage 3A sample-size assumptions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from smartcopy.correction_overlay import WalletFill, load_wallet_evidence
from smartcopy.maker_taker import PolygonReceiptAPI, _decode_fill, collect_receipts, summarize

_SCHEMA = "smartcopy-bonereaper-prospective-receipts-v2"
_CONTRACT_COMMIT = "0065f7ca8c38e435e0a859b06724040cfd01a900"
_CHAIN_ID = 137
_RAW = "receipt_responses_raw.jsonl"
_ROWS = "maker_taker_rows.jsonl"
_SUMMARY = "maker_taker_summary.json"
_MANIFEST = "prospective_receipts_manifest.json"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def run_prospective_receipts(
    *,
    wallet_activity_path: str | Path,
    expected_wallet_sha256: str,
    output_dir: str | Path,
    api: PolygonReceiptAPI,
    code_commit: str,
    batch_size: int = 25,
) -> dict[str, Any]:
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output}")
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    source = Path(wallet_activity_path)
    raw_wallet = source.read_bytes()
    wallet_sha = hashlib.sha256(raw_wallet).hexdigest()
    if wallet_sha != expected_wallet_sha256.lower():
        raise ValueError(
            f"wallet activity SHA256 mismatch: expected {expected_wallet_sha256.lower()}, got {wallet_sha}"
        )
    source_rows = sum(bool(line.strip()) for line in raw_wallet.splitlines())
    evidence = load_wallet_evidence(
        source,
        expected_sha256=expected_wallet_sha256,
        skip_unsupported_markets=True,
    )
    transaction_hashes = {fill.transaction_hash for fill in evidence.rows}
    chain_id, envelopes = collect_receipts(api, transaction_hashes, batch_size=batch_size)
    if chain_id != _CHAIN_ID:
        raise ValueError(f"expected Polygon chain id {_CHAIN_ID}, got {chain_id}")
    rows = decode_prospective_rows(evidence.rows, envelopes)
    legacy_summary = summarize(
        rows,
        market_slugs={condition_id: spec.slug for condition_id, spec in evidence.specs.items()},
    )
    summary = _prospective_summary(legacy_summary)

    output.mkdir(parents=True)
    raw_path = output / _RAW
    rows_path = output / _ROWS
    summary_path = output / _SUMMARY
    manifest_path = output / _MANIFEST
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
        "wallet_activity": {
            "path": str(source),
            "sha256": wallet_sha,
            "source_rows": source_rows,
            "selected_btc_eth_rows": len(evidence.rows),
            "selected_unique_transactions": len(transaction_hashes),
            "excluded_unsupported_rows": source_rows - len(evidence.rows),
        },
        "condition_count": len(evidence.specs),
        "receipt_count": len(transaction_hashes),
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in (raw_path, rows_path, summary_path)
        },
    }
    _write_json(manifest_path, manifest)
    return {"manifest": manifest, "summary": summary, "output_dir": str(output)}


def decode_prospective_rows(
    fills: Sequence[WalletFill],
    envelopes: Sequence[dict[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Decode every fill, allowing one transaction to sweep multiple price levels."""

    receipt_by_hash: dict[str, dict[str, Any]] = {}
    for envelope in envelopes:
        request = envelope.get("request")
        response = envelope.get("response")
        if not isinstance(request, dict) or not isinstance(response, dict):
            raise ValueError("malformed JSON-RPC envelope")
        if request.get("method") != "eth_getTransactionReceipt":
            continue
        params = request.get("params")
        receipt = response.get("result")
        if not isinstance(params, list) or len(params) != 1 or not isinstance(receipt, dict):
            raise ValueError("malformed prospective receipt envelope")
        requested = str(params[0]).lower()
        actual = str(receipt.get("transactionHash") or "").lower()
        if requested != actual:
            raise ValueError(f"receipt transaction hash mismatch for {requested}")
        if requested in receipt_by_hash:
            raise ValueError(f"duplicate receipt for {requested}")
        receipt_by_hash[requested] = receipt

    ordered_with_flags = _opposite_flags(fills)
    rows: list[dict[str, Any]] = []
    for fill, opposite in ordered_with_flags:
        receipt = receipt_by_hash.get(fill.transaction_hash.lower())
        if receipt is None:
            raise ValueError(f"no collected receipt for {fill.transaction_hash}")
        rows.append(_decode_fill(fill, receipt, opposite_fill=opposite))
    return tuple(rows)


def _opposite_flags(fills: Sequence[WalletFill]) -> tuple[tuple[WalletFill, bool], ...]:
    by_condition: dict[str, list[WalletFill]] = defaultdict(list)
    for fill in fills:
        by_condition[fill.condition_id].append(fill)
    output: list[tuple[WalletFill, bool]] = []
    for condition_id in sorted(by_condition):
        up_size = 0.0
        down_size = 0.0
        by_second: dict[int, list[WalletFill]] = defaultdict(list)
        for fill in by_condition[condition_id]:
            by_second[fill.source_second].append(fill)
        for second in sorted(by_second):
            dominant = "Up" if up_size > down_size else "Down" if down_size > up_size else None
            second_fills = sorted(
                by_second[second],
                key=lambda fill: (
                    fill.transaction_hash,
                    fill.asset_id,
                    fill.price,
                    fill.size,
                    fill.notional,
                ),
            )
            output.extend(
                (fill, dominant is not None and fill.outcome != dominant)
                for fill in second_fills
            )
            up_size += sum(fill.size for fill in second_fills if fill.outcome == "Up")
            down_size += sum(fill.size for fill in second_fills if fill.outcome == "Down")
    return tuple(output)


def _prospective_summary(decoded: dict[str, Any]) -> dict[str, Any]:
    corrected = decoded["schema_corrected_secondary"]
    per_market: dict[str, Any] = {}
    for condition_id, market in decoded["per_market"].items():
        per_market[condition_id] = {
            "slug": market["slug"],
            "roles": market["schema_corrected_roles"],
            "outcomes": {
                outcome: values["schema_corrected_roles"]
                for outcome, values in market["outcomes"].items()
            },
        }
    return {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "decoder_semantics": "CTF_EXCHANGE_V2_FEE_AWARE",
        "completeness": decoded["completeness"],
        "roles": {
            "all_fills": corrected["all_fills"],
            "opposite_fills": corrected["opposite_fills"],
            "non_opposite_fills": corrected["non_opposite_fills"],
        },
        "per_market": per_market,
        "interpretation_limit": decoded["interpretation_limit"],
    }


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    with path.open("xb") as handle:
        for row in rows:
            handle.write(_json_line(row))


def _write_json(path: Path, value: Any) -> None:
    with path.open("xb") as handle:
        handle.write((json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _json_line(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet-activity", required=True)
    parser.add_argument("--expected-wallet-sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--rpc-url", required=True)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_prospective_receipts(
        wallet_activity_path=args.wallet_activity,
        expected_wallet_sha256=args.expected_wallet_sha256,
        output_dir=args.output,
        api=PolygonReceiptAPI(rpc_url=args.rpc_url),
        code_commit=args.code_commit,
        batch_size=args.batch_size,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
