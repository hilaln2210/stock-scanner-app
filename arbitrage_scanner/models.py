"""
Data models for prediction markets (binary and multi-outcome).
Educational / mock data only; no real market integration.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MarketType(str, Enum):
    """Type of prediction market."""

    BINARY = "binary"
    MULTI_OUTCOME = "multi_outcome"


@dataclass
class BinaryMarket:
    """A binary market with YES and NO outcomes (prices in [0, 1])."""

    market_id: str
    question: str
    yes_price: float
    no_price: float
    liquidity: float  # total volume / depth for sizing
    spread_bps: float = 0.0  # bid-ask spread in basis points
    source: str = "polymarket"  # פלטפורמה: polymarket, kalshi, manifold, predictit

    def total_price(self) -> float:
        """YES + NO price; arbitrage exists when < 1.0."""
        return self.yes_price + self.no_price

    def is_arbitrage(self) -> bool:
        """True if buying both YES and NO costs less than 1 (guaranteed payoff)."""
        return self.total_price() < 1.0

    def locked_profit_pct(self) -> float:
        """
        Expected locked profit as percentage.
        If total_price < 1, you pay total_price and receive 1 → profit = (1 - total) / total * 100.
        """
        if self.total_price() <= 0:
            return 0.0
        if self.total_price() >= 1.0:
            return 0.0
        return (1.0 - self.total_price()) / self.total_price() * 100.0


@dataclass
class Outcome:
    """Single outcome in a multi-outcome market."""

    outcome_id: str
    name: str
    price: float
    liquidity: float


@dataclass
class MultiOutcomeMarket:
    """Market with mutually exclusive outcomes (e.g. A, B, C); sum of prices should be 1."""

    market_id: str
    question: str
    outcomes: list[Outcome] = field(default_factory=list)

    def total_price(self) -> float:
        """Sum of all outcome prices."""
        return sum(o.price for o in self.outcomes)

    def is_structural_arbitrage(self) -> bool:
        """True if sum of outcome prices < 1 (buy all outcomes for less than 1)."""
        return self.total_price() < 1.0

    def locked_profit_pct(self) -> float:
        """Profit % if you buy all outcomes: (1 - total) / total * 100."""
        t = self.total_price()
        if t <= 0 or t >= 1.0:
            return 0.0
        return (1.0 - t) / t * 100.0


@dataclass
class ArbitrageOpportunity:
    """Detected arbitrage opportunity (binary or multi-outcome)."""

    market_id: str
    market_type: MarketType
    question: str
    expected_profit_pct: float
    total_cost: float  # cost to buy all sides
    liquidity: float
    raw_market: Any  # BinaryMarket or MultiOutcomeMarket
