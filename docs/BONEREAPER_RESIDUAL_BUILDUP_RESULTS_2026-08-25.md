# Bonereaper residual-inventory buildup — 2026-08-25 UTC

Status: RESULT UNDER FROZEN SOURCE-TIME STATE-MACHINE CONTRACT

Contract: `docs/BONEREAPER_RESIDUAL_BUILDUP_CONTRACT.md`

Population: `752` valid two-leg BTC/ETH 5m/15m markets from the frozen complete activity backfill.

## Aggregate path accounting

Total acquired outcome size: `1,187,331.933985`.

Across the ordered BUY paths:
- pair-balancing quantity: `403,231.496236`;
- residual-increasing quantity: `784,100.437749`;
- residual-increasing share of acquired quantity: `66.0389%`.

`Residual-increasing quantity` is path accounting: a BUY is residual-increasing when it increases the absolute imbalance at that point in source time. Some of that temporary imbalance is later matched by subsequent BUYs on the opposite leg, so it is not equal to final residual inventory.

Final residual-size share per market:
- p25: `14.2067%`;
- median: `29.5809%`;
- p75: `47.2278%`.

Thus the wallet typically ends with material unmatched inventory even though nearly every target market contains both outcomes.

## Imbalance switching

Median number of cumulative-imbalance sign flips per market: `2`.

- zero flips: `21.9415%` of markets;
- exactly one flip: `23.9362%`;
- two or more flips: `54.1223%`.

This is inconsistent with an overly simple path of “choose one side once and keep it dominant.” In more than half the markets, the larger cumulative leg changes sides at least twice during the BUY sequence.

Final dominant outcome:
- Down: `407` markets;
- Up: `344` markets;
- equal/no final dominant outcome: `1` market.

No eventual winner is used here; Up/Down are only the contract labels of the final larger acquired leg.

## Market-clock placement of residual-increasing quantity

Using canonical slug window start and the frozen Q1/Q2/Q3/Q4 market-window buckets:

- Q1: `21.3008%`;
- Q2: `17.6893%`;
- Q3: `25.4888%`;
- Q4: `26.5031%`;
- outside canonical window: `9.0181%`.

Residual-increasing BUYs therefore occur throughout the market window rather than only at market open. The late-window Q3+Q4 share is substantial, but this alone does not identify a directional mechanism.

## Previously frozen pair-cost partition

### Pair cost < 1.00

Markets: `293`.

- residual-increasing quantity share: `62.7155%`;
- final residual share median: `23.8140%`;
- sign flips median: `2`;
- zero / one / >=2 flips: `21.5017% / 26.6212% / 51.8771%`;
- residual quantity Q1/Q2/Q3/Q4/outside: `28.1065% / 20.7765% / 25.6516% / 16.2981% / 9.1673%`;
- final dominant outcome: Down `157`, Up `136`.

### Pair cost >= 1.00

Markets: `459`.

- residual-increasing quantity share: `67.6124%`;
- final residual share median: `33.0220%`;
- sign flips median: `2`;
- zero / one / >=2 flips: `22.2222% / 22.2222% / 55.5556%`;
- residual quantity Q1/Q2/Q3/Q4/outside: `18.3118% / 16.3335% / 25.4172% / 30.9849% / 8.9526%`;
- final dominant outcome: Down `250`, Up `208`, none `1`.

The frozen `>=1` regime shows both a larger final residual share and more residual-increasing quantity late in the market window than the `<1` regime. This is a descriptive state difference, not a tuned trading rule.

## BTC/ETH × horizon split

| Segment | Markets | Residual-increasing share | Final residual share median | Median flips | Q1 | Q2 | Q3 | Q4 | Outside | Final Down / Up / None |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| BTC 5m | 282 | 66.3629% | 30.5508% | 1 | 20.7745% | 17.3704% | 25.3763% | 23.6330% | 12.8458% | 155 / 127 / 0 |
| BTC 15m | 92 | 66.6920% | 33.7254% | 2 | 16.3435% | 12.0054% | 21.3699% | 46.3671% | 3.9141% | 58 / 34 / 0 |
| ETH 5m | 283 | 63.6041% | 25.6508% | 2 | 28.6053% | 24.6404% | 26.7318% | 16.6383% | 3.3842% | 142 / 140 / 1 |
| ETH 15m | 95 | 69.6760% | 35.2865% | 2 | 15.8636% | 13.3905% | 33.8071% | 32.7280% | 4.2108% | 52 / 43 / 0 |

BTC 15m has a particularly large Q4 residual-increasing share on this day, while ETH 5m is more front-loaded and has almost balanced final Up/Down dominance. These differences were not used to select thresholds or strategies.

## What this stage changes in the working model

The evidence no longer supports a simple “buy both legs once, then hold a small directional tail” description.

A more accurate bounded description for this day is:

`repeated BUYs on both legs → temporary imbalance grows → opposite-leg BUYs partly rebalance it → imbalance often flips sign → material unmatched inventory remains at the end`.

That is compatible with dynamic inventory management, but it does NOT by itself prove market making, momentum, stale-price exploitation, or intentional directional forecasting.

## Next evidence needed

To determine whether the unmatched component is informed rather than merely inventory management, a new frozen study must relate source-time imbalance changes to an independent price-information stream and/or Polymarket repricing. Historical activity alone cannot answer that question causally, and BACKFILL observation timestamps remain forbidden for follower-latency analysis.
