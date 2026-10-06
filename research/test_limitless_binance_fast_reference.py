"""Causality and failure-isolation checks for the public 1s reference."""
import asyncio
import gzip
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from limitless_binance_fast_reference import capture, decode, record
from limitless_market_capture import capture as market_capture


def frame(symbol="BTCUSDT", start=1_790_000_000_000, close="100.0"):
    stream = symbol.lower() + "@kline_1s"
    return {"stream": stream, "data": {"e": "kline", "E": start + 500,
        "s": symbol, "k": {"t": start, "T": start + 999, "s": symbol,
                            "i": "1s", "c": close, "x": False}}}


class Sink:
    capped = False
    def __init__(self):
        self.rows = []
    def write(self, kind, **fields):
        self.rows.append((kind, fields))


class FastReferenceTests(unittest.TestCase):
    def test_wrong_stream_symbol_interval_and_nonfinite_price_never_enter_reference(self):
        for change in (lambda x: x.update(stream="ethusdt@kline_1s"),
                       lambda x: x["data"]["k"].update(i="1m"),
                       lambda x: x["data"]["k"].update(c="NaN"),
                       lambda x: x["data"]["k"].update(T=x["data"]["k"]["t"]+9999)):
            x = frame(); change(x)
            sink = Sink()
            self.assertIsNone(decode(x))
            self.assertFalse(record(sink, x, {}))
            self.assertFalse(any(kind == "binance_fast_reference" for kind, _ in sink.rows))

    def test_gaps_and_out_of_order_are_explicit_and_symbol_scoped(self):
        sink, previous = Sink(), {}
        self.assertTrue(record(sink, frame(), previous))
        self.assertTrue(record(sink, frame("ETHUSDT"), previous))
        self.assertTrue(record(sink, frame(start=1_790_000_003_000), previous))
        self.assertFalse(record(sink, frame(start=1_790_000_001_000), previous))
        self.assertEqual(previous["BTCUSDT"], 1_790_000_003_000)
        gaps = [fields for kind, fields in sink.rows if kind == "binance_fast_gap"]
        self.assertEqual(gaps, [{"symbol": "BTCUSDT", "from_open_ms": 1_790_000_000_000,
                                 "to_open_ms": 1_790_000_003_000, "unobserved_seconds": 2}])
        self.assertEqual(sum(kind == "binance_fast_reference" for kind, _ in sink.rows), 3)

    def test_stream_error_is_recorded_without_failing_capture(self):
        class FailingSession:
            def __init__(self, **kwargs): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            def ws_connect(self, *args, **kwargs): raise ConnectionError("offline")
        ticks = iter([0, 11])
        sink = Sink()
        fake = types.SimpleNamespace(ClientSession=FailingSession,
                                     ClientTimeout=lambda **kwargs: object())
        with patch.dict("sys.modules", {"aiohttp": fake}), \
             patch("limitless_binance_fast_reference.time",
                   types.SimpleNamespace(monotonic=lambda: next(ticks, 20))):
            asyncio.run(capture(sink, 10))
        self.assertTrue(any(kind == "binance_fast_error" for kind, _ in sink.rows))

    def test_optional_stream_stays_in_capture_journal_without_paper_state(self):
        class Socket:
            connected = False
            def __init__(self, **kwargs): pass
            def on(self, *args, **kwargs): return lambda fn: fn
            async def connect(self, *args, **kwargs): self.connected = True
            async def disconnect(self): self.connected = False
            async def emit(self, *args, **kwargs): pass

        async def stream(recorder, end):
            recorder.write("binance_fast_reference", stream="btcusdt@kline_1s",
                           raw=frame()["data"])
            await asyncio.Event().wait()

        with tempfile.TemporaryDirectory() as tmp:
            args = types.SimpleNamespace(out=tmp, state=None, minutes=.002,
                until="2026-10-10T09:00:00Z", fast_reference=True)
            with patch.dict(sys.modules, {"socketio": types.SimpleNamespace(AsyncClient=Socket)}), \
                 patch("limitless_market_capture.request", return_value={"data": [], "totalMarketsCount": 0}), \
                 patch("limitless_market_capture.capture_fast_reference", stream), \
                 patch("builtins.print"):
                loop = asyncio.new_event_loop()
                try:
                    loop.run_until_complete(market_capture(args))
                    self.assertFalse(asyncio.all_tasks(loop))
                finally:
                    loop.close()
            with gzip.open(pathlib.Path(tmp) / "capture.jsonl.gz", "rt") as fp:
                kinds = [json.loads(line)["kind"] for line in fp]
            state = json.loads((pathlib.Path(tmp) / "state.json").read_text())
            self.assertIn("binance_fast_reference", kinds)
            self.assertEqual(state["paper"]["episodes"], {})
            self.assertEqual(state["inventory_paper"]["positions"], {})


if __name__ == "__main__":
    unittest.main()
