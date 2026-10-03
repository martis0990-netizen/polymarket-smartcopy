# Limitless technical checkpoint — 2026-10-03 13:58 UTC

Only main artifacts support ongoing-study results. PR smoke is technical evidence only. No live trading, profitability verdict or parameter changes.

## Hourly paper model

Main capture run 37124589299, artifact 11275138151, commit 7cedb6683d6cb035f5a02c941b27ccf37c442947: 12:58:15–13:53:15 UTC, 55 minutes; 699 REST books, 40,483 public stream envelopes, no size-cap stop. Not continuous across jobs.

At 13:30:11.85 UTC BTC decision p(Up)=0.17653866; at 13:30:12.24 ETH p(Up)=0.09974385. Frozen model returned NO_TRADE / NO_EXECUTABLE_EDGE for both. This is a valid result, not grounds to tune the model. Control constant50 selected YES for both; later book requests produced paper fills at 13:30:30 UTC: BTC gross 21.237113 shares, cost 4.119999922 USDC, VWAP 0.194; ETH gross 21.237113 shares, cost 3.290175193 USDC, VWAP 0.1549257280. Each buy deducts 3% contracts, net 20.59999961 shares. These are simulated depth fills, not exchange executions.

Neither current-hour control purchase had an observed settlement in this artifact. Settled trade count zero; reported aggregate zero is not the final PnL of these positions. Previous-hour skipped conditions were later observed resolved and remained skipped. Four conditions seen, two decisions, two earlier missed-window skips; no scored current-hour conditions. INSUFFICIENT_DATA.

## Main discovery / profiles

Run 37127201646, artifact 11274604874, commit c3e70decab3457b80449dbfc1d12e404cd52a291: 52 current candidates, 12 enriched, 48 API requests, zero errors; three deeper profiles, 21 history requests, zero errors. Earliest discovery catalog contains 63 addresses. Returning addresses retain 13:21:22 UTC first discovery rather than the current run time, verifying checkpoint carry. Universe and profile selection are bounded; these counts are not qualified traders.

## Workflow defect and bounded correction

Architect: workflow_run discovery run 37126249589 was skipped on main. The job guard accessed github.event.workflow_run.repository.full_name, but repository is a top-level webhook payload field. Manual/push discovery continued, so this is a chain gap, not complete service failure.

Coder: use github.event.repository.full_name while retaining main-source branch, non-PR event checks, main checkout and separate serialized discovery concurrency. No trading or research thresholds change.

Test Engineer / Reviewer: parse YAML and inspect the real run metadata plus GitHub webhook documentation; verify current PR CI/public collector still succeeds. Acceptance of a future completed-main-capture workflow_run remains to be observed; do not label that live chain verified before it happens. Existing 55-minute collector continues without restart. PASS on field-path correction; next technical review checks trigger continuity.

Sources:
- https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37124589299
- https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37127201646
- https://github.com/martis0990-netizen/polymarket-smartcopy/actions/runs/37126249589
- https://docs.github.com/en/webhooks/webhook-events-and-payloads#workflow_run

Next: preserve the frozen model; audit subsequent settlement/checkpoint artifacts, observe corrected workflow_run acceptance, and review wallet intent before any copyability comparison. The main observer with new decoder was queued behind an existing segment at this checkpoint; PR decoder smoke alone is not main deployment evidence.
