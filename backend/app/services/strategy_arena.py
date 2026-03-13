"""
Strategy Arena — 6 mini-portfolios competing all week.
Each gets $1,000. No AI — fast rule-based scoring.
Sessions: pre-market 4:00-9:25, regular 9:25-16:05, after-market 16:05-20:00 ET.
Daily 16:05 ET: day-winner archived. Friday 16:05: weekly winner declared.
"""

import json
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

DATA_DIR   = Path(__file__).parent.parent.parent / "data"
ARENA_FILE = DATA_DIR / "strategy_arena.json"
LEARNING_FILE = DATA_DIR / "ai_learning.json"

ARENA_INITIAL_CAPITAL = 1000.0
CONF_MULTIPLIER = 1.5

# ─── Session helpers ──────────────────────────────────────────────────────────

def _et_now() -> datetime:
    month = datetime.now(timezone.utc).month
    offset = timedelta(hours=-4 if 3 <= month <= 11 else -5)
    return datetime.now(timezone.utc) + offset

def get_session_type() -> str:
    """Returns: premarket | regular | aftermarket | closed"""
    now = _et_now()
    if now.weekday() >= 5:
        return "closed"
    total_min = now.hour * 60 + now.minute
    if 4 * 60 <= total_min < 9 * 60 + 25:
        return "premarket"
    if 9 * 60 + 25 <= total_min < 16 * 60 + 5:
        return "regular"
    if 16 * 60 + 5 <= total_min < 20 * 60:
        return "aftermarket"
    return "closed"

def _week_start() -> str:
    """ISO date of the Monday of the current week."""
    now = _et_now()
    monday = now - timedelta(days=now.weekday())
    return monday.strftime("%Y-%m-%d")

def _today() -> str:
    return _et_now().strftime("%Y-%m-%d")

# ─── Strategy Configs ─────────────────────────────────────────────────────────

STRATEGY_CONFIGS = {
    "Balanced": {
        "label": "⚖️ Balanced",
        "description": "כניסות מאוזנות — health טוב + מומנטום, rvol ≥ 1.2, כניסה לפני 11:00 ET",
        "min_health": 30, "min_conf": 35, "min_rvol": 1.2,
        "stop_pct": 6.0, "target_pct": 18.0,
        "max_day_chg": 12.0, "requires_short_float": None,
        "requires_min_chg": None, "max_positions": 2,
        "entry_cutoff_et": 11 * 60,          # no new entries after 11:00 ET
    },
    "HighConviction": {
        "label": "🎯 High Conviction",
        "description": "רק הכי טובים — partial TP ב-8% (50%), יעד +15%",
        "min_health": 45, "min_conf": 48, "min_rvol": 0.6,
        "stop_pct": 5.0, "target_pct": 15.0,
        "max_day_chg": 8.0, "requires_short_float": None,
        "requires_min_chg": None, "max_positions": 2,
        "partial_tp_trigger": 8.0, "partial_tp_pct": 0.5,  # sell 50% at +8%
        "trailing_trigger": 8.0, "trail_pct": 0.91,
    },
    "SqueezeHunter": {
        "label": "🔥 Hard Squeeze",
        "description": "שורט סקוויז — שורט≥20%, partial TP ב-15% (50%), יעד +40%",
        "min_health": 12, "min_conf": 15, "min_rvol": 1.5,
        "stop_pct": 8.0, "target_pct": 40.0,
        "max_day_chg": 999.0, "requires_short_float": 20.0,
        "requires_min_chg": 2.0, "max_positions": 2,
        "small_cap_only": True,
        "partial_tp_trigger": 15.0, "partial_tp_pct": 0.5,  # sell 50% at +15%
        "trailing_trigger": 12.0, "trail_pct": 0.91,
    },
    "Scalper": {
        "label": "⚡ Scalper",
        "description": "כניסות אגרסיביות — rvol ≥ 1.5, כניסה רק 9:30-10:00 ET, trail 0.92",
        "min_health": 18, "min_conf": 20, "min_rvol": 1.5,
        "stop_pct": 6.0, "target_pct": 20.0,
        "max_day_chg": 999.0, "requires_short_float": None,
        "requires_min_chg": 0.1, "max_positions": 2,
        "partial_tp_trigger": 10.0, "trailing_trigger": 8.0, "trail_pct": 0.92,
        "entry_cutoff_et": 10 * 60,          # entries only 9:30–10:00 ET
    },
    "MomentumBreaker": {
        "label": "🚀 Momentum Breaker",
        "description": "פורצים עם נפח פנומנלי — rvol ≥ 1.5, תנועה > 1.5%, כניסה לפני 10:30 ET",
        "min_health": 22, "min_conf": 28, "min_rvol": 1.5,
        "stop_pct": 5.0, "target_pct": 16.0,
        "max_day_chg": 30.0, "requires_short_float": None,
        "requires_min_chg": 1.5, "max_positions": 2,
        "entry_cutoff_et": 10 * 60 + 30,     # no new entries after 10:30 ET
    },
    "SwingSetup": {
        "label": "⚡ Lightning Squeeze",
        "description": "Float<50M, שורט≥10%, GAP UP — trail רחב 0.87 לנשימה",
        "min_health": 10, "min_conf": 12, "min_rvol": 2.0,
        "stop_pct": 8.0, "target_pct": 35.0,
        "max_day_chg": 999.0, "requires_short_float": 10.0,
        "requires_min_chg": 1.0, "max_positions": 2,
        "max_price": 50.0,
        "requires_gap": True,
        "requires_float_shares_max": 50_000_000,
        "partial_tp_trigger": 10.0,
        "trailing_trigger": 8.0,
        "trail_pct": 0.87,                   # wider trail — small float needs room
    },
    "SeasonalityTrader": {
        "label": "🌪️ Gap & Squeeze",
        "description": "גאפ + שורט — partial TP ב-20% (30%) + ב-40% (30%), runner ל-60%",
        "min_health": 8, "min_conf": 10, "min_rvol": 5.0,
        "stop_pct": 10.0, "target_pct": 60.0,
        "max_day_chg": 999.0, "requires_short_float": 20.0,
        "requires_min_chg": 1.0, "max_positions": 2,
        "small_cap_only": True,
        "max_price": 20.0,
        "requires_gap": True,
        "requires_float_shares_max": 30_000_000,
        "partial_tp_trigger": 20.0, "partial_tp_pct": 0.3,   # sell 30% at +20%
        "partial_tp2_trigger": 40.0, "partial_tp2_pct": 0.3, # sell 30% at +40%, runner ל-60%
        "trailing_trigger": 20.0, "trail_pct": 0.88,
    },
    "PatternTrader": {
        "label": "💥 Nano Squeeze",
        "description": "מיקרו שורט סקוויז — stop קטן 6%, half position size, יעד +50%",
        "min_health": 10, "min_conf": 12, "min_rvol": 2.0,
        "stop_pct": 6.0, "target_pct": 50.0,
        "max_day_chg": 999.0, "requires_short_float": 15.0,
        "requires_min_chg": 1.0, "max_positions": 2,
        "small_cap_only": True,
        "half_position_size": True,          # לוטרי — חצי מגודל רגיל
    },
}

_ARENA_TO_BRAIN_PARAMS = {
    "stop_pct":   "stop_loss_pct",
    "target_pct": "target_pct",
    "min_health": "min_health_score",
    "min_rvol":   "min_rel_volume",
    "min_conf":   "min_confidence",
}

# Extended-hours session overrides (relaxed filters, 1 new position max)
_SESSION_OVERRIDES = {
    "premarket": {
        "rvol_factor": 0.4,      # multiply min_rvol by this
        "stop_add_pct": 1.0,     # widen stop
        "skip_min_chg": True,    # ignore requires_min_chg
        "max_new_pos": 1,
    },
    "aftermarket": {
        "rvol_factor": 0.35,
        "stop_add_pct": 1.5,
        "skip_min_chg": True,
        "max_new_pos": 1,
    },
    "regular": {
        "rvol_factor": 1.0,
        "stop_add_pct": 0.0,
        "skip_min_chg": False,
        "max_new_pos": 99,
    },
}

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _safe_float(val, default: float = 0.0) -> float:
    try:
        if isinstance(val, str):
            val = val.replace('%', '').replace(',', '').strip()
        return float(val) if val else default
    except (ValueError, TypeError):
        return default

def _arena_score(stock: dict) -> float:
    health = _safe_float(stock.get("health_score"))
    rvol   = _safe_float(stock.get("rel_volume"))
    chg    = _safe_float(stock.get("change_pct"))
    sf     = _safe_float(stock.get("short_float"))
    sq     = _safe_float(stock.get("squeeze_total_score"))
    rsi    = _safe_float(stock.get("rsi"), 50)
    score  = health * 0.3 + rvol * 20 + chg * 5
    if sf > 15:  score += 20
    if sq > 50:  score += 30
    if rsi > 80: score -= 15
    return score

# ─── MiniPortfolio ────────────────────────────────────────────────────────────

class MiniPortfolio:
    def __init__(self, name: str, config: dict):
        self.name   = name
        self.config = config
        self.cash   = ARENA_INITIAL_CAPITAL
        self.positions: dict = {}
        self.trades: list    = []
        self.partial_taken: set = set()

    def get_equity(self, live_prices: dict) -> float:
        eq = self.cash
        for ticker, pos in self.positions.items():
            price = live_prices.get(ticker) or pos["entry_price"]
            eq += pos["qty"] * price
        return eq

    def get_pnl(self, live_prices: dict) -> float:
        return self.get_equity(live_prices) - ARENA_INITIAL_CAPITAL

    def get_pnl_pct(self, live_prices: dict) -> float:
        return self.get_pnl(live_prices) / ARENA_INITIAL_CAPITAL * 100

    def get_win_rate(self) -> float:
        full = [t for t in self.trades if not t.get("was_partial")]
        if not full: return 0.0
        return sum(1 for t in full if t["pnl"] > 0) / len(full) * 100

    def open_position(self, ticker: str, price: float,
                      stop_override: float = None) -> bool:
        import math
        if not price or price <= 0 or math.isnan(price) or math.isinf(price):
            return False
        if ticker in self.positions:
            return False
        cfg        = self.config
        equity     = self.get_equity({ticker: price})
        if math.isnan(equity) or equity <= 0:
            return False
        slot_size  = equity / cfg["max_positions"]   # equal-weight slots
        if cfg.get("half_position_size"):
            slot_size = slot_size / 2               # Nano Squeeze: lottery size
        qty        = max(1, int(slot_size / price))
        cost       = price * qty
        if cost > self.cash:
            qty  = max(1, int(self.cash / price))
            cost = price * qty
        if qty <= 0 or cost > self.cash:
            return False

        stop_pct = (stop_override or cfg["stop_pct"])
        stop   = round(price * (1 - stop_pct / 100), 2)
        target = round(price * (1 + cfg["target_pct"] / 100), 2)

        self.cash -= cost
        self.positions[ticker] = {
            "entry_price": price, "qty": qty,
            "stop_loss": stop, "target": target,
            "entry_time": datetime.now().isoformat(),
            "highest_price": price, "trailing_active": False,
            "session": get_session_type(),
        }
        print(f"[Arena:{self.name}] BUY {ticker} @ ${price:.2f} qty={qty} "
              f"stop=${stop:.2f} target=${target:.2f}")
        return True

    def close_position(self, ticker: str, price: float, reason: str,
                       partial_pct: float = 0.0) -> Optional[dict]:
        pos = self.positions.get(ticker)
        if not pos: return None
        close_qty = pos["qty"]
        if 0 < partial_pct < 1:
            close_qty = max(1, int(pos["qty"] * partial_pct))
            if close_qty >= pos["qty"]:
                partial_pct = 0.0
        pnl = (price - pos["entry_price"]) * close_qty
        self.cash += pos["entry_price"] * close_qty + pnl
        trade = {
            "ticker": ticker, "entry_price": pos["entry_price"],
            "exit_price": price, "qty": close_qty,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / (pos["entry_price"] * close_qty) * 100, 2),
            "reason": reason, "entry_time": pos["entry_time"],
            "exit_time": datetime.now().isoformat(),
            "was_partial": partial_pct > 0,
            "session": pos.get("session", "regular"),
        }
        self.trades.append(trade)
        print(f"[Arena:{self.name}] CLOSE {ticker} @ ${price:.2f} "
              f"pnl=${pnl:+.2f} ({trade['pnl_pct']:+.1f}%) [{reason}]")
        remaining = pos["qty"] - close_qty
        if remaining > 0 and partial_pct > 0:
            self.positions[ticker] = {**pos, "qty": remaining}
            self.partial_taken.add(ticker)
        else:
            del self.positions[ticker]
            self.partial_taken.discard(ticker)
        return trade

    def check_stops(self, live_prices: dict) -> list:
        closed = []
        now    = datetime.now()
        cfg    = self.config
        partial_tp_trigger  = cfg.get("partial_tp_trigger",  12.0)
        partial_tp_pct      = cfg.get("partial_tp_pct",       0.4)   # fraction to sell at TP1
        partial_tp2_trigger = cfg.get("partial_tp2_trigger",  None)  # optional second TP level
        partial_tp2_pct     = cfg.get("partial_tp2_pct",      0.3)
        trailing_trigger    = cfg.get("trailing_trigger",      8.0)
        trail_pct           = cfg.get("trail_pct",             0.91)

        for ticker in list(self.positions.keys()):
            pos   = self.positions[ticker]
            price = live_prices.get(ticker)
            if not price: continue

            if price > pos["highest_price"]:
                pos["highest_price"] = price

            entry   = pos["entry_price"]
            pnl_pct = (price - entry) / entry * 100

            # Stale exit: held >2 calendar days with <2% gain
            try:
                age_days = (now - datetime.fromisoformat(pos["entry_time"])).days
                if age_days >= 2 and pnl_pct < 2.0:
                    t = self.close_position(ticker, price, "Stale exit (2d < 2%)")
                    if t: closed.append(t)
                    continue
            except Exception:
                pass

            # Partial TP1
            tp1_key = f"_tp1_{ticker}"
            if pnl_pct >= partial_tp_trigger and tp1_key not in self.partial_taken and pos["qty"] >= 2:
                t = self.close_position(ticker, price,
                                        f"Partial TP1 +{partial_tp_trigger:.0f}%",
                                        partial_pct=partial_tp_pct)
                if t: closed.append(t)
                self.partial_taken.add(tp1_key)
                pos = self.positions.get(ticker)
                if not pos: continue

            # Partial TP2 (e.g. Gap & Squeeze: sell another 30% at +40%)
            tp2_key = f"_tp2_{ticker}"
            if (partial_tp2_trigger and pnl_pct >= partial_tp2_trigger
                    and tp2_key not in self.partial_taken and pos["qty"] >= 2):
                t = self.close_position(ticker, price,
                                        f"Partial TP2 +{partial_tp2_trigger:.0f}%",
                                        partial_pct=partial_tp2_pct)
                if t: closed.append(t)
                self.partial_taken.add(tp2_key)
                pos = self.positions.get(ticker)
                if not pos: continue

            # Activate trailing stop
            if pnl_pct >= trailing_trigger and not pos["trailing_active"]:
                pos["trailing_active"] = True
                pos["stop_loss"] = max(pos["stop_loss"], round(entry * 1.01, 2))

            if pos["trailing_active"]:
                trail_sl = round(pos["highest_price"] * trail_pct, 2)
                if trail_sl > pos["stop_loss"]:
                    pos["stop_loss"] = trail_sl

            if price <= pos["stop_loss"]:
                reason = "Trailing stop" if pos["trailing_active"] else "Stop loss"
                t = self.close_position(ticker, price, reason)
                if t: closed.append(t)
                continue

            if price >= pos["target"]:
                t = self.close_position(ticker, price, "Target reached")
                if t: closed.append(t)
        return closed

    def to_dict(self, live_prices: dict) -> dict:
        return {
            "name": self.name, "cash": round(self.cash, 2),
            "equity": round(self.get_equity(live_prices), 2),
            "pnl": round(self.get_pnl(live_prices), 2),
            "pnl_pct": round(self.get_pnl_pct(live_prices), 2),
            "positions": self.positions, "trades": self.trades,
            "partial_taken": list(self.partial_taken),
        }

    def restore(self, state: dict):
        self.cash      = state.get("cash", ARENA_INITIAL_CAPITAL)
        self.trades    = state.get("trades", [])
        max_pos        = self.config.get("max_positions", 5)
        all_positions  = state.get("positions", {})
        # Enforce max_positions — keep oldest entries (sorted by entry_time)
        if len(all_positions) > max_pos:
            sorted_items = sorted(
                all_positions.items(),
                key=lambda kv: kv[1].get("entry_time", "")
            )
            # Refund the excess positions back to cash
            excess = sorted_items[max_pos:]
            for ticker, pos in excess:
                self.cash += pos["entry_price"] * pos["qty"]
                print(f"[Arena:{self.name}] Trimmed excess position {ticker} "
                      f"(max_positions={max_pos}) → refunded ${pos['entry_price'] * pos['qty']:.2f}")
            all_positions = dict(sorted_items[:max_pos])
        self.positions     = all_positions
        saved_pt = set(state.get("partial_taken", []))
        pos_keys = set(all_positions.keys())
        # Keep entries whose underlying ticker is still open
        # Handles both old (plain ticker) and new (_tp1_TICKER / _tp2_TICKER) formats
        self.partial_taken = {
            k for k in saved_pt
            if k in pos_keys
            or (k.startswith("_tp1_") and k[5:] in pos_keys)
            or (k.startswith("_tp2_") and k[5:] in pos_keys)
        }


# ─── StrategyArena ────────────────────────────────────────────────────────────

class StrategyArena:
    def __init__(self):
        self._lock = threading.Lock()
        self.portfolios: dict[str, MiniPortfolio] = {
            name: MiniPortfolio(name, cfg)
            for name, cfg in STRATEGY_CONFIGS.items()
        }
        self.week_start: str          = ""
        self.current_day: str         = ""
        self.daily_history: list      = []   # [{date, winner, label, pnl_pcts}]
        self.weekly_winner: Optional[dict] = None
        self.weekly_winner_at: Optional[str] = None
        self.tick_count: int          = 0
        self.last_tick: Optional[str] = None
        self.recent_events: list      = []   # rolling buffer, max 50
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load(self):
        try:
            if ARENA_FILE.exists():
                state = json.loads(ARENA_FILE.read_text())
                cur_week = _week_start()
                saved_week = state.get("week_start") or state.get("session_date", "")[:10]
                # Restore if same week OR if within 2 days (handles format migration)
                week_ok = (saved_week == cur_week) or (
                    saved_week and abs(
                        (datetime.strptime(cur_week, "%Y-%m-%d") -
                         datetime.strptime(saved_week[:10], "%Y-%m-%d")).days
                    ) <= 7
                )
                if week_ok:
                    for name, pf_state in state.get("portfolios", {}).items():
                        if name in self.portfolios:
                            self.portfolios[name].restore(pf_state)
                    self.week_start       = cur_week
                    self.current_day      = state.get("current_day", _today())
                    self.daily_history    = state.get("daily_history", [])
                    self.weekly_winner    = state.get("weekly_winner")
                    self.weekly_winner_at = state.get("weekly_winner_at")
                    self.tick_count       = state.get("tick_count", 0)
                    self.last_tick        = state.get("last_tick")
                    print(f"[Arena] Restored state: tick={self.tick_count}, week={self.week_start}")
                    return
        except Exception as e:
            print(f"[Arena] Load error: {e}")
        self._reset_week()

    def _save(self, live_prices: dict = None):
        try:
            DATA_DIR.mkdir(exist_ok=True)
            state = {
                "week_start":       self.week_start,
                "current_day":      self.current_day,
                "daily_history":    self.daily_history,
                "weekly_winner":    self.weekly_winner,
                "weekly_winner_at": self.weekly_winner_at,
                "tick_count":       self.tick_count,
                "last_tick":        self.last_tick,
                "portfolios": {
                    name: pf.to_dict(live_prices or {})
                    for name, pf in self.portfolios.items()
                },
            }
            ARENA_FILE.write_text(json.dumps(state, indent=2, default=str))
        except OSError:
            pass

    def force_close_and_reset(self, strategy_name: str, live_prices: dict = None) -> dict:
        """
        Force-close all positions for a strategy at current prices,
        and reload its config from STRATEGY_CONFIGS (picks up any config changes).
        Returns summary of closed trades.
        """
        live_prices = live_prices or {}
        with self._lock:
            pf = self.portfolios.get(strategy_name)
            if not pf:
                return {"error": f"Unknown strategy: {strategy_name}"}
            closed = []
            for ticker in list(pf.positions.keys()):
                price = live_prices.get(ticker) or pf.positions[ticker].get("entry_price", 0)
                trade = pf.close_position(ticker, price, "force_reset")
                if trade:
                    closed.append(trade)
                    self._add_event("SELL", strategy_name, ticker, price,
                                    trade.get("pnl_pct", 0), "force_reset")
            # Reload config from STRATEGY_CONFIGS (picks up new params)
            new_cfg = STRATEGY_CONFIGS.get(strategy_name, pf.config)
            pf.config = new_cfg
            self._save(live_prices)
            print(f"[Arena] force_reset {strategy_name}: closed {len(closed)} positions, new config: {new_cfg.get('label')}")
            return {"strategy": strategy_name, "closed": len(closed), "trades": closed}

    def auto_replace_losers(self, live_prices: dict = None) -> list:
        """
        EOD automatic strategy replacement.
        Strategies with negative P&L get their config replaced with a variant
        of the day's top-performing strategy. Called automatically at 16:15 ET.
        Returns list of replacement actions for Telegram report.
        """
        live_prices = live_prices or {}
        replacements = []

        with self._lock:
            # Rank by P&L
            ranked = sorted(
                self.portfolios.items(),
                key=lambda kv: kv[1].get_pnl(live_prices),
                reverse=True,
            )

            # Top 2 winners — use as templates
            winners = [(name, pf) for name, pf in ranked if pf.get_pnl(live_prices) > 0]
            if not winners:
                return []  # no positive strategy to clone from

            # Losers = negative P&L
            losers = [(name, pf) for name, pf in ranked if pf.get_pnl(live_prices) < 0]
            if not losers:
                return []

            for i, (loser_name, loser_pf) in enumerate(losers):
                # Pick template: cycle through winners
                template_name, template_pf = winners[i % len(winners)]
                base_cfg = dict(template_pf.config)

                # Vary slightly so strategies diverge from each other
                variation = i + 1
                new_cfg = dict(base_cfg)
                new_cfg["min_rvol"]   = round(base_cfg["min_rvol"] + variation * 0.15, 2)
                new_cfg["min_conf"]   = base_cfg["min_conf"] + variation * 2
                new_cfg["stop_pct"]   = round(base_cfg["stop_pct"] + variation * 0.3, 1)
                new_cfg["target_pct"] = round(base_cfg["target_pct"] + variation * 1.5, 1)
                new_cfg["max_positions"] = base_cfg.get("max_positions", 3)
                # Remove special requirements from clone (keeps it general)
                new_cfg["requires_pattern"]  = None
                new_cfg["requires_seasonal"] = None
                new_cfg["requires_short_float"] = None
                new_cfg["label"] = f"{base_cfg.get('label','?')} v{variation+1}"
                new_cfg["description"] = (
                    f"Clone of {template_name} (variation {variation}) — "
                    f"auto-replaced {loser_name} at EOD"
                )

                # Force close losing positions only — keep profitable ones running
                closed_tickers = []
                for ticker in list(loser_pf.positions.keys()):
                    price = live_prices.get(ticker) or loser_pf.positions[ticker].get("entry_price", 0)
                    pos_pnl_pct = (price - loser_pf.positions[ticker]["entry_price"]) / loser_pf.positions[ticker]["entry_price"] * 100
                    if pos_pnl_pct > 0:
                        print(f"[Arena] EOD: keeping {ticker} (pnl={pos_pnl_pct:+.1f}%) — profitable, not closing")
                        continue  # don't kill winning positions
                    trade = loser_pf.close_position(ticker, price, "eod_replace")
                    if trade:
                        closed_tickers.append(ticker)
                        self._add_event("SELL", loser_name, ticker, price,
                                        trade.get("pnl_pct", 0), "eod_replace")

                # Apply new config
                STRATEGY_CONFIGS[loser_name] = new_cfg
                loser_pf.config = new_cfg
                pnl = loser_pf.get_pnl(live_prices)

                replacements.append({
                    "replaced":   loser_name,
                    "template":   template_name,
                    "new_label":  new_cfg["label"],
                    "old_pnl":    round(pnl, 2),
                    "closed":     closed_tickers,
                })
                print(f"[Arena] EOD replace: {loser_name} → clone of {template_name} "
                      f"({new_cfg['label']}) | closed: {closed_tickers}")

            self._save(live_prices)
        return replacements

    def _reset_week(self):
        self.week_start       = _week_start()
        self.current_day      = _today()
        self.daily_history    = []
        self.weekly_winner    = None
        self.weekly_winner_at = None
        self.tick_count       = 0
        for pf in self.portfolios.values():
            pf.__init__(pf.name, pf.config)
        print(f"[Arena] New week started: {self.week_start}")

    # ── Core Logic ───────────────────────────────────────────────────────────

    @staticmethod
    def _spy_is_bearish(live_prices: dict) -> bool:
        """
        Global rule #1: if SPY is down > 0.5% on the day, block new entries.
        Uses live_prices cache; if SPY not present, allows trading (fail open).
        """
        spy = live_prices.get("SPY") or live_prices.get("spy")
        spy_prev = live_prices.get("SPY_prev_close") or live_prices.get("spy_prev_close")
        if not spy or not spy_prev or spy_prev <= 0:
            return False
        return (spy - spy_prev) / spy_prev * 100 < -0.5

    def think(self, stocks: list, live_prices: dict) -> dict:
        """Run one tick for all strategies. Works in all market sessions."""
        with self._lock:
            session = get_session_type()
            if session == "closed":
                return self.get_status(live_prices)

            # New week? Full reset.
            if _week_start() != self.week_start:
                self._reset_week()

            # Track current day
            today = _today()
            self.current_day = today

            # Session overrides
            ov = _SESSION_OVERRIDES.get(session, _SESSION_OVERRIDES["regular"])

            # Global rule #1: SPY regime — block all new entries on red market days
            spy_bearish = self._spy_is_bearish(live_prices)

            # Current ET time in minutes for entry_cutoff_et checks
            et_now   = _et_now()
            et_mins  = et_now.hour * 60 + et_now.minute

            # Pre-score all stocks
            scored = []
            import math as _math
            for s in stocks:
                ticker = s.get("ticker", "").upper()
                if not ticker: continue
                price = _safe_float(s.get("price"))
                if price <= 0 or _math.isnan(price) or _math.isinf(price): continue
                scored.append((ticker, price, _arena_score(s), s))
            scored.sort(key=lambda x: -x[2])

            new_positions_this_tick = {name: 0 for name in self.portfolios}

            for pf in self.portfolios.values():
                cfg = pf.config

                # 1. Check stops / stale exits — capture closed trades as events
                trades_before = len(pf.trades)
                pf.check_stops(live_prices)
                for trade in pf.trades[trades_before:]:
                    self._add_event("SELL", pf.name, trade["ticker"],
                                    trade["exit_price"], trade["pnl_pct"], trade["reason"])

                # 2. Skip new entries if at max positions
                if len(pf.positions) >= cfg["max_positions"]:
                    continue

                # 3. Respect per-tick new-position limit for extended hours
                if new_positions_this_tick[pf.name] >= ov["max_new_pos"]:
                    continue

                # Global rule #1: no new entries when SPY is bearish (regular session only)
                if spy_bearish and session == "regular":
                    continue

                # Global rule #2: entry time window (regular session only)
                if session == "regular" and cfg.get("entry_cutoff_et"):
                    if et_mins > cfg["entry_cutoff_et"]:
                        continue

                effective_min_rvol = cfg["min_rvol"] * ov["rvol_factor"]
                extra_stop         = ov["stop_add_pct"]

                # 4. Find best candidate
                for ticker, price, score, stock in scored:
                    if ticker in pf.positions: continue

                    health = _safe_float(stock.get("health_score"))
                    rvol   = _safe_float(stock.get("rel_volume"))
                    chg    = _safe_float(stock.get("change_pct"))
                    sf     = _safe_float(stock.get("short_float"))
                    raw_conf = score * CONF_MULTIPLIER
                    if _math.isnan(raw_conf) or _math.isinf(raw_conf):
                        continue
                    conf   = min(95, int(raw_conf))

                    if health < cfg["min_health"]:          continue
                    if conf   < cfg["min_conf"]:            continue
                    if rvol   < effective_min_rvol:         continue
                    if chg    > cfg["max_day_chg"]:         continue
                    if cfg["requires_short_float"] and sf < cfg["requires_short_float"]:
                        continue
                    if not ov["skip_min_chg"] and cfg["requires_min_chg"]:
                        if chg < cfg["requires_min_chg"]:  continue
                    if cfg.get("requires_seasonal") and not _safe_float(stock.get("seasonal_score")):
                        continue
                    if cfg.get("requires_pattern") and _safe_float(stock.get("pattern_win_rate", 0)) < 60:
                        continue
                    if cfg.get("max_price") and price > cfg["max_price"]:
                        continue
                    if cfg.get("requires_gap"):
                        gap = _safe_float(stock.get("gap_pct", stock.get("gap", 0)))
                        if gap <= 0 and chg < 3.0:
                            continue
                    if cfg.get("requires_float_shares_max"):
                        float_shares = _safe_float(stock.get("float_shares", stock.get("float_shares_num", 0)))
                        if float_shares > 0 and float_shares > cfg["requires_float_shares_max"]:
                            continue
                    if cfg.get("small_cap_only"):
                        cap = _safe_float(stock.get("market_cap", stock.get("cap", 0)))
                        if cap > 2_000_000_000 and price > 50:
                            continue

                    stop_override = cfg["stop_pct"] + extra_stop if extra_stop else None
                    if pf.open_position(ticker, price, stop_override=stop_override):
                        self._add_event("BUY", pf.name, ticker, price, 0.0, "Entry")
                        new_positions_this_tick[pf.name] += 1
                        break

            self.tick_count += 1
            self.last_tick   = datetime.now().isoformat()
            self._save(live_prices)
            return self.get_status(live_prices)

    def _add_event(self, action: str, strategy: str, ticker: str,
                   price: float, pnl_pct: float = 0.0, reason: str = ""):
        cfg   = STRATEGY_CONFIGS.get(strategy, {})
        event = {
            "action":   action,       # "BUY" | "SELL"
            "strategy": strategy,
            "label":    cfg.get("label", strategy),
            "ticker":   ticker,
            "price":    round(price, 2),
            "pnl_pct":  round(pnl_pct, 2),
            "reason":   reason,
            "time":     datetime.now().isoformat(),
        }
        self.recent_events.append(event)
        if len(self.recent_events) > 50:
            self.recent_events = self.recent_events[-50:]

    def declare_daily_winner(self, live_prices: dict = None) -> dict:
        """Archive today's winner. Called at 16:05 ET each trading day."""
        with self._lock:
            live_prices = live_prices or {}
            today = _today()

            # Don't double-archive same day
            if self.daily_history and self.daily_history[-1]["date"] == today:
                return {"already_declared": True, "date": today,
                        "history": self.daily_history}

            pnls = {
                name: pf.get_pnl_pct(live_prices)
                for name, pf in self.portfolios.items()
            }
            winner_name = max(pnls, key=pnls.get)
            cfg = STRATEGY_CONFIGS[winner_name]

            snapshot = {
                "date":     today,
                "weekday":  _et_now().strftime("%A"),
                "winner":   winner_name,
                "label":    cfg["label"],
                "pnl_pcts": {k: round(v, 2) for k, v in pnls.items()},
            }
            self.daily_history.append(snapshot)

            # Friday → also declare weekly winner
            is_friday = _et_now().weekday() == 4
            if is_friday and not self.weekly_winner:
                total_pnls = {
                    name: pf.get_pnl(live_prices)
                    for name, pf in self.portfolios.items()
                }
                ww_name = max(total_pnls, key=total_pnls.get)
                self.weekly_winner    = {
                    "name":    ww_name,
                    "label":   STRATEGY_CONFIGS[ww_name]["label"],
                    "pnl_pct": round(self.portfolios[ww_name].get_pnl_pct(live_prices), 2),
                    "pnl":     round(total_pnls[ww_name], 2),
                }
                self.weekly_winner_at = datetime.now().isoformat()
                self._apply_winner_to_main(ww_name, total_pnls[ww_name])
                print(f"[Arena] 🏆 WEEKLY WINNER: {ww_name}")

            self._save(live_prices)
            return {"date": today, "winner": winner_name,
                    "label": cfg["label"], "pnl_pcts": pnls,
                    "history": self.daily_history}

    def get_status(self, live_prices: dict = None) -> dict:
        live_prices = live_prices or {}
        session = get_session_type()
        leaderboard = []
        for name, pf in self.portfolios.items():
            cfg = STRATEGY_CONFIGS[name]
            full_closes = [t for t in pf.trades if not t.get("was_partial")]
            wins        = sum(1 for t in full_closes if t["pnl"] > 0)
            win_rate    = (wins / len(full_closes) * 100) if full_closes else 0.0

            # Day-wins count from history
            day_wins = sum(
                1 for d in self.daily_history if d.get("winner") == name
            )

            leaderboard.append({
                "name":          name,
                "label":         cfg["label"],
                "description":   cfg["description"],
                "equity":        round(pf.get_equity(live_prices), 2),
                "pnl":           round(pf.get_pnl(live_prices), 2),
                "pnl_pct":       round(pf.get_pnl_pct(live_prices), 2),
                "win_rate":      round(win_rate, 1),
                "trades":        len(full_closes),
                "partial_trades": sum(1 for t in pf.trades if t.get("was_partial")),
                "open_positions": len(pf.positions),
                "day_wins":       day_wins,
                "trade_log":      pf.trades[-10:],   # last 10 closed trades per strategy
                "positions": {
                    t: {
                        "entry":      pos["entry_price"],
                        "entry_price": pos["entry_price"],
                        "entry_time": pos.get("entry_time", ""),
                        "stop":       pos["stop_loss"],
                        "target":     pos["target"],
                        "current":    live_prices.get(t) or pos["entry_price"],
                        "pnl_pct":    round(
                            ((live_prices.get(t) or pos["entry_price"]) - pos["entry_price"])
                            / pos["entry_price"] * 100, 2
                        ),
                        "trailing":   pos.get("trailing_active", False),
                        "session":    pos.get("session", "regular"),
                    }
                    for t, pos in pf.positions.items()
                },
            })

        leaderboard.sort(key=lambda x: -x["pnl"])
        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1

        return {
            "session":          session,
            "week_start":       self.week_start,
            "current_day":      self.current_day,
            "tick_count":       self.tick_count,
            "last_tick":        self.last_tick,
            "daily_history":    self.daily_history,
            "weekly_winner":    self.weekly_winner,
            "weekly_winner_at": self.weekly_winner_at,
            "leaderboard":      leaderboard,
            "recent_events":    self.recent_events[-20:],  # last 20 buy/sell events
        }

    # ── Apply winner params ──────────────────────────────────────────────────

    def _apply_winner_to_main(self, winner_name: str, winner_pnl: float):
        try:
            arena_cfg = STRATEGY_CONFIGS[winner_name]
            existing  = {}
            if LEARNING_FILE.exists():
                try:
                    existing = json.loads(LEARNING_FILE.read_text())
                except Exception:
                    existing = {}
            strategy = existing.get("strategy", {})
            for arena_key, brain_key in _ARENA_TO_BRAIN_PARAMS.items():
                if arena_key in arena_cfg:
                    strategy[brain_key] = arena_cfg[arena_key]
            strategy["arena_winner"] = winner_name
            strategy["arena_date"]   = _today()
            existing["strategy"]     = strategy
            lessons = existing.get("lessons", [])
            lessons.append({
                "trade":   f"ARENA_WINNER_{winner_name}",
                "pnl":     round(winner_pnl, 2),
                "pnl_pct": round(winner_pnl / ARENA_INITIAL_CAPITAL * 100, 2),
                "lesson":  (
                    f"Weekly arena winner: {STRATEGY_CONFIGS[winner_name]['label']} "
                    f"(${winner_pnl:+.2f}). Strategy params updated."
                ),
                "adjustments": {
                    _ARENA_TO_BRAIN_PARAMS[k]: arena_cfg[k]
                    for k in _ARENA_TO_BRAIN_PARAMS if k in arena_cfg
                },
                "date": datetime.now().isoformat(),
            })
            existing["lessons"] = lessons[-50:]
            existing["updated"] = datetime.now().isoformat()
            LEARNING_FILE.write_text(json.dumps(existing, indent=2, default=str))
            print(f"[Arena] Winner {winner_name} params → ai_learning.json")
        except Exception as e:
            print(f"[Arena] Failed to apply winner: {e}")


# ─── Singleton ───────────────────────────────────────────────────────────────
arena_singleton = StrategyArena()
