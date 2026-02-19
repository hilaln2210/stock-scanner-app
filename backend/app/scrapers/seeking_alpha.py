"""
Seeking Alpha Trending Stocks Scraper
Scrapes trending stocks, top articles, and market insights
"""
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
import re


class SeekingAlphaScraper:
    """
    Scrapes Seeking Alpha for trending stocks and top articles
    Focuses on stocks with high analyst attention and article coverage
    """

    TRENDING_URL = "https://seekingalpha.com/market-news/trending"
    TOP_NEWS_URL = "https://seekingalpha.com/market-news/all"
    MARKET_MOVING_URL = "https://seekingalpha.com/market-news/on-the-move"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
        }
        self.ticker_pattern = re.compile(r'\b([A-Z]{1,5})\b')

    async def scrape_trending_stocks(self) -> List[Dict]:
        """
        Scrape trending stocks from Seeking Alpha
        Returns list of stocks with high article coverage
        """
        try:
            trending_stocks = []

            # Scrape multiple sources
            sources = [
                (self.TRENDING_URL, 'trending'),
                (self.MARKET_MOVING_URL, 'on_the_move'),
                (self.TOP_NEWS_URL, 'top_news')
            ]

            async with aiohttp.ClientSession() as session:
                for url, source_type in sources:
                    try:
                        async with session.get(url, headers=self.headers, timeout=10) as response:
                            if response.status != 200:
                                print(f"Seeking Alpha {source_type} returned status {response.status}")
                                continue

                            html = await response.text()
                            soup = BeautifulSoup(html, 'html.parser')

                            # Find article cards/links
                            articles = soup.find_all('article', limit=30)
                            if not articles:
                                # Try alternative selector
                                articles = soup.find_all('div', {'class': lambda x: x and 'article' in str(x).lower()}, limit=30)

                            for article in articles:
                                try:
                                    # Extract title
                                    title_elem = article.find(['h2', 'h3', 'a'])
                                    if not title_elem:
                                        continue

                                    title = title_elem.get_text(strip=True)
                                    if len(title) < 10:
                                        continue

                                    # Extract URL
                                    link = article.find('a', href=True)
                                    url = link['href'] if link else ''
                                    if url and not url.startswith('http'):
                                        url = f"https://seekingalpha.com{url}"

                                    # Extract tickers from title and article
                                    article_text = article.get_text()
                                    tickers = self._extract_tickers(title + ' ' + article_text)

                                    if not tickers:
                                        continue

                                    # Calculate relevance score
                                    relevance_score = self._calculate_relevance_score(title, source_type)

                                    for ticker in tickers[:3]:  # Max 3 tickers per article
                                        trending_stocks.append({
                                            'ticker': ticker,
                                            'title': title,
                                            'url': url,
                                            'source': f'seeking_alpha_{source_type}',
                                            'relevance_score': relevance_score,
                                            'published_at': datetime.now().isoformat(),
                                            'category': self._categorize_news(title)
                                        })

                                except Exception as e:
                                    continue

                    except Exception as e:
                        print(f"Error scraping Seeking Alpha {source_type}: {e}")
                        continue

            print(f"Seeking Alpha: Found {len(trending_stocks)} trending stocks")
            return trending_stocks

        except Exception as e:
            print(f"Error in Seeking Alpha scraper: {e}")
            return []

    def _extract_tickers(self, text: str) -> List[str]:
        """Extract ticker symbols from text"""
        tickers = set()

        # Known company name mappings (extended list)
        company_map = {
            'Apple': 'AAPL', 'Microsoft': 'MSFT', 'Amazon': 'AMZN', 'Google': 'GOOGL',
            'Alphabet': 'GOOGL', 'Tesla': 'TSLA', 'Meta': 'META', 'Facebook': 'META',
            'Nvidia': 'NVDA', 'AMD': 'AMD', 'Intel': 'INTC', 'Netflix': 'NFLX',
            'Palantir': 'PLTR', 'Coinbase': 'COIN', 'Uber': 'UBER', 'Airbnb': 'ABNB',
            'Snowflake': 'SNOW', 'CrowdStrike': 'CRWD', 'ServiceNow': 'NOW',
            'Salesforce': 'CRM', 'Oracle': 'ORCL', 'Adobe': 'ADBE', 'Zoom': 'ZM',
            'Spotify': 'SPOT', 'Block': 'SQ', 'Square': 'SQ', 'PayPal': 'PYPL',
            'Visa': 'V', 'Mastercard': 'MA', 'JPMorgan': 'JPM', 'Goldman': 'GS',
            'Morgan Stanley': 'MS', 'Bank of America': 'BAC', 'Citigroup': 'C',
            'Boeing': 'BA', 'Lockheed': 'LMT', 'Raytheon': 'RTX', 'Northrop': 'NOC',
            'Pfizer': 'PFE', 'Moderna': 'MRNA', 'BioNTech': 'BNTX', 'Johnson': 'JNJ',
            'Eli Lilly': 'LLY', 'Merck': 'MRK', 'AbbVie': 'ABBV', 'Bristol': 'BMY',
            'Walmart': 'WMT', 'Target': 'TGT', 'Costco': 'COST', 'Home Depot': 'HD',
            'Lowes': 'LOW', 'Nike': 'NKE', 'Starbucks': 'SBUX', 'McDonald': 'MCD',
            'Chipotle': 'CMG', 'Domino': 'DPZ', 'Yum': 'YUM', 'Pepsi': 'PEP',
            'Coca-Cola': 'KO', 'Mondelez': 'MDLZ', 'General Mills': 'GIS',
            'Ford': 'F', 'GM': 'GM', 'Rivian': 'RIVN', 'Lucid': 'LCID', 'NIO': 'NIO',
            'Exxon': 'XOM', 'Chevron': 'CVX', 'ConocoPhillips': 'COP', 'Shell': 'SHEL',
            'AT&T': 'T', 'Verizon': 'VZ', 'T-Mobile': 'TMUS', 'Comcast': 'CMCSA',
            'Disney': 'DIS', 'Warner': 'WBD', 'Paramount': 'PARA', 'Fox': 'FOX',
        }

        # Check for company names
        for company, ticker in company_map.items():
            if company.lower() in text.lower():
                tickers.add(ticker)

        # Pattern matching for explicit ticker mentions
        patterns = [
            r'\(([A-Z]{1,5})\)',                    # (AAPL)
            r'\$([A-Z]{1,5})\b',                    # $AAPL
            r'NASDAQ:([A-Z]{1,5})',                 # NASDAQ:AAPL
            r'NYSE:([A-Z]{1,5})',                   # NYSE:AAPL
            r'\b([A-Z]{2,5})\s+stock',              # AAPL stock
            r'\b([A-Z]{2,5})\s+shares',             # AAPL shares
            r'\b([A-Z]{2,5})\s+earnings',           # AAPL earnings
            r'\b([A-Z]{2,5}):\s',                   # AAPL: title format
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                # Filter false positives
                if match not in ['US', 'USD', 'UK', 'EU', 'AI', 'CEO', 'CFO', 'IPO', 'ETF', 'SEC', 'FDA', 'API', 'AWS', 'IT', 'PC', 'TV', 'EV']:
                    if len(match) >= 2:
                        tickers.add(match)

        return list(tickers)

    def _calculate_relevance_score(self, title: str, source_type: str) -> int:
        """Calculate relevance score based on keywords and source"""
        score = 50  # Base score

        title_lower = title.lower()

        # Source type bonus
        if source_type == 'trending':
            score += 20
        elif source_type == 'on_the_move':
            score += 25
        elif source_type == 'top_news':
            score += 15

        # Positive catalysts
        positive_keywords = [
            'surge', 'rally', 'breakout', 'upgrade', 'bullish', 'soar', 'jump',
            'beat', 'exceeds', 'approval', 'deal', 'partnership', 'breakthrough',
            'record', 'all-time high', 'strong', 'outperform', 'buy rating'
        ]
        score += sum(10 for keyword in positive_keywords if keyword in title_lower)

        # High attention indicators
        attention_keywords = ['analyst', 'rating', 'forecast', 'guidance', 'earnings', 'results']
        score += sum(5 for keyword in attention_keywords if keyword in title_lower)

        return min(100, score)

    def _categorize_news(self, title: str) -> str:
        """Categorize news article by type"""
        title_lower = title.lower()

        if any(word in title_lower for word in ['earnings', 'revenue', 'profit', 'results']):
            return 'earnings'
        elif any(word in title_lower for word in ['upgrade', 'downgrade', 'rating', 'analyst']):
            return 'analyst_rating'
        elif any(word in title_lower for word in ['deal', 'merger', 'acquisition', 'partnership']):
            return 'ma_activity'
        elif any(word in title_lower for word in ['fda', 'approval', 'clinical', 'trial']):
            return 'regulatory'
        elif any(word in title_lower for word in ['dividend', 'buyback', 'split']):
            return 'corporate_action'
        elif any(word in title_lower for word in ['guidance', 'forecast', 'outlook']):
            return 'guidance'
        else:
            return 'general'

    async def get_trending_stocks(self, limit: int = 30) -> List[Dict]:
        """
        Main method to get trending stocks from Seeking Alpha
        Returns enriched data sorted by relevance
        """
        stocks = await self.scrape_trending_stocks()

        # Sort by relevance score
        stocks.sort(key=lambda x: x.get('relevance_score', 0), reverse=True)

        # Deduplicate by ticker (keep highest score)
        seen_tickers = set()
        unique_stocks = []
        for stock in stocks:
            ticker = stock['ticker']
            if ticker not in seen_tickers:
                seen_tickers.add(ticker)
                unique_stocks.append(stock)

        return unique_stocks[:limit]
