# Bonereaper pre-open model competition v4 — frozen contract

Status: **FROZEN BEFORE ANY V4-ELIGIBLE WALLET DECISION**

## Purpose

Distinguish four explanations for Bonereaper's aggressive pre-open direction:

1. very short Binance momentum;
2. a Supertrend regime on the market's own higher timeframe;
3. a confirmed higher-timeframe break of structure;
4. an oracle-relative binary fair-value estimate.

The discovery and v3 conditions observed before this contract may test the
implementation, but cannot enter a v4 count or gate.

## Population and label

- Wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`.
- BTC and ETH 5m/15m Up/Down conditions resolved with the 60-second Chainlink
  TWAP rule.
- Independent unit: one `condition_id`.
- Decision window: `[market_start - 60s, market_start)`.
- Label: outcome of the earliest unambiguous taker BUY episode. Multiple fills
  of one intent in the same second are collapsed. Opposing outcomes in that
  first second make the condition ineligible.
- Stop at 30 eligible conditions or seven complete UTC days after the first
  eligible condition, whichever comes first. The latter result is
  `UNDERPOWERED`; collection is not extended after looking at model scores.

## No-leakage and coverage

Every feature uses exchange/source timestamps strictly before the wallet's
source second `t`; records from `t` are excluded. Binance candles must be fully
closed before `t`. Chainlink data must have zero unaccounted recorder gaps over
the required lookback. Receipt role must bind uniquely under the fee-aware CTF
Exchange V2 decoder.

Capture must start at least 11 minutes before market open and end after market
open. Binance one-second data must cover `[t-601s, t)`. Indicator history must
contain at least 100 fully closed higher-timeframe candles. Missing history
makes only the affected candidate ineligible; it is never forward-filled
across a known gap.

## Frozen candidate A — `MOM15`

Sign of the asset's Binance one-second close-to-close log return from `t-16` to
`t-1`. Positive is Up, negative is Down, exact zero is `None`.

## Frozen candidate B — `SUPERTREND_HTF_10_3`

Use Binance spot candles whose duration equals the Polymarket horizon: 5m for a
5m condition and 15m for a 15m condition. Only the last 100 fully closed
candles before `t` are addressable.

True range is `max(high-low, abs(high-prev_close), abs(low-prev_close))`. ATR is
Wilder ATR with length 10, seeded by the arithmetic mean of the first ten true
ranges. Basic bands are `(high+low)/2 ± 3*ATR`; final bands use the standard
carry rule against the prior final band and prior close. The regime flips Up
when close is above the prior final upper band and Down when close is below the
prior final lower band; otherwise it persists. The direction on the final
fully closed candle is the candidate. No alternate ATR seed, multiplier,
timeframe, or intrabar Supertrend is allowed.

## Frozen candidate C — `BOS_HTF_2`

Use the same fully closed higher-timeframe candles. A pivot high at index `i`
requires its high to be strictly greater than the highs of the two preceding
and two following candles. A pivot low is defined symmetrically with strictly
lower lows. A pivot is unavailable until both following candles have closed.

Process candles in time order. State becomes Up when a later close is strictly
above the most recent confirmed pivot high, and Down when it is strictly below
the most recent confirmed pivot low. State then persists until an opposite
break. A candle breaking both levels, equal highs/lows, or no prior break yields
`None` for that condition. No wick-only break, discretionary swing selection,
CHoCH relabeling, or pivot-length sweep is allowed.

## Frozen candidate D — `ORACLE_FV`

Let `K_hat` be the latest Chainlink 60-second TWAP strictly before `t`. Let
`B_t` be the last Binance one-second close before `t`.

Estimate the Binance/Chainlink level basis using paired strict-prior samples in
`[t-600s, t-60s)`: for each Binance second, pair the latest Chainlink value
available before that second and take

`b_med = median(log(B_i / C_i))`.

The basis-corrected spot is `S = B_t * exp(-b_med)`. Per-second volatility is
the square root of the mean squared Binance one-second log returns over
`[t-301s, t)`. Let `tau = market_end - t` seconds and

`z = log(S / K_hat) / (sigma_second * sqrt(tau))`, `p_up = Phi(z)`.

`p_up > 0.5` is Up, `p_up < 0.5` is Down, and equality/non-finite inputs are
`None`. There is no drift term, fat-tail correction, volatility blend,
probability clipping, or parameter fit in v4. This deliberately simple model
tests whether an oracle-relative level adds information before a richer model
is authorized.

## Frozen gates

Primary alignment is unweighted by condition. For each candidate:

- `SUPPORTED_DESCRIPTIVELY`: alignment at least 65% and Wilson 95% lower bound
  above 50%;
- `NOT_SUPPORTED`: alignment at most 55%;
- otherwise `INCONCLUSIVE`.

Pairwise dominance is evaluated only where both candidates exist and disagree.
It requires at least 10 discordant conditions, at least 65% alignment for the
winner, and a lead of at least 20 percentage points. Otherwise report
`UNDERPOWERED_COMPARISON` or `NO_DOMINANT_CANDIDATE`.

The primary output is imitation of Bonereaper's direction, not trading alpha.
After settlement, report each candidate's outcome alignment; for `ORACLE_FV`
also report Brier score and log loss. These secondary scores cannot upgrade a
failed wallet-alignment gate.

## Interpretation boundary

Correlated models can remain observationally equivalent. A candidate can be
identified only from strict-prior disagreement conditions. Alignment does not
prove Bonereaper uses that named indicator; it means the indicator is an
observationally sufficient proxy at this resolution.

No live orders, signing, automated trading, parameter search, or LLM hot-path
decision is authorized.
