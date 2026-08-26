"""Stage 3B: prospective wallet observation to executable Polymarket state join.

This module consumes immutable Stage 3A wallet observations plus TradingLab's normalized
Polymarket event log.  It measures the first provable top-of-book state after the wallet
activity became public; it does not make a copy decision.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Iterable

_SCHEMA = "smartcopy-executable-state-join-v1"
_OUTPUT = "executable_state_join.jsonl"
_MANIFEST = "join_manifest.json"
_ELIGIBLE_EVENT_TYPES = {"market_snapshot", "book_delta"}


class JoinDataError(ValueError):
    """Raised when evidence cannot support the frozen Stage 3B join semantics."""


class JoinStatus(StrEnum):
    JOINED = "JOINED"
    NO_EXECUTABLE_STATE = "NO_EXECUTABLE_STATE"


@dataclass(frozen=True, slots=True)
class WalletObservation:
    line_number: int
    token_id: str
    side: str
    source_price: float
    source_event_time: datetime
    first_observed_time: datetime
    condition_id: str
    transaction_hash: str | None
    outcome: str | None


@dataclass(frozen=True, slots=True)
class ExecutableStateJoin:
    wallet_line_number: int
    token_id: str
    side: str
    condition_id: str
    transaction_hash: str | None
    outcome: str | None
    source_price: float
    source_event_time: datetime
    first_observed_time: datetime
    status: JoinStatus
    market_line_number: int | None = None
    market_event_type: str | None = None
    market_event_time: datetime | None = None
    market_receive_time: datetime | None = None
    executable_price: float | None = None
    executable_size: float | None = None
    observation_to_state_seconds: float | None = None
    source_to_state_seconds: float | None = None
    deterioration: float | None = None
    deterioration_bps: float | None = None

    def as_json(self) -> dict[str, Any]:
        return {
            "wallet_line_number": self.wallet_line_number,
            "token_id": self.token_id,
            "side": self.side,
            "condition_id": self.condition_id,
            "transaction_hash": self.transaction_hash,
            "outcome": self.outcome,
            "source_price": self.source_price,
            "source_event_time": _iso(self.source_event_time),
            "first_observed_time": _iso(self.first_observed_time),
            "status": self.status.value,
            "market_line_number": self.market_line_number,
            "market_event_type": self.market_event_type,
            "market_event_time": _iso(self.market_event_time) if self.market_event_time else None,
            "market_receive_time": _iso(self.market_receive_time) if self.market_receive_time else None,
            "executable_price": self.executable_price,
            "executable_size": self.executable_size,
            "observation_to_state_seconds": self.observation_to_state_seconds,
            "source_to_state_seconds": self.source_to_state_seconds,
            "deterioration": self.deterioration,
            "deterioration_bps": self.deterioration_bps,
        }


def run_join(
    *,
    wallet_activity_path: str | Path,
    market_events_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Join Stage 3A observations to the first evidenced post-observation PM BBO state."""

    wallet_path = Path(wallet_activity_path)
    market_path = Path(market_events_path)
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    output_path = root / _OUTPUT
    manifest_path = root / _MANIFEST
    for path in (output_path, manifest_path):
        if path.exists():
            raise FileExistsError(f"refusing to overwrite Stage 3B artifact: {path}")

    observations, wallet_sha = _load_wallet_observations(wallet_path)
    joins, market_sha, market_lines = _scan_market_events(market_path, observations)

    output_digest = hashlib.sha256()
    with output_path.open("xb") as handle:
        for joined in joins:
            raw = _json_line(joined.as_json())
            handle.write(raw)
            output_digest.update(raw)
        handle.flush()

    joined_rows = [row for row in joins if row.status == JoinStatus.JOINED]
    delays = [row.observation_to_state_seconds for row in joined_rows]
    deterioration_bps = [row.deterioration_bps for row in joined_rows]
    assert all(value is not None for value in delays)
    assert all(value is not None for value in deterioration_bps)

    manifest = {
        "schema_version": _SCHEMA,
        "wallet_rows": len(observations),
        "joined_rows": len(joined_rows),
        "no_executable_state_rows": len(observations) - len(joined_rows),
        "observation_to_state_seconds": _summary(float(value) for value in delays if value is not None),
        "deterioration_bps": _summary(
            float(value) for value in deterioration_bps if value is not None
        ),
        "inputs": {
            "wallet_activity": {
                "path": str(wallet_path),
                "bytes": wallet_path.stat().st_size,
                "sha256": wallet_sha,
            },
            "market_events": {
                "path": str(market_path),
                "bytes": market_path.stat().st_size,
                "sha256": market_sha,
                "line_count": market_lines,
            },
        },
        "artifacts": {
            _OUTPUT: {
                "bytes": output_path.stat().st_size,
                "sha256": output_digest.hexdigest(),
            }
        },
    }
    with manifest_path.open("xb") as handle:
        handle.write(_json_line(manifest))
        handle.flush()
    return manifest


def _load_wallet_observations(path: Path) -> tuple[list[WalletObservation], str]:
    digest = hashlib.sha256()
    rows: list[WalletObservation] = []
    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            digest.update(raw)
            payload = _decode_json_object(raw, path=path, line_number=line_number)
            if payload.get("observation_mode") != "live_observed":
                raise JoinDataError(f"wallet line {line_number}: observation_mode must be live_observed")
            if str(payload.get("activity_type", "")).upper() != "TRADE":
                raise JoinDataError(f"wallet line {line_number}: activity_type must be TRADE")
            side = str(payload.get("side", "")).upper()
            if side not in {"BUY", "SELL"}:
                raise JoinDataError(f"wallet line {line_number}: side must be BUY or SELL")
            token_id = _normalized_text(payload.get("asset"), f"wallet line {line_number} asset")
            source_price = _positive(payload.get("price"), f"wallet line {line_number} price")
            source_time = _timestamp(
                payload.get("source_event_time"), f"wallet line {line_number} source_event_time"
            )
            observed_time = _timestamp(
                payload.get("first_observed_time"), f"wallet line {line_number} first_observed_time"
            )
            if observed_time < source_time:
                raise JoinDataError(f"wallet line {line_number}: first_observed_time precedes source event")
            condition_id = _normalized_text(
                payload.get("condition_id"), f"wallet line {line_number} condition_id"
            )
            transaction_hash = _optional_text(payload.get("transaction_hash"))
            outcome = _optional_text(payload.get("outcome"))
            rows.append(
                WalletObservation(
                    line_number=line_number,
                    token_id=token_id,
                    side=side,
                    source_price=source_price,
                    source_event_time=source_time,
                    first_observed_time=observed_time,
                    condition_id=condition_id,
                    transaction_hash=transaction_hash,
                    outcome=outcome,
                )
            )
    return rows, digest.hexdigest()


def _scan_market_events(
    path: Path, observations: list[WalletObservation]
) -> tuple[list[ExecutableStateJoin], str, int]:
    results: list[ExecutableStateJoin | None] = [None] * len(observations)
    pending: dict[tuple[str, str], deque[int]] = defaultdict(deque)
    for index in sorted(
        range(len(observations)),
        key=lambda idx: (observations[idx].first_observed_time, observations[idx].line_number),
    ):
        item = observations[index]
        pending[(item.token_id, item.side)].append(index)

    relevant_tokens = {item.token_id for item in observations}
    last_receive_by_token: dict[str, datetime] = {}
    digest = hashlib.sha256()
    line_count = 0

    with path.open("rb") as handle:
        for line_number, raw in enumerate(handle, start=1):
            line_count = line_number
            digest.update(raw)
            payload = _decode_json_object(raw, path=path, line_number=line_number)
            if payload.get("venue") != "polymarket":
                continue
            token_id = payload.get("instrument")
            if token_id not in relevant_tokens:
                continue
            event_type = payload.get("event_type")
            if event_type not in _ELIGIBLE_EVENT_TYPES:
                continue

            receive_time = _timestamp(
                payload.get("receive_ts"), f"market line {line_number} receive_ts"
            )
            previous_receive = last_receive_by_token.get(token_id)
            if previous_receive is not None and receive_time < previous_receive:
                raise JoinDataError(
                    f"market line {line_number}: receive_ts regressed for token {token_id}"
                )
            last_receive_by_token[token_id] = receive_time
            event_time = _timestamp(payload.get("ts"), f"market line {line_number} ts")

            for side in ("BUY", "SELL"):
                queue = pending.get((token_id, side))
                if not queue or observations[queue[0]].first_observed_time > receive_time:
                    continue
                quote = _executable_quote(payload, side=side, line_number=line_number)
                if quote is None:
                    continue
                executable_price, executable_size = quote
                while queue and observations[queue[0]].first_observed_time <= receive_time:
                    index = queue.popleft()
                    item = observations[index]
                    observation_lag = (receive_time - item.first_observed_time).total_seconds()
                    source_lag = (receive_time - item.source_event_time).total_seconds()
                    if observation_lag < 0 or source_lag < 0:
                        raise JoinDataError("negative Stage 3B join latency")
                    deterioration = (
                        executable_price - item.source_price
                        if item.side == "BUY"
                        else item.source_price - executable_price
                    )
                    results[index] = ExecutableStateJoin(
                        wallet_line_number=item.line_number,
                        token_id=item.token_id,
                        side=item.side,
                        condition_id=item.condition_id,
                        transaction_hash=item.transaction_hash,
                        outcome=item.outcome,
                        source_price=item.source_price,
                        source_event_time=item.source_event_time,
                        first_observed_time=item.first_observed_time,
                        status=JoinStatus.JOINED,
                        market_line_number=line_number,
                        market_event_type=str(event_type),
                        market_event_time=event_time,
                        market_receive_time=receive_time,
                        executable_price=executable_price,
                        executable_size=executable_size,
                        observation_to_state_seconds=observation_lag,
                        source_to_state_seconds=source_lag,
                        deterioration=deterioration,
                        deterioration_bps=deterioration / item.source_price * 10_000.0,
                    )

    finalized: list[ExecutableStateJoin] = []
    for index, item in enumerate(observations):
        joined = results[index]
        if joined is None:
            joined = ExecutableStateJoin(
                wallet_line_number=item.line_number,
                token_id=item.token_id,
                side=item.side,
                condition_id=item.condition_id,
                transaction_hash=item.transaction_hash,
                outcome=item.outcome,
                source_price=item.source_price,
                source_event_time=item.source_event_time,
                first_observed_time=item.first_observed_time,
                status=JoinStatus.NO_EXECUTABLE_STATE,
            )
        finalized.append(joined)
    return finalized, digest.hexdigest(), line_count


def _executable_quote(
    payload: dict[str, Any], *, side: str, line_number: int
) -> tuple[float, float] | None:
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict):
        raise JoinDataError(f"market line {line_number}: metrics must be an object")
    if side == "BUY":
        price_key, size_key = "best_ask_price", "best_ask_size"
    else:
        price_key, size_key = "best_bid_price", "best_bid_size"

    bbo_price = _optional_positive(metrics.get(price_key), f"market line {line_number} {price_key}")
    if bbo_price is None:
        return None
    bbo_size = _optional_positive(metrics.get(size_key), f"market line {line_number} {size_key}")
    if bbo_size is not None:
        return bbo_price, bbo_size

    if payload.get("event_type") != "book_delta":
        return None
    delta_price = _optional_positive(payload.get("price"), f"market line {line_number} price")
    delta_size = _optional_positive(payload.get("size"), f"market line {line_number} size")
    if delta_price is None or delta_size is None:
        return None
    if math.isclose(delta_price, bbo_price, rel_tol=0.0, abs_tol=1e-12):
        return bbo_price, delta_size
    return None


def _decode_json_object(raw: bytes, *, path: Path, line_number: int) -> dict[str, Any]:
    if not raw.strip():
        raise JoinDataError(f"{path}: blank JSONL line {line_number}")
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JoinDataError(f"{path}: invalid JSON at line {line_number}") from exc
    if not isinstance(payload, dict):
        raise JoinDataError(f"{path}: line {line_number} must be a JSON object")
    return payload


def _timestamp(value: object, label: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise JoinDataError(f"{label} must be a non-empty ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise JoinDataError(f"{label} is not a valid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise JoinDataError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _normalized_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise JoinDataError(f"{label} must be a non-empty whitespace-normalized string")
    return value


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or value != value.strip():
        raise JoinDataError("optional text value must be null or a normalized non-empty string")
    return value


def _positive(value: object, label: str) -> float:
    if isinstance(value, bool):
        raise JoinDataError(f"{label} must be numeric, not boolean")
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise JoinDataError(f"{label} must be numeric") from exc
    if not math.isfinite(parsed) or parsed <= 0:
        raise JoinDataError(f"{label} must be finite and positive")
    return parsed


def _optional_positive(value: object, label: str) -> float | None:
    if value is None:
        return None
    return _positive(value, label)


def _summary(values: Iterable[float]) -> dict[str, float | int | None]:
    ordered = sorted(float(value) for value in values)
    return {
        "count": len(ordered),
        "p50": _quantile(ordered, 0.50),
        "p90": _quantile(ordered, 0.90),
        "p99": _quantile(ordered, 0.99),
    }


def _quantile(ordered: list[float], q: float) -> float | None:
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


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


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Join prospective SmartCopy wallet observations to executable PM state"
    )
    parser.add_argument("--wallet-activity", required=True)
    parser.add_argument("--market-events", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    manifest = run_join(
        wallet_activity_path=args.wallet_activity,
        market_events_path=args.market_events,
        output_dir=args.output,
    )
    print(json.dumps(manifest, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
