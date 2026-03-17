"""
Sector Morning Briefing Service.

Each call returns:
1. Sector ETF leaderboard — all 11 sectors ranked by % change today
2. Top movers in the leading sector (Finviz screener with sector filter)
3. Insider trades — Form 4 purchases ≥ $100K in last 2 days (openinsider.com)

Cache TTL: 15 minutes
"""

import asyncio
import time as _time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
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

_cache: Optional[dict] = None
_cache_at: float = 0.0
_CACHE_TTL = 900  # 15 minutes
_cache_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock


# ── 1. Sector ETF Performance ───────────────────────────────────────────────────

def _fetch_etf_changes() -> List[dict]:
    """
    Fetch today's % change for all sector ETFs + their top holdings.
    Returns sectors list with 'drivers' field explaining the move.
    """
    etf_tickers = list(SECTOR_ETFS.keys())
    holding_tickers = list({t for holdings in ETF_TOP_HOLDINGS.values() for t in holdings})
    all_tickers = etf_tickers + holding_tickers

    holding_chg: Dict[str, float] = {}
    results = []
    try:
        data = yf.download(
            all_tickers,
            period='2d',
            interval='1d',
            progress=False,
            timeout=15,
            auto_adjust=True,
        )
        close = data.get('Close', data) if hasattr(data, 'get') else data

        def _pct(ticker: str) -> Optional[float]:
            try:
                prices = close[ticker].dropna()
                if len(prices) >= 2:
                    p, c = float(prices.iloc[-2]), float(prices.iloc[-1])
                    return (c - p) / p * 100 if p else 0.0
                return None
            except Exception:
                return None

        # Holdings % changes
        for t in holding_tickers:
            chg = _pct(t)
            if chg is not None:
                holding_chg[t] = round(chg, 2)

        # ETF % changes + drivers
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

                # Build drivers: top holdings sorted by their % change (desc)
                holdings = ETF_TOP_HOLDINGS.get(etf, [])
                drivers = []
                for h in holdings:
                    h_chg = holding_chg.get(h)
                    if h_chg is not None:
                        drivers.append({'ticker': h, 'change_pct': h_chg})
                drivers.sort(key=lambda x: x['change_pct'], reverse=True)

                results.append({
                    'etf':           etf,
                    'name':          meta['name'],
                    'icon':          meta['icon'],
                    'finviz_filter': meta['finviz'],
                    'change_pct':    round(chg, 2),
                    'price':         round(curr, 2),
                    'drivers':       drivers,
                })
            except Exception:
                pass

    except Exception as e:
        print(f"[SectorBriefing] ETF fetch error: {e}")

    return sorted(results, key=lambda x: x['change_pct'], reverse=True)


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


# ── Main Entry Point ────────────────────────────────────────────────────────────

async def get_sector_briefing() -> dict:
    """
    Returns the full sector morning briefing dict:
      {generated_at, sectors, top_sector, sector_stocks, insider_trades}
    Cached 15 minutes.
    """
    global _cache, _cache_at

    now = _time.time()
    if _cache is not None and (now - _cache_at) < _CACHE_TTL:
        return _cache

    lock = _get_lock()
    async with lock:
        now = _time.time()
        if _cache is not None and (now - _cache_at) < _CACHE_TTL:
            return _cache

        print('[SectorBriefing] Fetching sector data...')

        # 1. ETF performance — blocking yfinance in thread
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor(max_workers=1) as ex:
            try:
                sectors = await asyncio.wait_for(
                    loop.run_in_executor(ex, _fetch_etf_changes),
                    timeout=25,
                )
            except (asyncio.TimeoutError, FuturesTimeout):
                print('[SectorBriefing] ETF fetch timeout')
                sectors = []

        top_sector = sectors[0] if sectors else None

        async with aiohttp.ClientSession() as session:
            # 2+3 run concurrently
            async def _empty():
                return []
            sector_stocks_task = asyncio.ensure_future(
                _fetch_sector_stocks(session, top_sector['finviz_filter']) if top_sector
                else _empty()
            )
            insider_task = asyncio.ensure_future(_fetch_insider_trades(session))

            try:
                sector_stocks = await asyncio.wait_for(sector_stocks_task, timeout=18)
            except asyncio.TimeoutError:
                print('[SectorBriefing] sector stocks timeout')
                sector_stocks = []

            try:
                insider_trades = await asyncio.wait_for(insider_task, timeout=18)
            except asyncio.TimeoutError:
                print('[SectorBriefing] insider trades timeout')
                insider_trades = []

        # 4. Batch-fetch % change for insider tickers
        insider_tickers = list(dict.fromkeys(t['ticker'] for t in insider_trades))
        with ThreadPoolExecutor(max_workers=1) as ex:
            try:
                insider_chg = await asyncio.wait_for(
                    loop.run_in_executor(ex, _fetch_insider_changes, insider_tickers),
                    timeout=15,
                )
            except (asyncio.TimeoutError, FuturesTimeout):
                insider_chg = {}

        for trade in insider_trades:
            trade['change_pct'] = insider_chg.get(trade['ticker'])

        result = {
            'generated_at':  datetime.now().isoformat(),
            'sectors':        sectors,
            'top_sector':     top_sector,
            'sector_stocks':  sector_stocks,
            'insider_trades': insider_trades,
        }

        _cache = result
        _cache_at = _time.time()
        print(f'[SectorBriefing] Done — top: {top_sector["name"] if top_sector else "none"}, '
              f'stocks: {len(sector_stocks)}, insiders: {len(insider_trades)}')
        return result


def invalidate_cache() -> None:
    """Force-refresh next call."""
    global _cache_at
    _cache_at = 0.0
