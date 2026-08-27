"""Run the frozen prospective Chainlink, wallet and split public-CLOB bundle v5."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from smartcopy.live_observer import LiveWalletObserver
from smartcopy.polymarket import PolymarketDataAPI
from smartcopy.prospective_signal import ChainlinkTwapRecorder
from smartcopy.public_book import GammaMarketDiscovery, PublicBookRecorder

_SCHEMA = "smartcopy-bonereaper-prospective-bundle-v5"
_CONTRACT_COMMIT = "5af360f9eba6e650c42e4ada2ddbcf00ec87f408"
_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_MANIFEST = "prospective_bundle_manifest.json"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_MAX_DURATION_SECONDS = 120.0
_DISCOVERY_SAFETY_SECONDS = 60.0


async def run_bundle(
    *,
    output_dir: str | Path,
    duration_seconds: float,
    code_commit: str,
    twap_recorder: ChainlinkTwapRecorder | None = None,
    wallet_observer: LiveWalletObserver | None = None,
    book_recorder: PublicBookRecorder | None = None,
    current_book_recorder: PublicBookRecorder | None = None,
    safe_book_recorder: PublicBookRecorder | None = None,
    market_discovery: GammaMarketDiscovery | None = None,
) -> dict[str, Any]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if duration_seconds > _MAX_DURATION_SECONDS:
        raise ValueError(f"v5 bundle duration must not exceed {_MAX_DURATION_SECONDS:g} seconds")
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    root = Path(output_dir)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite existing bundle directory: {root}")

    discovery_started = datetime.now(timezone.utc)
    discovery = market_discovery or GammaMarketDiscovery()
    token_metadata = await asyncio.to_thread(
        discovery.token_metadata,
        at=discovery_started,
        min_remaining_seconds=duration_seconds + _DISCOVERY_SAFETY_SECONDS,
        include_current=True,
    )
    discovery_ended = datetime.now(timezone.utc)
    if not token_metadata:
        raise ValueError("market discovery returned no bound token metadata")
    current_metadata = [row for row in token_metadata if "current" in row.get("coverage_roles", ())]
    safe_metadata = [
        row
        for row in token_metadata
        if "safe" in row.get("coverage_roles", ()) and "current" not in row.get("coverage_roles", ())
    ]
    current_tokens = {str(row["token_id"]) for row in current_metadata}
    safe_tokens = {str(row["token_id"]) for row in safe_metadata}
    if not current_metadata or not safe_metadata:
        raise ValueError("v5 discovery requires non-empty current and following-safe token groups")
    if current_tokens & safe_tokens or current_tokens | safe_tokens != {
        str(row["token_id"]) for row in token_metadata
    }:
        raise ValueError("v5 discovery token groups must be disjoint and exhaustive")

    root.mkdir(parents=True)
    chainlink_dir = root / "chainlink"
    wallet_dir = root / "wallet"
    current_book_dir = root / "current_public_book"
    safe_book_dir = root / "safe_public_book"
    manifest_path = root / _MANIFEST
    recorder = twap_recorder or ChainlinkTwapRecorder()
    current_clob = current_book_recorder or book_recorder or PublicBookRecorder()
    safe_clob = safe_book_recorder or book_recorder or PublicBookRecorder()
    observer = wallet_observer or LiveWalletObserver(
        PolymarketDataAPI(),
        wallet=_WALLET,
        poll_interval_seconds=1.0,
    )
    started = datetime.now(timezone.utc)
    chainlink_task = asyncio.create_task(
        recorder.run(output_dir=chainlink_dir, duration_seconds=duration_seconds)
    )
    wallet_task = asyncio.create_task(
        asyncio.to_thread(
            observer.run,
            output_dir=wallet_dir,
            duration_seconds=duration_seconds,
        )
    )
    current_book_task = asyncio.create_task(
        current_clob.run(
            output_dir=current_book_dir,
            duration_seconds=duration_seconds,
            token_metadata=current_metadata,
            code_commit=code_commit,
        )
    )
    safe_book_task = asyncio.create_task(
        safe_clob.run(
            output_dir=safe_book_dir,
            duration_seconds=duration_seconds,
            token_metadata=safe_metadata,
            code_commit=code_commit,
        )
    )
    results = await asyncio.gather(
        chainlink_task,
        wallet_task,
        current_book_task,
        safe_book_task,
        return_exceptions=True,
    )
    errors = [result for result in results if isinstance(result, BaseException)]
    if errors:
        raise errors[0]
    chainlink_manifest, wallet_manifest, current_book_manifest, safe_book_manifest = results
    ended = datetime.now(timezone.utc)
    def book_binding(directory: Path, child_manifest: dict[str, Any]) -> dict[str, Any]:
        child_path = directory / "public_book_manifest.json"
        metadata_path = directory / "token_metadata.json"
        return {
            "manifest": str(directory.relative_to(root) / child_path.name),
            "sha256": _sha256(child_path),
            "token_metadata": str(directory.relative_to(root) / metadata_path.name),
            "token_metadata_sha256": _sha256(metadata_path),
            "event_counts": child_manifest["event_counts"],
            "reconnect_count": child_manifest["reconnect_count"],
            "initialized_at_finalize": child_manifest["initialized_at_finalize"],
        }
    manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "wallet": _WALLET,
        "requested_duration_seconds": duration_seconds,
        "discovery_started_at": _iso(discovery_started),
        "discovery_ended_at": _iso(discovery_ended),
        "started_at": _iso(started),
        "ended_at": _iso(ended),
        "clean_finalize": True,
        "chainlink": {
            "manifest": str(Path("chainlink") / "chainlink_twap_manifest.json"),
            "sha256": _sha256(chainlink_dir / "chainlink_twap_manifest.json"),
            "event_counts": chainlink_manifest["event_counts"],
            "reconnect_count": chainlink_manifest["reconnect_count"],
        },
        "wallet_observer": {
            "manifest": str(Path("wallet") / "observer_manifest.json"),
            "sha256": _sha256(wallet_dir / "observer_manifest.json"),
            "prospective_rows": wallet_manifest["emitted_prospective_row_count"],
            "gap_failures": wallet_manifest["gap_failures"],
        },
        "public_books": {
            "current": book_binding(current_book_dir, current_book_manifest),
            "safe": book_binding(safe_book_dir, safe_book_manifest),
        },
    }
    manifest_path.write_bytes(_json_line(manifest))
    return manifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_line(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration-seconds", required=True, type=float)
    parser.add_argument("--code-commit", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    manifest = asyncio.run(
        run_bundle(
            output_dir=args.output_dir,
            duration_seconds=args.duration_seconds,
            code_commit=args.code_commit,
        )
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
