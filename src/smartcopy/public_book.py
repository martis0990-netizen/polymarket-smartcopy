"""Bounded public Polymarket CLOB recorder for the frozen Bonereaper ladder study.

The module records public market data only. It cannot construct, sign, or submit orders.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, AsyncIterator, Iterable, Sequence

_SCHEMA = "smartcopy-bonereaper-public-book-v1"
_CONTRACT_COMMIT = "c16c4e6454c41296662e23d156bcc4b0b2e7b3c2"
_WS_URL = "wss://ws-subscriptions-clob.polymarket.com/ws/market"
_RAW = "book_frames_raw.jsonl"
_LEVELS = "book_levels.jsonl"
_GAPS = "book_gaps.jsonl"
_TOKENS = "token_metadata.json"
_MANIFEST = "public_book_manifest.json"
_SHA = re.compile(r"[0-9a-f]{40}")


class PublicBookError(RuntimeError):
    """Raised when public-book evidence violates the frozen capture semantics."""


@dataclass(frozen=True, slots=True)
class BookRecord:
    record_type: str
    event_type: str
    token_id: str
    market: str | None
    source_timestamp_ms: int
    receive_timestamp: datetime
    side: str | None
    price: Decimal | None
    size: Decimal | None
    book_hash: str | None

    def record(self, *, line_number: int, coverage_valid: bool) -> dict[str, Any]:
        return {
            "schema_version": _SCHEMA,
            "line_number": line_number,
            "record_type": self.record_type,
            "event_type": self.event_type,
            "token_id": self.token_id,
            "market": self.market,
            "source_timestamp_ms": self.source_timestamp_ms,
            "receive_timestamp": _iso(self.receive_timestamp),
            "side": self.side,
            "price": format(self.price, "f") if self.price is not None else None,
            "size": format(self.size, "f") if self.size is not None else None,
            "book_hash": self.book_hash,
            "coverage_valid": coverage_valid,
        }


def normalize_clob_market_message(
    payload: str | bytes | dict[str, Any] | list[Any],
    *,
    receive_timestamp: datetime,
) -> list[BookRecord]:
    """Normalize direct CLOB or SDK-shaped market messages into absolute records."""

    received = _aware(receive_timestamp)
    decoded = _decode(payload)
    if decoded is None:
        return []
    messages = decoded if isinstance(decoded, list) else [decoded]
    records: list[BookRecord] = []
    for message in messages:
        if not isinstance(message, dict):
            raise PublicBookError("CLOB message list entries must be objects")
        records.extend(_normalize_object(message, received))
    return records


def classify_captured_level(
    records: Iterable[dict[str, Any]],
    *,
    token_id: str,
    side: str,
    fill_price: str | Decimal,
    source_timestamp_ms: int,
    gaps: Iterable[dict[str, Any]] = (),
) -> str:
    """Apply the frozen exact-level diagnostic to normalized recorder output."""

    target_side = side.upper()
    if target_side not in {"BUY", "SELL"}:
        raise ValueError("side must be BUY or SELL")
    target_price = _decimal(fill_price, "fill price")
    required_from = source_timestamp_ms - 1_000
    for gap in gaps:
        if str(gap.get("token_id")) != token_id:
            continue
        start = gap.get("start_source_timestamp_ms")
        recovered = gap.get("recovered_source_timestamp_ms")
        if start is None:
            return "INELIGIBLE"
        start_ms = _integer(start, "gap start source timestamp")
        recovered_ms = (
            _integer(recovered, "gap recovery source timestamp") if recovered is not None else None
        )
        if start_ms < source_timestamp_ms and (recovered_ms is None or recovered_ms >= required_from):
            return "INELIGIBLE"

    initialized = False
    current_size = Decimal(0)
    continuous_start: int | None = None
    prior_line = 0
    for row in records:
        if str(row.get("token_id")) != token_id:
            continue
        line = _integer(row.get("line_number"), "book line number")
        if line <= prior_line:
            raise PublicBookError("book line numbers must increase per token")
        prior_line = line
        timestamp = _integer(row.get("source_timestamp_ms"), "book source timestamp")
        if timestamp >= source_timestamp_ms:
            continue
        record_type = str(row.get("record_type"))
        if record_type == "snapshot":
            initialized = bool(row.get("coverage_valid"))
            current_size = Decimal(0)
            continuous_start = None
            continue
        if not bool(row.get("coverage_valid")):
            initialized = False
            current_size = Decimal(0)
            continuous_start = None
            continue
        if not initialized:
            continue
        if str(row.get("side")) != target_side:
            continue
        if _decimal(row.get("price"), "book price") != target_price:
            continue
        new_size = _decimal(row.get("size"), "book size")
        if new_size > 0:
            if current_size <= 0:
                continuous_start = timestamp
            current_size = new_size
        else:
            current_size = Decimal(0)
            continuous_start = None
    if not initialized:
        return "INELIGIBLE"
    if current_size <= 0 or continuous_start is None:
        return "LATE_OR_UNSEEN_LEVEL"
    return (
        "PRE_POSITIONED_LEVEL"
        if continuous_start <= required_from
        else "LATE_OR_UNSEEN_LEVEL"
    )


def _normalize_object(message: dict[str, Any], received: datetime) -> list[BookRecord]:
    event_type = message.get("event_type", message.get("type"))
    if event_type not in {"book", "price_change"}:
        return []
    body = message.get("payload", message)
    if not isinstance(body, dict):
        raise PublicBookError("CLOB event payload must be an object")
    timestamp_raw = body.get("timestamp", message.get("timestamp"))
    source_timestamp_ms = _integer(timestamp_raw, "CLOB source timestamp")
    market = _optional_text(body.get("market", message.get("market")))

    if event_type == "book":
        token_id = _token(body)
        book_hash = _optional_text(body.get("hash", message.get("hash")))
        result = [
            BookRecord(
                record_type="snapshot",
                event_type="book",
                token_id=token_id,
                market=market,
                source_timestamp_ms=source_timestamp_ms,
                receive_timestamp=received,
                side=None,
                price=None,
                size=None,
                book_hash=book_hash,
            )
        ]
        for key, side in (("bids", "BUY"), ("asks", "SELL")):
            levels = body.get(key, [])
            if not isinstance(levels, list):
                raise PublicBookError(f"CLOB {key} must be a list")
            result.extend(
                _level_record(
                    level,
                    event_type="book",
                    token_id=token_id,
                    market=market,
                    source_timestamp_ms=source_timestamp_ms,
                    received=received,
                    side=side,
                    book_hash=book_hash,
                )
                for level in levels
            )
        return result

    changes = body.get("price_changes", body.get("priceChanges"))
    if not isinstance(changes, list):
        raise PublicBookError("CLOB price changes must be a list")
    result = []
    for change in changes:
        if not isinstance(change, dict):
            raise PublicBookError("CLOB price change must be an object")
        side = str(change.get("side", "")).upper()
        if side not in {"BUY", "SELL"}:
            raise PublicBookError(f"unsupported CLOB side {side!r}")
        result.append(
            _level_record(
                change,
                event_type="price_change",
                token_id=_token(change, fallback=body),
                market=market,
                source_timestamp_ms=source_timestamp_ms,
                received=received,
                side=side,
                book_hash=_optional_text(change.get("hash", body.get("hash"))),
            )
        )
    return result


def _level_record(
    level: dict[str, Any],
    *,
    event_type: str,
    token_id: str,
    market: str | None,
    source_timestamp_ms: int,
    received: datetime,
    side: str,
    book_hash: str | None,
) -> BookRecord:
    if not isinstance(level, dict):
        raise PublicBookError("CLOB book level must be an object")
    price = _decimal(level.get("price"), "CLOB price")
    size = _decimal(level.get("size"), "CLOB size")
    if price <= 0 or price > 1:
        raise PublicBookError("CLOB price must be in (0, 1]")
    if size < 0:
        raise PublicBookError("CLOB size must be non-negative")
    return BookRecord(
        record_type="level",
        event_type=event_type,
        token_id=token_id,
        market=market,
        source_timestamp_ms=source_timestamp_ms,
        receive_timestamp=received,
        side=side,
        price=price,
        size=size,
        book_hash=book_hash,
    )


class PublicBookRecorder:
    """Record a bounded public CLOB stream with explicit reconnect coverage gaps."""

    def __init__(self, *, url: str = _WS_URL) -> None:
        self.url = url

    async def run(
        self,
        *,
        output_dir: str | Path,
        duration_seconds: float,
        token_metadata: Sequence[dict[str, Any]],
        code_commit: str,
    ) -> dict[str, Any]:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        if not _SHA.fullmatch(code_commit):
            raise ValueError("code_commit must be a full lowercase 40-character SHA")
        metadata = _validate_metadata(token_metadata)
        token_ids = tuple(metadata)
        root = Path(output_dir)
        if root.exists():
            raise FileExistsError(f"refusing to overwrite existing output directory: {root}")
        root.mkdir(parents=True)
        raw_path = root / _RAW
        levels_path = root / _LEVELS
        gaps_path = root / _GAPS
        tokens_path = root / _TOKENS
        manifest_path = root / _MANIFEST
        tokens_path.write_bytes(_json_line({"schema_version": _SCHEMA, "tokens": list(metadata.values())}))

        started = datetime.now(timezone.utc)
        deadline = asyncio.get_running_loop().time() + duration_seconds
        initialized = {token_id: False for token_id in token_ids}
        last_source: dict[str, int] = {}
        pending_gap: dict[str, dict[str, Any]] = {}
        counts = {
            "raw_frames": 0,
            "snapshot_records": 0,
            "level_records": 0,
            "ineligible_delta_records": 0,
            "ignored_frames": 0,
        }
        reconnects = 0
        line_number = 0
        clean = False
        try:
            with raw_path.open("xb") as raw_handle, levels_path.open("xb") as level_handle, gaps_path.open("xb") as gap_handle:
                async for raw, received, reconnected in self._messages(deadline, token_ids):
                    if reconnected:
                        reconnects += 1
                        for token_id in token_ids:
                            initialized[token_id] = False
                            pending_gap[token_id] = {
                                "receive_timestamp": received,
                                "start_source_timestamp_ms": last_source.get(token_id),
                            }
                    counts["raw_frames"] += 1
                    raw_handle.write(
                        _json_line(
                            {
                                "schema_version": _SCHEMA,
                                "receive_timestamp": _iso(received),
                                "raw": _json_object(raw),
                            }
                        )
                    )
                    records = normalize_clob_market_message(raw, receive_timestamp=received)
                    if not records:
                        counts["ignored_frames"] += 1
                        continue
                    touched: dict[str, int] = {}
                    for record in records:
                        if record.token_id not in initialized:
                            continue
                        previous = touched.get(record.token_id, last_source.get(record.token_id))
                        if previous is not None and record.source_timestamp_ms < previous:
                            raise PublicBookError(
                                f"{record.token_id} CLOB source timestamp regressed"
                            )
                        touched[record.token_id] = record.source_timestamp_ms
                        if record.record_type == "snapshot":
                            if record.token_id in pending_gap:
                                gap_handle.write(
                                    _json_line(
                                        {
                                            "schema_version": _SCHEMA,
                                            "token_id": record.token_id,
                                            "reason": "CLOB_RECONNECT",
                                            "start_receive_timestamp": _iso(
                                                pending_gap[record.token_id]["receive_timestamp"]
                                            ),
                                            "start_source_timestamp_ms": pending_gap[
                                                record.token_id
                                            ]["start_source_timestamp_ms"],
                                            "recovered_receive_timestamp": _iso(received),
                                            "recovered_source_timestamp_ms": record.source_timestamp_ms,
                                        }
                                    )
                                )
                                pending_gap.pop(record.token_id)
                            initialized[record.token_id] = True
                            counts["snapshot_records"] += 1
                        coverage_valid = initialized[record.token_id]
                        if record.event_type == "price_change" and not coverage_valid:
                            counts["ineligible_delta_records"] += 1
                        line_number += 1
                        level_handle.write(
                            _json_line(
                                record.record(
                                    line_number=line_number,
                                    coverage_valid=coverage_valid,
                                )
                            )
                        )
                        if record.record_type == "level":
                            counts["level_records"] += 1
                    last_source.update(touched)
                    raw_handle.flush()
                    level_handle.flush()
                    gap_handle.flush()
                for token_id, gap in pending_gap.items():
                    gap_handle.write(
                        _json_line(
                            {
                                "schema_version": _SCHEMA,
                                "token_id": token_id,
                                "reason": "CLOB_RECONNECT_UNRECOVERED",
                                "start_receive_timestamp": _iso(gap["receive_timestamp"]),
                                "start_source_timestamp_ms": gap["start_source_timestamp_ms"],
                                "recovered_receive_timestamp": None,
                                "recovered_source_timestamp_ms": None,
                            }
                        )
                    )
            clean = True
        finally:
            if clean:
                ended = datetime.now(timezone.utc)
                manifest = {
                    "schema_version": _SCHEMA,
                    "contract_commit": _CONTRACT_COMMIT,
                    "code_commit": code_commit,
                    "url": self.url,
                    "started_at": _iso(started),
                    "ended_at": _iso(ended),
                    "duration_seconds": duration_seconds,
                    "token_ids": list(token_ids),
                    "event_counts": counts,
                    "reconnect_count": reconnects,
                    "initialized_at_finalize": initialized,
                    "clean_finalize": True,
                    "artifacts": {
                        path.name: _artifact(path)
                        for path in (raw_path, levels_path, gaps_path, tokens_path)
                    },
                }
                manifest_path.write_bytes(_json_line(manifest))
        if not all(initialized.values()):
            raise PublicBookError(f"bounded capture missed fresh snapshots: {initialized}")
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    async def _messages(
        self,
        deadline: float,
        token_ids: Sequence[str],
    ) -> AsyncIterator[tuple[str | bytes, datetime, bool]]:
        try:
            import websockets
        except ImportError as exc:  # pragma: no cover - packaging boundary
            raise PublicBookError("install project dependencies before CLOB collection") from exc
        first_connection = True
        while asyncio.get_running_loop().time() < deadline:
            try:
                async with websockets.connect(self.url, ping_interval=None, open_timeout=15) as socket:
                    await socket.send(json.dumps({"assets_ids": list(token_ids), "type": "market"}))
                    reconnected = not first_connection
                    first_connection = False
                    next_ping = asyncio.get_running_loop().time() + 10
                    while True:
                        now = asyncio.get_running_loop().time()
                        if now >= deadline:
                            return
                        if now >= next_ping:
                            await socket.send("PING")
                            next_ping = now + 10
                        timeout = min(max(0.05, next_ping - now), max(0.05, deadline - now))
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=timeout)
                        except asyncio.TimeoutError:
                            continue
                        yield raw, datetime.now(timezone.utc), reconnected
                        reconnected = False
            except Exception:  # pragma: no cover - live network boundary
                if asyncio.get_running_loop().time() >= deadline:
                    return
                await asyncio.sleep(min(1.0, max(0.0, deadline - asyncio.get_running_loop().time())))


def _validate_metadata(rows: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    if not rows:
        raise ValueError("token_metadata must not be empty")
    required = {"token_id", "condition_id", "asset", "window_seconds", "outcome"}
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        missing = required - row.keys()
        if missing:
            raise ValueError(f"token metadata missing fields: {sorted(missing)}")
        token_id = str(row["token_id"]).strip()
        if not token_id or token_id in result:
            raise ValueError("token IDs must be non-empty and unique")
        if str(row["outcome"]) not in {"Up", "Down"}:
            raise ValueError("token outcome must be Up or Down")
        if str(row["asset"]).upper() not in {"BTC", "ETH"}:
            raise ValueError("token asset must be BTC or ETH")
        if _integer(row["window_seconds"], "window_seconds") not in {300, 900}:
            raise ValueError("window_seconds must be 300 or 900")
        result[token_id] = dict(row)
    return result


def _decode(payload: str | bytes | dict[str, Any] | list[Any]) -> Any:
    if isinstance(payload, bytes):
        payload = payload.decode("utf-8")
    if isinstance(payload, str):
        if payload.strip() in {"", "PING", "PONG"}:
            return None
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise PublicBookError("CLOB message is not valid JSON") from exc
    return payload


def _token(value: dict[str, Any], fallback: dict[str, Any] | None = None) -> str:
    raw = value.get("asset_id", value.get("token_id", value.get("tokenId")))
    if raw is None and fallback is not None:
        raw = fallback.get("asset_id", fallback.get("token_id", fallback.get("tokenId")))
    token_id = str(raw).strip() if raw is not None else ""
    if not token_id:
        raise PublicBookError("CLOB event is missing token ID")
    return token_id


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool):
        raise PublicBookError(f"{label} must be an integer")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise PublicBookError(f"{label} must be an integer") from exc
    if str(value).strip() not in {str(parsed), f"{parsed}.0"} and not isinstance(value, int):
        raise PublicBookError(f"{label} must be an exact integer")
    return parsed


def _decimal(value: Any, label: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise PublicBookError(f"{label} must be a decimal") from exc
    if not parsed.is_finite():
        raise PublicBookError(f"{label} must be finite")
    return parsed


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise PublicBookError("receive timestamp must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _aware(value).isoformat().replace("+00:00", "Z")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Record a bounded public Polymarket CLOB stream")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--token-metadata", required=True)
    parser.add_argument("--code-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    metadata = json.loads(Path(args.token_metadata).read_text(encoding="utf-8"))
    if isinstance(metadata, dict) and "tokens" in metadata:
        metadata = metadata["tokens"]
    if not isinstance(metadata, list):
        raise SystemExit("token metadata must be a JSON list or an object with a tokens list")
    manifest = asyncio.run(
        PublicBookRecorder().run(
            output_dir=args.output_dir,
            duration_seconds=args.duration_seconds,
            token_metadata=metadata,
            code_commit=args.code_commit,
        )
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
