#!/usr/bin/env python3
"""Offline EWMA30 paper replay over all verifiable hourly decisions, without state writes."""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
import zipfile
from decimal import Decimal as D, ROUND_DOWN

from limitless_hourly_paper import BUDGET, FEE, HURDLE, MICRO, fill, levels, probability
from limitless_hourly_ewma_shadow import ewma_sigma


def stamp(s):
    parsed = dt.datetime.fromisoformat(s.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('naive source timestamp')
    return parsed.timestamp()


def proof(art, n, line):
    return {'artifact': art, 'line': n, 'sha256': hashlib.sha256(line.rstrip(b'\n')).hexdigest()}


def opportunity(book, p):
    choices = []
    for side, chance in [('YES', p), ('NO', 1 - p)]:
        cap = D(str(chance)) * (1 - FEE) / (1 + HURDLE)
        if cap <= 0:
            continue
        qty = (BUDGET / cap).quantize(MICRO, rounding=ROUND_DOWN)
        trade = fill(book, side, cap, qty)
        if trade:
            edge = D(trade['net_shares']) * D(str(chance)) / D(trade['cost_usdc']) - 1
            choices.append((edge, side, cap, qty))
    return max(choices, key=lambda a: (a[0], a[1])) if choices else None


def replay(name, rows, episodes, markets, books, events):
    cash, spent, payouts, realized = D(100), D(0), D(0), D(0)
    positions, actions = {}, []
    for row in rows:
        e, spec = episodes[row['condition']], markets[row['slug']]
        b = books[row['condition']][0]['raw']
        if b.get('tokenId') != spec['yes_token']:
            raise ValueError('decision book token mismatch')
        yes, no = levels(b, 'YES'), levels(b, 'NO')
        if not yes or not no or yes[0][0] + no[0][0] < 1:
            raise ValueError('invalid decision book')
        p = row['p_up'] if name == 'frozen' else row['p_ewma30']
        choice = opportunity(b, p)
        a = {'condition': e['condition'], 'slug': row['slug'], 'symbol': e['symbol'],
             'decision_at': e['decision_at'], 'p_up': p,
             'status': 'NO_TRADE' if not choice else 'PENDING',
             'decision_proof': row['decision_proof']}
        if choice:
            _, side, cap, qty = choice
            a.update(side=side, cap=str(cap), shares=str(qty))
            eligible = e['decision_at'] + spec['delay_s']
            attempts = []
            for raw, ref in events[row['slug']]:
                requested = stamp(raw['requested_at'])
                received = stamp(raw['observed_at'])
                if requested >= eligible:
                    attempts.append((requested, received, raw, ref))
            attempts.sort(key=lambda x: (x[0], x[1]))
            if not attempts or attempts[0][1] > e['decision_at'] + 30:
                a.update(status='SKIP', reason='MISSED_FIRST_ATTEMPT')
            else:
                _, at, raw, ref = attempts[0]
                a['execution_proof'] = ref
                if raw['kind'] == 'request_error':
                    a.update(status='SKIP', reason='FIRST_ERROR')
                else:
                    b = raw['raw']
                    yes, no = levels(b, 'YES'), levels(b, 'NO')
                    if b.get('tokenId') != spec['yes_token'] or not yes or not no or yes[0][0] + no[0][0] < 1:
                        a.update(status='SKIP', reason='INVALID_EXECUTION_BOOK')
                    else:
                        trade = fill(b, side, cap, qty)
                        if trade:
                            a.update(status='READY', fill_at=at, **trade)
                        else:
                            a.update(status='SKIP', reason='DEPTH_OR_PRICE_BOUND_FAILED')
        actions.append((e, a))
    transitions = []
    for e, a in actions:
        if a['status'] == 'READY':
            transitions.append((a['fill_at'], 1, e, a))
        if e.get('settled_at'):
            transitions.append((e['settled_at'], 0, e, a))
    for _, kind, e, a in sorted(transitions, key=lambda x: (x[0], x[1], x[2]['condition'])):
        if kind == 1:
            cost = D(a['cost_usdc'])
            if cost > cash:
                a.update(status='NO_TRADE', reason='INSUFFICIENT_CASH')
                continue
            cash -= cost
            spent += cost
            a['status'] = 'FILLED'
            positions[e['condition']] = D(a['net_shares']), cost, a['side']
        else:
            pos = positions.get(e['condition'])
            if pos and a['status'] == 'FILLED':
                net, cost, side = pos
                payout = net * D(str(e['payout'][0 if side == 'YES' else 1]))
                cash += payout
                payouts += payout
                realized += payout - cost
                a.update(status='SETTLED', payout_usdc=str(payout), pnl_usdc=str(payout - cost))
    plain = [a for _, a in actions]
    pending = sum((D(a['cost_usdc']) for a in plain if a['status'] == 'FILLED'), D(0))
    if cash + pending != D(100) + realized:
        raise ValueError('cash conservation failed')
    return {'cash': str(cash), 'spent': str(spent), 'payouts': str(payouts),
            'realized': str(realized), 'pending_cost': str(pending),
            'states': dict(collections.Counter(a['status'] for a in plain)), 'rows': plain}


def analyze(manifest):
    source_archives = []
    prev_end = None
    with zipfile.ZipFile(manifest[-1]['file']['path']) as z:
        state = json.loads(z.read('state.json'))['paper']
    episodes, markets = state['episodes'], state['markets']
    wanted = {e['slug']: e for e in episodes.values() if e.get('decision_at')}
    books, references, events = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for item in manifest:
        run, art = item['run'], item['artifact']
        if (run['name'] != 'Limitless independent market capture'
                or run['head_branch'] != 'main' or run['event'] == 'pull_request'
                or run['status'] != 'completed' or run['conclusion'] != 'success'
                or art['workflow_run']['id'] != run['id']):
            raise ValueError('non-main or incomplete archive')
        path = item['file']['path']
        digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()
        if art['digest'] != 'sha256:' + digest:
            raise ValueError('archive digest mismatch')
        with zipfile.ZipFile(path) as z:
            summary = json.loads(z.read('summary.json'))
            start, end = stamp(summary['started_at']), stamp(summary['ended_at'])
            if start >= end or (prev_end is not None and (start < prev_end or start - prev_end > 1200)):
                raise ValueError('capture sequence gap or overlap')
            prev_end = end
            with gzip.GzipFile(fileobj=z.open('capture.jsonl.gz')) as stream:
                for n, line in enumerate(stream, 1):
                    if b'"kind":"book"' not in line and b'"kind":"request_error"' not in line and b'"kind":"binance_1m"' not in line:
                        continue
                    x = json.loads(line)
                    ref = proof(art['id'], n, line)
                    if x['kind'] == 'binance_1m':
                        symbol = x.get('params', {}).get('symbol')
                        at = stamp(x['observed_at'])
                        for e in wanted.values():
                            if e['symbol'] == symbol and abs(at - e['reference_observed_at']) < .02:
                                references[e['condition']].append((x, ref))
                    elif x.get('slug') in wanted:
                        e = wanted[x['slug']]
                        if x['kind'] == 'book' and 0 <= e['decision_at'] - stamp(x['observed_at']) < .02:
                            books[e['condition']].append((x, ref))
                        elif x['kind'] == 'book' or x.get('operation') == 'book':
                            events[x['slug']].append((x, ref))
        source_archives.append({'run': run['id'], 'artifact': art['id'], 'sha256': digest,
                                'started_at': summary['started_at'], 'ended_at': summary['ended_at']})
    rows = []
    missing = []
    for e in sorted(wanted.values(), key=lambda a: a['decision_at']):
        bs, rs = books[e['condition']], references[e['condition']]
        if len(bs) != 1 or len(rs) != 1:
            missing.append({'condition': e['condition'], 'decision_books': len(bs), 'binance_receipts': len(rs)})
            continue
        source, ref = rs[0]
        if source.get('source') != 'binance' or source.get('path') != '/api/v3/klines':
            raise ValueError('unverified Binance source')
        raw = source['raw']
        now, request = e['decision_at'], stamp(source['requested_at'])
        current = [r for r in raw if float(r[0]) / 1000 <= now <= float(r[6]) / 1000]
        if len(current) != 1 or abs(float(current[0][4]) - e['reference_price']) > 1e-8:
            raise ValueError('current reference mismatch')
        p, sigma = probability(raw, {'price': e['reference_price'], 'end': e['start'] + 3600},
                               e['opening'], now, request)
        if abs(p - e['p_up']) > 1e-12 or abs(sigma - e['sigma_1m']) > 1e-12:
            raise ValueError('frozen forecast mismatch')
        closed = sorted((r for r in raw if float(r[6]) / 1000 < min(now, request)),
                        key=lambda r: r[0])[-121:]
        alternative_sigma = ewma_sigma([float(r[4]) for r in closed])
        z = math.log(e['reference_price'] / float(e['opening'])) / (
            alternative_sigma * math.sqrt((e['start'] + 3600 - now) / 60))
        alternative_p = .5 * (1 + math.erf(z / math.sqrt(2)))
        rows.append({'condition': e['condition'], 'slug': e['slug'], 'symbol': e['symbol'],
                     'decision_at': now, 'p_up': e['p_up'], 'p_ewma30': alternative_p,
                     'sigma_ewma30': alternative_sigma, 'decision_proof': bs[0][1],
                     'reference_proof': ref})
    if missing:
        raise ValueError('raw decision coverage missing: ' + json.dumps(missing))
    base = replay('frozen', rows, episodes, markets, {r['condition']: books[r['condition']][0] for r in rows}, events)
    alt = replay('ewma30', rows, episodes, markets, {r['condition']: books[r['condition']][0] for r in rows}, events)
    for row in base['rows']:
        a = episodes[row['condition']]['variants']['model']
        if row['status'] != a['status']:
            raise ValueError('frozen action mismatch: ' + row['condition'] + ' ' + row['status'] + ' ' + a['status'])
        if row['status'] == 'SETTLED' and (D(row['cost_usdc']) != D(a['cost_usdc'])
                                           or D(row['pnl_usdc']) != D(a['pnl_usdc'])):
            raise ValueError('frozen cost/payout mismatch')
    return {'schema': 'limitless-hourly-ewma30-all-raw-decisions-shadow-v1',
            'status': 'RETROSPECTIVE_ONLY', 'source_archives': source_archives,
            'state_artifact': source_archives[-1]['artifact'], 'decisions': len(rows),
            'frozen_exact_reproduction': len(rows), 'frozen': base, 'ewma30': alt}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = analyze(json.load(open(args.manifest)))
    with open(args.out, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: {v: x for v, x in result[k].items() if v != 'rows'} for k in ('frozen', 'ewma30')}))
