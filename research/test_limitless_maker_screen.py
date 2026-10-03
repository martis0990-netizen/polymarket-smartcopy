import copy
import datetime as dt
import gzip
import hashlib
import json
import pathlib
import tempfile
import unittest
import zipfile

from limitless_maker_screen import analyze, screen_rows, aggregate, bbo
from test_limitless_inventory_paper import market
from test_limitless_hourly_paper import MID, candles


def iso(at):
    return dt.datetime.fromtimestamp(at, dt.timezone.utc).isoformat()


def meta(at=MID-1):
    return {'kind':'market','observed_at':iso(at),'slug':'btc-hour','raw':market()}


def frame(t=0, bid=.45, ask=.55, version=None):
    return {'kind':'ws_event','event':'orderbookUpdate','observed_at':iso(MID+t),
        'raw':{'marketSlug':'btc-hour','version':int(t*10+1) if version is None else version,
               'timestamp':iso(MID+t-.1),'orderbook':{'tokenId':'token','minSize':100000000,
                   'bids':[{'price':bid,'size':30000000}], 'asks':[{'price':ask,'size':40000000}]}}}


def ref(t, price):
    rows=candles(MID+t);rows[-1][4]=str(price)
    return {'kind':'binance_1m','source':'binance','params':{'symbol':'BTCUSDT'},
            'observed_at':iso(MID+t),'requested_at':iso(MID+t-.2),'raw':rows}


def screen(rows):
    return screen_rows(enumerate(rows,1),'fixture')


def archive(root,name,rows,start=MID-2,end=MID+40):
    p=root/name
    with zipfile.ZipFile(p,'w') as z:
        z.writestr('summary.json',json.dumps({'started_at':iso(start),'ended_at':iso(end)}))
        z.writestr('capture.jsonl.gz',gzip.compress(('\n'.join(json.dumps(r) for r in rows)+'\n').encode()))
    return {'file':name,'head_branch':'main','event':'workflow_dispatch','conclusion':'success',
            'head_sha':'test-head','artifact_id':name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}


class MakerScreenTests(unittest.TestCase):
    def test_quote_margins_are_signed_and_never_fills(self):
        result=screen([meta()]+[frame(t,.45 if t<5 else .58,.55 if t<5 else .62) for t in range(32)])
        a=result['anchors'][0]
        self.assertEqual(a['nominal_bid_yes'],.45)
        self.assertAlmostEqual(a['nominal_bid_no'],.45)
        h=a['horizons']['5']
        self.assertEqual(h['status'],'OBSERVED_NOT_FILL')
        self.assertAlmostEqual(h['yes_midpoint_margin'],.15)
        self.assertAlmostEqual(h['worst_midpoint_margin'],-.05)
        self.assertEqual(a['bbo_first_observed_change_s'],5)
        self.assertEqual(aggregate(result['anchors'])['hour_clusters'],1)
        self.assertEqual(len(result['anchors']),2)

    def test_future_metadata_cannot_qualify_earlier_book(self):
        result=screen([frame(),meta(MID+.1),frame(1)])
        self.assertEqual(result['counts']['no_prior_qualified_metadata'],1)
        self.assertEqual(result['anchors'][0]['at'],MID+1)
        stale=screen([meta(MID-121),frame()])
        self.assertEqual(stale['anchors'],[])

    def test_missing_horizon_gap_and_disconnect_are_unknown(self):
        for rows in ([meta(),frame(),frame(5)],
                     [meta(),frame(),{'kind':'ws_disconnect','observed_at':iso(MID+.5)},frame(1)]):
            with self.subTest(rows=rows):
                self.assertEqual(screen(rows)['anchors'][0]['horizons']['1']['status'],'UNKNOWN_GAP_OR_END')

    def test_invalid_intermediate_frame_breaks_chain(self):
        bad=frame(.5);bad['raw']['orderbook']['tokenId']='foreign'
        result=screen([meta(),frame(),bad,frame(1)])
        self.assertEqual(result['anchors'][0]['horizons']['1']['status'],'UNKNOWN_GAP_OR_END')
        self.assertEqual(result['counts']['reason:TOKEN_MISMATCH'],1)

    def test_duplicates_do_not_count_and_conflicts_quarantine(self):
        a=frame();b=copy.deepcopy(a);b['observed_at']=iso(MID+.1)
        result=screen([meta(),a,b,frame(1)])
        self.assertEqual(result['counts']['valid_unique_book_frames'],2)
        self.assertEqual(result['counts']['duplicate_book_versions'],1)
        b['raw']['orderbook']['bids'][0]['price']=.44
        result=screen([meta(),a,b,frame(1)])
        self.assertEqual(result['anchors'],[])
        self.assertEqual(result['quarantined_slugs'],['btc-hour'])

    def test_version_reset_does_not_bridge_gap(self):
        result=screen([meta(),frame(0,version=10),frame(.5,version=2),frame(1,version=11)])
        self.assertEqual(result['counts']['reason:VERSION_OR_SOURCE_REVERSED'],1)
        self.assertEqual(result['anchors'][0]['horizons']['1']['status'],'UNKNOWN_GAP_OR_END')

    def test_nonfinite_crossed_future_and_naive_times_rejected(self):
        bads=[]
        b=frame();b['raw']['orderbook']['bids'][0]['price']=float('nan');bads.append(b)
        b=frame();b['raw']['timestamp']=iso(MID+1);bads.append(b)
        b=frame();b['raw']['timestamp']='2026-10-03T13:30:00';bads.append(b)
        bads.append(frame(bid=.56,ask=.55))
        b=frame();b['raw']['version']=True;bads.append(b)
        for bad in bads:
            with self.subTest(bad=bad):self.assertEqual(screen([meta(),bad])['anchors'],[])

    def test_reference_uses_only_received_data_and_requires_new_observation(self):
        result=screen([meta(),frame(),ref(.5,100),frame(1),ref(1.5,101),frame(2)])
        a=result['anchors'][0]
        self.assertIsNone(a['reference'])
        self.assertIsNone(a['horizons']['1']['underlying_change_bps'])
        result=screen([meta(),ref(0,100),frame(.1),frame(1.1),ref(1.5,101),frame(2.1)])
        self.assertIsNone(result['anchors'][0]['horizons']['1']['underlying_change_bps'])
        result=screen([meta(),ref(0,100),frame(.1),ref(.5,101),frame(1.1)])
        self.assertAlmostEqual(result['anchors'][0]['horizons']['1']['underlying_change_bps'],100)

    def test_raw_size_units_and_lp_min_are_separate_from_fill_eligibility(self):
        result=screen([meta(),frame()]);a=result['anchors'][0]
        self.assertEqual(a['displayed_yes_bid_shares'],30)
        self.assertEqual(a['displayed_no_bid_shares'],40)
        self.assertEqual(a['lp_min_size_shares'],100)
        self.assertEqual(aggregate([a])['nominal_size_below_lp_min'],1)

    def test_manifest_hash_pr_overlap_and_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp);entry=archive(root,'a.zip',[meta(),frame(),frame(1)])
            result=analyze({'artifacts':[entry,entry]},root)
            self.assertEqual(result['status'],'DIAGNOSTIC_ONLY_NO_FILL_MODEL')
            self.assertEqual(len(result['provenance']),1)
            self.assertIsNone(result['pnl']);self.assertIsNone(result['fill_probability'])
            bad={**entry,'sha256':'bad'}
            self.assertEqual(analyze({'artifacts':[bad]},root)['status'],'INVALID_INPUT')
            bad={**entry,'event':'pull_request'}
            self.assertEqual(analyze({'artifacts':[bad]},root)['status'],'INVALID_INPUT')
            other=archive(root,'b.zip',[meta(),frame(),frame(2)])
            self.assertEqual(analyze({'artifacts':[entry,other]},root)['status'],'INVALID_INPUT')

    def test_no_join_across_segments_and_unknown_is_in_denominator(self):
        a=screen([meta(),frame()])['anchors'][0]
        stats=aggregate([a]);self.assertEqual(stats['horizons']['30']['observed'],0)
        self.assertEqual(stats['horizons']['30']['unknown'],1)
        self.assertEqual(stats['horizons']['30']['worst_midpoint_margin']['n'],0)

    def test_identity_change_between_nonoverlapping_segments_invalidates_aggregate(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=pathlib.Path(tmp)
            a=archive(root,'a.zip',[meta(),frame()],end=MID+1)
            m=meta(MID+2);m['raw']['tokens']['yes']='other-token'
            f=frame(3);f['raw']['orderbook']['tokenId']='other-token'
            b=archive(root,'b.zip',[m,f],start=MID+2,end=MID+4)
            result=analyze({'artifacts':[a,b]},root)
            self.assertEqual(result['status'],'INVALID_INPUT')
            self.assertIsNone(result['summary'])
            self.assertEqual(result['errors'][0]['error'],'CROSS_SEGMENT_IDENTITY_CONFLICT')


if __name__=='__main__':unittest.main()
