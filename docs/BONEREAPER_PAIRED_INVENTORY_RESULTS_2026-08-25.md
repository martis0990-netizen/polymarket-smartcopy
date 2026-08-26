# Bonereaper paired-inventory decomposition — 2026-08-25 UTC

Status: DESCRIPTIVE RESULT UNDER FROZEN CONTRACT

Contract: `docs/BONEREAPER_PAIRED_INVENTORY_CONTRACT.md`

Dataset provenance:
- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- interval: `2026-08-25T00:00:00Z` through `2026-08-25T23:59:59Z`
- complete activity rows: `70,474`
- normalized SHA256: `5fd68d01a6768818303f288c9a61285c3ebc848f90566e2c05380c1bd895b5b4`
- primary target: BTC/ETH explicit 5m/15m Up/Down BUY activity

## Target-family totals

- BUY rows: `51,343`
- markets: `763`
- valid two-asset markets: `752`
- both-outcome market share: `98.5583%`
- source BUY notional: `$688,625.98`
- matched paired size: `403,231.496236` outcome units
- matched acquisition cost: `$432,633.60`
- unmatched/residual acquisition notional: `$255,131.21`
- residual-size share of total acquired outcome units: `32.0262%`

The paired/residual split is accounting-only. It is not realized PnL and does not include fees, rebates, liquidity rewards, sells outside this interval, redemptions, transfers, or queue economics.

## Paired acquisition cost

`paired_cost_per_unit = VWAP(leg A) + VWAP(leg B)` where each leg VWAP is `sum(usdc_size) / sum(size)`.

Across 752 valid two-leg target markets:

- mean: `1.05994`
- median: `1.04870`
- p10: `0.88513`
- p25: `0.95184`
- p75: `1.16360`
- p90: `1.25584`
- `< 1.00`: `38.9628%`
- `<= 0.99`: `35.7713%`
- `<= 0.98`: `33.5106%`
- `<= 0.95`: `24.3351%`

Therefore the simple claim that the wallet generally obtains a complete two-outcome pair below $1 is not supported by this day. A substantial minority of markets do have aggregate leg VWAP below $1, but more than half do not.

A prior exploratory figure near 41.8% was computed from per-row quoted `price`; it is superseded by this contract-defined `usdc_size/size` VWAP result and must not be used as canonical evidence.

## First-leg timing

Using only `source_event_time`:

- median absolute gap between first acquisition of the two legs: `27s`
- both legs first acquired within 1s: `3.0585%`
- within 5s: `9.7074%`
- within 15s: `28.9894%`
- within 30s: `55.1862%`
- within 60s: `87.3670%`

This rejects an overly simple interpretation that both legs are normally acquired simultaneously. Historical BACKFILL `first_observed_time` is not used for these timing calculations.

## Frozen descriptive split

| Segment | Markets | Valid pairs | BUY rows | BUY notional | Median pair cost | Pair cost <1 | Residual-size share | Median first-leg gap |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC 5m | 287 | 282 | 19,781 | $403,038.19 | 1.08206 | 33.6879% | 32.6775% | 32.5s |
| BTC 15m | 95 | 92 | 8,575 | $115,064.20 | 1.07979 | 34.7826% | 33.2357% | 24s |
| ETH 5m | 285 | 283 | 17,196 | $127,350.48 | 1.01536 | 47.3498% | 27.2057% | 21s |
| ETH 15m | 96 | 95 | 5,791 | $43,173.11 | 1.07037 | 33.6842% | 39.3431% | 39s |

ETH 5m is descriptively different on this day (lower median pair cost and larger `<1` share), but this document makes no alpha claim and performs no significance testing or threshold search.

## What is proven

- Bonereaper activity in the target family is overwhelmingly dual-outcome by market on this day.
- Acquired inventory contains both a large matched-pair component and a material one-sided residual component.
- Pair acquisition below $1 occurs often enough to matter descriptively, but not in the majority of valid target markets under the frozen VWAP definition.
- First-leg timing is usually not simultaneous at sub-second/few-second scale.

## What is not proven

This result does not establish:
- realized profitability of the matched component;
- market making or arbitrage as the strategy label;
- maker/taker classification;
- maker rebates or liquidity rewards;
- whether residual inventory is intentionally directional;
- whether the wallet leads Polymarket repricing;
- whether a follower can observe and reproduce any edge;
- COPY/WATCH/SKIP eligibility.

The next stage must add settlement/profit-source evidence or prospective live-observation evidence under a separately frozen contract. No outcome-conditioned optimization is authorized by this document.
