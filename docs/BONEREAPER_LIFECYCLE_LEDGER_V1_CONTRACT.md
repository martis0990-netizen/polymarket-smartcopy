# Bonereaper lifecycle ledger v1 — frozen contract

Status: **FROZEN BEFORE LIFECYCLE ACTIVITY RETRIEVAL**

## Purpose

Reconstruct the complete public activity ledger for the exact five conditions in prospective
settlement v1, from the earliest target market open through the already frozen settlement cutoff.
Test whether the short clean capture is representative of terminal inventory and whether public
flows can reconcile outcome-token burns at redemption.

This is a public-flow accounting test, not an assertion of wallet PnL.  Data API trade cash can
omit or encode fees differently from decoded receipts; rewards, rebates, transfers, deposits,
withdrawals and activity outside the frozen interval remain excluded.

## Immutable identity and interval

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- target conditions: exact five unique condition IDs in economics rows SHA256
  `8c848d320e2cc53e931fb408d493166f7ccb784416a56bcc4e8bdfdb745fb32f`
- settlement rows SHA256:
  `76e1dbae9cd9ef7708cde1976afa6ec13bc9018134483b87c5b91f9c599617b8`
- interval: Unix `[1787841600, 1787855700]`, inclusive
- requested activity type string: exact `TRADE,SPLIT,MERGE,REDEEM`
- source order: ascending timestamp from the complete range collector

The start is the earliest epoch encoded in the frozen target slugs.  The end is the settlement-v1
cutoff fixed before its retrieval.  The collector must fail closed if pagination completeness
cannot be proven.

## Outcome ledger

For each condition and ordered outcome (`Up`, `Down`), report:

- TRADE BUY tokens and USDC;
- TRADE SELL tokens and USDC;
- SPLIT tokens credited to both outcomes;
- MERGE tokens debited from both outcomes;
- outcome-specific REDEEM tokens burned and USDC paid;
- public-flow token delta before redemption;
- post-redemption flow balance.

The deterministic token equation is:

`flow_balance = BUY + SPLIT - SELL - MERGE - REDEEM`.

A non-zero balance is not silently called an error or a position.  It may represent unredeemed
ending inventory, transfers not represented by the requested activity types, trades before the
frozen start, or API/schema limitations.  A negative balance proves that redemption/sales consumed
more tokens than the included public acquisitions and therefore that the bounded capture cannot
explain the lifecycle.

## Cash accounting

Report a pre-fee public cash flow only:

`SELL usdcSize + MERGE usdcSize + REDEEM usdcSize - BUY usdcSize - SPLIT usdcSize`.

If SPLIT or MERGE rows do not provide a usable `usdcSize`, preserve them but mark cash
reconciliation incomplete.  Never label this value fee-adjusted, realized PnL or net expectancy.
Exact fee reconciliation requires subsequent Polygon receipt decoding.

## Capture representativeness

For every condition/outcome, compare lifecycle TRADE BUY size with the exact-bound decoded BUY size
from SHA256 `1cbbe07f740682e1f6542d1ed70d7d2b8b63a9099a3366382aa3e3b1bff2ab31`.
Report capture share `bounded_buy_size / lifecycle_buy_size` when the denominator is positive.
Do not compare costs across these two artifacts unless fee basis is made identical.

## Validation

- exact five condition/slug identities must match settlement rows;
- activity must be BACKFILL evidence for the frozen wallet, interval and requested types;
- TRADE requires side BUY/SELL, outcome Up/Down and non-negative size/USDC;
- REDEEM requires outcome Up/Down;
- target SPLIT/MERGE rows may omit outcome and apply their size equally to both outcomes;
- raw all-condition rows and target rows are preserved;
- duplicate exact activity identities are rejected after collector deduplication;
- no target condition discovered after retrieval may be added.

## Stopping and outputs

Status remains `COLLECTING` until 30 resolved independent conditions have complete lifecycle
ledgers.  A new output directory must not pre-exist.  Write raw requested activity, normalized
target activity, outcome ledgers, condition summaries, capture comparison, aggregate summary and a
manifest binding all input/output SHA256 plus contract and code commits.  Validation failure
withholds a clean manifest.
