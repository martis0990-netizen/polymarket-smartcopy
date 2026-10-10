# Limitless hourly: fixed 5/15/30/45-minute shadow replay

The [single four-window protocol](LIMITLESS_HOURLY_TIME_WINDOW_PROTOCOL_2026-10-07.md) was saved as [commit `40975d2`](https://github.com/martis0990-netizen/polymarket-smartcopy/commit/40975d28ac4bb81d26a979f6cef965b20a8eb77d) **before** calculating the new counterfactual PnL. It uses the existing 96 SHA256-verified main ZIPs, the same 162 market conditions, first source book/request at each fixed offset, then first subsequent execution request, the unchanged hourly-v1 Binance diffusion formula, 3% contract fee, 3% hurdle, 10 USDC size cap, 1.5s venue wait and 30s decision expiry. It creates no actual orders or new market collection. The previous October 6 holdout has been repeatedly inspected and is not independent validation for selecting a different minute.

Coverage of a first book in the 60-second decision window plus fresh Binance 1m/1h response: discovery **102/104, 102/104, 104/104, 104/104** for minute 5/15/30/45; old holdout **58/58, 58/58, 58/58, 56/58**. The subsequent `MISSING_CURRENT_CANDLE` gate makes many first snapshots unusable; the table counts those as permanent SKIP_INPUT, with no favorable retry. Both YES-token identity and latest observed FUNDED status are checked at the decision.

## Separate windows, no PnL summation

| Phase | Minute from opening | Scored probability forecasts | Input skips | NO_TRADE | Execution skips | Hypothetical settled fills / winners | Paper settled PnL, USDC | MODEL / midpoint Brier* |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Discovery | 5 | 81 | 23 | 75 | 1 | 5 / 3 | **−3.7058** | .2322 / .2364 |
| Discovery | 15 | 75 | 29 | 69 | 0 | 6 / 3 | **−3.0102** | .2240 / .2232 |
| Discovery | 30 | 98 | 6 | 78 | 2 | 18 / 9 | **+31.6981** | .1988 / .2025 |
| Discovery | 45 | 85 | 19 | 63 | 4 | 18 / 3 | **−18.8853** | .1578 / .1578 |
| Old holdout | 5 | 48 | 10 | 43 | 0 | 5 / 3 | **+1.3698** | .2294 / .2275 |
| Old holdout | 15 | 47 | 9 | 46 | 1 | 2 / 1 | **−6.8154** | .2069 / .1995 |
| Old holdout | 30 | 46 | 10 | 37 | 1 | 10 / 1 | **−74.3787** | .1563 / .1380 |
| Old holdout | 45 | 49 | 9 | 40 | 1 | 8 / 1 | **−46.6393** | .1363 / .1325 |

*The midpoint is used only to compare forecast accuracy, never as a fill. Forecast denominators vary because first-request availability differs; later Brier scores are easier as time to expiry falls and cannot be interpreted as a trading advantage by themselves. The windows overlap on the same resolved markets and are **not** independent trade portfolios.

The 5-minute old-holdout +1.3698 USDC came from just five hypothetical fills across four UTC-hour clusters; its other three fills together lost 17.0258 USDC. The same 5-minute rule lost 3.7058 USDC in discovery. The 30-minute discovery gain still depends on two rare wins (+51.0712 and +35.1545); the other 16 fills together lost 54.5276 USDC. At minute 45, three of 18 discovery fills won, and one of eight old-holdout fills won. This does not support moving the trading decision to any of the tested windows as a profit improvement.

## Reconciliation and limitations

- All 648 window/condition rows contain source artifact, book line SHA256, receipt times, reference line IDs, first execution attempt and payout when observed. Their decision and execution timestamps passed as-of and expiry assertions. [Row evidence](evidence/limitless_hourly_fixed_windows_2026-10-07.json); [source coverage](evidence/limitless_hourly_fixed_offset_coverage_2026-10-07.json).
- For the 146 minute-30 conditions where the first source book equals the original hourly-v1 decision book, the original MODEL's NO_TRADE/FILLED/SKIP states match and fill costs agree within 0.00001 USDC. The forecast difference on identical book/reference prices is at most 0.0000007, because the original decision event was written milliseconds after the raw book receipt.
- In 16 other minute-30 conditions an earlier first book had no current Binance candle; the original hourly-v1 code later retried that **input**, whereas this precommitted strict-first comparison permanently skips it. Thus its discovery +31.6981 and 18 fills are **not** a replacement for original v1's +23.0855 and 19 fills. Ten old-holdout fills are common, with negligible cost timing differences.
- REST book receipts assume visible depth could be taken; these are hypothetical taker paper fills, not executed orders. There is no funded portfolio model across simultaneous BTC/ETH windows. Two final outcomes remain unscored. Old holdout is no longer independent after repeated examinations.

**Conclusion:** alternative decision time is a valid hypothesis, and these archives can test it. The four fixed strict-first times do **not** identify a stable profitable hourly taker rule. A different schedule, wait-for-valid-input policy or optimized minute would be a new candidate requiring a separately fixed protocol and future untouched observations; do not pick minute 5 from five old-holdout trades.
