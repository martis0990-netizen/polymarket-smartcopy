import copy
import datetime as dt
import unittest

from limitless_market_regime import MinuteStore, aggregate, describe, milliseconds, scan


def bars(prices):
    return [{'open_ms': i*60000, 'close_ms': i*60000+59999,
             'o': p, 'h': p+.1, 'l': p-.1, 'c': p, 'available_ms': i*60000+60001}
            for i, p in enumerate(prices)]


TREND = [100, 101, 102, 103, 102, 101, 102, 104, 106, 105, 104, 103,
         104, 106, 108, 107, 106, 105, 106, 108, 110, 109, 108, 107, 106, 104, 102]
RANGE = [120, 118, 116, 115, 116, 117, 119, 118, 116, 114, 112, 110,
         112, 114, 116, 115, 113, 110.1, 112, 114, 116, 115, 113, 111, 112, 114, 117]


def envelope(received=61., requested=60., close=100.):
    iso = lambda t: dt.datetime.fromtimestamp(t, dt.timezone.utc).isoformat()
    return {'kind': 'binance_1m', 'source': 'binance', 'path': '/api/v3/klines',
            'params': {'symbol': 'BTCUSDT', 'interval': '1m'},
            'requested_at': iso(requested), 'observed_at': iso(received),
            'raw': [[0, '100', str(max(101., close)), '99', str(close), '1', 59999]]}


class MarketRegimeTests(unittest.TestCase):
    def test_every_prefix_keeps_state_pivot_and_event_history(self):
        # A later outside close must invalidate only the later state, never erase the box.
        for prices in (TREND, RANGE):
            rows = bars(prices)
            full = scan(rows)
            for n in range(1, len(rows)+1):
                prefix = scan(rows[:n])
                self.assertEqual(prefix['snapshots'], full['snapshots'][:n])
                self.assertEqual(prefix['events'], [e for e in full['events']
                                                   if e['bar_close_ms'] <= rows[n-1]['close_ms']])
                self.assertEqual(prefix['pivots'], [p for p in full['pivots']
                                                   if p['confirmed_ms'] <= rows[n-1]['close_ms']])

    def test_protected_anchor_changes_only_on_bos_not_new_local_low(self):
        old = scan(bars(TREND[:20]))
        self.assertEqual(old['state'], 'TREND_UP')
        self.assertAlmostEqual(old['protected']['price'], 102.9)
        self.assertAlmostEqual(old['swings'][-1]['price'], 104.9)
        confirmed = scan(bars(TREND[:21]))
        self.assertAlmostEqual(confirmed['protected']['price'], 104.9)
        broken = scan(bars(TREND))
        self.assertEqual(broken['state'], 'TRANSITION')
        self.assertEqual(broken['transition']['direction'], 'DOWN')
        self.assertNotEqual(broken['state'], 'TREND_DOWN')

    def test_three_points_are_candidate_fourth_reaction_confirms_range(self):
        candidate = scan(bars(RANGE[:20]))
        self.assertIsNotNone(candidate['range_candidate'])
        self.assertNotEqual(candidate['state'], 'RANGE')
        confirmed = scan(bars(RANGE[:23]))
        self.assertEqual(confirmed['state'], 'RANGE')
        self.assertAlmostEqual(confirmed['range']['low'], 109.9)
        self.assertAlmostEqual(confirmed['range']['high'], 116.1)
        broken = scan(bars(RANGE))
        self.assertEqual(broken['state'], 'TRANSITION')
        self.assertEqual(broken['transition']['from_state'], 'RANGE')
        self.assertEqual(broken['transition']['direction'], 'UP')

    def test_mirrored_structure_and_wick_do_not_reverse_protected_trend(self):
        inverse = bars([300-p for p in TREND[:21]])
        self.assertEqual(scan(inverse)['state'], 'TREND_DOWN')
        rows = bars(TREND[:21])
        rows.append({**rows[-1], 'open_ms': 21*60000, 'close_ms': 22*60000-1,
                     'o': 108, 'c': 108, 'h': 109, 'l': 100, 'available_ms': 22*60000+1})
        self.assertEqual(scan(rows)['state'], 'TREND_UP')

    def test_receipt_controls_availability_not_source_close_time(self):
        store = MinuteStore()
        store.add(envelope(received=120.), {'artifact': 1})
        self.assertEqual(store.view('BTCUSDT', 90000)[0], [])
        rows, conflicts = store.view('BTCUSDT', 120000)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['available_ms'], 120000)
        self.assertEqual(conflicts, [])

    def test_earliest_duplicate_preserved_conflict_only_after_receipt(self):
        store = MinuteStore()
        store.add(envelope(received=90.), {'artifact': 2})
        store.add(envelope(received=61.), {'artifact': 1})
        store.add(envelope(received=180., close=100.5), {'artifact': 3})
        rows, conflicts = store.view('BTCUSDT', 100000)
        self.assertEqual(rows[0]['available_ms'], 61000)
        self.assertEqual(rows[0]['provenance']['artifact'], 1)
        self.assertEqual(conflicts, [])
        self.assertEqual(store.view('BTCUSDT', 200000), ([], [0]))

    def test_partial_candle_never_admitted_even_if_received_after_close(self):
        store = MinuteStore()
        store.add(envelope(requested=30., received=90.), {'artifact': 1})
        self.assertEqual(store.view('BTCUSDT', 100000), ([], []))

    def test_complete_aligned_aggregation_gaps_and_missing_latest_are_unknown(self):
        rows = bars([100+i*.1 for i in range(120)])
        aligned = aggregate(rows, 15)
        self.assertEqual(len(aligned), 8)
        self.assertEqual(aligned[0]['close_ms'], 15*60000-1)
        self.assertEqual(aligned[0]['available_ms'], 15*60000+1)
        del rows[45]
        suffix = aggregate(rows, 15)
        self.assertEqual([x['open_ms'] for x in suffix], [i*60000 for i in (60, 75, 90, 105)])
        result = describe(rows, [], 135*60000+100)
        self.assertEqual(result['frames']['M15']['reason'], 'LATEST_COMPLETE_BAR_MISSING')
        self.assertEqual(result['frames']['H4']['state'], 'UNKNOWN')
        self.assertEqual(result['top_down_context'], 'UNKNOWN_HTF_CONTEXT')

    def test_unknown_htf_never_falls_back_to_m1_and_future_conflicts_do_not_rewrite(self):
        rows = bars(TREND)
        before = describe(rows, [], 27*60000+100)
        self.assertEqual(before['frames']['M1']['state'], 'TRANSITION')
        self.assertEqual(before['top_down_context'], 'UNKNOWN_HTF_CONTEXT')
        after = describe(rows, [0], 27*60000+100)
        self.assertTrue(all(x['state'] == 'UNKNOWN' for x in after['frames'].values()))

    def test_invalid_envelope_and_nonfinite_naive_times_rejected(self):
        for value in (float('nan'), float('inf'), True, '2026-10-04T00:00:00'):
            with self.assertRaises(ValueError):
                milliseconds(value)
        for alteration in ({'source': 'foreign'}, {'observed_at': '1970-01-01T00:00:59+00:00'},
                           {'raw': [[0, '100', '99', '101', '100', '1', 59999]]}):
            store = MinuteStore()
            row = copy.deepcopy(envelope())
            row.update(alteration)
            store.add(row, {'artifact': 1})
            self.assertEqual(store.view('BTCUSDT', 200000), ([], []))
            self.assertEqual(len(store.errors), 1)


if __name__ == '__main__':
    unittest.main()
