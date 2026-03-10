"""
Configuration for the prediction-market arbitrage scanner.
All settings are for paper trading and mock data only.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class ScannerFilters:
    """Configurable filters for opportunity detection."""

    min_liquidity: float = 100.0
    max_spread_bps: float = 500.0  # basis points, e.g. 500 = 5%
    min_expected_edge_pct: float = 0.0  # minimum profit % to consider (0 = don't miss small edges)


@dataclass
class RiskControls:
    """Risk limits for the paper-trading simulator."""

    max_capital_per_trade: float = 1000.0
    max_open_positions: int = 10
    max_daily_drawdown_pct: float = 10.0  # stop new trades if daily PnL drops by this %


@dataclass
class SimulatorConfig:
    """Paper-trading simulator settings."""

    initial_balance: float = 100.0
    risk: RiskControls = field(default_factory=RiskControls)


@dataclass
class Config:
    """Main configuration container."""

    data_dir: Path = field(default_factory=lambda: Path(__file__).parent / "data")
    filters: ScannerFilters = field(default_factory=ScannerFilters)
    simulator: SimulatorConfig = field(default_factory=SimulatorConfig)
    log_level: str = "INFO"
    # Data source: "polymarket" = שאלות אמיתיות מהשוק | "mock" = הדגמה (fallback)
    data_source: str = "polymarket"
    polymarket_gamma_url: str = "https://gamma-api.polymarket.com"
    polymarket_limit: int = 100  # events per page when fetching
    # סריקה אוטומטית ברקע: כל X שניות, מקור (all = כל הפלטפורמות)
    background_scan_interval_seconds: int = 90
    background_scan_source: str = "all"  # all | polymarket | kalshi | manifold | mock
    background_max_trades_per_cycle: int = 2

    def binary_markets_path(self) -> Path:
        """Path to binary markets JSON file."""
        return self.data_dir / "binary_markets.json"

    def multi_outcome_markets_path(self) -> Path:
        """Path to multi-outcome markets JSON file."""
        return self.data_dir / "multi_outcome_markets.json"
