import { useState, useEffect, useMemo, useRef } from 'react';
import { Activity, Target, BarChart3, Clock, TrendingUp, TrendingDown, Zap, ExternalLink, ChevronDown, ChevronUp, Newspaper, FileText } from 'lucide-react';

// ─── Helpers ─────────────────────────────────────────────

const pct = (v) => (v ?? 0).toFixed(2);
const abs_pct = (v) => Math.abs(v ?? 0).toFixed(2);
const arrow = (v) => (v > 0 ? '▲' : v < 0 ? '▼' : '—');
const fmtVol = (v) => {
  if (!v) return '0';
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(1)}B`;
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
  return v.toString();
};
const fmtMcap = (v) => {
  if (!v) return '-';
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v}`;
};
const changeColor = (v) => v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-slate-400';
const changeBg = (v) => v > 0 ? 'bg-green-900/30 border-green-500/40' : v < 0 ? 'bg-red-900/30 border-red-500/40' : 'bg-slate-800 border-slate-600';


// ─── Trading Session Timer ──────────────────────────────

function TradingSessionBar() {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 10000);
    return () => clearInterval(timer);
  }, []);

  // Convert to ET (Eastern Time)
  const etStr = now.toLocaleString('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', hour12: false });
  const [hStr, mStr] = etStr.split(':');
  const etHour = parseInt(hStr);
  const etMin = parseInt(mStr);
  const etDecimal = etHour + etMin / 60;

  // Market sessions
  const isPremarket = etDecimal >= 4 && etDecimal < 9.5;
  const isGoldenHour = etDecimal >= 9.5 && etDecimal < 10.5;
  const isMidDay = etDecimal >= 10.5 && etDecimal < 15;
  const isPowerHour = etDecimal >= 15 && etDecimal < 16;
  const isAfterHours = etDecimal >= 16 && etDecimal < 20;
  const isMarketOpen = etDecimal >= 9.5 && etDecimal < 16;

  let session = { label: 'Market Closed', color: 'text-slate-500', bg: 'bg-slate-800', emoji: '🌙', tip: '' };
  if (isPremarket) session = { label: 'Pre-Market', color: 'text-blue-400', bg: 'bg-blue-900/30', emoji: '🌅', tip: 'Low liquidity - watch for gaps' };
  else if (isGoldenHour) session = { label: 'GOLDEN HOUR', color: 'text-yellow-400', bg: 'bg-yellow-900/40', emoji: '🔥', tip: 'Best entry window! Wait 15-30min for range to form. High volume + VWAP above = entry.' };
  else if (isMidDay) session = { label: 'Mid-Day', color: 'text-slate-400', bg: 'bg-slate-800', emoji: '⏸️', tip: 'Lower volume, choppy. Avoid aggressive entries. Wait for power hour.' };
  else if (isPowerHour) session = { label: 'POWER HOUR', color: 'text-orange-400', bg: 'bg-orange-900/40', emoji: '⚡', tip: 'Volume returns. If stock holds above VWAP into close = strength for next day.' };
  else if (isAfterHours) session = { label: 'After Hours', color: 'text-purple-400', bg: 'bg-purple-900/30', emoji: '🌆', tip: 'Low volume. Watch for earnings/news reactions.' };

  // Progress bar for market hours (9:30 to 16:00 = 6.5 hours)
  const marketProgress = isMarketOpen ? Math.min(100, ((etDecimal - 9.5) / 6.5) * 100) : 0;

  return (
    <div className={`rounded-lg border border-slate-700 ${session.bg} p-3 mb-4`}>
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-xl">{session.emoji}</span>
          <span className={`font-bold text-lg ${session.color}`}>{session.label}</span>
          {(isGoldenHour || isPowerHour) && (
            <span className="relative flex h-3 w-3">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${isGoldenHour ? 'bg-yellow-400' : 'bg-orange-400'} opacity-75`}></span>
              <span className={`relative inline-flex rounded-full h-3 w-3 ${isGoldenHour ? 'bg-yellow-500' : 'bg-orange-500'}`}></span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <Clock size={14} className="text-slate-500" />
          <span className="text-slate-400 text-sm font-mono">{etStr} ET</span>
          {isMarketOpen && (
            <span className="text-xs text-green-400 font-semibold flex items-center gap-1">
              <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
              MARKET OPEN
            </span>
          )}
        </div>
      </div>

      {/* Market progress bar */}
      {isMarketOpen && (
        <div className="w-full bg-slate-700 rounded-full h-2 mb-2">
          <div
            className="h-2 rounded-full transition-all duration-500"
            style={{
              width: `${marketProgress}%`,
              background: `linear-gradient(90deg, #22c55e 0%, #eab308 50%, #f97316 100%)`
            }}
          />
          {/* Session markers */}
          <div className="relative h-0 -mt-2">
            <div className="absolute left-0 -top-1 text-[9px] text-slate-500">9:30</div>
            <div className="absolute text-[9px] text-yellow-500 font-bold" style={{ left: '15.4%' }}>10:30</div>
            <div className="absolute text-[9px] text-orange-500 font-bold" style={{ left: '84.6%' }}>15:00</div>
            <div className="absolute right-0 -top-1 text-[9px] text-slate-500">16:00</div>
          </div>
        </div>
      )}

      {session.tip && (
        <p className="text-xs text-slate-400 mt-3 italic">{session.tip}</p>
      )}
    </div>
  );
}


// ─── VWAP Gauge ──────────────────────────────────────────

function VWAPGauge({ stock }) {
  const vwap = stock.vwap || 0;
  const price = stock.current_price || stock.price || 0;
  const position = stock.vwap_position || 'unknown';
  const distance = stock.vwap_distance_pct || 0;

  if (!vwap || !price) return null;

  const isAbove = position === 'above';
  const isBelow = position === 'below';
  const isAt = position === 'at_vwap';

  return (
    <div className={`rounded-lg border p-3 ${isAbove ? 'bg-green-900/20 border-green-500/30' : isBelow ? 'bg-red-900/20 border-red-500/30' : 'bg-yellow-900/20 border-yellow-500/30'}`}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-400 font-semibold">VWAP</span>
        <span className={`text-xs font-bold ${isAbove ? 'text-green-400' : isBelow ? 'text-red-400' : 'text-yellow-400'}`}>
          {isAbove ? '📈 ABOVE' : isBelow ? '📉 BELOW' : '⚖️ AT VWAP'}
        </span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold text-white">${vwap.toFixed(2)}</span>
        <span className={`text-sm font-semibold ${changeColor(distance)}`}>
          {distance > 0 ? '+' : ''}{distance.toFixed(2)}%
        </span>
      </div>
      {/* Visual bar */}
      <div className="mt-2 relative h-2 bg-slate-700 rounded-full overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center">
          <div className="w-0.5 h-full bg-yellow-400 z-10" />
        </div>
        <div
          className={`h-full rounded-full transition-all ${isAbove ? 'bg-green-500' : 'bg-red-500'}`}
          style={{
            width: `${Math.min(100, Math.abs(distance) * 5 + 50)}%`,
            marginLeft: isBelow ? '0' : 'auto',
            marginRight: isAbove ? '0' : 'auto',
          }}
        />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-slate-500">Below</span>
        <span className="text-[10px] text-yellow-500">VWAP</span>
        <span className="text-[10px] text-slate-500">Above</span>
      </div>
    </div>
  );
}


// ─── ATR Meter ───────────────────────────────────────────

function ATRMeter({ stock }) {
  const atr = stock.atr || 0;
  const atrPct = stock.atr_pct || 0;
  const dayHigh = stock.day_high || 0;
  const dayLow = stock.day_low || 0;
  const dayRange = dayHigh - dayLow;
  const atrUsed = atr > 0 ? (dayRange / atr * 100) : 0;

  if (!atr) return null;

  const getATRColor = () => {
    if (atrUsed >= 150) return 'text-red-400';
    if (atrUsed >= 100) return 'text-orange-400';
    if (atrUsed >= 70) return 'text-yellow-400';
    return 'text-green-400';
  };

  const getATRLabel = () => {
    if (atrUsed >= 150) return 'EXTENDED';
    if (atrUsed >= 100) return 'FULL ATR';
    if (atrUsed >= 70) return 'ACTIVE';
    return 'ROOM LEFT';
  };

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/50 p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-400 font-semibold">ATR (14)</span>
        <span className={`text-xs font-bold ${getATRColor()}`}>{getATRLabel()}</span>
      </div>
      <div className="flex items-baseline gap-2">
        <span className="text-lg font-bold text-white">${atr.toFixed(2)}</span>
        <span className="text-xs text-slate-400">({atrPct}% of price)</span>
      </div>
      {/* ATR usage bar */}
      <div className="mt-2">
        <div className="flex justify-between text-[10px] text-slate-500 mb-1">
          <span>Day Range: ${dayRange.toFixed(2)}</span>
          <span className={getATRColor()}>{atrUsed.toFixed(0)}% used</span>
        </div>
        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${
              atrUsed >= 150 ? 'bg-red-500' : atrUsed >= 100 ? 'bg-orange-500' : atrUsed >= 70 ? 'bg-yellow-500' : 'bg-green-500'
            }`}
            style={{ width: `${Math.min(100, atrUsed)}%` }}
          />
        </div>
      </div>
    </div>
  );
}


// ─── Level Display ────────────────────────────────────────

function LevelsDisplay({ stock }) {
  const price = stock.current_price || stock.price || 0;
  const support = stock.support || 0;
  const resistance = stock.resistance || 0;
  const dayHigh = stock.day_high || 0;
  const dayLow = stock.day_low || 0;
  const sma20 = stock.sma20 || 0;
  const vwap = stock.vwap || 0;

  if (!price || !support) return null;

  const range = resistance - support;
  const pricePosition = range > 0 ? ((price - support) / range * 100) : 50;

  return (
    <div className="rounded-lg border border-slate-600 bg-slate-800/50 p-3">
      <span className="text-xs text-slate-400 font-semibold">KEY LEVELS</span>
      <div className="mt-2 space-y-1">
        <div className="flex justify-between text-xs">
          <span className="text-red-400">Resistance</span>
          <span className="text-white font-mono">${resistance.toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-slate-400">Day High</span>
          <span className="text-white font-mono">${dayHigh.toFixed(2)}</span>
        </div>
        {vwap > 0 && (
          <div className="flex justify-between text-xs">
            <span className="text-yellow-400">VWAP</span>
            <span className="text-white font-mono">${vwap.toFixed(2)}</span>
          </div>
        )}
        {sma20 > 0 && (
          <div className="flex justify-between text-xs">
            <span className="text-blue-400">SMA 20</span>
            <span className="text-white font-mono">${sma20.toFixed(2)}</span>
          </div>
        )}
        <div className="flex justify-between text-xs">
          <span className="text-slate-400">Day Low</span>
          <span className="text-white font-mono">${dayLow.toFixed(2)}</span>
        </div>
        <div className="flex justify-between text-xs">
          <span className="text-green-400">Support</span>
          <span className="text-white font-mono">${support.toFixed(2)}</span>
        </div>
      </div>

      {/* Price position bar */}
      <div className="mt-2 relative h-3 bg-gradient-to-r from-green-900/50 via-slate-700 to-red-900/50 rounded-full overflow-visible">
        <div
          className="absolute -top-0.5 w-3 h-4 bg-white rounded-sm shadow-lg shadow-white/30"
          style={{ left: `${Math.max(2, Math.min(95, pricePosition))}%`, transform: 'translateX(-50%)' }}
        >
          <div className="absolute -top-4 left-1/2 -translate-x-1/2 text-[9px] text-white font-bold whitespace-nowrap">
            ${price.toFixed(2)}
          </div>
        </div>
      </div>
    </div>
  );
}


// ─── TradingView Candlestick Chart (lazy-loaded) ────────

function CandleChart({ ticker }) {
  const containerRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);

  // Lazy load: only render chart when scrolled into view
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setIsVisible(true); observer.disconnect(); } },
      { threshold: 0.1 }
    );
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!isVisible || !containerRef.current) return;
    containerRef.current.innerHTML = '';

    const widgetDiv = document.createElement('div');
    widgetDiv.className = 'tradingview-widget-container__widget';
    widgetDiv.style.height = '100%';
    widgetDiv.style.width = '100%';
    containerRef.current.appendChild(widgetDiv);

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.async = true;
    script.type = 'text/javascript';
    script.textContent = JSON.stringify({
      autosize: false,
      symbol: ticker,
      width: '100%',
      height: 350,
      interval: '5',
      timezone: 'America/New_York',
      theme: 'dark',
      style: '1',
      locale: 'he_IL',
      allow_symbol_change: false,
      hide_top_toolbar: true,
      hide_side_toolbar: true,
      save_image: false,
      calendar: false,
      studies: ['Volume@tv-basicstudies'],
      support_host: 'https://www.tradingview.com',
    });

    containerRef.current.appendChild(script);
  }, [isVisible, ticker]);

  return (
    <div
      className="tradingview-widget-container rounded-lg overflow-hidden border border-slate-700"
      ref={containerRef}
      style={{ height: 350, minHeight: 350 }}
    >
      {!isVisible && (
        <div className="flex items-center justify-center h-full bg-slate-900/50 text-slate-500 text-sm">
          Loading chart...
        </div>
      )}
    </div>
  );
}


// ─── Company Description & News ──────────────────────────

function CompanyInfo({ stock }) {
  const summary = stock.business_summary || '';
  const news = stock.news || [];

  if (!summary && news.length === 0) return null;

  const formatTime = (dateStr) => {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return '';
      return d.toLocaleDateString('he-IL', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
    } catch { return ''; }
  };

  return (
    <div className="space-y-3">
      {/* Company description */}
      {summary && (
        <div className="bg-slate-900/60 rounded-lg border border-slate-700 p-3">
          <div className="flex items-center gap-2 mb-2">
            <FileText size={14} className="text-blue-400" />
            <span className="text-xs font-bold text-slate-300">על החברה</span>
          </div>
          <p className="text-sm text-slate-300 leading-relaxed" dir="rtl">{summary}</p>
        </div>
      )}

      {/* Latest news */}
      {news.length > 0 && (
        <div className="bg-slate-900/60 rounded-lg border border-slate-700 p-3">
          <div className="flex items-center gap-2 mb-2">
            <Newspaper size={14} className="text-orange-400" />
            <span className="text-xs font-bold text-slate-300">חדשות אחרונות</span>
          </div>
          <div className="space-y-2">
            {news.map((item, i) => (
              <a
                key={i}
                href={item.link}
                target="_blank"
                rel="noopener noreferrer"
                className="block hover:bg-slate-800/50 rounded p-2 transition-colors group"
                onClick={e => e.stopPropagation()}
              >
                <div className="text-sm text-slate-200 group-hover:text-blue-300 leading-snug" dir="rtl">
                  {item.title}
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[10px] text-slate-500">{item.publisher}</span>
                  {item.pub_date && (
                    <span className="text-[10px] text-slate-600">{formatTime(item.pub_date)}</span>
                  )}
                  <ExternalLink size={10} className="text-slate-600 group-hover:text-blue-400" />
                </div>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


// ─── Stock Card ──────────────────────────────────────────

function StockCard({ stock, rank }) {
  const [expanded, setExpanded] = useState(false);

  const move = stock.move || {};
  const change = stock.change_pct || 0;
  const isUp = change > 0;
  const score = stock.screener_score || 0;

  // Market cap — use enriched value or Finviz string
  const mcapDisplay = stock.market_cap > 0
    ? fmtMcap(stock.market_cap)
    : (stock.market_cap_str && stock.market_cap_str !== '-' ? stock.market_cap_str : '');

  // Scan source badges
  const sources = stock.scan_sources || [];
  const sourceBadges = {
    'momentum_up': { label: 'Momentum', color: 'bg-green-600' },
    'momentum_down': { label: 'Drop', color: 'bg-red-600' },
    'unusual_volume': { label: 'Unusual Vol', color: 'bg-orange-600' },
  };

  // VWAP signal
  const vwapSignal = stock.vwap_position === 'above' && isUp ? 'BULLISH VWAP'
    : stock.vwap_position === 'below' && !isUp ? 'BEARISH VWAP'
    : stock.vwap_position === 'at_vwap' ? 'AT VWAP'
    : '';

  // Catalyst tags
  const tags = [];
  if (stock.rel_volume >= 3) tags.push({ label: `${stock.rel_volume}x Vol`, color: 'bg-orange-500' });
  else if (stock.rel_volume >= 2) tags.push({ label: `${stock.rel_volume}x Vol`, color: 'bg-yellow-600' });
  if (stock.above_sma20) tags.push({ label: 'Above SMA20', color: 'bg-blue-600' });
  if (stock.vwap_position === 'above' && isUp) tags.push({ label: 'Above VWAP', color: 'bg-green-600' });
  if (stock.atr_pct >= 5) tags.push({ label: `ATR ${stock.atr_pct}%`, color: 'bg-purple-600' });
  if (move.acceleration === 'increasing') tags.push({ label: 'Accelerating', color: 'bg-emerald-600' });
  if (Math.abs(move.change_5m || 0) >= 1) tags.push({ label: `5m: ${move.change_5m > 0 ? '+' : ''}${(move.change_5m || 0).toFixed(1)}%`, color: move.change_5m > 0 ? 'bg-green-700' : 'bg-red-700' });

  return (
    <div
      className={`rounded-lg border transition-all ${
        rank <= 3 ? 'border-yellow-500/40 bg-slate-800/80' : 'border-slate-700 bg-slate-800/50'
      }`}
    >
      {/* ── Header row (clickable for technical details) ── */}
      <div className="p-4 cursor-pointer hover:bg-slate-700/20 transition-colors" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-start justify-between gap-4">
          {/* Left: Rank + Ticker + Price + Market Cap */}
          <div className="flex items-start gap-3 flex-1">
            {rank <= 3 && (
              <div className={`w-8 h-8 rounded-full flex items-center justify-center font-bold text-sm shrink-0 ${
                rank === 1 ? 'bg-yellow-500 text-black' : rank === 2 ? 'bg-slate-300 text-black' : 'bg-amber-700 text-white'
              }`}>
                {rank}
              </div>
            )}
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-2xl font-bold text-white">{stock.ticker}</span>
                <span className={`text-2xl font-bold ${changeColor(change)}`}>
                  {arrow(change)} {abs_pct(change)}%
                </span>
                {stock.current_price > 0 && (
                  <span className="text-lg text-slate-300 font-mono">${stock.current_price.toFixed(2)}</span>
                )}
                {/* Market Cap - prominent badge */}
                {mcapDisplay && (
                  <span className="px-2.5 py-1 rounded-md bg-indigo-900/50 border border-indigo-500/30 text-indigo-300 text-sm font-bold">
                    {mcapDisplay}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-2 mt-1 flex-wrap">
                <span className="text-xs text-slate-400">{stock.company_name || stock.company}</span>
                {stock.full_sector && (
                  <span className="text-xs text-slate-500">| {stock.full_sector}</span>
                )}
              </div>

              {/* Tags */}
              <div className="flex flex-wrap gap-1 mt-2">
                {sources.map(src => (
                  <span key={src} className={`px-2 py-0.5 rounded text-[10px] font-bold text-white ${sourceBadges[src]?.color || 'bg-slate-600'}`}>
                    {sourceBadges[src]?.label || src}
                  </span>
                ))}
                {vwapSignal && (
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold text-white ${
                    vwapSignal.includes('BULLISH') ? 'bg-green-700' : vwapSignal.includes('BEARISH') ? 'bg-red-700' : 'bg-yellow-700'
                  }`}>
                    {vwapSignal}
                  </span>
                )}
                {tags.map((tag, i) => (
                  <span key={i} className={`px-2 py-0.5 rounded text-[10px] font-bold text-white ${tag.color}`}>
                    {tag.label}
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Right: Score + Volume + Expand */}
          <div className="flex flex-col items-end gap-1">
            {/* Score circle */}
            <div className="relative">
              <svg className="transform -rotate-90 w-16 h-16">
                <circle cx="32" cy="32" r="26" stroke="currentColor" strokeWidth="5" fill="transparent" className="text-slate-700" />
                <circle
                  cx="32" cy="32" r="26" stroke="currentColor" strokeWidth="5" fill="transparent"
                  strokeDasharray={`${2 * Math.PI * 26}`}
                  strokeDashoffset={`${2 * Math.PI * 26 * (1 - score / 100)}`}
                  className={score >= 80 ? 'text-green-400' : score >= 60 ? 'text-yellow-400' : 'text-blue-400'}
                />
              </svg>
              <div className="absolute inset-0 flex items-center justify-center">
                <span className="text-lg font-bold text-white">{score}</span>
              </div>
            </div>
            <span className="text-[10px] text-slate-500">Score</span>

            {/* Volume */}
            <div className="text-right mt-1">
              <div className="text-xs text-slate-400">Vol: {fmtVol(stock.current_volume || stock.volume)}</div>
              {stock.rel_volume > 0 && (
                <div className={`text-xs font-bold ${stock.rel_volume >= 2 ? 'text-orange-400' : stock.rel_volume >= 1.5 ? 'text-yellow-400' : 'text-slate-400'}`}>
                  {stock.rel_volume}x avg
                </div>
              )}
            </div>

            {/* Expand hint */}
            <div className="mt-1 flex items-center gap-1">
              <span className="text-[10px] text-slate-600">Technical</span>
              {expanded ? <ChevronUp size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
            </div>
          </div>
        </div>

        {/* Quick move data row */}
        {move.ticker && (
          <div className="mt-3 flex items-center gap-4 text-xs">
            <div className={`px-2 py-1 rounded border ${changeBg(move.change_5m)}`}>
              <span className="text-slate-400">5m: </span>
              <span className={`font-bold ${changeColor(move.change_5m)}`}>
                {arrow(move.change_5m)} {abs_pct(move.change_5m)}%
              </span>
            </div>
            <div className={`px-2 py-1 rounded border ${changeBg(move.change_15m)}`}>
              <span className="text-slate-400">15m: </span>
              <span className={`font-bold ${changeColor(move.change_15m)}`}>
                {arrow(move.change_15m)} {abs_pct(move.change_15m)}%
              </span>
            </div>
            {move.velocity_5m !== 0 && (
              <span className="text-slate-400">
                Vel: <span className={`font-bold ${changeColor(move.velocity_5m)}`}>{(move.velocity_5m || 0).toFixed(3)}%/min</span>
              </span>
            )}
            {move.acceleration && move.acceleration !== 'steady' && (
              <span className={`font-bold ${move.acceleration === 'increasing' ? 'text-green-400' : 'text-orange-400'}`}>
                {move.acceleration === 'increasing' ? '🚀 Accel' : '⚠️ Decel'}
              </span>
            )}
          </div>
        )}
      </div>

      {/* ── Always visible: Candlestick Chart ── */}
      <div className="px-4 pb-3">
        <CandleChart ticker={stock.ticker} />
      </div>

      {/* ── Always visible: Company Info + News (Hebrew) ── */}
      <div className="px-4 pb-3">
        <CompanyInfo stock={stock} />
      </div>

      {/* ── Action links (always visible) ── */}
      <div className="px-4 pb-3 flex items-center gap-2">
        <a
          href={`https://finviz.com/quote.ashx?t=${stock.ticker}`}
          target="_blank"
          rel="noopener noreferrer"
          className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs flex items-center gap-1"
        >
          <BarChart3 size={12} /> Finviz
        </a>
        <a
          href={`https://www.tradingview.com/chart/?symbol=${stock.ticker}`}
          target="_blank"
          rel="noopener noreferrer"
          className="px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white rounded text-xs flex items-center gap-1"
        >
          <Activity size={12} /> TradingView
        </a>
        <a
          href={`https://finance.yahoo.com/quote/${stock.ticker}`}
          target="_blank"
          rel="noopener noreferrer"
          className="px-3 py-1 bg-slate-600 hover:bg-slate-500 text-white rounded text-xs flex items-center gap-1"
        >
          <ExternalLink size={12} /> Yahoo
        </a>
      </div>

      {/* ── Expandable: Technical Details ── */}
      {expanded && (
        <div className="border-t border-slate-700 p-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
            <VWAPGauge stock={stock} />
            <ATRMeter stock={stock} />
            <LevelsDisplay stock={stock} />
          </div>

          {/* Day structure row */}
          <div className="grid grid-cols-4 gap-2">
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <span className="text-[10px] text-slate-500 block">Open</span>
              <span className="text-sm font-bold text-white">${(stock.day_open || 0).toFixed(2)}</span>
            </div>
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <span className="text-[10px] text-slate-500 block">High</span>
              <span className="text-sm font-bold text-green-400">${(stock.day_high || 0).toFixed(2)}</span>
            </div>
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <span className="text-[10px] text-slate-500 block">Low</span>
              <span className="text-sm font-bold text-red-400">${(stock.day_low || 0).toFixed(2)}</span>
            </div>
            <div className="bg-slate-900/50 rounded p-2 text-center">
              <span className="text-[10px] text-slate-500 block">Prev Close</span>
              <span className="text-sm font-bold text-white">${(stock.prev_close || 0).toFixed(2)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


// ─── Filter Bar ──────────────────────────────────────────

function FilterBar({ filters, setFilters, stockCount }) {
  return (
    <div className="flex items-center gap-3 flex-wrap mb-4 bg-slate-800/50 border border-slate-700 rounded-lg p-3">
      <span className="text-xs text-slate-400 font-semibold">FILTERS:</span>

      {/* Direction */}
      <select
        value={filters.direction}
        onChange={e => setFilters(f => ({ ...f, direction: e.target.value }))}
        className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded"
      >
        <option value="all">All Directions</option>
        <option value="up">Gainers Only</option>
        <option value="down">Drops Only</option>
      </select>

      {/* VWAP */}
      <select
        value={filters.vwap}
        onChange={e => setFilters(f => ({ ...f, vwap: e.target.value }))}
        className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded"
      >
        <option value="all">Any VWAP</option>
        <option value="above">Above VWAP</option>
        <option value="below">Below VWAP</option>
        <option value="at">At VWAP</option>
      </select>

      {/* Min RelVol */}
      <select
        value={filters.minRelVol}
        onChange={e => setFilters(f => ({ ...f, minRelVol: parseFloat(e.target.value) }))}
        className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded"
      >
        <option value={0}>Any Volume</option>
        <option value={1.5}>RelVol 1.5x+</option>
        <option value={2}>RelVol 2x+</option>
        <option value={3}>RelVol 3x+</option>
        <option value={5}>RelVol 5x+</option>
      </select>

      {/* Min Change */}
      <select
        value={filters.minChange}
        onChange={e => setFilters(f => ({ ...f, minChange: parseFloat(e.target.value) }))}
        className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded"
      >
        <option value={0}>Any Change</option>
        <option value={5}>5%+ Move</option>
        <option value={10}>10%+ Move</option>
        <option value={15}>15%+ Move</option>
        <option value={20}>20%+ Move</option>
      </select>

      {/* Market Cap */}
      <select
        value={filters.marketCap}
        onChange={e => setFilters(f => ({ ...f, marketCap: e.target.value }))}
        className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded"
      >
        <option value="any">Market Cap: Any</option>
        <option value="mega">Mega ($200B+)</option>
        <option value="large">Large ($10B–$200B)</option>
        <option value="mid">Mid ($2B–$10B)</option>
        <option value="small">Small ($300M–$2B)</option>
        <option value="micro">Micro ($50M–$300M)</option>
        <option value="nano">Nano (under $50M)</option>
        <option disabled>──────────</option>
        <option value="+large">+Large (over $10B)</option>
        <option value="+mid">+Mid (over $2B)</option>
        <option value="+small">+Small (over $300M)</option>
        <option value="+micro">+Micro (over $50M)</option>
        <option disabled>──────────</option>
        <option value="-large">-Large (under $200B)</option>
        <option value="-mid">-Mid (under $10B)</option>
        <option value="-small">-Small (under $2B)</option>
        <option value="-micro">-Micro (under $300M)</option>
      </select>

      {/* Sort */}
      <select
        value={filters.sortBy}
        onChange={e => setFilters(f => ({ ...f, sortBy: e.target.value }))}
        className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded"
      >
        <option value="score">Sort: Score</option>
        <option value="change">Sort: % Change</option>
        <option value="volume">Sort: Rel Volume</option>
        <option value="5m">Sort: 5m Move</option>
      </select>

      <div className="flex-1" />
      <span className="text-xs text-slate-500">{stockCount} stocks</span>
    </div>
  );
}


// ─── Screener Legend ─────────────────────────────────────

function ScreenerLegend() {
  return (
    <div className="bg-slate-800/30 border border-slate-700 rounded-lg p-3 mb-4">
      <div className="flex items-center gap-2 mb-2">
        <Target size={14} className="text-yellow-400" />
        <span className="text-xs font-bold text-slate-300">SCREENER CRITERIA</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-[10px]">
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-green-500" />
          <span className="text-slate-400">Avg Volume &gt; 500K</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-orange-500" />
          <span className="text-slate-400">Rel Volume &gt; 1.5x</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-blue-500" />
          <span className="text-slate-400">Price &gt; $10</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-yellow-500" />
          <span className="text-slate-400">Change &gt; 5%</span>
        </div>
        <div className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-full bg-purple-500" />
          <span className="text-slate-400">Above SMA20</span>
        </div>
      </div>
    </div>
  );
}


// ─── Main Component ──────────────────────────────────────

export default function VWAPMomentumScanner({ stocks, loading }) {
  const [filters, setFilters] = useState({
    direction: 'all',
    vwap: 'all',
    minRelVol: 0,
    minChange: 0,
    sortBy: 'score',
    marketCap: 'any',
  });

  // Apply filters
  const filteredStocks = useMemo(() => {
    let result = [...(stocks || [])];

    // Direction filter
    if (filters.direction === 'up') result = result.filter(s => (s.change_pct || 0) > 0);
    if (filters.direction === 'down') result = result.filter(s => (s.change_pct || 0) < 0);

    // VWAP filter
    if (filters.vwap !== 'all') result = result.filter(s => s.vwap_position === filters.vwap);

    // Min relative volume
    if (filters.minRelVol > 0) result = result.filter(s => (s.rel_volume || 0) >= filters.minRelVol);

    // Min change
    if (filters.minChange > 0) result = result.filter(s => Math.abs(s.change_pct || 0) >= filters.minChange);

    // Market Cap filter
    const mc = s => s.market_cap || 0;
    if (filters.marketCap === 'mega')       result = result.filter(s => mc(s) >= 200e9);
    else if (filters.marketCap === 'large') result = result.filter(s => mc(s) >= 10e9 && mc(s) < 200e9);
    else if (filters.marketCap === 'mid')   result = result.filter(s => mc(s) >= 2e9  && mc(s) < 10e9);
    else if (filters.marketCap === 'small') result = result.filter(s => mc(s) >= 300e6 && mc(s) < 2e9);
    else if (filters.marketCap === 'micro') result = result.filter(s => mc(s) >= 50e6  && mc(s) < 300e6);
    else if (filters.marketCap === 'nano')  result = result.filter(s => mc(s) > 0 && mc(s) < 50e6);
    else if (filters.marketCap === '+large') result = result.filter(s => mc(s) >= 10e9);
    else if (filters.marketCap === '+mid')   result = result.filter(s => mc(s) >= 2e9);
    else if (filters.marketCap === '+small') result = result.filter(s => mc(s) >= 300e6);
    else if (filters.marketCap === '+micro') result = result.filter(s => mc(s) >= 50e6);
    else if (filters.marketCap === '-large') result = result.filter(s => mc(s) < 200e9);
    else if (filters.marketCap === '-mid')   result = result.filter(s => mc(s) < 10e9);
    else if (filters.marketCap === '-small') result = result.filter(s => mc(s) < 2e9);
    else if (filters.marketCap === '-micro') result = result.filter(s => mc(s) < 300e6);

    // Sort
    if (filters.sortBy === 'change') result.sort((a, b) => Math.abs(b.change_pct || 0) - Math.abs(a.change_pct || 0));
    else if (filters.sortBy === 'volume') result.sort((a, b) => (b.rel_volume || 0) - (a.rel_volume || 0));
    else if (filters.sortBy === '5m') result.sort((a, b) => Math.abs(b.move?.change_5m || 0) - Math.abs(a.move?.change_5m || 0));
    else result.sort((a, b) => (b.screener_score || 0) - (a.screener_score || 0));

    return result;
  }, [stocks, filters]);

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-3">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-yellow-500"></div>
        <span className="text-slate-400 text-sm">Scanning Finviz with momentum filters...</span>
        <span className="text-slate-500 text-xs">AvgVol&gt;500K | RelVol&gt;1.5 | Price&gt;$10 | Change&gt;5% | Above SMA20</span>
      </div>
    );
  }

  if (!stocks || stocks.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        <Activity size={48} className="mx-auto mb-4 opacity-50" />
        <p>No momentum stocks matching screener criteria</p>
        <p className="text-sm mt-2 text-slate-500">Criteria: AvgVol&gt;500K, RelVol&gt;1.5x, Price&gt;$10, Change&gt;5%, Above SMA20</p>
      </div>
    );
  }

  return (
    <div>
      {/* Trading Session Timer */}
      <TradingSessionBar />

      {/* Screener Legend */}
      <ScreenerLegend />

      {/* Filters */}
      <FilterBar filters={filters} setFilters={setFilters} stockCount={filteredStocks.length} />

      {/* Stock list */}
      <div className="space-y-3">
        {filteredStocks.map((stock, idx) => (
          <StockCard key={stock.ticker} stock={stock} rank={idx + 1} />
        ))}
      </div>
    </div>
  );
}
