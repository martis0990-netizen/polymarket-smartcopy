import sys, unittest, datetime as dt
from pathlib import Path
from decimal import Decimal
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'))
from limitless_hourly_proper_betting import compare, sized, quote, archive_report

START=dt.datetime(2026,10,5,0,tzinfo=dt.timezone.utc).timestamp()
def row(kind,t,**kw):return {'kind':kind,'observed_at':t,'_run':1,'_ordinal':int(t),**kw}
def market(status='FUNDED',winner=None):
 return {'tradeType':'clob','slug':'s','conditionId':'c','startAt':START,'expirationTimestamp':(START+3600)*1000,
 'collateralToken':{'symbol':'USDC','decimals':6},'tokens':{'yes':'y'},'metadata':{'openPrice':'100',
 'chart':{'source':'binance','market':'spot','candle':'hourly','symbol':'BTCUSDT','windowOpenAt':START}},'status':status,'winningOutcomeIndex':winner}
def book():return {'tokenId':'y','asks':[{'price':'.50','size':100000000}], 'bids':[{'price':'.49','size':100000000}]}
def records():
 ep={'condition':'c','slug':'s','start':START,'decision_at':START+1800.1,'p_up':.7,
 'variants':{'model':{'status':'PENDING','side':'YES','max_price':'.65','size_cap_shares':'15',
 'eligible_after':START+1801.1,'expires_at':START+1830.1}}}
 return [row('market',START+1,raw=market()),row('book',START+1800,slug='s',raw=book(),requested_at=START+1799),
 row('paper_decision',START+1800.2,episode=ep),row('book',START+1815,slug='s',raw=book(),requested_at=START+1814),
 row('market',START+3601,raw=market('RESOLVED',0))]
class Tests(unittest.TestCase):
 def test_size_is_shares_and_bound(self):
  a={'side':'YES','size_cap_shares':'15'}
  self.assertEqual(sized(a,.7,Decimal('.495')),Decimal('4.100000'))
  self.assertEqual(sized({**a,'size_cap_shares':'1'},.7,Decimal('.495')),Decimal('1.000000'))
  self.assertIsNone(sized(a,.3,Decimal('.495')))
 def test_payout_cash_and_cumulative_dedup(self):
  r=records();x=compare(r,START+4000);self.assertEqual(x['conditions'],1)
  for name,a in x['report'].items():
   self.assertEqual(Decimal(a['cash_usdc']),Decimal('100')+Decimal(a['settled_pnl_usdc']))
  self.assertEqual(x['report']['brier_sizing']['settled_spend_usdc'],'2.05000000')
  self.assertEqual(compare(r+[row('market',START+3602,raw=market('RESOLVED',0))],START+4000)['report'],x['report'])
 def test_first_failure_never_replaced(self):
  r=records();r.insert(3,row('request_error',START+1802,slug='s',requested_at=START+1801.5,operation='book'))
  x=compare(r,START+4000)
  self.assertTrue(all(a['states']=={'SKIP':1} for a in x['report'].values()))
  self.assertTrue(all(a['cash_usdc']=='100' for a in x['report'].values()))
 def test_future_resolution_excluded_and_open_basis(self):
  x=compare(records(),START+2000)
  self.assertTrue(all(a['states']=={'FILLED':1} for a in x['report'].values()))
  self.assertTrue(all(Decimal(a['cash_usdc'])+Decimal(a['open_cost_basis_usdc'])==100 for a in x['report'].values()))
 def test_conflict_null_report(self):
  r=records();r.append(row('market',START+3602,raw=market('RESOLVED',1)))
  self.assertIsNone(compare(r,START+4000)['report'])
 def test_last_settlement_updates_drawdown(self):
  r=records();r[-1]['raw']=market('RESOLVED',1)
  x=compare(r,START+4000)
  self.assertEqual(x['report']['fixed']['max_settled_equity_drawdown_usdc'],'7.50')
 def test_prospective_start_does_not_import_old_trades(self):
  x=compare(records(),START+4000,started_at=START+3600)
  self.assertEqual(x['conditions'],0)
  self.assertTrue(all(a['cash_usdc']=='100' for a in x['report'].values()))
 def test_archive_digest_and_main_gate(self):
  import tempfile
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'bad.zip';p.write_bytes(b'bad')
   e={'run':{'id':1,'name':'Limitless independent market capture','head_branch':'main','event':'push','status':'completed','conclusion':'success'},'artifact':{'digest':'sha256:wrong'},'file':{'path':str(p)}}
   with self.assertRaisesRegex(ValueError,'ARTIFACT_DIGEST_MISMATCH'):archive_report([e],START)
   e['run']['event']='pull_request'
   with self.assertRaisesRegex(ValueError,'NOT_MAIN_SUCCESS'):archive_report([e],START)
 def test_wrong_token_and_crossed_book(self):
  with self.assertRaises(ValueError):quote({**book(),'tokenId':'wrong'},'y')
  with self.assertRaises(ValueError):quote({**book(),'bids':[{'price':'.7','size':100000000}]},'y')
if __name__=='__main__':unittest.main()
