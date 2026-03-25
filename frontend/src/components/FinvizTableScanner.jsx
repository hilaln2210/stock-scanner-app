/**
 * FinvizTableScanner
 * - Finviz-style fundamental screener table
 * - Shows move reason badges + expandable news per stock
 * - Auto-refreshes every 30 seconds with live countdown
 */
import { useState, useMemo, useCallback, useEffect, useRef } from 'react';
import ReactDOM from 'react-dom';
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 90000,
  validateStatus: (status) => status >= 200 && status < 300,
});

// ── Filter options — קודים תואמי Finviz (לחיצה ובחירה כמו ב-Finviz) ─────────────
const ANY = { label: 'Any', value: '' };

const MCAP_OPTS = [
  ANY,
  { label: 'Mega ($200bln+)',        value: 'cap_mega' },
  { label: 'Large ($10-200bln)',     value: 'cap_large' },
  { label: 'Mid ($2-10bln)',         value: 'cap_mid' },
  { label: 'Small ($300mln-2bln)',   value: 'cap_small' },
  { label: 'Micro ($50-300mln)',     value: 'cap_micro' },
  { label: 'Nano (under $50mln)',    value: 'cap_nano' },
  { label: '─────────',             value: '', disabled: true },
  { label: '+Micro (over $50mln)',   value: 'cap_microover' },
  { label: '+Small (over $300mln)',  value: 'cap_smallover' },
  { label: '+Mid (over $2bln)',      value: 'cap_midover' },
  { label: '+Large (over $10bln)',   value: 'cap_largeover' },
  { label: '─────────',             value: '', disabled: true },
  { label: '-Micro (under $300mln)', value: 'cap_microunder' },
  { label: '-Small (under $2bln)',   value: 'cap_smallunder' },
  { label: '-Mid (under $10bln)',    value: 'cap_midunder' },
  { label: '-Large (under $200bln)', value: 'cap_largeunder' },
];

const AVGVOL_OPTS = [
  ANY,
  { label: 'Over 50K',         value: 'sh_avgvol_o50' },
  { label: 'Over 100K',        value: 'sh_avgvol_o100' },
  { label: 'Over 200K',        value: 'sh_avgvol_o200' },
  { label: 'Over 300K',        value: 'sh_avgvol_o300' },
  { label: 'Over 400K',        value: 'sh_avgvol_o400' },
  { label: 'Over 500K',        value: 'sh_avgvol_o500' },
  { label: 'Over 750K',        value: 'sh_avgvol_o750' },
  { label: 'Over 1M',          value: 'sh_avgvol_o1000' },
  { label: 'Over 2M',          value: 'sh_avgvol_o2000' },
  { label: 'Under 50K',        value: 'sh_avgvol_u50' },
  { label: 'Under 100K',       value: 'sh_avgvol_u100' },
  { label: 'Under 500K',       value: 'sh_avgvol_u500' },
  { label: 'Under 750K',       value: 'sh_avgvol_u750' },
  { label: 'Under 1M',         value: 'sh_avgvol_u1000' },
  { label: '100K to 500K',     value: 'sh_avgvol_100to500' },
  { label: '100K to 1M',       value: 'sh_avgvol_100to1000' },
  { label: '500K to 1M',       value: 'sh_avgvol_500to1000' },
  { label: '500K to 10M',      value: 'sh_avgvol_500to10000' },
];

const RELVOL_OPTS = [
  ANY,
  { label: 'Over 10×',    value: 'sh_relvol_o10' },
  { label: 'Over 5×',     value: 'sh_relvol_o5' },
  { label: 'Over 3×',     value: 'sh_relvol_o3' },
  { label: 'Over 2×',     value: 'sh_relvol_o2' },
  { label: 'Over 1.5×',   value: 'sh_relvol_o1.5' },
  { label: 'Over 1×',     value: 'sh_relvol_o1' },
  { label: 'Over 0.75×',  value: 'sh_relvol_o0.75' },
  { label: 'Over 0.5×',   value: 'sh_relvol_o0.5' },
  { label: 'Over 0.25×',  value: 'sh_relvol_o0.25' },
  { label: 'Under 2×',    value: 'sh_relvol_u2' },
  { label: 'Under 1.5×',  value: 'sh_relvol_u1.5' },
  { label: 'Under 1×',    value: 'sh_relvol_u1' },
  { label: 'Under 0.75×', value: 'sh_relvol_u0.75' },
  { label: 'Under 0.5×',  value: 'sh_relvol_u0.5' },
];

const CURVOL_OPTS = [
  ANY,
  { label: 'Over 50K',   value: 'sh_curvol_o50' },
  { label: 'Over 100K',  value: 'sh_curvol_o100' },
  { label: 'Over 200K',  value: 'sh_curvol_o200' },
  { label: 'Over 300K',  value: 'sh_curvol_o300' },
  { label: 'Over 400K',  value: 'sh_curvol_o400' },
  { label: 'Over 500K',  value: 'sh_curvol_o500' },
  { label: 'Over 750K',  value: 'sh_curvol_o750' },
  { label: 'Over 1M',    value: 'sh_curvol_o1000' },
  { label: 'Over 2M',    value: 'sh_curvol_o2000' },
  { label: 'Over 5M',    value: 'sh_curvol_o5000' },
  { label: 'Over 10M',   value: 'sh_curvol_o10000' },
  { label: 'Over 20M',   value: 'sh_curvol_o20000' },
  { label: 'Under 50K',  value: 'sh_curvol_u50' },
  { label: 'Under 100K', value: 'sh_curvol_u100' },
  { label: 'Under 500K', value: 'sh_curvol_u500' },
  { label: 'Under 1M',   value: 'sh_curvol_u1000' },
];

const CHANGE_OPTS = [
  ANY,
  { label: 'Custom %', value: 'custom' },
  { label: 'Up',       value: 'ta_change_u' },
  { label: 'Up 1%',    value: 'ta_change_u1' },
  { label: 'Up 2%',    value: 'ta_change_u2' },
  { label: 'Up 3%',    value: 'ta_change_u3' },
  { label: 'Up 4%',    value: 'ta_change_u4' },
  { label: 'Up 5%',    value: 'ta_change_u5' },
  { label: 'Up 6%',    value: 'ta_change_u6' },
  { label: 'Up 7%',    value: 'ta_change_u7' },
  { label: 'Up 8%',    value: 'ta_change_u8' },
  { label: 'Up 9%',    value: 'ta_change_u9' },
  { label: 'Up 10%',   value: 'ta_change_u10' },
  { label: 'Up 15%',   value: 'ta_change_u15' },
  { label: 'Up 20%',   value: 'ta_change_u20' },
  { label: 'Down',     value: 'ta_change_d' },
  { label: 'Down 1%',  value: 'ta_change_d1' },
  { label: 'Down 2%',  value: 'ta_change_d2' },
  { label: 'Down 3%',  value: 'ta_change_d3' },
  { label: 'Down 4%',  value: 'ta_change_d4' },
  { label: 'Down 5%',  value: 'ta_change_d5' },
  { label: 'Down 6%',  value: 'ta_change_d6' },
  { label: 'Down 7%',  value: 'ta_change_d7' },
  { label: 'Down 8%',  value: 'ta_change_d8' },
  { label: 'Down 9%',  value: 'ta_change_d9' },
  { label: 'Down 10%', value: 'ta_change_d10' },
  { label: 'Down 15%', value: 'ta_change_d15' },
  { label: 'Down 20%', value: 'ta_change_d20' },
];

const CHANGEOPEN_OPTS = [
  ANY,
  { label: 'Up',       value: 'ta_changeopen_u' },
  { label: 'Up 1%',    value: 'ta_changeopen_u1' },
  { label: 'Up 2%',    value: 'ta_changeopen_u2' },
  { label: 'Up 3%',    value: 'ta_changeopen_u3' },
  { label: 'Up 4%',    value: 'ta_changeopen_u4' },
  { label: 'Up 5%',    value: 'ta_changeopen_u5' },
  { label: 'Up 6%',    value: 'ta_changeopen_u6' },
  { label: 'Up 7%',    value: 'ta_changeopen_u7' },
  { label: 'Up 8%',    value: 'ta_changeopen_u8' },
  { label: 'Up 9%',    value: 'ta_changeopen_u9' },
  { label: 'Up 10%',   value: 'ta_changeopen_u10' },
  { label: 'Up 15%',   value: 'ta_changeopen_u15' },
  { label: 'Up 20%',   value: 'ta_changeopen_u20' },
  { label: 'Down',     value: 'ta_changeopen_d' },
  { label: 'Down 1%',  value: 'ta_changeopen_d1' },
  { label: 'Down 2%',  value: 'ta_changeopen_d2' },
  { label: 'Down 3%',  value: 'ta_changeopen_d3' },
  { label: 'Down 4%',  value: 'ta_changeopen_d4' },
  { label: 'Down 5%',  value: 'ta_changeopen_d5' },
  { label: 'Down 6%',  value: 'ta_changeopen_d6' },
  { label: 'Down 7%',  value: 'ta_changeopen_d7' },
  { label: 'Down 8%',  value: 'ta_changeopen_d8' },
  { label: 'Down 9%',  value: 'ta_changeopen_d9' },
  { label: 'Down 10%', value: 'ta_changeopen_d10' },
  { label: 'Down 15%', value: 'ta_changeopen_d15' },
  { label: 'Down 20%', value: 'ta_changeopen_d20' },
];

const SALESQQ_OPTS = [
  ANY,
  { label: 'Negative (<0%)',    value: 'fa_salesqoq_neg' },
  { label: 'Positive (>0%)',    value: 'fa_salesqoq_pos' },
  { label: 'Positive Low (0-10%)', value: 'fa_salesqoq_poslow' },
  { label: 'High (>25%)',       value: 'fa_salesqoq_high' },
  { label: 'Over 5%',          value: 'fa_salesqoq_o5' },
  { label: 'Over 10%',         value: 'fa_salesqoq_o10' },
  { label: 'Over 15%',         value: 'fa_salesqoq_o15' },
  { label: 'Over 20%',         value: 'fa_salesqoq_o20' },
  { label: 'Over 25%',         value: 'fa_salesqoq_o25' },
  { label: 'Over 30%',         value: 'fa_salesqoq_o30' },
  { label: 'Under 5%',         value: 'fa_salesqoq_u5' },
  { label: 'Under 10%',        value: 'fa_salesqoq_u10' },
  { label: 'Under 15%',        value: 'fa_salesqoq_u15' },
  { label: 'Under 20%',        value: 'fa_salesqoq_u20' },
  { label: 'Under 25%',        value: 'fa_salesqoq_u25' },
  { label: 'Under 30%',        value: 'fa_salesqoq_u30' },
];

const SHORT_OPTS = [
  ANY,
  { label: 'Low (<5%)',   value: 'sh_short_low' },
  { label: 'High (>20%)', value: 'sh_short_high' },
  { label: 'Over 5%',    value: 'sh_short_o5' },
  { label: 'Over 10%',   value: 'sh_short_o10' },
  { label: 'Over 15%',   value: 'sh_short_o15' },
  { label: 'Over 20%',   value: 'sh_short_o20' },
  { label: 'Over 25%',   value: 'sh_short_o25' },
  { label: 'Over 30%',   value: 'sh_short_o30' },
  { label: 'Under 5%',   value: 'sh_short_u5' },
  { label: 'Under 10%',  value: 'sh_short_u10' },
  { label: 'Under 15%',  value: 'sh_short_u15' },
  { label: 'Under 20%',  value: 'sh_short_u20' },
  { label: 'Under 25%',  value: 'sh_short_u25' },
  { label: 'Under 30%',  value: 'sh_short_u30' },
];

const RSI_OPTS = [
  ANY,
  { label: 'Overbought (90)', value: 'ta_rsi_ob90' },
  { label: 'Overbought (80)', value: 'ta_rsi_ob80' },
  { label: 'Overbought (70)', value: 'ta_rsi_ob70' },
  { label: 'Overbought (60)', value: 'ta_rsi_ob60' },
  { label: 'Oversold (40)',   value: 'ta_rsi_os40' },
  { label: 'Oversold (30)',   value: 'ta_rsi_os30' },
  { label: 'Oversold (20)',   value: 'ta_rsi_os20' },
  { label: 'Oversold (10)',   value: 'ta_rsi_os10' },
  { label: 'Not Overbought (<60)', value: 'ta_rsi_nob60' },
  { label: 'Not Overbought (<50)', value: 'ta_rsi_nob50' },
  { label: 'Not Oversold (>50)',   value: 'ta_rsi_nos50' },
  { label: 'Not Oversold (>40)',   value: 'ta_rsi_nos40' },
];

// NOTE: Finviz uses sh_iown_ prefix (NOT sh_instown_)
const INST_OPTS = [
  ANY,
  { label: 'Low (<5%)',   value: 'sh_iown_low' },
  { label: 'High (>90%)', value: 'sh_iown_high' },
  { label: 'Over 10%',   value: 'sh_iown_o10' },
  { label: 'Over 20%',   value: 'sh_iown_o20' },
  { label: 'Over 30%',   value: 'sh_iown_o30' },
  { label: 'Over 40%',   value: 'sh_iown_o40' },
  { label: 'Over 50%',   value: 'sh_iown_o50' },
  { label: 'Over 60%',   value: 'sh_iown_o60' },
  { label: 'Over 70%',   value: 'sh_iown_o70' },
  { label: 'Over 80%',   value: 'sh_iown_o80' },
  { label: 'Over 90%',   value: 'sh_iown_o90' },
  { label: 'Under 10%',  value: 'sh_iown_u10' },
  { label: 'Under 20%',  value: 'sh_iown_u20' },
  { label: 'Under 30%',  value: 'sh_iown_u30' },
  { label: 'Under 40%',  value: 'sh_iown_u40' },
  { label: 'Under 50%',  value: 'sh_iown_u50' },
  { label: 'Under 60%',  value: 'sh_iown_u60' },
  { label: 'Under 70%',  value: 'sh_iown_u70' },
  { label: 'Under 80%',  value: 'sh_iown_u80' },
  { label: 'Under 90%',  value: 'sh_iown_u90' },
];

const GAP_OPTS = [
  ANY,
  { label: 'Up',       value: 'ta_gap_u' },
  { label: 'Up 1%',    value: 'ta_gap_u1' },
  { label: 'Up 2%',    value: 'ta_gap_u2' },
  { label: 'Up 3%',    value: 'ta_gap_u3' },
  { label: 'Up 4%',    value: 'ta_gap_u4' },
  { label: 'Up 5%',    value: 'ta_gap_u5' },
  { label: 'Up 6%',    value: 'ta_gap_u6' },
  { label: 'Up 7%',    value: 'ta_gap_u7' },
  { label: 'Up 8%',    value: 'ta_gap_u8' },
  { label: 'Up 9%',    value: 'ta_gap_u9' },
  { label: 'Up 10%',   value: 'ta_gap_u10' },
  { label: 'Up 15%',   value: 'ta_gap_u15' },
  { label: 'Up 20%',   value: 'ta_gap_u20' },
  { label: 'Down',     value: 'ta_gap_d' },
  { label: 'Down 1%',  value: 'ta_gap_d1' },
  { label: 'Down 2%',  value: 'ta_gap_d2' },
  { label: 'Down 3%',  value: 'ta_gap_d3' },
  { label: 'Down 4%',  value: 'ta_gap_d4' },
  { label: 'Down 5%',  value: 'ta_gap_d5' },
  { label: 'Down 6%',  value: 'ta_gap_d6' },
  { label: 'Down 7%',  value: 'ta_gap_d7' },
  { label: 'Down 8%',  value: 'ta_gap_d8' },
  { label: 'Down 9%',  value: 'ta_gap_d9' },
  { label: 'Down 10%', value: 'ta_gap_d10' },
  { label: 'Down 15%', value: 'ta_gap_d15' },
  { label: 'Down 20%', value: 'ta_gap_d20' },
];

const SMA50_OPTS = [
  ANY,
  { label: 'Price above SMA50',         value: 'ta_sma50_pa' },
  { label: 'Price 10% above SMA50',     value: 'ta_sma50_pa10' },
  { label: 'Price 20% above SMA50',     value: 'ta_sma50_pa20' },
  { label: 'Price 30% above SMA50',     value: 'ta_sma50_pa30' },
  { label: 'Price 50% above SMA50',     value: 'ta_sma50_pa50' },
  { label: 'Price below SMA50',         value: 'ta_sma50_pb' },
  { label: 'Price 10% below SMA50',     value: 'ta_sma50_pb10' },
  { label: 'Price 20% below SMA50',     value: 'ta_sma50_pb20' },
  { label: 'Price 30% below SMA50',     value: 'ta_sma50_pb30' },
  { label: 'Price crossed SMA50 ↑',     value: 'ta_sma50_pca' },
  { label: 'Price crossed SMA50 ↓',     value: 'ta_sma50_pcb' },
  { label: 'SMA50 above SMA200',        value: 'ta_sma50_sa200' },
  { label: 'SMA50 below SMA200',        value: 'ta_sma50_sb200' },
  { label: 'SMA50 crossed SMA200 ↑ (Golden Cross)', value: 'ta_sma50_cross200a' },
  { label: 'SMA50 crossed SMA200 ↓ (Death Cross)',  value: 'ta_sma50_cross200b' },
  { label: 'SMA50 above SMA20',         value: 'ta_sma50_sa20' },
  { label: 'SMA50 crossed SMA20 ↑',     value: 'ta_sma50_cross20a' },
];

const SMA200_OPTS = [
  ANY,
  { label: 'Price above SMA200',        value: 'ta_sma200_pa' },
  { label: 'Price 10% above SMA200',    value: 'ta_sma200_pa10' },
  { label: 'Price 20% above SMA200',    value: 'ta_sma200_pa20' },
  { label: 'Price 50% above SMA200',    value: 'ta_sma200_pa50' },
  { label: 'Price 100% above SMA200',   value: 'ta_sma200_pa100' },
  { label: 'Price below SMA200',        value: 'ta_sma200_pb' },
  { label: 'Price 10% below SMA200',    value: 'ta_sma200_pb10' },
  { label: 'Price 20% below SMA200',    value: 'ta_sma200_pb20' },
  { label: 'Price 50% below SMA200',    value: 'ta_sma200_pb50' },
  { label: 'Price crossed SMA200 ↑',    value: 'ta_sma200_pca' },
  { label: 'Price crossed SMA200 ↓',    value: 'ta_sma200_pcb' },
  { label: 'SMA200 above SMA50',        value: 'ta_sma200_sa50' },
  { label: 'SMA200 below SMA50',        value: 'ta_sma200_sb50' },
  { label: 'SMA200 crossed SMA50 ↑',    value: 'ta_sma200_cross50a' },
  { label: 'SMA200 crossed SMA50 ↓',    value: 'ta_sma200_cross50b' },
];

const EARNINGS_OPTS = [
  ANY,
  { label: 'היום',                    value: 'earningsdate_today' },
  { label: 'היום לפני פתיחה',         value: 'earningsdate_todaybefore' },
  { label: 'היום אחרי סגירה',         value: 'earningsdate_todayafter' },
  { label: 'מחר',                     value: 'earningsdate_tomorrow' },
  { label: 'מחר לפני פתיחה',          value: 'earningsdate_tomorrowbefore' },
  { label: 'מחר אחרי סגירה',          value: 'earningsdate_tomorrowafter' },
  { label: 'אתמול',                   value: 'earningsdate_yesterday' },
  { label: '5 ימים הקרובים',          value: 'earningsdate_nextdays5' },
  { label: '5 ימים האחרונים',         value: 'earningsdate_prevdays5' },
  { label: 'השבוע',                   value: 'earningsdate_thisweek' },
  { label: 'שבוע הבא',                value: 'earningsdate_nextweek' },
  { label: 'שבוע שעבר',               value: 'earningsdate_prevweek' },
  { label: 'החודש',                   value: 'earningsdate_thismonth' },
];

function buildFilters(mcap, avgvol, relvol, curvol, change, changeopen, shortf, rsi, inst, salesqq, gap, sma50, sma200, earnings) {
  const changeForApi = change === 'custom' ? '' : change;
  return [mcap, avgvol, relvol, curvol, changeForApi, changeopen, shortf, rsi, inst, salesqq, gap, sma50, sma200, earnings]
    .filter(Boolean).join(',');
}

// ── Move reason colors ─────────────────────────────────────────────────────────
const REASON_STYLE = {
  earnings:  { bg: '#0c2a1a', border: '#166534', text: '#4ade80' },
  results:   { bg: '#0c2a1a', border: '#166534', text: '#4ade80' },
  upgrade:   { bg: '#0f2027', border: '#1d4ed8', text: '#60a5fa' },
  downgrade: { bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  fda:       { bg: '#1a0a2e', border: '#6b21a8', text: '#c084fc' },
  ma:        { bg: '#1c1000', border: '#78350f', text: '#fb923c' },
  guidance:  { bg: '#0f1a1a', border: '#0e7490', text: '#22d3ee' },
  contract:  { bg: '#1a1500', border: '#92400e', text: '#fbbf24' },
  risk:      { bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  dilution:  { bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  gap:       { bg: '#0c1a0c', border: '#14532d', text: '#86efac' },
  technical: { bg: '#12121a', border: '#374151', text: '#9ca3af' },
};

// ── Fundamental tag styles ─────────────────────────────────────────────────────
const TAG_META = {
  profitable:  { label: '✅ רווחית',     bg: '#0c2a1a', border: '#166534', text: '#4ade80' },
  loss:        { label: '❌ הפסד',       bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  high_debt:   { label: '⚠️ חוב גבוה',  bg: '#1c1000', border: '#78350f', text: '#fb923c' },
  cash_rich:   { label: '💰 מזומן גבוה', bg: '#0c1a2e', border: '#1e40af', text: '#60a5fa' },
  high_growth: { label: '🔥 צמיחה',     bg: '#1a0a2e', border: '#6b21a8', text: '#c084fc' },
  high_short:  { label: '📉 שורט >15%', bg: '#1c1200', border: '#854d0e', text: '#facc15' },
  earnings:  { label: '📊 דוח',    bg: '#052e16', border: '#166534', text: '#4ade80' },
  fda:       { label: '💊 FDA',     bg: '#1a0a2e', border: '#6b21a8', text: '#c084fc' },
  upgrade:   { label: '⬆️ שדרוג', bg: '#0c1a2e', border: '#1e40af', text: '#60a5fa' },
  contract:  { label: '📝 חוזה',   bg: '#1c1000', border: '#78350f', text: '#fbbf24' },
  ma:        { label: '🤝 עסקה',   bg: '#1a0e00', border: '#92400e', text: '#fb923c' },
  guidance:  { label: '🔮 תחזית',  bg: '#051818', border: '#0e4444', text: '#22d3ee' },
  gap:       { label: '📈 גאפ',    bg: '#052e16', border: '#16653450', text: '#86efac' },
  dilution:  { label: '📉 הנפקה', bg: '#2d0a0a', border: '#7f1d1d', text: '#fb7185' },
  risk:      { label: '⚠️ סיכון',  bg: '#1c1200', border: '#854d0e', text: '#f97316' },
  insider:   { label: '🏷️ פנים',   bg: '#130a2e', border: '#4c1d95', text: '#a78bfa' },
  ai_sector: { label: '🤖 AI',     bg: '#0a1628', border: '#1e40af', text: '#818cf8' },
};

// ── Formatters ─────────────────────────────────────────────────────────────────
function fmtMoney(n) {
  if (n == null || isNaN(n) || n === 0) return '—';
  const abs = Math.abs(n), sign = n < 0 ? '-' : '';
  if (abs >= 1e12) return `${sign}$${(abs / 1e12).toFixed(2)}T`;
  if (abs >= 1e9)  return `${sign}$${(abs / 1e9).toFixed(2)}B`;
  if (abs >= 1e6)  return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  return `${sign}$${abs.toFixed(0)}`;
}
function fmtVol(n) {
  if (!n) return '—';
  if (n >= 1e9) return `${(n / 1e9).toFixed(1)}B`;
  if (n >= 1e6) return `${(n / 1e6).toFixed(1)}M`;
  if (n >= 1e3) return `${(n / 1e3).toFixed(0)}K`;
  return String(n);
}
function fmtNum(v, dec = 1) {
  if (v == null || v === '') return '—';
  const n = parseFloat(v);
  return isNaN(n) ? (v || '—') : n.toFixed(dec);
}

// ── Table style constants — כותרות מעוצבות (פונט נבחר via --header-font) ───────
const TH_BASE = {
  padding: '7px 8px',
  textAlign: 'right',
  fontWeight: 600,
  fontSize: 11,
  color: '#94a3b8',
  letterSpacing: '0.045em',
  textTransform: 'uppercase',
  background: 'linear-gradient(180deg, #0f172a 0%, #020617 100%)',
  borderBottom: '1px solid rgba(51, 65, 85, 0.8)',
  boxShadow: 'inset 0 1px 0 rgba(255,255,255,0.03)',
  whiteSpace: 'nowrap',
  cursor: 'default',
  userSelect: 'none',
  position: 'sticky',
  top: 0,
  zIndex: 2,
};

const TD_BASE = {
  padding: '5px 7px',
  textAlign: 'right',
  verticalAlign: 'middle',
  fontSize: 12,
  color: '#e2e8f0',
  whiteSpace: 'nowrap',
};

// ── Cell helpers ───────────────────────────────────────────────────────────────
function PctCell({ val }) {
  if (val == null || val === '') return <span style={{ color: '#94a3b8' }}>—</span>;
  const n = parseFloat(val);
  const color = n > 0 ? '#4ade80' : n < 0 ? '#f87171' : '#94a3b8';
  return (
    <span style={{ color, fontFamily: 'monospace', fontWeight: 700 }}>
      {n > 0 ? '+' : ''}{n.toFixed(2)}%
    </span>
  );
}

function MoneyCell({ val, str }) {
  // val may be numeric or a string like '708.62M' (smallcap cache stocks)
  const numVal = typeof val === 'string' ? null : val;
  const strVal = str || (typeof val === 'string' ? val : null) || fmtMoney(numVal);
  const display = strVal;
  if (!display || display === '—') return <span style={{ color: '#94a3b8' }}>—</span>;
  const neg = display.startsWith('-') || (numVal != null && numVal < 0);
  return (
    <span style={{ color: neg ? '#f87171' : '#94a3b8', fontFamily: 'monospace', fontSize: 12 }}>
      {display}
    </span>
  );
}

function EvMcCell({ ratio }) {
  if (ratio == null) return <span style={{ color: '#94a3b8' }}>—</span>;
  const r = parseFloat(ratio);
  if (isNaN(r)) return <span style={{ color: '#94a3b8' }}>—</span>;
  const color = r <= 0.85 ? '#4ade80' : r <= 0.95 ? '#a3e635' : r <= 1.1 ? '#94a3b8' : r <= 1.3 ? '#fbbf24' : '#f87171';
  const label = r <= 0.85 ? '💰' : r >= 1.3 ? '⚠️' : '';
  return (
    <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 11, color }}
      title={r <= 0.9 ? 'EV < MC — מזומנים גבוהים, החברה שווה פחות מהשוק מעריך (חיובי)' : r >= 1.2 ? 'EV > MC — חוב גבוה, ערך הארגון גבוה מהשווי (סיכון)' : 'EV ≈ MC — יחס מאוזן'}>
      {label}{r.toFixed(2)}x
    </span>
  );
}

function RsiCell({ val, rsi1h, rsi5m }) {
  const rsiColor = (n) => n > 70 ? '#f87171' : n < 30 ? '#4ade80' : n > 50 ? '#a3e635' : '#94a3b8';
  const mainVal = val ? parseFloat(val) : null;
  const h = rsi1h ? parseFloat(rsi1h) : null;
  const m = rsi5m ? parseFloat(rsi5m) : null;
  if (!mainVal && !h && !m) return <span style={{ color: '#94a3b8' }}>—</span>;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 1, lineHeight: 1.2 }}>
      {mainVal != null && !isNaN(mainVal) && (
        <span style={{ color: rsiColor(mainVal), fontFamily: 'monospace', fontWeight: 800, fontSize: 12 }} title="RSI יומי (14)">
          {mainVal.toFixed(0)}
        </span>
      )}
      <div style={{ display: 'flex', gap: 4 }}>
        {h != null && !isNaN(h) && h > 0 && (
          <span style={{ fontSize: 8, fontFamily: 'monospace', fontWeight: 700, color: rsiColor(h), background: '#0f172a', borderRadius: 3, padding: '1px 3px', border: '1px solid #1e293b' }} title="RSI שעתי">
            1h:{h.toFixed(0)}
          </span>
        )}
        {m != null && !isNaN(m) && m > 0 && (
          <span style={{ fontSize: 8, fontFamily: 'monospace', fontWeight: 700, color: rsiColor(m), background: '#0f172a', borderRadius: 3, padding: '1px 3px', border: '1px solid #1e293b' }} title="RSI 5 דקות">
            5m:{m.toFixed(0)}
          </span>
        )}
      </div>
    </div>
  );
}

function ShortCell({ val }) {
  if (!val) return <span style={{ color: '#94a3b8' }}>—</span>;
  const n = parseFloat(val);
  const color = n > 20 ? '#f87171' : n > 10 ? '#fb923c' : '#94a3b8';
  return <span style={{ color, fontFamily: 'monospace' }}>{val}</span>;
}

function AtrCell({ atr, price, atrPct1h }) {
  const atrVal = parseFloat(atr);
  if (!atr || isNaN(atrVal) || atrVal === 0) return <span style={{ color: '#475569' }}>—</span>;
  const priceVal = parseFloat(price);
  const pct = atrPct1h || (priceVal > 0 ? (atrVal / priceVal * 100) : null);
  const color = !pct ? '#94a3b8' : pct > 5 ? '#f97316' : pct > 3 ? '#facc15' : pct > 1.5 ? '#60a5fa' : '#94a3b8';
  return (
    <div style={{ textAlign: 'center' }}>
      <span style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 600, color }}>${atrVal.toFixed(2)}</span>
      {pct != null && <div style={{ fontSize: 8, color, opacity: 0.75 }}>{pct.toFixed(1)}%</div>}
    </div>
  );
}

function BetaCell({ beta }) {
  const val = parseFloat(beta);
  if (!beta || isNaN(val)) return <span style={{ color: '#475569' }}>—</span>;
  const color = val >= 2.0 ? '#f87171' : val >= 1.5 ? '#fb923c' : val >= 1.0 ? '#94a3b8' : '#60a5fa';
  return <span style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 600, color }}>{val.toFixed(1)}</span>;
}

function SmaCell({ val }) {
  if (!val) return <span style={{ color: '#475569' }}>—</span>;
  const n = parseFloat(val);
  if (isNaN(n)) return <span style={{ color: '#475569' }}>—</span>;
  // >5% above = extended (orange); 0-5% above = healthy (green); -5–0% = pullback (yellow); <-5% = breakdown (red)
  const color = n > 5 ? '#fb923c' : n > 0 ? '#4ade80' : n > -5 ? '#fde047' : '#f87171';
  return (
    <span style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 600, color }}>
      {n > 0 ? '+' : ''}{n.toFixed(1)}%
    </span>
  );
}

function GapCell({ val, isProxy = false }) {
  if (!val) return <span style={{ color: '#475569' }}>—</span>;
  const n = parseFloat(val);
  if (isNaN(n)) return <span style={{ color: '#475569' }}>—</span>;
  const color = n > 2 ? '#4ade80' : n > 0 ? '#a3e635' : n < -2 ? '#f87171' : '#fde047';
  const title = isProxy
    ? `שינוי טרום/אחרי שוק: ${n > 0 ? '+' : ''}${n.toFixed(1)}% (Gap% לא זמין עדיין)`
    : n > 0 ? `גאפ פתיחה +${n.toFixed(1)}% — מומנטום חיובי` : `גאפ פתיחה ${n.toFixed(1)}% — חולשה`;
  return (
    <div style={{ textAlign: 'center' }}>
      <span style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 700, color }} title={title}>
        {n > 0 ? '+' : ''}{n.toFixed(1)}%
      </span>
      {isProxy && <div style={{ fontSize: 7, color: '#475569', lineHeight: 1 }}>ext</div>}
    </div>
  );
}

function EpsQqCell({ val }) {
  if (!val) return <span style={{ color: '#475569' }}>—</span>;
  const n = parseFloat(val);
  if (isNaN(n)) return <span style={{ color: '#475569' }}>—</span>;
  // EPS QoQ: >25% = strong acceleration (green), >0% = growth (light green), <0% = decline (red)
  const color = n > 50 ? '#4ade80' : n > 25 ? '#a3e635' : n > 0 ? '#fde047' : '#f87171';
  const icon = n > 50 ? '🚀' : n > 25 ? '↑' : n > 0 ? '~' : '↓';
  return (
    <span style={{ fontFamily: 'monospace', fontSize: 11, fontWeight: 700, color }}
      title={`EPS רבעון על רבעון: ${n > 0 ? '+' : ''}${n.toFixed(0)}%`}>
      {icon}{n > 0 ? '+' : ''}{n.toFixed(0)}%
    </span>
  );
}

// ── Technical Analysis signal badge ─────────────────────────────────────────────
const TA_SIGNAL_META = {
  'Strong Buy':  { label: 'קנייה חזקה', short: '🟢🟢', bg: '#052e16', border: '#166534', text: '#4ade80' },
  'Buy':         { label: 'קנייה',       short: '🟢',   bg: '#052e16', border: '#166534', text: '#4ade80' },
  'Neutral':     { label: 'ניטרלי',      short: '🟡',   bg: '#1c1a00', border: '#854d0e', text: '#fde047' },
  'Sell':        { label: 'מכירה',       short: '🔴',   bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  'Strong Sell': { label: 'מכירה חזקה', short: '🔴🔴', bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
};

function extractTime(str) {
  if (!str) return '';
  const m = str.match(/(\d{2}:\d{2}-\d{2}:\d{2})/);
  return m ? m[1] : '';
}

const SQUEEZE_META = {
  firing:      { emoji: '🚀', label: 'יורה',     color: '#4ade80', bg: 'rgba(74,222,128,0.15)', border: '#4ade80',  entry: '⚡ כניסה אגרסיבית עם STOP TIGHT', entryColor: '#4ade80' },
  compression: { emoji: '⏳', label: 'דחיסה',    color: '#fde047', bg: 'rgba(253,224,71,0.12)',  border: '#fde047', entry: '🎯 כניסה אידיאלית — לפני הפיצוץ',  entryColor: '#fde047' },
  accumulation:{ emoji: '👀', label: 'צבירה',    color: '#38bdf8', bg: 'rgba(56,189,248,0.12)', border: '#38bdf8',  entry: '⏳ המתיני לדחיסה — עוד מוקדם',     entryColor: '#94a3b8' },
  exhaustion:  { emoji: '⚠️', label: 'עייפות',   color: '#f87171', bg: 'rgba(248,113,113,0.12)', border: '#f87171', entry: '🚪 אל תיכנסי — שקלי יציאה',        entryColor: '#f87171' },
  none:        { emoji: '',   label: '',          color: '#475569', bg: 'transparent',           border: 'transparent', entry: '', entryColor: '#475569' },
};

// ── Column filter options per column key ──────────────────────────────────────
const COL_FILTER_OPTS = {
  squeeze_total_score: [
    { label: 'הכל', value: '' },
    { label: '🔥 NEWS + SQUEEZE', value: 'catalyst_squeeze' },
    { label: '🚀 יורה (Firing)', value: 'firing' },
    { label: '⏳ דחיסה (Compression)', value: 'compression' },
    { label: '👀 צבירה (Accumulation)', value: 'accumulation' },
    { label: '⚠️ עייפות (Exhaustion)', value: 'exhaustion' },
    { label: '— ללא סקוויז', value: 'none' },
  ],
  tech_score: [
    { label: 'הכל', value: '' },
    { label: '⚡ Strong Buy', value: 'strong_buy' },
    { label: '▲ Buy', value: 'buy' },
    { label: '◆ Neutral', value: 'neutral' },
    { label: '▼ Sell', value: 'sell' },
    { label: '✖ Strong Sell', value: 'strong_sell' },
  ],
  rsi: [
    { label: 'הכל', value: '' },
    { label: '🔴 קנוי יתר (>70)', value: 'overbought' },
    { label: '🟢 נורמלי (30–70)', value: 'normal' },
    { label: '🔵 מכור יתר (<30)', value: 'oversold' },
  ],
  short_float: [
    { label: 'הכל', value: '' },
    { label: '🔥 >20% (קיצוני)', value: 'sh_high' },
    { label: '📈 10–20% (גבוה)', value: 'sh_mid' },
    { label: '📊 5–10% (בינוני)', value: 'sh_low' },
    { label: '📉 <5% (נמוך)', value: 'sh_minimal' },
  ],
  rel_volume: [
    { label: 'הכל', value: '' },
    { label: '🔥 >3× (חריג)', value: 'rv_extreme' },
    { label: '📈 2–3× (גבוה)', value: 'rv_high' },
    { label: '📊 1–2× (רגיל)', value: 'rv_normal' },
    { label: '📉 <1× (שקט)', value: 'rv_low' },
  ],
  change_pct: [
    { label: 'הכל', value: '' },
    { label: '🚀 >10%', value: 'chg_huge' },
    { label: '📈 5–10%', value: 'chg_high' },
    { label: '📊 2–5%', value: 'chg_mid' },
    { label: '🔻 <0% (ירידה)', value: 'chg_neg' },
  ],
  market_cap: [
    { label: 'הכל', value: '' },
    { label: 'Mega ($200B+)', value: 'mega' },
    { label: 'Large ($10–200B)', value: 'large' },
    { label: 'Mid ($2–10B)', value: 'mid' },
    { label: 'Small ($300M–2B)', value: 'small' },
    { label: 'Micro (<$300M)', value: 'micro' },
  ],
  health_score: [
    { label: 'הכל', value: '' },
    { label: '⭐ מצוין (>85)', value: 'health_excel' },
    { label: '✅ טוב (70–85)', value: 'health_good' },
    { label: '📊 בינוני (50–70)', value: 'health_fair' },
    { label: '⚠️ חלש (<50)', value: 'health_poor' },
  ],
  chg_30m: [
    { label: 'הכל', value: '' },
    { label: '🚀 >3% (חזק)', value: 'mom_strong' },
    { label: '📈 1–3%', value: 'mom_mid' },
    { label: '◆ -1% – 1%', value: 'mom_flat' },
    { label: '🔻 <-1%', value: 'mom_neg' },
  ],
  atr: [
    { label: 'Any',        value: '' },
    { label: 'Over 0.25',  value: 'o0.25' },
    { label: 'Over 0.5',   value: 'o0.5' },
    { label: 'Over 0.75',  value: 'o0.75' },
    { label: 'Over 1',     value: 'o1' },
    { label: 'Over 1.5',   value: 'o1.5' },
    { label: 'Over 2',     value: 'o2' },
    { label: 'Over 2.5',   value: 'o2.5' },
    { label: 'Over 3',     value: 'o3' },
    { label: 'Over 4',     value: 'o4' },
    { label: 'Over 5',     value: 'o5' },
    { label: 'Under 0.5',  value: 'u0.5' },
    { label: 'Under 1',    value: 'u1' },
    { label: 'Under 1.5',  value: 'u1.5' },
    { label: 'Under 2',    value: 'u2' },
    { label: 'Under 2.5',  value: 'u2.5' },
  ],
};

function SqueezeCell({ s }) {
  const stage = s.squeeze_stage || 'none';
  const score = s.squeeze_total_score || s.squeeze_score || 0;
  const meta  = SQUEEZE_META[stage] || SQUEEZE_META['none'];
  const entry = s.squeeze_entry || meta.entry || '';

  if (stage === 'none' || !meta.emoji) {
    return <span style={{ color: '#334155', fontSize: 10 }}>—</span>;
  }

  const dtc    = s.short_ratio   ? parseFloat(s.short_ratio)   : null;
  const sf     = s.short_float   ? parseFloat(s.short_float)   : null;
  const rvol   = s.rel_volume    ? parseFloat(s.rel_volume)     : null;
  const rot    = s.float_rotation != null ? parseFloat(s.float_rotation) : null;
  const hasCat = s.squeeze_has_catalyst;
  const catLbl = s.squeeze_catalyst || '';
  // Detect if catalyst came from memory (backend adds "לפני Xי" suffix)
  const catAgeMatch = catLbl.match(/לפני (\d+)י/);
  const catDaysAgo  = catAgeMatch ? parseInt(catAgeMatch[1]) : 0;
  const catIsMemory = catDaysAgo >= 1;
  const isCatalystSqueeze = hasCat && (stage === 'firing' || stage === 'compression');

  const chip = (val, color, title) => val != null && (
    <span title={title} style={{
      fontSize: 10, padding: '1px 6px', borderRadius: 4, whiteSpace: 'nowrap',
      color, background: `${color}18`, border: `1px solid ${color}55`, fontWeight: 700,
    }}>
      {val}
    </span>
  );

  const check = (ok, label) => (
    <span title={ok ? `${label} ✓` : `${label} ✗`} style={{
      fontSize: 10, padding: '1px 6px', borderRadius: 4, whiteSpace: 'nowrap',
      color: ok ? '#4ade80' : '#334155',
      background: ok ? 'rgba(74,222,128,0.12)' : 'transparent',
      border: `1px solid ${ok ? '#22c55e44' : '#1e293b'}`,
      fontWeight: 700,
    }}>
      {ok ? '✓' : '○'} {label}
    </span>
  );

  const tooltipText = entry ? `${meta.label}\n${entry}\n\n${catLbl || (hasCat ? 'יש קטליסט' : 'אין קטליסט')}` : meta.label;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4, padding: '3px 0' }}>

      {/* Catalyst + Squeeze combo banner — strongest setup */}
      {isCatalystSqueeze && (
        <div title={`🔥 שילוב קטליסט + לחץ שורט\n\nזהו השילוב החזק ביותר בשוק:\n• קטליסט (חדשות) → קונים חדשים\n• שורטיסטים לחוצים → קונים גם\n• מומנטום טריידרים → נכנסים\n\nשלושה כוחות קונים ביחד = לולאת האצה\n\n${catLbl || 'קטליסט פעיל'}`}
          style={{
            padding: '3px 8px', borderRadius: 6,
            background: 'linear-gradient(135deg, rgba(251,191,36,0.25), rgba(251,146,60,0.2))',
            border: '1px solid rgba(251,191,36,0.6)',
            display: 'flex', alignItems: 'center', gap: 4,
            cursor: 'help', boxShadow: '0 0 6px rgba(251,191,36,0.3)',
          }}>
          <span style={{ fontSize: 13 }}>🔥</span>
          <span style={{ fontSize: 10, fontWeight: 800, color: '#fbbf24', letterSpacing: '0.04em' }}>
            NEWS + SQUEEZE{catIsMemory ? ` · לפני ${catDaysAgo}י` : ''}
          </span>
        </div>
      )}

      {/* Row 1: Stage badge + score + catalyst indicator */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 5, flexWrap: 'nowrap' }}>
        <span title={tooltipText} style={{
          padding: '3px 8px', borderRadius: 10, fontSize: 11, fontWeight: 700,
          color: isCatalystSqueeze ? '#fbbf24' : meta.color,
          background: isCatalystSqueeze ? 'rgba(251,191,36,0.18)' : meta.bg,
          border: `1px solid ${isCatalystSqueeze ? 'rgba(251,191,36,0.7)' : meta.border}`,
          whiteSpace: 'nowrap', cursor: 'help',
        }}>
          {meta.emoji} {meta.label}
        </span>
        <span style={{ fontSize: 10, color: '#475569', fontWeight: 600 }}>{score}pt</span>
        {hasCat ? (
          <span title={catLbl || 'קטליסט פעיל'} style={{
            display: 'flex', alignItems: 'center', gap: 3,
            fontSize: 10, fontWeight: 700, cursor: 'help',
            padding: '1px 5px', borderRadius: 4,
            color: catIsMemory ? '#fb923c' : '#4ade80',
            background: catIsMemory ? 'rgba(251,146,60,0.12)' : 'rgba(74,222,128,0.1)',
            border: `1px solid ${catIsMemory ? 'rgba(251,146,60,0.4)' : 'rgba(74,222,128,0.3)'}`,
            whiteSpace: 'nowrap', maxWidth: 90, overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {catIsMemory ? `🕐 ${catDaysAgo}י` : '🎯'}
            {catLbl && !catIsMemory && (
              <span style={{ fontWeight: 500, color: '#86efac', fontSize: 9 }}>
                {catLbl.replace(/\(.*\)/, '').trim().slice(0, 14)}
              </span>
            )}
            {catIsMemory && (
              <span style={{ fontWeight: 500, fontSize: 9 }}>
                {catLbl.replace(/\(לפני.*\)/, '').trim().slice(0, 12)}
              </span>
            )}
          </span>
        ) : (
          <span style={{ fontSize: 10, color: '#334155' }}>·</span>
        )}
      </div>

      {/* Row 2: Short pressure chips */}
      <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
        {sf  != null && chip(`${sf.toFixed(0)}%`,          '#f87171', `Short Float: ${sf.toFixed(1)}%`)}
        {dtc != null && chip(`DTC ${dtc.toFixed(1)}d`,     dtc >= 4 ? '#fb923c' : '#64748b', `Days to Cover: ${dtc.toFixed(1)} ימים`)}
        {rvol!= null && chip(`×${rvol.toFixed(1)}`,        rvol >= 2 ? '#fde047' : '#64748b', `Relative Volume: ×${rvol.toFixed(1)}`)}
        {rot != null && chip(`↺${rot.toFixed(1)}x`,        '#a78bfa', `Float Rotation: ×${rot.toFixed(2)}`)}
      </div>

      {/* Row 3: Breakout checks inline */}
      <div style={{ display: 'flex', gap: 3 }}>
        {check(s.squeeze_above_vwap,       'VWAP')}
        {check(s.squeeze_near_hod,          'HOD')}
        {check(s.squeeze_above_resistance,  'R')}
      </div>
    </div>
  );
}

function PatternBadges({ patterns }) {
  if (!patterns || patterns.length === 0) return null;
  const PATTERN_DIR_COLOR = { bullish: '#4ade80', bearish: '#f87171', neutral: '#fde047' };
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2, marginTop: 4 }}>
      {patterns.map((p, i) => {
        const col = PATTERN_DIR_COLOR[p.direction] || '#94a3b8';
        return (
          <span key={i} title={`${p.name} | חוזק: ${p.strength} | ${p.vol_confirmed ? '✓ אושר בנפח' : 'ללא אישור נפח'}`}
            style={{
              fontSize: 9, padding: '1px 5px', borderRadius: 6, fontWeight: 600,
              color: col, background: `${col}18`, border: `1px solid ${col}44`,
              cursor: 'help', whiteSpace: 'nowrap',
            }}>
            {p.direction === 'bullish' ? '▲' : p.direction === 'bearish' ? '▼' : '◆'} {p.name.replace(/_/g,' ')}
            {p.vol_confirmed && <span style={{ marginLeft: 2, opacity: 0.7 }}>✓</span>}
          </span>
        );
      })}
    </div>
  );
}

// ── Mobile metric chip ──────────────────────────────────────────────────────
function MetricChip({ label, value, color }) {
  return (
    <span style={{
      fontSize: 10, fontWeight: 700, padding: '2px 6px', borderRadius: 4,
      color, background: `${color}18`, border: `1px solid ${color}44`,
      whiteSpace: 'nowrap',
    }}>
      {label} {value}
    </span>
  );
}

// ── Mobile stock card (used when screen width < 768px) ──────────────────────
function MobileStockCard({ s, livePrices, priceFlashes }) {
  const liveChgStr = livePrices[s.ticker]?.change_pct;
  const chg   = liveChgStr ? parseFloat(liveChgStr) : parseFloat(s.change_pct) || 0;
  const price = parseFloat(livePrices[s.ticker]?.price || s.price || 0);
  const stage = s.squeeze_stage || 'none';
  const meta  = SQUEEZE_META[stage] || SQUEEZE_META['none'];
  const isCatSq = s.squeeze_has_catalyst && (stage === 'firing' || stage === 'compression');
  const flash = priceFlashes[s.ticker];
  const sig   = (s.tech_signal || '').toLowerCase();
  const sigColor = sig.includes('strong buy') ? '#4ade80'
    : sig.includes('buy') ? '#86efac'
    : sig.includes('strong sell') ? '#f87171'
    : sig.includes('sell') ? '#fca5a5'
    : '#64748b';

  return (
    <div
      onClick={() => window.open(`https://finviz.com/quote.ashx?t=${s.ticker}`, '_blank')}
      style={{
        background: isCatSq
          ? 'linear-gradient(135deg, rgba(251,191,36,0.13), rgba(251,146,60,0.08))'
          : '#0f172a',
        border: `1px solid ${isCatSq ? 'rgba(251,191,36,0.55)' : 'rgba(30,41,59,0.9)'}`,
        borderRadius: 12,
        padding: '11px 12px',
        cursor: 'pointer',
        boxShadow: isCatSq ? '0 0 10px rgba(251,191,36,0.15)' : 'none',
        transition: 'transform 0.1s',
        WebkitTapHighlightColor: 'transparent',
      }}
    >
      {/* NEWS+SQUEEZE banner */}
      {isCatSq && (
        <div style={{ fontSize: 10, fontWeight: 800, color: '#fbbf24', marginBottom: 5, letterSpacing: '0.04em' }}>
          🔥 NEWS + SQUEEZE
        </div>
      )}

      {/* Top row: ticker / company / change */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 7 }}>
        <div>
          <span style={{ fontSize: 15, fontWeight: 800, color: '#f1f5f9', fontFamily: 'monospace' }}>{s.ticker}</span>
          <div style={{ fontSize: 10, color: '#475569', marginTop: 1, maxWidth: 100, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' }}>
            {s.company || ''}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: chg >= 0 ? '#4ade80' : '#f87171',
            animation: flash ? `flash-${flash} 0.6s ease` : 'none' }}>
            {chg >= 0 ? '+' : ''}{chg.toFixed(1)}%
          </div>
          <div style={{ fontSize: 11, color: '#94a3b8', marginTop: 1 }}>
            ${price.toFixed(price >= 100 ? 2 : price >= 10 ? 2 : 3)}
          </div>
        </div>
      </div>

      {/* Squeeze badge row */}
      {stage !== 'none' && meta.emoji && (
        <div style={{ display: 'flex', gap: 5, alignItems: 'center', marginBottom: 7 }}>
          <span style={{
            fontSize: 11, fontWeight: 700, padding: '2px 8px', borderRadius: 8,
            color: isCatSq ? '#fbbf24' : meta.color,
            background: isCatSq ? 'rgba(251,191,36,0.18)' : meta.bg,
            border: `1px solid ${isCatSq ? 'rgba(251,191,36,0.6)' : meta.border}`,
          }}>
            {meta.emoji} {meta.label}
          </span>
          <span style={{ fontSize: 10, color: '#475569' }}>{s.squeeze_total_score || 0}pt</span>
          {s.squeeze_has_catalyst && <span title={s.squeeze_catalyst || 'קטליסט'}>🎯</span>}
        </div>
      )}

      {/* Metrics chips */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 5 }}>
        {s.short_float  != null && <MetricChip label="Short" value={`${parseFloat(s.short_float).toFixed(0)}%`}   color="#f87171" />}
        {s.short_ratio  != null && <MetricChip label="DTC"   value={`${parseFloat(s.short_ratio).toFixed(1)}d`}   color="#fb923c" />}
        {s.rel_volume   != null && <MetricChip label="Vol"   value={`×${parseFloat(s.rel_volume).toFixed(1)}`}    color="#fde047" />}
        {s.rsi          != null && <MetricChip label="RSI"   value={parseFloat(s.rsi).toFixed(0)}
          color={parseFloat(s.rsi) > 70 ? '#f87171' : parseFloat(s.rsi) < 30 ? '#60a5fa' : '#94a3b8'} />}
        {s.float_rotation != null && <MetricChip label="Rot" value={`${parseFloat(s.float_rotation).toFixed(1)}x`} color="#a78bfa" />}
      </div>

      {/* Tech signal */}
      {s.tech_signal && (
        <div style={{ fontSize: 10, color: sigColor, fontWeight: 600 }}>
          {s.tech_signal}
          {s.tech_score != null && <span style={{ color: '#475569', marginLeft: 4 }}>({s.tech_score > 0 ? '+' : ''}{s.tech_score})</span>}
        </div>
      )}
    </div>
  );
}

function TechCell({ s }) {
  const signal = s.tech_signal;
  const score  = s.tech_score;
  if (!signal) return <span style={{ color: '#475569', fontSize: 10 }}>⏳</span>;

  const meta = TA_SIGNAL_META[signal] || TA_SIGNAL_META['Neutral'];
  const scoreColor = score > 30 ? '#4ade80' : score > 0 ? '#a3e635' : score > -30 ? '#fde047' : '#f87171';

  const ind   = s.tech_indicators || {};
  const rsi5m = ind.rsi_5m != null   ? Math.round(ind.rsi_5m)   : null;
  const rsi1h = ind.rsi_1h != null   ? Math.round(ind.rsi_1h)   : null;
  const vwap  = ind.vwap_bias || 'neutral';
  const macd  = ind.macd_hist_5m;
  const adx   = ind.adx_1h != null   ? Math.round(ind.adx_1h)  : null;
  const bbSq  = ind.bb_squeeze;

  const rsiColor = r => r >= 70 ? '#f87171' : r <= 30 ? '#4ade80' : r >= 60 ? '#fb923c' : r <= 40 ? '#a3e635' : '#94a3b8';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3, padding: '1px 0' }}>
      {/* Signal badge + score */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
        <span style={{
          fontSize: 10, padding: '2px 7px', borderRadius: 6, fontWeight: 800,
          background: meta.bg, border: `1px solid ${meta.border}`, color: meta.text,
          whiteSpace: 'nowrap', letterSpacing: '0.02em',
        }}>
          {meta.short} {meta.label}
        </span>
        <span style={{ fontSize: 10, fontFamily: 'monospace', fontWeight: 800, color: scoreColor }}>
          {score > 0 ? '+' : ''}{score}
        </span>
      </div>

      {/* Key indicators row */}
      <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap' }}>
        {rsi5m != null && (
          <span title={`RSI 5m: ${rsi5m}${rsi1h != null ? ' | RSI 1h: ' + rsi1h : ''}`} style={{
            fontSize: 10, padding: '1px 5px', borderRadius: 3, fontWeight: 700,
            color: rsiColor(rsi5m), background: '#0a1628', border: '1px solid #1e293b',
            whiteSpace: 'nowrap', cursor: 'help',
          }}>
            RSI {rsi5m}{rsi1h != null ? `·${rsi1h}` : ''}
          </span>
        )}
        <span title={`VWAP: ${vwap}`} style={{
          fontSize: 10, padding: '1px 5px', borderRadius: 3, fontWeight: 700,
          color: vwap === 'bullish' ? '#4ade80' : vwap === 'bearish' ? '#f87171' : '#475569',
          background: '#0a1628', border: '1px solid #1e293b', whiteSpace: 'nowrap',
        }}>
          VWAP {vwap === 'bullish' ? '↑' : vwap === 'bearish' ? '↓' : '—'}
        </span>
        {macd != null && (
          <span title={`MACD histogram: ${macd.toFixed(4)}`} style={{
            fontSize: 10, padding: '1px 5px', borderRadius: 3, fontWeight: 700,
            color: macd > 0 ? '#4ade80' : '#f87171',
            background: '#0a1628', border: '1px solid #1e293b', whiteSpace: 'nowrap',
          }}>
            MACD {macd > 0 ? '↑' : '↓'}
          </span>
        )}
        {adx != null && adx > 20 && (
          <span title={`ADX 1h: ${adx} — עוצמת מגמה`} style={{
            fontSize: 10, padding: '1px 5px', borderRadius: 3, fontWeight: 700,
            color: adx >= 40 ? '#f59e0b' : adx >= 25 ? '#fde047' : '#94a3b8',
            background: '#0a1628', border: '1px solid #1e293b', whiteSpace: 'nowrap',
          }}>
            ADX {adx}
          </span>
        )}
        {bbSq && (
          <span title="Bollinger Bands Squeeze — פריצה צפויה" style={{
            fontSize: 10, padding: '1px 5px', borderRadius: 3, fontWeight: 700,
            color: '#c084fc', background: '#0a1628', border: '1px solid #4c1d95',
          }}>
            💥BB
          </span>
        )}
      </div>
    </div>
  );
}

// ── Health Score badge ─────────────────────────────────────────────────────────
const HEALTH_TIERS = [
  { min: 80, emoji: '🟢', label: 'איכות גבוהה', bg: '#052e16', border: '#166534', text: '#4ade80' },
  { min: 60, emoji: '🟡', label: 'יציבה',        bg: '#1c1a00', border: '#854d0e', text: '#fde047' },
  { min: 40, emoji: '🟠', label: 'ספקולטיבית',  bg: '#1c0f00', border: '#9a3412', text: '#fb923c' },
  { min: 0,  emoji: '🔴', label: 'מסוכנת',       bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
];
function getHealthTier(score) {
  return HEALTH_TIERS.find(t => score >= t.min) || HEALTH_TIERS[3];
}

function HealthBadge({ score, detail }) {
  const [hover, setHover] = useState(false);
  const badgeRef = useRef(null);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  if (score == null) return <span style={{ color: '#94a3b8' }}>—</span>;
  const tier = getHealthTier(score);
  const handleEnter = () => {
    if (badgeRef.current) {
      const r = badgeRef.current.getBoundingClientRect();
      setPos({ top: r.bottom + 4, left: Math.max(4, r.right - 220) });
    }
    setHover(true);
  };
  return (
    <div
      ref={badgeRef}
      style={{ display: 'inline-flex' }}
      onMouseEnter={handleEnter}
      onMouseLeave={() => setHover(false)}
    >
      <div style={{
        display: 'inline-flex', alignItems: 'center', gap: 3,
        padding: '2px 6px', borderRadius: 6, cursor: 'help',
        background: tier.bg, border: `1px solid ${tier.border}`,
      }}>
        <span style={{ fontSize: 10 }}>{tier.emoji}</span>
        <span style={{ fontFamily: 'monospace', fontWeight: 900, fontSize: 12, color: tier.text }}>
          {score}
        </span>
      </div>
      {hover && detail?.length > 0 && ReactDOM.createPortal(
        <div onClick={e => e.stopPropagation()} onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)} style={{
          position: 'fixed', top: pos.top, left: pos.left, zIndex: 99999,
          padding: '8px 10px', borderRadius: 8,
          background: '#1e293b', border: '1px solid #334155',
          boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
          minWidth: 220, whiteSpace: 'nowrap',
        }}>
          <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 700, marginBottom: 4, letterSpacing: '0.05em' }}>
            פירוט ציון בריאות
          </div>
          {detail.map((d, i) => (
            <div key={i} style={{
              display: 'flex', justifyContent: 'space-between', gap: 12,
              fontSize: 11, lineHeight: 1.6,
              color: d.pts > 0 ? '#4ade80' : d.pts < 0 ? '#f87171' : '#94a3b8',
            }}>
              <span>{d.text}</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 700 }}>
                {d.pts > 0 ? '+' : ''}{d.pts}
              </span>
            </div>
          ))}
          <div style={{
            borderTop: '1px solid #334155', marginTop: 4, paddingTop: 4,
            display: 'flex', justifyContent: 'space-between',
            fontSize: 11, fontWeight: 700, color: tier.text,
          }}>
            <span>סה"כ</span>
            <span style={{ fontFamily: 'monospace' }}>{score}</span>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}

// ── Earnings Status mini-card ──────────────────────────────────────────────────
const VERDICT_META = {
  beat:   { label: '✅ הכה ציפיות', bg: '#052e16', border: '#166534', text: '#4ade80' },
  miss:   { label: '❌ פספס ציפיות', bg: '#2d0a0a', border: '#7f1d1d', text: '#f87171' },
  inline: { label: '〰️ בציפיות',   bg: '#1c1a00', border: '#854d0e', text: '#fde047' },
};

function ReasonBadge({ reason }) {
  const s = REASON_STYLE[reason.type] || REASON_STYLE.technical;
  return (
    <span style={{
      fontSize: 10, padding: '2px 7px', borderRadius: 4,
      background: s.bg, border: `1px solid ${s.border}`, color: s.text,
      whiteSpace: 'nowrap', display: 'inline-block', fontWeight: 600,
    }}>
      {reason.label}
    </span>
  );
}

const _sparklineBuster = Math.floor(Date.now() / 120000);
function Sparkline({ ticker, width = 220, height = 80 }) {
  const [loaded, setLoaded] = useState(false);
  const [err, setErr] = useState(false);
  const chartUrl = `https://finviz.com/chart.ashx?t=${ticker}&ty=c&ta=0&p=i&s=l&_=${_sparklineBuster}`;
  if (err) return <div style={{ width, height: 40, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#475569', fontSize: 10 }}>גרף לא זמין</div>;
  return (
    <img src={chartUrl} alt={`${ticker} chart`}
      style={{ width, height, objectFit: 'contain', borderRadius: 4, display: loaded ? 'block' : 'none' }}
      onLoad={() => setLoaded(true)} onError={() => setErr(true)} />
  );
}

function TagBadge({ tag }) {
  const m = TAG_META[tag];
  if (!m) return <span style={{ fontSize: 11, color: '#94a3b8' }}>{tag}</span>;
  return (
    <span style={{
      fontSize: 10, padding: '2px 6px', borderRadius: 4, fontWeight: 600,
      background: m.bg, border: `1px solid ${m.border}`, color: m.text,
      whiteSpace: 'nowrap', display: 'inline-block', lineHeight: 1.3,
    }}>
      {m.label}
    </span>
  );
}

// ── Earnings Status badge (compact — verdict only) ────────────────────────────
function EarningsBadge({ s }) {
  const verdict = s.earnings_verdict ? VERDICT_META[s.earnings_verdict] : null;
  if (!verdict) return null;
  return (
    <span style={{
      fontSize: 9, padding: '1px 5px', borderRadius: 4, fontWeight: 700,
      background: verdict.bg, border: `1px solid ${verdict.border}`, color: verdict.text,
      whiteSpace: 'nowrap', display: 'inline-block', marginTop: 2,
    }}>
      {verdict.label}
    </span>
  );
}

// ── Finviz-style inline filter ─────────────────────────────────────────────────
function fvSelectStyle(isActive) {
  return {
    fontSize: 11,
    padding: '4px 6px',
    borderRadius: 6,
    border: `1px solid ${isActive ? '#3b82f6' : '#1e293b'}`,
    background: isActive ? '#0a1628' : '#111c2d',
    color: isActive ? '#60a5fa' : '#94a3b8',
    outline: 'none',
    cursor: 'pointer',
    maxWidth: 160,
    minWidth: 80,
    fontFamily: 'inherit',
  };
}

const fvLabelStyle = (isActive) => ({
  fontSize: 11,
  color: isActive ? '#cbd5e1' : '#64748b',
  fontWeight: isActive ? 600 : 400,
  whiteSpace: 'nowrap',
  userSelect: 'none',
});

function FilterItem({ label, options, value, onChange }) {
  const isActive = value !== '' && value !== (options[0]?.value ?? '');
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
      <span style={fvLabelStyle(isActive)}>{label}</span>
      <select
        value={value}
        onChange={e => onChange(e.target.value)}
        style={fvSelectStyle(isActive)}
      >
        {options.map((o, i) => (
          <option key={o.value ? o.value + i : 'sep' + i} value={o.value} disabled={o.disabled}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

// for the custom % number input
const fvNumInput = {
  fontSize: 11,
  padding: '3px 5px',
  borderRadius: 3,
  border: '1px solid #3b82f6',
  background: '#0a1628',
  color: '#60a5fa',
  outline: 'none',
  width: 60,
  fontFamily: 'inherit',
};

function ColTooltip({ text }) {
  const [visible, setVisible] = useState(false);
  const [pos, setPos] = useState({ top: 0, left: 0 });
  const ref = useRef(null);
  const handleEnter = () => {
    if (ref.current) {
      const r = ref.current.getBoundingClientRect();
      setPos({ top: r.bottom + 4, left: Math.min(r.left, window.innerWidth - 280) });
    }
    setVisible(true);
  };
  return (
    <span
      ref={ref}
      onMouseEnter={handleEnter}
      onMouseLeave={() => setVisible(false)}
      style={{ display: 'inline-block', marginRight: 3, cursor: 'help', color: '#475569', fontSize: 10, lineHeight: 1 }}
    >
      ?
      {visible && ReactDOM.createPortal(
        <div style={{
          position: 'fixed',
          top: pos.top,
          left: pos.left,
          zIndex: 9999,
          background: '#0f172a',
          border: '1px solid #334155',
          borderRadius: 8,
          padding: '10px 13px',
          maxWidth: 270,
          boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
          pointerEvents: 'none',
          direction: 'rtl',
          textAlign: 'right',
        }}>
          {text.split('\n').map((line, i) => (
            <div key={i} style={{ fontSize: 12, color: line.startsWith('•') ? '#94a3b8' : '#e2e8f0', fontWeight: line.startsWith('•') ? 400 : (i === 0 ? 700 : 400), marginBottom: 3 }}>{line}</div>
          ))}
        </div>,
        document.body
      )}
    </span>
  );
}

function SortTh({ label, col, sort, onSort, sub, title, style: extraStyle,
                   filterOpts, filterValue, onFilter, filterOpen, onFilterOpen }) {
  const active = sort.col === col;
  const hasFilter = filterOpts && filterOpts.length > 0;
  const selectedArr = Array.isArray(filterValue) ? filterValue : (filterValue ? [filterValue] : []);
  const filterActive = selectedArr.length > 0;
  const filterTitle = filterActive
    ? (selectedArr.length === 1
        ? (filterOpts.find(o => o.value === selectedArr[0]) || {}).label || selectedArr[0]
        : `${selectedArr.length} אפשרויות`)
    : 'סנן עמודה (ניתן לבחור כמה)';

  return (
    <th style={{
      ...TH_BASE,
      textAlign: 'right',
      cursor: 'pointer',
      color: active ? '#93c5fd' : TH_BASE.color,
      background: active
        ? 'linear-gradient(180deg, #1e3a5f 0%, #0f172a 100%)'
        : filterActive
          ? 'linear-gradient(180deg, #1c1917 0%, #0c0a09 100%)'
          : TH_BASE.background,
      borderBottom: filterActive
        ? '2px solid rgba(251, 191, 36, 0.85)'
        : active ? '2px solid rgba(96, 165, 250, 0.7)' : TH_BASE.borderBottom,
      position: 'relative',
      ...extraStyle,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 4, justifyContent: 'space-between' }}>
        {/* Sort area */}
        <span
          onClick={() => onSort(col)}
          style={{ display: 'flex', alignItems: 'center', gap: 4, flex: 1, justifyContent: 'flex-end' }}
        >
          {title && <ColTooltip text={title} />}
          <span style={{ fontWeight: 600 }}>{label}</span>
          {active && <span style={{ fontSize: 11, color: '#93c5fd', opacity: 0.95 }}>{sort.dir === 'desc' ? '↓' : '↑'}</span>}
          {sub && <span style={{ fontSize: 10, color: '#64748b', fontWeight: 400 }}>{sub}</span>}
        </span>
        {/* Filter icon */}
        {hasFilter && (
          <button
            onClick={e => { e.stopPropagation(); onFilterOpen(filterOpen ? null : col); }}
            title={`${filterTitle}\nלחץ לפתיחה — ניתן לסמן כמה אפשרויות`}
            style={{
              width: 16, height: 16, borderRadius: 3, border: 'none', flexShrink: 0,
              background: filterActive ? 'rgba(251,191,36,0.3)' : 'rgba(71,85,105,0.3)',
              color: filterActive ? '#fbbf24' : '#64748b',
              cursor: 'pointer', fontSize: 9, padding: 0, lineHeight: 1,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              transition: 'all 0.15s ease',
            }}
          >
            {filterActive ? '●' : '▽'}
          </button>
        )}
      </div>

      {/* Filter dropdown — בחירה מורחבת (צ'קבוקסים), הדרופדאון נשאר פתוח עד סגירה */}
      {filterOpen && hasFilter && (
        <div
          style={{
            position: 'absolute', top: '100%', right: 0, zIndex: 2000,
            background: '#1e293b', border: '1px solid #334155', borderRadius: 8,
            boxShadow: '0 8px 24px rgba(0,0,0,0.6)',
            minWidth: 200, padding: '6px 0', maxHeight: 320, overflowY: 'auto',
          }}
          onClick={e => e.stopPropagation()}
        >
          <div style={{ padding: '4px 12px 6px', fontSize: 10, color: '#94a3b8', borderBottom: '1px solid #334155', marginBottom: 4 }}>
            בחר אחד או יותר (שורה עוברת אם מתאימה לאחד)
          </div>
          {filterOpts.map(opt => {
            const isAny = opt.value === '';
            const checked = isAny ? selectedArr.length === 0 : selectedArr.includes(opt.value);
            return (
              <div
                key={opt.value || 'any'}
                onClick={() => {
                  onFilter(col, opt.value);
                  if (isAny) onFilterOpen(null);
                }}
                style={{
                  padding: '6px 14px 6px 10px', fontSize: 11, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 8,
                  color: checked ? '#fbbf24' : '#e2e8f0',
                  background: checked ? 'rgba(251,191,36,0.15)' : 'transparent',
                  fontWeight: checked ? 700 : 400,
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => { if (!checked) e.currentTarget.style.background = 'rgba(255,255,255,0.06)'; }}
                onMouseLeave={e => { if (!checked) e.currentTarget.style.background = 'transparent'; }}
              >
                <span style={{
                  width: 14, height: 14, borderRadius: 3, flexShrink: 0,
                  border: `2px solid ${checked ? '#fbbf24' : '#64748b'}`,
                  background: checked ? '#fbbf24' : 'transparent',
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 9,
                }}>
                  {checked && '✓'}
                </span>
                {opt.label}
              </div>
            );
          })}
        </div>
      )}
    </th>
  );
}

// ── Auto analysis builder ──────────────────────────────────────────────────────
const _REASON_COLORS = {
  earnings: '#4ade80', upgrade: '#60a5fa', downgrade: '#f87171',
  fda: '#c084fc', ma: '#fb923c', guidance: '#22d3ee',
  contract: '#fbbf24', risk: '#f87171', gap: '#86efac', technical: '#9ca3af',
  dilution: '#fb7185', insider: '#a78bfa', split: '#38bdf8',
  dividend: '#34d399', ai_sector: '#818cf8', volume_spike: '#fcd34d',
};

function buildAnalysis(s) {
  const chg    = parseFloat(s.extended_chg_pct ?? s.change_pct ?? 0);
  const rsi    = parseFloat(s.rsi);
  const shortF = parseFloat(s.short_float);
  const eps    = parseFloat(s.eps_qq);
  const sales  = parseFloat(s.sales_qq);
  const score  = s.health_score ?? 50;

  const movePoints = (s.reasons || []).map(r => {
    let text = r.label;
    const src = r.source ? ` (${r.source})` : '';
    if (r.type === 'earnings') {
      const v = s.earnings_verdict === 'beat' ? ' — הכה ציפיות' : s.earnings_verdict === 'miss' ? ' — פספסה ציפיות' : '';
      const e = !isNaN(eps)   ? ` | EPS ${eps > 0 ? '+' : ''}${eps.toFixed(1)}%`   : '';
      const sv= !isNaN(sales) ? ` | מכירות ${sales > 0 ? '+' : ''}${sales.toFixed(1)}%` : '';
      text = `📊 דוחות${v}${e}${sv}`;
    } else if (r.type === 'upgrade') {
      text = `⬆️ שדרוג${s.analyst_recom ? ` — ${RECOM_HE[s.analyst_recom] || s.analyst_recom}` : ''}${s.target_price ? ` | יעד $${s.target_price}` : ''}`;
    } else {
      text = text + src;
    }
    return { text, color: _REASON_COLORS[r.type] || '#94a3b8' };
  });

  // ── Strengths ──
  const strengths = [];
  if (s.tags?.includes('profitable')) strengths.push('חברה רווחית — הכנסה נטו חיובית');
  if (s.tags?.includes('cash_rich'))  strengths.push('עתירת מזומנים — סיכון פיננסי נמוך (EV ≈ Market Cap)');
  if (s.tags?.includes('high_growth')) strengths.push(`צמיחת הכנסות${!isNaN(sales) ? ` +${sales.toFixed(0)}% Q/Q` : ' גבוהה'} — שוק מתמחר עתיד`);
  if (s.earnings_verdict === 'beat')  strengths.push(`הכה ציפיות האנליסטים${!isNaN(eps) ? ` (EPS Q/Q: +${eps.toFixed(1)}%)` : ''}`);
  if (!isNaN(rsi) && rsi >= 50 && rsi < 70) strengths.push(`מומנטום חיובי — RSI ${rsi.toFixed(0)}`);
  if (!isNaN(shortF) && shortF < 5)  strengths.push(`שורט נמוך (${shortF.toFixed(1)}%) — לחץ מכירה מוגבל`);
  if (['Buy','Strong Buy','Outperform','Overweight'].includes(s.analyst_recom))
    strengths.push(`אנליסטים: ${RECOM_HE[s.analyst_recom]}${s.target_price ? ` | יעד $${s.target_price}` : ''}`);

  // ── Risks ──
  const risks = [];
  if (s.tags?.includes('loss'))      risks.push('הפסד נקי — החברה עדיין לא רווחית');
  if (s.tags?.includes('high_debt')) risks.push('חוב גבוה — עלות ריבית עלולה להכביד על הרווחיות');
  if (s.tags?.includes('high_short')) risks.push(`שורט גבוה (${s.short_float}) — לחץ מכירה אפשרי`);
  if (s.earnings_verdict === 'miss') risks.push('פספסה ציפיות האנליסטים ברבעון האחרון');
  if (!isNaN(rsi) && rsi > 72)       risks.push(`RSI גבוה (${rsi.toFixed(0)}) — קנוי יתר, סיכון לתיקון`);
  if (!isNaN(shortF) && shortF > 20) risks.push(`שורט גבוה מאוד (${shortF.toFixed(0)}%) — תנודתיות גבוהה`);

  // ── Conclusion ──
  let conclusion = '';
  const tier = score >= 80 ? 'top' : score >= 60 ? 'good' : score >= 40 ? 'spec' : 'risky';
  if      (tier === 'top'  && chg >= 5)  conclusion = 'מניה חזקה עם בסיס איכותי ומומנטום גבוה — ראויה לתשומת לב. לבדוק נזילות ונקודת כניסה.';
  else if (tier === 'top')               conclusion = 'חברה איכותית — ציון בריאות גבוה. מחכה לטריגר טכני לכניסה.';
  else if (tier === 'good' && chg >= 3)  conclusion = 'חברה יציבה עם תנועה חיובית — כדאי לעקוב אחרי המשך.';
  else if (tier === 'spec' && strengths.length >= risks.length)
    conclusion = 'מניה ספקולטיבית אך עם עוצמה — שקול כניסה קטנה עם stop מוגדר.';
  else if (tier === 'spec')              conclusion = 'מניה ספקולטיבית — פוטנציאל גבוה, אבל הסיכונים משמעותיים. גודל פוזיציה קטן.';
  else                                   conclusion = 'מניה בסיכון גבוה — נדרשת זהירות. לא לכניסה ללא catalyst ברור.';

  return { movePoints, strengths, risks, conclusion };
}

// ── Rich expand row ────────────────────────────────────────────────────────────
function ExpandRow({ s, colSpan }) {
  const fmtTs = (ts) => {
    if (!ts) return '';
    const d = new Date(ts * 1000);
    return d.toLocaleDateString('he-IL', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  };

  const epsVal   = parseFloat(s.eps_qq);
  const salesVal = parseFloat(s.sales_qq);
  const hasEps   = !isNaN(epsVal);
  const hasSales = !isNaN(salesVal);
  const verdict  = s.earnings_verdict
    ? { beat: { label: '✅ הכה ציפיות', color: '#4ade80' }, miss: { label: '❌ פספס ציפיות', color: '#f87171' }, inline: { label: '〰️ בציפיות', color: '#fde047' } }[s.earnings_verdict]
    : null;

  const analysis = buildAnalysis(s);

  return (
    <tr>
      <td colSpan={colSpan} style={{ padding: '0', background: '#060c18', borderBottom: '2px solid #1e3a5f' }}>
        <div style={{ display: 'flex', gap: 0, borderTop: '1px solid #1e293b' }}>

          {/* ── Col 1: Stock Analysis ── */}
          <div style={{ flex: '0 0 340px', padding: '14px 16px', borderLeft: '1px solid #1e293b' }}>

            {/* Header: ticker + sector */}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 10 }}>
              <span style={{ fontSize: 13, fontWeight: 900, color: '#f8fafc' }}>📌 {s.ticker}</span>
              {s.sector && (
                <span style={{ fontSize: 10, color: '#64748b' }}>
                  {SECTOR_HE[s.sector] || s.sector}{s.industry ? ` · ${INDUSTRY_HE[s.industry] || s.industry}` : ''}
                </span>
              )}
            </div>

            {/* Business summary */}
            {s.business_summary && (
              <p style={{
                fontSize: 11, color: '#94a3b8', margin: '0 0 10px 0', lineHeight: 1.55,
                borderRight: '2px solid #1e3a5f', paddingRight: 8,
              }}>
                {s.business_summary}
              </p>
            )}

            {/* Why it moved */}
            {analysis.movePoints.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 700, marginBottom: 5, letterSpacing: '0.05em' }}>
                  🔍 למה זזה
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                  {analysis.movePoints.map((p, i) => {
                    const conf = (s.reasons || [])[i]?.confidence;
                    const confColor = conf === 'high' ? '#4ade80' : conf === 'medium' ? '#fbbf24' : '#64748b';
                    return (
                      <div key={i} style={{ display: 'flex', gap: 7, alignItems: 'flex-start' }}>
                        <span style={{ color: p.color, fontSize: 10, marginTop: 1, flexShrink: 0 }}>◆</span>
                        <span style={{ fontSize: 11, color: p.color, fontWeight: 600, lineHeight: 1.4 }}>{p.text}</span>
                        {conf && <span style={{ fontSize: 8, color: confColor, border: `1px solid ${confColor}`, borderRadius: 3, padding: '0 3px', lineHeight: '14px', flexShrink: 0 }}>{conf === 'high' ? 'HIGH' : conf === 'medium' ? 'MED' : 'LOW'}</span>}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Strengths */}
            {analysis.strengths.length > 0 && (
              <div style={{ marginBottom: 8 }}>
                <div style={{ fontSize: 10, color: '#4ade80', fontWeight: 700, marginBottom: 4 }}>✅ נקודות חוזק</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {analysis.strengths.map((t, i) => (
                    <div key={i} style={{ fontSize: 11, color: '#94a3b8', display: 'flex', gap: 6 }}>
                      <span style={{ color: '#4ade80', flexShrink: 0 }}>+</span>{t}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Risks */}
            {analysis.risks.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{ fontSize: 10, color: '#f87171', fontWeight: 700, marginBottom: 4 }}>⚠️ נקודות סיכון</div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
                  {analysis.risks.map((t, i) => (
                    <div key={i} style={{ fontSize: 11, color: '#94a3b8', display: 'flex', gap: 6 }}>
                      <span style={{ color: '#f87171', flexShrink: 0 }}>−</span>{t}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Conclusion */}
            <div style={{
              fontSize: 11, color: '#e2e8f0', lineHeight: 1.5,
              background: '#0a1628', border: '1px solid #1e3a5f',
              borderRadius: 8, padding: '8px 10px',
            }}>
              <span style={{ color: '#60a5fa', fontWeight: 700 }}>💡 מסקנה: </span>
              {analysis.conclusion}
            </div>

            {/* Analyst rec */}
            {(s.analyst_recom || s.target_price) && (
              <div style={{ marginTop: 8, display: 'flex', gap: 12, fontSize: 10, color: '#64748b' }}>
                {s.analyst_recom && <span>👥 {RECOM_HE[s.analyst_recom] || s.analyst_recom}</span>}
                {s.target_price  && <span>🎯 יעד: <span style={{ color: '#60a5fa', fontWeight: 700 }}>${s.target_price}</span></span>}
              </div>
            )}
          </div>

          {/* ── Col 2: Earnings + Growth + Intraday ── */}
          <div style={{ flex: '0 0 220px', padding: '12px 14px', borderLeft: '1px solid #1e293b' }}>
            <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 700, marginBottom: 8, letterSpacing: '0.05em' }}>
              📊 דוחות
            </div>
            {(verdict || hasEps || hasSales || s.earnings_date) ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {verdict && (
                  <span style={{ fontSize: 12, color: verdict.color, fontWeight: 700 }}>
                    {verdict.label}
                  </span>
                )}
                {hasEps && (
                  <div style={{ fontSize: 11, fontFamily: 'monospace', color: epsVal > 0 ? '#4ade80' : '#f87171' }}>
                    EPS רבעוני: {epsVal > 0 ? '+' : ''}{epsVal.toFixed(1)}%
                  </div>
                )}
                {hasSales && (
                  <div style={{ fontSize: 11, fontFamily: 'monospace', color: salesVal > 0 ? '#4ade80' : '#f87171' }}>
                    הכנסות Q/Q: {salesVal > 0 ? '+' : ''}{salesVal.toFixed(1)}%
                  </div>
                )}
                {s.earnings_date && (
                  <div style={{ fontSize: 10, color: '#94a3b8', marginTop: 3 }}>
                    📅 דוח הבא: <span style={{ color: '#94a3b8' }}>{fmtEarningsDate(s.earnings_date)}</span>
                  </div>
                )}
                {(s.perf_week || s.perf_month) && (
                  <div style={{ marginTop: 5, display: 'flex', gap: 8 }}>
                    {s.perf_week && (
                      <div style={{ fontSize: 10 }}>
                        <span style={{ color: '#94a3b8' }}>7י׳ </span>
                        <span style={{ color: parseFloat(s.perf_week) > 0 ? '#4ade80' : '#f87171', fontFamily: 'monospace', fontWeight: 700 }}>{s.perf_week}</span>
                      </div>
                    )}
                    {s.perf_month && (
                      <div style={{ fontSize: 10 }}>
                        <span style={{ color: '#94a3b8' }}>30י׳ </span>
                        <span style={{ color: parseFloat(s.perf_month) > 0 ? '#4ade80' : '#f87171', fontFamily: 'monospace', fontWeight: 700 }}>{s.perf_month}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <span style={{ fontSize: 11, color: '#94a3b8' }}>אין נתוני דוחות</span>
            )}

            {/* Growth section — EPS Y, EPS Q, S Q/Q */}
            {(s.eps_this_y || s.eps_qq || s.sales_qq) && (
              <div style={{ marginTop: 12, borderTop: '1px solid #1e293b', paddingTop: 8 }}>
                <div style={{ fontSize: 10, color: '#a78bfa', fontWeight: 700, marginBottom: 6, letterSpacing: '0.05em' }}>
                  📈 צמיחה
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '4px 10px', fontSize: 10 }}>
                  {s.eps_this_y && (() => { const v = parseFloat(s.eps_this_y); return (
                    <span style={{ color: '#94a3b8' }}>EPS שנתי: <b style={{ color: v > 0 ? '#4ade80' : '#f87171', fontFamily: 'monospace' }}>{v > 0 ? '+' : ''}{v.toFixed(1)}%</b></span>
                  ); })()}
                  {s.eps_qq && (() => { const v = parseFloat(s.eps_qq); return (
                    <span style={{ color: '#94a3b8' }}>EPS רבעוני: <b style={{ color: v > 0 ? '#4ade80' : '#f87171', fontFamily: 'monospace' }}>{v > 0 ? '+' : ''}{v.toFixed(1)}%</b></span>
                  ); })()}
                  {s.sales_qq && (() => { const v = parseFloat(s.sales_qq); return (
                    <span style={{ color: '#94a3b8' }}>מכירות Q/Q: <b style={{ color: v > 0 ? '#4ade80' : '#f87171', fontFamily: 'monospace' }}>{v > 0 ? '+' : ''}{v.toFixed(1)}%</b></span>
                  ); })()}
                </div>
              </div>
            )}

            {/* Valuation section — P/E, EV, EV/MC, Cash/sh, Book/sh */}
            {(s.ev || s.ev_mc_ratio || s.cash_per_share || s.book_per_share || s.pe || s.forward_pe || s.beta) && (
              <div style={{ marginTop: 10, borderTop: '1px solid #1e293b', paddingTop: 8 }}>
                <div style={{ fontSize: 10, color: '#38bdf8', fontWeight: 700, marginBottom: 6, letterSpacing: '0.05em' }}>
                  💰 שווי
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '3px 10px', fontSize: 10 }}>
                  {s.pe && s.pe !== '-' && (() => {
                    const v = parseFloat(s.pe);
                    if (isNaN(v)) return null;
                    const c = v > 0 && v < 15 ? '#4ade80' : v > 0 && v < 25 ? '#fde047' : v > 50 ? '#f87171' : '#e2e8f0';
                    return <span style={{ color: '#94a3b8' }}>P/E: <b style={{ color: c, fontFamily: 'monospace' }}>{v.toFixed(1)}</b></span>;
                  })()}
                  {s.forward_pe && s.forward_pe !== '-' && (() => {
                    const v = parseFloat(s.forward_pe);
                    if (isNaN(v)) return null;
                    const c = v > 0 && v < 15 ? '#4ade80' : v > 0 && v < 25 ? '#fde047' : v > 50 ? '#f87171' : '#94a3b8';
                    return <span style={{ color: '#94a3b8' }}>P/E fwd: <b style={{ color: c, fontFamily: 'monospace' }}>{v.toFixed(1)}</b></span>;
                  })()}
                  {s.beta && (() => {
                    const v = parseFloat(s.beta);
                    if (isNaN(v)) return null;
                    const c = v > 2 ? '#f87171' : v > 1.5 ? '#fde047' : '#94a3b8';
                    return <span style={{ color: '#94a3b8' }}>Beta: <b style={{ color: c, fontFamily: 'monospace' }}>{v.toFixed(2)}</b></span>;
                  })()}
                  {s.ev && (
                    <span style={{ color: '#94a3b8' }}>EV: <b style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{s.ev_str || s.enterprise_value || '—'}</b></span>
                  )}
                  {s.ev_mc_ratio && (() => {
                    const r = parseFloat(s.ev_mc_ratio);
                    if (isNaN(r)) return null;
                    const c = r < 1.0 ? '#4ade80' : r > 1.5 ? '#f87171' : r > 1.1 ? '#fde047' : '#e2e8f0';
                    const label = r < 1.0 ? ' 💥' : '';
                    return <span style={{ color: '#94a3b8' }}>EV/MC: <b style={{ color: c, fontFamily: 'monospace' }}>{r.toFixed(2)}x{label}</b></span>;
                  })()}
                  {s.cash_per_share && (() => {
                    const cash = parseFloat(s.cash_per_share);
                    const price = parseFloat(s.price);
                    if (isNaN(cash) || cash <= 0) return null;
                    const ratio = price > 0 ? cash / price : 0;
                    const c = ratio >= 0.5 ? '#fbbf24' : ratio >= 0.3 ? '#f59e0b' : '#94a3b8';
                    const label = ratio >= 0.5 ? ' 💥' : ratio >= 0.3 ? ' ✓' : '';
                    return <span style={{ color: '#94a3b8' }}>Cash/sh: <b style={{ color: c, fontFamily: 'monospace' }}>${cash.toFixed(2)}{label && <span style={{ fontSize: 9 }}>{label}</span>}</b></span>;
                  })()}
                  {s.book_per_share && (() => {
                    const book = parseFloat(s.book_per_share);
                    const price = parseFloat(s.price);
                    if (isNaN(book) || book <= 0) return null;
                    const belowBook = price < book;
                    const disc = belowBook ? ((book - price) / book * 100).toFixed(0) : null;
                    const c = belowBook ? '#a78bfa' : '#94a3b8';
                    const label = belowBook ? ` 💎 -${disc}%` : '';
                    return <span style={{ color: '#94a3b8' }}>Book/sh: <b style={{ color: c, fontFamily: 'monospace' }}>${book.toFixed(2)}{label && <span style={{ fontSize: 9 }}>{label}</span>}</b></span>;
                  })()}
                </div>
              </div>
            )}

            {/* Intraday section — 5m, 10m, 30m */}
            {(s.chg_5m || s.chg_10m || s.chg_30m) && (
              <div style={{ marginTop: 10, borderTop: '1px solid #1e293b', paddingTop: 8 }}>
                <div style={{ fontSize: 10, color: '#f59e0b', fontWeight: 700, marginBottom: 6, letterSpacing: '0.05em' }}>
                  ⏱ תנועה תוך-יומית
                </div>
                <div style={{ display: 'flex', gap: 10, fontSize: 10 }}>
                  {[{ label: '5דק', val: s.chg_5m }, { label: '10דק', val: s.chg_10m }, { label: '30דק', val: s.chg_30m }].map(item => {
                    if (!item.val) return null;
                    const v = parseFloat(item.val);
                    return (
                      <div key={item.label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                        <span style={{ color: '#64748b', fontSize: 9 }}>{item.label}</span>
                        <span style={{ fontFamily: 'monospace', fontWeight: 700, fontSize: 11, color: v > 0 ? '#4ade80' : v < 0 ? '#f87171' : '#94a3b8' }}>
                          {v > 0 ? '+' : ''}{v.toFixed(1)}%
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>

          {/* ── Col 3: Technical Analysis ── */}
          {s.tech_signal ? (
            <div style={{ flex: '0 0 270px', padding: '12px 14px', borderLeft: '1px solid #1e293b' }}>
              <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 700, marginBottom: 8, letterSpacing: '0.05em' }}>
                📊 ניתוח טכני
              </div>
              {/* Signal + Score + Momentum Bar */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                {(() => {
                  const meta = TA_SIGNAL_META[s.tech_signal] || TA_SIGNAL_META['Neutral'];
                  return (
                    <span style={{
                      fontSize: 12, padding: '4px 10px', borderRadius: 6, fontWeight: 800,
                      background: meta.bg, border: `1px solid ${meta.border}`, color: meta.text,
                    }}>
                      {meta.short} {meta.label}
                    </span>
                  );
                })()}
                <span style={{
                  fontSize: 14, fontFamily: 'monospace', fontWeight: 900,
                  color: s.tech_score > 30 ? '#4ade80' : s.tech_score > 0 ? '#a3e635' : s.tech_score > -30 ? '#fde047' : '#f87171',
                }}>
                  {s.tech_score > 0 ? '+' : ''}{s.tech_score}
                </span>
              </div>

              {/* Momentum strength bar */}
              <div style={{ marginBottom: 10 }}>
                <div style={{
                  height: 6, borderRadius: 3, background: '#1e293b', position: 'relative', overflow: 'hidden',
                }}>
                  <div style={{
                    position: 'absolute',
                    left: '50%',
                    width: `${Math.abs(s.tech_score) / 2}%`,
                    height: '100%',
                    borderRadius: 3,
                    background: s.tech_score > 0
                      ? `linear-gradient(90deg, #22c55e, ${s.tech_score > 50 ? '#4ade80' : '#a3e635'})`
                      : `linear-gradient(270deg, #ef4444, ${s.tech_score < -50 ? '#f87171' : '#fbbf24'})`,
                    transform: s.tech_score < 0 ? 'translateX(-100%)' : 'none',
                    transition: 'width 0.3s ease',
                  }} />
                  <div style={{
                    position: 'absolute', left: '50%', top: 0, bottom: 0, width: 2,
                    background: '#475569', transform: 'translateX(-1px)',
                  }} />
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 8, color: '#475569', marginTop: 2 }}>
                  <span>-100</span><span>0</span><span>+100</span>
                </div>
              </div>

              {/* UP / DOWN timing — always visible */}
              <div style={{ display: 'flex', gap: 6, marginBottom: 10 }}>
                <div style={{
                  flex: 1, background: '#052e16', border: '1px solid #166534',
                  borderRadius: 6, padding: '6px 8px', textAlign: 'center',
                }}>
                  <div style={{ fontSize: 9, color: '#4ade80', fontWeight: 700, marginBottom: 3 }}>📈 צפי עלייה</div>
                  <div style={{ fontSize: 12, color: '#4ade80', fontFamily: 'monospace', fontWeight: 800 }}>
                    {extractTime(s.tech_timing_up) || '—'}
                  </div>
                  {s.tech_timing_up_desc && (
                    <div style={{ fontSize: 8, color: '#86efac', marginTop: 2, lineHeight: 1.3 }}>{s.tech_timing_up_desc}</div>
                  )}
                  {s.tech_timing_up_conf && (
                    <div style={{ fontSize: 8, color: '#22c55e', marginTop: 1, fontWeight: 600 }}>{s.tech_timing_up_conf}</div>
                  )}
                </div>
                <div style={{
                  flex: 1, background: '#2d0a0a', border: '1px solid #7f1d1d',
                  borderRadius: 6, padding: '6px 8px', textAlign: 'center',
                }}>
                  <div style={{ fontSize: 9, color: '#f87171', fontWeight: 700, marginBottom: 3 }}>📉 צפי ירידה</div>
                  <div style={{ fontSize: 12, color: '#f87171', fontFamily: 'monospace', fontWeight: 800 }}>
                    {extractTime(s.tech_timing_down) || '—'}
                  </div>
                  {s.tech_timing_down_desc && (
                    <div style={{ fontSize: 8, color: '#fca5a5', marginTop: 2, lineHeight: 1.3 }}>{s.tech_timing_down_desc}</div>
                  )}
                  {s.tech_timing_down_conf && (
                    <div style={{ fontSize: 8, color: '#ef4444', marginTop: 1, fontWeight: 600 }}>{s.tech_timing_down_conf}</div>
                  )}
                </div>
              </div>

              {/* Support / Resistance */}
              {(s.tech_support || s.tech_resistance) && (
                <div style={{
                  display: 'flex', gap: 10, marginBottom: 8, fontSize: 10,
                  background: '#0a1628', borderRadius: 4, padding: '5px 8px',
                }}>
                  {s.tech_support && (
                    <span style={{ color: '#4ade80' }}>
                      תמיכה: <b style={{ fontFamily: 'monospace' }}>${s.tech_support}</b>
                    </span>
                  )}
                  {s.tech_resistance && (
                    <span style={{ color: '#f87171' }}>
                      התנגדות: <b style={{ fontFamily: 'monospace' }}>${s.tech_resistance}</b>
                    </span>
                  )}
                </div>
              )}

              {/* Indicator breakdown */}
              {s.tech_detail && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 3, marginBottom: 8 }}>
                  {s.tech_detail.split(' | ').map((part, i) => (
                    <div key={i} style={{ fontSize: 10, color: '#94a3b8', display: 'flex', gap: 4 }}>
                      <span style={{ color: '#60a5fa', flexShrink: 0 }}>●</span>
                      <span>{part}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Squeeze Scorecard */}
              {s.squeeze_stage && s.squeeze_stage !== 'none' && (() => {
                const sqMeta = SQUEEZE_META[s.squeeze_stage] || SQUEEZE_META['none'];
                const totalScore = s.squeeze_total_score || 0;
                const dtcVal = s.short_ratio ? parseFloat(s.short_ratio) : null;
                const dtcComputed = !s.short_ratio && s.short_interest;

                // Score bar segments: each criterion contributes a visual block
                const criteria = [
                  { label: '🩳 Short Float', value: s.short_float ? `${parseFloat(s.short_float).toFixed(0)}%` : null, color: '#f87171', active: parseFloat(s.short_float||0) >= 10 },
                  { label: `DTC${dtcComputed ? ' *' : ''}`, value: dtcVal != null ? `${dtcVal.toFixed(1)}d` : null, color: '#fb923c', active: dtcVal != null && dtcVal >= 2 },
                  { label: 'RVol', value: s.rel_volume ? `×${parseFloat(s.rel_volume).toFixed(1)}` : null, color: '#fde047', active: parseFloat(s.rel_volume||0) >= 1.5 },
                  { label: '🔄 Rotation', value: s.float_rotation != null ? `×${parseFloat(s.float_rotation).toFixed(2)}` : null, color: '#a78bfa', active: s.float_rotation != null && s.float_rotation >= 0.3 },
                ];

                return (
                  <div style={{ marginBottom: 8, background: '#061220', borderRadius: 7, padding: '7px 8px', border: `1px solid ${sqMeta.border}40` }}>
                    {/* Header row */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 5 }}>
                      <span style={{ fontSize: 9, color: '#64748b', fontWeight: 700, letterSpacing: '0.06em' }}>🩳 SHORT SQUEEZE</span>
                      <span style={{ fontSize: 9, color: sqMeta.color, fontWeight: 700 }}>ציון {totalScore}</span>
                    </div>

                    {/* Stage + entry */}
                    <div style={{ marginBottom: 5 }}>
                      <SqueezeCell s={s} />
                    </div>

                    {/* ── Criterion 1: Short Pressure ── */}
                    <div style={{ fontSize: 8, color: '#475569', fontWeight: 700, marginBottom: 3, letterSpacing: '0.05em' }}>
                      לחץ שורטים (כמה + כמה קשה לצאת)
                    </div>
                    <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 6 }}>
                      {criteria.map((c, i) => c.value && (
                        <span key={i} style={{
                          fontSize: 8, padding: '1px 5px', borderRadius: 4, whiteSpace: 'nowrap',
                          color: c.active ? c.color : '#475569',
                          background: c.active ? `${c.color}12` : '#0a1628',
                          border: `1px solid ${c.active ? c.color + '44' : '#1e293b'}`,
                          fontWeight: c.active ? 700 : 400,
                        }}>
                          {c.label} {c.value}
                        </span>
                      ))}
                      {dtcComputed && <span style={{ fontSize: 7, color: '#475569', alignSelf: 'center' }}>* מחושב</span>}
                    </div>

                    {/* ── Criterion 2: Catalyst ── */}
                    <div style={{ fontSize: 8, color: '#475569', fontWeight: 700, marginBottom: 3, letterSpacing: '0.05em' }}>
                      קטליסט (למה עכשיו?)
                    </div>
                    <div style={{
                      marginBottom: 6, padding: '3px 6px', borderRadius: 5,
                      background: s.squeeze_has_catalyst ? 'rgba(74,222,128,0.07)' : 'rgba(239,68,68,0.07)',
                      border: `1px solid ${s.squeeze_has_catalyst ? '#16653488' : '#7f1d1d88'}`,
                      fontSize: 9, color: s.squeeze_has_catalyst ? '#4ade80' : '#f87171', fontWeight: 600,
                    }}>
                      {s.squeeze_catalyst || '⚠️ אין קטליסט ברור'}
                    </div>

                    {/* ── Criterion 3: Breakout Confirmation ── */}
                    <div style={{ fontSize: 8, color: '#475569', fontWeight: 700, marginBottom: 3, letterSpacing: '0.05em' }}>
                      אישור פריצה (מבנה מחיר)
                    </div>
                    <div style={{ display: 'flex', gap: 4, marginBottom: 5 }}>
                      {[
                        { ok: s.squeeze_above_vwap,      label: 'VWAP',    tip: 'מעל VWAP' },
                        { ok: s.squeeze_near_hod,         label: 'HOD',     tip: 'שיא יומי' },
                        { ok: s.squeeze_above_resistance, label: 'התנגדות', tip: 'פריצת התנגדות' },
                      ].map((c, i) => (
                        <span key={i} title={c.tip} style={{
                          fontSize: 8, padding: '2px 6px', borderRadius: 4, fontWeight: 700,
                          color: c.ok ? '#4ade80' : '#64748b',
                          background: c.ok ? 'rgba(74,222,128,0.1)' : '#0a1628',
                          border: `1px solid ${c.ok ? '#22c55e55' : '#1e293b'}`,
                        }}>
                          {c.ok ? '✅' : '○'} {c.label}
                        </span>
                      ))}
                    </div>

                    {/* Squeeze signals */}
                    {(s.squeeze_signals || []).length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 2, borderTop: '1px solid #1e293b', paddingTop: 4 }}>
                        {s.squeeze_signals.slice(0, 6).map((sig, i) => (
                          <span key={i} style={{ fontSize: 7.5, color: '#64748b', background: '#0a1628', borderRadius: 3, padding: '1px 4px' }}>{sig}</span>
                        ))}
                      </div>
                    )}
                  </div>
                );
              })()}

              {/* Candlestick patterns */}
              {(s.tech_patterns_detail?.length > 0 || s.tech_patterns) && (
                <div style={{ marginBottom: 4 }}>
                  <div style={{ fontSize: 9, color: '#64748b', fontWeight: 700, marginBottom: 3 }}>🕯 פטרני נרות</div>
                  <PatternBadges patterns={s.tech_patterns_detail} />
                  {(!s.tech_patterns_detail?.length && s.tech_patterns) && (
                    <div style={{ fontSize: 10, color: '#fde047' }}>{s.tech_patterns}</div>
                  )}
                </div>
              )}

              {/* Key indicators mini-grid */}
              {s.tech_indicators && (
                <div style={{
                  display: 'grid', gridTemplateColumns: '1fr 1fr',
                  gap: '3px 8px', fontSize: 9, color: '#64748b', marginTop: 6,
                  background: '#0a1628', borderRadius: 4, padding: '5px 6px',
                }}>
                  <span>RSI 5m: <b style={{ color: s.tech_indicators.rsi_5m > 70 ? '#f87171' : s.tech_indicators.rsi_5m < 30 ? '#4ade80' : '#94a3b8' }}>{s.tech_indicators.rsi_5m}</b></span>
                  <span>RSI 1h: <b style={{ color: s.tech_indicators.rsi_1h > 70 ? '#f87171' : s.tech_indicators.rsi_1h < 30 ? '#4ade80' : '#94a3b8' }}>{s.tech_indicators.rsi_1h}</b></span>
                  <span>VWAP: <b style={{ color: s.tech_indicators.vwap_bias === 'bullish' ? '#4ade80' : s.tech_indicators.vwap_bias === 'bearish' ? '#f87171' : '#94a3b8' }}>{s.tech_indicators.vwap_bias === 'bullish' ? 'מעל ↑' : s.tech_indicators.vwap_bias === 'bearish' ? 'מתחת ↓' : '—'}</b></span>
                  <span>ADX: <b style={{ color: s.tech_indicators.adx_1h > 25 ? '#fde047' : '#94a3b8' }}>{s.tech_indicators.adx_1h}</b></span>
                  <span>BB: <b>{(s.tech_indicators.bb_position_5m * 100).toFixed(0)}%</b></span>
                  <span>Stoch: <b style={{ color: s.tech_indicators.stoch_k_5m > 80 ? '#f87171' : s.tech_indicators.stoch_k_5m < 20 ? '#4ade80' : '#94a3b8' }}>{s.tech_indicators.stoch_k_5m}</b></span>
                </div>
              )}
            </div>
          ) : (
            <div style={{ flex: '0 0 270px', padding: '12px 14px', borderLeft: '1px solid #1e293b' }}>
              <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 700, marginBottom: 8, letterSpacing: '0.05em' }}>
                📊 ניתוח טכני
              </div>
              <span style={{ fontSize: 11, color: '#475569' }}>⏳ טוען...</span>
            </div>
          )}

          {/* ── Col 4: Chart + news ── */}
          <div style={{ flex: 1, padding: '12px 14px', minWidth: 0 }}>
            {/* Intraday sparkline chart */}
            <div style={{ marginBottom: 10 }}>
              <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 700, marginBottom: 4, letterSpacing: '0.05em' }}>
                📈 גרף יומי
              </div>
              <div style={{ background: '#0a1628', borderRadius: 6, padding: '4px', border: '1px solid #1e293b' }}>
                <Sparkline ticker={s.ticker} width={220} height={55} />
              </div>
            </div>
            <div style={{ fontSize: 10, color: '#94a3b8', fontWeight: 700, marginBottom: 8, letterSpacing: '0.05em' }}>
              📰 חדשות אחרונות
            </div>

            {/* Business summary */}
            {s.business_summary && (
              <p style={{
                fontSize: 11, color: '#94a3b8', margin: '0 0 8px 0',
                lineHeight: 1.5, fontStyle: 'italic',
                borderRight: '2px solid #1e3a5f', paddingRight: 8,
              }}>
                {s.business_summary}
              </p>
            )}

            {/* News list */}
            {s.news?.length > 0 ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {s.news.slice(0, 4).map((n, i) => (
                  <a
                    key={i}
                    href={n.link || '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={e => e.stopPropagation()}
                    style={{
                      display: 'flex', gap: 8, alignItems: 'flex-start',
                      textDecoration: 'none', padding: '5px 8px', borderRadius: 6,
                      background: '#0d1626', border: '1px solid #1e293b',
                      transition: 'border-color 0.15s',
                    }}
                    onMouseEnter={e => e.currentTarget.style.borderColor = '#3b82f6'}
                    onMouseLeave={e => e.currentTarget.style.borderColor = '#1e293b'}
                  >
                    <span style={{ color: '#94a3b8', fontSize: 9, minWidth: 12, paddingTop: 2 }}>{i + 1}.</span>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <p style={{ color: '#94a3b8', fontSize: 10, margin: 0, lineHeight: 1.3, direction: 'ltr', textAlign: 'left', fontStyle: 'italic' }}>
                        {n.title}
                      </p>
                      {n.title_he && (
                        <p style={{ color: '#e2e8f0', fontSize: 11, margin: '2px 0 0', lineHeight: 1.4, direction: 'rtl', textAlign: 'right', fontWeight: 500 }}>
                          {n.title_he}
                        </p>
                      )}
                      <div style={{ display: 'flex', gap: 8, marginTop: 2 }}>
                        {n.publisher && <span style={{ color: '#94a3b8', fontSize: 9 }}>{n.publisher}</span>}
                        {n.published && <span style={{ color: '#94a3b8', fontSize: 9 }}>{fmtTs(n.published)}</span>}
                      </div>
                    </div>
                    <span style={{ color: '#3b82f6', fontSize: 10, flexShrink: 0 }}>↗</span>
                  </a>
                ))}
              </div>
            ) : (
              <span style={{ fontSize: 11, color: '#94a3b8' }}>אין חדשות זמינות</span>
            )}
          </div>

        </div>
      </td>
    </tr>
  );
}

// ── Countdown ring ─────────────────────────────────────────────────────────────
function CountdownRing({ seconds, total }) {
  const pct = (seconds / total) * 100;
  const r = 9, c = 2 * Math.PI * r;
  const dash = (pct / 100) * c;
  return (
    <svg width={24} height={24} style={{ transform: 'rotate(-90deg)' }}>
      <circle cx={12} cy={12} r={r} fill="none" stroke="#1e293b" strokeWidth={2.5} />
      <circle
        cx={12} cy={12} r={r} fill="none"
        stroke={seconds <= 10 ? '#f87171' : '#3b82f6'}
        strokeWidth={2.5}
        strokeDasharray={`${dash} ${c}`}
        style={{ transition: 'stroke-dasharray 1s linear' }}
      />
    </svg>
  );
}

// ── Demo Portfolio ─────────────────────────────────────────────────────────────
function useDemoPortfolio() {
  const [positions, setPositions] = useState(() => {
    try { return JSON.parse(localStorage.getItem('demoPortfolio_v1') || '{}'); }
    catch { return {}; }
  });

  // Sync to localStorage whenever positions change (avoids stale closure writes)
  useEffect(() => {
    localStorage.setItem('demoPortfolio_v1', JSON.stringify(positions));
  }, [positions]);

  const buy = useCallback((ticker, price, qty) => {
    setPositions(prev => {
      const pos = { ...prev };
      if (pos[ticker]?.side === 'long') {
        const total = pos[ticker].qty + qty;
        pos[ticker] = { side: 'long', qty: total, avgPrice: (pos[ticker].avgPrice * pos[ticker].qty + price * qty) / total };
      } else {
        pos[ticker] = { side: 'long', qty, avgPrice: price };
      }
      return pos;
    });
  }, []);

  const short = useCallback((ticker, price, qty) => {
    setPositions(prev => {
      const pos = { ...prev };
      if (pos[ticker]?.side === 'short') {
        const total = pos[ticker].qty + qty;
        pos[ticker] = { side: 'short', qty: total, avgPrice: (pos[ticker].avgPrice * pos[ticker].qty + price * qty) / total };
      } else {
        pos[ticker] = { side: 'short', qty, avgPrice: price };
      }
      return pos;
    });
  }, []);

  const closePosition = useCallback((ticker) => {
    setPositions(prev => {
      const pos = { ...prev };
      delete pos[ticker];
      return pos;
    });
  }, []);

  return { positions, buy, short, closePosition };
}

// ── Buy/Sell cell ──────────────────────────────────────────────────────────────
function BuySellCell({ ticker, price, positions, onBuy, onShort, onClose }) {
  const [open, setOpen] = useState(false);
  const [qty, setQty] = useState('10');
  const pos = positions[ticker];
  const currentPnlPct = pos
    ? pos.side === 'long'
      ? ((price - pos.avgPrice) / pos.avgPrice * 100)
      : ((pos.avgPrice - price) / pos.avgPrice * 100)
    : null;
  const pnlColor = currentPnlPct > 0 ? '#4ade80' : currentPnlPct < 0 ? '#f87171' : '#94a3b8';

  return (
    <div style={{ position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2 }} onClick={e => e.stopPropagation()}>
      <button
        onClick={() => setOpen(o => !o)}
        title={pos ? 'ניהול פוזיציה' : 'קנה / שורט'}
        style={{
          width: 22, height: 22, borderRadius: 4, border: `1px solid ${pos ? (pos.side === 'long' ? '#166534' : '#7f1d1d') : '#1e293b'}`,
          background: pos ? (pos.side === 'long' ? '#052e16' : '#2d0a0a') : '#0d1626',
          color: pos ? (pos.side === 'long' ? '#4ade80' : '#f87171') : '#475569',
          cursor: 'pointer', fontSize: 11, lineHeight: 1,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}
      >
        {pos ? (pos.side === 'long' ? '▲' : '▼') : '+'}
      </button>
      {pos && currentPnlPct !== null && (
        <span style={{ fontSize: 9, color: pnlColor, fontFamily: 'monospace', fontWeight: 700 }}>
          {currentPnlPct > 0 ? '+' : ''}{currentPnlPct.toFixed(1)}%
        </span>
      )}
      {open && (
        <div style={{
          position: 'absolute', zIndex: 999, top: '110%', left: 0,
          background: '#0f172a', border: '1px solid #3b82f6', borderRadius: 10,
          padding: '12px', minWidth: 170, boxShadow: '0 8px 24px rgba(0,0,0,0.5)',
        }}>
          <div style={{ fontSize: 12, color: '#94a3b8', marginBottom: 8 }}>
            <span style={{ fontWeight: 700, color: '#f8fafc' }}>{ticker}</span>
            {' '}${price?.toFixed(2)}
          </div>
          <input
            type="number" value={qty} min="1"
            onChange={e => setQty(e.target.value)}
            style={{
              width: '100%', background: '#1e293b', border: '1px solid #334155',
              color: '#e2e8f0', borderRadius: 6, padding: '5px 8px', fontSize: 12,
              marginBottom: 8, outline: 'none', boxSizing: 'border-box',
            }}
            placeholder="כמות מניות"
          />
          {pos ? (
            <>
              <div style={{ fontSize: 11, color: pnlColor, fontWeight: 700, textAlign: 'center', marginBottom: 8 }}>
                {pos.side === 'long' ? '📈 Long' : '📉 Short'} · {pos.qty} יח׳ · כניסה ${pos.avgPrice.toFixed(2)}
                <div>{currentPnlPct > 0 ? '+' : ''}{currentPnlPct.toFixed(2)}% ({((price - pos.avgPrice) * pos.qty * (pos.side === 'long' ? 1 : -1)).toFixed(0)}$)</div>
              </div>
              <button onClick={() => { onClose(ticker); setOpen(false); }} style={{
                width: '100%', padding: '6px', background: '#2d0a0a', border: '1px solid #ef4444',
                color: '#fca5a5', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 700,
              }}>
                ✕ סגור פוזיציה
              </button>
            </>
          ) : (
            <>
              <button onClick={() => { onBuy(ticker, price, parseFloat(qty) || 1); setOpen(false); }} style={{
                width: '100%', padding: '6px', background: '#052e16', border: '1px solid #22c55e',
                color: '#4ade80', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 700, marginBottom: 6,
              }}>
                📈 קנה (Long)
              </button>
              <button onClick={() => { onShort(ticker, price, parseFloat(qty) || 1); setOpen(false); }} style={{
                width: '100%', padding: '6px', background: '#2d0a0a', border: '1px solid #ef4444',
                color: '#f87171', borderRadius: 6, cursor: 'pointer', fontSize: 12, fontWeight: 700,
              }}>
                📉 שורט (Short)
              </button>
            </>
          )}
          <button onClick={() => setOpen(false)} style={{
            width: '100%', marginTop: 6, padding: '4px', background: 'transparent',
            border: 'none', color: '#475569', cursor: 'pointer', fontSize: 10,
          }}>
            סגור ✕
          </button>
        </div>
      )}
    </div>
  );
}

// ── Portfolio Panel ────────────────────────────────────────────────────────────
function PortfolioPanel({ positions, stockMap, portfolioPrices, onClose }) {
  const tickers = Object.keys(positions);
  if (tickers.length === 0) return null;

  let totalPnl = 0;
  const rows = tickers.map(ticker => {
    const pos = positions[ticker];
    const fvPrice = portfolioPrices?.[ticker]?.price;
    const cur = fvPrice ?? stockMap[ticker] ?? pos.avgPrice;
    const priceSource = fvPrice ? 'live' : stockMap[ticker] ? 'screener' : 'fallback';
    const diff = pos.side === 'long' ? cur - pos.avgPrice : pos.avgPrice - cur;
    const pnl = diff * pos.qty;
    const pnlPct = (diff / pos.avgPrice) * 100;
    totalPnl += pnl;
    return { ticker, pos, cur, pnl, pnlPct, priceSource };
  });

  return (
    <div style={{ marginTop: 12, padding: 12, border: '1px solid #334155', borderRadius: 6 }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <h3 style={{ color: '#e2e8f0', fontSize: 13, fontWeight: 700, margin: 0 }}>💼 תיק דמו</h3>
        <span style={{ fontSize: 13, fontWeight: 700, color: totalPnl >= 0 ? '#4ade80' : '#f87171', fontFamily: 'monospace' }}>
          סה"כ: {totalPnl >= 0 ? '+' : ''}{totalPnl.toFixed(2)}$
        </span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }} dir="rtl">
          <thead>
            <tr style={{ borderBottom: '2px solid #334155' }}>
              {['מניה','כיוון','כמות','כניסה','עכשיו','רווח/הפסד','%',''].map(h => (
                <th key={h} style={{ textAlign: 'right', padding: '8px 10px', color: '#e2e8f0', fontWeight: 700, fontSize: 12, whiteSpace: 'nowrap' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ ticker, pos, cur, pnl, pnlPct, priceSource }) => {
              const c = pnl > 0 ? '#4ade80' : pnl < 0 ? '#f87171' : '#cbd5e1';
              return (
                <tr key={ticker} style={{ borderBottom: '1px solid #1e293b' }}>
                  <td style={{ padding: '8px 10px', fontWeight: 800, color: '#f8fafc', fontSize: 13 }}>{ticker}</td>
                  <td style={{ padding: '8px 10px', color: pos.side === 'long' ? '#4ade80' : '#f87171', fontWeight: 700, fontSize: 12 }}>
                    {pos.side === 'long' ? '📈 Long' : '📉 Short'}
                  </td>
                  <td style={{ padding: '8px 10px', color: '#e2e8f0', fontFamily: 'monospace', fontSize: 12 }}>{pos.qty}</td>
                  <td style={{ padding: '8px 10px', color: '#cbd5e1', fontFamily: 'monospace', fontSize: 12 }}>${pos.avgPrice.toFixed(2)}</td>
                  <td style={{ padding: '8px 10px', fontFamily: 'monospace', fontWeight: 700, fontSize: 12 }}>
                    <span style={{ color: '#f1f5f9' }}>▲ ${cur.toFixed(2)}</span>
                    {priceSource === 'live' && (
                      <span style={{ fontSize: 10, color: '#4ade80', marginRight: 3 }} title="מחיר לייב">●</span>
                    )}
                    {priceSource === 'fallback' && (
                      <span style={{ fontSize: 10, color: '#f87171', marginRight: 3 }} title="מחיר לא מעודכן">⚠️</span>
                    )}
                  </td>
                  <td style={{ padding: '8px 10px', color: c, fontFamily: 'monospace', fontWeight: 700, fontSize: 12 }}>
                    {pnl >= 0 ? '+' : ''}{pnl.toFixed(2)}$
                  </td>
                  <td style={{ padding: '8px 10px', color: c, fontFamily: 'monospace', fontWeight: 700, fontSize: 12 }}>
                    {pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%
                  </td>
                  <td style={{ padding: '7px 10px' }}>
                    <button onClick={() => onClose(ticker)} style={{
                      fontSize: 10, padding: '3px 8px', background: '#1e293b',
                      border: '1px solid #334155', color: '#94a3b8', borderRadius: 4, cursor: 'pointer',
                    }}>✕ סגור</button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── Sector translation ─────────────────────────────────────────────────────────
const SECTOR_HE = {
  'Technology': 'טכנולוגיה',
  'Healthcare': 'בריאות',
  'Financial': 'פיננסים',
  'Financial Services': 'שירותים פיננסיים',
  'Consumer Cyclical': 'צרכנות מחזורית',
  'Consumer Defensive': 'צרכנות הגנתית',
  'Industrials': 'תעשייה',
  'Communication Services': 'תקשורת',
  'Energy': 'אנרגיה',
  'Basic Materials': 'חומרי גלם',
  'Real Estate': 'נדל"ן',
  'Utilities': 'תשתיות',
};

// ── Industry translation ───────────────────────────────────────────────────────
const INDUSTRY_HE = {
  'Communication Equipment': 'ציוד תקשורת',
  'Software—Application': 'תוכנה - יישומים',
  'Software—Infrastructure': 'תוכנה - תשתיות',
  'Semiconductors': 'מוליכים למחצה',
  'Semiconductor Equipment': 'ציוד מוליכים',
  'Electronic Components': 'רכיבים אלקטרוניים',
  'Scientific & Technical Instruments': 'מכשירים מדעיים',
  'Computer Hardware': 'חומרת מחשב',
  'Information Technology Services': 'שירותי IT',
  'Biotechnology': 'ביוטכנולוגיה',
  'Drug Manufacturers—General': 'תרופות - כללי',
  'Drug Manufacturers—Specialty & Generic': 'תרופות - גנריות',
  'Medical Devices': 'מכשור רפואי',
  'Diagnostics & Research': 'אבחון ומחקר',
  'Health Information Services': 'מידע רפואי',
  'Medical Care Facilities': 'מוסדות רפואיים',
  'Banks—Regional': 'בנקים אזוריים',
  'Banks—Diversified': 'בנקים מגוונים',
  'Capital Markets': 'שוק ההון',
  'Asset Management': 'ניהול נכסים',
  'Insurance—Life': 'ביטוח חיים',
  'Insurance—Property & Casualty': 'ביטוח רכוש',
  'Credit Services': 'שירותי אשראי',
  'Oil & Gas E&P': 'נפט וגז - חיפוש',
  'Oil & Gas Integrated': 'נפט וגז משולב',
  'Oil & Gas Midstream': 'נפט וגז - הולכה',
  'Specialty Retail': 'קמעונאות מיוחדת',
  'Internet Retail': 'קמעונאות מקוונת',
  'Grocery Stores': 'סופרמרקטים',
  'Aerospace & Defense': 'תעופה וביטחון',
  'Industrial Distribution': 'הפצה תעשייתית',
  'Electrical Equipment & Parts': 'ציוד חשמלי',
  'REIT—Retail': 'נדל"ן מסחרי',
  'REIT—Residential': 'נדל"ן למגורים',
  'REIT—Industrial': 'נדל"ן תעשייתי',
  'REIT—Office': 'נדל"ן משרדים',
  'Telecom Services': 'שירותי תקשורת',
  'Entertainment': 'בידור',
  'Advertising Agencies': 'סוכנויות פרסום',
  'Auto Manufacturers': 'יצרני רכב',
  'Auto Parts': 'חלקי רכב',
  'Restaurants': 'מסעדות',
  'Airlines': 'חברות תעופה',
  'Lodging': 'מלונאות',
  'Residential Construction': 'בנייה למגורים',
};

// ── Earnings date formatter ────────────────────────────────────────────────────
const MONTH_HE = {
  Jan: 'ינו׳', Feb: 'פבר׳', Mar: 'מרץ', Apr: 'אפר׳',
  May: 'מאי',  Jun: 'יונ׳', Jul: 'יול׳', Aug: 'אוג׳',
  Sep: 'ספט׳', Oct: 'אוק׳', Nov: 'נוב׳', Dec: 'דצמ׳',
};
function fmtEarningsDate(d) {
  if (!d) return d;
  let s = d;
  Object.entries(MONTH_HE).forEach(([en, he]) => { s = s.replace(en, he); });
  s = s.replace('AMC', '| אחרי סגירה').replace('BMO', '| לפני פתיחה');
  return s;
}

// ── Analyst recommendation translation ────────────────────────────────────────
const RECOM_HE = {
  'Buy': 'קנה', 'Strong Buy': 'קנה חזק', 'Sell': 'מכור', 'Strong Sell': 'מכור חזק',
  'Hold': 'החזק', 'Outperform': 'מעל שוק', 'Underperform': 'מתחת לשוק',
  'Neutral': 'ניטרלי', 'Overweight': 'משקל יתר', 'Underweight': 'משקל חסר',
  'Equal Weight': 'משקל שווה',
};

// ── Session detection ──────────────────────────────────────────────────────────
const SESSION_META = {
  pre:     { label: '🌅 טרום מסחר', color: '#fb923c', bg: '#1c0f00', border: '#92400e' },
  regular: { label: '📈 מסחר רגיל', color: '#4ade80', bg: '#052e16', border: '#166534' },
  post:    { label: '🌆 אחרי שעות', color: '#818cf8', bg: '#1e1b4b', border: '#4338ca' },
  closed:  { label: '⏸ שוק סגור',  color: '#94a3b8', bg: '#0f172a', border: '#1e293b' },
};
function getClientSession() {
  try {
    const et = new Date().toLocaleString('en-US', { timeZone: 'America/New_York' });
    const d  = new Date(et);
    const h  = d.getHours() + d.getMinutes() / 60;
    const dow = d.getDay(); // 0=Sun, 6=Sat
    if (dow === 0 || dow === 6) return 'closed';
    if (h < 4)    return 'closed';
    if (h < 9.5)  return 'pre';
    if (h < 16)   return 'regular';
    if (h < 20)   return 'post';
    return 'closed';
  } catch { return 'regular'; }
}

// ── Main component ─────────────────────────────────────────────────────────────
const REFRESH_SEC = 30;

// ═══════════════════════════════════════════════════════════════════════════════
//  Smart AI Portfolio Dashboard
// ═══════════════════════════════════════════════════════════════════════════════
function SmartPortfolioDashboard({ floating = false, placement }) {
  const mode = placement || (floating ? 'floating' : 'inline');
  const [data, setData] = useState(null);
  const [trades, setTrades] = useState([]);
  const [thinking, setThinking] = useState(false);
  const [lastDecision, setLastDecision] = useState(null);
  // Full-page inline mode starts expanded
  const [expanded, setExpanded] = useState(mode === 'inline');
  const [tab, setTab] = useState('overview');
  const [regime, setRegime] = useState(null);

  const fetchStatus = () => {
    axios.get('/api/smart-portfolio/status').then(r => setData(r.data)).catch(() => {});
    axios.get('/api/smart-portfolio/trades').then(r => setTrades(r.data || [])).catch(() => {});
    axios.get('/api/smart-portfolio/regime').then(r => setRegime(r.data)).catch(() => {});
  };

  useEffect(() => { fetchStatus(); const iv = setInterval(fetchStatus, 15000); return () => clearInterval(iv); }, []);

  const triggerThink = async () => {
    setThinking(true);
    try {
      const r = await axios.post('/api/smart-portfolio/think');
      setLastDecision(r.data);
      fetchStatus();
    } catch (e) {
      setLastDecision({ error: e.message });
    }
    setThinking(false);
  };

  const resetPortfolio = async () => {
    if (confirm('לאפס את התיק החכם ל-$3,000?')) {
      await axios.post('/api/smart-portfolio/reset');
      setLastDecision(null);
      setTrades([]);
      fetchStatus();
    }
  };

  const W = '#4ade80', L = '#f87171', A = '#818cf8';
  const posCount = Object.keys(data?.positions || {}).length;
  const returnPct = data?.total_pnl_pct ?? 0;

  const headerStrip = (
    <button
      type="button"
      onClick={() => setExpanded(true)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 8,
        padding: '6px 12px',
        borderRadius: 8,
        border: '1px solid rgba(129,140,248,0.25)',
        background: 'linear-gradient(135deg, rgba(10,22,40,0.95) 0%, rgba(15,13,46,0.9) 100%)',
        color: '#e2e8f0',
        cursor: 'pointer',
        fontSize: 11,
        fontWeight: 700,
        fontFamily: 'inherit',
      }}
      onMouseEnter={e => {
        e.currentTarget.style.background = 'linear-gradient(135deg, rgba(30,27,75,0.98) 0%, rgba(30,41,59,0.95) 100%)';
        e.currentTarget.style.borderColor = 'rgba(129,140,248,0.45)';
      }}
      onMouseLeave={e => {
        e.currentTarget.style.background = 'linear-gradient(135deg, rgba(10,22,40,0.95) 0%, rgba(15,13,46,0.9) 100%)';
        e.currentTarget.style.borderColor = 'rgba(129,140,248,0.25)';
      }}
    >
      <span style={{ fontSize: 14 }}>🧠</span>
      <span style={{ color: A }}>תיק</span>
      {data ? (
        <>
          <span style={{ fontFamily: 'monospace', color: '#f8fafc' }}>${(data.equity ?? 3000).toFixed(0)}</span>
          <span style={{ color: returnPct >= 0 ? W : L, fontFamily: 'monospace' }}>
            {returnPct >= 0 ? '+' : ''}{returnPct.toFixed(1)}%
          </span>
          <span style={{ color: '#64748b' }}>·</span>
          <span style={{ color: '#94a3b8' }}>{posCount} פוזיציות</span>
          {data.note && <span style={{ color: '#64748b', fontSize: 9 }} title={data.note}> (ענן)</span>}
        </>
      ) : (
        <span style={{ color: '#64748b' }}>טוען…</span>
      )}
      <span style={{ color: '#475569', fontSize: 10 }}>▼</span>
    </button>
  );

  const collapsedContent = (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '12px 16px',
        background: 'linear-gradient(135deg, #0a1628 0%, #0f0d2e 100%)',
        border: '1px solid #2d1f6b',
        borderRadius: mode === 'floating' ? 16 : 10,
        cursor: 'pointer',
        boxShadow: mode === 'floating' ? '0 8px 32px rgba(0,0,0,0.4), 0 0 0 1px rgba(129,140,248,0.15)' : undefined,
        minWidth: mode === 'floating' ? 280 : undefined,
      }}
      onClick={() => setExpanded(true)}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 20 }}>🧠</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 800, color: A }}>תיק דמו חכם</div>
          <div style={{ fontSize: 9, color: '#64748b' }}>{posCount} פוזיציות · {lastDecision?.decision?.strategy_label || lastDecision?.decision?.strategy_name || 'אגרסיבי'}</div>
        </div>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        {data && (
          <>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 16, fontFamily: 'monospace', fontWeight: 900, color: returnPct >= 0 ? W : L }}>
                {returnPct >= 0 ? '+' : ''}{returnPct.toFixed(1)}%
              </div>
              <div style={{ fontSize: 9, color: '#64748b' }}>${data.equity?.toFixed(0)}</div>
            </div>
            <div style={{ width: 1, height: 24, background: '#1e293b' }} />
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 12, fontFamily: 'monospace', fontWeight: 700, color: '#94a3b8' }}>{data.total_trades}</div>
              <div style={{ fontSize: 9, color: '#64748b' }}>עסקאות</div>
            </div>
            {data.total_trades > 0 && (
              <>
                <div style={{ width: 1, height: 24, background: '#1e293b' }} />
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontSize: 12, fontFamily: 'monospace', fontWeight: 700, color: data.win_rate >= 50 ? W : L }}>{data.win_rate?.toFixed(0)}%</div>
                  <div style={{ fontSize: 9, color: '#64748b' }}>הצלחה</div>
                </div>
              </>
            )}
          </>
        )}
        <span style={{ fontSize: 14, color: '#475569' }}>▼</span>
      </div>
    </div>
  );

  if (!expanded) {
    if (mode === 'header') return headerStrip;
    if (mode === 'floating') {
      return (
        <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 50 }}>
          {collapsedContent}
        </div>
      );
    }
    return <div style={{ margin: '8px 0' }}>{collapsedContent}</div>;
  }

  const dailyLimitUsed = data ? Math.min(100, Math.abs(data.daily_pnl) / (data.equity * 0.05) * 100) : 0;
  const cashPct = data ? (data.cash / data.equity * 100) : 100;

  const tabStyle = (t) => ({
    fontSize: 11, padding: '5px 12px', borderRadius: 4, border: 'none', cursor: 'pointer', fontWeight: 600,
    background: tab === t ? '#1e1b4b' : 'transparent', color: tab === t ? A : '#64748b',
  });

  const isOverlay = mode === 'floating' || mode === 'header';
  const expandedPanel = (
    <div style={{
      margin: isOverlay ? 0 : '8px 0',
      background: 'linear-gradient(135deg, #0a1628 0%, #0f0d2e 100%)',
      border: '1px solid #2d1f6b',
      borderRadius: 10,
      overflow: 'hidden',
      display: isOverlay ? 'flex' : 'block',
      flexDirection: 'column',
      ...(isOverlay ? { width: 420, maxHeight: '85vh', boxShadow: '0 20px 60px rgba(0,0,0,0.5)' } : {}),
    }}>
      {/* Header — לא נגלל */}
      <div style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderBottom: '1px solid #1e293b', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer' }} onClick={() => setExpanded(false)}>
          <span style={{ fontSize: 18 }}>🧠</span>
          <div>
            <span style={{ fontSize: 14, fontWeight: 800, color: A }}>תיק דמו חכם — AI Brain v5 💥</span>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 9, color: '#64748b' }}>
              <span>מנוע: {lastDecision?.decision?.engine === 'groq' ? '⚡ Groq Llama 3.3' : lastDecision?.decision?.engine === 'gemini' ? '🔮 Gemini AI' : '🔧 Rule-Based'}</span>
              {regime && (
                <span style={{ padding: '1px 5px', borderRadius: 3, fontWeight: 700, background: regime.type === 'bullish' ? '#052e16' : regime.type === 'bearish' ? '#2a0000' : '#1e1b4b', color: regime.type === 'bullish' ? '#4ade80' : regime.type === 'bearish' ? '#f87171' : '#818cf8', border: `1px solid ${regime.type === 'bullish' ? '#166534' : regime.type === 'bearish' ? '#7f1d1d' : '#4338ca'}` }}>
                  {regime.type === 'bullish' ? '🟢 שורי' : regime.type === 'bearish' ? '🔴 דובי' : regime.type === 'volatile' ? '⚡ תנודתי' : '⚪ ניטרלי'}
                </span>
              )}
            </div>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          <button onClick={triggerThink} disabled={thinking}
            style={{ fontSize: 11, padding: '5px 12px', borderRadius: 6, border: 'none', background: thinking ? '#1e1b4b' : 'linear-gradient(135deg, #4338ca, #6366f1)', color: '#fff', cursor: 'pointer', fontWeight: 700, opacity: thinking ? 0.6 : 1 }}>
            {thinking ? '⏳ חושב...' : '🧠 חשוב עכשיו'}
          </button>
          <button onClick={resetPortfolio}
            style={{ fontSize: 10, padding: '5px 8px', borderRadius: 6, border: '1px solid #334155', background: 'transparent', color: '#64748b', cursor: 'pointer' }}>
            🔄 אפס
          </button>
          <span style={{ fontSize: 14, color: '#475569', cursor: 'pointer' }} onClick={() => setExpanded(false)}>▲</span>
        </div>
      </div>

      {/* גלילה פנימית — התוכן מתחת להדר */}
      <div style={{ ...(isOverlay ? { flex: 1, minHeight: 0, overflowY: 'auto', WebkitOverflowScrolling: 'touch' } : {}), padding: '0 16px 12px' }}>
      {data && (
        <div>
          {/* Big Stats */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, margin: '12px 0' }}>
            {[
              { label: 'הון כולל', value: `$${data.equity?.toFixed(0)}`, sub: `מתוך $${INITIAL_CAPITAL}`, color: '#f8fafc', icon: '💰' },
              { label: 'רווח/הפסד', value: `${returnPct >= 0 ? '+' : ''}${returnPct.toFixed(2)}%`, sub: `${data.total_pnl >= 0 ? '+' : ''}$${data.total_pnl?.toFixed(0)}`, color: returnPct >= 0 ? W : L, icon: returnPct >= 0 ? '📈' : '📉' },
              { label: 'יומי', value: `${data.daily_pnl >= 0 ? '+' : ''}$${data.daily_pnl?.toFixed(0)}`, sub: `מגבלה: 8%`, color: data.daily_pnl >= 0 ? W : L, icon: '📊' },
              { label: 'אחוז הצלחה', value: data.total_trades > 0 ? `${data.win_rate?.toFixed(0)}%` : '—', sub: `${data.winning_trades}W / ${data.total_trades - data.winning_trades}L`, color: data.win_rate >= 50 ? W : data.total_trades > 0 ? L : '#94a3b8', icon: '🎯' },
            ].map((s, i) => (
              <div key={i} style={{ background: '#060c18', borderRadius: 8, padding: '10px', border: '1px solid #1e293b', textAlign: 'center' }}>
                <div style={{ fontSize: 16 }}>{s.icon}</div>
                <div style={{ fontSize: 16, fontFamily: 'monospace', fontWeight: 900, color: s.color, margin: '2px 0' }}>{s.value}</div>
                <div style={{ fontSize: 9, color: '#64748b', fontWeight: 600 }}>{s.label}</div>
                <div style={{ fontSize: 8, color: '#475569', marginTop: 1 }}>{s.sub}</div>
              </div>
            ))}
          </div>

          {/* Risk Bars */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 10 }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#64748b', marginBottom: 2 }}>
                <span>מגבלת הפסד יומי</span>
                <span style={{ color: dailyLimitUsed > 80 ? L : '#94a3b8' }}>{dailyLimitUsed.toFixed(0)}%</span>
              </div>
              <div style={{ height: 4, background: '#1e293b', borderRadius: 2, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${dailyLimitUsed}%`, background: dailyLimitUsed > 80 ? L : dailyLimitUsed > 50 ? '#fbbf24' : W, borderRadius: 2, transition: 'width 0.5s' }} />
              </div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#64748b', marginBottom: 2 }}>
                <span>מזומן זמין</span>
                <span>${data.cash?.toFixed(0)} ({cashPct.toFixed(0)}%)</span>
              </div>
              <div style={{ height: 4, background: '#1e293b', borderRadius: 2, overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${cashPct}%`, background: A, borderRadius: 2, transition: 'width 0.5s' }} />
              </div>
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, color: '#64748b', marginBottom: 2 }}>
                <span>פוזיציות</span>
                <span>{posCount}/3</span>
              </div>
              <div style={{ display: 'flex', gap: 3 }}>
                {[0, 1, 2].map(i => <div key={i} style={{ flex: 1, height: 4, borderRadius: 2, background: i < posCount ? A : '#1e293b' }} />)}
              </div>
            </div>
          </div>

          {/* Tabs */}
          <div style={{ display: 'flex', gap: 2, marginBottom: 10, background: '#060c18', borderRadius: 6, padding: 2 }}>
            <button onClick={() => setTab('overview')} style={tabStyle('overview')}>📊 סקירה</button>
            <button onClick={() => setTab('positions')} style={tabStyle('positions')}>📌 פוזיציות ({posCount})</button>
            <button onClick={() => setTab('trades')} style={tabStyle('trades')}>📋 היסטוריה ({trades.length})</button>
            <button onClick={() => setTab('brain')} style={tabStyle('brain')}>🧠 מוח</button>
          </div>

          {/* Tab: Overview */}
          {tab === 'overview' && (
            <div>
              {/* Equity Curve */}
              {data.equity_history?.length > 1 && (() => {
                const vals = data.equity_history.map(p => p.equity);
                const mn = Math.min(...vals), mx = Math.max(...vals);
                const range = mx - mn || 1;
                const w = 500, h = 80, pad = 2;
                const iw = w - pad * 2, ih = h - pad * 2;
                const line = vals.map((v, i) => `${pad + (i / (vals.length - 1)) * iw},${pad + ih - ((v - mn) / range) * ih}`).join(' ');
                const area = line + ` ${pad + iw},${pad + ih} ${pad},${pad + ih}`;
                const isUp = vals[vals.length - 1] >= vals[0];
                const baseY = pad + ih - ((INITIAL_CAPITAL - mn) / range) * ih;
                return (
                  <div style={{ marginBottom: 10 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 3 }}>
                      <span style={{ fontSize: 9, color: '#64748b', fontWeight: 600 }}>EQUITY CURVE</span>
                      <span style={{ fontSize: 9, color: '#475569' }}>${mn.toFixed(0)} — ${mx.toFixed(0)}</span>
                    </div>
                    <svg width="100%" viewBox={`0 0 ${w} ${h}`} style={{ display: 'block', background: '#060c18', borderRadius: 6, border: '1px solid #1e293b' }}>
                      <defs>
                        <linearGradient id="eqGrad" x1="0" x2="0" y1="0" y2="1">
                          <stop offset="0%" stopColor={isUp ? W : L} stopOpacity="0.3" />
                          <stop offset="100%" stopColor={isUp ? W : L} stopOpacity="0" />
                        </linearGradient>
                      </defs>
                      <polygon points={area} fill="url(#eqGrad)" />
                      <line x1={pad} y1={baseY} x2={pad + iw} y2={baseY} stroke="#334155" strokeDasharray="4 2" />
                      <text x={pad + 4} y={baseY - 3} fill="#475569" fontSize="8">$3,000</text>
                      <polyline points={line} fill="none" stroke={isUp ? W : L} strokeWidth={2} strokeLinejoin="round" />
                      <circle cx={pad + iw} cy={pad + ih - ((vals[vals.length - 1] - mn) / range) * ih} r={3} fill={isUp ? W : L} />
                    </svg>
                  </div>
                );
              })()}

              {/* Advanced Stats */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6, marginBottom: 8 }}>
                {[
                  { label: 'Sharpe Ratio', value: data.sharpe_ratio?.toFixed(2) ?? '—', color: (data.sharpe_ratio ?? 0) > 1 ? W : (data.sharpe_ratio ?? 0) > 0 ? '#fbbf24' : L, icon: '📐' },
                  { label: 'Max Drawdown', value: `${(data.max_drawdown ?? 0).toFixed(1)}%`, color: (data.max_drawdown ?? 0) > 10 ? L : (data.max_drawdown ?? 0) > 5 ? '#fbbf24' : W, icon: '📉' },
                  { label: 'Profit Factor', value: (data.profit_factor ?? 0).toFixed(2), color: (data.profit_factor ?? 0) > 1.5 ? W : (data.profit_factor ?? 0) > 1 ? '#fbbf24' : L, icon: '⚖️' },
                  { label: 'ממוצע ניצחון', value: `+$${(data.avg_win ?? 0).toFixed(0)}`, color: W, icon: '🟢' },
                  { label: 'ממוצע הפסד', value: `$${(data.avg_loss ?? 0).toFixed(0)}`, color: L, icon: '🔴' },
                  { label: 'זמן ממוצע', value: `${(data.avg_holding_minutes ?? 0).toFixed(0)} דק׳`, color: '#94a3b8', icon: '⏱' },
                ].map((s, i) => (
                  <div key={i} style={{ background: '#0f172a', borderRadius: 6, padding: '8px', textAlign: 'center', border: '1px solid #1e293b' }}>
                    <div style={{ fontSize: 12 }}>{s.icon}</div>
                    <div style={{ fontSize: 12, fontFamily: 'monospace', fontWeight: 800, color: s.color }}>{s.value}</div>
                    <div style={{ fontSize: 8, color: '#475569' }}>{s.label}</div>
                  </div>
                ))}
              </div>

              {/* Best / Worst trades */}
              {data.best_trade && (
                <div style={{ display: 'flex', gap: 6, marginBottom: 6 }}>
                  <div style={{ flex: 1, background: 'rgba(74,222,128,0.06)', borderRadius: 6, padding: '6px 8px', border: '1px solid #166534' }}>
                    <div style={{ fontSize: 8, color: '#64748b' }}>הכי טוב</div>
                    <div style={{ fontSize: 12, fontFamily: 'monospace', fontWeight: 800, color: W }}>
                      {data.best_trade.ticker} +${data.best_trade.pnl?.toFixed(0)} ({data.best_trade.pnl_pct?.toFixed(1)}%)
                    </div>
                  </div>
                  {data.worst_trade && (
                    <div style={{ flex: 1, background: 'rgba(248,113,113,0.06)', borderRadius: 6, padding: '6px 8px', border: '1px solid #7f1d1d' }}>
                      <div style={{ fontSize: 8, color: '#64748b' }}>הכי גרוע</div>
                      <div style={{ fontSize: 12, fontFamily: 'monospace', fontWeight: 800, color: L }}>
                        {data.worst_trade.ticker} ${data.worst_trade.pnl?.toFixed(0)} ({data.worst_trade.pnl_pct?.toFixed(1)}%)
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Tab: Positions */}
          {tab === 'positions' && (
            <div>
              {posCount === 0 ? (
                <div style={{ textAlign: 'center', padding: 20, color: '#475569', fontSize: 11 }}>
                  אין פוזיציות פתוחות. המוח יפתח פוזיציות כשימצא הזדמנויות.
                </div>
              ) : Object.entries(data.positions).map(([ticker, pos]) => {
                const elapsed = pos.entry_time ? Math.round((Date.now() - new Date(pos.entry_time).getTime()) / 60000) : 0;
                const slDist = pos.side === 'long'
                  ? ((pos.entry_price - pos.stop_loss) / pos.entry_price * 100)
                  : ((pos.stop_loss - pos.entry_price) / pos.entry_price * 100);
                const tgtDist = pos.side === 'long'
                  ? ((pos.target - pos.entry_price) / pos.entry_price * 100)
                  : ((pos.entry_price - pos.target) / pos.entry_price * 100);
                return (
                  <div key={ticker} style={{ background: '#0f172a', borderRadius: 8, padding: '10px 12px', marginBottom: 6, border: '1px solid #1e293b' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 15, fontWeight: 900, color: '#f8fafc' }}>{ticker}</span>
                        <span style={{ fontSize: 10, padding: '2px 6px', borderRadius: 4, background: pos.side === 'long' ? '#052e16' : '#2a0000', color: pos.side === 'long' ? W : L, fontWeight: 700, border: `1px solid ${pos.side === 'long' ? '#166534' : '#7f1d1d'}` }}>
                          {pos.side === 'long' ? '🟢 LONG' : '🔴 SHORT'}
                        </span>
                      </div>
                      <span style={{ fontSize: 9, color: '#475569' }}>{elapsed} דק׳</span>
                    </div>
                    <div style={{ display: 'flex', gap: 14, fontSize: 11, flexWrap: 'wrap', alignItems: 'center' }}>
                      <div><span style={{ color: '#64748b' }}>כניסה: </span><span style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>${pos.entry_price?.toFixed(2)}</span></div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
                        <span style={{ color: '#64748b' }}>עכשיו: </span>
                        <span style={{ color: '#f8fafc', fontFamily: 'monospace', fontWeight: 700 }}>${pos.current_price?.toFixed(2) ?? '—'}</span>
                        {pos.has_live_price && <span style={{ fontSize: 7, color: '#22c55e', fontWeight: 800 }}>● live</span>}
                      </div>
                      <div>
                        <span style={{ color: '#64748b' }}>P&L: </span>
                        <span style={{ fontFamily: 'monospace', fontWeight: 800, color: (pos.unrealized_pnl_pct ?? 0) >= 0 ? '#4ade80' : '#f87171' }}>
                          {(pos.unrealized_pnl_pct ?? 0) >= 0 ? '+' : ''}{(pos.unrealized_pnl_pct ?? 0).toFixed(2)}%
                          {pos.unrealized_pnl != null && <span style={{ fontSize: 10, marginLeft: 3, opacity: 0.8 }}>(${pos.unrealized_pnl >= 0 ? '+' : ''}{pos.unrealized_pnl.toFixed(0)})</span>}
                        </span>
                      </div>
                      <div><span style={{ color: '#64748b' }}>כמות: </span><span style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{pos.qty}</span></div>
                    </div>
                    {/* SL / Target bar */}
                    <div style={{ marginTop: 8 }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 9, marginBottom: 2 }}>
                        <span style={{ color: L }}>🛑 ${pos.stop_loss?.toFixed(2)} (-{slDist.toFixed(1)}%)</span>
                        <span style={{ color: W }}>🎯 ${pos.target?.toFixed(2)} (+{tgtDist.toFixed(1)}%)</span>
                      </div>
                      <div style={{ height: 6, background: '#1e293b', borderRadius: 3, position: 'relative', overflow: 'hidden' }}>
                        <div style={{ position: 'absolute', right: 0, height: '100%', width: `${slDist / (slDist + tgtDist) * 100}%`, background: 'rgba(248,113,113,0.3)', borderRadius: 3 }} />
                        <div style={{ position: 'absolute', left: 0, height: '100%', width: `${tgtDist / (slDist + tgtDist) * 100}%`, background: 'rgba(74,222,128,0.3)', borderRadius: 3 }} />
                      </div>
                    </div>
                    {pos.reason && <div style={{ fontSize: 9, color: '#64748b', marginTop: 4 }}>💡 {pos.reason}</div>}
                  </div>
                );
              })}
            </div>
          )}

          {/* Tab: Trade History */}
          {tab === 'trades' && (
            <div>
              {trades.length === 0 ? (
                <div style={{ textAlign: 'center', padding: 20, color: '#475569', fontSize: 11 }}>עדיין אין עסקאות סגורות.</div>
              ) : (
                <div style={{ maxHeight: 250, overflowY: 'auto' }}>
                  {trades.slice().reverse().map((t, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 11, padding: '6px 8px', background: i % 2 === 0 ? '#0f172a' : 'transparent', borderRadius: 4 }}>
                      <span style={{ fontWeight: 800, color: '#f8fafc', width: 48 }}>{t.ticker}</span>
                      <span style={{ fontSize: 9, color: t.side === 'long' ? W : L, width: 36 }}>{t.side === 'long' ? 'LONG' : 'SHORT'}</span>
                      <span style={{ color: t.pnl >= 0 ? W : L, fontFamily: 'monospace', fontWeight: 800, width: 58 }}>
                        {t.pnl >= 0 ? '+' : ''}{t.pnl_pct?.toFixed(1)}%
                      </span>
                      <span style={{ color: t.pnl >= 0 ? W : L, fontFamily: 'monospace', width: 52 }}>
                        {t.pnl >= 0 ? '+' : ''}${t.pnl?.toFixed(0)}
                      </span>
                      <span style={{ color: '#94a3b8', fontFamily: 'monospace', fontSize: 10, width: 75 }}>
                        ${t.entry_price?.toFixed(2)} → ${t.exit_price?.toFixed(2)}
                      </span>
                      <span style={{ color: '#475569', fontSize: 9, flex: 1 }}>{t.exit_reason}</span>
                      <span style={{ color: '#334155', fontSize: 8 }}>{t.holding_minutes}m</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Tab: Brain */}
          {tab === 'brain' && (
            <div>
              {/* Market Regime */}
              {regime && (
                <div style={{ background: regime.type === 'bullish' ? 'rgba(74,222,128,0.06)' : regime.type === 'bearish' ? 'rgba(248,113,113,0.06)' : '#0f172a', borderRadius: 8, padding: '10px 12px', border: `1px solid ${regime.type === 'bullish' ? '#166534' : regime.type === 'bearish' ? '#7f1d1d' : '#1e293b'}`, marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 10, color: A, fontWeight: 700 }}>🌍 משטר שוק נוכחי</span>
                    <span style={{ fontSize: 12, fontWeight: 800, color: regime.type === 'bullish' ? W : regime.type === 'bearish' ? L : '#818cf8' }}>
                      {regime.type === 'bullish' ? '🟢 שורי' : regime.type === 'bearish' ? '🔴 דובי' : regime.type === 'volatile' ? '⚡ תנודתי' : '⚪ ניטרלי'}
                    </span>
                  </div>
                  <div style={{ display: 'flex', gap: 12, fontSize: 10, marginBottom: 6 }}>
                    <div><span style={{ color: '#64748b' }}>רוחב: </span><span style={{ color: '#e2e8f0', fontFamily: 'monospace' }}>{regime.breadth?.toFixed(0)}%</span></div>
                    <div><span style={{ color: '#64748b' }}>עוליות: </span><span style={{ color: W, fontFamily: 'monospace' }}>{regime.up_count}</span></div>
                    <div><span style={{ color: '#64748b' }}>יורדות: </span><span style={{ color: L, fontFamily: 'monospace' }}>{regime.down_count}</span></div>
                    <div><span style={{ color: '#64748b' }}>תנודתיות: </span><span style={{ color: regime.volatility === 'extreme' ? L : regime.volatility === 'high' ? '#fbbf24' : '#94a3b8', fontFamily: 'monospace' }}>{regime.volatility}</span></div>
                  </div>
                  {regime.hot_sectors?.length > 0 && (
                    <div>
                      <div style={{ fontSize: 9, color: '#64748b', marginBottom: 3 }}>סקטורים חמים:</div>
                      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                        {regime.hot_sectors.map((s, i) => (
                          <span key={i} style={{ fontSize: 9, padding: '2px 6px', borderRadius: 3, background: '#052e16', color: W, border: '1px solid #166534' }}>
                            🔥 {s.name} +{s.avg_change}%
                          </span>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* Last Decision */}
              {lastDecision?.decision && (
                <div style={{ padding: '10px 12px', background: '#0f0d2e', border: '1px solid #4338ca', borderRadius: 8, marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
                    <span style={{ fontSize: 10, color: A, fontWeight: 700 }}>🧠 החלטה אחרונה</span>
                    {lastDecision.decision.engine && (
                      <span style={{ fontSize: 8, color: '#475569', padding: '1px 5px', border: '1px solid #334155', borderRadius: 3 }}>
                        {lastDecision.decision.engine === 'gemini' ? '🤖 Gemini' : '📐 חוקים v3'}
                      </span>
                    )}
                  </div>
                  <div style={{ fontSize: 14, color: '#e2e8f0', fontWeight: 800, marginBottom: 4 }}>
                    {lastDecision.decision.action === 'BUY' ? '🟢' : lastDecision.decision.action === 'SELL' ? '🔴' : '⏸'}
                    {' '}{lastDecision.decision.action} {lastDecision.decision.ticker || ''}
                    {lastDecision.decision.confidence > 0 && (
                      <span style={{ fontSize: 11, color: A, fontWeight: 600 }}> ({lastDecision.decision.confidence}%)</span>
                    )}
                  </div>
                  {lastDecision.decision.reason && <div style={{ fontSize: 11, color: '#94a3b8' }}>📝 {lastDecision.decision.reason}</div>}
                  {lastDecision.decision.analysis && <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>📊 {lastDecision.decision.analysis}</div>}
                  {lastDecision.executed && <div style={{ fontSize: 11, color: W, marginTop: 4, fontWeight: 700 }}>✅ העסקה בוצעה!</div>}
                  {lastDecision.error && <div style={{ fontSize: 10, color: L, marginTop: 2 }}>⚠️ {lastDecision.error}</div>}
                  {lastDecision.closed_trades?.length > 0 && (
                    <div style={{ marginTop: 4, fontSize: 10, color: '#fbbf24' }}>
                      🔄 {lastDecision.closed_trades.length} פוזיציות נסגרו אוטומטית
                    </div>
                  )}
                </div>
              )}

              {/* Exit Suggestions */}
              {lastDecision?.decision?.exit_suggestions?.length > 0 && (
                <div style={{ background: '#1a0a00', borderRadius: 8, padding: '10px 12px', border: '1px solid #78350f', marginBottom: 8 }}>
                  <div style={{ fontSize: 10, color: '#fbbf24', fontWeight: 700, marginBottom: 6 }}>⚠️ המלצות יציאה חכמות</div>
                  {lastDecision.decision.exit_suggestions.map((s, i) => (
                    <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 10, padding: '3px 0', borderBottom: i < lastDecision.decision.exit_suggestions.length - 1 ? '1px solid #1e293b' : 'none' }}>
                      <span style={{ fontWeight: 800, color: '#f8fafc' }}>{s.ticker}</span>
                      <span style={{ color: s.urgency === 'high' ? L : s.urgency === 'medium' ? '#fbbf24' : '#64748b', fontSize: 9, padding: '1px 4px', borderRadius: 2, background: s.urgency === 'high' ? '#2a0000' : 'transparent' }}>
                        {s.urgency === 'high' ? '🔴 דחוף' : s.urgency === 'medium' ? '🟡 בינוני' : '⚪ נמוך'}
                      </span>
                      <span style={{ color: '#94a3b8', flex: 1 }}>{s.reason}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Strategy Parameters */}
              <div style={{ background: '#0f172a', borderRadius: 8, padding: '10px 12px', border: '1px solid #1e293b', marginBottom: 8 }}>
                <div style={{ fontSize: 10, color: '#f59e0b', fontWeight: 700, marginBottom: 6 }}>⚡ אסטרטגיה: Short Squeeze Aggressive</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, fontSize: 9 }}>
                  {[
                    { label: 'מקסימום לפוזיציה', value: '25%', color: '#fbbf24' },
                    { label: 'מגבלת הפסד יומי', value: '8%', color: '#fbbf24' },
                    { label: 'Stop Loss ברירת מחדל', value: '7%', color: '#f87171' },
                    { label: 'Target ברירת מחדל', value: '15%', color: '#4ade80' },
                    { label: 'מקסימום פוזיציות', value: '4', color: '#60a5fa' },
                    { label: 'Trailing Stop', value: 'ATR×2', color: '#818cf8' },
                    { label: 'Partial TP', value: '40% @+7%', color: '#a78bfa' },
                    { label: 'TTM Squeeze', value: '×1.5', color: '#ef4444' },
                    { label: 'Days to Cover', value: '×1.4', color: '#f97316' },
                    { label: 'Momentum Accel', value: '×1.3', color: '#eab308' },
                    { label: 'Short Squeeze', value: '×1.8', color: '#f59e0b' },
                    { label: 'Insider Trading', value: '×1.2', color: '#a855f7' },
                    { label: 'Monster Combo', value: '×1.4 bonus', color: '#dc2626' },
                  ].map((p, i) => (
                    <div key={i} style={{ display: 'flex', justifyContent: 'space-between', padding: '3px 6px', background: '#060c18', borderRadius: 3, border: '1px solid #1e293b' }}>
                      <span style={{ color: '#94a3b8' }}>{p.label}</span>
                      <span style={{ color: p.color, fontWeight: 700, fontFamily: 'monospace' }}>{p.value}</span>
                    </div>
                  ))}
                </div>
              </div>

              {/* Intelligence Modules */}
              <div style={{ background: '#0f172a', borderRadius: 8, padding: '10px 12px', border: '1px solid #1e293b', marginBottom: 8 }}>
                <div style={{ fontSize: 10, color: A, fontWeight: 700, marginBottom: 6 }}>🧩 13 מודולי אינטליגנציה</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
                  {[
                    { name: 'TTM Squeeze', icon: '💥', desc: 'BB/KC דחיסה → פיצוץ', hot: true },
                    { name: 'Days to Cover', icon: '⏰', desc: 'לחץ סקוויז לפי ימי כיסוי', hot: true },
                    { name: 'Momentum Accel', icon: '⚡', desc: '5m>10m>30m תאוצה', hot: true },
                    { name: 'ATR Stops', icon: '📐', desc: 'סטופים אדפטיביים לתנודתיות', hot: true },
                    { name: 'Short Squeeze', icon: '🩳', desc: 'שורט גבוה + מומנטום + נפח', hot: true },
                    { name: 'Insider Trading', icon: '🏷️', desc: 'קניות/מכירות אנשי פנים', hot: true },
                    { name: 'ניקוד מומנטום', icon: '🚀', desc: 'מחיר, Gap, נפח' },
                    { name: 'ניתוח פונדמנטלי', icon: '📊', desc: 'Health, RSI, EPS' },
                    { name: 'זיהוי קטליסטים', icon: '⚡', desc: 'דוחות, שדרוגים, FDA' },
                    { name: 'משטר שוק', icon: '🌍', desc: 'שורי/דובי/תנודתי' },
                    { name: 'ניתוח סנטימנט', icon: '📰', desc: 'NLP על חדשות' },
                    { name: 'מגמה רב-מסגרת', icon: '📈', desc: 'SMA 20/50/200' },
                    { name: 'יציאות חכמות', icon: '🎯', desc: 'Time decay, RSI fade' },
                  ].map((m, i) => (
                    <div key={i} style={{ display: 'flex', gap: 6, alignItems: 'center', padding: '4px 6px', background: m.hot ? '#1a0a00' : '#060c18', borderRadius: 4, border: `1px solid ${m.hot ? '#78350f' : '#1e293b'}` }}>
                      <span style={{ fontSize: 14 }}>{m.icon}</span>
                      <div>
                        <div style={{ fontSize: 9, color: m.hot ? '#fbbf24' : '#e2e8f0', fontWeight: 600 }}>{m.name}</div>
                        <div style={{ fontSize: 8, color: '#475569' }}>{m.desc}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Risk Features */}
              <div style={{ background: '#0f172a', borderRadius: 8, padding: '10px 12px', border: '1px solid #1e293b' }}>
                <div style={{ fontSize: 10, color: A, fontWeight: 700, marginBottom: 6 }}>🛡️ ניהול סיכון אגרסיבי</div>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                  {['ATR Trail Stop', 'Partial TP @7%', 'Vol Sizing', 'הגנת רצף', 'למידה עצמית', 'Sector Diversity', 'Squeeze Boost', 'Monster Combo'].map((f, i) => (
                    <span key={i} style={{ fontSize: 8, padding: '2px 6px', borderRadius: 3, background: (f.includes('ATR') || f.includes('Monster')) ? '#1a0a00' : '#052e16', color: (f.includes('ATR') || f.includes('Monster')) ? '#fbbf24' : W, border: `1px solid ${(f.includes('ATR') || f.includes('Monster')) ? '#78350f' : '#166534'}` }}>
                      {f}
                    </span>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
      </div>
    </div>
  );

  if (mode === 'floating' || mode === 'header') {
    return (
      <>
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', zIndex: 49, backdropFilter: 'blur(4px)' }} onClick={() => setExpanded(false)} />
        <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 50, maxHeight: '85vh', display: 'flex', flexDirection: 'column' }}>
          {expandedPanel}
        </div>
      </>
    );
  }
  return expandedPanel;
}

const INITIAL_CAPITAL = 3000;

export default function FinvizTableScanner({ ensureTickers, refreshSec: refreshSecProp }) {
  const effectiveRefreshSec = (refreshSecProp != null && refreshSecProp >= 0) ? refreshSecProp : REFRESH_SEC;
  // ברירת מחדל: כולל מניות כמו AAOI (RSI Any, Mid+)
  const [mcap,   setMcap]   = useState('');
  const [avgvol, setAvgvol] = useState('sh_avgvol_o200');
  const [relvol, setRelvol] = useState('');
  const [curvol, setCurvol] = useState('');  // Any — מניות כמו AAOI עם נפח יומי נמוך יופיעו
  const [change, setChange] = useState('ta_change_u');
  const [changeopen, setChangeopen] = useState('');
  const [customChangePct, setCustomChangePct] = useState('3');
  const [showChangeList, setShowChangeList] = useState(false);
  const [shortf, setShortf] = useState('');
  const [rsi,    setRsi]    = useState('');  // Any — כדי לכלול מניות עם RSI גבוה (למשל AAOI)
  const [inst,   setInst]   = useState('');
  const [salesqq, setSalesqq] = useState('');
  const [gap,    setGap]     = useState('');
  const [sma50,  setSma50]   = useState('');
  const [sma200, setSma200]  = useState('');
  const [earnings, setEarnings] = useState('');
  const [sort,   setSort]   = useState({ col: 'change_pct', dir: 'desc' });
  const [colFilter, setColFilter] = useState({});        // { col: string[] } — בחירה מרובה לכל עמודה
  const [colFilterOpen, setColFilterOpen] = useState(null); // col name of open dropdown
  const [isMobile, setIsMobile] = useState(() => typeof window !== 'undefined' && window.innerWidth < 768);
  useEffect(() => {
    const handler = () => setIsMobile(window.innerWidth < 768);
    window.addEventListener('resize', handler);
    return () => window.removeEventListener('resize', handler);
  }, []);
  const [expanded, setExpanded] = useState(new Set());
  const [countdown, setCountdown] = useState(effectiveRefreshSec || 30);
  const countdownRef = useRef(effectiveRefreshSec || 30);

  // ── Live data from Finviz (price, change%, volume, market cap) ──────────────
  const [livePrices, setLivePrices] = useState({});           // {ticker: {price, change_pct, volume, volume_str, market_cap_str}}
  const [priceFlashes, setPriceFlashes] = useState({});       // {ticker: 'up'|'down'}
  const prevLivePricesRef = useRef({});
  const screenerTickersRef = useRef([]);

  const filters = buildFilters(mcap, avgvol, relvol, curvol, change, changeopen, shortf, rsi, inst, salesqq, gap, sma50, sma200, earnings);

  // ensureTickers: טיקרים לחיזוק — אם לא בסורק, נשלוף אותם בנפרד (למשל חיפוש AAOI)
  const ensureParam = ensureTickers ? `&ensure_tickers=${encodeURIComponent(ensureTickers)}` : '';

  const { data, isLoading, isError, dataUpdatedAt, refetch } = useQuery({
    queryKey: ['finvizTable', filters, ensureTickers],
    queryFn: async () => {
      const r = await api.get(`/screener/finviz-table?filters=${encodeURIComponent(filters)}${ensureParam}`);
      if (r.status === 202 || r.data?.loading) {
        throw new Error('scan_in_progress');
      }
      return r.data;
    },
    refetchInterval: effectiveRefreshSec > 0 ? effectiveRefreshSec * 1000 : false,
    staleTime: 15000,
    retry: (failureCount, error) => {
      if (error?.message === 'scan_in_progress') return failureCount < 24; // 2 min
      return failureCount < 2;
    },
    retryDelay: (attempt, error) => {
      if (error?.message === 'scan_in_progress') return 5000;
      return Math.min(1000 * 2 ** attempt, 10000);
    },
    keepPreviousData: true,
  });

  // Detect if we're in "first scan" loading state (repeated scan_in_progress retries)
  const [scanAttempts, setScanAttempts] = useState(0);
  useEffect(() => {
    if (isError) setScanAttempts(v => v + 1);
    else setScanAttempts(0);
  }, [isError, dataUpdatedAt]);
  const isFirstScanLoading = isError && !stocks.length && scanAttempts > 0;

  // Reset countdown when data updates
  useEffect(() => {
    countdownRef.current = effectiveRefreshSec || 30;
    setCountdown(effectiveRefreshSec || 30);
  }, [dataUpdatedAt, effectiveRefreshSec]);

  // Tick countdown every second (paused when effectiveRefreshSec === 0)
  useEffect(() => {
    if (!effectiveRefreshSec) return;
    const id = setInterval(() => {
      countdownRef.current = Math.max(0, countdownRef.current - 1);
      setCountdown(countdownRef.current);
    }, 1000);
    return () => clearInterval(id);
  }, [effectiveRefreshSec]);

  const stocks  = data?.stocks || [];

  // Keep screener tickers ref in sync (used by live poll)
  useEffect(() => {
    screenerTickersRef.current = stocks.map(s => s.ticker);
  }, [stocks]);

  // התראה קופצת: מניה שעלתה מעל 7% בחצי שעה האחרונה
  const alerted30mRef = useRef(new Set());
  useEffect(() => {
    if (!stocks.length) return;
    const parseChg = (v) => {
      if (v == null) return null;
      const n = typeof v === 'number' ? v : parseFloat(String(v).replace(/[%,]/g, ''));
      return Number.isFinite(n) ? n : null;
    };
    const over7 = stocks.filter(s => {
      const chg = parseChg(s.chg_30m);
      return chg != null && chg >= 7;
    });
    if (!over7.length) return;
    const newTickers = over7.map(s => s.ticker).filter(t => !alerted30mRef.current.has(t));
    if (!newTickers.length) return;
    newTickers.forEach(t => alerted30mRef.current.add(t));
    const list = over7.map(s => `${s.ticker} ${parseChg(s.chg_30m) >= 0 ? '+' : ''}${parseChg(s.chg_30m).toFixed(1)}%`).join('\n');
    window.alert(`🚀 עלייה מעל 7% ב-30 דקות:\n\n${list}`);
  }, [stocks]);

  // Live price polling — 5s בפרה/אפטר, 10s ברגיל (pre/post market aware)
  const pollInterval = useMemo(() => {
    const s = getClientSession();
    return (s === 'pre' || s === 'post') ? 8_000 : 15_000;
  }, [dataUpdatedAt]); // מתעדכן כשהנתונים מתעדכנים (session יכול להשתנות)
  useEffect(() => {
    const poll = async () => {
      const tickers = screenerTickersRef.current;
      if (!tickers.length) return;
      try {
        const r = await api.get(`/screener/live-prices?tickers=${tickers.slice(0, 25).join(',')}`);
        const newPrices = r.data;
        if (!newPrices || !Object.keys(newPrices).length) return;

        // Detect changes → flash
        const flashes = {};
        Object.entries(newPrices).forEach(([ticker, d]) => {
          const prev = prevLivePricesRef.current[ticker]?.price;
          const cur  = d?.price;
          if (prev != null && cur != null && Math.abs(cur - prev) > 0.001) {
            flashes[ticker] = cur > prev ? 'up' : 'down';
          }
        });

        prevLivePricesRef.current = newPrices;
        setLivePrices(newPrices);

        if (Object.keys(flashes).length) {
          setPriceFlashes(flashes);
          setTimeout(() => setPriceFlashes({}), 700);
        }
      } catch (_) {}
    };

    poll();
    const id = setInterval(poll, pollInterval);
    return () => clearInterval(id);
  }, [pollInterval]); // 5s פרה/אפטר, 10s רגיל
  // Session: prefer client-side time (always fresh), use API response as fallback
  const session = useMemo(() => data ? getClientSession() : 'regular', [dataUpdatedAt]); // eslint-disable-line
  const sessionMeta = SESSION_META[session] || SESSION_META.regular;
  const isExtended  = session === 'pre' || session === 'post';

  const sorted = useMemo(() => {
    if (!stocks.length) return [];
    let list = stocks.filter(s => {
      const t = (s.ticker != null ? String(s.ticker).trim() : '');
      if (!t) return false;
      if (/^\d+$/.test(t)) return false; // טיקר שהוא רק ספרות (למשל "6") — שגיאה מהשרת, לא להציג
      return true;
    });
    // הסרת כפילויות לפי טיקר (משאירים רק הופעה ראשונה)
    const seen = new Set();
    list = list.filter(s => {
      const t = (s.ticker || '').trim().toUpperCase();
      if (seen.has(t)) return false;
      seen.add(t);
      return true;
    });
    // סינון לפי ערך שינוי מותאם (ידני)
    if (change === 'custom' && customChangePct !== '' && !isNaN(parseFloat(customChangePct))) {
      const minPct = parseFloat(customChangePct);
      list = list.filter(s => {
        const chg = isExtended && s.extended_chg_pct != null ? parseFloat(s.extended_chg_pct) : parseFloat(s.change_pct);
        return !isNaN(chg) && chg >= minPct;
      });
    }
    // ── Column filters (בחירה מורחבת — מערך ערכים, שורה עוברת אם מתאימה לאחד מהערכים) ──
    const arr = (col, def) => {
      const v = colFilter[col];
      if (!v) return def ? [def] : [];
      return Array.isArray(v) ? v : [v];
    };
    const squeezeArr = arr('squeeze_total_score');
    if (squeezeArr.length > 0) {
      list = list.filter(s => squeezeArr.some(f => {
        if (f === 'catalyst_squeeze') return s.squeeze_has_catalyst && (s.squeeze_stage === 'firing' || s.squeeze_stage === 'compression');
        if (f === 'none')             return !s.squeeze_stage || s.squeeze_stage === 'none';
        return s.squeeze_stage === f;
      }));
    }
    const techArr = arr('tech_score');
    if (techArr.length > 0) {
      list = list.filter(s => {
        const sig = (s.tech_signal || '').toLowerCase();
        return techArr.some(f => {
          if (f === 'strong_buy')  return sig.includes('strong buy');
          if (f === 'buy')         return sig.includes('buy') && !sig.includes('strong');
          if (f === 'neutral')     return sig.includes('neutral');
          if (f === 'sell')        return sig.includes('sell') && !sig.includes('strong');
          if (f === 'strong_sell') return sig.includes('strong sell');
          return false;
        });
      });
    }
    const rsiArr = arr('rsi');
    if (rsiArr.length > 0) {
      list = list.filter(s => {
        const r = parseFloat(s.rsi);
        if (isNaN(r)) return false;
        return rsiArr.some(f => {
          if (f === 'overbought') return r > 70;
          if (f === 'normal')     return r >= 30 && r <= 70;
          if (f === 'oversold')   return r < 30;
          return false;
        });
      });
    }
    const shortFloatArr = arr('short_float');
    if (shortFloatArr.length > 0) {
      list = list.filter(s => {
        const sf = parseFloat(s.short_float);
        if (isNaN(sf)) return false;
        return shortFloatArr.some(f => {
          if (f === 'sh_high')    return sf > 20;
          if (f === 'sh_mid')     return sf >= 10 && sf <= 20;
          if (f === 'sh_low')     return sf >= 5 && sf < 10;
          if (f === 'sh_minimal') return sf < 5;
          return false;
        });
      });
    }
    const relVolArr = arr('rel_volume');
    if (relVolArr.length > 0) {
      list = list.filter(s => {
        const rv = parseFloat(s.rel_volume);
        if (isNaN(rv)) return false;
        return relVolArr.some(f => {
          if (f === 'rv_extreme') return rv > 3;
          if (f === 'rv_high')    return rv >= 2 && rv <= 3;
          if (f === 'rv_normal')  return rv >= 1 && rv < 2;
          if (f === 'rv_low')     return rv < 1;
          return false;
        });
      });
    }
    const changePctArr = arr('change_pct');
    if (changePctArr.length > 0) {
      list = list.filter(s => {
        const chgVal = parseFloat(isExtended && s.extended_chg_pct != null ? s.extended_chg_pct : s.change_pct);
        if (isNaN(chgVal)) return false;
        return changePctArr.some(f => {
          if (f === 'chg_huge') return chgVal > 10;
          if (f === 'chg_high') return chgVal >= 5 && chgVal <= 10;
          if (f === 'chg_mid')  return chgVal >= 2 && chgVal < 5;
          if (f === 'chg_neg')  return chgVal < 0;
          return false;
        });
      });
    }
    const mcapArr = arr('market_cap');
    if (mcapArr.length > 0) {
      list = list.filter(s => {
        const mc = parseFloat(s.market_cap_num || s.market_cap) / 1e9;
        if (isNaN(mc)) return false;
        return mcapArr.some(f => {
          if (f === 'mega')  return mc >= 200;
          if (f === 'large') return mc >= 10 && mc < 200;
          if (f === 'mid')   return mc >= 2 && mc < 10;
          if (f === 'small') return mc >= 0.3 && mc < 2;
          if (f === 'micro') return mc < 0.3;
          return false;
        });
      });
    }
    const healthArr = arr('health_score');
    if (healthArr.length > 0) {
      list = list.filter(s => {
        const hs = parseFloat(s.health_score);
        if (isNaN(hs)) return false;
        return healthArr.some(f => {
          if (f === 'health_excel') return hs > 85;
          if (f === 'health_good')  return hs >= 70 && hs <= 85;
          if (f === 'health_fair')  return hs >= 50 && hs < 70;
          if (f === 'health_poor')  return hs < 50;
          return false;
        });
      });
    }
    const chg30mArr = arr('chg_30m');
    if (chg30mArr.length > 0) {
      list = list.filter(s => {
        const m = parseFloat(s.chg_30m);
        if (isNaN(m)) return false;
        return chg30mArr.some(f => {
          if (f === 'mom_strong') return m > 3;
          if (f === 'mom_mid')    return m >= 1 && m <= 3;
          if (f === 'mom_flat')   return m >= -1 && m < 1;
          if (f === 'mom_neg')    return m < -1;
          return false;
        });
      });
    }
    const atrArr = arr('atr');
    if (atrArr.length > 0) {
      list = list.filter(s => {
        const atrVal = parseFloat(s.atr);
        if (isNaN(atrVal) || atrVal === 0) return false;
        return atrArr.some(f => {
          if (f.startsWith('o')) return atrVal > parseFloat(f.slice(1));
          if (f.startsWith('u')) return atrVal < parseFloat(f.slice(1));
          return false;
        });
      });
    }
    // ── Sort ──────────────────────────────────────────────────────────────────
    return list.sort((a, b) => {
      let av = a[sort.col], bv = b[sort.col];
      if (sort.col === 'change_pct' && isExtended) {
        av = a.extended_chg_pct != null ? a.extended_chg_pct : av;
        bv = b.extended_chg_pct != null ? b.extended_chg_pct : bv;
      }
      av = parseFloat(av); bv = parseFloat(bv);
      av = isNaN(av) ? -Infinity : av;
      bv = isNaN(bv) ? -Infinity : bv;
      return sort.dir === 'desc' ? bv - av : av - bv;
    });
  }, [stocks, sort, change, customChangePct, isExtended, colFilter]);

  const handleSort = useCallback((col) => {
    setSort(prev => ({ col, dir: prev.col === col && prev.dir === 'desc' ? 'asc' : 'desc' }));
  }, []);

  const toggleExpand = useCallback((ticker, e) => {
    e.stopPropagation();
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(ticker) ? next.delete(ticker) : next.add(ticker);
      return next;
    });
  }, []);

  // Close column filter dropdown on outside click
  useEffect(() => {
    if (!colFilterOpen) return;
    const close = () => setColFilterOpen(null);
    document.addEventListener('click', close);
    return () => document.removeEventListener('click', close);
  }, [colFilterOpen]);

  // בחירה מורחבת: כל עמודה — מערך ערכים. לחיצה על "הכל" מנקה; על אפשרות — מוסיפה/מסירה (toggle).
  const handleColFilterToggle = useCallback((col, value) => {
    setColFilter(prev => {
      const arr = Array.isArray(prev[col]) ? prev[col] : (prev[col] ? [prev[col]] : []);
      if (value === '') return { ...prev, [col]: [] };
      const next = arr.includes(value) ? arr.filter(v => v !== value) : [...arr, value];
      return { ...prev, [col]: next };
    });
  }, []);

  const perfRankMap = useMemo(() => {
    if (!sorted.length) return {};
    const byPerf = [...sorted].sort((a, b) => {
      const aChg = parseFloat(livePrices[a.ticker]?.change_pct ?? a.change_pct) || 0;
      const bChg = parseFloat(livePrices[b.ticker]?.change_pct ?? b.change_pct) || 0;
      return bChg - aChg;
    });
    const map = {};
    byPerf.forEach((s, i) => { map[s.ticker] = i + 1; });
    return map;
  }, [sorted, livePrices]);

  const COL_COUNT = 16;
  const stockMap = useMemo(() => {
    const m = {};
    stocks.forEach(s => { if (s.price) m[s.ticker] = s.price; });
    return m;
  }, [stocks]);

  // TH_BASE / TD_BASE defined as module-level constants (TH_BASE / TD_BASE)

  // ── Value Scanner — מניות עם יתרון פונדמנטלי ──
  const valuePlays = useMemo(() => {
    if (!stocks.length) return { cashPlays: [], deepValue: [], evUnderMc: [], valueMomentum: [] };
    const cashPlays = [];
    const deepValue = [];
    const evUnderMc = [];
    stocks.forEach(s => {
      const price = parseFloat(s.price);
      if (!price || price <= 0) return;
      const chg = parseFloat(s.change_pct) || 0;
      const cash = parseFloat(s.cash_per_share);
      if (cash > 0 && cash / price >= 0.3) {
        cashPlays.push({ ...s, _cash_ratio: cash / price, _chg: chg });
      }
      const book = parseFloat(s.book_per_share);
      if (book > 0 && price < book) {
        deepValue.push({ ...s, _discount_pct: ((book - price) / book * 100), _chg: chg });
      }
      const evRatio = parseFloat(s.ev_mc_ratio);
      if (!isNaN(evRatio) && evRatio > 0 && evRatio < 1.0) {
        evUnderMc.push({ ...s, _ev_ratio: evRatio, _chg: chg });
      }
    });
    // Sort: positive movers first, then by value metric
    const sortVal = (arr, key, asc = false) => arr.sort((a, b) => {
      const aMov = a._chg > 0 ? 1 : 0, bMov = b._chg > 0 ? 1 : 0;
      if (aMov !== bMov) return bMov - aMov;
      return asc ? a[key] - b[key] : b[key] - a[key];
    });
    sortVal(cashPlays, '_cash_ratio');
    sortVal(deepValue, '_discount_pct');
    sortVal(evUnderMc, '_ev_ratio', true);
    // Value Momentum: any value play moving +2%+ today
    const valueTickers = new Set([...cashPlays, ...deepValue, ...evUnderMc].map(s => s.ticker));
    const valueMomentum = stocks
      .filter(s => valueTickers.has(s.ticker) && parseFloat(s.change_pct) >= 2)
      .map(s => ({
        ...s,
        _chg: parseFloat(s.change_pct),
        _cats: [
          cashPlays.find(c => c.ticker === s.ticker) ? '💰' : null,
          deepValue.find(d => d.ticker === s.ticker) ? '📘' : null,
          evUnderMc.find(e => e.ticker === s.ticker) ? '🏦' : null,
        ].filter(Boolean),
        _cashRatio: cashPlays.find(c => c.ticker === s.ticker)?._cash_ratio,
        _disc: deepValue.find(d => d.ticker === s.ticker)?._discount_pct,
        _evRatio: evUnderMc.find(e => e.ticker === s.ticker)?._ev_ratio,
      }))
      .sort((a, b) => b._chg - a._chg)
      .slice(0, 8);
    return {
      cashPlays: cashPlays.slice(0, 8),
      deepValue: deepValue.slice(0, 8),
      evUnderMc: evUnderMc.slice(0, 8),
      valueMomentum,
    };
  }, [stocks]);

  // ── Sector & Industry performance from stocks ──
  const sectorPerf = useMemo(() => {
    if (!stocks.length) return { sectors: [], industries: [] };
    const parsePct = v => { const n = parseFloat(String(v).replace('%','')); return isNaN(n) ? null : n; };
    const sectorMap = {};
    const industryMap = {};
    stocks.forEach(s => {
      const sec = s.sector;
      const ind = s.industry;
      const chg = parsePct(s.change_pct);
      const w = parsePct(s.perf_week);
      const m = parsePct(s.perf_month);
      if (sec && chg !== null) {
        if (!sectorMap[sec]) sectorMap[sec] = { name: sec, count: 0, day_sum: 0, week_sum: 0, week_n: 0, month_sum: 0, month_n: 0, top: null };
        const b = sectorMap[sec];
        b.count++; b.day_sum += chg;
        if (w !== null) { b.week_sum += w; b.week_n++; }
        if (m !== null) { b.month_sum += m; b.month_n++; }
        if (!b.top || chg > parsePct(b.top.change_pct)) b.top = s;
      }
      if (ind && chg !== null) {
        if (!industryMap[ind]) industryMap[ind] = { name: ind, sector: sec, count: 0, day_sum: 0, week_sum: 0, week_n: 0, month_sum: 0, month_n: 0, top: null };
        const b = industryMap[ind];
        b.count++; b.day_sum += chg;
        if (w !== null) { b.week_sum += w; b.week_n++; }
        if (m !== null) { b.month_sum += m; b.month_n++; }
        if (!b.top || chg > parsePct(b.top.change_pct)) b.top = s;
      }
    });
    const finalize = obj => {
      obj.day_avg = obj.count ? +(obj.day_sum / obj.count).toFixed(2) : 0;
      obj.week_avg = obj.week_n ? +(obj.week_sum / obj.week_n).toFixed(2) : null;
      obj.month_avg = obj.month_n ? +(obj.month_sum / obj.month_n).toFixed(2) : null;
    };
    Object.values(sectorMap).forEach(finalize);
    Object.values(industryMap).forEach(finalize);
    const sectors = Object.values(sectorMap).filter(s => s.count >= 5).sort((a, b) => b.day_avg - a.day_avg);
    const industries = Object.values(industryMap).filter(s => s.count >= 3).sort((a, b) => b.day_avg - a.day_avg);
    return { sectors, industries };
  }, [stocks]);

  const [valueExpanded, setValueExpanded] = useState(true);
  const hasValuePlays = valuePlays.cashPlays.length > 0 || valuePlays.deepValue.length > 0 || valuePlays.evUnderMc.length > 0 || valuePlays.valueMomentum.length > 0;

  return (
    <div
      style={{
        color: '#e2e8f0',
        background: '#0f172a',
        border: '1px solid rgba(51,65,85,0.5)',
        borderRadius: 16,
        overflow: 'hidden',
        boxShadow: '0 4px 24px rgba(0,0,0,0.3), 0 0 0 1px rgba(51,65,85,0.2)',
      }}
      dir="rtl"
    >
      {/* ── Header bar ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '14px 20px',
          background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
          borderBottom: '1px solid #334155',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <div style={{ width: 8, height: 28, borderRadius: 4, background: 'linear-gradient(180deg, #3b82f6, #8b5cf6)' }} />
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 800, color: '#f1f5f9', margin: 0, letterSpacing: '0.06em' }}>
              STOCK SCREENER
            </h2>
            {data && (
              <div style={{ fontSize: 10, color: '#64748b', marginTop: 2, display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>
                  {sorted.length !== stocks.filter(s => s.ticker && !/^\d+$/.test(s.ticker)).length
                    ? <><span style={{ color: '#fbbf24', fontWeight: 700 }}>{sorted.length}</span> מתוך {stocks.filter(s => s.ticker && !/^\d+$/.test(s.ticker)).length} מניות</>
                    : <>{sorted.length} מניות</>
                  }
                  {effectiveRefreshSec > 0 ? ` · כל ${effectiveRefreshSec}s` : ' · ידני'}
                </span>
                {Object.values(colFilter).some(v => Array.isArray(v) ? v.length > 0 : Boolean(v)) && (
                  <button
                    onClick={() => setColFilter({})}
                    title="נקה את כל פילטרי העמודות"
                    style={{
                      fontSize: 10, padding: '1px 7px', borderRadius: 5,
                      background: 'rgba(251,191,36,0.15)',
                      border: '1px solid rgba(251,191,36,0.4)',
                      color: '#fbbf24', cursor: 'pointer', fontWeight: 700,
                    }}>
                    × נקה פילטרים
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          {data && (
            <span className="session-badge" style={{
              fontSize: 11, padding: '4px 10px', borderRadius: 8,
              background: sessionMeta.bg, color: sessionMeta.color,
              fontWeight: 700, border: `1px solid ${sessionMeta.border}`,
            }}>
              {sessionMeta.label}
            </span>
          )}
          {isLoading && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <div style={{ width: 14, height: 14, border: '2px solid #334155', borderTopColor: '#60a5fa', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
              <span style={{ fontSize: 11, color: '#60a5fa' }}>סורק...</span>
            </div>
          )}
          <div style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '4px 10px', borderRadius: 8,
            background: 'rgba(30,41,59,0.5)', border: '1px solid #1e293b',
          }}>
            <CountdownRing seconds={countdown} total={effectiveRefreshSec || 30} />
            <span style={{ fontSize: 12, color: '#64748b', fontFamily: 'monospace', minWidth: 22, textAlign: 'center' }}>{countdown}s</span>
            <button
              onClick={() => { refetch(); countdownRef.current = effectiveRefreshSec || 30; setCountdown(effectiveRefreshSec || 30); }}
              disabled={isLoading}
              style={{
                fontSize: 11, padding: '5px 14px', borderRadius: 6,
                background: isLoading ? '#1e293b' : 'linear-gradient(135deg, #3b82f6, #2563eb)',
                border: 'none', color: '#fff', cursor: isLoading ? 'not-allowed' : 'pointer',
                opacity: isLoading ? 0.5 : 1, fontWeight: 600, transition: 'all 0.2s ease',
              }}
            >
              ⟳ רענן
            </button>
          </div>
        </div>
      </div>

      {/* ── Filters ── */}
      <div style={{
        padding: '10px 20px',
        background: 'rgba(15,23,42,0.8)',
        borderBottom: '1px solid rgba(51,65,85,0.5)',
        display: 'flex',
        flexWrap: 'wrap',
        alignItems: 'center',
        gap: '6px 14px',
        backdropFilter: 'blur(8px)',
      }}>
        <FilterItem label="Market Cap." options={MCAP_OPTS} value={mcap} onChange={v => { setMcap(v); setExpanded(new Set()); }} />
        <div style={{ width: 1, height: 16, background: '#1e293b', flexShrink: 0 }} />
        <FilterItem label="Avg Vol." options={AVGVOL_OPTS} value={avgvol} onChange={v => { setAvgvol(v); setExpanded(new Set()); }} />
        <FilterItem label="Cur Vol." options={CURVOL_OPTS} value={curvol} onChange={v => { setCurvol(v); setExpanded(new Set()); }} />
        <FilterItem label="Rel Vol." options={RELVOL_OPTS} value={relvol} onChange={v => { setRelvol(v); setExpanded(new Set()); }} />
        <div style={{ width: 1, height: 16, background: '#1e293b', flexShrink: 0 }} />
        <FilterItem label="Chg from Open" options={CHANGEOPEN_OPTS} value={changeopen} onChange={v => { setChangeopen(v); setExpanded(new Set()); }} />
        {/* Change — supports both dropdown and custom % input */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
          <span style={fvLabelStyle(change !== '')}>Change</span>
          {change === 'custom' && !showChangeList ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
              <input
                type="number"
                placeholder="%"
                value={customChangePct}
                onChange={e => setCustomChangePct(e.target.value)}
                min={0} step={0.5}
                style={fvNumInput}
              />
              <button
                type="button"
                onClick={() => setShowChangeList(true)}
                style={{ fontSize: 10, color: '#64748b', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
              >▼</button>
            </div>
          ) : (
            <select
              value={change}
              onChange={e => { const v = e.target.value; setChange(v); if (v === 'custom') setShowChangeList(false); setExpanded(new Set()); }}
              style={fvSelectStyle(change !== '')}
            >
              {CHANGE_OPTS.map(o => (
                <option key={o.value ?? 'any'} value={o.value}>{o.label}</option>
              ))}
            </select>
          )}
        </div>
        <div style={{ width: 1, height: 16, background: '#1e293b', flexShrink: 0 }} />
        <FilterItem label="Sales Q/Q" options={SALESQQ_OPTS} value={salesqq} onChange={v => { setSalesqq(v); setExpanded(new Set()); }} />
        <FilterItem label="Short Float" options={SHORT_OPTS} value={shortf} onChange={v => { setShortf(v); setExpanded(new Set()); }} />
        <FilterItem label="RSI (14)" options={RSI_OPTS} value={rsi} onChange={v => { setRsi(v); setExpanded(new Set()); }} />
        <FilterItem label="Inst. Own." options={INST_OPTS} value={inst} onChange={v => { setInst(v); setExpanded(new Set()); }} />
        <FilterItem label="Gap %" options={GAP_OPTS} value={gap} onChange={v => { setGap(v); setExpanded(new Set()); }} />
        <FilterItem label="ATR%"
          options={COL_FILTER_OPTS.atr}
          value={colFilter.atr?.[0] || ''}
          onChange={v => { setColFilter(prev => v ? { ...prev, atr: [v] } : { ...prev, atr: [] }); setExpanded(new Set()); }}
        />
        <FilterItem label="MA50"  options={SMA50_OPTS}  value={sma50}  onChange={v => { setSma50(v);  setExpanded(new Set()); }} />
        <FilterItem label="MA200" options={SMA200_OPTS} value={sma200} onChange={v => { setSma200(v); setExpanded(new Set()); }} />
        <FilterItem label="📊 דוח" options={EARNINGS_OPTS} value={earnings} onChange={v => { setEarnings(v); setExpanded(new Set()); }} />
      </div>

      {isError && !isFirstScanLoading && (
        <div style={{
          margin: '12px 20px', padding: '12px 16px', background: 'rgba(127,29,29,0.3)',
          color: '#fecaca', fontSize: 12, borderRadius: 10, display: 'flex',
          alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8,
          border: '1px solid rgba(239,68,68,0.3)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 18 }}>⚠️</span>
            <span>שגיאת חיבור — ודא שהשרת רץ ולחץ רענן</span>
          </div>
          <button
            onClick={() => refetch()}
            style={{
              padding: '6px 16px', background: 'linear-gradient(135deg, #dc2626, #b91c1c)',
              border: 'none', color: '#fff', borderRadius: 8, cursor: 'pointer', fontWeight: 600, fontSize: 11,
            }}
          >
            ⟳ נסה שוב
          </button>
        </div>
      )}
      {/* Global animations */}
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes starBlink {
          0%, 100% { background: rgba(34,197,94,0.08); }
          50% { background: rgba(34,197,94,0.25); }
        }
        @keyframes starBorderPulse {
          0%, 100% { border-right-color: rgba(34,197,94,0.5); }
          50% { border-right-color: #4ade80; }
        }
        tr.star-stock td { animation: starBlink 2s ease-in-out infinite; }
        tr.star-stock td:first-child { border-right: 3px solid #22c55e; animation: starBlink 2s ease-in-out infinite, starBorderPulse 2s ease-in-out infinite; }
        .finviz-scroll { scrollbar-width: thin; scrollbar-color: #334155 #0f172a; }
        .finviz-scroll::-webkit-scrollbar { height: 6px; }
        .finviz-scroll::-webkit-scrollbar-track { background: #0f172a; }
        .finviz-scroll::-webkit-scrollbar-thumb { background: #334155; border-radius: 3px; }
        .finviz-scroll::-webkit-scrollbar-thumb:hover { background: #475569; }
        @keyframes flashUp {
          0%   { background: rgba(74,222,128,0.45); }
          100% { background: transparent; }
        }
        @keyframes flashDown {
          0%   { background: rgba(248,113,113,0.45); }
          100% { background: transparent; }
        }
        .price-flash-up   { animation: flashUp 0.7s ease-out; border-radius: 4px; }
        .price-flash-down { animation: flashDown 0.7s ease-out; border-radius: 4px; }
        @keyframes sessionPulse {
          0%, 100% { opacity: 0.8; }
          50% { opacity: 1; }
        }
        .session-badge { animation: sessionPulse 2.5s ease-in-out infinite; }
        .fv-table { border-spacing: 0; }
        .fv-table thead th {
          user-select: none;
          font-weight: 600;
          letter-spacing: 0.045em;
        }
        .fv-table thead tr { box-shadow: 0 1px 0 rgba(51,65,85,0.5); }
        .fv-table td { border-left: 1px solid rgba(30,41,59,0.4); }
        .fv-table td:first-child { border-left: none; }
        .fv-table tbody tr { transition: background 0.12s ease; }
        .fv-table tbody tr:hover td { background: rgba(30,58,95,0.6) !important; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
        .fv-table tbody tr { animation: fadeIn 0.2s ease-out; }
      `}</style>

      {/* ── Value Scanner ── */}
      {stocks.length > 0 && (() => {
        // Mini-card component for value chips
        const ValueCard = ({ s, accentColor, badge, onClick }) => {
          const chg = parseFloat(s.change_pct) || 0;
          const isUp = chg > 0;
          const isDown = chg < 0;
          const chgColor = isUp ? '#4ade80' : isDown ? '#f87171' : '#94a3b8';
          const chgBg = isUp ? 'rgba(74,222,128,0.12)' : isDown ? 'rgba(248,113,113,0.12)' : 'rgba(148,163,184,0.08)';
          return (
            <div
              onClick={onClick}
              title={`${s.company || s.ticker} · ${s.sector || ''}`}
              style={{
                display: 'flex', flexDirection: 'column', gap: 3,
                padding: '6px 10px', borderRadius: 10, cursor: 'pointer',
                background: 'rgba(15,23,42,0.7)',
                border: `1px solid ${accentColor}33`,
                minWidth: 90,
                transition: 'border-color 0.15s',
              }}
              onMouseEnter={e => e.currentTarget.style.borderColor = accentColor + '88'}
              onMouseLeave={e => e.currentTarget.style.borderColor = accentColor + '33'}
            >
              {/* Row 1: Ticker + daily change */}
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6 }}>
                <span style={{ fontWeight: 900, fontSize: 12, color: accentColor, fontFamily: 'monospace', letterSpacing: '0.03em' }}>{s.ticker}</span>
                <span style={{
                  fontSize: 11, fontWeight: 800, color: chgColor,
                  background: chgBg, borderRadius: 5, padding: '1px 5px',
                  fontFamily: 'monospace',
                }}>
                  {isUp ? '▲' : isDown ? '▼' : ''}{isUp ? '+' : ''}{chg.toFixed(1)}%
                </span>
              </div>
              {/* Row 2: Price + value badge */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ fontSize: 9, color: '#64748b', fontFamily: 'monospace' }}>${parseFloat(s.price).toFixed(2)}</span>
                <span style={{ fontSize: 9, fontWeight: 700, color: accentColor, background: accentColor + '22', borderRadius: 4, padding: '1px 4px' }}>{badge}</span>
              </div>
            </div>
          );
        };

        const clickTicker = s => setExpanded(prev => { const n = new Set(prev); n.has(s.ticker) ? n.delete(s.ticker) : n.add(s.ticker); return n; });

        return (
          <div style={{ margin: '10px 16px 0', borderRadius: 12, border: '1px solid rgba(59,130,246,0.2)', background: 'rgba(15,23,42,0.8)', overflow: 'hidden' }}>
            <button
              onClick={() => setValueExpanded(v => !v)}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 8, padding: '8px 14px',
                background: 'linear-gradient(135deg, rgba(15,23,42,0.9), rgba(30,41,59,0.8))',
                border: 'none', borderBottom: valueExpanded ? '1px solid rgba(51,65,85,0.4)' : 'none',
                cursor: 'pointer', color: '#e2e8f0', textAlign: 'right',
              }}
            >
              <span style={{ fontSize: 13, fontWeight: 800, color: '#38bdf8', letterSpacing: '0.05em' }}>💎 VALUE SCANNER</span>
              {valuePlays.valueMomentum.length > 0 && (
                <span style={{ fontSize: 10, fontWeight: 700, color: '#4ade80', background: 'rgba(74,222,128,0.12)', borderRadius: 6, padding: '2px 7px', border: '1px solid rgba(74,222,128,0.25)' }}>
                  🚀 {valuePlays.valueMomentum.length} עולות היום
                </span>
              )}
              <span style={{ fontSize: 10, color: '#475569', flex: 1 }}>מניות עם יתרון פונדמנטלי</span>
              <span style={{ fontSize: 11, color: '#475569', transform: valueExpanded ? 'rotate(90deg)' : 'rotate(-90deg)', transition: 'transform 0.2s' }}>›</span>
            </button>
            {valueExpanded && (
              <div style={{ padding: '10px 14px 12px', display: 'flex', flexDirection: 'column', gap: 12 }}>

                {!hasValuePlays && (
                  <div style={{ fontSize: 11, color: '#475569', textAlign: 'center', padding: '8px 0' }}>
                    אין מניות עם יתרון value בסריקה הנוכחית
                  </div>
                )}

                {/* 🚀 Value Momentum — value plays moving up today */}
                {valuePlays.valueMomentum.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, fontWeight: 700, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span style={{ color: '#4ade80' }}>🚀 Value + Momentum</span>
                      <span style={{ fontWeight: 400, color: '#64748b' }}>— מניות value שעולות +2% היום</span>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {valuePlays.valueMomentum.map(s => {
                        const metricBadge = s._cats.length > 1
                          ? s._cats.join(' ')
                          : s._cashRatio ? `💰 cash ${(s._cashRatio * 100).toFixed(0)}%`
                            : s._disc ? `📘 -${s._disc.toFixed(0)}% book`
                              : s._evRatio ? `🏦 EV ${s._evRatio.toFixed(2)}x` : s._cats[0];
                        return (
                          <ValueCard key={s.ticker} s={s} accentColor="#4ade80" badge={metricBadge} onClick={() => clickTicker(s)} />
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* 💰 Cash Play */}
                {valuePlays.cashPlays.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, color: '#fbbf24', fontWeight: 700, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span>💰 Cash Play</span>
                      <span style={{ fontWeight: 400, color: '#64748b' }}>— Cash/sh ≥ 30% ממחיר המניה</span>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {valuePlays.cashPlays.map(s => (
                        <ValueCard
                          key={s.ticker} s={s} accentColor="#fbbf24"
                          badge={`cash ${(s._cash_ratio * 100).toFixed(0)}%${s._cash_ratio >= 0.5 ? ' 💥' : ''}`}
                          onClick={() => clickTicker(s)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* 📘 Deep Value */}
                {valuePlays.deepValue.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, color: '#a78bfa', fontWeight: 700, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span>📘 Deep Value</span>
                      <span style={{ fontWeight: 400, color: '#64748b' }}>— מחיר מתחת ל-Book/sh</span>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {valuePlays.deepValue.map(s => (
                        <ValueCard
                          key={s.ticker} s={s} accentColor="#a78bfa"
                          badge={`-${s._discount_pct.toFixed(0)}% book${s._discount_pct >= 40 ? ' 💎' : ''}`}
                          onClick={() => clickTicker(s)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* 🏦 EV < Market Cap */}
                {valuePlays.evUnderMc.length > 0 && (
                  <div>
                    <div style={{ fontSize: 10, color: '#34d399', fontWeight: 700, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <span>🏦 EV &lt; Market Cap</span>
                      <span style={{ fontWeight: 400, color: '#64748b' }}>— יש מזומן עודף / חוב נמוך</span>
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                      {valuePlays.evUnderMc.map(s => (
                        <ValueCard
                          key={s.ticker} s={s} accentColor="#34d399"
                          badge={`EV ${s._ev_ratio.toFixed(2)}x${s._ev_ratio < 0.7 ? ' 💥' : ''}`}
                          onClick={() => clickTicker(s)}
                        />
                      ))}
                    </div>
                  </div>
                )}

                {/* 📊 Top Sectors & Industries */}
                {sectorPerf.sectors.length > 0 && (
                  <div style={{ borderTop: '1px solid rgba(51,65,85,0.4)', paddingTop: 10, display: 'flex', flexDirection: 'column', gap: 10 }}>
                    {/* Sectors */}
                    <div>
                      <div style={{ fontSize: 10, color: '#f59e0b', fontWeight: 700, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span>📊 סקטורים מובילים</span>
                        <span style={{ fontWeight: 400, color: '#64748b' }}>— ממוצע שינוי לפי סקטור</span>
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                        {sectorPerf.sectors.slice(0, 6).map(sec => {
                          const dayColor = sec.day_avg >= 0 ? '#4ade80' : '#f87171';
                          return (
                            <div key={sec.name} style={{
                              background: 'rgba(15,23,42,0.9)', border: `1px solid ${sec.day_avg > 2 ? 'rgba(74,222,128,0.35)' : 'rgba(51,65,85,0.4)'}`,
                              borderRadius: 8, padding: '6px 10px', minWidth: 130, position: 'relative',
                            }}>
                              <div style={{ fontSize: 11, fontWeight: 700, color: '#e2e8f0', marginBottom: 3, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{sec.name}</div>
                              <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 10, fontFamily: 'monospace' }}>
                                <span style={{ color: dayColor, fontWeight: 800 }}>{sec.day_avg > 0 ? '+' : ''}{sec.day_avg}%</span>
                                <span style={{ color: '#64748b' }}>יום</span>
                                {sec.week_avg !== null && (
                                  <>
                                    <span style={{ color: sec.week_avg >= 0 ? '#86efac' : '#fca5a5', fontWeight: 600 }}>{sec.week_avg > 0 ? '+' : ''}{sec.week_avg}%</span>
                                    <span style={{ color: '#64748b' }}>שבוע</span>
                                  </>
                                )}
                                {sec.month_avg !== null && (
                                  <>
                                    <span style={{ color: sec.month_avg >= 0 ? '#86efac' : '#fca5a5', fontWeight: 600 }}>{sec.month_avg > 0 ? '+' : ''}{sec.month_avg}%</span>
                                    <span style={{ color: '#64748b' }}>חודש</span>
                                  </>
                                )}
                              </div>
                              {sec.top && (
                                <div style={{ fontSize: 9, color: '#94a3b8', marginTop: 2 }}>
                                  מוביל: <span style={{ color: '#38bdf8', fontWeight: 600 }}>{sec.top.ticker}</span> {parseFloat(sec.top.change_pct) > 0 ? '+' : ''}{parseFloat(sec.top.change_pct).toFixed(1)}%
                                </div>
                              )}
                              <div style={{ position: 'absolute', top: 4, left: 6, fontSize: 8, color: '#475569' }}>{sec.count}</div>
                            </div>
                          );
                        })}
                      </div>
                    </div>

                    {/* Industries */}
                    {sectorPerf.industries.length > 0 && (
                      <div>
                        <div style={{ fontSize: 10, color: '#818cf8', fontWeight: 700, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
                          <span>🏭 תעשיות מובילות</span>
                          <span style={{ fontWeight: 400, color: '#64748b' }}>— תת-סקטור עם הביצועים הטובים ביותר</span>
                        </div>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
                          {sectorPerf.industries.slice(0, 8).map(ind => {
                            const dayColor = ind.day_avg >= 0 ? '#4ade80' : '#f87171';
                            return (
                              <div key={ind.name} style={{
                                background: 'rgba(15,23,42,0.9)', border: `1px solid ${ind.day_avg > 3 ? 'rgba(129,140,248,0.35)' : 'rgba(51,65,85,0.4)'}`,
                                borderRadius: 8, padding: '5px 9px', minWidth: 110,
                              }}>
                                <div style={{ fontSize: 10, fontWeight: 700, color: '#e2e8f0', marginBottom: 2, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 160 }}>{ind.name}</div>
                                <div style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 9, fontFamily: 'monospace' }}>
                                  <span style={{ color: dayColor, fontWeight: 800 }}>{ind.day_avg > 0 ? '+' : ''}{ind.day_avg}%</span>
                                  {ind.week_avg !== null && (
                                    <span style={{ color: ind.week_avg >= 0 ? '#86efac' : '#fca5a5' }}>ש:{ind.week_avg > 0 ? '+' : ''}{ind.week_avg}%</span>
                                  )}
                                  {ind.month_avg !== null && (
                                    <span style={{ color: ind.month_avg >= 0 ? '#86efac' : '#fca5a5' }}>ח:{ind.month_avg > 0 ? '+' : ''}{ind.month_avg}%</span>
                                  )}
                                </div>
                                {ind.top && (
                                  <div style={{ fontSize: 8, color: '#94a3b8', marginTop: 1 }}>
                                    <span style={{ color: '#818cf8' }}>{ind.top.ticker}</span> {parseFloat(ind.top.change_pct) > 0 ? '+' : ''}{parseFloat(ind.top.change_pct).toFixed(1)}%
                                    {ind.sector && <span style={{ color: '#475569' }}> · {ind.sector}</span>}
                                  </div>
                                )}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                )}

              </div>
            )}
          </div>
        );
      })()}

      {(isLoading || isFirstScanLoading) && !stocks.length && (
        <div style={{ textAlign: 'center', padding: 60, color: '#64748b' }}>
          <div style={{
            width: 36, height: 36, border: '3px solid #1e293b', borderTopColor: '#3b82f6',
            borderRadius: '50%', animation: 'spin 0.8s linear infinite', margin: '0 auto 12px',
          }} />
          <div style={{ fontSize: 13, fontWeight: 600, color: '#94a3b8' }}>סורק מניות...</div>
          <div style={{ fontSize: 11, color: '#475569', marginTop: 4 }}>
            {isFirstScanLoading ? 'סריקה ראשונה — שולף פונדמנטלס מ-Finviz, עד כדקה...' : 'שולף נתונים מ-Finviz'}
          </div>
        </div>
      )}
      {!isLoading && !isError && stocks.length === 0 && (
        <div style={{ textAlign: 'center', padding: 60, color: '#475569' }}>
          <div style={{ fontSize: 32, marginBottom: 8 }}>📭</div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#94a3b8' }}>לא נמצאו מניות</div>
          <div style={{ fontSize: 11, marginTop: 4 }}>נסה לשנות את הפילטרים</div>
        </div>
      )}

      {sorted.length > 0 && (
        isMobile ? (
          <div style={{ padding: '8px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            {sorted.map((s) => (
              <MobileStockCard key={s.ticker} s={s} livePrices={livePrices} priceFlashes={priceFlashes} />
            ))}
          </div>
        ) : (
        <div className="finviz-scroll" style={{ overflowX: 'auto', maxHeight: 'calc(100vh - 200px)', overflowY: 'auto' }}>
          <table className="fv-table" style={{ width: '100%', minWidth: 1380, borderCollapse: 'collapse', fontSize: 11, tableLayout: 'fixed' }}>
            <thead>
              <tr>
                {/* ── RIGHT SIDE — most important ── */}
                <th style={{ ...TH_BASE, width: 28, padding: '6px 2px', background: TH_BASE.background }} />
                <SortTh label="🚀 סקוויז" col="squeeze_total_score" sort={sort} onSort={handleSort} style={{ width: 155 }}
                  title={"זיהוי Short Squeeze — לחץ שורטיסטים\n\nשלבים + מתי להיכנס:\n👀 צבירה — ⏳ המתיני לדחיסה (מוקדם מדי)\n⏳ דחיסה — 🎯 כניסה אידיאלית לפני הפיצוץ!\n🚀 יורה — ⚡ כניסה אגרסיבית עם STOP TIGHT\n⚠️ עייפות — 🚪 אל תיכנסי, שקלי יציאה\n\n🔥 NEWS + SQUEEZE = השילוב החזק ביותר\nחדשות + לחץ שורט = לולאת האצה\n\nנוסחת ניקוד (קרנות גידור):\n• Short Float — כמה אנשים בשורט\n• DTC — כמה קשה לצאת (ימים לכיסוי)\n• Rel Volume — עוצמת הקונים\n• Float Rotation — כמה פעמים הפלואט נסחר\n• Borrow Fee — לחץ כלכלי על שורטים\n• ניתוח תוך-יומי (5m/1h)"}
                  filterOpts={COL_FILTER_OPTS.squeeze_total_score}
                  filterValue={colFilter.squeeze_total_score || ''}
                  onFilter={handleColFilterToggle}
                  filterOpen={colFilterOpen === 'squeeze_total_score'}
                  onFilterOpen={setColFilterOpen} />
                <SortTh label="מניה"    col="ticker"       sort={sort} onSort={handleSort} style={{ width: 90 }}
                  title={"סמל המניה ושם החברה\nמקור: Finviz\nלחץ לפתיחת פרטים מלאים + חדשות"} />
                <SortTh label="מחיר"   col="price"        sort={sort} onSort={handleSort} style={{ width: 82 }}
                  title={"מחיר אחרון בדולרים\nשורה שנייה: מרחק מ-SMA20 (ממוצע 20 ימים)\nחיובי = מעל הממוצע | שלילי = מתחת"} />
                <SortTh label="שינוי%" col="change_pct"   sort={sort} onSort={handleSort} style={{ width: 68 }} sub={isExtended ? 'טרום' : null}
                  title={"שינוי אחוזי מסגירת אתמול\nחישוב: (מחיר עכשיו ÷ סגירה אתמול - 1) × 100\nבשעות ארכה: שינוי ממחיר הסגירה"}
                  filterOpts={COL_FILTER_OPTS.change_pct}
                  filterValue={colFilter.change_pct || ''}
                  onFilter={handleColFilterToggle}
                  filterOpen={colFilterOpen === 'change_pct'}
                  onFilterOpen={setColFilterOpen} />
                <SortTh label="פער%"   col="gap_pct"      sort={sort} onSort={handleSort} style={{ width: 52 }}
                  title={"פער פתיחה: הפרש בין מחיר הפתיחה לסגירה של אתמול\nחישוב: (פתיחה ÷ סגירה אתמול - 1) × 100\nחיובי = פתחה גבוה | שלילי = פתחה נמוך\nבשעות ארכה: מוצג שינוי ממחיר ההארכה"} />
                <SortTh label="📊 ניתוח" col="tech_score" sort={sort} onSort={handleSort} style={{ width: 114 }}
                  title={"ציון ניתוח טכני מרוכב (מינוס 100 עד פלוס 100)\nמקור: yfinance (נרות 5 דקות ושעתיים)\n• מגמה: ממוצעים נעים 50/200, חציית ממוצעים\n• מומנטום: מאקד, מדד תעלה, כוח יחסי\n• נפח: נפח מאוזן\n• תנודתיות: משטר טווח\nחיובי = סיגנלי קנייה | שלילי = סיגנלי מכירה"}
                  filterOpts={COL_FILTER_OPTS.tech_score}
                  filterValue={colFilter.tech_score || ''}
                  onFilter={handleColFilterToggle}
                  filterOpen={colFilterOpen === 'tech_score'}
                  onFilterOpen={setColFilterOpen} />
                <SortTh label="נפח יחסי" col="rel_volume" sort={sort} onSort={handleSort} style={{ width: 64 }}
                  title={"נפח יחסי: נפח היום חלקי ממוצע 10 ימים באותה שעה\nחישוב: נפח עכשיו ÷ ממוצע היסטורי\n>2.0 = נפח חריג, סיגנל חזק\n1.0 = רגיל | פחות מ-0.5 = שקט\nשורה שנייה: נפח מוחלט"}
                  filterOpts={COL_FILTER_OPTS.rel_volume}
                  filterValue={colFilter.rel_volume || ''}
                  onFilter={handleColFilterToggle}
                  filterOpen={colFilterOpen === 'rel_volume'}
                  onFilterOpen={setColFilterOpen} />
                <SortTh label="שורט%"  col="short_float"  sort={sort} onSort={handleSort} style={{ width: 52 }}
                  title={"אחוז מניות מושאלות למכירה בחסר מסך הצף\nמקור: Finviz\nמעל 20% = לחץ שורט גבוה, פוטנציאל לסחיטת שורטים\nמעל 10% = משמעותי | מתחת ל-5% = נמוך"}
                  filterOpts={COL_FILTER_OPTS.short_float}
                  filterValue={colFilter.short_float || ''}
                  onFilter={handleColFilterToggle}
                  filterOpen={colFilterOpen === 'short_float'}
                  onFilterOpen={setColFilterOpen} />
                <SortTh label="RSI"    col="rsi"          sort={sort} onSort={handleSort} style={{ width: 72 }}
                  title={"מדד כוח יחסי (14 נרות) — עוצמת מגמה\nחישוב: ממוצע עליות ÷ ממוצע ירידות\nמעל 70 = קנוי יתר, אזהרת תיקון\nמתחת ל-30 = מכור יתר, הזדמנות\nמוצג: יומי (גדול) + שעתי + 5 דקות"}
                  filterOpts={COL_FILTER_OPTS.rsi}
                  filterValue={colFilter.rsi || ''}
                  onFilter={handleColFilterToggle}
                  filterOpen={colFilterOpen === 'rsi'}
                  onFilterOpen={setColFilterOpen} />
                <th style={{ ...TH_BASE, width: 84, textAlign: 'right', background: TH_BASE.background }}>תגיות</th>
                <th style={{ ...TH_BASE, width: 3, padding: 0, background: '#1e3a5f', borderLeft: '2px solid #1e3a5f' }} />
                {/* ── LEFT SIDE — secondary ── */}
                <SortTh label="מומנטום" col="chg_30m" sort={sort} onSort={handleSort} style={{ width: 72 }}
                  title={"שינוי תוך-יומי\nשורה 1: 30 דקות אחרונות\nשורה 2: 4 שעות אחרונות"}
                  filterOpts={COL_FILTER_OPTS.chg_30m}
                  filterValue={colFilter.chg_30m || ''}
                  onFilter={handleColFilterToggle}
                  filterOpen={colFilterOpen === 'chg_30m'}
                  onFilterOpen={setColFilterOpen} />
                <SortTh label="שווי"   col="market_cap"   sort={sort} onSort={handleSort} style={{ width: 72 }}
                  title={"שווי שוק = מחיר × מספר מניות\nשורה 2 — EV/MC: פחות מ-1 = מזומנים עודפים\nשורה 3 — P/E (או Forward P/E)"}
                  filterOpts={COL_FILTER_OPTS.market_cap}
                  filterValue={colFilter.market_cap || ''}
                  onFilter={handleColFilterToggle}
                  filterOpen={colFilterOpen === 'market_cap'}
                  onFilterOpen={setColFilterOpen} />
                <SortTh label="בריאות" col="health_score" sort={sort} onSort={handleSort} style={{ width: 82 }}
                  title={"ציון בריאות פונדמנטלית (0-100)\nמקור: Finviz\n• רווחיות: רווח למניה, מכפיל רווח\n• צמיחה: רווח רבעוני, הכנסות\n• מאזן: חוב, נזילות\n• ביצועים: ביחס למדד\nמעל 70 = בריא | מעל 85 = מצוין\nשורה שנייה: EPS QoQ, או ביצוע שבועי אם אין EPS"}
                  filterOpts={COL_FILTER_OPTS.health_score}
                  filterValue={colFilter.health_score || ''}
                  onFilter={handleColFilterToggle}
                  filterOpen={colFilterOpen === 'health_score'}
                  onFilterOpen={setColFilterOpen} />
                <SortTh label="טווח"   col="atr"          sort={sort} onSort={handleSort} style={{ width: 56 }}
                  title={"טווח תנועה ממוצע יומי בדולרים (14 ימים)\nמקור: Finviz + yfinance\nמודד תנודתיות — כמה המניה זזה ביום\nגבוה = הזדמנויות גדולות, אך סיכון גדול\nשורה שנייה: טווח תוך-יומי אחוזי (נרות שעתיים)"}
                  filterOpts={COL_FILTER_OPTS.atr}
                  filterValue={colFilter.atr || ''}
                  onFilter={handleColFilterToggle}
                  filterOpen={colFilterOpen === 'atr'}
                  onFilterOpen={setColFilterOpen} />
              </tr>
            </thead>

            <tbody>
              {sorted.map((s, i) => {
                const liveChgStr = livePrices[s.ticker]?.change_pct;
                const chg = liveChgStr ? parseFloat(liveChgStr) : (isExtended && s.extended_chg_pct != null ? parseFloat(s.extended_chg_pct) : (parseFloat(s.change_pct) || 0));
                const isStar = (s.health_score >= 80) && (chg >= 8);
                const isOpen = expanded.has(s.ticker);

                const sig = (s.tech_signal || '').toLowerCase();
                const taBg = sig.includes('strong buy') ? 'rgba(74,222,128,0.07)'
                  : sig.includes('buy') ? 'rgba(74,222,128,0.035)'
                  : sig.includes('strong sell') ? 'rgba(248,113,113,0.07)'
                  : sig.includes('sell') ? 'rgba(248,113,113,0.035)'
                  : 'transparent';
                const taBorder = sig.includes('strong buy') ? '#16a34a'
                  : sig.includes('buy') ? '#22c55e'
                  : sig.includes('strong sell') ? '#dc2626'
                  : sig.includes('sell') ? '#ef4444'
                  : 'transparent';
                const baseBg = i % 2 === 0 ? '#0f172a' : 'rgba(30,41,59,0.4)';
                const isCatSqRow = s.squeeze_has_catalyst && (s.squeeze_stage === 'firing' || s.squeeze_stage === 'compression');
                const rowBg = isCatSqRow ? 'rgba(251,191,36,0.07)' : (taBg !== 'transparent' ? taBg : baseBg);
                const rowBorder = isCatSqRow ? '#fbbf24' : taBorder;

                return [
                  <tr
                    key={`row-${i}-${s.ticker}`}
                    className={isStar ? 'star-stock' : ''}
                    style={{ background: rowBg, cursor: 'pointer', borderLeft: `3px solid ${rowBorder}` }}
                    onClick={() => window.open(`https://finviz.com/quote.ashx?t=${s.ticker}`, '_blank')}
                    onMouseEnter={e => { e.currentTarget.style.background = '#1e293b'; }}
                    onMouseLeave={e => { e.currentTarget.style.background = rowBg; }}
                  >
                    {/* ── RIGHT SIDE ── */}

                    {/* Expand toggle */}
                    <td style={{ ...TD_BASE, textAlign: 'center', padding: '4px 2px' }}>
                      <button
                        onClick={e => toggleExpand(s.ticker, e)}
                        title={isOpen ? 'סגור פרטים' : 'הצג חדשות / דוחות / סיבות'}
                        style={{
                          width: 22, height: 22, borderRadius: 4, border: 'none',
                          background: isOpen ? '#1e3a5f' : '#1e293b',
                          color: isOpen ? '#60a5fa' : '#475569',
                          cursor: 'pointer', fontSize: 11, lineHeight: 1,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}
                      >
                        {isOpen ? '▲' : '▼'}
                      </button>
                    </td>

                    {/* Short Squeeze stage */}
                    <td style={{ ...TD_BASE, padding: '4px 6px', verticalAlign: 'top' }}>
                      <SqueezeCell s={s} />
                    </td>

                    {/* Ticker + Company + Sector */}
                    <td style={{ ...TD_BASE, padding: '6px 10px' }} title={s.company || s.ticker || ''}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                        <span style={{ fontWeight: 800, color: '#f1f5f9', fontSize: 13, letterSpacing: '-0.01em' }}>{s.ticker?.trim() || '—'}</span>
                        {isStar && <span style={{ fontSize: 10 }} title="Health ≥80 + עליה ≥8%">⭐</span>}
                      </div>
                      {s.company && (
                        <div style={{ fontSize: 10, color: '#94a3b8', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 105, marginTop: 1, direction: 'ltr', textAlign: 'right' }}>
                          {s.company}
                        </div>
                      )}
                      {s.sector && (
                        <div title={(SECTOR_HE[s.sector] || s.sector) + (s.industry ? ' · ' + (INDUSTRY_HE[s.industry] || s.industry) : '')}
                          style={{ fontSize: 9, color: '#475569', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 100, marginTop: 1, cursor: 'help' }}>
                          {SECTOR_HE[s.sector] || s.sector}
                        </div>
                      )}
                    </td>

                    {/* Price + SMA20 */}
                    <td style={TD_BASE}>
                      {(() => {
                        const liveP = livePrices[s.ticker]?.price;
                        const extP  = s.extended_price ? parseFloat(s.extended_price) : null;
                        const regP  = s.price ? parseFloat(s.price) : null;
                        const displayPrice = liveP ?? extP ?? regP;
                        const flash = priceFlashes[s.ticker];
                        const isLive = liveP != null;
                        const sma20v = s.sma20 != null ? parseFloat(s.sma20) : null;
                        return (
                          <>
                            <span
                              className={flash === 'up' ? 'price-flash-up' : flash === 'down' ? 'price-flash-down' : ''}
                              style={{ fontFamily: 'monospace', fontWeight: 700, color: '#e2e8f0', fontSize: 12, display: 'inline-block', padding: '1px 3px' }}
                            >
                              {displayPrice != null ? `$${displayPrice.toFixed(2)}` : '—'}
                            </span>
                            {isLive && (
                              <div className="session-badge" style={{ fontSize: 8, color: sessionMeta.color, lineHeight: 1.2, padding: '1px 4px', borderRadius: 3, background: sessionMeta.bg, border: `1px solid ${sessionMeta.border}`, marginTop: 1 }}>
                                {session === 'pre' ? '🌅 פרה' : session === 'post' ? '🌆 פוסט' : '● live'}
                              </div>
                            )}
                            {!isLive && sma20v != null && (
                              <div title={`SMA20: ${sma20v > 0 ? '+' : ''}${sma20v.toFixed(1)}% ${sma20v > 0 ? 'מעל' : 'מתחת'} לממוצע 20 ימים`}
                                style={{ fontSize: 9, color: sma20v > 5 ? '#4ade80' : sma20v < -5 ? '#f87171' : '#64748b', marginTop: 1, fontFamily: 'monospace', cursor: 'help' }}>
                                SMA {sma20v > 0 ? '+' : ''}{sma20v.toFixed(0)}%
                              </div>
                            )}
                          </>
                        );
                      })()}
                    </td>

                    {/* Chg% */}
                    <td style={TD_BASE}>
                      {(() => {
                        const liveChg = livePrices[s.ticker]?.change_pct;
                        const displayChg = liveChg || (isExtended && s.extended_chg_pct != null ? s.extended_chg_pct : s.change_pct);
                        return <PctCell val={displayChg} />;
                      })()}
                      {isExtended && (
                        <div style={{ fontSize: 8, color: sessionMeta.color, opacity: 0.7, lineHeight: 1.2 }}>
                          {session === 'pre' ? '🌅 טרום' : '🌆 פוסט'}
                        </div>
                      )}
                    </td>

                    {/* Gap% */}
                    <td style={{ ...TD_BASE, textAlign: 'center' }}>
                      {isExtended && (!s.gap_pct || parseFloat(s.gap_pct) === 0)
                        ? <GapCell val={s.extended_chg_pct} isProxy />
                        : <GapCell val={s.gap_pct} />}
                    </td>

                    {/* TA Signal */}
                    <td style={{ ...TD_BASE, padding: '3px 4px' }}>
                      <TechCell s={s} />
                    </td>

                    {/* Relative Volume + absolute volume */}
                    <td style={{ ...TD_BASE, fontFamily: 'monospace', fontSize: 11 }}>
                      <div style={{ color: parseFloat(s.rel_volume) >= 2 ? '#facc15' : parseFloat(s.rel_volume) >= 1.5 ? '#60a5fa' : '#94a3b8', fontWeight: 700 }}>
                        {s.rel_volume ? `×${parseFloat(s.rel_volume).toFixed(1)}` : '—'}
                      </div>
                      <div style={{ fontSize: 9, color: '#475569', marginTop: 1 }}>
                        {fmtVol(livePrices[s.ticker]?.volume || s.volume)}
                      </div>
                    </td>

                    {/* Short% */}
                    <td style={TD_BASE}><ShortCell val={s.short_float} /></td>

                    {/* RSI (daily + 1h + 5m) */}
                    <td style={{ ...TD_BASE, padding: '3px 4px' }}>
                      <RsiCell val={s.rsi} rsi1h={s.tech_indicators?.rsi_1h} rsi5m={s.tech_indicators?.rsi_5m} />
                    </td>

                    {/* Tags — catalyst first, then fundamental */}
                    <td style={TD_BASE}>
                      {(() => {
                        const catTags = (s.reasons || [])
                          .filter(r => TAG_META[r.type] && r.confidence !== 'low')
                          .slice(0, 2);
                        const fundTags = (s.tags || []).filter(t => TAG_META[t]);
                        const shown = [...catTags.map(r => r.type), ...fundTags].slice(0, 3);
                        const extra = (catTags.length + fundTags.length) - shown.length;
                        return (
                          <div style={{ display: 'flex', gap: 3, flexWrap: 'wrap', justifyContent: 'flex-end', alignItems: 'center' }}>
                            {shown.map((tag, i) => <TagBadge key={`${tag}-${i}`} tag={tag} />)}
                            {extra > 0 && <span style={{ fontSize: 10, color: '#94a3b8', fontWeight: 600 }}>+{extra}</span>}
                          </div>
                        );
                      })()}
                    </td>
                    <td style={{ ...TD_BASE, width: 3, padding: 0, background: 'rgba(30,58,95,0.3)', borderLeft: '2px solid #1e3a5f' }} />

                    {/* ── LEFT SIDE — secondary ── */}

                    {/* Momentum: 30m + 4h */}
                    <td style={{ ...TD_BASE, padding: '6px 10px' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <span style={{ fontSize: 9, color: '#334155', fontWeight: 600, minWidth: 20 }}>30m</span>
                          {s.chg_30m != null ? <PctCell val={s.chg_30m} /> : <span style={{ color: '#334155', fontSize: 11 }}>—</span>}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                          <span style={{ fontSize: 9, color: '#334155', fontWeight: 600, minWidth: 20 }}>4h</span>
                          {s.chg_4h != null ? <PctCell val={s.chg_4h} /> : <span style={{ color: '#334155', fontSize: 11 }}>—</span>}
                        </div>
                      </div>
                    </td>

                    {/* Market Cap + EV/MC + P/E */}
                    <td style={{ ...TD_BASE, padding: '3px 4px' }}>
                      <MoneyCell val={s.market_cap} str={livePrices[s.ticker]?.market_cap_str || s.market_cap_str} />
                      {s.ev_mc_ratio != null && (
                        <div style={{ marginTop: 1 }}><EvMcCell ratio={s.ev_mc_ratio} /></div>
                      )}
                      {(() => {
                        const pe = parseFloat(s.pe);
                        const fpe = parseFloat(s.forward_pe);
                        const val = !isNaN(pe) && pe > 0 ? pe : !isNaN(fpe) && fpe > 0 ? fpe : null;
                        const isFwd = isNaN(pe) || pe <= 0;
                        if (!val) return null;
                        const c = val < 15 ? '#4ade80' : val < 25 ? '#fde047' : val > 50 ? '#f87171' : '#94a3b8';
                        return (
                          <div style={{ marginTop: 1, fontSize: 9, color: '#475569', fontFamily: 'monospace' }}>
                            {isFwd ? 'fwd ' : ''}<span style={{ color: c, fontWeight: 700 }}>P/E {val.toFixed(0)}</span>
                          </div>
                        );
                      })()}
                    </td>

                    {/* Health + EPS QoQ / Perf Week */}
                    <td style={{ ...TD_BASE, padding: '4px 6px' }}>
                      <HealthBadge score={s.health_score} detail={s.health_detail} />
                      {s.eps_qq != null ? (
                        <div style={{ marginTop: 2 }}><EpsQqCell val={s.eps_qq} /></div>
                      ) : s.perf_week ? (() => {
                        const v = parseFloat(s.perf_week);
                        return (
                          <div style={{ marginTop: 2, fontSize: 9, color: '#475569' }}>
                            7י׳ <span style={{ color: v > 0 ? '#4ade80' : '#f87171', fontFamily: 'monospace', fontWeight: 700 }}>{v > 0 ? '+' : ''}{v.toFixed(1)}%</span>
                          </div>
                        );
                      })() : null}
                    </td>

                    {/* ATR */}
                    <td style={{ ...TD_BASE, padding: '3px 4px' }}>
                      <AtrCell atr={s.atr} price={s.price} atrPct1h={s.tech_indicators?.atr_pct_1h} />
                    </td>

                  </tr>,

                  /* ── Rich expand row ── */
                  isOpen && (
                    <ExpandRow key={`expand-${i}-${s.ticker}`} s={s} colSpan={COL_COUNT} />
                  ),
                ];
              })}
            </tbody>
          </table>
        </div>
        )
      )}

      {sorted.length > 0 && (
        <div style={{
          padding: '8px 20px', fontSize: 10, color: '#475569', borderTop: '1px solid #1e293b',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          background: 'rgba(15,23,42,0.5)',
        }}>
          <span>TA: 🟢 Strong Buy / Buy · 🟡 Neutral · 🔴 Sell / Strong Sell &nbsp;|&nbsp; Health: 🟢 80+ · 🟡 60+ · 🟠 40+ · 🔴 0-39</span>
          <span style={{ color: '#334155' }}>Powered by Finviz</span>
        </div>
      )}
    </div>
  );
}

export { SmartPortfolioDashboard };
