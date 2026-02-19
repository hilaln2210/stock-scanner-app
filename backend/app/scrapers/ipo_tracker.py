import aiohttp
from datetime import datetime, timedelta
from typing import List, Dict
from bs4 import BeautifulSoup


class IPOTracker:
    """Tracks IPOs and provides analysis"""

    def __init__(self):
        self.ipo_cache = {}

    async def get_upcoming_ipos(self, days_back: int = 7, days_forward: int = 7) -> List[Dict]:
        """
        Get IPOs from the past week and upcoming week
        Returns: list of IPO dicts with expected vs actual price, insights
        """
        try:
            # Use multiple sources for IPO data
            ipos = []

            # Try NASDAQ IPO calendar
            nasdaq_ipos = await self._scrape_nasdaq_ipos(days_back=days_back, days_forward=days_forward)
            ipos.extend(nasdaq_ipos)

            # Try Yahoo Finance IPO calendar
            yahoo_ipos = await self._scrape_yahoo_ipos(days_back=days_back, days_forward=days_forward)
            ipos.extend(yahoo_ipos)

            # Add analysis and insights
            for ipo in ipos:
                ipo['insights'] = self._generate_ipo_insights(ipo)

            # Sort by date (most recent first)
            ipos.sort(key=lambda x: x.get('date', ''), reverse=True)

            print(f"IPO Tracker: Found {len(ipos)} IPOs")
            return ipos

        except Exception as e:
            print(f"Error fetching IPOs: {e}")
            return []

    async def get_todays_ipos(self) -> List[Dict]:
        """Legacy method - now returns upcoming IPOs"""
        return await self.get_upcoming_ipos()

    async def _scrape_nasdaq_ipos(self, days_back: int = 7, days_forward: int = 7) -> List[Dict]:
        """Scrape NASDAQ IPO calendar"""
        try:
            url = "https://www.nasdaq.com/market-activity/ipos"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return []

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    ipos = []
                    # Calculate date range
                    today = datetime.now().date()
                    start_date = today - timedelta(days=days_back)
                    end_date = today + timedelta(days=days_forward)

                    # Find IPO table rows
                    rows = soup.find_all('tr', {'class': lambda x: x and 'ipo-row' in str(x)})

                    for row in rows:
                        try:
                            cols = row.find_all('td')
                            if len(cols) < 5:
                                continue

                            ticker = cols[0].text.strip()
                            company = cols[1].text.strip()
                            expected_price_range = cols[2].text.strip()
                            shares = cols[3].text.strip()
                            date_str = cols[4].text.strip()

                            # Parse and check date range
                            try:
                                ipo_date = datetime.strptime(date_str, '%m/%d/%Y').date()
                                if not (start_date <= ipo_date <= end_date):
                                    continue
                            except:
                                continue
                                # Parse price range (e.g., "$15.00 - $17.00")
                                expected_low, expected_high = self._parse_price_range(expected_price_range)

                                ipo_data = {
                                    'ticker': ticker,
                                    'company': company,
                                    'expected_low': expected_low,
                                    'expected_high': expected_high,
                                    'expected_midpoint': (expected_low + expected_high) / 2 if expected_low and expected_high else 0,
                                    'shares': shares,
                                    'date': date_str,
                                    'actual_price': 0,  # Will be updated
                                    'source': 'NASDAQ'
                                }

                                # Try to get actual opening price
                                actual = await self._get_actual_ipo_price(ticker)
                                if actual:
                                    ipo_data['actual_price'] = actual
                                    ipo_data['price_vs_expected'] = self._calculate_price_difference(
                                        actual, ipo_data['expected_midpoint']
                                    )

                                ipos.append(ipo_data)

                        except Exception as e:
                            continue

                    return ipos

        except Exception as e:
            print(f"Error scraping NASDAQ IPOs: {e}")
            return []

    async def _scrape_yahoo_ipos(self, days_back: int = 7, days_forward: int = 7) -> List[Dict]:
        """Scrape Yahoo Finance IPO calendar"""
        try:
            # Yahoo Finance has a simpler JSON API for IPOs
            url = "https://query2.finance.yahoo.com/v1/finance/ipos"
            params = {
                "formatted": "false",
                "start": 0,
                "size": 100
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return []

                    data = await response.json()
                    ipo_list = data.get('data', {}).get('ipoCalendar', [])

                    ipos = []
                    today = datetime.now().date()
                    start_date = today - timedelta(days=days_back)
                    end_date = today + timedelta(days=days_forward)

                    for ipo_item in ipo_list:
                        try:
                            # Check if IPO date is in range
                            ipo_date_str = ipo_item.get('pricedDate', '')
                            if not ipo_date_str:
                                continue

                            ipo_date = datetime.fromtimestamp(int(ipo_date_str)).date()
                            if not (start_date <= ipo_date <= end_date):
                                continue

                            ticker = ipo_item.get('ticker', '')
                            company = ipo_item.get('companyName', '')
                            price_low = float(ipo_item.get('priceLow', 0))
                            price_high = float(ipo_item.get('priceHigh', 0))
                            shares_offered = ipo_item.get('sharesOffered', '0')

                            ipo_data = {
                                'ticker': ticker,
                                'company': company,
                                'expected_low': price_low,
                                'expected_high': price_high,
                                'expected_midpoint': (price_low + price_high) / 2 if price_low and price_high else 0,
                                'shares': shares_offered,
                                'date': ipo_date.strftime('%m/%d/%Y'),
                                'actual_price': 0,
                                'source': 'Yahoo'
                            }

                            # Get actual price
                            actual = await self._get_actual_ipo_price(ticker)
                            if actual:
                                ipo_data['actual_price'] = actual
                                ipo_data['price_vs_expected'] = self._calculate_price_difference(
                                    actual, ipo_data['expected_midpoint']
                                )

                            ipos.append(ipo_data)

                        except Exception as e:
                            continue

                    return ipos

        except Exception as e:
            print(f"Error scraping Yahoo IPOs: {e}")
            return []

    async def _get_actual_ipo_price(self, ticker: str) -> float:
        """Get the actual opening/current price of an IPO"""
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
            params = {
                "interval": "1d",
                "range": "1d"
            }

            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                    if response.status != 200:
                        return 0

                    data = await response.json()
                    result = data.get('chart', {}).get('result', [{}])[0]
                    meta = result.get('meta', {})

                    # Get regular market price (current price)
                    current_price = meta.get('regularMarketPrice', 0)
                    return float(current_price) if current_price else 0

        except Exception as e:
            return 0

    def _parse_price_range(self, price_range_str: str) -> tuple:
        """Parse price range string like '$15.00 - $17.00' to (15.0, 17.0)"""
        try:
            # Remove $ and split on -
            cleaned = price_range_str.replace('$', '').replace(',', '')
            parts = cleaned.split('-')

            if len(parts) == 2:
                low = float(parts[0].strip())
                high = float(parts[1].strip())
                return (low, high)

            # If single price
            price = float(cleaned.strip())
            return (price, price)

        except:
            return (0, 0)

    def _calculate_price_difference(self, actual: float, expected: float) -> Dict:
        """Calculate how actual price compares to expected"""
        if not actual or not expected:
            return {'percent': 0, 'direction': 'unknown'}

        diff_percent = ((actual - expected) / expected) * 100

        return {
            'percent': round(diff_percent, 2),
            'direction': 'above' if diff_percent > 0 else 'below' if diff_percent < 0 else 'at',
            'amount': round(actual - expected, 2)
        }

    def _generate_ipo_insights(self, ipo: Dict) -> List[str]:
        """Generate insights and lessons from IPO data"""
        insights = []

        if not ipo.get('actual_price') or not ipo.get('expected_midpoint'):
            insights.append("⏳ IPO not yet priced - waiting for market open")
            return insights

        price_diff = ipo.get('price_vs_expected', {})
        percent = price_diff.get('percent', 0)

        # Price performance insights
        if percent > 20:
            insights.append("🚀 Strong debut! Opened >20% above expected - high demand")
            insights.append("💡 Lesson: Underwriters likely underpriced to generate excitement")
        elif percent > 10:
            insights.append("📈 Solid debut - opened 10-20% above range")
            insights.append("💡 Lesson: Healthy institutional demand")
        elif percent > 0:
            insights.append("✅ Opened above expected range - positive reception")
        elif percent < -10:
            insights.append("📉 Weak debut - opened >10% below expected")
            insights.append("⚠️ Warning: Market skepticism or poor timing")
        elif percent < 0:
            insights.append("⚡ Opened below expected range - cautious market")

        # Market cap insights
        actual_price = ipo.get('actual_price', 0)
        if actual_price > 0:
            try:
                shares_str = str(ipo.get('shares', '0'))
                shares_num = float(shares_str.replace('M', '000000').replace('K', '000').replace(',', ''))
                market_cap = actual_price * shares_num

                if market_cap > 10_000_000_000:
                    insights.append(f"💰 Large cap IPO - valuation ${market_cap/1_000_000_000:.1f}B")
                elif market_cap > 1_000_000_000:
                    insights.append(f"💼 Mid cap IPO - valuation ${market_cap/1_000_000_000:.1f}B")
                else:
                    insights.append(f"🏪 Small cap IPO - valuation ${market_cap/1_000_000:.0f}M")
            except:
                pass

        # Timing insights
        insights.append("📅 Fresh IPO - watch for volatility in first days/weeks")

        return insights
