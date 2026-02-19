from typing import List
from app.scrapers.finviz import FinvizScraper
from app.scrapers.yahoo import YahooFinanceScraper
from app.scrapers.marketwatch import MarketWatchScraper
from app.scrapers.seeking_alpha import SeekingAlphaScraper
from app.scrapers.benzinga import BenzingaScraper
from app.scrapers.tradingview import TradingViewScraper
from app.scrapers.cnbc import CNBCScraper
from app.scrapers.barrons import BarronsScraper
from app.scrapers.google_finance import GoogleFinanceScraper
from app.scrapers.social_trending import SocialTrendingScanner
from app.scrapers.momentum_scanner import MomentumScanner
from app.scrapers.price_monitor import PriceMonitor
from app.scrapers.ipo_tracker import IPOTracker
from app.scrapers import ScraperResult
from app.config import settings
import asyncio


class IngestionService:
    """Orchestrates data ingestion from multiple sources"""

    def __init__(self):
        # Original scrapers
        self.finviz = FinvizScraper(cookie=settings.finviz_cookie)
        self.yahoo = YahooFinanceScraper()
        self.marketwatch = MarketWatchScraper()

        # New scrapers
        self.seeking_alpha = SeekingAlphaScraper()
        self.benzinga = BenzingaScraper()
        self.tradingview = TradingViewScraper()
        self.cnbc = CNBCScraper()
        self.barrons = BarronsScraper()
        self.google_finance = GoogleFinanceScraper()

        # Specialized scanners
        self.social_trending = SocialTrendingScanner()
        self.momentum_scanner = MomentumScanner()
        self.price_monitor = PriceMonitor()
        self.ipo_tracker = IPOTracker()

    async def scrape_all_sources(self) -> List[ScraperResult]:
        """Scrape all configured sources in parallel for maximum efficiency"""
        all_results = []

        print("\n=== Starting comprehensive market scan ===")
        print("Scraping from 13+ sources in parallel...\n")

        # Run all scrapers in parallel for speed
        tasks = [
            self._scrape_with_label("Finviz", self.finviz.scrape()),
            self._scrape_with_label("Yahoo Finance", self.yahoo.scrape()),
            self._scrape_with_label("MarketWatch", self.marketwatch.scrape()),
            self._scrape_with_label("Seeking Alpha", self._convert_to_scraper_result(self.seeking_alpha.get_trending_stocks(), "seeking_alpha")),
            self._scrape_with_label("Benzinga", self._convert_to_scraper_result(self.benzinga.get_all_benzinga_data(), "benzinga")),
            self._scrape_with_label("TradingView", self._convert_to_scraper_result(self.tradingview.get_all_tradingview_data(), "tradingview")),
            self._scrape_with_label("CNBC", self._convert_to_scraper_result(self.cnbc.get_all_cnbc_data(), "cnbc")),
            self._scrape_with_label("Barron's", self._convert_to_scraper_result(self.barrons.get_all_barrons_data(), "barrons")),
            self._scrape_with_label("Google Finance", self._convert_to_scraper_result(self.google_finance.get_all_google_finance_data(), "google_finance")),
            self._scrape_with_label("Social Trending", self._convert_to_scraper_result(self.social_trending.get_trending_stocks(), "social")),
            self._scrape_with_label("Momentum Scanner", self._convert_to_scraper_result(self.momentum_scanner.scan_momentum_opportunities(), "momentum")),
            self._scrape_with_label("Price Monitor", self._convert_to_scraper_result(self.price_monitor.get_top_movers_today(), "price_movers")),
            self._scrape_with_label("IPO Tracker", self._convert_to_scraper_result(self.ipo_tracker.get_upcoming_ipos(), "ipos")),
        ]

        # Execute all in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect results
        for result in results:
            if isinstance(result, list):
                all_results.extend(result)
            elif isinstance(result, Exception):
                print(f"  ⚠️  Error in scraper: {result}")

        print(f"\n✅ Total items scraped: {len(all_results)}")
        print(f"📊 Unique tickers found: {len(set(item.tickers[0] if item.tickers else 'N/A' for item in all_results))}")
        print("=== Scan complete ===\n")

        return all_results

    async def _scrape_with_label(self, label: str, coro) -> List[ScraperResult]:
        """Helper to scrape with status printing"""
        try:
            results = await coro
            print(f"✓ {label}: {len(results)} items")
            return results
        except Exception as e:
            print(f"✗ {label}: Error - {str(e)[:50]}")
            return []

    async def _convert_to_scraper_result(self, data_coro, source: str) -> List[ScraperResult]:
        """Convert dict results to ScraperResult format"""
        from datetime import datetime

        try:
            data = await data_coro
            results = []

            for item in data:
                try:
                    # Extract ticker(s)
                    ticker = item.get('ticker', '')
                    tickers = [ticker] if ticker else []

                    # Parse published_at
                    published_at = item.get('published_at')
                    if isinstance(published_at, str):
                        try:
                            published_at = datetime.fromisoformat(published_at.replace('Z', '+00:00'))
                        except:
                            published_at = datetime.now()
                    elif not isinstance(published_at, datetime):
                        published_at = datetime.now()

                    # Create ScraperResult
                    results.append(
                        ScraperResult(
                            source=item.get('source', source),
                            title=item.get('title', f"{ticker} trending"),
                            url=item.get('url', ''),
                            published_at=published_at,
                            summary=item.get('summary', item.get('reason', ''))[:500],
                            tickers=tickers,
                        )
                    )
                except Exception as e:
                    continue

            return results
        except Exception as e:
            print(f"Error converting {source} data: {e}")
            return []
