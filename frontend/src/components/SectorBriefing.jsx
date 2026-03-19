import { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import {
  RefreshCw, TrendingUp, TrendingDown, AlertCircle, Newspaper,
  ChevronDown, ChevronUp, Zap, Shield, Activity, BarChart3,
  ArrowUpRight, ArrowDownRight, Minus,
} from 'lucide-react';

const api = axios.create({ baseURL: '/api' });

// ── helpers ────────────────────────────────────────────────────────────────────

function chgColor(pct) {
  if (pct == null) return 'text-slate-500';
  if (pct > 3)   return 'text-emerald-300';
  if (pct > 1)   return 'text-emerald-400';
  if (pct > 0)   return 'text-emerald-400/80';
  if (pct < -3)  return 'text-red-300';
  if (pct < -1)  return 'text-red-400';
  if (pct < 0)   return 'text-red-400/80';
  return 'text-slate-400';
}

function chgBg(pct) {
  if (pct > 2)   return 'bg-emerald-950/60 border-emerald-700/40';
  if (pct > 0)   return 'bg-emerald-950/30 border-emerald-800/30';
  if (pct < -2)  return 'bg-red-950/60 border-red-700/40';
  if (pct < 0)   return 'bg-red-950/30 border-red-800/30';
  return 'bg-slate-800/40 border-slate-700/30';
}

function heatColor(pct) {
  if (pct == null) return 'bg-slate-800';
  if (pct > 3)   return 'bg-emerald-600';
  if (pct > 2)   return 'bg-emerald-700';
  if (pct > 1)   return 'bg-emerald-800';
  if (pct > 0.3) return 'bg-emerald-900';
  if (pct > -0.3) return 'bg-slate-700';
  if (pct > -1)  return 'bg-red-900';
  if (pct > -2)  return 'bg-red-800';
  if (pct > -3)  return 'bg-red-700';
  return 'bg-red-600';
}

function fmtChg(pct) {
  if (pct == null) return '—';
  return `${pct >= 0 ? '+' : ''}${pct?.toFixed(2)}%`;
}

function fmtVol(n) {
  if (!n) return '';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000)     return `${(n / 1_000).toFixed(0)}K`;
  return `${n}`;
}

function fmtTime(iso) {
  if (!iso) return '';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' });
  } catch { return ''; }
}

const TF_LABELS = { d1: '1D', w1: '1W', m1: '1M', m3: '3M' };

// ── Sparkline SVG ──────────────────────────────────────────────────────────────

function Sparkline({ data, width = 80, height = 28, color }) {
  if (!data || data.length < 2) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const points = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width;
    const y = height - ((v - min) / range) * (height - 2) - 1;
    return `${x},${y}`;
  }).join(' ');

  const isUp = data[data.length - 1] >= data[0];
  const strokeColor = color || (isUp ? '#34d399' : '#f87171');
  const fillId = `sparkFill-${Math.random().toString(36).slice(2, 8)}`;

  return (
    <svg width={width} height={height} className="shrink-0">
      <defs>
        <linearGradient id={fillId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity="0.2" />
          <stop offset="100%" stopColor={strokeColor} stopOpacity="0" />
        </linearGradient>
      </defs>
      <polygon
        points={`0,${height} ${points} ${width},${height}`}
        fill={`url(#${fillId})`}
      />
      <polyline
        points={points}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// ── Momentum Score Gauge ────────────────────────────────────────────────────────

function MomentumGauge({ score, size = 32 }) {
  const r = (size - 4) / 2;
  const circumference = 2 * Math.PI * r;
  const dashoffset = circumference - (score / 100) * circumference;
  const color = score >= 65 ? '#34d399' : score >= 40 ? '#fbbf24' : '#f87171';

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="#334155" strokeWidth="3" />
        <circle
          cx={size/2} cy={size/2} r={r}
          fill="none"
          stroke={color}
          strokeWidth="3"
          strokeDasharray={circumference}
          strokeDashoffset={dashoffset}
          strokeLinecap="round"
        />
      </svg>
      <span className="absolute text-[9px] font-bold" style={{ color }}>{score}</span>
    </div>
  );
}

// ── Volume Ratio Badge ──────────────────────────────────────────────────────────

function VolumeBadge({ ratio }) {
  if (!ratio || ratio < 0.5) return null;
  const color = ratio >= 2 ? 'text-amber-300 bg-amber-950/60' :
                ratio >= 1.3 ? 'text-amber-400/80 bg-amber-950/40' :
                'text-slate-400 bg-slate-800/40';
  return (
    <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium ${color}`}>
      Vol {ratio.toFixed(1)}x
    </span>
  );
}

// ── Macro Indicators Strip ───────────────────────────────────────────────────────

function MacroStrip({ macro }) {
  if (!macro?.indicators?.length) return null;

  const riskColors = {
    high: 'bg-red-950/60 border-red-600/50 text-red-300',
    elevated: 'bg-amber-950/50 border-amber-700/40 text-amber-300',
    normal: 'bg-slate-800/50 border-slate-700/40 text-slate-400',
  };

  const vixLevelColors = {
    extreme: 'text-red-300 bg-red-900/60',
    high: 'text-red-400 bg-red-950/50',
    elevated: 'text-amber-400 bg-amber-950/50',
    normal: 'text-emerald-400 bg-emerald-950/50',
    low: 'text-blue-400 bg-blue-950/50',
  };

  const risk = macro.risk || {};
  const vix = macro.vix_level;

  return (
    <div className="space-y-2">
      {/* Risk Alert Banner */}
      {risk.level !== 'normal' && (
        <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border ${riskColors[risk.level] || riskColors.normal}`}>
          <AlertCircle size={14} className="shrink-0" />
          <span className="text-xs font-medium">{risk.label}</span>
          {risk.signals?.length > 0 && (
            <div className="flex gap-1.5 mr-auto">
              {risk.signals.map((s, i) => (
                <span key={i} className="text-[9px] bg-black/20 rounded px-1.5 py-0.5">{s}</span>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Indicator Cards */}
      <div className="flex gap-2 overflow-x-auto pb-1">
        {macro.indicators.map(ind => (
          <div key={ind.ticker}
            className={`shrink-0 rounded-xl border px-3 py-2 min-w-[110px]
              ${ind.type === 'fear' && vix
                ? `border-slate-700/40 ${vixLevelColors[vix.level] || 'bg-slate-800/40'}`
                : chgBg(ind.type === 'fear' ? -ind.change_pct : ind.change_pct)
              }`}
          >
            <div className="flex items-center gap-1.5 mb-0.5">
              <span className="text-sm">{ind.icon}</span>
              <span className="text-[10px] text-slate-400 font-medium">{ind.label}</span>
            </div>
            <div className="flex items-baseline gap-1.5">
              <span className="text-sm font-bold text-white">
                {ind.ticker === '^TNX' ? `${ind.price.toFixed(2)}%` : `$${ind.price.toLocaleString()}`}
              </span>
              <span className={`text-xs font-bold ${chgColor(ind.type === 'fear' ? -ind.change_pct : ind.change_pct)}`}>
                {fmtChg(ind.change_pct)}
              </span>
            </div>
            {ind.w1_change != null && (
              <div className="text-[9px] text-slate-500 mt-0.5">
                שבועי: <span className={chgColor(ind.type === 'fear' ? -ind.w1_change : ind.w1_change)}>{fmtChg(ind.w1_change)}</span>
              </div>
            )}
            {/* VIX level badge */}
            {ind.type === 'fear' && vix && (
              <div className="text-[9px] font-medium mt-1">{vix.description}</div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Market News Feed ────────────────────────────────────────────────────────────

function MarketNewsFeed({ news }) {
  const [expanded, setExpanded] = useState(false);
  if (!news?.length) return null;

  const shown = expanded ? news : news.slice(0, 3);

  return (
    <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl overflow-hidden">
      <div className="px-4 py-2.5 border-b border-slate-700/40 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Newspaper size={14} className="text-blue-400" />
          <h3 className="text-sm font-semibold text-blue-300">חדשות שוק קריטיות</h3>
        </div>
        {news.length > 3 && (
          <button onClick={() => setExpanded(!expanded)} className="text-[10px] text-slate-500 hover:text-slate-300">
            {expanded ? 'הצג פחות' : `עוד ${news.length - 3}`}
          </button>
        )}
      </div>
      <div className="divide-y divide-slate-700/20">
        {shown.map((n, i) => (
          <div key={i} className="px-4 py-2 hover:bg-slate-800/20 transition-colors">
            <p className="text-[12px] text-slate-200 leading-snug">{n.title}</p>
            <div className="flex gap-2 mt-0.5">
              {n.ticker && <span className="text-[9px] text-blue-400/70 font-medium">{n.ticker}</span>}
              {n.source && <span className="text-[9px] text-slate-600">{n.source}</span>}
              {n.pub_date && <span className="text-[9px] text-slate-600">{fmtTime(n.pub_date)}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Sector Impact Badges ────────────────────────────────────────────────────────

function ImpactBadges({ impacts }) {
  if (!impacts?.length) return null;
  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {impacts.map((imp, i) => (
        <span key={i} className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium inline-flex items-center gap-0.5
          ${imp.impact === 'positive'
            ? 'text-emerald-300 bg-emerald-950/50'
            : 'text-red-300 bg-red-950/50'
          }`}
          title={imp.explanation}
        >
          {imp.indicator_icon} {imp.indicator} {imp.impact === 'positive' ? '+' : '-'}
        </span>
      ))}
    </div>
  );
}

// ── Rotation Signal ─────────────────────────────────────────────────────────────

function RotationSignal({ rotation }) {
  if (!rotation) return null;

  const configs = {
    risk_on:      { icon: TrendingUp,   color: 'text-emerald-400', bg: 'bg-emerald-950/50 border-emerald-700/40' },
    risk_on_mild: { icon: ArrowUpRight, color: 'text-emerald-400/70', bg: 'bg-emerald-950/30 border-emerald-800/30' },
    risk_off:     { icon: TrendingDown, color: 'text-red-400', bg: 'bg-red-950/50 border-red-700/40' },
    risk_off_mild:{ icon: ArrowDownRight,color:'text-red-400/70', bg: 'bg-red-950/30 border-red-800/30' },
    neutral:      { icon: Minus,        color: 'text-slate-400', bg: 'bg-slate-800/50 border-slate-700/40' },
  };
  const cfg = configs[rotation.signal] || configs.neutral;
  const Icon = cfg.icon;

  return (
    <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border ${cfg.bg}`}>
      <Icon size={16} className={cfg.color} />
      <div>
        <div className={`text-xs font-semibold ${cfg.color}`}>{rotation.label}</div>
        <div className="flex gap-3 text-[10px] text-slate-500 mt-0.5">
          <span>צמיחה: <span className={chgColor(rotation.growth_avg)}>{fmtChg(rotation.growth_avg)}</span></span>
          <span>הגנה: <span className={chgColor(rotation.defensive_avg)}>{fmtChg(rotation.defensive_avg)}</span></span>
          <span>מחזורי: <span className={chgColor(rotation.cyclical_avg)}>{fmtChg(rotation.cyclical_avg)}</span></span>
        </div>
      </div>
    </div>
  );
}

// ── Market Pulse Bar ────────────────────────────────────────────────────────────

function MarketPulse({ pulse }) {
  if (!pulse) return null;

  const regimeColors = {
    strong_bull: 'text-emerald-300',
    bull: 'text-emerald-400',
    strong_bear: 'text-red-300',
    bear: 'text-red-400',
    divergent: 'text-amber-400',
    mixed: 'text-slate-400',
  };

  return (
    <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-4">
      <div className="flex flex-wrap items-center gap-4 justify-between">
        {/* SPY */}
        {pulse.spy && (
          <div className="flex items-center gap-2">
            <span className="text-xs text-slate-500 font-medium">S&P 500</span>
            <span className="text-sm font-bold text-white">${pulse.spy.price}</span>
            <div className="flex gap-1.5">
              {['w1', 'm1', 'm3'].map(tf => pulse.spy[tf] != null && (
                <span key={tf} className="text-[10px]">
                  <span className="text-slate-600">{TF_LABELS[tf]}</span>
                  <span className={`ml-0.5 ${chgColor(pulse.spy[tf])}`}>{fmtChg(pulse.spy[tf])}</span>
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Regime */}
        <div className="flex items-center gap-2">
          <Activity size={14} className={regimeColors[pulse.regime] || 'text-slate-400'} />
          <span className={`text-xs font-medium ${regimeColors[pulse.regime] || 'text-slate-400'}`}>
            {pulse.regime_label}
          </span>
        </div>

        {/* Breadth */}
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-emerald-500" />
            <span className="text-xs text-emerald-400 font-bold">{pulse.up_sectors}</span>
          </div>
          <div className="flex items-center gap-1">
            <div className="w-2 h-2 rounded-full bg-red-500" />
            <span className="text-xs text-red-400 font-bold">{pulse.down_sectors}</span>
          </div>
          {pulse.flat_sectors > 0 && (
            <div className="flex items-center gap-1">
              <div className="w-2 h-2 rounded-full bg-slate-500" />
              <span className="text-xs text-slate-400">{pulse.flat_sectors}</span>
            </div>
          )}
          <span className="text-[10px] text-slate-600">|</span>
          <span className="text-xs text-slate-400">ממוצע: <span className={chgColor(pulse.avg_change)}>{fmtChg(pulse.avg_change)}</span></span>
        </div>
      </div>
    </div>
  );
}

// ── Heatmap Tile ────────────────────────────────────────────────────────────────

function HeatmapTile({ s, tf, isExpanded, onToggle }) {
  const pct = tf === 'd1' ? s.change_pct : s[tf];
  return (
    <button
      onClick={onToggle}
      className={`relative overflow-hidden rounded-xl border transition-all duration-200
        ${isExpanded ? 'ring-2 ring-blue-500/50 border-blue-600/40' : 'border-slate-700/40 hover:border-slate-600/60'}
        ${heatColor(pct)} p-3 text-right w-full`}
    >
      <div className="flex items-start justify-between gap-1">
        <div className="flex items-center gap-1.5">
          <span className="text-base">{s.icon}</span>
          <MomentumGauge score={s.momentum_score} size={28} />
        </div>
        <div className="text-left min-w-0">
          <div className="text-[11px] text-white/90 font-semibold truncate">{s.name}</div>
          <div className={`text-lg font-black leading-tight ${chgColor(pct)}`}>
            {fmtChg(pct)}
          </div>
        </div>
      </div>

      {/* Sparkline */}
      {s.sparkline?.length > 1 && (
        <div className="mt-1.5 -mx-1">
          <Sparkline data={s.sparkline} width={120} height={24} />
        </div>
      )}

      {/* Multi-timeframe quick view */}
      <div className="flex gap-1.5 mt-1.5 flex-wrap">
        {tf !== 'd1' ? null : ['w1', 'm1', 'm3'].map(t => s[t] != null && (
          <span key={t} className="text-[9px] bg-black/30 rounded px-1 py-0.5">
            <span className="text-slate-500">{TF_LABELS[t]}</span>
            <span className={`ml-0.5 ${chgColor(s[t])}`}>{fmtChg(s[t])}</span>
          </span>
        ))}
        {tf !== 'd1' && s.change_pct != null && (
          <span className="text-[9px] bg-black/30 rounded px-1 py-0.5">
            <span className="text-slate-500">1D</span>
            <span className={`ml-0.5 ${chgColor(s.change_pct)}`}>{fmtChg(s.change_pct)}</span>
          </span>
        )}
      </div>

      {/* Macro impact badges */}
      <ImpactBadges impacts={s.impacts} />

      {/* Hot industry hint */}
      {s.hot_industry && (
        <div className="text-[9px] text-amber-400/70 mt-1 truncate">
          {s.hot_industry.name}
        </div>
      )}

      {/* Bottom: ETF + Volume */}
      <div className="flex items-center justify-between mt-1">
        <span className="text-[10px] text-slate-500">{s.etf} ${s.price}</span>
        <div className="flex items-center gap-1">
          <VolumeBadge ratio={s.volume_ratio} />
        </div>
      </div>

      {/* Expand indicator */}
      <div className="absolute top-1 left-1">
        {isExpanded
          ? <ChevronUp size={12} className="text-blue-400" />
          : <ChevronDown size={12} className="text-slate-600" />
        }
      </div>
    </button>
  );
}

// ── Expanded Sector Detail ──────────────────────────────────────────────────────

function SectorDetail({ sector, stocks, isLoadingStocks, onLoadStocks }) {
  return (
    <div className="bg-slate-900/80 border border-blue-700/30 rounded-2xl overflow-hidden animate-in fade-in duration-300">
      {/* Header */}
      <div className="px-4 py-3 border-b border-slate-700/40 bg-slate-800/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-lg">{sector.icon}</span>
            <div>
              <h3 className="text-sm font-bold text-white">{sector.name}</h3>
              <div className="flex gap-3 mt-0.5">
                {Object.entries(TF_LABELS).map(([key, label]) => {
                  const val = key === 'd1' ? sector.change_pct : sector[key];
                  return val != null && (
                    <span key={key} className="text-[10px]">
                      <span className="text-slate-500">{label}</span>
                      <span className={`ml-0.5 font-bold ${chgColor(val)}`}>{fmtChg(val)}</span>
                    </span>
                  );
                })}
              </div>
            </div>
          </div>
          <MomentumGauge score={sector.momentum_score} size={36} />
        </div>

        {/* Top Movers (actual market movers) */}
        {sector.top_movers?.length > 0 && (
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <span className="text-[10px] text-amber-400 font-medium">מניות שזזות:</span>
            {sector.top_movers.slice(0, 5).map(m => (
              <span key={m.ticker} className="text-xs bg-slate-800/60 rounded-lg px-2 py-0.5">
                <span className="text-white font-bold">{m.ticker}</span>
                <span className={`ml-1 font-bold ${chgColor(m.change_pct)}`}>{fmtChg(m.change_pct)}</span>
                {m.industry && (
                  <span className="text-[9px] text-slate-600 mr-1">{m.industry}</span>
                )}
              </span>
            ))}
          </div>
        )}

        {/* Hot Industry */}
        {sector.hot_industry && (
          <div className="mt-2 bg-amber-950/30 border border-amber-800/30 rounded-lg px-3 py-1.5">
            <div className="flex items-center gap-2 flex-wrap">
              <Zap size={12} className="text-amber-400 shrink-0" />
              <span className="text-[11px] font-semibold text-amber-300">
                תת-סקטור חם: {sector.hot_industry.name}
              </span>
              <span className={`text-[10px] font-bold ${chgColor(sector.hot_industry.avg_change)}`}>
                ממוצע {fmtChg(sector.hot_industry.avg_change)}
              </span>
              <span className="text-[9px] text-slate-500">
                ({sector.hot_industry.count} מניות)
              </span>
            </div>
            {sector.hot_industry.tickers?.length > 0 && (
              <div className="flex gap-1.5 mt-1">
                {sector.hot_industry.tickers.map(t => (
                  <span key={t} className="text-[10px] text-amber-400/80 bg-amber-950/40 rounded px-1.5 py-0.5">{t}</span>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ETF Holdings (weights) */}
        {sector.holdings?.length > 0 && (
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <span className="text-[10px] text-slate-500">משקולות ETF:</span>
            {sector.holdings.map(d => (
              <span key={d.ticker} className="text-xs bg-slate-800/40 rounded-lg px-2 py-0.5">
                <span className="text-slate-400 font-medium">{d.ticker}</span>
                <span className={`ml-1 ${chgColor(d.change_pct)}`}>{fmtChg(d.change_pct)}</span>
              </span>
            ))}
          </div>
        )}

        {/* Macro-driven impacts */}
        {sector.impacts?.length > 0 && (
          <div className="mt-2">
            <span className="text-[10px] text-slate-500 block mb-1">השפעות מאקרו:</span>
            <div className="space-y-1">
              {sector.impacts.map((imp, i) => (
                <div key={i} className={`flex items-center gap-2 text-[11px] px-2 py-1 rounded-lg
                  ${imp.impact === 'positive' ? 'bg-emerald-950/40 text-emerald-300' : 'bg-red-950/40 text-red-300'}`}>
                  <span>{imp.indicator_icon}</span>
                  <span>{imp.explanation}</span>
                  <span className="text-[9px] opacity-60 mr-auto">{fmtChg(imp.change_pct)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* News */}
      {sector.news?.length > 0 && (
        <div className="px-4 py-2.5 border-b border-slate-700/30 bg-slate-800/20">
          <div className="flex items-center gap-1.5 mb-1.5">
            <Newspaper size={12} className="text-blue-400" />
            <span className="text-[10px] font-medium text-blue-300">חדשות</span>
          </div>
          <div className="space-y-1">
            {sector.news.map((n, i) => (
              <div key={i} className="flex items-start gap-2">
                <span className="text-blue-400/50 mt-0.5 shrink-0 text-[8px]">&#9679;</span>
                <div className="min-w-0">
                  <p className="text-[11px] text-slate-300 leading-snug">{n.title}</p>
                  <div className="flex gap-2 mt-0.5">
                    {n.ticker && <span className="text-[9px] text-slate-500 font-medium">{n.ticker}</span>}
                    {n.source && <span className="text-[9px] text-slate-600">{n.source}</span>}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Stocks Grid */}
      <div className="p-3">
        {isLoadingStocks ? (
          <div className="flex items-center justify-center py-6">
            <RefreshCw size={14} className="animate-spin text-slate-500" />
            <span className="text-xs text-slate-500 mr-2">טוען מניות...</span>
          </div>
        ) : stocks && stocks.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {stocks.map(s => (
              <div key={s.ticker} className="bg-slate-800/50 border border-slate-700/30 rounded-lg p-2.5
                hover:border-slate-600/50 transition-colors">
                <div className="flex justify-between items-start mb-0.5">
                  <div className="min-w-0 flex-1">
                    <span className="text-sm font-bold text-white">{s.ticker}</span>
                    {s.company && (
                      <span className="text-[10px] text-slate-500 mr-1.5 truncate max-w-[100px] inline-block align-bottom">
                        {s.company}
                      </span>
                    )}
                  </div>
                  <span className={`text-sm font-bold mr-1 shrink-0 ${chgColor(s.change_pct)}`}>
                    {fmtChg(s.change_pct)}
                  </span>
                </div>
                <div className="flex flex-wrap gap-x-2 gap-y-0 text-[10px] text-slate-500">
                  <span>${s.price?.toFixed(2)}</span>
                  {s.market_cap && <span>{s.market_cap}</span>}
                  {s.volume > 0 && <span>Vol {fmtVol(s.volume)}</span>}
                  {s.rel_volume > 0.1 && (
                    <span className={s.rel_volume >= 2 ? 'text-amber-400' : ''}>
                      RV {s.rel_volume?.toFixed(1)}x
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-4">
            <button
              onClick={onLoadStocks}
              className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
            >
              טען מניות בסקטור
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Insider Row ─────────────────────────────────────────────────────────────────

function insiderSignal(chg) {
  if (chg == null) return null;
  if (chg >= 5)  return { text: 'המניה ממריאה', color: 'text-emerald-400' };
  if (chg >= 2)  return { text: 'עלייה חזקה', color: 'text-emerald-300' };
  if (chg > 0)   return { text: 'עלייה', color: 'text-emerald-300/70' };
  if (chg <= -5) return { text: 'ירידה חדה', color: 'text-red-400' };
  if (chg < -2)  return { text: 'ירידה', color: 'text-red-300' };
  if (chg < 0)   return { text: 'ירידה קלה', color: 'text-red-300/70' };
  return { text: 'יציבה', color: 'text-slate-400' };
}

function InsiderRow({ t }) {
  const sig = insiderSignal(t.change_pct);
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 border-b border-slate-700/30 last:border-0
      hover:bg-slate-800/30 transition-colors">
      <div className="w-20 shrink-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-bold text-emerald-400">{t.ticker}</span>
          {t.change_pct != null && (
            <span className={`text-xs font-bold ${chgColor(t.change_pct)}`}>
              {fmtChg(t.change_pct)}
            </span>
          )}
        </div>
        {sig && (
          <div className={`text-[10px] ${sig.color}`}>{sig.text}</div>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-xs text-slate-200 truncate">{t.insider || t.company || '—'}</div>
        <div className="text-[10px] text-slate-500 truncate">{t.title || ''}</div>
      </div>
      <div className="text-left shrink-0">
        {t.value && <div className="text-xs font-medium text-amber-400">{t.value}</div>}
        {t.date && <div className="text-[10px] text-slate-500">{t.date}</div>}
      </div>
    </div>
  );
}

// ── Group Header ────────────────────────────────────────────────────────────────

function GroupHeader({ group }) {
  const configs = {
    growth:    { label: 'צמיחה',   icon: Zap,      color: 'text-purple-400' },
    defensive: { label: 'הגנתי',   icon: Shield,    color: 'text-blue-400' },
    cyclical:  { label: 'מחזורי',  icon: Activity,  color: 'text-amber-400' },
    other:     { label: 'אחר',     icon: BarChart3,  color: 'text-slate-400' },
  };
  const cfg = configs[group] || configs.other;
  const Icon = cfg.icon;
  return (
    <div className="flex items-center gap-1.5 px-1 py-1">
      <Icon size={12} className={cfg.color} />
      <span className={`text-[10px] font-semibold uppercase tracking-wider ${cfg.color}`}>{cfg.label}</span>
    </div>
  );
}

// ── main component ─────────────────────────────────────────────────────────────

export default function SectorBriefing() {
  const [forceKey, setForceKey] = useState(0);
  const [expandedSector, setExpandedSector] = useState(null);
  const [sectorStocksMap, setSectorStocksMap] = useState({}); // {filter: stocks[]}
  const [loadingFilter, setLoadingFilter] = useState(null);
  const [timeframe, setTimeframe] = useState('d1');
  const [viewMode, setViewMode] = useState('heatmap'); // heatmap | list

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['sectorBriefing', forceKey],
    queryFn: async () => {
      const r = await api.get('/briefing/sector', {
        params: forceKey > 0 ? { force: true } : {},
      });
      return r.data;
    },
    staleTime: 25 * 1000,
    refetchInterval: 30 * 1000,
  });

  const sectors        = data?.sectors        || [];
  const topSector      = data?.top_sector     || null;
  const sectorStocks   = data?.sector_stocks  || [];
  const insiderTrades  = data?.insider_trades || [];
  const rotation       = data?.rotation;
  const pulse          = data?.market_pulse;
  const macro          = data?.macro;
  const marketNews     = data?.market_news    || [];
  const generatedAt    = data?.generated_at;

  // Sort sectors by selected timeframe
  const sortedSectors = useMemo(() => {
    if (timeframe === 'd1') return [...sectors];
    return [...sectors].sort((a, b) => {
      const aVal = a[timeframe] ?? -999;
      const bVal = b[timeframe] ?? -999;
      return bVal - aVal;
    });
  }, [sectors, timeframe]);

  // Group sectors
  const groupedSectors = useMemo(() => {
    const groups = { growth: [], defensive: [], cyclical: [], other: [] };
    sortedSectors.forEach(s => {
      const g = s.group || 'other';
      if (groups[g]) groups[g].push(s);
      else groups.other.push(s);
    });
    return groups;
  }, [sortedSectors]);

  const toggleSector = useCallback((etf, finviz_filter) => {
    if (expandedSector === etf) {
      setExpandedSector(null);
    } else {
      setExpandedSector(etf);
      // Load stocks if not cached
      if (!sectorStocksMap[finviz_filter]) {
        loadSectorStocks(finviz_filter);
      }
    }
  }, [expandedSector, sectorStocksMap]);

  const loadSectorStocks = useCallback(async (filter) => {
    setLoadingFilter(filter);
    try {
      const r = await api.get('/briefing/sector/movers', { params: { filter } });
      setSectorStocksMap(prev => ({ ...prev, [filter]: r.data?.stocks || [] }));
    } catch {
      // silent fail
    }
    setLoadingFilter(null);
  }, []);

  // For the top sector, use pre-loaded stocks from main endpoint
  const getStocksForSector = useCallback((s) => {
    if (topSector && s.etf === topSector.etf && sectorStocks.length > 0) {
      return sectorStocks;
    }
    return sectorStocksMap[s.finviz_filter] || null;
  }, [topSector, sectorStocks, sectorStocksMap]);

  return (
    <div className="max-w-7xl mx-auto px-4 py-5 space-y-4">

      {/* ── Header ─────────────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            מפת סקטורים
            <span className="text-xs font-normal text-slate-500 bg-slate-800/60 rounded-full px-2 py-0.5">
              {sectors.length} סקטורים
            </span>
          </h2>
          {generatedAt && (
            <p className="text-[11px] text-slate-500 mt-0.5">עודכן: {fmtTime(generatedAt)}</p>
          )}
        </div>

        <div className="flex items-center gap-2">
          {/* Timeframe Toggle */}
          <div className="flex bg-slate-800/60 rounded-lg border border-slate-700/40 p-0.5">
            {Object.entries(TF_LABELS).map(([key, label]) => (
              <button
                key={key}
                onClick={() => setTimeframe(key)}
                className={`px-2.5 py-1 text-[11px] font-medium rounded-md transition-all
                  ${timeframe === key
                    ? 'bg-blue-600/80 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                  }`}
              >
                {label}
              </button>
            ))}
          </div>

          {/* View Toggle */}
          <div className="flex bg-slate-800/60 rounded-lg border border-slate-700/40 p-0.5">
            <button
              onClick={() => setViewMode('heatmap')}
              className={`px-2 py-1 text-[11px] rounded-md transition-all
                ${viewMode === 'heatmap' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
            >
              Heatmap
            </button>
            <button
              onClick={() => setViewMode('list')}
              className={`px-2 py-1 text-[11px] rounded-md transition-all
                ${viewMode === 'list' ? 'bg-slate-700 text-white' : 'text-slate-500 hover:text-slate-300'}`}
            >
              List
            </button>
          </div>

          {/* Refresh */}
          <button
            onClick={() => setForceKey(k => k + 1)}
            disabled={isFetching}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/60 border border-slate-600/50
              rounded-lg text-xs text-slate-300 hover:bg-slate-600/60 disabled:opacity-50 transition-all"
          >
            <RefreshCw size={13} className={isFetching ? 'animate-spin' : ''} />
            רענן
          </button>
        </div>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center h-48">
          <div className="text-slate-400 flex items-center gap-2">
            <RefreshCw size={18} className="animate-spin" />
            טוען מפת סקטורים...
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-950/40 border border-red-700/40 rounded-xl p-4 flex items-center gap-2 text-red-300 text-sm">
          <AlertCircle size={16} />
          שגיאה בטעינת הנתונים
        </div>
      )}

      {data && (
        <>
          {/* ── Macro Indicators ──────────────────────────────────────────────── */}
          <MacroStrip macro={macro} />

          {/* ── Market Pulse + Rotation ─────────────────────────────────────────── */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
            <div className="lg:col-span-2">
              <MarketPulse pulse={pulse} />
            </div>
            <RotationSignal rotation={rotation} />
          </div>

          {/* ── Market News ────────────────────────────────────────────────────── */}
          <MarketNewsFeed news={marketNews} />

          {/* ── Sector Heatmap / List ──────────────────────────────────────────── */}
          {viewMode === 'heatmap' ? (
            <div className="space-y-3">
              {/* Grouped heatmap */}
              {['growth', 'cyclical', 'defensive', 'other'].map(group => {
                const items = groupedSectors[group];
                if (!items || items.length === 0) return null;
                return (
                  <div key={group}>
                    <GroupHeader group={group} />
                    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-2">
                      {items.map(s => (
                        <div key={s.etf} className="space-y-2">
                          <HeatmapTile
                            s={s}
                            tf={timeframe}
                            isExpanded={expandedSector === s.etf}
                            onToggle={() => toggleSector(s.etf, s.finviz_filter)}
                          />
                        </div>
                      ))}
                    </div>
                    {/* Expanded detail — show below the group if a sector in this group is expanded */}
                    {items.some(s => s.etf === expandedSector) && (
                      <div className="mt-2">
                        {items.filter(s => s.etf === expandedSector).map(s => (
                          <SectorDetail
                            key={s.etf}
                            sector={s}
                            stocks={getStocksForSector(s)}
                            isLoadingStocks={loadingFilter === s.finviz_filter}
                            onLoadStocks={() => loadSectorStocks(s.finviz_filter)}
                          />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            /* List View */
            <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-700/40">
                <h3 className="text-sm font-semibold text-slate-200">סקטורים — {TF_LABELS[timeframe]}</h3>
              </div>
              <div className="divide-y divide-slate-700/30">
                {sortedSectors.map((s, idx) => {
                  const pct = timeframe === 'd1' ? s.change_pct : s[timeframe];
                  const isExp = expandedSector === s.etf;
                  return (
                    <div key={s.etf}>
                      <button
                        onClick={() => toggleSector(s.etf, s.finviz_filter)}
                        className="w-full flex items-center gap-3 px-4 py-3 hover:bg-slate-800/30 transition-colors text-right"
                      >
                        <span className="text-xs text-slate-600 w-5">{idx + 1}</span>
                        <span className="text-base w-7 text-center">{s.icon}</span>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-sm font-medium text-slate-200">{s.name}</span>
                            <span className="text-[10px] text-slate-600">{s.etf}</span>
                          </div>
                          <div className="flex gap-2 mt-0.5">
                            {s.drivers?.slice(0, 3).map(d => (
                              <span key={d.ticker} className="text-[10px]">
                                <span className="text-slate-500">{d.ticker}</span>
                                <span className={`ml-0.5 ${chgColor(d.change_pct)}`}>{fmtChg(d.change_pct)}</span>
                              </span>
                            ))}
                          </div>
                        </div>
                        {s.sparkline?.length > 1 && (
                          <Sparkline data={s.sparkline} width={60} height={20} />
                        )}
                        <MomentumGauge score={s.momentum_score} size={28} />
                        <div className="text-left w-20">
                          <div className={`text-sm font-bold ${chgColor(pct)}`}>{fmtChg(pct)}</div>
                          <div className="flex gap-1.5 mt-0.5">
                            {timeframe === 'd1' ? (
                              <>
                                {s.w1 != null && <span className={`text-[9px] ${chgColor(s.w1)}`}>{TF_LABELS.w1} {fmtChg(s.w1)}</span>}
                              </>
                            ) : (
                              <span className={`text-[9px] ${chgColor(s.change_pct)}`}>1D {fmtChg(s.change_pct)}</span>
                            )}
                          </div>
                        </div>
                        <VolumeBadge ratio={s.volume_ratio} />
                        {isExp ? <ChevronUp size={14} className="text-blue-400" /> : <ChevronDown size={14} className="text-slate-600" />}
                      </button>
                      {isExp && (
                        <div className="px-4 pb-3">
                          <SectorDetail
                            sector={s}
                            stocks={getStocksForSector(s)}
                            isLoadingStocks={loadingFilter === s.finviz_filter}
                            onLoadStocks={() => loadSectorStocks(s.finviz_filter)}
                          />
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* ── Insider Trades ──────────────────────────────────────────────────── */}
          <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl overflow-hidden">
            <div className="px-4 py-3 border-b border-slate-700/40 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-semibold text-amber-300">קניות מנהלים — Form 4</h3>
                <p className="text-[10px] text-slate-500">קניות ≥ $100K • 2 ימים אחרונים</p>
              </div>
              <span className="text-xs text-slate-600">{insiderTrades.length} עסקאות</span>
            </div>

            {insiderTrades.length === 0 ? (
              <div className="p-6 text-center text-slate-500 text-sm">
                אין קניות מנהלים בטווח הזמן
              </div>
            ) : (
              <div className="divide-y divide-slate-700/20">
                {insiderTrades.map((t, i) => (
                  <InsiderRow key={`${t.ticker}-${i}`} t={t} />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
