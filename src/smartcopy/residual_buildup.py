"""Source-time state-machine accounting for paired vs residual inventory buildup."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .classify import classify_market
from .models import MarketFamily, ObservationMode, WalletActivity


_TARGET = {MarketFamily.CRYPTO_UPDOWN_5M, MarketFamily.CRYPTO_UPDOWN_15M}


@dataclass(frozen=True, slots=True)
class ResidualBuildupMarket:
    condition_id: str
    market_family: MarketFamily
    total_buy_size: float
    pair_balancing_quantity: float
    residual_increasing_quantity: float
    final_matched_size: float
    final_residual_size: float
    residual_increasing_share: float | None
    first_leg_gap_seconds: float
    first_residual_increasing_time: datetime | None
    first_pair_balancing_time: datetime | None
    dominant_outcome: str | None
    imbalance_sign_flips: int
    max_abs_imbalance_share: float | None
    residual_quantity_q1: float
    residual_quantity_q2: float
    residual_quantity_q3: float
    residual_quantity_q4: float
    residual_quantity_outside: float


def decompose_residual_buildup(
    activities: Iterable[WalletActivity],
) -> tuple[ResidualBuildupMarket, ...]:
    rows = tuple(activities)
    if any(row.observation_mode != ObservationMode.BACKFILL for row in rows):
        raise ValueError("historical residual buildup requires BACKFILL evidence only")

    grouped: dict[str, list[WalletActivity]] = {}
    for row in rows:
        if row.activity_type.upper() != "TRADE" or (row.side or "").upper() != "BUY":
            continue
        if not row.condition_id or not row.asset:
            continue
        family = classify_market(title=row.title, slug=row.slug, event_slug=row.event_slug).family
        if family not in _TARGET:
            continue
        grouped.setdefault(row.condition_id, []).append(row)

    out: list[ResidualBuildupMarket] = []
    for condition_id, market_rows in grouped.items():
        assets = sorted({row.asset for row in market_rows if row.asset})
        if len(assets) != 2:
            continue
        ordered = sorted(
            market_rows,
            key=lambda row: (row.source_event_time, row.transaction_hash or "", row.asset or ""),
        )
        family = classify_market(title=ordered[0].title, slug=ordered[0].slug, event_slug=ordered[0].event_slug).family
        balances = {assets[0]: 0.0, assets[1]: 0.0}
        outcomes = {row.asset: row.outcome for row in ordered}
        first_times: dict[str, datetime] = {}
        pair_qty = 0.0
        residual_qty = 0.0
        first_residual = None
        first_pair = None
        last_nonzero_sign = 0
        flips = 0
        max_abs_imbalance = 0.0
        buckets = [0.0, 0.0, 0.0, 0.0]
        outside = 0.0
        window = _window(ordered[0], family)

        for row in ordered:
            assert row.asset is not None
            own = row.asset
            other = assets[1] if own == assets[0] else assets[0]
            first_times.setdefault(own, row.source_event_time)
            deficit = max(0.0, balances[other] - balances[own])
            balancing = min(row.size, deficit)
            residual = row.size - balancing
            pair_qty += balancing
            residual_qty += residual
            if balancing > 0 and first_pair is None:
                first_pair = row.source_event_time
            if residual > 0:
                if first_residual is None:
                    first_residual = row.source_event_time
                bucket = _quartile(row.source_event_time, window)
                if bucket is None:
                    outside += residual
                else:
                    buckets[bucket] += residual

            balances[own] += row.size
            imbalance = balances[assets[0]] - balances[assets[1]]
            sign = 1 if imbalance > 1e-12 else -1 if imbalance < -1e-12 else 0
            if sign and last_nonzero_sign and sign != last_nonzero_sign:
                flips += 1
            if sign:
                last_nonzero_sign = sign
            max_abs_imbalance = max(max_abs_imbalance, abs(imbalance))

        left, right = balances[assets[0]], balances[assets[1]]
        matched = min(left, right)
        final_residual = abs(left - right)
        total = left + right
        dominant = None
        if left > right + 1e-12:
            dominant = outcomes.get(assets[0])
        elif right > left + 1e-12:
            dominant = outcomes.get(assets[1])
        first_gap = abs((first_times[assets[0]] - first_times[assets[1]]).total_seconds())
        out.append(ResidualBuildupMarket(
            condition_id=condition_id,
            market_family=family,
            total_buy_size=total,
            pair_balancing_quantity=pair_qty,
            residual_increasing_quantity=residual_qty,
            final_matched_size=matched,
            final_residual_size=final_residual,
            residual_increasing_share=(residual_qty / total) if total else None,
            first_leg_gap_seconds=first_gap,
            first_residual_increasing_time=first_residual,
            first_pair_balancing_time=first_pair,
            dominant_outcome=dominant,
            imbalance_sign_flips=flips,
            max_abs_imbalance_share=(max_abs_imbalance / total) if total else None,
            residual_quantity_q1=buckets[0],
            residual_quantity_q2=buckets[1],
            residual_quantity_q3=buckets[2],
            residual_quantity_q4=buckets[3],
            residual_quantity_outside=outside,
        ))
    return tuple(sorted(out, key=lambda item: item.condition_id))


def _window(row: WalletActivity, family: MarketFamily) -> tuple[int, int] | None:
    slug = row.slug or row.event_slug or ""
    try:
        start = int(slug.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None
    duration = 300 if family == MarketFamily.CRYPTO_UPDOWN_5M else 900
    return start, start + duration


def _quartile(time: datetime, window: tuple[int, int] | None) -> int | None:
    if window is None:
        return None
    ts = time.timestamp()
    start, end = window
    if ts < start or ts > end:
        return None
    fraction = (ts - start) / (end - start)
    if fraction >= 1.0:
        return 3
    return min(3, int(fraction * 4))
