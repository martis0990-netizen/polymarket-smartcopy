# Limitless 15-minute feasibility snapshot — 2026-10-04

Status: **DATA FEASIBILITY ONLY / NO 15M SIGNAL OR PNL**. This note does not change the frozen hourly-v1 benchmark, inventory-v2, their fees, timing, cohort, holdout, or capture workflows. Public Limitless and Binance data only; no orders.

## Reproducible observation

Main capture [run 37207365378](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37207365378), artifact 11306172779, ZIP SHA256 `8d41ac305694528fe09cbb104b085085d57ca478fb3de03974508f6ba40f12cf`. The segment covers 2026-10-04 approximately 13:55–14:50 UTC. Its `capture.jsonl.gz` contains 10 unique detailed BTC/ETH 15-minute market slugs, 342 REST book envelopes and 98 oracle-candle response envelopes associated with those slugs. The latest observed details say RESOLVED with a non-null winningOutcomeIndex for 7 of the 10; the other 3 say FUNDED. This is **one segment**, and two markets beginning 13:45 were already in progress when capture started. Counts of snapshots are not counts of independent trials, decisions, executable fills or profitable trades. Settlement must be checked against the actual time and payout fields per condition.

The inspected 15-minute market descriptions compare Chainlink BTC/USD or ETH/USD **60-second TWAP at expiry** against the Price to Beat from **the same stream at window open**. Oracle-candle responses are marked `source: chainlink`, `interval: 1m`; received candle arrays can describe times earlier than receipt and cannot be made causally available before receipt. The underlying stream, scaling, exact report/tolerance and market-specific rules require explicit validation before a probability model. The official [Limitless resolution documentation](https://docs.limitless.exchange/user-guide/market-resolution) says the market description is authoritative, compares TWAP at the two boundaries, and uses a specified fallback window if the exact deadline report is missing.

## Scope decision

The frozen hourly model uses Binance spot candle open, a midpoint decision about 30 minutes into a one-hour window, and a Binance-based volatility forecast. That timing is after a 15-minute market closes; the outcome is also a different oracle quantity. Running the hourly state machine on 15-minute markets or relabeling 15-minute outcomes from Binance closes would be invalid.

Next bounded work, in order:

1. Audit all distinct completed main capture ZIPs with run/artifact/hash provenance: deduplicate by condition, check segment gaps, first observation relative to open, oracle response source/receipt time, first book requests, depth, taker delay, and market-specific resolution/payout. Track missing or malformed data as UNKNOWN, and keep partially observed windows separate.
2. Validate raw Chainlink candle values and scaling against Price to Beat and observed settled market outcomes. Identify whether exact boundary stream reports and the stated tolerance are reproducible; if not, use the exchange's observed winningOutcomeIndex as outcome and leave independent oracle reconstruction UNVERIFIED.
3. Before calculating historical trading returns, write a separate, explicitly versioned 15m probability/entry/fee/first-attempt paper protocol with a decision time **inside** the window, availability constraints, no future candles, independent 15-minute clusters, and a later untouched prospective holdout. The historical archive can check mechanics and supply discovery diagnostics, not validate parameters chosen after seeing its outcomes.
4. Show independent conditions, missing windows, decisions, attempted and filled paper entries, execution assumptions, settlement and uncertainty. Until those exist, 15m profitability remains **INSUFFICIENT_DATA**.

Structure H1/M15 annotations may be recorded causally as diagnostics; the current H4/H1 warmup is incomplete and cannot justify a trading filter. No thresholds or strategy have been selected by this snapshot.
