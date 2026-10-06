#!/usr/bin/env python3
"""Offline hourly volatility challenger on an already verified discovery cohort.

Reads public capture ZIPs and a pinned decision/market evidence JSON. Does not
write paper state, change admission decisions, fetch network data or place orders.
"""
import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
import random
import statistics
import zipfile

from limitless_hourly_paper import probability

HALF_LIFE = 30  # closed 1m returns; fixed before inspecting challenger results
VERSION = 'limitless-hourly-ewma30-shadow-v1'


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('naive timestamp')
    return parsed.timestamp()


def ewma_sigma(closes):
    returns = [math.log(b / a) for a, b in zip(closes, closes[1:])]
    if len(returns) != 120:
        raise ValueError('missing 120 closed returns')
    weights = [2 ** (-age / HALF_LIFE) for age in reversed(range(len(returns)))]
    total = sum(weights)
    mean = sum(w * x for w, x in zip(weights, returns)) / total
    denominator = total - sum(w * w for w in weights) / total
    sigma = math.sqrt(sum(w * (x - mean) ** 2 for w, x in zip(weights, returns)) / denominator)
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError('invalid EWMA volatility')
    return sigma


def analyze(manifest, evidence):
    if evidence.get('schema') != 'limitless-hourly-decision-market-comparison-v1':
        raise ValueError('unexpected baseline evidence')
    wanted = {row['condition']: row for row in evidence['rows']}
    if len(wanted) != len(evidence['rows']):
        raise ValueError('duplicate condition')
    found = collections.defaultdict(list)
    proof_wanted = {(r['proof']['artifact'], r['proof']['line']): r['proof']['sha256']
                    for r in evidence['rows']}
    proof_wanted.update({(r['resolution_proof']['artifact'], r['resolution_proof']['line']):
                         r['resolution_proof']['sha256'] for r in evidence['rows']
                         if r.get('resolution_proof')})
    proof_seen = set()
    prior_end = None
    sources = []
    for item in manifest:
        run, art = item['run'], item['artifact']
        if (run['head_branch'] != 'main' or run['event'] == 'pull_request'
                or run['status'] != 'completed' or run['conclusion'] != 'success'
                or run['name'] != 'Limitless independent market capture'
                or run['id'] != art['workflow_run']['id']):
            raise ValueError('not a successful main capture')
        path = item['file']['path']
        digest = hashlib.sha256(open(path, 'rb').read()).hexdigest()
        if art['digest'] != 'sha256:' + digest:
            raise ValueError('ZIP digest mismatch')
        with zipfile.ZipFile(path) as z:
            summary = json.loads(z.read('summary.json'))
            begin, end = timestamp(summary['started_at']), timestamp(summary['ended_at'])
            if begin >= end or (prior_end is not None and (begin < prior_end or begin-prior_end > 1200)):
                raise ValueError('broken capture chronology')
            prior_end = end
            state = json.loads(z.read('state.json'))['paper']
            with gzip.GzipFile(fileobj=z.open('capture.jsonl.gz')) as stream:
                for line_no, line in enumerate(stream, 1):
                    key = (art['id'], line_no)
                    if key in proof_wanted:
                        if hashlib.sha256(line.rstrip(b'\n')).hexdigest() != proof_wanted[key]:
                            raise ValueError('decision/resolution proof mismatch')
                        proof_seen.add(key)
                    if b'"kind":"binance_1m"' not in line:
                        continue
                    row = json.loads(line)
                    symbol = row.get('params', {}).get('symbol')
                    received = timestamp(row['observed_at'])
                    for condition, base in wanted.items():
                        ep = state['episodes'].get(condition)
                        if (ep and ep.get('symbol') == symbol
                                and abs(received-ep['reference_observed_at']) < .02):
                            found[condition].append((row, art['id'], line_no,
                                                      hashlib.sha256(line.rstrip(b'\n')).hexdigest()))
        sources.append({'run': run['id'], 'artifact': art['id'], 'sha256': digest,
                        'ended_at': summary['ended_at']})
    if proof_seen != set(proof_wanted):
        raise ValueError('missing pinned book/resolution proofs')
    if (len(sources) != len(evidence['sources'])
            or any((s['artifact'], s['sha256']) != (e['artifact'], e['sha256'])
                   for s, e in zip(sources, evidence['sources']))):
        raise ValueError('baseline evidence source mismatch')
    if sources[-1]['artifact'] != evidence['decision_state_artifact']:
        raise ValueError('baseline evidence state mismatch')
    rows = []
    for condition, base in wanted.items():
        ep = state['episodes'][condition]
        matches = found[condition]
        if len(matches) != 1 or abs(ep['decision_at']-base['decision_at']) > .001:
            raise ValueError('missing or ambiguous Binance receipt for ' + condition)
        src, art, line, sha = matches[0]
        if src.get('source') != 'binance' or src.get('path') != '/api/v3/klines':
            raise ValueError('unverified Binance source')
        raw = src['raw']
        now, request = ep['decision_at'], timestamp(src['requested_at'])
        current = [r for r in raw if float(r[0]) / 1000 <= now <= float(r[6]) / 1000]
        if len(current) != 1 or abs(float(current[0][4])-ep['reference_price']) > 1e-8:
            raise ValueError('current reference mismatch')
        p, sigma = probability(raw, {'price': ep['reference_price'], 'end': ep['start'] + 3600},
                               ep['opening'], now, request)
        if abs(p-ep['p_up']) > 1e-12 or abs(sigma-ep['sigma_1m']) > 1e-12:
            raise ValueError('frozen model could not be reproduced')
        closed = sorted((r for r in raw if float(r[6])/1000 < min(now, request)),
                        key=lambda r: r[0])[-121:]
        alternative_sigma = ewma_sigma([float(r[4]) for r in closed])
        remaining = (ep['start'] + 3600-now) / 60
        z = math.log(ep['reference_price']/float(ep['opening'])) / (alternative_sigma * math.sqrt(remaining))
        alternative_p = .5 * (1 + math.erf(z/math.sqrt(2)))
        rows.append({**base, 'sigma_original': sigma, 'sigma_ewma30': alternative_sigma,
                     'p_ewma30': alternative_p,
                     'reference_proof': {'artifact': art, 'line': line, 'sha256': sha}})
    scored = [r for r in rows if r['yes_won'] is not None]
    if not scored:
        raise ValueError('no scored decisions')
    blocks = collections.defaultdict(list)
    for row in scored:
        y = row['yes_won']
        blocks[row['hour_start']].append((row['p_ewma30']-y)**2-(row['p_up']-y)**2)
    rng = random.Random(1030)
    groups = list(blocks.values())
    draws = []
    for _ in range(10000):
        sample = rng.choices(groups, k=len(groups))
        draws.append(sum(map(sum, sample))/sum(map(len, sample)))
    draws.sort()
    by_asset = {}
    for asset in ('BTCUSDT', 'ETHUSDT'):
        subset = [r for r in scored if r['symbol'] == asset]
        by_asset[asset] = {'scored': len(subset),
                           'baseline_brier': statistics.mean((r['p_up']-r['yes_won'])**2 for r in subset),
                           'ewma30_brier': statistics.mean((r['p_ewma30']-r['yes_won'])**2 for r in subset)}
    return {'schema': VERSION, 'status': 'RETROSPECTIVE_DISCOVERY_NO_TRADES',
            'source_archives': sources, 'half_life_closed_1m_returns': HALF_LIFE,
            'variance_method': 'exponential_weighted_sample_variance_effective_dof',
            'zero_drift_unchanged': True, 'exact_baseline_reproduction': len(rows),
            'matched_scored': len(scored), 'clusters': len(groups),
            'baseline_brier': statistics.mean((r['p_up']-r['yes_won'])**2 for r in scored),
            'ewma30_brier': statistics.mean((r['p_ewma30']-r['yes_won'])**2 for r in scored),
            'market_mid_brier': statistics.mean((r['market_mid']-r['yes_won'])**2 for r in scored),
            'delta_ewma_minus_baseline': statistics.mean(sum(groups, [])),
            'cluster_bootstrap_95': [draws[249], draws[9749]],
            'bootstrap_seed': 1030, 'bootstrap_draws': 10000,
            'by_asset': by_asset, 'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', help='Local JSON manifest with verified main ZIP paths')
    parser.add_argument('baseline_evidence', help='Pinned hourly model/market evidence JSON')
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    with open(args.manifest) as file:
        manifest = json.load(file)
    with open(args.baseline_evidence) as file:
        evidence = json.load(file)
    result = analyze(manifest, evidence)
    with open(args.out, 'w') as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
        file.write('\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'source_archives')}))
