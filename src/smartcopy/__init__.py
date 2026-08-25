"""Polymarket SmartCopy.

Evidence-gated selective copy-trading research. Live execution is not authorized.
"""

from .models import MarketFamily, StrategyArchetype, WatchlistStatus
from .polymarket import PolymarketDataAPI
from .wallets import ResearchEligibilityPolicy, WalletIntelligenceEngine

__all__ = [
    "MarketFamily",
    "PolymarketDataAPI",
    "ResearchEligibilityPolicy",
    "StrategyArchetype",
    "WalletIntelligenceEngine",
    "WatchlistStatus",
]

__version__ = "0.1.0"
