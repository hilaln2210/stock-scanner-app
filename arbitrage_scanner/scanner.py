"""
Scans mock market data for arbitrage opportunities.
Binary: yes_price + no_price < 1.0.
Multi-outcome: sum(outcome prices) < 1.0.
"""

import logging
from pathlib import Path
from typing import List

from .config import Config, ScannerFilters
from .models import (
    ArbitrageOpportunity,
    BinaryMarket,
    MarketType,
    MultiOutcomeMarket,
)
from .utils import load_binary_markets, load_multi_outcome_markets
from . import polymarket
from . import kalshi
from . import manifold

logger = logging.getLogger(__name__)


class Scanner:
    """
    Detects simple arbitrage and multi-outcome structural inconsistencies
    from JSON mock data. Applies configurable filters.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self.filters: ScannerFilters = config.filters

    def _passes_filters_binary(self, m: BinaryMarket) -> bool:
        """Check liquidity, spread, and minimum edge for a binary market."""
        if m.liquidity < self.filters.min_liquidity:
            return False
        if m.spread_bps > self.filters.max_spread_bps:
            return False
        if m.locked_profit_pct() < self.filters.min_expected_edge_pct:
            return False
        return True

    def _passes_filters_multi(self, m: MultiOutcomeMarket) -> bool:
        """Check min liquidity and min edge; use min outcome liquidity as proxy."""
        min_outcome_liquidity = min((o.liquidity for o in m.outcomes), default=0)
        if min_outcome_liquidity < self.filters.min_liquidity:
            return False
        if m.locked_profit_pct() < self.filters.min_expected_edge_pct:
            return False
        return True

    def scan_binary(self, markets: List[BinaryMarket]) -> List[ArbitrageOpportunity]:
        """Find binary arbitrage opportunities (yes + no < 1) that pass filters."""
        opportunities: List[ArbitrageOpportunity] = []
        for m in markets:
            if not m.is_arbitrage():
                continue
            if not self._passes_filters_binary(m):
                continue
            opportunities.append(
                ArbitrageOpportunity(
                    market_id=m.market_id,
                    market_type=MarketType.BINARY,
                    question=m.question,
                    expected_profit_pct=m.locked_profit_pct(),
                    total_cost=m.total_price(),
                    liquidity=m.liquidity,
                    raw_market=m,
                )
            )
        logger.info("Binary scan: %d opportunities (from %d markets)", len(opportunities), len(markets))
        return opportunities

    def scan_multi_outcome(
        self, markets: List[MultiOutcomeMarket]
    ) -> List[ArbitrageOpportunity]:
        """Find multi-outcome structural arbitrage (sum < 1) that pass filters."""
        opportunities: List[ArbitrageOpportunity] = []
        for m in markets:
            if not m.is_structural_arbitrage():
                continue
            if not self._passes_filters_multi(m):
                continue
            opportunities.append(
                ArbitrageOpportunity(
                    market_id=m.market_id,
                    market_type=MarketType.MULTI_OUTCOME,
                    question=m.question,
                    expected_profit_pct=m.locked_profit_pct(),
                    total_cost=m.total_price(),
                    liquidity=min((o.liquidity for o in m.outcomes), default=0),
                    raw_market=m,
                )
            )
        logger.info(
            "Multi-outcome scan: %d opportunities (from %d markets)",
            len(opportunities),
            len(markets),
        )
        return opportunities

    def run(
        self,
        binary_path: Path | None = None,
        multi_path: Path | None = None,
        data_source: str | None = None,
    ) -> List[ArbitrageOpportunity]:
        """
        Load markets from config data_source (polymarket or mock files) and return
        all opportunities that pass filters.
        """
        all_opps: List[ArbitrageOpportunity] = []
        source = (data_source or self.config.data_source or "").strip().lower()

        if source == "all":
            binary_all: List[BinaryMarket] = []
            try:
                binary_all.extend(polymarket.fetch_binary_markets(self.config))
            except Exception as e:
                logger.warning("Polymarket fetch failed: %s", e)
            try:
                binary_all.extend(kalshi.fetch_binary_markets(self.config))
            except Exception as e:
                logger.warning("Kalshi fetch failed: %s", e)
            try:
                binary_all.extend(manifold.fetch_binary_markets(500))
            except Exception as e:
                logger.warning("Manifold fetch failed: %s", e)
            all_opps.extend(self.scan_binary(binary_all))
        elif source == "polymarket":
            try:
                binary = polymarket.fetch_binary_markets(self.config)
                all_opps.extend(self.scan_binary(binary))
            except Exception as e:
                logger.exception("Polymarket fetch failed: %s", e)
                raise
            # Multi-outcome: Polymarket Gamma exposes mostly binary; skip file multi for this source
        elif source == "kalshi":
            try:
                binary = kalshi.fetch_binary_markets(self.config)
                all_opps.extend(self.scan_binary(binary))
            except Exception as e:
                logger.exception("Kalshi fetch failed: %s", e)
                raise
        elif source == "manifold":
            try:
                binary = manifold.fetch_binary_markets(500)
                all_opps.extend(self.scan_binary(binary))
            except Exception as e:
                logger.exception("Manifold fetch failed: %s", e)
                raise
        else:
            binary_path = binary_path or self.config.binary_markets_path()
            multi_path = multi_path or self.config.multi_outcome_markets_path()
            if binary_path.exists():
                binary = load_binary_markets(binary_path)
                all_opps.extend(self.scan_binary(binary))
            else:
                logger.warning("Binary markets file not found: %s", binary_path)
            if multi_path.exists():
                multi = load_multi_outcome_markets(multi_path)
                all_opps.extend(self.scan_multi_outcome(multi))
            else:
                logger.warning("Multi-outcome markets file not found: %s", multi_path)

        return all_opps
