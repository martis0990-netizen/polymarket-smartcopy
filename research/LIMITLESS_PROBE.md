# Limitless SmartCopy forward paper study (v1 frozen 2026-10-03)

This study is separate from Polymarket v5. It has no signing keys, no order submissions, and no live capital.

## Collection contract

- UTC capture window: 2026-10-03 through **2026-10-10 09:00 UTC**. The workflow stops collecting at that instant and disables its hourly schedule on the next scheduled run.
- GitHub Actions starts at minute 17 of each hour; each job records at most 55 minutes, polling at 30-second intervals. Scheduled starts can be late or absent. The study reports observed coverage and treats gaps as gaps; it never fills them from historical source prices.
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
