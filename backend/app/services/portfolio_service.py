"""
Demo Portfolio Service — paper trading simulation.

- Configurable portfolio size and budget per position
- Buy any stocks from the daily briefing (up to budget_per_position each)
- Tracks positions + P&L with live prices (parallel fetching)
- Persists to disk (survives restarts)
"""

import json
import pytz
from datetime import datetime, time as dtime
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import yfinance as yf

PORTFOLIO_FILE = "/tmp/demo_portfolio.json"
DEFAULT_INITIAL_CASH = 3000.0
DEFAULT_MAX_PER_POSITION = 700.0
_MAX_PRICE_WORKERS = 4

_ET = pytz.timezone("America/New_York")


def _market_session() -> str:
    """Return current market session label based on ET time."""
    now = datetime.now(_ET)
    t = now.time()
    wd = now.weekday()  # 0=Mon … 6=Sun
    if wd >= 5:
        return "סגור"
    if dtime(4, 0) <= t < dtime(9, 30):
        return "פריי-מרקט"
    if dtime(9, 30) <= t < dtime(16, 0):
        return "שוק פתוח"
    if dtime(16, 0) <= t < dtime(20, 0):
        return "אפטר-מרקט"
    return "סגור"


def _get_live_price(ticker: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Fetch the most recent price including pre/post-market data.
    Returns (price, price_time_iso) or (None, None).
    Uses prepost=True + 1m interval to capture all sessions.
    Falls back to 5m if 1m is empty.
    """
    try:
        stock = yf.Ticker(ticker)
        # 1-minute bars with pre/post market included
        hist = stock.history(period='1d', interval='1m', prepost=True, timeout=6)
        if hist is None or hist.empty:
            # fallback: 5m bars
            hist = stock.history(period='2d', interval='5m', prepost=True, timeout=6)
        if hist is not None and not hist.empty:
            price = round(float(hist['Close'].iloc[-1]), 2)
            ts = hist.index[-1]
            # Convert to ET string
            if hasattr(ts, 'tz_convert'):
                ts_et = ts.tz_convert(_ET)
            else:
                ts_et = ts
            price_time = ts_et.strftime("%H:%M")
            return price, price_time
    except Exception:
        pass
    return None, None


def _fetch_prices_parallel(tickers: List[str]) -> Dict[str, Tuple[Optional[float], Optional[str]]]:
    """Fetch prices for multiple tickers concurrently.
    Returns {ticker: (price, price_time)} — price_time is HH:MM ET."""
    if not tickers:
        return {}
    unique = list(set(tickers))
    results: Dict[str, Tuple] = {t: (None, None) for t in unique}
    with ThreadPoolExecutor(max_workers=min(len(unique), _MAX_PRICE_WORKERS)) as ex:
        future_to_ticker = {ex.submit(_get_live_price, t): t for t in unique}
        for future in as_completed(future_to_ticker, timeout=20):
            ticker = future_to_ticker[future]
            try:
                results[ticker] = future.result()
            except Exception:
                results[ticker] = (None, None)
    return results


def _load() -> Dict:
    try:
        with open(PORTFOLIO_FILE, 'r') as f:
            return json.load(f)
    except Exception:
        return _fresh_portfolio()


def _save(portfolio: Dict) -> None:
    try:
        with open(PORTFOLIO_FILE, 'w') as f:
            json.dump(portfolio, f, indent=2, default=str)
    except Exception:
        pass


def _fresh_portfolio(initial_cash: float = DEFAULT_INITIAL_CASH,
                     max_per_position: float = DEFAULT_MAX_PER_POSITION) -> Dict:
    return {
        "cash": initial_cash,
        "initial_cash": initial_cash,
        "max_per_position": max_per_position,
        "positions": [],
        "trades": [],
        "created_at": datetime.now().isoformat(),
    }


def get_portfolio_with_live_prices() -> Dict:
    """Load portfolio and enrich all positions with live prices + P&L (parallel, prepost=True)."""
    p = _load()
    positions = p.get("positions", [])
    session = _market_session()
    fetched_at = datetime.now(_ET).strftime("%H:%M")

    tickers = [pos["ticker"] for pos in positions]
    price_data = _fetch_prices_parallel(tickers)  # {ticker: (price, price_time)}

    enriched = []
    total_market_value = 0.0
    for pos in positions:
        ticker = pos["ticker"]
        live_price, price_time = price_data.get(ticker, (None, None))
        if live_price is None:
            live_price = pos.get("buy_price", 0)
            price_time = None

        shares = pos["shares"]
        cost_basis = pos["cost_basis"]
        market_value = round(shares * live_price, 2)
        pnl_dollar = round(market_value - cost_basis, 2)
        pnl_pct = round((pnl_dollar / cost_basis) * 100, 2) if cost_basis else 0.0

        total_market_value += market_value
        enriched.append({
            **pos,
            "current_price": live_price,
            "price_time": price_time,   # HH:MM ET of last trade
            "market_value": market_value,
            "pnl_dollar": pnl_dollar,
            "pnl_pct": pnl_pct,
        })

    cash = p.get("cash", 0)
    total_value = round(cash + total_market_value, 2)
    initial = p.get("initial_cash", DEFAULT_INITIAL_CASH)
    total_pnl_dollar = round(total_value - initial, 2)
    total_pnl_pct = round((total_pnl_dollar / initial) * 100, 2) if initial else 0.0

    return {
        "cash": round(cash, 2),
        "initial_cash": initial,
        "max_per_position": p.get("max_per_position", DEFAULT_MAX_PER_POSITION),
        "total_value": total_value,
        "total_pnl_dollar": total_pnl_dollar,
        "total_pnl_pct": total_pnl_pct,
        "positions": enriched,
        "trades": p.get("trades", [])[-30:],
        "created_at": p.get("created_at"),
        "session": session,
        "fetched_at": fetched_at,  # HH:MM ET
    }


def buy_selected_stocks(tickers: List[str], briefing_stocks: List[Dict]) -> Dict:
    """
    Buy specific tickers. Budget per position read from portfolio file.
    Pre-fetches all prices in parallel, skips already-held tickers.
    """
    p = _load()
    max_per_pos = p.get("max_per_position", DEFAULT_MAX_PER_POSITION)
    held_tickers = {pos["ticker"] for pos in p.get("positions", [])}
    briefing_map = {s["ticker"]: s for s in (briefing_stocks or [])}

    to_buy = []
    already_held = []
    for t in tickers:
        t = t.upper()
        if t in held_tickers:
            already_held.append(f"{t} (כבר מוחזקת)")
        elif t not in to_buy:
            to_buy.append(t)

    price_data = _fetch_prices_parallel(to_buy)  # {ticker: (price, price_time)}

    bought = []
    skipped = list(already_held)

    for ticker in to_buy:
        if p["cash"] < 10:
            skipped.append(f"{ticker} (אין מספיק מזומן)")
            break

        live_price, _ = price_data.get(ticker, (None, None))
        if not live_price or live_price <= 0:
            skipped.append(f"{ticker} (לא נמצא מחיר)")
            continue

        stock_meta = briefing_map.get(ticker, {})
        company = stock_meta.get("company", ticker)
        invest = min(max_per_pos, p["cash"])
        shares = round(invest / live_price, 6)
        cost = round(shares * live_price, 2)

        p["cash"] = round(p["cash"] - cost, 2)
        held_tickers.add(ticker)
        p["positions"].append({
            "ticker": ticker,
            "company": company,
            "shares": shares,
            "buy_price": live_price,
            "buy_date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "cost_basis": cost,
            "earnings_beat": stock_meta.get("earnings_surprise_pct"),
            "rsi_at_buy": stock_meta.get("rsi"),
            "watch_level": stock_meta.get("watch_level"),
            "support": stock_meta.get("support"),
            "resistance": stock_meta.get("resistance"),
        })
        p["trades"].append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "action": "BUY",
            "ticker": ticker,
            "shares": shares,
            "price": live_price,
            "value": cost,
        })
        bought.append({"ticker": ticker, "shares": shares, "price": live_price, "cost": cost})

    _save(p)
    return {"bought": bought, "skipped": skipped, "cash_remaining": round(p["cash"], 2)}


def sell_position(ticker: str) -> Dict:
    """Sell entire position in ticker at live price."""
    p = _load()
    positions = p.get("positions", [])
    pos = next((x for x in positions if x["ticker"] == ticker), None)
    if not pos:
        return {"error": f"{ticker} not in portfolio"}

    live_price, _ = _get_live_price(ticker)
    live_price = live_price or pos["buy_price"]
    proceeds = round(pos["shares"] * live_price, 2)
    pnl = round(proceeds - pos["cost_basis"], 2)

    p["cash"] = round(p["cash"] + proceeds, 2)
    p["positions"] = [x for x in positions if x["ticker"] != ticker]
    p["trades"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "action": "SELL",
        "ticker": ticker,
        "shares": pos["shares"],
        "price": live_price,
        "value": proceeds,
        "pnl": pnl,
    })
    _save(p)
    return {"ticker": ticker, "proceeds": proceeds, "pnl": pnl, "cash": round(p["cash"], 2)}


def set_portfolio_size(portfolio_size: float, budget_per_position: float) -> Dict:
    """
    Update portfolio size and budget per position without resetting positions.
    Adjusts available cash by the difference between old and new initial_cash.
    """
    portfolio_size = max(100.0, min(portfolio_size, 1_000_000.0))
    budget_per_position = max(10.0, min(budget_per_position, portfolio_size))

    p = _load()
    old_initial = p.get("initial_cash", DEFAULT_INITIAL_CASH)
    delta = round(portfolio_size - old_initial, 2)

    p["initial_cash"] = portfolio_size
    p["cash"] = round(max(0.0, p.get("cash", 0) + delta), 2)
    p["max_per_position"] = budget_per_position
    _save(p)

    return {
        "initial_cash": portfolio_size,
        "max_per_position": budget_per_position,
        "cash": p["cash"],
        "cash_delta": delta,
    }


def add_cash(amount: float) -> Dict:
    """Add cash to portfolio (simulate deposit). Also increases initial_cash baseline."""
    amount = max(0.0, min(round(amount, 2), 1_000_000.0))
    p = _load()
    p["cash"] = round(p.get("cash", 0) + amount, 2)
    p["initial_cash"] = round(p.get("initial_cash", DEFAULT_INITIAL_CASH) + amount, 2)
    _save(p)
    return {"added": amount, "cash": p["cash"], "initial_cash": p["initial_cash"]}


def reset_portfolio(initial_cash: float = DEFAULT_INITIAL_CASH,
                    max_per_position: float = DEFAULT_MAX_PER_POSITION) -> Dict:
    """Reset portfolio to fresh state with configurable size."""
    p = _fresh_portfolio(initial_cash=initial_cash, max_per_position=max_per_position)
    _save(p)
    return {"message": f"Portfolio reset to ${initial_cash:,.0f}", "cash": initial_cash}


# ── AI Portfolio Advisor ────────────────────────────────────────────────────

def _gen_missed_alert(ticker: str, change_pct: float, stock: Dict) -> str:
    beat = stock.get("earnings_surprise_pct")
    beat_str = f" (beat {beat:.0f}%)" if beat is not None else ""
    if change_pct >= 20:
        return f"🚨 {ticker}{beat_str} זינקה {change_pct:.1f}% מאז הבריפינג — פספסת תנועה גדולה!"
    elif change_pct >= 10:
        return f"⚠️ {ticker}{beat_str} עלתה {change_pct:.1f}% מאז הבריפינג — הזדמנות שעברה"
    else:
        return f"📈 {ticker}{beat_str} עלתה {change_pct:.1f}% מאז הבריפינג"


def _gen_position_comment(pos: Dict) -> str:
    ticker = pos.get("ticker", "")
    pnl_pct = pos.get("pnl_pct", 0)
    watch_level = pos.get("watch_level", "")
    support = pos.get("support")

    watch_hint = f" — עקבי אחרי: {watch_level}" if watch_level else ""
    support_hint = f" — תמיכה ב-${support:.2f}" if support else ""

    if pnl_pct >= 15:
        return f"🔥 ריצה חזקה של +{pnl_pct:.1f}%! שקלי לממש חלק מהרווח{watch_hint}"
    elif pnl_pct >= 8:
        return f"✅ +{pnl_pct:.1f}% — פוזיציה עובדת יפה{watch_hint}"
    elif pnl_pct >= 3:
        return f"📈 +{pnl_pct:.1f}% — תנועה חיובית{watch_hint}"
    elif pnl_pct >= -3:
        return f"⏳ {pnl_pct:+.1f}% — סביב נקודת הכניסה{support_hint}"
    elif pnl_pct >= -8:
        wl = f" {watch_level}" if watch_level else (support_hint or " רמת התמיכה")
        return f"⚠️ {pnl_pct:.1f}% — שמרי עין על{wl}"
    else:
        return f"🔴 {pnl_pct:.1f}% — בחני אם ההיסטוריה עדיין תקינה"


def _gen_overall_comment(portfolio: Dict) -> str:
    cash = portfolio.get("cash", 0)
    total_pnl_pct = portfolio.get("total_pnl_pct", 0)
    total_pnl_dollar = portfolio.get("total_pnl_dollar", 0)
    positions = portfolio.get("positions", [])
    n = len(positions)

    if n == 0:
        return f"התיק ריק — בחר מניות מהבריפינג. מזומן זמין: ${cash:,.0f}"

    sign = "+" if total_pnl_dollar >= 0 else "-"
    pnl_str = f"{sign}${abs(total_pnl_dollar):,.0f}"

    if total_pnl_pct >= 10:
        return f"💪 ביצועים מצוינים — {n} פוזיציות ב+{total_pnl_pct:.1f}% ({pnl_str}). מזומן: ${cash:,.0f}"
    elif total_pnl_pct >= 3:
        return f"📊 התיק ב+{total_pnl_pct:.1f}% ({pnl_str}) — {n} פוזיציות. מזומן זמין: ${cash:,.0f}"
    elif total_pnl_pct >= -2:
        return f"⚖️ התיק סביב נקודת האיזון ({total_pnl_pct:+.1f}%) — {n} פוזיציות. שמרי על דיסציפלינה"
    elif total_pnl_pct >= -8:
        return f"⚠️ התיק ב{total_pnl_pct:.1f}% ({pnl_str}) — בחני כל פוזיציה בנפרד. מזומן: ${cash:,.0f}"
    else:
        return f"🔴 התיק תחת לחץ — {total_pnl_pct:.1f}% ({pnl_str}). שקלי לצמצם חשיפה. מזומן: ${cash:,.0f}"


def analyze_portfolio(briefing_stocks: List[Dict]) -> Dict:
    """
    AI-style portfolio advisor:
    - Overall portfolio health comment
    - Per-position commentary (using live prices already fetched)
    - Missed opportunities: briefing stocks not held that rose ≥5% since briefing
    """
    # 1. Portfolio with live prices (positions already have pnl_pct computed)
    portfolio = get_portfolio_with_live_prices()
    positions = portfolio.get("positions", [])
    held_tickers = {pos["ticker"] for pos in positions}

    # 2. Per-position comments
    position_comments = []
    for pos in positions:
        position_comments.append({
            "ticker": pos["ticker"],
            "company": pos.get("company", pos["ticker"]),
            "pnl_pct": pos.get("pnl_pct", 0),
            "pnl_dollar": pos.get("pnl_dollar", 0),
            "comment": _gen_position_comment(pos),
        })

    # 3. Missed opportunities: briefing stocks not held, risen ≥5%
    missed = []
    not_held = [
        s for s in (briefing_stocks or [])
        if s.get("ticker") and s["ticker"].upper() not in held_tickers
           and s.get("price", 0) > 0
    ]
    if not_held:
        price_data = _fetch_prices_parallel([s["ticker"] for s in not_held])
        for stock in not_held:
            ticker = stock["ticker"]
            briefing_price = stock.get("price", 0)
            current_price, _ = price_data.get(ticker, (None, None))
            if briefing_price and current_price and briefing_price > 0:
                change_pct = round((current_price - briefing_price) / briefing_price * 100, 2)
                if change_pct >= 5.0:
                    missed.append({
                        "ticker": ticker,
                        "company": stock.get("company", ticker),
                        "briefing_price": round(briefing_price, 2),
                        "current_price": round(current_price, 2),
                        "change_pct": change_pct,
                        "earnings_beat": stock.get("earnings_surprise_pct"),
                        "reason": stock.get("reason", ""),
                        "alert": _gen_missed_alert(ticker, change_pct, stock),
                    })

    return {
        "overall": _gen_overall_comment(portfolio),
        "position_comments": position_comments,
        "missed_opportunities": sorted(missed, key=lambda x: -x["change_pct"]),
        "generated_at": datetime.now(_ET).strftime("%H:%M ET"),
    }
