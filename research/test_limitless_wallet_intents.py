import unittest
from limitless_wallet_intents import trace


def event(uid, side, at, operation='Limit Buy', order='o'):
    return {'tradeEventId': uid, 'orderId': order, 'strategy': operation, 'blockTimestamp': at,
            'outcomeIndex': side, 'outcomeTokenAmounts': ['10', '10'],
            'market': {'title': 'BTC Up or Down Hourly', 'conditionId': 'c'}}, '2026-10-03T14:00:00Z'


class TraceTests(unittest.TestCase):
    def test_unknown_initial_inventory_and_order_grouping(self):
        r = trace([event('a', 0, 100), event('b', 0, 110), event('a', 0, 100)], 'TRUNCATED_PAGE_CAP')
        c = r['conditions'][0]
        self.assertEqual(r['unique_events'], 2)
        self.assertEqual(c['initial_inventory'], 'UNKNOWN')
        self.assertEqual(c['order_side_groups'][0]['fill_events'], 2)
        self.assertEqual(c['timeline'][0]['actions'][0]['observed_action'], 'FIRST_OBSERVED_SIDE_BUY_NOT_CONFIRMED_ENTER')
        self.assertEqual(c['timeline'][1]['actions'][0]['observed_action'], 'REPEATED_OBSERVED_SIDE_BUY')
        self.assertIsNone(c['independent_intents'])

    def test_same_timestamp_both_sides_no_order_invention(self):
        c = trace([event('a', 0, 100), event('b', 1, 100)], 'END_OF_AVAILABLE_API_HISTORY')['conditions'][0]
        self.assertEqual(c['timeline'][0]['within_batch_order'], 'UNKNOWN')
        self.assertTrue(all(x['observed_action'] == 'BOTH_SIDE_BUY_BATCH' for x in c['timeline'][0]['actions']))

    def test_later_opposite_does_not_change_earlier_action(self):
        c = trace([event('a', 0, 100), event('b', 1, 200)], 'TRUNCATED_PAGE_CAP')['conditions'][0]
        self.assertEqual(c['timeline'][0]['actions'][0]['observed_action'], 'FIRST_OBSERVED_SIDE_BUY_NOT_CONFIRMED_ENTER')
        self.assertEqual(c['timeline'][1]['actions'][0]['observed_action'], 'BUY_SIDE_PREVIOUSLY_OPPOSITE_BUY_SEEN')

    def test_sell_merge_claim_never_invent_exit_inventory_profit(self):
        c = trace([event('a', 0, 100, 'Market Sell'), event('b', 0, 200, 'Merge'),
                   event('c', 0, 300, 'Claim')], 'END_OF_AVAILABLE_API_HISTORY')['conditions'][0]
        self.assertEqual(c['final_inventory'], 'UNKNOWN')
        self.assertEqual(c['timeline'][0]['actions'][0]['observed_action'], 'OBSERVED_SELL_REDUCE_OR_EXIT_UNKNOWN')
        self.assertEqual(c['timeline'][2]['actions'][0]['observed_action'], 'REDEMPTION_NOT_PROFIT_OR_INDEPENDENT_WIN')
        self.assertEqual(c['smartcopy_action'], 'SKIP_UNQUALIFIED_STRATEGY')

    def test_missing_time_not_silently_sorted_to_start(self):
        row, observed = event('a', 0, 100)
        row.pop('blockTimestamp')
        r = trace([(row, observed)], 'TRUNCATED_PAGE_CAP')
        self.assertEqual(r['conditions'], [])
        self.assertEqual(len(r['excluded_events']), 1)


if __name__ == '__main__':
    unittest.main()
