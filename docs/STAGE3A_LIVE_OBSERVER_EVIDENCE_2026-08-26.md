# Stage 3A Live Wallet Observer — Preserved Reference Evidence

Date: **2026-08-26**

This document records the immutable reference artifact used by the first real Stage 3B
wallet → executable-market-state join. It supersedes provisional smoke counts discussed
during development. The preserved GitHub Actions artifact is the source of truth.

## Identity

- Wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- Workflow: `Live wallet observer v1 smoke`
- Workflow run id: `32971365532`
- Job id: `98185639359`
- Workflow head SHA: `5ee4152bd04f8bac4ceb901beb02a0bcbf1a0755`
- Artifact id: `9607788691`
- Artifact name: `live-wallet-observer-v1-smoke`
- Artifact ZIP SHA256: `1850a671b6f85d37313e8fbd155c45c601437a1e92172abaa7fbc8174c45b738`
- Artifact expiry: `2026-09-25T12:59:14Z`

## Observer manifest evidence

- schema: `smartcopy-live-wallet-observer-v1`
- mode: `live_observed`
- started: `2026-08-26T12:57:14.529026Z`
- ended: `2026-08-26T12:59:14.579770Z`
- poll interval: `1.0s`
- poll cycles: `114`
- API pages: `114`
- baseline rows: `500`
- prospective rows emitted: **77**
- gap failures: **0**
- max offset reached: `0`
- first source event: `2026-08-26T12:57:10Z`
- first observed event: `2026-08-26T12:57:30.818711Z`
- last source event: `2026-08-26T12:58:49Z`
- last observed event: `2026-08-26T12:58:50.648699Z`

Observation delay, `source_event_time → first_observed_time`:

- p50: **21.63473s**
- p90: **28.03473s**
- p99: **29.41496836s**

These values include public Data API publication/indexing delay plus request/network
latency. They are not a pure network-latency measurement and do not prove absolute
on-chain completeness.

## Inner artifact hashes

`live_activity.jsonl`

- bytes: `115406`
- SHA256: `e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb`

`poll_cycles.jsonl`

- bytes: `30897`
- SHA256: `b9bb52540ec99cf4e120f6dd34fc16e68ccf8c00f0dc16d1ffc2b5a9c0f289d6`

The uploaded artifact contains three files: `live_activity.jsonl`, `poll_cycles.jsonl`,
and `observer_manifest.json`.

## Interpretation boundary

This artifact proves that the public observer prospectively saw 77 wallet activity rows
under the frozen v1 mechanics with zero detected pagination gaps. It does **not** prove
that every underlying wallet action was available immediately, that the public API is a
complete on-chain index, or that any observed action retained executable copy edge.
Stage 3B measures the latter question against independently captured Polymarket state.
