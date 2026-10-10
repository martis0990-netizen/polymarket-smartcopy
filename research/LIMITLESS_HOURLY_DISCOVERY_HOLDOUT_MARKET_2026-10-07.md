# Hourly Limitless: market baseline across discovery and holdout

This read-only continuation reconciles the final successful main state ([run 37588187303](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37588187303), artifact `11470560416`, ZIP SHA256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`, 2026-10-07 08:30:08 UTC) with the earlier [PR #54 raw entry-quality audit](https://github.com/martis0990-netizen/polymarket-smartcopy/pull/54). That audit matched 102 discovery decisions to their original books and archives. The final discovery state has **104** resolved decisions: the remaining BTC and ETH decisions at 2026-10-05 23:30 UTC are in subsequent successful main artifact `11381034166` (ZIP SHA256 `52bf2f2e2dc100e114c514da44fa69a6b58235c0d2124bad56e96cab3159a460`). For both I checked that the decision book immediately precedes its `paper_decision` event, matches slug and YES token, and contains valid YES/NO bids and asks. All previous 102 conditions exactly match the final state's probability, outcome and MODEL status. The [machine evidence](evidence/limitless_hourly_discovery_holdout_market_2026-10-07.json) contains 104 book fingerprints, archive lineage and comparison metrics. The 102 earlier source ZIPs were verified in PR #54; they were not downloaded anew for this continuation.

| Phase | Resolved decisions | UTC hours | MODEL Brier | Decision market-mid Brier | Difference MODEL − market |
| --- | ---: | ---: | ---: | ---: | ---: |
| Discovery | 104 | 55 | .205863 | .208709 | −.002846 |
| Holdout | 56 | 31 | .175204 | .157924 | +.017279 |

The earlier [probability diagnostic](LIMITLESS_HOURLY_PROBABILITY_DIAGNOSTIC_2026-10-07.md) had only the 56 holdout midpoint matches available; its statement that discovery midpoint coverage remained incomplete is **superseded** by this 104/104 reconciliation. Both model and market have lower absolute Brier in holdout than discovery, but **the market improved more**. The change in model-minus-market Brier is +.020125. An exploratory 10,000-draw bootstrap resampling whole UTC hours *within each phase* gives [.00500, .03633] for that change. Adjacent short market regimes and same-hour BTC/ETH dependence preclude a general predictive inference from this interval.

| Selected MODEL entries | Discovery | Holdout |
| --- | ---: | ---: |
| Settled paper entries | 19 | 10 |
| Mean model advantage over decision market midpoint on bought side | .0925 | .0884 |
| MODEL Brier on those entries | .1690 | .2257 |
| Market-mid Brier on those entries | .1731 | .1585 |
| Paper PnL, same frozen accounting | +23.086 USDC | −74.379 USDC |

At the **same MODEL paper fills**, treating the decision market midpoint as an alternative probability estimate gives expected PnL **−15.868 USDC** for 19 discovery entries and **−6.082 USDC** for 10 holdout entries, while frozen MODEL probabilities imply **+29.701** and **+16.792**, respectively. The market benchmark judges 16/19 and 8/10 selected entries negative after their observed execution price and modeled contract fee. These values do not backtest a market-mid trading strategy: a decision midpoint is neither a tradable price nor ground truth, and changing the probability would change admissions. Their purpose is to expose how much of the asserted edge rests on disagreement with the book.

The *size* of the model-market gap on selected entries was similar in both phases. Treating a larger positive gap as reliable edge is therefore unsupported. Discovery profit is highly concentrated in two outcomes, and neither these Brier slices nor paper REST-book fills establish execution profit. This is a relative forecast comparison, not a new bet-sizing strategy or an attempt to optimize a cutoff on holdout.

**Decision:** Keep the collector stopped and current holdout frozen. The existing market-blend50 shadow in [PR #54](https://github.com/martis0990-netizen/polymarket-smartcopy/pull/54) is already a distinct prospective challenger; its sparse later paper entries did not establish an advantage. Any further model, structure/ATR rule or market-residual threshold must be specified as a new version before a new forward sample. None is promoted from this retrospective diagnosis. No fee, workflow, state, portfolio or live-trading change was made.
