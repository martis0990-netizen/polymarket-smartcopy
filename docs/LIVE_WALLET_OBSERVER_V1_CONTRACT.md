# SmartCopy Live Wallet Observer v1 — frozen contract

Status: FROZEN BEFORE FIRST PROSPECTIVE LIVE RUN

## Purpose

Measure when SmartCopy can first observe public Bonereaper TRADE activity in real time, without placing orders or inferring copyability.

This is the first prospective evidence stage. It exists to establish truthful `source_event_time -> first_observed_time` latency and bounded catch-up completeness within the public API snapshot before any residual-edge backtest uses live wallet observations.

## Frozen subject

Initial observer wallet:

`0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`

Activity type: `TRADE` only.

The observer records every returned market family. BTC/ETH filtering happens only in later research joins. The observer itself must not discard non-target activity.

## Polling contract

- public Polymarket Data API `/activity`
- `sortBy=TIMESTAMP`
- `sortDirection=DESC`
- page size: `500`
- nominal poll interval: `1.0 second`
- Activity offset cap: existing empirically verified `5000`
- observation mode: `LIVE_OBSERVED`

Each HTTP page is timestamped by the existing `PolymarketDataAPI.activity_page` only after its response is received. That post-response timestamp is the page's `first_observed_time` for newly discovered rows on that page.

Do not backdate observation time to request start, source event time, or previous poll time.

## Catch-up / gap policy

A polling cycle starts at offset `0` and walks DESC pages only as far as needed to reach evidence already seen in an earlier cycle.

- newly seen rows are appended exactly once by immutable activity identity;
- if the first page is not full, the cycle is complete;
- if a full page contains at least one previously seen row, the cycle is complete after processing that page;
- if a full page contains no previously seen row, fetch the next offset page;
- continue in increments of 500 up to offset 5000;
- if offset capacity is exhausted without reaching previously seen evidence, fail closed with an explicit observation-gap error.

On the first polling cycle there is no previous watermark. It establishes a baseline snapshot and MUST NOT label pre-existing rows as newly live-observed signals. Baseline rows are used only to seed dedup/watermark state.

From the second cycle onward, only previously unseen rows are emitted as prospective `LIVE_OBSERVED` evidence.

### Public API visibility boundary

The observer proves catch-up only across rows visible in the Data API pagination snapshots it actually receives. The public endpoint may index an older source event later. If such a row appears deeper than the prior watermark after the observer has already reached known evidence, v1 cannot prove it was never omitted by the API at an earlier poll.

Therefore v1 evidence means **first observed through this public API observer**, not absolute first on-chain/public-system availability and not permanent historical completeness. A custom indexer or alternate source is not added until prospective measurements show this limitation is material.

## Identity / dedup

Use immutable source fields equivalent to the Stage 1.1 activity identity:

- proxy wallet
- source event time
- condition ID
- activity type
- side
- size
- USDC size
- price
- asset
- transaction hash
- outcome

Same transaction hash on different assets/outcomes must remain distinct.

## Timing fields

Every emitted row must preserve:

- `source_event_time`
- `first_observed_time`
- derived `observation_delay_seconds = first_observed_time - source_event_time`

Negative delay is invalid and fails closed through the existing model invariant.

Request timing may additionally record cycle/page start/end timestamps for diagnostics, but must never replace `first_observed_time`.

## Immutable artifacts

A bounded observer run writes a new output directory and never overwrites existing evidence.

Required artifacts:

- `live_activity.jsonl` — emitted prospective rows only
- `poll_cycles.jsonl` — one record per poll cycle with page/count/timing diagnostics
- `observer_manifest.json` — written only on clean finalize

Manifest must include:

- schema version
- wallet
- observation mode
- requested activity type
- configured poll interval and page size
- start/end UTC
- poll cycle count
- API page count
- baseline row count
- emitted prospective row count
- duplicate/already-seen row count
- max offset reached
- gap failures
- first/last source event time among emitted rows
- first/last observed time among emitted rows
- p50/p90/p99 observation delay if at least one prospective row exists
- artifact byte counts and SHA256

## Failure semantics

Fail visibly on:

- API/pagination failure that prevents proving catch-up to known evidence;
- offset-cap exhaustion without finding known evidence;
- non-`LIVE_OBSERVED` emitted row;
- negative source-to-observed delay;
- overwrite attempt;
- malformed output serialization.

Transient HTTP failure handling is deferred until measured need; v1 does not add a retry framework merely to hide failures.

## Explicit non-goals

This stage does NOT:

- place or simulate orders;
- join Polymarket BBO/depth;
- join Hyperliquid or spot data;
- reconstruct causal intent beyond recording raw prospective fills;
- calculate residual edge;
- classify COPY/WATCH/SKIP;
- infer source strategy;
- treat baseline snapshot rows as live observations.

## Acceptance gate

Implementation gate:

- deterministic unit tests for baseline seeding, dedup, multi-page catch-up, same-tx/different-asset identity, offset-cap fail-closed, post-response observation timing, and immutable finalize.

Runtime gate:

- one bounded real observer smoke;
- baseline established successfully;
- at least multiple poll cycles complete;
- if prospective rows occur, all are `LIVE_OBSERVED` with non-negative delay;
- clean manifest written;
- no observation gap.

A smoke with zero new wallet trades can prove collector mechanics but cannot characterize latency distribution. Longer prospective collection is authorized only after the bounded smoke passes.

## Hard prohibitions

- no historical BACKFILL rows as prospective signals;
- no midpoint/executable-price assumptions;
- no threshold search;
- no live orders;
- no copyability claim from source-observation latency alone.
