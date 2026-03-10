"""Unit tests for scanner."""

import pytest
from pathlib import Path

from arbitrage_scanner.config import Config, ScannerFilters
from arbitrage_scanner.scanner import Scanner
from arbitrage_scanner.models import BinaryMarket, MarketType


def test_scanner_detects_binary_arbitrage() -> None:
    config = Config()
    config.filters = ScannerFilters(min_liquidity=0, max_spread_bps=10000, min_expected_edge_pct=0)
    scanner = Scanner(config)
    markets = [
        BinaryMarket("1", "Q1", 0.45, 0.52, 1000, 50),
        BinaryMarket("2", "Q2", 0.55, 0.50, 1000, 50),
    ]
    opps = scanner.scan_binary(markets)
    assert len(opps) == 1
    assert opps[0].market_id == "1"
    assert opps[0].market_type == MarketType.BINARY


def test_scanner_filters_low_liquidity() -> None:
    config = Config()
    config.filters = ScannerFilters(min_liquidity=5000, max_spread_bps=10000, min_expected_edge_pct=0)
    scanner = Scanner(config)
    markets = [BinaryMarket("1", "Q", 0.45, 0.52, 100, 50)]
    opps = scanner.scan_binary(markets)
    assert len(opps) == 0


def test_scanner_filters_min_edge() -> None:
    config = Config()
    config.filters = ScannerFilters(min_liquidity=0, max_spread_bps=10000, min_expected_edge_pct=10.0)
    scanner = Scanner(config)
    # 0.45+0.52=0.97 -> edge ~3.09%
    markets = [BinaryMarket("1", "Q", 0.45, 0.52, 1000, 50)]
    opps = scanner.scan_binary(markets)
    assert len(opps) == 0


def test_scanner_run_loads_json(data_dir: Path) -> None:
    config = Config()
    config.data_dir = data_dir
    config.data_source = "mock"
    scanner = Scanner(config)
    opps = scanner.run(
        binary_path=data_dir / "binary_markets.json",
        multi_path=data_dir / "multi_outcome_markets.json",
        data_source="mock",
    )
    # From sample data: binary has arb in bin-003, bin-004; multi has in multi-001, multi-002
    # Filters may exclude some (liquidity, spread, edge)
    assert len(opps) >= 1


def test_scanner_misses_no_arbitrage_with_relaxed_filters(data_dir: Path) -> None:
    """With filters fully relaxed, every market with sum<1 must be found (no missed opportunities)."""
    config = Config()
    config.filters = ScannerFilters(min_liquidity=0, max_spread_bps=100_000, min_expected_edge_pct=0)
    scanner = Scanner(config)
    opps = scanner.run(
        binary_path=data_dir / "binary_markets.json",
        multi_path=data_dir / "multi_outcome_markets.json",
        data_source="mock",
    )
    # binary_markets: bin-001..004 and bin-006 have yes+no<1 (5). bin-005 has 1.05 -> no.
    # multi: multi-001 (0.95), multi-002 (0.95) have sum<1 (2). multi-003 sum=1 -> no.
    binary_ids = {o.market_id for o in opps if o.market_type == MarketType.BINARY}
    multi_ids = {o.market_id for o in opps if o.market_type == MarketType.MULTI_OUTCOME}
    assert binary_ids >= {"bin-001", "bin-002", "bin-003", "bin-004", "bin-006"}
    assert multi_ids >= {"multi-001", "multi-002"}
    assert len(opps) == 7


def test_scanner_binary_boundary() -> None:
    """Markets with total just below 1 are detected; total >= 1 are not."""
    config = Config()
    config.filters = ScannerFilters(min_liquidity=0, max_spread_bps=100_000, min_expected_edge_pct=0)
    scanner = Scanner(config)
    # 0.99 < 1 -> arb
    m_arb = BinaryMarket("a", "Q", 0.49, 0.50, 1000, 0)
    assert m_arb.is_arbitrage() is True
    opps = scanner.scan_binary([m_arb])
    assert len(opps) == 1
    # 1.0 exactly -> no arb
    m_no = BinaryMarket("b", "Q", 0.50, 0.50, 1000, 0)
    assert m_no.is_arbitrage() is False
    opps_no = scanner.scan_binary([m_no])
    assert len(opps_no) == 0


@pytest.fixture
def data_dir() -> Path:
    return Path(__file__).parent.parent / "data"
