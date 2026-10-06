#!/usr/bin/env python3
"""Offline, non-executing at-touch maker feasibility diagnostic for hourly blend50."""
import collections
import argparse
import datetime as dt
import gzip
import hashlib
import json
import zipfile
from decimal import Decimal as D

from limitless_hourly_paper import levels

START = dt.datetime(2026, 10, 6, tzinfo=dt.timezone.utc).timestamp()
DELAY = 1.5
WINDOW = 30
HURDLE = D('0.03')


def timestamp(s):
    return dt.datetime.fromisoformat(s.replace('Z', '+00:00')).timestamp()


def top(book):
    yes, no = levels(book, 'YES'), levels(book, 'NO')
    if not yes or not no:
        return None
    ya, na = yes[0][0], no[0][0]
    yb, nb = 1-na, 1-ya
    if yb >= ya or nb >= na:
        return None
    return {'YES': (yb, ya), 'NO': (nb, na), 'mid': (yb+ya)/2}


def analyze(manifest):
    all_events = collections.defaultdict(list)
    with zipfile.ZipFile(manifest[-1]['download']['path']) as z:
        paper = json.loads(z.read('state.json'))['paper']
    episodes = [x for x in paper['episodes'].values()
                if x.get('decision_at', 0) >= START and x.get('start', 0) < START+7*86400]
    by_slug = {x['slug']: x for x in episodes}
    sources = []
    previous_end = None
    for item in manifest:
        run, artifact = item['run'], item['artifact']
        if (run['name'] != 'Limitless independent market capture'
                or run['head_branch'] != 'main' or run['event'] == 'pull_request'
                or run['status'] != 'completed' or run['conclusion'] != 'success'
                or artifact['workflow_run']['id'] != run['id']):
            raise ValueError('not a successful main capture artifact')
        path = item['download']['path']
        digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()
        if digest != artifact['digest'].removeprefix('sha256:'):
            raise ValueError('ZIP digest mismatch')
        with zipfile.ZipFile(path) as z:
            summary = json.loads(z.read('summary.json'))
            s, e = timestamp(summary['started_at']), timestamp(summary['ended_at'])
            if previous_end is not None and (s < previous_end or s-previous_end > 1200):
                raise ValueError('capture discontinuity')
            previous_end = e
            sources.append({'run': run['id'], 'head_sha': run['head_sha'],
                            'event':run['event'], 'artifact': artifact['id'],
                            'sha256': digest, 'started_at': summary['started_at'],
                            'ended_at': summary['ended_at']})
            with gzip.GzipFile(fileobj=z.open('capture.jsonl.gz')) as f:
                for line_no, line in enumerate(f, 1):
                    if not (b'"kind":"book"' in line or b'"event":"orderbookUpdate"' in line
                            or b'"kind":"request_error"' in line):
                        continue
                    x = json.loads(line)
                    if x['kind'] == 'book':
                        slug = x['slug']; book = x['raw']
                    elif x['kind'] == 'request_error':
                        if x.get('operation') != 'book':
                            continue
                        slug = x.get('slug'); book = None
                    else:
                        slug = x['raw'].get('marketSlug');book = x['raw'].get('orderbook')
                    if slug not in by_slug or (book is not None and not isinstance(book, dict)):
                        continue
                    ep = by_slug[slug]
                    t = timestamp(x['observed_at'])
                    if t < ep['decision_at']-10 or t > ep['decision_at']+WINDOW+5:
                        continue
                    all_events[slug].append((t, x, book, {'artifact': artifact['id'],
                                                           'line': line_no,
                                                           'sha256': hashlib.sha256(line.rstrip(b'\n')).hexdigest()}))
    rows = []
    for ep in sorted(episodes, key=lambda x: (x['decision_at'], x['slug'])):
        t, slug = ep['decision_at'], ep['slug']
        events = sorted(all_events[slug], key=lambda r:r[0])
        decision = [r for r in events if r[1]['kind']=='book' and 0 <= t-r[0] < .02]
        row = {'condition': ep['condition'], 'slug':slug, 'decision_at':t,
               'model_status': ep['variants']['model']['status'],
               'p_up':ep['p_up'], 'decision_book_count':len(decision)}
        if (len(decision)!=1 or top(decision[0][2]) is None
                or decision[0][2].get('tokenId') != paper['markets'][slug]['yes_token']):
            row['status']='MISSING_DECISION_BOOK'; rows.append(row); continue
        dec = decision[0]; market_mid=top(dec[2])['mid']
        p=(D(str(ep['p_up']))+market_mid)/2
        row.update({'decision_proof':dec[3], 'market_mid':str(market_mid), 'p_blend50':str(p)})
        # Existing delay/window; first REST attempt by request start, including errors.
        tries=[r for r in events if r[1]['kind'] in ('book','request_error')
               and t+DELAY <= timestamp(r[1]['requested_at']) < t+WINDOW]
        tries.sort(key=lambda r: timestamp(r[1]['requested_at']))
        if not tries:
            row['status']='NO_POST_DELAY_BOOK';rows.append(row);continue
        attempt=tries[0]
        row['first_attempt_proof']=attempt[3];row['first_attempt_at']=attempt[0]
        row['first_attempt_requested_at']=attempt[1]['requested_at']
        if attempt[1]['kind']=='request_error':
            row['status']='FAILED_FIRST_BOOK';rows.append(row);continue
        if attempt[0]>=t+WINDOW:
            row['status']='LATE_FIRST_BOOK';rows.append(row);continue
        if attempt[1]['raw'].get('tokenId') != paper['markets'][slug]['yes_token']:
            row['status']='TOKEN_MISMATCH';rows.append(row);continue
        quote=top(attempt[2])
        if quote is None:
            row['status']='INVALID_FIRST_BOOK';rows.append(row);continue
        candidates=[]
        for side in ('YES','NO'):
            bid,ask=quote[side]
            chance=p if side=='YES' else 1-p
            edge=chance/bid-1 if bid>0 else D('-1')
            candidates.append({'side':side,'best_bid':str(bid),'best_ask':str(ask),
                               'fair':str(chance),'gross_expected_roi':str(edge),
                               'eligible':edge>=HURDLE})
        row['candidates']=candidates
        eligible=[c for c in candidates if c['eligible']]
        if not eligible:
            row['status']='NO_AT_TOUCH_EDGE';rows.append(row);continue
        # Fixed selection by largest estimated ROI, with YES as stable tie breaker.
        selected=max(eligible,key=lambda c:D(c['gross_expected_roi']))
        side=selected['side'];bid=D(selected['best_bid'])
        row['selected']=selected
        later=[r for r in events if r[0]>attempt[0] and r[0]<t+WINDOW and r[1]['kind']=='ws_event']
        row['subsequent_ws_frames']=len(later)
        crossings=[]
        for r in later:
            book=top(r[2])
            if book and book[side][1]<=bid:
                crossings.append({'at':r[0],'proof':r[3], 'opposite_ask':str(book[side][1])})
        row['first_price_cross']=crossings[0] if crossings else None
        row['status']='OPTIMISTIC_CROSS' if crossings else ('OBSERVED_NO_CROSS' if later else 'CENSORED_NO_FOLLOWUP')
        rows.append(row)
    return {'schema':'limitless-hourly-blend50-maker-at-touch-diagnostic-v1',
            'asof':sources[-1]['ended_at'], 'source_archives':sources,
            'fee_assumption':'zero maker fee for a resting order; no rebates assumed',
            'price_rule':'join best bid at first REST book after 1.5s; never cross spread',
            'horizon_s':30,'hurdle':str(HURDLE),'rows':rows,
            'counts':dict(collections.Counter(r['status'] for r in rows)),
            'confirmed_fills':0,'realized_pnl':None}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,help='Ordered main capture ZIPs with GitHub run/artifact metadata and download.path')
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    result=analyze(json.load(open(args.manifest)))
    with open(args.out,'w') as f: json.dump(result,f,indent=2);f.write('\n')
    print(result['counts'])
