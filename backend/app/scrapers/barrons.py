"""
Barron's Hot Stocks and Premium Insights Scraper
High-quality investment news and stock picks
"""
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
import re
import feedparser


class BarronsScraper:
    """
    Scrapes Barron's for hot stocks and premium investment insights
    Barron's is known for quality financial journalism
    """

    RSS_URL = "https://feeds.barrons.com/barrons/topstories"
    WEBSITE_URL = "https://www.barrons.com/market-data"
    HOT_STOCKS_URL = "https://www.barrons.com/topics/hot-stocks"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        }

    async def scrape_rss_feed(self) -> List[Dict]:
        """
        Scrape Barron's RSS feed for top stories
        """
        try:
            stocks = []

            feed = feedparser.parse(self.RSS_URL)

            for entry in feed.entries[:30]:
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

                # Quality score (Barron's is premium content)
                quality_score = self._calculate_quality_score(title, summary)

                for ticker in tickers[:3]:
                    stocks.append({
                        'ticker': ticker,
                        'title': title,
                        'url': url,
                        'summary': summary[:300],
                        'source': 'barrons',
                        'quality_score': quality_score,
                        'published_at': published_at.isoformat(),
                        'category': self._categorize_article(title),
                        'premium': True  # Barron's is premium content
                    })

            print(f"Barron's RSS: Found {len(stocks)} items")
            return stocks

        except Exception as e:
            print(f"Error scraping Barron's RSS: {e}")
            return []

    async def scrape_hot_stocks(self) -> List[Dict]:
        """
        Scrape hot stocks section from Barron's
        """
        try:
            stocks = []

            async with aiohttp.ClientSession() as session:
                async with session.get(self.HOT_STOCKS_URL, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Find article cards
                    articles = soup.find_all(['article', 'div'], {'class': lambda x: x and 'article' in str(x).lower()}, limit=30)

                    for article in articles:
                        try:
                            # Extract title
                            title_elem = article.find(['h2', 'h3'])
                            if not title_elem:
                                continue

                            title = title_elem.get_text(strip=True)
                            if len(title) < 15:
                                continue

                            # Extract URL
                            link = article.find('a', href=True)
                            url = link['href'] if link else ''
                            if url and not url.startswith('http'):
                                url = f"https://www.barrons.com{url}"

                            # Extract tickers
                            tickers = self._extract_tickers(title + ' ' + article.get_text())

                            # Extract summary/snippet
                            summary_elem = article.find(['p', 'div'], {'class': lambda x: x and any(word in str(x).lower() for word in ['summary', 'excerpt', 'description'])})
                            summary = summary_elem.get_text(strip=True)[:300] if summary_elem else ''

                            for ticker in tickers[:2]:
                                stocks.append({
                                    'ticker': ticker,
                                    'title': title,
                                    'url': url,
                                    'summary': summary,
                                    'source': 'barrons_hot_stocks',
                                    'quality_score': self._calculate_quality_score(title, summary),
                                    'published_at': datetime.now().isoformat(),
                                    'premium': True
                                })

                        except Exception as e:
                            continue

            print(f"Barron's Hot Stocks: Found {len(stocks)} items")
            return stocks

        except Exception as e:
            print(f"Error scraping Barron's hot stocks: {e}")
            return []

    def _extract_tickers(self, text: str) -> List[str]:
        """Extract ticker symbols from text"""
        tickers = set()

        # Premium company mappings
        companies = {
            'Apple': 'AAPL', 'Microsoft': 'MSFT', 'Amazon': 'AMZN', 'Alphabet': 'GOOGL',
            'Tesla': 'TSLA', 'Meta': 'META', 'Nvidia': 'NVDA', 'Netflix': 'NFLX',
            'Berkshire': 'BRK.B', 'JPMorgan': 'JPM', 'Goldman': 'GS', 'Morgan Stanley': 'MS',
            'Visa': 'V', 'Mastercard': 'MA', 'Johnson': 'JNJ', 'Pfizer': 'PFE',
            'Exxon': 'XOM', 'Chevron': 'CVX', 'Disney': 'DIS', 'Coca-Cola': 'KO',
        }

        for company, ticker in companies.items():
            if company.lower() in text.lower():
                tickers.add(ticker)

        # Pattern matching
        patterns = [
            r'\(([A-Z]{1,5})\)',
            r'\$([A-Z]{1,5})\b',
            r'\b([A-Z]{2,5})\s+stock',
            r'\b([A-Z]{2,5})\s+shares',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if match not in ['US', 'CEO', 'IPO'] and len(match) >= 2:
                    tickers.add(match)

        return list(tickers)

    def _calculate_quality_score(self, title: str, summary: str) -> int:
        """
        Calculate quality/investment score
        Barron's content is premium, so base score is higher
        """
        score = 70  # High base score for Barron's

        text = (title + ' ' + summary).lower()

        # Investment themes
        investment_themes = ['value', 'growth', 'dividend', 'undervalued', 'opportunity']
        score += sum(10 for theme in investment_themes if theme in text)

        # Analyst insights
        analyst_keywords = ['analyst', 'rating', 'target', 'recommendation', 'outlook']
        score += sum(8 for word in analyst_keywords if word in text)

        # Strong signals
        strong_signals = ['pick', 'buy', 'top', 'best', 'winner', 'favorite']
        score += sum(5 for signal in strong_signals if signal in text)

        return min(100, score)

    def _categorize_article(self, title: str) -> str:
        """Categorize article by investment theme"""
        title_lower = title.lower()

        if any(word in title_lower for word in ['pick', 'buy', 'top', 'best']):
            return 'stock_pick'
        elif any(word in title_lower for word in ['earnings', 'results']):
            return 'earnings'
        elif any(word in title_lower for word in ['dividend', 'yield']):
            return 'income'
        elif any(word in title_lower for word in ['tech', 'ai', 'innovation']):
            return 'technology'
        elif any(word in title_lower for word in ['value', 'undervalued', 'cheap']):
            return 'value'
        else:
            return 'general'

    async def get_all_barrons_data(self, limit: int = 25) -> List[Dict]:
        """Get all Barron's data"""
        import asyncio

        rss_data, hot_stocks = await asyncio.gather(
            self.scrape_rss_feed(),
            self.scrape_hot_stocks(),
            return_exceptions=True
        )

        all_data = []
        for result in [rss_data, hot_stocks]:
            if isinstance(result, list):
                all_data.extend(result)

        # Sort by quality score
        all_data.sort(key=lambda x: x.get('quality_score', 0), reverse=True)

        # Deduplicate
        seen_tickers = set()
        unique_data = []
        for item in all_data:
            ticker = item.get('ticker')
            if ticker and ticker not in seen_tickers:
                seen_tickers.add(ticker)
                unique_data.append(item)

        return unique_data[:limit]
