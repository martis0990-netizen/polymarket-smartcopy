# Stage 2H — Historical Paired-Leg Decomposition Contract

Status: FROZEN BEFORE Stage 2H implementation/results

## Purpose

Describe Bonereaper's historical paired inventory on one already-frozen complete activity interval without making causal, live-latency, profitability, market-making, arbitrage, or copyability claims.

Stage 2H is source-time descriptive research only. `ObservationMode.BACKFILL` is valid input. `first_observed_time` MUST NOT be used for episode formation, timing, or latency.

## Frozen evidence

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- UTC interval: `2026-08-25T00:00:00Z` through `2026-08-25T23:59:59Z`
- activity rows: 70,474
- source artifact SHA256: `9b95fc0535da5857589fd7fa1d49fb37e1504af9700ab5378df88902af071f42`
- normalized artifact SHA256: `5fd68d01a6768818303f288c9a61285c3ebc848f90566e2c05380c1bd895b5b4`
- completeness: `PROVEN_WITHIN_REQUESTED_RANGE`

Changing wallet, interval, source artifact, normalized artifact, or any metric below creates a new Stage 2H contract version.

## Frozen market scope

Analyze only deterministic `CRYPTO_UPDOWN_5M` and `CRYPTO_UPDOWN_15M` markets whose market text identifies BTC/Bitcoin or ETH/Ethereum.

Per `condition_id`, require exactly two canonical outcomes: `Up` and `Down` (case-insensitive). Markets that cannot be mapped unambiguously to these two outcomes are reported as excluded, never guessed.

Only `TRADE` rows are considered. BUY and SELL counts are always reported separately. Pair-cost metrics are computed from BUY inventory only. Presence of SELL rows does not get silently netted into BUY history.

## Per-leg metrics

For Up and Down independently, compute from BUY rows:

- fill count
- total token size
- total USDC size
- VWAP price = `sum(price * size) / sum(size)` over rows with non-null price and positive size
- first source event time
- last source event time

No `first_observed_time` metric is permitted in Stage 2H.

## Per-market paired inventory metrics

Given total BUY token sizes `U` and `D`:

- `matched_size = min(U, D)`
- `excess_up = max(U - D, 0)`
- `excess_down = max(D - U, 0)`
- `paired_fraction = 2 * matched_size / (U + D)` when `U + D > 0`
- `pair_vwap_sum = up_vwap + down_vwap` when both VWAPs exist
- `gross_pair_margin_per_unit = 1 - pair_vwap_sum`
- `matched_average_cost = matched_size * pair_vwap_sum`

These are average-cost inventory descriptors. They MUST NOT be labeled executable arbitrage because the two legs may have been acquired at different times.

## Frozen timing metrics

Use source timestamps only:

- `first_leg_gap_seconds = abs(first_up_source_time - first_down_source_time)`
- `first_leg_order = UP_FIRST | DOWN_FIRST | SAME_SECOND`
- `market_activity_span_seconds = last_any_source_time - first_any_source_time`

No causal latency or follower delay may be inferred.

## Frozen aggregate summary

Report:

- included market count
- excluded ambiguous-market count
- markets with both BUY legs
- markets with one BUY leg only
- BUY row count / SELL row count
- matched token size total
- excess Up token size total
- excess Down token size total
- median paired fraction
- median and mean pair VWAP sum
- count/share with `pair_vwap_sum < 1.00`
- count/share with `pair_vwap_sum <= 0.99`
- median first-leg gap seconds
- p25 / p75 first-leg gap seconds
- UP_FIRST / DOWN_FIRST / SAME_SECOND counts

Thresholds `1.00` and `0.99` are descriptive and frozen here before Stage 2H output generation. No threshold sweep is permitted.

## Required negative controls / integrity checks

Stage 2H MUST fail closed or explicitly exclude rather than infer when:

- an input row is not `ObservationMode.BACKFILL`
- source timestamps are absent
- outcome mapping is ambiguous
- a paired metric lacks both leg VWAPs
- size is negative
- source activity lies outside the frozen requested interval

Exact duplicate rows may only be removed according to the immutable identity already used by Stage 1.1.

## Forbidden claims

Stage 2H output alone cannot prove:

- profitability
- guaranteed arbitrage
- market making
- maker/taker status
- rewards/rebates
- settlement PnL
- directional skill
- live observation latency
- residual/copyable edge

Those require later evidence/contracts.

## Gate

Stage 2H passes only if deterministic tests pass and the frozen Bonereaper artifact can be processed reproducibly into the declared metrics with no use of `first_observed_time`.
