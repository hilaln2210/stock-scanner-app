import { useState } from 'react';
import { TrendingUp, TrendingDown, RefreshCw, AlertCircle, Calendar, BarChart2 } from 'lucide-react';

// ── RSI Circle ────────────────────────────────────────────────────────────────

function RsiGauge({ rsi }) {
  if (!rsi) return null;
  const pct = Math.min(rsi / 100, 1);
  const color = rsi >= 70 ? '#f87171' : rsi <= 30 ? '#4ade80' : rsi >= 55 ? '#60a5fa' : '#94a3b8';
  const r = 22;
  const circ = 2 * Math.PI * r;
  return (
    <div className="flex flex-col items-center gap-0.5">
      <div className="relative" style={{ width: 52, height: 52 }}>
        <svg className="transform -rotate-90" width="52" height="52">
          <circle cx="26" cy="26" r={r} stroke="#334155" strokeWidth="4" fill="transparent" />
          <circle cx="26" cy="26" r={r} stroke={color} strokeWidth="4" fill="transparent"
            strokeDasharray={circ} strokeDashoffset={circ * (1 - pct)} strokeLinecap="round" />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm font-bold" style={{ color }}>{Math.round(rsi)}</span>
        </div>
      </div>
      <span className="text-[10px] text-slate-500 font-semibold">RSI</span>
    </div>
  );
}

// ── Beat Badge ────────────────────────────────────────────────────────────────

function BeatBadge({ pct }) {
  if (!pct) return null;
  return (
    <div className="flex flex-col items-center gap-0.5">
      <div className="px-3 py-1.5 rounded-lg bg-emerald-900/60 border border-emerald-500/40">
        <span className="text-lg font-bold text-emerald-400">+{pct}%</span>
      </div>
      <span className="text-[10px] text-slate-500 font-semibold">Earnings Beat</span>
    </div>
  );
}

// ── Stock Card ────────────────────────────────────────────────────────────────

function StockCard({ stock, rank }) {
  const rankColors = ['bg-yellow-500 text-black', 'bg-slate-300 text-black', 'bg-amber-700 text-white',
                      'bg-slate-700 text-slate-300', 'bg-slate-700 text-slate-300'];
  const priceUp = (stock.price_change_since_earnings || 0) > 0;
  const mcap = stock.market_cap;
  const mcapStr = mcap >= 1e12 ? `$${(mcap / 1e12).toFixed(1)}T`
    : mcap >= 1e9 ? `$${(mcap / 1e9).toFixed(1)}B`
    : mcap >= 1e6 ? `$${(mcap / 1e6).toFixed(0)}M` : '';

  return (
    <div className="bg-slate-800/70 border border-slate-700 rounded-xl p-5 hover:border-blue-500/40 transition-all">
      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          {/* Rank badge */}
          <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold shrink-0 ${rankColors[rank - 1] || rankColors[4]}`}>
            {rank}
          </div>
          <div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-2xl font-bold text-white">{stock.ticker}</span>
              {mcapStr && (
                <span className="px-2 py-0.5 rounded bg-indigo-900/50 border border-indigo-500/30 text-indigo-300 text-xs font-bold">
                  {mcapStr}
                </span>
              )}
              {stock.sector && (
                <span className="text-xs text-slate-500">{stock.sector}</span>
              )}
            </div>
            <p className="text-sm text-slate-400 mt-0.5">{stock.company}</p>
          </div>
        </div>

        {/* Metrics */}
        <div className="flex items-start gap-4 shrink-0">
          <BeatBadge pct={stock.earnings_surprise_pct} />
          <RsiGauge rsi={stock.rsi} />
        </div>
      </div>

      {/* Hebrew reason */}
      <div className="mt-4 px-4 py-3 rounded-lg bg-blue-950/30 border-r-2 border-blue-400/60">
        <p className="text-sm text-slate-200 leading-relaxed text-right" dir="rtl">
          {stock.reason}
        </p>
      </div>

      {/* Price row */}
      <div className="mt-3 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-4">
          <div>
            <span className="text-xs text-slate-500 block">מחיר נוכחי</span>
            <span className="text-xl font-bold text-white font-mono">${stock.price}</span>
          </div>
          {stock.price_change_since_earnings !== 0 && (
            <div>
              <span className="text-xs text-slate-500 block">מאז הדוח</span>
              <span className={`text-sm font-bold flex items-center gap-1 ${priceUp ? 'text-green-400' : 'text-red-400'}`}>
                {priceUp ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
                {priceUp ? '+' : ''}{stock.price_change_since_earnings}%
              </span>
            </div>
          )}
          {stock.earnings_date && (
            <div>
              <span className="text-xs text-slate-500 block">תאריך דוח</span>
              <span className="text-xs text-slate-400">{stock.earnings_date}</span>
            </div>
          )}
        </div>

        {/* Watch level */}
        <div className="flex items-center gap-3 text-sm">
          <div className="px-3 py-2 rounded-lg bg-slate-700/60 border border-slate-600/50">
            <span className="text-xs text-slate-500 block text-right" dir="rtl">⚡ לצפות</span>
            <span className="text-yellow-300 font-semibold" dir="rtl">{stock.watch_level}</span>
          </div>
          <div className="px-3 py-2 rounded-lg bg-slate-700/60 border border-slate-600/50">
            <span className="text-xs text-slate-500 block text-right" dir="rtl">🛡️ תמיכה</span>
            <span className="text-slate-300 font-semibold">${stock.support}</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Market Status Bar ─────────────────────────────────────────────────────────

function MarketStatusBar({ status }) {
  if (!status || !status.summary) return null;
  const spy = status.spy || {};
  const qqq = status.qqq || {};
  const spyUp = (spy.change_pct || 0) >= 0;
  const qqqUp = (qqq.change_pct || 0) >= 0;

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-2">
        <BarChart2 size={16} className="text-blue-400" />
        <span className="text-xs font-bold text-slate-300 uppercase tracking-wide">מצב שוק</span>
      </div>
      <div className="flex items-center gap-6 flex-wrap">
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-400 font-bold">SPY</span>
          <span className="text-sm font-mono font-bold text-white">${spy.price || '—'}</span>
          <span className={`text-sm font-bold ${spyUp ? 'text-green-400' : 'text-red-400'}`}>
            {spyUp ? '▲' : '▼'} {Math.abs(spy.change_pct || 0).toFixed(2)}%
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-400 font-bold">QQQ</span>
          <span className="text-sm font-mono font-bold text-white">${qqq.price || '—'}</span>
          <span className={`text-sm font-bold ${qqqUp ? 'text-green-400' : 'text-red-400'}`}>
            {qqqUp ? '▲' : '▼'} {Math.abs(qqq.change_pct || 0).toFixed(2)}%
          </span>
        </div>
        <span className="text-sm text-slate-300 text-right flex-1" dir="rtl">{status.summary}</span>
      </div>
    </div>
  );
}

// ── Today's Events ────────────────────────────────────────────────────────────

function TodayEvents({ events }) {
  if (!events || events.length === 0) return null;
  const typeColors = {
    PDUFA: 'bg-red-700',
    Approval: 'bg-green-700',
    AdCom: 'bg-orange-700',
    Earnings: 'bg-blue-700',
    Phase3: 'bg-purple-700',
    NDA: 'bg-pink-700',
  };

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <Calendar size={16} className="text-yellow-400" />
        <span className="text-xs font-bold text-slate-300 uppercase tracking-wide">
          אירועים קרובים ({events.length})
        </span>
      </div>
      <div className="space-y-2">
        {events.map((e, i) => (
          <div key={i} className="flex items-center gap-3 text-sm">
            <span className={`px-2 py-0.5 rounded text-[10px] font-bold text-white ${typeColors[e.catalyst_type] || 'bg-slate-600'}`}>
              {e.catalyst_type}
            </span>
            <span className="font-bold text-white">{e.ticker}</span>
            <span className="text-slate-400">{e.company}</span>
            {e.drug_name && <span className="text-slate-500 text-xs">— {e.drug_name}</span>}
            {e.days_until === 0 && <span className="ml-auto text-xs text-yellow-400 font-bold">היום</span>}
            {e.days_until === 1 && <span className="ml-auto text-xs text-orange-400 font-bold">מחר</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Loading / Empty States ────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      <div className="text-center">
        <p className="text-slate-300 font-semibold">בונה את הבריפינג...</p>
        <p className="text-slate-500 text-sm mt-1">סורק מניות עם earnings beat + RSI ניטרלי</p>
        <p className="text-slate-600 text-xs mt-1">עלול לקחת עד דקה</p>
      </div>
    </div>
  );
}

function EmptyState({ onRefetch }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <AlertCircle size={48} className="text-slate-600" />
      <div className="text-center">
        <p className="text-slate-400 font-semibold">לא נמצאו מניות מתאימות</p>
        <p className="text-slate-500 text-sm mt-1">
          אין מניות עם earnings beat ≥15% ו-RSI בין 45-65 כרגע
        </p>
      </div>
      <button
        onClick={onRefetch}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2 text-sm"
      >
        <RefreshCw size={14} /> נסה שוב
      </button>
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

export default function DailyBriefing({ data, loading, onRefetch }) {
  const stocks = data?.stocks || [];
  const marketStatus = data?.market_status || {};
  const todayEvents = data?.today_events || [];
  const generatedAt = data?.generated_at;
  const scanned = data?.candidates_scanned;
  const qualified = data?.qualified_count;

  if (loading && stocks.length === 0) return <LoadingState />;

  return (
    <div className="space-y-4 max-w-3xl mx-auto">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            ☀️ <span dir="rtl">בריפינג יומי</span>
          </h2>
          {generatedAt && (
            <p className="text-xs text-slate-500 mt-0.5">
              עודכן: {new Date(generatedAt).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' })}
              {scanned && ` • נסרקו ${scanned} מניות`}
              {qualified !== undefined && ` • ${qualified} עמדו בקריטריונים`}
            </p>
          )}
        </div>
        <button
          onClick={onRefetch}
          disabled={loading}
          className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-xs flex items-center gap-1.5 disabled:opacity-50"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          רענן
        </button>
      </div>

      {/* Criteria banner */}
      <div className="flex items-center gap-3 px-3 py-2 bg-slate-800/40 border border-slate-700/50 rounded-lg text-xs text-slate-500 flex-wrap" dir="rtl">
        <span className="text-emerald-400 font-semibold">📈 Earnings Beat ≥15%</span>
        <span>•</span>
        <span>RSI 45–65 (ניטרלי)</span>
        <span>•</span>
        <span>ממוין לפי גודל ה-beat</span>
      </div>

      {/* Stock cards */}
      {stocks.length === 0
        ? <EmptyState onRefetch={onRefetch} />
        : stocks.map((stock, i) => (
            <StockCard key={stock.ticker} stock={stock} rank={i + 1} />
          ))
      }

      {/* Divider */}
      {(todayEvents.length > 0 || marketStatus.summary) && (
        <div className="border-t border-slate-700/50 pt-4 space-y-3">
          <TodayEvents events={todayEvents} />
          <MarketStatusBar status={marketStatus} />
        </div>
      )}
    </div>
  );
}
