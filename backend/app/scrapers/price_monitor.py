import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict
import os
from bs4 import BeautifulSoup
import re


class PriceMonitor:
    """Monitors stock prices for spike alerts using Finviz screener"""

    API_KEY = os.getenv('ALPHA_VANTAGE_API_KEY', 'demo')  # Free tier: 25 calls/day
    BASE_URL = "https://www.alphavantage.co/query"
    FINVIZ_SCREENER_URL = "https://finviz.com/screener.ashx?v=111&s=ta_topgainers&f=cap_midover"

    # Quality filters to prevent spam
    QUALITY_FILTERS = {
        'min_price': 1.0,           # $1+ (no penny stocks)
        'min_volume': 100_000,      # 100K+ volume
        'min_market_cap': 50_000_000,  # $50M+ (estimated from price * volume)
    }

    def __init__(self):
        self.price_cache = {}  # {ticker: {'price': float, 'volume': int, 'timestamp': datetime}}

    async def check_price_spike(self, ticker: str, threshold: float = 0.05) -> Dict:
        """
        Check if price spiked by threshold (default 5%) in last 5 minutes
        Returns: dict with spike info or None
        """
        current_data = await self.get_current_price(ticker)
        if not current_data:
            return None

        # Check quality filters
        if not self._passes_quality_filters(current_data):
            return None

        # Check cache for 5min ago price
        if ticker in self.price_cache:
            old_data = self.price_cache[ticker]
            time_diff = (datetime.now() - old_data['timestamp']).total_seconds() / 60

            if 4 <= time_diff <= 6:  # Between 4-6 minutes ago
                price_change = (current_data['price'] - old_data['price']) / old_data['price']

                if price_change >= threshold:
                    return {
                        'ticker': ticker,
                        'old_price': old_data['price'],
                        'new_price': current_data['price'],
                        'change_percent': price_change * 100,
                        'volume': current_data['volume'],
                        'timestamp': datetime.now(),
                    }

        # Update cache
        self.price_cache[ticker] = {
            'price': current_data['price'],
            'volume': current_data['volume'],
            'timestamp': datetime.now(),
        }

        return None

    async def get_current_price(self, ticker: str) -> Dict:
        """Fetch current price from Alpha Vantage"""
        try:
            params = {
                'function': 'GLOBAL_QUOTE',
                'symbol': ticker,
                'apikey': self.API_KEY,
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(self.BASE_URL, params=params) as response:
                    if response.status != 200:
                        return None

                    data = await response.json()
                    quote = data.get('Global Quote', {})

                    if not quote:
                        return None

                    return {
                        'ticker': ticker,
                        'price': float(quote.get('05. price', 0)),
                        'volume': int(quote.get('06. volume', 0)),
                        'change_percent': float(quote.get('10. change percent', '0').replace('%', '')),
                    }

        except Exception as e:
            print(f"Error fetching price for {ticker}: {e}")
            return None

    async def scrape_yahoo_top_gainers(self, limit: int = 20) -> List[Dict]:
        """
        Scrape top gainers from Yahoo Finance (real-time data)
        Returns: list of dicts with ticker, change%, price, volume
        """
        try:
            url = "https://finance.yahoo.com/markets/stocks/gainers/"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        print(f"Yahoo Finance returned status {response.status}")
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    movers = []

                    # Find all table rows with stock data
                    rows = soup.find_all('tr', {'class': lambda x: x and 'row' in str(x).lower()})

                    for row in rows[:limit * 2]:
                        try:
                            # Find ticker symbol
                            ticker_elem = row.find('a', {'data-test': 'quoteLink'})
                            if not ticker_elem:
                                continue

                            ticker = ticker_elem.text.strip()

                            # Find all fin-streamer elements for price, change%, volume
                            streamers = row.find_all('fin-streamer')
                            if len(streamers) < 3:
                                continue

                            # Extract price (usually first streamer)
                            price = 0.0
                            change_percent = 0.0
                            volume = 0

                            for streamer in streamers:
                                field = streamer.get('data-field', '')
                                value = streamer.text.strip()

                                if field == 'regularMarketPrice':
                                    price = float(value.replace(',', ''))
                                elif field == 'regularMarketChangePercent':
                                    # Remove % and + signs
                                    change_percent = float(value.replace('%', '').replace('+', '').replace(',', ''))
                                elif field == 'regularMarketVolume':
                                    # Convert volume string to number
                                    volume = self._parse_volume(value)

                            if price > 0:
                                mover_data = {
                                    'ticker': ticker,
                                    'price': price,
                                    'change_percent': change_percent,
                                    'volume': volume if volume > 0 else 100000,  # Default volume if not found
                                }

                                # Apply quality filters
                                if self._passes_quality_filters(mover_data):
                                    movers.append(mover_data)

                                if len(movers) >= limit:
                                    break

                        except (ValueError, AttributeError) as e:
                            continue

                    print(f"Yahoo Top Gainers: Found {len(movers)} quality stocks")
                    return movers

        except Exception as e:
            print(f"Error scraping Yahoo top gainers: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def scrape_finviz_top_gainers(self, limit: int = 20) -> List[Dict]:
        """
        Scrape top gainers from Finviz screener (real-time data)
        Returns: list of dicts with ticker, change%, price, volume
        """
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(self.FINVIZ_SCREENER_URL, headers=headers) as response:
                    if response.status != 200:
                        print(f"Finviz screener returned status {response.status}")
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Find the screener table
                    table = soup.find('table', {'class': 'screener-view-table'})
                    if not table:
                        print("Could not find Finviz screener table")
                        return []

                    movers = []
                    # Find all rows with ticker data
                    rows = table.find_all('tr', {'class': lambda x: x and 'screener-row' in x})

                    if not rows:
                        # Fallback: try to find all tr elements
                        rows = table.find_all('tr')[1:]  # Skip header

                    for idx, row in enumerate(rows[:limit * 2]):  # Get more rows to ensure we have enough after filtering
                        cols = row.find_all('td')
                        if len(cols) < 11:
                            continue

                        try:
                            # Column indices may vary - let's find ticker first
                            ticker = None
                            for col in cols:
                                link = col.find('a', href=lambda x: x and 'quote.ashx?t=' in str(x))
                                if link:
                                    ticker = link.text.strip()
                                    break

                            if not ticker:
                                continue

                            # Try to find price, change%, and volume by looking at all columns
                            price = 0.0
                            change_percent = 0.0
                            volume = 0

                            for i, col in enumerate(cols):
                                text = col.text.strip()

                                # Price: looks like a decimal number (e.g., "45.32")
                                if '.' in text and price == 0.0:
                                    try:
                                        p = float(text)
                                        if 0.01 < p < 10000:  # Reasonable price range
                                            price = p
                                    except:
                                        pass

                                # Change %: contains % sign
                                if '%' in text and change_percent == 0.0:
                                    try:
                                        change_percent = float(text.replace('%', '').replace('+', ''))
                                    except:
                                        pass

                                # Volume: contains M, K, or B
                                if any(x in text for x in ['M', 'K', 'B']) and volume == 0:
                                    volume = self._parse_volume(text)

                            if price > 0 and change_percent > 0:
                                mover_data = {
                                    'ticker': ticker,
                                    'price': price,
                                    'change_percent': change_percent,
                                    'volume': volume if volume > 0 else 500000,  # Default volume
                                }

                                print(f"  Parsed: {ticker} ${price} +{change_percent}% Vol:{volume}")

                                # Apply quality filters
                                if self._passes_quality_filters(mover_data):
                                    movers.append(mover_data)
                                    print(f"    ✓ Passed quality filters")
                                else:
                                    print(f"    ✗ Failed quality filters")

                        except (ValueError, IndexError) as e:
                            continue

                    print(f"Finviz Top Gainers: Found {len(movers)} quality stocks")
                    return movers

        except Exception as e:
            print(f"Error scraping Finviz top gainers: {e}")
            return []

    def _parse_volume(self, volume_str: str) -> int:
        """Parse volume strings like '1.23M' or '456.78K' to integers"""
        try:
            volume_str = volume_str.strip().upper()
            if 'M' in volume_str:
                return int(float(volume_str.replace('M', '')) * 1_000_000)
            elif 'K' in volume_str:
                return int(float(volume_str.replace('K', '')) * 1_000)
            elif 'B' in volume_str:
                return int(float(volume_str.replace('B', '')) * 1_000_000_000)
            else:
                return int(volume_str.replace(',', ''))
        except:
            return 0

    async def get_top_movers_via_api(self, limit: int = 10) -> List[Dict]:
        """
        Get top movers using a simple free API (MarketStack alternative)
        Uses publicly available market data
        """
        try:
            # Use a free market data API (no key needed for basic data)
            # This URL returns JSON with current market movers
            url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
            params = {
                "formatted": "false",
                "scrIds": "day_gainers",
                "count": limit * 2,
                "start": 0
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }

            # Increase header size limit
            connector = aiohttp.TCPConnector(limit_per_host=5)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        print(f"API returned status {response.status}")
                        return []

                    data = await response.json()
                    quotes = data.get('finance', {}).get('result', [{}])[0].get('quotes', [])

                    movers = []
                    for quote in quotes[:limit * 2]:
                        try:
                            ticker = quote.get('symbol', '')
                            price = float(quote.get('regularMarketPrice', 0))
                            change_percent = float(quote.get('regularMarketChangePercent', 0))
                            volume = int(quote.get('regularMarketVolume', 0))

                            if price > 0 and change_percent > 0:
                                # Get the reason from quote data
                                long_name = quote.get('longName', ticker)
                                market_cap = quote.get('marketCap', 0)

                                mover_data = {
                                    'ticker': ticker,
                                    'price': price,
                                    'change_percent': change_percent,
                                    'volume': volume,
                                    'name': long_name,
                                    'market_cap': market_cap,
                                    'reason': '',  # Will be filled by news scraper
                                }

                                # Apply quality filters
                                if self._passes_quality_filters(mover_data):
                                    movers.append(mover_data)

                                if len(movers) >= limit:
                                    break

                        except (ValueError, KeyError) as e:
                            continue

                    print(f"API Top Gainers: Found {len(movers)} quality stocks")
                    return movers

        except Exception as e:
            print(f"Error fetching top movers via API: {e}")
            return []

    async def get_news_reason(self, ticker: str) -> str:
        """
        Get the main reason/catalyst for a stock's price movement from news
        Returns: Brief reason string
        """
        try:
            # Use Yahoo Finance news API
            url = f"https://query1.finance.yahoo.com/v1/finance/search"
            params = {
                "q": ticker,
                "quotesCount": 1,
                "newsCount": 3,
                "enableFuzzyQuery": False,
                "enableNavLinks": False
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        return "Strong market momentum"

                    data = await response.json()
                    news_items = data.get('news', [])

                    if news_items:
                        # Get the most recent news headline
                        first_news = news_items[0]
                        title = first_news.get('title', '')

                        # Extract key phrases for common catalysts
                        title_lower = title.lower()
                        if 'earnings' in title_lower or 'beats' in title_lower or 'revenue' in title_lower:
                            return "📊 Strong earnings beat"
                        elif 'upgrade' in title_lower or 'raised' in title_lower or 'price target' in title_lower:
                            return "📈 Analyst upgrade"
                        elif 'deal' in title_lower or 'acquisition' in title_lower or 'merger' in title_lower:
                            return "🤝 M&A activity"
                        elif 'fda' in title_lower or 'approval' in title_lower:
                            return "🚀 FDA approval"
                        elif 'contract' in title_lower or 'partnership' in title_lower:
                            return "📝 Major contract win"
                        elif 'guidance' in title_lower:
                            return "📊 Raised guidance"
                        else:
                            # Return shortened headline
                            return title[:60] + "..." if len(title) > 60 else title

                    return "High trading volume"

        except Exception as e:
            return "Market momentum"

    async def get_top_movers_today(self, limit: int = 10) -> List[Dict]:
        """
        Get top movers (gainers) today - uses API for real-time data with reasons
        Returns: list of dicts with ticker, change%, price, volume, reason
        """
        # Try API first (most reliable)
        movers = await self.get_top_movers_via_api(limit=limit)

        # If API fails, try Finviz as fallback
        if not movers:
            print("API failed, trying Finviz fallback...")
            movers = await self.scrape_finviz_top_gainers(limit=limit)

        # Get news/reasons for each mover in parallel
        tasks = []
        for mover in movers:
            tasks.append(self.get_news_reason(mover['ticker']))

        if tasks:
            reasons = await asyncio.gather(*tasks, return_exceptions=True)
            for i, reason in enumerate(reasons):
                if isinstance(reason, str):
                    movers[i]['reason'] = reason
                else:
                    movers[i]['reason'] = "Market momentum"

        return movers[:limit]

    def _passes_quality_filters(self, data: Dict) -> bool:
        """Check if stock passes quality filters"""
        price = data.get('price', 0)
        volume = data.get('volume', 0)

        # Price filter
        if price < self.QUALITY_FILTERS['min_price']:
            return False

        # Volume filter
        if volume < self.QUALITY_FILTERS['min_volume']:
            return False

        # Estimated market cap filter (rough estimate: price * volume * 10)
        estimated_market_cap = price * volume * 10
        if estimated_market_cap < self.QUALITY_FILTERS['min_market_cap']:
            return False

        return True

    async def monitor_watchlist(self, tickers: List[str], threshold: float = 0.05) -> List[Dict]:
        """
        Monitor a list of tickers for price spikes
        Returns: list of spike alerts
        """
        alerts = []

        for ticker in tickers:
            spike = await self.check_price_spike(ticker, threshold)
            if spike:
                alerts.append(spike)
            # Rate limiting: wait between calls
            await asyncio.sleep(0.5)

        return alerts
