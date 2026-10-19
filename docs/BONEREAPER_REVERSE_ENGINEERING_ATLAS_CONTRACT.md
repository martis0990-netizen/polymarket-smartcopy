# Bonereaper Reverse-Engineering Atlas Contract

Status: **FROZEN BEFORE ATLAS OUTCOME INSPECTION**

## Purpose

Build a deterministic, source-time-only state reconstruction for Bonereaper's frozen
2026-08-25 BTC/ETH 5m/15m Up/Down activity. The atlas is a reverse-engineering evidence
layer, not a trading strategy and not a copy decision engine.

The target question is:

> Given the inventory state immediately before a Bonereaper BUY fill, what state transition
> did that fill cause?

## Frozen evidence

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- interval: `2026-08-25T00:00:00Z` through `2026-08-25T23:59:59Z`
- normalized activity SHA256:
  `5fd68d01a6768818303f288c9a61285c3ebc848f90566e2c05380c1bd895b5b4`
- observation mode: `BACKFILL` only
- target families: BTC/ETH `crypto_updown_5m` and `crypto_updown_15m`
- activity type: `TRADE`
- side: `BUY`
- outcomes must resolve unambiguously to `Up` or `Down`
- each included market must have exactly two token assets

`first_observed_time` is ingestion provenance only and MUST NOT be used analytically.
All ordering and market-phase calculations use `source_event_time`.

## Deterministic fill ordering

Within each `condition_id`, fills are ordered by:

1. `source_event_time`
2. `transaction_hash` (empty string when absent)
3. `asset`
4. `price` (missing last)
5. `size`

No future market outcome, closed-position PnL, Polymarket book state, Hyperliquid state,
or later wallet activity may alter an earlier state row.

## State before and after every BUY

For each fill preserve at minimum:

- cumulative Up and Down inventory before and after;
- matched inventory before and after;
- residual side and residual size before and after;
- running VWAP per leg and running pair-VWAP sum when both legs exist;
- balancing quantity created by the fill;
- residual-increasing quantity created by the fill;
- market elapsed time and time remaining from the exact 5m/15m slug window;
- fill price, size, USDC size, asset, outcome, transaction hash;
- deterministic action role.

## Frozen action-role semantics

For a BUY on one leg, let `deficit` be the amount by which that leg trails the opposite
leg immediately before the fill.

`balancing_quantity = min(fill_size, deficit)`

`residual_increasing_quantity = fill_size - balancing_quantity`

Roles are mutually exclusive:

- `PAIR_BALANCE`: balancing quantity > 0 and residual-increasing quantity = 0;
- `RESIDUAL_INCREASE`: balancing quantity = 0 and residual-increasing quantity > 0;
- `BALANCE_THEN_RESIDUAL`: both quantities > 0 in the same fill.

The first one-sided fill is therefore `RESIDUAL_INCREASE`; this is accounting semantics,
not a claim that it is directional alpha.

## Market sequence reconstruction

For each market emit a deterministic market record containing:

- role counts;
- Up/Down fill counts and quantities;
- final matched inventory;
- final residual side and size;
- imbalance sign-flip count;
- maximum absolute residual share;
- first/last source event time;
- compact run-length sequence signatures for action role and outcome;
- transition counts between consecutive action roles.

## Market phase

The market window comes only from the epoch suffix in the canonical 5m/15m slug.
Each fill is labeled `PRE_WINDOW`, `Q1`, `Q2`, `Q3`, `Q4`, or `POST_WINDOW`.
Rows outside the nominal market window are preserved rather than silently discarded.

## Explicit non-claims

This stage MUST NOT:

- infer `NO_ACTION` controls from wallet-only activity;
- infer a trigger from correlation alone;
- call residual inventory directional alpha;
- use settlement/PnL to label actions;
- use mutable fresh API responses to replace the frozen artifact;
- introduce ML, decision trees, thresholds, or optimization;
- make `COPY/WATCH/SKIP` decisions;
- place orders.

`NO_ACTION` controls require an independent market-state timeline and are deferred until
replayable Polymarket market data is available.

## Artifacts

The implementation writes create-only:

- `trade_atlas_steps.jsonl`
- `trade_atlas_markets.jsonl`
- `trade_atlas_summary.json`

The summary binds the exact input SHA256 and output artifact hashes.

## Acceptance gate

PASS requires:

1. exact frozen input SHA256;
2. deterministic byte-identical output for identical input;
3. all included rows are BACKFILL target BUY trades;
4. per-fill state conservation holds;
5. final market state reconciles with cumulative leg sizes;
6. no artifact overwrite;
7. tests and CI green.

Only after this gate may graphical visualization or trigger/counterfactual analysis consume
the atlas.