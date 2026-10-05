#!/usr/bin/env python3
"""Causal 50/50 model/decision-book midpoint shadow; offline and separately funded."""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import zipfile
from decimal import Decimal as D

from limitless_hourly_paper import levels
from limitless_hourly_ewma_full_shadow import replay, stamp

START = dt.datetime(2026, 10, 6, tzinfo=dt.timezone.utc).timestamp()
END = dt.datetime(2026, 10, 13, tzinfo=dt.timezone.utc).timestamp()
VERSION = 'limitless-hourly-market-blend50-prospective-shadow-v1'


def read_sources(manifest, shadow, wanted):
    if len(manifest) != len(shadow['source_archives']):
        raise ValueError('missing source archive')
    proofs = {(r['decision_proof']['artifact'], r['decision_proof']['line']): r['decision_proof']['sha256']
              for r in wanted}
    found, events = {}, collections.defaultdict(list)
    prior_end = None
    wanted_slugs = {r['slug'] for r in wanted}
    for item, pinned in zip(manifest, shadow['source_archives']):
        run, art = item['run'], item['artifact']
        if (run['name'] != 'Limitless independent market capture' or run['head_branch'] != 'main'
                or run['event'] == 'pull_request' or run['status'] != 'completed'
                or run['conclusion'] != 'success' or art['workflow_run']['id'] != run['id']
                or (art['id'], art['digest']) != (pinned['artifact'], 'sha256:' + pinned['sha256'])):
            raise ValueError('wrong main archive lineage')
        digest = hashlib.sha256(open(item['file']['path'], 'rb').read()).hexdigest()
        if digest != pinned['sha256']:
            raise ValueError('ZIP SHA256 mismatch')
        with zipfile.ZipFile(item['file']['path']) as z:
            summary = json.loads(z.read('summary.json'))
            start, end = stamp(summary['started_at']), stamp(summary['ended_at'])
            if start >= end or (prior_end is not None and (start < prior_end or start - prior_end > 1200)):
                raise ValueError('broken capture sequence')
            prior_end = end
            with gzip.GzipFile(fileobj=z.open('capture.jsonl.gz')) as f:
                for n, line in enumerate(f, 1):
                    key = art['id'], n
                    is_proof = key in proofs
                    if not is_proof and b'"kind":"book"' not in line and b'"kind":"request_error"' not in line:
                        continue
                    x = json.loads(line)
                    if not is_proof and x.get('slug') not in wanted_slugs:
                        continue
                    ref = {'artifact': art['id'], 'line': n,
                           'sha256': hashlib.sha256(line.rstrip(b'\n')).hexdigest()}
                    if is_proof:
                        if ref['sha256'] != proofs[key] or x['kind'] != 'book':
                            raise ValueError('first decision proof mismatch')
                        found[key] = (x, ref)
                    elif x['kind'] == 'book' or x.get('operation') == 'book':
                        events[x['slug']].append((x, ref))
    if set(found) != set(proofs):
        raise ValueError('missing decision book')
    return found, events


def analyze(manifest, shadow, cohort):
    if shadow.get('schema') != 'limitless-hourly-ewma30-all-raw-decisions-shadow-v1':
        raise ValueError('wrong frozen decision source')
    if cohort == 'prospective':
        wanted = [r for r in shadow['frozen']['rows'] if START <= r['decision_at'] < END]
    else:
        wanted = list(shadow['frozen']['rows'])
    if not wanted:
        return {'schema': VERSION, 'cohort': cohort, 'status': 'WAITING_FOR_PROSPECTIVE_DECISIONS',
                'decision_start_utc': '2026-10-06T00:00:00Z',
                'decision_end_exclusive_utc': '2026-10-13T00:00:00Z',
                'source_archives': shadow['source_archives'], 'report': None}
    found, events = read_sources(manifest, shadow, wanted)
    with zipfile.ZipFile(manifest[-1]['file']['path']) as z:
        state = json.loads(z.read('state.json'))['paper']
    books, rows = {}, []
    for orig in wanted:
        condition = orig['condition']
        proof = orig['decision_proof']
        x, ref = found[(proof['artifact'], proof['line'])]
        spec = state['markets'][orig['slug']]
        if (x['slug'] != orig['slug'] or x['raw']['tokenId'] != spec['yes_token']
                or not 0 <= orig['decision_at'] - stamp(x['observed_at']) < .02):
            raise ValueError('wrong decision slug/token')
        yes, no = levels(x['raw'], 'YES'), levels(x['raw'], 'NO')
        if not yes or not no or yes[0][0] + no[0][0] < 1:
            raise ValueError('invalid decision book')
        mid = ((1 - no[0][0]) + yes[0][0]) / 2
        if not 0 < mid < 1:
            raise ValueError('invalid market midpoint')
        blend = (D(str(orig['p_up'])) + mid) / 2
        books[condition] = x, ref
        rows.append({**orig, 'p_blend50': float(blend), 'market_mid': str(mid),
                     # replay() selects this field for its non-frozen case.
                     'p_ewma30': float(blend)})
    baseline = replay('frozen', rows, state['episodes'], state['markets'], books, events)
    alternative = replay('market_blend50', rows, state['episodes'], state['markets'], books, events)
    if cohort == 'discovery-sanity':
        for row in baseline['rows']:
            original = next(x for x in wanted if x['condition'] == row['condition'])
            if row['status'] != original['status']:
                raise ValueError('historical frozen reproduction mismatch')
    if cohort == 'discovery-sanity':
        status = 'RETROSPECTIVE_SANITY_ONLY'
    elif (stamp(shadow['source_archives'][-1]['ended_at']) < END + 3600
          or baseline['pending_cost'] != '0' or alternative['pending_cost'] != '0'):
        status = 'COLLECTING_PAPER_ONLY'
    elif alternative['states'].get('SETTLED', 0) < 30:
        status = 'INSUFFICIENT_DATA'
    else:
        status = 'EVALUABLE_PAPER_ONLY'
    return {'schema': VERSION, 'cohort': cohort,
            'status': status,
            'decision_start_utc': '2026-10-06T00:00:00Z',
            'decision_end_exclusive_utc': '2026-10-13T00:00:00Z',
            'fixed_weight_model': '0.5', 'fixed_weight_market_mid': '0.5',
            'source_archives': shadow['source_archives'], 'decisions': len(rows),
            'first_decision_at': min(r['decision_at'] for r in rows),
            'last_decision_at': max(r['decision_at'] for r in rows),
            'decision_inputs': [{k: r[k] for k in ('condition', 'slug', 'decision_at', 'p_up',
                                                   'market_mid', 'p_blend50', 'decision_proof')} for r in rows],
            'frozen_funded': baseline, 'blend50_funded': alternative}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('full_shadow')
    parser.add_argument('--cohort', choices=['prospective', 'discovery-sanity'], default='prospective')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = analyze(json.load(open(args.manifest)), json.load(open(args.full_shadow)), args.cohort)
    with open(args.out, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: ({a: b for a, b in v.items() if a != 'rows'} if isinstance(v, dict) else v)
                      for k, v in result.items() if k not in ('decision_inputs', 'source_archives')}))
