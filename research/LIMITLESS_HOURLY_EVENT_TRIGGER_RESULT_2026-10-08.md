# Limitless hourly: first eligible event, then opposite-side quote

As of 2026-10-07 22:20 UTC (2026-10-08 01:20 Moscow). Retrospective paper diagnostic on the same 96 SHA256-verified main capture ZIPs and 162 hourly BTC/ETH conditions. Protocol was committed on branch `research/hourly-status-20261007` as `0a64a8b19aee4a3c5c9accd4bfce0e8b10b53533` **before calculating results**; causal second-quote request boundary was clarified in `71907bec6d4849a792797b0c1e54d67d4ba2a884`. No source capture, frozen hourly-v1 rule, fee, hurdle or holdout was changed. This experiment reuses an already inspected holdout and cannot validate a new profitable strategy.

## Result

| Measure | Discovery | Previously inspected holdout |
| --- | ---: | ---: |
| Conditions | 104 | 58 |
| Captured REST book/request records during those hours | 19,775 | 10,839 |
| Valid fresh as-of model/book checks **before first signal** | 6,655 | 3,763 |
| First qualifying opportunity at any observed time | 97 | 57 |
| First delayed entry successfully quoted as paper fill | 65 | 37 |
| First delayed attempt failed or absent | 32 | 20 |
| No qualifying signal observed | 7 | 1 |
| Settled winners of first-leg paper entries | 35 / 65 | 11 / 37 |
| First-leg settled paper PnL, USDC | **+119.599141550** | **−152.665714556** |
| First-leg PnL excluding best two winners, USDC | +40.135194217 | −183.604198314 |
| Active UTC-hour clusters / positive clusters | 46 / 25 | 26 / 7 |
| First later opposite-side book quote satisfying the paired-cost test | **42 / 65** | **18 / 37** |
| Median delay from first-leg response to qualifying opposite quote | 611.3 s | 664.1 s |
| Median *quoted* paired margin, USDC, among such quotes | 0.4402 | 0.3614 |

First opportunity occurred at median 16.3 minutes after open in discovery, 17.3 in old holdout; earliest observations were before one minute, and some only appeared past minute 50. The decision is therefore genuinely event based, not an alternative fixed minute. Counts of valid as-of checks stop at each condition's first signal, while book/request totals cover whole conditions; these denominators must not be interchanged.

The unchanged diffusion probability, 3% contract fee, 3% entry hurdle, full visible ask depth, 10 USDC first-leg budget, venue wait and 30s expiry were used. The first eligible book locks the choice. Of 52 unsuccessful first execution attempts, 50 failed the unchanged price/depth cap and two had no request. No later favorable attempt replaces either failure. The one-sided PnL settles the **paper first leg only** against the observed payout; it is not a wallet PnL or a claim of live fill.

For the second leg, the scan began with book **requests after the first-leg response**, required enough depth to match its net shares after another 3% buy fee, no more than 10 extra USDC, and a combined quoted spend strictly below guaranteed paired payout. The 42 and 18 observations are **quotes**, not second paper fills or booked paired PnL. A later order would encounter latency, book movement, competition and potentially unavailable depth. The median wait of roughly ten minutes supports the user's different-times hypothesis as an observable price-path pattern, not as a proven execution edge. No maker queue, rebate, resting order or re-entry was modeled.

## Verification and decision

- All 96 ZIP SHA256 values matched the existing `archive_manifest.json`. The temporary stream index contained 30,614 book/error rows, 9,335 market-status rows and 43,116 Binance reference responses, passed SQLite `quick_check` after a corrupted initial temporary index was discarded. Original ZIPs stayed unchanged.
- On 533 valid fixed-window source books, this index reproduced the earlier frozen probability **exactly** (maximum absolute difference 0), including the same as-of 1m/1h artifact and line references. All 162 condition rows passed entry/second-quote chronology checks. No midpoint or outcome informed entry.
- The event rule increases eligible entries relative to a single time window, but its holdout first-leg result is deeply negative. Do not promote this directional rule or tune its event thresholds on these repeatedly inspected outcomes. The differing discovery/holdout regimes remain a live model-calibration and adverse-selection concern.
- A paired quote alone cannot determine whether the second purchase would fill. A separate frozen forward paper state machine needs two distinct first attempts and actual delayed book checks; maker claims additionally need queue/execution evidence. No new forward collection or production trading was started here.

Machine rows with condition, source artifact/line hash, as-of reference pointers, first decision/attempt, settlement, and first qualifying later paired quote: `limitless_hourly_event_trigger_2026-10-08.json` (SHA256 `c7cce48759667a9d7e78f5d10cc726c0e7056c2a2e8952154ea764385fc643df`). Verification: `limitless_hourly_event_verification_2026-10-08.json` (SHA256 `9d79f2a70792cbed96f4f1706efe7587e8412d839a48d2c33557e8f8566a2d02`). Reproducer: `extract_hourly_event_raw.py`, `replay_hourly_event_trigger.py`, `verify_hourly_event_trigger.py`; place the previously verified attachment ZIPs and prior frozen hourly decision/fixed-window evidence alongside them before running. The generated 356 MB SQLite cache is disposable and not committed.
