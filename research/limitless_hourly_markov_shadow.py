#!/usr/bin/env python3
"""Read-only two-state observable volatility Markov comparison, same event/attempt."""
import argparse
import collections
import datetime as dt
import decimal
import gzip
import hashlib
import json
import math
import os
import pathlib
import statistics
import zipfile

from limitless_hourly_paper import BUDGET,FEE,HURDLE,MICRO,fill,levels,probability
from limitless_hourly_paired_attempt import download,good_book

D=decimal.Decimal
ROOT=pathlib.Path(__file__).resolve().parents[1]
EVENT=ROOT/'research/limitless_hourly_event_trigger_2026-10-08.json'
SOURCE=ROOT/'research/evidence/limitless_hourly_all_decisions_2026-10-07.json'


def seconds(value):
    return dt.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def markov_probability(candles,current,opening,now,available_before,end):
    cutoff=min(now,available_before)
    closed=sorted((r for r in candles if float(r[6])/1000<cutoff),key=lambda r:r[0])[-121:]
    if len(closed)!=121 or any(int(b[0])-int(a[0])!=60000 for a,b in zip(closed,closed[1:])):
        raise ValueError('MISSING_CLOSED_WARMUP')
    if now-float(closed[-1][6])/1000>120:raise ValueError('STALE_CANDLES')
    closes=[float(r[4]) for r in closed]
    if not all(math.isfinite(p) and p>0 for p in closes):raise ValueError('INVALID_CANDLES')
    returns=[math.log(b/a) for a,b in zip(closes,closes[1:])]
    boundary=statistics.median(abs(r) for r in returns)
    states=[int(abs(r)>boundary) for r in returns]
    variance=[]
    for regime in (0,1):
        vals=[r*r for r,s in zip(returns,states) if s==regime]
        if not vals:raise ValueError('EMPTY_VOLATILITY_REGIME')
        variance.append(statistics.mean(vals))
    transitions=[[1,1],[1,1]]
    for a,b in zip(states,states[1:]):transitions[a][b]+=1
    matrix=[[count/sum(transitions[state]) for count in transitions[state]] for state in (0,1)]
    remaining=(end-now)/60
    if remaining<=0:raise ValueError('EXPIRED_MARKET')
    distribution=[0.0,0.0];distribution[states[-1]]=1.0
    total_variance=0.0
    while remaining>0:
        distribution=[distribution[0]*matrix[0][0]+distribution[1]*matrix[1][0],
                      distribution[0]*matrix[0][1]+distribution[1]*matrix[1][1]]
        weight=min(1.0,remaining)
        total_variance+=weight*sum(p*v for p,v in zip(distribution,variance))
        remaining-=weight
    if total_variance<=0 or not math.isfinite(total_variance):raise ValueError('INVALID_FORECAST_VARIANCE')
    z=math.log(current/float(opening))/math.sqrt(total_variance)
    return .5*(1+math.erf(z/math.sqrt(2))),variance,matrix,states[-1],total_variance


def select(book,p):
    choices=[]
    for side,chance in (('YES',p),('NO',1-p)):
        cap=D(str(chance))*(1-FEE)/(1+HURDLE)
        if cap<=0:continue
        gross=(BUDGET/cap).quantize(MICRO,rounding=decimal.ROUND_DOWN)
        simulated=fill(book,side,cap,gross)
        if simulated:
            edge=float(D(simulated['net_shares'])*D(str(chance))/D(simulated['cost_usdc'])-1)
            choices.append((edge,side,cap,gross))
    return max(choices,key=lambda x:(x[0],x[1])) if choices else None


def summarize(rows):
    out={}
    for phase in ('discovery','holdout'):
        all_rows=[r for r in rows if r['phase']==phase]
        valid=[r for r in all_rows if r['p_markov'] is not None]
        scored=[r for r in valid if r['outcome_yes'] in (0,1)]
        filled=[r for r in valid if r['status']=='FILLED']
        pnls=sorted((D(r['settled_markov_pnl_usdc']) for r in filled if r['settled_markov_pnl_usdc'] is not None),reverse=True)
        allpnls=[D(r['settled_markov_pnl_usdc']) if r['settled_markov_pnl_usdc'] is not None else D(0) for r in all_rows]
        basepnls=[D(r['settled_baseline_pnl_usdc']) if r['settled_baseline_pnl_usdc'] is not None else D(0) for r in all_rows]
        out[phase]={'conditional_first_opportunities':len(all_rows),'valid_markov_forecasts':len(valid),
            'scored_binary_forecasts':len(scored),'skips':dict(collections.Counter(r['reason'] for r in all_rows if r['status']!='FILLED')),
            'markov_brier':statistics.mean((r['p_markov']-r['outcome_yes'])**2 for r in scored) if scored else None,
            'frozen_brier_same_events':statistics.mean((r['p_frozen']-r['outcome_yes'])**2 for r in scored) if scored else None,
            'markov_log_loss':statistics.mean(-r['outcome_yes']*math.log(max(1e-12,min(1-1e-12,r['p_markov'])))-(1-r['outcome_yes'])*math.log(max(1e-12,min(1-1e-12,1-r['p_markov']))) for r in scored) if scored else None,
            'frozen_log_loss_same_events':statistics.mean(-r['outcome_yes']*math.log(max(1e-12,min(1-1e-12,r['p_frozen'])))-(1-r['outcome_yes'])*math.log(max(1e-12,min(1-1e-12,1-r['p_frozen']))) for r in scored) if scored else None,
            'markov_paper_fills':len(filled),'markov_paper_wins':sum(v>0 for v in pnls),
            'markov_settled_pnl_usdc':str(sum(allpnls,D(0))),
            'frozen_settled_pnl_same_events_usdc':str(sum(basepnls,D(0))),
            'markov_top_two_pnl_usdc':[str(p) for p in pnls[:2]],
            'markov_pnl_excluding_top_two_usdc':str(sum(pnls[2:],D(0))),
            'active_hour_clusters':len({r['hour_cluster'] for r in filled})}
    return out


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='markov_shadow_evidence.json')
    parser.add_argument('--cache',default='artifact-cache')
    args=parser.parse_args()
    event=json.loads(EVENT.read_text())
    manifest=json.loads(SOURCE.read_text())['archive_zip_digests']
    assert len(manifest)==96 and len(event['rows'])==162
    rows=[r for r in event['rows'] if r['decision'] is not None]
    targets=collections.defaultdict(list)
    for row in rows:
        d=row['decision'];condition=row['condition']
        for role,location in [('minute',d['minute_reference']),('hour',d['hour_reference']),('book',d),('attempt',row['entry'])]:
            if location:targets[(location['artifact'],location['line'])].append((condition,role))
    seen={};cache=pathlib.Path(args.cache);cache.mkdir(exist_ok=True)
    state=None
    for index,item in enumerate(manifest,1):
        aid=item['artifact'];path=cache/f'{aid}.zip'
        download(aid,path,item['zip_sha256'],os.environ['GITHUB_TOKEN'])
        with zipfile.ZipFile(path) as archive:
            if aid==manifest[-1]['artifact']:state=json.loads(archive.read('state.json'))['paper']
            with gzip.GzipFile(fileobj=archive.open('capture.jsonl.gz')) as stream:
                for line_number,line in enumerate(stream,1):
                    key=(aid,line_number)
                    if key in targets:
                        record=json.loads(line)
                        for condition,role in targets[key]:
                            assert (condition,role) not in seen
                            seen[(condition,role)]=(record,hashlib.sha256(line.rstrip(b'\n')).hexdigest())
        path.unlink()
        if index%12==0:print(f'validated_archives={index}',flush=True)
    assert state and state['version']=='limitless-hourly-v1' and len(seen)==sum(map(len,targets.values()))
    output=[]
    for row in rows:
        c=row['condition'];d=row['decision'];market=state['markets'][row['slug']]
        book,bookhash=seen[(c,'book')]
        minute,_=seen[(c,'minute')];hour,_=seen[(c,'hour')]
        assert bookhash==d['line_sha256'] and book['slug']==row['slug']
        assert good_book(book['raw'],market)
        now=d['observed_at']
        assert seconds(book['observed_at'])==now and seconds(minute['observed_at'])<=now and seconds(hour['observed_at'])<=now
        assert 0<=now-seconds(minute['observed_at'])<=10 and 0<=now-seconds(hour['observed_at'])<=120
        assert minute['params']['symbol']==hour['params']['symbol']==market['symbol']
        opening=next((r for r in hour['raw'] if int(r[0])==int(market['start']*1000)),None)
        assert opening is not None and D(str(opening[1]))==D(market['opening'])
        current=[r for r in minute['raw'] if float(r[0])/1000<=now<=float(r[6])/1000]
        assert len(current)==1
        price=float(current[0][4]);available=seconds(minute['requested_at'])
        original,_=probability(minute['raw'],{'price':price,'end':market['end']},market['opening'],now,available)
        assert abs(original-d['p_up'])<1e-12
        result={'condition':c,'phase':row['phase'],'hour_cluster':row['hour_cluster'],
            'source_book_artifact':d['artifact'],'source_book_line':d['line'],'source_book_sha256':bookhash,
            'minute_reference_artifact':d['minute_reference']['artifact'],'minute_reference_line':d['minute_reference']['line'],
            'p_frozen':original,'p_markov':None,'outcome_yes':row['outcome_yes'],
            'settled_baseline_pnl_usdc':row['settled_first_leg_pnl_usdc'],
            'status':None,'reason':None,'side':None,'first_attempt_artifact':None,
            'first_attempt_line':None,'first_attempt_sha256':None,
            'cost_usdc':None,'net_shares':None,'settled_markov_pnl_usdc':None}
        try:
            p,variance,matrix,last_state,vtotal=markov_probability(minute['raw'],price,market['opening'],now,available,market['end'])
            result.update(p_markov=p,regime_variances=variance,transition_matrix=matrix,
                          last_state=last_state,forecast_variance=vtotal)
            choice=select(book['raw'],p)
        except (ValueError,TypeError,KeyError,ArithmeticError) as exc:
            result.update(status='SKIP_INPUT',reason=str(exc));output.append(result);continue
        if choice is None:
            result.update(status='NO_TRADE',reason='NO_EXECUTABLE_EDGE');output.append(result);continue
        _,side,cap,gross=choice
        result['side']=side
        if row['entry'] is None:
            result.update(status='SKIP_EXECUTION',reason='NO_FIRST_REQUEST');output.append(result);continue
        attempt,hashline=seen[(c,'attempt')]
        result.update(first_attempt_artifact=row['entry']['artifact'],first_attempt_line=row['entry']['line'],
                      first_attempt_sha256=hashline)
        assert hashline==row['entry']['line_sha256']
        assert seconds(attempt['requested_at'])>=now+market['delay_s'] and seconds(attempt['requested_at'])<=now+30
        if attempt['kind']!='book':
            result.update(status='SKIP_EXECUTION',reason='FIRST_REQUEST_ERROR');output.append(result);continue
        if seconds(attempt['observed_at'])>now+30 or seconds(attempt['observed_at'])>=market['end']:
            result.update(status='SKIP_EXECUTION',reason='LATE_RESPONSE');output.append(result);continue
        if not good_book(attempt['raw'],market):
            result.update(status='SKIP_EXECUTION',reason='INVALID_BOOK');output.append(result);continue
        filled=fill(attempt['raw'],side,cap,gross)
        if filled is None:
            result.update(status='SKIP_EXECUTION',reason='DEPTH_OR_PRICE_BOUND_FAILED');output.append(result);continue
        payout=state['episodes'][c].get('payout')
        pnl=(D(filled['net_shares'])*D(str(payout[0 if side=='YES' else 1]))-D(filled['cost_usdc'])) if payout else None
        result.update(status='FILLED',cost_usdc=filled['cost_usdc'],net_shares=filled['net_shares'],
                      settled_markov_pnl_usdc=str(pnl) if pnl is not None else None)
        output.append(result)
    result={'schema':'limitless-hourly-markov-volatility-shadow-v1',
        'protocol':'research/LIMITLESS_HOURLY_MARKOV_PROTOCOL_2026-10-08.md',
        'source_archives':96,'total_conditions':162,'conditional_opportunities':len(rows),
        'summary':summarize(output),'rows':output,
        'limitations':'Same original first event/attempt, old inspected holdout, paper quotes not fills.'}
    pathlib.Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result['summary'],indent=2))


if __name__=='__main__':main()
