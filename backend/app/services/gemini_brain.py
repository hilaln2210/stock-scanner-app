"""
AI Brain v5 — Monster trading intelligence with multi-provider AI.

Providers (in priority order):
  1. Groq (Llama 3.3 70B — ultra-fast, free)
  2. Gemini (Google — free fallback)
  3. Rule-based engine (always available)

Features:
  - 12 intelligence modules (TTM Squeeze, DTC, Momentum Accel, ATR Stops, etc.)
  - Market regime detection (trending / volatile / ranging)
  - Sector rotation tracking (prefer hot sectors)
  - News sentiment analysis (keyword-based NLP)
  - Smart exit intelligence (time decay, momentum fade, reversal detection)
  - Multi-timeframe trend confirmation (SMA20/50/200 alignment)
  - Volatility-adjusted position sizing
  - Adaptive learning from past trades
"""
import json
import aiohttp
import math
import re
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path
from collections import Counter

from groq import Groq, APIError as GroqAPIError
from app.config import settings

LEARNING_FILE = Path(__file__).parent.parent.parent / "data" / "ai_learning.json"
REGIME_FILE = Path(__file__).parent.parent.parent / "data" / "market_regime.json"

# ─── Gemini Prompt ────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a MONSTER AI trading brain managing a $3,000 virtual demo portfolio.
You combine 12 intelligence modules for maximum alpha extraction.

CORE STRATEGY: SQUEEZE + BREAKOUT HUNTER (v5)

MODULE 1 — TTM SQUEEZE (weight ×1.5):
- Detects price compression (low ATR + tight SMA20) BEFORE breakout
- "Squeeze Firing" = the most explosive signal — BB expanding outside KC
- ALWAYS flag stocks where TTM state = 'firing'

MODULE 2 — DAYS TO COVER (weight ×1.4):
- Short Ratio > 7 days = EXTREME squeeze pressure (shorts trapped)
- DTC × Short Float combo = strongest squeeze predictor
- Example: DTC 8 + Short 25% = 🔥 Monster pressure

MODULE 3 — MOMENTUM ACCELERATION (weight ×1.3):
- chg_5m > chg_10m > chg_30m = move is ACCELERATING (enter now)
- chg_5m < chg_10m < chg_30m = move is FADING (avoid/exit)
- Fresh 5min surge > 2% = breakout happening NOW

MODULE 4 — ATR-BASED TRAILING STOPS:
- Stops adapt to each stock's volatility (ATR × 2)
- Volatile stock gets wider stops (avoids whipsaw)
- Tight stock gets tighter stops (protects gains)

MODULE 5 — SHORT SQUEEZE (weight ×1.8):
- High Short Float (>15%) + Rising Price + High Volume = SQUEEZE
- 🔥🔥🔥 MONSTER COMBO: TTM Firing + High Short + Acceleration = ×1.4 total bonus

ADDITIONAL MODULES: Momentum, Fundamentals, Catalysts, Regime, Sentiment, Trend, Smart Exits

{strategy_params}

MARKET REGIME: {market_regime}
HOT SECTORS: {hot_sectors}

RISK RULES:
- Max 15% of portfolio per position — focused, disciplined sizing
- Stop loss: 3-5% TIGHT — cut losses fast, protect capital
- Max 5 open positions at a time
- No trading if daily loss exceeds 8%
- Target: 10-15% default, up to 25% for high-conviction squeeze setups
- ONLY trade high-liquidity stocks: NVDA, AMD, TSLA, META, MSTR, COIN, PLTR, IONQ, RGTI, RKLB, HIMS, SOFI, HOOD, SOUN, UPST etc.
- NEVER recommend low-volume or obscure tickers (DYN, GTM, ARR, LEVI, etc.)

SCORING PRIORITIES:
1. TTM Squeeze Firing + Short Float combo (MONSTER SETUP)
2. Days to Cover pressure (>4 days with rising price)
3. Momentum Acceleration (chg_5m > chg_10m > chg_30m)
4. Short Squeeze potential (short_float > 15% + volume)
5. Catalysts (earnings, upgrades) + Sentiment

RESPOND ONLY WITH VALID JSON — no markdown, no explanation outside JSON:
{{
  "action": "BUY" | "SELL" | "SHORT" | "HOLD",
  "ticker": "AAPL",
  "confidence": 75,
  "position_pct": 18,
  "stop_loss_pct": 7,
  "target_pct": 15,
  "reason": "Brief Hebrew explanation",
  "analysis": "Detailed Hebrew analysis of why"
}}

If no good trade exists, return: {{"action": "HOLD", "reason": "אין הזדמנות מספיק חזקה כרגע"}}
"""

# ─── Strategy Profiles ────────────────────────────────────────────

AGGRESSIVE_STRATEGY = {
    'name': 'aggressive',
    'label': '🔥 אגרסיבי — סקוויזים ופריצות',
    'min_health_score': 30,          # was 40 — take riskier plays
    'min_rel_volume': 0.3,           # was 0.4 — wider net
    'min_change_pct': 0.5,           # was 1.0 — catch earlier
    'preferred_rsi_low': 20,         # was 25
    'preferred_rsi_high': 80,        # was 75 — ride overbought momentum
    'min_confidence': 35,            # was 45 — enter more aggressively
    'gap_weight': 1.8,               # was 1.5
    'volume_weight': 1.5,            # was 1.3
    'earnings_boost': 2.5,           # was 2.0
    'momentum_weight': 1.6,          # was 1.4
    'news_weight': 1.0,
    'mean_reversion_weight': 0.5,    # was 0.8
    'sector_weight': 1.2,            # was 1.0
    'regime_weight': 0.5,            # was 0.8 — less scared of regime
    'trend_alignment_weight': 0.8,   # was 1.1 — squeeze stocks fight trends
    'short_squeeze_weight': 2.2,     # was 1.8 — max squeeze priority
    'max_position_pct': 15,          # capped at 15% — focused bets
    'stop_loss_pct': 4,              # tight 4% stops — cut losses fast
    'target_pct': 12,                # 12% target — realistic
    'max_positions': 5,              # 5 positions max
}

CONSERVATIVE_STRATEGY = {
    'name': 'conservative',
    'label': '🛡️ שמרני — מומנטום יציב',
    'min_health_score': 65,
    'min_rel_volume': 1.0,
    'min_change_pct': 2.0,
    'preferred_rsi_low': 35,
    'preferred_rsi_high': 65,
    'min_confidence': 65,
    'gap_weight': 1.0,
    'volume_weight': 1.5,
    'earnings_boost': 2.5,
    'momentum_weight': 1.2,
    'news_weight': 1.3,
    'mean_reversion_weight': 0.5,
    'sector_weight': 1.2,
    'regime_weight': 1.5,       # very regime-aware
    'trend_alignment_weight': 1.8,  # only trade with the trend
    'short_squeeze_weight': 0.5,    # less squeeze focus
    'max_position_pct': 15,
    'stop_loss_pct': 5,
    'target_pct': 10,
    'max_positions': 3,
}

DEFAULT_STRATEGY = AGGRESSIVE_STRATEGY.copy()

def pick_strategy(regime: dict) -> dict:
    """Auto-select strategy based on market conditions."""
    rtype = regime.get('type', 'neutral')
    vol = regime.get('volatility', 'normal')

    if rtype == 'bearish' or vol == 'extreme':
        return CONSERVATIVE_STRATEGY.copy()
    return AGGRESSIVE_STRATEGY.copy()

# ─── Sentiment Lexicon ────────────────────────────────────────────

_BULLISH_WORDS = {
    'upgrade', 'upgraded', 'beat', 'beats', 'exceeds', 'exceeded', 'raises',
    'raised', 'growth', 'surges', 'soars', 'jumps', 'rally', 'bullish',
    'strong', 'record', 'high', 'profit', 'revenue', 'buy', 'outperform',
    'overweight', 'positive', 'approval', 'fda', 'partnership', 'deal',
    'contract', 'acquisition', 'dividend', 'buyback', 'breakout', 'momentum',
    'impressive', 'robust', 'accelerate', 'boost', 'expand', 'innovation',
    'breakthrough', 'optimistic', 'confident', 'above', 'beat expectations',
}

_BEARISH_WORDS = {
    'downgrade', 'downgraded', 'miss', 'misses', 'missed', 'cuts', 'cut',
    'decline', 'drops', 'falls', 'crash', 'bearish', 'weak', 'loss',
    'losses', 'sell', 'underperform', 'underweight', 'negative', 'warning',
    'recall', 'lawsuit', 'investigation', 'dilution', 'offering', 'layoffs',
    'restructuring', 'disappointing', 'concern', 'risk', 'below', 'slump',
    'plunge', 'tumble', 'bankruptcy', 'default', 'suspend', 'delayed',
}

# ─── Persistence Helpers ──────────────────────────────────────────

def _load_strategy() -> dict:
    try:
        if LEARNING_FILE.exists():
            data = json.loads(LEARNING_FILE.read_text())
            stored = data.get('strategy', {})
            merged = DEFAULT_STRATEGY.copy()
            merged.update({k: v for k, v in stored.items() if k in DEFAULT_STRATEGY})
            return merged
    except Exception:
        pass
    return DEFAULT_STRATEGY.copy()


def _save_learning(strategy: dict, lessons: list):
    LEARNING_FILE.parent.mkdir(exist_ok=True)
    data = {'strategy': strategy, 'lessons': lessons[-50:], 'updated': datetime.now().isoformat()}
    LEARNING_FILE.write_text(json.dumps(data, indent=2, default=str))


def _save_regime(regime: dict):
    REGIME_FILE.parent.mkdir(exist_ok=True)
    REGIME_FILE.write_text(json.dumps(regime, indent=2, default=str))


def _load_regime() -> dict:
    try:
        if REGIME_FILE.exists():
            return json.loads(REGIME_FILE.read_text())
    except Exception:
        pass
    return {'type': 'unknown', 'breadth': 0, 'volatility': 'normal', 'hot_sectors': [], 'updated': ''}


def _safe_float(val, default=0.0) -> float:
    try:
        if isinstance(val, str):
            val = val.replace('%', '').replace(',', '').strip()
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


# ─── AI Provider: Groq (Primary) ─────────────────────────────────

def _parse_ai_json(text: str) -> Optional[dict]:
    """Extract JSON from AI response text, handling markdown fences."""
    text = text.strip()
    if text.startswith('```'):
        text = text.split('\n', 1)[1] if '\n' in text else text[3:]
        if text.endswith('```'):
            text = text[:-3]
        text = text.strip()
    # Sometimes model wraps in ```json ... ```
    if text.startswith('{'):
        return json.loads(text)
    # Try to find JSON object in the text
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1:
        return json.loads(text[start:end + 1])
    return None


async def ask_groq(prompt: str) -> Optional[dict]:
    """Call Groq API with Llama 3.3 70B — ultra-fast inference."""
    api_key = settings.groq_api_key
    if not api_key:
        return None
    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a JSON-only trading AI. Respond ONLY with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_completion_tokens=1024,
            response_format={"type": "json_object"},
        )
        text = completion.choices[0].message.content
        print(f"[Groq] Response received ({len(text)} chars, model: llama-3.3-70b)")
        return _parse_ai_json(text)
    except GroqAPIError as e:
        print(f"[Groq] API error: {e.status_code} — {str(e)[:200]}")
        return None
    except json.JSONDecodeError:
        print(f"[Groq] Failed to parse JSON")
        return None
    except Exception as e:
        print(f"[Groq] Error: {e}")
        return None


# ─── AI Provider: Gemini (Fallback) ──────────────────────────────

async def ask_gemini(prompt: str) -> Optional[dict]:
    """Call Gemini API — fallback when Groq is unavailable."""
    api_key = settings.gemini_api_key
    if not api_key:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1024},
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    print(f"[Gemini] API error {resp.status}: {err[:200]}")
                    return None
                data = await resp.json()
        text = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        print(f"[Gemini] Response received ({len(text)} chars)")
        return _parse_ai_json(text)
    except json.JSONDecodeError:
        print(f"[Gemini] Failed to parse JSON")
        return None
    except Exception as e:
        print(f"[Gemini] Error: {e}")
        return None


# ─── Multi-Provider AI Call ──────────────────────────────────────

async def ask_ai(prompt: str) -> tuple[Optional[dict], str]:
    """
    Try AI providers in order: Groq → Gemini → None.
    Returns (response_dict, engine_name).
    """
    # 1. Groq (primary — fastest)
    result = await ask_groq(prompt)
    if result:
        return result, 'groq'

    # 2. Gemini (fallback)
    result = await ask_gemini(prompt)
    if result:
        return result, 'gemini'

    # 3. No AI available
    print("[Brain] All AI providers unavailable, using rule-based engine")
    return None, 'rules'


# ─── Market Regime Detection ─────────────────────────────────────

def detect_market_regime(stocks: list) -> dict:
    """
    Analyze all stocks to determine overall market regime.
    Returns: {type: 'bullish'|'bearish'|'neutral'|'volatile', breadth, volatility, hot_sectors}
    """
    if not stocks:
        return {'type': 'unknown', 'breadth': 0, 'volatility': 'normal', 'hot_sectors': [], 'updated': datetime.now().isoformat()}

    changes = [_safe_float(s.get('change_pct')) for s in stocks if s.get('change_pct')]
    up_count = sum(1 for c in changes if c > 0)
    down_count = sum(1 for c in changes if c < 0)
    breadth = (up_count - down_count) / max(len(changes), 1) * 100

    avg_abs_chg = sum(abs(c) for c in changes) / max(len(changes), 1)
    volatility = 'extreme' if avg_abs_chg > 5 else 'high' if avg_abs_chg > 3 else 'normal' if avg_abs_chg > 1 else 'low'

    if breadth > 30:
        regime_type = 'bullish'
    elif breadth < -30:
        regime_type = 'bearish'
    elif volatility in ('high', 'extreme'):
        regime_type = 'volatile'
    else:
        regime_type = 'neutral'

    sector_gains = {}
    sector_counts = {}
    for s in stocks:
        sector = s.get('sector', 'Unknown')
        if not sector or sector == 'Unknown':
            continue
        chg = _safe_float(s.get('change_pct'))
        sector_gains[sector] = sector_gains.get(sector, 0) + chg
        sector_counts[sector] = sector_counts.get(sector, 0) + 1

    sector_avg = {}
    for sec in sector_gains:
        if sector_counts[sec] >= 2:
            sector_avg[sec] = sector_gains[sec] / sector_counts[sec]

    hot_sectors = sorted(sector_avg.items(), key=lambda x: x[1], reverse=True)[:3]
    hot_sectors = [{'name': s, 'avg_change': round(v, 2)} for s, v in hot_sectors if v > 0.5]

    regime = {
        'type': regime_type,
        'breadth': round(breadth, 1),
        'volatility': volatility,
        'avg_change': round(avg_abs_chg, 2),
        'up_count': up_count,
        'down_count': down_count,
        'total': len(changes),
        'hot_sectors': hot_sectors,
        'updated': datetime.now().isoformat(),
    }
    _save_regime(regime)
    return regime


# ─── News Sentiment ──────────────────────────────────────────────

def analyze_news_sentiment(news_list: list) -> dict:
    """Score news headlines for bullish/bearish sentiment."""
    if not news_list:
        return {'score': 0, 'label': 'neutral', 'bullish': 0, 'bearish': 0}

    bullish = 0
    bearish = 0
    for n in news_list:
        title = (n.get('title', '') or '').lower()
        words = set(re.findall(r'[a-z]+', title))
        b = len(words & _BULLISH_WORDS)
        br = len(words & _BEARISH_WORDS)
        bullish += b
        bearish += br

    total = bullish + bearish
    if total == 0:
        return {'score': 0, 'label': 'neutral', 'bullish': 0, 'bearish': 0}

    score = (bullish - bearish) / total
    label = 'bullish' if score > 0.2 else 'bearish' if score < -0.2 else 'neutral'
    return {'score': round(score, 2), 'label': label, 'bullish': bullish, 'bearish': bearish}


# ─── TTM Squeeze Detection ───────────────────────────────────────

def detect_ttm_squeeze(stock: dict) -> tuple:
    """
    TTM Squeeze: Bollinger Bands inside Keltner Channels = compression.
    When BB expands outside KC = breakout (squeeze fires).

    We approximate using Finviz data:
      - SMA20 distance tells us how far price deviates (proxy for BB width)
      - ATR tells us volatility (proxy for KC width)
      - Volatility string (e.g. "5.23%") tells us weekly vol

    Squeeze states:
      'firing'   = was compressed, now breaking out (best entry!)
      'on'       = currently compressed (building energy)
      'off'      = normal, no squeeze
    """
    sma20_dist = _safe_float(stock.get('sma20'))
    atr = _safe_float(stock.get('atr'))
    price = _safe_float(stock.get('price'))
    chg = _safe_float(stock.get('change_pct'))
    rel_vol = _safe_float(stock.get('rel_volume'))
    vol_str = stock.get('volatility', '')

    score = 0
    reasons = []

    if not price or price <= 0 or not atr:
        return 0, [], 'unknown'

    # ATR as % of price — normalized volatility
    atr_pct = (atr / price) * 100

    # Parse weekly volatility (e.g. "5.23%" from Finviz)
    weekly_vol = _safe_float(vol_str.split(' ')[0] if isinstance(vol_str, str) else vol_str)

    # Squeeze detection heuristics:
    # Tight range (low ATR%) + close to SMA20 + then a breakout move = squeeze firing
    is_compressed = atr_pct < 3 and abs(sma20_dist) < 3
    is_breaking_out = chg > 2 and rel_vol >= 1.2

    if is_compressed and is_breaking_out:
        # SQUEEZE FIRING — best signal
        score += 20
        reasons.append(f'🔥 TTM Squeeze Firing! (ATR {atr_pct:.1f}% + פריצה +{chg:.1f}%)')
        state = 'firing'
    elif is_compressed and not is_breaking_out:
        # SQUEEZE ON — building energy, watch closely
        score += 6
        reasons.append(f'⏳ Squeeze On — דחיסה (ATR {atr_pct:.1f}%)')
        state = 'on'
    elif atr_pct < 2 and weekly_vol and weekly_vol < 4:
        # Very tight, even if SMA20 dist is wider
        score += 4
        reasons.append(f'📦 דחיסה נמוכה (vol {weekly_vol:.1f}%)')
        state = 'on'
    else:
        state = 'off'

    # Momentum direction during squeeze
    if state in ('firing', 'on') and chg > 0:
        score += 5
        reasons.append('מומנטום חיובי בזמן דחיסה')
    elif state == 'firing' and chg > 5:
        score += 8
        reasons.append(f'פריצה חזקה +{chg:.1f}%!')

    return score, reasons, state


# ─── Days to Cover (Squeeze Pressure) ───────────────────────────

def score_days_to_cover(stock: dict) -> tuple:
    """
    Days to Cover = Short Interest / Avg Daily Volume.
    Higher = harder for shorts to exit = more squeeze pressure.

    Source priority:
      1. Finviz 'short_ratio' — real DTC, updated bi-monthly by FINRA
      2. Computed: short_interest / avg_volume — fallback when short_ratio missing

    Thresholds from research:
      > 7 days: extreme squeeze pressure
      > 4 days: high pressure
      > 2 days: moderate
    """
    dtc = _safe_float(stock.get('short_ratio'))
    dtc_source = 'finviz'

    # Fallback: compute DTC from short_interest / avg_volume
    if dtc <= 0:
        si  = _safe_float(stock.get('short_interest'))   # shares (already parsed to number)
        avg = _safe_float(stock.get('avg_volume'))
        if si > 0 and avg > 0:
            dtc = si / avg
            dtc_source = 'computed'

    short_fl = _safe_float(stock.get('short_float'))
    chg = _safe_float(stock.get('change_pct'))

    score = 0
    reasons = []

    if dtc <= 0:
        return 0, []

    _dtc_tag = '' if dtc_source == 'finviz' else ' (מחושב)'
    # DTC alone
    if dtc >= 7:
        score += 15
        reasons.append(f'⚠️ DTC {dtc:.1f}d{_dtc_tag} — לחץ סקוויז קיצוני!')
    elif dtc >= 4:
        score += 10
        reasons.append(f'DTC {dtc:.1f}d{_dtc_tag} — לחץ גבוה')
    elif dtc >= 2:
        score += 4
        reasons.append(f'DTC {dtc:.1f}d{_dtc_tag}')

    # DTC + High Short Float = deadly combo
    if dtc >= 4 and short_fl >= 15:
        combo_bonus = min(12, int(dtc * short_fl / 10))
        score += combo_bonus
        reasons.append(f'💣 קומבו: DTC {dtc:.1f} × Short {short_fl:.0f}% = מלכודת שורטים')

    # DTC + Rising price = shorts bleeding
    if dtc >= 3 and chg >= 3:
        score += 8
        reasons.append(f'🩸 שורטים מדממים (DTC {dtc:.1f} + עלייה +{chg:.1f}%)')

    return score, reasons


# ─── Catalyst Scoring for Squeeze ────────────────────────────────

def score_catalyst_for_squeeze(stock: dict) -> tuple:
    """
    Evaluate catalyst quality to confirm a squeeze is real.
    Without a catalyst, even a high-score squeeze may not hold.

    Uses the 'reasons' list already computed by _classify_move_reason.
    Returns (score, catalyst_label, catalyst_type, has_strong_catalyst).
    """
    reasons = stock.get('reasons') or []
    score = 0
    labels = []
    types = set()

    # Catalyst weights by type
    _weights = {
        'earnings':   (25, '📊 דוח רבעוני'),
        'fda':        (25, '💊 FDA'),
        'ma':         (22, '🤝 מיזוג/רכישה'),
        'upgrade':    (18, '⬆️ שדרוג אנליסט'),
        'contract':   (16, '📝 חוזה'),
        'guidance':   (14, '🔮 תחזית'),
        'insider':    (12, '🏷️ קניית פנים'),
        'gap':        (10, '📈 גאפ'),
        'volume_spike': (6, '📊 נפח חריג'),
        'ai_sector':  (8,  '🤖 AI/סמיקונדקטור'),
        'dilution':   (-10, '📉 הנפקת מניות'),
        'risk':       (-8,  '⚠️ חקירה/סיכון'),
    }

    for r in reasons[:4]:
        rtype = r.get('type', '')
        conf  = r.get('confidence', 'low')
        w, lbl = _weights.get(rtype, (0, ''))
        if w == 0:
            continue
        # Confidence multiplier
        mult = 1.0 if conf == 'high' else (0.6 if conf == 'medium' else 0.3)
        pts = int(w * mult)
        score += pts
        if lbl and pts > 0:
            # Preserve memory age suffix (e.g. "(לפני 2י)") from original label
            if r.get('from_memory') and '(לפני' in (r.get('label') or ''):
                age_suffix = r['label'].split('(לפני')[1]
                lbl = lbl + ' (לפני' + age_suffix
            labels.append(lbl)
            types.add(rtype)

    has_strong = any(t in types for t in ('earnings', 'fda', 'ma', 'upgrade', 'contract'))
    catalyst_label = ' + '.join(labels[:3]) if labels else '⚠️ אין קטליסט ברור'

    return score, catalyst_label, list(types), has_strong


# ─── Breakout Confirmation ────────────────────────────────────────

def score_breakout_confirmation(stock: dict) -> tuple:
    """
    Check breakout quality: Above VWAP / HOD / Resistance.
    A squeeze without a good price structure often fails.

    Returns (score, checks_dict) where checks_dict has:
      above_vwap, near_hod, above_resistance, breakout_label
    """
    score = 0
    checks = {
        'above_vwap':      False,
        'near_hod':        False,
        'above_resistance': False,
    }
    signals = []

    price        = _safe_float(stock.get('price'))
    indicators   = stock.get('tech_indicators') or {}
    vwap_bias    = indicators.get('vwap_bias') or stock.get('vwap_bias', 'neutral')
    resistance   = _safe_float(stock.get('tech_resistance'))
    day_high     = _safe_float(stock.get('day_high'))

    # 1. Above VWAP — confirms intraday buyers in control
    if vwap_bias == 'bullish':
        score += 15
        checks['above_vwap'] = True
        signals.append('✅ מעל VWAP')
    elif vwap_bias == 'bearish':
        score -= 8
        signals.append('❌ מתחת VWAP')

    # 2. Near or at High of Day — price making new highs = shorts running
    if price > 0 and day_high > 0:
        dist_to_hod = (day_high - price) / day_high * 100  # % below HOD
        if dist_to_hod <= 0.5:   # within 0.5% = essentially at HOD
            score += 18
            checks['near_hod'] = True
            signals.append('✅ שיא יומי — HOD!')
        elif dist_to_hod <= 2.0:
            score += 10
            checks['near_hod'] = True
            signals.append(f'↗️ קרוב ל-HOD ({dist_to_hod:.1f}% מתחת)')
        else:
            signals.append(f'📉 {dist_to_hod:.1f}% מתחת לשיא היום')

    # 3. Above resistance — breakout confirmed
    if price > 0 and resistance > 0:
        if price > resistance * 1.005:   # price > resistance + 0.5% buffer
            score += 15
            checks['above_resistance'] = True
            signals.append(f'✅ פריצת התנגדות ${resistance:.2f}')
        elif price > resistance * 0.995:  # touching resistance
            score += 6
            signals.append(f'⚡ נוגע בהתנגדות ${resistance:.2f}')
        elif price < resistance:
            pct_below = (resistance - price) / price * 100
            signals.append(f'🔴 התנגדות ${resistance:.2f} (+{pct_below:.1f}%)')

    confirmed_count = sum(checks.values())
    if confirmed_count == 3:
        breakout_label = '✅✅✅ פריצה מושלמת'
    elif confirmed_count == 2:
        breakout_label = '✅✅ פריצה חזקה'
    elif confirmed_count == 1:
        breakout_label = '✅ פריצה חלקית'
    else:
        breakout_label = '⚠️ ללא אישור פריצה'

    checks['breakout_label'] = breakout_label
    checks['breakout_signals'] = signals

    return score, checks


# ─── Full Short Squeeze Scoring ──────────────────────────────────

def score_short_squeeze_full(stock: dict) -> dict:
    """
    Combined short squeeze analysis using Finviz fundamentals + intraday TA.

    Squeeze potential levels:
      0-20:  Low — not a squeeze candidate
      21-40: Watch — elevated short interest, monitor
      41-60: Alert — squeeze conditions building
      61-80: High — active squeeze, high probability
      81+:   Extreme — squeeze firing, urgent signal

    Squeeze stages (from intraday TA if available):
      accumulation → compression → firing → exhaustion

    Returns dict with total_score, stage, signals, label, emoji.
    """
    total_score = 0
    all_signals = []

    # ── 1. Short Float (% of float sold short) ───────────────────
    short_fl = _safe_float(stock.get('short_float'))
    if short_fl >= 30:
        total_score += 25
        all_signals.append(f'🩸 Short Float {short_fl:.0f}% — מלכודת שורטים קיצונית')
    elif short_fl >= 20:
        total_score += 18
        all_signals.append(f'⚠️ Short Float {short_fl:.0f}% — לחץ שורט גבוה')
    elif short_fl >= 15:
        total_score += 12
        all_signals.append(f'Short Float {short_fl:.0f}% — שורט משמעותי')
    elif short_fl >= 10:
        total_score += 6
        all_signals.append(f'Short Float {short_fl:.0f}%')

    # ── 2. Days to Cover (DTC) ───────────────────────────────────
    dtc_score, dtc_signals = score_days_to_cover(stock)
    total_score += dtc_score
    all_signals.extend(dtc_signals)

    # ── 3. Intraday squeeze stage from TA engine ──────────────────
    squeeze_stage = stock.get('squeeze_stage') or 'none'
    squeeze_intra = stock.get('squeeze_score') or 0
    squeeze_sigs  = stock.get('squeeze_signals') or []

    stage_bonus = {
        'firing':       30,
        'compression':  15,
        'accumulation': 8,
        'exhaustion':   -10,
        'none':         0,
    }
    total_score += stage_bonus.get(squeeze_stage, 0)
    if squeeze_intra > 0:
        total_score += min(20, squeeze_intra // 2)
    all_signals.extend(squeeze_sigs)

    # ── 4. Price momentum confirms squeeze ───────────────────────
    chg = _safe_float(stock.get('change_pct'))
    rel_vol = _safe_float(stock.get('rel_volume'))
    if short_fl >= 10 and chg >= 5 and rel_vol >= 1.5:
        total_score += 15
        all_signals.append(f'💥 מחיר +{chg:.1f}% עם RVol {rel_vol:.1f}× בזמן שורט גבוה')
    elif short_fl >= 10 and chg >= 3:
        total_score += 8
        all_signals.append(f'📈 מחיר +{chg:.1f}% לוחץ על שורטים')

    # ── 5. Small float = easier to squeeze ───────────────────────
    market_cap = _safe_float(stock.get('market_cap'))
    if 0 < market_cap < 500:  # under $500M
        total_score += 8
        all_signals.append(f'שווי שוק קטן (${market_cap:.0f}M) — קל יותר לסחוט')
    elif 0 < market_cap < 2000:
        total_score += 4

    # ── 6. Float Rotation (volume / float shares) ─────────────────
    # מדד כמה פעמים כל הפלואט נסחר היום — >1x = כל המניות החליפו ידיים → קונים חדשים מציפים את השורטים
    shs_float_raw = stock.get('shs_float', '')
    shs_float_m = _safe_float(shs_float_raw)   # Finviz נותן ב-Millions (e.g. "45.32M" → 45.32 after parse)
    volume_raw   = _safe_float(stock.get('volume'))
    if shs_float_m > 0 and volume_raw > 0:
        # Finviz shs_float is already parsed by _parse_fv_num → number in millions
        float_shares = shs_float_m * 1_000_000
        float_rotation = volume_raw / float_shares
        if float_rotation >= 1.5:
            total_score += 22
            all_signals.append(f'🔄 Float Rotation ×{float_rotation:.1f} — הפלואט נסחר {float_rotation:.1f}× היום! (קונים שוטפים שורטים)')
        elif float_rotation >= 1.0:
            total_score += 16
            all_signals.append(f'🔄 Float Rotation ×{float_rotation:.1f} — כל הפלואט החליף ידיים (לחץ עצום)')
        elif float_rotation >= 0.5:
            total_score += 8
            all_signals.append(f'🔄 Float Rotation ×{float_rotation:.1f} — חצי הפלואט נסחר')
        elif float_rotation >= 0.25:
            total_score += 3
            all_signals.append(f'Float Rotation ×{float_rotation:.1f}')

    # ── 7. Borrow Fee estimation (from Short Float as proxy) ──────
    # כשהרבה אנשים בשורט → מניה קשה להשאלה (HTB) → ריבית שאלה יומית גבוהה
    # → שורטים משלמים ריבית כל יום → לחץ כלכלי לסגור פוזיציה → forced buying
    if short_fl >= 40:
        total_score += 12
        all_signals.append(f'💸 HTB קיצוני (Short {short_fl:.0f}%) — ריבית השאלה >100% שנתי, שורטים מדממים כסף!')
    elif short_fl >= 30:
        total_score += 8
        all_signals.append(f'💸 HTB גבוה (Short {short_fl:.0f}%) — ריבית השאלה גבוהה, לחץ כלכלי לסגור')
    elif short_fl >= 20:
        total_score += 4
        all_signals.append(f'💸 ריבית השאלה מוגברת (Short {short_fl:.0f}%)')

    # ── 8. TTM squeeze confirmation ───────────────────────────────
    ttm_score, ttm_signals, ttm_state = detect_ttm_squeeze(stock)
    if ttm_state in ('firing', 'on'):
        total_score += ttm_score
        all_signals.extend(ttm_signals)

    # ── 9. Catalyst quality ────────────────────────────────────────
    # Without a real catalyst, even a beautiful squeeze can fade
    cat_score, cat_label, cat_types, has_strong_cat = score_catalyst_for_squeeze(stock)
    total_score += cat_score
    if has_strong_cat:
        all_signals.append(f'🎯 קטליסט: {cat_label}')
    elif cat_score > 0:
        all_signals.append(f'קטליסט: {cat_label}')
    else:
        all_signals.append('⚠️ אין קטליסט ברור — סקוויז טכני בלבד')

    # ── 10. Breakout confirmation ──────────────────────────────────
    # Above VWAP + HOD + Resistance = full confirmation
    brk_score, brk_checks = score_breakout_confirmation(stock)
    total_score += brk_score
    for sig in brk_checks.get('breakout_signals', []):
        all_signals.append(sig)

    # ── Determine stage ────────────────────────────────────────────
    # Priority: intraday TA (most granular) → TTM → fundamentals score
    if squeeze_stage not in ('none', '', None):
        final_stage = squeeze_stage
    elif ttm_state == 'firing':
        final_stage = 'firing'
    elif ttm_state == 'on':
        # If strong fundamentals + TTM compressed → promote to compression
        final_stage = 'compression'
    elif ttm_state in ('off', 'unknown'):
        # Fundamentals-only path: classify by score
        # Lowered threshold so short_float=20%+DTC=5d (≈28pts) still surfaces
        if total_score >= 50:
            # High enough that a squeeze is building even without intraday confirmation
            final_stage = 'accumulation'
        elif total_score >= 20:
            final_stage = 'accumulation'
        else:
            final_stage = 'none'
    else:
        final_stage = 'none'

    # ── M&A Override: Acquisition/merger → NOT a short squeeze ─────
    # When a stock is being acquired, the price moves to the acquisition price.
    # This is event-driven, not short-squeeze-driven. Misclassifying it as
    # "compression" or "firing" would mislead traders into thinking it will
    # squeeze further when it won't — it'll just trade near the deal price.
    if final_stage != 'none' and 'ma' in cat_types:
        # Check if any reason has M&A with high confidence
        ma_reasons = [r for r in (stock.get('reasons') or [])
                      if r.get('type') == 'ma' and r.get('confidence') == 'high']
        if ma_reasons:
            final_stage = 'none'

    # ── Label + emoji + entry action ──────────────────────────────
    stage_meta = {
        'none':        {
            'label': 'ללא סקוויז',    'emoji': '—',
            'entry': '',
        },
        'accumulation': {
            'label': 'בנייה',          'emoji': '👀',
            'entry': '⏳ המתיני לדחיסה — עדיין מוקדם מדי',
        },
        'compression':  {
            'label': 'דחיסה — כוונו',  'emoji': '⏳',
            'entry': '🎯 כניסה אידיאלית — לפני הפיצוץ',
        },
        'firing':       {
            'label': 'סקוויז פעיל!',   'emoji': '🚀',
            'entry': '⚡ כניסה אגרסיבית עם STOP TIGHT',
        },
        'exhaustion':   {
            'label': 'עייפות — זהירות','emoji': '⚠️',
            'entry': '🚪 אל תיכנסי — שקלי יציאה',
        },
    }
    meta = stage_meta.get(final_stage, stage_meta['none'])

    return {
        'squeeze_total_score': round(total_score),
        'squeeze_stage':       final_stage,
        'squeeze_label':       meta['label'],
        'squeeze_emoji':       meta['emoji'],
        'squeeze_entry':       meta['entry'],
        'squeeze_signals':     all_signals,
        'short_float':         short_fl,
        'dtc':                 _safe_float(stock.get('short_ratio')),
        'float_rotation':      round(volume_raw / (shs_float_m * 1_000_000), 2) if shs_float_m > 0 and volume_raw > 0 else None,
        # Catalyst
        'squeeze_catalyst':        cat_label,
        'squeeze_catalyst_types':  cat_types,
        'squeeze_has_catalyst':    has_strong_cat,
        # Breakout confirmation
        'squeeze_above_vwap':      brk_checks.get('above_vwap', False),
        'squeeze_near_hod':        brk_checks.get('near_hod', False),
        'squeeze_above_resistance': brk_checks.get('above_resistance', False),
        'squeeze_breakout_label':  brk_checks.get('breakout_label', ''),
    }


# ─── Momentum Acceleration ───────────────────────────────────────

def score_momentum_acceleration(stock: dict) -> tuple:
    """
    Detect acceleration: is the move speeding up or fading?

    Acceleration:  chg_5m > chg_10m > chg_30m (getting faster)
    Deceleration:  chg_5m < chg_10m < chg_30m (fading)

    Also detect "surge" patterns: chg_5m very high = fresh breakout.
    """
    chg_5m = _safe_float(stock.get('chg_5m'))
    chg_10m = _safe_float(stock.get('chg_10m'))
    chg_30m = _safe_float(stock.get('chg_30m'))

    score = 0
    reasons = []

    has_data = any(v != 0 for v in [chg_5m, chg_10m, chg_30m])
    if not has_data:
        return 0, []

    # Fresh surge: strong 5m move
    if chg_5m >= 2:
        score += 10
        reasons.append(f'🚀 סרג׳ 5דק +{chg_5m:.1f}%')
    elif chg_5m >= 1:
        score += 5

    # Acceleration pattern: each shorter timeframe is stronger
    if chg_5m > chg_10m > 0 and chg_10m > chg_30m:
        score += 12
        reasons.append(f'⚡ תאוצה! ({chg_30m:+.1f}→{chg_10m:+.1f}→{chg_5m:+.1f}%)')
    elif chg_5m > 0 and chg_10m > 0 and chg_5m > chg_10m:
        score += 6
        reasons.append(f'📈 מאיץ ({chg_10m:+.1f}→{chg_5m:+.1f}%)')

    # Deceleration — momentum fading, negative signal
    if chg_5m < chg_10m < chg_30m and chg_30m > 2:
        score -= 8
        reasons.append(f'📉 מומנטום דועך ({chg_30m:+.1f}→{chg_5m:+.1f}%)')

    # Reversal: was dropping, now rising (buy the dip)
    if chg_30m < -1 and chg_5m > 0.5:
        score += 7
        reasons.append(f'🔄 היפוך! (30דק {chg_30m:+.1f}% → 5דק {chg_5m:+.1f}%)')

    return score, reasons


# ─── Trend Alignment ─────────────────────────────────────────────

def check_trend_alignment(stock: dict) -> tuple:
    """Check if SMA20 > SMA50 > SMA200 (strong uptrend alignment)."""
    sma20 = _safe_float(stock.get('sma20'))
    sma50 = _safe_float(stock.get('sma50'))
    sma200 = _safe_float(stock.get('sma200'))
    price = _safe_float(stock.get('price'))

    if not all([sma20, sma50, price]):
        return 0, []

    score = 0
    reasons = []

    if price > sma20 > 0:
        score += 3
    if price > sma50 > 0:
        score += 3
    if sma200 > 0 and price > sma200:
        score += 4

    if sma20 > 0 and sma50 > 0 and sma20 > sma50:
        score += 4
        if sma200 > 0 and sma50 > sma200:
            score += 5
            reasons.append('מגמה עולה מאושרת (SMA 20>50>200)')
        else:
            reasons.append('מעל ממוצעים נעים')

    if sma20 > 0 and price < sma20 * 0.95:
        score -= 5
        reasons.append('מתחת SMA20')

    if sma50 > 0:
        deviation = (price - sma50) / sma50 * 100
        if deviation > 15:
            score -= 4
            reasons.append(f'רחוק מ-SMA50 (+{deviation:.0f}%)')

    return score, reasons


# ─── Scoring Modules ─────────────────────────────────────────────

def _score_momentum(chg: float, gap: float, rel_vol: float, rsi: float) -> tuple:
    score = 0
    reasons = []
    if 1.5 <= chg <= 15:
        score += chg * 2
        if chg >= 5:
            reasons.append(f'מומנטום חזק +{chg:.1f}%')
        elif chg >= 2:
            reasons.append(f'עלייה +{chg:.1f}%')
    elif chg > 15:
        score -= 10
        reasons.append(f'עלייה קיצונית +{chg:.1f}%')
    elif chg < -5:
        score -= 15
    if gap > 1.5:
        score += gap * 2.5
        reasons.append(f'Gap +{gap:.1f}%')
    if rel_vol >= 1.5:
        score += min(rel_vol, 6) * 3
        if rel_vol >= 3:
            reasons.append(f'נפח חריג x{rel_vol:.1f}')
        elif rel_vol >= 1.5:
            reasons.append(f'נפח גבוה x{rel_vol:.1f}')
    elif rel_vol >= 0.5:
        score += rel_vol * 1.5
    return score, reasons


def _score_fundamentals(health: float, rsi: float, short_fl: float, eps_qq: float, sales_qq: float) -> tuple:
    score = 0
    reasons = []
    score += (health - 50) * 0.5
    if health >= 80:
        reasons.append(f'איכות גבוהה ({health:.0f})')
    elif health >= 60:
        score += 3
    if 30 <= rsi <= 50:
        score += 8
        reasons.append(f'RSI אופטימלי ({rsi:.0f})')
    elif 50 < rsi <= 65:
        score += 4
    elif rsi > 75:
        score -= 10
        reasons.append(f'RSI מכור-יתר ({rsi:.0f})')
    elif 0 < rsi < 30:
        score += 10
        reasons.append(f'RSI מכור ({rsi:.0f}) — הזדמנות')
    if short_fl > 25:
        score += 10
        reasons.append(f'שורט קיצוני {short_fl:.0f}%!')
    elif short_fl > 15:
        score += 6
        reasons.append(f'שורט גבוה {short_fl:.0f}%')
    elif short_fl > 10:
        score += 3
    if eps_qq > 25:
        score += 5
        reasons.append(f'צמיחת EPS +{eps_qq:.0f}%')
    elif eps_qq > 10:
        score += 2
    if sales_qq > 15:
        score += 3
    return score, reasons


def _score_insider(stock: dict) -> tuple:
    """Score based on insider transaction activity from Finviz."""
    score = 0
    reasons = []
    it_str = stock.get('insider_trans', '')
    try:
        it = float(str(it_str).replace('%', '').replace(',', ''))
    except (ValueError, TypeError):
        return 0, []

    if it > 10:
        score += 12
        reasons.append(f'🏷️ אנשי פנים קונים בחוזקה +{it:.0f}%!')
    elif it > 2:
        score += 6
        reasons.append(f'🏷️ קניות פנים +{it:.0f}%')
    elif it < -15:
        score -= 8
        reasons.append(f'⚠️ מכירות פנים חזקות {it:.0f}%')
    elif it < -5:
        score -= 4
        reasons.append(f'מכירות פנים {it:.0f}%')
    return score, reasons


def _score_short_squeeze(short_fl: float, chg: float, rel_vol: float, rsi: float) -> tuple:
    """
    Score short squeeze potential.
    High short float + rising price + high volume = squeeze setup.
    The combination is more powerful than each factor alone.
    """
    score = 0
    reasons = []

    if short_fl <= 5:
        return 0, []

    if short_fl >= 30:
        score += 18
        reasons.append(f'שורט קיצוני {short_fl:.0f}% — פוטנציאל סקוויז')
    elif short_fl >= 20:
        score += 12
        reasons.append(f'שורט גבוה מאוד {short_fl:.0f}%')
    elif short_fl >= 15:
        score += 8
        reasons.append(f'שורט גבוה {short_fl:.0f}%')
    elif short_fl >= 10:
        score += 4

    # Squeeze multiplier: high short + price already rising = squeeze in action
    if short_fl >= 15 and chg >= 3:
        squeeze_mult = min(2.5, 1 + (chg / 10) + (short_fl / 50))
        score = int(score * squeeze_mult)
        reasons.append(f'סקוויז פעיל! (עלייה +{chg:.1f}% עם שורט {short_fl:.0f}%)')

    # Volume confirmation: high volume on a high-short stock is bullish
    if short_fl >= 15 and rel_vol >= 2:
        score += 8
        reasons.append(f'נפח חריג על מניית שורט (x{rel_vol:.1f})')
    elif short_fl >= 10 and rel_vol >= 1.5:
        score += 4

    # RSI sweet spot for squeezes: 40-65 is ideal (not overbought yet)
    if short_fl >= 15:
        if 40 <= rsi <= 65:
            score += 5
            reasons.append(f'RSI {rsi:.0f} — חלון כניסה לסקוויז')
        elif rsi > 80:
            score -= 5
            reasons.append(f'RSI {rsi:.0f} — סקוויז עשוי להיגמר')

    return score, reasons


def _score_catalysts(reasons_list: list) -> tuple:
    score = 0
    reasons = []
    catalyst_weights = {
        'earnings': 14, 'upgrade': 12, 'fda': 12, 'contract': 10,
        'ma': 10, 'insider': 8, 'dividend': 5, 'ai_sector': 6,
        'volume_spike': 4, 'split': 3,
        'downgrade': -12, 'dilution': -10,
    }
    seen_types = set()
    for r in (reasons_list or []):
        rt = r.get('type', '')
        if rt in seen_types:
            continue
        seen_types.add(rt)
        w = catalyst_weights.get(rt, 0)
        score += w
        conf = r.get('confidence', 'low')
        multiplier = 1.5 if conf == 'high' else 1.0 if conf == 'medium' else 0.7
        score = score * multiplier if w > 0 else score
        names = {'earnings': 'דוח רבעוני', 'upgrade': 'שדרוג אנליסט', 'fda': 'אישור FDA',
                 'contract': 'חוזה חדש', 'downgrade': 'הורדת דירוג', 'ma': 'מיזוג/רכישה',
                 'insider': 'רכישת פנים', 'ai_sector': 'סקטור AI'}
        if rt in names:
            reasons.append(names[rt])
    return score, reasons


def _score_trade_context(ticker: str, trade_history: list) -> float:
    score = 0
    recent = [t for t in (trade_history or [])[-20:] if t.get('ticker') == ticker]
    for t in recent:
        if t.get('pnl', 0) < 0:
            score -= 8
        elif t.get('pnl', 0) > 0:
            score += 3
    return score


def _score_regime(stock: dict, regime: dict, strategy: dict) -> tuple:
    """Score adjustment based on market regime and sector."""
    score = 0
    reasons = []
    regime_type = regime.get('type', 'neutral')

    if regime_type == 'bullish':
        score += 5
        reasons.append('שוק שורי')
    elif regime_type == 'bearish':
        score -= 10
        reasons.append('שוק דובי — זהירות')
    elif regime_type == 'volatile':
        score -= 3

    stock_sector = stock.get('sector', '')
    for hs in regime.get('hot_sectors', []):
        if stock_sector and stock_sector == hs.get('name'):
            bonus = min(8, max(2, hs.get('avg_change', 0) * 2))
            score += bonus
            reasons.append(f'סקטור חם ({stock_sector})')
            break

    return score, reasons


def _score_sentiment(stock: dict) -> tuple:
    """Score based on news sentiment analysis."""
    news = stock.get('news', [])
    if not news:
        return 0, []

    sentiment = analyze_news_sentiment(news)
    score = 0
    reasons = []

    if sentiment['label'] == 'bullish':
        score += 6 + min(4, sentiment['bullish'])
        reasons.append(f"סנטימנט חיובי ({sentiment['bullish']}🟢)")
    elif sentiment['label'] == 'bearish':
        score -= 8 - min(4, sentiment['bearish'])
        reasons.append(f"סנטימנט שלילי ({sentiment['bearish']}🔴)")

    return score, reasons


# ─── Smart Exit Logic ────────────────────────────────────────────

def evaluate_exits(positions: dict, stocks: list, live_prices: dict, regime: dict) -> list:
    """
    Suggest smart exits beyond basic SL/TP.
    Returns list of {ticker, reason, urgency} for positions that should be closed.
    """
    suggestions = []
    stock_map = {s.get('ticker'): s for s in stocks}

    for ticker, pos in positions.items():
        price = live_prices.get(ticker, pos['entry_price'])
        entry = pos['entry_price']
        is_long = pos['side'] == 'long'
        pnl_pct = ((price - entry) / entry * 100) if is_long else ((entry - price) / entry * 100)

        entry_time = pos.get('entry_time', '')
        holding_minutes = 0
        try:
            holding_minutes = (datetime.now() - datetime.fromisoformat(entry_time)).total_seconds() / 60
        except Exception:
            pass

        stock_data = stock_map.get(ticker, {})

        # Time decay: flat position eating capital — exit fast
        if holding_minutes > 120 and abs(pnl_pct) < 1.0:
            urgency = 'high' if holding_minutes > 240 else 'medium'
            suggestions.append({
                'ticker': ticker, 'reason': f'Time decay — {int(holding_minutes/60)}h ללא תזוזה ({pnl_pct:+.1f}%)',
                'urgency': urgency, 'action': 'close',
            })

        # Momentum fade: entered on momentum but RSI now overbought
        rsi = _safe_float(stock_data.get('rsi'))
        if is_long and rsi > 80 and pnl_pct > 2:
            suggestions.append({
                'ticker': ticker, 'reason': f'RSI {rsi:.0f} — מומנטום דועך, לממש',
                'urgency': 'high', 'action': 'close',
            })

        # Regime reversal: market turned bearish while we're long
        if is_long and regime.get('type') == 'bearish' and pnl_pct < 2:
            suggestions.append({
                'ticker': ticker, 'reason': 'שוק הפך דובי — צמצום חשיפה',
                'urgency': 'medium', 'action': 'close',
            })

        # Negative news after entry
        sentiment = analyze_news_sentiment(stock_data.get('news', []))
        if is_long and sentiment['label'] == 'bearish' and sentiment['bearish'] >= 3 and pnl_pct < 3:
            suggestions.append({
                'ticker': ticker, 'reason': f"חדשות שליליות ({sentiment['bearish']} אזכורים)",
                'urgency': 'high', 'action': 'close',
            })

        # Volatility expansion with no follow-through
        rel_vol = _safe_float(stock_data.get('rel_volume'))
        if rel_vol > 3 and abs(pnl_pct) < 1 and holding_minutes > 60:
            suggestions.append({
                'ticker': ticker, 'reason': f'נפח גבוה x{rel_vol:.1f} בלי תזוזה — מלכודת',
                'urgency': 'low', 'action': 'watch',
            })

        # Squeeze exhaustion — squeeze stage moved to "exhausted", time to exit
        sq_stage = stock_data.get('squeeze_stage', '')
        if sq_stage == 'exhausted' and pnl_pct > 0:
            suggestions.append({
                'ticker': ticker, 'reason': f'סקוויז נגמר (שלב: exhausted) — לממש רווח ({pnl_pct:+.1f}%)',
                'urgency': 'high', 'action': 'close',
            })

        # Squeeze firing with big gains — tighten trailing or partial exit
        if sq_stage == 'firing' and pnl_pct > 8:
            suggestions.append({
                'ticker': ticker, 'reason': f'סקוויז בפריצה עם רווח {pnl_pct:+.1f}% — הדק טריילינג',
                'urgency': 'medium', 'action': 'tighten_trail',
            })

        # Entered on squeeze but momentum died (building stage + negative P&L after 2h)
        if sq_stage == 'building' and pnl_pct < -2 and holding_minutes > 120:
            suggestions.append({
                'ticker': ticker, 'reason': f'סקוויז לא התפתח ({pnl_pct:+.1f}% אחרי {int(holding_minutes/60)}שע) — שקול יציאה',
                'urgency': 'medium', 'action': 'close',
            })

    return suggestions


# ─── Main Decision Engine ────────────────────────────────────────

def _rule_based_decision(stocks: list, portfolio_state: dict, trade_history: list) -> dict:
    """Advanced multi-factor rule-based engine v5."""
    regime = detect_market_regime(stocks)
    strategy = pick_strategy(regime)
    open_positions = portfolio_state.get('positions', {})
    cash = portfolio_state.get('cash', 0)
    equity = portfolio_state.get('equity', 3000)

    regime = detect_market_regime(stocks)

    if len(open_positions) >= 5:
        return _build_hold('כבר 5 פוזיציות פתוחות — ממתין', regime=regime)

    if cash < equity * 0.05:  # use almost all capital
        return _build_hold('מזומן נמוך — ממתין לסגירת פוזיציה', regime=regime)

    recent_losses = sum(1 for t in (trade_history or [])[-6:] if t.get('pnl', 0) < 0)
    if recent_losses >= 5:  # was 4/5 → 5/6 — more forgiving
        return _build_hold(f'רצף הפסדים ({recent_losses}/6) — מצנן', regime=regime)

    if regime['type'] == 'bearish' and regime.get('breadth', 0) < -60:  # was -50 — less scared
        return _build_hold('שוק דובי חזק — ממתין לתיקון', regime=regime)

    last_10 = (trade_history or [])[-10:]
    recent_win_rate = (sum(1 for t in last_10 if t.get('pnl', 0) > 0) / len(last_10)) if len(last_10) >= 3 else 0.5

    candidates = []
    for s in stocks:
        ticker = s.get('ticker', '')
        if ticker in open_positions:
            continue

        health = _safe_float(s.get('health_score'))
        chg = _safe_float(s.get('change_pct'))
        rsi = _safe_float(s.get('rsi'))
        rel_vol = _safe_float(s.get('rel_volume'))
        gap = _safe_float(s.get('gap_pct'))
        short_fl = _safe_float(s.get('short_float'))
        price = _safe_float(s.get('price'))
        eps_qq = _safe_float(s.get('eps_qq'))
        sales_qq = _safe_float(s.get('sales_qq'))

        if health < strategy.get('min_health_score', 50):
            continue
        if price <= 0.5 or price > 500:
            continue

        mom_score, mom_reasons = _score_momentum(chg, gap, rel_vol, rsi)
        fund_score, fund_reasons = _score_fundamentals(health, rsi, short_fl, eps_qq, sales_qq)
        squeeze_score, squeeze_reasons = _score_short_squeeze(short_fl, chg, rel_vol, rsi)
        ttm_score, ttm_reasons, ttm_state = detect_ttm_squeeze(s)
        dtc_score, dtc_reasons = score_days_to_cover(s)
        accel_score, accel_reasons = score_momentum_acceleration(s)
        cat_score, cat_reasons = _score_catalysts(s.get('reasons'))
        insider_score, insider_reasons = _score_insider(s)
        ctx_score = _score_trade_context(ticker, trade_history)
        regime_score, regime_reasons = _score_regime(s, regime, strategy)
        sent_score, sent_reasons = _score_sentiment(s)
        trend_score, trend_reasons = check_trend_alignment(s)

        total_score = (
            mom_score * strategy.get('momentum_weight', 1.4) +
            fund_score * 1.0 +
            squeeze_score * strategy.get('short_squeeze_weight', 1.8) +
            ttm_score * 1.5 +       # TTM Squeeze — high value signal
            dtc_score * 1.4 +        # Days to Cover — squeeze pressure
            accel_score * 1.3 +      # Momentum Acceleration
            insider_score * 1.2 +    # Insider Trading — smart money signal
            cat_score * strategy.get('news_weight', 1.0) +
            ctx_score +
            regime_score * strategy.get('regime_weight', 0.8) +
            sent_score * strategy.get('news_weight', 1.0) +
            trend_score * strategy.get('trend_alignment_weight', 1.1)
        )

        # Super-combo bonus: TTM firing + high short + acceleration = monster setup
        if ttm_state == 'firing' and short_fl >= 15 and accel_score > 5:
            total_score *= 1.4
            squeeze_reasons.insert(0, '🔥🔥🔥 MONSTER SETUP: TTM + Short + Acceleration')

        all_reasons = (
            ttm_reasons + dtc_reasons + accel_reasons + insider_reasons +
            squeeze_reasons + mom_reasons + fund_reasons +
            cat_reasons + regime_reasons + sent_reasons + trend_reasons
        )

        if total_score >= 8:
            candidates.append({
                'ticker': ticker, 'price': price, 'score': total_score,
                'reasons': all_reasons, 'health': health, 'rsi': rsi,
                'chg': chg, 'rel_vol': rel_vol, 'gap': gap,
                'short_fl': short_fl,
                'sector': s.get('sector', ''),
                'mom_score': mom_score, 'fund_score': fund_score,
                'squeeze_score': squeeze_score,
                'ttm_score': ttm_score, 'ttm_state': ttm_state,
                'dtc_score': dtc_score, 'accel_score': accel_score,
                'cat_score': cat_score, 'regime_score': regime_score,
                'sent_score': sent_score, 'trend_score': trend_score,
            })

    if not candidates:
        return _build_hold('אין הזדמנות חזקה מספיק כרגע', regime=regime)

    # Diversity: if we already have a stock from this sector, slightly penalize
    open_sectors = set()
    for t, p in open_positions.items():
        for ss in stocks:
            if ss.get('ticker') == t:
                open_sectors.add(ss.get('sector', ''))
    for c in candidates:
        if c['sector'] in open_sectors:
            c['score'] *= 0.8

    candidates.sort(key=lambda c: c['score'], reverse=True)
    best = candidates[0]

    confidence = min(95, max(30, int(best['score'] * 1.3)))  # was *1.2, more generous
    min_conf = strategy.get('min_confidence', 45)
    if regime['type'] == 'volatile':
        min_conf = min(75, min_conf + 8)  # less scared of volatility (was +10)

    # Squeeze plays get a confidence boost
    is_squeeze_play = best.get('squeeze_score', 0) > 10
    if is_squeeze_play:
        confidence = min(95, confidence + 10)

    if confidence < min_conf:
        return {
            'action': 'HOLD',
            'reason': f"ביטחון נמוך ({confidence}%) — דורש {min_conf}%+",
            'confidence': confidence, 'engine': 'rules',
            'analysis': f"המועמד: {best['ticker']} (ציון {best['score']:.0f})",
            'market_regime': regime,
        }

    # AGGRESSIVE POSITION SIZING — bigger bets on conviction
    base_pct = min(25, max(10, int(confidence / 4)))   # confidence 60→15%, 80→20%, 90→22%
    if regime['volatility'] in ('high', 'extreme'):
        base_pct = max(10, base_pct - 3)
    if recent_win_rate > 0.6 and len(last_10) >= 5:
        base_pct = min(25, base_pct + 5)   # hot streak → size up
    elif recent_win_rate < 0.3 and len(last_10) >= 5:
        base_pct = max(8, base_pct - 3)    # cold streak → size down
    # Squeeze plays get biggest position
    if is_squeeze_play:
        base_pct = min(25, base_pct + 5)

    # TIGHT STOPS — cut losers fast, protect capital
    stop_pct = 3 if best['health'] >= 70 else 4 if best['health'] >= 50 else 5
    if regime['volatility'] == 'extreme':
        stop_pct = min(7, stop_pct + 2)   # wider only in extreme volatility
    elif regime['volatility'] == 'high':
        stop_pct = min(6, stop_pct + 1)
    # Squeeze plays use ATR-adaptive stops (wider is ok — these moves are big)
    if is_squeeze_play and best.get('short_fl', 0) >= 20:
        stop_pct = min(6, stop_pct + 2)

    # BIG TARGETS — let winners run
    target_pct = max(15, int(best['chg'] * 2.5)) if best['chg'] > 3 else 15
    if best.get('cat_score', 0) > 10:
        target_pct = min(30, target_pct + 5)
    if regime['type'] == 'bullish':
        target_pct = min(35, target_pct + 5)
    # Squeeze plays → big target, these can run 20-50%
    if is_squeeze_play:
        target_pct = min(40, target_pct + 8)
    # TTM Squeeze firing → maximum target
    if best.get('ttm_state') == 'firing':
        target_pct = min(50, target_pct + 10)
    # Accelerating momentum → bigger target
    if best.get('accel_score', 0) > 10:
        target_pct = min(40, target_pct + 5)

    reason_text = ' | '.join(best['reasons'][:5]) if best['reasons'] else f"ציון {best['score']:.0f}"

    return {
        'action': 'BUY',
        'ticker': best['ticker'],
        'confidence': confidence,
        'position_pct': base_pct,
        'stop_loss_pct': stop_pct,
        'target_pct': target_pct,
        'reason': reason_text,
        'analysis': (
            f"ציון: {best['score']:.0f} | "
            f"TTM: {best.get('ttm_score', 0):.0f}({best.get('ttm_state', '?')}) | "
            f"DTC: {best.get('dtc_score', 0):.0f} | "
            f"תאוצה: {best.get('accel_score', 0):.0f} | "
            f"סקוויז: {best.get('squeeze_score', 0):.0f} | "
            f"מומנטום: {best['mom_score']:.0f} | "
            f"פונדמנטלי: {best['fund_score']:.0f} | "
            f"Health: {best['health']:.0f} | RSI: {best['rsi']:.0f} | "
            f"Short: {best.get('short_fl', 0):.0f}%"
        ),
        'engine': 'rules',
        'market_regime': regime,
        'strategy_name': strategy.get('name', 'aggressive'),
        'strategy_label': strategy.get('label', ''),
        'exit_suggestions': evaluate_exits(
            portfolio_state.get('positions', {}), stocks,
            {s.get('ticker'): _safe_float(s.get('price')) for s in stocks},
            regime,
        ),
    }


def _build_hold(reason: str, confidence: int = 0, regime: dict = None) -> dict:
    return {
        'action': 'HOLD', 'reason': reason, 'confidence': confidence,
        'engine': 'rules', 'market_regime': regime or _load_regime(),
    }


# ─── Main Entry Point ────────────────────────────────────────────

async def get_ai_decision(stocks: list, portfolio_state: dict, trade_history: list) -> Optional[dict]:
    """Main brain entry point. Auto-selects strategy, then Groq → Gemini → Rule-based."""
    regime = detect_market_regime(stocks)
    auto_strategy = pick_strategy(regime)
    learned = _load_strategy()
    # Merge learned adjustments into the auto-selected strategy
    strategy = auto_strategy.copy()
    for k, v in learned.items():
        if k in strategy and k not in ('name', 'label'):
            strategy[k] = v

    has_ai = settings.groq_api_key or settings.gemini_api_key
    if has_ai:
        def _ai_sort_key(s):
            h = _safe_float(s.get('health_score'))
            sf = _safe_float(s.get('short_float'))
            chg = _safe_float(s.get('change_pct'))
            rv = _safe_float(s.get('rel_volume'))
            squeeze_bonus = sf * 2 if sf > 10 else 0
            momentum_bonus = chg * 1.5 if chg > 0 else 0
            return h + squeeze_bonus + momentum_bonus + (rv * 3 if rv > 1 else 0)

        top_stocks = sorted(stocks, key=_ai_sort_key, reverse=True)[:18]
        stock_summary = []
        for s in top_stocks:
            ttm_s, ttm_r, ttm_st = detect_ttm_squeeze(s)
            dtc_s, dtc_r = score_days_to_cover(s)
            accel_s, accel_r = score_momentum_acceleration(s)
            stock_summary.append({
                'ticker': s.get('ticker'), 'price': s.get('price'),
                'change_pct': s.get('change_pct'), 'health_score': s.get('health_score'),
                'rel_volume': s.get('rel_volume'), 'rsi': s.get('rsi'),
                'gap_pct': s.get('gap_pct'), 'eps_qq': s.get('eps_qq'),
                'sales_qq': s.get('sales_qq'),
                'short_float': s.get('short_float'),
                'short_ratio': s.get('short_ratio'),
                'atr': s.get('atr'),
                'chg_5m': s.get('chg_5m'), 'chg_10m': s.get('chg_10m'), 'chg_30m': s.get('chg_30m'),
                'ttm_squeeze': ttm_st, 'ttm_score': ttm_s,
                'dtc_score': dtc_s,
                'accel_score': accel_s, 'accel_signals': accel_r[:2],
                'sector': s.get('sector', ''),
                'reasons': [r.get('label') for r in (s.get('reasons') or [])],
                'news': [n.get('title', '')[:80] for n in (s.get('news') or [])[:2]],
            })

        recent_trades = trade_history[-10:] if trade_history else []
        lessons = [
            f"{t.get('ticker')}: {'profit' if t.get('pnl', 0) > 0 else 'loss'} "
            f"${t.get('pnl', 0):.2f} ({t.get('pnl_pct', 0):.1f}%) — {t.get('exit_reason', '')}"
            for t in recent_trades
        ]

        hot_sec_str = ', '.join(h['name'] for h in regime.get('hot_sectors', [])) or 'N/A'
        prompt = SYSTEM_PROMPT.format(
            strategy_params=json.dumps(strategy, indent=2),
            market_regime=regime.get('type', 'unknown'),
            hot_sectors=hot_sec_str,
        )
        prompt += f"\n\nCURRENT TIME: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}"
        prompt += f"\n\nPORTFOLIO STATE:\n{json.dumps(portfolio_state, indent=2)}"
        prompt += f"\n\nTOP STOCKS:\n{json.dumps(stock_summary, indent=2)}"
        if lessons:
            prompt += f"\n\nRECENT TRADE RESULTS:\n" + "\n".join(lessons)
        prompt += "\n\nAnalyze and decide the best action NOW."

        decision, engine = await ask_ai(prompt)
        if decision:
            decision['engine'] = engine
            decision['market_regime'] = regime
            decision['strategy_name'] = strategy.get('name', 'aggressive')
            decision['strategy_label'] = strategy.get('label', '')
            return decision

    return _rule_based_decision(stocks, portfolio_state, trade_history)


# ─── Post-Mortem & Learning ──────────────────────────────────────

async def post_mortem(trade: dict, strategy: dict) -> dict:
    """Analyze closed trade and adjust strategy. Groq/Gemini first, then rules."""
    result = None
    if settings.groq_api_key or settings.gemini_api_key:
        prompt = f"""Analyze this completed trade and suggest strategy improvements.

TRADE:
{json.dumps(trade, indent=2)}

CURRENT STRATEGY:
{json.dumps(strategy, indent=2)}

Respond ONLY with valid JSON:
{{
  "lesson": "Brief Hebrew lesson learned",
  "adjustments": {{
    "param_name": new_value
  }}
}}
Only suggest adjustments if the lesson clearly supports them. Small incremental changes only."""
        result, _ = await ask_ai(prompt)

    if not result:
        result = _rule_based_post_mortem(trade, strategy)

    if result and result.get('adjustments'):
        for key, val in result['adjustments'].items():
            if key in strategy and isinstance(val, (int, float)):
                old = strategy[key]
                strategy[key] = round(old + (val - old) * 0.2, 3)

        lessons = []
        try:
            if LEARNING_FILE.exists():
                lessons = json.loads(LEARNING_FILE.read_text()).get('lessons', [])
        except Exception:
            pass
        lessons.append({
            'trade': trade.get('ticker'), 'pnl': trade.get('pnl'),
            'pnl_pct': trade.get('pnl_pct'), 'lesson': result.get('lesson', ''),
            'adjustments': result.get('adjustments', {}), 'date': datetime.now().isoformat(),
        })
        _save_learning(strategy, lessons)

    return result or {}


def _rule_based_post_mortem(trade: dict, strategy: dict) -> dict:
    """Analyze a closed trade using rules and suggest parameter tweaks."""
    pnl = trade.get('pnl', 0)
    pnl_pct = trade.get('pnl_pct', 0)
    exit_reason = trade.get('exit_reason', '')
    holding = trade.get('holding_minutes', 0)
    adjustments = {}
    lesson = ''

    if pnl > 0:
        if exit_reason == 'Target reached':
            lesson = f"עסקה מוצלחת — הטרגט הושג ({pnl_pct:+.1f}%)"
        elif 'Partial' in exit_reason:
            lesson = f"מימוש חלקי חכם ({pnl_pct:+.1f}%)"
        elif 'Trailing' in exit_reason:
            lesson = f"Trailing stop הציל רווח ({pnl_pct:+.1f}%)"
        elif 'Time decay' in exit_reason:
            lesson = f"יציאה בזמן — עדיף ריווח קטן ({pnl_pct:+.1f}%)"
        elif 'RSI' in exit_reason or 'momentum' in exit_reason.lower():
            lesson = f"יציאה חכמה על RSI גבוה ({pnl_pct:+.1f}%)"
            adjustments['momentum_weight'] = strategy.get('momentum_weight', 1.3) + 0.03
        else:
            lesson = f"רווח: {pnl_pct:+.1f}%"

        if holding < 30 and pnl_pct > 3:
            adjustments['min_confidence'] = max(40, strategy.get('min_confidence', 55) - 1)
        if pnl_pct > 8:
            adjustments['momentum_weight'] = strategy.get('momentum_weight', 1.3) + 0.05

    elif pnl < 0:
        if exit_reason == 'Stop loss':
            if abs(pnl_pct) >= 5:
                lesson = f"הפסד גדול — SL נפגע ({pnl_pct:.1f}%)"
                adjustments['min_confidence'] = min(75, strategy.get('min_confidence', 55) + 2)
            else:
                lesson = f"SL עצר הפסד בזמן ({pnl_pct:.1f}%)"
        elif 'Trailing' in exit_reason:
            lesson = f"Trailing stop חתך ({pnl_pct:.1f}%)"
        elif 'regime' in exit_reason.lower() or 'bearish' in exit_reason.lower():
            lesson = f"יציאה על שינוי משטר ({pnl_pct:.1f}%)"
            adjustments['regime_weight'] = strategy.get('regime_weight', 1.0) + 0.1
        elif 'sentiment' in exit_reason.lower() or 'news' in exit_reason.lower():
            lesson = f"חדשות שליליות הכריחו יציאה ({pnl_pct:.1f}%)"
            adjustments['news_weight'] = strategy.get('news_weight', 1.0) + 0.1
        else:
            lesson = f"הפסד: {pnl_pct:.1f}% — {exit_reason}"
            adjustments['min_health_score'] = min(65, strategy.get('min_health_score', 50) + 1)

        if holding < 15:
            lesson += " | החזקה קצרה"
            adjustments['min_rel_volume'] = min(2.0, strategy.get('min_rel_volume', 0.5) + 0.1)

    else:
        lesson = "עסקה ללא רווח/הפסד"

    return {'lesson': lesson, 'adjustments': adjustments}
