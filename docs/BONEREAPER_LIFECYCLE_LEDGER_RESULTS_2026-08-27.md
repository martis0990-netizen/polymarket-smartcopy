# Bonereaper lifecycle ledger v1 — results

Status: **COLLECTING (5/30 RESOLVED CONDITIONS)**

Contract commit: `cced633d551aa294cc458083009cb238b2e0a5a6`  
Analyzer commit: `5617ed79f7745ff7758f6d400409cd9c82412ed3`  
Manifest SHA256: `62f5c702c146b4f010c353f6c89e1b1a5fcafe8acb49dd9330a13aef520507b0`

## Main result

The complete frozen range contained 9,951 wallet activity rows.  Exactly 275 belonged to the five
target conditions: 270 `TRADE` rows and five outcome-specific `REDEEM` rows.  Every target trade
was a `BUY`.  There were zero target `SELL`, `SPLIT` or `MERGE` rows.

This changes the recovered mechanism materially.  In these markets Bonereaper did not close risk
through the order book.  It accumulated outcome tokens—usually on both sides—and later redeemed
the winning inventory (plus one explicit losing redemption).  The clean two-minute capture saw
2,367.021836 of 7,555.492966 lifecycle BUY tokens, a size-weighted share of only `31.33%`.

## Condition accounting

| Market | Winner | BUY USDC | Redeem USDC | Public pre-fee cash flow | Flow status |
|---|---|---:|---:|---:|---|
| ETH 5m `1787841600` | Up | $1,043.094573 | $974.454704 | -$68.639869 | complete |
| ETH 15m `1787841900` | Down | $35.817960 | $0.000000 | -$35.817960 | complete |
| BTC 5m `1787841900` | Down | $1,130.844801 | $334.305120 | -$796.539681 | complete |
| BTC 5m `1787841600` | Up | $968.521802 | $2,081.018871 | +$1,112.497069 | incomplete prehistory |
| ETH 5m `1787841900` | Down | $718.881781 | $760.268570 | +$41.386789 | complete |

Four conditions have no negative post-redemption token balance.  Their combined public Data API
cash flow is `-$859.610721` before exact receipt-fee reconciliation; only one of the four is
positive.  Losing token balances remain positive and worthless after resolution, which is expected
when only winning tokens are redeemed.

The current BTC 5m condition is not cash-reconcilable from the slug epoch.  It reports 621.993332
in-window `Up` BUY tokens but burns 2,081.018871 winning `Up` tokens.  At least 1,459.025539 tokens
came from earlier activity or another unobserved inflow.  Gamma metadata shows that this market was
created and became tradeable on 2026-08-26, about one day before its 2026-08-27 resolution epoch.
Therefore its apparent `+$1,112.50` is not evidence of profit; acquisition cost is missing.

## What this says about the algorithm

The five-condition evidence supports an accumulative two-sided inventory process:

1. buy outcome tokens repeatedly rather than trade in and out;
2. vary the imbalance between sides, sometimes strongly;
3. retain losing inventory through resolution;
4. redeem terminal tokens instead of using order-book SELL or pair MERGE.

This is incompatible with a simple copy-and-hold signal and with deterministic sub-`$1` pair
arbitrage.  It is closer to repeated probability/value quoting expressed entirely through BUYs:
the second side may reduce directional risk, but it does not guarantee a profitable pair.  Large
directional errors occur—the following BTC 5m lifecycle lost about `$796.54` before exact fee
reconciliation.

The sample remains too small and outcome-selected to conclude that Bonereaper is unprofitable
overall.  Portfolio-level rewards, rebates and other markets may compensate for these losses, and
the current BTC condition still lacks its pre-epoch acquisitions.

## Evidence artifacts

Directory: `artifacts/bonereaper-prospective-bundle-v5-20260827-01/lifecycle-v1`

- all requested activity: 9,951 rows, SHA256
  `ec94e4438446b920579d15bb2e7356f40042f7a8bee843500f6f9fff390ab115`;
- target activity: 275 rows, SHA256
  `97887d7905a03967fe574d6e4ee8b2af34bf1d0d03c133ba9a559834bb9891c2`;
- outcome ledgers SHA256
  `5e69e74eb1165f07139976ab06e56d09cb8cc5aacc2ddeebef1af795af5ff6d4`;
- condition summaries SHA256
  `f893db734676af5ad6e9cb2867962d62071e60a18c0202201050e91c271839f0`;
- capture comparison SHA256
  `789e57f54823a4282130f8c5c4d68b75a5e3f28017b8e63c9b80e9074f469f12`.

## Next discriminating stage

Extend the five-condition activity start to the earliest Gamma `createdAt/startDate`, using the
official condition-ID filter so completeness is practical.  Reconcile the missing 1,459.025539 BTC
`Up` tokens, then decode every target TRADE receipt to place Data API cash on an exact fee basis.
Only after that should rewards/rebates be added as a separate portfolio-level component.
