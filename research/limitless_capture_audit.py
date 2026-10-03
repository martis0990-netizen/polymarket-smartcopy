#!/usr/bin/env python3
"""Capture feasibility only. Never turns midpoint/book touches into paper fills."""
import argparse
import gzip
import json
import statistics
import zipfile
from collections import Counter


def audit(paths):
    counts, socket_events = Counter(), Counter()
    spreads, slugs, oracle_slugs = [], set(), set()
    segments = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            for name in archive.namelist():
                if name.endswith("summary.json"):
                    segments.append(json.loads(archive.read(name)))
                if not name.endswith("capture.jsonl.gz"):
                    continue
                with archive.open(name) as compressed, gzip.open(compressed, "rt") as lines:
                    for line in lines:
                        row = json.loads(line)
                        kind = row["kind"]
                        counts[kind] += 1
                        raw = row.get("raw") or {}
                        if kind == "oracle_candles":
                            oracle_slugs.add(row["slug"])
                        if kind == "market":
                            slugs.add(row["slug"])
                        if kind == "ws_event":
                            socket_events[row["event"]] += 1
                        # Use REST snapshots only; each one has an unambiguous slug.
                        if kind != "book" or not isinstance(raw, dict):
                            continue
                        try:
                            bids = [float(x["price"]) for x in raw.get("bids", []) if float(x["size"]) > 0]
                            asks = [float(x["price"]) for x in raw.get("asks", []) if float(x["size"]) > 0]
                            if bids and asks and 0 <= max(bids) <= min(asks) <= 1:
                                spreads.append(min(asks) - max(bids))
                        except (KeyError, TypeError, ValueError):
                            counts["invalid_book_schema"] += 1
    ready = bool(counts["book"] and counts["oracle_candles"] and slugs)
    return {"status": "READY_FOR_SCHEMA_REVIEW" if ready else "INSUFFICIENT_DATA",
            "segments": len(segments), "counts": dict(counts), "ws_events": dict(socket_events),
            "distinct_markets": len(slugs), "oracle_candle_markets": len(oracle_slugs),
            "two_sided_rest_books": len(spreads),
            "median_rest_spread": statistics.median(spreads) if spreads else None,
            "segment_windows": [{k: s.get(k) for k in ("started_at", "ended_at", "size_cap_reached")} for s in segments],
            "pnl": None, "interpretation": "Feasibility only; schema review is required. Repeated snapshots are not independent opportunities."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archives", nargs="+")
    parser.add_argument("--out", default="limitless_market_audit.json")
    args = parser.parse_args()
    result = audit(args.archives)
    with open(args.out, "w") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)
    print(json.dumps(result))
