#!/usr/bin/env python3
"""Replay frozen and EWMA30 decisions on identical public first-attempt books; never writes paper state."""
import argparse,json,zipfile,gzip,datetime,hashlib,collections
from decimal import Decimal as D,ROUND_DOWN
from limitless_hourly_paper import fill,levels,FEE,BUDGET,HURDLE,MICRO
parser=argparse.ArgumentParser(description='Offline, separate-funded EWMA30/frozen replay on pinned hourly shadow decisions')
parser.add_argument('manifest')
parser.add_argument('shadow_evidence')
parser.add_argument('--out',required=True)
args=parser.parse_args()
manifest=json.load(open(args.manifest))
trial=json.load(open(args.shadow_evidence))
if trial.get('schema')!='limitless-hourly-ewma30-shadow-v1' or len(manifest)!=len(trial['source_archives']):raise ValueError('unverified shadow sources')
for item,source in zip(manifest,trial['source_archives']):
 if item['artifact']['id']!=source['artifact'] or hashlib.sha256(open(item['file']['path'],'rb').read()).hexdigest()!=source['sha256']:raise ValueError('ZIP digest or lineage mismatch')
with zipfile.ZipFile(manifest[-1]['file']['path']) as z:s=json.loads(z.read('state.json'))['paper']
rows={x['slug']:x for x in trial['rows']};events=collections.defaultdict(list);decisions={}
for item in manifest:
 art=item['artifact']['id']
 with zipfile.ZipFile(item['file']['path']) as z,gzip.GzipFile(fileobj=z.open('capture.jsonl.gz')) as f:
  for n,line in enumerate(f,1):
   if b'"kind":"book"' not in line and b'"kind":"request_error"' not in line:continue
   x=json.loads(line);slug=x.get('slug')
   if slug not in rows or (x['kind']=='request_error' and x.get('operation')!='book'):continue
   proof={'artifact':art,'line':n,'sha256':hashlib.sha256(line.rstrip(b'\n')).hexdigest()}
   if proof==rows[slug]['proof']:decisions[slug]=(x,proof)
   elif x['kind']=='book' or x.get('operation')=='book':events[slug].append((x,proof))
assert len(decisions)==len(rows)
def timestamp(value):return datetime.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()
def opportunity(book,p):
 choices=[]
 for side,chance in [('YES',p),('NO',1-p)]:
  cap=D(str(chance))*(1-FEE)/(1+HURDLE)
  if cap<=0:continue
  qty=(BUDGET/cap).quantize(MICRO,rounding=ROUND_DOWN)
  a=fill(book,side,cap,qty)
  if a:
   edge=D(a['net_shares'])*D(str(chance))/D(a['cost_usdc'])-1
   choices.append((edge,side,cap,qty))
 return max(choices,key=lambda x:(x[0],x[1])) if choices else None

def replay(name):
 account={'cash':D(100),'spent':D(0),'payouts':D(0),'realized':D(0),'positions':{},'rows':[]}
 actions=[]
 for slug,row in rows.items():
  e=s['episodes'][row['condition']];spec=s['markets'][slug];book=decisions[slug][0]['raw']
  assert book['tokenId']==spec['yes_token']
  yes,no=levels(book,'YES'),levels(book,'NO')
  assert yes and no and yes[0][0]+no[0][0]>=1
  p=row['p_up'] if name=='frozen' else row['p_ewma30']
  choice=opportunity(book,p)
  a={'condition':e['condition'],'slug':slug,'symbol':e['symbol'],'hour_start':e['start'],'p_up':p,
     'decision_at':e['decision_at'],'status':'NO_TRADE' if not choice else 'PENDING'}
  if choice:
   _,side,cap,qty=choice;a.update(side=side,cap=str(cap),shares=str(qty))
   eligible=e['decision_at']+spec['delay_s'];attempts=[]
   for raw,proof in events[slug]:
    requested=timestamp(raw['requested_at']);received=timestamp(raw['observed_at'])
    if requested>=eligible:attempts.append((requested,received,raw,proof))
   attempts.sort(key=lambda x:(x[0],x[1]))
   if not attempts or attempts[0][1]>e['decision_at']+30:
    a.update(status='SKIP',reason='MISSED_FIRST_ATTEMPT')
   else:
    _,at,raw,proof=attempts[0]
    a['execution_proof']=proof
    if raw['kind']=='request_error':a.update(status='SKIP',reason='FIRST_ERROR')
    else:
     b=raw['raw'];ys,ns=levels(b,'YES'),levels(b,'NO')
     if b.get('tokenId')!=spec['yes_token'] or not ys or not ns or ys[0][0]+ns[0][0]<1:
      a.update(status='SKIP',reason='INVALID_EXECUTION_BOOK')
     else:
      trade=fill(b,side,cap,qty)
      if not trade:a.update(status='SKIP',reason='DEPTH_OR_PRICE_BOUND_FAILED')
      else:a.update(status='READY',fill_at=at,**trade)
  actions.append((e,a))
 transitions=[]
 for e,a in actions:
  if a['status']=='READY':transitions.append((a['fill_at'],1,e,a))
  if e.get('settled_at'):transitions.append((e['settled_at'],0,e,a))
 for _,kind,e,a in sorted(transitions,key=lambda x:(x[0],x[1],x[2]['condition'])):
  if kind==1:
   cost=D(a['cost_usdc'])
   if cost>account['cash']:
    a.update(status='NO_TRADE',reason='INSUFFICIENT_CASH');continue
   account['cash']-=cost;account['spent']+=cost;a['status']='FILLED'
   account['positions'][e['condition']]=(D(a['net_shares']),cost,a['side'])
  else:
   pos=account['positions'].get(e['condition'])
   if pos and a['status']=='FILLED':
    net,cost,side=pos;win=D(str(e['payout'][0 if side=='YES' else 1]));payout=net*win
    account['cash']+=payout;account['payouts']+=payout;account['realized']+=payout-cost
    a.update(status='SETTLED',payout_usdc=str(payout),pnl_usdc=str(payout-cost))
 account['rows']=[a for _,a in actions]
 pending=sum((D(a['cost_usdc']) for a in account['rows'] if a['status']=='FILLED'),D(0))
 assert account['cash']+pending==D(100)+account['realized']
 return {'cash':str(account['cash']),'spent':str(account['spent']),'payouts':str(account['payouts']),
         'realized':str(account['realized']),'pending_cost':str(pending),'states':dict(collections.Counter(a['status'] for a in account['rows'])),'rows':account['rows']}
base=replay('frozen');alt=replay('ewma30')
for row in base['rows']:
 e=s['episodes'][row['condition']];a=e['variants']['model'];assert row['status']==a['status'],(row['slug'],row['status'],a['status'])
 if row['status']=='SETTLED':assert D(row['cost_usdc'])==D(a['cost_usdc']) and D(row['pnl_usdc'])==D(a['pnl_usdc'])
result={'schema':'limitless-hourly-ewma30-frozen-cohort-shadow-pnl-v1','scope':'matched decisions in pinned shadow evidence only','funding':'separate 100 USDC each at first matched decision','baseline_exact_action_reproduction':len(base['rows']),'source_archives':trial['source_archives'],'frozen':base,'ewma30':alt}
with open(args.out,'w') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
print(json.dumps({n:{k:v for k,v in result[n].items() if k!='rows'} for n in ('frozen','ewma30')}))
