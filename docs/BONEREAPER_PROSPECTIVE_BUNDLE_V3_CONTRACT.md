# Bonereaper prospective bundle v3 — frozen capture contract

Status: **FROZEN BEFORE THE FIRST V3 BUNDLE**

## Purpose

Capture the three public evidence streams required by the external-signal and maker-ladder studies
over one bounded interval:

- Chainlink BTC/USD and ETH/USD 60-second TWAP;
- Bonereaper public wallet activity observed live;
- Polymarket public CLOB snapshots and absolute price changes for bound BTC/ETH 5m/15m tokens.

The bundle records research evidence only.  It cannot construct, sign, cancel, or submit orders.

## Pre-start binding

Before starting any child recorder:

1. resolve exact BTC/ETH 5m/15m conditions through the public Gamma API;
2. require every selected market to cover the requested capture plus the frozen discovery safety
   margin;
3. bind condition IDs, token IDs, outcomes, window lengths, slugs and end dates;
4. bind a full lowercase code commit.

Discovery time is not capture time.  The bundle interval starts only after successful metadata
validation.  A v3 bundle is limited to 120 seconds so one fixed 5-minute token set can cover the
entire run without rotation.

## Concurrent children

After binding, start all children concurrently:

- `ChainlinkTwapRecorder` under `chainlink/`;
- `LiveWalletObserver` under `wallet/`;
- `PublicBookRecorder` under `public_book/` with the exact bound metadata and code commit.

Each child retains its own frozen semantics, raw evidence, gaps and manifest.  A child exception
fails the bundle.  Partial child files remain for diagnosis, but the root clean manifest must not be
written.

## Root manifest

A clean root manifest binds:

- bundle contract commit and code commit;
- discovery start/end UTC and SHA256 of bound token metadata;
- requested duration and root start/end UTC;
- relative path and SHA256 of all three child manifests;
- Chainlink event counts/reconnects;
- wallet prospective row count/gap failures;
- CLOB raw/level/snapshot counts, reconnects and final token initialization state.

The output directory is immutable and must not pre-exist.  The bundle cannot silently omit a child
or relabel partial data as clean.

## Downstream use

- The public-book confirmatory pilot is excluded; only bundles after its frozen contract may count.
- Receipt decoding and exact-level classification happen after capture against SHA-bound children.
- Binance 1-second klines are collected by the existing bounded post-capture analyzer and must obey
  strict-pre rules.  They are not claimed to have been observed live in v3.
- Same-source-second ordering is never resolved in Bonereaper's favour.
- No interim result changes the 30-condition confirmatory stopping rule.

