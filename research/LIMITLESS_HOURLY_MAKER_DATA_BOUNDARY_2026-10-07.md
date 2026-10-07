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
