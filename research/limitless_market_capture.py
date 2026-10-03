#!/usr/bin/env python3
"""Bounded public Limitless capture, independent of wallet activity. No orders."""
import argparse
import asyncio
import datetime as dt
import gzip
import json
import pathlib
import re
import time
import urllib.parse
import urllib.request
import urllib.error
from collections import Counter

BASE = "https://api.limitless.exchange"
NS = "/markets"


def utc():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="microseconds")


def timestamp(value):
    try:
        if isinstance(value, (int, float)):
            return value / (1000 if value > 1e11 else 1)
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, AttributeError):
        return None


def family(m):
    text = str(m.get("title", ""))
    asset = "BTC" if re.search(r"\bBTC\b|Bitcoin", text, re.I) else (
        "ETH" if re.search(r"\bETH\b|Ethereum", text, re.I) else None)
    horizon = "15m" if re.search(r"\b15\s*(?:min|minute)", text, re.I) else (
        "1h" if re.search(r"hourly|\b1\s*hour\b", text, re.I) else None)
    if asset and horizon and re.search(r"up\s*(?:or|/)\s*down", text, re.I):
        return asset, horizon
    return None


def select(markets, current):
    eligible = [m for m in markets if family(m) and m.get("slug")
                and str(m.get("tradeType", "")).lower() == "clob"
                and m.get("status") == "FUNDED" and not m.get("expired")
                and (timestamp(m.get("expirationTimestamp")) or 0) > current]
    # Deterministic cap, never rank markets by subsequent returns.
    return sorted(eligible, key=lambda m: (timestamp(m["expirationTimestamp"]), m["slug"]))[:8]


def request(path, params=None):
    if not path.startswith("/markets/"):
        raise ValueError("Only public market GET routes allowed")
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/json",
        "User-Agent": "SmartCopyLimitlessMarketResearch/1"})
    with urllib.request.urlopen(req, timeout=8) as response:
        return json.load(response)


class Recorder:
    def __init__(self, out):
        self.out = pathlib.Path(out)
        self.out.mkdir(parents=True, exist_ok=True)
        self.file = gzip.open(self.out / "capture.jsonl.gz", "at", encoding="utf-8")
        self.counts = Counter()
        self.bytes = 0
        self.capped = False

    def write(self, kind, **fields):
        row = {"kind": kind, "observed_at": utc(), "monotonic_ns": time.monotonic_ns(), **fields}
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
        self.bytes += len(line.encode())
        if self.bytes > 256 * 1024 * 1024:
            self.capped = True
            return
        self.file.write(line)
        self.counts[kind] += 1

    def flush(self):
        self.file.flush()


async def capture(args):
    import socketio
    recorder = Recorder(args.out)
    started = utc()
    cutoff = timestamp(args.until)
    end = min(time.monotonic() + args.minutes * 60,
              time.monotonic() + max(0, cutoff - time.time()))
    client = socketio.AsyncClient(reconnection=True, reconnection_delay=2,
                                 reconnection_delay_max=15)
    watched = {}
    active = []
    restored = pathlib.Path(args.state) if args.state else None
    if restored and restored.exists():
        try:
            watched = json.loads(restored.read_text()).get("watched", {})
        except (ValueError, OSError) as error:
            recorder.write("state_error", error=str(error))
    backoff_until = 0

    async def get(kind, path, params=None, slug=None):
        nonlocal backoff_until
        if time.monotonic() < backoff_until or time.monotonic() >= end:
            return None
        requested_at = utc()
        try:
            raw = await asyncio.to_thread(request, path, params)
            recorder.write(kind, slug=slug, requested_at=requested_at, path=path,
                           params=params, raw=raw)
            return raw
        except Exception as error:
            detail = error.read(2000).decode("utf-8", errors="replace") if isinstance(error, urllib.error.HTTPError) else None
            recorder.write("request_error", operation=kind, slug=slug, path=path,
                           requested_at=requested_at, params=params, error=str(error), detail=detail)
            if getattr(error, "code", None) == 429:
                backoff_until = time.monotonic() + 60
            return None

    async def subscribe():
        if client.connected and active:
            payload = {"marketSlugs": active}
            await client.emit("subscribe_market_prices", payload, namespace=NS)
            await client.emit("subscribe_oracle_price_data", payload, namespace=NS)
            recorder.write("subscription", slugs=list(active))

    @client.on("connect", namespace=NS)
    async def connected():
        recorder.write("ws_connect")
        await client.emit("subscribe_market_lifecycle", namespace=NS)
        await subscribe()

    @client.on("disconnect", namespace=NS)
    async def disconnected(*_):
        recorder.write("ws_disconnect")

    @client.on("*", namespace=NS)
    async def event(name, *payload):
        # Keep complete envelopes, publisher timestamps and versions. Do not infer fills.
        recorder.write("ws_event", event=name, raw=payload[0] if len(payload) == 1 else list(payload))

    async def discover():
        nonlocal active
        found = []
        complete = False
        for page in range(1, 21):
            raw = await get("listing", "/markets/active",
                            {"page": page, "limit": 25, "tradeType": "clob"})
            if not isinstance(raw, dict) or not isinstance(raw.get("data"), list):
                break
            rows = raw["data"]
            found.extend(rows)
            if not rows or len(rows) < 25 or len(found) >= (raw.get("totalMarketsCount") or float("inf")):
                complete = True
                break
        chosen = select(found, time.time())
        recorder.write("discovery", complete=complete, scanned=len(found),
                       selected=[m["slug"] for m in chosen])
        # Failed/partial discovery cannot silently erase an existing subscription.
        if complete:
            active = [m["slug"] for m in chosen]
        for m in chosen:
            watched.setdefault(m["slug"], {"first_observed_at": utc(), "market": m})
        await subscribe()

    async def snapshots():
        for slug in list(active):
            await get("book", "/markets/" + urllib.parse.quote(slug, safe="") + "/orderbook", slug=slug)

    async def metadata():
        due = [(slug, entry) for slug, entry in watched.items()
               if not entry.get("resolved") and time.time() >= entry.get("next_check", 0)]
        due.sort(key=lambda pair: (pair[0] not in active, pair[1].get("next_check", 0), pair[0]))
        for slug, entry in due[:16]:
            entry["next_check"] = time.time() + (60 if slug in active else 300)
            raw = await get("market", "/markets/" + urllib.parse.quote(slug, safe=""), slug=slug)
            if isinstance(raw, dict):
                entry["market"] = raw
                entry["resolved"] = raw.get("status") == "RESOLVED"
                # Unresolved markets remain in the carried checkpoint until resolved.
        # One current oracle history per asset; all responses remain observation-timed.
        by_asset = {}
        for slug in active:
            entry = watched.get(slug, {})
            f = family(entry.get("market", {}))
            if f:
                by_asset.setdefault(f[0], slug)
        for slug in by_asset.values():
            current = int(time.time())
            await get("oracle_candles", "/markets/" + urllib.parse.quote(slug, safe="") + "/oracle-candles",
                      {"interval": "1m", "from": current - 3 * 3600, "to": current}, slug=slug)

    next_discovery = next_metadata = next_book = next_connect = 0
    try:
        while time.monotonic() < end and not recorder.capped:
            t = time.monotonic()
            if t >= next_discovery:
                await discover()
                next_discovery = time.monotonic() + 60
            if not client.connected and t >= next_connect:
                try:
                    await client.connect("https://ws.limitless.exchange", namespaces=[NS],
                                         transports=["websocket"], wait_timeout=8)
                except Exception as error:
                    recorder.write("ws_connect_error", error=str(error))
                next_connect = time.monotonic() + 30
            if t >= next_metadata:
                await metadata()
                next_metadata = time.monotonic() + 60
            if t >= next_book:
                await snapshots()
                next_book = time.monotonic() + 15
                recorder.write("heartbeat", active=list(active), ws_connected=client.connected)
                recorder.flush()
            await asyncio.sleep(min(1, max(0, end - time.monotonic())))
    finally:
        if client.connected:
            await client.disconnect()
        recorder.flush()
        recorder.file.close()
        state = {"watched": {slug: item for slug, item in watched.items() if not item.get("resolved")}}
        (recorder.out / "state.json").write_text(json.dumps(state, ensure_ascii=False))
        summary = {"status": "CAPTURE_ONLY_NO_PNL", "started_at": started, "ended_at": utc(),
                   "counts": dict(recorder.counts), "uncompressed_bytes": recorder.bytes,
                   "size_cap_reached": recorder.capped, "markets_seen": len(watched),
                   "unresolved_carried": len(state["watched"]), "active_slugs": active,
                   "limitations": ["GitHub job gaps are missing observations",
                       "Book frames are coalesced states, not fills or queue events",
                       "Oracle response schemas and settlement streams require verification before paper PnL"]}
        (recorder.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(summary))


def selftest():
    assert family({"title": "BTC Up or Down - 15 Min"}) == ("BTC", "15m")
    assert family({"title": "ETH Up or Down - Hourly"}) == ("ETH", "1h")
    assert family({"title": "BTC Up or Down - 5 Min"}) is None
    assert family({"title": "SOL Up or Down - Hourly"}) is None
    assert family({"title": "BTC above $100000 - Hourly"}) is None
    m = {"title": "BTC Up or Down - 15 Min", "slug": "x", "tradeType": "clob",
         "status": "FUNDED", "expirationTimestamp": 2000000000000}
    assert select([m], 1900000000) == [m]
    assert not select([{**m, "tradeType": "amm"}], 1900000000)
    assert not select([m], 2100000000)
    print("selftest PASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--minutes", type=float, default=55)
    parser.add_argument("--until", default="2026-10-10T09:00:00Z")
    parser.add_argument("--out", default="limitless_market_capture")
    parser.add_argument("--state")
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    if args.selftest:
        selftest()
    else:
        if not 0 < args.minutes <= 55 or timestamp(args.until) is None:
            parser.error("minutes must be in (0,55], until must be an ISO UTC timestamp")
        asyncio.run(capture(args))
