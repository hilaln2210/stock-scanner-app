import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { TrendingUp, TrendingDown, RefreshCw, ShoppingCart, Trash2, RotateCcw, CheckSquare, Square, X, Settings, Bot, ChevronDown, ChevronUp } from 'lucide-react';
import axios from 'axios';

const api = axios.create({ baseURL: '/api' });

function fmt$(n) {
  return `$${Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function PnlBadge({ dollar, pct }) {
  const up = dollar >= 0;
  return (
    <span className={`inline-flex items-center gap-1 font-bold ${up ? 'text-green-400' : 'text-red-400'}`}>
      {up ? <TrendingUp size={14} /> : <TrendingDown size={14} />}
      {up ? '+' : ''}{fmt$(dollar)} ({up ? '+' : ''}{Number(pct).toFixed(2)}%)
    </span>
  );
}

export default function DemoPortfolio() {
  const queryClient = useQueryClient();
  const [confirmReset, setConfirmReset] = useState(false);
  const [selectedTickers, setSelectedTickers] = useState(new Set());
  const [buyResult, setBuyResult] = useState(null);
  const [confirmSell, setConfirmSell] = useState(null);
  const [showSettings, setShowSettings] = useState(false);
  const [lastFetchedAt, setLastFetchedAt] = useState(null); // local browser time of last successful fetch
  const [showAdvisor, setShowAdvisor] = useState(true);

  // Settings form state (synced from server data)
  const [settingsPortfolioSize, setSettingsPortfolioSize] = useState('');
  const [settingsBudget, setSettingsBudget] = useState('');
  const [depositAmount, setDepositAmount] = useState('');

  const { data, isLoading, isFetching, refetch } = useQuery({
    queryKey: ['demoPortfolio'],
    queryFn: () => api.get('/portfolio/demo').then(r => {
      setLastFetchedAt(new Date());
      return r.data;
    }),
    refetchInterval: 2 * 60 * 1000,
  });

  // Sync settings form when data loads
  useEffect(() => {
    if (data) {
      setSettingsPortfolioSize(String(data.initial_cash ?? 3000));
      setSettingsBudget(String(data.max_per_position ?? 700));
    }
  }, [data?.initial_cash, data?.max_per_position]);

  const { data: briefingData, isLoading: briefingLoading } = useQuery({
    queryKey: ['demoPortfolioBriefing'],
    queryFn: () => api.get('/briefing/daily').then(r => r.data),
    staleTime: 30 * 60 * 1000,
  });

  const { data: advisorData, isLoading: advisorLoading, refetch: refetchAdvisor } = useQuery({
    queryKey: ['portfolioAdvisor'],
    queryFn: () => api.get('/portfolio/demo/analysis').then(r => r.data),
    refetchInterval: 5 * 60 * 1000,
    staleTime: 3 * 60 * 1000,
  });

  const buyMutation = useMutation({
    mutationFn: (tickers) => api.post('/portfolio/demo/buy', { tickers }).then(r => r.data),
    onSuccess: (result) => {
      queryClient.invalidateQueries(['demoPortfolio']);
      queryClient.invalidateQueries(['portfolioAdvisor']);
      setBuyResult(result);
      setSelectedTickers(new Set());
    },
    onError: (err) => {
      setBuyResult({ error: err.response?.data?.detail || err.message || 'שגיאה בביצוע הרכישה' });
    },
  });

  const sellMutation = useMutation({
    mutationFn: (ticker) => api.post(`/portfolio/demo/sell/${ticker}`).then(r => r.data),
    onSuccess: (result) => {
      queryClient.invalidateQueries(['demoPortfolio']);
      queryClient.invalidateQueries(['portfolioAdvisor']);
      setConfirmSell(null);
      setBuyResult({ sold: true, ticker: result.ticker, pnl: result.pnl, proceeds: result.proceeds });
    },
    onError: (err) => {
      setConfirmSell(null);
      setBuyResult({ error: err.response?.data?.detail || err.message || 'שגיאה במכירה' });
    },
  });

  const resetMutation = useMutation({
    mutationFn: () => api.post('/portfolio/demo/reset', {
      initial_cash: parseFloat(settingsPortfolioSize) || 3000,
      budget_per_position: parseFloat(settingsBudget) || 700,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries(['demoPortfolio']);
      setConfirmReset(false);
      setSelectedTickers(new Set());
      setBuyResult(null);
      setConfirmSell(null);
    },
  });

  const setSizeMutation = useMutation({
    mutationFn: (vals) => api.post('/portfolio/demo/set-size', vals).then(r => r.data),
    onSuccess: (result) => {
      queryClient.invalidateQueries(['demoPortfolio']);
      setShowSettings(false);
      setBuyResult({
        settingsSaved: true,
        initial_cash: result.initial_cash,
        max_per_position: result.max_per_position,
        cash_delta: result.cash_delta,
      });
    },
    onError: (err) => {
      setBuyResult({ error: err.response?.data?.detail || 'שגיאה בשמירת הגדרות' });
    },
  });

  const depositMutation = useMutation({
    mutationFn: (amount) => api.post('/portfolio/demo/add-cash', { amount }).then(r => r.data),
    onSuccess: (result) => {
      queryClient.invalidateQueries(['demoPortfolio']);
      setDepositAmount('');
      setBuyResult({ deposited: true, amount: result.added, cash: result.cash });
    },
    onError: (err) => {
      setBuyResult({ error: err.response?.data?.detail || 'שגיאה בהוספת כסף' });
    },
  });

  const handleSaveSettings = () => {
    const size = parseFloat(settingsPortfolioSize);
    const budget = parseFloat(settingsBudget);
    if (!size || size < 100) return;
    if (!budget || budget < 10) return;
    setSizeMutation.mutate({ portfolio_size: size, budget_per_position: budget });
  };

  const handleDeposit = () => {
    const n = parseFloat(depositAmount);
    if (!n || n <= 0) return;
    depositMutation.mutate(n);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-10 h-10 border-4 border-blue-500 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const positions = data?.positions || [];
  const trades = data?.trades || [];
  const heldTickers = new Set(positions.map(p => p.ticker));
  const briefingStocks = (briefingData?.stocks || []).filter(s => !heldTickers.has(s.ticker));
  // Use live server value so preview matches actual buy
  const budgetPerPos = data?.max_per_position ?? 700;

  const toggleTicker = (ticker) => {
    setSelectedTickers(prev => {
      const next = new Set(prev);
      if (next.has(ticker)) next.delete(ticker);
      else next.add(ticker);
      return next;
    });
    setBuyResult(null);
  };

  const handleBuy = () => {
    if (selectedTickers.size === 0) return;
    setBuyResult(null);
    buyMutation.mutate([...selectedTickers]);
  };

  return (
    <div className="space-y-4 max-w-3xl mx-auto">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            💼 <span dir="rtl">תיק דמו</span>
            {isFetching && !isLoading && <RefreshCw size={14} className="text-slate-500 animate-spin" />}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5" dir="rtl">
            הון: {fmt$(data?.initial_cash || 3000)} | תקציב למניה: {fmt$(budgetPerPos)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => { setBuyResult(null); refetch(); refetchAdvisor(); }}
            className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-lg text-xs flex items-center gap-1.5">
            <RefreshCw size={12} /> רענן
          </button>
          <button
            onClick={() => { setShowSettings(s => !s); setBuyResult(null); setConfirmReset(false); }}
            className={`px-3 py-1.5 rounded-lg text-xs flex items-center gap-1.5 transition-all ${
              showSettings ? 'bg-blue-700 text-white' : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
            }`}
          >
            <Settings size={12} /> הגדרות
          </button>
          {confirmReset ? (
            <div className="flex items-center gap-1.5">
              <span className="text-xs text-red-400" dir="rtl">למחוק הכל?</span>
              <button onClick={() => resetMutation.mutate()} disabled={resetMutation.isLoading}
                className="px-3 py-1.5 bg-red-700 hover:bg-red-600 text-white rounded-lg text-xs">כן, אפס</button>
              <button onClick={() => setConfirmReset(false)}
                className="px-3 py-1.5 bg-slate-700 text-slate-300 rounded-lg text-xs">ביטול</button>
            </div>
          ) : (
            <button onClick={() => { setConfirmReset(true); setShowSettings(false); }}
              className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-400 rounded-lg text-xs flex items-center gap-1.5">
              <RotateCcw size={12} /> איפוס
            </button>
          )}
        </div>
      </div>

      {/* Settings panel */}
      {showSettings && (
        <div className="bg-slate-800/80 border border-blue-700/40 rounded-xl p-4 space-y-3">
          <p className="text-sm font-bold text-white" dir="rtl">⚙️ הגדרות תיק</p>

          {/* Size + Budget */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-slate-400 block mb-1" dir="rtl">הון כולל ($)</label>
              <input
                type="number" min="100" step="500"
                value={settingsPortfolioSize}
                onChange={e => setSettingsPortfolioSize(e.target.value)}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 text-white rounded-lg text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="text-xs text-slate-400 block mb-1" dir="rtl">תקציב למניה ($)</label>
              <input
                type="number" min="10" step="100"
                value={settingsBudget}
                onChange={e => setSettingsBudget(e.target.value)}
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 text-white rounded-lg text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>
          <p className="text-[10px] text-slate-500" dir="rtl">
            שינוי ההון מוסיף/מוריד מזומן בהפרש. פוזיציות קיימות לא מושפעות.
          </p>
          <button
            onClick={handleSaveSettings}
            disabled={setSizeMutation.isLoading}
            className="w-full py-2 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white rounded-lg text-sm font-bold"
          >
            {setSizeMutation.isLoading ? 'שומר...' : 'שמור הגדרות'}
          </button>

          {/* Add cash */}
          <div className="border-t border-slate-700 pt-3">
            <p className="text-xs text-slate-400 mb-2" dir="rtl">הפקדת מזומן נוסף</p>
            <div className="flex gap-2">
              <input
                type="number" min="1" placeholder="סכום..."
                value={depositAmount}
                onChange={e => setDepositAmount(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleDeposit()}
                className="flex-1 px-3 py-2 bg-slate-700 border border-slate-600 text-white rounded-lg text-sm focus:border-emerald-500 focus:outline-none"
              />
              <button
                onClick={handleDeposit}
                disabled={depositMutation.isLoading || !depositAmount}
                className="px-4 py-2 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white rounded-lg text-sm font-bold"
              >
                {depositMutation.isLoading ? '...' : 'הפקד'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-3 gap-3">
        <div className="bg-slate-800/70 border border-slate-700 rounded-xl p-4 text-center">
          <p className="text-xs text-slate-500 mb-1" dir="rtl">שווי תיק</p>
          <p className="text-2xl font-bold text-white font-mono">{fmt$(data?.total_value || 0)}</p>
        </div>
        <div className="bg-slate-800/70 border border-slate-700 rounded-xl p-4 text-center">
          <p className="text-xs text-slate-500 mb-1" dir="rtl">רווח/הפסד</p>
          <div className="flex flex-col items-center">
            <PnlBadge dollar={data?.total_pnl_dollar || 0} pct={data?.total_pnl_pct || 0} />
          </div>
        </div>
        <div className="bg-slate-800/70 border border-slate-700 rounded-xl p-4 text-center">
          <p className="text-xs text-slate-500 mb-1" dir="rtl">מזומן</p>
          <p className="text-xl font-bold text-slate-300 font-mono">{fmt$(data?.cash || 0)}</p>
        </div>
      </div>

      {/* Open positions */}
      <div className="bg-slate-800/60 border border-slate-700 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between gap-3 flex-wrap">
          <span className="text-sm font-bold text-white" dir="rtl">
            📊 פוזיציות פתוחות
            {positions.length > 0 && <span className="ml-2 text-xs text-slate-400">({positions.length})</span>}
          </span>
          <div className="flex items-center gap-2">
            {/* Market session badge */}
            {data?.session && (
              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                data.session === 'שוק פתוח'    ? 'bg-green-700/60 text-green-300' :
                data.session === 'פריי-מרקט'  ? 'bg-blue-700/60 text-blue-300' :
                data.session === 'אפטר-מרקט'  ? 'bg-orange-700/60 text-orange-300' :
                'bg-slate-700 text-slate-400'
              }`} dir="rtl">
                {data.session}
              </span>
            )}
            {lastFetchedAt && !isFetching && (
              <span className="text-[10px] text-slate-500">
                עודכן {lastFetchedAt.toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' })}
              </span>
            )}
            {isFetching && <span className="text-xs text-slate-500 animate-pulse">מעדכן...</span>}
          </div>
        </div>

        {positions.length === 0 ? (
          <div className="px-4 py-8 text-center" dir="rtl">
            <p className="text-slate-400 text-sm">אין פוזיציות פתוחות</p>
            <p className="text-slate-600 text-xs mt-1">בחר מניות מרשימת הבריפינג למטה</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-700/50">
            {positions.map(pos => {
              const up = (pos.pnl_dollar || 0) >= 0;
              const isSelling = confirmSell === pos.ticker;
              return (
                <div key={pos.ticker} className={`px-4 py-3 transition-all ${isSelling ? 'bg-red-950/30' : ''}`}>
                  <div className="flex items-start gap-3 flex-wrap">
                    <div className="min-w-[90px]">
                      <span className="text-base font-bold text-white">{pos.ticker}</span>
                      <p className="text-[10px] text-slate-500 truncate max-w-[130px]">{pos.company}</p>
                      <p className="text-[10px] text-slate-600">{pos.buy_date}</p>
                    </div>
                    <div className="flex-1 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs">
                      <div><span className="text-slate-500">קנייה: </span><span className="text-slate-300 font-mono">${pos.buy_price}</span></div>
                      <div>
                        <span className="text-slate-500">עכשיו: </span>
                        <span className={`font-mono font-bold ${up ? 'text-green-400' : 'text-red-400'}`}>${pos.current_price}</span>
                        {pos.price_time && <span className="text-slate-600 text-[9px] ml-1">{pos.price_time}</span>}
                      </div>
                      <div><span className="text-slate-500">מניות: </span><span className="text-slate-300">{pos.shares?.toFixed(4)}</span></div>
                      <div><span className="text-slate-500">שווי: </span><span className="text-slate-300 font-mono">{fmt$(pos.market_value)}</span></div>
                    </div>
                    <div className="text-right shrink-0 min-w-[80px]">
                      <p className={`text-sm font-bold ${up ? 'text-green-400' : 'text-red-400'}`}>
                        {up ? '+' : ''}{fmt$(pos.pnl_dollar)}
                      </p>
                      <p className={`text-xs ${up ? 'text-green-500' : 'text-red-500'}`}>
                        {up ? '+' : ''}{Number(pos.pnl_pct).toFixed(2)}%
                      </p>
                    </div>
                    <div className="shrink-0 flex items-center gap-1.5">
                      {isSelling ? (
                        <>
                          <button onClick={() => sellMutation.mutate(pos.ticker)} disabled={sellMutation.isLoading}
                            className="px-2.5 py-1.5 bg-red-700 hover:bg-red-600 text-white rounded-lg text-xs font-bold">
                            {sellMutation.isLoading ? '...' : 'מכור עכשיו'}
                          </button>
                          <button onClick={() => setConfirmSell(null)}
                            className="p-1.5 bg-slate-700 hover:bg-slate-600 text-slate-400 rounded-lg">
                            <X size={12} />
                          </button>
                        </>
                      ) : (
                        <button onClick={() => setConfirmSell(pos.ticker)}
                          className="px-2.5 py-1.5 bg-red-900/60 hover:bg-red-800 text-red-300 rounded-lg text-xs flex items-center gap-1">
                          <Trash2 size={11} /> מכור
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="mt-1.5 flex items-center gap-2 flex-wrap">
                    {pos.earnings_beat != null && (
                      <span className="px-1.5 py-0.5 rounded bg-emerald-900/50 border border-emerald-600/30 text-emerald-400 text-[10px] font-bold">
                        beat +{Number(pos.earnings_beat).toFixed(0)}%
                      </span>
                    )}
                    {pos.rsi_at_buy != null && (
                      <span className="px-1.5 py-0.5 rounded bg-slate-700 text-slate-400 text-[10px]">
                        RSI קנייה: {Number(pos.rsi_at_buy).toFixed(0)}
                      </span>
                    )}
                    {pos.watch_level && (
                      <span className="px-1.5 py-0.5 rounded bg-blue-900/40 border border-blue-700/30 text-blue-300 text-[10px]" dir="rtl">
                        🎯 {pos.watch_level}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Feedback banner */}
      {buyResult && (
        <div className={`px-4 py-3 rounded-lg text-sm border relative ${
          buyResult.error ? 'bg-red-950/50 border-red-500/30 text-red-400' : 'bg-emerald-950/50 border-emerald-500/30 text-emerald-300'
        }`} dir="rtl">
          <button onClick={() => setBuyResult(null)} className="absolute top-2 left-2 text-slate-500 hover:text-slate-300">
            <X size={13} />
          </button>
          {buyResult.error ? (
            <p>{buyResult.error}</p>
          ) : buyResult.sold ? (
            <p>נמכרה {buyResult.ticker} — תמורה: {fmt$(buyResult.proceeds)}{' '}
              <span className={buyResult.pnl >= 0 ? 'text-green-300' : 'text-red-300'}>
                ({buyResult.pnl >= 0 ? '+' : ''}{fmt$(buyResult.pnl)})
              </span>
            </p>
          ) : buyResult.deposited ? (
            <p>הופקדו {fmt$(buyResult.amount)} — יתרה: {fmt$(buyResult.cash)}</p>
          ) : buyResult.settingsSaved ? (
            <p>
              הגדרות נשמרו — הון: {fmt$(buyResult.initial_cash)} | תקציב: {fmt$(buyResult.max_per_position)}
              {buyResult.cash_delta !== 0 && (
                <span className="text-slate-400 text-xs ml-2">
                  (מזומן {buyResult.cash_delta > 0 ? `+${fmt$(buyResult.cash_delta)}` : fmt$(buyResult.cash_delta)})
                </span>
              )}
            </p>
          ) : (
            <>
              {buyResult.bought?.length > 0 && (
                <p>נקנו: {buyResult.bought.map(b => `${b.ticker} — ${b.shares?.toFixed(3)} מניות @ $${b.price} = ${fmt$(b.cost)}`).join(' | ')}</p>
              )}
              {buyResult.bought?.length === 0 && <p className="text-yellow-400">לא נרכשה אף מניה</p>}
              {buyResult.skipped?.length > 0 && (
                <p className="text-slate-400 mt-1 text-xs">דולגו: {buyResult.skipped.join(' | ')}</p>
              )}
            </>
          )}
        </div>
      )}

      {/* AI Portfolio Advisor */}
      <div className="bg-slate-900/70 border border-amber-700/30 rounded-xl overflow-hidden">
        <button
          className="w-full px-4 py-3 flex items-center justify-between hover:bg-slate-800/40 transition-all"
          onClick={() => setShowAdvisor(s => !s)}
        >
          <span className="flex items-center gap-2 text-sm font-bold text-amber-300">
            <Bot size={15} />
            <span dir="rtl">יועצת AI</span>
            {advisorData?.missed_opportunities?.length > 0 && (
              <span className="px-1.5 py-0.5 bg-red-700/70 text-red-200 rounded-full text-[10px] font-bold">
                {advisorData.missed_opportunities.length} פספוס{advisorData.missed_opportunities.length > 1 ? 'ים' : ''}
              </span>
            )}
          </span>
          <span className="flex items-center gap-2 text-slate-500">
            {advisorData?.generated_at && (
              <span className="text-[10px]">{advisorData.generated_at}</span>
            )}
            {advisorLoading ? <RefreshCw size={12} className="animate-spin" /> :
              showAdvisor ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </span>
        </button>

        {showAdvisor && (
          <div className="border-t border-amber-700/20">
            {/* Overall assessment */}
            {advisorData?.overall && (
              <div className="px-4 py-3 border-b border-slate-700/40">
                <p className="text-sm text-slate-200 leading-relaxed" dir="rtl">{advisorData.overall}</p>
              </div>
            )}
            {advisorLoading && !advisorData && (
              <div className="px-4 py-5 text-center text-slate-500 text-sm" dir="rtl">
                <RefreshCw size={14} className="animate-spin inline mr-2" />
                מנתח תיק ומזהה פספוסים...
              </div>
            )}

            {/* Missed opportunities */}
            {advisorData?.missed_opportunities?.length > 0 && (
              <div className="px-4 py-3 space-y-2 border-b border-slate-700/40">
                <p className="text-[11px] font-bold text-amber-500 uppercase tracking-wide mb-2" dir="rtl">
                  ⚠️ פספוסים מהבריפינג
                </p>
                {advisorData.missed_opportunities.map(m => (
                  <div key={m.ticker}
                    className="bg-amber-950/40 border border-amber-700/30 rounded-lg px-3 py-2.5"
                    dir="rtl"
                  >
                    <p className="text-sm text-amber-200 font-medium">{m.alert}</p>
                    <div className="flex items-center gap-3 mt-1 text-[11px] text-slate-400">
                      <span>מחיר בריפינג: <span className="font-mono text-slate-300">${m.briefing_price}</span></span>
                      <span className="text-slate-600">→</span>
                      <span>כעת: <span className="font-mono text-green-400">${m.current_price}</span></span>
                      {m.earnings_beat != null && (
                        <span className="px-1.5 py-0.5 bg-emerald-900/50 border border-emerald-600/30 text-emerald-400 rounded text-[10px]">
                          beat +{Number(m.earnings_beat).toFixed(0)}%
                        </span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Per-position comments */}
            {advisorData?.position_comments?.length > 0 && (
              <div className="px-4 py-3 space-y-1.5">
                <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wide mb-2" dir="rtl">
                  📋 הערות על פוזיציות
                </p>
                {advisorData.position_comments.map(c => (
                  <div key={c.ticker} className="flex items-start gap-2 text-sm" dir="rtl">
                    <span className="font-bold text-white shrink-0 w-14 text-right">{c.ticker}</span>
                    <span className="text-slate-300 leading-snug">{c.comment}</span>
                  </div>
                ))}
              </div>
            )}

            {advisorData && !advisorData.overall && (
              <div className="px-4 py-4 text-center text-slate-500 text-sm" dir="rtl">
                אין נתוני ניתוח זמינים
              </div>
            )}
          </div>
        )}
      </div>

      {/* Stock Picker from Briefing */}
      <div className="bg-slate-800/60 border border-slate-700 rounded-xl overflow-hidden">
        <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
          <span className="text-sm font-bold text-white" dir="rtl">☀️ בחר מניות לקנייה מהבריפינג</span>
          <span className="text-xs text-slate-500" dir="rtl">עד {fmt$(budgetPerPos)} לכל מניה</span>
        </div>

        {briefingLoading ? (
          <div className="px-4 py-6 text-center text-slate-500 text-sm" dir="rtl">טוען בריפינג...</div>
        ) : briefingData?.loading ? (
          <div className="px-4 py-6 text-center text-slate-500 text-sm" dir="rtl">הבריפינג בהכנה — נסה שוב עוד כמה דקות</div>
        ) : briefingStocks.length === 0 && heldTickers.size > 0 ? (
          <div className="px-4 py-6 text-center text-slate-500 text-sm" dir="rtl">כל מניות הבריפינג כבר מוחזקות בתיק</div>
        ) : briefingStocks.length === 0 ? (
          <div className="px-4 py-6 text-center text-slate-500 text-sm" dir="rtl">לא נמצאו מניות בבריפינג — עבור לטאב הבריפינג לרענון</div>
        ) : (
          <div className="divide-y divide-slate-700/50 max-h-80 overflow-y-auto">
            {briefingStocks.map(stock => {
              const selected = selectedTickers.has(stock.ticker);
              const negEps = stock.reported_eps != null && stock.reported_eps < 0;
              const estShares = stock.price > 0 ? (budgetPerPos / stock.price) : 0;
              return (
                <button
                  key={stock.ticker}
                  onClick={() => toggleTicker(stock.ticker)}
                  className={`w-full px-4 py-2.5 flex flex-col gap-1.5 text-left transition-all ${
                    selected ? 'bg-emerald-900/30 border-l-2 border-emerald-500' : 'hover:bg-slate-700/40'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div className={`shrink-0 ${selected ? 'text-emerald-400' : 'text-slate-600'}`}>
                      {selected ? <CheckSquare size={18} /> : <Square size={18} />}
                    </div>
                    <div className="min-w-[70px]">
                      <span className="text-sm font-bold text-white">{stock.ticker}</span>
                      <p className="text-[10px] text-slate-500 truncate max-w-[110px]">{stock.company}</p>
                    </div>
                    {stock.earnings_surprise_pct != null && (
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${
                        negEps ? 'bg-yellow-900/50 border border-yellow-600/30 text-yellow-400'
                               : 'bg-emerald-900/50 border border-emerald-600/30 text-emerald-400'
                      }`}>
                        {negEps ? '⚠️ ' : ''}+{stock.earnings_surprise_pct?.toFixed(0)}% beat
                      </span>
                    )}
                    {stock.rsi != null && (
                      <span className={`px-1.5 py-0.5 rounded text-[10px] font-bold shrink-0 ${
                        stock.rsi > 70 ? 'bg-red-900/50 text-red-400' :
                        stock.rsi < 40 ? 'bg-blue-900/50 text-blue-400' :
                        'bg-slate-700 text-slate-400'
                      }`}>
                        RSI {stock.rsi?.toFixed(0)}
                      </span>
                    )}
                    {stock.sector && (
                      <span className="text-[10px] text-slate-500 hidden sm:inline truncate shrink-0">{stock.sector}</span>
                    )}
                    <p className="text-[10px] text-slate-500 flex-1 truncate hidden md:block text-right" dir="rtl">
                      {stock.reason}
                    </p>
                  </div>
                  {selected && stock.price > 0 && (
                    <div className="ml-7 flex items-center gap-2 text-[11px] font-mono text-emerald-400">
                      <span>~{estShares.toFixed(3)} מניות</span>
                      <span className="text-slate-600">@</span>
                      <span className="text-slate-300">${stock.price.toFixed(2)}</span>
                      <span className="text-slate-600">=</span>
                      <span className="text-emerald-300 font-bold">
                        ${Math.min(budgetPerPos, data?.cash ?? budgetPerPos).toFixed(2)}
                      </span>
                      {stock.watch_level && (
                        <span className="text-blue-400 text-[10px] ml-2">🎯 {stock.watch_level}</span>
                      )}
                    </div>
                  )}
                </button>
              );
            })}
          </div>
        )}

        {briefingStocks.length > 0 && (
          <div className="border-t border-slate-700">
            {selectedTickers.size > 0 && (
              <div className="px-4 py-2 bg-emerald-950/40 flex items-center justify-between text-xs" dir="rtl">
                <span className="text-slate-400">
                  {selectedTickers.size} מניות × {fmt$(budgetPerPos)} — סה"כ השקעה משוערת:
                </span>
                <span className="text-emerald-300 font-bold font-mono">
                  {fmt$(Math.min(budgetPerPos * selectedTickers.size, data?.cash ?? budgetPerPos * selectedTickers.size))}
                </span>
              </div>
            )}
            <div className="px-4 py-3 flex items-center gap-3">
              <button
                onClick={handleBuy}
                disabled={selectedTickers.size === 0 || buyMutation.isLoading || (data?.cash != null && data.cash < 10)}
                className="flex-1 py-2.5 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white font-bold rounded-lg flex items-center justify-center gap-2 transition-all text-sm"
              >
                <ShoppingCart size={15} />
                {buyMutation.isLoading ? 'קונה... (מביא מחירים)'
                  : selectedTickers.size > 0 ? `אשר קנייה — ${selectedTickers.size} מניות`
                  : 'בחר מניות לקנייה'}
              </button>
              {selectedTickers.size > 0 && (
                <button onClick={() => { setSelectedTickers(new Set()); setBuyResult(null); }}
                  className="px-3 py-2.5 bg-slate-700 hover:bg-slate-600 text-slate-400 rounded-lg text-xs">
                  נקה
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Trade history */}
      {trades.length > 0 && (
        <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-700/50">
            <span className="text-xs font-bold text-slate-400 uppercase tracking-wide" dir="rtl">
              היסטוריית עסקאות ({trades.length})
            </span>
          </div>
          <div className="divide-y divide-slate-700/30 max-h-52 overflow-y-auto">
            {[...trades].reverse().map((t, i) => {
              const isBuy = t.action === 'BUY';
              return (
                <div key={i} className="px-4 py-2 flex items-center gap-3 text-xs flex-wrap">
                  <span className={`px-1.5 py-0.5 rounded font-bold text-[10px] shrink-0 ${
                    isBuy ? 'bg-emerald-900/60 text-emerald-300' : 'bg-red-900/60 text-red-300'
                  }`}>
                    {isBuy ? 'קנייה' : 'מכירה'}
                  </span>
                  <span className="font-bold text-white shrink-0">{t.ticker}</span>
                  <span className="text-slate-400">{Number(t.shares).toFixed(4)} מניות @ ${t.price}</span>
                  <span className="text-slate-500 font-mono">{fmt$(t.value)}</span>
                  {t.pnl != null && (
                    <span className={`font-bold shrink-0 ${t.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {t.pnl >= 0 ? '+' : ''}{fmt$(t.pnl)}
                    </span>
                  )}
                  <span className="text-slate-600 mr-auto">{t.date}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
