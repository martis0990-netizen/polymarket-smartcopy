# Limitless 15m structure: prospective paired paper test v1

Status: **FROZEN PROPOSAL; NOT RUNNING; NO PNL CLAIM**. Specified 2026-10-04 UTC before the first prospective 15m window on 2026-10-05 00:00 UTC. This is a separate experiment. The hourly-v1, inventory-v2, existing 15m model/constant-50 control, and October 6 hourly structural diagnostic remain unchanged. No real orders.

## Prerequisite

The [15m paper contract](LIMITLESS_15M_PAPER_CONTRACT_V1.md) is specified but its executor and main-state migration are not yet verified. The published structural follow-up observed H1=UNKNOWN in all 46 scored hourly decisions; H4=UNKNOWN in all 46. A parallel 15m PnL claim is blocked until a prospective executor produces reconciled fills and observed payouts. Empty filtered positions are a coverage failure, not a zero-risk winning strategy.

## Frozen input and comparison

Use only BTC/USD and ETH/USD 15-minute CLOB markets admitted by the existing 15m contract. The model account remains its current independent 100 USDC baseline. Create an additional independent 100 USDC **structure account** at the same prospective start, never funded by baseline. It evaluates exactly the model's decision opportunity, side, max acceptable price, cap, fee and first delayed book attempt. If the structure gate says SKIP, it places no paper entry. If ALLOW, it runs the same first-attempt execution and settlement rules from the 15m contract, with its own cash balance. Insufficient cash is its own NO_TRADE; no borrowing, favorable retry, partial fill or midpoint execution. The existing constant-50 control is not repurposed.

The gate never picks a YES/NO side, adjusts model probability or creates an entry. It is evaluated at the **original model's decision time** against Binance BTCUSDT/ETHUSDT 1m responses already received before that instant. Reconstruct UTC H1/M15/M5/M1 from complete closed M1 only using [frozen diagnostic v1 definitions](LIMITLESS_MARKET_REGIME_PROTOCOL.md): 16-bar minimum, 2/2 confirmed pivots, protected anchors and range/transition states. The H4 label is reported separately; it is not a gate until enough data exists. A later response or corrected candle cannot change the prior label. A source conflict, missing latest complete bar, insufficient swings or missing response yields UNKNOWN and SKIP. Record the input view digest and event availability.

The 15m label version is `limitless-15m-structure-label-v2`. A conflicting minute is excluded from the candle stream as soon as its second version becomes available. That gap resets the contiguous warmup on each affected timeframe. Older conflicts remain in the evidence ledger but do not permanently poison a new complete suffix. This is an explicit 15m data-availability rule; it does not change the frozen hourly diagnostic. The same conflict cannot retrospectively alter an earlier decision snapshot.

Gate v1:

| Baseline side | Required H1 state | Required most recent visible M5 close-break |
|---|---|---|
| YES | TREND_UP | UP, available within 300 seconds of decision |
| NO | TREND_DOWN | DOWN, available within 300 seconds of decision |

All H1 RANGE, TRANSITION, opposite trend and UNKNOWN states SKIP with separate reasons. M15 and M1 states are recorded for analysis but do not change entry. M5 UNKNOWN, absent/stale/opposite break SKIP. The 300-second event age is a fixed initial operational definition, not a fitted optimum. A future event is an integrity failure. These are deliberately narrow labels, not evidence of institutional activity or a claim that all Smart Money concepts are implemented. Do not change definitions based on October 5 outcomes.

## Provenance and gate before evaluation

Consume only SHA256-verified completed-success main capture archives and the matching cumulative state; retain ZIP artifact/run/head SHA, source request and receipt, decision identity, first errors, UTC quarter-hour, market metadata, oracle feed and book identity. Preserve all eligible conditions including UNKNOWN and missed decisions. Reject mismatched identity, invalid feed/settlement, conflicting or late source. Do not backfill old snapshots or sum cumulative reports. A smoke test or a manual screenshot is not prospective evidence.

Before calculating a comparative PnL, publish structure coverage over **all** eligible decisions: known H1/H4, UNKNOWN reasons, gate ALLOW/SKIP by reason, BTC/ETH and distinct quarter-hour clusters. Then reconcile both independent cash ledgers, first delayed book attempts and observed payouts. Pending claims remain pending, not losses or wins.

## Evaluation and stopping

October 5 UTC is discovery. October 6 00:00 UTC to the existing capture cutoff October 10 09:00 UTC is untouched holdout, only if the baseline and structure implementation and their source semantics were frozen before that period. If integration misses that boundary, use a later untouched interval; never relabel already seen outcomes as holdout.

Report both accounts on the same eligible condition denominator: settled net USDC, spent capital, cash/locked claims, drawdown, fills, skips, unresolved positions, and opportunity differences. Report per H1 state, BTC/ETH and quarter-hour clusters, with clustered uncertainty; do not count same-slot BTC and ETH as independent time observations. The original 15m gate of at least 60 resolved scored conditions, 60 distinct quarter-hour clusters and >=90% relevant observation coverage is a **coverage review**, not a profit threshold. Require meaningful H1-known and ALLOW samples before interpreting an apparent improvement. If these are empty or scarce: INSUFFICIENT_DATA. A higher PnL on discovery alone does not promote the gate.

The offline executor `limitless_15m_replay.py` consumes an existing verified main-artifact manifest (same `run`/`artifact`/`file.path` schema as the market-regime diagnostic), reads ZIPs locally, orders raw envelopes by receipt, applies the first oracle/book/after-delay book attempts, and reconciles three 100 USDC paper accounts: model, existing constant-50 control, and structure. Run `python research/limitless_15m_replay.py manifest.json --out paired_report.json`. It makes no API calls and does not change capture schedules. It reports UNKNOWN, pending claims and observation coverage. Two adjacent October 4 main ZIPs passed a retrospective continuity smoke (16 conditions, 14 decisions, H1 known 0, missing metadata 0, `INSUFFICIENT_DATA`), using a temporary pre-October-5 start bound **only in local smoke**. This is not a prospective result or an independent economic review; no live schedule or real capital follows automatically.
