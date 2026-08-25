# Execution Realism Specification

## Principle

A profitable source wallet can be uncopyable. SmartCopy performance must be evaluated from the follower's first observable and executable state.

## Observation latency

Persist:

- `source_event_time`
- `first_observed_time`
- `decision_time`
- `order_send_time`
- `follower_fill_time`

The live paper observer must measure the distribution of source-to-observation latency (`p50/p90/p99`). Historical research may not assume zero delay unless the source is genuinely observable at that time.

## Executable prices

Use bid/ask and visible book depth. Midpoint may be reported descriptively but never assumed as a fill.

Every COPY decision requires a max acceptable price/min acceptable sell price. If the book moves past that boundary before execution, cancel/skip rather than chase.

## Fees

Fee semantics are versioned market inputs and must be verified against current official Polymarket rules for the specific market family. Do not hard-code one universal fee assumption for all categories.

## Fill simulation

Paper/shadow modeling should account for:

- available top-of-book size
- deeper levels if crossed
- taker vs passive/maker behavior
- partial fills
- order TTL
- stale signal cancellation
- queue uncertainty for passive orders
- adverse selection

Do not extrapolate fills beyond visible liquidity without a separately justified model.

## Passive vs aggressive copy

The project may compare:

- `PASSIVE_COPY`
- `AGGRESSIVE_COPY`

Aggressive copying may capture more signals but pays spread/fees and can suffer adverse selection. Passive copying may reduce cost but adds queue/non-fill risk. Both require separate evidence.

## Edge decay

For each validated wallet x strategy class, estimate how follower expectancy changes with delay. Delay buckets are predeclared. If public observability is slower than the source alpha half-life, that strategy is not copyable even if the source wallet is highly profitable.

## Shadow benchmark

At Stage 7, run the full decision/risk/order lifecycle with actual order submission disabled and compare:

- Source reference
- BlindCopy
- SmartCopy
- Matched control

The same observability and execution assumptions must be used for BlindCopy and SmartCopy so filtering is the only intended difference.

## Tiny-live prerequisite

No live orders until observed paper/shadow evidence shows:

- positive net expectancy
- SmartCopy > BlindCopy
- latency survivability
- sufficient independent decisions
- realistic fill rates
- acceptable drawdown
- no single-event dominance
