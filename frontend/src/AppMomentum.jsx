import { useState, useCallback, useRef, useEffect, useMemo, lazy, Suspense } from 'react';
import { useQuery, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RefreshCw, Zap, Search } from 'lucide-react';
import axios from 'axios';
import FinvizTableScanner from './components/FinvizTableScanner';
const StrategyArena = lazy(() => import('./components/StrategyArena'));
const AlertSystem = lazy(() => import('./components/AlertSystem'));

const FDACatalystTracker = lazy(() => import('./components/FDACatalystTracker'));
const DailyBriefing = lazy(() => import('./components/DailyBriefing'));
const TechnicalSignalsScanner = lazy(() => import('./components/TechnicalSignalsScanner'));
const DailyAnalysisScanner = lazy(() => import('./components/DailyAnalysisScanner'));
const NewsPanel = lazy(() => import('./components/NewsPanel'));
import IBPortfolio from './components/IBPortfolio';
const PatternScanner = lazy(() => import('./components/PatternScanner'));
const SeasonalityScanner = lazy(() => import('./components/SeasonalityScanner'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: true,  // sync when switching desktop ↔ mobile (PWA)
      refetchOnReconnect: true,
      retry: 1,
      staleTime: 60000,
      cacheTime: 15 * 60000,
    },
  },
});

const API_BASE = '/api';
const api = axios.create({ baseURL: API_BASE, timeout: 45000 });

// Derive a short Hebrew reason label from a news headline
function getReasonFromTitle(title) {
  if (!title) return null;
  const t = title.toLowerCase();
  if (/\bearnings?\b|beat.*eps|eps.*beat|\bq[1-4]\b.*result|revenue.*beat|profit.*rise|\bsurpas/.test(t)) return { label: 'רווחים טובים', color: '#4ade80' };
  if (/\bfda\b.*approv|approv.*\bfda\b|\bpdufa\b|\bnda\b.*approv|drug.*approv|clearance.*fda/.test(t)) return { label: 'אישור FDA', color: '#a78bfa' };
  if (/\bupgrad\b|price target.*rais|rais.*price target|outperform|overweight|buy rating|strong buy/.test(t)) return { label: 'שדרוג אנליסט', color: '#60a5fa' };
  if (/\bdowngrad\b|price target.*cut|cut.*price target|underperform|underweight|sell rating/.test(t)) return { label: 'הורדת דירוג', color: '#f87171' };
  if (/\bacquisition\b|\bmerger\b|\bbuyout\b|\bto acquire\b|\bto buy\b.*\b(company|corp|inc)\b|\btakeover\b/.test(t)) return { label: 'רכישה/מיזוג', color: '#fbbf24' };
  if (/\bguidance\b.*rais|raise.*\bguidance\b|\boutlook\b.*raised|forecast.*upgrad/.test(t)) return { label: 'שיפור תחזית', color: '#34d399' };
  if (/\bguidance\b.*low|lower.*\bguidance\b|\boutlook\b.*cut|warns.*miss|guidance.*cut/.test(t)) return { label: 'תחזית נמוכה', color: '#f87171' };
  if (/\bcontract\b|\bdeal\b.*\$|\bpartnership\b|\bagreement\b.*\$|\bawarded\b/.test(t)) return { label: 'עסקה/חוזה', color: '#fbbf24' };
  if (/short sell|short interest|fraud|manipulat|accounting irregularit/.test(t)) return { label: 'ספקולציה שורט', color: '#fb923c' };
  if (/\bbuyback\b|share repurchase|dividend|special dividend/.test(t)) return { label: 'ריבאק/דיבידנד', color: '#4ade80' };
  if (/clinical trial|phase [123]|data read|topline|top.line|positive data/.test(t)) return { label: 'נתוני ניסוי', color: '#a78bfa' };
  if (/layoff|restructur|job cut|workforce reduction/.test(t)) return { label: 'פיטורים', color: '#f87171' };
  if (/ipo|initial public offering|debut/.test(t)) return { label: 'IPO', color: '#60a5fa' };
  return null;
}

// Arena IB Trader status widget for the header
function ArenaIBWidget() {
  const { data } = useQuery({
    queryKey: ['arenaIBStatus'],
    queryFn: () => api.get('/ib/arena-trader/status').then(r => r.data),
    refetchInterval: 30000,
    staleTime: 20000,
  });
  if (!data) return null;
  const pnl = data.total_pnl ?? 0;
  const positions = Object.keys(data.ib_positions || {}).length;
  const strategy = data.active_strategy || '—';
  const connected = data.ib_connected;
  const enabled = data.enabled;
  const isLive = connected && enabled;
  const pnlColor = pnl >= 0 ? '#4ade80' : '#f87171';
  const borderColor = isLive ? 'rgba(74,222,128,0.3)' : 'rgba(248,113,113,0.3)';
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: '6px',
      background: '#0f172a', border: `1px solid ${borderColor}`,
      borderRadius: '8px', padding: '4px 10px', fontSize: '11px', color: '#94a3b8',
      whiteSpace: 'nowrap',
    }}>
      <span style={{
        fontSize: '9px', fontWeight: 700, letterSpacing: '0.05em',
        color: isLive ? '#4ade80' : '#f87171',
        background: isLive ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)',
        padding: '1px 5px', borderRadius: '4px',
      }}>
        {isLive ? 'LIVE' : 'OFFLINE'}
      </span>
      <span style={{ color: '#e2e8f0', fontWeight: 700 }}>{strategy}</span>
      <span style={{ color: '#475569' }}>|</span>
      <span style={{ color: pnlColor, fontWeight: 600 }}>{pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</span>
      <span style={{ color: '#475569' }}>|</span>
      <span>{positions} פוז׳</span>
    </div>
  );
}

// Tab definitions with accent hex colors for the active underline
// Hidden tabs (disabled to save server resources):
// { key: 'briefing',        label: '☀️ בריפינג',            accent: '#f59e0b' },
// { key: 'fda',             label: '💊 FDA',                  accent: '#22c55e' },
// { key: 'news',            label: '📰 חדשות',               accent: '#3b82f6' },
const TABS = [
  { key: 'arena',           label: '🏆 ארנה',                accent: '#fbbf24' },
  { key: 'tech-signals',    label: '📈 סיגנלים',             accent: '#6366f1' },
  { key: 'daily-analysis',  label: '🎯 ניתוח יומי',           accent: '#8b5cf6' },
  { key: 'ib',              label: '🏦 IB חשבון',             accent: '#3b82f6' },
  { key: 'pattern-bot',     label: '🤖 Pattern Bot',           accent: '#a78bfa' },
  { key: 'seasonality',     label: '📅 עונתיות',               accent: '#06b6d4' },
  { key: 'finviz-table',    label: '📋 סורק בסיסי',           accent: '#14b8a6' },
];

// האפליקציה המלאה: כל הסורקים
const APP_TABS = [
  { key: 'finviz-table', label: '📋 סורק בסיסי', accent: '#14b8a6' },
  { key: 'news',         label: '📰 חדשות',      accent: '#3b82f6' },
];

function MomentumDashboard() {
  const tabs = TABS; // אפליקציה מלאה עם כל הסורקים
  const [autoRefresh, setAutoRefresh]         = useState(30);
  const [searchInput, setSearchInput]         = useState('');
  const [searchTicker, setSearchTicker]       = useState('');
  const debounceRef = useRef(null);
  const handleSearchChange = useCallback((e) => {
    const val = e.target.value.toUpperCase();
    setSearchInput(val);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setSearchTicker(val), 400);
  }, []);
  const [viewMode, setViewMode]               = useState('finviz-table');
  const [newsCollapsed, setNewsCollapsed]     = useState(false);
  const [lastUpdateTime, setLastUpdateTime]   = useState(new Date());
  const [language, setLanguage]               = useState('he');
  const [liveMode, setLiveMode]               = useState(false);
  const [briefingForceKey, setBriefingForceKey] = useState(0);

  const normalInterval = autoRefresh > 0 ? autoRefresh * 1000 : 0;

  const { data: fdaData, refetch: refetchFda, isLoading: fdaLoading } = useQuery({
    queryKey: ['fdaCatalysts', language],
    queryFn: async () => (await api.get(`/catalyst/fda?lang=${language}`)).data,
    refetchInterval: viewMode === 'fda' ? Math.max(autoRefresh, 120) * 1000 : 0,
    enabled: viewMode === 'fda',
    keepPreviousData: true,
    staleTime: 120000,
  });

  const { data: techSignalsData, refetch: refetchTechSignals, isLoading: techSignalsLoading } = useQuery({
    queryKey: ['techSignals'],
    queryFn: async () => (await api.get('/scanner/signals')).data,
    enabled: viewMode === 'tech-signals',
    staleTime: 15 * 60 * 1000,
    refetchInterval: 0,
    keepPreviousData: true,
  });

  const { data: dailyAnalysisData, refetch: refetchDailyAnalysis, isLoading: dailyAnalysisLoading } = useQuery({
    queryKey: ['dailyAnalysis'],
    queryFn: async () => (await api.get('/analysis/daily')).data,
    enabled: viewMode === 'daily-analysis',
    staleTime: 15 * 60 * 1000,
    refetchInterval: 0,
    keepPreviousData: true,
  });

  const { data: briefingData, isLoading: briefingLoading } = useQuery({
    queryKey: ['dailyBriefing', briefingForceKey],
    queryFn: async () => (await api.get('/briefing/daily')).data,
    enabled: viewMode === 'briefing',
    staleTime: 30 * 60 * 1000,
    refetchInterval: (data) => (data?.loading || !data?.stocks?.length) ? 10000 : 0,
    keepPreviousData: true,
  });

  const refetchBriefing = () => setBriefingForceKey(k => k + 1);

  const { data: newsData } = useQuery({
    queryKey: ['news', searchTicker, language],
    queryFn: async () => {
      const params = searchTicker
        ? `?ticker=${searchTicker}&hours=24&limit=30&lang=${language}`
        : `?hours=24&limit=30&lang=${language}&midcap_plus=true`;
      return (await api.get(`/news${params}`)).data;
    },
    refetchInterval: viewMode === 'news' ? normalInterval : 60000,
    staleTime: 30000,
    keepPreviousData: true,
  });

  const { data: searchedStock } = useQuery({
    queryKey: ['searchStock', searchTicker, language],
    queryFn: async () => {
      if (!searchTicker) return null;
      try {
        const r = await api.get(`/stock/${searchTicker.toUpperCase()}?lang=${language}`);
        return r.data.error ? null : r.data;
      } catch { return null; }
    },
    enabled: searchTicker.length >= 2,
    staleTime: 60000,
    keepPreviousData: true,
  });

  const { data: searchedBriefing, isFetching: briefingSearchLoading } = useQuery({
    queryKey: ['tickerBriefing', searchTicker],
    queryFn: async () => {
      if (!searchTicker) return null;
      try {
        const r = await api.get(`/briefing/ticker/${searchTicker.toUpperCase()}`);
        return r.data?.error ? null : r.data;
      } catch { return null; }
    },
    enabled: searchTicker.length >= 1,
    staleTime: 5 * 60 * 1000,
    keepPreviousData: true,
  });

  const handleQuickRefresh = () => {
    setLastUpdateTime(new Date());
    if (viewMode === 'briefing')           refetchBriefing();
    else if (viewMode === 'fda')           refetchFda();
    else if (viewMode === 'tech-signals')  refetchTechSignals();
    else if (viewMode === 'daily-analysis') refetchDailyAnalysis();
  };

  const isAnyLoading = fdaLoading || techSignalsLoading
    || dailyAnalysisLoading || briefingLoading;

  // Cross-scanner map (memoized)
  const SCANNER_LABELS = { briefing: '☀️ בריפינג', techSignals: '📈 סיגנלים', dailyAnalysis: '🎯 ניתוח יומי' };
  const crossScannerMap = useMemo(() => {
    const scannerSets = {
      briefing:      new Set((briefingData?.stocks || []).map(s => s.ticker)),
      techSignals:   new Set((techSignalsData?.stocks || []).map(s => s.ticker)),
      dailyAnalysis: new Set((dailyAnalysisData?.stocks || []).map(s => s.ticker)),
    };
    const map = {};
    for (const [key, tickers] of Object.entries(scannerSets)) {
      for (const ticker of tickers) {
        if (!map[ticker]) map[ticker] = [];
        map[ticker].push(SCANNER_LABELS[key]);
      }
    }
    Object.keys(map).forEach(t => {
      if (map[t].length < 2) delete map[t];
    });
    return map;
  }, [briefingData, techSignalsData, dailyAnalysisData]);

  const tabCount =
    viewMode === 'fda'            ? `${fdaData?.count || 0} אירועים` :
    viewMode === 'tech-signals'   ? `${techSignalsData?.count || 0} מניות` :
    viewMode === 'daily-analysis' ? `${dailyAnalysisData?.count || 0} מניות` :
    viewMode === 'news'           ? `${newsData?.length || 0} כתבות` : '';

  const activeTab = tabs.find(t => t.key === viewMode);

  // Scroll active tab into view on mobile
  const activeTabRef = useRef(null);
  useEffect(() => {
    if (activeTabRef.current) {
      activeTabRef.current.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' });
    }
  }, [viewMode]);

  return (
    <div className="min-h-screen" style={{ background: '#080c14', color: '#e2e8f0' }}>

      {/* ── Slim header ── */}
      <header className="sticky top-0 z-30 h-14 flex items-center px-3 sm:px-5 gap-2 sm:gap-4 border-b safe-top"
        style={{ background: '#0d1117', borderColor: 'rgba(255,255,255,0.05)', paddingTop: 'max(0.75rem, env(safe-area-inset-top))' }}>

        {/* Logo */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)' }}>
            <Zap size={14} className="text-white" />
          </div>
          <span className="text-white font-black tracking-tight text-sm hidden sm:block">STOCK SCANNER</span>
          <span className="text-[10px] text-slate-500 hidden sm:inline" title="גרסה נוכחית">v2</span>
        </div>

        {/* Arena IB status — removed */}

        {/* Search — center */}
        <div className="relative flex-1 max-w-sm mx-auto">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2" size={13}
            style={{ color: '#475569' }} />
          <input
            type="text"
            placeholder="חיפוש טיקר... (AAPL, TSLA...)"
            value={searchInput}
            onChange={handleSearchChange}
            className="w-full pl-8 pr-4 py-1.5 text-sm rounded-lg focus:outline-none transition-all"
            style={{
              background: '#161b22',
              border: '1px solid rgba(255,255,255,0.06)',
              color: '#e2e8f0',
              fontFamily: 'inherit',
            }}
            onFocus={e => (e.target.style.borderColor = 'rgba(59,130,246,0.5)')}
            onBlur={e => (e.target.style.borderColor = 'rgba(255,255,255,0.06)')}
          />
        </div>

        {/* Controls */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Language */}
          <div className="flex rounded-lg overflow-hidden text-xs font-bold"
            style={{ border: '1px solid rgba(255,255,255,0.06)' }}>
            {['en','he'].map(lang => (
              <button key={lang} onClick={() => setLanguage(lang)}
                className="px-2.5 py-1.5 transition-all"
                style={{
                  background: language === lang ? '#3b82f6' : 'transparent',
                  color: language === lang ? '#fff' : '#64748b',
                }}>
                {lang === 'en' ? 'EN' : 'עב'}
              </button>
            ))}
          </div>

          {/* Live mode */}
          <button
            onClick={() => { setLiveMode(!liveMode); setAutoRefresh(liveMode ? 0 : 30); }}
            className="px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all"
            style={{
              background: liveMode ? 'rgba(239,68,68,0.15)' : 'rgba(255,255,255,0.04)',
              border: `1px solid ${liveMode ? 'rgba(239,68,68,0.4)' : 'rgba(255,255,255,0.06)'}`,
              color: liveMode ? '#f87171' : '#64748b',
            }}>
            {liveMode ? (
              <>
                <span className="w-1.5 h-1.5 rounded-full bg-red-400 animate-pulse" />
                <span className="hidden sm:inline">LIVE</span>
              </>
            ) : <span className="hidden sm:inline">⏸ עצור</span>}
          </button>

          {/* Refresh interval */}
          <select
            value={autoRefresh}
            onChange={e => { const v = Number(e.target.value); setAutoRefresh(v); setLiveMode(v > 0 && v <= 10); }}
            className="hidden sm:block px-2 py-1.5 text-xs rounded-lg focus:outline-none"
            style={{
              background: '#161b22',
              border: '1px solid rgba(255,255,255,0.06)',
              color: '#64748b',
            }}>
            <option value={5}>⚡ 5s</option>
            <option value={10}>🔥 10s</option>
            <option value={30}>30s</option>
            <option value={60}>1m</option>
            <option value={120}>2m</option>
            <option value={0}>ידני</option>
          </select>

          {/* Refresh button */}
          <button onClick={handleQuickRefresh}
            className="px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all"
            style={{
              background: 'rgba(59,130,246,0.12)',
              border: '1px solid rgba(59,130,246,0.3)',
              color: '#60a5fa',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'rgba(59,130,246,0.2)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'rgba(59,130,246,0.12)')}>
            <RefreshCw size={11} className={isAnyLoading ? 'animate-spin' : ''} />
            רענן
          </button>
        </div>
      </header>

      {/* ── Tab bar ── */}
      <nav className="sticky top-14 z-20 border-b overflow-x-auto"
        style={{ background: '#0d1117', borderColor: 'rgba(255,255,255,0.05)' }}>
        <div className="flex items-stretch px-2">
          {tabs.map(tab => {
            const isActive = viewMode === tab.key;
            return (
              <button key={tab.key}
                ref={isActive ? activeTabRef : null}
                onClick={() => setViewMode(tab.key)}
                className="relative px-4 py-3 text-sm font-semibold whitespace-nowrap transition-all flex items-center gap-1.5"
                style={{ color: isActive ? '#fff' : '#475569' }}
                onMouseEnter={e => { if (!isActive) e.currentTarget.style.color = '#94a3b8'; }}
                onMouseLeave={e => { if (!isActive) e.currentTarget.style.color = '#475569'; }}>
                {tab.label}
                {/* Active indicator */}
                {isActive && (
                  <div className="absolute bottom-0 left-2 right-2 h-0.5 rounded-full"
                    style={{ background: tab.accent, boxShadow: `0 0 8px ${tab.accent}88` }} />
                )}
              </button>
            );
          })}

          {/* Right side: count + update time */}
          <div className="ml-auto flex items-center gap-3 px-4">
            {tabCount && <span className="text-xs" style={{ color: '#475569' }}>{tabCount}</span>}
            <span className="text-xs flex items-center gap-1" style={{ color: '#475569' }}>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              {new Date(lastUpdateTime).toLocaleTimeString('he-IL', { hour: '2-digit', minute: '2-digit' })}
            </span>
          </div>
        </div>
      </nav>

      {/* ── Main content ── */}
      <main className="px-2 sm:px-4 py-4 w-full" style={{ paddingBottom: 'max(1rem, env(safe-area-inset-bottom))' }}>

        {/* ── Horizontal news ticker (replaces right sidebar) ── */}
        {viewMode !== 'news' && newsData && newsData.length > 0 && (
          <div className="mb-4 rounded-xl overflow-hidden"
            style={{
              background: '#0d1117',
              border: '1px solid rgba(255,255,255,0.06)',
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            }}>
            <div
              className="flex items-center gap-3 px-4 py-2"
              style={{
                borderBottom: newsCollapsed ? 'none' : '1px solid rgba(255,255,255,0.05)',
                cursor: 'pointer',
              }}
              onClick={() => setNewsCollapsed(c => !c)}
            >
              <span className="text-xs font-black text-white whitespace-nowrap">📰 חדשות שוק</span>
              <span className="text-xs" style={{ color: '#475569' }}>{newsData.length} כתבות</span>

              {/* Collapsed: show mini preview of top tickers with price change */}
              {newsCollapsed && (
                <div className="flex items-center gap-2 overflow-hidden" style={{ maxWidth: '70%' }}>
                  {newsData.slice(0, 6).map((item, i) => {
                    const tk = item.tickers ? item.tickers.split(',')[0]?.trim() : '';
                    if (!tk) return null;
                    const tc = (item.ticker_changes || {})[tk];
                    const chg = tc?.change_pct;
                    return (
                      <span key={i} className="font-mono font-bold px-1.5 py-0.5 rounded flex items-center gap-1.5"
                        style={{ background: 'rgba(251,191,36,0.1)', color: '#fbbf24', fontSize: 11 }}>
                        {tk}
                        {chg != null && (
                          <span style={{
                            color: chg >= 0 ? '#4ade80' : '#f87171',
                            fontSize: 11, fontWeight: 900,
                          }}>
                            {chg >= 0 ? '+' : ''}{chg.toFixed(1)}%
                          </span>
                        )}
                      </span>
                    );
                  })}
                </div>
              )}

              <div className="flex-1" />
              <button
                onClick={(e) => { e.stopPropagation(); setViewMode('news'); }}
                className="text-xs px-2 py-1 rounded-md transition-colors"
                style={{ color: '#60a5fa', background: 'rgba(96,165,250,0.08)', border: '1px solid rgba(96,165,250,0.15)' }}
              >
                הכל →
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); setNewsCollapsed(c => !c); }}
                className="text-xs px-1.5 py-1 rounded-md transition-all"
                style={{ color: '#94a3b8', background: 'rgba(148,163,184,0.08)', border: '1px solid rgba(148,163,184,0.12)' }}
                title={newsCollapsed ? 'הרחב חדשות' : 'מזער חדשות'}
              >
                <span style={{
                  display: 'inline-block',
                  transition: 'transform 0.3s ease',
                  transform: newsCollapsed ? 'rotate(180deg)' : 'rotate(0deg)',
                }}>▲</span>
              </button>
            </div>
            <div style={{
              maxHeight: newsCollapsed ? 0 : 200,
              opacity: newsCollapsed ? 0 : 1,
              overflow: 'hidden',
              transition: 'max-height 0.35s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.25s ease',
            }}>
              <div className="flex gap-3 px-4 py-3 overflow-x-auto" style={{ scrollbarWidth: 'thin', scrollbarColor: '#1e293b transparent' }}>
                {newsData.slice(0, 12).map((item, idx) => {
                  const tickers = item.tickers ? item.tickers.split(',').map(t => t.trim()).filter(t => t) : [];
                  const timeAgo = (() => {
                    const d = new Date(item.published_at);
                    const diff = Math.floor((Date.now() - d) / 60000);
                    if (diff < 60) return `${diff}m`;
                    if (diff < 1440) return `${Math.floor(diff / 60)}h`;
                    return d.toLocaleDateString();
                  })();
                  const moveReason = getReasonFromTitle(item.title);
                  return (
                    <a key={item.id || idx} href={item.url} target="_blank" rel="noopener noreferrer"
                      className="flex-shrink-0 rounded-lg p-3 transition-all hover:scale-[1.02]"
                      style={{
                        width: 260, minWidth: 260,
                        background: 'rgba(30,41,59,0.3)', border: '1px solid rgba(51,65,85,0.3)',
                      }}
                      onMouseEnter={e => { e.currentTarget.style.borderColor = 'rgba(96,165,250,0.3)'; e.currentTarget.style.background = 'rgba(30,41,59,0.5)'; }}
                      onMouseLeave={e => { e.currentTarget.style.borderColor = 'rgba(51,65,85,0.3)'; e.currentTarget.style.background = 'rgba(30,41,59,0.3)'; }}
                    >
                      <div className="flex items-center gap-2 mb-1.5">
                        <span className="px-1.5 py-0.5 rounded text-xs font-semibold"
                          style={{ background: 'rgba(96,165,250,0.12)', color: '#60a5fa', fontSize: 9 }}>
                          {item.source?.replace(/_/g, ' ').substring(0, 20)}
                        </span>
                        {tickers.length > 0 && (
                          <span className="font-mono text-xs font-bold" style={{ color: '#fbbf24' }}>
                            {tickers[0]}
                          </span>
                        )}
                        <span className="text-xs ml-auto" style={{ color: '#475569' }}>{timeAgo}</span>
                      </div>
                      <div className="text-xs font-medium leading-snug line-clamp-2" style={{ color: '#e2e8f0' }} dir="rtl">
                        {item.title}
                      </div>
                      {/* Price change since news — prominent bar */}
                      {tickers.length > 0 && (() => {
                        const tc = (item.ticker_changes || {})[tickers[0]];
                        const chg = tc?.change_pct;
                        const price = tc?.price;
                        if (chg == null) return null;
                        const isUp = chg >= 0;
                        const big = Math.abs(chg) >= 5;
                        return (
                          <div style={{
                            marginTop: 6, padding: '4px 8px', borderRadius: 6,
                            background: isUp ? 'rgba(74,222,128,0.13)' : 'rgba(248,113,113,0.13)',
                            border: `1px solid ${isUp ? 'rgba(74,222,128,0.35)' : 'rgba(248,113,113,0.35)'}`,
                            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                          }}>
                            <span style={{
                              fontSize: big ? 14 : 12, fontWeight: 900, fontFamily: 'monospace',
                              color: isUp ? '#4ade80' : '#f87171',
                            }}>
                              {isUp ? '▲' : '▼'} {isUp ? '+' : ''}{chg.toFixed(1)}%
                            </span>
                            {price != null && (
                              <span style={{ fontSize: 10, color: '#94a3b8', fontFamily: 'monospace' }}>
                                ${price.toFixed(2)}
                              </span>
                            )}
                          </div>
                        );
                      })()}
                      {/* Move reason badge */}
                      {moveReason && (
                        <div style={{
                          marginTop: 5, display: 'inline-flex', alignItems: 'center',
                          padding: '2px 7px', borderRadius: 4,
                          background: `${moveReason.color}18`,
                          border: `1px solid ${moveReason.color}40`,
                        }}>
                          <span style={{ fontSize: 10, fontWeight: 700, color: moveReason.color, direction: 'rtl' }}>
                            💡 {moveReason.label}
                          </span>
                        </div>
                      )}
                    </a>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        <div className="w-full">

          {/* Full-width main content */}
          <div className="space-y-4">

            {/* Searched stock card */}
            {searchedStock && (
              <div className="rounded-xl p-4"
                style={{ background: '#0d1117', border: '1px solid rgba(59,130,246,0.25)' }}>
                <div className="flex items-center gap-4 flex-wrap">
                  <div className="flex items-baseline gap-3">
                    <span className="text-2xl font-black text-white">{searchedStock.ticker}</span>
                    {searchedStock.live_data?.price > 0 && (
                      <span className="text-xl font-black font-mono text-white tabular-nums">
                        ${searchedStock.live_data.price.toFixed(2)}
                      </span>
                    )}
                    {searchedStock.live_data?.change_percent != null && (
                      <span className={`text-lg font-black ${searchedStock.live_data.change_percent >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                        {searchedStock.live_data.change_percent >= 0 ? '▲' : '▼'}{Math.abs(searchedStock.live_data.change_percent || 0).toFixed(2)}%
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 flex-wrap ml-auto">
                    {searchedStock.live_data?.company_name && (
                      <span className="text-sm" style={{ color: '#64748b' }}>{searchedStock.live_data.company_name}</span>
                    )}
                    {searchedStock.live_data?.market_cap > 0 && (
                      <span className="px-2 py-0.5 rounded text-xs font-bold"
                        style={{ background: 'rgba(99,102,241,0.15)', border: '1px solid rgba(99,102,241,0.3)', color: '#a5b4fc' }}>
                        {searchedStock.live_data.market_cap >= 1e12 ? `$${(searchedStock.live_data.market_cap/1e12).toFixed(1)}T`
                          : searchedStock.live_data.market_cap >= 1e9  ? `$${(searchedStock.live_data.market_cap/1e9).toFixed(1)}B`
                          : `$${(searchedStock.live_data.market_cap/1e6).toFixed(0)}M`}
                      </span>
                    )}
                    <a href={`https://www.tradingview.com/chart/?symbol=${searchedStock.ticker}`}
                      target="_blank" rel="noopener noreferrer"
                      className="px-3 py-1 rounded text-xs font-semibold"
                      style={{ background: 'rgba(139,92,246,0.15)', border: '1px solid rgba(139,92,246,0.3)', color: '#c4b5fd' }}>
                      TradingView ↗
                    </a>
                    <a href={`https://finance.yahoo.com/quote/${searchedStock.ticker}`}
                      target="_blank" rel="noopener noreferrer"
                      className="px-3 py-1 rounded text-xs font-semibold"
                      style={{ background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.08)', color: '#94a3b8' }}>
                      Yahoo ↗
                    </a>
                  </div>
                </div>
                {searchedStock.live_data?.volume > 0 && (
                  <div className="flex gap-4 mt-2 text-xs" style={{ color: '#475569' }}>
                    <span>Vol: {searchedStock.live_data.volume >= 1e6
                      ? `${(searchedStock.live_data.volume/1e6).toFixed(1)}M`
                      : `${(searchedStock.live_data.volume/1e3).toFixed(0)}K`}</span>
                    {searchedStock.live_data?.day_high > 0 && <span>H: ${searchedStock.live_data.day_high.toFixed(2)}</span>}
                    {searchedStock.live_data?.day_low  > 0 && <span>L: ${searchedStock.live_data.day_low.toFixed(2)}</span>}
                  </div>
                )}
              </div>
            )}

            {/* Ticker briefing card */}
            {searchTicker.length >= 1 && (briefingSearchLoading || searchedBriefing) && (
              <div className="rounded-xl p-4"
                style={{ background: '#0d1117', border: '1px solid rgba(139,92,246,0.25)' }}>
                {briefingSearchLoading && !searchedBriefing ? (
                  <div className="flex items-center gap-2 text-sm" style={{ color: '#a78bfa' }}>
                    <RefreshCw size={14} className="animate-spin" />
                    מנתח את {searchTicker}...
                  </div>
                ) : searchedBriefing && (
                  <div className="space-y-2">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold uppercase tracking-wider" style={{ color: '#a78bfa' }}>ניתוח בריפינג</span>
                      {searchedBriefing.sector && (
                        <span className="px-2 py-0.5 rounded text-xs" style={{ background: 'rgba(139,92,246,0.12)', border: '1px solid rgba(139,92,246,0.25)', color: '#c4b5fd' }}>
                          {searchedBriefing.sector}
                        </span>
                      )}
                      {searchedBriefing.rsi != null && (
                        <span className="px-2 py-0.5 rounded text-xs font-bold"
                          style={{ background: searchedBriefing.rsi > 68 ? 'rgba(239,68,68,0.12)' : searchedBriefing.rsi < 42 ? 'rgba(59,130,246,0.12)' : 'rgba(255,255,255,0.05)',
                            border: `1px solid ${searchedBriefing.rsi > 68 ? 'rgba(239,68,68,0.3)' : searchedBriefing.rsi < 42 ? 'rgba(59,130,246,0.3)' : 'rgba(255,255,255,0.08)'}`,
                            color: searchedBriefing.rsi > 68 ? '#fca5a5' : searchedBriefing.rsi < 42 ? '#93c5fd' : '#94a3b8' }}>
                          RSI {searchedBriefing.rsi}
                        </span>
                      )}
                      {searchedBriefing.earnings_surprise_pct != null && (
                        <span className="px-2 py-0.5 rounded text-xs font-bold"
                          style={{ background: searchedBriefing.earnings_surprise_pct >= 20 ? 'rgba(16,185,129,0.12)' : 'rgba(255,255,255,0.05)',
                            border: `1px solid ${searchedBriefing.earnings_surprise_pct >= 20 ? 'rgba(16,185,129,0.3)' : 'rgba(255,255,255,0.08)'}`,
                            color: searchedBriefing.earnings_surprise_pct >= 20 ? '#6ee7b7' : '#94a3b8' }}>
                          Beat {searchedBriefing.earnings_surprise_pct > 0 ? '+' : ''}{searchedBriefing.earnings_surprise_pct}%
                        </span>
                      )}
                    </div>
                    {searchedBriefing.reason && (
                      <p className="text-sm leading-relaxed" style={{ color: '#cbd5e1' }} dir="rtl">{searchedBriefing.reason}</p>
                    )}
                    <div className="flex items-center gap-4 text-xs flex-wrap" style={{ color: '#475569' }}>
                      {searchedBriefing.watch_level && (
                        <span>⚡ לצפות: <span style={{ color: '#fde047' }} className="font-semibold">{searchedBriefing.watch_level}</span></span>
                      )}
                      {searchedBriefing.support > 0 && (
                        <span>תמיכה: <span style={{ color: '#4ade80' }} className="font-mono">${searchedBriefing.support}</span></span>
                      )}
                      {searchedBriefing.price_change_since_earnings !== 0 && (
                        <span>מאז דוח: <span style={{ color: searchedBriefing.price_change_since_earnings > 0 ? '#4ade80' : '#f87171' }} className="font-bold">
                          {searchedBriefing.price_change_since_earnings > 0 ? '+' : ''}{searchedBriefing.price_change_since_earnings}%
                        </span></span>
                      )}
                    </div>
                    {((searchedBriefing.tailwinds?.length || 0) + (searchedBriefing.headwinds?.length || 0)) > 0 && (
                      <div className="flex gap-1.5 flex-wrap">
                        {(searchedBriefing.tailwinds || []).map((tw, i) => (
                          <span key={i} className="px-2 py-0.5 rounded-full text-xs"
                            style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid rgba(16,185,129,0.25)', color: '#6ee7b7' }}>
                            ↑ {tw}
                          </span>
                        ))}
                        {(searchedBriefing.headwinds || []).map((hw, i) => (
                          <span key={i} className="px-2 py-0.5 rounded-full text-xs"
                            style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.25)', color: '#fca5a5' }}>
                            ↓ {hw}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* ── Tab content ── */}
            <Suspense fallback={<div style={{ padding: 40, textAlign: 'center', color: '#64748b' }}>טוען...</div>}>
            {viewMode === 'briefing' ? (
              <DailyBriefing
                data={briefingData}
                loading={briefingLoading}
                onRefetch={refetchBriefing}
                crossScannerMap={crossScannerMap}
              />
            ) : (
              <div className="rounded-xl overflow-hidden"
                style={{ background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)' }}>
                {activeTab && (
                  <div className="h-0.5 w-full"
                    style={{ background: `linear-gradient(to right, ${activeTab.accent}, transparent)` }} />
                )}
                <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 160px)' }}>
                  {viewMode === 'arena' ? (
                    <StrategyArena />
                  ) : viewMode === 'fda' ? (
                    <FDACatalystTracker events={fdaData?.events || []} loading={fdaLoading} viewMode="fda" />
                  ) : viewMode === 'tech-signals' ? (
                    <TechnicalSignalsScanner data={techSignalsData} loading={techSignalsLoading} onRefetch={refetchTechSignals} crossScannerMap={crossScannerMap} />
                  ) : viewMode === 'daily-analysis' ? (
                    <DailyAnalysisScanner data={dailyAnalysisData} loading={dailyAnalysisLoading} onRefetch={refetchDailyAnalysis} crossScannerMap={crossScannerMap} />
                  ) : viewMode === 'ib' ? (
                    <IBPortfolio />
                  ) : viewMode === 'pattern-bot' ? (
                    <PatternScanner />
                  ) : viewMode === 'seasonality' ? (
                    <SeasonalityScanner />
                  ) : viewMode === 'finviz-table' ? (
                    <FinvizTableScanner ensureTickers={searchTicker?.trim().toUpperCase() || undefined} refreshSec={autoRefresh} />
                  ) : viewMode === 'news' ? (
                    <div className="p-4">
                      <NewsPanel news={newsData} />
                    </div>
                  ) : null}
                </div>
              </div>
            )}
            </Suspense>
          </div>

        </div>
      </main>

    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <MomentumDashboard />
      <Suspense fallback={null}>
        <AlertSystem />
      </Suspense>
    </QueryClientProvider>
  );
}
