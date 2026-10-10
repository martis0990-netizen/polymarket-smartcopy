# Limitless hourly: understand the old paper results before changing strategy

This research-only audit uses the frozen final hourly-v1 main state and report in artifact `11470560416` (ZIP SHA-256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`), with previously SHA-checked [Binance candle metrics](evidence/limitless_hourly_pair_candles_2026-10-07.json). [Machine evidence](evidence/limitless_hourly_loss_mechanism_2026-10-07.json) has 161 first-fill records, phase, source proof, decision-time direction/probability, prior volatility near the fill, and observed payout. The results below are paper quotes/fills, not live execution.

## First diagnose the original outcome

| Frozen cohort | Discovery: fills / winners / settled PnL | Old holdout: fills / winners / settled PnL |
| --- | ---: | ---: |
| MODEL | 19 / 9 / **+23.0855 USDC** | 10 / 1 / **−74.3787 USDC** |
| constant50 control | 89 / 25 / **+17.3098 USDC** | 43 / 7 / **−71.9924 USDC** |

The MODEL discovery gain depended on **two cheap long-shot winners** of +51.0712 and +35.1545 USDC. The other 17 MODEL fills summed to **−63.1402 USDC**. All six UTC-hour clusters that contain the ten MODEL holdout fills have negative aggregate PnL. Do not infer a positive expectation from the discovery total or treat those correlated BTC/ETH fills as ten independent experiments.

At the decision, compare the selected YES/NO side to the reference Binance price relative to the hour opening. This sign uses **decision-time** data; no later candle enters it.

| MODEL side at decision | Discovery: wins / fills; PnL | Old holdout: wins / fills; PnL |
| --- | ---: | ---: |
| Against reference direction | 2 / 11; +8.6440 USDC | **0 / 6; −49.6761 USDC** |
| With reference direction | 7 / 8; +14.4415 USDC | **1 / 4; −24.7026 USDC** |

This shows why a simple reversal bet is fragile in the observed holdout; it does **not** validate a momentum-only strategy either. Both direction groups lost in that period. MODEL entry probabilities assigned the selected sides a total of **9.66 expected wins** across 19 discovery fills (9 observed), but **4.78 expected wins** across ten holdout fills (one observed). The forecast's full-condition Brier score on old holdout was 0.1752; calibration of probabilities across *all* questions did not prevent poor economics on the selected traded subset. Expected edge computed using the saved forecast and eventual paper entry depth was **+16.7925 USDC** on the ten holdout fills; the observed settled PnL was **−74.3787 USDC**. This is an observed forecast/selection miss on a tiny sample, not a proof of a permanent regime effect.

The median *closed-candle* 30-minute realized-volatility proxy just before the first fill was **13.02 bp in MODEL discovery** and **24.71 bp in old holdout**. The model's own decision-time `sigma_1m` median also rose from **2.51 to 5.49 bp**. A more volatile period is an observable distinction, but the model did react in its volatility estimate; these numbers alone do not prove the volatility model was too low. The prior 30-minute metric was recorded shortly before the fill, which followed the decision, so it cannot be transplanted into a decision-time rule without recomputing it as of the decision.

## Two bounded, economically motivated checks

1. **Only keep MODEL fills on the side already favoured by the decision-time reference price.** This sign-only rule has no optimized threshold and keeps 8/19 discovery fills (+14.4415 USDC), but 4/10 old-holdout fills still lose **24.7026 USDC**.
2. **Symmetric probability recalibration:** fit the single slope `q = sigmoid(β · logit(p))` on all 104 resolved discovery decisions by minimizing binary log loss, with no PnL tuning; β = **0.71385**. Then retain only existing original fills when calibrated selected-side probability exceeds the original decision-time max buy price divided by 0.97 (the unchanged illustrative fee in contracts). This retains 11/19 discovery fills (+8.6440 USDC) and 7/10 old-holdout fills (**−57.8251 USDC**). Full-condition Brier score moves from 0.2059 to 0.2039 in fit-period discovery, but from 0.1752 to **0.1788** in old holdout. It fails as a fix. This checks only a subset of actual paper fills; it never fabricates fills for original NO_TRADE conditions.

**Research conclusion:** current evidence identifies two plausible failure mechanisms—dependence on rare long-shot payouts and miscalibration/selection under changing conditions—but does **not** identify a profitable rule that survives even the already inspected holdout. We should not optimize cutoffs against these ten losing trades or claim a positive strategy from twelve hypothetical paired book quotes. A useful next analysis on the existing archive is a causal decomposition of *all* decision conditions and executable quotes by time-to-expiry, distance to strike, volatility and price after fees, with a rule defined from probability/settlement mechanics before inspecting its PnL. If that still fails the old holdout, report the failure; a new prospective period would then be necessary to validate any changed strategy. The previous holdout has been examined repeatedly and cannot be relabeled independent evidence for a new rule. No collection, code path, fee, or threshold was changed here.

The caution about transferring probability calibration across domains and resolution horizons is consistent with [recent empirical calibration work](https://arxiv.org/html/2602.19520v2); that paper does not establish a Limitless edge.
