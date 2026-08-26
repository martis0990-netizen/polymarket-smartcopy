# Bonereaper asset-level accounting consistency — frozen contract

Status: FROZEN BEFORE RESIDUAL ATTRIBUTION

Inputs: frozen 2026-08-25 UTC target-family activity evidence and same-day bounded closed-position evidence.

## Purpose

Test whether Data API activity BUY accounting and closed-position accounting refer to sufficiently consistent per-asset quantities to support a later matched-vs-residual PnL allocation.

This stage performs NO profit-source attribution.

## Exact join

Join by exact `(condition_id, asset)` only, restricted to BTC/ETH explicit 5m/15m Up/Down markets present in both frozen evidence sets.

For each joined asset:

- activity buy size = sum activity `size`;
- activity buy notional = sum activity `usdc_size`;
- activity VWAP = activity buy notional / activity buy size;
- closed total bought = closed-position `total_bought` (sum if duplicate rows share the same condition+asset);
- closed avg price = total-bought-weighted closed `avg_price` if duplicates exist;
- size error = closed total bought - activity buy size;
- absolute size error;
- relative size error = absolute size error / max(activity buy size, closed total bought), when denominator >0;
- price error = closed avg price - activity VWAP;
- absolute price error.

## Frozen aggregate outputs

Report:
- activity asset count, closed asset count, joined asset count, activity-only and closed-only counts;
- duplicate closed `(condition_id, asset)` key count;
- median/p90/p99 absolute relative size error;
- median/p90/p99 absolute price error;
- share with relative size error <=1e-6, <=1e-4, <=1e-2;
- share with absolute price error <=1e-6, <=1e-4, <=1e-2;
- same descriptive errors by BTC/ETH × 5m/15m.

These tolerances are diagnostics only and are frozen before seeing the results. They do not authorize dropping rows.

## Hard prohibitions

- do not force activity size to equal `total_bought`;
- do not infer settlement winner from `realized_pnl` in this stage;
- do not allocate PnL to matched vs residual inventory in this stage;
- do not remove mismatches after seeing results;
- no copyability or live-latency conclusions.

A later allocation contract is permitted only if this consistency check shows that the accounting fields are interpretable with disclosed mismatch behavior.
