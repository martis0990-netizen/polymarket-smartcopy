# Limitless independent strategy study v1

Frozen collection scope: BTC/ETH Up/Down, 15-minute and hourly **CLOB** markets.
Collection ends 2026-10-10 09:00 UTC. Research only; public market GETs and public
WebSocket subscriptions, no credentials, orders or capital. No other trading venue
is involved. This capture is independent of wallet activity.

## Implementation and evidence

`limitless_market_capture.py` discovers markets every 60 seconds, deterministically
selects up to eight active markets by expiration then slug, and records complete
Socket.IO orderbook/oracle/lifecycle envelopes with local receipt timestamps.
REST books every 15 seconds provide an independent check. Market details include
settlement description, spot/TWAP stream, tokens, Price to Beat metadata, expiration,
taker delay and fee-related settings. Oracle candles are requested every minute,
three-hour lookback, one request per asset. A response is usable only from its
receipt time, even when it describes earlier candles.

Unresolved markets carry across successful main runs in an artifact checkpoint.
Metadata checks prioritize active markets and are capped at 16 per minute. Closed
markets are rechecked no more frequently than five minutes. Disconnection,
REST errors, rate-limit backoff, incomplete discovery and job gaps are recorded.
Raw uncompressed output is capped at 256 MiB per segment; reaching it is a coverage
failure. Each job lasts at most 55 minutes and archives compressed data for 14 days.
Push/PR checks run two minutes; successful main jobs dispatch the next segment.
The hourly schedule is backup, not a guarantee of continuous uptime.

`limitless_capture_audit.py` reports data availability, socket event counts,
two-sided REST books and observed spreads. It reports **no PnL** and does not count
snapshots as independent trades. `READY_FOR_SCHEMA_REVIEW` is not a profitability
or execution verdict. Inspect the real oracle schema and exact settlement terms
before implementing the following predeclared benchmark.

## First directional benchmark (predeclared; not implemented yet)

Use spot-resolved markets only. TWAP markets are collected but excluded until a
matching TWAP model is explicitly specified. Unknown feed, threshold or settlement
semantics => SKIP. Do not silently treat every oracle stream as instantaneous spot.

The first benchmark uses zero-drift log-price diffusion: estimate volatility from
the last 120 fully closed one-minute oracle returns available before decision time;
compute P(Up) from log(current reference price / verified Price to Beat), volatility,
and remaining time. Missing warmup, stale/missing reference data or zero volatility
=> SKIP. A model probability is not supplied by the oracle itself.

One hypothetical decision per condition at the first valid observation at or after
the midpoint of its trading window, never repeated entries every snapshot. Compare
the model against a constant 50% model and no-trade control. A trade requires at
least 3% expected net return on its 10 USDC budget, after a conservative 3% buy fee
deducted from acquired contracts. Entry must use visible ask depth, a fixed maximum
acceptable price implied by that hurdle, and a subsequent observed book after
market takerDelayMs plus one second. If size cannot fill within the bound => SKIP.
Hold to verified settlement, including documented split payouts. No midpoint fills.

Report calibration and net expectancy separately. Use October 3–5 for schema and
data validation; October 6 through cutoff is untouched evaluation. Do not tune
thresholds on it. At least 60 independent conditions and adequate observation
coverage are required for an informative result, not proof of edge. Correlated
BTC/ETH/time windows must also be reported as clusters.

## Other directions

The existing wallet observer remains the source for BlindCopy vs SmartCopy research.
This independent data can quantify available follower quotes and price deterioration.
MOM15/Supertrend/BOS are later additions, with rules frozen before a new holdout.
Market making initially measures spread, depth and subsequent price movement only:
coalesced books do not reveal queue position, placements or individual fills, so
book touches cannot substantiate maker PnL. No live execution follows automatically.

Official references:
- https://docs.limitless.exchange/developers/websocket/overview
- https://docs.limitless.exchange/developers/websocket/market-data
- https://docs.limitless.exchange/api-reference/markets/browse-active
- https://docs.limitless.exchange/api-reference/markets/get-market
- https://docs.limitless.exchange/api-reference/markets/oracle-candles
- https://docs.limitless.exchange/user-guide/fees
