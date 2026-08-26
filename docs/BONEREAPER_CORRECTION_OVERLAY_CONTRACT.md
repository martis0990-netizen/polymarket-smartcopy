# Bonereaper correction / opposite-leg overlay — frozen contract

Status: **FROZEN BEFORE FULL MARKET-TAPE COLLECTION**

Purpose: test the user-specified hypothesis that Bonereaper buys the outcome opposite its
existing dominant inventory during a correction, and render the wallet fills on an independent
Polymarket trade-price tape. This is a descriptive source-time study. It does not establish
maker/taker status, order-placement time, causality, or copyability.

A small `/trades` response was inspected only to verify endpoint schema and connectivity before
this contract. No complete tape, joined correction metric, or hypothesis result was available
when the rules below were frozen.

## Frozen wallet evidence

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- input: Stage 3A `live_activity.jsonl`
- SHA256: `e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb`
- prospective rows: `77`
- source-time interval: `2026-08-26T12:57:10Z` through `2026-08-26T12:58:49Z`
- conditions: exactly the four condition ids present in the frozen input

The wallet evidence remains `LIVE_OBSERVED` for follower-latency provenance. This study uses
`source_event_time` only for source-path alignment; it must not reinterpret the historical market
tape as live-observation evidence.

## Independent market tape

For every exact condition id in the wallet evidence, collect the public Polymarket Data API
`/trades` resource with `market=<condition_id>` in deterministic offset pages.

Collection rules:

1. Use a fixed page size and increasing offsets until the first short page.
2. If the last addressable page is full, fail closed instead of treating the tape as complete.
3. Preserve every raw response row and the exact request/capture manifest before analysis.
4. De-duplicate only exact public-trade identities:
   `conditionId, timestamp, transactionHash, proxyWallet, asset, outcome, side, price, size`.
5. Retain only source timestamps inside the canonical market window encoded in the slug:
   `[window_start, window_start + 300s]` for `5m` and
   `[window_start, window_start + 900s]` for `15m`, inclusive.
6. Exclude Bonereaper rows from the reference tape so its own fills cannot manufacture the
   price path used to classify those fills.
7. Refuse rows with a mismatched condition id, unsupported outcome, non-positive size, price
   outside `[0, 1]`, or invalid Unix timestamp.

The raw market-tape artifact is immutable and SHA-bound. Re-fetching later is a new evidence
artifact, not a silent replacement.

## Common price axis

Map every trade to an Up-probability-equivalent price:

- `Up -> q = price`
- `Down -> q = 1 - price`

For each Unix second, the independent reference `q_second` is the size-weighted mean of all
non-Bonereaper tape rows in that second. Bonereaper fills are plotted at their own mapped price;
they are never inserted into `q_second`.

The usable pre-fill reference for a Bonereaper source second `t` is the last `q_second` at a
strictly earlier second. Same-second public trades cannot establish whether they preceded or
followed the wallet fill and are therefore excluded from correction metrics.

## Inventory state

Bonereaper rows are grouped by `source_event_time` second. All rows in one second observe the
same inventory state carried from strictly earlier seconds; arbitrary ordering within a second is
forbidden.

Before each source second:

- `up_inventory = cumulative Up BUY size`
- `down_inventory = cumulative Down BUY size`
- dominant outcome is `Up`, `Down`, or `None` when equal
- an `opposite fill` buys the outcome different from the non-null pre-second dominant outcome

After classification, all fills in the second are added to cumulative inventory.

## Frozen correction measurements

The bought-outcome probability is `r=q` for an Up fill and `r=1-q` for a Down fill.

For each eligible fill and each trailing horizon `5s`, `15s`, and `30s`:

- `pre_fill_r`: bought-outcome probability from the strict-pre reference
- `trailing_max_r`: maximum bought-outcome reference inside `[t-horizon, t)`
- `correction_depth = trailing_max_r - pre_fill_r`
- `horizon_change = pre_fill_r - first bought-outcome reference in [t-horizon, t)`

Negative `horizon_change` means the outcome being bought became cheaper over the horizon.
Positive `correction_depth` means it is below its trailing high. The natural one-cent threshold
is reported as `correction_depth >= 0.01`; no alternative threshold is selected after results.

Report row-weighted, size-weighted, and notional-weighted metrics separately. The primary test
uses source notional because many public rows can be dust or partial fills.

## Primary hypothesis gate

Population: opposite fills with a valid strict-pre reference and a non-empty 15-second tape
window.

`SUPPORTED_DESCRIPTIVELY` requires both:

1. at least `60%` of eligible opposite-fill source notional has
   `15s correction_depth >= 0.01`; and
2. the notional-weighted median `15s horizon_change` is negative.

`NOT_SUPPORTED` applies when the one-cent share is at most `40%` or the weighted median change is
non-negative. Values between those bounds are `INCONCLUSIVE`.

The 5-second and 30-second horizons are robustness descriptions only. They cannot replace the
15-second primary horizon after seeing results.

## Overlay output

Render one panel per condition:

- independent `q_second` line on the Up-probability axis;
- Bonereaper Up BUY markers at `price`;
- Bonereaper Down BUY markers at `1 - price`;
- marker area scaled by source size with a visible cap;
- canonical market start/end and source timestamps;
- cumulative `Up size - Down size` path in a separate aligned band.

The chart must distinguish missing reference tape from a flat price and must not interpolate
through gaps longer than five seconds.

## Interpretation limits

Even a `SUPPORTED_DESCRIPTIVELY` result means only that this frozen 77-row, four-market sample
matches the correction/opposite-leg pattern. It does not distinguish an actively timed correction
entry from resting passive bid ladders. That distinction needs maker/taker or order-lifecycle
evidence. It also does not authorize a COPY/WATCH/SKIP rule, live orders, or a general claim about
Bonereaper outside this sample.
