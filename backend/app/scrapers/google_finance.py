"""
Google Finance Trending Stocks Scraper
Popular stocks on Google Finance with high search interest
"""
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
import re


class GoogleFinanceScraper:
    """
    Scrapes Google Finance for trending stocks
    Stocks with high retail investor interest and search volume
    """

    TRENDING_URL = "https://www.google.com/finance/markets/indexes"
    MOST_ACTIVE_URL = "https://www.google.com/finance/markets/most-active"
    GAINERS_URL = "https://www.google.com/finance/markets/gainers"
    LOSERS_URL = "https://www.google.com/finance/markets/losers"

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
        }

    async def scrape_market_section(self, url: str, section_name: str) -> List[Dict]:
        """
        Generic scraper for Google Finance market sections
        """
        try:
            stocks = []

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        print(f"Google Finance {section_name} returned status {response.status}")
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Google Finance uses specific class names for stock listings
                    # Find stock items (li or div elements)
                    items = soup.find_all(['li', 'div'], {'class': lambda x: x and any(word in str(x).lower() for word in ['stock', 'item', 'tile'])}, limit=30)

                    for item in items:
                        try:
                            # Extract ticker
                            ticker_elem = item.find(['div', 'span'], {'class': lambda x: x and 'ticker' in str(x).lower()})
                            if not ticker_elem:
                                # Alternative: look for pattern in text
                                text = item.get_text()
                                ticker_match = re.search(r'\b([A-Z]{1,5})\b', text)
                                if ticker_match:
                                    ticker = ticker_match.group(1)
                                else:
                                    continue
                            else:
                                ticker = ticker_elem.get_text(strip=True)

                            # Filter out common false positives
                            if ticker in ['US', 'USD', 'NYSE', 'NASDAQ']:
                                continue

                            # Extract price
                            price_elem = item.find(['div', 'span'], {'class': lambda x: x and 'price' in str(x).lower()})
                            price = 0.0
                            if price_elem:
                                try:
                                    price_text = price_elem.get_text(strip=True).replace('$', '').replace(',', '')
                                    price = float(price_text)
                                except:
                                    pass

                            # Extract change percent
                            change_elem = item.find(['div', 'span'], {'class': lambda x: x and any(word in str(x).lower() for word in ['change', 'percent'])})
                            change_percent = 0.0
                            if change_elem:
                                try:
                                    change_text = change_elem.get_text(strip=True)
                                    change_percent = float(change_text.replace('%', '').replace('+', '').replace(',', ''))
                                except:
                                    pass

                            # Extract company name
                            name_elem = item.find(['div', 'span'], {'class': lambda x: x and 'name' in str(x).lower()})
                            company_name = name_elem.get_text(strip=True) if name_elem else ticker

                            # Build stock data
                            stock_data = {
                                'ticker': ticker,
                                'company_name': company_name,
                                'price': price if price > 0 else None,
                                'change_percent': change_percent,
                                'source': f'google_finance_{section_name}',
                                'category': section_name,
                                'published_at': datetime.now().isoformat(),
                                'url': f"https://www.google.com/finance/quote/{ticker}:NASDAQ",
                                'retail_interest': self._calculate_retail_interest_score(section_name, change_percent)
                            }

                            stocks.append(stock_data)

                        except Exception as e:
                            continue

            print(f"Google Finance {section_name}: Found {len(stocks)} stocks")
            return stocks

        except Exception as e:
            print(f"Error scraping Google Finance {section_name}: {e}")
            return []

    async def scrape_trending_stocks(self) -> List[Dict]:
        """
        Scrape trending/most searched stocks
        """
        import asyncio

        # Scrape multiple sections in parallel
        gainers, active, trending = await asyncio.gather(
            self.scrape_market_section(self.GAINERS_URL, 'gainers'),
            self.scrape_market_section(self.MOST_ACTIVE_URL, 'most_active'),
            self.scrape_market_section(self.TRENDING_URL, 'trending'),
            return_exceptions=True
        )

        all_stocks = []
        for result in [gainers, active, trending]:
            if isinstance(result, list):
                all_stocks.extend(result)

        return all_stocks

    async def scrape_stock_news(self, ticker: str) -> List[Dict]:
        """
        Get news for a specific stock from Google Finance
        """
        try:
            news_items = []
            url = f"https://www.google.com/finance/quote/{ticker}:NASDAQ"

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=self.headers, timeout=10) as response:
                    if response.status != 200:
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Find news items on stock page
                    articles = soup.find_all(['div', 'article'], {'class': lambda x: x and 'news' in str(x).lower()}, limit=10)

                    for article in articles:
                        try:
                            # Extract title
                            title_elem = article.find(['div', 'h3', 'h4'])
                            if not title_elem:
                                continue

                            title = title_elem.get_text(strip=True)
                            if len(title) < 10:
                                continue

                            # Extract URL
                            link = article.find('a', href=True)
                            news_url = link['href'] if link else ''

                            # Extract source
                            source_elem = article.find(['div', 'span'], {'class': lambda x: x and 'source' in str(x).lower()})
                            news_source = source_elem.get_text(strip=True) if source_elem else 'google_finance'

                            news_items.append({
                                'ticker': ticker,
                                'title': title,
                                'url': news_url,
                                'news_source': news_source,
                                'source': 'google_finance',
                                'published_at': datetime.now().isoformat()
                            })

                        except Exception as e:
                            continue

            return news_items

        except Exception as e:
            print(f"Error scraping Google Finance news for {ticker}: {e}")
            return []

    def _calculate_retail_interest_score(self, category: str, change_percent: float) -> int:
        """
        Calculate retail investor interest score
        Google Finance reflects retail investor attention
        """
        score = 50  # Base score

        # Category bonus
        if category == 'gainers':
            score += 25
        elif category == 'most_active':
            score += 30  # High retail interest
        elif category == 'trending':
            score += 35  # Very high interest

        # Price movement bonus
        if abs(change_percent) >= 10:
            score += 20
        elif abs(change_percent) >= 5:
            score += 15
        elif abs(change_percent) >= 3:
            score += 10

        return min(100, score)

    async def get_all_google_finance_data(self, limit: int = 30) -> List[Dict]:
        """
        Get all Google Finance trending data
        Returns deduplicated list sorted by retail interest
        """
        stocks = await self.scrape_trending_stocks()

        # Sort by retail interest score
        stocks.sort(key=lambda x: x.get('retail_interest', 0), reverse=True)

        # Deduplicate by ticker (keep highest score)
        seen_tickers = set()
        unique_stocks = []
        for stock in stocks:
            ticker = stock['ticker']
            if ticker not in seen_tickers:
                seen_tickers.add(ticker)
                unique_stocks.append(stock)

        return unique_stocks[:limit]
