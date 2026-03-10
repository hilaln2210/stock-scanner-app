"""Unit tests for paper-trading simulator."""

import pytest
from datetime import date

from arbitrage_scanner.config import Config
from arbitrage_scanner.models import ArbitrageOpportunity, MarketType, BinaryMarket
from arbitrage_scanner.simulator import PaperTradingSimulator


def _make_opportunity(market_id: str, profit_pct: float, liquidity: float = 5000.0) -> ArbitrageOpportunity:
    return ArbitrageOpportunity(
        market_id=market_id,
        market_type=MarketType.BINARY,
        question="Test?",
        expected_profit_pct=profit_pct,
        total_cost=0.97,
        liquidity=liquidity,
        raw_market=BinaryMarket(market_id, "Test?", 0.48, 0.49, liquidity),
    )


def test_simulator_initial_balance() -> None:
    config = Config()
    config.simulator.initial_balance = 10000.0
    sim = PaperTradingSimulator(config)
    assert sim.balance == 10000.0
    assert sim.total_pnl() == 0.0


def test_simulator_enter_reduces_balance() -> None:
    config = Config()
    config.simulator.initial_balance = 10000.0
    config.simulator.risk.max_capital_per_trade = 1000.0
    sim = PaperTradingSimulator(config)
    opp = _make_opportunity("m1", 3.0)
    ok, _ = sim.try_enter(opp, as_of_date=date(2025, 1, 1))
    assert ok is True
    assert sim.balance == 10000.0 - 1000.0  # capped at max_capital_per_trade
    assert len(sim.open_positions) == 1


def test_simulator_exit_realizes_pnl() -> None:
    config = Config()
    config.simulator.initial_balance = 10000.0
    config.simulator.risk.max_capital_per_trade = 1000.0
    sim = PaperTradingSimulator(config)
    opp = _make_opportunity("m1", 5.0)
    sim.try_enter(opp, as_of_date=date(2025, 1, 1))
    before = sim.balance
    found = sim.close_position("m1", as_of_date=date(2025, 1, 2))
    assert found is True
    assert sim.balance == before + 1000.0 + 1000.0 * 0.05  # capital + 5% profit
    assert sim.total_realized_pnl() == 50.0


def test_simulator_reset() -> None:
    config = Config()
    sim = PaperTradingSimulator(config)
    sim.try_enter(_make_opportunity("m1", 2.0), as_of_date=date(2025, 1, 1))
    sim.reset()
    assert sim.balance == config.simulator.initial_balance
    assert len(sim.open_positions) == 0
    assert len(sim.entries) == 0
    assert len(sim.exits) == 0


def test_simulator_close_nonexistent_returns_false() -> None:
    sim = PaperTradingSimulator(Config())
    assert sim.close_position("nonexistent") is False
