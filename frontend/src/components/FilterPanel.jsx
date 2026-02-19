import { Search, Filter, TrendingUp, TrendingDown, Eye } from 'lucide-react';

export default function FilterPanel({ filters, onFilterChange }) {
  return (
    <div className="bg-slate-800 rounded-lg p-4 border border-slate-700 mb-6">
      <div className="flex items-center gap-2 mb-4">
        <Filter size={20} className="text-slate-400" />
        <h3 className="text-white font-semibold">Filters</h3>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Search */}
        <div>
          <label className="block text-sm text-slate-400 mb-2">Search Ticker</label>
          <div className="relative">
            <Search size={18} className="absolute left-3 top-2.5 text-slate-500" />
            <input
              type="text"
              placeholder="AAPL"
              value={filters.ticker || ''}
              onChange={(e) => onFilterChange({ ...filters, ticker: e.target.value.toUpperCase() })}
              className="w-full pl-10 pr-3 py-2 bg-slate-900 border border-slate-700 rounded text-white placeholder-slate-500 focus:outline-none focus:border-blue-500"
            />
          </div>
        </div>

        {/* Min Score */}
        <div>
          <label className="block text-sm text-slate-400 mb-2">
            Min Score: {filters.minScore}
          </label>
          <input
            type="range"
            min="0"
            max="100"
            step="5"
            value={filters.minScore}
            onChange={(e) => onFilterChange({ ...filters, minScore: parseInt(e.target.value) })}
            className="w-full"
          />
        </div>

        {/* Stance */}
        <div>
          <label className="block text-sm text-slate-400 mb-2">Stance</label>
          <div className="flex gap-2">
            <button
              onClick={() => onFilterChange({ ...filters, stance: '' })}
              className={`flex-1 py-2 px-3 rounded border transition-colors ${
                filters.stance === ''
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-600'
              }`}
            >
              All
            </button>
            <button
              onClick={() => onFilterChange({ ...filters, stance: 'Bullish' })}
              className={`flex-1 py-2 px-3 rounded border transition-colors flex items-center justify-center gap-1 ${
                filters.stance === 'Bullish'
                  ? 'bg-green-600 border-green-500 text-white'
                  : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-600'
              }`}
            >
              <TrendingUp size={16} />
            </button>
            <button
              onClick={() => onFilterChange({ ...filters, stance: 'Bearish' })}
              className={`flex-1 py-2 px-3 rounded border transition-colors flex items-center justify-center gap-1 ${
                filters.stance === 'Bearish'
                  ? 'bg-red-600 border-red-500 text-white'
                  : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-600'
              }`}
            >
              <TrendingDown size={16} />
            </button>
            <button
              onClick={() => onFilterChange({ ...filters, stance: 'Watchlist' })}
              className={`flex-1 py-2 px-3 rounded border transition-colors flex items-center justify-center gap-1 ${
                filters.stance === 'Watchlist'
                  ? 'bg-yellow-600 border-yellow-500 text-white'
                  : 'bg-slate-900 border-slate-700 text-slate-400 hover:border-slate-600'
              }`}
            >
              <Eye size={16} />
            </button>
          </div>
        </div>

        {/* Auto Refresh */}
        <div>
          <label className="block text-sm text-slate-400 mb-2">Auto Refresh</label>
          <select
            value={filters.autoRefresh}
            onChange={(e) => onFilterChange({ ...filters, autoRefresh: parseInt(e.target.value) })}
            className="w-full py-2 px-3 bg-slate-900 border border-slate-700 rounded text-white focus:outline-none focus:border-blue-500"
          >
            <option value={0}>Off</option>
            <option value={30}>30 seconds</option>
            <option value={60}>1 minute</option>
            <option value={300}>5 minutes</option>
            <option value={600}>10 minutes</option>
          </select>
        </div>
      </div>
    </div>
  );
}
