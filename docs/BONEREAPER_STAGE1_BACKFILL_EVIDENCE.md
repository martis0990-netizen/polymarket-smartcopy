# Bonereaper Stage 1 — Historical Activity Backfill Evidence

Status: **BONEREAPER_STAGE1_BACKFILL_PASS**

This document records a bounded historical activity backfill for the public Polymarket wallet `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30` (Bonereaper). It is Stage-1 evidence only: activity completeness and descriptive structure, not a profitability, alpha, strategy-source, or copyability claim.

## Frozen interval

Exactly one UTC day was selected before the successful run:

- start: `2026-08-25T00:00:00Z` (`1787616000`)
- end: `2026-08-25T23:59:59Z` (`1787702399`)
- activity type: `TRADE`
- observation mode: `BACKFILL`

Historical `first_observed_time` values are API-ingestion provenance only. They are not historical live-observation latency and must not be used to claim that SmartCopy could have observed these fills at those times.

## Runtime pagination correction

The first live attempt used the documented larger Activity offset budget and failed when the real Data API returned HTTP 400 at `offset=5500`. The code was corrected to use the empirically verified safe offset boundary `5000`; a full page at that boundary triggers timestamp-window splitting rather than a request to 5500.

The frozen day/wallet were not changed for the retry.

- failed verification run: `32954099784`
- successful verification run: `32954440207`
- successful verification branch head: `d8d51fbc05e4780c7e3ca88a60ffcd38a005d2f4`
- runtime-cap fix merged to main: `52c1ce18d2241055b1049d984fe77d5b2823db9c`

## Completeness result

The second run completed the full requested interval and the independent verifier passed.

- verdict: `BONEREAPER_STAGE1_BACKFILL_PASS`
- completeness: `PROVEN_WITHIN_REQUESTED_RANGE`
- rows: **70,474**
- first source event: `2026-08-25T00:00:00Z`
- last source event: `2026-08-25T23:59:55Z`
- distinct condition IDs: **2,479**
- distinct event slugs: **2,479**
- distinct token assets: **4,213**
- normalized rows with observation mode other than BACKFILL: **0**

The verifier also checked source-time ordering, line counts, manifest range/wallet, observation mode, and artifact byte/SHA-256 integrity.

## Immutable artifact fingerprints

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `activity_source_rows.jsonl` | 54,277,148 | `9b95fc0535da5857589fd7fa1d49fb37e1504af9700ab5378df88902af071f42` |
| `activity_normalized.jsonl` | 48,067,080 | `5fd68d01a6768818303f288c9a61285c3ebc848f90566e2c05380c1bd895b5b4` |

GitHub Actions artifact:

- artifact id: `9601460978`
- artifact name: `bonereaper-stage1-backfill-2026-08-25-r2`
- uploaded zip size: `9,220,380` bytes
- uploaded zip SHA-256: `86b5a484b9aede76d62f395f9bcb36caa3f933901c12cc056d26fbe7c0f3160c`

The large data files are not committed to the source repository.

## Descriptive observations from the frozen artifact

These are source-row descriptions only. They do not identify intent or profit source.

### Entire one-day sample

- all **70,474 / 70,474** activity rows have `side=BUY`
- total recorded `usdc_size` across rows: approximately **$953,751.62**
- **5.28%** of rows have price `>= 0.90`
- rows at price `>= 0.90` account for approximately **29.56%** of recorded `usdc_size`

`sum(usdc_size)` is gross recorded trade notional. It is not realized PnL, unique capital, maker rebate income, or copyable edge.

### Frozen SmartCopy target subset: BTC/ETH 5m + 15m canonical slugs

Target rule used only explicit canonical slugs matching BTC/ETH `updown-5m` or `updown-15m`. No outcome-based selection was used.

- rows: **51,343** (**72.85%** of the complete one-day activity sample)
- markets/event slugs: **763**
- gross recorded `usdc_size`: approximately **$688,625.98**
- markets with BUY activity in both Up and Down outcomes: **752 / 763 = 98.56%**
- one-outcome-only markets: **11 / 763**
- median absolute source-time gap between the first Up BUY and first Down BUY in dual-outcome markets: **27 seconds**
- **6.47%** of target rows have price `>= 0.90`
- price `>= 0.90` accounts for approximately **38.96%** of target recorded `usdc_size`

Breakdown:

| Family | Rows | Markets | Markets with both outcomes | Gross recorded `usdc_size` |
|---|---:|---:|---:|---:|
| BTC 5m | 19,781 | 287 | 282 | $403,038.19 |
| BTC 15m | 8,575 | 95 | 92 | $115,064.20 |
| ETH 5m | 17,196 | 285 | 283 | $127,350.48 |
| ETH 15m | 5,791 | 96 | 95 | $43,173.11 |

The near-universal dual-outcome BUY pattern is evidence of paired inventory behavior in this interval. It is **not** sufficient to label the strategy market making, arbitrage, hedging, or directional trading; those mechanisms require separate tests.

## Important negative/guardrail findings

1. The one-day Data API sample contains no SELL activity rows for this wallet. Therefore any claim that Bonereaper routinely "sells the losing leg" is not supported by this frozen interval.
2. Historical BACKFILL rows must not be passed into causal `IntentReconstructor.cluster`, because page-fetch observation times are not historical live latency.
3. High win-rate/profit claims are not tested by this artifact. Closed positions, settlements, rebates, liquidity rewards, executable follower prices, and costs are separate evidence layers.
4. The paired-outcome result does not by itself establish risk-free pair acquisition below $1. To test that, fills must be grouped causally by source time and pair economics must be computed without assuming simultaneous availability or follower execution.

## Next allowed research

The next bounded step is a **historical descriptive paired-leg study** over this already-frozen target subset. It may use source event times and recorded prices to measure pair timing/inventory construction, but it must remain explicitly non-causal with respect to SmartCopy observation latency.

A later live/prospective observation dataset is required for residual-edge and copyability timing claims.
