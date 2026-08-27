# Bonereaper prospective signal checkpoint — 2026-08-27 09:44 UTC

Status: **BOTH STUDIES COLLECTING; NO GATE MAY BE EVALUATED YET**

## Latest clean bundle

- capture: `bonereaper-prospective-bundle-20260827-04`
- interval: `2026-08-27T09:32:42Z` through `09:41:23Z`
- bundle manifest SHA256: `9c76008f9a6b8a07f6b98487cf73d9e6deefd783a0e65eaae76118cfb5381bff`
- Chainlink events: `483` BTC and `483` ETH; zero reconnects and empty gap artifact
- wallet rows: `283`; zero observer gap failures
- selected BTC/ETH receipt rows: `269`; all fee-aware roles unambiguous
- receipt rows SHA256: `a519a277ce59b4a006dbdd341fabe47fd9128a409d2d971ec5a5276913164acd`

## V3 pre-open study

The v3 contract was frozen at `82988de` before this bundle.  Analyzer code commit is `54ca960`.
Three new conditions are eligible toward the target of 30:

| Market | Lead | Side | Notional | Binance 15s | Chainlink 15s | BTC lead |
|---|---:|---|---:|---|---|---|
| BTC 5m, 09:35 | 30 s | Down | $11.15 | Down ✓ | Down ✓ | n/a |
| BTC 5m, 09:40 | 33 s | Up | $69.63 | Up ✓ | Up ✓ | n/a |
| ETH 5m, 09:40 | 17 s | Down | $2.44 | Up ✗ | Up ✗ | Down ✓ |

Interim counts, with gate evaluation deferred:

- Binance asset momentum: `2/3` aligned (`66.67%`)
- Chainlink asset trend: `2/3` aligned (`66.67%`)
- BTC lead for ETH: `1/1` aligned, descriptive only
- stopping progress: `3/30`

Binance and Chainlink signs agree on all three eligible conditions, so this bundle contains zero
discordant observations and cannot distinguish which feed drives the active decision.  The one ETH
condition is consistent with a BTC-to-ETH lead, but `1/1` is not evidence of a stable effect.

## V2 post-open study

The latest bundle contributes one eligible post-open condition:

- ETH 5m, 09:35: first taker `Up` three seconds after start; Binance 15s was `Up`, while the
  Chainlink barrier direction was `Down`.

Combined with the earlier eligible ETH 15m condition, the cumulative descriptive v2 counts are:

| Candidate | Aligned | Eligible | Share |
|---|---:|---:|---:|
| Binance 15s momentum | 2 | 2 | 100% |
| Chainlink opening barrier | 1 | 2 | 50% |

The frozen stopping target is 40 eligible conditions including at least 20 taker conditions.
Therefore the formal status remains `COLLECTING`; these fractions cannot be labelled supported or
not supported.

## Current mechanism reconstruction

The evidence now supports a narrower working architecture:

1. Bonereaper frequently initiates active taker inventory before the nominal market start.
2. In the discovery pilot, strict-pre Binance 15s momentum aligned in `5/6` pre-open conditions;
   the first prospective v3 bundle gives `2/3`.
3. Post-open active decisions currently favour Binance momentum over the opening barrier in two
   observations, but the sample is far too small.
4. Across the original study and the 391-row second bundle, opposite-leg maker notional was about
   `62–63%`, consistent with passive rebalancing.  The latest bundle is regime-different and has
   predominantly taker opposite-leg notional, so the mechanism is not universal per interval.

This does not identify Bonereaper's sizing formula, volatility model, order-placement time, or
profit after fees.  Public CLOB recording and separate maker/taker markout remain required.

