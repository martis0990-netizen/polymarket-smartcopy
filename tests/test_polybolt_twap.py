import asyncio
import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from smartcopy.polybolt_twap import (
    PolyBoltCaptureError, PolyBoltCredentials, PolyBoltTwapRecorder,
)

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
SYMBOLS = ("btc", "eth", "sol", "xrp", "bnb", "doge", "hype")


def stream_frames(*, missing=None, dropped=False, skipped=False, bad_value=False):
    seq = 0
    for asset in SYMBOLS:
        seq += 1
        yield {"v": 1, "channel": "price.crypto.twap", "seq": seq, "ts": 1,
               "snapshot": True, "payload": {"symbol": asset + "usd", "window_seconds": 60,
                                            "data": [{"timestamp": 1, "value": "999.9"}]}}
    for asset in SYMBOLS:
        if asset == missing:
            continue
        seq += 2 if skipped and asset == "sol" else 1
        yield {"v": 1, "channel": "price.crypto.twap", "seq": seq, "ts": 2,
               "dropped": 1 if dropped and asset == "sol" else 0,
               "payload": {"symbol": asset + "usd", "window_seconds": 60,
                           "timestamp": 2, "full_accuracy_value": "oops" if bad_value and asset == "sol" else "123.000000000000000001",
                           "value": 123.0}}


class FakeStream(PolyBoltTwapRecorder):
    def __init__(self, **kwargs):
        super().__init__(PolyBoltCredentials("key", "secret", "passphrase"))
        self.kwargs = kwargs

    async def _frames(self, deadline):
        for i in range(7):
            yield {"op": "subscribed", "channel": "price.crypto.twap"}, NOW
        for frame in stream_frames(**self.kwargs):
            yield frame, NOW


def test_seven_live_updates_and_historical_snapshots_are_separate(tmp_path):
    out = tmp_path / "stream"
    manifest = asyncio.run(FakeStream().run(output_dir=out, duration_seconds=1))
    assert manifest["feed_protocol"] == "polybolt-v1"
    assert set(manifest["event_counts"].values()) == {1}
    rows = [json.loads(line) for line in (out / "chainlink_twap_raw.jsonl").read_text().splitlines()]
    assert [r["kind"] for r in rows].count("snapshot") == 7
    assert [r["kind"] for r in rows].count("live") == 7
    assert rows[9]["normalized"]["value"] == "123.000000000000000001"
    assert rows[9]["normalized"]["symbol"] == "sol/usd"


@pytest.mark.parametrize("fault", [
    {"missing": "hype"}, {"dropped": True}, {"skipped": True}, {"bad_value": True},
])
def test_missing_and_corrupt_frames_leave_no_clean_manifest(tmp_path, fault):
    out = tmp_path / "stream"
    with pytest.raises(PolyBoltCaptureError):
        asyncio.run(FakeStream(**fault).run(output_dir=out, duration_seconds=1))
    assert not (out / "chainlink_twap_manifest.json").exists()


def test_auth_and_subscription_do_not_persist_secrets(monkeypatch, tmp_path):
    class Socket:
        def __init__(self):
            self.sent = []
            self.frames = iter([{"op": "authed", "rid": "auth-v5"},
                                *([{"op": "subscribed", "channel": "price.crypto.twap"}] * 7),
                                *stream_frames()])

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send(self, value):
            self.sent.append(json.loads(value))

        async def recv(self):
            try:
                return json.dumps(next(self.frames))
            except StopIteration:
                await asyncio.sleep(1)

    socket = Socket()
    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=lambda *a, **kw: socket))
    recorder = PolyBoltTwapRecorder(PolyBoltCredentials("key-test", "secret-test", "passphrase-test"))
    out = tmp_path / "stream"
    asyncio.run(recorder.run(output_dir=out, duration_seconds=0.1))
    assert socket.sent[0]["auth"] == {"apiKey": "key-test", "secret": "secret-test", "passphrase": "passphrase-test"}
    assert {entry["filter"]["symbol"] for entry in socket.sent[1]["subscriptions"]} == {asset + "usd" for asset in SYMBOLS}
    assert all(entry["filter"]["window_seconds"] == 60 for entry in socket.sent[1]["subscriptions"])
    for path in out.iterdir():
        content = path.read_text()
        assert "secret-test" not in content and "passphrase-test" not in content and "key-test" not in content


def test_missing_credentials_rejected_without_logging(monkeypatch):
    for name in ("POLYMARKET_CLOB_API_KEY", "POLYMARKET_CLOB_API_SECRET", "POLYMARKET_CLOB_API_PASSPHRASE"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(PolyBoltCaptureError, match="set POLYMARKET_CLOB_API_KEY"):
        PolyBoltCredentials.from_env()


@pytest.mark.parametrize("reply", [{"op": "error", "code": "auth_invalid"},
                                     {"op": "authed", "rid": "auth-v5"}])
def test_auth_error_or_premature_disconnect_never_finalizes(monkeypatch, tmp_path, reply):
    class Socket:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def send(self, value):
            pass

        def __init__(self):
            self.first = True

        async def recv(self):
            if self.first:
                self.first = False
                return json.dumps(reply)
            raise ConnectionError("stream closed")

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=lambda *a, **kw: Socket()))
    recorder = PolyBoltTwapRecorder(PolyBoltCredentials("key", "secret", "passphrase"))
    out = tmp_path / "capture"
    with pytest.raises((PolyBoltCaptureError, ConnectionError)):
        asyncio.run(recorder.run(output_dir=out, duration_seconds=1))
    assert not (out / "chainlink_twap_manifest.json").exists()
