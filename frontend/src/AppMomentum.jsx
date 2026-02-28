import { useState } from 'react';
import { useQuery, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RefreshCw, Zap, Search } from 'lucide-react';
import axios from 'axios';
import TrendingStocks from './components/TrendingStocks';
import FDACatalystTracker from './components/FDACatalystTracker';
import DailyBriefing from './components/DailyBriefing';
import DemoPortfolio from './components/DemoPortfolio';
import TechnicalSignalsScanner from './components/TechnicalSignalsScanner';
import DailyAnalysisScanner from './components/DailyAnalysisScanner';
import NewsPanel from './components/NewsPanel';
import AIAssistant from './components/AIAssistant';
import IBPortfolio from './components/IBPortfolio';
import AlertSystem from './components/AlertSystem';
import FinvizTableScanner from './components/FinvizTableScanner';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30000,
      cacheTime: 5 * 60000,
    },
  },
});

const API_BASE = '/api';
const api = axios.create({ baseURL: API_BASE, timeout: 30000 });

// Tab definitions with accent hex colors for the active underline
const TABS = [
  { key: 'briefing',        label: '☀️ בריפינג',            accent: '#f59e0b' },
  { key: 'portfolio',       label: '💼 תיק דמו',             accent: '#f43f5e' },
  { key: 'trending',        label: '🔥 הכי מדוברות',         accent: '#a855f7' },
  { key: 'fda',             label: '💊 FDA',                  accent: '#22c55e' },
  { key: 'tech-catalyst',   label: '🖥️ קטליסטים',            accent: '#06b6d4' },
  { key: 'tech-signals',    label: '📈 סיגנלים',             accent: '#6366f1' },
  { key: 'daily-analysis',  label: '🎯 ניתוח יומי',           accent: '#8b5cf6' },
  { key: 'ib',              label: '🏦 IB חשבון',             accent: '#3b82f6' },
  { key: 'finviz-table',   label: '📋 סורק בסיסי',           accent: '#14b8a6' },
];

function MomentumDashboard() {
  const [autoRefresh, setAutoRefresh]         = useState(30);
  const [searchTicker, setSearchTicker]       = useState('');
  const [viewMode, setViewMode]               = useState('briefing');
  const [lastUpdateTime, setLastUpdateTime]   = useState(new Date());
  const [language, setLanguage]               = useState('he');
  const [liveMode, setLiveMode]               = useState(false);
  const [briefingForceKey, setBriefingForceKey] = useState(0);

  const normalInterval = autoRefresh > 0 ? autoRefresh * 1000 : 0;

  const { data: trendingData, refetch: refetchTrending, isLoading: trendingLoading } = useQuery({
    queryKey: ['trendingStocks', language],
    queryFn: async () => (await api.get(`/trending/social?lang=${language}`)).data,
    refetchInterval: viewMode === 'trending' ? normalInterval : 0,
    enabled: viewMode === 'trending',
    keepPreviousData: true,
  });

  const { data: fdaData, refetch: refetchFda, isLoading: fdaLoading } = useQuery({
    queryKey: ['fdaCatalysts', language],
    queryFn: async () => (await api.get(`/catalyst/fda?lang=${language}`)).data,
    refetchInterval: viewMode === 'fda' ? Math.max(autoRefresh, 120) * 1000 : 0,
    enabled: viewMode === 'fda',
    keepPreviousData: true,
    staleTime: 120000,
  });

  const { data: techCatalystData, refetch: refetchTechCatalyst, isLoading: techCatalystLoading } = useQuery({
    queryKey: ['techCatalysts', language],
    queryFn: async () => (await api.get(`/catalyst/tech?lang=${language}`)).data,
    refetchInterval: viewMode === 'tech-catalyst' ? Math.max(autoRefresh, 120) * 1000 : 0,
    enabled: viewMode === 'tech-catalyst',
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
    refetchInterval: normalInterval,
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
    enabled: searchTicker.length >= 1,
    refetchInterval: normalInterval,
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
    if (viewMode === 'briefing')         refetchBriefing();
    else if (viewMode === 'fda')         refetchFda();
    else if (viewMode === 'tech-catalyst') refetchTechCatalyst();
    else if (viewMode === 'tech-signals')  refetchTechSignals();
    else if (viewMode === 'daily-analysis') refetchDailyAnalysis();
    else refetchTrending();
  };

  const isAnyLoading = fdaLoading || techCatalystLoading || techSignalsLoading
    || dailyAnalysisLoading || trendingLoading || briefingLoading;

  // Cross-scanner map
  const SCANNER_LABELS = { briefing: '☀️ בריפינג', techSignals: '📈 סיגנלים', dailyAnalysis: '🎯 ניתוח יומי' };
  const scannerSets = {
    briefing:      new Set((briefingData?.stocks || []).map(s => s.ticker)),
    techSignals:   new Set((techSignalsData?.stocks || []).map(s => s.ticker)),
    dailyAnalysis: new Set((dailyAnalysisData?.stocks || []).map(s => s.ticker)),
  };
  const crossScannerMap = {};
  for (const [key, tickers] of Object.entries(scannerSets)) {
    for (const ticker of tickers) {
      if (!crossScannerMap[ticker]) crossScannerMap[ticker] = [];
      crossScannerMap[ticker].push(SCANNER_LABELS[key]);
    }
  }
  Object.keys(crossScannerMap).forEach(t => {
    if (crossScannerMap[t].length < 2) delete crossScannerMap[t];
  });

  const tabCount =
    viewMode === 'fda'            ? `${fdaData?.count || 0} אירועים` :
    viewMode === 'tech-catalyst'  ? `${techCatalystData?.count || 0} אירועים` :
    viewMode === 'tech-signals'   ? `${techSignalsData?.count || 0} מניות` :
    viewMode === 'daily-analysis' ? `${dailyAnalysisData?.count || 0} מניות` :
    viewMode === 'trending'       ? `${trendingData?.trending?.length || 0} מניות` : '';

  const activeTab = TABS.find(t => t.key === viewMode);

  return (
    <div className="min-h-screen" style={{ background: '#080c14', color: '#e2e8f0' }}>

      {/* ── Slim header ── */}
      <header className="sticky top-0 z-30 h-14 flex items-center px-5 gap-4 border-b"
        style={{ background: '#0d1117', borderColor: 'rgba(255,255,255,0.05)' }}>

        {/* Logo */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
            style={{ background: 'linear-gradient(135deg, #3b82f6, #8b5cf6)' }}>
            <Zap size={14} className="text-white" />
          </div>
          <span className="text-white font-black tracking-tight text-sm hidden sm:block">STOCK SCANNER</span>
        </div>

        {/* Search — center */}
        <div className="relative flex-1 max-w-sm mx-auto">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2" size={13}
            style={{ color: '#475569' }} />
          <input
            type="text"
            placeholder="חיפוש טיקר... (AAPL, TSLA...)"
            value={searchTicker}
            onChange={e => setSearchTicker(e.target.value.toUpperCase())}
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
                LIVE
              </>
            ) : '⏸ עצור'}
          </button>

          {/* Refresh interval */}
          <select
            value={autoRefresh}
            onChange={e => { const v = Number(e.target.value); setAutoRefresh(v); setLiveMode(v > 0 && v <= 10); }}
            className="px-2 py-1.5 text-xs rounded-lg focus:outline-none"
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
          {TABS.map(tab => {
            const isActive = viewMode === tab.key;
            return (
              <button key={tab.key}
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
      <main className="px-4 py-4 w-full">
        <div className="grid grid-cols-1 xl:grid-cols-5 lg:grid-cols-4 gap-4">

          {/* Left: 4/5 on XL, 3/4 on LG — main content */}
          <div className="xl:col-span-4 lg:col-span-3 space-y-4">

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
            {viewMode === 'briefing' ? (
              /* Briefing has its own beautiful header — no wrapper */
              <DailyBriefing
                data={briefingData}
                loading={briefingLoading}
                onRefetch={refetchBriefing}
                crossScannerMap={crossScannerMap}
              />
            ) : (
              /* All other tabs: minimal card wrapper */
              <div className="rounded-xl overflow-hidden"
                style={{ background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)' }}>
                {/* Thin colored tab accent at top */}
                {activeTab && (
                  <div className="h-0.5 w-full"
                    style={{ background: `linear-gradient(to right, ${activeTab.accent}, transparent)` }} />
                )}
                <div className="overflow-y-auto" style={{ maxHeight: 'calc(100vh - 160px)' }}>
                  {viewMode === 'portfolio' ? (
                    <DemoPortfolio />
                  ) : viewMode === 'fda' ? (
                    <FDACatalystTracker events={fdaData?.events || []} loading={fdaLoading} viewMode="fda" />
                  ) : viewMode === 'tech-catalyst' ? (
                    <FDACatalystTracker events={techCatalystData?.events || []} loading={techCatalystLoading} viewMode="tech" />
                  ) : viewMode === 'tech-signals' ? (
                    <TechnicalSignalsScanner data={techSignalsData} loading={techSignalsLoading} onRefetch={refetchTechSignals} crossScannerMap={crossScannerMap} />
                  ) : viewMode === 'daily-analysis' ? (
                    <DailyAnalysisScanner data={dailyAnalysisData} loading={dailyAnalysisLoading} onRefetch={refetchDailyAnalysis} crossScannerMap={crossScannerMap} />
                  ) : viewMode === 'ib' ? (
                    <IBPortfolio />
                  ) : viewMode === 'finviz-table' ? (
                    <FinvizTableScanner />
                  ) : (
                    <TrendingStocks stocks={trendingData?.trending || []} loading={trendingLoading} />
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Right: 1/5 on XL, 1/4 on LG — news panel */}
          <div className="xl:col-span-1 lg:col-span-1">
            <div className="rounded-xl overflow-hidden sticky"
              style={{ background: '#0d1117', border: '1px solid rgba(255,255,255,0.06)', top: '7.5rem' }}>
              <div className="px-4 py-3 border-b" style={{ borderColor: 'rgba(255,255,255,0.05)' }}>
                <h2 className="text-sm font-black text-white">חדשות שוק</h2>
                <p className="text-xs mt-0.5" style={{ color: '#475569' }}>{newsData?.length || 0} כתבות</p>
              </div>
              <div className="p-3 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 160px)' }}>
                <NewsPanel news={newsData} />
              </div>
            </div>
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
      <AIAssistant />
      <AlertSystem />
    </QueryClientProvider>
  );
}
