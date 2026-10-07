# Limitless hourly: delayed second leg with a fixed paper budget

This is a tighter paper-only check of the [sequential pair audit](LIMITLESS_HOURLY_TEMPORAL_PAIR_2026-10-07.md), using the frozen first paper fills and the archived main Limitless books. It does not authorize a new strategy, restart collection, or assume that a book quote actually filled. [Machine evidence](evidence/limitless_hourly_pair_strict_budget_2026-10-07.json) names each condition, book line and SHA-256, ZIP digest, as-of time, quote arithmetic, and cash before the hypothetical second leg.

## Fixed rules checked

1. Start with the actual frozen MODEL or constant50 paper fill, quantity and cost. Keep discovery and the old holdout separate and never add overlapping cohort results as independent trades.
2. Find the first *positive* complementary depth quote: matching **net** YES and NO shares after the original illustrative 3% buy fee in contracts, and `net shares − first cost − second cost > 0` USDC. This is only the trigger.
3. Check the **first** public book request started after the recorded 1.5-second venue delay, received within 30 seconds of that trigger. No replacement with a later favorable book.
4. At the original first-leg quantity, require first and second costs each `<= 10 USDC`. Independently replay every first fill and observed settlement for each variant with a hypothetical initial 100-USDC cash balance, adding only the qualifying second-leg costs. No borrowing and no mixing MODEL with constant50 cash.

The previously verified 96 main ZIPs supply the [original event audit](evidence/limitless_hourly_temporal_pair_2026-10-07.json). This follow-up independently downloaded the 10 ZIPs containing the surviving delayed requests, matched their published ZIP SHA-256 and the 12 exact raw-line SHA-256 values, checked slug and YES token against the final state, verified there was no earlier eligible request for the slug, and recomputed the opposite-side book depth from raw `1e6` sizes (`NO` asks from `1−YES bid`). All 12 recorded second-leg costs matched the raw-depth calculation. The final state ZIP is artifact `11470560416`, SHA-256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`.

## Counts

| Frozen first-leg cohort | First fills | Any later positive complementary quote | Still positive on first delayed request | Also within 10 USDC per leg |
| --- | ---: | ---: | ---: | ---: |
| MODEL discovery | 19 | 15 | 13 | **7** |
| MODEL old holdout | 10 | 8 | 6 | **2** |
| constant50 discovery | 89 | 60 | 49 | **2** |
| constant50 old holdout | 43 | 28 | 24 | **1** |

The final column has **12 distinct conditions in 10 UTC hour clusters**, not 12 filled pair trades. Their first delayed response arrived about 17.2–21.4 seconds after the trigger; this includes the capture cadence and exceeds the nominal 1.5-second eligibility delay. The 12 *illustrative* locked quote surpluses ranged from **0.1223 to 3.3668 USDC**, median **0.5404 USDC**. Five had a margin no greater than 0.25 USDC. These values include the paper 3% contract fee for both buys, but do not account for a second actual fill, book races, network costs or any additional real-world fee variation.

One of the three old-holdout examples is condition `0x947c8f1ced63d9435ca2a348f1f89e226b6e6ff38c8411d4b8edac2b44f2fad4`: constant50 first paid `8.90858746` USDC and the first delayed NO book priced equal net shares at `9.447937963` USDC. The implied minimum binary payout is `20.59999961` USDC, leaving a **2.243474187-USDC book surplus** if the second order actually filled at that depth. Raw request: artifact `11385278898`, line `27653`.

## Funded counterfactual, not observed PnL

The original hourly v1 paper report explicitly had **no funded portfolio model**. To check the requested 100-USDC cash constraint, we replayed its saved 29 MODEL and 132 constant50 first fills and settlements as **two separate** portfolios, then deducted the 9 and 3 hypothetical second legs at the qualifying observed books. None of the original first fills or 12 hypothetical second costs encountered a cash shortfall in that replay. This proves only that these 12 quoted sizes fit that retrospective cash path.

| Separate variant | Saved first-leg-only settled PnL, discovery + old holdout | Final cash if all qualifying second quotes had filled, initial 100 USDC |
| --- | ---: | ---: |
| MODEL | −51.2932 USDC | **37.3074 USDC** |
| constant50 | −54.6826 USDC | **39.0451 USDC** |

The right column is an **optimistic conditional counterfactual**, not a new paper bot result. It assumes every second leg filled at the observed book and preserves every other first-leg action and observed payout. Even under that assumption the whole portfolios remain below their initial 100 USDC. A positive locked pair can cap the upside of a first leg that would have won anyway: **10 of these 12 first legs won on their own** in the saved settlement ledger. The second purchase would have exchanged part of that upside for a smaller guaranteed quote surplus. The two remaining first legs lost alone, so those pairs would have helped *if* the second book had filled.

**Decision:** twelve delayed, budget-sized, positive **quotes** survive this historical screen, including only three in the already inspected holdout. There is no demonstrated fill rate or profitable executable pair strategy. Do not fit new thresholds to these 12 or relabel this old holdout as forward validation. A future paper executor would need a precommitted second-leg rule, actual first-attempt outcomes, funded inventory through payout, and new data; no live orders or model changes follow from this audit.
