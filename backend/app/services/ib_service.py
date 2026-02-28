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


def _next_client_id() -> int:
    cid = next(_client_id_counter)
    # Wrap around at 99 to avoid very large numbers
    return 21 + (cid - 21) % 78


def _run_in_ib_thread(fn, timeout=12):
    """
    Run fn(ib: IB) in a fresh daemon thread with its own IB connection.
    Returns the result or None on timeout/error.
    """
    result_holder = [None]
    error_holder = [None]
    done = threading.Event()

    def _worker():
        import asyncio
        # ib_insync requires an event loop in the thread
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        ib = _ib.IB()
        try:
            cid = _next_client_id()
            ib.connect("127.0.0.1", 4002, clientId=cid, readonly=False, timeout=8)
            result_holder[0] = fn(ib)
        except Exception as e:
            error_holder[0] = e
            log.error(f"[IB thread] error: {e}")
        finally:
            try:
                ib.disconnect()
            except Exception:
                pass
            loop.close()
            done.set()

    t = threading.Thread(target=_worker, daemon=True, name="ib-fetch")
    t.start()
    done.wait(timeout=timeout)
    if error_holder[0]:
        log.warning(f"[IB] fetch failed: {error_holder[0]}")
    return result_holder[0]


class IBService:
    def __init__(self):
        self._connected = False
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
        self._CACHE_TTL = 15  # seconds

    # ── helpers ──────────────────────────────────────────────────────────

    def _make_persistent(self, host, port, client_id):
        """Create/replace the persistent IB connection (clientId=20)."""
        def _worker():
            ib = _ib.IB()
            ib.connect(host, port, clientId=client_id, readonly=False, timeout=10)
            accounts = ib.managedAccounts()
            account = accounts[0] if accounts else ""
            return ib, account

        done = threading.Event()
        result = [None]

        def _run():
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result[0] = _worker()
            except Exception as e:
                log.error(f"[IB connect] {e}")
            finally:
                loop.close()
                done.set()

        t = threading.Thread(target=_run, daemon=True, name="ib-connect")
        t.start()
        done.wait(timeout=15)
        return result[0]

    # ── Connection ────────────────────────────────────────────────────────

    def is_connected(self) -> bool:
        return _IB_AVAILABLE and self._connected and (
            self._ib is not None and self._ib.isConnected()
        )

    def status(self) -> Dict:
        return {
            "connected": self.is_connected(),
            "account": self._account,
            "ib_available": _IB_AVAILABLE,
        }

    async def connect(self, host="127.0.0.1", port=4002, client_id=20) -> Dict:
        if not _IB_AVAILABLE:
            return {"connected": False, "error": "ib_insync לא מותקן"}

        import asyncio
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: self._make_persistent(host, port, client_id)
        )
        if result is None:
            return {"connected": False, "error": "חיבור נכשל (timeout)"}
        ib, account = result
        if not ib.isConnected():
            return {"connected": False, "error": "חיבור נכשל"}
        with self._lock:
            if self._ib and self._ib.isConnected():
                try:
                    self._ib.disconnect()
                except Exception:
                    pass
            self._ib = ib
            self._account = account
            self._host = host
            self._port = port
            self._connected = True
        return {"connected": True, "account": self._account, "host": host, "port": port}

    # ── Account Summary ───────────────────────────────────────────────────

    async def get_account_summary(self) -> Dict:
        if not self.is_connected():
            return {"error": "לא מחובר ל-IB"}

        # Serve from cache if fresh
        if time.time() - self._account_cache_time < self._CACHE_TTL and self._account_cache:
            return self._account_cache

        account = self._account

        def _fetch(ib: "_ib.IB"):
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
        result = await loop.run_in_executor(None, lambda: _run_in_ib_thread(_fetch, timeout=15))
        if result:
            self._account_cache = result
            self._account_cache_time = time.time()
        return result or {"error": "timeout"}

    # ── Positions ─────────────────────────────────────────────────────────

    async def get_positions(self) -> List[Dict]:
        if not self.is_connected():
            return []

        # Serve from cache if fresh (avoid new IB connection on every refresh)
        if time.time() - self._positions_cache_time < self._CACHE_TTL and self._positions_cache:
            return self._positions_cache

        def _fetch(ib: "_ib.IB"):
            ib.reqPositions()
            ib.sleep(3)
            raw = ib.positions()
            log.info(f"[IB] got {len(raw)} positions")

            # Fetch live prices via yfinance (IB paper has no market data)
            tickers_needed = [pos.contract.symbol for pos in raw if pos.position != 0]
            yf_prices: Dict[str, float] = {}
            if tickers_needed:
                try:
                    import yfinance as yf
                    data = yf.download(
                        " ".join(tickers_needed),
                        period="1d", interval="1m",
                        progress=False, auto_adjust=True, timeout=5
                    )
                    close = data.get("Close", data) if hasattr(data, "get") else data
                    if hasattr(close, "iloc") and not close.empty:
                        last_row = close.iloc[-1]
                        if len(tickers_needed) == 1:
                            yf_prices[tickers_needed[0]] = float(last_row)
                        else:
                            for tk in tickers_needed:
                                try:
                                    yf_prices[tk] = float(last_row[tk])
                                except Exception:
                                    pass
                except Exception as e:
                    log.warning(f"[IB] yfinance price fetch failed: {e}")

            result = []
            for pos in raw:
                if pos.position == 0:
                    continue
                c = pos.contract
                avg = pos.avgCost
                qty = pos.position
                mkt = yf_prices.get(c.symbol, 0.0)
                pnl = round((mkt - avg) * qty, 2) if mkt and avg else 0
                pnl_pct = round((mkt - avg) / avg * 100, 2) if mkt and avg else 0
                result.append({
                    "ticker": c.symbol,
                    "currency": c.currency,
                    "qty": qty,
                    "avg_cost": round(avg, 4),
                    "market_price": round(mkt, 4) if mkt else None,
                    "market_value": round(mkt * qty, 2) if mkt else None,
                    "unrealized_pnl": pnl,
                    "pnl_pct": pnl_pct,
                    "account": pos.account,
                })
            return sorted(result, key=lambda x: abs(x.get("market_value") or 0), reverse=True)

        import asyncio
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(None, lambda: _run_in_ib_thread(_fetch, timeout=25))
        if result is not None:
            self._positions_cache = result
            self._positions_cache_time = time.time()
        return result if result is not None else self._positions_cache

    # ── Open Orders ───────────────────────────────────────────────────────

    async def get_open_orders(self) -> List[Dict]:
        if not self.is_connected():
            return []

        def _fetch(ib: "_ib.IB"):
            ib.sleep(1)  # allow order data to arrive
            result = []
            _MAX = 1.7976931348623157e+308
            for trade in ib.openTrades():
                o = trade.order
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
        return await loop.run_in_executor(None, lambda: _run_in_ib_thread(_fetch, timeout=12)) or []

    # ── Executions ────────────────────────────────────────────────────────

    async def get_executions(self, days: int = 7) -> List[Dict]:
        if not self.is_connected():
            return []

        def _fetch(ib: "_ib.IB"):
            since = (datetime.now() - timedelta(days=days)).strftime("%Y%m%d %H:%M:%S")
            ef = _ib.ExecutionFilter(time=since)
            fills = ib.reqExecutions(ef)
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

        # Use persistent connection for order placement (needs to stay connected
        # for order status tracking)
        def _do():
            contract = _ib.Stock(ticker.upper(), "SMART", "USD")
            self._ib.qualifyContracts(contract)
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
            trade = self._ib.placeOrder(contract, order)
            self._ib.sleep(0.5)
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

        done = threading.Event()
        result = [None]

        def _run():
            try:
                result[0] = _do()
            except Exception as e:
                result[0] = {"error": str(e)}
            finally:
                done.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: done.wait(15))
        return result[0] or {"error": "timeout"}

    # ── Cancel Order ──────────────────────────────────────────────────────

    async def cancel_order(self, order_id: int) -> Dict:
        if not self.is_connected():
            return {"error": "לא מחובר ל-IB"}

        def _do():
            target = next(
                (t for t in self._ib.openTrades() if t.order.orderId == order_id), None
            )
            if target is None:
                return {"error": f"הוראה #{order_id} לא נמצאה"}
            self._ib.cancelOrder(target.order)
            self._ib.sleep(0.3)
            return {"cancelled": True, "order_id": order_id}

        done = threading.Event()
        result = [None]

        def _run():
            try:
                result[0] = _do()
            except Exception as e:
                result[0] = {"error": str(e)}
            finally:
                done.set()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, lambda: done.wait(10))
        return result[0] or {"error": "timeout"}


ib_service = IBService()
