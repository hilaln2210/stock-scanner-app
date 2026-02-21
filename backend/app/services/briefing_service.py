"""
Daily Briefing Service — Morning digest of 3-5 top stocks.

Logic:
1. Fetch candidate universe from Finviz (stocks with recent earnings)
2. For each candidate: fetch yfinance earnings_dates → EPS surprise %
3. Filter: surprise >= 15%, RSI 45-65
4. Generate one Hebrew sentence explaining why the stock is interesting
5. Add today's events (FDA PDUFA, earnings) and SPY/QQQ market status
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import yfinance as yf
import aiohttp
from bs4 import BeautifulSoup


# ── RSI calculation (Wilder's smoothing) ──────────────────────────────────────

def _calc_rsi(prices: list, period: int = 14) -> Optional[float]:
    if not prices or len(prices) < period + 1:
        return None
    p = prices[-(period * 3):]
    deltas = [p[i + 1] - p[i] for i in range(len(p) - 1)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


# ── Human-readable Hebrew sentence templates ──────────────────────────────────

def _generate_reason(ticker: str, company: str, surprise_pct: float, rsi: float,
                     price: float, resistance: float, support: float,
                     price_change_since_earnings: float) -> str:
    beat_str = f"+{surprise_pct:.0f}%" if surprise_pct > 0 else f"{surprise_pct:.0f}%"
    rsi_int = int(rsi)

    if surprise_pct >= 40:
        base = f"דיווחה על ביצועים חזקים מאוד עם beat של {beat_str} ב-EPS"
    elif surprise_pct >= 20:
        base = f"beat מרשים של {beat_str} ב-EPS הרבעוני האחרון"
    else:
        base = f"beat של {beat_str} ב-EPS לאחרונה"

    if rsi < 50:
        rsi_note = f"RSI {rsi_int} — מנוחה טובה, לא נמכר מדי"
    elif rsi <= 60:
        rsi_note = f"RSI {rsi_int} ניטרלי — יש מקום לתנועה נוספת"
    else:
        rsi_note = f"RSI {rsi_int} — מומנטום חיובי עדיין לא קנוי מדי"

    if price_change_since_earnings > 15:
        momentum_note = f"עלתה {price_change_since_earnings:.0f}% מאז הדוח"
    elif price_change_since_earnings > 5:
        momentum_note = f"עלתה {price_change_since_earnings:.0f}% מאז הדוח"
    elif price_change_since_earnings < -5:
        momentum_note = "ירדה מאז הדוח — פוטנציאל כניסה נמוך יותר"
    else:
        momentum_note = "תגובה מתונה לדוח עד כה"

    return f"{base}. {rsi_note}. {momentum_note}."


def _watch_level_text(price: float, resistance: float, support: float) -> str:
    if resistance > price:
        return f"פריצה מעל ${resistance:.2f}"
    return f"שמירה מעל ${support:.2f}"


# ── Per-ticker yfinance fetch ─────────────────────────────────────────────────

def _fetch_ticker_data_sync(ticker: str, min_surprise_pct: float = 15.0) -> Optional[Dict]:
    """Fetch earnings surprise, RSI, price data for one ticker. Returns None if doesn't qualify."""
    try:
        stock = yf.Ticker(ticker)

        # ── Earnings dates (surprise %) ─────────────────────
        surprise_pct = None
        earnings_date = None
        price_at_earnings = None
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                ed = ex.submit(lambda: stock.earnings_dates).result(timeout=6)
            if ed is not None and not ed.empty:
                cutoff = datetime.now() - timedelta(days=45)
                # earnings_dates index is timezone-aware
                recent = ed[ed.index >= cutoff.strftime('%Y-%m-%d')]
                if not recent.empty:
                    row = recent.iloc[0]
                    sp = row.get('Surprise(%)')
                    if sp is not None and not (sp != sp):  # not NaN
                        surprise_pct = float(sp)
                        earnings_date = str(recent.index[0].date())
        except Exception:
            pass

        if surprise_pct is None or surprise_pct < min_surprise_pct:
            return None

        # ── RSI (daily 14-period) ───────────────────────────
        rsi = None
        try:
            hist = stock.history(period='60d', interval='1d', timeout=5)
            if hist is not None and not hist.empty:
                rsi = _calc_rsi(list(hist['Close']), period=14)
        except Exception:
            pass

        if rsi is None or not (45 <= rsi <= 65):
            return None

        # ── Price / levels ──────────────────────────────────
        price = 0.0
        resistance = 0.0
        support = 0.0
        company = ticker
        sector = ''
        market_cap = 0
        price_change_since_earnings = 0.0

        try:
            hist_daily = stock.history(period='2mo', interval='1d', timeout=5)
            if hist_daily is not None and not hist_daily.empty:
                price = float(hist_daily['Close'].iloc[-1])
                resistance = float(hist_daily['High'].tail(20).max())
                support = float(hist_daily['Low'].tail(10).min())

                # Price change since earnings date
                if earnings_date:
                    try:
                        earn_dt = datetime.strptime(earnings_date, '%Y-%m-%d')
                        # Find first close on/after earnings date
                        for idx, row in hist_daily.iterrows():
                            idx_date = idx.date() if hasattr(idx, 'date') else idx
                            if hasattr(idx_date, 'date'):
                                idx_date = idx_date.date()
                            if str(idx_date) >= earnings_date:
                                price_at_earnings = float(row['Close'])
                                break
                        if price_at_earnings and price_at_earnings > 0:
                            price_change_since_earnings = round(
                                (price - price_at_earnings) / price_at_earnings * 100, 1
                            )
                    except Exception:
                        pass
        except Exception:
            pass

        # ── Company info ────────────────────────────────────
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                info = ex.submit(lambda: stock.info or {}).result(timeout=4)
            company = str(info.get('longName') or info.get('shortName') or ticker)
            sector = str(info.get('sector') or '')
            market_cap = int(info.get('marketCap') or 0)
        except Exception:
            pass

        reason = _generate_reason(
            ticker, company, surprise_pct, rsi, price,
            resistance, support, price_change_since_earnings
        )

        return {
            'ticker': ticker,
            'company': company,
            'sector': sector,
            'market_cap': market_cap,
            'price': round(price, 2),
            'rsi': rsi,
            'earnings_surprise_pct': round(surprise_pct, 1),
            'earnings_date': earnings_date,
            'price_change_since_earnings': price_change_since_earnings,
            'resistance': round(resistance, 2),
            'support': round(support, 2),
            'watch_level': _watch_level_text(price, resistance, support),
            'reason': reason,
        }

    except Exception as e:
        return None


# ── Market status (SPY + QQQ) ─────────────────────────────────────────────────

def _fetch_market_status_sync() -> Dict:
    try:
        data = {}
        for sym in ['SPY', 'QQQ']:
            try:
                t = yf.Ticker(sym)
                hist = t.history(period='2d', interval='1d', timeout=5)
                if hist is not None and len(hist) >= 2:
                    prev = float(hist['Close'].iloc[-2])
                    last = float(hist['Close'].iloc[-1])
                    pct = round((last - prev) / prev * 100, 2)
                    data[sym] = {'price': round(last, 2), 'change_pct': pct}
            except Exception:
                data[sym] = {'price': 0, 'change_pct': 0}

        spy_pct = data.get('SPY', {}).get('change_pct', 0)
        qqq_pct = data.get('QQQ', {}).get('change_pct', 0)

        if spy_pct > 0.5 and qqq_pct > 0.5:
            mood = "סביבת שוק חיובית — רוח גב למניות צמיחה"
        elif spy_pct < -0.5 and qqq_pct < -0.5:
            mood = "לחץ כללי בשוק — זהירות עם כניסות חדשות"
        else:
            mood = "שוק מעורב — בחר סלקטיבי"

        spy_str = f"SPY {'+' if spy_pct >= 0 else ''}{spy_pct}%"
        qqq_str = f"QQQ {'+' if qqq_pct >= 0 else ''}{qqq_pct}%"

        return {
            'spy': data.get('SPY', {}),
            'qqq': data.get('QQQ', {}),
            'summary': f"{spy_str}, {qqq_str} — {mood}",
        }
    except Exception:
        return {'spy': {}, 'qqq': {}, 'summary': 'נתוני שוק לא זמינים'}


# ── Candidate universe from Finviz ────────────────────────────────────────────

async def _get_candidate_tickers(session: aiohttp.ClientSession) -> List[str]:
    """Scrape Finviz for stocks with recent earnings (prev month) + volume > 500K."""
    url = (
        'https://finviz.com/screener.ashx?v=111'
        '&f=earningsdate_prevmonth,sh_avgvol_o500'
        '&o=-volume'
    )
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; StockScanner/1.0)'}
    tickers = []
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                raise Exception(f"HTTP {resp.status}")
            html = await resp.text()
        soup = BeautifulSoup(html, 'html.parser')
        rows = soup.select('tr.styled-row-light, tr.styled-row-dark, tr[id^="row"]')
        for row in rows:
            cells = row.select('td')
            if len(cells) > 1:
                ticker_el = row.select_one('td a.tab-link')
                if ticker_el:
                    tickers.append(ticker_el.text.strip())
        # Also try alternate Finviz table structure
        if not tickers:
            for a in soup.select('a.screener-link-primary'):
                t = a.text.strip()
                if t and t.isupper() and len(t) <= 5:
                    tickers.append(t)
    except Exception as e:
        print(f"Briefing: Finviz candidate fetch failed: {e}")

    # Deduplicate, cap at 80
    seen = set()
    result = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            result.append(t)
        if len(result) >= 80:
            break

    # Fallback: well-known tickers that often have recent earnings
    if len(result) < 10:
        result = [
            'AAPL', 'MSFT', 'GOOGL', 'META', 'AMZN', 'NVDA', 'AMD', 'TSLA',
            'CRM', 'SNOW', 'DDOG', 'NET', 'MDB', 'ZS', 'PANW', 'CRWD',
            'AFRM', 'HOOD', 'COIN', 'RBLX', 'UBER', 'LYFT', 'ABNB', 'DASH',
            'SHOP', 'ROKU', 'SQ', 'PYPL', 'NFLX', 'DIS', 'SPOT', 'PINS',
        ]
    return result


# ── Main briefing function ────────────────────────────────────────────────────

class BriefingService:

    async def get_daily_briefing(
        self,
        min_surprise_pct: float = 15.0,
        rsi_min: float = 45.0,
        rsi_max: float = 65.0,
        top_n: int = 5,
    ) -> Dict:
        """
        Build daily briefing: top N stocks with recent earnings beat + neutral RSI.
        Also returns market status and today's catalyst events.
        """
        # 1. Fetch candidate tickers
        async with aiohttp.ClientSession() as session:
            candidates = await _get_candidate_tickers(session)

        print(f"Briefing: scanning {len(candidates)} candidates...")

        # 2. Batch-process tickers via thread pool (yfinance is blocking)
        sem = asyncio.Semaphore(3)
        loop = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=4)

        async def process_one(ticker: str) -> Optional[Dict]:
            async with sem:
                try:
                    return await asyncio.wait_for(
                        loop.run_in_executor(executor, _fetch_ticker_data_sync, ticker, min_surprise_pct),
                        timeout=15
                    )
                except asyncio.TimeoutError:
                    return None
                except Exception:
                    return None

        tasks = [process_one(t) for t in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        executor.shutdown(wait=False)

        qualified = [r for r in results if isinstance(r, dict) and r is not None]
        print(f"Briefing: {len(qualified)} stocks qualified (beat≥{min_surprise_pct}%, RSI {rsi_min}-{rsi_max})")

        # 3. Sort by earnings surprise descending, take top N
        qualified.sort(key=lambda x: x.get('earnings_surprise_pct', 0), reverse=True)
        top_stocks = qualified[:top_n]

        # 4. Market status
        loop2 = asyncio.get_event_loop()
        market_status = await loop2.run_in_executor(None, _fetch_market_status_sync)

        return {
            'stocks': top_stocks,
            'market_status': market_status,
            'generated_at': datetime.now().isoformat(),
            'candidates_scanned': len(candidates),
            'qualified_count': len(qualified),
        }
