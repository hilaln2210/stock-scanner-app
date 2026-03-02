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

    ELITE_SCREENER_URL = "https://elite.finviz.com/screener.ashx"
    PRICE_CACHE_TTL = 60  # 1 minute for live prices

    def __init__(self, email: str = '', password: str = '', cookie: str = ''):
        self.email = email
        self.password = password
        self.cookie = cookie
        self._ticker_cache: Dict[str, Dict] = {}
        self._ticker_cache_time: Dict[str, float] = {}
        self._price_cache: Dict[str, Dict] = {}
        self._price_cache_time: float = 0

    async def get_prices_batch(self, tickers: List[str]) -> Dict[str, Dict]:
        """
        Fetch real-time prices for multiple tickers in a single Finviz screener request.
        Uses Elite (Pro) session for pre/post-market real-time data.
        Returns: {ticker: {"price": float, "change_pct": str, "prev_close": float}}
        """
        if not tickers:
            return {}

        now = time.time()
        # Return cached if fresh (1 minute)
        if (now - self._price_cache_time) < self.PRICE_CACHE_TTL and self._price_cache:
            # Check all tickers are in cache
            if all(t.upper() in self._price_cache for t in tickers):
                return {t.upper(): self._price_cache[t.upper()] for t in tickers}

        ticker_str = ",".join(t.upper() for t in tickers)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml',
        }
        if self.cookie:
            headers['Cookie'] = self.cookie

        # Screener with ticker filter + overview columns (price + change)
        url = f"{self.ELITE_SCREENER_URL}?v=111&t={ticker_str}&o=-change"
        results = {}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
                    if resp.status != 200:
                        return {}
                    html = await resp.text()

            soup = BeautifulSoup(html, 'html.parser')

            # Find screener table — try multiple selectors
            table = (soup.find('table', {'id': 'screener-views-table'}) or
                     soup.find('table', attrs={'cellpadding': '3', 'width': '100%'}))
            if not table:
                all_tables = soup.find_all('table')
                for t in all_tables:
                    rows = t.find_all('tr')
                    if len(rows) > 2 and len(rows[1].find_all('td')) >= 8:
                        table = t
                        break

            if not table:
                return {}

            rows = table.find_all('tr')

            # Parse header to find column indices
            header = []
            data_rows = []
            for row in rows:
                ths = row.find_all('th')
                if ths:
                    header = [th.get_text(strip=True).lower() for th in ths]
                else:
                    tds = row.find_all('td')
                    if len(tds) >= 5:
                        data_rows.append(tds)

            if not header:
                header = ['no', 'ticker', 'company', 'sector', 'industry',
                          'country', 'market cap', 'p/e', 'price', 'change', 'volume']

            col = {h: i for i, h in enumerate(header)}
            ticker_col  = col.get('ticker', 1)
            price_col   = col.get('price', 8)
            change_col  = col.get('change', 9)

            for cells in data_rows:
                texts = [td.get_text(strip=True) for td in cells]
                if len(texts) <= max(ticker_col, price_col):
                    continue
                ticker = texts[ticker_col].upper()
                if not re.match(r'^[A-Z]{1,5}$', ticker):
                    continue
                try:
                    price_str = texts[price_col].replace(',', '').replace('$', '')
                    price = float(price_str) if price_str else None
                except (ValueError, IndexError):
                    price = None
                change_str = texts[change_col] if change_col < len(texts) else ''
                if price:
                    results[ticker] = {
                        "price": price,
                        "change_pct": change_str,
                        "source": "finviz_elite",
                    }

            if results:
                self._price_cache.update(results)
                self._price_cache_time = now

        except Exception as e:
            print(f"Finviz get_prices_batch error: {e}")

        return results

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
