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
    unique = list(dict.fromkeys(tickers))[:30]
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


def _fetch_sector_news(etf_tickers: List[str]) -> Dict[str, List[dict]]:
    """
    Fetch news for multiple sector ETFs + their top holdings.
    Returns {etf: [news items]} with Hebrew-translated titles.
    """
    result: Dict[str, List[dict]] = {}
    all_news: List[dict] = []

    for etf in etf_tickers:
        tickers_to_check = [etf] + ETF_TOP_HOLDINGS.get(etf, [])[:2]
        etf_news: List[dict] = []

        for ticker in tickers_to_check:
            if len(etf_news) >= 3:
                break
            items = _fetch_news_for_ticker(ticker, 2)
            etf_news.extend(items)

        seen = set()
        deduped = []
        for n in etf_news:
            if n['title'] not in seen:
                seen.add(n['title'])
                deduped.append(n)
        deduped = deduped[:3]
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

    # ── Launch independent fetches concurrently ───────────────────────────────
    drivers_task = None
    multi_tf_task = None
    sparkline_task = None
    stocks_task = None
    insider_task = None
    news_task = None

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
        top_etfs = [s['etf'] for s in sorted(sectors, key=lambda x: abs(x['change_pct']), reverse=True)[:5]]
        print(f'[SectorBriefing] Refreshing news for {top_etfs}...')
        news_task = asyncio.ensure_future(asyncio.wait_for(
            asyncio.to_thread(_fetch_sector_news, top_etfs),
            timeout=25,
        ))

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

    # ── Merge all data into sectors ─────────────────────────────────────────────
    multi_tf = _multi_tf_cache or {}
    sparklines = _sparkline_cache or {}

    sectors_full = []
    for s in sectors:
        entry = dict(s)
        etf = entry['etf']

        # Drivers
        holdings = ETF_TOP_HOLDINGS.get(etf, [])
        drivers = []
        for h in holdings:
            h_chg = _drivers_cache.get(h)
            if h_chg is not None:
                drivers.append({'ticker': h, 'change_pct': h_chg})
        drivers.sort(key=lambda x: x['change_pct'], reverse=True)
        entry['drivers'] = drivers

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

        sectors_full.append(entry)

    sector_stocks = _stocks_cache or []
    insider_trades = _insider_cache or []

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

    result = {
        'generated_at':    datetime.now().isoformat(),
        'sectors':         sectors_full,
        'top_sector':      sectors_full[0] if sectors_full else None,
        'sector_stocks':   sector_stocks,
        'insider_trades':  insider_trades,
        'rotation':        rotation,
        'market_pulse':    pulse,
    }

    top_name = result['top_sector']['name'] if result['top_sector'] else 'none'
    print(f'[SectorBriefing] Done — top: {top_name}, '
          f'stocks: {len(sector_stocks)}, insiders: {len(insider_trades)}, '
          f'rotation: {rotation["signal"]}')
    return result


def invalidate_cache() -> None:
    """Force-refresh next call — clears all caches."""
    global _etf_cache_at, _drivers_cache_at, _stocks_cache_at
    global _insider_cache_at, _news_cache_at
    global _multi_tf_cache_at, _sparkline_cache_at
    _etf_cache_at = 0.0
    _drivers_cache_at = 0.0
    _stocks_cache_at = 0.0
    _insider_cache_at = 0.0
    _news_cache_at = 0.0
    _multi_tf_cache_at = 0.0
    _sparkline_cache_at = 0.0
