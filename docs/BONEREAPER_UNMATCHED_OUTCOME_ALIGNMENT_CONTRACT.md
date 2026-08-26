# Bonereaper unmatched-inventory outcome alignment — frozen contract

Status: FROZEN BEFORE RESULTS

Population: eligible exact-asset high-consistency markets from the already-frozen 2026-08-25 matched-vs-unmatched PnL allocation. No new market selection or pair-cost threshold is introduced.

## Purpose

Test whether the final unmatched inventory component is economically positive at settlement/closure more often and more strongly than negative. This is a historical outcome-association test only. It does NOT establish causality, foresight, live observability, or copyability.

## Market-level definitions

For each eligible market with nonzero final unmatched size:
- identify the exact asset with final unmatched size from the frozen activity accounting;
- obtain its exact asset-level bounded closed-position realized PnL rate: `unit_closed_realized_pnl = closed_realized_pnl / closed_total_bought`;
- `unmatched_leg_positive = unit_closed_realized_pnl > 1e-9`;
- `unmatched_leg_negative = unit_closed_realized_pnl < -1e-9`;
- otherwise zero;
- `unmatched_inventory_realized_pnl` remains the already-defined allocated PnL on unmatched size.

No attempt is made to infer an oracle outcome directly from title text or external data.

## Frozen outputs

For all eligible markets with nonzero unmatched size, and for the already frozen partitions `<1.00` vs `>=1.00` plus BTC/ETH × 5m/15m, report:
- market count;
- positive / negative / zero unmatched-leg counts and shares;
- total unmatched-inventory realized PnL;
- median unmatched-inventory realized PnL;
- positive-PnL magnitude vs negative-PnL magnitude;
- size-weighted share of final unmatched inventory whose asset has positive unit closed PnL;
- final dominant outcome label counts Up vs Down.

Using the previously frozen market-window quartiles from `BONEREAPER_RESIDUAL_BUILDUP_CONTRACT.md`, also report descriptive positive/negative unmatched PnL totals grouped by the quartile containing the LAST residual-increasing BUY fill. Fills outside the canonical window remain `outside`.

## Interpretation constraints

A positive unmatched leg is not automatically “directional alpha.” Possible explanations include informed direction, inventory skew, price-dependent sizing, settlement mechanics, maker economics captured in closed-position accounting, or other behavior not yet identified.

Historical BACKFILL cannot establish when a follower would have observed the skew. No COPY/WATCH/SKIP decision is authorized.

## Hard prohibitions

- no new threshold search;
- no exclusion of losing residual markets;
- no post-hoc selection of quartiles;
- no claim that positive association implies causality;
- no claim of copyable residual edge without prospective LIVE_OBSERVED evidence and executable market prices.
