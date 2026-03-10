"""Unit tests for models."""

import pytest
from arbitrage_scanner.models import (
    BinaryMarket,
    MultiOutcomeMarket,
    Outcome,
    MarketType,
    ArbitrageOpportunity,
)


def test_binary_total_price() -> None:
    m = BinaryMarket("id", "Q?", 0.45, 0.52, 1000.0)
    assert m.total_price() == 0.97


def test_binary_is_arbitrage() -> None:
    m_arb = BinaryMarket("id", "Q?", 0.45, 0.52, 1000.0)
    assert m_arb.is_arbitrage() is True
    m_no = BinaryMarket("id", "Q?", 0.55, 0.50, 1000.0)
    assert m_no.is_arbitrage() is False


def test_binary_locked_profit_pct() -> None:
    m = BinaryMarket("id", "Q?", 0.45, 0.52, 1000.0)  # total 0.97
    # (1 - 0.97) / 0.97 * 100 ≈ 3.09
    assert 3.0 < m.locked_profit_pct() < 3.2


def test_binary_locked_profit_zero_when_no_arbitrage() -> None:
    m = BinaryMarket("id", "Q?", 0.55, 0.50, 1000.0)
    assert m.locked_profit_pct() == 0.0


def test_multi_outcome_total_and_arbitrage() -> None:
    outcomes = [
        Outcome("A", "A", 0.32, 1000),
        Outcome("B", "B", 0.33, 1000),
        Outcome("C", "C", 0.30, 1000),
    ]
    m = MultiOutcomeMarket("mid", "Q?", outcomes)
    assert m.total_price() == 0.95
    assert m.is_structural_arbitrage() is True
    assert m.locked_profit_pct() > 5.0  # (1-0.95)/0.95*100 ≈ 5.26


def test_multi_outcome_no_arbitrage_when_sum_one() -> None:
    outcomes = [
        Outcome("P", "P", 0.34, 1000),
        Outcome("Q", "Q", 0.33, 1000),
        Outcome("R", "R", 0.33, 1000),
    ]
    m = MultiOutcomeMarket("mid", "Q?", outcomes)
    assert m.total_price() == 1.0
    assert m.is_structural_arbitrage() is False
    assert m.locked_profit_pct() == 0.0


def test_arbitrage_opportunity_fields() -> None:
    b = BinaryMarket("bid", "Q?", 0.48, 0.50, 5000.0)
    o = ArbitrageOpportunity(
        market_id="bid",
        market_type=MarketType.BINARY,
        question="Q?",
        expected_profit_pct=2.04,
        total_cost=0.98,
        liquidity=5000.0,
        raw_market=b,
    )
    assert o.market_id == "bid"
    assert o.market_type == MarketType.BINARY
    assert o.expected_profit_pct == 2.04
