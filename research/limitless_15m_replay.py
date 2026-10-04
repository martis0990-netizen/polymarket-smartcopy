#!/usr/bin/env python3
"""Offline, receipt-ordered Limitless 15m paired paper replay. No network or orders."""

import argparse
import collections
import datetime as dt
import gzip
import hashlib
import html
import json
import math
import pathlib
import re
import random
import statistics
import zipfile
from decimal import Decimal, ROUND_DOWN

from limitless_15m_structure import coverage, label_decision, structural_gate
from limitless_hourly_paper import fill, levels
from limitless_inventory_paper import payouts
from limitless_market_regime import MinuteStore

VERSION = "limitless-15m-paired-paper-v1"
START = dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc).timestamp()
HOLDOUT = dt.datetime(2026, 10, 6, tzinfo=dt.timezone.utc).timestamp()
CUTOFF = dt.datetime(2026, 10, 10, 9, tzinfo=dt.timezone.utc).timestamp()
D = Decimal
FEE, HURDLE, BUDGET, MICRO = D(".03"), D(".03"), D("10"), D(".000001")
CAPITAL = D("100")
USDC = "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913"


def seconds(value):
    if isinstance(value, bool):
        raise ValueError("boolean timestamp")
    if isinstance(value, (int, float)):
        result = float(value) / (1000 if value > 1e11 else 1)
    else:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("naive timestamp")
        result = parsed.timestamp()
    if not math.isfinite(result):
        raise ValueError("nonfinite timestamp")
    return result


def fingerprint(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()


def market_spec(raw):
    """Only the exact Chainlink TWAP 15m binary family in the frozen contract."""
    try:
        meta = raw["metadata"]
        feed = meta["chainlinkDataStream"]
        asset = raw["title"].split(" Up or Down - 15 Min")[0]
        if asset not in ("BTC", "ETH") or raw["title"] != asset + " Up or Down - 15 Min":
            return None
        start, end = seconds(raw["startAt"]), seconds(raw["expirationTimestamp"])
        token = raw["collateralToken"]
        pair = asset + "/USD"
        description = html.unescape(re.sub(r"<[^>]*>", " ", raw["description"]))
        description = " ".join(description.split())
        dates = re.findall(r"on ([A-Z][a-z]+ \d{1,2}, \d{4}), at (\d{2}:\d{2}) UTC", description)
        parsed_dates = [dt.datetime.strptime(" ".join(pair_date), "%B %d, %Y %H:%M")
                        .replace(tzinfo=dt.timezone.utc).timestamp() for pair_date in dates]
        if (raw["tradeType"] != "clob" or raw["marketType"] != "single"
                or raw.get("groupId") or start % 900 or end-start != 900
                or token["symbol"] != "USDC" or token["decimals"] != 6
                or token["address"].lower() != USDC
                or feed["enabled"] is not True or feed["pair"] != pair
                or feed["streamType"] != "twap" or feed["twapWindowSeconds"] != 60
                or feed["priceDecimals"] != 18 or not feed["feedId"]
                or description.count(f"Chainlink {pair} 60-second TWAP") < 3
                or "greater than or equal to the Price to Beat captured from the same TWAP" not in description
                or 'Otherwise, this market will resolve to "Down"' not in description
                or "exact resolution time is used first" not in description
                or "first Chainlink observation within the following 5 seconds" not in description
                or "If no report exists in that window, the market will not resolve automatically" not in description
                or len(parsed_dates) != 3 or parsed_dates != [end, start, start]
                or seconds(meta["openPriceCapturedAt"]) != start
                or raw["tokens"]["yes"] == raw["tokens"]["no"]
                or not raw["tokens"]["yes"] or not raw["tokens"]["no"]):
            return None
        opening = D(str(meta["openPrice"]))
        delay = D(str(raw.get("settings", {}).get("takerDelayMs",
                                                meta.get("takerDelayMs"))))
        if not opening.is_finite() or opening <= 0 or not delay.is_finite() or delay < 0:
            return None
        return {"slug": raw["slug"], "condition": raw["conditionId"],
                "symbol": asset + "USDT", "oracle_symbol": asset + "USD",
                "start": start, "end": end, "opening": opening,
                "yes_token": raw["tokens"]["yes"], "no_token": raw["tokens"]["no"],
                "delay_s": float(delay)/1000 + 1,
                "feed_id": feed["feedId"]}
    except (KeyError, TypeError, ValueError, ArithmeticError, AttributeError):
        return None


def checked_book(row, spec):
    book = row.get("raw")
    if (row.get("slug") != spec["slug"] or row.get("source") != "limitless"
            or row.get("path") != "/markets/" + spec["slug"] + "/orderbook"
            or seconds(row["requested_at"]) > seconds(row["observed_at"])
            or not isinstance(book, dict) or book.get("tokenId") != spec["yes_token"]):
        raise ValueError("INVALID_BOOK_IDENTITY")
    for side in ("bids", "asks"):
        if not isinstance(book.get(side), list) or not book[side]:
            raise ValueError("EMPTY_BOOK")
        for level in book[side]:
            raw_size = D(str(level["size"]))
            if not raw_size.is_finite() or raw_size < 0 or raw_size != raw_size.to_integral_value():
                raise ValueError("INVALID_BOOK_SIZE")
    yes_asks, no_asks = levels(book, "YES"), levels(book, "NO")
    if not yes_asks or not no_asks or yes_asks[0][0] + no_asks[0][0] <= 1:
        raise ValueError("CROSSED_OR_LOCKED_BOOK")
    return book


def oracle_probability(row, spec):
    raw = row.get("raw")
    if (not isinstance(raw, dict) or raw.get("source") != "chainlink"
            or raw.get("symbol") != spec["oracle_symbol"] or raw.get("interval") != "1m"
            or row.get("slug") != spec["slug"] or row.get("source") != "limitless"
            or row.get("path") != "/markets/" + spec["slug"] + "/oracle-candles"):
        raise ValueError("INVALID_ORACLE_IDENTITY")
    requested, received = seconds(row["requested_at"]), seconds(row["observed_at"])
    if requested > received:
        raise ValueError("INVALID_ORACLE_TIMES")
    by_minute = {}
    for candle in raw["rows"]:
        stamp = candle["timestamp"]
        if (type(stamp) not in (int, float) or not math.isfinite(stamp)
                or stamp % 60 or stamp + 60 > requested):
            continue
        value = float(candle["close"])/1e18
        if not math.isfinite(value) or value <= 0 or stamp in by_minute:
            raise ValueError("INVALID_ORACLE_CANDLE")
        by_minute[stamp] = value
    times = sorted(by_minute)[-121:]
    if len(times) != 121 or any(b-a != 60 for a, b in zip(times, times[1:])):
        raise ValueError("MISSING_ORACLE_WARMUP")
    candle_end = times[-1] + 60
    if received-candle_end > 120 or candle_end > received or spec["end"] <= candle_end:
        raise ValueError("STALE_ORACLE")
    values = [by_minute[t] for t in times]
    sigma = statistics.stdev(math.log(b/a) for a, b in zip(values, values[1:]))
    if not math.isfinite(sigma) or sigma <= 0:
        raise ValueError("INVALID_VOLATILITY")
    z = math.log(values[-1]/float(spec["opening"])) / (sigma*math.sqrt((spec["end"]-candle_end)/60))
    return .5*(1+math.erf(z/math.sqrt(2))), sigma, candle_end


def candidate(book, probability):
    choices = []
    for side, chance in (("YES", probability), ("NO", 1-probability)):
        if not math.isfinite(chance) or not 0 <= chance <= 1:
            raise ValueError("INVALID_PROBABILITY")
        cap = D(str(chance))*(1-FEE)/(1+HURDLE)
        if cap <= 0:
            continue
        shares = (BUDGET/cap).quantize(MICRO, rounding=ROUND_DOWN)
        attempt = fill(book, side, cap, shares)
        if attempt:
            edge = D(attempt["net_shares"])*D(str(chance))/D(attempt["cost_usdc"])-1
            if edge >= HURDLE:
                choices.append((edge, side, cap, shares))
    if not choices:
        return None
    edge, side, cap, shares = max(choices, key=lambda x: (x[0], x[1]))
    return {"side": side, "max_price": str(cap), "shares": str(shares),
            "modeled_return": str(edge)}


def load_archives(manifest):
    """Verify exact main ZIPs, retain every raw request and receipt fingerprint."""
    rows, sources, seen_artifacts = [], [], set()
    previous_end, previous_state = None, None
    for item in manifest:
        run, artifact = item["run"], item["artifact"]
        if artifact["id"] in seen_artifacts:
            raise ValueError("DUPLICATE_ARTIFACT")
        seen_artifacts.add(artifact["id"])
        if (run.get("head_branch") != "main" or run.get("event") == "pull_request"
                or run.get("status") != "completed" or run.get("conclusion") != "success"
                or run.get("name") != "Limitless independent market capture"
                or run["id"] != artifact["workflow_run"]["id"]
                or run["head_sha"] != artifact["workflow_run"]["head_sha"]):
            raise ValueError("UNVERIFIED_MAIN_RUN")
        path = pathlib.Path(item["file"]["path"])
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if artifact["digest"] != "sha256:" + digest:
            raise ValueError("ZIP_DIGEST_MISMATCH")
        sources.append({"run": run["id"], "artifact": artifact["id"], "sha256": digest})
        with zipfile.ZipFile(path) as archive:
            state_bytes, summary_bytes = archive.read("state.json"), archive.read("summary.json")
            state, summary = json.loads(state_bytes), json.loads(summary_bytes)
            begin, end = seconds(summary["started_at"]), seconds(summary["ended_at"])
            if (summary["status"] != "CAPTURE_ONLY_NO_PNL" or begin >= end
                    or (previous_end is not None and
                        (begin < previous_end or begin-previous_end > 20*60))):
                raise ValueError("CHECKPOINT_TIMELINE_BROKEN")
            if previous_state is not None:
                if (state["paper"]["version"] != previous_state["paper"]["version"]
                        or state["inventory_paper"]["version"] != previous_state["inventory_paper"]["version"]
                        or state["inventory_paper"]["started_at"] != previous_state["inventory_paper"]["started_at"]):
                    raise ValueError("CHECKPOINT_VERSION_BROKEN")
                for family, field in (("paper", "markets"), ("paper", "episodes"),
                                      ("inventory_paper", "entry_attempts")):
                    old = previous_state[family][field]
                    new = state[family][field]
                    if not set(old) <= set(new):
                        raise ValueError("CHECKPOINT_LINEAGE_BROKEN")
                    for key in old:
                        prior, current = old[key], new[key]
                        immutable = ("condition", "slug", "start", "phase", "side")
                        if isinstance(prior, dict) and any(
                                k in prior and k in current and prior[k] != current[k]
                                for k in immutable):
                            raise ValueError("CHECKPOINT_IDENTITY_BROKEN")
                if not set(previous_state["inventory_paper_history"]) <= set(state["inventory_paper_history"]):
                    raise ValueError("CHECKPOINT_HISTORY_BROKEN")
            sources[-1].update({"state_sha256": hashlib.sha256(state_bytes).hexdigest(),
                                "summary_sha256": hashlib.sha256(summary_bytes).hexdigest(),
                                "started_at": summary["started_at"],
                                "ended_at": summary["ended_at"]})
            previous_end, previous_state = end, state
            with gzip.GzipFile(fileobj=archive.open("capture.jsonl.gz")) as stream:
                for line_number, line in enumerate(stream, 1):
                    if not any(tag in line for tag in
                               (b'"kind":"market"', b'"kind":"oracle_candles"',
                                b'"kind":"book"', b'"kind":"request_error"',
                                b'"kind":"binance_1m"', b'"kind":"discovery"')):
                        continue
                    row = json.loads(line)
                    row["_proof"] = {"artifact": artifact["id"], "line": line_number,
                                     "sha256": hashlib.sha256(line.rstrip(b"\n")).hexdigest()}
                    rows.append(row)
    rows.sort(key=lambda x: (seconds(x["observed_at"]), x["_proof"]["artifact"],
                             x["_proof"]["line"]))
    return rows, sources


def _attempts(rows, kind):
    return [r for r in rows if r["kind"] == kind or
            (r["kind"] == "request_error" and r.get("operation") == kind)]


def _first(rows, after, before):
    eligible = [r for r in rows if seconds(r["requested_at"]) >= after]
    if not eligible:
        return None
    first = min(eligible, key=lambda r: (seconds(r["requested_at"]),
                                         seconds(r["observed_at"])))
    return first if seconds(first["observed_at"]) <= before else None


def _first_received(rows, after, before):
    """First requested decision book whose response arrived within the window."""
    eligible = [r for r in rows if seconds(r["requested_at"]) >= after
                and seconds(r["observed_at"]) <= before]
    return min(eligible, key=lambda r: (seconds(r["requested_at"]),
                                         seconds(r["observed_at"]))) if eligible else None


def prepare(rows):
    store = MinuteStore()
    grouped = collections.defaultdict(list)
    discovered = set()
    for row in rows:
        if row["kind"] == "binance_1m":
            store.add(row, row["_proof"])
        elif row["kind"] == "discovery":
            discovered.update(slug for slug in row.get("selected", [])
                              if isinstance(slug, str) and "15-min-" in slug)
        elif row.get("slug") and "15-min-" in row["slug"]:
            grouped[row["slug"]].append(row)
    if store.errors:
        raise ValueError("INVALID_BINANCE_RESPONSE")
    episodes, labels, verified_slugs = [], [], set()
    for slug, events in grouped.items():
        market_rows = [r for r in events if r["kind"] == "market"
                       and isinstance(r.get("raw"), dict)]
        if not market_rows:
            continue
        spec = market_spec(market_rows[0]["raw"])
        if spec is None or not START <= spec["start"] < CUTOFF:
            continue
        verified_slugs.add(slug)
        ep = {"slug": slug, "condition": spec["condition"], "start": spec["start"],
              "phase": "discovery" if spec["start"] < HOLDOUT else "holdout",
              "symbol": spec["symbol"], "status": "SKIP", "reason": None,
              "market_proof": market_rows[0]["_proof"]}
        episodes.append(ep)
        identity = lambda s: (s["condition"], s["start"], s["end"], s["yes_token"],
                              s["no_token"], s["opening"], s["feed_id"])
        if (spec["slug"] != slug or any((other := market_spec(r["raw"])) is None
                                       or identity(other) != identity(spec)
                                       for r in market_rows)):
            ep["reason"] = "MARKET_IDENTITY_CONFLICT"
            continue
        window_start, window_end = spec["start"]+450, spec["start"]+510
        oracles = [r for r in _attempts(events, "oracle_candles")
                   if window_start <= seconds(r["observed_at"]) <= window_end]
        if not oracles:
            ep["reason"] = "MISSED_ORACLE_WINDOW"
            continue
        oracle = min(oracles, key=lambda r: (seconds(r["observed_at"]),
                                            seconds(r["requested_at"])))
        ep["oracle_proof"] = oracle["_proof"]
        if oracle["kind"] == "request_error":
            ep["reason"] = "FIRST_ORACLE_ERROR"
            continue
        try:
            p, sigma, candle_end = oracle_probability(oracle, spec)
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            ep["reason"] = str(exc)
            continue
        book_rows = _attempts(events, "book")
        decision_book = _first_received(book_rows, seconds(oracle["observed_at"]), window_end)
        if decision_book is None:
            ep["reason"] = "MISSED_DECISION_BOOK"
            continue
        ep["decision_book_proof"] = decision_book["_proof"]
        if decision_book["kind"] == "request_error":
            ep["reason"] = "FIRST_BOOK_ERROR"
            continue
        try:
            book = checked_book(decision_book, spec)
            model = candidate(book, p)
            control = candidate(book, .5)
        except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
            ep["reason"] = str(exc)
            continue
        decision_at = seconds(decision_book["observed_at"])
        if seconds(market_rows[0]["observed_at"]) > decision_at:
            ep["reason"] = "MARKET_NOT_KNOWN_AT_DECISION"
            continue
        ep.update(status="DECIDED", reason=None, decision_at=decision_at,
                  p_up=p, sigma=sigma, oracle_candle_end=candle_end,
                  opportunities={"model": model, "constant50": control},
                  accounts={}, settlement=None)
        label = label_decision(store, condition=spec["condition"],
                               symbol=spec["symbol"], open_ms=int(spec["start"]*1000),
                               decision_ms=int(decision_at*1000))
        ep["structure"] = label
        labels.append(label)
        if model:
            ep["structure_gate"] = structural_gate(label, model["side"])
            ep["opportunities"]["structure"] = (model if ep["structure_gate"] == "ALLOW"
                                                  else None)
        else:
            ep["structure_gate"] = "SKIP_BASELINE_NO_TRADE"
            ep["opportunities"]["structure"] = None
        # Lock the first execution request, including failed responses. No retry.
        eligible = decision_at + spec["delay_s"]
        execution = _first(book_rows, eligible, min(decision_at+30, spec["end"]))
        ep["execution_proof"] = execution["_proof"] if execution else None
        ep["execution_reason"] = None
        if execution is None:
            ep["execution_reason"] = "MISSED_EXECUTION_BOOK"
        elif execution["kind"] == "request_error":
            ep["execution_reason"] = "FIRST_EXECUTION_ERROR"
        else:
            try:
                ep["_execution_book"] = checked_book(execution, spec)
                ep["execution_at"] = seconds(execution["observed_at"])
                if ep["execution_at"] >= spec["end"]:
                    ep.pop("_execution_book")
                    ep["execution_reason"] = "EXECUTION_AT_OR_AFTER_EXPIRY"
            except (ValueError, KeyError, TypeError, ArithmeticError) as exc:
                ep["execution_reason"] = str(exc)
        resolved = [r for r in market_rows if r["raw"].get("status") == "RESOLVED"
                    and seconds(r["observed_at"]) >= spec["end"]]
        if resolved:
            first = resolved[0]
            pay = payouts(first["raw"])
            if pay is not None and all(payouts(r["raw"]) == pay for r in resolved):
                ep["settlement"] = {"at": seconds(first["observed_at"]),
                                    "payouts": [str(x) for x in pay],
                                    "proof": first["_proof"]}
            else:
                raise ValueError("INVALID_OR_CONFLICTING_PAYOUT:" + spec["condition"])
    if len({ep["condition"] for ep in episodes}) != len(episodes):
        raise ValueError("DUPLICATE_CONDITION_ID")
    unverified = []
    for slug in sorted((discovered | set(grouped)) - verified_slugs):
        try:
            opened = int(slug.rsplit("-", 1)[1])
        except ValueError:
            opened = None
        if opened is None or START <= opened < CUTOFF:
            unverified.append({"slug": slug, "start": opened})
    return episodes, coverage(labels), unverified


def settle_accounts(episodes):
    accounts = {name: {"cash": CAPITAL, "debits": D(0), "credits": D(0),
                       "settled_pnl": D(0), "positions": {}}
                for name in ("model", "constant50", "structure")}
    events = []
    for ep in episodes:
        if ep["status"] != "DECIDED":
            continue
        events.append((ep.get("execution_at", ep["decision_at"]), 1, ep))
        if ep["settlement"]:
            events.append((ep["settlement"]["at"], 0, ep))
    for _, kind, ep in sorted(events, key=lambda x: (x[0], x[1], x[2]["condition"])):
        for name, account in accounts.items():
            if kind == 0:
                position = account["positions"].get(ep["condition"])
                if position and position["status"] == "PENDING":
                    payout = D(ep["settlement"]["payouts"][0 if position["side"] == "YES" else 1])
                    credit = position["net_shares"] * payout
                    account["cash"] += credit
                    account["credits"] += credit
                    account["settled_pnl"] += credit-position["cost"]
                    position.update(status="SETTLED", payout=str(credit),
                                    pnl=str(credit-position["cost"]))
                    ep["accounts"][name].update(status="SETTLED",
                                                payout_usdc=str(credit),
                                                pnl_usdc=position["pnl"])
                continue
            opportunity = ep["opportunities"].get(name)
            if not opportunity:
                ep["accounts"][name] = {"status": "NO_TRADE",
                                         "reason": ep.get("structure_gate") if name == "structure"
                                         else "NO_EXECUTABLE_EDGE"}
                continue
            if ep["execution_reason"]:
                ep["accounts"][name] = {"status": "SKIP", "reason": ep["execution_reason"]}
                continue
            attempt = fill(ep["_execution_book"], opportunity["side"],
                           D(opportunity["max_price"]), D(opportunity["shares"]))
            if not attempt:
                ep["accounts"][name] = {"status": "SKIP", "reason": "NO_FULL_DELAYED_DEPTH"}
                continue
            cost = D(attempt["cost_usdc"])
            if cost > account["cash"]:
                ep["accounts"][name] = {"status": "NO_TRADE", "reason": "INSUFFICIENT_CASH"}
                continue
            account["cash"] -= cost
            account["debits"] += cost
            position = {"status": "PENDING", "side": opportunity["side"],
                        "cost": cost, "net_shares": D(attempt["net_shares"])}
            account["positions"][ep["condition"]] = position
            ep["accounts"][name] = {"status": "FILLED", "side": position["side"],
                                     "cost_usdc": str(cost),
                                     "net_shares": str(position["net_shares"])}
    result = {}
    for name, account in accounts.items():
        positions = account["positions"]
        pending_cost = sum((x["cost"] for x in positions.values()
                            if x["status"] == "PENDING"), D(0))
        if account["cash"] + pending_cost != CAPITAL + account["settled_pnl"]:
            raise ValueError("ACCOUNT_RECONCILIATION_FAILED")
        result[name] = {"cash_usdc": str(account["cash"]),
                        "pending_cost_usdc": str(pending_cost),
                        "settled_pnl_usdc": str(account["settled_pnl"]),
                        "debits_usdc": str(account["debits"]),
                        "payouts_usdc": str(account["credits"]),
                        "filled": len(positions),
                        "settled": sum(x["status"] == "SETTLED" for x in positions.values()),
                        "pending": sum(x["status"] == "PENDING" for x in positions.values())}
    return result


def phase_metrics(selected):
    scored = [ep for ep in selected if ep["status"] == "DECIDED" and ep["settlement"]]
    binary = [ep for ep in scored if ep["settlement"]["payouts"] in (["1", "0"], ["0", "1"])]
    brier = (sum((ep["p_up"] - float(ep["settlement"]["payouts"][0]))**2
                 for ep in binary)/len(binary)) if binary else None
    by_asset = {}
    by_h1 = {}
    for key, groups in (("asset", by_asset), ("h1", by_h1)):
        for ep in selected:
            label = ep["symbol"][:3] if key == "asset" else ep.get("structure", {}).get("h1_state", "UNAVAILABLE")
            item = groups.setdefault(label, {"conditions": 0, "decisions": 0, "allowed": 0,
                                              "settled_pnl_usdc": {name: D(0) for name in
                                                                   ("model", "constant50", "structure")}})
            item["conditions"] += 1
            item["decisions"] += ep["status"] == "DECIDED"
            item["allowed"] += ep.get("structure_gate") == "ALLOW"
            for name in item["settled_pnl_usdc"]:
                account = ep.get("accounts", {}).get(name, {})
                if account.get("status") == "SETTLED":
                    item["settled_pnl_usdc"][name] += D(account["pnl_usdc"])
        for item in groups.values():
            item["settled_pnl_usdc"] = {k: str(v) for k, v in item["settled_pnl_usdc"].items()}
    summaries = {}
    for name in ("model", "constant50", "structure"):
        account_rows = [ep["accounts"][name] for ep in selected if name in ep.get("accounts", {})]
        settled = [r for r in account_rows if r["status"] == "SETTLED"]
        spend = sum((D(r["cost_usdc"]) for r in settled), D(0))
        pnl = sum((D(r["pnl_usdc"]) for r in settled), D(0))
        timeline = sorted((ep["settlement"]["at"], ep["condition"],
                           D(ep["accounts"][name]["pnl_usdc"])) for ep in selected
                          if ep.get("settlement") and ep.get("accounts", {}).get(name, {}).get("status") == "SETTLED")
        wealth = peak = CAPITAL
        drawdown = D(0)
        for _, _, change in timeline:
            wealth += change
            peak = max(peak, wealth)
            drawdown = max(drawdown, peak-wealth)
        summaries[name] = {"fills": sum(r["status"] in ("FILLED", "SETTLED") for r in account_rows),
                           "skips": dict(collections.Counter(r.get("reason", "UNSPECIFIED") for r in account_rows
                                                             if r["status"] in ("SKIP", "NO_TRADE"))),
                           "pending": sum(r["status"] == "FILLED" for r in account_rows),
                           "settled": len(settled), "settled_spend_usdc": str(spend),
                           "settled_pnl_usdc": str(pnl),
                           "return_on_settled_spend": str(pnl/spend) if spend else None,
                           "settled_equity_drawdown_usdc": str(drawdown)}
    clusters = collections.defaultdict(lambda: {"model": D(0), "structure": D(0)})
    for ep in selected:
        for name in ("model", "structure"):
            row = ep.get("accounts", {}).get(name, {})
            if row.get("status") == "SETTLED":
                clusters[ep["start"]][name] += D(row["pnl_usdc"])
    uncertainty = None
    if len(clusters) >= 60 and len(scored) >= 60:
        differences = [float(v["structure"]-v["model"]) for _, v in sorted(clusters.items())]
        rng = random.Random(1506)
        samples = sorted(sum(rng.choices(differences, k=len(differences))) for _ in range(2000))
        uncertainty = {"method": "quarter_hour_cluster_bootstrap_2000_fixed_seed",
                       "structure_minus_model_pnl_usdc_95pct": [samples[49], samples[1949]],
                       "clusters": len(differences)}
    return {"brier_p_up": brier, "asset": by_asset, "h1_state": by_h1,
            "gate_reasons": dict(collections.Counter(ep.get("structure_gate", "NO_DECISION") for ep in selected)),
            "accounts": summaries, "cluster_uncertainty": uncertainty}


def replay(manifest):
    rows, sources = load_archives(manifest)
    episodes, structure_coverage, unverified = prepare(rows)
    accounts = settle_accounts(episodes)
    # Actual depth is a REST approximation, not a guaranteed exchange fill.
    for ep in episodes:
        ep.pop("_execution_book", None)
    phases = {}
    for phase in ("discovery", "holdout"):
        selected = [ep for ep in episodes if ep["phase"] == phase]
        missing = [row for row in unverified if row["start"] is None or
                   (row["start"] < HOLDOUT) == (phase == "discovery")]
        scored = [ep for ep in selected if ep["status"] == "DECIDED" and ep["settlement"]]
        decided = sum(ep["status"] == "DECIDED" for ep in selected)
        phases[phase] = {"conditions": len(selected),
                         "discovered_without_verified_market": len(missing),
                         "unverified_discovery_slugs": missing,
                         "quarter_hour_clusters": len({ep["start"] for ep in selected}),
                         "decisions": decided,
                         "observation_coverage": decided/(len(selected)+len(missing))
                         if selected or missing else None,
                         "resolved_scored_conditions": len(scored),
                         "resolved_scored_clusters": len({ep["start"] for ep in scored}),
                         "h1_known": sum(ep.get("structure", {}).get("ready_h1", False)
                                         for ep in selected),
                         "structure_allowed": sum(ep.get("structure_gate") == "ALLOW"
                                                  for ep in selected),
                         "reasons": dict(collections.Counter(ep["reason"] for ep in selected
                                                            if ep["reason"])),
                         **phase_metrics(selected)}
        phases[phase]["review_status"] = (
            "COVERAGE_REVIEW_ONLY" if len(scored) >= 60
            and len({ep["start"] for ep in scored}) >= 60
            and decided/(len(selected)+len(missing)) >= .9
            and phases[phase]["h1_known"] > 0
            and phases[phase]["structure_allowed"] > 0
            else "INSUFFICIENT_DATA")
    return {"version": VERSION, "status": "PAPER_ONLY_NOT_LIVE",
            "sources": sources, "structure_coverage": structure_coverage,
            "accounts": accounts, "phases": phases, "episodes": episodes,
            "limitations": ["REST depth is not a guaranteed match or queue fill.",
                            "Only observed resolution yields settled PnL.",
                            "No order submission, secrets, or network reads."]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    try:
        manifest_path = pathlib.Path(args.manifest).resolve()
        manifest = json.loads(manifest_path.read_text())
        for item in manifest:
            path = pathlib.Path(item["file"]["path"])
            if not path.is_absolute():
                item["file"]["path"] = str(manifest_path.parent/path)
        report = replay(manifest)
    except (ValueError, KeyError, TypeError, OSError, zipfile.BadZipFile,
            ArithmeticError) as exc:
        report = {"version": VERSION, "status": "UNRECONCILED", "report": None,
                  "error": str(exc)}
    pathlib.Path(args.out).write_text(json.dumps(report, ensure_ascii=False,
                                                 indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: report.get(k) for k in
                      ("version", "status", "structure_coverage", "accounts", "error")},
                     ensure_ascii=False))
    raise SystemExit(0 if report["status"] == "PAPER_ONLY_NOT_LIVE" else 1)
