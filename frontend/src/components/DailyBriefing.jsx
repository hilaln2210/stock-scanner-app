import { useState, useEffect } from 'react';
import { RefreshCw, Calendar } from 'lucide-react';
import axios from 'axios';

const API_BASE = '/api';

// ── Sector icons ───────────────────────────────────────────────────────────────

const SECTOR_ICONS = {
  'Technology':             '💻',
  'Healthcare':             '💊',
  'Financial Services':     '🏦',
  'Financial':              '🏦',
  'Consumer Cyclical':      '🛍️',
  'Consumer Defensive':     '🛒',
  'Consumer Discretionary': '🛍️',
  'Consumer Staples':       '🛒',
  'Energy':                 '⚡',
  'Industrials':            '🏭',
  'Communication Services': '📡',
  'Utilities':              '💡',
  'Real Estate':            '🏘️',
  'Basic Materials':        '⛏️',
  'Materials':              '⛏️',
};
function sectorIcon(s) { return s ? (SECTOR_ICONS[s] || '📊') : ''; }

// ── News type labels ───────────────────────────────────────────────────────────

const NEWS_TYPE_META = {
  analyst_upgrade:   { label: '↑ שדרוג אנליסט',  color: 'text-emerald-300 bg-emerald-950/60 border-emerald-700/40' },
  analyst_downgrade: { label: '↓ הורדת דירוג',   color: 'text-red-300    bg-red-950/60    border-red-700/40' },
  analyst_note:      { label: 'אנליסט',           color: 'text-sky-300    bg-sky-950/60    border-sky-700/40' },
  earnings:          { label: 'דוח כספי',         color: 'text-yellow-300 bg-yellow-950/60 border-yellow-700/40' },
  regulatory:        { label: 'FDA / רגולציה',    color: 'text-purple-300 bg-purple-950/60 border-purple-700/40' },
  ma:                { label: 'מיזוג / רכישה',    color: 'text-amber-300  bg-amber-950/60  border-amber-700/40' },
  partnership:       { label: 'עסקה / שותפות',    color: 'text-sky-300    bg-sky-950/60    border-sky-700/40' },
  capital:           { label: 'הון / דיבידנד',    color: 'text-slate-300  bg-slate-800/60  border-slate-600/40' },
  guidance:          { label: 'תחזית',            color: 'text-orange-300 bg-orange-950/60 border-orange-700/40' },
  legal:             { label: '⚠ משפטי',          color: 'text-red-400    bg-red-950/60    border-red-700/40' },
  general:           null,
};

// ── Helpers ────────────────────────────────────────────────────────────────────

function rsiLabel(rsi) {
  if (!rsi) return { text: 'אין מידע', color: 'text-slate-500' };
  if (rsi < 30) return { text: `מכירת יתר (${Math.round(rsi)}) — ריבאונד אפשרי`, color: 'text-emerald-400' };
  if (rsi < 42) return { text: `ירד חזק (${Math.round(rsi)}) — מחפש קרקע`, color: 'text-sky-400' };
  if (rsi < 62) return { text: `ניטרלי (${Math.round(rsi)}) — יש מקום לתנועה`, color: 'text-slate-300' };
  if (rsi < 72) return { text: `מומנטום חיובי (${Math.round(rsi)})`, color: 'text-slate-300' };
  if (rsi < 80) return { text: `חם (${Math.round(rsi)}) — שים לב לתיקון`, color: 'text-yellow-400' };
  return { text: `קנוי מדי (${Math.round(rsi)}) — סיכון לתיקון`, color: 'text-red-400' };
}

function beatLabel(pct) {
  if (pct == null) return null;
  if (pct >= 40) return { text: `הפתיעה בענק +${pct}%`, color: 'text-emerald-400', icon: '🚀' };
  if (pct >= 15) return { text: `הפתיעה חזק +${pct}%`, color: 'text-emerald-400', icon: '↑' };
  if (pct >= 3)  return { text: `הפתיעה +${pct}%`, color: 'text-emerald-500', icon: '↑' };
  if (pct >= 0)  return { text: `עברה בצמצום (${pct}%)`, color: 'text-slate-400', icon: '→' };
  return { text: `החמיצה ${pct}%`, color: 'text-red-400', icon: '↓' };
}

function scoreColor(score) {
  if (score >= 75) return '#10b981';
  if (score >= 55) return '#38bdf8';
  if (score >= 35) return '#f59e0b';
  return '#475569';
}

function fmtMcap(v) {
  if (!v) return '';
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9)  return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6)  return `$${(v / 1e6).toFixed(0)}M`;
  return '';
}

function fmtDate(d) {
  if (!d) return null;
  return new Date(d).toLocaleDateString('he-IL', { day: 'numeric', month: 'long' });
}

// ── SVG Sparkline ─────────────────────────────────────────────────────────────

function Sparkline({ prices, ticker, width = 120, height = 36 }) {
  if (!prices || prices.length < 3) return null;
  const min = Math.min(...prices), max = Math.max(...prices);
  const range = max - min || 1;
  const pad = 2;
  const pts = prices.map((p, i) => {
    const x = pad + (i / (prices.length - 1)) * (width - pad * 2);
    const y = pad + (height - pad * 2) - ((p - min) / range) * (height - pad * 2);
    return [x.toFixed(1), y.toFixed(1)];
  });
  const ptsStr = pts.map(p => p.join(',')).join(' ');
  const isUp = prices[prices.length - 1] >= prices[0];
  const color = isUp ? '#10b981' : '#ef4444';
  const fillPts = `${pts[0][0]},${height} ${ptsStr} ${pts[pts.length-1][0]},${height}`;
  const gid = `spk-${ticker}`;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={color} stopOpacity="0.35" />
          <stop offset="100%" stopColor={color} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <polygon points={fillPts} fill={`url(#${gid})`} />
      <polyline points={ptsStr} fill="none" stroke={color} strokeWidth="1.5"
        strokeLinejoin="round" strokeLinecap="round" />
      {/* Last price dot */}
      <circle cx={pts[pts.length-1][0]} cy={pts[pts.length-1][1]} r="2.5"
        fill={color} />
    </svg>
  );
}

// ── Score Gauge (SVG ring) ─────────────────────────────────────────────────────

function ScoreGauge({ score }) {
  const r = 24, cx = 30, cy = 30, sw = 4.5;
  const circ = 2 * Math.PI * r;
  const filled = Math.min((score || 0) / 100, 1) * circ;
  const c = scoreColor(score || 0);
  return (
    <div className="relative flex items-center justify-center shrink-0" style={{ width: 60, height: 60 }}>
      <svg width="60" height="60" viewBox="0 0 60 60" style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={cx} cy={cy} r={r} fill="none" stroke="#1e293b" strokeWidth={sw} />
        <circle cx={cx} cy={cy} r={r} fill="none" stroke={c} strokeWidth={sw}
          strokeDasharray={`${filled.toFixed(1)} ${circ.toFixed(1)}`}
          strokeLinecap="round"
          style={{ filter: (score || 0) >= 55 ? `drop-shadow(0 0 6px ${c}99)` : 'none' }}
        />
      </svg>
      <div className="absolute flex flex-col items-center leading-none">
        <span className="text-base font-black tabular-nums" style={{ color: c }}>{score || 0}</span>
        <span className="text-[8px] font-bold uppercase tracking-wide" style={{ color: c + '88' }}>score</span>
      </div>
    </div>
  );
}

// ── News ──────────────────────────────────────────────────────────────────────

function StockNews({ ticker, embeddedNews }) {
  const [dbNews, setDbNews] = useState(null);
  const hasEmbedded = embeddedNews && embeddedNews.length > 0;

  useEffect(() => {
    if (hasEmbedded) return;
    let ok = true;
    axios.get(`${API_BASE}/news?ticker=${ticker}&hours=168&limit=5`)
      .then(r => { if (ok) setDbNews(r.data || []); })
      .catch(() => { if (ok) setDbNews([]); });
    return () => { ok = false; };
  }, [ticker, hasEmbedded]);

  const news = hasEmbedded ? embeddedNews : (dbNews || []);
  if (!news.length) return <p className="text-xs text-slate-600 py-1">אין חדשות זמינות</p>;

  const typeOrder = ['analyst_upgrade','analyst_downgrade','earnings','guidance','regulatory','ma','partnership','capital','analyst_note','legal','general'];
  const sorted = [...news].sort((a, b) =>
    typeOrder.indexOf(a.news_type || 'general') - typeOrder.indexOf(b.news_type || 'general')
  );

  return (
    <div className="space-y-3">
      {sorted.slice(0, 4).map((n, i) => {
        const url = n.url || n.link || '#';
        const src = n.publisher || n.source || '';
        const pd  = n.published_at || n.providerPublishTime;
        const ds  = pd ? (typeof pd === 'number'
          ? new Date(pd * 1000).toLocaleDateString('he-IL', { day: 'numeric', month: 'short' })
          : new Date(pd).toLocaleDateString('he-IL', { day: 'numeric', month: 'short' })) : '';
        const meta = NEWS_TYPE_META[n.news_type] || null;
        const mainText = n.summary?.length > 20 ? n.summary : n.title;
        const subText  = n.summary?.length > 20 ? n.title : null;
        return (
          <div key={i} className="border-b border-slate-800 last:border-0 pb-3 last:pb-0">
            {meta && (
              <span className={`inline-block text-[10px] font-semibold px-2 py-0.5 rounded-full border mb-1.5 ${meta.color}`}>
                {meta.label}
              </span>
            )}
            <p className="text-sm text-slate-200 leading-snug" dir="rtl">{mainText}</p>
            {subText && (
              <a href={url} target="_blank" rel="noreferrer"
                className="text-xs text-slate-600 hover:text-sky-400 transition-colors line-clamp-1 mt-1 block">
                ← {subText}
              </a>
            )}
            {!subText && (
              <a href={url} target="_blank" rel="noreferrer"
                className="text-[10px] text-slate-700 hover:text-sky-400 transition-colors mt-1 block">
                קרא עוד →
              </a>
            )}
            <p className="text-[10px] text-slate-700 mt-0.5">{src}{ds ? ` · ${ds}` : ''}</p>
          </div>
        );
      })}
    </div>
  );
}

// ── Earnings Timeline ──────────────────────────────────────────────────────────

function EarningsTimeline({ stock, compact = false }) {
  const history = stock.earnings_history || [];
  if (!history.length) return null;
  const beatCount  = history.filter(q => q.beat).length;
  const allBeat    = beatCount === history.length;
  const mostlyBeat = beatCount >= history.length * 0.75;
  const cScore = allBeat ? 'text-emerald-300' : mostlyBeat ? 'text-emerald-400'
    : beatCount >= history.length * 0.5 ? 'text-yellow-400' : 'text-red-400';
  const fmtShort = d => d ? new Date(d).toLocaleDateString('he-IL', { month: 'short' }) : '?';

  return (
    <div className="space-y-3">
      {/* Beat-rate headline */}
      <div className="flex items-end gap-5" dir="rtl">
        <div className="flex items-baseline gap-2">
          <span className={`text-4xl font-black tabular-nums ${cScore}`}
            style={allBeat ? { textShadow: '0 0 20px #10b98177' } : {}}>
            {beatCount}/{history.length}
          </span>
          <span className="text-sm text-slate-500 leading-tight">רבעונים<br/>הפתיעו</span>
        </div>
        {/* Bar chart — bigger, with % label above each bar */}
        <div className="flex gap-2 items-end" style={{ height: 56 }}>
          {[...history].reverse().map((q, i) => {
            const barH = Math.min(44, Math.max(10, Math.abs(q.surprise_pct || 5) * 2));
            return (
              <div key={i} className="flex flex-col items-center gap-1">
                <span className={`text-xs font-black ${q.beat ? 'text-emerald-400' : 'text-red-400'}`}>
                  {q.beat ? '+' : ''}{q.surprise_pct}%
                </span>
                <div className={`w-8 rounded-sm ${q.beat ? 'bg-emerald-500' : 'bg-red-500/70'}`}
                  style={{ height: barH }}
                  title={`${q.date}: ${q.beat ? '+' : ''}${q.surprise_pct}%`}
                />
                <span className="text-[9px] text-slate-600">{fmtShort(q.date)}</span>
              </div>
            );
          })}
        </div>
        {allBeat && (
          <span className="text-sm text-emerald-400 font-black border border-emerald-700/50 rounded-lg px-2.5 py-1 bg-emerald-950/40">
            ✓ רצף מושלם
          </span>
        )}
      </div>

      {/* Next earnings hint */}
      {!compact && stock.next_earnings_date && (
        <p className="text-xs text-slate-600">
          הדוח הבא: <span className="text-sky-500 font-semibold">{fmtDate(stock.next_earnings_date)}</span>
        </p>
      )}

      {/* 52-week range bar */}
      {!compact && stock.week52_high && stock.week52_low && (() => {
        const pct = Math.min(100, Math.max(0,
          (stock.price - stock.week52_low) / (stock.week52_high - stock.week52_low) * 100
        ));
        return (
          <div>
            <div className="flex justify-between text-[10px] text-slate-700 mb-1">
              <span>שפל שנתי ${stock.week52_low}</span>
              <span className="text-slate-500">שנה אחרונה</span>
              <span>שיא שנתי ${stock.week52_high}</span>
            </div>
            <div className="h-1.5 bg-slate-800 rounded-full relative">
              <div className="h-full rounded-full"
                style={{ width: `${pct}%`, background: 'linear-gradient(to right, #475569, #38bdf8)' }} />
              <div className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full bg-white shadow-lg ring-2 ring-slate-900"
                style={{ left: `calc(${pct}% - 6px)` }} />
            </div>
          </div>
        );
      })()}
    </div>
  );
}

// ── Stock Card (Top 5 — full detail, 2-column body) ───────────────────────────

function StockCard({ stock, rank, crossScanners }) {
  const beat      = beatLabel(stock.earnings_surprise_pct);
  const rsi       = rsiLabel(stock.rsi);
  const sc        = stock.score || 0;
  const todayPct  = stock.today_pct;
  const volRatio  = stock.volume_ratio;
  const isUp      = (todayPct || 0) >= 0;
  const isHotMove = Math.abs(todayPct || 0) >= 3;
  const isHotVol  = (volRatio || 0) >= 1.5;
  const priceChangeEarnings = stock.price_change_since_earnings || 0;
  const ac = scoreColor(sc);

  const borderColor = isHotMove ? (isUp ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)')
    : isHotVol ? 'rgba(245,158,11,0.35)' : 'rgba(255,255,255,0.06)';

  const glowShadow = isHotMove
    ? (isUp ? '0 0 32px rgba(16,185,129,0.12)' : '0 0 32px rgba(239,68,68,0.12)')
    : isHotVol ? '0 0 32px rgba(245,158,11,0.1)' : 'none';

  return (
    <div className="rounded-xl overflow-hidden flex bg-[#0d1117]"
      style={{ border: `1px solid ${borderColor}`, boxShadow: glowShadow }}>

      {/* Score accent bar — left edge */}
      <div className="w-1.5 shrink-0"
        style={{ background: `linear-gradient(to bottom, ${ac}, ${ac}22)` }} />

      <div className="flex-1 min-w-0">

        {/* ══ HEADER ROW ══ */}
        <div className="flex items-stretch gap-0 border-b border-slate-800/80">

          {/* Left: ticker identity */}
          <div className="flex-1 px-6 py-4">
            <div className="flex items-center gap-3 flex-wrap mb-1">
              <span className="text-xs text-slate-700 font-mono">#{rank}</span>
              <a href={`https://finviz.com/quote.ashx?t=${stock.ticker}`} target="_blank" rel="noreferrer"
                className="text-3xl font-black text-white hover:text-sky-400 transition-colors tracking-tighter leading-none">
                {stock.ticker}
              </a>
              {stock.sector && (
                <span className="text-xs text-slate-500 bg-slate-800/80 border border-slate-700/40 px-2 py-0.5 rounded-full">
                  {sectorIcon(stock.sector)} {stock.sector}
                </span>
              )}
              {fmtMcap(stock.market_cap) && (
                <span className="text-sm font-bold text-slate-600">{fmtMcap(stock.market_cap)}</span>
              )}
              {crossScanners?.length > 0 && (
                <span className="text-xs text-amber-400 bg-amber-950/30 border border-amber-700/30 px-2 py-0.5 rounded-full">
                  ⭐ {crossScanners.join(' · ')}
                </span>
              )}
            </div>
            <p className="text-base text-slate-500">{stock.company}</p>
          </div>

          {/* Center: price block */}
          <div className="flex flex-col items-center justify-center px-8 border-l border-r border-slate-800/80">
            <p className="text-3xl font-black text-white font-mono tabular-nums leading-none">${stock.price}</p>
            {todayPct != null && (
              <p className={`text-lg font-black mt-1 ${isUp ? 'text-emerald-400' : 'text-red-400'}`}
                style={{ textShadow: isHotMove ? `0 0 10px ${isUp ? '#10b981' : '#ef4444'}55` : 'none' }}>
                {isUp ? '▲' : '▼'}{Math.abs(todayPct).toFixed(1)}%
              </p>
            )}
            {isHotVol && (
              <p className="text-xs text-amber-400 mt-0.5 font-bold">🔥 vol ×{volRatio?.toFixed(1)}</p>
            )}
          </div>

          {/* Right: score gauge */}
          <div className="flex flex-col items-center justify-center px-6">
            <ScoreGauge score={sc} />
          </div>
        </div>

        {/* ══ SPARKLINE — full width ══ */}
        {stock.price_history?.length >= 5 && (
          <div className="px-6 pt-3 pb-1">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[9px] text-slate-700 uppercase tracking-widest">20 יום אחרונים</span>
              {stock.week52_high && stock.week52_low && (() => {
                const pct = Math.min(100, Math.max(0,
                  (stock.price - stock.week52_low) / (stock.week52_high - stock.week52_low) * 100
                ));
                return (
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] text-slate-700">${stock.week52_low}</span>
                    <div className="w-24 h-1.5 bg-slate-800 rounded-full relative">
                      <div className="h-full rounded-full"
                        style={{ width: `${pct}%`, background: 'linear-gradient(to right, #334155, #38bdf8)' }} />
                      <div className="absolute top-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full bg-white ring-1 ring-slate-900"
                        style={{ left: `calc(${pct}% - 5px)` }} />
                    </div>
                    <span className="text-[9px] text-slate-700">${stock.week52_high}</span>
                    <span className="text-[9px] text-slate-600">שנה</span>
                  </div>
                );
              })()}
            </div>
            <Sparkline prices={stock.price_history} ticker={stock.ticker} width={900} height={56} />
          </div>
        )}

        {/* ══ ALERT STRIP ══ */}
        {(isHotMove || (isHotVol && !isHotMove)) && (
          <div className={`mx-6 my-2 rounded-lg px-4 py-2 text-sm font-semibold ${
            isHotMove && isUp  ? 'bg-emerald-950/60 text-emerald-300 border border-emerald-800/40'
            : isHotMove        ? 'bg-red-950/60 text-red-300 border border-red-800/40'
            :                    'bg-amber-950/50 text-amber-300 border border-amber-800/40'
          }`} dir="rtl">
            {isHotMove && isUp  && `⚡ עולה ${todayPct?.toFixed(1)}% היום — תנועה חריגה`}
            {isHotMove && !isUp && `⚡ יורדת ${Math.abs(todayPct || 0).toFixed(1)}% היום — לחץ מכירה`}
            {!isHotMove && isHotVol && `🔥 Volume ×${volRatio?.toFixed(1)} — ביקוש חריג מהממוצע`}
          </div>
        )}

        {/* ══ TWO-COLUMN BODY ══ */}
        <div className="grid grid-cols-2 border-t border-slate-800/80 divide-x divide-slate-800/80">

          {/* ─── LEFT COLUMN: Earnings + Facts + Prices ─── */}
          <div className="space-y-0">

            {/* Earnings track record */}
            {(stock.earnings_history || []).length > 0 && (
              <div className="px-6 py-5 border-b border-slate-800/80">
                <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-4">רקורד דוחות</p>
                <EarningsTimeline stock={stock} />
              </div>
            )}

            {/* Key facts */}
            <div className="px-6 py-5 border-b border-slate-800/80 space-y-3" dir="rtl">
              {beat && (
                <div className="flex items-start gap-3">
                  <span className="text-2xl mt-0.5 shrink-0">{beat.icon}</span>
                  <div>
                    <p className="text-xs text-slate-600 mb-0.5">דוח {fmtDate(stock.earnings_date)}</p>
                    <p className={`text-base font-bold ${beat.color}`}>{beat.text}</p>
                  </div>
                </div>
              )}
              {stock.reported_eps != null && stock.reported_eps < 0 && (
                <div className="flex items-center gap-2 rounded-lg px-3 py-2 bg-yellow-950/30 border border-yellow-800/30">
                  <span className="text-yellow-400">⚠</span>
                  <p className="text-sm text-yellow-500">עדיין מפסידה — {stock.reported_eps.toFixed(2)}$ למניה</p>
                </div>
              )}
              {stock.rsi && (
                <div>
                  <p className="text-xs text-slate-600 mb-0.5">לחץ שוק</p>
                  <p className={`text-sm font-semibold ${rsi.color}`}>{rsi.text}</p>
                </div>
              )}
              {priceChangeEarnings !== 0 && (
                <div>
                  <p className="text-xs text-slate-600 mb-0.5">מאז הדוח</p>
                  <p className={`text-base font-black ${priceChangeEarnings > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {priceChangeEarnings > 0 ? '+' : ''}{priceChangeEarnings}%
                  </p>
                </div>
              )}
              {stock.rs_vs_qqq != null && (
                <div>
                  <p className="text-xs text-slate-600 mb-0.5">כוח יחסי vs QQQ (20 יום)</p>
                  <p className={`text-base font-black ${stock.rs_vs_qqq >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                    {stock.rs_vs_qqq >= 0 ? '+' : ''}{stock.rs_vs_qqq}%
                  </p>
                </div>
              )}
              {!beat && stock.reason && (
                <p className="text-sm text-slate-400 leading-relaxed">{stock.reason}</p>
              )}
              {stock.atr_pct && (
                <p className="text-xs text-slate-700">ATR: {stock.atr_pct}% ביום</p>
              )}
            </div>

            {/* Tailwinds / Headwinds */}
            {(stock.tailwinds?.length > 0 || stock.headwinds?.length > 0) && (
              <div className="px-6 py-4 border-b border-slate-800/80 flex flex-wrap gap-2">
                {stock.tailwinds?.map((t, i) => (
                  <span key={i} className="text-xs text-emerald-400 bg-emerald-950/30 border border-emerald-900/40 px-2.5 py-1 rounded-full">↑ {t}</span>
                ))}
                {stock.headwinds?.map((h, i) => (
                  <span key={i} className="text-xs text-red-400 bg-red-950/30 border border-red-900/40 px-2.5 py-1 rounded-full">↓ {h}</span>
                ))}
              </div>
            )}

            {/* Price levels */}
            <div className="px-6 py-4 grid grid-cols-2 gap-6" dir="rtl">
              <div>
                <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-1.5">⚡ לצפות לפריצה</p>
                <p className="text-lg font-black text-yellow-400">{stock.watch_level}</p>
              </div>
              <div>
                <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-1.5">תמיכה</p>
                <p className="text-lg font-black text-slate-400">${stock.support}</p>
              </div>
              {stock.recent_8k_date && (
                <div className="col-span-2">
                  <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-1">דיווח SEC</p>
                  <p className="text-xs text-slate-500">{stock.recent_8k_type || '8-K'} · {stock.recent_8k_date}</p>
                </div>
              )}
            </div>
          </div>

          {/* ─── RIGHT COLUMN: News ─── */}
          <div className="px-6 py-5">
            <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-4">חדשות אחרונות</p>
            <StockNews ticker={stock.ticker} embeddedNews={stock.recent_news} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Compact Row (ranks 6+) ─────────────────────────────────────────────────────

function CompactRow({ stock, rank, crossScanners }) {
  const [expanded, setExpanded] = useState(false);
  const history   = stock.earnings_history || [];
  const beat      = beatLabel(stock.earnings_surprise_pct);
  const rsi       = rsiLabel(stock.rsi);
  const sc        = stock.score || 0;
  const todayPct  = stock.today_pct;
  const volRatio  = stock.volume_ratio;
  const isUp      = (todayPct || 0) >= 0;
  const isHotMove = Math.abs(todayPct || 0) >= 3;
  const isHotVol  = (volRatio || 0) >= 1.5;
  const ac        = scoreColor(sc);

  const borderStyle = isHotMove
    ? { borderColor: isUp ? 'rgba(16,185,129,0.4)' : 'rgba(239,68,68,0.4)' }
    : isHotVol ? { borderColor: 'rgba(245,158,11,0.35)' }
    : {};

  return (
    <div className="rounded-lg overflow-hidden bg-[#0d1117] border border-slate-800 flex"
      style={borderStyle}>
      {/* Accent stripe */}
      <div className="w-0.5 shrink-0" style={{ background: `linear-gradient(to bottom, ${ac}, ${ac}22)` }} />

      <div className="flex-1 min-w-0">
        {/* Main row */}
        <div className="flex items-center gap-3 px-4 py-3.5 cursor-pointer hover:bg-slate-800/20 transition-colors"
          onClick={() => setExpanded(e => !e)}>

          {/* Rank */}
          <span className="text-xs text-slate-700 w-6 text-center shrink-0 font-mono">{rank}</span>

          {/* Score badge */}
          <div className="shrink-0 w-10 h-7 flex items-center justify-center rounded text-sm font-black tabular-nums"
            style={{
              background: `${ac}18`,
              border: `1px solid ${ac}44`,
              color: ac,
              boxShadow: sc >= 75 ? `0 0 6px ${ac}44` : 'none',
            }}>
            {sc}
          </div>

          {/* Ticker */}
          <span className="text-base font-black text-white w-16 shrink-0 tracking-tight">{stock.ticker}</span>

          {/* Company + sector */}
          <div className="flex flex-col min-w-0 flex-1 hidden sm:flex">
            <span className="text-sm text-slate-400 truncate">{stock.company}</span>
            {stock.sector && (
              <span className="text-xs text-slate-700">{sectorIcon(stock.sector)} {stock.sector}</span>
            )}
          </div>

          {/* Sparkline — larger */}
          {stock.price_history?.length >= 5 && (
            <div className="shrink-0 hidden md:block">
              <Sparkline prices={stock.price_history} ticker={`${stock.ticker}-c`} width={90} height={30} />
            </div>
          )}

          {/* Earnings beat */}
          {beat && (
            <div className="shrink-0 text-right hidden lg:block">
              <p className="text-[9px] text-slate-700">דוח</p>
              <p className={`text-sm font-black ${beat.color}`}>
                {stock.earnings_surprise_pct > 0 ? '+' : ''}{stock.earnings_surprise_pct}%
              </p>
            </div>
          )}

          {/* Today % */}
          <div className="shrink-0 text-right w-16">
            <p className="text-[9px] text-slate-700">היום</p>
            <p className={`text-sm font-black tabular-nums ${
              isHotMove ? (isUp ? 'text-emerald-400' : 'text-red-400')
              : todayPct == null ? 'text-slate-600'
              : isUp ? 'text-emerald-500' : 'text-red-500'
            }`}>
              {todayPct != null ? `${isUp ? '+' : ''}${todayPct.toFixed(1)}%` : '—'}
            </p>
          </div>

          {/* Volume ratio */}
          {isHotVol && (
            <span className="text-xs text-amber-400 font-bold shrink-0 hidden lg:block">🔥×{volRatio?.toFixed(1)}</span>
          )}

          {/* Price */}
          <div className="shrink-0 text-right w-20">
            <p className="text-[9px] text-slate-700">מחיר</p>
            <p className="text-sm font-black font-mono text-white tabular-nums">${stock.price}</p>
          </div>

          {/* RS vs QQQ */}
          {stock.rs_vs_qqq != null && (
            <div className="shrink-0 text-right hidden xl:block w-14">
              <p className="text-[9px] text-slate-700">RS</p>
              <p className={`text-sm font-bold ${stock.rs_vs_qqq >= 0 ? 'text-emerald-500' : 'text-red-500'}`}>
                {stock.rs_vs_qqq >= 0 ? '+' : ''}{stock.rs_vs_qqq}
              </p>
            </div>
          )}

          {/* Beat history dots — larger */}
          {history.length > 0 && (
            <div className="flex gap-1 shrink-0">
              {[...history].reverse().map((q, i) => (
                <div key={i} className={`w-2.5 h-2.5 rounded-full ${q.beat ? 'bg-emerald-500' : 'bg-red-500/70'}`}
                  title={`${q.date}: ${q.beat ? '+' : ''}${q.surprise_pct}%`} />
              ))}
            </div>
          )}

          <span className="text-slate-700 text-xs ml-1">{expanded ? '▲' : '▼'}</span>
        </div>

        {/* Expanded — 2-column */}
        {expanded && (
          <div className="border-t border-slate-800/60 bg-[#0a0e14]">
            {/* Sparkline full-width */}
            {stock.price_history?.length >= 5 && (
              <div className="px-5 pt-4 pb-2">
                <Sparkline prices={stock.price_history} ticker={`${stock.ticker}-exp`} width={900} height={44} />
              </div>
            )}
            <div className="grid grid-cols-2 divide-x divide-slate-800/60 border-t border-slate-800/60">
              {/* Left: facts + earnings */}
              <div className="px-5 py-4 space-y-3" dir="rtl">
                {beat && (
                  <div>
                    <p className="text-xs text-slate-600 mb-0.5">דוח {fmtDate(stock.earnings_date)}</p>
                    <p className={`text-sm font-bold ${beat.color}`}>{beat.text}</p>
                  </div>
                )}
                {stock.rsi && (
                  <div>
                    <p className="text-xs text-slate-600 mb-0.5">לחץ שוק</p>
                    <p className={`text-sm font-semibold ${rsi.color}`}>{rsi.text}</p>
                  </div>
                )}
                {stock.price_change_since_earnings !== 0 && (
                  <div>
                    <p className="text-xs text-slate-600 mb-0.5">מאז הדוח</p>
                    <p className={`text-base font-black ${stock.price_change_since_earnings > 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                      {stock.price_change_since_earnings > 0 ? '+' : ''}{Math.abs(stock.price_change_since_earnings)}%
                    </p>
                  </div>
                )}
                {stock.reason && !beat && <p className="text-sm text-slate-500 leading-relaxed">{stock.reason}</p>}
                <EarningsTimeline stock={stock} compact={true} />
              </div>
              {/* Right: news */}
              <div className="px-5 py-4">
                <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-3">חדשות</p>
                <StockNews ticker={stock.ticker} embeddedNews={stock.recent_news} />
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Hot Today ─────────────────────────────────────────────────────────────────

function HotToday({ stocks }) {
  const hot = stocks
    .filter(s => Math.abs(s.today_pct || 0) >= 3 || (s.volume_ratio || 0) >= 1.5)
    .sort((a, b) =>
      (Math.abs(b.today_pct || 0) * 2 + (b.volume_ratio || 1)) -
      (Math.abs(a.today_pct || 0) * 2 + (a.volume_ratio || 1))
    );
  if (!hot.length) return null;

  // Max magnitude for bar scaling
  const maxMag = Math.max(...hot.map(s => Math.max(Math.abs(s.today_pct || 0), (s.volume_ratio || 1) - 1)));

  return (
    <div className="rounded-xl overflow-hidden border border-orange-900/50"
      style={{ boxShadow: '0 0 20px rgba(251,146,60,0.08)' }}>
      {/* Header */}
      <div className="px-4 py-2.5 flex items-center gap-2 border-b border-orange-900/40"
        style={{ background: 'linear-gradient(to right, rgba(120,53,15,0.4), rgba(30,27,75,0.1))' }}>
        <span className="text-sm font-black text-orange-300" style={{ textShadow: '0 0 12px rgba(251,146,60,0.5)' }}>
          🔥 חם עכשיו
        </span>
        <span className="text-xs text-orange-700">{hot.length} מניות עם פעילות חריגה</span>
        <span className="ml-auto flex items-center gap-1">
          <span className="w-1.5 h-1.5 rounded-full bg-orange-400 animate-pulse" />
          <span className="text-[10px] text-orange-700">LIVE</span>
        </span>
      </div>

      {/* Leaderboard rows */}
      <div className="divide-y divide-slate-800/60 bg-[#0d1117]">
        {hot.map((s, idx) => {
          const tod = s.today_pct;
          const vol = s.volume_ratio;
          const up  = (tod || 0) >= 0;
          const mag = Math.max(Math.abs(tod || 0) / maxMag, ((vol || 1) - 1) / maxMag);
          return (
            <div key={s.ticker} className="flex items-center gap-3 px-4 py-2.5">
              {/* Rank */}
              <span className="text-[10px] text-slate-700 w-4 shrink-0 font-mono">{idx + 1}</span>

              {/* Ticker */}
              <a href={`https://finviz.com/quote.ashx?t=${s.ticker}`} target="_blank" rel="noreferrer"
                className="text-sm font-black text-white hover:text-orange-300 transition-colors w-14 shrink-0">
                {s.ticker}
              </a>

              {/* Company + sector */}
              <div className="flex flex-col min-w-0 w-32 shrink-0">
                <span className="text-xs text-slate-500 truncate">{s.company}</span>
                {s.sector && <span className="text-[9px] text-slate-700">{sectorIcon(s.sector)} {s.sector}</span>}
              </div>

              {/* Magnitude bar */}
              <div className="flex-1 min-w-0 hidden sm:block">
                <div className="h-1.5 bg-slate-800 rounded-full overflow-hidden">
                  <div className="h-full rounded-full transition-all"
                    style={{
                      width: `${Math.min(100, mag * 100)}%`,
                      background: up
                        ? 'linear-gradient(to right, #065f46, #10b981)'
                        : 'linear-gradient(to right, #7f1d1d, #ef4444)',
                    }} />
                </div>
              </div>

              {/* Stats */}
              <div className="flex items-center gap-2 shrink-0">
                {Math.abs(tod || 0) >= 1 && (
                  <span className={`text-sm font-black tabular-nums ${up ? 'text-emerald-400' : 'text-red-400'}`}>
                    {up ? '+' : ''}{tod?.toFixed(1)}%
                  </span>
                )}
                {(vol || 0) >= 1.5 && (
                  <span className="text-xs text-amber-500 font-bold bg-amber-950/30 px-1.5 py-0.5 rounded">
                    ×{vol?.toFixed(1)}
                  </span>
                )}
                <span className="text-xs font-mono text-slate-500">${s.price}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Market Status ─────────────────────────────────────────────────────────────

function MarketStatus({ status }) {
  if (!status?.summary) return null;
  const spy  = status.spy || {};
  const qqq  = status.qqq || {};
  const spyUp = (spy.change_pct || 0) >= 0;
  const qqqUp = (qqq.change_pct || 0) >= 0;
  const vix   = status.vix;
  const vixColor = !vix ? '#94a3b8' : vix < 20 ? '#10b981' : vix < 30 ? '#f59e0b' : '#ef4444';
  const ma = status.ma_signal;
  const maText = ma === 'bullish' ? `SPY +${status.spy_vs_200_pct}% מעל MA200`
    : ma === 'bearish' ? `SPY ${status.spy_vs_200_pct}% מתחת MA200`
    : ma === 'neutral' ? `SPY ליד MA200 (${status.spy_vs_200_pct}%)`
    : null;
  const maColor = ma === 'bullish' ? '#10b981' : ma === 'bearish' ? '#ef4444' : '#f59e0b';

  const bgGrad = ma === 'bullish'
    ? 'linear-gradient(135deg, rgba(2,44,34,0.6) 0%, rgba(13,17,23,0.95) 60%)'
    : ma === 'bearish'
    ? 'linear-gradient(135deg, rgba(69,10,10,0.5) 0%, rgba(13,17,23,0.95) 60%)'
    : 'linear-gradient(135deg, rgba(15,23,42,0.8) 0%, rgba(13,17,23,0.95) 60%)';

  return (
    <div className="rounded-xl border border-slate-800 overflow-hidden"
      style={{ background: bgGrad, boxShadow: '0 1px 20px rgba(0,0,0,0.4)' }}>
      <div className="px-5 py-4">
        {/* Live indicator */}
        <div className="flex items-center gap-2 mb-4">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span className="text-[10px] text-slate-500 uppercase tracking-widest">שוק בזמן אמת</span>
          <span className="ml-auto text-[10px] text-slate-700">
            {new Date().toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' })}
          </span>
        </div>

        <div className="flex items-end gap-6 flex-wrap">
          {/* SPY */}
          <div>
            <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-1">S&P 500</p>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-black text-white font-mono tabular-nums">${spy.price}</span>
              <span className={`text-base font-bold ${spyUp ? 'text-emerald-400' : 'text-red-400'}`}>
                {spyUp ? '▲' : '▼'}{Math.abs(spy.change_pct || 0).toFixed(2)}%
              </span>
            </div>
          </div>

          {/* QQQ */}
          <div>
            <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-1">NASDAQ 100</p>
            <div className="flex items-baseline gap-2">
              <span className="text-2xl font-black text-white font-mono tabular-nums">${qqq.price}</span>
              <span className={`text-base font-bold ${qqqUp ? 'text-emerald-400' : 'text-red-400'}`}>
                {qqqUp ? '▲' : '▼'}{Math.abs(qqq.change_pct || 0).toFixed(2)}%
              </span>
            </div>
          </div>

          {/* VIX */}
          {vix && (
            <div className="border-l border-slate-800 pl-6">
              <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-1">VIX — פחד</p>
              <span className="text-2xl font-black font-mono tabular-nums" style={{ color: vixColor,
                textShadow: `0 0 12px ${vixColor}66` }}>
                {vix}
              </span>
            </div>
          )}

          {/* MA signal */}
          {maText && (
            <div className="border-l border-slate-800 pl-6 flex-1" dir="rtl">
              <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-1">מצב שוק</p>
              <p className="text-sm font-bold" style={{ color: maColor }}>{maText}</p>
              <p className="text-[10px] text-slate-600 mt-0.5">
                {ma === 'bullish' ? 'מגמה עולה מאושרת' : ma === 'bearish' ? 'מגמה יורדת מאושרת' : 'אזור החלטה קריטי'}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Sector Heatmap ────────────────────────────────────────────────────────────

function SectorHeatmap({ sectorPerf }) {
  if (!sectorPerf || !Object.keys(sectorPerf).length) return null;
  const sectors = Object.entries(sectorPerf)
    .map(([sym, d]) => ({ sym, name: d.name, pct: d.pct }))
    .sort((a, b) => b.pct - a.pct);

  function blockStyle(pct) {
    if (pct > 2)   return { bg: 'rgba(16,185,129,0.85)', text: '#022c22', shadow: '0 0 10px rgba(16,185,129,0.35)' };
    if (pct > 1)   return { bg: 'rgba(16,185,129,0.45)', text: '#a7f3d0', shadow: 'none' };
    if (pct > 0.2) return { bg: 'rgba(16,185,129,0.18)', text: '#6ee7b7', shadow: 'none' };
    if (pct > -0.2)return { bg: 'rgba(71,85,105,0.3)',   text: '#94a3b8', shadow: 'none' };
    if (pct > -1)  return { bg: 'rgba(239,68,68,0.18)',  text: '#fca5a5', shadow: 'none' };
    if (pct > -2)  return { bg: 'rgba(239,68,68,0.45)',  text: '#fecaca', shadow: 'none' };
    return { bg: 'rgba(239,68,68,0.85)', text: '#450a0a', shadow: '0 0 10px rgba(239,68,68,0.35)' };
  }

  return (
    <div className="bg-[#0d1117] border border-slate-800 rounded-xl px-4 py-3">
      <p className="text-[9px] text-slate-600 uppercase tracking-widest mb-3">סיבוב סקטורים</p>
      <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-2 gap-1.5">
        {sectors.map(s => {
          const style = blockStyle(s.pct);
          const shortName = s.name.replace('Consumer ', '').replace(' Services', '').replace(' Materials', '');
          return (
            <div key={s.sym} className="rounded-lg flex flex-col items-center gap-0.5 py-2 px-1 transition-transform hover:scale-105 cursor-default"
              style={{ background: style.bg, boxShadow: style.shadow }}>
              <span className="text-xl leading-none">{sectorIcon(s.name)}</span>
              <span className="text-[9px] text-center leading-tight font-medium" style={{ color: style.text }}>{shortName}</span>
              <span className="text-[11px] font-black tabular-nums" style={{ color: style.text }}>
                {s.pct >= 0 ? '+' : ''}{s.pct.toFixed(1)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Today's Events ────────────────────────────────────────────────────────────

function TodayEvents({ events }) {
  if (!events?.length) return null;
  return (
    <div className="bg-[#0d1117] border border-slate-800 rounded-xl px-5 py-3">
      <div className="flex items-center gap-2 mb-2">
        <Calendar size={11} className="text-slate-600" />
        <span className="text-[9px] text-slate-600 uppercase tracking-widest">אירועים קרובים</span>
      </div>
      <div className="space-y-1.5">
        {events.map((e, i) => (
          <div key={i} className="flex items-center gap-3 text-sm" dir="rtl">
            <span className="font-bold text-white">{e.ticker}</span>
            <span className="text-slate-600 text-xs">{e.catalyst_type}</span>
            <span className="text-slate-500 text-xs">{e.company}</span>
            {e.drug_name && <span className="text-slate-700 text-xs">— {e.drug_name}</span>}
            {e.days_until === 0 && (
              <span className="mr-auto text-xs text-yellow-400 font-bold animate-pulse">● היום</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Loading / Empty ───────────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center py-24 gap-4">
      <div className="relative">
        <div className="w-12 h-12 rounded-full border-2 border-slate-800" />
        <div className="absolute inset-0 w-12 h-12 rounded-full border-2 border-t-sky-500 animate-spin" />
      </div>
      <p className="text-slate-500 text-sm">סורק מניות... ~90 שניות</p>
    </div>
  );
}

function EmptyState({ onRefetch }) {
  return (
    <div className="flex flex-col items-center gap-4 py-16">
      <p className="text-slate-500 text-sm">לא נמצאו מניות</p>
      <button onClick={onRefetch} className="px-4 py-2 bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 rounded-lg text-sm transition-colors">
        רענן
      </button>
    </div>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

const SELF_LABEL = '☀️ בריפינג';

export default function DailyBriefing({ data, loading, onRefetch, crossScannerMap }) {
  const [sectorFilter, setSectorFilter] = useState('');

  const stocks       = data?.stocks || [];
  const marketStatus = data?.market_status || {};
  const todayEvents  = data?.today_events || [];
  const generatedAt  = data?.generated_at;
  const scanned      = data?.candidates_scanned;

  if ((loading || data?.loading) && !stocks.length) return <LoadingState />;

  const sectorCounts = stocks.reduce((acc, s) => {
    if (s.sector) acc[s.sector] = (acc[s.sector] || 0) + 1;
    return acc;
  }, {});
  const sectors = Object.keys(sectorCounts).sort();
  const filteredStocks = sectorFilter ? stocks.filter(s => s.sector === sectorFilter) : stocks;

  return (
    <div className="space-y-4">

      {/* ── Page header ── */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-black text-white tracking-tight">☀️ בריפינג יומי</h2>
          {generatedAt && (
            <p className="text-xs text-slate-600 mt-0.5">
              {new Date(generatedAt).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' })}
              {scanned && ` · ${scanned} מניות נסרקו`}
            </p>
          )}
        </div>
        <button onClick={onRefetch} disabled={loading}
          className="px-4 py-2 border text-sm flex items-center gap-2 rounded-lg disabled:opacity-40 transition-all"
          style={{ background: 'rgba(255,255,255,0.03)', borderColor: 'rgba(255,255,255,0.08)', color: '#64748b' }}
          onMouseEnter={e => (e.currentTarget.style.color = '#e2e8f0')}
          onMouseLeave={e => (e.currentTarget.style.color = '#64748b')}>
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          רענן
        </button>
      </div>

      {/* ── Market + Sector side-by-side ── */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-4">
        <div className="xl:col-span-3"><MarketStatus status={marketStatus} /></div>
        <div className="xl:col-span-2"><SectorHeatmap sectorPerf={marketStatus.sector_perf} /></div>
      </div>

      {/* ── Today events ── */}
      {todayEvents.length > 0 && <TodayEvents events={todayEvents} />}

      {/* ── Hot today ── */}
      <HotToday stocks={stocks} />

      {/* ── Sector filter ── */}
      {sectors.length > 1 && (
        <div className="flex items-center gap-1.5 flex-wrap">
          <button onClick={() => setSectorFilter('')}
            className={`px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all ${
              !sectorFilter ? 'bg-slate-700 text-white shadow' : 'text-slate-600 hover:text-slate-400'
            }`}>
            הכל ({stocks.length})
          </button>
          {sectors.map(sec => (
            <button key={sec} onClick={() => setSectorFilter(sectorFilter === sec ? '' : sec)}
              className={`px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all ${
                sectorFilter === sec ? 'bg-slate-700 text-white shadow' : 'text-slate-600 hover:text-slate-400'
              }`}>
              {sectorIcon(sec)} {sec} ({sectorCounts[sec]})
            </button>
          ))}
        </div>
      )}

      {/* ── Stock list ── */}
      {!filteredStocks.length ? <EmptyState onRefetch={onRefetch} /> : (
        <>
          {filteredStocks.slice(0, 5).map((stock, i) => (
            <StockCard key={stock.ticker} stock={stock} rank={i + 1}
              crossScanners={crossScannerMap?.[stock.ticker]?.filter(s => s !== SELF_LABEL)} />
          ))}

          {filteredStocks.length > 5 && (
            <div>
              {/* Table header */}
              <div className="flex items-center gap-3 px-4 py-2 border-b border-slate-800/60 text-[9px] text-slate-700 uppercase tracking-widest"
                style={{ background: '#0d1117', borderRadius: '0.5rem 0.5rem 0 0', borderTop: '1px solid rgba(255,255,255,0.05)' }}>
                <span className="w-6 text-center">#</span>
                <span className="w-10">score</span>
                <span className="w-16">טיקר</span>
                <span className="flex-1 hidden sm:block">חברה / סקטור</span>
                <span className="w-[90px] hidden md:block">20 יום</span>
                <span className="w-16 hidden lg:block">דוח</span>
                <span className="w-16">היום</span>
                <span className="w-20">מחיר</span>
                <span className="w-14 hidden xl:block">RS</span>
                <span className="shrink-0">היסטוריה</span>
                <span className="w-4" />
              </div>
              <div className="rounded-b-xl overflow-hidden border border-t-0 border-slate-800/60 divide-y divide-slate-800/40">
                {filteredStocks.slice(5).map((stock, i) => (
                  <CompactRow key={stock.ticker} stock={stock} rank={i + 6}
                    crossScanners={crossScannerMap?.[stock.ticker]?.filter(s => s !== SELF_LABEL)} />
                ))}
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
