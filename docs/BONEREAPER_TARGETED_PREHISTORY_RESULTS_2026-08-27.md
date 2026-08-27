# Bonereaper targeted prehistory v1 — results

Status: **PREHISTORY_GAP_CLOSED; LIFECYCLE STUDY COLLECTING 5/30**

Contract commit: `14ff7231b27b2f8e4526ded6c28b2ec4f497f5dd`  
Analyzer commit: `bf8ba207ddf9ac1b0ab30905180c4733f25b5689`  
Manifest SHA256: `f8453e3d565d45f5bb6f83f77cfe6320fa7269a6645a071b41c888cf01a244e1`

## Result

The exact condition-filtered query recovered 19 target BUY rows before the slug epoch.  It retained
all 275 lifecycle-v1 rows with exact normalized identity overlap and no missing rows.

- recovered BUY tokens: 1,501.025539;
- recovered BUY USDC: `$701.514812`;
- previous minimum unexplained inflow: 1,459.025539 tokens;
- extended minimum unexplained inflow: exactly zero;
- verdict: `PREHISTORY_GAP_CLOSED`.

The 19 rows were not spread across the market's preceding day of availability.  They occurred only
in the final 54 seconds before the 5-minute resolution window:

| Market/outcome | Rows | Tokens | BUY USDC | First | Last |
|---|---:|---:|---:|---|---|
| BTC 5m `1787841600` Up | 17 | 1,459.025539 | $677.270402 | 14:39:06 | 14:39:58 |
| ETH 5m `1787841600` Down | 2 | 42.000000 | $24.244410 | 14:39:52 | 14:39:55 |

BTC `Up` later won; ETH `Down` lost.  This is direct evidence of directional pre-positioning before
the window rather than inventory inherited arbitrarily from much earlier trading.

## Fully reconciled public cash

After including prehistory, all ten outcome ledgers have zero or positive post-redemption balances.
The complete five-condition public cash flow is `-$448.628464` before exact fee reconciliation.

| Market | Winner | Total BUY USDC | Redeem USDC | Pre-fee cash flow |
|---|---|---:|---:|---:|
| ETH 5m `1787841600` | Up | $1,067.338983 | $974.454704 | -$92.884279 |
| ETH 15m `1787841900` | Down | $35.817960 | $0.000000 | -$35.817960 |
| BTC 5m `1787841900` | Down | $1,130.844801 | $334.305120 | -$796.539681 |
| BTC 5m `1787841600` | Up | $1,645.792204 | $2,081.018871 | +$435.226667 |
| ETH 5m `1787841900` | Down | $718.881781 | $760.268570 | +$41.386789 |

Two of five conditions were positive and three negative.  The clean two-minute capture represented
2,367.021836 of 9,056.518505 full-history BUY tokens, only `26.14%` by size.

## Mechanism update

The strongest evidence-compatible sequence is now:

1. enter a directional side during the final minute before the crypto window;
2. continue accumulating both outcomes after the window begins;
3. vary the final imbalance rather than enforce a fixed hedge ratio;
4. hold all tokens—winning and losing—without SELL or MERGE;
5. redeem terminal inventory.

Full-history average outcome costs also show why neither “pure direction” nor “always sub-$1 pair”
is sufficient.  The profitable current BTC condition had average `Up + Down` cost around `0.837`
and a winning `Up` residual.  Three two-sided conditions had average pair costs above `$1` (about
`1.065`, `1.151`, and `1.144`), so their complementary legs were not guaranteed arbitrage.

The external signal hypothesis becomes more plausible because large positioning begins before the
Polymarket resolution window.  The evidence does not yet distinguish Binance momentum from the
Chainlink opening anchor; the recovered BTC and ETH choices provide only two additional directional
labels, one correct and one incorrect.

## Evidence artifacts

Directory: `artifacts/bonereaper-prospective-bundle-v5-20260827-01/targeted-prehistory-v1`

- targeted raw activity SHA256:
  `a858d567e2c4d259c7f28d33d0214c78f8c9ccc670cdad49e8ce7f2af5f0a3f5`;
- normalized targeted activity SHA256:
  `1a6989f9465b9ea7e4721038602dd1252ffa4a35395d50da0c3a9a90323d9576`;
- pre-epoch activity SHA256:
  `afc78e4d6d274b1e2e633a69f3de18fd29826d95c15a0f41984156b4b28a1420`;
- outcome ledgers SHA256:
  `131da0a2bb5d76947e176b24bd624cff679c52ebe22c92e7c08a4af8208ea997`;
- condition summaries SHA256:
  `65ce84e0179b52ecd87923f242ad1e7babdd418cd9517b8cfac81406b024decf`;
- prehistory comparison SHA256:
  `f02a7ca594b184a362fd68bd5c7f65a3a27537737001a6b3e9a564ad1ae06ab3`.

## Next discriminating stage

Decode Polygon receipts for all 289 target trades and attribute exact fees, maker/taker role and
transaction ordering across the complete lifecycle.  Then test whether pre-open trades are
systematically taker directional entries and whether later opposite-side buys are predominantly
maker inventory orders.  This separates the two-loop architecture using full-market evidence.
