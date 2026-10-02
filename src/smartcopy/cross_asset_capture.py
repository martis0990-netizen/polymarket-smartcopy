"""Capture Bonereaper and seven asset-specific Chainlink TWAP streams for v5 research."""

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

_SCHEMA = "smartcopy-bonereaper-cross-asset-capture-v1"
_CONTRACT_COMMIT = "a696cf068dcb5b4555073d1d5636eec7efa05050"
_WALLET = "0xeebde7a0e019a63e6b476eb425505b7b3e6eba30"
_SYMBOLS = (
    "btc/usd",
    "eth/usd",
    "sol/usd",
    "xrp/usd",
    "bnb/usd",
    "doge/usd",
    "hype/usd",
)
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


async def run_cross_asset_capture(
    *,
    output_dir: str | Path,
    duration_seconds: float,
    code_commit: str,
    twap_recorder: ChainlinkTwapRecorder | None = None,
    wallet_observer: LiveWalletObserver | None = None,
) -> dict[str, Any]:
    if not 960 <= duration_seconds <= 14_400:
        raise ValueError("capture duration must be 960..14400 seconds")
    if _COMMIT.fullmatch(code_commit) is None:
        raise ValueError("code_commit must be a full lowercase Git SHA")
    root = Path(output_dir)
    if root.exists():
        raise FileExistsError(f"refusing to overwrite existing capture directory: {root}")
    root.mkdir(parents=True)
    chainlink_dir = root / "chainlink"
    wallet_dir = root / "wallet"
    recorder = twap_recorder or ChainlinkTwapRecorder(symbols=_SYMBOLS)
    observer = wallet_observer or LiveWalletObserver(
        PolymarketDataAPI(), wallet=_WALLET, poll_interval_seconds=1.0
    )

    started = datetime.now(timezone.utc)
    results = await asyncio.gather(
        asyncio.create_task(
            recorder.run(output_dir=chainlink_dir, duration_seconds=duration_seconds)
        ),
        asyncio.create_task(
            asyncio.to_thread(
                observer.run,
                output_dir=wallet_dir,
                duration_seconds=duration_seconds,
            )
        ),
        return_exceptions=True,
    )
    errors = [result for result in results if isinstance(result, BaseException)]
    if errors:
        raise errors[0]
    chainlink_manifest, wallet_manifest = results
    chainlink_path = chainlink_dir / "chainlink_twap_manifest.json"
    wallet_path = wallet_dir / "observer_manifest.json"
    if not chainlink_path.exists() or not wallet_path.exists():
        raise ValueError("capture component returned without an immutable manifest")
    if chainlink_manifest.get("clean_finalize") is not True:
        raise ValueError("Chainlink component did not cleanly finalize")
    if wallet_manifest.get("gap_failures") != 0:
        raise ValueError("wallet component had observation gaps")
    counts = chainlink_manifest["event_counts"]
    if set(counts) != set(_SYMBOLS) or any(counts[symbol] <= 0 for symbol in _SYMBOLS):
        raise ValueError(f"capture missed required cross-asset symbols: {counts}")
    # Match returned metadata to the bytes bound by the root manifest.
    if json.loads(chainlink_path.read_text()) != chainlink_manifest:
        raise ValueError("Chainlink child manifest does not match returned metadata")
    if json.loads(wallet_path.read_text()) != wallet_manifest:
        raise ValueError("wallet child manifest does not match returned metadata")

    manifest = {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "code_commit": code_commit,
        "wallet": _WALLET,
        "symbols": list(_SYMBOLS),
        "requested_duration_seconds": duration_seconds,
        "started_at": _iso(started),
        "ended_at": _iso(datetime.now(timezone.utc)),
        "clean_finalize": True,
        "eligibility_warmup_seconds": 660,
        "chainlink": {
            "manifest": "chainlink/chainlink_twap_manifest.json",
            "sha256": _sha256(chainlink_path),
            "event_counts": counts,
            "reconnect_count": chainlink_manifest["reconnect_count"],
        },
        "wallet_observer": {
            "manifest": "wallet/observer_manifest.json",
            "sha256": _sha256(wallet_path),
            "prospective_rows": wallet_manifest["emitted_prospective_row_count"],
            "gap_failures": wallet_manifest["gap_failures"],
        },
    }
    (root / "cross_asset_capture_manifest.json").write_bytes(
        (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode()
    )
    return manifest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--duration-seconds", required=True, type=float)
    parser.add_argument("--code-commit", required=True)
    args = parser.parse_args(argv)
    manifest = asyncio.run(
        run_cross_asset_capture(
            output_dir=args.output_dir,
            duration_seconds=args.duration_seconds,
            code_commit=args.code_commit,
        )
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
