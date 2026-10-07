# Limitless hourly: can existing captures establish maker PnL?

The 96 main capture ZIPs used in the [hourly decision review](LIMITLESS_HOURLY_ALL_DECISIONS_2026-10-07.md) were previously checked against their artifact SHA256 digests. This additional [channel inventory](evidence/limitless_hourly_ws_event_inventory_2026-10-07.json) scanned **every** `ws_event` record in those ZIPs. The code subscribes to `subscribe_market_prices`, `subscribe_oracle_price_data` and market lifecycle; the captured raw event envelopes were counted without converting book updates into transactions.

| Websocket event | Records across 96 ZIPs |
|---|---:|
| `orderbookUpdate` | 3,512,355 |
| `oraclePriceData` | 1,036,387 |
| `marketCreated` | 3,893 |
| `marketResolved` | 3,875 |
| `system` | 4,914 |
| Trade prints / own order execution events | **0 recorded as such** |

Three representative ZIPs (first, middle, last) were independently recounted by full JSON parsing and matched the channel inventory exactly. These event totals cover all subscribed Limitless market families, not just hourly. `orderbookUpdate` is an order-book state observation; it does not identify whether a hypothetical maker order entered the queue, its priority, a trade against it, or its partial fill. Even a later disappearance of best bid volume could be cancellation rather than an execution. Consequently the existing archive **cannot** support a maker fill rate or settled maker PnL estimate. The observed hourly median spread near 4.5–4.8¢ is a quoting opportunity hypothesis, not captured profit.

This is a data sufficiency result, not a request to change the active collector or to place orders. Historical maker returns must remain **UNMEASURED**. The existing taker quote replay, with first subsequent book, is a different execution hypothesis and remained negative on the repeatedly inspected old holdout. No new strategy, fee, threshold, order, or capture schedule is introduced here.

## Public historical trade source outside these ZIPs

The [official Limitless market-events documentation](https://docs.limitless.exchange/api-reference/trading/market-events) describes unauthenticated `GET /markets/{exactSlug}/events`: finalized `MINED` CLOB trades, newest first, pages of at most 100, with trade time, token, taker side, size and weighted price. The [order-book guide](https://academy.limitless.exchange/academies/api_academy/08_OrderBook.html) explicitly says that a market-wide trade-print channel is absent from the websocket and directs readers to this REST feed. We have **not** retrieved or reconciled this separate historical feed for our 162 conditions, and its completeness over the target dates is unverified. It could establish when public trades occurred at particular prices; it still omits our hypothetical order's queue position and unexecuted placements/cancellations. Therefore it can support conservative execution bounds, not an exact passive-fill or profit claim. The next read-only feasibility check is one exact archived slug and paginated source-time coverage, then a bounded cross-check against captured order-book observations; do not call missing trades fills.
