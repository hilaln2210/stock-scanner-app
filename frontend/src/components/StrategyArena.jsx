import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';

/* ── CSS animations ──────────────────────────────────────────────────────── */
const STYLES = `
@keyframes leaderPulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(251,191,36,0), 0 0 20px rgba(251,191,36,0.12); border-color: rgba(251,191,36,0.5); }
  50%       { box-shadow: 0 0 0 5px rgba(251,191,36,0.2), 0 0 30px rgba(251,191,36,0.3);  border-color: rgba(251,191,36,0.95); }
}
@keyframes sessionPulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.55; }
}
@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-6px) scale(0.97); }
  to   { opacity: 1; transform: translateY(0) scale(1); }
}
@keyframes flashUp {
  0%   { background: rgba(74,222,128,0.35); }
  100% { background: transparent; }
}
@keyframes flashDown {
  0%   { background: rgba(248,113,113,0.35); }
  100% { background: transparent; }
}
.leader-card  { animation: leaderPulse 1.8s ease-in-out infinite; }
.session-dot  { animation: sessionPulse 1.4s ease-in-out infinite; }
.popover-enter { animation: fadeIn 0.15s ease-out; }
.flash-up   { animation: flashUp   0.7s ease-out; }
.flash-down { animation: flashDown 0.7s ease-out; }
`;

/* ── Constants ───────────────────────────────────────────────────────────── */
const W = '#4ade80', L = '#f87171', A = '#818cf8';
const GOLD = '#fbbf24', SILVER = '#94a3b8', BRONZE = '#f97316';
const RANK_COLORS = [GOLD, SILVER, BRONZE, L, '#64748b', '#64748b'];

const SESSION_META = {
  premarket:   { label: 'PRE-MARKET',  icon: '🌅', color: '#f59e0b', dot: '#f59e0b' },
  regular:     { label: 'LIVE',        icon: '📈', color: '#4ade80', dot: '#4ade80' },
  aftermarket: { label: 'AFTER-HOURS', icon: '🌙', color: '#818cf8', dot: '#818cf8' },
  closed:      { label: 'CLOSED',      icon: '💤', color: '#475569', dot: '#475569' },
};

const STRATEGY_META = {
  Balanced:        { emoji: '⚖️', color: '#60a5fa', bg: 'rgba(96,165,250,0.08)',  border: 'rgba(96,165,250,0.25)'  },
  HighConviction:  { emoji: '🎯', color: '#a78bfa', bg: 'rgba(167,139,250,0.08)', border: 'rgba(167,139,250,0.25)' },
  SqueezeHunter:   { emoji: '🔥', color: '#fb923c', bg: 'rgba(251,146,60,0.08)',  border: 'rgba(251,146,60,0.25)'  },
  Scalper:         { emoji: '⚡', color: '#34d399', bg: 'rgba(52,211,153,0.08)',  border: 'rgba(52,211,153,0.25)'  },
  MomentumBreaker: { emoji: '🚀', color: '#f43f5e', bg: 'rgba(244,63,94,0.08)',   border: 'rgba(244,63,94,0.25)'   },
  SwingSetup:      { emoji: '🌊', color: '#22d3ee', bg: 'rgba(34,211,238,0.08)', border: 'rgba(34,211,238,0.25)'  },
};

/* ── Strategy detailed info (for popover) ────────────────────────────────── */
const STRATEGY_INFO = {
  Balanced: {
    style: 'כניסות מאוזנות לשוק נורמלי — לא קיצוני, לא שמרני',
    rules: ['Health ≥ 40 | Confidence ≥ 45', 'rvol ≥ 0.5 — נפח סביר', 'שינוי יומי מקס׳ 8%'],
    exit:  ['Stop 4% | Target 12%', 'Trailing stop מ-4% | TP חלקי ב-5%', 'סגירה אחרי 2 ימים אם < +2%'],
    max_positions: 3, stop_pct: 4.0, target_pct: 12.0,
  },
  HighConviction: {
    style: 'רק הכי טובים — פחות עסקאות, R:R גבוה יותר',
    rules: ['Health ≥ 55 | Confidence ≥ 58', 'rvol ≥ 0.8 — נפח גבוה', 'שינוי יומי מקס׳ 5%'],
    exit:  ['Stop 3.5% | Target 17.5%', 'Trailing stop מ-4% | TP חלקי ב-5%', 'סגירה אחרי 2 ימים אם < +2%'],
    max_positions: 2, stop_pct: 3.5, target_pct: 17.5,
  },
  SqueezeHunter: {
    style: 'מחפשת מניות עם שורט גבוה — לחץ כיסוי שורטים',
    rules: ['Health ≥ 35 | Confidence ≥ 40', 'Short Float ≥ 8% — חובה', 'rvol ≥ 0.5 | ללא מגבלת שינוי'],
    exit:  ['Stop 4% | Target 20%', 'Trailing stop מ-4% | TP חלקי ב-5%', 'סגירה אחרי 2 ימים אם < +2%'],
    max_positions: 3, stop_pct: 4.0, target_pct: 20.0,
  },
  Scalper: {
    style: 'כניסות אגרסיביות עם סיכון גבוה — יעדי רווח גדולים',
    rules: ['Health ≥ 22 | Confidence ≥ 25 — threshold נמוך', 'rvol ≥ 0.6 | שינוי מינימלי 0.1%', 'ללא מגבלת שינוי יומי'],
    exit:  ['Stop 4.5% | Target 14%', 'Trailing צמוד מ-6% (4% מהשיא)', 'TP חלקי ב-8% — נשאר זמן יותר'],
    max_positions: 3, stop_pct: 4.5, target_pct: 14.0,
  },
  MomentumBreaker: {
    style: 'פורצים עם נפח חריג — מחפש ספייקים אמיתיים',
    rules: ['Health ≥ 30 | Confidence ≥ 35', 'rvol ≥ 1.8 — נפח חריג, חובה', 'שינוי > 1% | שינוי מקס׳ 20%'],
    exit:  ['Stop 3.5% | Target 10%', 'Trailing stop מ-4% | TP חלקי ב-5%', 'סגירה אחרי 2 ימים אם < +2%'],
    max_positions: 3, stop_pct: 3.5, target_pct: 10.0,
  },
  SwingSetup: {
    style: 'כניסות איכותיות, יעדים גדולים — סבלנות ומשמעת',
    rules: ['Health ≥ 50 | Confidence ≥ 50 — איכות גבוהה', 'rvol ≥ 0.4 | שינוי יומי מקס׳ 4%', 'ללא תנאי מינימום שינוי'],
    exit:  ['Stop 5% | Target 18%', 'Trailing stop מ-4% | TP חלקי ב-5%', 'סגירה אחרי 2 ימים אם < +2%'],
    max_positions: 2, stop_pct: 5.0, target_pct: 18.0,
  },
};

const DAYS_HE = { Monday: 'שני', Tuesday: 'שלישי', Wednesday: 'רביעי', Thursday: 'חמישי', Friday: 'שישי' };
const INITIAL_CAPITAL = 1000;

/* ── Helpers ─────────────────────────────────────────────────────────────── */
function timeAgo(isoStr) {
  if (!isoStr) return '';
  const diff = (Date.now() - new Date(isoStr).getTime()) / 60000;
  if (diff < 60)  return `${Math.floor(diff)}ד׳`;
  if (diff < 1440) return `${Math.floor(diff / 60)}ש׳`;
  return `${Math.floor(diff / 1440)}י׳`;
}

/* ── InfoPopover ─────────────────────────────────────────────────────────── */
function InfoPopover({ name, type, onClose }) {
  const info = STRATEGY_INFO[name];
  const meta = STRATEGY_META[name] || { color: A };
  if (!info) return null;

  const slotSize = Math.round(INITIAL_CAPITAL / info.max_positions);
  const rr       = (info.target_pct / info.stop_pct).toFixed(1);

  return (
    <div
      className="popover-enter"
      onClick={e => e.stopPropagation()}
      style={{
        position: 'absolute', top: 40, left: 0, zIndex: 999, width: 240,
        background: '#0f172a', border: `1px solid ${meta.color}40`,
        borderRadius: 10, padding: '12px 14px', boxShadow: '0 8px 32px rgba(0,0,0,0.7)',
      }}
    >
      <button onClick={onClose} style={{
        position: 'absolute', top: 6, right: 8, background: 'none', border: 'none',
        color: '#475569', cursor: 'pointer', fontSize: 14, lineHeight: 1,
      }}>✕</button>

      {type === 'method' ? (
        <>
          <div style={{ fontSize: 11, fontWeight: 800, color: meta.color, marginBottom: 6 }}>
            {meta.emoji} שיטה
          </div>
          <div style={{ fontSize: 10, color: '#94a3b8', marginBottom: 8, lineHeight: 1.5 }}>
            {info.style}
          </div>
          <div style={{ fontSize: 9, fontWeight: 700, color: '#475569', marginBottom: 4 }}>כניסה</div>
          {info.rules.map((r, i) => (
            <div key={i} style={{ fontSize: 10, color: '#cbd5e1', marginBottom: 3, display: 'flex', gap: 5 }}>
              <span style={{ color: meta.color }}>›</span> {r}
            </div>
          ))}
          <div style={{ fontSize: 9, fontWeight: 700, color: '#475569', margin: '8px 0 4px' }}>יציאה</div>
          {info.exit.map((r, i) => (
            <div key={i} style={{ fontSize: 10, color: '#cbd5e1', marginBottom: 3, display: 'flex', gap: 5 }}>
              <span style={{ color: '#f87171' }}>›</span> {r}
            </div>
          ))}
        </>
      ) : (
        <>
          <div style={{ fontSize: 11, fontWeight: 800, color: meta.color, marginBottom: 10 }}>
            📊 גודל פוזיציה
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {[
              { label: 'פוזיציות מקס׳', value: info.max_positions, unit: '' },
              { label: 'הון לכל מניה', value: `$${slotSize}`, unit: '' },
              { label: 'סטופ לוס', value: info.stop_pct, unit: '%' },
              { label: 'יעד רווח', value: info.target_pct, unit: '%' },
              { label: 'יחס R:R', value: `1:${rr}`, unit: '', wide: true },
            ].map((m, i) => (
              <div key={i} style={{
                gridColumn: m.wide ? '1 / -1' : undefined,
                background: '#1e293b', borderRadius: 7, padding: '7px 10px', textAlign: 'center',
              }}>
                <div style={{ fontSize: 14, fontWeight: 900, color: meta.color, fontFamily: 'monospace' }}>
                  {m.value}{m.unit}
                </div>
                <div style={{ fontSize: 9, color: '#475569', marginTop: 2 }}>{m.label}</div>
              </div>
            ))}
          </div>
          <div style={{
            marginTop: 10, padding: '7px 10px', borderRadius: 7,
            background: 'rgba(251,191,36,0.07)', border: '1px solid rgba(251,191,36,0.2)',
            fontSize: 10, color: '#fbbf24', textAlign: 'center',
          }}>
            הפסד מקסימלי לפוזיציה: ~${Math.round(slotSize * info.stop_pct / 100)}
            &nbsp;|&nbsp;
            רווח מקסימלי: ~${Math.round(slotSize * info.target_pct / 100)}
          </div>
        </>
      )}
    </div>
  );
}

/* ── MiniSparkline ───────────────────────────────────────────────────────── */
function MiniSparkline({ history = [] }) {
  if (history.length < 2) return null;
  const vals = history.map(h => h.equity);
  const mn = Math.min(...vals), mx = Math.max(...vals), range = mx - mn || 1;
  const WW = 80, HH = 28, pad = 2;
  const pts = vals.map((v, i) =>
    `${pad + (i / (vals.length - 1)) * (WW - pad * 2)},${pad + (HH - pad * 2) - ((v - mn) / range) * (HH - pad * 2)}`
  ).join(' ');
  const isUp = vals[vals.length - 1] >= vals[0];
  return (
    <svg width={WW} height={HH} viewBox={`0 0 ${WW} ${HH}`} style={{ display: 'block' }}>
      <polyline points={pts} fill="none" stroke={isUp ? W : L} strokeWidth={1.5} strokeLinejoin="round" />
      <circle
        cx={pad + WW - pad * 2}
        cy={pad + (HH - pad * 2) - ((vals[vals.length - 1] - mn) / range) * (HH - pad * 2)}
        r={2.5} fill={isUp ? W : L}
      />
    </svg>
  );
}

/* ── StrategyCard ────────────────────────────────────────────────────────── */
function StrategyCard({ strategy, rank, isLeader, livePrices = {}, flashState = {} }) {
  const [popover, setPopover] = useState(null); // 'method' | 'sizing' | null
  const cardRef  = useRef(null);
  const meta     = STRATEGY_META[strategy.name] || { emoji: '📊', color: A, bg: 'rgba(129,140,248,0.08)', border: 'rgba(129,140,248,0.25)' };
  const info     = STRATEGY_INFO[strategy.name];
  const pnlPct   = strategy.pnl_pct ?? 0;
  const posCount = Object.keys(strategy.positions || {}).length;
  const rankColor = RANK_COLORS[rank] ?? SILVER;
  const rr        = info ? (info.target_pct / info.stop_pct).toFixed(1) : '—';

  // Close popover when clicking outside
  useEffect(() => {
    if (!popover) return;
    const handler = (e) => { if (cardRef.current && !cardRef.current.contains(e.target)) setPopover(null); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [popover]);

  const togglePop = (type) => setPopover(p => p === type ? null : type);

  return (
    <div
      ref={cardRef}
      className={isLeader ? 'leader-card' : ''}
      style={{
        background: isLeader
          ? 'linear-gradient(135deg, rgba(251,191,36,0.09) 0%, rgba(30,27,75,0.95) 100%)'
          : `linear-gradient(135deg, ${meta.bg} 0%, rgba(13,17,23,0.95) 100%)`,
        border: `1px solid ${isLeader ? 'rgba(251,191,36,0.5)' : meta.border}`,
        borderRadius: 12, padding: '14px 16px', position: 'relative',
      }}
    >
      {/* Rank badge */}
      <div style={{
        position: 'absolute', top: 10, right: 12,
        fontSize: 11, fontWeight: 900, color: rankColor,
        background: `${rankColor}18`, border: `1px solid ${rankColor}40`,
        borderRadius: 6, padding: '2px 8px',
      }}>
        #{rank + 1}{isLeader && <span style={{ marginLeft: 4 }}>👑</span>}
      </div>

      {/* Name row + info buttons */}
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8, marginBottom: 10, paddingRight: 56 }}>
        <span style={{ fontSize: 22 }}>{meta.emoji}</span>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: 13, fontWeight: 800, color: meta.color }}>{strategy.label}</div>
          <div style={{ fontSize: 9, color: '#475569', marginTop: 1 }}>{strategy.description || ''}</div>
          {/* Info buttons */}
          <div style={{ display: 'flex', gap: 5, marginTop: 6, position: 'relative' }}>
            <button
              onClick={() => togglePop('method')}
              title="שיטת מסחר"
              style={{
                fontSize: 9, padding: '2px 7px', borderRadius: 5, cursor: 'pointer', fontWeight: 700,
                background: popover === 'method' ? `${meta.color}25` : 'rgba(255,255,255,0.05)',
                border: `1px solid ${popover === 'method' ? meta.color + '60' : 'rgba(255,255,255,0.1)'}`,
                color: popover === 'method' ? meta.color : '#94a3b8',
              }}
            >
              ? שיטה
            </button>
            <button
              onClick={() => togglePop('sizing')}
              title="גודל פוזיציה"
              style={{
                fontSize: 9, padding: '2px 7px', borderRadius: 5, cursor: 'pointer', fontWeight: 700,
                background: popover === 'sizing' ? `${meta.color}25` : 'rgba(255,255,255,0.05)',
                border: `1px solid ${popover === 'sizing' ? meta.color + '60' : 'rgba(255,255,255,0.1)'}`,
                color: popover === 'sizing' ? meta.color : '#94a3b8',
              }}
            >
              📊 פוזיציה
            </button>
            {/* R:R badge */}
            <div style={{
              fontSize: 9, padding: '2px 7px', borderRadius: 5, fontFamily: 'monospace', fontWeight: 700,
              background: 'rgba(251,191,36,0.07)', border: '1px solid rgba(251,191,36,0.2)', color: GOLD,
            }}>
              1:{rr}
            </div>

            {/* Popover */}
            {popover && (
              <InfoPopover name={strategy.name} type={popover} onClose={() => setPopover(null)} />
            )}
          </div>
        </div>
      </div>

      {/* Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 10 }}>
        {[
          { v: `${pnlPct >= 0 ? '+' : ''}${pnlPct.toFixed(2)}%`, l: 'שבועי', c: pnlPct >= 0 ? W : L, big: true },
          { v: `$${(strategy.equity ?? 1000).toFixed(0)}`, l: 'הון', c: '#f8fafc' },
          { v: strategy.total_trades > 0 ? `${strategy.win_rate?.toFixed(0)}%` : '—', l: 'הצלחה', c: strategy.win_rate >= 50 ? W : strategy.total_trades > 0 ? L : '#94a3b8' },
        ].map((s, i) => (
          <div key={i} style={{ textAlign: 'center' }}>
            <div style={{ fontSize: s.big ? 18 : 15, fontFamily: 'monospace', fontWeight: 900, color: s.c }}>{s.v}</div>
            <div style={{ fontSize: 8, color: '#475569' }}>{s.l}</div>
          </div>
        ))}
      </div>

      {/* Sparkline + stats */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <MiniSparkline history={strategy.equity_history || []} />
        <div style={{ textAlign: 'right', fontSize: 10, color: '#64748b' }}>
          {strategy.total_trades} עסקאות · {posCount} פתוחות
          {(strategy.day_wins ?? 0) > 0 && (
            <div style={{ color: GOLD, fontWeight: 700 }}>{strategy.day_wins} ניצחון{strategy.day_wins > 1 ? 'ות' : ''} שבועיים</div>
          )}
        </div>
      </div>

      {/* Open positions */}
      {posCount > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {Object.entries(strategy.positions || {}).map(([ticker, pos]) => {
            const liveData  = livePrices[ticker];
            const livePrice = liveData?.price ?? null;
            const entry     = pos.entry_price ?? 0;
            const ppnl      = livePrice && entry > 0
              ? (livePrice - entry) / entry * 100
              : (pos.pnl_pct ?? 0);
            const changePct = liveData?.change_pct ?? null;
            const age       = timeAgo(pos.entry_time);
            const trail     = pos.trailing;
            const sess      = pos.session;
            const flashCls  = flashState[ticker] === 'up'   ? 'flash-up'
                            : flashState[ticker] === 'down' ? 'flash-down' : '';
            return (
              <div key={ticker} className={flashCls} style={{
                fontSize: 10, fontWeight: 700, padding: '4px 8px', borderRadius: 6,
                background: ppnl >= 0 ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)',
                border: `1px solid ${ppnl >= 0 ? '#166534' : '#7f1d1d'}`,
                color: ppnl >= 0 ? W : L, fontFamily: 'monospace',
              }}>
                {/* Ticker + P&L */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ fontWeight: 900 }}>{ticker}</span>
                  <span>{ppnl >= 0 ? '+' : ''}{ppnl.toFixed(2)}%</span>
                  {trail && <span title="Trailing active" style={{ fontSize: 8 }}>🔒</span>}
                  {sess && sess !== 'regular' && (
                    <span style={{ fontSize: 8, opacity: 0.7 }}>
                      {sess === 'premarket' ? '🌅' : '🌙'}
                    </span>
                  )}
                </div>
                {/* Live price + change */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 4, marginTop: 2 }}>
                  {livePrice && (
                    <span style={{ fontSize: 11, fontWeight: 900, color: '#f8fafc' }}>
                      ${livePrice.toFixed(2)}
                    </span>
                  )}
                  {changePct !== null && (
                    <span style={{
                      fontSize: 9,
                      color: String(changePct).startsWith('-') ? L : W,
                    }}>
                      {String(changePct).startsWith('-') ? '▼' : '▲'} {String(changePct).replace(/[+-]/, '')}
                    </span>
                  )}
                  {age && <span style={{ fontSize: 8, opacity: 0.45, fontFamily: 'sans-serif' }}>{age}</span>}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Dollar P&L */}
      {(strategy.total_pnl ?? 0) !== 0 && (
        <div style={{ marginTop: 6, fontSize: 10, fontFamily: 'monospace', color: (strategy.total_pnl ?? 0) >= 0 ? W : L }}>
          {(strategy.total_pnl ?? 0) >= 0 ? '+' : ''}${(strategy.total_pnl ?? 0).toFixed(1)}
        </div>
      )}
    </div>
  );
}

/* ── WeeklyHistory ───────────────────────────────────────────────────────── */
function WeeklyHistory({ history = [], strategies = [] }) {
  if (!history.length) return null;
  return (
    <div style={{
      marginTop: 16, padding: '14px 16px', borderRadius: 10,
      background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)',
    }}>
      <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', marginBottom: 10 }}>
        📅 היסטוריה שבועית
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 10 }}>
          <thead>
            <tr>
              <th style={{ textAlign: 'left', color: '#475569', padding: '4px 8px', fontWeight: 600 }}>יום</th>
              <th style={{ textAlign: 'left', color: '#475569', padding: '4px 8px', fontWeight: 600 }}>מנצחת</th>
              {strategies.map(s => {
                const meta = STRATEGY_META[s.name] || { emoji: '📊', color: A };
                return (
                  <th key={s.name} style={{ textAlign: 'center', color: meta.color, padding: '4px 6px', fontWeight: 700, whiteSpace: 'nowrap' }}>
                    {meta.emoji}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {history.map((day, i) => {
              const dayHe = DAYS_HE[day.weekday] || day.weekday || day.date?.slice(5);
              return (
                <tr key={i} style={{ borderTop: '1px solid rgba(255,255,255,0.04)' }}>
                  <td style={{ padding: '5px 8px', color: '#94a3b8', fontWeight: 600 }}>{dayHe}</td>
                  <td style={{ padding: '5px 8px' }}>
                    <span style={{
                      fontSize: 11, fontWeight: 800,
                      color: STRATEGY_META[day.winner]?.color || GOLD,
                    }}>
                      {STRATEGY_META[day.winner]?.emoji} {day.label?.replace(/^[^\s]+ /, '') || day.winner}
                    </span>
                  </td>
                  {strategies.map(s => {
                    const pct = (day.pnl_pcts || {})[s.name] ?? null;
                    const isWinner = day.winner === s.name;
                    return (
                      <td key={s.name} style={{ textAlign: 'center', padding: '5px 6px' }}>
                        {pct !== null ? (
                          <span style={{
                            fontFamily: 'monospace', fontWeight: isWinner ? 900 : 600,
                            color: pct >= 0 ? W : L,
                            fontSize: isWinner ? 12 : 10,
                          }}>
                            {isWinner && '★ '}{pct >= 0 ? '+' : ''}{pct.toFixed(1)}%
                          </span>
                        ) : <span style={{ color: '#334155' }}>—</span>}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Main Component ──────────────────────────────────────────────────────── */
export default function StrategyArena() {
  const [data, setData]             = useState(null);
  const [loading, setLoading]       = useState(true);
  const [thinking, setThinking]     = useState(false);
  const [declaring, setDeclaring]   = useState(false);
  const [lastMsg, setLastMsg]       = useState(null);
  const [countdown, setCountdown]   = useState('');
  const [sessionLabel, setSessionLabel] = useState('');
  const [livePrices, setLivePrices]       = useState({});   // {HIMS: {price, change_pct}, ...}
  const [flashState, setFlashState]       = useState({});   // {HIMS: 'up'|'down'}
  const [lastPriceUpdate, setLastPriceUpdate] = useState(null);
  const prevPricesRef = useRef({});
  const flashTimers   = useRef({});

  const fetchStatus = async () => {
    try {
      const r = await axios.get('/api/smart-portfolio/arena/status');
      setData(r.data);
    } catch { /* silent */ } finally { setLoading(false); }
  };

  // Fetch live prices for all open positions every 30s
  const fetchLivePrices = useCallback(async (currentData) => {
    const d = currentData;
    if (!d?.leaderboard) return;
    const tickers = new Set();
    d.leaderboard.forEach(s => Object.keys(s.positions || {}).forEach(t => tickers.add(t)));
    if (!tickers.size) return;
    try {
      const r = await axios.get(`/api/screener/live-prices?tickers=${[...tickers].join(',')}`);
      const fresh = r.data || {};
      // Detect changes → trigger flash
      const newFlash = {};
      Object.entries(fresh).forEach(([ticker, info]) => {
        const newP = info?.price;
        const oldP = prevPricesRef.current[ticker]?.price;
        if (newP && oldP && Math.abs(newP - oldP) > 0.001) {
          newFlash[ticker] = newP > oldP ? 'up' : 'down';
          // Auto-clear flash after 800ms
          clearTimeout(flashTimers.current[ticker]);
          flashTimers.current[ticker] = setTimeout(() => {
            setFlashState(prev => { const n = { ...prev }; delete n[ticker]; return n; });
          }, 800);
        }
        prevPricesRef.current[ticker] = info;
      });
      if (Object.keys(newFlash).length) setFlashState(prev => ({ ...prev, ...newFlash }));
      setLivePrices(prev => ({ ...prev, ...fresh }));
      setLastPriceUpdate(new Date());
    } catch { /* silent */ }
  }, []);

  // Countdown + session label (local ET approximation)
  useEffect(() => {
    const tick = () => {
      const now  = new Date();
      const utcH = now.getUTCHours() + (3 <= now.getMonth() + 1 && now.getMonth() + 1 <= 11 ? -4 : -5);
      const etH  = ((utcH % 24) + 24) % 24;
      const etM  = now.getUTCMinutes();
      const total = etH * 60 + etM;
      const dow   = ((now.getUTCDay() + (utcH < 0 ? -1 : 0)) + 7) % 7;

      if (dow === 0 || dow === 6) { setCountdown('סוף שבוע'); setSessionLabel('closed'); return; }
      if (total >= 4 * 60 && total < 9 * 60 + 25) {
        setSessionLabel('premarket');
        const diff = 9 * 60 + 25 - total;
        setCountdown(`${Math.floor(diff / 60)}ש' ${diff % 60}ד' לפתיחה`);
      } else if (total >= 9 * 60 + 25 && total < 16 * 60 + 5) {
        setSessionLabel('regular');
        const diff = 16 * 60 + 5 - total;
        setCountdown(Math.floor(diff / 60) > 0 ? `${Math.floor(diff / 60)}ש' ${diff % 60}ד' לסגירה` : `${diff % 60} דקות לסגירה`);
      } else if (total >= 16 * 60 + 5 && total < 20 * 60) {
        setSessionLabel('aftermarket');
        const diff = 20 * 60 - total;
        setCountdown(`${diff} דקות לסיום after`);
      } else {
        setSessionLabel('closed');
        setCountdown('השוק סגור');
      }
    };
    tick();
    const iv = setInterval(tick, 30000);
    return () => clearInterval(iv);
  }, []);

  useEffect(() => {
    fetchStatus();
    const iv = setInterval(fetchStatus, 15000);
    return () => clearInterval(iv);
  }, []);

  // Live price polling — every 30s, fetch fresh prices for open positions
  useEffect(() => {
    if (!data) return;
    fetchLivePrices(data);
    const iv = setInterval(() => fetchLivePrices(data), 30000);
    return () => clearInterval(iv);
  }, [data, fetchLivePrices]);

  const triggerThink = async () => {
    setThinking(true); setLastMsg(null);
    try {
      const r = await axios.post('/api/smart-portfolio/arena/think');
      setLastMsg({ ok: true, text: `✅ עדכון הצליח · ${r.data?.tick_count ?? ''} ticks` });
      fetchStatus();
    } catch (e) { setLastMsg({ ok: false, text: e.message }); }
    setThinking(false);
  };

  const declareDaily = async () => {
    if (!confirm('להכריז על מנצחת היום?')) return;
    setDeclaring(true); setLastMsg(null);
    try {
      const r = await axios.post('/api/smart-portfolio/arena/declare-daily-winner');
      const w = r.data?.winner;
      setLastMsg({ ok: true, text: `🏆 מנצחת: ${w || '?'}` });
      fetchStatus();
    } catch (e) { setLastMsg({ ok: false, text: e.message }); }
    setDeclaring(false);
  };

  if (loading) return <div style={{ padding: 60, textAlign: 'center', color: '#475569' }}>טוען ארנה...</div>;
  if (!data)   return <div style={{ padding: 40, textAlign: 'center', color: L }}>שגיאה בטעינת ארנה</div>;

  const strategies = (data.leaderboard || []).map(s => ({
    ...s,
    total_trades: s.trades ?? s.total_trades ?? 0,
    total_pnl:    s.pnl   ?? s.total_pnl   ?? 0,
    equity_history: s.equity_history || [],
  }));
  const sorted       = [...strategies].sort((a, b) => (b.pnl_pct ?? 0) - (a.pnl_pct ?? 0));
  const leaderName   = sorted[0]?.name;
  const totalInitial = strategies.length * INITIAL_CAPITAL;
  const totalEquity  = strategies.reduce((sum, s) => sum + (s.equity ?? INITIAL_CAPITAL), 0);
  const totalReturn  = totalInitial > 0 ? ((totalEquity - totalInitial) / totalInitial * 100) : 0;

  const apiSession = data.session || sessionLabel;
  const sm = SESSION_META[apiSession] || SESSION_META.closed;

  return (
    <div style={{ padding: '16px', maxWidth: 980, margin: '0 auto' }}>
      <style>{STYLES}</style>

      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14, flexWrap: 'wrap', gap: 10 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ fontSize: 26 }}>🏆</span>
          <div>
            <h2 style={{ fontSize: 20, fontWeight: 900, color: '#f8fafc', margin: 0 }}>Strategy Arena</h2>
            <div style={{ fontSize: 10, color: '#475569' }}>
              6 אסטרטגיות מתחרות כל השבוע · מנצחת יומית 16:05 · מנצחת שבועית שישי
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6,
            fontSize: 11, fontWeight: 800, padding: '5px 10px', borderRadius: 8,
            background: `${sm.color}12`, border: `1px solid ${sm.color}40`, color: sm.color,
          }}>
            <span className={apiSession !== 'closed' ? 'session-dot' : ''}
              style={{ width: 7, height: 7, borderRadius: '50%', background: sm.dot, display: 'inline-block' }} />
            {sm.icon} {sm.label}
          </div>
          {countdown && (
            <div style={{ fontSize: 10, fontWeight: 600, padding: '4px 8px', borderRadius: 6, background: 'rgba(251,191,36,0.08)', border: '1px solid rgba(251,191,36,0.25)', color: GOLD }}>
              ⏰ {countdown}
            </div>
          )}
          {lastPriceUpdate && (
            <div style={{ fontSize: 9, padding: '4px 8px', borderRadius: 6, background: 'rgba(74,222,128,0.07)', border: '1px solid rgba(74,222,128,0.2)', color: '#4ade80', fontFamily: 'monospace' }}>
              📡 {lastPriceUpdate.toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
            </div>
          )}
          <button onClick={triggerThink} disabled={thinking} style={{
            fontSize: 11, padding: '6px 14px', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: 700,
            background: thinking ? '#1e1b4b' : 'linear-gradient(135deg,#4338ca,#6366f1)', color: '#fff', opacity: thinking ? 0.6 : 1,
          }}>
            {thinking ? '⏳ חושב...' : '🧠 עדכן'}
          </button>
          <button onClick={declareDaily} disabled={declaring} style={{
            fontSize: 11, padding: '6px 12px', borderRadius: 8, cursor: 'pointer', fontWeight: 700,
            background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.35)', color: GOLD, opacity: declaring ? 0.6 : 1,
          }}>
            {declaring ? '⏳...' : '🏆 הכרז מנצחת יום'}
          </button>
        </div>
      </div>

      {/* ── Last message ── */}
      {lastMsg && (
        <div style={{
          marginBottom: 12, padding: '8px 14px', borderRadius: 8, fontSize: 11, fontWeight: 600,
          background: lastMsg.ok ? 'rgba(74,222,128,0.08)' : 'rgba(248,113,113,0.08)',
          border: `1px solid ${lastMsg.ok ? '#166534' : '#7f1d1d'}`,
          color: lastMsg.ok ? W : L,
        }}>
          {lastMsg.text}
        </div>
      )}

      {/* ── Weekly winner ── */}
      {data.weekly_winner && (
        <div style={{
          marginBottom: 14, padding: '12px 16px', borderRadius: 12,
          background: 'linear-gradient(135deg,rgba(251,191,36,0.1),rgba(30,27,75,0.9))',
          border: '1px solid rgba(251,191,36,0.5)', display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <span style={{ fontSize: 30 }}>🏆</span>
          <div>
            <div style={{ fontSize: 14, fontWeight: 900, color: GOLD }}>{data.weekly_winner.label} — מנצחת השבוע!</div>
            <div style={{ fontSize: 10, color: '#94a3b8' }}>
              תשואה שבועית: {data.weekly_winner.pnl_pct >= 0 ? '+' : ''}{data.weekly_winner.pnl_pct?.toFixed(2)}%
              · הוחל על התיק הראשי ✅
            </div>
          </div>
        </div>
      )}

      {/* ── Stats bar ── */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 14,
        padding: '10px 14px', borderRadius: 10, background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)',
      }}>
        {[
          { label: 'הון כולל',      value: `$${totalEquity.toFixed(0)}`,                                                          color: '#f8fafc', icon: '💰' },
          { label: 'תשואה שבועית',  value: `${totalReturn >= 0 ? '+' : ''}${totalReturn.toFixed(2)}%`,                           color: totalReturn >= 0 ? W : L, icon: totalReturn >= 0 ? '📈' : '📉' },
          { label: 'מנהיגה כרגע',   value: sorted[0]?.label?.replace(/^[^\s]+ /, '').split(' ')[0] || '—',                       color: GOLD, icon: '👑' },
          { label: 'ימי ניצחון',    value: data.daily_history?.length > 0 ? `${data.daily_history.length} ימים` : 'שבוע ראשון', color: A, icon: '📅' },
        ].map((s, i) => (
          <div key={i} style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 9, color: '#475569', marginBottom: 2 }}>{s.icon} {s.label}</div>
            <div style={{ fontSize: 13, fontFamily: 'monospace', fontWeight: 900, color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* ── Strategy cards ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 12 }}>
        {sorted.map((strategy, rank) => (
          <StrategyCard
            key={strategy.name}
            strategy={strategy}
            rank={rank}
            isLeader={strategy.name === leaderName && rank === 0}
            livePrices={livePrices}
            flashState={flashState}
          />
        ))}
      </div>

      {/* ── Performance bars ── */}
      <div style={{ marginTop: 14, padding: '12px 16px', borderRadius: 10, background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)' }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', marginBottom: 10 }}>השוואת ביצועים שבועיים</div>
        {sorted.map((s, i) => {
          const meta   = STRATEGY_META[s.name] || { color: A };
          const pct    = s.pnl_pct ?? 0;
          const maxPct = Math.max(...strategies.map(x => Math.abs(x.pnl_pct ?? 0)), 0.1);
          return (
            <div key={s.name} style={{ marginBottom: 6 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 3 }}>
                <span style={{ color: meta.color, fontWeight: 700 }}>
                  <span style={{ color: RANK_COLORS[i] }}>#{i + 1} </span>
                  {meta.emoji} {s.label?.replace(/^[^\s]+ /, '')}
                </span>
                <span style={{ fontFamily: 'monospace', fontWeight: 800, color: pct >= 0 ? W : L }}>
                  {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                </span>
              </div>
              <div style={{ height: 6, background: '#1e293b', borderRadius: 3, overflow: 'hidden' }}>
                <div style={{
                  height: '100%', width: `${Math.abs(pct) / maxPct * 100}%`,
                  background: pct >= 0 ? meta.color : L, borderRadius: 3, transition: 'width 0.6s ease',
                }} />
              </div>
            </div>
          );
        })}
      </div>

      {/* ── Weekly history table ── */}
      <WeeklyHistory history={data.daily_history || []} strategies={sorted} />

      {/* ── Footer ── */}
      <div style={{ marginTop: 12, fontSize: 9, color: '#334155', textAlign: 'center' }}>
        עדכון כל 15 שניות · פועל בפרי-מרקט / מסחר / אפטר-מרקט · מנצחת יום: 16:05 · מנצחת שבוע: שישי 16:05 · פרמטרים → AI ראשי
      </div>
    </div>
  );
}
