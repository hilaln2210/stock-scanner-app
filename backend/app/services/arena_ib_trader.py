"""
Arena → IB Live Trader
Bridges the best arena strategy to the IB paper account.
Watches arena recent_events every tick and executes BUY/SELL via IB.

When strategy_name == "__auto__", automatically follows the #1 strategy
on the leaderboard — the winning strategy always trades on IB.
"""

import asyncio
import threading
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set

DATA_DIR = Path(__file__).parent.parent.parent / "data"
IB_TRADER_FILE = DATA_DIR / "arena_ib_trader.json"

AUTO_FOLLOW = "__auto__"


class ArenaIBTrader:
    def __init__(self):
        self._lock = threading.Lock()
        self.enabled: bool = False
        self.strategy_name: str = ""        # which arena strategy to follow (or "__auto__")
        self.active_strategy: str = ""      # actual strategy being followed right now
        self.trade_amount: float = 500.0    # $ allocated per position in IB
        self.seen_event_ids: Set[str] = set()
        self.ib_positions: Dict[str, dict] = {}   # ticker → {qty, entry_price, ...}
        self.trade_log: List[dict] = []
        self._pending_orders: bool = False  # prevent overlapping order batches
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self):
        try:
            if IB_TRADER_FILE.exists():
                state = json.loads(IB_TRADER_FILE.read_text())
                self.enabled        = state.get("enabled", False)
                self.strategy_name  = state.get("strategy_name", "")
                self.active_strategy = state.get("active_strategy", self.strategy_name)
                self.trade_amount   = state.get("trade_amount", 500.0)
                self.seen_event_ids = set(state.get("seen_event_ids", []))
                self.ib_positions   = state.get("ib_positions", {})
                self.trade_log      = state.get("trade_log", [])
                print(f"[ArenaIB] Loaded — strategy={self.strategy_name} "
                      f"active={self.active_strategy} "
                      f"enabled={self.enabled} open_pos={len(self.ib_positions)}")
        except Exception as e:
            print(f"[ArenaIB] Load error: {e}")

    def _save(self):
        try:
            DATA_DIR.mkdir(exist_ok=True)
            state = {
                "enabled":          self.enabled,
                "strategy_name":    self.strategy_name,
                "active_strategy":  self.active_strategy,
                "trade_amount":     self.trade_amount,
                "seen_event_ids":   list(self.seen_event_ids)[-500:],
                "ib_positions":     self.ib_positions,
                "trade_log":        self.trade_log[-100:],
                "updated":          datetime.now().isoformat(),
            }
            IB_TRADER_FILE.write_text(json.dumps(state, indent=2, default=str))
        except Exception:
            pass

    # ── Control ──────────────────────────────────────────────────────────────

    def enable(self, strategy_name: str, trade_amount: float = 500.0):
        with self._lock:
            self.enabled       = True
            self.strategy_name = strategy_name
            if strategy_name != AUTO_FOLLOW:
                self.active_strategy = strategy_name
            self.trade_amount  = trade_amount
            self._save()
        mode = "auto-follow leader" if strategy_name == AUTO_FOLLOW else f"following '{strategy_name}'"
        print(f"[ArenaIB] Enabled — {mode} @ ${trade_amount}/position")

    def disable(self):
        with self._lock:
            self.enabled = False
            self._save()
        print("[ArenaIB] Disabled")

    def get_state(self) -> dict:
        with self._lock:
            pnl = sum(
                t.get("pnl", 0) for t in self.trade_log if t.get("action") == "SELL"
            )
            return {
                "enabled":           self.enabled,
                "strategy_name":     self.strategy_name,
                "active_strategy":   self.active_strategy,
                "auto_follow":       self.strategy_name == AUTO_FOLLOW,
                "trade_amount":      self.trade_amount,
                "ib_positions":      dict(self.ib_positions),
                "trade_log":         list(self.trade_log[-30:]),
                "total_trades":      len([t for t in self.trade_log if t.get("action") == "SELL"]),
                "total_pnl":         round(pnl, 2),
                "seen_events_count": len(self.seen_event_ids),
            }

    # ── Core: process arena events (non-blocking) ──────────────────────────

    async def process_arena_tick(self, recent_events: list, ib_svc,
                                  leaderboard: list = None):
        """
        Called after each arena tick. Non-blocking — schedules IB orders
        as a background task so the arena think response isn't delayed.
        """
        if not self.enabled:
            return

        if not ib_svc.is_connected():
            return

        if self._pending_orders:
            return  # previous batch still running

        # Collect orders to place (fast, no I/O)
        orders = []
        with self._lock:
            # Auto-follow: update active_strategy to the leaderboard #1
            if self.strategy_name == AUTO_FOLLOW and leaderboard:
                leader_name = leaderboard[0].get("name", "")
                if leader_name and leader_name != self.active_strategy:
                    old = self.active_strategy
                    self.active_strategy = leader_name
                    print(f"[ArenaIB] Leader changed: {old} → {leader_name}")
                    # Queue sells for positions the new leader doesn't hold
                    orders.extend(self._plan_leader_switch(leader_name, leaderboard))

            target_strategy = self.active_strategy
            if not target_strategy:
                return

            # Sync: queue buys for arena positions we don't have yet
            if leaderboard:
                orders.extend(self._plan_position_sync(target_strategy, leaderboard))

            # Process new events
            for event in recent_events:
                strategy = event.get("strategy", "")
                ticker   = event.get("ticker", "")
                action   = event.get("action", "")
                price    = float(event.get("price") or 0)
                etime    = str(event.get("time", ""))[:19]

                eid = f"{strategy}-{ticker}-{etime}"
                if eid in self.seen_event_ids:
                    continue
                self.seen_event_ids.add(eid)

                if strategy != target_strategy:
                    continue
                if not ticker or not action or price <= 0:
                    continue

                if action == "BUY" and ticker not in self.ib_positions:
                    qty = max(1, int(self.trade_amount / price))
                    orders.append(("BUY", ticker, qty, price, target_strategy, "event"))
                elif action == "SELL" and ticker in self.ib_positions:
                    qty = self.ib_positions[ticker]["qty"]
                    orders.append(("SELL", ticker, qty, price, target_strategy, "event"))

            self._save()

        if orders:
            self._pending_orders = True
            asyncio.get_event_loop().create_task(self._execute_orders(orders, ib_svc))

    def _plan_position_sync(self, strategy_name: str, leaderboard: list) -> list:
        """Plan BUY orders for arena positions we don't have on IB yet."""
        leader_data = next((s for s in leaderboard if s.get("name") == strategy_name), None)
        if not leader_data:
            return []
        arena_positions = leader_data.get("positions", {})
        if not isinstance(arena_positions, dict):
            return []

        orders = []
        for ticker, pos_data in arena_positions.items():
            if ticker in self.ib_positions:
                continue
            price = pos_data.get("current") or pos_data.get("entry_price") or pos_data.get("entry", 0)
            if not price or price <= 0:
                continue
            qty = max(1, int(self.trade_amount / price))
            orders.append(("BUY", ticker, qty, price, strategy_name, "sync"))
        return orders

    def _plan_leader_switch(self, new_leader: str, leaderboard: list) -> list:
        """Plan SELL orders for positions not held by the new leader."""
        leader_data = next((s for s in leaderboard if s.get("name") == new_leader), None)
        leader_tickers = set()
        if leader_data and isinstance(leader_data.get("positions"), dict):
            leader_tickers = set(leader_data["positions"].keys())

        orders = []
        for ticker, pos in self.ib_positions.items():
            if ticker not in leader_tickers:
                orders.append(("SELL", ticker, pos["qty"], 0, new_leader, "leader_switch"))
        return orders

    async def _execute_orders(self, orders: list, ib_svc):
        """Execute planned orders sequentially in background."""
        try:
            for action, ticker, qty, price, strategy, reason in orders:
                try:
                    result = await ib_svc.place_order(ticker, action, qty)
                    if result.get("error"):
                        print(f"[ArenaIB] {action} {ticker} failed: {result['error']}")
                        continue

                    with self._lock:
                        if action == "BUY":
                            self.ib_positions[ticker] = {
                                "qty": qty, "entry_price": price,
                                "entry_time": datetime.now().isoformat(),
                                "order_id": result.get("order_id"),
                                "strategy": strategy,
                            }
                            log_entry = {
                                "action": "BUY", "ticker": ticker, "qty": qty,
                                "price": price, "time": datetime.now().isoformat(),
                                "order_id": result.get("order_id"),
                                "strategy": strategy, "reason": reason,
                            }
                        else:  # SELL
                            entry_price = self.ib_positions.get(ticker, {}).get("entry_price", price)
                            pnl = (price - entry_price) * qty if price > 0 else 0
                            self.ib_positions.pop(ticker, None)
                            log_entry = {
                                "action": "SELL", "ticker": ticker, "qty": qty,
                                "price": price, "pnl": round(pnl, 2),
                                "time": datetime.now().isoformat(),
                                "order_id": result.get("order_id"),
                                "strategy": strategy, "reason": reason,
                            }

                        self.trade_log.append(log_entry)
                        self._save()

                    tag = f"[{strategy}/{reason}]"
                    if action == "BUY":
                        print(f"[ArenaIB] BUY {ticker} qty={qty} @ ${price:.2f} {tag}")
                    else:
                        print(f"[ArenaIB] SELL {ticker} qty={qty} {tag}")

                except Exception as e:
                    print(f"[ArenaIB] Error {action} {ticker}: {e}")
        finally:
            self._pending_orders = False


arena_ib_trader = ArenaIBTrader()
