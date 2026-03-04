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

// ── Filter options — קודים תואמי Finviz (לחיצה ובחירה כמו ב-Finviz) ─────────────
const ANY = { label: 'Any', value: '' };

const MCAP_OPTS = [
  ANY,
  { label: '+Mid (over $2bln)', value: 'cap_midover' },
  { label: '+Large (over $10bln)', value: 'cap_largeover' },
  { label: '+Small (over $300mln)', value: 'cap_smallover' },
  { label: 'Mega ($200bln+)', value: 'cap_mega' },
];

const AVGVOL_OPTS = [
  ANY,
  { label: 'Over 100K', value: 'sh_avgvol_o100' },
  { label: 'Over 300K', value: 'sh_avgvol_o300' },
  { label: 'Over 500K', value: 'sh_avgvol_o500' },
  { label: 'Over 1M', value: 'sh_avgvol_o1000' },
  { label: 'Over 2M', value: 'sh_avgvol_o2000' },
];

const RELVOL_OPTS = [
  ANY,
  { label: 'Over 1×', value: 'sh_relvol_o1' },
  { label: 'Over 1.5×', value: 'sh_relvol_o1.5' },
  { label: 'Over 2×', value: 'sh_relvol_o2' },
  { label: 'Over 3×', value: 'sh_relvol_o3' },
];

const CURVOL_OPTS = [
  ANY,
  { label: 'Over 100K', value: 'sh_curvol_o100' },
  { label: 'Over 300K', value: 'sh_curvol_o300' },
  { label: 'Over 500K', value: 'sh_curvol_o500' },
  { label: 'Over 1M', value: 'sh_curvol_o1000' },
  { label: 'Over 2M', value: 'sh_curvol_o2000' },
];

const CHANGE_OPTS = [
  ANY,
  { label: 'Custom %', value: 'custom' },
  { label: 'From Open >2%', value: 'ta_changeopen_u2' },
  { label: 'From Open >4%', value: 'ta_changeopen_u4' },
  { label: 'Day >3%', value: 'ta_change_u3' },
  { label: 'Day >5%', value: 'ta_change_u5' },
];

const CHANGEOPEN_OPTS = [
  ANY,
  { label: 'Up', value: 'ta_changeopen_u' },
  { label: 'Up >1%', value: 'ta_changeopen_u1' },
  { label: 'Up >2%', value: 'ta_changeopen_u2' },
  { label: 'Up >3%', value: 'ta_changeopen_u3' },
  { label: 'Up >5%', value: 'ta_changeopen_u5' },
  { label: 'Down', value: 'ta_changeopen_d' },
  { label: 'Down >2%', value: 'ta_changeopen_d2' },
];

const SALESQQ_OPTS = [
  ANY,
  { label: 'Positive (>0%)', value: 'fa_salesqoq_pos' },
  { label: 'Over 5%', value: 'fa_salesqoq_o5' },
  { label: 'Over 10%', value: 'fa_salesqoq_o10' },
  { label: 'Over 25%', value: 'fa_salesqoq_o25' },
  { label: 'Negative (<0%)', value: 'fa_salesqoq_neg' },
];

const SHORT_OPTS = [
  ANY,
  { label: 'Over 5%', value: 'sh_short_o5' },
  { label: 'Over 10%', value: 'sh_short_o10' },
  { label: 'Over 20%', value: 'sh_short_o20' },
  { label: 'Over 30%', value: 'sh_short_o30' },
];

const RSI_OPTS = [
  ANY,
  { label: '>30 (לא מכור)', value: 'ta_rsi_nos30' },
  { label: '>50', value: 'ta_rsi_nos50' },
  { label: 'Overbought (60)', value: 'ta_rsi_nos60' },
  { label: 'Overbought (70)', value: 'ta_rsi_ob70' },
  { label: '<30 (מכור יתר)', value: 'ta_rsi_os30' },
];

const INST_OPTS = [
  ANY,
  { label: 'Over 10%', value: 'sh_instown_o10' },
  { label: 'Over 30%', value: 'sh_instown_o30' },
  { label: 'Over 50%', value: 'sh_instown_o50' },
];

function buildFilters(mcap, avgvol, relvol, curvol, change, changeopen, shortf, rsi, inst, salesqq) {
  const changeForApi = change === 'custom' ? '' : change;
  return [mcap, avgvol, relvol, curvol, changeForApi, changeopen, shortf, rsi, inst, salesqq]
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
  profitable:  { label: '✅ רווחית',     bg: '#0c2a1a', border: '#166534', text: '#4ade80' },
  loss:        { label: '❌ הפסד',       bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  high_debt:   { label: '⚠️ חוב גבוה',  bg: '#1c1000', border: '#78350f', text: '#fb923c' },
  cash_rich:   { label: '💰 מזומן גבוה', bg: '#0c1a2e', border: '#1e40af', text: '#60a5fa' },
  high_growth: { label: '🔥 צמיחה',     bg: '#1a0a2e', border: '#6b21a8', text: '#c084fc' },
  high_short:  { label: '📉 שורט >15%', bg: '#1c1200', border: '#854d0e', text: '#facc15' },
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
  if (val == null || val === '') return <span style={{ color: '#94a3b8' }}>—</span>;
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
  if (!display || display === '—') return <span style={{ color: '#94a3b8' }}>—</span>;
  const neg = display.startsWith('-') || (val != null && val < 0);
  return (
    <span style={{ color: neg ? '#f87171' : '#94a3b8', fontFamily: 'monospace', fontSize: 12 }}>
      {display}
    </span>
  );
}

function RsiCell({ val }) {
  if (!val) return <span style={{ color: '#94a3b8' }}>—</span>;
  const n = parseFloat(val);
  const color = n > 70 ? '#f87171' : n < 30 ? '#4ade80' : n > 50 ? '#a3e635' : '#94a3b8';
  return <span style={{ color, fontFamily: 'monospace', fontWeight: 700 }}>{n.toFixed(0)}</span>;
}

function ShortCell({ val }) {
  if (!val) return <span style={{ color: '#94a3b8' }}>—</span>;
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

function HealthBadge({ score }) {
  if (score == null) return <span style={{ color: '#94a3b8' }}>—</span>;
  const tier = getHealthTier(score);
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 3,
      padding: '2px 6px', borderRadius: 6,
      background: tier.bg, border: `1px solid ${tier.border}`,
    }}>
      <span style={{ fontSize: 10 }}>{tier.emoji}</span>
      <span style={{ fontFamily: 'monospace', fontWeight: 900, fontSize: 12, color: tier.text }}>
        {score}
      </span>
    </div>
  );
}

// ── Earnings Status mini-card ──────────────────────────────────────────────────
const VERDICT_META = {
  beat:   { label: '✅ הכה ציפיות', bg: '#052e16', border: '#166534', text: '#4ade80' },
  miss:   { label: '❌ פספס ציפיות', bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  inline: { label: '〰️ בציפיות',   bg: '#1c1a00', border: '#854d0e', text: '#fde047' },
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
  if (!m) return <span style={{ fontSize: 11, color: '#94a3b8' }}>{tag}</span>;
  return (
    <span style={{
      fontSize: 11, padding: '3px 8px', borderRadius: 4, fontWeight: 600,
      background: m.bg, border: `1px solid ${m.border}`, color: m.text,
      whiteSpace: 'nowrap', display: 'inline-block', lineHeight: 1.3,
    }}>
      {m.label}
    </span>
  );
}

// ── Earnings Status badge (compact — verdict only) ────────────────────────────
function EarningsBadge({ s }) {
  const verdict = s.earnings_verdict ? VERDICT_META[s.earnings_verdict] : null;
  if (!verdict) return null;
  return (
    <span style={{
      fontSize: 9, padding: '1px 5px', borderRadius: 4, fontWeight: 700,
      background: verdict.bg, border: `1px solid ${verdict.border}`, color: verdict.text,
      whiteSpace: 'nowrap', display: 'inline-block', marginTop: 2,
    }}>
      {verdict.label}
    </span>
  );
}

// ── Finviz-style inline filter ─────────────────────────────────────────────────
function fvSelectStyle(isActive) {
  return {
    fontSize: 11,
    padding: '3px 5px',
    borderRadius: 3,
    border: `1px solid ${isActive ? '#3b82f6' : '#2a3a52'}`,
    background: isActive ? '#0a1628' : '#111c2d',
    color: isActive ? '#60a5fa' : '#94a3b8',
    outline: 'none',
    cursor: 'pointer',
    maxWidth: 160,
    minWidth: 80,
    fontFamily: 'inherit',
  };
}

const fvLabelStyle = (isActive) => ({
  fontSize: 11,
  color: isActive ? '#cbd5e1' : '#64748b',
  fontWeight: isActive ? 600 : 400,
  whiteSpace: 'nowrap',
  userSelect: 'none',
});

function FilterItem({ label, options, value, onChange }) {
  const isActive = value !== '' && value !== (options[0]?.value ?? '');
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <span style={fvLabelStyle(isActive)}>{label}</span>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={fvSelectStyle(isActive)}
      >
        {options.map(o => (
          <option key={o.value ?? 'any'} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

// for the custom % number input
const fvNumInput = {
  fontSize: 11,
  padding: '3px 5px',
  borderRadius: 3,
  border: '1px solid #3b82f6',
  background: '#0a1628',
  color: '#60a5fa',
  outline: 'none',
  width: 60,
  fontFamily: 'inherit',
};

function SortTh({ label, col, sort, onSort, sub, style: extraStyle }) {
  const active = sort.col === col;
  return (
    <th onClick={() => onSort(col)} style={{
      textAlign: 'right', padding: '6px 8px', fontSize: 11, fontWeight: 600,
      cursor: 'pointer', userSelect: 'none', whiteSpace: 'nowrap',
      color: active ? '#60a5fa' : '#94a3b8',
      background: active ? '#0f1c2e' : '#1a2332',
      borderBottom: '2px solid #2d3f56',
      borderLeft: '1px solid #1e293b',
      ...extraStyle,
    }}>
      {label}{active ? (sort.dir === 'desc' ? ' ↓' : ' ↑') : ''}
      {sub && <span style={{ fontSize: 9, color: '#64748b', fontWeight: 400, marginRight: 3 }}> {sub}</span>}
    </th>
  );
}

// ── Auto analysis builder ──────────────────────────────────────────────────────
const _REASON_COLORS = {
  earnings: '#4ade80', upgrade: '#60a5fa', downgrade: '#f87171',
  fda: '#c084fc', ma: '#fb923c', guidance: '#22d3ee',
  contract: '#fbbf24', risk: '#f87171', gap: '#86efac', technical: '#9ca3af',
};

function buildAnalysis(s) {
  const chg    = parseFloat(s.extended_chg_pct ?? s.change_pct ?? 0);
  const rsi    = parseFloat(s.rsi);
  const shortF = parseFloat(s.short_float);
  const eps    = parseFloat(s.eps_qq);
  const sales  = parseFloat(s.sales_qq);
  const score  = s.health_score ?? 50;

  // ── Move reasons (enriched) ──
  const movePoints = (s.reasons || []).map(r => {
    let text = r.label;
    if (r.type === 'earnings') {
      const v = s.earnings_verdict === 'beat' ? ' — הכה ציפיות' : s.earnings_verdict === 'miss' ? ' — פספסה ציפיות' : '';
      const e = !isNaN(eps)   ? ` | EPS ${eps > 0 ? '+' : ''}${eps.toFixed(1)}%`   : '';
      const sv= !isNaN(sales) ? ` | מכירות ${sales > 0 ? '+' : ''}${sales.toFixed(1)}%` : '';
      text = `📊 דוחות${v}${e}${sv}`;
    } else if (r.type === 'upgrade') {
      text = `⬆️ שדרוג${s.analyst_recom ? ` — ${RECOM_HE[s.analyst_recom] || s.analyst_recom}` : ''}${s.target_price ? ` | יעד $${s.target_price}` : ''}`;
    }
    return { text, color: _REASON_COLORS[r.type] || '#94a3b8' };
  });

  // ── Strengths ──
  const strengths = [];
  if (s.tags?.includes('profitable')) strengths.push('חברה רווחית — הכנסה נטו חיובית');
  if (s.tags?.includes('cash_rich'))  strengths.push('עתירת מזומנים — סיכון פיננסי נמוך (EV ≈ Market Cap)');
  if (s.tags?.includes('high_growth')) strengths.push(`צמיחת הכנסות${!isNaN(sales) ? ` +${sales.toFixed(0)}% Q/Q` : ' גבוהה'} — שוק מתמחר עתיד`);
  if (s.earnings_verdict === 'beat')  strengths.push(`הכה ציפיות האנליסטים${!isNaN(eps) ? ` (EPS Q/Q: +${eps.toFixed(1)}%)` : ''}`);
  if (!isNaN(rsi) && rsi >= 50 && rsi < 70) strengths.push(`מומנטום חיובי — RSI ${rsi.toFixed(0)}`);
  if (!isNaN(shortF) && shortF < 5)  strengths.push(`שורט נמוך (${shortF.toFixed(1)}%) — לחץ מכירה מוגבל`);
  if (['Buy','Strong Buy','Outperform','Overweight'].includes(s.analyst_recom))
    strengths.push(`אנליסטים: ${RECOM_HE[s.analyst_recom]}${s.target_price ? ` | יעד $${s.target_price}` : ''}`);

  // ── Risks ──
  const risks = [];
  if (s.tags?.includes('loss'))      risks.push('הפסד נקי — החברה עדיין לא רווחית');
  if (s.tags?.includes('high_debt')) risks.push('חוב גבוה — עלות ריבית עלולה להכביד על הרווחיות');
  if (s.tags?.includes('high_short')) risks.push(`שורט גבוה (${s.short_float}) — לחץ מכירה אפשרי`);
  if (s.earnings_verdict === 'miss') risks.push('פספסה ציפיות האנליסטים ברבעון האחרון');
  if (!isNaN(rsi) && rsi > 72)       risks.push(`RSI גבוה (${rsi.toFixed(0)}) — קנוי יתר, סיכון לתיקון`);
  if (!isNaN(shortF) && shortF > 20) risks.push(`שורט גבוה מאוד (${shortF.toFixed(0)}%) — תנודתיות גבוהה`);

  // ── Conclusion ──
  let conclusion = '';
  const tier = score >= 80 ? 'top' : score >= 60 ? 'good' : score >= 40 ? 'spec' : 'risky';
  if      (tier === 'top'  && chg >= 5)  conclusion = 'מניה חזקה עם בסיס איכותי ומומנטום גבוה — ראויה לתשומת לב. לבדוק נזילות ונקודת כניסה.';
  else if (tier === 'top')               conclusion = 'חברה איכותית — ציון בריאות גבוה. מחכה לטריגר טכני לכניסה.';
  else if (tier === 'good' && chg >= 3)  conclusion = 'חברה יציבה עם תנועה חיובית — כדאי לעקוב אחרי המשך.';
  else if (tier === 'spec' && strengths.length >= risks.length)
    conclusion = 'מניה ספקולטיבית אך עם עוצמה — שקול כניסה קטנה עם stop מוגדר.';
  else if (tier === 'spec')              conclusion = 'מניה ספקולטיבית — פוטנציאל גבוה, אבל הסיכונים משמעותיים. גודל פוזיציה קטן.';
  else                                   conclusion = 'מניה בסיכון גבוה — נדרשת זהירות. לא לכניסה ללא catalyst ברור.';

  return { movePoints, strengths, risks, conclusion };
}

// ── Rich expand row ────────────────────────────────────────────────────────────
function ExpandRow({ s, colSpan }) {
  const fmtTs = (ts) => {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleDateString('he-IL', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const epsVal   = parseFloat(s.eps_qq);
  const salesVal = parseFloat(s.sales_qq);
  const hasEps   = !isNaN(epsVal);
  const hasSales = !isNaN(salesVal);
  const verdict  = s.earnings_verdict
    ? { beat: { label: '✅ הכה ציפיות', color: '#4ade80' }, miss: { label: '❌ פספס ציפיות', color: '#f87171' }, inline: { label: '〰️ בציפיות', color: '#fde047' } }[s.earnings_verdict]
    : null;

  const analysis = buildAnalysis(s);

  return (
    <tr>
      <td colSpan={colSpan} style={{ padding: '0', background: '#060c18', borderBottom: '2px solid #1e3a5f' }}>
        <div style={{ display: 'flex', gap: 0, borderTop: '1px solid #1e293b' }}>

          {/* ── Col 1: Stock Analysis ── */}
          <div style={{ flex: '0 0 340px', padding: '14px 16px', borderLeft: '1px solid #1e293b' }}>

            {/* Header: ticker + sector */}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
              <span style={{ fontSize: 13, fontWeight: 900, color: '#f8fafc' }}>📌 {s.ticker}</span>
              {s.sector && (
                <span style={{ fontSize: 10, color: '#64748b' }}>
                  {SECTOR_HE[s.sector] || s.sector}{s.industry ? ` · ${INDUSTRY_HE[s.industry] || s.industry}` : ''}
                </span>
              )}
            </div>

            {/* Business summary */}
            {s.business_summary && (
              <p style={{
                fontSize: 11, color: '#94a3b8', margin: '0 0 10px 0', lineHeight: 1.55,
                borderRight: '2px solid #1e3a5f', paddingRight: 8,
              }}>
                {s.business_summary}
              </p>
            )}

            {/* Why it moved */}
            {analysis.movePoints.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 700, marginBottom: 5, letterSpacing: '0.05em' }}>
                  🔍 למה זזה
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {analysis.movePoints.map((p, i) => (
                    <div key={i} style={{ display: 'flex', gap: 7, alignItems: 'flex-start' }}>
                      <span style={{ color: p.color, fontSize: 10, marginTop: 1, flexShrink: 0 }}>◆</span>
                      <span style={{ fontSize: 11, color: p.color, fontWeight: 600, lineHeight: 1.4 }}>{p.text}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Strengths */}
            {analysis.strengths.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 10, color: '#4ade80', fontWeight: 700, marginBottom: 4 }}>✅ נקודות חוזק</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {analysis.strengths.map((t, i) => (
                    <div key={i} style={{ fontSize: 11, color: '#94a3b8', display: 'flex', gap: 6 }}>
                      <span style={{ color: '#4ade80', flexShrink: 0 }}>+</span>{t}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Risks */}
            {analysis.risks.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, color: '#f87171', fontWeight: 700, marginBottom: 4 }}>⚠️ נקודות סיכון</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {analysis.risks.map((t, i) => (
                    <div key={i} style={{ fontSize: 11, color: '#94a3b8', display: 'flex', gap: 6 }}>
                      <span style={{ color: '#f87171', flexShrink: 0 }}>−</span>{t}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Conclusion */}
            <div style={{
              fontSize: 11, color: '#e2e8f0', lineHeight: 1.5,
              background: '#0a1628', border: '1px solid #1e3a5f',
              borderRadius: 8, padding: '8px 10px',
            }}>
              <span style={{ color: '#60a5fa', fontWeight: 700 }}>💡 מסקנה: </span>
              {analysis.conclusion}
            </div>

            {/* Analyst rec */}
            {(s.analyst_recom || s.target_price) && (
              <div style={{ marginTop: 8, display: 'flex', gap: 12, fontSize: 10, color: '#64748b' }}>
                {s.analyst_recom && <span>👥 {RECOM_HE[s.analyst_recom] || s.analyst_recom}</span>}
                {s.target_price  && <span>🎯 יעד: <span style={{ color: '#60a5fa', fontWeight: 700 }}>${s.target_price}</span></span>}
              </div>
            )}
          </div>

          {/* ── Col 2: Earnings ── */}
          <div style={{ flex: '0 0 200px', padding: '12px 14px', borderLeft: '1px solid #1e293b' }}>
            <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 700, marginBottom: 8, letterSpacing: '0.05em' }}>
              📊 דוחות
            </div>
            {(verdict || hasEps || hasSales || s.earnings_date) ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {verdict && (
                  <span style={{ fontSize: 12, color: verdict.color, fontWeight: 700 }}>
                    {verdict.label}
                  </span>
                )}
                {hasEps && (
                  <div style={{ fontSize: 11, fontFamily: 'monospace', color: epsVal > 0 ? '#4ade80' : '#f87171' }}>
                    EPS רבעוני: {epsVal > 0 ? '+' : ''}{epsVal.toFixed(1)}%
                  </div>
                )}
                {hasSales && (
                  <div style={{ fontSize: 11, fontFamily: 'monospace', color: salesVal > 0 ? '#4ade80' : '#f87171' }}>
                    הכנסות Q/Q: {salesVal > 0 ? '+' : ''}{salesVal.toFixed(1)}%
                  </div>
                )}
                {s.earnings_date && (
                  <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 3 }}>
                    📅 דוח הבא: <span style={{ color: '#94a3b8' }}>{fmtEarningsDate(s.earnings_date)}</span>
                  </div>
                )}
                {(s.perf_week || s.perf_month) && (
                  <div style={{ marginTop: 5, display: 'flex', gap: 8 }}>
                    {s.perf_week && (
                      <div style={{ fontSize: 10 }}>
                        <span style={{ color: '#94a3b8' }}>7י׳ </span>
                        <span style={{ color: parseFloat(s.perf_week) > 0 ? '#4ade80' : '#f87171', fontFamily: 'monospace', fontWeight: 700 }}>{s.perf_week}</span>
                      </div>
                    )}
                    {s.perf_month && (
                      <div style={{ fontSize: 10 }}>
                        <span style={{ color: '#94a3b8' }}>30י׳ </span>
                        <span style={{ color: parseFloat(s.perf_month) > 0 ? '#4ade80' : '#f87171', fontFamily: 'monospace', fontWeight: 700 }}>{s.perf_month}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <span style={{ fontSize: 11, color: '#94a3b8' }}>אין נתוני דוחות</span>
            )}
          </div>

          {/* ── Col 3: Company + news ── */}
          <div style={{ flex: 1, padding: '12px 14px', minWidth: 0 }}>
            <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 700, marginBottom: 8, letterSpacing: '0.05em' }}>
              📰 חדשות אחרונות
            </div>

            {/* Business summary */}
            {s.business_summary && (
              <p style={{
                fontSize: 11, color: '#94a3b8', margin: '0 0 8px 0',
                lineHeight: 1.5, fontStyle: 'italic',
                borderRight: '2px solid #1e3a5f', paddingRight: 8,
              }}>
                {s.business_summary}
              </p>
            )}

            {/* News list */}
            {s.news?.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {s.news.slice(0, 4).map((n, i) => (
                  <a
                    key={i}
                    href={n.link || '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={e => e.stopPropagation()}
                    style={{
                      display: 'flex', gap: 8, alignItems: 'flex-start',
                      textDecoration: 'none', padding: '5px 8px', borderRadius: 6,
                      background: '#0d1626', border: '1px solid #1e293b',
                      transition: 'border-color 0.15s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.borderColor = '#3b82f6'}
                    onMouseLeave={e => e.currentTarget.style.borderColor = '#1e293b'}
                  >
                    <span style={{ color: '#94a3b8', fontSize: 9, minWidth: 12, paddingTop: 2 }}>{i + 1}.</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ color: '#cbd5e1', fontSize: 11, margin: 0, lineHeight: 1.4 }}>
                        {n.title}
                      </p>
                      <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
                        {n.publisher && <span style={{ color: '#94a3b8', fontSize: 9 }}>{n.publisher}</span>}
                        {n.published && <span style={{ color: '#94a3b8', fontSize: 9 }}>{fmtTs(n.published)}</span>}
                      </div>
                    </div>
                    <span style={{ color: '#3b82f6', fontSize: 10, flexShrink: 0 }}>↗</span>
                  </a>
                ))}
              </div>
            ) : (
              <span style={{ fontSize: 11, color: '#94a3b8' }}>אין חדשות זמינות</span>
            )}
          </div>

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

// ── Demo Portfolio ─────────────────────────────────────────────────────────────
function useDemoPortfolio() {
  const [positions, setPositions] = useState(() => {
    try { return JSON.parse(localStorage.getItem('demoPortfolio_v1') || '{}'); }
    catch { return {}; }
  });

  // Sync to localStorage whenever positions change (avoids stale closure writes)
  useEffect(() => {
    localStorage.setItem('demoPortfolio_v1', JSON.stringify(positions));
  }, [positions]);

  const buy = useCallback((ticker, price, qty) => {
    setPositions(prev => {
      const pos = { ...prev };
      if (pos[ticker]?.side === 'long') {
        const total = pos[ticker].qty + qty;
        pos[ticker] = { side: 'long', qty: total, avgPrice: (pos[ticker].avgPrice * pos[ticker].qty + price * qty) / total };
      } else {
        pos[ticker] = { side: 'long', qty, avgPrice: price };
      }
      return pos;
    });
  }, []);

  const short = useCallback((ticker, price, qty) => {
    setPositions(prev => {
      const pos = { ...prev };
      if (pos[ticker]?.side === 'short') {
        const total = pos[ticker].qty + qty;
        pos[ticker] = { side: 'short', qty: total, avgPrice: (pos[ticker].avgPrice * pos[ticker].qty + price * qty) / total };
      } else {
        pos[ticker] = { side: 'short', qty, avgPrice: price };
      }
      return pos;
    });
  }, []);

  const closePosition = useCallback((ticker) => {
    setPositions(prev => {
      const pos = { ...prev };
      delete pos[ticker];
      return pos;
    });
  }, []);

  return { positions, buy, short, closePosition };
}

// ── Buy/Sell cell ──────────────────────────────────────────────────────────────
function BuySellCell({ ticker, price, positions, onBuy, onShort, onClose }) {
  const [open, setOpen] = useState(false);
  const [qty, setQty] = useState('10');
  const pos = positions[ticker];
  const currentPnlPct = pos
    ? pos.side === 'long'
      ? ((price - pos.avgPrice) / pos.avgPrice * 100)
      : ((pos.avgPrice - price) / pos.avgPrice * 100)
    : null;
  const pnlColor = currentPnlPct > 0 ? '#4ade80' : currentPnlPct < 0 ? '#f87171' : '#94a3b8';

  return (
    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }} onClick={e => e.stopPropagation()}>
      <button
        onClick={() => setOpen(o => !o)}
        title={pos ? 'ניהול פוזיציה' : 'קנה / שורט'}
        style={{
          width: 22, height: 22, borderRadius: 4, border: `1px solid ${pos ? (pos.side === 'long' ? '#166534' : '#7f1d1d') : '#1e293b'}`,
          background: pos ? (pos.side === 'long' ? '#052e16' : '#2d0a0a') : '#0d1626',
          color: pos ? (pos.side === 'long' ? '#4ade80' : '#f87171') : '#475569',
          cursor: 'pointer', fontSize: 11, lineHeight: 1,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        {pos ? (pos.side === 'long' ? '▲' : '▼') : '+'}
      </button>
      {pos && currentPnlPct !== null && (
        <span style={{ fontSize: 9, color: pnlColor, fontFamily: 'monospace', fontWeight: 700 }}>
          {currentPnlPct > 0 ? '+' : ''}{currentPnlPct.toFixed(1)}%
        </span>
      )}
      {open && (
        <div style={{
          position: 'absolute', zIndex: 999, top: '110%', left: 0,
          background: '#0f172a', border: '1px solid #3b82f6', borderRadius: 10,
          padding: '12px', minWidth: 170, boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        }}>
          <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
            <span style={{ fontWeight: 700, color: '#f8fafc' }}>{ticker}</span>
            {' '}${price?.toFixed(2)}
          </div>
          <input
            type="number" value={qty} min="1"
            onChange={e => setQty(e.target.value)}
            style={{
              width: '100%', background: '#1e293b', border: '1px solid #334155',
              color: '#e2e8f0', borderRadius: 6, padding: '5px 8px', fontSize: 12,
              marginBottom: 8, outline: 'none', boxSizing: 'border-box',
            }}
            placeholder="כמות מניות"
          />
          {pos ? (
            <>
              <div style={{ fontSize: 11, color: pnlColor, fontWeight: 700, textAlign: 'center', marginBottom: 8 }}>
                {pos.side === 'long' ? '📈 Long' : '📉 Short'} · {pos.qty} יח׳ · כניסה ${pos.avgPrice.toFixed(2)}
                <div>{currentPnlPct > 0 ? '+' : ''}{currentPnlPct.toFixed(2)}% ({((price - pos.avgPrice) * pos.qty * (pos.side === 'long' ? 1 : -1)).toFixed(0)}$)</div>
              </div>
              <button onClick={() => { onClose(ticker); setOpen(false); }} style={{
                width: '100%', padding: '6px', background: '#2d0a0a', border: '1px solid #ef4444',
                color: '#fca5a5', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 700,
              }}>
                ✕ סגור פוזיציה
              </button>
            </>
          ) : (
            <>
              <button onClick={() => { onBuy(ticker, price, parseFloat(qty) || 1); setOpen(false); }} style={{
                width: '100%', padding: '6px', background: '#052e16', border: '1px solid #22c55e',
                color: '#4ade80', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 700, marginBottom: 6,
              }}>
                📈 קנה (Long)
              </button>
              <button onClick={() => { onShort(ticker, price, parseFloat(qty) || 1); setOpen(false); }} style={{
                width: '100%', padding: '6px', background: '#2d0a0a', border: '1px solid #ef4444',
                color: '#f87171', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 700,
              }}>
                📉 שורט (Short)
              </button>
            </>
          )}
          <button onClick={() => setOpen(false)} style={{
            width: '100%', marginTop: 6, padding: '4px', background: 'transparent',
            border: 'none', color: '#475569', cursor: 'pointer', fontSize: 10,
          }}>
            סגור ✕
          </button>
        </div>
      )}
    </div>
  );
}

// ── Portfolio Panel ────────────────────────────────────────────────────────────
function PortfolioPanel({ positions, stockMap, portfolioPrices, onClose }) {
  const tickers = Object.keys(positions);
  if (tickers.length === 0) return null;

  let totalPnl = 0;
  const rows = tickers.map(ticker => {
    const pos = positions[ticker];
    const fvPrice = portfolioPrices?.[ticker]?.price;
    const cur = fvPrice ?? stockMap[ticker] ?? pos.avgPrice;
    const priceSource = fvPrice ? 'live' : stockMap[ticker] ? 'screener' : 'fallback';
    const diff = pos.side === 'long' ? cur - pos.avgPrice : pos.avgPrice - cur;
    const pnl = diff * pos.qty;
    const pnlPct = (diff / pos.avgPrice) * 100;
    totalPnl += pnl;
    return { ticker, pos, cur, pnl, pnlPct, priceSource };
  });

  return (
    <div style={{ marginTop: 12, padding: 12, border: '1px solid #334155', borderRadius: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <h3 style={{ color: '#e2e8f0', fontSize: 13, fontWeight: 700, margin: 0 }}>💼 תיק דמו</h3>
        <span style={{ fontSize: 13, fontWeight: 700, color: totalPnl >= 0 ? '#4ade80' : '#f87171', fontFamily: 'monospace' }}>
          סה"כ: {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}$
        </span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }} dir="rtl">
          <thead>
            <tr style={{ borderBottom: '2px solid #334155' }}>
              {['מניה','כיוון','כמות','כניסה','עכשיו','רווח/הפסד','%',''].map(h => (
                <th key={h} style={{ textAlign: 'right', padding: '8px 10px', color: '#e2e8f0', fontWeight: 700, fontSize: 12, whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ ticker, pos, cur, pnl, pnlPct, priceSource }) => {
              const c = pnl > 0 ? '#4ade80' : pnl < 0 ? '#f87171' : '#cbd5e1';
              return (
                <tr key={ticker} style={{ borderBottom: '1px solid #1e293b' }}>
                  <td style={{ padding: '8px 10px', fontWeight: 800, color: '#f8fafc', fontSize: 13 }}>{ticker}</td>
                  <td style={{ padding: '8px 10px', color: pos.side === 'long' ? '#4ade80' : '#f87171', fontWeight: 700, fontSize: 12 }}>
                    {pos.side === 'long' ? '📈 Long' : '📉 Short'}
                  </td>
                  <td style={{ padding: '8px 10px', color: '#e2e8f0', fontFamily: 'monospace', fontSize: 12 }}>{pos.qty}</td>
                  <td style={{ padding: '8px 10px', color: '#cbd5e1', fontFamily: 'monospace', fontSize: 12 }}>${pos.avgPrice.toFixed(2)}</td>
                  <td style={{ padding: '8px 10px', fontFamily: 'monospace', fontWeight: 700, fontSize: 12 }}>
                    <span style={{ color: '#f1f5f9' }}>▲ ${cur.toFixed(2)}</span>
                    {priceSource === 'live' && (
                      <span style={{ fontSize: 10, color: '#4ade80', marginRight: 3 }} title="מחיר לייב">●</span>
                    )}
                    {priceSource === 'fallback' && (
                      <span style={{ fontSize: 10, color: '#f87171', marginRight: 3 }} title="מחיר לא מעודכן">⚠️</span>
                    )}
                  </td>
                  <td style={{ padding: '8px 10px', color: c, fontFamily: 'monospace', fontWeight: 700, fontSize: 12 }}>
                    {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}$
                  </td>
                  <td style={{ padding: '8px 10px', color: c, fontFamily: 'monospace', fontWeight: 700, fontSize: 12 }}>
                    {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                  </td>
                  <td style={{ padding: '7px 10px' }}>
                    <button onClick={() => onClose(ticker)} style={{
                      fontSize: 10, padding: '3px 8px', background: '#1e293b',
                      border: '1px solid #334155', color: '#94a3b8', borderRadius: 4, cursor: 'pointer',
                    }}>✕ סגור</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Sector translation ─────────────────────────────────────────────────────────
const SECTOR_HE = {
  'Technology': 'טכנולוגיה',
  'Healthcare': 'בריאות',
  'Financial': 'פיננסים',
  'Financial Services': 'שירותים פיננסיים',
  'Consumer Cyclical': 'צרכנות מחזורית',
  'Consumer Defensive': 'צרכנות הגנתית',
  'Industrials': 'תעשייה',
  'Communication Services': 'תקשורת',
  'Energy': 'אנרגיה',
  'Basic Materials': 'חומרי גלם',
  'Real Estate': 'נדל"ן',
  'Utilities': 'תשתיות',
};

// ── Industry translation ───────────────────────────────────────────────────────
const INDUSTRY_HE = {
  'Communication Equipment': 'ציוד תקשורת',
  'Software—Application': 'תוכנה - יישומים',
  'Software—Infrastructure': 'תוכנה - תשתיות',
  'Semiconductors': 'מוליכים למחצה',
  'Semiconductor Equipment': 'ציוד מוליכים',
  'Electronic Components': 'רכיבים אלקטרוניים',
  'Scientific & Technical Instruments': 'מכשירים מדעיים',
  'Computer Hardware': 'חומרת מחשב',
  'Information Technology Services': 'שירותי IT',
  'Biotechnology': 'ביוטכנולוגיה',
  'Drug Manufacturers—General': 'תרופות - כללי',
  'Drug Manufacturers—Specialty & Generic': 'תרופות - גנריות',
  'Medical Devices': 'מכשור רפואי',
  'Diagnostics & Research': 'אבחון ומחקר',
  'Health Information Services': 'מידע רפואי',
  'Medical Care Facilities': 'מוסדות רפואיים',
  'Banks—Regional': 'בנקים אזוריים',
  'Banks—Diversified': 'בנקים מגוונים',
  'Capital Markets': 'שוק ההון',
  'Asset Management': 'ניהול נכסים',
  'Insurance—Life': 'ביטוח חיים',
  'Insurance—Property & Casualty': 'ביטוח רכוש',
  'Credit Services': 'שירותי אשראי',
  'Oil & Gas E&P': 'נפט וגז - חיפוש',
  'Oil & Gas Integrated': 'נפט וגז משולב',
  'Oil & Gas Midstream': 'נפט וגז - הולכה',
  'Specialty Retail': 'קמעונאות מיוחדת',
  'Internet Retail': 'קמעונאות מקוונת',
  'Grocery Stores': 'סופרמרקטים',
  'Aerospace & Defense': 'תעופה וביטחון',
  'Industrial Distribution': 'הפצה תעשייתית',
  'Electrical Equipment & Parts': 'ציוד חשמלי',
  'REIT—Retail': 'נדל"ן מסחרי',
  'REIT—Residential': 'נדל"ן למגורים',
  'REIT—Industrial': 'נדל"ן תעשייתי',
  'REIT—Office': 'נדל"ן משרדים',
  'Telecom Services': 'שירותי תקשורת',
  'Entertainment': 'בידור',
  'Advertising Agencies': 'סוכנויות פרסום',
  'Auto Manufacturers': 'יצרני רכב',
  'Auto Parts': 'חלקי רכב',
  'Restaurants': 'מסעדות',
  'Airlines': 'חברות תעופה',
  'Lodging': 'מלונאות',
  'Residential Construction': 'בנייה למגורים',
};

// ── Earnings date formatter ────────────────────────────────────────────────────
const MONTH_HE = {
  Jan: 'ינו׳', Feb: 'פבר׳', Mar: 'מרץ', Apr: 'אפר׳',
  May: 'מאי',  Jun: 'יונ׳', Jul: 'יול׳', Aug: 'אוג׳',
  Sep: 'ספט׳', Oct: 'אוק׳', Nov: 'נוב׳', Dec: 'דצמ׳',
};
function fmtEarningsDate(d) {
  if (!d) return d;
  let s = d;
  Object.entries(MONTH_HE).forEach(([en, he]) => { s = s.replace(en, he); });
  s = s.replace('AMC', '| אחרי סגירה').replace('BMO', '| לפני פתיחה');
  return s;
}

// ── Analyst recommendation translation ────────────────────────────────────────
const RECOM_HE = {
  'Buy': 'קנה', 'Strong Buy': 'קנה חזק', 'Sell': 'מכור', 'Strong Sell': 'מכור חזק',
  'Hold': 'החזק', 'Outperform': 'מעל שוק', 'Underperform': 'מתחת לשוק',
  'Neutral': 'ניטרלי', 'Overweight': 'משקל יתר', 'Underweight': 'משקל חסר',
  'Equal Weight': 'משקל שווה',
};

// ── Session detection ──────────────────────────────────────────────────────────
const SESSION_META = {
  pre:     { label: '🌅 טרום מסחר', color: '#fb923c', bg: '#1c0f00', border: '#92400e' },
  regular: { label: '📈 מסחר רגיל', color: '#4ade80', bg: '#052e16', border: '#166534' },
  post:    { label: '🌆 אחרי שעות', color: '#818cf8', bg: '#1e1b4b', border: '#4338ca' },
  closed:  { label: '⏸ שוק סגור',  color: '#94a3b8', bg: '#0f172a', border: '#1e293b' },
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
  // ברירת מחדל תואמת ל-Finviz Elite של המשתמש:
  // cap_midover, sh_avgvol_o2000, sh_curvol_o300, sh_instown_o10, ta_rsi_nos50
  // ללא פילטר שורט וללא פילטר change — כמו ב-Finviz
  const [mcap,   setMcap]   = useState('cap_midover');
  const [avgvol, setAvgvol] = useState('sh_avgvol_o2000');
  const [relvol, setRelvol] = useState('');
  const [curvol, setCurvol] = useState('sh_curvol_o300');
  const [change, setChange] = useState('');
  const [changeopen, setChangeopen] = useState('');
  const [customChangePct, setCustomChangePct] = useState('3');
  const [showChangeList, setShowChangeList] = useState(false);
  const [shortf, setShortf] = useState('');
  const [rsi,    setRsi]    = useState('ta_rsi_nos50');
  const [inst,   setInst]   = useState('sh_instown_o10');
  const [salesqq, setSalesqq] = useState('');
  const [sort,   setSort]   = useState({ col: 'change_pct', dir: 'desc' });
  const [expanded, setExpanded] = useState(new Set());
  const { positions, buy, short, closePosition } = useDemoPortfolio();
  const [countdown, setCountdown] = useState(REFRESH_SEC);
  const countdownRef = useRef(REFRESH_SEC);

  // ── Live prices (pre/post market, flash animation) ──────────────────────────
  const [livePrices, setLivePrices] = useState({});           // {ticker: {price}}
  const [priceFlashes, setPriceFlashes] = useState({});       // {ticker: 'up'|'down'}
  const prevLivePricesRef = useRef({});
  const screenerTickersRef = useRef([]);

  const filters = buildFilters(mcap, avgvol, relvol, curvol, change, changeopen, shortf, rsi, inst, salesqq);

  // Live prices for portfolio tickers — uses same batch endpoint as table (reliable)
  const portfolioTickers = Object.keys(positions);
  const { data: portfolioPricesData } = useQuery({
    queryKey: ['portfolioPrices', portfolioTickers.join(',')],
    queryFn: () =>
      portfolioTickers.length > 0
        ? api.get(`/screener/live-prices?tickers=${portfolioTickers.join(',')}`).then(r => r.data)
        : Promise.resolve({}),
    enabled: portfolioTickers.length > 0,
    refetchInterval: 10 * 1000,
    staleTime: 0,
  });

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

  // Keep screener tickers ref in sync (used by live poll)
  useEffect(() => {
    screenerTickersRef.current = stocks.map(s => s.ticker);
  }, [stocks]);

  // Live price polling — every 10s, batch yfinance (pre/post market aware)
  useEffect(() => {
    const poll = async () => {
      const tickers = screenerTickersRef.current;
      if (!tickers.length) return;
      try {
        const r = await api.get(`/screener/live-prices?tickers=${tickers.slice(0, 25).join(',')}`);
        const newPrices = r.data;
        if (!newPrices || !Object.keys(newPrices).length) return;

        // Detect changes → flash
        const flashes = {};
        Object.entries(newPrices).forEach(([ticker, d]) => {
          const prev = prevLivePricesRef.current[ticker]?.price;
          const cur  = d?.price;
          if (prev != null && cur != null && Math.abs(cur - prev) > 0.001) {
            flashes[ticker] = cur > prev ? 'up' : 'down';
          }
        });

        prevLivePricesRef.current = newPrices;
        setLivePrices(newPrices);

        if (Object.keys(flashes).length) {
          setPriceFlashes(flashes);
          setTimeout(() => setPriceFlashes({}), 700);
        }
      } catch (_) {}
    };

    poll();
    const id = setInterval(poll, 10_000);
    return () => clearInterval(id);
  }, []); // mount once — reads tickers from ref
  // Session: prefer client-side time (always fresh), use API response as fallback
  const session = useMemo(() => data ? getClientSession() : 'regular', [dataUpdatedAt]); // eslint-disable-line
  const sessionMeta = SESSION_META[session] || SESSION_META.regular;
  const isExtended  = session === 'pre' || session === 'post';

  const sorted = useMemo(() => {
    if (!stocks.length) return [];
    let list = stocks.filter(s => {
      const t = (s.ticker != null ? String(s.ticker).trim() : '');
      if (!t) return false;
      if (/^\d+$/.test(t)) return false; // טיקר שהוא רק ספרות (למשל "6") — שגיאה מהשרת, לא להציג
      return true;
    });
    // הסרת כפילויות לפי טיקר (משאירים רק הופעה ראשונה)
    const seen = new Set();
    list = list.filter(s => {
      const t = (s.ticker || '').trim().toUpperCase();
      if (seen.has(t)) return false;
      seen.add(t);
      return true;
    });
    // סינון לפי ערך שינוי מותאם (ידני)
    if (change === 'custom' && customChangePct !== '' && !isNaN(parseFloat(customChangePct))) {
      const minPct = parseFloat(customChangePct);
      list = list.filter(s => {
        const chg = isExtended && s.extended_chg_pct != null ? parseFloat(s.extended_chg_pct) : parseFloat(s.change_pct);
        return !isNaN(chg) && chg >= minPct;
      });
    }
    return list.sort((a, b) => {
      let av = a[sort.col], bv = b[sort.col];
      if (sort.col === 'change_pct' && isExtended) {
        av = a.extended_chg_pct != null ? a.extended_chg_pct : av;
        bv = b.extended_chg_pct != null ? b.extended_chg_pct : bv;
      }
      av = parseFloat(av); bv = parseFloat(bv);
      av = isNaN(av) ? -Infinity : av;
      bv = isNaN(bv) ? -Infinity : bv;
      return sort.dir === 'desc' ? bv - av : av - bv;
    });
  }, [stocks, sort, change, customChangePct, isExtended]);

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

  const COL_COUNT = 17; // expand + # + ticker + sector + price + chg% + 5m + 10m + 30m + vol + mcap + eps + salesqq + rsi + short + health + tags + portfolio
  const stockMap = useMemo(() => {
    const m = {};
    stocks.forEach(s => { if (s.price) m[s.ticker] = s.price; });
    return m;
  }, [stocks]);

  const thBase = { background: '#1e293b', borderBottom: '2px solid #334155', color: '#e2e8f0', padding: '8px 10px', fontSize: 12, fontWeight: 700, whiteSpace: 'nowrap' };
  const tdBase = { padding: '6px 10px', borderBottom: '1px solid #1e293b', textAlign: 'right', fontSize: 12, color: '#e2e8f0', whiteSpace: 'nowrap' };

  return (
    <div
      style={{
        color: '#e2e8f0',
        background: '#0f172a',
        border: '1px solid #334155',
        borderRadius: 12,
        overflow: 'hidden',
      }}
      dir="rtl"
    >
      {/* ── Bar: title + meta + refresh ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '12px 16px',
          background: '#1e293b',
          borderBottom: '1px solid #334155',
        }}
      >
        <h2 style={{ fontSize: 15, fontWeight: 700, color: '#cbd5e1', margin: 0, letterSpacing: '0.03em' }}>SCREENER</h2>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {data && <span style={{ fontSize: 13, color: '#94a3b8' }}>{sorted.length} מניות</span>}
          {data && (
            <span style={{ fontSize: 11, padding: '3px 8px', borderRadius: 6, background: sessionMeta.bg, color: sessionMeta.color, fontWeight: 600 }}>
              {sessionMeta.label}
            </span>
          )}
          {isLoading && <span style={{ fontSize: 12, color: '#60a5fa' }}>טוען...</span>}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <CountdownRing seconds={countdown} total={REFRESH_SEC} />
            <span style={{ fontSize: 12, color: '#64748b', fontFamily: 'monospace' }}>{countdown}s</span>
            <button
              onClick={() => { refetch(); countdownRef.current = REFRESH_SEC; setCountdown(REFRESH_SEC); }}
              disabled={isLoading}
              style={{
                fontSize: 12, padding: '6px 12px', borderRadius: 6, background: '#334155', border: 'none',
                color: '#e2e8f0', cursor: isLoading ? 'not-allowed' : 'pointer', opacity: isLoading ? 0.6 : 1,
              }}
            >
              רענן
            </button>
          </div>
        </div>
      </div>

      {/* ── Filters: Finviz-style inline bar ── */}
      <div style={{
        padding: '8px 16px',
        background: '#0d1627',
        borderBottom: '1px solid #1e293b',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: '6px 14px',
      }}>
        <FilterItem label="Market Cap." options={MCAP_OPTS} value={mcap} onChange={v => { setMcap(v); setExpanded(new Set()); }} />
        <div style={{ width: 1, height: 16, background: '#1e293b', flexShrink: 0 }} />
        <FilterItem label="Avg Vol." options={AVGVOL_OPTS} value={avgvol} onChange={v => { setAvgvol(v); setExpanded(new Set()); }} />
        <FilterItem label="Cur Vol." options={CURVOL_OPTS} value={curvol} onChange={v => { setCurvol(v); setExpanded(new Set()); }} />
        <FilterItem label="Rel Vol." options={RELVOL_OPTS} value={relvol} onChange={v => { setRelvol(v); setExpanded(new Set()); }} />
        <div style={{ width: 1, height: 16, background: '#1e293b', flexShrink: 0 }} />
        <FilterItem label="Chg from Open" options={CHANGEOPEN_OPTS} value={changeopen} onChange={v => { setChangeopen(v); setExpanded(new Set()); }} />
        {/* Change — supports both dropdown and custom % input */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={fvLabelStyle(change !== '')}>Change</span>
          {change === 'custom' && !showChangeList ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <input
                type="number"
                placeholder="%"
                value={customChangePct}
                onChange={e => setCustomChangePct(e.target.value)}
                min={0} step={0.5}
                style={fvNumInput}
              />
              <button
                type="button"
                onClick={() => setShowChangeList(true)}
                style={{ fontSize: 10, color: '#64748b', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
              >▼</button>
            </div>
          ) : (
            <select
              value={change}
              onChange={e => { const v = e.target.value; setChange(v); if (v === 'custom') setShowChangeList(false); setExpanded(new Set()); }}
              style={fvSelectStyle(change !== '')}
            >
              {CHANGE_OPTS.map(o => (
                <option key={o.value ?? 'any'} value={o.value}>{o.label}</option>
              ))}
            </select>
          )}
        </div>
        <div style={{ width: 1, height: 16, background: '#1e293b', flexShrink: 0 }} />
        <FilterItem label="Sales Q/Q" options={SALESQQ_OPTS} value={salesqq} onChange={v => { setSalesqq(v); setExpanded(new Set()); }} />
        <FilterItem label="Short Float" options={SHORT_OPTS} value={shortf} onChange={v => { setShortf(v); setExpanded(new Set()); }} />
        <FilterItem label="RSI (14)" options={RSI_OPTS} value={rsi} onChange={v => { setRsi(v); setExpanded(new Set()); }} />
        <FilterItem label="Inst. Own." options={INST_OPTS} value={inst} onChange={v => { setInst(v); setExpanded(new Set()); }} />
      </div>

      {isError && (
        <div style={{ padding: 12, marginBottom: 10, background: '#7f1d1d', color: '#fecaca', fontSize: 12, borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 }}>
          <span>שגיאה — וודא ש-backend רץ (למשל פורט 8000) ולחץ רענן</span>
          <button
            onClick={() => refetch()}
            style={{ padding: '6px 12px', background: '#b91c1c', border: 'none', color: '#fff', borderRadius: 6, cursor: 'pointer', fontWeight: 600 }}
          >
            רענן
          </button>
        </div>
      )}
      {/* Global animations */}
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes starBlink {
          0%, 100% { background: rgba(34,197,94,0.12); }
          50% { background: rgba(34,197,94,0.45); }
        }
        @keyframes starBorderPulse {
          0%, 100% { border-left-color: rgba(34,197,94,0.6); }
          50% { border-left-color: #4ade80; }
        }
        tr.star-stock td { animation: starBlink 1.2s ease-in-out infinite; }
        tr.star-stock td:first-child { border-left: 3px solid #22c55e; animation: starBlink 1.2s ease-in-out infinite, starBorderPulse 1.2s ease-in-out infinite; }
        .finviz-scroll::-webkit-scrollbar { height: 8px; }
        .finviz-scroll::-webkit-scrollbar-track { background: #1e293b; border-radius: 4px; }
        .finviz-scroll::-webkit-scrollbar-thumb { background: #475569; border-radius: 4px; }
        .finviz-scroll::-webkit-scrollbar-thumb:hover { background: #64748b; }
        @keyframes flashUp {
          0%   { background: rgba(74,222,128,0.55); color: #fff; }
          100% { background: transparent; }
        }
        @keyframes flashDown {
          0%   { background: rgba(248,113,113,0.55); color: #fff; }
          100% { background: transparent; }
        }
        .price-flash-up   { animation: flashUp   0.7s ease-out; border-radius: 3px; }
        .price-flash-down { animation: flashDown 0.7s ease-out; border-radius: 3px; }
        .fv-table td { border-left: 1px solid #1e293b; }
        .fv-table td:first-child { border-left: none; }
        .fv-table tbody tr:hover td { background: #172033 !important; }
      `}</style>

      {isLoading && !stocks.length && (
        <div style={{ textAlign: 'center', padding: 40, color: '#64748b', fontSize: 12 }}>
          <div style={{ width: 24, height: 24, border: '2px solid #334155', borderTopColor: '#60a5fa', borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 8px' }} />
          טוען...
        </div>
      )}
      {!isLoading && !isError && stocks.length === 0 && (
        <div style={{ textAlign: 'center', padding: 40, color: '#64748b', fontSize: 12 }}>לא נמצאו מניות</div>
      )}

      {sorted.length > 0 && (
        <div className="finviz-scroll" style={{ overflowX: 'auto' }}>
          <table className="fv-table" style={{ width: '100%', minWidth: 1080, borderCollapse: 'collapse', fontSize: 12, tableLayout: 'fixed' }}>
            <thead>
              <tr>
                <th style={{ ...thBase, width: 26, padding: '6px 2px' }} />
                <th style={{ ...thBase, width: 26, textAlign: 'center' }}>#</th>
                <SortTh label="מניה"     col="ticker"       sort={sort} onSort={handleSort} style={{ width: 64 }} />
                <SortTh label="סקטור"   col="sector"       sort={sort} onSort={handleSort} style={{ width: 74 }} />
                <SortTh label="מחיר"     col="price"        sort={sort} onSort={handleSort} style={{ width: 68 }} />
                <SortTh label="שינוי%"   col="change_pct"   sort={sort} onSort={handleSort} style={{ width: 72 }} sub={isExtended ? 'טרום' : null} />
                <SortTh label="5דק"     col="chg_5m"       sort={sort} onSort={handleSort} style={{ width: 44 }} />
                <SortTh label="10דק"    col="chg_10m"      sort={sort} onSort={handleSort} style={{ width: 44 }} />
                <SortTh label="30דק"    col="chg_30m"      sort={sort} onSort={handleSort} style={{ width: 44 }} />
                <SortTh label="נפח"     col="volume"       sort={sort} onSort={handleSort} style={{ width: 50 }} />
                <SortTh label="שווי"    col="market_cap"   sort={sort} onSort={handleSort} style={{ width: 62 }} />
                <SortTh label="בריאות"  col="health_score" sort={sort} onSort={handleSort} style={{ width: 92 }} />
                <SortTh label="RSI"      col="rsi"          sort={sort} onSort={handleSort} style={{ width: 38 }} />
                <SortTh label="שורט%"   col="short_float"  sort={sort} onSort={handleSort} style={{ width: 48 }} />
                <SortTh label="EPS"      col="eps_this_y"   sort={sort} onSort={handleSort} style={{ width: 54 }} />
                <SortTh label="S Q/Q"    col="sales_qq"     sort={sort} onSort={handleSort} style={{ width: 54 }} />
                <th style={{ ...thBase, width: 88, textAlign: 'right' }}>תגיות</th>
                <th style={{ ...thBase, width: 34, textAlign: 'center' }}>💼</th>
              </tr>
            </thead>

            <tbody>
              {sorted.map((s, i) => {
                const chg = isExtended && s.extended_chg_pct != null ? parseFloat(s.extended_chg_pct) : (parseFloat(s.change_pct) || 0);
                const isStar = (s.health_score >= 80) && (chg >= 8);
                const isOpen = expanded.has(s.ticker);
                const rowBg = i % 2 === 0 ? '#0f172a' : 'rgba(30,41,59,0.4)';

                return [
                  <tr
                    key={`row-${i}-${s.ticker}`}
                    className={isStar ? 'star-stock' : ''}
                    style={{ background: rowBg, cursor: 'pointer' }}
                    onClick={() => window.open(`https://finviz.com/quote.ashx?t=${s.ticker}`, '_blank')}
                    onMouseEnter={e => { e.currentTarget.style.background = '#1e293b'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = rowBg; }}
                  >
                    {/* Expand toggle — always visible */}
                    <td style={{ ...tdBase, textAlign: 'center', padding: '4px 2px' }}>
                      <button
                        onClick={e => toggleExpand(s.ticker, e)}
                        title={isOpen ? 'סגור פרטים' : 'הצג חדשות / דוחות / סיבות'}
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
                    </td>

                    {/* # */}
                    <td style={{ ...tdBase, color: '#94a3b8', fontSize: 11 }}>{i + 1}</td>

                    {/* Ticker — צר; שם החברה ב-tooltip */}
                    <td style={{ ...tdBase, padding: '4px 6px', overflow: 'hidden' }} title={s.company || s.ticker || ''}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 2, overflow: 'hidden' }}>
                        <span style={{ fontWeight: 800, color: '#fff', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.ticker?.trim() || '—'}</span>
                        {isStar && <span style={{ fontSize: 10, flexShrink: 0 }} title="Health ≥80 + עליה ≥8%">⭐</span>}
                      </div>
                    </td>

                    {/* Sector — שורה אחת, קיצור */}
                    <td style={{ ...tdBase, overflow: 'hidden' }}>
                      {s.sector ? (
                        <span
                          title={(SECTOR_HE[s.sector] || s.sector) + (s.industry ? ' · ' + (INDUSTRY_HE[s.industry] || s.industry) : '')}
                          style={{ fontSize: 11, color: '#94a3b8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', display: 'block' }}
                        >
                          {SECTOR_HE[s.sector] || s.sector}
                        </span>
                      ) : <span style={{ color: '#94a3b8' }}>—</span>}
                    </td>

                    {/* Price */}
                    <td style={{ ...tdBase, overflow: 'hidden' }}>
                      {(() => {
                        const liveP = livePrices[s.ticker]?.price;
                        const extP  = s.extended_price ? parseFloat(s.extended_price) : null;
                        const regP  = s.price ? parseFloat(s.price) : null;
                        const displayPrice = liveP ?? extP ?? regP;
                        const flash = priceFlashes[s.ticker];
                        const isLive = liveP != null;
                        return (
                          <>
                            <span
                              className={flash === 'up' ? 'price-flash-up' : flash === 'down' ? 'price-flash-down' : ''}
                              style={{ fontFamily: 'monospace', fontWeight: 700, color: '#e2e8f0', fontSize: 11, display: 'inline-block', padding: '1px 3px' }}
                            >
                              {displayPrice != null ? `$${displayPrice.toFixed(2)}` : '—'}
                            </span>
                            {isLive && (
                              <div style={{ fontSize: 9, color: sessionMeta.color, opacity: 0.85, lineHeight: 1.2 }}>
                                {session === 'pre' ? '🌅 פרה' : session === 'post' ? '🌆 פוסט' : '● live'}
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </td>

                    {/* Chg% */}
                    <td style={{ ...tdBase, overflow: 'hidden' }}>
                      <PctCell val={isExtended && s.extended_chg_pct != null
                        ? s.extended_chg_pct
                        : s.change_pct}
                      />
                      {isExtended && s.extended_chg_pct != null && s.prev_close && (
                        <div style={{ fontSize: 9, color: '#94a3b8', fontFamily: 'monospace' }}>
                          מ-${parseFloat(s.prev_close).toFixed(2)}
                        </div>
                      )}
                    </td>

                    {/* 5m */}
                    <td style={tdBase}><PctCell val={s.chg_5m} /></td>
                    {/* 10m */}
                    <td style={tdBase}><PctCell val={s.chg_10m} /></td>
                    {/* 30m */}
                    <td style={tdBase}><PctCell val={s.chg_30m} /></td>

                    {/* Volume */}
                    <td style={{ ...tdBase, color: '#94a3b8', fontFamily: 'monospace' }}>
                      {fmtVol(s.volume)}
                    </td>

                    {/* Market Cap */}
                    <td style={tdBase}><MoneyCell val={s.market_cap} str={s.market_cap_str} /></td>

                    {/* Health — badge + תיאור */}
                    <td style={{ ...tdBase, padding: '4px 6px', overflow: 'hidden' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'flex-end', flexWrap: 'nowrap', overflow: 'hidden' }}>
                        <HealthBadge score={s.health_score} />
                        {s.ai_label && (
                          <span style={{ fontSize: 10, color: '#cbd5e1', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={s.ai_label}>{s.ai_label}</span>
                        )}
                      </div>
                    </td>

                    {/* RSI */}
                    <td style={tdBase}><RsiCell val={s.rsi} /></td>

                    {/* Short% */}
                    <td style={tdBase}><ShortCell val={s.short_float} /></td>

                    {/* EPS Y% */}
                    <td style={tdBase}><PctCell val={s.eps_this_y} /></td>

                    {/* Sales Q/Q */}
                    <td style={tdBase}><PctCell val={s.sales_qq} /></td>

                    {/* Tags */}
                    <td style={{ ...tdBase, overflow: 'hidden' }}>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', justifyContent: 'flex-end', alignItems: 'center', maxWidth: '100%', overflow: 'hidden' }}>
                        {(s.tags || []).slice(0, 3).map(tag => <TagBadge key={tag} tag={tag} />)}
                        {(s.tags || []).length > 3 && (
                          <span style={{ fontSize: 11, color: '#94a3b8', fontWeight: 600 }}>+{(s.tags || []).length - 3}</span>
                        )}
                      </div>
                    </td>

                    {/* Portfolio buy/sell */}
                    <td style={{ ...tdBase, textAlign: 'center', padding: '4px 4px' }}>
                      <BuySellCell
                        ticker={s.ticker}
                        price={parseFloat(s.price) || 0}
                        positions={positions}
                        onBuy={buy}
                        onShort={short}
                        onClose={closePosition}
                      />
                    </td>
                  </tr>,

                  /* ── Rich expand row ── */
                  isOpen && (
                    <ExpandRow key={`expand-${i}-${s.ticker}`} s={s} colSpan={COL_COUNT} />
                  ),
                ];
              })}
            </tbody>
          </table>
        </div>
      )}

      {sorted.length > 0 && (
        <div style={{ padding: '6px 16px', fontSize: 10, color: '#475569', borderTop: '1px solid #1e293b' }}>
          Health: 🟢 80+ quality · 🟡 60+ stable · 🟠 40+ speculative · 🔴 0-39 risky
        </div>
      )}

      {/* ── Demo Portfolio ── */}
      <PortfolioPanel
        positions={positions}
        stockMap={stockMap}
        portfolioPrices={portfolioPricesData || {}}
        onClose={closePosition}
      />
    </div>
  );
}
