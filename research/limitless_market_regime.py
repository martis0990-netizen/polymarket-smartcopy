#!/usr/bin/env python3
"""Offline structural diagnostic. No network, model changes, orders or fills."""
import argparse
import collections
import datetime as dt
from decimal import Decimal, InvalidOperation
import gzip
import hashlib
import json
import math
import pathlib
import zipfile

VERSION = 'limitless-market-regime-diagnostic-v1'
FRAMES = {'H4': 240, 'H1': 60, 'M15': 15, 'M5': 5, 'M1': 1}
MIN_BARS = 16
LEFT = RIGHT = 2
RETEST_ATR = .25
MIN_WIDTH_ATR = 1.
STATES = ('TREND_UP', 'TREND_DOWN', 'RANGE', 'TRANSITION', 'UNKNOWN')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def milliseconds(value):
    if isinstance(value, bool):
        raise ValueError('boolean time')
    if isinstance(value, (int, float)):
        result = float(value) * 1000  # numeric decision time is seconds
    elif isinstance(value, str):
        at = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if at.tzinfo is None:
            raise ValueError('naive time')
        result = at.timestamp() * 1000
    else:
        raise ValueError('invalid time')
    if not math.isfinite(result):
        raise ValueError('nonfinite time')
    return result


def candle(raw):
    if not isinstance(raw, list) or len(raw) < 7:
        raise ValueError('invalid candle')
    opened, closed = raw[0], raw[6]
    if (isinstance(opened, bool) or isinstance(closed, bool)
            or not isinstance(opened, int) or not isinstance(closed, int)
            or opened % 60000 or closed != opened + 59999):
        raise ValueError('invalid M1 boundaries')
    try:
        values = [Decimal(str(x)) for x in raw[1:5]]
        if any(not x.is_finite() or x <= 0 for x in values):
            raise ValueError('nonfinite/nonpositive OHLC')
        o, h, l, c = values
        if not l <= min(o, c) <= max(o, c) <= h:
            raise ValueError('inconsistent OHLC')
    except InvalidOperation as exc:
        raise ValueError('invalid OHLC') from exc
    return {'open_ms': opened, 'close_ms': closed, 'o': float(o), 'h': float(h),
            'l': float(l), 'c': float(c)}, tuple(str(v.normalize()) for v in values)


class MinuteStore:
    """First closed observations; conflicts apply only once observed."""
    def __init__(self):
        self.minutes = collections.defaultdict(dict)
        self.errors = []
        self.requests = 0

    def add(self, row, provenance):
        if row.get('kind') != 'binance_1m':
            return
        self.requests += 1
        try:
            if row.get('source') != 'binance' or row.get('path') != '/api/v3/klines':
                raise ValueError('unsupported source')
            params = row.get('params') or {}
            symbol = params.get('symbol')
            if symbol not in ('BTCUSDT', 'ETHUSDT') or params.get('interval') != '1m':
                raise ValueError('unsupported symbol/interval')
            requested = milliseconds(row.get('requested_at'))
            received = milliseconds(row.get('observed_at'))
            if received < requested or not isinstance(row.get('raw'), list):
                raise ValueError('invalid request envelope')
            fingerprint = digest(row)
            # Validate the entire response before admitting any part of it.
            parsed = [candle(raw) for raw in row['raw']]
            if len({bar['open_ms'] for bar, _ in parsed}) != len(parsed):
                raise ValueError('duplicate response minute')
            for bar, identity in parsed:
                if bar['close_ms'] >= requested:
                    continue  # never take the in-flight candle's partial values
                key = (symbol, bar['open_ms'])
                value = {**bar, 'available_ms': received, 'source_fingerprint': fingerprint,
                         'provenance': provenance}
                old = self.minutes[key].get(identity)
                if old is None or received < old['available_ms']:
                    self.minutes[key][identity] = value
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            self.errors.append({'provenance': provenance, 'error': str(exc)})

    def view(self, symbol, as_of_ms):
        rows, conflicts = [], []
        for (asset, minute), variants in self.minutes.items():
            if asset != symbol:
                continue
            available = [x for x in variants.values() if x['available_ms'] <= as_of_ms
                         and x['close_ms'] < as_of_ms]
            if len(available) > 1:
                conflicts.append(minute)
            elif available:
                rows.append(available[0])
        return sorted(rows, key=lambda x: x['open_ms']), sorted(conflicts)


def aggregate(rows, minutes):
    """UTC aligned complete bars only. Missing minutes never become flat bars."""
    size = minutes * 60000
    groups = collections.defaultdict(list)
    for row in rows:
        groups[row['open_ms'] // size].append(row)
    result = []
    for group, parts in sorted(groups.items()):
        parts.sort(key=lambda x: x['open_ms'])
        start = group * size
        if [x['open_ms'] for x in parts] != list(range(start, start + size, 60000)):
            continue
        result.append({'open_ms': start, 'close_ms': start + size - 1,
                       'o': parts[0]['o'], 'h': max(x['h'] for x in parts),
                       'l': min(x['l'] for x in parts), 'c': parts[-1]['c'],
                       'available_ms': max(x['available_ms'] for x in parts)})
    # A gap restarts the structural warmup; no inference across absent bars.
    suffix = []
    for bar in result:
        if suffix and bar['open_ms'] - suffix[-1]['open_ms'] != size:
            suffix = []
        suffix.append(bar)
    return suffix


def swing_direction(swings):
    highs = [x['price'] for x in swings if x['kind'] == 'HIGH']
    lows = [x['price'] for x in swings if x['kind'] == 'LOW']
    if len(highs) < 2 or len(lows) < 2:
        return None
    if highs[-1] > highs[-2] and lows[-1] > lows[-2]:
        return 'UP'
    if highs[-1] < highs[-2] and lows[-1] < lows[-2]:
        return 'DOWN'
    return None


def scan(bars):
    """Causal price-path state machine; all level/event records are copied."""
    state = 'UNKNOWN'
    reason = 'INSUFFICIENT_SWINGS'
    protected = None
    candidate = None
    active_range = None
    transition = None
    swings, pivots, events, snapshots = [], [], [], []
    consumed = set()
    available = 0
    dual = 0
    for i, bar in enumerate(bars):
        available = max(available, bar['available_ms'])
        def emit(kind, **fields):
            events.append({'kind': kind, 'bar_close_ms': bar['close_ms'],
                           'available_ms': available, **fields})

        # Previously known levels are evaluated BEFORE this bar confirms a pivot.
        if active_range and not active_range['low'] <= bar['c'] <= active_range['high']:
            direction = 'UP' if bar['c'] > active_range['high'] else 'DOWN'
            transition = {'direction': direction, 'from_state': 'RANGE',
                          'trigger_ms': bar['close_ms'], 'available_ms': available}
            emit('RANGE_BREAK_CANDIDATE', direction=direction, bounds=dict(active_range))
            active_range = None
            state, reason, protected = 'TRANSITION', 'RANGE_CLOSE_OUTSIDE', None
        elif state in ('TREND_UP', 'TREND_DOWN') and protected:
            broken = bar['c'] < protected['price'] if state == 'TREND_UP' else bar['c'] > protected['price']
            if broken:
                direction = 'DOWN' if state == 'TREND_UP' else 'UP'
                transition = {'direction': direction, 'from_state': state,
                              'trigger_ms': bar['close_ms'], 'available_ms': available}
                emit('PROTECTED_BREAK_CANDIDATE', direction=direction, anchor=dict(protected))
                state, reason, protected = 'TRANSITION', 'PROTECTED_CLOSE_BROKEN', None
        if candidate and not candidate['low'] <= bar['c'] <= candidate['high']:
            emit('RANGE_CANDIDATE_INVALIDATED', bounds=dict(candidate))
            candidate = None

        direction_before = swing_direction(swings)
        for kind, direction in [('HIGH', 'UP'), ('LOW', 'DOWN')]:
            point = next((x for x in reversed(swings) if x['kind'] == kind), None)
            if not point or i == 0 or point['confirmed_ms'] >= bar['close_ms']:
                continue
            crossed = (bars[i-1]['c'] <= point['price'] < bar['c'] if direction == 'UP'
                       else bars[i-1]['c'] >= point['price'] > bar['c'])
            key = (kind, point['pivot_ms'])
            if not crossed or key in consumed:
                continue
            consumed.add(key)
            emit('SWING_CLOSE_BREAK', direction=direction, pivot=dict(point))
            last_opposite = next((x for x in reversed(swings) if x['kind'] != kind), None)
            can_confirm = direction_before == direction and last_opposite is not None
            if transition:
                # New alternating structure must form after the original break.
                recent = [x for x in swings if x['pivot_ms'] > transition['trigger_ms']]
                can_confirm = (can_confirm and swing_direction(recent) == direction
                               and point['pivot_ms'] > transition['trigger_ms'])
            if can_confirm and active_range is None:
                desired = 'TREND_' + direction
                if state not in (desired, 'UNKNOWN', 'TRANSITION'):
                    continue  # opposing micro swing cannot overwrite a protected trend
                changed = state != desired
                state, reason, protected = desired, 'ALIGNED_SWINGS_AND_CLOSE_BREAK', dict(last_opposite)
                if changed:
                    emit('TREND_CONFIRMED', direction=direction, anchor=dict(protected),
                         previous_transition=transition)
                else:
                    emit('BOS_ANCHOR_UPDATED', direction=direction, anchor=dict(protected))
                transition = None

        if i >= LEFT + RIGHT:
            k = i - RIGHT
            p = bars[k]
            high = p['h'] > max(x['h'] for x in bars[k-LEFT:k]) and p['h'] >= max(x['h'] for x in bars[k+1:i+1])
            low = p['l'] < min(x['l'] for x in bars[k-LEFT:k]) and p['l'] <= min(x['l'] for x in bars[k+1:i+1])
            if high and low:
                dual += 1
            elif high or low:
                point = {'kind': 'HIGH' if high else 'LOW', 'price': p['h'] if high else p['l'],
                         'pivot_ms': p['open_ms'], 'confirmed_ms': bar['close_ms'],
                         'available_ms': available}
                pivots.append(dict(point))
                appended = not swings or swings[-1]['kind'] != point['kind']
                if appended:
                    swings.append(point)
                elif ((high and point['price'] >= swings[-1]['price'])
                      or (low and point['price'] <= swings[-1]['price'])):
                    swings[-1] = point
                # A fourth alternating reaction confirms the original frozen box.
                if candidate and appended and point['pivot_ms'] > candidate['third_ms']:
                    expected = 'HIGH' if candidate['origin'] == 'DOWN' else 'LOW'
                    boundary = candidate['high'] if expected == 'HIGH' else candidate['low']
                    if point['kind'] == expected and abs(point['price'] - boundary) <= candidate['tolerance']:
                        active_range = {**candidate, 'confirmed_ms': bar['close_ms'],
                                        'confirmed_available_ms': available}
                        emit('RANGE_CONFIRMED', bounds=dict(active_range))
                        candidate = None
                        state, reason, protected, transition = 'RANGE', 'FOUR_ALTERNATING_REACTIONS', None, None
                if not candidate and not active_range and appended and len(swings) >= 4 and i >= 14:
                    previous, p1, p2, p3 = swings[-4:]
                    origin = ('DOWN' if p1['kind'] == 'LOW' and p3['kind'] == 'LOW'
                              and previous['kind'] == 'HIGH' else 'UP')
                    # Require the first test to extend the prior same-side extreme.
                    earlier = next((x for x in reversed(swings[:-3]) if x['kind'] == p1['kind']), None)
                    prior_move = earlier and (p1['price'] < earlier['price'] if origin == 'DOWN'
                                             else p1['price'] > earlier['price'])
                    if prior_move:
                        lo, hi = sorted((p1['price'], p2['price']))
                        tr = [max(bars[j]['h']-bars[j]['l'], abs(bars[j]['h']-bars[j-1]['c']),
                                  abs(bars[j]['l']-bars[j-1]['c'])) for j in range(i-13, i+1)]
                        atr = sum(tr)/14
                        tolerance = RETEST_ATR * atr
                        valid_retest = abs(p3['price']-p1['price']) <= tolerance
                        inside = all(lo <= x['c'] <= hi for x in bars[:i+1] if x['open_ms'] >= p1['pivot_ms'])
                        if atr > 0 and hi-lo >= MIN_WIDTH_ATR*atr and valid_retest and inside:
                            candidate = {'low': lo, 'high': hi, 'origin': origin, 'first_ms': p1['pivot_ms'],
                                         'second_ms': p2['pivot_ms'], 'third_ms': p3['pivot_ms'],
                                         'created_ms': bar['close_ms'], 'available_ms': available,
                                         'tolerance': tolerance, 'atr14_sma_at_creation': atr}
                            emit('RANGE_CANDIDATE', bounds=dict(candidate))
        visible = state if i+1 >= MIN_BARS else 'UNKNOWN'
        snapshots.append({'bar_close_ms': bar['close_ms'], 'available_ms': available,
                          'state': visible, 'reason': reason if i+1 >= MIN_BARS else 'INSUFFICIENT_WARMUP',
                          'protected': dict(protected) if protected else None,
                          'range': dict(active_range) if active_range else None,
                          'range_candidate': dict(candidate) if candidate else None,
                          'transition': dict(transition) if transition else None})
    last = snapshots[-1] if snapshots else {'state': 'UNKNOWN', 'reason': 'NO_COMPLETE_BARS'}
    return {**last, 'closed_bars': len(bars), 'pivots': pivots, 'swings': swings,
            'events': events, 'snapshots': snapshots, 'dual_pivots_excluded': dual}


def describe(rows, conflicts, at_ms):
    result = {}
    for frame, minutes in FRAMES.items():
        bars = aggregate(rows, minutes)
        computed = scan(bars)
        # Full latest expected bar must exist, not an arbitrary stale suffix.
        size = minutes*60000
        expected = int(at_ms // size)*size - size
        if not bars or bars[-1]['open_ms'] != expected:
            computed.update(state='UNKNOWN', reason='LATEST_COMPLETE_BAR_MISSING')
        if conflicts:
            computed.update(state='UNKNOWN', reason='CONFLICTING_CLOSED_SOURCE')
        if bars and max(x['available_ms'] for x in bars) > at_ms:
            raise ValueError('future bar leaked')
        result[frame] = {k: v for k, v in computed.items() if k not in ('pivots', 'swings', 'events', 'snapshots')}
        result[frame].update(last_swings=computed['swings'][-6:],
                             recent_events=computed['events'][-8:], event_count=len(computed['events']),
                             event_ledger_sha256=digest(computed['events']),
                             bars_sha256=digest(bars))
        box = computed.get('range')
        result[frame]['last_closed_price'] = bars[-1]['c'] if bars else None
        result[frame]['range_position_closed'] = ((bars[-1]['c']-box['low'])/(box['high']-box['low'])
                                                  if computed['state'] == 'RANGE' and box else None)
    # Do not fall back to a lower frame and call it complete HTF context.
    context = 'READY' if all(result[f]['state'] != 'UNKNOWN' for f in ('H4', 'H1')) else 'UNKNOWN_HTF_CONTEXT'
    def relation(parent, child):
        if parent == 'UNKNOWN' or child == 'UNKNOWN':
            return 'UNKNOWN_OR_OTHER'
        return ('CORRECTION_CANDIDATE' if (parent, child) in (('TREND_UP', 'TREND_DOWN'), ('TREND_DOWN', 'TREND_UP'))
                else 'ALIGNED_TRENDS' if parent == child and parent in ('TREND_UP', 'TREND_DOWN')
                else 'RANGE_CONTEXT' if parent == 'RANGE' else 'TRANSITION_CONTEXT' if parent == 'TRANSITION'
                else 'UNKNOWN_OR_OTHER')
    return {'frames': result, 'top_down_context': context,
            'h4_h1_relation': relation(result['H4']['state'], result['H1']['state']),
            'h1_m15_relation': relation(result['H1']['state'], result['M15']['state']),
            'conflicting_minutes': conflicts, 'source_minutes': len(rows),
            'minute_view_sha256': digest(rows)}


def build_report(manifest, state_path):
    store = MinuteStore()
    artifacts = []
    for item in manifest:
        artifact = item['artifact']
        run = item['run']
        if (run.get('head_branch') != 'main' or run.get('event') == 'pull_request'
                or run.get('status') != 'completed' or run.get('conclusion') != 'success'
                or run.get('name') != 'Limitless independent market capture'
                or run['id'] != artifact['workflow_run']['id']
                or run['head_sha'] != artifact['workflow_run']['head_sha']):
            raise ValueError('not a verified completed main market capture')
        path = pathlib.Path(item['file']['path'])
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        if artifact.get('digest') != 'sha256:' + sha:
            raise ValueError('artifact ZIP digest mismatch')
        artifacts.append({'id': artifact['id'], 'run': run, 'sha256': sha})
        with zipfile.ZipFile(path) as archive:
            for line_number, line in enumerate(gzip.GzipFile(fileobj=archive.open('capture.jsonl.gz')), 1):
                # Ignore unrelated public Limitless envelopes; no v1/v2 replay.
                if b'binance_1m' not in line:
                    continue
                row = json.loads(line)
                store.add(row, {'artifact': artifact['id'], 'line': line_number, 'run': run['id']})
    # State is verified independently against the same manifest, not guessed by path.
    state_sha = hashlib.sha256(pathlib.Path(state_path).read_bytes()).hexdigest()
    state_artifact = next((a['id'] for a in artifacts if a['sha256'] == state_sha), None)
    if state_artifact is None:
        raise ValueError('state ZIP is outside verified manifest')
    with zipfile.ZipFile(state_path) as archive:
        state_bytes = archive.read('state.json')
        state = json.loads(state_bytes)
        source_as_of = json.loads(archive.read('summary.json'))['ended_at']
    end_ms = milliseconds(source_as_of)
    if state['paper'].get('version') != 'limitless-hourly-v1':
        raise ValueError('unsupported hourly state version')
    results = []
    for condition, episode in sorted(state['paper']['episodes'].items()):
        if 'brier_model' not in episode:
            continue
        symbol = episode['symbol']
        at_ms = milliseconds(episode['decision_at'])
        if (symbol not in ('BTCUSDT', 'ETHUSDT') or episode['condition'] != condition
                or not math.isfinite(episode['start']) or episode['start'] % 3600
                or not episode['start']*1000 <= at_ms < (episode['start']+3600)*1000
                or at_ms > end_ms or episode.get('phase') not in ('discovery', 'holdout')):
            raise ValueError('invalid scored hourly episode')
        rows, conflicts = store.view(symbol, at_ms)
        diagnostic = describe(rows, conflicts, at_ms)
        opening = float(episode['opening'])
        reference = float(episode['reference_price'])
        p_up = episode['p_up']
        if not all(math.isfinite(x) and x > 0 for x in (opening, reference)) or not math.isfinite(p_up) or not 0 <= p_up <= 1:
            raise ValueError('invalid episode prices/probability')
        for frame in diagnostic['frames'].values():
            box = frame.get('range')
            frame['range_position_reference'] = ((reference-box['low'])/(box['high']-box['low'])
                                                  if frame['state'] == 'RANGE' and box else None)
        results.append({'condition': condition, 'symbol': symbol, 'decision_ms': at_ms,
                        'hour_start': episode['start'], 'phase': episode['phase'],
                        'model_status': episode['variants']['model']['status'],
                        'p_up': episode['p_up'], 'opening': opening, 'reference_price': reference,
                        'distance_from_hour_open': reference-opening,
                        'seconds_to_hour_end': episode['start']+3600-episode['decision_at'],
                        **diagnostic})
    counts = {frame: dict(collections.Counter(r['frames'][frame]['state'] for r in results)) for frame in FRAMES}
    conflicts = [{'symbol': symbol, 'open_ms': minute,
                  'variants': sorted(variants.values(), key=lambda x: x['available_ms'])}
                 for (symbol, minute), variants in sorted(store.minutes.items()) if len(variants) > 1]
    coverage = {symbol: {'first_open_ms': min(k[1] for k in store.minutes if k[0] == symbol),
                         'last_open_ms': max(k[1] for k in store.minutes if k[0] == symbol),
                         'unique_closed_minutes': sum(k[0] == symbol for k in store.minutes)}
                for symbol in sorted({k[0] for k in store.minutes})}
    return {'version': VERSION, 'status': 'RECONCILED_DIAGNOSTIC_ONLY' if not store.errors else 'UNRECONCILED',
            'report': None if store.errors else {'decisions': len(results),
                'hour_clusters': len({r['hour_start'] for r in results}), 'state_counts': counts,
                'phase_counts': dict(collections.Counter(r['phase'] for r in results)),
                'conflicting_decisions': sum(bool(r['conflicting_minutes']) for r in results),
                'ready_top_down': sum(r['top_down_context'] == 'READY' for r in results)},
            'source_as_of': source_as_of, 'implementation_sha256': hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),
            'state_artifact': state_artifact, 'state_json_sha256': hashlib.sha256(state_bytes).hexdigest(),
            'artifacts': artifacts, 'binance_requests': store.requests,
            'data_errors': store.errors, 'closed_candle_conflicts': conflicts, 'source_coverage': coverage,
            'results': results,
            'parameters': {'min_bars': MIN_BARS, 'left': LEFT, 'right': RIGHT,
                           'retest_atr': RETEST_ATR, 'min_width_atr': MIN_WIDTH_ATR},
            'limitations': ['Post-hoc fixed discovery snapshot; no calibration or economic promotion.',
                            'Historical closed bars can arrive later; available_ms is receipt, not candle event time.',
                            'Events describe confirmed price-path geometry, not contemporaneous orders or fills.',
                            'State names are this diagnostic protocol, not universal ICT/Wyckoff definitions.',
                            'No alteration of frozen hourly/inventory or existing M1 validation protocol.']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--state-zip', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = build_report(json.loads(pathlib.Path(args.manifest).read_text()), args.state_zip)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile) as exc:
        result = {'version': VERSION, 'status': 'UNRECONCILED', 'report': None, 'error': str(exc)}
    pathlib.Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k: result.get(k) for k in ('version', 'status', 'report', 'error')}, ensure_ascii=False))
    raise SystemExit(0 if result['status'] == 'RECONCILED_DIAGNOSTIC_ONLY' else 1)
