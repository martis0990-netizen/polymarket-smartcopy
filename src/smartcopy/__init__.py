"""Polymarket SmartCopy.

Evidence-gated selective copy-trading research. Live execution is not authorized.
"""

from .discovery import WalletCandidate, WalletDiscoveryService
from .intent import IntentClusteringPolicy, IntentReconstructor
from .models import MarketFamily, ObservationMode, StrategyArchetype, WatchlistStatus
from .polymarket import PolymarketDataAPI
from .wallets import ResearchEligibilityPolicy, WalletIntelligenceEngine

__all__ = [
    "IntentClusteringPolicy",
    "IntentReconstructor",
    "MarketFamily",
    "ObservationMode",
    "PolymarketDataAPI",
    "ResearchEligibilityPolicy",
    "StrategyArchetype",
    "WalletCandidate",
    "WalletDiscoveryService",
    "WalletIntelligenceEngine",
    "WatchlistStatus",
]

__version__ = "0.1.0"
