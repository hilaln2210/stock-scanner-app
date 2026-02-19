import { TrendingUp, TrendingDown, Zap, Activity } from 'lucide-react';

export default function QuickStats({ stocks }) {
  if (!stocks || stocks.length === 0) {
    return null;
  }

  // Calculate stats
  const avgMomentum = (stocks.reduce((sum, s) => sum + s.momentum_score, 0) / stocks.length).toFixed(1);
  const highMomentumCount = stocks.filter(s => s.momentum_score >= 80).length;
  const gainersCount = stocks.filter(s => s.price_change > 0).length;
  const losersCount = stocks.filter(s => s.price_change < 0).length;

  const stats = [
    {
      label: 'Extreme Momentum',
      value: highMomentumCount,
      icon: Zap,
      color: 'text-green-400',
      bg: 'bg-green-900/20'
    },
    {
      label: 'Average Score',
      value: avgMomentum,
      icon: Activity,
      color: 'text-blue-400',
      bg: 'bg-blue-900/20'
    },
    {
      label: 'Gainers',
      value: gainersCount,
      icon: TrendingUp,
      color: 'text-green-400',
      bg: 'bg-green-900/20'
    },
    {
      label: 'Decliners',
      value: losersCount,
      icon: TrendingDown,
      color: 'text-red-400',
      bg: 'bg-red-900/20'
    }
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {stats.map((stat, idx) => (
        <div key={idx} className={`${stat.bg} border border-slate-700 rounded-lg p-4`}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-sm">{stat.label}</p>
              <p className={`text-2xl font-bold ${stat.color} mt-1`}>{stat.value}</p>
            </div>
            <stat.icon className={stat.color} size={32} />
          </div>
        </div>
      ))}
    </div>
  );
}
