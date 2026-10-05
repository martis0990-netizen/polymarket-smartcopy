#!/usr/bin/env python3
"""Offline gated Brier-inspired sizing comparison; no trading or network."""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import math
import zipfile
from collections import Counter
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from limitless_hourly_paper import spec, levels, fill, FEE, MICRO

VERSION='limitless-hourly-brier-sizing-v1'
SCALE=Decimal('10')  # shares per unit signed Brier exposure; fixed before replay


def when(x):
    if isinstance(x,(int,float)):
        if not math.isfinite(x):raise ValueError('NONFINITE_TIME')
        return float(x)
    t=dt.datetime.fromisoformat(x.replace('Z','+00:00'))
    if t.tzinfo is None:raise ValueError('NAIVE_TIME')
    return t.timestamp()


def fingerprint(x):
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def quote(book,token):
    if not isinstance(book,dict) or book.get('tokenId')!=token:raise ValueError('BOOK_IDENTITY')
    asks,noasks=levels(book,'YES'),levels(book,'NO')
    if not asks or not noasks or asks[0][0]+noasks[0][0]<1:raise ValueError('INVALID_BOOK')
    return (asks[0][0]+1-noasks[0][0])/2


def sized(action,p,q):
    gap=Decimal(str(p))-q
    direction='YES' if gap>0 else 'NO' if gap<0 else None
    if direction!=action['side']:return None
    return min(Decimal(action['size_cap_shares']),2*SCALE*abs(gap)).quantize(MICRO,rounding=ROUND_DOWN)


def payout(m):
    winner=m.get('winningOutcomeIndex')
    if type(winner) is int and winner in (0,1):return [Decimal(int(winner==0)),Decimal(int(winner==1))]
    nums=[Decimal(str(x)) for x in m.get('payoutNumerators',[])]
    if len(nums)==2 and all(x.is_finite() and x>=0 for x in nums) and sum(nums)>0:return [x/sum(nums) for x in nums]
    return None


def compare(rows,as_of,started_at=None):
    cutoff=when(as_of);markets={};books={};episodes={};conflicts=[]
    accounts={name:{'cash':Decimal('100'),'ledger':[],'peak':Decimal('100'),'max_settled_equity_drawdown':Decimal(0)}
              for name in ('fixed','brier_sizing')}
    def cash_event(name,condition,amount,kind,t,source):
        a=accounts[name];a['cash']+=amount
        if a['cash']<0:raise ValueError('BORROWING')
        a['ledger'].append({'condition':condition,'kind':kind,'time':t,'amount':str(amount),
                           'cash_after':str(a['cash']),'source':source})
    def mark_equity():
        for name,account in accounts.items():
            open_cost=sum((Decimal(e['actions'].get(name,{}).get('cost_usdc','0')) for e in episodes.values()
                           if e['actions'].get(name,{}).get('status')=='FILLED'),Decimal(0))
            equity=account['cash']+open_cost;account['peak']=max(account['peak'],equity)
            account['max_settled_equity_drawdown']=max(account['max_settled_equity_drawdown'],account['peak']-equity)
    for row in sorted(rows,key=lambda r:(when(r['observed_at']),r['_run'],r['_ordinal'])):
        t=when(row['observed_at'])
        if t>cutoff:continue
        kind=row['kind'];raw=row.get('raw');slug=row.get('slug');source=fingerprint({k:v for k,v in row.items() if not k.startswith('_')})
        if kind=='market' and isinstance(raw,dict):
            s=spec(raw)
            if s is None:continue
            prior=markets.get(s['slug'])
            if prior and any(prior[k]!=s[k] for k in ('condition','start','end','opening','symbol','yes_token','delay_s')):
                conflicts.append({'condition':s['condition'],'reason':'MARKET_CONFLICT'});continue
            markets[s['slug']]=s
            ep=episodes.get(s['condition'])
            if raw.get('status')!='RESOLVED' or t<s['end'] or ep is None:continue
            pay=payout(raw)
            if pay is None:continue
            if 'payout' in ep:
                if ep['payout']!=list(map(str,pay)):conflicts.append({'condition':s['condition'],'reason':'PAYOUT_CONFLICT'})
                continue
            ep['payout']=list(map(str,pay));ep['settled_at']=t
            if pay in ([Decimal(1),Decimal(0)],[Decimal(0),Decimal(1)]):
                y=float(pay[0]);ep['brier_model']=(ep['p_up']-y)**2
                if ep.get('q') is not None:ep['brier_market']=(float(ep['q'])-y)**2
            for name,action in ep['actions'].items():
                if action['status']=='FILLED':
                    paid=Decimal(action['net_shares'])*pay[0 if action['side']=='YES' else 1]
                    cash_event(name,s['condition'],paid,'PAYOUT',t,source)
                    action.update(status='SETTLED',payout_usdc=str(paid),pnl_usdc=str(paid-Decimal(action['cost_usdc'])))
                elif action['status']=='PENDING':action.update(status='SKIP',reason='RESOLVED_BEFORE_ATTEMPT')
            mark_equity()
            continue
        if kind=='paper_decision':
            original=row['episode'];condition=original['condition']
            if started_at is not None and when(original['start'])<when(started_at):continue
            if condition in episodes:
                if episodes[condition]['decision_identity']!=fingerprint(original):conflicts.append({'condition':condition,'reason':'DECISION_CONFLICT'})
                continue
            p=float(original['p_up'])
            if not math.isfinite(p) or not 0<=p<=1:raise ValueError('INVALID_PROBABILITY')
            ep={'condition':condition,'slug':original['slug'],'start':original['start'],'decision_at':original['decision_at'],
                'p_up':p,'actions':{},'decision_identity':fingerprint(original),'decision_source':source}
            episodes[condition]=ep
            base=original['variants']['model'];s=markets.get(ep['slug']);b=books.get(ep['slug'])
            try:
                if s is None or s['condition']!=condition or b is None:raise ValueError('MISSING_CAUSAL_BOOK_OR_METADATA')
                if not 0<=when(original['decision_at'])-when(b['observed_at'])<=1:raise ValueError('DECISION_BOOK_RECEIPT_MISMATCH')
                q=quote(b['raw'],s['yes_token']);ep['q']=str(q);ep['decision_book_source']=fingerprint(b)
            except (ValueError,TypeError,KeyError,ArithmeticError) as error:
                ep['actions']={name:{'status':'SKIP','reason':str(error)} for name in accounts};continue
            if base['status']!='PENDING':
                ep['actions']={name:{'status':'NO_TRADE','reason':'FROZEN_MODEL_NO_TRADE'} for name in accounts};continue
            ep['token']=s['yes_token'];ep['end']=s['end'];ep['eligible_after']=base['eligible_after'];ep['expires_at']=base['expires_at']
            for name in accounts:
                qty=Decimal(base['size_cap_shares']) if name=='fixed' else sized(base,p,q)
                ep['actions'][name]={'status':'PENDING','side':base['side'],'max_price':base['max_price'],'size_cap_shares':str(qty)} if qty else {'status':'SKIP','reason':'ZERO_SIZE_OR_DIRECTION_MISMATCH'}
            continue
        if kind=='book':books[slug]=row
        if kind!='book' and not (kind=='request_error' and row.get('operation')=='book'):continue
        requested=when(row['requested_at'])
        if requested>t:raise ValueError('REQUEST_AFTER_RECEIPT')
        for ep in episodes.values():
            if ep['slug']!=slug or requested<ep.get('eligible_after',math.inf):continue
            for name,a in ep['actions'].items():
                if a['status']!='PENDING':continue
                a.update(first_attempt_requested=requested,first_attempt_received=t,execution_source=source)
                try:
                    if t>ep['expires_at'] or t>=ep['end']:raise ValueError('EXECUTION_TOO_LATE')
                    quote(raw,ep['token'])
                    result=fill(raw,a['side'],Decimal(a['max_price']),Decimal(a['size_cap_shares']))
                    if result is None:raise ValueError('PRICE_OR_DEPTH')
                    cost=Decimal(result['cost_usdc'])
                    if cost>accounts[name]['cash']:raise ValueError('INSUFFICIENT_CASH')
                    cash_event(name,ep['condition'],-cost,'ENTRY',t,source)
                    a.update(status='FILLED',fill_at=t,**result)
                except (ValueError,TypeError,KeyError,ArithmeticError) as error:a.update(status='SKIP',reason=str(error))
        # Cost-basis equity drawdown only; never claim marked-to-market risk.
        mark_equity()
    summary={}
    for name,account in accounts.items():
        actions=[e['actions'][name] for e in episodes.values()];settled=[a for a in actions if a['status']=='SETTLED']
        spent=sum((Decimal(a['cost_usdc']) for a in settled),Decimal(0));pnl=sum((Decimal(a['pnl_usdc']) for a in settled),Decimal(0))
        open_cost=sum((Decimal(a['cost_usdc']) for a in actions if a['status']=='FILLED'),Decimal(0))
        if account['cash']+open_cost!=Decimal('100')+pnl:raise ValueError('CASH_RECONCILIATION')
        summary[name]={'states':dict(Counter(a['status'] for a in actions)),'skip_reasons':dict(Counter(a.get('reason') for a in actions if a.get('reason'))),
            'cash_usdc':str(account['cash']),'open_cost_basis_usdc':str(open_cost),'settled_pnl_usdc':str(pnl),
            'settled_spend_usdc':str(spent),'return_on_settled_spend':str(pnl/spent) if spent else None,
            'max_settled_equity_drawdown_usdc':str(account['max_settled_equity_drawdown']),'ledger':account['ledger']}
    scored=[e for e in episodes.values() if 'brier_market' in e]
    matched=[e for e in episodes.values() if 'payout' in e]
    matched_delta=sum((Decimal(e['actions']['brier_sizing'].get('pnl_usdc','0'))-Decimal(e['actions']['fixed'].get('pnl_usdc','0')) for e in matched),Decimal(0))
    result={'matched_resolved_conditions':len(matched),'matched_brier_minus_fixed_pnl_usdc':str(matched_delta),'version':VERSION,'status':'UNRECONCILED' if conflicts else 'DISCOVERY_ONLY','report':None if conflicts else summary,
        'comparison_started_at':started_at,'as_of':as_of,'conditions':len(episodes),'hour_clusters':len({e['start'] for e in episodes.values()}),
        'scored_conditions':len(scored),'brier_model':sum(e['brier_model'] for e in scored)/len(scored) if scored else None,
        'brier_market_mid':sum(e['brier_market'] for e in scored)/len(scored) if scored else None,
        'holdout_conditions':sum(e['start']>=when('2026-10-06T00:00:00Z') for e in episodes.values()),
        'conflicts':conflicts,'episodes':list(episodes.values()),'limitations':['Gated Brier-inspired sizing, not the theorem strategy',
        'Midpoint is a probability reference only, never a fill','First actual request only; hourly missing-frame retry is not inherited',
        'Drawdown uses settled equity plus open cost basis, not liquidation value','No fees/threshold/holdout/capture changes']}
    return result


def archive_report(manifest,as_of,started_at=None):
    rows=[];lineage=[];seen=set()
    for entry in manifest:
        run,art=entry['run'],entry['artifact']
        if run['id'] in seen:raise ValueError('DUPLICATE_RUN')
        seen.add(run['id'])
        if run['head_branch']!='main' or run['event']=='pull_request' or run['status']!='completed' or run['conclusion']!='success' or run['name']!='Limitless independent market capture':raise ValueError('NOT_MAIN_SUCCESS')
        path=Path(entry['file']['path']);sha=hashlib.sha256(path.read_bytes()).hexdigest()
        if art['digest']!='sha256:'+sha:raise ValueError('ARTIFACT_DIGEST_MISMATCH')
        with zipfile.ZipFile(path) as z:
            summary=json.loads(z.read('summary.json'))
            lineage.append({'run_id':run['id'],'artifact_id':art['id'],'sha256':sha,'start':summary['started_at'],'end':summary['ended_at']})
            with gzip.GzipFile(fileobj=z.open('capture.jsonl.gz')) as f:
                for i,line in enumerate(f):
                    r=json.loads(line)
                    if r['kind'] in ('market','book','paper_decision','request_error'):
                        r.update(_run=run['id'],_ordinal=i);rows.append(r)
    result=compare(rows,as_of,started_at);result['archives']=sorted(lineage,key=lambda x:x['start'])
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest',required=True);parser.add_argument('--as-of',required=True);parser.add_argument('--out',required=True)
    parser.add_argument('--start',help='Fresh account eligibility start; market open must be at/after it')
    a=parser.parse_args()
    try:result=archive_report(json.loads(Path(a.manifest).read_text()),a.as_of,a.start)
    except (ValueError,KeyError,TypeError,ArithmeticError,OSError,zipfile.BadZipFile) as error:result={'version':VERSION,'status':'UNRECONCILED','report':None,'error':str(error)}
    Path(a.out).write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('episodes','archives','report')}))
    if result['status']=='UNRECONCILED':raise SystemExit(1)

if __name__=='__main__':main()
