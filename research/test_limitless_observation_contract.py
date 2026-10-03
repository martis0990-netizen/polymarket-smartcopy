import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from limitless_smartcopy_probe import event_items, page_evidence, capture_metadata
from limitless_entry_availability import book_identity, entry_eligibility, observation_quality, observed_actions


def snapshot():
    raw = {'slug': 's', 'tokens': {'yes': '123', 'no': '456'}, 'conditionId': '0x' + 'a'*64,
           'collateralToken': {'symbol': 'USDC', 'decimals': 6,
                               'address': '0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'},
           'expirationTimestamp': 1791028800000, 'tradeType': 'clob', 'marketType': 'single',
           'expired': False, 'status': 'FUNDED', 'description': 'Rules retained verbatim in raw snapshot.'}
    return {'slug': 's', 'request_started_at': '2026-10-03T09:01:09Z',
            'fetched_at': '2026-10-03T09:01:10Z', 'raw': raw,
            'raw_sha256': hashlib.sha256(json.dumps(raw, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}


def fixture(meta=None):
    return ({'slug': 's', 'raw': {}},
            {'slug': 's', 'raw': {'tokenId': '123'}, 'request_started_at': '2026-10-03T09:01:11Z',
             'fetched_at': '2026-10-03T09:01:12Z', 'market_snapshot': meta or snapshot()})


class ContractTests(unittest.TestCase):
    def test_unknown_page_schema_is_not_successful_empty_poll(self):
        self.assertEqual(event_items({'events': []}), [])
        for p in ({'error': 'upstream'}, {'events': None}, None):
            with self.assertRaises(ValueError):
                event_items(p)
        with self.assertRaises(ValueError):
            page_evidence([None], None, [])

    def test_disjoint_pages_warn_without_inventing_loss_count(self):
        p = page_evidence([{'id': str(i)} for i in range(30)], 'w', ['w:old'])
        self.assertTrue(p['page_saturated'])
        self.assertTrue(p['possible_page_gap'])
        self.assertIsNone(p['lost_events_count'])
        self.assertFalse(page_evidence([{'id': '1'}], 'w', ['w:1'])['possible_page_gap'])
        self.assertFalse(page_evidence([], 'w', ['w:1'])['possible_page_gap'])

    def test_metadata_request_budget_and_no_favorable_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = pathlib.Path(tmp)/'metadata.jsonl'
            cache = {}
            with patch('limitless_smartcopy_probe.get_json', side_effect=ValueError('first attempt failed')) as get:
                a = capture_metadata('s', cache, path, limit=1)
                self.assertIs(capture_metadata('s', cache, path, limit=1), a)
                self.assertEqual(capture_metadata('other', cache, path, limit=1)['error'], 'METADATA_REQUEST_BUDGET_EXHAUSTED')
                self.assertEqual(get.call_count, 1)
                self.assertEqual(len(path.read_text().splitlines()), 1)

    def test_prospective_identity_is_separate_from_copy_eligibility(self):
        status, identity = book_identity(*fixture())
        self.assertIsNone(status)
        self.assertTrue(identity['full_market_metadata_verified'])
        self.assertFalse(identity['resolution_semantics_verified'])
        r = entry_eligibility({'status': 'DEPTH_SUPPORTS_10_USDC_QUOTE', 'market_identity': identity})
        self.assertTrue(r['data_qualified_quote'])
        self.assertEqual(r['copy_decision'], 'SKIP')
        self.assertIsNone(r['fill']); self.assertIsNone(r['copy_pnl'])

    def test_late_metadata_missing_fields_expiry_and_hash_never_qualify(self):
        variants = []
        m = snapshot(); m['fetched_at'] = '2026-10-03T09:01:15Z'; variants.append(m)
        for field, value in [('expired', True), ('status','RESOLVED'), ('expirationTimestamp',1791018000000), ('tokens',None)]:
            m = snapshot(); m['raw'][field] = value
            m['raw_sha256'] = hashlib.sha256(json.dumps(m['raw'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            variants.append(m)
        m = snapshot(); m['raw_sha256'] = 'corrupt'; variants.append(m)
        for m in variants:
            status, identity = book_identity(*fixture(m))
            self.assertFalse(identity['full_market_metadata_verified'])
            self.assertFalse(entry_eligibility({'status': status or 'DEPTH_SUPPORTS_10_USDC_QUOTE', 'market_identity': identity})['data_qualified_quote'])

    def test_wrong_book_token_and_collateral_are_rejected(self):
        row, b = fixture(); b['raw']['tokenId'] = '456'
        self.assertEqual(book_identity(row,b)[0], 'MARKET_IDENTITY_MISMATCH')
        m = snapshot(); m['raw']['collateralToken']['address'] = '0xother'
        m['raw_sha256'] = hashlib.sha256(json.dumps(m['raw'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        self.assertEqual(book_identity(*fixture(m))[0], 'UNSUPPORTED_COLLATERAL')

    def test_legacy_pages_stay_unknown_and_request_errors_counted(self):
        rows = [{'kind':'poll_success','source':'history','account':'w','fetched_at':'2026-10-03T09:00:00Z'},
                {'kind':'request_error','source':'history','account':'w','fetched_at':'2026-10-03T09:00:30Z'}]
        q = observation_quality(rows)['history:w']
        self.assertEqual(q['legacy_pages_completeness_unknown'],1)
        self.assertEqual(q['request_errors'],1)
        self.assertIsNone(q['lost_events_count'])

    def test_both_sides_and_paired_operations_do_not_become_directional_entries(self):
        selected = {str(i):{'account':'w','slug':'s','raw':{'strategy':op,'outcome':side}} for i,(op,side) in enumerate([('Buy','YES'),('Buy','NO'),('Merge',None)])}
        # The decoder accepts literal BUY; title-free YES/NO labels are explicit.
        r = observed_actions(selected)
        self.assertEqual(r['conditions'][0]['category'],'PAIRED_OPERATION_OBSERVED')
        self.assertEqual(r['conditions'][0]['initial_inventory'],'UNKNOWN')
        self.assertFalse(r['conditions'][0]['confirmed_directional_entry'])
        self.assertEqual(r['conditions'][0]['copy_decision'],'SKIP')
