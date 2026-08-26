# Bonereaper matched vs unmatched inventory PnL allocation — frozen contract

Status: FROZEN BEFORE ALLOCATION RESULTS

Inputs are the already-frozen 2026-08-25 UTC:
- target-family activity backfill and paired-inventory decomposition;
- bounded closed-position evidence;
- asset accounting consistency result.

## Eligibility

A valid two-leg activity market is eligible only if BOTH exact `(condition_id, asset)` legs:
- exist in closed-position evidence;
- have activity buy size > 0 and closed totalBought > 0;
- satisfy the previously frozen diagnostic `relative size error <= 1e-4`.

No row is repaired, rescaled, or manually overridden. Ineligible conditions are reported separately.

## Asset-level realized-PnL rate

For each eligible asset:

`unit_closed_realized_pnl = sum(closed realizedPnl for condition+asset) / sum(closed totalBought for condition+asset)`

This is an accounting allocation rate, not an execution-return estimate.

## Condition-level allocation

For a valid two-leg market:

- `matched_size = min(activity_buy_size_A, activity_buy_size_B)` from the frozen paired decomposition;
- `unmatched_size_A = activity_buy_size_A - matched_size`;
- `unmatched_size_B = activity_buy_size_B - matched_size`;
- `matched_inventory_realized_pnl = matched_size * (unit_pnl_A + unit_pnl_B)`;
- `unmatched_inventory_realized_pnl = unmatched_size_A * unit_pnl_A + unmatched_size_B * unit_pnl_B`;
- `allocated_realized_pnl = matched_inventory_realized_pnl + unmatched_inventory_realized_pnl`;
- `closed_realized_pnl = sum closed realizedPnl across both exact asset keys`;
- `allocation_error = closed_realized_pnl - allocated_realized_pnl`.

Because activity size and closed `totalBought` are not asserted perfectly identical, allocation error must be reported rather than forced to zero.

## Frozen outputs

Report:
- total joined valid-pair conditions;
- eligible/ineligible condition counts and reasons;
- aggregate closed realized PnL, matched-inventory realized PnL, unmatched-inventory realized PnL, and allocation error;
- matched/unmatched contribution shares where total absolute component PnL is nonzero;
- same aggregates for the already frozen pair-cost partition `<1.00` vs `>=1.00`;
- same aggregates by BTC/ETH × 5m/15m;
- median condition-level matched and unmatched PnL;
- sign distribution for matched and unmatched components.

No additional pair-cost threshold or filtering may be introduced.

## Interpretation constraints

`unmatched_inventory_realized_pnl` is neutral accounting terminology. It MUST NOT be renamed directional alpha, momentum PnL, market-making edge, reward PnL, or copyable PnL without independent evidence.

`matched_inventory_realized_pnl` also does not prove simultaneous executable pair arbitrage for a follower because the two legs were often acquired at different source times.

This allocation uses Data API closed-position economics only and does not prove inclusion/exclusion of maker rebates, liquidity rewards, or other account-level transfers.

## Hard prohibitions

- no manual exclusion of negative/outlier conditions after seeing allocation results;
- no threshold search;
- no live-latency inference from historical BACKFILL;
- no COPY/WATCH/SKIP decision;
- no claim that allocated components equal total wallet economics.
