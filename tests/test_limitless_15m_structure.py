import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))
from limitless_15m_structure import coverage, label_decision, structural_gate
from limitless_market_regime import MinuteStore


class RecordingStore:
    def __init__(self):
        self.calls = []

    def view(self, symbol, at_ms):
        self.calls.append((symbol, at_ms))
        return [], []


class TestFifteenMinuteStructure(unittest.TestCase):
    def test_unknown_is_retained_and_decision_time_is_used(self):
        store = RecordingStore()
        row = label_decision(store, condition="a", symbol="BTCUSDT",
                             open_ms=0, decision_ms=480_000)
        self.assertEqual(store.calls, [("BTCUSDT", 480_000)])
        self.assertEqual(row["h1_state"], "UNKNOWN")
        self.assertFalse(row["ready_h1"])
        self.assertEqual(coverage([row])["status"], "INSUFFICIENT_DATA")
        self.assertEqual(coverage([row])["h1_unknown_reasons"],
                         {row["h1_reason"]: 1})

    def test_market_identity_and_time_are_rejected(self):
        for kwargs in (
            {"condition": "", "symbol": "BTCUSDT", "open_ms": 0, "decision_ms": 1},
            {"condition": "a", "symbol": "SOLUSDT", "open_ms": 0, "decision_ms": 1},
            {"condition": "a", "symbol": "BTCUSDT", "open_ms": 1, "decision_ms": 2},
            {"condition": "a", "symbol": "BTCUSDT", "open_ms": 0, "decision_ms": 900_000},
            {"condition": "a", "symbol": "BTCUSDT", "open_ms": 0, "decision_ms": float("nan")},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                label_decision(RecordingStore(), **kwargs)

    def test_two_assets_share_one_quarter_hour_cluster(self):
        store = RecordingStore()
        a = label_decision(store, condition="a", symbol="BTCUSDT",
                           open_ms=0, decision_ms=480_000)
        b = label_decision(store, condition="b", symbol="ETHUSDT",
                           open_ms=0, decision_ms=480_000)
        self.assertEqual(coverage([a, b])["quarter_hour_clusters"], 1)
        with self.assertRaises(ValueError):
            coverage([a, a])

    def test_later_backfill_cannot_change_earlier_label(self):
        store = MinuteStore()
        before = label_decision(store, condition="a", symbol="BTCUSDT",
                                open_ms=900_000, decision_ms=1_380_000)
        store.add({
            "kind": "binance_1m", "source": "binance", "path": "/api/v3/klines",
            "params": {"symbol": "BTCUSDT", "interval": "1m"},
            "requested_at": 1_440, "observed_at": 1_441,
            "raw": [[1_200_000, "100", "101", "99", "100", "1",
                     1_259_999]],
        }, {"artifact": 1, "line": 1})
        after = label_decision(store, condition="a", symbol="BTCUSDT",
                               open_ms=900_000, decision_ms=1_380_000)
        self.assertEqual(before, after)

    def test_gate_uses_last_observed_m5_break_and_skips_unknown(self):
        row = label_decision(RecordingStore(), condition="a", symbol="BTCUSDT",
                             open_ms=0, decision_ms=480_000)
        self.assertEqual(structural_gate(row, "YES"), "SKIP_H1_UNKNOWN")
        row["h1_state"] = "TREND_UP"
        row["m5_state"] = "TREND_UP"
        row["frames"]["M5"]["recent_events"] = [
            {"kind": "SWING_CLOSE_BREAK", "direction": "UP",
             "available_ms": 450_000, "bar_close_ms": 449_999}]
        self.assertEqual(structural_gate(row, "YES"), "ALLOW")
        self.assertEqual(structural_gate(row, "NO"), "SKIP_H1_NOT_ALIGNED")
        row["frames"]["M5"]["recent_events"].append(
            {"kind": "SWING_CLOSE_BREAK", "direction": "DOWN",
             "available_ms": 470_000, "bar_close_ms": 469_999})
        self.assertEqual(structural_gate(row, "YES"), "SKIP_M5_BREAK_OPPOSED")
        row["frames"]["M5"]["recent_events"][-1]["available_ms"] = 490_000
        with self.assertRaises(ValueError):
            structural_gate(row, "YES")


if __name__ == "__main__":
    unittest.main()
