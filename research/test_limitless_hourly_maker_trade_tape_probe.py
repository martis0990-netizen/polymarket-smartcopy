import unittest

from limitless_hourly_maker_trade_tape_probe import collect


class PublicTradeTapeProbeTest(unittest.TestCase):
    def setUp(self):
        self.row={'slug':'btc-up-or-down-hourly-p-123','condition':'0xabc',
                  'decision_at':1791246600,'first_attempt_at':1791246618}

    def test_complete_page_with_recheck_is_retrospective_only(self):
        event={'createdAt':'2026-10-06T00:30:20Z','tokenId':'7','side':1,
               'matchedSize':'1000000','price':0.5,'txHash':'0xab'}
        calls=[]; written=[]
        def fetch(slug,page):
            calls.append(page)
            return {'http_status':200,'body_sha256':'same',
                    'body':{'events':[event],'totalPages':1}}
        result=collect([self.row],fetch,written.append)
        self.assertEqual(calls,[1,1])
        self.assertTrue(result[0]['complete'])
        self.assertEqual(result[0]['field_time_window_events'],1)
        self.assertIsNone(result[0].get('maker_fill'))
        self.assertNotIn('profile',written[0]['events'][0])

    def test_pagination_error_never_becomes_no_trades(self):
        written=[]
        def fetch(slug,page):
            if page==1:
                return {'http_status':200,'body_sha256':'one',
                        'body':{'events':[{'createdAt':'2026-10-06T00:30:20Z'}],
                                'totalPages':2}}
            return {'http_status':500,'error':'unavailable'}
        result=collect([self.row],fetch,written.append)
        self.assertFalse(result[0]['complete'])
        self.assertEqual(result[0]['error'],'unavailable')
        self.assertEqual(result[0]['pages'],1)


if __name__=='__main__':unittest.main()
