"""
CNBC Breaking News and Market Movers Scraper
Real-time financial news and stock alerts
"""
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
import re
import feedparser


class CNBCScraper:
    """
    Scrapes CNBC for breaking financial news and market movers
    CNBC is a major source for real-time market news
    """

    RSS_URLS = [
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",  # Top News
        "https://www.cnbc.com/id/15839135/device/rss/rss.html",   # Investing
        "https://www.cnbc.com/id/19854910/device/rss/rss.html",   # Earnings
    ]

    BREAKING_URL = "https://www.cnbc.com/markets/"
    MOVERS_URL = "https://www.cnbc.com/stocks/"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }

    async def scrape_rss_feeds(self) -> List[Dict]:
        """
        Scrape CNBC RSS feeds for latest financial news
        """
        try:
            news_items = []

            for rss_url in self.RSS_URLS:
                try:
                    feed = feedparser.parse(rss_url)

                    for entry in feed.entries[:20]:  # Top 20 per feed
                        title = entry.get('title', '')
                        url = entry.get('link', '')
                        summary = entry.get('summary', '')

                        if len(title) < 10:
                            continue

                        # Parse published date
                        published_struct = entry.get('published_parsed')
                        if published_struct:
                            published_at = datetime(*published_struct[:6])
                        else:
                            published_at = datetime.now()

                        # Extract tickers
                        tickers = self._extract_tickers(title + ' ' + summary)

                        # Calculate relevance score
                        relevance_score = self._calculate_relevance_score(title, summary)

                        for ticker in tickers[:3]:
                            news_items.append({
                                'ticker': ticker,
                                'title': title,
                                'url': url,
                                'summary': summary[:300],
                                'source': 'cnbc_rss',
                                'relevance_score': relevance_score,
                                'published_at': published_at.isoformat(),
                                'category': self._categorize_news(title)
                            })

                except Exception as e:
                    print(f"Error scraping CNBC RSS {rss_url}: {e}")
                    continue

            print(f"CNBC RSS: Found {len(news_items)} news items")
            return news_items

        except Exception as e:
            print(f"Error in CNBC RSS scraper: {e}")
            return []

    async def scrape_breaking_news(self) -> List[Dict]:
        """
        Scrape breaking news from CNBC website
        """
        try:
            news_items = []

            async with aiohttp.ClientSession() as session:
                async with session.get(self.BREAKING_URL, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Find news articles
                    articles = soup.find_all(['article', 'div'], {'class': lambda x: x and any(word in str(x).lower() for word in ['card', 'article', 'story'])}, limit=40)

                    for article in articles:
                        try:
                            # Extract title
                            title_elem = article.find(['h2', 'h3', 'a'])
                            if not title_elem:
                                continue

                            title = title_elem.get_text(strip=True)
                            if len(title) < 15:
                                continue

                            # Extract URL
                            link = article.find('a', href=True)
                            url = link['href'] if link else ''
                            if url and not url.startswith('http'):
                                url = f"https://www.cnbc.com{url}"

                            # Extract tickers
                            tickers = self._extract_tickers(title + ' ' + article.get_text())

                            for ticker in tickers[:2]:
                                news_items.append({
                                    'ticker': ticker,
                                    'title': title,
                                    'url': url,
                                    'source': 'cnbc_breaking',
                                    'published_at': datetime.now().isoformat(),
                                    'relevance_score': self._calculate_relevance_score(title, '')
                                })

                        except Exception as e:
                            continue

            print(f"CNBC Breaking: Found {len(news_items)} news items")
            return news_items

        except Exception as e:
            print(f"Error scraping CNBC breaking news: {e}")
            return []

    def _extract_tickers(self, text: str) -> List[str]:
        """Extract ticker symbols from text"""
        tickers = set()

        # Company name mappings
        companies = {
            'Apple': 'AAPL', 'Microsoft': 'MSFT', 'Amazon': 'AMZN', 'Google': 'GOOGL',
            'Tesla': 'TSLA', 'Meta': 'META', 'Netflix': 'NFLX', 'Nvidia': 'NVDA',
            'AMD': 'AMD', 'Intel': 'INTC', 'Palantir': 'PLTR', 'Coinbase': 'COIN',
            'JPMorgan': 'JPM', 'Goldman': 'GS', 'Bank of America': 'BAC',
            'Pfizer': 'PFE', 'Moderna': 'MRNA', 'Boeing': 'BA', 'Disney': 'DIS',
        }

        for company, ticker in companies.items():
            if company.lower() in text.lower():
                tickers.add(ticker)

        # Pattern matching
        patterns = [
            r'\(([A-Z]{1,5})\)',
            r'\$([A-Z]{1,5})\b',
            r'NASDAQ:([A-Z]{1,5})',
            r'NYSE:([A-Z]{1,5})',
            r'\b([A-Z]{2,5})\s+stock',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if match not in ['US', 'USD', 'CEO', 'IPO', 'SEC'] and len(match) >= 2:
                    tickers.add(match)

        return list(tickers)

    def _calculate_relevance_score(self, title: str, summary: str) -> int:
        """Calculate relevance score"""
        score = 50
        text = (title + ' ' + summary).lower()

        # High impact keywords
        high_impact = ['breaking', 'alert', 'surge', 'plunge', 'halted', 'emergency']
        score += sum(20 for word in high_impact if word in text)

        # Catalysts
        catalysts = ['earnings', 'upgrade', 'downgrade', 'deal', 'merger', 'fda', 'approval']
        score += sum(10 for word in catalysts if word in text)

        # Market moving
        market_moving = ['market', 'trading', 'volume', 'volatility']
        score += sum(5 for word in market_moving if word in text)

        return min(100, score)

    def _categorize_news(self, title: str) -> str:
        """Categorize news by type"""
        title_lower = title.lower()

        if any(word in title_lower for word in ['earnings', 'revenue', 'profit']):
            return 'earnings'
        elif any(word in title_lower for word in ['upgrade', 'downgrade', 'rating']):
            return 'analyst'
        elif any(word in title_lower for word in ['deal', 'merger', 'acquisition']):
            return 'ma'
        elif any(word in title_lower for word in ['fed', 'interest', 'inflation']):
            return 'macro'
        else:
            return 'general'

    async def get_all_cnbc_data(self, limit: int = 30) -> List[Dict]:
        """Get all CNBC data"""
        import asyncio

        rss_news, breaking_news = await asyncio.gather(
            self.scrape_rss_feeds(),
            self.scrape_breaking_news(),
            return_exceptions=True
        )

        all_data = []
        for result in [rss_news, breaking_news]:
            if isinstance(result, list):
                all_data.extend(result)

        # Sort by relevance
        all_data.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

        # Deduplicate
        seen_tickers = set()
        unique_data = []
        for item in all_data:
            ticker = item.get('ticker')
            if ticker and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                unique_data.append(item)

        return unique_data[:limit]
