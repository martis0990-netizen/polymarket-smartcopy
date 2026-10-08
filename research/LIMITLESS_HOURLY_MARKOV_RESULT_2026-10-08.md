# Limitless hourly: observable Markov volatility pilot

As of 2026-10-08 07:55 UTC (10:55 Moscow). [Protocol](LIMITLESS_HOURLY_MARKOV_PROTOCOL_2026-10-08.md) was committed as `77aa5c8eb09269fb500191638d3a0714f09ed0f3` before replay. This is a two-state **observable** Markov chain for LOW/HIGH one-minute volatility, not a fitted hidden Markov model. It changes only the projected integrated variance in the same zero-drift hourly probability formula. Transition counts use 120 available closed 1m returns with fixed Laplace smoothing; no outcome/PnL-based fitting.

All 96 prior capture ZIPs passed SHA256 checks. The [main PR job](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37745936693) succeeded on head `80c75c3dc226052ebdb2ba8cff61baf827530a44`. The event moment, first decision book and first delayed attempt were identical to the earlier frozen event replay. This comparison is conditional on **154 first opportunities** (97 discovery, 57 old holdout); eight other conditions had no saved first opportunity and cannot be scored as Markov entries.

| Same-event measure | Discovery | Previously inspected holdout |
| --- | ---: | ---: |
| Scored binary decisions | 97 | 55 (two unresolved) |
| Markov Brier / frozen Brier | .2138266 / .2138278 | **.1925885 / .1923893** |
| Markov log loss / frozen log loss | .6143137 / .6142246 | **.5600384 / .5594114** |
| Markov paper fills / wins | 62 / 33 | 37 / 11 |
| Markov settled paper PnL, USDC | +94.902147654 | **−152.212447455** |
| Frozen first-event PnL on same rows, USDC | +119.599141550 | **−152.665714556** |
| Markov PnL without best two winners, USDC | +20.113984330 | −183.174716711 |

The old holdout PnL improved by only **0.453267101 USDC** while both Brier and log loss worsened. Discovery PnL fell by **24.696993896 USDC**. Median absolute change in probability was about .00056 in discovery and .00051 in holdout; no successful Markov entry changed side relative to the frozen first-event choice. Median LOW→LOW and HIGH→HIGH one-minute transition probabilities were about .53 in discovery and .52 in holdout, so the observed one-minute regime rarely persisted long enough to materially change the remaining hourly variance estimate. This is an inference from this fixed model's measured transitions, not a general claim against all Markov models.

**Decision:** This prespecified two-state volatility chain does not improve the conditional hourly model in a useful way and does not meet the user's historical-positive-holdout gate. Do not tune states, training windows or filters on this reused holdout, and do not promote the paper candidate. The sample and repeated inspection do not support a claim about HMMs generally; a directional/HMM proposal would need its own causal input, fixed protocol and independent evaluation.

Full [machine evidence](evidence/limitless_hourly_markov_shadow_2026-10-08.json) contains 154 row-level as-of source IDs, hashes, probabilities, transition matrices, first attempts and settlements. The original CI [artifact](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37745936693/artifacts/11535802844) is 11535802844, ZIP SHA256 `11b0f4a684c84f1beda1975566df0f1db81b27ef2be8f17f8335aefd4e675409` (retention through 2026-11-07). No source capture, fees, live orders, collection workflow or frozen production model changed.
