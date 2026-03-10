"""
Risk controls for the paper-trading simulator.
Max capital per trade, max open positions, daily drawdown limit.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List

from .config import RiskControls

logger = logging.getLogger(__name__)


@dataclass
class PositionRecord:
    """A single open simulated position."""

    market_id: str
    capital_used: float
    entry_date: date
    expected_profit_pct: float


class RiskManager:
    """
    Enforces risk limits: max capital per trade, max open positions,
    and stop new trades when daily drawdown exceeds threshold.
    """

    def __init__(self, controls: RiskControls) -> None:
        self.controls = controls
        self._daily_start_balance: float = 0.0
        self._daily_start_date: date | None = None

    def set_daily_start(self, balance: float, as_of_date: date) -> None:
        """Set the balance at start of day for drawdown calculation."""
        self._daily_start_balance = balance
        self._daily_start_date = as_of_date

    def can_open_trade(
        self,
        balance: float,
        open_positions: List[PositionRecord],
        trade_size: float,
        current_date: date,
    ) -> tuple[bool, str]:
        """
        Returns (allowed, reason). If not allowed, reason explains why.
        """
        if trade_size > self.controls.max_capital_per_trade:
            return False, f"Trade size {trade_size} exceeds max {self.controls.max_capital_per_trade}"

        if len(open_positions) >= self.controls.max_open_positions:
            return False, f"Max open positions {self.controls.max_open_positions} reached"

        # Daily drawdown: compare current balance to start-of-day balance
        if self._daily_start_date is not None and current_date == self._daily_start_date:
            if self._daily_start_balance > 0:
                drawdown_pct = (self._daily_start_balance - balance) / self._daily_start_balance * 100
                if drawdown_pct >= self.controls.max_daily_drawdown_pct:
                    return (
                        False,
                        f"Daily drawdown {drawdown_pct:.1f}% >= max {self.controls.max_daily_drawdown_pct}%",
                    )

        return True, ""

    def max_trade_size(self) -> float:
        """Maximum capital allowed per single trade."""
        return self.controls.max_capital_per_trade
