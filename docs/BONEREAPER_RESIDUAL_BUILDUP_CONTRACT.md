# Bonereaper residual-inventory buildup — frozen contract

Status: FROZEN BEFORE RESULTS

Dataset: already-frozen Bonereaper 2026-08-25 UTC target-family BTC/ETH 5m/15m BUY activity.

## Purpose

Describe how paired and unmatched inventory are formed through source-time BUY sequences. This is historical source-time accounting only. It does not infer live observation latency, winner selection, directional alpha, or copyability.

## Fill ordering

Within each exact `condition_id`, process target-family BUY rows in deterministic order:
1. `source_event_time` ascending;
2. `transaction_hash` ascending;
3. `asset` ascending.

Exactly two assets are required. One-leg or >2-asset markets are excluded from dynamic two-leg decomposition and reported as non-eligible.

## Per-fill quantity decomposition

Before a BUY fill on one leg, let:
- `own_before` = cumulative acquired size on the fill's leg;
- `other_before` = cumulative acquired size on the opposite leg;
- `q` = fill size.

If `own_before < other_before`:
- `pair_balancing_quantity = min(q, other_before - own_before)`;
- `residual_increasing_quantity = q - pair_balancing_quantity`.

If `own_before >= other_before`:
- `pair_balancing_quantity = 0`;
- `residual_increasing_quantity = q`.

This decomposition is path-dependent but deterministic. It does not assert intent.

## Frozen market-level outputs

For each valid two-leg market report:
- total BUY size;
- total pair-balancing quantity;
- total residual-increasing quantity;
- final matched size and final residual size;
- residual-increasing quantity share of BUY size;
- first-leg gap in source seconds;
- time of first residual-increasing fill;
- time of first pair-balancing fill;
- final dominant residual asset/outcome, if any;
- number of times the sign of cumulative leg imbalance flips;
- maximum absolute cumulative imbalance as share of total final BUY size.

## Market clock

For canonical BTC/ETH Up/Down slugs ending in a Unix window-start epoch:
- derive market window start from the slug suffix;
- horizon is fixed by already-classified 5m or 15m family;
- report residual-increasing BUY quantity by source-time quartile of the market window: Q1 0–25%, Q2 25–50%, Q3 50–75%, Q4 75–100%;
- fills outside the canonical `[window_start, window_end]` interval are reported separately and never clipped into a quartile.

These quartiles are frozen before results and are descriptive, not optimized thresholds.

## Frozen aggregate outputs

Report for all eligible target markets and BTC/ETH × 5m/15m:
- market count;
- aggregate pair-balancing and residual-increasing quantities;
- residual-increasing quantity share;
- median/p25/p75 final residual-size share;
- median imbalance sign-flip count;
- share with zero, one, and >=2 sign flips;
- residual-increasing quantity share by Q1/Q2/Q3/Q4/outside;
- final dominant outcome counts Up vs Down vs none.

Also report the same aggregates under the previously frozen market partition `paired_cost_per_unit <1.00` vs `>=1.00`; no new price threshold is introduced.

## Hard prohibitions

- do not call residual-increasing quantity directional alpha;
- do not condition on eventual market winner in this stage;
- do not use BACKFILL `first_observed_time`;
- do not alter time buckets after seeing results;
- do not infer simultaneous executability;
- no COPY/WATCH/SKIP decision.
