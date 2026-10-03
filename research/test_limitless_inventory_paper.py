import copy
import unittest
from unittest.mock import patch
from decimal import Decimal as D
from limitless_inventory_paper import InventoryPaper, value, quote, archive_report
from limitless_hourly_paper import HourlyPaper
from test_limitless_hourly_paper import market as old_market, START, MID


def market(**kw):
    m = old_market(); m['marketType']='single';m['tokens']['no']='no-token'
    m['collateralToken']['address']='0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913';m.update(kw)
    return m


def book(bid='.69', ask='.71', size=100000000):
    return {'tokenId':'token','bids':[{'price':bid,'size':size}], 'asks':[{'price':ask,'size':size}]}


def seeded():
    p=HourlyPaper();p.market(market(),MID)
    ep={'condition':'condition-1','slug':'btc-hour','decision_at':MID,
        'variants':{'model':{'status':'FILLED','side':'YES','fill_at':MID+2,
                            'cost_usdc':'10','net_shares':'24.25'}}}
    p.state['episodes']['condition-1']=ep
    manager=InventoryPaper(started_at=MID-1);manager.book(p,market(),book(),MID+2,MID+1.5)
    return p,manager


class InventoryTests(unittest.TestCase):
    def test_pair_payoff_not_double_discounted_by_probability_stress(self):
        self.assertEqual(value(D(10),D(10),'.5'),10)
        self.assertEqual(value(D(10),D(0),'.5'),D('4.7'))

    def test_yes_no_sell_quotes_and_buy_fee_units(self):
        b=book('.4','.6')
        self.assertEqual(D(quote(b,'YES',10,False)['net_cash']),D('3.940'))
        self.assertEqual(D(quote(b,'NO',10,False)['net_cash']),D('3.940'))
        self.assertEqual(quote(b,'NO',10,True)['net_quantity'],'9.70')
        for b in (book('.6','.5'),book('.5','.5'),book(size=1.5)):
            with self.assertRaises(ValueError):quote(b,'YES',10,False)
        self.assertIsNone(quote(book(size=1000000),'YES',10,False))

    def test_admission_is_once_funded_and_not_on_legacy_fills(self):
        p,m=seeded();self.assertEqual(m.state['cash'],'90');self.assertEqual(len(m.state['positions']),1)
        self.assertFalse(m.admit(p.state['episodes']['condition-1'],market(),MID+3))
        old=InventoryPaper(started_at=MID+3)
        self.assertFalse(old.admit(p.state['episodes']['condition-1'],market(),MID+4))
        self.assertEqual(old.state['cash'],'100')

    def test_capital_exhaustion_and_market_identity_skip(self):
        p,m=seeded()
        for i in range(1,11):
            ep=copy.deepcopy(p.state['episodes']['condition-1']);ep['condition']=str(i);ep['slug']=str(i)
            m.admit(ep,market(conditionId=str(i),slug=str(i)),MID+3)
        self.assertEqual(m.state['cash'],'0')
        self.assertEqual(m.state['admission_skips']['10'],'INSUFFICIENT_CAPITAL')
        m.validate()
        bad=InventoryPaper(started_at=MID-1);mm=market();mm['collateralToken']['address']='other'
        self.assertFalse(bad.admit(p.state['episodes']['condition-1'],mm,MID+3))

    def test_completion_uses_net_shares_delay_and_real_accounting(self):
        p,m=seeded()
        with patch.object(p,'_inputs',return_value=(.6,.01,100,MID+3)):
            m.book(p,market(),book(),MID+3,MID+2.9)
        pos=m.state['positions']['condition-1'];a=pos['management']
        self.assertEqual(a['action'],'COMPLETE_PAIR');self.assertEqual(a['status'],'PENDING')
        m.book(p,market(),book(),MID+4,MID+3.2);self.assertEqual(a['status'],'PENDING')
        m.book(p,market(),book(),MID+5,MID+4.6)
        self.assertEqual(pos['management']['status'],'PAPER_EXECUTED')
        self.assertEqual(pos['quantity']['YES'],'0.00')
        self.assertGreater(D(pos['paper_merge']['pnl_usdc']),0)
        m.validate();before=copy.deepcopy(m.state)
        m.book(p,market(),book(),MID+6,MID+5.6);self.assertEqual(before,m.state)
        m.market(market(status='RESOLVED',winningOutcomeIndex=0),START+3601)
        r=m.report();self.assertEqual(r['settled_positions'],1)
        self.assertGreater(D(r['seed_hold_settled_pnl']),D(r['managed_settled_pnl']))
        # A profitable pair may still underperform holding a winning directional position.
        m.validate()

    def test_hold_when_upside_exceeds_pair_or_sale(self):
        p,m=seeded()
        with patch.object(p,'_inputs',return_value=(.95,.01,100,MID+3)):
            m.book(p,market(),book(),MID+3,MID+2.9)
        self.assertEqual(m.state['positions']['condition-1']['management']['action'],'HOLD')

    def test_sale_when_model_reverses_and_no_profitable_pair(self):
        p,m=seeded()
        with patch.object(p,'_inputs',return_value=(.2,.01,100,MID+3)):
            m.book(p,market(),book('.3','.32'),MID+3,MID+2.9)
        pos=m.state['positions']['condition-1'];self.assertEqual(pos['management']['action'],'SELL')
        m.book(p,market(),book('.3','.32'),MID+5,MID+4.6)
        self.assertEqual(pos['quantity']['YES'],'0.00');self.assertLess(D(m.state['realized_pnl']),0)
        m.validate()

    def test_first_failed_execution_never_retried_at_better_price(self):
        p,m=seeded()
        with patch.object(p,'_inputs',return_value=(.6,.01,100,MID+3)):
            m.book(p,market(),book(),MID+3,MID+2.9)
        before=m.state['cash']
        m.book(p,market(),book('.4','.42'),MID+5,MID+4.6)
        a=m.state['positions']['condition-1']['management'];self.assertEqual(a['status'],'SKIP')
        m.book(p,market(),book(),MID+6,MID+5.6)
        self.assertEqual(m.state['cash'],before);m.validate()

    def test_unavailable_book_missing_inputs_and_bad_token_do_not_promote(self):
        p,m=seeded();m.unavailable_book('btc-hour',MID+3,MID+2.9)
        self.assertEqual(m.state['positions']['condition-1']['management']['status'],'SKIP')
        p,m=seeded()
        with patch.object(p,'_inputs',side_effect=ValueError('STALE_REFERENCE')):
            m.book(p,market(),book(),MID+3,MID+2.9)
        self.assertEqual(m.state['positions']['condition-1']['management']['reason'],'STALE_REFERENCE')
        p,m=seeded()
        with patch.object(p,'_inputs',return_value=(.6,.01,100,MID+3)):
            m.book(p,market(),book(),MID+3,MID+2.9)
        bad=book();bad['tokenId']='wrong'
        m.book(p,market(),bad,MID+5,MID+4.6)
        self.assertEqual(m.state['positions']['condition-1']['management']['status'],'SKIP')
        m.validate()

    def test_split_settlement_restore_and_cash_invariant(self):
        p,m=seeded();restored=InventoryPaper(m.state,started_at=MID+100)
        self.assertEqual(restored.state['started_at'],MID-1)
        mm=market(status='RESOLVED',winningOutcomeIndex=None,payoutNumerators=['1','1'])
        restored.market(mm,START+3599);self.assertEqual(restored.report()['settled_positions'],0)
        restored.market(mm,START+3601);self.assertEqual(restored.state['cash'],'102.125')
        before=copy.deepcopy(restored.state);restored.market(mm,START+3602);self.assertEqual(before,restored.state)
        corrupt=copy.deepcopy(restored.state);corrupt['cash']='999'
        with self.assertRaises(ValueError):InventoryPaper(corrupt)

    def test_deadline_and_resolution_prevent_late_execution(self):
        p,m=seeded()
        with patch.object(p,'_inputs',return_value=(.6,.01,100,MID+3)):
            m.book(p,market(),book(),MID+3,MID+2.9)
        m.book(p,market(),book(),MID+34,MID+33.9)
        self.assertEqual(m.state['positions']['condition-1']['management']['reason'],'EXECUTION_TOO_LATE')
        self.assertEqual(m.state['cash'],'90')
        p,m=seeded()
        with patch.object(p,'_inputs',return_value=(.6,.01,100,MID+3)):
            m.book(p,market(),book(),MID+3,MID+2.9)
        m.market(market(status='RESOLVED',winningOutcomeIndex=1),START+3601)
        self.assertEqual(m.state['positions']['condition-1']['management']['reason'],'RESOLVED_BEFORE_EXECUTION')
        m.validate()

    def test_checkpoints_do_not_sum_and_conflicting_history_has_no_report(self):
        import tempfile,pathlib,json,zipfile
        p,m=seeded()
        with tempfile.TemporaryDirectory() as tmp:
            paths=[]
            for i in range(2):
                path=pathlib.Path(tmp)/f'{i}.zip';paths.append(path)
                with zipfile.ZipFile(path,'w') as z:
                    z.writestr('summary.json',json.dumps({'ended_at':f'2026-10-03T14:0{i}:00Z'}))
                    z.writestr('state.json',json.dumps({'inventory_paper':m.state}))
            r=archive_report(paths);self.assertEqual(r['status'],'RECONCILED_PAPER_ONLY')
            self.assertEqual(r['report']['positions'],1);self.assertEqual(r['report']['cash'],'90')
            reset=InventoryPaper(started_at=MID+1)
            with zipfile.ZipFile(paths[1],'w') as z:
                z.writestr('summary.json',json.dumps({'ended_at':'2026-10-03T14:01:00Z'}))
                z.writestr('state.json',json.dumps({'inventory_paper':reset.state}))
            r=archive_report(paths);self.assertEqual(r['status'],'UNRECONCILED_CHECKPOINTS')
            self.assertIsNone(r['report'])
