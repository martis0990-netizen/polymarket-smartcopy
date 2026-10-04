"""Economic and causality regressions for the offline 15m paper replay."""
import datetime as dt
import gzip
import hashlib
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile
from decimal import Decimal
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from limitless_15m_replay import (_first, _first_received, candidate, load_archives,
                                  market_spec, oracle_probability, prepare, replay,
                                  settle_accounts)

START = dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc).timestamp()


def market():
    return {
        "title": "BTC Up or Down - 15 Min", "slug": "btc-15-min-test",
        "conditionId": "c", "startAt": START, "expirationTimestamp": (START+900)*1000,
        "tradeType": "clob", "marketType": "single", "groupId": None,
        "collateralToken": {"symbol": "USDC", "decimals": 6,
                            "address": "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"},
        "tokens": {"yes": "y", "no": "n"}, "settings": {"takerDelayMs": 500},
        "description": ('Chainlink BTC/USD 60-second TWAP on October 5, 2026, at 00:15 UTC '
                        'is greater than or equal to the Price to Beat captured from the same TWAP '
                        'on October 5, 2026, at 00:00 UTC. Otherwise, this market will resolve to "Down". '
                        'Chainlink BTC/USD 60-second TWAP is used for both the Price to Beat and resolution. '
                        'The report at the exact resolution time is used first. If it is unavailable, '
                        'the first Chainlink observation within the following 5 seconds will be used. '
                        'If no report exists in that window, the market will not resolve automatically. '
                        'Price to Beat captured from the Chainlink BTC/USD 60-second TWAP '
                        'on October 5, 2026, at 00:00 UTC was $100.'),
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
        raw = market()
        raw["description"] = raw["description"].replace("October 5, 2026", "January 1, 2010")
        self.assertIsNone(market_spec(raw))

    def test_first_failed_request_consumes_attempt(self):
        failed = {"kind": "request_error", "requested_at": START+451,
                  "observed_at": START+452}
        later = {"kind": "book", "requested_at": START+453,
                 "observed_at": START+454}
        self.assertIs(_first([later, failed], START+450, START+510), failed)

    def test_decision_book_uses_first_completed_attempt_inside_window(self):
        late = {"requested_at": START+480, "observed_at": START+520}
        in_window = {"requested_at": START+481, "observed_at": START+500}
        self.assertIs(_first_received([late, in_window], START+480, START+510), in_window)
        self.assertIsNone(_first([late, in_window], START+480, START+510))

    def test_malformed_observed_market_is_in_coverage_denominator(self):
        row = {"kind": "market", "slug": "btc-up-or-down-15-min-1791158400",
               "raw": {"title": "bad"}, "_proof": {"artifact": 1, "line": 1}}
        episodes, _, unverified = prepare([row])
        self.assertEqual(episodes, [])
        self.assertEqual([r["slug"] for r in unverified], [row["slug"]])

    def test_cumulative_checkpoint_lineage_rejects_missing_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = []
            for index, episodes in enumerate(({"c": {"condition": "c"}}, {})):
                state = {"paper": {"version": "v", "markets": {}, "episodes": episodes},
                         "inventory_paper": {"version": "v", "started_at": 1,
                                             "entry_attempts": {}},
                         "inventory_paper_history": {}}
                summary = {"status": "CAPTURE_ONLY_NO_PNL",
                           "started_at": START+index*60,
                           "ended_at": START+index*60+50}
                path = pathlib.Path(directory)/f"{index}.zip"
                with zipfile.ZipFile(path, "w") as archive:
                    archive.writestr("state.json", json.dumps(state))
                    archive.writestr("summary.json", json.dumps(summary))
                    archive.writestr("capture.jsonl.gz", gzip.compress(b""))
                run_id = index+1
                sha = "sha"
                entries.append({"run": {"id": run_id, "head_branch": "main",
                                        "event": "workflow_dispatch", "status": "completed",
                                        "conclusion": "success",
                                        "name": "Limitless independent market capture",
                                        "head_sha": sha},
                                "artifact": {"id": run_id, "digest": "sha256:" +
                                             hashlib.sha256(path.read_bytes()).hexdigest(),
                                             "workflow_run": {"id": run_id, "head_sha": sha}},
                                "file": {"path": str(path)}})
            with self.assertRaisesRegex(ValueError, "CHECKPOINT_LINEAGE_BROKEN"):
                load_archives(entries)

    def test_unseen_quarter_hour_assets_remain_in_coverage_denominator(self):
        episode = {"condition": "c", "slug": "btc-15-min-test", "symbol": "BTCUSDT",
                   "phase": "discovery", "start": START, "status": "SKIP",
                   "reason": "MISSED_ORACLE_WINDOW"}
        sources = [{"started_at": START-60, "ended_at": START+1800}]
        with (patch("limitless_15m_replay.START", START),
              patch("limitless_15m_replay.HOLDOUT", START+900),
              patch("limitless_15m_replay.CUTOFF", START+1800),
              patch("limitless_15m_replay.load_archives", return_value=([], sources)),
              patch("limitless_15m_replay.prepare", return_value=([episode], {}, []))):
            report = replay([])
        phase = report["phases"]["discovery"]
        self.assertEqual(phase["expected_conditions"], 2)
        self.assertEqual(phase["unobserved_expected_conditions"], 1)
        self.assertEqual(phase["observation_coverage"], 0)
        self.assertEqual(phase["review_status"], "INSUFFICIENT_DATA")

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
