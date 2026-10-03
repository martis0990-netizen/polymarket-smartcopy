#!/usr/bin/env python3
"""Observed-depth entry diagnostics; no trades, inferred fills or copy PnL."""
import argparse
import collections
import datetime as dt
from decimal import Decimal, InvalidOperation, ROUND_DOWN
import json
import pathlib
import statistics
import zipfile
from limitless_smartcopy_probe import metadata, canonical_identity, parse_time, DEFAULT_ACCOUNTS

D = Decimal
BUDGET = D('10')
FEE = D('.03')
UNIT = D('1000000')


def valid_time(value):
    """Reject absent, malformed, nonfinite and timezone-naive timestamps."""
    try:
        if isinstance(value, bool):
            return None
        if isinstance(value, str) and dt.datetime.fromisoformat(value.replace('Z', '+00:00')).tzinfo is None:
            return None
        return parse_time(value)
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def data_error(row, field):
    return {'id': row.get('id') or row.get('event_id'), 'account': row.get('account'),
            'artifact': row.get('_artifact'), 'field': field, 'reason': 'INVALID_REQUIRED_DATA'}


def book_identity(row, book):
    """Validate identifiers present at detection; never enrich from later metadata."""
    raw = row.get('raw') or {}
    market, subject, facts = raw.get('market') or {}, raw.get('subject') or {}, raw.get('facts') or {}
    result = {'slug_validation': 'UNKNOWN', 'yes_token_validation': 'UNKNOWN',
              'collateral_validation': 'UNKNOWN', 'full_market_metadata_verified': False}
    slug = row.get('slug')
    if not slug or not book.get('slug'):
        return 'UNVERIFIED_MARKET_IDENTITY', result
    if slug != book['slug'] or any(x and x != slug for x in (market.get('slug'), subject.get('slug'))):
        return 'MARKET_IDENTITY_MISMATCH', result
    result['slug_validation'] = 'MATCH'
    if market.get('group') or subject.get('groupSlug') or market.get('marketType') == 'group':
        return 'UNSUPPORTED_MARKET_METADATA', result
    if market.get('tradeType') and market['tradeType'] != 'clob':
        return 'UNSUPPORTED_MARKET_METADATA', result
    collateral = market.get('collateral') or {}
    tokens = market.get('tokens') or {}
    if not isinstance(collateral, dict) or not isinstance(tokens, dict):
        return 'UNSUPPORTED_MARKET_METADATA', result
    symbols = [str(x).upper() for x in (collateral.get('symbol'), facts.get('symbol')) if x is not None]
    if any(x != 'USDC' for x in symbols):
        return 'UNSUPPORTED_COLLATERAL', result
    if symbols:
        result['collateral_validation'] = 'USDC_SYMBOL_OBSERVED_DECIMALS_UNVERIFIED'
    decimals = collateral.get('decimals')
    if decimals is not None:
        if type(decimals) is not int or decimals != 6:
            return 'UNSUPPORTED_COLLATERAL', result
        if symbols:
            result['collateral_validation'] = 'USDC_6_DECIMALS_OBSERVED'
    expected = tokens.get('yes')
    if expected is not None:
        if str(expected) != str((book.get('raw') or {}).get('tokenId')):
            return 'MARKET_IDENTITY_MISMATCH', result
        result['yes_token_validation'] = 'MATCH'
    # Presence of some identifiers does not establish all active-market semantics.
    return None, result


def decimal(value):
    x = D(str(value))
    if not x.is_finite():
        raise ValueError('Nonfinite value')
    return x


def depth_quote(book, outcome, source_price):
    if outcome not in ('YES', 'NO'):
        return {'status': 'UNKNOWN_OUTCOME'}
    if not isinstance(book, dict):
        return {'status': 'INVALID_OR_UNVERIFIED_BOOK', 'reason': 'Expected book object'}
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


def build_report(summary, observations, books):
    start = valid_time(summary.get('started_at'))
    if start is None:
        raise ValueError('INVALID_SEGMENT_START')
    selected, aliases, evidence = {}, {}, collections.defaultdict(list)
    errors, invalid_keys, invalid_books = [], set(), set()
    for row in observations:
        if row.get('kind') != 'observation':
            continue
        raw, account = row.get('raw') or {}, row.get('account') or ''
        if (not isinstance(raw, dict) or not row.get('id') or not account
                or any(raw.get(k) is not None and not isinstance(raw[k], dict) for k in ('facts', 'subject', 'market', 'profile'))):
            errors.append(data_error(row, 'raw/id/account'))
            continue
        meta = metadata(raw)
        key = canonical_identity(raw, account)
        aliases[row['id']] = key
        observed = valid_time(row.get('first_seen_at'))
        source_at = valid_time(row.get('occurred_at'))
        segment = valid_time(row.get('_segment_started_at')) if '_segment_started_at' in row else start
        if observed is None or source_at is None or segment is None:
            errors.append(data_error(row, 'first_seen_at/occurred_at/segment_start'))
            invalid_keys.add(key)
            continue
        evidence[key].append((observed, meta['outcome'], meta['outcome_basis']))
        if key not in selected or observed < valid_time(selected[key]['first_seen_at']):
            selected[key] = {**row, **{k: meta[k] for k in ('outcome', 'operation', 'source_price', 'order_id', 'condition_id')}}
    first_books = {}
    for book in books:
        key = aliases.get(book.get('event_id'))
        if key not in selected:
            continue
        at = valid_time(book.get('fetched_at'))
        if at is None:
            errors.append(data_error(book, 'fetched_at'))
            invalid_books.add(key)
            continue
        if at >= valid_time(selected[key]['first_seen_at']):
            if key not in first_books or at < valid_time(first_books[key]['fetched_at']):
                # First attempt wins even if it failed. Never select a later favorable snapshot.
                first_books[key] = book
    results = []
    for key, row in selected.items():
        if key in invalid_keys:
            continue  # Unknown earlier receipt must not be replaced by a later valid duplicate.
        source_at = valid_time(row.get('occurred_at'))
        segment_start = valid_time(row.get('_segment_started_at')) or start
        if row.get('operation') != 'BUY' or not row.get('crypto_candidate') or source_at is None or source_at < max(start, segment_start):
            continue
        observed = valid_time(row['first_seen_at'])
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
        elif key in invalid_books:
            result['status'] = 'INVALID_BOOK_TIME'
        elif book is None:
            result['status'] = 'NO_BOOK_CAPTURED'
        elif 'error' in book:
            result.update(status='FIRST_BOOK_REQUEST_FAILED', error=book['error'])
        else:
            requested = valid_time(book.get('request_started_at'))
            received = valid_time(book.get('fetched_at'))
            if requested is None or requested < observed or received < requested:
                result['status'] = 'UNVERIFIED_POST_DETECTION_REQUEST'
                if book.get('request_started_at') is not None:
                    errors.append(data_error(book, 'request_started_at/order'))
            else:
                identity_status, identity = book_identity(row, book)
                result.update(book_request_started_at=book['request_started_at'], book_received_at=book['fetched_at'],
                              detection_to_request_s=(requested-observed).total_seconds(),
                              book_http_latency_s=(received-requested).total_seconds(),
                              source_to_book_receipt_s=(received-source_at).total_seconds(),
                              market_identity=identity)
                if identity_status:
                    result['status'] = identity_status
                else:
                    result.update(depth_quote(book.get('raw') or {}, row['outcome'], row.get('source_price')))
        sides, conflict_at = set(), None
        for at, side, basis in sorted(evidence[key], key=lambda x: x[0]):
            if side:
                sides.add(side)
            if basis == 'CONFLICT' or len(sides) > 1:
                conflict_at = at
                break
        # Preserve the original quote status; late evidence is only retrospective validation.
        result['validation_status'] = 'CONFLICTING_SOURCE_OUTCOME' if conflict_at else result['status']
        result['conflict_observed_at'] = conflict_at.isoformat() if conflict_at else None
        result['validated_for_quote_statistics'] = conflict_at is None and result['status'] == 'DEPTH_SUPPORTS_10_USDC_QUOTE'
        results.append(result)
    by_scope = {}
    for scope in ('FIXED_COHORT', 'DISCOVERY_FEED'):
        rows = [r for r in results if r['scope'] == scope]
        supported = [r for r in rows if r['validation_status'] == 'DEPTH_SUPPORTS_10_USDC_QUOTE']
        prices = [float(r['vwap_minus_source_price']) for r in supported if r.get('vwap_minus_source_price') is not None]
        delays = [r['detection_delay_s'] for r in rows if r['detection_delay_s'] >= 0]
        by_scope[scope] = {'canonical_buy_records': len(rows), 'status_counts': dict(collections.Counter(r['validation_status'] for r in rows)),
                           'ten_usdc_depth_quote_fraction': len(supported)/len(rows) if rows else None,
                           'at_or_below_source_price_records': sum(r.get('ten_usdc_available_at_or_below_source') is True for r in supported),
                           'detection_delay_p50_s': statistics.median(delays) if delays else None,
                           'vwap_minus_source_p50': statistics.median(prices) if prices else None,
                           'independent_intents': None}
    report = {'schema': 'limitless-entry-availability-v2', 'status': 'OBSERVED_DEPTH_DIAGNOSTIC_NO_FILL_NO_PNL',
              'data_errors': errors, 'quarantined_canonical_ids': sorted(invalid_keys),
              'segment_started_at': summary['started_at'], 'scopes': by_scope, 'records': results,
              'limitations': ['Ratios use canonical observed buy records, not independent intentions or all exchange trades.',
                 'NO ask depth is derived from YES bids; raw share sizes divided by 1e6.',
                 '10 USDC depth quote has no approved trading max price and is not an order or fill.',
                 '3% fee is a conservative diagnostic assumption; source fee and actual follower fee are not established.',
                 'REST freshness has no guaranteed bound; receipt time is not book matching time.',
                 'Record status preserves the original quote; validation_status includes later retrospective conflicts and drives quote statistics.',
                 'Market identity checks only observed identifiers. full_market_metadata_verified remains false; unknown YES-token binding is explicit.',
                 'Malformed required observation times quarantine the canonical key; quarantined records are not in buy denominators and are listed separately.',
                 'Missing/inactive/error books stay missing; no historical fill at source price or midpoint.',
                 'No funding, latency races, cancellations, queue or market resolution modeled.']}
    report['by_wallet'] = {}
    for account in sorted({r['account'] for r in results}):
        rows = [r for r in results if r['account'] == account]
        supported = [r for r in rows if r['validation_status'] == 'DEPTH_SUPPORTS_10_USDC_QUOTE']
        gaps = [float(r['vwap_minus_source_price']) for r in supported if r.get('vwap_minus_source_price') is not None]
        delays = [r['detection_delay_s'] for r in rows if r['detection_delay_s'] >= 0]
        report['by_wallet'][account] = {'canonical_buy_records': len(rows),
            'status_counts': dict(collections.Counter(r['validation_status'] for r in rows)),
            'detection_delay_p50_s': statistics.median(delays) if delays else None,
            'vwap_minus_source_p50': statistics.median(gaps) if gaps else None,
            'depth_quote_fraction': len(supported)/len(rows), 'independent_intents': None}
    return report


def save_report(report, json_path):
    json_path = pathlib.Path(json_path)
    json_path.write_text(json.dumps(report, indent=2) + '\n')
    lines = ['# Entry availability diagnostics', '', report['status'], '',
             '| Scope | Canonical buys | Depth supports 10 USDC | At/below source price | Median detection delay |',
             '|---|---:|---:|---:|---:|']
    for scope, stats in report['scopes'].items():
        lines.append(f"| {scope} | {stats['canonical_buy_records']} | {stats['status_counts'].get('DEPTH_SUPPORTS_10_USDC_QUOTE',0)} | {stats['at_or_below_source_price_records']} | {stats['detection_delay_p50_s']} |")
    lines += ['', *['- '+x for x in report['limitations']]]
    lines += ['', f"Data errors: {len(report['data_errors'])}; quarantined canonical IDs: {len(report['quarantined_canonical_ids'])}"]
    if 'coverage_by_wallet' in report:
        lines += ['', 'Coverage is successful history poll credit, not guaranteed event completeness.', '',
                  '| Wallet | Credited seconds | Elapsed-window fraction | Largest uncredited gap (s) |',
                  '|---|---:|---:|---:|']
        for account, v in report['coverage_by_wallet'].items():
            lines.append(f"| {account} | {v['covered_seconds']} | {v['fraction']} | {v['largest_uncredited_gap_s']} |")
        lines += ['', f"Archive errors: {len(report['archive_errors'])}; window: {report['window_utc']}"]
    if report['by_wallet']:
        lines += ['', '| Wallet | Canonical fresh buys | Status counts | Median quote deterioration |',
                  '|---|---:|---|---:|']
        for account, v in report['by_wallet'].items():
            lines.append(f"| {account} | {v['canonical_buy_records']} | {v['status_counts']} | {v['vwap_minus_source_p50']} |")
    json_path.with_suffix('.md').write_text('\n'.join(lines)+'\n')


def report_directory(directory):
    directory = pathlib.Path(directory)
    summary = json.loads((directory/'summary.json').read_text())
    observations = [json.loads(x) for x in (directory/'observations.jsonl').read_text().splitlines()]
    path = directory/'books.jsonl'
    books = [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    report = build_report(summary, observations, books)
    save_report(report, directory/'entry_availability.json')
    return report


def aggregate_archives(paths, as_of):
    start = valid_time('2026-10-03T09:00:00Z')
    requested_end = valid_time(as_of)
    if requested_end is None:
        raise ValueError('INVALID_AUDIT_END')
    end = min(requested_end, valid_time('2026-10-10T09:00:00Z'))
    if end <= start:
        raise ValueError('Audit end must be after study start')
    rows, books, segments, errors, row_errors = [], [], [], [], []
    for path in paths:
        try:
            with zipfile.ZipFile(path) as z:
                summary = json.loads(z.read('summary.json'))
                segment_start = valid_time(summary['started_at'])
                if segment_start is None:
                    raise ValueError('Missing segment start')
                captured = [json.loads(x) for x in z.read('observations.jsonl').splitlines()]
                captured_books = [json.loads(x) for x in z.read('books.jsonl').splitlines()] if 'books.jsonl' in z.namelist() else []
            segments.append({'artifact': pathlib.Path(path).name, 'started_at': summary['started_at'],
                             'generated_at': summary.get('generated_at')})
            for row in captured:
                row = {**row, '_segment_started_at': summary['started_at'], '_artifact': pathlib.Path(path).name}
                at = valid_time(row.get('fetched_at') or row.get('first_seen_at'))
                if at is None:
                    if row.get('kind') == 'observation':
                        rows.append(row)  # Quarantine its key; do not promote a later duplicate.
                    else:
                        row_errors.append(data_error(row, 'fetched_at'))
                elif start <= at < end:
                    rows.append(row)
            for b in captured_books:
                at = valid_time(b.get('fetched_at'))
                if at is None or start <= at < end:
                    books.append({**b, '_artifact': pathlib.Path(path).name})
        except (zipfile.BadZipFile, KeyError, ValueError, OSError) as exc:
            errors.append({'artifact': pathlib.Path(path).name, 'error': str(exc)})
    report = build_report({'started_at': start.isoformat()}, rows, books)
    report['data_errors'].extend(row_errors)
    report.update(schema='limitless-entry-aggregate-v2', as_of=end.isoformat(),
                  window_utc=[start.isoformat(), end.isoformat()], segments=segments, archive_errors=errors)
    coverage = {}
    for account in DEFAULT_ACCOUNTS:
        at = sorted({valid_time(r['fetched_at']) for r in rows if r.get('kind') == 'poll_success'
                     and r.get('source') == 'history' and r.get('account') == account})
        spans = []
        for t in at:
            left, right = max(start, t-dt.timedelta(seconds=30)), min(end, t)
            if spans and left <= spans[-1][1]:
                spans[-1] = (spans[-1][0], max(right, spans[-1][1]))
            else:
                spans.append((left, right))
        seconds = sum((b-a).total_seconds() for a,b in spans)
        gaps, previous = [], start
        for left,right in spans:
            gaps.append((left-previous).total_seconds())
            previous = right
        gaps.append((end-previous).total_seconds())
        coverage[account] = {'successful_polls': len(at), 'covered_seconds': round(seconds,3),
                             'fraction': seconds/(end-start).total_seconds(),
                             'largest_uncredited_gap_s': max(gaps)}
    report['coverage_by_wallet'] = coverage
    # Preserve the earliest actual observation even when it is historical backfill.
    earliest = {}
    invalid_row_ids = {e['id'] for e in report['data_errors']}
    for row in rows:
        if (row.get('kind') == 'observation' and valid_time(row.get('first_seen_at')) is not None
                and row.get('id') not in invalid_row_ids and isinstance(row.get('raw'), dict)):
            key = canonical_identity(row.get('raw') or {}, row.get('account') or '')
            if key in report['quarantined_canonical_ids']:
                continue
            if key not in earliest or valid_time(row['first_seen_at']) < valid_time(earliest[key]['first_seen_at']):
                earliest[key] = row
    report['historical_crypto_buy_records_excluded'] = sum(
        metadata(r.get('raw') or {})['operation'] == 'BUY' and bool(r.get('crypto_candidate'))
        and valid_time(r.get('occurred_at')) is not None
        and valid_time(r['occurred_at']) < valid_time(r['_segment_started_at']) for r in earliest.values())
    report['limitations'] += ['Main archives only: workflow provenance is saved in the companion manifest.',
        'Cross-segment canonical deduplication keeps earliest detection; historical first detection never becomes a fresh entry.',
        'Coverage credits only 30 seconds before successful fixed-wallet history polls, clipped to elapsed study time; no credit for failed polls.',
        'Unfinished jobs and unavailable artifacts are not observed coverage; gaps include the leading and trailing window.',
        'This interim elapsed-window coverage does not replace the frozen full-week feasibility gate.']
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='limitless_probe')
    parser.add_argument('--archives', nargs='+', type=pathlib.Path)
    parser.add_argument('--as-of', help='UTC report end, required with --archives')
    args = parser.parse_args()
    if args.archives:
        if not args.as_of:
            parser.error('--as-of required with --archives')
        report = aggregate_archives(args.archives, args.as_of)
        save_report(report, args.out)
    else:
        report = report_directory(args.out)
    print(json.dumps(report['scopes']))
