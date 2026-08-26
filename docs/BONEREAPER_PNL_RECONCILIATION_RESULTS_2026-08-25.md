# Bonereaper activity ↔ closed-position PnL reconciliation — 2026-08-25 UTC

Status: RESULT UNDER FROZEN RECONCILIATION CONTRACT

Contract: `docs/BONEREAPER_PNL_RECONCILIATION_CONTRACT.md`

## Evidence inputs

Activity evidence:
- wallet `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- complete 2026-08-25 UTC activity backfill
- 70,474 total TRADE rows
- paired-inventory target population: BTC/ETH explicit 5m/15m Up/Down markets

Settlement evidence:
- bounded `/closed-positions` collection for the same UTC day
- 3,855 closed-position rows across 2,159 condition IDs overall
- aggregate bounded closed-position `realizedPnl`: `-$5,780.2070`
- positive rows: `2,141`
- negative rows: `1,702`
- zero rows: `12`
- missing closed timestamp rows encountered: `0`
- pages fetched: `106`
- last offset: `5,250`
- closed-position artifact SHA256: `d4573d8c6cbf2306a41209911b0777f20f3d518741d24b78392b8cb527dfb35b`

The overall `-$5,780.21` is NOT asserted to be total wallet economics. It is only the sum of bounded Data API closed-position rows and may omit or differently account for rebates, rewards, transfers, open inventory, and other economics.

## Target-family settlement subset

Within BTC/ETH explicit 5m/15m Up/Down closed-position rows:

- closed rows: `1,500`
- condition IDs: `755`
- bounded closed-position realized PnL: `+$851.2665`

## Exact condition-ID reconciliation coverage

Activity target markets: `763`

Settlement target markets: `755`

Exact joined condition IDs: `751`

- activity-only: `12`
- closed-only: `4`
- joined share of activity markets: `98.4273%`
- joined share of settlement markets: `99.4702%`

Among joined markets, `741` are valid two-leg activity decompositions under the frozen paired-inventory contract.

Closed-position row shape among those 741 valid pairs:
- 739 conditions have exactly 2 closed rows;
- 1 condition has 3 closed rows across 2 assets;
- 1 condition has 1 closed row / 1 asset.

These two irregular cases remain in the frozen population; they are disclosed rather than silently removed.

## Primary reconciliation

For each valid joined condition:

`matched_pair_edge = matched_size * (1 - paired_cost_per_unit)`

`reconciliation_residual = closed_realized_pnl - matched_pair_edge`

Across all 741 valid joined pairs:

- closed-position PnL total: `+$1,290.1631`
- mean closed PnL / condition: `+$1.7411`
- median closed PnL / condition: `-$7.5001`
- matched-pair accounting edge total: `-$28,478.4833`
- reconciliation residual total: `+$29,768.6464`
- Pearson correlation, matched-pair edge vs closed PnL: `0.35257`
- sign agreement share: `54.3860%`

The positive reconciliation residual is NOT labeled directional PnL. It is an unexplained reconciliation term under this contract.

## Frozen pair-cost partition

### Pair cost < 1.00

Conditions: `292`

- closed-position PnL total: `+$10,881.0555`
- mean: `+$37.2639`
- median: `+$1.6997`
- matched-pair accounting edge: `+$10,683.1777`
- reconciliation residual: `+$197.8778`

At aggregate level, the matched-pair accounting component and bounded closed-position PnL are very close in this subset. This is consistent with paired acquisition below $1 explaining most aggregate closed-position economics for this subset, but it is not proof of simultaneous executable arbitrage or total wallet profit.

Condition-level residuals remain dispersed; aggregate closeness must not be interpreted as every condition reconciling tightly.

### Pair cost >= 1.00

Conditions: `449`

- closed-position PnL total: `-$9,590.8924`
- mean: `-$21.3606`
- median: `-$10.1783`
- matched-pair accounting edge: `-$39,161.6610`
- reconciliation residual: `+$29,570.7686`

Here the matched-pair component alone would be substantially more negative than the bounded closed-position result. A large positive reconciliation residual offsets most of that accounting loss. This establishes a material unexplained component; it does NOT establish that the component is directional alpha.

## BTC/ETH × horizon split, joined valid pairs

| Segment | Conditions | Closed PnL | Matched-pair edge | Reconciliation residual |
|---|---:|---:|---:|---:|
| BTC 5m | 278 | +$2,055.6503 | -$20,931.2150 | +$22,986.8653 |
| BTC 15m | 90 | +$1,670.5827 | -$4,236.9385 | +$5,907.5212 |
| ETH 5m | 280 | -$3,515.5350 | -$2,304.8463 | -$1,210.6887 |
| ETH 15m | 93 | +$1,079.4651 | -$1,005.4835 | +$2,084.9486 |

This split is descriptive only. No thresholds or market families were selected after seeing these results.

## Interpretation allowed by this stage

The frozen evidence supports three bounded statements:

1. Bonereaper's BTC/ETH 5m/15m activity and same-day closed-position evidence reconcile at very high condition-ID coverage.
2. For the predeclared pair-cost `<1` subset, aggregate matched-pair accounting edge is close to aggregate bounded closed-position PnL.
3. For the `>=1` subset, a large positive unexplained reconciliation residual is economically material and requires further decomposition.

## Interpretation NOT allowed yet

This document does not prove that the reconciliation residual is:
- directional trading PnL;
- maker execution edge;
- rebates;
- liquidity rewards;
- fee effects;
- inventory carried from outside the frozen day;
- or copyable edge.

It also does not prove simultaneous availability of both paired leg VWAPs to a follower.

The next stage must explicitly decompose the reconciliation residual using additional evidence. Until then the correct label is `UNEXPLAINED_RECONCILIATION_RESIDUAL`.
