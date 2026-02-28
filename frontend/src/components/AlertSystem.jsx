/**
 * AlertSystem — global big-mover push notifications
 *
 * Polls /api/alerts/movers every 90s.
 * For each NEW ticker (not seen before this session): shows a toast.
 * Toasts auto-dismiss after 12s. User can dismiss manually or snooze all.
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';

const API_BASE = '/api';
const POLL_INTERVAL = 90_000;   // 90 seconds
const TOAST_LIFETIME = 12_000;  // 12 seconds before auto-dismiss
const MAX_VISIBLE = 5;          // max toasts on screen at once

// Sector → icon map (same as DailyBriefing)
const SECTOR_ICONS = {
  'Technology':             '💻',
  'Healthcare':             '💊',
  'Financial Services':     '🏦',
  'Financial':              '🏦',
  'Consumer Cyclical':      '🛍️',
  'Consumer Defensive':     '🛒',
  'Consumer Discretionary': '🛍️',
  'Consumer Staples':       '🛒',
  'Energy':                 '⚡',
  'Industrials':            '🏭',
  'Communication Services': '📡',
  'Utilities':              '💡',
  'Real Estate':            '🏘️',
  'Basic Materials':        '⛏️',
  'Materials':              '⛏️',
};
function sectorIcon(s) { return s ? (SECTOR_ICONS[s] || '📊') : ''; }

function pctColor(pct) {
  if (pct >= 25) return '#f87171';   // explosive — warn with red-ish
  if (pct >= 15) return '#fb923c';   // very hot orange
  return '#4ade80';                  // normal green
}

function pctLabel(pct) {
  if (pct >= 25) return `+${pct.toFixed(1)}% 🔥`;
  if (pct >= 15) return `+${pct.toFixed(1)}% ⚡`;
  return `+${pct.toFixed(1)}%`;
}

// Individual toast card
function AlertToast({ alert, onDismiss }) {
  const [progress, setProgress] = useState(100);
  const [exiting, setExiting] = useState(false);
  const startRef = useRef(Date.now());
  const rafRef   = useRef(null);

  // Animate the progress bar countdown
  useEffect(() => {
    const tick = () => {
      const elapsed = Date.now() - startRef.current;
      const remaining = Math.max(0, 100 - (elapsed / TOAST_LIFETIME) * 100);
      setProgress(remaining);
      if (remaining > 0) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        handleDismiss();
      }
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => { if (rafRef.current) cancelAnimationFrame(rafRef.current); };
  }, []);

  const handleDismiss = useCallback(() => {
    if (exiting) return;
    setExiting(true);
    setTimeout(() => onDismiss(alert.id), 280);
  }, [exiting, alert.id, onDismiss]);

  const color = pctColor(alert.pct);

  return (
    <div
      className="relative overflow-hidden rounded-xl cursor-pointer select-none"
      style={{
        background: '#0d1117',
        border: `1px solid ${color}44`,
        boxShadow: `0 0 24px ${color}22, 0 4px 20px rgba(0,0,0,0.6)`,
        width: 300,
        opacity: exiting ? 0 : 1,
        transform: exiting ? 'translateX(320px)' : 'translateX(0)',
        transition: 'opacity 0.28s ease, transform 0.28s ease',
      }}
      onClick={() => window.open(`https://finviz.com/quote.ashx?t=${alert.ticker}`, '_blank')}
    >
      {/* Countdown bar — top edge */}
      <div className="absolute top-0 left-0 h-0.5 transition-none"
        style={{ width: `${progress}%`, background: color, boxShadow: `0 0 6px ${color}` }} />

      {/* Content */}
      <div className="p-3.5 pr-9">
        <div className="flex items-start gap-3">
          {/* Pulsing color dot */}
          <div className="mt-0.5 relative shrink-0">
            <div className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />
            <div className="absolute inset-0 rounded-full animate-ping" style={{ background: color, opacity: 0.4 }} />
          </div>

          <div className="flex-1 min-w-0">
            {/* Header */}
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="text-base font-black text-white tracking-tight">{alert.ticker}</span>
              <span className="text-base font-black tabular-nums" style={{ color }}>
                {pctLabel(alert.pct)}
              </span>
            </div>

            {/* Company */}
            <p className="text-xs mt-0.5 truncate" style={{ color: '#94a3b8' }}>
              {alert.company}
            </p>

            {/* Sector + price */}
            <div className="flex items-center gap-2 mt-1.5">
              {alert.sector && (
                <span className="text-[10px] px-1.5 py-0.5 rounded"
                  style={{ background: 'rgba(255,255,255,0.05)', color: '#64748b' }}>
                  {sectorIcon(alert.sector)} {alert.sector}
                </span>
              )}
              <span className="text-xs font-mono ml-auto" style={{ color: '#475569' }}>
                ${alert.price} <span style={{ color: '#334155' }}>/ פתיחה ${alert.open}</span>
              </span>
            </div>

            {/* Market cap */}
            {alert.mcap_str && (
              <p className="text-[10px] mt-1" style={{ color: '#334155' }}>
                שווי שוק: {alert.mcap_str}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Dismiss × */}
      <button
        className="absolute top-2.5 right-2.5 w-5 h-5 flex items-center justify-center rounded"
        style={{ color: '#475569', background: 'rgba(255,255,255,0.04)' }}
        onClick={e => { e.stopPropagation(); handleDismiss(); }}
      >
        ×
      </button>
    </div>
  );
}

// Collapsed pill when there are hidden alerts
function CollapsedPill({ count, onClick }) {
  return (
    <button
      onClick={onClick}
      className="rounded-full px-4 py-2 text-sm font-black flex items-center gap-2"
      style={{
        background: 'rgba(239,68,68,0.15)',
        border: '1px solid rgba(239,68,68,0.4)',
        color: '#f87171',
        boxShadow: '0 0 12px rgba(239,68,68,0.15)',
      }}
    >
      <span className="w-2 h-2 rounded-full bg-red-400 animate-pulse" />
      +{count} מניות נוספות ↑10%
    </button>
  );
}

export default function AlertSystem() {
  const [toasts, setToasts]     = useState([]);   // { id, ...moverData }
  const [snoozed, setSnoozed]   = useState(false);
  const [showAll, setShowAll]   = useState(false);
  const seenRef                 = useRef(new Set());
  const nextIdRef               = useRef(0);

  const dismiss = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  const dismissAll = useCallback(() => {
    setToasts([]);
  }, []);

  const snooze = useCallback(() => {
    setSnoozed(true);
    setToasts([]);
    // Un-snooze after 10 minutes
    setTimeout(() => setSnoozed(false), 10 * 60 * 1000);
  }, []);

  const fetchMovers = useCallback(async () => {
    if (snoozed) return;
    try {
      const { data } = await axios.get(`${API_BASE}/alerts/movers`);
      const movers = data.movers || [];
      const newOnes = movers.filter(m => !seenRef.current.has(m.ticker));

      newOnes.forEach(m => seenRef.current.add(m.ticker));

      if (newOnes.length === 0) return;

      setToasts(prev => {
        const added = newOnes.map(m => ({ ...m, id: nextIdRef.current++ }));
        return [...added, ...prev].slice(0, 20);  // keep max 20 in queue
      });
    } catch (e) {
      // Silent fail — alerts are non-critical
    }
  }, [snoozed]);

  // Initial fetch + polling
  useEffect(() => {
    fetchMovers();
    const timer = setInterval(fetchMovers, POLL_INTERVAL);
    return () => clearInterval(timer);
  }, [fetchMovers]);

  if (toasts.length === 0) return null;

  const visible  = showAll ? toasts : toasts.slice(0, MAX_VISIBLE);
  const overflow = toasts.length - MAX_VISIBLE;

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col-reverse gap-2.5 items-end"
      style={{ maxWidth: 320 }}>

      {/* Snooze + dismiss all bar — shown when 2+ toasts */}
      {toasts.length >= 2 && (
        <div className="flex items-center gap-2">
          <button onClick={snooze}
            className="text-[10px] px-2.5 py-1 rounded"
            style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)', color: '#475569' }}>
            נשים על pause (10 דק)
          </button>
          <button onClick={dismissAll}
            className="text-[10px] px-2.5 py-1 rounded"
            style={{ background: 'rgba(255,255,255,0.04)', border: '1px solid rgba(255,255,255,0.06)', color: '#475569' }}>
            נקה הכל ×
          </button>
        </div>
      )}

      {/* Overflow pill */}
      {!showAll && overflow > 0 && (
        <CollapsedPill count={overflow} onClick={() => setShowAll(true)} />
      )}

      {/* Toast stack */}
      {visible.map(toast => (
        <AlertToast key={toast.id} alert={toast} onDismiss={dismiss} />
      ))}
    </div>
  );
}
