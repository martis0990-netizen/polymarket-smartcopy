"""Economic and causality regressions for the offline 15m paper replay."""
import datetime as dt
import pathlib
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from limitless_15m_replay import (_first, candidate, market_spec,
                                  oracle_probability, settle_accounts)

START = dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc).timestamp()


def market():
    return {
        "title": "BTC Up or Down - 15 Min", "slug": "btc-15-min-test",
        "conditionId": "c", "startAt": START, "expirationTimestamp": (START+900)*1000,
        "tradeType": "clob", "marketType": "single", "groupId": None,
        "collateralToken": {"symbol": "USDC", "decimals": 6,
                            "address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"},
        "tokens": {"yes": "y", "no": "n"}, "settings": {"takerDelayMs": 500},
        "description": "Chainlink BTC/USD 60-second TWAP greater than or equal to the Price to Beat",
        "metadata": {"openPrice": "100", "openPriceCapturedAt": START, "chainlinkDataStream": {
            "pair": "BTC/USD", "enabled": True, "streamType": "twap",
            "twapWindowSeconds": 60, "priceDecimals": 18, "feedId": "f"}},
    }


def book():
    return {"tokenId": "y", "asks": [{"price": ".4", "size": 100000000}],
            "bids": [{"price": ".35", "size": 100000000}]}


class ReplayTests(unittest.TestCase):
    def test_strict_market_feed_and_15m_identity(self):
        self.assertIsNotNone(market_spec(market()))
        raw = market()
        raw["metadata"]["chainlinkDataStream"]["twapWindowSeconds"] = 30
        self.assertIsNone(market_spec(raw))
        raw = market()
        raw["tokens"]["no"] = "y"
        self.assertIsNone(market_spec(raw))

    def test_first_failed_request_consumes_attempt(self):
        failed = {"kind": "request_error", "requested_at": START+451,
                  "observed_at": START+452}
        later = {"kind": "book", "requested_at": START+453,
                 "observed_at": START+454}
        self.assertIs(_first([later, failed], START+450, START+510), failed)

    def test_oracle_uses_only_contiguous_closed_candles(self):
        spec = market_spec(market())
        first = START+420-121*60
        rows = [{"timestamp": first+i*60,
                 "close": (100 + (i % 2)*.01)*1e18} for i in range(121)]
        source = {"slug": spec["slug"], "source": "limitless",
                  "path": "/markets/" + spec["slug"] + "/oracle-candles",
                  "requested_at": START+481,
                  "observed_at": START+482, "raw": {
                      "source": "chainlink", "symbol": "BTCUSD",
                      "interval": "1m", "rows": rows}}
        p, sigma, end = oracle_probability(source, spec)
        self.assertTrue(0 <= p <= 1)
        self.assertGreater(sigma, 0)
        self.assertLessEqual(end, START+481)
        source["raw"]["rows"] = rows + [dict(rows[-1])]
        with self.assertRaisesRegex(ValueError, "INVALID_ORACLE_CANDLE"):
            oracle_probability(source, spec)

    def test_accounts_settle_independently_and_reconcile(self):
        quote = candidate(book(), .8)
        self.assertEqual(quote["side"], "YES")
        ep = {"status": "DECIDED", "condition": "c", "phase": "discovery",
              "decision_at": START+480, "execution_at": START+483,
              "opportunities": {"model": quote, "constant50": None,
                                "structure": None},
              "structure_gate": "SKIP_H1_UNKNOWN", "execution_reason": None,
              "_execution_book": book(), "accounts": {},
              "settlement": {"at": START+901, "payouts": ["1", "0"]}}
        accounts = settle_accounts([ep])
        self.assertEqual(accounts["model"]["settled"], 1)
        self.assertGreater(Decimal(accounts["model"]["settled_pnl_usdc"]), 0)
        self.assertEqual(accounts["structure"]["cash_usdc"], "100")
        self.assertEqual(ep["accounts"]["structure"]["reason"], "SKIP_H1_UNKNOWN")


if __name__ == "__main__":
    unittest.main()
