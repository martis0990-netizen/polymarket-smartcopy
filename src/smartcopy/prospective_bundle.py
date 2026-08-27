"""Run the frozen prospective Chainlink and Bonereaper observers over one interval."""

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

_SCHEMA = "smartcopy-bonereaper-prospective-bundle-v2"
_CONTRACT_COMMIT = "0065f7ca8c38e435e0a859b06724040cfd01a900"
_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_MANIFEST = "prospective_bundle_manifest.json"
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


async def run_bundle(
    *,
    output_dir: str | Path,
    duration_seconds: float,
    code_commit: str,
    twap_recorder: ChainlinkTwapRecorder | None = None,
    wallet_observer: LiveWalletObserver | None = None,
) -> dict[str, Any]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    root = Path(output_dir)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite existing bundle directory: {root}")
    root.mkdir(parents=True)
    chainlink_dir = root / "chainlink"
    wallet_dir = root / "wallet"
    manifest_path = root / _MANIFEST
    recorder = twap_recorder or ChainlinkTwapRecorder()
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
    chainlink_manifest, wallet_manifest = await asyncio.gather(chainlink_task, wallet_task)
    ended = datetime.now(timezone.utc)
    manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "wallet": _WALLET,
        "requested_duration_seconds": duration_seconds,
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
