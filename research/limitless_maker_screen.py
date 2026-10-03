#!/usr/bin/env python3
"""Read-only quote-stability diagnostics. No simulated orders, fills or PnL."""
import argparse
import bisect
import collections
import datetime as dt
import gzip
import hashlib
import json
import math
import pathlib
import statistics
import zipfile

from limitless_inventory_paper import market_identity

VERSION = 'limitless-maker-screen-v1'
HORIZONS = (1, 5, 15, 30)
MAX_GAP = 2.0
META_AGE = 120.0
REFERENCE_AGE = 10.0
ANCHOR_BUCKET = 30
SHARES = 10.0


def number(value):
    if isinstance(value, bool):
        raise ValueError('BOOL_NUMBER')
    result = float(value)
    if not math.isfinite(result):
        raise ValueError('NONFINITE_NUMBER')
    return result


def stamp(value):
    if not isinstance(value, str):
        raise ValueError('TIMESTAMP_MUST_BE_AWARE_ISO')
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('NAIVE_TIMESTAMP')
    return parsed.timestamp()


def bbo(book):
    sides = []
    for key in ('bids', 'asks'):
        levels = []
        for x in book[key]:
            p, q = number(x['price']), number(x['size']) / 1e6
            if not 0 < p < 1 or q < 0:
                raise ValueError('INVALID_LEVEL')
            if q:
                levels.append((p, q))
        if not levels:
            raise ValueError('EMPTY_BOOK')
        price = (max if key == 'bids' else min)(p for p, _ in levels)
        sides.append((price, sum(q for p, q in levels if p == price)))
    (bid, bid_size), (ask, ask_size) = sides
    if bid >= ask:
        raise ValueError('CROSSED_OR_LOCKED_BOOK')
    return bid, ask, bid_size, ask_size


def reference_at(references, symbol, at):
    item = references.get(symbol)
    if item is None or not 0 <= at - item['at'] <= REFERENCE_AGE:
        return None
    valid = [r for r in item['rows'] if number(r[0])/1000 <= at <= number(r[6])/1000]
    if len(valid) != 1:
        return None
    price = number(valid[0][4])
    if price <= 0:
        return None
    return {'price': price, 'received_at': item['at'], 'requested_at': item['requested']}


def screen_rows(rows, segment):
    """Rows stay in original receipt order; later metadata cannot qualify earlier books."""
    counts = collections.Counter()
    metadata, references, identities, seen, latest_version, latest_source = {}, {}, {}, {}, {}, {}
    points = collections.defaultdict(list)
    quarantined, buckets = set(), set()
    chains = collections.defaultdict(int)
    last_point = {}
    previous_at = -math.inf
    global_chain = 0
    for line_no, row in rows:
        kind = row.get('kind')
        try:
            at = stamp(row['observed_at'])
            if at < previous_at:
                raise ValueError('RECEIPT_TIME_REVERSED')
            previous_at = at
        except (ValueError, KeyError, TypeError, OverflowError):
            counts['invalid_receipt_time'] += 1
            global_chain += 1
            continue
        if kind in ('ws_disconnect', 'ws_connect', 'subscription'):
            global_chain += 1
            counts[kind] += 1
        if kind == 'market':
            slug = row.get('slug')
            metadata.pop(slug, None)
            try:
                raw = row['raw']
                if raw['slug'] != slug:
                    raise ValueError('METADATA_SLUG_MISMATCH')
                identity = market_identity(raw)
                if slug in identities and identities[slug] != identity:
                    quarantined.add(slug)
                    counts['market_identity_conflict'] += 1
                identities[slug] = identity
                metadata[slug] = (at, raw, identity)
            except (ValueError, KeyError, TypeError, ArithmeticError):
                counts['unqualified_metadata'] += 1
            continue
        if kind == 'binance_1m':
            symbol = (row.get('params') or {}).get('symbol')
            references.pop(symbol, None)
            try:
                requested = stamp(row['requested_at'])
                if (row.get('source') != 'binance' or requested > at
                        or symbol not in ('BTCUSDT', 'ETHUSDT') or not isinstance(row['raw'], list)):
                    raise ValueError('INVALID_REFERENCE')
                references[symbol] = {'at': at, 'requested': requested, 'rows': row['raw']}
            except (ValueError, KeyError, TypeError):
                counts['invalid_reference'] += 1
            continue
        if kind != 'ws_event' or row.get('event') != 'orderbookUpdate':
            continue
        counts['ws_book_frames'] += 1
        raw = row.get('raw')
        slug = raw.get('marketSlug') if isinstance(raw, dict) else None
        if slug not in metadata:
            counts['no_prior_qualified_metadata'] += 1
            chains[slug] += 1
            continue
        meta_at, market, identity = metadata[slug]
        try:
            if (at - meta_at > META_AGE or market.get('status') != 'FUNDED'
                    or not identity['start'] <= at < identity['end'] - 60):
                raise ValueError('INACTIVE_OR_STALE_METADATA')
            source_at = stamp(raw['timestamp'])
            if not 0 <= at - source_at <= MAX_GAP:
                raise ValueError('SOURCE_TIME_OUTSIDE_BOUND')
            version = raw['version']
            if isinstance(version, bool) or not isinstance(version, int) or version < 0:
                raise ValueError('INVALID_VERSION')
            book = raw['orderbook']
            if book.get('tokenId') != identity['yes_token']:
                raise ValueError('TOKEN_MISMATCH')
            fingerprint = hashlib.sha256(json.dumps(book, sort_keys=True, allow_nan=False).encode()).hexdigest()
            key = (slug, version)
            if key in seen:
                if seen[key] != fingerprint:
                    quarantined.add(slug)
                    raise ValueError('VERSION_CONTENT_CONFLICT')
                counts['duplicate_book_versions'] += 1
                continue
            if version <= latest_version.get(slug, -1) or source_at < latest_source.get(slug, -math.inf):
                raise ValueError('VERSION_OR_SOURCE_REVERSED')
            seen[key] = fingerprint
            latest_version[slug], latest_source[slug] = version, source_at
            bid, ask, bid_size, ask_size = bbo(book)
            minimum = number(book['minSize'])/1e6 if book.get('minSize') is not None else None
            if minimum is not None and minimum < 0:
                raise ValueError('INVALID_MIN_SIZE')
        except (ValueError, KeyError, TypeError, ArithmeticError) as error:
            counts['rejected_book_frames'] += 1
            # Preserve the reason without dropping other valid conditions.
            counts['reason:' + str(error)] += 1
            chains[slug] += 1
            continue
        if at - last_point.get(slug, -math.inf) > MAX_GAP:
            chains[slug] += 1
        last_point[slug] = at
        try:
            reference = reference_at(references, identity['symbol'], at)
        except (ValueError, TypeError, IndexError, ArithmeticError):
            reference = None
            counts['malformed_reference_at_book'] += 1
        bucket = (identity['condition'], int(at // ANCHOR_BUCKET))
        anchor = bucket not in buckets
        buckets.add(bucket)
        points[slug].append({'at': at, 'source_at': source_at, 'source_lag_s': at-source_at,
            'condition': identity['condition'], 'symbol': identity['symbol'], 'hour_start': identity['start'],
            'chain': (global_chain, chains[slug]), 'version': version, 'bid': bid, 'ask': ask,
            'mid': (bid+ask)/2, 'spread': ask-bid, 'displayed_yes_bid_shares': bid_size,
            'displayed_no_bid_shares': ask_size, 'lp_min_size_shares': minimum,
            'reference': reference, 'anchor': anchor, 'segment': segment, 'line': line_no,
            'book_sha256': fingerprint})
        counts['valid_unique_book_frames'] += 1
    anchors = []
    for slug, series in points.items():
        if slug in quarantined:
            continue
        times = [p['at'] for p in series]
        for i, p in enumerate(series):
            if not p['anchor']:
                continue
            a = {k:v for k,v in p.items() if k not in ('chain', 'anchor')}
            a['slug'] = slug
            a['nominal_bid_yes'], a['nominal_bid_no'] = p['bid'], 1-p['ask']
            a['nominal_shares_each'] = SHARES
            a['horizons'] = {}
            end = i
            while end+1 < len(series) and series[end+1]['chain'] == p['chain'] and series[end+1]['at'] <= p['at']+30:
                end += 1
            changed = next((q for q in series[i+1:end+1] if (q['bid'],q['ask']) != (p['bid'],p['ask'])), None)
            a['bbo_first_observed_change_s'] = changed['at']-p['at'] if changed else None
            a['bbo_observation_end_s'] = series[end]['at']-p['at']
            a['bbo_change_censored'] = changed is None
            for horizon in HORIZONS:
                j = bisect.bisect_left(times, p['at']+horizon, lo=i+1)
                q = series[j] if j < len(series) else None
                if q is None or q['at'] > p['at']+horizon+MAX_GAP or q['chain'] != p['chain']:
                    a['horizons'][str(horizon)] = {'status': 'UNKNOWN_GAP_OR_END'}
                    continue
                yes_margin, no_margin = q['mid']-p['bid'], p['ask']-q['mid']
                ref0, ref1 = p['reference'], q['reference']
                underlying = ((ref1['price']/ref0['price']-1)*10000
                              if ref0 and ref1 and ref1['received_at'] > ref0['received_at'] else None)
                a['horizons'][str(horizon)] = {'status': 'OBSERVED_NOT_FILL', 'actual_delay_s': q['at']-p['at'],
                    'future_line': q['line'], 'midpoint_change': q['mid']-p['mid'],
                    'yes_midpoint_margin': yes_margin, 'no_midpoint_margin': no_margin,
                    'worst_midpoint_margin': min(yes_margin,no_margin),
                    'underlying_change_bps': underlying}
            anchors.append(a)
    return {'segment': segment, 'counts': dict(counts), 'quarantined_slugs': sorted(quarantined),
            'identities': identities, 'anchors': anchors}


def distribution(values):
    values = sorted(values)
    if not values:
        return {'n': 0, 'median': None, 'p95': None, 'min': None, 'max': None}
    return {'n': len(values), 'median': statistics.median(values),
            'p95': values[math.ceil(.95*len(values))-1], 'min': values[0], 'max': values[-1]}


def aggregate(anchors):
    changed = [a['bbo_first_observed_change_s'] for a in anchors if not a['bbo_change_censored']]
    result = {'anchors': len(anchors), 'conditions': len({a['condition'] for a in anchors}),
        'hour_clusters': len({a['hour_start'] for a in anchors}),
        'spread': distribution([a['spread'] for a in anchors]),
        'source_receipt_lag_s': distribution([a['source_lag_s'] for a in anchors]),
        'bbo_first_observed_change_s_uncensored_only': distribution(changed),
        'bbo_change_censored': sum(a['bbo_change_censored'] for a in anchors),
        'anchors_with_fresh_binance_reference': sum(a['reference'] is not None for a in anchors),
        'lp_size_threshold_known': sum(a['lp_min_size_shares'] is not None for a in anchors),
        'nominal_size_below_lp_min': sum(a['lp_min_size_shares'] is not None and SHARES<a['lp_min_size_shares'] for a in anchors),
        'horizons': {}}
    for h in map(str,HORIZONS):
        rows = [a['horizons'][h] for a in anchors]
        known = [r for r in rows if r['status']=='OBSERVED_NOT_FILL']
        result['horizons'][h] = {'observed':len(known), 'unknown':len(rows)-len(known),
            'actual_delay_s':distribution([r['actual_delay_s'] for r in known]),
            'midpoint_change':distribution([r['midpoint_change'] for r in known]),
            'worst_midpoint_margin':distribution([r['worst_midpoint_margin'] for r in known]),
            'future_midpoint_outside_original_quotes':sum(r['worst_midpoint_margin'] < -1e-12 for r in known),
            'underlying_change_bps':distribution([r['underlying_change_bps'] for r in known if r['underlying_change_bps'] is not None])}
    return result


def analyze(manifest, root):
    segments, errors, windows, used, provenance = [], [], [], set(), []
    identities, condition_ids = {}, {}
    for entry in manifest['artifacts']:
        name = entry.get('file')
        try:
            if (entry.get('head_branch')!='main' or entry.get('event') not in ('push','schedule','workflow_dispatch')
                    or entry.get('conclusion')!='success' or not entry.get('head_sha')):
                raise ValueError('NOT_SUCCESSFUL_MAIN_CAPTURE')
            if pathlib.Path(name).name != name:
                raise ValueError('MANIFEST_FILE_MUST_BE_BASENAME')
            path = pathlib.Path(root)/name
            sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if sha != entry['sha256']:
                raise ValueError('ARTIFACT_SHA_MISMATCH')
            if sha in used:
                continue
            used.add(sha)
            with zipfile.ZipFile(path) as z:
                summary = json.loads(z.read('summary.json'))
                start,end = stamp(summary['started_at']),stamp(summary['ended_at'])
                if end <= start or any(start < b and end > a for a,b in windows):
                    raise ValueError('INVALID_OR_OVERLAPPING_SEGMENT')
                windows.append((start,end))
                def rows():
                    with gzip.open(z.open('capture.jsonl.gz'),'rt') as lines:
                        for n,line in enumerate(lines,1):
                            row=json.loads(line)
                            if row.get('kind') in ('market','binance_1m','ws_event','ws_disconnect','ws_connect','subscription'):
                                at=stamp(row['observed_at'])
                                if not start<=at<=end:
                                    raise ValueError('ROW_OUTSIDE_SEGMENT')
                                yield n,row
                result=screen_rows(rows(),str(entry['artifact_id']))
                for slug, identity in result['identities'].items():
                    condition = identity['condition']
                    if ((slug in identities and identities[slug] != identity)
                            or (condition in condition_ids and condition_ids[condition] != identity)):
                        errors.append({'artifact':name,'error':'CROSS_SEGMENT_IDENTITY_CONFLICT','slug':slug})
                    identities[slug], condition_ids[condition] = identity, identity
                if result['quarantined_slugs']:
                    errors.append({'artifact':name,'error':'QUARANTINED_BOOK_IDENTITY','slugs':result['quarantined_slugs']})
                segments.append(result)
                provenance.append({**entry,'started_at':summary['started_at'],'ended_at':summary['ended_at'],
                                   'size_cap_reached':summary.get('size_cap_reached')})
        except (ValueError,KeyError,TypeError,ArithmeticError,OSError,zipfile.BadZipFile) as error:
            errors.append({'artifact':name,'error':str(error)})
    anchors=sorted((a for s in segments for a in s['anchors']),key=lambda a:(a['at'],a['condition']))
    # One condition/bucket remains one anchor even across job boundaries.
    distinct={}
    for a in anchors:
        distinct.setdefault((a['condition'],int(a['at']//ANCHOR_BUCKET)),a)
    anchors=list(distinct.values())
    conditions=sorted({a['condition'] for a in anchors})
    return {'schema':VERSION,'status':'INVALID_INPUT' if errors else 'DIAGNOSTIC_ONLY_NO_FILL_MODEL',
        'pnl':None,'fill_probability':None,'errors':errors,'provenance':provenance,
        'protocol':{'horizons_s':HORIZONS,'max_gap_source_age_and_horizon_slack_s':MAX_GAP,
                    'anchor_bucket_s':ANCHOR_BUCKET,'metadata_max_age_s':META_AGE,'nominal_shares_each':SHARES},
        'segments':[{k:v for k,v in s.items() if k not in ('anchors','identities')} for s in segments],
        'summary':aggregate(anchors) if not errors else None,
        'by_condition':[{ 'condition':key, **aggregate([a for a in anchors if a['condition']==key])} for key in conditions] if not errors else [],
        'anchors':anchors if not errors else [],
        'limitations':['Historical descriptive screen, not a prospective maker strategy or PnL.',
          'Coalesced books omit queue position, individual fills, cancellations and intermediate states.',
          'Version jumps do not quantify lost events; publisher restart cannot be inferred safely.',
          'Future midpoint margins are unconditional quote diagnostics, not fair value or fill-conditional markouts.',
          'Unknown horizons are excluded from metric denominators and reported; favourable observed subsets may be biased.',
          'LP minSize check alone proves neither rewards eligibility nor maker rebate income.',
          'Snapshots/anchors are dependent; sample units for inference remain conditions and hourly clusters.']}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',required=True,type=pathlib.Path)
    parser.add_argument('--archives-dir',required=True,type=pathlib.Path)
    parser.add_argument('--out',required=True,type=pathlib.Path)
    args=parser.parse_args()
    result=analyze(json.loads(args.manifest.read_text()),args.archives_dir)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'errors':result['errors'],'summary':result['summary']}))
    raise SystemExit(1 if result['errors'] else 0)
