/**
 * FinvizTableScanner
 * - Finviz-style fundamental screener table
 * - Shows move reason badges + expandable news per stock
 * - Auto-refreshes every 30 seconds with live countdown
 */
import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const api = axios.create({ baseURL: '/api' });

// ── Filter options ─────────────────────────────────────────────────────────────
const MCAP_OPTS = [
  { label: 'Mid+ ($2B+)',     value: 'cap_midover' },
  { label: 'Large+ ($10B+)', value: 'cap_largeover' },
  { label: 'Mega ($200B+)',   value: 'cap_mega' },
  { label: 'Small+ ($300M+)',value: 'cap_smallover' },
  { label: 'All',             value: '' },
];
const VOL_OPTS = [
  { label: 'Avg Vol >2M',   value: 'sh_avgvol_o2000' },
  { label: 'Avg Vol >1M',   value: 'sh_avgvol_o1000' },
  { label: 'Avg Vol >500K', value: 'sh_avgvol_o500' },
  { label: 'Any',           value: '' },
];
const CHANGE_OPTS = [
  { label: '+4%+ Open',  value: 'ta_changeopen_u4' },
  { label: '+2%+ Open',  value: 'ta_changeopen_u2' },
  { label: '+3%+ Day',   value: 'ta_change_u3' },
  { label: '+5%+ Day',   value: 'ta_change_u5' },
  { label: 'Any',        value: '' },
];
const SHORT_OPTS = [
  { label: 'Short >5%',  value: 'sh_short_o5' },
  { label: 'Short >10%', value: 'sh_short_o10' },
  { label: 'Short >20%', value: 'sh_short_o20' },
  { label: 'Any',        value: '' },
];
const RSI_OPTS = [
  { label: 'RSI >50',        value: 'ta_rsi_nos50' },
  { label: 'RSI Overbought', value: 'ta_rsi_ob70' },
  { label: 'Any',            value: '' },
];
const INST_OPTS = [
  { label: 'Inst >10%', value: 'sh_instown_o10' },
  { label: 'Inst >30%', value: 'sh_instown_o30' },
  { label: 'Any',       value: '' },
];

function buildFilters(mcap, vol, change, shortf, rsi, inst) {
  return [mcap, vol, 'sh_curvol_o0', change, shortf, rsi, inst]
    .filter(Boolean).join(',');
}

// ── Move reason colors ─────────────────────────────────────────────────────────
const REASON_STYLE = {
  earnings:  { bg: '#0c2a1a', border: '#166534', text: '#4ade80' },
  results:   { bg: '#0c2a1a', border: '#166534', text: '#4ade80' },
  upgrade:   { bg: '#0f2027', border: '#1d4ed8', text: '#60a5fa' },
  downgrade: { bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  fda:       { bg: '#1a0a2e', border: '#6b21a8', text: '#c084fc' },
  ma:        { bg: '#1c1000', border: '#78350f', text: '#fb923c' },
  guidance:  { bg: '#0f1a1a', border: '#0e7490', text: '#22d3ee' },
  contract:  { bg: '#1a1500', border: '#92400e', text: '#fbbf24' },
  risk:      { bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  dilution:  { bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  gap:       { bg: '#0c1a0c', border: '#14532d', text: '#86efac' },
  technical: { bg: '#12121a', border: '#374151', text: '#9ca3af' },
};

// ── Fundamental tag styles ─────────────────────────────────────────────────────
const TAG_META = {
  profitable:  { label: '✅ Profitable', bg: '#0c2a1a', border: '#166534', text: '#4ade80' },
  loss:        { label: '❌ Loss',        bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  high_debt:   { label: '⚠️ High Debt',  bg: '#1c1000', border: '#78350f', text: '#fb923c' },
  cash_rich:   { label: '💰 Cash-Rich',  bg: '#0c1a2e', border: '#1e40af', text: '#60a5fa' },
  high_growth: { label: '🔥 Growth',     bg: '#1a0a2e', border: '#6b21a8', text: '#c084fc' },
  high_short:  { label: '📉 Short >15%', bg: '#1c1200', border: '#854d0e', text: '#facc15' },
};

// ── Formatters ─────────────────────────────────────────────────────────────────
function fmtMoney(n) {
  if (n == null) return '—';
  const abs = Math.abs(n), sign = n < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  return `${sign}$${abs.toFixed(0)}`;
}
function fmtVol(n) {
  if (!n) return '—';
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return String(n);
}
function fmtNum(v, dec = 1) {
  if (v == null || v === '') return '—';
  const n = parseFloat(v);
  return isNaN(n) ? (v || '—') : n.toFixed(dec);
}

// ── Cell helpers ───────────────────────────────────────────────────────────────
function PctCell({ val }) {
  if (val == null || val === '') return <span style={{ color: '#334155' }}>—</span>;
  const n = parseFloat(val);
  const color = n > 0 ? '#4ade80' : n < 0 ? '#f87171' : '#94a3b8';
  return (
    <span style={{ color, fontFamily: 'monospace', fontWeight: 700 }}>
      {n > 0 ? '+' : ''}{n.toFixed(2)}%
    </span>
  );
}

function MoneyCell({ val, str }) {
  const display = str || fmtMoney(val);
  if (!display || display === '—') return <span style={{ color: '#334155' }}>—</span>;
  const neg = display.startsWith('-') || (val != null && val < 0);
  return (
    <span style={{ color: neg ? '#f87171' : '#94a3b8', fontFamily: 'monospace', fontSize: 12 }}>
      {display}
    </span>
  );
}

function RsiCell({ val }) {
  if (!val) return <span style={{ color: '#334155' }}>—</span>;
  const n = parseFloat(val);
  const color = n > 70 ? '#f87171' : n < 30 ? '#4ade80' : n > 50 ? '#a3e635' : '#94a3b8';
  return <span style={{ color, fontFamily: 'monospace', fontWeight: 700 }}>{n.toFixed(0)}</span>;
}

function ShortCell({ val }) {
  if (!val) return <span style={{ color: '#334155' }}>—</span>;
  const n = parseFloat(val);
  const color = n > 20 ? '#f87171' : n > 10 ? '#fb923c' : '#94a3b8';
  return <span style={{ color, fontFamily: 'monospace' }}>{val}</span>;
}

// ── Health Score badge ─────────────────────────────────────────────────────────
const HEALTH_TIERS = [
  { min: 80, emoji: '🟢', label: 'איכות גבוהה', bg: '#052e16', border: '#166534', text: '#4ade80' },
  { min: 60, emoji: '🟡', label: 'יציבה',        bg: '#1c1a00', border: '#854d0e', text: '#fde047' },
  { min: 40, emoji: '🟠', label: 'ספקולטיבית',  bg: '#1c0f00', border: '#9a3412', text: '#fb923c' },
  { min: 0,  emoji: '🔴', label: 'מסוכנת',       bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
];
function getHealthTier(score) {
  return HEALTH_TIERS.find(t => score >= t.min) || HEALTH_TIERS[3];
}

function HealthBadge({ score, evMcRatio, tags }) {
  if (score == null) return <span style={{ color: '#334155' }}>—</span>;
  const tier = getHealthTier(score);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 3 }}>
      {/* Score pill */}
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        padding: '4px 9px', borderRadius: 8,
        background: tier.bg, border: `1px solid ${tier.border}`,
        minWidth: 64, justifyContent: 'center',
      }}>
        <span style={{ fontSize: 12 }}>{tier.emoji}</span>
        <span style={{ fontFamily: 'monospace', fontWeight: 900, fontSize: 15, color: tier.text }}>
          {score}
        </span>
      </div>
      {/* Tier label */}
      <span style={{ fontSize: 9, color: tier.text, opacity: 0.75 }}>{tier.label}</span>
      {/* EV/MC ratio if available */}
      {evMcRatio != null && (
        <span style={{ fontSize: 9, color: '#334155', fontFamily: 'monospace' }}>
          EV/MC: {evMcRatio.toFixed(2)}
        </span>
      )}
    </div>
  );
}

// ── Earnings Status mini-card ──────────────────────────────────────────────────
const VERDICT_META = {
  beat:   { label: '✅ Beat',    bg: '#052e16', border: '#166534', text: '#4ade80' },
  miss:   { label: '❌ Miss',    bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  inline: { label: '〰️ In-line', bg: '#1c1a00', border: '#854d0e', text: '#fde047' },
};

function ReasonBadge({ reason }) {
  const s = REASON_STYLE[reason.type] || REASON_STYLE.technical;
  return (
    <span style={{
      fontSize: 10, padding: '2px 7px', borderRadius: 4,
      background: s.bg, border: `1px solid ${s.border}`, color: s.text,
      whiteSpace: 'nowrap', display: 'inline-block', fontWeight: 600,
    }}>
      {reason.label}
    </span>
  );
}

function TagBadge({ tag }) {
  const m = TAG_META[tag];
  if (!m) return null;
  return (
    <span style={{
      fontSize: 10, padding: '2px 6px', borderRadius: 4,
      background: m.bg, border: `1px solid ${m.border}`, color: m.text,
      whiteSpace: 'nowrap', display: 'inline-block',
    }}>
      {m.label}
    </span>
  );
}

// ── Earnings Status card (verdict + Q/Q metrics + next date) ──────────────────
function EarningsBadge({ s }) {
  const epsVal   = s.eps_qq   != null && s.eps_qq   !== '' ? parseFloat(s.eps_qq)   : NaN;
  const salesVal = s.sales_qq != null && s.sales_qq !== '' ? parseFloat(s.sales_qq) : NaN;
  const hasEps   = !isNaN(epsVal);
  const hasSales = !isNaN(salesVal);
  const verdict  = s.earnings_verdict ? VERDICT_META[s.earnings_verdict] : null;

  if (!verdict && !hasEps && !hasSales && !s.earnings_date) return null;

  const epsColor   = epsVal >= 20   ? '#4ade80' : epsVal > 0    ? '#86efac'
                   : epsVal < -10   ? '#f87171' : epsVal < 0    ? '#fca5a5' : '#94a3b8';
  const epsEmoji   = epsVal >= 20   ? '🔥' : epsVal > 0  ? '✅' : epsVal < 0 ? '❌' : '➖';
  const salesColor = salesVal > 15  ? '#4ade80' : salesVal > 0  ? '#86efac'
                   : salesVal < 0   ? '#f87171' : '#94a3b8';

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', gap: 3,
      padding: '5px 8px', borderRadius: 7, marginTop: 4,
      background: '#0d1a2e', border: '1px solid #1e3a5f',
      minWidth: 120,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
        <span style={{ fontSize: 9, color: '#475569', fontWeight: 700 }}>דוחות אחרונים</span>
        {verdict && (
          <span style={{
            fontSize: 10, padding: '1px 6px', borderRadius: 4, fontWeight: 700,
            background: verdict.bg, border: `1px solid ${verdict.border}`, color: verdict.text,
          }}>
            {verdict.label}
          </span>
        )}
      </div>
      {hasEps && (
        <span style={{ fontSize: 10, color: epsColor, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
          {epsEmoji} EPS Q/Q: {epsVal > 0 ? '+' : ''}{epsVal.toFixed(1)}%
        </span>
      )}
      {hasSales && (
        <span style={{ fontSize: 10, color: salesColor, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
          📦 Rev Q/Q: {salesVal > 0 ? '+' : ''}{salesVal.toFixed(1)}%
        </span>
      )}
      {s.earnings_date && (
        <span style={{ fontSize: 9, color: '#334155', whiteSpace: 'nowrap' }}>
          📅 {s.earnings_date}
        </span>
      )}
    </div>
  );
}

function FilterSelect({ options, value, onChange }) {
  return (
    <select
      value={value}
      onChange={e => onChange(e.target.value)}
      style={{
        fontSize: 12, padding: '5px 8px', borderRadius: 8,
        background: '#18181b', border: '1px solid #3f3f46',
        color: '#d4d4d8', cursor: 'pointer', outline: 'none',
      }}
    >
      {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function SortTh({ label, col, sort, onSort, sub }) {
  const active = sort.col === col;
  return (
    <th onClick={() => onSort(col)} style={{
      textAlign: 'right', padding: '9px 10px', fontSize: 11, fontWeight: 600,
      cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
      color: active ? '#60a5fa' : '#64748b', borderBottom: '1px solid #1e293b',
      background: '#0a0f1a', verticalAlign: 'top',
    }}>
      <div style={{ lineHeight: 1.3 }}>
        {label}{active ? (sort.dir === 'desc' ? ' ↓' : ' ↑') : ''}
      </div>
      {sub && (
        <div style={{ fontSize: 9, color: '#334155', fontWeight: 400, marginTop: 2, lineHeight: 1.2 }}>
          {sub}
        </div>
      )}
    </th>
  );
}

// ── News row (expandable) ──────────────────────────────────────────────────────
function NewsRow({ news, colSpan }) {
  if (!news?.length) return null;
  const fmt = (ts) => {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleDateString('he-IL', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };
  return (
    <tr>
      <td colSpan={colSpan} style={{ padding: '0 10px 12px 10px', background: '#070d1a' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6, paddingTop: 8 }}>
          {news.slice(0, 4).map((n, i) => (
            <a
              key={i}
              href={n.link || '#'}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              style={{
                display: 'flex', gap: 10, alignItems: 'flex-start',
                textDecoration: 'none', padding: '6px 10px', borderRadius: 8,
                background: '#0d1626', border: '1px solid #1e293b',
                transition: 'border-color 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.borderColor = '#3b82f6'}
              onMouseLeave={e => e.currentTarget.style.borderColor = '#1e293b'}
            >
              <span style={{ color: '#334155', fontSize: 10, minWidth: 14, paddingTop: 2 }}>{i + 1}.</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ color: '#cbd5e1', fontSize: 12, margin: 0, lineHeight: 1.4 }}>
                  {n.title}
                </p>
                <div style={{ display: 'flex', gap: 8, marginTop: 3 }}>
                  {n.publisher && (
                    <span style={{ color: '#475569', fontSize: 10 }}>{n.publisher}</span>
                  )}
                  {n.published && (
                    <span style={{ color: '#334155', fontSize: 10 }}>{fmt(n.published)}</span>
                  )}
                </div>
              </div>
              <span style={{ color: '#3b82f6', fontSize: 11, paddingTop: 2, flexShrink: 0 }}>↗</span>
            </a>
          ))}
        </div>
      </td>
    </tr>
  );
}

// ── Countdown ring ─────────────────────────────────────────────────────────────
function CountdownRing({ seconds, total }) {
  const pct = (seconds / total) * 100;
  const r = 9, c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;
  return (
    <svg width={24} height={24} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={12} cy={12} r={r} fill="none" stroke="#1e293b" strokeWidth={2.5} />
      <circle
        cx={12} cy={12} r={r} fill="none"
        stroke={seconds <= 10 ? '#f87171' : '#3b82f6'}
        strokeWidth={2.5}
        strokeDasharray={`${dash} ${c}`}
        style={{ transition: 'stroke-dasharray 1s linear' }}
      />
    </svg>
  );
}

// ── Session detection ──────────────────────────────────────────────────────────
const SESSION_META = {
  pre:     { label: '🌅 Pre-Market',  color: '#fb923c', bg: '#1c0f00', border: '#92400e' },
  regular: { label: '📈 Regular',     color: '#4ade80', bg: '#052e16', border: '#166534' },
  post:    { label: '🌆 After-Hours', color: '#818cf8', bg: '#1e1b4b', border: '#4338ca' },
  closed:  { label: '⏸ Closed',      color: '#475569', bg: '#0f172a', border: '#1e293b' },
};
function getClientSession() {
  try {
    const et = new Date().toLocaleString('en-US', { timeZone: 'America/New_York' });
    const d  = new Date(et);
    const h  = d.getHours() + d.getMinutes() / 60;
    const dow = d.getDay(); // 0=Sun, 6=Sat
    if (dow === 0 || dow === 6) return 'closed';
    if (h < 4)    return 'closed';
    if (h < 9.5)  return 'pre';
    if (h < 16)   return 'regular';
    if (h < 20)   return 'post';
    return 'closed';
  } catch { return 'regular'; }
}

// ── Main component ─────────────────────────────────────────────────────────────
const REFRESH_SEC = 30;

export default function FinvizTableScanner() {
  const [mcap,   setMcap]   = useState('cap_midover');
  const [vol,    setVol]    = useState('sh_avgvol_o2000');
  const [change, setChange] = useState('ta_changeopen_u4');
  const [shortf, setShortf] = useState('sh_short_o5');
  const [rsi,    setRsi]    = useState('ta_rsi_nos50');
  const [inst,   setInst]   = useState('sh_instown_o10');
  const [sort,   setSort]   = useState({ col: 'change_pct', dir: 'desc' });
  const [expanded, setExpanded] = useState(new Set());
  const [countdown, setCountdown] = useState(REFRESH_SEC);
  const countdownRef = useRef(REFRESH_SEC);

  const filters = buildFilters(mcap, vol, change, shortf, rsi, inst);

  const { data, isLoading, isError, dataUpdatedAt, refetch } = useQuery({
    queryKey: ['finvizTable', filters],
    queryFn: () =>
      api.get(`/screener/finviz-table?filters=${encodeURIComponent(filters)}`).then(r => r.data),
    refetchInterval: REFRESH_SEC * 1000,
    staleTime: 0,
  });

  // Reset countdown when data updates
  useEffect(() => {
    countdownRef.current = REFRESH_SEC;
    setCountdown(REFRESH_SEC);
  }, [dataUpdatedAt]);

  // Tick countdown every second
  useEffect(() => {
    const id = setInterval(() => {
      countdownRef.current = Math.max(0, countdownRef.current - 1);
      setCountdown(countdownRef.current);
    }, 1000);
    return () => clearInterval(id);
  }, []);

  const stocks  = data?.stocks || [];
  // Session: prefer client-side time (always fresh), use API response as fallback
  const session = useMemo(() => data ? getClientSession() : 'regular', [dataUpdatedAt]); // eslint-disable-line
  const sessionMeta = SESSION_META[session] || SESSION_META.regular;
  const isExtended  = session === 'pre' || session === 'post';

  const sorted = useMemo(() => {
    if (!stocks.length) return [];
    return [...stocks].sort((a, b) => {
      let av = a[sort.col], bv = b[sort.col];
      av = parseFloat(av); bv = parseFloat(bv);
      av = isNaN(av) ? -Infinity : av;
      bv = isNaN(bv) ? -Infinity : bv;
      return sort.dir === 'desc' ? bv - av : av - bv;
    });
  }, [stocks, sort]);

  const handleSort = useCallback((col) => {
    setSort(prev => ({ col, dir: prev.col === col && prev.dir === 'desc' ? 'asc' : 'desc' }));
  }, []);

  const toggleExpand = useCallback((ticker, e) => {
    e.stopPropagation();
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }, []);

  const COL_COUNT = 21; // expand + # + ticker + sector + price + chg_day + chg_5m + chg_30m + vol + mcap + revenue + income + pe + eps + salesqq + rsi + short + inst + beta + health + tags

  const thBase = { background: '#0a0f1a', borderBottom: '1px solid #1e293b' };
  const tdBase = { padding: '9px 10px', borderBottom: '1px solid #131c2e', textAlign: 'right' };

  return (
    <div style={{ color: '#e2e8f0' }} dir="rtl">
      {/* ── Header ── */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 10, marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <h2 style={{ fontSize: 17, fontWeight: 900, color: '#fff', margin: 0 }}>סורק בסיסי</h2>
          {data && (
            <span style={{ fontSize: 12, color: '#475569' }}>
              {data.count} מניות
            </span>
          )}
          {/* Session badge */}
          {data && (
            <span style={{
              fontSize: 11, padding: '3px 9px', borderRadius: 6, fontWeight: 700,
              background: sessionMeta.bg, border: `1px solid ${sessionMeta.border}`,
              color: sessionMeta.color,
            }}>
              {sessionMeta.label}
            </span>
          )}
          {isLoading && <span style={{ fontSize: 11, color: '#3b82f6' }}>טוען...</span>}
        </div>

        {/* Countdown + refresh */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <CountdownRing seconds={countdown} total={REFRESH_SEC} />
            <span style={{ fontSize: 11, color: countdown <= 10 ? '#f87171' : '#475569', fontFamily: 'monospace' }}>
              {countdown}s
            </span>
          </div>
          <button
            onClick={() => { refetch(); countdownRef.current = REFRESH_SEC; setCountdown(REFRESH_SEC); }}
            disabled={isLoading}
            style={{
              fontSize: 12, padding: '5px 12px', borderRadius: 8,
              background: '#1e293b', border: '1px solid #334155',
              color: '#94a3b8', cursor: 'pointer', opacity: isLoading ? 0.5 : 1,
            }}
          >
            🔄 רענן
          </button>
        </div>
      </div>

      {/* ── Filters ── */}
      <div style={{
        display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center',
        padding: '10px 14px', marginBottom: 14,
        background: '#0a0f1a', border: '1px solid #1e293b', borderRadius: 12,
      }}>
        <span style={{ fontSize: 11, color: '#475569', marginLeft: 4 }}>פילטרים:</span>
        <FilterSelect options={MCAP_OPTS}   value={mcap}   onChange={v => { setMcap(v);   setExpanded(new Set()); }} />
        <FilterSelect options={VOL_OPTS}    value={vol}    onChange={v => { setVol(v);    setExpanded(new Set()); }} />
        <FilterSelect options={CHANGE_OPTS} value={change} onChange={v => { setChange(v); setExpanded(new Set()); }} />
        <FilterSelect options={SHORT_OPTS}  value={shortf} onChange={v => { setShortf(v); setExpanded(new Set()); }} />
        <FilterSelect options={RSI_OPTS}    value={rsi}    onChange={v => { setRsi(v);    setExpanded(new Set()); }} />
        <FilterSelect options={INST_OPTS}   value={inst}   onChange={v => { setInst(v);   setExpanded(new Set()); }} />
      </div>

      {/* ── States ── */}
      {isError && (
        <div style={{ padding: 14, borderRadius: 10, marginBottom: 12,
          background: '#2d0a0a', border: '1px solid #7f1d1d', color: '#f87171', fontSize: 13 }}>
          שגיאה בטעינת הנתונים — בדוק שהשרת פועל
        </div>
      )}
      {/* Global animations */}
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes starGlow {
          0%, 100% { background: rgba(74,222,128,0.06); }
          50% { background: rgba(74,222,128,0.16); box-shadow: inset 0 0 20px rgba(74,222,128,0.12); }
        }
        tr.star-stock { animation: starGlow 2.2s ease-in-out infinite; }
        tr.star-stock td:last-child { border-left: 2px solid rgba(74,222,128,0.4); }
      `}</style>

      {isLoading && !stocks.length && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#475569' }}>
          <div style={{
            width: 28, height: 28, border: '3px solid #1e293b', borderTopColor: '#3b82f6',
            borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 10px',
          }} />
          <p style={{ fontSize: 13 }}>טוען נתונים מ-Finviz...</p>
        </div>
      )}
      {!isLoading && !isError && stocks.length === 0 && (
        <div style={{ textAlign: 'center', padding: '60px 0', color: '#475569', fontSize: 13 }}>
          לא נמצאו מניות עם הפילטרים הנוכחיים
        </div>
      )}

      {/* ── Table ── */}
      {sorted.length > 0 && (
        <div style={{ overflowX: 'auto', borderRadius: 12, border: '1px solid #1e293b' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
            <thead>
              <tr>
                {/* expand toggle col */}
                <th style={{ ...thBase, padding: '9px 6px', width: 28 }} />
                <th style={{ ...thBase, padding: '9px 10px', textAlign: 'right', fontSize: 11, color: '#475569', width: 28 }}>#</th>
                <SortTh label="מניה + סיבה"  col="ticker"       sort={sort} onSort={handleSort} sub="סימול ומה מניע" />
                <SortTh label="סקטור"          col="sector"       sort={sort} onSort={handleSort} sub="ענף ותת-ענף" />
                <SortTh label="מחיר"           col="price"        sort={sort} onSort={handleSort} sub={isExtended ? `Pre/Post` : "מחיר נוכחי"} />
                <SortTh label="Chg% יום"       col="change_pct"   sort={sort} onSort={handleSort} sub={isExtended ? "שינוי מ-Close" : "שינוי מתחילת יום"} />
                <SortTh label="Chg 5m"         col="chg_5m"       sort={sort} onSort={handleSort} sub="שינוי 5 דקות" />
                <SortTh label="Chg 30m"        col="chg_30m"      sort={sort} onSort={handleSort} sub="שינוי 30 דקות" />
                <SortTh label="נפח"            col="volume"       sort={sort} onSort={handleSort} sub="כמות מסחר יומית" />
                <SortTh label="Mkt Cap"        col="market_cap"   sort={sort} onSort={handleSort} sub="שווי שוק כולל" />
                <SortTh label="Revenue"        col="sales"        sort={sort} onSort={handleSort} sub="סה״כ הכנסות" />
                <SortTh label="Net Income"     col="income"       sort={sort} onSort={handleSort} sub="רווח / הפסד נקי" />
                <SortTh label="P/E"            col="pe"           sort={sort} onSort={handleSort} sub="מכפיל רווח" />
                <SortTh label="EPS Y%"         col="eps_this_y"   sort={sort} onSort={handleSort} sub="צמיחת רווח למניה" />
                <SortTh label="Sales Q/Q"      col="sales_qq"     sort={sort} onSort={handleSort} sub="צמיחת מכירות רבעוני" />
                <SortTh label="RSI"            col="rsi"          sort={sort} onSort={handleSort} sub="מדד כוח יחסי" />
                <SortTh label="Short%"         col="short_float"  sort={sort} onSort={handleSort} sub="% מניות בשורט" />
                <SortTh label="Inst%"          col="inst_own"     sort={sort} onSort={handleSort} sub="אחזקה מוסדית" />
                <SortTh label="Beta"           col="beta"         sort={sort} onSort={handleSort} sub="תנודתיות מול שוק" />
                <SortTh label="🧠 Health"      col="health_score" sort={sort} onSort={handleSort} sub="ציון בריאות פיננסי" />
                <th style={{ ...thBase, padding: '9px 10px', textAlign: 'right', fontSize: 11, color: '#475569', minWidth: 130 }}>תגיות</th>
              </tr>
            </thead>

            <tbody>
              {sorted.map((s, i) => {
                // Use extended_chg_pct during pre/post market, otherwise regular change
                const chg = isExtended && s.extended_chg_pct != null
                  ? parseFloat(s.extended_chg_pct)
                  : (parseFloat(s.change_pct) || 0);
                const isStar = (s.health_score >= 80) && (chg >= 8);
                const rowBg = isStar ? undefined
                            : chg >= 8 ? 'rgba(74,222,128,0.04)'
                            : chg >= 4 ? 'rgba(74,222,128,0.02)'
                            : chg <= -3 ? 'rgba(248,113,113,0.03)'
                            : 'transparent';
                const isOpen = expanded.has(s.ticker);
                const hasNews = s.news?.length > 0;

                return [
                  /* ── Main row ── */
                  <tr
                    key={`row-${s.ticker}`}
                    className={isStar ? 'star-stock' : ''}
                    style={{ background: rowBg, cursor: 'pointer', transition: 'background 0.12s' }}
                    onClick={() => window.open(`https://finviz.com/quote.ashx?t=${s.ticker}`, '_blank')}
                    onMouseEnter={e => e.currentTarget.style.background = '#0d1626'}
                    onMouseLeave={e => { e.currentTarget.style.background = isStar ? '' : rowBg; }}
                  >
                    {/* Expand toggle */}
                    <td style={{ ...tdBase, width: 28, textAlign: 'center', paddingLeft: 4, paddingRight: 4 }}>
                      {hasNews && (
                        <button
                          onClick={e => toggleExpand(s.ticker, e)}
                          title={isOpen ? 'סגור חדשות' : 'הצג חדשות'}
                          style={{
                            width: 20, height: 20, borderRadius: 4, border: 'none',
                            background: isOpen ? '#1e3a5f' : '#1e293b',
                            color: isOpen ? '#60a5fa' : '#475569',
                            cursor: 'pointer', fontSize: 11, lineHeight: 1,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                          }}
                        >
                          {isOpen ? '▲' : '▼'}
                        </button>
                      )}
                    </td>

                    {/* # */}
                    <td style={{ ...tdBase, color: '#334155', fontSize: 11 }}>{i + 1}</td>

                    {/* Ticker + company + reasons + business summary */}
                    <td style={tdBase}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                        <span style={{ fontWeight: 900, color: '#f8fafc', fontSize: 14, letterSpacing: '-0.3px' }}>
                          {s.ticker}
                        </span>
                        {isStar && (
                          <span style={{ fontSize: 12 }} title="מניה מצוינת: Health ≥80 + עליה ≥8%">⭐</span>
                        )}
                      </div>
                      <div style={{ color: '#475569', fontSize: 10, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {s.company}
                      </div>
                      {/* Business summary — 1 sentence about the company */}
                      {s.business_summary && (
                        <div style={{
                          color: '#334155', fontSize: 10, maxWidth: 240, marginTop: 2, marginBottom: 3,
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                          lineHeight: 1.3, fontStyle: 'italic',
                        }} title={s.business_summary}>
                          {s.business_summary}
                        </div>
                      )}
                      {/* Move reasons */}
                      {s.reasons?.length > 0 && (
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                          {s.reasons.map((r, ri) => <ReasonBadge key={ri} reason={r} />)}
                        </div>
                      )}
                      {/* Top news headline preview */}
                      {hasNews && !isOpen && (
                        <div style={{ marginTop: 4, fontSize: 10, color: '#475569', maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          📰 {s.news[0].title}
                        </div>
                      )}
                    </td>

                    {/* Sector */}
                    <td style={{ ...tdBase, maxWidth: 110 }}>
                      {s.sector ? (
                        <span style={{
                          fontSize: 10, color: '#64748b',
                          display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>
                          {s.sector}
                        </span>
                      ) : <span style={{ color: '#334155' }}>—</span>}
                      {s.industry && (
                        <span style={{
                          fontSize: 9, color: '#334155',
                          display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>
                          {s.industry}
                        </span>
                      )}
                    </td>

                    {/* Price — show extended price during pre/post market */}
                    <td style={tdBase}>
                      <span style={{ fontFamily: 'monospace', fontWeight: 700, color: '#e2e8f0', fontSize: 13 }}>
                        {isExtended && s.extended_price
                          ? `$${parseFloat(s.extended_price).toFixed(2)}`
                          : s.price ? `$${parseFloat(s.price).toFixed(2)}` : '—'
                        }
                      </span>
                      {isExtended && s.extended_price && (
                        <div style={{ fontSize: 9, color: sessionMeta.color, opacity: 0.8 }}>
                          {session === 'pre' ? '🌅 Pre' : '🌆 Post'}
                        </div>
                      )}
                    </td>

                    {/* Chg% day — show extended change during pre/post market */}
                    <td style={tdBase}>
                      <PctCell val={isExtended && s.extended_chg_pct != null
                        ? s.extended_chg_pct
                        : s.change_pct}
                      />
                      {isExtended && s.extended_chg_pct != null && s.prev_close && (
                        <div style={{ fontSize: 9, color: '#334155', fontFamily: 'monospace' }}>
                          מ-${parseFloat(s.prev_close).toFixed(2)}
                        </div>
                      )}
                    </td>

                    {/* Chg 5m */}
                    <td style={tdBase}>
                      <PctCell val={s.chg_5m} />
                    </td>

                    {/* Chg 30m */}
                    <td style={tdBase}>
                      <PctCell val={s.chg_30m} />
                    </td>

                    {/* Volume */}
                    <td style={{ ...tdBase, color: '#64748b', fontFamily: 'monospace', fontSize: 12 }}>
                      {fmtVol(s.volume)}
                    </td>

                    {/* Market Cap */}
                    <td style={tdBase}><MoneyCell val={s.market_cap} str={s.market_cap_str} /></td>

                    {/* Revenue */}
                    <td style={tdBase}><MoneyCell val={s.sales} str={s.sales_str} /></td>

                    {/* Net Income */}
                    <td style={tdBase}><MoneyCell val={s.income} str={s.income_str} /></td>

                    {/* P/E */}
                    <td style={{ ...tdBase, color: '#64748b', fontFamily: 'monospace', fontSize: 12 }}>
                      {fmtNum(s.pe)}
                    </td>

                    {/* EPS Y% */}
                    <td style={tdBase}><PctCell val={s.eps_this_y} /></td>

                    {/* Sales Q/Q */}
                    <td style={tdBase}><PctCell val={s.sales_qq} /></td>

                    {/* RSI */}
                    <td style={tdBase}><RsiCell val={s.rsi} /></td>

                    {/* Short% */}
                    <td style={tdBase}><ShortCell val={s.short_float} /></td>

                    {/* Inst% */}
                    <td style={{ ...tdBase, color: '#64748b', fontFamily: 'monospace', fontSize: 12 }}>
                      {s.inst_own || '—'}
                    </td>

                    {/* Beta */}
                    <td style={{ ...tdBase, color: '#64748b', fontFamily: 'monospace', fontSize: 12 }}>
                      {fmtNum(s.beta)}
                    </td>

                    {/* Health Score */}
                    <td style={{ ...tdBase, textAlign: 'right' }}>
                      <HealthBadge
                        score={s.health_score}
                        evMcRatio={s.ev_mc_ratio}
                        tags={s.tags}
                      />
                    </td>

                    {/* Tags + Recent Earnings Status */}
                    <td style={tdBase}>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
                        <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
                          {(s.tags || []).map(tag => <TagBadge key={tag} tag={tag} />)}
                        </div>
                        <EarningsBadge s={s} />
                      </div>
                    </td>
                  </tr>,

                  /* ── News expansion row ── */
                  isOpen && hasNews && (
                    <NewsRow key={`news-${s.ticker}`} news={s.news} colSpan={COL_COUNT} />
                  ),
                ];
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Legend ── */}
      {sorted.length > 0 && (
        <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 8 }}>

          {/* Health Score legend */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, alignItems: 'center' }}>
            <span style={{ fontSize: 10, color: '#475569', marginLeft: 8, fontWeight: 600 }}>🧠 Health Score:</span>
            {HEALTH_TIERS.map(t => (
              <span key={t.min} style={{
                fontSize: 10, padding: '3px 9px', borderRadius: 6,
                background: t.bg, border: `1px solid ${t.border}`, color: t.text, fontWeight: 600,
              }}>
                {t.emoji} {t.min === 80 ? '80–100' : t.min === 60 ? '60–79' : t.min === 40 ? '40–59' : '0–39'} {t.label}
              </span>
            ))}
            <span style={{ fontSize: 10, color: '#334155', marginRight: 8 }}>
              חישוב: +30 רווחית · +20 מזומן · +20 צמיחה · −25 הפסד · −20 חוב · בסיס 50
            </span>
          </div>

          {/* Health tags + move reasons */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, alignItems: 'center' }}>
            <span style={{ fontSize: 10, color: '#475569', marginLeft: 6, fontWeight: 600 }}>תגיות בריאות:</span>
            {Object.entries(TAG_META).map(([k, m]) => (
              <span key={k} style={{
                fontSize: 10, padding: '2px 7px', borderRadius: 4,
                background: m.bg, border: `1px solid ${m.border}`, color: m.text,
              }}>
                {m.label}
              </span>
            ))}
            <span style={{ fontSize: 10, color: '#334155', margin: '0 6px' }}>|</span>
            <span style={{ fontSize: 10, color: '#475569', marginLeft: 4, fontWeight: 600 }}>סיבות תנועה:</span>
            {[
              { type: 'earnings', label: '📊 דוח/תוצאות' },
              { type: 'upgrade',  label: '⬆️ שדרוג' },
              { type: 'downgrade',label: '⬇️ הורדה' },
              { type: 'fda',      label: '💊 FDA' },
              { type: 'ma',       label: '🤝 מיזוג' },
              { type: 'guidance', label: '🔮 תחזית' },
              { type: 'gap',      label: '📈 Gap' },
            ].map(r => {
              const st = REASON_STYLE[r.type];
              return (
                <span key={r.type} style={{
                  fontSize: 10, padding: '2px 7px', borderRadius: 4,
                  background: st.bg, border: `1px solid ${st.border}`, color: st.text,
                }}>
                  {r.label}
                </span>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
