# Limitless independent strategy study v1

Frozen collection scope: BTC/ETH Up/Down, 15-minute and hourly **CLOB** markets.
Collection ends 2026-10-10 09:00 UTC. Research only; public market GETs and public
WebSocket subscriptions, no credentials, orders or capital. No other trading venue
is involved. This capture is independent of wallet activity.

## Implementation and evidence

`limitless_market_capture.py` discovers markets every 60 seconds, deterministically
selects up to eight active markets by expiration then slug, and records complete
Socket.IO orderbook/oracle/lifecycle envelopes with local receipt timestamps.
REST books every 15 seconds provide an independent check. For verified Binance-settled hourly markets, public Binance 1m candles (181 rows) are received before each book cycle; 1h candles (two rows) are checked every minute. Only BTCUSDT and ETHUSDT are permitted, through data-api.binance.vision; no Binance account or trading route is used. Market details include
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
two-sided REST books and observed spreads. The capture audit reports **no PnL** and does not count
snapshots as independent trades. `READY_FOR_SCHEMA_REVIEW` is not a profitability
or execution verdict. Inspect the real oracle schema and exact settlement terms
before implementing the following predeclared benchmark.

## First directional benchmark: hourly v1, implemented and frozen 2026-10-03

`limitless_hourly_paper.py` is a deterministic paper state machine inside the capture.
It writes decisions, skips, delayed executions and settlements to the observation
journal, carries cumulative condition state in `state.json`, and publishes
`hourly_paper_report.json` per segment. Archive reports reconcile checkpoints,
count each condition once, and exclude conflicting decision lineages.

Eligibility is strict: CLOB, USDC six decimals, BTCUSDT/ETHUSDT spot Binance hourly
chart metadata, UTC-aligned startAt equal to chart.windowOpenAt, expiration exactly
one hour later, and no Chainlink stream. The Binance hour's open must exactly equal
the Limitless metadata.openPrice. Current actual 15m markets use Chainlink TWAP60
and are collected but excluded from this benchmark. Unknown semantics => SKIP.

One decision per condition at the first valid observation from its midpoint through
midpoint + 60 seconds. Missing that window => SKIP. Estimate volatility from the
last 120 consecutive fully closed one-minute log returns. A candle must have closed
before the underlying request began, not merely before its response arrived. The
partially formed current candle's last price is a reference only, never a training
return. Reference receipt age must be <=10 seconds, hour-open verification <=120
seconds old; current candle must contain the observation time. Missing/stale/zero
volatility data => no decision. Zero drift in log price gives
P(Up) = Phi(log(reference / opening) / (sigma_1m * sqrt(minutes_remaining))).
This is an approximate forecasting model to validate, not an arbitrage identity.

Compare the model and a constant 50% model using the same observation, book and
execution rules; also report no-trade PnL zero. Buy only when modeled expected net
return on spent USDC is at least 3%, using a conservative 3% buy fee deducted from
contracts. For each side the maximum acceptable price is p_side * 0.97 / 1.03.
The size cap is floor_to_6_decimals(10 USDC / max_price); all visible depth for that
quantity must fit under the cap and the 10 USDC cost budget. Choose the side with
higher expected net return, or NO_TRADE when neither qualifies. Fixed quantity can
spend less than the budget when prices are better.

The decision snapshot never fills the trade. The first subsequently requested
usable book after takerDelayMs + one second must pass the fixed quantity, depth,
token identity and price bounds. The request itself must begin after that delay;
a late response to an earlier request does not qualify. Execution observation must
arrive within 30 seconds of decision. Failed/invalid first execution book => SKIP,
not repeated attempts until a favorable quote. NO ask depth is derived by inverting
the merged YES bids; raw sizes are divided by 1e6. Empty/crossed books are invalid.

Hold to a subsequently observed RESOLVED market at/after expiration. Respect
winningOutcomeIndex and split payoutNumerators; do not infer winning from price.
Unresolved outcomes remain pending and never enter settled PnL. Report forecast
Brier score on binary resolved conditions, settled net PnL/return/cost, state counts,
condition counts and UTC hour clusters separately for discovery and holdout. Split
payouts count financially but are excluded from binary calibration. Both variants
can choose no trade; no-trade conditions contribute zero PnL.

Discovery: October 3-5 UTC. Untouched holdout: October 6 through collection cutoff.
Do not change rules based on holdout outcomes. At least 60 scored conditions and
60 distinct resolved hour clusters trigger coverage review; below that the report
says INSUFFICIENT_DATA. These counts are feasibility checks, not proof of edge.
The final review must check >=90% relevant observation coverage, concentration,
uncertainty and execution assumptions before interpreting performance.

Limits: REST depth is assumed executable at receipt; cache staleness, competing
fills and matching races are not reproduced. No portfolio funding or collateral
lockup model is implemented. Therefore descriptive paper returns do not authorize
live trading. The default 3% fee is deliberately conservative, not a claim that
all accounts/prices pay that exact rate. No rewards/rebates are included.

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

- https://developers.binance.com/docs/binance-spot-api-docs/faqs/market_data_only
- https://developers.binance.com/docs/binance-spot-api-docs/rest-api/market-data-endpoints
