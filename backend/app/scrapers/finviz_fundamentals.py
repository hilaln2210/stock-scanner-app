"""
Finviz Fundamentals Scraper — Detailed quote page data for individual tickers.

Fetches from finviz.com/quote.ashx?t={ticker} and parses the snapshot table.
Returns: institutional ownership, insider activity, margins, analyst consensus,
moving averages, volume data, gap %, target price, short data.

Rate-limited: max 3 concurrent, 0.3s delay between requests.
Per-ticker cache: 300s TTL.
"""

import aiohttp
from bs4 import BeautifulSoup
from typing import Dict, List, Optional
import re
import asyncio
import time


class FinvizFundamentals:
    QUOTE_URL = "https://finviz.com/quote.ashx"
    ELITE_QUOTE_URL = "https://elite.finviz.com/quote.ashx"
    TICKER_CACHE_TTL = 300  # 5 minutes
    MAX_CONCURRENT = 3

    # Maps Finviz label text to our key names
    LABEL_MAP = {
        'Market Cap': 'market_cap',
        'Income': 'income',
        'Sales': 'sales',
        'Book/sh': 'book_per_share',
        'Cash/sh': 'cash_per_share',
        'Dividend': 'dividend',
        'Dividend %': 'dividend_pct',
        'Employees': 'employees',
        'Optionable': 'optionable',
        'Shortable': 'shortable',
        'Recom': 'analyst_recom_raw',
        'P/E': 'pe_ratio',
        'Forward P/E': 'forward_pe',
        'PEG': 'peg',
        'P/S': 'ps_ratio',
        'P/B': 'pb_ratio',
        'P/C': 'pc_ratio',
        'P/FCF': 'pfcf_ratio',
        'Enterprise Value': 'enterprise_value',
        'EV/EBITDA': 'ev_ebitda',
        'EV/Sales': 'ev_sales',
        'Quick Ratio': 'quick_ratio',
        'Current Ratio': 'current_ratio',
        'Debt/Eq': 'debt_equity',
        'LT Debt/Eq': 'lt_debt_equity',
        'EPS (ttm)': 'eps_ttm',
        'EPS next Y': 'eps_next_y',
        'EPS next Q': 'eps_next_q',
        'EPS this Y': 'eps_this_y',
        'EPS next 5Y': 'eps_next_5y',
        'EPS past 5Y': 'eps_past_5y',
        'Sales past 5Y': 'sales_past_5y',
        'Sales Q/Q': 'sales_qq',
        'EPS Q/Q': 'eps_qq',
        'EPS Surprise': 'eps_surpr',
        'EPS/Sales Surpr': 'eps_sales_surpr',
        'Earnings': 'earnings_date',
        'Insider Own': 'insider_own',
        'Insider Trans': 'insider_trans',
        'Inst Own': 'inst_own',
        'Inst Trans': 'inst_trans',
        'ROA': 'roa',
        'ROE': 'roe',
        'ROI': 'roi',
        'Gross Margin': 'gross_margin',
        'Oper. Margin': 'oper_margin',
        'Profit Margin': 'profit_margin',
        'Payout': 'payout',
        'Short Float': 'short_float',
        'Short Float / Ratio': 'short_float',
        'Short Ratio': 'short_ratio',
        'Short Interest': 'short_interest',
        'Target Price': 'target_price',
        'SMA20': 'sma20_dist',
        'SMA50': 'sma50_dist',
        'SMA200': 'sma200_dist',
        '52W High': 'w52_high_dist',
        '52W Low': 'w52_low_dist',
        '52W Range': 'w52_range',
        'RSI (14)': 'rsi',
        'Rel Volume': 'rel_volume',
        'Avg Volume': 'avg_volume',
        'Volume': 'volume',
        'Perf Week': 'perf_week',
        'Perf Month': 'perf_month',
        'Perf Quarter': 'perf_quarter',
        'Perf Half Y': 'perf_half',
        'Perf Year': 'perf_year',
        'Perf YTD': 'perf_ytd',
        'Beta': 'beta',
        'ATR': 'atr',
        'ATR (14)': 'atr',
        'Volatility': 'volatility',
        'Prev Close': 'prev_close',
        'Price': 'price',
        'Change': 'change_pct',
        'Gap': 'gap_pct',
        'Sector': 'sector',
        'Industry': 'industry',
        'Country': 'country',
        'Index': 'index',
    }

    def __init__(self, email: str = '', password: str = '', cookie: str = ''):
        self.email = email
        self.password = password
        self.cookie = cookie
        self._ticker_cache: Dict[str, Dict] = {}
        self._ticker_cache_time: Dict[str, float] = {}

    async def get_fundamentals_batch(self, tickers: List[str]) -> Dict[str, Dict]:
        """Fetch fundamentals for a batch of tickers with bounded concurrency."""
        sem = asyncio.Semaphore(self.MAX_CONCURRENT)
        now = time.time()
        results = {}

        async def fetch_one(ticker: str, idx: int):
            async with sem:
                ticker = ticker.upper()
                # Check cache
                cached_time = self._ticker_cache_time.get(ticker, 0)
                if (now - cached_time) < self.TICKER_CACHE_TTL and ticker in self._ticker_cache:
                    return ticker, self._ticker_cache[ticker]

                # Stagger within each batch of MAX_CONCURRENT
                await asyncio.sleep((idx % self.MAX_CONCURRENT) * 0.2)

                try:
                    data = await self._fetch_fundamentals(ticker)
                    if data:
                        self._ticker_cache[ticker] = data
                        self._ticker_cache_time[ticker] = time.time()
                    return ticker, data
                except Exception as e:
                    print(f"Finviz fundamentals error {ticker}: {e}")
                    return ticker, None

        try:
            tasks = [fetch_one(t, i) for i, t in enumerate(tickers)]
            completed = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=50  # Overall timeout
            )

            for item in completed:
                if isinstance(item, tuple) and len(item) == 2:
                    ticker, data = item
                    if data:
                        results[ticker] = data
        except asyncio.TimeoutError:
            print("Finviz fundamentals OVERALL TIMEOUT (>30s)")

        return results

    async def _fetch_fundamentals(self, ticker: str) -> Optional[Dict]:
        """Fetch and parse fundamentals for a single ticker."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        if self.cookie:
            headers['Cookie'] = self.cookie

        use_elite = bool(self.cookie)
        base_url = self.ELITE_QUOTE_URL if use_elite else self.QUOTE_URL
        url = f"{base_url}?t={ticker}&ty=c&p=d&b=1"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status != 200:
                        return None

                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')

                    # Parse the snapshot table
                    data = self._parse_snapshot_table(soup)
                    if not data:
                        return None

                    # Extract company name from title
                    title_elem = soup.find('title')
                    if title_elem:
                        title_text = title_elem.get_text()
                        # Format: "MRNA Stock Price | Moderna Inc. Stock Quote (U.S.: Nasdaq) | FinViz"
                        parts = title_text.split('|')
                        if len(parts) >= 2:
                            company_part = parts[1].strip()
                            data['company_name'] = company_part.replace('Stock Quote', '').strip().rstrip('.')
                            data['company_name'] = re.sub(r'\s*\(.*?\)\s*$', '', data['company_name']).strip()

                    # Post-process values
                    data['ticker'] = ticker
                    data['analyst_recom'] = self._convert_recom_to_text(data.get('analyst_recom_raw', ''))

                    return data

        except Exception as e:
            print(f"Finviz fetch error {ticker}: {e}")
            return None

    def _parse_snapshot_table(self, soup: BeautifulSoup) -> Dict:
        """Parse the Finviz snapshot-table2 fundamental data table."""
        data = {}

        # Find the snapshot table (class="snapshot-table2")
        table = soup.find('table', class_='snapshot-table2')
        if not table:
            # Try alternative selector
            tables = soup.find_all('table', class_=lambda x: x and 'snapshot' in str(x).lower())
            if tables:
                table = tables[0]

        if not table:
            return data

        rows = table.find_all('tr')
        for row in rows:
            cells = row.find_all('td')
            # Cells alternate: label, value, label, value, ...
            for i in range(0, len(cells) - 1, 2):
                label = cells[i].get_text(strip=True)
                value = cells[i + 1].get_text(strip=True)

                key = self.LABEL_MAP.get(label)
                if key:
                    data[key] = value

        return data

    def _convert_recom_to_text(self, recom_str: str) -> str:
        """Convert Finviz recommendation number to text."""
        try:
            val = float(recom_str)
            if val <= 1.5:
                return 'Strong Buy'
            elif val <= 2.5:
                return 'Buy'
            elif val <= 3.5:
                return 'Hold'
            elif val <= 4.5:
                return 'Sell'
            else:
                return 'Strong Sell'
        except (ValueError, TypeError):
            return recom_str or ''
