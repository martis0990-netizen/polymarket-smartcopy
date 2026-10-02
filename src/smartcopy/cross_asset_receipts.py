"""Bind amended v5 wallet evidence to fee-aware Polygon execution roles."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from smartcopy.correction_overlay import load_wallet_evidence
from smartcopy.cross_asset_intake import _bound_json, _sha256, _line
from smartcopy.maker_taker import PolygonReceiptAPI, collect_receipts, summarize
from smartcopy.prospective_receipts import decode_prospective_rows, _prospective_summary

_SCHEMA = "smartcopy-bonereaper-cross-asset-receipts-v1"
_ASSETS = ("btc", "eth", "sol", "xrp", "bnb", "doge", "hype")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def run_v5_receipts(*, bundle_dir: str | Path, intake_dir: str | Path,
                    expected_intake_sha256: str, output_dir: str | Path,
                    api: PolygonReceiptAPI, code_commit: str,
                    batch_size: int = 25) -> dict[str, Any]:
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite receipt directory: {output}")
    intake = _bound_json(Path(intake_dir) / "cross_asset_intake_manifest.json", expected_intake_sha256)
    if intake.get("schema_version") != "smartcopy-bonereaper-cross-asset-intake-v1" or intake.get("confirmed_labels") != 0:
        raise ValueError("expected unlabelled v5 intake")
    root = Path(bundle_dir)
    _bound_json(root / "cross_asset_capture_manifest.json", intake["capture_manifest_sha256"])
    wallet_path = root / "wallet" / "live_activity.jsonl"
    wallet_sha = intake["wallet_activity_sha256"]
    if _sha256(wallet_path) != wallet_sha:
        raise ValueError("v5 wallet activity changed since intake")
    evidence = load_wallet_evidence(
        wallet_path, expected_sha256=wallet_sha, skip_unsupported_markets=True,
        allow_empty=True, allowed_assets=_ASSETS, skip_non_buy=True,
    )
    hashes = {fill.transaction_hash for fill in evidence.rows}
    chain_id, envelopes = collect_receipts(api, hashes, batch_size=batch_size)
    if chain_id != 137:
        raise ValueError("expected Polygon chain ID 137")
    rows = decode_prospective_rows(evidence.rows, envelopes)
    legacy = summarize(rows, market_slugs={condition: spec.slug for condition, spec in evidence.specs.items()})
    summary = _prospective_summary(legacy)
    summary["schema_version"] = _SCHEMA
    summary["cohort"] = {"core_assets": list(_ASSETS[:-1]), "hype": "ENGINEERING_ONLY"}

    output.mkdir(parents=True)
    raw_path = output / "receipt_responses_raw.jsonl"
    rows_path = output / "maker_taker_rows.jsonl"
    summary_path = output / "maker_taker_summary.json"
    for path, values in ((raw_path, envelopes), (rows_path, rows)):
        with path.open("xb") as handle:
            for row in values:
                handle.write(_line(row))
    summary_path.write_bytes(_line(summary))
    manifest = {
        "schema_version": _SCHEMA,
        "code_commit": code_commit,
        "collection_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "intake_manifest_sha256": expected_intake_sha256,
        "capture_manifest_sha256": intake["capture_manifest_sha256"],
        "wallet_activity_sha256": wallet_sha,
        "chain_id": chain_id,
        "rpc_transport": "polygon_json_rpc",
        "selected_buy_rows": len(evidence.rows),
        "selected_unique_transactions": len(hashes),
        "decoded_rows": len(rows),
        "core_conditions": sum(spec.asset in {asset.upper() for asset in _ASSETS[:-1]} for spec in evidence.specs.values()),
        "hype_engineering_conditions": sum(spec.asset == "HYPE" for spec in evidence.specs.values()),
        "artifacts": {path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
                      for path in (raw_path, rows_path, summary_path)},
    }
    (output / "cross_asset_receipts_manifest.json").write_bytes(_line(manifest))
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--intake-dir", required=True)
    parser.add_argument("--expected-intake-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--rpc-url", default=os.environ.get("POLYGON_RPC_URL"))
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args(argv)
    if not args.rpc_url:
        parser.error("set POLYGON_RPC_URL or pass --rpc-url")
    manifest = run_v5_receipts(
        bundle_dir=args.bundle_dir, intake_dir=args.intake_dir,
        expected_intake_sha256=args.expected_intake_sha256,
        output_dir=args.output_dir, api=PolygonReceiptAPI(args.rpc_url),
        code_commit=args.code_commit, batch_size=args.batch_size,
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
