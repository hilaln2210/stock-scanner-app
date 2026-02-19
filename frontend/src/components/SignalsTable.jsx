import { TrendingUp, TrendingDown, Eye } from 'lucide-react';

function getStanceIcon(stance) {
  switch (stance) {
    case 'Bullish':
      return <TrendingUp className="text-green-400" size={18} />;
    case 'Bearish':
      return <TrendingDown className="text-red-400" size={18} />;
    default:
      return <Eye className="text-yellow-400" size={18} />;
  }
}

function getStanceColor(stance) {
  switch (stance) {
    case 'Bullish':
      return 'text-green-400';
    case 'Bearish':
      return 'text-red-400';
    default:
      return 'text-yellow-400';
  }
}

function getScoreColor(score) {
  if (score >= 80) return 'text-green-400 bg-green-950';
  if (score >= 60) return 'text-blue-400 bg-blue-950';
  if (score >= 40) return 'text-yellow-400 bg-yellow-950';
  return 'text-red-400 bg-red-950';
}

function formatTime(timestamp) {
  const date = new Date(timestamp);
  const now = new Date();
  const diff = Math.floor((now - date) / 1000 / 60); // minutes

  if (diff < 60) return `${diff}m ago`;
  if (diff < 1440) return `${Math.floor(diff / 60)}h ago`;
  return date.toLocaleDateString();
}

export default function SignalsTable({ signals, selectedSignal, onSelectSignal }) {
  if (!signals || signals.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        No signals found. Signals will appear as news is processed.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="bg-slate-800 border-b border-slate-700">
          <tr>
            <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Ticker</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Signal Type</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Score</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Stance</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Time</th>
            <th className="px-4 py-3 text-left text-xs font-medium text-slate-400 uppercase">Reason</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-700">
          {signals.map((signal) => (
            <tr
              key={signal.id}
              onClick={() => onSelectSignal(signal)}
              className={`hover:bg-slate-700 cursor-pointer transition-colors ${
                selectedSignal?.id === signal.id ? 'bg-slate-700' : ''
              }`}
            >
              <td className="px-4 py-3">
                <span className="font-mono font-bold text-lg text-blue-300">{signal.ticker}</span>
              </td>
              <td className="px-4 py-3 text-slate-300">
                {signal.signal_type.replace(/_/g, ' ').toUpperCase()}
              </td>
              <td className="px-4 py-3">
                <span className={`px-2 py-1 rounded text-sm font-semibold ${getScoreColor(signal.score)}`}>
                  {Math.round(signal.score)}
                </span>
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center gap-2">
                  {getStanceIcon(signal.stance)}
                  <span className={getStanceColor(signal.stance)}>{signal.stance}</span>
                </div>
              </td>
              <td className="px-4 py-3 text-slate-400 text-sm">{formatTime(signal.event_time)}</td>
              <td className="px-4 py-3 text-slate-300 text-sm max-w-md truncate">{signal.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
