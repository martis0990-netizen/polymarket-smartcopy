"""Bind prospective Bonereaper pre-open labels to the frozen v4 candidates."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

from smartcopy.correction_overlay import MarketSpec, market_spec
from smartcopy.external_signal import BinanceKline, BinanceSpotAPI, normalize_binance_response
from smartcopy.preopen_model_competition import (
    evaluate_preopen_candidates,
    summarize_model_competition,
)
from smartcopy.preopen_signal import collapse_preopen_taker
from smartcopy.prospective_analysis import (
    _iso_ms,
    _load_json_sha,
    _load_jsonl_sha,
    group_receipt_episodes,
    load_chainlink_events,
)

_SCHEMA = "smartcopy-bonereaper-preopen-model-analysis-v4"
_CONTRACT_COMMIT = "70d6772a5f8ea671f2b2477509d957d25a1d2360"
_CAPTURE_SCHEMA = "smartcopy-bonereaper-preopen-model-capture-v1"
_CAPTURE_CONTRACT_COMMIT = "PENDING_CAPTURE_CONTRACT"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def collect_v4_binance(
    api: BinanceSpotAPI,
    decisions: Sequence[dict[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], dict[tuple[str, str], tuple[BinanceKline, ...]]]:
    """Collect bounded one-second and native HTF bars for candidate decisions."""

    if not decisions:
        return (), {}
    envelopes: list[dict[str, Any]] = []
    output: dict[tuple[str, str], tuple[BinanceKline, ...]] = {}
    by_asset: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for decision in decisions:
        by_asset[str(decision["asset"])].append(decision)

    for asset, asset_decisions in sorted(by_asset.items()):
        symbol = f"{asset}USDT"
        seconds = [int(row["source_second"]) for row in asset_decisions]
        one_second, one_envelopes = _collect_range(
            api,
            symbol=symbol,
            interval="1s",
            start_time_ms=(min(seconds) - 601) * 1_000,
            end_time_ms=max(seconds) * 1_000 - 1,
            page_step_ms=1_000,
        )
        output[(symbol, "1s")] = one_second
        envelopes.extend(one_envelopes)
        for horizon, duration_ms in (("5m", 300_000), ("15m", 900_000)):
            relevant = [
                int(row["source_second"])
                for row in asset_decisions
                if str(row["horizon"]) == horizon
            ]
            if not relevant:
                continue
            htf, htf_envelopes = _collect_range(
                api,
                symbol=symbol,
                interval=horizon,
                start_time_ms=min(relevant) * 1_000 - 102 * duration_ms,
                end_time_ms=max(relevant) * 1_000 - 1,
                page_step_ms=duration_ms,
            )
            output[(symbol, horizon)] = htf
            envelopes.extend(htf_envelopes)
    return tuple(envelopes), output


def build_model_rows(
    *,
    specs: dict[str, MarketSpec],
    episodes: dict[str, tuple[dict[str, Any], ...]],
    chainlink: dict[str, tuple[dict[str, Any], ...]],
    binance: dict[tuple[str, str], tuple[BinanceKline, ...]],
    capture_started_ms: int,
    capture_ended_ms: int,
    confirmatory_capture: bool,
) -> tuple[dict[str, Any], ...]:
    rows: list[dict[str, Any]] = []
    for condition_id, spec in sorted(specs.items(), key=lambda item: item[1].window_start):
        label = collapse_preopen_taker(
            episodes.get(condition_id, ()), market_start=spec.window_start
        )
        if label is None:
            continue
        source_second = int(label["source_second"])
        symbol = f"{spec.asset}USDT"
        candidate = evaluate_preopen_candidates(
            label=str(label["outcome"]),
            source_second=source_second,
            market_end=spec.window_end,
            one_second_bars=binance.get((symbol, "1s"), ()),
            htf_bars=binance.get((symbol, spec.horizon), ()),
            chainlink_rows=chainlink.get(
                "btc/usd" if spec.asset == "BTC" else "eth/usd", ()
            ),
        )
        coverage_ok = (
            capture_started_ms <= spec.window_start * 1_000 - 660_000
            and capture_ended_ms >= spec.window_start * 1_000
        )
        rows.append(
            {
                "condition_id": condition_id,
                "slug": spec.slug,
                "asset": spec.asset,
                "horizon": spec.horizon,
                "market_start": spec.window_start,
                "confirmatory_eligible": confirmatory_capture and coverage_ok,
                "exclusion_reasons": [
                    reason
                    for reason, excluded in (
                        ("PRECONTRACT_CAPTURE", not confirmatory_capture),
                        ("INSUFFICIENT_11M_CAPTURE", not coverage_ok),
                    )
                    if excluded
                ],
                "primary_preopen_taker": label,
                **candidate,
            }
        )
    return tuple(rows)


def run_model_analysis(
    *,
    bundle_dir: str | Path,
    expected_bundle_manifest_sha256: str,
    receipts_dir: str | Path,
    expected_receipt_rows_sha256: str,
    output_dir: str | Path,
    code_commit: str,
    api: BinanceSpotAPI | None = None,
) -> dict[str, Any]:
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output}")
    bundle = Path(bundle_dir)
    manifest_path = bundle / "prospective_bundle_manifest.json"
    if not manifest_path.exists():
        manifest_path = bundle / "preopen_model_capture_manifest.json"
    manifest = _load_json_sha(
        manifest_path, expected_bundle_manifest_sha256, "capture manifest"
    )
    if manifest.get("clean_finalize") is not True:
        raise ValueError("capture did not cleanly finalize")
    started_ms = _iso_ms(manifest.get("started_at"), "capture started_at")
    ended_ms = _iso_ms(manifest.get("ended_at"), "capture ended_at")
    chainlink_manifest = _load_json_sha(
        bundle / "chainlink" / "chainlink_twap_manifest.json",
        str(manifest["chainlink"]["sha256"]),
        "Chainlink manifest",
    )
    if chainlink_manifest.get("reconnect_count") != 0:
        raise ValueError("v4 requires zero Chainlink reconnects")
    if (bundle / "chainlink" / "chainlink_twap_gaps.jsonl").read_bytes().strip():
        raise ValueError("v4 requires an empty Chainlink gap artifact")

    receipt_rows_path = Path(receipts_dir) / "maker_taker_rows.jsonl"
    receipt_rows = _load_jsonl_sha(
        receipt_rows_path, expected_receipt_rows_sha256, "receipt rows"
    )
    receipt_summary = json.loads(
        (Path(receipts_dir) / "maker_taker_summary.json").read_text()
    )
    specs = {
        condition_id: market_spec(
            condition_id=condition_id,
            slug=str(values["slug"]),
            title=str(values["slug"]),
        )
        for condition_id, values in receipt_summary["per_market"].items()
    }
    episodes = group_receipt_episodes(receipt_rows)
    decisions = []
    for condition_id, spec in specs.items():
        label = collapse_preopen_taker(
            episodes.get(condition_id, ()), market_start=spec.window_start
        )
        if label:
            decisions.append(
                {
                    "asset": spec.asset,
                    "horizon": spec.horizon,
                    "source_second": int(label["source_second"]),
                }
            )
    envelopes, binance = collect_v4_binance(api or BinanceSpotAPI(), decisions)
    chainlink = load_chainlink_events(bundle / "chainlink" / "chainlink_twap_raw.jsonl")
    confirmatory = (
        manifest.get("schema_version") == _CAPTURE_SCHEMA
        and manifest.get("contract_commit") == _CAPTURE_CONTRACT_COMMIT
    )
    rows = build_model_rows(
        specs=specs,
        episodes=episodes,
        chainlink=chainlink,
        binance=binance,
        capture_started_ms=started_ms,
        capture_ended_ms=ended_ms,
        confirmatory_capture=confirmatory,
    )
    summary = summarize_model_competition(
        [row for row in rows if row["confirmatory_eligible"]]
    )
    summary["engineering_smoke_rows"] = len(rows)
    summary["excluded_precontract_rows"] = sum(
        not row["confirmatory_eligible"] for row in rows
    )

    output.mkdir(parents=True)
    binance_path = output / "binance_v4_raw.jsonl"
    rows_path = output / "preopen_model_rows.jsonl"
    summary_path = output / "preopen_model_summary.json"
    analysis_manifest_path = output / "preopen_model_analysis_manifest.json"
    _write_jsonl(binance_path, envelopes)
    _write_jsonl(rows_path, rows)
    _write_json(summary_path, summary)
    analysis_manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "collection_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "capture_manifest": {
            "path": str(manifest_path),
            "sha256": expected_bundle_manifest_sha256,
        },
        "receipt_rows": {
            "path": str(receipt_rows_path),
            "sha256": expected_receipt_rows_sha256,
        },
        "row_count": len(rows),
        "confirmatory_row_count": sum(row["confirmatory_eligible"] for row in rows),
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
            for path in (binance_path, rows_path, summary_path)
        },
    }
    _write_json(analysis_manifest_path, analysis_manifest)
    return {"manifest": analysis_manifest, "summary": summary, "output_dir": str(output)}


def _collect_range(
    api: BinanceSpotAPI,
    *,
    symbol: str,
    interval: str,
    start_time_ms: int,
    end_time_ms: int,
    page_step_ms: int,
) -> tuple[tuple[BinanceKline, ...], tuple[dict[str, Any], ...]]:
    bars: dict[int, BinanceKline] = {}
    envelopes: list[dict[str, Any]] = []
    cursor = start_time_ms
    while cursor <= end_time_ms:
        page_end = min(end_time_ms, cursor + 1_000 * page_step_ms - 1)
        url, payload = api.klines(
            symbol=symbol,
            interval=interval,
            start_time_ms=cursor,
            end_time_ms=page_end,
            limit=1_000,
        )
        envelope = {
            "collection_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "request": {
                "symbol": symbol,
                "interval": interval,
                "start_time_ms": cursor,
                "end_time_ms": page_end,
                "limit": 1_000,
                "url": url,
            },
            "response": payload,
        }
        normalized = normalize_binance_response(envelope)
        for bar in normalized:
            bars[bar.open_time_ms] = bar
        envelopes.append(envelope)
        cursor = page_end + 1
    return tuple(bars[key] for key in sorted(bars)), tuple(envelopes)


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
    parser.add_argument("--bundle-dir", required=True)
    parser.add_argument("--expected-bundle-manifest-sha256", required=True)
    parser.add_argument("--receipts-dir", required=True)
    parser.add_argument("--expected-receipt-rows-sha256", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--code-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_model_analysis(
        bundle_dir=args.bundle_dir,
        expected_bundle_manifest_sha256=args.expected_bundle_manifest_sha256,
        receipts_dir=args.receipts_dir,
        expected_receipt_rows_sha256=args.expected_receipt_rows_sha256,
        output_dir=args.output,
        code_commit=args.code_commit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
