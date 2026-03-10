import { useState, useMemo, useCallback, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import axios from 'axios';
import { RefreshCw, Search, TrendingUp, TrendingDown, Target, Shield, Zap, Clock, BarChart3, Wallet, Bot, Power, PowerOff, Send, ArrowUp, ArrowDown, ChevronsUpDown, Star, Activity, Info } from 'lucide-react';

const api = axios.create({ baseURL: '/api', timeout: 120000 });

// ── Color helpers ────────────────────────────────────────────────────────────
const winColor = (rate) => rate >= 70 ? '#4ade80' : rate >= 60 ? '#a3e635' : rate >= 55 ? '#fbbf24' : '#f87171';
const changeColor = (v) => v > 0 ? '#4ade80' : v < 0 ? '#f87171' : '#94a3b8';
const strengthLabel = { very_strong: 'חזק מאוד', strong: 'חזק', moderate: 'בינוני', weak: 'חלש' };
const strengthColor = { very_strong: '#4ade80', strong: '#a3e635', moderate: '#fbbf24', weak: '#64748b' };

// ── Get current NY time window ───────────────────────────────────────────────
function getCurrentNYWindow() {
  const ny = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const h = ny.getHours(), m = ny.getMinutes();
  const totalMin = h * 60 + m;
  const windows = [
    [570, '09:30-10:00'], [600, '10:00-10:30'], [630, '10:30-11:00'],
    [660, '11:00-11:30'], [690, '11:30-12:00'], [720, '12:00-12:30'],
    [750, '12:30-13:00'], [780, '13:00-13:30'], [810, '13:30-14:00'],
    [840, '14:00-14:30'], [870, '14:30-15:00'], [900, '15:00-15:30'],
    [930, '15:30-16:00'],
  ];
  for (let i = windows.length - 1; i >= 0; i--) {
    if (totalMin >= windows[i][0]) return windows[i][1];
  }
  return null;
}

// ── Pattern Heatmap Chart (SVG) ──────────────────────────────────────────────
function PatternHeatmap({ windows, height = 580, investment = 700, price = 0 }) {
  if (!windows || windows.length === 0) return null;

  const currentWindow = getCurrentNYWindow();

  const W = 1050;
  const H = height;
  const pad = { top: 65, right: 30, bottom: 85, left: 60 };
  const chartW = W - pad.left - pad.right;
  const chartH = H - pad.top - pad.bottom;
  const barW = Math.min(chartW / windows.length - 4, 58);

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
        <linearGradient id="entryGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#fbbf24" stopOpacity="1" />
          <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.8" />
        </linearGradient>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="blur" />
          <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
        </filter>
        <filter id="glowGold">
          <feGaussianBlur stdDeviation="3" result="blur" />
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

        const barH = Math.abs(w.avg_change / maxRange) * (chartH / 2);
        const barY = w.avg_change >= 0 ? zeroY - barH : zeroY;
        const isWin = w.avg_change >= 0;

        const dotR = 5 + (w.win_rate - 50) / 10;
        const dotColor = winColor(w.win_rate);
        const rangeH = (w.avg_range / maxRange) * (chartH / 2);

        // Dollar P&L for this window
        const pnl = investment * (w.avg_change / 100);
        const pnlWin = investment * ((w.avg_win || 0) / 100);
        const pnlLoss = investment * ((w.avg_loss || 0) / 100);

        // Is this the current live window?
        const isCurrent = w.window === currentWindow;

        // Entry point logic: tradeable = entry point
        const isEntry = w.tradeable;

        return (
          <g key={i}>
            {/* Current window highlight — full-height glow strip */}
            {isCurrent && (
              <>
                <rect x={x - 4} y={pad.top - 2} width={barW + 8} height={chartH + 4} rx="4"
                  fill="rgba(251,191,36,0.06)" stroke="rgba(251,191,36,0.25)" strokeWidth="1" strokeDasharray="3,3" />
                <text x={x + barW / 2} y={pad.top - 22} fill="#fbbf24" fontSize="8" fontWeight="bold"
                  textAnchor="middle">
                  עכשיו
                </text>
                <polygon
                  points={`${x + barW / 2 - 4},${pad.top - 17} ${x + barW / 2 + 4},${pad.top - 17} ${x + barW / 2},${pad.top - 12}`}
                  fill="#fbbf24" opacity="0.7" />
              </>
            )}

            {/* Range whisker */}
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

            {/* Tradeable highlight border */}
            {w.tradeable && (
              <rect x={x - 2} y={barY - 2} width={barW + 4} height={Math.max(barH, 1) + 4} rx="4"
                fill="none" stroke={dotColor} strokeWidth="1.5" opacity="0.5" filter="url(#glow)" />
            )}

            {/* ★ ENTRY POINT — gold diamond + verbal label */}
            {isEntry && (
              <g>
                {/* Diamond marker */}
                <polygon
                  points={`${x + barW / 2},${zeroY - rangeH - 22} ${x + barW / 2 + 8},${zeroY - rangeH - 13} ${x + barW / 2},${zeroY - rangeH - 4} ${x + barW / 2 - 8},${zeroY - rangeH - 13}`}
                  fill="url(#entryGrad)" filter="url(#glowGold)" />
                <text x={x + barW / 2} y={zeroY - rangeH - 13} fill="#0f172a" fontSize="7" fontWeight="900"
                  textAnchor="middle" dominantBaseline="middle">$</text>

                {/* Verbal: "כאן נכנסים" */}
                <text x={x + barW / 2} y={zeroY - rangeH - 27} fill="#fbbf24" fontSize="8" fontWeight="bold"
                  textAnchor="middle">כאן נכנסים</text>
              </g>
            )}

            {/* ★ Dollar P&L verbal callout below bar */}
            {isEntry && (
              <g>
                <text x={x + barW / 2} y={zeroY + rangeH + 14}
                  fill={pnl >= 0 ? '#4ade80' : '#f87171'} fontSize="9" fontWeight="900"
                  textAnchor="middle" fontFamily="monospace">
                  {pnl >= 0 ? '+' : ''}{pnl < 10 && pnl > -10 ? pnl.toFixed(2) : pnl.toFixed(1)}$
                </text>
                {/* Verbal: "היית מרוויח/מפסיד" */}
                <text x={x + barW / 2} y={zeroY + rangeH + 26}
                  fill={pnl >= 0 ? 'rgba(74,222,128,0.7)' : 'rgba(248,113,113,0.7)'} fontSize="7"
                  textAnchor="middle">
                  {pnl >= 0 ? `רווח מ-$${investment}` : `הפסד מ-$${investment}`}
                </text>
              </g>
            )}

            {/* ★ Current window + tradeable = "להיכנס עכשיו!" */}
            {isCurrent && isEntry && (
              <g>
                <rect x={x + barW / 2 - 35} y={zeroY + rangeH + 34} width="70" height="30" rx="6"
                  fill="rgba(251,191,36,0.15)" stroke="#fbbf24" strokeWidth="1.5" />
                <text x={x + barW / 2} y={zeroY + rangeH + 47} fill="#fbbf24" fontSize="9" fontWeight="900"
                  textAnchor="middle">
                  להיכנס עכשיו!
                </text>
                <text x={x + barW / 2} y={zeroY + rangeH + 58} fill="rgba(251,191,36,0.8)" fontSize="7"
                  textAnchor="middle">
                  WR {w.win_rate}% | +${pnlWin.toFixed(0)} / ${pnlLoss.toFixed(0)}
                </text>
              </g>
            )}

            {/* ★ Current window + NOT tradeable = "לא להיכנס" */}
            {isCurrent && !isEntry && (
              <g>
                <rect x={x + barW / 2 - 30} y={zeroY + rangeH + 34} width="60" height="22" rx="5"
                  fill="rgba(248,113,113,0.1)" stroke="rgba(248,113,113,0.35)" strokeWidth="1" />
                <text x={x + barW / 2} y={zeroY + rangeH + 48} fill="#f87171" fontSize="8" fontWeight="bold"
                  textAnchor="middle">
                  לא להיכנס
                </text>
              </g>
            )}

            {/* Non-tradeable label — short reason */}
            {!isEntry && !isCurrent && w.sample_days >= 5 && (
              <text x={x + barW / 2} y={zeroY + rangeH + 14}
                fill="rgba(100,116,139,0.5)" fontSize="6.5"
                textAnchor="middle">
                {w.win_rate < 55 ? 'חלש' : w.win_rate < 60 ? 'לא מספיק' : 'תנודה קטנה'}
              </text>
            )}

            {/* Win rate dot on top */}
            <circle cx={x + barW / 2} cy={pad.top - 5} r={Math.max(dotR, 3)}
              fill={dotColor} opacity="0.9" />
            <text x={x + barW / 2} y={pad.top - 4} fill="#0f172a" fontSize="7" fontWeight="bold"
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
            <text x={x + barW / 2} y={H - pad.bottom + 15} fill={isCurrent ? '#fbbf24' : '#94a3b8'}
              fontSize={isCurrent ? '10' : '9'} fontWeight={isCurrent ? 'bold' : 'normal'}
              textAnchor="middle" transform={`rotate(-35, ${x + barW / 2}, ${H - pad.bottom + 15})`}>
              {w.window.split('-')[0]}
            </text>
          </g>
        );
      })}

      {/* Legend */}
      <g transform={`translate(${pad.left + 5}, ${H - 12})`}>
        <circle cx="0" cy="0" r="4" fill="#4ade80" opacity="0.9" />
        <text x="8" y="3" fill="#94a3b8" fontSize="8">Win Rate</text>
        <polygon points="68,-5 74,0 68,5 62,0" fill="#fbbf24" />
        <text x="78" y="3" fill="#94a3b8" fontSize="8">= נקודת כניסה</text>
        <rect x="155" y="-5" width="10" height="10" rx="2" fill="none" stroke="rgba(251,191,36,0.5)" strokeWidth="1" strokeDasharray="2,2" />
        <text x="170" y="3" fill="#94a3b8" fontSize="8">= עכשיו</text>
        <text x="210" y="3" fill="#64748b" fontSize="8">| ${investment} השקעה</text>
      </g>
    </svg>
  );
}

// ── ET → IL time helper (ET is always 7h behind Israel) ─────────────────────
const etToIL = (t) => {
  const [h, m] = t.split(':').map(Number);
  return `${String((h + 7) % 24).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
};
const fmtWindow = (w) => {
  const [s, e] = w.split('-');
  return `${s}–${e} NY  /  ${etToIL(s)}–${etToIL(e)} IL`;
};
const fmtTime = (t) => t ? `${t} NY / ${etToIL(t)} IL` : t;

// ── Static sector map for common tickers ────────────────────────────────────
const SECTOR_MAP = {
  // Tech
  NVDA:'טכנולוגיה (מוליכים)', AMD:'טכנולוגיה (מוליכים)', INTC:'טכנולוגיה (מוליכים)',
  AAPL:'טכנולוגיה (צרכן)', MSFT:'תוכנה/ענן', GOOGL:'פרסום/ענן', META:'רשתות חברתיות',
  AMZN:'ריטייל/ענן', TSLA:'רכב חשמלי', NFLX:'בידור דיגיטלי',
  CRM:'תוכנה ארגונית', ADBE:'תוכנה ארגונית', NOW:'תוכנה ארגונית',
  PLTR:'ניתוח נתונים/ממשל', SNOW:'ענן/נתונים', DDOG:'ניטור ענן',
  // Finance
  JPM:'בנקאות', GS:'השקעות', MS:'השקעות', BAC:'בנקאות', C:'בנקאות',
  V:'תשלומים דיגיטליים', MA:'תשלומים דיגיטליים', PYPL:'פינטק', SQ:'פינטק',
  // Biotech/Pharma
  MRNA:'ביוטק (mRNA)', BNTX:'ביוטק (mRNA)', REGN:'ביוטק', BIIB:'ביוטק',
  PFE:'פארמה', JNJ:'פארמה/בריאות', ABBV:'פארמה',
  // Energy
  XOM:'אנרגיה (נפט)', CVX:'אנרגיה (נפט)', OXY:'אנרגיה (נפט)',
  // ETFs/Indices
  SPY:'ETF S&P500', QQQ:'ETF נאסד"ק', IWM:'ETF Small Cap', ARKK:'ETF צמיחה',
  // Other
  DIS:'בידור/מדיה', BABA:'טכנולוגיה סינית', NIO:'רכב חשמלי סיני',
  GME:'ריטייל (ממים)', AMC:'בידור (ממים)',
};

// ── Textual stock insight generator ─────────────────────────────────────────
function generateStockInsight(s, botPick, isTop, ibOpen) {
  const lines = [];

  // Cap + sector
  const capLabel = s.market_cap >= 200e9 ? 'Mega Cap'
    : s.market_cap >= 10e9 ? 'Large Cap'
    : s.market_cap >= 2e9 ? 'Mid Cap' : 'Small Cap';
  const sector = SECTOR_MAP[s.ticker];
  lines.push(`📌 ${capLabel}${sector ? ` — ${sector}` : ''}`);

  // Volatility
  const atrText = s.atr_pct >= 7 ? `תנודתיות גבוהה מאוד (ATR ${s.atr_pct}%) — מתאים לסוחרים מנוסים`
    : s.atr_pct >= 5 ? `תנודתיות גבוהה (ATR ${s.atr_pct}%) — פוטנציאל רווח גדול אך גם סיכון`
    : s.atr_pct >= 3 ? `תנודתיות טובה (ATR ${s.atr_pct}%) — אידיאלי לאינטרה-דיי`
    : `תנודתיות בינונית (ATR ${s.atr_pct}%)`;
  lines.push(`📊 ${atrText}`);

  // Liquidity + spread
  const volM = (s.avg_volume / 1e6).toFixed(0);
  const volText = s.avg_volume >= 50e6 ? `נפח ${volM}M — נזילות מצוינת, קל להיכנס ולצאת`
    : s.avg_volume >= 20e6 ? `נפח ${volM}M — נזילות טובה`
    : `נפח ${volM}M — נזילות סבירה`;
  const spreadText = s.spread_pct <= 0.05 ? 'עלות כניסה/יציאה זולה מאוד'
    : s.spread_pct <= 0.1 ? 'עלות כניסה/יציאה זולה'
    : s.spread_pct <= 0.2 ? 'עלות כניסה/יציאה בינונית'
    : 'עלות כניסה/יציאה גבוהה — שים לב';
  lines.push(`💧 ${volText} | ${spreadText} (Bid/Ask ${s.spread_pct}%)`);

  // Today's movement
  if (s.change_pct != null && Math.abs(s.change_pct) > 0.5) {
    const dir = s.change_pct > 0 ? '▲ עולה' : '▼ יורדת';
    const strength = Math.abs(s.change_pct) > 5 ? 'תנועה חזקה מאוד'
      : Math.abs(s.change_pct) > 3 ? 'תנועה חזקה'
      : Math.abs(s.change_pct) > 1.5 ? 'תנועה בולטת'
      : 'תנועה קלה';
    lines.push(`📅 היום: ${dir} ${Math.abs(s.change_pct)}% — ${strength}`);
  }

  // Bot pick details
  if (botPick) {
    const [ws, we] = botPick.window.split('-');
    const ilWindow = `${etToIL(ws)}–${etToIL(we)}`;
    const nyWindow = `${ws}–${we}`;
    const dirText = botPick.direction === 'Long' ? '📈 Long (עלייה)' : '📉 Short (ירידה)';
    const strengthText = botPick.score > 75 ? 'חוזק גבוה' : botPick.score > 55 ? 'חוזק בינוני' : 'חוזק חלש';
    lines.push(`🤖 בוט: ${dirText} | חלון ${ilWindow} IL (${nyWindow} NY) | Win Rate ${botPick.win_rate}% | ${strengthText}`);
  } else if (isTop) {
    lines.push(`⭐ ציון מאגר גבוה — ATR%+נפח+Bid/Ask בטופ 5 | מומלץ לנתח לפני פתיחת שוק`);
  }

  // IB open
  if (ibOpen) {
    lines.push(`🔴 פוזיציה פתוחה ב-Interactive Brokers`);
  }

  return lines;
}

// ── Auto Bot Panel ───────────────────────────────────────────────────────────
function AutoBotPanel({ investment }) {
  const qc = useQueryClient();

  const [scanning, setScanning] = useState(false);

  const { data: bot, isLoading } = useQuery({
    queryKey: ['autoBotStatus'],
    queryFn: async () => (await api.get('/pattern/autotrader/status')).data,
    // poll every 3s while scanning, 15s otherwise
    refetchInterval: (data) => data?.status_msg?.includes('סורק') ? 3000 : 15000,
    staleTime: 2000,
  });

  // clear scanning flag when picks arrive
  useState(() => {
    if (bot?.today_picks?.length > 0) setScanning(false);
  }, [bot?.today_picks?.length]);

  const toggle = useCallback(async () => {
    if (!bot) return;
    if (bot.enabled) {
      await api.post('/pattern/autotrader/disable');
    } else {
      setScanning(true);
      await api.post('/pattern/autotrader/enable', { amount: investment, top_n: 5 });
    }
    qc.invalidateQueries({ queryKey: ['autoBotStatus'] });
  }, [bot, investment, qc]);

  const scan = useCallback(async () => {
    setScanning(true);
    await api.post('/pattern/autotrader/scan', { amount: investment, top_n: 5 });
    qc.invalidateQueries({ queryKey: ['autoBotStatus'] });
  }, [investment, qc]);

  if (isLoading || !bot) return (
    <div className="text-center py-8 text-slate-500 text-sm">טוען...</div>
  );

  const enabled = bot.enabled;

  return (
    <div className="space-y-4">

      {/* ── Header card ── */}
      <div className="rounded-xl p-4" style={{
        background: enabled
          ? 'linear-gradient(135deg, rgba(74,222,128,0.08), rgba(16,185,129,0.05))'
          : 'linear-gradient(135deg, rgba(100,116,139,0.08), rgba(71,85,105,0.05))',
        border: `1px solid ${enabled ? 'rgba(74,222,128,0.25)' : 'rgba(100,116,139,0.2)'}`,
      }}>
        <div className="flex items-center gap-3 flex-wrap">
          <Bot size={22} color={enabled ? '#4ade80' : '#64748b'} />
          <div>
            <div className="text-base font-black text-white">Pattern Auto-Trader</div>
            <div className="text-xs mt-0.5" style={{ color: enabled ? '#4ade80' : '#64748b' }}>
              {bot.status_msg}
            </div>
          </div>

          {/* P&L */}
          {enabled && (
            <div className="mr-4 text-center">
              <div className="text-xs text-slate-500">P&L היום</div>
              <div className="text-xl font-black font-mono" style={{
                color: bot.daily_pnl >= 0 ? '#4ade80' : '#f87171'
              }}>
                {bot.daily_pnl >= 0 ? '+' : ''}${bot.daily_pnl}
              </div>
            </div>
          )}

          <div className="mr-auto flex gap-2">
            <button onClick={scan} disabled={scanning}
              className="px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1"
              style={{ background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.3)', color: '#c4b5fd',
                opacity: scanning ? 0.6 : 1 }}>
              <RefreshCw size={12} className={scanning ? 'animate-spin' : ''} />
              {scanning ? 'סורק...' : 'סרוק עכשיו'}
            </button>
            <button onClick={toggle}
              className="px-4 py-1.5 rounded-lg text-xs font-black flex items-center gap-1.5 transition-all"
              style={{
                background: enabled
                  ? 'linear-gradient(135deg, #ef4444, #dc2626)'
                  : 'linear-gradient(135deg, #22c55e, #16a34a)',
                color: '#fff',
                boxShadow: enabled ? '0 0 12px rgba(239,68,68,0.3)' : '0 0 12px rgba(34,197,94,0.3)',
              }}>
              {enabled ? <><PowerOff size={13} /> כבה</> : <><Power size={13} /> הפעל</>}
            </button>
          </div>
        </div>

        {/* Info box */}
        <div className="mt-3 p-2 rounded-lg text-xs text-slate-500" style={{ background: 'rgba(0,0,0,0.2)' }}>
          <span className="text-slate-400">📋 איך עובד: </span>
          <span>
            <b className="text-slate-300">חלון 10:00–10:30 NY (17:00–17:30 IL)</b> = נכנסים בדיוק ב-10:00 NY / 17:00 IL, יוצאים ב-10:30 NY / 17:30 IL.
            {' '}הבוט שולח התראת טלגרם <b className="text-slate-300">5 דקות לפני</b> כל כניסה, ונכנס אוטומטית ל-IB.
          </span>
        </div>
      </div>

      {/* ── Today's picks ── */}
      {bot.today_picks && bot.today_picks.length > 0 && (
        <div className="rounded-xl overflow-hidden" style={{
          background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)',
        }}>
          <div className="p-3 flex items-center gap-2 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
            <Target size={14} color="#a78bfa" />
            <span className="text-sm font-bold text-white">מניות נבחרות להיום</span>
            <span className="text-xs text-slate-500">{bot.last_scan_date}</span>
            <div className="mr-auto flex items-center gap-1 text-xs text-slate-500">
              <Send size={11} color="#4ade80" /> טלגרם + IB אוטומטי
            </div>
          </div>
          <div className="divide-y" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
            {bot.today_picks.map((p, i) => (
              <div key={i} className="px-4 py-3 flex items-center gap-3 flex-wrap">
                <span className="text-base font-black text-white w-16">{p.ticker}</span>
                <div className="flex flex-col">
                  <div className="flex items-center gap-1.5">
                    <Clock size={11} className="text-slate-500" />
                    <span className="text-xs font-bold text-white font-mono">{fmtWindow(p.window)}</span>
                  </div>
                  <span className="text-[10px] text-slate-500">כניסה: {p.window.split('-')[0]} NY / {etToIL(p.window.split('-')[0])} IL</span>
                </div>
                <span className="text-xs font-black px-2 py-0.5 rounded" style={{
                  background: p.direction === 'LONG' ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)',
                  color: p.direction === 'LONG' ? '#4ade80' : '#f87171',
                }}>{p.direction}</span>
                <span className="text-xs font-bold" style={{ color: winColor(p.win_rate) }}>WR {p.win_rate}%</span>
                <span className="text-xs font-mono font-bold" style={{ color: changeColor(p.avg_change) }}>
                  {p.avg_change > 0 ? '+' : ''}{p.avg_change}%
                </span>
                <span className="text-xs text-slate-500">ציון {p.score}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* ── Active IB trades ── */}
      {bot.active_trades && bot.active_trades.length > 0 && (
        <div className="rounded-xl p-4 space-y-2" style={{
          background: 'rgba(74,222,128,0.05)', border: '1px solid rgba(74,222,128,0.2)',
        }}>
          <div className="flex items-center gap-2 mb-2">
            <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
            <span className="text-sm font-bold text-white">פוזיציות פתוחות ב-IB</span>
          </div>
          {bot.active_trades.map((t, i) => (
            <div key={i} className="flex items-center gap-3 text-xs flex-wrap">
              <span className="font-black text-white">{t.ticker}</span>
              <span className="px-1.5 py-0.5 rounded font-bold" style={{
                background: t.direction === 'LONG' ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)',
                color: t.direction === 'LONG' ? '#4ade80' : '#f87171',
              }}>{t.direction}</span>
              <span className="text-slate-400">{t.shares} @ ${t.entry_price}</span>
              <span className="text-slate-500 font-mono text-[10px]">{fmtWindow(t.window)}</span>
              <span className="text-slate-500 font-mono text-[10px]">{fmtTime(t.opened_at)}</span>
              <span className="text-[10px] px-1 rounded" style={{
                background: t.ib_filled ? 'rgba(74,222,128,0.1)' : 'rgba(251,191,36,0.1)',
                color: t.ib_filled ? '#4ade80' : '#fbbf24',
              }}>
                {t.ib_filled ? '✓ IB' : '⚡ ידני'}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ── Trade history ── */}
      {bot.trade_history && bot.trade_history.length > 0 && (
        <div className="rounded-xl overflow-hidden" style={{
          background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)',
        }}>
          <div className="p-3 border-b text-sm font-bold text-white" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
            היסטוריית עסקאות אוטומטיות
          </div>
          <div className="divide-y" style={{ borderColor: 'rgba(255,255,255,0.04)' }}>
            {bot.trade_history.map((t, i) => (
              <div key={i} className="px-4 py-2 flex items-center gap-3 text-xs flex-wrap">
                <span className="font-black text-white w-14">{t.ticker}</span>
                <span className="text-slate-500 font-mono text-[10px]">{fmtWindow(t.window)}</span>
                <span className="text-slate-400 font-mono text-[10px]">{fmtTime(t.opened_at)} → {fmtTime(t.closed_at)}</span>
                <span className="font-mono font-black" style={{ color: t.pnl >= 0 ? '#4ade80' : '#f87171' }}>
                  {t.pnl >= 0 ? '+' : ''}${t.pnl}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Empty state / scanning state */}
      {(!bot.today_picks || bot.today_picks.length === 0) && (
        <div className="text-center py-10">
          {scanning || bot.status_msg?.includes('סורק') ? (
            <>
              <RefreshCw size={32} className="animate-spin mx-auto mb-3" style={{ color: '#a78bfa' }} />
              <div className="text-sm text-slate-300 mb-1">סורק מניות...</div>
              <div className="text-xs text-slate-500">מוריד ומנתח דפוסים ל-15 מניות — עד דקה</div>
            </>
          ) : (
            <>
              <Bot size={36} className="mx-auto mb-3 text-slate-700" />
              <div className="text-sm text-slate-500 mb-1">לא בוצעה סריקה היום עדיין</div>
              <div className="text-xs text-slate-600">לחץ "סרוק עכשיו" כדי לבחור את 5 המניות הכי חזקות להיום</div>
            </>
          )}
        </div>
      )}
    </div>
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

// ── Signal Card with TRADE button ────────────────────────────────────────────
function SignalCard({ signal, onTrade, hasOpenPosition, investment = 700 }) {
  const isLong = signal.direction === 'LONG';
  const dollarPnl = investment * (signal.avg_change / 100);
  const dollarWin = investment * (signal.avg_win / 100);
  const dollarLoss = investment * (signal.avg_loss / 100);
  return (
    <div className="rounded-lg p-4 flex items-center gap-4" style={{
      background: isLong ? 'rgba(74,222,128,0.06)' : 'rgba(248,113,113,0.06)',
      border: `1px solid ${isLong ? 'rgba(74,222,128,0.2)' : 'rgba(248,113,113,0.2)'}`,
    }}>
      <div className="flex flex-col items-center gap-1">
        {isLong ? <TrendingUp size={22} color="#4ade80" /> : <TrendingDown size={22} color="#f87171" />}
        <span className="text-sm font-black" style={{ color: isLong ? '#4ade80' : '#f87171' }}>
          {signal.direction}
        </span>
      </div>
      <div className="flex-1 grid grid-cols-2 sm:grid-cols-5 gap-3 text-sm">
        <div>
          <span className="text-slate-500 text-xs">חלון</span>
          <div className="font-bold text-white flex items-center gap-1">
            <Clock size={12} className="text-slate-500" />
            {signal.window}
          </div>
        </div>
        <div>
          <span className="text-slate-500 text-xs">Win Rate</span>
          <div className="font-black text-lg" style={{ color: winColor(signal.win_rate) }}>
            {signal.win_rate}%
          </div>
        </div>
        <div>
          <span className="text-slate-500 text-xs">R:R</span>
          <div className="font-bold text-lg" style={{ color: signal.risk_reward >= 1.5 ? '#4ade80' : '#fbbf24' }}>
            1:{signal.risk_reward}
          </div>
        </div>
        <div>
          <span className="text-slate-500 text-xs">רווח ממוצע</span>
          <div className="font-bold font-mono" style={{ color: '#4ade80' }}>+${dollarWin.toFixed(1)}</div>
          <div className="font-bold font-mono text-xs" style={{ color: '#f87171' }}>${dollarLoss.toFixed(1)}</div>
        </div>
        <div>
          <span className="text-slate-500 text-xs">EV (${investment})</span>
          <div className="font-black font-mono text-lg" style={{ color: changeColor(dollarPnl) }}>
            {dollarPnl >= 0 ? '+' : ''}${dollarPnl.toFixed(1)}
          </div>
        </div>
      </div>
      <div className="text-xs text-right space-y-1" style={{ minWidth: 110 }}>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">כניסה</span>
          <span className="font-mono text-white font-bold">${signal.entry}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">סטופ</span>
          <span className="font-mono font-bold" style={{ color: '#f87171' }}>${signal.stop}</span>
        </div>
        <div className="flex justify-between gap-2">
          <span className="text-slate-500">יעד</span>
          <span className="font-mono font-bold" style={{ color: '#4ade80' }}>${signal.target}</span>
        </div>
      </div>
      <div className="flex flex-col items-center gap-2">
        <div className="text-center">
          <div className="text-xs text-slate-500">ביטחון</div>
          <div className="text-xl font-black" style={{ color: signal.confidence >= 70 ? '#4ade80' : signal.confidence >= 55 ? '#fbbf24' : '#f87171' }}>
            {signal.confidence}
          </div>
        </div>
        {onTrade && (
          <button onClick={() => onTrade(signal)}
            disabled={hasOpenPosition}
            className="px-4 py-2 rounded-lg text-xs font-black transition-all whitespace-nowrap"
            style={{
              background: hasOpenPosition ? 'rgba(100,116,139,0.2)' :
                isLong ? 'linear-gradient(135deg, #22c55e, #16a34a)' : 'linear-gradient(135deg, #ef4444, #dc2626)',
              color: hasOpenPosition ? '#64748b' : '#fff',
              cursor: hasOpenPosition ? 'not-allowed' : 'pointer',
              boxShadow: hasOpenPosition ? 'none' : `0 0 12px ${isLong ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
            }}>
            {hasOpenPosition ? 'פוזיציה פתוחה' : `סחר ${signal.direction}`}
          </button>
        )}
      </div>
    </div>
  );
}

// ── Portfolio Widget ─────────────────────────────────────────────────────────
function PortfolioWidget({ portfolio, onClose, onReset }) {
  if (!portfolio) return null;
  const pos = portfolio.open_position;
  const pnlColor = portfolio.total_pnl >= 0 ? '#4ade80' : '#f87171';
  const retColor = portfolio.return_pct >= 0 ? '#4ade80' : '#f87171';

  return (
    <div className="rounded-xl p-4 space-y-3" style={{
      background: 'linear-gradient(135deg, rgba(251,191,36,0.06), rgba(139,92,246,0.04))',
      border: '1px solid rgba(251,191,36,0.2)',
    }}>
      <div className="flex items-center gap-3 flex-wrap">
        <Wallet size={18} color="#fbbf24" />
        <span className="text-sm font-black text-white">תיק דמו Pattern Bot</span>

        {/* Balance */}
        <div className="flex items-baseline gap-2 mr-4">
          <span className="text-2xl font-black font-mono text-white">${portfolio.current_value}</span>
          <span className="text-sm font-bold font-mono" style={{ color: retColor }}>
            {portfolio.return_pct >= 0 ? '+' : ''}{portfolio.return_pct}%
          </span>
        </div>

        {/* Stats */}
        <div className="flex gap-4 text-xs">
          <div>
            <span className="text-slate-500">P&L</span>
            <div className="font-bold font-mono" style={{ color: pnlColor }}>
              {portfolio.total_pnl >= 0 ? '+' : ''}${portfolio.total_pnl}
            </div>
          </div>
          <div>
            <span className="text-slate-500">עסקאות</span>
            <div className="font-bold text-white">{portfolio.trade_count}</div>
          </div>
          <div>
            <span className="text-slate-500">Win Rate</span>
            <div className="font-bold" style={{ color: winColor(portfolio.win_rate) }}>
              {portfolio.win_rate}%
            </div>
          </div>
          <div>
            <span className="text-slate-500">W/L</span>
            <div>
              <span style={{ color: '#4ade80' }} className="font-bold">{portfolio.win_count}</span>
              <span className="text-slate-600">/</span>
              <span style={{ color: '#f87171' }} className="font-bold">{portfolio.loss_count}</span>
            </div>
          </div>
        </div>

        <button onClick={onReset} className="mr-auto text-xs px-2 py-1 rounded"
          style={{ background: 'rgba(248,113,113,0.1)', border: '1px solid rgba(248,113,113,0.2)', color: '#f87171' }}>
          איפוס
        </button>
      </div>

      {/* Open position */}
      {pos && (
        <div className="rounded-lg p-3 flex items-center gap-3 flex-wrap" style={{
          background: pos.direction === 'LONG' ? 'rgba(74,222,128,0.08)' : 'rgba(248,113,113,0.08)',
          border: `1px solid ${pos.direction === 'LONG' ? 'rgba(74,222,128,0.25)' : 'rgba(248,113,113,0.25)'}`,
        }}>
          <span className="text-xs font-bold px-2 py-0.5 rounded" style={{
            background: pos.direction === 'LONG' ? 'rgba(74,222,128,0.2)' : 'rgba(248,113,113,0.2)',
            color: pos.direction === 'LONG' ? '#4ade80' : '#f87171',
          }}>
            {pos.direction} פתוח
          </span>
          <span className="font-black text-white">{pos.ticker}</span>
          <span className="text-xs text-slate-400">{pos.shares} מניות @ ${pos.entry_price}</span>
          <span className="text-xs text-slate-400">${pos.amount} השקעה</span>
          <span className="text-xs text-slate-500">חלון: {pos.window}</span>

          <div className="mr-auto flex gap-2">
            <button onClick={() => onClose(pos.target_price, 'target')}
              className="px-3 py-1.5 rounded text-xs font-bold"
              style={{ background: 'rgba(74,222,128,0.15)', border: '1px solid rgba(74,222,128,0.3)', color: '#4ade80' }}>
              סגור ביעד ${pos.target_price}
            </button>
            <button onClick={() => onClose(pos.stop_price, 'stop')}
              className="px-3 py-1.5 rounded text-xs font-bold"
              style={{ background: 'rgba(248,113,113,0.15)', border: '1px solid rgba(248,113,113,0.3)', color: '#f87171' }}>
              סגור בסטופ ${pos.stop_price}
            </button>
            <button onClick={() => onClose(pos.entry_price, 'breakeven')}
              className="px-3 py-1.5 rounded text-xs font-bold"
              style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)', color: '#94a3b8' }}>
              סגור ב-B/E
            </button>
          </div>
        </div>
      )}

      {/* Recent trades */}
      {portfolio.trades && portfolio.trades.length > 0 && (
        <div className="flex gap-1.5 flex-wrap">
          {portfolio.trades.slice(-10).reverse().map((t, i) => (
            <div key={i} className="px-2 py-1 rounded text-xs flex items-center gap-1.5" style={{
              background: t.pnl >= 0 ? 'rgba(74,222,128,0.08)' : 'rgba(248,113,113,0.08)',
              border: `1px solid ${t.pnl >= 0 ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)'}`,
            }}>
              <span className="font-bold text-white">{t.ticker}</span>
              <span className="font-mono font-bold" style={{ color: t.pnl >= 0 ? '#4ade80' : '#f87171' }}>
                {t.pnl >= 0 ? '+' : ''}${t.pnl}
              </span>
              <span className="text-slate-600">{t.reason}</span>
            </div>
          ))}
        </div>
      )}
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
  const [expandedInsights, setExpandedInsights] = useState(new Set());
  const [activeTab, setActiveTab] = useState('analyze'); // pool | analyze | autobot
  const [poolRequested, setPoolRequested] = useState(false);
  const [investment, setInvestment] = useState(700);
  const [poolSort, setPoolSort] = useState({ by: 'atr_pct', dir: 'desc' });
  const qc = useQueryClient();

  // Portfolio
  const { data: portfolio, refetch: refetchPortfolio } = useQuery({
    queryKey: ['patternPortfolio'],
    queryFn: async () => (await api.get('/pattern/portfolio')).data,
    staleTime: 5000,
    refetchInterval: 10000,
  });

  const handleTrade = useCallback(async (signal) => {
    try {
      await api.post('/pattern/portfolio/trade', {
        ticker: signal.ticker,
        direction: signal.direction,
        entry_price: signal.entry,
        stop_price: signal.stop,
        target_price: signal.target,
        window: signal.window,
        win_rate: signal.win_rate,
        amount: investment,
      });
      refetchPortfolio();
    } catch (e) {
      console.error('Trade error', e);
    }
  }, [investment, refetchPortfolio]);

  const handleClose = useCallback(async (exitPrice, reason) => {
    try {
      await api.post('/pattern/portfolio/close', { exit_price: exitPrice, reason });
      refetchPortfolio();
    } catch (e) {
      console.error('Close error', e);
    }
  }, [refetchPortfolio]);

  const handleReset = useCallback(async () => {
    await api.post('/pattern/portfolio/reset', { balance: investment });
    refetchPortfolio();
  }, [investment, refetchPortfolio]);

  // IB positions — for marking open positions in pool
  const { data: ibPositions } = useQuery({
    queryKey: ['ibPositionsForPool'],
    queryFn: async () => { try { return (await api.get('/ib/positions')).data; } catch { return []; } },
    staleTime: 15000,
    refetchInterval: activeTab === 'pool' ? 30000 : false,
    enabled: activeTab === 'pool',
  });

  // Autotrader status — for marking bot picks in pool
  const { data: botStatus } = useQuery({
    queryKey: ['autoBotStatusForPool'],
    queryFn: async () => (await api.get('/pattern/autotrader/status')).data,
    staleTime: 15000,
    refetchInterval: activeTab === 'pool' ? 30000 : false,
    enabled: activeTab === 'pool',
  });

  // Step 1: Pool — only fetch when explicitly requested
  const { data: poolData, isLoading: poolLoading, refetch: refetchPool, dataUpdatedAt } = useQuery({
    queryKey: ['patternPool'],
    queryFn: async () => (await api.get('/pattern/pool')).data,
    staleTime: 60 * 60 * 1000,
    refetchInterval: activeTab === 'pool' ? 30000 : 0,
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

  // Derived: open IB position tickers
  const ibOpenTickers = useMemo(() => {
    if (!ibPositions) return new Set();
    const arr = Array.isArray(ibPositions) ? ibPositions : (ibPositions.positions || []);
    return new Set(arr.map(p => (p.ticker || p.symbol || '').toUpperCase()));
  }, [ibPositions]);

  // Derived: bot picks map { ticker → pick }
  const botPicksMap = useMemo(() => {
    const picks = botStatus?.today_picks || [];
    return Object.fromEntries(picks.map(p => [p.ticker, p]));
  }, [botStatus]);

  // Sorted + annotated pool
  // Compute composite "quality score" for each stock: ATR% (volatility) + volume + low spread
  const topTickers = useMemo(() => {
    if (!poolData?.pool) return new Set();
    const scored = poolData.pool.map(s => ({
      ticker: s.ticker,
      score: (s.atr_pct || 0) * 3
            + Math.log10((s.avg_volume || 1e6) / 1e6 + 1) * 5
            - (s.spread_pct || 0) * 20,
    }));
    scored.sort((a, b) => b.score - a.score);
    return new Set(scored.slice(0, 5).map(x => x.ticker));
  }, [poolData]);

  // Auto-expand bot picks + TOP tickers when pool data loads
  useEffect(() => {
    if (!poolData?.pool) return;
    const autoExpand = new Set();
    poolData.pool.forEach(s => {
      if (topTickers.has(s.ticker) || botPicksMap[s.ticker]) autoExpand.add(s.ticker);
    });
    setExpandedInsights(autoExpand);
  }, [poolData, topTickers, botPicksMap]);

  const sortedPool = useMemo(() => {
    if (!poolData?.pool) return [];
    const arr = [...poolData.pool];
    const { by, dir } = poolSort;
    arr.sort((a, b) => {
      const va = a[by] ?? 0, vb = b[by] ?? 0;
      if (typeof va === 'string') return dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      return dir === 'asc' ? va - vb : vb - va;
    });
    return arr;
  }, [poolData, poolSort]);

  const handlePoolSort = useCallback((col) => {
    setPoolSort(prev => prev.by === col ? { by: col, dir: prev.dir === 'desc' ? 'asc' : 'desc' } : { by: col, dir: 'desc' });
  }, []);

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
          <select value={interval} onChange={e => { setInterval_(e.target.value); if (e.target.value !== '1h' && days > 59) setDays(45); }}
            className="px-2 py-1.5 text-xs rounded-lg" style={{
              background: '#161b22', border: '1px solid rgba(255,255,255,0.08)', color: '#94a3b8'
            }}>
            <option value="5m">5 דק׳ (אינטרה)</option>
            <option value="15m">15 דק׳ (אינטרה)</option>
            <option value="1h">שעתי (1h)</option>
          </select>
          <select value={days} onChange={e => setDays(Number(e.target.value))}
            className="px-2 py-1.5 text-xs rounded-lg" style={{
              background: '#161b22', border: '1px solid rgba(255,255,255,0.08)', color: '#94a3b8'
            }}>
            <option value={30}>30 ימים</option>
            <option value={45}>45 ימים</option>
            <option value={59}>60 ימים</option>
            {interval === '1h' && <option value={90}>90 ימים</option>}
            {interval === '1h' && <option value={120}>120 ימים</option>}
            {interval === '1h' && <option value={180}>180 ימים (6 חודש)</option>}
            {interval === '1h' && <option value={252}>252 ימים (שנה)</option>}
            {interval === '1h' && <option value={500}>500 ימים</option>}
            {interval === '1h' && <option value={729}>729 ימים (מקסימום)</option>}
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
          { key: 'autobot', label: '🤖 Auto Bot', icon: Bot, accent: '#4ade80' },
        ].map(tab => (
          <button key={tab.key} onClick={() => { setActiveTab(tab.key); if (tab.key === 'pool') setPoolRequested(true); }}
            className="relative px-4 py-2.5 text-sm font-semibold transition-all flex items-center gap-1.5"
            style={{ color: activeTab === tab.key ? (tab.accent || '#fff') : '#475569' }}>
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
                style={{ background: tab.accent || '#8b5cf6', boxShadow: `0 0 8px ${tab.accent || '#8b5cf6'}80` }} />
            )}
          </button>
        ))}
      </div>

      {/* ── Pool Tab ── */}
      {activeTab === 'pool' && (
        <div className="space-y-3">

          {/* Header bar */}
          <div className="flex flex-wrap items-center gap-3 justify-between">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-slate-500">
                ATR &gt;$2 | ATR% &gt;3% | מחזור &gt;5M
              </span>
              {poolData?.pool && (
                <span className="text-xs px-2 py-0.5 rounded-full font-bold" style={{
                  background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.2)', color: '#c4b5fd'
                }}>{poolData.pool.length} מניות</span>
              )}
              {ibOpenTickers.size > 0 && (
                <span className="text-xs px-2 py-0.5 rounded-full font-bold flex items-center gap-1" style={{
                  background: 'rgba(251,191,36,0.12)', border: '1px solid rgba(251,191,36,0.3)', color: '#fbbf24'
                }}>
                  <Activity size={10} /> {ibOpenTickers.size} פוזיציות פתוחות
                </span>
              )}
              {Object.keys(botPicksMap).length > 0 && (
                <span className="text-xs px-2 py-0.5 rounded-full font-bold flex items-center gap-1" style={{
                  background: 'rgba(74,222,128,0.1)', border: '1px solid rgba(74,222,128,0.25)', color: '#4ade80'
                }}>
                  <Star size={10} /> {Object.keys(botPicksMap).length} בחירות Bot
                </span>
              )}
              {dataUpdatedAt > 0 && (
                <span className="text-xs text-slate-600">
                  עדכון: {new Date(dataUpdatedAt).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
              )}
            </div>
            <div className="flex items-center gap-2">
              {poolLoading && <RefreshCw size={12} className="animate-spin text-purple-400" />}
              <button onClick={() => refetchPool()} className="text-xs px-3 py-1 rounded-lg flex items-center gap-1"
                style={{ background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.3)', color: '#c4b5fd' }}>
                <RefreshCw size={11} className={poolLoading ? 'animate-spin' : ''} />
                רענן
              </button>
            </div>
          </div>

          {/* Legend */}
          <div className="flex flex-wrap gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-1"><span style={{ color: '#f59e0b' }}>▲</span><span style={{ color: '#fbbf24', fontWeight: 'bold' }}>TOP</span> טופ 5 ע"פ ATR%+נפח+Bid/Ask</span>
            <span className="flex items-center gap-1"><span style={{ color: '#fbbf24' }}>●</span> פוזיציה פתוחה ב-IB</span>
            <span className="flex items-center gap-1"><span style={{ color: '#4ade80' }}>★</span> נבחר ע"י Bot היום</span>
            <span className="flex items-center gap-1 cursor-help" title="Bid/Ask% = הפרש בין מחיר הקנייה למכירה כאחוז מהמחיר. ככל שנמוך יותר — עלות הכניסה/יציאה זולה יותר. מעל 0.1% = פחות אטרקטיבי.">
              <Info size={11} /> Bid/Ask% = עלות כניסה/יציאה
            </span>
          </div>

          {poolLoading && !poolData && (
            <div className="text-center py-12">
              <RefreshCw size={24} className="animate-spin mx-auto mb-3" style={{ color: '#8b5cf6' }} />
              <div className="text-sm text-slate-400">סורק מניות... (עד דקה)</div>
            </div>
          )}

          {sortedPool.length > 0 && (() => {
            const SortTh = ({ col, label, className = '' }) => {
              const active = poolSort.by === col;
              return (
                <th className={`py-2 px-2 cursor-pointer select-none whitespace-nowrap ${className}`}
                  onClick={() => handlePoolSort(col)}>
                  <span className="flex items-center gap-0.5 justify-end">
                    {label}
                    {active
                      ? (poolSort.dir === 'desc' ? <ArrowDown size={10} style={{ color: '#8b5cf6' }} /> : <ArrowUp size={10} style={{ color: '#8b5cf6' }} />)
                      : <ChevronsUpDown size={10} className="opacity-30" />}
                  </span>
                </th>
              );
            };

            return (
              <div className="overflow-x-auto rounded-xl" style={{ border: '1px solid rgba(255,255,255,0.05)' }}>
                <table className="w-full text-xs">
                  <thead>
                    <tr className="text-slate-500 border-b" style={{
                      borderColor: 'rgba(255,255,255,0.06)',
                      background: 'rgba(15,20,30,0.6)',
                    }}>
                      <th className="text-right py-2.5 px-3 font-semibold">טיקר</th>
                      <SortTh col="price" label="מחיר" className="text-right font-semibold" />
                      <SortTh col="change_pct" label="שינוי%" className="text-right font-semibold" />
                      <SortTh col="market_cap" label="שווי שוק" className="text-right font-semibold" />
                      <SortTh col="atr" label="ATR $" className="text-right font-semibold" />
                      <SortTh col="atr_pct" label="ATR %" className="text-right font-semibold" />
                      <SortTh col="avg_volume" label="מחזור" className="text-right font-semibold" />
                      <th className="text-right py-2.5 px-2 font-semibold cursor-help whitespace-nowrap"
                        title="Bid/Ask% = הפרש בין מחיר הקנייה למכירה. ככל שנמוך יותר, עלות הכניסה/יציאה זולה יותר.">
                        Bid/Ask%
                      </th>
                      <th className="text-right py-2.5 px-2 font-semibold">Bot</th>
                      <th className="text-center py-2.5 px-2 font-semibold">פעולה</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedPool.map((s) => {
                      const hasIB = ibOpenTickers.has(s.ticker);
                      const botPick = botPicksMap[s.ticker];
                      const isTop = topTickers.has(s.ticker);
                      // Priority: IB > Bot > Top > default
                      const rowBg = hasIB
                        ? 'rgba(251,191,36,0.07)'
                        : botPick
                        ? 'rgba(74,222,128,0.07)'
                        : isTop
                        ? 'rgba(245,158,11,0.04)'
                        : 'transparent';
                      const borderColor = hasIB
                        ? 'rgba(251,191,36,0.3)'
                        : botPick
                        ? 'rgba(74,222,128,0.3)'
                        : isTop
                        ? 'rgba(245,158,11,0.15)'
                        : 'rgba(255,255,255,0.03)';

                      return (
                        <React.Fragment key={s.ticker}>
                        <tr className="border-b transition-colors hover:bg-slate-800/40"
                          style={{ borderColor, background: rowBg,
                            boxShadow: botPick ? 'inset 3px 0 0 #4ade80' : hasIB ? 'inset 3px 0 0 #fbbf24' : 'none' }}>

                          {/* Ticker + badges + insight toggle */}
                          <td className="py-2.5 px-3 cursor-pointer"
                            onClick={() => setExpandedInsights(prev => {
                              const n = new Set(prev);
                              n.has(s.ticker) ? n.delete(s.ticker) : n.add(s.ticker);
                              return n;
                            })}>
                            <div className="flex items-center gap-1.5 flex-wrap">
                              <span className="font-black text-white">{s.ticker}</span>
                              {isTop && (
                                <span className="text-xs px-1.5 rounded font-bold" title="טופ 5 — ATR% גבוה + נפח + Bid/Ask נמוך"
                                  style={{ background: 'rgba(245,158,11,0.2)', color: '#f59e0b', border: '1px solid rgba(245,158,11,0.3)', fontSize: 9 }}>▲TOP</span>
                              )}
                              {hasIB && (
                                <span className="text-xs px-1 rounded font-bold" title="פוזיציה פתוחה ב-IB"
                                  style={{ background: 'rgba(251,191,36,0.2)', color: '#fbbf24' }}>IB</span>
                              )}
                              <span style={{ color: expandedInsights.has(s.ticker) ? '#a78bfa' : '#334155', fontSize: 10 }}>
                                {expandedInsights.has(s.ticker) ? '▲' : '▼'}
                              </span>
                            </div>
                          </td>

                          {/* Price */}
                          <td className="py-2.5 px-2 font-mono font-bold text-white">${s.price}</td>

                          {/* Change % */}
                          <td className="py-2.5 px-2 font-mono font-bold" style={{ color: s.change_pct > 0 ? '#4ade80' : s.change_pct < 0 ? '#f87171' : '#94a3b8' }}>
                            {s.change_pct != null ? `${s.change_pct > 0 ? '+' : ''}${s.change_pct}%` : '—'}
                          </td>

                          {/* Market cap */}
                          <td className="py-2.5 px-2 font-mono text-slate-300">
                            {s.market_cap >= 1e12 ? `$${(s.market_cap / 1e12).toFixed(1)}T`
                              : s.market_cap >= 1e9 ? `$${(s.market_cap / 1e9).toFixed(1)}B`
                              : s.market_cap > 0 ? `$${(s.market_cap / 1e6).toFixed(0)}M`
                              : '—'}
                          </td>

                          {/* ATR $ */}
                          <td className="py-2.5 px-2 font-mono font-bold" style={{ color: s.atr >= 3 ? '#4ade80' : '#fbbf24' }}>
                            ${s.atr}
                          </td>

                          {/* ATR % */}
                          <td className="py-2.5 px-2">
                            <span className="px-1.5 py-0.5 rounded font-bold" style={{
                              background: s.atr_pct >= 5 ? 'rgba(74,222,128,0.15)' : s.atr_pct >= 3.5 ? 'rgba(163,230,53,0.12)' : 'rgba(251,191,36,0.12)',
                              color: s.atr_pct >= 5 ? '#4ade80' : s.atr_pct >= 3.5 ? '#a3e635' : '#fbbf24',
                            }}>
                              {s.atr_pct}%
                            </span>
                          </td>

                          {/* Volume */}
                          <td className="py-2.5 px-2 font-mono text-slate-300">
                            {s.avg_volume >= 1e9 ? `${(s.avg_volume / 1e9).toFixed(1)}B`
                              : s.avg_volume >= 1e6 ? `${(s.avg_volume / 1e6).toFixed(1)}M`
                              : `${(s.avg_volume / 1e3).toFixed(0)}K`}
                          </td>

                          {/* Bid/Ask% */}
                          <td className="py-2.5 px-2 font-mono"
                            title={`Bid/Ask%: ${s.spread_pct}% — ${s.spread_pct <= 0.05 ? 'מצוין' : s.spread_pct <= 0.1 ? 'טוב' : s.spread_pct <= 0.2 ? 'בינוני' : 'גבוה'} (עלות כניסה/יציאה)`}
                            style={{ color: s.spread_pct <= 0.05 ? '#4ade80' : s.spread_pct <= 0.1 ? '#a3e635' : s.spread_pct <= 0.2 ? '#fbbf24' : '#f87171' }}>
                            {s.spread_pct > 0 ? `${s.spread_pct}%` : '—'}
                          </td>

                          {/* Bot pick */}
                          <td className="py-2.5 px-2">
                            {botPick ? (
                              <div className="flex flex-col gap-0.5">
                                <span className="flex items-center gap-0.5 font-bold text-xs" style={{ color: '#4ade80' }}>
                                  <Star size={10} fill="#4ade80" /> {botPick.direction}
                                </span>
                                <span className="text-slate-500" style={{ fontSize: 10 }}>
                                  WR {botPick.win_rate}% | {botPick.window}
                                </span>
                              </div>
                            ) : (
                              <span className="text-slate-700">—</span>
                            )}
                          </td>

                          {/* Action */}
                          <td className="py-2.5 px-2 text-center">
                            <button onClick={() => handlePoolTickerClick(s.ticker)}
                              className="px-2.5 py-1 rounded text-xs font-bold transition-all hover:scale-105"
                              style={{
                                background: botPick ? 'rgba(74,222,128,0.15)' : 'rgba(139,92,246,0.15)',
                                border: `1px solid ${botPick ? 'rgba(74,222,128,0.3)' : 'rgba(139,92,246,0.3)'}`,
                                color: botPick ? '#4ade80' : '#c4b5fd',
                              }}>
                              נתח →
                            </button>
                          </td>
                        </tr>
                        {/* ── Insight row ── */}
                        {expandedInsights.has(s.ticker) && (() => {
                          const insightLines = generateStockInsight(s, botPick, isTop, hasIB);
                          return (
                            <tr style={{ background: 'rgba(139,92,246,0.04)', borderBottom: '1px solid rgba(139,92,246,0.1)' }}>
                              <td colSpan={10} className="px-4 py-3">
                                <div className="flex flex-col gap-1.5">
                                  <div className="flex items-center gap-1.5 mb-0.5">
                                    <span style={{ color: '#a78bfa', fontSize: 11, fontWeight: 'bold' }}>💡 ניתוח מילולי — {s.ticker}</span>
                                    <span className="text-slate-600" style={{ fontSize: 10 }}>לחץ על הטיקר לסגירה</span>
                                  </div>
                                  {insightLines.map((line, i) => (
                                    <div key={i} className="text-xs text-slate-300 leading-relaxed">
                                      {line}
                                    </div>
                                  ))}
                                </div>
                              </td>
                            </tr>
                          );
                        })()}
                      </React.Fragment>
                    );
                    })}
                  </tbody>
                </table>
              </div>
            );
          })()}
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

              {/* ── Entry Points Summary Cards ── */}
              {tickerAnalysis.tradeable_windows.length > 0 && (() => {
                const tw = tickerAnalysis.tradeable_windows;
                const totalEV = tw.reduce((s, w) => s + investment * (w.avg_change / 100), 0);
                const bestW = tw[0];
                const bestPnl = investment * (bestW.avg_change / 100);
                const currentW = getCurrentNYWindow();
                const nowTrade = tw.find(w => w.window === currentW);
                return (
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    {/* Best entry */}
                    <div className="rounded-xl p-3" style={{ background: 'rgba(74,222,128,0.06)', border: '1px solid rgba(74,222,128,0.15)' }}>
                      <div className="text-xs text-slate-500 mb-1">נקודת כניסה הכי טובה</div>
                      <div className="text-lg font-black text-white">{bestW.window}</div>
                      <div className="flex items-baseline gap-2">
                        <span className="text-sm font-bold" style={{ color: '#4ade80' }}>WR {bestW.win_rate}%</span>
                        <span className="text-xs font-mono" style={{ color: '#4ade80' }}>+${bestPnl.toFixed(1)}</span>
                      </div>
                    </div>
                    {/* Total daily EV */}
                    <div className="rounded-xl p-3" style={{ background: 'rgba(139,92,246,0.06)', border: '1px solid rgba(139,92,246,0.15)' }}>
                      <div className="text-xs text-slate-500 mb-1">סה״כ EV יומי (${investment})</div>
                      <div className="text-lg font-black font-mono" style={{ color: totalEV >= 0 ? '#4ade80' : '#f87171' }}>
                        {totalEV >= 0 ? '+' : ''}${totalEV.toFixed(1)}
                      </div>
                      <div className="text-xs text-slate-500">{tw.length} כניסות</div>
                    </div>
                    {/* Now — should I enter? */}
                    <div className="rounded-xl p-3 sm:col-span-2" style={{
                      background: nowTrade ? 'rgba(251,191,36,0.08)' : 'rgba(248,113,113,0.05)',
                      border: `1px solid ${nowTrade ? 'rgba(251,191,36,0.25)' : 'rgba(248,113,113,0.15)'}`,
                    }}>
                      <div className="text-xs text-slate-500 mb-1">עכשיו ({currentW || 'מחוץ לשעות'})</div>
                      {nowTrade ? (
                        <div>
                          <div className="flex items-center gap-2">
                            <span className="text-lg font-black" style={{ color: '#fbbf24' }}>כן — להיכנס!</span>
                            <span className="px-2 py-0.5 rounded text-xs font-bold" style={{
                              background: 'rgba(74,222,128,0.15)', color: '#4ade80'
                            }}>WR {nowTrade.win_rate}%</span>
                          </div>
                          <div className="flex gap-3 mt-1 text-xs">
                            <span style={{ color: '#4ade80' }}>Win: <span className="font-mono font-bold">+${(investment * nowTrade.avg_win / 100).toFixed(1)}</span></span>
                            <span style={{ color: '#f87171' }}>Loss: <span className="font-mono font-bold">${(investment * nowTrade.avg_loss / 100).toFixed(1)}</span></span>
                            <span style={{ color: '#c4b5fd' }}>EV: <span className="font-mono font-bold">+${(investment * nowTrade.avg_change / 100).toFixed(1)}</span></span>
                          </div>
                        </div>
                      ) : (
                        <div className="text-lg font-black" style={{ color: '#f87171' }}>
                          {currentW ? 'לא — אין דפוס חזק עכשיו' : 'השוק סגור'}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })()}

              {/* ── Chart ── */}
              <div className="rounded-xl p-4" style={{
                background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)',
              }}>
                <div className="flex items-center gap-2 mb-3">
                  <BarChart3 size={16} color="#a78bfa" />
                  <span className="text-sm font-bold text-white">גרף דפוסים לפי חצי שעה</span>
                  <span className="text-xs text-slate-500">שינוי ממוצע + טווח + Win Rate + נקודות כניסה</span>
                  <div className="mr-auto flex items-center gap-1.5">
                    <span className="text-xs text-slate-500">השקעה $</span>
                    <input type="number" value={investment} onChange={e => setInvestment(Number(e.target.value) || 700)}
                      className="w-20 px-2 py-1 text-xs rounded-lg text-right font-mono"
                      style={{ background: '#161b22', border: '1px solid rgba(255,255,255,0.08)', color: '#fbbf24' }}
                    />
                  </div>
                </div>
                <PatternHeatmap windows={tickerAnalysis.windows} height={720} investment={investment} price={tickerAnalysis.price} />
              </div>

              {/* ── Windows Table ── */}
              <div className="rounded-xl overflow-hidden" style={{
                background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)',
              }}>
                <div className="p-3 flex items-center gap-2 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                  <Clock size={14} color="#a78bfa" />
                  <span className="text-sm font-bold text-white">טבלת חלונות זמן</span>
                  <span className="text-xs text-slate-500 mr-1">🇮🇱 ישראל למעלה · 🇺🇸 NY למטה</span>
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="text-slate-500 border-b" style={{ borderColor: 'rgba(255,255,255,0.06)' }}>
                        <th className="text-right py-2 px-3">
                          <div className="text-slate-300">🇮🇱 ישראל</div>
                          <div className="text-slate-600 font-normal">🇺🇸 NY</div>
                        </th>
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
                        <th className="text-right py-2 px-2">💰 ${investment}</th>
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
                          <td className="py-2 px-3 whitespace-nowrap">
                            {(() => {
                              const [s, e] = w.window.split('-');
                              return (
                                <div>
                                  <div className="font-bold text-white">{etToIL(s)}–{etToIL(e)}</div>
                                  <div className="text-slate-500" style={{ fontSize: 10 }}>
                                    <Clock size={9} className="inline ml-0.5" />{s}–{e}
                                  </div>
                                </div>
                              );
                            })()}
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
                          <td className="py-2 px-2 font-mono font-bold" style={{ color: changeColor(w.avg_change) }}>
                            {(() => { const d = investment * (w.avg_change / 100); return `${d >= 0 ? '+' : ''}$${d.toFixed(1)}`; })()}
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

              {/* ── Portfolio Widget ── */}
              <PortfolioWidget portfolio={portfolio} onClose={handleClose} onReset={handleReset} />

              {/* ── Trade Signals (Step 3) ── */}
              {tickerAnalysis.signals && tickerAnalysis.signals.length > 0 && (
                <div className="rounded-xl p-4 space-y-3" style={{
                  background: '#0d1117', border: '1px solid rgba(74,222,128,0.15)',
                }}>
                  <div className="flex items-center gap-2">
                    <Target size={18} color="#4ade80" />
                    <span className="text-base font-bold text-white">שלב 3: סיגנלים למסחר</span>
                    <span className="text-xs text-slate-500">לחצי "סחר" כדי לפתוח פוזיציה בתיק הדמו</span>
                  </div>
                  {tickerAnalysis.signals.map((sig, i) => (
                    <SignalCard key={i} signal={sig} onTrade={handleTrade}
                      hasOpenPosition={!!portfolio?.open_position} investment={investment} />
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

      {/* ── Auto Bot Tab ── */}
      {activeTab === 'autobot' && <AutoBotPanel investment={investment} />}
    </div>
  );
}
