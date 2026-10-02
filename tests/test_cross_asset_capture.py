import asyncio
import json

import pytest

from smartcopy.cross_asset_capture import run_cross_asset_capture

SYMBOLS = (
    "btc/usd", "eth/usd", "sol/usd", "xrp/usd", "bnb/usd", "doge/usd", "hype/usd"
)


class FakeTwap:
    def __init__(self, *, missing=None, fail=False):
        self.missing = missing
        self.fail = fail

    async def run(self, *, output_dir, duration_seconds):
        output_dir.mkdir()
        if self.fail:
            raise RuntimeError("stream failed")
        manifest = {
            "event_counts": {symbol: 1 for symbol in SYMBOLS if symbol != self.missing},
            "reconnect_count": 0,
            "clean_finalize": True,
        }
        (output_dir / "chainlink_twap_manifest.json").write_text(json.dumps(manifest))
        return manifest


class FakeWallet:
    def __init__(self, *, gaps=0, mismatch=False):
        self.gaps = gaps
        self.mismatch = mismatch

    def run(self, *, output_dir, duration_seconds):
        output_dir.mkdir()
        manifest = {"emitted_prospective_row_count": 0, "gap_failures": self.gaps}
        (output_dir / "observer_manifest.json").write_text(json.dumps(manifest))
        return {**manifest, "emitted_prospective_row_count": 1} if self.mismatch else manifest


def capture(tmp_path, recorder=None, observer=None):
    return asyncio.run(
        run_cross_asset_capture(
            output_dir=tmp_path / "capture",
            duration_seconds=960,
            code_commit="a" * 40,
            twap_recorder=recorder or FakeTwap(),
            wallet_observer=observer or FakeWallet(),
        )
    )


def test_capture_binds_seven_symbols_and_zero_wallet_rows(tmp_path) -> None:
    manifest = capture(tmp_path)
    assert manifest["clean_finalize"] is True
    assert tuple(manifest["symbols"]) == SYMBOLS
    assert manifest["wallet_observer"]["prospective_rows"] == 0
    assert len(manifest["chainlink"]["sha256"]) == 64
    assert (tmp_path / "capture" / "cross_asset_capture_manifest.json").exists()


@pytest.mark.parametrize("recorder", [FakeTwap(missing="hype/usd"), FakeTwap(fail=True)])
def test_capture_fail_closed_without_root_manifest(tmp_path, recorder) -> None:
    with pytest.raises((ValueError, RuntimeError)):
        capture(tmp_path, recorder=recorder)
    assert not (tmp_path / "capture" / "cross_asset_capture_manifest.json").exists()


@pytest.mark.parametrize("observer", [FakeWallet(gaps=1), FakeWallet(mismatch=True)])
def test_wallet_gap_or_manifest_mismatch_fails_closed(tmp_path, observer) -> None:
    with pytest.raises(ValueError):
        capture(tmp_path, observer=observer)
    assert not (tmp_path / "capture" / "cross_asset_capture_manifest.json").exists()


def test_capture_rejects_short_duration_and_existing_directory(tmp_path) -> None:
    with pytest.raises(ValueError, match="duration"):
        asyncio.run(
            run_cross_asset_capture(
                output_dir=tmp_path / "short", duration_seconds=959,
                code_commit="a" * 40, twap_recorder=FakeTwap(),
                wallet_observer=FakeWallet(),
            )
        )
    capture(tmp_path)
    with pytest.raises(FileExistsError):
        capture(tmp_path)
