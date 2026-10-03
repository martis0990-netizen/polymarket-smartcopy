"""Pinned review probes, not strategy acceptance tests. No network or orders.

Run against bd67203: python research/review_limitless_inventory_v1.py --out review.json
Synthetic observations reproduce defects; they are not measured trading results.
"""
import argparse
import copy
import hashlib
import json
import pathlib
import tempfile
import zipfile
from decimal import ROUND_UP
from unittest.mock import patch

from limitless_hourly_paper import HourlyPaper
from limitless_inventory_paper import InventoryPaper, archive_report, number, MICRO, HOLDOUT, VERSION
from test_limitless_inventory_paper import seeded, market, book, START, MID

REVIEWED_COMMIT = 'bd67203e8d35eb8768e85eb4e6a1ec30c8c81df0'


def checkpoints(states):
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i, state in enumerate(states):
            path = pathlib.Path(tmp) / f'{i}.zip'
            with zipfile.ZipFile(path, 'w') as archive:
                archive.writestr('state.json', json.dumps({'inventory_paper': state}))
                archive.writestr('summary.json', json.dumps({'ended_at': MID+100+i}))
            paths.append(path)
        report = archive_report(paths)
        return {k: report[k] for k in ('status', 'errors', 'report')}


def run():
    findings = {}
    # Generate the seed through the existing hourly entry decision and delayed fill.
    paper = HourlyPaper()
    paper.market(market(), MID)
    entry_book = book('.55', '.57')
    with patch.object(paper, '_inputs', return_value=(.606, .01, 100, MID)):
        paper.book('btc-hour', entry_book, MID, MID-.1)
    paper.book('btc-hour', entry_book, MID+2, MID+1.6)
    manager = InventoryPaper(started_at=MID-1)
    manager.book(paper, market(), entry_book, MID+2, MID+1.6)
    pos = manager.state['positions']['condition-1']
    raw_size = int((number(pos['quantity']['YES'])/MICRO).to_integral_value(rounding=ROUND_UP))
    decision_book = {'tokenId': 'token', 'bids': [
        {'price': '.95', 'size': raw_size}, {'price': '.58', 'size': 100000000}],
        'asks': [{'price': '.97', 'size': 100000000}]}
    with patch.object(paper, '_inputs', return_value=(.6, .01, 100, MID+3)):
        manager.book(paper, market(), decision_book, MID+3, MID+2.9)
    decision = copy.deepcopy(pos['management'])
    manager.book(paper, market(), book('.58', '.60'), MID+5, MID+4.6)
    findings['R1_EXECUTION_PAIR_PROFIT_NOT_RECHECKED'] = {
        'entry_cost': pos['entry_cost'], 'entry_net_shares': pos['entry_net_shares'],
        'decision_action': decision['action'], 'decision_locked_profit': decision['locked_profit'],
        'decision_buy_cost': decision['gross_cash'], 'price_bound': decision['price_bound'],
        'execution_buy_cost': pos['management']['execution']['gross_cash'],
        'execution_price_bound': pos['management']['execution']['price_bound'],
        'execution_status': pos['management']['status'], 'merge_pnl': pos['paper_merge']['pnl_usdc'],
        'cash': manager.state['cash'],
        'observed_violation': pos['management']['status']=='PAPER_EXECUTED'
            and number(pos['paper_merge']['pnl_usdc']) < 0}

    paper, manager = seeded()
    before = copy.deepcopy(manager.state)
    after = copy.deepcopy(before)
    after['cash'] = str(number(after['cash'])+5)
    after['realized_pnl'] = '5'
    invented = checkpoints([before, after])
    with patch.object(paper, '_inputs', return_value=(.6, .01, 100, MID+3)):
        manager.book(paper, market(), book(), MID+3, MID+2.9)
    pending = copy.deepcopy(manager.state)
    changed = copy.deepcopy(pending)
    changed['positions']['condition-1']['management']['quantity'] = '1'
    changed['positions']['condition-1']['management']['price_bound'] = '.99'
    rewritten = checkpoints([pending, changed])
    findings['R2_CHECKPOINT_RECONCILIATION_INCOMPLETE'] = {
        'invented_cash_and_pnl_status': invented['status'],
        'invented_realized_pnl': invented['report']['realized_pnl'] if invented['report'] else None,
        'rewritten_pending_order_status': rewritten['status'],
        'observed_violation': invented['status']=='RECONCILED_PAPER_ONLY'
            and rewritten['status']=='RECONCILED_PAPER_ONLY'}

    _, manager = seeded()
    manager.market(market(status='RESOLVED', winningOutcomeIndex=0), START+3601)
    second_start = HOLDOUT+13*3600
    second_market = market(slug='holdout-hour', conditionId='holdout-condition',
        startAt=second_start, expirationTimestamp=(second_start+3600)*1000)
    second_market['metadata']['chart']['windowOpenAt'] = second_start
    ep = {'condition': 'holdout-condition', 'slug': 'holdout-hour', 'decision_at': second_start+1800,
        'variants': {'model': {'status': 'FILLED', 'side': 'YES', 'fill_at': second_start+1802,
            'cost_usdc': '10', 'net_shares': '24.25'}}}
    manager.admit(ep, second_market, second_start+1802)
    second_market.update(status='RESOLVED', winningOutcomeIndex=1)
    manager.market(second_market, second_start+3601)
    report = manager.report()
    findings['R3_PHASE_PNL_MISSING'] = {
        'true_discovery_managed_pnl': '14.25', 'true_holdout_managed_pnl': '-10',
        'pooled_managed_settled_pnl': report['managed_settled_pnl'], 'reported_phases': report['phases'],
        'observed_violation': all('managed_settled_pnl' not in phase for phase in report['phases'].values())}

    _, manager = seeded()
    unresolved_payout = market(status='RESOLVED', winningOutcomeIndex=None)
    manager.market(unresolved_payout, START+3601)
    # These are the collector's exact retirement/persistence expressions.
    watched = {'btc-hour': {'market': unresolved_payout,
        'resolved': unresolved_payout.get('status') == 'RESOLVED'}}
    carried = {slug: item for slug, item in watched.items() if not item.get('resolved')}
    position_open = not manager.state['positions']['condition-1'].get('settled_at')
    findings['R4_UNVERIFIED_SETTLEMENT_RETIRES_WATCH'] = {
        'position_still_open': position_open, 'cash': manager.state['cash'],
        'open_cost_basis': manager.report()['open_cost_basis'], 'carried_slugs': sorted(carried),
        'observed_violation': position_open and 'btc-hour' not in carried}

    _, manager = seeded()
    manager.market(market(status='RESOLVED', winningOutcomeIndex=0), float('nan'))
    findings['R5_NONFINITE_SETTLEMENT_TIME'] = {
        'nan_settlement_time_accepted': manager.report()['settled_positions']==1,
        'observed_violation': manager.report()['settled_positions']==1}

    paper = HourlyPaper()
    paper.market(market(), MID)
    manager = InventoryPaper(started_at=MID-1)
    with patch.object(paper, '_inputs', return_value=(.606, .01, 100, MID)):
        paper.book('btc-hour', entry_book, MID, MID-.1)
    manager.book(paper, market(), entry_book, MID, MID-.1)
    # Exact collector raw=None branch: hourly book() is not called.
    manager.unavailable_book('btc-hour', MID+2, MID+1.6)
    status_after_failure = paper.state['episodes']['condition-1']['variants']['model']['status']
    later_book = book('.54', '.56')
    paper.book('btc-hour', later_book, MID+18, MID+17.9)
    manager.book(paper, market(), later_book, MID+18, MID+17.9)
    later = paper.state['episodes']['condition-1']['variants']['model']
    findings['R6_ENTRY_RETRIES_AFTER_UNAVAILABLE_FIRST_BOOK'] = {
        'first_eligible_attempt_failed_at': MID+2, 'hourly_status_after_failure': status_after_failure,
        'hourly_status_after_later_success': later['status'], 'later_fill_at': later.get('fill_at'),
        'inventory_admitted_later_fill': 'condition-1' in manager.state['positions'],
        'observed_violation': status_after_failure=='PENDING' and later['status']=='FILLED'
            and 'condition-1' in manager.state['positions']}
    hashes = {name: hashlib.sha256(pathlib.Path(__file__).with_name(name).read_bytes()).hexdigest()
        for name in ('limitless_inventory_paper.py', 'limitless_hourly_paper.py', 'limitless_market_capture.py')}
    return {'reviewed_commit': REVIEWED_COMMIT, 'status': 'SYNTHETIC_REVIEW_NOT_TRADING_RESULTS',
        'source_sha256': hashes, 'findings': findings,
        'all_findings_reproduced': all(f['observed_violation'] for f in findings.values())}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=pathlib.Path, required=True)
    args = parser.parse_args()
    if VERSION != 'limitless-inventory-paper-v1':
        parser.error('Pinned v1 diagnostic: use the reviewed bd67203 sources. Current v2 fixes use test_limitless_inventory_paper.py and test_limitless_capture_integration.py.')
    result = run()
    args.out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'status': result['status'], 'findings': len(result['findings']),
        'all_findings_reproduced': result['all_findings_reproduced']}))
    raise SystemExit(0 if result['all_findings_reproduced'] else 1)
