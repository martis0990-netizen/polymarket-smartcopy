"""Frozen Bonereaper correction/opposite-leg overlay study.

The implementation follows ``docs/BONEREAPER_CORRECTION_OVERLAY_CONTRACT.md``.
It uses source event time for descriptive path alignment only; it is not a live
copyability or execution simulation.
"""

from __future__ import annotations

import argparse
import bisect
import hashlib
import html
import json
import math
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

_SCHEMA = "smartcopy-bonereaper-correction-overlay-v1"
_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_RAW = "market_trades_raw.jsonl"
_ROWS = "correction_rows.jsonl"
_SUMMARY = "correction_summary.json"
_CHART = "correction_overlay.svg"
_MANIFEST = "collection_manifest.json"
_HORIZONS = (5, 15, 30)
_SLUG = re.compile(r"^(btc|eth)-updown-(5m|15m)-(\d+)$")

Transport = Callable[[str, dict[str, str]], Any]


class CorrectionOverlayError(RuntimeError):
    """Raised when the frozen evidence contract cannot be satisfied."""


@dataclass(frozen=True, slots=True)
class MarketSpec:
    condition_id: str
    slug: str
    title: str
    asset: str
    horizon: str
    window_start: int
    window_end: int


@dataclass(frozen=True, slots=True)
class WalletFill:
    condition_id: str
    source_second: int
    source_event_time: str
    outcome: str
    price: float
    size: float
    notional: float
    asset_id: str
    transaction_hash: str

    @property
    def q_fill(self) -> float:
        return self.price if self.outcome == "Up" else 1.0 - self.price


@dataclass(frozen=True, slots=True)
class MarketTrade:
    condition_id: str
    source_second: int
    outcome: str
    price: float
    size: float
    proxy_wallet: str
    asset_id: str
    transaction_hash: str
    side: str

    @property
    def q(self) -> float:
        return self.price if self.outcome == "Up" else 1.0 - self.price


@dataclass(frozen=True, slots=True)
class TapePoint:
    source_second: int
    q: float
    size: float
    trade_count: int


@dataclass(frozen=True, slots=True)
class WalletEvidence:
    sha256: str
    rows: tuple[WalletFill, ...]
    specs: dict[str, MarketSpec]


def _default_transport(url: str, headers: dict[str, str]) -> Any:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed HTTPS host
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network boundary
        raise CorrectionOverlayError(f"GET {url} failed: {exc}") from exc


@dataclass(slots=True)
class PolymarketTradeTapeAPI:
    base_url: str = "https://data-api.polymarket.com"
    transport: Transport = _default_transport
    user_agent: str = "polymarket-smartcopy/0.1"

    def trades_page(self, condition_id: str, *, limit: int, offset: int) -> tuple[dict[str, Any], ...]:
        if not 1 <= limit <= 500:
            raise ValueError("trade page limit must be 1..500")
        if offset < 0:
            raise ValueError("trade offset must be non-negative")
        query = urlencode({"market": condition_id, "limit": limit, "offset": offset})
        url = f"{self.base_url.rstrip('/')}/trades?{query}"
        payload = self.transport(
            url,
            {"Accept": "application/json", "User-Agent": self.user_agent},
        )
        if not isinstance(payload, list):
            raise CorrectionOverlayError(
                f"expected list response for condition {condition_id}, got {type(payload).__name__}"
            )
        if any(not isinstance(row, dict) for row in payload):
            raise CorrectionOverlayError(f"non-object trade row for condition {condition_id}")
        return tuple(dict(row) for row in payload)


def load_wallet_evidence(
    path: str | Path,
    *,
    expected_sha256: str | None = None,
    skip_unsupported_markets: bool = False,
) -> WalletEvidence:
    source = Path(path)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256.lower():
        raise CorrectionOverlayError(
            f"wallet activity SHA256 mismatch: expected {expected_sha256.lower()}, got {digest}"
        )

    fills: list[WalletFill] = []
    specs: dict[str, MarketSpec] = {}
    for line_number, line in enumerate(raw.splitlines(), start=1):
        payload = _decode_json(line, source, line_number)
        wallet = str(payload.get("proxy_wallet") or "").lower()
        if wallet != _WALLET:
            raise CorrectionOverlayError(f"wallet line {line_number}: unexpected proxy_wallet")
        if payload.get("observation_mode") != "live_observed":
            raise CorrectionOverlayError(f"wallet line {line_number}: expected live_observed")
        if payload.get("activity_type") != "TRADE" or payload.get("side") != "BUY":
            raise CorrectionOverlayError(f"wallet line {line_number}: expected TRADE BUY")
        condition_id = _string(payload.get("condition_id"), f"wallet line {line_number} condition_id")
        slug = _string(payload.get("slug"), f"wallet line {line_number} slug")
        title = _string(payload.get("title"), f"wallet line {line_number} title")
        if skip_unsupported_markets and _SLUG.fullmatch(slug) is None:
            continue
        outcome = _outcome(payload.get("outcome"), f"wallet line {line_number} outcome")
        timestamp = _unix_second(payload.get("source_event_time"), f"wallet line {line_number}")
        price = _price(payload.get("price"), f"wallet line {line_number} price")
        size = _positive(payload.get("size"), f"wallet line {line_number} size")
        notional = _positive(payload.get("usdc_size"), f"wallet line {line_number} usdc_size")
        asset_id = _string(payload.get("asset"), f"wallet line {line_number} asset")
        transaction_hash = _string(
            payload.get("transaction_hash"), f"wallet line {line_number} transaction_hash"
        )
        spec = market_spec(condition_id=condition_id, slug=slug, title=title)
        previous = specs.setdefault(condition_id, spec)
        if previous != spec:
            raise CorrectionOverlayError(f"wallet condition {condition_id}: inconsistent market metadata")
        fills.append(
            WalletFill(
                condition_id=condition_id,
                source_second=timestamp,
                source_event_time=_iso_unix(timestamp),
                outcome=outcome,
                price=price,
                size=size,
                notional=notional,
                asset_id=asset_id,
                transaction_hash=transaction_hash,
            )
        )
    if not fills:
        raise CorrectionOverlayError("wallet activity artifact is empty")
    return WalletEvidence(
        sha256=digest,
        rows=tuple(sorted(fills, key=_fill_sort_key)),
        specs=specs,
    )


def market_spec(*, condition_id: str, slug: str, title: str) -> MarketSpec:
    match = _SLUG.fullmatch(slug)
    if match is None:
        raise CorrectionOverlayError(f"unsupported market slug: {slug}")
    asset, horizon, start_text = match.groups()
    duration = 300 if horizon == "5m" else 900
    start = int(start_text)
    return MarketSpec(
        condition_id=condition_id,
        slug=slug,
        title=title,
        asset=asset.upper(),
        horizon=horizon,
        window_start=start,
        window_end=start + duration,
    )


def collect_market_rows(
    api: PolymarketTradeTapeAPI,
    condition_ids: Iterable[str],
    *,
    page_size: int = 500,
    max_offset: int = 5_000,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not 1 <= page_size <= 500:
        raise ValueError("page_size must be 1..500")
    if max_offset < 0 or max_offset % page_size:
        raise ValueError("max_offset must be a non-negative multiple of page_size")
    envelopes: list[dict[str, Any]] = []
    requests: list[dict[str, Any]] = []
    for condition_id in sorted(set(condition_ids)):
        offset = 0
        while True:
            page = api.trades_page(condition_id, limit=page_size, offset=offset)
            requests.append(
                {
                    "condition_id": condition_id,
                    "limit": page_size,
                    "offset": offset,
                    "row_count": len(page),
                }
            )
            for index, row in enumerate(page):
                envelopes.append(
                    {
                        "requested_condition_id": condition_id,
                        "request_offset": offset,
                        "response_index": index,
                        "row": row,
                    }
                )
            if len(page) < page_size:
                break
            if offset == max_offset:
                raise CorrectionOverlayError(
                    f"condition {condition_id} filled final addressable page at offset {max_offset}"
                )
            next_offset = offset + page_size
            if next_offset > max_offset:
                raise CorrectionOverlayError(
                    f"condition {condition_id} requires offset {next_offset} beyond {max_offset}"
                )
            offset = next_offset
    return envelopes, requests


def normalize_market_rows(
    envelopes: Iterable[dict[str, Any]],
    *,
    specs: dict[str, MarketSpec],
) -> tuple[MarketTrade, ...]:
    unique: dict[tuple[Any, ...], MarketTrade] = {}
    for envelope in envelopes:
        requested = _string(envelope.get("requested_condition_id"), "requested_condition_id")
        if requested not in specs:
            raise CorrectionOverlayError(f"unexpected requested condition: {requested}")
        row = envelope.get("row")
        if not isinstance(row, dict):
            raise CorrectionOverlayError("market row envelope must contain an object row")
        actual = _string(row.get("conditionId"), f"trade condition for {requested}")
        if actual != requested:
            raise CorrectionOverlayError(
                f"market filter mismatch: requested {requested}, received {actual}"
            )
        side = _string(row.get("side"), "trade side").upper()
        if side not in {"BUY", "SELL"}:
            raise CorrectionOverlayError("trade side must be BUY or SELL")
        trade = MarketTrade(
            condition_id=actual,
            source_second=_integer(row.get("timestamp"), "trade timestamp"),
            outcome=_outcome(row.get("outcome"), "trade outcome"),
            price=_price(row.get("price"), "trade price"),
            size=_positive(row.get("size"), "trade size"),
            proxy_wallet=_string(row.get("proxyWallet"), "trade proxyWallet").lower(),
            asset_id=_string(row.get("asset"), "trade asset"),
            transaction_hash=_string(row.get("transactionHash"), "trade transactionHash"),
            side=side,
        )
        spec = specs[actual]
        if not spec.window_start <= trade.source_second <= spec.window_end:
            continue
        identity = (
            trade.condition_id,
            trade.source_second,
            trade.transaction_hash,
            trade.proxy_wallet,
            trade.asset_id,
            trade.outcome,
            trade.side,
            trade.price,
            trade.size,
        )
        unique.setdefault(identity, trade)
    return tuple(sorted(unique.values(), key=_trade_sort_key))


def build_independent_tape(
    trades: Iterable[MarketTrade],
    *,
    source_wallet: str = _WALLET,
) -> dict[str, tuple[TapePoint, ...]]:
    grouped: dict[tuple[str, int], list[MarketTrade]] = defaultdict(list)
    for trade in trades:
        if trade.proxy_wallet == source_wallet.lower():
            continue
        grouped[(trade.condition_id, trade.source_second)].append(trade)
    by_condition: dict[str, list[TapePoint]] = defaultdict(list)
    for (condition_id, second), rows in grouped.items():
        total_size = sum(row.size for row in rows)
        q = sum(row.q * row.size for row in rows) / total_size
        by_condition[condition_id].append(
            TapePoint(second, q, total_size, len(rows))
        )
    return {
        condition_id: tuple(sorted(points, key=lambda item: item.source_second))
        for condition_id, points in by_condition.items()
    }


def analyze_fills(
    fills: Sequence[WalletFill],
    tape: dict[str, tuple[TapePoint, ...]],
) -> tuple[dict[str, Any], ...]:
    by_condition: dict[str, list[WalletFill]] = defaultdict(list)
    for fill in fills:
        by_condition[fill.condition_id].append(fill)

    output: list[dict[str, Any]] = []
    for condition_id in sorted(by_condition):
        condition_fills = sorted(by_condition[condition_id], key=_fill_sort_key)
        points = tape.get(condition_id, ())
        times = [point.source_second for point in points]
        up_size = 0.0
        down_size = 0.0
        groups: dict[int, list[WalletFill]] = defaultdict(list)
        for fill in condition_fills:
            groups[fill.source_second].append(fill)

        for second in sorted(groups):
            dominant = "Up" if up_size > down_size else "Down" if down_size > up_size else None
            pre_index = bisect.bisect_left(times, second) - 1
            pre_point = points[pre_index] if pre_index >= 0 else None
            for fill in groups[second]:
                pre_r = _outcome_probability(pre_point.q, fill.outcome) if pre_point else None
                horizons: dict[str, Any] = {}
                for horizon in _HORIZONS:
                    window_start = bisect.bisect_left(times, second - horizon)
                    window_end = bisect.bisect_left(times, second)
                    window = points[window_start:window_end]
                    if not window or pre_r is None:
                        horizons[str(horizon)] = None
                        continue
                    values = [_outcome_probability(point.q, fill.outcome) for point in window]
                    horizons[str(horizon)] = {
                        "point_count": len(window),
                        "correction_depth": max(values) - pre_r,
                        "horizon_change": pre_r - values[0],
                    }
                output.append(
                    {
                        "condition_id": condition_id,
                        "source_event_time": fill.source_event_time,
                        "source_second": second,
                        "outcome": fill.outcome,
                        "source_price": fill.price,
                        "source_size": fill.size,
                        "source_notional": fill.notional,
                        "q_fill": fill.q_fill,
                        "pre_reference_second": pre_point.source_second if pre_point else None,
                        "pre_reference_age_seconds": second - pre_point.source_second if pre_point else None,
                        "pre_reference_q": pre_point.q if pre_point else None,
                        "pre_fill_bought_outcome_probability": pre_r,
                        "pre_dominant_outcome": dominant,
                        "opposite_fill": dominant is not None and fill.outcome != dominant,
                        "pre_up_inventory": up_size,
                        "pre_down_inventory": down_size,
                        "horizons": horizons,
                    }
                )
            up_size += sum(fill.size for fill in groups[second] if fill.outcome == "Up")
            down_size += sum(fill.size for fill in groups[second] if fill.outcome == "Down")
    return tuple(sorted(output, key=lambda row: (row["source_second"], row["condition_id"], row["outcome"])))


def summarize(
    rows: Sequence[dict[str, Any]],
    *,
    tape: dict[str, tuple[TapePoint, ...]],
    specs: dict[str, MarketSpec],
) -> dict[str, Any]:
    all_metrics = _population_metrics(rows)
    opposite_metrics = _population_metrics([row for row in rows if row["opposite_fill"]])
    primary = opposite_metrics["horizons"]["15"]
    share = primary["notional_weighted_correction_ge_1c_share"]
    median_change = primary["notional_weighted_horizon_change_median"]
    if share is None or median_change is None:
        verdict = "INCONCLUSIVE"
    elif share >= 0.60 and median_change < 0:
        verdict = "SUPPORTED_DESCRIPTIVELY"
    elif share <= 0.40 or median_change >= 0:
        verdict = "NOT_SUPPORTED"
    else:
        verdict = "INCONCLUSIVE"

    per_market: dict[str, Any] = {}
    for condition_id in sorted(specs):
        market_rows = [row for row in rows if row["condition_id"] == condition_id]
        per_market[condition_id] = {
            "slug": specs[condition_id].slug,
            "wallet_fill_rows": len(market_rows),
            "wallet_source_seconds": len({row["source_second"] for row in market_rows}),
            "independent_tape_seconds": len(tape.get(condition_id, ())),
            "all_fills": _population_metrics(market_rows),
            "opposite_fills": _population_metrics(
                [row for row in market_rows if row["opposite_fill"]]
            ),
        }

    return {
        "schema_version": _SCHEMA,
        "primary_hypothesis": {
            "verdict": verdict,
            "population": "opposite fills with valid strict-pre 15s tape",
            "correction_threshold": 0.01,
            "required_notional_share": 0.60,
            "not_supported_share_ceiling": 0.40,
            "notional_weighted_correction_ge_1c_share": share,
            "notional_weighted_horizon_change_median": median_change,
        },
        "wallet_fill_rows": len(rows),
        "market_count": len(specs),
        "all_fills": all_metrics,
        "opposite_fills": opposite_metrics,
        "per_market": per_market,
        "interpretation_limit": (
            "Descriptive source-time alignment only; active timing cannot be distinguished "
            "from resting passive bid ladders without order-lifecycle or maker/taker evidence."
        ),
    }


def _population_metrics(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {
        "row_count": len(rows),
        "source_size": sum(float(row["source_size"]) for row in rows),
        "source_notional": sum(float(row["source_notional"]) for row in rows),
        "horizons": {},
    }
    for horizon in _HORIZONS:
        eligible = [row for row in rows if row["horizons"][str(horizon)] is not None]
        result["horizons"][str(horizon)] = _horizon_metrics(eligible, horizon)
    return result


def _horizon_metrics(rows: Sequence[dict[str, Any]], horizon: int) -> dict[str, Any]:
    if not rows:
        return {
            "eligible_rows": 0,
            "eligible_size": 0.0,
            "eligible_notional": 0.0,
            "row_correction_ge_1c_share": None,
            "size_weighted_correction_ge_1c_share": None,
            "notional_weighted_correction_ge_1c_share": None,
            "row_correction_depth_median": None,
            "size_weighted_correction_depth_median": None,
            "notional_weighted_correction_depth_median": None,
            "row_horizon_change_median": None,
            "size_weighted_horizon_change_median": None,
            "notional_weighted_horizon_change_median": None,
        }
    metrics = [row["horizons"][str(horizon)] for row in rows]
    depths = [float(item["correction_depth"]) for item in metrics]
    changes = [float(item["horizon_change"]) for item in metrics]
    sizes = [float(row["source_size"]) for row in rows]
    notionals = [float(row["source_notional"]) for row in rows]
    flags = [depth >= 0.01 for depth in depths]
    return {
        "eligible_rows": len(rows),
        "eligible_size": sum(sizes),
        "eligible_notional": sum(notionals),
        "row_correction_ge_1c_share": sum(flags) / len(flags),
        "size_weighted_correction_ge_1c_share": _weighted_share(flags, sizes),
        "notional_weighted_correction_ge_1c_share": _weighted_share(flags, notionals),
        "row_correction_depth_median": _weighted_median(depths, [1.0] * len(depths)),
        "size_weighted_correction_depth_median": _weighted_median(depths, sizes),
        "notional_weighted_correction_depth_median": _weighted_median(depths, notionals),
        "row_horizon_change_median": _weighted_median(changes, [1.0] * len(changes)),
        "size_weighted_horizon_change_median": _weighted_median(changes, sizes),
        "notional_weighted_horizon_change_median": _weighted_median(changes, notionals),
    }


def render_overlay_svg(
    *,
    specs: dict[str, MarketSpec],
    tape: dict[str, tuple[TapePoint, ...]],
    analysis_rows: Sequence[dict[str, Any]],
) -> str:
    width = 1400
    panel_height = 245
    top = 92
    bottom = 50
    height = top + panel_height * len(specs) + bottom
    left = 105
    right = 40
    plot_width = width - left - right
    price_height = 155
    inventory_top = 181
    inventory_height = 38
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>text{font-family:Inter,Arial,sans-serif}.label{fill:#aeb6c2;font-size:12px}.small{fill:#8993a2;font-size:10px}.title{fill:#eef2f7;font-size:22px;font-weight:700}.market{fill:#eef2f7;font-size:14px;font-weight:600}.tape{fill:none;stroke:#b8c0cc;stroke-width:1.7}.grid{stroke:#2b3441;stroke-width:1}.zero{stroke:#617084;stroke-width:1}.up{fill:#43a5ff;stroke:#bfe2ff;stroke-width:1}.down{fill:#ff9d45;stroke:#ffe0bd;stroke-width:1}.inv{fill:none;stroke:#c779ff;stroke-width:1.5}</style>",
        f'<rect width="{width}" height="{height}" fill="#0d1117"/>',
        '<text x="36" y="38" class="title">Bonereaper fills over independent Polymarket tape</text>',
        '<text x="36" y="62" class="label">Common y-axis: Up-equivalent probability. Tape excludes Bonereaper. Inventory band: cumulative Up size − Down size.</text>',
        '<circle cx="975" cy="36" r="6" class="up"/><text x="988" y="40" class="label">Bonereaper Up BUY</text>',
        '<path d="M1160 30 L1167 42 L1153 42 Z" class="down"/><text x="1175" y="40" class="label">Bonereaper Down BUY</text>',
    ]
    rows_by_condition: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in analysis_rows:
        rows_by_condition[str(row["condition_id"])].append(row)

    for panel_index, condition_id in enumerate(sorted(specs, key=lambda key: specs[key].slug)):
        spec = specs[condition_id]
        y0 = top + panel_index * panel_height

        def x(second: int) -> float:
            return left + (second - spec.window_start) / (spec.window_end - spec.window_start) * plot_width

        def y(q: float) -> float:
            return y0 + (1.0 - q) * price_height

        parts.append(f'<text x="{left}" y="{y0 - 12}" class="market">{html.escape(spec.slug)}</text>')
        parts.append(
            f'<text x="{width-right}" y="{y0 - 12}" text-anchor="end" class="small">{spec.asset} {spec.horizon} · {html.escape(condition_id[:12])}…</text>'
        )
        for q in (0.0, 0.25, 0.5, 0.75, 1.0):
            yy = y(q)
            parts.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{width-right}" y2="{yy:.2f}" class="grid"/>')
            parts.append(f'<text x="{left-12}" y="{yy+4:.2f}" text-anchor="end" class="label">{q:.2f}</text>')
        for fraction in (0.0, 0.25, 0.5, 0.75, 1.0):
            second = round(spec.window_start + fraction * (spec.window_end - spec.window_start))
            xx = x(second)
            parts.append(
                f'<line x1="{xx:.2f}" y1="{y0}" x2="{xx:.2f}" '
                f'y2="{y0+inventory_top+inventory_height:.2f}" class="grid"/>'
            )
            parts.append(f'<text x="{xx:.2f}" y="{y0+price_height+72}" text-anchor="middle" class="small">{_clock(second)}</text>')

        points = tape.get(condition_id, ())
        segment: list[TapePoint] = []
        previous: TapePoint | None = None
        for point in points:
            if previous is not None and point.source_second - previous.source_second > 5:
                _append_polyline(parts, segment, x=x, y=y)
                segment = []
            segment.append(point)
            previous = point
        _append_polyline(parts, segment, x=x, y=y)

        market_rows = sorted(rows_by_condition.get(condition_id, []), key=lambda row: row["source_second"])
        up_inventory = 0.0
        down_inventory = 0.0
        inventory_path: list[tuple[int, float]] = [(spec.window_start, 0.0)]
        grouped_rows: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in market_rows:
            grouped_rows[int(row["source_second"])].append(row)
            radius = min(11.0, 2.6 + math.sqrt(float(row["source_size"])) * 0.38)
            xx = x(int(row["source_second"]))
            yy = y(float(row["q_fill"]))
            tooltip = html.escape(
                f"{row['source_event_time']} {row['outcome']} BUY price={row['source_price']:.4f} "
                f"size={row['source_size']:.4f} opposite={row['opposite_fill']}"
            )
            if row["outcome"] == "Up":
                parts.append(f'<circle cx="{xx:.2f}" cy="{yy:.2f}" r="{radius:.2f}" class="up"><title>{tooltip}</title></circle>')
            else:
                r = radius
                parts.append(
                    f'<path d="M{xx:.2f} {yy-r:.2f} L{xx+r:.2f} {yy+r:.2f} L{xx-r:.2f} {yy+r:.2f} Z" class="down"><title>{tooltip}</title></path>'
                )
        for second in sorted(grouped_rows):
            up_inventory += sum(float(row["source_size"]) for row in grouped_rows[second] if row["outcome"] == "Up")
            down_inventory += sum(float(row["source_size"]) for row in grouped_rows[second] if row["outcome"] == "Down")
            inventory_path.append((second, up_inventory - down_inventory))
        inventory_path.append((spec.window_end, up_inventory - down_inventory))
        max_abs = max((abs(value) for _, value in inventory_path), default=1.0) or 1.0
        inv_mid = y0 + inventory_top + inventory_height / 2
        parts.append(f'<line x1="{left}" y1="{inv_mid:.2f}" x2="{width-right}" y2="{inv_mid:.2f}" class="zero"/>')
        inv_points = " ".join(
            f"{x(second):.2f},{inv_mid - value/max_abs*(inventory_height/2-2):.2f}"
            for second, value in inventory_path
        )
        parts.append(f'<polyline points="{inv_points}" class="inv"/>')
        parts.append(f'<text x="{left-12}" y="{inv_mid+4:.2f}" text-anchor="end" class="small">inv</text>')

    parts.append('<text x="36" y="{}" class="small">Source-time descriptive evidence only · no same-second ordering · no midpoint or inferred order placement.</text>'.format(height - 18))
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def run_study(
    *,
    wallet_activity_path: str | Path,
    output_dir: str | Path,
    expected_wallet_sha256: str | None = None,
    api: PolymarketTradeTapeAPI | None = None,
    page_size: int = 500,
    max_offset: int = 5_000,
) -> dict[str, Any]:
    wallet = load_wallet_evidence(
        wallet_activity_path,
        expected_sha256=expected_wallet_sha256,
    )
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=False)
    api = api or PolymarketTradeTapeAPI()
    collection_started_at = datetime.now(timezone.utc)
    envelopes, requests = collect_market_rows(
        api,
        wallet.specs,
        page_size=page_size,
        max_offset=max_offset,
    )
    raw_path = root / _RAW
    _write_jsonl(raw_path, envelopes)
    trades = normalize_market_rows(envelopes, specs=wallet.specs)
    tape = build_independent_tape(trades)
    rows = analyze_fills(wallet.rows, tape)
    summary = summarize(rows, tape=tape, specs=wallet.specs)
    rows_path = root / _ROWS
    summary_path = root / _SUMMARY
    chart_path = root / _CHART
    _write_jsonl(rows_path, rows)
    _write_json(summary_path, summary)
    chart_path.write_text(
        render_overlay_svg(specs=wallet.specs, tape=tape, analysis_rows=rows),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": _SCHEMA,
        "wallet": _WALLET,
        "wallet_activity": {
            "path": str(Path(wallet_activity_path)),
            "sha256": wallet.sha256,
            "expected_sha256": expected_wallet_sha256.lower() if expected_wallet_sha256 else None,
            "row_count": len(wallet.rows),
        },
        "market_tape_collection": {
            "started_at": _iso_datetime(collection_started_at),
            "completed_at": _iso_datetime(datetime.now(timezone.utc)),
            "base_url": api.base_url,
            "resource": "/trades",
            "page_size": page_size,
            "max_offset": max_offset,
            "requests": requests,
            "raw_response_rows": len(envelopes),
            "normalized_window_rows": len(trades),
            "independent_reference_rows": sum(
                1 for trade in trades if trade.proxy_wallet != _WALLET
            ),
        },
        "implementation": {"github_sha": os.environ.get("GITHUB_SHA")},
        "conditions": {
            condition_id: {
                "slug": spec.slug,
                "window_start": _iso_unix(spec.window_start),
                "window_end": _iso_unix(spec.window_end),
            }
            for condition_id, spec in sorted(wallet.specs.items())
        },
        "artifacts": {
            name: _artifact(root / name)
            for name in (_RAW, _ROWS, _SUMMARY, _CHART)
        },
    }
    _write_json(root / _MANIFEST, manifest)
    return {"manifest": manifest, "summary": summary}


def _append_polyline(parts: list[str], segment: Sequence[TapePoint], *, x: Callable[[int], float], y: Callable[[float], float]) -> None:
    if not segment:
        return
    if len(segment) == 1:
        point = segment[0]
        parts.append(f'<circle cx="{x(point.source_second):.2f}" cy="{y(point.q):.2f}" r="1.8" fill="#b8c0cc"/>')
        return
    coordinates = " ".join(f"{x(point.source_second):.2f},{y(point.q):.2f}" for point in segment)
    parts.append(f'<polyline points="{coordinates}" class="tape"/>')


def _outcome_probability(q: float, outcome: str) -> float:
    return q if outcome == "Up" else 1.0 - q


def _weighted_share(flags: Sequence[bool], weights: Sequence[float]) -> float:
    total = sum(weights)
    if total <= 0:
        raise CorrectionOverlayError("weighted share requires positive total weight")
    return sum(weight for flag, weight in zip(flags, weights, strict=True) if flag) / total


def _weighted_median(values: Sequence[float], weights: Sequence[float]) -> float:
    pairs = sorted(zip(values, weights, strict=True), key=lambda item: item[0])
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        raise CorrectionOverlayError("weighted median requires positive total weight")
    threshold = total / 2
    cumulative = 0.0
    for value, weight in pairs:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return pairs[-1][0]


def _fill_sort_key(fill: WalletFill) -> tuple[Any, ...]:
    return (fill.source_second, fill.condition_id, fill.transaction_hash, fill.asset_id, fill.outcome)


def _trade_sort_key(trade: MarketTrade) -> tuple[Any, ...]:
    return (
        trade.condition_id,
        trade.source_second,
        trade.transaction_hash,
        trade.proxy_wallet,
        trade.asset_id,
        trade.outcome,
        trade.side,
        trade.price,
        trade.size,
    )


def _decode_json(raw: bytes, path: Path, line_number: int) -> dict[str, Any]:
    if not raw.strip():
        raise CorrectionOverlayError(f"{path}: blank JSONL line {line_number}")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CorrectionOverlayError(f"{path}: invalid JSON at line {line_number}") from exc
    if not isinstance(payload, dict):
        raise CorrectionOverlayError(f"{path}: line {line_number} must be an object")
    return payload


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CorrectionOverlayError(f"{label} must be a non-empty string")
    return value.strip()


def _outcome(value: object, label: str) -> str:
    outcome = _string(value, label)
    if outcome not in {"Up", "Down"}:
        raise CorrectionOverlayError(f"{label} must be Up or Down")
    return outcome


def _integer(value: object, label: str) -> int:
    if isinstance(value, bool):
        raise CorrectionOverlayError(f"{label} must be an integer")
    try:
        parsed = int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise CorrectionOverlayError(f"{label} must be an integer") from exc
    if isinstance(value, float) and value != parsed:
        raise CorrectionOverlayError(f"{label} must be an integer")
    return parsed


def _unix_second(value: object, label: str) -> int:
    text = _string(value, f"{label} source_event_time")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CorrectionOverlayError(f"{label}: invalid source_event_time") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CorrectionOverlayError(f"{label}: source_event_time must be timezone-aware")
    utc = parsed.astimezone(timezone.utc)
    timestamp = int(utc.timestamp())
    if utc.microsecond:
        raise CorrectionOverlayError(f"{label}: source_event_time must have second precision")
    return timestamp


def _positive(value: object, label: str) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise CorrectionOverlayError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise CorrectionOverlayError(f"{label} must be finite and positive")
    return parsed


def _price(value: object, label: str) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise CorrectionOverlayError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed) or not 0 <= parsed <= 1:
        raise CorrectionOverlayError(f"{label} must be finite and in [0, 1]")
    return parsed


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    with path.open("xb") as handle:
        for row in rows:
            handle.write(_json_line(row))


def _write_json(path: Path, payload: Any) -> None:
    with path.open("xb") as handle:
        handle.write(_json_line(payload))


def _json_line(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _artifact(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _iso_unix(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _iso_datetime(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _clock(value: int) -> str:
    return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%H:%M:%S")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run frozen Bonereaper correction overlay study")
    parser.add_argument("--wallet-activity", required=True)
    parser.add_argument("--expected-wallet-sha256")
    parser.add_argument("--output", required=True)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--max-offset", type=int, default=5_000)
    args = parser.parse_args()
    result = run_study(
        wallet_activity_path=args.wallet_activity,
        output_dir=args.output,
        expected_wallet_sha256=args.expected_wallet_sha256,
        page_size=args.page_size,
        max_offset=args.max_offset,
    )
    print(json.dumps(result["summary"], sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
