import { MessageCircle, TrendingUp, TrendingDown, ExternalLink, Users } from 'lucide-react';

function getMentionBadge(mentions) {
  if (mentions >= 100) return { label: 'VIRAL', color: 'text-purple-400', bg: 'bg-purple-900/30', border: 'border-purple-600/30' };
  if (mentions >= 50) return { label: 'HOT', color: 'text-red-400', bg: 'bg-red-900/30', border: 'border-red-600/30' };
  if (mentions >= 20) return { label: 'Trending', color: 'text-orange-400', bg: 'bg-orange-900/30', border: 'border-orange-600/30' };
  return { label: 'Rising', color: 'text-yellow-400', bg: 'bg-yellow-900/30', border: 'border-yellow-600/30' };
}

function getSentimentIcon(sentiment) {
  if (sentiment > 0.3) return { icon: '🚀', text: 'Very Bullish', color: 'text-green-400' };
  if (sentiment > 0) return { icon: '📈', text: 'Bullish', color: 'text-green-400' };
  if (sentiment < -0.3) return { icon: '📉', text: 'Very Bearish', color: 'text-red-400' };
  if (sentiment < 0) return { icon: '⬇️', text: 'Bearish', color: 'text-red-400' };
  return { icon: '➡️', text: 'Neutral', color: 'text-slate-400' };
}

function SourceBadge({ source, count }) {
  const sourceIcons = {
    reddit: '🔴',
    twitter: '🐦',
    telegram: '✈️',
    stocktwits: '📊',
    discord: '💬'
  };

  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs bg-slate-700/50 text-slate-300 border border-slate-600/50">
      {sourceIcons[source.toLowerCase()] || '📱'} {source}: {count}
    </span>
  );
}

export default function TrendingStocks({ stocks, loading }) {
  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-4 border-blue-500 border-t-transparent mx-auto mb-4"></div>
          <p className="text-slate-400">Searching social media...</p>
        </div>
      </div>
    );
  }

  if (!stocks || stocks.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        <MessageCircle size={48} className="mx-auto mb-4 opacity-50" />
        <p>No trending stocks found</p>
        <p className="text-sm mt-2 text-slate-500">Check back soon for hot discussions</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {stocks.map((stock, idx) => {
        const badge = getMentionBadge(stock.mention_count || 0);
        const sentiment = getSentimentIcon(stock.sentiment_score || 0);
        const isClimbing = stock.live_data?.change_percent > 2;
        const isDropping = stock.live_data?.change_percent < -2;

        return (
          <div
            key={stock.ticker || idx}
            className={`bg-slate-800/80 rounded-lg p-4 border transition-all hover:border-blue-500/50 ${
              isClimbing
                ? 'border-green-600/40 bg-green-900/10'
                : isDropping
                  ? 'border-red-600/40 bg-red-900/10'
                  : 'border-slate-700'
            }`}
          >
            {/* Header Row */}
            <div className="flex items-start justify-between mb-3">
              <div className="flex items-center gap-3">
                <div className="flex flex-col">
                  <span className="text-2xl font-bold text-white">{stock.ticker}</span>
                  {stock.live_data && (
                    <span className="text-lg font-mono text-slate-300">
                      ${stock.live_data.price?.toFixed(2) || '0.00'}
                    </span>
                  )}
                </div>

                {/* Price Movement Indicator */}
                {stock.live_data && stock.live_data.price > 0 && (
                  <div className="flex flex-col items-start">
                    <span className={`text-lg font-bold flex items-center gap-1 ${
                      stock.live_data.change_percent > 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {stock.live_data.change_percent > 0 ? <TrendingUp size={18} /> : <TrendingDown size={18} />}
                      {stock.live_data.change_percent > 0 ? '+' : ''}
                      {stock.live_data.change_percent?.toFixed(2)}%
                    </span>
                    {(isClimbing || isDropping) && (
                      <span className={`text-xs font-semibold ${isClimbing ? 'text-green-400' : 'text-red-400'}`}>
                        {isClimbing ? '🚀 Climbing!' : '⬇️ Dropping'}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Mention Badge */}
              <div className={`px-3 py-1 rounded-lg border ${badge.bg} ${badge.border}`}>
                <span className={`text-sm font-bold ${badge.color}`}>{badge.label}</span>
              </div>
            </div>

            {/* Company Name */}
            {stock.live_data?.company_name && (
              <p className="text-slate-400 text-sm mb-2">{stock.live_data.company_name}</p>
            )}

            {/* Mentions and Sentiment Row */}
            <div className="flex items-center gap-4 mb-3">
              <div className="flex items-center gap-2">
                <Users size={16} className="text-blue-400" />
                <span className="text-white font-bold">{stock.mention_count || 0}</span>
                <span className="text-slate-400 text-sm">mentions</span>
              </div>

              <span className="text-slate-600">•</span>

              <div className="flex items-center gap-2">
                <span className="text-lg">{sentiment.icon}</span>
                <span className={`text-sm font-semibold ${sentiment.color}`}>
                  {sentiment.text}
                </span>
              </div>

              {stock.live_data?.volume_anomaly && (
                <>
                  <span className="text-slate-600">•</span>
                  <span className="text-xs text-orange-400 font-semibold">
                    🔥 {stock.live_data.volume_ratio?.toFixed(1)}x Vol
                  </span>
                </>
              )}
            </div>

            {/* Source Breakdown */}
            {stock.sources && Object.keys(stock.sources).length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {Object.entries(stock.sources).map(([source, count]) => (
                  <SourceBadge key={source} source={source} count={count} />
                ))}
              </div>
            )}

            {/* Top Mentions/Snippets */}
            {stock.top_snippets && stock.top_snippets.length > 0 && (
              <div className="space-y-2">
                {stock.top_snippets.slice(0, 2).map((snippet, i) => (
                  <div key={i} className="bg-slate-900/50 rounded p-2 border border-slate-700/50">
                    <p className="text-slate-300 text-sm italic">"{snippet.text}"</p>
                    <div className="flex items-center justify-between mt-1">
                      <span className="text-xs text-slate-500">
                        {snippet.source} • {snippet.author || 'Anonymous'}
                      </span>
                      {snippet.url && (
                        <a
                          href={snippet.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-400 hover:text-blue-300 text-xs flex items-center gap-1"
                        >
                          <ExternalLink size={12} />
                          View
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Sector/Industry */}
            {stock.live_data?.sector && (
              <div className="mt-3 pt-3 border-t border-slate-700/50">
                <div className="flex items-center gap-3 text-xs text-slate-400">
                  <span>{stock.live_data.sector}</span>
                  {stock.live_data.industry && (
                    <>
                      <span className="text-slate-600">•</span>
                      <span>{stock.live_data.industry}</span>
                    </>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
