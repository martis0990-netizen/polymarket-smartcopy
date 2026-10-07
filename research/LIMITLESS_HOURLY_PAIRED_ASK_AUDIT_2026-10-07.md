# Limitless hourly: simultaneous YES+NO taker depth audit

**Result: no simultaneous same-book pair.** This is a read-only diagnostic on 96 digest-verified completed main capture ZIPs from 3 October 12:58 UTC through 7 October 08:30 UTC. The segments have a known gap on 5 October; the result applies to observed books only. PR smoke and cancelled runs are excluded. The final [main capture 37588187303](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37588187303), artifact `11470560416`, ZIP SHA256 `73c77d52bd73f82ff3c07f354172a6a406dacbcb96d5abc2ba30b4e3844a741b`, supplies 180 eligible hourly BTC/ETH CLOB market specifications, YES token IDs and active time windows. [Machine evidence](evidence/limitless_hourly_paired_ask_audit_2026-10-07.json) records all ZIP IDs/digests, counts and the raw line proof of the minimum.

| Check | Observed |
| --- | ---: |
| Hourly market specifications | 180 |
| Book attempts in market window | 33,550 |
| Valid YES-token book envelopes | 33,439 |
| Both sides present | 33,365 |
| One side missing | 74 |
| Request errors | 111 |
| Lowest YES ask + derived NO ask | **1.001** |
| Median YES ask + derived NO ask | **1.046** |
| Sums below 1, before any fees | **0** |
| Positive simultaneous pair after conservative 3% buy fee | **0** |

For this captured endpoint, `YES ask` is the least YES ask and `NO ask = 1 − greatest YES bid` in the same YES-token orderbook. Thus `YES ask + NO ask = 1 + (YES ask − YES bid)`. An uncrossed book cannot offer the two contracts below their combined $1 payout. The smallest observed sum was 1.001 in ETH condition `0x4971ba885a5ec4ad2b552f9238c15b6df0e44c4aeee9bebea65ce122ffe122a0`, artifact `11275138151`, capture line `29464` (SHA256 `a1e474530aa66bc2d07c64f972ef3b4501b97a7418d4a216411590a0bb1f8670`). The [official CLOB description](https://docs.limitless.exchange/api-reference/markets/browse-active) describes independent YES/NO quotes, and the [fee guide](https://docs.limitless.exchange/user-guide/fees) gives taker buy fees up to 3%, paid in outcome tokens. The existing frozen paper convention of a flat conservative 3% was used for depth accounting; fee-free buying also finds zero same-book pairs below $1.

The hypothetical paired-depth calculation matches equal gross YES and NO shares, with total cost capped at 10 USDC. At a 3% contract fee, equal gross shares `n` would yield only `0.97n` on resolution, so a positive pre-network surplus requires `YES ask + NO ask < 0.97` at the consumed depths. None of the 33,365 complete books reaches even `<1` at the top. No first-followup or second-leg fill claim is made because there was no eligible first quote.

**Decision:** Do not implement an instantaneous taker YES+NO arbitrage bot for these books. A sequential strategy that buys the sides at different times or a maker strategy is a different hypothesis with inventory, adverse selection and queue risk. Previous public-tape diagnostic found zero confirmed hypothetical maker fills; this audit does not establish returns for either alternative. The stopped hourly collection and all existing models, fees, holdout, schedules and orders remain unchanged.
