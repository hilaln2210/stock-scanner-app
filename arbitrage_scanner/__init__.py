"""
Prediction-market arbitrage scanner (educational, paper trading only).
No real money, no API keys, no wallet integration.
"""

from .config import Config, ScannerFilters, RiskControls, SimulatorConfig
from .models import (
    BinaryMarket,
    MultiOutcomeMarket,
    ArbitrageOpportunity,
    MarketType,
    Outcome,
)
from .scanner import Scanner
from .simulator import PaperTradingSimulator
from .risk import RiskManager

__all__ = [
    "Config",
    "ScannerFilters",
    "RiskControls",
    "SimulatorConfig",
    "BinaryMarket",
    "MultiOutcomeMarket",
    "ArbitrageOpportunity",
    "MarketType",
    "Outcome",
    "Scanner",
    "PaperTradingSimulator",
    "RiskManager",
]
