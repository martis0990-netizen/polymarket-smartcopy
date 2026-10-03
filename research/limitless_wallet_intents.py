#!/usr/bin/env python3
"""Retrospective observed-action traces. Never asserts flat initial inventory or copy eligibility."""
import argparse
import collections
import gzip
import json
import pathlib
from limitless_wallet_discovery import event_key
from limitless_smartcopy_probe import metadata, parse_time


def trace(rows, history_status):
    # Earliest receipt per immutable event. Mutable market resolution is never used.
    unique = {}
    for row, observed_at in rows:
        key = event_key(row)
        if key not in unique or observed_at < unique[key][1]:
            unique[key] = (row, observed_at)
    conditions, excluded = collections.defaultdict(list), []
    for key, (row, observed_at) in unique.items():
        meta = metadata(row)
        try:
            at = parse_time(meta['occurred_at'])
        except (ValueError, TypeError, OverflowError, OSError):
            at = None
        condition = meta['condition_id'] or (row.get('market') or {}).get('id')
        if at is None or condition is None:
            excluded.append({'event_id': key, 'reason': 'UNKNOWN_CONDITION_OR_SOURCE_TIME'})
            continue
        conditions[str(condition)].append({
            'event_id': key, 'source_time': at.isoformat(), 'history_observed_at': observed_at,
            'operation': meta['operation'], 'outcome': meta['outcome'],
            'execution_type': meta['entry_type'], 'order_id': meta['order_id'],
            'outcome_basis': meta['outcome_basis'],
            'raw_quantity': row.get('outcomeTokenAmount'),
            'raw_outcome_quantities': row.get('outcomeTokenAmounts'),
            'raw_collateral_amount': row.get('collateralAmount')})
    result = []
    for condition, events in sorted(conditions.items()):
        batches = collections.defaultdict(list)
        orders = collections.defaultdict(list)
        for event in events:
            batches[event['source_time']].append(event)
            if event['operation'] in ('BUY', 'SELL') and event['order_id'] and event['outcome']:
                orders[(event['order_id'], event['operation'], event['outcome'])].append(event)
        previous_buy_sides = set()
        timeline, flags = [], {'INITIAL_INVENTORY_UNKNOWN', 'RETROSPECTIVE_NOT_A_FORWARD_SIGNAL'}
        for at, batch in sorted(batches.items()):
            actions = []
            batch_buy_sides = {e['outcome'] for e in batch if e['operation'] == 'BUY' and e['outcome']}
            if len(batch_buy_sides) == 2:
                flags.add('BOTH_SIDE_BUYS_SAME_TIMESTAMP_ORDER_UNKNOWN')
            for event in sorted(batch, key=lambda x: x['event_id']):
                operation, side = event['operation'], event['outcome']
                if operation == 'BUY' and side:
                    if len(batch_buy_sides) == 2:
                        action = 'BOTH_SIDE_BUY_BATCH'
                    elif previous_buy_sides - {side}:
                        action = 'BUY_SIDE_PREVIOUSLY_OPPOSITE_BUY_SEEN'
                    elif side in previous_buy_sides:
                        action = 'REPEATED_OBSERVED_SIDE_BUY'
                    else:
                        action = 'FIRST_OBSERVED_SIDE_BUY_NOT_CONFIRMED_ENTER'
                elif operation == 'SELL' and side:
                    action = 'OBSERVED_SELL_REDUCE_OR_EXIT_UNKNOWN'
                elif operation == 'MERGE':
                    action = 'OBSERVED_MERGE_QUANTITY_SEMANTICS_UNVERIFIED'
                    flags.add('MERGE_PREVENTS_SIMPLE_DIRECTIONAL_COPY')
                elif operation == 'SPLIT':
                    action = 'OBSERVED_SPLIT_ADDS_PAIRED_EXPOSURE'
                    flags.add('SPLIT_PREVENTS_SIMPLE_DIRECTIONAL_COPY')
                elif operation == 'CLAIM':
                    action = 'REDEMPTION_NOT_PROFIT_OR_INDEPENDENT_WIN'
                elif operation in ('BUY', 'SELL'):
                    action = 'UNKNOWN_SIDE_TRADE_SKIP'
                    flags.add('UNKNOWN_SIDE')
                else:
                    action = 'UNKNOWN_OPERATION_SKIP'
                    flags.add('UNKNOWN_OPERATION')
                if str(event['execution_type']).upper().startswith('LIMIT '):
                    flags.add('MAKER_PRICE_NOT_FOLLOWER_ENTRY_PRICE')
                actions.append({**event, 'observed_action': action})
            # No ordering is invented inside an equal-source-time batch.
            timeline.append({'source_time': at, 'within_batch_order': 'UNKNOWN' if len(batch) > 1 else 'SINGLE_RECORD',
                             'actions': actions})
            previous_buy_sides.update(batch_buy_sides)
        if len(previous_buy_sides) == 2:
            flags.add('BOTH_SIDES_BOUGHT_IN_HISTORY_NOT_PROOF_OF_HEDGE')
        groups = []
        for key, fills in sorted(orders.items()):
            groups.append({'order_id': key[0], 'operation': key[1], 'outcome': key[2],
                           'fill_events': len(fills), 'event_ids': [e['event_id'] for e in fills],
                           'source_time_span': [min(e['source_time'] for e in fills), max(e['source_time'] for e in fills)]})
        result.append({'condition': condition, 'initial_inventory': 'UNKNOWN',
                       'final_inventory': 'UNKNOWN', 'independent_intents': None,
                       'strategy': 'UNKNOWN', 'smartcopy_action': 'SKIP_UNQUALIFIED_STRATEGY',
                       'flags': sorted(flags), 'order_side_groups': groups, 'timeline': timeline})
    return {'history_status': history_status, 'unique_events': len(unique), 'excluded_events': excluded,
            'conditions': result, 'copy_pnl': None,
            'limitations': ['Complete available API history does not prove zero starting inventory or complete transfers/fees.',
                'A repeated buy is not necessarily ADD; a sell is not necessarily EXIT.',
                'Same-timestamp execution order is unknown; event ID sorting is display only.',
                'No inventory, merge size, return, profit, win rate or copy decision is inferred from raw amounts.',
                'Later opposing purchases must not retroactively filter an earlier forward trade.',
                'Order-side groups are fill aggregation, not independent economic intentions.']}


def run(args):
    out = pathlib.Path(args.out)
    profiles = json.loads((out / 'profile.json').read_text())
    rows = collections.defaultdict(list)
    with gzip.open(out / 'profile_requests.jsonl.gz', 'rt') as archive:
        for line in archive:
            envelope = json.loads(line)
            path = envelope['path'].split('/')
            if len(path) != 4 or path[1] != 'portfolio' or path[3] != 'history':
                continue
            payload = envelope.get('payload')
            if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                continue
            for row in payload['data']:
                if isinstance(row, dict):
                    rows[path[2]].append((row, envelope['response_observed_at']))
    wallets = [{'account': w['account'], 'analysis_observed_at': profiles['generated_at'],
                **trace(rows[w['account']], w['history_status'])} for w in profiles['wallets']]
    report = {'schema': 'limitless-observed-action-traces-v1',
              'status': 'RETROSPECTIVE_DIAGNOSTIC_NOT_PAPER_EXECUTION', 'wallets': wallets}
    (out / 'intent_traces.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Observed wallet action traces', '', report['status'], '',
             '| Wallet | Conditions | Both-side histories | Merge conditions | Order-side groups |',
             '|---|---:|---:|---:|---:|']
    for wallet in wallets:
        conditions = wallet['conditions']
        both = sum('BOTH_SIDES_BOUGHT_IN_HISTORY_NOT_PROOF_OF_HEDGE' in c['flags'] for c in conditions)
        merges = sum('MERGE_PREVENTS_SIMPLE_DIRECTIONAL_COPY' in c['flags'] for c in conditions)
        groups = sum(len(c['order_side_groups']) for c in conditions)
        lines.append(f"| `{wallet['account']}` | {len(conditions)} | {both} | {merges} | {groups} |")
    lines += ['', 'Initial/final inventory, independent intentions and strategy remain UNKNOWN. No wallet or action is qualified for copying.',
              'These are retrospective sequences; later events cannot be used to reject earlier forward decisions.']
    (out / 'intent_traces.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({'wallets': len(wallets), 'status': report['status']}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='limitless_discovery')
    run(parser.parse_args())
