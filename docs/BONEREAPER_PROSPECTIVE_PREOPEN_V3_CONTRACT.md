# Bonereaper prospective pre-open signal study v3 — frozen contract

Status: **FROZEN AFTER THE DISCOVERY PILOT AND BEFORE ANY V3 OBSERVATION**

## Purpose

Test whether Bonereaper's earliest active BUY in a not-yet-started BTC/ETH Up/Down condition follows
strict-pre Binance momentum, the contemporaneous Chainlink TWAP trend, or neither.  The six
discovery-pilot conditions from 2026-08-27 select this question but are excluded from every v3
count and gate.

## Population and stopping rule

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- BTC and ETH 5m/15m Up/Down conditions using the 60-second Chainlink rule
- one independent unit per `condition_id`
- pre-open decision window: source time in `[market_start - 60s, market_start)`
- label: earliest unambiguous taker BUY episode in that window
- opposing outcomes tied in the earliest source second make the condition ineligible

Stop at the first of `30` eligible pre-open conditions or seven complete UTC days after the first
clean v3 observation.  If seven days end first, report `UNDERPOWERED`; do not extend after viewing
directions.

## Coverage and no-leakage rules

Required inputs are prospective wallet activity, Polygon receipt roles, Chainlink
`crypto_prices_twap_sixty`, and Binance BTCUSDT/ETHUSDT one-second aggregates.  Every candidate uses
source records strictly earlier than the wallet source second.  Same-second data is excluded.

An eligible condition requires:

- clean wallet and Chainlink capture covering at least 76 seconds before market start;
- no gap intersecting the pre-open decision or either 15-second lookback;
- exact market metadata and an unambiguous receipt role;
- a first taker episode inside the frozen 60-second pre-open window;
- complete strict-pre Binance and Chainlink inputs.

The official opening `K` at market start is future information for every v3 decision and is never
used as a feature.  It may be recorded later only as an outcome diagnostic.

## Frozen candidates

For source second `t`:

1. `BINANCE_MOM15`: sign of the asset's Binance close-to-close log return from `t-16` to `t-1`.
2. `CHAINLINK_MOM15`: sign of the asset's official TWAP update change between the last update before
   `t-15s` and the last update before `t`.
3. `BTC_LEAD15`: for ETH only, the strict-pre BTCUSDT 15-second momentum sign; descriptive secondary
   candidate.

Zero is `None`.  No threshold sweep, RSI, EMA, MACD, volatility fit, or notional reweighting is
allowed in the primary gates.

## Gates

Primary results use unweighted condition counts for candidates 1 and 2:

- `SUPPORTED_DESCRIPTIVELY`: alignment at least `65%` and Wilson 95% lower bound above `50%`;
- `NOT_SUPPORTED`: alignment at most `55%`;
- otherwise `INCONCLUSIVE`.

Compare candidates only on conditions where their signs disagree.  One dominates only with at
least `10` discordant conditions, at least `65%` alignment, and a lead of at least 20 percentage
points.  Otherwise report `UNDERPOWERED_COMPARISON` or `NO_DOMINANT_CANDIDATE`.

Report lead-time distribution and BTC/ETH, 5m/15m strata descriptively.  A notional-weighted table
cannot rescue a failed condition-count gate.

## Boundary

This study identifies a directional trigger, not fair-value calibration or profit.  A later,
separately frozen layer may test a forecast of the final opening TWAP, entry-price edge, realized
outcomes, or interaction with maker inventory.  No live orders, signing, parameter tuning, or LLM
decision loop is authorized.

