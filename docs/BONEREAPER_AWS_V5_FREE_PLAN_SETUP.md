# AWS Free Plan setup for prospective v5 capture

Status: deployment specification only. No AWS account or cloud resources were
created by this document. No trading or wallet signing is authorized.

## Account boundary

At https://aws.amazon.com/free/ a *new* eligible AWS customer can select the
Free account plan: $100 credit at signup, up to $100 more for eligible learning
activities, at most six months or until credits are exhausted. Verify the
actual balance in Billing after signup. The Free plan closes at its deadline;
copy capture bundles off the instance before then. Do not upgrade to Paid for
this research without a separate decision.

The owner must personally complete signup at
https://signin.aws.amazon.com/signup: email, password, contact details,
payment method, verification, plan choice and terms. Do not put these values
in this repository or send them to an assistant. Enable root MFA after signup.

## First infrastructure configuration (review in AWS Console before launch)

| Setting | Proposed value | Reason |
| --- | --- | --- |
| Region | `eu-west-1` (Ireland) | Working default; check actual availability and price in console |
| Plan | **Free**, never Paid by default | Prevent out-of-credit spending |
| EC2 image | Current Ubuntu LTS, x86_64, marked Free Tier eligible | Match Python 3.11+ |
| EC2 type | `t3.small`, only if console marks eligible | 2 GiB memory, one collector |
| CPU mode | Standard/limited, if offered | Avoid unexpected unlimited CPU credits |
| Root volume | 25 GiB gp3, delete on termination | Bounded scratch for raw captures |
| Inbound network | SSH 22 only from owner's current IP; no other inbound rules | Data capture needs outbound HTTPS/WSS |
| Budget | Monthly $1 actual + forecast email alerts to owner | Early signal; not a hard cap |
| Lifetime | Initial 20-minute clean bundle, then a separately scheduled research window | Validate transport before repeated capture |

AWS lists `t3.small` and gp3 as Free Tier eligible for accounts created on or
after 2025-07-15, but charges consume credits; the Free plan ends when the
credits or six months expire. See
https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-free-tier-usage.html .
AWS Budgets alerts can lag actual usage; monitor credit balance directly. See
https://docs.aws.amazon.com/cost-management/latest/userguide/budgets-managing-costs.html .

## Order of setup

1. Owner creates Free account, confirms the $100 credit and enables root MFA.
2. Owner creates a $1 monthly cost budget with actual and forecast email
   thresholds; AWS Budgets alerts do not stop running resources.
3. Owner reviews region, instance eligibility, image, storage, network rules,
   estimated charges and launches the small EC2 instance. Tag it
   `Project=BonereaperV5`, `Environment=Research`.
4. Install the repository on the instance, pin the deployed Git commit, and
   configure the three CLOB API values using the host secret mechanism. Never
   give the instance a wallet private key. Set `POLYGON_RPC_URL` for the later
   receipt stage; a public Polygon mainnet endpoint can be used for the pilot.
5. Run the 1200-second collector once following
   `BONEREAPER_CROSS_ASSET_CAPTURE_V5_RUNBOOK.md`, check `clean_finalize`,
   verify all seven live TWAP counts, and copy the immutable bundle to durable
   storage *before* terminating the instance. Incomplete captures are retained
   for diagnosis and cannot enter the study.
6. Only after the pilot passes, schedule bounded repeated bundles. The
   collector allows 960–14,400 seconds per invocation; a process supervisor,
   off-instance backup, retry policy and duplicate prevention are required
   before unattended multi-day operation. The frozen study ends at 60 eligible
   core conditions or seven complete UTC days after the first eligible day.
7. Remove the instance and its volume at the end of the research window after
   verifying off-instance backups. Check Billing for any remaining resources.

No IAM access keys or cloud credentials are required in the Git repository.
Avoid pasting root credentials, CLOB secrets, private keys or a credentialed
RPC URL into chat, commands, logs or Git. AWS signup/account handoff and
creation of billable resources require the owner's access to the AWS console.
