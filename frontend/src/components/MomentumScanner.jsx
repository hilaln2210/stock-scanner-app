import { useState, useEffect } from 'react';
import { TrendingUp, Zap, DollarSign, Clock, ExternalLink } from 'lucide-react';

export default function MomentumScanner({ stocks, loading }) {
  const [selectedStock, setSelectedStock] = useState(null);
  const [priceFlash, setPriceFlash] = useState({});

  // Track price changes for flash animation
  useEffect(() => {
    stocks.forEach(stock => {
      if (stock.live_data && stock.live_data.price) {
        const key = stock.ticker;
        setPriceFlash(prev => ({
          ...prev,
          [key]: true
        }));
        setTimeout(() => {
          setPriceFlash(prev => ({
            ...prev,
            [key]: false
          }));
        }, 1000);
      }
    });
  }, [stocks]);

  const getSectorEmoji = (sector) => {
    const sectorEmojis = {
      'Technology': '💻',
      'Healthcare': '🏥',
      'Financial Services': '🏦',
      'Consumer Cyclical': '🛍️',
      'Communication Services': '📡',
      'Industrials': '🏭',
      'Consumer Defensive': '🍔',
      'Energy': '⚡',
      'Utilities': '💡',
      'Real Estate': '🏢',
      'Basic Materials': '⚒️',
      'Financial': '💰',
      'Finance': '💰',
      'Consumer Discretionary': '🛒',
      'Materials': '🔩',
      'Telecommunications': '📞',
    };
    return sectorEmojis[sector] || '🏢';
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
      </div>
    );
  }

  if (!stocks || stocks.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        <Zap size={48} className="mx-auto mb-4 opacity-50" />
        <p>No high-momentum stocks found</p>
        <p className="text-sm mt-2">Try refreshing or check back later</p>
      </div>
    );
  }

  const getMomentumColor = (score) => {
    if (score >= 80) return 'text-green-400 bg-green-900/30 border-green-500';
    if (score >= 65) return 'text-yellow-400 bg-yellow-900/30 border-yellow-500';
    return 'text-blue-400 bg-blue-900/30 border-blue-500';
  };

  const getMomentumLabel = (score) => {
    if (score >= 80) return 'EXTREME';
    if (score >= 65) return 'HIGH';
    return 'MODERATE';
  };

  const getPriceChangeColor = (change) => {
    if (change > 0) return 'text-green-400';
    if (change < 0) return 'text-red-400';
    return 'text-slate-400';
  };

  return (
    <div className="space-y-3">
      {stocks.map((stock, idx) => (
        <div
          key={`${stock.ticker}-${idx}`}
          className="bg-slate-800 border border-slate-700 rounded-lg p-4 hover:border-blue-500 transition-all cursor-pointer group"
          onClick={() => setSelectedStock(stock)}
        >
          <div className="flex items-start justify-between gap-4">
            {/* Left: Ticker and Info */}
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-2">
                <div className="flex flex-col gap-1">
                  {/* Ticker and Price on same line */}
                  <div className="flex items-center gap-3">
                    <span className="text-2xl font-bold text-white">{stock.ticker}</span>
                    {stock.live_data && stock.live_data.price > 0 && (
                      <div className="flex items-center gap-2">
                        <span
                          className={`text-2xl font-bold transition-all duration-300 ${
                            priceFlash[stock.ticker] ? 'scale-110 text-yellow-400' : 'text-green-400'
                          }`}
                        >
                          ${stock.live_data.price.toFixed(2)}
                        </span>
                        {stock.live_data.change_percent !== 0 && (
                          <span className={`text-lg font-bold ${getPriceChangeColor(stock.live_data.change_percent)}`}>
                            {stock.live_data.change_percent > 0 ? '+' : ''}{stock.live_data.change_percent.toFixed(2)}%
                          </span>
                        )}
                        {stock.live_data.volume_anomaly && (
                          <span className="px-2 py-1 bg-orange-500 text-white rounded text-xs font-bold animate-pulse">
                            🔥 HIGH VOL
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  {/* Company Name & Sector */}
                  {stock.live_data && stock.live_data.company_name && (
                    <div className="flex items-center gap-2 text-xs text-slate-400">
                      {stock.live_data.sector && stock.live_data.sector !== 'Unknown' && (
                        <span className="text-base">{getSectorEmoji(stock.live_data.sector)}</span>
                      )}
                      <span>{stock.live_data.company_name}</span>
                    </div>
                  )}
                </div>

                {/* Momentum Badge */}
                <div className={`px-3 py-1 rounded-full border ${getMomentumColor(stock.momentum_score)} text-xs font-bold`}>
                  <div className="flex items-center gap-1">
                    <Zap size={12} />
                    {getMomentumLabel(stock.momentum_score)}
                  </div>
                </div>
              </div>

              {/* Title */}
              <p className="text-slate-200 text-sm leading-relaxed mb-2 group-hover:text-white transition-colors">
                {stock.title}
              </p>

              {/* Business Summary */}
              {stock.live_data && stock.live_data.business_summary && (
                <p className="text-slate-400 text-xs leading-relaxed mb-2 italic">
                  {stock.live_data.business_summary}
                </p>
              )}

              {/* Time */}
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <Clock size={12} />
                <span>{new Date(stock.published_at).toLocaleTimeString('en-US', {
                  hour: '2-digit',
                  minute: '2-digit',
                  hour12: true
                })}</span>
                <span className="text-slate-600">•</span>
                <span className="text-slate-600">
                  {(() => {
                    const mins = Math.floor((new Date() - new Date(stock.published_at)) / 60000);
                    if (mins < 1) return 'Just now';
                    if (mins < 60) return `${mins}m ago`;
                    const hours = Math.floor(mins / 60);
                    return `${hours}h ago`;
                  })()}
                </span>
              </div>
            </div>

            {/* Right: Score */}
            <div className="flex flex-col items-center">
              <div className="relative">
                <svg className="transform -rotate-90 w-20 h-20">
                  <circle
                    cx="40"
                    cy="40"
                    r="32"
                    stroke="currentColor"
                    strokeWidth="6"
                    fill="transparent"
                    className="text-slate-700"
                  />
                  <circle
                    cx="40"
                    cy="40"
                    r="32"
                    stroke="currentColor"
                    strokeWidth="6"
                    fill="transparent"
                    strokeDasharray={`${2 * Math.PI * 32}`}
                    strokeDashoffset={`${2 * Math.PI * 32 * (1 - stock.momentum_score / 100)}`}
                    className={stock.momentum_score >= 80 ? 'text-green-400' :
                              stock.momentum_score >= 65 ? 'text-yellow-400' : 'text-blue-400'}
                  />
                </svg>
                <div className="absolute inset-0 flex items-center justify-center">
                  <span className="text-xl font-bold text-white">{stock.momentum_score}</span>
                </div>
              </div>
              <p className="text-xs text-slate-500 mt-1">Momentum</p>
            </div>
          </div>

          {/* Read More Link */}
          {stock.url && (
            <a
              href={stock.url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 mt-3 text-xs text-blue-400 hover:text-blue-300 transition-colors"
              onClick={(e) => e.stopPropagation()}
            >
              <ExternalLink size={12} />
              Read Full Article
            </a>
          )}
        </div>
      ))}

      {/* Stock Detail Modal */}
      {selectedStock && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50" onClick={() => setSelectedStock(null)}>
          <div className="bg-slate-800 rounded-lg border border-slate-600 max-w-2xl w-full max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
            <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between bg-gradient-to-r from-blue-900/50 to-purple-900/50">
              <div className="flex items-center gap-3">
                <h2 className="text-2xl font-bold text-white">{selectedStock.ticker}</h2>
                {selectedStock.price_change !== 0 && (
                  <span className={`text-xl font-bold ${getPriceChangeColor(selectedStock.price_change)}`}>
                    {selectedStock.price_change > 0 ? '+' : ''}{selectedStock.price_change.toFixed(2)}%
                  </span>
                )}
              </div>
              <button onClick={() => setSelectedStock(null)} className="text-slate-400 hover:text-white text-2xl">✕</button>
            </div>

            <div className="px-6 py-4 space-y-4">
              {/* Company Info */}
              {selectedStock.live_data && selectedStock.live_data.company_name && (
                <div>
                  <label className="text-slate-400 text-sm font-semibold">Company</label>
                  <div className="flex items-center gap-2 mt-1">
                    {selectedStock.live_data.sector && selectedStock.live_data.sector !== 'Unknown' && (
                      <span className="text-2xl">{getSectorEmoji(selectedStock.live_data.sector)}</span>
                    )}
                    <div>
                      <p className="text-white text-lg font-bold">{selectedStock.live_data.company_name}</p>
                      {selectedStock.live_data.sector && selectedStock.live_data.sector !== 'Unknown' && (
                        <p className="text-slate-400 text-sm">{selectedStock.live_data.sector} • {selectedStock.live_data.industry || 'N/A'}</p>
                      )}
                    </div>
                  </div>
                  {selectedStock.live_data.business_summary && (
                    <p className="text-slate-300 text-sm leading-relaxed mt-2">
                      {selectedStock.live_data.business_summary}
                    </p>
                  )}
                </div>
              )}

              {/* Live Price */}
              {selectedStock.live_data && selectedStock.live_data.price > 0 && (
                <div>
                  <label className="text-slate-400 text-sm font-semibold">Current Price</label>
                  <div className="flex items-center gap-3 mt-1">
                    <span className="text-3xl font-bold text-white">${selectedStock.live_data.price.toFixed(2)}</span>
                    {selectedStock.live_data.change_percent !== 0 && (
                      <span className={`text-xl font-bold ${getPriceChangeColor(selectedStock.live_data.change_percent)}`}>
                        {selectedStock.live_data.change_percent > 0 ? '+' : ''}{selectedStock.live_data.change_percent.toFixed(2)}%
                      </span>
                    )}
                  </div>
                  {selectedStock.live_data.volume_anomaly && (
                    <div className="flex items-center gap-2 mt-2">
                      <span className="px-3 py-1 bg-orange-500 text-white rounded-lg text-sm font-bold">
                        🔥 Unusual Volume Detected
                      </span>
                      <span className="text-slate-400 text-sm">
                        {selectedStock.live_data.volume_ratio}x average
                      </span>
                    </div>
                  )}
                </div>
              )}

              <div>
                <label className="text-slate-400 text-sm font-semibold">Momentum Score</label>
                <div className="flex items-center gap-3 mt-1">
                  <div className="text-4xl font-bold text-white">{selectedStock.momentum_score}</div>
                  <div className={`px-3 py-1 rounded-full border ${getMomentumColor(selectedStock.momentum_score)} text-sm font-bold`}>
                    {getMomentumLabel(selectedStock.momentum_score)}
                  </div>
                </div>
              </div>

              <div>
                <label className="text-slate-400 text-sm font-semibold">Headline</label>
                <p className="text-white text-lg leading-relaxed mt-1">{selectedStock.title}</p>
              </div>

              <div>
                <label className="text-slate-400 text-sm font-semibold">Time</label>
                <p className="text-white mt-1">{new Date(selectedStock.published_at).toLocaleString()}</p>
              </div>

              {selectedStock.url && (
                <a
                  href={selectedStock.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition-colors"
                >
                  <ExternalLink size={16} />
                  Read Full Article
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
