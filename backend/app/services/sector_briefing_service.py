"""
Sector Briefing Service — Monster Edition.

Full sector intelligence dashboard:
1.  Sector ETF leaderboard — all 11 sectors ranked by % change today
2.  Multi-timeframe performance — 1D / 1W / 1M / 3M for each sector + SPY
3.  Intraday sparkline data — 5-minute close prices for mini charts
4.  Top movers in the leading sector (Finviz screener with sector filter)
5.  On-demand top movers for any sector (per-sector cache)
6.  Insider trades — Form 4 purchases ≥ $100K in last 2 days (openinsider.com)
7.  Sector rotation signal — growth vs defensive money flow
8.  Market pulse — up/down sector count, average change, SPY status
9.  Sector momentum scores — composite of multi-timeframe performance
10. Sector news headlines — last 24h, Hebrew-translated

8 separate caches with different TTLs for real-time accuracy:
  - ETF prices:      30s  (real-time sector ranking)
  - Drivers:        120s  (top holding % changes)
  - Multi-timeframe: 300s (1W/1M/3M — slow-changing)
  - Sparklines:      60s  (intraday 5m bars)
  - Sector stocks:  180s  (Finviz rate limit friendly, per leading sector)
  - Per-sector:     180s  (on-demand Finviz per sector)
  - Insider trades:  900s (slow-changing data)
  - News headlines:  300s (sector ETF + holding news via yfinance)
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
    'XLK':  {'name': 'טכנולוגיה',        'icon': '💻', 'finviz': 'sec_technology'},
    'XLF':  {'name': 'פיננסים',          'icon': '🏦', 'finviz': 'sec_financial'},
    'XLV':  {'name': 'בריאות',           'icon': '💊', 'finviz': 'sec_healthcare'},
    'XLE':  {'name': 'אנרגיה',           'icon': '⚡', 'finviz': 'sec_energy'},
    'XLI':  {'name': 'תעשייה',           'icon': '🏭', 'finviz': 'sec_industrials'},
    'XLY':  {'name': 'צריכה מחזורית',    'icon': '🛍️', 'finviz': 'sec_consumercyclical'},
    'XLP':  {'name': 'צריכה בסיסית',     'icon': '🛒', 'finviz': 'sec_consumerdefensive'},
    'XLC':  {'name': 'תקשורת',           'icon': '📡', 'finviz': 'sec_communicationservices'},
    'XLB':  {'name': 'חומרי גלם',        'icon': '⛏️', 'finviz': 'sec_basicmaterials'},
    'XLRE': {'name': 'נדל״ן',            'icon': '🏘️', 'finviz': 'sec_realestate'},
    'XLU':  {'name': 'שירותים',          'icon': '💡', 'finviz': 'sec_utilities'},
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

# Rotation classification
GROWTH_ETFS = {'XLK', 'XLY', 'XLC'}
DEFENSIVE_ETFS = {'XLU', 'XLP', 'XLV'}
CYCLICAL_ETFS = {'XLI', 'XLE', 'XLB'}

# Mapping Finviz sector names → our ETF keys
FINVIZ_SECTOR_MAP = {
    'Technology':              'XLK',
    'Financial':               'XLF',
    'Healthcare':              'XLV',
    'Energy':                  'XLE',
    'Industrials':             'XLI',
    'Consumer Cyclical':       'XLY',
    'Consumer Defensive':      'XLP',
    'Communication Services':  'XLC',
    'Basic Materials':         'XLB',
    'Real Estate':             'XLRE',
    'Utilities':               'XLU',
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

_multi_tf_cache: Optional[Dict[str, dict]] = None
_multi_tf_cache_at: float = 0.0
_MULTI_TF_TTL = 300  # 5 minutes — weekly/monthly data is slow-changing

_sparkline_cache: Optional[Dict[str, List[float]]] = None
_sparkline_cache_at: float = 0.0
_SPARKLINE_TTL = 60  # 1 minute

_stocks_cache: Optional[List[dict]] = None
_stocks_cache_at: float = 0.0
_stocks_sector: str = ''  # which sector the cached stocks are for
_STOCKS_CACHE_TTL = 180  # 3 minutes (Finviz rate limit)

# Per-sector movers cache (on-demand)
_per_sector_cache: Dict[str, dict] = {}  # {finviz_filter: {'data': [...], 'at': float}}
_PER_SECTOR_TTL = 180  # 3 minutes

_insider_cache: Optional[List[dict]] = None
_insider_cache_at: float = 0.0
_INSIDER_CACHE_TTL = 300  # 5 minutes — insider filings trickle in throughout the day

_news_cache: Dict[str, List[dict]] = {}  # {etf: [{title, source, ticker}]}
_news_cache_at: float = 0.0
_NEWS_CACHE_TTL = 300  # 5 minutes

# Macro indicators cache
_macro_cache: Optional[dict] = None
_macro_cache_at: float = 0.0
_MACRO_TTL = 60  # 1 minute — critical real-time data

# Market-wide news cache
_market_news_cache: Optional[List[dict]] = None
_market_news_cache_at: float = 0.0
_MARKET_NEWS_TTL = 300  # 5 minutes

# All-sector movers cache (unified Finviz call)
_all_movers_cache: Optional[Dict[str, dict]] = None
_all_movers_cache_at: float = 0.0
_ALL_MOVERS_TTL = 180  # 3 minutes

# Stock intelligence cache (analyst targets, earnings, catalysts)
_intel_cache: Optional[Dict[str, dict]] = None
_intel_cache_at: float = 0.0
_INTEL_TTL = 300  # 5 minutes

# ── Macro Indicator Definitions ──────────────────────────────────────────────────

MACRO_TICKERS = {
    '^VIX':      {'name': 'VIX',       'label': 'מדד פחד',        'icon': '😰', 'type': 'fear'},
    'GC=F':      {'name': 'זהב',       'label': 'זהב',           'icon': '🥇', 'type': 'safe_haven'},
    'CL=F':      {'name': 'נפט',       'label': 'נפט גולמי',     'icon': '🛢️', 'type': 'commodity'},
    'NG=F':      {'name': 'גז טבעי',   'label': 'גז טבעי',       'icon': '🔥', 'type': 'commodity'},
    '^TNX':      {'name': '10Y',       'label': 'תשואה 10 שנים', 'icon': '📊', 'type': 'rates'},
    'DX-Y.NYB':  {'name': 'דולר',      'label': 'מדד דולר',      'icon': '💵', 'type': 'currency'},
    '^GSPC':     {'name': 'S&P 500',   'label': 'S&P 500',       'icon': '📈', 'type': 'index'},
}

# Sector impact rules: when indicator moves, which sectors are affected
# (indicator, threshold_pct, affected_etfs, impact, hebrew_explanation)
IMPACT_RULES = [
    # VIX (fear)
    ('^VIX', 5,    ['XLU', 'XLP', 'XLV'], 'positive',  'VIX קופץ → כסף זורם להגנתיים'),
    ('^VIX', 5,    ['XLK', 'XLY', 'XLC'], 'negative',  'VIX קופץ → צמיחה תחת לחץ'),
    ('^VIX', 10,   ['XLE', 'XLI', 'XLB'], 'negative',  'VIX זינוק → מחזוריים נפגעים'),
    # Oil
    ('CL=F', 2,    ['XLE'],               'positive',  'נפט עולה → אנרגיה מרוויחה'),
    ('CL=F', 2,    ['XLI'],               'negative',  'נפט עולה → עלויות תעשייה עולות'),
    ('CL=F', -3,   ['XLE'],               'negative',  'נפט צונח → אנרגיה תחת לחץ'),
    ('CL=F', -3,   ['XLI', 'XLY'],        'positive',  'נפט יורד → הקלה בעלויות'),
    # Natural Gas
    ('NG=F', 3,    ['XLE'],               'positive',  'גז טבעי עולה → אנרגיה מרוויחה'),
    ('NG=F', 5,    ['XLE'],               'positive',  'גז טבעי זינוק → small-cap אנרגיה ירוצו'),
    ('NG=F', -4,   ['XLE'],               'negative',  'גז טבעי צונח → לחץ על מפיקי גז'),
    ('NG=F', 3,    ['XLU'],               'positive',  'גז טבעי עולה → חברות חשמל יעלו מחירים'),
    # Gold
    ('GC=F', 1.5,  ['XLB'],               'positive',  'זהב עולה → חומרי גלם מרוויחים'),
    ('GC=F', 2,    ['XLK', 'XLY'],        'negative',  'זהב קופץ → סנטימנט risk-off'),
    # Rates
    ('^TNX', 2,    ['XLF'],               'positive',  'תשואות עולות → בנקים מרוויחים'),
    ('^TNX', 2,    ['XLRE', 'XLU'],       'negative',  'תשואות עולות → נדל"ן ושירותים תחת לחץ'),
    ('^TNX', 3,    ['XLK'],               'negative',  'תשואות זינוק → טכנולוגיה תחת לחץ (DCF)'),
    ('^TNX', -2,   ['XLRE', 'XLU'],       'positive',  'תשואות יורדות → נדל"ן ושירותים מרוויחים'),
    ('^TNX', -2,   ['XLK'],               'positive',  'תשואות יורדות → טכנולוגיה מרוויחה'),
    # USD
    ('DX-Y.NYB', 1, ['XLK', 'XLI'],      'negative',  'דולר חזק → פוגע ביצואנים'),
    ('DX-Y.NYB', -1, ['XLK', 'XLB'],     'positive',  'דולר חלש → יצואנים מרוויחים'),
]

# VIX level interpretation
VIX_LEVELS = [
    (35, 'קיצוני',   'extreme', 'פאניקה בשוק — סיכון גבוה מאוד'),
    (25, 'גבוה',     'high',    'פחד מוגבר — תנודתיות חריגה'),
    (20, 'מוגבר',    'elevated','תנודתיות מעל הממוצע'),
    (15, 'רגיל',     'normal',  'שוק רגוע יחסית'),
    (0,  'נמוך',     'low',     'שאננות — זהירות מפיכה'),
]


# ── 1a. Sector ETF Performance (ETFs only) ───────────────────────────────────────

def _get_live_price(ticker_obj) -> dict:
    """Get the most current price: pre-market > post-market > regular.
    yfinance returns changePercent as actual percentage (e.g. 0.58 = 0.58%)."""
    try:
        info = ticker_obj.get_info() if hasattr(ticker_obj, 'get_info') else ticker_obj.info
        pre_price = info.get('preMarketPrice')
        pre_chg = info.get('preMarketChangePercent')
        post_price = info.get('postMarketPrice')
        post_chg = info.get('postMarketChangePercent')
        reg_price = info.get('regularMarketPrice') or info.get('currentPrice')
        reg_chg = info.get('regularMarketChangePercent')

        # Priority: pre-market > post-market > regular
        if pre_price and pre_chg is not None:
            return {'price': round(pre_price, 2), 'change_pct': round(pre_chg, 2), 'session': 'pre'}
        if post_price and post_chg is not None:
            return {'price': round(post_price, 2), 'change_pct': round(post_chg, 2), 'session': 'post'}
        if reg_price and reg_chg is not None:
            return {'price': round(reg_price, 2), 'change_pct': round(reg_chg, 2), 'session': 'regular'}
    except Exception:
        pass
    return {}


def _fetch_live_prices_batch(tickers: List[str]) -> Dict[str, dict]:
    """Fast batch fetch: yf.download for prices, then quick change calc."""
    result: Dict[str, dict] = {}
    unique = list(dict.fromkeys(tickers))[:15]
    if not unique:
        return result
    try:
        data = yf.download(unique, period='5d', interval='1d', progress=False,
                           timeout=10, auto_adjust=True, prepost=True)
        close = data.get('Close', data) if hasattr(data, 'get') else data
        for t in unique:
            try:
                prices = close[t].dropna() if len(unique) > 1 else close.dropna()
                if len(prices) >= 2:
                    p, c = float(prices.iloc[-2]), float(prices.iloc[-1])
                    result[t] = {
                        'change_pct': round((c - p) / p * 100, 2) if p else 0.0,
                        'price': round(c, 2),
                        'session': 'regular',
                    }
            except Exception:
                pass
    except Exception:
        pass
    return result


def _fetch_etf_only() -> List[dict]:
    """
    Fetch today's % change for the 11 sector ETFs.
    Fast: single yf.download batch call (~2-3s), not 11 individual .info calls.
    """
    etf_tickers = list(SECTOR_ETFS.keys())
    results = []
    try:
        data = yf.download(etf_tickers, period='5d', interval='1d', progress=False,
                           timeout=10, auto_adjust=True, prepost=True)
        close = data.get('Close', data) if hasattr(data, 'get') else data
        for etf, meta in SECTOR_ETFS.items():
            try:
                prices = close[etf].dropna()
                if len(prices) >= 2:
                    prev, curr = float(prices.iloc[-2]), float(prices.iloc[-1])
                    chg = (curr - prev) / prev * 100 if prev else 0.0
                    results.append({
                        'etf': etf, 'name': meta['name'], 'icon': meta['icon'],
                        'finviz_filter': meta['finviz'],
                        'change_pct': round(chg, 2), 'price': round(curr, 2),
                    })
            except Exception:
                pass
    except Exception as e:
        print(f"[SectorBriefing] ETF fetch error: {e}")

    return sorted(results, key=lambda x: x['change_pct'], reverse=True)


# ── 1b. Driver Holdings % Changes ────────────────────────────────────────────────

def _fetch_drivers() -> Dict[str, float]:
    """
    Fetch today's % change for the 33 unique top-holding tickers.
    Uses live prices for top 15, batch download for the rest.
    Returns {ticker: change_pct}.
    """
    holding_tickers = list({t for holdings in ETF_TOP_HOLDINGS.values() for t in holdings})
    result: Dict[str, float] = {}

    # Batch download all — fast and memory-friendly
    try:
        data = yf.download(holding_tickers, period='5d', interval='1d', progress=False, timeout=12, auto_adjust=True)
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


# ── 1c. Multi-Timeframe Performance (1W / 1M / 3M) + SPY ─────────────────────────

def _fetch_multi_timeframe() -> Dict[str, dict]:
    """
    Fetch 1W, 1M, 3M performance for all 11 sector ETFs + SPY.
    Returns {ticker: {w1: float, m1: float, m3: float, price: float}}.
    Single yf.download call with period='3mo'.
    """
    tickers = list(SECTOR_ETFS.keys()) + ['SPY']
    result: Dict[str, dict] = {}
    try:
        data = yf.download(
            tickers,
            period='3mo',
            interval='1d',
            progress=False,
            timeout=15,
            auto_adjust=True,
        )
        close = data.get('Close', data) if hasattr(data, 'get') else data

        # Also fetch volume for ETF volume ratio
        vol = data.get('Volume', None)

        for t in tickers:
            try:
                prices = close[t].dropna()
                if len(prices) < 2:
                    continue
                current = float(prices.iloc[-1])

                def pct_ago(n_days):
                    idx = min(n_days, len(prices) - 1)
                    if idx <= 0:
                        return None
                    ref = float(prices.iloc[-idx - 1])
                    return round((current - ref) / ref * 100, 2) if ref else 0.0

                entry = {
                    'w1': pct_ago(5),
                    'm1': pct_ago(21),
                    'm3': pct_ago(63),
                    'price': round(current, 2),
                }

                # Volume ratio: today vs 20-day average
                if vol is not None:
                    try:
                        volumes = vol[t].dropna()
                        if len(volumes) >= 2:
                            today_vol = float(volumes.iloc[-1])
                            avg_vol = float(volumes.iloc[-21:].mean()) if len(volumes) >= 21 else float(volumes.mean())
                            entry['volume_ratio'] = round(today_vol / avg_vol, 2) if avg_vol > 0 else 1.0
                    except Exception:
                        pass

                result[t] = entry
            except Exception:
                pass

    except Exception as e:
        print(f"[SectorBriefing] multi-tf fetch error: {e}")

    return result


# ── 1d. Intraday Sparkline Data (5m bars) ─────────────────────────────────────────

def _fetch_sparklines() -> Dict[str, List[float]]:
    """
    Fetch intraday 5-minute close prices for all sector ETFs.
    Returns {etf: [price1, price2, ...]} for mini-chart rendering.
    """
    tickers = list(SECTOR_ETFS.keys())
    result: Dict[str, List[float]] = {}
    try:
        data = yf.download(
            tickers,
            period='1d',
            interval='5m',
            progress=False,
            timeout=12,
            auto_adjust=True,
            prepost=True,
        )
        close = data.get('Close', data) if hasattr(data, 'get') else data

        for t in tickers:
            try:
                prices = close[t].dropna().tolist()
                if prices:
                    result[t] = [round(float(p), 2) for p in prices]
            except Exception:
                pass

    except Exception as e:
        print(f"[SectorBriefing] sparkline fetch error: {e}")

    return result


# ── 2. Top Movers in Sector (Finviz) ───────────────────────────────────────────

async def _fetch_sector_stocks(
    session: aiohttp.ClientSession,
    finviz_filter: str,
) -> List[dict]:
    """
    Fetch top movers within a sector from Finviz screener.
    Filters: avg vol > 200K, sorted by change desc.
    """
    url = (
        'https://finviz.com/screener.ashx?v=111'
        f'&f=sh_avgvol_o200,{finviz_filter}'
        '&o=-change&r=1'
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
            for t in soup.find_all('table'):
                hdr = t.find('tr')
                if hdr and 'Ticker' in [c.get_text(strip=True) for c in hdr.find_all(['th', 'td'])]:
                    table = t
                    break

        if not table:
            return []

        rows = table.find_all('tr')
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

            if len(stocks) >= 15:
                break

        return stocks

    except Exception as e:
        print(f"[SectorBriefing] Finviz sector stocks error ({finviz_filter}): {e}")
        return []


# ── 3. Insider Trades (Form 4 — openinsider.com) ───────────────────────────────

async def _fetch_insider_trades(session: aiohttp.ClientSession) -> List[dict]:
    """
    Scrape openinsider.com for recent Form 4 cluster buys.
    Filters: purchases only, value ≥ $100K, last 5 days (covers weekends), top 30.
    """
    url = (
        'http://openinsider.com/screener?'
        's=&o=&pl=&ph=&ll=&lh=&fd=5&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&'
        'xp=1&vl=100&vh=&ocl=&och=&sic1=-1&sicl=100&sich=9999&grp=0&'
        'nfl=&nfh=&nil=&nih=&nol=&noh=&v2l=&v2h=&oc2l=&oc2h=&'
        'sortcol=0&cnt=100&action=1'
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

        header_cells = rows[0].find_all(['th', 'td'])
        headers = [h.get_text(strip=True).replace('\xa0', ' ') for h in header_cells]

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

            if len(trades) >= 30:
                break

        return trades

    except Exception as e:
        print(f"[SectorBriefing] insider trades fetch error: {e}")
        return []


# ── 3b. Insider History + Track Record Scoring ───────────────────────────────────

_insider_score_cache: Dict[str, dict] = {}   # {ticker: {scores, fetched_at}}
_INSIDER_SCORE_TTL = 86400  # 24 hours — track records change slowly

async def _fetch_insider_history(session: aiohttp.ClientSession, ticker: str) -> List[dict]:
    """
    Fetch 6-month insider trade history for a ticker from OpenInsider.
    Returns list of {insider, date, price, value, trade_type}.
    """
    url = (
        f'http://openinsider.com/screener?s={ticker}&o=&pl=&ph=&ll=&lh=&fd=180'
        '&fdr=&td=0&tdr=&fdlyl=&fdlyh=&daysago=&xp=1&vl=25&vh=&ocl=&och=&'
        'sic1=-1&sicl=100&sich=9999&grp=0&nfl=&nfh=&nil=&nih=&nol=&noh=&'
        'v2l=&v2h=&oc2l=&oc2h=&sortcol=0&cnt=100&action=1'
    )
    try:
        async with session.get(
            url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=12)
        ) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()

        soup = BeautifulSoup(html, 'html.parser')
        table = soup.find('table', class_='tinytable')
        if not table:
            return []

        rows = table.find_all('tr')
        if len(rows) < 2:
            return []

        header_cells = rows[0].find_all(['th', 'td'])
        headers = [h.get_text(strip=True).replace('\xa0', ' ') for h in header_cells]

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
            insider = gcell(cells, 'Insider Name', 'Insider')
            title   = gcell(cells, 'Title')
            date_s  = gcell(cells, 'Filing Date', 'Date', 'Filed')
            price   = gcell(cells, 'Price')
            value   = gcell(cells, 'Value', 'Val')
            trade_type = gcell(cells, 'Trade Type', 'Type', 'X')

            # Only purchases
            if trade_type and 'P' not in trade_type:
                continue

            try:
                price_f = float(price.replace('$', '').replace(',', ''))
            except (ValueError, TypeError):
                price_f = None

            trades.append({
                'insider': insider,
                'title':   title,
                'date':    date_s,
                'price':   price_f,
                'value':   value,
            })
        return trades

    except Exception as e:
        print(f'[SectorBriefing] insider history fetch error ({ticker}): {e}')
        return []


def _score_insider_track_record(
    history: List[dict], price_data, current_trades: List[dict]
) -> Dict[str, dict]:
    """
    Score each insider based on stock performance 30 days after their historical buys.
    price_data: pandas DataFrame with daily Close prices for the ticker (6+ months).
    Returns {insider_name: {win_rate, avg_return, total_trades, grade}}.
    """
    from datetime import date, timedelta

    if price_data is None or price_data.empty:
        return {}

    # Build a date→price lookup (handle both DataFrame and Series from yfinance)
    import pandas as pd
    price_lookup = {}
    if isinstance(price_data, pd.Series):
        for idx, val in price_data.items():
            d = idx.date() if hasattr(idx, 'date') else idx
            try:
                price_lookup[d] = float(val)
            except (ValueError, TypeError):
                pass
    else:
        for idx, row in price_data.iterrows():
            d = idx.date() if hasattr(idx, 'date') else idx
            try:
                price_lookup[d] = float(row.iloc[0]) if hasattr(row, 'iloc') else float(row)
            except (ValueError, TypeError):
                pass

    if not price_lookup:
        return {}

    sorted_dates = sorted(price_lookup.keys())
    last_date = sorted_dates[-1] if sorted_dates else date.today()

    # Group historical trades by insider
    insider_trades_map: Dict[str, list] = {}
    for h in history:
        name = h.get('insider', '').strip()
        if not name:
            continue
        if name not in insider_trades_map:
            insider_trades_map[name] = []
        insider_trades_map[name].append(h)

    # Also add current insiders we're interested in (so they get scored even if no history)
    for t in current_trades:
        name = (t.get('insider') or '').strip()
        if name and name not in insider_trades_map:
            insider_trades_map[name] = []

    scores: Dict[str, dict] = {}
    for insider_name, trades in insider_trades_map.items():
        wins = 0
        total = 0
        returns = []

        for trade in trades:
            buy_date = None
            try:
                ds = trade.get('date', '')
                if ' ' in ds:
                    ds = ds.split(' ')[0]
                buy_date = date.fromisoformat(ds)
            except (ValueError, TypeError):
                continue

            buy_price = trade.get('price')
            if not buy_price:
                continue

            # Find price ~30 days later
            check_date = buy_date + timedelta(days=30)
            # If check_date is in the future, use latest available
            if check_date > last_date:
                check_date = last_date
                # Skip if buy was too recent (< 10 days) to judge
                if (last_date - buy_date).days < 10:
                    continue

            # Find closest trading day to check_date
            best_date = None
            for d in sorted_dates:
                if d >= check_date:
                    best_date = d
                    break
            if best_date is None and sorted_dates:
                best_date = sorted_dates[-1]

            if best_date and best_date in price_lookup:
                later_price = price_lookup[best_date]
                ret = (later_price - buy_price) / buy_price * 100
                returns.append(ret)
                total += 1
                if ret > 0:
                    wins += 1

        if total > 0:
            win_rate = round(wins / total * 100)
            avg_ret = round(sum(returns) / len(returns), 1)
        else:
            win_rate = None
            avg_ret = None

        # Grade: A (track record ≥ 70%), B (≥ 50%), C (< 50%), N (new/unknown)
        if total >= 1 and win_rate is not None:
            if win_rate >= 70:
                grade = 'A'
            elif win_rate >= 50:
                grade = 'B'
            else:
                grade = 'C'
        else:
            grade = 'N'  # New — not enough data

        scores[insider_name] = {
            'win_rate': win_rate,
            'avg_return': avg_ret,
            'total_trades': total,
            'grade': grade,
        }

    return scores


def _enrich_cluster_buys(trades: List[dict]) -> None:
    """Fast synchronous grouping of trades by ticker for cluster buy detection."""
    ticker_groups: Dict[str, list] = {}
    for t in trades:
        tk = t.get('ticker', '')
        if tk:
            ticker_groups.setdefault(tk, []).append(t)

    for tk, group in ticker_groups.items():
        count = len(group)
        for t in group:
            t['same_ticker_buys'] = count
            if count > 1:
                others = [
                    {'insider': o.get('insider', ''), 'value': o.get('value', ''),
                     'date': o.get('date', ''), 'title': o.get('title', '')}
                    for o in group if o is not t
                ]
                t['other_buyers'] = others
            else:
                t['other_buyers'] = []


async def _enrich_insider_scores(
    session: aiohttp.ClientSession, trades: List[dict]
) -> None:
    """
    For each unique ticker in trades, fetch 6-month insider history + price data,
    score each insider's track record, and attach results to trades.
    """
    import concurrent.futures

    ticker_groups: Dict[str, list] = {}
    for t in trades:
        tk = t.get('ticker', '')
        if tk:
            ticker_groups.setdefault(tk, []).append(t)

    # ── Insider track record scoring ──────────────────────────────────
    now = _time.time()
    tickers_to_score = []
    for tk in ticker_groups:
        cached = _insider_score_cache.get(tk)
        if cached and (now - cached.get('fetched_at', 0)) < _INSIDER_SCORE_TTL:
            # Use cached scores
            for t in ticker_groups[tk]:
                insider_name = (t.get('insider') or '').strip()
                sc = cached.get('scores', {}).get(insider_name, {})
                t['insider_grade'] = sc.get('grade', 'N')
                t['insider_win_rate'] = sc.get('win_rate')
                t['insider_avg_return'] = sc.get('avg_return')
                t['insider_total_trades'] = sc.get('total_trades', 0)
        else:
            tickers_to_score.append(tk)

    if not tickers_to_score:
        return

    # Limit to 8 tickers to avoid overloading
    tickers_to_score = tickers_to_score[:8]

    # Fetch history + prices in parallel
    history_tasks = {
        tk: _fetch_insider_history(session, tk) for tk in tickers_to_score
    }
    histories = {}
    for tk, coro in history_tasks.items():
        try:
            histories[tk] = await asyncio.wait_for(coro, timeout=12)
        except (asyncio.TimeoutError, Exception) as e:
            print(f'[SectorBriefing] insider history timeout/error ({tk}): {e}')
            histories[tk] = []

    # Fetch 6-month price data for all tickers at once
    price_data = {}
    try:
        def _dl():
            return yf.download(
                tickers_to_score, period='6mo', interval='1d',
                progress=False, timeout=15, auto_adjust=True
            )
        raw = await asyncio.wait_for(asyncio.to_thread(_dl), timeout=20)
        close = raw.get('Close', raw) if hasattr(raw, 'get') else raw
        for tk in tickers_to_score:
            try:
                if len(tickers_to_score) > 1:
                    col = close[tk].dropna()
                else:
                    col = close.dropna()
                price_data[tk] = col
            except Exception:
                pass
    except (asyncio.TimeoutError, Exception) as e:
        print(f'[SectorBriefing] insider price history error: {e}')

    # Score each ticker's insiders
    for tk in tickers_to_score:
        hist = histories.get(tk, [])
        prices = price_data.get(tk)
        group_trades = ticker_groups.get(tk, [])

        scores = _score_insider_track_record(hist, prices, group_trades)

        # Cache it
        _insider_score_cache[tk] = {
            'scores': scores,
            'fetched_at': now,
        }

        # Attach to trades
        for t in group_trades:
            insider_name = (t.get('insider') or '').strip()
            sc = scores.get(insider_name, {})
            t['insider_grade'] = sc.get('grade', 'N')
            t['insider_win_rate'] = sc.get('win_rate')
            t['insider_avg_return'] = sc.get('avg_return')
            t['insider_total_trades'] = sc.get('total_trades', 0)


# ── 4. Insider Why Analysis ──────────────────────────────────────────────────────

# Catalyst keyword patterns — ordered by specificity
_CATALYST_PATTERNS = [
    # FDA / biotech approvals
    (['fda approv', 'fda clear', 'nda approv', 'pdufa', 'breakthrough therap',
      'fast track', 'priority review', 'eua', 'emergency use'],
     'fda'),
    # Earnings / guidance
    (['beat estimat', 'beats estimat', 'earnings beat', 'revenue beat',
      'raised guidance', 'raises guidance', 'upside guidance', 'record revenue',
      'record earnings', 'record profit', 'strong quarter', 'blowout quarter',
      'eps beat', 'quarterly results'],
     'earnings_beat'),
    (['earnings miss', 'revenue miss', 'misses estimat', 'lowered guidance',
      'cuts guidance', 'weak quarter', 'disappointing'],
     'earnings_miss'),
    # Partnerships / contracts / deals
    (['partnership', 'strategic alliance', 'collaborat', 'licensing deal',
      'license agreement', 'joint venture', 'distribution deal',
      'government contract', 'defense contract', 'awarded contract',
      'supply agreement', 'multi-year deal', 'billion dollar deal',
      'major contract'],
     'deal'),
    # M&A / buyout
    (['acquisition', 'acquire', 'merger', 'buyout', 'takeover', 'tender offer',
      'goes private', 'take private'],
     'ma'),
    # Analyst upgrades
    (['upgrade', 'price target raised', 'raises price target', 'initiates coverage',
      'outperform', 'overweight'],
     'upgrade'),
    (['downgrade', 'price target cut', 'lowers price target', 'underperform',
      'underweight'],
     'downgrade'),
    # Clinical trials (biotech)
    (['phase 3', 'phase iii', 'pivotal trial', 'positive data', 'trial success',
      'primary endpoint', 'topline results', 'clinical data'],
     'trial_data'),
    # Buyback / dividend
    (['buyback', 'share repurchase', 'repurchase program', 'dividend increase',
      'special dividend', 'dividend hike'],
     'buyback'),
    # Sector / macro
    (['tariff', 'trade war', 'sanctions', 'stimulus', 'rate cut', 'rate hike',
      'inflation data', 'jobs report', 'fed meeting'],
     'macro'),
]


def _classify_news_catalyst(news_items: List[dict]) -> Optional[str]:
    """
    Analyze recent news headlines and return a short, specific catalyst reason.
    Returns None if no clear catalyst found.
    """
    if not news_items:
        return None

    for item in news_items:
        title_lower = (item.get('title') or '').lower()
        if not title_lower:
            continue

        for keywords, cat in _CATALYST_PATTERNS:
            if any(kw in title_lower for kw in keywords):
                title = item['title']
                source = item.get('source', '')
                src_tag = f' ({source})' if source else ''

                if cat == 'fda':
                    return f'אישור/התקדמות FDA — {title}{src_tag}'
                elif cat == 'earnings_beat':
                    return f'דוחות חזקים — {title}{src_tag}'
                elif cat == 'earnings_miss':
                    return f'קונה אחרי דוחות חלשים (contrarian) — {title}{src_tag}'
                elif cat == 'deal':
                    return f'עסקה/שותפות חדשה — {title}{src_tag}'
                elif cat == 'ma':
                    return f'מיזוג/רכישה — {title}{src_tag}'
                elif cat == 'upgrade':
                    return f'שדרוג אנליסט — {title}{src_tag}'
                elif cat == 'downgrade':
                    return f'קונה אחרי דאונגרייד (contrarian) — {title}{src_tag}'
                elif cat == 'trial_data':
                    return f'תוצאות ניסוי קליני — {title}{src_tag}'
                elif cat == 'buyback':
                    return f'תוכנית רכישה עצמית/דיבידנד — {title}{src_tag}'
                elif cat == 'macro':
                    return f'אירוע מאקרו משפיע — {title}{src_tag}'

    return None


def _fetch_insider_news_batch(tickers: List[str]) -> Dict[str, List[dict]]:
    """
    Batch-fetch recent news for insider tickers (threaded, max 3 concurrent).
    Returns {ticker: [news_items]}.
    """
    import concurrent.futures
    if not tickers:
        return {}

    unique = list(dict.fromkeys(tickers))[:15]
    result: Dict[str, List[dict]] = {}

    def _get_news(ticker):
        return ticker, _fetch_news_for_ticker(ticker, max_items=5)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_get_news, t): t for t in unique}
        for future in concurrent.futures.as_completed(futures, timeout=15):
            try:
                t, news = future.result(timeout=3)
                if news:
                    result[t] = news
            except Exception:
                pass

    return result


def _insider_why(trade: dict) -> str:
    """
    Generate a specific Hebrew explanation of WHY this insider is buying.
    Priority: real catalyst from news > earnings/guidance > analyst targets > price action.
    Rules: max 1-2 lines, must be tied to a real catalyst or data.
    """
    # Priority 1: News-based catalyst (most specific)
    news_catalyst = trade.get('_news_catalyst')
    if news_catalyst:
        return news_catalyst

    title = (trade.get('title') or '').upper()
    chg = trade.get('change_pct')
    mcap_str = trade.get('market_cap_live', '')
    val_str = trade.get('value', '')
    target = trade.get('target_price')
    upside = trade.get('upside_pct')
    earnings = trade.get('earnings_date')

    # Parse purchase value
    try:
        purchase_val = int(val_str.replace('$', '').replace(',', '').replace('+', ''))
    except (ValueError, TypeError):
        purchase_val = 0

    # Priority 2: Earnings timing — strongest non-news signal
    if earnings:
        from datetime import date
        try:
            today = date.today()
            ed = date.fromisoformat(earnings)
            days = (ed - today).days
            if days == 0:
                return 'דוחות היום — קנה לפני פרסום התוצאות'
            elif 0 < days <= 7:
                who = 'CEO' if 'CEO' in title else 'CFO' if 'CFO' in title else 'insider'
                return f'דוחות עוד {days} ימים — {who} צובר לפני הדוחות'
            elif 0 < days <= 14:
                return f'דוחות ב-{earnings} — רוכש 2 שבועות לפני'
        except (ValueError, TypeError):
            pass

    # Priority 3: Massive purchase relative to market cap
    if mcap_str and purchase_val:
        try:
            if mcap_str.endswith('B'):
                mcap_val = float(mcap_str[:-1]) * 1e9
            elif mcap_str.endswith('M'):
                mcap_val = float(mcap_str[:-1]) * 1e6
            else:
                mcap_val = None
            if mcap_val:
                pct = (purchase_val / mcap_val) * 100
                if pct >= 0.5:
                    return f'קנייה חריגה — {pct:.1f}% משווי החברה. סימן חזק לאירוע צפוי'
        except (ValueError, TypeError):
            pass

    # Priority 4: Analyst target with big upside + dip buying
    if target and upside and chg is not None:
        if upside > 50 and chg < -3:
            return f'קונה בירידה של {chg:.1f}% — יעד אנליסטים ${target} ({upside:+.0f}% פוטנציאל)'
        elif upside > 80:
            return f'יעד אנליסטים ${target} — פוטנציאל של {upside:.0f}% מהמחיר הנוכחי'

    # Priority 5: Dip buying (significant drop)
    if chg is not None and chg < -8:
        who = 'CEO' if 'CEO' in title else 'CFO' if 'CFO' in title else 'Insider'
        return f'{who} קונה אחרי ירידה של {chg:.1f}% — contrarian buy בתחתית'

    # Priority 6: Volume breakout (large purchase by C-suite on uptick)
    if chg is not None and chg > 5 and purchase_val >= 500_000:
        if 'CEO' in title or 'CFO' in title:
            who = 'CEO' if 'CEO' in title else 'CFO'
            return f'{who} שם ${purchase_val:,} אחרי עלייה של {chg:+.1f}% — מצפה להמשך'

    # No clear catalyst
    return 'No clear catalyst'


# ── 4b. Insider Enrichment (yfinance batch) ─────────────────────────────────────

def _fetch_insider_enrichment(tickers: List[str]) -> Dict[str, dict]:
    """
    Batch-fetch today's % change + current price + market cap for insider tickers.
    Uses prepost=True for pre/after-hours data.
    Returns {ticker: {change_pct, price, market_cap}}.
    """
    if not tickers:
        return {}
    unique = list(dict.fromkeys(tickers))[:30]
    result: Dict[str, dict] = {}

    # Phase 1: Live prices (pre/post/regular market)
    live = _fetch_live_prices_batch(unique[:15])
    for t, d in live.items():
        result[t] = {'change_pct': d['change_pct'], 'price': d['price']}

    # Fallback for tickers missing from live fetch
    missing = [t for t in unique if t not in result]
    if missing:
        try:
            data = yf.download(missing, period='5d', interval='1d', progress=False, timeout=12, auto_adjust=True)
            close = data.get('Close', data) if hasattr(data, 'get') else data
            for t in missing:
                try:
                    prices = close[t].dropna() if len(missing) > 1 else close.dropna()
                    if len(prices) >= 2:
                        p, c = float(prices.iloc[-2]), float(prices.iloc[-1])
                        result[t] = {'change_pct': round((c - p) / p * 100, 2) if p else 0.0, 'price': round(c, 2)}
                except Exception:
                    pass
        except Exception as e:
            print(f'[SectorBriefing] insider price fallback error: {e}')

    # Phase 2: Full company intel from Ticker.info (threaded)
    import concurrent.futures

    def _get_company_intel(ticker):
        """Fetch market cap, industry, business summary, analyst target, earnings."""
        intel = {}
        try:
            t = yf.Ticker(ticker)
            info = t.get_info() if hasattr(t, 'get_info') else t.info

            # Market cap
            mcap = info.get('marketCap') or info.get('market_cap')
            if mcap:
                if mcap >= 1_000_000_000:
                    intel['market_cap'] = f'{mcap / 1_000_000_000:.1f}B'
                elif mcap >= 1_000_000:
                    intel['market_cap'] = f'{mcap / 1_000_000:.0f}M'

            # Industry + sector
            intel['industry'] = info.get('industry', '')
            intel['sector'] = info.get('sector', '')

            # Business summary — first sentence only
            summary = info.get('longBusinessSummary', '')
            if summary:
                first_sentence = summary.split('.')[0]
                intel['business'] = first_sentence[:120]

            # Analyst target
            target = info.get('targetMeanPrice')
            if target:
                intel['target_price'] = round(target, 2)
                current = info.get('currentPrice') or info.get('regularMarketPrice')
                if current and target:
                    intel['upside_pct'] = round((target - current) / current * 100, 1)

            # Recommendation
            rec = info.get('recommendationKey')
            if rec and rec != 'none':
                rec_map = {'strong_buy': 'קנייה חזקה', 'buy': 'קנייה', 'hold': 'החזקה',
                           'sell': 'מכירה', 'strong_sell': 'מכירה חזקה'}
                intel['recommendation'] = rec_map.get(rec, rec)

            intel['analyst_count'] = info.get('numberOfAnalystOpinions')

            # Earnings date
            try:
                cal = t.calendar
                if cal is not None and hasattr(cal, 'get') and cal.get('Earnings Date'):
                    ed = cal['Earnings Date']
                    if isinstance(ed, list) and ed:
                        intel['earnings_date'] = str(ed[0].date()) if hasattr(ed[0], 'date') else str(ed[0])
            except Exception:
                pass

        except Exception:
            pass
        return intel

    # Fetch for top tickers (max 8 — Render free plan friendly)
    intel_tickers = [t for t in unique if t in result][:8]
    if intel_tickers:
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = {pool.submit(_get_company_intel, t): t for t in intel_tickers}
            for future in concurrent.futures.as_completed(futures, timeout=10):
                t = futures[future]
                try:
                    intel = future.result(timeout=2)
                    if intel and t in result:
                        result[t].update(intel)
                except Exception:
                    pass

    return result


# ── 5. Sector News Headlines (yfinance ticker.news) ──────────────────────────

def _fetch_news_for_ticker(ticker: str, max_items: int = 3) -> List[dict]:
    """
    Fetch recent news for a single ticker via yfinance.
    Returns list of {title, source, ticker}.
    """
    import concurrent.futures
    try:
        def _inner():
            t = yf.Ticker(ticker)
            return t.news or []

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            raw = pool.submit(_inner).result(timeout=4)

        results = []
        from datetime import timezone
        now_utc = datetime.now(timezone.utc)
        for item in raw[:max_items * 2]:
            content = item.get('content', item)
            title = content.get('title', '') or content.get('headline', '')
            pub_date = content.get('pubDate', '')
            if pub_date:
                try:
                    from datetime import datetime as _dt
                    pd = _dt.fromisoformat(pub_date.replace('Z', '+00:00'))
                    age_hours = (now_utc - pd).total_seconds() / 3600
                    if age_hours > 24:
                        continue
                except Exception:
                    pass
            provider = content.get('provider', {})
            source = (provider.get('displayName', '') if isinstance(provider, dict)
                      else content.get('publisher', '') or content.get('source', ''))
            if title:
                results.append({
                    'title': title,
                    'source': source,
                    'ticker': ticker,
                    'pub_date': pub_date,
                })
            if len(results) >= max_items:
                break
        return results
    except Exception:
        return []


def _translate_titles(news_items: List[dict]) -> List[dict]:
    """Translate news titles from English to Hebrew using Google Translate."""
    if not news_items:
        return news_items
    try:
        from deep_translator import GoogleTranslator
        translator = GoogleTranslator(source='en', target='iw')
        titles = [n['title'] for n in news_items]
        translated = translator.translate_batch(titles)
        for i, t in enumerate(translated):
            if t:
                news_items[i]['title'] = t
    except Exception as e:
        print(f'[SectorBriefing] translation error: {e}')
    return news_items


def _fetch_sector_news(etf_tickers: List[str], extra_tickers: Dict[str, List[str]] = None) -> Dict[str, List[dict]]:
    """
    Fetch news for multiple sector ETFs + their top holdings + hot industry tickers.
    Returns {etf: [news items]} with Hebrew-translated titles.
    """
    extra_tickers = extra_tickers or {}
    result: Dict[str, List[dict]] = {}
    all_news: List[dict] = []

    for etf in etf_tickers:
        # Priority: hot industry tickers first, then ETF + holdings
        hot_tickers = extra_tickers.get(etf, [])
        tickers_to_check = hot_tickers + [etf] + ETF_TOP_HOLDINGS.get(etf, [])[:2]
        # Deduplicate while preserving order
        seen_t = set()
        unique_tickers = []
        for t in tickers_to_check:
            if t not in seen_t:
                seen_t.add(t)
                unique_tickers.append(t)

        etf_news: List[dict] = []

        for ticker in unique_tickers:
            if len(etf_news) >= 4:
                break
            items = _fetch_news_for_ticker(ticker, 2)
            etf_news.extend(items)

        seen = set()
        deduped = []
        for n in etf_news:
            if n['title'] not in seen:
                seen.add(n['title'])
                deduped.append(n)
        deduped = deduped[:4]
        result[etf] = deduped
        all_news.extend(deduped)

    _translate_titles(all_news)

    return result


# ── 6. Rotation Signal Computation ──────────────────────────────────────────────

def _compute_rotation(sectors: List[dict], multi_tf: Dict[str, dict]) -> dict:
    """
    Compute sector rotation signal by comparing growth vs defensive sectors.
    Returns rotation dict with signal, label, and spread metrics.
    """
    growth_1d = [s['change_pct'] for s in sectors if s['etf'] in GROWTH_ETFS]
    defense_1d = [s['change_pct'] for s in sectors if s['etf'] in DEFENSIVE_ETFS]
    cyclical_1d = [s['change_pct'] for s in sectors if s['etf'] in CYCLICAL_ETFS]

    g_avg = sum(growth_1d) / len(growth_1d) if growth_1d else 0
    d_avg = sum(defense_1d) / len(defense_1d) if defense_1d else 0
    c_avg = sum(cyclical_1d) / len(cyclical_1d) if cyclical_1d else 0

    diff = g_avg - d_avg

    if diff > 1.5:
        signal, label = 'risk_on', 'כסף זורם לצמיחה'
    elif diff > 0.5:
        signal, label = 'risk_on_mild', 'נטייה קלה לצמיחה'
    elif diff < -1.5:
        signal, label = 'risk_off', 'כסף זורם להגנה'
    elif diff < -0.5:
        signal, label = 'risk_off_mild', 'נטייה קלה להגנה'
    else:
        signal, label = 'neutral', 'שוק מאוזן'

    # Weekly rotation (if available)
    w_rotation = None
    if multi_tf:
        g_w = [multi_tf[etf]['w1'] for etf in GROWTH_ETFS if etf in multi_tf and multi_tf[etf].get('w1') is not None]
        d_w = [multi_tf[etf]['w1'] for etf in DEFENSIVE_ETFS if etf in multi_tf and multi_tf[etf].get('w1') is not None]
        if g_w and d_w:
            w_diff = sum(g_w) / len(g_w) - sum(d_w) / len(d_w)
            if w_diff > 2:
                w_rotation = 'risk_on'
            elif w_diff < -2:
                w_rotation = 'risk_off'
            else:
                w_rotation = 'neutral'

    return {
        'signal': signal,
        'label': label,
        'growth_avg': round(g_avg, 2),
        'defensive_avg': round(d_avg, 2),
        'cyclical_avg': round(c_avg, 2),
        'spread': round(diff, 2),
        'weekly_signal': w_rotation,
    }


# ── 7. Momentum Score Computation ──────────────────────────────────────────────

def _compute_momentum_score(change_1d: float, tf_data: Optional[dict]) -> int:
    """
    Compute a composite momentum score (0-100) from multi-timeframe performance.
    Weights: 1D=40%, 1W=30%, 1M=20%, 3M=10%.
    """
    score = 0.0

    # 1D component: map -5..+5 to 0..40
    d1 = max(-5, min(5, change_1d))
    score += ((d1 + 5) / 10) * 40

    if tf_data:
        # 1W component: map -10..+10 to 0..30
        w1 = tf_data.get('w1')
        if w1 is not None:
            w1 = max(-10, min(10, w1))
            score += ((w1 + 10) / 20) * 30

        # 1M component: map -15..+15 to 0..20
        m1 = tf_data.get('m1')
        if m1 is not None:
            m1 = max(-15, min(15, m1))
            score += ((m1 + 15) / 30) * 20

        # 3M component: map -20..+20 to 0..10
        m3 = tf_data.get('m3')
        if m3 is not None:
            m3 = max(-20, min(20, m3))
            score += ((m3 + 20) / 40) * 10

    return min(100, max(0, int(round(score))))


# ── 8. Market Pulse Computation ─────────────────────────────────────────────────

def _compute_market_pulse(sectors: List[dict], spy_data: Optional[dict]) -> dict:
    """
    Compute market pulse summary from sector data.
    """
    up = sum(1 for s in sectors if s['change_pct'] > 0)
    down = sum(1 for s in sectors if s['change_pct'] < 0)
    flat = len(sectors) - up - down
    avg_chg = sum(s['change_pct'] for s in sectors) / len(sectors) if sectors else 0

    # Spread between best and worst sector
    if sectors:
        best = sectors[0]['change_pct'] if sectors else 0
        worst = sectors[-1]['change_pct'] if sectors else 0
        spread = best - worst
    else:
        spread = 0

    # Market regime
    if up >= 9:
        regime = 'strong_bull'
        regime_label = 'שוק חזק — רוב הסקטורים עולים'
    elif up >= 7:
        regime = 'bull'
        regime_label = 'שוק חיובי'
    elif down >= 9:
        regime = 'strong_bear'
        regime_label = 'שוק חלש — רוב הסקטורים יורדים'
    elif down >= 7:
        regime = 'bear'
        regime_label = 'שוק שלילי'
    elif spread > 3:
        regime = 'divergent'
        regime_label = 'שוק מפוצל — פער גדול בין סקטורים'
    else:
        regime = 'mixed'
        regime_label = 'שוק מעורב'

    pulse = {
        'up_sectors': up,
        'down_sectors': down,
        'flat_sectors': flat,
        'avg_change': round(avg_chg, 2),
        'spread': round(spread, 2),
        'regime': regime,
        'regime_label': regime_label,
    }

    if spy_data:
        pulse['spy'] = spy_data

    return pulse


# ── 9. Macro Indicators (VIX, Gold, Oil, Rates, USD) ────────────────────────────

def _fetch_macro_indicators() -> dict:
    """
    Fetch key macro indicators with price + 1D change.
    Returns dict with indicator data + VIX level interpretation + overall risk assessment.
    """
    tickers = list(MACRO_TICKERS.keys())
    indicators = []
    try:
        data = yf.download(
            tickers,
            period='5d',
            interval='1d',
            progress=False,
            timeout=20,
            auto_adjust=True,
            threads=False,  # sequential to avoid rate limits
        )
        close = data.get('Close', data) if hasattr(data, 'get') else data

        for t, meta in MACRO_TICKERS.items():
            try:
                prices = close[t].dropna()
                if len(prices) >= 2:
                    prev = float(prices.iloc[-2])
                    curr = float(prices.iloc[-1])
                    chg = (curr - prev) / prev * 100 if prev else 0.0

                    # 5-day change if available
                    w_chg = None
                    if len(prices) >= 5:
                        w_ref = float(prices.iloc[-5])
                        w_chg = round((curr - w_ref) / w_ref * 100, 2) if w_ref else None

                    entry = {
                        'ticker': t,
                        'name': meta['name'],
                        'label': meta['label'],
                        'icon': meta['icon'],
                        'type': meta['type'],
                        'price': round(curr, 2),
                        'change_pct': round(chg, 2),
                        'w1_change': w_chg,
                    }
                    indicators.append(entry)
            except Exception:
                pass

    except Exception as e:
        print(f"[SectorBriefing] macro indicators fetch error: {e}")

    # VIX level interpretation
    vix_data = next((i for i in indicators if i['ticker'] == '^VIX'), None)
    vix_level = None
    if vix_data:
        vix_price = vix_data['price']
        for threshold, name, key, desc in VIX_LEVELS:
            if vix_price >= threshold:
                vix_level = {
                    'level': key,
                    'name': name,
                    'description': desc,
                    'value': vix_price,
                }
                break

    # Overall risk assessment
    risk_signals = []
    if vix_data and vix_data['price'] >= 25:
        risk_signals.append('VIX גבוה')
    if vix_data and vix_data['change_pct'] > 10:
        risk_signals.append('VIX זינוק')

    gold = next((i for i in indicators if i['ticker'] == 'GC=F'), None)
    if gold and gold['change_pct'] > 2:
        risk_signals.append('זהב עולה (risk-off)')

    oil = next((i for i in indicators if i['ticker'] == 'CL=F'), None)
    if oil and abs(oil['change_pct']) > 3:
        risk_signals.append(f'נפט {"קופץ" if oil["change_pct"] > 0 else "צונח"}')

    rates = next((i for i in indicators if i['ticker'] == '^TNX'), None)
    if rates and abs(rates['change_pct']) > 3:
        risk_signals.append(f'תשואות {"זינוק" if rates["change_pct"] > 0 else "צניחה"}')

    if len(risk_signals) >= 3:
        risk_level = 'high'
        risk_label = 'סיכון גבוה — תנאי שוק קשים'
    elif len(risk_signals) >= 1:
        risk_level = 'elevated'
        risk_label = 'סיכון מוגבר — ' + ' + '.join(risk_signals[:2])
    else:
        risk_level = 'normal'
        risk_label = 'סביבה נורמלית'

    return {
        'indicators': indicators,
        'vix_level': vix_level,
        'risk': {
            'level': risk_level,
            'label': risk_label,
            'signals': risk_signals,
        },
    }


# ── 10. Sector Impact Analysis ──────────────────────────────────────────────────

def _compute_sector_impacts(macro_data: dict) -> Dict[str, List[dict]]:
    """
    Based on macro indicator moves, compute expected sector impacts.
    Returns {etf: [{indicator, impact, explanation}]}.
    """
    if not macro_data or not macro_data.get('indicators'):
        return {}

    indicator_changes = {i['ticker']: i['change_pct'] for i in macro_data['indicators']}
    impacts: Dict[str, List[dict]] = {}

    for ticker, threshold, etfs, impact, explanation in IMPACT_RULES:
        chg = indicator_changes.get(ticker)
        if chg is None:
            continue

        # Positive threshold = indicator must be UP by that much
        # Negative threshold = indicator must be DOWN by that much
        triggered = False
        if threshold > 0 and chg >= threshold:
            triggered = True
        elif threshold < 0 and chg <= threshold:
            triggered = True

        if triggered:
            for etf in etfs:
                if etf not in impacts:
                    impacts[etf] = []
                indicator_meta = MACRO_TICKERS.get(ticker, {})
                impacts[etf].append({
                    'indicator': indicator_meta.get('name', ticker),
                    'indicator_icon': indicator_meta.get('icon', ''),
                    'impact': impact,
                    'explanation': explanation,
                    'change_pct': round(chg, 2),
                })

    return impacts


# ── 10b. Geopolitical Event Scanner — detect macro events from news ────────────

_geo_cache: Optional[List[dict]] = None
_geo_cache_at: float = 0.0
_GEO_CACHE_TTL = 120  # 2 minutes

# RSS feeds to scan (free, no API key, fast updates)
_GEO_RSS_FEEDS = [
    ('google_energy', 'https://news.google.com/rss/search?q=oil+OR+gas+OR+LNG+OR+energy+attack+OR+strike+OR+war+OR+sanctions+OR+pipeline+OR+embargo&hl=en&gl=US&ceid=US:en'),
    ('google_geopolitical', 'https://news.google.com/rss/search?q=iran+OR+iraq+OR+saudi+OR+qatar+OR+russia+OR+ukraine+energy+OR+oil+OR+gas&hl=en&gl=US&ceid=US:en'),
    ('oilprice', 'https://oilprice.com/rss/main'),
    ('bbc_world', 'https://feeds.bbci.co.uk/news/world/rss.xml'),
]

# Keywords and their weights for event scoring
_GEO_KEYWORDS = {
    # War / military
    'attack': 8, 'strike': 8, 'missile': 9, 'bomb': 8, 'war': 9,
    'military': 6, 'invasion': 9, 'airstrike': 9, 'escalation': 7,
    'conflict': 6, 'troops': 5, 'naval': 6, 'blockade': 8,
    # Energy infrastructure
    'oil': 5, 'gas': 5, 'lng': 6, 'pipeline': 7, 'refinery': 7,
    'crude': 5, 'petroleum': 5, 'natural gas': 7, 'opec': 6,
    'infrastructure': 5, 'facility': 4, 'terminal': 5, 'tanker': 6,
    # Disruption
    'disruption': 7, 'outage': 7, 'shutdown': 7, 'halt': 6,
    'shortage': 7, 'supply': 5, 'embargo': 8, 'sanctions': 7,
    'cut': 4, 'suspend': 6, 'block': 5,
    # Locations (energy-critical)
    'hormuz': 9, 'strait': 7, 'qatar': 7, 'iran': 7, 'iraq': 6,
    'saudi': 7, 'russia': 6, 'ukraine': 6, 'libya': 6,
    'ras laffan': 10, 'kharg island': 9, 'basra': 7, 'aramco': 8,
    # Market impact
    'surge': 6, 'spike': 6, 'soar': 6, 'plunge': 6, 'crash': 6,
    'barrel': 5, 'futures': 5, 'price': 3,
}

# Map event themes to affected commodities and sectors
_EVENT_IMPACT_MAP = {
    'oil_supply': {
        'keywords': ['oil', 'crude', 'barrel', 'opec', 'aramco', 'refinery', 'petroleum'],
        'commodity': 'CL=F',
        'commodity_name': 'נפט',
        'sectors': ['XLE'],
        'stocks': ['OXY', 'DVN', 'MRO', 'FANG', 'PR', 'CTRA', 'SM', 'MTDR'],
    },
    'gas_supply': {
        'keywords': ['gas', 'lng', 'natural gas', 'ras laffan', 'pipeline', 'terminal'],
        'commodity': 'NG=F',
        'commodity_name': 'גז טבעי',
        'sectors': ['XLE', 'XLU'],
        'stocks': ['ANNA', 'AR', 'RRC', 'EQT', 'TELL', 'SWN', 'CNX', 'CHK', 'NEXT'],
    },
    'strait_hormuz': {
        'keywords': ['hormuz', 'strait', 'tanker', 'blockade', 'naval'],
        'commodity': 'CL=F',
        'commodity_name': 'נפט + שילוח',
        'sectors': ['XLE'],
        'stocks': ['STNG', 'TNK', 'FRO', 'INSW', 'DHT', 'OXY', 'DVN'],
    },
    'gold_safe_haven': {
        'keywords': ['war', 'conflict', 'escalation', 'invasion', 'missile'],
        'commodity': 'GC=F',
        'commodity_name': 'זהב',
        'sectors': ['XLB'],
        'stocks': ['GLD', 'NEM', 'GOLD', 'AEM', 'KGC', 'AG'],
    },
    'defense': {
        'keywords': ['military', 'troops', 'airstrike', 'missile', 'defense'],
        'commodity': None,
        'commodity_name': 'ביטחון',
        'sectors': ['XLI'],
        'stocks': ['LMT', 'RTX', 'NOC', 'GD', 'BA', 'HII', 'KTOS'],
    },
}


def _scan_geopolitical_events() -> List[dict]:
    """
    Scan RSS feeds for geopolitical events that could move energy/commodity markets.
    Returns list of detected events with impact analysis.
    """
    import feedparser
    from datetime import timezone, timedelta

    now_utc = datetime.now(timezone.utc)
    all_articles = []

    for source_name, url in _GEO_RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:30]:
                title = entry.get('title', '')
                summary = entry.get('summary', entry.get('description', ''))
                pub = entry.get('published_parsed') or entry.get('updated_parsed')

                # Parse publication date
                pub_dt = None
                if pub:
                    try:
                        from calendar import timegm
                        pub_dt = datetime.fromtimestamp(timegm(pub), tz=timezone.utc)
                    except Exception:
                        pass

                # Only process articles from last 24 hours
                if pub_dt and (now_utc - pub_dt).total_seconds() > 86400:
                    continue

                # Score the article
                text = f'{title} {summary}'.lower()
                score = 0
                matched_keywords = []
                for kw, weight in _GEO_KEYWORDS.items():
                    if kw in text:
                        score += weight
                        matched_keywords.append(kw)

                # Only keep articles with significant geopolitical + energy relevance
                if score >= 15:
                    # Determine which event themes match
                    themes = []
                    for theme_key, theme_data in _EVENT_IMPACT_MAP.items():
                        theme_score = sum(1 for kw in theme_data['keywords'] if kw in text)
                        if theme_score >= 2:
                            themes.append(theme_key)

                    all_articles.append({
                        'title': title,
                        'source': source_name,
                        'pub_date': pub_dt.isoformat() if pub_dt else None,
                        'age_hours': round((now_utc - pub_dt).total_seconds() / 3600, 1) if pub_dt else None,
                        'score': score,
                        'keywords': matched_keywords[:8],
                        'themes': themes,
                    })
        except Exception as e:
            print(f'[GeoScanner] {source_name} error: {e}')

    # Sort by score (highest first), deduplicate by similar titles
    all_articles.sort(key=lambda x: x['score'], reverse=True)
    seen_titles = set()
    unique = []
    for a in all_articles:
        # Simple dedup: first 40 chars of title
        key = a['title'][:40].lower()
        if key not in seen_titles:
            seen_titles.add(key)
            unique.append(a)

    # Group into events and generate impact analysis
    events = []
    theme_scores: Dict[str, int] = {}
    theme_articles: Dict[str, list] = {}

    for article in unique[:20]:
        for theme in article.get('themes', []):
            theme_scores[theme] = theme_scores.get(theme, 0) + article['score']
            if theme not in theme_articles:
                theme_articles[theme] = []
            theme_articles[theme].append(article)

    # Generate event alerts for themes with multiple high-score articles
    for theme_key, total_score in sorted(theme_scores.items(), key=lambda x: -x[1]):
        articles = theme_articles[theme_key]
        if total_score < 20 or len(articles) < 1:
            continue

        theme_data = _EVENT_IMPACT_MAP[theme_key]
        confidence = 'High' if total_score >= 50 and len(articles) >= 3 else 'Medium' if total_score >= 30 else 'Low'

        # Best headline
        top_article = articles[0]

        events.append({
            'theme': theme_key,
            'headline': top_article['title'],
            'source': top_article['source'],
            'age_hours': top_article.get('age_hours'),
            'total_score': total_score,
            'article_count': len(articles),
            'confidence': confidence,
            'commodity': theme_data['commodity'],
            'commodity_name': theme_data['commodity_name'],
            'affected_sectors': theme_data['sectors'],
            'play_tickers': theme_data['stocks'],
            'keywords': list(set(kw for a in articles for kw in a.get('keywords', [])))[:10],
            'all_headlines': [a['title'] for a in articles[:5]],
        })

    # Translate headlines to Hebrew
    if events:
        try:
            from deep_translator import GoogleTranslator
            translator = GoogleTranslator(source='en', target='iw')
            headlines = [ev['headline'] for ev in events]
            translated = translator.translate_batch(headlines)
            for i, t in enumerate(translated):
                if t:
                    events[i]['headline_he'] = t

            # Also translate all_headlines
            for ev in events:
                originals = ev.get('all_headlines', [])
                if originals:
                    try:
                        tr = translator.translate_batch(originals[:3])
                        ev['all_headlines_he'] = [t or o for t, o in zip(tr, originals)]
                    except Exception:
                        pass
        except Exception as e:
            print(f'[GeoScanner] translation error: {e}')

    return events[:5]


async def _fetch_geo_events() -> List[dict]:
    """Async wrapper for geopolitical event scanning (runs in thread)."""
    global _geo_cache, _geo_cache_at
    now = _time.time()
    if _geo_cache is not None and (now - _geo_cache_at) < _GEO_CACHE_TTL:
        return _geo_cache
    try:
        events = await asyncio.to_thread(_scan_geopolitical_events)

        if events:
            print(f'[GeoScanner] Detected {len(events)} geopolitical events')

        _geo_cache = events
        _geo_cache_at = _time.time()
        return events
    except Exception as e:
        print(f'[GeoScanner] Error: {e}')
        return _geo_cache or []


# ── 11. Market-Wide News ─────────────────────────────────────────────────────────

def _fetch_market_news() -> List[dict]:
    """
    Fetch broad market-moving news from major ETFs (SPY, QQQ, DIA).
    Returns list of {title, source, ticker, pub_date} with Hebrew translation.
    """
    import concurrent.futures
    market_tickers = ['SPY', 'QQQ', 'DIA']
    all_news = []
    seen_titles = set()

    for ticker in market_tickers:
        items = _fetch_news_for_ticker(ticker, max_items=4)
        for item in items:
            # Deduplicate
            if item['title'] not in seen_titles:
                seen_titles.add(item['title'])
                all_news.append(item)

    # Sort by pub_date (newest first)
    def parse_date(n):
        try:
            from datetime import datetime as _dt
            return _dt.fromisoformat(n.get('pub_date', '').replace('Z', '+00:00'))
        except Exception:
            return datetime.min
    all_news.sort(key=parse_date, reverse=True)

    # Keep top 8
    all_news = all_news[:8]

    # Translate to Hebrew
    _translate_titles(all_news)

    return all_news


# ── 12. All-Sector Movers (single Finviz call) ─────────────────────────────────

async def _fetch_all_movers(session: aiohttp.ClientSession) -> Dict[str, dict]:
    """
    Fetch top movers across ALL sectors from Finviz:
    - v=111 (3 pages, 60 stocks) for sector, industry, company
    - v=141 (1 page, top 20) for ownership data (inst own, insider own, float short)
    Groups by sector + identifies hottest industry per sector.
    Flags institutional activity, insider buying, short squeeze potential.
    """
    import re as _re
    all_stocks = []

    # ── Phase 1: Overview data (v=111) — sector, industry, company ──────────
    for page_start in [1, 21, 41]:
        url = (
            f'https://finviz.com/screener.ashx?v=111'
            f'&f=sh_avgvol_o200'
            f'&o=-change&r={page_start}'
        )
        try:
            async with session.get(
                url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=12)
            ) as resp:
                if resp.status != 200:
                    print(f"[SectorBriefing] all-movers v111 page {page_start} HTTP {resp.status}")
                    break
                html = await resp.text()

            soup = BeautifulSoup(html, 'html.parser')

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
                for t in soup.find_all('table'):
                    hdr = t.find('tr')
                    if hdr and 'Ticker' in [c.get_text(strip=True) for c in hdr.find_all(['th', 'td'])]:
                        table = t
                        break
            if not table:
                break

            rows = table.find_all('tr')
            header_cells = rows[0].find_all(['th', 'td'])
            col = {c.get_text(strip=True): i for i, c in enumerate(header_cells)}

            def gcol(row_cells, name, default=''):
                i = col.get(name)
                return row_cells[i].get_text(strip=True) if i is not None and i < len(row_cells) else default

            for row in rows[1:]:
                cells = row.find_all('td')
                if not cells:
                    continue

                ticker = gcol(cells, 'Ticker')
                if not ticker or ticker.isdigit():
                    continue

                sector = gcol(cells, 'Sector')
                industry = gcol(cells, 'Industry')

                try:
                    chg = float(gcol(cells, 'Change', '0').replace('%', '').replace('+', ''))
                    price_str = gcol(cells, 'Price', '0').replace('$', '').replace(',', '')
                    price = float(price_str) if price_str else 0.0
                    vol_str = gcol(cells, 'Volume', '0').replace(',', '')
                    volume = int(vol_str) if vol_str.isdigit() else 0
                except Exception:
                    continue

                all_stocks.append({
                    'ticker':     ticker,
                    'company':    gcol(cells, 'Company'),
                    'sector':     sector,
                    'industry':   industry,
                    'change_pct': chg,
                    'price':      price,
                    'volume':     volume,
                    'market_cap': gcol(cells, 'Market Cap'),
                })

        except Exception as e:
            print(f"[SectorBriefing] all-movers v111 page {page_start} error: {e}")
            break

    # ── Phase 2: Ownership data (v=141) — inst own, insider, float short ────
    # Fetch top 2 pages (40 stocks) to match most of our v=111 results
    ownership_map: Dict[str, dict] = {}
    for page_start in [1, 21]:
        url = (
            f'https://finviz.com/screener.ashx?v=131'
            f'&f=sh_avgvol_o200'
            f'&o=-change&r={page_start}'
        )
        try:
            async with session.get(
                url, headers=_HEADERS, timeout=aiohttp.ClientTimeout(total=12)
            ) as resp:
                if resp.status != 200:
                    break
                html = await resp.text()

            soup = BeautifulSoup(html, 'html.parser')

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
                break

            rows = table.find_all('tr')
            header_cells = rows[0].find_all(['th', 'td'])
            col141 = {c.get_text(strip=True): i for i, c in enumerate(header_cells)}

            def gcol141(row_cells, name, default=''):
                i = col141.get(name)
                return row_cells[i].get_text(strip=True) if i is not None and i < len(row_cells) else default

            for row in rows[1:]:
                cells = row.find_all('td')
                if not cells:
                    continue
                ticker = gcol141(cells, 'Ticker')
                if not ticker or ticker.isdigit():
                    continue

                def parse_pct(val):
                    try:
                        return float(val.replace('%', '').replace(',', ''))
                    except (ValueError, AttributeError):
                        return None

                def parse_num(val):
                    try:
                        val = val.replace(',', '')
                        if val.endswith('B'):
                            return float(val[:-1]) * 1_000_000_000
                        if val.endswith('M'):
                            return float(val[:-1]) * 1_000_000
                        if val.endswith('K'):
                            return float(val[:-1]) * 1_000
                        return float(val) if val and val != '-' else None
                    except (ValueError, AttributeError):
                        return None

                ownership_map[ticker] = {
                    'inst_own':      parse_pct(gcol141(cells, 'Inst Own')),
                    'inst_trans':    parse_pct(gcol141(cells, 'Inst Trans')),
                    'insider_own':   parse_pct(gcol141(cells, 'Insider Own')),
                    'insider_trans': parse_pct(gcol141(cells, 'Insider Trans')),
                    'float_short':   parse_pct(gcol141(cells, 'Short Float')),
                    'short_ratio':   parse_pct(gcol141(cells, 'Short Ratio')),
                    'float_shares':  parse_num(gcol141(cells, 'Float')),
                    'avg_volume':    parse_num(gcol141(cells, 'Avg Volume')),
                }
                # Debug: print first match to verify parsing
                if len(ownership_map) == 1:
                    print(f'[SectorBriefing] ownership sample: {ticker} inst={ownership_map[ticker]["inst_own"]}% short={ownership_map[ticker]["float_short"]}%')

        except Exception as e:
            print(f"[SectorBriefing] ownership v141 page {page_start} error: {e}")
            break

    print(f'[SectorBriefing] ownership data for {len(ownership_map)} tickers')

    # ── Phase 3: Merge ownership into stocks + compute smart flags ──────────
    for stock in all_stocks:
        own = ownership_map.get(stock['ticker'], {})
        stock.update(own)

        # Smart flags
        flags = []

        # Institutional activity
        inst = own.get('inst_own')
        inst_tr = own.get('inst_trans')
        if inst is not None and inst >= 60:
            flags.append({'type': 'institutional', 'label': f'מוסדיים {inst:.0f}%', 'icon': '🏛️'})
        if inst_tr is not None and inst_tr > 5:
            flags.append({'type': 'inst_buying', 'label': f'מוסדיים קונים +{inst_tr:.0f}%', 'icon': '📈'})

        # Insider activity
        insider_tr = own.get('insider_trans')
        if insider_tr is not None and insider_tr > 1:
            flags.append({'type': 'insider_buying', 'label': f'מנהלים קונים +{insider_tr:.0f}%', 'icon': '👔'})

        # Short squeeze potential
        fs = own.get('float_short')
        if fs is not None and fs >= 20:
            flags.append({'type': 'high_short', 'label': f'שורט {fs:.0f}%', 'icon': '🩳'})
        elif fs is not None and fs >= 10:
            flags.append({'type': 'short', 'label': f'שורט {fs:.0f}%', 'icon': '🩳'})

        # Small float (potential for big moves)
        fl = own.get('float_shares')
        if fl is not None and fl < 20_000_000:
            flags.append({'type': 'small_float', 'label': 'Float קטן', 'icon': '💎'})

        stock['flags'] = flags

        # Move estimate
        estimate = _compute_move_estimate(stock)
        if estimate:
            stock['move_estimate'] = estimate

    # ── Phase 4: Mark standout stock per sector ──────────────────────────────
    # Score: |change| * max(rel_volume, 1) * small_cap_bonus
    for stock in all_stocks:
        chg = abs(stock.get('change_pct', 0) or 0)
        rvol = stock.get('rel_volume', 1) or 1
        price = stock.get('price', 0) or 0
        small_cap = 1.5 if price < 20 else 1.0
        stock['_standout_score'] = chg * min(rvol, 10) * small_cap

    # Group by sector → ETF key
    result: Dict[str, dict] = {}
    for etf_key in SECTOR_ETFS:
        result[etf_key] = {'movers': [], 'hot_industry': None}

    for stock in all_stocks:
        etf_key = FINVIZ_SECTOR_MAP.get(stock['sector'])
        if etf_key and etf_key in result:
            result[etf_key]['movers'].append(stock)

    # For each sector, find hottest industry
    for etf_key, data in result.items():
        movers = data['movers']
        if not movers:
            continue

        # Keep only top 5 movers per sector
        data['movers'] = movers[:5]

        # Mark standout (highest score in this sector)
        best = max(data['movers'], key=lambda s: s.get('_standout_score', 0))
        if best.get('_standout_score', 0) > 5:
            best['is_standout'] = True

        # Group by industry
        industry_map: Dict[str, List[dict]] = {}
        for m in movers:
            ind = m.get('industry', '')
            if ind:
                if ind not in industry_map:
                    industry_map[ind] = []
                industry_map[ind].append(m)

        if industry_map:
            # Score: count * avg_change — more stocks with higher change = hotter
            best_industry = None
            best_score = -999
            for ind_name, ind_stocks in industry_map.items():
                avg_chg = sum(s['change_pct'] for s in ind_stocks) / len(ind_stocks)
                score = len(ind_stocks) * avg_chg
                if score > best_score:
                    best_score = score
                    # Build detailed stock list (all stocks in this industry)
                    detailed = []
                    for s in sorted(ind_stocks, key=lambda x: abs(x.get('change_pct', 0)), reverse=True):
                        rvol = s.get('rel_volume') or s.get('avg_volume')
                        vol = s.get('volume', 0) or 0
                        avg_vol = s.get('avg_volume')
                        # Compute rel_volume if we have avg
                        rv = round(vol / avg_vol, 1) if avg_vol and avg_vol > 0 else s.get('rel_volume')
                        detailed.append({
                            'ticker':     s['ticker'],
                            'price':      s.get('price'),
                            'change_pct': s.get('change_pct'),
                            'volume':     vol,
                            'rel_volume': rv,
                            'market_cap': s.get('market_cap', ''),
                            'chg_30m':    s.get('chg_30m'),
                            'chg_4h':     s.get('chg_4h'),
                            'chg_1w':     s.get('chg_1w'),
                            'float_short': s.get('float_short'),
                            'is_standout': s.get('is_standout', False),
                        })

                    best_industry = {
                        'name': ind_name,
                        'count': len(ind_stocks),
                        'avg_change': round(avg_chg, 2),
                        'top_ticker': ind_stocks[0]['ticker'],
                        'tickers': [s['ticker'] for s in ind_stocks[:3]],
                        'stocks': detailed[:8],  # All stocks (up to 8)
                    }
            data['hot_industry'] = best_industry

    total = sum(len(d['movers']) for d in result.values())
    print(f'[SectorBriefing] all-movers: {total} stocks across {sum(1 for d in result.values() if d["movers"])} sectors')
    return result


# ── 12b. Multi-Timeframe Mover Enrichment ─────────────────────────────────────

def _fetch_multi_timeframe_movers(tickers: List[str]) -> Dict[str, dict]:
    """
    Fetch 30m, 4h, 1d, 1w changes for a list of tickers.
    Uses hourly bars (5d) for 4h/1d/1w, and 5m bars (1d) for 30m.
    Returns {ticker: {chg_30m, chg_4h, chg_1d, chg_1w}}.
    """
    if not tickers:
        return {}
    result: Dict[str, dict] = {}
    unique = list(dict.fromkeys(tickers))[:30]

    try:
        # Hourly bars for 4h, 1d, 1w
        hourly = yf.download(
            unique, period='5d', interval='1h',
            progress=False, timeout=12, auto_adjust=True, prepost=True
        )
        h_close = hourly.get('Close', hourly) if hasattr(hourly, 'get') else hourly

        for tk in unique:
            try:
                if len(unique) > 1:
                    prices = h_close[tk].dropna()
                else:
                    prices = h_close.dropna()
                if len(prices) < 2:
                    continue

                curr = float(prices.iloc[-1])
                entry = {}

                # 4h change (~4 bars back)
                if len(prices) >= 5:
                    ref = float(prices.iloc[-5])
                    entry['chg_4h'] = round((curr - ref) / ref * 100, 2) if ref else None

                # 1d change (~7 bars back for regular hours)
                if len(prices) >= 8:
                    ref = float(prices.iloc[-8])
                    entry['chg_1d'] = round((curr - ref) / ref * 100, 2) if ref else None

                # 1w change (all data = ~5 days)
                if len(prices) >= 20:
                    ref = float(prices.iloc[0])
                    entry['chg_1w'] = round((curr - ref) / ref * 100, 2) if ref else None

                result[tk] = entry
            except Exception:
                pass

        # 5m bars for 30min change
        try:
            intra = yf.download(
                unique[:15], period='1d', interval='5m',
                progress=False, timeout=8, auto_adjust=True, prepost=True
            )
            i_close = intra.get('Close', intra) if hasattr(intra, 'get') else intra

            for tk in unique[:15]:
                try:
                    if len(unique[:15]) > 1:
                        prices = i_close[tk].dropna()
                    else:
                        prices = i_close.dropna()
                    if len(prices) >= 7:
                        curr = float(prices.iloc[-1])
                        ref = float(prices.iloc[-7])  # 6 bars * 5m = 30m
                        if tk not in result:
                            result[tk] = {}
                        result[tk]['chg_30m'] = round((curr - ref) / ref * 100, 2) if ref else None
                except Exception:
                    pass
        except Exception as e:
            print(f'[SectorBriefing] 5m bars error: {e}')

    except Exception as e:
        print(f'[SectorBriefing] multi-TF mover error: {e}')

    return result


# ── 13. Move Estimate per Stock ────────────────────────────────────────────────

def _compute_move_estimate(stock: dict) -> dict:
    """
    Estimate potential move based on stock characteristics:
    - Short float → squeeze potential
    - Float size → move amplification
    - Volume vs average → momentum sustainability
    - Institutional activity → smart money conviction
    Returns {target_pct, timeframe, catalyst, confidence}.
    """
    chg = abs(stock.get('change_pct', 0) or 0)
    fs = stock.get('float_short') or 0
    fl = stock.get('float_shares')
    inst_tr = stock.get('inst_trans') or 0
    insider_tr = stock.get('insider_trans') or 0
    vol = stock.get('volume') or 0
    avg_vol = stock.get('avg_volume') or vol or 1
    vol_ratio = vol / avg_vol if avg_vol > 0 else 1

    # Base: continuation of current move
    base = chg * 0.4
    catalyst = 'מומנטום'
    timeframe = '1-2 ימים'
    conf = 'low'

    # Short squeeze scenario
    if fs >= 20 and vol_ratio >= 1.5:
        base += fs * 0.6
        catalyst = 'סקוויז פוטנציאלי'
        timeframe = '1-3 ימים'
        conf = 'high' if vol_ratio >= 2.5 else 'medium'
    elif fs >= 10 and vol_ratio >= 1.3:
        base += fs * 0.3
        catalyst = 'לחץ שורט'
        timeframe = '2-5 ימים'
        conf = 'medium'

    # Institutional accumulation
    if inst_tr is not None and inst_tr > 5:
        base += inst_tr * 0.4
        if catalyst == 'מומנטום':
            catalyst = 'צבירה מוסדית'
            timeframe = '1-2 שבועות'
            conf = 'medium'
        else:
            catalyst += ' + מוסדיים'
            conf = 'high'

    # Insider buying
    if insider_tr is not None and insider_tr > 3:
        base += 5
        if catalyst == 'מומנטום':
            catalyst = 'קניות מנהלים'
            timeframe = '1-3 שבועות'
            conf = 'medium'

    # Small float amplifier
    if fl is not None and fl < 10_000_000:
        base *= 1.6
        if 'Float קטן' not in catalyst:
            catalyst += ' + Float קטן'
    elif fl is not None and fl < 20_000_000:
        base *= 1.3

    # Volume confirmation
    if vol_ratio >= 3:
        base *= 1.3
        if conf == 'low':
            conf = 'medium'
    elif vol_ratio < 1.2 and conf != 'high':
        conf = 'low'

    # Cap at reasonable levels
    target = round(min(base, 80), 1)

    # Don't show tiny targets
    if target < 3:
        return None

    return {
        'target_pct': target,
        'timeframe': timeframe,
        'catalyst': catalyst,
        'confidence': conf,
    }


# ── 14. Smart Stock Intelligence (analyst targets, earnings, catalysts) ──────

def _generate_catalyst_analysis(stock: dict) -> List[str]:
    """
    Generate actionable catalyst hypotheses from stock data patterns.
    No API calls — pure data analysis.
    """
    chg = stock.get('change_pct', 0) or 0
    fs = stock.get('float_short') or 0
    fl = stock.get('float_shares')
    inst = stock.get('inst_own') or 0
    inst_tr = stock.get('inst_trans') or 0
    insider_tr = stock.get('insider_trans') or 0
    vol = stock.get('volume') or 0
    avg_vol = stock.get('avg_volume') or vol or 1
    vol_ratio = vol / avg_vol if avg_vol > 0 else 1

    catalysts = []

    # Short squeeze signal
    if fs >= 20 and vol_ratio >= 1.5 and chg > 5:
        catalysts.append(f'סקוויז שורט — {fs:.0f}% שורט × נפח {vol_ratio:.1f}x, שורטיסטים נלכדים')
    elif fs >= 15 and chg > 3:
        catalysts.append(f'לחץ שורט — {fs:.0f}% שורט נדחס, סיכוי לסקוויז')
    elif fs >= 10 and vol_ratio >= 2:
        catalysts.append(f'שורט פגיע — {fs:.0f}% שורט עם נפח חריג, מצב מתפוצץ')

    # Institutional activity
    if inst_tr > 10:
        catalysts.append(f'מוסדיים צוברים בעוצמה — +{inst_tr:.0f}% אחזקות ברבעון')
    elif inst_tr > 5:
        catalysts.append(f'צבירה מוסדית — +{inst_tr:.0f}% הגדלה ברבעון, כסף חכם נכנס')

    # Insider buying
    if insider_tr > 5:
        catalysts.append(f'מנהלים קונים בכוח — +{insider_tr:.0f}% הגדלה, יודעים משהו?')
    elif insider_tr > 2:
        catalysts.append(f'Insider buying — מנהלים שמים כסף מהכיס +{insider_tr:.0f}%')

    # Float analysis
    if fl is not None and fl < 5_000_000:
        catalysts.append(f'Float זעיר ({fl/1e6:.1f}M) — כל נפח מזיז חזק, עלייה מואצת')
    elif fl is not None and fl < 15_000_000:
        catalysts.append(f'Float קטן ({fl/1e6:.1f}M) — היצע מוגבל, תנועות חדות')

    # Volume anomaly
    if vol_ratio >= 5:
        catalysts.append(f'נפח פי {vol_ratio:.0f} מהממוצע — אירוע חריג בתוך המניה')
    elif vol_ratio >= 3:
        catalysts.append(f'נפח חריג ×{vol_ratio:.1f} — משהו קורה מאחורי הקלעים')

    # High institutional + big move = smart money
    if inst >= 70 and abs(chg) > 3:
        catalysts.append(f'{inst:.0f}% בעלות מוסדית — ענקים מזיזים את המניה')

    # Combination signals
    if fs >= 15 and inst_tr > 5:
        catalysts.append('קומבו נדיר: שורט גבוה + מוסדיים קונים = מלכודת שורט')
    if fs >= 10 and fl and fl < 20_000_000:
        catalysts.append('Float קטן + שורט = חבית דינמיט — פוטנציאל ריצה חדה')

    return catalysts


def _fetch_stock_intelligence(stocks: List[dict], max_stocks: int = 6) -> Dict[str, dict]:
    """
    Fetch analyst targets + earnings date for top interesting movers.
    Each call is wrapped in ThreadPoolExecutor with timeout.
    Returns {ticker: {target_price, target_low, target_high, analyst_count,
                      recommendation, earnings_date, catalysts}}.
    """
    import concurrent.futures

    # Score and rank
    def interest_score(s):
        score = abs(s.get('change_pct', 0))
        flags = s.get('flags', [])
        score += len(flags) * 5
        for f in flags:
            if f['type'] in ('inst_buying', 'high_short'):
                score += 10
            elif f['type'] in ('insider_buying', 'small_float'):
                score += 5
        return score

    ranked = sorted(stocks, key=interest_score, reverse=True)
    top_stocks = ranked[:max_stocks]

    def _get_intel(stock):
        ticker = stock['ticker']
        result = {
            'catalysts': _generate_catalyst_analysis(stock),
        }
        try:
            t = yf.Ticker(ticker)
            info = t.get_info() if hasattr(t, 'get_info') else t.info

            # Analyst targets
            target = info.get('targetMeanPrice')
            if target:
                result['target_price'] = round(target, 2)
                result['target_low'] = round(info.get('targetLowPrice', 0), 2) if info.get('targetLowPrice') else None
                result['target_high'] = round(info.get('targetHighPrice', 0), 2) if info.get('targetHighPrice') else None
                result['analyst_count'] = info.get('numberOfAnalystOpinions')

                # Upside/downside from current price
                current = stock.get('price', 0)
                if current and target:
                    result['upside_pct'] = round((target - current) / current * 100, 1)

            # Recommendation
            rec = info.get('recommendationKey')
            rec_map = {
                'strong_buy': 'קנייה חזקה',
                'buy': 'קנייה',
                'hold': 'החזקה',
                'sell': 'מכירה',
                'strong_sell': 'מכירה חזקה',
            }
            if rec and rec != 'none':
                result['recommendation'] = rec_map.get(rec, rec)

            # Earnings date
            try:
                cal = t.calendar
                if cal is not None:
                    if hasattr(cal, 'get') and cal.get('Earnings Date'):
                        ed = cal['Earnings Date']
                        if isinstance(ed, list) and ed:
                            result['earnings_date'] = str(ed[0].date()) if hasattr(ed[0], 'date') else str(ed[0])
                    elif hasattr(cal, 'columns') and 'Earnings Date' in cal.columns:
                        result['earnings_date'] = str(cal['Earnings Date'].iloc[0])
            except Exception:
                pass

        except Exception as e:
            # Catalysts still work even if yfinance fails
            pass

        return ticker, result

    intel_map: Dict[str, dict] = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(_get_intel, s): s['ticker'] for s in top_stocks}
        for future in concurrent.futures.as_completed(futures, timeout=12):
            try:
                ticker, intel = future.result(timeout=2)
                if intel:
                    intel_map[ticker] = intel
            except Exception:
                pass

    # Also add catalyst analysis for stocks that didn't get full enrichment
    for s in stocks:
        if s['ticker'] not in intel_map:
            cats = _generate_catalyst_analysis(s)
            if cats:
                intel_map[s['ticker']] = {'catalysts': cats}

    print(f'[SectorBriefing] intelligence: {len(intel_map)} stocks enriched, '
          f'{sum(1 for v in intel_map.values() if v.get("target_price"))} with analyst targets')
    return intel_map


# ── 15. Gold Signal Engine ─────────────────────────────────────────────────────

def _generate_gold_signals(
    all_movers: Dict[str, dict],
    insider_trades: List[dict],
    macro_data: dict,
    intel: Dict[str, dict],
) -> List[dict]:
    """
    Generate ranked, actionable signals from ALL data sources.
    No articles — short punchy Hebrew messages with clear action.
    Returns sorted list of {level, icon, message, ticker, action, source}.
    """
    signals = []

    # Build mover lookup for cross-referencing insider data
    mover_map: Dict[str, dict] = {}
    for etf_data in all_movers.values():
        for m in etf_data.get('movers', []):
            mover_map[m['ticker']] = m

    # Title significance ranking
    TITLE_WEIGHT = {
        'CEO': 5, 'CFO': 4, 'COO': 4, 'CTO': 3, 'President': 4,
        'Chairman': 4, 'Director': 2, 'VP': 2, 'EVP': 3, 'SVP': 3,
        'Gen Counsel': 2, 'CMO': 3, 'CIO': 3, 'CAO': 2,
    }

    def _title_weight(title_str: str) -> tuple:
        """Returns (weight, hebrew_title) for insider title."""
        if not title_str:
            return 1, 'מנהל'
        title_up = title_str.upper()
        for key, w in TITLE_WEIGHT.items():
            if key.upper() in title_up:
                return w, key
        if '10%' in title_str or 'Owner' in title_str:
            return 1, 'בעל שליטה'
        return 1, title_str[:15]

    def _insider_reason(tk: str, buys: list) -> str:
        """
        Cross-reference insider buy with market data to hypothesize WHY.
        Data sources: SEC Form 4 (verified) × Finviz (institutional) × yfinance (targets).
        """
        reasons = []
        stock_intel = intel.get(tk, {})
        mover_data = mover_map.get(tk, {})

        # Check if buying before earnings
        ed = stock_intel.get('earnings_date')
        if ed:
            from datetime import date, timedelta
            try:
                today = date.today()
                ed_date = date.fromisoformat(ed)
                days_to_earn = (ed_date - today).days
                if 0 <= days_to_earn <= 14:
                    reasons.append(f'קונה {days_to_earn} ימים לפני דוחות ({ed}) — יודע משהו?')
                elif days_to_earn < 0 and days_to_earn >= -3:
                    reasons.append('קנה ממש אחרי דוחות — כנראה תוצאות טובות צפויות')
            except (ValueError, TypeError):
                pass

        # Check analyst target vs purchase price
        target = stock_intel.get('target_price')
        upside = stock_intel.get('upside_pct')
        if target and upside and upside > 30:
            reasons.append(f'קונה מתחת ליעד אנליסטים ${target} ({upside:+.0f}% upside)')

        # Check short float — buying against shorts
        fs = mover_data.get('float_short') or 0
        if fs >= 15:
            reasons.append(f'קונה נגד {fs:.0f}% שורטיסטים — ביטחון שהשורטים טועים')
        elif fs >= 8:
            reasons.append(f'שורט {fs:.0f}% — הקנייה מאותתת שהמנהל לא מודאג')

        # Check institutional buying alongside
        inst_tr = mover_data.get('inst_trans') or 0
        if inst_tr > 5:
            reasons.append(f'גם מוסדיים צוברים +{inst_tr:.0f}% — קונסנזוס חכם')

        # Purchase significance vs market cap
        mcap_str = buys[0].get('market_cap_live', '')
        if mcap_str:
            try:
                if mcap_str.endswith('B'):
                    mcap_val = float(mcap_str[:-1]) * 1e9
                elif mcap_str.endswith('M'):
                    mcap_val = float(mcap_str[:-1]) * 1e6
                else:
                    mcap_val = None

                if mcap_val:
                    total_val = 0
                    for b in buys:
                        try:
                            v = b.get('value', '').replace('$', '').replace(',', '').replace('+', '')
                            total_val += int(v)
                        except (ValueError, TypeError):
                            pass
                    if total_val > 0:
                        pct_of_mcap = (total_val / mcap_val) * 100
                        if pct_of_mcap >= 1:
                            reasons.append(f'קנייה = {pct_of_mcap:.1f}% משווי החברה — חריג!')
                        elif pct_of_mcap >= 0.1:
                            reasons.append(f'קנייה = {pct_of_mcap:.2f}% משווי החברה')
            except (ValueError, TypeError):
                pass

        # Change since purchase
        chg = buys[0].get('change_pct')
        if chg is not None:
            if chg < -3:
                reasons.append(f'המניה ירדה {chg:.1f}% מאז — עדיין מחזיק, לא מודאג')
            elif chg > 5:
                reasons.append(f'כבר עלתה {chg:+.1f}% — הקנייה כבר מוכיחה את עצמה')

        if not reasons:
            # Fallback based on title
            weight, _ = _title_weight(buys[0].get('title', ''))
            if weight >= 4:
                reasons.append('מנהל בכיר שם כסף אישי — אמון גבוה בחברה')
            else:
                reasons.append('קנייה מכספי המנהל — חייב לדווח ל-SEC, אמין 100%')

        return ' | '.join(reasons[:3])

    # ── 1. Insider Trades Analysis ─────────────────────────────────────────
    ticker_buys: Dict[str, list] = {}
    for t in insider_trades:
        tk = t.get('ticker', '')
        if tk:
            if tk not in ticker_buys:
                ticker_buys[tk] = []
            ticker_buys[tk].append(t)

    for tk, buys in ticker_buys.items():
        total_val = 0
        for b in buys:
            try:
                v = b.get('value', '').replace('$', '').replace(',', '').replace('+', '')
                total_val += int(v)
            except (ValueError, TypeError):
                pass

        mcap = buys[0].get('market_cap_live', '')
        price = buys[0].get('current_price')
        price_str = f'${price:.2f}' if price else ''
        val_str = f'${total_val:,.0f}' if total_val else ''
        # Use the enriched 'why' from the trade (has full company intel)
        reason = buys[0].get('why', '')
        best_title_w, best_title = max((_title_weight(b.get('title', '')) for b in buys), key=lambda x: x[0])

        detail_line = reason or f'{mcap}'

        if len(buys) >= 2:
            titles = ', '.join(dict.fromkeys(_title_weight(b.get('title', ''))[1] for b in buys))
            signals.append({
                'level': 'gold',
                'icon': '🔥',
                'message': f'{len(buys)} מנהלים ({titles}) קנו {val_str} ב-{tk} {price_str}',
                'detail': detail_line,
                'ticker': tk,
                'action': 'Cluster Buy — כמה מנהלים קונים יחד = סיגנל חזק',
                'source': 'insider_cluster',
                'data_source': 'SEC Form 4 (דיווח חובה)',
            })
        elif total_val >= 500_000:
            insider_name = buys[0].get('insider', 'מנהל')[:25]
            signals.append({
                'level': 'gold',
                'icon': '👔',
                'message': f'{insider_name} ({best_title}) קנה {val_str} ב-{tk} {price_str}',
                'detail': detail_line,
                'ticker': tk,
                'action': f'{best_title} שם כסף רציני מהכיס — חובה לעקוב',
                'source': 'insider_big',
                'data_source': 'SEC Form 4 (דיווח חובה)',
            })
        elif total_val >= 100_000 and best_title_w >= 3:
            insider_name = buys[0].get('insider', 'מנהל')[:25]
            signals.append({
                'level': 'silver',
                'icon': '👔',
                'message': f'{insider_name} ({best_title}) קנה {val_str} ב-{tk} {price_str}',
                'detail': detail_line,
                'ticker': tk,
                'action': f'קנייה של {best_title} — שווה מעקב',
                'source': 'insider_mid',
                'data_source': 'SEC Form 4 (דיווח חובה)',
            })

    # ── 2. Squeeze Setups ──────────────────────────────────────────────────
    for etf_data in all_movers.values():
        for m in etf_data.get('movers', []):
            fs = m.get('float_short') or 0
            chg = m.get('change_pct', 0)
            vol = m.get('volume') or 0
            avg_vol = m.get('avg_volume') or vol or 1
            vr = vol / avg_vol if avg_vol > 0 else 1
            fl = m.get('float_shares')
            inst_tr = m.get('inst_trans') or 0

            if fs >= 20 and vr >= 2 and chg > 5:
                fl_str = f', Float {fl/1e6:.1f}M' if fl and fl < 30e6 else ''
                est = m.get('move_estimate', {})
                target = f' → יעד +{est["target_pct"]}%' if est.get('target_pct') else ''
                signals.append({
                    'level': 'gold',
                    'icon': '🩳💥',
                    'message': f'{m["ticker"]} סקוויז פעיל! שורט {fs:.0f}% × נפח {vr:.1f}x{fl_str}{target}',
                    'detail': m.get('industry'),
                    'ticker': m['ticker'],
                    'action': 'שורטיסטים נלכדים — מומנטום ממשיך',
                    'source': 'squeeze',
                    'data_source': 'FINRA Short Data + Finviz',
                })
            elif fs >= 15 and chg > 3 and vr >= 1.5:
                signals.append({
                    'level': 'silver',
                    'icon': '🩳',
                    'message': f'{m["ticker"]} לחץ שורט — {fs:.0f}% שורט, נפח {vr:.1f}x, עלייה {chg:+.1f}%',
                    'ticker': m['ticker'],
                    'action': 'פוטנציאל סקוויז אם הנפח ממשיך',
                    'source': 'short_pressure',
                    'data_source': 'FINRA Short Data',
                })

            if inst_tr > 8 and chg > 3:
                intel_data = intel.get(m['ticker'], {})
                target_str = f' | יעד ${intel_data["target_price"]}' if intel_data.get('target_price') else ''
                signals.append({
                    'level': 'silver',
                    'icon': '🏛️',
                    'message': f'מוסדיים צוברים {m["ticker"]} — +{inst_tr:.0f}% ברבעון{target_str}',
                    'ticker': m['ticker'],
                    'action': 'כסף חכם נכנס — מגמה מתמשכת',
                    'source': 'inst_acc',
                    'data_source': 'SEC 13F Filing',
                })

            if fl and fl < 10e6 and chg > 10 and vr >= 2:
                signals.append({
                    'level': 'silver',
                    'icon': '💎',
                    'message': f'{m["ticker"]} ריצת Float קטן — {fl/1e6:.1f}M מניות, {chg:+.1f}%, נפח ×{vr:.0f}',
                    'ticker': m['ticker'],
                    'action': 'Float קטן + נפח = תנועה חדה',
                    'source': 'float_run',
                    'data_source': 'Finviz Float Data',
                })

            insider_tr = m.get('insider_trans') or 0
            if insider_tr > 3 and fs >= 10:
                signals.append({
                    'level': 'gold',
                    'icon': '🎯',
                    'message': f'{m["ticker"]} — מנהלים קונים +{insider_tr:.0f}% בזמן ששורט {fs:.0f}%',
                    'ticker': m['ticker'],
                    'action': 'מנהלים נגד השורטיסטים — מלכודת',
                    'source': 'insider_vs_short',
                    'data_source': 'SEC Form 4 + FINRA',
                })

    # ── 3. Earnings plays ──────────────────────────────────────────────────
    from datetime import date
    today = str(date.today())
    for ticker, data in intel.items():
        ed = data.get('earnings_date')
        if not ed:
            continue
        target = data.get('target_price')
        upside = data.get('upside_pct')

        if ed == today:
            up_str = f' | יעד ${target} ({upside:+.0f}%)' if target and upside else ''
            signals.append({
                'level': 'gold',
                'icon': '📅🔥',
                'message': f'{ticker} מדווח דוחות היום!{up_str}',
                'ticker': ticker,
                'action': 'דוחות היום — תנועה חדה צפויה',
                'source': 'earnings_today',
            })

    # ── 4. Analyst targets with extreme upside ─────────────────────────────
    for ticker, data in intel.items():
        upside = data.get('upside_pct')
        target = data.get('target_price')
        rec = data.get('recommendation')
        count = data.get('analyst_count')
        if upside and target and count:
            if upside > 100 and count >= 2:
                signals.append({
                    'level': 'gold',
                    'icon': '🎯',
                    'message': f'{ticker} — {count} אנליסטים, יעד ${target} ({upside:+.0f}% upside!)',
                    'detail': f'המלצה: {rec}' if rec else None,
                    'ticker': ticker,
                    'action': 'פער ענק מיעד — שווה חקירה',
                    'source': 'analyst_extreme',
                })
            elif upside > 50 and count >= 3:
                signals.append({
                    'level': 'silver',
                    'icon': '📊',
                    'message': f'{ticker} — {count} אנליסטים, יעד ${target} ({upside:+.0f}%)',
                    'ticker': ticker,
                    'action': 'upside משמעותי לפי וול סטריט',
                    'source': 'analyst_upside',
                })

    # ── 5. Macro alerts ────────────────────────────────────────────────────
    if macro_data:
        vix = macro_data.get('vix_level', {})
        if vix.get('level') == 'extreme':
            signals.append({
                'level': 'gold', 'icon': '🚨',
                'message': f'VIX {vix.get("value", 0):.1f} — פאניקה בשוק!',
                'action': 'סיכון מקסימלי — הגנתיים בלבד',
                'source': 'vix_extreme',
            })
        elif vix.get('level') == 'high':
            signals.append({
                'level': 'silver', 'icon': '😰',
                'message': f'VIX {vix.get("value", 0):.1f} — פחד מוגבר',
                'action': 'תנודתיות גבוהה — זהירות',
                'source': 'vix_high',
            })

        for ind in macro_data.get('indicators', []):
            if ind['ticker'] == 'GC=F' and abs(ind.get('change_pct', 0)) > 2:
                d = 'עולה' if ind['change_pct'] > 0 else 'יורד'
                signals.append({
                    'level': 'silver', 'icon': '🥇',
                    'message': f'זהב {d} {abs(ind["change_pct"]):.1f}% — ${ind["price"]:.0f}',
                    'action': 'Risk-Off, מחפשים מקלט' if ind['change_pct'] > 0 else 'Risk-On, תיאבון לסיכון',
                    'source': 'gold_move',
                })
            if ind['ticker'] == 'CL=F' and abs(ind.get('change_pct', 0)) > 3:
                d = 'זינוק' if ind['change_pct'] > 0 else 'צניחה'
                signals.append({
                    'level': 'silver', 'icon': '🛢️',
                    'message': f'נפט {d} {abs(ind["change_pct"]):.1f}% — ${ind["price"]:.0f}',
                    'action': 'אנרגיה מושפעת ישירות',
                    'source': 'oil_move',
                })
            # Natural gas alerts
            if ind['ticker'] == 'NG=F' and abs(ind.get('change_pct', 0)) > 3:
                chg = ind['change_pct']
                lvl = 'gold' if abs(chg) > 8 else 'silver'
                d = 'זינוק' if chg > 0 else 'צניחה'
                signals.append({
                    'level': lvl, 'icon': '🔥',
                    'message': f'גז טבעי {d} {abs(chg):.1f}% — ${ind["price"]:.2f}',
                    'action': 'Small-cap אנרגיה/גז ירוצו — חפש ANNA, AR, RRC, EQT, TELL' if chg > 0 else 'מפיקי גז תחת לחץ',
                    'source': 'natgas_move',
                })
            # Oil big move (>5%) — escalate to gold
            if ind['ticker'] == 'CL=F' and abs(ind.get('change_pct', 0)) > 5:
                chg = ind['change_pct']
                signals.append({
                    'level': 'gold', 'icon': '🛢️🚨',
                    'message': f'נפט {abs(chg):.1f}% — מהלך חריג! גיאופוליטי?',
                    'action': 'חפש small-cap אנרגיה + הגנתיים. סקטור XLE ישפיע.',
                    'source': 'oil_spike',
                })

    # ── Sort & deduplicate ─────────────────────────────────────────────────
    level_order = {'gold': 0, 'silver': 1, 'bronze': 2}
    signals.sort(key=lambda x: level_order.get(x.get('level', 'bronze'), 2))

    seen = set()
    unique = []
    for s in signals:
        key = f'{s.get("ticker", "")}-{s.get("source", "")}'
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return unique[:20]


# ── 15b. Macro Event Plays — detect commodity/geopolitical-driven opportunities ─

# Maps macro indicator spikes to Finviz sector filters for finding small-cap beneficiaries
MACRO_PLAY_RULES = [
    # (macro_ticker, min_abs_chg, direction, finviz_sector, play_label, filters)
    ('NG=F',  3,  'up',   'sec_energy',           'גז טבעי',    {'cap_small': True, 'ta_change_u5': True}),
    ('NG=F',  3,  'up',   'sec_utilities',         'גז → חשמל',  {'cap_small': True, 'ta_change_u5': True}),
    ('CL=F',  3,  'up',   'sec_energy',           'נפט',         {'cap_small': True, 'ta_change_u5': True}),
    ('CL=F',  3,  'down', 'sec_consumercyclical',  'נפט יורד',   {'cap_small': True, 'ta_change_u': True}),
    ('GC=F',  2,  'up',   'sec_basicmaterials',    'זהב',        {'cap_small': True, 'ta_change_u5': True}),
    ('^VIX', 10,  'up',   'sec_consumerdefensive', 'פאניקה',     {'cap_midover': True}),
    ('^VIX', 10,  'up',   'sec_utilities',         'פאניקה',     {'cap_midover': True}),
]

_macro_plays_cache: Optional[List[dict]] = None
_macro_plays_cache_at: float = 0.0
_MACRO_PLAYS_TTL = 120  # 2 minutes


def _detect_macro_event_plays(
    macro_data: dict, all_movers: Dict[str, dict]
) -> List[dict]:
    """
    When macro indicators spike, find small-cap stocks in affected sectors
    that are already moving with unusual volume — these are the ANNA-type plays.
    Uses already-fetched all_movers data (no extra API calls).
    """
    global _macro_plays_cache, _macro_plays_cache_at

    now = _time.time()
    if _macro_plays_cache is not None and (now - _macro_plays_cache_at) < _MACRO_PLAYS_TTL:
        return _macro_plays_cache

    if not macro_data or not macro_data.get('indicators'):
        return []

    indicator_changes = {i['ticker']: i for i in macro_data['indicators']}
    plays: List[dict] = []

    for macro_tk, min_chg, direction, sector_filter, play_label, _ in MACRO_PLAY_RULES:
        ind = indicator_changes.get(macro_tk)
        if not ind:
            continue
        chg = ind.get('change_pct', 0)

        # Check if threshold triggered in correct direction
        triggered = False
        if direction == 'up' and chg >= min_chg:
            triggered = True
        elif direction == 'down' and chg <= -min_chg:
            triggered = True
        if not triggered:
            continue

        # Find matching sector in all_movers
        sector_etf = None
        for etf, info in SECTOR_ETFS.items():
            if info.get('finviz') == sector_filter:
                sector_etf = etf
                break
        if not sector_etf or sector_etf not in all_movers:
            continue

        movers = all_movers[sector_etf].get('movers', [])

        # Filter for stocks with strong momentum + volume
        for stock in movers:
            stock_chg = stock.get('change_pct', 0) or 0
            rvol = stock.get('rel_volume', 0) or 0
            price = stock.get('price', 0) or 0
            mcap = stock.get('market_cap', '')
            ticker = stock.get('ticker', '')

            # Must be moving significantly in the right direction
            if direction == 'up' and stock_chg < 3:
                continue
            if direction == 'down' and stock_chg > -3:
                continue

            # Prioritize: unusual volume + big move + small cap
            is_small_cap = any(x in str(mcap).lower() for x in ['m', 'micro']) if mcap else price < 20
            vol_score = min(rvol, 10)
            move_score = min(abs(stock_chg), 20)
            priority = vol_score * 2 + move_score + (5 if is_small_cap else 0)

            # Confidence based on signals alignment
            confidence = 'Medium'
            if rvol >= 3 and abs(stock_chg) >= 8 and is_small_cap:
                confidence = 'High'
            elif rvol >= 5 and abs(stock_chg) >= 15:
                confidence = 'High'
            elif rvol < 1.5 or abs(stock_chg) < 5:
                confidence = 'Low'

            plays.append({
                'ticker': ticker,
                'price': price,
                'change_pct': round(stock_chg, 2),
                'rel_volume': round(rvol, 1) if rvol else None,
                'market_cap': mcap,
                'macro_trigger': ind['name'],
                'macro_change': round(chg, 2),
                'macro_icon': ind.get('icon', ''),
                'play_label': play_label,
                'sector': SECTOR_ETFS.get(sector_etf, {}).get('name', ''),
                'confidence': confidence,
                'priority': priority,
                'why': (
                    f'{ind["name"]} {"עלה" if chg > 0 else "ירד"} {abs(chg):.1f}% → '
                    f'{ticker} {"+"+str(round(stock_chg,1)) if stock_chg>0 else round(stock_chg,1)}% '
                    f'עם נפח {"חריג x"+str(round(rvol,1)) if rvol and rvol>=2 else "רגיל"}'
                ),
            })

    # Sort by priority (highest first), deduplicate by ticker
    plays.sort(key=lambda x: x['priority'], reverse=True)
    seen_tickers = set()
    unique_plays = []
    for p in plays:
        if p['ticker'] not in seen_tickers:
            seen_tickers.add(p['ticker'])
            unique_plays.append(p)
    unique_plays = unique_plays[:10]

    _macro_plays_cache = unique_plays
    _macro_plays_cache_at = now
    return unique_plays


# ── 16. Smart Money Flow Analysis ──────────────────────────────────────────────

def _compute_money_flow(sectors: List[dict]) -> dict:
    """
    Compute Smart Money flow signals per sector using:
    - ETF volume ratio (institutional trading drives large ETF volume)
    - Price direction (accumulation = high vol + up, distribution = high vol + down)
    - Multi-timeframe consistency (same direction across timeframes = conviction)

    Returns {etf: {score, signal, label}} + summary.
    """
    flows: Dict[str, dict] = {}

    for s in sectors:
        etf = s['etf']
        chg = s.get('change_pct', 0) or 0
        vol_ratio = s.get('volume_ratio') or 1.0
        w1 = s.get('w1') or 0
        m1 = s.get('m1') or 0

        # Core flow: volume_ratio * direction-weighted change
        # Cap change at ±5 to prevent extreme outliers
        capped_chg = max(-5, min(5, chg))
        flow_score = vol_ratio * capped_chg

        # Conviction bonus: consistent direction across timeframes
        same_dir_w1 = (chg > 0 and w1 > 0) or (chg < 0 and w1 < 0)
        same_dir_m1 = (chg > 0 and m1 > 0) or (chg < 0 and m1 < 0)
        conviction = 0
        if same_dir_w1:
            conviction += 1
        if same_dir_m1:
            conviction += 1

        # Boost score with conviction (consistent trend = smart money, not noise)
        if conviction >= 2:
            flow_score *= 1.5
        elif conviction == 1:
            flow_score *= 1.2

        # Volume signal amplification
        if vol_ratio >= 2.0:
            flow_score *= 1.3  # unusually high volume = institutional activity

        # Classify
        if flow_score > 5:
            signal, label = 'strong_accumulation', 'הצטברות חזקה'
        elif flow_score > 2:
            signal, label = 'accumulation', 'הצטברות'
        elif flow_score > 0.5:
            signal, label = 'mild_accumulation', 'הצטברות קלה'
        elif flow_score < -5:
            signal, label = 'strong_distribution', 'חלוקה חזקה'
        elif flow_score < -2:
            signal, label = 'distribution', 'חלוקה'
        elif flow_score < -0.5:
            signal, label = 'mild_distribution', 'חלוקה קלה'
        else:
            signal, label = 'neutral', 'ניטרלי'

        flows[etf] = {
            'score': round(flow_score, 2),
            'signal': signal,
            'label': label,
            'conviction': conviction,
            'volume_signal': 'high' if vol_ratio >= 2.0 else 'elevated' if vol_ratio >= 1.3 else 'normal',
        }

    # Summary: top accumulators and distributors
    sorted_by_score = sorted(flows.items(), key=lambda x: x[1]['score'], reverse=True)
    top_accumulation = [
        {'etf': etf, **flow}
        for etf, flow in sorted_by_score[:3]
        if flow['score'] > 0.5
    ]
    top_distribution = [
        {'etf': etf, **flow}
        for etf, flow in sorted_by_score[-3:]
        if flow['score'] < -0.5
    ]
    top_distribution.reverse()  # most negative first

    return {
        'flows': flows,
        'top_accumulation': top_accumulation,
        'top_distribution': top_distribution,
    }


def _map_insiders_to_sectors(insider_trades: List[dict], all_movers: Dict[str, dict]) -> Dict[str, List[dict]]:
    """
    Map insider trades to sector ETFs using the all-movers data.
    Detects cluster buys (multiple insiders buying in same sector).
    Returns {etf: [insider trades in that sector]}.
    """
    # Build ticker→sector map from all_movers data
    ticker_to_sector: Dict[str, str] = {}
    for etf_key, data in all_movers.items():
        for m in data.get('movers', []):
            ticker_to_sector[m['ticker']] = etf_key

    # Map each insider trade to its sector
    sector_insiders: Dict[str, List[dict]] = {}
    for trade in insider_trades:
        etf = ticker_to_sector.get(trade['ticker'])
        if etf:
            if etf not in sector_insiders:
                sector_insiders[etf] = []
            sector_insiders[etf].append(trade)

    return sector_insiders


# ── On-Demand Per-Sector Movers ─────────────────────────────────────────────────

async def get_stocks_for_sector(finviz_filter: str) -> List[dict]:
    """
    Public function: fetch top movers for a specific sector (on-demand).
    Uses per-sector cache with 3-minute TTL.
    """
    global _per_sector_cache

    now = _time.time()
    cached = _per_sector_cache.get(finviz_filter)
    if cached and (now - cached['at']) < _PER_SECTOR_TTL:
        return cached['data']

    async with aiohttp.ClientSession() as session:
        stocks = await _fetch_sector_stocks(session, finviz_filter)

    _per_sector_cache[finviz_filter] = {'data': stocks, 'at': _time.time()}
    return stocks


# ── Main Entry Point ────────────────────────────────────────────────────────────

async def get_sector_briefing() -> dict:
    """
    Returns the full sector briefing dict with all intelligence data.
    Uses 8 separate caches with different TTLs.
    """
    global _etf_cache, _etf_cache_at
    global _drivers_cache, _drivers_cache_at
    global _multi_tf_cache, _multi_tf_cache_at
    global _sparkline_cache, _sparkline_cache_at
    global _stocks_cache, _stocks_cache_at, _stocks_sector
    global _insider_cache, _insider_cache_at
    global _news_cache, _news_cache_at
    global _macro_cache, _macro_cache_at
    global _market_news_cache, _market_news_cache_at
    global _all_movers_cache, _all_movers_cache_at
    global _intel_cache, _intel_cache_at

    now = _time.time()

    # ── 1a. ETF prices (30s TTL) ──────────────────────────────────────────────
    if _etf_cache is None or (now - _etf_cache_at) >= _ETF_CACHE_TTL:
        print('[SectorBriefing] Refreshing ETF prices...')
        try:
            sectors = await asyncio.wait_for(
                asyncio.to_thread(_fetch_etf_only),
                timeout=10,
            )
            if sectors:
                _etf_cache = sectors
                _etf_cache_at = _time.time()
        except (asyncio.TimeoutError, FuturesTimeout):
            print('[SectorBriefing] ETF-only fetch timeout')

    sectors = _etf_cache or []

    # ── Determine staleness ─────────────────────────────────────────────────
    drivers_stale = (now - _drivers_cache_at) >= _DRIVERS_CACHE_TTL
    multi_tf_stale = _multi_tf_cache is None or (now - _multi_tf_cache_at) >= _MULTI_TF_TTL
    sparkline_stale = _sparkline_cache is None or (now - _sparkline_cache_at) >= _SPARKLINE_TTL

    top_sector = sectors[0] if sectors else None
    top_filter = top_sector['finviz_filter'] if top_sector else ''
    stocks_stale = (
        _stocks_cache is None
        or (now - _stocks_cache_at) >= _STOCKS_CACHE_TTL
        or _stocks_sector != top_filter
    )
    insider_stale = _insider_cache is None or (now - _insider_cache_at) >= _INSIDER_CACHE_TTL
    news_stale = not _news_cache or (now - _news_cache_at) >= _NEWS_CACHE_TTL

    # ── Macro, market news, all-movers staleness ──────────────────────────────
    macro_stale = _macro_cache is None or (now - _macro_cache_at) >= _MACRO_TTL
    market_news_stale = _market_news_cache is None or (now - _market_news_cache_at) >= _MARKET_NEWS_TTL
    all_movers_stale = _all_movers_cache is None or (now - _all_movers_cache_at) >= _ALL_MOVERS_TTL

    # ── Launch independent fetches concurrently ───────────────────────────────
    drivers_task = None
    multi_tf_task = None
    sparkline_task = None
    stocks_task = None
    insider_task = None
    news_task = None
    macro_task = None
    market_news_task = None
    all_movers_task = None

    if drivers_stale:
        print('[SectorBriefing] Refreshing drivers...')
        drivers_task = asyncio.ensure_future(asyncio.wait_for(
            asyncio.to_thread(_fetch_drivers),
            timeout=20,
        ))

    if multi_tf_stale:
        print('[SectorBriefing] Refreshing multi-timeframe data...')
        multi_tf_task = asyncio.ensure_future(asyncio.wait_for(
            asyncio.to_thread(_fetch_multi_timeframe),
            timeout=20,
        ))

    if sparkline_stale:
        print('[SectorBriefing] Refreshing sparklines...')
        sparkline_task = asyncio.ensure_future(asyncio.wait_for(
            asyncio.to_thread(_fetch_sparklines),
            timeout=15,
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
        # Include hot_industry top tickers in news fetch for richer coverage
        extra_tickers = {}
        if _all_movers_cache:
            for etf_key, am in _all_movers_cache.items():
                hi = am.get('hot_industry')
                if hi and hi.get('top_ticker'):
                    extra_tickers[etf_key] = hi['tickers'][:2]

        top_etfs = [s['etf'] for s in sorted(sectors, key=lambda x: abs(x['change_pct']), reverse=True)[:5]]
        print(f'[SectorBriefing] Refreshing news for {top_etfs}...')
        news_task = asyncio.ensure_future(asyncio.wait_for(
            asyncio.to_thread(_fetch_sector_news, top_etfs, extra_tickers),
            timeout=25,
        ))

    if macro_stale:
        print('[SectorBriefing] Refreshing macro indicators...')
        macro_task = asyncio.ensure_future(asyncio.wait_for(
            asyncio.to_thread(_fetch_macro_indicators),
            timeout=25,
        ))

    if market_news_stale:
        print('[SectorBriefing] Refreshing market news...')
        market_news_task = asyncio.ensure_future(asyncio.wait_for(
            asyncio.to_thread(_fetch_market_news),
            timeout=25,
        ))

    if all_movers_stale:
        print('[SectorBriefing] Refreshing all-sector movers...')

        async def _do_all_movers():
            async with aiohttp.ClientSession() as session:
                return await _fetch_all_movers(session)

        all_movers_task = asyncio.ensure_future(asyncio.wait_for(_do_all_movers(), timeout=25))

    # ── Geopolitical event scanner (always runs, 2min cache) ─────────────────
    geo_task = asyncio.ensure_future(asyncio.wait_for(_fetch_geo_events(), timeout=15))

    # ── Await all tasks ────────────────────────────────────────────────────────
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

    if multi_tf_task is not None:
        try:
            new_mtf = await multi_tf_task
            if new_mtf:
                _multi_tf_cache = new_mtf
                _multi_tf_cache_at = _time.time()
        except (asyncio.TimeoutError, FuturesTimeout):
            print('[SectorBriefing] multi-tf fetch timeout')
        except Exception as e:
            print(f'[SectorBriefing] multi-tf fetch error: {e}')

    if sparkline_task is not None:
        try:
            new_spark = await sparkline_task
            if new_spark:
                _sparkline_cache = new_spark
                _sparkline_cache_at = _time.time()
        except (asyncio.TimeoutError, FuturesTimeout):
            print('[SectorBriefing] sparkline fetch timeout')
        except Exception as e:
            print(f'[SectorBriefing] sparkline fetch error: {e}')

    if stocks_task is not None:
        try:
            new_stocks = await stocks_task
            # Overlay live prices (pre/post/regular) on Finviz data
            if new_stocks:
                try:
                    stock_tickers = [s['ticker'] for s in new_stocks[:15]]
                    live = await asyncio.wait_for(
                        asyncio.to_thread(_fetch_live_prices_batch, stock_tickers),
                        timeout=15,
                    )
                    for s in new_stocks:
                        lp = live.get(s['ticker'])
                        if lp:
                            s['change_pct'] = lp['change_pct']
                            s['price'] = lp['price']
                            s['session'] = lp.get('session', '')
                except (asyncio.TimeoutError, FuturesTimeout):
                    pass
            _stocks_cache = new_stocks
            _stocks_cache_at = _time.time()
            _stocks_sector = top_filter
        except asyncio.TimeoutError:
            print('[SectorBriefing] sector stocks timeout')
        except Exception as e:
            print(f'[SectorBriefing] sector stocks error: {e}')

    if insider_task is not None:
        try:
            new_insider = await insider_task
            if new_insider is not None:
                insider_tickers = list(dict.fromkeys(t['ticker'] for t in new_insider))
                print(f'[SectorBriefing] Enriching {len(insider_tickers)} insider tickers...')
                try:
                    insider_enrichment = await asyncio.wait_for(
                        asyncio.to_thread(_fetch_insider_enrichment, insider_tickers),
                        timeout=12,
                    )
                    print(f'[SectorBriefing] Insider enrichment: {len(insider_enrichment)} tickers enriched')
                except (asyncio.TimeoutError, FuturesTimeout):
                    print('[SectorBriefing] Insider enrichment TIMEOUT')
                    insider_enrichment = {}

                # Fetch recent news for insider tickers (catalyst detection)
                try:
                    insider_news = await asyncio.wait_for(
                        asyncio.to_thread(_fetch_insider_news_batch, insider_tickers),
                        timeout=10,
                    )
                    print(f'[SectorBriefing] Insider news: {len(insider_news)} tickers with news')
                except (asyncio.TimeoutError, FuturesTimeout):
                    print('[SectorBriefing] Insider news TIMEOUT')
                    insider_news = {}

                for trade in new_insider:
                    enrich = insider_enrichment.get(trade['ticker'], {})
                    trade['change_pct'] = enrich.get('change_pct')
                    trade['current_price'] = enrich.get('price')
                    trade['market_cap_live'] = enrich.get('market_cap')
                    # Company intel for "why" analysis
                    trade['industry'] = enrich.get('industry', '')
                    trade['business'] = enrich.get('business', '')
                    trade['target_price'] = enrich.get('target_price')
                    trade['upside_pct'] = enrich.get('upside_pct')
                    trade['earnings_date'] = enrich.get('earnings_date')
                    trade['recommendation'] = enrich.get('recommendation')

                    # Classify news catalyst for this ticker
                    ticker_news = insider_news.get(trade['ticker'], [])
                    trade['_news_catalyst'] = _classify_news_catalyst(ticker_news)

                    # Generate 'why' reason using real catalysts + company intel
                    trade['why'] = _insider_why(trade)

                # Cluster buy grouping (fast, synchronous)
                _enrich_cluster_buys(new_insider)

                # Historical track record scoring (slow — fire and forget in background)
                async def _bg_score():
                    try:
                        async with aiohttp.ClientSession() as score_session:
                            await _enrich_insider_scores(score_session, new_insider)
                        print(f'[SectorBriefing] Insider scores enriched (background)')
                    except Exception as e:
                        print(f'[SectorBriefing] Insider score bg error: {e}')

                asyncio.ensure_future(_bg_score())

                _insider_cache = new_insider
                _insider_cache_at = _time.time()
        except asyncio.TimeoutError:
            print('[SectorBriefing] insider trades timeout')
        except Exception as e:
            print(f'[SectorBriefing] insider trades error: {e}')

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

    if macro_task is not None:
        try:
            new_macro = await macro_task
            if new_macro:
                _macro_cache = new_macro
                _macro_cache_at = _time.time()
        except (asyncio.TimeoutError, FuturesTimeout):
            print('[SectorBriefing] macro indicators timeout')
        except Exception as e:
            print(f'[SectorBriefing] macro indicators error: {e}')

    if market_news_task is not None:
        try:
            new_mnews = await market_news_task
            if new_mnews is not None:
                _market_news_cache = new_mnews
                _market_news_cache_at = _time.time()
        except (asyncio.TimeoutError, FuturesTimeout):
            print('[SectorBriefing] market news timeout')
        except Exception as e:
            print(f'[SectorBriefing] market news error: {e}')

    if all_movers_task is not None:
        try:
            new_am = await all_movers_task
            if new_am:
                _all_movers_cache = new_am
                _all_movers_cache_at = _time.time()
        except (asyncio.TimeoutError, FuturesTimeout):
            print('[SectorBriefing] all-movers timeout')
        except Exception as e:
            print(f'[SectorBriefing] all-movers error: {e}')

    # ── Await geopolitical events ─────────────────────────────────────────────
    geo_events = []
    try:
        geo_events = await geo_task or []
    except (asyncio.TimeoutError, FuturesTimeout):
        print('[SectorBriefing] geo events timeout')
        geo_events = _geo_cache or []
    except Exception as e:
        print(f'[SectorBriefing] geo events error: {e}')
        geo_events = _geo_cache or []

    # ── Fetch stock intelligence (after all_movers is resolved) ──────────────
    intel_stale = _intel_cache is None or (now - _intel_cache_at) >= _INTEL_TTL
    if intel_stale and _all_movers_cache:
        all_movers_list = []
        for data in _all_movers_cache.values():
            all_movers_list.extend(data.get('movers', []))
        if all_movers_list:
            print(f'[SectorBriefing] Fetching stock intelligence for {len(all_movers_list)} movers...')
            try:
                new_intel = await asyncio.wait_for(
                    asyncio.to_thread(_fetch_stock_intelligence, all_movers_list, 8),
                    timeout=25,
                )
                if new_intel is not None:
                    _intel_cache = new_intel
                    _intel_cache_at = _time.time()
            except (asyncio.TimeoutError, FuturesTimeout):
                print('[SectorBriefing] intelligence timeout')
            except Exception as e:
                print(f'[SectorBriefing] intelligence error: {e}')

    # Attach intelligence to stocks
    intel = _intel_cache or {}
    if intel and _all_movers_cache:
        for data in _all_movers_cache.values():
            for m in data.get('movers', []):
                stock_intel = intel.get(m['ticker'])
                if stock_intel:
                    m['intel'] = stock_intel

    # ── Compute sector impacts from macro data ──────────────────────────────────
    macro_data = _macro_cache or {}
    sector_impacts = _compute_sector_impacts(macro_data) if macro_data else {}

    # ── Merge all data into sectors ─────────────────────────────────────────────
    multi_tf = _multi_tf_cache or {}
    sparklines = _sparkline_cache or {}
    all_movers = _all_movers_cache or {}

    sectors_full = []
    for s in sectors:
        entry = dict(s)
        etf = entry['etf']

        # ETF top holdings (weight-based)
        holdings = ETF_TOP_HOLDINGS.get(etf, [])
        weights = []
        for h in holdings:
            h_chg = _drivers_cache.get(h)
            if h_chg is not None:
                weights.append({'ticker': h, 'change_pct': h_chg})
        weights.sort(key=lambda x: x['change_pct'], reverse=True)
        entry['holdings'] = weights  # renamed from 'drivers' — these are ETF weights

        # Actual top movers from Finviz (real market movers, not just ETF weights)
        am = all_movers.get(etf, {})
        entry['top_movers'] = am.get('movers', [])
        entry['hot_industry'] = am.get('hot_industry')

        # drivers = top_movers if available, fallback to holdings
        if entry['top_movers']:
            entry['drivers'] = [
                {'ticker': m['ticker'], 'change_pct': m['change_pct']}
                for m in entry['top_movers'][:3]
            ]
        else:
            entry['drivers'] = weights

        # Multi-timeframe
        tf = multi_tf.get(etf, {})
        entry['w1'] = tf.get('w1')
        entry['m1'] = tf.get('m1')
        entry['m3'] = tf.get('m3')
        entry['volume_ratio'] = tf.get('volume_ratio')

        # Sparkline
        entry['sparkline'] = sparklines.get(etf, [])

        # Momentum score
        entry['momentum_score'] = _compute_momentum_score(entry['change_pct'], tf)

        # News
        entry['news'] = _news_cache.get(etf, [])

        # Sector group classification
        if etf in GROWTH_ETFS:
            entry['group'] = 'growth'
        elif etf in DEFENSIVE_ETFS:
            entry['group'] = 'defensive'
        elif etf in CYCLICAL_ETFS:
            entry['group'] = 'cyclical'
        else:
            entry['group'] = 'other'

        # Macro-driven sector impacts
        entry['impacts'] = sector_impacts.get(etf, [])

        sectors_full.append(entry)

    sector_stocks = _stocks_cache or []
    insider_trades = _insider_cache or []

    # Add filing age (hours since filing) for freshness display
    from datetime import timezone
    now_utc = datetime.now(timezone.utc)
    for trade in insider_trades:
        try:
            filed = datetime.strptime(trade.get('date', ''), '%Y-%m-%d %H:%M:%S')
            filed = filed.replace(tzinfo=timezone.utc)
            age_hours = (now_utc - filed).total_seconds() / 3600
            trade['filing_age_hours'] = round(age_hours, 1)
        except (ValueError, TypeError):
            trade['filing_age_hours'] = None

    # SPY data
    spy_tf = multi_tf.get('SPY', {})
    spy_data = None
    if spy_tf:
        # Get SPY 1D change from the ETF fetch if available
        spy_1d = None
        if sectors:
            # SPY isn't in sectors list, compute from multi_tf
            spy_1d = spy_tf.get('w1', 0)  # will use dedicated field below
        spy_data = {
            'price': spy_tf.get('price'),
            'w1': spy_tf.get('w1'),
            'm1': spy_tf.get('m1'),
            'm3': spy_tf.get('m3'),
            'volume_ratio': spy_tf.get('volume_ratio'),
        }

    # Rotation signal
    rotation = _compute_rotation(sectors, multi_tf)

    # Market pulse
    pulse = _compute_market_pulse(sectors, spy_data)

    # Smart money flow analysis
    smart_money = _compute_money_flow(sectors_full)

    # Add money_flow to each sector entry
    for entry in sectors_full:
        flow = smart_money['flows'].get(entry['etf'])
        if flow:
            entry['money_flow'] = flow

    # Enrich hot_industry with "why" reason from geo events + macro
    if geo_events and all_movers:
        # Build lookup: which industries are affected by geo events
        geo_reasons: Dict[str, str] = {}  # {industry_keyword: reason}
        for ev in geo_events:
            theme = ev.get('theme', '')
            headline = ev.get('headline', '')
            conf = ev.get('confidence', '')
            commodity = ev.get('commodity_name', '')
            short_reason = headline[:80] if headline else ''

            # Map themes to industry keywords
            if theme in ('oil_supply', 'strait_hormuz'):
                for kw in ['Oil & Gas', 'Energy', 'Petroleum', 'Crude', 'Refin']:
                    geo_reasons[kw] = f'{commodity}: {short_reason}'
            elif theme == 'gas_supply':
                for kw in ['Gas', 'LNG', 'Natural Gas', 'Utilities']:
                    geo_reasons[kw] = f'{commodity}: {short_reason}'
            elif theme == 'gold_safe_haven':
                for kw in ['Gold', 'Silver', 'Mining', 'Metals']:
                    geo_reasons[kw] = f'{commodity}: {short_reason}'
            elif theme == 'defense':
                for kw in ['Aerospace', 'Defense']:
                    geo_reasons[kw] = f'ביטחון: {short_reason}'

        # Also add macro-driven reasons
        if macro_data:
            for ind in macro_data.get('indicators', []):
                chg = ind.get('change_pct', 0)
                name = ind.get('name', '')
                if name == 'נפט' and abs(chg) > 2:
                    d = 'עולה' if chg > 0 else 'יורד'
                    for kw in ['Oil & Gas', 'Energy']:
                        if kw not in geo_reasons:
                            geo_reasons[kw] = f'נפט {d} {abs(chg):.1f}%'
                if name == 'גז טבעי' and abs(chg) > 2:
                    d = 'עולה' if chg > 0 else 'יורד'
                    for kw in ['Gas', 'LNG', 'Natural Gas']:
                        if kw not in geo_reasons:
                            geo_reasons[kw] = f'גז טבעי {d} {abs(chg):.1f}%'

        # Attach reason to each sector's hot_industry
        for entry in sectors_full:
            hi = entry.get('top_movers_data', {}).get('hot_industry') if isinstance(entry.get('top_movers_data'), dict) else None
            # Access hot_industry from all_movers
            etf = entry.get('etf', '')
            am = all_movers.get(etf, {})
            hi = am.get('hot_industry')
            if hi and hi.get('name'):
                ind_name = hi['name']
                for kw, reason in geo_reasons.items():
                    if kw.lower() in ind_name.lower():
                        hi['reason'] = reason
                        break

    # Map insider trades to sectors for cluster buy detection
    sector_insiders = _map_insiders_to_sectors(insider_trades, all_movers)
    for entry in sectors_full:
        si = sector_insiders.get(entry['etf'], [])
        entry['sector_insider_count'] = len(si)
        entry['sector_insiders'] = si[:3]  # top 3 insider trades for this sector

    # Enrich geo events with live prices for play_tickers
    if geo_events:
        # Check if already enriched (from cache)
        needs_enrich = any(not ev.get('play_tickers_enriched') for ev in geo_events)
        if needs_enrich:
            try:
                all_geo_tickers = list(dict.fromkeys(
                    t for ev in geo_events for t in ev.get('play_tickers', [])
                ))[:20]
                if all_geo_tickers:
                    def _geo_batch():
                        # Split into two batches to avoid yfinance 15-ticker limit
                        r = _fetch_live_prices_batch(all_geo_tickers[:15])
                        if len(all_geo_tickers) > 15:
                            r2 = _fetch_live_prices_batch(all_geo_tickers[15:])
                            r.update(r2)
                        return r

                    geo_prices = await asyncio.wait_for(
                        asyncio.to_thread(_geo_batch),
                        timeout=15,
                    )
                    for ev in geo_events:
                        enriched = []
                        for tk in ev.get('play_tickers', []):
                            p = geo_prices.get(tk, {})
                            enriched.append({
                                'ticker': tk,
                                'change_pct': p.get('change_pct'),
                                'price': p.get('price'),
                            })
                        enriched.sort(key=lambda x: abs(x.get('change_pct') or 0), reverse=True)
                        ev['play_tickers_enriched'] = enriched
            except (asyncio.TimeoutError, FuturesTimeout, Exception):
                pass

    # Multi-TF enrichment for movers (skip on cold start, enrich on 2nd+ call)
    if all_movers:
        # Check if first mover already has TF data
        first_movers = next((d['movers'] for d in all_movers.values() if d.get('movers')), [])
        needs_tf = first_movers and first_movers[0].get('chg_4h') is None
        if needs_tf:
            try:
                all_tickers = []
                for etf_data in all_movers.values():
                    all_tickers.extend(m['ticker'] for m in etf_data.get('movers', []))
                if all_tickers:
                    tf_data = await asyncio.wait_for(
                        asyncio.to_thread(_fetch_multi_timeframe_movers, all_tickers[:30]),
                        timeout=15,
                    )
                    for etf_data in all_movers.values():
                        for m in etf_data.get('movers', []):
                            tf = tf_data.get(m['ticker'], {})
                            m['chg_30m'] = tf.get('chg_30m')
                            m['chg_4h']  = tf.get('chg_4h')
                            m['chg_1d']  = tf.get('chg_1d')
                            m['chg_1w']  = tf.get('chg_1w')
            except (asyncio.TimeoutError, FuturesTimeout, Exception):
                pass

    result = {
        'generated_at':    datetime.now().isoformat(),
        'sectors':         sectors_full,
        'top_sector':      sectors_full[0] if sectors_full else None,
        'sector_stocks':   sector_stocks,
        'insider_trades':  insider_trades,
        'rotation':        rotation,
        'market_pulse':    pulse,
        'macro':           macro_data,
        'market_news':     _market_news_cache or [],
        'gold_signals':    _generate_gold_signals(
            all_movers, insider_trades, macro_data,
            _intel_cache or {},
        ),
        'macro_event_plays': _detect_macro_event_plays(macro_data, all_movers),
        'geo_events':      geo_events,
        'smart_money':     {
            'top_accumulation': smart_money['top_accumulation'],
            'top_distribution': smart_money['top_distribution'],
        },
    }

    top_name = result['top_sector']['name'] if result['top_sector'] else 'none'
    vix_info = ''
    if macro_data and macro_data.get('vix_level'):
        vix_info = f', VIX={macro_data["vix_level"]["value"]:.1f}({macro_data["vix_level"]["name"]})'
    print(f'[SectorBriefing] Done — top: {top_name}, '
          f'stocks: {len(sector_stocks)}, insiders: {len(insider_trades)}, '
          f'rotation: {rotation["signal"]}{vix_info}')
    return result


def invalidate_cache() -> None:
    """Force-refresh next call — clears all caches."""
    global _etf_cache_at, _drivers_cache_at, _stocks_cache_at
    global _insider_cache_at, _news_cache_at
    global _multi_tf_cache_at, _sparkline_cache_at
    global _macro_cache_at, _market_news_cache_at
    global _all_movers_cache_at, _intel_cache_at
    _etf_cache_at = 0.0
    _drivers_cache_at = 0.0
    _stocks_cache_at = 0.0
    _insider_cache_at = 0.0
    _news_cache_at = 0.0
    _multi_tf_cache_at = 0.0
    _sparkline_cache_at = 0.0
    _macro_cache_at = 0.0
    _market_news_cache_at = 0.0
    _all_movers_cache_at = 0.0
    _intel_cache_at = 0.0
