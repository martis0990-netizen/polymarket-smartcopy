# Bonereaper v5: no-card GitHub Actions pilot

This pilot uses the existing **public** GitHub repository's standard hosted
runner. It creates no AWS account and needs no payment method. It runs the
read-only collector for 1,200 seconds and stores a compressed immutable
capture bundle as a seven-day GitHub Actions artifact. It does not sign or
place orders. No run has been performed until the three CLOB credentials are
installed and the owner manually starts the workflow.

## Before the run

1. Review and merge `.github/workflows/bonereaper_v5_cardless_pilot.yml` into
   the repository's default `main` branch. GitHub's manual `workflow_dispatch`
   button only appears when the workflow exists on the default branch. The
   job checks out the selected commit and binds it as `code_commit`.
2. Obtain the three CLOB API values by signing on your own device using
   https://docs.polymarket.com/getting-started/api . Do not upload or share a
   private wallet key. These API credentials can authorize more than a market
   data connection, so use a separate research account if possible and grant
   GitHub write access only to trusted collaborators.
3. In the GitHub repository open **Settings → Secrets and variables → Actions →
   New repository secret** and create exactly these three secrets:
   `POLYMARKET_CLOB_API_KEY`, `POLYMARKET_CLOB_API_SECRET`,
   `POLYMARKET_CLOB_API_PASSPHRASE`. Never put values in workflow inputs, commits,
   issues or chat. This pilot does not require Polygon RPC until later offline
   receipt decoding.
4. From **Actions → Bonereaper v5 cardless pilot → Run workflow**, select the
   reviewed `main` version and start one run. This workflow has no automatic
   schedule. Check the archive step even if capture fails.

## Validate the result

Download the artifact named `bonereaper-v5-RUN_ID-ATTEMPT` promptly. Keep an
off-GitHub copy; GitHub deletes this artifact after seven days. Verify the
archive and root manifest SHA-256 against the two lines in the run summary,
then unpack to a new directory. A clean result contains
`cross_asset_capture_manifest.json` with `clean_finalize: true`, all seven
positive live TWAP counts and no child gaps. A failure archive with no root
manifest is diagnostic only and must never enter v5 scoring.

Only after a clean pilot, pass the root SHA-256 into
`BONEREAPER_CROSS_ASSET_CAPTURE_V5_RUNBOOK.md` for intake and fee-aware receipts.
The Polygon RPC can be a public mainnet endpoint for initial decoding.

## Limits

Standard hosted runners in a public repository are currently free, including
when the owner has no payment method, but artifact storage is limited (GitHub
Free includes 500 MB). One hosted job has a six-hour maximum; this pilot caps
itself at 35 minutes. Neither runner availability nor outbound access to
Polymarket from the runner has yet been validated. GitHub scheduled workflows
may be delayed or skipped, so this pilot cannot establish a continuous
seven-day capture. Bundle-level v5 eligibility still requires an uninterrupted
stream, wallet baseline and 660-second warm-up. We will only design repeated
bounded jobs and artifact monitoring after the first real bundle passes.

Official limits: https://docs.github.com/en/actions/reference/limits
Official billing: https://docs.github.com/en/billing/concepts/product-billing/github-actions
Official secrets: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
Manual trigger: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch
