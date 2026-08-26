# Bonereaper maker/taker receipt study — 2026-08-26 UTC

Status: **FROZEN PRIMARY INCONCLUSIVE; COMPLETE SCHEMA-CORRECTED SECONDARY RESULT**

Contract: `docs/BONEREAPER_MAKER_TAKER_CONTRACT.md`

The contract was preserved on the remote research branch at commit
`91cd1a12c75ec6ad1be80086ad871bafbb3be897` before all 77 receipts were collected.
As disclosed there, only one maker-role receipt had been decoded as a schema pilot.

## Evidence identity and completeness

- Polygon chain id: `137`
- wallet input rows / unique transactions: `77 / 77`
- wallet input SHA256:
  `e3a5318d9a54f87c3b044327a38387e853ef5bb3d1fb3d8ea35c70aed27db7fb`
- successful receipts returned: `77 / 77`
- exchange used by all matched wallet events:
  `0xe111180000d2663c0091e4f400237545b87b996b`
- raw receipt artifact bytes: `1,216,756`
- raw receipt artifact SHA256:
  `b5a056432cbc0e2b4c768a087241eb943c059478eddbd1d166c63c025ce0f96c`
- decoded-row SHA256:
  `a26b9ba714708173ba830fd4e621d1524bcf4dafd761818ce4c6fcb27b2bb901`
- summary SHA256:
  `55c140913e334e40cfd60fca45fb274d3a1f2095d69cccc03ac97c2b0a28e421`

Role is decoded from the official Polymarket CTF Exchange V2 event path: the exchange emits
`OrderFilled` for every order and additionally emits `OrdersMatched` with the taker order hash.
An order hash present in `OrdersMatched` is therefore `TAKER`; another filled order is `MAKER`.
See the official
[ITrading event interface](https://github.com/Polymarket/ctf-exchange-v2/blob/main/src/exchange/interfaces/ITrading.sol)
and
[V2 event emission implementation](https://github.com/Polymarket/ctf-exchange-v2/blob/main/src/exchange/mixins/Events.sol).

## Frozen primary result

`INCONCLUSIVE`

The frozen match required `makerAmountFilled / 1e6 == source usdc_size`. It uniquely matched 52
rows, all `MAKER`, but rejected 25 rows. Full collection exposed a schema error in that frozen
rule: all 25 rejected rows were BUY taker events with a non-zero separate V2 `fee` word. For each
one, exactly:

`makerAmountFilled + fee == source usdc_size`

Their base execution price still matched exactly as
`makerAmountFilled / takerAmountFilled == source price`, and their size, token id, wallet,
transaction, exchange, and order hash were unique. The 25 fee values totalled `$7.883820`; every
one of the 52 maker rows had zero event fee.

Because the original frozen condition omitted the fee-inclusive BUY case, its verdict remains
`INCONCLUSIVE`. It is not rewritten after seeing the receipts.

## Complete schema-corrected secondary result

The deterministic repair adds the separate event fee only to the source-cost binding; it does not
change the event role test, population, weights, or frozen `80/20` mechanism thresholds. All 77
rows then bind uniquely.

Result under the original gate: `MIXED_EXECUTION`.

| Weight | Maker | Taker | Maker share | Taker share |
|---|---:|---:|---:|---:|
| Rows | 52 | 25 | 67.5325% | 32.4675% |
| Outcome size | 653.506547 | 897.090000 | 42.1455% | 57.8545% |
| Source notional | $277.450183 | $272.912720 | 50.4122% | 49.5878% |

Row count alone is misleading: many maker fills are small. On the pre-specified primary notional
weight, passive and active execution are almost exactly balanced. The data reject both simple
extremes — Bonereaper is neither an all-passive resting grid nor a strategy that usually crosses
the book after every signal.

## Opposite-leg asymmetry

The stronger result is the difference between fills that buy the outcome opposite the strictly
prior dominant inventory and the remaining fills.

| Population | Rows M/T | Maker notional | Total notional | Maker notional share |
|---|---:|---:|---:|---:|
| Opposite fills | 19 / 10 | $224.909534 | $360.306464 | 62.4217% |
| Non-opposite fills | 33 / 15 | $52.540649 | $190.056439 | 27.6448% |

Thus the opposite leg is materially more passive, although not exclusively so. By contrast,
`72.3552%` of non-opposite notional is taker execution.

This supports a more precise mechanism than the original correction hypothesis:

1. Bonereaper uses mixed execution to establish or add to the currently cheap / existing leg,
   with economically large non-opposite purchases often crossing the book.
2. It more often supplies passive bids while acquiring the balancing opposite leg.
3. Those opposite fills frequently occur after a short pullback from a local high, but the frozen
   15-second test already showed that they are not generally net cheaper across the full window.

The word “often” is important: `37.5783%` of opposite-fill notional was still taker execution.
This is an asymmetric execution policy, not a pure passive ladder.

## Market and outcome heterogeneity

Schema-corrected maker notional shares:

| Market | Maker rows / total | Maker notional share |
|---|---:|---:|
| BTC 5m | 12 / 18 | 51.7184% |
| BTC 15m | 12 / 18 | 60.1169% |
| ETH 5m | 5 / 8 | 29.4873% |
| ETH 15m | 23 / 33 | 36.4923% |

Across outcomes, Up purchases were `65.3123%` maker by notional while Down purchases were only
`23.2680%` maker. This direction asymmetry is sample-specific: the four markets were observed
during one 99-second interval and cannot establish a general Up/Down preference.

All 77 events had zero `builder` and `metadata` values, so those fields do not identify a client
or strategy implementation in this sample.

## Combined strategy inference

Together with the frozen correction overlay, the best current explanation is:

- Bonereaper accumulates both outcomes and actively manages unmatched inventory rather than
  making a single directional bet;
- after a strong move, it often acquires the balancing leg on a short retracement;
- execution is hybrid: aggressive taker orders matter economically, while the balancing
  opposite leg is more maker-heavy;
- therefore “detect correction, then market-buy the opposite side” is too simple, and “leave a
  fully passive symmetric grid” is also too simple.

This has a direct copyability consequence. A follower observing Bonereaper after the fact cannot
reproduce either half reliably: taker prices may be gone before the measured 21.63-second median
observation delay, while maker fills require the follower's limit order to have been resting in
the book before Bonereaper's fill. The on-chain role result is mechanism evidence, not proof of a
profitable follower rule.

## Next falsifiable experiment

The next prospective capture should snapshot executable order-book levels continuously and bind
every Bonereaper fill to the last snapshot observed before its source event. Pre-freeze these
questions:

1. Are maker-heavy opposite fills at stable ladder price levels that existed before the impulse?
2. Do taker fills consume visible liquidity at or below a fixed maximum acquisition cost?
3. Does the resulting paired cost remain below `$1` after current fees and realistic follower
   delay?

That experiment can distinguish a pre-positioned ladder from freshly posted passive orders and
connect the reverse-engineered mechanism to actual copyability. Historical receipts alone cannot
recover off-chain order placement or cancellation time.
