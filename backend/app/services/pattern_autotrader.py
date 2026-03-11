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
from app.services.alerts_service import send_telegram, send_telegram_with_buttons
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
    "missed_windows": [],     # [{ticker, window, direction, win_rate, avg_change, reason_missed, date}]
    "ib_demo_trades": [],     # [{ticker, window, direction, confirmed_at, status, date}]
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


# ── AI Learning: record missed pattern windows ─────────────────────────────────
def _record_missed_lesson(entry: dict):
    """Save a missed window to ai_learning.json so the bot can learn from it."""
    import os
    try:
        data_path = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "data", "ai_learning.json")
        )
        if os.path.exists(data_path):
            with open(data_path, "r") as f:
                data = json.load(f)
        else:
            data = {"strategy": {}, "lessons": [], "missed_patterns": []}
        if "missed_patterns" not in data:
            data["missed_patterns"] = []
        data["missed_patterns"].insert(0, {
            "ticker":       entry["ticker"],
            "window":       entry["window"],
            "direction":    entry["direction"],
            "win_rate":     entry["win_rate"],
            "avg_change":   entry["avg_change"],
            "reason_missed": entry["reason_missed"],
            "date":         entry["date"],
            "lesson":       (
                f"פספסנו {entry['ticker']} חלון {entry['window']} "
                f"(WR {entry['win_rate']}%, avg {entry['avg_change']:+.2f}%) — {entry['reason_missed']}"
            ),
        })
        data["missed_patterns"] = data["missed_patterns"][:100]
        data["updated"] = datetime.now().isoformat()
        with open(data_path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[AutoTrader] missed_lesson write failed: {e}")


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
            # Pass cur directly so _exit_trade uses the real stop price, not a re-fetch
            await _exit_trade(trade, reason="stop_loss", known_exit_price=cur)

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
                lines.append(f"\n⏸ פוזיציה פתוחה — הבוט לא נכנס (max {MAX_CONCURRENT})")
            else:
                lines.append("\nאכנס אוטומטית ב-" + w_start + " 🎯")
            lines.append("\n❓ האם תכנסי גם ב-IB דמו?")
            best = max(picks, key=lambda p: p["score"])
            t_cb = best["ticker"]
            buttons = [[
                {"text": f"✅ כן — {t_cb}", "callback_data": f"ibyes_{t_cb}"},
                {"text": "❌ לא", "callback_data": f"ibno_{t_cb}"},
            ]]
            await send_telegram_with_buttons("\n".join(lines), buttons)

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

        # ── Window close: exit trades + record missed ───────────────────────
        elif total_min >= end_min:
            to_close = [t for t in _state["active_trades"] if t["window"] == label]
            for trade in to_close:
                await _exit_trade(trade)
            # Record missed opportunities (picks that were never entered today)
            if picks:
                today_str = date.today().isoformat()
                already_missed = {(m["ticker"], m["window"]) for m in _state["missed_windows"]}
                was_entered = _state["last_alert_sent"].get(label) == "enter"
                if not was_entered:
                    reason = (
                        "מגבלת הפסד יומית" if _state["daily_loss_hit"]
                        else "פוזיציה פתוחה" if len(_state["active_trades"]) > 0
                        else "לא נכנסנו"
                    )
                    for p in picks:
                        key = (p["ticker"], label)
                        if key not in already_missed:
                            missed_entry = {
                                "ticker":       p["ticker"],
                                "window":       label,
                                "direction":    p["direction"],
                                "win_rate":     p["win_rate"],
                                "avg_change":   p["avg_change"],
                                "reason_missed": reason,
                                "date":         today_str,
                            }
                            _state["missed_windows"].insert(0, missed_entry)
                            _record_missed_lesson(missed_entry)


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

    arrow = "📈" if pick["direction"] == "LONG" else "📉"
    ib_line = "🤖 הוזמן דרך IB" if ib_result else "📊 ניטור בלבד (IB לא מחובר)"
    lines = [
        f"{arrow} <b>כניסה — {ticker}</b>",
        f"חלון: <b>{window_label}</b>  |  {pick['direction']}",
        f"מחיר: ${price:.2f}  |  {shares} מניות  |  ${amount:.0f}",
        f"WR {pick['win_rate']}%  |  avg {'+' if pick['avg_change']>0 else ''}{pick['avg_change']:.2f}%",
        ib_line,
    ]
    await send_telegram("\n".join(lines))


async def _exit_trade(trade: dict, reason: str = "window_close", known_exit_price: float = None):
    if trade not in _state["active_trades"]:
        return
    _state["active_trades"].remove(trade)

    ticker = trade["ticker"]
    direction = trade["direction"]
    exit_action = "SELL" if direction == "LONG" else "BUY"

    # Determine exit price: known (stop-loss) > IB fill > live price > entry fallback
    if known_exit_price is not None:
        exit_price = known_exit_price
        ib_result = None
    else:
        ib_result = await asyncio.get_event_loop().run_in_executor(
            None, _place_ib_order, ticker, exit_action, trade["amount"]
        )
        if ib_result:
            exit_price = ib_result["price"]
        else:
            live = await asyncio.get_event_loop().run_in_executor(None, _get_current_price, ticker)
            exit_price = live if live else trade["entry_price"]

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

    pnl_sign = "+" if pnl >= 0 else ""
    daily_sign = "+" if _state["daily_pnl"] >= 0 else ""
    emoji = "✅" if pnl >= 0 else "🔴"
    reason_he = "🛑 Stop Loss" if reason == "stop_loss" else "⏰ סוף חלון"
    ib_line = "🤖 בוצע דרך IB" if ib_result else ""

    lines = [
        f"{emoji} <b>יציאה — {ticker}</b>  |  {reason_he}",
        f"חלון: {trade['window']}  |  {direction}",
        f"כניסה ${trade['entry_price']}  →  יציאה ${exit_price:.2f}",
        f"P&L: <b>{pnl_sign}${pnl}</b>   יומי: {daily_sign}${_state['daily_pnl']}",
    ]
    if ib_line:
        lines.append(ib_line)
    await send_telegram("\n".join(lines))


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
    now = _ny_now()
    total_min = now.hour * 60 + now.minute
    today_str = date.today().isoformat()

    # Upcoming = picks whose window start is still in the future
    upcoming = [
        p for p in _state["today_picks"]
        if _parse_hhmm(p["window"].split("-")[0]) > total_min
    ]
    # Missed today only
    missed_today = [m for m in _state["missed_windows"] if m.get("date") == today_str]
    # IB demo trades today
    ib_demo_today = [t for t in _state["ib_demo_trades"] if t.get("date") == today_str]

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
        "upcoming_windows": upcoming,
        "missed_windows": missed_today,
        "ib_demo_trades": ib_demo_today,
    }


def confirm_ib_demo(ticker: str) -> dict:
    """Called when user confirms entering a trade in IB demo (via Telegram).
    Finds the matching pick and records it in ib_demo_trades."""
    today_str = date.today().isoformat()
    pick = next(
        (p for p in _state["today_picks"] if p["ticker"].upper() == ticker.upper()),
        None,
    )
    if not pick:
        return {"ok": False, "msg": f"לא נמצאה מניה {ticker} בבחירות היום"}
    # Avoid duplicates
    for existing in _state["ib_demo_trades"]:
        if existing["ticker"] == ticker and existing["window"] == pick["window"] and existing["date"] == today_str:
            return {"ok": False, "msg": "כבר רשום"}
    entry = {
        "ticker":       ticker,
        "window":       pick["window"],
        "direction":    pick["direction"],
        "win_rate":     pick["win_rate"],
        "avg_change":   pick["avg_change"],
        "confirmed_at": _ny_now().strftime("%H:%M"),
        "status":       "פתוחה",
        "date":         today_str,
    }
    _state["ib_demo_trades"].append(entry)
    return {"ok": True, "entry": entry}


def enable_no_scan(amount: float = 700, top_n: int = 3) -> dict:
    """Enable the bot instantly with no immediate scan (used on server startup).
    Scan runs at 3:55 AM ET or when manually triggered."""
    _state["enabled"] = True
    _state["amount_per_trade"] = amount
    _state["top_n"] = top_n
    if not _state["status_msg"] or _state["status_msg"] in ("לא פעיל", "כובה"):
        _state["status_msg"] = "פעיל — ממתין לסריקה הבאה (3:55 AM ET)"
    return get_state()


async def enable(amount: float = 700, top_n: int = 5) -> dict:
    """Enable the bot and trigger an immediate scan if not done today."""
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
