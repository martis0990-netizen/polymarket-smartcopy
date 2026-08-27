# Bonereaper prospective bundle v4 — frozen dual-window capture contract

Status: **FROZEN BEFORE THE FIRST V4 BUNDLE**

## Purpose

Preserve the clean v3 Chainlink, wallet and public-CLOB semantics while binding both sides of a
market boundary.  One bounded bundle must be able to observe Bonereaper fills in the expiring
market and pre-open decisions for the following market without relabelling either population.
The recorder is research-only and cannot construct, sign, cancel or submit orders.

## Pre-start binding

Before any child recorder starts, resolve exact public Gamma metadata for BTC and ETH 5m/15m:

- bind the current condition when it remains active at discovery time;
- independently bind the safe condition selected to cover the requested capture plus 60 seconds;
- retain both when those conditions differ and deduplicate them when they are identical;
- bind condition IDs, token IDs, outcomes, slugs, window starts, window lengths and end dates;
- bind one full lowercase code commit.

Current conditions are not asserted to remain open for the whole bundle.  Their public-book rows
are eligible only before their own market end and under the existing exact-level rules.  Safe
conditions retain the v3 full-capture coverage requirement.

## Capture interval

- Maximum requested duration remains 120 seconds.
- Discovery is outside capture time.
- Chainlink, live wallet observation and the public CLOB start concurrently after metadata binding.
- A boundary-study bundle is scheduled so capture starts at least 76 seconds before a target open
  and ends at or after that open.  Downstream analyzers enforce this from timestamps; a bundle that
  misses the interval may remain valid for other studies but contributes no pre-open condition.

## Clean finalization

Each child keeps its own raw evidence, gaps and manifest.  Any child exception withholds the root
manifest.  A clean root manifest SHA-binds all three child manifests and token metadata, records
discovery/capture times, event counts, reconnects, wallet gaps and final token initialization.
The output directory is immutable and must not pre-exist.

## Downstream rules

- Receipt rows must match an exact bound condition and token before public-book classification.
- Same-source-second evidence is never ordered in Bonereaper's favour.
- Pre-open analysis still requires complete 76-second pre-open coverage, capture through market
  start, an unambiguous taker in `[open-60s, open)`, and strict-pre Chainlink/Binance inputs.
- Current-market and following-market results are never pooled as if they were one condition.
- Existing 30-condition stopping rules and frozen signal thresholds do not change.
- Binance 1-second evidence remains a SHA-bound post-capture collection; it is not claimed live.

