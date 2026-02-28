"""
Daily Briefing Service — Morning digest of 3-5 top stocks.

Logic:
1. Fetch candidate universe from Finviz (stocks with recent earnings)
2. For each candidate: fetch yfinance earnings_dates → EPS surprise %
3. Filter: surprise >= 5%, RSI 35-85
4. Generate one Hebrew sentence explaining why the stock is interesting
5. Add today's events (FDA PDUFA, earnings) and SPY/QQQ market status
"""

import asyncio
import functools
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import yfinance as yf
import aiohttp
from bs4 import BeautifulSoup

from app.services.sec_filings import get_recent_8k_tickers, BEARISH_EXCLUDE_ITEMS, fetch_sec_highlights


# ── Translation helper ────────────────────────────────────────────────────────

_SEP = ' |||SEP||| '

def _translate_batch(texts: list[str]) -> list[str]:
    """Batch-translate a list of English strings to Hebrew in a single API call."""
    if not texts:
        return texts
    try:
        from deep_translator import GoogleTranslator
        combined = _SEP.join(t or '' for t in texts)
        result = GoogleTranslator(source='auto', target='iw').translate(combined)
        parts = (result or combined).split('|||SEP|||')
        # Align lengths (Google might collapse empties)
        translated = [p.strip() for p in parts]
        if len(translated) == len(texts):
            return translated
        # Fallback: return originals if split count mismatches
        return texts
    except Exception:
        return texts


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


# ── News type classifier (run on ENGLISH text, before translation) ────────────

def _classify_news_type(title: str, summary: str = '') -> str:
    text = (title + ' ' + summary).lower()
    if any(w in text for w in ['upgrades', 'upgrade to', 'raises target', 'raises price target',
                                'boosts target', 'initiates', 'overweight', 'outperform', 'strong buy']):
        return 'analyst_upgrade'
    if any(w in text for w in ['downgrades', 'downgrade to', 'lowers target', 'lowers price target',
                                'cuts target', 'underweight', 'underperform', 'reduces to']):
        return 'analyst_downgrade'
    if any(w in text for w in ['analyst', 'price target', 'pt ', 'rating', 'coverage', 'hold', 'neutral']):
        return 'analyst_note'
    if any(w in text for w in ['earnings', 'quarterly results', 'revenue', 'eps', 'beats estimates',
                                'misses estimates', 'beats expectations', 'q1 ', 'q2 ', 'q3 ', 'q4 ']):
        return 'earnings'
    if any(w in text for w in ['fda', 'approval', 'clinical trial', 'phase 3', 'phase 2', 'pdufa',
                                'nda', 'bla', 'inda', 'regulatory', 'drug', 'therapy']):
        return 'regulatory'
    if any(w in text for w in ['acquires', 'acquisition', 'merger', 'takeover', 'buyout', 'to buy ']):
        return 'ma'
    if any(w in text for w in ['partnership', 'agreement', 'deal', 'contract', 'collaboration', 'license']):
        return 'partnership'
    if any(w in text for w in ['buyback', 'repurchase', 'share repurchase', 'dividend', 'special dividend']):
        return 'capital'
    if any(w in text for w in ['guidance', 'outlook', 'raises guidance', 'lowers guidance', 'forecast']):
        return 'guidance'
    if any(w in text for w in ['lawsuit', 'investigation', 'sec ', 'ftc ', 'doj ', 'class action', 'probe', 'subpoena']):
        return 'legal'
    return 'general'


# ── ATR calculation ──────────────────────────────────────────────────────────

def _calc_atr(hist, period: int = 14) -> Optional[float]:
    """Average True Range % — measures daily volatility."""
    try:
        if hist is None or len(hist) < period + 2:
            return None
        highs = hist['High'].values
        lows = hist['Low'].values
        closes = hist['Close'].values
        trs = []
        for i in range(1, len(highs)):
            tr = max(highs[i] - lows[i],
                     abs(highs[i] - closes[i - 1]),
                     abs(lows[i] - closes[i - 1]))
            trs.append(tr)
        atr = sum(trs[-period:]) / period
        last_price = float(closes[-1])
        return round(atr / last_price * 100, 1) if last_price > 0 else None
    except Exception:
        return None


# ── Sector ETF helpers ────────────────────────────────────────────────────────

SECTOR_ETFS = {
    'XLK': 'טכנולוגיה',
    'XLV': 'בריאות',
    'XLF': 'פיננסים',
    'XLY': 'צריכה שיקולית',
    'XLP': 'צריכה בסיסית',
    'XLE': 'אנרגיה',
    'XLI': 'תעשייה',
    'XLC': 'תקשורת',
}


def _fetch_sector_etf_sync(sym: str) -> tuple:
    try:
        d = yf.Ticker(sym).history(period='5d', interval='1d', timeout=4)
        if d is not None and len(d) >= 2:
            prev = float(d['Close'].iloc[-2])
            last = float(d['Close'].iloc[-1])
            return (sym, round((last - prev) / prev * 100, 2))
    except Exception:
        pass
    return (sym, None)


def _get_qqq_20d_pct() -> float:
    """Fetch QQQ 20-day return for RS line calculation."""
    try:
        d = yf.Ticker('QQQ').history(period='25d', interval='1d', timeout=4)
        if d is not None and len(d) >= 20:
            return round(
                (float(d['Close'].iloc[-1]) - float(d['Close'].iloc[-20]))
                / float(d['Close'].iloc[-20]) * 100, 1
            )
    except Exception:
        pass
    return 0.0


# ── Wind Analysis (Tailwinds / Headwinds) ────────────────────────────────────

_SECTOR_TAILWINDS: Dict[str, List[str]] = {
    'Technology':              ['רוח גב מ-AI', 'צמיחת הוצאות ענן'],
    'Communication Services':  ['התאוששות שוק פרסום', 'צמיחת סטרימינג'],
    'Consumer Defensive':      ['כוח תמחור', 'חוסן הצרכן'],
    'Consumer Discretionary':  ['התאוששות בצריכה'],
    'Healthcare':              ['מגמה דמוגרפית', 'פייפליין חדשנות'],
    'Financials':              ['סביבת ריבית תומכת', 'פעילות שוק ההון'],
    'Energy':                  ['משמעת היצע', 'ביקוש אנרגיה'],
    'Industrials':             ['מגמת reshoring', 'הוצאות תשתיות'],
    'Basic Materials':         ['מחזור סחורות'],
    'Real Estate':             ['מחסור בהיצע'],
    'Utilities':               ['ציפיות להורדת ריבית'],
}

_SECTOR_HEADWINDS: Dict[str, List[str]] = {
    'Technology':              ['סיכון רגולציה', 'תחרות AI גוברת'],
    'Communication Services':  ['האטה בהוצאות פרסום'],
    'Consumer Discretionary':  ['ריבית גבוהה', 'לחץ חוב הצרכן'],
    'Healthcare':              ['לחץ על מחירי תרופות', 'סיכון FDA'],
    'Financials':              ['חשש לאיכות אשראי'],
    'Energy':                  ['אי-ודאות ביקוש', 'מעבר לאנרגיה נקייה'],
    'Real Estate':             ['ריבית גבוהה', 'לחץ על cap rate'],
    'Industrials':             ['חשש ממכסים'],
    'Basic Materials':         ['האטת ביקוש סין'],
}


def _generate_wind(sector: str, surprise_pct: float, price_change: float,
                   rsi: float, reported_eps: Optional[float] = None) -> Dict:
    """Generate tailwind / headwind labels for a stock based on sector + metrics."""
    tailwinds: List[str] = []
    headwinds: List[str] = []

    # Sector-level
    for tw in _SECTOR_TAILWINDS.get(sector, [])[:1]:
        tailwinds.append(tw)
    for hw in _SECTOR_HEADWINDS.get(sector, [])[:1]:
        headwinds.append(hw)

    # Earnings beat quality
    if surprise_pct >= 40:
        tailwinds.append('beat ענק על הדוח')
    elif surprise_pct >= 20:
        tailwinds.append('beat חזק על הדוח')

    # Post-earnings price action
    if price_change > 10:
        tailwinds.append('מומנטום פוסט-דוח')
    elif price_change < -10:
        headwinds.append('ירידה פוסט-דוח')

    # RSI
    if rsi < 42:
        tailwinds.append('מנוחה טכנית — יש מקום')
    elif rsi > 68:
        headwinds.append('קנוי מדי — זהירות')

    # Negative EPS
    if reported_eps is not None and reported_eps < 0:
        headwinds.append('EPS שלילי')

    return {
        'tailwinds': tailwinds[:3],
        'headwinds': headwinds[:2],
    }


# ── Human-readable Hebrew sentence templates ──────────────────────────────────

def _generate_reason(ticker: str, company: str, surprise_pct: Optional[float], rsi: float,
                     price: float, resistance: float, support: float,
                     price_change_since_earnings: float) -> str:
    rsi_int = int(rsi)

    # Base — earnings beat or technical setup
    if surprise_pct and surprise_pct >= 40:
        beat_str = f"+{surprise_pct:.0f}%"
        base = f"דיווחה על ביצועים חזקים מאוד עם beat של {beat_str} ב-EPS"
    elif surprise_pct and surprise_pct >= 20:
        beat_str = f"+{surprise_pct:.0f}%"
        base = f"beat מרשים של {beat_str} ב-EPS הרבעוני האחרון"
    elif surprise_pct and surprise_pct > 0:
        beat_str = f"+{surprise_pct:.0f}%"
        base = f"beat של {beat_str} ב-EPS לאחרונה"
    elif surprise_pct and surprise_pct < 0:
        base = f"miss של {surprise_pct:.0f}% ב-EPS — יש ללמוד ממה שהוביל לכך"
    else:
        # No recent earnings — describe technical posture
        if rsi < 40:
            base = "מניה בתיקון — RSI נמוך, פוטנציאל ריבאונד"
        elif rsi > 65:
            base = "מומנטום טכני חיובי — RSI גבוה, מגמה חיובית"
        else:
            base = "מניה עם סטאפ טכני נקי — RSI ניטרלי, מחכה לקטליסט"

    # RSI note
    if rsi < 40:
        rsi_note = f"RSI {rsi_int} — אזור מכירת יתר, סיכוי לריבאונד"
    elif rsi < 50:
        rsi_note = f"RSI {rsi_int} — מנוחה טובה, לא נמכר מדי"
    elif rsi <= 65:
        rsi_note = f"RSI {rsi_int} ניטרלי — יש מקום לתנועה נוספת"
    elif rsi <= 75:
        rsi_note = f"RSI {rsi_int} — מומנטום חיובי, עדיין לא קנוי מדי"
    else:
        rsi_note = f"RSI {rsi_int} — קנוי יתר, יש לשים לב לתיקון"

    # Momentum note
    if price_change_since_earnings > 15:
        momentum_note = f"עלתה {price_change_since_earnings:.0f}% מאז הדוח"
    elif price_change_since_earnings > 5:
        momentum_note = f"עלתה {price_change_since_earnings:.0f}% מאז הדוח"
    elif price_change_since_earnings < -10:
        momentum_note = f"ירדה {abs(price_change_since_earnings):.0f}% מאז הדוח — פוטנציאל כניסה נמוך יותר"
    elif price_change_since_earnings < -5:
        momentum_note = "ירדה מאז הדוח — פוטנציאל כניסה נמוך יותר"
    elif resistance > price:
        dist_pct = round((resistance - price) / price * 100, 1)
        momentum_note = f"רזיסטנס ב-${resistance:.2f} — מרחק {dist_pct}% לפריצה"
    else:
        momentum_note = f"נסחרת קרוב לשיא — שמירה מעל ${support:.2f} חיונית"

    return f"{base}. {rsi_note}. {momentum_note}."


def _watch_level_text(price: float, resistance: float, support: float) -> str:
    if resistance > price:
        return f"פריצה מעל ${resistance:.2f}"
    return f"שמירה מעל ${support:.2f}"


# ── Per-ticker yfinance fetch ─────────────────────────────────────────────────

def _compute_score(surprise_pct: Optional[float], rsi: Optional[float],
                   price_change_since_earnings: float, has_8k: bool) -> float:
    """Composite score 0-100. Higher = more interesting for briefing."""
    # Earnings component (0-50): rewards strong beats
    earn_score = 0.0
    if surprise_pct is not None:
        if surprise_pct >= 50:
            earn_score = 50
        elif surprise_pct >= 20:
            earn_score = 30 + (surprise_pct - 20) / 30 * 20
        elif surprise_pct >= 5:
            earn_score = 15 + (surprise_pct - 5) / 15 * 15
        elif surprise_pct > 0:
            earn_score = 8
        # Negative surprise gives 0

    # RSI component (0-25): rewards neutral/healthy RSI
    rsi_score = 0.0
    if rsi is not None:
        if 45 <= rsi <= 65:
            rsi_score = 25
        elif 38 <= rsi <= 72:
            rsi_score = 18
        elif 30 <= rsi <= 80:
            rsi_score = 10
        elif rsi < 30:
            rsi_score = 8   # oversold — possible bounce candidate
        else:
            rsi_score = 5   # overbought — some momentum

    # Momentum component (0-20): price change since earnings or recent move
    mom_score = 0.0
    chg = price_change_since_earnings
    if chg >= 20:
        mom_score = 20
    elif chg >= 10:
        mom_score = 16
    elif chg >= 5:
        mom_score = 12
    elif chg >= 0:
        mom_score = 8
    elif chg >= -5:
        mom_score = 5
    else:
        mom_score = 2

    # SEC 8-K bonus (0-5)
    sec_bonus = 5.0 if has_8k else 0.0

    return round(earn_score + rsi_score + mom_score + sec_bonus, 1)


def _fetch_ticker_data_sync(ticker: str, min_surprise_pct: float = 0.0,
                            sec_8k_dates: Optional[Dict] = None,
                            rsi_min: float = 20.0,
                            rsi_max: float = 90.0,
                            min_market_cap: int = 500_000_000,
                            qqq_20d_pct: float = 0.0) -> Optional[Dict]:
    """Fetch price/RSI/earnings for one ticker. Returns scored dict or None if no price data.
    Uses composite scoring — no hard reject on earnings/RSI alone.
    """
    reported_eps: Optional[float] = None
    try:
        stock = yf.Ticker(ticker)

        # ── Earnings dates (optional — no early reject) ──────
        surprise_pct = None
        earnings_date = None
        price_at_earnings = None
        earnings_history: list = []   # last 4 quarters
        next_earnings_date = None
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                ed = ex.submit(lambda: stock.earnings_dates).result(timeout=4)
            if ed is not None and not ed.empty:
                import pandas as pd
                now = datetime.now()
                cutoff = now - timedelta(days=365)  # up to 1 year for history
                past_all = ed.dropna(subset=['Reported EPS'])
                try:
                    past_all = past_all[past_all.index <= pd.Timestamp(now, tz='UTC')]
                except Exception:
                    pass
                # Most recent quarter within 6 months
                past = past_all[past_all.index >= pd.Timestamp(now - timedelta(days=180), tz='UTC')] \
                    if hasattr(past_all.index, 'tz') else \
                    past_all[past_all.index.astype(str) >= (now - timedelta(days=180)).strftime('%Y-%m-%d')]
                if not past.empty:
                    row = past.iloc[0]
                    sp = row.get('Surprise(%)')
                    eps_est = row.get('EPS Estimate')
                    eps_rep = row.get('Reported EPS')
                    if sp is not None and not (sp != sp):
                        sp_val = float(sp)
                        if abs(sp_val) > 200 and eps_est is not None and abs(float(eps_est)) < 0.1:
                            sp_val = None
                        if sp_val is not None:
                            surprise_pct = sp_val
                            earnings_date = str(past.index[0].date())
                            if eps_rep is not None and eps_rep == eps_rep:
                                try:
                                    reported_eps = float(eps_rep)
                                except Exception:
                                    pass
                # Earnings history — up to 4 most recent reported quarters
                for idx, qrow in past_all.head(4).iterrows():
                    sp_q = qrow.get('Surprise(%)')
                    eps_q = qrow.get('Reported EPS')
                    if sp_q is not None and sp_q == sp_q:
                        try:
                            sp_val_q = float(sp_q)
                            eps_val_q = round(float(eps_q), 2) if eps_q is not None and eps_q == eps_q else None
                            d_str = str(idx.date()) if hasattr(idx, 'date') else str(idx)
                            earnings_history.append({
                                'date': d_str,
                                'surprise_pct': round(sp_val_q, 1),
                                'eps': eps_val_q,
                                'beat': sp_val_q > 0,
                            })
                        except Exception:
                            pass
                # Next upcoming earnings (no Reported EPS yet)
                try:
                    future = ed[ed.index > pd.Timestamp(now, tz='UTC')]
                    if not future.empty:
                        next_earnings_date = str(future.index[0].date())
                except Exception:
                    pass
        except Exception:
            pass

        # ── History: RSI + price levels (REQUIRED — reject only if unavailable) ──
        rsi = None
        price = 0.0
        resistance = 0.0
        support = 0.0
        price_change_since_earnings = 0.0
        today_pct = None
        atr_pct = None
        price_history = []

        try:
            hist = stock.history(period='60d', interval='1d', timeout=4)
            if hist is None or hist.empty:
                return None
            closes = list(hist['Close'])
            rsi = _calc_rsi(closes, period=14)
            price = float(hist['Close'].iloc[-1])
            if price < 1.0:
                return None  # reject penny stocks
            resistance = float(hist['High'].tail(20).max())
            support = float(hist['Low'].tail(10).min())
            atr_pct = _calc_atr(hist)
            today_pct = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if len(closes) >= 2 else None
            price_history = [round(float(c), 2) for c in closes[-20:]]

            if earnings_date:
                for idx, row in hist.iterrows():
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
            return None

        # ── Company info: sector + market_cap ──
        company = ticker
        sector = ''
        market_cap = 0

        week52_high = 0.0
        week52_low = 0.0
        avg_volume = 0
        volume_ratio = None
        try:
            fi = stock.fast_info
            market_cap = int(getattr(fi, 'market_cap', 0) or 0)
            week52_high = float(getattr(fi, 'year_high', 0) or 0)
            week52_low = float(getattr(fi, 'year_low', 0) or 0)
            avg_volume = int(getattr(fi, 'three_month_average_volume', 0) or 0)
            today_vol = int(hist['Volume'].iloc[-1]) if not hist.empty else 0
            if avg_volume > 0 and today_vol > 0:
                volume_ratio = round(today_vol / avg_volume, 1)
        except Exception:
            pass

        # Reject true micro-caps (< 500M) — these are too illiquid for briefing
        if market_cap > 0 and market_cap < min_market_cap:
            return None

        # RS vs QQQ: stock 20d return minus QQQ 20d return
        rs_vs_qqq = None
        if qqq_20d_pct and len(closes) >= 20:
            try:
                stock_20d = (closes[-1] - closes[-20]) / closes[-20] * 100
                rs_vs_qqq = round(stock_20d - qqq_20d_pct, 1)
            except Exception:
                pass

        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                info = ex.submit(lambda: stock.info or {}).result(timeout=2)
            company = str(info.get('longName') or info.get('shortName') or ticker)
            sector = str(info.get('sector') or '')
            if market_cap == 0:
                market_cap = int(info.get('marketCap') or 0)
                if 0 < market_cap < min_market_cap:
                    return None
        except Exception:
            pass

        # ── News: yfinance (new nested content structure) ──────────────────
        recent_news = []
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                raw_news = ex.submit(lambda: stock.news or []).result(timeout=4)
            parsed = []
            for n in raw_news[:5]:
                content = n.get('content', n)  # new API has nested 'content', old API is flat
                title = (content.get('title') or n.get('title') or '').strip()
                url = (
                    (content.get('canonicalUrl') or {}).get('url')
                    or (content.get('clickThroughUrl') or {}).get('url')
                    or n.get('link') or n.get('url') or ''
                )
                publisher = (
                    (content.get('provider') or {}).get('displayName')
                    or n.get('publisher') or ''
                )
                pub_date = content.get('pubDate') or content.get('displayTime') or n.get('providerPublishTime') or ''
                summary = content.get('summary') or content.get('description') or ''
                if title and url:
                    news_type = _classify_news_type(title, summary)
                    parsed.append({'title': title, 'url': url, 'publisher': publisher,
                                   'published_at': pub_date, 'summary': summary,
                                   'news_type': news_type})
            if parsed:
                # Batch-translate all titles + summaries in one API call
                texts_to_translate = [p['title'] for p in parsed] + [p['summary'] for p in parsed]
                translated = _translate_batch(texts_to_translate)
                mid = len(parsed)
                titles_he = translated[:mid]
                summaries_he = translated[mid:]
                for i, p in enumerate(parsed):
                    recent_news.append({
                        'title': titles_he[i] if i < len(titles_he) else p['title'],
                        'url': p['url'],
                        'publisher': p['publisher'],
                        'published_at': p['published_at'],
                        'summary': summaries_he[i] if i < len(summaries_he) else p['summary'],
                        'news_type': p['news_type'],
                    })
        except Exception:
            pass

        sec_8k_info_local = (sec_8k_dates or {}).get(ticker)
        has_8k = bool(sec_8k_info_local and sec_8k_info_local.get('sentiment') == 'bullish')

        score = _compute_score(surprise_pct, rsi, price_change_since_earnings, has_8k)

        reason = _generate_reason(
            ticker, company, surprise_pct, rsi or 50, price,
            resistance, support, price_change_since_earnings
        )

        if has_8k and sec_8k_info_local.get('type'):
            reason = reason.rstrip('.') + f". בנוסף, דיווחה לאחרונה על: {sec_8k_info_local['type']}."

        wind = _generate_wind(sector, surprise_pct or 0, price_change_since_earnings,
                              rsi or 50, reported_eps)

        return {
            'ticker': ticker,
            'company': company,
            'sector': sector,
            'market_cap': market_cap,
            'price': round(price, 2),
            'rsi': round(rsi, 1) if rsi else None,
            'score': score,
            'earnings_surprise_pct': round(surprise_pct, 1) if surprise_pct is not None else None,
            'earnings_date': earnings_date,
            'earnings_history': earnings_history,
            'next_earnings_date': next_earnings_date,
            'week52_high': round(week52_high, 2) if week52_high else None,
            'week52_low': round(week52_low, 2) if week52_low else None,
            'price_change_since_earnings': price_change_since_earnings,
            'resistance': round(resistance, 2),
            'support': round(support, 2),
            'watch_level': _watch_level_text(price, resistance, support),
            'reason': reason,
            'reported_eps': reported_eps,
            'recent_news': recent_news,
            'tailwinds': wind['tailwinds'],
            'headwinds': wind['headwinds'],
            'avg_volume': avg_volume,
            'volume_ratio': volume_ratio,
            'atr_pct': atr_pct,
            'today_pct': today_pct,
            'price_history': price_history,
            'rs_vs_qqq': rs_vs_qqq,
            'recent_8k_date': sec_8k_info_local['date'] if sec_8k_info_local else None,
            'recent_8k_type': sec_8k_info_local.get('type') if sec_8k_info_local else None,
            'recent_8k_sentiment': sec_8k_info_local.get('sentiment') if sec_8k_info_local else None,
        }

    except Exception:
        return None


# ── Single-ticker on-demand briefing ─────────────────────────────────────────

def fetch_single_ticker_briefing(ticker: str) -> Dict:
    """
    Run a full briefing analysis on any ticker, regardless of earnings filter.
    Always returns a dict (never None). Missing data fields are None/0.
    """
    ticker = ticker.upper().strip()
    try:
        stock = yf.Ticker(ticker)

        # Earnings data (optional — don't reject if missing)
        surprise_pct = None
        earnings_date = None
        reported_eps = None
        price_at_earnings = None
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                ed = ex.submit(lambda: stock.earnings_dates).result(timeout=5)
            if ed is not None and not ed.empty:
                import pandas as pd
                now = datetime.now()
                cutoff = now - timedelta(days=120)
                past = ed.dropna(subset=['Reported EPS'])
                try:
                    past = past[past.index <= pd.Timestamp(now, tz='UTC')]
                    past = past[past.index >= pd.Timestamp(cutoff, tz='UTC')]
                except Exception:
                    past = past[past.index.astype(str) >= cutoff.strftime('%Y-%m-%d')]
                if not past.empty:
                    row = past.iloc[0]
                    sp = row.get('Surprise(%)')
                    eps_rep = row.get('Reported EPS')
                    if sp is not None and sp == sp:
                        sp_val = float(sp)
                        eps_est = row.get('EPS Estimate')
                        if abs(sp_val) > 200 and eps_est is not None and abs(float(eps_est)) < 0.1:
                            sp_val = None
                        if sp_val is not None:
                            surprise_pct = round(sp_val, 1)
                            earnings_date = str(past.index[0].date())
                    if eps_rep is not None and eps_rep == eps_rep:
                        try:
                            reported_eps = float(eps_rep)
                        except Exception:
                            pass
        except Exception:
            pass

        # History for price/RSI/levels
        price = 0.0
        rsi = None
        resistance = 0.0
        support = 0.0
        price_change_since_earnings = 0.0
        try:
            hist = stock.history(period='60d', interval='1d', timeout=5)
            if hist is not None and not hist.empty:
                closes = list(hist['Close'])
                rsi = _calc_rsi(closes, period=14)
                price = float(hist['Close'].iloc[-1])
                resistance = float(hist['High'].tail(20).max())
                support = float(hist['Low'].tail(10).min())
                if earnings_date:
                    for idx, row in hist.iterrows():
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

        # Company info
        company = ticker
        sector = ''
        market_cap = 0
        try:
            fi = stock.fast_info
            market_cap = int(getattr(fi, 'market_cap', 0) or 0)
        except Exception:
            pass
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                info = ex.submit(lambda: stock.info or {}).result(timeout=3)
            company = str(info.get('longName') or info.get('shortName') or ticker)
            sector = str(info.get('sector') or '')
            if market_cap == 0:
                market_cap = int(info.get('marketCap') or 0)
        except Exception:
            pass

        reason = _generate_reason(
            ticker, company, surprise_pct or 0, rsi or 50, price,
            resistance, support, price_change_since_earnings
        )

        wind = _generate_wind(sector, surprise_pct or 0, price_change_since_earnings,
                              rsi or 50, reported_eps)

        return {
            'ticker': ticker,
            'company': company,
            'sector': sector,
            'market_cap': market_cap,
            'price': round(price, 2),
            'rsi': round(rsi, 1) if rsi else None,
            'earnings_surprise_pct': surprise_pct,
            'earnings_date': earnings_date,
            'price_change_since_earnings': price_change_since_earnings,
            'resistance': round(resistance, 2),
            'support': round(support, 2),
            'watch_level': _watch_level_text(price, resistance, support),
            'reason': reason,
            'reported_eps': reported_eps,
            'tailwinds': wind['tailwinds'],
            'headwinds': wind['headwinds'],
        }
    except Exception as e:
        return {'ticker': ticker, 'error': str(e)}


# ── Market status (SPY + QQQ) ─────────────────────────────────────────────────

def _fetch_market_status_sync() -> Dict:
    try:
        data = {}
        spy_daily = None

        for sym in ['SPY', 'QQQ']:
            try:
                t = yf.Ticker(sym)
                intra = t.history(period='1d', interval='5m', timeout=5)
                # Fetch 1y daily for SPY (MA200), 5d for QQQ
                period_str = '1y' if sym == 'SPY' else '5d'
                daily = t.history(period=period_str, interval='1d', timeout=5)
                if intra is not None and not intra.empty and daily is not None and len(daily) >= 2:
                    last = float(intra['Close'].iloc[-1])
                    prev_close = float(daily['Close'].iloc[-2])
                    pct = round((last - prev_close) / prev_close * 100, 2)
                    data[sym] = {'price': round(last, 2), 'change_pct': pct}
                    if sym == 'SPY':
                        spy_daily = daily
                elif daily is not None and len(daily) >= 2:
                    prev = float(daily['Close'].iloc[-2])
                    last = float(daily['Close'].iloc[-1])
                    pct = round((last - prev) / prev * 100, 2)
                    data[sym] = {'price': round(last, 2), 'change_pct': pct}
                    if sym == 'SPY':
                        spy_daily = daily
            except Exception:
                data[sym] = {'price': 0, 'change_pct': 0}

        # SPY Moving Averages (50 / 200) + market timing signal
        spy_ma50 = spy_ma200 = spy_vs_200_pct = ma_signal = None
        if spy_daily is not None:
            closes_spy = spy_daily['Close'].values
            spy_price = float(closes_spy[-1])
            if len(closes_spy) >= 50:
                spy_ma50 = round(float(closes_spy[-50:].mean()), 2)
            if len(closes_spy) >= 200:
                spy_ma200 = round(float(closes_spy[-200:].mean()), 2)
                spy_vs_200_pct = round((spy_price - spy_ma200) / spy_ma200 * 100, 1)
                if spy_price > spy_ma200 * 1.03:
                    ma_signal = 'bullish'    # >3% above 200 MA — healthy uptrend
                elif spy_price < spy_ma200 * 0.97:
                    ma_signal = 'bearish'   # >3% below 200 MA — downtrend
                else:
                    ma_signal = 'neutral'   # near 200 MA

        # VIX
        vix = None
        try:
            vix = round(float(yf.Ticker('^VIX').fast_info.last_price or 0), 1) or None
        except Exception:
            pass

        # Sector ETF performance (parallel)
        sector_perf = {}
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {ex.submit(_fetch_sector_etf_sync, sym): (sym, name)
                    for sym, name in SECTOR_ETFS.items()}
            for fut, (sym, name) in futs.items():
                try:
                    _, pct = fut.result(timeout=8)
                    if pct is not None:
                        sector_perf[sym] = {'name': name, 'pct': pct}
                except Exception:
                    pass

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
            'vix': vix,
            'spy_ma50': spy_ma50,
            'spy_ma200': spy_ma200,
            'spy_vs_200_pct': spy_vs_200_pct,
            'ma_signal': ma_signal,
            'sector_perf': sector_perf,
        }
    except Exception:
        return {'spy': {}, 'qqq': {}, 'summary': 'נתוני שוק לא זמינים'}


# ── Candidate universe from Finviz ────────────────────────────────────────────

async def _scrape_finviz_tickers(session: aiohttp.ClientSession, url: str) -> List[str]:
    """Scrape tickers from a Finviz screener URL."""
    headers = {'User-Agent': 'Mozilla/5.0 (compatible; StockScanner/1.0)'}
    tickers = []
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=12)) as resp:
            if resp.status != 200:
                return []
            html = await resp.text()
        soup = BeautifulSoup(html, 'html.parser')
        rows = soup.select('tr.styled-row-light, tr.styled-row-dark, tr[id^="row"]')
        for row in rows:
            cells = row.select('td')
            if len(cells) > 1:
                ticker_el = row.select_one('td a.tab-link')
                if ticker_el:
                    tickers.append(ticker_el.text.strip())
        if not tickers:
            for a in soup.select('a.screener-link-primary'):
                t = a.text.strip()
                if t and t.isupper() and len(t) <= 5:
                    tickers.append(t)
    except Exception as e:
        print(f"Briefing: Finviz fetch failed ({url[:60]}...): {e}")
    return tickers


def _fetch_volume_ticker_sync(ticker: str) -> Optional[Dict]:
    """Fetch data for an unusual-volume mover. No earnings requirement."""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='15d', interval='1d', timeout=4)
        if hist is None or hist.empty or len(hist) < 2:
            return None

        price = float(hist['Close'].iloc[-1])
        if price < 1.0:
            return None

        # Price changes
        prev_close = float(hist['Close'].iloc[-2])
        chg_1d = round((price / prev_close - 1) * 100, 2) if prev_close > 0 else 0
        chg_5d = round((price / float(hist['Close'].iloc[max(-6, -len(hist))]) - 1) * 100, 2) if len(hist) >= 5 else chg_1d

        # Relative volume (today vs average of prior days)
        today_vol = float(hist['Volume'].iloc[-1])
        avg_vol = float(hist['Volume'].iloc[:-1].mean()) if len(hist) > 1 else today_vol
        rel_vol = round(today_vol / avg_vol, 2) if avg_vol > 0 else 1.0

        # Only include if there's meaningful volume surge or price move
        if rel_vol < 1.3 and abs(chg_1d) < 3:
            return None

        # RSI
        closes = list(hist['Close'])
        rsi = _calc_rsi(closes, period=14)

        # Market cap (fast, no hang)
        market_cap = 0
        try:
            fi = stock.fast_info
            market_cap = int(getattr(fi, 'market_cap', 0) or 0)
        except Exception:
            pass

        # Company name + sector — quick, with timeout
        company = ticker
        sector = ''
        try:
            with ThreadPoolExecutor(max_workers=1) as ex:
                info = ex.submit(lambda: stock.info or {}).result(timeout=2)
            company = str(info.get('longName') or info.get('shortName') or ticker)
            sector = str(info.get('sector') or '')
            if market_cap == 0:
                market_cap = int(info.get('marketCap') or 0)
        except Exception:
            pass

        resistance = float(hist['High'].tail(10).max())
        support = float(hist['Low'].tail(5).min())

        return {
            'ticker': ticker,
            'company': company,
            'sector': sector,
            'market_cap': market_cap,
            'price': round(price, 2),
            'chg_1d': chg_1d,
            'chg_5d': chg_5d,
            'rel_volume': rel_vol,
            'rsi': round(rsi, 1) if rsi else None,
            'resistance': round(resistance, 2),
            'support': round(support, 2),
            'is_volume_play': True,
        }
    except Exception:
        return None


async def _get_candidate_tickers(session: aiohttp.ClientSession) -> tuple:
    """Scrape Finviz for stocks with recent earnings (this + prev month) + volume > 500K.
    Also scrapes unusual-volume movers. Returns (earnings_tickers, volume_tickers)."""
    earnings_urls = [
        # Previous calendar month earnings
        ('https://finviz.com/screener.ashx?v=111'
         '&f=earningsdate_prevmonth,sh_avgvol_o500&o=-volume'),
        # Current calendar month earnings (catches Feb earnings)
        ('https://finviz.com/screener.ashx?v=111'
         '&f=earningsdate_thismonth,sh_avgvol_o500&o=-volume'),
    ]
    volume_urls = [
        # Mid/large cap unusual volume (rel vol > 1.5x, avg vol > 500K)
        ('https://finviz.com/screener.ashx?v=111'
         '&f=sh_relvol_o1.5,sh_avgvol_o500,sh_price_o1&o=-relativevolume'),
        # Small cap unusual volume (rel vol > 2x, avg vol > 100K)
        ('https://finviz.com/screener.ashx?v=111'
         '&f=sh_relvol_o2,sh_avgvol_o100,sh_price_o1&o=-relativevolume'),
    ]

    all_tasks = [_scrape_finviz_tickers(session, u) for u in earnings_urls + volume_urls]
    results = await asyncio.gather(*all_tasks, return_exceptions=True)

    tickers = []
    for r in results[:2]:
        if isinstance(r, list):
            tickers.extend(r)

    # Deduplicate earnings tickers, cap at 30
    seen = set()
    result = []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            result.append(t)
        if len(result) >= 30:
            break

    # Volume tickers (separate pool, cap at 20, no overlap with earnings)
    volume_tickers = []
    vol_seen = set(result)
    for r in results[2:]:
        if isinstance(r, list):
            for t in r:
                if t not in vol_seen:
                    vol_seen.add(t)
                    volume_tickers.append(t)
                if len(volume_tickers) >= 20:
                    break
    volume_tickers = volume_tickers[:20]

    # Track how many tickers came from Finviz (before adding biotech/fallback)
    finviz_count = len(result)
    seen_set = set(result)

    # Always add sector-diverse anchors — guaranteed healthcare + other sectors
    # Interleaved so the cap doesn't cut any sector out
    sector_anchors = [
        # Tech
        'NVDA', 'META', 'MSFT', 'AAPL', 'GOOGL', 'AMZN',
        'CRM', 'SNOW', 'MDB', 'NET', 'PANW', 'CRWD',
        'DDOG', 'ZS', 'APP', 'PLTR', 'SMCI', 'AMD',
        'COIN', 'RBLX', 'ROKU', 'PYPL', 'ZM', 'SPOT',
        'CELH', 'BILL', 'HUBS', 'RBRK', 'DKNG', 'ABNB',
        # Healthcare (large-cap)
        'LLY', 'UNH', 'ABBV', 'JNJ', 'MRK', 'PFE',
        'AMGN', 'BMY', 'CI', 'CVS', 'ISRG', 'HUM',
        'MDT', 'EW', 'SYK', 'BSX',
        # Financials
        'GS', 'JPM', 'MS', 'V', 'MA', 'AXP',
        'BLK', 'SCHW', 'SPGI', 'MCO',
        # Consumer / Retail
        'COST', 'WMT', 'HD', 'NKE', 'SBUX', 'MCD',
        'CMG', 'BURL', 'TJX', 'ROST',
        # Industrials / Energy
        'CAT', 'GE', 'HON', 'RTX', 'AXON',
        'XOM', 'CVX', 'COP',
        # Semiconductors
        'AVGO', 'QCOM', 'MU', 'AMAT', 'LRCX', 'TXN',
        # Real Estate / Utilities
        'AMT', 'EQIX', 'PLD',
    ]
    for t in sector_anchors:
        if t not in seen_set:
            result.append(t)
            seen_set.add(t)

    if finviz_count < 10:
        print(f"Briefing: Finviz returned {finviz_count} tickers, added sector anchors ({len(result)} total)")

    # Biotech tickers — always added
    biotech_tickers = [
        'MRNA', 'REGN', 'VRTX', 'GILD', 'ALNY', 'ARQT', 'ACAD',
        'NBIX', 'INSM', 'NUVL', 'APLS', 'TGTX', 'RCKT', 'RVMD',
    ]
    for bt in biotech_tickers:
        if bt not in seen_set:
            result.append(bt)
            seen_set.add(bt)

    # Hard cap — never scan more than 70 tickers total
    return result[:70], volume_tickers


# ── Main briefing function ────────────────────────────────────────────────────

class BriefingService:

    async def get_daily_briefing(
        self,
        min_surprise_pct: float = 0.0,   # no hard earnings floor — use scoring
        rsi_min: float = 20.0,            # wide RSI range — scoring handles it
        rsi_max: float = 90.0,
        top_n: int = 25,
        min_market_cap: int = 500_000_000,  # 500M — include mid-caps
    ) -> Dict:
        """
        Build daily briefing: top stocks scored by earnings beat + RSI + momentum.
        Always returns at least top_n stocks when enough candidates exist.
        """
        # 1. Fetch candidate tickers + SEC 8-K data concurrently
        async with aiohttp.ClientSession() as session:
            ticker_result, sec_8k_dates = await asyncio.gather(
                _get_candidate_tickers(session),
                get_recent_8k_tickers(session, days=7),
                return_exceptions=True,
            )
        if isinstance(ticker_result, Exception) or not isinstance(ticker_result, tuple):
            candidates = []
            volume_candidates = []
        else:
            candidates, volume_candidates = ticker_result
        if isinstance(sec_8k_dates, Exception):
            sec_8k_dates = {}

        # Add SEC 8-K tickers not already in candidates (cap at 30 extra)
        # Exclude tickers with clearly bearish signals (bankruptcy, restatement, delisting)
        seen_candidates = set(candidates)
        sec_added = 0
        sec_skipped_bearish = 0
        for t, info in list(sec_8k_dates.items()):
            # Skip bearish-flagged filings (e.g. bankruptcy 1.03, restatement 4.02, delisting 3.01)
            if isinstance(info, dict):
                bad_items = set(info.get('items', [])) & BEARISH_EXCLUDE_ITEMS
                if bad_items:
                    sec_skipped_bearish += 1
                    continue
            if t not in seen_candidates and sec_added < 10:
                candidates.append(t)
                seen_candidates.add(t)
                sec_added += 1
        if sec_skipped_bearish:
            print(f"SEC: skipped {sec_skipped_bearish} tickers with bearish 8-K items")

        # Final hard cap
        candidates = candidates[:70]

        print(f"Briefing: scanning {len(candidates)} candidates "
              f"({len(sec_8k_dates)} with recent 8-K), top_n={top_n}...")

        # 1b. Pre-fetch QQQ 20d return for RS line (fast, ~1s)
        loop = asyncio.get_running_loop()
        qqq_20d_pct = await loop.run_in_executor(None, _get_qqq_20d_pct)
        print(f"Briefing: QQQ 20d return = {qqq_20d_pct}%")

        # 2. Batch-process tickers via thread pool (yfinance is blocking)
        sem = asyncio.Semaphore(6)
        executor = ThreadPoolExecutor(max_workers=8)

        async def process_one(ticker: str) -> Optional[Dict]:
            async with sem:
                try:
                    fn = functools.partial(
                        _fetch_ticker_data_sync, ticker, min_surprise_pct,
                        sec_8k_dates, rsi_min, rsi_max, min_market_cap,
                        qqq_20d_pct
                    )
                    return await asyncio.wait_for(
                        loop.run_in_executor(executor, fn),
                        timeout=12
                    )
                except asyncio.TimeoutError:
                    return None
                except Exception:
                    return None

        tasks = [process_one(t) for t in candidates]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 2b. Volume movers scan (parallel with earnings scan completion)
        vol_sem = asyncio.Semaphore(4)

        async def process_vol(ticker: str) -> Optional[Dict]:
            async with vol_sem:
                try:
                    return await asyncio.wait_for(
                        loop.run_in_executor(executor, functools.partial(_fetch_volume_ticker_sync, ticker)),
                        timeout=10
                    )
                except Exception:
                    return None

        vol_tasks = [process_vol(t) for t in volume_candidates]
        vol_results = await asyncio.gather(*vol_tasks, return_exceptions=True)
        executor.shutdown(wait=False)

        qualified = [r for r in results if isinstance(r, dict) and r is not None]
        print(f"Briefing: {len(qualified)} stocks with price data (from {len(candidates)} candidates)")

        # Volume movers: sort by relative volume * abs(chg_1d), take top 8
        volume_movers = [r for r in vol_results if isinstance(r, dict) and r is not None]
        volume_movers.sort(key=lambda x: x.get('rel_volume', 1) * (1 + abs(x.get('chg_1d', 0)) / 10), reverse=True)
        volume_movers = volume_movers[:8]
        print(f"Briefing: {len(volume_movers)} volume movers (from {len(volume_candidates)} candidates)")

        # 3. Sort by composite score, apply sector diversity cap (max 4 per sector)
        qualified.sort(key=lambda x: x.get('score', 0), reverse=True)
        _sector_counts: Dict[str, int] = {}
        top_stocks = []
        for s in qualified:
            sec = s.get('sector') or 'Other'
            if _sector_counts.get(sec, 0) < 4:
                top_stocks.append(s)
                _sector_counts[sec] = _sector_counts.get(sec, 0) + 1
            if len(top_stocks) >= top_n:
                break

        # 4. Market status (run concurrently — no SEC highlights to keep it fast)
        market_status = await loop.run_in_executor(None, _fetch_market_status_sync)

        return {
            'stocks': top_stocks,
            'volume_movers': volume_movers,
            'market_status': market_status,
            'generated_at': datetime.now().astimezone().isoformat(),
            'candidates_scanned': len(candidates),
            'qualified_count': len(qualified),
        }
