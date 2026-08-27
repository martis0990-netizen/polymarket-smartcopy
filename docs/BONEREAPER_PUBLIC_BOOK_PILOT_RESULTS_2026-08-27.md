# Bonereaper public-book pilot — 2026-08-27 14:04 UTC

Status: **PILOT OBSERVATION; NOT A CONFIRMATORY POPULATION VERDICT**

## Valid capture

- interval: `2026-08-27T14:03:59.498632Z` through `14:04:54.522253Z`
- frozen capture contract: `c16c4e6454c41296662e23d156bcc4b0b2e7b3c2`
- recorder/discovery code: `b37d72a7ef5769e9f4573765eab85e1845df3ad0`
- capture manifest SHA256: `09289d3b0a0aebdc31b5fef776d23c2d42130b20a9d3d741394fe4e8cd7f748c`
- raw frames SHA256: `5de6dadf293ea7de91d8aab95adda8e66f3c9710c6606b0b845f8fb2553beec3`
- normalized levels SHA256: `b30961421fbcecc39d2a3c0d5b2488e879540738d491e6d43a4b5bc826ef463d`
- token metadata SHA256: `adcfc6d38e743f9a2743ad43e07f0a6c42fbc3f80d09646042e55a342685de3f`
- 31,160 raw frames, 98,866 level records, 384 full snapshots
- zero reconnects, empty gap artifact, all eight bound tokens initialized at finalize

An earlier engineering smoke is excluded because its manifest contained a format-valid but
incorrect code SHA.  It was not repaired or merged into this result.

## Receipt and ladder join

The public Data API returned 46 Bonereaper fills in the four bound conditions, representing 39
unique Polygon transactions.  Every transaction receipt was obtained from Polygon and decoded with
the existing fee-aware CTF Exchange V2 decoder.

| Role / public-level result | Fills | Notional |
|---|---:|---:|
| Maker, startup coverage ineligible | 18 | $61.413026 |
| Maker, late or unseen exact-price level | 14 | $124.038600 |
| Maker, exact-price level visible at least 1 second | 1 | $0.013400 |
| Taker, ladder test not applicable | 13 | $157.608990 |
| **Total** | **46** | **$343.074016** |

Maker execution accounted for 33/46 fills and 54.06% of notional.  Among the 15 maker fills with
eligible book coverage, the pre-positioned share was 1/15 by row (6.67%) but only 0.0108% by
notional.  The sole qualifying fill was a two-cent-size dust trade.  The other 14 eligible maker
fills had no continuously positive public bid at their exact execution price from `t-1s` through
the final strict-pre update.

`LATE_OR_UNSEEN_LEVEL` deliberately combines a level introduced less than one second before the
fill and a level absent at the final strict-pre state.  Maker status proves passive execution, not
long resting duration or ownership of any visible aggregate level.

## Cross-horizon observation

All 13 taker fills occurred in the next BTC/ETH 5-minute markets before their nominal 14:05 UTC
start.  The concurrently open 15-minute markets were traded as maker.  During the same short
interval Bonereaper moved from buying Down in the open 15-minute markets to buying Up, while also
buying the future 5-minute markets aggressively.

This is consistent with one external BTC/ETH signal being expressed differently across overlapping
horizons: aggressive pre-open positioning in the next 5-minute contract and rapidly refreshed
maker quotes in the current 15-minute contract.  It does not yet identify whether that signal is
Binance momentum, Chainlink trend, volatility, order flow, or another input because this book-only
capture did not simultaneously record those feeds.

## Interpretation

The pilot does **not** support the simple picture of a long-standing public maker grid.  It instead
motivates the confirmatory hypothesis that Bonereaper submits or refreshes passive limit orders
close to execution while using taker orders for selected pre-open entries.  The confirmatory sample
and gates are frozen separately; this pilot is excluded from them.

