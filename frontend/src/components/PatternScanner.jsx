import { useState, useMemo, useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { RefreshCw, Search, TrendingUp, TrendingDown, Target, Shield, Zap, ChevronDown, ChevronUp, Clock, BarChart3 } from 'lucide-react';

const api = axios.create({ baseURL: '/api', timeout: 120000 });

// ── Color helpers ────────────────────────────────────────────────────────────
const winColor = (rate) => rate >= 70 ? '#4ade80' : rate >= 60 ? '#a3e635' : rate >= 55 ? '#fbbf24' : '#f87171';
const changeColor = (v) => v > 0 ? '#4ade80' : v < 0 ? '#f87171' : '#94a3b8';
const strengthLabel = { very_strong: 'חזק מאוד', strong: 'חזק', moderate: 'בינוני', weak: 'חלש' };
const strengthColor = { very_strong: '#4ade80', strong: '#a3e635', moderate: '#fbbf24', weak: '#64748b' };

// ── Pattern Heatmap Chart (SVG) ──────────────────────────────────────────────
function PatternHeatmap({ windows, height = 320 }) {
  if (!windows || windows.length === 0) return null;

  const W = 900;
  const H = height;
  const pad = { top: 40, right: 30, bottom: 60, left: 55 };
  const chartW = W - pad.left - pad.right;
  const chartH = H - pad.top - pad.bottom;
  const barW = Math.min(chartW / windows.length - 4, 50);

  const maxRange = Math.max(...windows.map(w => Math.max(Math.abs(w.avg_change), w.avg_range || 0.5)), 0.5);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ maxHeight: H }}>
      <defs>
        <linearGradient id="winGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#4ade80" stopOpacity="0.9" />
          <stop offset="100%" stopColor="#22c55e" stopOpacity="0.6" />
        </linearGradient>
        <linearGradient id="lossGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#f87171" stopOpacity="0.6" />
          <stop offset="100%" stopColor="#ef4444" stopOpacity="0.9" />
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
      </defs>

      {/* Background grid */}
      <rect x={pad.left} y={pad.top} width={chartW} height={chartH} fill="rgba(15,23,42,0.3)" rx="4" />
      {/* Zero line */}
      <line x1={pad.left} y1={pad.top + chartH / 2} x2={pad.left + chartW} y2={pad.top + chartH / 2}
        stroke="rgba(148,163,184,0.3)" strokeDasharray="4,4" />
      <text x={pad.left - 8} y={pad.top + chartH / 2 + 4} fill="#64748b" fontSize="10" textAnchor="end">0%</text>

      {/* Grid lines */}
      {[-maxRange, -maxRange / 2, maxRange / 2, maxRange].map((v, i) => {
        const y = pad.top + chartH / 2 - (v / maxRange) * (chartH / 2);
        return (
          <g key={i}>
            <line x1={pad.left} y1={y} x2={pad.left + chartW} y2={y}
              stroke="rgba(148,163,184,0.1)" />
            <text x={pad.left - 8} y={y + 4} fill="#475569" fontSize="9" textAnchor="end">
              {v > 0 ? '+' : ''}{v.toFixed(2)}%
            </text>
          </g>
        );
      })}

      {/* Bars */}
      {windows.map((w, i) => {
        const x = pad.left + (i * (chartW / windows.length)) + (chartW / windows.length - barW) / 2;
        const zeroY = pad.top + chartH / 2;

        // Main bar: avg change
        const barH = Math.abs(w.avg_change / maxRange) * (chartH / 2);
        const barY = w.avg_change >= 0 ? zeroY - barH : zeroY;
        const isWin = w.avg_change >= 0;

        // Win rate indicator dot
        const dotR = 5 + (w.win_rate - 50) / 10;
        const dotColor = winColor(w.win_rate);

        // Range whisker
        const rangeH = (w.avg_range / maxRange) * (chartH / 2);

        return (
          <g key={i}>
            {/* Range whisker (thin line showing total range) */}
            <line x1={x + barW / 2} y1={zeroY - rangeH} x2={x + barW / 2} y2={zeroY + rangeH}
              stroke="rgba(148,163,184,0.25)" strokeWidth="1" />
            <line x1={x + barW / 2 - 3} y1={zeroY - rangeH} x2={x + barW / 2 + 3} y2={zeroY - rangeH}
              stroke="rgba(148,163,184,0.3)" strokeWidth="1" />
            <line x1={x + barW / 2 - 3} y1={zeroY + rangeH} x2={x + barW / 2 + 3} y2={zeroY + rangeH}
              stroke="rgba(148,163,184,0.3)" strokeWidth="1" />

            {/* Main avg change bar */}
            <rect x={x} y={barY} width={barW} height={Math.max(barH, 1)} rx="3"
              fill={isWin ? 'url(#winGrad)' : 'url(#lossGrad)'}
              opacity={w.tradeable ? 1 : 0.5} />

            {/* Tradeable highlight */}
            {w.tradeable && (
              <rect x={x - 2} y={barY - 2} width={barW + 4} height={Math.max(barH, 1) + 4} rx="4"
                fill="none" stroke={dotColor} strokeWidth="1.5" opacity="0.5" filter="url(#glow)" />
            )}

            {/* Win rate dot on top */}
            <circle cx={x + barW / 2} cy={pad.top - 15} r={Math.max(dotR, 3)}
              fill={dotColor} opacity="0.9" />
            <text x={x + barW / 2} y={pad.top - 14} fill="#0f172a" fontSize="7" fontWeight="bold"
              textAnchor="middle" dominantBaseline="middle">
              {Math.round(w.win_rate)}
            </text>

            {/* Avg change label */}
            <text x={x + barW / 2} y={isWin ? barY - 4 : barY + barH + 12}
              fill={isWin ? '#4ade80' : '#f87171'} fontSize="9" fontWeight="bold"
              textAnchor="middle">
              {w.avg_change > 0 ? '+' : ''}{w.avg_change.toFixed(2)}%
            </text>

            {/* Time label */}
            <text x={x + barW / 2} y={H - pad.bottom + 15} fill="#94a3b8" fontSize="9"
              textAnchor="middle" transform={`rotate(-35, ${x + barW / 2}, ${H - pad.bottom + 15})`}>
              {w.window.split('-')[0]}
            </text>
          </g>
        );
      })}

      {/* Legend */}
      <g transform={`translate(${pad.left + 10}, ${H - 15})`}>
        <circle cx="0" cy="0" r="5" fill="#4ade80" opacity="0.9" />
        <text x="10" y="4" fill="#94a3b8" fontSize="9">Win Rate (בעיגול)</text>
        <line x1="100" y1="-3" x2="100" y2="3" stroke="rgba(148,163,184,0.4)" strokeWidth="1" />
        <text x="108" y="4" fill="#94a3b8" fontSize="9">| טווח ממוצע (ויסקר)</text>
        <rect x="230" y="-6" width="12" height="12" rx="2" fill="url(#winGrad)" opacity="0.7" />
        <text x="246" y="4" fill="#94a3b8" fontSize="9">שינוי ממוצע</text>
        <rect x="320" y="-7" width="14" height="14" rx="3" fill="none" stroke="#4ade80" strokeWidth="1.5" opacity="0.5" />
        <text x="340" y="4" fill="#94a3b8" fontSize="9">= חלון למסחר (WR≥60%)</text>
      </g>
    </svg>
  );
}

// ── Win/Loss donut mini ──────────────────────────────────────────────────────
function WinDonut({ winRate, size = 36 }) {
  const r = (size - 6) / 2;
  const circumference = 2 * Math.PI * r;
  const winArc = (winRate / 100) * circumference;

  return (
    <svg width={size} height={size}>
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="rgba(248,113,113,0.3)" strokeWidth="4" />
      <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={winColor(winRate)} strokeWidth="4"
        strokeDasharray={`${winArc} ${circumference}`}
        strokeLinecap="round" transform={`rotate(-90 ${size / 2} ${size / 2})`} />
      <text x={size / 2} y={size / 2 + 1} fill="#e2e8f0" fontSize="9" fontWeight="bold"
        textAnchor="middle" dominantBaseline="middle">{Math.round(winRate)}</text>
    </svg>
  );
}

// ── Signal Card ──────────────────────────────────────────────────────────────
function SignalCard({ signal }) {
  const isLong = signal.direction === 'LONG';
  return (
    <div className="rounded-lg p-3 flex items-center gap-3" style={{
      background: isLong ? 'rgba(74,222,128,0.06)' : 'rgba(248,113,113,0.06)',
      border: `1px solid ${isLong ? 'rgba(74,222,128,0.2)' : 'rgba(248,113,113,0.2)'}`,
    }}>
      <div className="flex flex-col items-center gap-1">
        {isLong ? <TrendingUp size={18} color="#4ade80" /> : <TrendingDown size={18} color="#f87171" />}
        <span className="text-xs font-black" style={{ color: isLong ? '#4ade80' : '#f87171' }}>
          {signal.direction}
        </span>
      </div>
      <div className="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
        <div>
          <span className="text-slate-500">חלון</span>
          <div className="font-bold text-white flex items-center gap-1">
            <Clock size={11} className="text-slate-500" />
            {signal.window}
          </div>
        </div>
        <div>
          <span className="text-slate-500">Win Rate</span>
          <div className="font-black" style={{ color: winColor(signal.win_rate) }}>
            {signal.win_rate}%
          </div>
        </div>
        <div>
          <span className="text-slate-500">R:R</span>
          <div className="font-bold" style={{ color: signal.risk_reward >= 1.5 ? '#4ade80' : '#fbbf24' }}>
            1:{signal.risk_reward}
          </div>
        </div>
        <div>
          <span className="text-slate-500">EV</span>
          <div className="font-bold" style={{ color: changeColor(signal.expected_value) }}>
            {signal.expected_value > 0 ? '+' : ''}{signal.expected_value}%
          </div>
        </div>
      </div>
      <div className="text-xs text-right space-y-0.5" style={{ minWidth: 100 }}>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">כניסה</span>
          <span className="font-mono text-white">${signal.entry}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">סטופ</span>
          <span className="font-mono" style={{ color: '#f87171' }}>${signal.stop}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">יעד</span>
          <span className="font-mono" style={{ color: '#4ade80' }}>${signal.target}</span>
        </div>
      </div>
      <div className="flex flex-col items-center">
        <div className="text-xs text-slate-500">ביטחון</div>
        <div className="text-lg font-black" style={{ color: signal.confidence >= 70 ? '#4ade80' : signal.confidence >= 55 ? '#fbbf24' : '#f87171' }}>
          {signal.confidence}
        </div>
      </div>
    </div>
  );
}

// ── Main Component ───────────────────────────────────────────────────────────
export default function PatternScanner() {
  const [manualTicker, setManualTicker] = useState('');
  const [analyzeTicker, setAnalyzeTicker] = useState('');
  const [interval, setInterval_] = useState('5m');
  const [days, setDays] = useState(45);
  const [expandedTicker, setExpandedTicker] = useState(null);
  const [activeTab, setActiveTab] = useState('analyze'); // pool | analyze
  const [poolRequested, setPoolRequested] = useState(false);

  // Step 1: Pool — only fetch when explicitly requested
  const { data: poolData, isLoading: poolLoading, refetch: refetchPool } = useQuery({
    queryKey: ['patternPool'],
    queryFn: async () => (await api.get('/pattern/pool')).data,
    staleTime: 60 * 60 * 1000,
    refetchInterval: 0,
    enabled: poolRequested,
  });

  // Manual ticker analysis
  const { data: tickerAnalysis, isLoading: tickerLoading, refetch: refetchTicker } = useQuery({
    queryKey: ['patternTicker', analyzeTicker, days, interval],
    queryFn: async () => (await api.get(`/pattern/analyze/${analyzeTicker}?days=${days}&interval=${interval}`)).data,
    enabled: analyzeTicker.length >= 1,
    staleTime: 15 * 60 * 1000,
    refetchInterval: 0,
  });

  const handleAnalyze = useCallback(() => {
    const t = manualTicker.trim().toUpperCase();
    if (t) {
      setAnalyzeTicker(t);
      setActiveTab('analyze');
    }
  }, [manualTicker]);

  const handlePoolTickerClick = useCallback((ticker) => {
    setManualTicker(ticker);
    setAnalyzeTicker(ticker);
    setActiveTab('analyze');
  }, []);

  return (
    <div className="p-3 sm:p-4 space-y-4" dir="rtl">

      {/* ── Header ── */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
        <div className="flex items-center gap-2">
          <BarChart3 size={20} color="#a78bfa" />
          <h2 className="text-lg font-black text-white">Pattern Scanner Bot</h2>
          <span className="text-xs px-2 py-0.5 rounded-full" style={{
            background: 'rgba(167,139,250,0.15)', border: '1px solid rgba(167,139,250,0.3)', color: '#c4b5fd'
          }}>Backtesting</span>
        </div>

        {/* Manual ticker input */}
        <div className="flex items-center gap-2 mr-auto">
          <div className="relative">
            <Search size={13} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              type="text"
              value={manualTicker}
              onChange={e => setManualTicker(e.target.value.toUpperCase())}
              onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
              placeholder="הכנס טיקר..."
              className="pl-8 pr-3 py-1.5 text-sm rounded-lg focus:outline-none"
              style={{
                background: '#161b22', border: '1px solid rgba(255,255,255,0.08)',
                color: '#e2e8f0', width: 140,
              }}
            />
          </div>
          <select value={interval} onChange={e => setInterval_(e.target.value)}
            className="px-2 py-1.5 text-xs rounded-lg" style={{
              background: '#161b22', border: '1px solid rgba(255,255,255,0.08)', color: '#94a3b8'
            }}>
            <option value="5m">5 דקות</option>
            <option value="15m">15 דקות</option>
          </select>
          <select value={days} onChange={e => setDays(Number(e.target.value))}
            className="px-2 py-1.5 text-xs rounded-lg" style={{
              background: '#161b22', border: '1px solid rgba(255,255,255,0.08)', color: '#94a3b8'
            }}>
            <option value={30}>30 ימים</option>
            <option value={45}>45 ימים</option>
            <option value={59}>60 ימים</option>
          </select>
          <button onClick={handleAnalyze}
            className="px-4 py-1.5 rounded-lg text-xs font-bold transition-all"
            style={{
              background: 'linear-gradient(135deg, #8b5cf6, #6366f1)',
              color: '#fff',
            }}>
            <Zap size={12} className="inline ml-1" />
            נתח
          </button>
        </div>
      </div>

      {/* ── Tabs ── */}
      <div className="flex gap-1 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
        {[
          { key: 'pool', label: 'מאגר מניות', icon: Shield, count: poolData?.count },
          { key: 'analyze', label: 'ניתוח דפוסים', icon: Target, count: tickerAnalysis?.tradeable_windows?.length },
        ].map(tab => (
          <button key={tab.key} onClick={() => { setActiveTab(tab.key); if (tab.key === 'pool') setPoolRequested(true); }}
            className="relative px-4 py-2.5 text-sm font-semibold transition-all flex items-center gap-1.5"
            style={{ color: activeTab === tab.key ? '#fff' : '#475569' }}>
            <tab.icon size={14} />
            {tab.label}
            {tab.count != null && (
              <span className="text-xs px-1.5 rounded-full" style={{
                background: activeTab === tab.key ? 'rgba(139,92,246,0.2)' : 'rgba(255,255,255,0.05)',
                color: activeTab === tab.key ? '#c4b5fd' : '#64748b',
              }}>{tab.count}</span>
            )}
            {activeTab === tab.key && (
              <div className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full"
                style={{ background: '#8b5cf6', boxShadow: '0 0 8px rgba(139,92,246,0.5)' }} />
            )}
          </button>
        ))}
      </div>

      {/* ── Pool Tab ── */}
      {activeTab === 'pool' && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">
              שלב 1: סינון מניות — שווי שוק &gt;$2B | ATR &gt;$2 או &gt;3% | מחזור &gt;5M
            </span>
            <button onClick={() => refetchPool()} className="text-xs px-3 py-1 rounded-lg flex items-center gap-1"
              style={{ background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.3)', color: '#c4b5fd' }}>
              <RefreshCw size={11} className={poolLoading ? 'animate-spin' : ''} />
              רענן
            </button>
          </div>

          {poolLoading && !poolData && (
            <div className="text-center py-12">
              <RefreshCw size={24} className="animate-spin mx-auto mb-3" style={{ color: '#8b5cf6' }} />
              <div className="text-sm text-slate-400">סורק מניות... (עד דקה)</div>
            </div>
          )}

          {poolData?.pool && (
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-slate-500 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                    <th className="text-right py-2 px-2">טיקר</th>
                    <th className="text-right py-2 px-2">חברה</th>
                    <th className="text-right py-2 px-2">מחיר</th>
                    <th className="text-right py-2 px-2">שווי שוק</th>
                    <th className="text-right py-2 px-2">ATR ($)</th>
                    <th className="text-right py-2 px-2">ATR %</th>
                    <th className="text-right py-2 px-2">מחזור</th>
                    <th className="text-right py-2 px-2">ספרד</th>
                    <th className="text-right py-2 px-2">סקטור</th>
                    <th className="text-center py-2 px-2">פעולה</th>
                  </tr>
                </thead>
                <tbody>
                  {poolData.pool.map((s, i) => (
                    <tr key={s.ticker} className="border-b transition-colors hover:bg-slate-800/30"
                      style={{ borderColor: 'rgba(255,255,255,0.03)' }}>
                      <td className="py-2 px-2 font-black text-white">{s.ticker}</td>
                      <td className="py-2 px-2 text-slate-400 truncate" style={{ maxWidth: 140 }}>{s.company}</td>
                      <td className="py-2 px-2 font-mono text-white">${s.price}</td>
                      <td className="py-2 px-2 font-mono text-slate-300">
                        {s.market_cap >= 1e12 ? `$${(s.market_cap / 1e12).toFixed(1)}T`
                          : `$${(s.market_cap / 1e9).toFixed(1)}B`}
                      </td>
                      <td className="py-2 px-2 font-mono font-bold" style={{ color: s.atr >= 3 ? '#4ade80' : '#fbbf24' }}>
                        ${s.atr}
                      </td>
                      <td className="py-2 px-2">
                        <span className="px-1.5 py-0.5 rounded font-bold" style={{
                          background: s.atr_pct >= 4 ? 'rgba(74,222,128,0.12)' : 'rgba(251,191,36,0.12)',
                          color: s.atr_pct >= 4 ? '#4ade80' : '#fbbf24',
                        }}>
                          {s.atr_pct}%
                        </span>
                      </td>
                      <td className="py-2 px-2 font-mono text-slate-300">
                        {s.avg_volume >= 1e6 ? `${(s.avg_volume / 1e6).toFixed(1)}M` : `${(s.avg_volume / 1e3).toFixed(0)}K`}
                      </td>
                      <td className="py-2 px-2 font-mono text-slate-400">{s.spread_pct}%</td>
                      <td className="py-2 px-2 text-slate-500 truncate" style={{ maxWidth: 100 }}>{s.sector}</td>
                      <td className="py-2 px-2 text-center">
                        <button onClick={() => handlePoolTickerClick(s.ticker)}
                          className="px-2.5 py-1 rounded text-xs font-bold transition-all"
                          style={{
                            background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.3)',
                            color: '#c4b5fd',
                          }}>
                          נתח →
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Analyze Tab ── */}
      {activeTab === 'analyze' && (
        <div className="space-y-4">
          {!analyzeTicker && (
            <div className="text-center py-16">
              <Search size={32} className="mx-auto mb-3 text-slate-600" />
              <div className="text-sm text-slate-500">הכנס טיקר למעלה או בחר מהמאגר</div>
            </div>
          )}

          {tickerLoading && (
            <div className="text-center py-12">
              <RefreshCw size={24} className="animate-spin mx-auto mb-3" style={{ color: '#8b5cf6' }} />
              <div className="text-sm text-slate-400">מנתח דפוסים ל-{analyzeTicker}...</div>
              <div className="text-xs text-slate-600 mt-1">מוריד נתונים של {days} ימים בנרות {interval}</div>
            </div>
          )}

          {tickerAnalysis && !tickerAnalysis.error && !tickerLoading && (
            <>
              {/* Ticker header */}
              <div className="rounded-xl p-4" style={{
                background: 'linear-gradient(135deg, rgba(139,92,246,0.08), rgba(59,130,246,0.05))',
                border: '1px solid rgba(139,92,246,0.2)',
              }}>
                <div className="flex items-center gap-4 flex-wrap">
                  <span className="text-2xl font-black text-white">{tickerAnalysis.ticker}</span>
                  <span className="text-xl font-mono font-bold text-white">${tickerAnalysis.price}</span>
                  <div className="flex gap-3 text-xs">
                    <span className="px-2 py-1 rounded" style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8' }}>
                      ATR: <span className="font-bold text-white">${tickerAnalysis.daily_atr}</span> ({tickerAnalysis.daily_atr_pct}%)
                    </span>
                    <span className="px-2 py-1 rounded" style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8' }}>
                      ימי מסחר: <span className="font-bold text-white">{tickerAnalysis.trading_days_analyzed}</span>
                    </span>
                    <span className="px-2 py-1 rounded" style={{ background: 'rgba(255,255,255,0.05)', color: '#94a3b8' }}>
                      נרות: <span className="font-bold text-white">{interval}</span>
                    </span>
                  </div>
                  <div className="mr-auto">
                    {tickerAnalysis.has_strong_patterns ? (
                      <span className="px-3 py-1 rounded-lg text-xs font-bold" style={{
                        background: 'rgba(74,222,128,0.12)', border: '1px solid rgba(74,222,128,0.3)', color: '#4ade80'
                      }}>
                        נמצאו {tickerAnalysis.tradeable_windows.length} דפוסים למסחר
                      </span>
                    ) : (
                      <span className="px-3 py-1 rounded-lg text-xs font-bold" style={{
                        background: 'rgba(248,113,113,0.12)', border: '1px solid rgba(248,113,113,0.3)', color: '#f87171'
                      }}>
                        אין דפוסים חזקים מספיק
                      </span>
                    )}
                  </div>
                </div>
              </div>

              {/* ── Chart ── */}
              <div className="rounded-xl p-4" style={{
                background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)',
              }}>
                <div className="flex items-center gap-2 mb-3">
                  <BarChart3 size={16} color="#a78bfa" />
                  <span className="text-sm font-bold text-white">גרף דפוסים לפי חצי שעה</span>
                  <span className="text-xs text-slate-500">שינוי ממוצע + טווח + Win Rate</span>
                </div>
                <PatternHeatmap windows={tickerAnalysis.windows} height={340} />
              </div>

              {/* ── Windows Table ── */}
              <div className="rounded-xl overflow-hidden" style={{
                background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)',
              }}>
                <div className="p-3 flex items-center gap-2 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                  <Clock size={14} color="#a78bfa" />
                  <span className="text-sm font-bold text-white">טבלת חלונות זמן</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-slate-500 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                        <th className="text-right py-2 px-3">חלון</th>
                        <th className="text-right py-2 px-2">שינוי ממוצע</th>
                        <th className="text-right py-2 px-2">Win Rate</th>
                        <th className="text-center py-2 px-2">W/L</th>
                        <th className="text-right py-2 px-2">ממוצע Win</th>
                        <th className="text-right py-2 px-2">ממוצע Loss</th>
                        <th className="text-right py-2 px-2">טווח</th>
                        <th className="text-right py-2 px-2">שגיאת תקן</th>
                        <th className="text-right py-2 px-2">הכי טוב</th>
                        <th className="text-right py-2 px-2">הכי גרוע</th>
                        <th className="text-right py-2 px-2">EV</th>
                        <th className="text-right py-2 px-2">חוזק</th>
                        <th className="text-center py-2 px-2">סטטוס</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tickerAnalysis.windows.map((w, i) => (
                        <tr key={i} className="border-b transition-colors hover:bg-slate-800/30"
                          style={{
                            borderColor: 'rgba(255,255,255,0.03)',
                            background: w.tradeable ? 'rgba(139,92,246,0.04)' : 'transparent',
                          }}>
                          <td className="py-2 px-3 font-bold text-white whitespace-nowrap">
                            <Clock size={11} className="inline ml-1 text-slate-500" />
                            {w.window}
                          </td>
                          <td className="py-2 px-2 font-mono font-bold" style={{ color: changeColor(w.avg_change) }}>
                            {w.avg_change > 0 ? '+' : ''}{w.avg_change}%
                          </td>
                          <td className="py-2 px-2">
                            <div className="flex items-center gap-1.5">
                              <WinDonut winRate={w.win_rate} size={30} />
                              <span className="font-bold" style={{ color: winColor(w.win_rate) }}>{w.win_rate}%</span>
                            </div>
                          </td>
                          <td className="py-2 px-2 text-center">
                            <div className="flex justify-center gap-0.5">
                              <div className="h-2 rounded-r" style={{
                                width: `${w.win_rate * 0.4}px`, background: '#4ade80',
                              }} />
                              <div className="h-2 rounded-l" style={{
                                width: `${w.loss_rate * 0.4}px`, background: '#f87171',
                              }} />
                            </div>
                          </td>
                          <td className="py-2 px-2 font-mono" style={{ color: '#4ade80' }}>
                            +{w.avg_win}%
                          </td>
                          <td className="py-2 px-2 font-mono" style={{ color: '#f87171' }}>
                            {w.avg_loss}%
                          </td>
                          <td className="py-2 px-2 font-mono text-slate-300">{w.avg_range}%</td>
                          <td className="py-2 px-2 font-mono text-slate-400">{w.std_dev}</td>
                          <td className="py-2 px-2 font-mono" style={{ color: '#4ade80' }}>+{w.best_day}%</td>
                          <td className="py-2 px-2 font-mono" style={{ color: '#f87171' }}>{w.worst_day}%</td>
                          <td className="py-2 px-2 font-mono font-bold" style={{ color: changeColor(w.expected_value || 0) }}>
                            {(w.expected_value || 0) > 0 ? '+' : ''}{(w.expected_value || 0)}%
                          </td>
                          <td className="py-2 px-2">
                            <span className="px-1.5 py-0.5 rounded text-xs font-bold" style={{
                              background: `${strengthColor[w.strength]}15`,
                              color: strengthColor[w.strength],
                            }}>
                              {strengthLabel[w.strength]}
                            </span>
                          </td>
                          <td className="py-2 px-2 text-center">
                            {w.tradeable ? (
                              <span className="px-2 py-0.5 rounded text-xs font-black" style={{
                                background: 'rgba(74,222,128,0.15)', color: '#4ade80',
                                border: '1px solid rgba(74,222,128,0.3)',
                              }}>TRADE</span>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* ── Trade Signals (Step 3) ── */}
              {tickerAnalysis.signals && tickerAnalysis.signals.length > 0 && (
                <div className="rounded-xl p-4 space-y-3" style={{
                  background: '#0d1117', border: '1px solid rgba(74,222,128,0.15)',
                }}>
                  <div className="flex items-center gap-2">
                    <Target size={16} color="#4ade80" />
                    <span className="text-sm font-bold text-white">שלב 3: סיגנלים למסחר</span>
                    <span className="text-xs text-slate-500">חלונות עם Win Rate ≥60% + שינוי ≥0.05%</span>
                  </div>
                  {tickerAnalysis.signals.map((sig, i) => (
                    <SignalCard key={i} signal={sig} />
                  ))}
                </div>
              )}
            </>
          )}

          {tickerAnalysis?.error && (
            <div className="text-center py-12">
              <div className="text-sm text-red-400">{tickerAnalysis.error}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
