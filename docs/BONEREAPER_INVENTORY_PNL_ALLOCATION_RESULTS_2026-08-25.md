# Bonereaper matched vs unmatched inventory PnL allocation — 2026-08-25 UTC

Status: RESULT UNDER FROZEN ALLOCATION CONTRACT

Contract: `docs/BONEREAPER_INVENTORY_PNL_ALLOCATION_CONTRACT.md`

## Population and eligibility

Condition-level joined valid two-leg target markets: `741`.

Eligible under the previously frozen asset consistency requirement (`relative size error <=1e-4` on both exact `(condition_id, asset)` legs): `738`.

Ineligible: `3`:
- `2` size-mismatch conditions;
- `1` condition with a missing exact closed-position asset leg.

No condition was manually repaired, rescaled, or dropped after seeing its PnL.

## Aggregate allocation — 738 eligible conditions

- bounded closed-position realized PnL: `+$1,235.6250`
- matched-inventory realized PnL: `-$28,520.3859`
- unmatched-inventory realized PnL: `+$29,756.0081`
- aggregate allocation error: `+$0.0028`

By absolute component magnitude:
- matched component: `48.9399%`
- unmatched component: `51.0601%`

Condition medians:
- matched-inventory PnL median: `-$12.0628`
- unmatched-inventory PnL median: `+$20.0486`

Sign counts:
- matched: `290` positive / `446` negative / `2` approximately zero;
- unmatched: `440` positive / `295` negative / `3` approximately zero.

The near-zero aggregate allocation error is strong evidence that the exact asset-level allocation is internally consistent for the frozen high-consistency subset. It is not proof that these components represent total account economics.

## Frozen pair-cost partition

### Pair cost < 1.00

Eligible conditions: `291`.

- closed-position realized PnL: `+$10,930.0561`
- matched-inventory realized PnL: `+$10,573.2351`
- unmatched-inventory realized PnL: `+$356.8218`
- allocation error: `-$0.0008`

Absolute component magnitude:
- matched: `96.7354%`
- unmatched: `3.2646%`

Medians:
- matched PnL: `+$24.4030`
- unmatched PnL: `-$21.5463`

Signs:
- matched: `290` positive / `0` negative / `1` zero;
- unmatched: `112` positive / `178` negative / `1` zero.

This is the strongest result in the current historical evidence: when the frozen aggregate leg VWAP is below $1, the bounded closed-position economics are overwhelmingly accounted for by the matched inventory component at aggregate level.

This still does NOT prove a follower could execute both legs below $1 simultaneously. The prior timing study showed the first acquisition of the two legs is often separated by tens of seconds.

### Pair cost >= 1.00

Eligible conditions: `447`.

- closed-position realized PnL: `-$9,694.4311`
- matched-inventory realized PnL: `-$39,093.6210`
- unmatched-inventory realized PnL: `+$29,399.1864`
- allocation error: `+$0.0036`

Absolute component magnitude:
- matched: `57.0770%`
- unmatched: `42.9230%`

Medians:
- matched PnL: `-$45.7261`
- unmatched PnL: `+$44.2050`

Signs:
- matched: `0` positive / `446` negative / `1` zero;
- unmatched: `328` positive / `117` negative / `2` zero.

Thus the large positive reconciliation residual identified in the previous stage is now accounted for almost entirely by realized PnL allocated to unmatched inventory. Under the frozen terminology this is `unmatched_inventory_realized_pnl`, NOT directional alpha.

## BTC/ETH × horizon split

| Segment | Eligible | Closed PnL | Matched inventory PnL | Unmatched inventory PnL | Allocation error |
|---|---:|---:|---:|---:|---:|
| BTC 5m | 277 | +$2,104.6509 | -$21,004.9688 | +$23,109.6183 | +$0.0014 |
| BTC 15m | 90 | +$1,670.5827 | -$4,235.4953 | +$5,906.0778 | +$0.0002 |
| ETH 5m | 279 | -$3,567.7466 | -$2,242.3344 | -$1,325.4129 | +$0.0007 |
| ETH 15m | 92 | +$1,028.1380 | -$1,037.5874 | +$2,065.7249 | +$0.0004 |

BTC 5m and BTC 15m show large positive unmatched-inventory components on this frozen day; ETH 5m does not. This is descriptive evidence only and does not authorize a cross-segment strategy selection.

## What this stage establishes

1. The prior `UNEXPLAINED_RECONCILIATION_RESIDUAL` is not primarily a bookkeeping artifact on the high-consistency population; exact asset-level PnL allocation accounts for the bounded closed-position totals with negligible aggregate error.
2. In the frozen `<1` pair-cost regime, matched inventory accounts for almost all absolute aggregate PnL component magnitude and is strongly positive.
3. In the frozen `>=1` regime, matched inventory is strongly negative while unmatched inventory offsets a large part of that loss.
4. Bonereaper therefore cannot be reduced to one universal mechanism across all markets on this day: paired inventory and unmatched inventory play materially different economic roles depending on the predeclared pair-cost regime.

## What remains unknown

`unmatched_inventory_realized_pnl` is not yet identified as:
- intentional directional exposure;
- momentum / price-following alpha;
- stale-price exploitation;
- maker execution edge;
- reward/rebate economics;
- or copyable PnL.

The closed-position Data API also does not by itself establish total wallet economics, and historical BACKFILL does not establish follower observation latency.

The next research contract should study the source-time behavior of unmatched inventory (which leg receives the excess size, when that excess is added, and how it relates to external/Polymarket price movement) without outcome-conditioned threshold search. Prospective copyability must wait for LIVE_OBSERVED evidence.
