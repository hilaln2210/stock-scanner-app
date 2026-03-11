import React, { useState, useMemo, useCallback } from 'react';
import axios from 'axios';

const api = axios.create({ baseURL: '/api', timeout: 180000 });

const MARKETS = [
  { value: 'ndx100', label: 'NASDAQ 100' },
  { value: 'sp500',  label: 'S&P 500' },
  { value: 'djia',   label: 'Dow Jones (DJIA)' },
];

const YEARS_OPTS = [3, 5, 7, 10, 12, 15];
const MIN_WIN_OPTS = [50, 60, 65, 70, 75, 80, 85, 90];

// Color helpers
const pctColor = (v) => {
  if (v === null || v === undefined) return '#94a3b8';
  return v > 0 ? '#4ade80' : v < 0 ? '#f87171' : '#94a3b8';
};
const winColor = (r) =>
  r >= 90 ? '#4ade80' : r >= 80 ? '#a3e635' : r >= 70 ? '#fbbf24' : r >= 60 ? '#fb923c' : '#f87171';
const sharpeColor = (s) =>
  s >= 3 ? '#4ade80' : s >= 1.5 ? '#a3e635' : s >= 0.5 ? '#fbbf24' : '#94a3b8';

function fmt(v, decimals = 2, suffix = '') {
  if (v === null || v === undefined || isNaN(v)) return '—';
  const n = Number(v).toFixed(decimals);
  return (v > 0 ? '+' : '') + n + suffix;
}

// Table header with sort
function Th({ label, col, sortCol, sortDir, onSort, style = {} }) {
  const active = sortCol === col;
  return (
    <th
      onClick={() => onSort(col)}
      style={{
        padding: '8px 6px', cursor: 'pointer', whiteSpace: 'nowrap',
        color: active ? '#e2e8f0' : '#94a3b8',
        fontWeight: active ? 700 : 400, fontSize: 11,
        borderBottom: '1px solid #1e293b', userSelect: 'none',
        background: '#0f172a',
        ...style,
      }}
    >
      {label}
      {active ? (sortDir === 'desc' ? ' ▼' : ' ▲') : ' ⇅'}
    </th>
  );
}

export default function SeasonalityScanner() {
  // ── State ──────────────────────────────────────────────────────────────────
  const today = new Date().toISOString().slice(0, 10);
  const [market,     setMarket]     = useState('ndx100');
  const [startDate,  setStartDate]  = useState(today);
  const [years,      setYears]      = useState(10);
  const [daysMin,    setDaysMin]    = useState(5);
  const [daysMax,    setDaysMax]    = useState(30);
  const [minWin,     setMinWin]     = useState(75);
  const [direction,  setDirection]  = useState('long');

  const [patterns,   setPatterns]   = useState([]);
  const [loading,    setLoading]    = useState(false);
  const [error,      setError]      = useState('');
  const [cached,     setCached]     = useState(false);
  const [sortCol,    setSortCol]    = useState('win_ratio');
  const [sortDir,    setSortDir]    = useState('desc');

  // ── Fetch ──────────────────────────────────────────────────────────────────
  const runScan = useCallback(async () => {
    setLoading(true);
    setError('');
    setPatterns([]);
    try {
      const res = await api.get('/seasonality', {
        params: {
          market, start_date: startDate, years, days_min: daysMin,
          days_max: daysMax, min_win_pct: minWin, direction,
        },
      });
      setPatterns(res.data.patterns || []);
      setCached(res.data.cached || false);
    } catch (e) {
      setError(e.response?.data?.detail || e.message || 'שגיאה');
    } finally {
      setLoading(false);
    }
  }, [market, startDate, years, daysMin, daysMax, minWin, direction]);

  // ── Sort ───────────────────────────────────────────────────────────────────
  const handleSort = useCallback((col) => {
    setSortDir(prev => sortCol === col ? (prev === 'desc' ? 'asc' : 'desc') : 'desc');
    setSortCol(col);
  }, [sortCol]);

  const sorted = useMemo(() => {
    return [...patterns].sort((a, b) => {
      const av = a[sortCol] ?? 0, bv = b[sortCol] ?? 0;
      return sortDir === 'desc' ? bv - av : av - bv;
    });
  }, [patterns, sortCol, sortDir]);

  // ── Styles ─────────────────────────────────────────────────────────────────
  const S = {
    wrap:  { background: '#0f172a', minHeight: '100vh', color: '#e2e8f0', fontFamily: 'system-ui, sans-serif' },
    panel: { background: '#1e293b', borderRadius: 10, padding: '14px 18px', marginBottom: 14 },
    label: { color: '#94a3b8', fontSize: 12, marginBottom: 4, display: 'block' },
    sel:   { background: '#0f172a', color: '#e2e8f0', border: '1px solid #334155',
             borderRadius: 6, padding: '6px 10px', fontSize: 13, cursor: 'pointer', outline: 'none' },
    inp:   { background: '#0f172a', color: '#e2e8f0', border: '1px solid #334155',
             borderRadius: 6, padding: '6px 10px', fontSize: 13, outline: 'none', width: 120 },
    btn:   { background: '#22c55e', color: '#000', border: 'none', borderRadius: 8,
             padding: '9px 24px', fontWeight: 700, fontSize: 14, cursor: 'pointer', letterSpacing: 0.3 },
    td:    { padding: '7px 6px', fontSize: 12, borderBottom: '1px solid #1e293b' },
  };

  return (
    <div style={S.wrap}>
      {/* Header */}
      <div style={{ ...S.panel, background: 'linear-gradient(135deg,#0e7490,#0f172a)', padding: '20px 24px' }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: '#fff', marginBottom: 4 }}>
          📅 סורק עונתיות — Seasonality Screener
        </div>
        <div style={{ color: '#7dd3fc', fontSize: 13 }}>
          מצא דפוסי מחיר חוזרים על פי תאריך לאורך שנים
        </div>
      </div>

      {/* Filters */}
      <div style={{ ...S.panel, display: 'flex', flexWrap: 'wrap', gap: 18, alignItems: 'flex-end' }}>
        {/* Market */}
        <div>
          <label style={S.label}>Market</label>
          <select value={market} onChange={e => setMarket(e.target.value)} style={S.sel}>
            {MARKETS.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
          </select>
        </div>

        {/* Start Date */}
        <div>
          <label style={S.label}>Start date</label>
          <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)}
            style={S.inp} />
        </div>

        {/* Examination period */}
        <div>
          <label style={S.label}>Examination period</label>
          <select value={years} onChange={e => setYears(Number(e.target.value))} style={S.sel}>
            {YEARS_OPTS.map(y => <option key={y} value={y}>{y} years</option>)}
          </select>
        </div>

        {/* Time period */}
        <div>
          <label style={S.label}>Time period (days)</label>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input type="number" value={daysMin} min={1} max={89}
              onChange={e => setDaysMin(Number(e.target.value))}
              style={{ ...S.inp, width: 56 }} />
            <span style={{ color: '#64748b' }}>–</span>
            <input type="number" value={daysMax} min={5} max={90}
              onChange={e => setDaysMax(Number(e.target.value))}
              style={{ ...S.inp, width: 56 }} />
          </div>
        </div>

        {/* Min Win % */}
        <div>
          <label style={S.label}>Filter Win %</label>
          <select value={minWin} onChange={e => setMinWin(Number(e.target.value))} style={S.sel}>
            {MIN_WIN_OPTS.map(w => <option key={w} value={w}>{w}%</option>)}
          </select>
        </div>

        {/* Direction */}
        <div>
          <label style={S.label}>Direction</label>
          <div style={{ display: 'flex', gap: 12, marginTop: 2 }}>
            {['long', 'short'].map(d => (
              <label key={d} style={{ display: 'flex', alignItems: 'center', gap: 5, cursor: 'pointer', fontSize: 13 }}>
                <input type="radio" name="dir" value={d} checked={direction === d}
                  onChange={() => setDirection(d)}
                  style={{ accentColor: d === 'long' ? '#22c55e' : '#f87171' }} />
                <span style={{ color: d === 'long' ? '#4ade80' : '#f87171', fontWeight: 600 }}>
                  {d === 'long' ? '● Long' : '● Short'}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* Scan button */}
        <div style={{ marginLeft: 'auto' }}>
          <button onClick={runScan} disabled={loading} style={{
            ...S.btn,
            opacity: loading ? 0.6 : 1,
            minWidth: 120,
          }}>
            {loading ? '⏳ סורק...' : '🔍 סרוק'}
          </button>
        </div>
      </div>

      {/* Status bar */}
      {(patterns.length > 0 || error) && (
        <div style={{ ...S.panel, padding: '10px 18px', display: 'flex', alignItems: 'center', gap: 12 }}>
          {error ? (
            <span style={{ color: '#f87171' }}>⚠️ {error}</span>
          ) : (
            <>
              <span style={{ fontWeight: 700, color: '#e2e8f0' }}>
                נמצאו {patterns.length} דפוסים
              </span>
              {cached && <span style={{ color: '#64748b', fontSize: 12 }}>(מנתונים שמורים)</span>}
              <span style={{ color: '#64748b', fontSize: 12, marginLeft: 'auto' }}>
                {MARKETS.find(m => m.value === market)?.label} · {startDate} · {years} שנים · {daysMin}–{daysMax} ימים · ≥{minWin}% ניצחונות
              </span>
            </>
          )}
        </div>
      )}

      {/* Loading overlay */}
      {loading && (
        <div style={{ ...S.panel, textAlign: 'center', padding: 40 }}>
          <div style={{ fontSize: 36, marginBottom: 12 }}>⏳</div>
          <div style={{ color: '#94a3b8', fontSize: 14 }}>
            מוריד נתונים היסטוריים ומחשב דפוסים...
          </div>
          <div style={{ color: '#64748b', fontSize: 12, marginTop: 6 }}>
            הסריקה עשויה לקחת 30–60 שניות בפעם הראשונה
          </div>
        </div>
      )}

      {/* Table */}
      {!loading && sorted.length > 0 && (
        <div style={S.panel}>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
              <thead>
                <tr>
                  <Th label="Rank"          col="rank"              sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Symbol"        col="ticker"            sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Annualized Return" col="annualized_return" sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Avg Return"    col="avg_return"        sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Median Return" col="median_return"     sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Pattern Start" col="pattern_start"     sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Pattern End"   col="pattern_end"       sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Cal. Days"     col="cal_days"          sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Max Profit"    col="max_profit"        sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Max Loss"      col="max_loss"          sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="No. of Winners" col="num_winners"      sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="No. of Trades"  col="num_trades"       sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Win Ratio"     col="win_ratio"         sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Std Dev"       col="std_dev"           sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                  <Th label="Sharpe Ratio"  col="sharpe_ratio"      sortCol={sortCol} sortDir={sortDir} onSort={handleSort} />
                </tr>
              </thead>
              <tbody>
                {sorted.map((p, i) => (
                  <tr key={p.ticker} style={{ background: i % 2 === 0 ? '#0f172a' : '#111827' }}>
                    <td style={{ ...S.td, color: '#64748b', textAlign: 'center' }}>{p.rank}</td>
                    <td style={{ ...S.td, fontWeight: 700, color: '#38bdf8', fontFamily: 'monospace' }}>
                      <a
                        href={`https://www.tradingview.com/chart/?symbol=${p.ticker}`}
                        target="_blank" rel="noopener noreferrer"
                        style={{ color: '#38bdf8', textDecoration: 'none' }}
                      >
                        {p.ticker}
                      </a>
                    </td>
                    <td style={{ ...S.td, color: pctColor(p.annualized_return), fontWeight: 700, textAlign: 'right' }}>
                      {fmt(p.annualized_return, 2, '%')}
                    </td>
                    <td style={{ ...S.td, color: pctColor(p.avg_return), textAlign: 'right' }}>
                      {fmt(p.avg_return, 2, '%')}
                    </td>
                    <td style={{ ...S.td, color: pctColor(p.median_return), textAlign: 'right' }}>
                      {fmt(p.median_return, 2, '%')}
                    </td>
                    <td style={{ ...S.td, color: '#cbd5e1', textAlign: 'center' }}>{p.pattern_start}</td>
                    <td style={{ ...S.td, color: '#cbd5e1', textAlign: 'center' }}>{p.pattern_end}</td>
                    <td style={{ ...S.td, color: '#94a3b8', textAlign: 'center' }}>{p.cal_days}</td>
                    <td style={{ ...S.td, color: '#4ade80', textAlign: 'right', fontWeight: 600 }}>
                      {fmt(p.max_profit, 2, '%')}
                    </td>
                    <td style={{ ...S.td, color: '#f87171', textAlign: 'right' }}>
                      {fmt(p.max_loss, 2, '%')}
                    </td>
                    <td style={{ ...S.td, color: '#94a3b8', textAlign: 'center' }}>{p.num_winners}</td>
                    <td style={{ ...S.td, color: '#64748b', textAlign: 'center' }}>{p.num_trades}</td>
                    <td style={{ ...S.td, textAlign: 'center' }}>
                      <span style={{
                        background: winColor(p.win_ratio) + '22',
                        color: winColor(p.win_ratio),
                        borderRadius: 6, padding: '2px 8px', fontWeight: 700,
                      }}>
                        {p.win_ratio}%
                      </span>
                    </td>
                    <td style={{ ...S.td, color: '#94a3b8', textAlign: 'right' }}>
                      {p.std_dev?.toFixed(2)}%
                    </td>
                    <td style={{ ...S.td, color: sharpeColor(p.sharpe_ratio), textAlign: 'right', fontWeight: 600 }}>
                      {p.sharpe_ratio?.toFixed(2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty state */}
      {!loading && patterns.length === 0 && !error && (
        <div style={{ ...S.panel, textAlign: 'center', padding: 48, color: '#475569' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>📅</div>
          <div style={{ fontSize: 15, fontWeight: 600, color: '#64748b' }}>
            לחץ "סרוק" כדי לאתר דפוסי עונתיות
          </div>
          <div style={{ fontSize: 12, marginTop: 6, color: '#334155' }}>
            הסריקה מנתחת ביצועים היסטוריים של כל מניה עבור אותם תאריכים לאורך השנים
          </div>
        </div>
      )}
    </div>
  );
}
