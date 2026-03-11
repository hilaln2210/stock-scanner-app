"""
Interactive Brokers integration via ib_insync.

Architecture: each data-fetch creates a short-lived IB connection in a
plain daemon thread (no asyncio complications). The main IBService object
tracks connection status and credentials.
"""

import logging
import threading
import itertools
import time
import json
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timedelta

log = logging.getLogger(__name__)

try:
    import ib_insync as _ib
    _IB_AVAILABLE = True
except ImportError:
    _IB_AVAILABLE = False

# Rotating clientId pool to avoid conflicts when requests overlap
_client_id_counter = itertools.count(21)
# Semaphore: max 4 concurrent IB connections for background polling
_ib_semaphore = threading.Semaphore(4)


def _next_client_id() -> int:
    cid = next(_client_id_counter)
    return 21 + (cid - 21) % 78


def _run_in_ib_thread(fn, timeout=12, priority=False):
    """
    Run fn(ib: IB) in a fresh daemon thread with its own IB connection.
    priority=True bypasses semaphore (for user-initiated order operations).
    Returns the result or None on timeout/error.
    """
    result_holder = [None]
    error_holder = [None]
    done = threading.Event()

    def _worker():
        import asyncio
        if not priority:
            if not _ib_semaphore.acquire(timeout=timeout - 1):
                log.warning("[IB] semaphore timeout — too many concurrent connections")
                done.set()
                return
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ib = _ib.IB()
        try:
            cid = _next_client_id()
            ib.RequestTimeout = 2
            # Block auto-disconnect during connect (position/account timeouts)
            _real_disc = ib.disconnect
            _block = [True]
            ib.disconnect = lambda: (log.debug("[IB] blocked auto-disconnect") if _block[0] else _real_disc())
            try:
                ib.connect("127.0.0.1", 4002, clientId=cid, readonly=False, timeout=8)
            except Exception:
                pass  # may "fail" due to startup timeouts
            _block[0] = False
            ib.disconnect = _real_disc

            if ib.client.isConnected():
                result_holder[0] = fn(ib)
            else:
                error_holder[0] = Exception("IB connection not alive after connect")
        except Exception as e:
            error_holder[0] = e
            log.error(f"[IB thread] error: {e}")
        finally:
            try:
                ib.disconnect()
            except Exception:
                pass
            loop.close()
            if not priority:
                _ib_semaphore.release()
            done.set()

    t = threading.Thread(target=_worker, daemon=True, name="ib-fetch")
    t.start()
    done.wait(timeout=timeout)
    if error_holder[0]:
        log.warning(f"[IB] fetch failed: {error_holder[0]}")
    return result_holder[0]


def _ensure_event_loop():
    """Ensure current thread has an event loop (needed for ib_insync operations)."""
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)


class IBService:
    def __init__(self):
        self._connected = False
        self._ever_connected = False  # True after first successful connect
        self._account = ""
        self._host = "127.0.0.1"
        self._port = 4002
        self._lock = threading.Lock()
        self._ib: Optional[_ib.IB] = None
        # Cache to avoid creating a new IB connection on every auto-refresh
        self._positions_cache: List[Dict] = []
        self._positions_cache_time: float = 0
        self._account_cache: Dict = {}
        self._account_cache_time: float = 0
        self._orders_cache: List[Dict] = []
        self._orders_cache_time: float = 0
        self._CACHE_TTL = 20  # seconds
        # Local trade history (persists across reconnections)
        self._trade_history_file = Path(__file__).parent.parent.parent / "data" / "ib_trade_history.json"
        self._trade_history: List[Dict] = self._load_trade_history()

    def _load_trade_history(self) -> List[Dict]:
        try:
            if self._trade_history_file.exists():
                return json.loads(self._trade_history_file.read_text())
        except Exception as e:
            log.warning(f"[IB] Failed to load trade history: {e}")
        return []

    def _save_trade_log(self, entry: Dict):
        """Append a trade to local history and persist."""
        self._trade_history.append(entry)
        # Keep last 500 entries
        self._trade_history = self._trade_history[-500:]
        try:
            self._trade_history_file.parent.mkdir(exist_ok=True)
            self._trade_history_file.write_text(
                json.dumps(self._trade_history, indent=2, default=str)
            )
        except Exception as e:
            log.warning(f"[IB] Failed to save trade history: {e}")

    def get_trade_history(self, limit: int = 50) -> List[Dict]:
        """Return local trade history (most recent first), mapped to execution format."""
        raw = list(reversed(self._trade_history[-limit:]))
        result = []
        for r in raw:
            qty = r.get("shares") or r.get("qty", 0)
            price = r.get("price") or r.get("limit_price", 0)
            action_raw = r.get("action", "")
            # Map BUY/SELL → BOT/SLD (IB execution format expected by frontend)
            action = "BOT" if action_raw.upper() == "BUY" else "SLD" if action_raw.upper() == "SELL" else action_raw
            result.append({
                "exec_id": r.get("exec_id") or r.get("order_id"),
                "date": r.get("date") or r.get("time"),
                "ticker": r.get("ticker", ""),
                "action": action,
                "shares": qty,
                "price": round(price, 4) if price else None,
                "value": round(qty * price, 2) if qty and price else None,
                "commission": r.get("commission"),
                "account": r.get("account", ""),
                "order_type": r.get("order_type", ""),
                "status": r.get("status", ""),
            })
        return result

    # ── helpers ──────────────────────────────────────────────────────────

    def _make_persistent(self, host, port, client_id):
        """Create/replace the persistent IB connection (clientId=20)."""
        done = threading.Event()
        result = [None]

        def _run():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                ib = _ib.IB()
                ib.RequestTimeout = 2

                # Prevent ib_insync from auto-disconnecting on startup timeout
                _real_disconnect = ib.disconnect
                _block_disconnect = [True]
                def _guarded_disconnect():
                    if _block_disconnect[0]:
                        log.info("[IB connect] blocked auto-disconnect during startup")
                        return
                    _real_disconnect()
                ib.disconnect = _guarded_disconnect

                try:
                    ib.connect(host, port, clientId=client_id, readonly=False, timeout=8)
                except Exception as e:
                    log.info(f"[IB connect] connect raised: {e} (checking if alive)")

                # Restore real disconnect
                _block_disconnect[0] = False
                ib.disconnect = _real_disconnect

                # Check if we're actually connected despite ib_insync thinking we failed
                is_alive = False
                try:
                    is_alive = ib.client.isConnected() if hasattr(ib, 'client') else False
                except Exception:
                    pass

                accounts = ib.managedAccounts() or []
                if not accounts and hasattr(ib, 'wrapper'):
                    accounts = getattr(ib.wrapper, 'accounts', [])

                if is_alive or accounts:
                    account = accounts[0] if accounts else ""
                    result[0] = (ib, account)
                    log.info(f"[IB connect] OK — account={account}, client_alive={is_alive}")
                else:
                    log.warning("[IB connect] connection truly failed, no accounts")
                    try:
                        _real_disconnect()
                    except Exception:
                        pass
            except Exception as e:
                log.error(f"[IB connect] {e}")
            finally:
                loop.close()
                done.set()

        t = threading.Thread(target=_run, daemon=True, name="ib-connect")
        t.start()
        done.wait(timeout=20)
        if not done.is_set():
            log.warning("[IB connect] thread timed out")
        return result[0]

    # ── Connection ────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        if not (_IB_AVAILABLE and self._connected and self._ib is not None):
            return False
        try:
            return self._ib.isConnected()
        except Exception:
            self._connected = False
            return False

    def status(self) -> Dict:
        return {
            "connected": self.is_connected(),
            "account": self._account,
            "ib_available": _IB_AVAILABLE,
        }

    def _force_disconnect(self):
        """Force-close stale IB connection so clientId can be reused."""
        with self._lock:
            old_ib = self._ib
            self._ib = None
            self._connected = False
        if old_ib:
            try:
                old_ib.disconnect()
            except Exception:
                pass
            # Force-close the underlying socket if disconnect didn't work
            try:
                if hasattr(old_ib, 'client') and old_ib.client:
                    sock = getattr(old_ib.client, '_socket', None)
                    if sock:
                        sock.close()
            except Exception:
                pass

    async def connect(self, host="127.0.0.1", port=4002, client_id=20) -> Dict:
        if not _IB_AVAILABLE:
            return {"connected": False, "error": "ib_insync לא מותקן"}

        # Disconnect stale connection first — frees clientId
        self._force_disconnect()

        import asyncio
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: self._make_persistent(host, port, client_id)
        )
        if result is None:
            return {"connected": False, "error": "חיבור נכשל (timeout)"}
        ib, account = result
        # Check client-level connection (ib.isConnected may be wrong after startup timeout)
        if not (ib.isConnected() or (hasattr(ib, 'client') and ib.client.isConnected())):
            return {"connected": False, "error": "חיבור נכשל"}
        with self._lock:
            self._ib = ib
            self._account = account
            self._host = host
            self._port = port
            self._connected = True
            self._ever_connected = True
        return {"connected": True, "account": self._account, "host": host, "port": port}

    async def disconnect(self) -> Dict:
        self._force_disconnect()
        return {"disconnected": True}

    # ── Account Summary ───────────────────────────────────────────────────

    async def get_account_summary(self) -> Dict:
        if not self.is_connected():
            if self._account_cache:
                return self._account_cache
            return {"error": "לא מחובר ל-IB"}

        # Serve from cache if fresh
        if time.time() - self._account_cache_time < self._CACHE_TTL and self._account_cache:
            return self._account_cache

        account = self._account

        def _fetch_persistent():
            _ensure_event_loop()
            ib = self._ib
            if not ib or not ib.client.isConnected():
                return None
            ib.reqAccountUpdates(True)
            ib.sleep(2)
            vals = {}
            for v in ib.accountValues():
                if v.currency == "USD" and v.tag in (
                    "NetLiquidation", "TotalCashValue",
                    "UnrealizedPnL", "RealizedPnL", "BuyingPower"
                ):
                    try:
                        vals[v.tag] = float(v.value)
                    except Exception:
                        pass
            return {
                "net_liquidation": vals.get("NetLiquidation", 0),
                "cash": vals.get("TotalCashValue", 0),
                "unrealized_pnl": vals.get("UnrealizedPnL", 0),
                "realized_pnl": vals.get("RealizedPnL", 0),
                "buying_power": vals.get("BuyingPower", 0),
                "account": account,
            }

        import asyncio
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _fetch_persistent)
        if result:
            self._account_cache = result
            self._account_cache_time = time.time()
        return result or self._account_cache or {"error": "timeout"}

    # ── Positions ─────────────────────────────────────────────────────────

    async def get_positions(self) -> List[Dict]:
        if not self.is_connected():
            # Return stale cache if available (keeps UI populated during disconnect)
            if self._positions_cache:
                return self._positions_cache
            return []

        # Serve from cache if fresh (avoid new IB connection on every refresh)
        if time.time() - self._positions_cache_time < self._CACHE_TTL and self._positions_cache:
            return self._positions_cache

        def _fetch_raw_persistent():
            """Get raw positions from persistent IB connection."""
            _ensure_event_loop()
            ib = self._ib
            if not ib or not ib.client.isConnected():
                return None
            ib.reqPositions()
            ib.sleep(3)
            raw = ib.positions()
            log.info(f"[IB] got {len(raw)} positions")
            return [(pos.contract.symbol, pos.contract.currency, pos.position, pos.avgCost, pos.account)
                    for pos in raw if pos.position != 0]

        def _enrich_with_yfinance(raw_positions):
            """Fetch yfinance prices outside IB thread — doesn't hold semaphore."""
            import yfinance as yf
            tickers_needed = [sym for sym, *_ in raw_positions]
            yf_prices: Dict[str, float] = {}
            yf_prev_close: Dict[str, float] = {}

            def _extract_close(data, tk, n_tickers):
                """Extract Close series from yfinance data — handles all column formats."""
                # Try multi-level: data[tk]["Close"]
                if data.columns.nlevels >= 2:
                    level0 = data.columns.get_level_values(0).unique().tolist()
                    if tk in level0:
                        return data[tk]["Close"]
                    if "Close" in level0:
                        col = data["Close"]
                        if hasattr(col, 'columns') and tk in col.columns:
                            return col[tk]
                        if hasattr(col, 'columns'):
                            return col.iloc[:, 0]
                        return col
                # Single-level: data["Close"]
                if "Close" in data.columns:
                    return data["Close"]
                return None

            if tickers_needed:
                try:
                    data = yf.download(
                        tickers_needed,
                        period="2d", interval="1m",
                        progress=False, auto_adjust=True, timeout=10,
                        group_by="ticker",
                    )
                    if data is not None and not data.empty:
                        log.info(f"[IB] yfinance columns: {data.columns.tolist()[:6]}, nlevels={data.columns.nlevels}")
                        for tk in tickers_needed:
                            try:
                                close_col = _extract_close(data, tk, len(tickers_needed))
                                if close_col is None:
                                    log.warning(f"[IB] yfinance: could not find Close for {tk}")
                                    continue
                                # Squeeze DataFrame to Series if needed
                                if hasattr(close_col, 'columns'):
                                    close_col = close_col.iloc[:, 0]
                                close_series = close_col.dropna()
                                if close_series.empty:
                                    log.warning(f"[IB] yfinance: no close data for {tk}")
                                    continue
                                yf_prices[tk] = float(close_series.iloc[-1])
                                today = close_series.index[-1].date()
                                prev = close_series[close_series.index.date < today]
                                if not prev.empty:
                                    yf_prev_close[tk] = float(prev.iloc[-1])
                            except Exception as e:
                                log.warning(f"[IB] yfinance parse error for {tk}: {e}")
                    else:
                        log.warning("[IB] yfinance returned empty data")
                except Exception as e:
                    log.warning(f"[IB] yfinance download failed: {e}")

                # Fallback: per-ticker fetch for any missing prices
                missing = [tk for tk in tickers_needed if tk not in yf_prices]
                for tk in missing:
                    try:
                        hist = yf.Ticker(tk).history(period="2d", interval="1m", timeout=8)
                        if hist is not None and not hist.empty:
                            cs = hist["Close"].dropna()
                            if not cs.empty:
                                yf_prices[tk] = float(cs.iloc[-1])
                                today = cs.index[-1].date()
                                prev = cs[cs.index.date < today]
                                if not prev.empty:
                                    yf_prev_close[tk] = float(prev.iloc[-1])
                                log.info(f"[IB] yfinance fallback OK for {tk}: {yf_prices[tk]}")
                    except Exception as e:
                        log.warning(f"[IB] yfinance fallback failed for {tk}: {e}")

                log.info(f"[IB] yfinance prices: {yf_prices}")

            result = []
            for sym, currency, qty, avg, acct in raw_positions:
                mkt = yf_prices.get(sym, 0.0)
                prev = yf_prev_close.get(sym, 0.0)
                pnl = round((mkt - avg) * qty, 2) if mkt and avg else 0
                pnl_pct = round((mkt - avg) / avg * 100, 2) if mkt and avg else 0
                result.append({
                    "ticker": sym, "currency": currency, "qty": qty,
                    "avg_cost": round(avg, 4),
                    "market_price": round(mkt, 4) if mkt else None,
                    "market_value": round(mkt * qty, 2) if mkt else None,
                    "unrealized_pnl": pnl, "pnl_pct": pnl_pct,
                    "day_change": round(mkt - prev, 4) if mkt and prev else None,
                    "day_change_pct": round((mkt - prev) / prev * 100, 2) if mkt and prev else None,
                    "account": acct,
                })
            return sorted(result, key=lambda x: abs(x.get("market_value") or 0), reverse=True)

        import asyncio
        loop = asyncio.get_running_loop()
        # Step 1: get raw positions from persistent IB connection
        raw = await loop.run_in_executor(None, _fetch_raw_persistent)
        if raw is None:
            return self._positions_cache
        # Step 2: enrich with yfinance (no semaphore, separate thread)
        result = await loop.run_in_executor(None, lambda: _enrich_with_yfinance(raw))
        if result is not None:
            self._positions_cache = result
            self._positions_cache_time = time.time()
        return result if result is not None else self._positions_cache

    # ── Open Orders ───────────────────────────────────────────────────────

    async def get_open_orders(self) -> List[Dict]:
        if not self.is_connected():
            if self._orders_cache:
                return self._orders_cache
            return []

        if time.time() - self._orders_cache_time < self._CACHE_TTL:
            return self._orders_cache

        def _fetch_persistent():
            _ensure_event_loop()
            ib = self._ib
            if not ib or not ib.client.isConnected():
                return None
            trades = ib.reqAllOpenOrders()
            ib.sleep(1)
            seen = set()
            result = []
            _MAX = 1.7976931348623157e+308
            for trade in trades:
                o = trade.order
                if o.orderId in seen:
                    continue
                seen.add(o.orderId)
                c = trade.contract
                s = trade.orderStatus
                result.append({
                    "order_id": o.orderId,
                    "ticker": c.symbol,
                    "action": o.action,
                    "qty": o.totalQuantity,
                    "filled": s.filled,
                    "remaining": s.remaining,
                    "order_type": o.orderType,
                    "limit_price": o.lmtPrice if o.lmtPrice not in (0, _MAX) else None,
                    "stop_price": o.auxPrice if o.auxPrice not in (0, _MAX) else None,
                    "tif": o.tif,
                    "status": s.status,
                })
            return result

        import asyncio
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _fetch_persistent)
        if result is not None:
            self._orders_cache = result
            self._orders_cache_time = time.time()
        return result if result is not None else self._orders_cache

    # ── Executions ────────────────────────────────────────────────────────

    async def get_executions(self, days: int = 7) -> List[Dict]:
        if not self.is_connected():
            return []

        def _fetch(ib: "_ib.IB"):
            since = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d %H:%M:%S")
            ef = _ib.ExecutionFilter(time=since)
            fills = ib.reqExecutions(ef)
            ib.sleep(2)  # wait for execution reports to arrive
            fills = ib.fills()  # get all fills after sleep
            result = []
            _MAX = 1.7976931348623157e+308
            for fill in fills:
                ex = fill.execution
                c = fill.contract
                comm = fill.commissionReport
                result.append({
                    "exec_id": ex.execId,
                    "date": ex.time,
                    "ticker": c.symbol,
                    "action": ex.side,
                    "shares": ex.shares,
                    "price": round(ex.price, 4),
                    "value": round(ex.shares * ex.price, 2),
                    "commission": round(comm.commission, 4) if comm.commission not in (0, _MAX) else None,
                    "account": ex.acctNumber,
                })
            return sorted(result, key=lambda x: x["date"], reverse=True)

        import asyncio
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: _run_in_ib_thread(_fetch, timeout=15)) or []

    # ── Place Order ───────────────────────────────────────────────────────

    async def place_order(self, ticker, action, quantity, order_type="MKT",
                          limit_price=None, stop_price=None, tif="DAY") -> Dict:
        if not self.is_connected():
            return {"error": "לא מחובר ל-IB"}

        def _do_on_persistent():
            """Use the persistent connection (clientId=20) for orders — no new connect needed."""
            _ensure_event_loop()
            ib = self._ib
            if not ib or not ib.client.isConnected():
                return {"error": "חיבור IB לא פעיל"}
            contract = _ib.Stock(ticker.upper(), "SMART", "USD")
            ib.qualifyContracts(contract)
            if order_type == "MKT":
                order = _ib.MarketOrder(action.upper(), quantity, tif=tif)
            elif order_type == "LMT":
                if limit_price is None:
                    return {"error": "limit_price חסר"}
                order = _ib.LimitOrder(action.upper(), quantity, limit_price, tif=tif)
            elif order_type == "STP":
                if stop_price is None:
                    return {"error": "stop_price חסר"}
                order = _ib.StopOrder(action.upper(), quantity, stop_price, tif=tif)
            else:
                return {"error": f"סוג הוראה לא נתמך: {order_type}"}
            order.outsideRth = True  # execute in extended hours too
            trade = ib.placeOrder(contract, order)
            ib.sleep(2)
            return {
                "order_id": trade.order.orderId,
                "ticker": ticker.upper(),
                "action": action.upper(),
                "qty": quantity,
                "order_type": order_type,
                "limit_price": limit_price,
                "status": trade.orderStatus.status,
                "tif": tif,
            }

        import asyncio
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _do_on_persistent)
        if result and "order_id" in result:
            self._orders_cache_time = 0
            self._positions_cache_time = 0
            # Log to local trade history
            self._save_trade_log({
                "time": datetime.now().isoformat(),
                "order_id": result.get("order_id"),
                "ticker": result.get("ticker"),
                "action": result.get("action"),
                "qty": result.get("qty"),
                "order_type": result.get("order_type"),
                "limit_price": result.get("limit_price"),
                "status": result.get("status"),
                "tif": result.get("tif"),
            })
        return result or {"error": "timeout"}

    # ── Cancel Order ──────────────────────────────────────────────────────

    async def cancel_order(self, order_id: int) -> Dict:
        if not self.is_connected():
            return {"error": "לא מחובר ל-IB"}

        def _do_persistent():
            _ensure_event_loop()
            ib = self._ib
            if not ib or not ib.client.isConnected():
                return {"error": "חיבור IB לא פעיל"}
            trades = ib.reqAllOpenOrders()
            ib.sleep(0.5)
            target = next((t for t in trades if t.order.orderId == order_id), None)
            if target is None:
                return {"error": f"הוראה #{order_id} לא נמצאה"}
            ib.cancelOrder(target.order)
            ib.sleep(0.5)
            return {"cancelled": True, "order_id": order_id}

        import asyncio
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, _do_persistent)
        if result and result.get("cancelled"):
            self._orders_cache_time = 0
        return result or {"error": "timeout"}


ib_service = IBService()
