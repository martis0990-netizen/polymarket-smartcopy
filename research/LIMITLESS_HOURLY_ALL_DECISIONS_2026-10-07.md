# Limitless hourly: every decision and the price actually available

This continues the [loss-mechanism review](LIMITLESS_HOURLY_LOSS_MECHANISM_2026-10-07.md) without changing the frozen hourly model. The [machine evidence](evidence/limitless_hourly_all_decisions_2026-10-07.json) links every decision to its exact original book line and SHA-256, all 96 main ZIP digests, the selected-side forecast, visible depth, observed outcome when resolved, and the recomputed eligibility result. The final v1 state is from artifact `11470560416`, ZIP SHA-256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`.

The 96 ZIPs all passed the published SHA-256 check. The capture has **162 distinct `paper_decision` events**, each matched to the immediately preceding market-specific raw book; their condition, decision time and original probability match the final state exactly. This is 104 discovery and 58 old-holdout decisions. **160** have observed binary outcomes; two old-holdout decisions remain without a scored payout. The original selection logic was replayed for both MODEL and constant50 on all 162 raw books: 3% paper buy fee in contracts, 3% required edge, 10-USDC intended gross spend, six-decimal share rounding, exact book levels rather than midpoint or best-level-only liquidity. Its selected side, cap and size or NO_TRADE status agree with the recorded decision every time.

## Why the model said NO_TRADE

| Phase | All decisions | MODEL NO_TRADE | No best-level price meeting fee + 3% hurdle | A qualifying top price but insufficient depth at the intended size | Eligible at decision |
| --- | ---: | ---: | ---: | ---: | ---: |
| Discovery | 104 | 83 | **81** | **2** | 21 |
| Old holdout | 58 | 47 | **45** | **2** | 11 |

Thus **126 of the 130 NO_TRADE decisions** had no even top-level price passing the frozen model's fee and hurdle; only four were stopped by depth. The four depth examples are ETH, and their best-level quantities were smaller than the model's prescribed target. Reducing the intended amount *might* change future eligibility, but is a different sizing policy and has not been backfilled as a fill. Of the 32 eligible decisions, 29 later became paper fills; three failed the delayed execution depth/price bound. A decision-time quote is not the delayed execution price. The median decision-book YES bid–ask spread was about **4.8¢ discovery** and **4.5¢ old holdout**.

## Forecasts and selection

The market number below is the **midpoint of the observed YES bid and ask**, included only as a non-executable forecast comparator. The actual trade screen above always uses full ask depth and the fee.

| Phase and group | Resolved conditions | MODEL Brier | Book-midpoint Brier, forecast only |
| --- | ---: | ---: | ---: |
| Discovery, all decisions | 104 | **0.2059** | 0.2087 |
| Discovery, eligible at decision | 21 | **0.1858** | 0.1913 |
| Discovery, MODEL NO_TRADE | 83 | **0.2109** | 0.2131 |
| Old holdout, all resolved decisions | 56 | 0.1752 | **0.1579** |
| Old holdout, eligible at decision | 11 | 0.2078 | **0.1452** |
| Old holdout, MODEL NO_TRADE with outcome | 45 | 0.1672 | **0.1610** |

The gate selected a relatively better-calibrated subset in discovery, but a worse-calibrated subset in the old holdout. On the 10 selected **and subsequently filled** holdout entries, the model assigned **4.78 expected wins**; only one paid, and settled MODEL PnL was **−74.3787 USDC**. The book midpoint's lower holdout Brier is a clue that the model's apparent disagreement with the market did not translate into an edge at available asks. It is **not** a midpoint fill, proof that the market always knows best, or a validated blended forecast. Selected conditions share UTC hours and the sample is small.

## What this rules out and what remains testable

The data do not support “trade every skipped market”: almost all skips lack a price meeting the *existing* forecast, fee and hurdle even at the best visible level. Nor do the 29 filled MODEL entries establish a profitable original strategy: discovery's small gain relied on two outsized winners, while the old holdout lost. Simple direction-only and single-slope probability recalibration diagnostics in the earlier review also remained negative on that old period.

The relevant next hypothesis is **conditional disagreement quality**: when the Binance-derived forecast differs enough from an executable venue ask, is that disagreement informative about the final binary payout *after controlling for the market's own quoted probability, time left and volatility known at decision time*? All three quantities are now recoverable for every historical decision, not just fills. A causally specified probability model could be fitted by proper score on earlier UTC-hour clusters and evaluated on later clusters without selecting thresholds by PnL. However, the old holdout has already been inspected repeatedly; even a positive retrospective slice would remain exploratory and could not be called an independently verified profitable strategy. This report makes no new trades, changes no thresholds or fees, and does not restart collection.
