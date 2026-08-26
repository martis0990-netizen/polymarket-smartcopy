# Bonereaper paired-inventory decomposition — frozen contract

Status: FROZEN BEFORE OUTCOME / COPYABILITY ANALYSIS

Dataset:
- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- source interval: `2026-08-25T00:00:00Z` through `2026-08-25T23:59:59Z`
- evidence verdict: `BONEREAPER_STAGE1_BACKFILL_PASS`
- row count: `70,474`
- normalized artifact SHA256: `5fd68d01a6768818303f288c9a61285c3ebc848f90566e2c05380c1bd895b5b4`

## Purpose

Describe how historical BUY activity is split between matched two-outcome inventory and one-sided residual inventory. This is source-time descriptive research only. It does not estimate live observation latency, profitability, maker/taker status, rewards, or copyable edge.

## Scope

Primary target family: BTC/ETH crypto Up/Down markets with explicit 5m or 15m horizon. Unsupported/ambiguous markets remain excluded from target-family summaries rather than guessed.

## Deterministic definitions

For each `condition_id` and outcome asset:

- `buy_size`: sum of source BUY sizes.
- `buy_notional`: sum of source `usdc_size`.
- `vwap`: `buy_notional / buy_size` when size > 0.
- exactly two distinct outcome assets are required for paired decomposition. Markets with fewer or more than two distinct assets are reported separately and not coerced into a pair.

For a valid two-asset market with legs A and B:

- `matched_size = min(buy_size_A, buy_size_B)`.
- `paired_cost_per_unit = vwap_A + vwap_B`.
- `matched_pair_cost = matched_size * paired_cost_per_unit`.
- `gross_pair_value_at_resolution = matched_size` for a complete binary pair.
- `gross_pair_edge = gross_pair_value_at_resolution - matched_pair_cost`.
- `residual_size_A = buy_size_A - matched_size`.
- `residual_size_B = buy_size_B - matched_size`.
- `directional_residual_notional` is the source acquisition notional attributable to unmatched size, using the leg VWAP.

These are accounting descriptors, not profit attribution. They ignore fees, rebates/rewards, sells outside this sample, transfers, redemption timing, and execution queue economics.

## Timing descriptors

For each valid two-leg market record:

- first and last source-event time per leg;
- absolute gap between first observed source-event times of the two legs;
- whether both legs were first acquired within 1s, 5s, 15s, 30s, 60s, or later.

No `first_observed_time` field from BACKFILL may be used for timing inference.

## Frozen aggregate outputs

Report for target-family markets:

- market count;
- valid two-leg market count;
- both-outcome market share;
- total BUY rows and notional;
- total matched size and matched acquisition cost;
- total residual notional and residual-size share;
- paired-cost-per-unit distribution: mean, median, p10, p25, p75, p90;
- share with paired cost `<1.00`, `<=0.99`, `<=0.98`, `<=0.95`;
- first-leg gap distribution and frozen bucket shares;
- split by BTC vs ETH and 5m vs 15m.

## Hard prohibitions

- no profitability claim from `paired_cost < 1` alone;
- no market-making/arbitrage label from paired buying alone;
- no historical live-latency estimate from BACKFILL ingestion timestamps;
- no threshold search beyond the frozen reporting cutoffs above;
- no settlement/outcome-conditioned analysis in this stage;
- no COPY/WATCH/SKIP decision in this stage.

A later profit-source or copyability study requires a new frozen contract and additional settlement/cost/live-observation evidence.
