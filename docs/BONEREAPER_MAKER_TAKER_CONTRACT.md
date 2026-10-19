# Bonereaper maker/taker receipt study — frozen contract

Status: **FROZEN BEFORE FULL RECEIPT COLLECTION**

Purpose: distinguish two mechanisms that the correction overlay could not separate:

1. Bonereaper actively crosses the book after a correction (`TAKER`); or
2. Bonereaper leaves passive orders that other traders cross (`MAKER`).

This study classifies the on-chain role of the same 77 prospective Bonereaper BUY fills used by
the frozen correction overlay. It is a mechanism study, not a copyability simulation and not an
authorization for live trading.

One receipt was inspected before this contract only to verify the current CTF Exchange V2 event
schema and decoding logic. That disclosed pilot transaction was
`0x2efcf505ae71b616577242e31185bdeeb139142da91e4198e04aac83800c428b`;
its Bonereaper order decoded as `MAKER`. No other receipt, population share, market split, or
verdict was available when these rules were frozen.

## Frozen wallet evidence

- chain: Polygon PoS, chain id `137`
- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- input: Stage 3A `live_activity.jsonl`
- SHA256: `e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb`
- prospective BUY rows: `77`
- unique transaction hashes: `77`
- source-time interval: `2026-08-26T12:57:10Z` through `2026-08-26T12:58:49Z`
- conditions: exactly the four condition ids present in the frozen input

The source rows remain `LIVE_OBSERVED`. Receipts are immutable historical chain evidence used
only to classify the execution role of those already-preserved rows.

## Frozen contracts and event schema

Accept logs only from the Polygon CTF Exchange V2 deployments documented by Polymarket:

- CTF Exchange V2: `0xe111180000d2663c0091e4f400237545b87b996b`
- Neg Risk CTF Exchange V2: `0xe2222d279d744050d28e00520010520000310f59`

Decode only these exact V2 event topics:

- `OrderFilled(bytes32,address,address,uint8,uint256,uint256,uint256,uint256,bytes32,bytes32)`
  topic:
  `0xd543adfd945773f1a62f74f0ee55a5e3b9b1a28262980ba90b1a89f2ea84d8ee`
- `OrdersMatched(bytes32,address,uint8,uint256,uint256,uint256)` topic:
  `0x174b3811690657c217184f89418266767c87e4805d09680c39fc9c031c0cab7c`

The V2 `OrderFilled` event has indexed `orderHash`, `maker`, and `taker`; its seven data words are
`side`, `tokenId`, `makerAmountFilled`, `takerAmountFilled`, `fee`, `builder`, and `metadata`.
`Side.BUY` is `0`.

The V2 exchange emits both `OrderFilled` and `OrdersMatched` for the taker order, but only
`OrderFilled` for each maker order. Therefore the address stored in the event's indexed `maker`
field is not itself the maker/taker-role test.

## Receipt collection and binding

For every exact transaction hash in the wallet evidence:

1. Fetch `eth_getTransactionReceipt` from a recorded Polygon RPC endpoint.
2. Require a non-null receipt whose `transactionHash` equals the requested hash and whose status
   is successful (`0x1`).
3. Preserve the complete raw JSON-RPC response envelope before decoding it.
4. Record endpoint, UTC collection time, request count, response count, chain id, and SHA256 for
   the wallet input, raw receipt artifact, decoded rows, and summary.
5. Refuse a missing response, duplicate response id, JSON-RPC error, failed transaction,
   malformed log, or log from an unapproved exchange address.
6. The raw receipt artifact is immutable and SHA-bound. A later re-fetch is a new artifact rather
   than a silent replacement.

## Fill-to-event match

For each wallet source row, find exactly one `OrderFilled` event in that row's receipt satisfying
all of:

- indexed `maker` equals the frozen Bonereaper wallet;
- `side == BUY`;
- `tokenId` equals the source row's exact `asset` id;
- `makerAmountFilled / 1e6` equals source `usdc_size` within one micro-unit; and
- `takerAmountFilled / 1e6` equals source `size` within one micro-unit.

Also report the decoded execution price `makerAmountFilled / takerAmountFilled` and require it to
match the source price within `1e-6`. Multiple or zero matching events make the row `AMBIGUOUS`;
the primary verdict then becomes `INCONCLUSIVE` rather than silently dropping it.

For a uniquely matched event:

- `TAKER` if an `OrdersMatched` event from the same exchange address and receipt has the same
  indexed order hash;
- `MAKER` otherwise.

This order-hash rule follows the V2 emission path and is frozen before population collection.

## Frozen populations and weights

Report role shares separately by:

- source row count;
- acquired outcome size; and
- source notional (`usdc_size`).

The primary population is all 77 frozen BUY rows, and the primary weight is source notional.
Also report market and outcome splits.

For continuity with the correction overlay, classify an `opposite fill` using exactly its frozen
same-second inventory rule: all fills in a source second observe inventory from strictly earlier
seconds; a fill is opposite when it buys the outcome different from the non-null dominant prior
cumulative BUY size. The opposite-fill maker/taker split is a pre-specified secondary diagnostic,
not a replacement primary population.

## Primary mechanism gate

Provided all 77 rows are uniquely matched:

- `PASSIVE_MAKER_DOMINANT` if maker source-notional share is at least `80%`;
- `ACTIVE_TAKER_DOMINANT` if maker source-notional share is at most `20%`;
- `MIXED_EXECUTION` otherwise.

If any source row is not uniquely bound, or if receipt completeness/integrity fails, the verdict
is `INCONCLUSIVE`.

The `80/20` thresholds are intentionally strong and may not be changed after collection. Row- or
size-weighted results and the opposite-fill subset cannot override the notional-weighted primary
gate.

## Interpretation limits

`PASSIVE_MAKER_DOMINANT` would refute a simple strategy description in which Bonereaper usually
waits for a detected correction and then crosses the spread. It would support passive limit-order
execution at the time of fill, including a resting-ladder mechanism.

Maker status alone does not reveal when an order was posted, its unfilled siblings, cancellations,
queue position, or whether the order was submitted shortly before execution. Receipt evidence
also does not establish that a follower could obtain the same price after observation latency.
