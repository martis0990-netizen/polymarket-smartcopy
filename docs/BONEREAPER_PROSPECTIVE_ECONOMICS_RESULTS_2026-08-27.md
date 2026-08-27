# Bonereaper prospective economics v1 — first clean result

Status: **COLLECTING — 2/30 PAIRED CONDITIONS**

## Bound evidence

- bundle: `bonereaper-prospective-bundle-v5-20260827-01`
- bundle manifest SHA256:
  `3748dbd327adbdfeea8506bcb8f747f1831b721afe3ea782933d82da00b69160`
- decoded receipt rows SHA256:
  `1cbbe07f740682e1f6542d1ed70d7d2b8b63a9099a3366382aa3e3b1bff2ab31`
- contract commit: `e1cd5f307185ee564758cf296385933027ce3889`
- analyzer commit: `7f7b60462aa2970415a67efb99bece7ae47ffb7b`
- coverage: 34 decoded rows, 34 exact bound rows, zero unbound exclusions

The result uses FIFO Up/Down allocation, integer receipt amounts and decoded on-chain fees.  It
does not infer a merge or realized PnL.

## Pair economics

Nine FIFO chunks matched 141.670726 complete pairs in two independent current-market conditions.
Every matched unit cost more than `$1`, both before and after decoded fees.

| Market | Matched units | Gross pair cost | After-fee pair cost | After-fee edge |
|---|---:|---:|---:|---:|
| ETH 5m | 30.670726 | 1.23794 | 1.24911 | -$7.64040 total |
| BTC 5m | 111.000000 | 1.03778 | 1.04636 | -$5.14555 total |

The individual after-fee chunk costs ranged from `1.02037` to `1.31632`.  Matched size by role
composition was:

- maker + maker: `9.670726`;
- maker + taker: `127.00`;
- taker + taker: `5.00`.

This clean interval does **not** support the simple explanation that Bonereaper's completed pairs
are primarily a deterministic sub-$1 arbitrage.  The stopping rule is not met, so it also cannot
establish that expensive pairs dominate generally.

## Residual directional inventory

| Market | Residual side | Units | Fee-adjusted cost | Mean unit cost |
|---|---|---:|---:|---:|
| Current ETH 5m | Up | 335.480384 | $314.9674 | 0.93885 |
| Current BTC 5m | Down | 83.000000 | $9.9905 | 0.12037 |
| Following ETH 15m | Up | 72.000000 | $35.8180 | 0.49747 |
| Following BTC 5m | Up | 1,562.200000 | $787.5780 | 0.50415 |
| Following ETH 5m | Down | 31.000000 | $15.7323 | 0.50749 |

The three following-market positions were entered before their nominal opens and had no observed
opposite leg in this bundle.  The largest position was BTC `Up`, consistent with the previously
identified Binance-aligned/Chainlink-discordant pre-open episode.

## Fee-adjusted markout

| Role | Horizon | Eligible fills | Eligible size | Markout/unit | Markout USDC |
|---|---:|---:|---:|---:|---:|
| Maker | 10s | 6 | 126.781836 | -0.02039 | -2.58449 |
| Maker | 30s | 11 | 223.821836 | -0.05472 | -12.24746 |
| Maker | 60s | 11 | 223.821836 | +0.04583 | +10.25796 |
| Taker | 10s | 23 | 2,143.2 | -0.00975 | -20.88975 |
| Taker | 30s | 17 | 1,776.0 | -0.03312 | -58.81579 |
| Taker | 60s | 6 | 542.0 | -0.04539 | -24.59938 |

The aggregate hides material condition differences.  For example, ETH-current taker markout was
slightly positive at all three horizons, while BTC-current taker markout was strongly negative.
Maker 60-second markout turned positive mainly because the BTC-current maker fills appreciated.
These values are descriptive and are not independent-condition significance tests.

## Updated mechanism inference

The evidence is more consistent with:

1. take a sizeable directional position when the external signal has conviction;
2. acquire some complementary inventory through maker or taker execution;
3. accept a completed-pair cost above `$1` when the second leg reduces a larger directional risk;
4. retain substantial unmatched exposure when the model still favours one outcome.

For our own algorithm, pair cost below `$1` should be treated as an opportunistic bonus, not the
core assumption.  A candidate hedge must instead be evaluated against the expected value and tail
risk of the remaining directional inventory, with maker and taker adverse selection modelled
separately.

## Limits and next evidence

- only two conditions contain complete pairs; target is 30;
- the bundle ends before many 30/60-second targets, reducing markout coverage;
- markout is public-book mid, not executable liquidation PnL;
- settlement outcome and on-chain merge evidence are outside this contract;
- cumulative inventory before the bounded capture is not reconstructed here.

The next bundles should extend post-fill coverage while keeping the same frozen horizons and FIFO
rules.  Settlement and merge evidence require separately frozen analyses.

