import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict
import re


class MarketPulseScraper:
    """Scrapes Finviz Elite Market Pulse for high-momentum stocks"""

    ELITE_URL = "https://elite.finviz.com/news.ashx?v=6"

    def __init__(self, email: str = None, password: str = None, cookie: str = None):
        self.email = email
        self.password = password
        self.cookie = cookie
        self.session = None

    async def login_and_get_cookie(self, session: aiohttp.ClientSession) -> str:
        """Login to Finviz Elite and get session cookie"""
        if not self.email or not self.password:
            return None

        try:
            login_url = "https://elite.finviz.com/login_submit.ashx"
            login_data = {
                "email": self.email,
                "password": self.password,
                "remember": "on"
            }
            headers = {
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://elite.finviz.com/login.ashx"
            }

            async with session.post(login_url, data=login_data, headers=headers, allow_redirects=True) as response:
                if response.status == 200:
                    # Get cookies from session
                    cookies = session.cookie_jar.filter_cookies("https://elite.finviz.com")
                    cookie_str = "; ".join([f"{cookie.key}={cookie.value}" for cookie in cookies.values()])
                    return cookie_str
        except Exception as e:
            print(f"Login failed: {e}")

        return None

    async def scrape_market_pulse(self) -> List[Dict]:
        """
        Scrape Market Pulse for stocks with high momentum
        Returns: List of stocks with momentum data
        """
        results = []

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }

                # Try to login if credentials provided
                if self.email and self.password and not self.cookie:
                    print("Attempting to login to Finviz Elite...")
                    self.cookie = await self.login_and_get_cookie(session)
                    if self.cookie:
                        print("Login successful!")

                # Add cookie if available
                if self.cookie:
                    headers["Cookie"] = self.cookie

                async with session.get(self.ELITE_URL, headers=headers) as response:
                    if response.status != 200:
                        print(f"Market Pulse returned status {response.status}")
                        return results

                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")

                    # Debug: Check what we got
                    print(f"Market Pulse: Response status {response.status}, HTML length: {len(html)}")

                    # Try multiple selectors for news items
                    news_items = soup.find_all("tr", {"class": ["nn-row-odd", "nn-row-even"]})
                    if not news_items:
                        # Try alternative selector
                        news_items = soup.find_all("tr", class_=lambda x: x and 'news' in x.lower())
                    if not news_items:
                        # Try finding any table rows with links
                        news_items = soup.find_all("tr")

                    print(f"Market Pulse: Found {len(news_items)} potential news items")

                    processed = 0
                    for item in news_items[:100]:  # Process top 100 items
                        try:
                            # Market Pulse structure: ticker link + text in different elements
                            ticker_link = item.find("a", class_=lambda x: x and 'ticker' in str(x).lower())
                            if not ticker_link:
                                # Try finding link with ticker pattern
                                ticker_link = item.find("a")

                            if not ticker_link:
                                continue

                            # Extract ticker from link text (format: "MARA+6.98%" or just "MARA")
                            ticker_text = ticker_link.get_text(strip=True)
                            ticker_match = re.match(r'([A-Z]{1,5})', ticker_text)
                            if not ticker_match:
                                continue

                            ticker = ticker_match.group(1)

                            # Extract price change ONLY from ticker link (not from title!)
                            # Format: "MARA+6.98%" or "MGM-2.5%"
                            price_change = 0.0
                            # Only get percentage that's directly attached to ticker
                            change_match = re.match(r'[A-Z]{1,5}([+-]\d+\.\d+)%', ticker_text)
                            if change_match:
                                price_change = float(change_match.group(1))

                            # Find title - usually in same row, after ticker
                            title = ""
                            # Try to get text from the whole row, excluding the ticker
                            row_text = item.get_text(separator=" ", strip=True)
                            # Remove ticker and percentage from text
                            title = re.sub(r'^[A-Z]{1,5}[+-]?\d*\.?\d*%?\s*', '', row_text)

                            if not title or len(title) < 10:
                                # Try finding adjacent text elements
                                text_elems = item.find_all(text=True, recursive=False)
                                if text_elems:
                                    title = " ".join([t.strip() for t in text_elems if len(t.strip()) > 10])

                            if not title:
                                continue

                            # Get URL - try to find news link
                            url = ticker_link.get("href", "")
                            if not url.startswith("http"):
                                # Look for other links in row
                                other_links = item.find_all("a")
                                for link in other_links:
                                    href = link.get("href", "")
                                    if href and href.startswith("http"):
                                        url = href
                                        break

                            tickers = [ticker]

                            # Extract time
                            time_elem = item.find("td", {"class": "nn-date"})
                            time_str = time_elem.get_text(strip=True) if time_elem else ""

                            # Parse time (format: "Feb-05-26 11:30PM")
                            published_at = self._parse_time(time_str)

                            # Calculate momentum score based on keywords
                            momentum_score = self._calculate_momentum_score(title)

                            # Note: price_change already extracted from ticker_text above
                            # We DON'T extract from title - percentages there are often YoY earnings, not price changes

                            for ticker in tickers[:3]:  # Limit to 3 tickers per news
                                if len(ticker) >= 2 and ticker not in ['US', 'USD', 'UK', 'CEO', 'IPO', 'ETF']:
                                    results.append({
                                        "ticker": ticker,
                                        "title": title,
                                        "url": url,
                                        "published_at": published_at,
                                        "momentum_score": momentum_score,
                                        "price_change": price_change,
                                        "source": "finviz_elite_pulse"
                                    })
                                    processed += 1

                        except Exception as e:
                            if processed < 5:
                                print(f"Error processing item: {e}")
                            continue

                    print(f"Market Pulse: Processed {processed} items, got {len(results)} results")

        except Exception as e:
            print(f"Error scraping Market Pulse: {e}")

        return results

    def _parse_time(self, time_str: str) -> datetime:
        """Parse Finviz time format"""
        try:
            # Try parsing formats like "Feb-05-26 11:30PM"
            if time_str:
                # Simple fallback - use current time
                return datetime.now()
        except:
            pass
        return datetime.now()

    def _calculate_momentum_score(self, text: str) -> int:
        """
        Calculate momentum score (0-100) based on keywords
        High scores = strong momentum indicators
        """
        text_lower = text.lower()
        score = 50  # Base score

        # High momentum keywords
        high_momentum = [
            "surge", "soar", "rocket", "explode", "breakout", "all-time high",
            "record high", "rally", "jump", "spike", "skyrocket", "climbs",
            "pops", "moon", "parabolic", "massive gain"
        ]

        # Volume/momentum indicators
        volume_keywords = [
            "unusual volume", "heavy volume", "volume spike", "massive volume",
            "trading activity", "high volume"
        ]

        # Positive catalysts
        catalysts = [
            "beat", "exceeds", "upgrade", "approval", "breakthrough", "partnership",
            "contract", "revenue", "earnings beat", "guidance raise"
        ]

        # Count momentum indicators
        high_momentum_count = sum(1 for word in high_momentum if word in text_lower)
        volume_count = sum(1 for word in volume_keywords if word in text_lower)
        catalyst_count = sum(1 for word in catalysts if word in text_lower)

        # Calculate final score
        score += high_momentum_count * 15
        score += volume_count * 12
        score += catalyst_count * 8

        # Negative indicators reduce score
        negative = ["fall", "drop", "plunge", "crash", "decline", "miss", "downgrade"]
        negative_count = sum(1 for word in negative if word in text_lower)
        score -= negative_count * 10

        return max(0, min(100, score))

    def _extract_price_change(self, text: str) -> float:
        """Extract price change percentage from text"""
        try:
            # Look for patterns like "+15%", "up 20%", "gains 10%"
            patterns = [
                r'[\+\-](\d+\.?\d*)%',
                r'up (\d+\.?\d*)%',
                r'down (\d+\.?\d*)%',
                r'gains? (\d+\.?\d*)%',
                r'drops? (\d+\.?\d*)%'
            ]

            for pattern in patterns:
                match = re.search(pattern, text.lower())
                if match:
                    change = float(match.group(1))
                    # Determine sign
                    if 'down' in text.lower() or 'drop' in text.lower() or 'fall' in text.lower():
                        return -change
                    return change
        except:
            pass
        return 0.0


async def get_high_momentum_stocks(limit: int = 50, email: str = None, password: str = None, cookie: str = None) -> List[Dict]:
    """
    Get high momentum stocks from Market Pulse
    Returns top momentum stocks sorted by score
    """
    scraper = MarketPulseScraper(email=email, password=password, cookie=cookie)
    stocks = await scraper.scrape_market_pulse()

    # Filter high momentum only (score > 60)
    high_momentum = [s for s in stocks if s["momentum_score"] > 60]

    # Sort by momentum score (descending)
    high_momentum.sort(key=lambda x: x["momentum_score"], reverse=True)

    # Deduplicate by ticker (keep highest score)
    seen_tickers = set()
    unique_stocks = []
    for stock in high_momentum:
        if stock["ticker"] not in seen_tickers:
            seen_tickers.add(stock["ticker"])
            unique_stocks.append(stock)

    return unique_stocks[:limit]
