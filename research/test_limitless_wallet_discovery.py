import unittest
from limitless_wallet_discovery import discover, history_summary, pnl_summary, Client

A = '0x' + 'a' * 40
B = '0x' + 'b' * 40
C = '0x' + 'c' * 40


class DiscoveryTests(unittest.TestCase):
    def test_not_ready_and_invalid_accounts_excluded(self):
        rows = discover([('leaderboard_pnl', {'state': 'STALE', 'data': [{'account': A}]}),
                         ('public_feed', [{'profile': {'account': 'invalid'}}, {'profile': {'account': B}}])], 't', {})
        self.assertEqual([x['account'] for x in rows], [B])

    def test_round_robin_before_pnl_and_earliest_observation(self):
        rows = discover([('leaderboard_position_size', {'state': 'READY', 'data': [{'account': A}, {'account': C}]}),
                         ('public_feed', [{'profile': {'account': B}}, {'profile': {'account': A},
                                          'subject': {'title': 'BTC Up or Down Hourly'}}])], 'new', {A: 'old'})
        self.assertEqual([x['account'] for x in rows], [A, B, C])
        self.assertEqual(rows[0]['first_seen_at'], 'old')
        self.assertEqual(len(rows[0]['sources']), 2)
        self.assertTrue(rows[0]['crypto_btc_eth_15m_hourly_seen'])
        self.assertEqual(rows[0]['qualification'], 'UNASSESSED_NO_COPY_PERMISSION')

    def test_same_transaction_distinct_fills_not_collapsed(self):
        rows = [{'tradeEventId': 'one', 'transactionHash': 'tx', 'market': {'conditionId': 'same'}},
                {'tradeEventId': 'two', 'transactionHash': 'tx', 'market': {'conditionId': 'same'}}]
        result = history_summary(rows + rows)
        self.assertEqual(result['sampled_unique_events'], 2)
        self.assertEqual(result['sampled_conditions'], 1)
        self.assertIsNone(result['independent_intent_episodes'])
        self.assertIsNone(result['copy_pnl'])

    def test_pnl_units_not_invented(self):
        self.assertEqual(pnl_summary({'current': {'raw': '123'}})['realized_pnl_usd'], None)
        self.assertEqual(pnl_summary({'current': {'usd': '-2.3'}, 'timeframe': '1w'})['realized_pnl_usd'], '-2.3')
        self.assertEqual(pnl_summary({})['status'], 'SCHEMA_UNKNOWN')

    def test_trading_and_external_paths_rejected_before_network(self):
        client = Client(None, 0)
        for path in ('/orders', 'https://elsewhere/', '/portfolio/invalid/history'):
            with self.assertRaises(ValueError):
                client.get(path)


if __name__ == '__main__':
    unittest.main()
