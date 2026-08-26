# Bonereaper activity ↔ closed-position PnL reconciliation — frozen contract

Status: FROZEN BEFORE PROFIT-SOURCE INTERPRETATION

Inputs are already-frozen 2026-08-25 UTC evidence:

1. complete Bonereaper TRADE activity backfill (`70,474` rows; target BTC/ETH 5m/15m subset defined by the paired-inventory contract), and
2. bounded `/closed-positions` interval for the same UTC day.

## Join key and population

Join only by exact `condition_id`.

Primary reconciliation population is the intersection of:
- target-family activity markets; and
- target-family closed-position markets whose `closed_time` falls within the same frozen day.

Do not impute missing joins. Report activity-only and closed-only condition counts separately.

## Condition-level accounting quantities

For each joined condition:

- `closed_realized_pnl = sum(realized_pnl)` across its closed-position rows in the bounded settlement evidence;
- `matched_pair_edge = matched_size * (1 - paired_cost_per_unit)` from the frozen paired-inventory decomposition, only when the activity market is a valid two-leg pair;
- `reconciliation_residual = closed_realized_pnl - matched_pair_edge`.

`reconciliation_residual` is deliberately neutral terminology. It is NOT called directional PnL, rewards, rebates, execution edge, or fees because those components are not separately identified yet.

## Frozen aggregate comparisons

Report, without optimization:

- join coverage counts and percentages;
- total/mean/median `closed_realized_pnl` on joined valid-pair markets;
- total `matched_pair_edge`;
- total `reconciliation_residual`;
- same aggregates split only by the previously frozen pair-cost partition: `<1.00` vs `>=1.00`;
- same aggregates by BTC/ETH × 5m/15m;
- Pearson correlation between condition-level `matched_pair_edge` and `closed_realized_pnl` if at least 20 joined valid-pair markets exist;
- share of conditions where signs agree, treating values with absolute magnitude `<1e-9` as zero.

No new pair-cost thresholds may be introduced in this stage.

## Integrity checks

- activity and settlement condition IDs must be exact strings;
- no BACKFILL `first_observed_time` may enter any metric;
- invalid one-leg or >2-leg activity markets are excluded from pair-edge reconciliation but retained in coverage reporting;
- closed-position rows are not assumed to represent rewards/rebates;
- results are scoped to one wallet and one UTC day.

## Hard prohibitions

This stage does NOT prove:
- that `reconciliation_residual` is directional alpha;
- that closed-position PnL equals total wallet economics;
- that maker rebates or liquidity rewards are absent/present;
- that a follower could realize either component;
- that paired-cost `<1` is simultaneously executable;
- any COPY/WATCH/SKIP decision.

Any decomposition of `reconciliation_residual` into directional / rewards / execution / unknown requires a new contract and independent evidence.
