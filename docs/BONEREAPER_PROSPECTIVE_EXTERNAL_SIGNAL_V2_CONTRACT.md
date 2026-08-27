# Bonereaper prospective external-signal study v2 — frozen contract

Status: **FROZEN BEFORE THE FIRST ELIGIBLE V2 OBSERVATION**

## Purpose

Discriminate three explanations for Bonereaper's BTC/ETH Up/Down behavior without treating repeated
fills in one market as independent evidence:

1. active taker buys follow fair value relative to the exact Chainlink TWAP opening price;
2. active taker buys follow short Binance momentum or BTC-to-ETH lead;
3. opposite-leg maker fills come from a pre-positioned public-book ladder used to rebalance inventory.

The August 26 external-signal run is a descriptive pilot with a missing pre-result Git object. Its
results selected these hypotheses but do not contribute observations to v2 and do not satisfy any
v2 threshold.

## Frozen subject and market family

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- assets: BTC and ETH only
- horizons: 5-minute and 15-minute Up/Down markets only
- market rule: 60-second Chainlink TWAP for both opening price-to-beat and settlement
- activity: BUY fills; maker/taker role is decoded from CTF Exchange V2 receipts
- authorization: research and paper analysis only; no order signing or live trading

## Independent unit and stopping rule

The primary independent unit is one `condition_id`, not a raw fill or source second.

Collect until the first of:

- `40` eligible conditions, including at least `20` with one or more unambiguous taker BUY episodes;
- `7` complete UTC days after the first clean observation.

If seven days end before both count requirements are met, report `UNDERPOWERED`; do not extend the
window after inspecting directional results. Report BTC/ETH and 5m/15m strata, but they cannot
replace the combined primary population.

## Required prospective streams

Every source record preserves its source timestamp and local receive timestamp.

1. Polymarket RTDS `crypto_prices_twap_sixty` for `btc/usd` and `eth/usd`.
2. Binance spot BTCUSDT and ETHUSDT trades or one-second aggregates sufficient to calculate strict
   pre-5s and pre-15s momentum and signed taker flow.
3. Polymarket public CLOB book updates for the exact outcome tokens of eligible markets.
4. Bonereaper public wallet activity through the existing live observer.
5. Polygon receipts for every observed BUY transaction, decoded through the existing maker/taker
   module.

RTDS has no snapshot, history, or replay. A disconnect creates an explicit coverage gap from the
last accepted source timestamp until the first post-reconnect update. Any feature whose lookback or
opening window intersects a gap is ineligible. No forward-fill bridges a gap.

The exact Chainlink decimal representation is retained from `full_accuracy_value` when available.
Do not use the display float as the canonical value.

## Market eligibility

A condition is eligible only when all of the following hold:

- market metadata and both outcome token IDs are bound before the first included fill;
- the complete 60-second Chainlink opening window is observed without a declared gap;
- required strict-pre Chainlink and Binance lookbacks are complete;
- wallet evidence is `LIVE_OBSERVED` and maker/taker role is unambiguous for the relevant episode;
- public CLOB capture covers the tested maker lookback when a maker-ladder diagnostic is reported.

An ineligible market remains in the coverage report with explicit reasons. It is never silently
removed from denominators after its candidate direction or outcome is known.

## No future leakage

For a wallet source time `t`, features use only external records with source timestamps `< t`.
Same-millisecond and same-second ordering is treated as unknown and excluded where necessary.
`first_observed_time` measures copy latency but never replaces the wallet's source time when
reconstructing the source decision.

The Chainlink opening price `K` is the last official 60-second opening TWAP update whose observation
timestamp is at or immediately before market start. If the stream cannot bind that update without
ambiguity, the market is ineligible; v2 does not reconstruct Chainlink's unpublished internals.

## Episode and market aggregation

Collapse partial fills sharing `(condition_id, outcome, source_second, role)` into one episode.

Primary active-decision label for a condition:

- take the earliest unambiguous taker BUY episode by source time;
- ties across opposing outcomes in the same second make the condition ineligible for the primary
  directional gate;
- later taker episodes are secondary path diagnostics only.

Secondary market label: taker-notional majority direction. Exact ties are `None`.

## Frozen candidate directions

All directions are `Up`, `Down`, or `None` at exact zero.

### A. Chainlink barrier direction — primary fair-value candidate

At the strict-pre update before the primary taker episode:

`barrier_bps = 10,000 * ln(chainlink_twap_60s / opening_twap_60s)`

The sign defines direction. Also record remaining seconds and realized Binance volatility, but do
not fit or threshold a probability model in v2.

### B. Binance 15-second momentum — primary external competitor

Direction is the sign of the strict-pre BTCUSDT or ETHUSDT 15-second log return. Five-second
momentum is descriptive robustness only.

### C. BTC lead for ETH

For ETH conditions only, direction is the strict-pre BTCUSDT 15-second momentum sign.

### D. Signed taker flow

Over the strict-pre 15 seconds:

`flow = taker_buy_quote - (total_quote - taker_buy_quote)`

Its sign is descriptive. It is not allowed to replace A or B as the primary candidate.

RSI and EMA are omitted from v2 primary testing because the pilot showed they collapsed to the same
trend signs as momentum. They may be computed later only under a separately frozen contract.

## Primary directional gates

For the primary first-taker label, report unweighted condition counts. Notional weighting is
secondary and cannot rescue a failed condition-count gate.

For each of A and B:

- `SUPPORTED_DESCRIPTIVELY`: alignment is at least `65%` and the Wilson 95% lower bound is above
  `50%`;
- `NOT_SUPPORTED`: alignment is at most `55%`;
- otherwise `INCONCLUSIVE`.

Candidate comparison on conditions where A and B disagree:

- momentum dominates barrier only if B aligns on at least `65%` of discordant conditions and beats
  A by at least `20` percentage points;
- barrier dominates momentum under the symmetric rule;
- fewer than `10` discordant eligible conditions is `UNDERPOWERED_COMPARISON`.

No threshold or horizon sweep is permitted.

## Maker-ladder diagnostic

This diagnostic cannot attribute a public order to Bonereaper. It tests whether the public book is
consistent with a pre-positioned ladder before an on-chain maker fill.

For each unambiguous maker episode, inspect the exact outcome token and fill price:

- `PRE_POSITIONED_LEVEL`: visible size at that exact price existed continuously from at least
  `1.0` second before source time until the final pre-source book update;
- `LATE_OR_UNSEEN_LEVEL`: the level first appeared less than 1.0 second before source time or was
  absent from the final pre-source book;
- `INELIGIBLE`: coverage gap, ambiguous ordering, or no pre-source update.

Report episode share and notional share, stratified by opposite-leg status. This is descriptive;
there is no causal attribution gate.

## Pair economics diagnostic

Reconstruct cumulative UP and DOWN inventory per condition with actual buy prices and decoded fees.
For every newly matchable pair, record:

`pair_cost = allocated_up_cost + allocated_down_cost`

Report the share of paired units with `pair_cost < 1`, `= 1`, and `> 1`, gross and after fees.
Do not assume a merge occurred unless a merge transaction is independently observed.

## Immutable artifacts

Every bounded run writes a new directory and refuses overwrite:

- raw Chainlink TWAP JSONL
- raw Binance input JSONL
- wallet live activity JSONL
- public-book capture reference and SHA256
- decoded receipt rows
- normalized condition records
- coverage gaps and ineligibility reasons
- summary JSON
- manifest with byte counts, SHA256 values, contract commit, code commit, start/end UTC, and clean
  versus interrupted finalize status

Interrupted runs retain raw partial data but cannot write a clean final manifest.

## Acceptance boundary

Before collection starts:

- this contract is committed;
- deterministic tests cover strict-pre selection, gap exclusion, independent condition aggregation,
  Wilson gates, discordant comparison, maker-level continuity, and overwrite refusal;
- one bounded smoke proves both Chainlink symbols are received and timestamped.

After collection, one mandatory verification pass is allowed, with at most two fix-and-verify
cycles. A fix may correct implementation or documented external semantics; it may not change the
stopping rule, candidates, horizons, populations, or gates after directional results are visible.
