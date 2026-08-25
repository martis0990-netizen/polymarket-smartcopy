# SmartCopy Roadmap

The roadmap is evidence-gated. Passing a stage means its acceptance criteria were demonstrated, not merely implemented.

## Stage 0 — Frozen semantics

Goal: make later research impossible to rewrite after seeing results.

Freeze definitions for:

- source trade / source intent
- source timestamp
- first observed timestamp
- decision timestamp
- hypothetical or real order-send timestamp
- follower fill timestamp
- source price
- observed BBO
- follower executable price
- source return
- follower return
- residual edge
- independent decision episode

Acceptance:

- deterministic definitions documented
- no future information in signal construction
- exact rules for latency, fees and fills documented

Deliverable: `RESEARCH_CONTRACT.md`.

## Stage 1 — Wallet Intelligence

Goal: discover which wallets deserve observation and where their skill is concentrated.

Inputs:

- Polymarket leaderboard
- historical positions / activity
- realized PnL
- market metadata

Build per-wallet evidence:

- realized PnL
- trade and market count
- days active
- consistency through time
- maximum drawdown where reconstructable
- profit concentration
- category specialization
- horizon specialization
- entry-price distribution
- average trade size
- repeatability

Do not assign one universal score. Build `WalletSkillProfile` by market family and horizon.

Classify likely behavior when evidence permits:

- `DIRECTIONAL`
- `MARKET_MAKER`
- `ARBITRAGE`
- `PAIRED_HEDGE`
- `SCALPER`
- `UNKNOWN`

`UNKNOWN` is not copyable.

Acceptance:

- watchlist contains only sufficiently sampled wallets
- one lucky market cannot dominate a high score without penalty
- market-family skill is separate from global PnL

## Stage 2 — Source Intent Reconstruction

Goal: reconstruct position decisions rather than mirror individual fills.

Cluster public fills into intent episodes such as:

- `ENTER`
- `ADD`
- `HOLD`
- `REDUCE`
- `EXIT`
- `FLIP`
- `HEDGE`

Example: 50 fills that increase YES exposure by 20,000 shares represent one source exposure change, not 50 copy signals.

Acceptance:

- deterministic clustering
- paired/hedged behavior is not mislabeled directional
- repeated fills do not create duplicated follower signals

## Stage 3 — Residual Edge / Delay Decay Research

This is the main proof-of-value gate.

For every source decision, compare source performance with hypothetical follower performance at the first realistically observable time and under delayed entry assumptions.

Estimate an edge-decay curve such as:

- observed immediately when first public
- +1s
- +3s
- +5s
- +10s
- +20s

Use actual executable book prices, fees, spread, visible liquidity and conservative fill assumptions.

Primary question:

**Does a follower retain positive net expectancy after public observability delay?**

Secondary question:

**Can a deterministic filter identify the subset where residual edge remains?**

Gate:

- if no reproducible residual edge exists -> `NO_EDGE_STOP`
- no threshold hunting after failure

## Stage 4 — Deterministic Copyability Engine v1

Only after Stage 3 passes.

Inputs:

- source wallet
- reconstructed intent
- wallet x market skill
- source entry / exposure change
- first observed time
- current bid/ask/depth
- edge-decay evidence
- fee / spread / slippage assumptions
- current portfolio exposure

Outputs:

- `COPY`
- `WATCH`
- `SKIP`
- maximum acceptable follower price
- allowed size
- evidence/reason codes

No ML initially.

## Stage 5 — Portfolio & Risk Engine

Risk is sized from the follower portfolio, never from whale size.

Controls include:

- max risk per signal
- max exposure per wallet
- max exposure per market
- max exposure per event
- correlated cluster exposure
- daily loss limit
- stale-signal rejection

BTC/ETH/SOL directional positions must be treated as a correlated crypto cluster when appropriate.

## Stage 6 — 24/7 Live Paper Observer

Goal: measure actual observability latency and live out-of-sample behavior without sending orders.

Record:

- source event time
- first time SmartCopy sees it
- decision time
- observed book state
- simulated order price / TTL
- simulated partial fills
- exit / resolution
- net PnL

Required output: live latency distribution (`p50/p90/p99`) and out-of-sample performance.

## Stage 7 — Shadow Execution

Run the complete production decision/risk/order lifecycle with order submission disabled.

Benchmark four cohorts:

1. source wallet reference
2. blind copy
3. SmartCopy
4. matched random/control

Key acceptance rule:

`SmartCopy > BlindCopy` on unseen data after all modeled execution costs.

Also require:

- positive net expectancy
- acceptable drawdown
- no single-trade profit dominance
- sufficient independent decisions
- edge survives measured observability latency

Failure -> no live capital.

## Stage 8 — Tiny Live

Only after all prior gates pass.

Start with:

- one market family
- 2–3 verified wallet x strategy classes
- tiny capital
- hard kill switches

Scale only from measured live evidence.

## Stage 9 — Smart Money Layer

Deferred until single-wallet SmartCopy is proven.

Add:

- multi-wallet consensus
- lead/lag wallet dependency graph
- correlated-source de-duplication
- contrarian exit / reduce signals
- independent-vote weighting

Three wallets copying one upstream source count as one information source, not three.

## Deferred until measured need

Do not add by default:

- LLM trading agents
- vector databases
- graph databases
- custom blockchain indexer
- distributed backend
- ML classifiers
- wallet embeddings
- social sentiment engine
- dashboard/mobile app
- subscriptions/marketplace

Rule: **No measured gap -> no component.**
