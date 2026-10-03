#!/usr/bin/env python3
"""Bounded descriptive history profiles, selected by activity, never historical PnL."""
import argparse
import collections
import gzip
import json
import pathlib
import time
from limitless_wallet_discovery import Client, items, event_key, now
from limitless_smartcopy_probe import metadata, parse_time


def profile(rows):
    unique = {event_key(row): row for row in rows}
    types, families = collections.Counter(), collections.Counter()
    conditions, sides, orders = set(), collections.defaultdict(set), set()
    unknown_side, missing_order, maker_buys, taker_buys, buy_events = 0, 0, 0, 0, 0
    source_times = []
    for uid, row in unique.items():
        meta = metadata(row)
        title = meta['title'].lower()
        family = ('BTC' if 'btc' in title or 'bitcoin' in title else 'ETH' if 'eth' in title or 'ethereum' in title else 'OTHER')
        horizon = '15M' if '15 min' in title else 'HOURLY' if 'hourly' in title else 'OTHER'
        families[family + '_' + horizon] += 1
        types[str(meta['entry_type'])] += 1
        condition = meta['condition_id'] or (row.get('market') or {}).get('id')
        if condition is not None:
            condition = str(condition)
            conditions.add(condition)
        at = parse_time(meta['occurred_at'])
        if at:
            source_times.append(at)
        if meta['operation'] in ('BUY', 'SELL'):
            if meta['order_id'] and condition is not None and meta['outcome'] is not None:
                orders.add((condition, str(meta['order_id']), meta['operation'], meta['outcome']))
            else:
                missing_order += 1
            unknown_side += meta['outcome'] is None
        if meta['operation'] == 'BUY':
            buy_events += 1
            maker_buys += str(meta['entry_type']).upper() == 'LIMIT BUY'
            taker_buys += str(meta['entry_type']).upper() == 'MARKET BUY'
            if condition is not None and meta['outcome'] is not None:
                sides[condition].add(meta['outcome'])
    both = sum(len(x) == 2 for x in sides.values())
    flags = []
    if maker_buys:
        flags.append('MAKER_ENTRIES_REQUIRE_NEW_EXECUTABLE_FOLLOWER_PRICE')
    if both:
        flags.append('BOTH_OUTCOMES_BOUGHT_IN_SAMPLE_STRATEGY_AMBIGUOUS')
    if types.get('Claim'):
        flags.append('REDEMPTIONS_PRESENT_NOT_SELL_TRADES_OR_PROFIT')
    return {'unique_events': len(unique), 'sampled_conditions': len(conditions),
            'execution_types': dict(types), 'event_families': dict(families),
            'buy_events': buy_events, 'maker_buy_events': maker_buys, 'taker_buy_events': taker_buys,
            'buy_conditions_with_both_outcomes': both,
            'order_side_groups': len(orders), 'trade_events_without_groupable_order_side': missing_order,
            'trade_events_unknown_outcome': unknown_side,
            'source_time_range': [min(source_times).isoformat(), max(source_times).isoformat()] if source_times else None,
            'independent_intents': None, 'strategy': 'UNKNOWN_REQUIRES_INTENT_REVIEW',
            'copyability': 'UNASSESSED', 'copy_pnl': None, 'flags': flags}


def run(args):
    out = pathlib.Path(args.out)
    source = json.loads((out / 'report.json').read_text())
    # Choose before any deeper history request, and do not use PnL in selection.
    selected = sorted((x for x in source['candidates'] if x.get('sampled_crypto_events', 0) > 0),
                      key=lambda x: (-x['sampled_crypto_events'], x['account']))[:args.max_wallets]
    selected_at = now()
    results = []
    with gzip.open(out / 'profile_requests.jsonl.gz', 'wt') as archive:
        client = Client(archive, time.monotonic() + 300)
        for candidate in selected:
            rows, cursor, seen = [], None, set()
            status = 'TRUNCATED_PAGE_CAP'
            pages = 0
            for _ in range(args.pages):
                params = {'limit': 30}
                if cursor is not None:
                    params['cursor'] = cursor
                payload = client.get('/portfolio/' + candidate['account'] + '/history', params)
                if payload is None:
                    status = 'REQUEST_FAILED_OR_BUDGET_EXHAUSTED'
                    break
                if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                    status = 'SCHEMA_UNKNOWN'
                    break
                pages += 1
                rows.extend(items(payload))
                cursor = payload.get('nextCursor')
                if not cursor:
                    status = 'END_OF_AVAILABLE_API_HISTORY'
                    break
                if not isinstance(cursor, str) or cursor in seen:
                    status = 'INVALID_OR_REPEATED_CURSOR'
                    break
                seen.add(cursor)
            results.append({'account': candidate['account'], 'selected_at': selected_at,
                            'first_discovered_at': candidate['first_seen_at'], 'pages': pages,
                            'history_status': status, 'api_window_pnl': candidate.get('pnl'),
                            **profile(rows)})
        report = {'schema': 'limitless-wallet-profile-v1', 'generated_at': now(),
                  'selection': 'top sampled crypto event activity, address tie-break, no PnL filter',
                  'selection_universe': 'only wallets enriched by the bounded discovery snapshot',
                  'selection_at': selected_at, 'requests': client.requests, 'request_errors': client.errors,
                  'status': 'DESCRIPTIVE_HISTORY_NOT_FORWARD_RESULT', 'wallets': results,
                  'limitations': ['At most 300 events per wallet; truncated history cannot prove full strategy or profitability.',
                     'Both-side purchases may be hedging, rotation or separate intents; not proof of arbitrage.',
                     'An order-side group is not an independently reconstructed intent.',
                     'Limit Buy is maker execution, not proof of market making.',
                     'Claims are redemption cashflows, not independent wins or profit.',
                     'Historical API PnL is not follower PnL; no automatic copy eligibility.']}
    (out / 'profile.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    lines = ['# Limitless crypto wallet profiles', '', report['status'], '',
             '| Wallet | Events | Conditions | Maker buys | Taker buys | Both-side conditions | History |',
             '|---|---:|---:|---:|---:|---:|---|']
    for row in results:
        lines.append(f"| `{row['account']}` | {row['unique_events']} | {row['sampled_conditions']} | {row['maker_buy_events']} | {row['taker_buy_events']} | {row['buy_conditions_with_both_outcomes']} | {row['history_status']} |")
    lines += ['', *['- ' + x for x in report['limitations']]]
    (out / 'profile.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'wallets'}))
    return 1 if client.requests and client.requests == client.errors else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='limitless_discovery')
    parser.add_argument('--max-wallets', type=int, choices=range(1, 6), default=5)
    parser.add_argument('--pages', type=int, choices=range(1, 11), default=10)
    raise SystemExit(run(parser.parse_args()))
