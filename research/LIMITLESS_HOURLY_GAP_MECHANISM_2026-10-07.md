# Limitless hourly: does the venue book catch up to the Binance forecast?

## Question

The prior [chronological blend replay](LIMITLESS_HOURLY_WALKFORWARD_2026-10-07.md) did not survive the previously inspected holdout. A narrower diagnostic asks whether a signed forecast gap `p_model − YES_book_midpoint` at a decision predicts the **next observed** public YES-book midpoint movement toward the model. A positive relation would be consistent with a venue that temporarily lags the reference. It would not establish an executable trade.

This diagnostic uses the same 162 unique hourly decisions in 96 SHA256-verified main ZIPs, the decision-book line and the first subsequent eligible book request after the original 1.5-second wait. The previously published [all-decisions evidence](evidence/limitless_hourly_all_decisions_2026-10-07.json) established exact match between each decision and its raw book; the [walk-forward evidence](evidence/limitless_hourly_walkforward_2026-10-07.json) identifies first-attempt lines. The final archive is artifact `11470560416`, ZIP SHA256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`. The row-level [gap evidence](evidence/limitless_hourly_gap_mechanism_2026-10-07.json) retains condition, phase, hour cluster, both probabilities, book observations, source artifact and line hashes.

For each valid pair, calculate `sign(p_model − initial_midpoint) × (first_attempt_midpoint − initial_midpoint)`. Positive means that the subsequent venue midpoint moved toward the model. No selection by future payout, profit or gap size was applied. The first request is a book in 160 cases, all within the original 30-second expiry; two final, unresolved NO_TRADE conditions have no subsequent request in the retained capture. These books arrived a median of 17.7 seconds (discovery) and 17.6 seconds (old holdout) after the decision. YES token identity was checked against the saved market state.

## Observations

| Measure | Discovery | Previously inspected holdout |
|---|---:|---:|
| Decision/valid first-book pairs | 104/104 | 58/56 |
| Mean absolute model–midpoint gap | 3.58¢ | 3.73¢ |
| Median initial bid–ask spread | 4.8¢ | 4.5¢ |
| First midpoint moved toward/away/unchanged | 43/52/9 | 19/29/8 |
| Mean signed first midpoint movement toward model | **−0.65¢** | **−0.48¢** |
| UTC-hour cluster bootstrap 95% interval for that mean | −1.20¢ to −0.14¢ | −1.42¢ to +0.53¢ |
| Regression slope, midpoint change on signed gap | −0.101 | −0.177 |
| Resolved conditions on which model / midpoint had lower Brier loss | 60/44 | 22/34 |

The interval resamples complete UTC-hour clusters 4,000 times with a fixed random seed; it describes sampling variation within these historical periods, not an independent confirmatory test. Model and market forecasts were evaluated on all resolved conditions. In discovery, the model has a small full-condition Brier advantage, yet the next venue midpoint moved *away* from it on average. In the old holdout the midpoint also has the better Brier score, consistent with the earlier audit. Median half-spreads were about 2.4¢ and 2.3¢ respectively, larger than these sub-cent average moves. A midpoint movement is neither a tradable return nor a guaranteed ask/bid change at usable depth.

## Interpretation and boundary

The specific, simple **venue catches up within the first recorded request** mechanism is unsupported here. This does not rule out later catch-up, transient opportunities between the two snapshots, or another source of edge; those would require their own observable execution and prospective test. The first books are roughly 17–18 seconds apart, not continuous market data. Both periods have been analyzed repeatedly, and the old holdout cannot be reused as independent validation for a new trading rule. This diagnostic creates **zero** new trade entries and makes no PnL claim; the original hourly rules and collection schedule remain unchanged.

The practical next boundary is clear: with these archives we can describe forecast quality and first-book responses, but cannot establish a consistently positive executable edge. Any proposed new order policy must first specify how its ask/bid, fees, latency and fills will be observed; it then needs a genuinely new forward sample. Adjusting an historical gap threshold until the old outcomes look profitable would not answer that question.
