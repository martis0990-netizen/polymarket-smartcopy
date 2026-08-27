"""Prospective Bonereaper external-signal v2 primitives and Chainlink RTDS recorder.

The module records public reference data and evaluates frozen research gates. It does not place,
sign, or simulate orders.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

_SCHEMA = "smartcopy-bonereaper-prospective-signal-v2"
_CONTRACT_COMMIT = "0065f7ca8c38e435e0a859b06724040cfd01a900"
_RTDS_URL = "wss://ws-live-data.polymarket.com"
_RAW = "chainlink_twap_raw.jsonl"
_GAPS = "chainlink_twap_gaps.jsonl"
_MANIFEST = "chainlink_twap_manifest.json"
_SYMBOLS = ("btc/usd", "eth/usd")


class ProspectiveSignalError(RuntimeError):
    """Raised when prospective evidence cannot satisfy the frozen semantics."""


@dataclass(frozen=True, slots=True)
class TwapEvent:
    symbol: str
    source_timestamp_ms: int
    publisher_timestamp_ms: int | None
    receive_timestamp: datetime
    window_seconds: int
    value: Decimal
    full_accuracy_value: str | None
    raw_topic: str

    def record(self) -> dict[str, Any]:
        return {
            "schema_version": _SCHEMA,
            "symbol": self.symbol,
            "source_timestamp_ms": self.source_timestamp_ms,
            "publisher_timestamp_ms": self.publisher_timestamp_ms,
            "receive_timestamp": _iso(self.receive_timestamp),
            "window_seconds": self.window_seconds,
            "value": format(self.value, "f"),
            "full_accuracy_value": self.full_accuracy_value,
            "raw_topic": self.raw_topic,
        }


@dataclass(frozen=True, slots=True)
class CoverageGap:
    symbol: str
    start_source_ms: int
    end_source_ms: int
    reason: str

    def __post_init__(self) -> None:
        if self.symbol not in _SYMBOLS:
            raise ValueError(f"unsupported gap symbol {self.symbol}")
        if self.end_source_ms < self.start_source_ms:
            raise ValueError("coverage gap ends before it starts")


class TwapSeries:
    """Strict-pre Chainlink TWAP lookup with explicit gap exclusion."""

    def __init__(self) -> None:
        self._events: dict[str, list[TwapEvent]] = {symbol: [] for symbol in _SYMBOLS}
        self._gaps: list[CoverageGap] = []

    def add(self, event: TwapEvent) -> None:
        if event.symbol not in self._events:
            raise ProspectiveSignalError(f"unsupported TWAP symbol {event.symbol}")
        values = self._events[event.symbol]
        if values and event.source_timestamp_ms < values[-1].source_timestamp_ms:
            raise ProspectiveSignalError(f"{event.symbol} Chainlink source timestamp regressed")
        if values and event.source_timestamp_ms == values[-1].source_timestamp_ms:
            if event.value != values[-1].value:
                raise ProspectiveSignalError(
                    f"{event.symbol} conflicting TWAP values at {event.source_timestamp_ms}"
                )
            return
        values.append(event)

    def add_gap(self, gap: CoverageGap) -> None:
        self._gaps.append(gap)

    def strict_pre(
        self,
        symbol: str,
        source_timestamp_ms: int,
        *,
        required_from_ms: int | None = None,
    ) -> TwapEvent | None:
        if symbol not in self._events:
            raise ProspectiveSignalError(f"unsupported TWAP symbol {symbol}")
        lower = source_timestamp_ms if required_from_ms is None else required_from_ms
        if lower > source_timestamp_ms:
            raise ValueError("required_from_ms is after lookup time")
        if any(
            gap.symbol == symbol
            and gap.start_source_ms < source_timestamp_ms
            and gap.end_source_ms >= lower
            for gap in self._gaps
        ):
            return None
        for event in reversed(self._events[symbol]):
            if event.source_timestamp_ms < source_timestamp_ms:
                return event
        return None

    @property
    def gaps(self) -> tuple[CoverageGap, ...]:
        return tuple(self._gaps)


def normalize_rtds_twap_message(
    payload: str | bytes | dict[str, Any],
    *,
    receive_timestamp: datetime,
) -> TwapEvent | None:
    """Normalize one direct RTDS message, preserving the exact E18 value when present."""

    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        if payload.strip() in {"", "PING", "PONG"}:
            return None
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise ProspectiveSignalError("RTDS message is not valid JSON") from exc
    else:
        decoded = payload
    if not isinstance(decoded, dict):
        raise ProspectiveSignalError("RTDS message must be an object")
    topic = decoded.get("topic")
    if topic != "crypto_prices_twap_sixty":
        return None
    if decoded.get("type") != "update":
        return None
    body = decoded.get("payload")
    if not isinstance(body, dict):
        raise ProspectiveSignalError("RTDS TWAP payload must be an object")
    symbol = str(body.get("symbol", "")).lower()
    if symbol not in _SYMBOLS:
        return None
    source_timestamp_ms = _integer(body.get("timestamp"), "Chainlink source timestamp")
    publisher_raw = decoded.get("timestamp")
    publisher_timestamp_ms = (
        _integer(publisher_raw, "RTDS publisher timestamp") if publisher_raw is not None else None
    )
    window = _integer(body.get("window_s", body.get("windowSeconds", body.get("window_seconds"))), "TWAP window")
    if window != 60:
        raise ProspectiveSignalError(f"expected 60-second TWAP, received {window}")
    exact = body.get("full_accuracy_value")
    try:
        if exact is not None:
            exact_text = str(exact)
            exact_integer = int(exact_text)
            value = Decimal(exact_integer) / Decimal(10**18)
        else:
            exact_text = None
            value = Decimal(str(body.get("value")))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ProspectiveSignalError("invalid Chainlink TWAP value") from exc
    if not value.is_finite() or value <= 0:
        raise ProspectiveSignalError("Chainlink TWAP value must be positive and finite")
    return TwapEvent(
        symbol=symbol,
        source_timestamp_ms=source_timestamp_ms,
        publisher_timestamp_ms=publisher_timestamp_ms,
        receive_timestamp=_aware(receive_timestamp),
        window_seconds=window,
        value=value,
        full_accuracy_value=exact_text,
        raw_topic=str(topic),
    )


def collapse_primary_taker(episodes: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the frozen first-taker condition label, or None for no/ambiguous evidence."""

    taker = [row for row in episodes if row.get("role") == "TAKER" and row.get("outcome") in {"Up", "Down"}]
    if not taker:
        return None
    first_second = min(_integer(row.get("source_second"), "episode source_second") for row in taker)
    first = [row for row in taker if _integer(row.get("source_second"), "episode source_second") == first_second]
    outcomes = {str(row["outcome"]) for row in first}
    if len(outcomes) != 1:
        return None
    return {
        "source_second": first_second,
        "outcome": next(iter(outcomes)),
        "episode_count": len(first),
        "source_notional": sum(float(row.get("source_notional", 0.0)) for row in first),
    }


def wilson_lower_bound(successes: int, total: int, *, z: float = 1.959963984540054) -> float | None:
    if successes < 0 or total < 0 or successes > total:
        raise ValueError("invalid Wilson count")
    if total == 0:
        return None
    proportion = successes / total
    denominator = 1 + z * z / total
    center = proportion + z * z / (2 * total)
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
    return (center - margin) / denominator


def directional_gate(successes: int, total: int) -> dict[str, Any]:
    share = successes / total if total else None
    lower = wilson_lower_bound(successes, total)
    if share is None:
        verdict = "UNDERPOWERED"
    elif share >= 0.65 and lower is not None and lower > 0.50:
        verdict = "SUPPORTED_DESCRIPTIVELY"
    elif share <= 0.55:
        verdict = "NOT_SUPPORTED"
    else:
        verdict = "INCONCLUSIVE"
    return {
        "successes": successes,
        "total": total,
        "alignment_share": share,
        "wilson_95_lower": lower,
        "verdict": verdict,
    }


def discordant_gate(*, barrier_wins: int, momentum_wins: int) -> dict[str, Any]:
    total = barrier_wins + momentum_wins
    if barrier_wins < 0 or momentum_wins < 0:
        raise ValueError("discordant wins must be non-negative")
    if total < 10:
        verdict = "UNDERPOWERED_COMPARISON"
    else:
        barrier_share = barrier_wins / total
        momentum_share = momentum_wins / total
        if momentum_share >= 0.65 and momentum_share - barrier_share >= 0.20:
            verdict = "MOMENTUM_DOMINATES_BARRIER"
        elif barrier_share >= 0.65 and barrier_share - momentum_share >= 0.20:
            verdict = "BARRIER_DOMINATES_MOMENTUM"
        else:
            verdict = "NO_DOMINANT_CANDIDATE"
    return {
        "barrier_wins": barrier_wins,
        "momentum_wins": momentum_wins,
        "discordant_conditions": total,
        "verdict": verdict,
    }


def classify_visible_level(
    updates: Iterable[dict[str, Any]],
    *,
    fill_price: str | Decimal,
    source_timestamp_ms: int,
) -> str:
    """Classify exact-price public-book continuity under the frozen 1-second rule."""

    price = Decimal(str(fill_price))
    eligible = sorted(
        (
            (_integer(row.get("source_timestamp_ms"), "book source timestamp"), Decimal(str(row.get("size"))))
            for row in updates
            if Decimal(str(row.get("price"))) == price
            and _integer(row.get("source_timestamp_ms"), "book source timestamp") < source_timestamp_ms
        ),
        key=lambda item: item[0],
    )
    if not eligible:
        return "INELIGIBLE"
    final_time, final_size = eligible[-1]
    if final_size <= 0:
        return "LATE_OR_UNSEEN_LEVEL"
    positive_times = [timestamp for timestamp, size in eligible if size > 0]
    if not positive_times:
        return "LATE_OR_UNSEEN_LEVEL"
    last_zero = max((timestamp for timestamp, size in eligible if size <= 0), default=None)
    continuous_start = min(timestamp for timestamp in positive_times if last_zero is None or timestamp > last_zero)
    if final_time >= source_timestamp_ms:
        raise AssertionError("same/future book update passed strict-pre filter")
    return (
        "PRE_POSITIONED_LEVEL"
        if continuous_start <= source_timestamp_ms - 1_000
        else "LATE_OR_UNSEEN_LEVEL"
    )


class ChainlinkTwapRecorder:
    """Bounded direct RTDS recorder with reconnect gaps and immutable finalize."""

    def __init__(self, *, url: str = _RTDS_URL) -> None:
        self.url = url

    async def run(self, *, output_dir: str | Path, duration_seconds: float) -> dict[str, Any]:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        root = Path(output_dir)
        if root.exists():
            raise FileExistsError(f"refusing to overwrite existing output directory: {root}")
        root.mkdir(parents=True)
        raw_path = root / _RAW
        gaps_path = root / _GAPS
        manifest_path = root / _MANIFEST
        started = datetime.now(timezone.utc)
        deadline = asyncio.get_running_loop().time() + duration_seconds
        counts = {symbol: 0 for symbol in _SYMBOLS}
        last_source: dict[str, int] = {}
        reconnects = 0
        pending_gap_symbols: set[str] = set()
        clean = False
        try:
            with raw_path.open("xb") as raw_handle, gaps_path.open("xb") as gap_handle:
                async for raw, received, reconnected in self._messages(deadline):
                    if reconnected:
                        reconnects += 1
                        pending_gap_symbols = set(last_source)
                    event = normalize_rtds_twap_message(raw, receive_timestamp=received)
                    if event is None:
                        continue
                    if event.symbol in pending_gap_symbols:
                        gap = CoverageGap(
                            symbol=event.symbol,
                            start_source_ms=last_source[event.symbol] + 1,
                            end_source_ms=max(last_source[event.symbol] + 1, event.source_timestamp_ms - 1),
                            reason="RTDS_RECONNECT",
                        )
                        gap_handle.write(_json_line(asdict(gap)))
                        pending_gap_symbols.remove(event.symbol)
                    raw_handle.write(_json_line({"normalized": event.record(), "raw": _json_object(raw)}))
                    raw_handle.flush()
                    gap_handle.flush()
                    last_source[event.symbol] = event.source_timestamp_ms
                    counts[event.symbol] += 1
            clean = True
        finally:
            if clean:
                ended = datetime.now(timezone.utc)
                manifest = {
                    "schema_version": _SCHEMA,
                    "contract_commit": _CONTRACT_COMMIT,
                    "url": self.url,
                    "started_at": _iso(started),
                    "ended_at": _iso(ended),
                    "duration_seconds": duration_seconds,
                    "event_counts": counts,
                    "reconnect_count": reconnects,
                    "clean_finalize": True,
                    "artifacts": {
                        raw_path.name: _artifact(raw_path),
                        gaps_path.name: _artifact(gaps_path),
                    },
                }
                manifest_path.write_bytes(_json_line(manifest))
        if not all(counts.values()):
            raise ProspectiveSignalError(f"bounded smoke missed required symbols: {counts}")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    async def _messages(
        self, deadline: float
    ) -> AsyncIterator[tuple[str | bytes, datetime, bool]]:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - packaging boundary
            raise ProspectiveSignalError("install project dependencies before RTDS collection") from exc
        first_connection = True
        while asyncio.get_running_loop().time() < deadline:
            try:
                async with websockets.connect(self.url, ping_interval=None, open_timeout=15) as socket:
                    # Omitting filters is the documented way to receive every symbol. Local
                    # normalization admits only the two frozen BTC/ETH symbols.
                    subscriptions = [
                        {"topic": "crypto_prices_twap_sixty", "type": "update"}
                    ]
                    await socket.send(json.dumps({"action": "subscribe", "subscriptions": subscriptions}))
                    reconnected = not first_connection
                    first_connection = False
                    next_ping = asyncio.get_running_loop().time() + 5
                    while True:
                        now = asyncio.get_running_loop().time()
                        if now >= deadline:
                            return
                        if now >= next_ping:
                            await socket.send("PING")
                            next_ping = now + 5
                        timeout = min(max(0.05, next_ping - now), max(0.05, deadline - now))
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=timeout)
                        except asyncio.TimeoutError:
                            continue
                        yield raw, datetime.now(timezone.utc), reconnected
                        reconnected = False
            except Exception as exc:  # pragma: no cover - live network boundary
                if asyncio.get_running_loop().time() >= deadline:
                    return
                await asyncio.sleep(min(1.0, max(0.0, deadline - asyncio.get_running_loop().time())))


def _json_object(raw: str | bytes) -> Any:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def _artifact(path: Path) -> dict[str, Any]:
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def _json_line(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise ProspectiveSignalError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ProspectiveSignalError(f"{label} must be an integer") from exc
    if str(value).strip() not in {str(parsed), f"{parsed}.0"} and not isinstance(value, int):
        raise ProspectiveSignalError(f"{label} must be an exact integer")
    return parsed


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ProspectiveSignalError("receive timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _aware(value).isoformat().replace("+00:00", "Z")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record prospective Chainlink 60-second TWAP")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = asyncio.run(
        ChainlinkTwapRecorder().run(
            output_dir=args.output_dir,
            duration_seconds=args.duration_seconds,
        )
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
