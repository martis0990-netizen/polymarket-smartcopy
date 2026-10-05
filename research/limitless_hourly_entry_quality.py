#!/usr/bin/env python3
"""Causal entry-quality audit of a pinned, fully reproduced hourly shadow.

Only reads public main capture ZIPs; no state writes, orders, or parameter search.
"""
import argparse
import collections
import gzip
import hashlib
import json
import math
import random
import statistics
import zipfile
from decimal import Decimal as D

from limitless_hourly_paper import levels

VERSION = 'limitless-hourly-entry-quality-v1'


def source_books(manifest, expected):
    wanted = collections.defaultdict(dict)
    for row in expected:
        for name in ('decision_proof', 'execution_proof'):
            if name in row:
                ref = row[name]
                key = (ref['artifact'], ref['line'])
                previous = wanted[key].get('sha256')
                if previous and previous != ref['sha256']:
                    raise ValueError('conflicting source fingerprint')
                wanted[key] = ref
    found = {}
    for item in manifest:
        art = item['artifact']['id']
        digest = hashlib.sha256(open(item['file']['path'], 'rb').read()).hexdigest()
        if 'sha256:' + digest != item['artifact']['digest']:
            raise ValueError('archive hash mismatch')
        with zipfile.ZipFile(item['file']['path']) as z:
            with gzip.GzipFile(fileobj=z.open('capture.jsonl.gz')) as f:
                for n, line in enumerate(f, 1):
                    key = art, n
                    if key in wanted:
                        sha = hashlib.sha256(line.rstrip(b'\n')).hexdigest()
                        if sha != wanted[key]['sha256']:
                            raise ValueError('source fingerprint mismatch')
                        found[key] = json.loads(line)
    if set(found) != set(wanted):
        raise ValueError('missing source books')
    return found


def analyze(manifest, shadow):
    if shadow.get('schema') != 'limitless-hourly-ewma30-all-raw-decisions-shadow-v1':
        raise ValueError('unexpected cohort')
    if len(manifest) != len(shadow['source_archives']):
        raise ValueError('archive count mismatch')
    if any((a['artifact']['id'], a['artifact']['digest']) !=
           (b['artifact'], 'sha256:' + b['sha256']) for a, b in zip(manifest, shadow['source_archives'])):
        raise ValueError('archive lineage mismatch')
    frozen = shadow['frozen']['rows']
    books = source_books(manifest, frozen)
    with zipfile.ZipFile(manifest[-1]['file']['path']) as z:
        state = json.loads(z.read('state.json'))['paper']
    if len(frozen) != shadow['frozen_exact_reproduction'] or len(frozen) != shadow['decisions']:
        raise ValueError('incomplete decisions')
    rows = []
    for action in frozen:
        ep = state['episodes'][action['condition']]
        spec = state['markets'][action['slug']]
        ref = action['decision_proof']
        raw = books[(ref['artifact'], ref['line'])]
        if raw['kind'] != 'book' or raw['slug'] != action['slug'] or raw['raw']['tokenId'] != spec['yes_token']:
            raise ValueError('wrong decision book')
        yes, no = levels(raw['raw'], 'YES'), levels(raw['raw'], 'NO')
        if not yes or not no or yes[0][0] + no[0][0] < 1:
            raise ValueError('invalid binary book')
        yes_bid = 1 - no[0][0]
        yes_ask = yes[0][0]
        market_mid = (yes_bid + yes_ask) / 2
        payout = ep.get('payout')
        if payout not in ([1.0, 0.0], [0.0, 1.0]):
            raise ValueError('unsettled or nonbinary condition')
        trade = action['status'] == 'SETTLED'
        if trade:
            pos = D(action['net_shares'])
            cost = D(action['cost_usdc'])
            if pos <= 0 or cost <= 0:
                raise ValueError('invalid settled trade')
            breakeven = cost / pos
            p_side = D(str(action['p_up'] if action['side'] == 'YES' else 1 - action['p_up']))
            fair_edge = p_side / breakeven - 1
            expected = pos * p_side - cost
            execution_ref = action['execution_proof']
            execution = books[(execution_ref['artifact'], execution_ref['line'])]
            if execution['kind'] != 'book' or execution['slug'] != action['slug']:
                raise ValueError('wrong execution book')
            first_decision_ask = yes_ask if action['side'] == 'YES' else no[0][0]
            vwap_delta = D(action['vwap']) - first_decision_ask
            reported = ep['variants']['model']
            if (reported['status'] != 'SETTLED' or D(reported['cost_usdc']) != cost
                    or D(reported['pnl_usdc']) != D(action['pnl_usdc'])):
                raise ValueError('state trade mismatch')
        else:
            fair_edge = expected = breakeven = vwap_delta = None
        rows.append({'condition': action['condition'], 'slug': action['slug'],
                     'symbol': action['symbol'], 'hour_start': ep['start'],
                     'decision_at': action['decision_at'], 'p_up': action['p_up'],
                     'yes_won': payout[0], 'market_mid': float(market_mid),
                     'yes_spread': str(yes_ask - yes_bid),
                     'status': action['status'], 'side': action.get('side'),
                     'net_shares': action.get('net_shares'),
                     'cost_usdc': action.get('cost_usdc'),
                     'pnl_usdc': action.get('pnl_usdc'),
                     'p_side_breakeven_after_fee': str(breakeven) if trade else None,
                     'forecast_net_edge_at_fill': str(fair_edge) if trade else None,
                     'forecast_ev_usdc_at_fill': str(expected) if trade else None,
                     'execution_vwap_minus_decision_best_ask': str(vwap_delta) if trade else None,
                     'decision_proof': ref,
                     'execution_proof': action.get('execution_proof')})
    scored = rows
    blocks = collections.defaultdict(list)
    for r in scored:
        blocks[r['hour_start']].append((r['p_up'] - r['yes_won']) ** 2 -
                                       (r['market_mid'] - r['yes_won']) ** 2)
    rng = random.Random(2105)
    groups = list(blocks.values())
    draws = sorted(sum(map(sum, sample)) / sum(map(len, sample))
                   for sample in (rng.choices(groups, k=len(groups)) for _ in range(10000)))
    by_asset = {}
    for symbol in ('BTCUSDT', 'ETHUSDT'):
        a = [r for r in rows if r['symbol'] == symbol]
        t = [r for r in a if r['status'] == 'SETTLED']
        by_asset[symbol] = {'decisions': len(a), 'settled_trades': len(t),
                            'model_brier': statistics.mean((r['p_up'] - r['yes_won']) ** 2 for r in a),
                            'market_mid_brier': statistics.mean((r['market_mid'] - r['yes_won']) ** 2 for r in a),
                            'settled_pnl_usdc': str(sum((D(r['pnl_usdc']) for r in t), D(0)))}
    return {'schema': VERSION, 'scope': 'discovery, exact raw matched main hourly decisions',
            'decisions': len(rows), 'hour_clusters': len(groups),
            'model_brier': statistics.mean((r['p_up'] - r['yes_won']) ** 2 for r in rows),
            'market_mid_brier': statistics.mean((r['market_mid'] - r['yes_won']) ** 2 for r in rows),
            'model_minus_market_brier': statistics.mean(sum(groups, [])),
            'cluster_bootstrap_95': [draws[249], draws[9749]],
            'bootstrap_seed': 2105, 'bootstrap_draws': 10000,
            'by_asset': by_asset, 'rows': rows,
            'source_archive_hashes': shadow['source_archives']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest')
    parser.add_argument('full_shadow')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    result = analyze(json.load(open(args.manifest)), json.load(open(args.full_shadow)))
    with open(args.out, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'source_archive_hashes')}))
