#!/usr/bin/env python3
"""Bounded public-only finalized trade tape probe for existing hourly maker diagnostic.

No order creation, signatures, API keys, wallet endpoints, or capture-state writes.
"""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://api.limitless.exchange'
SLUG = re.compile(r'^(?:btc|eth)-up-or-down-hourly-p-[0-9]+$')
SCHEMA = 'limitless-hourly-maker-public-tape-probe-v1'
LIMIT = 100
MAX_PAGES = 25
FIELDS = ('createdAt','makerAmount','matchedSize','price','side','takerAmount',
          'title','tokenId','txHash')


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='microseconds')


def stamp(s):
    parsed = dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('naive trade timestamp')
    return parsed.timestamp()


def fetch(slug,page):
    if not SLUG.fullmatch(slug) or not 1 <= page <= MAX_PAGES:
        raise ValueError('unapproved public market scope')
    path = '/markets/'+urllib.parse.quote(slug,safe='')+'/events'
    url = BASE+path+'?'+urllib.parse.urlencode({'page':page,'limit':LIMIT})
    req = urllib.request.Request(url,headers={
        'Accept':'application/json','User-Agent':'SmartCopyLimitlessPublicMakerTape/1'})
    began=now()
    try:
        with urllib.request.urlopen(req,timeout=12) as response:
            body=response.read(2_000_001)
            if len(body)>2_000_000:
                raise ValueError('oversize public trade page')
            received=now()
            return {'requested_at':began,'observed_at':received,
                    'http_status':response.status,
                    'cache_control':response.headers.get('Cache-Control'),
                    'body_sha256':hashlib.sha256(body).hexdigest(),
                    'body':json.loads(body)}
    except urllib.error.HTTPError as exc:
        return {'requested_at':began,'observed_at':now(),
                'http_status':exc.code,'error':str(exc.reason)}
    except (urllib.error.URLError,TimeoutError,ValueError,json.JSONDecodeError) as exc:
        return {'requested_at':began,'observed_at':now(),
                'http_status':None,'error':type(exc).__name__+': '+str(exc)[:180]}


def collect(rows,fetch_page,raw_write,max_pages=MAX_PAGES):
    results=[]
    for row in rows:
        slug=row['slug']
        if not SLUG.fullmatch(slug):
            raise ValueError('unapproved slug')
        first=row['first_attempt_at'];end=row['decision_at']+30
        info={'slug':slug,'condition':row['condition'],'decision_at':row['decision_at'],
              'first_attempt_at':first,'window_end':end,'pages':0,
              'events':0,'field_time_window_events':0,'field_time_window_examples':[],
              'complete':False,'page1_stable':None,'error':None}
        expected=None;page1_digest=None; seen=set()
        for page in range(1,max_pages+1):
            reply=fetch_page(slug,page)
            record={k:v for k,v in reply.items() if k!='body'}
            record.update({'slug':slug,'page':page})
            payload=reply.get('body')
            if reply.get('http_status')!=200 or not isinstance(payload,dict):
                info['error']=reply.get('error','invalid response')
                raw_write(record); break
            events=payload.get('events')
            total=payload.get('totalPages')
            if not isinstance(events,list) or not isinstance(total,int) or total<0:
                info['error']='invalid events/pagination schema';raw_write(record);break
            if expected is None:expected=total;page1_digest=reply.get('body_sha256')
            if total!=expected:
                info['error']='pagination changed during collection'
            record['total_pages']=total
            record['events']=[{k:x.get(k) for k in FIELDS} for x in events if isinstance(x,dict)]
            raw_write(record)
            info['pages']+=1
            for event in record['events']:
                key=tuple(str(event.get(k)) for k in FIELDS)
                if key in seen:continue
                seen.add(key);info['events']+=1
                try: within=first<=stamp(event['createdAt'])<end
                except (ValueError,TypeError,AttributeError):within=False
                if within:
                    info['field_time_window_events']+=1
                    if len(info['field_time_window_examples'])<10:
                        info['field_time_window_examples'].append(event)
            if not events or page>=total or info['error']:
                if not info['error'] and page>=total:info['complete']=True
                elif not events and page<total:
                    info['error']='premature empty page'
                break
        if expected is not None and info['pages']>=max_pages and expected>max_pages:
            info['error']='page cap reached';info['complete']=False
        if info['complete'] and expected>0:
            again=fetch_page(slug,1)
            info['page1_stable']=(again.get('http_status')==200 and
                                  again.get('body_sha256')==page1_digest)
            raw_write({'slug':slug,'page':1,'verification_only':True,
                       **{k:v for k,v in again.items() if k!='body'}})
            if not info['page1_stable']:
                info['complete']=False;info['error']='page1 drift or verification error'
        results.append(info)
    return results


def run(source,out):
    evidence=json.load(open(source))
    if evidence.get('schema')!='limitless-hourly-blend50-maker-at-touch-diagnostic-v1':
        raise ValueError('wrong maker diagnostic source')
    rows=evidence['rows']
    if len(rows)!=len({x['slug'] for x in rows}):raise ValueError('duplicate condition slug')
    target=pathlib.Path(out);target.mkdir(parents=True,exist_ok=True)
    with gzip.open(target/'market_events_pages.jsonl.gz','wt',encoding='utf-8') as stream:
        def write(row):
            stream.write(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n')
        results=collect(rows,fetch,write)
    report={'schema':SCHEMA,'asof':now(),'source_diagnostic_sha256':hashlib.sha256(
        pathlib.Path(source).read_bytes()).hexdigest(),
        'source_capture_asof':evidence['asof'],'endpoint':'GET /markets/{exact-slug}/events',
        'meaning':'retrospective MINED public tape; createdAt field not proven executable observation time',
        'markets':results,
        'complete_markets':sum(x['complete'] for x in results),
        'field_time_window_events':sum(x['field_time_window_events'] for x in results),
        'hypothetical_maker_fills':None,'maker_pnl':None}
    (target/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'markets':len(results),'complete':report['complete_markets'],
                      'field_time_window_events':report['field_time_window_events']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    run(args.source,args.out)
