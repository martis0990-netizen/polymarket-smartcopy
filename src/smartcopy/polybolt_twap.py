"""Prospective authenticated PolyBolt TWAP capture for the frozen v5 cohort."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, AsyncIterator

_URL = "wss://ws-live-v2.polymarket.com/ws"
_CHANNEL = "price.crypto.twap"
_SYMBOLS = ("btc/usd", "eth/usd", "sol/usd", "xrp/usd", "bnb/usd", "doge/usd", "hype/usd")
_RAW = "chainlink_twap_raw.jsonl"
_GAPS = "chainlink_twap_gaps.jsonl"
_MANIFEST = "chainlink_twap_manifest.json"


class PolyBoltCaptureError(RuntimeError):
    """The capture cannot establish complete, causally eligible TWAP coverage."""


@dataclass(frozen=True, repr=False)
class PolyBoltCredentials:
    api_key: str
    secret: str
    passphrase: str

    @classmethod
    def from_env(cls) -> PolyBoltCredentials:
        names = ("POLYMARKET_CLOB_API_KEY", "POLYMARKET_CLOB_API_SECRET", "POLYMARKET_CLOB_API_PASSPHRASE")
        values = tuple(os.environ.get(name, "") for name in names)
        if not all(values):
            raise PolyBoltCaptureError("set POLYMARKET_CLOB_API_KEY, POLYMARKET_CLOB_API_SECRET and POLYMARKET_CLOB_API_PASSPHRASE")
        return cls(*values)


class PolyBoltTwapRecorder:
    def __init__(self, credentials: PolyBoltCredentials, *, url: str = _URL) -> None:
        self._credentials = credentials
        self.url = url

    async def run(self, *, output_dir: str | Path, duration_seconds: float) -> dict[str, Any]:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        root = Path(output_dir)
        if root.exists():
            raise FileExistsError(f"refusing to overwrite existing TWAP directory: {root}")
        root.mkdir(parents=True)
        raw_path, gaps_path, manifest_path = (root / name for name in (_RAW, _GAPS, _MANIFEST))
        started = datetime.now(timezone.utc)
        deadline = asyncio.get_running_loop().time() + duration_seconds
        counts = dict.fromkeys(_SYMBOLS, 0)
        last_source: dict[str, int] = {}
        snapshots: set[str] = set()
        accepted = 0
        last_seq: int | None = None
        with raw_path.open("xb") as raw_file, gaps_path.open("xb"):
            async for frame, received in self._frames(deadline):
                if "op" in frame:
                    if frame["op"] != "subscribed" or frame.get("channel") != _CHANNEL:
                        raise PolyBoltCaptureError("unexpected PolyBolt acknowledgement")
                    accepted += 1
                    continue
                if frame.get("v") != 1 or frame.get("channel") != _CHANNEL:
                    raise PolyBoltCaptureError("unexpected PolyBolt channel or version")
                seq = _integer(frame.get("seq"), "sequence")
                dropped = _integer(frame.get("dropped", 0), "dropped")
                if seq <= 0 or dropped != 0 or (last_seq is not None and seq != last_seq + 1):
                    raise PolyBoltCaptureError("PolyBolt sequence discontinuity or dropped frames")
                last_seq = seq
                payload = frame.get("payload")
                if not isinstance(payload, dict):
                    raise PolyBoltCaptureError("PolyBolt TWAP payload is missing")
                wire_symbol = payload.get("symbol")
                if not isinstance(wire_symbol, str) or not wire_symbol.endswith("usd"):
                    raise PolyBoltCaptureError("unknown PolyBolt symbol")
                symbol = wire_symbol[:-3] + "/usd"
                if symbol not in counts:
                    raise PolyBoltCaptureError("unexpected PolyBolt symbol")
                window = _integer(payload.get("window_seconds"), "window_seconds")
                if window != 60:
                    raise PolyBoltCaptureError("TWAP window is not 60 seconds")
                if frame.get("snapshot") is True:
                    if symbol in snapshots or not isinstance(payload.get("data"), list):
                        raise PolyBoltCaptureError("duplicate or malformed PolyBolt snapshot")
                    snapshots.add(symbol)
                    # These points predate subscription and must never be counted as live.
                    raw_file.write(_line({"kind": "snapshot", "receive_timestamp": _iso(received), "raw": frame}))
                    raw_file.flush()
                    continue
                if symbol not in snapshots:
                    raise PolyBoltCaptureError("TWAP update preceded its initial snapshot")
                source_ms = _integer(payload.get("timestamp"), "source timestamp")
                if source_ms <= last_source.get(symbol, 0):
                    raise PolyBoltCaptureError("TWAP source timestamp repeated or regressed")
                last_source[symbol] = source_ms
                value_text = payload.get("full_accuracy_value", payload.get("value"))
                try:
                    value = Decimal(str(value_text))
                except (ValueError, InvalidOperation) as exc:
                    raise PolyBoltCaptureError("invalid TWAP decimal") from exc
                if not value.is_finite() or value <= 0:
                    raise PolyBoltCaptureError("TWAP value must be positive and finite")
                record = {
                    "symbol": symbol,
                    "source_timestamp_ms": source_ms,
                    "publisher_timestamp_ms": _integer(frame.get("ts"), "publisher timestamp"),
                    "receive_timestamp": _iso(received),
                    "window_seconds": 60,
                    "value": format(value, "f"),
                    "full_accuracy_value": str(value_text),
                    "raw_topic": _CHANNEL,
                    "feed_protocol": "polybolt-v1",
                    "channel_seq": seq,
                }
                raw_file.write(_line({"kind": "live", "normalized": record, "raw": frame}))
                raw_file.flush()
                counts[symbol] += 1
        if accepted != len(_SYMBOLS) or snapshots != set(_SYMBOLS) or not all(counts.values()):
            raise PolyBoltCaptureError("missing subscriptions, snapshots or live symbol updates")
        manifest = {
            "schema_version": "smartcopy-bonereaper-polybolt-twap-v1",
            "feed_protocol": "polybolt-v1",
            "url": self.url,
            "symbols": list(_SYMBOLS),
            "started_at": _iso(started),
            "ended_at": _iso(datetime.now(timezone.utc)),
            "duration_seconds": duration_seconds,
            "event_counts": counts,
            "snapshot_symbols": sorted(snapshots),
            "reconnect_count": 0,
            "clean_finalize": True,
            "artifacts": {_RAW: _artifact(raw_path), _GAPS: _artifact(gaps_path)},
        }
        manifest_path.write_bytes(_line(manifest))
        return manifest

    async def _frames(self, deadline: float) -> AsyncIterator[tuple[dict[str, Any], datetime]]:
        import websockets

        # No reconnect: interruption invalidates the entire bundle, including its warm-up.
        async with websockets.connect(self.url, open_timeout=15) as socket:
            await socket.send(json.dumps({"op": "auth", "rid": "auth-v5", "auth": {
                "apiKey": self._credentials.api_key,
                "secret": self._credentials.secret,
                "passphrase": self._credentials.passphrase,
            }}))
            auth = await _receive(socket, min(deadline, asyncio.get_running_loop().time() + 15))
            if auth.get("op") != "authed" or auth.get("rid") != "auth-v5":
                raise PolyBoltCaptureError("PolyBolt authentication was not accepted")
            await socket.send(json.dumps({"op": "subscribe", "rid": "twap-v5", "subscriptions": [
                {"channel": _CHANNEL, "filter": {"symbol": symbol.replace("/", ""), "window_seconds": 60}}
                for symbol in _SYMBOLS
            ]}))
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    return
                try:
                    raw = await asyncio.wait_for(socket.recv(), timeout=min(remaining, 15))
                except asyncio.TimeoutError:
                    if asyncio.get_running_loop().time() >= deadline:
                        return
                    raise PolyBoltCaptureError("PolyBolt stream stopped producing frames") from None
                received = datetime.now(timezone.utc)
                try:
                    frame = json.loads(raw)
                except (TypeError, ValueError) as exc:
                    raise PolyBoltCaptureError("invalid PolyBolt frame") from exc
                if not isinstance(frame, dict):
                    raise PolyBoltCaptureError("invalid PolyBolt frame")
                if frame.get("op") == "error":
                    raise PolyBoltCaptureError("PolyBolt rejected subscription or connection")
                yield frame, received


async def _receive(socket: Any, deadline: float) -> dict[str, Any]:
    remaining = deadline - asyncio.get_running_loop().time()
    if remaining <= 0:
        raise PolyBoltCaptureError("PolyBolt authentication timed out")
    try:
        frame = json.loads(await asyncio.wait_for(socket.recv(), timeout=remaining))
    except (asyncio.TimeoutError, ValueError, TypeError) as exc:
        raise PolyBoltCaptureError("PolyBolt authentication timed out or was malformed") from exc
    if not isinstance(frame, dict):
        raise PolyBoltCaptureError("PolyBolt authentication was malformed")
    return frame


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PolyBoltCaptureError(f"{label} must be an integer")
    return value


def _artifact(path: Path) -> dict[str, Any]:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return {"bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def _iso(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _line(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
