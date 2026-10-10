"""Causal, first-eligible event shadow for the precommitted protocol."""
import bisect
import collections
import decimal
import glob
import json
import math
import sqlite3
import statistics
import zipfile
import zlib

from limitless_hourly_paper import BUDGET, FEE, HURDLE, MICRO, fill, levels, probability

D = decimal.Decimal
conn = sqlite3.connect('hourly_event_raw.sqlite')
conn.row_factory = sqlite3.Row
source = json.load(open('limitless_hourly_all_decisions_2026-10-07.json'))['rows']
path, = glob.glob('attachments/**/github-actions-artifact-11470560416.zip', recursive=True)
state = json.loads(zipfile.ZipFile(path).read('state.json'))['paper']


def expand(sql_row):
    row=dict(sql_row)
    if 'raw' in row:
        row['raw']=json.loads(zlib.decompress(row['raw']))
    if 'requested' in row:row['requested_at']=row.pop('requested')
    if 'observed' in row:row['observed_at']=row.pop('observed')
    if 'sha256' in row:row['line_sha256']=row.pop('sha256')
    return row


def asof(recs, times, now):
    idx = bisect.bisect_right(times, now)-1
    return recs[idx] if idx >= 0 else None


def good_book(record, market):
    if record['kind'] != 'book' or not isinstance(record['raw'],dict):
        return False
    try:
        b = record['raw']
        return str(b.get('tokenId')) == str(market['yes_token']) and bool(levels(b,'YES')) and \
               bool(levels(b,'NO')) and levels(b,'YES')[0][0]+levels(b,'NO')[0][0] >= 1
    except (ValueError,TypeError,KeyError,ArithmeticError):
        return False


def inputs(market, now):
    symbol = market['symbol']
    minute_row=conn.execute('SELECT * FROM refs WHERE symbol=? AND kind=? AND observed<=? ORDER BY observed DESC,artifact DESC,line DESC LIMIT 1',
                            (symbol,'binance_1m',now)).fetchone()
    hour_row=conn.execute('SELECT * FROM refs WHERE symbol=? AND kind=? AND observed<=? ORDER BY observed DESC,artifact DESC,line DESC LIMIT 1',
                          (symbol,'binance_1h',now)).fetchone()
    minute=expand(minute_row) if minute_row else None
    hour=expand(hour_row) if hour_row else None
    if not minute or not hour or not 0<=now-minute['observed_at']<=10 or not 0<=now-hour['observed_at']<=120:
        raise ValueError('STALE_REFERENCE')
    opening = next((bar for bar in hour['raw'] if int(bar[0])==int(market['start']*1000)),None)
    if opening is None or D(str(opening[1]))!=D(market['opening']):
        raise ValueError('OPEN_PRICE_NOT_VERIFIED')
    current = [bar for bar in minute['raw'] if float(bar[0])/1000 <= now <= float(bar[6])/1000]
    if len(current)!=1:raise ValueError('MISSING_CURRENT_CANDLE')
    price = float(current[0][4])
    if not math.isfinite(price) or price<=0:raise ValueError('INVALID_REFERENCE')
    p,sigma = probability(minute['raw'],{'price':price,'end':market['end']},
                          market['opening'],now,minute['requested_at'])
    return p,sigma,price,minute,hour


def cost_for_shares(book,side,shares):
    remaining,cost = shares,D(0)
    for price,size in levels(book,side):
        take=min(remaining,size)
        cost+=price*take
        remaining-=take
        if remaining==0:break
    return cost if remaining==0 and cost>0 else None


results=[]
for source_row in source:
    condition=source_row['condition']
    ep=state['episodes'][condition]
    slug=ep['slug']
    market=state['markets'][slug]
    books=[expand(r) for r in conn.execute('SELECT * FROM books WHERE slug=? ORDER BY observed,artifact,line',(slug,))]
    statuses=[expand(r) for r in conn.execute('SELECT * FROM statuses WHERE slug=? ORDER BY observed,artifact,line',(slug,))]
    stimes=[r['observed_at'] for r in statuses]
    tally=collections.Counter()
    record={'condition':condition,'slug':slug,'phase':source_row['phase'],
            'symbol':market['symbol'],'hour_cluster':source_row['hour_cluster'],
            'status':'NO_TRADE','reason':'NO_OBSERVED_ELIGIBLE_EVENT',
            'books_in_market':len(books),'input_checks':{},
            'decision':None,'entry':None,'pair_quote':None,
            'outcome_yes':ep['payout'][0] if ep.get('payout') else None,
            'settled_first_leg_pnl_usdc':None}
    signal=None
    for book in books:
        if book['kind']!='book':continue
        now=book['observed_at']
        if now>=market['end']:continue
        status=asof(statuses,stimes,now)
        if status is None or status['status']!='FUNDED':
            tally['MARKET_NOT_OBSERVED_FUNDED']+=1;continue
        if not good_book(book,market):
            tally['INVALID_BOOK']+=1;continue
        try:p,sigma,price,minute,hour=inputs(market,now)
        except (ValueError,TypeError,KeyError,ArithmeticError) as exc:
            tally[str(exc)]+=1;continue
        tally['VALID_ASOF_INPUTS']+=1
        choices=[]
        for side,chance in (('YES',p),('NO',1-p)):
            cap=D(str(chance))*(1-FEE)/(1+HURDLE)
            if cap<=0:continue
            shares=(BUDGET/cap).quantize(MICRO,rounding=decimal.ROUND_DOWN)
            try:simulated=fill(book['raw'],side,cap,shares)
            except (ValueError,TypeError,KeyError,ArithmeticError):simulated=None
            if simulated:
                edge=float(D(simulated['net_shares'])*D(str(chance))/D(simulated['cost_usdc'])-1)
                choices.append((edge,side,cap,shares))
        if not choices:
            tally['NO_EXECUTABLE_EDGE']+=1;continue
        _,side,cap,shares=max(choices,key=lambda x:(x[0],x[1]))
        signal=(book,side,cap,shares,p)
        record['decision']={'artifact':book['artifact'],'line':book['line'],
            'line_sha256':book['line_sha256'],'requested_at':book['requested_at'],
            'observed_at':now,'minute_from_open':(now-market['start'])/60,
            'side':side,'p_up':p,'sigma_1m':sigma,'reference_price':price,
            'entry_cap':str(cap),'gross_shares':str(shares),
            'minute_reference':{'artifact':minute['artifact'],'line':minute['line'],
                'observed_at':minute['observed_at']},
            'hour_reference':{'artifact':hour['artifact'],'line':hour['line'],
                'observed_at':hour['observed_at']}}
        break
    record['input_checks']=dict(tally)
    if signal is None:results.append(record);continue
    decision,side,cap,shares,p=signal
    eligible_after=decision['observed_at']+market['delay_s']
    first=next((book for book in sorted(books,key=lambda r:(r['requested_at'],r['observed_at'],r['artifact'],r['line']))
                if eligible_after<=book['requested_at']<=decision['observed_at']+30),None)
    if first is None:
        record.update(status='SKIP_EXECUTION',reason='NO_FIRST_REQUEST');results.append(record);continue
    record['entry']={'artifact':first['artifact'],'line':first['line'],
                     'line_sha256':first['line_sha256'],'requested_at':first['requested_at'],
                     'observed_at':first['observed_at']}
    if first['kind']!='book':
        record.update(status='SKIP_EXECUTION',reason='FIRST_REQUEST_ERROR');results.append(record);continue
    if first['observed_at']>decision['observed_at']+30 or first['observed_at']>=market['end']:
        record.update(status='SKIP_EXECUTION',reason='FIRST_RESPONSE_TOO_LATE');results.append(record);continue
    if not good_book(first,market):
        record.update(status='SKIP_EXECUTION',reason='INVALID_EXECUTION_BOOK');results.append(record);continue
    try:filled=fill(first['raw'],side,cap,shares)
    except (ValueError,TypeError,KeyError,ArithmeticError):filled=None
    if filled is None:
        record.update(status='SKIP_EXECUTION',reason='DEPTH_OR_PRICE_BOUND_FAILED');results.append(record);continue
    record['entry'].update(filled)
    record.update(status='FILLED',reason=None)
    if ep.get('payout'):
        winning=ep['payout'][0 if side=='YES' else 1]
        record['settled_first_leg_pnl_usdc']=str(D(filled['net_shares'])*D(str(winning))-D(filled['cost_usdc']))
    opposite='NO' if side=='YES' else 'YES'
    target=(D(filled['net_shares'])/(1-FEE)).quantize(MICRO,rounding=decimal.ROUND_UP)
    for later in books:
        if later['requested_at']<first['observed_at'] or later['observed_at']>=market['end']:
            continue
        later_status=asof(statuses,stimes,later['observed_at'])
        if later_status is None or later_status['status']!='FUNDED' or not good_book(later,market):continue
        try:cost=cost_for_shares(later['raw'],opposite,target)
        except (ValueError,TypeError,KeyError,ArithmeticError):continue
        if cost is not None and cost<=BUDGET and D(filled['cost_usdc'])+cost<D(filled['net_shares']):
            record['pair_quote']={'artifact':later['artifact'],'line':later['line'],
                'line_sha256':later['line_sha256'],'requested_at':later['requested_at'],
                'observed_at':later['observed_at'],'opposite_side':opposite,
                'gross_shares':str(target),'quoted_cost_usdc':str(cost),
                'combined_quoted_cost_usdc':str(D(filled['cost_usdc'])+cost),
                'guaranteed_payout_at_quoted_sizes':str(D(filled['net_shares']))}
            break
    results.append(record)

summary={}
for phase in ('discovery','holdout'):
    rows=[r for r in results if r['phase']==phase]
    filled=[r for r in rows if r['status']=='FILLED']
    resolved=[r for r in filled if r['settled_first_leg_pnl_usdc'] is not None]
    pnl=sorted((D(r['settled_first_leg_pnl_usdc']) for r in resolved),reverse=True)
    cluster=collections.defaultdict(lambda:D(0))
    for row in resolved:cluster[row['hour_cluster']]+=D(row['settled_first_leg_pnl_usdc'])
    summary[phase]={'conditions':len(rows),'market_book_records':sum(r['books_in_market'] for r in rows),
        'valid_asof_input_books':sum(r['input_checks'].get('VALID_ASOF_INPUTS',0) for r in rows),
        'input_failures':dict(sum((collections.Counter(r['input_checks']) for r in rows),collections.Counter())),
        'first_eligible_opportunities':sum(r['decision'] is not None for r in rows),
        'statuses':dict(collections.Counter(r['status'] for r in rows)),
        'execution_skip_reasons':dict(collections.Counter(r['reason'] for r in rows if r['status']=='SKIP_EXECUTION')),
        'filled_first_leg':len(filled),'resolved_first_leg':len(resolved),
        'later_pair_quote_available':sum(r['pair_quote'] is not None for r in filled),
        'median_first_eligible_minute':statistics.median(r['decision']['minute_from_open'] for r in rows if r['decision']) if any(r['decision'] for r in rows) else None,
        'one_leg_settled_pnl_usdc':str(sum(pnl,D(0))),
        'one_leg_wins':sum(v>0 for v in pnl),'top_two_pnl_usdc':[str(v) for v in pnl[:2]],
        'pnl_excluding_top_two_usdc':str(sum(pnl[2:],D(0))),
        'active_hour_clusters':len(cluster),'positive_hour_clusters':sum(v>0 for v in cluster.values())}

output={'schema':'limitless-hourly-event-trigger-shadow-v1',
        'protocol':'research/LIMITLESS_HOURLY_EVENT_TRIGGER_PROTOCOL_2026-10-08.md',
        'source_archive_count':96,'summary':summary,'rows':results,
        'limitations':'Previously inspected holdout; second-leg availability is a quote, not a fill.'}
with open('limitless_hourly_event_trigger_2026-10-08.json','w') as target:
    json.dump(output,target,indent=2)
print(json.dumps(summary,indent=2))
