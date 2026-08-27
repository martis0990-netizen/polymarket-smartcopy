"""Frozen terminal-value and public merge/redeem analysis for bundle v5 economics."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.request import Request, urlopen

from .models import ObservationMode, WalletActivity
from .polymarket import PolymarketDataAPI

_SCHEMA = "smartcopy-bonereaper-prospective-settlement-v1"
_CONTRACT_COMMIT = "5a1b989ac2a01bb14e63a4c9bca86fb0d73096f1"
_ECONOMICS_SHA = "8c848d320e2cc53e931fb408d493166f7ccb784416a56bcc4e8bdfdb745fb32f"
_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_START = 1787841769
_END = 1787855700
_ACTIVITY_TYPES = "MERGE,REDEEM"
_GAMMA_URL = "https://gamma-api.polymarket.com"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


class ProspectiveSettlementError(RuntimeError):
    """Raised when evidence violates the frozen settlement contract."""


GammaTransport = Callable[[str, dict[str, str]], Any]


def _default_gamma_transport(url: str, headers: dict[str, str]) -> Any:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=25) as response:  # noqa: S310 - fixed host
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network boundary
        raise ProspectiveSettlementError(f"GET {url} failed: {exc}") from exc


def parse_resolution(
    market: Any, *, expected_slug: str, expected_condition_id: str
) -> dict[str, Any]:
    """Validate exact market identity and return an unambiguous binary resolution."""

    if not isinstance(market, dict):
        raise ProspectiveSettlementError(f"Gamma response for {expected_slug} is not an object")
    if str(market.get("slug")) != expected_slug:
        raise ProspectiveSettlementError(f"Gamma slug mismatch for {expected_slug}")
    condition_id = str(market.get("conditionId") or market.get("condition_id") or "").lower()
    if condition_id != expected_condition_id.lower():
        raise ProspectiveSettlementError(f"Gamma condition ID mismatch for {expected_slug}")
    outcomes = _array(market.get("outcomes"), "outcomes", expected_slug)
    prices = _array(market.get("outcomePrices"), "outcomePrices", expected_slug)
    if len(outcomes) != 2 or len(prices) != 2 or len({str(item) for item in outcomes}) != 2:
        return _unresolved(outcomes, prices, bool(market.get("closed")))
    try:
        decimals = [Decimal(str(item)) for item in prices]
    except InvalidOperation:
        return _unresolved(outcomes, prices, bool(market.get("closed")))
    closed = market.get("closed") is True
    if not closed or sorted(decimals) != [Decimal(0), Decimal(1)]:
        return _unresolved(outcomes, prices, closed)
    winner_index = decimals.index(Decimal(1))
    return {
        "resolution_status": "RESOLVED",
        "closed": True,
        "outcomes": [str(item) for item in outcomes],
        "terminal_prices": [_text(item) for item in decimals],
        "winning_outcome": str(outcomes[winner_index]),
        "winning_index": winner_index,
    }


def allocate_terminal(economics: dict[str, Any], resolution: dict[str, Any]) -> dict[str, Any]:
    """Allocate terminal value to the exact matched and residual economics lots."""

    base = {
        "schema_version": _SCHEMA,
        "condition_id": str(economics["condition_id"]),
        "slug": str(economics["slug"]),
        "asset": economics.get("asset"),
        "window_seconds": economics.get("window_seconds"),
        **resolution,
    }
    residuals = economics.get("residuals")
    if not isinstance(residuals, dict) or set(residuals) != {"Up", "Down"}:
        raise ProspectiveSettlementError("economics residuals must contain exact Up and Down legs")
    sizes = {side: _decimal(residuals[side].get("size"), f"{side} residual size") for side in ("Up", "Down")}
    costs = {
        side: _decimal(residuals[side].get("fee_adjusted_cost"), f"{side} residual cost")
        for side in ("Up", "Down")
    }
    matched_size = _decimal(economics.get("matched_size"), "matched size")
    matched_cost = _decimal(economics.get("fee_adjusted_pair_cost_total"), "matched pair cost")
    acquisition = matched_cost + costs["Up"] + costs["Down"]
    largest = _largest_residual(sizes)
    base.update(
        {
            "matched_size": _text(matched_size),
            "matched_terminal_value": None,
            "residuals": {
                side: {
                    "size": _text(sizes[side]),
                    "fee_adjusted_cost": _text(costs[side]),
                    "terminal_value": None,
                }
                for side in ("Up", "Down")
            },
            "bounded_acquisition_cost": _text(acquisition),
            "bounded_terminal_value": None,
            "bounded_terminal_edge": None,
            "largest_residual_side": largest,
            "largest_residual_aligned_with_winner": None,
        }
    )
    if resolution["resolution_status"] != "RESOLVED":
        return base
    winner = str(resolution["winning_outcome"])
    if winner not in sizes:
        raise ProspectiveSettlementError(f"Gamma outcome {winner!r} does not map to Up/Down")
    residual_terminal = sizes[winner]
    terminal = matched_size + residual_terminal
    for side in ("Up", "Down"):
        base["residuals"][side]["terminal_value"] = _text(sizes[side] if side == winner else Decimal(0))
    base.update(
        {
            "matched_terminal_value": _text(matched_size),
            "bounded_terminal_value": _text(terminal),
            "bounded_terminal_edge": _text(terminal - acquisition),
            "largest_residual_aligned_with_winner": largest == winner if largest else None,
        }
    )
    return base


def run_analysis(
    *,
    economics_conditions_path: str | Path,
    expected_economics_sha256: str,
    output_dir: str | Path,
    code_commit: str,
    client: PolymarketDataAPI | None = None,
    gamma_transport: GammaTransport = _default_gamma_transport,
    gamma_base_url: str = _GAMMA_URL,
) -> dict[str, Any]:
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    if expected_economics_sha256.lower() != _ECONOMICS_SHA:
        raise ProspectiveSettlementError("expected economics SHA differs from frozen contract")
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing analysis directory: {output}")
    economics_path = Path(economics_conditions_path)
    actual_sha = _sha256(economics_path)
    if actual_sha != _ECONOMICS_SHA:
        raise ProspectiveSettlementError(
            f"economics condition rows SHA256 mismatch: expected {_ECONOMICS_SHA}, got {actual_sha}"
        )
    economics_rows = _load_jsonl(economics_path)
    if len(economics_rows) != 5:
        raise ProspectiveSettlementError(f"expected exactly five economics conditions, got {len(economics_rows)}")
    identities = {(str(row.get("condition_id", "")).lower(), str(row.get("slug", ""))) for row in economics_rows}
    if len(identities) != 5 or any(not condition or not slug for condition, slug in identities):
        raise ProspectiveSettlementError("economics conditions are not five unique condition/slug identities")

    headers = {"Accept": "application/json", "User-Agent": "polymarket-smartcopy/0.1"}
    gamma_rows: list[dict[str, Any]] = []
    settlements: list[dict[str, Any]] = []
    for economics in sorted(economics_rows, key=lambda row: str(row["condition_id"])):
        slug = str(economics["slug"])
        market = gamma_transport(f"{gamma_base_url.rstrip('/')}/markets/slug/{slug}", headers)
        gamma_rows.append({"slug": slug, "response": market})
        resolution = parse_resolution(
            market,
            expected_slug=slug,
            expected_condition_id=str(economics["condition_id"]),
        )
        settlements.append(allocate_terminal(economics, resolution))

    activity_client = client or PolymarketDataAPI()
    activity = activity_client.collect_activity_range(
        _WALLET, start=_START, end=_END, activity_type=_ACTIVITY_TYPES
    )
    _validate_activity(activity)
    targets = {condition for condition, _slug in identities}
    target_activity = [_normalized(item) for item in activity if item.condition_id.lower() in targets]
    summary = _summary(settlements, activity, target_activity)

    output.mkdir(parents=True)
    gamma_path = output / "gamma_responses.jsonl"
    activity_raw_path = output / "activity_all_raw.jsonl"
    target_path = output / "target_activity.jsonl"
    settlements_path = output / "condition_settlements.jsonl"
    summary_path = output / "prospective_settlement_summary.json"
    manifest_path = output / "prospective_settlement_manifest.json"
    _write_jsonl(gamma_path, gamma_rows)
    _write_jsonl(activity_raw_path, (item.raw for item in activity))
    _write_jsonl(target_path, target_activity)
    _write_jsonl(settlements_path, settlements)
    _write_json(summary_path, summary)
    artifacts = (gamma_path, activity_raw_path, target_path, settlements_path, summary_path)
    manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "economics_conditions": {"path": str(economics_path), "sha256": actual_sha},
        "activity_contract": {
            "wallet": _WALLET,
            "start": _START,
            "end": _END,
            "types": _ACTIVITY_TYPES,
            "observation_mode": ObservationMode.BACKFILL.value,
        },
        "artifacts": {
            path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)} for path in artifacts
        },
    }
    _write_json(manifest_path, manifest)
    return {"manifest": manifest, "summary": summary, "output_dir": str(output)}


def _summary(
    settlements: Sequence[dict[str, Any]],
    activity: Sequence[WalletActivity],
    target_activity: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    resolved = [row for row in settlements if row["resolution_status"] == "RESOLVED"]
    total_cost = sum((_decimal(row["bounded_acquisition_cost"], "cost") for row in resolved), Decimal(0))
    total_terminal = sum((_decimal(row["bounded_terminal_value"], "terminal") for row in resolved), Decimal(0))
    aligned = [row["largest_residual_aligned_with_winner"] for row in resolved if row["largest_residual_aligned_with_winner"] is not None]
    return {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "study_status": "COLLECTING" if len(resolved) < 30 else "STOPPING_TARGET_MET",
        "resolved_conditions": len(resolved),
        "target_conditions": len(settlements),
        "bounded_acquisition_cost": _text(total_cost),
        "bounded_terminal_value": _text(total_terminal),
        "bounded_terminal_edge": _text(total_terminal - total_cost),
        "largest_residual_alignment": {
            "eligible_conditions": len(aligned),
            "aligned_conditions": sum(value is True for value in aligned),
            "share": _text(Decimal(sum(value is True for value in aligned)) / Decimal(len(aligned))) if aligned else None,
        },
        "activity": {
            "all_rows": len(activity),
            "target_rows": len(target_activity),
            "all_by_type": {kind: sum(item.activity_type == kind for item in activity) for kind in ("MERGE", "REDEEM")},
            "target_by_type": {kind: sum(row["activity_type"] == kind for row in target_activity) for kind in ("MERGE", "REDEEM")},
            "target_distinct_conditions": len({row["condition_id"] for row in target_activity}),
        },
        "interpretation": "BOUNDED_HOLD_TO_RESOLUTION_COUNTERFACTUAL_NOT_REALIZED_WALLET_PNL",
    }


def _validate_activity(rows: Sequence[WalletActivity]) -> None:
    for item in rows:
        timestamp = int(item.source_event_time.timestamp())
        if item.observation_mode is not ObservationMode.BACKFILL:
            raise ProspectiveSettlementError("activity evidence is not BACKFILL")
        if item.proxy_wallet.lower() != _WALLET:
            raise ProspectiveSettlementError("activity wallet mismatch")
        if item.activity_type not in {"MERGE", "REDEEM"}:
            raise ProspectiveSettlementError(f"unexpected activity type {item.activity_type}")
        if not _START <= timestamp <= _END:
            raise ProspectiveSettlementError("activity row outside frozen interval")


def _normalized(item: WalletActivity) -> dict[str, Any]:
    return {
        "condition_id": item.condition_id.lower(),
        "activity_type": item.activity_type,
        "source_event_time": item.source_event_time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "transaction_hash": item.transaction_hash,
        "size": item.size,
        "usdc_size": item.usdc_size,
        "asset": item.asset,
        "outcome": item.outcome,
        "slug": item.slug,
        "observation_mode": item.observation_mode.value,
    }


def _array(value: Any, field: str, slug: str) -> list[Any]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ProspectiveSettlementError(f"Gamma {field} is invalid JSON for {slug}") from exc
    if not isinstance(value, list):
        raise ProspectiveSettlementError(f"Gamma {field} is not an array for {slug}")
    return value


def _unresolved(outcomes: list[Any], prices: list[Any], closed: bool) -> dict[str, Any]:
    return {
        "resolution_status": "UNRESOLVED_OR_AMBIGUOUS",
        "closed": closed,
        "outcomes": [str(item) for item in outcomes],
        "terminal_prices": [str(item) for item in prices],
        "winning_outcome": None,
        "winning_index": None,
    }


def _largest_residual(sizes: dict[str, Decimal]) -> str | None:
    if sizes["Up"] == sizes["Down"]:
        return None
    return "Up" if sizes["Up"] > sizes["Down"] else "Down"


def _decimal(value: Any, label: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ProspectiveSettlementError(f"invalid {label}") from exc
    if not result.is_finite() or result < 0:
        raise ProspectiveSettlementError(f"{label} must be finite and non-negative")
    return result


def _text(value: Decimal) -> str:
    return format(value, "f")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if any(not isinstance(row, dict) for row in rows):
        raise ProspectiveSettlementError(f"{path} contains a non-object row")
    return rows


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    path.write_text("".join(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n" for row in rows))


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--economics-conditions", required=True)
    parser.add_argument("--expected-economics-sha256", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--code-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = run_analysis(
        economics_conditions_path=args.economics_conditions,
        expected_economics_sha256=args.expected_economics_sha256,
        output_dir=args.output_dir,
        code_commit=args.code_commit,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
