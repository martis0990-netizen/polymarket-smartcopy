# Bonereaper pre-open model v4 — zero-bundle checkpoint (2026-08-28)

Status: **VALID NEGATIVE BUNDLE; V4 REMAINS COLLECTING**

## Capture identity

- Capture: `artifacts/bonereaper-preopen-model-capture-20260828-115935`
- Interval: `2026-08-28T11:59:42.960080Z` to
  `2026-08-28T12:19:50.742991Z`
- Root manifest SHA256:
  `c63834c113482f6969d46baa2cc9fa278b23528626d65570657bb0ae67a26bd6`
- Wallet activity SHA256:
  `b2e05c3c495cac47c2df8200e3dcb7273d4176824549dcabfbeb90b34caa9ba0`
- `clean_finalize: true`
- Chainlink events: 424 BTC/USD and 425 ETH/USD
- Chainlink reconnects: 0
- Wallet gap failures: 0
- Prospective wallet rows: 91

An earlier attempted bundle at `20260828-111046` has raw child files but no
root or child manifests. It is an invalid interrupted capture and is excluded
from every count.

## Result

The 91 new Bonereaper rows contained no BTC or ETH 5m/15m trade. Therefore the
frozen v4 population selected zero wallet rows, requested zero transaction
receipts, and produced zero confirmatory conditions. This is not evidence for
or against any v4 candidate. All candidate verdicts remain
`DEFERRED_UNTIL_STOPPING_RULE`.

Unsupported-row distribution:

| Asset | New BUY rows |
|---|---:|
| SOL | 48 |
| BNB | 19 |
| XRP | 12 |
| HYPE | 7 |
| DOGE | 5 |
| **Total** | **91** |

The zero-row receipt artifact is the SHA256 of an empty file:
`e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
The analysis correctly reports `eligible_conditions: 0` and
`study_status: COLLECTING`.

## What this changes

It does not change v4. BTC/ETH remain the frozen v4 population, and the first
eligible ETH 15m condition remains the only v4 observation.

It does justify a separately frozen cross-asset generalization study. In this
window Bonereaper did not merely add a few altcoin fills: all newly observed
activity was outside BTC/ETH. This is consistent with a shared crypto engine
that routes capital across currently active Up/Down markets, but does not prove
the signal formula is shared.

Polymarket's current documentation describes BTC, ETH, SOL, XRP, HYPE, BNB and
DOGE Up/Down TWAP markets, and documents 60-second Chainlink TWAP resolution
for all 5-minute crypto markets after 2026-08-14:

- https://docs.polymarket.com/changelog/predictions
- https://docs.polymarket.com/market-data/chainlink-twap

## Implementation correction

`prospective_receipts` previously treated an unsupported-only wallet artifact
as an error because the selected BTC/ETH evidence was empty. Prospective
capture contracts explicitly allow zero eligible decisions. The loader now
permits an empty selected population only when the caller opts in; all existing
strict callers retain the old fail-closed behavior. A regression test binds
the zero-row manifest and empty receipt artifact.

Research only. No live orders, signing or execution are authorized.
