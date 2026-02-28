"""
Real-time trading context builder for the AI assistant.
Assembles data from cached dashboard sources into a concise context string
that is injected into every Claude conversation.
"""

from datetime import datetime
from typing import Dict
import pytz

from app.services import portfolio_service

_ET = pytz.timezone("America/New_York")


def build_trading_context(response_cache: Dict) -> str:
    """
    Assemble real-time context from:
    - Demo portfolio (live P&L, positions, trades)
    - Daily briefing stocks (earnings beat, RSI, tailwinds)
    - Market status (SPY / QQQ)
    Returns a markdown-formatted string to inject into the system prompt.
    """
    now_et = datetime.now(_ET).strftime("%A, %d/%m/%Y  %H:%M ET")
    parts = [f"## זמן ותאריך\n{now_et}"]

    # ── Portfolio ──────────────────────────────────────────────────────────────
    try:
        portfolio = portfolio_service.get_portfolio_with_live_prices()
        positions = portfolio.get("positions", [])
        cash = portfolio.get("cash", 0)
        total_value = portfolio.get("total_value", 0)
        total_pnl_pct = portfolio.get("total_pnl_pct", 0)
        total_pnl_dollar = portfolio.get("total_pnl_dollar", 0)

        if positions:
            pnl_sign = "+" if total_pnl_pct >= 0 else ""
            header = (
                f"שווי כולל: ${total_value:,.0f} | "
                f"P&L: {pnl_sign}{total_pnl_pct:.1f}% (${total_pnl_dollar:+,.0f}) | "
                f"מזומן: ${cash:,.0f}"
            )
            lines = []
            for pos in positions:
                pnl_pct = pos.get("pnl_pct", 0)
                pnl_d = pos.get("pnl_dollar", 0)
                sign = "+" if pnl_pct >= 0 else ""
                lines.append(
                    f"- **{pos['ticker']}** ({pos.get('company', '')[:22]}): "
                    f"קנייה ${pos['buy_price']} → עכשיו ${pos.get('current_price', '?')} "
                    f"({sign}{pnl_pct:.1f}%, {sign}${pnl_d:.0f})"
                    + (f" | יעד: {pos['watch_level']}" if pos.get("watch_level") else "")
                )
            parts.append("## תיק דמו — פוזיציות פתוחות\n" + header + "\n\n" + "\n".join(lines))
        else:
            parts.append(f"## תיק דמו\nאין פוזיציות פתוחות. מזומן זמין: ${cash:,.0f}")

        trades = portfolio.get("trades", [])[-6:]
        if trades:
            tlines = []
            for t in reversed(trades):
                pnl_str = f" | רווח: ${t['pnl']:+.0f}" if t.get("pnl") is not None else ""
                tlines.append(f"- {t['action']} {t['ticker']} @ ${t['price']} ({t['date']}){pnl_str}")
            parts.append("## עסקאות אחרונות\n" + "\n".join(tlines))
    except Exception:
        pass

    # ── Daily briefing ─────────────────────────────────────────────────────────
    briefing = response_cache.get("briefing_daily", {})
    briefing_stocks = briefing.get("stocks", [])
    if briefing_stocks:
        slines = []
        for s in briefing_stocks[:10]:
            tws = " | ".join(s.get("tailwinds", [])[:2])
            hws = " | ".join(s.get("headwinds", [])[:1])
            wind = ""
            if tws:
                wind += f" ▲ {tws}"
            if hws:
                wind += f" ▼ {hws}"
            slines.append(
                f"- **{s['ticker']}** ({s.get('company','')[:22]}): "
                f"beat +{s.get('earnings_surprise_pct',0):.0f}% | "
                f"RSI {s.get('rsi',0):.0f} | ${s.get('price',0):.2f}"
                + wind
            )
        parts.append(
            "## בריפינג יומי — מניות עם earnings beat\n"
            + "\n".join(slines)
        )

    # ── Market status ──────────────────────────────────────────────────────────
    market = briefing.get("market_status", {})
    if market.get("summary"):
        spy = market.get("spy", {})
        qqq = market.get("qqq", {})
        spy_str = f"SPY ${spy.get('price', 0)} ({spy.get('change_pct', 0):+.2f}%)"
        qqq_str = f"QQQ ${qqq.get('price', 0)} ({qqq.get('change_pct', 0):+.2f}%)"
        parts.append(f"## מצב שוק\n{spy_str} | {qqq_str}\n{market.get('summary', '')}")

    return "\n\n".join(parts)


SYSTEM_PROMPT_TEMPLATE = """\
אתה עוזרת AI מקצועית לניתוח מניות ומסחר. את עובדת עם טריידרית מקצועית ישראלית.

להלן הנתונים העדכניים שלה מהדשבורד — קראי אותם לפני שאת עונה:

{context}

---
הנחיות:
- עני תמיד בעברית, בסגנון ישיר ומקצועי של טריידרית
- כשמדברים על מניה בתיק — התייחסי ל-P&L ולמחיר הנוכחי שרואים למעלה
- כשמדברים על מניה מהבריפינג — ציירי את ה-beat, RSI, tailwinds
- תשובות קצרות ומעשיות — לא הרצאה אקדמית, אלא שותפה מסחרית
- אל תמציאי מחירים שלא בקונטקסט — תגידי "אין לי את המחיר הנוכחי"
- אם שואלים על הזדמנויות — השוואי גם למניות מהבריפינג שלא נקנו\
"""
