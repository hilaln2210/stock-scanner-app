import { useState, useEffect, useRef } from 'react';
import { useQuery, QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { api } from './api/client';
import StatsCards from './components/StatsCards';
import SignalsTable from './components/SignalsTable';
import NewsPanel from './components/NewsPanel';
import FilterPanel from './components/FilterPanel';
import TopMovers from './components/TopMovers';
import SearchHistory from './components/SearchHistory';
import IPOTracker from './components/IPOTracker';
import { RefreshCw, Activity, Bell, BellOff, Languages } from 'lucide-react';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

function Dashboard() {
  const { t, i18n } = useTranslation();
  const [filters, setFilters] = useState({
    ticker: '',
    minScore: 0,
    stance: '',
    autoRefresh: 600, // 10 minutes default
  });
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [notificationsEnabled, setNotificationsEnabled] = useState(false);
  const [toasts, setToasts] = useState([]);
  const seenSignals = useRef(new Set());

  // RTL support for Hebrew
  const isRTL = i18n.language === 'he';
  useEffect(() => {
    document.dir = isRTL ? 'rtl' : 'ltr';
  }, [isRTL]);

  const toggleLanguage = () => {
    i18n.changeLanguage(i18n.language === 'en' ? 'he' : 'en');
  };

  // Track search history
  useEffect(() => {
    if (filters.ticker && window.addToSearchHistory) {
      window.addToSearchHistory(filters.ticker);
    }
  }, [filters.ticker]);

  const handleSelectTickerFromHistory = (ticker) => {
    setFilters((prev) => ({ ...prev, ticker }));
  };

  // Request notification permission on mount
  useEffect(() => {
    if ('Notification' in window && Notification.permission === 'granted') {
      setNotificationsEnabled(true);
    }
  }, []);

  const requestNotificationPermission = async () => {
    if (!('Notification' in window)) {
      alert('This browser does not support notifications');
      return;
    }

    const permission = await Notification.requestPermission();
    setNotificationsEnabled(permission === 'granted');
  };

  // Fetch stats
  const { data: stats } = useQuery({
    queryKey: ['stats'],
    queryFn: api.getDashboardStats,
    refetchInterval: filters.autoRefresh * 1000 || false,
  });

  // Fetch signals
  const { data: signals, refetch: refetchSignals, isLoading: signalsLoading } = useQuery({
    queryKey: ['signals', filters.ticker, filters.minScore, filters.stance],
    queryFn: () =>
      api.getSignals({
        ticker: filters.ticker || undefined,
        min_score: filters.minScore,
        stance: filters.stance || undefined,
        limit: 100,
      }),
    refetchInterval: filters.autoRefresh * 1000 || false,
  });

  // Fetch news
  const { data: news, refetch: refetchNews } = useQuery({
    queryKey: ['news', filters.ticker],
    queryFn: () =>
      api.getNews({
        ticker: filters.ticker || undefined,
        hours: 48,
        limit: 50,
      }),
    refetchInterval: filters.autoRefresh * 1000 || false,
  });

  // Notification system for new high-priority signals
  useEffect(() => {
    if (!signals || signals.length === 0) return;

    signals.forEach((signal) => {
      // Only notify for high-scoring signals that we haven't seen before
      if (signal.score >= 75 && !seenSignals.current.has(signal.id)) {
        seenSignals.current.add(signal.id);

        // Show toast
        showToast(signal);

        // Show browser notification if enabled
        if (notificationsEnabled) {
          showBrowserNotification(signal);
        }
      }
    });
  }, [signals, notificationsEnabled]);

  const showToast = (signal) => {
    const toast = {
      id: Date.now(),
      signal,
    };

    setToasts((prev) => [...prev, toast]);

    // Auto-remove after 10 seconds
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== toast.id));
    }, 10000);
  };

  const showBrowserNotification = (signal) => {
    const title = `🚨 ${signal.ticker} Signal - Score: ${Math.round(signal.score)}`;
    const options = {
      body: signal.reason,
      icon: '/favicon.ico',
      badge: '/favicon.ico',
      tag: signal.id,
      requireInteraction: false,
    };

    new Notification(title, options);
  };

  const removeToast = (id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  };

  // Manual refresh
  const handleRefresh = () => {
    refetchSignals();
    refetchNews();
  };

  // Trigger scrape
  const handleTriggerScrape = async () => {
    try {
      await api.triggerScrape();
      setTimeout(() => {
        refetchSignals();
        refetchNews();
      }, 2000);
    } catch (error) {
      console.error('Scrape failed:', error);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900">
      {/* Header */}
      <header className="bg-slate-800 border-b border-slate-700 sticky top-0 z-10">
        <div className="container mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <Activity size={32} className="text-blue-400" />
              <div>
                <h1 className="text-2xl font-bold text-white">{t('app.title')}</h1>
                <p className="text-slate-400 text-sm">{t('app.subtitle')}</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <SearchHistory onSelectTicker={handleSelectTickerFromHistory} />
              <button
                onClick={toggleLanguage}
                className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded flex items-center gap-2 transition-colors"
                title="Toggle Language"
              >
                <Languages size={18} />
                {i18n.language === 'en' ? 'עב' : 'EN'}
              </button>
              <button
                onClick={notificationsEnabled ? () => setNotificationsEnabled(false) : requestNotificationPermission}
                className={`px-4 py-2 rounded flex items-center gap-2 transition-colors ${
                  notificationsEnabled
                    ? 'bg-green-600 hover:bg-green-700 text-white'
                    : 'bg-slate-700 hover:bg-slate-600 text-slate-300'
                }`}
                title={t(notificationsEnabled ? 'button.notificationsOn' : 'button.enableAlerts')}
              >
                {notificationsEnabled ? <Bell size={18} /> : <BellOff size={18} />}
                {t(notificationsEnabled ? 'button.notificationsOn' : 'button.enableAlerts')}
              </button>
              <button
                onClick={handleTriggerScrape}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded flex items-center gap-2 transition-colors"
              >
                <RefreshCw size={18} />
                {t('button.triggerScrape')}
              </button>
              <button
                onClick={handleRefresh}
                className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded flex items-center gap-2 transition-colors"
              >
                <RefreshCw size={18} />
                {t('button.refresh')}
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-6">
        {/* Stats */}
        <StatsCards stats={stats} />

        {/* Filters */}
        <FilterPanel filters={filters} onFilterChange={setFilters} />

        {/* Content Grid */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Signals Table (2/3) */}
          <div className="lg:col-span-2 space-y-6">
            <div className="bg-slate-800 rounded-lg border border-slate-700">
              <div className="px-4 py-3 border-b border-slate-700">
                <h2 className="text-lg font-semibold text-white">{t('signals.title')}</h2>
                <p className="text-sm text-slate-400">
                  {signalsLoading ? t('signals.loading') : `${signals?.length || 0} ${t('signals.found')}`}
                </p>
              </div>
              <div className="overflow-auto max-h-[calc(100vh-400px)]">
                <SignalsTable
                  signals={signals}
                  selectedSignal={selectedSignal}
                  onSelectSignal={setSelectedSignal}
                />
              </div>
            </div>
          </div>

          {/* Right Column: IPOs + Top Movers + News (1/3) */}
          <div className="lg:col-span-1 space-y-6">
            {/* IPO Tracker */}
            <IPOTracker />

            {/* Top Movers Widget */}
            <TopMovers />

            {/* News Panel */}
            <div className="bg-slate-800 rounded-lg border border-slate-700">
              <div className="px-4 py-3 border-b border-slate-700">
                <h2 className="text-lg font-semibold text-white">{t('news.title')}</h2>
                <p className="text-sm text-slate-400">{news?.length || 0} {t('news.articles')}</p>
              </div>
              <div className="p-4 overflow-auto max-h-[calc(100vh-500px)]">
                <NewsPanel news={news} />
              </div>
            </div>
          </div>
        </div>

        {/* Selected Signal Detail */}
        {selectedSignal && (
          <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center p-4 z-50">
            <div className="bg-slate-800 rounded-lg border border-slate-700 max-w-2xl w-full max-h-[80vh] overflow-auto">
              <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
                <h2 className="text-xl font-bold text-white">{selectedSignal.ticker} Signal</h2>
                <button
                  onClick={() => setSelectedSignal(null)}
                  className="text-slate-400 hover:text-white transition-colors"
                >
                  ✕
                </button>
              </div>
              <div className="px-6 py-4 space-y-4">
                <div>
                  <label className="text-slate-400 text-sm">{t('signals.signalType')}</label>
                  <p className="text-white font-medium">
                    {selectedSignal.signal_type.replace(/_/g, ' ').toUpperCase()}
                  </p>
                </div>
                <div>
                  <label className="text-slate-400 text-sm">{t('signals.score')}</label>
                  <p className="text-white font-bold text-2xl">{Math.round(selectedSignal.score)}</p>
                </div>
                <div>
                  <label className="text-slate-400 text-sm">{t('signals.stance')}</label>
                  <p className={`font-semibold ${
                    selectedSignal.stance === 'Bullish' ? 'text-green-400' :
                    selectedSignal.stance === 'Bearish' ? 'text-red-400' :
                    'text-yellow-400'
                  }`}>
                    {selectedSignal.stance}
                  </p>
                </div>
                <div>
                  <label className="text-slate-400 text-sm">{t('signals.reason')}</label>
                  <p className="text-white leading-relaxed">{selectedSignal.reason}</p>
                </div>
                <div>
                  <label className="text-slate-400 text-sm">{t('signals.time')}</label>
                  <p className="text-white">{new Date(selectedSignal.event_time).toLocaleString()}</p>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Toast Notifications */}
        <div className="fixed bottom-4 right-4 space-y-3 z-50">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className="bg-gradient-to-r from-blue-600 to-purple-600 text-white rounded-lg shadow-2xl p-4 max-w-sm animate-slide-in border-2 border-white"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-bold text-lg">{toast.signal.ticker}</span>
                    <span className="px-2 py-0.5 bg-white text-blue-600 rounded text-sm font-bold">
                      {Math.round(toast.signal.score)}
                    </span>
                    <span className={`text-sm ${
                      toast.signal.stance === 'Bullish' ? 'text-green-200' :
                      toast.signal.stance === 'Bearish' ? 'text-red-200' :
                      'text-yellow-200'
                    }`}>
                      {toast.signal.stance}
                    </span>
                  </div>
                  <p className="text-sm text-white/90">{toast.signal.reason}</p>
                  <button
                    onClick={() => {
                      setSelectedSignal(toast.signal);
                      removeToast(toast.id);
                    }}
                    className="mt-2 text-xs text-white/80 hover:text-white underline"
                  >
                    {t('modal.viewDetails')}
                  </button>
                </div>
                <button
                  onClick={() => removeToast(toast.id)}
                  className="text-white/70 hover:text-white transition-colors"
                >
                  ✕
                </button>
              </div>
            </div>
          ))}
        </div>
      </main>

      <style jsx>{`
        @keyframes slide-in {
          from {
            transform: translateX(400px);
            opacity: 0;
          }
          to {
            transform: translateX(0);
            opacity: 1;
          }
        }
        .animate-slide-in {
          animation: slide-in 0.3s ease-out;
        }
      `}</style>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Dashboard />
    </QueryClientProvider>
  );
}
