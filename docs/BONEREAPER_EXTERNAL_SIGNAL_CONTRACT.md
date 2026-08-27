# Bonereaper external-market signal study — recovered pilot specification

Status: **DESCRIPTIVE PILOT — NOT AN EVIDENCE-GATED FROZEN CONTRACT**

## Provenance incident

The pilot artifact names contract commit `7080225c0b0bbeabcac251a5e7c244d83c4e806b`
and correction commit `af9effce55fe7543749c94585ebbfbfafa000987`, but neither object exists in
the recovered repository object database or any fetched branch. The code, tests, immutable input
hashes, and result artifacts survived; the claimed pre-result Git boundary did not.

Consequently, the August 26 output is retained only as hypothesis-generating descriptive evidence.
It must not satisfy a roadmap gate, authorize implementation parameters, or be presented as a
prospectively frozen result. A new independent-market study requires a new contract committed
before its first eligible observation.

Purpose: test whether Bonereaper's active buys are better explained by an external BTC/ETH
fair-value signal than by a conventional technical indicator calculated only from past prices.
The study follows the already-observed hybrid execution result: active `TAKER` fills are the
primary signal population; passive `MAKER` fills are a secondary placement/inventory diagnostic.

Before this contract, public internet research and official documentation were reviewed. One
complete Binance 5-minute-window response for BTCUSDT and ETHUSDT was fetched only to verify that
the official 1-second kline endpoint served the required historical interval. The response was
not preserved, joined to wallet fills, or used to compute any signal metric before the rules below
were frozen.

## Prior evidence and fixed inputs

Wallet:

- `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`

Immutable Polymarket inputs:

- Stage 3A live activity: `77` rows, SHA256
  `e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb`
- complete four-market Data API trade tape: `5,467` raw rows, SHA256
  `308e78519728c4d43b71427596d4136fdc15c4c9e1ef97e1ec046ac4f2cf8068`
- maker/taker decoded rows: `77` rows, SHA256
  `a26b9ba714708173ba830fd4e621d1524bcf4dafd761818ce4c6fcb27b2bb901`
- exact markets: BTC and ETH 5-minute windows beginning `2026-08-26T12:55:00Z`, and BTC
  and ETH 15-minute windows beginning `2026-08-26T12:45:00Z`

The complete Polymarket tape contains exactly `107` Bonereaper BUY rows across those markets.
Those historical rows may reconstruct inventory from near market open, but only the frozen 77
Stage 3A rows retain `LIVE_OBSERVED` provenance and on-chain maker/taker binding.

## Why the opening reference is a TWAP

Polymarket's August 7, 2026 rule change specifies that crypto Up/Down markets use Chainlink TWAP
for both the opening price to beat and final settlement:

- 5-minute markets: 30-second TWAP
- 15-minute and 4-hour markets: 60-second TWAP

Historical Chainlink TWAP replay is not available from public RTDS. Binance spot is therefore a
declared proxy, not mislabeled as the settlement oracle. The proxy opening barrier is the
arithmetic mean of Binance 1-second close prices in `[market_start - window, market_start)` using
30 or 60 seconds as applicable.

## External evidence collection

Collect official Binance Spot API klines for `BTCUSDT` and `ETHUSDT`:

1. `1s` bars from `2026-08-26T12:44:00Z` through `2026-08-26T13:00:00Z`.
2. `1m` bars from `2026-08-26T10:00:00Z` through `2026-08-26T13:00:00Z`.
3. Use explicit `startTime`, `endTime`, and `limit`; preserve the complete raw response envelope,
   URL parameters, collection time, row count, and SHA256 before analysis.
4. Require unique, strictly increasing open times and the canonical Binance kline field count.
5. Require contiguous 1-second bars for every market barrier window and every strict-pre signal
   lookup. Missing bars make the affected metric ineligible rather than silently forward-filled.
6. Refuse to overwrite an existing output directory. A later re-fetch is a new artifact.

## No future leakage

For a wallet source second `t`, every external feature uses information no later than the close of
the Binance bar at `t-1`.

- The current proxy spot is the 1-second close at `t-1`.
- An `Ns` return compares that close with the close at `t-1-N`.
- A 1-second RSI uses returns ending at `t-1`.
- Minute indicators use only complete 1-minute bars whose close time is strictly before `t`.
- Same-second Binance bars are forbidden.

## Independent signal episodes

Raw partial fills must not inflate the sample. Group frozen Stage 3A rows sharing exact
`condition_id`, `outcome`, and `source_second` into one episode. Sum source size and source
notional; maker/taker role must be identical inside an episode or the episode is `MIXED_ROLE` and
is excluded from role-specific gates.

Primary population: schema-corrected `TAKER` episodes. These orders crossed resting liquidity and
are the cleanest available evidence of an active decision.

Secondary populations:

- `MAKER` episodes;
- all Stage 3A episodes;
- the complete 107-row historical tape, grouped by condition/outcome/second, for cumulative
  inventory-path diagnostics only.

## Frozen candidate signals

All directional signals are `Up`, `Down`, or `None` at exact zero.

### 1. Opening-barrier distance — primary hypothesis

- `barrier_distance_bps = 10,000 * ln(strict_pre_spot / proxy_opening_twap)`
- direction is `Up` when positive and `Down` when negative

This is the simplest proxy for a fair-value engine on an Up/Down contract.

### 2. Short-horizon momentum

Report strict-pre log-return directions over `5s`, `15s`, `30s`, and `60s`. The frozen primary
technical-analysis comparator is `15s` momentum; other horizons are robustness descriptions and
cannot replace it after results.

### 3. One-second RSI(14)

Use Wilder RSI over the last 14 completed one-second close-to-close changes. Direction:

- `Up` when RSI is above 50
- `Down` when RSI is below 50
- `None` at exactly 50

The conventional 30/70 overbought/oversold flags are reported separately but do not reverse the
direction. A reversal interpretation would be a different hypothesis.

### 4. Closed-minute RSI(14)

Compute Wilder RSI from completed Binance 1-minute closes. Use the same 50 direction boundary and
report 30/70 flags.

### 5. Closed-minute EMA trend

Compute standard recursive EMA(5) and EMA(20) over completed 1-minute closes. Direction is `Up`
when EMA(5) > EMA(20), `Down` when lower, and `None` when equal.

### 6. Binance aggressive-flow imbalance

Over `[t-15, t)`, sum total base volume `V` and taker-buy base volume `B` from 1-second bars:

`flow_imbalance = (2 * B / V) - 1`

Direction is `Up` when positive and `Down` when negative. This tests order flow rather than a
chart indicator.

### 7. BTC-leads-ETH diagnostic

For ETH episodes only, compare the bought outcome with BTC's strict-pre 15-second momentum. This
is secondary and cannot replace the ETH-local signals.

### 8. Volatility-normalized barrier score

Estimate strict-pre one-second log-return volatility over the preceding 60 seconds. With seconds
remaining `tau`, report:

`z = ln(strict_pre_spot / proxy_opening_twap) / (sigma_1s * sqrt(max(tau, 1)))`

and `normal_cdf(z)` as a diagnostic fair probability. This deliberately simplified digital-price
proxy ignores drift, settlement TWAP mechanics, jumps, and cross-venue basis; it has no primary
gate.

## Alignment metrics

For each candidate and population, report:

- eligible episode count and source notional;
- episode-direction alignment share;
- source-notional-weighted alignment share;
- BTC and ETH splits;
- maker and taker splits;
- opposite-inventory and non-opposite splits using the already-frozen strict-prior inventory rule.

Also report discordant episodes where opening-barrier direction and the candidate indicator point
opposite ways. Their bought-side alignment is the only allowed descriptive comparison of
incremental information in this four-market case study.

## Frozen gates

Primary external fair-value gate, over eligible `TAKER` episodes:

- `SUPPORTED_DESCRIPTIVELY` if opening-barrier direction aligns with at least `70%` of source
  notional and at least `60%` of episodes;
- `NOT_SUPPORTED` if notional alignment is at most `55%` or episode alignment is at most `50%`;
- otherwise `INCONCLUSIVE`.

Technical-indicator candidate gate, evaluated separately for 15-second momentum, RSI(14) 1s,
RSI(14) 1m, EMA(5/20) 1m, and 15-second flow imbalance:

- `SUPPORTED_DESCRIPTIVELY` only if overall taker notional alignment is at least `70%`, episode
  alignment at least `60%`, and both BTC and ETH taker-notional alignment are at least `60%`;
- `NOT_SUPPORTED` if overall notional alignment is at most `55%` or episode alignment is at most
  `50%`;
- otherwise `INCONCLUSIVE`.

No candidate may be selected because it wins a post-hoc horizon or threshold sweep.

## Rebate economics — separate hypothesis

The role study measured gross taker fees of `$7.883820` in the 77-row sample. Report hypothetical
net fees at the public maximum `50%` taker rebate and at the publicly alleged, but not officially
verified, `80%` account-specific rebate. This arithmetic is an economic sensitivity only. It must
not be presented as proof that Bonereaper actually received 80% during this interval.

## Interpretation limits

This is one 99-second live-observation interval and four overlapping contracts, not four thousand
independent markets. A supported result identifies compatibility with a signal family, not the
exact exchange, oracle, formula, indicator parameters, or order-placement logic used by
Bonereaper. A broader prospective multi-market capture is required for confirmation and for any
copyability rule.
