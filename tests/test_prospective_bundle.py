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


def test_bundle_binds_both_clean_child_manifests(tmp_path) -> None:
    root = tmp_path / "bundle"
    manifest = asyncio.run(
        run_bundle(
            output_dir=root,
            duration_seconds=1,
            code_commit=CODE_COMMIT,
            twap_recorder=FakeTwapRecorder(),
            wallet_observer=FakeWalletObserver(),
        )
    )
    assert manifest["chainlink"]["event_counts"] == {"btc/usd": 2, "eth/usd": 2}
    assert manifest["code_commit"] == CODE_COMMIT
    assert manifest["wallet_observer"]["prospective_rows"] == 3
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
            )
        )
