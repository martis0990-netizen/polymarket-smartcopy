#!/usr/bin/env python3
"""Observed-depth entry diagnostics; no trades, inferred fills or copy PnL."""
import argparse
import collections
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import json
import pathlib
import statistics
from limitless_smartcopy_probe import metadata, canonical_identity, parse_time, DEFAULT_ACCOUNTS

D = Decimal
BUDGET = D('10')
FEE = D('.03')
UNIT = D('1000000')


def decimal(value):
    x = D(str(value))
    if not x.is_finite():
        raise ValueError('Nonfinite value')
    return x


def depth_quote(book, outcome, source_price):
    if outcome not in ('YES', 'NO'):
        return {'status': 'UNKNOWN_OUTCOME'}
    try:
        if not book.get('tokenId'):
            raise ValueError('Missing YES token ID')
        sides = {}
        for side in ('bids', 'asks'):
            levels = []
            if not isinstance(book.get(side), list):
                raise ValueError('Unknown book schema')
            for level in book[side]:
                p, raw = decimal(level['price']), decimal(level['size'])
                if not 0 <= p <= 1 or raw < 0 or raw != raw.to_integral_value():
                    raise ValueError('Invalid price or raw share size')
                if raw:
                    levels.append((p, raw / UNIT))
            sides[side] = levels
        if sides['bids'] and sides['asks'] and max(p for p, _ in sides['bids']) >= min(p for p, _ in sides['asks']):
            raise ValueError('Crossed or locked book')
        levels = sides['asks'] if outcome == 'YES' else [(1-p, q) for p, q in sides['bids']]
        if any(p <= 0 for p, _ in levels):
            raise ValueError('Zero ask unsupported')
        levels = sorted(levels)
        try:
            source = decimal(source_price)
            if not 0 < source <= 1:
                source = None
        except (InvalidOperation, ValueError):
            source = None
        capacity = sum((p*q for p, q in levels if source is not None and p <= source), D(0))
        spent, shares, used = D(0), D(0), 0
        for price, quantity in levels:
            take = min(quantity, ((BUDGET-spent)/price).quantize(D('.000001'), rounding=ROUND_DOWN))
            if take > 0:
                spent += price*take
                shares += take
                used += 1
            if BUDGET-spent <= D('.000001'):
                break
        complete = BUDGET-spent <= D('.000001')
        vwap = spent/shares if shares else None
        effective = vwap/(1-FEE) if vwap is not None else None
        return {'status': 'DEPTH_SUPPORTS_10_USDC_QUOTE' if complete else 'INSUFFICIENT_VISIBLE_DEPTH',
                'outcome': outcome, 'budget_usdc': str(BUDGET), 'spent_in_quote_usdc': str(spent),
                'unspent_usdc': str(BUDGET-spent), 'gross_quoted_shares': str(shares),
                'net_shares_assuming_3pct_contract_fee': str(shares*(1-FEE)),
                'best_ask': str(levels[0][0]) if levels else None,
                'levels_used': used, 'vwap': str(vwap) if vwap is not None else None,
                'effective_cost_per_net_share_3pct': str(effective) if effective is not None else None,
                'source_price': str(source) if source is not None else None,
                'vwap_minus_source_price': str(vwap-source) if vwap is not None and source is not None else None,
                'fee_adjusted_cost_minus_source_gross_price': str(effective-source) if effective is not None and source is not None else None,
                'visible_cost_capacity_at_or_below_source': str(capacity) if source is not None else None,
                'ten_usdc_available_at_or_below_source': capacity >= BUDGET if source is not None else None,
                'quote_only_not_fill_or_pnl': True}
    except (KeyError, TypeError, InvalidOperation, ValueError) as exc:
        return {'status': 'INVALID_OR_UNVERIFIED_BOOK', 'reason': str(exc)}


def report_directory(directory):
    directory = pathlib.Path(directory)
    summary = json.loads((directory/'summary.json').read_text())
    start = parse_time(summary['started_at'])
    observations = [json.loads(x) for x in (directory/'observations.jsonl').read_text().splitlines()]
    path = directory/'books.jsonl'
    books = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    selected, aliases = {}, {}
    for row in observations:
        if row.get('kind') != 'observation':
            continue
        raw, account = row.get('raw') or {}, row.get('account') or ''
        meta = metadata(raw)
        key = canonical_identity(raw, account)
        aliases[row['id']] = key
        observed = parse_time(row['first_seen_at'])
        if key not in selected or observed < parse_time(selected[key]['first_seen_at']):
            selected[key] = {**row, **{k: meta[k] for k in ('outcome', 'operation', 'source_price', 'order_id', 'condition_id')}}
    first_books = {}
    for book in books:
        key = aliases.get(book.get('event_id'))
        if key not in selected:
            continue
        at = parse_time(book.get('fetched_at'))
        if at is not None and at >= parse_time(selected[key]['first_seen_at']):
            if key not in first_books or at < parse_time(first_books[key]['fetched_at']):
                # First attempt wins even if it failed. Never select a later favorable snapshot.
                first_books[key] = book
    results = []
    for key, row in selected.items():
        source_at = parse_time(row.get('occurred_at'))
        if row.get('operation') != 'BUY' or not row.get('crypto_candidate') or source_at is None or source_at < start:
            continue
        observed = parse_time(row['first_seen_at'])
        result = {'canonical_trade_id': key, 'account': row['account'], 'slug': row.get('slug'),
                  'condition_id': row.get('condition_id'), 'order_id': row.get('order_id'),
                  'scope': 'FIXED_COHORT' if row['account'] in DEFAULT_ACCOUNTS else 'DISCOVERY_FEED',
                  'source_time': source_at.isoformat(), 'first_observed_at': row['first_seen_at'],
                  'detection_delay_s': (observed-source_at).total_seconds(),
                  'outcome': row.get('outcome'), 'source_price': row.get('source_price')}
        book = first_books.get(key)
        if source_at > observed:
            result['status'] = 'INVALID_SOURCE_OBSERVATION_TIME'
        elif row.get('outcome') not in ('YES', 'NO'):
            result['status'] = 'UNKNOWN_OUTCOME'
        elif book is None:
            result['status'] = 'NO_BOOK_CAPTURED'
        elif 'error' in book:
            result.update(status='FIRST_BOOK_REQUEST_FAILED', error=book['error'])
        else:
            requested = parse_time(book.get('request_started_at'))
            received = parse_time(book.get('fetched_at'))
            if requested is None or requested < observed or received < requested:
                result['status'] = 'UNVERIFIED_POST_DETECTION_REQUEST'
            else:
                result.update(book_request_started_at=book['request_started_at'], book_received_at=book['fetched_at'],
                              detection_to_request_s=(requested-observed).total_seconds(),
                              book_http_latency_s=(received-requested).total_seconds(),
                              source_to_book_receipt_s=(received-source_at).total_seconds(),
                              **depth_quote(book.get('raw') or {}, row['outcome'], row.get('source_price')))
        results.append(result)
    by_scope = {}
    for scope in ('FIXED_COHORT', 'DISCOVERY_FEED'):
        rows = [r for r in results if r['scope'] == scope]
        supported = [r for r in rows if r['status'] == 'DEPTH_SUPPORTS_10_USDC_QUOTE']
        prices = [float(r['vwap_minus_source_price']) for r in supported if r.get('vwap_minus_source_price') is not None]
        by_scope[scope] = {'canonical_buy_records': len(rows), 'status_counts': dict(collections.Counter(r['status'] for r in rows)),
                           'ten_usdc_depth_quote_fraction': len(supported)/len(rows) if rows else None,
                           'at_or_below_source_price_records': sum(r.get('ten_usdc_available_at_or_below_source') is True for r in supported),
                           'detection_delay_p50_s': statistics.median([r['detection_delay_s'] for r in rows]) if rows else None,
                           'vwap_minus_source_p50': statistics.median(prices) if prices else None,
                           'independent_intents': None}
    report = {'schema': 'limitless-entry-availability-v1', 'status': 'OBSERVED_DEPTH_DIAGNOSTIC_NO_FILL_NO_PNL',
              'segment_started_at': summary['started_at'], 'scopes': by_scope, 'records': results,
              'limitations': ['Ratios use canonical observed buy records, not independent intentions or all exchange trades.',
                 'NO ask depth is derived from YES bids; raw share sizes divided by 1e6.',
                 '10 USDC depth quote has no approved trading max price and is not an order or fill.',
                 '3% fee is a conservative diagnostic assumption; source fee and actual follower fee are not established.',
                 'REST freshness has no guaranteed bound; receipt time is not book matching time.',
                 'Missing/inactive/error books stay missing; no historical fill at source price or midpoint.',
                 'No funding, latency races, cancellations, queue or market resolution modeled.']}
    (directory/'entry_availability.json').write_text(json.dumps(report, indent=2) + '\n')
    lines = ['# Entry availability diagnostics', '', report['status'], '',
             '| Scope | Canonical buys | Depth supports 10 USDC | At/below source price | Median detection delay |',
             '|---|---:|---:|---:|---:|']
    for scope, stats in by_scope.items():
        lines.append(f"| {scope} | {stats['canonical_buy_records']} | {stats['status_counts'].get('DEPTH_SUPPORTS_10_USDC_QUOTE',0)} | {stats['at_or_below_source_price_records']} | {stats['detection_delay_p50_s']} |")
    lines += ['', *['- '+x for x in report['limitations']]]
    (directory/'entry_availability.md').write_text('\n'.join(lines)+'\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='limitless_probe')
    args = parser.parse_args()
    print(json.dumps(report_directory(args.out)['scopes']))
