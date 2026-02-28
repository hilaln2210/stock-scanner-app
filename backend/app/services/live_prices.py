import yfinance as yf
from typing import Dict, List
from datetime import datetime
import asyncio
from concurrent.futures import ThreadPoolExecutor


class LivePriceService:
    """Fetches live stock prices, volume, and anomaly detection"""

    def __init__(self):
        self.cache = {}
        self.cache_expiry = {}

    async def get_stock_data(self, ticker: str) -> Dict:
        """
        Get real-time stock data for a ticker
        Returns: price, change, volume, volume_anomaly
        """
        # Check cache (5 second expiry for real-time feel)
        now = datetime.now()
        if ticker in self.cache and ticker in self.cache_expiry:
            if (now - self.cache_expiry[ticker]).total_seconds() < 5:
                return self.cache[ticker]

        try:
            # Run yfinance in executor with timeout to avoid blocking
            loop = asyncio.get_event_loop()
            stock_data = await asyncio.wait_for(
                loop.run_in_executor(None, self._fetch_stock_data, ticker),
                timeout=10
            )

            # Cache result
            self.cache[ticker] = stock_data
            self.cache_expiry[ticker] = now

            return stock_data
        except asyncio.TimeoutError:
            print(f"Timeout fetching {ticker}")
            return self._empty_data()
        except Exception as e:
            print(f"Error fetching {ticker}: {e}")
            return self._empty_data()

    def _fetch_stock_data(self, ticker: str) -> Dict:
        """Sync function to fetch stock data (with timeout on stock.info)"""
        try:
            stock = yf.Ticker(ticker)

            # Get current price and volume — stock.info can hang, use timeout
            try:
                with ThreadPoolExecutor(max_workers=1) as ex:
                    info = ex.submit(lambda: stock.info or {}).result(timeout=6)
            except Exception:
                info = {}

            # Get the most current price (pre-market, regular, or post-market)
            current_price = (
                info.get('preMarketPrice') or  # Pre-market price (priority)
                info.get('currentPrice') or
                info.get('regularMarketPrice') or
                info.get('postMarketPrice') or
                0
            )

            prev_close = info.get('previousClose', current_price)

            # Calculate daily change
            # Try to get pre-calculated change first, otherwise calculate manually
            change_percent = (
                info.get('preMarketChangePercent') or
                info.get('regularMarketChangePercent') or
                info.get('postMarketChangePercent')
            )

            if change_percent is None:
                # Calculate manually if not provided
                if prev_close and prev_close > 0:
                    change_dollar = current_price - prev_close
                    change_percent = (change_dollar / prev_close) * 100
                else:
                    change_dollar = 0
                    change_percent = 0
            else:
                # If we have the percentage, calculate the dollar change
                change_dollar = (change_percent / 100) * prev_close if prev_close else 0

            # Volume analysis
            current_volume = info.get('volume', 0) or info.get('regularMarketVolume', 0)
            avg_volume = info.get('averageVolume', 0) or info.get('averageDailyVolume10Day', 0)

            volume_ratio = 0
            volume_anomaly = False
            if avg_volume and avg_volume > 0:
                volume_ratio = current_volume / avg_volume
                # Anomaly if volume > 2x average
                volume_anomaly = volume_ratio >= 2.0

            # Company info
            sector = info.get('sector', 'Unknown')
            industry = info.get('industry', 'Unknown')
            business_summary = info.get('longBusinessSummary', '')
            company_name = info.get('longName') or info.get('shortName', ticker)

            # Shorten business summary to 150 chars
            if business_summary and len(business_summary) > 150:
                business_summary = business_summary[:150] + "..."

            # Extra fields for search results
            market_cap = info.get('marketCap', 0) or 0
            day_high = info.get('dayHigh', 0) or info.get('regularMarketDayHigh', 0) or 0
            day_low = info.get('dayLow', 0) or info.get('regularMarketDayLow', 0) or 0

            return {
                "price": round(current_price, 2) if current_price else 0,
                "change_dollar": round(change_dollar, 2) if change_dollar else 0,
                "change_percent": round(change_percent, 2) if change_percent else 0,
                "volume": current_volume,
                "avg_volume": avg_volume,
                "volume_ratio": round(volume_ratio, 2) if volume_ratio else 0,
                "volume_anomaly": volume_anomaly,
                "sector": sector,
                "industry": industry,
                "company_name": company_name,
                "business_summary": business_summary,
                "market_cap": market_cap,
                "day_high": round(day_high, 2) if day_high else 0,
                "day_low": round(day_low, 2) if day_low else 0,
                "prev_close": round(prev_close, 2) if prev_close else 0,
                "updated_at": datetime.now().astimezone().isoformat()
            }
        except Exception as e:
            print(f"Error in _fetch_stock_data for {ticker}: {e}")
            return self._empty_data()

    def _empty_data(self) -> Dict:
        """Return empty data structure"""
        return {
            "price": 0,
            "change_dollar": 0,
            "change_percent": 0,
            "volume": 0,
            "avg_volume": 0,
            "volume_ratio": 0,
            "volume_anomaly": False,
            "sector": "Unknown",
            "industry": "Unknown",
            "company_name": "",
            "business_summary": "",
            "updated_at": datetime.now().astimezone().isoformat()
        }

    def get_sector_emoji(self, sector: str) -> str:
        """Get emoji for sector"""
        sector_emojis = {
            "Technology": "💻",
            "Healthcare": "🏥",
            "Financial Services": "🏦",
            "Consumer Cyclical": "🛍️",
            "Communication Services": "📡",
            "Industrials": "🏭",
            "Consumer Defensive": "🍔",
            "Energy": "⚡",
            "Utilities": "💡",
            "Real Estate": "🏢",
            "Basic Materials": "⚒️",
            "Financial": "💰",
            "Finance": "💰",
            "Consumer Discretionary": "🛒",
            "Materials": "🔩",
            "Telecommunications": "📞",
        }
        return sector_emojis.get(sector, "🏢")

    async def enrich_stocks_with_live_data(self, stocks: List[Dict]) -> List[Dict]:
        """
        Enrich a list of stocks with live price/volume data
        Processes in parallel for speed
        """
        if not stocks:
            return stocks

        # Get unique tickers
        tickers = list(set([s['ticker'] for s in stocks if s.get('ticker')]))

        # Fetch all data in parallel (limit to 10 at a time to avoid rate limits)
        tasks = []
        for ticker in tickers[:20]:  # Limit to top 20 tickers
            tasks.append(self.get_stock_data(ticker))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Create lookup dict
        price_data = {}
        for ticker, result in zip(tickers[:20], results):
            if isinstance(result, dict):
                price_data[ticker] = result
            else:
                price_data[ticker] = self._empty_data()

        # Enrich stocks
        enriched_stocks = []
        for stock in stocks:
            ticker = stock.get('ticker')
            if ticker in price_data:
                stock['live_data'] = price_data[ticker]
            else:
                stock['live_data'] = self._empty_data()
            enriched_stocks.append(stock)

        return enriched_stocks
