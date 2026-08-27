# Bonereaper pre-open taker pilot — 2026-08-27 UTC

Status: **POST-HOC MECHANISM DISCOVERY; NOT A CONFIRMATORY RESULT**

## Why this pilot exists

The frozen v2 external-signal contract compares a first taker BUY with the official Chainlink
opening value `K`.  The first verification pass found that Bonereaper can trade a condition before
its nominal market start.  Using the later `K` for those decisions would leak future information,
so commit `0137789` marks them `PRE_OPEN_PRIMARY_TAKER` and excludes them from the v2 gate.

The excluded observations reveal a distinct mechanism worth preserving.  They were inspected
after collection and therefore may select the next hypothesis, but cannot confirm it.

## Immutable inputs

| Bundle | Bundle manifest SHA256 | Receipt rows SHA256 |
|---|---|---|
| `bonereaper-prospective-bundle-20260827-02` | `e591895c59b03893e94e46d5c9b5c3db2f9918b7376a0ddbab5470b89c0ebbd4` | `30437f8fd1599a32c654f1244071aa0942fafcbf31bf2c96728a9b9ec912c8fc` |
| `bonereaper-prospective-bundle-20260827-03` | `dd16db139529d3cc9087dc32dec1aa539106b0dca45425456176e8a0b67c47ea` | `10eec2ac41dedf96ad6ac4ff9973b132c38b9110b0c5536f2e59a94c7b047494` |

Both captures cleanly finalized with zero Chainlink reconnects and zero wallet gap failures.
Receipt roles were schema-corrected and unambiguous for every included BTC/ETH row.

## Observed pre-open first-taker episodes

The label is the earliest unambiguous taker BUY episode per `condition_id`.  Binance momentum uses
only one-second closes at `t-1` and `t-16`; the same second as the wallet fill is excluded.

| Market | Lead before start | Taker side | Taker notional | Binance 15s sign | Aligned |
|---|---:|---|---:|---|---|
| BTC 5m, 09:00 | 9 s | Down | $5.91 | Up | No |
| BTC 15m, 09:00 | 6 s | Up | $40.60 | Up | Yes |
| ETH 5m, 09:20 | 11 s | Up | $7.28 | Up | Yes |
| BTC 5m, 09:20 | 20 s | Up | $120.22 | Up | Yes |
| ETH 5m, 09:25 | 41 s | Up | $1.99 | Up | Yes |
| BTC 5m, 09:25 | 9 s | Up | $20.27 | Up | Yes |

Descriptively, momentum aligns in `5/6` conditions (`83.33%`).  Median lead is `10` seconds.  These
fractions are not evaluated against a support gate because the population was discovered after
the results were visible.

## Interpretation boundary

This pilot weakens the universal explanation “Bonereaper waits for the official opening `K`, then
trades relative to it.”  It is consistent with an active pre-positioning contour driven by recent
external momentum or by a forecast of the still-forming opening TWAP.  It does not distinguish
those two explanations and does not show profitability, causality, or copyability.

The formal v2 result remains `COLLECTING`: across these bundles only one post-open condition is
eligible for its barrier-versus-momentum gate.  The pre-open rows never enter that denominator.

