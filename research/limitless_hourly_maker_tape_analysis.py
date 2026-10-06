#!/usr/bin/env python3
"""Retrospective tape match; potential contra volume is never a maker fill."""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import zipfile
from decimal import Decimal as D


def stamp(value):
    x=dt.datetime.fromisoformat(value.replace('Z','+00:00'))
    if x.tzinfo is None:raise ValueError('naive timestamp')
    return x.timestamp()


def digest(path):return hashlib.sha256(open(path,'rb').read()).hexdigest()


def analyze(diagnostic,probe_zip,state_zip):
    source=json.load(open(diagnostic))
    with zipfile.ZipFile(probe_zip) as z:
        report=json.loads(z.read('summary.json'))
        raw=[]
        with gzip.GzipFile(fileobj=z.open('market_events_pages.jsonl.gz')) as f:
            for line in f:raw.append(json.loads(line))
    with zipfile.ZipFile(state_zip) as z:
        state=json.loads(z.read('state.json'))['paper']
    if report['source_diagnostic_sha256']!=digest(diagnostic):
        raise ValueError('probe references another diagnostic')
    status={r['slug']:r for r in report['markets']}
    if set(status)!={r['slug'] for r in source['rows']}:
        raise ValueError('missing market')
    pages={}
    for page in raw:
        if not page.get('verification_only'):
            pages.setdefault(page['slug'],[]).append(page)
    result=[]
    for row in source['rows']:
        slug=row['slug']; s=status[slug]
        if not s['complete'] or not s['page1_stable']:
            raise ValueError('incomplete market tape')
        yes_token=state['markets'][slug]['yes_token']
        selected=row['selected'];side=selected['side'];bid=D(selected['best_bid'])
        all_events=[];possible=[];seen=set()
        for page in pages[slug]:
            for index,event in enumerate(page['events']):
                key=tuple(str(event.get(k)) for k in ('txHash','tokenId','side','price','matchedSize','createdAt'))
                if key in seen:continue
                seen.add(key)
                try:within=row['first_attempt_at']<=stamp(event['createdAt'])<row['decision_at']+30
                except (ValueError,TypeError,AttributeError):within=False
                if not within:continue
                trace={'page':page['page'],'index':index,'txHash':event.get('txHash'),
                       'createdAt':event.get('createdAt'),'tokenId':event.get('tokenId'),
                       'side':event.get('side'),'price':event.get('price'),
                       'matchedSize':event.get('matchedSize')}
                all_events.append(trace)
                if event.get('tokenId')!=yes_token:continue
                try:
                    price=D(str(event['price'])); size=D(str(event['matchedSize']))/D(1000000)
                except (ArithmeticError,ValueError,TypeError):continue
                compatible=(side=='YES' and event.get('side')==1 and price<=bid or
                            side=='NO' and event.get('side')==0 and price>=1-bid)
                if compatible and size>0:possible.append({**trace,'yes_token_shares':str(size)})
        result.append({'slug':slug,'condition':row['condition'],'quote_side':side,
                       'quote_bid':str(bid),'decision_at':row['decision_at'],
                       'first_attempt_at':row['first_attempt_at'],
                       'window_end':row['decision_at']+30,
                       'book_cross_status':row['status'],
                       'all_field_time_events':all_events,
                       'price_side_compatible_tape':possible,
                       'compatible_volume_upper_shares':str(sum((D(e['yes_token_shares']) for e in possible),D(0))),
                       'hypothetical_fill_shares':None})
    return {'schema':'limitless-hourly-maker-tape-match-v1',
            'source_diagnostic_sha256':digest(diagnostic),'probe_zip_sha256':digest(probe_zip),
            'source_capture_zip_sha256':digest(state_zip),
            'probe_asof':report['asof'],'complete_markets':report['complete_markets'],
            'field_time_events':sum(len(r['all_field_time_events']) for r in result),
            'price_side_compatible_events':sum(len(r['price_side_compatible_tape']) for r in result),
            'rows':result,'confirmed_fills':0,'realized_pnl':None,
            'scope':'finalized MINED public trades by createdAt field; no order identity or queue proof'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diagnostic',required=True)
    parser.add_argument('--probe-zip',required=True)
    parser.add_argument('--state-zip',required=True)
    parser.add_argument('--out',required=True)
    a=parser.parse_args()
    result=analyze(a.diagnostic,a.probe_zip,a.state_zip)
    with open(a.out,'w') as f:json.dump(result,f,indent=2);f.write('\n')
    print({k:v for k,v in result.items() if k in ('complete_markets','field_time_events','price_side_compatible_events')})
