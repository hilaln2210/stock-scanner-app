import { useState, useEffect } from 'react';
import { Clock, TrendingUp, Moon, Sun } from 'lucide-react';

export default function MarketStatus({ lastUpdate }) {
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => {
      setCurrentTime(new Date());
    }, 1000);

    return () => clearInterval(timer);
  }, []);

  const getMarketStatus = () => {
    // Convert to ET (Eastern Time - US market time)
    const etTime = new Date(currentTime.toLocaleString('en-US', { timeZone: 'America/New_York' }));
    const hours = etTime.getHours();
    const minutes = etTime.getMinutes();
    const dayOfWeek = etTime.getDay(); // 0 = Sunday, 6 = Saturday

    // Weekend
    if (dayOfWeek === 0 || dayOfWeek === 6) {
      return {
        status: 'MARKET CLOSED',
        label: 'Weekend',
        color: 'text-slate-400',
        bg: 'bg-slate-800',
        icon: Moon
      };
    }

    const timeInMinutes = hours * 60 + minutes;
    const preMarketStart = 4 * 60; // 4:00 AM
    const marketOpen = 9 * 60 + 30; // 9:30 AM
    const marketClose = 16 * 60; // 4:00 PM
    const afterHoursEnd = 20 * 60; // 8:00 PM

    if (timeInMinutes >= preMarketStart && timeInMinutes < marketOpen) {
      return {
        status: 'PRE-MARKET',
        label: 'Opens at 9:30 AM ET',
        color: 'text-blue-400',
        bg: 'bg-blue-900/30',
        icon: Sun
      };
    } else if (timeInMinutes >= marketOpen && timeInMinutes < marketClose) {
      return {
        status: 'MARKET OPEN',
        label: 'Live Trading',
        color: 'text-green-400',
        bg: 'bg-green-900/30',
        icon: TrendingUp
      };
    } else if (timeInMinutes >= marketClose && timeInMinutes < afterHoursEnd) {
      return {
        status: 'AFTER HOURS',
        label: 'Extended Trading',
        color: 'text-orange-400',
        bg: 'bg-orange-900/30',
        icon: Moon
      };
    } else {
      return {
        status: 'MARKET CLOSED',
        label: 'Closed',
        color: 'text-slate-400',
        bg: 'bg-slate-800',
        icon: Moon
      };
    }
  };

  const marketStatus = getMarketStatus();
  const StatusIcon = marketStatus.icon;

  const formatTime = (date) => {
    return date.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false
    });
  };

  const formatDate = (date) => {
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
      year: 'numeric'
    });
  };

  const getETTime = () => {
    const etTime = new Date(currentTime.toLocaleString('en-US', { timeZone: 'America/New_York' }));
    return etTime.toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: true,
      timeZone: 'America/New_York'
    });
  };

  const getTimeSinceUpdate = () => {
    if (!lastUpdate) return 'Just now';

    const now = new Date();
    const updated = new Date(lastUpdate);
    const diffMs = now - updated;
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);

    if (diffSecs < 60) return `${diffSecs}s ago`;
    if (diffMins < 60) return `${diffMins}m ago`;
    return `${diffHours}h ago`;
  };

  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Market Status */}
        <div className={`${marketStatus.bg} border border-slate-700 rounded-lg p-4`}>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-slate-400 text-xs mb-1">Market Status</p>
              <div className="flex items-center gap-2">
                <StatusIcon className={marketStatus.color} size={20} />
                <span className={`font-bold text-lg ${marketStatus.color}`}>
                  {marketStatus.status}
                </span>
              </div>
              <p className="text-slate-500 text-xs mt-1">{marketStatus.label}</p>
            </div>
            {marketStatus.status === 'MARKET OPEN' && (
              <div className="w-3 h-3 bg-green-400 rounded-full animate-pulse"></div>
            )}
          </div>
        </div>

        {/* Current Time */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <p className="text-slate-400 text-xs mb-1">Current Time</p>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <Clock className="text-blue-400" size={18} />
              <span className="font-mono font-bold text-lg text-white">
                {formatTime(currentTime)}
              </span>
              <span className="text-slate-500 text-xs">Local</span>
            </div>
            <div className="flex items-center gap-2 pl-7">
              <span className="font-mono text-sm text-slate-400">
                {getETTime()}
              </span>
              <span className="text-slate-600 text-xs">ET</span>
            </div>
          </div>
        </div>

        {/* Last Update */}
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
          <p className="text-slate-400 text-xs mb-1">Data Updated</p>
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 bg-blue-400 rounded-full"></div>
              <span className="font-bold text-lg text-white">
                {getTimeSinceUpdate()}
              </span>
            </div>
            <p className="text-slate-500 text-xs pl-4">
              {formatDate(currentTime)}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
