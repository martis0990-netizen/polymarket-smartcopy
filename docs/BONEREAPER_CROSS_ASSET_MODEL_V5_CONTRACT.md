# Bonereaper cross-asset model v5 — frozen contract

Status: **FROZEN BEFORE ANY V5-ELIGIBLE WALLET DECISION**

## Purpose

Test whether the same external directional architecture that is being studied
on BTC/ETH generalizes across Bonereaper's broader crypto universe. V5 is a new
population; it does not alter, merge with, or rescue the v4 result.

The 91 SOL/BNB/XRP/HYPE/DOGE rows observed on 2026-08-28 were inspected before
this contract. They may motivate the universe and test parsing, but they are
discovery-only and can never enter a v5 score.

## Frozen population

- Wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`.
- Core assets: BTC, ETH, SOL, XRP, BNB and DOGE.
- Horizons: 5m and 15m Up/Down conditions.
- Resolution input: the asset's 60-second Chainlink TWAP.
- Independent unit: one `condition_id`.
- Decision window: `[market_start - 60s, market_start)`.
- Label: outcome of the earliest unambiguous fee-aware taker BUY episode.
  Multiple fills in the same transaction/second are one intent. Opposing
  outcomes in the first eligible second make the condition ineligible.
- HYPE is recorded as an engineering cohort but excluded from confirmatory v5
  scoring until a separate strict-prior external-venue proxy contract is
  frozen. It cannot be silently mapped to BTC or another asset.

Stop at 60 eligible core conditions or seven complete UTC days after the first
eligible v5 condition, whichever comes first. Report `UNDERPOWERED` if time
expires first. Collection cannot be extended after inspecting scores.

## Capture and no-leakage gate

Capture all available RTDS `crypto_prices_twap_sixty` symbols, then retain the
seven named crypto symbols in an immutable raw artifact. A confirmatory core
condition requires its own Chainlink symbol to be present with zero
unaccounted reconnect gap over the required lookback.

Every feature uses source timestamps strictly before wallet source second `t`.
The second containing the wallet trade and all later observations are excluded.
Binance candles must be fully closed before `t`; no forward fill crosses a
known gap. Polygon receipts must bind the source fill uniquely under the
fee-aware CTF Exchange V2 decoder.

Capture starts at least 660 seconds before an eligible market open and ends
after that open. A clean bundle with zero eligible decisions remains valid.

## External venue

For the six core assets use the same asset's Binance spot pair `<ASSET>USDT`.
Before a condition can score, the pair must return complete native 1s and
horizon-matched 5m/15m history under the existing strict normalization rules.
Missing or delisted pairs make only that condition ineligible; no alternate
venue is chosen after observing the Bonereaper direction.

## Frozen candidates

V5 reuses the four v4 definitions without parameter changes:

1. `MOM15`: sign of the strict-prior 15-second Binance log return.
2. `SUPERTREND_HTF_10_3`: Wilder ATR(10), multiplier 3, on fully closed native
   candles matching the Polymarket horizon.
3. `BOS_HTF_2`: persistent close-break state from confirmed length-2 pivots on
   the same fully closed native candles.
4. `ORACLE_FV`: basis-corrected Binance spot versus the latest strict-prior
   asset-specific Chainlink 60-second TWAP, with 300-second realized volatility
   and remaining time to settlement exactly as defined in v4.

No asset-specific threshold, indicator parameter, probability calibration or
discretionary structure relabeling is allowed in v5.

## Frozen evaluation

Primary alignment is pooled and unweighted by condition. Candidate gates are
unchanged from v4:

- `SUPPORTED_DESCRIPTIVELY`: alignment at least 65% and Wilson 95% lower bound
  above 50%;
- `NOT_SUPPORTED`: alignment at most 55%;
- otherwise `INCONCLUSIVE`.

Pairwise dominance requires at least 10 discordant conditions, at least 65%
alignment for the winner, and a lead of at least 20 percentage points.

Report per-asset and leave-one-asset-out tables as diagnostics. A per-asset
verdict is forbidden below 10 eligible conditions. These diagnostics cannot
upgrade a failed pooled gate.

The primary target is imitation of Bonereaper's earliest pre-open taker
direction, not profit. Settlement alignment, Brier score and log loss remain
secondary. A later strategy may use model/Polymarket price divergence only
under a separately frozen fee-, slippage- and latency-aware paper-trading
contract.

## Interpretation and safety boundary

Shared alignment across assets supports a universal external-price engine, not
proof that Bonereaper uses a named indicator. Persistent asset-specific failure
supports routing or calibration differences. Only disagreement conditions can
separate correlated candidates.

No live orders, signing, automated trading, parameter search, credential
extraction or LLM hot-path decision is authorized.
