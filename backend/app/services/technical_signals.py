"""
Technical Signals Service — MACD + RSI + Bollinger Bands scanner.

Based on: https://github.com/ravening/stock-trading-bots
- MACD: 12/26 EMA crossover, 9-period signal line
  → BUY = MACD crosses above signal (bullish crossover)
  → SELL = MACD crosses below signal (bearish crossover)
- RSI: 20-period Wilder's smoothing
  → BUY = RSI < 40 (oversold)
  → SELL = RSI > 70 (overbought)
- Bollinger Bands: 20-period SMA ± 2σ
  → BUY = close < lower band
  → SELL = close > upper band
"""

import asyncio
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import List, Dict, Optional

import aiohttp
import yfinance as yf
from bs4 import BeautifulSoup


# ── EMA ───────────────────────────────────────────────────────────────────────

def _ema(prices: list, period: int) -> list:
    if len(prices) < period:
        return []
    mult = 2 / (period + 1)
    result = [sum(prices[:period]) / period]
    for p in prices[period:]:
        result.append((p - result[-1]) * mult + result[-1])
    return result


# ── MACD (12/26/9) ────────────────────────────────────────────────────────────

def _calc_macd(prices: list) -> Optional[Dict]:
    if len(prices) < 40:
        return None
    ema12 = _ema(prices, 12)
    ema26 = _ema(prices, 26)
    # Align: ema12 is longer, trim to match ema26 length
    offset = len(ema12) - len(ema26)
    ema12_aligned = ema12[offset:]
    macd_line = [f - s for f, s in zip(ema12_aligned, ema26)]
    if len(macd_line) < 12:
        return None
    signal_line = _ema(macd_line, 9)
    if not signal_line:
        return None

    macd_val = macd_line[-1]
    sig_val = signal_line[-1]
    hist = macd_val - sig_val

    prev_macd = macd_line[-2] if len(macd_line) >= 2 else macd_val
    prev_sig = signal_line[-2] if len(signal_line) >= 2 else sig_val
    prev_hist = prev_macd - prev_sig

    # Exact ravening/stock-trading-bots logic:
    # BUY  = MACD < Signal (MACD crosses BELOW signal — momentum weakening / contrarian entry)
    # SELL = MACD > Signal (MACD crosses ABOVE signal — momentum peaking / contrarian exit)
    if hist < 0 and prev_hist >= 0:
        signal_type = 'BUY'      # fresh cross: MACD dropped below signal
    elif hist > 0 and prev_hist <= 0:
        signal_type = 'SELL'     # fresh cross: MACD rose above signal
    elif hist < 0:
        signal_type = 'BELOW'    # MACD below signal (buy territory)
    else:
        signal_type = 'ABOVE'    # MACD above signal (sell territory)

    return {
        'value': round(macd_val, 4),
        'signal': round(sig_val, 4),
        'histogram': round(hist, 4),
        'signal_type': signal_type,
    }


# ── RSI (20-period Wilder's) ──────────────────────────────────────────────────

def _calc_rsi(prices: list, period: int = 20) -> Optional[Dict]:
    if len(prices) < period + 1:
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
        rsi = 100.0 if avg_gain > 0 else 50.0
    else:
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))
    rsi = round(rsi, 1)

    if rsi < 40:
        signal_type = 'BUY'
    elif rsi > 70:
        signal_type = 'SELL'
    else:
        signal_type = 'NEUTRAL'

    return {'value': rsi, 'signal_type': signal_type}


# ── Bollinger Bands (20/2σ) ───────────────────────────────────────────────────

def _calc_bollinger(prices: list, period: int = 20) -> Optional[Dict]:
    if len(prices) < period:
        return None
    window = prices[-period:]
    mean = sum(window) / period
    variance = sum((x - mean) ** 2 for x in window) / period
    std = math.sqrt(variance)
    upper = mean + 2 * std
    lower = mean - 2 * std
    current = prices[-1]
    pct_b = (current - lower) / (upper - lower) if (upper - lower) > 0 else 0.5

    if current < lower:
        signal_type = 'BUY'
    elif current > upper:
        signal_type = 'SELL'
    else:
        signal_type = 'NEUTRAL'

    return {
        'upper': round(upper, 2),
        'middle': round(mean, 2),
        'lower': round(lower, 2),
        'pct_b': round(pct_b, 3),
        'signal_type': signal_type,
    }


# ── Per-ticker sync calculation ───────────────────────────────────────────────

def _calc_signals_sync(ticker: str) -> Optional[Dict]:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='90d', interval='1d', timeout=5)
        if hist is None or len(hist) < 30:
            return None

        closes = list(hist['Close'])
        price = closes[-1]
        change_pct = round((closes[-1] - closes[-2]) / closes[-2] * 100, 2) if len(closes) >= 2 else 0.0

        macd_data = _calc_macd(closes)
        rsi_data = _calc_rsi(closes)
        bb_data = _calc_bollinger(closes)

        if not macd_data or not rsi_data or not bb_data:
            return None

        # Composite: count BUY / SELL signals across all 3 indicators
        # MACD BUY = 'BUY' (fresh cross below) or 'BELOW' (in buy territory)
        buy_count = sum([
            1 if macd_data['signal_type'] in ('BUY', 'BELOW') else 0,
            1 if rsi_data['signal_type'] == 'BUY' else 0,
            1 if bb_data['signal_type'] == 'BUY' else 0,
        ])
        sell_count = sum([
            1 if macd_data['signal_type'] in ('SELL', 'ABOVE') else 0,
            1 if rsi_data['signal_type'] == 'SELL' else 0,
            1 if bb_data['signal_type'] == 'SELL' else 0,
        ])
        fresh_buys = sum([
            1 if macd_data['signal_type'] == 'BUY' else 0,
            1 if rsi_data['signal_type'] == 'BUY' else 0,
            1 if bb_data['signal_type'] == 'BUY' else 0,
        ])
        fresh_sells = sum([
            1 if macd_data['signal_type'] == 'SELL' else 0,
            1 if rsi_data['signal_type'] == 'SELL' else 0,
            1 if bb_data['signal_type'] == 'SELL' else 0,
        ])

        if buy_count == 3:
            composite = 'STRONG BUY'
        elif buy_count == 2:
            composite = 'BUY'
        elif sell_count == 3:
            composite = 'STRONG SELL'
        elif sell_count == 2:
            composite = 'SELL'
        else:
            composite = 'NEUTRAL'

        return {
            'ticker': ticker,
            'sector': _SECTOR_MAP.get(ticker, ''),
            'price': round(price, 2),
            'change_pct': change_pct,
            'macd': macd_data,
            'rsi': rsi_data,
            'bb': bb_data,
            'buy_signals': buy_count,
            'sell_signals': sell_count,
            'fresh_buys': fresh_buys,
            'fresh_sells': fresh_sells,
            'composite': composite,
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


# ── Ticker universe ────────────────────────────────────────────────────────────

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
    """Get top-volume liquid US stocks from Finviz (avg vol > 1M)."""
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
        print(f"TechSignals: Finviz fetch failed: {e}")

    seen = set()
    result = []
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

class TechnicalSignalsService:

    async def scan(self) -> Dict:
        """
        Scan liquid US stocks for MACD/RSI/Bollinger Bands signals.
        Returns all stocks with signal data.
        Sort order: STRONG BUY > BUY > NEUTRAL > SELL > STRONG SELL,
        then by number of buy signals descending.
        """
        async with aiohttp.ClientSession() as session:
            tickers = await _get_liquid_tickers(session)

        print(f"TechSignals: scanning {len(tickers)} tickers...")

        sem = asyncio.Semaphore(4)
        loop = asyncio.get_running_loop()
        executor = ThreadPoolExecutor(max_workers=5)

        async def process_one(ticker: str) -> Optional[Dict]:
            async with sem:
                try:
                    return await asyncio.wait_for(
                        loop.run_in_executor(executor, _calc_signals_sync, ticker),
                        timeout=12
                    )
                except Exception:
                    return None

        tasks = [process_one(t) for t in tickers]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        executor.shutdown(wait=False)

        valid = [r for r in results if isinstance(r, dict)]
        print(f"TechSignals: {len(valid)} stocks processed")

        _order = {'STRONG BUY': 0, 'BUY': 1, 'NEUTRAL': 2, 'SELL': 3, 'STRONG SELL': 4}
        valid.sort(key=lambda x: (_order.get(x['composite'], 2), -x['buy_signals'], x['sell_signals']))

        return {
            'stocks': valid,
            'scanned': len(tickers),
            'count': len(valid),
            'generated_at': datetime.now().astimezone().isoformat(),
        }
