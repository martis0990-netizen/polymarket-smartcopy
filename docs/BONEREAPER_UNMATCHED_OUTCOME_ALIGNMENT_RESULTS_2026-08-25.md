# Bonereaper unmatched-inventory outcome alignment — 2026-08-25 UTC

Status: RESULT UNDER FROZEN OUTCOME-ALIGNMENT CONTRACT

Contract: `docs/BONEREAPER_UNMATCHED_OUTCOME_ALIGNMENT_CONTRACT.md`

Population: `738` eligible high-consistency markets from the frozen matched-vs-unmatched allocation; `737` have nonzero final unmatched size.

## All nonzero-residual eligible markets

Markets: `737`.

Final unmatched asset has positive / negative / approximately zero unit closed PnL:
- positive: `440` (`59.7015%`);
- negative: `295` (`40.0271%`);
- zero: `2` (`0.2714%`).

Unmatched inventory economics:
- aggregate realized PnL: `+$29,756.0081`;
- median condition PnL: `+$20.1506`;
- sum of positive unmatched PnL magnitudes: `+$61,290.1565`;
- sum of negative unmatched PnL magnitudes: `-$31,534.1484`;
- size-weighted share of final unmatched inventory whose asset has positive unit closed PnL: `74.7669%`.

Final dominant outcome labels:
- Down: `401`;
- Up: `336`.

This establishes a positive historical outcome association for the final unmatched inventory on this frozen day. It does not establish causality or live copyability.

## Frozen pair-cost partition

### Pair cost < 1.00

Markets with nonzero final residual: `291`.

- positive unmatched leg: `112` (`38.4880%`);
- negative: `178` (`61.1684%`);
- zero: `1`;
- unmatched inventory PnL: `+$356.8218`;
- median unmatched PnL: `-$21.5463`;
- positive magnitude: `+$16,649.2686`;
- negative magnitude: `-$16,292.4468`;
- size-weighted positive unmatched share: `41.1899%`;
- final Down / Up: `156 / 135`.

In this regime the historical profit evidence remains dominated by the matched-pair component. The unmatched component is approximately flat in aggregate and more often negative by condition count.

### Pair cost >= 1.00

Markets with nonzero final residual: `446`.

- positive unmatched leg: `328` (`73.5426%`);
- negative: `117` (`26.2332%`);
- zero: `1`;
- unmatched inventory PnL: `+$29,399.1864`;
- median unmatched PnL: `+$44.2114`;
- positive magnitude: `+$44,640.8879`;
- negative magnitude: `-$15,241.7016`;
- size-weighted positive unmatched share: `86.4246%`;
- final Down / Up: `245 / 201`.

This is strong descriptive evidence that the unmatched component in the frozen `>=1` regime is not merely symmetric inventory noise on this day. It remains inappropriate to call it directional alpha without independent price/timing evidence.

## BTC/ETH × horizon

| Segment | Markets | Positive unmatched leg | Unmatched PnL | Median PnL | Size-weighted positive share | Final Down / Up |
|---|---:|---:|---:|---:|---:|---:|
| BTC 5m | 277 | 62.8159% | +$23,109.6183 | +$72.0831 | 77.0991% | 153 / 124 |
| BTC 15m | 90 | 67.7778% | +$5,906.0778 | +$54.6559 | 81.6352% | 58 / 32 |
| ETH 5m | 278 | 48.2014% | -$1,325.4129 | -$2.8743 | 53.6550% | 140 / 138 |
| ETH 15m | 92 | 77.1739% | +$2,065.7249 | +$23.0362 | 91.6437% | 50 / 42 |

The ETH 5m exception is important: the unmatched component is not uniformly positive across target families on this day.

## Last residual-increasing fill market-clock bucket

Using the quartiles frozen before this outcome test:

| Last residual-increasing fill | Markets | Unmatched PnL | Positive / Negative |
|---|---:|---:|---:|
| Q1 | 26 | -$2.6876 | 10 / 16 |
| Q2 | 63 | +$1,731.6490 | 36 / 27 |
| Q3 | 212 | +$1,115.2722 | 111 / 101 |
| Q4 | 417 | +$23,165.5049 | 265 / 150 |
| Outside canonical window | 19 | +$3,746.2697 | 18 / 1 |

The Q4 group contains most markets and most aggregate unmatched PnL. This is descriptive association only: market count, position size, volatility, price level, and other confounders are not controlled here.

## Bounded conclusion

The historical evidence now supports a two-regime working hypothesis:

1. `pair cost <1`: economics are primarily explained by matched paired inventory; unmatched inventory is not reliably positive.
2. `pair cost >=1`: matched inventory is economically costly, while a large, frequently positive unmatched component offsets much of that cost; the unmatched component is especially material in later source-time market activity.

This is a hypothesis about economic structure, not yet a causal trading strategy.

The correct next step is prospective observation: capture wallet actions as `LIVE_OBSERVED`, align them with executable Polymarket prices and independent market information, and measure how much of this unmatched-inventory association remains after observation delay, spread, fees, and slippage. Historical BACKFILL cannot answer that.
