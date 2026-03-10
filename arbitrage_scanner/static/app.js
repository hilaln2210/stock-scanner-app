(function () {
  'use strict';

  const API = '/api';

  let opportunities = [];
  let markets = [];
  let simulator = null;
  function getDataSource() {
    const el = $('data-source');
    return (el && el.value) ? el.value : 'all';
  }
  const POLL_INTERVAL_MS = 12 * 1000; // רענון נתונים מהשרת כל 12 שניות (כניסות/יציאות מהסריקה ברקע)

  const $ = (id) => document.getElementById(id);
  const showToast = (msg) => {
    const el = $('toast');
    el.textContent = msg;
    el.classList.add('show');
    setTimeout(() => el.classList.remove('show'), 2500);
  };

  function formatNum(n, decimals = 2) {
    if (n == null || n === '') return '–';
    return Number(n).toLocaleString('he-IL', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  function formatPct(n) {
    if (n == null || n === '') return '–';
    const x = Number(n);
    const s = formatNum(x, 2) + '%';
    return x >= 0 ? s : s;
  }

  async function fetchMarkets(source) {
    const s = source !== undefined ? source : getDataSource();
    const res = await fetch(API + '/markets?source=' + encodeURIComponent(s));
    if (!res.ok) {
      let msg = 'טעינת שווקים נכשלה';
      try {
        const body = await res.json();
        if (body.detail) {
          if (typeof body.detail === 'object' && body.detail.message) msg = body.detail.message;
          else if (typeof body.detail === 'string') msg = body.detail;
        }
      } catch (_) { /* ignore */ }
      throw new Error(msg + ' (' + res.status + ')');
    }
    return res.json();
  }

  async function fetchScan() {
    const res = await fetch(API + '/scan?source=' + encodeURIComponent(getDataSource()));
    if (!res.ok) {
      let msg = 'סריקה נכשלה';
      try {
        const body = await res.json();
        if (body.detail && body.detail.message) msg = body.detail.message;
      } catch (_) { /* ignore */ }
      throw new Error(msg + ' (' + res.status + ')');
    }
    return res.json();
  }

  /** הזדמנויות מהסריקה האחרונה (אוטומטית או ידנית) – מתעדכן בזמן אמת */
  async function fetchLastOpportunities() {
    const res = await fetch(API + '/last-opportunities');
    if (!res.ok) return [];
    return res.json();
  }

  async function fetchSimulator() {
    const res = await fetch(API + '/simulator');
    if (!res.ok) throw new Error('Simulator failed');
    return res.json();
  }

  async function postSimulate(maxEntries = 3) {
    const res = await fetch(API + '/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_entries: maxEntries }),
    });
    if (!res.ok) throw new Error('Simulate failed');
    return res.json();
  }

  async function postReset() {
    const res = await fetch(API + '/simulator/reset', { method: 'POST' });
    if (!res.ok) throw new Error('Reset failed');
    return res.json();
  }

  async function fetchStatus() {
    const res = await fetch(API + '/status');
    if (!res.ok) return null;
    return res.json();
  }

  function renderKpis() {
    const oppCount = opportunities.length;
    $('kpi-opportunities').textContent = oppCount;
    $('kpi-opportunities').className = 'kpi-value';

    if (simulator) {
      $('kpi-balance').textContent = formatNum(simulator.balance);
      $('kpi-balance').className = 'kpi-value';

      const pnl = simulator.total_pnl;
      const pnlEl = $('kpi-pnl');
      pnlEl.textContent = formatNum(pnl) + ' (' + formatPct(simulator.total_pnl_pct) + ')';
      pnlEl.className = 'kpi-value' + (pnl >= 0 ? ' positive' : ' negative');

      const real = simulator.total_realized_pnl;
      const realEl = $('kpi-realized');
      realEl.textContent = formatNum(real);
      realEl.className = 'kpi-value' + (real >= 0 ? ' positive' : ' negative');
    } else {
      $('kpi-balance').textContent = '–';
      $('kpi-realized').textContent = '–';
      $('kpi-pnl').textContent = '–';
    }
  }

  function renderLastScan(status) {
    const el = $('last-scan');
    if (!el) return;
    if (!status || !status.last_scan_iso) {
      el.textContent = 'מחכה לסריקה ראשונה';
      return;
    }
    const t = new Date(status.last_scan_iso);
    const sec = Math.round((Date.now() - t.getTime()) / 1000);
    if (sec < 60) el.textContent = 'לפני ' + sec + ' שניות';
    else if (sec < 3600) el.textContent = 'לפני ' + Math.floor(sec / 60) + ' דקות';
    else el.textContent = 'לפני ' + Math.floor(sec / 3600) + ' שעות';
    if (status.last_opportunities_count !== undefined) el.textContent += ' (' + status.last_opportunities_count + ' הזדמנויות)';
  }

  function renderMarkets() {
    const tbody = document.querySelector('#table-markets tbody');
    const empty = $('empty-markets');
    const countEl = $('markets-count');
    const summaryEl = $('markets-filter-summary');
    const filterArb = ($('filter-arb') && $('filter-arb').value) || 'all';
    const filtered = markets.filter((m) => {
      if (filterArb === 'yes') return m.is_arbitrage === true;
      if (filterArb === 'no') return m.is_arbitrage !== true;
      return true;
    });
    tbody.innerHTML = '';
    countEl.textContent = markets.length;
    if (summaryEl) {
      if (filterArb === 'all') summaryEl.textContent = '';
      else summaryEl.textContent = 'מציג ' + filtered.length + ' מתוך ' + markets.length;
    }
    if (markets.length === 0) {
      empty.classList.remove('hidden');
      empty.textContent = 'אין שווקים. ייתכן שהשרת לא זמין או שטעינת הנתונים נכשלה – נסה לרענן.';
      const demoEl = $('demo-notice');
      if (demoEl) demoEl.classList.add('hidden');
      return;
    }
    empty.classList.add('hidden');
    const demoEl = $('demo-notice');
    const allMock = markets.every((m) => (m.source || '').toLowerCase() === 'mock');
    if (demoEl) demoEl.classList.toggle('hidden', !allMock);
    filtered.forEach((m) => {
      const tr = document.createElement('tr');
      const arbClass = m.is_arbitrage ? 'positive' : '';
      const src = m.source || 'polymarket';
      tr.innerHTML =
        '<td>' + escapeHtml(src) + '</td>' +
        '<td class="num">' + escapeHtml(m.market_id) + '</td>' +
        '<td>' + escapeHtml(m.question) + '</td>' +
        '<td class="num">' + formatNum(m.yes_price, 4) + '</td>' +
        '<td class="num">' + formatNum(m.no_price, 4) + '</td>' +
        '<td class="num">' + formatNum(m.total_price, 4) + '</td>' +
        '<td class="num">' + formatNum(m.liquidity) + '</td>' +
        '<td class="num ' + arbClass + '">' + (m.is_arbitrage ? 'כן' : 'לא') + '</td>' +
        '<td class="num ' + arbClass + '">' + formatPct(m.expected_profit_pct) + '</td>';
      tbody.appendChild(tr);
    });
  }

  function renderOpportunities() {
    const tbody = document.querySelector('#table-opportunities tbody');
    const empty = $('empty-opportunities');
    const summaryEl = $('opp-filter-summary');
    const filterType = ($('filter-opp-type') && $('filter-opp-type').value) || 'all';
    const filtered = opportunities.filter((o) => {
      const t = (o.market_type || '').toLowerCase();
      if (filterType === 'binary') return t === 'binary';
      if (filterType === 'multi_outcome') return t === 'multi_outcome';
      return true;
    });
    tbody.innerHTML = '';
    if (summaryEl) {
      if (filterType === 'all') summaryEl.textContent = '';
      else summaryEl.textContent = 'מציג ' + filtered.length + ' מתוך ' + opportunities.length;
    }
    if (opportunities.length === 0) {
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    filtered.forEach((o) => {
      const tr = document.createElement('tr');
      const src = o.source || 'polymarket';
      tr.innerHTML =
        '<td>' + escapeHtml(src) + '</td>' +
        '<td class="num">' + escapeHtml(o.market_id) + '</td>' +
        '<td>' + escapeHtml(o.market_type) + '</td>' +
        '<td>' + escapeHtml(o.question) + '</td>' +
        '<td class="num positive">' + formatPct(o.expected_profit_pct) + '</td>' +
        '<td class="num">' + formatNum(o.total_cost, 4) + '</td>' +
        '<td class="num">' + formatNum(o.liquidity) + '</td>';
      tbody.appendChild(tr);
    });
  }

  /** היסטוריית עסקאות מאוחדת: כניסות + יציאות לפי תאריך (חדש ביותר קודם) */
  function renderHistory() {
    const tbody = document.querySelector('#table-history tbody');
    const empty = $('empty-history');
    if (!tbody) return;
    tbody.innerHTML = '';
    const entries = simulator ? simulator.entries : [];
    const exits = simulator ? simulator.exits : [];
    const rows = [];
    entries.forEach((e) => {
      rows.push({ date: e.entry_date, type: 'entry', entry: e, exit: null });
    });
    exits.forEach((x) => {
      rows.push({ date: x.exit_date, type: 'exit', entry: null, exit: x });
    });
    rows.sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : (a.type === 'exit' ? -1 : 1)));
    if (rows.length === 0) {
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    rows.forEach((r) => {
      const tr = document.createElement('tr');
      if (r.type === 'entry') {
        const e = r.entry;
        tr.innerHTML =
          '<td>' + escapeHtml(e.entry_date) + '</td>' +
          '<td>כניסה</td>' +
          '<td class="num">' + escapeHtml(e.market_id) + '</td>' +
          '<td class="num">' + formatNum(e.capital_used) + '</td>' +
          '<td class="num positive">צפוי</td>' +
          '<td class="num positive">' + formatPct(e.expected_profit_pct) + '</td>' +
          '<td class="num">–</td>';
      } else {
        const x = r.exit;
        const pnlClass = x.realized_pnl >= 0 ? 'positive' : 'negative';
        const fee = x.fee_estimate != null && x.fee_estimate !== 0 ? formatNum(x.fee_estimate) : '–';
        tr.innerHTML =
          '<td>' + escapeHtml(x.exit_date) + '</td>' +
          '<td>יציאה</td>' +
          '<td class="num">' + escapeHtml(x.market_id) + '</td>' +
          '<td class="num">' + formatNum(x.capital_used) + '</td>' +
          '<td class="num ' + pnlClass + '">' + formatNum(x.realized_pnl) + '</td>' +
          '<td class="num ' + pnlClass + '">' + formatPct(x.realized_pnl_pct) + '</td>' +
          '<td class="num">' + fee + '</td>';
      }
      tbody.appendChild(tr);
    });
  }

  function renderPositions() {
    const tbody = document.querySelector('#table-positions tbody');
    const empty = $('empty-positions');
    tbody.innerHTML = '';
    const list = simulator ? simulator.open_positions : [];
    if (list.length === 0) {
      empty.classList.remove('hidden');
      return;
    }
    empty.classList.add('hidden');
    list.forEach((p) => {
      const tr = document.createElement('tr');
      tr.innerHTML =
        '<td class="num">' + escapeHtml(p.market_id) + '</td>' +
        '<td class="num">' + formatNum(p.capital_used) + '</td>' +
        '<td>' + escapeHtml(p.entry_date) + '</td>' +
        '<td class="num positive">' + formatPct(p.expected_profit_pct) + '</td>';
      tbody.appendChild(tr);
    });
  }

  function escapeHtml(s) {
    if (s == null) return '';
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  let lastStatus = null;

  function render(status) {
    if (status) lastStatus = status;
    renderKpis();
    renderMarkets();
    renderOpportunities();
    renderHistory();
    renderPositions();
    renderLastScan(lastStatus);
  }

  async function loadScan(silent) {
    const main = document.querySelector('main');
    if (!silent) main.classList.add('loading');
    try {
      try {
        markets = await fetchMarkets(getDataSource());
      } catch (e) {
        if (getDataSource() === 'polymarket') {
          try {
            markets = await fetchMarkets('mock');
            if (!silent) showToast('Polymarket לא זמין – מוצגים נתוני הדגמה (' + markets.length + ' שווקים)');
          } catch (_) {
            throw e;
          }
        } else {
          throw e;
        }
      }
      opportunities = await fetchScan();
      if (!simulator) simulator = await fetchSimulator();
      render();
      if (!silent) showToast('סריקה הושלמה · ' + markets.length + ' שווקים');
    } catch (e) {
      if (!silent) showToast('שגיאה: ' + (e.message || 'לא ניתן לטעון'));
    } finally {
      if (!silent) main.classList.remove('loading');
    }
  }

  async function resetSimulator() {
    const main = document.querySelector('main');
    main.classList.add('loading');
    try {
      simulator = await postReset();
      render();
      showToast('הסימולטור אופס');
    } catch (e) {
      showToast('שגיאה: ' + (e.message || 'איפוס נכשל'));
    } finally {
      main.classList.remove('loading');
    }
  }

  $('btn-scan').addEventListener('click', () => loadScan(false));
  $('btn-reset').addEventListener('click', resetSimulator);
  const dataSourceEl = $('data-source');
  if (dataSourceEl) dataSourceEl.addEventListener('change', () => loadScan(false));
  function applyFilters() {
    renderMarkets();
    renderOpportunities();
  }
  const filterArbEl = $('filter-arb');
  const filterOppEl = $('filter-opp-type');
  if (filterArbEl) {
    filterArbEl.addEventListener('change', applyFilters);
    filterArbEl.addEventListener('input', applyFilters);
    let lastArb = filterArbEl.value;
    setInterval(() => {
      if (filterArbEl.value !== lastArb) {
        lastArb = filterArbEl.value;
        applyFilters();
      }
    }, 400);
  }
  if (filterOppEl) {
    filterOppEl.addEventListener('change', applyFilters);
    filterOppEl.addEventListener('input', applyFilters);
    let lastOpp = filterOppEl.value;
    setInterval(() => {
      if (filterOppEl.value !== lastOpp) {
        lastOpp = filterOppEl.value;
        applyFilters();
      }
    }, 400);
  }

  // רענון מהשרת כל 12 שניות – הזדמנויות מהסריקה האוטומטית + כניסות/יציאות
  async function pollUpdates() {
    try {
      const [sim, opps, status] = await Promise.all([
        fetchSimulator(),
        fetchLastOpportunities(),
        fetchStatus(),
      ]);
      simulator = sim;
      opportunities = opps;
      render(status);
    } catch (_) { /* ignore */ }
  }

  setInterval(pollUpdates, POLL_INTERVAL_MS);

  // טעינה ראשונית
  (async function init() {
    await loadScan(false);
    const status = await fetchStatus();
    render(status);
    showToast('הבוט פעיל – סורק ארביטראז\', נכנס ויוצא אוטומטית');
  })();
})();
