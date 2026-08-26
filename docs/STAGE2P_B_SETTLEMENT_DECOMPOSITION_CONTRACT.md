# Stage 2P-B — Settlement Decomposition Contract

Status: FROZEN BEFORE fetching the post-day settlement grace window

## Purpose

For the already frozen 763 Bonereaper BTC/ETH 5m/15m Up/Down markets from 2026-08-25, reconcile observable BUY acquisition cost with public REDEEM cash inflow and decompose eligible market gross settlement cashflow into:

1. matched paired-inventory component; and
2. excess directional-inventory component.

This is historical outcome accounting. It is NOT a live predictor, copyability test, or net PnL claim.

## Frozen inputs

### Stage 1 TRADE evidence

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- date: 2026-08-25 UTC
- normalized activity SHA256: `5fd68d01a6768818303f288c9a61285c3ebc848f90566e2c05380c1bd895b5b4`
- complete TRADE rows: 70,474

### Stage 2H paired-market evidence

- market count: 763
- paired markets SHA256: `90bd0ebaad300545f2f9aab2ef713ac40d33eb26ec3da42bd6dc0fbe8669d0f7`

### Stage 2P-A same-day non-TRADE evidence

- normalized SHA256: `6e34113cd17665caa7d333ab35cb49b9beb989ba5c18f5054d438bcc4ce2c10b`
- raw SHA256: `78eb46b009016586179f391fec46a9e23ff9b7fce9eab088794409ecf187a6fe`
- requested types: `REDEEM,REWARD,MAKER_REBATE,TAKER_REBATE,SPLIT,MERGE`
- target markets with same-day REDEEM evidence: 758 / 763

Stage 2P-A also observed same-day wallet-level activity amounts:

- REWARD usdcSize: 144.463
- MAKER_REBATE usdcSize: 1062.633
- TAKER_REBATE usdcSize: 8631.8889

These three amounts are kept as UNALLOCATED WALLET-LEVEL INCENTIVE ACTIVITY. They MUST NOT be assigned to the 763 target markets without condition-level attribution evidence.

## Frozen settlement grace window

To resolve target conditions lacking same-day redemption evidence, fetch exactly:

- start: `2026-08-26T00:00:00Z` / Unix `1787702400`
- end: `2026-08-27T23:59:59Z` / Unix `1787875199`
- activity types: `REDEEM,SPLIT,MERGE`

The 48-hour grace interval and type set are frozen before viewing its results. Do not extend the window after seeing coverage. A market still lacking redemption evidence after this window is `UNRESOLVED_IN_FROZEN_EVIDENCE` for Stage 2P-B.

## Market eligibility

For each of the 763 Stage 2H conditions, combine:

- Aug-25 BUY acquisition evidence from Stage 2H;
- same-day REDEEM/SPLIT/MERGE evidence from Stage 2P-A; and
- frozen grace-window REDEEM/SPLIT/MERGE evidence.

A market is `SIMPLE_SETTLEMENT_ELIGIBLE` only when:

- it has at least one REDEEM row in the combined settlement evidence;
- it has zero SPLIT rows in the combined settlement evidence;
- it has zero MERGE rows in the combined settlement evidence;
- Stage 2H BUY-leg cost fields needed below are present.

Any transformed or unresolved market is excluded from simple decomposition and reported separately. Exclusion is not failure.

## Frozen per-market formulas

From Stage 2H:

- `buy_outflow = up.total_usdc + down.total_usdc`
- `matched_size = min(up.total_size, down.total_size)`
- `matched_cost = matched_average_cost`
- `excess_up = max(up.total_size - down.total_size, 0)`
- `excess_down = max(down.total_size - up.total_size, 0)`
- `excess_cost = excess_up * up.vwap_price + excess_down * down.vwap_price` for existing excess legs

From settlement evidence:

- `redeem_inflow = sum(REDEEM.usdcSize)` for the condition across same-day + grace evidence

For each SIMPLE_SETTLEMENT_ELIGIBLE market:

- `gross_settlement_cashflow = redeem_inflow - buy_outflow`
- `matched_pair_cashflow = matched_size - matched_cost`
- `excess_directional_payout = redeem_inflow - matched_size`
- `excess_directional_cashflow = excess_directional_payout - excess_cost`
- `reconciliation_error = gross_settlement_cashflow - (matched_pair_cashflow + excess_directional_cashflow)`

The identity should reconcile near zero subject to source rounding. A large mismatch is a DATA_INTEGRITY failure, not a new profit source.

## Interpretation

`matched_pair_cashflow` answers: what gross settlement contribution is explained by buying matched Up+Down inventory at their observed average acquisition costs?

`excess_directional_cashflow` is the residual gross settlement contribution associated with unequal Up/Down token inventory on simple-settlement markets. It is historical outcome accounting, not proof that the wallet predicted direction ex ante.

`gross_settlement_cashflow` is NOT net PnL because this stage does not prove complete fee accounting, financing, transfers, or incentive allocation.

Daily REWARD/MAKER_REBATE/TAKER_REBATE amounts remain outside target-market settlement cashflow and are reported separately as `unallocated_wallet_incentive_activity`.

## Frozen aggregate report

Report:

- target market count (763)
- same-day redeem coverage
- grace-window redeem coverage
- combined redeem coverage
- simple-settlement eligible count/share
- excluded SPLIT/MERGE count
- unresolved-after-grace count
- eligible BUY outflow total
- eligible REDEEM inflow total
- eligible gross settlement cashflow total
- matched pair cashflow total
- excess directional cashflow total
- absolute and max per-market reconciliation error
- count/share of eligible markets where matched pair cashflow > 0
- count/share where excess directional cashflow > 0
- median matched pair cashflow per market
- median excess directional cashflow per market
- unallocated REWARD activity amount
- unallocated MAKER_REBATE activity amount
- unallocated TAKER_REBATE activity amount

No threshold sweep is allowed. Positivity (`>0`) is an accounting sign, not an optimized threshold.

## Verdict

Exactly one:

- `SETTLEMENT_DECOMPOSITION_RECONCILED` — grace retrieval is complete and eligible markets reconcile within numerical tolerance.
- `SETTLEMENT_DECOMPOSITION_PARTIAL` — retrieval is complete but unresolved/transformed markets prevent full target coverage; eligible subset still reconciles.
- `DATA_INSUFFICIENT` — API completeness, frozen input identity, or accounting reconciliation cannot be proven.

A PARTIAL verdict may still be useful. It must not be upgraded by extending the frozen grace window.

## Forbidden claims

Stage 2P-B alone cannot establish:

- net total wallet PnL
- maker/taker causal attribution by market
- reward attribution to target markets
- live copyability
- residual executable edge
- future directional predictability
- market-making strategy classification

Those require separate evidence/contracts.