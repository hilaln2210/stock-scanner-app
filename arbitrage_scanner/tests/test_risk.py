"""Unit tests for risk manager."""

import pytest
from datetime import date

from arbitrage_scanner.risk import RiskManager, PositionRecord
from arbitrage_scanner.config import RiskControls


def test_can_open_trade_respects_max_positions() -> None:
    controls = RiskControls(max_open_positions=2, max_capital_per_trade=1000.0)
    rm = RiskManager(controls)
    positions = [
        PositionRecord("m1", 500, date(2025, 1, 1), 3.0),
        PositionRecord("m2", 500, date(2025, 1, 1), 2.0),
    ]
    allowed, reason = rm.can_open_trade(10000.0, positions, 500.0, date(2025, 1, 1))
    assert allowed is False
    assert "positions" in reason.lower() or "max" in reason.lower()


def test_can_open_trade_respects_max_capital_per_trade() -> None:
    controls = RiskControls(max_capital_per_trade=500.0)
    rm = RiskManager(controls)
    allowed, reason = rm.can_open_trade(10000.0, [], 1000.0, date(2025, 1, 1))
    assert allowed is False
    assert "500" in reason or "exceeds" in reason.lower()


def test_can_open_trade_allows_valid_trade() -> None:
    controls = RiskControls(max_capital_per_trade=1000.0, max_open_positions=10)
    rm = RiskManager(controls)
    allowed, reason = rm.can_open_trade(10000.0, [], 500.0, date(2025, 1, 1))
    assert allowed is True
    assert reason == ""


def test_max_trade_size() -> None:
    controls = RiskControls(max_capital_per_trade=750.0)
    rm = RiskManager(controls)
    assert rm.max_trade_size() == 750.0


def test_daily_drawdown_blocks_new_trades() -> None:
    controls = RiskControls(
        max_capital_per_trade=1000.0,
        max_open_positions=10,
        max_daily_drawdown_pct=10.0,
    )
    rm = RiskManager(controls)
    rm.set_daily_start(10000.0, date(2025, 1, 1))
    # Current balance 8900 -> 11% drawdown
    allowed, reason = rm.can_open_trade(8900.0, [], 500.0, date(2025, 1, 1))
    assert allowed is False
    assert "drawdown" in reason.lower() or "10" in reason
