# Bonereaper prospective settlement v1 — frozen contract

Status: **FROZEN BEFORE OUTCOME OR POST-CAPTURE ACTIVITY RETRIEVAL**

## Purpose

Determine the terminal value of the exact bounded fills from the first clean bundle v5, and test
whether public post-capture evidence reports a merge or redemption for those conditions.  This is
not total wallet PnL: inventory before the capture, fills after it, rewards, rebates, transfers and
unobserved positions remain outside the allocation.

## Immutable population and inputs

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- bundle manifest SHA256:
  `3748dbd327adbdfeea8506bcb8f747f1831b721afe3ea782933d82da00b69160`
- decoded receipt rows SHA256:
  `1cbbe07f740682e1f6542d1ed70d7d2b8b63a9099a3366382aa3e3b1bff2ab31`
- economics condition rows SHA256:
  `8c848d320e2cc53e931fb408d493166f7ccb784416a56bcc4e8bdfdb745fb32f`
- exact target conditions: the five unique condition IDs in that economics artifact
- public activity interval: Unix `[1787841769, 1787855700]`, inclusive
- activity types: exact string `MERGE,REDEEM`

The end corresponds to `2026-08-27T18:35:00Z`, fixed before retrieval.  Absence inside this interval
means only “not publicly reported by cutoff,” never “never merged/redeemed.”

## Resolution evidence

Fetch exact Gamma market metadata by each frozen slug.  A market is resolved only when metadata is
closed and its ordered `outcomes` map to an ordered terminal price vector containing exactly one
`1` and one `0`.  Any other vector, missing condition ID, slug mismatch or API ambiguity is
`UNRESOLVED_OR_AMBIGUOUS` and receives no terminal allocation.

## Public merge/redeem evidence

Use the complete range collector with ascending source timestamps and the frozen comma-separated
type filter.  Preserve raw rows.  Retain target-condition rows separately and report transaction
hash, type, source time, size and USDC size.  Rows for other conditions remain in the coverage
summary but are not attributed to the five targets.

`MERGE` is an inventory transformation: equal complementary units are burned for collateral.
`REDEEM` is a settlement cash inflow after resolution.  Neither row is profit without acquisition
cost, and public activity cannot prove which bounded fill lot was transformed.

## Bounded terminal allocation

For every resolved target condition, use the frozen economics condition row:

- matched pair terminal value equals matched size;
- winning residual terminal value equals its residual size;
- losing residual terminal value equals zero;
- bounded acquisition cost equals fee-adjusted matched-pair cost plus both residual costs;
- `bounded_terminal_edge = terminal_value - bounded_acquisition_cost`.

This is a counterfactual hold-to-resolution value of only the bounded BUY rows.  It is not labelled
realized PnL and is not reconciled to the wallet balance.

## Aggregation and stopping

Report condition rows and totals, plus outcome-alignment of the largest residual side.  Until 30
resolved independent conditions have bounded economics, status remains `COLLECTING` and no
settlement mechanism is labelled supported.  No outcome-conditioned threshold or population
change is permitted.

## Immutable outputs

A new output directory must not pre-exist.  Write Gamma responses, all frozen-interval activity,
target activity, condition settlement rows, summary and a manifest binding input/output SHA256,
contract commit and code commit.  Retrieval or validation failure withholds a clean manifest.

