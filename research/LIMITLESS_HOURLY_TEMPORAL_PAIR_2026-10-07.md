# Limitless hourly: buy YES and NO at different times

**Correction to scope.** The [simultaneous paired-ask audit](LIMITLESS_HOURLY_PAIRED_ASK_AUDIT_2026-10-07.md) checked two taker buys against one snapshot; it did not test the proposed sequential accumulation. This follow-up uses the same 96 digest-verified successful main ZIPs and the final hourly v1 paper state from [run 37588187303](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37588187303), artifact `11470560416`, SHA256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`. Collection remains stopped. [Machine evidence](evidence/limitless_hourly_temporal_pair_2026-10-07.json) records each raw first-fill, trigger-quote and first delayed-request fingerprint.

## Fixed first legs and causal second-leg test

First legs are the **actual frozen paper MODEL and constant50 entries**, not a first-entry rule selected after observing the second price. Their contract quantities and cost were recomputed exactly from the original raw execution books. At each later observed book before expiry, a complementary buy qualifies if equal net YES and NO quantities after the existing conservative 3% fee would make `guaranteed binary payout − first cost − second cost > 0` at visible depth. The second leg is first **triggered** by the earliest such quote for a condition. The test then looks only at the first public book request starting after the venue delay and arriving within 30 seconds; it never substitutes a later favorable response for a failed first attempt. There is no second order or observed second fill.

| Frozen first-leg cohort | First paper fills | Later positive second-leg quote | Still positive at first delayed attempt |
| --- | ---: | ---: | ---: |
| MODEL discovery | 19 | 15 | 13 |
| MODEL holdout | 10 | 8 | 6 |
| constant50 discovery | 89 | 60 | 49 |
| constant50 holdout | 43 | 28 | 24 |

The 161 first-leg rows are **134 distinct conditions**: MODEL and constant50 sometimes bought the same condition, so their counts and hypothetical gains must not be added. Across both overlapping cohorts, 80 distinct conditions in 52 UTC hour clusters had a positive depth quote at the first delayed attempt. There were no parsing errors. For example, one holdout constant50 condition `0x947c8f1ced63d9435ca2a348f1f89e226b6e6ff38c8411d4b8edac2b44f2fad4` had first cost `8.90858746` USDC. The first delayed response showed the matching complementary shares for `9.447937963` USDC; the pair's minimum payout would be `20.59999961`, an *illustrative quote surplus* of `2.243474187` USDC before execution/network costs. It is not a realized trade.

Capital is a major constraint. At the **unchanged original first-leg size**, the delayed complementary quote exceeded 10 USDC in 6/13 and 4/6 persistent MODEL cases (discovery/holdout), and 47/49 and 23/24 persistent constant50 cases. The fixed paper entry budget was 10 USDC per leg; most constant50 examples would need a smaller first position or a separately specified capital policy. This report does **not** rescale entries after seeing their second-leg prices, assert all pairs fit a funded 100-USDC portfolio, or sum quote surpluses as PnL.

## Interpretation and next gate

The user's temporal hypothesis **has observed quote support** and is materially different from the same-book null result. What remains unknown is whether two actual taker executions, with first-leg funding, second-leg delay, changing depth and cancellation risk, produce positive *funded* PnL. Both discovery and old holdout were inspected before this hypothesis was formulated; neither is independent validation. Maker queue fills are also unobserved. The next useful paper-only version would fix a first-leg sizing rule and a funded capital cap *before* replay, record the first second-leg attempt and unhedged inventory through payout, then use a new forward period if retrospective economics merit it. No strategy, fee, workflow, holdout, state or live order has been changed here.
