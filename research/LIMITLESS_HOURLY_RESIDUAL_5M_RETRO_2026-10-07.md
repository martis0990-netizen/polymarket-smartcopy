# Limitless hourly: five-minute Binance residual, retrospective check

**Result: do not promote this candidate.** This is a read-only research replay of the stopped paper collection. It uses Limitless hourly decision books and public Binance spot M1 candles, with no new order, collector, fee, threshold, holdout or workflow change. The hypothesis was proposed after the prior holdout results had been inspected, so the late period below is a retrospective comparison, not an independent prospective test.

## Sources and coverage

The final successful main [capture run 37588187303](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37588187303), artifact `11470560416` (ZIP SHA256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`), supplies the frozen hourly episodes, settlement and market metadata. All 60 earlier main ZIPs in the [104-decision market reconciliation](evidence/limitless_hourly_discovery_holdout_market_2026-10-07.json) were downloaded and matched to their published SHA256. The additional early segment `11381034166` contains the final two discovery decisions; the 36 later main ZIPs were also digest-checked. PR smoke and cancelled runs are excluded. The ZIP identities and every decision/reference proof are in [machine evidence](evidence/limitless_hourly_residual_5m_retro_2026-10-07.json).

| Phase | Decisions with causal reference and book | Resolved for scoring | Independent UTC hours |
| --- | ---: | ---: | ---: |
| Discovery | 104/104 | 104 | 55 |
| Later period | 58/58 | 56 | 31 |

For each decision, the exact original M1 REST response was matched to the recorded reference receipt before the decision. The six consecutive M1 bars end before the request; their first and last closes are five minutes apart. The original book was matched by slug, YES token, line number and SHA256, and the independently calculated midpoint agrees with the previous reconciliation. Two later decisions have no observed settlement and are excluded from forecast scores. The frozen source model's separate paper replay reproduced discovery `+23.085530854` USDC and later `−74.378700028` USDC, including the original first eligible execution attempt. These source trades are not a funded v2 account.

## One-parameter candidate

The exploratory feature is `x = log(close_last / close_five_minutes_earlier) / (sigma_1m * sqrt(5))`. The forecast is `logit(p) = logit(q) + beta * x`, where `q` is the observed decision-book midpoint. A single nonnegative coefficient represents the stated continuation hypothesis. It was fit by logistic loss on the 104 discovery outcomes with a fixed unit-strength L2 penalty; no horizon, threshold, sign or penalty sweep was performed. The derivative of the discovery objective at `beta=0` is `+5.9672039567`, so the convex constrained optimum is **exactly beta=0**.

| Phase | Market Brier | Candidate Brier | Market log loss | Candidate log loss |
| --- | ---: | ---: | ---: | ---: |
| Discovery | .208709 | .208709 | .612382 | .612382 |
| Later period | .157924 | .157924 | .478825 | .478825 |

With `beta=0`, the candidate equals the market midpoint. The unchanged 3% paper contract fee and 3% hurdle leave no candidate entries: **zero settled trades, zero paper PnL and cash 100 USDC** in each separately funded phase. This is abstention, not evidence of profitability or an economic comparison based on fills. For reference, an arbitrary `beta=1` on the later 56 resolved outcomes had Brier `.171295` versus the market's `.157924`; that illustration was not fit or selected and is not a second strategy.

## Decision

The specific positive five-minute continuation correction has no estimated incremental signal on the early sample and requires no new forward paper run. A negative sign, another lookback, a structure label, or a different regularizer would be a new hypothesis. Choosing one after these results would reuse the already observed outcomes. Existing collection remains stopped; nothing here changes the frozen hourly v1, inventory v2 or execution rules.
