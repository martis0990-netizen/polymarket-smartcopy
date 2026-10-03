"""Collector integration regressions: mocked HTTP/socket/clock; no network."""
import asyncio
import copy
import gzip
import json
import pathlib
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from limitless_hourly_paper import HourlyPaper
from limitless_inventory_paper import InventoryPaper, VERSION, archive_report
from limitless_market_capture import (capture, process_book_attempt, process_market_observation,
                                      restore_inventory)
from test_limitless_inventory_paper import market, book, seeded, START, MID, write_archive


class Socket:
    def __init__(self, **kwargs):self.connected=False
    def on(self, *args, **kwargs):return lambda f:f
    async def connect(self, *args, **kwargs):self.connected=True
    async def disconnect(self):self.connected=False
    async def emit(self, *args, **kwargs):pass


class Clock:
    def __init__(self, at):self.now=at
    def time(self):return self.now
    async def sleep(self, seconds):self.now+=max(1,seconds)


class CaptureIntegrationTests(unittest.TestCase):
    def test_first_failed_entry_cannot_be_replaced_by_later_hourly_fill(self):
        p=HourlyPaper();p.market(market(),MID);m=InventoryPaper(started_at=MID-1)
        with patch.object(p,'_inputs',return_value=(.606,.01,100,MID)):
            process_book_attempt(p,m,market(),book('.55','.57'),MID,MID-.1)
        process_book_attempt(p,m,market(),None,MID+2,MID+1.6)
        self.assertEqual(m.state['admission_skips']['condition-1'],'FIRST_ENTRY_ATTEMPT_FAILED')
        process_book_attempt(p,m,market(),book('.54','.56'),MID+18,MID+17.9)
        self.assertEqual(p.state['episodes']['condition-1']['variants']['model']['status'],'FILLED')
        self.assertEqual(m.state['positions'],{});self.assertEqual(m.state['cash'],'100')

    def test_preeligibility_failure_does_not_consume_future_entry_attempt(self):
        p=HourlyPaper();p.market(market(),MID);m=InventoryPaper(started_at=MID-1)
        with patch.object(p,'_inputs',return_value=(.606,.01,100,MID)):
            process_book_attempt(p,m,market(),book('.55','.57'),MID,MID-.1)
        process_book_attempt(p,m,market(),None,MID+1,MID+.5)
        self.assertEqual(m.state['entry_attempts'],{})
        process_book_attempt(p,m,market(),book('.55','.57'),MID+2,MID+1.6)
        self.assertEqual(len(m.state['positions']),1);m.validate()

    def test_resolved_without_payout_is_not_retired_then_settles_once(self):
        p,m=seeded()
        self.assertFalse(process_market_observation(p,m,market(status='RESOLVED'),START+3601))
        restored,_=restore_inventory({'inventory_paper':m.state},START+3700)
        mm=market(status='RESOLVED',winningOutcomeIndex=0)
        self.assertTrue(process_market_observation(p,restored,mm,START+3701))
        before=copy.deepcopy(restored.state)
        self.assertTrue(process_market_observation(p,restored,mm,START+3702))
        self.assertEqual(before,restored.state)

    def test_invalid_payout_does_not_corrupt_frozen_baseline_before_validation(self):
        p,m=seeded();before=copy.deepcopy(p.state)
        for nums in ([float('inf'),1],[float('nan'),1],[0,1]):
            raw=market(status='RESOLVED',winningOutcomeIndex=0,payoutNumerators=nums)
            self.assertFalse(process_market_observation(p,m,raw,START+3601))
            self.assertEqual(p.state,before);self.assertEqual(m.state['cash'],'90')

    def test_v1_state_is_preserved_but_never_imported_and_v2_restores(self):
        old={'version':'limitless-inventory-paper-v1','cash':'90','realized_pnl':'0',
             'started_at':MID-100,'positions':{'old':{'unverified':'retained'}}}
        saved={'inventory_paper':old}
        m,history=restore_inventory(saved,MID)
        self.assertEqual(m.state['version'],VERSION);self.assertEqual(m.state['cash'],'100')
        self.assertEqual(m.state['positions'],{});self.assertIn(old,list(history.values()))
        m2,h2=restore_inventory({'inventory_paper':m.state,'inventory_paper_history':history},MID+10)
        self.assertEqual(m2.state['started_at'],MID);self.assertEqual(h2,history);self.assertEqual(saved['inventory_paper'],old)

    def run_capture(self,tmp,args,clock,request):
        with patch.dict(sys.modules,{'socketio':types.SimpleNamespace(AsyncClient=Socket)}), \
                patch('limitless_market_capture.request',side_effect=request), \
                patch('limitless_market_capture.time.time',side_effect=clock.time), \
                patch('limitless_market_capture.time.monotonic',side_effect=clock.time), \
                patch('limitless_market_capture.asyncio.sleep',side_effect=clock.sleep), \
                patch.object(HourlyPaper,'_inputs',side_effect=lambda s,at:(.606,.01,100,at)), \
                patch('builtins.print'):
            asyncio.run(capture(args))
        return json.loads((pathlib.Path(args.out)/'state.json').read_text())

    def test_full_capture_http_failure_records_rejected_first_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            clock=Clock(MID);calls=0
            def request(path,params=None):
                nonlocal calls
                if path=='/markets/active':return {'data':[market()],'totalMarketsCount':1}
                if path.endswith('/orderbook'):
                    calls+=1
                    if calls==2:raise RuntimeError('mock timeout')
                    return book('.55','.57') if calls==1 else book('.54','.56')
                if path=='/api/v3/klines':return [[int(START*1000),'100']]
                if path=='/markets/btc-hour':return market()
                return []
            args=types.SimpleNamespace(out=tmp+'/out',state=None,minutes=.8,until='2026-10-03T15:00:00Z')
            state=self.run_capture(tmp,args,clock,request)
            self.assertGreaterEqual(calls,3)
            self.assertEqual(state['inventory_paper']['positions'],{})
            self.assertEqual(state['inventory_paper']['admission_skips']['condition-1'],'FIRST_ENTRY_ATTEMPT_FAILED')
            self.assertEqual(state['paper']['episodes']['condition-1']['variants']['model']['status'],'FILLED')
            with gzip.open(tmp+'/out/inventory_evidence.jsonl.gz','rt') as f:rows=[json.loads(x) for x in f]
            self.assertTrue(any(r['source']['book'] is None for r in rows))

    def test_full_capture_restores_lost_watch_retries_partial_payout_and_carries_evidence(self):
        import zipfile
        with tempfile.TemporaryDirectory() as tmp:
            p,m=seeded();prior=pathlib.Path(tmp)/'prior.zip';write_archive(prior,m.state,ended=START+3600)
            previous=pathlib.Path(tmp)/'previous';previous.mkdir()
            with zipfile.ZipFile(prior) as z:z.extractall(previous)
            initial=json.loads((previous/'state.json').read_text());initial['paper']=p.state
            initial['watched']={'btc-hour':{'resolved':True,'market':market(status='RESOLVED')}}
            (previous/'state.json').write_text(json.dumps(initial))
            clock=Clock(START+3601);calls=0
            def request(path,params=None):
                nonlocal calls
                if path=='/markets/active':return {'data':[],'totalMarketsCount':0}
                if path=='/markets/btc-hour':
                    calls+=1
                    return market(status='RESOLVED') if calls==1 else market(status='RESOLVED',winningOutcomeIndex=0)
                return []
            args=types.SimpleNamespace(out=tmp+'/out',state=str(previous/'state.json'),minutes=5.1,until='2026-10-03T15:00:00Z')
            state=self.run_capture(tmp,args,clock,request)
            self.assertEqual(calls,2);self.assertEqual(state['watched'],{})
            self.assertEqual(state['inventory_paper']['cash'],'114.25')
            restored=InventoryPaper(state['inventory_paper']);self.assertEqual(restored.report()['settled_positions'],1)
            path=pathlib.Path(tmp)/'current.zip'
            with zipfile.ZipFile(path,'w') as z:
                for name in ('state.json','summary.json','inventory_evidence.jsonl.gz'):
                    z.write(pathlib.Path(args.out)/name,name)
            r=archive_report([path]);self.assertEqual(r['status'],'RECONCILED_PAPER_ONLY');self.assertEqual(r['report']['cash'],'114.25')


if __name__=='__main__':unittest.main()
