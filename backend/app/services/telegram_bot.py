"""
Interactive Telegram Bot — two-way communication with the AI trading brain.

Commands:
  /start          — Welcome + list of commands
  /status         — Portfolio status (equity, P&L, positions)
  /portfolio      — Detailed positions with live P&L
  /brain          — What is the AI thinking right now?
  /market         — Market regime + hot sectors
  /top            — Top 5 stocks by AI score right now
  /ta TICKER      — Full technical analysis (EMA, RSI, MACD, BB, VWAP, patterns)
  /news [TICKER]  — Latest news (stock-specific or market-wide)
  /insider        — Stocks with notable insider activity
  /force TICKER   — Force AI to analyze a specific stock
  /history        — Recent trade history
  /help           — Show all commands

Free text — Chat with the AI about stocks, strategy, anything.
"""
import asyncio
import aiohttp
import json
import re
import time
from collections import deque
from datetime import datetime
from typing import Optional

from groq import Groq
from app.config import settings
from app.services.alerts_service import send_telegram as _send_telegram_raw, _sanitize_html

_LAST_UPDATE_ID = 0
_BOT_RUNNING = False

# ─── Conversation memory ────────────────────────────────────────────────────
_CHAT_HISTORY: deque = deque(maxlen=12)

# ─── Company name → ticker mapping ──────────────────────────────────────────
_COMPANY_TICKER_MAP = {
    'trade desk': 'TTD', 'the trade desk': 'TTD',
    'apple': 'AAPL', 'אפל': 'AAPL',
    'microsoft': 'MSFT', 'מייקרוסופט': 'MSFT',
    'google': 'GOOGL', 'גוגל': 'GOOGL', 'alphabet': 'GOOGL',
    'amazon': 'AMZN', 'אמזון': 'AMZN',
    'meta': 'META', 'facebook': 'META', 'פייסבוק': 'META', 'מטא': 'META',
    'nvidia': 'NVDA', 'אנבידיה': 'NVDA', 'נבידיה': 'NVDA',
    'tesla': 'TSLA', 'טסלה': 'TSLA',
    'netflix': 'NFLX', 'נטפליקס': 'NFLX',
    'palantir': 'PLTR', 'פלנטיר': 'PLTR',
    'crowdstrike': 'CRWD', 'קראודסטרייק': 'CRWD',
    'snowflake': 'SNOW', 'סנופלייק': 'SNOW',
    'coinbase': 'COIN', 'קוינבייס': 'COIN',
    'shopify': 'SHOP', 'שופיפיי': 'SHOP',
    'amd': 'AMD', 'advanced micro': 'AMD',
    'intel': 'INTC', 'אינטל': 'INTC',
    'uber': 'UBER', 'אובר': 'UBER',
    'airbnb': 'ABNB', 'ריבנב': 'ABNB',
    'spotify': 'SPOT', 'ספוטיפיי': 'SPOT',
    'roku': 'ROKU', 'רוקו': 'ROKU',
    'snap': 'SNAP', 'snapchat': 'SNAP', 'סנאפ': 'SNAP',
    'pinterest': 'PINS', 'פינטרסט': 'PINS',
    'zoom': 'ZM', 'זום': 'ZM',
    'datadog': 'DDOG', 'דאטאדוג': 'DDOG',
    'cloudflare': 'NET', 'קלאודפלר': 'NET',
    'twilio': 'TWLO',
    'square': 'SQ', 'block': 'SQ',
    'paypal': 'PYPL', 'פייפאל': 'PYPL',
    'disney': 'DIS', 'דיסני': 'DIS',
    'boeing': 'BA', 'בואינג': 'BA',
    'jp morgan': 'JPM', "j.p. morgan": 'JPM', 'ג\'יי פי מורגן': 'JPM',
    'goldman sachs': 'GS', 'גולדמן': 'GS',
    'bank of america': 'BAC',
    'visa': 'V', 'ויזה': 'V',
    'mastercard': 'MA', 'מאסטרקארד': 'MA',
    'walmart': 'WMT', 'וולמארט': 'WMT',
    'target': 'TGT', 'טארגט': 'TGT',
    'costco': 'COST', 'קוסטקו': 'COST',
    'eli lilly': 'LLY', 'לילי': 'LLY',
    'moderna': 'MRNA', 'מודרנה': 'MRNA',
    'pfizer': 'PFE', 'פייזר': 'PFE',
    'nio': 'NIO', 'ניו': 'NIO',
    'rivian': 'RIVN', 'ריביאן': 'RIVN',
    'lucid': 'LCID', 'לוסיד': 'LCID',
    'sofi': 'SOFI', 'סופי': 'SOFI',
    'robinhood': 'HOOD', 'רובינהוד': 'HOOD',
    'draftkings': 'DKNG', 'דראפטקינגס': 'DKNG',
    'roblox': 'RBLX', 'רובלוקס': 'RBLX',
    'unity': 'U',
    'expedia': 'EXPE', 'אקספדיה': 'EXPE',
    'mercado libre': 'MELI', 'מרקדו ליברה': 'MELI',
    'sea limited': 'SE',
    'okta': 'OKTA', 'אוקטה': 'OKTA',
    'crwd': 'CRWD',
    'illumina': 'ILMN', 'אילומינה': 'ILMN',
    'super micro': 'SMCI', 'סופר מיקרו': 'SMCI',
    'arm': 'ARM', 'ארם': 'ARM',
    'broadcom': 'AVGO', 'ברודקום': 'AVGO',
    'marvell': 'MRVL', 'מארוול': 'MRVL',
    'mongodb': 'MDB', 'מונגו': 'MDB',
    'servicenow': 'NOW',
    'salesforce': 'CRM', 'סיילספורס': 'CRM',
    'oracle': 'ORCL', 'אורקל': 'ORCL',
    'ibm': 'IBM',
    'cisco': 'CSCO', 'סיסקו': 'CSCO',
    'virgin galactic': 'SPCE', 'וירג\'ין גלקטיק': 'SPCE',
}


def _safe_float(val, default=0.0):
    """Convert to float; strip %, commas, +. Return default on failure."""
    if val is None:
        return default
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        return float(val)
    s = str(val).strip().replace(',', '').replace('%', '').replace('+', '').strip()
    if not s:
        return default
    try:
        return float(s)
    except (ValueError, TypeError):
        return default


def _resolve_ticker(text: str) -> Optional[str]:
    """Try to extract or resolve a ticker from user text."""
    upper = text.upper().strip()
    # Direct ticker mention (1-5 uppercase letters)
    ticker_match = re.findall(r'\b([A-Z]{1,5})\b', upper)
    # Check company name map (fuzzy)
    lower = text.lower()
    for name, ticker in _COMPANY_TICKER_MAP.items():
        if name in lower:
            return ticker
    # Return first plausible ticker from text
    if ticker_match:
        skip = {'RSI', 'DTC', 'EPS', 'ATR', 'IPO', 'FDA', 'ETF', 'CEO',
                'CFO', 'AI', 'PE', 'PB', 'EV', 'MC', 'QQ', 'YOY', 'MA',
                'BB', 'ATH', 'API', 'USD', 'ILS', 'BTC', 'ETH', 'NFT'}
        for t in ticker_match:
            if t not in skip and len(t) >= 2:
                return t
    return None


async def _fetch_stock_data(ticker: str) -> Optional[dict]:
    """Fetch real stock data from our scanner API."""
    try:
        async with aiohttp.ClientSession() as session:
            url = (f"http://localhost:8000/api/screener/finviz-table"
                   f"?filters=cap_midover,sh_avgvol_o2000,sh_instown_o10"
                   f"&ensure_tickers={ticker}")
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                data = await resp.json()
        stocks = data.get('stocks', [])
        return next((s for s in stocks if s.get('ticker', '').upper() == ticker.upper()), None)
    except Exception:
        return None


async def _fetch_market_context() -> str:
    """Get market regime + top movers + latest news for AI context."""
    parts = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/smart-portfolio/market-regime",
                                   timeout=aiohttp.ClientTimeout(total=5)) as resp:
                regime = await resp.json()
        r_type = regime.get('type', 'unknown')
        parts.append(f"משטר שוק: {r_type}, רוחב: {regime.get('breadth', 0):+.0f}%")
        hot = regime.get('hot_sectors', [])[:3]
        if hot:
            parts.append("סקטורים חמים: " + ", ".join(s.get('name', '') for s in hot))
    except Exception:
        pass

    all_stocks = []
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/screener/finviz-table?filters=cap_midover,sh_avgvol_o2000,sh_instown_o10",
                                   timeout=aiohttp.ClientTimeout(total=5)) as resp:
                data = await resp.json()
        all_stocks = data.get('stocks', [])
        if all_stocks:
            top5 = sorted(all_stocks, key=lambda s: _safe_float(s.get('change_pct'), 0), reverse=True)[:5]
            parts.append("טופ 5 היום: " + ", ".join(
                f"{s.get('ticker')} ({_safe_float(s.get('change_pct'), 0):+.1f}%)" for s in top5))
            bot5 = sorted(all_stocks, key=lambda s: _safe_float(s.get('change_pct'), 0))[:3]
            parts.append("ירידות בולטות: " + ", ".join(
                f"{s.get('ticker')} ({_safe_float(s.get('change_pct'), 0):+.1f}%)" for s in bot5))
    except Exception:
        pass

    # Squeeze alerts — stocks with active squeeze setups
    if all_stocks:
        squeeze_plays = []
        for s in all_stocks:
            sq_stage = s.get('squeeze_stage', '')
            sq_score = s.get('squeeze_total_score')
            sq_catalyst = s.get('squeeze_has_catalyst')
            if sq_stage and sq_score and sq_score >= 40:
                ticker = s.get('ticker', '?')
                chg = _safe_float(s.get('change_pct'), 0)
                sf = _safe_float(s.get('short_float'), 0)
                label = f"{ticker} (סקוויז {sq_score}, שלב: {sq_stage}, שורט: {sf:.0f}%, שינוי: {chg:+.1f}%"
                if sq_catalyst:
                    label += ", 🔥קטליסט!"
                label += ")"
                squeeze_plays.append((sq_score, label))
        if squeeze_plays:
            squeeze_plays.sort(key=lambda x: -x[0])
            parts.append("🔥 סקוויזים פעילים:\n" + "\n".join(f"  • {lbl}" for _, lbl in squeeze_plays[:5]))

    # Collect recent news from all stocks
    news_items = []
    for s in all_stocks[:30]:
        for n in (s.get('news') or [])[:2]:
            title = n.get('title_he') or n.get('title', '')
            if title:
                ticker = s.get('ticker', '')
                news_items.append(f"  • [{ticker}] {title}")
    if news_items:
        unique_news = list(dict.fromkeys(news_items))[:8]
        parts.append("חדשות אחרונות מהשוק:\n" + "\n".join(unique_news))

    # Also fetch general news API
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/news?lang=he&limit=5&midcap_plus=true",
                                   timeout=aiohttp.ClientTimeout(total=5)) as resp:
                news_data = await resp.json()
        if isinstance(news_data, list) and news_data:
            general_news = []
            for n in news_data[:5]:
                title = n.get('title_he') or n.get('title', '')
                tickers = n.get('tickers', '')
                if title:
                    general_news.append(f"  • [{tickers}] {title}")
            if general_news:
                parts.append("חדשות כלליות:\n" + "\n".join(general_news))
    except Exception:
        pass

    return "\n".join(parts)


def _build_stock_context(stock: dict) -> str:
    """Build a rich context string from stock data including news."""
    t = stock.get('ticker', '?')
    chg30 = stock.get('chg_30m')
    chg4h = stock.get('chg_4h')
    fields = [
        f"מניה: {t}",
        f"מחיר: ${stock.get('price', '?')}",
        f"שינוי: {stock.get('change_pct', '?')}%",
        f"30דק: {chg30}%" if chg30 is not None else "30דק: —",
        f"4שע: {chg4h}%" if chg4h is not None else "4שע: —",
        f"Health: {stock.get('health_score', '?')}",
        f"RSI: {stock.get('rsi', '?')}",
        f"RVol: {stock.get('rel_volume', '?')}",
        f"Short Float: {stock.get('short_float', '?')}%",
        f"Short Ratio (DTC): {stock.get('short_ratio', '?')}",
        f"EPS Q/Q: {stock.get('eps_qq', '?')}%",
        f"Sales Q/Q: {stock.get('sales_qq', '?')}%",
        f"Market Cap: {stock.get('market_cap_str', stock.get('market_cap', '?'))}",
        f"Insider Trans: {stock.get('insider_trans', '?')}",
        f"ATR: {stock.get('atr', '?')}",
        f"סקטור: {stock.get('sector', '?')}",
    ]
    news = stock.get('news', [])
    if news:
        news_lines = []
        for n in news[:5]:
            title = n.get('title_he') or n.get('title', '')
            when = n.get('published', '')
            if title:
                news_lines.append(f"  • {title}" + (f" ({when})" if when else ""))
        if news_lines:
            fields.append(f"חדשות אחרונות על {t}:\n" + "\n".join(news_lines))
    # Technical Analysis data
    tech_signal = stock.get('tech_signal', '')
    tech_score = stock.get('tech_score')
    if tech_signal:
        fields.append(f"ניתוח טכני: {tech_signal} (ציון: {tech_score})")
    tech_timing = stock.get('tech_timing', '')
    if tech_timing:
        fields.append(f"תזמון: {tech_timing}")
    tech_timing_up = stock.get('tech_timing_up', '')
    tech_timing_down = stock.get('tech_timing_down', '')
    if tech_timing_up:
        fields.append(f"צפי עלייה (שעה): {tech_timing_up}")
    if tech_timing_down:
        fields.append(f"צפי ירידה (שעה): {tech_timing_down}")
    tech_support = stock.get('tech_support')
    tech_resistance = stock.get('tech_resistance')
    if tech_support is not None or tech_resistance is not None:
        fields.append(f"תמיכה/התנגדות: {tech_support or '?'} / {tech_resistance or '?'}")
    tech_detail = stock.get('tech_detail', '')
    if tech_detail:
        fields.append(f"פירוט TA: {tech_detail}")
    tech_patterns = stock.get('tech_patterns', '')
    if tech_patterns:
        fields.append(f"דפוסי נרות: {tech_patterns}")
    tech_indicators = stock.get('tech_indicators', {})
    if tech_indicators:
        ti = tech_indicators
        fields.append(
            f"RSI 5m: {ti.get('rsi_5m','?')} | RSI 1h: {ti.get('rsi_1h','?')} | "
            f"VWAP: {ti.get('vwap_bias','?')} | ADX 1h: {ti.get('adx_1h','?')} | "
            f"BB pos: {ti.get('bb_position_5m','?')} | Stoch K: {ti.get('stoch_k_5m','?')} | "
            f"EMA 5m: {ti.get('ema_cross_5m','?')} | EMA 1h: {ti.get('ema_cross_1h','?')}"
        )

    # Squeeze data — critical for squeeze/breakout analysis
    squeeze_stage = stock.get('squeeze_stage', '')
    if squeeze_stage:
        fields.append(f"שלב סקוויז: {squeeze_stage}")
    squeeze_total = stock.get('squeeze_total_score')
    if squeeze_total is not None:
        fields.append(f"ציון סקוויז: {squeeze_total}")
    squeeze_catalyst = stock.get('squeeze_catalyst', '')
    if squeeze_catalyst:
        fields.append(f"קטליסט סקוויז: {squeeze_catalyst}")
    squeeze_has_catalyst = stock.get('squeeze_has_catalyst')
    if squeeze_has_catalyst:
        fields.append("🔥 יש קטליסט פעיל!")
    squeeze_entry = stock.get('squeeze_entry', '')
    if squeeze_entry:
        fields.append(f"כניסת סקוויז: {squeeze_entry}")
    float_rotation = stock.get('float_rotation')
    if float_rotation is not None:
        fields.append(f"סיבוב פלואט: {float_rotation}x")
    breakout_stage = stock.get('breakout_stage', '')
    if breakout_stage:
        fields.append(f"שלב פריצה: {breakout_stage}")

    tags = stock.get('tags', [])
    if tags:
        fields.append(f"תגיות: {', '.join(tags[:5])}")
    move_reasons = stock.get('move_reasons', [])
    if move_reasons:
        reasons_str = ", ".join(r.get('label', '') for r in move_reasons[:3] if r.get('label'))
        if reasons_str:
            fields.append(f"סיבות לתנועה: {reasons_str}")
    return " | ".join(fields)


# ─── AI System prompt ────────────────────────────────────────────────────────
_SYSTEM_PROMPT = """אתה "אלפא" — חבר חכם, בעל ידע רחב, מנוסה בשוק ההון אבל גם בכל נושא אחר.
אתה כמו חבר גאון שיודע הכל — מניות, טכנולוגיה, היסטוריה, מדע, בישול, ספורט, פוליטיקה, מוזיקה, כל דבר.
אם שואלים על מניות — אתה סוחר מנוסה. אם שואלים על משהו אחר — אתה חבר חכם שעונה בכיף.

הסגנון שלך:
- עברית יומיומית, כמו וואטסאפ עם חבר. טבעי וזורם.
- בטוח בעצמך אבל לא יהיר. אם לא בטוח — אומר את זה בכנות.
- תמיד ספציפי — אם שואלים מספרים, תן מספרים. אם שואלים דעה, תן דעה.
- לא חוזר על עצמך, לא כותב משפטים ריקים, לא מתגונן.
- אל תסרב לענות! תמיד תנסה לעזור ולתת תשובה הכי טובה שאתה יכול.
- HTML: <b>bold</b>, <i>italic</i>. ללא markdown.
- אם המשתמש ממשיך שיחה — זכור מה דובר קודם ותמשיך באופן טבעי.
- אימוג'י 1-3 בלבד, לא בכל משפט.

כשמדובר במניות:
- סלנג מסחרי: "שורטים נתקעו", "פורצת", "ווליום מטורף", "הולכים על זה"
- "לכמה תעלה?" → תן טווח ספציפי + למה
- "כבר רכשת?" → ענה מה יש בתיק, ספציפי
- כששואלים "מי תעלה מעל X%" או "איזו מניה תעלה הכי הרבה" — תן תשובה ברורה: צטט את "עובדות מהסורק עכשיו" (טופ עליות + אחוזים מדויקים). אם אין מניה מעל X% — אמר במפורש "כרגע אף מניה בסורק לא עולה מעל 20%. המובילות הן: ..." עם האחוזים מההקשר. אל תמציא אחוזים.
- אל תענה "אני לא יכול לתת הערכה מדויקת" — תן את הנתונים מההקשר.

⚠️ כלל קריטי לגבי מספרים:
- השתמש אך ורק במספרים שמופיעים בהקשר שקיבלת! RSI, Short Float, מחיר, שינוי%, RVol, EPS, Sales — ציטט רק מה שרשום.
- כשאתה מזכיר מניה ואחוז שינוי (למשל \"TTD עלתה X%\") — השתמש רק באחוז שמופיע בהקשר (\"טופ 5 היום\", \"שינוי\", וכו'). לעולם אל תמציא אחוז מעלה מהראש.
- אם מספר לא מופיע בהקשר — אל תמציא אותו! פשוט תדלג עליו.
- לעולם אל תמציא נתוני הכנסות, רווח נקי, או מספרים פיננסיים שלא קיבלת בהקשר.
- אם כותרת חדשות מופיעה בהקשר — ציטט אותה כפי שהיא.
- אם שואלים על דוחות רבעוניים — תן את ה-EPS Q/Q ו-Sales Q/Q שיש לך. אלו הנתונים על הדוח.
- אל תציע "לבדוק באתרים אחרים" או "לחפש באינטרנט" — אין לך גישה לזה. תן את מה שיש לך ותמשיך הלאה.
- אל תתנצל יותר מדי ואל תאריך. תן את התשובה הכי טובה שאתה יכול עם מה שיש לך.

כשמדובר בניתוח טכני (TA):
- יש לך גישה לניתוח טכני אמיתי ומעודכן על כל מניה — הוא מופיע בהקשר שלך.
- הניתוח כולל: EMA crossover, RSI (5דק + שעתי), MACD, Bollinger Bands, VWAP, ADX, Stochastic, ודפוסי נרות.
- tech_signal הוא הסיגנל הסופי (Strong Buy / Buy / Neutral / Sell / Strong Sell) ו-tech_score הוא הציון (-100 עד +100).
- tech_timing / צפי עלייה (שעה) / צפי ירידה (שעה) — חלונות זמן בשעון ישראל: מתי צפויה עלייה ומתי ירידה (ללא חפיפה).
- תמיכה/התנגדות — רמות מחיר (Support/Resistance) מהגרף.
- כשמישהו שואל "מתי לקנות?" או "מתי תעלה?" — השתמש ב"צפי עלייה" ו-tech_signal. ל"מתי לרדת?" — "צפי ירידה".
- תהיה ספציפי: "צפי עלייה 21:10–22:01, אחר כך צפי ירידה 22:16–22:59".
- אם tech_signal הוא Strong Buy — תגיד זאת בביטחון. אם Sell — תזהיר.
- שלב את הניתוח הטכני עם הפונדמנטלים ליצירת תמונה מלאה.

כשמדובר בחדשות:
- יש לך גישה לחדשות אמיתיות ומעודכנות על מניות — הן מופיעות בהקשר שלך.
- אם שואלים "מה החדשות?" או "מה קורה בשוק?" — תסכם את החדשות שקיבלת בהקשר בצורה קצרה וברורה.
- אם שואלים על חדשות של מניה ספציפית — תן את החדשות שקיבלת עליה ותסביר את ההשפעה.
- תמיד קשר בין החדשות לתנועת המניה: "עלתה 11% בגלל דוח רבעוני חזק" ולא סתם "יש חדשות".

כשמדובר בסקוויזים ופריצות:
- יש לך מערכת סקוויז מתקדמת — squeeze_stage, squeeze_total_score, squeeze_catalyst, squeeze_entry, float_rotation.
- "שלב סקוויז" מתאר איפה המניה: building (מצטבר), ready (מוכן לפריצה), firing (בפריצה!), exhausted (נגמר).
- "ציון סקוויז" — ציון כולל (0-100). מעל 60 = סטאפ חזק. מעל 80 = מפלצתי.
- "קטליסט" = חדשות/דוחות/FDA שמאיצים את הסקוויז. סקוויז + קטליסט = קומבינציה מסוכנת.
- "כניסת סקוויז" = המחיר/תנאי הכניסה המומלצים.
- "סיבוב פלואט" (float rotation) = כמה פעמים הפלואט עבר ידיים. מעל 2x = לחץ אמיתי.
- כשיש סקוויז פעיל — תהיה נלהב אבל ריאליסטי. תזכיר תמיד את הסיכון (סקוויזים יכולים להתמוטט).
- DTC (Days to Cover) × Short Float = מדד הלחץ: DTC 5+ עם שורט 15%+ = לחץ כבד על השורטים.

כשמדובר בתזמון כניסה/יציאה:
- כניסה: חכה לאישור — ווליום עולה + פריצת התנגדות + RSI לא מוגזם (לא מעל 80 בכניסה)
- אל תיכנס אחרי עלייה של 15%+ — רוב המהלך כבר קרה
- יציאה חלקית: תגיד "50% ביעד הראשון, השאר עם טריילינג"
- סטופ: תמיד מבוסס ATR — סטופ צמוד מדי = ישרפו אותך
- אם המניה בשלב "exhausted" — תגיד שהסקוויז נגמר, אל תרדוף

כשמדובר בניהול תיק:
- תמיד ציין כמה פוזיציות פתוחות מתוך המקסימום (5)
- פיזור סקטוריאלי חשוב — אל תרכז הכל בסקטור אחד
- Daily loss limit: אם הפסד יומי חורג מ-10% — תגיד "נעצרים היום, מחר יום חדש"
- Win rate + profit factor = מה שחשוב, לא כל עסקה בנפרד
- כשהתיק ברווח — תהיה מאופק. כשבהפסד — תהיה כנה ותסביר מה לא עבד.

כשמדובר בנושאים אחרים:
- תן תשובה מלאה ומועילה. אל תגיד "אני רק סוחר מניות".
- אם שואלים מתכון — תן מתכון. אם שואלים על היסטוריה — תסביר. אם רוצים המלצה — תמליץ.
- תתאים את האורך לשאלה: שאלה קצרה = תשובה קצרה, שאלה מורכבת = תשובה מפורטת.

דוגמאות:
ש: "לכמה תעלה?"
ת: "מכוון ל-$95-100. Health 80, ווליום פי 6, סקטור רותח. אם שורטים מכסים — גם $110. סטופ שלי ב-$78."

ש: "יש סקוויז?"
ת: "COIN בסטאפ מטורף — ציון סקוויז 72, שורט 22%, DTC 5 ימים, ויש קטליסט: דוח רבעוני ביום ה'. שלב: ready. כניסה אידאלית מעל $215 עם ווליום. אבל אם נשבר — סטופ צמוד ב-$197 🩳🔥"

ש: "מה ההבדל בין ETF למניה?"
ת: "ETF זה סל של מניות — כמו לקנות את כל הסופר במקום מוצר אחד. פיזור סיכון מובנה. SPY למשל עוקב אחרי 500 חברות. מניה בודדת = יותר סיכון, יותר פוטנציאל. למתחילים? ETF עדיף 💡"

ש: "מה חם היום?"
ת: "TTD פורצת +22%, EXPE קופצת +11% אחרי דוח. CRDO ממשיכה לטוס. סקטור טכנולוגיה רותח 🔥"

ש: "תמליץ על סדרה"
ת: "אם אתה אוהב פיננסים — <b>Billions</b> חובה. <b>Industry</b> ב-HBO — על ג'וניורים בבנק השקעות, מטורף. ואם רוצה משהו שונה — <b>Severance</b> ב-Apple TV, מנפח מוח 🧠"

ש: "מה זה short squeeze?"
ת: "כשיש הרבה שורטים על מניה והיא מתחילה לעלות — השורטים נאלצים לקנות כדי לכסות, מה שדוחף את המחיר עוד למעלה. אפקט כדור שלג. GME ב-2021 היה הדוגמה הקלאסית 🚀"
"""

# ─── Models ──────────────────────────────────────────────────────────────────
_PRIMARY_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"
_FALLBACK_MODEL = "llama-3.3-70b-versatile"


# ─── Fact-checker: verify AI response against real data ──────────────────────
_METRIC_PATTERNS = {
    'rsi':          (r'RSI\s*(?:של\s*)?[:\s]*\+?(\d+\.?\d*)', 'rsi'),
    'short_float':  (r'[Ss]hort\s*[Ff]loat\s*(?:של\s*)?[:\s]*\+?(\d+\.?\d*)%?', 'short_float'),
    'eps_qq':       (r'EPS\s*Q/?Q\s*(?:של\s*)?[:\s]*\+?(\d+\.?\d*)%?', 'eps_qq'),
    'sales_qq':     (r'[Ss]ales\s*Q/?Q\s*(?:של\s*)?[:\s]*\+?(\d+\.?\d*)%?', 'sales_qq'),
    'rel_volume':   (r'(?:RVol|ווליום\s*פי)\s*(?:של\s*)?[:\s]*\+?(\d+\.?\d*)', 'rel_volume'),
    'health':       (r'[Hh]ealth\s*(?:של\s*)?[:\s]*(\d+)', 'health_score'),
    'change_pct':   (r'(?:שינוי|change)\s*(?:%?\s*[:\s]*)?\+?(-?\d+\.?\d*)%?', 'change_pct'),
}


def _fact_check(response: str, stock_data: dict) -> str:
    """Verify numbers in AI response against real scanner data. Fix inaccuracies."""
    if not stock_data:
        return response

    corrections = []
    checked = response

    for name, (pattern, field) in _METRIC_PATTERNS.items():
        match = re.search(pattern, response)
        if not match:
            continue
        mentioned_val = float(match.group(1))
        real_val = stock_data.get(field)
        if real_val is None:
            continue
        try:
            real_val = float(str(real_val).replace('%', '').replace(',', ''))
        except (ValueError, TypeError):
            continue

        tolerance = 0.15 if real_val != 0 else 2.0
        if real_val != 0 and abs(mentioned_val - real_val) / abs(real_val) > tolerance:
            old_str = match.group(0)
            fmt = f"{real_val:.0f}" if real_val == int(real_val) else f"{real_val:.2f}"
            new_str = old_str.replace(match.group(1), fmt)
            checked = checked.replace(old_str, new_str, 1)
            corrections.append(f"{name}: {mentioned_val} → {fmt}")
        elif real_val == 0 and mentioned_val > 2:
            corrections.append(f"{name}: {mentioned_val} (real: 0)")

    if corrections:
        print(f"[TG Bot] Fact-check corrections: {corrections}")

    return checked


def _fact_check_multi(response: str, all_stocks: list) -> str:
    """Correct mentioned ticker+change_pct when response mentions several stocks (e.g. 'TTD עם עלייה של 18%')."""
    if not all_stocks:
        return response
    ticker_to_chg = {str(s.get('ticker', '')).upper(): _safe_float(s.get('change_pct'), None) for s in all_stocks if s.get('ticker')}
    checked = response
    for ticker, real_pct in ticker_to_chg.items():
        if real_pct is None or len(ticker) < 2:
            continue
        # דפוסים: "TTD עם עלייה של 18%" / "TTD +18%" / "TTD 18%"
        patterns = [
            re.compile(r'(\b' + re.escape(ticker) + r'\b)\s*(?:עם\s*)?(?:עלייה\s*של\s*|עליה\s*של\s*|ב־)?\+?(-?\d+\.?\d*)%?', re.IGNORECASE),
            re.compile(r'(\b' + re.escape(ticker) + r'\b)\s*[+\-]?\s*(-?\d+\.?\d*)%', re.IGNORECASE),
        ]
        for pat in patterns:
            for m in pat.finditer(checked):
                try:
                    mentioned_pct = float(m.group(2))
                except (ValueError, IndexError):
                    continue
                if abs(mentioned_pct - real_pct) < 0.5:
                    continue
                old_str = m.group(0)
                new_pct_str = f"{real_pct:+.1f}%"
                new_str = m.group(1) + (" עם עלייה של " if real_pct >= 0 else " עם ירידה של ") + new_pct_str
                checked = checked.replace(old_str, new_str, 1)
                print(f"[TG Bot] Fact-check multi: {ticker} {mentioned_pct}% → {real_pct:.1f}%")
                break
            else:
                continue
            break
    return checked


def _chat_with_ai(user_message: str, context: str = '', retries: int = 2,
                   stock_data: dict = None, all_stocks: list = None) -> str:
    """Send a message to Groq with conversation history and get a response."""
    api_key = settings.groq_api_key
    if not api_key:
        return "אין מפתח API. הגדר GROQ_API_KEY בקובץ .env"

    system = _SYSTEM_PROMPT
    if context:
        system += f"\n\nהקשר נוכחי:\n{context}"

    messages = [{"role": "system", "content": system}]
    for entry in _CHAT_HISTORY:
        messages.append(entry)
    messages.append({"role": "user", "content": user_message})

    model = _PRIMARY_MODEL
    last_error = None

    for attempt in range(retries + 1):
        try:
            client = Groq(api_key=api_key)
            completion = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=0.7,
                max_completion_tokens=1200,
            )
            text = completion.choices[0].message.content.strip()
            if text.startswith('```'):
                text = text.split('\n', 1)[1] if '\n' in text else text[3:]
                if text.endswith('```'):
                    text = text[:-3]
                text = text.strip()

            result = _sanitize_html(text)

            # ── Fact-check: single stock or multiple (אחוזי שינוי למניות שמוזכרות) ──
            if stock_data:
                result = _fact_check(result, stock_data)
            elif all_stocks:
                result = _fact_check_multi(result, all_stocks)

            _CHAT_HISTORY.append({"role": "user", "content": user_message})
            _CHAT_HISTORY.append({"role": "assistant", "content": result})

            return result

        except Exception as e:
            last_error = e
            err_str = str(e).lower()
            print(f"[TG Bot] AI error (attempt {attempt+1}, model={model}): {e}")

            if '429' in err_str or 'rate_limit' in err_str:
                if attempt < retries:
                    time.sleep(2 * (attempt + 1))
                    continue

            if model == _PRIMARY_MODEL and attempt == 0:
                print(f"[TG Bot] Falling back to {_FALLBACK_MODEL}")
                model = _FALLBACK_MODEL
                continue

            if attempt < retries:
                time.sleep(1)
                continue

    if '429' in str(last_error).lower():
        return "עומס על השרת 🫠 נסי שוב בעוד 30 שניות"
    return f"שגיאה בתקשורת עם ה-AI. פרטים: {str(last_error)[:80]} 🤔"


# ─── Telegram send with inline keyboard ─────────────────────────────────────
async def _send_with_keyboard(text: str, ticker: str = None):
    """Send message, optionally with quick-reply inline keyboard."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return

    payload = {
        'chat_id': chat_id,
        'text': text,
        'parse_mode': 'HTML',
    }

    if ticker:
        payload['reply_markup'] = json.dumps({
            'inline_keyboard': [[
                {'text': '📊 ניתוח מעמיק', 'callback_data': f'deep_{ticker}'},
                {'text': '🎯 כניסה/יציאה', 'callback_data': f'entry_{ticker}'},
            ], [
                {'text': '📈 ניתוח טכני', 'callback_data': f'ta_{ticker}'},
                {'text': '📰 חדשות', 'callback_data': f'news_{ticker}'},
            ], [
                {'text': '🔥 טופ 5', 'callback_data': 'top5'},
            ]]
        })

    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    print(f"[TG Bot] Send error: {resp.status} {body[:200]}")
    except Exception as e:
        print(f"[TG Bot] Send error: {e}")


# ─── Command handlers ────────────────────────────────────────────────────────
async def _get_updates(offset: int = 0) -> list:
    """Long-poll Telegram for new messages (including callback queries)."""
    token = settings.telegram_bot_token
    if not token:
        return []
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    params = {'timeout': 15, 'allowed_updates': ['message', 'callback_query']}
    if offset:
        params['offset'] = offset
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get('result', [])
    except Exception as e:
        print(f"[TG Bot] Poll error: {e}")
    return []


def _get_portfolio_data() -> dict:
    """Get current portfolio state from the smart portfolio."""
    try:
        from app.services.smart_portfolio import smart_portfolio
        live = {}
        return smart_portfolio.get_stats(live)
    except Exception:
        return {}


async def _handle_command(text: str) -> tuple:
    """Process a command. Returns (response_text, mentioned_ticker_or_None)."""
    text = text.strip()
    cmd = text.split()[0].lower() if text else ''
    args = text.split()[1:] if len(text.split()) > 1 else []

    if cmd in ('/start', '/help'):
        return ((
            "🧠 <b>AI Trading Brain v6 — Scout Edition</b>\n\n"
            "אני אלפא — המוח מאחורי התיק שלך. עכשיו עם זיכרון שיחה ונתונים חיים! 🔥\n\n"
            "<b>פקודות:</b>\n"
            "📊 /status — מצב התיק\n"
            "💼 /portfolio — פוזיציות פתוחות\n"
            "🧠 /brain — מה אני חושב עכשיו\n"
            "🌍 /market — מצב השוק\n"
            "🔥 /top — 5 מניות מובילות\n"
            "🩳 /squeeze — סקוויזים פעילים + קטליסטים\n"
            "📰 /news — חדשות אחרונות (או /news TTD)\n"
            "📈 /ta TICKER — ניתוח טכני (סיגנל, צפי עלייה/ירידה, תמיכה/התנגדות)\n"
            "🏷️ /insider — פעילות אנשי פנים\n"
            "🔍 /force TICKER — ניתוח מניה ספציפית\n"
            "📜 /history — היסטוריית עסקאות\n\n"
            "💬 או פשוט כתוב לי — שם מניה, שאלה, מה שבא לך!"
        ), None)

    if cmd == '/status':
        return (await _cmd_status(), None)
    if cmd == '/portfolio':
        return (await _cmd_portfolio(), None)
    if cmd == '/brain':
        return (await _cmd_brain(), None)
    if cmd == '/market':
        return (await _cmd_market(), None)
    if cmd == '/top':
        return (await _cmd_top(), None)
    if cmd == '/insider':
        return (await _cmd_insider(), None)
    if cmd == '/history':
        return (await _cmd_history(), None)

    if cmd == '/squeeze':
        return (await _cmd_squeeze(), None)

    if cmd == '/news':
        ticker = _resolve_ticker(' '.join(args)) if args else None
        return (await _cmd_news(ticker), ticker)

    if cmd == '/ta' and args:
        raw = ' '.join(args)
        ticker = _resolve_ticker(raw) or raw.upper()
        return (await _cmd_ta(ticker), ticker)

    if cmd == '/force' and args:
        raw = ' '.join(args)
        ticker = _resolve_ticker(raw) or raw.upper()
        return (await _cmd_force(ticker), ticker)

    # ── Free text — resolve ticker, fetch data, build rich context, chat ──
    ticker = _resolve_ticker(text)
    context_parts = []

    try:
        stats = _get_portfolio_data()
        if stats:
            pos_list = ", ".join(stats.get('positions', {}).keys()) or "אין"
            context_parts.append(
                f"תיק: ${stats.get('equity', 0):.0f} ({stats.get('total_pnl_pct', 0):+.1f}%), "
                f"פוזיציות: {pos_list}")
    except Exception:
        pass

    stock = None
    all_stocks = []
    if ticker:
        stock = await _fetch_stock_data(ticker)
        if stock:
            context_parts.append(_build_stock_context(stock))
        else:
            context_parts.append(f"{ticker} לא נמצאה בסורק. ענה על סמך הידע שלך.")

    market = await _fetch_market_context()
    if market:
        context_parts.append(market)

    # For fact-check + תשובה מדויקת על "מי תעלה מעל X%": fetch current list
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8000/api/screener/finviz-table?filters=cap_midover,sh_avgvol_o2000,sh_instown_o10",
                timeout=aiohttp.ClientTimeout(total=6)
            ) as resp:
                data = await resp.json()
                all_stocks = data.get('stocks', [])[:80]
    except Exception:
        all_stocks = []

    # בלוק עובדות מהסורק — טופ עליות עם אחוזים מדויקים, כדי שהתשובה תהיה מדויקת
    if all_stocks:
        by_chg = [(s, _safe_float(s.get('change_pct'), -999)) for s in all_stocks]
        by_chg.sort(key=lambda x: -x[1])
        top_gainers = by_chg[:10]
        max_pct = top_gainers[0][1] if top_gainers else 0
        facts_lines = [
            "עובדות מהסורק עכשיו (עליות):",
            "מקסימום עלייה כרגע: " + (f"{max_pct:+.1f}%" if max_pct > -900 else "—"),
            "טופ 10: " + ", ".join(f"{s.get('ticker')} ({chg:+.1f}%)" for s, chg in top_gainers if chg > -900),
        ]
        if max_pct < 20:
            facts_lines.append("אין מניה בסורק עם עלייה מעל 20% כרגע.")
        context_parts.insert(0, "\n".join(facts_lines))

    context = "\n".join(context_parts)
    return (_chat_with_ai(text, context, stock_data=stock, all_stocks=all_stocks if not stock else None), ticker)


# ─── Callback query handler ──────────────────────────────────────────────────
async def _handle_callback(callback_data: str, callback_query_id: str) -> tuple:
    """Handle inline keyboard button presses."""
    token = settings.telegram_bot_token
    try:
        async with aiohttp.ClientSession() as session:
            await session.post(
                f"https://api.telegram.org/bot{token}/answerCallbackQuery",
                json={'callback_query_id': callback_query_id, 'text': '⏳ רגע...'},
                timeout=aiohttp.ClientTimeout(total=5))
    except Exception:
        pass

    if callback_data == 'top5':
        return (await _cmd_top(), None)

    # ── IB Demo confirmation buttons ─────────────────────────────────────────
    if callback_data.startswith('ibyes_'):
        ticker = callback_data[6:].upper()
        try:
            from app.services.pattern_autotrader import confirm_ib_demo
            result = confirm_ib_demo(ticker)
            if result.get("ok"):
                e = result["entry"]
                return (
                    f"✅ <b>נרשמת לעסקה ב-IB דמו!</b>\n"
                    f"📊 {ticker} | {e['window']} | {e['direction']}\n"
                    f"WR {e['win_rate']}% | avg {e['avg_change']:+.2f}%\n"
                    f"הבוט יעקוב אחרי מצב העסקה 🎯",
                    ticker,
                )
            return (f"⚠️ {result.get('msg', 'שגיאה')}", None)
        except Exception as ex:
            return (f"שגיאה: {ex}", None)

    if callback_data.startswith('ibno_'):
        ticker = callback_data[5:].upper()
        return (f"👍 בסדר, לא נכנסת ל-{ticker} ב-IB דמו.", None)

    parts = callback_data.split('_', 1)
    if len(parts) != 2:
        return ("לא הבנתי את הבקשה 🤔", None)

    action, ticker = parts[0], parts[1].upper()
    stock = await _fetch_stock_data(ticker)
    context = _build_stock_context(stock) if stock else f"{ticker} לא בסורק."

    if action == 'deep':
        prompt = f"תן ניתוח מעמיק על {ticker}. Health, RSI, Short, סקטור, ווליום, יעדים, סיכונים. תהיה ספציפי."
    elif action == 'entry':
        prompt = f"איפה נקודת כניסה טובה ל-{ticker}? יעד? סטופ? position sizing?"
    elif action == 'news':
        prompt = f"מה החדשות האחרונות על {ticker}? מה ההשפעה על המניה?"
    elif action == 'ta':
        return (await _cmd_ta(ticker), ticker)
    else:
        prompt = f"ספר לי על {ticker}"

    return (_chat_with_ai(prompt, context, stock_data=stock), ticker)


# ─── Structured command implementations ──────────────────────────────────────
async def _cmd_status() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/smart-portfolio/status", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        equity = data.get('equity', 0)
        pnl = data.get('total_pnl', 0)
        pnl_pct = data.get('total_pnl_pct', 0)
        daily = data.get('daily_pnl', 0)
        cash = data.get('cash', 0)
        positions = data.get('positions', {})
        win_rate = data.get('win_rate', 0)
        total_trades = data.get('total_trades', 0)
        max_dd = data.get('max_drawdown', 0)
        sharpe = data.get('sharpe_ratio', 0)
        profit_factor = data.get('profit_factor', 0)
        best = data.get('best_trade')
        worst = data.get('worst_trade')

        emoji = '📈' if pnl >= 0 else '📉'
        daily_emoji = '🟢' if daily >= 0 else '🔴'

        lines = [
            f"{emoji} <b>מצב התיק</b>\n",
            f"💰 הון כולל: <b>${equity:,.0f}</b>",
            f"📊 רווח/הפסד: <b>${pnl:+,.2f}</b> ({pnl_pct:+.1f}%)",
            f"{daily_emoji} היום: <b>${daily:+,.2f}</b>",
            f"💵 מזומן: ${cash:,.0f}",
            f"📦 פוזיציות: {len(positions)}/5\n",
        ]

        if total_trades > 0:
            lines.append(f"📊 <b>ביצועים</b>")
            lines.append(f"  Win rate: {win_rate:.0f}% ({total_trades} עסקאות)")
            lines.append(f"  Profit factor: {profit_factor:.1f}")
            lines.append(f"  Sharpe: {sharpe}")
            lines.append(f"  Max drawdown: {max_dd:.1f}%")
            if best:
                lines.append(f"  🏆 הכי טוב: {best.get('ticker')} ({best.get('pnl_pct', 0):+.1f}%)")
            if worst:
                lines.append(f"  💔 הכי גרוע: {worst.get('ticker')} ({worst.get('pnl_pct', 0):+.1f}%)")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ לא הצלחתי לשלוף נתונים: {e}"


async def _cmd_portfolio() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/smart-portfolio/status", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        positions = data.get('positions', {})
        if not positions:
            return "📦 אין פוזיציות פתוחות כרגע. ממתין להזדמנות..."

        # Fetch live stock data for squeeze info
        tickers = list(positions.keys())
        stock_map = {}
        try:
            tickers_str = ','.join(tickers)
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://localhost:8000/api/screener/finviz-table?filters=cap_midover,sh_avgvol_o2000,sh_instown_o10&ensure_tickers={tickers_str}",
                    timeout=aiohttp.ClientTimeout(total=8)
                ) as resp:
                    sdata = await resp.json()
            for s in sdata.get('stocks', []):
                stock_map[s.get('ticker', '')] = s
        except Exception:
            pass

        equity = data.get('equity', 0)
        total_pnl_pct = data.get('total_pnl_pct', 0)
        lines = [f"💼 <b>פוזיציות פתוחות</b> ({len(positions)}/5) | הון: ${equity:,.0f} ({total_pnl_pct:+.1f}%)\n"]

        for ticker, pos in positions.items():
            entry = pos.get('entry_price', 0)
            current = pos.get('current_price', entry)
            pnl_pct = ((current - entry) / entry * 100) if entry else 0
            emoji = '🟢' if pnl_pct >= 0 else '🔴'

            sd = stock_map.get(ticker, {})
            sq_stage = sd.get('squeeze_stage', '')
            trailing = '🔄' if pos.get('trailing_active') else ''

            line = (
                f"{emoji} <b>{ticker}</b> — ${current:.2f} ({pnl_pct:+.1f}%) {trailing}\n"
                f"   כניסה: ${entry:.2f} | סטופ: ${pos.get('stop_loss', 0):.2f} | יעד: ${pos.get('target', 0):.2f}"
            )
            if sq_stage:
                line += f"\n   🩳 סקוויז: {sq_stage}"
            if pos.get('partial_taken'):
                line += " | חלקי נלקח ✓"
            lines.append(line)

        # Stats summary
        win_rate = data.get('win_rate', 0)
        total_trades = data.get('total_trades', 0)
        if total_trades > 0:
            lines.append(f"\n📊 Win rate: {win_rate:.0f}% ({total_trades} עסקאות)")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ שגיאה: {e}"


async def _cmd_brain() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/smart-portfolio/status", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        last = data.get('last_decision', {}).get('decision', {})
        positions = data.get('positions', {})
        equity = data.get('equity', 0)
        pnl_pct = data.get('total_pnl_pct', 0)
        win_rate = data.get('win_rate', 0)
        max_dd = data.get('max_drawdown', 0)
        sharpe = data.get('sharpe_ratio', 0)
        profit_factor = data.get('profit_factor', 0)
        daily_pnl = data.get('daily_pnl', 0)

        context = (
            f"תיק: ${equity:.0f} ({pnl_pct:+.1f}%), {len(positions)}/5 פוזיציות.\n"
            f"יום: ${daily_pnl:+.2f} | Win rate: {win_rate:.0f}% | "
            f"Profit factor: {profit_factor:.1f} | Sharpe: {sharpe} | Max DD: {max_dd:.1f}%"
        )
        if last:
            context += (f"\nהחלטה אחרונה: {last.get('action')} {last.get('ticker', '')} "
                       f"(confidence {last.get('confidence', 0)}%). סיבה: {last.get('reason', '')}.")
        if positions:
            pos_details = []
            for t, p in positions.items():
                entry = p.get('entry_price', 0)
                current = p.get('current_price', entry)
                pos_pnl = ((current - entry) / entry * 100) if entry else 0
                trail = " 🔄trail" if p.get('trailing_active') else ""
                pos_details.append(f"{t} ({pos_pnl:+.1f}%{trail})")
            context += f"\nפוזיציות: {', '.join(pos_details)}"

        # Recent trade history for pattern analysis
        history = data.get('trade_history', [])
        if history:
            recent = history[-5:]
            context += "\nעסקאות אחרונות: " + ", ".join(
                f"{t.get('ticker')} {t.get('pnl_pct', 0):+.1f}% ({t.get('exit_reason', '')})"
                for t in reversed(recent))

        market = await _fetch_market_context()
        if market:
            context += f"\n{market}"

        return _chat_with_ai(
            "מה המצב? מה החלטת אחרונה? על מה אתה מסתכל עכשיו? "
            "תן ניתוח ספציפי: האם התיק מנוהל נכון? מה צריך לשנות? "
            "תגיד אם יש סקוויזים חזקים שכדאי לשקול.",
            context
        )
    except Exception as e:
        return f"❌ שגיאה: {e}"


async def _cmd_market() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/smart-portfolio/market-regime", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        regime = data.get('type', 'unknown')
        regime_map = {'bullish': '🟢 שורי', 'bearish': '🔴 דובי', 'volatile': '⚡ תנודתי', 'neutral': '⚪ ניטרלי'}
        breadth = data.get('breadth', 0)
        vol = data.get('volatility', 'normal')
        sectors = data.get('hot_sectors', [])

        lines = [f"🌍 <b>משטר שוק: {regime_map.get(regime, regime)}</b>\n"]
        lines.append(f"📊 רוחב שוק: {breadth:+.0f}%")
        lines.append(f"📈 תנודתיות: {vol}")
        if sectors:
            lines.append(f"\n🔥 <b>סקטורים חמים:</b>")
            for s in sectors[:5]:
                lines.append(f"  • {s.get('name', '')} ({s.get('avg_change', 0):+.1f}%)")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ שגיאה: {e}"


async def _cmd_top() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/screener/finviz-table?filters=cap_midover,sh_avgvol_o2000,sh_instown_o10", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        stocks = data.get('stocks', [])
        if not stocks:
            return "📊 אין נתונים עדיין. הסורק טוען..."

        top = sorted(stocks, key=lambda s: _safe_float(s.get('health_score'), 0), reverse=True)[:5]
        lines = ["🔥 <b>Top 5 מניות</b>\n"]
        for i, s in enumerate(top, 1):
            chg = _safe_float(s.get('change_pct'), 0)
            emoji = '🟢' if chg >= 0 else '🔴'
            sf = _safe_float(s.get('short_float'), 0)
            short_tag = f" | 🩳{sf:.0f}%" if sf > 10 else ""
            ts = s.get('tech_score')
            ta_tag = f" | TA {ts:+d}" if ts is not None else ""
            lines.append(
                f"{i}. {emoji} <b>{s.get('ticker', '?')}</b> ${s.get('price', 0)} ({chg:+.1f}%) "
                f"— Health {s.get('health_score', 0)}{ta_tag}{short_tag}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"❌ שגיאה: {e}"


async def _cmd_insider() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/screener/finviz-table?filters=cap_midover,sh_avgvol_o2000,sh_instown_o10", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        stocks = data.get('stocks', [])
        if not stocks:
            return "📊 אין נתונים עדיין."

        insiders = []
        for s in stocks:
            it = s.get('insider_trans') or s.get('insider_own') or ''
            try:
                it_val = float(str(it).replace('%', '').replace(',', ''))
            except (ValueError, TypeError):
                it_val = 0
            if abs(it_val) > 1:
                insiders.append((s, it_val))
        insiders.sort(key=lambda x: abs(x[1]), reverse=True)

        if not insiders:
            return "🏷️ אין פעילות אנשי פנים בולטת כרגע."

        lines = ["🏷️ <b>פעילות אנשי פנים</b>\n"]
        for s, val in insiders[:8]:
            emoji = '🟢' if val > 0 else '🔴'
            action = 'קונים' if val > 0 else 'מוכרים'
            lines.append(f"{emoji} <b>{s.get('ticker', '?')}</b> — אנשי פנים {action} ({val:+.1f}%) | ${s.get('price', 0)}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ שגיאה: {e}"


async def _cmd_history() -> str:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("http://localhost:8000/api/smart-portfolio/status", timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
        history = data.get('trade_history', [])
        if not history:
            return "📜 אין היסטוריית עסקאות עדיין."

        recent = history[-8:]
        lines = ["📜 <b>עסקאות אחרונות</b>\n"]
        for t in reversed(recent):
            pnl = t.get('pnl', 0)
            emoji = '💰' if pnl >= 0 else '🔴'
            lines.append(
                f"{emoji} <b>{t.get('ticker', '?')}</b> — ${pnl:+.2f} ({t.get('pnl_pct', 0):+.1f}%) | {t.get('exit_reason', '')}"
            )
        return "\n".join(lines)
    except Exception as e:
        return f"❌ שגיאה: {e}"


async def _cmd_squeeze() -> str:
    """Show active squeeze setups with catalyst info."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8000/api/screener/finviz-table?filters=cap_midover,sh_avgvol_o2000,sh_instown_o10",
                timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                data = await resp.json()
        stocks = data.get('stocks', [])
        if not stocks:
            return "📊 אין נתונים עדיין. הסורק טוען..."

        squeeze_plays = []
        for s in stocks:
            sq_stage = s.get('squeeze_stage', '')
            sq_score = s.get('squeeze_total_score')
            if not sq_stage or not sq_score or sq_score < 30:
                continue
            squeeze_plays.append((sq_score, s))

        if not squeeze_plays:
            return "🩳 אין סקוויזים פעילים כרגע. ממתין לסטאפ..."

        squeeze_plays.sort(key=lambda x: -x[0])
        lines = ["🩳 <b>סקוויזים פעילים</b>\n"]

        for score, s in squeeze_plays[:8]:
            ticker = s.get('ticker', '?')
            chg = _safe_float(s.get('change_pct'), 0)
            sf = _safe_float(s.get('short_float'), 0)
            sr = _safe_float(s.get('short_ratio'), 0)
            price = s.get('price', 0)
            stage = s.get('squeeze_stage', '')
            catalyst = s.get('squeeze_catalyst', '')
            has_cat = s.get('squeeze_has_catalyst', False)
            entry = s.get('squeeze_entry', '')
            fr = s.get('float_rotation')

            emoji = '🔥' if score >= 60 else '⚡' if score >= 45 else '📊'
            cat_tag = " 🔥קטליסט" if has_cat else ""

            line = (
                f"{emoji} <b>{ticker}</b> ${price} ({chg:+.1f}%) — "
                f"ציון {score}{cat_tag}\n"
                f"   שלב: {stage} | שורט: {sf:.0f}% | DTC: {sr:.1f}"
            )
            if fr is not None:
                line += f" | סיבוב: {fr}x"
            if catalyst:
                line += f"\n   קטליסט: {catalyst}"
            if entry:
                line += f"\n   כניסה: {entry}"
            lines.append(line)

        # AI summary of top squeeze
        top_ticker = squeeze_plays[0][1].get('ticker', '')
        top_stock = squeeze_plays[0][1]
        context = _build_stock_context(top_stock)
        ai_insight = _chat_with_ai(
            f"תן סיכום קצר (3 משפטים) על הסקוויז הכי חזק עכשיו: {top_ticker}. למה הוא מעניין? מה הסיכון?",
            context, stock_data=top_stock)
        lines.append(f"\n💡 <b>תובנה על {top_ticker}:</b>\n{ai_insight}")

        return "\n".join(lines)
    except Exception as e:
        return f"❌ שגיאה: {e}"


async def _cmd_news(ticker: str = None) -> str:
    """Get latest news — for a specific stock or general market."""
    if ticker:
        stock = await _fetch_stock_data(ticker)
        if stock and stock.get('news'):
            news = stock['news']
            lines = [f"📰 <b>חדשות על {ticker}</b>\n"]
            for n in news[:6]:
                title = n.get('title_he') or n.get('title', '')
                when = n.get('published', '')
                if title:
                    time_str = f" <i>({when})</i>" if when else ""
                    lines.append(f"• {title}{time_str}")
            if len(lines) == 1:
                lines.append("אין חדשות אחרונות.")
            context = _build_stock_context(stock)
            ai_summary = _chat_with_ai(
                f"סכם בקצרה את החדשות האחרונות על {ticker} ומה ההשפעה על המניה. 2-3 משפטים.",
                context,
                stock_data=stock)
            lines.append(f"\n💡 <b>סיכום:</b>\n{ai_summary}")
            return "\n".join(lines)
        else:
            return _chat_with_ai(
                f"מה החדשות האחרונות על {ticker}? מה ההשפעה על המניה?",
                f"{ticker} — אין חדשות בסורק. ענה על סמך הידע שלך.")

    # General market news
    market_ctx = await _fetch_market_context()
    if not market_ctx:
        return "📰 אין חדשות זמינות כרגע. נסי שוב בעוד דקה."
    return _chat_with_ai(
        "סכם את החדשות האחרונות מהשוק. מה הכותרות? מה משפיע על המניות היום? תהיה ספציפי.",
        market_ctx)


async def _cmd_ta(ticker: str) -> str:
    """Dedicated Technical Analysis command — builds a structured TA report."""
    stock = await _fetch_stock_data(ticker)
    if not stock:
        return f"❌ <b>{ticker}</b> לא נמצאה בסורק. נסי /force {ticker} לניתוח כללי."

    signal = stock.get('tech_signal', '')
    score = stock.get('tech_score')
    timing = stock.get('tech_timing', '')
    timing_up = stock.get('tech_timing_up', '')
    timing_down = stock.get('tech_timing_down', '')
    support = stock.get('tech_support')
    resistance = stock.get('tech_resistance')
    detail = stock.get('tech_detail', '')
    patterns = stock.get('tech_patterns', '')
    indicators = stock.get('tech_indicators', {})

    if not signal:
        return (f"⏳ <b>{ticker}</b> — הניתוח הטכני עדיין נטען.\n"
                f"המערכת מחשבת אינדיקטורים ב-background. נסי שוב בעוד 30 שניות.")

    signal_emoji = {'Strong Buy': '🟢🟢', 'Buy': '🟢', 'Neutral': '🟡',
                    'Sell': '🔴', 'Strong Sell': '🔴🔴'}.get(signal, '⚪')
    signal_he = {'Strong Buy': 'קנייה חזקה', 'Buy': 'קנייה', 'Neutral': 'ניטרלי',
                 'Sell': 'מכירה', 'Strong Sell': 'מכירה חזקה'}.get(signal, signal)
    score_emoji = '🔥' if score and score > 30 else '❄️' if score and score < -30 else '➡️'

    lines = [
        f"📈 <b>ניתוח טכני — {ticker}</b>\n",
        f"{signal_emoji} <b>סיגנל: {signal_he}</b>",
        f"{score_emoji} ציון: <b>{score:+d}</b> (מתוך -100 עד +100)\n",
    ]

    if timing:
        lines.append(f"⏱ <b>תזמון:</b> {timing}\n")
    if timing_up:
        lines.append(f"📈 <b>צפי עלייה (שעון ישראל):</b> {timing_up}")
        if stock.get('tech_timing_up_desc'):
            lines.append(f"   <i>{stock.get('tech_timing_up_desc')}</i>")
        lines.append("")
    if timing_down:
        lines.append(f"📉 <b>צפי ירידה (שעון ישראל):</b> {timing_down}")
        if stock.get('tech_timing_down_desc'):
            lines.append(f"   <i>{stock.get('tech_timing_down_desc')}</i>")
        lines.append("")
    if support is not None or resistance is not None:
        s_str = f"${float(support):.2f}" if support is not None else "?"
        r_str = f"${float(resistance):.2f}" if resistance is not None else "?"
        lines.append(f"📍 <b>תמיכה / התנגדות:</b> {s_str} / {r_str}\n")

    if detail:
        lines.append("<b>📊 פירוט אינדיקטורים:</b>")
        for part in detail.split(' | '):
            lines.append(f"  • {part}")
        lines.append("")

    if patterns:
        lines.append(f"🕯 <b>דפוסי נרות:</b> {patterns}\n")

    if indicators:
        ti = indicators
        rsi5_color = '🔴' if ti.get('rsi_5m', 50) > 70 else '🟢' if ti.get('rsi_5m', 50) < 30 else '⚪'
        rsi1h_color = '🔴' if ti.get('rsi_1h', 50) > 70 else '🟢' if ti.get('rsi_1h', 50) < 30 else '⚪'
        vwap_he = 'מעל ↑' if ti.get('vwap_bias') == 'bullish' else 'מתחת ↓' if ti.get('vwap_bias') == 'bearish' else '—'

        lines.append("<b>🔢 מדדים מרכזיים:</b>")
        lines.append(f"  {rsi5_color} RSI 5m: <b>{ti.get('rsi_5m', '?')}</b>")
        lines.append(f"  {rsi1h_color} RSI 1h: <b>{ti.get('rsi_1h', '?')}</b>")
        lines.append(f"  📍 VWAP: <b>{vwap_he}</b>")
        lines.append(f"  📏 ADX 1h: <b>{ti.get('adx_1h', '?')}</b>")
        lines.append(f"  📐 BB position: <b>{int(ti.get('bb_position_5m', 0.5) * 100)}%</b>")
        lines.append(f"  📉 Stochastic K: <b>{ti.get('stoch_k_5m', '?')}</b>")
        lines.append(f"  📊 EMA 5m: <b>{ti.get('ema_cross_5m', '?')}</b> | EMA 1h: <b>{ti.get('ema_cross_1h', '?')}</b>")
        if ti.get('bb_squeeze'):
            lines.append("  ⚡ <b>Bollinger Squeeze פעיל — פריצה צפויה!</b>")

    context = _build_stock_context(stock)
    ai_insight = _chat_with_ai(
        f"בהתבסס על הניתוח הטכני של {ticker}, תן 2-3 משפטים: מה המסקנה? מתי כדאי להיכנס/לצאת? מה הסיכונים?",
        context,
        stock_data=stock)
    lines.append(f"\n💡 <b>תובנה:</b>\n{ai_insight}")

    return "\n".join(lines)


async def _cmd_force(ticker: str) -> str:
    stock = await _fetch_stock_data(ticker)
    context = _build_stock_context(stock) if stock else f"{ticker} לא נמצאה בסורק כרגע. ענה על סמך הידע שלך."

    market = await _fetch_market_context()
    if market:
        context += f"\n{market}"

    return _chat_with_ai(
        f"תנתח לי את {ticker} עכשיו. כדאי להיכנס? לכמה יעד? איפה סטופ? תהיה ספציפי עם מספרים.",
        context,
        stock_data=stock
    )


# ─── Main bot loop ───────────────────────────────────────────────────────────
async def start_telegram_bot():
    """Background task: poll Telegram for incoming messages and respond."""
    global _LAST_UPDATE_ID, _BOT_RUNNING

    if _BOT_RUNNING:
        return
    _BOT_RUNNING = True

    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        print("[TG Bot] No token/chat_id configured, bot disabled")
        _BOT_RUNNING = False
        return

    print(f"[TG Bot] v6 Scout Edition started — model: {_PRIMARY_MODEL} (fallback: {_FALLBACK_MODEL})")

    while True:
        try:
            updates = await _get_updates(_LAST_UPDATE_ID)
            for update in updates:
                _LAST_UPDATE_ID = update['update_id'] + 1

                # Handle callback queries (inline keyboard buttons)
                callback = update.get('callback_query')
                if callback:
                    cb_chat_id = str(callback.get('message', {}).get('chat', {}).get('id', ''))
                    if cb_chat_id == chat_id:
                        cb_data = callback.get('data', '')
                        cb_id = callback.get('id', '')
                        print(f"[TG Bot] Callback: {cb_data}")
                        response, ticker = await _handle_callback(cb_data, cb_id)
                        await _send_with_keyboard(response, ticker)
                    continue

                # Handle regular messages
                msg = update.get('message', {})
                msg_chat_id = str(msg.get('chat', {}).get('id', ''))
                text = msg.get('text', '').strip()

                if not text or msg_chat_id != chat_id:
                    continue

                print(f"[TG Bot] Got message: {text[:50]}")
                response, ticker = await _handle_command(text)
                await _send_with_keyboard(response, ticker)

        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"[TG Bot] Error in poll loop: {e}")
            await asyncio.sleep(5)
