# Wallet Intelligence Specification

## Objective

Find wallets worth studying and determine **where** their skill is repeatable. Do not rank solely by headline PnL.

## Candidate discovery

Use public Polymarket leaderboard/activity/positions and market metadata. Candidate discovery may begin from top PnL/volume lists, but acceptance into the watchlist requires deeper evidence.

## Required metrics

Per wallet, where reconstructable:

- realized PnL
- trade/fill count
- independent intent count
- market count
- active days
- PnL consistency through time
- maximum drawdown
- largest single-event contribution
- profit concentration
- market-category distribution
- horizon distribution
- average/median trade size
- entry-price distribution
- holding-time distribution
- repeatability by market family

## Profit concentration

A wallet with very high PnL from one or two events is not equivalent to a wallet with repeatable PnL across many independent decisions.

Record metrics such as:

- top-1 event share of lifetime PnL
- top-5 event share
- effective number of profitable events

High concentration lowers confidence.

## Conditional skill

Build skill by `wallet x market_family x horizon`, not one universal score.

Example families:

- crypto_updown_5m
- crypto_updown_15m
- crypto_updown_1h
- crypto_price_threshold
- football_match_winner
- sports_over_under
- esports_match_winner
- politics_long_dated

A wallet may be strong in one and unverified in all others.

## Strategy archetype

Attempt to classify only from observable evidence:

- DIRECTIONAL
- MARKET_MAKER
- ARBITRAGE
- PAIRED_HEDGE
- SCALPER
- UNKNOWN

Classification confidence must be explicit. Do not infer participant identity or private intent beyond observable activity.

## Initial research focus

Start with high-frequency, repeatable crypto Up/Down participants because these markets provide:

- short horizons
- frequent decisions
- live CLOB microstructure
- external BTC/ETH reference markets
- measurable delay/edge-decay opportunities

Bonereaper-class activity is an initial research target, not a pre-approved wallet.

## Watchlist acceptance

A candidate is promoted only if:

- enough independent decisions exist
- category/horizon specialization can be estimated
- profit is not dominated by a tiny number of outcomes
- source behavior is observable with sufficient timeliness
- historical data is sufficient for holdout evaluation

Otherwise classify `WATCH_ONLY` or `INSUFFICIENT_SAMPLE`.
