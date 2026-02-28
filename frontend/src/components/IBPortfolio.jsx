import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import axios from "axios";
import {
  Wifi, WifiOff, RefreshCw, TrendingUp, TrendingDown,
  X, AlertTriangle, CheckCircle, Loader2
} from "lucide-react";

const api = axios.create({ baseURL: "/api" });

const fmt$ = (n) => {
  if (n == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 }).format(n);
};
const fmtPct = (n) => n == null ? "—" : `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;

// ── Connection Banner ────────────────────────────────────────────────────────
function ConnectBanner({ onConnect, loading }) {
  const [port, setPort] = useState("4002");
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-4">
      <WifiOff size={48} className="text-slate-500" />
      <p className="text-slate-300 text-lg font-semibold">לא מחובר ל-IB Gateway</p>
      <p className="text-slate-500 text-sm text-center max-w-xs">
        ודאי ש-IB Gateway פתוח ומחובר לחשבון הדמו.<br />
        ברירת מחדל: localhost:4002
      </p>
      <div className="flex items-center gap-2">
        <input
          value={port}
          onChange={e => setPort(e.target.value)}
          className="w-24 px-3 py-2 rounded bg-zinc-800 border border-zinc-600 text-zinc-100 text-sm text-center"
          placeholder="4002"
        />
        <button
          onClick={() => onConnect(port)}
          disabled={loading}
          className="px-6 py-2 bg-blue-600 hover:bg-blue-500 disabled:opacity-50 text-white rounded-lg font-semibold flex items-center gap-2"
        >
          {loading ? <Loader2 size={16} className="animate-spin" /> : <Wifi size={16} />}
          התחבר
        </button>
      </div>
    </div>
  );
}

// ── Account Summary ──────────────────────────────────────────────────────────
function AccountSummary({ data }) {
  if (!data || data.error) return null;
  const unreal = data.unrealized_pnl ?? 0;
  const real = data.realized_pnl ?? 0;
  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
      {[
        { label: "שווי נכסי נטו", value: fmt$(data.net_liquidation) },
        { label: "מזומן זמין", value: fmt$(data.cash) },
        { label: "רווח לא ממומש", value: fmt$(unreal), color: unreal >= 0 ? "text-emerald-400" : "text-red-400" },
        { label: "רווח ממומש", value: fmt$(real), color: real >= 0 ? "text-emerald-400" : "text-red-400" },
      ].map(({ label, value, color }) => (
        <div key={label} className="bg-zinc-800/60 border border-zinc-700 rounded-xl p-3">
          <p className="text-xs text-zinc-500 mb-1">{label}</p>
          <p className={`text-lg font-bold font-mono ${color || "text-zinc-100"}`}>{value}</p>
        </div>
      ))}
    </div>
  );
}

// ── Positions Table ──────────────────────────────────────────────────────────
function PositionsTable({ positions }) {
  if (!positions?.length) return (
    <p className="text-zinc-500 text-sm text-center py-6">אין פוזיציות פתוחות</p>
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-zinc-500 text-xs border-b border-zinc-700">
            <th className="text-right pb-2 pr-2">מניה</th>
            <th className="text-right pb-2">כמות</th>
            <th className="text-right pb-2">מחיר קנייה</th>
            <th className="text-right pb-2">מחיר נוכחי</th>
            <th className="text-right pb-2">שווי</th>
            <th className="text-right pb-2">P&L</th>
          </tr>
        </thead>
        <tbody>
          {positions.map(pos => {
            const pnl = pos.unrealized_pnl ?? 0;
            const isUp = pnl >= 0;
            return (
              <tr key={pos.ticker} className="border-b border-zinc-800 hover:bg-zinc-800/40">
                <td className="py-2.5 pr-2">
                  <span className="font-bold text-zinc-100">{pos.ticker}</span>
                  <span className="text-zinc-500 text-xs ml-1">{pos.currency}</span>
                </td>
                <td className="py-2.5 text-right text-zinc-300 font-mono">{pos.qty}</td>
                <td className="py-2.5 text-right text-zinc-400 font-mono">{fmt$(pos.avg_cost)}</td>
                <td className="py-2.5 text-right text-zinc-200 font-mono">{pos.market_price ? fmt$(pos.market_price) : "—"}</td>
                <td className="py-2.5 text-right text-zinc-300 font-mono">{pos.market_value ? fmt$(pos.market_value) : "—"}</td>
                <td className="py-2.5 text-right">
                  <div className={`flex flex-col items-end ${isUp ? "text-emerald-400" : "text-red-400"}`}>
                    <span className="font-mono font-semibold">{fmt$(pnl)}</span>
                    {pos.pnl_pct !== 0 && (
                      <span className="text-xs">{fmtPct(pos.pnl_pct)}</span>
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Order Entry ──────────────────────────────────────────────────────────────
function OrderEntry({ onPlace }) {
  const [ticker, setTicker] = useState("");
  const [qty, setQty] = useState("");
  const [orderType, setOrderType] = useState("MKT");
  const [limitPrice, setLimitPrice] = useState("");
  const [tif, setTif] = useState("DAY");
  const [confirm, setConfirm] = useState(null);
  const [result, setResult] = useState(null);

  const handleSubmit = (action) => {
    if (!ticker || !qty) return;
    setConfirm({ action, ticker: ticker.toUpperCase(), qty, orderType, limitPrice, tif });
  };

  const handleConfirm = async () => {
    const res = await onPlace({ ...confirm });
    setResult(res);
    setConfirm(null);
    if (!res.error) { setTicker(""); setQty(""); setLimitPrice(""); }
  };

  return (
    <div className="bg-zinc-800/40 border border-zinc-700 rounded-xl p-4">
      <h3 className="text-sm font-semibold text-zinc-300 mb-3">ביצוע הוראה</h3>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-3">
        <div>
          <label className="text-xs text-zinc-500 block mb-1">סימול</label>
          <input value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())}
            className="w-full px-3 py-2 bg-zinc-900 border border-zinc-600 rounded-lg text-zinc-100 text-sm font-mono uppercase placeholder-zinc-600"
            placeholder="AAPL" />
        </div>
        <div>
          <label className="text-xs text-zinc-500 block mb-1">כמות</label>
          <input value={qty} onChange={e => setQty(e.target.value)} type="number" min="1"
            className="w-full px-3 py-2 bg-zinc-900 border border-zinc-600 rounded-lg text-zinc-100 text-sm font-mono placeholder-zinc-600"
            placeholder="100" />
        </div>
        <div>
          <label className="text-xs text-zinc-500 block mb-1">סוג הוראה</label>
          <select value={orderType} onChange={e => setOrderType(e.target.value)}
            className="w-full px-3 py-2 bg-zinc-900 border border-zinc-600 rounded-lg text-zinc-100 text-sm">
            <option value="MKT">MKT — שוק</option>
            <option value="LMT">LMT — לימיט</option>
            <option value="STP">STP — סטופ</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-zinc-500 block mb-1">תוקף</label>
          <select value={tif} onChange={e => setTif(e.target.value)}
            className="w-full px-3 py-2 bg-zinc-900 border border-zinc-600 rounded-lg text-zinc-100 text-sm">
            <option value="DAY">DAY</option>
            <option value="GTC">GTC</option>
          </select>
        </div>
      </div>

      {(orderType === "LMT" || orderType === "STP") && (
        <div className="mb-3">
          <label className="text-xs text-zinc-500 block mb-1">
            {orderType === "LMT" ? "מחיר לימיט" : "מחיר סטופ"}
          </label>
          <input value={limitPrice} onChange={e => setLimitPrice(e.target.value)} type="number" step="0.01"
            className="w-40 px-3 py-2 bg-zinc-900 border border-zinc-600 rounded-lg text-zinc-100 text-sm font-mono placeholder-zinc-600"
            placeholder="0.00" />
        </div>
      )}

      <div className="flex gap-3">
        <button onClick={() => handleSubmit("BUY")}
          disabled={!ticker || !qty}
          className="px-6 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 text-white rounded-lg font-semibold text-sm">
          קנה
        </button>
        <button onClick={() => handleSubmit("SELL")}
          disabled={!ticker || !qty}
          className="px-6 py-2 bg-red-600 hover:bg-red-500 disabled:opacity-40 text-white rounded-lg font-semibold text-sm">
          מכור
        </button>
      </div>

      {/* Confirm dialog */}
      {confirm && (
        <div className="mt-3 p-3 bg-yellow-900/30 border border-yellow-600/40 rounded-lg">
          <p className="text-yellow-300 text-sm mb-2 font-semibold">
            ⚠️ אישור הוראה: {confirm.action} {confirm.qty} מניות {confirm.ticker}
            {confirm.orderType !== "MKT" && ` @ $${confirm.limitPrice}`}
            {" "}({confirm.orderType} / {confirm.tif})
          </p>
          <div className="flex gap-2">
            <button onClick={handleConfirm}
              className="px-4 py-1.5 bg-yellow-600 hover:bg-yellow-500 text-white rounded font-semibold text-sm">
              אשרי
            </button>
            <button onClick={() => setConfirm(null)}
              className="px-4 py-1.5 bg-zinc-700 hover:bg-zinc-600 text-zinc-200 rounded text-sm">
              ביטול
            </button>
          </div>
        </div>
      )}

      {/* Result */}
      {result && (
        <div className={`mt-3 p-3 rounded-lg border text-sm flex items-start gap-2 ${result.error ? "bg-red-900/30 border-red-600/40 text-red-300" : "bg-emerald-900/30 border-emerald-600/40 text-emerald-300"}`}>
          {result.error ? <AlertTriangle size={16} className="shrink-0 mt-0.5" /> : <CheckCircle size={16} className="shrink-0 mt-0.5" />}
          <span>{result.error || `הוראה #${result.order_id} נשלחה — ${result.status}`}</span>
          <button onClick={() => setResult(null)} className="ml-auto"><X size={14} /></button>
        </div>
      )}
    </div>
  );
}

// ── Open Orders ──────────────────────────────────────────────────────────────
function OpenOrders({ orders, onCancel }) {
  if (!orders?.length) return (
    <p className="text-zinc-500 text-sm text-center py-4">אין הוראות פתוחות</p>
  );
  return (
    <div className="space-y-2">
      {orders.map(ord => (
        <div key={ord.order_id} className="flex items-center justify-between bg-zinc-800/40 border border-zinc-700 rounded-lg px-3 py-2">
          <div className="flex items-center gap-3 text-sm">
            <span className={`font-bold px-2 py-0.5 rounded text-xs ${ord.action === "BUY" ? "bg-emerald-900/60 text-emerald-300" : "bg-red-900/60 text-red-300"}`}>
              {ord.action}
            </span>
            <span className="font-bold text-zinc-100">{ord.ticker}</span>
            <span className="text-zinc-400">{ord.qty} מניות</span>
            <span className="text-zinc-500">{ord.order_type}{ord.limit_price ? ` @ $${ord.limit_price}` : ""}</span>
            <span className="text-zinc-600 text-xs">{ord.tif}</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-xs text-zinc-500">{ord.status}</span>
            <button onClick={() => onCancel(ord.order_id)}
              className="p-1 rounded hover:bg-red-900/40 text-zinc-500 hover:text-red-400 transition-colors" title="בטל הוראה">
              <X size={15} />
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}

// ── Executions ───────────────────────────────────────────────────────────────
function Executions({ executions }) {
  if (!executions?.length) return (
    <p className="text-zinc-500 text-sm text-center py-4">אין עסקאות אחרונות</p>
  );
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="text-zinc-500 text-xs border-b border-zinc-700">
            <th className="text-right pb-2 pr-2">תאריך</th>
            <th className="text-right pb-2">סימול</th>
            <th className="text-right pb-2">פעולה</th>
            <th className="text-right pb-2">כמות</th>
            <th className="text-right pb-2">מחיר</th>
            <th className="text-right pb-2">שווי</th>
            <th className="text-right pb-2">עמלה</th>
          </tr>
        </thead>
        <tbody>
          {executions.slice(0, 30).map((ex, i) => {
            const isBuy = ex.action === "BOT";
            const dateStr = typeof ex.date === "string" ? ex.date.slice(0, 16).replace("T", " ") : ex.date;
            return (
              <tr key={ex.exec_id || i} className="border-b border-zinc-800/60 hover:bg-zinc-800/30">
                <td className="py-2 pr-2 text-zinc-500 text-xs font-mono">{dateStr}</td>
                <td className="py-2 text-right font-bold text-zinc-100">{ex.ticker}</td>
                <td className="py-2 text-right">
                  <span className={`px-2 py-0.5 rounded text-xs font-bold ${isBuy ? "bg-emerald-900/60 text-emerald-300" : "bg-red-900/60 text-red-300"}`}>
                    {isBuy ? "קנייה" : "מכירה"}
                  </span>
                </td>
                <td className="py-2 text-right text-zinc-300 font-mono">{ex.shares}</td>
                <td className="py-2 text-right text-zinc-300 font-mono">{fmt$(ex.price)}</td>
                <td className="py-2 text-right text-zinc-400 font-mono">{fmt$(ex.value)}</td>
                <td className="py-2 text-right text-zinc-500 font-mono text-xs">
                  {ex.commission != null ? fmt$(ex.commission) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────
export default function IBPortfolio() {
  const qc = useQueryClient();
  const [connectLoading, setConnectLoading] = useState(false);
  const [connectError, setConnectError] = useState("");

  const { data: status, refetch: refetchStatus } = useQuery({
    queryKey: ["ibStatus"],
    queryFn: () => api.get("/ib/status").then(r => r.data),
    refetchInterval: 15000,
  });

  const connected = status?.connected === true;

  const { data: account, refetch: refetchAccount } = useQuery({
    queryKey: ["ibAccount"],
    queryFn: () => api.get("/ib/account").then(r => r.data),
    enabled: connected,
    refetchInterval: 10000,
  });

  const { data: positions, refetch: refetchPositions } = useQuery({
    queryKey: ["ibPositions"],
    queryFn: () => api.get("/ib/positions").then(r => r.data),
    enabled: connected,
    refetchInterval: 10000,
  });

  const { data: orders, refetch: refetchOrders } = useQuery({
    queryKey: ["ibOrders"],
    queryFn: () => api.get("/ib/orders").then(r => r.data),
    enabled: connected,
    refetchInterval: 5000,
  });

  const { data: executions } = useQuery({
    queryKey: ["ibExecutions"],
    queryFn: () => api.get("/ib/executions").then(r => r.data),
    enabled: connected,
    refetchInterval: 30000,
  });

  const handleConnect = async (port) => {
    setConnectLoading(true);
    setConnectError("");
    try {
      const res = await api.post("/ib/connect", { port: parseInt(port) });
      if (!res.data.connected) setConnectError(res.data.error || "חיבור נכשל");
      await refetchStatus();
    } catch (e) {
      setConnectError(e.message);
    } finally {
      setConnectLoading(false);
    }
  };

  const handlePlaceOrder = async (params) => {
    try {
      const res = await api.post("/ib/order", {
        ticker: params.ticker,
        action: params.action,
        qty: parseFloat(params.qty),
        order_type: params.orderType,
        limit_price: params.orderType !== "MKT" && params.limitPrice ? parseFloat(params.limitPrice) : undefined,
        tif: params.tif,
      });
      setTimeout(() => {
        refetchOrders();
        refetchPositions();
        refetchAccount();
        qc.invalidateQueries(["ibExecutions"]);
      }, 1500);
      return res.data;
    } catch (e) {
      return { error: e.message };
    }
  };

  const handleCancelOrder = async (orderId) => {
    try {
      await api.delete(`/ib/order/${orderId}`);
      setTimeout(refetchOrders, 800);
    } catch (e) {
      console.error(e);
    }
  };

  const refreshAll = () => {
    refetchStatus();
    if (connected) { refetchAccount(); refetchPositions(); refetchOrders(); }
  };

  return (
    <div className="text-zinc-100" dir="rtl">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="text-lg font-bold">IB Paper Account</span>
          {status && (
            <span className={`flex items-center gap-1.5 text-xs px-2 py-1 rounded-full border font-semibold ${connected ? "bg-emerald-900/40 border-emerald-600/40 text-emerald-300" : "bg-red-900/40 border-red-600/40 text-red-400"}`}>
              <span className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-400 animate-pulse" : "bg-red-500"}`} />
              {connected ? `מחובר — ${status.account}` : "לא מחובר"}
            </span>
          )}
        </div>
        <button onClick={refreshAll} className="p-2 rounded-lg hover:bg-zinc-700 text-zinc-400 hover:text-zinc-200 transition-colors">
          <RefreshCw size={16} />
        </button>
      </div>

      {/* Connect error */}
      {connectError && (
        <div className="mb-4 p-3 bg-red-900/30 border border-red-600/40 rounded-lg text-red-300 text-sm flex items-center gap-2">
          <AlertTriangle size={15} />
          {connectError}
          <button onClick={() => setConnectError("")} className="ml-auto"><X size={14} /></button>
        </div>
      )}

      {!connected ? (
        <ConnectBanner onConnect={handleConnect} loading={connectLoading} />
      ) : (
        <div className="space-y-5">
          {/* Account summary */}
          <AccountSummary data={account} />

          {/* Positions */}
          <section>
            <h3 className="text-sm font-semibold text-zinc-400 mb-2 flex items-center gap-2">
              <TrendingUp size={15} /> פוזיציות פתוחות
              {positions?.length > 0 && <span className="text-xs bg-zinc-700 px-1.5 py-0.5 rounded">{positions.length}</span>}
            </h3>
            <PositionsTable positions={positions} />
          </section>

          {/* Order entry */}
          <OrderEntry onPlace={handlePlaceOrder} />

          {/* Open orders */}
          <section>
            <h3 className="text-sm font-semibold text-zinc-400 mb-2">הוראות פתוחות
              {orders?.length > 0 && <span className="text-xs bg-zinc-700 px-1.5 py-0.5 rounded mr-2">{orders.length}</span>}
            </h3>
            <OpenOrders orders={orders} onCancel={handleCancelOrder} />
          </section>

          {/* Executions */}
          <section>
            <h3 className="text-sm font-semibold text-zinc-400 mb-2">עסקאות אחרונות</h3>
            <Executions executions={executions} />
          </section>
        </div>
      )}
    </div>
  );
}
