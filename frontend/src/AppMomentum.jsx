import { useState } from 'react';
import { useQuery, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RefreshCw, Zap, Filter, Search, TrendingUp } from 'lucide-react';
import axios from 'axios';
import MomentumScanner from './components/MomentumScanner';
import MomentumScannerPro from './components/MomentumScannerPro';
import VWAPMomentumScanner from './components/VWAPMomentumScanner';
import TrendingStocks from './components/TrendingStocks';
import FDACatalystTracker from './components/FDACatalystTracker';
import QuickStats from './components/QuickStats';
import NewsPanel from './components/NewsPanel';
import MarketStatus from './components/MarketStatus';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30000,      // Data considered fresh for 30s
      cacheTime: 5 * 60000,  // Keep in cache for 5 minutes
    },
  },
});

const API_BASE = '/api';

// Axios instance with timeout to prevent stuck requests
const api = axios.create({
  baseURL: API_BASE,
  timeout: 30000, // 30 second timeout — never hang forever
});

function MomentumDashboard() {
  const [autoRefresh, setAutoRefresh] = useState(10); // seconds - default 10s for live feel
  const [searchTicker, setSearchTicker] = useState('');
  const [minMomentum, setMinMomentum] = useState(60);
  const [viewMode, setViewMode] = useState('pulse'); // 'pulse', 'scanner', 'trending', 'vwap', 'fda', 'tech-catalyst'
  const [lastUpdateTime, setLastUpdateTime] = useState(new Date());
  const [language, setLanguage] = useState('he'); // 'en' or 'he'
  const [liveMode, setLiveMode] = useState(true); // Live price updates

  // VWAP tab uses longer interval (heavy endpoint, cached on backend for 60s)
  const vwapInterval = autoRefresh > 0 ? Math.max(autoRefresh, 60) * 1000 : 0;
  const normalInterval = autoRefresh > 0 ? autoRefresh * 1000 : 0;

  // Fetch Market Pulse — only when active
  const { data: pulseData, refetch: refetchPulse, isLoading: pulseLoading } = useQuery({
    queryKey: ['marketPulse', language],
    queryFn: async () => {
      const response = await api.get(`/momentum/market-pulse?limit=50&lang=${language}`);
      setLastUpdateTime(new Date());
      return response.data;
    },
    refetchInterval: viewMode === 'pulse' ? normalInterval : 0,
    enabled: viewMode === 'pulse',
    keepPreviousData: true,
  });

  // Fetch Momentum Scanner — only when active
  const { data: scannerData, refetch: refetchScanner, isLoading: scannerLoading } = useQuery({
    queryKey: ['momentumScanner', language],
    queryFn: async () => {
      const response = await api.get(`/momentum/scanner?lang=${language}`);
      return response.data;
    },
    refetchInterval: viewMode === 'scanner' ? normalInterval : 0,
    enabled: viewMode === 'scanner',
    keepPreviousData: true,
  });

  // Fetch Trending Stocks — only when active
  const { data: trendingData, refetch: refetchTrending, isLoading: trendingLoading } = useQuery({
    queryKey: ['trendingStocks', language],
    queryFn: async () => {
      const response = await api.get(`/trending/social?lang=${language}`);
      return response.data;
    },
    refetchInterval: viewMode === 'trending' ? normalInterval : 0,
    enabled: viewMode === 'trending',
    keepPreviousData: true,
  });

  // Fetch VWAP Momentum Screener — only when active, longer interval
  const { data: vwapData, refetch: refetchVwap, isLoading: vwapLoading } = useQuery({
    queryKey: ['vwapMomentum', language],
    queryFn: async () => {
      const response = await api.get(`/screener/vwap-momentum?lang=${language}`);
      return response.data;
    },
    refetchInterval: viewMode === 'vwap' ? vwapInterval : 0,
    enabled: viewMode === 'vwap',
    keepPreviousData: true,
  });

  // Fetch FDA Catalysts — only when active, longer interval (data changes slowly)
  const { data: fdaData, refetch: refetchFda, isLoading: fdaLoading } = useQuery({
    queryKey: ['fdaCatalysts', language],
    queryFn: async () => {
      const response = await api.get(`/catalyst/fda?lang=${language}`);
      return response.data;
    },
    refetchInterval: viewMode === 'fda' ? Math.max(autoRefresh, 120) * 1000 : 0,
    enabled: viewMode === 'fda',
    keepPreviousData: true,
    staleTime: 120000,
  });

  // Fetch Tech Catalysts — only when active
  const { data: techCatalystData, refetch: refetchTechCatalyst, isLoading: techCatalystLoading } = useQuery({
    queryKey: ['techCatalysts', language],
    queryFn: async () => {
      const response = await api.get(`/catalyst/tech?lang=${language}`);
      return response.data;
    },
    refetchInterval: viewMode === 'tech-catalyst' ? Math.max(autoRefresh, 120) * 1000 : 0,
    enabled: viewMode === 'tech-catalyst',
    keepPreviousData: true,
    staleTime: 120000,
  });

  // Fetch News
  const { data: newsData, refetch: refetchNews } = useQuery({
    queryKey: ['news', searchTicker, language],
    queryFn: async () => {
      const params = searchTicker
        ? `?ticker=${searchTicker}&hours=24&limit=30&lang=${language}`
        : `?hours=24&limit=30&lang=${language}`;
      const response = await api.get(`/news${params}`);
      return response.data;
    },
    refetchInterval: normalInterval,
    keepPreviousData: true,
  });

  const stocks =
    viewMode === 'pulse' ? pulseData?.stocks || [] :
    viewMode === 'scanner' ? scannerData?.opportunities || [] :
    viewMode === 'vwap' ? vwapData?.stocks || [] :
    trendingData?.trending || [];
  const isLoading =
    viewMode === 'pulse' ? pulseLoading :
    viewMode === 'scanner' ? scannerLoading :
    viewMode === 'vwap' ? vwapLoading :
    trendingLoading;

  // Fetch specific stock if search ticker is provided
  const { data: searchedStock } = useQuery({
    queryKey: ['searchStock', searchTicker, language],
    queryFn: async () => {
      if (!searchTicker || searchTicker.length < 1) return null;

      // Fetch live data for this specific ticker
      try {
        const response = await api.get(`/stock/${searchTicker.toUpperCase()}?lang=${language}`);
        return response.data.error ? null : response.data;
      } catch (err) {
        return null;
      }
    },
    enabled: searchTicker.length >= 1,
    refetchInterval: normalInterval,
    keepPreviousData: true,
  });

  // Combine regular stocks with searched stock
  const allStocks = searchedStock ? [searchedStock, ...stocks] : stocks;

  // Filter stocks
  const filteredStocks = allStocks
    .filter(s => {
      // Always show searched stock regardless of momentum score
      if (searchedStock && s.ticker === searchedStock.ticker) return true;
      // Otherwise apply momentum filter
      return s.momentum_score >= minMomentum;
    })
    .filter(s => !searchTicker || s.ticker.toLowerCase().includes(searchTicker.toLowerCase()))
    // For Market Pulse: prefer recent items (last 3 hours) - but not for searched stocks
    .filter(s => {
      // Always show searched stock regardless of time
      if (searchedStock && s.ticker === searchedStock.ticker) return true;
      if (viewMode !== 'pulse') return true;
      const ageMinutes = (new Date() - new Date(s.published_at)) / 60000;
      return ageMinutes < 180; // Last 3 hours
    })
    // Sort by momentum score (searched stock on top)
    .sort((a, b) => {
      // Searched stock always first
      if (searchedStock && a.ticker === searchedStock.ticker) return -1;
      if (searchedStock && b.ticker === searchedStock.ticker) return 1;
      return b.momentum_score - a.momentum_score;
    });

  const handleRefreshAll = () => {
    setLastUpdateTime(new Date());
    refetchPulse();
    refetchScanner();
    refetchTrending();
    refetchVwap();
    refetchFda();
    refetchTechCatalyst();
    refetchNews();
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900">
      {/* Header */}
      <header className="bg-slate-900/80 backdrop-blur-sm border-b border-slate-700 sticky top-0 z-20 shadow-xl">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-gradient-to-br from-blue-500 to-purple-600 rounded-lg">
                <Zap size={28} className="text-white" />
              </div>
              <div>
                <h1 className="text-2xl font-bold text-white">Momentum Scanner</h1>
                <p className="text-slate-400 text-sm">Real-time high-momentum opportunities</p>
              </div>
            </div>

            <div className="flex items-center gap-3">
              {/* Language Toggle */}
              <div className="flex bg-slate-800 border border-slate-600 rounded-lg overflow-hidden">
                <button
                  onClick={() => setLanguage('en')}
                  className={`px-3 py-2 text-sm font-semibold transition-all ${
                    language === 'en'
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  EN
                </button>
                <button
                  onClick={() => setLanguage('he')}
                  className={`px-3 py-2 text-sm font-semibold transition-all ${
                    language === 'he'
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  עב
                </button>
              </div>

              {/* Live Mode Toggle */}
              <button
                onClick={() => {
                  setLiveMode(!liveMode);
                  setAutoRefresh(liveMode ? 0 : 5);
                }}
                className={`px-4 py-2 rounded-lg flex items-center gap-2 transition-all font-semibold ${
                  liveMode
                    ? 'bg-red-600 hover:bg-red-700 text-white shadow-lg shadow-red-500/50'
                    : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
                }`}
              >
                {liveMode ? (
                  <>
                    <span className="relative flex h-3 w-3">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-red-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-3 w-3 bg-red-500"></span>
                    </span>
                    LIVE
                  </>
                ) : (
                  <>⏸ Paused</>
                )}
              </button>

              {/* Auto-refresh selector */}
              <select
                value={autoRefresh}
                onChange={(e) => {
                  const val = Number(e.target.value);
                  setAutoRefresh(val);
                  setLiveMode(val > 0 && val <= 10);
                }}
                className="px-3 py-2 bg-slate-800 text-slate-300 border border-slate-600 rounded-lg text-sm focus:outline-none focus:border-blue-500"
              >
                <option value={5}>⚡ Live: 5s</option>
                <option value={10}>🔥 Fast: 10s</option>
                <option value={30}>Refresh: 30s</option>
                <option value={60}>Refresh: 1m</option>
                <option value={120}>Refresh: 2m</option>
                <option value={0}>Manual</option>
              </select>

              <button
                onClick={handleRefreshAll}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg flex items-center gap-2 transition-all shadow-lg hover:shadow-blue-500/50"
              >
                <RefreshCw size={18} />
                Refresh
              </button>
            </div>
          </div>
        </div>
      </header>

      <main className="container mx-auto px-4 py-6">
        {/* Market Status Bar */}
        <MarketStatus lastUpdate={lastUpdateTime} />

        {/* View Mode Toggle */}
        <div className="mb-6 flex items-center gap-4">
          <div className="flex bg-slate-800 border border-slate-700 rounded-lg p-1">
            <button
              onClick={() => setViewMode('pulse')}
              className={`px-4 py-2 rounded-md transition-all ${
                viewMode === 'pulse'
                  ? 'bg-blue-600 text-white shadow-lg'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Market Pulse
            </button>
            <button
              onClick={() => setViewMode('scanner')}
              className={`px-4 py-2 rounded-md transition-all ${
                viewMode === 'scanner'
                  ? 'bg-blue-600 text-white shadow-lg'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Momentum Scanner
            </button>
            <button
              onClick={() => setViewMode('vwap')}
              className={`px-4 py-2 rounded-md transition-all flex items-center gap-2 ${
                viewMode === 'vwap'
                  ? 'bg-yellow-600 text-white shadow-lg'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              📊 {language === 'he' ? 'VWAP מומנטום' : 'VWAP Momentum'}
            </button>
            <button
              onClick={() => setViewMode('trending')}
              className={`px-4 py-2 rounded-md transition-all flex items-center gap-2 ${
                viewMode === 'trending'
                  ? 'bg-purple-600 text-white shadow-lg'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              🔥 {language === 'he' ? 'המניות הכי מדוברות' : 'Most Talked About'}
            </button>
            <button
              onClick={() => setViewMode('fda')}
              className={`px-4 py-2 rounded-md transition-all flex items-center gap-2 ${
                viewMode === 'fda'
                  ? 'bg-green-600 text-white shadow-lg'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              💊 {language === 'he' ? 'FDA קטליסטים' : 'FDA Catalysts'}
            </button>
            <button
              onClick={() => setViewMode('tech-catalyst')}
              className={`px-4 py-2 rounded-md transition-all flex items-center gap-2 ${
                viewMode === 'tech-catalyst'
                  ? 'bg-cyan-600 text-white shadow-lg'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              🖥️ {language === 'he' ? 'קטליסטים טכנולוגיה' : 'Tech Catalysts'}
            </button>
          </div>

          {/* Quick Refresh Button */}
          <button
            onClick={() => {
              setLastUpdateTime(new Date());
              if (viewMode === 'pulse') {
                refetchPulse();
              } else if (viewMode === 'scanner') {
                refetchScanner();
              } else if (viewMode === 'vwap') {
                refetchVwap();
              } else if (viewMode === 'fda') {
                refetchFda();
              } else if (viewMode === 'tech-catalyst') {
                refetchTechCatalyst();
              } else {
                refetchTrending();
              }
            }}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg flex items-center gap-2 transition-all shadow-lg hover:shadow-green-500/50"
          >
            <RefreshCw size={18} />
            <span className="font-semibold">Quick Refresh</span>
          </button>

          <div className="flex-1"></div>

          {/* Search */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-slate-500" size={18} />
            <input
              type="text"
              placeholder="Search ticker..."
              value={searchTicker}
              onChange={(e) => setSearchTicker(e.target.value.toUpperCase())}
              className="pl-10 pr-4 py-2 bg-slate-800 border border-slate-600 text-white rounded-lg focus:outline-none focus:border-blue-500 w-64"
            />
          </div>

          {/* Momentum Filter */}
          <div className="flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-lg px-4 py-2">
            <Filter size={18} className="text-slate-400" />
            <label className="text-slate-400 text-sm">Min Score:</label>
            <select
              value={minMomentum}
              onChange={(e) => setMinMomentum(Number(e.target.value))}
              className="bg-slate-800 text-white text-sm focus:outline-none"
            >
              <option value={0}>All</option>
              <option value={60}>60+</option>
              <option value={70}>70+</option>
              <option value={80}>80+ (Extreme)</option>
            </select>
          </div>
        </div>

        {/* Quick Stats */}
        <QuickStats stocks={filteredStocks} />

        {/* Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Momentum Stocks - 2/3 width */}
          <div className="lg:col-span-2">
            <div className="bg-slate-800/50 backdrop-blur-sm rounded-xl border border-slate-700 shadow-2xl">
              <div className="px-6 py-4 border-b border-slate-700 bg-gradient-to-r from-blue-900/30 to-purple-900/30">
                <div className="flex items-center justify-between">
                  <div>
                    <h2 className="text-xl font-bold text-white flex items-center gap-2">
                      <TrendingUp size={24} />
                      {viewMode === 'pulse' ? 'Market Pulse' :
                       viewMode === 'scanner' ? 'Momentum Scanner' :
                       viewMode === 'vwap' ? 'VWAP Momentum Screener' :
                       viewMode === 'fda' ? (language === 'he' ? 'קטליסטים FDA' : 'FDA Catalyst Calendar') :
                       viewMode === 'tech-catalyst' ? (language === 'he' ? 'קטליסטים טכנולוגיה' : 'Tech Catalyst Calendar') :
                       language === 'he' ? 'המניות הכי מדוברות' : 'Most Talked About Stocks'}
                      {viewMode === 'pulse' && (
                        <span className="text-xs bg-red-500 text-white px-2 py-1 rounded-full animate-pulse">
                          HOT
                        </span>
                      )}
                      {viewMode === 'vwap' && (
                        <span className="text-xs bg-yellow-500 text-black px-2 py-1 rounded-full font-bold">
                          PRO
                        </span>
                      )}
                      {viewMode === 'trending' && (
                        <span className="text-xs bg-purple-500 text-white px-2 py-1 rounded-full animate-pulse">
                          SOCIAL
                        </span>
                      )}
                      {viewMode === 'fda' && (
                        <span className="text-xs bg-green-500 text-white px-2 py-1 rounded-full font-bold">
                          BIO
                        </span>
                      )}
                      {viewMode === 'tech-catalyst' && (
                        <span className="text-xs bg-cyan-500 text-black px-2 py-1 rounded-full font-bold">
                          TECH
                        </span>
                      )}
                    </h2>
                    <p className="text-sm text-slate-400 mt-1">
                      {isLoading || fdaLoading || techCatalystLoading ? 'Loading...' :
                       viewMode === 'trending' ?
                         `${stocks.length} trending stocks from social media` :
                       viewMode === 'fda' ?
                         `${fdaData?.count || 0} FDA catalyst events` :
                       viewMode === 'tech-catalyst' ?
                         `${techCatalystData?.count || 0} tech catalyst events` :
                         `${filteredStocks.length} stocks found`}
                      {viewMode === 'pulse' && !isLoading && (
                        <span className="text-slate-500"> • Last 3 hours only</span>
                      )}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-xs text-slate-500">Live Feed</p>
                    <p className="text-xs text-green-400 flex items-center gap-1 justify-end">
                      <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
                      Active
                    </p>
                  </div>
                </div>
              </div>

              <div className="p-4 max-h-[calc(100vh-300px)] overflow-y-auto">
                {/* Search result card — shows on any tab when ticker is searched */}
                {searchedStock && (
                  <div className="mb-4 rounded-lg border border-blue-500/40 bg-blue-900/20 p-4">
                    <div className="flex items-center justify-between flex-wrap gap-3">
                      <div className="flex items-center gap-3">
                        <span className="text-2xl font-bold text-white">{searchedStock.ticker}</span>
                        {searchedStock.live_data?.price > 0 && (
                          <span className="text-lg text-slate-300 font-mono">${searchedStock.live_data.price.toFixed(2)}</span>
                        )}
                        {searchedStock.live_data?.change_percent != null && (
                          <span className={`text-lg font-bold ${searchedStock.live_data.change_percent > 0 ? 'text-green-400' : searchedStock.live_data.change_percent < 0 ? 'text-red-400' : 'text-slate-400'}`}>
                            {searchedStock.live_data.change_percent > 0 ? '▲' : searchedStock.live_data.change_percent < 0 ? '▼' : '—'} {Math.abs(searchedStock.live_data.change_percent || 0).toFixed(2)}%
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        {searchedStock.live_data?.company_name && (
                          <span className="text-sm text-slate-400">{searchedStock.live_data.company_name}</span>
                        )}
                        {searchedStock.live_data?.sector && searchedStock.live_data.sector !== 'Unknown' && (
                          <span className="text-xs text-slate-500">| {searchedStock.live_data.sector}</span>
                        )}
                        {searchedStock.live_data?.market_cap > 0 && (
                          <span className="px-2 py-0.5 rounded bg-indigo-900/50 border border-indigo-500/30 text-indigo-300 text-xs font-bold">
                            {searchedStock.live_data.market_cap >= 1e12 ? `$${(searchedStock.live_data.market_cap / 1e12).toFixed(1)}T` :
                             searchedStock.live_data.market_cap >= 1e9 ? `$${(searchedStock.live_data.market_cap / 1e9).toFixed(1)}B` :
                             searchedStock.live_data.market_cap >= 1e6 ? `$${(searchedStock.live_data.market_cap / 1e6).toFixed(0)}M` :
                             `$${searchedStock.live_data.market_cap}`}
                          </span>
                        )}
                        <a
                          href={`https://www.tradingview.com/chart/?symbol=${searchedStock.ticker}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white rounded text-xs"
                        >
                          TradingView
                        </a>
                        <a
                          href={`https://finance.yahoo.com/quote/${searchedStock.ticker}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="px-3 py-1 bg-slate-600 hover:bg-slate-500 text-white rounded text-xs"
                        >
                          Yahoo
                        </a>
                      </div>
                    </div>
                    {searchedStock.live_data?.volume > 0 && (
                      <div className="mt-2 flex items-center gap-4 text-xs text-slate-400">
                        <span>Vol: {searchedStock.live_data.volume >= 1e6 ? `${(searchedStock.live_data.volume / 1e6).toFixed(1)}M` : searchedStock.live_data.volume >= 1e3 ? `${(searchedStock.live_data.volume / 1e3).toFixed(0)}K` : searchedStock.live_data.volume}</span>
                        {searchedStock.live_data?.day_high > 0 && <span>H: ${searchedStock.live_data.day_high.toFixed(2)}</span>}
                        {searchedStock.live_data?.day_low > 0 && <span>L: ${searchedStock.live_data.day_low.toFixed(2)}</span>}
                        {searchedStock.live_data?.prev_close > 0 && <span>Prev: ${searchedStock.live_data.prev_close.toFixed(2)}</span>}
                      </div>
                    )}
                  </div>
                )}

                {viewMode === 'fda' ? (
                  <FDACatalystTracker events={fdaData?.events || []} loading={fdaLoading} viewMode="fda" />
                ) : viewMode === 'tech-catalyst' ? (
                  <FDACatalystTracker events={techCatalystData?.events || []} loading={techCatalystLoading} viewMode="tech" />
                ) : viewMode === 'trending' ? (
                  <TrendingStocks stocks={stocks} loading={isLoading} />
                ) : viewMode === 'vwap' ? (
                  <VWAPMomentumScanner stocks={vwapData?.stocks || []} loading={vwapLoading} />
                ) : (
                  <MomentumScannerPro stocks={filteredStocks} loading={isLoading} />
                )}
              </div>
            </div>
          </div>

          {/* News Panel - 1/3 width */}
          <div className="lg:col-span-1">
            <div className="bg-slate-800/50 backdrop-blur-sm rounded-xl border border-slate-700 shadow-2xl sticky top-24">
              <div className="px-6 py-4 border-b border-slate-700 bg-gradient-to-r from-slate-800 to-slate-700">
                <h2 className="text-lg font-bold text-white">Market News</h2>
                <p className="text-sm text-slate-400 mt-1">
                  {newsData?.length || 0} latest articles
                </p>
              </div>

              <div className="p-4 max-h-[calc(100vh-300px)] overflow-y-auto">
                <NewsPanel news={newsData} />
              </div>
            </div>
          </div>
        </div>

        {/* Footer Info */}
        <div className="mt-8 text-center text-slate-500 text-sm">
          <p className="flex items-center justify-center gap-2">
            {liveMode && (
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
              </span>
            )}
            Data updates {autoRefresh > 0 ? `every ${autoRefresh} seconds` : 'manually'}
            {liveMode && <span className="text-green-400 font-semibold">• LIVE MODE ACTIVE</span>}
          </p>
          <p className="mt-1">Showing stocks with momentum score ≥ {minMomentum}</p>
        </div>
      </main>

      <style jsx>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
      `}</style>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <MomentumDashboard />
    </QueryClientProvider>
  );
}
