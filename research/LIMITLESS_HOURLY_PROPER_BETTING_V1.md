# Hourly Brier-inspired sizing comparison v1

Freeze: 2026-10-05 UTC, before prospective October 6 windows. Status: standalone offline research; no live orders, keys, market requests or existing strategy/workflow changes. Source hourly module blob `992167fc3410953447f9378ad006741597df2be2`, base main `5b3164c4e5fbd2c17e91ef5d9d65080f44d3a9fa`.

## Scope and precise claim

This is a **gated, capped Brier-inspired size ablation**, not the full proper betting strategy and not a verification of its profitability theorem. Reference: [Gu et al., When Do Prophets Profit](https://www.prophetarena.co/research/when-do-prophets-profit). The theoretical signed exposure is proportional to `2(p-q)`; fixed existing entry gates, hard caps, buy fees, discrete quantities and financing constraints change that strategy. There is no automatic guarantee.

Use the frozen hourly model's actual observation-time `paper_decision` events. Do not reconstruct earlier predictions from later candles/checkpoints. Same model probability, entry eligibility, selected side, limit price, delay and 30s timeout. NO_TRADE remains NO_TRADE. No tuning to retrospective returns.

`q` = midpoint of best YES bid/ask in the exact preceding decision REST envelope, with token/crossing/depth checks and a <=1s receipt match to the saved decision. This is a reference probability, **never** an executable fill. An unknown/missing source is SKIP. If sign(p-q) disagrees with the already selected side, proportional variant skips; this is reported, not silently changed into another entry strategy.

- Fixed account uses the frozen model's `size_cap_shares`.
- Proportional account quantity is `floor_6(min(fixed_size_cap, 2 * 10 shares * abs(p-q)))`.
- The **10-share scale** is predeclared dimensional normalization, not 10% of capital and not optimized. Maximum spend remains 10 USDC per condition; no size/threshold grid.
- Each account starts at **100 USDC**, no borrowing or importing inventory-v1/v2. Debit depth-weighted cost, credit 97% net shares. Cash insufficiency => SKIP, never partial clipping.
- Use the first actually requested book/request-error after delay, received within timeout and before expiry. No favorable retry. The standalone hourly missing-frame retry is deliberately not inherited; this fixed comparator is a funded first-attempt control, not a claim to reproduce all historic hourly fills.
- Resolve only from an observed valid hourly RESOLVED metadata/payout after expiration; pending payout is open cost basis, not zero payoff. Reconcile cash + open cost basis = 100 + settled PnL per account.

Only completed-success main independent capture ZIPs, never PR smoke. Verify ZIP SHA256 against artifact digest; deduplicate condition decisions. Identity/payout conflicts => UNRECONCILED/report=null. Traces/ledgers retain source fingerprints. Cumulative job reports are not summed.

## Run

Manifest JSON: array of `{run,artifact,file:{path}}`, including artifact digest and main run name/status/event. Download the run/artifact IDs in the evidence and recreate local file paths.

```sh
python research/limitless_hourly_proper_betting.py --manifest manifest.json \
  --as-of 2026-10-05T10:12:54Z --out comparison.json
python -m unittest discover -s tests -p 'test_limitless_hourly_proper_betting.py' -v
```

Current retrospective corpus is bounded to 45 successful main segments, starting Oct3 17:34:42 UTC. Earlier conditions and their cash/positions are not imported. This is discovery, not full-week certification. Prospective comparison uses `--start 2026-10-06T00:00:00Z` for fresh 100 USDC accounts and independent reporting; current hourly/inventory holdout, fees and collection remain frozen.

## Interpretation

Report matched conditions, actual settled spend, PnL, return on spent cash, open claims, and first-attempt skips. Smaller absolute losses can simply mean smaller exposure. Midpoint Brier is a model-vs-reference diagnostic, not a net executable advantage. Drawdown uses cash plus open cost basis (settled equity); it is **not marked-to-market drawdown**. REST cache, competing orders, matching and redemption are not simulated. A small sample and one large payout cannot establish stable profit.

Nine focused tests cover sizing units/cap/direction, cash/fee payout and idempotence, first failure, as-of exclusion/open basis, payout conflicts, last-settlement drawdown and invalid token/crossed books. No frozen hourly code edits or threshold sweep.
