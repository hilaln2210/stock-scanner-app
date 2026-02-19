import { TrendingUp, TrendingDown, Eye, BarChart3 } from 'lucide-react';

export default function StatsCards({ stats }) {
  if (!stats) return null;

  return (
    <div className="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">Total Signals</p>
            <p className="text-2xl font-bold text-white">{stats.total_signals}</p>
          </div>
          <BarChart3 className="text-blue-400" size={32} />
        </div>
      </div>

      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">Bullish</p>
            <p className="text-2xl font-bold text-green-400">{stats.bullish_count}</p>
          </div>
          <TrendingUp className="text-green-400" size={32} />
        </div>
      </div>

      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">Bearish</p>
            <p className="text-2xl font-bold text-red-400">{stats.bearish_count}</p>
          </div>
          <TrendingDown className="text-red-400" size={32} />
        </div>
      </div>

      <div className="bg-slate-800 rounded-lg p-4 border border-slate-700">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-slate-400 text-sm">Avg Score</p>
            <p className="text-2xl font-bold text-white">{stats.avg_score}</p>
          </div>
          <Eye className="text-purple-400" size={32} />
        </div>
      </div>
    </div>
  );
}
