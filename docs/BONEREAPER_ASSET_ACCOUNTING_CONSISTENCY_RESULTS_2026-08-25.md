# Bonereaper asset-level accounting consistency — 2026-08-25 UTC

Status: RESULT UNDER FROZEN CONSISTENCY CONTRACT

Contract: `docs/BONEREAPER_ASSET_ACCOUNTING_CONSISTENCY_CONTRACT.md`

Inputs are the already-frozen target-family activity and same-day bounded closed-position evidence.

## Exact `(condition_id, asset)` coverage

- activity asset keys: `1,515`
- closed-position asset keys: `1,499`
- joined asset keys: `1,491`
- activity-only keys: `24`
- closed-only keys: `8`
- duplicate closed `(condition_id, asset)` keys: `1`

No missing joins were imputed.

## Size consistency

Relative size error is:

`abs(closed_total_bought - activity_buy_size) / max(closed_total_bought, activity_buy_size)`

Across 1,491 exact asset joins:

- median: `5.22635e-08`
- p90: `2.63469e-07`
- p99: `1.14008e-06`
- share `<=1e-6`: `98.7257%`
- share `<=1e-4`: `99.8659%`
- share `<=1e-2`: `99.8659%`

Thus activity `size` and closed-position `totalBought` are effectively identical for nearly all joined assets at the predeclared diagnostics.

## Price consistency

Absolute price error is:

`abs(closed_weighted_avg_price - activity_buy_vwap)`

Across the same exact joins:

- median: `5.93459e-05`
- p90: `9.79222e-05`
- p99: `1.10870e-04`
- share `<=1e-6`: `0.3353%`
- share `<=1e-4`: `92.0858%`
- share `<=1e-2`: `99.8659%`

The price fields show small systematic rounding/representation differences relative to the source activity VWAP, but nearly all are within one basis-point-like absolute probability-price scale (`1e-4`).

## Frozen family splits

| Segment | Joined assets | Median relative size error | p99 relative size error | Size error <=1e-6 | Median abs price error | p99 abs price error | Price error <=1e-4 |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTC 5m | 560 | 3.233e-08 | 5.660e-07 | 99.6429% | 6.018e-05 | 1.1614e-04 | 91.4286% |
| BTC 15m | 183 | 4.317e-08 | 4.470e-07 | 100.0000% | 5.860e-05 | 1.1035e-04 | 90.7104% |
| ETH 5m | 561 | 9.019e-08 | 9.969e-07 | 98.9305% | 5.850e-05 | 1.0728e-04 | 92.5134% |
| ETH 15m | 187 | 9.409e-08 | 2.138e-06 | 94.1176% | 5.965e-05 | 1.0618e-04 | 94.1176% |

## Disclosed material size mismatches

Two exact asset joins dominate the relative-size mismatch tail and are retained as evidence rather than corrected.

1. ETH 15m condition `0x44a361fa7785309f2628c44bc48ded9d665382fad781b7e342de9034379c9028`
   - activity buy size: `458.65`
   - closed totalBought: `917.3`
   - relative size error: `0.5`
   - activity VWAP: `0.9417898`
   - closed avgPrice: `0.9417`
   - two closed rows share this condition/asset key

2. BTC 5m condition `0xb573eb5dfc8f2de2602eb1ce93ede4fc301a4cb96ff4bc68acfe6f30d390b08a`
   - activity buy size: `1229.487183`
   - closed totalBought: `1389.4871`
   - relative size error: `0.11515`
   - activity VWAP: `0.24011669`
   - closed avgPrice: `0.2697`

Possible explanations such as duplicate API semantics, inventory acquired outside the frozen activity day, transfers, or other boundary effects are not resolved in this stage.

## Allowed conclusion

The Data API activity BUY quantities and closed-position accounting are sufficiently consistent at exact asset level to support a separately frozen matched-vs-unmatched realized-PnL allocation on the high-consistency subset.

This document does not itself allocate PnL and does not label unmatched inventory as directional alpha.
