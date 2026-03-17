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
    """Fetch today's % change for all sector ETFs. Runs in thread (yfinance blocks)."""
    tickers = list(SECTOR_ETFS.keys())
    results = []
    try:
        data = yf.download(
            tickers,
            period='2d',
            interval='1d',
            progress=False,
            timeout=15,
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
                    'etf': etf,
                    'name': meta['name'],
                    'icon': meta['icon'],
                    'finviz_filter': meta['finviz'],
                    'change_pct': round(chg, 2),
                    'price': round(curr, 2),
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
        f'&f=sh_avgvol_o200,sh_relvol_o1,ta_change_u2,{finviz_filter}'
        '&o=-change'
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

        # Find the screener results table by looking for the header row
        table = None
        for t in soup.find_all('table'):
            header = t.find('tr')
            if header:
                header_texts = [td.get_text(strip=True) for td in header.find_all('td')]
                if 'Ticker' in header_texts:
                    table = t
                    break

        if not table:
            return []

        rows = table.find_all('tr')
        # Build column index from header row
        header_cells = rows[0].find_all('td')
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
                'ticker': ticker,
                'company': gcol(cells, 'Company'),
                'change_pct': chg,
                'rel_volume': rvol,
                'price': price,
                'volume': volume,
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
            # 2. Top movers in leading sector
            sector_stocks: List[dict] = []
            if top_sector:
                try:
                    sector_stocks = await asyncio.wait_for(
                        _fetch_sector_stocks(session, top_sector['finviz_filter']),
                        timeout=18,
                    )
                except asyncio.TimeoutError:
                    print('[SectorBriefing] sector stocks timeout')

            # 3. Insider trades (run concurrently with sector stocks would be ideal,
            #    but we already have the session; run sequentially to avoid overlap)
            try:
                insider_trades = await asyncio.wait_for(
                    _fetch_insider_trades(session),
                    timeout=18,
                )
            except asyncio.TimeoutError:
                print('[SectorBriefing] insider trades timeout')
                insider_trades = []

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
