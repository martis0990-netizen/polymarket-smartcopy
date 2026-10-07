#!/usr/bin/env python3
"""Read-only causal M1 structure and market-baseline diagnostic for saved hourly paper."""
import argparse
import collections
import gzip
import hashlib
import json
import pathlib
import random
import statistics
import zipfile

from limitless_market_regime import MinuteStore, milliseconds, scan, swing_direction, digest


def run(manifest_path, state_zip, probability_path, full_regime_path=None):
    manifest = json.loads(pathlib.Path(manifest_path).read_text())
    probabilities = json.loads(pathlib.Path(probability_path).read_text())
    market = {r['condition']: r for r in probabilities['rows'] if r['phase'] == 'holdout'}
    store = MinuteStore()
    archives = []
    for item in manifest:
        run_meta, art = item['run'], item['artifact']
        if (run_meta['head_branch'] != 'main' or run_meta['event'] == 'pull_request'
                or run_meta['status'] != 'completed' or run_meta['conclusion'] != 'success'
                or run_meta['name'] != 'Limitless independent market capture'
                or art['workflow_run']['id'] != run_meta['id']
                or art['workflow_run']['head_sha'] != run_meta['head_sha']):
            raise ValueError('invalid main run lineage')
        path = pathlib.Path(item['file']['path'])
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if art['digest'] != 'sha256:' + sha:
            raise ValueError('artifact digest mismatch')
        archives.append({'run': run_meta['id'], 'artifact': art['id'], 'sha256': sha})
        with zipfile.ZipFile(path) as archive:
            with gzip.GzipFile(fileobj=archive.open('capture.jsonl.gz')) as stream:
                for line_number, line in enumerate(stream, 1):
                    if b'binance_1m' in line:
                        store.add(json.loads(line), {'artifact': art['id'], 'line': line_number})
    with zipfile.ZipFile(state_zip) as archive:
        state = json.loads(archive.read('state.json'))['paper']
    if pathlib.Path(state_zip).resolve() != pathlib.Path(manifest[-1]['file']['path']).resolve():
        raise ValueError('state ZIP is not final verified archive')
    if probabilities['source']['zip_sha256'] != archives[-1]['sha256']:
        raise ValueError('probability evidence does not belong to state ZIP')
    if state['version'] != 'limitless-hourly-v1':
        raise ValueError('wrong paper state')
    rows = []
    for condition, ep in sorted(state['episodes'].items()):
        if ep['phase'] != 'holdout' or 'brier_model' not in ep:
            continue
        q = market[condition]
        if (abs(q['p_up_model'] - ep['p_up']) > 1e-12 or q['realized_up'] != ep['payout'][0]
                or abs(q['brier_model'] - ep['brier_model']) > 1e-12):
            raise ValueError('probability or payout conflict')
        at_ms = milliseconds(ep['decision_at'])
        source, conflicting = store.view(ep['symbol'], at_ms)
        expected = int(at_ms // 60000) * 60000 - 60000
        end = {r['open_ms']: r for r in source}
        opens = list(range(expected - 120 * 60000, expected + 1, 60000))
        bars = [end[t] for t in opens if t in end]
        relevant_conflicts = [t for t in conflicting if opens[0] <= t <= expected]
        reason = None
        if relevant_conflicts:
            reason = 'CONFLICT_IN_121M_WINDOW'
        elif len(bars) != 121:
            reason = 'INCOMPLETE_121M_WINDOW'
        elif any(b['available_ms'] > at_ms or b['close_ms'] >= at_ms for b in bars):
            raise ValueError('future candle')
        geometry = scan(bars) if reason is None else None
        direction = swing_direction(geometry['swings']) if geometry else None
        group = ('HH_HL' if direction == 'UP' else 'LH_LL' if direction == 'DOWN'
                 else 'MIXED_OR_EQUAL' if geometry and len([s for s in geometry['swings'] if s['kind']=='HIGH']) >= 2
                 and len([s for s in geometry['swings'] if s['kind']=='LOW']) >= 2
                 else 'INSUFFICIENT_SWINGS' if geometry else 'UNKNOWN')
        rows.append({'condition': condition, 'symbol': ep['symbol'], 'hour_start': ep['start'],
                     'decision_at': ep['decision_at'], 'group': group, 'unknown_reason': reason,
                     'p_up_model': ep['p_up'], 'p_up_market_mid': q['p_up_market_mid'],
                     'realized_up': ep['payout'][0], 'brier_model': ep['brier_model'],
                     'brier_market_mid': q['brier_market_mid'],
                     'model_action_status': ep['variants']['model']['status'],
                     'market_book_proof': q['market_mid_decision_proof'],
                     'm1_window_sha256': digest(bars) if geometry else None,
                     'm1_first_source': bars[0]['provenance'] if geometry else None,
                     'm1_last_source': bars[-1]['provenance'] if geometry else None,
                     'last_two_highs': [s['price'] for s in geometry['swings'] if s['kind']=='HIGH'][-2:] if geometry else [],
                     'last_two_lows': [s['price'] for s in geometry['swings'] if s['kind']=='LOW'][-2:] if geometry else []})
    if len(rows) != len(market):
        raise ValueError('missing scored holdout decision')
    groups = {}
    for group in ('HH_HL', 'LH_LL', 'MIXED_OR_EQUAL', 'INSUFFICIENT_SWINGS', 'UNKNOWN'):
        subset = [r for r in rows if r['group'] == group]
        groups[group] = {'n': len(subset), 'hour_clusters': len({r['hour_start'] for r in subset}),
                         'model_brier': statistics.mean(r['brier_model'] for r in subset) if subset else None,
                         'market_brier': statistics.mean(r['brier_market_mid'] for r in subset) if subset else None,
                         'model_minus_market_brier': statistics.mean(r['brier_model']-r['brier_market_mid'] for r in subset) if subset else None,
                         'mean_model_confidence': statistics.mean(max(r['p_up_model'], 1-r['p_up_model']) for r in subset) if subset else None,
                         'model_favourite_correct': sum((r['p_up_model'] >= .5) == bool(r['realized_up']) for r in subset)}
    aligned = [r for r in rows if r['group'] in ('HH_HL', 'LH_LL')]
    mixed = [r for r in rows if r['group'] == 'MIXED_OR_EQUAL']
    contrast = (statistics.mean(r['brier_model'] for r in mixed)-statistics.mean(r['brier_model'] for r in aligned)
                if mixed and aligned else None)
    relative = (statistics.mean(r['brier_model']-r['brier_market_mid'] for r in mixed)
                -statistics.mean(r['brier_model']-r['brier_market_mid'] for r in aligned)
                if mixed and aligned else None)
    blocks = collections.defaultdict(list)
    for row in rows:
        blocks[row['hour_start']].append(row)
    rng = random.Random(20261007)
    hours = list(blocks)
    primary_draws, relative_draws = [], []
    for _ in range(10000):
        sample = [row for hour in rng.choices(hours, k=len(hours)) for row in blocks[hour]]
        m = [row for row in sample if row['group'] == 'MIXED_OR_EQUAL']
        a = [row for row in sample if row['group'] in ('HH_HL', 'LH_LL')]
        if m and a:
            primary_draws.append(statistics.mean(row['brier_model'] for row in m)
                                 - statistics.mean(row['brier_model'] for row in a))
            relative_draws.append(statistics.mean(row['brier_model']-row['brier_market_mid'] for row in m)
                                  - statistics.mean(row['brier_model']-row['brier_market_mid'] for row in a))
    primary_draws.sort()
    relative_draws.sort()
    def interval(draws):
        return [draws[int(.025*len(draws))], draws[int(.975*len(draws))-1]] if draws else None
    higher_frames = None
    if full_regime_path:
        full = json.loads(pathlib.Path(full_regime_path).read_text())
        if (full['status'] != 'RECONCILED_DIAGNOSTIC_ONLY'
                or [(x['id'], x['sha256']) for x in full['artifacts']]
                != [(x['artifact'], x['sha256']) for x in archives]
                or full['state_artifact'] != archives[-1]['artifact']):
            raise ValueError('full regime source lineage mismatch')
        by_condition = {r['condition']: r for r in full['results'] if r['phase'] == 'holdout'}
        if set(by_condition) != {r['condition'] for r in rows}:
            raise ValueError('full regime condition mismatch')
        higher_frames = {'ready_h4_h1': 0, 'by_frame': {}}
        for frame in ('H4', 'H1'):
            higher_frames['by_frame'][frame] = dict(collections.Counter(
                (by_condition[r['condition']]['frames'][frame]['state'],
                 by_condition[r['condition']]['frames'][frame]['reason']) for r in rows))
        higher_frames['by_frame'] = {frame: [{'state': state, 'reason': reason, 'n': n}
                                              for (state, reason), n in counts.items()]
                                     for frame, counts in higher_frames['by_frame'].items()}
        higher_frames['ready_h4_h1'] = sum(by_condition[r['condition']]['top_down_context'] == 'READY' for r in rows)
    return {'schema': 'limitless-hourly-structure-versus-market-diagnostic-2026-10-07',
            'status': 'RECONCILED_DIAGNOSTIC_ONLY' if not store.errors else 'UNRECONCILED',
            'report': {'scored_holdout': len(rows), 'hour_clusters': len({r['hour_start'] for r in rows}),
                       'groups': groups, 'predefined_model_brier_mixed_minus_aligned': contrast,
                       'incremental_relative_brier_mixed_minus_aligned': relative,
                       'predefined_contrast_cluster_bootstrap_95pct': interval(primary_draws),
                       'incremental_contrast_cluster_bootstrap_95pct': interval(relative_draws),
                       'bootstrap_seed': 20261007, 'bootstrap_draws': len(primary_draws),
                       'higher_frames': higher_frames,
                       'unknown_reasons': dict(collections.Counter(r['unknown_reason'] for r in rows if r['unknown_reason']))} if not store.errors else None,
            'source': {'state_artifact': archives[-1]['artifact'], 'archives': archives,
                       'classifier_sha256': hashlib.sha256(pathlib.Path(__file__).with_name('limitless_market_regime.py').read_bytes()).hexdigest(),
                       'probability_evidence': 'research/evidence/limitless_hourly_probability_audit_2026-10-07.json',
                       'probability_evidence_sha256': hashlib.sha256(pathlib.Path(probability_path).read_bytes()).hexdigest()},
            'binance_response_count': store.requests, 'data_errors': store.errors, 'rows': rows,
            'limitations': ['121 closed M1 bars only; H4/H1 hierarchy unavailable in this archive set',
                            'Mixed/aligned groups are small, time clustered and exploratory against market midpoint',
                            'No revised probability or retrospective PnL filter',
                            'Unknown and conflicting source rows remain visible']}


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--manifest', required=True)
    ap.add_argument('--state-zip', required=True)
    ap.add_argument('--probability-evidence', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--full-regime-evidence')
    args = ap.parse_args()
    result = run(args.manifest, args.state_zip, args.probability_evidence, args.full_regime_evidence)
    pathlib.Path(args.output).write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'status': result['status'], 'report': result['report']}))
