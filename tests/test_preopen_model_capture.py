import asyncio
import json

import pytest

from smartcopy.preopen_model_capture import run_preopen_model_capture


class FakeTwap:
    async def run(self, *, output_dir, duration_seconds):
        output_dir.mkdir()
        manifest = {
            "event_counts": {"btc/usd": 1, "eth/usd": 1},
            "reconnect_count": 0,
        }
        (output_dir / "chainlink_twap_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return manifest


class FakeWallet:
    def run(self, *, output_dir, duration_seconds):
        output_dir.mkdir()
        manifest = {"emitted_prospective_row_count": 2, "gap_failures": 0}
        (output_dir / "observer_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        return manifest


def test_capture_binds_both_child_manifests(tmp_path) -> None:
    output = tmp_path / "capture"
    manifest = asyncio.run(
        run_preopen_model_capture(
            output_dir=output,
            duration_seconds=960,
            code_commit="a" * 40,
            twap_recorder=FakeTwap(),
            wallet_observer=FakeWallet(),
        )
    )
    assert manifest["clean_finalize"] is True
    assert manifest["wallet_observer"]["prospective_rows"] == 2
    assert len(manifest["chainlink"]["sha256"]) == 64


def test_capture_rejects_short_or_reused_output(tmp_path) -> None:
    with pytest.raises(ValueError, match="duration"):
        asyncio.run(
            run_preopen_model_capture(
                output_dir=tmp_path / "short",
                duration_seconds=959,
                code_commit="a" * 40,
                twap_recorder=FakeTwap(),
                wallet_observer=FakeWallet(),
            )
        )
    existing = tmp_path / "existing"
    existing.mkdir()
    with pytest.raises(FileExistsError):
        asyncio.run(
            run_preopen_model_capture(
                output_dir=existing,
                duration_seconds=960,
                code_commit="a" * 40,
                twap_recorder=FakeTwap(),
                wallet_observer=FakeWallet(),
            )
        )
