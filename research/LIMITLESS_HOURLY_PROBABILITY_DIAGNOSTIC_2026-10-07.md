# Limitless hourly: probability and half-hour price diagnostic

**Frozen data.** Final successful main [capture 37588187303](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37588187303), artifact `11470560416`, ZIP SHA256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`, 2026-10-07 08:30:08 UTC. Collection remains stopped. The state and saved `hourly_paper_report.json` recompute identically with current `HourlyPaper`. No trading rule, sizing, fee or holdout changed. [Machine evidence](evidence/limitless_hourly_probability_audit_2026-10-07.json) provides all 160 resolved decision rows, market book proofs for holdout, 56 later closed 1h candle proofs, and all 36 source ZIP identities.

## 1. Probabilities at every resolved decision

| Phase | Resolved decisions | UTC hour clusters | Frozen model Brier | Contemporaneous market-mid Brier |
| --- | ---: | ---: | ---: | ---: |
| Discovery | 104 | 55 | .205863 | Not fully matched |
| Holdout | 56 | 31 | .175204 | .157924 |

The holdout contains 58 decisions, but the last two have no observed resolution in the final checkpoint; neither enters these scores. The frozen model had lower squared error than market midpoint on 22 of 56 resolved decisions and higher error on 34. The paired Brier difference (model minus market) is **+.017279**. Exploratory bootstrap over the 31 UTC hour clusters (10,000 resamples, fixed seed) gives [.00548, .02966]; this conditional interval does not establish performance in a future market regime. Market midpoint is a probability comparison, **not** a fill.

The economic selection is materially worse than the all-decision score: among the ten settled MODEL entries, model Brier **.225680** versus midpoint **.158519**; among 45 resolved NO_TRADE decisions, model **.167239** versus midpoint **.161030**. The one resolved skipped candidate has still smaller errors and is excluded from both groups. These are descriptive, post-selection slices; they cannot establish a new entry filter. The previous [all-trade audit](LIMITLESS_HOURLY_ALL_TRADES_AUDIT_2026-10-07.md) measured 10 holdout fills at −74.379 USDC. Neither a respectable Brier relative to an unconditional .25 forecast nor a large apparent gap between model and market guarantees a fee-adjusted tradable edge.

## 2. From the half-hour reference to the close

For every one of the 56 resolved holdout decisions I found a Binance 1h candle captured *after* that hour ended. Each candle's open matches the episode open and its close direction matches the observed Limitless binary payout (56/56). Binance's [kline response schema](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market) identifies indices 0/1/4/6 as open time/open/close/close time. The evidence records source artifact, raw line and SHA256; a sampled line hash was independently reproduced.

In **44/56**, the final close was on the same side of the hour open as the half-hour reference. The frozen model's average probability for that continued side was **.729**, versus observed **.786**. Thus a blanket statement that the model is overconfident in trend continuation is unsupported. Yet it often bought the apparently cheap *opposite* outcome and lost; selection on model-versus-book disagreement is the more immediate failure mode.

As a volatility check, the realized reference-to-close log return divided by the model's stored `sigma_1m * sqrt(remaining minutes)` has sample standard deviation **1.752** across 56 symbol-hours. Two values around **−7.15 and −7.74** occur together at **2026-10-07 01:00 UTC** (BTC and ETH in one shock hour); neither produced a MODEL fill. Excluding that single hour only for attribution leaves standard deviation **.996** across 54 rows. This small, dependent sample does not show a pervasive volatility-scale error or validate Gaussian tails; the shock also cannot explain the ten losing entries. Any future tail model needs prospective validation.

## Interpretation and next gate

The first concrete weakness is that the **book midpoint predicted outcomes better than our frozen probability model** in the observed holdout, especially on selected entries. The hour-level direction often persisted, so apparently cheap counter-direction contracts were not necessarily bargains. Keep the stopped experiment and its holdout immutable. A replacement probability estimate, selection rule, structure/ATR label or maker execution scheme requires a documented new version and a new forward evaluation; tuning it against these 56 conditions would recycle the test set. Actual queue fills and Limitless execution remain unobserved.
