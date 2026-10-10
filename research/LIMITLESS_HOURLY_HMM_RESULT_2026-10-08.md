# Limitless hourly: fixed hidden Markov volatility shadow — 8 October 2026

**Decision:** this specified HMM is not a profitable candidate on the available historical paper replay. No promotion or tuning. The frozen hourly model, fees, thresholds, holdout, jobs and live controls remain unchanged.

## Reproducibility

The [protocol](LIMITLESS_HOURLY_HMM_PROTOCOL_2026-10-08.md) was committed before results. [Implementation](limitless_hourly_hmm_shadow.py) fits one two-state zero-mean Gaussian volatility HMM to 120 as-of closed Binance 1m returns, using the specified 20 EM iterations and priors. It changes only the probability at each already chosen first event. It reuses the first archived delayed book request, including failures, 3% buy fee, 3% hurdle and 10 USDC budget. Same [first-event baseline](LIMITLESS_HOURLY_EVENT_TRIGGER_RESULT_2026-10-08.md). Run [37747378560](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37747378560) succeeded at 2026-10-08 08:06 UTC (head `6ff8c3e0adc8a6e8d53324bdf05d63d54be56334`); output artifact 11536611248, ZIP digest `sha256:7c7e15bc6e709e9fc8e6a7a7bc448a09a09e970d5953ea9ab1cca9f0adb0680a`. Replay verified 96 source ZIP hashes, 162 conditions, 154 saved first event opportunities. [Post-row machine evidence](evidence/limitless_hourly_hmm_shadow_2026-10-08.json) includes run/artifact/as-of provenance.

| Phase | First events | HMM Brier / frozen | HMM paper fills | HMM settled paper PnL | Frozen same-event PnL |
| --- | ---: | ---: | ---: | ---: | ---: |
| Discovery | 97 | 0.213158 / 0.213828 | 57 | +113.185032 USDC | +119.599142 USDC |
| Old holdout | 57 | 0.192562 / 0.192389 | 32 | −151.089766 USDC | −152.665715 USDC |

Discovery HMM improves Brier by 0.000670, but loses 6.414110 USDC against the frozen same-event replay. Old holdout Brier worsens by 0.000172; its PnL improves by only 1.575949 USDC and remains deeply negative. Log loss: discovery 0.612471 versus 0.614225; holdout 0.559564 versus 0.559411. Scores use 97 and 55 observed binary resolutions respectively; two old-holdout payouts remain unscored. All 154 HMM inputs were valid; no input-failure skip.

Discovery: 21 no executable edge and 19 first-attempt depth/price failures; 57 filled, 32 positive settled, spanning 42 UTC-hour clusters. Its two largest wins total 75.063883 USDC, while PnL excluding those two is +38.121149 USDC. Old holdout: 9 no executable edge, 14 depth/price failures, 2 missing first requests; 32 filled, 9 positive settled, 23 UTC-hour clusters. Excluding its two largest wins produces −182.118566 USDC. Post-row recomputation matched all reported phase fills and PnL.

Median absolute probability shift versus frozen model: 0.002363 discovery and 0.001383 old holdout; maxima 0.036717 and 0.033801. Median filtered HIGH-state posterior: 0.245823 and 0.401564. Across fitted chains transition self-probabilities span 0.342404–0.969535 discovery, 0.625057–0.981895 holdout. This is a small change in the most relevant decision probability in most opportunities.

These are conditional, retrospective paper quotes, not actual fills or a fresh forward test. Old holdout has been repeatedly inspected by previous candidate research and no longer validates a selected improvement independently. The two-state variance HMM has no directional mean or order-flow signal. We have tested this one frozen specification, not rejected every hidden-state model. A new candidate would need a precommitted mechanism and untouched future data; fitting variants to the old holdout is not evidence of edge.
