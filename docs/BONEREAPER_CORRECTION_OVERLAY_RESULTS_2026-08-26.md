# Bonereaper correction / opposite-leg overlay — 2026-08-26 UTC

Status: **DESCRIPTIVE RESULT UNDER FROZEN CONTRACT**

Contract: `docs/BONEREAPER_CORRECTION_OVERLAY_CONTRACT.md`

The contract was preserved on the remote research branch at commit
`2077f9ec6f5f968ee2b843a35132d5bb255ea33f` before the complete four-market tape was
collected. A small endpoint response had previously been inspected only for schema/connectivity,
as disclosed in the contract.

## Evidence identity and completeness

Wallet evidence:

- wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`
- Stage 3A prospective rows: `77`
- markets: `4`
- source interval: `2026-08-26T12:57:10Z` through `2026-08-26T12:58:49Z`
- wallet input SHA256:
  `e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb`

Independent Polymarket `/trades` tape:

- raw response rows: `5,467`
- normalized rows inside the four canonical market windows: `5,282`
- independent reference rows after excluding Bonereaper: `5,175`
- raw tape bytes: `4,885,499`
- raw tape SHA256:
  `308e78519728c4d43b71427596d4136fdc15c4c9e1ef97e1ec046ac4f2cf8068`
- all four condition paginations ended with a short page; no condition hit the frozen offset cap
- all `77` wallet rows had a strict-earlier independent tape reference for the 5s, 15s, and
  30s measurements

The reference tape maps Up trades to `q=price` and Down trades to `q=1-price`, then computes a
size-weighted Up-equivalent price per second. Bonereaper rows are excluded from that line. Public
trades from the same second as a wallet fill are not allowed to act as pre-fill evidence.

## Frozen primary verdict

`NOT_SUPPORTED`

The primary population contains `29` fills that bought the outcome opposite the strictly prior
cumulative dominant inventory:

- `29 / 77 = 37.6623%` of wallet rows
- `$360.306464 / $550.362903 = 65.4671%` of source notional
- `506.757830 / 1,550.596547 = 32.6815%` of acquired outcome size

For those opposite fills on the frozen 15-second horizon:

- `74.8633%` of source notional was at least `$0.01` below the bought outcome's trailing high;
- notional-weighted median correction depth: `$0.05610`;
- notional-weighted median change from the start of the 15-second window: `+$0.08820`.

The first threshold passed, but the second frozen requirement did not: the bought outcome was
below its recent local high yet still materially above where it began the 15-second window.
Because the contract requires a negative 15-second start-to-fill change, the primary verdict is
`NOT_SUPPORTED`. That verdict must not be rewritten after seeing the result.

## What the overlay actually shows

The result rejects the narrow version of the hypothesis — “Bonereaper buys the opposite outcome
after it has become net cheaper across the whole 15-second window.”

It is nevertheless consistent with a more specific two-step path:

1. Bonereaper accumulates the currently cheap outcome during a strong directional move, creating
   a large token imbalance at relatively low notional.
2. The opposite outcome then rises sharply, pulls back from its local high, and Bonereaper buys
   that pullback, reducing or reversing the prior imbalance.

This distinction explains the apparently conflicting 15-second measurements: the opposite leg
can be `5.61c` below its local peak while remaining `8.82c` above its price at the start of the
window.

The neighboring frozen horizons support the “short pullback” shape descriptively:

| Horizon | Opposite-fill notional at least 1c below trailing high | Weighted median correction depth | Weighted median start-to-fill change |
|---|---:|---:|---:|
| 5s | 62.1338% | 4.6138c | -4.6138c |
| 15s primary | 74.8633% | 5.6098c | +8.8200c |
| 30s | 94.2324% | 9.1976c | -8.5547c |

These horizons were frozen together and are reported without selecting a replacement primary
horizon.

## Market heterogeneity

| Market | Opposite rows | Opposite notional | 15s notional share at least 1c below high | 15s weighted start-to-fill change |
|---|---:|---:|---:|---:|
| BTC 5m | 3 | $133.550350 | 47.7440% | +11.0870c |
| BTC 15m | 11 | $166.564060 | 100.0000% | +8.8200c |
| ETH 5m | 2 | $2.701540 | 100.0000% | -8.0000c |
| ETH 15m | 13 | $57.490514 | 63.8531% | +8.0000c |

The aggregate result is not four independent confirmations. BTC 15m contributes the largest
opposite-fill notional and ETH 5m is economically tiny in this sample.

## Mechanism interpretation

The visual and path accounting materially strengthen the inventory-balancing interpretation:

- the opposite-leg rows are only `37.66%` of row count and `32.68%` of token size, but
  `65.47%` of notional;
- this is the expected shape when the first leg is bought cheaply in larger token quantity and a
  later, more expensive opposite leg is used to form paired inventory;
- the source is not simply choosing one directional side and holding it.

The evidence does **not** yet distinguish an active “detect correction, then submit order” rule
from passive resting bid ladders that are filled automatically when each outcome pulls back. The
many clustered fills and multi-price same-second executions are compatible with passive ladders,
but the public Data API does not expose order placement time or maker/taker role here.

## Next falsifiable experiment

Freeze a new out-of-sample `SURGE_THEN_PULLBACK_OPPOSITE_LEG` contract before collecting another
prospective window. Its event sequence should be:

1. one outcome is the pre-event dominant unmatched inventory;
2. the opposite outcome rises by a pre-specified amount over a pre-specified impulse window;
3. that opposite outcome retraces by a pre-specified amount;
4. Bonereaper buys it only after the retracement begins;
5. the fill reduces prior imbalance and the resulting paired acquisition cost is measured.

Maker/taker or order-lifecycle evidence remains a separate gate. Without it, the next study can
validate the price/inventory sequence but cannot claim that Bonereaper actively reacts to the
correction rather than leaving orders in the book.
