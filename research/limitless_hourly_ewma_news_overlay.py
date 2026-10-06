#!/usr/bin/env python3
"""Read-only, explicitly exploratory ISM hour-bucket overlay on saved shadow PnL."""
import argparse
import datetime as dt
import hashlib
import json
from decimal import Decimal
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("shadow_pnl", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    data = args.shadow_pnl.read_bytes()
    shadow = json.loads(data)
    if shadow["schema"] not in (
        "limitless-hourly-ewma30-frozen-cohort-shadow-pnl-v1",
        "limitless-hourly-ewma30-all-raw-decisions-shadow-v1",
    ):
        raise ValueError("unexpected shadow source")

    # The pre-published ISM release was 14:00 UTC 2026-10-05. The previous
    # exploratory review compared both adjacent 13:30 and 14:30 decisions.
    # This is an hour-bucket scenario, not an installed blackout rule.
    excluded_hours = {"2026-10-05T13", "2026-10-05T14"}
    output = {
        "schema": ("limitless-hourly-ewma30-all-ism-hour-overlay-v1"
                   if shadow["schema"] == "limitless-hourly-ewma30-all-raw-decisions-shadow-v1"
                   else "limitless-hourly-ewma30-ism-hour-overlay-v1"),
        "input_sha256": hashlib.sha256(data).hexdigest(),
        "input_schema": shadow["schema"],
        "scope": shadow.get("scope", "all raw-reconciled hourly decisions"),
        "event": {
            "name": "ISM Services PMI September 2026",
            "scheduled_at": "2026-10-05T14:00:00Z",
            "prior_schedule_source": "https://www.ismworld.org/supply-management-news-and-reports/reports/ism-pmi-reports/services/august/",
            "excluded_utc_hour_buckets": sorted(excluded_hours),
            "rule_status": "illustrative_posthoc_not_frozen",
        },
        "variants": {},
    }
    for name in ("frozen", "ewma30"):
        variant = shadow[name]
        rows = variant["rows"]
        assert len(rows) == shadow.get("baseline_exact_action_reproduction", shadow.get("decisions"))
        affected = []
        for row in rows:
            hour = dt.datetime.fromtimestamp(row["decision_at"], dt.timezone.utc).strftime("%Y-%m-%dT%H")
            if hour in excluded_hours:
                affected.append({
                    "condition": row["condition"], "symbol": row["symbol"],
                    "decision_at": dt.datetime.fromtimestamp(row["decision_at"], dt.timezone.utc).isoformat(),
                    "status": row["status"], "pnl_usdc": row.get("pnl_usdc"),
                    "cost_usdc": row.get("cost_usdc"), "payout_usdc": row.get("payout_usdc"),
                })
        settled = [r for r in affected if r["status"] == "SETTLED"]
        removed_pnl = sum((Decimal(r["pnl_usdc"]) for r in settled), Decimal(0))
        removed_cost = sum((Decimal(r["cost_usdc"]) for r in settled), Decimal(0))
        # All affected attempts were terminal in the pinned source.
        if any(r["status"] == "FILLED" for r in affected) or Decimal(variant["pending_cost"]) != 0:
            raise ValueError("open affected position needs chronological funded replay")
        original = Decimal(variant["realized"])
        adjusted = original - removed_pnl
        assert Decimal(variant["cash"]) == 100 + original
        output["variants"][name] = {
            "original_settled": variant["states"].get("SETTLED", 0),
            "original_pnl_usdc": str(original),
            "excluded_decisions": len(affected),
            "excluded_settled": len(settled),
            "excluded_cost_usdc": str(removed_cost),
            "excluded_pnl_usdc": str(removed_pnl),
            "retained_settled": variant["states"].get("SETTLED", 0) - len(settled),
            "retained_pnl_usdc": str(adjusted),
            "retained_cash_usdc": str(100 + adjusted),
            "excluded_rows": affected,
        }
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
