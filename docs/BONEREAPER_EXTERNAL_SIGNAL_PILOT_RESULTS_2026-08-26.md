# Bonereaper external-signal pilot results — 2026-08-26

Status: **DESCRIPTIVE PILOT — HYPOTHESIS GENERATION ONLY**

## Integrity boundary

The recovered result artifact references two pre-result commits that are absent from the repository
object database. The immutable inputs and complete output remain hash-bound, and the implementation
is deterministic, but the missing Git boundary prevents this run from satisfying an evidence gate.
The result is retained to choose the next prospective hypotheses, not to select trading parameters.

## Population

- `77` live-observed Bonereaper fills from four overlapping BTC/ETH 5m/15m contracts
- `49` condition/outcome/source-second episodes
- `18` schema-corrected taker episodes, `25` maker episodes, `6` mixed-role episodes
- one `99`-second live interval; episodes are not independent markets
- Binance spot is a declared historical proxy because Chainlink TWAP has no replay

## Corrected primary result

The August 26 markets all require a 60-second opening TWAP under the August 14 Polymarket rule.
After recomputing the two 5-minute barriers without changing the frozen thresholds:

| Candidate | Aligned episodes | Episode share | Aligned notional | Notional share | Verdict |
|---|---:|---:|---:|---:|---|
| Binance-proxy opening-TWAP side | 9 / 18 | 50.00% | $127.93429 / $195.03102 | 65.60% | `NOT_SUPPORTED` |

The simple explanation "Bonereaper actively buys whichever outcome is currently above the opening
barrier" is not supported by this pilot.

## Candidate signal results

| Candidate | Episode share | Notional share | Interpretation |
|---|---:|---:|---|
| 15s momentum | 72.22% | 82.59% | strongest cross-asset descriptive candidate |
| 1s RSI(14) side of 50 | 72.22% | 82.59% | identical decisions to 15s momentum in this sample |
| BTC 15s lead on ETH episodes | 72.73% | 80.21% | useful lead-lag candidate, ETH only |
| 1m EMA(5/20) | 66.67% | 74.22% | weaker and asset-dependent |
| 1m RSI(14) side of 50 | 66.67% | 74.22% | identical decisions to 1m EMA in this sample |
| 15s aggressive flow | 50.00% | 68.11% | not convincing |

On the eight taker episodes where opening-barrier direction and 15-second momentum disagreed,
momentum aligned on `6 / 8` episodes and `74.71%` of notional, while the barrier aligned on `2 / 8`
and `25.29%` of notional.

## Interpretation

The pilot supports carrying short external momentum and BTC-to-ETH lead into a new prospective
contract. It does not identify RSI, EMA, or a proprietary technical indicator: in this short sample
those transforms collapse to the same trend sign. The result also cannot distinguish a directional
fair-value engine from inventory-driven taker rebalancing.

## Next admissible study

Freeze before collection and evaluate independent market windows across multiple days. Capture the
official 60-second Chainlink TWAP prospectively, Binance spot/perpetual trades, Polymarket public
book state, and Bonereaper fills. Pre-register market-level evaluation so repeated fills within one
contract cannot inflate evidence.
