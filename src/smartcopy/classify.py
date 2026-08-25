from __future__ import annotations

import re
from dataclasses import dataclass

from .models import MarketFamily


_CRYPTO = re.compile(r"\b(bitcoin|btc|ethereum|eth|solana|sol|bnb|dogecoin|doge|xrp)\b", re.I)
_UPDOWN = re.compile(r"\b(up\s*(?:or|/)\s*down|updown)\b", re.I)
_FIVE = re.compile(r"(?:\b5\s*(?:m|min|mins|minute|minutes)\b|(?:^|[-_])5m(?:[-_]|$))", re.I)
_FIFTEEN = re.compile(r"(?:\b15\s*(?:m|min|mins|minute|minutes)\b|(?:^|[-_])15m(?:[-_]|$))", re.I)
_ONE_HOUR = re.compile(r"(?:\b1\s*(?:h|hr|hour)\b|(?:^|[-_])1h(?:[-_]|$))", re.I)
_THRESHOLD = re.compile(r"\b(above|below|reach|hit|dip|higher than|lower than|at least)\b", re.I)
_OVER_UNDER = re.compile(r"\b(over\s*/\s*under|over or under|o/u|total (?:goals|points|runs))\b", re.I)
_ESPORTS = re.compile(r"\b(counter[- ]?strike|cs2|dota\s*2|league of legends|lol|valorant)\b", re.I)
_FOOTBALL = re.compile(r"\b(premier league|champions league|la liga|serie a|bundesliga|football|soccer)\b", re.I)
_POLITICS = re.compile(r"\b(election|president|prime minister|democrat|republican|senate|governor)\b", re.I)


@dataclass(frozen=True, slots=True)
class MarketClassification:
    family: MarketFamily
    confidence: float
    reason: str


def classify_market(*, title: str | None, slug: str | None = None, event_slug: str | None = None) -> MarketClassification:
    text = " ".join(part for part in (title, slug, event_slug) if part)
    if not text:
        return MarketClassification(MarketFamily.UNKNOWN, 0.0, "no market text")

    if _CRYPTO.search(text) and _UPDOWN.search(text):
        if _FIVE.search(text):
            return MarketClassification(MarketFamily.CRYPTO_UPDOWN_5M, 1.0, "explicit crypto up/down 5m marker")
        if _FIFTEEN.search(text):
            return MarketClassification(MarketFamily.CRYPTO_UPDOWN_15M, 1.0, "explicit crypto up/down 15m marker")
        if _ONE_HOUR.search(text):
            return MarketClassification(MarketFamily.CRYPTO_UPDOWN_1H, 0.95, "explicit crypto up/down 1h marker")
        return MarketClassification(MarketFamily.UNKNOWN, 0.45, "crypto up/down detected but horizon is not explicit")

    if _CRYPTO.search(text) and _THRESHOLD.search(text):
        return MarketClassification(MarketFamily.CRYPTO_PRICE_THRESHOLD, 0.9, "crypto threshold language")
    if _ESPORTS.search(text):
        return MarketClassification(MarketFamily.ESPORTS_MATCH_WINNER, 0.85, "esports title marker")
    if _OVER_UNDER.search(text):
        return MarketClassification(MarketFamily.SPORTS_OVER_UNDER, 0.8, "over/under market language")
    if _FOOTBALL.search(text):
        return MarketClassification(MarketFamily.FOOTBALL_MATCH_WINNER, 0.65, "football market marker")
    if _POLITICS.search(text):
        return MarketClassification(MarketFamily.POLITICS_LONG_DATED, 0.6, "politics marker; horizon unverified")
    return MarketClassification(MarketFamily.UNKNOWN, 0.0, "no supported deterministic rule matched")
