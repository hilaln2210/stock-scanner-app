"""
TradingView Trending Ideas and Hot Stocks Scraper
Scrapes popular trading ideas and trending tickers
"""
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
import re


class TradingViewScraper:
    """
    Scrapes TradingView for trending stocks and popular trading ideas
    TradingView is a major platform for technical analysis and trading ideas
    """

    IDEAS_URL = "https://www.tradingview.com/ideas/"
    TRENDING_URL = "https://www.tradingview.com/markets/stocks-usa/market-movers-active/"
    GAINERS_URL = "https://www.tradingview.com/markets/stocks-usa/market-movers-gainers/"
    SCREENER_URL = "https://www.tradingview.com/screener/"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

    async def scrape_trending_ideas(self) -> List[Dict]:
        """
        Scrape trending trading ideas from TradingView
        Returns stocks with high community attention
        """
        try:
            trending_stocks = []

            async with aiohttp.ClientSession() as session:
                async with session.get(self.IDEAS_URL, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        print(f"TradingView Ideas returned status {response.status}")
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Find idea cards
                    ideas = soup.find_all(['div', 'article'], {'class': lambda x: x and 'idea' in str(x).lower()}, limit=50)

                    if not ideas:
                        # Alternative: find any card-like structures
                        ideas = soup.find_all(['div', 'a'], {'class': lambda x: x and any(word in str(x).lower() for word in ['card', 'item', 'post'])}, limit=50)

                    for idea in ideas:
                        try:
                            # Extract title
                            title_elem = idea.find(['h2', 'h3', 'span', 'div'], {'class': lambda x: x and 'title' in str(x).lower()})
                            if not title_elem:
                                title_elem = idea.find('a')

                            if not title_elem:
                                continue

                            title = title_elem.get_text(strip=True)
                            if len(title) < 10:
                                continue

                            # Extract URL
                            link = idea.find('a', href=True)
                            url = link['href'] if link else ''
                            if url and not url.startswith('http'):
                                url = f"https://www.tradingview.com{url}"

                            # Extract ticker from URL or title
                            # TradingView URLs often like: /chart/AAPL/ or /symbols/AAPL/
                            ticker_match = re.search(r'/(?:chart|symbols)/([A-Z]{1,5})/', url)
                            if ticker_match:
                                ticker = ticker_match.group(1)
                            else:
                                # Extract from title
                                tickers = self._extract_tickers(title)
                                if not tickers:
                                    continue
                                ticker = tickers[0]

                            # Look for bullish/bearish sentiment
                            sentiment = 'neutral'
                            idea_text = idea.get_text().lower()
                            if any(word in idea_text for word in ['long', 'buy', 'bullish', 'bull']):
                                sentiment = 'bullish'
                            elif any(word in idea_text for word in ['short', 'sell', 'bearish', 'bear']):
                                sentiment = 'bearish'

                            # Look for like count or popularity indicators
                            likes = 0
                            like_elem = idea.find(['span', 'div'], {'class': lambda x: x and any(word in str(x).lower() for word in ['like', 'boost', 'vote'])})
                            if like_elem:
                                try:
                                    likes_text = like_elem.get_text(strip=True)
                                    likes = int(re.sub(r'[^\d]', '', likes_text))
                                except:
                                    pass

                            trending_stocks.append({
                                'ticker': ticker,
                                'title': title,
                                'url': url,
                                'source': 'tradingview_ideas',
                                'sentiment': sentiment,
                                'likes': likes,
                                'popularity_score': min(100, 50 + likes // 10),
                                'published_at': datetime.now().isoformat()
                            })

                        except Exception as e:
                            continue

            print(f"TradingView Ideas: Found {len(trending_stocks)} trending ideas")
            return trending_stocks

        except Exception as e:
            print(f"Error scraping TradingView ideas: {e}")
            return []

    async def scrape_market_movers(self) -> List[Dict]:
        """
        Scrape market movers from TradingView
        Returns top gainers and most active stocks
        """
        try:
            movers = []

            urls = [
                (self.GAINERS_URL, 'gainers'),
                (self.TRENDING_URL, 'active')
            ]

            async with aiohttp.ClientSession() as session:
                for url, category in urls:
                    try:
                        async with session.get(url, headers=self.headers, timeout=10) as response:
                            if response.status != 200:
                                continue

                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')

                            # Find table rows with stock data
                            rows = soup.find_all('tr', limit=25)

                            for row in rows:
                                try:
                                    # Look for ticker in row
                                    ticker_elem = row.find('a', href=lambda x: x and '/symbols/' in str(x))
                                    if not ticker_elem:
                                        continue

                                    # Extract ticker from URL
                                    href = ticker_elem.get('href', '')
                                    ticker_match = re.search(r'/symbols/([A-Z]{1,5})', href)
                                    if not ticker_match:
                                        continue

                                    ticker = ticker_match.group(1)

                                    # Extract price and change
                                    cols = row.find_all('td')
                                    price = 0.0
                                    change_percent = 0.0
                                    volume = 0

                                    for col in cols:
                                        text = col.get_text(strip=True)

                                        # Price (decimal number)
                                        if '.' in text and '$' not in text and '%' not in text and price == 0.0:
                                            try:
                                                p = float(text.replace(',', ''))
                                                if 0.01 < p < 100000:
                                                    price = p
                                            except:
                                                pass

                                        # Change percent
                                        if '%' in text and change_percent == 0.0:
                                            try:
                                                change_percent = float(text.replace('%', '').replace('+', '').replace(',', ''))
                                            except:
                                                pass

                                        # Volume
                                        if any(x in text for x in ['M', 'K', 'B']) and volume == 0:
                                            volume = self._parse_volume(text)

                                    if ticker:
                                        movers.append({
                                            'ticker': ticker,
                                            'price': price if price > 0 else None,
                                            'change_percent': change_percent,
                                            'volume': volume if volume > 0 else None,
                                            'source': f'tradingview_{category}',
                                            'category': category,
                                            'published_at': datetime.now().isoformat(),
                                            'url': f"https://www.tradingview.com/symbols/{ticker}/"
                                        })

                                except Exception as e:
                                    continue

                    except Exception as e:
                        print(f"Error scraping TradingView {category}: {e}")
                        continue

            print(f"TradingView Movers: Found {len(movers)} movers")
            return movers

        except Exception as e:
            print(f"Error scraping TradingView movers: {e}")
            return []

    def _extract_tickers(self, text: str) -> List[str]:
        """Extract ticker symbols from text"""
        tickers = set()

        patterns = [
            r'\b([A-Z]{1,5}):\s',           # AAPL: format
            r'\$([A-Z]{1,5})\b',            # $AAPL
            r'\(([A-Z]{1,5})\)',            # (AAPL)
            r'NASDAQ:([A-Z]{1,5})',
            r'NYSE:([A-Z]{1,5})',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if match not in ['US', 'USD', 'SPY', 'QQQ', 'DIA'] and len(match) >= 2:
                    tickers.add(match)

        return list(tickers)

    def _parse_volume(self, volume_str: str) -> int:
        """Parse volume strings"""
        try:
            volume_str = volume_str.strip().upper()
            if 'M' in volume_str:
                return int(float(volume_str.replace('M', '')) * 1_000_000)
            elif 'K' in volume_str:
                return int(float(volume_str.replace('K', '')) * 1_000)
            elif 'B' in volume_str:
                return int(float(volume_str.replace('B', '')) * 1_000_000_000)
            return int(volume_str.replace(',', ''))
        except:
            return 0

    async def get_all_tradingview_data(self, limit: int = 30) -> List[Dict]:
        """
        Get all TradingView data: ideas and movers
        Returns combined results
        """
        import asyncio

        ideas, movers = await asyncio.gather(
            self.scrape_trending_ideas(),
            self.scrape_market_movers(),
            return_exceptions=True
        )

        all_data = []
        for result in [ideas, movers]:
            if isinstance(result, list):
                all_data.extend(result)

        # Deduplicate
        seen_tickers = set()
        unique_data = []
        for item in all_data:
            ticker = item.get('ticker')
            if ticker and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                unique_data.append(item)

        return unique_data[:limit]
