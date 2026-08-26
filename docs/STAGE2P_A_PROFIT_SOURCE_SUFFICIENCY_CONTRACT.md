# Stage 2P-A — Public Profit-Source Data Sufficiency Contract

Status: FROZEN BEFORE querying Stage 2P-A result rows

## Purpose

Determine whether Polymarket's public Activity API exposes enough non-TRADE evidence to support a later Bonereaper profit-source decomposition. This stage is a data-sufficiency test, not a PnL calculation.

## Frozen subject and interval

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- inclusive UTC interval: `2026-08-25T00:00:00Z` through `2026-08-25T23:59:59Z`
- Unix range: `1787616000..1787702399`
- Stage 2H target-market evidence: 763 BTC/ETH 5m/15m Up/Down condition IDs from the frozen Stage 2H artifact.

Changing the wallet, date, activity-type set, or summary fields below creates a new contract version.

## Frozen public Activity types

Query exactly these activity types:

`REDEEM,REWARD,MAKER_REBATE,TAKER_REBATE,SPLIT,MERGE`

Do not add `TRADE`, deposits/withdrawals, referral rewards, yield, or conversion after inspecting results.

The query is historical `BACKFILL` evidence. `first_observed_time` is ingestion provenance only and MUST NOT be interpreted as historical observation latency.

## Retrieval contract

- use the same complete timestamp-window pagination mechanism as Stage 1.1
- empirical/official Activity offset cap: 5000 per timestamp window
- `sortDirection=ASC`
- recursively split dense timestamp windows
- fail closed when completeness cannot be proven
- preserve raw rows
- deterministic source-time sort and immutable dedup only

## Frozen summary fields

For each requested activity type report:

- row count
- sum of `size`
- sum of `usdcSize`
- distinct non-empty condition IDs
- distinct non-empty transaction hashes
- first/last source timestamp

Also report:

- total requested-type row count
- counts of rows whose `condition_id` overlaps the 763 Stage 2H target condition IDs
- per-type target-condition overlap counts
- count/share of Stage 2H target conditions with at least one REDEEM row during this same-day interval
- REDEEM `usdcSize` total overall and on Stage 2H target conditions
- REWARD `usdcSize` total
- MAKER_REBATE `usdcSize` total
- TAKER_REBATE `usdcSize` total
- SPLIT and MERGE row/token totals

## Interpretation boundaries

`REDEEM usdcSize` is observable redemption cash inflow for rows returned by the API, not profit. Acquisition cost is separate.

`REWARD`, `MAKER_REBATE`, and `TAKER_REBATE` `usdcSize` values are observable activity amounts for that same-day interval only. Stage 2P-A does not assume they represent the wallet's lifetime rewards or all economics attributable to trades opened that day.

Same-day absence of a REDEEM or reward row does NOT mean the economic event never occurred: resolution/redemption/reward posting can happen outside the frozen day.

SPLIT/MERGE are inventory transformations, not profit.

## Sufficiency verdicts

Exactly one:

- `PUBLIC_PROFIT_SOURCE_ACTIVITY_PRESENT` — at least one requested non-TRADE activity row is returned and completeness is proven.
- `PUBLIC_PROFIT_SOURCE_ACTIVITY_EMPTY` — completeness is proven and zero requested rows are returned for the frozen day.
- `DATA_INSUFFICIENT` — completeness, parsing, or public API semantics cannot be proven.

`PUBLIC_PROFIT_SOURCE_ACTIVITY_PRESENT` does NOT authorize a PnL calculation. It only permits a separately frozen Stage 2P-B accounting contract.

## Forbidden claims

Stage 2P-A cannot establish:

- total wallet PnL
- strategy PnL
- maker status
- market making
- guaranteed arbitrage
- reward causality
- settlement PnL
- copyable/residual edge
- live latency

## Gate

Pass requires deterministic tests plus one real run on the frozen wallet/date. The real run must preserve exact requested types, prove pagination completeness, verify all rows are `BACKFILL`, and materialize a manifest with artifact hashes.