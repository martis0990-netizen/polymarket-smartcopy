# Bonereaper prospective settlement v1 — results

Status: **COLLECTING (5/30 RESOLVED CONDITIONS)**

Contract commit: `5a1b989ac2a01bb14e63a4c9bca86fb0d73096f1`  
Analyzer commit: `a98f880ade6f8ed3929ac8473435be9cef4f5ec7`  
Economics rows SHA256: `8c848d320e2cc53e931fb408d493166f7ccb784416a56bcc4e8bdfdb745fb32f`

## Result

All five frozen markets were closed with one unambiguous winning outcome.  The complete public
`MERGE,REDEEM` range contained 259 rows: zero merges and 259 redemptions.  Exactly five redemption
rows belonged to the five target conditions, one for every condition.

The frozen hold-to-resolution counterfactual was sharply negative:

- bounded after-fee acquisition cost: `$1,318.542792`;
- bounded terminal value: `$508.151110`;
- bounded terminal edge: `-$810.391682`;
- largest bounded residual aligned with the winner: `2/5` conditions.

This rejects the proposition that the 34 observed BUY fills, taken alone and held unchanged, were
a profitable terminal portfolio.  It does **not** establish the wallet's realized PnL: the public
redemptions prove that its terminal inventory was materially different from the bounded capture.

| Market | Winner | Bounded cost | Bounded terminal | Edge | Largest residual won? | Public redeem USDC |
|---|---|---:|---:|---:|---|---:|
| ETH 5m `1787841600` | Up | $353.278542 | $366.151110 | +$12.872568 | yes | $974.454704 |
| ETH 15m `1787841900` | Down | $35.817960 | $0.000000 | -$35.817960 | no | $0.000000 |
| BTC 5m `1787841900` | Down | $787.577960 | $0.000000 | -$787.577960 | no | $334.305120 |
| BTC 5m `1787841600` | Up | $126.136050 | $111.000000 | -$15.136050 | no | $2,081.018871 |
| ETH 5m `1787841900` | Down | $15.732280 | $31.000000 | +$15.267720 | yes | $760.268570 |

The target redemption rows total 4,222.047265 tokens and `$4,150.047265` USDC.  Four rows redeemed
winning inventory; the ETH 15m row burned 72 losing `Up` tokens for zero USDC.  Its size exactly
matches the 72-unit bounded residual, which is direct evidence that at least this observed position
was held to a losing resolution.  In the other four conditions, redemption quantities are far
larger than the bounded terminal allocation, or even on the opposite outcome.  Therefore missing
pre-capture inventory and post-capture trading dominate any attempt to reconcile the wallet from
this two-minute BUY slice.

## Interpretation

The simple recovered algorithm is now falsified in two ways:

1. Completed observed pairs were not sub-`$1` arbitrage: all 141.670726 paired units cost more than
   `$1` after fees.
2. Holding the observed pairs and residuals unchanged to resolution lost `$810.39` counterfactually.

The remaining plausible mechanism is dynamic inventory control: Bonereaper continues trading after
our capture, changes directional exposure, and redeems the resulting terminal inventory.  The
observed complementary leg behaves more like temporary insurance or inventory management than a
guaranteed pair-arbitrage leg.  Directional mistakes are real—the 72-unit losing ETH 15m redemption
is one concrete example—so the edge, if present, must be measured across complete market lifecycles
and cannot be inferred from isolated winning trades.

## Evidence artifacts

Directory: `artifacts/bonereaper-prospective-bundle-v5-20260827-01/settlement-v1`

- manifest SHA256: `a2abfb00880cbd3ceb20a4b908085d3559008819d2a706620b170339e4ffc29b`;
- Gamma responses SHA256: `d28c1fa9de96766c8828238a1f8f49c9d2cb63a182bb9f76e4c320d20fc9ef24`;
- condition settlements SHA256: `76e1dbae9cd9ef7708cde1976afa6ec13bc9018134483b87c5b91f9c599617b8`;
- all activity SHA256: `591b2dfc5591ce9e41bd69891da60b4070d9c49dcae3e2fd87f6f5b3af1cdc10`;
- target activity SHA256: `0cb6a79f39b873396d8708bc4a8690a2d4a08bef5a3be7374fe1cb8227ea2b3c`.

## Next discriminating stage

Capture complete market lifecycles from before the first fill through resolution, including BUY
and SELL activity, receipts, book state and terminal redemption.  Reconstruct inventory after every
fill and decompose PnL into completed-pair edge, directional residual, fees, maker rebates and
markout.  The frozen stopping target remains 30 resolved independent conditions; no live-order
authorization follows from this result.
