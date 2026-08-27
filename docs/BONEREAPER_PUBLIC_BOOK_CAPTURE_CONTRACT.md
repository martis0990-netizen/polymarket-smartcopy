# Bonereaper public-book ladder capture — frozen contract

Status: **FROZEN BEFORE THE FIRST BOOK-CAPTURE OBSERVATION**

## Purpose

Record the public Polymarket CLOB state needed by the maker-ladder diagnostic already frozen in
`BONEREAPER_PROSPECTIVE_EXTERNAL_SIGNAL_V2_CONTRACT.md`.  This stage measures whether the exact
maker-fill price was publicly visible continuously before the fill.  It cannot identify ownership
of a public order.

## Source and scope

- endpoint: `wss://ws-subscriptions-clob.polymarket.com/ws/market`
- public `market` subscription; no authentication and no user channel
- exact Up and Down token IDs for prospective BTC/ETH 5m/15m conditions
- standard `book` and `price_change` events
- application heartbeat: text `PING` every 10 seconds
- research only; no order construction, signing, cancellation, or live execution

Token IDs and condition metadata must be bound before the first included wallet fill.  Unknown or
unbound tokens remain raw coverage evidence but cannot enter a ladder diagnostic.

## Normalization

Preserve every accepted raw frame with local UTC receive time.  Canonical price and size are exact
`Decimal` strings.

For `book`, emit one normalized absolute level for every bid and ask in the full snapshot:

- `BUY` for a bid and `SELL` for an ask;
- token ID from `asset_id`/`tokenId`;
- source timestamp from the event `timestamp`;
- snapshot hash and condition/market ID when present.

For `price_change`, emit one normalized absolute level per change:

- token ID, side, price, size and hash from the change;
- source timestamp from the enclosing event;
- size `0` removes the exact level.

A `price_change` before a full `book` snapshot for that token is retained raw but is not eligible to
initialize continuity.  Missing/invalid source timestamps, non-positive prices, negative sizes, or
unknown sides fail closed.

## Ordering and gaps

Local receive time is retained separately and never replaces source time.  Source timestamps may
be equal; arrival order is retained by monotonically increasing local line number.  A source-time
regression for one token fails the bounded run.

Any disconnect creates an explicit coverage gap.  After reconnect the token is ineligible until a
new full `book` snapshot is received.  No delta replay or forward fill bridges a gap.  A maker
episode is `INELIGIBLE` whenever its required interval intersects a declared gap or precedes the
latest valid snapshot.

## Frozen ladder diagnostic

For an unambiguous maker BUY at source time `t`, inspect the bid level at the exact execution price:

- `PRE_POSITIONED_LEVEL`: positive public size existed continuously from at least `t-1.0s` through
  the final strict-pre update;
- `LATE_OR_UNSEEN_LEVEL`: the level first appeared later than `t-1.0s`, was absent, or had size zero
  at the final strict-pre update;
- `INELIGIBLE`: no valid snapshot, a coverage gap, ambiguous ordering, or missing strict-pre state.

Same-millisecond and same-source-second events are never ordered in Bonereaper's favour.  Report
episode and notional shares, stratified by opposite-leg status.  There is no causal ownership gate.

## Immutable artifacts

Each bounded run uses a new output directory and refuses overwrite:

- raw WebSocket frames JSONL;
- normalized absolute levels JSONL;
- coverage gaps JSONL;
- token metadata JSON;
- manifest with start/end UTC, clean finalize, event counts, reconnect count, byte counts, SHA256,
  contract commit and code commit.

Interrupted runs retain partial raw data but cannot write a clean manifest.

