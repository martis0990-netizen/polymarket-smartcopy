# Limitless hourly: one closed-candle structure factor

The [range-break protocol](LIMITLESS_HOURLY_STRUCTURE_PROTOCOL_2026-10-08.md) was frozen in [commit `71a3b0f`](https://github.com/martis0990-netizen/polymarket-smartcopy/commit/71a3b0f65c8547c2e492f1f77503034bfbeaf1c7) before scoring its outcome relation. Source: the same 96 previously SHA256-verified main ZIPs, the strict-first minute-30 [window replay](LIMITLESS_HOURLY_TIME_WINDOW_RESULT_2026-10-07.md), and only Binance candles closed before each source request and decision. No active bot, fee, threshold or collection changed.

The signal is `+1` when the last fully closed 1m close exceeds the highest high of 60 older 1m candles ending 15 minutes earlier; `−1` when below their lowest low; otherwise `0`. It is a **local range-break proxy**. This capture carries up to 181 Binance 1m bars per response and a two-bar 1h response; it cannot establish the 4h swing structure, BOS/CHOCH or three-point consolidation previously discussed. The 30-minute strict-first screen provides 98 scored discovery and 46 scored old-holdout conditions, with two more unresolved old-holdout conditions.

For each decision, a baseline convex blend `q0` of the Limitless midpoint and frozen Binance probability is fitted by log loss only on previously **observed** payouts. The added model `q1` uses one bounded structure coefficient fitted on prior frozen `q0` predictions, with a fixed penalty of 10. Both are forecasts, **not** midpoint executions or trades. The comparison uses identical resolved conditions in each phase.

| Phase | Range break + / − / neutral | Market midpoint Brier* | Binance Brier | Chronological blend `q0` Brier | Blend + structure `q1` Brier | `q1 − q0` Brier difference; UTC-hour cluster bootstrap 95% interval |
|---|---:|---:|---:|---:|---:|---:|
| Discovery (98 outcomes, 53 hour clusters) | 10 / 13 / 75 | .20245 | **.19883** | .19970 | .20017 | +.00047 [−.00022, +.00115] |
| Previously inspected holdout (46 outcomes, 25 clusters) | 1 / 7 / 38 | **.13796** | .15632 | .14748 | .14654 | −.00094 [−.00310, +.00076] |

*Market midpoint is a forecast comparator only. Lower Brier is better. The proper-score log-loss comparison points in the same directions: discovery `q0 .59284 → q1 .59357`, old holdout `.45453 → .45199`, while the market midpoint alone is `.42943` in old holdout. The 4,000 bootstrap samples resample whole UTC-hour clusters and describe these reused historical periods, not an independent test.

The feature changes sign only on 23 discovery and 8 scored old-holdout conditions. It does not show a stable incremental advantage: slight discovery deterioration, small old-holdout improvement with uncertainty spanning zero, and both holdout combinations below market-only forecast quality. No PnL or fill was calculated for this new forecast. These observations do **not** justify adding BOS, more indicators or a new trading rule. A true higher-timeframe structure feature would require a separately defined as-of data history and untouched future evaluation; sweeping pivot settings on these outcomes would be fitting the answer.

[Row-level machine evidence](evidence/limitless_hourly_structure_factor_2026-10-08.json) contains source book artifact/line SHA256, reference candle line, last closed candle time, frozen training count, weight, structure coefficient, forecast and observed payout. All 146 eligible rows passed as-of/feature/score identity checks.
