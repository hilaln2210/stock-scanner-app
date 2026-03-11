"""
Alerts service — Telegram Bot + Email daily summary.
Uses Groq AI to generate human-like Hebrew messages.
"""
import aiohttp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Optional
import asyncio
import json

from groq import Groq, APIError as GroqAPIError
from app.config import settings

_SIGNAL_LOG: list = []


async def send_telegram(message: str, parse_mode: str = 'HTML') -> bool:
    """Send a message via Telegram Bot API."""
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {'chat_id': chat_id, 'text': message, 'parse_mode': parse_mode}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    err = await resp.text()
                    print(f"[Telegram] Error {resp.status}: {err[:200]}")
                return resp.status == 200
    except Exception as e:
        print(f"[Telegram] Error: {e}")
        return False


async def send_telegram_with_buttons(message: str, buttons: list, parse_mode: str = 'HTML') -> bool:
    """Send a Telegram message with inline keyboard buttons.
    buttons = [[{'text': '...', 'callback_data': '...'}, ...], ...]  (rows of button dicts)
    """
    token = settings.telegram_bot_token
    chat_id = settings.telegram_chat_id
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': parse_mode,
        'reply_markup': json.dumps({'inline_keyboard': buttons}),
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                return resp.status == 200
    except Exception as e:
        print(f"[Telegram] send_with_buttons error: {e}")
        return False


def _humanize_signal(signal: dict) -> str:
    """Use Groq to generate a human-like Hebrew Telegram message."""
    api_key = settings.groq_api_key
    if not api_key:
        return _fallback_message(signal)

    action = signal.get('action', 'SIGNAL')
    ticker = signal.get('ticker', '?')
    price = signal.get('price', 0)
    target = signal.get('target', 0)
    stop = signal.get('stop_loss', 0)
    confidence = signal.get('confidence', 0)
    reason = signal.get('reason', '')
    analysis = signal.get('analysis', '')
    engine = signal.get('engine', '')
    squeeze_stage = signal.get('squeeze_stage', '')
    squeeze_score = signal.get('squeeze_total_score', 0)
    squeeze_catalyst = signal.get('squeeze_catalyst', '')
    short_float = signal.get('short_float', 0)
    dtc = signal.get('short_ratio', 0)

    pnl_pct = 0
    if action in ('CLOSED', 'SMART_EXIT'):
        entry_str = signal.get('entry_price', 0)
        try:
            entry_p = float(entry_str)
        except (ValueError, TypeError):
            entry_p = 0
        if entry_p > 0 and price > 0:
            pnl_pct = round((price - entry_p) / entry_p * 100, 1)

    prompt = f"""אתה סוחר מניות ישראלי מנוסה שגם חבר טוב. אתה גאון פיננסי שמסביר דברים בגובה העיניים.
אתה שולח הודעת טלגרם לחבר שלך על פעולה שעשית בתיק.

הסגנון שלך:
- אתה מדבר כמו חבר חכם שיודע מה הוא עושה, לא כמו רובוט
- אתה מסביר את ה-WHY — למה דווקא המניה הזאת, דווקא עכשיו
- אתה משתמש במונחים מקצועיים אבל מסביר אותם בקצרה אם צריך
- אתה ישיר ותכליתי, לא מפטפט
- אתה שם את המספרים החשובים (מחיר כניסה, יעד, סטופ) בצורה ברורה
- אם יש סקוויז/מומנטום חזק — אתה מתלהב אבל לא מאבד שליטה
- אם מצב לא ברור — אתה אומר את זה בכנות

פעולה: {action}
מניה: {ticker}
מחיר: ${price:.2f}
יעד: ${target:.2f}
סטופ לוס: ${stop:.2f}
ביטחון: {confidence}%
סיבה: {reason}
ניתוח נוסף: {analysis}
{"רווח/הפסד: " + str(pnl_pct) + "%" if pnl_pct else ""}
{f"סקוויז: שלב {squeeze_stage}, ציון {squeeze_score}" if squeeze_stage else ""}
{f"שורט פלואט: {short_float}%, DTC: {dtc}" if short_float else ""}
{f"קטליסט: {squeeze_catalyst}" if squeeze_catalyst else ""}

מבנה ההודעה (2 שורות בלבד — ללא שורת יעד/סטופ, אני אוסיף אותה בנפרד):
1. שורה ראשונה — אימוג'י + <b>טיקר</b> + פעולה + מחיר. קצר וחד.
2. 1-2 שורות הסבר — למה? מה ראיתי? מה המשחק? תהיה ספציפי ומדויק.
   אל תכתוב ביטויים כלליים כמו "מרמז על עתיד חיובי" — כתוב עובדות קונקרטיות.
   אל תשתמש במונחים מתורגמים גרועים — "פתיחת שוק" ולא "פתיחת בית", "שוק" ולא "בית".
   אם CLOSED — כתוב סיכום תוצאה בשורה 2.

דוגמה BUY:
🟢 <b>TTD</b> — נכנסתי ב-$85.50
שורט פלואט 10%, פריצה עם ווליום פי 6, הסקטור חם. ריח סקוויז.

דוגמה BUY ביטחון נמוך:
⚠️ <b>COIN</b> — נכנסתי ב-$215, יד על הסטופ
שורט 22%, DTC 5 ימים — מפתה. אבל RSI 72 ושוק תנודתי — פוזיציה קטנה.

דוגמה CLOSED רווח:
💰 <b>AVGO</b> — סגרתי ב-$355, רווח +4.2%
טריילינג סטופ נעל רווח אוטומטית. עסקה נקייה.

דוגמה CLOSED הפסד:
🔴 <b>PENN</b> — סגרתי ב-$18.50, הפסד -6.1%
המומנטום דעך מהר, נפלנו לסטופ. לומדים.

דוגמה BUY סקוויז:
🩳🔥 <b>CVNA</b> — נכנסתי ב-$72, סקוויז פעיל!
שורט 28%, DTC 6 ימים, ווליום פי 8. דוח רבעוני beat +40%. השורטים נלחצים.

כתוב ב-HTML בלבד: <b>bold</b>. ללא markdown. מקסימום 250 תווים."""

    try:
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.7,
            max_completion_tokens=300,
        )
        text = completion.choices[0].message.content.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1] if '\n' in text else text[3:]
            if text.endswith('```'):
                text = text[:-3]
            text = text.strip()
        text = _sanitize_html(text)
        # Always append hardcoded stop/target line — AI numbers are unreliable
        if action not in ('CLOSED', 'SMART_EXIT') and target > 0 and stop > 0:
            text = text + f"\n🎯 יעד: <b>${target:.2f}</b>  |  🛑 סטופ: <b>${stop:.2f}</b>"
        elif action in ('CLOSED', 'SMART_EXIT') and pnl_pct:
            pass  # AI handles the P&L line for closed trades
        return text
    except Exception as e:
        print(f"[Telegram AI] Groq error: {e}")
        return _fallback_message(signal)


def _sanitize_html(text: str) -> str:
    """Keep only Telegram-safe HTML tags, strip everything else."""
    import re
    allowed = {'b', 'i', 'u', 's', 'code', 'pre', 'a'}
    def _replace_tag(m):
        tag = m.group(1).replace('/', '').split()[0].lower()
        if tag in allowed:
            return m.group(0)
        return ''
    text = re.sub(r'<(/?\w[^>]*)>', _replace_tag, text)
    # Fix unclosed tags — just strip them all if there's a mismatch
    for tag in allowed:
        opens = text.count(f'<{tag}>') + text.count(f'<{tag} ')
        closes = text.count(f'</{tag}>')
        while closes < opens:
            text += f'</{tag}>'
            closes += 1
    return text


def _fallback_message(signal: dict) -> str:
    """Structured fallback when AI is unavailable."""
    action_emoji = {
        'BUY': '🟢', 'SELL': '🔴', 'SHORT': '🔻',
        'HOLD': '⏸', 'CLOSED': '🔒', 'SMART_EXIT': '🧠'
    }.get(signal.get('action', ''), '📊')

    return (
        f"{action_emoji} <b>{signal.get('action', 'SIGNAL')} {signal.get('ticker', '?')}</b>\n"
        f"💰 ${signal.get('price', 0):.2f} | "
        f"🎯 ${signal.get('target', 0):.2f} | "
        f"🛑 ${signal.get('stop_loss', 0):.2f}\n"
        f"📊 ביטחון: {signal.get('confidence', 0):.0f}%\n"
        f"📝 {signal.get('reason', '')}"
    )


async def send_signal_alert(signal: dict):
    """
    Send a human-like trading signal alert via Telegram.
    Uses Groq AI to generate natural Hebrew messages.
    """
    msg = _humanize_signal(signal)
    _SIGNAL_LOG.append({**signal, 'timestamp': datetime.now().isoformat()})
    await send_telegram(msg)


async def send_daily_summary_email():
    """Send daily summary of all signals and P&L via email."""
    if not settings.smtp_host or not settings.email_to:
        return False

    today_signals = [s for s in _SIGNAL_LOG
                     if s.get('timestamp', '').startswith(datetime.now().strftime('%Y-%m-%d'))]

    if not today_signals:
        return False

    buys = [s for s in today_signals if s.get('action') == 'BUY']
    sells = [s for s in today_signals if s.get('action') in ('SELL', 'SHORT')]

    html = f"""
    <h2>📊 סיכום יומי — {datetime.now().strftime('%d/%m/%Y')}</h2>
    <p>סה"כ סיגנלים: <b>{len(today_signals)}</b></p>
    <p>🟢 קניות: <b>{len(buys)}</b> | 🔴 מכירות: <b>{len(sells)}</b></p>
    <hr>
    <table border="1" cellpadding="4" style="border-collapse:collapse;">
    <tr><th>פעולה</th><th>מניה</th><th>מחיר</th><th>ביטחון</th><th>סיבה</th></tr>
    """
    for s in today_signals:
        html += f"<tr><td>{s.get('action','')}</td><td>{s.get('ticker','')}</td>"
        html += f"<td>${s.get('price',0):.2f}</td><td>{s.get('confidence',0):.0f}%</td>"
        html += f"<td>{s.get('reason','')}</td></tr>"
    html += "</table>"

    msg = MIMEMultipart('alternative')
    msg['Subject'] = f"📊 Stock Scanner — סיכום יומי {datetime.now().strftime('%d/%m')}"
    msg['From'] = settings.smtp_user
    msg['To'] = settings.email_to
    msg.attach(MIMEText(html, 'html'))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as server:
            server.starttls()
            server.login(settings.smtp_user, settings.smtp_pass)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f"[Email] Error: {e}")
        return False


def get_signal_log() -> list:
    return _SIGNAL_LOG[-100:]
