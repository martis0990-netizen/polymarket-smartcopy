# Hourly Limitless: stop and first holdout postmortem

**Stop at 2026-10-07 08:47:06 UTC.** The user authorized ending collection after the large holdout miss. [Stop action 37596060915](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37596060915) disabled `limitless-market-capture.yml`, `limitless-readonly-probe.yml`, and `limitless-wallet-discovery.yml`; all three are `disabled_manually` in [receipt artifact 11469729047](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37596060915/artifacts/11469729047), ZIP SHA256 `b81d379f1b939c774cfb3244c355622995c45afff804b29e4fc465d1e7827fc0`. Current capture 37594185151 and queued/in-progress observer runs were cancelled. The cancelled capture uploaded only two raw gzip files, **no state, summary, or report**. It is excluded from the main ledger. No state reset, live order, fee or model change occurred. The read-only final audit was left available for reconciliation of preserved archives.

The final complete-success main checkpoint remains [run 37588187303](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37588187303), artifact `11470560416`, ended **08:30:08 UTC**. It contains the immutable hourly and inventory reports described in [the status note](LIMITLESS_HOURLY_STATUS_2026-10-07.md). The existing inventory v2 cash is **6.019112775 USDC**, realized PnL **−93.980887225**, all 27 admitted positions settled. Standalone hourly holdout MODEL has 10 settled, **−74.378700028 USDC**.

## Ten settled MODEL entries

`p` is the frozen model's probability of the purchased side. `market` is the contemporaneous YES-book midpoint expressed for that side; it is a probability reference, never an execution price. All entries include the conservative 3% contract fee in their paper settlement. Amounts are USDC.

| Decision UTC | Asset | Bought | Model p | Market | VWAP | Result | Paper PnL |
| --- | --- | --- | ---: | ---: | ---: | --- | ---: |
| Oct 6 10:30 | BTC | NO | .275 | .225 | .231 | loss | −8.933 |
| Oct 6 10:30 | ETH | NO | .269 | .160 | .185 | loss | −7.309 |
| Oct 6 13:30 | BTC | NO | .881 | .742 | .762 | loss | −9.180 |
| Oct 6 13:30 | ETH | NO | .871 | .780 | .776 | win | +2.366 |
| Oct 6 15:30 | BTC | YES | .144 | .096 | .114 | loss | −8.452 |
| Oct 6 15:30 | ETH | YES | .207 | .170 | .184 | loss | −9.441 |
| Oct 6 19:30 | BTC | NO | .528 | .442 | .405 | loss | −8.149 |
| Oct 6 23:30 | BTC | NO | .806 | .715 | .739 | loss | −9.740 |
| Oct 7 03:30 | BTC | NO | .391 | .255 | .241 | loss | −6.549 |
| Oct 7 03:30 | ETH | YES | .413 | .316 | .349 | loss | −8.992 |

These 10 trades occupy **six UTC hour clusters**. In every chosen trade the model valued the purchased side above the book midpoint, by **8.84 percentage points on average**. It forecast about **4.785 wins** across these bets; only one won. Its own entry probabilities implied **+16.792460010 USDC** expected paper PnL, versus **−74.378700028 USDC** realized. This descriptive expectation is not a confidence interval: BTC/ETH within an hour and market regimes are dependent, and the sample was selected by the algorithm itself.

Across **56 already scored holdout conditions**, including NO_TRADE, model Brier is **0.17520**, compared with **0.15792** for the decision-book midpoint. Lower is better; on this sample the market reference was better calibrated. This does not imply that the midpoint can be bought or sold at that price. Paper execution itself assumes visible REST depth available at receipt; real fills could be worse.

At decision time six losing bets bought the side **opposite the current hour-open/reference move** and that move persisted to settlement. Three losing bets followed the then-current move, which reversed before hour close. The one winner followed the current move. This is a descriptive partition of these 10 outcomes, not a proven regime filter. All **10/10** Limitless payouts agree with independently captured closed Binance 1h open/close direction; the observed miss is not explained by an outcome-decoder or Binance hourly settlement mismatch in these trades. Frozen model probabilities were independently recomputed from decision-time raw Binance 1m during the 36-archive replay.

## Next analysis gate

Do not reset capital, tune a threshold, credit maker-cross snapshots as fills, or reuse these six hours as a fresh test. Review the probability model and selection rule against the book on the remaining observed decisions, and evaluate any proposed new version only on a later independent data window. Current evidence supports stopping the losing paper collection; it does not identify a profitable replacement.

[Machine evidence](evidence/limitless_hourly_loss_postmortem_2026-10-07.json) contains exact input probabilities, prices, entry economics, payout, Binance close checks, and source fingerprints for each trade.
