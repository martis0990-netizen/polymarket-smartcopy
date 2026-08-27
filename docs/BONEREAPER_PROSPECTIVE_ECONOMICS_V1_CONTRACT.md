# Bonereaper prospective economics v1 — frozen contract

Status: **FROZEN BEFORE THE FIRST PROSPECTIVE ECONOMICS CALCULATION**

## Purpose and boundary

Measure whether Bonereaper's observed inventory is economically explained by pairs bought below
one dollar, and whether maker and taker fills have different short-horizon markout.  This is a
descriptive research diagnostic.  It does not infer a merge, queue position, unrealized inventory
value, copyability, or authorization to trade.

## Immutable inputs

The analyzer accepts only a clean prospective bundle v5 and SHA-verifies:

- the root bundle manifest;
- current and safe public-book child manifests and token metadata;
- both book-level and gap artifacts;
- fee-aware decoded receipt rows.

A receipt is included only when its exact `asset_id`, condition and outcome agree with one unique
bound token.  Ambiguous roles, duplicated token bindings and SHA mismatches fail closed.

## FIFO pair construction

Only BUY fills with an unambiguous corrected role are used.  Within each condition, order fills by
`(source_second, block_number, event_log_index, transaction_hash)`.  Maintain independent FIFO
queues for Up and Down.  Every arriving fill is matched against the oldest unmatched opposite lot;
partial lots remain in their queue.  Each newly matched chunk records its size and the two source
fills.

For each allocated leg:

- base USDC cost is `maker_amount_filled / 1e6`;
- decoded fee is `fee / 1e6`;
- fee-adjusted cost is base cost plus decoded fee;
- per-unit costs allocate those amounts pro rata by source size.

For every matched chunk:

- `gross_pair_cost_per_unit` is Up plus Down base cost per unit;
- `fee_adjusted_pair_cost_per_unit` includes both decoded fees;
- gross and fee-adjusted edge per unit are `1 - pair_cost`;
- role composition is `MAKER_MAKER`, `TAKER_TAKER`, or `MIXED`.

Classify costs using exact decimal comparison as `<1`, `=1`, or `>1`.  Report unit-weighted shares,
not raw chunk shares.  Residual unmatched size and cost remain explicit per condition.

## Markout

For every bound BUY fill, reconstruct its token book from absolute snapshots and deltas.  A full
snapshot clears the prior state.  At horizons 10, 30 and 60 seconds, select the final valid state
with source timestamp at or before `fill source second + horizon`.

A markout is eligible only when:

- the target is inside the bundle capture interval;
- a valid initialized state exists at or after the fill source second;
- both best bid and best ask are positive;
- no declared coverage gap intersects the fill-to-target interval.

`mid = (best_bid + best_ask) / 2` and BUY markout per unit is
`mid - fee_adjusted_fill_cost_per_unit`.  Report size-weighted mean markout and eligible notional
separately for maker and taker roles at each frozen horizon.  Markout is not realized PnL.

## Stopping and outputs

Until 30 independent conditions contain at least one matched pair, status is `COLLECTING`; no
economic mechanism is labelled supported.  Interim outputs may report counts and values but cannot
change horizons, FIFO allocation, role classes, cost boundary or population.

Each run writes a new immutable directory containing pair chunks JSONL, fill markouts JSONL,
condition summaries JSONL, aggregate summary JSON and a manifest binding contract/code commits and
all input/output SHA256 values.  Existing output is never overwritten.

