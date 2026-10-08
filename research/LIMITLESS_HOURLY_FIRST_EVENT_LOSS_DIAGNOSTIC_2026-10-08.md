# Limitless hourly: first-event paper loss attribution — 8 October 2026

Derived from the [verified first-event replay](LIMITLESS_HOURLY_EVENT_TRIGGER_RESULT_2026-10-08.md) using all 102 settled first-leg paper entries. This audit does not reopen the 96 previously SHA256-verified raw ZIPs or change the frozen bot. [Machine evidence](evidence/limitless_hourly_first_event_loss_diagnostic_2026-10-08.json) preserves the exact condition, decision and first-attempt artifact/line/hash, model probability, cost, net shares, payout and PnL for each row. [Full human-readable ledger](LIMITLESS_HOURLY_FIRST_EVENT_TRADE_LEDGER_2026-10-08.md).

For the chosen side, let p be the decision-time model probability, y the observed binary payout, and q=cost/net shares the first-attempt break-even probability after the 3% contract fee. Expected PnL *if decision-time p still applied at the first-attempt quote* equals net shares × p − cost; settled PnL equals net shares × y − cost. The difference is an accounting surprise, not a causal attribution to a single flaw.

| Phase | First events / paper fills | Wins / model-expected wins | Expected PnL at first quote | Settled PnL | Difference |
| --- | ---: | ---: | ---: | ---: | ---: |
| Discovery | 97 / 65 | 35 / 31.89 | +58.486 USDC | +119.599 USDC | +61.113 USDC |
| Previously inspected holdout | 57 / 37 | 11 / 17.97 | +43.834 USDC | **−152.666 USDC** | **−196.500 USDC** |

All 37 holdout paper fills had p > q (median margin 0.0329, minimum 0.0062). Mean p was 0.4858 and mean fee-inclusive q was 0.4393. First requests started on average 18.4 seconds after decisions: the decision-time p can be stale by the first attempt. In addition, 18 of 57 holdout first opportunities failed price/depth and 2 had no first request; no favorable retry was substituted. Eleven winning fills generated +82.105 USDC, while 26 losing fills cost −234.770 USDC.

| Overlapping holdout group | Fills | Wins / expected wins | Settled PnL |
| --- | ---: | ---: | ---: |
| BTC | 19 | 4 / 9.67 | -95.629 USDC |
| ETH | 18 | 7 / 8.30 | -57.037 USDC |
| YES | 15 | 2 / 6.14 | -108.724 USDC |
| NO | 22 | 9 / 11.83 | -43.942 USDC |

BTC and YES overlap. Of 26 active UTC-hour holdout clusters, 19 lost; 11 hours had both BTC and ETH fills, 6 of them losing both. This is a small correlated sample and does not justify excluding a chosen symbol, side or hour after seeing outcomes.

**Finding:** the archived first-attempt cost was acceptable *under the model's own decision-time p*, but its selected holdout outcomes diverged sharply. Possible explanations include probability calibration, selection/adverse selection, regime shift, or stale p during the entry delay; this saved ledger cannot distinguish them. All 102 settled paper payouts reconcile to y × net shares − cost; there are no duplicate conditions or requests before decisions. The old holdout was previously inspected and cannot establish an independent forward edge. Paper quotes do not prove live fills.

**Next diagnostic:** replay only as-of information available at the first request to measure changes in price, volatility and side between the decision and request, grouped by UTC-hour. Do not fit a side/time threshold to the old holdout or alter production rules based on this descriptive split.
