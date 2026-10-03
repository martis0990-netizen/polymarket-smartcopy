import copy
import datetime as dt
import json
import pathlib
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from limitless_hourly_paper import HourlyPaper, fill, probability, spec

START = dt.datetime(2026, 10, 3, 13, tzinfo=dt.timezone.utc).timestamp()
MID = START + 1800


def market(**changes):
    m = {"slug": "btc-hour", "conditionId": "condition-1", "title": "BTC Up or Down Hourly",
         "tradeType": "clob", "status": "FUNDED", "startAt": START,
         "expirationTimestamp": (START + 3600) * 1000,
         "collateralToken": {"symbol": "USDC", "decimals": 6}, "tokens": {"yes": "token"},
         "metadata": {"chart": {"source": "binance", "market": "spot", "candle": "hourly",
             "symbol": "BTCUSDT", "windowOpenAt": START}, "openPrice": "100"},
         "settings": {"takerDelayMs": 500}}
    m.update(changes)
    return m


def candles(at=MID):
    first = int(at // 60 * 60) - 121 * 60
    rows = []
    for i in range(122):
        opening = (first + i * 60) * 1000
        close = 100 * (1.001 if i % 2 else .999)
        rows.append([opening, "100", "101", "99", str(close), "1", opening + 59999, "1", 1, "1", "1", "0"])
    rows[-1][4] = "100"
    return rows


def book(ask="0.40", size=100000000):
    return {"tokenId": "token", "bids": [{"price": ".38", "size": size}],
            "asks": [{"price": ask, "size": size}]}


def engine():
    p = HourlyPaper()
    p.market(market(), MID - 2)
    p.candles("BTCUSDT", "1m", candles(), MID)
    p.candles("BTCUSDT", "1h", [[int(START * 1000), "100"]], MID - 2)
    return p


class PaperTests(unittest.TestCase):
    def test_only_matching_hourly_settlement(self):
        self.assertIsNotNone(spec(market()))
        m = market(); m["metadata"]["chainlinkDataStream"] = {"streamType": "twap"}
        self.assertIsNone(spec(m))
        m = market(); m["metadata"]["chart"]["source"] = "pyth"
        self.assertIsNone(spec(m))

    def test_open_hour_boundary_is_not_creation_time(self):
        m = market(createdAt=START - 3600)
        self.assertEqual(spec(m)["start"], START)
        m["metadata"]["chart"]["windowOpenAt"] = START - 60
        self.assertIsNone(spec(m))

    def test_future_candle_cannot_change_volatility(self):
        rows = candles()
        inputs = {"price": 100, "end": START + 3600}
        original = probability(rows, inputs, "100", MID)
        rows[-1][4] = "999999999"  # current incomplete close is not a training return
        future = copy.deepcopy(rows[-1]); future[0] += 60000; future[6] += 60000
        self.assertEqual(probability(rows + [future], inputs, "100", MID), original)

    def test_missing_minute_rejected(self):
        with self.assertRaisesRegex(ValueError, "MISSING_CLOSED_WARMUP"):
            probability(candles()[1:], {"price": 100, "end": START + 3600}, "100", MID)

    def test_never_fill_on_decision_or_before_delay(self):
        p = engine(); p.book("btc-hour", book(), MID)
        a = p.state["episodes"]["condition-1"]["variants"]["model"]
        self.assertEqual(a["status"], "PENDING")
        p.book("btc-hour", book(), MID + 1)
        self.assertEqual(a["status"], "PENDING")
        p.book("btc-hour", book(), MID + 2)
        self.assertEqual(a["status"], "FILLED")

    def test_response_after_delay_does_not_make_early_request_eligible(self):
        p = engine(); p.book("btc-hour", book(), MID)
        p.book("btc-hour", book(), MID + 3, requested=MID + 1)
        self.assertEqual(p.state["episodes"]["condition-1"]["variants"]["model"]["status"], "PENDING")

    def test_invalid_next_execution_book_does_not_retry_for_better_quote(self):
        p = engine(); p.book("btc-hour", book(), MID)
        p.book("btc-hour", book(".20"), MID + 2)
        p.book("btc-hour", book(), MID + 3)
        self.assertEqual(p.state["episodes"]["condition-1"]["variants"]["model"]["reason"], "INVALID_EXECUTION_BOOK")

    def test_fee_in_contracts_and_verified_settlement(self):
        p = engine(); p.book("btc-hour", book(), MID); p.book("btc-hour", book(), MID + 2)
        ep = p.state["episodes"]["condition-1"]
        a = ep["variants"]["model"]
        self.assertEqual(Decimal(a["net_shares"]), Decimal(a["gross_shares"]) * Decimal(".97"))
        p.market(market(status="RESOLVED", winningOutcomeIndex=0), START + 3601)
        self.assertEqual(a["status"], "SETTLED")
        self.assertEqual(Decimal(a["pnl_usdc"]), Decimal(a["net_shares"]) - Decimal(a["cost_usdc"]))
        self.assertAlmostEqual(ep["brier_model"], .25)

    def test_split_payout_is_not_binary_win(self):
        p = engine(); p.book("btc-hour", book(), MID); p.book("btc-hour", book(), MID + 2)
        p.market(market(status="RESOLVED", winningOutcomeIndex=None, payoutNumerators=[70, 30]), START + 3601)
        ep = p.state["episodes"]["condition-1"]
        a = ep["variants"]["model"]
        self.assertEqual(Decimal(a["pnl_usdc"]), Decimal(a["net_shares"]) * Decimal(".7") - Decimal(a["cost_usdc"]))
        self.assertNotIn("brier_model", ep)

    def test_raw_depth_units_and_no_leg(self):
        self.assertIsNone(fill(book(size=1000000), "YES", Decimal(".5"), Decimal("2")))
        result = fill(book(), "NO", Decimal(".7"), Decimal("2"))
        self.assertEqual(Decimal(result["cost_usdc"]), Decimal("1.24"))

    def test_price_bound_failure_is_skip(self):
        p = engine(); p.book("btc-hour", book(), MID); p.book("btc-hour", book(".60"), MID + 2)
        self.assertEqual(p.state["episodes"]["condition-1"]["variants"]["model"]["status"], "SKIP")

    def test_stale_reference_and_wrong_open_do_not_predict(self):
        p = engine(); p.minute["BTCUSDT"] = (MID - 11, candles()); p.book("btc-hour", book(), MID)
        self.assertFalse(p.state["episodes"])
        p = engine(); p.hour["BTCUSDT"] = (MID, [[int(START * 1000), "101"]]); p.book("btc-hour", book(), MID)
        self.assertFalse(p.state["episodes"])

    def test_checkpoint_prevents_duplicate_condition(self):
        p = engine(); p.book("btc-hour", book(), MID)
        restored = HourlyPaper(json.loads(json.dumps(p.state)))
        restored.market(market(slug="alias"), MID + 1)
        restored.book("alias", book(), MID + 2)
        self.assertEqual(len(restored.state["episodes"]), 1)
        self.assertEqual(restored.state["episodes"]["condition-1"]["decision_at"], MID)

    def test_missed_window_and_late_execution(self):
        p = engine(); p.book("btc-hour", book(), MID + 61)
        self.assertEqual(p.state["episodes"]["condition-1"]["reason"], "MISSED_DECISION_WINDOW")
        p = engine(); p.book("btc-hour", book(), MID); p.book("btc-hour", book(), MID + 31)
        self.assertEqual(p.state["episodes"]["condition-1"]["variants"]["model"]["reason"], "EXECUTION_OBSERVATION_TOO_LATE")

    def test_crossed_book_and_wrong_token_rejected(self):
        p = engine(); p.book("btc-hour", book(".20"), MID)
        self.assertFalse(p.state["episodes"])
        b = book(); b["tokenId"] = "other"
        p.book("btc-hour", b, MID)
        self.assertFalse(p.state["episodes"])


if __name__ == "__main__":
    unittest.main()
