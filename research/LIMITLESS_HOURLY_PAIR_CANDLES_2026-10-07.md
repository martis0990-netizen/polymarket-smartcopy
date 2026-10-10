# Limitless hourly: candles around sequential YES/NO quotes

The [sequential-pair audit](LIMITLESS_HOURLY_TEMPORAL_PAIR_2026-10-07.md) fixes the first leg to an actual frozen hourly paper fill and looks for a later complementary ask whose **visible depth**, after the existing illustrative 3% fee in contracts, would leave a positive binary payout surplus. This note characterizes the Binance BTCUSDT/ETHUSDT one-minute candles around those observations. It does not add a strategy, reopen collection, or turn a quote into a second fill or realized PnL.

## Source and time discipline

The underlying audit covered 96 successful main capture ZIPs. For this candle check, 80 implicated ZIPs were downloaded and checked against their published ZIP SHA-256; all 272 distinct first-fill/first-positive-quote source rows were checked against the exact line SHA-256 in the [original machine evidence](evidence/limitless_hourly_temporal_pair_2026-10-07.json). There were 161 first-leg cohort records and 111 first-positive-quote records; MODEL and constant50 overlap on some conditions. The 80 ZIPs include one required for the delayed-attempt proof but without a first/trigger row. All 272 targets had a prior Binance 1m REST response for the correct symbol, requested before the corresponding Limitless book request. Median Binance-request-to-book-request gap was 1.61 s at first fill and 1.77 s at the quote. Full candles *containing* the quote were later available in the same ZIP for 107/111 records. [Machine-readable candle metrics](evidence/limitless_hourly_pair_candles_2026-10-07.json) preserve condition, source artifact/line, timestamps, prior candle metrics, observed partial reference prices, and cohort/phase. Binance's [spot kline format](https://developers.binance.com/en/docs/catalog/core-trading-spot-trading/api/rest-api/market) supplies open/high/low/close and the candle close time.

For pre-entry comparisons, use only 30 **closed** one-minute bars already returned before the first book request. The prior 30m realized movement is `sqrt(sum(1m log-return-bp²))`; it is a descriptive realized-volatility proxy, not ATR. The median of the 30 one-minute high-low ranges is the local range baseline. Spot at each book is the close reported by the most recent prior Binance response, including its unfinished current minute where present. Thus the measured first-to-quote move is a near-time reference, **not** the later final close. Full quote-minute OHLC is strictly retrospective and never a pre-quote signal.

## Was volatility already high when the first leg was bought?

The table compares eventual positive second-leg quotes with first fills that had no such quote in the observed books. Values are medians of the **pre-first-fill** 30m volatility proxy, in basis points (bp); each cohort has overlapping hour clusters, so rows are not independent experiments.

| Frozen cohort | Positive / first fills | Prior volatility: positive | Prior volatility: no quote | Prior 1m median range: positive / no quote |
| --- | ---: | ---: | ---: | ---: |
| constant50 discovery | 60 / 89 | 13.60 | 15.86 | 1.65 / 2.35 bp |
| constant50 holdout | 28 / 43 | 21.12 | 19.31 | 3.56 / 3.64 bp |
| MODEL discovery | 15 / 19 | 13.02 | 18.31 | 1.32 / 3.39 bp |
| MODEL holdout | 8 / 10 | 25.56 | 22.31 | 4.14 / 3.86 bp |

This does **not** support a general rule that an unusually volatile preceding candle or high prior volatility predicts the second leg. In discovery the positives started in *quieter*, not more volatile, conditions by this measure; holdout comparisons are mixed and the MODEL negatives are only four and two first fills. BTC and ETH differ and some hours contribute multiple rows. This is a descriptive check, not a hypothesis test or a threshold search.

## What happened between the two legs?

| Cohort | First fill → first positive quote, median | Spot move **toward first-leg outcome**, median | Toward first-leg outcome, count | Quote-minute full range / preceding 30m median 1m range, median* | Full quote-minute range >2× baseline* |
| --- | ---: | ---: | ---: | ---: | ---: |
| constant50 discovery | 248 s | 5.74 bp | 60/60 | 2.07× (56 available) | 28/56 |
| constant50 holdout | 167 s | 7.41 bp | 28/28 | 1.62× (28 available) | 13/28 |
| MODEL discovery | 246 s | 4.73 bp | 13/15 | 3.36× (15 available) | 12/15 |
| MODEL holdout | 183 s | 5.89 bp | 7/8 | 1.17× (8 available) | 3/8 |

*The complete quote-minute high/low was observed **after** the trigger and may include later price movement. It can describe a candle, but cannot justify an earlier order. The already closed minute immediately before the quote was much less extreme: its range versus the preceding 30m median had cohort medians 1.08×, 1.20×, 1.00× and 0.76× respectively. The typical move unfolds over several minutes, not necessarily in one exceptional one-minute candle.*

As expected when one side is bought first and its opposite becomes cheaper, the reference price often moves in the first side's direction; it is not universal. A MODEL holdout NO example had an opposite 15.82-bp reference move over roughly 29 minutes yet still showed a complementary quote; market quotes, strike/time-to-expiry, and reference definitions matter too. `Toward first-leg outcome` is computed from the first to second observed Binance prices, so it is a **post-entry description**, not an ex-ante predictor.

A concrete volatile example: in BTC on **2026-10-06 13:30:24 UTC**, constant50 first bought YES with Binance's recent price about **86,003.60**. At **13:32:18 UTC**, the first positive NO quote coincided with a recent Binance price about **86,219.09** (+25.02 bp); the most recent *closed* minute spanned **17.92 bp** versus a 30m median one-minute range of **3.17 bp**. The required NO cost was **10.85 USDC** at that book, above the unchanged 10-USDC per-leg paper entry budget. The visible pair surplus of **2.96 USDC** therefore must not be reported as an executed or budget-admissible profit. Source: condition `0xb26c4aef037f7a11972615abae22c737568b8a3a8e558bad5cf005cdcadea7c7`, artifact `11417994486`, first book line `22338`, quote line `24602` (fingerprints in the original evidence).

## Execution and inference limits

Of 111 first positive quote rows, 92 still had a positive depth quote on the first delayed public request (13/15, 6/8, 49/60, 24/28 in the table's order). The cohorts overlap: the prior audit identifies **80 distinct conditions across 52 UTC hour clusters** for persistent quotes. At the fixed first-leg quantity, only **7/13, 2/6, 2/49, 1/24** persistent rows respectively had a delayed second-leg quote costing at most 10 USDC. These are still book-depth quotes, with no observed second order, fill, queue position, fee payment, payout, or realized pair PnL. A larger permitted second-leg budget or a smaller initial position would be a *different* paper capital policy and has not been silently assumed here.

**Conclusion:** the hypothesis is partly right in a descriptive sense: a multi-minute price move, often with a wider candle near the second quote, frequently accompanies the cheapening opposite leg. It is **not** supported as a pre-entry rule that a high-volatility candle identifies profitable pairs. The more useful next research question is whether a strictly causal, capital-bounded second-leg executor could obtain those prices after delay, using the already frozen paper collection; no thresholds or live trades are proposed by this report.
