"""
Finviz Screener — Professional Momentum Stock Scanner

Filters designed to find stocks like MSTR with unusual activity:
1. Average Volume > 500K (liquidity)
2. Relative Volume > 1.5 (institutional interest)
3. Price > $10 (no penny stocks)
4. Change > 5% (already moving)
5. Price above SMA20 (short-term uptrend)
6. Unusual Volume signal detection

Enriched with yfinance data:
- VWAP calculation from intraday data
- ATR (Average True Range) for movement potential
- Support/Resistance levels
- Intraday price structure
"""

import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Optional
import re
import asyncio
import yfinance as yf
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
import time
import threading


class FinvizScreener:
    """
    Professional Finviz Screener with momentum filters.
    Combines Finviz screening with yfinance VWAP/ATR enrichment.
    """

    # Finviz screener URL with filters baked in
    # v=111 = overview view, f_* = filters
    SCREENER_FILTERS = {
        'v': '111',              # Overview
        'f': ','.join([
            'sh_avgvol_o500',    # Avg Volume > 500K
            'sh_relvol_o1.5',    # Relative Volume > 1.5
            'sh_price_o10',      # Price > $10
            'ta_change_u5',      # Change > 5% up
            'ta_sma20_pa',       # Price above SMA20
        ]),
        'o': '-change',          # Sort by change descending
    }

    # Alternative: also scan for unusual volume signal
    UNUSUAL_VOL_FILTERS = {
        'v': '111',
        's': 'ta_unusualvolume',  # Unusual Volume signal
        'f': ','.join([
            'sh_avgvol_o500',
            'sh_price_o10',
        ]),
        'o': '-change',
    }

    # For strong drops too (both directions = momentum)
    DROP_FILTERS = {
        'v': '111',
        'f': ','.join([
            'sh_avgvol_o500',
            'sh_relvol_o1.5',
            'sh_price_o10',
            'ta_change_d5',      # Change > 5% DOWN
        ]),
        'o': 'change',           # Sort by biggest drop
    }

    BASE_URL = "https://elite.finviz.com/screener.ashx"
    PUBLIC_URL = "https://finviz.com/screener.ashx"

    # Timeout for each yfinance call (seconds)
    YFINANCE_CALL_TIMEOUT = 8
    # Cache enriched data per ticker for this many seconds
    TICKER_CACHE_TTL = 120
    # Cache the full scan result for this many seconds
    SCAN_CACHE_TTL = 90

    def __init__(self, email: str = '', password: str = '', cookie: str = ''):
        self.email = email
        self.password = password
        self.cookie = cookie
        # Per-ticker enrichment cache
        self._ticker_cache: Dict[str, Dict] = {}
        self._ticker_cache_time: Dict[str, float] = {}
        # Full scan result cache
        self._scan_cache: Optional[List[Dict]] = None
        self._scan_cache_time: float = 0
        # Dedicated thread pool for yfinance (bounded)
        self._yf_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix='yfinance')
        self._lock = threading.Lock()

    async def scan_momentum_stocks(self, include_drops: bool = True) -> List[Dict]:
        """
        Run the full momentum screener pipeline with caching.
        Returns cached result if within SCAN_CACHE_TTL seconds.
        """
        # Return cached result if fresh enough
        now = time.time()
        if self._scan_cache and (now - self._scan_cache_time) < self.SCAN_CACHE_TTL:
            return self._scan_cache

        tasks = [
            self._scrape_screener(self.SCREENER_FILTERS, 'momentum_up'),
            self._scrape_screener(self.UNUSUAL_VOL_FILTERS, 'unusual_volume'),
        ]
        if include_drops:
            tasks.append(self._scrape_screener(self.DROP_FILTERS, 'momentum_down'))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Merge and deduplicate
        all_stocks = {}
        for result in results:
            if isinstance(result, list):
                for stock in result:
                    ticker = stock.get('ticker', '')
                    if ticker:
                        if ticker in all_stocks:
                            existing = all_stocks[ticker]
                            existing['scan_sources'] = list(set(
                                existing.get('scan_sources', []) + stock.get('scan_sources', [])
                            ))
                        else:
                            all_stocks[ticker] = stock

        stocks_list = list(all_stocks.values())

        # Enrich with VWAP/ATR data (with per-ticker caching + timeouts)
        if stocks_list:
            stocks_list = await self._enrich_with_vwap_atr(stocks_list)

        # Calculate composite score
        for stock in stocks_list:
            stock['screener_score'] = self._calculate_screener_score(stock)

        # Sort by score
        stocks_list.sort(key=lambda x: x.get('screener_score', 0), reverse=True)

        # Cache the result
        self._scan_cache = stocks_list
        self._scan_cache_time = time.time()

        return stocks_list

    async def _scrape_screener(self, filters: Dict, source_label: str) -> List[Dict]:
        """Scrape a single Finviz screener page with given filters."""
        results = []

        try:
            async with aiohttp.ClientSession() as session:
                headers = {
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }

                # Login if needed
                if self.email and self.password and not self.cookie:
                    self.cookie = await self._login(session)

                if self.cookie:
                    headers["Cookie"] = self.cookie

                # Build URL
                use_elite = bool(self.cookie)
                base = self.BASE_URL if use_elite else self.PUBLIC_URL
                params = '&'.join(f'{k}={v}' for k, v in filters.items())
                url = f"{base}?{params}"

                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        print(f"Finviz Screener [{source_label}] returned {response.status}")
                        return results

                    html = await response.text()
                    soup = BeautifulSoup(html, "html.parser")

                    # Parse screener table
                    results = self._parse_screener_table(soup, source_label)

        except Exception as e:
            print(f"Finviz Screener [{source_label}] error: {e}")

        return results

    def _parse_screener_table(self, soup: BeautifulSoup, source_label: str) -> List[Dict]:
        """Parse the Finviz screener results table."""
        stocks = []

        # Finviz screener table has class 'screener_table' or id 'screener-views-table'
        table = soup.find('table', {'id': 'screener-views-table'})
        if not table:
            # Try alternative table structure
            tables = soup.find_all('table', class_='table-light')
            if tables:
                table = tables[-1]  # Usually the last one is the data table

        if not table:
            # Try the newer Finviz table structure
            table = soup.find('table', attrs={'width': '100%', 'cellpadding': '3'})

        if not table:
            print(f"Screener [{source_label}]: Could not find results table")
            # Try to extract from any table with ticker-like data
            all_tables = soup.find_all('table')
            for t in all_tables:
                rows = t.find_all('tr')
                if len(rows) > 2:
                    # Check if it looks like a stock table
                    first_data = rows[1] if len(rows) > 1 else None
                    if first_data:
                        cells = first_data.find_all('td')
                        if len(cells) >= 8:
                            table = t
                            break

        if not table:
            return stocks

        rows = table.find_all('tr')

        # Find header row to map columns
        header_row = None
        data_rows = []
        for row in rows:
            ths = row.find_all('th')
            if ths:
                header_row = [th.get_text(strip=True).lower() for th in ths]
            else:
                tds = row.find_all('td')
                if len(tds) >= 5:
                    data_rows.append(tds)

        if not header_row:
            # Default Finviz screener overview columns (v=111)
            header_row = ['no', 'ticker', 'company', 'sector', 'industry',
                         'country', 'market cap', 'p/e', 'price', 'change', 'volume']

        # Map column indices
        col_map = {}
        for i, h in enumerate(header_row):
            col_map[h] = i

        for row_cells in data_rows[:50]:  # Limit to 50 results
            try:
                cells_text = [td.get_text(strip=True) for td in row_cells]

                ticker_idx = col_map.get('ticker', 1)
                ticker = cells_text[ticker_idx] if ticker_idx < len(cells_text) else ''

                if not ticker or not re.match(r'^[A-Z]{1,5}$', ticker):
                    # Try to find ticker from links
                    for td in row_cells:
                        link = td.find('a', href=re.compile(r'quote\.ashx\?t='))
                        if link:
                            ticker = link.get_text(strip=True)
                            break

                if not ticker:
                    continue

                company = cells_text[col_map.get('company', 2)] if col_map.get('company', 2) < len(cells_text) else ''
                sector = cells_text[col_map.get('sector', 3)] if col_map.get('sector', 3) < len(cells_text) else ''
                industry = cells_text[col_map.get('industry', 4)] if col_map.get('industry', 4) < len(cells_text) else ''

                # Parse price
                price_idx = col_map.get('price', 8)
                price_str = cells_text[price_idx] if price_idx < len(cells_text) else '0'
                price = float(re.sub(r'[^\d.]', '', price_str)) if price_str else 0

                # Parse change %
                change_idx = col_map.get('change', 9)
                change_str = cells_text[change_idx] if change_idx < len(cells_text) else '0'
                change_pct = float(re.sub(r'[^\d.\-]', '', change_str)) if change_str else 0

                # Parse volume
                vol_idx = col_map.get('volume', 10)
                vol_str = cells_text[vol_idx] if vol_idx < len(cells_text) else '0'
                volume = self._parse_volume(vol_str)

                # Parse market cap
                mcap_idx = col_map.get('market cap', 6)
                mcap_str = cells_text[mcap_idx] if mcap_idx < len(cells_text) else ''

                stocks.append({
                    'ticker': ticker,
                    'company': company,
                    'sector': sector,
                    'industry': industry,
                    'price': price,
                    'change_pct': change_pct,
                    'volume': volume,
                    'market_cap_str': mcap_str,
                    'scan_sources': [source_label],
                    'scanned_at': datetime.now().isoformat(),
                })

            except Exception as e:
                continue

        return stocks

    def _parse_volume(self, vol_str: str) -> int:
        """Parse volume string like '1.2M' or '500K' or '1,234,567'."""
        vol_str = vol_str.strip().upper().replace(',', '')
        try:
            if 'B' in vol_str:
                return int(float(vol_str.replace('B', '')) * 1_000_000_000)
            elif 'M' in vol_str:
                return int(float(vol_str.replace('M', '')) * 1_000_000)
            elif 'K' in vol_str:
                return int(float(vol_str.replace('K', '')) * 1_000)
            else:
                return int(float(vol_str)) if vol_str else 0
        except (ValueError, TypeError):
            return 0

    async def _login(self, session: aiohttp.ClientSession) -> Optional[str]:
        """Login to Finviz Elite."""
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
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
                "Content-Type": "application/x-www-form-urlencoded",
                "Referer": "https://elite.finviz.com/login.ashx"
            }

            async with session.post(login_url, data=login_data, headers=headers, allow_redirects=True) as response:
                if response.status == 200:
                    cookies = session.cookie_jar.filter_cookies("https://elite.finviz.com")
                    cookie_str = "; ".join([f"{c.key}={c.value}" for c in cookies.values()])
                    if cookie_str:
                        print("Finviz Screener: Login successful!")
                        return cookie_str
        except Exception as e:
            print(f"Finviz Screener login error: {e}")

        return None

    async def _enrich_with_vwap_atr(self, stocks: List[Dict], max_concurrent: int = 3) -> List[Dict]:
        """
        Enrich stocks with VWAP/ATR from yfinance.
        - Per-ticker cache (TICKER_CACHE_TTL seconds)
        - Bounded thread pool with YFINANCE_CALL_TIMEOUT per ticker
        - Overall enrichment timeout of 25 seconds
        """
        sem = asyncio.Semaphore(max_concurrent)
        now = time.time()

        async def enrich_one(stock, idx):
            async with sem:
                ticker = stock.get('ticker', '')
                # Check per-ticker cache
                cached_time = self._ticker_cache_time.get(ticker, 0)
                if (now - cached_time) < self.TICKER_CACHE_TTL and ticker in self._ticker_cache:
                    stock.update(self._ticker_cache[ticker])
                    return stock

                # Small staggered delay
                await asyncio.sleep(idx * 0.2)
                try:
                    loop = asyncio.get_event_loop()
                    vwap_data = await asyncio.wait_for(
                        loop.run_in_executor(
                            self._yf_executor, self._fetch_vwap_atr_sync, ticker
                        ),
                        timeout=self.YFINANCE_CALL_TIMEOUT
                    )
                    if vwap_data:
                        stock.update(vwap_data)
                        # Cache the result
                        self._ticker_cache[ticker] = vwap_data
                        self._ticker_cache_time[ticker] = time.time()
                except asyncio.TimeoutError:
                    print(f"VWAP enrichment TIMEOUT {ticker} (>{self.YFINANCE_CALL_TIMEOUT}s)")
                except Exception as e:
                    print(f"VWAP enrichment error {ticker}: {e}")
                return stock

        # Limit to top 15 stocks
        stocks_to_enrich = stocks[:15]
        try:
            enriched = await asyncio.wait_for(
                asyncio.gather(*[enrich_one(s, i) for i, s in enumerate(stocks_to_enrich)], return_exceptions=True),
                timeout=25  # Overall timeout for all enrichments
            )
        except asyncio.TimeoutError:
            print("VWAP enrichment OVERALL TIMEOUT (>25s) — returning partial results")
            enriched = stocks_to_enrich

        remaining = stocks[15:]
        result = [s for s in enriched if isinstance(s, dict)]
        result.extend(remaining)
        return result

    def _fetch_vwap_atr_sync(self, ticker: str) -> Optional[Dict]:
        """Synchronous yfinance fetch for VWAP and ATR data.
        Each sub-call is individually protected with a timeout."""
        try:
            stock = yf.Ticker(ticker)

            # --- Intraday data for VWAP ---
            hist_intraday = None
            try:
                hist_intraday = stock.history(period='1d', interval='5m', timeout=5)
            except Exception:
                pass
            vwap = 0
            vwap_position = 'unknown'
            current_price = 0

            if hist_intraday is not None and not hist_intraday.empty:
                # Calculate VWAP: cumulative(typical_price * volume) / cumulative(volume)
                tp = (hist_intraday['High'] + hist_intraday['Low'] + hist_intraday['Close']) / 3
                cumulative_tp_vol = (tp * hist_intraday['Volume']).cumsum()
                cumulative_vol = hist_intraday['Volume'].cumsum()

                # Avoid division by zero
                mask = cumulative_vol > 0
                vwap_series = cumulative_tp_vol[mask] / cumulative_vol[mask]

                if not vwap_series.empty:
                    vwap = float(vwap_series.iloc[-1])
                    current_price = float(hist_intraday['Close'].iloc[-1])

                    # Position relative to VWAP
                    if current_price > vwap * 1.005:
                        vwap_position = 'above'
                    elif current_price < vwap * 0.995:
                        vwap_position = 'below'
                    else:
                        vwap_position = 'at_vwap'

            # --- Daily data for ATR and SMA ---
            hist_daily = None
            try:
                hist_daily = stock.history(period='1mo', interval='1d', timeout=5)
            except Exception:
                pass
            atr = 0
            atr_pct = 0
            sma20 = 0
            above_sma20 = False
            day_high = 0
            day_low = 0
            day_open = 0
            prev_close = 0
            resistance = 0
            support = 0

            if hist_daily is not None and not hist_daily.empty and len(hist_daily) >= 2:
                # True Range calculation
                highs = hist_daily['High']
                lows = hist_daily['Low']
                closes = hist_daily['Close']

                tr1 = highs - lows
                tr2 = abs(highs - closes.shift(1))
                tr3 = abs(lows - closes.shift(1))

                true_range = tr1.copy()
                for i in range(len(true_range)):
                    true_range.iloc[i] = max(
                        tr1.iloc[i],
                        tr2.iloc[i] if not tr2.isna().iloc[i] else 0,
                        tr3.iloc[i] if not tr3.isna().iloc[i] else 0
                    )

                # ATR-14
                atr = float(true_range.rolling(14).mean().iloc[-1]) if len(true_range) >= 14 else float(true_range.mean())
                atr_pct = round((atr / current_price * 100), 2) if current_price > 0 else 0

                # SMA20
                if len(closes) >= 20:
                    sma20 = float(closes.rolling(20).mean().iloc[-1])
                    above_sma20 = current_price > sma20

                # Today's OHLC
                day_high = float(highs.iloc[-1])
                day_low = float(lows.iloc[-1])
                day_open = float(hist_daily['Open'].iloc[-1])
                prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else 0

                # Simple resistance/support from recent highs/lows
                recent = hist_daily.tail(5)
                resistance = float(recent['High'].max())
                support = float(recent['Low'].min())

            # Company info - handle case where info might have None values
            # stock.info can hang indefinitely — skip if it takes too long
            info = {}
            try:
                from concurrent.futures import ThreadPoolExecutor as _TP, TimeoutError as _TE
                with _TP(max_workers=1) as _ex:
                    future = _ex.submit(lambda: stock.info or {})
                    info = future.result(timeout=4)
            except Exception:
                pass

            avg_volume = int(info.get('averageVolume') or 0)
            current_volume = int(info.get('volume') or 0)
            rel_volume = round(current_volume / avg_volume, 2) if avg_volume > 0 else 0

            # Business summary (company description)
            business_summary = str(info.get('longBusinessSummary') or '')
            if len(business_summary) > 300:
                business_summary = business_summary[:297] + '...'

            # Recent news — stock.news can also hang
            news_items = []
            try:
                from concurrent.futures import ThreadPoolExecutor as _TP2
                with _TP2(max_workers=1) as _ex2:
                    future2 = _ex2.submit(lambda: stock.news or [])
                    raw_news = future2.result(timeout=3)
                for item in raw_news[:5]:
                    content = item.get('content', {}) or {}
                    title = str(content.get('title') or '')
                    if not title:
                        continue
                    provider = content.get('provider', {})
                    publisher = str(provider.get('displayName', '')) if isinstance(provider, dict) else str(provider or '')
                    canonical = content.get('canonicalUrl', {})
                    link = str(canonical.get('url', '')) if isinstance(canonical, dict) else str(canonical or '')
                    if not link:
                        click = content.get('clickThroughUrl', {})
                        link = str(click.get('url', '')) if isinstance(click, dict) else str(click or '')
                    pub_date = str(content.get('pubDate') or '')
                    news_items.append({
                        'title': title,
                        'publisher': publisher,
                        'link': link,
                        'pub_date': pub_date,
                    })
            except Exception:
                pass

            return {
                # VWAP
                'vwap': round(vwap, 2),
                'vwap_position': vwap_position,
                'vwap_distance_pct': round(((current_price - vwap) / vwap * 100), 2) if vwap > 0 else 0,
                'current_price': round(current_price, 2),

                # ATR
                'atr': round(atr, 2),
                'atr_pct': atr_pct,

                # SMA
                'sma20': round(sma20, 2),
                'above_sma20': above_sma20,

                # Day structure
                'day_open': round(day_open, 2),
                'day_high': round(day_high, 2),
                'day_low': round(day_low, 2),
                'prev_close': round(prev_close, 2),

                # Levels
                'resistance': round(resistance, 2),
                'support': round(support, 2),

                # Volume
                'avg_volume': avg_volume,
                'current_volume': current_volume,
                'rel_volume': rel_volume,

                # Company
                'company_name': str(info.get('longName') or info.get('shortName') or ticker),
                'full_sector': str(info.get('sector') or ''),
                'full_industry': str(info.get('industry') or ''),
                'market_cap': int(info.get('marketCap') or 0),

                # Earnings beat (quarterly growth from yfinance)
                'earnings_growth_pct': round((info.get('earningsQuarterlyGrowth') or 0) * 100, 1),

                # Description & News
                'business_summary': business_summary,
                'news': news_items,
            }

        except Exception as e:
            print(f"VWAP/ATR fetch error {ticker}: {e}")
            return None

    def _calculate_screener_score(self, stock: Dict) -> int:
        """
        Calculate composite momentum score for screened stocks.

        Scoring (0-100):
        - Price change magnitude: 0-25
        - VWAP position: 0-20
        - Relative volume: 0-20
        - ATR utilization: 0-15
        - Multiple scan hits: 0-10
        - Above SMA20: 0-10
        """
        score = 0

        # 1. Price change (0-25)
        change = abs(stock.get('change_pct', 0))
        if change >= 20:
            score += 25
        elif change >= 15:
            score += 22
        elif change >= 10:
            score += 18
        elif change >= 7:
            score += 14
        elif change >= 5:
            score += 10

        # 2. VWAP position (0-20)
        vwap_pos = stock.get('vwap_position', 'unknown')
        change_pct = stock.get('change_pct', 0)
        if change_pct > 0 and vwap_pos == 'above':
            score += 20  # Bullish + above VWAP = strong
        elif change_pct < 0 and vwap_pos == 'below':
            score += 20  # Bearish + below VWAP = strong
        elif vwap_pos == 'at_vwap':
            score += 10  # At VWAP = potential decision point
        else:
            score += 5

        # 3. Relative volume (0-20)
        rel_vol = stock.get('rel_volume', 0)
        if rel_vol >= 5:
            score += 20
        elif rel_vol >= 3:
            score += 16
        elif rel_vol >= 2:
            score += 12
        elif rel_vol >= 1.5:
            score += 8

        # 4. ATR utilization (0-15) — how much of ATR has been used today
        atr = stock.get('atr', 0)
        day_range = stock.get('day_high', 0) - stock.get('day_low', 0)
        if atr > 0:
            atr_used = day_range / atr
            if atr_used >= 1.5:
                score += 15  # Extended beyond normal ATR
            elif atr_used >= 1.0:
                score += 12
            elif atr_used >= 0.7:
                score += 8
            elif atr_used >= 0.5:
                score += 5

        # 5. Multiple scan hits (0-10)
        sources = stock.get('scan_sources', [])
        if len(sources) >= 3:
            score += 10
        elif len(sources) >= 2:
            score += 7
        else:
            score += 3

        # 6. Above SMA20 (0-10)
        if stock.get('above_sma20', False):
            score += 10

        return min(100, score)


# Singleton factory
def create_finviz_screener(email: str = '', password: str = '', cookie: str = '') -> FinvizScreener:
    return FinvizScreener(email=email, password=password, cookie=cookie)
