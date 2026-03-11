"""
Arena → IB Live Trader
Bridges the best arena strategy to the IB paper account.
Watches arena recent_events every tick and executes BUY/SELL via IB.
"""

import threading
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Optional

DATA_DIR = Path(__file__).parent.parent.parent / "data"
IB_TRADER_FILE = DATA_DIR / "arena_ib_trader.json"


class ArenaIBTrader:
    def __init__(self):
        self._lock = threading.Lock()
        self.enabled: bool = False
        self.strategy_name: str = ""        # which arena strategy to follow
        self.trade_amount: float = 500.0    # $ allocated per position in IB
        self.seen_event_ids: Set[str] = set()
        self.ib_positions: Dict[str, dict] = {}   # ticker → {qty, entry_price, ...}
        self.trade_log: List[dict] = []
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self):
        try:
            if IB_TRADER_FILE.exists():
                state = json.loads(IB_TRADER_FILE.read_text())
                self.enabled       = state.get("enabled", False)
                self.strategy_name = state.get("strategy_name", "")
                self.trade_amount  = state.get("trade_amount", 500.0)
                self.seen_event_ids = set(state.get("seen_event_ids", []))
                self.ib_positions  = state.get("ib_positions", {})
                self.trade_log     = state.get("trade_log", [])
                print(f"[ArenaIB] Loaded — strategy={self.strategy_name} "
                      f"enabled={self.enabled} open_pos={len(self.ib_positions)}")
        except Exception as e:
            print(f"[ArenaIB] Load error: {e}")

    def _save(self):
        try:
            DATA_DIR.mkdir(exist_ok=True)
            state = {
                "enabled":          self.enabled,
                "strategy_name":    self.strategy_name,
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
            self.trade_amount  = trade_amount
            self._save()
        print(f"[ArenaIB] ✅ Enabled — following '{strategy_name}' @ ${trade_amount}/position")

    def disable(self):
        with self._lock:
            self.enabled = False
            self._save()
        print("[ArenaIB] ⛔ Disabled")

    def get_state(self) -> dict:
        with self._lock:
            pnl = sum(
                t.get("pnl", 0) for t in self.trade_log if t.get("action") == "SELL"
            )
            return {
                "enabled":           self.enabled,
                "strategy_name":     self.strategy_name,
                "trade_amount":      self.trade_amount,
                "ib_positions":      self.ib_positions,
                "trade_log":         self.trade_log[-30:],
                "total_trades":      len([t for t in self.trade_log if t.get("action") == "SELL"]),
                "total_pnl":         round(pnl, 2),
                "seen_events_count": len(self.seen_event_ids),
            }

    # ── Core: process arena events ────────────────────────────────────────────

    async def process_arena_tick(self, recent_events: list, ib_svc) -> list:
        """
        Called after each arena tick.
        Finds new BUY/SELL events for the followed strategy and executes via IB.
        Returns list of actions taken.
        """
        if not self.enabled or not self.strategy_name:
            return []

        if not ib_svc.is_connected():
            return []

        actions = []

        with self._lock:
            for event in recent_events:
                strategy = event.get("strategy", "")
                ticker   = event.get("ticker", "")
                action   = event.get("action", "")    # "BUY" or "SELL"
                price    = float(event.get("price") or 0)
                etime    = str(event.get("time", ""))[:19]

                # Unique event fingerprint
                eid = f"{strategy}-{ticker}-{etime}"

                if eid in self.seen_event_ids:
                    continue
                self.seen_event_ids.add(eid)

                # Only act on events for the chosen strategy
                if strategy != self.strategy_name:
                    continue

                if not ticker or not action or price <= 0:
                    continue

                try:
                    if action == "BUY" and ticker not in self.ib_positions:
                        qty = max(1, int(self.trade_amount / price))
                        result = await ib_svc.place_order(ticker, "BUY", qty)
                        if not result.get("error"):
                            self.ib_positions[ticker] = {
                                "qty":         qty,
                                "entry_price": price,
                                "entry_time":  datetime.now().isoformat(),
                                "order_id":    result.get("order_id"),
                            }
                            log_entry = {
                                "action": "BUY", "ticker": ticker, "qty": qty,
                                "price": price, "time": datetime.now().isoformat(),
                                "order_id": result.get("order_id"),
                            }
                            self.trade_log.append(log_entry)
                            actions.append(log_entry)
                            print(f"[ArenaIB] 🟢 BUY {ticker} qty={qty} @ ${price:.2f}")
                        else:
                            print(f"[ArenaIB] ❌ BUY {ticker} failed: {result['error']}")

                    elif action == "SELL" and ticker in self.ib_positions:
                        pos = self.ib_positions[ticker]
                        qty = pos["qty"]
                        result = await ib_svc.place_order(ticker, "SELL", qty)
                        if not result.get("error"):
                            pnl = (price - pos["entry_price"]) * qty
                            self.ib_positions.pop(ticker)
                            log_entry = {
                                "action": "SELL", "ticker": ticker, "qty": qty,
                                "price": price, "pnl": round(pnl, 2),
                                "pnl_pct": round((price - pos["entry_price"]) / pos["entry_price"] * 100, 2),
                                "time": datetime.now().isoformat(),
                                "order_id": result.get("order_id"),
                            }
                            self.trade_log.append(log_entry)
                            actions.append(log_entry)
                            print(f"[ArenaIB] 🔴 SELL {ticker} qty={qty} @ ${price:.2f} "
                                  f"pnl=${pnl:+.2f} ({log_entry['pnl_pct']:+.1f}%)")
                        else:
                            print(f"[ArenaIB] ❌ SELL {ticker} failed: {result['error']}")

                except Exception as e:
                    print(f"[ArenaIB] Error {action} {ticker}: {e}")

            if actions:
                self._save()

        return actions


arena_ib_trader = ArenaIBTrader()
