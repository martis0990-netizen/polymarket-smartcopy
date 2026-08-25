# Decision Model v0

## Principle

SmartCopy does not copy wallets or transactions. It decides whether a newly observed source intent still contains enough residual edge for the follower.

## Inputs

A decision may use only information available at `decision_time`:

- source wallet identity
- reconstructed source intent
- wallet x market-family skill profile
- source exposure change estimate
- source price summary
- first-observed timestamp
- current executable bid/ask
- visible depth / spread
- current market metadata
- current fee assumptions
- historical edge-decay evidence for the relevant wallet/strategy class
- current follower portfolio exposure

## Wallet Skill Profile

Do not compress wallet quality into one global score. Use a conditional profile, e.g.:

```text
wallet: X
crypto_updown_5m: 0.94
crypto_updown_15m: 0.91
crypto_updown_1h: 0.72
sports: unknown
politics: unknown
```

Inputs to skill estimation may include:

- realized PnL
- independent decision count
- market count
- days active
- consistency through time
- profit concentration
- drawdown
- category specialization
- horizon specialization
- entry-price distribution
- repeatability

High historical PnL with very few independent bets must be discounted.

## Strategy classification

When evidence permits classify the source behavior as:

- DIRECTIONAL
- MARKET_MAKER
- ARBITRAGE
- PAIRED_HEDGE
- SCALPER
- UNKNOWN

The system must not copy a single visible leg from a likely hedge/arb structure as if it were directional.

## Copyability dimensions

The v0 engine should remain deterministic and explainable. Candidate dimensions:

- `source_skill`
- `market_fit`
- `signal_freshness`
- `remaining_edge`
- `liquidity_quality`
- `execution_quality`
- `portfolio_fit`

Do not introduce ML until a deterministic baseline is proven insufficient by measurement.

## Decision outputs

Every decision returns:

- `COPY`, `WATCH`, or `SKIP`
- reason codes
- max acceptable follower price (or min acceptable price for sells)
- max allowed size
- expiry/staleness condition
- evidence version / model version

## Price discipline

A COPY decision without a maximum acceptable price is invalid.

Example:

```text
source_buy_price = 0.421
current_ask = 0.432
max_acceptable_price = 0.439
```

If the market moves to 0.448 before execution, the order is cancelled/skipped. SmartCopy must never chase merely because the source wallet is highly ranked.

## Residual Edge

The decision target is expected follower value remaining after observation, not source alpha.

At minimum account for:

- deterioration from source price to current executable price
- spread
- fees
- expected slippage
- latency / stale-signal decay
- adverse-selection reserve

If the sign or magnitude is too uncertain, return `WATCH` or `SKIP`.

## Hard skip conditions

Examples:

- source strategy = UNKNOWN
- likely hedge/arb leg without complete intent
- stale observation beyond validated copyability window
- missing executable BBO
- insufficient visible depth
- fee semantics unresolved
- price already beyond max acceptable level
- follower risk/correlation limit exceeded
- source sample too small for relevant wallet x strategy class

## Consensus — deferred

Multi-wallet consensus is Stage 9. When added, wallets are not automatically independent votes. A lead/lag dependency graph must discount followers/copycats so one upstream information source cannot become three votes.

## Contrarian state — deferred

Later versions may treat `REDUCE`, `EXIT`, and `FLIP` from proven sources as information signals. These are not automatically inverse trades; their value must be measured separately.
