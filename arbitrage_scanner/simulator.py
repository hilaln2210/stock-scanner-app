"""
Paper-trading simulator: virtual balance, simulated positions, PnL tracking.
No real orders, no wallet, no API keys.
"""

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import List

from .config import Config
from .models import ArbitrageOpportunity
from .risk import RiskManager, PositionRecord

logger = logging.getLogger(__name__)


@dataclass
class SimulatedEntry:
    """Record of a simulated entry into an arbitrage."""

    market_id: str
    question: str
    capital_used: float
    expected_profit_pct: float
    entry_date: date


@dataclass
class SimulatedExit:
    """Record of a simulated exit (realized PnL)."""

    market_id: str
    capital_used: float
    realized_pnl: float
    realized_pnl_pct: float
    exit_date: date
    fee_estimate: float = 0.0  # עמלות משוערות (אופציונלי)


class PaperTradingSimulator:
    """
    Simulates arbitrage entries and exits with a virtual balance.
    Tracks open positions, entries, exits, and total PnL.
    """

    def __init__(self, config: Config) -> None:
        self.initial_balance = config.simulator.initial_balance
        self._balance = config.simulator.initial_balance
        self._risk = RiskManager(config.simulator.risk)
        self._open_positions: List[PositionRecord] = []
        self._entries: List[SimulatedEntry] = []
        self._exits: List[SimulatedExit] = []
        self._daily_start_balance = self.initial_balance
        self._daily_start_date: date | None = None

    @property
    def balance(self) -> float:
        return self._balance

    @property
    def open_positions(self) -> List[PositionRecord]:
        return list(self._open_positions)

    @property
    def entries(self) -> List[SimulatedEntry]:
        return list(self._entries)

    @property
    def exits(self) -> List[SimulatedExit]:
        return list(self._exits)

    def total_realized_pnl(self) -> float:
        """Sum of all realized PnL from exits."""
        return sum(e.realized_pnl for e in self._exits)

    def total_pnl(self) -> float:
        """Current balance minus initial balance (includes unrealized)."""
        return self._balance - self.initial_balance

    def total_pnl_pct(self) -> float:
        """Total PnL as percentage of initial balance."""
        if self.initial_balance <= 0:
            return 0.0
        return (self._balance - self.initial_balance) / self.initial_balance * 100.0

    def _equity(self) -> float:
        """Current equity = balance + capital tied in open positions."""
        return self._balance + sum(p.capital_used for p in self._open_positions)

    def _ensure_daily_start(self, d: date) -> None:
        """Set start-of-day equity if we're on a new day."""
        if self._daily_start_date != d:
            self._daily_start_date = d
            self._daily_start_balance = self._equity()
            self._risk.set_daily_start(self._daily_start_balance, d)

    def try_enter(
        self, opportunity: ArbitrageOpportunity, as_of_date: date | None = None
    ) -> tuple[bool, str]:
        """
        Try to open a simulated position. Returns (success, message).
        Size is capped by risk controls.
        """
        d = as_of_date or date.today()
        self._ensure_daily_start(d)

        trade_size = min(
            opportunity.liquidity,
            self._risk.max_trade_size(),
            self._balance,
        )
        if trade_size <= 0:
            return False, "Insufficient balance or zero size"

        allowed, reason = self._risk.can_open_trade(
            self._equity(), self._open_positions, trade_size, d
        )
        if not allowed:
            return False, reason

        self._balance -= trade_size
        pos = PositionRecord(
            market_id=opportunity.market_id,
            capital_used=trade_size,
            entry_date=d,
            expected_profit_pct=opportunity.expected_profit_pct,
        )
        self._open_positions.append(pos)
        self._entries.append(
            SimulatedEntry(
                market_id=opportunity.market_id,
                question=opportunity.question,
                capital_used=trade_size,
                expected_profit_pct=opportunity.expected_profit_pct,
                entry_date=d,
            )
        )
        logger.info(
            "Simulated ENTRY: %s | size=%.2f | edge=%.2f%%",
            opportunity.market_id,
            trade_size,
            opportunity.expected_profit_pct,
        )
        return True, ""

    def close_position(self, market_id: str, as_of_date: date | None = None) -> bool:
        """
        Close a simulated position: realize PnL at expected profit %.
        Returns True if a position was found and closed.
        """
        d = as_of_date or date.today()
        for i, pos in enumerate(self._open_positions):
            if pos.market_id == market_id:
                self._open_positions.pop(i)
                # Simulate realized PnL at expected rate (simplified: we assume we get the edge)
                realized_pnl = pos.capital_used * (pos.expected_profit_pct / 100.0)
                realized_pct = pos.expected_profit_pct
                self._balance += pos.capital_used + realized_pnl
                # עמלה משוערת: כ־0.5% מהון (דמו; במסחר אמיתי יגיע מהפלטפורמה)
                fee_estimate = round(pos.capital_used * 0.005, 2)
                self._exits.append(
                    SimulatedExit(
                        market_id=market_id,
                        capital_used=pos.capital_used,
                        realized_pnl=realized_pnl,
                        realized_pnl_pct=realized_pct,
                        exit_date=d,
                        fee_estimate=fee_estimate,
                    )
                )
                logger.info(
                    "Simulated EXIT: %s | pnl=%.2f (%.2f%%)",
                    market_id,
                    realized_pnl,
                    realized_pct,
                )
                return True
        return False

    def reset(self) -> None:
        """Reset simulator to initial state (for testing or new run)."""
        self._balance = self.initial_balance
        self._open_positions.clear()
        self._entries.clear()
        self._exits.clear()
        self._daily_start_balance = self.initial_balance
        self._daily_start_date = None
