# Bonereaper settlement evidence — frozen contract

Status: FROZEN BEFORE PROFIT-SOURCE INTERPRETATION

Wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`

Primary activity interval: `2026-08-25T00:00:00Z` through `2026-08-25T23:59:59Z`.

## Purpose

Collect closed-position rows whose `closed_time` falls inside the frozen UTC day so the already-frozen paired-inventory decomposition can later be joined to realized closed-position evidence by market/asset. This stage collects and verifies evidence only; it does not attribute profit to paired inventory, rewards, directional exposure, or copyability.

## Retrieval rule

Use `/closed-positions` sorted `TIMESTAMP DESC`, page size 50. Continue pagination until at least one page proves the lower boundary has been crossed (`closed_time < start`). Keep only rows with `start <= closed_time <= end`.

A page containing only rows newer than `end` does not prove completeness and pagination continues. Rows with missing `closed_time` are not silently treated as in-range; their count is reported.

If the API offset budget is exhausted before crossing the lower boundary, fail closed with no completeness claim.

API contract used by this stage: `limit<=50`, `offset<=100000`, sort field `TIMESTAMP`, direction `DESC`.

## Required outputs

- in-range closed-position count;
- distinct condition IDs and assets;
- realized PnL sum for the bounded closed-position rows;
- positive/negative/zero row counts;
- missing timestamp count encountered while paging;
- pages/last offset fetched;
- first/last in-range close time;
- evidence manifest with requested range and completeness status.

## Hard prohibitions

- no inference that closed-position realized PnL equals total wallet PnL;
- no assumption that rewards/rebates are included or excluded unless independently proven;
- no attribution of a closed-position PnL row to matched-pair vs residual inventory yet;
- no COPY/WATCH/SKIP decision;
- no outcome-conditioned threshold tuning.
