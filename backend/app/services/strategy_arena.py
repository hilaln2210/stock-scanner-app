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
        "description": "כניסות מאוזנות — health טוב + מומנטום",
        "min_health": 55, "min_conf": 60, "min_rvol": 0.8,
        "stop_pct": 4.0, "target_pct": 14.0,
        "max_day_chg": 5.0, "requires_short_float": None,
        "requires_min_chg": None, "max_positions": 3,
    },
    "HighConviction": {
        "label": "🎯 High Conviction",
        "description": "רק הכי טובים — פחות עסקאות, R:R גבוה",
        "min_health": 65, "min_conf": 70, "min_rvol": 1.0,
        "stop_pct": 3.5, "target_pct": 17.5,
        "max_day_chg": 4.0, "requires_short_float": None,
        "requires_min_chg": None, "max_positions": 2,
    },
    "SqueezeHunter": {
        "label": "🔥 Squeeze Hunter",
        "description": "מניות עם שורט גבוה — לחץ כיסוי שורטים",
        "min_health": 50, "min_conf": 58, "min_rvol": 0.8,
        "stop_pct": 4.0, "target_pct": 20.0,
        "max_day_chg": 999.0, "requires_short_float": 12.0,
        "requires_min_chg": None, "max_positions": 3,
    },
    "Scalper": {
        "label": "⚡ Scalper",
        "description": "ווליום גבוה + תנועה מהירה — יציאה מהירה",
        "min_health": 55, "min_conf": 62, "min_rvol": 1.5,
        "stop_pct": 2.5, "target_pct": 7.0,
        "max_day_chg": 999.0, "requires_short_float": None,
        "requires_min_chg": 1.5, "max_positions": 4,
    },
    "MomentumBreaker": {
        "label": "🚀 Momentum Breaker",
        "description": "פורצים עם נפח פנומנלי — rvol ≥ 2.5, תנועה > 2%",
        "min_health": 48, "min_conf": 55, "min_rvol": 2.5,
        "stop_pct": 3.5, "target_pct": 11.0,
        "max_day_chg": 15.0, "requires_short_float": None,
        "requires_min_chg": 2.0, "max_positions": 4,
    },
    "SwingSetup": {
        "label": "🌊 Swing Setup",
        "description": "כניסות איכותיות, יעדים גדולים — סבלנות ומשמעת",
        "min_health": 62, "min_conf": 68, "min_rvol": 0.6,
        "stop_pct": 5.0, "target_pct": 20.0,
        "max_day_chg": 3.0, "requires_short_float": None,
        "requires_min_chg": None, "max_positions": 2,
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
        if price <= 0 or ticker in self.positions:
            return False
        cfg    = self.config
        equity = self.get_equity({ticker: price})
        qty    = max(1, int((equity * 0.30) / price))
        cost   = price * qty
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

            # Partial TP at +5%
            if pnl_pct >= 5 and ticker not in self.partial_taken and pos["qty"] >= 2:
                t = self.close_position(ticker, price, "Partial TP +5%", partial_pct=0.4)
                if t: closed.append(t)
                pos = self.positions.get(ticker)
                if not pos: continue

            # Activate trailing stop at +4%
            if pnl_pct >= 4 and not pos["trailing_active"]:
                pos["trailing_active"] = True
                pos["stop_loss"] = max(pos["stop_loss"], round(entry * 1.01, 2))

            if pos["trailing_active"]:
                trail_sl = round(pos["highest_price"] * 0.97, 2)
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
        self.cash          = state.get("cash", ARENA_INITIAL_CAPITAL)
        self.positions     = state.get("positions", {})
        self.trades        = state.get("trades", [])
        self.partial_taken = set(state.get("partial_taken", []))


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
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load(self):
        try:
            if ARENA_FILE.exists():
                state = json.loads(ARENA_FILE.read_text())
                cur_week = _week_start()
                if state.get("week_start") == cur_week:
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
                    return
        except Exception:
            pass
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

            # Pre-score all stocks
            scored = []
            for s in stocks:
                ticker = s.get("ticker", "").upper()
                if not ticker: continue
                price = _safe_float(s.get("price"))
                if price <= 0: continue
                scored.append((ticker, price, _arena_score(s), s))
            scored.sort(key=lambda x: -x[2])

            new_positions_this_tick = {name: 0 for name in self.portfolios}

            for pf in self.portfolios.values():
                cfg = pf.config

                # 1. Check stops / stale exits
                pf.check_stops(live_prices)

                # 2. Skip new entries if at max positions
                if len(pf.positions) >= cfg["max_positions"]:
                    continue

                # 3. Respect per-tick new-position limit for extended hours
                if new_positions_this_tick[pf.name] >= ov["max_new_pos"]:
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
                    conf   = min(95, int(score * CONF_MULTIPLIER))

                    if health < cfg["min_health"]:          continue
                    if conf   < cfg["min_conf"]:            continue
                    if rvol   < effective_min_rvol:         continue
                    if chg    > cfg["max_day_chg"]:         continue
                    if cfg["requires_short_float"] and sf < cfg["requires_short_float"]:
                        continue
                    if not ov["skip_min_chg"] and cfg["requires_min_chg"]:
                        if chg < cfg["requires_min_chg"]:  continue

                    stop_override = cfg["stop_pct"] + extra_stop if extra_stop else None
                    if pf.open_position(ticker, price, stop_override=stop_override):
                        new_positions_this_tick[pf.name] += 1
                        break

            self.tick_count += 1
            self.last_tick   = datetime.now().isoformat()
            self._save(live_prices)
            return self.get_status(live_prices)

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
                "positions": {
                    t: {
                        "entry":   pos["entry_price"],
                        "stop":    pos["stop_loss"],
                        "target":  pos["target"],
                        "current": live_prices.get(t) or pos["entry_price"],
                        "pnl_pct": round(
                            ((live_prices.get(t) or pos["entry_price"]) - pos["entry_price"])
                            / pos["entry_price"] * 100, 2
                        ),
                        "trailing": pos.get("trailing_active", False),
                        "session":  pos.get("session", "regular"),
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
