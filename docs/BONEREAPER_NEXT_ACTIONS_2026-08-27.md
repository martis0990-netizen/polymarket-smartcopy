# Bonereaper research — next actions from the 2026-08-27 checkpoint

Status: **EVIDENCE COLLECTION; NO LIVE-ORDER AUTHORIZATION**

## Established checkpoint

- Execution is mixed, not a pure grid: the original 77 fills were approximately 50/50 maker/taker
  by notional.  Opposite-leg inventory was more often maker in the larger completed samples, but
  this is not universal in every interval.
- The strict 15-second “buy after a full-window fall” hypothesis was not supported.  The observed
  pattern is better described as impulse, partial pullback, then balancing-leg acquisition.
- The first SHA-bound public-book confirmatory bundle contributed two independent 15m conditions:
  one `PRE_POSITIONED_DOMINANT` and one `LATE_DOMINANT`.  Formal progress is `2/30`, with both 5m
  strata still empty.
- Frozen pre-open signal progress from earlier clean data is `3/30`: Binance and Chainlink signs
  aligned on 2/3 conditions and were mutually concordant in all three, so the driver is unresolved.
- Frozen post-open signal progress is `2/40`: Binance 15s momentum aligned 2/2; the Chainlink
  opening barrier aligned 1/2.  These are descriptive counts, not a passed gate.
- Bundle v3 proved that sequential Gamma discovery consumed the needed pre-open history.  Parallel
  discovery reduced it from about 30.5 seconds to 9.5 seconds.
- The second v3 bundle produced 13 valid fee-aware receipts ($182.93; 6 maker, 7 taker), but all
  belonged to current markets while the book was bound to following markets.  They were correctly
  excluded rather than joined across conditions.
- Bundle v4 freezes dual-window binding: current conditions for expiring-market fills and safe
  following conditions for pre-open decisions.  Its first attempt failed closed on a real CLOB
  source-timestamp regression and contributes no evidence.

## Assessment of the JLM 5.3 proposal

Use the proposal as a hypothesis queue, not as a recovered strategy.  Its strongest testable
architecture is `Chainlink resolution anchor + Binance lead/momentum + separate maker inventory and
taker conviction loops`.  Its exact volatility weights, Gaussian fair-value formula, logit clamp,
inventory coefficients, latency/location claims, and time-to-profit estimates are not identified by
Bonereaper evidence.  RSI/EMA/MACD are currently redundant trend transformations, not independent
signals.  GPT belongs in research and review, not in the deterministic subsecond execution path.

## Ordered plan

1. **Collect clean Bundle v4 boundaries.** Run bounded 120-second public-only captures across 5m
   opens; preserve every failed run and count only clean SHA-bound roots.
2. **Decode and bind receipts.** Match Polygon receipts fee-aware, then filter to exact bound
   condition and token IDs before any role or book conclusion.
3. **Finish the maker-ladder gate.** Accumulate 30 eligible independent conditions with at least
   five in each BTC/ETH × 5m/15m stratum.  Keep same-second and gap/startup fills ineligible.
4. **Finish signal gates separately.** Reach 30 eligible pre-open conditions and 40 post-open
   conditions (at least 20 taker).  Prioritize discordant Binance-versus-Chainlink observations;
   they distinguish the feeds better than more concordant rows.
5. **Add executed-flow tests only after freezing them.** Test Binance taker OFI and BTC→ETH lead
   against the same first-taker labels.  Do not add RSI/MACD variants unless they contribute
   information beyond momentum out of sample.
6. **Test economics, not just direction.** Compute per-fill fee, pair cost, 10/30/60-second markout,
   adverse selection, and maker/taker PnL attribution.  Look for on-chain merge evidence separately.
7. **Only then test a fair-value model.** Compare an empirical `P(outcome | distance to K, time,
   volatility)` model with Polymarket mid using walk-forward Brier score and net executable edge.
8. **Paper execution gate.** Inject measured observation/order latency, pessimistic queue position,
   cancellations and fees.  No real-money run until positive net expectancy is reproduced on held-
   out conditions with explicit loss limits and kill switches.

## 14:48 UTC addendum — first clean split-book bundle

Bundle `bonereaper-prospective-bundle-v5-20260827-01` cleanly captured `14:43:03–14:45:12 UTC`.
Its root manifest SHA256 is
`3748dbd327adbdfeea8506bcb8f747f1831b721afe3ea782933d82da00b69160`.

- Chainlink: 106 BTC and 106 ETH events, zero reconnects.
- Wallet: 40 live-observed rows, zero gap failures; 34 supported BTC/ETH receipts and all fee-aware
  roles unambiguous.
- Receipts: 11 maker and 23 taker fills; $1,318.54 total notional; receipt-row SHA256
  `1cbbe07f740682e1f6542d1ed70d7d2b8b63a9099a3366382aa3e3b1bff2ab31`.
- Both current and safe book groups initialized 8/8 tokens with zero reconnects.  All 34 receipt
  rows matched one exact bound token; none was excluded as unbound.

Public-book scoring added two independent 5m conditions.  BTC 5m and ETH 5m were both
`LATE_DOMINANT`: six eligible maker fills and $107.25 eligible maker notional had no exact level
continuously visible for the frozen one-second lookback.  Five additional maker fills ($87.36)
remained startup/same-second ineligible.  Cumulative progress is now `4/30`: three late-dominant,
one pre-positioned-dominant, and one condition in each required asset × horizon stratum.

Pre-open scoring added three conditions:

| Market | Lead | Side | Binance 15s | Chainlink 15s | BTC lead |
|---|---:|---|---|---|---|
| ETH 15m | 26 s | Up | Up ✓ | Up ✓ | Up ✓ |
| BTC 5m | 57 s | Up | Up ✓ | Down ✗ | n/a |
| ETH 5m | 12 s | Down | Up ✗ | Up ✗ | Up ✗ |

The BTC 5m row is the first prospective discordant Binance-versus-Chainlink observation in this
study.  It favours Binance momentum for that condition, but one row is not a gate.  Combined frozen
pre-open progress is `6/30`: Binance `4/6`, Chainlink `3/6`, and descriptive BTC lead for ETH `2/3`.
Post-open progress remains `2/40`; this bundle correctly contributed zero because current markets
lacked complete pre-open Chainlink coverage and following-market takers all occurred before open.

## Prospective economics addendum

The first frozen FIFO economics calculation used all 34 exact-bound receipt rows.  Two conditions
formed 141.670726 paired units, and 100% cost more than `$1` before and after decoded fees.  The
after-fee weighted costs were `1.24911` for ETH 5m and `1.04636` for BTC 5m.  Therefore this bundle
does not support a simple deterministic sub-$1 pair-arbitrage explanation.

Residual inventory was much larger than matched inventory, including 1,562.2 following-market BTC
`Up` units at an after-fee mean cost of `0.50415`.  Taker markout was negative in aggregate at the
frozen 10/30/60-second horizons; maker markout was negative at 10/30 seconds and positive at 60
seconds, with material variation by condition.  Economics status is `COLLECTING`, `2/30` paired
conditions.  The architecture plan must treat the complementary leg as inventory insurance that
may rationally cost more than `$1` per completed pair, not assume every pair is an arbitrage.
