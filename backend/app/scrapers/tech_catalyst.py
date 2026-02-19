"""
Tech Catalyst Scraper — Upcoming earnings, product launches, conferences for tech stocks.

Uses yfinance for earnings dates and Yahoo Finance earnings calendar.
Returns events in the same shape as FDA calendar events for unified handling.
"""

import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import re
import asyncio
import time
import yfinance as yf
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout


# Major tech stocks to track for catalysts
TECH_WATCHLIST = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD', 'INTC',
    'CRM', 'ORCL', 'ADBE', 'NOW', 'SNOW', 'PLTR', 'NET', 'DDOG', 'ZS', 'CRWD',
    'PANW', 'FTNT', 'MDB', 'SHOP', 'SQ', 'PYPL', 'COIN', 'UBER', 'ABNB', 'DASH',
    'NFLX', 'DIS', 'SPOT', 'RBLX', 'U', 'SNAP', 'PINS', 'TWLO', 'OKTA', 'DOCU',
    'SNDK', 'WDC', 'STX', 'MU', 'QCOM', 'AVGO', 'TXN', 'MRVL', 'LRCX', 'KLAC',
    'ASML', 'TSM', 'ARM', 'SMCI', 'DELL', 'HPQ', 'IBM', 'CSCO', 'ANET',
    'AI', 'PATH', 'S', 'IOT', 'CFLT', 'ESTC', 'BILL', 'HUBS', 'VEEV',
    'TTD', 'ROKU', 'ZM', 'TEAM', 'GDDY', 'WDAY', 'INTU', 'ADSK', 'ANSS',
    'MSTR', 'RIOT', 'MARA', 'CLSK', 'BITF',
]


class TechCatalystScraper:
    CACHE_TTL = 900  # 15 minutes
    MAX_CONCURRENT = 3

    def __init__(self):
        self._cache: List[Dict] = []
        self._cache_time: float = 0
        self._yf_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='tech_cat')
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }

    async def get_tech_catalyst_events(self, days_forward: int = 90) -> List[Dict]:
        """Main entry point. Returns tech stock catalyst events."""
        now = time.time()
        if self._cache and (now - self._cache_time) < self.CACHE_TTL:
            return self._cache

        tasks = [
            self._get_earnings_dates(),
            self._scrape_yahoo_earnings_calendar(),
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_events = []
        for result in results:
            if isinstance(result, list):
                all_events.extend(result)

        # Deduplicate
        seen = {}
        for event in all_events:
            ticker = event.get('ticker', '')
            date = event.get('catalyst_date', '')
            key = (ticker, date)
            if key not in seen:
                seen[key] = event
            else:
                # Merge
                existing = seen[key]
                for field in ['company', 'catalyst_type']:
                    if not existing.get(field) and event.get(field):
                        existing[field] = event[field]

        # Filter by date range
        now_date = datetime.now()
        end_date = now_date + timedelta(days=days_forward)

        filtered = []
        for event in seen.values():
            try:
                if event.get('catalyst_date'):
                    event_date = datetime.strptime(event['catalyst_date'], '%Y-%m-%d')
                    event['days_until'] = (event_date - now_date).days
                    if event['days_until'] >= -7 and event_date <= end_date:
                        filtered.append(event)
                else:
                    filtered.append(event)
            except (ValueError, KeyError):
                filtered.append(event)

        filtered.sort(key=lambda x: abs(x.get('days_until') or 9999))

        self._cache = filtered
        self._cache_time = time.time()
        print(f"Tech Catalysts: {len(filtered)} events")
        return filtered

    async def _get_earnings_dates(self) -> List[Dict]:
        """Get earnings dates for tech watchlist using yfinance.
        Uses batches to avoid overwhelming yfinance."""
        events = []
        sem = asyncio.Semaphore(self.MAX_CONCURRENT)
        found_count = 0

        async def fetch_one(ticker: str, idx: int):
            nonlocal found_count
            async with sem:
                # Stagger within each batch, not globally
                await asyncio.sleep((idx % self.MAX_CONCURRENT) * 0.15)
                try:
                    loop = asyncio.get_event_loop()
                    result = await asyncio.wait_for(
                        loop.run_in_executor(self._yf_executor, self._get_ticker_earnings_sync, ticker),
                        timeout=5
                    )
                    if result:
                        found_count += len(result)
                    return result
                except asyncio.TimeoutError:
                    return []
                except Exception:
                    return []

        try:
            print(f"Tech: Fetching earnings for {len(TECH_WATCHLIST)} tickers...")
            tasks = [fetch_one(t, i) for i, t in enumerate(TECH_WATCHLIST)]
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=90
            )

            for result in results:
                if isinstance(result, list):
                    events.extend(result)
            print(f"Tech: Found {found_count} earnings events from yfinance")
        except asyncio.TimeoutError:
            print(f"Tech earnings fetch OVERALL TIMEOUT (got {found_count} so far)")

        return events

    def _get_ticker_earnings_sync(self, ticker: str) -> List[Dict]:
        """Synchronous yfinance call to get earnings date for a ticker.
        Skips stock.info (too slow/hangs). Company name comes from Finviz enrichment later."""
        events = []
        try:
            stock = yf.Ticker(ticker)

            # Get calendar (earnings date) — skip stock.info, it hangs
            try:
                cal = stock.calendar
                if cal is not None:
                    if isinstance(cal, dict):
                        earnings_date = cal.get('Earnings Date', [])
                        if isinstance(earnings_date, list) and earnings_date:
                            for ed in earnings_date[:2]:
                                date_str = ''
                                if hasattr(ed, 'strftime'):
                                    date_str = ed.strftime('%Y-%m-%d')
                                elif isinstance(ed, str):
                                    date_str = ed[:10]

                                if date_str:
                                    events.append({
                                        'ticker': ticker,
                                        'company': ticker,
                                        'drug_name': '',
                                        'indication': 'Quarterly Earnings Report',
                                        'catalyst_type': 'Earnings',
                                        'catalyst_date': date_str,
                                        'phase': '',
                                        'status': 'Upcoming',
                                        'source': 'yfinance',
                                        'source_url': f'https://finance.yahoo.com/quote/{ticker}',
                                    })

                        # Ex-dividend date
                        ex_div = cal.get('Ex-Dividend Date')
                        if ex_div:
                            date_str = ''
                            if hasattr(ex_div, 'strftime'):
                                date_str = ex_div.strftime('%Y-%m-%d')
                            elif isinstance(ex_div, str):
                                date_str = ex_div[:10]
                            if date_str:
                                events.append({
                                    'ticker': ticker,
                                    'company': ticker,
                                    'drug_name': '',
                                    'indication': 'Ex-Dividend Date',
                                    'catalyst_type': 'Dividend',
                                    'catalyst_date': date_str,
                                    'phase': '',
                                    'status': 'Upcoming',
                                    'source': 'yfinance',
                                    'source_url': f'https://finance.yahoo.com/quote/{ticker}',
                                })
            except Exception as e:
                print(f"  Tech calendar error {ticker}: {e}")

        except Exception as e:
            print(f"  Tech ticker error {ticker}: {e}")

        return events

    async def _scrape_yahoo_earnings_calendar(self) -> List[Dict]:
        """Scrape Yahoo Finance earnings calendar for upcoming tech earnings."""
        events = []
        # Check next 7 days of earnings
        today = datetime.now()

        for day_offset in range(0, 14):
            date = today + timedelta(days=day_offset)
            date_str = date.strftime('%Y-%m-%d')

            try:
                url = f"https://finance.yahoo.com/calendar/earnings?day={date_str}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, headers=self.headers,
                                           timeout=aiohttp.ClientTimeout(total=10)) as response:
                        if response.status != 200:
                            continue

                        html = await response.text()
                        soup = BeautifulSoup(html, 'html.parser')

                        # Find earnings table
                        table = soup.find('table')
                        if not table:
                            continue

                        rows = table.find_all('tr')
                        for row in rows[1:]:  # Skip header
                            cells = row.find_all('td')
                            if len(cells) < 3:
                                continue

                            ticker = cells[0].get_text(strip=True)
                            company = cells[1].get_text(strip=True) if len(cells) > 1 else ''

                            # Only include tech watchlist stocks
                            if ticker not in TECH_WATCHLIST:
                                continue

                            eps_estimate = cells[2].get_text(strip=True) if len(cells) > 2 else ''

                            events.append({
                                'ticker': ticker,
                                'company': company,
                                'drug_name': '',
                                'indication': f'Earnings Report (EPS Est: {eps_estimate})' if eps_estimate else 'Earnings Report',
                                'catalyst_type': 'Earnings',
                                'catalyst_date': date_str,
                                'phase': '',
                                'status': 'Upcoming',
                                'source': 'yahoo_calendar',
                                'source_url': url,
                            })

            except Exception:
                continue

            # Small delay between date pages
            await asyncio.sleep(0.2)

        return events
