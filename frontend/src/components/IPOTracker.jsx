import { useQuery } from '@tanstack/react-query';
import { Rocket, TrendingUp, TrendingDown, AlertCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { api } from '../api/client';

export default function IPOTracker() {
  const { t, i18n } = useTranslation();
  const isHebrew = i18n.language === 'he';

  const { data, isLoading } = useQuery({
    queryKey: ['ipos', i18n.language],
    queryFn: () => api.getTodaysIPOs(),
    refetchInterval: 120000, // Every 2 minutes
  });

  const ipos = data?.ipos || [];

  // Helper function to determine IPO status
  const getIpoStatus = (dateStr) => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const ipoDate = new Date(dateStr);
    ipoDate.setHours(0, 0, 0, 0);

    if (ipoDate < today) {
      return { label: t('ipoTracker.completed', 'Completed'), color: 'bg-slate-500/20 text-slate-300' };
    } else if (ipoDate.getTime() === today.getTime()) {
      return { label: t('ipoTracker.today', 'Today'), color: 'bg-green-500/20 text-green-300' };
    } else {
      return { label: t('ipoTracker.upcoming', 'Upcoming'), color: 'bg-blue-500/20 text-blue-300' };
    }
  };

  if (isLoading) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
        <div className="flex items-center gap-2 mb-4">
          <Rocket className="text-purple-400" size={20} />
          <h3 className="text-white font-semibold">{t('ipoTracker.title', 'Upcoming IPOs')}</h3>
        </div>
        <p className="text-slate-400 text-sm">{t('common.loading', 'Loading...')}</p>
      </div>
    );
  }

  if (ipos.length === 0) {
    return (
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4">
        <div className="flex items-center gap-2 mb-4">
          <Rocket className="text-purple-400" size={20} />
          <h3 className="text-white font-semibold">{t('ipoTracker.title', 'Upcoming IPOs')}</h3>
        </div>
        <p className="text-slate-400 text-sm">{t('ipoTracker.noIpos', 'No IPOs scheduled in the next 2 weeks')}</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-800 rounded-lg border border-slate-700">
      <div className="px-4 py-3 border-b border-slate-700 bg-gradient-to-r from-purple-900/30 to-pink-900/30">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Rocket className="text-purple-400" size={20} />
            <h3 className="text-white font-semibold">{t('ipoTracker.title', 'Upcoming IPOs')}</h3>
          </div>
          <span className="px-2 py-1 bg-purple-500/20 text-purple-300 rounded text-xs font-bold">
            {ipos.length} IPO{ipos.length !== 1 ? 's' : ''}
          </span>
        </div>
        <div className="text-xs text-slate-400 mt-1">
          {t('ipoTracker.subtitle', 'Past week • Today • Upcoming week')}
        </div>
      </div>
      <div className="p-3 space-y-3 max-h-96 overflow-y-auto">
        {ipos.map((ipo, idx) => (
          <div
            key={ipo.ticker || idx}
            className="bg-slate-700/50 hover:bg-slate-700 rounded-lg p-4 transition-colors border border-purple-500/20"
          >
            {/* Header */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <span className="font-mono font-bold text-white text-lg">{ipo.ticker}</span>
                  {(() => {
                    const status = getIpoStatus(ipo.date);
                    return (
                      <span className={`px-2 py-0.5 rounded text-xs font-semibold ${status.color}`}>
                        {status.label}
                      </span>
                    );
                  })()}
                  {ipo.actual_price > 0 && ipo.price_vs_expected && (
                    <span
                      className={`text-sm font-semibold ${
                        ipo.price_vs_expected.direction === 'above'
                          ? 'text-green-400'
                          : ipo.price_vs_expected.direction === 'below'
                          ? 'text-red-400'
                          : 'text-yellow-400'
                      }`}
                    >
                      {ipo.price_vs_expected.direction === 'above' && <TrendingUp size={16} className="inline mr-1" />}
                      {ipo.price_vs_expected.direction === 'below' && <TrendingDown size={16} className="inline mr-1" />}
                      {ipo.price_vs_expected.percent > 0 ? '+' : ''}
                      {ipo.price_vs_expected.percent}%
                    </span>
                  )}
                </div>
                <div className="text-sm text-slate-300">
                  {isHebrew && ipo.company_he ? ipo.company_he : ipo.company}
                </div>
                <div className="text-xs text-slate-500 mt-0.5">
                  {ipo.date}
                </div>
              </div>
            </div>

            {/* Pricing Info */}
            <div className="grid grid-cols-2 gap-3 mb-3 p-3 bg-slate-800/50 rounded">
              <div>
                <div className="text-xs text-slate-400 mb-1">Expected Range</div>
                <div className="text-sm text-white font-semibold">
                  ${ipo.expected_low?.toFixed(2)} - ${ipo.expected_high?.toFixed(2)}
                </div>
                <div className="text-xs text-slate-500">
                  Mid: ${ipo.expected_midpoint?.toFixed(2)}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-400 mb-1">
                  {ipo.actual_price > 0 ? 'Actual Price' : 'Status'}
                </div>
                {ipo.actual_price > 0 ? (
                  <div className="text-sm text-green-400 font-bold text-lg">
                    ${ipo.actual_price.toFixed(2)}
                  </div>
                ) : (
                  <div className="text-sm text-yellow-400 font-semibold">
                    Not Yet Priced
                  </div>
                )}
              </div>
            </div>

            {/* What Does This Mean */}
            {ipo.actual_price > 0 && ipo.price_vs_expected && (
              <div className="mb-3 p-3 bg-blue-900/20 border border-blue-500/30 rounded">
                <div className="text-xs text-blue-300 font-semibold mb-1">📊 What does this mean?</div>
                <div className="text-xs text-slate-300">
                  {ipo.price_vs_expected.direction === 'above' && (
                    <>
                      The stock opened <span className="text-green-400 font-bold">${ipo.price_vs_expected.amount.toFixed(2)}</span> above
                      the expected midpoint. This indicates <span className="text-green-400 font-semibold">strong demand</span> from investors.
                    </>
                  )}
                  {ipo.price_vs_expected.direction === 'below' && (
                    <>
                      The stock opened <span className="text-red-400 font-bold">${Math.abs(ipo.price_vs_expected.amount).toFixed(2)}</span> below
                      the expected midpoint. This suggests <span className="text-red-400 font-semibold">weak demand</span> or market skepticism.
                    </>
                  )}
                  {ipo.price_vs_expected.direction === 'at' && (
                    <>The stock opened exactly at the expected midpoint - neutral reception.</>
                  )}
                </div>
              </div>
            )}

            {/* Insights */}
            {((isHebrew && ipo.insights_he) || ipo.insights) && (
              <div className="space-y-1">
                <div className="text-xs text-purple-300 font-semibold mb-2">💡 Insights & Lessons:</div>
                {(isHebrew && ipo.insights_he ? ipo.insights_he : ipo.insights || []).map((insight, i) => (
                  <div key={i} className="text-xs text-slate-300 pl-3 border-l-2 border-purple-500/30">
                    {insight}
                  </div>
                ))}
              </div>
            )}

            {/* Additional Info */}
            <div className="mt-3 pt-3 border-t border-slate-600/50 flex items-center justify-between text-xs">
              <span className="text-slate-400">
                Shares: <span className="text-white">{ipo.shares}</span>
              </span>
              <span className="text-slate-500">
                Source: {ipo.source}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
