import { useState } from 'react';
import { TrendingUp, TrendingDown, Minus, RefreshCw, AlertCircle, Target, Shield, Crosshair } from 'lucide-react';

// ── Signal config ──────────────────────────────────────────────────────────────

const SIGNAL_CONFIG = {
  'STRONG BUY': { bg: 'bg-emerald-500',    border: 'border-emerald-400/50', row: 'bg-emerald-950/30',  text: 'text-emerald-300' },
  'BUY':        { bg: 'bg-emerald-700',    border: 'border-emerald-600/40', row: 'bg-emerald-950/20',  text: 'text-emerald-400' },
  'HOLD':       { bg: 'bg-yellow-700',     border: 'border-yellow-600/30',  row: 'bg-yellow-950/10',   text: 'text-yellow-400'  },
  'WAIT':       { bg: 'bg-slate-600',      border: 'border-slate-500/30',   row: 'bg-slate-800/30',    text: 'text-slate-400'   },
  'SELL':       { bg: 'bg-red-700',        border: 'border-red-500/40',     row: 'bg-red-950/20',      text: 'text-red-400'     },
};

const SIGNAL_FILTERS = [
  { key: 'all',         label: 'הכל' },
  { key: 'STRONG BUY', label: 'STRONG BUY' },
  { key: 'BUY',        label: 'BUY' },
  { key: 'HOLD',       label: 'HOLD' },
  { key: 'WAIT',       label: 'WAIT' },
  { key: 'SELL',       label: 'SELL' },
];

// ── Score Bar (6 components) ──────────────────────────────────────────────────

function ScoreBar({ score, breakdown }) {
  const pct = Math.min(score, 100);
  const color = score >= 75 ? '#10b981' : score >= 60 ? '#34d399' : score >= 45 ? '#f59e0b' : score >= 30 ? '#94a3b8' : '#ef4444';
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2">
        <div className="flex-1 bg-slate-700 rounded-full h-2 overflow-hidden">
          <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
        </div>
        <span className="text-sm font-bold font-mono" style={{ color }}>{score}</span>
      </div>
      {breakdown && (
        <div className="flex gap-0.5">
          {[
            { key: 'trend',      max: 30, label: 'T' },
            { key: 'deviation',  max: 20, label: 'D' },
            { key: 'volume',     max: 15, label: 'V' },
            { key: 'ma_support', max: 10, label: 'S' },
            { key: 'macd',       max: 15, label: 'M' },
            { key: 'rsi',        max: 10, label: 'R' },
          ].map(({ key, max, label }) => {
            const val = breakdown[key] || 0;
            const pctInner = (val / max) * 100;
            return (
              <div key={key} className="flex flex-col items-center gap-0.5" title={`${label}: ${val}/${max}`}>
                <div className="w-4 h-3 bg-slate-700 rounded-sm overflow-hidden">
                  <div className="h-full bg-blue-500/60 rounded-sm" style={{ width: `${pctInner}%` }} />
                </div>
                <span className="text-[8px] text-slate-600">{label}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── MA Alignment Indicator ────────────────────────────────────────────────────

function MATrend({ ma5, ma10, ma20, price }) {
  if (!ma5 || !ma10 || !ma20) return null;
  const bull5  = price > ma5;
  const bull10 = price > ma10;
  const bull20 = price > ma20;
  return (
    <div className="flex items-center gap-0.5">
      <span className={`w-2 h-2 rounded-full ${bull5  ? 'bg-emerald-400' : 'bg-red-400'}`} title="MA5" />
      <span className={`w-2 h-2 rounded-full ${bull10 ? 'bg-emerald-400' : 'bg-red-400'}`} title="MA10" />
      <span className={`w-2 h-2 rounded-full ${bull20 ? 'bg-emerald-400' : 'bg-red-400'}`} title="MA20" />
    </div>
  );
}

// ── Stock Card ────────────────────────────────────────────────────────────────

function StockCard({ stock, rank, crossScanners }) {
  const [showLevels, setShowLevels] = useState(false);
  const cfg = SIGNAL_CONFIG[stock.signal] || SIGNAL_CONFIG['HOLD'];
  const priceUp   = stock.change_pct > 0;
  const priceDown = stock.change_pct < 0;
  const rsi12 = stock.rsi?.rsi12;

  return (
    <div className={`rounded-xl border ${cfg.border} ${cfg.row} transition-all hover:opacity-95`}>
      {/* Main row */}
      <div className="grid grid-cols-[auto_1fr_auto_auto_auto_auto_auto_auto] gap-3 items-center px-4 py-3">

        {/* Rank */}
        <span className="text-xs text-slate-500 w-5 text-right font-mono">{rank}</span>

        {/* Ticker + Price */}
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <a
              href={`https://www.tradingview.com/chart/?symbol=${stock.ticker}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-lg font-bold text-white hover:text-blue-400 transition-colors"
            >
              {stock.ticker}
            </a>
            <MATrend ma5={stock.ma5} ma10={stock.ma10} ma20={stock.ma20} price={stock.price} />
            {stock.sector && (
              <span className="px-1.5 py-0.5 rounded text-[9px] font-semibold bg-slate-700/60 text-slate-400 border border-slate-600/40 hidden sm:inline">
                {stock.sector}
              </span>
            )}
            {crossScanners && crossScanners.length > 0 && (
              <span className="px-1.5 py-0.5 rounded bg-amber-900/60 border border-amber-500/50 text-amber-300 text-[9px] font-bold whitespace-nowrap" title="מופיע גם בסורקים אחרים">
                ⭐ {crossScanners.join(' · ')}
              </span>
            )}
            {stock.is_chasing && (
              <span className="text-[9px] bg-orange-900/60 text-orange-300 border border-orange-500/30 px-1.5 py-0.5 rounded font-bold">
                לא לרדוף
              </span>
            )}
          </div>
          <div className="flex items-center gap-2 text-xs mt-0.5">
            <span className="text-slate-300 font-mono font-bold">${stock.price}</span>
            <span className={`font-semibold flex items-center gap-0.5 ${priceUp ? 'text-emerald-400' : priceDown ? 'text-red-400' : 'text-slate-400'}`}>
              {priceUp ? <TrendingUp size={10} /> : priceDown ? <TrendingDown size={10} /> : <Minus size={10} />}
              {priceUp ? '+' : ''}{stock.change_pct}%
            </span>
          </div>
        </div>

        {/* Trend state */}
        <div className="text-center min-w-[80px]">
          <div className="text-[9px] text-slate-500 mb-1">מגמה</div>
          <span className="text-xs font-bold text-slate-200 text-right" dir="rtl">{stock.trend}</span>
          <div className="text-[9px] text-slate-600 mt-0.5 font-mono">
            {stock.deviation > 0 ? '+' : ''}{stock.deviation}% MA5
          </div>
        </div>

        {/* Volume pattern */}
        <div className="text-center min-w-[100px]">
          <div className="text-[9px] text-slate-500 mb-1">כמות</div>
          <div className="text-[10px] text-slate-300 text-right leading-tight" dir="rtl">{stock.vol_pattern}</div>
          <div className="text-[9px] text-slate-600 mt-0.5 font-mono">{stock.vol_ratio}×</div>
        </div>

        {/* MACD */}
        <div className="text-center min-w-[80px]">
          <div className="text-[9px] text-slate-500 mb-1">MACD</div>
          <div className="text-[10px] font-semibold text-slate-300 text-right leading-tight" dir="rtl">{stock.macd_label}</div>
          {stock.macd?.bar !== undefined && (
            <div className={`text-[9px] font-mono mt-0.5 ${stock.macd.bar > 0 ? 'text-emerald-500' : 'text-red-500'}`}>
              {stock.macd.bar > 0 ? '+' : ''}{stock.macd.bar.toFixed(3)}
            </div>
          )}
        </div>

        {/* RSI-12 */}
        <div className="text-center w-14">
          <div className="text-[9px] text-slate-500 mb-1">RSI-12</div>
          <span className={`text-sm font-bold font-mono ${
            rsi12 < 30 ? 'text-emerald-300' :
            rsi12 < 40 ? 'text-emerald-400' :
            rsi12 > 70 ? 'text-red-400' :
            rsi12 > 60 ? 'text-orange-400' : 'text-slate-300'
          }`}>{rsi12 ?? '—'}</span>
          <div className="text-[9px] text-slate-600 mt-0.5">{stock.rsi_label}</div>
        </div>

        {/* Score */}
        <div className="min-w-[90px]">
          <ScoreBar score={stock.score} breakdown={stock.breakdown} />
        </div>

        {/* Signal + levels toggle */}
        <div className="flex flex-col items-center gap-1">
          <span className={`px-2.5 py-1 rounded text-[10px] font-bold text-white ${cfg.bg} whitespace-nowrap`}>
            {stock.signal_he}
          </span>
          <button
            onClick={() => setShowLevels(!showLevels)}
            className="text-[9px] text-slate-500 hover:text-blue-400 flex items-center gap-0.5 transition-colors"
          >
            <Crosshair size={10} />
            {showLevels ? 'הסתר' : 'רמות'}
          </button>
        </div>
      </div>

      {/* Expandable levels row */}
      {showLevels && stock.levels && (
        <div className="px-4 pb-3 pt-0 border-t border-slate-700/30">
          <div className="flex items-center gap-6 mt-2 flex-wrap">
            <div className="flex items-center gap-1.5">
              <Crosshair size={12} className="text-emerald-400" />
              <span className="text-[10px] text-slate-500">כניסה</span>
              <span className="text-sm font-bold text-emerald-400 font-mono">${stock.levels.entry}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Shield size={12} className="text-red-400" />
              <span className="text-[10px] text-slate-500">סטופ</span>
              <span className="text-sm font-bold text-red-400 font-mono">${stock.levels.stop}</span>
            </div>
            <div className="flex items-center gap-1.5">
              <Target size={12} className="text-blue-400" />
              <span className="text-[10px] text-slate-500">יעד</span>
              <span className="text-sm font-bold text-blue-400 font-mono">${stock.levels.target}</span>
            </div>
            <div className="flex items-center gap-1.5 ml-auto">
              <span className="text-[10px] text-slate-500">R:R</span>
              <span className={`text-sm font-bold font-mono ${stock.levels.rr >= 2 ? 'text-emerald-400' : stock.levels.rr >= 1 ? 'text-yellow-400' : 'text-red-400'}`}>
                1:{stock.levels.rr}
              </span>
            </div>
            {/* MA reference */}
            <div className="w-full flex items-center gap-4 text-[9px] text-slate-600 font-mono mt-1">
              {stock.ma5  && <span>MA5: ${stock.ma5}</span>}
              {stock.ma10 && <span>MA10: ${stock.ma10}</span>}
              {stock.ma20 && <span>MA20: ${stock.ma20}</span>}
              {stock.ma60 && <span>MA60: ${stock.ma60}</span>}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Loading / Empty ────────────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <div className="w-12 h-12 border-4 border-indigo-500 border-t-transparent rounded-full animate-spin" />
      <div className="text-center">
        <p className="text-slate-300 font-semibold">מנתח מניות...</p>
        <p className="text-slate-500 text-sm mt-1">MA · סטייה · כמות · MACD · RSI</p>
        <p className="text-slate-600 text-xs mt-1">עלול לקחת עד 2 דקות</p>
      </div>
    </div>
  );
}

function EmptyState({ onRefetch }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <AlertCircle size={48} className="text-slate-600" />
      <p className="text-slate-400 font-semibold">לא נמצאו תוצאות</p>
      <button onClick={onRefetch} className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg flex items-center gap-2 text-sm">
        <RefreshCw size={14} /> נסה שוב
      </button>
    </div>
  );
}

// ── Main Component ─────────────────────────────────────────────────────────────

const SELF_LABEL = '🎯 ניתוח יומי';

export default function DailyAnalysisScanner({ data, loading, onRefetch, crossScannerMap }) {
  const [signalFilter, setSignalFilter] = useState('all');
  const [sectorFilter, setSectorFilter] = useState('');
  const [showFOMO, setShowFOMO] = useState(true);  // show "chasing" stocks?

  const stocks      = data?.stocks || [];
  const generatedAt = data?.generated_at;
  const scanned     = data?.scanned;

  if (loading && stocks.length === 0) return <LoadingState />;

  // Unique sectors sorted by count
  const sectorCounts = stocks.reduce((acc, s) => {
    if (s.sector) acc[s.sector] = (acc[s.sector] || 0) + 1;
    return acc;
  }, {});
  const sectors = Object.entries(sectorCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([s]) => s);

  // Filter
  let filtered = stocks
    .filter(s => signalFilter === 'all' || s.signal === signalFilter)
    .filter(s => !sectorFilter || s.sector === sectorFilter);
  if (!showFOMO) filtered = filtered.filter(s => !s.is_chasing);

  const strongBuy = data?.strong_buy || 0;
  const buy       = data?.buy || 0;
  const sell      = data?.sell || 0;
  const chasing   = stocks.filter(s => s.is_chasing).length;

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <TrendingUp size={22} className="text-indigo-400" />
            <span dir="rtl">ניתוח יומי — ציון מורכב</span>
          </h2>
          {generatedAt && (
            <p className="text-xs text-slate-500 mt-0.5">
              עודכן: {new Date(generatedAt).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' })}
              {scanned && ` • נסרקו ${scanned} מניות`}
              {` • ${stocks.length} תוצאות`}
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

      {/* Scoring legend */}
      <div className="grid grid-cols-3 gap-2 text-[10px] text-slate-500">
        <div className="px-2 py-1.5 bg-slate-800/50 rounded border border-slate-700/50 text-center">
          <span className="text-slate-400 font-semibold block">ציון מורכב</span>
          STRONG BUY ≥75 · BUY 60 · HOLD 45 · WAIT 30 · SELL &lt;30
        </div>
        <div className="px-2 py-1.5 bg-slate-800/50 rounded border border-slate-700/50 text-center">
          <span className="text-slate-400 font-semibold block">רכיבי ציון</span>
          מגמה(30) + סטייה(20) + כמות(15) + תמיכה(10) + MACD(15) + RSI(10)
        </div>
        <div className="px-2 py-1.5 bg-orange-950/30 rounded border border-orange-700/40 text-center">
          <span className="text-orange-400 font-semibold block">⚠️ כלל אנטי-FOMO</span>
          סטייה &gt;5% מ-MA5 = "לא לרדוף" — המתן לתיקון
        </div>
      </div>

      {/* Summary chips */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="px-3 py-1.5 rounded-lg bg-emerald-900/40 border border-emerald-500/30">
          <span className="text-emerald-400 font-bold">{strongBuy}</span>
          <span className="text-emerald-600 text-xs ml-1">STRONG BUY</span>
        </div>
        <div className="px-3 py-1.5 rounded-lg bg-emerald-950/40 border border-emerald-700/30">
          <span className="text-emerald-500 font-bold">{buy}</span>
          <span className="text-emerald-700 text-xs ml-1">BUY</span>
        </div>
        <div className="px-3 py-1.5 rounded-lg bg-red-950/40 border border-red-700/30">
          <span className="text-red-500 font-bold">{sell}</span>
          <span className="text-red-700 text-xs ml-1">SELL</span>
        </div>
        {chasing > 0 && (
          <div className="px-3 py-1.5 rounded-lg bg-orange-950/40 border border-orange-700/30">
            <span className="text-orange-400 font-bold">{chasing}</span>
            <span className="text-orange-600 text-xs ml-1">לא לרדוף</span>
          </div>
        )}
      </div>

      {/* Filters */}
      <div className="flex items-center gap-2 flex-wrap">
        {SIGNAL_FILTERS.map(f => {
          const cfg = SIGNAL_CONFIG[f.key] || {};
          const count = f.key === 'all' ? stocks.length : stocks.filter(s => s.signal === f.key).length;
          return (
            <button
              key={f.key}
              onClick={() => setSignalFilter(f.key)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                signalFilter === f.key
                  ? `${cfg.bg || 'bg-slate-600'} text-white shadow-lg`
                  : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
              }`}
            >
              {f.label} <span className="opacity-70 ml-1">({count})</span>
            </button>
          );
        })}

        <button
          onClick={() => setShowFOMO(!showFOMO)}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ml-auto ${
            !showFOMO
              ? 'bg-orange-700 text-white'
              : 'bg-slate-800 text-slate-400 hover:text-white border border-orange-700/40'
          }`}
        >
          ⚠️ {showFOMO ? 'הסתר' : 'הצג'} "לא לרדוף"
        </button>
      </div>

      {/* Sector filter */}
      {sectors.length > 0 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[10px] text-slate-500 font-semibold shrink-0">סקטור:</span>
          <button
            onClick={() => setSectorFilter('')}
            className={`px-2.5 py-1 rounded text-[10px] font-semibold transition-all ${
              !sectorFilter
                ? 'bg-slate-500 text-white'
                : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
            }`}
          >
            הכל ({stocks.length})
          </button>
          {sectors.map(sec => (
            <button
              key={sec}
              onClick={() => setSectorFilter(sectorFilter === sec ? '' : sec)}
              className={`px-2.5 py-1 rounded text-[10px] font-semibold transition-all ${
                sectorFilter === sec
                  ? 'bg-indigo-600 text-white shadow-lg'
                  : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
              }`}
            >
              {sec} <span className="opacity-60">({sectorCounts[sec]})</span>
            </button>
          ))}
        </div>
      )}

      {/* Column headers */}
      <div className="grid grid-cols-[auto_1fr_auto_auto_auto_auto_auto_auto] gap-3 px-4 py-2 text-[10px] text-slate-500 font-semibold uppercase tracking-wide border-b border-slate-700/50">
        <span className="w-5">#</span>
        <span>מניה</span>
        <span className="text-center w-20">מגמה</span>
        <span className="text-center w-24">כמות</span>
        <span className="text-center w-20">MACD</span>
        <span className="text-center w-14">RSI-12</span>
        <span className="w-24">ציון</span>
        <span className="text-center w-28">סיגנל</span>
      </div>

      {/* Stock rows */}
      {filtered.length === 0 ? (
        <EmptyState onRefetch={onRefetch} />
      ) : (
        <div className="space-y-1.5">
          {filtered.map((stock, i) => (
            <StockCard
              key={stock.ticker}
              stock={stock}
              rank={i + 1}
              crossScanners={crossScannerMap?.[stock.ticker]?.filter(s => s !== SELF_LABEL)}
            />
          ))}
        </div>
      )}

      {/* Footer */}
      <p className="text-[10px] text-slate-600 text-center pt-2 border-t border-slate-700/30">
        מבוסס על daily_stock_analysis (ZhuLinsen) · נתוני EOD · לחץ על "רמות" לצפייה בנקודות כניסה/יעד/סטופ
      </p>
    </div>
  );
}
