import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List
import re
from app.scrapers import ScraperResult


class FinvizScraper:
    """Scrapes Finviz public news feed"""

    BASE_URL = "https://finviz.com/news.ashx"

    def __init__(self, cookie: str = None):
        self.cookie = cookie
        self.headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }
        if cookie:
            self.headers["Cookie"] = cookie

    async def scrape(self) -> List[ScraperResult]:
        """Scrape news from Finviz"""
        results = []

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(self.BASE_URL, headers=self.headers) as response:
                    if response.status != 200:
                        print(f"Finviz returned status {response.status}")
                        return results

                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")

                    # Find news rows (new HTML structure as of Feb 2026)
                    news_rows = soup.find_all("tr", {"class": "news_table-row"})

                    if not news_rows:
                        print("Finviz: Could not find news rows")
                        return results

                    print(f"Finviz: Found {len(news_rows)} raw rows")

                    for row in news_rows[:50]:  # Limit to 50 items
                        try:
                            # Find link
                            link = row.find("a", {"class": "nn-tab-link"})
                            if not link:
                                continue

                            title = link.get_text(strip=True)
                            url = link.get("href", "")

                            # Skip if no valid URL
                            if not url or url.startswith("javascript"):
                                continue

                            # Use current time (timestamps not easily accessible in new layout)
                            published_at = datetime.now()

                            # Extract tickers from title using improved NLP-like patterns
                            tickers = self._extract_tickers_from_text(title)

                            results.append(
                                ScraperResult(
                                    source="finviz",
                                    title=title,
                                    url=url,
                                    published_at=published_at,
                                    summary="",
                                    tickers=tickers,
                                )
                            )
                        except Exception as e:
                            continue  # Skip problematic rows

        except Exception as e:
            print(f"Error scraping Finviz: {e}")

        return results

    def _extract_tickers_from_text(self, text: str) -> List[str]:
        """Extract ticker symbols from text using company names + patterns"""
        tickers = set()

        # Known company name -> ticker mappings
        known_companies = {
            'Apple': 'AAPL', 'Microsoft': 'MSFT', 'Google': 'GOOGL', 'Amazon': 'AMZN',
            'Tesla': 'TSLA', 'Meta': 'META', 'Netflix': 'NFLX', 'Nvidia': 'NVDA',
            'AMD': 'AMD', 'Intel': 'INTC', 'Alphabet': 'GOOGL', 'Facebook': 'META',
            'Disney': 'DIS', 'Walmart': 'WMT', 'Target': 'TGT', 'Costco': 'COST',
            'JPMorgan': 'JPM', 'Goldman': 'GS', 'Morgan Stanley': 'MS',
            'Bank of America': 'BAC', 'Wells Fargo': 'WFC', 'Citigroup': 'C',
            'Pfizer': 'PFE', 'Moderna': 'MRNA', 'Johnson': 'JNJ', 'Merck': 'MRK',
            'Coca-Cola': 'KO', 'Pepsi': 'PEP', 'McDonald': 'MCD', 'Starbucks': 'SBUX',
            'Boeing': 'BA', 'Ford': 'F', 'GM': 'GM', 'Rivian': 'RIVN', 'Lucid': 'LCID',
            'Coinbase': 'COIN', 'PayPal': 'PYPL', 'Square': 'SQ', 'Block': 'SQ',
            'Robinhood': 'HOOD', 'Uber': 'UBER', 'Lyft': 'LYFT', 'Airbnb': 'ABNB',
            'Zoom': 'ZM', 'Salesforce': 'CRM', 'Oracle': 'ORCL', 'IBM': 'IBM',
            'Cisco': 'CSCO', 'Dell': 'DELL', 'HP': 'HPQ', 'VMware': 'VMW',
            'Visa': 'V', 'Mastercard': 'MA', 'AmEx': 'AXP', 'Discover': 'DFS',
            'Exxon': 'XOM', 'Chevron': 'CVX', 'BP': 'BP', 'Shell': 'SHEL',
            'Dow': 'DOW', 'DuPont': 'DD', '3M': 'MMM', 'Caterpillar': 'CAT',
            'Deere': 'DE', 'General Electric': 'GE', 'Honeywell': 'HON',
            'Home Depot': 'HD', 'Lowe\'s': 'LOW', 'Nike': 'NKE', 'Adidas': 'ADDYY',
        }

        for company, ticker in known_companies.items():
            if company.lower() in text.lower():
                tickers.add(ticker)

        # Pattern matching for explicit ticker mentions
        patterns = [
            r'\$([A-Z]{1,5})\b',              # $AAPL
            r'\(([A-Z]{1,5})\)',              # (AAPL)
            r'NASDAQ:([A-Z]{1,5})',           # NASDAQ:AAPL
            r'NYSE:([A-Z]{1,5})',             # NYSE:AAPL
            r'\b([A-Z]{2,5})\s+stock',        # AAPL stock
            r'\b([A-Z]{2,5})\s+shares',       # AAPL shares
            r'\b([A-Z]{2,5})\s+earnings',     # AAPL earnings
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text)
            # Filter out common false positives
            for match in matches:
                if match not in ['US', 'USD', 'UK', 'EU', 'AI', 'CEO', 'IPO', 'ETF', 'SEC']:
                    tickers.add(match)

        return list(tickers)
