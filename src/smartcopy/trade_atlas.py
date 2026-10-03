"""Deterministic source-time trade atlas for Bonereaper reverse engineering.

The atlas reconstructs inventory state before and after every frozen historical BUY fill.
It is descriptive evidence only: no market-state controls, trigger inference, PnL labels,
or copy decisions are produced here.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable, Sequence

from .classify import classify_market
from .historical import (
    FROZEN_END,
    FROZEN_NORMALIZED_SHA256,
    FROZEN_START,
    FROZEN_WALLET,
    HistoricalEvidenceError,
    load_normalized_activity_jsonl,
)
from .models import MarketFamily, ObservationMode, WalletActivity

ATLAS_SCHEMA_VERSION = "bonereaper-reverse-engineering-atlas-v1"
_TARGET_FAMILIES = {MarketFamily.CRYPTO_UPDOWN_5M, MarketFamily.CRYPTO_UPDOWN_15M}
_BTC = re.compile(r"\b(?:bitcoin|btc)\b", re.I)
_ETH = re.compile(r"\b(?:ethereum|eth)\b", re.I)
_EPS = 1e-12
_STEPS_FILE = "trade_atlas_steps.jsonl"
_MARKETS_FILE = "trade_atlas_markets.jsonl"
_SUMMARY_FILE = "trade_atlas_summary.json"


class AtlasEvidenceError(ValueError):
    """Frozen activity cannot satisfy the reverse-engineering atlas contract."""


class ActionRole(StrEnum):
    PAIR_BALANCE = "PAIR_BALANCE"
    RESIDUAL_INCREASE = "RESIDUAL_INCREASE"
    BALANCE_THEN_RESIDUAL = "BALANCE_THEN_RESIDUAL"


class MarketPhase(StrEnum):
    PRE_WINDOW = "PRE_WINDOW"
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"
    POST_WINDOW = "POST_WINDOW"


@dataclass(frozen=True, slots=True)
class AtlasStep:
    condition_id: str
    symbol: str
    market_family: MarketFamily
    title: str | None
    slug: str | None
    event_slug: str | None
    fill_index: int
    source_event_time: datetime
    market_start_time: datetime
    market_end_time: datetime
    market_phase: MarketPhase
    seconds_from_market_start: float
    seconds_to_market_end: float
    transaction_hash: str | None
    asset: str
    outcome: str
    price: float
    size: float
    usdc_size: float
    up_balance_before: float
    down_balance_before: float
    matched_before: float
    residual_outcome_before: str | None
    residual_size_before: float
    up_vwap_before: float | None
    down_vwap_before: float | None
    pair_vwap_sum_before: float | None
    balancing_quantity: float
    residual_increasing_quantity: float
    action_role: ActionRole
    up_balance_after: float
    down_balance_after: float
    matched_after: float
    residual_outcome_after: str | None
    residual_size_after: float
    up_vwap_after: float | None
    down_vwap_after: float | None
    pair_vwap_sum_after: float | None
    residual_share_after: float


@dataclass(frozen=True, slots=True)
class AtlasMarket:
    condition_id: str
    symbol: str
    market_family: MarketFamily
    title: str | None
    slug: str | None
    event_slug: str | None
    fill_count: int
    up_fill_count: int
    down_fill_count: int
    up_quantity: float
    down_quantity: float
    pair_balance_fill_count: int
    residual_increase_fill_count: int
    balance_then_residual_fill_count: int
    final_matched_size: float
    final_residual_outcome: str | None
    final_residual_size: float
    final_residual_share: float
    imbalance_sign_flips: int
    max_abs_residual_share: float
    first_source_event_time: datetime
    last_source_event_time: datetime
    activity_span_seconds: float
    role_sequence_signature: str
    outcome_sequence_signature: str
    transition_counts: tuple[tuple[str, int], ...]


def build_trade_atlas(
    activities: Iterable[WalletActivity],
    *,
    start: datetime = FROZEN_START,
    end: datetime = FROZEN_END,
) -> tuple[tuple[AtlasStep, ...], tuple[AtlasMarket, ...], dict[str, Any]]:
    """Reconstruct deterministic per-fill inventory state for the frozen target universe."""

    start = _aware_utc(start, "start")
    end = _aware_utc(end, "end")
    if start > end:
        raise AtlasEvidenceError("start must be <= end")

    grouped: dict[str, list[WalletActivity]] = {}
    for row in activities:
        if row.observation_mode != ObservationMode.BACKFILL:
            raise AtlasEvidenceError("reverse-engineering atlas accepts BACKFILL evidence only")
        source_time = _aware_utc(row.source_event_time, "source_event_time")
        if not start <= source_time <= end:
            raise AtlasEvidenceError("source activity lies outside the frozen atlas interval")
        if row.activity_type.upper() != "TRADE" or (row.side or "").upper() != "BUY":
            continue
        classification = classify_market(title=row.title, slug=row.slug, event_slug=row.event_slug)
        if classification.family not in _TARGET_FAMILIES or _target_symbol(row) is None:
            continue
        if row.price is None:
            raise AtlasEvidenceError(f"target BUY has no price: {row.condition_id}")
        if row.size <= 0:
            raise AtlasEvidenceError(f"target BUY has non-positive size: {row.condition_id}")
        if not row.condition_id or not row.asset:
            raise AtlasEvidenceError("target BUY requires condition_id and asset")
        grouped.setdefault(row.condition_id, []).append(row)

    all_steps: list[AtlasStep] = []
    markets: list[AtlasMarket] = []
    excluded_asset_count = 0
    excluded_outcome_count = 0

    for condition_id, rows in grouped.items():
        assets = sorted({row.asset for row in rows if row.asset})
        if len(assets) != 2:
            excluded_asset_count += 1
            continue
        outcome_by_asset = _outcome_map(rows)
        if set(outcome_by_asset.values()) != {"Up", "Down"}:
            excluded_outcome_count += 1
            continue

        ordered = sorted(rows, key=_fill_sort_key)
        steps, market = _build_market(condition_id, ordered, outcome_by_asset)
        all_steps.extend(steps)
        markets.append(market)

    all_steps.sort(key=lambda item: (item.condition_id, item.fill_index))
    markets.sort(key=lambda item: (item.condition_id, item.symbol, item.market_family.value))

    role_counts = Counter(step.action_role.value for step in all_steps)
    phase_counts = Counter(step.market_phase.value for step in all_steps)
    transition_counts: Counter[str] = Counter()
    for market in markets:
        transition_counts.update(dict(market.transition_counts))

    summary: dict[str, Any] = {
        "schema_version": ATLAS_SCHEMA_VERSION,
        "market_count": len(markets),
        "step_count": len(all_steps),
        "excluded_non_two_asset_market_count": excluded_asset_count,
        "excluded_ambiguous_outcome_market_count": excluded_outcome_count,
        "action_role_counts": dict(sorted(role_counts.items())),
        "market_phase_counts": dict(sorted(phase_counts.items())),
        "transition_counts": dict(sorted(transition_counts.items())),
        "markets_final_residual_up": sum(m.final_residual_outcome == "Up" for m in markets),
        "markets_final_residual_down": sum(m.final_residual_outcome == "Down" for m in markets),
        "markets_final_flat": sum(m.final_residual_outcome is None for m in markets),
        "markets_with_sign_flip": sum(m.imbalance_sign_flips > 0 for m in markets),
        "claims": "SOURCE_TIME_DESCRIPTIVE_ONLY",
    }
    return tuple(all_steps), tuple(markets), summary


def write_trade_atlas_artifacts(
    *,
    normalized_activity_path: str | Path,
    output_dir: str | Path,
    expected_sha256: str = FROZEN_NORMALIZED_SHA256,
    start: datetime = FROZEN_START,
    end: datetime = FROZEN_END,
) -> dict[str, Any]:
    """Create immutable atlas artifacts bound to the exact frozen normalized activity file."""

    source = Path(normalized_activity_path)
    if not source.is_file():
        raise AtlasEvidenceError(f"normalized activity file not found: {source}")
    digest = _sha256(source)
    if digest != expected_sha256:
        raise AtlasEvidenceError(
            f"normalized activity SHA256 mismatch: expected {expected_sha256}, got {digest}"
        )

    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    steps_path = root / _STEPS_FILE
    markets_path = root / _MARKETS_FILE
    summary_path = root / _SUMMARY_FILE
    for target in (steps_path, markets_path, summary_path):
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing atlas artifact: {target}")

    activities = load_normalized_activity_jsonl(source)
    wallets = {row.proxy_wallet for row in activities}
    if wallets != {FROZEN_WALLET}:
        raise AtlasEvidenceError(f"frozen wallet mismatch: {sorted(wallets)}")

    steps, markets, summary = build_trade_atlas(activities, start=start, end=end)

    with steps_path.open("xb") as handle:
        for step in steps:
            handle.write(_json_line(_step_dict(step)))
        handle.flush()
    with markets_path.open("xb") as handle:
        for market in markets:
            handle.write(_json_line(_market_dict(market)))
        handle.flush()

    payload = dict(summary)
    payload.update(
        {
            "wallet": FROZEN_WALLET,
            "range": {"start": _iso(start), "end": _iso(end)},
            "input": {
                "path": source.name,
                "sha256": digest,
                "bytes": source.stat().st_size,
            },
            "artifacts": {
                "steps": _artifact_record(steps_path),
                "markets": _artifact_record(markets_path),
            },
        }
    )
    with summary_path.open("xb") as handle:
        handle.write(_json_line(payload))
        handle.flush()
    return payload


def _build_market(
    condition_id: str,
    rows: list[WalletActivity],
    outcome_by_asset: dict[str, str],
) -> tuple[list[AtlasStep], AtlasMarket]:
    first = rows[0]
    family = classify_market(title=first.title, slug=first.slug, event_slug=first.event_slug).family
    symbol = _target_symbol(first)
    if symbol is None or family not in _TARGET_FAMILIES:
        raise AtlasEvidenceError("target market lost classification")
    market_start, market_end = _market_window(first, family)

    balances = {"Up": 0.0, "Down": 0.0}
    notionals = {"Up": 0.0, "Down": 0.0}
    quantities = {"Up": 0.0, "Down": 0.0}
    steps: list[AtlasStep] = []
    signs: list[int] = []
    max_residual_share = 0.0

    for fill_index, row in enumerate(rows, start=1):
        assert row.asset is not None and row.price is not None
        outcome = outcome_by_asset[row.asset]
        other = "Down" if outcome == "Up" else "Up"

        up_before = balances["Up"]
        down_before = balances["Down"]
        matched_before = min(up_before, down_before)
        residual_before, residual_size_before = _residual(up_before, down_before)
        up_vwap_before = _vwap(notionals["Up"], quantities["Up"])
        down_vwap_before = _vwap(notionals["Down"], quantities["Down"])
        pair_before = _pair_sum(up_vwap_before, down_vwap_before)

        deficit = max(0.0, balances[other] - balances[outcome])
        balancing = min(row.size, deficit)
        residual_increasing = row.size - balancing
        role = _role(balancing, residual_increasing)

        balances[outcome] += row.size
        quantities[outcome] += row.size
        notionals[outcome] += row.price * row.size

        up_after = balances["Up"]
        down_after = balances["Down"]
        matched_after = min(up_after, down_after)
        residual_after, residual_size_after = _residual(up_after, down_after)
        up_vwap_after = _vwap(notionals["Up"], quantities["Up"])
        down_vwap_after = _vwap(notionals["Down"], quantities["Down"])
        pair_after = _pair_sum(up_vwap_after, down_vwap_after)
        total_after = up_after + down_after
        residual_share_after = residual_size_after / total_after if total_after else 0.0
        max_residual_share = max(max_residual_share, residual_share_after)

        imbalance = up_after - down_after
        sign = 1 if imbalance > _EPS else -1 if imbalance < -_EPS else 0
        signs.append(sign)

        source_time = _aware_utc(row.source_event_time, "source_event_time")
        seconds_from_start = (source_time - market_start).total_seconds()
        seconds_to_end = (market_end - source_time).total_seconds()

        steps.append(
            AtlasStep(
                condition_id=condition_id,
                symbol=symbol,
                market_family=family,
                title=first.title,
                slug=first.slug,
                event_slug=first.event_slug,
                fill_index=fill_index,
                source_event_time=source_time,
                market_start_time=market_start,
                market_end_time=market_end,
                market_phase=_market_phase(source_time, market_start, market_end),
                seconds_from_market_start=seconds_from_start,
                seconds_to_market_end=seconds_to_end,
                transaction_hash=row.transaction_hash,
                asset=row.asset,
                outcome=outcome,
                price=row.price,
                size=row.size,
                usdc_size=row.usdc_size,
                up_balance_before=up_before,
                down_balance_before=down_before,
                matched_before=matched_before,
                residual_outcome_before=residual_before,
                residual_size_before=residual_size_before,
                up_vwap_before=up_vwap_before,
                down_vwap_before=down_vwap_before,
                pair_vwap_sum_before=pair_before,
                balancing_quantity=balancing,
                residual_increasing_quantity=residual_increasing,
                action_role=role,
                up_balance_after=up_after,
                down_balance_after=down_after,
                matched_after=matched_after,
                residual_outcome_after=residual_after,
                residual_size_after=residual_size_after,
                up_vwap_after=up_vwap_after,
                down_vwap_after=down_vwap_after,
                pair_vwap_sum_after=pair_after,
                residual_share_after=residual_share_after,
            )
        )

    flips = _sign_flips(signs)
    role_values = [step.action_role.value for step in steps]
    outcome_values = [step.outcome for step in steps]
    transitions = Counter(
        f"{left}->{right}" for left, right in zip(role_values, role_values[1:])
    )
    final_residual, final_residual_size = _residual(balances["Up"], balances["Down"])
    total = balances["Up"] + balances["Down"]
    market = AtlasMarket(
        condition_id=condition_id,
        symbol=symbol,
        market_family=family,
        title=first.title,
        slug=first.slug,
        event_slug=first.event_slug,
        fill_count=len(steps),
        up_fill_count=sum(step.outcome == "Up" for step in steps),
        down_fill_count=sum(step.outcome == "Down" for step in steps),
        up_quantity=balances["Up"],
        down_quantity=balances["Down"],
        pair_balance_fill_count=sum(step.action_role == ActionRole.PAIR_BALANCE for step in steps),
        residual_increase_fill_count=sum(
            step.action_role == ActionRole.RESIDUAL_INCREASE for step in steps
        ),
        balance_then_residual_fill_count=sum(
            step.action_role == ActionRole.BALANCE_THEN_RESIDUAL for step in steps
        ),
        final_matched_size=min(balances["Up"], balances["Down"]),
        final_residual_outcome=final_residual,
        final_residual_size=final_residual_size,
        final_residual_share=(final_residual_size / total) if total else 0.0,
        imbalance_sign_flips=flips,
        max_abs_residual_share=max_residual_share,
        first_source_event_time=steps[0].source_event_time,
        last_source_event_time=steps[-1].source_event_time,
        activity_span_seconds=(steps[-1].source_event_time - steps[0].source_event_time).total_seconds(),
        role_sequence_signature=_rle(role_values),
        outcome_sequence_signature=_rle(outcome_values),
        transition_counts=tuple(sorted(transitions.items())),
    )
    return steps, market


def _fill_sort_key(row: WalletActivity) -> tuple[Any, ...]:
    return (
        row.source_event_time,
        row.transaction_hash or "",
        row.asset or "",
        row.price is None,
        row.price if row.price is not None else 0.0,
        row.size,
    )


def _outcome_map(rows: list[WalletActivity]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for row in rows:
        assert row.asset is not None
        outcome = _canonical_outcome(row.outcome)
        if outcome is None:
            return {}
        previous = mapping.setdefault(row.asset, outcome)
        if previous != outcome:
            raise AtlasEvidenceError(
                f"asset maps to conflicting outcomes in {row.condition_id}: {row.asset}"
            )
    return mapping


def _role(balancing: float, residual: float) -> ActionRole:
    if balancing > _EPS and residual > _EPS:
        return ActionRole.BALANCE_THEN_RESIDUAL
    if balancing > _EPS:
        return ActionRole.PAIR_BALANCE
    if residual > _EPS:
        return ActionRole.RESIDUAL_INCREASE
    raise AtlasEvidenceError("positive BUY fill produced no inventory transition")


def _residual(up: float, down: float) -> tuple[str | None, float]:
    if up > down + _EPS:
        return "Up", up - down
    if down > up + _EPS:
        return "Down", down - up
    return None, 0.0


def _vwap(notional: float, quantity: float) -> float | None:
    return notional / quantity if quantity > _EPS else None


def _pair_sum(up: float | None, down: float | None) -> float | None:
    return up + down if up is not None and down is not None else None


def _sign_flips(signs: list[int]) -> int:
    previous = 0
    flips = 0
    for sign in signs:
        if sign == 0:
            continue
        if previous and sign != previous:
            flips += 1
        previous = sign
    return flips


def _rle(values: list[str]) -> str:
    if not values:
        return ""
    parts: list[str] = []
    current = values[0]
    count = 1
    for value in values[1:]:
        if value == current:
            count += 1
            continue
        parts.append(f"{current}*{count}" if count > 1 else current)
        current = value
        count = 1
    parts.append(f"{current}*{count}" if count > 1 else current)
    return ">".join(parts)


def _market_window(row: WalletActivity, family: MarketFamily) -> tuple[datetime, datetime]:
    slug = row.slug or row.event_slug or ""
    try:
        start_unix = int(slug.rsplit("-", 1)[1])
    except (IndexError, ValueError) as exc:
        raise AtlasEvidenceError(f"target market slug lacks epoch suffix: {slug!r}") from exc
    duration = 300 if family == MarketFamily.CRYPTO_UPDOWN_5M else 900
    start = datetime.fromtimestamp(start_unix, tz=timezone.utc)
    return start, datetime.fromtimestamp(start_unix + duration, tz=timezone.utc)


def _market_phase(time: datetime, start: datetime, end: datetime) -> MarketPhase:
    if time < start:
        return MarketPhase.PRE_WINDOW
    if time > end:
        return MarketPhase.POST_WINDOW
    duration = (end - start).total_seconds()
    fraction = (time - start).total_seconds() / duration
    if fraction < 0.25:
        return MarketPhase.Q1
    if fraction < 0.50:
        return MarketPhase.Q2
    if fraction < 0.75:
        return MarketPhase.Q3
    return MarketPhase.Q4


def _target_symbol(item: WalletActivity) -> str | None:
    text = " ".join(part for part in (item.title, item.slug, item.event_slug) if part)
    btc = bool(_BTC.search(text))
    eth = bool(_ETH.search(text))
    if btc == eth:
        return None
    return "BTC" if btc else "ETH"


def _canonical_outcome(value: str | None) -> str | None:
    normalized = value.strip().lower() if value is not None else ""
    return "Up" if normalized == "up" else "Down" if normalized == "down" else None


def _aware_utc(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AtlasEvidenceError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _aware_utc(value, "timestamp").isoformat().replace("+00:00", "Z")


def _step_dict(step: AtlasStep) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name in step.__dataclass_fields__:
        value = getattr(step, name)
        if isinstance(value, datetime):
            payload[name] = _iso(value)
        elif isinstance(value, StrEnum):
            payload[name] = value.value
        else:
            payload[name] = value
    return payload


def _market_dict(market: AtlasMarket) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name in market.__dataclass_fields__:
        value = getattr(market, name)
        if isinstance(value, datetime):
            payload[name] = _iso(value)
        elif isinstance(value, StrEnum):
            payload[name] = value.value
        elif name == "transition_counts":
            payload[name] = dict(value)
        else:
            payload[name] = value
    return payload


def _json_line(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _artifact_record(path: Path) -> dict[str, Any]:
    return {"path": path.name, "sha256": _sha256(path), "bytes": path.stat().st_size}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build frozen Bonereaper reverse-engineering atlas")
    parser.add_argument("--activity", required=True, help="Frozen normalized activity.jsonl")
    parser.add_argument("--output", required=True, help="Fresh output directory")
    parser.add_argument("--expected-sha256", default=FROZEN_NORMALIZED_SHA256)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    payload = write_trade_atlas_artifacts(
        normalized_activity_path=args.activity,
        output_dir=args.output,
        expected_sha256=args.expected_sha256,
    )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
