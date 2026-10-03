#!/usr/bin/env python3
"""Bounded public Limitless candidate discovery. No orders or copy PnL."""
import argparse
import datetime as dt
import gzip
import hashlib
import json
import pathlib
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://api.limitless.exchange'
ADDRESS = re.compile(r'^0x[0-9a-fA-F]{40}$')
CRYPTO = re.compile(r'(BTC|ETH|Bitcoin|Ethereum).*(15 Min|Hourly)', re.I)
CUTOFF = dt.datetime(2026, 10, 10, 9, tzinfo=dt.timezone.utc)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def items(payload):
    if isinstance(payload, list):
        return [x for x in payload if isinstance(x, dict)]
    if isinstance(payload, dict):
        for key in ('data', 'events', 'history', 'items'):
            if isinstance(payload.get(key), list):
                return items(payload[key])
    return []


def discover(snapshots, observed_at, previous):
    """All sources contribute; roster priority is round-robin, never historical PnL."""
    pools, candidates = [], {}
    for source, payload in snapshots:
        if source.startswith('leaderboard') and payload.get('state') != 'READY':
            continue
        pool = []
        for row in items(payload):
            profile = row.get('profile') or {}
            address = row.get('account') or profile.get('account')
            if not isinstance(address, str) or not ADDRESS.fullmatch(address):
                continue
            address = address.lower()
            if address not in pool:
                pool.append(address)
            market = row.get('market') or row.get('subject') or {}
            title = market.get('title') or ''
            candidate = candidates.setdefault(address, {
                'account': address, 'first_seen_at': previous.get(address, observed_at),
                'sources': [], 'crypto_btc_eth_15m_hourly_seen': False,
                'qualification': 'UNASSESSED_NO_COPY_PERMISSION',
            })
            if source not in candidate['sources']:
                candidate['sources'].append(source)
            candidate['crypto_btc_eth_15m_hourly_seen'] |= bool(CRYPTO.search(title))
        pools.append(pool)
    ordered = []
    for index in range(max(map(len, pools), default=0)):
        for pool in pools:
            if index < len(pool) and pool[index] not in ordered:
                ordered.append(pool[index])
    return [candidates[a] for a in ordered]


def event_key(row):
    for key in ('tradeEventId', 'id', 'uid'):
        if row.get(key) is not None:
            return str(row[key])
    stable = {k: row.get(k) for k in ('transactionHash', 'orderId', 'blockTimestamp',
              'strategy', 'outcomeIndex', 'outcomeTokenAmount', 'collateralAmount')}
    stable['market_id'] = (row.get('market') or {}).get('id')
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode()).hexdigest()


def history_summary(rows):
    unique = {event_key(row): row for row in rows}
    markets, crypto = set(), 0
    for row in unique.values():
        market = row.get('market') or {}
        key = market.get('conditionId') or market.get('condition_id') or market.get('id')
        if key is not None:
            markets.add(str(key))
        crypto += bool(CRYPTO.search(market.get('title') or ''))
    return {'sampled_unique_events': len(unique), 'sampled_conditions': len(markets),
            'sampled_crypto_events': crypto,
            'independent_intent_episodes': None, 'copy_pnl': None}


def pnl_summary(payload):
    """API values are USD strings; no unit guessing or profitability gate."""
    if not isinstance(payload, dict) or not isinstance(payload.get('current'), dict):
        return {'status': 'SCHEMA_UNKNOWN'}
    return {'status': 'API_BEST_EFFORT_WINDOW_PNL', 'timeframe': payload.get('timeframe'),
            'window_start': payload.get('windowStart'),
            'realized_pnl_usd': payload['current'].get('usd'),
            'categories': payload.get('categories'),
            'timeline_points': len(payload.get('data') or []),
            'portfolio_drawdown': None}


class Client:
    def __init__(self, archive, deadline):
        self.archive, self.deadline = archive, deadline
        self.requests, self.errors, self.blocked_until = 0, 0, 0

    def get(self, path, params=None):
        if not (path == '/feed/trading' or
                path == '/leaderboard/pnl/unrealized/biggest-positions' or
                re.fullmatch(r'/portfolio/0x[0-9a-f]{40}/(history|realized-pnl)', path)):
            raise ValueError('Public read endpoint not whitelisted')
        if (time.monotonic() >= self.deadline or time.monotonic() < self.blocked_until
                or dt.datetime.now(dt.timezone.utc) >= CUTOFF):
            return None
        time.sleep(.4)
        started = now()
        self.requests += 1
        envelope = {'path': path, 'params': params, 'request_started_at': started}
        try:
            request = urllib.request.Request(BASE + path + '?' + urllib.parse.urlencode(params or {}),
                         headers={'Accept': 'application/json', 'User-Agent': 'SmartCopyDiscovery/1'})
            with urllib.request.urlopen(request, timeout=8) as response:
                raw = response.read(2 * 1024 * 1024 + 1)
                if len(raw) > 2 * 1024 * 1024:
                    raise ValueError('Response exceeds 2 MiB cap')
                payload = json.loads(raw)
                envelope.update(http_status=response.status,
                                cache_control=response.headers.get('Cache-Control'),
                                age=response.headers.get('Age'), payload=payload)
        except (OSError, ValueError) as exc:
            self.errors += 1
            envelope['error'] = str(exc)[:500]
            if isinstance(exc, urllib.error.HTTPError):
                envelope['http_status'] = exc.code
                if exc.code == 429:
                    self.blocked_until = time.monotonic() + 60
            payload = None
        envelope['response_observed_at'] = now()
        self.archive.write(json.dumps(envelope, ensure_ascii=False) + '\n')
        self.archive.flush()
        return payload


def run(args):
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    started = now()
    previous = {}
    if args.state and pathlib.Path(args.state).exists():
        checkpoint = json.loads(pathlib.Path(args.state).read_text())
        if checkpoint.get('schema') != 'limitless-discovery-v1':
            raise ValueError('Unknown checkpoint schema')
        previous = checkpoint['first_seen']
    snapshots = []
    candidates = []
    selected = []
    with gzip.open(out / 'requests.jsonl.gz', 'wt', encoding='utf-8') as archive:
        client = Client(archive, time.monotonic() + 600)
        if dt.datetime.now(dt.timezone.utc) < CUTOFF:
            for metric in ('position_size', 'pnl'):
                payload = client.get('/leaderboard/pnl/unrealized/biggest-positions',
                                     {'metric': metric, 'limit': 50})
                if isinstance(payload, dict):
                    snapshots.append(('leaderboard_' + metric, payload))
            payload = client.get('/feed/trading', {'audience': 'all', 'limit': 30})
            if isinstance(payload, (dict, list)):
                snapshots.append(('public_feed', payload))
            # Selection timestamp precedes all history/PnL enrichment.
            selection_at = now()
            candidates = discover(snapshots, selection_at, previous)
            for row in candidates:
                previous.setdefault(row['account'], row['first_seen_at'])
            selected = candidates[:args.max_wallets]
            for candidate in selected:
                account = candidate['account']
                rows, cursor, seen_cursors = [], None, set()
                candidate['selected_at'] = selection_at
                candidate['history_status'] = 'TRUNCATED_OR_UNKNOWN'
                for page in range(args.history_pages):
                    params = {'limit': 30}
                    if cursor is not None:
                        params['cursor'] = cursor
                    history = client.get('/portfolio/' + account + '/history', params)
                    if history is None:
                        candidate['history_status'] = 'REQUEST_FAILED_OR_BUDGET_EXHAUSTED'
                        break
                    if not (isinstance(history, list) or (isinstance(history, dict) and
                            any(isinstance(history.get(k), list) for k in ('data', 'events', 'history', 'items')))):
                        candidate['history_status'] = 'SCHEMA_UNKNOWN'
                        break
                    rows.extend(items(history))
                    cursor = history.get('nextCursor') if isinstance(history, dict) else None
                    if not cursor:
                        candidate['history_status'] = 'END_OF_AVAILABLE_API_HISTORY'
                        break
                    if not isinstance(cursor, str) or cursor in seen_cursors:
                        candidate['history_status'] = 'INVALID_OR_REPEATED_CURSOR'
                        break
                    seen_cursors.add(cursor)
                candidate.update(history_summary(rows))
                candidate['pnl'] = {}
                for timeframe in ('1w', '1m'):
                    pnl = client.get('/portfolio/' + account + '/realized-pnl', {'timeframe': timeframe})
                    candidate['pnl'][timeframe] = pnl_summary(pnl) if pnl is not None else {'status': 'UNAVAILABLE'}
        states = {source: payload.get('state') for source, payload in snapshots if source.startswith('leaderboard')}
        report = {'schema': 'limitless-discovery-v1', 'status': 'DISCOVERY_ONLY_NO_SKILL_OR_COPYABILITY_CLAIM',
                  'started_at': started, 'finished_at': now(), 'leaderboard_states': states,
                  'requests': client.requests, 'request_errors': client.errors,
                  'candidate_count': len(candidates), 'enriched_count': len(selected),
                  'candidate_selection': 'round-robin source order before history/PnL, capped; not global ranking',
                  'candidates': candidates,
                  'limitations': ['Leaderboard size/open PnL is not wallet skill.',
                     'PnL is best-effort API projection, not independently reconciled ledger.',
                     'History is bounded and may be incomplete; events are not independent intents.',
                     'No portfolio drawdown, return on capital or follower PnL calculated.',
                     'Discovery addresses do not enter the frozen wallet cohort.',
                     'No observed-time execution or forward validation for these candidates yet.']}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    # Keep earliest observation only. Bound the durable candidate catalog.
    first_seen = dict(sorted(previous.items(), key=lambda x: (x[1], x[0]))[:10000])
    (out / 'state.json').write_text(json.dumps({'schema': 'limitless-discovery-v1', 'first_seen': first_seen}) + '\n')
    lines = ['# Limitless wallet discovery', '', report['status'], '',
             f"Candidates: {len(candidates)}; enriched: {len(selected)}; request errors: {client.errors}.", '',
             '| Wallet | Sampled conditions | Crypto events | 7d API PnL, USD | 1m API PnL, USD |',
             '|---|---:|---:|---:|---:|']
    for row in selected:
        pnl = row['pnl']
        lines.append(f"| `{row['account']}` | {row['sampled_conditions']} | {row['sampled_crypto_events']} | "
                     f"{pnl['1w'].get('realized_pnl_usd', 'unknown')} | {pnl['1m'].get('realized_pnl_usd', 'unknown')} |")
    lines += ['', *['- ' + x for x in report['limitations']]]
    (out / 'report.md').write_text('\n'.join(lines) + '\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'candidates'}, ensure_ascii=False))
    return 1 if client.requests and client.requests == client.errors else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='limitless_discovery')
    parser.add_argument('--state')
    parser.add_argument('--max-wallets', type=int, choices=range(1, 21), default=12)
    parser.add_argument('--history-pages', type=int, choices=range(1, 4), default=2)
    raise SystemExit(run(parser.parse_args()))
