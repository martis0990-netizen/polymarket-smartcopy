# Limitless hourly: decision-time regime and forecast errors

## Scope

This is a descriptive check of **all 162 original hourly decisions**, not an optimized entry filter. Inputs are the immutable decision-book audit in [all-decisions evidence](evidence/limitless_hourly_all_decisions_2026-10-07.json) and the corresponding saved final market/episode state in main artifact `11470560416` (ZIP SHA256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`). Every reported opening, Binance reference price, model `sigma_1m`, forecast, venue midpoint, market end, and decision timestamp is known at the decision. The venue midpoint is a forecast comparator, **not an executable fill**.

For each resolved condition, define the proper-score difference `Brier(model) − Brier(book midpoint)`: positive means the book midpoint forecast was better on that outcome. Continuous explanatory features are decision-time one-minute volatility and absolute standardized distance from hour opening, `abs(reference/open − 1) / (sigma_1m × sqrt(minutes to expiry))`. There is no fitted volatility cutoff, PnL objective, or trade reclassification. [Row-level evidence](evidence/limitless_hourly_decision_regime_2026-10-07.json) includes conditions, phase, hour cluster, source artifact/line hash, features and score difference.

| Measurement | Discovery | Previously inspected holdout |
|---|---:|---:|
| Decisions / observed outcomes | 104 / 104 | 58 / 56 |
| Median seconds remaining | 1789 | 1788 |
| Full range, seconds remaining | 1777–1796 | 1759–1797 |
| Median decision `sigma_1m`, bp | 2.32 | 3.25 |
| Median absolute standardized distance from hour opening | 0.635 | 0.619 |
| Mean Brier(model) − Brier(midpoint) | −0.00285 | **+0.01728** |
| UTC-hour cluster bootstrap 95% interval of that mean | −0.01225 to +0.00752 | +0.00550 to +0.03056 |
| Spearman relation: log(volatility) versus Brier difference | +0.068 | +0.211 |
| Spearman relation: absolute standardized distance versus Brier difference | −0.100 | −0.087 |

The old holdout had higher median decision volatility, and its book midpoint gave a better full-condition Brier score. Both BTC and ETH had a positive model-minus-midpoint score difference in that later period (BTC +0.02461 over 26 resolved conditions; ETH +0.01092 over 30). Yet the within-period rank relations with volatility and standardized distance are weak. This does **not** establish that volatility caused the model's change in relative quality, nor that a retrospective volatility gate would yield positive PnL. A Brier difference on all conditions is not the economic result on selected offers.

The decision horizon is effectively fixed near 30 minutes, so these archives cannot compare an earlier versus later entry hour. Earlier work measured 30-minute realized volatility near a fill; that later measurement must not be used as a decision-time filter. The model's own `sigma_1m` here avoids that look-ahead, but contains too little evidence for a profitable regime rule. The 4,000-resample intervals draw whole UTC-hour clusters with fixed seed; they describe these historical samples only. The old holdout has been inspected repeatedly and is no longer independent for new rules.

## Implication

The hypothesis “only trade when volatility is low/high” remains unqualified. There is no new entry or PnL claim and no threshold chosen from the observed winners. Taken with the [first-book gap diagnostic](LIMITLESS_HOURLY_GAP_MECHANISM_2026-10-07.md) and the [chronological blend replay](LIMITLESS_HOURLY_WALKFORWARD_2026-10-07.md), these data do not presently identify a repeatable executable hourly taker edge. Keep the existing paper-only rules unchanged. Future validation of a different time horizon or a new model would require a fixed protocol and genuinely new observations.
