"""Frozen external-market signal study for Bonereaper."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from smartcopy.correction_overlay import (
    MarketSpec,
    MarketTrade,
    load_wallet_evidence,
    normalize_market_rows,
)

_SCHEMA = "smartcopy-bonereaper-external-signal-v2"
_EVIDENCE_STATUS = "DESCRIPTIVE_PILOT_MISSING_FROZEN_COMMIT"
_CLAIMED_CONTRACT_COMMIT = "7080225c0b0bbeabcac251a5e7c244d83c4e806b"
_CLAIMED_CORRECTION_COMMIT = "af9effce55fe7543749c94585ebbfbfafa000987"
_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_BINANCE_START_1S = 1_787_748_240_000  # 2026-08-26 12:44:00Z
_BINANCE_START_1M = 1_787_738_400_000  # 2026-08-26 10:00:00Z
_BINANCE_END = 1_787_749_200_000  # 2026-08-26 13:00:00Z, exclusive
_RAW_EXTERNAL = "binance_klines_raw.jsonl"
_EPISODES = "external_signal_episodes.jsonl"
_INVENTORY = "historical_inventory_signal_rows.jsonl"
_SUMMARY = "external_signal_summary.json"
_MANIFEST = "collection_manifest.json"
_CANDIDATES = (
    "barrier",
    "momentum_5s",
    "momentum_15s",
    "momentum_30s",
    "momentum_60s",
    "rsi_1s",
    "rsi_1m",
    "ema_1m",
    "flow_15s",
    "btc_lead_15s",
)
_GATED_TECHNICAL = ("momentum_15s", "rsi_1s", "rsi_1m", "ema_1m", "flow_15s")

Transport = Callable[[str, dict[str, str]], Any]


class ExternalSignalError(RuntimeError):
    """Raised when the frozen external-signal contract cannot be satisfied."""


def _default_transport(url: str, headers: dict[str, str]) -> Any:
    request = Request(url, headers=headers, method="GET")
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310 - fixed official HTTPS host
            return json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # pragma: no cover - network boundary
        raise ExternalSignalError(f"GET {url} failed: {exc}") from exc


@dataclass(slots=True)
class BinanceSpotAPI:
    base_url: str = "https://api.binance.com"
    transport: Transport = _default_transport
    user_agent: str = "polymarket-smartcopy/0.1"

    def klines(
        self,
        *,
        symbol: str,
        interval: str,
        start_time_ms: int,
        end_time_ms: int,
        limit: int = 1_000,
    ) -> tuple[str, Any]:
        query = urlencode(
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": start_time_ms,
                "endTime": end_time_ms,
                "limit": limit,
            }
        )
        url = f"{self.base_url.rstrip('/')}/api/v3/klines?{query}"
        payload = self.transport(
            url,
            {"Accept": "application/json", "User-Agent": self.user_agent},
        )
        return url, payload


@dataclass(frozen=True, slots=True)
class BinanceKline:
    symbol: str
    interval: str
    open_time_ms: int
    close_time_ms: int
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float
    trade_count: int
    taker_buy_base: float
    taker_buy_quote: float

    @property
    def source_second(self) -> int:
        return self.open_time_ms // 1_000


def collect_binance_klines(
    api: BinanceSpotAPI,
) -> tuple[tuple[dict[str, Any], ...], dict[tuple[str, str], tuple[BinanceKline, ...]]]:
    envelopes: list[dict[str, Any]] = []
    normalized: dict[tuple[str, str], tuple[BinanceKline, ...]] = {}
    for symbol in ("BTCUSDT", "ETHUSDT"):
        for interval, start_time in (("1s", _BINANCE_START_1S), ("1m", _BINANCE_START_1M)):
            request = {
                "symbol": symbol,
                "interval": interval,
                "start_time_ms": start_time,
                "end_time_ms": _BINANCE_END - 1,
                "limit": 1_000,
            }
            url, payload = api.klines(**request)
            envelope = {
                "collection_time_utc": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
                "request": {**request, "url": url},
                "response_row_count": len(payload) if isinstance(payload, list) else None,
                "response": payload,
            }
            envelopes.append(envelope)
            bars = normalize_binance_response(envelope)
            normalized[(symbol, interval)] = bars
    _require_expected_external_coverage(normalized)
    return tuple(envelopes), normalized


def load_collected_binance_klines(
    path: str | Path,
    *,
    expected_sha256: str,
) -> tuple[str, tuple[dict[str, Any], ...], dict[tuple[str, str], tuple[BinanceKline, ...]]]:
    source = Path(path)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256.lower():
        raise ExternalSignalError(
            f"external tape SHA256 mismatch: expected {expected_sha256.lower()}, got {digest}"
        )
    envelopes: list[dict[str, Any]] = []
    normalized: dict[tuple[str, str], tuple[BinanceKline, ...]] = {}
    for line_number, line in enumerate(raw.splitlines(), start=1):
        try:
            envelope = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExternalSignalError(f"external tape line {line_number}: invalid JSON") from exc
        if not isinstance(envelope, dict):
            raise ExternalSignalError(f"external tape line {line_number}: expected object")
        bars = normalize_binance_response(envelope)
        key = (bars[0].symbol, bars[0].interval) if bars else ("", "")
        if key in normalized:
            raise ExternalSignalError(f"external tape line {line_number}: duplicate request {key}")
        envelopes.append(envelope)
        normalized[key] = bars
    _require_expected_external_coverage(normalized)
    return digest, tuple(envelopes), normalized


def normalize_binance_response(envelope: dict[str, Any]) -> tuple[BinanceKline, ...]:
    request = envelope.get("request")
    payload = envelope.get("response")
    if not isinstance(request, dict) or not isinstance(payload, list):
        raise ExternalSignalError("malformed Binance response envelope")
    symbol = _string(request.get("symbol"), "Binance request symbol")
    interval = _string(request.get("interval"), "Binance request interval")
    if interval not in {"1s", "1m"}:
        raise ExternalSignalError(f"unsupported Binance interval {interval}")
    bars: list[BinanceKline] = []
    for index, row in enumerate(payload):
        context = f"{symbol} {interval} row {index}"
        if not isinstance(row, list) or len(row) != 12:
            raise ExternalSignalError(f"{context}: expected canonical 12-field kline")
        bar = BinanceKline(
            symbol=symbol,
            interval=interval,
            open_time_ms=_integer(row[0], f"{context} open time"),
            close_time_ms=_integer(row[6], f"{context} close time"),
            open=_positive(row[1], f"{context} open"),
            high=_positive(row[2], f"{context} high"),
            low=_positive(row[3], f"{context} low"),
            close=_positive(row[4], f"{context} close"),
            volume=_non_negative(row[5], f"{context} volume"),
            quote_volume=_non_negative(row[7], f"{context} quote volume"),
            trade_count=_integer(row[8], f"{context} trade count"),
            taker_buy_base=_non_negative(row[9], f"{context} taker buy base"),
            taker_buy_quote=_non_negative(row[10], f"{context} taker buy quote"),
        )
        if not bar.low <= min(bar.open, bar.close) <= max(bar.open, bar.close) <= bar.high:
            raise ExternalSignalError(f"{context}: inconsistent OHLC values")
        if bar.taker_buy_base > bar.volume + 1e-12:
            raise ExternalSignalError(f"{context}: taker-buy volume exceeds total volume")
        bars.append(bar)
    bars.sort(key=lambda item: item.open_time_ms)
    if len({item.open_time_ms for item in bars}) != len(bars):
        raise ExternalSignalError(f"{symbol} {interval}: duplicate open times")
    step = 1_000 if interval == "1s" else 60_000
    if any(b.open_time_ms - a.open_time_ms != step for a, b in zip(bars, bars[1:])):
        raise ExternalSignalError(f"{symbol} {interval}: non-contiguous bars")
    return tuple(bars)


def load_maker_taker_rows(
    path: str | Path,
    *,
    expected_sha256: str,
    expected_transaction_hashes: set[str],
) -> tuple[str, tuple[dict[str, Any], ...]]:
    source = Path(path)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256.lower():
        raise ExternalSignalError(
            f"maker/taker SHA256 mismatch: expected {expected_sha256.lower()}, got {digest}"
        )
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExternalSignalError(f"maker/taker line {line_number}: invalid JSON") from exc
        if not isinstance(row, dict):
            raise ExternalSignalError(f"maker/taker line {line_number}: expected object")
        role = row.get("schema_corrected_role")
        if role not in {"MAKER", "TAKER"}:
            raise ExternalSignalError(f"maker/taker line {line_number}: unresolved role")
        rows.append(dict(row))
    transaction_hashes = {str(row.get("transaction_hash")) for row in rows}
    if transaction_hashes != expected_transaction_hashes:
        raise ExternalSignalError("maker/taker transactions do not match frozen wallet evidence")
    return digest, tuple(rows)


def load_historical_wallet_trades(
    path: str | Path,
    *,
    expected_sha256: str,
    specs: dict[str, MarketSpec],
) -> tuple[str, tuple[MarketTrade, ...], int]:
    source = Path(path)
    raw = source.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != expected_sha256.lower():
        raise ExternalSignalError(
            f"market tape SHA256 mismatch: expected {expected_sha256.lower()}, got {digest}"
        )
    envelopes: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ExternalSignalError(f"market tape line {line_number}: invalid JSON") from exc
        if not isinstance(row, dict):
            raise ExternalSignalError(f"market tape line {line_number}: expected object")
        envelopes.append(row)
    normalized = normalize_market_rows(envelopes, specs=specs)
    wallet_rows = tuple(
        row for row in normalized if row.proxy_wallet == _WALLET and row.side == "BUY"
    )
    if len(wallet_rows) != 107:
        raise ExternalSignalError(f"frozen market tape requires 107 wallet rows, got {len(wallet_rows)}")
    return digest, wallet_rows, len(envelopes)


def group_live_episodes(
    rows: Sequence[dict[str, Any]],
    *,
    specs: dict[str, MarketSpec],
) -> tuple[dict[str, Any], ...]:
    grouped: dict[tuple[str, int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        condition_id = _string(row.get("condition_id"), "episode condition_id")
        if condition_id not in specs:
            raise ExternalSignalError(f"unexpected maker/taker condition {condition_id}")
        second = _integer(row.get("source_second"), "episode source_second")
        outcome = _outcome(row.get("outcome"), "episode outcome")
        grouped[(condition_id, second, outcome)].append(row)

    episodes: list[dict[str, Any]] = []
    for (condition_id, second, outcome), group in sorted(grouped.items()):
        roles = {str(row["schema_corrected_role"]) for row in group}
        opposite = {bool(row["opposite_fill"]) for row in group}
        if len(opposite) != 1:
            raise ExternalSignalError("same episode has inconsistent opposite-fill state")
        role = next(iter(roles)) if len(roles) == 1 else "MIXED_ROLE"
        episodes.append(
            {
                "condition_id": condition_id,
                "slug": specs[condition_id].slug,
                "asset": specs[condition_id].asset,
                "horizon": specs[condition_id].horizon,
                "source_second": second,
                "source_event_time": _iso_unix(second),
                "outcome": outcome,
                "role": role,
                "opposite_fill": next(iter(opposite)),
                "fill_rows": len(group),
                "source_size": sum(float(row["source_size"]) for row in group),
                "source_notional": sum(float(row["source_notional"]) for row in group),
                "transaction_hashes": sorted(str(row["transaction_hash"]) for row in group),
            }
        )
    return tuple(episodes)


def attach_external_features(
    episodes: Sequence[dict[str, Any]],
    *,
    bars: dict[tuple[str, str], tuple[BinanceKline, ...]],
    specs: dict[str, MarketSpec],
) -> tuple[dict[str, Any], ...]:
    output: list[dict[str, Any]] = []
    for episode in episodes:
        spec = specs[str(episode["condition_id"])]
        features = external_features(
            asset=spec.asset,
            horizon=spec.horizon,
            market_start=spec.window_start,
            market_end=spec.window_end,
            source_second=int(episode["source_second"]),
            bars=bars,
        )
        output.append({**episode, **features})
    return tuple(output)


def external_features(
    *,
    asset: str,
    horizon: str,
    market_start: int,
    market_end: int,
    source_second: int,
    bars: dict[tuple[str, str], tuple[BinanceKline, ...]],
) -> dict[str, Any]:
    symbol = f"{asset}USDT"
    seconds = {bar.source_second: bar for bar in bars[(symbol, "1s")]}
    pre_second = source_second - 1
    pre = seconds.get(pre_second)
    if pre is None:
        raise ExternalSignalError(f"{symbol}: missing strict-pre second {pre_second}")
    if horizon not in {"5m", "15m"}:
        raise ExternalSignalError(f"unsupported market horizon {horizon}")
    # Effective 2026-08-14, both 5m and 15m crypto contracts use a 60s TWAP.
    twap_window = 60
    barrier_bars = [seconds.get(second) for second in range(market_start - twap_window, market_start)]
    if any(bar is None for bar in barrier_bars):
        raise ExternalSignalError(f"{symbol}: incomplete proxy opening TWAP window")
    barrier = sum(bar.close for bar in barrier_bars if bar is not None) / twap_window
    distance = math.log(pre.close / barrier)

    result: dict[str, Any] = {
        "proxy_symbol": symbol,
        "strict_pre_second": pre_second,
        "strict_pre_spot": pre.close,
        "proxy_opening_twap": barrier,
        "barrier_distance_bps": 10_000 * distance,
        "barrier_direction": _direction(distance),
        "seconds_remaining": max(0, market_end - source_second),
    }
    for lookback in (5, 15, 30, 60):
        earlier = seconds.get(pre_second - lookback)
        if earlier is None:
            result[f"momentum_{lookback}s_log_return"] = None
            result[f"momentum_{lookback}s_direction"] = None
        else:
            value = math.log(pre.close / earlier.close)
            result[f"momentum_{lookback}s_log_return"] = value
            result[f"momentum_{lookback}s_direction"] = _direction(value)

    one_second_closes = _strict_second_closes(seconds, end_second=pre_second, changes=14)
    rsi_1s = _rsi(one_second_closes, period=14)
    result["rsi_1s_value"] = rsi_1s
    result["rsi_1s_direction"] = _rsi_direction(rsi_1s)
    result["rsi_1s_zone"] = _rsi_zone(rsi_1s)

    completed_minutes = [
        bar for bar in bars[(symbol, "1m")] if bar.close_time_ms < source_second * 1_000
    ]
    minute_closes = [bar.close for bar in completed_minutes]
    rsi_1m = _rsi(minute_closes, period=14)
    ema_5 = _ema(minute_closes, period=5)
    ema_20 = _ema(minute_closes, period=20)
    result["rsi_1m_value"] = rsi_1m
    result["rsi_1m_direction"] = _rsi_direction(rsi_1m)
    result["rsi_1m_zone"] = _rsi_zone(rsi_1m)
    result["ema_5_1m"] = ema_5
    result["ema_20_1m"] = ema_20
    result["ema_1m_direction"] = (
        _direction(ema_5 - ema_20) if ema_5 is not None and ema_20 is not None else None
    )

    flow_bars = [seconds.get(second) for second in range(source_second - 15, source_second)]
    if any(bar is None for bar in flow_bars):
        flow = None
    else:
        total = sum(bar.volume for bar in flow_bars if bar is not None)
        taker_buy = sum(bar.taker_buy_base for bar in flow_bars if bar is not None)
        flow = (2 * taker_buy / total) - 1 if total > 0 else 0.0
    result["flow_15s_imbalance"] = flow
    result["flow_15s_direction"] = _direction(flow) if flow is not None else None

    volatility_closes = _strict_second_closes(seconds, end_second=pre_second, changes=60)
    sigma = _return_volatility(volatility_closes)
    tau = max(market_end - source_second, 1)
    z_score = distance / (sigma * math.sqrt(tau)) if sigma and sigma > 0 else None
    result["volatility_60s_per_second"] = sigma
    result["barrier_z_score"] = z_score
    result["barrier_normal_cdf"] = (
        0.5 * (1.0 + math.erf(z_score / math.sqrt(2))) if z_score is not None else None
    )

    if asset == "ETH":
        btc_seconds = {bar.source_second: bar for bar in bars[("BTCUSDT", "1s")]}
        btc_pre = btc_seconds.get(pre_second)
        btc_earlier = btc_seconds.get(pre_second - 15)
        if btc_pre is not None and btc_earlier is not None:
            btc_momentum = math.log(btc_pre.close / btc_earlier.close)
            result["btc_lead_15s_log_return"] = btc_momentum
            result["btc_lead_15s_direction"] = _direction(btc_momentum)
        else:
            result["btc_lead_15s_log_return"] = None
            result["btc_lead_15s_direction"] = None
    else:
        result["btc_lead_15s_log_return"] = None
        result["btc_lead_15s_direction"] = None
    return result


def build_historical_inventory_rows(
    trades: Sequence[MarketTrade],
    *,
    bars: dict[tuple[str, str], tuple[BinanceKline, ...]],
    specs: dict[str, MarketSpec],
) -> tuple[dict[str, Any], ...]:
    by_condition: dict[str, list[MarketTrade]] = defaultdict(list)
    for trade in trades:
        by_condition[trade.condition_id].append(trade)
    output: list[dict[str, Any]] = []
    for condition_id, condition_trades in sorted(by_condition.items()):
        up_notional = 0.0
        down_notional = 0.0
        by_second: dict[int, list[MarketTrade]] = defaultdict(list)
        for trade in condition_trades:
            by_second[trade.source_second].append(trade)
        spec = specs[condition_id]
        for second in sorted(by_second):
            rows = by_second[second]
            up_notional += sum(row.price * row.size for row in rows if row.outcome == "Up")
            down_notional += sum(row.price * row.size for row in rows if row.outcome == "Down")
            inventory_direction = _direction(up_notional - down_notional)
            features = external_features(
                asset=spec.asset,
                horizon=spec.horizon,
                market_start=spec.window_start,
                market_end=spec.window_end,
                source_second=second,
                bars=bars,
            )
            output.append(
                {
                    "condition_id": condition_id,
                    "slug": spec.slug,
                    "asset": spec.asset,
                    "horizon": spec.horizon,
                    "source_second": second,
                    "source_event_time": _iso_unix(second),
                    "fill_rows": len(rows),
                    "cumulative_up_notional": up_notional,
                    "cumulative_down_notional": down_notional,
                    "inventory_imbalance_notional": up_notional - down_notional,
                    "inventory_direction": inventory_direction,
                    "barrier_direction": features["barrier_direction"],
                    "barrier_distance_bps": features["barrier_distance_bps"],
                    "aligned": (
                        inventory_direction == features["barrier_direction"]
                        if inventory_direction and features["barrier_direction"]
                        else None
                    ),
                }
            )
    return tuple(output)


def summarize(
    episodes: Sequence[dict[str, Any]],
    *,
    inventory_rows: Sequence[dict[str, Any]],
    gross_taker_fee: float,
) -> dict[str, Any]:
    taker = [row for row in episodes if row["role"] == "TAKER"]
    maker = [row for row in episodes if row["role"] == "MAKER"]
    populations = {
        "taker": _population_candidates(taker),
        "maker": _population_candidates(maker),
        "all": _population_candidates(episodes),
        "taker_opposite": _population_candidates(
            [row for row in taker if row["opposite_fill"]]
        ),
        "taker_non_opposite": _population_candidates(
            [row for row in taker if not row["opposite_fill"]]
        ),
    }
    primary = populations["taker"]["barrier"]
    primary_verdict = _primary_verdict(primary)
    technical_verdicts: dict[str, str] = {}
    for candidate in _GATED_TECHNICAL:
        technical_verdicts[candidate] = _technical_verdict(
            populations["taker"][candidate]
        )

    discordant: dict[str, Any] = {}
    for candidate in _GATED_TECHNICAL:
        rows = [
            row
            for row in taker
            if row.get("barrier_direction") is not None
            and row.get(f"{candidate}_direction") is not None
            and row["barrier_direction"] != row[f"{candidate}_direction"]
        ]
        discordant[candidate] = {
            "episode_count": len(rows),
            "source_notional": sum(float(row["source_notional"]) for row in rows),
            "barrier": _alignment(rows, "barrier_direction"),
            "candidate": _alignment(rows, f"{candidate}_direction"),
        }

    eligible_inventory = [row for row in inventory_rows if row["aligned"] is not None]
    inventory_total_weight = sum(
        abs(float(row["inventory_imbalance_notional"])) for row in eligible_inventory
    )
    inventory_aligned_weight = sum(
        abs(float(row["inventory_imbalance_notional"]))
        for row in eligible_inventory
        if row["aligned"]
    )
    inventory_diagnostic = {
        "source_seconds": len(inventory_rows),
        "eligible_source_seconds": len(eligible_inventory),
        "aligned_source_second_share": (
            sum(bool(row["aligned"]) for row in eligible_inventory) / len(eligible_inventory)
            if eligible_inventory
            else None
        ),
        "absolute_imbalance_weighted_alignment_share": (
            inventory_aligned_weight / inventory_total_weight if inventory_total_weight else None
        ),
        "per_market": {},
    }
    for slug in sorted({str(row["slug"]) for row in inventory_rows}):
        market_rows = [row for row in inventory_rows if row["slug"] == slug and row["aligned"] is not None]
        inventory_diagnostic["per_market"][slug] = {
            "eligible_source_seconds": len(market_rows),
            "aligned_share": (
                sum(bool(row["aligned"]) for row in market_rows) / len(market_rows)
                if market_rows
                else None
            ),
        }

    return {
        "schema_version": _SCHEMA,
        "evidence_status": _EVIDENCE_STATUS,
        "contract_frozen_commit": None,
        "specification_correction_commit": None,
        "unverified_claimed_commits": {
            "contract": _CLAIMED_CONTRACT_COMMIT,
            "correction": _CLAIMED_CORRECTION_COMMIT,
        },
        "primary_external_fair_value": {
            "candidate": "Binance-proxy opening TWAP barrier direction",
            "population": "schema-corrected TAKER episodes",
            "verdict": primary_verdict,
            **primary,
        },
        "technical_indicator_verdicts": technical_verdicts,
        "episode_counts": {
            "all": len(episodes),
            "taker": len(taker),
            "maker": len(maker),
            "mixed_role": sum(row["role"] == "MIXED_ROLE" for row in episodes),
        },
        "populations": populations,
        "discordant_taker_episodes": discordant,
        "historical_inventory_diagnostic": inventory_diagnostic,
        "taker_fee_sensitivity": {
            "gross_fee_usdc": gross_taker_fee,
            "net_fee_at_public_50pct_rebate": gross_taker_fee * 0.50,
            "net_fee_at_alleged_80pct_rebate": gross_taker_fee * 0.20,
            "alleged_80pct_is_verified_for_sample": False,
        },
        "interpretation_limit": (
            "Four overlapping contracts and one 99-second live interval; Binance is a declared "
            "proxy for unavailable historical Chainlink TWAP, and repeated episodes are not "
            "independent markets."
        ),
    }


def run_study(
    *,
    wallet_activity_path: str | Path,
    expected_wallet_sha256: str,
    market_tape_path: str | Path,
    expected_market_tape_sha256: str,
    maker_taker_path: str | Path,
    expected_maker_taker_sha256: str,
    output_dir: str | Path,
    api: BinanceSpotAPI | None = None,
    external_tape_path: str | Path | None = None,
    expected_external_tape_sha256: str | None = None,
) -> dict[str, Any]:
    output = Path(output_dir)
    if output.exists():
        raise FileExistsError(f"refusing to overwrite existing output directory: {output}")
    wallet = load_wallet_evidence(
        wallet_activity_path,
        expected_sha256=expected_wallet_sha256,
    )
    maker_digest, maker_rows = load_maker_taker_rows(
        maker_taker_path,
        expected_sha256=expected_maker_taker_sha256,
        expected_transaction_hashes={row.transaction_hash for row in wallet.rows},
    )
    market_digest, historical_wallet_rows, raw_market_rows = load_historical_wallet_trades(
        market_tape_path,
        expected_sha256=expected_market_tape_sha256,
        specs=wallet.specs,
    )
    if external_tape_path is not None:
        if api is not None:
            raise ExternalSignalError("external tape reuse and live API collection are mutually exclusive")
        if expected_external_tape_sha256 is None:
            raise ExternalSignalError("external tape reuse requires an expected SHA256")
        external_digest, envelopes, bars = load_collected_binance_klines(
            external_tape_path,
            expected_sha256=expected_external_tape_sha256,
        )
        external_source = "https://api.binance.com"
    else:
        if expected_external_tape_sha256 is not None:
            raise ExternalSignalError("expected external SHA256 requires an external tape path")
        collector = api or BinanceSpotAPI()
        envelopes, bars = collect_binance_klines(collector)
        external_digest = None
        external_source = collector.base_url
    episodes = group_live_episodes(maker_rows, specs=wallet.specs)
    episode_rows = attach_external_features(episodes, bars=bars, specs=wallet.specs)
    inventory_rows = build_historical_inventory_rows(
        historical_wallet_rows,
        bars=bars,
        specs=wallet.specs,
    )
    gross_taker_fee = sum(
        float(row["fee"]) / 1_000_000
        for row in maker_rows
        if row["schema_corrected_role"] == "TAKER"
    )
    summary = summarize(
        episode_rows,
        inventory_rows=inventory_rows,
        gross_taker_fee=gross_taker_fee,
    )

    output.mkdir(parents=True)
    raw_path = output / _RAW_EXTERNAL
    episodes_path = output / _EPISODES
    inventory_path = output / _INVENTORY
    summary_path = output / _SUMMARY
    manifest_path = output / _MANIFEST
    _write_jsonl(raw_path, envelopes)
    _write_jsonl(episodes_path, episode_rows)
    _write_jsonl(inventory_path, inventory_rows)
    _write_json(summary_path, summary)
    artifacts = {
        path.name: {"bytes": path.stat().st_size, "sha256": _sha256(path)}
        for path in (raw_path, episodes_path, inventory_path, summary_path)
    }
    manifest = {
        "schema_version": _SCHEMA,
        "evidence_status": _EVIDENCE_STATUS,
        "contract_frozen_commit": None,
        "specification_correction_commit": None,
        "unverified_claimed_commits": {
            "contract": _CLAIMED_CONTRACT_COMMIT,
            "correction": _CLAIMED_CORRECTION_COMMIT,
        },
        "collection_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "github_sha": os.environ.get("GITHUB_SHA"),
        "external_source": external_source,
        "reused_external_tape": (
            {
                "path": str(external_tape_path),
                "sha256": external_digest,
            }
            if external_tape_path is not None
            else None
        ),
        "external_requests": len(envelopes),
        "external_rows": {
            f"{symbol}_{interval}": len(values)
            for (symbol, interval), values in sorted(bars.items())
        },
        "wallet_activity": {
            "path": str(wallet_activity_path),
            "rows": len(wallet.rows),
            "sha256": wallet.sha256,
        },
        "market_tape": {
            "path": str(market_tape_path),
            "raw_rows": raw_market_rows,
            "wallet_rows": len(historical_wallet_rows),
            "sha256": market_digest,
        },
        "maker_taker_rows": {
            "path": str(maker_taker_path),
            "rows": len(maker_rows),
            "sha256": maker_digest,
        },
        "artifacts": artifacts,
    }
    _write_json(manifest_path, manifest)
    return {"summary": summary, "manifest": manifest, "output_dir": str(output)}


def _population_candidates(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for candidate in _CANDIDATES:
        metrics = _alignment(rows, f"{candidate}_direction")
        metrics["by_asset"] = {
            asset: _alignment(
                [row for row in rows if row["asset"] == asset],
                f"{candidate}_direction",
            )
            for asset in ("BTC", "ETH")
        }
        output[candidate] = metrics
    return output


def _alignment(rows: Sequence[dict[str, Any]], direction_field: str) -> dict[str, Any]:
    eligible = [row for row in rows if row.get(direction_field) in {"Up", "Down"}]
    total_notional = sum(float(row["source_notional"]) for row in eligible)
    aligned = [row for row in eligible if row["outcome"] == row[direction_field]]
    aligned_notional = sum(float(row["source_notional"]) for row in aligned)
    return {
        "eligible_episodes": len(eligible),
        "eligible_notional": total_notional,
        "aligned_episodes": len(aligned),
        "aligned_notional": aligned_notional,
        "episode_alignment_share": len(aligned) / len(eligible) if eligible else None,
        "notional_alignment_share": aligned_notional / total_notional if total_notional else None,
    }


def _primary_verdict(metrics: dict[str, Any]) -> str:
    notional = metrics["notional_alignment_share"]
    episodes = metrics["episode_alignment_share"]
    if notional is None or episodes is None:
        return "INCONCLUSIVE"
    if notional >= 0.70 and episodes >= 0.60:
        return "SUPPORTED_DESCRIPTIVELY"
    if notional <= 0.55 or episodes <= 0.50:
        return "NOT_SUPPORTED"
    return "INCONCLUSIVE"


def _technical_verdict(metrics: dict[str, Any]) -> str:
    notional = metrics["notional_alignment_share"]
    episodes = metrics["episode_alignment_share"]
    if notional is None or episodes is None:
        return "INCONCLUSIVE"
    if notional <= 0.55 or episodes <= 0.50:
        return "NOT_SUPPORTED"
    asset_shares = [
        metrics["by_asset"][asset]["notional_alignment_share"]
        for asset in ("BTC", "ETH")
    ]
    if (
        notional >= 0.70
        and episodes >= 0.60
        and all(share is not None and share >= 0.60 for share in asset_shares)
    ):
        return "SUPPORTED_DESCRIPTIVELY"
    return "INCONCLUSIVE"


def _require_expected_external_coverage(
    bars: dict[tuple[str, str], tuple[BinanceKline, ...]],
) -> None:
    for symbol in ("BTCUSDT", "ETHUSDT"):
        seconds = bars.get((symbol, "1s"), ())
        minutes = bars.get((symbol, "1m"), ())
        if len(seconds) != 960:
            raise ExternalSignalError(f"{symbol} 1s: expected 960 rows, got {len(seconds)}")
        if len(minutes) != 180:
            raise ExternalSignalError(f"{symbol} 1m: expected 180 rows, got {len(minutes)}")
        if seconds[0].open_time_ms != _BINANCE_START_1S or seconds[-1].open_time_ms != _BINANCE_END - 1_000:
            raise ExternalSignalError(f"{symbol} 1s: unexpected time coverage")
        if minutes[0].open_time_ms != _BINANCE_START_1M or minutes[-1].open_time_ms != _BINANCE_END - 60_000:
            raise ExternalSignalError(f"{symbol} 1m: unexpected time coverage")


def _strict_second_closes(
    seconds: dict[int, BinanceKline],
    *,
    end_second: int,
    changes: int,
) -> list[float]:
    values = [seconds.get(second) for second in range(end_second - changes, end_second + 1)]
    if any(bar is None for bar in values):
        return []
    return [bar.close for bar in values if bar is not None]


def _rsi(closes: Sequence[float], *, period: int) -> float | None:
    if len(closes) < period + 1:
        return None
    changes = [right - left for left, right in zip(closes, closes[1:])]
    seed = changes[:period]
    average_gain = sum(max(change, 0.0) for change in seed) / period
    average_loss = sum(max(-change, 0.0) for change in seed) / period
    for change in changes[period:]:
        average_gain = (average_gain * (period - 1) + max(change, 0.0)) / period
        average_loss = (average_loss * (period - 1) + max(-change, 0.0)) / period
    if average_gain == 0 and average_loss == 0:
        return 50.0
    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def _ema(closes: Sequence[float], *, period: int) -> float | None:
    if not closes:
        return None
    alpha = 2.0 / (period + 1.0)
    value = float(closes[0])
    for close in closes[1:]:
        value = alpha * float(close) + (1.0 - alpha) * value
    return value


def _return_volatility(closes: Sequence[float]) -> float | None:
    if len(closes) < 2:
        return None
    returns = [math.log(right / left) for left, right in zip(closes, closes[1:])]
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / len(returns)
    return math.sqrt(variance)


def _rsi_direction(value: float | None) -> str | None:
    return _direction(value - 50.0) if value is not None else None


def _rsi_zone(value: float | None) -> str | None:
    if value is None:
        return None
    if value < 30:
        return "OVERSOLD"
    if value > 70:
        return "OVERBOUGHT"
    return "NEUTRAL"


def _direction(value: float) -> str | None:
    if value > 0:
        return "Up"
    if value < 0:
        return "Down"
    return None


def _string(value: Any, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ExternalSignalError(f"{context}: expected non-empty string")
    return value


def _outcome(value: Any, context: str) -> str:
    text = _string(value, context)
    if text not in {"Up", "Down"}:
        raise ExternalSignalError(f"{context}: expected Up or Down")
    return text


def _integer(value: Any, context: str) -> int:
    if isinstance(value, bool):
        raise ExternalSignalError(f"{context}: expected integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ExternalSignalError(f"{context}: expected integer") from exc
    if isinstance(value, float) and value != parsed:
        raise ExternalSignalError(f"{context}: expected integer")
    return parsed


def _positive(value: Any, context: str) -> float:
    parsed = _number(value, context)
    if parsed <= 0:
        raise ExternalSignalError(f"{context}: expected positive number")
    return parsed


def _non_negative(value: Any, context: str) -> float:
    parsed = _number(value, context)
    if parsed < 0:
        raise ExternalSignalError(f"{context}: expected non-negative number")
    return parsed


def _number(value: Any, context: str) -> float:
    if isinstance(value, bool):
        raise ExternalSignalError(f"{context}: expected finite number")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ExternalSignalError(f"{context}: expected finite number") from exc
    if not math.isfinite(parsed):
        raise ExternalSignalError(f"{context}: expected finite number")
    return parsed


def _iso_unix(second: int) -> str:
    return datetime.fromtimestamp(second, tz=timezone.utc).isoformat().replace("+00:00", "Z")


def _write_jsonl(path: Path, rows: Iterable[Any]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wallet-activity", required=True)
    parser.add_argument("--expected-wallet-sha256", required=True)
    parser.add_argument("--market-tape", required=True)
    parser.add_argument("--expected-market-tape-sha256", required=True)
    parser.add_argument("--maker-taker-rows", required=True)
    parser.add_argument("--expected-maker-taker-sha256", required=True)
    parser.add_argument("--external-tape")
    parser.add_argument("--expected-external-tape-sha256")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    result = run_study(
        wallet_activity_path=args.wallet_activity,
        expected_wallet_sha256=args.expected_wallet_sha256,
        market_tape_path=args.market_tape,
        expected_market_tape_sha256=args.expected_market_tape_sha256,
        maker_taker_path=args.maker_taker_rows,
        expected_maker_taker_sha256=args.expected_maker_taker_sha256,
        external_tape_path=args.external_tape,
        expected_external_tape_sha256=args.expected_external_tape_sha256,
        output_dir=args.output,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":  # pragma: no cover
    main()
