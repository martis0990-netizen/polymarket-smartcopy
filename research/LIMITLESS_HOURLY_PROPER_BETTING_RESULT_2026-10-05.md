# Hourly size comparison — discovery result, 2026-10-05

As-of 2026-10-05 10:12:54 UTC. 45 ZIPs from completed-success main jobs, each SHA256 verified against GitHub artifact digest; captured interval Oct3 17:34:42 to Oct5 10:12:49 UTC. 77 observed decision conditions /40 UTC hour clusters, 75 resolved probability observations; holdout0. This bounded corpus excludes earlier decisions, not the entire hourly history. No account legacy carry or cumulative report summation.

| Funded first-attempt comparator | Fixed size | Brier-inspired size |
|---|---:|---:|
| Starting cash USDC |100|100|
| Settled simulated trades |13|14|
| Settled spend USDC |112.696525109|11.688906789|
| Settled PnL USDC |+53.372829291|+2.461790771|
| Return on settled spend |47.36%|21.06%|
| Current cash USDC |153.372829291|102.108470727|
| Open claim cost basis USDC |0|0.353320044|
| Maximum settled-equity drawdown USDC |34.735634612|2.662338391|

62 frozen model NO_TRADE in both. Fixed has2 price/depth failures; smaller size passes those same first books, with one additional claim still open. Same decision/attempt does not imply same fill availability at different quantities. Never assign zero PnL to that open claim. Matched75 resolved conditions: proportional-minus-fixed PnL **−50.911038520 USDC**.

On the same75 resolved forecasts, model Brier **0.2361034171**, market decision-book midpoint **0.2387614267**; descriptive advantage only0.0026580096. No inference of statistical significance or executable profit guarantee. Midpoint is never used for fills.

One fixed trade contributes **+51.071221619 USDC** (condition `0xdfd4c7c99214c28d00ee5f6c8babb7a3d3a7f2e598c0c4848c9f5be4861bf867`). Removing it descriptively leaves +2.301607672. Two large payouts dominate this small sample. Lower proportional drawdown primarily accompanies much lower spend, not demonstrated better sizing skill; proportional return on settled spend is also lower here.

**Conclusion: no demonstrated improvement from this predeclared proportional sizing on the observed sample.** Do not promote it or call the existing model reliably profitable. The fixed comparator is a separate freshly funded first-attempt replay, not the cumulative historical hourly account or inventory-v2 runtime. Execution assumes REST depth, omits competing takers/matching/cache risk; settled-equity drawdown does not value open claims at liquidation prices.

Code/protocol: [v1](LIMITLESS_HOURLY_PROPER_BETTING_V1.md). Machine evidence retains per-condition decisions/attempts, cash events, source hashes and run/artifact/ZIP digests. Independent ledger sum/idempotence/cash checks PASS, nine focused tests PASS; cloud CI must be checked separately. No original hourly or inventory code, thresholds, fees, holdout or workflow changes.
