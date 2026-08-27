# Bonereaper lifecycle maker/taker — results

Status: **COMPLETE FOR THE FROZEN FIVE-CONDITION POPULATION**

## Result

All 289 BUY rows in the targeted lifecycle artifact were bound to 285 Polygon
receipts and exactly one fee-aware CTF Exchange V2 fill. There are zero
ambiguous rows.

The strongest identified mechanism is an aggressive pre-open directional
entry. The simpler proposed continuation — passively acquire the complementary
outcome after open — is not supported by notional-weighted execution roles.

| Frozen group | Rows | Notional | Maker share | Taker share | Verdict |
|---|---:|---:|---:|---:|---|
| Pre-open directional | 39 | $1,618.067352 | 0.62% | **99.38%** | `TAKER_DOMINANT` |
| Post-open complement | 99 | $1,540.604888 | 26.80% | **73.20%** | `MIXED` |
| Post-open same side | 103 | $721.121708 | **62.58%** | 37.42% | descriptive |
| No unique pre-open side | 48 | $718.881781 | 54.99% | 45.01% | excluded from directional test |
| All fills | 289 | $4,598.675729 | 27.61% | **72.39%** | descriptive |

The frozen joint hypothesis `ACTIVE_ENTRY_PASSIVE_COMPLEMENT` is
`NOT_SUPPORTED`: its first leg passes strongly, while the complement is not
80% maker. The frozen inventory-role asymmetry also fails. Complement maker
share is 35.79 percentage points *lower* than same-side maker share, rather
than at least 20 points higher.

## Why row counts tell a different story

The complement has 78/99 maker rows (78.79%), but maker rows carry only 26.80%
of its dollars. Bonereaper therefore has many small passive fills and a small
number of large active fills. The largest complement taker BUYs include:

| Market | Time | Side | Size | Fee-aware cost |
|---|---|---|---:|---:|
| ETH 5m `1787841600` | 14:44:04 | Up | 258.00 | $245.957850 |
| BTC 5m `1787841600` | 14:40:55 | Down | 271.00 | $181.715140 |
| BTC 5m `1787841600` | 14:41:13 | Down | 241.00 | $106.437660 |
| BTC 5m `1787841600` | 14:42:03 | Down | 257.00 | $94.376760 |
| BTC 5m `1787841600` | 14:42:09 | Down | 320.00 | $81.756180 |

This rejects a single passive-ladder explanation. A better reconstruction is
two simultaneous post-open contours: small passive quotes plus selected large
aggressive sweeps when a price/inventory condition is met.

## Timing

All 41 pre-open rows occurred within the final 60 seconds before market start.
They carried $1,637.856132 and were 99.38% taker by notional. Post-open taker
activity persists throughout the market rather than appearing only at the
opening boundary:

| Relative interval | Rows | Notional | Maker | Taker |
|---|---:|---:|---:|---:|
| 0–30 s | 49 | $498.882883 | $165.062483 | $333.820400 |
| 31–60 s | 37 | $473.912515 | $142.852175 | $331.060340 |
| 61–120 s | 69 | $511.598412 | $218.560692 | $293.037720 |
| >120 s | 93 | $1,476.425787 | $733.003957 | $743.421830 |

## Fees and observed cash

Decoded event fees total $100.926880. The fee-aware source purchase cost is
$4,598.675729 and the five public redemption rows total $4,150.047265, leaving
the previously reconciled public cash result of **-$448.628464**.

This is not total strategy PnL. Maker rewards/rebates, gas, transfers, funding,
and positions outside the selected public activity remain excluded. The result
does show that liquidity rewards or unobserved economics are material if this
population was profitable overall.

## Updated review of the JLM-5.3 proposal

The proposal was useful as a modular hypothesis, but only part of its claimed
Bonereaper reconstruction survives this stage:

- **Supported:** separate active-taking and passive-quoting contours; an
  external signal is expressed as a highly aggressive pre-open directional
  position.
- **Still plausible, not identified:** Chainlink-anchored fair value with a
  Binance lead, short-horizon volatility, and a bounded order-flow overlay.
- **Rejected as a universal mechanism:** “directional taker entry followed by
  predominantly passive complementary acquisition.” Large complementary BUYs
  are mostly taker by dollars in this population.
- **Not reconstructed:** Gaussian/HAR formula, `0.4/0.4/0.2` weights, quote
  width, inventory coefficient, Supertrend, RSI, EMA, or structure-break
  parameters.

The current narrow reconstruction is:

`external crypto state -> aggressive next-window pre-positioning -> mixed
small-maker / large-taker execution on both legs -> settlement/reward economics`.

## What this says about higher-timeframe trend or structure break

The result makes an external technical state more plausible than a rule based
only on the new Polymarket contract: the bot takes almost all pre-open exposure
as taker before the contract's resolution window starts, and earlier pilots
aligned the first pre-open taker side with strict-prior Binance 15-second
momentum in 5/6 discovery conditions. It still does not distinguish:

1. short momentum;
2. a 1m/5m Supertrend regime;
3. an objective higher-timeframe break of structure;
4. a forecast of the forming Chainlink opening TWAP;
5. a calibrated binary fair-value model using price, strike, time, and
   volatility.

Supertrend, RSI, EMA, and short momentum often produce the same sign during a
clean move. Exact identification therefore requires new out-of-sample
conditions where these signals disagree, with definitions and parameters
frozen before observing Bonereaper's choice.

## Next discriminating stage

Collect at least 30 new eligible pre-open conditions with simultaneous Binance
trade flow, Chainlink updates, Polymarket book, and receipts. Before collection,
freeze four competitors: 15-second momentum; 1m/5m Supertrend regime; an
objective swing-break rule; and an oracle-relative fair-value score. Evaluate
only strict-prior data and use disagreement conditions as the primary sample.
Compare direction, taker size, Brier/log loss where a probability is available,
and post-fill markout. This can identify incremental information; another
in-sample overlay cannot.

## Artifacts

- Contract: `docs/BONEREAPER_LIFECYCLE_MAKER_TAKER_CONTRACT.md`
- Summary:
  `artifacts/bonereaper-prospective-bundle-v5-20260827-01/lifecycle-maker-taker-v1/lifecycle_maker_taker_summary.json`
- Decoded rows:
  `artifacts/bonereaper-prospective-bundle-v5-20260827-01/lifecycle-maker-taker-v1/lifecycle_maker_taker_rows.jsonl`
- Immutable receipts:
  `artifacts/bonereaper-prospective-bundle-v5-20260827-01/lifecycle-maker-taker-v1/receipt_responses_raw.jsonl`
- Manifest:
  `artifacts/bonereaper-prospective-bundle-v5-20260827-01/lifecycle-maker-taker-v1/lifecycle_maker_taker_manifest.json`
