# Bonereaper pre-open model capture v1 — frozen contract

Status: **FROZEN BEFORE THE FIRST CONFIRMATORY V4 CAPTURE**

## Purpose

Record the prospective wallet and Chainlink history required by
`BONEREAPER_PREOPEN_MODEL_COMPETITION_V4_CONTRACT.md`. This capture observes
public data only. It does not place, sign, cancel, or simulate orders.

## Components

Run concurrently from one recorded root start time:

1. Chainlink RTDS `crypto_prices_twap_sixty` recorder for BTC/USD and ETH/USD.
2. Bonereaper public Data API live observer for
   `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`.

Public CLOB recording is not required for the v4 directional-trigger question.
Polygon receipts and Binance history are collected after finalize and bound by
SHA in the analysis stage.

## Duration and eligibility

- One bundle duration must be between 900 and 14,400 seconds.
- A condition is eligible only if nominal market start is at least 660 seconds
  after the recorded bundle start and no later than the bundle end.
- The taker decision must remain inside the frozen final-60-second pre-open
  window.
- A bundle may contain zero eligible decisions; that is a valid negative
  observation and cannot be extended after inspecting directions.

The 900-second minimum ensures at least one possible five-minute opening after
the 11-minute warm-up. The 14,400-second ceiling bounds artifact size and
failure recovery. Multiple immutable bundles may be accumulated until the v4
stopping rule is reached.

## Clean-finalize gate

The root manifest may state `clean_finalize: true` only when both concurrent
components return normally and their child manifests exist. Confirmatory
analysis additionally requires:

- Chainlink reconnect count zero;
- empty Chainlink gap artifact over the required lookback;
- wallet observer gap failures zero;
- exact child-manifest SHA256 bindings;
- full lowercase 40-character code commit;
- immutable output directory created with no overwrite.

Component failure leaves its partial child artifacts for diagnosis but must not
produce a clean root manifest.

## Time semantics

The root records discovery-independent `started_at` immediately before tasks
are launched and `ended_at` after both return. Eligibility uses this root
interval, while every signal continues to use strict source timestamps.
Observation time is never substituted for source event time.

## Boundary

This contract authorizes research data capture only. No live execution,
credential extraction, parameter tuning, or LLM trading decision is allowed.
