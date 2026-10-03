#!/usr/bin/env python3
"""Read-only Limitless SmartCopy observability probe (Python 3.10+).

Run: python3 limitless_smartcopy_probe.py --minutes 60 --interval 15 --out ./limitless_probe
No credentials, private keys, trading endpoints, or third-party packages.
The program records observations; it does NOT assess trading profitability.
"""

import argparse
import datetime as dt
import json
import pathlib
import re
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.limitless.exchange"
DEFAULT_ACCOUNTS = (
    "0xff612b93bf130a2bccdf303e360e89d225685e71",  # AncientDiligentRainbow
    "0xc2faf128201d89cba789c1dde5424d49bd75e44e",  # SmokyFleetStream
    "0x61761b4ff620607295e894f7c529a4de35dec3b4",  # asthenic_pieces (basket control)
)
ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
CRYPTO = re.compile(r"(?:\bBTC\b|\bETH\b|Bitcoin|Ethereum).*(?:5 Min|15 Min|Hourly)", re.I)


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def parse_time(value):
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value / (1000 if value > 1e11 else 1), dt.timezone.utc)
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(dt.timezone.utc)
        except ValueError:
            pass
    return None


def get_json(path, params=None, timeout=8):
    if not path.startswith("/"):
        raise ValueError("Only relative API paths are accepted")
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "SmartCopyLimitlessReadOnlyProbe/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def append_jsonl(path, obj):
    with path.open("a", encoding="utf-8") as out:
        out.write(json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + "\n")


def event_items(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("events", "data", "history", "items"):
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def identity(item, account=""):
    # Do not collapse multiple fills merely because they share a market and time.
    for key in ("id", "uid", "tradeEventId"):
        if item.get(key) is not None:
            return account + ":" + str(item[key])
    # Market metadata (status, winner, etc.) changes after execution.
    stable = {k: item.get(k) for k in (
        "transactionHash", "orderId", "blockTimestamp", "strategy",
        "outcomeIndex", "outcomeTokenAmount", "collateralAmount",
    ) if item.get(k) is not None}
    if stable:
        stable["market_id"] = (item.get("market") or {}).get("id")
        return account + ":" + json.dumps(stable, sort_keys=True)
    return account + ":" + json.dumps(item, sort_keys=True, ensure_ascii=False)


def metadata(item):
    profile = item.get("profile") or {}
    subject = item.get("subject") or {}
    market = item.get("market") or {}
    facts = item.get("facts") or {}
    slug = subject.get("slug") or market.get("slug") or item.get("marketSlug")
    title = subject.get("title") or market.get("title") or item.get("marketTitle") or ""
    account = profile.get("account") or item.get("account") or item.get("wallet")
    occurred = item.get("occurredAt") or item.get("blockTimestamp") or item.get("createdAt")
    entry_type = item.get("entryType") or item.get("strategy") or item.get("type")
    outcome = facts.get("outcome") or item.get("outcome") or item.get("side")
    return dict(account=account, slug=slug, title=title, occurred_at=occurred,
                entry_type=entry_type, outcome=outcome,
                source_price=facts.get("price") or item.get("outcomeTokenPrice"))


def book_prices(book):
    def top(levels, reverse):
        values = [float(x["price"]) for x in levels if isinstance(x, dict) and x.get("price") is not None]
        return (max(values) if reverse else min(values)) if values else None
    bid = top(book.get("bids") or [], True)
    ask = top(book.get("asks") or [], False)
    return {"yes_bid": bid, "yes_ask": ask,
            "no_bid": None if ask is None else 1 - ask,
            "no_ask": None if bid is None else 1 - bid}


def report(events_path, output, started_at, books_path):
    rows = [json.loads(s) for s in events_path.read_text(encoding="utf-8").splitlines()] if events_path.exists() else []
    genuine = [r for r in rows if r.get("kind") == "observation"]
    errors = [r for r in rows if r.get("kind") == "request_error"]
    polls = [r for r in rows if r.get("kind") == "poll_success"]
    crypto = [r for r in genuine if r.get("crypto_candidate")]
    delays = [r["visible_delay_s"] for r in genuine if isinstance(r.get("visible_delay_s"), (int, float))]
    start = parse_time(started_at)
    fresh = [r for r in genuine if (parse_time(r.get("occurred_at")) or dt.datetime.min.replace(
        tzinfo=dt.timezone.utc)) >= start]
    fresh_delays = [r["visible_delay_s"] for r in fresh
                    if isinstance(r.get("visible_delay_s"), (int, float))]
    books = [json.loads(s) for s in books_path.read_text(encoding="utf-8").splitlines()] if books_path.exists() else []
    output.write_text(json.dumps({
        "status": "API_UNAVAILABLE" if errors and not genuine else "OBSERVATIONS_ONLY_NO_EDGE_CLAIM",
        "generated_at": now(), "started_at": started_at, "observations": len(genuine),
        "events_occurred_during_run": len(fresh),
        "fresh_delay_p50_s": statistics.median(fresh_delays) if fresh_delays else None,
        "poll_successes": len(polls),
        "first_poll_at": polls[0]["fetched_at"] if polls else None,
        "last_poll_at": polls[-1]["fetched_at"] if polls else None,
        "fresh_crypto_trades": sum(bool(r.get("crypto_candidate")) and
                                   str(r.get("entry_type")).upper() in
                                   ("BOUGHT", "BUY", "LIMIT BUY", "MARKET BUY", "SOLD", "SELL", "MARKET SELL")
                                   for r in fresh),
        "book_requests": len(books), "book_errors": sum("error" in b for b in books),
        "request_errors": len(errors),
        "last_error": errors[-1]["error"] if errors else None, "crypto_candidates": len(crypto),
        "wallets_seen": sorted({r.get("account") for r in genuine if r.get("account")}),
        "first_seen_minus_occurred_p50_s": statistics.median(delays) if delays else None,
        "first_seen_minus_occurred_max_s": max(delays) if delays else None,
        "caveats": ["This is an upper bound on publication delay plus polling and network delay.",
                    "Public global feed filters small events and may be cached.",
                    "A REST book fetched after detection is not the book at source execution.",
                    "Without full depth, fees, fill model and out-of-sample controls, no copyability claim."],
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(args):
    output = pathlib.Path(args.out)
    output.mkdir(parents=True, exist_ok=True)
    events_path = output / "observations.jsonl"
    books_path = output / "books.jsonl"
    started_at = now()
    seen = set()
    accounts = tuple(x.lower() for x in args.account) if args.account else DEFAULT_ACCOUNTS
    if not all(ADDRESS.fullmatch(x) for x in accounts):
        raise SystemExit("Invalid account address")
    deadline = parse_time(args.until) if args.until else None
    if args.until and deadline is None:
        raise SystemExit("--until must be an ISO-8601 UTC timestamp")
    end = time.monotonic() + args.minutes * 60
    if deadline is not None:
        end = min(end, time.monotonic() + max(0, (deadline - dt.datetime.now(dt.timezone.utc)).total_seconds()))
    cycle = 0
    try:
        while time.monotonic() < end:
            cycle += 1
            started = time.monotonic()
            sources = [("feed", None, "/feed/trading", {"audience": "all", "limit": 30})]
            sources += [("history", account, "/portfolio/" + account + "/history", {"limit": 30}) for account in accounts]
            for source, account, path, params in sources:
                fetched_at = now()
                try:
                    payload = get_json(path, params)
                    fetched_at = now()
                    items = event_items(payload)
                    if not isinstance(payload, (dict, list)):
                        raise ValueError("Unexpected payload")
                    append_jsonl(events_path, {
                        "kind": "poll_success", "source": source, "account": account,
                        "fetched_at": fetched_at, "items": len(items),
                        "has_more": payload.get("hasMore") if isinstance(payload, dict) else None,
                        "next_cursor_present": bool(payload.get("nextCursor")) if isinstance(payload, dict) else False,
                    })
                    if not items and cycle == 1:
                        append_jsonl(events_path, {"kind": "empty_response", "source": source,
                                                   "account": account, "fetched_at": fetched_at,
                                                   "response_keys": list(payload) if isinstance(payload, dict) else []})
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        meta = metadata(item)
                        observed_account = (meta["account"] or account or "").lower()
                        uid = identity(item, observed_account)
                        if uid in seen:
                            continue
                        seen.add(uid)
                        occurred = parse_time(meta["occurred_at"])
                        first_seen = parse_time(fetched_at)
                        delay = (first_seen - occurred).total_seconds() if occurred else None
                        crypto_candidate = bool(CRYPTO.search(meta["title"]))
                        row = {**meta, "kind": "observation", "source": source, "id": uid,
                               "account": observed_account, "first_seen_at": fetched_at,
                               "visible_delay_s": delay, "crypto_candidate": crypto_candidate,
                               "raw": item}
                        append_jsonl(events_path, row)
                        # Book is read only after the event reaches our observer.
                        if (crypto_candidate and occurred and occurred >= parse_time(started_at)
                                and meta["slug"]
                                and not (item.get("market") or {}).get("closed")
                                and str(meta["entry_type"]).upper() in
                                ("BOUGHT", "BUY", "LIMIT BUY", "MARKET BUY")):
                            slug = urllib.parse.quote(meta["slug"], safe="")
                            try:
                                book = get_json("/markets/" + slug + "/orderbook")
                                append_jsonl(books_path, {"event_id": uid, "fetched_at": now(),
                                                          "slug": meta["slug"], "top": book_prices(book), "raw": book})
                            except (urllib.error.HTTPError, urllib.error.URLError, ValueError, OSError) as e:
                                append_jsonl(books_path, {"event_id": uid, "fetched_at": now(),
                                                          "slug": meta["slug"], "error": str(e)})
                except (urllib.error.HTTPError, urllib.error.URLError, ValueError, OSError) as e:
                    append_jsonl(events_path, {"kind": "request_error", "source": source,
                                               "account": account, "fetched_at": fetched_at, "error": str(e)})
            report(events_path, output / "summary.json", started_at, books_path)
            time.sleep(max(0, min(args.interval - (time.monotonic() - started), end - time.monotonic())))
    except KeyboardInterrupt:
        pass
    finally:
        report(events_path, output / "summary.json", started_at, books_path)
        print("Saved", output / "summary.json")


def selftest():
    assert book_prices({"bids": [{"price": 0.4}], "asks": [{"price": 0.6}]}) == {
        "yes_bid": 0.4, "yes_ask": 0.6, "no_bid": 0.4, "no_ask": 0.6}
    assert parse_time("2026-10-02T20:00:00Z").tzinfo is not None
    assert metadata({"profile": {"account": DEFAULT_ACCOUNTS[0]},
                     "subject": {"slug": "btc-15min", "title": "BTC Up or Down - 15 Min"},
                     "facts": {"outcome": "YES", "price": "0.5"},
                     "entryType": "BOUGHT"})["outcome"] == "YES"
    assert len(event_items({"events": [{"id": "1"}]})) == 1
    a = {"tradeEventId": "t1", "market": {"id": "1", "closed": False}}
    b = {"tradeEventId": "t1", "market": {"id": "1", "closed": True}}
    assert identity(a) == identity(b)
    print("Selftest OK")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--minutes", type=float, default=60)
    parser.add_argument("--interval", type=float, default=15)
    parser.add_argument("--until", help="Absolute UTC stop time, e.g. 2026-10-10T09:00:00Z")
    parser.add_argument("--out", default="./limitless_probe")
    parser.add_argument("--account", action="append", help="Repeat for specific public accounts")
    parser.add_argument("--selftest", action="store_true")
    options = parser.parse_args()
    if options.selftest:
        selftest()
    elif options.minutes <= 0 or options.interval < 5:
        parser.error("minutes must be positive and interval at least 5 seconds")
    else:
        run(options)
