import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';

export default function ChartModal({ ticker, onClose }) {
  const containerRef = useRef(null);

  useEffect(() => {
    if (!ticker) return;

    // Create TradingView widget script
    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/tv.js';
    script.async = true;
    script.onload = () => {
      if (window.TradingView) {
        new window.TradingView.widget({
          autosize: true,
          symbol: `NASDAQ:${ticker}`,
          interval: 'D',
          timezone: 'America/New_York',
          theme: 'dark',
          style: '1', // Candlestick style
          locale: 'en',
          toolbar_bg: '#1e293b',
          enable_publishing: false,
          hide_side_toolbar: false,
          allow_symbol_change: true,
          container_id: 'tradingview_widget',
          studies: [
            'MASimple@tv-basicstudies',
            'RSI@tv-basicstudies',
            'VWMA@tv-basicstudies'
          ],
          show_popup_button: true,
          popup_width: '1000',
          popup_height: '650'
        });
      }
    };

    document.head.appendChild(script);

    return () => {
      // Cleanup
      if (script.parentNode) {
        script.parentNode.removeChild(script);
      }
    };
  }, [ticker]);

  if (!ticker) return null;

  return (
    <div className="fixed inset-0 bg-black/70 flex items-center justify-center p-4 z-50">
      <div className="bg-slate-800 rounded-lg border border-slate-700 w-full max-w-6xl h-[80vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">{ticker} Chart</h2>
            <p className="text-sm text-slate-400">Real-time candlestick chart with indicators</p>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white transition-colors"
          >
            <X size={24} />
          </button>
        </div>

        {/* Chart Container */}
        <div className="flex-1 p-4">
          <div
            id="tradingview_widget"
            ref={containerRef}
            className="w-full h-full"
          />
        </div>

        {/* Footer with tips */}
        <div className="px-6 py-3 border-t border-slate-700 bg-slate-900/50">
          <p className="text-xs text-slate-400">
            💡 Tip: Use mouse wheel to zoom, drag to pan. Click indicators button to add more studies.
          </p>
        </div>
      </div>
    </div>
  );
}
