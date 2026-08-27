"""Run the frozen prospective Chainlink, wallet and public-CLOB bundle v3."""

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

_SCHEMA = "smartcopy-bonereaper-prospective-bundle-v3"
_CONTRACT_COMMIT = "418489d12dc0affedc19468201413b57e634cc0c"
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
    market_discovery: GammaMarketDiscovery | None = None,
) -> dict[str, Any]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if duration_seconds > _MAX_DURATION_SECONDS:
        raise ValueError(f"v3 bundle duration must not exceed {_MAX_DURATION_SECONDS:g} seconds")
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
    )
    discovery_ended = datetime.now(timezone.utc)
    if not token_metadata:
        raise ValueError("market discovery returned no bound token metadata")

    root.mkdir(parents=True)
    chainlink_dir = root / "chainlink"
    wallet_dir = root / "wallet"
    public_book_dir = root / "public_book"
    manifest_path = root / _MANIFEST
    recorder = twap_recorder or ChainlinkTwapRecorder()
    clob = book_recorder or PublicBookRecorder()
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
    book_task = asyncio.create_task(
        clob.run(
            output_dir=public_book_dir,
            duration_seconds=duration_seconds,
            token_metadata=token_metadata,
            code_commit=code_commit,
        )
    )
    results = await asyncio.gather(
        chainlink_task,
        wallet_task,
        book_task,
        return_exceptions=True,
    )
    errors = [result for result in results if isinstance(result, BaseException)]
    if errors:
        raise errors[0]
    chainlink_manifest, wallet_manifest, book_manifest = results
    ended = datetime.now(timezone.utc)
    book_manifest_path = public_book_dir / "public_book_manifest.json"
    token_metadata_path = public_book_dir / "token_metadata.json"
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
        "public_book": {
            "manifest": str(Path("public_book") / book_manifest_path.name),
            "sha256": _sha256(book_manifest_path),
            "token_metadata": str(Path("public_book") / token_metadata_path.name),
            "token_metadata_sha256": _sha256(token_metadata_path),
            "event_counts": book_manifest["event_counts"],
            "reconnect_count": book_manifest["reconnect_count"],
            "initialized_at_finalize": book_manifest["initialized_at_finalize"],
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
