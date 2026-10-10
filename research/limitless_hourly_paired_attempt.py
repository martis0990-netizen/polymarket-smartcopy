#!/usr/bin/env python3
"""Read-only, first delayed second-leg paper replay on archived Limitless books."""
import argparse
import collections
import datetime as dt
import decimal
import gzip
import hashlib
import json
import os
import pathlib
import statistics
import urllib.error
import urllib.request
import zipfile

from limitless_hourly_paper import BUDGET, FEE, MICRO, levels

D=decimal.Decimal
REPO='martis0990-netizen/polymarket-smartcopy'
ROOT=pathlib.Path(__file__).resolve().parents[1]
INPUT=ROOT/'research/limitless_hourly_event_trigger_2026-10-08.json'
MANIFEST=ROOT/'research/evidence/limitless_hourly_all_decisions_2026-10-07.json'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*_):
        return None


def seconds(value):
    return dt.datetime.fromisoformat(value.replace('Z','+00:00')).timestamp()


def download(artifact,path,expected,token):
    if path.exists():
        with path.open('rb') as existing:
            if hashlib.file_digest(existing,'sha256').hexdigest()==expected:return
    url=f'https://api.github.com/repos/{REPO}/actions/artifacts/{artifact}/zip'
    req=urllib.request.Request(url,headers={'Authorization':f'Bearer {token}',
                                        'Accept':'application/vnd.github+json'})
    opener=urllib.request.build_opener(NoRedirect)
    try:
        response=opener.open(req,timeout=30)
        raise ValueError(f'EXPECTED_GITHUB_REDIRECT_{response.status}')
    except urllib.error.HTTPError as error:
        if error.code not in (302,307):raise
        location=error.headers['Location']
    # Never forward the Actions token to the redirected blob host.
    with urllib.request.urlopen(location,timeout=120) as response,path.open('wb') as out:
        while block:=response.read(1024*1024):out.write(block)
    with path.open('rb') as downloaded:
        actual=hashlib.file_digest(downloaded,'sha256').hexdigest()
    if actual!=expected:
        path.unlink(missing_ok=True)
        raise ValueError(f'ZIP_SHA256_MISMATCH_{artifact}')


def good_book(book,market):
    try:
        yes,no=levels(book,'YES'),levels(book,'NO')
        return str(book.get('tokenId'))==str(market['yes_token']) and bool(yes and no) and yes[0][0]+no[0][0]>=1
    except (ValueError,TypeError,KeyError,ArithmeticError):return False


def book_cost(book,side,shares):
    remaining,cost=shares,D(0)
    for price,size in levels(book,side):
        qty=min(remaining,size)
        cost+=qty*price
        remaining-=qty
        if remaining==0:break
    return cost if remaining==0 and cost>0 else None


def replay(event_rows,state,books,statuses,source_check):
    result=[]
    for row in event_rows:
        if row['pair_quote'] is None:continue
        condition,slug=row['condition'],row['slug']
        market=state['markets'][slug]
        quote=row['pair_quote']; first=row['entry']; side=quote['opposite_side']
        assert row['status']=='FILLED' and first and first['net_shares'] and side!=row['decision']['side']
        assert source_check[condition]==1,('QUOTE_SOURCE_NOT_CONFIRMED',condition)
        episode=state['episodes'][condition]
        assert episode.get('payout') and D(str(episode['payout'][0]))==D(str(row['outcome_yes']))
        target=D(quote['gross_shares'])
        assert target* (1-FEE)>=D(first['net_shares']) and target<=D(first['net_shares'])/(1-FEE)+MICRO
        after=quote['observed_at']+market['delay_s']
        end=quote['observed_at']+30
        result_row={'condition':condition,'slug':slug,'phase':row['phase'],
            'hour_cluster':row['hour_cluster'],'first_side':row['decision']['side'],
            'first_net_shares':first['net_shares'],'first_cost_usdc':first['cost_usdc'],
            'first_leg_settled_pnl_usdc':row['settled_first_leg_pnl_usdc'],
            'quote_artifact':quote['artifact'],'quote_line':quote['line'],
            'quote_sha256':quote['line_sha256'],'quote_observed_at':quote['observed_at'],
            'quoted_cost_usdc':quote['quoted_cost_usdc'],'second_side':side,
            'second_gross_shares':str(target),'eligible_after':after,
            'expiry_at':end,'status':None,'reason':None,'attempt':None,
            'paired_settled_pnl_usdc':None,'settled_pnl_after_policy_usdc':row['settled_first_leg_pnl_usdc']}
        candidates=[b for b in books[slug] if after<=b['requested_at']<=end]
        candidates.sort(key=lambda b:(b['requested_at'],b['observed_at'],b['artifact'],b['line']))
        if not candidates:
            result_row.update(status='SKIP_SECOND',reason='NO_FIRST_REQUEST');result.append(result_row);continue
        attempt=candidates[0]
        result_row['attempt']={k:attempt[k] for k in ('kind','artifact','line','sha256','requested_at','observed_at')}
        if attempt['kind']!='book':
            result_row.update(status='SKIP_SECOND',reason='FIRST_REQUEST_ERROR');result.append(result_row);continue
        if attempt['observed_at']>end or attempt['observed_at']>=market['end']:
            result_row.update(status='SKIP_SECOND',reason='LATE_RESPONSE');result.append(result_row);continue
        observed_status=[s for s in statuses[slug] if s['observed_at']<=attempt['observed_at']]
        if not observed_status or observed_status[-1]['status']!='FUNDED':
            result_row.update(status='SKIP_SECOND',reason='NOT_OBSERVED_FUNDED');result.append(result_row);continue
        book=attempt['raw']
        if not good_book(book,market):
            result_row.update(status='SKIP_SECOND',reason='INVALID_BOOK');result.append(result_row);continue
        try:cost=book_cost(book,side,target)
        except (ValueError,TypeError,KeyError,ArithmeticError):cost=None
        if cost is None:
            result_row.update(status='SKIP_SECOND',reason='INSUFFICIENT_DEPTH');result.append(result_row);continue
        net=target*(1-FEE)
        first_net=D(first['net_shares']); first_cost=D(first['cost_usdc'])
        if cost>BUDGET or first_cost+cost>=min(first_net,net):
            result_row.update(status='SKIP_SECOND',reason='PAIRED_COST_BOUND_FAILED');result.append(result_row);continue
        payout=episode['payout']
        gross=first_net*D(str(payout[0 if row['decision']['side']=='YES' else 1]))+net*D(str(payout[0 if side=='YES' else 1]))
        pnl=gross-first_cost-cost
        result_row['attempt'].update(second_cost_usdc=str(cost),second_net_shares=str(net),
            pair_minimum_payout_usdc=str(min(first_net,net)),
            guaranteed_quoted_margin_usdc=str(min(first_net,net)-first_cost-cost))
        result_row.update(status='PAIRED_PAPER',reason=None,paired_settled_pnl_usdc=str(pnl),
                          settled_pnl_after_policy_usdc=str(pnl))
        result.append(result_row)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='paired_attempt_evidence.json')
    parser.add_argument('--cache',default='artifact-cache')
    args=parser.parse_args()
    token=os.environ['GITHUB_TOKEN']
    event=json.loads(INPUT.read_text())
    manifest=json.loads(MANIFEST.read_text())['archive_zip_digests']
    assert len(manifest)==96 and len(event['rows'])==162
    assert manifest[-1]['artifact']==json.loads(MANIFEST.read_text())['source_final_state_artifact']
    pairs=[r for r in event['rows'] if r['pair_quote']]
    assert len(pairs)==60
    slugs={r['slug'] for r in pairs}
    source_check=collections.Counter()
    quote_raw={}
    books=collections.defaultdict(list)
    statuses=collections.defaultdict(list)
    cache=pathlib.Path(args.cache);cache.mkdir(exist_ok=True)
    state=None
    for index,item in enumerate(manifest,1):
        aid=item['artifact'];path=cache/f'{aid}.zip'
        download(aid,path,item['zip_sha256'],token)
        with zipfile.ZipFile(path) as archive:
            if aid==manifest[-1]['artifact']:
                state=json.loads(archive.read('state.json'))['paper']
            with gzip.GzipFile(fileobj=archive.open('capture.jsonl.gz')) as stream:
                for line_number,line in enumerate(stream,1):
                    if not line.startswith((b'{"kind":"book"',b'{"kind":"request_error"',b'{"kind":"market"')):continue
                    record=json.loads(line)
                    slug=record.get('slug')
                    if slug not in slugs:continue
                    kind=record['kind']
                    observed=seconds(record['observed_at'])
                    if kind=='market':
                        statuses[slug].append({'observed_at':observed,
                            'status':(record.get('raw') or {}).get('status'),
                            'artifact':aid,'line':line_number})
                        continue
                    if kind=='request_error' and record.get('operation')!='book':continue
                    requested=seconds(record['requested_at'])
                    hashline=hashlib.sha256(line.rstrip(b'\n')).hexdigest()
                    for row in pairs:
                        q=row['pair_quote']
                        if q['artifact']==aid and q['line']==line_number:
                            assert slug==row['slug'] and hashline==q['line_sha256']
                            assert requested==q['requested_at'] and observed==q['observed_at']
                            assert kind=='book'
                            quote_raw[row['condition']]=record['raw']
                            source_check[row['condition']]+=1
                    earliest=min(r['pair_quote']['observed_at'] for r in pairs if r['slug']==slug)
                    latest=max(r['pair_quote']['observed_at']+30 for r in pairs if r['slug']==slug)
                    if not earliest<=requested<=latest:continue
                    books[slug].append({'kind':kind,'requested_at':requested,'observed_at':observed,
                        'artifact':aid,'line':line_number,'sha256':hashline,
                        'raw':record.get('raw') if kind=='book' else None})
        path.unlink()
        if index%12==0:print(f'validated_archives={index}',flush=True)
    assert state is not None
    assert state['version']=='limitless-hourly-v1'
    for row in pairs:
        quote=row['pair_quote'];market=state['markets'][row['slug']]
        assert source_check[row['condition']]==1
        assert good_book(quote_raw[row['condition']],market)
        assert book_cost(quote_raw[row['condition']],quote['opposite_side'],D(quote['gross_shares']))==D(quote['quoted_cost_usdc'])
    for slug in statuses:statuses[slug].sort(key=lambda s:(s['observed_at'],s['artifact'],s['line']))
    result=replay(event['rows'],state,books,statuses,source_check)
    summary={}
    for phase in ('discovery','holdout'):
        rows=[r for r in result if r['phase']==phase]
        first_fills=[r for r in event['rows'] if r['phase']==phase and r['status']=='FILLED']
        pairs_filled=[r for r in rows if r['status']=='PAIRED_PAPER']
        policy_total=sum((D(r['settled_first_leg_pnl_usdc']) for r in first_fills),D(0))
        policy_total+=sum((D(r['paired_settled_pnl_usdc'])-D(r['first_leg_settled_pnl_usdc']) for r in pairs_filled),D(0))
        summary[phase]={'observed_pair_quotes':len(rows),'paired_paper_second_fills':len(pairs_filled),
            'all_first_leg_paper_fills':len(first_fills),
            'second_fail_reasons':dict(collections.Counter(r['reason'] for r in rows if r['reason'])),
            'paired_settled_pnl_usdc':str(sum((D(r['paired_settled_pnl_usdc']) for r in pairs_filled),D(0))),
            'one_sided_fallback_pnl_usdc':str(sum((D(r['settled_pnl_after_policy_usdc']) for r in rows if r['status']!='PAIRED_PAPER'),D(0))),
            'paired_quote_cohort_total_pnl_usdc':str(sum((D(r['settled_pnl_after_policy_usdc']) for r in rows),D(0))),
            'all_first_fills_with_second_policy_settled_pnl_usdc':str(policy_total),
            'active_hour_clusters':len({r['hour_cluster'] for r in rows})}
    output={'schema':'limitless-hourly-paired-attempt-shadow-v1',
        'protocol':'research/LIMITLESS_HOURLY_PAIRED_ATTEMPT_PROTOCOL_2026-10-08.md',
        'source_archive_count':len(manifest),'verified_pair_quote_sources':dict(source_check),
        'summary':summary,'rows':result,
        'note':'Quote-based paper execution proxy; old holdout reused, no actual orders.'}
    pathlib.Path(args.output).write_text(json.dumps(output,indent=2)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
