"""
Sector Morning Briefing Service.

Each call returns:
1. Sector ETF leaderboard — all 11 sectors ranked by % change today
2. Top movers in the leading sector (Finviz screener with sector filter)
3. Insider trades — Form 4 purchases ≥ $100K in last 2 days (openinsider.com)

5 separate caches with different TTLs for real-time accuracy:
  - ETF prices:     30s  (real-time sector ranking)
  - Drivers:       120s  (top holding % changes)
  - Sector stocks: 180s  (Finviz rate limit friendly)
  - Insider trades: 900s (slow-changing data)
  - News headlines: 300s (sector ETF + holding news via yfinance)
"""

import asyncio
import time as _time
from concurrent.futures import TimeoutError as FuturesTimeout
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
import yfinance as yf
from bs4 import BeautifulSoup


# ── Sector ETF definitions ──────────────────────────────────────────────────────

SECTOR_ETFS: Dict[str, dict] = {
    'XLK':  {'name': 'Technology',             'icon': '💻', 'finviz': 'sec_technology'},
    'XLF':  {'name': 'Financial Services',     'icon': '🏦', 'finviz': 'sec_financial'},
    'XLV':  {'name': 'Healthcare',             'icon': '💊', 'finviz': 'sec_healthcare'},
    'XLE':  {'name': 'Energy',                 'icon': '⚡', 'finviz': 'sec_energy'},
    'XLI':  {'name': 'Industrials',            'icon': '🏭', 'finviz': 'sec_industrials'},
    'XLY':  {'name': 'Consumer Cyclical',      'icon': '🛍️', 'finviz': 'sec_consumercyclical'},
    'XLP':  {'name': 'Consumer Defensive',     'icon': '🛒', 'finviz': 'sec_consumerdefensive'},
    'XLC':  {'name': 'Communication Svcs',     'icon': '📡', 'finviz': 'sec_communicationservices'},
    'XLB':  {'name': 'Basic Materials',        'icon': '⛏️', 'finviz': 'sec_basicmaterials'},
    'XLRE': {'name': 'Real Estate',            'icon': '🏘️', 'finviz': 'sec_realestate'},
    'XLU':  {'name': 'Utilities',              'icon': '💡', 'finviz': 'sec_utilities'},
}

# Top 3 holdings per ETF — used to explain why the sector is moving
ETF_TOP_HOLDINGS: Dict[str, List[str]] = {
    'XLK':  ['AAPL', 'MSFT', 'NVDA'],
    'XLF':  ['BRK-B', 'JPM', 'V'],
    'XLV':  ['UNH', 'JNJ', 'LLY'],
    'XLE':  ['XOM', 'CVX', 'EOG'],
    'XLI':  ['GE', 'RTX', 'CAT'],
    'XLY':  ['AMZN', 'TSLA', 'HD'],
    'XLP':  ['PG', 'COST', 'KO'],
    'XLC':  ['META', 'GOOGL', 'NFLX'],
    'XLB':  ['LIN', 'APD', 'ECL'],
    'XLRE': ['AMT', 'PLD', 'CCI'],
    'XLU':  ['NEE', 'DUK', 'SO'],
}

_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

# ── Separate caches with different TTLs ──────────────────────────────────────────

_etf_cache: Optional[List[dict]] = None
_etf_cache_at: float = 0.0
_ETF_CACHE_TTL = 30  # 30 seconds — real-time sector ranking

_drivers_cache: Dict[str, float] = {}
_drivers_cache_at: float = 0.0
_DRIVERS_CACHE_TTL = 120  # 2 minutes

_stocks_cache: Optional[List[dict]] = None
_stocks_cache_at: float = 0.0
_stocks_sector: str = ''  # which sector the cached stocks are for
_STOCKS_CACHE_TTL = 180  # 3 minutes (Finviz rate limit)

_insider_cache: Optional[List[dict]] = None
_insider_cache_at: float = 0.0
_INSIDER_CACHE_TTL = 900  # 15 minutes

_news_cache: Dict[str, List[dict]] = {}  # {etf: [{title, source, ticker}]}
_news_cache_at: float = 0.0
_NEWS_CACHE_TTL = 300  # 5 minutes


# ── 1a. Sector ETF Performance (ETFs only) ───────────────────────────────────────

def _fetch_etf_only() -> List[dict]:
    """
    Fetch today's % change for only the 11 sector ETFs (fast, ~2-3 seconds).
    Returns sectors list sorted by change_pct desc. No drivers yet.
    """
    etf_tickers = list(SECTOR_ETFS.keys())
    results = []
    try:
        data = yf.download(
            etf_tickers,
            period='2d',
            interval='1d',
            progress=False,
            timeout=10,
            auto_adjust=True,
        )
        close = data.get('Close', data) if hasattr(data, 'get') else data

        for etf, meta in SECTOR_ETFS.items():
            try:
                prices = close[etf].dropna()
                if len(prices) >= 2:
                    prev = float(prices.iloc[-2])
                    curr = float(prices.iloc[-1])
                    chg = (curr - prev) / prev * 100 if prev else 0.0
                elif len(prices) == 1:
                    curr = float(prices.iloc[-1])
                    chg = 0.0
                else:
                    continue

                results.append({
                    'etf':           etf,
                    'name':          meta['name'],
                    'icon':          meta['icon'],
                    'finviz_filter': meta['finviz'],
                    'change_pct':    round(chg, 2),
                    'price':         round(curr, 2),
                })
            except Exception:
                pass

    except Exception as e:
        print(f"[SectorBriefing] ETF-only fetch error: {e}")

    return sorted(results, key=lambda x: x['change_pct'], reverse=True)


# ── 1b. Driver Holdings % Changes ────────────────────────────────────────────────

def _fetch_drivers() -> Dict[str, float]:
    """
    Fetch today's % change for the 33 unique top-holding tickers.
    Returns {ticker: change_pct}.
    """
    holding_tickers = list({t for holdings in ETF_TOP_HOLDINGS.values() for t in holdings})
    result: Dict[str, float] = {}
    try:
        data = yf.download(
            holding_tickers,
            period='2d',
            interval='1d',
            progress=False,
            timeout=15,
            auto_adjust=True,
        )
        close = data.get('Close', data) if hasattr(data, 'get') else data

        for t in holding_tickers:
            try:
                prices = close[t].dropna()
                if len(prices) >= 2:
                    p, c = float(prices.iloc[-2]), float(prices.iloc[-1])
                    result[t] = round((c - p) / p * 100, 2) if p else 0.0
            except Exception:
                pass

    except Exception as e:
        print(f"[SectorBriefing] drivers fetch error: {e}")

    return result


# ── 2. Top Movers in Sector (Finviz) ───────────────────────────────────────────

async def _fetch_sector_stocks(
    session: aiohttp.ClientSession,
    finviz_filter: str,
) -> List[dict]:
    """
    Fetch top movers within a sector from Finviz screener.
    Filters: avg vol > 200K, rel vol > 1.0, change > 2%, sorted by change desc.
    """
    url = (
        'https://finviz.com/screener.ashx?v=111'
        f'&f=sh_avgvol_o200,{finviz_filter}'
        '&o=-change&r=1'  # page 1, sorted by change desc — works in/out of market hours
    )
    try:
        async with session.get(
            url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                print(f"[SectorBriefing] Finviz {finviz_filter} HTTP {resp.status}")
                return []
            html = await resp.text()

        soup = BeautifulSoup(html, 'html.parser')

        # Find by walking up from the first quote link (robust against class changes)
        import re as _re
        table = None
        link = soup.find('a', href=_re.compile(r'quote\.ashx\?t='))
        if link:
            node = link
            for _ in range(12):
                node = node.parent
                if node.name == 'table':
                    table = node
                    break
                if node.name == 'body':
                    break
        if not table:
            # Fallback: any table whose header row contains 'Ticker'
            for t in soup.find_all('table'):
                hdr = t.find('tr')
                if hdr and 'Ticker' in [c.get_text(strip=True) for c in hdr.find_all(['th', 'td'])]:
                    table = t
                    break

        if not table:
            return []

        rows = table.find_all('tr')
        # Build column index from header row (Finviz uses <th>)
        header_cells = rows[0].find_all(['th', 'td'])
        col = {c.get_text(strip=True): i for i, c in enumerate(header_cells)}

        def gcol(row_cells, name, default=''):
            i = col.get(name)
            return row_cells[i].get_text(strip=True) if i is not None and i < len(row_cells) else default

        stocks = []
        for row in rows[1:]:
            cells = row.find_all('td')
            if not cells:
                continue

            ticker = gcol(cells, 'Ticker')
            if not ticker or ticker.isdigit():
                continue

            try:
                chg = float(gcol(cells, 'Change', '0').replace('%', '').replace('+', ''))
                rvol = float(gcol(cells, 'Rel Volume', '0') or '0')
                price_str = gcol(cells, 'Price', '0').replace('$', '').replace(',', '')
                price = float(price_str) if price_str else 0.0
                vol_str = gcol(cells, 'Volume', '0').replace(',', '')
                volume = int(vol_str) if vol_str.isdigit() else 0
            except Exception:
                continue

            stocks.append({
                'ticker':     ticker,
                'company':    gcol(cells, 'Company'),
                'change_pct': chg,
                'rel_volume': rvol,
                'price':      price,
                'volume':     volume,
                'market_cap': gcol(cells, 'Market Cap'),
            })

            if len(stocks) >= 12:
                break

        return stocks

    except Exception as e:
        print(f"[SectorBriefing] Finviz sector stocks error ({finviz_filter}): {e}")
        return []


# ── 3. Insider Trades (Form 4 — openinsider.com) ───────────────────────────────

async def _fetch_insider_trades(session: aiohttp.ClientSession) -> List[dict]:
    """
    Scrape openinsider.com for recent Form 4 cluster buys.
    Filters: purchases only, value ≥ $100K, last 2 days, top 20.
    """
    url = (
        'http://openinsider.com/screener?'
        's=&o=&pl=&ph=&ll=&lh=&fd=2&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&'
        'xp=1&vl=100&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&'
        'nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&'
        'sortcol=0&cnt=50&action=1'
    )
    try:
        async with session.get(
            url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                print(f"[SectorBriefing] openinsider HTTP {resp.status}")
                return []
            html = await resp.text()

        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table', class_='tinytable')
        if not table:
            return []

        rows = table.find_all('tr')
        if len(rows) < 2:
            return []

        # Parse column headers
        header_cells = rows[0].find_all(['th', 'td'])
        headers = [h.get_text(strip=True) for h in header_cells]

        def gcell(row_cells, *names):
            for name in names:
                try:
                    i = headers.index(name)
                    if i < len(row_cells):
                        return row_cells[i].get_text(strip=True)
                except ValueError:
                    pass
            return ''

        trades = []
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) < 5:
                continue

            # Extract ticker via link href pattern /quote/TICKER
            ticker = ''
            for c in cells:
                a = c.find('a', href=True)
                if a and '/quote/' in a['href']:
                    ticker = a.get_text(strip=True).upper()
                    break
            if not ticker:
                ticker = gcell(cells, 'Ticker', 'Sym').upper()
            if not ticker:
                continue

            trade_type = gcell(cells, 'Trade Type', 'Type', 'X')
            # Keep only purchases (P - Purchase)
            if trade_type and 'P' not in trade_type:
                continue

            insider  = gcell(cells, 'Insider Name', 'Insider')
            title    = gcell(cells, 'Title')
            value    = gcell(cells, 'Value', 'Val')
            qty      = gcell(cells, 'Qty', '#Shares', 'Shares')
            price    = gcell(cells, 'Price')
            date     = gcell(cells, 'Filing Date', 'Date', 'Filed')
            company  = gcell(cells, 'Company', 'Issuer')

            trades.append({
                'ticker':  ticker,
                'company': company,
                'insider': insider,
                'title':   title,
                'value':   value,
                'qty':     qty,
                'price':   price,
                'date':    date,
            })

            if len(trades) >= 20:
                break

        return trades

    except Exception as e:
        print(f"[SectorBriefing] insider trades fetch error: {e}")
        return []


# ── 4. Insider ticker % change (yfinance batch) ────────────────────────────────

def _fetch_insider_changes(tickers: List[str]) -> Dict[str, float]:
    """Batch-fetch today's % change for a list of tickers. Returns {ticker: chg}."""
    if not tickers:
        return {}
    unique = list(dict.fromkeys(tickers))[:30]  # cap at 30 to avoid rate-limit
    result: Dict[str, float] = {}
    try:
        data = yf.download(
            unique,
            period='2d',
            interval='1d',
            progress=False,
            timeout=12,
            auto_adjust=True,
        )
        close = data.get('Close', data) if hasattr(data, 'get') else data
        for t in unique:
            try:
                prices = close[t].dropna() if len(unique) > 1 else close.dropna()
                if len(prices) >= 2:
                    p, c = float(prices.iloc[-2]), float(prices.iloc[-1])
                    result[t] = round((c - p) / p * 100, 2) if p else 0.0
            except Exception:
                pass
    except Exception as e:
        print(f'[SectorBriefing] insider changes fetch error: {e}')
    return result


# ── 5. Sector News Headlines (yfinance ticker.news) ──────────────────────────

def _fetch_news_for_ticker(ticker: str, max_items: int = 3) -> List[dict]:
    """
    Fetch recent news for a single ticker via yfinance.
    Returns list of {title, source, ticker}.
    ticker.news can hang — caller must wrap with timeout.
    """
    try:
        t = yf.Ticker(ticker)
        raw = t.news or []
        results = []
        for item in raw[:max_items]:
            title = item.get('title', '') or item.get('headline', '')
            source = item.get('publisher', '') or item.get('source', '')
            if title:
                results.append({
                    'title': title,
                    'source': source,
                    'ticker': ticker,
                })
        return results
    except Exception as e:
        print(f'[SectorBriefing] news fetch error for {ticker}: {e}')
        return []


def _fetch_sector_news(etf_tickers: List[str]) -> Dict[str, List[dict]]:
    """
    Fetch news for multiple sector ETFs + their top holdings.
    Returns {etf: [news items]}.
    Each individual ticker fetch is capped at 4 seconds internally.
    """
    import concurrent.futures
    result: Dict[str, List[dict]] = {}

    for etf in etf_tickers:
        # Collect tickers: ETF itself + top holdings
        tickers_to_check = [etf] + ETF_TOP_HOLDINGS.get(etf, [])[:3]
        etf_news: List[dict] = []

        for ticker in tickers_to_check:
            if len(etf_news) >= 3:
                break
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(_fetch_news_for_ticker, ticker, 2)
                    items = future.result(timeout=4)
                    etf_news.extend(items)
            except (concurrent.futures.TimeoutError, Exception):
                pass

        # Deduplicate by title
        seen = set()
        deduped = []
        for n in etf_news:
            if n['title'] not in seen:
                seen.add(n['title'])
                deduped.append(n)
        result[etf] = deduped[:3]

    return result


# ── Main Entry Point ────────────────────────────────────────────────────────────

async def get_sector_briefing() -> dict:
    """
    Returns the full sector morning briefing dict:
      {generated_at, sectors, top_sector, sector_stocks, insider_trades}
    Uses 4 separate caches with different TTLs.
    No global lock — each cache section is independent, yfinance calls have timeouts.
    """
    global _etf_cache, _etf_cache_at
    global _drivers_cache, _drivers_cache_at
    global _stocks_cache, _stocks_cache_at, _stocks_sector
    global _insider_cache, _insider_cache_at
    global _news_cache, _news_cache_at

    now = _time.time()

    # ── 1a. ETF prices (30s TTL) ──────────────────────────────────────────────
    if _etf_cache is None or (now - _etf_cache_at) >= _ETF_CACHE_TTL:
        print('[SectorBriefing] Refreshing ETF prices...')
        try:
            sectors = await asyncio.wait_for(
                asyncio.to_thread(_fetch_etf_only),
                timeout=15,
            )
            if sectors:
                _etf_cache = sectors
                _etf_cache_at = _time.time()
        except (asyncio.TimeoutError, FuturesTimeout):
            print('[SectorBriefing] ETF-only fetch timeout')

    sectors = _etf_cache or []

    # ── 1b. Drivers (120s TTL) — can run concurrently with stocks/insider ─────
    drivers_stale = (now - _drivers_cache_at) >= _DRIVERS_CACHE_TTL

    # Determine top sector for stocks cache check
    top_sector = sectors[0] if sectors else None
    top_filter = top_sector['finviz_filter'] if top_sector else ''
    stocks_stale = (
        _stocks_cache is None
        or (now - _stocks_cache_at) >= _STOCKS_CACHE_TTL
        or _stocks_sector != top_filter
    )
    insider_stale = _insider_cache is None or (now - _insider_cache_at) >= _INSIDER_CACHE_TTL
    news_stale = not _news_cache or (now - _news_cache_at) >= _NEWS_CACHE_TTL

    # ── Launch independent fetches concurrently ───────────────────────────────
    drivers_task = None
    stocks_task = None
    insider_task = None
    news_task = None

    if drivers_stale:
        print('[SectorBriefing] Refreshing drivers...')
        drivers_task = asyncio.ensure_future(asyncio.wait_for(
            asyncio.to_thread(_fetch_drivers),
            timeout=20,
        ))

    if stocks_stale and top_sector:
        print(f'[SectorBriefing] Refreshing sector stocks ({top_sector["name"]})...')

        async def _do_stocks():
            async with aiohttp.ClientSession() as session:
                return await _fetch_sector_stocks(session, top_filter)

        stocks_task = asyncio.ensure_future(asyncio.wait_for(_do_stocks(), timeout=18))

    if insider_stale:
        print('[SectorBriefing] Refreshing insider trades...')

        async def _do_insider():
            async with aiohttp.ClientSession() as session:
                return await _fetch_insider_trades(session)

        insider_task = asyncio.ensure_future(asyncio.wait_for(_do_insider(), timeout=18))

    if news_stale and sectors:
        # Fetch news for top 5 sectors by absolute change
        top_etfs = [s['etf'] for s in sorted(sectors, key=lambda x: abs(x['change_pct']), reverse=True)[:5]]
        print(f'[SectorBriefing] Refreshing news for {top_etfs}...')
        news_task = asyncio.ensure_future(asyncio.wait_for(
            asyncio.to_thread(_fetch_sector_news, top_etfs),
            timeout=25,
        ))

    # ── Await drivers ─────────────────────────────────────────────────────────
    if drivers_task is not None:
        try:
            new_drivers = await drivers_task
            if new_drivers:
                _drivers_cache = new_drivers
                _drivers_cache_at = _time.time()
        except (asyncio.TimeoutError, FuturesTimeout):
            print('[SectorBriefing] drivers fetch timeout')
        except Exception as e:
            print(f'[SectorBriefing] drivers fetch error: {e}')

    # ── Await sector stocks ───────────────────────────────────────────────────
    if stocks_task is not None:
        try:
            new_stocks = await stocks_task
            _stocks_cache = new_stocks
            _stocks_cache_at = _time.time()
            _stocks_sector = top_filter
        except asyncio.TimeoutError:
            print('[SectorBriefing] sector stocks timeout')
        except Exception as e:
            print(f'[SectorBriefing] sector stocks error: {e}')

    # ── Await insider trades ──────────────────────────────────────────────────
    if insider_task is not None:
        try:
            new_insider = await insider_task
            if new_insider is not None:
                # Batch-fetch % change for insider tickers
                insider_tickers = list(dict.fromkeys(t['ticker'] for t in new_insider))
                try:
                    insider_chg = await asyncio.wait_for(
                        asyncio.to_thread(_fetch_insider_changes, insider_tickers),
                        timeout=15,
                    )
                except (asyncio.TimeoutError, FuturesTimeout):
                    insider_chg = {}

                for trade in new_insider:
                    trade['change_pct'] = insider_chg.get(trade['ticker'])

                _insider_cache = new_insider
                _insider_cache_at = _time.time()
        except asyncio.TimeoutError:
            print('[SectorBriefing] insider trades timeout')
        except Exception as e:
            print(f'[SectorBriefing] insider trades error: {e}')

    # ── Await news ───────────────────────────────────────────────────────────
    if news_task is not None:
        try:
            new_news = await news_task
            if new_news:
                _news_cache = new_news
                _news_cache_at = _time.time()
        except (asyncio.TimeoutError, FuturesTimeout):
            print('[SectorBriefing] news fetch timeout')
        except Exception as e:
            print(f'[SectorBriefing] news fetch error: {e}')

    # ── Merge drivers into sectors ────────────────────────────────────────────
    sectors_with_drivers = []
    for s in sectors:
        entry = dict(s)  # shallow copy
        etf = entry['etf']
        holdings = ETF_TOP_HOLDINGS.get(etf, [])
        drivers = []
        for h in holdings:
            h_chg = _drivers_cache.get(h)
            if h_chg is not None:
                drivers.append({'ticker': h, 'change_pct': h_chg})
        drivers.sort(key=lambda x: x['change_pct'], reverse=True)
        entry['drivers'] = drivers
        entry['news'] = _news_cache.get(etf, [])
        sectors_with_drivers.append(entry)

    sector_stocks = _stocks_cache or []
    insider_trades = _insider_cache or []

    result = {
        'generated_at':  datetime.now().isoformat(),
        'sectors':        sectors_with_drivers,
        'top_sector':     sectors_with_drivers[0] if sectors_with_drivers else None,
        'sector_stocks':  sector_stocks,
        'insider_trades': insider_trades,
    }

    top_name = result['top_sector']['name'] if result['top_sector'] else 'none'
    print(f'[SectorBriefing] Done — top: {top_name}, '
          f'stocks: {len(sector_stocks)}, insiders: {len(insider_trades)}')
    return result


def invalidate_cache() -> None:
    """Force-refresh next call — clears all 5 caches."""
    global _etf_cache_at, _drivers_cache_at, _stocks_cache_at, _insider_cache_at, _news_cache_at
    _etf_cache_at = 0.0
    _drivers_cache_at = 0.0
    _stocks_cache_at = 0.0
    _insider_cache_at = 0.0
    _news_cache_at = 0.0
