# Bonereaper lifecycle maker/taker — frozen contract

Status: frozen before retrieving any new Polygon receipts for this stage.

## Question

Does Bonereaper actively establish a directional position before a short-duration
crypto market opens, then passively acquire the complementary outcome after the
open? This is the executable implication of the proposed architecture
`external fair value / conviction -> inventory-aware complementary quoting`.

This stage tests execution roles. It does not claim to identify the fair-value
formula, technical indicator, or order-placement time.

## Immutable source population

- Wallet: `0xeebde7a0e019a63e6b476eb425505b7b3e6eba30`.
- Source:
  `artifacts/bonereaper-prospective-bundle-v5-20260827-01/targeted-prehistory-v1/targeted_activity.jsonl`.
- Source SHA256:
  `1a6989f9465b9ea7e4721038602dd1252ffa4a35395d50da0c3a9a90323d9576`.

The raw targeted API envelope has SHA256 `a858d567...`; it is not the selected
normalized activity file. This distinction was corrected before any receipt was
retrieved for this stage.
- Select every `TRADE` / `BUY` row and exclude the five `REDEEM` rows.
- Expected population: 289 fill rows, 285 unique Polygon transactions, five
  conditions.
- Completeness is all-or-nothing: every one of the 289 rows must bind uniquely
  to a CTF Exchange V2 `OrderFilled` event under the fee-aware decoder.

## Phase labels fixed before receipt retrieval

The market-open second is the integer suffix of the canonical slug. Source event
time strictly before that second is `PRE_OPEN`; time at or after it is
`POST_OPEN`. This produces 41 pre-open rows with $1,637.856132 source notional
and 248 post-open rows.

Four conditions have a single pre-open outcome and therefore a frozen
directional side: BTC 5m `1787841600` Up, BTC 5m `1787841900` Up, ETH 15m
`1787841900` Up, and ETH 5m `1787841600` Down. Their groups are:

- `PRE_OPEN_DIRECTIONAL`: 39 rows, $1,618.067352.
- `POST_OPEN_SAME_SIDE`: 103 rows, $721.121708.
- `POST_OPEN_COMPLEMENT`: 99 rows, $1,540.604888.

ETH 5m `1787841900` has both outcomes before open. Its two pre-open and 46
post-open rows remain in aggregate/per-market reporting but are excluded from
the directional-side test.

## Role binding

Role is determined from the wallet's address in official CTF Exchange V2 fill
events. A taker order is identified by its associated `OrdersMatched` taker
order hash. BUY source notional is matched fee-aware: when the separate event
fee is non-zero, `usdc_size = makerAmountFilled + fee`; fill price remains
`makerAmountFilled / takerAmountFilled`. Multi-level fills in one transaction
are retained as separate source rows and must each have exactly one match.

The primary role is `schema_corrected_role`. The original non-fee-aware contract
role may be retained only as audit metadata.

## Frozen hypotheses and gates

All shares are weighted by source USDC notional, not row count.

1. **Pre-open active conviction.** `PRE_OPEN_DIRECTIONAL` is
   `TAKER_DOMINANT` when taker share is at least 0.80, `MAKER_DOMINANT` when
   maker share is at least 0.80, and `MIXED` otherwise.
2. **Post-open passive complement.** `POST_OPEN_COMPLEMENT` is
   `MAKER_DOMINANT` when maker share is at least 0.80, `TAKER_DOMINANT` when
   taker share is at least 0.80, and `MIXED` otherwise.
3. **Inventory-aware role asymmetry.** Supported only if the complement's maker
   share exceeds the post-open same-side maker share by at least 0.20. Zero-row
   or incomplete groups are `INCONCLUSIVE`.

The joint mechanism `ACTIVE_ENTRY_PASSIVE_COMPLEMENT` is supported only when
hypotheses 1 and 2 both pass their 0.80 gates. Descriptive asymmetry cannot
upgrade a failed joint verdict.

## Secondary outputs

- Role mix by phase, condition, and outcome.
- Event fee totals and fee-aware acquisition cost.
- Redemption cash from the same source artifact and lifecycle cash result by
  condition. Maker liquidity rewards/rebates, gas, funding, transfers, and any
  positions outside the source population remain excluded.

## Interpretation limits

- Maker at fill time proves passive execution, not when the order was placed.
- Taker at fill time proves active crossing, not which market or indicator
  generated the decision.
- Five conditions are a mechanism-identification sample, not a profitability or
  universality sample.
- The JLM-5.3 fair-value/volatility/OFI proposal remains a model to test later;
  this stage can support or reject only its execution-role implication.
