import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { TrendingUp, Activity, BarChart3 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';
import ChartModal from './ChartModal';

export default function TopMovers() {
  const { t, i18n } = useTranslation();
  const [selectedTicker, setSelectedTicker] = useState(null);
  const isHebrew = i18n.language === 'he';

  const { data, isLoading } = useQuery({
    queryKey: ['topMovers', i18n.language],
    queryFn: () => api.getTopMovers({ limit: 10 }),
    refetchInterval: 60000, // Every minute
  });

  const movers = data?.movers || [];

  if (isLoading) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="text-green-400" size={20} />
          <h3 className="text-white font-semibold">{t('movers.title')}</h3>
        </div>
        <p className="text-slate-400 text-sm">{t('signals.loading')}</p>
      </div>
    );
  }

  if (movers.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
        <div className="flex items-center gap-2 mb-4">
          <TrendingUp className="text-green-400" size={20} />
          <h3 className="text-white font-semibold">{t('movers.title')}</h3>
        </div>
        <p className="text-slate-400 text-sm">No data available. Add ALPHA_VANTAGE_API_KEY to .env</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700">
      <div className="px-4 py-3 border-b border-slate-700 bg-gradient-to-r from-green-900/30 to-emerald-900/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <TrendingUp className="text-green-400" size={20} />
            <h3 className="text-white font-semibold">{t('movers.title')}</h3>
          </div>
          <Activity className="text-green-400 animate-pulse" size={18} />
        </div>
      </div>
      <div className="p-3 space-y-2 max-h-96 overflow-y-auto">
        {movers.map((mover, idx) => (
          <div
            key={mover.ticker}
            className="bg-slate-700/50 hover:bg-slate-700 rounded-lg p-3 transition-colors cursor-pointer border border-green-500/20"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="px-1.5 py-0.5 bg-slate-600 text-white rounded text-xs font-bold">
                    #{idx + 1}
                  </span>
                  <span className="font-mono font-bold text-white text-lg">{mover.ticker}</span>
                  <span className="text-green-400 font-bold text-lg">
                    +{mover.change_percent.toFixed(2)}%
                  </span>
                </div>
                {(mover.name || mover.name_he) && (
                  <div className="text-xs text-slate-300 mb-1">
                    {isHebrew && mover.name_he ? mover.name_he : mover.name}
                  </div>
                )}
                {(mover.reason || mover.reason_he) && (
                  <div className="text-xs text-blue-300 mb-2 italic">
                    💡 {isHebrew && mover.reason_he ? mover.reason_he : mover.reason}
                  </div>
                )}
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-slate-400">{t('movers.price')}: </span>
                    <span className="text-white font-semibold">${mover.price.toFixed(2)}</span>
                  </div>
                  <div>
                    <span className="text-slate-400">{t('movers.volume')}: </span>
                    <span className="text-white font-semibold">
                      {(mover.volume / 1000000).toFixed(1)}M
                    </span>
                  </div>
                </div>
                {mover.market_cap && mover.market_cap > 0 && (
                  <div className="text-xs text-slate-400 mt-1">
                    Market Cap: ${(mover.market_cap / 1000000000).toFixed(1)}B
                  </div>
                )}
              </div>
              <div className="text-right flex flex-col gap-2">
                <div className="w-12 h-12 rounded-full bg-green-500/20 flex items-center justify-center">
                  <TrendingUp className="text-green-400" size={24} />
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedTicker(mover.ticker);
                  }}
                  className="px-2 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs flex items-center gap-1 transition-colors"
                  title="View Chart"
                >
                  <BarChart3 size={14} />
                  Chart
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Chart Modal */}
      {selectedTicker && (
        <ChartModal
          ticker={selectedTicker}
          onClose={() => setSelectedTicker(null)}
        />
      )}
    </div>
  );
}
