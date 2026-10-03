#!/usr/bin/env python3
"""Audit archived forward observation. Never infers trades from historical backfill."""
import argparse
import collections
import datetime as dt
import json
import pathlib
import statistics
import zipfile
from limitless_smartcopy_probe import metadata

START = dt.datetime.fromisoformat("2026-10-03T09:00:00+00:00")
END = dt.datetime.fromisoformat("2026-10-10T09:00:00+00:00")
WATCHLIST = {
    "0xff612b93bf130a2bccdf303e360e89d225685e71",
    "0xc2faf128201d89cba789c1dde5424d49bd75e44e",
    "0x61761b4ff620607295e894f7c529a4de35dec3b4",
}


def timestamp(value):
    if isinstance(value, (float, int)):
        return dt.datetime.fromtimestamp(value / (1000 if value > 1e11 else 1), dt.timezone.utc)
    if isinstance(value, str):
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
    return None


def audit(paths):
    rows, books, segments = [], [], []
    for path in paths:
        try:
            with zipfile.ZipFile(path) as z:
                summary = json.loads(z.read("summary.json"))
                if timestamp(summary.get("started_at")) is None:
                    continue
                segments.append({"artifact": pathlib.Path(path).name,
                                 "started_at": summary["started_at"],
                                 "ended_at": summary["generated_at"]})
                rows.extend(json.loads(x) for x in z.read("observations.jsonl").splitlines())
                if "books.jsonl" in z.namelist():
                    books.extend(json.loads(x) for x in z.read("books.jsonl").splitlines())
        except (zipfile.BadZipFile, KeyError, ValueError) as exc:
            segments.append({"artifact": pathlib.Path(path).name, "error": str(exc)})
    polls = collections.defaultdict(set)
    observed = {}
    for row in rows:
        at = timestamp(row.get("fetched_at") or row.get("first_seen_at"))
        if at is None or not START <= at < END:
            continue
        if row.get("kind") == "poll_success" and row.get("source") == "history":
            account = row.get("account")
            if account in WATCHLIST:
                polls[account].add(at)
        elif row.get("kind") == "observation":
            # Deterministic decoding of the original immutable source record only.
            # Do not fetch later market data to enrich an earlier observation.
            if isinstance(row.get("raw"), dict):
                decoded = metadata(row["raw"])
                row = {**row, **{k: decoded[k] for k in
                       ("outcome", "outcome_basis", "operation", "condition_id", "order_id")}}
            key = row.get("id")
            if key and (key not in observed or at < timestamp(observed[key]["first_seen_at"])):
                observed[key] = row

    # A successful poll credits only the 30 seconds immediately before it.
    window_s = (END - START).total_seconds()
    coverage = {}
    for account in sorted(WATCHLIST):
        spans = []
        for at in sorted(polls[account]):
            left, right = max(START, at - dt.timedelta(seconds=30)), min(END, at)
            if spans and left <= spans[-1][1]:
                spans[-1] = (spans[-1][0], max(right, spans[-1][1]))
            else:
                spans.append((left, right))
        seconds = sum((b - a).total_seconds() for a, b in spans)
        coverage[account] = {"polls": len(polls[account]),
                             "covered_seconds": round(seconds, 1),
                             "fraction": round(seconds / window_s, 4)}

    book_by_id = {}
    for b in books:
        key = b.get("event_id")
        if key in observed and "error" not in b and b.get("fetched_at"):
            at = timestamp(b["fetched_at"])
            if at >= timestamp(observed[key]["first_seen_at"]) and (key not in book_by_id or at < timestamp(book_by_id[key]["fetched_at"])):
                book_by_id[key] = b
    candidates = []
    for r in observed.values():
        event_time = timestamp(r.get("occurred_at"))
        if (r.get("account") in WATCHLIST and r.get("crypto_candidate")
                and str(r.get("entry_type")).upper() in
                ("BOUGHT", "BUY", "LIMIT BUY", "MARKET BUY")
                and event_time and START <= event_time < END):
            candidates.append(r)
    candidates.sort(key=lambda x: timestamp(x["first_seen_at"]))
    episodes, last = [], {}
    for r in candidates:
        key = (r["account"], r.get("slug"), str(r.get("outcome")))
        t = timestamp(r["first_seen_at"])
        if key not in last or (t - last[key]).total_seconds() > 60:
            episodes.append(r)
        last[key] = t
    executable = [r for r in episodes if r.get("outcome") in ("YES", "NO")
                  and book_by_id.get(r["id"], {}).get("top", {}).get(
                      "yes_ask" if r["outcome"] == "YES" else "no_ask") is not None]
    delays = [r["visible_delay_s"] for r in episodes
              if isinstance(r.get("visible_delay_s"), (int, float))]
    gaps = [book_by_id[r['id']].get('observed_ask_minus_source_price') for r in executable]
    gaps = [x for x in gaps if isinstance(x, (int, float))]
    grouped = {(r['account'], r.get('condition_id'), r.get('order_id'), r.get('outcome'))
               for r in candidates if r.get('condition_id') and r.get('order_id') and r.get('outcome')}
    return {
        "status": ("FEASIBLE_FOR_PAPER_REVIEW" if segments
                   and min(v["fraction"] for v in coverage.values()) >= .9
                   and len(executable) >= 60 else "INSUFFICIENT_DATA"),
        "window_utc": [START.isoformat(), END.isoformat()],
        "segments": len(segments), "segment_errors": [s for s in segments if "error" in s],
        "coverage_by_wallet": coverage,
        "candidate_buy_events": len(candidates),
        "independent_episode_proxy_60s": len(episodes),
        "episodes_with_outcome_and_observed_ask": len(executable),
        "episode_first_seen_delay_p50_s": statistics.median(delays) if delays else None,
        "order_side_groups_not_independent_intents": len(grouped),
        "candidate_events_unknown_outcome": sum(r.get('outcome') not in ('YES', 'NO') for r in candidates),
        "gross_quote_gap_sample_count": len(gaps),
        "observed_ask_minus_source_price_median": statistics.median(gaps) if gaps else None,
        "quote_gap_is_not_fill_or_pnl": True,
        "reason": "Proxy episodes need source-intent review; this is a data feasibility audit, not PnL.",
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archives", nargs="+", type=pathlib.Path)
    ap.add_argument("--out", default="limitless_audit.json")
    args = ap.parse_args()
    result = audit(args.archives)
    pathlib.Path(args.out).write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
