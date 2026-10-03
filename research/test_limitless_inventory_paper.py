import copy
import unittest
from unittest.mock import patch
from decimal import Decimal as D
from limitless_inventory_paper import InventoryPaper, value, quote, archive_report, digest, VERSION, HOLDOUT
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
    ep={'condition':'condition-1','slug':'btc-hour','decision_at':MID,'phase':'discovery','start':START,
        'variants':{'model':{'status':'FILLED','side':'YES','fill_at':MID+2,
                            'cost_usdc':'10','net_shares':'24.25'}}}
    p.state['episodes']['condition-1']=ep
    manager=InventoryPaper(started_at=MID-1)
    admit_fixture(manager,ep,market(),MID+2)
    return p,manager


def admit_fixture(manager, ep, mm, observed):
    pending=copy.deepcopy(ep)
    a=pending['variants']['model']
    gross=D(a['net_shares'])/D('.97')
    price=D(a['cost_usdc'])/gross
    a.update(status='PENDING',max_price=str(price),size_cap_shares=str(gross),
             eligible_after=ep['decision_at']+1.5,expires_at=ep['decision_at']+30)
    paper=HourlyPaper();paper.state['episodes'][ep['condition']]=pending
    raw=book(str(price-D('.02')),str(price));raw['tokenId']=mm['tokens']['yes']
    manager.observe_entry_attempt(paper,mm,raw,observed,observed-.5)
    ep['variants']['model']['fill_at']=observed
    return manager.admit(ep,mm,observed)


def write_archive(path,state,ended=MID+100,evidence=True,sources=None):
    import json,zipfile,gzip
    if sources is None:
        sources=[a['source'] for a in state.get('entry_attempts',{}).values()]
        for pos in state['positions'].values():
            a=pos.get('management') or {}
            sources += [s for s in (a.get('source'),a.get('execution_source'),pos.get('settlement_source')) if s]
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('summary.json',json.dumps({'ended_at':ended}))
        z.writestr('state.json',json.dumps({'inventory_paper':state}))
        if evidence:
            rows=''.join(json.dumps({'kind':'inventory_observation','source':s,'source_sha256':digest(s)})+'\n' for s in sources)
            z.writestr('inventory_evidence.jsonl.gz',gzip.compress(rows.encode()))


class InventoryTests(unittest.TestCase):
    def test_execution_rechecks_pair_profit_after_depth_distribution_changes(self):
        from limitless_market_capture import process_book_attempt
        from decimal import ROUND_UP
        p=HourlyPaper();p.market(market(),MID);m=InventoryPaper(started_at=MID-1)
        with patch.object(p,'_inputs',return_value=(.606,.01,100,MID)):
            process_book_attempt(p,m,market(),book('.55','.57'),MID,MID-.1)
        process_book_attempt(p,m,market(),book('.55','.57'),MID+2,MID+1.6)
        pos=m.state['positions']['condition-1']
        size=int((D(pos['entry_net_shares'])*1000000).to_integral_value(rounding=ROUND_UP))
        raw=book('.95','.97');raw['bids'].append({'price':'.58','size':100000000});raw['bids'][0]['size']=size
        with patch.object(p,'_inputs',return_value=(.6,.01,100,MID+3)):
            process_book_attempt(p,m,market(),raw,MID+3,MID+2.9)
        self.assertEqual(pos['management']['action'],'COMPLETE_PAIR')
        before={k:copy.deepcopy(m.state[k]) for k in ('cash','realized_pnl')}
        m.book(p,market(),book('.58','.60'),MID+5,MID+4.6)
        pos=m.state['positions']['condition-1']
        self.assertEqual(pos['management']['reason'],'EXECUTION_PAIR_PROFIT_HURDLE')
        self.assertEqual(pos['management']['status'],'SKIP')
        self.assertNotIn('paper_merge',pos)
        self.assertEqual(before,{k:m.state[k] for k in before});m.validate()
        m.book(p,market(),raw,MID+6,MID+5.6)
        self.assertEqual(pos['management']['status'],'SKIP')

    def test_sell_rechecks_total_proceeds_with_unchanged_worst_price(self):
        p,m=seeded();raw=book('.8','.82');raw['bids'][0]['size']=15000000
        raw['bids'].append({'price':'.4','size':100000000})
        with patch.object(p,'_inputs',return_value=(.6,.01,100,MID+3)):
            m.book(p,market(),raw,MID+3,MID+2.9)
        self.assertEqual(m.state['positions']['condition-1']['management']['action'],'SELL')
        m.book(p,market(),book('.4','.42'),MID+5,MID+4.6)
        self.assertEqual(m.state['positions']['condition-1']['management']['reason'],'EXECUTION_INCREMENTAL_VALUE')
        self.assertEqual(m.state['cash'],'90');m.validate()

    def test_ledger_rejects_invented_pnl_quantities_and_spending(self):
        _,m=seeded()
        for mutation in ('pnl','quantity','basis','spent'):
            bad=copy.deepcopy(m.state);pos=bad['positions']['condition-1']
            if mutation=='pnl':bad.update(cash='95',realized_pnl='5')
            if mutation=='quantity':pos['quantity']['YES']='30'
            if mutation=='basis':pos['basis']['YES']='11';bad['cash']='89'
            if mutation=='spent':pos['spent_total']='9'
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):InventoryPaper(bad)

    def test_nonfinite_or_early_settlement_does_not_mutate_state(self):
        _,m=seeded();before=copy.deepcopy(m.state)
        for at in (float('nan'),float('inf'),float('-inf'),START+3599,True,'2026-10-03'):
            self.assertFalse(m.market(market(status='RESOLVED',winningOutcomeIndex=0),at))
            self.assertEqual(m.state,before)
        bad=copy.deepcopy(m.state);bad['positions']['condition-1']['settled_at']=float('nan')
        with self.assertRaises(ValueError):InventoryPaper(bad)
        self.assertFalse(m.market(market(status='RESOLVED',winningOutcomeIndex=0,payoutNumerators=[0,1]),START+3601))
        self.assertEqual(m.state,before)

    def test_restored_entry_attempt_times_are_all_finite_and_ordered(self):
        _,m=seeded()
        for field in ('observed','requested','decision_at','eligible_after','expires_at'):
            bad=copy.deepcopy(m.state);bad['entry_attempts']['condition-1'][field]=float('nan')
            with self.subTest(field=field),self.assertRaises(ValueError):InventoryPaper(bad)
        bad=copy.deepcopy(m.state);bad['entry_attempts']['condition-1']['expires_at']+=1
        with self.assertRaises(ValueError):InventoryPaper(bad)

    def test_phase_pnl_keeps_negative_holdout_visible(self):
        _,m=seeded();m.market(market(status='RESOLVED',winningOutcomeIndex=0),START+3601)
        start=HOLDOUT+13*3600;mm=market(slug='holdout',conditionId='holdout',startAt=start,expirationTimestamp=(start+3600)*1000)
        mm['metadata']['chart']['windowOpenAt']=start
        ep={'condition':'holdout','slug':'holdout','decision_at':start+1800,
            'variants':{'model':{'status':'FILLED','side':'YES','cost_usdc':'10','net_shares':'24.25'}}}
        admit_fixture(m,ep,mm,start+1802)
        mm.update(status='RESOLVED',winningOutcomeIndex=1);m.market(mm,start+3601)
        r=m.report();self.assertEqual(D(r['managed_settled_pnl']),D('4.25'))
        self.assertEqual(D(r['phases']['discovery']['managed_settled_pnl']),D('14.25'))
        self.assertEqual(D(r['phases']['holdout']['managed_settled_pnl']),D('-10'))
        self.assertEqual(r['phases']['holdout']['matched_conditions'],1)
        self.assertEqual(D(r['phases']['holdout']['managed_minus_seed_hold']),0)

    def test_archive_rejects_rewritten_pending_order_or_missing_raw_source(self):
        import tempfile,pathlib
        p,m=seeded()
        with patch.object(p,'_inputs',return_value=(.6,.01,100,MID+3)):
            m.book(p,market(),book(),MID+3,MID+2.9)
        with tempfile.TemporaryDirectory() as tmp:
            a,b=pathlib.Path(tmp)/'a.zip',pathlib.Path(tmp)/'b.zip'
            write_archive(a,m.state)
            changed=copy.deepcopy(m.state);changed['positions']['condition-1']['management']['quantity']='1'
            write_archive(b,changed,ended=MID+101)
            r=archive_report([a,b]);self.assertEqual(r['status'],'UNRECONCILED_CHECKPOINTS');self.assertIsNone(r['report'])
            write_archive(b,m.state,evidence=False)
            r=archive_report([b]);self.assertIsNone(r['report'])
            self.assertTrue(any('RAW_EVIDENCE' in e['error'] for e in r['errors']))

    def test_archive_same_time_conflicts_and_asof_and_version_isolation(self):
        import tempfile,pathlib
        p,m=seeded()
        with tempfile.TemporaryDirectory() as tmp:
            a,b,c=[pathlib.Path(tmp)/f'{k}.zip' for k in 'abc']
            write_archive(a,m.state)
            with patch.object(p,'_inputs',return_value=(.95,.01,100,MID+3)):
                m.book(p,market(),book(),MID+3,MID+2.9)
            write_archive(b,m.state)
            r=archive_report([a,b]);self.assertIsNone(r['report'])
            self.assertTrue(any(e['error']=='SAME_TIME_CHECKPOINT_CHANGED' for e in r['errors']))
            write_archive(b,m.state,ended=MID+101)
            r=archive_report([a,b],as_of=MID+100);self.assertEqual(r['checkpoints'],1)
            self.assertEqual(r['report']['management_states'],{'AWAITING_NEXT_BOOK':1})
            old={'version':'limitless-inventory-paper-v1','positions':{},'cash':'999','realized_pnl':'899','started_at':MID-1}
            write_archive(c,old)
            r=archive_report([a,c]);self.assertEqual(r['status'],'RECONCILED_PAPER_ONLY')
            self.assertEqual(r['legacy_v1_checkpoints_excluded'],1);self.assertEqual(r['report']['cash'],'90')

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
            admit_fixture(m,ep,market(conditionId=str(i),slug=str(i)),MID+3)
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
                write_archive(path,m.state,ended=MID+100+i)
            r=archive_report(paths);self.assertEqual(r['status'],'RECONCILED_PAPER_ONLY')
            self.assertEqual(r['report']['positions'],1);self.assertEqual(r['report']['cash'],'90')
            reset=InventoryPaper(started_at=MID+1)
            write_archive(paths[1],reset.state,ended=MID+101)
            r=archive_report(paths);self.assertEqual(r['status'],'UNRECONCILED_CHECKPOINTS')
            self.assertIsNone(r['report'])
