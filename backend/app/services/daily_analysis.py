"""
Daily Stock Analysis Service — based on ZhuLinsen/daily_stock_analysis.

Core logic (adapted for US stocks):
1. MA5/10/20/60 trend alignment (7 states, 30pts)
2. Deviation rate from MA5 — anti-FOMO filter at >5% (20pts)
3. Volume pattern vs 5-day avg (15pts)
4. MA proximity support (10pts)
5. MACD 12/26/9 state (15pts)
6. RSI-6/12/24 condition (10pts)

Composite score 0-100 → STRONG BUY / BUY / HOLD / WAIT / SELL
Precise entry/stop/target levels derived from MA positions.
"""

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Dict, Optional, Tuple

import aiohttp
import yfinance as yf
from bs4 import BeautifulSoup


# ── Moving Averages ────────────────────────────────────────────────────────────

def _sma(prices: list, period: int) -> Optional[float]:
    if len(prices) < period:
        return None
    return sum(prices[-period:]) / period


def _ema(prices: list, period: int) -> list:
    if len(prices) < period:
        return []
    mult = 2 / (period + 1)
    result = [sum(prices[:period]) / period]
    for p in prices[period:]:
        result.append((p - result[-1]) * mult + result[-1])
    return result


# ── Trend Alignment (7 states) ─────────────────────────────────────────────────

def _calc_trend(prices: list) -> Tuple[str, int, float]:
    """
    Returns (trend_label_he, trend_score 0-30, ma_alignment_score).
    7 states from ZhuLinsen repo.
    """
    if len(prices) < 20:
        return ('ניטרלי', 10, 0.0)

    ma5  = _sma(prices, 5)
    ma10 = _sma(prices, 10)
    ma20 = _sma(prices, 20)
    ma60 = _sma(prices, 60) if len(prices) >= 60 else None

    # Check if MAs are expanding (comparing gap now vs 5 days ago)
    expanding = False
    if len(prices) >= 25:
        ma5_5d  = _sma(prices[:-5], 5)
        ma10_5d = _sma(prices[:-5], 10)
        if ma5 and ma5_5d and ma10 and ma10_5d:
            gap_now = abs(ma5 - ma10)
            gap_5d  = abs(ma5_5d - ma10_5d)
            expanding = gap_now > gap_5d * 1.05

    if ma5 and ma10 and ma20:
        if ma5 > ma10 > ma20:
            if expanding:
                return ('חזק עולה', 30, 1.0)     # Strong bull — MAs expanding
            else:
                return ('עולה', 25, 0.85)          # Bull
        elif ma5 > ma10 and ma20 > ma10:
            return ('החלשות עלייה', 18, 0.60)      # Weakening bull
        elif ma5 < ma10 < ma20:
            if expanding:
                return ('חזק יורד', 0, 0.0)        # Strong bear
            else:
                return ('יורד', 5, 0.15)            # Bear
        elif ma5 < ma10 and ma20 < ma10:
            return ('החלשות ירידה', 12, 0.40)       # Weakening bear
        elif ma5 > ma20 > ma10:
            return ('התאוששות', 20, 0.65)           # Recovery
        else:
            return ('ניטרלי', 14, 0.45)             # Neutral / mixed

    return ('ניטרלי', 10, 0.30)


# ── Deviation Rate (anti-FOMO) ─────────────────────────────────────────────────

def _calc_deviation(price: float, ma5: float, ma10: float, ma20: float) -> Tuple[float, int, bool]:
    """
    Returns (deviation_from_ma5_pct, deviation_score 0-20, is_chasing_high).
    Anti-FOMO: if price >5% above MA5 = is_chasing_high = True.
    Best entry: price near or slightly below MA5/MA10.
    """
    if ma5 <= 0:
        return (0.0, 10, False)

    dev_ma5  = (price - ma5)  / ma5  * 100
    dev_ma10 = (price - ma10) / ma10 * 100
    dev_ma20 = (price - ma20) / ma20 * 100

    BIAS_THRESHOLD = 5.0
    is_chasing = dev_ma5 > BIAS_THRESHOLD

    # Score: best when near or at MA5/MA10 (pullback entry zone)
    abs_dev = abs(dev_ma5)
    if abs_dev <= 1.0:
        score = 20    # Right at MA5 — ideal
    elif abs_dev <= 2.5:
        score = 18
    elif abs_dev <= BIAS_THRESHOLD:
        score = 14
    elif abs_dev <= 8.0:
        score = 8     # Extended but not extreme
    else:
        score = 2     # Very extended

    # Penalty: if below MA5, slight reduction vs neutral
    if dev_ma5 < -5:
        score = max(score - 5, 0)  # Far below MA5 also bad (downtrend)

    return (round(dev_ma5, 2), score, is_chasing)


# ── Volume Pattern ─────────────────────────────────────────────────────────────

def _calc_volume_pattern(closes: list, volumes: list) -> Tuple[str, int]:
    """
    5 patterns from ZhuLinsen (adapted):
    Returns (pattern_label_he, volume_score 0-15).
    """
    if len(volumes) < 6 or len(closes) < 2:
        return ('כמות נורמלית', 8)

    avg_vol_5d = sum(volumes[-6:-1]) / 5
    curr_vol   = volumes[-1]
    vol_ratio  = curr_vol / avg_vol_5d if avg_vol_5d > 0 else 1.0

    price_up   = closes[-1] > closes[-2]
    shrinking  = vol_ratio < 0.7
    heavy      = vol_ratio > 1.5

    if shrinking and not price_up:
        return ('כמות מצטמצמת — ירידה בריאה', 15)   # Best: shrinking vol on pullback
    elif heavy and price_up:
        return ('כמות כבדה — עלייה חזקה', 13)         # Good: heavy vol on rise
    elif shrinking and price_up:
        return ('כמות חלשה — עלייה צולעת', 6)         # Weak: shrinking vol on rise
    elif heavy and not price_up:
        return ('כמות כבדה — ירידה', 2)               # Bad: heavy vol on decline
    else:
        return ('כמות נורמלית', 8)                     # Neutral


# ── MA Support Score ───────────────────────────────────────────────────────────

def _calc_ma_support(price: float, ma5: Optional[float], ma10: Optional[float], ma20: Optional[float]) -> int:
    """Score 0-10 based on proximity to MA support levels."""
    score = 0
    if ma5 and abs(price - ma5) / price < 0.02:
        score += 5    # Within 2% of MA5
    elif ma10 and abs(price - ma10) / price < 0.02:
        score += 3    # Within 2% of MA10
    if ma20 and price > ma20:
        score += 5    # Above MA20 (trending)
    return min(score, 10)


# ── MACD ───────────────────────────────────────────────────────────────────────

def _calc_macd_score(prices: list) -> Tuple[str, int, dict]:
    """
    Returns (label_he, score 0-15, raw_data).
    Golden cross above zero = 15pts.
    """
    if len(prices) < 40:
        return ('—', 8, {})

    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    offset = len(ema12) - len(ema26)
    ema12a = ema12[offset:]
    macd_line = [f - s for f, s in zip(ema12a, ema26)]
    if len(macd_line) < 12:
        return ('—', 8, {})
    signal_line = _ema(macd_line, 9)
    if not signal_line:
        return ('—', 8, {})

    dif = macd_line[-1]
    dea = signal_line[-1]
    bar = (dif - dea) * 2
    prev_dif = macd_line[-2] if len(macd_line) >= 2 else dif
    prev_dea = signal_line[-2] if len(signal_line) >= 2 else dea

    golden_cross = (dif > dea) and (prev_dif <= prev_dea)
    dead_cross   = (dif < dea) and (prev_dif >= prev_dea)

    raw = {'dif': round(dif, 4), 'dea': round(dea, 4), 'bar': round(bar, 4)}

    if golden_cross and dif > 0:
        return ('צלב זהב מעל אפס', 15, raw)       # Best
    elif golden_cross and dif <= 0:
        return ('צלב זהב מתחת אפס', 11, raw)      # Good
    elif dif > dea > 0:
        return ('MACD מעל אפס', 10, raw)           # Bullish but no fresh cross
    elif dif > dea and dif <= 0:
        return ('MACD בהתאוששות', 7, raw)          # Recovering below zero
    elif dead_cross:
        return ('צלב מוות', 2, raw)                # Bear cross
    elif dif < dea < 0:
        return ('MACD שלילי', 3, raw)              # Below zero, bearish
    else:
        return ('MACD ניטרלי', 8, raw)


# ── RSI (3 periods) ───────────────────────────────────────────────────────────

def _calc_rsi_val(prices: list, period: int) -> Optional[float]:
    if len(prices) < period + 1:
        return None
    p = prices[-(period * 3):]
    deltas = [p[i + 1] - p[i] for i in range(len(p) - 1)]
    gains  = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    if al == 0:
        return 100.0 if ag > 0 else 50.0
    return round(100 - (100 / (1 + ag / al)), 1)


def _calc_rsi_score(prices: list) -> Tuple[str, int, dict]:
    """
    RSI-6 (short), RSI-12 (medium), RSI-24 (long).
    Primary driver: RSI-12.
    Returns (label_he, score 0-10, raw_data).
    """
    r6  = _calc_rsi_val(prices, 6)
    r12 = _calc_rsi_val(prices, 12)
    r24 = _calc_rsi_val(prices, 24)
    raw = {'rsi6': r6, 'rsi12': r12, 'rsi24': r24}

    if r12 is None:
        return ('RSI —', 5, raw)

    # Primary: RSI-12
    if r12 < 30:
        label, score = ('RSI מוכר מדי', 10), 10      # Oversold = best buy
    elif r12 < 40:
        label, score = ('RSI נמוך — כניסה', 8), 8
    elif r12 <= 60:
        label, score = ('RSI ניטרלי', 6), 6
    elif r12 <= 70:
        label, score = ('RSI גבוה — זהירות', 3), 3
    else:
        label, score = ('RSI קנוי מדי', 1), 1         # Overbought = avoid

    return (label[0], score, raw)


# ── Entry / Stop / Target ──────────────────────────────────────────────────────

def _calc_levels(price: float, ma5: Optional[float], ma10: Optional[float],
                 ma20: Optional[float], trend_label: str) -> Dict:
    """
    Entry: buy near MA5/MA10 pullback.
    Stop: below MA20 (or -5% from entry if MA20 not available).
    Target: +7% from entry for bull, +5% for neutral.
    """
    # Entry point: the nearest MA below current price
    candidates = [m for m in [ma5, ma10, ma20] if m and m < price * 1.02]
    if candidates:
        entry = max(candidates)  # Closest MA below price
    else:
        entry = price

    # Stop: below MA20, or -5%
    stop = ma20 * 0.98 if ma20 else price * 0.95

    # Target
    target_pct = 0.08 if 'חזק' in trend_label else 0.06
    target = entry * (1 + target_pct)

    # Risk/reward
    risk = entry - stop
    reward = target - entry
    rr = round(reward / risk, 1) if risk > 0 else 0

    return {
        'entry':  round(entry, 2),
        'stop':   round(stop, 2),
        'target': round(target, 2),
        'rr':     rr,
    }


# ── Composite signal ───────────────────────────────────────────────────────────

def _classify_signal(score: int, is_chasing: bool) -> Tuple[str, str]:
    """Returns (signal_en, signal_he)."""
    if is_chasing:
        return ('WAIT', 'לא לרדוף ↗️')
    if score >= 75:
        return ('STRONG BUY', 'קנייה חזקה ✅')
    elif score >= 60:
        return ('BUY', 'קנייה 📈')
    elif score >= 45:
        return ('HOLD', 'המתנה ⏳')
    elif score >= 30:
        return ('WAIT', 'המתנה ⚠️')
    else:
        return ('SELL', 'מכירה 🔴')


# ── Per-ticker sync calculation ────────────────────────────────────────────────

def _analyze_ticker_sync(ticker: str) -> Optional[Dict]:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='90d', interval='1d', timeout=5)
        if hist is None or len(hist) < 22:
            return None

        closes  = list(hist['Close'])
        volumes = list(hist['Volume'])
        price   = closes[-1]
        change_pct = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if len(closes) >= 2 else 0.0

        ma5  = _sma(closes, 5)
        ma10 = _sma(closes, 10)
        ma20 = _sma(closes, 20)
        ma60 = _sma(closes, 60) if len(closes) >= 60 else None

        # 1. Trend (30pts)
        trend_label, trend_score, _ = _calc_trend(closes)

        # 2. Deviation / anti-FOMO (20pts)
        dev_pct, dev_score, is_chasing = _calc_deviation(
            price,
            ma5  or price,
            ma10 or price,
            ma20 or price,
        )

        # 3. Volume pattern (15pts)
        vol_label, vol_score = _calc_volume_pattern(closes, volumes)

        # 4. MA Support (10pts)
        ma_support_score = _calc_ma_support(price, ma5, ma10, ma20)

        # 5. MACD (15pts)
        macd_label, macd_score, macd_raw = _calc_macd_score(closes)

        # 6. RSI (10pts)
        rsi_label, rsi_score, rsi_raw = _calc_rsi_score(closes)

        # Composite
        total = trend_score + dev_score + vol_score + ma_support_score + macd_score + rsi_score
        total = min(100, total)

        signal_en, signal_he = _classify_signal(total, is_chasing)

        # Levels
        levels = _calc_levels(price, ma5, ma10, ma20, trend_label)

        # Volume ratio for display
        avg_vol_5d = sum(volumes[-6:-1]) / 5 if len(volumes) >= 6 else 0
        vol_ratio  = round(volumes[-1] / avg_vol_5d, 2) if avg_vol_5d > 0 else 1.0

        return {
            'ticker':       ticker,
            'sector':       _SECTOR_MAP.get(ticker, ''),
            'price':        round(price, 2),
            'change_pct':   change_pct,
            'ma5':          round(ma5, 2)  if ma5  else None,
            'ma10':         round(ma10, 2) if ma10 else None,
            'ma20':         round(ma20, 2) if ma20 else None,
            'ma60':         round(ma60, 2) if ma60 else None,
            'trend':        trend_label,
            'trend_score':  trend_score,
            'deviation':    dev_pct,       # % from MA5
            'is_chasing':   is_chasing,
            'vol_pattern':  vol_label,
            'vol_ratio':    vol_ratio,
            'macd_label':   macd_label,
            'macd':         macd_raw,
            'rsi':          rsi_raw,
            'rsi_label':    rsi_label,
            'score':        total,
            'signal':       signal_en,
            'signal_he':    signal_he,
            'levels':       levels,
            'breakdown': {
                'trend':    trend_score,
                'deviation': dev_score,
                'volume':   vol_score,
                'ma_support': ma_support_score,
                'macd':     macd_score,
                'rsi':      rsi_score,
            },
        }
    except Exception:
        return None


# ── Sector map ────────────────────────────────────────────────────────────────

_SECTOR_MAP: dict = {
    # Technology
    'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology',
    'NVDA': 'Technology', 'AMD': 'Technology', 'INTC': 'Technology',
    'QCOM': 'Technology', 'MU': 'Technology', 'AMAT': 'Technology',
    'LRCX': 'Technology', 'KLAC': 'Technology', 'TSM': 'Technology',
    'ASML': 'Technology', 'CRM': 'Technology', 'SNOW': 'Technology',
    'DDOG': 'Technology', 'NET': 'Technology', 'MDB': 'Technology',
    'ZS': 'Technology', 'PANW': 'Technology', 'CRWD': 'Technology',
    'ADBE': 'Technology', 'ORCL': 'Technology', 'SQ': 'Technology',
    'SHOP': 'Technology', 'UBER': 'Technology', 'LYFT': 'Technology',
    'TTD': 'Technology', 'TWLO': 'Technology', 'ZM': 'Technology',
    'DOCN': 'Technology', 'APP': 'Technology', 'SMCI': 'Technology',
    # Communication Services
    'META': 'Communication', 'NFLX': 'Communication', 'DIS': 'Communication',
    'RBLX': 'Communication', 'SNAP': 'Communication', 'SPOT': 'Communication',
    'PINS': 'Communication', 'ROKU': 'Communication',
    # Consumer Cyclical
    'AMZN': 'Consumer Cycl.', 'TSLA': 'Consumer Cycl.', 'ABNB': 'Consumer Cycl.',
    'DASH': 'Consumer Cycl.', 'TGT': 'Consumer Cycl.', 'HD': 'Consumer Cycl.',
    'LOW': 'Consumer Cycl.', 'BABA': 'Consumer Cycl.',
    # Consumer Defensive
    'WMT': 'Consumer Def.', 'COST': 'Consumer Def.', 'KO': 'Consumer Def.',
    'PEP': 'Consumer Def.', 'CELH': 'Consumer Def.',
    # Financial Services
    'JPM': 'Financials', 'GS': 'Financials', 'MS': 'Financials',
    'BAC': 'Financials', 'WFC': 'Financials', 'C': 'Financials',
    'AXP': 'Financials', 'V': 'Financials', 'MA': 'Financials',
    'PYPL': 'Financials', 'AFRM': 'Financials', 'COIN': 'Financials', 'HOOD': 'Financials',
    # Healthcare
    'PFE': 'Healthcare', 'JNJ': 'Healthcare', 'MRK': 'Healthcare',
    'ABBV': 'Healthcare', 'LLY': 'Healthcare', 'UNH': 'Healthcare', 'AMGN': 'Healthcare',
    # Biotech
    'MRNA': 'Biotech', 'BNTX': 'Biotech', 'REGN': 'Biotech', 'BIIB': 'Biotech',
    'VRTX': 'Biotech', 'GILD': 'Biotech', 'ALNY': 'Biotech', 'BMRN': 'Biotech',
    'INCY': 'Biotech', 'ILMN': 'Biotech', 'EXAS': 'Biotech', 'RXRX': 'Biotech',
    'EXEL': 'Biotech', 'RARE': 'Biotech', 'IONS': 'Biotech', 'FOLD': 'Biotech',
    'HALO': 'Biotech', 'ARQT': 'Biotech', 'ACAD': 'Biotech', 'SAGE': 'Biotech',
    # Energy
    'XOM': 'Energy', 'CVX': 'Energy',
    # Industrials
    'BA': 'Industrials', 'CAT': 'Industrials', 'DE': 'Industrials',
    'HON': 'Industrials', 'RTX': 'Industrials', 'GE': 'Industrials',
    'MMM': 'Industrials', 'UPS': 'Industrials',
}


# ── Ticker universe (reuse tech_signals logic) ────────────────────────────────

_FALLBACK_TICKERS = [
    'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'META', 'NVDA', 'TSLA', 'AMD',
    'NFLX', 'CRM', 'ORCL', 'ADBE', 'SHOP', 'SNOW', 'DDOG', 'NET',
    'MDB', 'ZS', 'PANW', 'CRWD', 'AFRM', 'COIN', 'HOOD', 'RBLX',
    'UBER', 'LYFT', 'ABNB', 'DASH', 'ROKU', 'PYPL', 'SQ', 'PINS',
    'SNAP', 'SPOT', 'DIS', 'JPM', 'BAC', 'GS', 'V', 'MA',
    'XOM', 'CVX', 'PFE', 'JNJ', 'MRK', 'ABBV', 'LLY', 'UNH',
    'KO', 'PEP', 'WMT', 'COST', 'TGT', 'HD', 'LOW', 'BABA',
    'TSM', 'ASML', 'QCOM', 'INTC', 'MU', 'AMAT', 'LRCX', 'KLAC',
    # Biotech
    'MRNA', 'BNTX', 'REGN', 'BIIB', 'VRTX', 'GILD', 'ALNY', 'BMRN',
    'INCY', 'ILMN', 'EXAS', 'RXRX', 'EXEL', 'RARE', 'IONS', 'FOLD',
]


async def _get_liquid_tickers(session: aiohttp.ClientSession) -> List[str]:
    url = (
        'https://finviz.com/screener.ashx?v=111'
        '&f=sh_avgvol_o1000,exch_nasd|exch_nyse'
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
        for a in soup.select('a.screener-link-primary'):
            t = a.text.strip()
            if t and t.isupper() and 1 <= len(t) <= 5:
                tickers.append(t)
    except Exception as e:
        print(f"DailyAnalysis: Finviz fetch failed: {e}")

    seen, result = set(), []
    for t in tickers:
        if t not in seen:
            seen.add(t)
            result.append(t)
        if len(result) >= 100:
            break

    if len(result) < 20:
        result = _FALLBACK_TICKERS[:]

    return result


# ── Main service ───────────────────────────────────────────────────────────────

class DailyAnalysisService:

    async def analyze(self) -> Dict:
        """
        Scan liquid US stocks with composite 0-100 scoring:
        MA trend + deviation (anti-FOMO) + volume + MACD + RSI.
        Returns stocks sorted by score descending.
        """
        async with aiohttp.ClientSession() as session:
            tickers = await _get_liquid_tickers(session)

        print(f"DailyAnalysis: scanning {len(tickers)} tickers...")

        sem      = asyncio.Semaphore(4)
        loop     = asyncio.get_event_loop()
        executor = ThreadPoolExecutor(max_workers=5)

        async def process_one(ticker: str) -> Optional[Dict]:
            async with sem:
                try:
                    return await asyncio.wait_for(
                        loop.run_in_executor(executor, _analyze_ticker_sync, ticker),
                        timeout=12
                    )
                except Exception:
                    return None

        tasks   = [process_one(t) for t in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        executor.shutdown(wait=False)

        valid = [r for r in results if isinstance(r, dict)]
        valid.sort(key=lambda x: x['score'], reverse=True)

        print(f"DailyAnalysis: {len(valid)} stocks analyzed")

        # Summary stats
        strong_buy = sum(1 for s in valid if s['signal'] == 'STRONG BUY')
        buy        = sum(1 for s in valid if s['signal'] == 'BUY')
        sell       = sum(1 for s in valid if s['signal'] == 'SELL')

        return {
            'stocks':       valid,
            'scanned':      len(tickers),
            'count':        len(valid),
            'strong_buy':   strong_buy,
            'buy':          buy,
            'sell':         sell,
            'generated_at': datetime.now().astimezone().isoformat(),
        }
