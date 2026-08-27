# Bonereaper public-book confirmatory study — frozen contract

Status: **FROZEN AFTER THE PILOT AND BEFORE CONFIRMATORY OBSERVATIONS**

## Question

For future Bonereaper maker BUY fills, does the exact public bid look like a long-standing ladder or
a rapidly introduced/refreshed quote?

The pilot in `BONEREAPER_PUBLIC_BOOK_PILOT_RESULTS_2026-08-27.md` informed this design and is
excluded from every confirmatory count.

## Evidence and eligibility

- Use only new bounded captures created after this contract commit.
- Apply `BONEREAPER_PUBLIC_BOOK_CAPTURE_CONTRACT.md` without forward fill across reconnects.
- Token metadata, capture contract and exact code commit must be SHA-bound before an included fill.
- Decode maker/taker role from Polygon receipts using the fee-aware CTF Exchange V2 decoder.
- Include only unambiguous maker BUY fills with a full strict-pre snapshot and no intersecting gap.
- Same-source-second book events are never ordered in Bonereaper's favour.
- Taker fills, ambiguous receipts and startup/gap-ineligible maker fills remain reported but do not
  enter the primary denominator.

## Frozen classification

Use the existing 1-second exact-price rule:

- `PRE_POSITIONED_LEVEL`: positive aggregate public bid existed continuously from at least `t-1s`;
- `LATE_OR_UNSEEN_LEVEL`: it appeared later, was removed, or was absent at final strict-pre state;
- `INELIGIBLE`: insufficient or ambiguous coverage.

Public size cannot establish order ownership.  The diagnostic measures visible exact-price
continuity only.

## Independent unit and stopping rule

The primary independent unit is a condition ID, not a fill.  Stop at 30 new eligible conditions,
with all of the following strata represented by at least five conditions:

- BTC 5m;
- BTC 15m;
- ETH 5m;
- ETH 15m.

A condition is eligible after at least one eligible maker BUY fill.  Do not stop early because an
interim share crosses a threshold.  Freeze and retain every clean capture, including conditions
with no eligible maker fill.

## Condition score and verdict

For each eligible condition, compute the notional share of eligible maker BUY fills classified
`PRE_POSITIONED_LEVEL`:

- at least 80%: `PRE_POSITIONED_DOMINANT`;
- at most 20%: `LATE_DOMINANT`;
- otherwise: `MIXED_CONDITION`.

The primary verdict uses condition counts and a two-sided 95% Wilson interval:

- `LONG_STANDING_LADDER_SUPPORTED` when at least 65% of conditions are
  `PRE_POSITIONED_DOMINANT` and the Wilson lower bound exceeds 50%;
- `RAPID_QUOTING_SUPPORTED` when at least 65% are `LATE_DOMINANT` and the Wilson lower bound
  exceeds 50%;
- otherwise `MIXED_OR_INCONCLUSIVE`.

Also report fill and notional shares, startup/gap exclusions, asset/window strata, opposite-leg
status and maker-fill markout.  These are secondary and cannot replace the condition-level verdict.

## Prohibited reinterpretations

- Do not reduce one second, change exact-price matching to a price band, or infer ownership.
- Do not count this pilot in the confirmatory sample.
- Do not pool repeated fills as independent trials.
- Do not equate maker execution with a pre-existing order.
- Do not build or place live orders from this study.

