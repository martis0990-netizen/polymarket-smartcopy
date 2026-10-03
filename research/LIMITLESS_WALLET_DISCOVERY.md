# Limitless wallet discovery v1

Architect: measured gap is the fixed three-wallet cohort cannot discover new traders. Add a separate bounded public snapshot collector; do not change that cohort or the hourly paper model. No order endpoints, keys, private profiles, external indexer or database.

Sources: official biggest-position leaderboard in both `position_size` and `pnl` modes (50 position lines each), plus public all-audience trading feed (30 events). Only READY leaderboards produce candidates; other states and request errors remain in evidence. Each candidate preserves source provenance and earliest local observation across successful main artifacts. Source event time is not discovery time.

Enrichment: round-robin across sources, maximum 12 wallets per snapshot, selected BEFORE fetching historical PnL. Up to two 30-event cursor pages and public realized PnL for `1w` and `1m` per wallet. BTC/ETH 15-minute/hourly activity is a descriptive flag, not an execution eligibility gate. Bounded histories are explicitly incomplete when a cursor remains. Unique market conditions and events are reported separately; neither is called an independent intent episode.

Outputs: raw request/response envelopes in `requests.jsonl.gz`, `report.json`, human-readable `report.md`, and earliest observation catalog `state.json` (10,000-address cap). Record request-start and response-observed timestamps, cache headers, failures and source readiness. API PnL is a best-effort projection, not our independently reconstructed ledger. No ROI, portfolio drawdown, profitability gate or copy PnL is invented. Unknown strategy remains UNASSESSED.

Operation: immediate main push, completed main market-capture runs, hourly minute-37 schedule backup and manual dispatch. Main runs serialize; PR smoke is separate and enriches three wallets without restoring main state. Public GET requests only, timeout 8s, response cap 2MiB, spacing 0.4s, 10-minute request budget, 60-second 429 circuit pause (skipped requests, no retries). Stop at 2026-10-10 09:00 UTC; workflow disables itself afterward. No continuous or complete wallet-feed coverage claim.

Coder: standard-library standalone collector, no changes to existing cohorts/models. Test Engineer: deterministic source readiness, address validation, selection provenance, same-transaction distinct fills, PnL unit handling and public-endpoint whitelist tests, plus real GitHub PR smoke. Reviewer: examine real response shape/cursor handling before merge. One required pass; at most two fix cycles; PASS -> STOP.

Next gate: choose a prospective frozen cohort and market family with enough independent intents. Measure event publication delay and follower executable price/depth after discovery, reconcile fees and settlement before any copyability verdict. Never report the selected candidates' historical PnL as a forward result. Current cohort remains untouched.

Primary documentation:
- https://docs.limitless.exchange/api-reference/leaderboard/biggest-positions
- https://docs.limitless.exchange/api-reference/public-portfolio/history
- https://docs.limitless.exchange/api-reference/public-portfolio/realized-pnl

Reuse assessment: MoonDev's market-event scanner suggests an additional discovery source but does not evaluate skill, and txHash-only deduplication can collapse fills. Harrier's examined Limitless wrapper contains venue metadata; its shared copy implementation uses Polygon/Polymarket, while resolution_sniper is a stub. Neither is adopted as a ready Limitless execution engine. PredictMarketCap can provide cross-check candidates but its five-minute scan and buy/sell-only PnL cannot substitute for observed-time execution evidence. Dune/Arkham are optional future corroboration; no exact usable wallet ranking has been verified.
