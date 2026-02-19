"""
Benzinga Movers and News Scraper
Real-time market movers, breaking news, and momentum stocks
"""
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
import re


class BenzingaScraper:
    """
    Scrapes Benzinga for market movers, breaking news, and hot stocks
    Benzinga is known for real-time financial news and market data
    """

    MOVERS_URL = "https://www.benzinga.com/markets/movers"
    NEWS_URL = "https://www.benzinga.com/markets/news"
    HOT_STOCKS_URL = "https://www.benzinga.com/markets/hot-stocks"
    PREMARKET_URL = "https://www.benzinga.com/markets/premarket"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

    async def scrape_movers(self) -> List[Dict]:
        """
        Scrape top movers (gainers and unusual volume) from Benzinga
        Returns list of stocks with price movements
        """
        try:
            movers = []

            async with aiohttp.ClientSession() as session:
                async with session.get(self.MOVERS_URL, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        print(f"Benzinga Movers returned status {response.status}")
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Find mover cards/tables
                    # Benzinga typically uses tables or card layouts for movers
                    tables = soup.find_all('table', limit=3)
                    if tables:
                        for table in tables:
                            rows = table.find_all('tr')[1:]  # Skip header
                            for row in rows[:20]:  # Top 20 per table
                                try:
                                    cols = row.find_all('td')
                                    if len(cols) < 3:
                                        continue

                                    # Extract ticker (usually first column or has link)
                                    ticker = None
                                    for col in cols[:2]:
                                        text = col.get_text(strip=True)
                                        # Look for ticker pattern
                                        if re.match(r'^[A-Z]{1,5}$', text):
                                            ticker = text
                                            break
                                        # Or find link with ticker
                                        link = col.find('a')
                                        if link:
                                            ticker_match = re.search(r'/stock/([A-Z]{1,5})', link.get('href', ''))
                                            if ticker_match:
                                                ticker = ticker_match.group(1)
                                                break

                                    if not ticker:
                                        continue

                                    # Extract price change (look for % symbol)
                                    price_change = 0.0
                                    price = 0.0
                                    volume = 0

                                    for col in cols:
                                        text = col.get_text(strip=True)

                                        # Price change
                                        if '%' in text and price_change == 0.0:
                                            try:
                                                price_change = float(text.replace('%', '').replace('+', '').replace(',', ''))
                                            except:
                                                pass

                                        # Price
                                        if '$' in text and price == 0.0:
                                            try:
                                                price = float(text.replace('$', '').replace(',', ''))
                                            except:
                                                pass

                                        # Volume
                                        if any(x in text for x in ['M', 'K', 'B']) and volume == 0:
                                            volume = self._parse_volume(text)

                                    if ticker and (price_change != 0.0 or price > 0):
                                        movers.append({
                                            'ticker': ticker,
                                            'price': price if price > 0 else None,
                                            'change_percent': price_change,
                                            'volume': volume if volume > 0 else None,
                                            'source': 'benzinga_movers',
                                            'published_at': datetime.now().isoformat(),
                                            'url': f"https://www.benzinga.com/stock/{ticker}"
                                        })

                                except Exception as e:
                                    continue

                    # Alternative: Look for article cards with ticker mentions
                    articles = soup.find_all(['article', 'div'], {'class': lambda x: x and any(word in str(x).lower() for word in ['article', 'story', 'card'])}, limit=30)

                    for article in articles:
                        try:
                            # Find title
                            title_elem = article.find(['h2', 'h3', 'h4', 'a'])
                            if not title_elem:
                                continue

                            title = title_elem.get_text(strip=True)
                            if len(title) < 15:
                                continue

                            # Extract URL
                            link = article.find('a', href=True)
                            url = link['href'] if link else ''
                            if url and not url.startswith('http'):
                                url = f"https://www.benzinga.com{url}"

                            # Extract tickers from title
                            tickers = self._extract_tickers(title)

                            # Look for price change in article text
                            article_text = article.get_text()
                            price_change = self._extract_price_change(article_text)

                            for ticker in tickers[:2]:  # Max 2 tickers per article
                                movers.append({
                                    'ticker': ticker,
                                    'title': title,
                                    'change_percent': price_change,
                                    'source': 'benzinga_news',
                                    'published_at': datetime.now().isoformat(),
                                    'url': url,
                                    'momentum_score': self._calculate_momentum_score(title)
                                })

                        except Exception as e:
                            continue

            print(f"Benzinga: Found {len(movers)} movers/news")
            return movers

        except Exception as e:
            print(f"Error scraping Benzinga movers: {e}")
            return []

    async def scrape_breaking_news(self) -> List[Dict]:
        """
        Scrape breaking news from Benzinga
        Real-time market-moving news
        """
        try:
            news_items = []

            async with aiohttp.ClientSession() as session:
                async with session.get(self.NEWS_URL, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Find news articles
                    articles = soup.find_all(['article', 'div'], {'class': lambda x: x and 'article' in str(x).lower()}, limit=50)

                    for article in articles:
                        try:
                            # Extract title
                            title_elem = article.find(['h2', 'h3', 'h4'])
                            if not title_elem:
                                continue

                            title = title_elem.get_text(strip=True)
                            if len(title) < 15:
                                continue

                            # Extract URL
                            link = article.find('a', href=True)
                            url = link['href'] if link else ''
                            if url and not url.startswith('http'):
                                url = f"https://www.benzinga.com{url}"

                            # Extract tickers
                            tickers = self._extract_tickers(title + ' ' + article.get_text())

                            # Extract time if available
                            time_elem = article.find(['time', 'span'], {'class': lambda x: x and 'time' in str(x).lower()})
                            time_str = time_elem.get_text(strip=True) if time_elem else ''

                            for ticker in tickers[:3]:
                                news_items.append({
                                    'ticker': ticker,
                                    'title': title,
                                    'url': url,
                                    'source': 'benzinga_breaking',
                                    'published_at': datetime.now().isoformat(),
                                    'time_str': time_str,
                                    'relevance_score': self._calculate_momentum_score(title)
                                })

                        except Exception as e:
                            continue

            print(f"Benzinga Breaking: Found {len(news_items)} news items")
            return news_items

        except Exception as e:
            print(f"Error scraping Benzinga breaking news: {e}")
            return []

    async def scrape_premarket_movers(self) -> List[Dict]:
        """
        Scrape pre-market movers from Benzinga
        Stocks moving before market open
        """
        try:
            movers = []

            async with aiohttp.ClientSession() as session:
                async with session.get(self.PREMARKET_URL, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Similar parsing logic as movers
                    tables = soup.find_all('table', limit=2)
                    for table in tables:
                        rows = table.find_all('tr')[1:]
                        for row in rows[:15]:
                            try:
                                cols = row.find_all('td')
                                if len(cols) < 3:
                                    continue

                                ticker = None
                                for col in cols[:2]:
                                    text = col.get_text(strip=True)
                                    if re.match(r'^[A-Z]{1,5}$', text):
                                        ticker = text
                                        break

                                if not ticker:
                                    continue

                                price_change = 0.0
                                for col in cols:
                                    text = col.get_text(strip=True)
                                    if '%' in text:
                                        try:
                                            price_change = float(text.replace('%', '').replace('+', ''))
                                        except:
                                            pass

                                movers.append({
                                    'ticker': ticker,
                                    'change_percent': price_change,
                                    'source': 'benzinga_premarket',
                                    'published_at': datetime.now().isoformat(),
                                    'url': f"https://www.benzinga.com/stock/{ticker}",
                                    'premarket': True
                                })

                            except Exception as e:
                                continue

            print(f"Benzinga Premarket: Found {len(movers)} movers")
            return movers

        except Exception as e:
            print(f"Error scraping Benzinga premarket: {e}")
            return []

    def _extract_tickers(self, text: str) -> List[str]:
        """Extract ticker symbols from text"""
        tickers = set()

        patterns = [
            r'\(([A-Z]{1,5})\)',
            r'\$([A-Z]{1,5})\b',
            r'NASDAQ:([A-Z]{1,5})',
            r'NYSE:([A-Z]{1,5})',
            r'\b([A-Z]{2,5})\s+stock',
            r'\b([A-Z]{2,5})\s+shares',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if match not in ['US', 'USD', 'UK', 'CEO', 'IPO', 'ETF', 'SEC', 'FDA', 'API']:
                    if len(match) >= 2:
                        tickers.add(match)

        return list(tickers)

    def _extract_price_change(self, text: str) -> float:
        """Extract price change from text"""
        try:
            # Look for patterns like "+15%", "up 20%"
            patterns = [
                r'([+-]\d+\.?\d*)%',
                r'up (\d+\.?\d*)%',
                r'down (\d+\.?\d*)%',
            ]

            for pattern in patterns:
                match = re.search(pattern, text.lower())
                if match:
                    change = float(match.group(1).replace('+', ''))
                    if 'down' in text.lower():
                        return -abs(change)
                    return change
        except:
            pass
        return 0.0

    def _calculate_momentum_score(self, text: str) -> int:
        """Calculate momentum score based on keywords"""
        score = 50
        text_lower = text.lower()

        high_momentum = ['surge', 'soar', 'explode', 'breakout', 'rally', 'spike', 'rocket']
        catalysts = ['earnings', 'upgrade', 'approval', 'deal', 'partnership', 'contract']
        volume_indicators = ['unusual volume', 'heavy trading', 'volume spike']

        score += sum(15 for word in high_momentum if word in text_lower)
        score += sum(10 for word in catalysts if word in text_lower)
        score += sum(12 for word in volume_indicators if word in text_lower)

        return min(100, score)

    def _parse_volume(self, volume_str: str) -> int:
        """Parse volume strings like '1.23M' to integers"""
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

    async def get_all_benzinga_data(self, limit: int = 30) -> List[Dict]:
        """
        Get all Benzinga data: movers, breaking news, premarket
        Returns combined and deduplicated results
        """
        import asyncio

        # Scrape all sources in parallel
        movers, breaking, premarket = await asyncio.gather(
            self.scrape_movers(),
            self.scrape_breaking_news(),
            self.scrape_premarket_movers(),
            return_exceptions=True
        )

        all_data = []
        for result in [movers, breaking, premarket]:
            if isinstance(result, list):
                all_data.extend(result)

        # Deduplicate by ticker
        seen_tickers = set()
        unique_data = []
        for item in all_data:
            ticker = item.get('ticker')
            if ticker and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                unique_data.append(item)

        # Sort by momentum/relevance score
        unique_data.sort(key=lambda x: x.get('momentum_score', x.get('relevance_score', 0)), reverse=True)

        return unique_data[:limit]
