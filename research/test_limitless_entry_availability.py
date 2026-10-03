import unittest
import json
import pathlib
import tempfile
import zipfile
from limitless_entry_availability import depth_quote, report_directory, aggregate_archives, build_report
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
        books = [{**b, 'slug': b.get('slug', 's')} for b in books]
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

    def test_aggregate_dedups_archives_clips_overlapping_poll_credit_and_retains_failure(self):
        account = DEFAULT_ACCOUNTS[0]
        raw = {'tradeEventId': 't', 'strategy': 'Limit Buy', 'outcome': 'YES', 'outcomeTokenPrice': '.5'}
        row = {'kind': 'observation', 'id': 't', 'account': account, 'crypto_candidate': True,
               'first_seen_at': '2026-10-03T09:00:40Z', 'occurred_at': '2026-10-03T09:00:35Z', 'raw': raw}
        polls = [{'kind': 'poll_success', 'source': 'history', 'account': account,
                  'fetched_at': at} for at in ['2026-10-03T09:00:10Z','2026-10-03T09:00:30Z']]
        with tempfile.TemporaryDirectory() as tmp:
            paths = []
            for i in range(2):
                p = pathlib.Path(tmp)/f'{i}.zip'; paths.append(p)
                b = {'event_id': 't', 'fetched_at': '2026-10-03T09:00:41Z', 'error': 'timeout'} if i == 0 else {
                    'event_id': 't', 'request_started_at': '2026-10-03T09:00:45Z',
                    'fetched_at': '2026-10-03T09:00:46Z', 'raw': book()}
                with zipfile.ZipFile(p,'w') as z:
                    z.writestr('summary.json',json.dumps({'started_at':'2026-10-03T09:00:00Z'}))
                    z.writestr('observations.jsonl','\n'.join(map(json.dumps,[row,*polls])))
                    z.writestr('books.jsonl',json.dumps(b))
            r = aggregate_archives(paths,'2026-10-03T09:01:00Z')
        self.assertEqual(len(r['records']),1)
        self.assertEqual(r['records'][0]['status'],'FIRST_BOOK_REQUEST_FAILED')
        self.assertEqual(r['coverage_by_wallet'][account]['covered_seconds'],30)
        self.assertEqual(r['coverage_by_wallet'][account]['fraction'],.5)
        self.assertEqual(r['coverage_by_wallet'][account]['largest_uncredited_gap_s'],30)
        self.assertEqual(r['coverage_by_wallet'][DEFAULT_ACCOUNTS[1]]['fraction'],0)

    def test_aggregate_historical_first_detection_cannot_become_fresh_and_errors_visible(self):
        row = {'kind':'observation','id':'t','account':DEFAULT_ACCOUNTS[0],'crypto_candidate':True,
               'first_seen_at':'2026-10-03T09:01:00Z','occurred_at':'2026-10-03T09:00:30Z',
               'raw':{'tradeEventId':'t','strategy':'Limit Buy','outcome':'YES'}}
        with tempfile.TemporaryDirectory() as tmp:
            paths=[]
            for i, start in enumerate(['2026-10-03T09:01:00Z','2026-10-03T09:00:00Z']):
                p=pathlib.Path(tmp)/f'{i}.zip';paths.append(p)
                with zipfile.ZipFile(p,'w') as z:
                    z.writestr('summary.json',json.dumps({'started_at':start}))
                    z.writestr('observations.jsonl',json.dumps({**row,'first_seen_at':f'2026-10-03T09:01:0{i}Z'}))
            bad=pathlib.Path(tmp)/'bad.zip';bad.write_text('broken');paths.append(bad)
            r=aggregate_archives(paths,'2026-10-03T09:02:00Z')
        self.assertEqual(r['records'],[])
        self.assertEqual(r['historical_crypto_buy_records_excluded'],1)
        self.assertEqual(len(r['archive_errors']),1)

    def fixtures(self):
        uid = '01046332-dc4d-428c-bcf8-deeef19dd43d'
        feed = {'kind':'observation', 'id':'feed', 'account':DEFAULT_ACCOUNTS[0], 'crypto_candidate':True,
            'slug':'s', 'occurred_at':'2026-10-03T09:01:00Z', 'first_seen_at':'2026-10-03T09:01:10Z',
            'raw':{'id':'clob:'+uid+':123', 'profile':{'id':123}, 'entryType':'BOUGHT',
                   'subject':{'slug':'s','title':'BTC Up or Down Hourly'},
                   'facts':{'outcome':'YES','price':'.5','symbol':'USDC'}}}
        history = {**feed, 'id':'history', 'first_seen_at':'2026-10-03T09:01:15Z',
            'raw':{'tradeEventId':uid, 'strategy':'Limit Buy', 'outcomeIndex':1,
                   'outcomeTokenAmounts':['1','1'], 'outcomeTokenPrice':'.5',
                   'market':{'title':'BTC Up or Down Hourly','slug':'s'}}}
        b = {'event_id':'feed', 'slug':'s', 'request_started_at':'2026-10-03T09:01:11Z',
             'fetched_at':'2026-10-03T09:01:12Z', 'raw':book()}
        return {'started_at':'2026-10-03T09:00:00Z'}, feed, history, b

    def test_conflict_is_retrospective_and_preserves_original_quote(self):
        summary, feed, history, b = self.fixtures()
        before = build_report(summary,[feed],[b])
        after = build_report(summary,[history,feed],[b])
        r = after['records'][0]
        self.assertEqual(r['status'],before['records'][0]['status'])
        self.assertEqual(r['vwap'],before['records'][0]['vwap'])
        self.assertEqual(r['first_observed_at'],feed['first_seen_at'])
        self.assertEqual(r['validation_status'],'CONFLICTING_SOURCE_OUTCOME')
        self.assertEqual(r['conflict_observed_at'],'2026-10-03T09:01:15+00:00')
        self.assertFalse(r['validated_for_quote_statistics'])
        stats = after['scopes']['FIXED_COHORT']
        self.assertEqual(stats['ten_usdc_depth_quote_fraction'],0)
        self.assertIsNone(stats['vwap_minus_source_p50'])

    def test_identity_rejects_wrong_and_missing_slug_and_known_wrong_yes_token(self):
        summary, feed, _, b = self.fixtures()
        for slug,status in [('other','MARKET_IDENTITY_MISMATCH'),(None,'UNVERIFIED_MARKET_IDENTITY')]:
            r = build_report(summary,[feed],[{**b,'slug':slug}])['records'][0]
            self.assertEqual(r['status'],status)
        feed['raw']['market'] = {'tokens':{'yes':'wrong-token'}}
        self.assertEqual(build_report(summary,[feed],[b])['records'][0]['status'],'MARKET_IDENTITY_MISMATCH')

    def test_partial_metadata_explicit_and_non_usdc_or_wrong_decimals_rejected(self):
        summary,feed,_,b = self.fixtures()
        r = build_report(summary,[feed],[b])['records'][0]
        self.assertEqual(r['market_identity']['yes_token_validation'],'UNKNOWN')
        self.assertFalse(r['market_identity']['full_market_metadata_verified'])
        for collateral in [{'symbol':'DAI','decimals':6},{'symbol':'USDC','decimals':18}]:
            feed['raw']['market'] = {'collateral':collateral}
            self.assertEqual(build_report(summary,[feed],[b])['records'][0]['status'],'UNSUPPORTED_COLLATERAL')

    def test_bad_timestamp_quarantines_duplicate_without_crashing_good_rows(self):
        summary, feed, history, b = self.fixtures()
        good = {**feed, 'id':'good', 'raw':{**feed['raw'],'id':'unrelated'}}
        for at in ['malformed',None,'2026-10-03T09:01:10',float('nan')]:
            r = build_report(summary,[{**feed,'first_seen_at':at},history,good],[b])
            self.assertEqual(len(r['records']),1)
            self.assertEqual(r['records'][0]['canonical_trade_id'],DEFAULT_ACCOUNTS[0]+':unrelated')
            self.assertEqual(len(r['data_errors']),1)
            self.assertEqual(len(r['quarantined_canonical_ids']),1)

    def test_bad_book_receipt_cannot_be_replaced_by_later_valid_book(self):
        summary,feed,_,b = self.fixtures()
        r = build_report(summary,[feed],[{**b,'fetched_at':'broken'},b])
        self.assertEqual(r['records'][0]['status'],'INVALID_BOOK_TIME')
        self.assertEqual(len(r['data_errors']),1)

    def test_invalid_source_and_request_times_do_not_become_supported(self):
        summary,feed,_,b = self.fixtures()
        r = build_report(summary,[{**feed,'occurred_at':'broken'}],[b])
        self.assertEqual(r['records'],[])
        self.assertEqual(len(r['data_errors']),1)
        for requested in ['broken','2026-10-03T09:01:09Z','2026-10-03T09:01:13Z']:
            r = build_report(summary,[feed],[{**b,'request_started_at':requested}])
            self.assertEqual(r['records'][0]['status'],'UNVERIFIED_POST_DETECTION_REQUEST')

    def test_archive_invalid_observation_time_is_visible_and_preserves_valid_rows(self):
        summary,feed,_,b = self.fixtures()
        bad = {**feed,'first_seen_at':'broken'}
        good = {**feed,'id':'good','raw':{**feed['raw'],'id':'other'}}
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp)/'segment.zip'
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('summary.json',json.dumps(summary))
                z.writestr('observations.jsonl','\n'.join(map(json.dumps,[bad,good])))
                z.writestr('books.jsonl',json.dumps(b))
            r = aggregate_archives([p],'2026-10-03T09:02:00Z')
        self.assertEqual(len(r['records']),1)
        self.assertEqual(len(r['data_errors']),1)
        self.assertEqual(r['data_errors'][0]['artifact'],'segment.zip')

    def test_cross_archive_conflict_is_not_available_before_its_observation(self):
        summary,feed,history,b = self.fixtures()
        with tempfile.TemporaryDirectory() as tmp:
            paths=[]
            for i, rows in enumerate([[feed],[history]]):
                p=pathlib.Path(tmp)/f'{i}.zip';paths.append(p)
                with zipfile.ZipFile(p,'w') as z:
                    z.writestr('summary.json',json.dumps(summary))
                    z.writestr('observations.jsonl','\n'.join(map(json.dumps,rows)))
                    if i==0:z.writestr('books.jsonl',json.dumps(b))
            before=aggregate_archives(paths,'2026-10-03T09:01:14Z')
            after=aggregate_archives(paths,'2026-10-03T09:01:16Z')
        self.assertEqual(before['records'][0]['validation_status'],'DEPTH_SUPPORTS_10_USDC_QUOTE')
        self.assertEqual(after['records'][0]['validation_status'],'CONFLICTING_SOURCE_OUTCOME')
        self.assertEqual(before['records'][0]['vwap'],after['records'][0]['vwap'])


if __name__ == '__main__':
    unittest.main()
