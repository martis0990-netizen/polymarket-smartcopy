#!/usr/bin/env python3
"""Frozen Binance-settled hourly benchmark. Pure paper state; no network/orders."""
import datetime as dt
import json
import math
import statistics
from collections import Counter
from decimal import Decimal, ROUND_DOWN

VERSION = "limitless-hourly-v1"
FEE = Decimal("0.03")  # conservative upper buy fee, deducted in contracts
BUDGET = Decimal("10")
HURDLE = Decimal("0.03")
MICRO = Decimal("0.000001")
HOLDOUT = dt.datetime(2026, 10, 6, tzinfo=dt.timezone.utc).timestamp()


def seconds(value):
    if isinstance(value, (int, float)):
        return value / (1000 if value > 1e11 else 1)
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


def spec(m):
    """Unknown venue/settlement semantics never enter the benchmark."""
    try:
        meta = m["metadata"]
        chart = meta["chart"]
        start = seconds(m["startAt"])
        end = seconds(m["expirationTimestamp"])
        token = m["collateralToken"]
        if (m["tradeType"] != "clob" or chart.get("source") != "binance"
                or chart.get("market") != "spot" or chart.get("candle") != "hourly"
                or chart.get("symbol") not in ("BTCUSDT", "ETHUSDT")
                or seconds(chart["windowOpenAt"]) != start or end - start != 3600
                or start % 3600 != 0 or token.get("symbol") != "USDC"
                or token.get("decimals") != 6 or meta.get("chainlinkDataStream")):
            return None
        opening = Decimal(str(meta["openPrice"]))
        delay_ms = m.get("settings", {}).get("takerDelayMs", meta.get("takerDelayMs", 0))
        delay = float(delay_ms)
        if not math.isfinite(delay) or delay < 0 or not opening.is_finite() or opening <= 0:
            return None
        return {"condition": m["conditionId"], "slug": m["slug"], "start": start,
                "end": end, "symbol": chart["symbol"], "opening": str(opening),
                "yes_token": m["tokens"]["yes"], "delay_s": delay / 1000 + 1}
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return None


def probability(rows, current, opening, now, available_before=None):
    """Zero-drift log-price diffusion; training is 120 closed 1m returns."""
    cutoff = min(now, available_before) if available_before is not None else now
    closed = sorted((r for r in rows if float(r[6]) / 1000 < cutoff), key=lambda r: r[0])[-121:]
    if (len(closed) != 121 or any(int(r[6]) - int(r[0]) != 59999 for r in closed)
            or any(int(b[0]) - int(a[0]) != 60000 for a, b in zip(closed, closed[1:]))):
        raise ValueError("MISSING_CLOSED_WARMUP")
    if now - float(closed[-1][6]) / 1000 > 120:
        raise ValueError("STALE_CANDLES")
    prices = [float(r[4]) for r in closed]
    if not all(math.isfinite(p) and p > 0 for p in prices):
        raise ValueError("INVALID_CANDLES")
    sigma = statistics.stdev(math.log(b / a) for a, b in zip(prices, prices[1:]))
    remaining_min = (current["end"] - now) / 60
    if sigma <= 0 or remaining_min <= 0:
        raise ValueError("INVALID_VOLATILITY")
    z = math.log(current["price"] / float(opening)) / (sigma * math.sqrt(remaining_min))
    return .5 * (1 + math.erf(z / math.sqrt(2))), sigma


def levels(book, side):
    source = book.get("asks", []) if side == "YES" else book.get("bids", [])
    result = []
    for level in source:
        price = Decimal(str(level["price"]))
        size = Decimal(str(level["size"])) / Decimal(1000000)
        if not price.is_finite() or not size.is_finite() or not 0 < price < 1 or size < 0:
            raise ValueError("INVALID_BOOK")
        if size:
            result.append((price if side == "YES" else 1 - price, size))
    return sorted(result)


def fill(book, side, cap, shares):
    remaining, cost = shares, Decimal(0)
    for price, size in levels(book, side):
        if price > cap:
            break
        quantity = min(remaining, size)
        cost += quantity * price
        remaining -= quantity
        if remaining == 0:
            break
    if remaining > 0 or cost <= 0 or cost > BUDGET:
        return None
    return {"gross_shares": str(shares), "net_shares": str(shares * (1 - FEE)),
            "cost_usdc": str(cost), "vwap": str(cost / shares)}


class HourlyPaper:
    def __init__(self, state=None, emit=None):
        self.state = state or {"version": VERSION, "markets": {}, "episodes": {}}
        if self.state.get("version") != VERSION:
            raise ValueError("INCOMPATIBLE_PAPER_STATE")
        self.emit = emit or (lambda *args, **kwargs: None)
        self.minute = {}
        self.hour = {}

    def candles(self, symbol, interval, raw, observed, requested=None):
        if symbol not in ("BTCUSDT", "ETHUSDT") or not isinstance(raw, list):
            return
        target = self.minute if interval == "1m" else self.hour
        if interval in ("1m", "1h"):
            target[symbol] = (observed, raw, requested if requested is not None else observed)

    def market(self, m, observed):
        s = spec(m)
        if s is None:
            return
        s["status"] = m.get("status")
        self.state["markets"][s["slug"]] = s
        if m.get("status") != "RESOLVED" or observed < s["end"]:
            return
        winner = m.get("winningOutcomeIndex")
        payout = None
        if winner in (0, 1):
            payout = [1.0, 0.0] if winner == 0 else [0.0, 1.0]
        elif winner is None:
            numerators = m.get("payoutNumerators") or []
            if len(numerators) == 2 and all(float(x) >= 0 for x in numerators) and sum(map(float, numerators)) > 0:
                payout = [float(x) / sum(map(float, numerators)) for x in numerators]
        if payout is None:
            return
        ep = self.state["episodes"].get(s["condition"])
        if ep is None or ep.get("settled_at"):
            return
        ep["settled_at"], ep["payout"] = observed, payout
        if winner in (0, 1) and ep.get("p_up") is not None:
            y = float(winner == 0)
            ep["brier_model"] = (ep["p_up"] - y) ** 2
            ep["brier_50"] = .25
        for name, action in ep.get("variants", {}).items():
            if action["status"] == "PENDING":
                action.update(status="SKIP", reason="RESOLVED_BEFORE_FILL")
            if action["status"] == "FILLED":
                index = 0 if action["side"] == "YES" else 1
                profit = Decimal(action["net_shares"]) * Decimal(str(payout[index])) - Decimal(action["cost_usdc"])
                action.update(status="SETTLED", pnl_usdc=str(profit))
            else:
                action["pnl_usdc"] = "0"
        self.emit("paper_settlement", condition=s["condition"], episode=ep)

    def _inputs(self, s, observed):
        minute = self.minute.get(s["symbol"], (0, [], 0))
        ref_at, rows = minute[:2]
        requested_at = minute[2] if len(minute) > 2 else ref_at
        hour_at, hourly = self.hour.get(s["symbol"], (0, [], 0))[:2]
        if not 0 <= observed - ref_at <= 10 or not 0 <= observed - hour_at <= 120:
            raise ValueError("STALE_REFERENCE")
        opening = next((r for r in hourly if int(r[0]) == int(s["start"] * 1000)), None)
        if opening is None or Decimal(str(opening[1])) != Decimal(s["opening"]):
            raise ValueError("OPEN_PRICE_NOT_VERIFIED")
        current = [r for r in rows if float(r[0]) / 1000 <= observed <= float(r[6]) / 1000]
        if len(current) != 1:
            raise ValueError("MISSING_CURRENT_CANDLE")
        price = float(current[0][4])  # partially formed candle is reference only, never volatility training
        if not math.isfinite(price) or price <= 0:
            raise ValueError("INVALID_REFERENCE")
        p, sigma = probability(rows, {"price": price, "end": s["end"]}, s["opening"], observed, requested_at)
        return p, sigma, price, ref_at

    def book(self, slug, book, observed, requested=None):
        request_at = requested if requested is not None else observed
        s = self.state["markets"].get(slug)
        if s is None or s["status"] != "FUNDED" or observed >= s["end"]:
            return
        condition = s["condition"]
        ep = self.state["episodes"].get(condition)
        valid = book.get("tokenId") == s["yes_token"]
        try:
            yes_asks, no_asks = levels(book, "YES"), levels(book, "NO")
            if not yes_asks or not no_asks or yes_asks[0][0] + no_asks[0][0] < 1:
                valid = False
        except (ValueError, KeyError, TypeError, ArithmeticError):
            valid = False
        if not valid:
            for name, action in (ep or {}).get("variants", {}).items():
                if action["status"] == "PENDING" and request_at >= action["eligible_after"]:
                    action.update(status="SKIP", reason="INVALID_EXECUTION_BOOK")
                    self.emit("paper_execution", condition=condition, variant=name, action=action)
            return
        if ep is None:
            midpoint = s["start"] + 1800
            if observed < midpoint:
                return
            if observed > midpoint + 60:
                self.state["episodes"][condition] = {"slug": slug, "condition": condition,
                    "start": s["start"], "phase": "holdout" if observed >= HOLDOUT else "discovery",
                    "status": "SKIP", "reason": "MISSED_DECISION_WINDOW", "variants": {}}
                return
            try:
                p, sigma, reference, ref_at = self._inputs(s, observed)
                # Validate both sides before establishing a decision.
                levels(book, "YES"); levels(book, "NO")
            except (ValueError, TypeError, KeyError, ArithmeticError) as error:
                self.emit("paper_input_skip", condition=condition, reason=str(error))
                return
            ep = {"condition": condition, "slug": slug, "symbol": s["symbol"], "start": s["start"],
                  "decision_at": observed, "phase": "holdout" if observed >= HOLDOUT else "discovery",
                  "p_up": p, "sigma_1m": sigma, "reference_price": reference,
                  "reference_observed_at": ref_at, "opening": s["opening"], "variants": {}}
            for name, prob in (("model", p), ("constant50", .5)):
                choices = []
                for side, chance in (("YES", prob), ("NO", 1 - prob)):
                    cap = Decimal(str(chance)) * (1 - FEE) / (1 + HURDLE)
                    if cap <= 0:
                        continue
                    shares = (BUDGET / cap).quantize(MICRO, rounding=ROUND_DOWN)
                    simulated = fill(book, side, cap, shares)
                    if simulated:
                        edge = float(Decimal(simulated["net_shares"]) * Decimal(str(chance)) / Decimal(simulated["cost_usdc"]) - 1)
                        choices.append((edge, side, cap, shares))
                if not choices:
                    ep["variants"][name] = {"status": "NO_TRADE", "reason": "NO_EXECUTABLE_EDGE"}
                else:
                    _, side, cap, shares = max(choices, key=lambda x: (x[0], x[1]))
                    ep["variants"][name] = {"status": "PENDING", "side": side,
                        "max_price": str(cap), "size_cap_shares": str(shares),
                        "eligible_after": observed + s["delay_s"], "expires_at": observed + 30}
            self.state["episodes"][condition] = ep
            self.emit("paper_decision", condition=condition, episode=ep)
            return  # never execute on the decision snapshot
        for name, action in ep.get("variants", {}).items():
            if action["status"] != "PENDING" or request_at < action["eligible_after"]:
                continue
            if observed > action["expires_at"]:
                action.update(status="SKIP", reason="EXECUTION_OBSERVATION_TOO_LATE")
            else:
                try:
                    result = fill(book, action["side"], Decimal(action["max_price"]), Decimal(action["size_cap_shares"]))
                except (ValueError, KeyError, TypeError, ArithmeticError):
                    result = None
                if result is None:
                    action.update(status="SKIP", reason="DEPTH_OR_PRICE_BOUND_FAILED")
                else:
                    action.update(status="FILLED", fill_at=observed, **result)
            self.emit("paper_execution", condition=condition, variant=name, action=action)

    def report(self):
        result = {"version": VERSION, "status": "PAPER_ONLY_NOT_LIVE", "phases": {},
                  "assumptions": ["3% buy fee in contracts", "Observed REST depth is assumed executable at receipt",
                      "Queue, matching races and REST cache staleness are not reproduced",
                      "No portfolio funding/capital lockup model; 10 USDC cap per condition and variant"]}
        for phase in ("discovery", "holdout"):
            eps = [e for e in self.state["episodes"].values() if e["phase"] == phase]
            scored = [e for e in eps if "brier_model" in e]
            report = {"conditions_seen": len(eps), "decision_conditions": sum("decision_at" in e for e in eps),
                "hour_clusters": len({e["start"] for e in eps}), "scored_conditions": len(scored),
                "brier_model": statistics.mean(e["brier_model"] for e in scored) if scored else None,
                "brier_50": .25 if scored else None,
                "skips": dict(Counter(e.get("reason") for e in eps if e.get("reason"))),
                "no_trade_control_pnl_usdc": 0, "variants": {}}
            for name in ("model", "constant50"):
                actions = [e["variants"][name] for e in eps if name in e.get("variants", {})]
                settled = [a for a in actions if a["status"] == "SETTLED"]
                costs = sum(float(a["cost_usdc"]) for a in settled)
                pnl = sum(float(a["pnl_usdc"]) for a in settled)
                report["variants"][name] = {"states": dict(Counter(a["status"] for a in actions)),
                    "settled_trades": len(settled), "net_pnl_usdc": sum(float(a["pnl_usdc"]) for a in settled),
                    "settled_cost_usdc": costs, "net_return_on_spent": pnl / costs if costs else None,
                    "mean_pnl_per_settled_trade": pnl / len(settled) if settled else None}
            report["feasibility"] = ("REQUIRES_COVERAGE_REVIEW" if len(scored) >= 60 and
                                     len({e["start"] for e in scored}) >= 60 else "INSUFFICIENT_DATA")
            result["phases"][phase] = report
        return result


def archive_report(paths):
    """Reconcile cumulative checkpoints without double-counting daily/job reports."""
    import zipfile
    ordered = []
    for path in paths:
        with zipfile.ZipFile(path) as archive:
            if "state.json" not in archive.namelist():
                continue
            state = json.loads(archive.read("state.json")).get("paper")
            if state is not None:
                summary = json.loads(archive.read("summary.json"))
                ordered.append((summary["ended_at"], state))
    combined = {"version": VERSION, "markets": {}, "episodes": {}}
    conflicts = set()
    for _, state in sorted(ordered, key=lambda x: x[0]):
        if state.get("version") != VERSION:
            raise ValueError("INCOMPATIBLE_PAPER_STATE")
        for key, ep in state["episodes"].items():
            existing = combined["episodes"].get(key)
            if existing and existing.get("decision_at") and ep.get("decision_at"):
                identity = lambda e: (e["decision_at"], e["p_up"], e["opening"])
                if identity(existing) != identity(ep):
                    conflicts.add(key)
                    continue
            if existing and existing.get("decision_at") and not ep.get("decision_at"):
                continue
            combined["episodes"][key] = ep
    for key in conflicts:
        combined["episodes"].pop(key, None)
    result = HourlyPaper(combined).report()
    result.update(archive_checkpoints=len(ordered), excluded_conflicting_conditions=sorted(conflicts))
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("state", nargs="+")
    parser.add_argument("--out", default="limitless_hourly_report.json")
    args = parser.parse_args()
    if all(path.endswith(".zip") for path in args.state):
        result = archive_report(args.state)
    elif len(args.state) == 1:
        state = json.load(open(args.state[0])).get("paper")
        result = HourlyPaper(state).report()
    else:
        parser.error("Use one state JSON or one or more ZIP captures")
    with open(args.out, "w") as file:
        json.dump(result, file, indent=2)
    print(json.dumps(result))
