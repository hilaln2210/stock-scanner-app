"""
Strategy Arena — 4 mini-portfolios competing on live data all day.
Each gets $1,000 virtual capital. No AI calls — fast rule-based scoring.
At 16:05 ET: winner's params are written to ai_learning.json.

Strategies:
  Balanced       — balanced quality filters
  HighConviction — only the best setups, higher R:R
  SqueezeHunter  — requires short squeeze setup (short_float > 12%)
  Scalper        — high volume + fast moves, tight stop/target
"""

import json
import math
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).parent.parent.parent / "data"
ARENA_FILE = DATA_DIR / "strategy_arena.json"
LEARNING_FILE = DATA_DIR / "ai_learning.json"

ARENA_INITIAL_CAPITAL = 1000.0
CONF_MULTIPLIER = 1.5   # arena_score * CONF_MULTIPLIER = derived confidence

# ─── Strategy Configs ────────────────────────────────────────────────────────
STRATEGY_CONFIGS = {
    "Balanced": {
        "label": "⚖️ Balanced",
        "description": "כניסות מאוזנות — health טוב + מומנטום",
        "min_health": 55,
        "min_conf": 60,
        "min_rvol": 0.8,
        "stop_pct": 4.0,
        "target_pct": 14.0,
        "max_day_chg": 5.0,
        "requires_short_float": None,
        "requires_min_chg": None,
        "max_positions": 3,
    },
    "HighConviction": {
        "label": "🎯 High Conviction",
        "description": "רק הכי טובים — פחות עסקאות, R:R גבוה",
        "min_health": 65,
        "min_conf": 70,
        "min_rvol": 1.0,
        "stop_pct": 3.5,
        "target_pct": 17.5,
        "max_day_chg": 4.0,
        "requires_short_float": None,
        "requires_min_chg": None,
        "max_positions": 2,
    },
    "SqueezeHunter": {
        "label": "🩳 Squeeze Hunter",
        "description": "מניות עם שורט גבוה — לחץ כיסוי שורטים",
        "min_health": 50,
        "min_conf": 58,
        "min_rvol": 0.8,
        "stop_pct": 4.0,
        "target_pct": 20.0,
        "max_day_chg": 999.0,  # squeezes can run — no cap
        "requires_short_float": 12.0,
        "requires_min_chg": None,
        "max_positions": 3,
    },
    "Scalper": {
        "label": "⚡ Scalper",
        "description": "ווליום גבוה + תנועה מהירה — יציאה מהירה",
        "min_health": 55,
        "min_conf": 62,
        "min_rvol": 1.5,
        "stop_pct": 2.5,
        "target_pct": 7.0,
        "max_day_chg": 999.0,
        "requires_short_float": None,
        "requires_min_chg": 1.5,
        "max_positions": 4,
    },
}

# Mapping from arena config keys to ai_learning.json strategy keys
_ARENA_TO_BRAIN_PARAMS = {
    "stop_pct":   "stop_loss_pct",
    "target_pct": "target_pct",
    "min_health": "min_health_score",
    "min_rvol":   "min_rel_volume",
    "min_conf":   "min_confidence",
}


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _safe_float(val, default: float = 0.0) -> float:
    try:
        if isinstance(val, str):
            val = val.replace('%', '').replace(',', '').strip()
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def _arena_score(stock: dict) -> float:
    """Fast deterministic score using only Finviz fields. No AI, no I/O."""
    health = _safe_float(stock.get("health_score"))
    rvol   = _safe_float(stock.get("rel_volume"))
    chg    = _safe_float(stock.get("change_pct"))
    sf     = _safe_float(stock.get("short_float"))
    sq     = _safe_float(stock.get("squeeze_total_score"))
    rsi    = _safe_float(stock.get("rsi"), 50)

    score = health * 0.3 + rvol * 20 + chg * 5
    if sf > 15:
        score += 20
    if sq > 50:
        score += 30
    # RSI penalty for extreme overbought (> 80) entries
    if rsi > 80:
        score -= 15
    return score


# ─── MiniPortfolio ────────────────────────────────────────────────────────────
class MiniPortfolio:
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.cash = ARENA_INITIAL_CAPITAL
        self.positions: dict = {}   # ticker -> position dict
        self.trades: list = []      # closed trade records
        self.partial_taken: set = set()  # tickers where partial TP was taken

    # ── Accounting ──────────────────────────────────────────────────────────

    def get_equity(self, live_prices: dict) -> float:
        equity = self.cash
        for ticker, pos in self.positions.items():
            price = live_prices.get(ticker) or pos["entry_price"]
            equity += pos["qty"] * price
        return equity

    def get_pnl(self, live_prices: dict) -> float:
        return self.get_equity(live_prices) - ARENA_INITIAL_CAPITAL

    def get_pnl_pct(self, live_prices: dict) -> float:
        return self.get_pnl(live_prices) / ARENA_INITIAL_CAPITAL * 100

    def get_win_rate(self) -> float:
        full_closes = [t for t in self.trades if not t.get("was_partial")]
        if not full_closes:
            return 0.0
        wins = sum(1 for t in full_closes if t["pnl"] > 0)
        return wins / len(full_closes) * 100

    # ── Trade Execution ─────────────────────────────────────────────────────

    def open_position(self, ticker: str, price: float) -> bool:
        if price <= 0 or ticker in self.positions:
            return False
        cfg = self.config
        # Position size: up to 30% of current capital
        equity = self.get_equity({ticker: price})
        qty = max(1, int((equity * 0.30) / price))
        cost = price * qty
        if cost > self.cash:
            qty = max(1, int(self.cash / price))
            cost = price * qty
        if qty <= 0 or cost > self.cash:
            return False

        stop  = round(price * (1 - cfg["stop_pct"] / 100), 2)
        target = round(price * (1 + cfg["target_pct"] / 100), 2)

        self.cash -= cost
        self.positions[ticker] = {
            "entry_price": price,
            "qty": qty,
            "stop_loss": stop,
            "target": target,
            "entry_time": datetime.now().isoformat(),
            "highest_price": price,
            "trailing_active": False,
        }
        print(f"[Arena:{self.name}] BUY {ticker} @ ${price:.2f} qty={qty} "
              f"stop=${stop:.2f} target=${target:.2f}")
        return True

    def close_position(self, ticker: str, price: float, reason: str,
                       partial_pct: float = 0.0) -> Optional[dict]:
        pos = self.positions.get(ticker)
        if not pos:
            return None

        close_qty = pos["qty"]
        if 0 < partial_pct < 1:
            close_qty = max(1, int(pos["qty"] * partial_pct))
            # If partial would close everything, make it full
            if close_qty >= pos["qty"]:
                partial_pct = 0.0

        pnl = (price - pos["entry_price"]) * close_qty
        self.cash += pos["entry_price"] * close_qty + pnl

        trade = {
            "ticker": ticker,
            "entry_price": pos["entry_price"],
            "exit_price": price,
            "qty": close_qty,
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl / (pos["entry_price"] * close_qty) * 100, 2),
            "reason": reason,
            "entry_time": pos["entry_time"],
            "exit_time": datetime.now().isoformat(),
            "was_partial": partial_pct > 0,
        }
        self.trades.append(trade)
        print(f"[Arena:{self.name}] CLOSE {ticker} @ ${price:.2f} "
              f"pnl=${pnl:+.2f} ({trade['pnl_pct']:+.1f}%) [{reason}]")

        remaining_qty = pos["qty"] - close_qty
        if remaining_qty > 0 and partial_pct > 0:
            self.positions[ticker] = {**pos, "qty": remaining_qty}
            self.partial_taken.add(ticker)
        else:
            del self.positions[ticker]
            self.partial_taken.discard(ticker)

        return trade

    def check_stops(self, live_prices: dict) -> list:
        """Exit positions that hit stop/target. Returns list of closed trade dicts."""
        closed = []
        for ticker in list(self.positions.keys()):
            pos = self.positions[ticker]
            price = live_prices.get(ticker)
            if not price:
                continue

            # Track highest price
            if price > pos["highest_price"]:
                pos["highest_price"] = price

            entry = pos["entry_price"]
            pnl_pct = (price - entry) / entry * 100

            # Partial TP at +5% (once per position)
            if pnl_pct >= 5 and ticker not in self.partial_taken and pos["qty"] >= 2:
                t = self.close_position(ticker, price, "Partial TP +5%", partial_pct=0.4)
                if t:
                    closed.append(t)
                pos = self.positions.get(ticker)
                if not pos:
                    continue

            # Activate trailing stop at +4%
            if pnl_pct >= 4 and not pos["trailing_active"]:
                pos["trailing_active"] = True
                pos["stop_loss"] = max(pos["stop_loss"], round(entry * 1.01, 2))

            # Move trailing stop up
            if pos["trailing_active"]:
                trail_sl = round(pos["highest_price"] * 0.97, 2)
                if trail_sl > pos["stop_loss"]:
                    pos["stop_loss"] = trail_sl

            # Check stop loss
            if price <= pos["stop_loss"]:
                reason = "Trailing stop" if pos["trailing_active"] else "Stop loss"
                t = self.close_position(ticker, price, reason)
                if t:
                    closed.append(t)
                continue

            # Check target
            if price >= pos["target"]:
                t = self.close_position(ticker, price, "Target reached")
                if t:
                    closed.append(t)

        return closed

    # ── Serialization ────────────────────────────────────────────────────────

    def to_dict(self, live_prices: dict) -> dict:
        return {
            "name": self.name,
            "cash": round(self.cash, 2),
            "equity": round(self.get_equity(live_prices), 2),
            "pnl": round(self.get_pnl(live_prices), 2),
            "pnl_pct": round(self.get_pnl_pct(live_prices), 2),
            "positions": self.positions,
            "trades": self.trades,
            "partial_taken": list(self.partial_taken),
        }

    def restore(self, state: dict):
        self.cash = state.get("cash", ARENA_INITIAL_CAPITAL)
        self.positions = state.get("positions", {})
        self.trades = state.get("trades", [])
        self.partial_taken = set(state.get("partial_taken", []))


# ─── StrategyArena ────────────────────────────────────────────────────────────
class StrategyArena:
    def __init__(self):
        self._lock = threading.Lock()
        self.portfolios: dict[str, MiniPortfolio] = {
            name: MiniPortfolio(name, cfg)
            for name, cfg in STRATEGY_CONFIGS.items()
        }
        self.session_date: str = ""
        self.winner: Optional[str] = None
        self.winner_declared_at: Optional[str] = None
        self.tick_count: int = 0
        self.last_tick: Optional[str] = None
        self._load()

    # ── Persistence ─────────────────────────────────────────────────────────

    def _load(self):
        try:
            if ARENA_FILE.exists():
                state = json.loads(ARENA_FILE.read_text())
                today = datetime.now().strftime("%Y-%m-%d")
                if state.get("session_date") == today:
                    for name, pf_state in state.get("portfolios", {}).items():
                        if name in self.portfolios:
                            self.portfolios[name].restore(pf_state)
                    self.session_date = today
                    self.winner = state.get("winner")
                    self.winner_declared_at = state.get("winner_declared_at")
                    self.tick_count = state.get("tick_count", 0)
                    self.last_tick = state.get("last_tick")
                    return
        except Exception:
            pass
        self.session_date = datetime.now().strftime("%Y-%m-%d")
        self.winner = None
        self.tick_count = 0

    def _save(self, live_prices: dict = None):
        try:
            DATA_DIR.mkdir(exist_ok=True)
            state = {
                "session_date": self.session_date,
                "winner": self.winner,
                "winner_declared_at": self.winner_declared_at,
                "tick_count": self.tick_count,
                "last_tick": self.last_tick,
                "portfolios": {
                    name: pf.to_dict(live_prices or {})
                    for name, pf in self.portfolios.items()
                },
            }
            ARENA_FILE.write_text(json.dumps(state, indent=2, default=str))
        except OSError:
            pass

    # ── Core Logic ───────────────────────────────────────────────────────────

    def think(self, stocks: list, live_prices: dict) -> dict:
        """Run one tick for all 4 strategies on the same market data."""
        with self._lock:
            # Reset on new calendar day
            today = datetime.now().strftime("%Y-%m-%d")
            if self.session_date != today:
                for pf in self.portfolios.values():
                    pf.__init__(pf.name, pf.config)
                self.session_date = today
                self.winner = None
                self.winner_declared_at = None
                self.tick_count = 0

            if self.winner:
                # Winner already declared — just update stops
                for pf in self.portfolios.values():
                    pf.check_stops(live_prices)
                self._save(live_prices)
                return self.get_status(live_prices)

            # Pre-score all stocks once
            scored = []
            for s in stocks:
                ticker = s.get("ticker", "").upper()
                if not ticker:
                    continue
                price = _safe_float(s.get("price"))
                if price <= 0:
                    continue
                scored.append((ticker, price, _arena_score(s), s))

            scored.sort(key=lambda x: -x[2])  # best score first

            # Run each portfolio
            for pf in self.portfolios.values():
                cfg = pf.config

                # 1. Check stops first
                pf.check_stops(live_prices)

                # 2. Skip entry if at max positions
                if len(pf.positions) >= cfg["max_positions"]:
                    continue

                # 3. Find best candidate not already held
                for ticker, price, score, stock in scored:
                    if ticker in pf.positions:
                        continue

                    health   = _safe_float(stock.get("health_score"))
                    rvol     = _safe_float(stock.get("rel_volume"))
                    chg      = _safe_float(stock.get("change_pct"))
                    sf       = _safe_float(stock.get("short_float"))
                    conf     = min(95, int(score * CONF_MULTIPLIER))

                    if health < cfg["min_health"]:
                        continue
                    if conf < cfg["min_conf"]:
                        continue
                    if rvol < cfg["min_rvol"]:
                        continue
                    if chg > cfg["max_day_chg"]:
                        continue  # gap filter
                    if cfg["requires_short_float"] and sf < cfg["requires_short_float"]:
                        continue
                    if cfg["requires_min_chg"] and chg < cfg["requires_min_chg"]:
                        continue

                    # Passed all filters — open position
                    pf.open_position(ticker, price)
                    break  # one entry per tick per portfolio

            self.tick_count += 1
            self.last_tick = datetime.now().isoformat()
            self._save(live_prices)
            return self.get_status(live_prices)

    def get_status(self, live_prices: dict = None) -> dict:
        live_prices = live_prices or {}
        leaderboard = []
        for name, pf in self.portfolios.items():
            cfg = STRATEGY_CONFIGS[name]
            full_closes = [t for t in pf.trades if not t.get("was_partial")]
            wins = sum(1 for t in full_closes if t["pnl"] > 0)
            win_rate = (wins / len(full_closes) * 100) if full_closes else 0.0
            leaderboard.append({
                "name": name,
                "label": cfg["label"],
                "description": cfg["description"],
                "equity": round(pf.get_equity(live_prices), 2),
                "pnl": round(pf.get_pnl(live_prices), 2),
                "pnl_pct": round(pf.get_pnl_pct(live_prices), 2),
                "win_rate": round(win_rate, 1),
                "trades": len(full_closes),
                "partial_trades": sum(1 for t in pf.trades if t.get("was_partial")),
                "open_positions": len(pf.positions),
                "positions": {
                    t: {
                        "entry": pos["entry_price"],
                        "stop": pos["stop_loss"],
                        "target": pos["target"],
                        "current": live_prices.get(t) or pos["entry_price"],
                        "pnl_pct": round(
                            ((live_prices.get(t) or pos["entry_price"]) - pos["entry_price"])
                            / pos["entry_price"] * 100, 2
                        ),
                        "trailing": pos.get("trailing_active", False),
                    }
                    for t, pos in pf.positions.items()
                },
            })

        leaderboard.sort(key=lambda x: -x["pnl"])
        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1

        return {
            "session_date": self.session_date,
            "tick_count": self.tick_count,
            "last_tick": self.last_tick,
            "winner": self.winner,
            "winner_declared_at": self.winner_declared_at,
            "leaderboard": leaderboard,
        }

    def declare_winner(self, live_prices: dict = None) -> dict:
        """Pick winner by P&L, write params to ai_learning.json."""
        with self._lock:
            if self.winner:
                return {"already_declared": True, "winner": self.winner}

            live_prices = live_prices or {}
            scores = {
                name: pf.get_pnl(live_prices)
                for name, pf in self.portfolios.items()
            }
            winner_name = max(scores, key=scores.get)
            self.winner = winner_name
            self.winner_declared_at = datetime.now().isoformat()

            winner_pnl = scores[winner_name]
            winner_pnl_pct = winner_pnl / ARENA_INITIAL_CAPITAL * 100

            self._apply_winner_to_main(winner_name, winner_pnl)
            self._save(live_prices)

            return {
                "winner": winner_name,
                "label": STRATEGY_CONFIGS[winner_name]["label"],
                "pnl": round(winner_pnl, 2),
                "pnl_pct": round(winner_pnl_pct, 2),
                "final_scores": {k: round(v, 2) for k, v in scores.items()},
                "declared_at": self.winner_declared_at,
            }

    def _apply_winner_to_main(self, winner_name: str, winner_pnl: float):
        """Write winner strategy params to ai_learning.json (read-modify-write)."""
        try:
            arena_cfg = STRATEGY_CONFIGS[winner_name]
            existing = {}
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
            strategy["arena_date"] = datetime.now().strftime("%Y-%m-%d")
            existing["strategy"] = strategy

            lessons = existing.get("lessons", [])
            lessons.append({
                "trade": f"ARENA_WINNER_{winner_name}",
                "pnl": round(winner_pnl, 2),
                "pnl_pct": round(winner_pnl / ARENA_INITIAL_CAPITAL * 100, 2),
                "lesson": (
                    f"Arena winner: {STRATEGY_CONFIGS[winner_name]['label']} "
                    f"(${winner_pnl:+.2f}). Strategy params updated automatically."
                ),
                "adjustments": {
                    _ARENA_TO_BRAIN_PARAMS[k]: arena_cfg[k]
                    for k in _ARENA_TO_BRAIN_PARAMS
                    if k in arena_cfg
                },
                "date": datetime.now().isoformat(),
            })
            existing["lessons"] = lessons[-50:]
            existing["updated"] = datetime.now().isoformat()

            LEARNING_FILE.write_text(json.dumps(existing, indent=2, default=str))
            print(f"[Arena] Winner {winner_name} params written to ai_learning.json")
        except Exception as e:
            print(f"[Arena] Failed to apply winner: {e}")


# ─── Singleton ───────────────────────────────────────────────────────────────
arena_singleton = StrategyArena()
