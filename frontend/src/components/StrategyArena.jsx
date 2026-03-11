import { useState, useEffect } from 'react';
import axios from 'axios';

const W = '#4ade80';
const L = '#f87171';
const A = '#818cf8';
const GOLD = '#fbbf24';
const SILVER = '#94a3b8';
const BRONZE = '#f97316';

const STRATEGY_META = {
  balanced:        { emoji: '⚖️', color: '#60a5fa', bg: 'rgba(96,165,250,0.08)', border: 'rgba(96,165,250,0.25)' },
  high_conviction: { emoji: '🎯', color: '#a78bfa', bg: 'rgba(167,139,250,0.08)', border: 'rgba(167,139,250,0.25)' },
  squeeze_hunter:  { emoji: '🔥', color: '#fb923c', bg: 'rgba(251,146,60,0.08)',  border: 'rgba(251,146,60,0.25)'  },
  scalper:         { emoji: '⚡', color: '#34d399', bg: 'rgba(52,211,153,0.08)',  border: 'rgba(52,211,153,0.25)'  },
};

const RANK_COLORS = [GOLD, SILVER, BRONZE, L];

function MiniSparkline({ history = [] }) {
  if (history.length < 2) return null;
  const vals = history.map(h => h.equity);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const range = mx - mn || 1;
  const W_px = 80, H_px = 28, pad = 2;
  const pts = vals.map((v, i) =>
    `${pad + (i / (vals.length - 1)) * (W_px - pad * 2)},${pad + (H_px - pad * 2) - ((v - mn) / range) * (H_px - pad * 2)}`
  ).join(' ');
  const isUp = vals[vals.length - 1] >= vals[0];
  return (
    <svg width={W_px} height={H_px} viewBox={`0 0 ${W_px} ${H_px}`}>
      <polyline points={pts} fill="none" stroke={isUp ? W : L} strokeWidth={1.5} strokeLinejoin="round" />
      <circle
        cx={pad + (W_px - pad * 2)}
        cy={pad + (H_px - pad * 2) - ((vals[vals.length - 1] - mn) / range) * (H_px - pad * 2)}
        r={2.5} fill={isUp ? W : L}
      />
    </svg>
  );
}

function StrategyCard({ strategy, rank, isLeader }) {
  const meta = STRATEGY_META[strategy.name] || { emoji: '📊', color: A, bg: 'rgba(129,140,248,0.08)', border: 'rgba(129,140,248,0.25)' };
  const pnlPct = strategy.pnl_pct ?? 0;
  const posCount = Object.keys(strategy.positions || {}).length;
  const rankColor = RANK_COLORS[rank] || SILVER;

  return (
    <div style={{
      background: isLeader
        ? 'linear-gradient(135deg, rgba(251,191,36,0.07) 0%, rgba(30,27,75,0.95) 100%)'
        : `linear-gradient(135deg, ${meta.bg} 0%, rgba(13,17,23,0.95) 100%)`,
      border: `1px solid ${isLeader ? 'rgba(251,191,36,0.4)' : meta.border}`,
      borderRadius: 12,
      padding: '14px 16px',
      position: 'relative',
      transition: 'all 0.3s ease',
    }}>
      {/* Rank badge */}
      <div style={{
        position: 'absolute', top: 10, right: 12,
        fontSize: 11, fontWeight: 900, color: rankColor,
        background: `${rankColor}15`,
        border: `1px solid ${rankColor}40`,
        borderRadius: 6, padding: '2px 8px',
      }}>
        #{rank + 1}
        {isLeader && <span style={{ marginLeft: 4 }}>👑</span>}
      </div>

      {/* Strategy name + emoji */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
        <span style={{ fontSize: 22 }}>{meta.emoji}</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 800, color: meta.color }}>{strategy.label}</div>
          <div style={{ fontSize: 9, color: '#475569', marginTop: 1 }}>
            Stop: {strategy.config?.stop_loss_pct}% | Target: {strategy.config?.target_pct}%
          </div>
        </div>
      </div>

      {/* Key metrics row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 10 }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            fontSize: 18, fontFamily: 'monospace', fontWeight: 900,
            color: pnlPct >= 0 ? W : L,
          }}>
            {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
          </div>
          <div style={{ fontSize: 8, color: '#475569' }}>תשואה</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 16, fontFamily: 'monospace', fontWeight: 800, color: '#f8fafc' }}>
            ${(strategy.equity ?? 1000).toFixed(0)}
          </div>
          <div style={{ fontSize: 8, color: '#475569' }}>הון</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{
            fontSize: 16, fontFamily: 'monospace', fontWeight: 800,
            color: strategy.win_rate >= 50 ? W : strategy.total_trades > 0 ? L : '#94a3b8',
          }}>
            {strategy.total_trades > 0 ? `${strategy.win_rate?.toFixed(0)}%` : '—'}
          </div>
          <div style={{ fontSize: 8, color: '#475569' }}>הצלחה</div>
        </div>
      </div>

      {/* Sparkline + trade count */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <MiniSparkline history={strategy.equity_history || []} />
        <div style={{ textAlign: 'right' }}>
          <span style={{ fontSize: 11, color: '#64748b' }}>
            {strategy.total_trades} עסקאות · {posCount} פתוחות
          </span>
        </div>
      </div>

      {/* Open positions */}
      {posCount > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {Object.entries(strategy.positions || {}).map(([ticker, pos]) => {
            const ppnl = pos.unrealized_pnl_pct ?? 0;
            return (
              <div key={ticker} style={{
                fontSize: 10, fontWeight: 700, padding: '3px 8px', borderRadius: 5,
                background: ppnl >= 0 ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)',
                border: `1px solid ${ppnl >= 0 ? '#166534' : '#7f1d1d'}`,
                color: ppnl >= 0 ? W : L,
                fontFamily: 'monospace',
              }}>
                {ticker} {ppnl >= 0 ? '+' : ''}{ppnl.toFixed(1)}%
              </div>
            );
          })}
        </div>
      )}

      {/* P&L $ */}
      {(strategy.total_pnl ?? 0) !== 0 && (
        <div style={{
          marginTop: 8, fontSize: 10, fontFamily: 'monospace',
          color: (strategy.total_pnl ?? 0) >= 0 ? W : L,
        }}>
          {(strategy.total_pnl ?? 0) >= 0 ? '+' : ''}${(strategy.total_pnl ?? 0).toFixed(1)} רווח/הפסד
        </div>
      )}
    </div>
  );
}

export default function StrategyArena() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [thinking, setThinking] = useState(false);
  const [declaring, setDeclaring] = useState(false);
  const [lastMsg, setLastMsg] = useState(null);
  const [countdown, setCountdown] = useState('');

  const fetchStatus = async () => {
    try {
      const r = await axios.get('/api/smart-portfolio/arena/status');
      setData(r.data);
    } catch {
      /* silent */
    } finally {
      setLoading(false);
    }
  };

  // Countdown to 16:05 ET
  useEffect(() => {
    const tick = () => {
      const now = new Date();
      // ET offset (approximate — ignores DST edge)
      const etOffset = -4; // EDT; use -5 for EST
      const utcH = now.getUTCHours() + etOffset;
      const etH = ((utcH % 24) + 24) % 24;
      const etM = now.getUTCMinutes();
      const closeH = 16, closeM = 5;
      const diffM = (closeH * 60 + closeM) - (etH * 60 + etM);
      if (diffM <= 0) {
        setCountdown('השוק נסגר');
      } else if (diffM > 480) {
        setCountdown('השוק עוד לא פתוח');
      } else {
        const h = Math.floor(diffM / 60);
        const m = diffM % 60;
        setCountdown(h > 0 ? `${h}ש' ${m}ד' לסגירה` : `${m} דקות לסגירה`);
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

  const triggerThink = async () => {
    setThinking(true);
    setLastMsg(null);
    try {
      const r = await axios.post('/api/smart-portfolio/arena/think');
      setLastMsg({ ok: true, text: `מחשב... ${r.data?.results?.length || 0} אסטרטגיות עודכנו` });
      fetchStatus();
    } catch (e) {
      setLastMsg({ ok: false, text: e.message });
    }
    setThinking(false);
  };

  const declareWinner = async () => {
    if (!confirm('להכריז על המנצח ולהחיל את האסטרטגיה הטובה ביותר?')) return;
    setDeclaring(true);
    setLastMsg(null);
    try {
      const r = await axios.post('/api/smart-portfolio/arena/declare-winner');
      const w = r.data?.winner;
      setLastMsg({ ok: true, text: `🏆 המנצח: ${w?.label || w?.name || '?'} עם ${w?.pnl_pct?.toFixed(2)}%!` });
      fetchStatus();
    } catch (e) {
      setLastMsg({ ok: false, text: e.message });
    }
    setDeclaring(false);
  };

  if (loading) {
    return (
      <div style={{ padding: 60, textAlign: 'center', color: '#475569' }}>
        טוען ארנה...
      </div>
    );
  }

  if (!data || data.error) {
    return (
      <div style={{ padding: 40, textAlign: 'center' }}>
        <div style={{ color: L, fontSize: 13, marginBottom: 12 }}>
          {data?.error || 'שגיאה בטעינת ארנה'}
        </div>
        <button onClick={fetchStatus}
          style={{ padding: '8px 18px', borderRadius: 8, background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.3)', color: '#60a5fa', cursor: 'pointer', fontSize: 12 }}>
          נסה שוב
        </button>
      </div>
    );
  }

  // Sort strategies by equity descending for ranking
  const strategies = Object.entries(data.strategies || {}).map(([name, s]) => ({
    ...s,
    name,
  }));
  const sorted = [...strategies].sort((a, b) => (b.pnl_pct ?? 0) - (a.pnl_pct ?? 0));
  const leaderName = sorted[0]?.name;

  const totalPnl = strategies.reduce((sum, s) => sum + (s.total_pnl ?? 0), 0);
  const totalEquity = strategies.reduce((sum, s) => sum + (s.equity ?? 1000), 0);
  const totalReturn = ((totalEquity - 4000) / 4000 * 100);

  return (
    <div style={{ padding: '16px', maxWidth: 900, margin: '0 auto' }}>

      {/* ─── Header ─── */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        marginBottom: 16, flexWrap: 'wrap', gap: 10,
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 26 }}>🏆</span>
            <div>
              <h2 style={{ fontSize: 20, fontWeight: 900, color: '#f8fafc', margin: 0 }}>
                Strategy Arena
              </h2>
              <div style={{ fontSize: 11, color: '#475569' }}>
                4 אסטרטגיות מתחרות · המנצח לוקח הכל בסגירה
              </div>
            </div>
          </div>
        </div>

        {/* Countdown + controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          {countdown && (
            <div style={{
              fontSize: 11, fontWeight: 700, padding: '5px 10px', borderRadius: 6,
              background: 'rgba(251,191,36,0.1)', border: '1px solid rgba(251,191,36,0.3)',
              color: GOLD,
            }}>
              ⏰ {countdown}
            </div>
          )}
          <button onClick={triggerThink} disabled={thinking}
            style={{
              fontSize: 11, padding: '6px 14px', borderRadius: 8, border: 'none', cursor: 'pointer', fontWeight: 700,
              background: thinking ? '#1e1b4b' : 'linear-gradient(135deg, #4338ca, #6366f1)',
              color: '#fff', opacity: thinking ? 0.6 : 1,
            }}>
            {thinking ? '⏳ חושב...' : '🧠 עדכן עכשיו'}
          </button>
          <button onClick={declareWinner} disabled={declaring}
            style={{
              fontSize: 11, padding: '6px 14px', borderRadius: 8, cursor: 'pointer', fontWeight: 700,
              background: declaring ? 'transparent' : 'rgba(251,191,36,0.12)',
              border: `1px solid ${declaring ? '#334155' : 'rgba(251,191,36,0.4)'}`,
              color: declaring ? '#64748b' : GOLD,
              opacity: declaring ? 0.6 : 1,
            }}>
            {declaring ? '⏳...' : '🏆 הכרז מנצח'}
          </button>
        </div>
      </div>

      {/* ─── Winner announcement (if set) ─── */}
      {data.winner && (
        <div style={{
          marginBottom: 16, padding: '14px 18px', borderRadius: 12,
          background: 'linear-gradient(135deg, rgba(251,191,36,0.12), rgba(30,27,75,0.9))',
          border: '1px solid rgba(251,191,36,0.5)',
          display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <span style={{ fontSize: 32 }}>🏆</span>
          <div>
            <div style={{ fontSize: 14, fontWeight: 900, color: GOLD }}>
              {data.winner.label} — מנצח היום!
            </div>
            <div style={{ fontSize: 11, color: '#94a3b8' }}>
              תשואה: {data.winner.pnl_pct >= 0 ? '+' : ''}{data.winner.pnl_pct?.toFixed(2)}% ·
              {data.winner.total_trades} עסקאות ·
              הוחל על התיק הראשי ב-{data.declared_at ? new Date(data.declared_at).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' }) : '?'}
            </div>
          </div>
        </div>
      )}

      {/* ─── Last message ─── */}
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

      {/* ─── Combined stats bar ─── */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 16,
        padding: '12px 14px', borderRadius: 10,
        background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)',
      }}>
        {[
          { label: 'סה"כ הון', value: `$${totalEquity.toFixed(0)}`, color: '#f8fafc', icon: '💰' },
          { label: 'תשואה כוללת', value: `${totalReturn >= 0 ? '+' : ''}${totalReturn.toFixed(2)}%`, color: totalReturn >= 0 ? W : L, icon: totalReturn >= 0 ? '📈' : '📉' },
          { label: 'מנהיג נוכחי', value: sorted[0]?.label?.split('—')[0]?.trim() || '—', color: GOLD, icon: '👑' },
        ].map((s, i) => (
          <div key={i} style={{ textAlign: 'center' }}>
            <div style={{ fontSize: 9, color: '#475569', marginBottom: 2 }}>{s.icon} {s.label}</div>
            <div style={{ fontSize: 15, fontFamily: 'monospace', fontWeight: 900, color: s.color }}>{s.value}</div>
          </div>
        ))}
      </div>

      {/* ─── Strategy cards ─── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12 }}>
        {sorted.map((strategy, rank) => (
          <StrategyCard
            key={strategy.name}
            strategy={strategy}
            rank={rank}
            isLeader={strategy.name === leaderName && rank === 0}
          />
        ))}
      </div>

      {/* ─── Performance bar comparison ─── */}
      {strategies.length > 0 && (
        <div style={{
          marginTop: 16, padding: '12px 16px', borderRadius: 10,
          background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)',
        }}>
          <div style={{ fontSize: 10, fontWeight: 700, color: '#64748b', marginBottom: 10 }}>
            השוואת ביצועים
          </div>
          {sorted.map((s, i) => {
            const meta = STRATEGY_META[s.name] || { color: A };
            const pct = s.pnl_pct ?? 0;
            const maxPct = Math.max(...strategies.map(x => Math.abs(x.pnl_pct ?? 0)), 1);
            const barW = Math.abs(pct) / maxPct * 100;
            return (
              <div key={s.name} style={{ marginBottom: 6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 10, marginBottom: 3 }}>
                  <span style={{ color: meta.color, fontWeight: 700 }}>
                    {RANK_COLORS[i] && <span style={{ color: RANK_COLORS[i] }}>#{i + 1} </span>}
                    {s.label?.split('—')[0]?.trim()}
                  </span>
                  <span style={{ fontFamily: 'monospace', fontWeight: 800, color: pct >= 0 ? W : L }}>
                    {pct >= 0 ? '+' : ''}{pct.toFixed(2)}%
                  </span>
                </div>
                <div style={{ height: 6, background: '#1e293b', borderRadius: 3, overflow: 'hidden' }}>
                  <div style={{
                    height: '100%',
                    width: `${barW}%`,
                    background: pct >= 0 ? meta.color : L,
                    borderRadius: 3,
                    transition: 'width 0.5s ease',
                  }} />
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* ─── Footer info ─── */}
      <div style={{ marginTop: 12, fontSize: 9, color: '#334155', textAlign: 'center' }}>
        עדכון אוטומטי כל 15 שניות · הכרזת מנצח אוטומטית ב-16:05 ET · הנבחר מוחל על התיק הראשי
      </div>
    </div>
  );
}
