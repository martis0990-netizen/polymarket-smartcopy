# Hourly maker diagnostic: public finalized trade tape

As of **2026-10-06 17:32 UTC**, a separate GitHub Actions probe fetched `GET /markets/{exact-slug}/events` for all 29 hourly BTC/ETH decisions in the maker diagnostic. No credentials, orders, or changes to the ongoing capture workflow were involved.

## Provenance and completeness

- Source: 19 digest-verified `main` capture ZIPs through run [37491277603](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37491277603), plus the frozen [maker diagnostic](LIMITLESS_HOURLY_BLEND50_MAKER_DIAGNOSTIC_2026-10-06.md).
- Public trade probe: [run 37504223682](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37504223682), [artifact 11431695483](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37504223682/artifacts/11431695483), ZIP SHA256 `f8eb9d28bb835e9caf5db641d4b012f0a7e6a5aa3f3021ba00037d12a61a9fda`.
- All **29/29** markets had complete pagination and an identical first-page recheck; no API error, page cap, or drift. The probe retained all public event fields needed for this comparison, each page's request/receipt time and raw response hash. It counted **807** distinct finalized trade records across the 29 markets.
- Limitless documents this endpoint as **finalized MINED CLOB trades**, newest first; `side` means *taker* side (`0=BUY`, `1=SELL`), `matchedSize` uses 6 decimals, and successful pages can be cached. It does not return order placement, cancellation, or our hypothetical order's queue position. See the [official API reference](https://docs.limitless.exchange/api-reference/trading/market-events).

## Thirty-second quote windows

We compare the event's `createdAt` field with the interval from the first eligible REST book response until 30 seconds after the original decision. The API documentation does not establish `createdAt` as a contemporaneously observable execution timestamp, so this is **retrospective alignment**, not a live execution replay.

| Observation | Independent conditions / records |
| --- | ---: |
| Hourly market conditions | 29 |
| Public trades with `createdAt` in the individual quote window | 3 records, across 3 conditions |
| Matching the hypothetical side and at or through the quoted price | 2 records, across 2 conditions |
| Book price crosses in the previous diagnostic | 5 conditions |
| Confirmed hypothetical maker fills | **0** |

The two price/side compatible records were:

| Market and window | Hypothetical quote | Finalized trade | Visible same-price size ahead at first book |
| --- | --- | --- | ---: |
| BTC, 13:30 UTC | Buy NO at 0.757, the complement of YES ask 0.243 | YES taker BUY at 0.243, 0.093 YES shares at 13:30:26.386 | 0.093 YES shares offered at 0.243 |
| BTC, 15:30 UTC | Buy YES at 0.082 | YES taker SELL at 0.082, 9.897555 shares at 15:30:28.526 | 20 YES shares bid at 0.082 |

The first book lines are artifact `11417994486`, line `22338`, and artifact `11425277513`, line `33769`, respectively; their SHA256 fingerprints and the exact trade hashes are in the [machine evidence](evidence/limitless_hourly_maker_tape_match_2026-10-06.json). Both public trade sizes are no larger than the displayed same-price queue already ahead at the first snapshot. If that queue stayed in place and price/time priority applied, our hypothetical joined bid would not fill on those trades. Cancellations, replenishment, other unobserved changes, actual order acceptance, and the YES/NO complement implementation are unverified. This is a conditional observation, not a queue reconstruction.

Among the five later book-price crosses, only **one** has a side/price compatible finalized trade in its 30-second window. Another compatible trade occurred **without** a visible book cross. Four crosses have no such trade in the public finalized tape window. Thus price crossing is an unreliable fill label in either direction. The two observed compatible trade sizes together represent at most **$0.882** of gross quote-priced turnover if all of their volume had gone to us; that conditional arithmetic is not a bound on all unseen/off-chain executions and is not PnL.

## Decision and forward rule

The venue offers useful retrospective trade data, but public pages still cannot prove our place in the queue or a maker fill. Keep maker fills and PnL **UNKNOWN**; neither the earlier five crosses nor these two records promote the maker strategy. The maker quote diagnostic stays separate from all funded paper ledgers.

For a new, independent period after the current hourly holdout, the read-only candidate is frozen as follows: on each first hourly decision, blend frozen Binance `p_up` 50/50 with the contemporaneously observed YES book mid; after the existing 1.5-second delay take the first subsequent REST book request inside 30 seconds, including a first failure; join the best displayed bid on the side with greatest estimated `p_side/bid - 1` that meets the existing 3% hurdle, at a hypothetical gross budget of $10. Zero fee is conditional on truly resting, and no rebates are assumed. No order or paper fill is credited from public snapshots/trades alone. This post hoc rule **cannot reuse October 6 observations as its untouched holdout**. No new schedule, capital ledger, or order capability is enabled by this note.

Reproduce the tape match with `research/limitless_hourly_maker_tape_analysis.py --diagnostic <maker-diagnostic.json> --probe-zip <artifact-11431695483.zip> --state-zip <main-artifact-11428826971.zip> --out <result.json>`; compare all three SHA256 values in the machine evidence.
