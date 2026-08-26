# Live Wallet Observer v1 — first prospective Bonereaper smoke

Status: `LIVE_WALLET_OBSERVER_V1_SMOKE_PASS`

Contract: `docs/LIVE_WALLET_OBSERVER_V1_CONTRACT.md`

Run date: 2026-08-26 UTC

## Subject and configuration

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- public source: Polymarket Data API `/activity`
- type: `TRADE`
- observation mode: `LIVE_OBSERVED`
- nominal poll interval: `1.0s`
- page size: `500`
- bounded duration: `120s`
- workflow run: `32971091105`
- implementation head used by smoke: `856c72876f744b9a180b457a1d61964b1a3bd7e8`

## Runtime gates

- clean observer run: PASS
- independent manifest verifier: PASS
- baseline established: `500` rows
- poll cycles: `114`
- API pages: `114`
- prospective emitted rows: `104`
- observation gap failures: `0`
- maximum offset reached: `0`
- all emitted rows: `LIVE_OBSERVED`
- all source-to-observed delays: non-negative
- clean manifest: written

The run therefore proves v1 mechanics for this bounded sample. No page beyond offset 0 was required in this interval, so the real smoke did not exercise the multi-page catch-up path; that path is covered by deterministic adversarial tests.

## Observed public-feed latency

For the 104 prospective rows:

- p50: `20.053174s`
- p90: `27.2438901s`
- p99: `32.053174s`

First emitted source event: `2026-08-26T12:54:13Z`.

First observation among emitted rows: `2026-08-26T12:54:42.276144Z`.

Last emitted source event: `2026-08-26T12:55:52Z`.

Last observation among emitted rows: `2026-08-26T12:56:02.053174Z`.

These numbers are **public-observer latency**, not exchange matching latency and not network-only latency. They combine at least:

- Polymarket public Data API publication/indexing delay;
- integer-second source timestamp granularity;
- request/poll timing;
- network and response time.

The 1-second polling interval therefore does not imply 1-second observability.

## Evidence fingerprints

`live_activity.jsonl`

- bytes: `155156`
- SHA256: `e2e6386fe086b1766c468144c876eef9502ed374dac98972f65c7cdccf0cd99a`

`poll_cycles.jsonl`

- bytes: `30897`
- SHA256: `30f8b6caf074775b0fd5382c6a646d07a1ed87afd2c207bdc17a395bb392bb53`

Uploaded Actions artifact:

- artifact ID: `9607683432`
- artifact ZIP SHA256: `7dafdd33a3a458eb4914d8226d2dd2df3bc4541b8a29794e8546d57ae1d24f3d`

## Interpretation

The smoke materially changes the default SmartCopy latency assumption. For this sample, public wallet activity appeared tens of seconds after its source timestamp even while the API was polled every second.

This does **not** prove that 20–32 seconds is a stable distribution across hours, regimes, wallets, or endpoints. A longer prospective run is required before Stage 3 delay-decay research freezes empirical latency buckets.

It also does not establish that a source action remains economically copyable after this delay. That requires joining first-observed wallet evidence to executable Polymarket book state at or after the observation time.

## Next allowed step

After merge of the observer implementation, run a longer prospective evidence collection alongside the existing Polymarket capture. Then perform a separately frozen executable market-state join. No live order placement is authorized.
