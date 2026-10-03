import unittest
import json
import pathlib
import tempfile
import zipfile
from limitless_smartcopy_probe import metadata, identity, book_prices
from limitless_wallet_profile import profile
from limitless_probe_audit import audit, WATCHLIST


def trade(uid, index, order='o', operation='Limit Buy'):
    return {'tradeEventId': uid, 'orderId': order, 'strategy': operation, 'outcomeIndex': index,
            'outcomeTokenAmounts': ['1', '1'], 'outcomeTokenPrice': 0,
            'market': {'title': 'BTC Up or Down Hourly', 'conditionId': 'c'}}


class ProfileTests(unittest.TestCase):
    def test_index_and_zero_price(self):
        self.assertEqual(metadata(trade('a', 0))['outcome'], 'YES')
        self.assertEqual(metadata(trade('a', 1))['outcome'], 'NO')
        self.assertEqual(metadata(trade('a', 0))['source_price'], 0)

    def test_ambiguous_group_claim_bad_index_not_mapped(self):
        for index in (2, True, '1'):
            self.assertIsNone(metadata(trade('a', index))['outcome'])
        row = trade('a', 0, operation='Claim')
        self.assertIsNone(metadata(row)['outcome'])
        row = trade('a', 0)
        row['market']['group'] = {'id': 'g'}
        self.assertIsNone(metadata(row)['outcome'])
        row = trade('a', 0)
        row['market']['title'] = 'Custom sports outcome'
        self.assertIsNone(metadata(row)['outcome'])

    def test_label_conflict_and_down(self):
        row = trade('a', 0)
        row['outcome'] = 'Down'
        self.assertIsNone(metadata(row)['outcome'])
        self.assertEqual(metadata(row)['outcome_basis'], 'CONFLICT')
        self.assertEqual(metadata({'entryType': 'BOUGHT', 'subject': {'title': 'ETH Up or Down Hourly'},
                                   'facts': {'outcome': 'Down'}})['outcome'], 'NO')

    def test_order_groups_both_side_claim_not_win(self):
        rows = [trade('a', 0), trade('b', 0), trade('c', 1, order='other'), trade('d', 0, operation='Claim')]
        r = profile(rows + rows)
        self.assertEqual(r['unique_events'], 4)
        self.assertEqual(r['order_side_groups'], 2)
        self.assertEqual(r['buy_conditions_with_both_outcomes'], 1)
        self.assertEqual(r['maker_buy_events'], 3)
        self.assertEqual(r['buy_events'], 3)
        self.assertIsNone(r['independent_intents'])
        self.assertIsNone(r['copy_pnl'])

    def test_book_rejects_crossed_nonfinite_out_of_range(self):
        for bid, ask in ((.6, .5), (.5, .5), (float('nan'), .5), (-.1, .5), (.5, 1.1)):
            with self.assertRaises(ValueError):
                book_prices({'bids': [{'price': bid}], 'asks': [{'price': ask}]})

    def test_identity_not_changed_by_resolution(self):
        a = trade('a', 0)
        b = trade('a', 0)
        b['market']['status'] = 'RESOLVED'
        self.assertEqual(identity(a), identity(b))

    def test_archive_decode_uses_earliest_post_observation_book(self):
        account = sorted(WATCHLIST)[0]
        raw = trade('a', 1)
        row = {'kind': 'observation', 'id': 'a', 'account': account, 'source': 'history',
               'first_seen_at': '2026-10-03T09:01:10Z', 'occurred_at': '2026-10-03T09:01:00Z',
               'visible_delay_s': 10, 'entry_type': 'Limit Buy', 'crypto_candidate': True,
               'slug': 's', 'outcome': None, 'raw': raw}
        books = [{'event_id': 'a', 'fetched_at': at, 'top': {'no_ask': .6},
                  'observed_ask_minus_source_price': gap} for at, gap in
                 [('2026-10-03T09:01:20Z', .2), ('2026-10-03T09:01:12Z', .1),
                  ('2026-10-03T09:01:05Z', -.1)]]
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / 'segment.zip'
            with zipfile.ZipFile(path, 'w') as z:
                z.writestr('summary.json', json.dumps({'started_at': '2026-10-03T09:00:00Z',
                                                       'generated_at': '2026-10-03T09:02:00Z'}))
                z.writestr('observations.jsonl', json.dumps(row) + '\n')
                z.writestr('books.jsonl', '\n'.join(json.dumps(b) for b in books))
            r = audit([path])
        self.assertEqual(r['episodes_with_outcome_and_observed_ask'], 1)
        self.assertEqual(r['order_side_groups_not_independent_intents'], 1)
        self.assertAlmostEqual(r['observed_ask_minus_source_price_median'], .1)


if __name__ == '__main__':
    unittest.main()
