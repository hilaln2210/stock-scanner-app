import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';
import { RefreshCw, TrendingUp, TrendingDown, AlertCircle, Newspaper } from 'lucide-react';

const api = axios.create({ baseURL: '/api' });

// ── helpers ────────────────────────────────────────────────────────────────────

function chgColor(pct) {
  if (pct > 2)   return 'text-emerald-400';
  if (pct > 0)   return 'text-emerald-300';
  if (pct < -2)  return 'text-red-400';
  if (pct < 0)   return 'text-red-300';
  return 'text-slate-400';
}

function chgBg(pct) {
  if (pct > 2)   return 'bg-emerald-950/60 border-emerald-700/40';
  if (pct > 0)   return 'bg-emerald-950/30 border-emerald-800/30';
  if (pct < -2)  return 'bg-red-950/60 border-red-700/40';
  if (pct < 0)   return 'bg-red-950/30 border-red-800/30';
  return 'bg-slate-800/40 border-slate-700/30';
}

function fmtChg(pct) {
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

// ── sub-components ─────────────────────────────────────────────────────────────

function SectorBar({ s, isTop }) {
  const bar = Math.min(100, Math.max(0, (s.change_pct + 5) / 10 * 100));
  const drivers = s.drivers || [];
  return (
    <div className={`px-3 py-2.5 rounded-lg border transition-all
      ${isTop
        ? 'bg-emerald-950/70 border-emerald-600/50 shadow-emerald-900/30 shadow-md'
        : chgBg(s.change_pct)
      }`}>
      <div className="flex items-center gap-3">
        <span className="text-lg w-7 text-center">{s.icon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex justify-between items-center">
            <span className={`text-xs font-medium truncate ${isTop ? 'text-emerald-200' : 'text-slate-300'}`}>
              {s.name}
            </span>
            <span className={`text-sm font-bold ml-2 ${chgColor(s.change_pct)}`}>
              {fmtChg(s.change_pct)}
            </span>
          </div>
          <div className="mt-1 h-1 bg-slate-700/50 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${s.change_pct >= 0 ? 'bg-emerald-500' : 'bg-red-500'}`}
              style={{ width: `${bar}%` }}
            />
          </div>
        </div>
        <span className="text-xs text-slate-500 w-10 text-right">{s.etf}</span>
      </div>
      {drivers.length > 0 && (
        <div className="flex gap-2 mt-1.5 mr-10 flex-wrap">
          {drivers.map(d => (
            <span key={d.ticker} className="text-[10px]">
              <span className="text-slate-400">{d.ticker}</span>
              <span className={`ml-0.5 ${chgColor(d.change_pct)}`}>{fmtChg(d.change_pct)}</span>
            </span>
          ))}
        </div>
      )}
      {(s.news || []).length > 0 && (
        <div className="mt-1.5 mr-10 space-y-0.5">
          {s.news.slice(0, 2).map((n, i) => (
            <div key={i} className="text-[10px] text-slate-500 truncate leading-tight" title={n.title}>
              <span className="text-blue-400/60 mr-1">&#9679;</span>
              {n.title}
              {n.source && <span className="text-slate-600 ml-1">({n.source})</span>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function StockCard({ s }) {
  return (
    <div className="bg-slate-800/50 border border-slate-700/40 rounded-xl p-3 hover:border-slate-600/60 transition-colors">
      <div className="flex justify-between items-start mb-1">
        <div className="min-w-0 flex-1">
          <span className="text-sm font-bold text-white">{s.ticker}</span>
          {s.company && (
            <span className="text-xs text-slate-400 ml-2 truncate max-w-[120px] inline-block align-bottom">
              {s.company}
            </span>
          )}
        </div>
        <span className={`text-sm font-bold ml-2 shrink-0 ${chgColor(s.change_pct)}`}>
          {fmtChg(s.change_pct)}
        </span>
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-400 mt-1">
        <span>${s.price?.toFixed(2)}</span>
        {s.market_cap && <span className="text-slate-500">{s.market_cap}</span>}
        {s.volume > 0 && <span>נפח: {fmtVol(s.volume)}</span>}
        {s.rel_volume > 0.1 && (
          <span className={s.rel_volume >= 2 ? 'text-amber-400' : ''}>
            נפח יחסי: {s.rel_volume?.toFixed(1)}x
          </span>
        )}
      </div>
    </div>
  );
}

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
    <div className="flex items-center gap-3 px-3 py-2.5 border-b border-slate-700/30 last:border-0 hover:bg-slate-800/30 transition-colors">
      <div className="w-20 shrink-0">
        <div className="flex items-center gap-1.5">
          <span className="text-sm font-bold text-emerald-400">{t.ticker}</span>
          {t.change_pct != null && (
            <span className={`text-sm font-bold ${chgColor(t.change_pct)}`}>
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
        <div className="text-xs text-slate-500 truncate">{t.title || ''}</div>
      </div>
      <div className="text-right shrink-0">
        {t.value && (
          <div className="text-xs font-medium text-amber-400">{t.value}</div>
        )}
        {t.date && (
          <div className="text-xs text-slate-500">{t.date}</div>
        )}
      </div>
    </div>
  );
}

// ── main component ─────────────────────────────────────────────────────────────

export default function SectorBriefing() {
  const [forceKey, setForceKey] = useState(0);

  const { data, isLoading, isFetching, error } = useQuery({
    queryKey: ['sectorBriefing', forceKey],
    queryFn: async () => {
      const r = await api.get('/briefing/sector', {
        params: forceKey > 0 ? { force: true } : {},
      });
      return r.data;
    },
    staleTime: 25 * 1000,  // 25 sec
    refetchInterval: 30 * 1000,  // 30 sec
  });

  const sectors        = data?.sectors        || [];
  const topSector      = data?.top_sector     || null;
  const sectorStocks   = data?.sector_stocks  || [];
  const insiderTrades  = data?.insider_trades || [];
  const generatedAt    = data?.generated_at;

  return (
    <div className="max-w-6xl mx-auto px-4 py-6 space-y-6">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">בריפינג סקטורים 🌅</h2>
          {generatedAt && (
            <p className="text-xs text-slate-500 mt-0.5">עודכן: {fmtTime(generatedAt)}</p>
          )}
        </div>
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

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center h-40">
          <div className="text-slate-400 flex items-center gap-2">
            <RefreshCw size={16} className="animate-spin" />
            טוען נתוני סקטורים...
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
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

          {/* Left: Sector leaderboard */}
          <div className="lg:col-span-1">
            <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-700/40">
                <h3 className="text-sm font-semibold text-slate-200">סקטורים היום</h3>
                <p className="text-xs text-slate-500">ביצועי ETF</p>
              </div>
              <div className="p-3 space-y-1.5">
                {sectors.length === 0 ? (
                  <p className="text-xs text-slate-500 text-center py-4">אין נתונים</p>
                ) : (
                  sectors.map((s) => (
                    <SectorBar key={s.etf} s={s} isTop={topSector?.etf === s.etf} />
                  ))
                )}
              </div>
            </div>
          </div>

          {/* Right: Top sector stocks + Insider trades */}
          <div className="lg:col-span-2 space-y-6">

            {/* Top sector stocks */}
            <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-700/40">
                {topSector ? (
                  <div className="flex items-start gap-2">
                    <span className="text-lg mt-0.5">{topSector.icon}</span>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <h3 className="text-sm font-semibold text-emerald-300">
                          {topSector.name} — סקטור מוביל
                        </h3>
                        <span className={`text-sm font-bold ${chgColor(topSector.change_pct)}`}>
                          {fmtChg(topSector.change_pct)}
                        </span>
                      </div>
                      {topSector.drivers?.length > 0 && (
                        <div className="flex items-center gap-2 mt-1 flex-wrap">
                          <span className="text-xs text-slate-500">מובלת ע״י:</span>
                          {topSector.drivers.map(d => (
                            <span key={d.ticker} className="text-xs">
                              <span className="text-slate-300 font-medium">{d.ticker}</span>
                              <span className={`ml-1 ${chgColor(d.change_pct)}`}>
                                {fmtChg(d.change_pct)}
                              </span>
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ) : (
                  <h3 className="text-sm font-semibold text-slate-300">מניות בסקטור המוביל</h3>
                )}
              </div>

              {/* News headlines for top sector */}
              {topSector?.news?.length > 0 && (
                <div className="px-4 py-3 border-b border-slate-700/40 bg-slate-800/30">
                  <div className="flex items-center gap-1.5 mb-2">
                    <Newspaper size={13} className="text-blue-400" />
                    <span className="text-xs font-medium text-blue-300">חדשות הסקטור</span>
                  </div>
                  <div className="space-y-1.5">
                    {topSector.news.map((n, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <span className="text-blue-400/50 mt-0.5 shrink-0">&#9679;</span>
                        <div className="min-w-0">
                          <p className="text-xs text-slate-300 leading-snug">{n.title}</p>
                          <div className="flex gap-2 mt-0.5">
                            {n.ticker && (
                              <span className="text-[10px] text-slate-500 font-medium">{n.ticker}</span>
                            )}
                            {n.source && (
                              <span className="text-[10px] text-slate-600">{n.source}</span>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {sectorStocks.length === 0 ? (
                <div className="p-6 text-center text-slate-500 text-sm">
                  {topSector
                    ? 'אין מניות עם מומנטום בסקטור זה כרגע'
                    : 'טוען...'}
                </div>
              ) : (
                <div className="p-4 grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {sectorStocks.map((s) => (
                    <StockCard key={s.ticker} s={s} />
                  ))}
                </div>
              )}
            </div>

            {/* Insider trades */}
            <div className="bg-slate-900/60 border border-slate-700/50 rounded-2xl overflow-hidden">
              <div className="px-4 py-3 border-b border-slate-700/40">
                <h3 className="text-sm font-semibold text-amber-300">🏷️ קניות מנהלים — Form 4</h3>
                <p className="text-xs text-slate-500">קניות מנהלים ≥ $100K • 2 ימים אחרונים</p>
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

          </div>
        </div>
      )}
    </div>
  );
}
