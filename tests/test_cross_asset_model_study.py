"""High-value v5 boundaries, runnable with pytest or stdlib unittest."""

import unittest
from datetime import datetime, timedelta, timezone

from smartcopy.cross_asset_model import build_v5_model_rows
from smartcopy.cross_asset_study import summarize_v5_study
from smartcopy.external_signal import BinanceKline


def bar(second, interval="1s", duration=1, price=100.0):
    return BinanceKline("BTCUSDT", interval, second * 1000,
        (second + duration) * 1000 - 1, price, price + 1, price - 1,
        price, 1, 100, 1, 0.5, 50)


class V5ModelStudyTest(unittest.TestCase):
    def setUp(self):
        self.start = 1_800_000_000
        self.t = self.start - 10
        self.symbol = "btc/usd"
        self.candidate = {"condition_id": "0x123", "slug": f"btc-updown-5m-{self.start}",
            "asset": "BTC", "horizon": "5m", "market_start": self.start,
            "cohort": "CORE", "capture_warmup_satisfied": True}
        self.episodes = {"0x123": ({"role": "TAKER", "source_second": self.t,
            "outcome": "Up", "source_notional": 1.0},)}
        self.one = tuple(bar(s, price=100 + (s - self.t) * .001)
                         for s in range(self.t - 601, self.t))
        latest = (self.t // 300) * 300 - 300
        self.htf = tuple(bar(latest - i * 300, "5m", 300, 100 + i * .001)
                         for i in range(100))
        self.base = dict(candidates=(self.candidate,), episodes=self.episodes,
            binance={("BTCUSDT", "1s"): self.one, ("BTCUSDT", "5m"): self.htf},
            capture_started_ms=(self.start - 700) * 1000,
            capture_ended_ms=(self.start + 1) * 1000,
            first_live_receive_ms={self.symbol: (self.start - 700) * 1000},
            wallet_baseline_finished_ms=(self.start - 700) * 1000)

    def chain(self, receive):
        return {self.symbol: ({"source_timestamp_ms": (self.t - 700) * 1000,
            "receive_timestamp_ms": receive * 1000, "value_decimal": 100.0},)}

    def test_strict_prior_receive_time_blocks_future_oracle(self):
        rows = build_v5_model_rows(**self.base, chainlink=self.chain(self.t))
        self.assertFalse(rows[0]["eligible"])
        self.assertIn("INCOMPLETE_STRICT_PRIOR_CHAINLINK", rows[0]["exclusion_reasons"])

    def test_gap_in_one_second_history_excludes_condition(self):
        inputs = dict(self.base)
        inputs["binance"] = dict(inputs["binance"])
        inputs["binance"][("BTCUSDT", "1s")] = self.one[1:]
        rows = build_v5_model_rows(**inputs, chainlink=self.chain(self.t - 1))
        self.assertFalse(rows[0]["eligible"])
        self.assertIn("INCOMPLETE_NATIVE_BINANCE_HISTORY", rows[0]["exclusion_reasons"])

    def test_candidate_label_and_features(self):
        rows = build_v5_model_rows(**self.base, chainlink=self.chain(self.t - 1))
        self.assertTrue(rows[0]["eligible"])
        self.assertEqual(rows[0]["MOM15"], "Up")
        self.assertEqual(rows[0]["primary_preopen_taker"]["episode_count"], 1)

    def test_stop_and_no_early_verdict(self):
        first = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
        sample = {"eligible": True, "cohort": "CORE", "asset": "BTC", "label": "Up",
                  "MOM15": "Up", "condition_id": "abc", "market_start": int(first.timestamp())}
        interim = summarize_v5_study([sample], as_of=first + timedelta(hours=1))
        self.assertEqual(interim["study_status"], "COLLECTING")
        self.assertEqual(interim["candidates"]["MOM15"]["verdict"], "DEFERRED_UNTIL_STOPPING_RULE")
        self.assertEqual(interim["pairwise_disagreements"]["MOM15__vs__BOS_HTF_2"]["verdict"],
                         "DEFERRED_UNTIL_STOPPING_RULE")
        end = summarize_v5_study([sample], as_of=datetime(2026, 9, 28, tzinfo=timezone.utc))
        self.assertEqual(end["study_status"], "UNDERPOWERED")
        self.assertEqual(end["per_asset"]["BTC"]["candidates"]["MOM15"]["verdict"],
                         "INSUFFICIENT_ASSET_CONDITIONS")

    def test_cap_is_first_sixty_independent_conditions(self):
        first = datetime(2026, 10, 1, 12, tzinfo=timezone.utc)
        base = {"eligible": True, "cohort": "CORE", "asset": "BTC", "label": "Up", "MOM15": "Up"}
        values = [{**base, "condition_id": str(i), "market_start": int(first.timestamp()) + i}
                  for i in range(61)]
        summary = summarize_v5_study(values, as_of=first + timedelta(minutes=2))
        self.assertEqual(summary["study_status"], "STOPPING_RULE_REACHED")
        self.assertEqual(summary["eligible_conditions"], 60)
        self.assertEqual(summary["duplicate_or_late_conditions_excluded"], 1)


if __name__ == "__main__":
    unittest.main()
