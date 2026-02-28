import { useState } from 'react';
import { TrendingUp, TrendingDown, Minus, RefreshCw, AlertCircle, BarChart2 } from 'lucide-react';

// ── Signal Badge ───────────────────────────────────────────────────────────────

function SignalBadge({ type, compact = false }) {
  // ravening logic: MACD BUY = crosses BELOW signal, SELL = crosses ABOVE
  const cfg = {
    'BUY':         { bg: 'bg-emerald-600',    text: 'text-white',      label: 'BUY' },
    'BELOW':       { bg: 'bg-emerald-900/60', text: 'text-emerald-300', label: 'BELOW SIG' },
    'SELL':        { bg: 'bg-red-600',         text: 'text-white',      label: 'SELL' },
    'ABOVE':       { bg: 'bg-red-900/60',      text: 'text-red-300',    label: 'ABOVE SIG' },
    'NEUTRAL':     { bg: 'bg-slate-700',       text: 'text-slate-300',  label: 'NEUT' },
    'STRONG BUY':  { bg: 'bg-emerald-500',     text: 'text-white',      label: 'STRONG BUY' },
    'STRONG SELL': { bg: 'bg-red-500',         text: 'text-white',      label: 'STRONG SELL' },
  };
  const c = cfg[type] || cfg['NEUTRAL'];
  return (
    <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${c.bg} ${c.text}`}>
      {compact ? c.label : type}
    </span>
  );
}

// ── Signal Dot ────────────────────────────────────────────────────────────────

function SignalDot({ type }) {
  const isBuy  = type === 'BUY' || type === 'BELOW';
  const isSell = type === 'SELL' || type === 'ABOVE';
  return (
    <span className={`inline-block w-2.5 h-2.5 rounded-full ${
      isBuy ? 'bg-emerald-400' : isSell ? 'bg-red-400' : 'bg-slate-500'
    }`} />
  );
}

// ── Composite Score Bar ───────────────────────────────────────────────────────

function ScoreBar({ buys, sells }) {
  return (
    <div className="flex gap-0.5 items-center">
      {[0, 1, 2].map(i => (
        <span key={i} className={`w-3 h-3 rounded-sm ${
          i < buys ? 'bg-emerald-500' : i < (3 - sells) ? 'bg-slate-600' : 'bg-red-500'
        }`} />
      ))}
    </div>
  );
}

// ── Loading / Empty States ─────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4">
      <div className="w-12 h-12 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      <div className="text-center">
        <p className="text-slate-300 font-semibold">מחשב סיגנלים טכניים...</p>
        <p className="text-slate-500 text-sm mt-1">MACD · RSI · Bollinger Bands</p>
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
      <button
        onClick={onRefetch}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2 text-sm"
      >
        <RefreshCw size={14} /> נסה שוב
      </button>
    </div>
  );
}

// ── Filter Bar ────────────────────────────────────────────────────────────────

const SIGNAL_FILTERS = [
  { key: 'all',          label: 'הכל',         color: 'bg-slate-600' },
  { key: 'STRONG BUY',  label: 'STRONG BUY',  color: 'bg-emerald-600' },
  { key: 'BUY',         label: 'BUY',          color: 'bg-emerald-700' },
  { key: 'NEUTRAL',     label: 'נייטרלי',      color: 'bg-slate-700' },
  { key: 'SELL',        label: 'SELL',         color: 'bg-red-700' },
  { key: 'STRONG SELL', label: 'STRONG SELL',  color: 'bg-red-600' },
];

// ── Stock Row ─────────────────────────────────────────────────────────────────

function StockRow({ stock, rank, crossScanners }) {
  const priceUp = stock.change_pct > 0;
  const priceDown = stock.change_pct < 0;
  const compositeColors = {
    'STRONG BUY':  'bg-emerald-500/20 border-emerald-500/40 text-emerald-300',
    'BUY':         'bg-emerald-900/30 border-emerald-700/30 text-emerald-400',
    'NEUTRAL':     'bg-slate-800/50 border-slate-700/30 text-slate-300',
    'SELL':        'bg-red-900/30 border-red-700/30 text-red-400',
    'STRONG SELL': 'bg-red-500/20 border-red-500/40 text-red-300',
  };
  const rowClass = compositeColors[stock.composite] || compositeColors['NEUTRAL'];

  return (
    <div className={`grid grid-cols-[auto_1fr_auto_auto_auto_auto_auto_auto] gap-3 items-center
      px-4 py-3 rounded-lg border ${rowClass} hover:opacity-90 transition-all`}>

      {/* Rank */}
      <span className="text-xs text-slate-500 w-5 text-right">{rank}</span>

      {/* Ticker + Price */}
      <div>
        <div className="flex items-center gap-2">
          <span className="text-base font-bold text-white">{stock.ticker}</span>
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
          <a
            href={`https://www.tradingview.com/chart/?symbol=${stock.ticker}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[10px] text-slate-500 hover:text-blue-400 transition-colors"
          >
            TV
          </a>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="text-slate-300 font-mono">${stock.price}</span>
          <span className={`font-semibold flex items-center gap-0.5 ${
            priceUp ? 'text-emerald-400' : priceDown ? 'text-red-400' : 'text-slate-400'
          }`}>
            {priceUp ? <TrendingUp size={11} /> : priceDown ? <TrendingDown size={11} /> : <Minus size={11} />}
            {priceUp ? '+' : ''}{stock.change_pct}%
          </span>
        </div>
      </div>

      {/* MACD signal */}
      <div className="text-center">
        <div className="text-[9px] text-slate-500 mb-1">MACD</div>
        <div className="flex items-center gap-1 justify-center">
          <SignalDot type={stock.macd.signal_type} />
          <span className="text-[10px] font-bold text-slate-300">{stock.macd.signal_type}</span>
        </div>
        <div className="text-[9px] text-slate-600 mt-0.5 font-mono">
          {stock.macd.histogram > 0 ? '+' : ''}{stock.macd.histogram.toFixed(3)}
        </div>
      </div>

      {/* RSI signal */}
      <div className="text-center">
        <div className="text-[9px] text-slate-500 mb-1">RSI-20</div>
        <div className="flex items-center gap-1 justify-center">
          <SignalDot type={stock.rsi.signal_type} />
          <span className={`text-sm font-bold font-mono ${
            stock.rsi.signal_type === 'BUY' ? 'text-emerald-400' :
            stock.rsi.signal_type === 'SELL' ? 'text-red-400' : 'text-slate-300'
          }`}>{stock.rsi.value}</span>
        </div>
        <div className="text-[9px] text-slate-600 mt-0.5">{stock.rsi.signal_type}</div>
      </div>

      {/* BB signal */}
      <div className="text-center">
        <div className="text-[9px] text-slate-500 mb-1">BB</div>
        <div className="flex items-center gap-1 justify-center">
          <SignalDot type={stock.bb.signal_type} />
          <span className="text-[10px] font-bold text-slate-300">{stock.bb.signal_type}</span>
        </div>
        <div className="text-[9px] text-slate-600 mt-0.5 font-mono">
          %B {stock.bb.pct_b.toFixed(2)}
        </div>
      </div>

      {/* Score bar */}
      <div className="text-center">
        <div className="text-[9px] text-slate-500 mb-1.5">ציון</div>
        <ScoreBar buys={stock.buy_signals} sells={stock.sell_signals} />
      </div>

      {/* Composite signal */}
      <SignalBadge type={stock.composite} />
    </div>
  );
}

// ── Main Component ────────────────────────────────────────────────────────────

const SELF_LABEL = '📈 סיגנלים';

export default function TechnicalSignalsScanner({ data, loading, onRefetch, crossScannerMap }) {
  const [signalFilter, setSignalFilter] = useState('all');
  const [sectorFilter, setSectorFilter] = useState('');
  const [sortBy, setSortBy] = useState('composite'); // 'composite' | 'rsi' | 'change'

  const stocks = data?.stocks || [];
  const generatedAt = data?.generated_at;
  const scanned = data?.scanned;

  if (loading && stocks.length === 0) return <LoadingState />;

  // Unique sectors sorted by count
  const sectorCounts = stocks.reduce((acc, s) => {
    if (s.sector) acc[s.sector] = (acc[s.sector] || 0) + 1;
    return acc;
  }, {});
  const sectors = Object.entries(sectorCounts)
    .sort((a, b) => b[1] - a[1])
    .map(([s]) => s);

  // Filter by signal + sector
  const filtered = stocks
    .filter(s => signalFilter === 'all' || s.composite === signalFilter)
    .filter(s => !sectorFilter || s.sector === sectorFilter);

  // Sort
  const sorted = [...filtered].sort((a, b) => {
    if (sortBy === 'rsi') return a.rsi.value - b.rsi.value;
    if (sortBy === 'change') return b.change_pct - a.change_pct;
    // Default: composite order (already sorted by backend)
    return 0;
  });

  const buyCount      = stocks.filter(s => s.composite === 'STRONG BUY' || s.composite === 'BUY').length;
  const sellCount     = stocks.filter(s => s.composite === 'STRONG SELL' || s.composite === 'SELL').length;
  const strongBuyCount = stocks.filter(s => s.composite === 'STRONG BUY').length;

  return (
    <div className="space-y-4">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <BarChart2 size={22} className="text-blue-400" />
            <span>סיגנלים טכניים</span>
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

      {/* Legend */}
      <div className="flex items-center gap-2 px-3 py-2 bg-slate-800/40 border border-slate-700/50 rounded-lg text-[10px] text-slate-500 flex-wrap" dir="rtl">
        <span className="text-emerald-400 font-semibold">MACD 12/26/9</span>
        <span>•</span>
        <span className="text-blue-400 font-semibold">RSI-20 (קנייה &lt;40, מכירה &gt;70)</span>
        <span>•</span>
        <span className="text-purple-400 font-semibold">BB 20/2σ</span>
      </div>

      {/* Summary chips */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="px-3 py-1.5 rounded-lg bg-emerald-900/40 border border-emerald-500/30">
          <span className="text-emerald-400 font-bold text-sm">{buyCount}</span>
          <span className="text-emerald-500/70 text-xs ml-1">BUY signals</span>
        </div>
        {strongBuyCount > 0 && (
          <div className="px-3 py-1.5 rounded-lg bg-emerald-600/30 border border-emerald-400/40">
            <span className="text-emerald-300 font-bold text-sm">{strongBuyCount}</span>
            <span className="text-emerald-400/70 text-xs ml-1">STRONG BUY</span>
          </div>
        )}
        <div className="px-3 py-1.5 rounded-lg bg-red-900/40 border border-red-500/30">
          <span className="text-red-400 font-bold text-sm">{sellCount}</span>
          <span className="text-red-500/70 text-xs ml-1">SELL signals</span>
        </div>
      </div>

      {/* Signal filter buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        {SIGNAL_FILTERS.map(f => (
          <button
            key={f.key}
            onClick={() => setSignalFilter(f.key)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              signalFilter === f.key
                ? `${f.color} text-white shadow-lg`
                : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
            }`}
          >
            {f.label}
            {f.key !== 'all' && (
              <span className="ml-1.5 opacity-70">
                ({stocks.filter(s => s.composite === f.key).length})
              </span>
            )}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-2">
          <span className="text-xs text-slate-500">מיון:</span>
          {[
            { key: 'composite', label: 'סיגנל' },
            { key: 'rsi',       label: 'RSI ↑' },
            { key: 'change',    label: '% שינוי' },
          ].map(s => (
            <button
              key={s.key}
              onClick={() => setSortBy(s.key)}
              className={`px-2 py-1 rounded text-[10px] font-semibold transition-all ${
                sortBy === s.key
                  ? 'bg-blue-600 text-white'
                  : 'bg-slate-800 text-slate-400 hover:text-white border border-slate-700'
              }`}
            >
              {s.label}
            </button>
          ))}
        </div>
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
      <div className="grid grid-cols-[auto_1fr_auto_auto_auto_auto_auto] gap-3 px-4 py-2 text-[10px] text-slate-500 font-semibold uppercase tracking-wide border-b border-slate-700/50">
        <span className="w-5">#</span>
        <span>מניה</span>
        <span className="text-center w-20">MACD</span>
        <span className="text-center w-16">RSI-20</span>
        <span className="text-center w-16">BB</span>
        <span className="text-center w-14">ציון</span>
        <span className="text-center w-24">קומפוזיט</span>
      </div>

      {/* Stock rows */}
      {sorted.length === 0 ? (
        <EmptyState onRefetch={onRefetch} />
      ) : (
        <div className="space-y-1.5">
          {sorted.map((stock, i) => (
            <StockRow
              key={stock.ticker}
              stock={stock}
              rank={i + 1}
              crossScanners={crossScannerMap?.[stock.ticker]?.filter(s => s !== SELF_LABEL)}
            />
          ))}
        </div>
      )}

      {/* Footer note */}
      <p className="text-[10px] text-slate-600 text-center pt-2 border-t border-slate-700/30">
        מבוסס על ravening/stock-trading-bots · MACD קנייה = MACD חוצה מתחת ל-signal (מומנטום נחלש = כניסה קונטרריאנית) · RSI קנייה &lt;40 · BB קנייה = מחיר מתחת לרצועה התחתונה
      </p>
    </div>
  );
}
