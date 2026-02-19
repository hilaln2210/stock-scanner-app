import { useState, useEffect } from 'react';
import { ExternalLink, Clock, TrendingUp, TrendingDown, Zap } from 'lucide-react';
import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

function formatTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = Math.floor((now - date) / 1000 / 60);

  if (diff < 60) return `${diff}m ago`;
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
  return date.toLocaleDateString();
}

function formatReactionSpeed(seconds) {
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${minutes}m ${secs}s`;
}

function getMoveStrength(changePct) {
  const abs = Math.abs(changePct);
  if (abs >= 5) return { label: 'Explosive', color: 'text-purple-400', bg: 'bg-purple-900/30' };
  if (abs >= 3) return { label: 'Strong', color: 'text-orange-400', bg: 'bg-orange-900/30' };
  if (abs >= 1) return { label: 'Moderate', color: 'text-yellow-400', bg: 'bg-yellow-900/30' };
  return { label: 'Weak', color: 'text-slate-400', bg: 'bg-slate-900/30' };
}

function MarketReaction({ ticker, publishedAt }) {
  const [reaction, setReaction] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;

    const fetchReaction = async () => {
      try {
        const response = await axios.get(`${API_BASE}/stock/${ticker}?lang=en`);
        if (mounted && response.data && !response.data.error) {
          const liveData = response.data.live_data;
          const changePct = liveData.change_percent || 0;

          // Calculate reaction speed (time from publish to first significant move)
          const publishTime = new Date(publishedAt);
          const now = new Date();
          const reactionSeconds = Math.floor((now - publishTime) / 1000);

          setReaction({
            ticker,
            changePct,
            changeAbs: liveData.change_dollar || 0,
            price: liveData.price || 0,
            reactionSpeed: reactionSeconds,
            volumeRatio: liveData.volume_ratio || 0,
            volumeAnomaly: liveData.volume_anomaly || false
          });
        }
        setLoading(false);
      } catch (error) {
        if (mounted) {
          setLoading(false);
        }
      }
    };

    fetchReaction();
    const interval = setInterval(fetchReaction, 10000); // Update every 10s

    return () => {
      mounted = false;
      clearInterval(interval);
    };
  }, [ticker, publishedAt]);

  if (loading) {
    return (
      <div className="text-xs text-slate-500 italic">
        Loading reaction...
      </div>
    );
  }

  if (!reaction || reaction.price === 0) {
    return (
      <div className="text-xs text-slate-500 italic">
        ⏳ Market reaction pending
      </div>
    );
  }

  const strength = getMoveStrength(reaction.changePct);
  const isPositive = reaction.changePct > 0;

  return (
    <div className={`mt-2 p-2 rounded-lg border ${strength.bg} ${isPositive ? 'border-green-600/30' : 'border-red-600/30'}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-mono text-xs font-bold text-white">{ticker}</span>
          <span className={`text-sm font-bold ${isPositive ? 'text-green-400' : 'text-red-400'}`}>
            {isPositive ? '🟢' : '🔴'} {isPositive ? '+' : ''}{reaction.changePct.toFixed(2)}%
          </span>
          <span className={`px-2 py-0.5 rounded text-xs font-semibold ${strength.color} ${strength.bg} border border-current/20`}>
            {strength.label}
          </span>
        </div>
        {reaction.volumeAnomaly && (
          <span className="text-xs text-orange-400 font-semibold">
            🔥 {reaction.volumeRatio.toFixed(1)}x Vol
          </span>
        )}
      </div>

      <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
        <span className="flex items-center gap-1">
          <Zap size={12} className="text-blue-400" />
          <span className="text-blue-400 font-semibold">Reaction:</span> {formatReactionSpeed(reaction.reactionSpeed)}
        </span>
        <span className="text-slate-600">•</span>
        <span className="font-mono">${reaction.price.toFixed(2)}</span>
        {reaction.changeAbs !== 0 && (
          <>
            <span className="text-slate-600">•</span>
            <span className={isPositive ? 'text-green-400' : 'text-red-400'}>
              {isPositive ? '+' : ''}${reaction.changeAbs.toFixed(2)}
            </span>
          </>
        )}
      </div>
    </div>
  );
}

export default function NewsPanel({ news }) {
  if (!news || news.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        No recent news. News will appear as sources are scraped.
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {news.map((item) => {
        // Extract tickers from the news item
        const tickers = item.tickers ? item.tickers.split(',').map(t => t.trim()).filter(t => t) : [];

        return (
          <div key={item.id} className="bg-slate-800 rounded-lg p-4 border border-slate-700 hover:border-slate-600 transition-colors">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span className="px-2 py-0.5 rounded text-xs font-medium bg-blue-950 text-blue-400">
                    {item.source.toUpperCase()}
                  </span>
                  {tickers.length > 0 && (
                    <span className="font-mono text-sm text-slate-400">
                      {tickers.slice(0, 3).join(', ')}
                    </span>
                  )}
                </div>
                <h3 className="text-white font-medium mb-2 leading-tight">{item.title}</h3>
                {item.summary && (
                  <p className="text-slate-400 text-sm line-clamp-2">{item.summary}</p>
                )}
                <div className="flex items-center gap-4 mt-2">
                  <div className="flex items-center gap-1 text-slate-500 text-xs">
                    <Clock size={14} />
                    <span>{formatTime(item.published_at)}</span>
                  </div>
                  {item.sentiment_score !== 0 && (
                    <span
                      className={`text-xs font-medium ${
                        item.sentiment_score > 0 ? 'text-green-400' : 'text-red-400'
                      }`}
                    >
                      {item.sentiment_score > 0 ? '↑' : '↓'} Sentiment: {Math.abs(item.sentiment_score).toFixed(2)}
                    </span>
                  )}
                </div>

                {/* Market Reactions for all tickers */}
                {tickers.length > 0 && (
                  <div className="mt-3 space-y-2">
                    {tickers.slice(0, 5).map((ticker) => (
                      <MarketReaction
                        key={ticker}
                        ticker={ticker}
                        publishedAt={item.published_at}
                      />
                    ))}
                  </div>
                )}
              </div>
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-400 hover:text-blue-300 transition-colors"
                onClick={(e) => e.stopPropagation()}
              >
                <ExternalLink size={18} />
              </a>
            </div>
          </div>
        );
      })}
    </div>
  );
}
