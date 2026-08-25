# Risk Policy v0

## Principle

Follower risk belongs to the follower portfolio. Never derive position size by simply scaling a whale's notional.

## Required controls before live trading

- max risk per independent signal
- max exposure per wallet
- max exposure per market
- max exposure per event
- max correlated-cluster exposure
- daily loss limit
- max stale-signal age
- max tolerated price deterioration
- minimum liquidity / visible-depth rule
- hard kill switch

Exact numeric limits are intentionally not frozen at project creation; they must be justified by paper/shadow evidence and then versioned.

## Correlation

Multiple prediction positions can represent the same underlying risk. Examples include BTC/ETH/SOL short-horizon directional markets or several markets tied to one event.

Risk must aggregate related positions into a correlation/event cluster rather than counting them as independent bets.

## Source diversification

Exposure to several wallets is not diversified if those wallets exhibit lead/lag copying or share the same underlying information source. Stage 9 dependency analysis must discount correlated sources.

## Size constraints

Follower size must be the minimum of:

- portfolio risk allowance
- per-market allowance
- per-wallet allowance
- correlated-cluster allowance
- visible executable liquidity
- copyability decision size cap

Do not extrapolate beyond visible liquidity in backtests or paper simulation.

## Execution risk

A valid signal can become invalid before fill. Orders must obey:

- max acceptable price
- TTL/staleness condition
- partial-fill policy
- cancellation when residual edge falls below required margin

## Fail closed

Missing data, unresolved fee rules, ambiguous source intent, stale activity, or breached exposure limits -> `SKIP` / cancel, never optimistic execution.

## Live progression

No capital before historical research, live paper and shadow execution pass.

When live is eventually authorized:

1. one validated market family
2. 2–3 validated wallet x strategy classes
3. tiny capital
4. hard risk caps
5. complete event logging
6. immediate rollback/kill-switch path

Scale only after measured live performance, not because source wallets scale.
