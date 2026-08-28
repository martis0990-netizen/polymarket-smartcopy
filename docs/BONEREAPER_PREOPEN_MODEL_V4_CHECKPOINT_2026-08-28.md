# Bonereaper pre-open model competition v4 — checkpoint 2026-08-28

Status: **COLLECTING — 1 / 30 CONFIRMATORY CONDITIONS**

## What was added

- Frozen four-candidate contract before new observations:
  `MOM15`, `SUPERTREND_HTF_10_3`, `BOS_HTF_2`, and `ORACLE_FV`.
- Strict-prior implementations with same-second exclusion and fully closed HTF
  candles.
- Pairwise disagreement accounting, Wilson intervals, and stopping-rule gates.
- Long prospective Chainlink + wallet capture with SHA-bound child manifests.
- Fee-aware Polygon receipt binding and a bundle analyzer that physically
  excludes pre-contract and insufficient-warm-up rows from the v4 count.

## Boundary correction before eligible data

The original capture contract allowed a 900-second minimum. A live engineering
run starting at 08:19:30 UTC showed that this does not guarantee a market
boundary after the 660-second warm-up: 08:30 was too early and 08:35 occurred
after the 08:34:31 end. The minimum was corrected to 960 seconds before any
confirmatory-eligible condition was observed.

The excluded 900-second smoke cleanly finalized with 862 BTC and 862 ETH
Chainlink events, 526 prospective wallet rows, zero reconnects, and zero wallet
gap failures. It never entered a model gate.

## First confirmatory capture

| Field | Value |
|---|---|
| Capture interval | 08:29:41–08:49:42 UTC |
| Duration | 1,200 seconds |
| Chainlink events | 943 BTC + 943 ETH |
| Chainlink reconnects | 0 |
| Prospective wallet rows | 901 |
| Wallet gap failures | 0 |
| Supported BTC/ETH 5m/15m rows | 629 |
| Unique Polygon receipts | 596 |
| Fee-aware unique matches | 629 / 629 |
| Confirmatory conditions | 1 |

Capture manifest SHA256:
`b256b75c12f1061d326a2c9a06f4b01273fa7d9333fb3c4b4bd343b73e834e9d`.

Receipt rows SHA256:
`96c90247113f66b708c81a950f05c834553606a8c49455f35bae9a15688b4ff2`.

## First independent condition

Market: ETH 15m `eth-updown-15m-1787906700`.

The earliest unambiguous pre-open taker episode occurred at 08:44:45 UTC,
15 seconds before nominal start. Bonereaper bought Down for $6.089910.

| Candidate | Direction | Detail | Aligned with wallet |
|---|---|---|---|
| `MOM15` | Down | log return `-0.0000921949` | Yes |
| `SUPERTREND_HTF_10_3` | Down | final closed 15m regime | Yes |
| `BOS_HTF_2` | Up | persistent last confirmed structure break | **No** |
| `ORACLE_FV` | Down | `p_up=0.458733`, `z=-0.103627` | Yes |

Oracle diagnostics:

- basis-corrected Binance spot: `2494.926720`;
- last strict-pre Chainlink anchor: `2495.132020`;
- median log basis: `-0.0001309623`;
- realized per-second sigma: `0.00002624996`.

This row is a useful disagreement: the frozen BOS proxy points Up while the
wallet, momentum, Supertrend, and oracle-relative level point Down. It weakens
BOS as a sufficient standalone explanation for this decision. It does not yet
identify which of the other three Bonereaper uses because they are
observationally equivalent on this row.

## Interim interpretation

No candidate receives a final verdict at 1/30. All candidate verdicts are
`DEFERRED_UNTIL_STOPPING_RULE`; the pairwise comparisons are underpowered.

Combined with the completed lifecycle receipt study, the best current narrow
reconstruction is:

`strict-prior external crypto state -> aggressive pre-open directional taker ->
mixed small-maker and large-taker post-open inventory execution`.

The exact external state remains unresolved. More conditions where momentum,
Supertrend, BOS, and oracle fair value disagree are required.

## Immutable artifacts

- Corrected model output:
  `artifacts/bonereaper-preopen-model-capture-20260828-082935/preopen-model-v4-r2`
- Raw capture:
  `artifacts/bonereaper-preopen-model-capture-20260828-082935`
- Model rows SHA256:
  `bdacd22a533ee92010d5257074ade60983f454b498b42439630a460747c65d20`
- Summary SHA256:
  `a0ff155f9d36afcaa9027fc72ffe99283d7d96ea1b18bcefaa6e234181265d88`

Raw captures and receipts remain ignored by Git due to artifact size; code,
contracts, tests, hashes, and this checkpoint are versioned.
