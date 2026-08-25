# Intent Reconstruction Specification

## Problem

Public source activity may expose many fills for one underlying trading decision. Mirroring each fill independently inflates signal count and can misread inventory management or hedging as directional conviction.

## Goal

Convert raw source activity into deterministic exposure-change episodes.

## Canonical intent states

- `ENTER`
- `ADD`
- `HOLD`
- `REDUCE`
- `EXIT`
- `FLIP`
- `HEDGE`
- `UNKNOWN`

## Required evidence

Where available, use:

- wallet
- market / condition
- token / outcome
- side
- fill price
- shares / amount
- source timestamp
- transaction/activity identifiers
- nearby opposite-outcome activity
- position before/after when reconstructable

## Clustering

Related fills should be aggregated into one episode using a predeclared deterministic rule based on market, token/outcome, direction and bounded time proximity.

The clustering window must be frozen before outcome analysis and evaluated for sensitivity without threshold hunting.

## Exposure interpretation

Examples:

- `0 -> +YES` = ENTER
- `+YES -> larger +YES` = ADD
- `+YES -> smaller +YES` = REDUCE
- `+YES -> 0` = EXIT
- `+YES -> -/NO directional exposure` = FLIP only when exposure semantics are clear
- simultaneous/near-simultaneous paired YES/NO activity may be HEDGE/ARBITRAGE and must not be treated as a directional vote without evidence

## Fail closed

If activity cannot be reconciled into a coherent exposure change:

`UNKNOWN -> SKIP`

Do not force classification to increase sample size.

## Evaluation unit

The independent intent episode, not the raw fill, is the primary statistical unit for wallet skill, copyability and PnL comparisons.

## Live observer requirement

Persist both source timestamps and `first_observed_time`. Intent may be reconstructed only from information actually received by that time; later fills may update the episode prospectively but cannot retroactively improve an earlier decision.
