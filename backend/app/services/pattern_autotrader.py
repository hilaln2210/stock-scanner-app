"""
Pattern Auto-Trader — Background Bot

Flow:
  1. Daily at 9:20 AM ET: scan universe, pick top 5 stocks by pattern strength
  2. 5 min before each window: Telegram warning  "⚠️ AAOI — עוד 5 דק'"
  3. At window open (9:30, 10:00, ...): place IB market order + Telegram confirm
  4. At window close: exit all active positions from that window + P&L report

"חלון 10:00-10:30" = נכנסים בדיוק ב-10:00 בבוקר (שעון ניו-יורק), יוצאים ב-10:30
"""

import asyncio
import json
import math
import threading
import time as _time
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional
import pytz

from app.config import settings
from app.services.alerts_service import send_telegram
from app.services.pattern_scanner import analyze_single_ticker, filter_stock_pool

_NY = pytz.timezone("America/New_York")

# ── Window definitions ─────────────────────────────────────────────────────────
WINDOWS = [
    # Pre-market
    ("04:00", "04:30"), ("04:30", "05:00"), ("05:00", "05:30"),
    ("05:30", "06:00"), ("06:00", "06:30"), ("06:30", "07:00"),
    ("07:00", "07:30"), ("07:30", "08:00"), ("08:00", "08:30"),
    ("08:30", "09:00"), ("09:00", "09:30"),
    # Regular hours
    ("09:30", "10:00"), ("10:00", "10:30"), ("10:30", "11:00"),
    ("11:00", "11:30"), ("11:30", "12:00"), ("12:00", "12:30"),
    ("12:30", "13:00"), ("13:00", "13:30"), ("13:30", "14:00"),
    ("14:00", "14:30"), ("14:30", "15:00"), ("15:00", "15:30"),
    ("15:30", "16:00"),
]

def _ny_now() -> datetime:
    return datetime.now(_NY)

def _window_label(start: str, end: str) -> str:
    return f"{start}-{end}"

def _parse_hhmm(s: str):
    h, m = map(int, s.split(":"))
    return h * 60 + m

# ── Risk parameters ────────────────────────────────────────────────────────────
PORTFOLIO_SIZE   = 700    # $ total portfolio
MAX_CONCURRENT   = 1      # max open positions at once (1 = full portfolio on 1 trade)
DAILY_LOSS_LIMIT = -50    # $ — stop trading today if daily_pnl drops below this
STOP_LOSS_PCT    = 1.5    # % from entry — exit early if loss exceeds this
MIN_WIN_RATE     = 65     # % — only trade windows with WR >= this
MIN_SAMPLE_DAYS  = 10     # minimum backtested days required per window

# ── State ──────────────────────────────────────────────────────────────────────
_state: Dict = {
    "enabled": False,
    "today_picks": [],        # list of {ticker, window, direction, win_rate, avg_change, score}
    "active_trades": [],      # list of {ticker, window, direction, entry_price, shares, amount, opened_at}
    "trade_history": [],      # last 20 closed trades
    "daily_pnl": 0.0,
    "last_scan_date": None,   # date string "YYYY-MM-DD"
    "last_alert_sent": {},    # {window_label: "warn"/"enter"}
    "amount_per_trade": PORTFOLIO_SIZE,
    "top_n": 3,               # pick best 3 — execute only 1 at a time (MAX_CONCURRENT)
    "status_msg": "לא פעיל",
    "daily_loss_hit": False,  # True = stop trading today (loss limit reached)
}


# ── IB market order helper ─────────────────────────────────────────────────────
def _place_ib_order(ticker: str, action: str, amount: float) -> Optional[dict]:
    """Place a market order via IB. action = 'BUY' or 'SELL'."""
    try:
        import ib_insync as _ib
    except ImportError:
        return None

    result_holder = [None]
    done = threading.Event()

    def _worker():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ib = _ib.IB()
        try:
            ib.connect("127.0.0.1", 4002, clientId=99, readonly=False, timeout=8)
            contract = _ib.Stock(ticker, 'SMART', 'USD')
            ib.qualifyContracts(contract)

            # Get current price to calculate shares
            ticker_data = ib.reqMktData(contract, '', False, False)
            ib.sleep(2)
            price = ticker_data.last or ticker_data.close or 0
            if not price or math.isnan(float(price)):
                price = ticker_data.bid or 1
            price = float(price)
            if price <= 0:
                return

            shares = max(1, int(amount / price))
            order = _ib.MarketOrder(action, shares)
            trade = ib.placeOrder(contract, order)
            ib.sleep(3)  # wait for fill

            fill_price = price  # fallback
            if trade.fills:
                fill_price = trade.fills[-1].execution.price

            result_holder[0] = {
                "ticker": ticker,
                "action": action,
                "shares": shares,
                "price": round(fill_price, 2),
                "amount": round(shares * fill_price, 2),
            }
        except Exception as e:
            print(f"[AutoTrader IB] {action} {ticker} error: {e}")
        finally:
            try:
                ib.disconnect()
            except Exception:
                pass
            loop.close()
            done.set()

    t = threading.Thread(target=_worker, daemon=True, name="autotrader-ib")
    t.start()
    done.wait(timeout=20)
    return result_holder[0]


# ── Daily scan: pick top N stocks ─────────────────────────────────────────────
async def _run_daily_scan():
    """Scan universe and pick top-N stocks for today based on pattern strength."""
    _state["status_msg"] = "סורק מניות..."
    try:
        pool = await filter_stock_pool(
            min_market_cap=2_000_000_000,
            min_atr=2.0, min_atr_pct=2.5, min_volume=5_000_000
        )
        tickers = [s["ticker"] for s in pool[:15]]  # analyze top 15 from pool
    except Exception as e:
        _state["status_msg"] = f"שגיאה בסריקה: {e}"
        return

    candidates = []
    sem = asyncio.Semaphore(3)

    async def _check(ticker):
        async with sem:
            try:
                data = await analyze_single_ticker(ticker, days=45, interval="5m")
                if not data or data.get("error"):
                    return
                best_score = 0
                best_window = None
                best_dir = "LONG"
                for w in data.get("windows", []):
                    if not w.get("tradeable"):
                        continue
                    wr = w.get("win_rate", 0)
                    ac = abs(w.get("avg_change", 0))
                    samples = w.get("sample_days", 0)
                    # Strict quality gates
                    if wr < MIN_WIN_RATE:
                        continue
                    if samples < MIN_SAMPLE_DAYS:
                        continue
                    # Score: win_rate × avg_change × sample_bonus
                    sample_bonus = min(samples / 20, 1.5)  # up to 1.5x for 30+ samples
                    score = wr * ac * sample_bonus
                    if score > best_score:
                        best_score = score
                        best_window = w
                        best_dir = "LONG" if w["avg_change"] > 0 else "SHORT"
                if best_window and best_score > 0:
                    candidates.append({
                        "ticker": ticker,
                        "window": best_window["window"],
                        "direction": best_dir,
                        "win_rate": best_window["win_rate"],
                        "avg_change": best_window["avg_change"],
                        "avg_win": best_window.get("avg_win", 0),
                        "score": round(best_score, 2),
                        "price": data.get("price", 0),
                    })
            except Exception as e:
                print(f"[AutoTrader scan] {ticker}: {e}")

    await asyncio.gather(*[_check(t) for t in tickers])

    candidates.sort(key=lambda x: x["score"], reverse=True)
    picks = candidates[:_state["top_n"]]
    _state["today_picks"] = picks
    _state["last_scan_date"] = date.today().isoformat()
    _state["last_alert_sent"] = {}
    _state["daily_loss_hit"] = False
    _state["status_msg"] = f"פעיל — {len(picks)} מניות נבחרו להיום (מקסימום {MAX_CONCURRENT} במקביל)"

    if picks:
        lines = ["🤖 <b>Pattern Bot — המניות להיום</b>\n"]
        for p in picks:
            arrow = "📈" if p["direction"] == "LONG" else "📉"
            lines.append(
                f"{arrow} <b>{p['ticker']}</b> | {p['window']} | "
                f"WR {p['win_rate']}% | avg {'+' if p['avg_change']>0 else ''}{p['avg_change']}%"
            )
        lines.append(f"\n💰 ${_state['amount_per_trade']} לכל עסקה | אכנס אוטומטית בזמן האמת 🚀")
        await send_telegram("\n".join(lines))


# ── Tick: runs every 30 seconds ───────────────────────────────────────────────
def _get_current_price(ticker: str) -> Optional[float]:
    """Quick price fetch via yfinance fast_info — used for stop-loss checks."""
    import threading, yfinance as yf
    result = [None]
    done = threading.Event()
    def _fetch():
        try:
            fi = yf.Ticker(ticker).fast_info
            p = fi.last_price or fi.previous_close
            result[0] = float(p) if p and not math.isnan(float(p)) else None
        except Exception:
            pass
        finally:
            done.set()
    threading.Thread(target=_fetch, daemon=True).start()
    done.wait(timeout=4)
    return result[0]


async def _tick():
    """Check windows for entries/exits + monitor open trades for stop-loss."""
    if not _state["enabled"] or not _state["today_picks"]:
        return

    now = _ny_now()
    h, m = now.hour, now.minute
    total_min = h * 60 + m

    # Operating hours: 3:55 AM – 16:05 PM ET
    if not (3 * 60 + 55 <= total_min <= 16 * 60 + 5):
        return

    # ── Stop-loss check for active trades ──────────────────────────────────
    for trade in list(_state["active_trades"]):
        cur = await asyncio.get_event_loop().run_in_executor(None, _get_current_price, trade["ticker"])
        if cur is None:
            continue
        entry = trade["entry_price"]
        if trade["direction"] == "LONG":
            loss_pct = (entry - cur) / entry * 100
        else:
            loss_pct = (cur - entry) / entry * 100
        if loss_pct >= STOP_LOSS_PCT:
            await send_telegram(
                f"🛑 <b>Stop Loss — {trade['ticker']}</b>\n"
                f"כניסה: ${entry} → עכשיו: ${cur:.2f}\n"
                f"הפסד: -{loss_pct:.1f}% (מגבלה: -{STOP_LOSS_PCT}%)"
            )
            await _exit_trade(trade, reason="stop_loss")

    # ── Daily loss limit ────────────────────────────────────────────────────
    if _state["daily_pnl"] <= DAILY_LOSS_LIMIT and not _state["daily_loss_hit"]:
        _state["daily_loss_hit"] = True
        _state["status_msg"] = f"⛔ הפסד יומי מקסימלי הושג (${_state['daily_pnl']}) — הפסקת מסחר"
        await send_telegram(
            f"⛔ <b>מגבלת הפסד יומית</b>\n"
            f"הפסד יומי: ${_state['daily_pnl']} (מגבלה: ${DAILY_LOSS_LIMIT})\n"
            f"הבוט מפסיק לסחור היום."
        )
        return

    if _state["daily_loss_hit"]:
        return

    picks_by_window: Dict[str, list] = {}
    for p in _state["today_picks"]:
        picks_by_window.setdefault(p["window"], []).append(p)

    for (w_start, w_end) in WINDOWS:
        label = _window_label(w_start, w_end)
        start_min = _parse_hhmm(w_start)
        end_min   = _parse_hhmm(w_end)
        picks      = picks_by_window.get(label, [])
        last_alert = _state["last_alert_sent"].get(label)

        # ── 5-min warning ───────────────────────────────────────────────────
        if total_min == start_min - 5 and last_alert is None and picks:
            _state["last_alert_sent"][label] = "warn"
            concurrent = len(_state["active_trades"])
            lines = [f"⚠️ <b>עוד 5 דקות! — {label}</b>\n"]
            for p in picks:
                arrow = "📈 LONG" if p["direction"] == "LONG" else "📉 SHORT"
                lines.append(f"  {arrow} <b>{p['ticker']}</b> | WR {p['win_rate']}%")
            if concurrent >= MAX_CONCURRENT:
                lines.append(f"\n⏸ פוזיציה פתוחה — לא נכנס (max {MAX_CONCURRENT})")
            else:
                lines.append("\nאכנס אוטומטית ב-" + w_start + " 🎯")
            await send_telegram("\n".join(lines))

        # ── Window open: enter trade (only if slot available) ───────────────
        elif total_min == start_min and last_alert in (None, "warn") and picks:
            _state["last_alert_sent"][label] = "enter"
            if len(_state["active_trades"]) < MAX_CONCURRENT:
                # Take only the best pick for this window
                best_pick = max(picks, key=lambda p: p["score"])
                await _enter_trade(best_pick, label)
            else:
                await send_telegram(
                    f"⏸ <b>דילוג — {label}</b>\n"
                    f"יש {len(_state['active_trades'])} פוזיציה פתוחה (max {MAX_CONCURRENT})"
                )

        # ── Window close: exit trades ───────────────────────────────────────
        elif total_min >= end_min:
            to_close = [t for t in _state["active_trades"] if t["window"] == label]
            for trade in to_close:
                await _exit_trade(trade)


async def _enter_trade(pick: dict, window_label: str):
    action = "BUY" if pick["direction"] == "LONG" else "SELL"
    amount = _state["amount_per_trade"]
    ticker = pick["ticker"]

    # Try IB
    ib_result = await asyncio.get_event_loop().run_in_executor(
        None, _place_ib_order, ticker, action, amount
    )

    price = ib_result["price"] if ib_result else pick["price"]
    shares = ib_result["shares"] if ib_result else max(1, int(amount / price)) if price > 0 else 1

    trade = {
        "ticker": ticker,
        "window": window_label,
        "direction": pick["direction"],
        "entry_price": price,
        "shares": shares,
        "amount": amount,
        "opened_at": _ny_now().strftime("%H:%M"),
        "ib_filled": ib_result is not None,
    }
    _state["active_trades"].append(trade)

    ib_tag = "✅ נכנס דרך IB" if ib_result else "⚡ ידני (IB לא מחובר)"
    arrow = "📈" if pick["direction"] == "LONG" else "📉"
    msg = (
        f"{arrow} <b>כניסה — {ticker}</b>\n"
        f"חלון: <b>{window_label}</b>  |  {pick['direction']}\n"
        f"מחיר: ${price}  |  {shares} מניות\n"
        f"WR: {pick['win_rate']}%  |  avg {'+' if pick['avg_change']>0 else ''}{pick['avg_change']}%\n"
        f"{ib_tag}"
    )
    await send_telegram(msg)


async def _exit_trade(trade: dict, reason: str = "window_close"):
    if trade not in _state["active_trades"]:
        return
    _state["active_trades"].remove(trade)

    ticker = trade["ticker"]
    direction = trade["direction"]
    exit_action = "SELL" if direction == "LONG" else "BUY"

    ib_result = await asyncio.get_event_loop().run_in_executor(
        None, _place_ib_order, ticker, exit_action, trade["amount"]
    )

    exit_price = ib_result["price"] if ib_result else trade["entry_price"]
    if direction == "LONG":
        pnl = (exit_price - trade["entry_price"]) * trade["shares"]
    else:
        pnl = (trade["entry_price"] - exit_price) * trade["shares"]
    pnl = round(pnl, 2)

    _state["daily_pnl"] = round(_state["daily_pnl"] + pnl, 2)
    closed = {**trade, "exit_price": exit_price, "pnl": pnl,
              "closed_at": _ny_now().strftime("%H:%M"), "exit_reason": reason}
    _state["trade_history"].insert(0, closed)
    _state["trade_history"] = _state["trade_history"][:20]

    emoji = "✅" if pnl >= 0 else "❌"
    reason_tag = "🛑 Stop Loss" if reason == "stop_loss" else "⏰ סוף חלון"
    ib_tag = "✅ יצא דרך IB" if ib_result else "⚡ ידני"
    msg = (
        f"{emoji} <b>יציאה — {ticker}</b> ({reason_tag})\n"
        f"חלון: {trade['window']}\n"
        f"כניסה: ${trade['entry_price']}  →  יציאה: ${exit_price}\n"
        f"P&L: <b>{'+'if pnl>=0 else ''}${pnl}</b>  |  יומי: {'+'if _state['daily_pnl']>=0 else ''}${_state['daily_pnl']}\n"
        f"{ib_tag}"
    )
    await send_telegram(msg)


# ── Background loop ────────────────────────────────────────────────────────────
_bg_task: Optional[asyncio.Task] = None

async def _loop():
    while True:
        try:
            now = _ny_now()
            today = date.today().isoformat()

            # Daily scan at 3:55 AM ET (before pre-market opens at 4:00)
            if (_state["enabled"]
                    and _state["last_scan_date"] != today
                    and now.hour == 3 and now.minute == 55):
                await _run_daily_scan()

            await _tick()
        except Exception as e:
            print(f"[AutoTrader loop] error: {e}")
        await asyncio.sleep(30)


def start_background_loop():
    global _bg_task
    if _bg_task is None or _bg_task.done():
        loop = asyncio.get_event_loop()
        _bg_task = loop.create_task(_loop())


# ── Public API ─────────────────────────────────────────────────────────────────
def get_state() -> dict:
    return {
        "enabled": _state["enabled"],
        "today_picks": _state["today_picks"],
        "active_trades": _state["active_trades"],
        "trade_history": _state["trade_history"][:10],
        "daily_pnl": _state["daily_pnl"],
        "last_scan_date": _state["last_scan_date"],
        "amount_per_trade": _state["amount_per_trade"],
        "top_n": _state["top_n"],
        "status_msg": _state["status_msg"],
    }


async def enable(amount: float = 700, top_n: int = 5) -> dict:
    _state["enabled"] = True
    _state["amount_per_trade"] = amount
    _state["top_n"] = top_n
    _state["status_msg"] = "פעיל — סורק..."
    start_background_loop()

    # If no scan today yet — run immediately
    if _state["last_scan_date"] != date.today().isoformat():
        _state["daily_pnl"] = 0.0
        asyncio.get_event_loop().create_task(_run_daily_scan())

    return get_state()


def disable() -> dict:
    _state["enabled"] = False
    _state["status_msg"] = "כובה"
    return get_state()


def manual_scan(amount: float = 700, top_n: int = 5) -> dict:
    """Fire-and-forget: start scan in background, return immediately."""
    _state["amount_per_trade"] = amount
    _state["top_n"] = top_n
    _state["last_scan_date"] = None   # force re-scan
    _state["daily_pnl"] = 0.0
    _state["today_picks"] = []
    _state["status_msg"] = "סורק מניות... (עד דקה)"
    # launch as background task — do NOT await
    asyncio.get_event_loop().create_task(_run_daily_scan())
    return get_state()
