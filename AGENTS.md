# Agent Operating Rules

This project is evidence-gated and intentionally small.

## Prime directive

SmartCopy copies residual edge, not wallets.

## Workflow

For meaningful code changes use:

`Architect -> Coder -> Test Engineer -> Reviewer`

For research/data work use independent roles where needed:

`Data Analyst -> Trading Researcher -> Test Engineer -> Reviewer`

Bound verification:

- one mandatory verification pass
- maximum two fix -> verify cycles
- PASS -> STOP
- reopen a settled criterion only with new contradicting evidence

## No overengineering

No measured gap -> no component.

Do not add a new framework, database, agent runtime, ML system or indexer because it might be useful later.

## Research discipline

- source event time is not observation time
- no future leakage
- no midpoint fills
- no raw-fill sample inflation; use independent intent episodes
- no hidden threshold/horizon sweep
- negative results are valid
- high wallet PnL is not proof of copyability
- wallet skill is conditional on market family/horizon
- unknown strategy -> SKIP

## Execution discipline

- no live orders until all roadmap gates pass
- no LLM in trade decision/risk/execution hot path
- every COPY must include max acceptable price and size cap
- risk is follower-owned, not proportional to source wallet size
- use actual executable prices, visible depth and current fee semantics

## TradingLab boundary

Do not duplicate TradingLab. Consume stable verified research artifacts/contracts where appropriate. SmartCopy owns wallet observation, intent reconstruction, copyability, risk and eventual execution.

## Current authorization

`PROJECT_SPEC_FROZEN_V0`

Documentation/research scaffolding is allowed. Production/live execution is not authorized.
