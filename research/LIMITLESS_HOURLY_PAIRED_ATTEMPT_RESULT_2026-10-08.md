# Limitless hourly: delayed second leg after first paired quote

As of 2026-10-08 07:33 UTC (10:33 Moscow). Read-only historical paper replay under [the protocol](LIMITLESS_HOURLY_PAIRED_ATTEMPT_PROTOCOL_2026-10-08.md), committed before this replay. It keeps all 162 prior hourly conditions, the first event-driven entry and the **first** later paired quote fixed. The second paper order waits the saved venue delay, takes only the first subsequent REST book request within 30 seconds, and either buys the entire opposite quantity under the same 3% contract fee, 10 USDC leg budget and positive paired-cost test, or leaves the first leg unchanged. No retries, new market data, maker fills or real orders.

| Measure | Discovery | Previously inspected holdout |
| --- | ---: | ---: |
| First-leg paper fills across all conditions | 65 | 37 |
| First-leg-only settled PnL, USDC | +119.599141550 | −152.665714556 |
| Later qualifying opposite quotes | 42 | 18 |
| Second leg passes first delayed paper attempt | **32** | **14** |
| Second attempt rejected on cost | 9 | 4 |
| No subsequent request within 30 seconds | 1 | 0 |
| Settled PnL of successfully paired subset, USDC | +180.575509301 | +25.510061998 |
| **All first fills with pair-or-fallback policy, USDC** | **+70.273395818** | **−144.175995894** |
| Change from first-leg-only, USDC | **-49.325745732** | **+8.489718662** |

The late pair sometimes locks a small positive payout, but it also sells away upside from first-leg winners. The full policy is **worse in discovery** and only slightly less negative in the already inspected holdout. The 46 successful second paper legs are a subset of the 102 initial paper fills. The 32/14 paired-subset profits cannot be used alone as strategy PnL: the other initial positions and failed second attempts remain in the denominator. Later availability of a pair was not knowable at first entry and cannot serve as an entry-time filter.

The CI job [run 37743942529](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37743942529) completed successfully. It downloaded and SHA256-checked all 96 original ZIPs against the prior immutable manifest, rechecked all 60 first opposite-quote line fingerprints and quoted depth costs, checked the final hourly-v1 state, and recorded first delayed attempts with their source lines. [Machine rows](https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37743942529/artifacts/11534838638) are in artifact 11534838638 (ZIP digest `sha256:ef99e1634703b96c0aa95f9e3469b977a43f5719b797ed0722c8d29fa6779745`, expires 2026-11-07 UTC); [compact summary](evidence/limitless_hourly_paired_attempt_acceptance_2026-10-08.json) persists in the branch. The runner used public archived Limitless/Binance data only, with read permissions and artifact upload.

**Decision:** This specific first-signal-plus-delayed-pair rule does not establish a positive edge. The reused holdout is not independent validation, and book snapshots are still hypothetical execution, without maker queue or shared bankroll accounting. Keep the frozen hourly model and collection controls unchanged. If further research is justified, a prospective two-leg paper ledger needs explicit capital reservation and failed-attempt handling before any trading promotion.
