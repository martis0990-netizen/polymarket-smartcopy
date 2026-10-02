# Bonereaper v5 cross-asset capture — operator runbook

Research-only collector. It records the Bonereaper public wallet activity and
seven Chainlink 60-second TWAP symbols concurrently. It never signs or places
an order. The v5 population and exclusions are frozen in
`BONEREAPER_CROSS_ASSET_MODEL_V5_CONTRACT.md`.

## Start one bounded bundle

From the repository root with project dependencies installed:

```bash
python -m smartcopy.cross_asset_capture \
  --output-dir artifacts/bonereaper-v5-YYYYMMDD-HHMMSS \
  --duration-seconds 1200 \
  --code-commit FULL_40_CHARACTER_LOWERCASE_COMMIT_SHA
```

Use a new output directory for every run. Accepted duration is 960–14,400
seconds. Record the exact code commit before starting; never replace a partial
directory or alter a completed bundle. A terminated process leaves child raw
files for diagnosis but must have no root manifest.

The collector subscribes to the unfiltered RTDS 60-second TWAP topic, then
retains exactly BTC, ETH, SOL, XRP, BNB, DOGE and HYPE. Its root manifest
`cross_asset_capture_manifest.json` binds the Chainlink and wallet child
manifests by SHA-256. A clean bundle may contain zero wallet trades, but all
seven oracle symbols must have at least one update. HYPE is recorded for
engineering only; it is not in the confirmatory v5 core.

## Verify before analysis

- Exit code is zero and the root manifest has `clean_finalize: true`.
- All seven `chainlink.event_counts` are positive.
- Recompute the two child-manifest SHA-256 hashes and compare to the root.
- Inspect Chainlink `reconnect_count` and
  `chainlink/chainlink_twap_gaps.jsonl`; an affected lookback is ineligible.
- Inspect wallet `gap_failures`; any observer gap rejects the bundle.
- Preserve `source_timestamp_ms` and `receive_timestamp` separately.
  Observation time is not a substitute for source time.

No v4 analysis command accepts a v5 bundle. The v5 receipts and model-analysis
stages still require their own implementation and verification before a
confirmatory v5 score can be published. For a cloud run, first validate a
complete 960+ second bundle, then add process supervision and durable backup;
the command above alone does not provide automatic restart or off-host backup.
