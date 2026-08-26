"""Prospective public wallet activity observer.

The observer is deliberately narrow: it establishes truthful LIVE_OBSERVED evidence
and source-to-observation latency. It does not make trading decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from .models import ObservationMode, WalletActivity
from .polymarket import PolymarketDataAPI

_SCHEMA = "smartcopy-live-wallet-observer-v1"
_LIVE = "live_activity.jsonl"
_CYCLES = "poll_cycles.jsonl"
_MANIFEST = "observer_manifest.json"

Clock = Callable[[], datetime]
Monotonic = Callable[[], float]
Sleeper = Callable[[float], None]


class ObservationGapError(RuntimeError):
    """Raised when live pagination cannot prove catch-up to prior evidence."""


@dataclass(frozen=True, slots=True)
class PollCycle:
    baseline: bool
    started_at: datetime
    finished_at: datetime
    pages_fetched: int
    max_offset: int
    rows_returned: int
    baseline_rows: int
    emitted_rows: tuple[WalletActivity, ...]
    already_seen_rows: int
    reached_prior_evidence: bool
    exhausted_page: bool


class LiveWalletObserver:
    def __init__(
        self,
        client: PolymarketDataAPI,
        *,
        wallet: str,
        page_size: int = 500,
        poll_interval_seconds: float = 1.0,
        clock: Clock | None = None,
        monotonic: Monotonic = time.monotonic,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        if not 1 <= page_size <= 500:
            raise ValueError("page_size must be 1..500")
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        self.client = client
        self.wallet = wallet.lower()
        self.page_size = page_size
        self.poll_interval_seconds = poll_interval_seconds
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.monotonic = monotonic
        self.sleeper = sleeper
        self._seen: set[tuple[Any, ...]] = set()
        self._baseline_established = False

    def poll(self) -> PollCycle:
        """Perform one baseline or prospective catch-up cycle."""

        started = _aware(self.clock(), "observer clock")
        baseline = not self._baseline_established
        known_before_cycle = set(self._seen)
        emitted: list[WalletActivity] = []
        emitted_ids: set[tuple[Any, ...]] = set()
        pages = 0
        rows_returned = 0
        already_seen = 0
        baseline_rows = 0
        max_offset = 0
        reached_prior = False
        exhausted_page = False
        offset = 0

        while True:
            if offset > self.client.activity_offset_cap:
                raise ObservationGapError(
                    f"live activity catch-up exceeded API offset cap {self.client.activity_offset_cap}"
                )
            page = self.client.activity_page(
                self.wallet,
                limit=self.page_size,
                offset=offset,
                activity_type="TRADE",
                sort_direction="DESC",
                observation_mode=ObservationMode.LIVE_OBSERVED,
            )
            pages += 1
            max_offset = max(max_offset, offset)
            rows_returned += len(page)

            if baseline:
                for row in page:
                    self._validate_live_row(row)
                    identity = activity_identity(row)
                    if identity not in self._seen:
                        self._seen.add(identity)
                        baseline_rows += 1
                exhausted_page = len(page) < self.page_size
                # The first page is a watermark snapshot, not a historical backfill.
                break

            page_reached_prior = False
            for row in page:
                self._validate_live_row(row)
                identity = activity_identity(row)
                if identity in known_before_cycle:
                    page_reached_prior = True
                    reached_prior = True
                    already_seen += 1
                    continue
                if identity in emitted_ids:
                    already_seen += 1
                    continue
                emitted.append(row)
                emitted_ids.add(identity)

            exhausted_page = len(page) < self.page_size
            if page_reached_prior or exhausted_page:
                break
            if offset == self.client.activity_offset_cap:
                raise ObservationGapError(
                    "live activity filled the final addressable page without reaching evidence known before the cycle"
                )
            next_offset = offset + self.page_size
            if next_offset > self.client.activity_offset_cap:
                raise ObservationGapError(
                    f"live activity requires offset {next_offset} beyond API cap {self.client.activity_offset_cap}"
                )
            offset = next_offset

        if not baseline:
            for identity in emitted_ids:
                self._seen.add(identity)
        else:
            self._baseline_established = True

        emitted.sort(key=_activity_sort_key)
        finished = _aware(self.clock(), "observer clock")
        if finished < started:
            raise ValueError("observer clock regressed during poll cycle")
        return PollCycle(
            baseline=baseline,
            started_at=started,
            finished_at=finished,
            pages_fetched=pages,
            max_offset=max_offset,
            rows_returned=rows_returned,
            baseline_rows=baseline_rows,
            emitted_rows=tuple(emitted),
            already_seen_rows=already_seen,
            reached_prior_evidence=reached_prior,
            exhausted_page=exhausted_page,
        )

    def run(self, *, output_dir: str | Path, duration_seconds: float) -> dict[str, Any]:
        if duration_seconds <= 0:
            raise ValueError("duration_seconds must be positive")
        root = Path(output_dir)
        root.mkdir(parents=True, exist_ok=True)
        live_path = root / _LIVE
        cycles_path = root / _CYCLES
        manifest_path = root / _MANIFEST
        for path in (live_path, cycles_path, manifest_path):
            if path.exists():
                raise FileExistsError(f"refusing to overwrite observer artifact: {path}")

        started_at = _aware(self.clock(), "observer clock")
        deadline = self.monotonic() + duration_seconds
        cycle_count = 0
        api_pages = 0
        baseline_rows = 0
        emitted_count = 0
        already_seen_count = 0
        max_offset = 0
        gap_failures = 0
        delays: list[float] = []
        first_source: datetime | None = None
        last_source: datetime | None = None
        first_observed: datetime | None = None
        last_observed: datetime | None = None

        # Create streaming evidence files before network I/O, but manifest only after clean finalize.
        with live_path.open("xb") as live_handle, cycles_path.open("xb") as cycles_handle:
            while True:
                try:
                    cycle = self.poll()
                except ObservationGapError:
                    gap_failures += 1
                    raise
                cycle_count += 1
                api_pages += cycle.pages_fetched
                baseline_rows += cycle.baseline_rows
                already_seen_count += cycle.already_seen_rows
                max_offset = max(max_offset, cycle.max_offset)

                for row in cycle.emitted_rows:
                    payload = normalized_live_activity(row)
                    live_handle.write(_json_line(payload))
                    emitted_count += 1
                    delay = (row.first_observed_time - row.source_event_time).total_seconds()
                    if delay < 0:
                        raise ValueError("negative source-to-observed delay")
                    delays.append(delay)
                    first_source = row.source_event_time if first_source is None else min(first_source, row.source_event_time)
                    last_source = row.source_event_time if last_source is None else max(last_source, row.source_event_time)
                    first_observed = row.first_observed_time if first_observed is None else min(first_observed, row.first_observed_time)
                    last_observed = row.first_observed_time if last_observed is None else max(last_observed, row.first_observed_time)

                cycles_handle.write(_json_line(cycle_record(cycle)))
                live_handle.flush()
                cycles_handle.flush()

                now = self.monotonic()
                if now >= deadline:
                    break
                self.sleeper(min(self.poll_interval_seconds, max(0.0, deadline - now)))

        ended_at = _aware(self.clock(), "observer clock")
        if ended_at < started_at:
            raise ValueError("observer clock regressed across run")
        manifest = {
            "schema_version": _SCHEMA,
            "wallet": self.wallet,
            "observation_mode": ObservationMode.LIVE_OBSERVED.value,
            "activity_type": "TRADE",
            "poll_interval_seconds": self.poll_interval_seconds,
            "page_size": self.page_size,
            "activity_offset_cap": self.client.activity_offset_cap,
            "started_at": _iso(started_at),
            "ended_at": _iso(ended_at),
            "poll_cycle_count": cycle_count,
            "api_page_count": api_pages,
            "baseline_row_count": baseline_rows,
            "emitted_prospective_row_count": emitted_count,
            "already_seen_row_count": already_seen_count,
            "max_offset_reached": max_offset,
            "gap_failures": gap_failures,
            "first_source_event_time": _iso(first_source) if first_source else None,
            "last_source_event_time": _iso(last_source) if last_source else None,
            "first_observed_time": _iso(first_observed) if first_observed else None,
            "last_observed_time": _iso(last_observed) if last_observed else None,
            "observation_delay_seconds": {
                "p50": _quantile(delays, 0.50),
                "p90": _quantile(delays, 0.90),
                "p99": _quantile(delays, 0.99),
            },
            "artifacts": {
                _LIVE: _artifact(live_path),
                _CYCLES: _artifact(cycles_path),
            },
        }
        with manifest_path.open("xb") as handle:
            handle.write(_json_line(manifest))
            handle.flush()
        return manifest

    def _validate_live_row(self, row: WalletActivity) -> None:
        if row.proxy_wallet != self.wallet:
            raise ValueError(f"observer row wallet mismatch: {row.proxy_wallet}")
        if row.observation_mode != ObservationMode.LIVE_OBSERVED:
            raise ValueError("observer received non-LIVE_OBSERVED row")
        if row.activity_type.upper() != "TRADE":
            raise ValueError(f"observer received unexpected activity type {row.activity_type}")
        if row.first_observed_time < row.source_event_time:
            raise ValueError("negative source-to-observed delay")


def activity_identity(item: WalletActivity) -> tuple[Any, ...]:
    return (
        item.proxy_wallet,
        item.source_event_time,
        item.condition_id,
        item.activity_type,
        item.side,
        item.size,
        item.usdc_size,
        item.price,
        item.asset,
        item.transaction_hash,
        item.outcome,
    )


def normalized_live_activity(item: WalletActivity) -> dict[str, Any]:
    return {
        "proxy_wallet": item.proxy_wallet,
        "source_event_time": _iso(item.source_event_time),
        "first_observed_time": _iso(item.first_observed_time),
        "observation_delay_seconds": (item.first_observed_time - item.source_event_time).total_seconds(),
        "observation_mode": item.observation_mode.value,
        "condition_id": item.condition_id,
        "activity_type": item.activity_type,
        "side": item.side,
        "size": item.size,
        "usdc_size": item.usdc_size,
        "price": item.price,
        "asset": item.asset,
        "transaction_hash": item.transaction_hash,
        "title": item.title,
        "slug": item.slug,
        "event_slug": item.event_slug,
        "outcome": item.outcome,
        "raw": item.raw,
    }


def cycle_record(cycle: PollCycle) -> dict[str, Any]:
    return {
        "baseline": cycle.baseline,
        "started_at": _iso(cycle.started_at),
        "finished_at": _iso(cycle.finished_at),
        "pages_fetched": cycle.pages_fetched,
        "max_offset": cycle.max_offset,
        "rows_returned": cycle.rows_returned,
        "baseline_rows": cycle.baseline_rows,
        "emitted_rows": len(cycle.emitted_rows),
        "already_seen_rows": cycle.already_seen_rows,
        "reached_prior_evidence": cycle.reached_prior_evidence,
        "exhausted_page": cycle.exhausted_page,
    }


def _activity_sort_key(item: WalletActivity) -> tuple[Any, ...]:
    return (
        item.source_event_time,
        item.transaction_hash or "",
        item.condition_id,
        item.asset or "",
        item.outcome or "",
    )


def _artifact(path: Path) -> dict[str, Any]:
    return {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha256(path)}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _json_line(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def _aware(value: datetime, label: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _quantile(values: Iterable[float], q: float) -> float | None:
    ordered = sorted(float(value) for value in values)
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
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def main() -> None:
    parser = argparse.ArgumentParser(description="Prospective SmartCopy wallet activity observer")
    parser.add_argument("--wallet", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--duration-seconds", type=float, required=True)
    parser.add_argument("--poll-interval-seconds", type=float, default=1.0)
    args = parser.parse_args()
    observer = LiveWalletObserver(
        PolymarketDataAPI(),
        wallet=args.wallet,
        poll_interval_seconds=args.poll_interval_seconds,
    )
    manifest = observer.run(output_dir=args.output, duration_seconds=args.duration_seconds)
    print(json.dumps(manifest, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
