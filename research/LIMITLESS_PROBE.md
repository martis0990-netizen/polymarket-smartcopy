# Limitless SmartCopy forward paper study (v1 frozen 2026-10-03)

This study is separate from Polymarket v5. It has no signing keys, no order submissions, and no live capital.

## Collection contract

- UTC capture window: 2026-10-03 through **2026-10-10 09:00 UTC**. The workflow stops collecting at that instant and disables its hourly schedule on the next scheduled run.
- GitHub Actions schedules a start at minute 17 of each hour and each completed main-branch observation dispatches the next one. Each full job records at most 55 minutes, polling at 30-second intervals. Scheduled starts can be late or absent; chained starts can fail. The study reports observed coverage and treats gaps as gaps; it never fills them from historical source prices.
- Fixed initial watchlist: `0xff612b93bf130a2bccdf303e360e89d225685e71`, `0xc2faf128201d89cba789c1dde5424d49bd75e44e`, `0x61761b4ff620607295e894f7c529a4de35dec3b4`. The public all-profile feed is a discovery channel; its other wallets do not enter the predeclared watchlist evaluation.
- Family: BTC/ETH Up/Down, 5-minute, 15-minute and hourly markets. Each successful poll, source record, first observer timestamp, and current YES book is written to a JSONL artifact. A NO book is derived by price inversion.
- A book is fetched only for a crypto buy with source event time at or after the current job start and with a market that is not already marked closed. The book is fetched after detection. Missing/inactive/AMM books are unexecutable observations, not assumed fills.
- Each run uploads its own artifact for 14 days. The first artifacts must be retrieved before expiry for the final analysis.

## Feasibility gate

Count distinct source exposure decisions by wallet and market, not raw fills, events or repeated polls. Report the first-seen delay distribution, the fraction with a usable contemporaneous book, and per-wallet observation coverage. Require at least 90% time coverage in the relevant watchlist history poll stream and at least 60 independent eligible entry episodes across the watchlist to treat a paper comparison as informative. These are proposed feasibility thresholds, not statistical proof of edge. If they fail, publish `INSUFFICIENT_DATA` and stop.

## Paper comparison after collection

Reconstruct source ENTER/ADD/REDUCE/EXIT/hedge intent from public history before labeling copyable actions. Ambiguous or paired strategy is UNKNOWN and SmartCopy skips it. Use a fixed 10 USDC hypothetical follower budget per eligible episode. A buy takes only visible ask depth at or after `first_observed_time`; if it cannot fill at a predeclared max price and size, mark it skipped or partially filled. Apply the current documented fee semantics, conservative timing and market resolution/exit, and record explicit assumptions. Never enter at source price or midpoint.

Evaluate BlindCopy and deterministic SmartCopy on identical eligible episodes and identical execution assumptions. Use early data for discovery and the later period for untouched evaluation; freeze the filtering rule before evaluating the later period. Include no-follow control, net return, drawdown, coverage, and concentration by wallet and market. If follower expectancy is not positive and SmartCopy does not beat BlindCopy on unseen episodes, report `NO_EDGE_STOP`; no trading code follows from this study.

This collection workflow does not by itself produce a PnL result. GitHub-hosted schedules can be delayed; hourly 55-minute jobs cannot claim continuous observation. The archived data and gaps must be audited before applying the paper comparison.

## Decoder correction, 2026-10-03

Architect: actual history records carried numeric outcomeIndex but the observer left outcome unknown. Decode 0=YES/Up, 1=NO/Down only for BUY/SELL records on explicitly titled Up or Down markets with two outcomeTokenAmounts and no group object. Claims/default indices, custom/group markets, invalid indices and contradictory labels remain unknown. Explicit YES/NO labels and Up/Down labels on Up/Down markets are normalized. Preserve original raw records; the audit applies the same deterministic decoder to archived raw observations without any later market lookup. The cohort, times, feasibility thresholds and model remain fixed.

Coder: add operation, condition/order identifiers and outcome provenance. Record book request-start plus observed ask minus source price as a descriptive gross quote gap; it is never a fill or PnL. Reject nonfinite, out-of-range, locked and crossed binary books. The audit selects the earliest valid post-observation book rather than the last duplicate and reports order-side groups separately from the existing 60s episode proxy. Order groups are not independent intents. Verified raw evidence in artifact 11275396509 shows the same CLOB tradeEventId UUID embedded in feed id clob:<UUID>:<profileId>. The audit canonicalizes only this exact format with matching numeric profileId and BOUGHT/SOLD type, scoped by wallet. Both raw source records remain archived; the earliest observation wins. Later condition/order IDs may support retrospective grouping with their own observation timestamp, never an earlier execution price. Other feed event types are not cross-deduplicated speculatively.

Test Engineer / Reviewer: deterministic mapping, ambiguous claims/groups, conflicting labels, zero price, separate fills, order grouping and invalid books; real PR smoke. The public history API documents Limit Buy/Limit Sell as maker fills, Market Buy/Market Sell as taker fills, Buy/Sell as AMM trades and Claim as redemption. Maker fills do not prove a market-making strategy or follower execution at that price.

References: https://docs.limitless.exchange/api-reference/markets/get-market and https://docs.limitless.exchange/api-reference/portfolio/history

## Observed entry availability, 2026-10-03

Measured gap: top-of-book quote gaps do not show whether a follower's fixed budget fits the visible depth. After each observer segment, `limitless_entry_availability.py` writes `entry_availability.json` and `.md` using existing raw captures only. No extra API requests or orders.

Canonicalize verified feed/history duplicates by wallet and trade UUID, preserve earliest observation, and evaluate the first book attempt after detection. A failed first attempt cannot be replaced by a favorable later snapshot. Report detection delay, detection-to-request delay, HTTP latency and source-to-receipt delay. Unknown sides, missing books, errors and requests begun before detection remain separate statuses. Fixed watchlist and discovery-feed wallets have separate denominators. These are observed buy records, not independent intents; cross-segment aggregation must deduplicate again by canonical ID.

Walk YES asks (or NO asks derived from YES bids at 1-price) for a diagnostic 10 USDC budget. Raw CLOB share sizes use 6 decimals. Report gross VWAP, visible capacity at/below the source price, insufficient depth and price deterioration. A 3% contract deduction is an explicit conservative illustration, not a verified account-specific fee or a comparison of equal net fee bases. Source execution and follower budget are different quantities. The budget assumes the studied USDC markets; this diagnostic does not generalize to other collateral currencies.

A supported depth quote is not an execution, approved max price, copy signal or profit. REST has no guaranteed freshness bound; matching-time depth, cancellations and queue priority remain unknown. No later wallet inventory, source PnL or resolution is used to improve an earlier entry. Unknown strategy remains SKIP.

Primary schema reference: https://docs.limitless.exchange/api-reference/trading/orderbook

## Cross-segment progress audit, 2026-10-03

Measured gap: the final audit previously waited until Oct10 and per-run entry reports could double-count a trade. The existing entry diagnostic now accepts main observer ZIP archives and an explicit UTC as-of time. Re-decode raw source records, retain earliest canonical wallet/trade detection and first book attempt across all archives, then report by wallet and separately by fixed cohort/discovery. Historical first detection cannot turn into a fresh entry through a later duplicate. Unknown request-start timestamps in older captures remain unverified.

Credit only the union of 30-second intervals immediately before successful fixed-wallet history polls, clipped to the elapsed study window. Report coverage, the largest uncredited gap including leading/trailing gaps, archive errors, and excluded historical buys. This describes collection coverage, not complete trade discovery. It does not change the frozen full-week feasibility gate or its 60s episode proxy.

The existing final audit workflow also runs a progress snapshot on PR/push/manual runs and after a completed trusted-main observer run. It downloads main observer artifacts only, saves a run/SHA/download-status manifest (including unfinished/missing jobs), and archives aggregate JSON/Markdown. PR runs validate code using main research data but do not join the study dataset. Independent-market final aggregation and disabling the final schedule remain restricted to the study cutoff.

Current integration limitation: main observer run 37129700774 started before PR27, and the PR27 main push is queued behind it. Existing raw archives can establish source detection delay but lack the new request-start field; no retroactive follower fill is reconstructed. Validate a future main archive before claiming the new segment report is active.
