# SmartCopy Architecture

## Design goal

Keep production small and deterministic. SmartCopy should consume verified public market/wallet data, reconstruct source intent, estimate copyability, apply portfolio risk rules and either simulate or execute an order.

## High-level flow

```text
Polymarket public APIs / market WS
          |
          +--> Wallet Intelligence
          |
          +--> Source Activity Observer
          |
          +--> Market Context
                    |
                    v
             Intent Reconstruction
                    |
                    v
             Copyability Engine
                    |
             +------+------+
             |             |
           SKIP          WATCH/COPY
                           |
                           v
                      Risk Engine
                           |
                           v
                     Paper / Shadow
                           |
                           v
                     Live Executor
                    (only after gates)
```

## Module boundary

Initial package layout:

```text
src/smartcopy/
    models.py
    polymarket.py
    wallets.py
    observer.py
    intent.py
    context.py
    copyability.py
    risk.py
    paper.py
    evaluation.py
```

### `models.py`
Canonical immutable domain models and enums. No API calls.

### `polymarket.py`
Thin adapter over official/public Polymarket interfaces required by SmartCopy. Keep transport semantics outside decision logic.

### `wallets.py`
Wallet discovery, historical metrics, specialization and `WalletSkillProfile` construction.

### `observer.py`
Observes tracked public wallet activity and records first-observed timestamps. Must preserve the distinction between source event time and SmartCopy observation time.

### `intent.py`
Clusters fills/activity into source exposure decisions (`ENTER`, `ADD`, `REDUCE`, `EXIT`, `FLIP`, `HEDGE`).

### `context.py`
Provides current market state: bid/ask, spread, visible depth, market metadata, relevant timing and fee inputs.

### `copyability.py`
Pure deterministic decision layer. Consumes source intent + wallet skill + current executable market state + historical edge-decay evidence. Emits `COPY`, `WATCH` or `SKIP`, max acceptable price and reason codes.

### `risk.py`
Follower-owned sizing and portfolio controls. Never scales directly from whale notional.

### `paper.py`
Paper/shadow lifecycle and conservative fill simulation. Real order submission is not part of early stages.

### `evaluation.py`
BlindCopy vs SmartCopy vs matched-control evaluation, independent episode accounting and out-of-sample reports.

## Storage

Start with SQLite + Parquet/JSON artifacts where useful. No external database is justified yet.

Required persisted records should be append-only or versioned where practical:

- raw observed wallet activity
- first-observed timestamp
- reconstructed intent episodes
- market context at decision time
- decision and reason codes
- hypothetical/real order lifecycle
- evaluation outcomes

## Determinism

Research and decision code should be reproducible from frozen inputs. Where randomness is needed for controls/bootstrap, seeds must be explicit and recorded.

## No LLM in the hot path

LLMs may assist offline research/documentation but may not decide whether a live order is sent, alter sizing, infer a price limit, or bypass risk gates.

## Fail-closed behavior

Ambiguity must resolve to `SKIP`, especially for:

- unknown wallet strategy
- stale activity
- missing executable book state
- insufficient liquidity
- unresolved fee semantics
- position reconstruction conflict
- correlated exposure beyond limit

## TradingLab boundary

SmartCopy may import data contracts or verified artifacts from TradingLab only through explicit stable interfaces/artifacts. Avoid shared mutable runtime state and avoid duplicating TradingLab research infrastructure inside SmartCopy.
