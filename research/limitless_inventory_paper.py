"""Independent, funded inventory-management paper variant. No network or orders."""
import copy
import datetime as dt
import hashlib
import json
import math
from decimal import Decimal, ROUND_UP
from collections import Counter
from limitless_hourly_paper import levels, spec

D = Decimal
VERSION = 'limitless-inventory-paper-v2'
LEGACY_VERSION = 'limitless-inventory-paper-v1'
CAPITAL = D('100')
ENTRY_LIMIT = D('10')
CONDITION_LIMIT = D('20')
BUY_FEE = D('.03')
SELL_FEE = D('.015')
MERGE_COST = D('.01')  # explicit hypothetical reserve, not a measured on-chain fee
PROBABILITY_STRESS = D('.03')  # scenario width, NOT a confidence interval
PAIR_HURDLE = D('.02')
MICRO = D('.000001')
LEDGER_EPS = D('1e-18')
HOLDOUT = dt.datetime(2026, 10, 6, tzinfo=dt.timezone.utc).timestamp()


def timestamp(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError('INVALID_OBSERVATION_TIME')
    number(value)
    if not math.isfinite(value) or value < 0:
        raise ValueError('INVALID_OBSERVATION_TIME')
    return value


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                   allow_nan=False).encode()).hexdigest()


def market_identity(market):
    s = spec(market)
    if s is None:
        raise ValueError('UNVERIFIED_MARKET')
    timestamp(s['start']); timestamp(s['end'])
    tokens = market.get('tokens') or {}
    if (market.get('marketType') != 'single' or market.get('groupId') or not tokens.get('no')
            or tokens.get('yes') == tokens.get('no')
            or str(market['collateralToken'].get('address')).lower() != '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'):
        raise ValueError('UNVERIFIED_MARKET')
    return {**s, 'no_token': market['tokens']['no'],
            'collateral': str(market['collateralToken']['address']).lower()}


def payouts(market):
    winner, nums = market.get('winningOutcomeIndex'), market.get('payoutNumerators')
    result = None
    if type(winner) is int and winner in (0, 1):
        result = [D(1), D(0)] if winner == 0 else [D(0), D(1)]
    if nums is not None:
        if not isinstance(nums, list) or len(nums) != 2:
            return None
        try:
            nums = list(map(number, nums))
            if min(nums) < 0 or sum(nums) <= 0:
                return None
            split = [n/sum(nums) for n in nums]
            if result is not None and result != split:
                return None
            result = split
        except (ValueError, ArithmeticError):
            return None
    return result


def number(value):
    n = D(str(value))
    if not n.is_finite():
        raise ValueError('NONFINITE_NUMBER')
    return n


def value(yes, no, p):
    """Worst portfolio payoff over p +/- stress; matched pairs retain payoff one."""
    p = number(p)
    if not 0 <= p <= 1:
        raise ValueError('INVALID_PROBABILITY')
    lo, hi = max(D(0), p-PROBABILITY_STRESS), min(D(1), p+PROBABILITY_STRESS)
    return min(lo*yes+(1-lo)*no, hi*yes+(1-hi)*no)


def quote(book, side, quantity, buy):
    """Complete visible depth only; quantities are gross contracts for buys."""
    q = number(quantity)
    if side not in ('YES', 'NO') or q <= 0:
        raise ValueError('INVALID_QUANTITY_OR_SIDE')
    for side_levels in (book.get('bids', []), book.get('asks', [])):
        for level in side_levels:
            raw = number(level['size'])
            if raw < 0 or raw != raw.to_integral_value():
                raise ValueError('INVALID_RAW_SHARE_UNITS')
    ask_yes, ask_no = levels(book, 'YES'), levels(book, 'NO')
    if not ask_yes or not ask_no or ask_yes[0][0]+ask_no[0][0] <= 1:
        raise ValueError('EMPTY_CROSSED_OR_LOCKED_BOOK')
    if buy:
        prices = ask_yes if side == 'YES' else ask_no
    else:
        prices = sorted(((1-p, n) for p,n in (ask_no if side == 'YES' else ask_yes)), reverse=True)
    remaining, total, worst = q, D(0), None
    for price, size in prices:
        take = min(remaining, size)
        if take:
            total += take*price
            remaining -= take
            worst = price
        if remaining == 0:
            break
    if remaining or total <= 0:
        return None
    return {'gross_quantity': str(q), 'gross_cash': str(total),
            'net_quantity': str(q*(1-BUY_FEE)) if buy else str(q),
            'net_cash': str(total) if buy else str(total*(1-SELL_FEE)),
            'price_bound': str(worst)}


class InventoryPaper:
    def __init__(self, state=None, started_at=0, emit=None):
        self.state = copy.deepcopy(state) if state is not None else {
            'version': VERSION, 'started_at': started_at, 'cash': str(CAPITAL),
            'positions': {}, 'admission_skips': {}, 'entry_attempts': {}, 'realized_pnl': '0'}
        if self.state.get('version') != VERSION:
            raise ValueError('INCOMPATIBLE_INVENTORY_STATE')
        self.emit = emit or (lambda *a, **k: None)
        self.validate()

    def validate(self):
        timestamp(self.state['started_at'])
        cash = number(self.state['cash'])
        pnl = number(self.state['realized_pnl'])
        basis = D(0)
        expected_cash, expected_pnl = CAPITAL, D(0)
        events = []
        for key, attempt in self.state['entry_attempts'].items():
            for field in ('observed','requested','decision_at','eligible_after','expires_at'):
                timestamp(attempt[field])
            if (attempt['requested'] > attempt['observed'] or attempt['condition'] != key
                    or not self.state['started_at'] <= attempt['decision_at'] < attempt['eligible_after'] <= attempt['requested']
                    or attempt['expires_at'] != attempt['decision_at']+30):
                raise ValueError('INVALID_ENTRY_ATTEMPT')
        for key, pos in self.state['positions'].items():
            if pos['condition'] != key or pos['phase'] != ('holdout' if pos['entry_decision_at'] >= HOLDOUT else 'discovery'):
                raise ValueError('INVALID_POSITION_IDENTITY')
            timestamp(pos['seed_at']); timestamp(pos['entry_decision_at'])
            if not self.state['started_at'] <= pos['entry_decision_at'] <= pos['seed_at'] < pos['identity']['end']:
                raise ValueError('INVALID_ENTRY_TIMES')
            attempt = self.state['entry_attempts'][key]
            q = self.entry_quote(attempt)
            if (q is None or pos['entry_side'] != attempt['side'] or pos['identity'] != attempt['identity']
                    or pos['slug'] != pos['identity']['slug'] or pos['hour_start'] != pos['identity']['start']
                    or pos['seed_at'] != attempt['observed'] or pos['entry_decision_at'] != attempt['decision_at']
                    or number(pos['entry_cost']) != number(q['gross_cash'])
                    or number(pos['entry_net_shares']) != number(q['net_quantity'])):
                raise ValueError('ENTRY_SOURCE_MISMATCH')
            rebuilt = self.rebuild(pos)
            events.extend(rebuilt['events'])
            expected_cash += rebuilt['cash_delta']; expected_pnl += rebuilt['pnl']
            if abs(number(pos['spent_total'])-rebuilt['spent_total']) > LEDGER_EPS:
                raise ValueError('SPEND_LEDGER_MISMATCH')
            for side in ('YES','NO'):
                q, cost = number(pos['quantity'][side]), number(pos['basis'][side])
                if q < 0 or cost < 0 or (q == 0 and cost != 0):
                    raise ValueError('INVALID_INVENTORY')
                if abs(q-rebuilt['quantity'][side]) > LEDGER_EPS or abs(cost-rebuilt['basis'][side]) > LEDGER_EPS:
                    raise ValueError('POSITION_LEDGER_MISMATCH')
                basis += cost
        if abs(cash-expected_cash) > LEDGER_EPS or abs(pnl-expected_pnl) > LEDGER_EPS:
            raise ValueError('CASH_PNL_EVENT_LEDGER_MISMATCH')
        if cash < 0 or abs(cash+basis-CAPITAL-pnl) > MICRO:
            raise ValueError('BROKEN_CASH_BASIS_PNL_IDENTITY')
        running = CAPITAL
        for at, priority, key, delta, needed in sorted(events):
            timestamp(at)
            if running+LEDGER_EPS < needed:
                raise ValueError('UNFUNDED_EVENT_HISTORY')
            running += delta
        for pos in self.state['positions'].values():
            a = pos.get('management') or {}
            if 'decision_cash' in a:
                decision_cash = CAPITAL+sum(e[3] for e in events if e[0] <= a['decision_at'])
                if abs(decision_cash-number(a['decision_cash'])) > LEDGER_EPS:
                    raise ValueError('DECISION_CASH_HISTORY_MISMATCH')

    def source(self, kind, market, observed, requested=None, book=None):
        timestamp(observed)
        if requested is not None:
            timestamp(requested)
            if requested > observed:
                raise ValueError('INVALID_REQUEST_TIME')
        source = {'kind':kind, 'market':copy.deepcopy(market), 'observed':observed,
                  'requested':requested, 'book':copy.deepcopy(book)}
        self.emit('inventory_observation', source=source, source_sha256=digest(source))
        return source

    def observe_entry_attempt(self, paper, market, book, observed, requested):
        timestamp(observed); timestamp(requested)
        condition = market.get('conditionId')
        ep = paper.state['episodes'].get(condition) or {}
        a = ep.get('variants', {}).get('model') or {}
        if (condition in self.state['entry_attempts'] or a.get('status') != 'PENDING'
                or ep.get('decision_at', -1) < self.state['started_at']
                or requested < a['eligible_after']):
            return None
        source = self.source('BOOK', market, observed, requested, book)
        try:
            identity = market_identity(market)
        except (ValueError, KeyError, TypeError, ArithmeticError):
            identity = None
        self.state['entry_attempts'][condition] = {
            'condition':condition, 'slug':ep['slug'], 'observed':observed, 'requested':requested,
            'decision_at':ep['decision_at'], 'side':a['side'], 'max_price':a['max_price'],
            'gross_quantity':a['size_cap_shares'], 'eligible_after':a['eligible_after'],
            'expires_at':a['expires_at'], 'identity':identity, 'source':source}
        if self.entry_quote(self.state['entry_attempts'][condition]) is None:
            self.state['admission_skips'][condition] = 'FIRST_ENTRY_ATTEMPT_FAILED'
        return source

    @staticmethod
    def entry_quote(attempt):
        try:
            for name in ('observed','requested','decision_at','eligible_after','expires_at'):
                timestamp(attempt[name])
            s, source = attempt['identity'], attempt['source']
            if (s is None or source['kind'] != 'BOOK' or source['observed'] != attempt['observed']
                    or s['condition'] != attempt['condition'] or s['slug'] != attempt['slug']
                    or source['requested'] != attempt['requested'] or market_identity(source['market']) != s
                    or source['market'].get('status') != 'FUNDED' or not isinstance(source['book'], dict)
                    or source['book'].get('tokenId') != s['yes_token']
                    or not attempt['decision_at'] < attempt['eligible_after'] <= attempt['requested'] <= attempt['observed'] <= attempt['expires_at']
                    or attempt['observed'] >= s['end']):
                return None
            q = quote(source['book'], attempt['side'], attempt['gross_quantity'], True)
            if q is None or number(q['price_bound']) > number(attempt['max_price']) or number(q['gross_cash']) > ENTRY_LIMIT:
                return None
            return q
        except (ValueError, KeyError, TypeError, ArithmeticError):
            return None

    def admit(self, ep, market, observed):
        condition = ep['condition']
        if condition in self.state['positions'] or condition in self.state['admission_skips']:
            return False
        a = ep.get('variants', {}).get('model', {})
        if (a.get('status') != 'FILLED' or ep.get('decision_at', -1) < self.state['started_at']
                or a.get('fill_at', -1) < self.state['started_at']):
            return False  # carried legacy fills never become new funded entries
        reason = None
        timestamp(observed); timestamp(ep['decision_at']); timestamp(a['fill_at'])
        if not ep['decision_at'] <= a['fill_at'] <= observed:
            self.state['admission_skips'][condition] = 'INVALID_ENTRY_TIMES'
            return False
        s = spec(market)
        token = market.get('collateralToken') or {}
        tokens = market.get('tokens') or {}
        if (s is None or s['condition'] != condition or ep['slug'] != s['slug'] or market.get('status') != 'FUNDED'
                or market.get('marketType') != 'single' or market.get('groupId')
                or str(token.get('address')).lower() != '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
                or not tokens.get('no') or tokens.get('yes') == tokens.get('no')
                or a.get('side') not in ('YES','NO') or observed >= s['end']):
            reason = 'UNVERIFIED_MARKET'
        try:
            cost, qty = number(a['cost_usdc']), number(a['net_shares'])
        except (ValueError, KeyError, ArithmeticError):
            self.state['admission_skips'][condition] = 'INVALID_ENTRY_AMOUNT'
            return False
        if cost <= 0 or cost > ENTRY_LIMIT or qty <= 0:
            reason = 'INVALID_OR_OVERSIZED_ENTRY'
        if cost > number(self.state['cash']):
            reason = 'INSUFFICIENT_CAPITAL'
        attempt = self.state['entry_attempts'].get(condition)
        q = self.entry_quote(attempt) if attempt else None
        if (q is None or a['fill_at'] != attempt['observed'] or observed != attempt['observed']
                or number(q['gross_cash']) != cost or number(q['net_quantity']) != qty
                or a['side'] != attempt['side'] or ep['decision_at'] != attempt['decision_at']):
            reason = reason or 'UNVERIFIED_FIRST_ENTRY_ATTEMPT'
        if reason:
            self.state['admission_skips'][condition] = reason
            return False
        side = a['side']
        self.state['cash'] = str(number(self.state['cash'])-cost)
        self.state['positions'][condition] = {
            'slug': ep['slug'], 'condition': condition, 'seed_at': observed, 'hour_start': s['start'],
            'phase': 'holdout' if ep['decision_at'] >= HOLDOUT else 'discovery',
            'quantity': {'YES': str(qty if side == 'YES' else D(0)), 'NO': str(qty if side == 'NO' else D(0))},
            'basis': {'YES': str(cost if side == 'YES' else D(0)), 'NO': str(cost if side == 'NO' else D(0))},
            'spent_total': str(cost), 'entry_cost': str(cost), 'entry_side': side,
            'entry_net_shares': str(qty), 'entry_decision_at':ep['decision_at'],
            'identity':market_identity(market), 'management': None,
            'origin': 'FROZEN_HOURLY_MODEL_ASSUMED_DEPTH_FILL'}
        self.validate()
        self.emit('inventory_entry', condition=condition, position=self.state['positions'][condition])
        return True

    def alternatives(self, pos, book, p, cash=None):
        yes, no = (number(pos['quantity'][s]) for s in ('YES','NO'))
        hold = value(yes, no, p)
        options = [{'action':'HOLD', 'conservative_value':str(hold), 'incremental_value':'0'}]
        side = 'YES' if yes > no else 'NO'
        other = 'NO' if side == 'YES' else 'YES'
        surplus = abs(yes-no)
        if not surplus:
            return options
        sell = quote(book, side, surplus, False)
        if sell:
            total = number(sell['net_cash'])+min(yes,no)
            options.append({'action':'SELL', 'side':side, 'quantity':str(surplus), **sell,
                            'conservative_value':str(total), 'incremental_value':str(total-hold)})
        gross = (surplus/(1-BUY_FEE)).quantize(MICRO, rounding=ROUND_UP)
        buy = quote(book, other, gross, True)
        if buy:
            cost, net = number(buy['gross_cash']), number(buy['net_quantity'])
            acquired = number(pos['quantity'][other])+net
            y, n = (yes,acquired) if side == 'YES' else (acquired,no)
            paired = min(y,n)
            # Existing cost is used only for a separate locked-profit constraint.
            existing_basis = number(pos['basis'][side]) * surplus / number(pos['quantity'][side])
            locked_profit = surplus-existing_basis-cost-MERGE_COST
            allowed = (cost+MERGE_COST <= number(self.state['cash'] if cash is None else cash)
                       and number(pos['spent_total'])+cost <= CONDITION_LIMIT
                       and locked_profit >= (existing_basis+cost)*PAIR_HURDLE)
            total = value(y,n,p)-cost-MERGE_COST
            options.append({'action':'COMPLETE_PAIR', 'side':other, **buy,
                            'quantity':str(gross), 'locked_profit':str(locked_profit),
                            'risk_allowed':allowed, 'conservative_value':str(total),
                            'incremental_value':str(total-hold), 'paired_quantity':str(paired)})
        return options

    @staticmethod
    def trade_result(pos, q, buy):
        quantity = {s:number(pos['quantity'][s]) for s in ('YES','NO')}
        basis = {s:number(pos['basis'][s]) for s in ('YES','NO')}
        side = pos['management']['side']
        spent = number(pos['spent_total'])
        if buy:
            cost, net = number(q['gross_cash']), number(q['net_quantity'])
            quantity[side] += net; basis[side] += cost; spent += cost
            paired, consumed = min(quantity.values()), D(0)
            for s in ('YES','NO'):
                removed = basis[s]*paired/quantity[s]
                basis[s] -= removed; quantity[s] -= paired; consumed += removed
            proceeds = paired-MERGE_COST
            pnl = proceeds-consumed
            record = {'paper_merge':{'quantity':str(paired), 'net_proceeds':str(proceeds),
                      'pnl_usdc':str(pnl), 'assumed_cost':str(MERGE_COST)}}
            delta = proceeds-cost
        else:
            qty, proceeds = number(q['gross_quantity']), number(q['net_cash'])
            if qty > quantity[side]:
                raise ValueError('OVERSIZED_SALE')
            removed = basis[side]*qty/quantity[side]
            quantity[side] -= qty; basis[side] -= removed
            pnl, delta = proceeds-removed, proceeds
            record = {'paper_sale':{'net_proceeds':str(proceeds), 'pnl_usdc':str(pnl)}}
        return {'quantity':quantity, 'basis':basis, 'spent_total':spent,
                'cash_delta':delta, 'pnl':pnl, 'record':record}

    @staticmethod
    def execution_economics(pos, q):
        a = pos['management']
        y, n = (number(pos['quantity'][s]) for s in ('YES','NO'))
        surplus = abs(y-n)
        side = 'YES' if y > n else 'NO'
        hold = value(y, n, a['p_up'])
        if a['action'] == 'COMPLETE_PAIR':
            expected = (surplus/(1-BUY_FEE)).quantize(MICRO, rounding=ROUND_UP)
            if a['side'] == side or number(q['gross_quantity']) != expected:
                raise ValueError('INVALID_PAIR_QUANTITY_OR_SIDE')
            cost, net = number(q['gross_cash']), number(q['net_quantity'])
            existing = number(pos['basis'][side])*surplus/number(pos['quantity'][side])
            locked = surplus-existing-cost-MERGE_COST
            if locked <= 0 or locked < (existing+cost)*PAIR_HURDLE:
                raise ValueError('EXECUTION_PAIR_PROFIT_HURDLE')
            y, n = (y,n+net) if side == 'YES' else (y+net,n)
            total = value(y,n,a['p_up'])-cost-MERGE_COST
        elif a['action'] == 'SELL':
            if a['side'] != side or number(q['gross_quantity']) != surplus:
                raise ValueError('INVALID_SELL_QUANTITY_OR_SIDE')
            total = number(q['net_cash'])+min(y,n)
            locked = None
        else:
            raise ValueError('INVALID_EXECUTION_ACTION')
        if total-hold < D('.02'):
            raise ValueError('EXECUTION_INCREMENTAL_VALUE')
        return {'conservative_value':str(total), 'incremental_value':str(total-hold),
                'locked_profit':str(locked) if locked is not None else None}

    def rebuild(self, pos):
        """Derive every balance from verified seed, execution and payout records."""
        cost, qty = number(pos['entry_cost']), number(pos['entry_net_shares'])
        if not 0 < cost <= ENTRY_LIMIT or qty <= 0:
            raise ValueError('INVALID_ENTRY_AMOUNT')
        seed = {**pos, 'quantity':{s:str(qty if s==pos['entry_side'] else D(0)) for s in ('YES','NO')},
                'basis':{s:str(cost if s==pos['entry_side'] else D(0)) for s in ('YES','NO')},
                'spent_total':str(cost)}
        result = {'quantity':dict(map(lambda kv:(kv[0],number(kv[1])),seed['quantity'].items())),
                  'basis':dict(map(lambda kv:(kv[0],number(kv[1])),seed['basis'].items())),
                  'cash_delta':-cost, 'pnl':D(0), 'spent_total':cost,
                  'events':[(pos['seed_at'],0,pos['condition'],-cost,cost)]}
        a = pos.get('management')
        if a is not None:
            timestamp(a['decision_at'])
            if not pos['seed_at'] < a['decision_at'] or 'action' in a and a['decision_at'] >= pos['identity']['end']:
                raise ValueError('INVALID_MANAGEMENT_TIME')
            if a['status'] not in ('HOLD','PENDING','SKIP','PAPER_EXECUTED'):
                raise ValueError('INVALID_MANAGEMENT_STATUS')
            if 'action' in a:
                src = a['source']
                if (src['observed'] != a['decision_at'] or src['requested'] <= pos['seed_at']
                        or market_identity(src['market']) != pos['identity']
                        or src['book'].get('tokenId') != pos['identity']['yes_token']):
                    raise ValueError('INVALID_DECISION_SOURCE')
                timestamp(src['requested']); timestamp(a['reference_observed_at'])
                if not 0 <= a['decision_at']-a['reference_observed_at'] <= 10 or src['requested'] > src['observed']:
                    raise ValueError('INVALID_DECISION_REFERENCE_TIME')
                options = self.alternatives(seed, src['book'], a['p_up'], a['decision_cash'])
                best = max((o for o in options if o.get('risk_allowed',True)), key=lambda o:number(o['incremental_value']))
                if number(best['incremental_value']) < D('.02'):
                    best = options[0]
                if any(a.get(k)!=v for k,v in best.items()) or a['alternatives']!=options:
                    raise ValueError('DECISION_REBUILD_MISMATCH')
                if (a['eligible_after'] != a['decision_at']+pos['identity']['delay_s']
                        or a['expires_at'] != a['decision_at']+30 or a['end'] != pos['identity']['end']
                        or a['yes_token'] != pos['identity']['yes_token']):
                    raise ValueError('DECISION_TIMING_OR_TOKEN_CHANGED')
            if a['status']=='PAPER_EXECUTED':
                src = a['execution_source']
                timestamp(a['executed_at']); timestamp(src['requested'])
                if (src['observed']!=a['executed_at'] or not a['eligible_after']<=src['requested']<=a['executed_at']<=a['expires_at']
                        or a['executed_at']>=a['end'] or market_identity(src['market']) != pos['identity']
                        or src['book'].get('tokenId')!=a['yes_token']):
                    raise ValueError('INVALID_EXECUTION_SOURCE')
                buy = a['action']=='COMPLETE_PAIR'
                q = quote(src['book'], a['side'], a['quantity'], buy)
                if q is None or q!=a['execution']:
                    raise ValueError('EXECUTION_REBUILD_MISMATCH')
                bound, actual = number(a['price_bound']),number(q['price_bound'])
                if (buy and actual>bound) or (not buy and actual<bound):
                    raise ValueError('PRICE_BOUND_FAILED')
                if self.execution_economics(seed,q)!=a['execution_economics']:
                    raise ValueError('EXECUTION_ECONOMICS_CHANGED')
                trade = self.trade_result(seed,q,buy)
                if trade['spent_total']>CONDITION_LIMIT or any(pos.get(k)!=v for k,v in trade['record'].items()):
                    raise ValueError('TRADE_LEDGER_MISMATCH')
                result.update(quantity=trade['quantity'], basis=trade['basis'], spent_total=trade['spent_total'],
                              cash_delta=result['cash_delta']+trade['cash_delta'], pnl=trade['pnl'])
                if buy:
                    execution_cost = number(q['gross_cash'])
                    result['events'].append((a['executed_at'],1,pos['condition'],-execution_cost,execution_cost+MERGE_COST))
                    result['events'].append((a['executed_at'],2,pos['condition'],number(pos['paper_merge']['net_proceeds']),D(0)))
                else:
                    result['events'].append((a['executed_at'],2,pos['condition'],number(q['net_cash']),D(0)))
            elif any(k in pos for k in ('paper_sale','paper_merge')):
                raise ValueError('UNEXECUTED_TRADE_RECORD')
        elif any(k in pos for k in ('paper_sale','paper_merge')):
            raise ValueError('UNEXECUTED_TRADE_RECORD')
        if pos.get('settled_at') is not None:
            at = timestamp(pos['settled_at']); src = pos['settlement_source']
            if (at < pos['identity']['end'] or src['observed'] != at or market_identity(src['market']) != pos['identity']
                    or src['market'].get('status')!='RESOLVED' or a and a.get('executed_at',0)>at):
                raise ValueError('INVALID_SETTLEMENT_SOURCE')
            payout = payouts(src['market'])
            if payout is None or list(map(str,payout)) != pos['payout']:
                raise ValueError('SETTLEMENT_PAYOUT_CHANGED')
            proceeds = sum(result['quantity'][s]*payout[i] for i,s in enumerate(('YES','NO')))
            profit = proceeds-sum(result['basis'].values())
            baseline = qty*payout[0 if pos['entry_side']=='YES' else 1]-cost
            if profit!=number(pos['settlement_pnl']) or baseline!=number(pos['seed_hold_pnl']):
                raise ValueError('SETTLEMENT_LEDGER_MISMATCH')
            result['cash_delta'] += proceeds; result['pnl'] += profit
            result['events'].append((at,3,pos['condition'],proceeds,D(0)))
            result.update(quantity={'YES':D(0),'NO':D(0)},basis={'YES':D(0),'NO':D(0)})
        return result

    def book(self, paper, market, book, observed, requested, source=None):
        timestamp(observed); timestamp(requested)
        s = spec(market)
        if s is None:
            return
        condition = s['condition']
        ep = paper.state['episodes'].get(condition)
        if ep is None:
            return
        if self.admit(ep, market, observed):
            return  # first management decision cannot share the entry snapshot
        pos = self.state['positions'].get(condition)
        if pos is None or pos.get('settled_at') or observed <= pos['seed_at']:
            return
        action = pos['management']
        if action is not None:
            if action['status'] != 'PENDING':
                return
            if requested < action['eligible_after'] and observed <= action['expires_at']:
                return
            if observed > action['expires_at']:
                action.update(status='SKIP', reason='EXECUTION_TOO_LATE')
                return
            source = self.source('BOOK',market,observed,requested,book)
            self.execute(pos, book, observed, requested, source)
            return
        try:
            source = self.source('BOOK',market,observed,requested,book)
            if (requested > observed or requested <= pos['seed_at'] or observed >= s['end']
                    or book.get('tokenId') != s['yes_token'] or market.get('status') != 'FUNDED'
                    or market_identity(market) != pos['identity']):
                raise ValueError('INVALID_DECISION_BOOK_OR_TIME')
            p, _, _, ref_at = paper._inputs(s, observed)
            options = self.alternatives(pos, book, p)
            permitted = [a for a in options if a.get('risk_allowed', True)]
            best = max(permitted, key=lambda a:number(a['incremental_value']))
            # Tiny improvements do not justify an additional action.
            if number(best['incremental_value']) < D('.02'):
                best = options[0]
            pos['management'] = {**best, 'status':'HOLD' if best['action']=='HOLD' else 'PENDING',
                                 'decision_at':observed, 'p_up':str(p), 'reference_observed_at':ref_at,
                                 'source':source, 'decision_cash':self.state['cash'],
                                 'alternatives':options, 'eligible_after':observed+s['delay_s'],
                                 'expires_at':observed+30, 'yes_token':s['yes_token'], 'end':s['end']}
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            pos['management'] = {'status':'SKIP', 'reason':str(exc), 'decision_at':observed}
        self.emit('inventory_decision', condition=condition, management=pos['management'])

    def execute(self, pos, book, observed, requested, source=None):
        backup = copy.deepcopy(self.state)
        condition = pos['condition']
        a = pos['management']
        try:
            timestamp(observed); timestamp(requested)
            if (source is None or market_identity(source['market']) != pos['identity']
                    or source['market'].get('status') != 'FUNDED'):
                raise ValueError('INVALID_EXECUTION_MARKET')
            if (requested < a['eligible_after'] or requested > observed or observed > a['expires_at']
                    or observed >= a['end'] or book.get('tokenId') != a['yes_token']):
                raise ValueError('INVALID_EXECUTION_BOOK_OR_TIME')
            buy = a['action']=='COMPLETE_PAIR'
            q = quote(book, a['side'], a['quantity'], buy)
            if q is None:
                raise ValueError('INSUFFICIENT_DEPTH')
            bound = number(a['price_bound'])
            if (buy and number(q['price_bound']) > bound or not buy and number(q['price_bound']) < bound):
                raise ValueError('PRICE_BOUND_FAILED')
            side = a['side']
            economics = self.execution_economics(pos,q)
            if buy:
                cost = number(q['gross_cash']); net = number(q['net_quantity'])
                if (cost+MERGE_COST > number(self.state['cash'])
                        or number(pos['spent_total'])+cost > CONDITION_LIMIT):
                    raise ValueError('CAPITAL_OR_CONDITION_LIMIT')
                self.state['cash'] = str(number(self.state['cash'])-cost)
                pos['quantity'][side] = str(number(pos['quantity'][side])+net)
                pos['basis'][side] = str(number(pos['basis'][side])+cost)
                pos['spent_total'] = str(number(pos['spent_total'])+cost)
                paired = min(number(pos['quantity']['YES']),number(pos['quantity']['NO']))
                consumed = D(0)
                for s in ('YES','NO'):
                    held = number(pos['quantity'][s]); basis = number(pos['basis'][s])
                    removed = basis*paired/held
                    pos['quantity'][s] = str(held-paired); pos['basis'][s] = str(basis-removed)
                    consumed += removed
                proceeds = paired-MERGE_COST
                self.state['cash'] = str(number(self.state['cash'])+proceeds)
                self.state['realized_pnl'] = str(number(self.state['realized_pnl'])+proceeds-consumed)
                pos['paper_merge'] = {'quantity':str(paired), 'net_proceeds':str(proceeds),
                                      'pnl_usdc':str(proceeds-consumed), 'assumed_cost':str(MERGE_COST)}
            else:
                qty = number(q['gross_quantity']); held = number(pos['quantity'][side])
                removed = number(pos['basis'][side])*qty/held
                proceeds = number(q['net_cash'])
                pos['quantity'][side] = str(held-qty)
                pos['basis'][side] = str(number(pos['basis'][side])-removed)
                self.state['cash'] = str(number(self.state['cash'])+proceeds)
                self.state['realized_pnl'] = str(number(self.state['realized_pnl'])+proceeds-removed)
                pos['paper_sale'] = {'net_proceeds':str(proceeds), 'pnl_usdc':str(proceeds-removed)}
            a.update(status='PAPER_EXECUTED', executed_at=observed, execution=q,
                     execution_economics=economics, execution_source=source)
            self.validate()
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            self.state = backup
            pos = self.state['positions'][condition]
            a = pos['management']
            a.update(status='SKIP', reason=str(exc))
        self.emit('inventory_execution', condition=pos['condition'], management=a)

    def unavailable_book(self, slug, observed, requested):
        timestamp(observed); timestamp(requested)
        for pos in self.state['positions'].values():
            if pos['slug'] != slug or pos.get('settled_at') or observed <= pos['seed_at']:
                continue
            a = pos['management']
            if a is None:
                pos['management'] = {'status':'SKIP','reason':'FIRST_MANAGEMENT_BOOK_UNAVAILABLE','decision_at':observed}
            elif a['status']=='PENDING' and (requested >= a['eligible_after'] or observed > a['expires_at']):
                a.update(status='SKIP',reason='FIRST_EXECUTION_BOOK_UNAVAILABLE')

    def market(self, market, observed):
        try:
            timestamp(observed)
            s = spec(market)
            if s is None or market.get('status') != 'RESOLVED' or observed < s['end']:
                return False
            identity = market_identity(market)
        except (ValueError, KeyError, TypeError, ArithmeticError):
            return False
        pos = self.state['positions'].get(s['condition'])
        if pos is None or identity != pos['identity']:
            return False
        if pos.get('settled_at') is not None:
            return True
        payout = payouts(market)
        if payout is None:
            return False
        source = self.source('MARKET', market, observed)
        proceeds = sum(number(pos['quantity'][s])*payout[i] for i,s in enumerate(('YES','NO')))
        basis = sum(number(x) for x in pos['basis'].values())
        self.state['cash'] = str(number(self.state['cash'])+proceeds)
        self.state['realized_pnl'] = str(number(self.state['realized_pnl'])+proceeds-basis)
        baseline = number(pos['entry_net_shares'])*payout[0 if pos['entry_side']=='YES' else 1]-number(pos['entry_cost'])
        pos.update(settled_at=observed, payout=list(map(str,payout)), seed_hold_pnl=str(baseline), settlement_source=source,
                   settlement_pnl=str(proceeds-basis), quantity={'YES':'0','NO':'0'}, basis={'YES':'0','NO':'0'})
        if pos['management'] and pos['management']['status']=='PENDING':
            pos['management'].update(status='SKIP',reason='RESOLVED_BEFORE_EXECUTION')
        self.validate()
        self.emit('inventory_settlement',condition=s['condition'],position=pos)
        return True

    def report(self):
        self.validate()
        positions = list(self.state['positions'].values())
        return {'version':VERSION, 'status':'INDEPENDENT_PAPER_ASSUMPTIONS_NOT_LIVE',
                'started_at':self.state['started_at'], 'initial_capital':str(CAPITAL),
                'cash':self.state['cash'], 'open_cost_basis':str(sum(number(v) for p in positions for v in p['basis'].values())),
                'realized_pnl':self.state['realized_pnl'], 'admission_skips':dict(Counter(self.state['admission_skips'].values())),
                'positions':len(positions), 'management_states':dict(Counter((p['management'] or {}).get('status','AWAITING_NEXT_BOOK') for p in positions)),
                'settled_positions':sum(bool(p.get('settled_at')) for p in positions),
                'seed_hold_settled_pnl':str(sum(number(p['seed_hold_pnl']) for p in positions if p.get('settled_at'))),
                'managed_settled_pnl':str(sum(number(p.get('paper_merge',{}).get('pnl_usdc','0'))
                    +number(p.get('paper_sale',{}).get('pnl_usdc','0'))+number(p['settlement_pnl'])
                    for p in positions if p.get('settled_at'))),
                'no_trade_control_pnl':'0',
                'phases':{phase:self.phase_report([p for p in positions if p['phase']==phase])
                    for phase in ('discovery','holdout')},
                'limitations':['Entries require independently observed first eligible hourly entry attempt; no old fill backfill.',
                  '100 USDC funded paper ledger; entry10, condition20, no borrowing; management only once per condition.',
                  'Buy fee3%, sell fee1.5%, hypothetical merge cost0.01 USDC; no rebates/rewards.',
                  'Probability +/-0.03 is an engineering stress scenario, not calibrated uncertainty.',
                  'First post-delay REST depth assumes executable liquidity; no matching/cache/queue guarantees.',
                  'Paper merge is assumed successful; no on-chain transaction or signing is performed.',
                  'Realized interim PnL excludes open risk; seed-hold settled comparison is paired by admitted condition.',
                  'No passive maker fills or profitable-strategy verdict.']}

    @staticmethod
    def phase_report(positions):
        settled = [p for p in positions if p.get('settled_at') is not None]
        def realized(p):
            return (number(p.get('paper_merge',{}).get('pnl_usdc','0'))
                    +number(p.get('paper_sale',{}).get('pnl_usdc','0'))+number(p.get('settlement_pnl','0')))
        managed = sum(realized(p) for p in settled)
        seed = sum(number(p['seed_hold_pnl']) for p in settled)
        clusters = []
        for hour in sorted({p['hour_start'] for p in settled}):
            group = [p for p in settled if p['hour_start']==hour]
            m, h = sum(realized(p) for p in group), sum(number(p['seed_hold_pnl']) for p in group)
            clusters.append({'hour_start':hour,'conditions':len(group),'managed_settled_pnl':str(m),
                             'seed_hold_settled_pnl':str(h),'managed_minus_seed_hold':str(m-h)})
        return {'positions':len(positions),'settled_positions':len(settled),'matched_conditions':len(settled),
                'resolved_hour_clusters':len(clusters),'managed_settled_pnl':str(managed),
                'seed_hold_settled_pnl':str(seed),'managed_minus_seed_hold':str(managed-seed),
                'settled_entry_cost':str(sum(number(p['entry_cost']) for p in settled)),
                'realized_pnl':str(sum(realized(p) for p in positions)),
                'open_positions':sum(p.get('settled_at') is None for p in positions),
                'open_cost_basis':str(sum(number(v) for p in positions for v in p['basis'].values())),
                'management_states':dict(Counter((p['management'] or {}).get('status','AWAITING_NEXT_BOOK') for p in positions)),
                'hour_clusters':clusters,'no_trade_control_pnl':'0',
                'feasibility':'REQUIRES_COVERAGE_REVIEW' if len(settled)>=60 and len(clusters)>=60 else 'INSUFFICIENT_DATA'}


def archive_report(paths, as_of=None):
    """Audit v2 ledger, immutable decisions and raw evidence; v1 is never pooled."""
    import gzip
    import zipfile
    from limitless_hourly_paper import seconds
    checkpoints, errors, sources, legacy = [], [], set(), 0
    limit = timestamp(as_of) if as_of is not None else None
    for path in paths:
        try:
            with zipfile.ZipFile(path) as z:
                state = json.loads(z.read('state.json')).get('inventory_paper')
                if state is None:
                    continue
                if state.get('version') == LEGACY_VERSION:
                    legacy += 1
                    continue
                raw_at = json.loads(z.read('summary.json'))['ended_at']
                if isinstance(raw_at,str) and dt.datetime.fromisoformat(raw_at.replace('Z','+00:00')).tzinfo is None:
                    raise ValueError('NAIVE_CHECKPOINT_TIME')
                at = timestamp(seconds(raw_at))
                if limit is not None and at > limit:
                    continue
                InventoryPaper(state).validate()
                checkpoints.append((at,str(path),state))
                if 'inventory_evidence.jsonl.gz' in z.namelist():
                    with gzip.GzipFile(fileobj=z.open('inventory_evidence.jsonl.gz')) as stream:
                        for line in stream:
                            row = json.loads(line)
                            if row.get('kind')!='inventory_observation':
                                raise ValueError('INVALID_EVIDENCE_RECORD')
                            source = row['source']
                            timestamp(source['observed'])
                            if source['requested'] is not None:
                                timestamp(source['requested'])
                            key = digest(source)
                            if key != row['source_sha256'] or source['observed'] > at:
                                raise ValueError('INVALID_OR_FUTURE_RAW_EVIDENCE')
                            sources.add(key)
        except (ValueError,KeyError,TypeError,ArithmeticError,OSError,zipfile.BadZipFile) as exc:
            errors.append({'artifact':str(path),'error':str(exc)})
    checkpoints.sort(key=lambda x:(x[0],x[1]))
    previous, previous_at = None, None
    for at,path,state in checkpoints:
        for attempt in state['entry_attempts'].values():
            if attempt['observed'] > at or digest(attempt['source']) not in sources:
                errors.append({'artifact':path,'error':'ENTRY_RAW_EVIDENCE_MISSING_OR_FUTURE'})
        for pos in state['positions'].values():
            a = pos.get('management') or {}
            for source in (a.get('source'),a.get('execution_source'),pos.get('settlement_source')):
                if source is not None and (source['observed'] > at or digest(source) not in sources):
                    errors.append({'artifact':path,'condition':pos['condition'],'error':'RAW_EVIDENCE_MISSING_OR_FUTURE'})
        if previous is not None:
            if state['started_at'] != previous['started_at']:
                errors.append({'artifact':path,'error':'CHECKPOINT_LINEAGE_CHANGED'})
            if at==previous_at and state!=previous:
                errors.append({'artifact':path,'error':'SAME_TIME_CHECKPOINT_CHANGED'})
            for field in ('entry_attempts','admission_skips'):
                if any(state[field].get(k)!=v for k,v in previous[field].items()):
                    errors.append({'artifact':path,'error':field.upper()+'_HISTORY_CHANGED'})
            if not set(previous['positions']) <= set(state['positions']):
                errors.append({'artifact':path,'error':'CHECKPOINT_POSITIONS_LOST'})
            for key in set(previous['positions']) & set(state['positions']):
                old,new = previous['positions'][key],state['positions'][key]
                immutable = ('seed_at','entry_cost','entry_net_shares','entry_side','entry_decision_at',
                             'condition','slug','phase','hour_start','identity','origin')
                if any(old.get(k)!=new.get(k) for k in immutable) or old.get('settled_at') is not None and old!=new:
                    errors.append({'artifact':path,'condition':key,'error':'IMMUTABLE_POSITION_CHANGED'})
                a,b = old.get('management'),new.get('management')
                if a is not None:
                    allowed = {'status','reason','executed_at','execution','execution_source','execution_economics'}
                    if a['status']!='PENDING' and a!=b:
                        errors.append({'artifact':path,'condition':key,'error':'TERMINAL_ACTION_CHANGED'})
                    elif a['status']=='PENDING' and (b is None or b['status'] not in ('PENDING','SKIP','PAPER_EXECUTED')
                            or {k:v for k,v in a.items() if k not in allowed}!={k:v for k,v in b.items() if k not in allowed}
                            or b['status']=='PENDING' and a!=b):
                        errors.append({'artifact':path,'condition':key,'error':'PENDING_DECISION_CHANGED'})
        previous, previous_at = state, at
    status = 'UNRECONCILED_CHECKPOINTS' if errors else 'RECONCILED_PAPER_ONLY' if checkpoints else 'NO_V2_CHECKPOINTS'
    return {'version':VERSION,'status':status,'checkpoints':len(checkpoints),'errors':errors,
            'legacy_v1_checkpoints_excluded':legacy,'legacy_status':'UNVERIFIED_V1_NO_EDGE',
            'raw_sources':len(sources),'latest_artifact':checkpoints[-1][1] if checkpoints else None,
            'report':InventoryPaper(checkpoints[-1][2]).report() if checkpoints and not errors else None}


if __name__ == '__main__':
    import argparse
    import json
    import pathlib
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives',nargs='+',type=pathlib.Path)
    parser.add_argument('--out',default='limitless_inventory_final_report.json')
    parser.add_argument('--as-of', help='Aware ISO timestamp; future checkpoints are excluded')
    args=parser.parse_args()
    from limitless_hourly_paper import seconds
    if args.as_of and dt.datetime.fromisoformat(args.as_of.replace('Z','+00:00')).tzinfo is None:
        parser.error('--as-of requires timezone')
    pathlib.Path(args.out).write_text(json.dumps(archive_report(args.archives,seconds(args.as_of) if args.as_of else None),indent=2)+'\n')
