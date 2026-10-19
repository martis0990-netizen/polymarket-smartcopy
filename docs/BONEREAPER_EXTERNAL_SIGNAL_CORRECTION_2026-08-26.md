# Bonereaper external-signal contract correction

Status: **FROZEN BEFORE CORRECTED BARRIER RECOMPUTATION**

The v1 external-signal contract incorrectly applied the August 7, 2026 rule of a 30-second
Chainlink TWAP to the two 5-minute markets in the August 26 sample. Polymarket's official
Predictions Changelog states that, effective August 14 at 00:00 UTC, all 5-minute crypto markets
moved to a 60-second Chainlink TWAP. The sample therefore requires a 60-second opening window for
all four contracts.

This is a dated specification correction derived from official documentation, not from the v1
outcome. It changes only the Binance-proxy opening barrier and its volatility-normalized distance
for 5-minute episodes. The already-frozen momentum, RSI, EMA, flow, BTC-lead definitions,
populations, thresholds, and no-future-leakage rules remain unchanged.

The corrected run must reuse the first immutable external collection rather than refetching it:

- `binance_klines_raw.jsonl`: SHA256
  `0dfe8feb753affd9e04de86f70c71dd4191f3cfff94b2e56784b2a32504f8f85`
- collection: `960` one-second and `180` one-minute rows for each of BTCUSDT and ETHUSDT
- source: official Binance Spot API

The v1 primary opening-barrier result is invalidated. The corrected primary verdict uses the
original frozen gate without modification:

- `SUPPORTED_DESCRIPTIVELY`: at least 70% taker notional and at least 60% taker episodes align;
- `NOT_SUPPORTED`: at most 55% taker notional or at most 50% taker episodes align;
- otherwise `INCONCLUSIVE`.

The corrected output must be written to a new directory and must not overwrite the v1 artifact.
