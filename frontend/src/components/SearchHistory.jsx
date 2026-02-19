import { useState, useEffect } from 'react';
import { History, X, Search } from 'lucide-react';

export default function SearchHistory({ onSelectTicker }) {
  const [history, setHistory] = useState([]);
  const [isOpen, setIsOpen] = useState(false);

  useEffect(() => {
    const saved = localStorage.getItem('searchHistory');
    if (saved) {
      setHistory(JSON.parse(saved));
    }
  }, []);

  const addToHistory = (ticker) => {
    if (!ticker) return;

    const updated = [ticker, ...history.filter(t => t !== ticker)].slice(0, 10);
    setHistory(updated);
    localStorage.setItem('searchHistory', JSON.stringify(updated));
  };

  const removeFromHistory = (ticker) => {
    const updated = history.filter(t => t !== ticker);
    setHistory(updated);
    localStorage.setItem('searchHistory', JSON.stringify(updated));
  };

  const clearHistory = () => {
    setHistory([]);
    localStorage.removeItem('searchHistory');
  };

  // Expose addToHistory to parent
  useEffect(() => {
    window.addToSearchHistory = addToHistory;
  }, [history]);

  if (!isOpen) {
    return (
      <button
        onClick={() => setIsOpen(true)}
        className="px-3 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded flex items-center gap-2 transition-colors"
        title="Search History"
      >
        <History size={18} />
      </button>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-800 rounded-lg border border-slate-700 max-w-md w-full">
        <div className="px-4 py-3 border-b border-slate-700 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <History className="text-blue-400" size={20} />
            <h3 className="text-white font-semibold">Search History</h3>
          </div>
          <button onClick={() => setIsOpen(false)} className="text-slate-400 hover:text-white">
            <X size={20} />
          </button>
        </div>
        <div className="p-4">
          {history.length === 0 ? (
            <p className="text-slate-400 text-center py-8">No search history yet</p>
          ) : (
            <>
              <div className="space-y-2 mb-3">
                {history.map((ticker) => (
                  <div
                    key={ticker}
                    className="flex items-center justify-between bg-slate-700 hover:bg-slate-600 rounded px-3 py-2 transition-colors"
                  >
                    <button
                      onClick={() => {
                        onSelectTicker(ticker);
                        setIsOpen(false);
                      }}
                      className="flex items-center gap-2 flex-1 text-left"
                    >
                      <Search size={16} className="text-blue-400" />
                      <span className="text-white font-mono">{ticker}</span>
                    </button>
                    <button
                      onClick={() => removeFromHistory(ticker)}
                      className="text-slate-400 hover:text-red-400 transition-colors"
                    >
                      <X size={16} />
                    </button>
                  </div>
                ))}
              </div>
              <button
                onClick={clearHistory}
                className="w-full py-2 bg-red-600 hover:bg-red-700 text-white rounded text-sm transition-colors"
              >
                Clear All History
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
