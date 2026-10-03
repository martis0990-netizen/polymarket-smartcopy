import unittest
import json
import pathlib
import tempfile
from limitless_entry_availability import depth_quote, report_directory
from limitless_smartcopy_probe import DEFAULT_ACCOUNTS


def book():
    return {'tokenId': 'yes', 'bids': [{'price': .4, 'size': 100000000}],
            'asks': [{'price': .5, 'size': 10000000}, {'price': .6, 'size': 100000000}]}


class AvailabilityTests(unittest.TestCase):
    def test_walks_depth_in_raw_units_and_fees(self):
        r = depth_quote(book(), 'YES', '.5')
        self.assertEqual(r['status'], 'DEPTH_SUPPORTS_10_USDC_QUOTE')
        self.assertEqual(r['levels_used'], 2)
        self.assertFalse(r['ten_usdc_available_at_or_below_source'])
        self.assertGreater(float(r['vwap_minus_source_price']), 0)
        self.assertGreater(float(r['effective_cost_per_net_share_3pct']), float(r['vwap']))
        self.assertLessEqual(float(r['spent_in_quote_usdc']), 10)

    def test_no_asks_come_from_yes_bids(self):
        r = depth_quote(book(), 'NO', '.6')
        self.assertEqual(r['best_ask'], '0.6')
        self.assertTrue(r['ten_usdc_available_at_or_below_source'])

    def test_insufficient_depth_not_assumed_fill(self):
        b = book(); b['asks'] = [{'price': .5, 'size': 1000000}]
        r = depth_quote(b, 'YES', '.5')
        self.assertEqual(r['status'], 'INSUFFICIENT_VISIBLE_DEPTH')
        self.assertEqual(r['spent_in_quote_usdc'], '0.5')

    def test_unknown_price_not_zero_edge(self):
        r = depth_quote(book(), 'YES', None)
        self.assertIsNone(r['vwap_minus_source_price'])
        self.assertIsNone(r['ten_usdc_available_at_or_below_source'])

    def test_invalid_books_and_unknown_side(self):
        self.assertEqual(depth_quote(book(), None, '.5')['status'], 'UNKNOWN_OUTCOME')
        for price, size in ((.3,100), (float('nan'),100), (.5,-1), (.5,1.5)):
            b = book(); b['asks'] = [{'price': price, 'size': size}]
            self.assertEqual(depth_quote(b, 'YES', '.5')['status'], 'INVALID_OR_UNVERIFIED_BOOK')

    def report(self, books, unknown=False, duplicate=False):
        uid = '01046332-dc4d-428c-bcf8-deeef19dd43d'
        row = {'kind': 'observation', 'id': 'feed', 'account': DEFAULT_ACCOUNTS[0],
               'first_seen_at': '2026-10-03T09:01:10Z', 'occurred_at': '2026-10-03T09:01:00Z',
               'crypto_candidate': True, 'slug': 's',
               'raw': {'id': 'clob:' + uid + ':123', 'profile': {'id': 123}, 'entryType': 'BOUGHT',
                       'subject': {'title': 'BTC Up or Down Hourly'},
                       'facts': {'price': '.5', 'outcome': None if unknown else 'YES'}}}
        rows = [row]
        if duplicate:
            rows.append({**row, 'id': 'history', 'first_seen_at': '2026-10-03T09:01:15Z',
                         'raw': {'tradeEventId': uid, 'strategy': 'Limit Buy', 'outcomeIndex': 0,
                                 'outcomeTokenAmounts': ['1','1'], 'outcomeTokenPrice': '.5',
                                 'market': {'title': 'BTC Up or Down Hourly'}}})
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)
            (path/'summary.json').write_text(json.dumps({'started_at': '2026-10-03T09:00:00Z'}))
            (path/'observations.jsonl').write_text('\n'.join(map(json.dumps, rows)))
            (path/'books.jsonl').write_text('\n'.join(map(json.dumps, books)))
            return report_directory(path)

    def test_first_failure_not_replaced_by_later_good_book_and_dedup(self):
        rows = [{'event_id': 'feed', 'fetched_at': '2026-10-03T09:01:11Z', 'error': 'timeout'},
                {'event_id': 'history', 'request_started_at': '2026-10-03T09:01:16Z',
                 'fetched_at': '2026-10-03T09:01:17Z', 'raw': book()}]
        r = self.report(rows, duplicate=True)
        self.assertEqual(len(r['records']), 1)
        self.assertEqual(r['records'][0]['status'], 'FIRST_BOOK_REQUEST_FAILED')
        self.assertEqual(r['records'][0]['detection_delay_s'], 10)

    def test_request_must_start_after_detection(self):
        r = self.report([{'event_id': 'feed', 'request_started_at': '2026-10-03T09:01:09Z',
                          'fetched_at': '2026-10-03T09:01:11Z', 'raw': book()}])
        self.assertEqual(r['records'][0]['status'], 'UNVERIFIED_POST_DETECTION_REQUEST')

    def test_missing_and_unknown_not_reported_as_entries(self):
        self.assertEqual(self.report([])['records'][0]['status'], 'NO_BOOK_CAPTURED')
        self.assertEqual(self.report([], unknown=True)['records'][0]['status'], 'UNKNOWN_OUTCOME')

    def test_valid_book_timings_and_cohort_denominator(self):
        r = self.report([{'event_id': 'feed', 'request_started_at': '2026-10-03T09:01:11Z',
                          'fetched_at': '2026-10-03T09:01:12Z', 'raw': book()}])
        self.assertEqual(r['records'][0]['book_http_latency_s'], 1)
        self.assertEqual(r['scopes']['FIXED_COHORT']['ten_usdc_depth_quote_fraction'], 1)
        self.assertIsNone(r['scopes']['DISCOVERY_FEED']['ten_usdc_depth_quote_fraction'])


if __name__ == '__main__':
    unittest.main()
