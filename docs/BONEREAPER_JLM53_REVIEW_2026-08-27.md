# Review of the “JLM 5.3” Bonereaper architecture proposal — 2026-08-27

Status: **HYPOTHESIS TRIAGE AGAINST CURRENT EVIDENCE**

## What the proposal gets right

| Proposal | Current evidence | Disposition |
|---|---|---|
| Chainlink is the resolution anchor; Binance can be a leading signal | The v2 post-open sample is underpowered, while the post-hoc pre-open pilot has Binance 15s alignment in 5/6 conditions | Keep as two competing, separately measured signals |
| Separate passive quoting from active taking | 77-fill study was 50.41% maker / 49.59% taker by notional; the second prospective bundle was 44.03% / 55.97% | Required architecture boundary |
| Opposite-leg inventory is often passively acquired | Original opposite-leg maker notional share was 62.42%; the new 391-row bundle gives 63.20% | Strong repeated mechanism evidence |
| Attribute maker and taker PnL separately | Role differences are large enough that aggregate PnL would hide the mechanism | Required future gate |
| Prefer executed flow to raw book imbalance | Sensible spoofing defense, but OFI is not yet captured prospectively here | Freeze and test later; do not assume |
| Conservative event-driven paper simulation and markout | Directly addresses adverse selection and observation delay | Keep before any live authorization |

## What is not reconstructed from Bonereaper

- The Gaussian binary fair-value equation, HAR-like volatility weights `0.4/0.4/0.2`, empirical
  calibration table, logit clamp `±0.5`, quote-width coefficient `2–3`, inventory skew, and taker
  threshold are design proposals.  Current wallet/receipt evidence does not identify those models
  or parameters.
- RSI, EMA, and MACD are not independent explanations in the existing pilot; their trend signs
  largely collapse to momentum.  Adding them now would be post-hoc indicator shopping.
- Maker status proves passive execution at fill time, not when the order was posted.  A public CLOB
  recorder is still required before calling the mechanism a continuously resting ladder.
- Pair completion does not prove an on-chain merge.  Merge transactions must be observed
  independently.
- The proposal's statement that crypto takers pay `0.07%` of notional is wrong.  Official docs use
  `fee = shares × 0.07 × p × (1-p)`: `0.07` is a curve parameter, not a flat percentage.  The fee
  peaks at `$1.75` for 100 shares at `$0.50`.  Research must use decoded per-fill fees rather than a
  flat notional haircut.  See [official fee documentation](https://docs.polymarket.com/trading/fees).
- Chainlink publishes exact 30s/60s TWAP values and observation timestamps, but explicitly does not
  publish the custom feed's internal sampling boundaries, weighting, rounding, or missing-input
  behavior.  A future-`K` forecast can be tested, but should not claim to reconstruct the oracle.
  See [official Chainlink TWAP documentation](https://docs.polymarket.com/market-data/chainlink-twap).
- Exact latency, server-region, minimum-order, win-rate, capital, and “first dollar in 2–4 weeks”
  claims are not strategy evidence.  They require current official mechanics and measured
  end-to-end latency; a winning trade is not proof of positive expected value.
- GPT is appropriate for research, code review, and hypothesis generation, not the deterministic
  subsecond hot path.  Runtime decisions must remain reproducible and bounded.

## Resulting research order

1. Finish the frozen v2 post-open barrier-versus-momentum collection without changing its gates.
2. Run the newly frozen v3 pre-open momentum-versus-Chainlink-trend study on new conditions only.
3. Add prospective public-book recording to test the exact one-second maker-level continuity rule.
4. Attribute pair economics, fees, and markout separately for maker inventory and taker conviction.
5. Only then freeze a fair-value/volatility model and test whether it improves over market mid by
   more than fees, latency, and conservative fill assumptions.

The current best architectural reconstruction is therefore narrower than the proposal:
`pre-open momentum-led taker positioning + mixed post-open taker decisions + predominantly passive
opposite-leg rebalancing`.  The probability model behind sizing and price selection remains
unknown.
