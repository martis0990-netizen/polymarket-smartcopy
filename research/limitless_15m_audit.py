"""Offline Limitless 15m coverage and exploratory forecast audit; never submits orders."""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
import pathlib
import re
import zipfile
from decimal import Decimal, InvalidOperation
import statistics

parser=argparse.ArgumentParser()
parser.add_argument('manifest', help='JSON list with GitHub run, artifact digest and downloaded ZIP file.path')
parser.add_argument('--out', required=True)
args=parser.parse_args()
manifest = json.loads(pathlib.Path(args.manifest).read_text())
def sec(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()

selected = sorted((x for x in manifest if x['run']['head_branch']=='main'
                  and x['run']['event']!='pull_request' and x['run']['status']=='completed'
                  and x['run']['conclusion']=='success'), key=lambda x:x['run']['run_started_at'])
markets = collections.defaultdict(lambda: {'books':[], 'oracle':[], 'market':[], 'runs':set()})
segments=[]
for x in selected:
    path=pathlib.Path(x['file']['path'])
    if not path.is_absolute():path=pathlib.Path(args.manifest).resolve().parent/path
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha == x['artifact']['digest'].split(':')[-1], (path, sha)
    with zipfile.ZipFile(path) as z:
        summary=json.loads(z.read('summary.json'))
        segments.append({'run':x['run']['id'], 'artifact':x['artifact']['id'], 'sha256':sha,
                         'start':summary['started_at'], 'end':summary['ended_at']})
        with gzip.GzipFile(fileobj=z.open('capture.jsonl.gz')) as f:
            for line in f:
                if b'"kind":"ws_event"' in line:continue
                if b'15-min-' not in line:continue
                row=json.loads(line)
                slug=row.get('slug')
                if not slug or '15-min-' not in slug:continue
                k=row['kind']
                if k not in ('market','book','oracle_candles'):continue
                market=markets[slug]
                market['runs'].add(x['run']['id'])
                if k=='market':
                    raw=row.get('raw') or {}
                    market['market'].append((sec(row['observed_at']),raw))
                elif k=='book':market['books'].append((sec(row['requested_at']),sec(row['observed_at']),row.get('raw')))
                else:market['oracle'].append((sec(row['requested_at']),sec(row['observed_at']),row.get('raw')))

stats=collections.Counter(); examples=[]; kinds=collections.Counter(); sources=collections.Counter()
oracle_lags=[];history_counts=[]
forecast_rows=[]
for slug,v in markets.items():
    if not v['market']:continue
    observed=sorted(v['market'])
    first=observed[0][1];last=observed[-1][1]
    identity=lambda m:(m.get('conditionId'),str((m.get('metadata') or {}).get('openPrice')),
                       str(((m.get('metadata') or {}).get('chainlinkDataStream') or {}).get('feedId')))
    if len({identity(m) for _,m in observed})>1:stats['conflicting_market_identity']+=1
    start=sec(first['startAt'])
    # Market expiration timestamp is the exact boundary. Never rely on display date.
    expiry=float(first['expirationTimestamp'])
    if expiry>1e11:expiry/=1000
    horizon=expiry-start
    stats['markets']+=1
    if abs(horizon-900)>1:stats['non_15_min_expiry']+=1
    if observed[0][0]<=start:stats['seen_before_open']+=1
    if observed[0][0]<=start+450:stats['seen_by_midpoint']+=1
    if observed[0][0]>start+450:stats['first_seen_after_midpoint']+=1
    winners=[(t,m.get('winningOutcomeIndex')) for t,m in observed if m.get('status')=='RESOLVED' and m.get('winningOutcomeIndex') is not None]
    if winners:stats['observed_resolved']+=1
    if len({w for _,w in winners})>1:stats['conflicting_winners']+=1
    if not winners:stats['no_observed_resolution']+=1
    try:
        opening=Decimal(str(first['metadata']['openPrice']))
        ending=Decimal(str(last['metadata']['resolvePrice']))
        winner=last.get('winningOutcomeIndex')
        if winner is not None:
            stats['resolution_price_and_winner']+=1
            if (ending>=opening)==(winner==0):stats['resolution_price_consistent']+=1
            else:stats['resolution_price_conflict']+=1
    except (KeyError, TypeError, InvalidOperation):
        if winners:stats['resolution_price_missing']+=1
    b=sorted(v['books']); o=sorted(v['oracle'])
    if any(isinstance(raw,dict) and raw.get('tokenId')!=first.get('tokens',{}).get('yes')
           for _,_,raw in b):stats['markets_with_book_token_mismatch']+=1
    stats['book_envelopes']+=len(b);stats['oracle_envelopes']+=len(o)
    if any(start+450<=request<expiry for request,receipt,raw in b):stats['midpoint_to_expiry_book']+=1
    if any(start+450<=request<expiry and isinstance(raw,dict) and raw.get('bids') and raw.get('asks') for request,receipt,raw in b):stats['midpoint_to_expiry_two_sided_book']+=1
    if any(start+450<=request<expiry for request,receipt,raw in o):stats['midpoint_to_expiry_oracle_request']+=1
    entry_books=[(q,r,raw) for q,r,raw in b if start+450<=q<=start+510 and r<=start+510]
    entry_oracles=[(q,r,raw) for q,r,raw in o if start+450<=q<=start+510 and r<=start+510]
    if entry_books:stats['midpoint_60s_book_receipt']+=1
    if entry_oracles:stats['midpoint_60s_oracle_receipt']+=1
    if entry_books and entry_oracles:stats['midpoint_60s_both_receipts']+=1
    if entry_books and any(isinstance(raw,dict) and raw.get('bids') and raw.get('asks') for _,_,raw in entry_books):stats['midpoint_60s_two_sided_book']+=1
    for _,_,raw in o:
        if isinstance(raw,dict):sources[str(raw.get('source'))]+=1
        if isinstance(raw,dict):
            for candle in raw.get('rows') or []:
                if candle.get('timestamp')==expiry:stats['exact_expiry_oracle_row_envelopes']+=1
                if candle.get('timestamp')==start:stats['exact_open_oracle_row_envelopes']+=1
    if entry_oracles:
        q,r,entry_raw=entry_oracles[0]
        candles=(entry_raw or {}).get('rows',[]) if isinstance(entry_raw,dict) else []
        closed=sorted({float(c['timestamp']):c for c in candles if isinstance(c,dict)
                      and isinstance(c.get('timestamp'),(int,float))
                      and c['timestamp']+60<=q}.items())
        if closed:
            lag=r-(closed[-1][0]+60)
            oracle_lags.append(lag)
            consecutive=1
            for i in range(len(closed)-1,0,-1):
                if closed[i][0]-closed[i-1][0]!=60:break
                consecutive+=1
            history_counts.append(consecutive)
            if consecutive>=121:stats['midpoint_60s_oracle_120_returns']+=1
            if consecutive>=121 and winners and entry_books and (entry_raw or {}).get('source')=='chainlink':
                recent=[c for _,c in closed[-121:]]
                values=[float(c['close'])/1e18 for c in recent]
                if all(math.isfinite(x) and x>0 for x in values):
                    returns=[math.log(values[i]/values[i-1]) for i in range(1,len(values))]
                    sigma=statistics.stdev(returns)
                    # Forecast horizon begins at the stale, fully closed oracle reference,
                    # not at response receipt. Receipt is only the first time it is usable.
                    remain=(expiry-(closed[-1][0]+60))/60
                    if sigma>0 and remain>0:
                        p=0.5*(1+math.erf(math.log(values[-1]/float(first['metadata']['openPrice']))/(sigma*math.sqrt(remain)*math.sqrt(2))))
                        forecast_rows.append({'slug':slug,'start':start,'p_up':p,'up':int(winners[-1][1]==0),
                                              'reference_age_s':lag,'decision_at':r,'sigma':sigma})
    description=re.sub('<[^>]*>',' ',first.get('description',''))
    if 'Chainlink' in description and '60-second TWAP' in description:stats['chainlink_twap60_description']+=1
    else:stats['other_description']+=1
    kinds[str(last.get('status'))]+=1
    examples.append({'slug':slug,'start':first['startAt'],'expiry':expiry,'first_seen':observed[0][0],
                     'status':last.get('status'),'winningOutcomeIndex':last.get('winningOutcomeIndex'),
                     'market_count':len(observed),'book_count':len(b),'oracle_count':len(o),
                     'first_midpoint_book_request':next((q for q,r,raw in b if start+450<=q<expiry),None),
                     'first_midpoint_oracle_request':next((q for q,r,raw in o if start+450<=q<expiry),None),
                     'midpoint_60s_book':bool(entry_books),'midpoint_60s_oracle':bool(entry_oracles)})
report={'scope':'main_completed_success_available_local_manifest','segments':segments,'stats':dict(stats),
        'market_status_last':dict(kinds),'oracle_sources':dict(sources),
        'oracle_first_midpoint_lag_seconds':{'n':len(oracle_lags),'median':statistics.median(oracle_lags) if oracle_lags else None,
            'p10':sorted(oracle_lags)[len(oracle_lags)//10] if oracle_lags else None,
            'p90':sorted(oracle_lags)[len(oracle_lags)*9//10] if oracle_lags else None},
        'contiguous_closed_oracle_rows':{'n':len(history_counts),'median':statistics.median(history_counts) if history_counts else None,
            'min':min(history_counts) if history_counts else None},
        'exploratory_oracle_midpoint_forecast': {
            'n':len(forecast_rows), 'clusters':len({x['start'] for x in forecast_rows}),
            'brier':sum((x['p_up']-x['up'])**2 for x in forecast_rows)/len(forecast_rows) if forecast_rows else None,
            'constant50_brier':0.25,
            'favourite_accuracy':sum((x['p_up']>=0.5)==bool(x['up']) for x in forecast_rows)/len(forecast_rows) if forecast_rows else None,
            'mean_p_up':statistics.mean(x['p_up'] for x in forecast_rows) if forecast_rows else None},
        'exploratory_forecast_rows': sorted(forecast_rows,key=lambda a:a['start']),
        'markets':sorted(examples,key=lambda a:a['start']), 'pnl':None}
out=pathlib.Path(args.out)
out.write_text(json.dumps(report,indent=2,ensure_ascii=False))
print(json.dumps({'segments':len(segments),'first':segments[0]['start'],'last':segments[-1]['end'],
                  'stats':report['stats'],'status':report['market_status_last'],
                  'oracle_sources':report['oracle_sources'],
                  'oracle_lag':report['oracle_first_midpoint_lag_seconds'],
                  'oracle_history':report['contiguous_closed_oracle_rows']},indent=2))
