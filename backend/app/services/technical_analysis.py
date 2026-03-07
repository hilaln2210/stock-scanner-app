"""
Multi-indicator Technical Analysis Engine.

Computes a confluence-based technical signal per stock using two timeframes
(5-min for entry timing, 1-hour for trend direction) and 7 indicators +
candlestick pattern recognition.

Indicators (weighted):
  Trend     25%  — EMA 9/21 crossover, ADX
  Momentum  30%  — RSI 14, MACD histogram, Stochastic %K/%D
  Volatility 20% — Bollinger Bands position + squeeze
  Volume    15%  — VWAP, volume vs average
  Patterns  10%  — Engulfing, Hammer, Doji/Star

Output per ticker:
  tech_signal   — "Strong Buy" / "Buy" / "Neutral" / "Sell" / "Strong Sell"
  tech_score    — -100 … +100
  tech_detail   — human-readable breakdown
  tech_timing   — short-term timing prediction
  tech_patterns — detected candlestick patterns
"""

import time
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional

import numpy as np
import pandas as pd
import yfinance as yf

try:
    import pandas_ta as ta
    _HAS_TA = True
except ImportError:
    _HAS_TA = False

# ─── Cache ────────────────────────────────────────────────────────────────────
_TECH_CACHE: dict = {}       # {ticker: result_dict}
_TECH_CACHE_TIME: dict = {}  # {ticker: timestamp}
_TECH_CACHE_TTL = 60         # seconds


def compute_technicals(ticker: str) -> Optional[dict]:
    """
    Main entry point. Returns a dict with tech_signal, tech_score,
    tech_detail, tech_timing, tech_patterns — or None on failure.
    Results are cached for _TECH_CACHE_TTL seconds.
    """
    now = time.time()
    cached = _TECH_CACHE.get(ticker)
    if cached and (now - _TECH_CACHE_TIME.get(ticker, 0)) < _TECH_CACHE_TTL:
        return cached

    try:
        result = _compute(ticker)
        if result:
            _TECH_CACHE[ticker] = result
            _TECH_CACHE_TIME[ticker] = now
        return result
    except Exception as e:
        print(f"[TA] Error for {ticker}: {e}")
        traceback.print_exc()
        return _TECH_CACHE.get(ticker)


def _fetch_bars(ticker: str):
    """Fetch 5-min (7d) and 1-hour (30d) OHLCV bars from yfinance."""
    t = yf.Ticker(ticker)
    df_5m = t.history(period='5d', interval='5m', prepost=True, timeout=8)
    df_1h = t.history(period='1mo', interval='1h', prepost=True, timeout=8)
    return df_5m, df_1h


def _compute(ticker: str) -> Optional[dict]:
    """Core computation: fetch bars, calc indicators, produce signal."""
    if not _HAS_TA:
        return None

    df_5m, df_1h = _fetch_bars(ticker)

    if df_5m is None or len(df_5m) < 20:
        return None
    if df_1h is None or len(df_1h) < 20:
        return None

    ind_5m = _calc_indicators(df_5m)
    ind_1h = _calc_indicators(df_1h)
    patterns = _detect_patterns(df_5m)

    score, detail_parts = _confluence_signal(ind_5m, ind_1h, patterns)
    signal = _score_to_signal(score)
    timing_dual = _predict_timing_dual(ind_5m, ind_1h, patterns, score)

    pattern_names = [p['name'] for p in patterns]

    # Support / Resistance from recent price action
    sr = _calc_support_resistance(df_5m)

    return {
        'tech_signal': signal,
        'tech_score': round(score),
        'tech_detail': " | ".join(detail_parts),
        'tech_timing': timing_dual.get('summary', ''),
        'tech_timing_up': timing_dual.get('up', ''),
        'tech_timing_down': timing_dual.get('down', ''),
        'tech_timing_up_desc': timing_dual.get('up_desc', ''),
        'tech_timing_down_desc': timing_dual.get('down_desc', ''),
        'tech_timing_up_conf': timing_dual.get('up_confidence', ''),
        'tech_timing_down_conf': timing_dual.get('down_confidence', ''),
        'tech_timing_up_signals': timing_dual.get('up_signals', 0),
        'tech_timing_down_signals': timing_dual.get('down_signals', 0),
        'tech_patterns': ", ".join(pattern_names) if pattern_names else "",
        'tech_support': sr.get('support'),
        'tech_resistance': sr.get('resistance'),
        'tech_indicators': {
            'rsi_5m': round(ind_5m.get('rsi', 0), 1),
            'rsi_1h': round(ind_1h.get('rsi', 0), 1),
            'macd_hist_5m': round(ind_5m.get('macd_hist', 0), 4),
            'macd_hist_1h': round(ind_1h.get('macd_hist', 0), 4),
            'ema_cross_5m': ind_5m.get('ema_cross', 'neutral'),
            'ema_cross_1h': ind_1h.get('ema_cross', 'neutral'),
            'bb_position_5m': round(ind_5m.get('bb_pct', 0.5), 2),
            'adx_1h': round(ind_1h.get('adx', 0), 1),
            'stoch_k_5m': round(ind_5m.get('stoch_k', 50), 1),
            'vwap_bias': ind_5m.get('vwap_bias', 'neutral'),
            'bb_squeeze': ind_5m.get('bb_squeeze', False),
            'atr_pct_5m': round(ind_5m.get('atr_pct', 0), 2),
            'atr_pct_1h': round(ind_1h.get('atr_pct', 0), 2),
            'obv_trend': ind_5m.get('obv_trend', 'neutral'),
            'cci_5m': round(ind_5m.get('cci', 0), 1),
            'above_ema50_1h': ind_1h.get('above_ema50'),
            'above_ema200_1h': ind_1h.get('above_ema200'),
            'golden_cross_1h': ind_1h.get('golden_cross'),
        },
    }


# ─── Indicator Calculations ──────────────────────────────────────────────────

def _calc_indicators(df: pd.DataFrame) -> dict:
    """Calculate all technical indicators on a single timeframe DataFrame."""
    result = {}
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']

    # --- RSI 14 ---
    rsi = ta.rsi(close, length=14)
    result['rsi'] = float(rsi.iloc[-1]) if rsi is not None and len(rsi) > 0 and not pd.isna(rsi.iloc[-1]) else 50.0

    # --- MACD (12, 26, 9) ---
    macd_df = ta.macd(close, fast=12, slow=26, signal=9)
    if macd_df is not None and len(macd_df) > 0:
        hist_col = [c for c in macd_df.columns if 'h' in c.lower() or 'hist' in c.lower()]
        if hist_col:
            h = macd_df[hist_col[0]]
            result['macd_hist'] = float(h.iloc[-1]) if not pd.isna(h.iloc[-1]) else 0.0
            result['macd_hist_prev'] = float(h.iloc[-2]) if len(h) > 1 and not pd.isna(h.iloc[-2]) else 0.0
        else:
            result['macd_hist'] = 0.0
            result['macd_hist_prev'] = 0.0
        macd_col = [c for c in macd_df.columns if 'macd' in c.lower() and 'h' not in c.lower() and 's' not in c.lower()]
        signal_col = [c for c in macd_df.columns if 's' in c.lower()]
        if macd_col and signal_col:
            result['macd_line'] = float(macd_df[macd_col[0]].iloc[-1]) if not pd.isna(macd_df[macd_col[0]].iloc[-1]) else 0.0
            result['macd_signal'] = float(macd_df[signal_col[0]].iloc[-1]) if not pd.isna(macd_df[signal_col[0]].iloc[-1]) else 0.0
    else:
        result['macd_hist'] = 0.0
        result['macd_hist_prev'] = 0.0

    # --- EMA 9 / 21 crossover ---
    ema9 = ta.ema(close, length=9)
    ema21 = ta.ema(close, length=21)
    if ema9 is not None and ema21 is not None and len(ema9) > 1 and len(ema21) > 1:
        cur9, cur21 = float(ema9.iloc[-1]), float(ema21.iloc[-1])
        prev9, prev21 = float(ema9.iloc[-2]), float(ema21.iloc[-2])
        if not (pd.isna(cur9) or pd.isna(cur21)):
            if cur9 > cur21:
                result['ema_cross'] = 'bullish'
                if prev9 <= prev21:
                    result['ema_cross'] = 'bullish_crossover'
            else:
                result['ema_cross'] = 'bearish'
                if prev9 >= prev21:
                    result['ema_cross'] = 'bearish_crossover'
            result['ema9'] = cur9
            result['ema21'] = cur21
        else:
            result['ema_cross'] = 'neutral'
    else:
        result['ema_cross'] = 'neutral'

    # --- ADX ---
    adx_df = ta.adx(high, low, close, length=14)
    if adx_df is not None and len(adx_df) > 0:
        adx_col = [c for c in adx_df.columns if 'adx' in c.lower() and 'dm' not in c.lower()]
        if adx_col:
            result['adx'] = float(adx_df[adx_col[0]].iloc[-1]) if not pd.isna(adx_df[adx_col[0]].iloc[-1]) else 0.0
        else:
            result['adx'] = 0.0
    else:
        result['adx'] = 0.0

    # --- Bollinger Bands (20, 2) ---
    bb = ta.bbands(close, length=20, std=2)
    if bb is not None and len(bb) > 0:
        lower_col = [c for c in bb.columns if 'l' in c.lower() and 'b' in c.lower()]
        upper_col = [c for c in bb.columns if 'u' in c.lower() and 'b' in c.lower()]
        mid_col = [c for c in bb.columns if 'm' in c.lower() and 'b' in c.lower()]
        bw_col = [c for c in bb.columns if 'bw' in c.lower() or 'bandwidth' in c.lower()]

        price = float(close.iloc[-1])
        if lower_col and upper_col:
            lb = float(bb[lower_col[0]].iloc[-1]) if not pd.isna(bb[lower_col[0]].iloc[-1]) else price
            ub = float(bb[upper_col[0]].iloc[-1]) if not pd.isna(bb[upper_col[0]].iloc[-1]) else price
            band_range = ub - lb if ub != lb else 1.0
            result['bb_pct'] = (price - lb) / band_range
            result['bb_upper'] = ub
            result['bb_lower'] = lb
        else:
            result['bb_pct'] = 0.5

        if bw_col:
            bw_series = bb[bw_col[0]].dropna()
            if len(bw_series) >= 5:
                avg_bw = bw_series.iloc[-20:].mean() if len(bw_series) >= 20 else bw_series.mean()
                cur_bw = float(bw_series.iloc[-1])
                result['bb_squeeze'] = cur_bw < avg_bw * 0.75
                result['bb_bandwidth'] = cur_bw
            else:
                result['bb_squeeze'] = False
        else:
            result['bb_squeeze'] = False
    else:
        result['bb_pct'] = 0.5
        result['bb_squeeze'] = False

    # --- Stochastic (14, 3, 3) ---
    stoch = ta.stoch(high, low, close, k=14, d=3, smooth_k=3)
    if stoch is not None and len(stoch) > 0:
        k_col = [c for c in stoch.columns if 'k' in c.lower()]
        d_col = [c for c in stoch.columns if 'd' in c.lower()]
        result['stoch_k'] = float(stoch[k_col[0]].iloc[-1]) if k_col and not pd.isna(stoch[k_col[0]].iloc[-1]) else 50.0
        result['stoch_d'] = float(stoch[d_col[0]].iloc[-1]) if d_col and not pd.isna(stoch[d_col[0]].iloc[-1]) else 50.0
    else:
        result['stoch_k'] = 50.0
        result['stoch_d'] = 50.0

    # --- VWAP ---
    try:
        vwap = ta.vwap(high, low, close, volume)
        if vwap is not None and len(vwap) > 0 and not pd.isna(vwap.iloc[-1]):
            price = float(close.iloc[-1])
            vwap_val = float(vwap.iloc[-1])
            result['vwap'] = vwap_val
            result['vwap_bias'] = 'bullish' if price > vwap_val else 'bearish'
        else:
            result['vwap_bias'] = 'neutral'
    except Exception:
        result['vwap_bias'] = 'neutral'

    # --- Volume ratio ---
    if len(volume) >= 20:
        avg_vol = float(volume.iloc[-20:].mean())
        cur_vol = float(volume.iloc[-1])
        result['vol_ratio'] = cur_vol / avg_vol if avg_vol > 0 else 1.0
    else:
        result['vol_ratio'] = 1.0

    # --- ATR 14 ---
    try:
        atr_series = ta.atr(high, low, close, length=14)
        if atr_series is not None and len(atr_series) > 0 and not pd.isna(atr_series.iloc[-1]):
            atr_val = float(atr_series.iloc[-1])
            price = float(close.iloc[-1])
            result['atr'] = atr_val
            result['atr_pct'] = round((atr_val / price * 100), 2) if price > 0 else 0.0
        else:
            result['atr'] = 0.0
            result['atr_pct'] = 0.0
    except Exception:
        result['atr'] = 0.0
        result['atr_pct'] = 0.0

    # --- EMA 50 / 200 (long-term trend context) ---
    try:
        price = float(close.iloc[-1])
        ema50 = ta.ema(close, length=50)
        ema200 = ta.ema(close, length=200)
        e50 = float(ema50.iloc[-1]) if ema50 is not None and len(ema50) > 0 and not pd.isna(ema50.iloc[-1]) else None
        e200 = float(ema200.iloc[-1]) if ema200 is not None and len(ema200) > 0 and not pd.isna(ema200.iloc[-1]) else None
        result['ema50'] = e50
        result['ema200'] = e200
        result['above_ema50'] = (price > e50) if e50 else None
        result['above_ema200'] = (price > e200) if e200 else None
        result['golden_cross'] = (e50 > e200) if (e50 and e200) else None
    except Exception:
        result['ema50'] = None
        result['ema200'] = None
        result['above_ema50'] = None
        result['above_ema200'] = None
        result['golden_cross'] = None

    # --- OBV trend (accumulation vs distribution) ---
    try:
        obv = ta.obv(close, volume)
        if obv is not None and len(obv) >= 20:
            obv_sma = float(obv.iloc[-20:].mean())
            obv_cur = float(obv.iloc[-1])
            result['obv_trend'] = 'rising' if obv_cur > obv_sma else 'falling'
        else:
            result['obv_trend'] = 'neutral'
    except Exception:
        result['obv_trend'] = 'neutral'

    # --- CCI 20 (extremes detector) — manual impl: pandas_ta CCI has a precision bug on tight bars ---
    try:
        if len(close) >= 20:
            tp = (high + low + close) / 3
            tp_s = tp.iloc[-20:]
            sma_tp = float(tp_s.mean())
            mad = float(np.mean(np.abs(tp_s.values - sma_tp)))
            result['cci'] = round((float(tp.iloc[-1]) - sma_tp) / (0.015 * mad), 1) if mad > 1e-8 else 0.0
        else:
            result['cci'] = 0.0
    except Exception:
        result['cci'] = 0.0

    return result


# ─── Candlestick Pattern Detection ──────────────────────────────────────────

def _detect_patterns(df: pd.DataFrame) -> list:
    """Detect major candlestick patterns on the last few bars."""
    patterns_found = []
    if len(df) < 3:
        return patterns_found

    o = df['Open'].values
    h = df['High'].values
    l = df['Low'].values
    c = df['Close'].values

    c1_open, c1_high, c1_low, c1_close = o[-2], h[-2], l[-2], c[-2]
    c2_open, c2_high, c2_low, c2_close = o[-1], h[-1], l[-1], c[-1]

    body1 = c1_close - c1_open
    body2 = c2_close - c2_open
    range2 = c2_high - c2_low if c2_high != c2_low else 0.01

    # Bullish Engulfing
    if body1 < 0 and body2 > 0 and c2_open <= c1_close and c2_close >= c1_open:
        patterns_found.append({'name': 'Bullish Engulfing', 'direction': 1, 'strength': 0.8})

    # Bearish Engulfing
    if body1 > 0 and body2 < 0 and c2_open >= c1_close and c2_close <= c1_open:
        patterns_found.append({'name': 'Bearish Engulfing', 'direction': -1, 'strength': 0.8})

    # Hammer (bullish reversal)
    lower_shadow = min(c2_open, c2_close) - c2_low
    upper_shadow = c2_high - max(c2_open, c2_close)
    body_size = abs(body2)
    if body_size > 0 and lower_shadow >= body_size * 2 and upper_shadow <= body_size * 0.5:
        patterns_found.append({'name': 'Hammer', 'direction': 1, 'strength': 0.6})

    # Shooting Star (bearish reversal)
    if body_size > 0 and upper_shadow >= body_size * 2 and lower_shadow <= body_size * 0.5:
        patterns_found.append({'name': 'Shooting Star', 'direction': -1, 'strength': 0.6})

    # Doji (indecision)
    if range2 > 0 and body_size / range2 < 0.1:
        patterns_found.append({'name': 'Doji', 'direction': 0, 'strength': 0.4})

    # Morning Star (3-candle bullish)
    if len(df) >= 4:
        c0_open, c0_close = o[-3], c[-3]
        body0 = c0_close - c0_open
        if body0 < 0 and abs(body1) < abs(body0) * 0.3 and body2 > 0 and c2_close > (c0_open + c0_close) / 2:
            patterns_found.append({'name': 'Morning Star', 'direction': 1, 'strength': 0.9})

    # Evening Star (3-candle bearish)
    if len(df) >= 4:
        c0_open, c0_close = o[-3], c[-3]
        body0 = c0_close - c0_open
        if body0 > 0 and abs(body1) < abs(body0) * 0.3 and body2 < 0 and c2_close < (c0_open + c0_close) / 2:
            patterns_found.append({'name': 'Evening Star', 'direction': -1, 'strength': 0.9})

    return patterns_found


# ─── Confluence Signal ────────────────────────────────────────────────────────

def _confluence_signal(ind_5m: dict, ind_1h: dict, patterns: list) -> tuple:
    """
    Weighted multi-factor scoring.
    Returns (score: float, detail_parts: list[str]).
    Score ranges from -100 to +100.
    """
    score = 0.0
    details = []

    # ── Trend (25%) — based on 1h timeframe ──
    trend_score = 0.0
    ema_1h = ind_1h.get('ema_cross', 'neutral')
    adx_1h = ind_1h.get('adx', 0)

    if 'bullish' in ema_1h:
        trend_score += 60
        details.append(f"EMA 1h: שורי{'↗' if 'crossover' in ema_1h else ''}")
    elif 'bearish' in ema_1h:
        trend_score -= 60
        details.append(f"EMA 1h: דובי{'↘' if 'crossover' in ema_1h else ''}")
    else:
        details.append("EMA 1h: ניטרלי")

    if adx_1h > 25:
        trend_score *= 1.3
        details.append(f"ADX {adx_1h:.0f} (מגמה חזקה)")
    elif adx_1h < 15:
        trend_score *= 0.5
        details.append(f"ADX {adx_1h:.0f} (אין מגמה)")

    # EMA 50/200 long-term context — bonus/penalty on top of EMA9/21
    above_ema50 = ind_1h.get('above_ema50')
    above_ema200 = ind_1h.get('above_ema200')
    golden_cross = ind_1h.get('golden_cross')
    if above_ema50 is True and above_ema200 is True:
        trend_score += 20
        details.append("מעל EMA50/200 ✓")
    elif above_ema50 is False and above_ema200 is False:
        trend_score -= 20
        details.append("מתחת EMA50/200 ✗")
    elif above_ema50 is True:
        trend_score += 10
        details.append("מעל EMA50")
    if golden_cross is True:
        trend_score += 8
        details.append("Golden Cross 🟡")
    elif golden_cross is False:
        trend_score -= 8
        details.append("Death Cross 💀")

    score += trend_score * 0.25

    # ── Momentum (30%) — 5m for timing, 1h for confirmation ──
    momentum_score = 0.0

    rsi_5m = ind_5m.get('rsi', 50)
    if rsi_5m > 70:
        momentum_score -= 40
        details.append(f"RSI 5m: {rsi_5m:.0f} (קניית יתר)")
    elif rsi_5m < 30:
        momentum_score += 40
        details.append(f"RSI 5m: {rsi_5m:.0f} (מכירת יתר)")
    elif rsi_5m > 55:
        momentum_score += 20
        details.append(f"RSI 5m: {rsi_5m:.0f} (שורי)")
    elif rsi_5m < 45:
        momentum_score -= 20
        details.append(f"RSI 5m: {rsi_5m:.0f} (דובי)")
    else:
        details.append(f"RSI 5m: {rsi_5m:.0f}")

    rsi_1h = ind_1h.get('rsi', 50)
    if rsi_1h > 55:
        momentum_score += 10
    elif rsi_1h < 45:
        momentum_score -= 10

    macd_h = ind_5m.get('macd_hist', 0)
    macd_h_prev = ind_5m.get('macd_hist_prev', 0)
    if macd_h > 0:
        momentum_score += 25
        if macd_h > macd_h_prev:
            momentum_score += 10
            details.append("MACD: חיובי ↑")
        else:
            details.append("MACD: חיובי ↓")
    elif macd_h < 0:
        momentum_score -= 25
        if macd_h < macd_h_prev:
            momentum_score -= 10
            details.append("MACD: שלילי ↓")
        else:
            details.append("MACD: שלילי ↑")

    stoch_k = ind_5m.get('stoch_k', 50)
    stoch_d = ind_5m.get('stoch_d', 50)
    if stoch_k > 80:
        momentum_score -= 15
    elif stoch_k < 20:
        momentum_score += 15
    if stoch_k > stoch_d and stoch_k < 50:
        momentum_score += 10
    elif stoch_k < stoch_d and stoch_k > 50:
        momentum_score -= 10

    # CCI — catches extremes RSI can miss (>150 overbought, <-150 oversold)
    cci = ind_5m.get('cci', 0)
    if cci > 200:
        momentum_score -= 25
        details.append(f"CCI {cci:.0f} (קיצוני-קניית יתר)")
    elif cci > 100:
        momentum_score -= 12
        details.append(f"CCI {cci:.0f} (קניית יתר)")
    elif cci < -200:
        momentum_score += 25
        details.append(f"CCI {cci:.0f} (קיצוני-מכירת יתר)")
    elif cci < -100:
        momentum_score += 12
        details.append(f"CCI {cci:.0f} (מכירת יתר)")

    score += momentum_score * 0.30

    # ── Volatility (20%) — 5m ──
    vol_score = 0.0
    bb_pct = ind_5m.get('bb_pct', 0.5)
    bb_squeeze = ind_5m.get('bb_squeeze', False)

    if bb_pct < 0.2:
        vol_score += 30
        details.append("BB: קרוב לרצפה (קנייה)")
    elif bb_pct > 0.8:
        vol_score -= 30
        details.append("BB: קרוב לתקרה (מכירה)")
    else:
        details.append(f"BB: {bb_pct:.0%} מהטווח")

    if bb_squeeze:
        vol_score += 5
        details.append("BB Squeeze: פריצה צפויה!")

    # ATR regime: high ATR amplifies directional signals; low ATR + squeeze = coiled spring
    atr_pct_1h = ind_1h.get('atr_pct', 0)
    if atr_pct_1h > 4:
        # Highly volatile stock — oversold bounces are larger, overbought drops steeper
        if bb_pct < 0.35:
            vol_score += 10
            details.append(f"ATR {atr_pct_1h:.1f}% תנודתי+נמוך ✓")
        elif bb_pct > 0.65:
            vol_score -= 10
            details.append(f"ATR {atr_pct_1h:.1f}% תנודתי+גבוה ✗")
        else:
            details.append(f"ATR {atr_pct_1h:.1f}% (תנודתי)")
    elif 0 < atr_pct_1h < 1.5:
        # Low volatility / compression — squeeze breakouts are more explosive
        if bb_squeeze:
            vol_score += 8
            details.append(f"ATR {atr_pct_1h:.1f}% לחץ+Squeeze ⚡")
        else:
            details.append(f"ATR {atr_pct_1h:.1f}% (שקט)")
    elif atr_pct_1h >= 1.5:
        details.append(f"ATR {atr_pct_1h:.1f}%")

    score += vol_score * 0.20

    # ── Volume (15%) — 5m ──
    volume_score = 0.0
    vwap_bias = ind_5m.get('vwap_bias', 'neutral')
    vol_ratio = ind_5m.get('vol_ratio', 1.0)

    if vwap_bias == 'bullish':
        volume_score += 30
        details.append("VWAP: מעל (שורי)")
    elif vwap_bias == 'bearish':
        volume_score -= 30
        details.append("VWAP: מתחת (דובי)")

    if vol_ratio > 2.0:
        volume_score += 20
        details.append(f"ווליום: x{vol_ratio:.1f} (מטורף)")
    elif vol_ratio > 1.5:
        volume_score += 10
    elif vol_ratio < 0.5:
        volume_score -= 10

    # OBV trend — confirms or contradicts price direction
    obv_trend = ind_5m.get('obv_trend', 'neutral')
    if obv_trend == 'rising' and vwap_bias == 'bullish':
        volume_score += 15
        details.append("OBV↑ + VWAP שורי (אקומולציה)")
    elif obv_trend == 'rising':
        volume_score += 8
        details.append("OBV↑ (אקומולציה)")
    elif obv_trend == 'falling' and vwap_bias == 'bearish':
        volume_score -= 15
        details.append("OBV↓ + VWAP דובי (דיסטריביושן)")
    elif obv_trend == 'falling':
        volume_score -= 8
        details.append("OBV↓ (דיסטריביושן)")

    score += volume_score * 0.15

    # ── Candlestick Patterns (10%) ──
    pattern_score = 0.0
    for p in patterns:
        pattern_score += p['direction'] * p['strength'] * 50
    if patterns:
        names = ", ".join(p['name'] for p in patterns)
        details.append(f"נרות: {names}")

    score += pattern_score * 0.10

    score = max(-100, min(100, score))
    return score, details


# ─── Signal Label ─────────────────────────────────────────────────────────────

def _score_to_signal(score: float) -> str:
    if score >= 40:
        return "Strong Buy"
    elif score >= 15:
        return "Buy"
    elif score > -15:
        return "Neutral"
    elif score > -40:
        return "Sell"
    else:
        return "Strong Sell"


# ─── Support / Resistance Calculation ─────────────────────────────────────────

def _calc_support_resistance(df: pd.DataFrame) -> dict:
    """Calculate nearest support and resistance from recent price pivots."""
    result = {'support': None, 'resistance': None}
    if df is None or len(df) < 10:
        return result

    close = df['Close'].values
    high = df['High'].values
    low = df['Low'].values
    current = float(close[-1])

    pivot_highs = []
    pivot_lows = []
    window = 5

    for i in range(window, len(df) - window):
        if high[i] == max(high[i - window:i + window + 1]):
            pivot_highs.append(float(high[i]))
        if low[i] == min(low[i - window:i + window + 1]):
            pivot_lows.append(float(low[i]))

    # BB bands as extra levels
    bb = ta.bbands(pd.Series(close), length=20, std=2) if _HAS_TA and len(close) >= 20 else None
    if bb is not None and len(bb) > 0:
        lower_col = [c for c in bb.columns if 'l' in c.lower() and 'b' in c.lower()]
        upper_col = [c for c in bb.columns if 'u' in c.lower() and 'b' in c.lower()]
        if lower_col:
            val = float(bb[lower_col[0]].iloc[-1])
            if not pd.isna(val):
                pivot_lows.append(val)
        if upper_col:
            val = float(bb[upper_col[0]].iloc[-1])
            if not pd.isna(val):
                pivot_highs.append(val)

    supports = sorted([p for p in pivot_lows if p < current], reverse=True)
    resistances = sorted([p for p in pivot_highs if p > current])

    if supports:
        result['support'] = round(supports[0], 2)
    if resistances:
        result['resistance'] = round(resistances[0], 2)

    return result


# ─── Time Estimation Helpers ─────────────────────────────────────────────────

_IL_TZ = timezone(timedelta(hours=3))   # IDT (summer) — Israel is ~7h ahead of ET year-round
_ET_TZ = timezone(timedelta(hours=-4))  # EDT


def _il_now():
    """Current time in Israel (IDT UTC+3 / IST UTC+2). Using +3 for trading season."""
    return datetime.now(timezone.utc).astimezone(_IL_TZ)


def _market_close_il():
    """NYSE closes 16:00 ET = 23:00 Israel time."""
    return 23


def _narrow_window(base_min: int, base_max: int, adx: float, vol_ratio: float, rsi: float) -> tuple:
    """Tighten the time window when signals are strong and clear."""
    factor = 1.0
    if adx > 35:
        factor *= 0.7
    elif adx > 25:
        factor *= 0.85
    if vol_ratio > 2.5:
        factor *= 0.7
    elif vol_ratio > 1.5:
        factor *= 0.85
    if rsi > 70 or rsi < 30:
        factor *= 0.8
    narrowed_min = max(3, int(base_min * factor))
    narrowed_max = max(narrowed_min + 10, int(base_max * factor))
    return narrowed_min, narrowed_max


def _fmt_time_range_il(minutes_min: int, minutes_max: int) -> str:
    """Format a time range in Israel time."""
    now = _il_now()
    t_start = now + timedelta(minutes=minutes_min)
    t_end = now + timedelta(minutes=minutes_max)
    close_h = _market_close_il()
    if t_start.hour >= close_h:
        return "לאחר סגירת השוק"
    end_h = t_end.hour if t_end.hour < close_h else close_h
    end_m = t_end.minute if t_end.hour < close_h else 0
    return f"{t_start.hour:02d}:{t_start.minute:02d}-{end_h:02d}:{end_m:02d} 🇮🇱"


def _breakout_confidence(score: float, vol_ratio: float, adx: float) -> str:
    """Confidence label for the breakout estimate."""
    c = 0
    if abs(score) > 40:
        c += 2
    elif abs(score) > 20:
        c += 1
    if vol_ratio > 2.0:
        c += 2
    elif vol_ratio > 1.5:
        c += 1
    if adx > 30:
        c += 1
    if c >= 4:
        return "ביטחון גבוה 🔥"
    if c >= 2:
        return "ביטחון בינוני"
    return "ביטחון נמוך"


# ─── Timing Prediction ──────────────────────────────────────────────────────

def _predict_timing(ind_5m: dict, ind_1h: dict, patterns: list, score: float) -> str:
    """Legacy wrapper — returns combined summary string."""
    result = _predict_timing_dual(ind_5m, ind_1h, patterns, score)
    return result.get('summary', '⏳')


def _predict_timing_dual(ind_5m: dict, ind_1h: dict, patterns: list, score: float) -> dict:
    """
    Always returns BOTH up and down timing for every stock.
    Returns dict: { up, down, summary, up_confidence, down_confidence }
    """
    rsi_5m = ind_5m.get('rsi', 50)
    rsi_1h = ind_1h.get('rsi', 50)
    macd_h = ind_5m.get('macd_hist', 0)
    macd_h_prev = ind_5m.get('macd_hist_prev', 0)
    bb_squeeze = ind_5m.get('bb_squeeze', False)
    bb_pct = ind_5m.get('bb_pct', 0.5)
    adx_1h = ind_1h.get('adx', 0)
    ema_1h = ind_1h.get('ema_cross', 'neutral')
    vwap = ind_5m.get('vwap_bias', 'neutral')
    vol_ratio = ind_5m.get('vol_ratio', 1.0)
    stoch_k = ind_5m.get('stoch_k', 50)
    stoch_d = ind_5m.get('stoch_d', 50)

    bullish_patterns = [p for p in patterns if p['direction'] > 0]
    bearish_patterns = [p for p in patterns if p['direction'] < 0]

    def _tw(base_min, base_max):
        mn, mx = _narrow_window(base_min, base_max, adx_1h, vol_ratio, rsi_5m)
        return _fmt_time_range_il(mn, mx)

    def _tw_raw(base_min, base_max):
        mn, mx = _narrow_window(base_min, base_max, adx_1h, vol_ratio, rsi_5m)
        return mn, mx

    # ── Compute UP (rise) timing ──────────────────────────────────────────
    up_signals = 0
    up_base_min, up_base_max = 30, 120  # default wide window

    if rsi_5m < 30:
        up_signals += 3
        up_base_min, up_base_max = min(up_base_min, 5), min(up_base_max, 40)
    elif rsi_5m < 40:
        up_signals += 2
        up_base_min, up_base_max = min(up_base_min, 10), min(up_base_max, 55)
    elif rsi_5m < 50:
        up_signals += 1

    if macd_h > 0 and macd_h > macd_h_prev:
        up_signals += 2
        up_base_min, up_base_max = min(up_base_min, 10), min(up_base_max, 60)
    elif macd_h > 0:
        up_signals += 1

    if 'bullish' in ema_1h:
        up_signals += 2
        up_base_min, up_base_max = min(up_base_min, 15), min(up_base_max, 75)

    if vwap == 'bullish':
        up_signals += 1
        up_base_min = min(up_base_min, 15)

    if bb_pct < 0.2:
        up_signals += 2
        up_base_min, up_base_max = min(up_base_min, 8), min(up_base_max, 50)

    if bb_squeeze and score > 0:
        up_signals += 3
        up_base_min, up_base_max = min(up_base_min, 3), min(up_base_max, 25)

    if stoch_k < 20:
        up_signals += 2
        up_base_min, up_base_max = min(up_base_min, 8), min(up_base_max, 50)
    elif stoch_k < 40 and stoch_k > stoch_d:
        up_signals += 1

    if vol_ratio > 2.0 and score > 0:
        up_signals += 1
        up_base_min = min(up_base_min, 5)

    for p in bullish_patterns:
        up_signals += 2
        up_base_min, up_base_max = min(up_base_min, 10), min(up_base_max, 60)

    # ── Compute DOWN (decline) timing ─────────────────────────────────────
    down_signals = 0
    down_base_min, down_base_max = 30, 120

    if rsi_5m > 70:
        down_signals += 3
        down_base_min, down_base_max = min(down_base_min, 5), min(down_base_max, 40)
    elif rsi_5m > 60:
        down_signals += 2
        down_base_min, down_base_max = min(down_base_min, 10), min(down_base_max, 55)
    elif rsi_5m > 50:
        down_signals += 1

    if macd_h < 0 and macd_h < macd_h_prev:
        down_signals += 2
        down_base_min, down_base_max = min(down_base_min, 10), min(down_base_max, 60)
    elif macd_h < 0:
        down_signals += 1

    if 'bearish' in ema_1h:
        down_signals += 2
        down_base_min, down_base_max = min(down_base_min, 15), min(down_base_max, 75)

    if vwap == 'bearish':
        down_signals += 1
        down_base_min = min(down_base_min, 15)

    if bb_pct > 0.8:
        down_signals += 2
        down_base_min, down_base_max = min(down_base_min, 8), min(down_base_max, 50)

    if bb_squeeze and score < 0:
        down_signals += 3
        down_base_min, down_base_max = min(down_base_min, 3), min(down_base_max, 25)

    if stoch_k > 80:
        down_signals += 2
        down_base_min, down_base_max = min(down_base_min, 8), min(down_base_max, 50)
    elif stoch_k > 60 and stoch_k < stoch_d:
        down_signals += 1

    if vol_ratio > 2.0 and score < 0:
        down_signals += 1
        down_base_min = min(down_base_min, 5)

    for p in bearish_patterns:
        down_signals += 2
        down_base_min, down_base_max = min(down_base_min, 10), min(down_base_max, 60)

    # ── Confidence based on signal count ──────────────────────────────────
    def _conf_label(signals):
        if signals >= 8:
            return "גבוה מאוד 🔥🔥"
        if signals >= 5:
            return "גבוה 🔥"
        if signals >= 3:
            return "בינוני"
        return "נמוך"

    up_conf = _conf_label(up_signals)
    down_conf = _conf_label(down_signals)

    # Get raw minute windows (from now)
    up_mn, up_mx = _tw_raw(up_base_min, up_base_max)
    down_mn, down_mx = _tw_raw(down_base_min, down_base_max)

    # Enforce NO overlap: secondary window always starts AFTER primary ends + gap
    gap_min = 15  # minutes between "up phase" and "down phase"
    primary_is_up = score > 0 or up_signals >= down_signals

    if primary_is_up:
        # Primary = UP. UP stays; DOWN must start strictly after UP ends.
        up_time = _fmt_time_range_il(up_mn, up_mx)
        down_start = max(down_mn, up_mx + gap_min)  # no overlap: down_start >= up_mx + gap
        down_duration = max(20, down_mx - down_mn)
        down_end = down_start + down_duration
        down_time = _fmt_time_range_il(down_start, down_end)
    else:
        # Primary = DOWN. DOWN stays; UP must start strictly after DOWN ends.
        down_time = _fmt_time_range_il(down_mn, down_mx)
        up_start = max(up_mn, down_mx + gap_min)  # no overlap: up_start >= down_mx + gap
        up_duration = max(20, up_mx - up_mn)
        up_end = up_start + up_duration
        up_time = _fmt_time_range_il(up_start, up_end)

    # ── Build UP description ──────────────────────────────────────────────
    up_reasons = []
    if rsi_5m < 30:
        up_reasons.append(f"RSI {rsi_5m:.0f} מכירת יתר")
    elif rsi_5m < 45:
        up_reasons.append(f"RSI {rsi_5m:.0f} נמוך")
    if macd_h > 0 and macd_h > macd_h_prev:
        up_reasons.append("MACD חיובי ↑")
    if 'bullish' in ema_1h:
        up_reasons.append("EMA שורי")
    if bb_squeeze and score > 0:
        up_reasons.append("BB Squeeze")
    if bullish_patterns:
        up_reasons.append(", ".join(p['name'] for p in bullish_patterns))
    if stoch_k < 20:
        up_reasons.append("Stoch oversold")
    up_desc = " · ".join(up_reasons[:3]) if up_reasons else "מומנטום כללי"

    # ── Build DOWN description ────────────────────────────────────────────
    down_reasons = []
    if rsi_5m > 70:
        down_reasons.append(f"RSI {rsi_5m:.0f} קניית יתר")
    elif rsi_5m > 55:
        down_reasons.append(f"RSI {rsi_5m:.0f} גבוה")
    if macd_h < 0 and macd_h < macd_h_prev:
        down_reasons.append("MACD שלילי ↓")
    if 'bearish' in ema_1h:
        down_reasons.append("EMA דובי")
    if bb_squeeze and score < 0:
        down_reasons.append("BB Squeeze")
    if bearish_patterns:
        down_reasons.append(", ".join(p['name'] for p in bearish_patterns))
    if stoch_k > 80:
        down_reasons.append("Stoch overbought")
    down_desc = " · ".join(down_reasons[:3]) if down_reasons else "תיקון טבעי"

    # ── Summary (legacy field) ────────────────────────────────────────────
    if bb_squeeze and adx_1h > 20 and vol_ratio > 1.3:
        direction = "למעלה 🚀" if score > 0 else "למטה 📉"
        summary = f"⚡ פריצה צפויה {direction} | {up_time if score > 0 else down_time}"
    elif up_signals >= 5 and up_signals > down_signals:
        summary = f"📈 עלייה חזקה צפויה | {up_time} | {up_conf}"
    elif down_signals >= 5 and down_signals > up_signals:
        summary = f"📉 ירידה צפויה | {down_time} | {down_conf}"
    elif score > 20:
        summary = f"📈 מומנטום חיובי | {up_time}"
    elif score < -20:
        summary = f"📉 מומנטום שלילי | {down_time}"
    else:
        summary = f"⏳ ניטרלי | עלייה: {up_time} | ירידה: {down_time}"

    return {
        'up': up_time,
        'down': down_time,
        'up_desc': up_desc,
        'down_desc': down_desc,
        'up_confidence': up_conf,
        'down_confidence': down_conf,
        'up_signals': up_signals,
        'down_signals': down_signals,
        'summary': summary,
    }
