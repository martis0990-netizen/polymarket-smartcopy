# Polymarket SmartCopy

> SmartCopy does not copy wallets. It buys residual edge revealed by wallets.

Polymarket SmartCopy is a selective copy-trading research and execution project. Its purpose is not to mirror every public trade from a profitable wallet. It reconstructs the source trader's likely position change, measures whether that trader is skilled in the specific market family, estimates how much of the original edge remains after observation delay, spread, fees, slippage and liquidity constraints, and returns one of three decisions:

- `COPY`
- `WATCH`
- `SKIP`

## Core thesis

A profitable source trade is not automatically profitable for a follower. The project therefore optimizes for **Residual Edge**, not source PnL.

Conceptually:

`source action -> intent reconstruction -> wallet x market skill -> current executable market state -> edge decay -> risk -> COPY/WATCH/SKIP`

The first research objective is deliberately narrow:

**Does deterministic smart filtering outperform blind copy trading out of sample after realistic execution costs and observation latency?**

If the answer is no, the project stops or changes market family. It does not proceed to live trading by optimism or threshold tuning.

## Initial market family

The first candidate universe is short-horizon crypto prediction markets, especially:

- BTC Up/Down
- ETH Up/Down
- later SOL/BNB where activity and liquidity justify capture

High-frequency, category-specialized wallets such as Bonereaper-class traders are research candidates, never trusted sources by default.

## Product boundary

`TradingLab` is the research/evidence laboratory. `SmartCopy` is the wallet-intelligence, decision, risk and execution product.

TradingLab may produce evidence about wallet behavior, microstructure, replay, latency and execution. SmartCopy consumes verified outputs; it must not become a second TradingLab.

## Non-negotiable rules

- No LLM in the trading decision loop.
- No live trading before historical proof, out-of-sample paper validation and shadow execution.
- No wallet is copyable merely because it has high PnL.
- Do not copy individual fills; reconstruct source intent / exposure change.
- `source_time != observed_time`; backtests must enter only when the action could actually have been observed.
- Use executable bid/ask and visible depth, never midpoint fantasy fills.
- Fees, slippage, partial fills, latency and adverse selection are part of the strategy.
- Unknown or ambiguous source strategy -> `SKIP`.
- SmartCopy must beat BlindCopy on unseen data before live capital is allowed.
- Negative evidence is a valid result.
- No overengineering: no measured gap -> no new component.

## Project stages

0. Frozen semantics / research contract
1. Wallet discovery and Wallet Skill Profiles
2. Historical source-intent reconstruction
3. Residual-edge and delay-decay research
4. Deterministic Copyability Engine
5. Portfolio and risk engine
6. 24/7 live paper observer
7. Shadow execution and SmartCopy vs BlindCopy benchmark
8. Tiny live deployment only after all gates pass
9. Multi-wallet consensus, contrarian signals and dependency graph

See [ROADMAP.md](ROADMAP.md), [RESEARCH_CONTRACT.md](RESEARCH_CONTRACT.md), [ARCHITECTURE.md](ARCHITECTURE.md), [DECISION_MODEL.md](DECISION_MODEL.md), and [RISK_POLICY.md](RISK_POLICY.md).

## Status

`PROJECT_SPEC_FROZEN_V0`

No production trading code is authorized by this repository state.
