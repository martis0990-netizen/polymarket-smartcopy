from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest

from smartcopy.prospective_bundle import run_bundle

CODE_COMMIT = "a" * 40


class FakeTwapRecorder:
    async def run(self, *, output_dir, duration_seconds):
        root = Path(output_dir)
        root.mkdir()
        manifest = {"event_counts": {"btc/usd": 2, "eth/usd": 2}, "reconnect_count": 0}
        (root / "chainlink_twap_manifest.json").write_text(json.dumps(manifest) + "\n")
        return manifest


class FakeWalletObserver:
    def run(self, *, output_dir, duration_seconds):
        root = Path(output_dir)
        root.mkdir()
        manifest = {"emitted_prospective_row_count": 3, "gap_failures": 0}
        (root / "observer_manifest.json").write_text(json.dumps(manifest) + "\n")
        return manifest


class FakeMarketDiscovery:
    def token_metadata(self, *, at, min_remaining_seconds, include_current):
        assert min_remaining_seconds == 61
        assert include_current is True
        return [
            {
                "token_id": "token-up",
                "condition_id": "condition",
                "asset": "BTC",
                "window_seconds": 300,
                "outcome": "Up",
            }
        ]


class FakeBookRecorder:
    async def run(self, *, output_dir, duration_seconds, token_metadata, code_commit):
        root = Path(output_dir)
        root.mkdir()
        (root / "token_metadata.json").write_text(json.dumps({"tokens": token_metadata}) + "\n")
        manifest = {
            "event_counts": {"raw_frames": 5, "snapshot_records": 1, "level_records": 4},
            "reconnect_count": 0,
            "initialized_at_finalize": {"token-up": True},
        }
        (root / "public_book_manifest.json").write_text(json.dumps(manifest) + "\n")
        return manifest


def test_bundle_binds_both_clean_child_manifests(tmp_path) -> None:
    root = tmp_path / "bundle"
    manifest = asyncio.run(
        run_bundle(
            output_dir=root,
            duration_seconds=1,
            code_commit=CODE_COMMIT,
            twap_recorder=FakeTwapRecorder(),
            wallet_observer=FakeWalletObserver(),
            book_recorder=FakeBookRecorder(),
            market_discovery=FakeMarketDiscovery(),
        )
    )
    assert manifest["chainlink"]["event_counts"] == {"btc/usd": 2, "eth/usd": 2}
    assert manifest["code_commit"] == CODE_COMMIT
    assert manifest["wallet_observer"]["prospective_rows"] == 3
    assert manifest["schema_version"] == "smartcopy-bonereaper-prospective-bundle-v4"
    assert manifest["public_book"]["event_counts"]["snapshot_records"] == 1
    assert manifest["public_book"]["initialized_at_finalize"] == {"token-up": True}
    child = root / "wallet" / "observer_manifest.json"
    assert manifest["wallet_observer"]["sha256"] == hashlib.sha256(child.read_bytes()).hexdigest()
    assert (root / "prospective_bundle_manifest.json").is_file()


def test_bundle_refuses_overwrite_before_starting_children(tmp_path) -> None:
    root = tmp_path / "bundle"
    root.mkdir()
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        asyncio.run(
            run_bundle(
                output_dir=root,
                duration_seconds=1,
                code_commit=CODE_COMMIT,
                twap_recorder=FakeTwapRecorder(),
                wallet_observer=FakeWalletObserver(),
                book_recorder=FakeBookRecorder(),
                market_discovery=FakeMarketDiscovery(),
            )
        )


def test_bundle_rejects_duration_that_requires_token_rotation(tmp_path) -> None:
    with pytest.raises(ValueError, match="must not exceed 120"):
        asyncio.run(
            run_bundle(
                output_dir=tmp_path / "bundle",
                duration_seconds=121,
                code_commit=CODE_COMMIT,
                twap_recorder=FakeTwapRecorder(),
                wallet_observer=FakeWalletObserver(),
                book_recorder=FakeBookRecorder(),
                market_discovery=FakeMarketDiscovery(),
            )
        )


def test_bundle_child_failure_does_not_write_clean_root_manifest(tmp_path) -> None:
    class FailedBookRecorder:
        async def run(self, **kwargs):
            raise RuntimeError("book failed")

    root = tmp_path / "bundle"
    with pytest.raises(RuntimeError, match="book failed"):
        asyncio.run(
            run_bundle(
                output_dir=root,
                duration_seconds=1,
                code_commit=CODE_COMMIT,
                twap_recorder=FakeTwapRecorder(),
                wallet_observer=FakeWalletObserver(),
                book_recorder=FailedBookRecorder(),
                market_discovery=FakeMarketDiscovery(),
            )
        )
    assert not (root / "prospective_bundle_manifest.json").exists()
