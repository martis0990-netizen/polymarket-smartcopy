# Limitless hourly: chronological market residual replay (7 October 2026)

## Scope and provenance

This is a research-only replay of the **existing** 96 SHA256-verified main capture ZIPs. The last final hourly archive is artifact `11470560416`, ZIP SHA256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`. The full source ledger and frozen bot results are in `LIMITLESS_HOURLY_ALL_DECISIONS_2026-10-07.md` and its machine evidence. The single candidate protocol was committed **before** computing its PnL as [`0f993de`](https://github.com/martis0990-netizen/polymarket-smartcopy/commit/0f993de4f9ab344932222c1de89ac25f4a1e1787), in `LIMITLESS_HOURLY_WALKFORWARD_PROTOCOL_2026-10-07.md`.

For each of 162 hourly conditions, the protocol blends the frozen Binance probability with the contemporaneous Limitless YES bid/ask midpoint **as a forecast only**. One blend weight minimizes binary log loss on earlier conditions whose payouts had already been observed by that decision. With no prior outcomes the weight is 0.5. It applies the original 3% contract fee, 3% entry hurdle, 10 USDC per-entry budget, 1.5-second venue wait, 30-second expiry, full visible ask depth and first eligible subsequent request; there are no retries or midpoint fills. There was one prespecified candidate and no PnL-based parameter search. No production rule, holdout boundary, source collection, or order workflow changed.

## Replay result

| Measure | Discovery | Previously inspected holdout |
|---|---:|---:|
| Decisions / observed outcomes | 104 / 104 | 58 / 56 |
| Candidate NO_TRADE / SKIP / hypothetical FILLED | 90 / 2 / 12 | 55 / 1 / 2 |
| Settled candidate fills / winners | 12 / 8 | 2 / 0 |
| Candidate hypothetical settled PnL, USDC | **+72.448614016** | **−18.050673826** |
| Frozen MODEL settled PnL on respective periods, USDC | +23.085530854 | −74.378700028 |
| Frozen constant50 control settled PnL, USDC | +17.309766642 | −71.992366613 |
| Candidate forecast Brier / log loss | .206417 / .608531 | .165233 / .498756 |
| Active UTC-hour clusters / positive clusters | 10 / 6 | 2 / 0 |

The two largest discovery winners contributed +51.071221619 and +42.423127453 USDC. **The other ten discovery fills together lost 21.045735056 USDC.** Both later hypothetical holdout fills lost, despite the candidate losing less than the frozen hourly model. The old holdout has already been inspected repeatedly; it is not a fresh independent confirmation. In the prior full decision audit, the market midpoint alone had holdout Brier .1579, better than this blend's .1652, but midpoint is never treated as an executable price.

## Causality and execution checks

- Training contains only earlier conditions with `settled_at < decision_at`, including NO_TRADE conditions; BTC and ETH from the same hour cannot train each other before payout. The starting weight is .5. The weight may approach an endpoint with sparse earlier outcomes; no weight was fitted to a future outcome or trade PnL.
- The first qualifying public request after the entry delay was recovered for 160/162 decisions; two have no such request. For the candidate's 14 hypothetical fills, the first request was a book, the side's target shares fit at the decision cap, and the payout was observed. Three other eligible candidate decisions permanently SKIP for insufficient first-attempt depth or a failed price bound. The two missing first requests do not create candidate fills.
- As a cross-check, applying the extracted first-attempt books to the frozen original MODEL and constant50 decision ledger recovered their reported fill/skip outcomes and every reported entry cost, without a cost discrepancy. This checks the extraction and arithmetic, not actual execution.
- These are public book snapshots and hypothetical taker fills; queue position, actual orders, adverse selection and funded portfolio feasibility were not established. One control position remains unresolved and is excluded from settled PnL. Do not sum cumulative archive reports or overlapping variants as independent trades.

## Decision

**No robust profitable candidate has been established.** The apparent discovery profit is concentrated in two outcomes and the old holdout is negative. Preserve the frozen hourly benchmark and the paper-only limits. This replay supports studying where the Binance forecast differs from the market; it does not justify maker deployment, a new threshold, or live trading. Any further candidate requires a separately fixed protocol and a genuinely new forward sample before a profit claim.

Machine-readable row evidence: `research/evidence/limitless_hourly_walkforward_2026-10-07.json`; raw archived sources are identified by artifact, line and SHA256 in each row.
