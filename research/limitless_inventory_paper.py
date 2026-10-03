"""Independent, funded inventory-management paper variant. No network or orders."""
import copy
import datetime as dt
from decimal import Decimal, ROUND_UP
from collections import Counter
from limitless_hourly_paper import levels, spec

D = Decimal
VERSION = 'limitless-inventory-paper-v1'
CAPITAL = D('100')
ENTRY_LIMIT = D('10')
CONDITION_LIMIT = D('20')
BUY_FEE = D('.03')
SELL_FEE = D('.015')
MERGE_COST = D('.01')  # explicit hypothetical reserve, not a measured on-chain fee
PROBABILITY_STRESS = D('.03')  # scenario width, NOT a confidence interval
PAIR_HURDLE = D('.02')
MICRO = D('.000001')
HOLDOUT = dt.datetime(2026, 10, 6, tzinfo=dt.timezone.utc).timestamp()


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
            'positions': {}, 'admission_skips': {}, 'realized_pnl': '0'}
        if self.state.get('version') != VERSION:
            raise ValueError('INCOMPATIBLE_INVENTORY_STATE')
        self.emit = emit or (lambda *a, **k: None)
        self.validate()

    def validate(self):
        number(self.state['started_at'])
        cash = number(self.state['cash'])
        pnl = number(self.state['realized_pnl'])
        basis = D(0)
        for pos in self.state['positions'].values():
            for side in ('YES','NO'):
                q, cost = number(pos['quantity'][side]), number(pos['basis'][side])
                if q < 0 or cost < 0 or (q == 0 and cost != 0):
                    raise ValueError('INVALID_INVENTORY')
                basis += cost
        if cash < 0 or abs(cash+basis-CAPITAL-pnl) > MICRO:
            raise ValueError('BROKEN_CASH_BASIS_PNL_IDENTITY')

    def admit(self, ep, market, observed):
        condition = ep['condition']
        if condition in self.state['positions'] or condition in self.state['admission_skips']:
            return False
        a = ep.get('variants', {}).get('model', {})
        if (a.get('status') != 'FILLED' or ep.get('decision_at', -1) < self.state['started_at']
                or a.get('fill_at', -1) < self.state['started_at']):
            return False  # carried legacy fills never become new funded entries
        reason = None
        number(observed)
        if not ep['decision_at'] <= a['fill_at'] <= observed:
            self.state['admission_skips'][condition] = 'INVALID_ENTRY_TIMES'
            return False
        s = spec(market)
        token = market.get('collateralToken') or {}
        tokens = market.get('tokens') or {}
        if (s is None or s['condition'] != condition or market.get('status') != 'FUNDED'
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
            'entry_net_shares': str(qty), 'management': None,
            'origin': 'FROZEN_HOURLY_MODEL_ASSUMED_DEPTH_FILL'}
        self.validate()
        self.emit('inventory_entry', condition=condition, position=self.state['positions'][condition])
        return True

    def alternatives(self, pos, book, p):
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
            allowed = (cost+MERGE_COST <= number(self.state['cash'])
                       and number(pos['spent_total'])+cost <= CONDITION_LIMIT
                       and locked_profit >= (existing_basis+cost)*PAIR_HURDLE)
            total = value(y,n,p)-cost-MERGE_COST
            options.append({'action':'COMPLETE_PAIR', 'side':other, **buy,
                            'quantity':str(gross), 'locked_profit':str(locked_profit),
                            'risk_allowed':allowed, 'conservative_value':str(total),
                            'incremental_value':str(total-hold), 'paired_quantity':str(paired)})
        return options

    def book(self, paper, market, book, observed, requested):
        number(observed); number(requested)
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
            self.execute(pos, book, observed, requested)
            return
        try:
            if (requested > observed or requested <= pos['seed_at'] or observed >= s['end']
                    or book.get('tokenId') != s['yes_token'] or market.get('status') != 'FUNDED'):
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
                                 'alternatives':options, 'eligible_after':observed+s['delay_s'],
                                 'expires_at':observed+30, 'yes_token':s['yes_token'], 'end':s['end']}
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            pos['management'] = {'status':'SKIP', 'reason':str(exc), 'decision_at':observed}
        self.emit('inventory_decision', condition=condition, management=pos['management'])

    def execute(self, pos, book, observed, requested):
        backup = copy.deepcopy(self.state)
        condition = pos['condition']
        a = pos['management']
        try:
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
            a.update(status='PAPER_EXECUTED', executed_at=observed, execution=q)
            self.validate()
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            self.state = backup
            pos = self.state['positions'][condition]
            a = pos['management']
            a.update(status='SKIP', reason=str(exc))
        self.emit('inventory_execution', condition=pos['condition'], management=a)

    def unavailable_book(self, slug, observed, requested):
        for pos in self.state['positions'].values():
            if pos['slug'] != slug or pos.get('settled_at') or observed <= pos['seed_at']:
                continue
            a = pos['management']
            if a is None:
                pos['management'] = {'status':'SKIP','reason':'FIRST_MANAGEMENT_BOOK_UNAVAILABLE','decision_at':observed}
            elif a['status']=='PENDING' and (requested >= a['eligible_after'] or observed > a['expires_at']):
                a.update(status='SKIP',reason='FIRST_EXECUTION_BOOK_UNAVAILABLE')

    def market(self, market, observed):
        s = spec(market)
        if s is None or market.get('status') != 'RESOLVED' or observed < s['end']:
            return
        pos = self.state['positions'].get(s['condition'])
        if pos is None or pos.get('settled_at'):
            return
        winner = market.get('winningOutcomeIndex')
        numerators = market.get('payoutNumerators')
        if type(winner) is int and winner in (0,1):
            payouts = [D(1),D(0)] if winner==0 else [D(0),D(1)]
        elif isinstance(numerators,list) and len(numerators)==2:
            try:
                nums = [number(n) for n in numerators]
                if min(nums)<0 or sum(nums)<=0:
                    return
                payouts = [n/sum(nums) for n in nums]
            except (ValueError,ArithmeticError):
                return
        else:
            return
        proceeds = sum(number(pos['quantity'][s])*payouts[i] for i,s in enumerate(('YES','NO')))
        basis = sum(number(x) for x in pos['basis'].values())
        self.state['cash'] = str(number(self.state['cash'])+proceeds)
        self.state['realized_pnl'] = str(number(self.state['realized_pnl'])+proceeds-basis)
        baseline = number(pos['entry_net_shares'])*payouts[0 if pos['entry_side']=='YES' else 1]-number(pos['entry_cost'])
        pos.update(settled_at=observed, payout=list(map(str,payouts)), seed_hold_pnl=str(baseline),
                   settlement_pnl=str(proceeds-basis), quantity={'YES':'0','NO':'0'}, basis={'YES':'0','NO':'0'})
        if pos['management'] and pos['management']['status']=='PENDING':
            pos['management'].update(status='SKIP',reason='RESOLVED_BEFORE_EXECUTION')
        self.validate()
        self.emit('inventory_settlement',condition=s['condition'],position=pos)

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
                'phases':{phase:{'positions':sum(p['phase']==phase for p in positions),
                    'settled_positions':sum(p['phase']==phase and bool(p.get('settled_at')) for p in positions),
                    'resolved_hour_clusters':len({p['hour_start'] for p in positions if p['phase']==phase and p.get('settled_at')}),
                    'feasibility':'REQUIRES_COVERAGE_REVIEW' if sum(p['phase']==phase and bool(p.get('settled_at')) for p in positions)>=60
                        and len({p['hour_start'] for p in positions if p['phase']==phase and p.get('settled_at')})>=60 else 'INSUFFICIENT_DATA'}
                    for phase in ('discovery','holdout')},
                'limitations':['Entries reuse newly observed frozen hourly model paper fills; no old checkpoint backfill.',
                  '100 USDC funded paper ledger; entry10, condition20, no borrowing; management only once per condition.',
                  'Buy fee3%, sell fee1.5%, hypothetical merge cost0.01 USDC; no rebates/rewards.',
                  'Probability +/-0.03 is an engineering stress scenario, not calibrated uncertainty.',
                  'First post-delay REST depth assumes executable liquidity; no matching/cache/queue guarantees.',
                  'Paper merge is assumed successful; no on-chain transaction or signing is performed.',
                  'Realized interim PnL excludes open risk; seed-hold settled comparison is paired by admitted condition.',
                  'No passive maker fills or profitable-strategy verdict.']}


def archive_report(paths):
    """Latest cumulative checkpoint only; conflicting histories have no PnL verdict."""
    import json
    import zipfile
    from limitless_hourly_paper import seconds
    checkpoints, errors = [], []
    for path in paths:
        try:
            with zipfile.ZipFile(path) as z:
                state = json.loads(z.read('state.json')).get('inventory_paper')
                if state is None:
                    continue
                at = seconds(json.loads(z.read('summary.json'))['ended_at'])
                InventoryPaper(state).validate()
                checkpoints.append((at,str(path),state))
        except (ValueError, KeyError, ArithmeticError, OSError, zipfile.BadZipFile) as exc:
            errors.append({'artifact':str(path),'error':str(exc)})
    checkpoints.sort(key=lambda x:(x[0],x[1]))
    previous = None
    for at,path,state in checkpoints:
        if previous is not None:
            if state['started_at'] != previous['started_at']:
                errors.append({'artifact':path,'error':'CHECKPOINT_LINEAGE_CHANGED'})
            if not set(previous['positions']) <= set(state['positions']):
                errors.append({'artifact':path,'error':'CHECKPOINT_POSITIONS_LOST'})
            for key in set(previous['positions']) & set(state['positions']):
                old,new = previous['positions'][key],state['positions'][key]
                immutable = ('seed_at','entry_cost','entry_net_shares','entry_side','condition','slug','phase','hour_start')
                if any(old.get(k)!=new.get(k) for k in immutable) or old.get('settled_at') and old != new:
                    errors.append({'artifact':path,'condition':key,'error':'IMMUTABLE_POSITION_CHANGED'})
                a,b = old.get('management'),new.get('management')
                if a and a['status']!='PENDING' and a!=b:
                    errors.append({'artifact':path,'condition':key,'error':'TERMINAL_ACTION_CHANGED'})
        previous = state
    if not checkpoints:
        return {'version':VERSION,'status':'NO_INVENTORY_CHECKPOINTS','errors':errors,'report':None}
    return {'version':VERSION,'status':'UNRECONCILED_CHECKPOINTS' if errors else 'RECONCILED_PAPER_ONLY',
            'checkpoints':len(checkpoints),'latest_artifact':checkpoints[-1][1], 'errors':errors,
            'report':None if errors else InventoryPaper(checkpoints[-1][2]).report()}


if __name__ == '__main__':
    import argparse
    import json
    import pathlib
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archives',nargs='+',type=pathlib.Path)
    parser.add_argument('--out',default='limitless_inventory_final_report.json')
    args=parser.parse_args()
    pathlib.Path(args.out).write_text(json.dumps(archive_report(args.archives),indent=2)+'\n')
