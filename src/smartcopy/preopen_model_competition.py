"""Frozen strict-prior signal primitives for Bonereaper pre-open model competition v4."""

from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Any, Sequence

from smartcopy.external_signal import BinanceKline

_SCHEMA = "smartcopy-bonereaper-preopen-model-competition-v4"
_CONTRACT_COMMIT = "70d6772a5f8ea671f2b2477509d957d25a1d2360"
_CANDIDATES = ("MOM15", "SUPERTREND_HTF_10_3", "BOS_HTF_2", "ORACLE_FV")


@dataclass(frozen=True, slots=True)
class OracleFairValue:
    direction: str
    p_up: float
    z: float
    corrected_spot: float
    chainlink_anchor: float
    basis_median: float
    sigma_second: float


def momentum_15s(bars: Sequence[BinanceKline], *, source_second: int) -> float | None:
    """Strict-pre close return from t-16 to t-1, requiring exact one-second bars."""

    by_second = {bar.open_time_ms // 1_000: bar for bar in bars}
    earlier = by_second.get(source_second - 16)
    current = by_second.get(source_second - 1)
    if earlier is None or current is None:
        return None
    value = math.log(current.close / earlier.close)
    return value if value != 0 else None


def supertrend_direction(
    bars: Sequence[BinanceKline],
    *,
    source_second: int,
    length: int = 10,
    multiplier: float = 3.0,
) -> str | None:
    """Canonical Wilder-ATR Supertrend on the last 100 fully closed bars."""

    if length != 10 or multiplier != 3.0:
        raise ValueError("v4 freezes Supertrend at length 10 and multiplier 3")
    eligible = _strict_closed(bars, source_second=source_second)[-100:]
    if len(eligible) < length:
        return None

    true_ranges: list[float] = []
    for index, bar in enumerate(eligible):
        if index == 0:
            true_ranges.append(bar.high - bar.low)
        else:
            previous_close = eligible[index - 1].close
            true_ranges.append(
                max(
                    bar.high - bar.low,
                    abs(bar.high - previous_close),
                    abs(bar.low - previous_close),
                )
            )

    atr = sum(true_ranges[:length]) / length
    first = eligible[length - 1]
    midpoint = (first.high + first.low) / 2
    final_upper = midpoint + multiplier * atr
    final_lower = midpoint - multiplier * atr
    trend = "Down" if first.close <= final_upper else "Up"

    for index in range(length, len(eligible)):
        bar = eligible[index]
        previous = eligible[index - 1]
        atr = ((length - 1) * atr + true_ranges[index]) / length
        midpoint = (bar.high + bar.low) / 2
        basic_upper = midpoint + multiplier * atr
        basic_lower = midpoint - multiplier * atr
        next_upper = (
            basic_upper
            if basic_upper < final_upper or previous.close > final_upper
            else final_upper
        )
        next_lower = (
            basic_lower
            if basic_lower > final_lower or previous.close < final_lower
            else final_lower
        )
        if trend == "Down" and bar.close > next_upper:
            trend = "Up"
        elif trend == "Up" and bar.close < next_lower:
            trend = "Down"
        final_upper, final_lower = next_upper, next_lower
    return trend


def bos_direction(
    bars: Sequence[BinanceKline],
    *,
    source_second: int,
    pivot_length: int = 2,
) -> str | None:
    """Persistent close-confirmed structure state from strict two-sided pivots."""

    if pivot_length != 2:
        raise ValueError("v4 freezes BOS pivot length at 2")
    eligible = _strict_closed(bars, source_second=source_second)[-100:]
    if len(eligible) < 2 * pivot_length + 2:
        return None
    latest_high: float | None = None
    latest_low: float | None = None
    state: str | None = None
    for current_index, bar in enumerate(eligible):
        pivot_index = current_index - pivot_length
        if pivot_index >= pivot_length:
            pivot = eligible[pivot_index]
            neighbors = eligible[pivot_index - pivot_length : pivot_index] + eligible[
                pivot_index + 1 : pivot_index + pivot_length + 1
            ]
            if len(neighbors) == 2 * pivot_length:
                if all(pivot.high > neighbor.high for neighbor in neighbors):
                    latest_high = pivot.high
                if all(pivot.low < neighbor.low for neighbor in neighbors):
                    latest_low = pivot.low
        breaks_high = latest_high is not None and bar.close > latest_high
        breaks_low = latest_low is not None and bar.close < latest_low
        if breaks_high and breaks_low:
            state = None
        elif breaks_high:
            state = "Up"
        elif breaks_low:
            state = "Down"
    return state


def oracle_fair_value(
    one_second_bars: Sequence[BinanceKline],
    chainlink_rows: Sequence[dict[str, Any]],
    *,
    source_second: int,
    market_end: int,
) -> OracleFairValue | None:
    """Compute the frozen basis-corrected Gaussian oracle-relative candidate."""

    if market_end <= source_second:
        return None
    by_second = {
        bar.open_time_ms // 1_000: bar
        for bar in one_second_bars
        if bar.open_time_ms // 1_000 < source_second
    }
    volatility_prices = [by_second.get(second) for second in range(source_second - 301, source_second)]
    if any(bar is None for bar in volatility_prices):
        return None
    prices = [bar.close for bar in volatility_prices if bar is not None]
    returns = [math.log(current / previous) for previous, current in zip(prices, prices[1:])]
    if len(returns) != 300:
        return None
    sigma = math.sqrt(sum(value * value for value in returns) / len(returns))
    if not math.isfinite(sigma) or sigma <= 0:
        return None

    ordered_chainlink = sorted(
        (
            (int(row["source_timestamp_ms"]), float(row.get("value_decimal", row.get("value"))))
            for row in chainlink_rows
            if int(row["source_timestamp_ms"]) < source_second * 1_000
        ),
        key=lambda item: item[0],
    )
    if not ordered_chainlink:
        return None
    anchor = ordered_chainlink[-1][1]
    if not math.isfinite(anchor) or anchor <= 0:
        return None

    basis_samples: list[float] = []
    chainlink_index = -1
    for second in range(source_second - 600, source_second - 60):
        bar = by_second.get(second)
        if bar is None:
            return None
        cutoff = second * 1_000
        while (
            chainlink_index + 1 < len(ordered_chainlink)
            and ordered_chainlink[chainlink_index + 1][0] < cutoff
        ):
            chainlink_index += 1
        if chainlink_index < 0:
            return None
        chainlink_value = ordered_chainlink[chainlink_index][1]
        if chainlink_value <= 0:
            return None
        basis_samples.append(math.log(bar.close / chainlink_value))
    if len(basis_samples) != 540:
        return None

    current = by_second.get(source_second - 1)
    if current is None:
        return None
    basis = median(basis_samples)
    corrected_spot = current.close * math.exp(-basis)
    tau = market_end - source_second
    z = math.log(corrected_spot / anchor) / (sigma * math.sqrt(tau))
    if not math.isfinite(z):
        return None
    p_up = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    direction = _direction(p_up - 0.5)
    if direction is None:
        return None
    return OracleFairValue(
        direction=direction,
        p_up=p_up,
        z=z,
        corrected_spot=corrected_spot,
        chainlink_anchor=anchor,
        basis_median=basis,
        sigma_second=sigma,
    )


def evaluate_preopen_candidates(
    *,
    label: str,
    source_second: int,
    market_end: int,
    one_second_bars: Sequence[BinanceKline],
    htf_bars: Sequence[BinanceKline],
    chainlink_rows: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    """Produce one condition row using only the frozen candidate definitions."""

    if label not in {"Up", "Down"}:
        raise ValueError("label must be Up or Down")
    momentum = momentum_15s(one_second_bars, source_second=source_second)
    oracle = oracle_fair_value(
        one_second_bars,
        chainlink_rows,
        source_second=source_second,
        market_end=market_end,
    )
    return {
        "label": label,
        "source_second": source_second,
        "MOM15": _direction(momentum) if momentum is not None else None,
        "MOM15_log_return": momentum,
        "SUPERTREND_HTF_10_3": supertrend_direction(
            htf_bars, source_second=source_second
        ),
        "BOS_HTF_2": bos_direction(htf_bars, source_second=source_second),
        "ORACLE_FV": oracle.direction if oracle else None,
        "ORACLE_FV_p_up": oracle.p_up if oracle else None,
        "ORACLE_FV_z": oracle.z if oracle else None,
        "ORACLE_FV_corrected_spot": oracle.corrected_spot if oracle else None,
        "ORACLE_FV_chainlink_anchor": oracle.chainlink_anchor if oracle else None,
        "ORACLE_FV_basis_median": oracle.basis_median if oracle else None,
        "ORACLE_FV_sigma_second": oracle.sigma_second if oracle else None,
    }


def summarize_model_competition(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Summarize frozen candidates and pairwise disagreement conditions."""

    candidate_summary: dict[str, Any] = {}
    for candidate in _CANDIDATES:
        values = [row for row in rows if row.get("label") and row.get(candidate) in {"Up", "Down"}]
        aligned = sum(row["label"] == row[candidate] for row in values)
        total = len(values)
        share = aligned / total if total else None
        lower = _wilson_lower(aligned, total) if total else None
        if total == 0:
            verdict = "INCONCLUSIVE"
        elif share is not None and share >= 0.65 and lower is not None and lower > 0.50:
            verdict = "SUPPORTED_DESCRIPTIVELY"
        elif share is not None and share <= 0.55:
            verdict = "NOT_SUPPORTED"
        else:
            verdict = "INCONCLUSIVE"
        candidate_summary[candidate] = {
            "eligible_conditions": total,
            "aligned_conditions": aligned,
            "alignment_share": share,
            "wilson_95_lower": lower,
            "verdict": verdict,
        }

    comparisons: dict[str, Any] = {}
    for left_index, left in enumerate(_CANDIDATES):
        for right in _CANDIDATES[left_index + 1 :]:
            discordant = [
                row
                for row in rows
                if row.get("label")
                and row.get(left) in {"Up", "Down"}
                and row.get(right) in {"Up", "Down"}
                and row[left] != row[right]
            ]
            left_wins = sum(row["label"] == row[left] for row in discordant)
            right_wins = sum(row["label"] == row[right] for row in discordant)
            total = len(discordant)
            left_share = left_wins / total if total else None
            right_share = right_wins / total if total else None
            winner = None
            if total < 10:
                verdict = "UNDERPOWERED_COMPARISON"
            elif left_share is not None and left_share >= 0.65 and left_share - right_share >= 0.20:
                verdict, winner = "DOMINANT_CANDIDATE", left
            elif right_share is not None and right_share >= 0.65 and right_share - left_share >= 0.20:
                verdict, winner = "DOMINANT_CANDIDATE", right
            else:
                verdict = "NO_DOMINANT_CANDIDATE"
            comparisons[f"{left}__vs__{right}"] = {
                "discordant_conditions": total,
                "left_wins": left_wins,
                "right_wins": right_wins,
                "winner": winner,
                "verdict": verdict,
            }

    return {
        "schema_version": _SCHEMA,
        "contract_commit": _CONTRACT_COMMIT,
        "study_status": "COLLECTING" if len(rows) < 30 else "STOPPING_RULE_REACHED",
        "eligible_conditions": len(rows),
        "target_conditions": 30,
        "candidates": candidate_summary,
        "pairwise_disagreements": comparisons,
    }


def _strict_closed(bars: Sequence[BinanceKline], *, source_second: int) -> list[BinanceKline]:
    cutoff_ms = source_second * 1_000
    return sorted(
        (bar for bar in bars if bar.close_time_ms < cutoff_ms),
        key=lambda bar: bar.open_time_ms,
    )


def _direction(value: float) -> str | None:
    if value > 0:
        return "Up"
    if value < 0:
        return "Down"
    return None


def _wilson_lower(successes: int, total: int, *, z: float = 1.959963984540054) -> float:
    if total <= 0:
        raise ValueError("Wilson interval requires a positive total")
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = proportion + z * z / (2 * total)
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total))
    return (centre - margin) / denominator
