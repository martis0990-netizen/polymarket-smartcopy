"""Causal, read-only structure labels for prospective Limitless 15m decisions.

The caller must supply a verified capture manifest and the decision-time Binance
MinuteStore. This module does not infer a trade from a chart label.
"""

import collections
import math

from limitless_market_regime import describe

VERSION = "limitless-15m-structure-label-v2"
ALLOWED = {"TREND_UP", "TREND_DOWN", "RANGE", "TRANSITION", "UNKNOWN"}


def label_decision(store, *, condition, symbol, open_ms, decision_ms):
    """Label one condition using observations received no later than decision_ms.

    An unavailable H1 state stays UNKNOWN. H4 is reported separately and cannot
    silently become a prerequisite or a lower-timeframe substitute.
    """
    if not isinstance(condition, str) or not condition:
        raise ValueError("missing condition")
    if symbol not in ("BTCUSDT", "ETHUSDT"):
        raise ValueError("unsupported symbol")
    if any(isinstance(x, bool) or not isinstance(x, (int, float))
           or not math.isfinite(x) for x in (open_ms, decision_ms)):
        raise ValueError("invalid time")
    if open_ms % 900_000 or not open_ms <= decision_ms < open_ms + 900_000:
        raise ValueError("decision outside 15m market")
    rows, conflicts = store.view(symbol, decision_ms)
    # MinuteStore excludes conflicting minutes from rows. UTC aggregation then
    # restarts at that gap and requires a fresh contiguous warmup. Passing every
    # historical conflict to the hourly diagnostic would permanently mark all
    # frames UNKNOWN even after the affected minute has left the current suffix.
    # The conflict ledger remains visible below; no disputed candle is used.
    snapshot = describe(rows, [], decision_ms)
    frames = snapshot["frames"]
    if any(frames[f]["state"] not in ALLOWED for f in ("H4", "H1", "M15", "M5", "M1")):
        raise ValueError("unexpected regime state")
    return {
        "version": VERSION,
        "condition": condition,
        "symbol": symbol,
        "open_ms": open_ms,
        "decision_ms": decision_ms,
        "h1_state": frames["H1"]["state"],
        "h1_reason": frames["H1"]["reason"],
        "h4_state": frames["H4"]["state"],
        "h4_reason": frames["H4"]["reason"],
        "m15_state": frames["M15"]["state"],
        "m5_state": frames["M5"]["state"],
        "m1_state": frames["M1"]["state"],
        "h1_m15_relation": snapshot["h1_m15_relation"],
        "minute_view_sha256": snapshot["minute_view_sha256"],
        "conflicting_minutes": conflicts,
        "ready_h1": frames["H1"]["state"] != "UNKNOWN",
        "ready_full_h4_h1": snapshot["top_down_context"] == "READY",
        "frames": frames,
    }


def coverage(labels):
    """Keep every condition, including UNKNOWN and both assets in one UTC slot."""
    seen = set()
    rows = list(labels)
    for row in rows:
        if row["condition"] in seen:
            raise ValueError("duplicate condition")
        seen.add(row["condition"])
        if row["version"] != VERSION:
            raise ValueError("mixed label versions")
    clusters = {row["open_ms"] for row in rows}
    return {
        "version": VERSION,
        "conditions": len(rows),
        "quarter_hour_clusters": len(clusters),
        "h1_known": sum(row["ready_h1"] for row in rows),
        "full_h4_h1_ready": sum(row["ready_full_h4_h1"] for row in rows),
        "h1_states": dict(collections.Counter(row["h1_state"] for row in rows)),
        "h1_unknown_reasons": dict(collections.Counter(
            row["h1_reason"] for row in rows if not row["ready_h1"])),
        "status": ("INSUFFICIENT_DATA" if not rows or not any(row["ready_h1"] for row in rows)
                   else "DESCRIPTIVE_ONLY"),
    }


def structural_gate(label, side):
    """Frozen narrow shadow gate. A label never creates a trade on its own."""
    if label["version"] != VERSION or side not in ("YES", "NO"):
        raise ValueError("invalid label or side")
    desired = "UP" if side == "YES" else "DOWN"
    if label["h1_state"] == "UNKNOWN":
        return "SKIP_H1_UNKNOWN"
    if label["h1_state"] != "TREND_" + desired:
        return "SKIP_H1_NOT_ALIGNED"
    if label["m5_state"] == "UNKNOWN":
        return "SKIP_M5_UNKNOWN"
    breaks = [event for event in label["frames"]["M5"]["recent_events"]
              if event["kind"] == "SWING_CLOSE_BREAK"]
    if not breaks:
        return "SKIP_NO_M5_BREAK"
    last = breaks[-1]
    if (last["available_ms"] > label["decision_ms"]
            or last["bar_close_ms"] > label["decision_ms"]):
        raise ValueError("future break leaked")
    if label["decision_ms"] - last["available_ms"] > 300_000:
        return "SKIP_STALE_M5_BREAK"
    if last["direction"] != desired:
        return "SKIP_M5_BREAK_OPPOSED"
    return "ALLOW"
