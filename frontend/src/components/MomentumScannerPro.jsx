import { useState } from 'react';
import { Zap, BarChart3, Newspaper, Activity, Target, X } from 'lucide-react';

// ─── Helpers ─────────────────────────────────────────────

const pct = (v) => v?.toFixed(2) ?? '0.00';
const abs_pct = (v) => Math.abs(v ?? 0).toFixed(2);

const changeColor = (v) =>
  v > 0 ? 'text-green-400' : v < 0 ? 'text-red-400' : 'text-slate-400';

const changeBg = (v) =>
  v > 0 ? 'bg-green-900/30 border-green-500/40' : v < 0 ? 'bg-red-900/30 border-red-500/40' : 'bg-slate-800 border-slate-600';

const arrow = (v) => (v > 0 ? '▲' : v < 0 ? '▼' : '—');

const accelLabel = (a) => {
  if (a === 'increasing') return { text: 'Accelerating ↗', color: 'text-green-400', icon: '🚀' };
  if (a === 'decreasing') return { text: 'Decelerating ↘', color: 'text-orange-400', icon: '⚠️' };
  return { text: 'Steady →', color: 'text-slate-400', icon: '➡️' };
};

const triggerLabel = (t) => {
  const map = {
    'volume_spike': '📊 Volume Spike',
    'break_of_high': '🔺 Break of HOD',
    'reversal': '🔄 Reversal',
    'momentum': '⚡ Momentum',
    'none': '',
  };
  return map[t] || t;
};

const confidenceCalc = (move, momentum_score) => {
  let score = 0;

  // Short-term movement strength
  if (Math.abs(move?.change_5m ?? 0) >= 3) score += 25;
  else if (Math.abs(move?.change_5m ?? 0) >= 1.5) score += 15;
  else if (Math.abs(move?.change_5m ?? 0) >= 0.5) score += 8;

  // Acceleration
  if (move?.acceleration === 'increasing') score += 20;
  else if (move?.acceleration === 'steady') score += 5;

  // Volume
  if ((move?.rel_volume ?? 0) >= 3) score += 20;
  else if ((move?.rel_volume ?? 0) >= 2) score += 12;
  else if ((move?.rel_volume ?? 0) >= 1.5) score += 5;

  // Momentum score
  if (momentum_score >= 80) score += 20;
  else if (momentum_score >= 65) score += 10;

  // Move freshness
  if ((move?.move_started_ago_min ?? 999) <= 10) score += 15;
  else if ((move?.move_started_ago_min ?? 999) <= 30) score += 8;

  return Math.min(100, score);
};

const confidenceLabel = (c) => {
  if (c >= 80) return { text: 'VERY HIGH', color: 'text-green-400 bg-green-900/40 border-green-500/50' };
  if (c >= 60) return { text: 'HIGH', color: 'text-green-300 bg-green-900/30 border-green-500/30' };
  if (c >= 40) return { text: 'MODERATE', color: 'text-yellow-400 bg-yellow-900/30 border-yellow-500/30' };
  return { text: 'LOW', color: 'text-slate-400 bg-slate-800 border-slate-600' };
};

// ─── Heat Map ────────────────────────────────────────────

function MarketHeatMap({ stocks }) {
  const distribution = stocks.reduce((acc, s) => {
    const c = s.move?.change_5m ?? s.live_data?.change_percent ?? 0;
    if (c > 5) acc[0]++;
    else if (c > 2) acc[1]++;
    else if (c > 0.5) acc[2]++;
    else if (c > -0.5) acc[3]++;
    else if (c > -2) acc[4]++;
    else acc[5]++;
    return acc;
  }, [0, 0, 0, 0, 0, 0]);

  const total = stocks.length || 1;
  const bullish = ((distribution[0] + distribution[1] + distribution[2]) / total * 100).toFixed(0);
  const colors = ['bg-green-500', 'bg-green-400', 'bg-green-300', 'bg-yellow-300', 'bg-red-300', 'bg-red-500'];

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-3 mb-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-bold text-slate-400 uppercase tracking-wider">Market Breadth (5m)</span>
        <span className={`px-2 py-0.5 rounded text-xs font-bold ${
          bullish > 65 ? 'bg-green-500/20 text-green-400' :
          bullish > 40 ? 'bg-yellow-500/20 text-yellow-400' :
          'bg-red-500/20 text-red-400'
        }`}>
          {bullish > 65 ? 'RISK ON' : bullish > 40 ? 'MIXED' : 'RISK OFF'} — {bullish}% green
        </span>
      </div>
      <div className="flex gap-0.5 h-2.5 rounded-full overflow-hidden">
        {distribution.map((count, idx) => (
          <div key={idx} className={`${colors[idx]}`} style={{ width: `${(count / total * 100)}%` }} />
        ))}
      </div>
    </div>
  );
}

// ─── Move Display (the core) ─────────────────────────────

function MoveDisplay({ move, compact = false }) {
  if (!move || move.price === 0) {
    return <span className="text-xs text-slate-500">No data</span>;
  }

  const accel = accelLabel(move.acceleration);
  const vel = Math.abs(move.velocity_5m);

  if (compact) {
    return (
      <div className="flex flex-col gap-1">
        {/* Active Move - short-term */}
        <div className="flex items-center gap-2">
          <div className={`flex items-center gap-1 px-2 py-0.5 rounded border ${changeBg(move.change_5m)}`}>
            <span className={`text-sm font-bold ${changeColor(move.change_5m)}`}>
              5m: {arrow(move.change_5m)} {abs_pct(move.change_5m)}%
            </span>
          </div>
          <div className={`flex items-center gap-1 px-2 py-0.5 rounded border ${changeBg(move.change_15m)}`}>
            <span className={`text-sm font-bold ${changeColor(move.change_15m)}`}>
              15m: {arrow(move.change_15m)} {abs_pct(move.change_15m)}%
            </span>
          </div>
        </div>

        {/* Velocity + Acceleration */}
        <div className="flex items-center gap-2 text-xs">
          {move.move_started_ago_min > 0 && move.move_trigger !== 'none' && (
            <span className="text-yellow-400">⚡ Move: {move.move_started_ago_min}m ago</span>
          )}
          <span className={accel.color}>{accel.icon} {accel.text}</span>
          {move.rel_volume >= 1.5 && (
            <span className="text-orange-400">Vol: {move.rel_volume}x</span>
          )}
        </div>
      </div>
    );
  }

  // Full display for TOP 3
  return (
    <div className="space-y-3">
      {/* Context Move */}
      <div className="text-sm text-slate-400">
        <span className={changeColor(move.daily_change)}>
          {arrow(move.daily_change)} {abs_pct(move.daily_change)}%
        </span> today (since open ${move.open_price})
      </div>

      {/* Active Move - THE MAIN EVENT */}
      <div className={`p-3 rounded-lg border-2 ${
        Math.abs(move.change_5m) >= 2 ? 'border-yellow-500/60 bg-yellow-900/10' : 'border-slate-600 bg-slate-900/40'
      }`}>
        {/* Move start */}
        {move.move_started_ago_min > 0 && move.move_trigger !== 'none' && (
          <div className="flex items-center gap-2 mb-2 text-sm">
            <span className="text-yellow-400 font-bold">⚡ Move started {move.move_started_ago_min}m ago</span>
            <span className="text-slate-500">{triggerLabel(move.move_trigger)}</span>
            {move.move_change_since_start !== 0 && (
              <span className={`font-bold ${changeColor(move.move_change_since_start)}`}>
                ({arrow(move.move_change_since_start)} {abs_pct(move.move_change_since_start)}% since trigger)
              </span>
            )}
          </div>
        )}

        {/* 5m / 15m windows */}
        <div className="grid grid-cols-2 gap-3">
          <div className={`p-2 rounded border ${changeBg(move.change_5m)}`}>
            <div className="text-xs text-slate-400 mb-1">5 min</div>
            <div className={`text-2xl font-bold ${changeColor(move.change_5m)}`}>
              {arrow(move.change_5m)} {abs_pct(move.change_5m)}%
            </div>
          </div>
          <div className={`p-2 rounded border ${changeBg(move.change_15m)}`}>
            <div className="text-xs text-slate-400 mb-1">15 min</div>
            <div className={`text-2xl font-bold ${changeColor(move.change_15m)}`}>
              {arrow(move.change_15m)} {abs_pct(move.change_15m)}%
            </div>
          </div>
        </div>

        {/* Velocity + Acceleration */}
        <div className="mt-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div>
              <span className="text-xs text-slate-500">Velocity</span>
              <div className={`text-sm font-bold ${
                vel >= 0.5 ? 'text-red-400' : vel >= 0.2 ? 'text-orange-400' : vel >= 0.05 ? 'text-yellow-400' : 'text-slate-400'
              }`}>
                {move.velocity_5m.toFixed(3)}%/min
              </div>
            </div>
            <div>
              <span className="text-xs text-slate-500">Acceleration</span>
              <div className={`text-sm font-bold ${accel.color}`}>
                {accel.icon} {accel.text}
              </div>
            </div>
          </div>

          {/* Relative Volume */}
          <div className="text-right">
            <span className="text-xs text-slate-500">Rel. Volume</span>
            <div className={`text-sm font-bold ${
              move.rel_volume >= 3 ? 'text-red-400' :
              move.rel_volume >= 2 ? 'text-orange-400' :
              move.rel_volume >= 1.5 ? 'text-yellow-400' :
              'text-slate-400'
            }`}>
              {move.rel_volume}x
            </div>
          </div>
        </div>

        {/* Speed Bar */}
        <div className="mt-2">
          <div className="relative w-full h-2 bg-slate-800 rounded-full overflow-hidden">
            <div
              className={`absolute top-0 left-0 h-full transition-all duration-500 rounded-full ${
                vel >= 0.5 ? 'bg-gradient-to-r from-orange-500 to-red-500' :
                vel >= 0.2 ? 'bg-gradient-to-r from-yellow-500 to-orange-500' :
                vel >= 0.05 ? 'bg-gradient-to-r from-green-400 to-yellow-500' :
                'bg-slate-600'
              }`}
              style={{ width: `${Math.min(100, vel * 100)}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Action Buttons ──────────────────────────────────────

function ActionButtons({ ticker, url, compact = false }) {
  const btnClass = compact
    ? 'px-2 py-1 text-xs rounded'
    : 'flex-1 px-3 py-2 text-sm font-semibold rounded-lg flex items-center justify-center gap-1';

  return (
    <div className={`flex gap-2 ${compact ? '' : 'mt-3'}`}>
      <button
        onClick={(e) => { e.stopPropagation(); window.open(`https://finviz.com/quote.ashx?t=${ticker}`, '_blank'); }}
        className={`${btnClass} bg-blue-600/80 hover:bg-blue-600 text-white transition-all`}
      >
        <BarChart3 size={compact ? 12 : 14} />
        {!compact && ' Chart'}
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); if (url) window.open(url, '_blank'); }}
        className={`${btnClass} bg-purple-600/80 hover:bg-purple-600 text-white transition-all`}
      >
        <Newspaper size={compact ? 12 : 14} />
        {!compact && ' News'}
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); window.open(`https://www.tradingview.com/symbols/${ticker}`, '_blank'); }}
        className={`${btnClass} bg-green-600/80 hover:bg-green-600 text-white transition-all`}
      >
        <Activity size={compact ? 12 : 14} />
        {!compact && ' Live'}
      </button>
    </div>
  );
}

// ─── TOP 3 Card ──────────────────────────────────────────

function TopCard({ stock, rank }) {
  const move = stock.move || {};
  const confidence = confidenceCalc(move, stock.momentum_score);
  const confInfo = confidenceLabel(confidence);

  const borders = {
    1: 'border-yellow-500/50 from-yellow-900/20',
    2: 'border-slate-400/40 from-slate-700/20',
    3: 'border-orange-500/30 from-orange-900/15',
  };
  const medals = { 1: '🥇', 2: '🥈', 3: '🥉' };

  return (
    <div className={`
      relative bg-gradient-to-br ${borders[rank]} via-slate-800 to-slate-900
      border-2 rounded-xl p-5 cursor-pointer
      hover:scale-[1.01] transition-transform duration-200
    `}>
      {/* Rank */}
      <div className="absolute top-3 right-4 text-4xl opacity-80">{medals[rank]}</div>

      {/* Header: Ticker + Price */}
      <div className="flex items-baseline gap-3 mb-3">
        <span className={`font-bold text-white ${rank === 1 ? 'text-5xl' : rank === 2 ? 'text-4xl' : 'text-3xl'}`}>
          {stock.ticker}
        </span>
        {move.price > 0 && (
          <span className="text-2xl font-bold text-green-400">${move.price}</span>
        )}
        {stock.live_data?.company_name && (
          <span className="text-sm text-slate-400">{stock.live_data.company_name}</span>
        )}
      </div>

      {/* Move Display */}
      <MoveDisplay move={move} />

      {/* Confidence + Catalysts */}
      <div className="mt-4 flex items-center gap-4">
        {/* Confidence */}
        <div className="flex-1">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs text-slate-400">Trade Confidence</span>
            <span className={`text-xs font-bold px-2 py-0.5 rounded border ${confInfo.color}`}>
              {confInfo.text}
            </span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all duration-500 ${
                confidence >= 80 ? 'bg-green-500' :
                confidence >= 60 ? 'bg-green-400' :
                confidence >= 40 ? 'bg-yellow-400' :
                'bg-slate-500'
              }`}
              style={{ width: `${confidence}%` }}
            />
          </div>
        </div>
      </div>

      {/* Quick Catalysts */}
      <div className="mt-3 flex flex-wrap gap-1">
        {move.acceleration === 'increasing' && (
          <span className="px-2 py-0.5 bg-green-900/40 text-green-400 rounded text-xs font-bold">🚀 Accelerating</span>
        )}
        {move.rel_volume >= 2 && (
          <span className="px-2 py-0.5 bg-orange-900/40 text-orange-400 rounded text-xs font-bold">🔥 Vol {move.rel_volume}x</span>
        )}
        {move.distance_from_hod >= -0.5 && move.distance_from_hod <= 0 && (
          <span className="px-2 py-0.5 bg-yellow-900/40 text-yellow-400 rounded text-xs font-bold">🔺 Near HOD</span>
        )}
        {Math.abs(move.change_5m) >= 2 && (
          <span className="px-2 py-0.5 bg-red-900/40 text-red-400 rounded text-xs font-bold">⚡ Fast move</span>
        )}
        {move.move_started_ago_min > 0 && move.move_started_ago_min <= 10 && (
          <span className="px-2 py-0.5 bg-blue-900/40 text-blue-400 rounded text-xs font-bold">⏰ Fresh ({move.move_started_ago_min}m)</span>
        )}
      </div>

      {/* Action Buttons */}
      <ActionButtons ticker={stock.ticker} url={stock.url} />
    </div>
  );
}

// ─── Compact Card ────────────────────────────────────────

function CompactCard({ stock }) {
  const move = stock.move || {};
  const confidence = confidenceCalc(move, stock.momentum_score);
  const confInfo = confidenceLabel(confidence);

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 hover:border-blue-500/50 transition-all cursor-pointer">
      <div className="flex items-start justify-between gap-3">
        {/* Left */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg font-bold text-white">{stock.ticker}</span>
            {move.price > 0 && (
              <span className="text-base font-bold text-green-400">${move.price}</span>
            )}
            <span className={`text-xs px-1.5 py-0.5 rounded border ${confInfo.color}`}>
              {confInfo.text}
            </span>
          </div>

          {/* Move data */}
          <MoveDisplay move={move} compact />
        </div>

        {/* Right - Actions */}
        <div className="flex flex-col items-end gap-1">
          <ActionButtons ticker={stock.ticker} url={stock.url} compact />
        </div>
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────

export default function MomentumScannerPro({ stocks, loading }) {
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

  // Sort by active move strength (5m change), not daily
  const sorted = [...stocks].sort((a, b) => {
    const a5m = Math.abs(a.move?.change_5m ?? 0);
    const b5m = Math.abs(b.move?.change_5m ?? 0);
    // If no move data, fall back to momentum_score
    if (a5m === 0 && b5m === 0) return b.momentum_score - a.momentum_score;
    return b5m - a5m;
  });

  const top3 = sorted.slice(0, 3);
  const rest = sorted.slice(3);

  return (
    <div>
      {/* Heat Map */}
      <MarketHeatMap stocks={stocks} />

      {/* TOP 3 FOCUS ZONE */}
      <div className="mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Target className="text-yellow-400" size={20} />
          <h3 className="text-lg font-bold text-white">FOCUS ZONE</h3>
          <span className="text-xs text-slate-500">sorted by 5m move strength</span>
        </div>
        <div className="grid grid-cols-1 gap-4">
          {top3.map((stock, idx) => (
            <TopCard key={stock.ticker} stock={stock} rank={idx + 1} />
          ))}
        </div>
      </div>

      {/* Rest */}
      {rest.length > 0 && (
        <div>
          <h3 className="text-sm font-bold text-slate-500 mb-2 uppercase tracking-wider">
            Other ({rest.length})
          </h3>
          <div className="space-y-2">
            {rest.map((stock) => (
              <CompactCard key={stock.ticker} stock={stock} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
