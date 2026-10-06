# Hourly blend50: exploratory maker entry diagnostic

As of **2026-10-06 16:48:40 UTC**, this is an offline counterfactual on the independent hourly Limitless BTC/ETH markets. It does not modify the funded frozen benchmark, market-blend50 shadow, inventory v2, or their holdout, capture schedule, and fees. No orders were placed. The maker rule was defined after this holdout had begun; these 29 decisions are **exploratory** for that rule, not its untouched holdout.

## Source and fixed calculation

- Nineteen consecutive completed-success `main` capture artifacts, runs **37387593991–37491277603**, cover 2026-10-05 23:17:16 through 2026-10-06 16:48:40 UTC. Every downloaded ZIP SHA256 equals its GitHub artifact digest. Summary timestamps have no gap greater than 20 minutes or overlap. The machine evidence records every run, artifact, hash, decision-book and future-frame line proof.
- Use each of the 29 independent hourly decision episodes starting October 6 UTC, its frozen Binance `p_up` and the exact first decision book. From that book, `market_mid=(YES best bid+YES best ask)/2`, `p_blend50=(p_up+market_mid)/2` as in PR #54. Each decision book matches its episode time within 20 ms and its YES token.
- Wait the existing 1.5 seconds. Use the **first subsequent REST book request** begun in the existing 30-second window, including failures; do not replace a failed attempt. In this sample all 29 first requests succeeded, beginning 16.43–28.70 seconds after the decision. Join that first book's displayed best bid on one side, without crossing the spread. Select the side with maximum estimated ROI among those satisfying `p_side / bid - 1 >= 3%`; zero maker fee only if an order actually rests. Both sides qualified once. No rebate is assumed.
- A later observed WebSocket book within the same window whose opposite best ask reaches the hypothetical bid is a **price-cross observation**, not an executed trade. Book frames have no order ID, queue position, or reliable proof of our hypothetical fill. A trade can also hit our bid without an ask-cross in a snapshot. No cross is therefore not a proof of no fill.

## Result

| Measure | Count |
| --- | ---: |
| Independent decisions with exact source book and first later book | 29 |
| At-touch quotes passing the 3% model hurdle | 29 |
| Later price-cross observations within the window | 5 |
| Later WebSocket frames, without observed cross | 23 |
| No later frame in the remaining window | 1 |
| Confirmed maker fills or realized PnL | **0 confirmed; PnL unknown** |

The five crossings are a diagnostic subset, **not an upper bound on true possible fills**. Actual counterfactual fills have no useful identified rate from this capture: zero to 29 remains compatible with the observed book frames. The first possible posted quote was much later than the 1.5-second eligibility delay because the next successful REST book was observed 16.75–28.86 seconds after the decision; one case had no subsequent WebSocket frame. The frozen hourly source episodes over these 29 conditions had 22 model `NO_TRADE`, six settled model fills and one `SKIP`; these are not maker fills or the blend50 shadow's PnL.

At a hypothetical gross $10 per crossed bid, assuming all five crosses filled in full and were held to the observed outcome, the arithmetic would be **+$40.36**, comprised of one +$68.13 winner, one +$2.24 winner and three −$10 losers. This calculation conditions on future crossings, ignores queue/partial fills and is **not a strategy return, bound, or paper PnL**. It illustrates how one low-priced winner dominates an apparent result. The machine evidence intentionally leaves `realized_pnl=null`.

## Decision

Maker entry can improve the quoted price and remove the maker fee on a genuinely resting order, but these data cannot establish fill probability or positive net expectancy. Keep this diagnostic separate from the frozen paper books. A prospective maker comparison needs a predeclared rule and fresh, independent validation period, plus order-level or calibrated queue/trade evidence; public snapshots alone are insufficient to upgrade the five crosses to fills. Do not count rebates or change the current model/holdout on this result.

Reproduce with `python research/limitless_hourly_maker_diagnostic.py --manifest <ordered-downloaded-main-ZIP-manifest.json> --out <result.json>`, using entries with the GitHub `run` and `artifact` metadata and local `download.path`. The machine evidence in `research/evidence/limitless_hourly_blend50_maker_2026-10-06.json` pins the exact archives and raw line fingerprints.
