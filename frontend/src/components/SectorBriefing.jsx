import { useState, useMemo, useCallback, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import {
  RefreshCw, TrendingUp, TrendingDown, AlertCircle, Newspaper,
  ChevronDown, ChevronUp, Zap, Shield, Activity, BarChart3,
  ArrowUpRight, ArrowDownRight, Minus, DollarSign, Users,
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

// ── Gold Signals ────────────────────────────────────────────────────────────────

function ResearchPanel({ ticker, onClose }) {
  const { data, isLoading } = useQuery({
    queryKey: ['insider-research', ticker],
    queryFn: () => api.get(`/research/insider-catalyst?ticker=${ticker}`).then(r => r.data),
    staleTime: 5 * 60_000,
  });

  return (
    <div className="mt-2 bg-slate-950/80 border border-amber-700/40 rounded-xl p-3 animate-in slide-in-from-top-2">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-bold text-amber-300">
          {isLoading ? '🔍 חוקר...' : `🔬 חקירה: ${data?.company || ticker}`}
        </span>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-xs px-2">✕</button>
      </div>
      {isLoading && (
        <div className="flex items-center gap-2 py-3">
          <RefreshCw className="w-3 h-3 animate-spin text-amber-400" />
          <span className="text-[11px] text-slate-400">מחפש חדשות, דוחות, שורט, אנליסטים...</span>
        </div>
      )}
      {data?.findings?.map((f, i) => (
        <div key={i} className="flex items-start gap-2 py-1.5 border-t border-slate-800/50 first:border-0">
          <span className="text-sm shrink-0">{f.icon}</span>
          <div className="flex-1 min-w-0">
            <p className="text-[11px] text-slate-200 leading-snug">{f.text}</p>
            <div className="flex items-center gap-2 mt-0.5">
              {f.source && <span className="text-[9px] text-slate-500">{f.source}</span>}
              {f.age && <span className="text-[9px] text-amber-600">{f.age}</span>}
            </div>
          </div>
        </div>
      ))}
      {data?.conclusion && (
        <div className="mt-2 pt-2 border-t border-amber-700/30">
          <p className="text-[11px] font-bold text-amber-400 leading-snug">{data.conclusion}</p>
        </div>
      )}
    </div>
  );
}

function GoldSignals({ signals }) {
  const [expanded, setExpanded] = useState(false);
  const [researchTicker, setResearchTicker] = useState(null);
  if (!signals?.length) return null;

  const goldCount = signals.filter(s => s.level === 'gold').length;
  const shown = expanded ? signals : signals.slice(0, 6);

  const levelAccent = {
    gold: 'text-amber-300',
    silver: 'text-slate-300',
    bronze: 'text-slate-400',
  };

  return (
    <div className="bg-slate-900/60 border border-amber-700/30 rounded-2xl overflow-hidden">
      <div className="px-3 sm:px-4 py-2.5 border-b border-amber-700/20 bg-amber-950/20 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-base">⚡</span>
          <h3 className="text-sm font-bold text-amber-300">סיגנלים — מידע זהב</h3>
          {goldCount > 0 && (
            <span className="text-[10px] bg-amber-800/50 text-amber-200 rounded-full px-2 py-0.5 font-bold">
              {goldCount} זהב
            </span>
          )}
        </div>
        {signals.length > 6 && (
          <button onClick={() => setExpanded(!expanded)} className="text-[11px] text-slate-500 hover:text-slate-300 py-1">
            {expanded ? 'הצג פחות' : `עוד ${signals.length - 6}`}
          </button>
        )}
      </div>
      <div className="divide-y divide-slate-700/20">
        {shown.map((s, i) => (
          <div key={i} className={`px-3 sm:px-4 py-2.5 hover:bg-slate-800/20 transition-colors border-r-2
            ${s.level === 'gold' ? 'border-r-amber-500' : 'border-r-slate-600'}`}>
            <div className="flex items-start gap-2">
              <span className="text-base shrink-0">{s.icon}</span>
              <div className="flex-1 min-w-0">
                <p className={`text-[12px] sm:text-[13px] font-medium leading-snug ${levelAccent[s.level]}`}>
                  {s.message}
                </p>
                {s.detail && s.detail !== 'No clear catalyst' && (
                  <p className="text-[11px] text-amber-400/70 mt-0.5 leading-snug font-medium">{s.detail}</p>
                )}
                <div className="flex flex-wrap items-center gap-2 mt-1">
                  <span className="text-[10px] sm:text-[11px] text-emerald-400/80 font-medium">→ {s.action}</span>
                  {s.ticker && (
                    <span className="text-[10px] text-slate-600 bg-slate-800/60 rounded px-1">{s.ticker}</span>
                  )}
                  {s.ticker && (
                    <button
                      onClick={() => setResearchTicker(researchTicker === s.ticker ? null : s.ticker)}
                      className="text-[10px] sm:text-[11px] bg-amber-700/40 hover:bg-amber-600/50 text-amber-200 rounded-lg px-2 py-1 font-bold transition-colors active:scale-95"
                    >
                      {researchTicker === s.ticker ? '🔬 סגור' : '🔍 חקור'}
                    </button>
                  )}
                </div>
                {s.data_source && (
                  <div className="text-[9px] sm:text-[10px] text-slate-600 mt-0.5 flex items-center gap-1">
                    <span className="text-emerald-600">✓</span>
                    <span>{s.data_source}</span>
                  </div>
                )}
                {researchTicker === s.ticker && (
                  <ResearchPanel ticker={s.ticker} onClose={() => setResearchTicker(null)} />
                )}
              </div>
              {s.level === 'gold' && (
                <span className="text-[10px] text-amber-500 font-bold shrink-0">GOLD</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Geopolitical Event Alerts ────────────────────────────────────────────────────

function GeoEventAlerts({ events }) {
  if (!events?.length) return null;

  const confColor = { High: 'text-emerald-400', Medium: 'text-amber-400', Low: 'text-slate-400' };

  const themeLabels = {
    oil_supply: '🛢️ אספקת נפט',
    gas_supply: '🔥 אספקת גז',
    strait_hormuz: '🚢 מצר הורמוז',
    gold_safe_haven: '🥇 מקלט בטוח',
    defense: '🛡️ ביטחון/הגנה',
  };

  return (
    <div className="bg-slate-900/60 border border-red-600/40 rounded-2xl overflow-hidden">
      <div className="px-3 sm:px-4 py-2.5 border-b border-red-700/30 bg-red-950/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-base">🌍</span>
          <h3 className="text-sm font-bold text-red-300">התראות גיאופוליטיות</h3>
          <span className="text-[10px] bg-red-800/60 text-red-200 rounded-full px-2 py-0.5 font-bold animate-pulse">
            {events.length} אירועים
          </span>
        </div>
      </div>
      <div className="divide-y divide-slate-700/20">
        {events.map((ev, i) => (
          <div key={i} className="px-3 sm:px-4 py-3 hover:bg-slate-800/20 transition-colors">
            {/* Event headline */}
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[11px] font-bold text-red-400">
                    {themeLabels[ev.theme] || ev.theme}
                  </span>
                  <span className={`text-[10px] font-medium ${confColor[ev.confidence]}`}>
                    {ev.confidence === 'High' ? 'ביטחון גבוה' : ev.confidence === 'Medium' ? 'ביטחון בינוני' : 'מעקב'}
                  </span>
                  {ev.age_hours != null && (
                    <span className="text-[10px] text-slate-600">
                      {ev.age_hours < 1 ? 'עכשיו' : ev.age_hours < 24 ? `לפני ${Math.round(ev.age_hours)} שע׳` : `לפני ${Math.round(ev.age_hours / 24)} ימים`}
                    </span>
                  )}
                </div>
                <p className="text-[12px] sm:text-[13px] text-slate-200 leading-snug font-medium">{ev.headline}</p>
                <p className="text-[10px] text-slate-500 mt-0.5">{ev.source} • {ev.article_count} כתבות • ציון {ev.total_score}</p>
              </div>
            </div>

            {/* Impact */}
            <div className="mt-2 flex flex-wrap gap-1.5">
              {ev.commodity_name && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-900/40 text-amber-300 border border-amber-600/30">
                  משפיע על: {ev.commodity_name}
                </span>
              )}
              {ev.affected_sectors?.map(s => (
                <span key={s} className="text-[10px] px-2 py-0.5 rounded-full bg-blue-900/30 text-blue-300 border border-blue-600/30">
                  {s}
                </span>
              ))}
            </div>

            {/* Play tickers with live % change */}
            {(ev.play_tickers_enriched || ev.play_tickers)?.length > 0 && (
              <div className="mt-1.5">
                <span className="text-[10px] text-emerald-500 font-medium">מניות לעקוב: </span>
                <div className="flex flex-wrap gap-1.5 mt-1">
                  {(ev.play_tickers_enriched || ev.play_tickers.map(t => ({ticker: t}))).map((item, j) => {
                    const tk = typeof item === 'string' ? item : item.ticker;
                    const chg = typeof item === 'object' ? item.change_pct : null;
                    const price = typeof item === 'object' ? item.price : null;
                    return (
                      <span key={j} className={`text-[11px] px-2 py-0.5 rounded-lg border font-medium
                        ${chg != null && chg > 5 ? 'bg-emerald-950/50 border-emerald-600/40 text-emerald-300' :
                          chg != null && chg > 0 ? 'bg-emerald-950/30 border-emerald-700/30 text-emerald-400' :
                          chg != null && chg < -3 ? 'bg-red-950/40 border-red-600/30 text-red-300' :
                          chg != null && chg < 0 ? 'bg-red-950/20 border-red-700/20 text-red-400' :
                          'bg-slate-800/60 border-slate-700/30 text-slate-300'}`}>
                        <span className="font-bold">{tk}</span>
                        {chg != null && (
                          <span className={`mr-1 ${chg >= 0 ? 'text-emerald-300' : 'text-red-300'}`}>
                            {chg > 0 ? '+' : ''}{chg.toFixed(1)}%
                          </span>
                        )}
                        {price != null && (
                          <span className="text-[9px] text-white/50">${price}</span>
                        )}
                      </span>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Additional headlines */}
            {ev.all_headlines?.length > 1 && (
              <div className="mt-1.5 space-y-0.5">
                {ev.all_headlines.slice(1, 3).map((h, j) => (
                  <p key={j} className="text-[10px] text-slate-500 leading-snug">• {h}</p>
                ))}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}


// ── Macro Event Plays ────────────────────────────────────────────────────────────

function MacroEventPlays({ plays }) {
  if (!plays?.length) return null;

  const confColor = { High: 'text-emerald-400', Medium: 'text-amber-400', Low: 'text-red-400' };
  const confBg = { High: 'bg-emerald-900/40 border-emerald-600/30', Medium: 'bg-amber-900/30 border-amber-600/30', Low: 'bg-red-900/30 border-red-600/30' };

  return (
    <div className="bg-slate-900/60 border border-red-700/30 rounded-2xl overflow-hidden">
      <div className="px-3 sm:px-4 py-2.5 border-b border-red-700/20 bg-red-950/20 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-base">🎯</span>
          <h3 className="text-sm font-bold text-red-300">התראות מאקרו — מניות בתנועה</h3>
          <span className="text-[10px] bg-red-800/50 text-red-200 rounded-full px-2 py-0.5 font-bold">
            {plays.length} הזדמנויות
          </span>
        </div>
      </div>
      <div className="divide-y divide-slate-700/20">
        {plays.map((p, i) => (
          <div key={`${p.ticker}-${i}`} className="px-3 sm:px-4 py-2.5 hover:bg-slate-800/20 transition-colors">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-sm font-bold text-emerald-400">{p.ticker}</span>
                <span className={`text-xs font-bold ${p.change_pct >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                  {p.change_pct > 0 ? '+' : ''}{p.change_pct}%
                </span>
                {p.price && <span className="text-[11px] text-white/70">${p.price}</span>}
                {p.rel_volume && p.rel_volume >= 2 && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-orange-900/40 text-orange-300 border border-orange-600/30">
                    x{p.rel_volume} נפח
                  </span>
                )}
              </div>
              <span className={`text-[10px] px-2 py-0.5 rounded-full border font-medium ${confBg[p.confidence]} ${confColor[p.confidence]}`}>
                {p.confidence === 'High' ? 'ביטחון גבוה' : p.confidence === 'Medium' ? 'ביטחון בינוני' : 'ביטחון נמוך'}
              </span>
            </div>
            <div className="text-[11px] text-amber-400/80 mt-1 leading-snug">{p.why}</div>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[10px] text-slate-500">{p.macro_icon} {p.play_label} | {p.sector}</span>
              {p.market_cap && <span className="text-[10px] text-slate-600">{p.market_cap}</span>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


// ── Smart Money Summary ─────────────────────────────────────────────────────────

function SmartMoneySummary({ smartMoney, sectors }) {
  if (!smartMoney) return null;
  const { top_accumulation = [], top_distribution = [] } = smartMoney;
  if (!top_accumulation.length && !top_distribution.length) return null;

  const getName = (etf) => sectors.find(s => s.etf === etf)?.name || etf;
  const getIcon = (etf) => sectors.find(s => s.etf === etf)?.icon || '';

  return (
    <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl p-4">
      <div className="flex items-center gap-2 mb-3">
        <DollarSign size={16} className="text-amber-400" />
        <h3 className="text-sm font-semibold text-amber-300">כסף חכם — לאן זורם הכסף?</h3>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {/* Accumulation (money flowing IN) */}
        {top_accumulation.length > 0 && (
          <div className="bg-emerald-950/30 border border-emerald-800/30 rounded-xl p-3">
            <div className="flex items-center gap-1.5 mb-2">
              <ArrowUpRight size={14} className="text-emerald-400" />
              <span className="text-[11px] font-semibold text-emerald-400">כסף נכנס (הצטברות)</span>
            </div>
            <div className="space-y-1.5">
              {top_accumulation.map(item => (
                <div key={item.etf} className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm">{getIcon(item.etf)}</span>
                    <span className="text-xs text-slate-200 font-medium">{getName(item.etf)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-emerald-400 font-bold">{item.label}</span>
                    {item.conviction >= 2 && (
                      <span className="text-[8px] bg-emerald-900/60 text-emerald-300 rounded px-1 py-0.5">שכנוע</span>
                    )}
                    {item.volume_signal === 'high' && (
                      <span className="text-[8px] bg-amber-900/60 text-amber-300 rounded px-1 py-0.5">Vol!</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Distribution (money flowing OUT) */}
        {top_distribution.length > 0 && (
          <div className="bg-red-950/30 border border-red-800/30 rounded-xl p-3">
            <div className="flex items-center gap-1.5 mb-2">
              <ArrowDownRight size={14} className="text-red-400" />
              <span className="text-[11px] font-semibold text-red-400">כסף יוצא (חלוקה)</span>
            </div>
            <div className="space-y-1.5">
              {top_distribution.map(item => (
                <div key={item.etf} className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className="text-sm">{getIcon(item.etf)}</span>
                    <span className="text-xs text-slate-200 font-medium">{getName(item.etf)}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-red-400 font-bold">{item.label}</span>
                    {item.conviction >= 2 && (
                      <span className="text-[8px] bg-red-900/60 text-red-300 rounded px-1 py-0.5">שכנוע</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Money Flow Badge ────────────────────────────────────────────────────────────

function MoneyFlowBadge({ flow }) {
  if (!flow || flow.signal === 'neutral') return null;

  const configs = {
    strong_accumulation: { color: 'text-emerald-300 bg-emerald-950/60', arrow: '▲▲' },
    accumulation:        { color: 'text-emerald-400 bg-emerald-950/40', arrow: '▲' },
    mild_accumulation:   { color: 'text-emerald-400/60 bg-emerald-950/30', arrow: '△' },
    strong_distribution: { color: 'text-red-300 bg-red-950/60', arrow: '▼▼' },
    distribution:        { color: 'text-red-400 bg-red-950/40', arrow: '▼' },
    mild_distribution:   { color: 'text-red-400/60 bg-red-950/30', arrow: '▽' },
  };
  const cfg = configs[flow.signal] || null;
  if (!cfg) return null;

  return (
    <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold ${cfg.color}`}
      title={flow.label}
    >
      {cfg.arrow} {flow.label}
    </span>
  );
}

// ── Feature Legend ───────────────────────────────────────────────────────────────

function FeatureLegend() {
  const [open, setOpen] = useState(false);

  const items = [
    { label: 'בעלות מוסדית', desc: 'אחוז המניות שמוחזקות על ידי קרנות ובנקי השקעות. מעל 60 אחוז אומר שהמניה מגובה על ידי שחקנים גדולים — הם לא נכנסים בלי לעשות שיעורי בית' },
    { label: 'מוסדיים מגדילים', desc: 'הקרנות הגדילו את האחזקה שלהן ברבעון האחרון. כשכסף חכם זורם פנימה, שווה לעקוב' },
    { label: 'מנהלים קונים', desc: 'מנהלי החברה שמים כסף מהכיס שלהם — הם חייבים לדווח על זה ל-SEC. אם CEO קונה, הוא בטוח שהחברה הולכת למקום טוב' },
    { label: 'שורט גבוה', desc: 'הרבה משקיעים הימרו נגד המניה. כשהמניה עולה, הם נאלצים לקנות בחזרה ולדחוף אותה עוד יותר למעלה — זה נקרא סקוויז' },
    { label: 'כמות מניות קטנה', desc: 'יש מעט מניות זמינות למסחר. כל קנייה גדולה מזיזה את המחיר בצורה חדה — גם למעלה וגם למטה' },
    { label: 'כסף נכנס לסקטור', desc: 'נפח מסחר גבוה ב-ETF של הסקטור בזמן שהוא עולה, ובאופן עקבי לאורך שבועות. סימן שמשקיעים גדולים צוברים' },
    { label: 'כסף יוצא מסקטור', desc: 'נפח מסחר גבוה ב-ETF בזמן ירידה עקבית. המוסדיים מפזרים אחזקות — הם רואים בעיות לפני כולם' },
    { label: 'מדד הפחד', desc: 'VIX מודד כמה השוק מפחד. מעל 25 זו תנודתיות חריגה, מעל 35 זו פאניקה אמיתית — שווה להקטין סיכון' },
    { label: 'נפט', desc: 'מחיר הנפט משפיע ישירות על חברות אנרגיה, חברות תעשייה ועלויות הובלה. עלייה חדה בנפט פוגעת ברוב הכלכלה' },
    { label: 'זהב', desc: 'כשזהב עולה, המשקיעים מחפשים מקלט — הם חוששים ממשהו. ירידה בזהב אומרת שהם מרגישים בטוחים ומוכנים לסכן' },
    { label: 'תשואת אגרות חוב', desc: 'כשהתשואה ל-10 שנים עולה, בנקים מרוויחים יותר אבל חברות טכנולוגיה ונדל"ן נפגעות כי הלוואות יקרות יותר' },
  ];

  return (
    <div className="bg-slate-900/40 border border-slate-700/30 rounded-xl overflow-hidden">
      <button onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-3 py-2 hover:bg-slate-800/30 transition-colors">
        <span className="text-[11px] text-slate-400 font-medium">מה כל מושג אומר — בעברית פשוטה</span>
        {open ? <ChevronUp size={12} className="text-slate-500" /> : <ChevronDown size={12} className="text-slate-500" />}
      </button>
      {open && (
        <div className="px-3 pb-3 space-y-2">
          {items.map((item, i) => (
            <div key={i} className="text-[11px]">
              <span className="text-slate-200 font-semibold">{item.label}: </span>
              <span className="text-slate-400">{item.desc}</span>
            </div>
          ))}
        </div>
      )}
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

      {/* Money flow badge */}
      <MoneyFlowBadge flow={s.money_flow} />

      {/* Bottom: ETF + Volume + Insiders */}
      <div className="flex items-center justify-between mt-1">
        <span className="text-[10px] text-slate-500">{s.etf} ${s.price}</span>
        <div className="flex items-center gap-1">
          {s.sector_insider_count > 0 && (
            <span className="text-[9px] px-1 py-0.5 rounded-full text-amber-400 bg-amber-950/40">
              {s.sector_insider_count} insider{s.sector_insider_count > 1 ? 's' : ''}
            </span>
          )}
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

        {/* Top Movers — multi-timeframe table */}
        {sector.top_movers?.length > 0 && (
          <div className="mt-2 bg-slate-800/40 rounded-xl overflow-hidden border border-slate-700/30">
            <div className="px-3 py-1.5 border-b border-slate-700/20 flex items-center gap-2">
              <span className="text-[10px] text-amber-400 font-medium">מניות שזזות:</span>
            </div>
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-[9px] text-slate-500 border-b border-slate-700/20">
                  <th className="text-right px-2 py-1 font-medium">טיקר</th>
                  <th className="text-right px-1 py-1 font-medium">מחיר</th>
                  <th className="text-right px-1 py-1 font-medium">30 ד׳</th>
                  <th className="text-right px-1 py-1 font-medium">4 שע׳</th>
                  <th className="text-right px-1 py-1 font-medium">יום</th>
                  <th className="text-right px-1 py-1 font-medium">שבוע</th>
                  <th className="text-right px-1 py-1 font-medium">נפח</th>
                  <th className="text-right px-1 py-1 font-medium"></th>
                </tr>
              </thead>
              <tbody>
                {sector.top_movers.slice(0, 5).map(m => {
                  const standout = m.is_standout;
                  const fmtVol = (v) => {
                    if (!v) return '—';
                    if (v >= 1e6) return `${(v/1e6).toFixed(1)}M`;
                    if (v >= 1e3) return `${(v/1e3).toFixed(0)}K`;
                    return v;
                  };
                  return (
                    <tr key={m.ticker} className={`border-b border-slate-700/10 hover:bg-slate-700/20 transition-colors
                      ${standout ? 'bg-amber-950/20 border-r-2 border-r-amber-500' : ''}`}>
                      <td className="px-2 py-1.5">
                        <div className="flex items-center gap-1">
                          {standout && <span className="text-amber-400 text-[9px]">★</span>}
                          <span className={`font-bold ${standout ? 'text-amber-300' : 'text-white'}`}>{m.ticker}</span>
                          {m.flags?.map((f, i) => (
                            <span key={i} className="text-[8px]" title={f.label}>{f.icon}</span>
                          ))}
                        </div>
                        {m.industry && <div className="text-[8px] text-slate-600 leading-tight">{m.industry}</div>}
                      </td>
                      <td className="px-1 py-1.5 text-right text-white/80">${m.price}</td>
                      <td className={`px-1 py-1.5 text-right font-medium ${chgColor(m.chg_30m)}`}>
                        {m.chg_30m != null ? `${m.chg_30m > 0 ? '+' : ''}${m.chg_30m}%` : '—'}
                      </td>
                      <td className={`px-1 py-1.5 text-right font-medium ${chgColor(m.chg_4h)}`}>
                        {m.chg_4h != null ? `${m.chg_4h > 0 ? '+' : ''}${m.chg_4h}%` : '—'}
                      </td>
                      <td className={`px-1 py-1.5 text-right font-bold ${chgColor(m.change_pct)}`}>
                        {fmtChg(m.change_pct)}
                      </td>
                      <td className={`px-1 py-1.5 text-right font-medium ${chgColor(m.chg_1w)}`}>
                        {m.chg_1w != null ? `${m.chg_1w > 0 ? '+' : ''}${m.chg_1w}%` : '—'}
                      </td>
                      <td className="px-1 py-1.5 text-right">
                        <span className="text-slate-400">{fmtVol(m.volume)}</span>
                        {m.rel_volume >= 2 && (
                          <span className="text-orange-400 text-[9px] mr-0.5">x{m.rel_volume.toFixed(1)}</span>
                        )}
                      </td>
                      <td className="px-1 py-1.5 text-right">
                        {m.move_estimate && (
                          <span className="text-[9px] text-emerald-400/80"
                            title={`${m.move_estimate.catalyst} • ${m.move_estimate.timeframe}`}>
                            →{m.move_estimate.target_pct}%
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
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

        {/* Money Flow + Sector Insiders */}
        <div className="flex flex-wrap items-center gap-3 mt-2">
          {sector.money_flow && sector.money_flow.signal !== 'neutral' && (
            <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px] font-medium
              ${sector.money_flow.score > 0
                ? 'bg-emerald-950/40 border border-emerald-800/30 text-emerald-300'
                : 'bg-red-950/40 border border-red-800/30 text-red-300'
              }`}>
              <DollarSign size={12} />
              <span>{sector.money_flow.label}</span>
              {sector.money_flow.conviction >= 2 && (
                <span className="text-[9px] opacity-70">(שכנוע רב-מסגרתי)</span>
              )}
            </div>
          )}

          {sector.sector_insider_count > 0 && (
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[11px]
              bg-amber-950/30 border border-amber-800/30 text-amber-300">
              <Users size={12} />
              <span>{sector.sector_insider_count} קניות מנהלים בסקטור</span>
            </div>
          )}
        </div>

        {/* Sector-specific insider trades */}
        {sector.sector_insiders?.length > 0 && (
          <div className="mt-2 space-y-1">
            {sector.sector_insiders.map((t, i) => (
              <div key={i} className="flex items-center gap-2 text-[10px] bg-amber-950/20 rounded-lg px-2 py-1">
                <span className="text-amber-400 font-bold">{t.ticker}</span>
                <span className="text-slate-400 truncate">{t.insider}</span>
                {t.value && <span className="text-amber-300 mr-auto">{t.value}</span>}
              </div>
            ))}
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
            {stocks.map(s => {
              const hasFlags = s.flags?.length > 0;
              const hasInst = s.inst_own != null;
              return (
                <div key={s.ticker} className={`bg-slate-800/50 border rounded-lg p-2.5
                  hover:border-slate-600/50 transition-colors
                  ${hasFlags ? 'border-amber-700/30' : 'border-slate-700/30'}`}>
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

                  {/* Ownership data row */}
                  {hasInst && (
                    <div className="flex flex-wrap gap-x-2 gap-y-0 text-[10px] mb-0.5">
                      {s.inst_own != null && (
                        <span className={s.inst_own >= 60 ? 'text-blue-400' : 'text-slate-500'}>
                          🏛️ {s.inst_own.toFixed(0)}%
                        </span>
                      )}
                      {s.inst_trans != null && s.inst_trans !== 0 && (
                        <span className={s.inst_trans > 0 ? 'text-emerald-400' : 'text-red-400'}>
                          {s.inst_trans > 0 ? '↑' : '↓'}{Math.abs(s.inst_trans).toFixed(1)}%
                        </span>
                      )}
                      {s.insider_own != null && s.insider_own > 5 && (
                        <span className="text-amber-400">👔 {s.insider_own.toFixed(0)}%</span>
                      )}
                      {s.float_short != null && s.float_short >= 10 && (
                        <span className={s.float_short >= 20 ? 'text-red-400 font-bold' : 'text-orange-400'}>
                          🩳 {s.float_short.toFixed(0)}%
                        </span>
                      )}
                    </div>
                  )}

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

                  {/* Smart flags */}
                  {hasFlags && (
                    <div className="flex flex-wrap gap-1 mt-1">
                      {s.flags.map((f, i) => (
                        <span key={i} className={`text-[9px] px-1.5 py-0.5 rounded-full font-medium
                          ${f.type === 'inst_buying' ? 'bg-blue-950/50 text-blue-300' :
                            f.type === 'institutional' ? 'bg-blue-950/30 text-blue-400/80' :
                            f.type === 'insider_buying' ? 'bg-amber-950/50 text-amber-300' :
                            f.type === 'high_short' ? 'bg-red-950/50 text-red-300' :
                            f.type === 'short' ? 'bg-orange-950/40 text-orange-300' :
                            f.type === 'small_float' ? 'bg-purple-950/40 text-purple-300' :
                            'bg-slate-800/40 text-slate-400'
                          }`}
                        >
                          {f.icon} {f.label}
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Move estimate */}
                  {s.move_estimate && (
                    <div className={`mt-1.5 px-2 py-1.5 rounded-lg text-[10px] border
                      ${s.move_estimate.confidence === 'high'
                        ? 'bg-emerald-950/40 border-emerald-700/30'
                        : s.move_estimate.confidence === 'medium'
                        ? 'bg-blue-950/30 border-blue-800/30'
                        : 'bg-slate-800/40 border-slate-700/30'
                      }`}>
                      <div className="flex items-center justify-between">
                        <span className="text-emerald-300 font-bold">
                          יעד: +{s.move_estimate.target_pct}%
                        </span>
                        <span className="text-slate-400">{s.move_estimate.timeframe}</span>
                      </div>
                      <div className="flex items-center justify-between mt-0.5">
                        <span className="text-slate-500">{s.move_estimate.catalyst}</span>
                        <span className={`text-[9px] px-1 rounded
                          ${s.move_estimate.confidence === 'high' ? 'text-emerald-400 bg-emerald-950/50' :
                            s.move_estimate.confidence === 'medium' ? 'text-blue-400 bg-blue-950/50' :
                            'text-slate-500 bg-slate-800/50'
                          }`}
                        >
                          {s.move_estimate.confidence === 'high' ? 'ביטחון גבוה' :
                           s.move_estimate.confidence === 'medium' ? 'ביטחון בינוני' : 'ביטחון נמוך'}
                        </span>
                      </div>
                    </div>
                  )}

                  {/* Stock Intelligence */}
                  {s.intel && (
                    <div className="mt-1.5 space-y-1">
                      {/* Analyst target + earnings */}
                      {(s.intel.target_price || s.intel.earnings_date) && (
                        <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-[10px] bg-blue-950/30 border border-blue-800/20 rounded-lg px-2 py-1.5">
                          {s.intel.target_price && (
                            <div>
                              <span className="text-slate-500">יעד אנליסטים: </span>
                              <span className="text-blue-300 font-bold">${s.intel.target_price}</span>
                              {s.intel.upside_pct != null && (
                                <span className={`font-bold mr-1 ${s.intel.upside_pct > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                  ({s.intel.upside_pct > 0 ? '+' : ''}{s.intel.upside_pct}%)
                                </span>
                              )}
                              {s.intel.analyst_count && (
                                <span className="text-slate-600"> ({s.intel.analyst_count} אנליסטים)</span>
                              )}
                            </div>
                          )}
                          {s.intel.target_low && s.intel.target_high && (
                            <div className="text-slate-500">
                              טווח: ${s.intel.target_low} — ${s.intel.target_high}
                            </div>
                          )}
                          {s.intel.recommendation && (
                            <div>
                              <span className="text-slate-500">המלצה: </span>
                              <span className={`font-medium ${
                                s.intel.recommendation.includes('קנייה') ? 'text-emerald-400' :
                                s.intel.recommendation.includes('מכירה') ? 'text-red-400' :
                                'text-amber-400'
                              }`}>{s.intel.recommendation}</span>
                            </div>
                          )}
                          {s.intel.earnings_date && (
                            <div>
                              <span className="text-slate-500">דוחות: </span>
                              <span className="text-amber-300 font-medium">{s.intel.earnings_date}</span>
                            </div>
                          )}
                        </div>
                      )}

                      {/* Catalyst hypotheses */}
                      {s.intel.catalysts?.length > 0 && (
                        <div className="bg-slate-800/30 rounded-lg px-2 py-1.5 space-y-0.5">
                          {s.intel.catalysts.slice(0, 3).map((c, i) => (
                            <div key={i} className="flex items-start gap-1.5 text-[10px]">
                              <span className="text-amber-400 shrink-0 mt-0.5">⚡</span>
                              <span className="text-slate-300">{c}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
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

function insiderGradeBadge(grade, winRate, totalTrades) {
  if (!grade || grade === 'N') {
    if (totalTrades === 0) return { text: 'חדש', color: 'bg-slate-700 text-slate-400', tip: 'אין היסטוריה' };
    return { text: 'חדש', color: 'bg-slate-700 text-slate-400', tip: 'פחות מ-2 עסקאות להערכה' };
  }
  if (grade === 'A') return { text: `${winRate}% הצלחה`, color: 'bg-emerald-900/60 text-emerald-300 border border-emerald-600/40', tip: `${totalTrades} עסקאות • הצלחה גבוהה` };
  if (grade === 'B') return { text: `${winRate}% הצלחה`, color: 'bg-amber-900/40 text-amber-300 border border-amber-600/30', tip: `${totalTrades} עסקאות • הצלחה בינונית` };
  return { text: `${winRate}% הצלחה`, color: 'bg-red-900/40 text-red-300 border border-red-600/30', tip: `${totalTrades} עסקאות • הצלחה נמוכה — זהירות` };
}

function InsiderRow({ t }) {
  const sig = insiderSignal(t.change_pct);
  const ageColor = t.filing_age_hours < 6 ? 'text-green-400' : t.filing_age_hours < 24 ? 'text-yellow-500' : 'text-slate-600';
  const ageText = t.filing_age_hours != null
    ? (t.filing_age_hours < 1 ? 'עכשיו' : t.filing_age_hours < 24 ? `לפני ${Math.round(t.filing_age_hours)} שע׳` : `לפני ${Math.round(t.filing_age_hours / 24)} ימים`)
    : null;

  const gradeBadge = insiderGradeBadge(t.insider_grade, t.insider_win_rate, t.insider_total_trades || 0);
  const clusterCount = t.same_ticker_buys || 1;

  return (
    <div className="px-3 py-2.5 border-b border-slate-700/30 last:border-0 hover:bg-slate-800/30 transition-colors">
      {/* Row 1: Ticker + change + value + freshness */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-sm font-bold text-emerald-400">{t.ticker}</span>
          {t.change_pct != null && (
            <span className={`text-xs font-bold ${chgColor(t.change_pct)}`}>{fmtChg(t.change_pct)}</span>
          )}
          {t.current_price && (
            <span className="text-[11px] text-white/70">${t.current_price.toFixed(2)}</span>
          )}
          {sig && <span className={`text-[10px] sm:text-[11px] ${sig.color}`}>{sig.text}</span>}
          {clusterCount > 1 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-purple-900/50 text-purple-300 border border-purple-600/30 font-medium">
              {clusterCount} רוכשים
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {t.value && <span className="text-xs font-medium text-amber-400">{t.value}</span>}
          {ageText && <span className={`text-[10px] ${ageColor}`}>{ageText}</span>}
        </div>
      </div>
      {/* Row 2: Insider name + title + quality badge */}
      <div className="flex items-center gap-2 mt-1">
        <span className="text-[11px] sm:text-xs text-slate-200">{t.insider || t.company || '—'}</span>
        {t.title && <span className="text-[10px] sm:text-[11px] text-slate-500">({t.title})</span>}
        <span className={`text-[9px] px-1.5 py-0.5 rounded-full ${gradeBadge.color}`} title={gradeBadge.tip}>
          {gradeBadge.text}
        </span>
        {t.insider_avg_return != null && t.insider_total_trades >= 2 && (
          <span className={`text-[9px] ${t.insider_avg_return >= 0 ? 'text-emerald-500' : 'text-red-400'}`}>
            ממוצע {t.insider_avg_return > 0 ? '+' : ''}{t.insider_avg_return}%
          </span>
        )}
        {t.market_cap_live && <span className="text-[10px] text-slate-600">{t.market_cap_live}</span>}
      </div>
      {/* Row 2.5: Other buyers (cluster buy detail) */}
      {t.other_buyers && t.other_buyers.length > 0 && (
        <div className="text-[10px] text-purple-400/70 mt-0.5 leading-snug">
          גם קנו: {t.other_buyers.map(o => `${o.insider || 'מנהל'}${o.title ? ` (${o.title})` : ''} ${o.value || ''}`).join(' • ')}
        </div>
      )}
      {/* Row 3: Why / catalyst */}
      {t.why && t.why !== 'No clear catalyst' && (
        <div className="text-[11px] text-amber-400/80 mt-1 leading-snug">{t.why}</div>
      )}
      {t.why === 'No clear catalyst' && (
        <div className="text-[10px] text-slate-500/50 mt-0.5">אין קטליסט ברור</div>
      )}
      {/* Grade C warning */}
      {t.insider_grade === 'C' && (
        <div className="text-[10px] text-red-400/60 mt-0.5">
          ⚠️ אחוזי הצלחה נמוכים — {t.insider_win_rate}% מתוך {t.insider_total_trades} עסקאות
        </div>
      )}
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
  const [expandedSector, setExpandedSector] = useState(null);
  const [sectorStocksMap, setSectorStocksMap] = useState({}); // {filter: stocks[]}
  const [loadingFilter, setLoadingFilter] = useState(null);
  const [timeframe, setTimeframe] = useState('d1');
  const [viewMode, setViewMode] = useState('heatmap'); // heatmap | list

  const forceRef = useRef(false);
  const { data, isLoading, isFetching, error, refetch } = useQuery({
    queryKey: ['sectorBriefing'],
    queryFn: async () => {
      const params = forceRef.current ? { force: true } : {};
      forceRef.current = false;
      const r = await api.get('/briefing/sector', { params });
      return r.data;
    },
    staleTime: 25 * 1000,
    refetchInterval: 30 * 1000,
    placeholderData: (prev) => prev,  // keep old data visible during refetch
    retry: 2,
    retryDelay: 3000,
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
            onClick={() => { forceRef.current = true; refetch(); }}
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

          {/* ── Geopolitical Alerts ──────────────────────────────────────────── */}
          <GeoEventAlerts events={data?.geo_events} />

          {/* ── Gold Signals ──────────────────────────────────────────────────── */}
          <GoldSignals signals={data?.gold_signals} />

          {/* ── Macro Event Plays ─────────────────────────────────────────────── */}
          <MacroEventPlays plays={data?.macro_event_plays} />

          {/* ── Smart Money ─────────────────────────────────────────────────────── */}
          <SmartMoneySummary smartMoney={data?.smart_money} sectors={sectors} />

          {/* ── Feature Legend ──────────────────────────────────────────────────── */}
          <FeatureLegend />

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
                    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
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
