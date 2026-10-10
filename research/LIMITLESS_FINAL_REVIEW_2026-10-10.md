# Limitless final research review — 2026-10-10

As-of: **2026-10-10 10:00:49 UTC**. Reviewed main: `ca44b0d50ceca861a09dfe5a70d80ef7c158837e`. Decision: **NO_PROMOTION**. Paper research only; no live orders, credentials, parameter tuning or restart of collection.

This timestamped supplement supersedes earlier pending/runtime statements, not their historical evidence. Collection was stopped on October 7 following the user's instruction. The planned October 10 cutoff therefore does not imply seven complete days of observations. Current probe/study, inventory-v2 fixes, entry pipeline, roadmap, wallet discovery and SmartCopy paper contract were read. Their economic qualification requirements remain in force.

## Own hourly signal and funded inventory

The frozen hourly-v1 evaluator is implemented. Each of the last two main market checkpoints was independently reconstructed with the current `HourlyPaper` and `InventoryPaper`; both saved reports match. Current inventory `archive_report` reconciles each ZIP separately and the pair, with aware as-of, no errors and `RECONCILED_PAPER_ONLY`. Cumulative reports were not summed.

| Hourly benchmark | Discovery | Holdout |
|---|---:|---:|
| Conditions observed / decisions | 112 / 104 | 66 / 58 |
| Model settled trades | 19 | 10 |
| Model settled PnL, USDC | +23.085530854 | −74.378700028 |
| Constant50 settled trades | 89 | 43 |
| Constant50 settled PnL, USDC | +17.309766642 | −71.992366613 |
| Model Brier score | 0.205862939097 | 0.175203813658 |
| Missed conditions | 8 | 8 |

Constant50 also has one pending holdout decision; it is not assigned an invented final payout. The standalone benchmark is not a funded account. Lower aggregate Brier than constant50 does not establish profitability at the selected execution prices. Ten model holdout trades span only six settled hour clusters: negative observed economics justify withholding promotion, but do not estimate a robust population effect.

Independent inventory-v2: initial **100 USDC**, cash **6.019112775**, realized/settled PnL **−93.980887225**, **27 settled positions**, zero open cost basis. Discovery: 17 settled positions, −19.602187197; holdout: 10, −74.378700028. Three first-entry attempts failed. Management states are HOLD26/SKIP1; no SELL or COMPLETE_PAIR execution occurred. Managed PnL equals matched seed-hold PnL; no management advantage demonstrated.

`started_at=1791058984.920855` is unchanged across the last two checkpoints. Entry attempts, admission skips, existing positions and immutable legacy history carry forward. Both raw evidence streams have 85 nonempty rows: source fingerprints validate and the earlier sequence is an exact prefix of the next. Legacy v1 history digest `cdd8166e55c911a26062daa3af94ea7acd5734eed01dfb9fc4eca1f6a7b21629` remains excluded from v2 economics. Strict current inventory validation rebuilds the funded ledger using raw entry/execution/payout sources. This proves nonempty evidence/state transfer, not execution of absent management actions. The bounded replay here does not replace a full re-download of every historical capture segment.

Hourly settlement and fees follow the frozen paper assumptions; this is not exchange fill evidence. Fifteen-minute Chainlink TWAP60 markets cannot be evaluated with the hourly Binance spot probability model. No such extrapolation was made.

## Wallet copying and coverage

The verified main audit artifact includes the latest main observer and its entry diagnostics. Its manifest lists 128 main runs: 101 successful downloaded segments, one failed partial segment and one cancelled partial segment downloaded; 24 cancelled and one failed run have no artifacts. The aggregate contains 103 actually captured segments. PR smoke is excluded. Partial-run data is not relabeled as successful complete coverage.

Frozen October 3 09:00–October 10 09:00 UTC coverage is **52.41–53.95%** across the fixed three wallets. The larger 91.88–94.58% figures in the intermediate aggregate apply only to elapsed time ending October 7 08:49:36, not the full week. The missing final >72 hours remains missing. Instrumented history pages are saturated; absence of overlap warnings does not prove no lost events (`lost_events_count=null`).

| First-observed fresh buy diagnostic | Fixed cohort | Discovery feed |
|---|---:|---:|
| Canonical observed buys | 15 | 2,777 |
| Depth supports illustrative 10 USDC quote | 14 | 2,101 |
| Data-qualified quotes | 10 | 1,746 |
| COPY-eligible | 0 | 0 |
| Median detection delay | 36.61s | 52.53s |
| Median gross VWAP minus source quote | +0.2940 | +0.0440 |

Discovery has 204 older unverified request starts, 47 failed first attempts and 425 insufficient-depth records; fixed cohort has one insufficient-depth record. Failed first attempts are not favorably replaced. Gross gaps, including quotes at/below source, are neither fills nor PnL and cannot isolate pure latency loss.

The legacy frozen gate has only 18 episode proxies against its 60-episode requirement and fails 90% weekly coverage. Those 60s groups/order-side groups are not independently reconstructed ENTER/ADD/REDUCE/EXIT intentions. Outcome decoding, prospective metadata and request timing reached main, but they do not supply unknown initial inventory, verified intent, follower fees and calibrated fair value. **BlindCopy and SmartCopy economic comparison: INSUFFICIENT_DATA; both PnL=null.** SKIP is not evidence of profitable superiority.

## Discovery and profiles

Latest successful discovery is actual main `workflow_run` 37560062877, not YAML-only evidence. Both leaderboards are READY, with zero discovery request errors. Latest snapshot has **47 candidates**, **12 enriched**, and **242 cumulative first_seen addresses**. Previous-to-next first_seen values remain unchanged; candidate first_seen agrees with state. All 24 saved 1w/1m PnL projections exactly reproduce from raw API responses, but remain API historical projections rather than an independently reconciled or forward follower ledger.

Five wallet profiles and action traces were reconstructed from `profile_requests.jsonl.gz`; all match the saved reports. Cursor chains match nextCursor and remain open at the ten-page cap: all five histories are `TRUNCATED_PAGE_CAP`, at most 300 returned events each. Some profiles are predominantly maker, others taker; both-side buys and Merge/Claim activity occur. This describes executions, not proof of market making, arbitrage or independent wins. Strategy, initial/final inventory and independent intent remain UNKNOWN. Later opposing trades or metadata cannot filter an earlier execution retrospectively. New candidates remain discovery-only and do not enter the fixed cohort.

## Maker hypothesis

Latest main capture has 740 two-sided REST snapshots across 14 markets and median spread **5.1¢**, plus 6,598 received public Binance 1s reference frames. These are repeated, dependent mixed-market observations. The older 4¢ median was a different sample, not a realized margin. No passive queue/own-order/fill model is verified: touching a price does not imply execution. Maker profitability and rebate earnings remain unmeasured.

## Provenance and verification boundary

All six downloaded ZIP hashes were checked against artifact digests. The observer aggregate is audited as saved output in the hash-verified audit ZIP; this review did not download/recompute all 103 underlying observer ZIPs. The machine evidence contains hashes, report reconstructions, aware as-of, continuity, coverage and discovery checks.

| Main run | Artifact | SHA256 |
|---|---|---|
| 37582713347 | 11467850234 | 5a5349dda8c13d4c70195902f2db37b13e7ce45472dc8adc8e5f1cd56918647c |
| 37588187303 | 11470560416 | 73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b |
| 37589820380 | 11470667489 | d275a3e3ded4ef120409ff08da4ce662c7fac3eea234f08c2fe05c443e17dbf2 |
| 37596229199 | 11470474384 | 8a4207186dfc659607b26a57507549daf9ac172a78d4ca1aa34053ac7b90fef0 |
| 37558764411 | 11456295217 | 17c5e7f4aab9cfd90ada26fe653dab85fc437913367a6de10e5c9d4913df5a38 |
| 37560062877 | 11456765866 | e2a38920b786a828e40adfdb52028137f678c45ccc0eba4a873ba3f9099c7cd7 |

October 8/9 successful scheduler checks produced no data artifacts: their audit/upload steps were skipped. They add no observations. No strategy, thresholds, fees, frozen holdout, cohort, concurrency or collection schedule was changed. No reproduced technical error requiring a code fix was found in this bounded reconciliation; the previous 88 regression tests were not unnecessarily repeated.

Next authorized research should preserve this frozen loss record. Any new candidate must be a separately versioned causal specification with a fresh untouched evaluation period; these inspected outcomes cannot become a new untouched holdout. Copying first requires independently reconstructed intentions and executable follower economics; maker first requires a conservative queue/fill measurement contract. Neither is ready for live deployment.

Machine evidence: [limitless_final_review_2026-10-10.json](evidence/limitless_final_review_2026-10-10.json).
