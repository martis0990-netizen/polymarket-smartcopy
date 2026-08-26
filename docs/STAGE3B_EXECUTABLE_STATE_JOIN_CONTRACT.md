# Stage 3B — Prospective Wallet → Executable Polymarket State Contract

Status: **FROZEN BEFORE REAL DATA JOIN**

This gate measures what Polymarket quote state is first provably available after a
prospective wallet action becomes public through Stage 3A. It is measurement only;
it does not authorize copy decisions, fair-value estimates, or order placement.

## Inputs

1. Stage 3A `live_activity.jsonl`.
   - `observation_mode` MUST be `live_observed`.
   - `activity_type` MUST be `TRADE`.
   - `asset` is the exact Polymarket CLOB token id and MUST be present.
   - `side` MUST be `BUY` or `SELL`.
   - `source_event_time` and `first_observed_time` MUST be timezone-aware.
   - `first_observed_time >= source_event_time`.
2. TradingLab normalized `events.jsonl` from a latency-aware Polymarket capture.
   - join only `venue=polymarket` and exact matching `instrument=asset`.
   - eligible event types are `market_snapshot` and `book_delta`.
   - eligible matching events MUST carry a real `receive_ts`; source `ts` is never a
     substitute.

Inputs are immutable evidence. The joiner MUST refuse to overwrite its outputs.

## Frozen join rule

For each wallet row, in capture append order:

1. Ignore all market events with `receive_ts < first_observed_time`.
2. Do not fuzzy-match market titles, slugs, outcomes, or condition ids. Token id is
   the only join key.
3. Wallet `BUY` requires the ask; wallet `SELL` requires the bid.
4. The first eligible post-observation state is accepted only when both a positive
   executable-side price and positive size are evidenced.
   - A full snapshot may supply `best_ask_price/best_ask_size` or
     `best_bid_price/best_bid_size` in normalized metrics.
   - A `book_delta` may supply size from its own `price`/`size` only when that price
     equals the normalized current BBO price for the required side.
5. Do not use midpoint, interpolation, a pre-observation snapshot, a synthetic size,
   or source event time as receive time.
6. If no such state exists in the supplied capture artifact, label the row
   `NO_EXECUTABLE_STATE`. There is no post-hoc maximum-wait threshold in Stage 3B;
   actual wait time is measured and preserved.
7. For a matching token, a receive-time regression in capture append order is a
   fail-closed data-integrity error.

This is intentionally conservative. It may understate practical state availability,
but it must not overstate executable liquidity.

## Frozen measurements

For every `JOINED` row preserve:

- wallet source price;
- wallet source event time;
- wallet first observed time;
- market source event time;
- market receive time;
- market event type and input line number;
- executable price and evidenced size;
- `observation_to_state_seconds`;
- `source_to_state_seconds`;
- signed deterioration where positive means worse for the copier:
  - BUY: `executable_price - source_price`;
  - SELL: `source_price - executable_price`;
- deterioration in bps relative to wallet source price.

The manifest reports counts plus p50/p90/p99 for observation→state delay and signed
price deterioration. No threshold is selected from those results.

## Hard exclusions

Stage 3B does **not**:

- infer Bonereaper intent;
- reconstruct a stale/pre-observation order book;
- estimate fair value or residual expected value;
- add Hyperliquid/spot features;
- output COPY/WATCH/SKIP;
- simulate fills beyond the evidenced top-of-book size;
- place or authorize live orders.

A later gate may use this evidence only after Stage 3B is independently verified.
