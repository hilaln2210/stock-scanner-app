import { useState, useMemo, useRef, useEffect, useCallback } from 'react';
import { Calendar, Table2, ChevronLeft, ChevronRight, ChevronDown, ChevronUp, Activity, BarChart3, ExternalLink, Newspaper, Clock, Target, AlertTriangle, TrendingUp, TrendingDown, Zap, FileText, Filter, Search, Star, Copy, Check, X, Layers, ArrowRight, Flame, Eye } from 'lucide-react';

// ─── Helpers ─────────────────────────────────────────────

const fmtMcap = (v) => {
  if (!v || v === '-') return typeof v === 'string' ? v : '-';
  if (typeof v === 'string') return v;
  if (v >= 1e12) return `$${(v / 1e12).toFixed(1)}T`;
  if (v >= 1e9) return `$${(v / 1e9).toFixed(1)}B`;
  if (v >= 1e6) return `$${(v / 1e6).toFixed(0)}M`;
  return `$${v}`;
};

const changeColor = (v) => {
  const num = parseFloat(v);
  return num > 0 ? 'text-green-400' : num < 0 ? 'text-red-400' : 'text-slate-400';
};

const catalystColors = {
  PDUFA: { bg: 'bg-red-600', dot: 'bg-red-500', text: 'text-red-400', border: 'border-red-500/40', ring: 'ring-red-500/30' },
  AdCom: { bg: 'bg-orange-600', dot: 'bg-orange-500', text: 'text-orange-400', border: 'border-orange-500/40', ring: 'ring-orange-500/30' },
  Phase3: { bg: 'bg-blue-600', dot: 'bg-blue-500', text: 'text-blue-400', border: 'border-blue-500/40', ring: 'ring-blue-500/30' },
  Phase2: { bg: 'bg-cyan-600', dot: 'bg-cyan-500', text: 'text-cyan-400', border: 'border-cyan-500/40', ring: 'ring-cyan-500/30' },
  Phase1: { bg: 'bg-teal-600', dot: 'bg-teal-500', text: 'text-teal-400', border: 'border-teal-500/40', ring: 'ring-teal-500/30' },
  NDA: { bg: 'bg-green-600', dot: 'bg-green-500', text: 'text-green-400', border: 'border-green-500/40', ring: 'ring-green-500/30' },
  BLA: { bg: 'bg-green-600', dot: 'bg-green-500', text: 'text-green-400', border: 'border-green-500/40', ring: 'ring-green-500/30' },
  CRL: { bg: 'bg-yellow-600', dot: 'bg-yellow-500', text: 'text-yellow-400', border: 'border-yellow-500/40', ring: 'ring-yellow-500/30' },
  Approval: { bg: 'bg-emerald-600', dot: 'bg-emerald-500', text: 'text-emerald-400', border: 'border-emerald-500/40', ring: 'ring-emerald-500/30' },
  Rejection: { bg: 'bg-red-700', dot: 'bg-red-600', text: 'text-red-500', border: 'border-red-600/40', ring: 'ring-red-600/30' },
  Earnings: { bg: 'bg-violet-600', dot: 'bg-violet-500', text: 'text-violet-400', border: 'border-violet-500/40', ring: 'ring-violet-500/30' },
  Dividend: { bg: 'bg-lime-600', dot: 'bg-lime-500', text: 'text-lime-400', border: 'border-lime-500/40', ring: 'ring-lime-500/30' },
  Other: { bg: 'bg-slate-600', dot: 'bg-slate-500', text: 'text-slate-400', border: 'border-slate-500/40', ring: 'ring-slate-500/30' },
};

// Hebrew explanations for each catalyst type
const catalystTypeHebrew = {
  PDUFA: 'תאריך יעד להחלטת FDA',
  AdCom: 'ועדה מייעצת של FDA',
  Phase3: 'ניסוי קליני שלב 3 (אחרון לפני הגשה)',
  Phase2: 'ניסוי קליני שלב 2 (בדיקת יעילות)',
  Phase1: 'ניסוי קליני שלב 1 (בטיחות)',
  NDA: 'בקשת אישור תרופה חדשה',
  BLA: 'בקשת רישיון תרופה ביולוגית',
  CRL: 'מכתב תגובה - FDA דחה את הבקשה',
  Approval: 'אושר ע"י FDA',
  Rejection: 'נדחה ע"י FDA',
  Earnings: 'דוח רווחים',
  Dividend: 'דיבידנד',
  Other: 'אירוע אחר',
};

// Hebrew stage descriptions
const stageHebrew = {
  'Phase 1': 'שלב 1 - בדיקת בטיחות',
  'Phase 2': 'שלב 2 - בדיקת יעילות',
  'Phase 3': 'שלב 3 - ניסוי מתקדם',
  'NDA/BLA': 'הוגש לאישור FDA',
  'Approved': 'מאושר',
};

// Map common indications/diseases to Hebrew
const indicationHebrew = {
  'cancer': 'סרטן', 'oncology': 'אונקולוגיה', 'tumor': 'גידול',
  'leukemia': 'לוקמיה', 'lymphoma': 'לימפומה', 'myeloma': 'מיאלומה',
  'melanoma': 'מלנומה', 'carcinoma': 'קרצינומה',
  'ovarian': 'שחלות', 'breast': 'שד', 'lung': 'ריאות', 'liver': 'כבד',
  'prostate': 'ערמונית', 'colon': 'מעי גס', 'pancreatic': 'לבלב',
  'kidney': 'כליות', 'bladder': 'שלפוחית', 'gastric': 'קיבה',
  'brain': 'מוח', 'glioblastoma': 'גליובלסטומה', 'glioma': 'גליומה',
  'sarcoma': 'סרקומה', 'mesothelioma': 'מזותליומה',
  'diabetes': 'סוכרת', 'obesity': 'השמנה', 'weight': 'משקל',
  'heart failure': 'אי-ספיקת לב', 'cardiovascular': 'לב וכלי דם',
  'hypertension': 'יתר לחץ דם', 'atrial fibrillation': 'פרפור פרוזדורים',
  'coronary': 'כלילי', 'thrombosis': 'פקקת',
  'alzheimer': 'אלצהיימר', 'parkinson': 'פרקינסון', 'dementia': 'דמנציה',
  'schizophrenia': 'סכיזופרניה', 'bipolar': 'דו-קוטבי',
  'depression': 'דיכאון', 'anxiety': 'חרדה', 'epilepsy': 'אפילפסיה',
  'migraine': 'מיגרנה', 'neuropathy': 'נוירופתיה', 'pain': 'כאב',
  'multiple sclerosis': 'טרשת נפוצה', 'ms': 'טרשת נפוצה',
  'als': 'ALS - טרשת צדית', 'amyotrophic': 'ALS - טרשת צדית',
  'huntington': 'הנטינגטון', 'dystrophy': 'דיסטרופיה',
  'arthritis': 'דלקת מפרקים', 'psoriasis': 'פסוריאזיס',
  'psoriatic': 'פסוריאטי', 'lupus': 'זאבת',
  'asthma': 'אסטמה', 'copd': 'מחלת ריאות חסימתית',
  'rhinosinusitis': 'דלקת אף וסינוסים', 'dermatitis': 'דרמטיטיס',
  'eczema': 'אקזמה', 'urticaria': 'אורטיקריה (חרלת)',
  'alopecia': 'התקרחות', 'vitiligo': 'ויטיליגו',
  'crohn': 'קרוהן', 'colitis': 'קוליטיס', 'ibd': 'מחלת מעי דלקתית',
  'hepatitis': 'דלקת כבד', 'cirrhosis': 'שחמת כבד',
  'cholangitis': 'דלקת דרכי מרה', 'nash': 'כבד שומני',
  'anemia': 'אנמיה', 'hemophilia': 'המופיליה',
  'thrombocytopenia': 'טרומבוציטופניה', 'sickle cell': 'חרמשית',
  'thalassemia': 'תלסמיה',
  'immunodeficiency': 'כשל חיסוני', 'hiv': 'HIV',
  'infection': 'זיהום', 'sepsis': 'אלח דם', 'pneumonia': 'דלקת ריאות',
  'rsv': 'RSV - וירוס נשימתי', 'influenza': 'שפעת',
  'rare disease': 'מחלה נדירה', 'orphan': 'מחלה נדירה',
  'mucopolysaccharidosis': 'מוקופוליסכרידוזיס (מחלה מטבולית נדירה)',
  'phenylketonuria': 'פנילקטונוריה (PKU)',
  'achondroplasia': 'אכונדרופלזיה (גמדות)',
  'acromegaly': 'אקרומגליה',
  'gaucher': 'מחלת גושה',
  'fabry': 'מחלת פברי',
  'pompe': 'מחלת פומפה',
  'hunter syndrome': 'תסמונת האנטר',
  'hodgkin': 'הודג\'קין',
  'myeloid': 'מיאלואידי',
  'myelofibrosis': 'מיאלופיברוזיס',
  'polycythemia': 'פוליציתמיה',
  'nephropathy': 'נפרופתיה (מחלת כליות)',
  'glomerulosclerosis': 'גלומרולוסקלרוזיס (מחלת כליות)',
  'thyroid eye': 'מחלת עיניים של בלוטת התריס',
  'neuroendocrine': 'נוירואנדוקריני',
  'retinal': 'רשתית', 'macular': 'ניוון מקולרי', 'glaucoma': 'גלאוקומה',
  'hearing': 'שמיעה', 'otitis': 'דלקת אוזניים',
  'fibrosis': 'פיברוזיס', 'cystic fibrosis': 'סיסטיק פיברוזיס',
  'endometriosis': 'אנדומטריוזיס', 'fertility': 'פוריות',
  'osteoporosis': 'אוסטאופורוזיס', 'bone': 'עצם',
  'transplant': 'השתלה', 'graft': 'השתלה',
  'gene therapy': 'טיפול גנטי',
  'cell therapy': 'טיפול תאי',
  'immunotherapy': 'אימונותרפיה',
  'antibody': 'נוגדן',
  'checkpoint': 'אימונותרפיה',
  'car-t': 'טיפול CAR-T',
  'bispecific': 'נוגדן דו-ספציפי',
  'adc': 'ADC - נוגדן-תרופה מצומד',
  'sirna': 'טיפול siRNA',
  'mrna': 'טיפול mRNA',
  'crispr': 'עריכת גנים CRISPR',
};

// Get Hebrew description for a company/drug based on indication
const getHebrewDescription = (event) => {
  if (!event) return '';
  const indication = (event.indication || '').toLowerCase();
  const drugName = (event.drug_name || '').toLowerCase();
  const company = (event.company || '').toLowerCase();
  const fullText = `${indication} ${drugName} ${company}`;

  // Find matching Hebrew indications (collect multiple)
  const matches = [];
  for (const [eng, heb] of Object.entries(indicationHebrew)) {
    if (fullText.includes(eng) && !matches.includes(heb)) {
      matches.push(heb);
      if (matches.length >= 2) break;
    }
  }

  // Get Hebrew stage
  const phase = event.phase || '';
  const hebrewStage = stageHebrew[phase] || '';

  // Build description
  const parts = [];
  if (matches.length > 0) parts.push(matches.join(', '));
  if (hebrewStage) parts.push(hebrewStage);
  return parts.join(' | ');
};

const getCatalystStyle = (type) => catalystColors[type] || catalystColors.Other;

const getDaysUntilBadge = (days) => {
  if (days === null || days === undefined) return { color: 'bg-slate-600 text-slate-300', label: 'TBD', urgency: 0 };
  if (days < 0) return { color: 'bg-slate-700 text-slate-400', label: `${Math.abs(days)}d ago`, urgency: 0 };
  if (days === 0) return { color: 'bg-red-600 text-white animate-pulse', label: 'TODAY', urgency: 5 };
  if (days <= 3) return { color: 'bg-red-600 text-white', label: `${days}d`, urgency: 4 };
  if (days <= 7) return { color: 'bg-red-500 text-white', label: `${days}d`, urgency: 3 };
  if (days <= 14) return { color: 'bg-orange-500 text-white', label: `${days}d`, urgency: 2 };
  if (days <= 30) return { color: 'bg-orange-600 text-white', label: `${days}d`, urgency: 1 };
  if (days <= 60) return { color: 'bg-yellow-600 text-black', label: `${days}d`, urgency: 0 };
  return { color: 'bg-green-700 text-white', label: `${days}d`, urgency: 0 };
};

const formatDate = (dateStr) => {
  if (!dateStr) return 'TBD';
  try {
    const d = new Date(dateStr + 'T00:00:00');
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
  } catch { return dateStr; }
};

const formatNewsDate = (dateStr) => {
  if (!dateStr) return '';
  try {
    const d = new Date(dateStr);
    if (isNaN(d.getTime())) return '';
    const now = new Date();
    const diffMs = now - d;
    const diffHours = diffMs / (1000 * 60 * 60);
    if (diffHours < 1) return `${Math.floor(diffMs / 60000)}m ago`;
    if (diffHours < 24) return `${Math.floor(diffHours)}h ago`;
    if (diffHours < 48) return 'Yesterday';
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
  } catch { return ''; }
};

// ─── Watchlist (localStorage) ─────────────────────────────
const WATCHLIST_KEY = 'fda_catalyst_watchlist';

const getWatchlist = () => {
  try {
    return JSON.parse(localStorage.getItem(WATCHLIST_KEY) || '[]');
  } catch { return []; }
};

const toggleWatchlist = (ticker) => {
  const list = getWatchlist();
  const idx = list.indexOf(ticker);
  if (idx >= 0) {
    list.splice(idx, 1);
  } else {
    list.push(ticker);
  }
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(list));
  return list;
};


// ─── TradingView Chart (lazy-loaded) ─────────────────────

function CandleChart({ ticker }) {
  const containerRef = useRef(null);
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setIsVisible(true); observer.disconnect(); } },
      { threshold: 0.1 }
    );
    if (containerRef.current) observer.observe(containerRef.current);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (!isVisible || !containerRef.current) return;
    containerRef.current.innerHTML = '';

    const widgetDiv = document.createElement('div');
    widgetDiv.className = 'tradingview-widget-container__widget';
    widgetDiv.style.height = '100%';
    widgetDiv.style.width = '100%';
    containerRef.current.appendChild(widgetDiv);

    const script = document.createElement('script');
    script.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    script.async = true;
    script.type = 'text/javascript';
    script.textContent = JSON.stringify({
      autosize: false,
      symbol: ticker,
      width: '100%',
      height: 300,
      interval: 'D',
      timezone: 'America/New_York',
      theme: 'dark',
      style: '1',
      locale: 'he_IL',
      allow_symbol_change: false,
      hide_top_toolbar: true,
      hide_side_toolbar: true,
      save_image: false,
      calendar: false,
      studies: ['Volume@tv-basicstudies'],
      support_host: 'https://www.tradingview.com',
    });

    containerRef.current.appendChild(script);
  }, [isVisible, ticker]);

  return (
    <div className="tradingview-widget-container rounded-lg overflow-hidden border border-slate-700"
      ref={containerRef} style={{ height: 300, minHeight: 300 }}>
      {!isVisible && (
        <div className="flex items-center justify-center h-full bg-slate-900/50 text-slate-500 text-sm">
          Loading chart...
        </div>
      )}
    </div>
  );
}


// ─── Summary Stats Header ─────────────────────────────────

function StatsHeader({ events, viewMode }) {
  const stats = useMemo(() => {
    if (!events || events.length === 0) return null;

    const now = new Date();
    const thisWeek = events.filter(e => e.days_until !== null && e.days_until >= 0 && e.days_until <= 7);
    const thisMonth = events.filter(e => e.days_until !== null && e.days_until >= 0 && e.days_until <= 30);
    const pdufa = events.filter(e => e.catalyst_type === 'PDUFA');
    const highProb = events.filter(e => e.approval_probability?.probability >= 80);
    const avgProb = events.reduce((sum, e) => sum + (e.approval_probability?.probability || 0), 0) / events.length;

    // Next upcoming event
    const nextEvent = events.find(e => e.days_until !== null && e.days_until >= 0);

    return { thisWeek, thisMonth, pdufa, highProb, avgProb: Math.round(avgProb), nextEvent, total: events.length };
  }, [events]);

  if (!stats) return null;

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 mb-4">
      <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-3 text-center">
        <div className="text-2xl font-bold text-white">{stats.total}</div>
        <div className="text-[10px] text-slate-500 mt-0.5" dir="rtl">סה"כ אירועים</div>
      </div>
      <div className={`bg-slate-800/60 border rounded-lg p-3 text-center ${stats.thisWeek.length > 0 ? 'border-red-500/50' : 'border-slate-700'}`}>
        <div className={`text-2xl font-bold ${stats.thisWeek.length > 0 ? 'text-red-400' : 'text-slate-400'}`}>
          {stats.thisWeek.length}
        </div>
        <div className="text-[10px] text-slate-500 mt-0.5" dir="rtl">השבוע</div>
      </div>
      <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-3 text-center">
        <div className="text-2xl font-bold text-orange-400">{stats.thisMonth.length}</div>
        <div className="text-[10px] text-slate-500 mt-0.5" dir="rtl">החודש</div>
      </div>
      {viewMode === 'fda' && (
        <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-3 text-center">
          <div className="text-2xl font-bold text-red-400">{stats.pdufa.length}</div>
          <div className="text-[10px] text-slate-500 mt-0.5">PDUFA</div>
        </div>
      )}
      <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-3 text-center">
        <div className="text-2xl font-bold text-green-400">{stats.highProb.length}</div>
        <div className="text-[10px] text-slate-500 mt-0.5" dir="rtl">סיכוי גבוה (80%+)</div>
      </div>
      <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-3 text-center">
        <div className="text-2xl font-bold text-yellow-400">{stats.avgProb}%</div>
        <div className="text-[10px] text-slate-500 mt-0.5" dir="rtl">ממוצע סיכוי</div>
      </div>
    </div>
  );
}


// ─── This Week Banner ──────────────────────────────────────

function ThisWeekBanner({ events }) {
  const thisWeek = useMemo(() => {
    return (events || []).filter(e => e.days_until !== null && e.days_until >= 0 && e.days_until <= 7)
      .sort((a, b) => (a.days_until || 0) - (b.days_until || 0));
  }, [events]);

  if (thisWeek.length === 0) return null;

  return (
    <div className="bg-gradient-to-r from-red-950/60 to-orange-950/40 border border-red-500/30 rounded-lg p-3 mb-4">
      <div className="flex items-center gap-2 mb-2">
        <Zap size={16} className="text-red-400" />
        <span className="text-sm font-bold text-red-300" dir="rtl">אירועים קרובים השבוע ({thisWeek.length})</span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-1">
        {thisWeek.map((e, i) => {
          const catStyle = getCatalystStyle(e.catalyst_type);
          const prob = e.approval_probability?.probability;
          return (
            <div key={i} className={`flex-shrink-0 bg-slate-900/60 border ${catStyle.border} rounded-lg px-3 py-2 min-w-[160px]`}>
              <div className="flex items-center gap-2">
                <span className="text-lg font-bold text-white">{e.ticker}</span>
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold text-white ${catStyle.bg}`}>
                  {e.catalyst_type}
                </span>
              </div>
              <div className="text-xs text-slate-400 mt-0.5">{formatDate(e.catalyst_date)}</div>
              <div className="flex items-center gap-2 mt-1">
                <span className={`text-xs font-bold ${
                  e.days_until === 0 ? 'text-red-400 animate-pulse' : 'text-orange-400'
                }`}>
                  {e.days_until === 0 ? 'TODAY!' : `${e.days_until} days`}
                </span>
                {prob !== undefined && (
                  <span className={`text-[10px] font-bold ${
                    prob >= 80 ? 'text-green-400' : prob >= 50 ? 'text-yellow-400' : 'text-orange-400'
                  }`}>{prob}%</span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ─── Fundamentals Panel ──────────────────────────────────

function FundamentalsPanel({ fundamentals }) {
  if (!fundamentals || Object.keys(fundamentals).length === 0) return null;

  const f = fundamentals;

  const Item = ({ label, value, highlight, warn }) => {
    if (!value || value === '-' || value === '') return null;
    let valColor = 'text-white';
    if (highlight) {
      const num = parseFloat(String(value).replace('%', ''));
      valColor = num > 0 ? 'text-green-400' : num < 0 ? 'text-red-400' : 'text-white';
    }
    if (warn) valColor = 'text-orange-400';

    return (
      <div className="bg-slate-900/50 rounded p-2">
        <span className="text-[10px] text-slate-500 block">{label}</span>
        <span className={`text-sm font-bold ${valColor}`}>{value}</span>
      </div>
    );
  };

  return (
    <div className="space-y-3">
      {/* Ownership & Transactions */}
      <div>
        <span className="text-xs text-slate-400 font-semibold mb-2 block">OWNERSHIP</span>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Item label="Inst Own" value={f.inst_own} />
          <Item label="Inst Trans" value={f.inst_trans} highlight />
          <Item label="Insider Own" value={f.insider_own} />
          <Item label="Insider Trans" value={f.insider_trans} highlight />
        </div>
      </div>

      {/* Volume & Short */}
      <div>
        <span className="text-xs text-slate-400 font-semibold mb-2 block">VOLUME & SHORT</span>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Item label="Avg Volume" value={f.avg_volume} />
          <Item label="Volume" value={f.volume} />
          <Item label="Rel Volume" value={f.rel_volume} />
          <Item label="Gap" value={f.gap_pct} highlight />
          <Item label="Short Float" value={f.short_float} warn={parseFloat(String(f.short_float || '0').replace('%', '')) > 15} />
          <Item label="Short Ratio" value={f.short_ratio} />
          <Item label="Short Interest" value={f.short_interest} />
        </div>
      </div>

      {/* Moving Averages */}
      <div>
        <span className="text-xs text-slate-400 font-semibold mb-2 block">MOVING AVERAGES</span>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Item label="SMA20" value={f.sma20_dist} highlight />
          <Item label="SMA50" value={f.sma50_dist} highlight />
          <Item label="SMA200" value={f.sma200_dist} highlight />
          <Item label="RSI (14)" value={f.rsi} warn={parseFloat(f.rsi || '50') > 70 || parseFloat(f.rsi || '50') < 30} />
        </div>
      </div>

      {/* Margins & Financials */}
      <div>
        <span className="text-xs text-slate-400 font-semibold mb-2 block">MARGINS & FINANCIALS</span>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Item label="Gross Margin" value={f.gross_margin} highlight />
          <Item label="Oper Margin" value={f.oper_margin} highlight />
          <Item label="Profit Margin" value={f.profit_margin} highlight />
          <Item label="ROE" value={f.roe} highlight />
          <Item label="ROA" value={f.roa} highlight />
          <Item label="P/E" value={f.pe_ratio} />
          <Item label="Forward P/E" value={f.forward_pe} />
          <Item label="EPS (TTM)" value={f.eps_ttm} />
          <Item label="EPS Q/Q" value={f.eps_qq} highlight />
          <Item label="Sales Q/Q" value={f.sales_qq} highlight />
          <Item label="Debt/Eq" value={f.debt_equity} warn={parseFloat(f.debt_equity || '0') > 2} />
          <Item label="Market Cap" value={f.market_cap} />
        </div>
      </div>

      {/* Performance */}
      <div>
        <span className="text-xs text-slate-400 font-semibold mb-2 block">PERFORMANCE</span>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Item label="Perf Week" value={f.perf_week} highlight />
          <Item label="Perf Month" value={f.perf_month} highlight />
          <Item label="Perf Quarter" value={f.perf_quarter} highlight />
          <Item label="Perf YTD" value={f.perf_ytd} highlight />
          <Item label="52W High" value={f.w52_high_dist} highlight />
          <Item label="52W Low" value={f.w52_low_dist} highlight />
          <Item label="Beta" value={f.beta} />
          <Item label="ATR" value={f.atr} />
        </div>
      </div>

      {/* Analyst */}
      <div>
        <span className="text-xs text-slate-400 font-semibold mb-2 block">ANALYST</span>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Item label="Recommendation" value={f.analyst_recom} />
          <Item label="Target Price" value={f.target_price ? `$${f.target_price}` : ''} />
          <Item label="Earnings Date" value={f.earnings_date} />
        </div>
      </div>
    </div>
  );
}


// ─── News Panel ──────────────────────────────────────────

function EventNewsPanel({ news }) {
  if (!news || news.length === 0) return null;

  return (
    <div className="bg-slate-900/60 rounded-lg border border-slate-700 p-3">
      <div className="flex items-center gap-2 mb-2">
        <Newspaper size={14} className="text-orange-400" />
        <span className="text-xs font-bold text-slate-300">Latest News</span>
      </div>
      <div className="space-y-2">
        {news.map((item, i) => (
          <a key={i} href={item.link} target="_blank" rel="noopener noreferrer"
            className="block hover:bg-slate-800/50 rounded p-2 transition-colors group"
            onClick={e => e.stopPropagation()}>
            <div className="text-sm text-slate-200 group-hover:text-blue-300 leading-snug">
              {item.title}
            </div>
            {item.summary && (
              <p className="text-xs text-slate-400 mt-1 line-clamp-2">{item.summary}</p>
            )}
            <div className="flex items-center gap-2 mt-1">
              <span className="text-[10px] text-slate-500">{item.publisher}</span>
              {item.pub_date && (
                <span className="text-[10px] text-slate-600">{formatNewsDate(item.pub_date)}</span>
              )}
              <ExternalLink size={10} className="text-slate-600 group-hover:text-blue-400" />
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}


// ─── Stage Pipeline (BPIQ-style) ─────────────────────────

const PIPELINE_STAGES = [
  { key: 'Phase1', label: 'Phase 1', shortLabel: 'P1', color: 'teal', desc: 'בטיחות' },
  { key: 'Phase2', label: 'Phase 2', shortLabel: 'P2', color: 'cyan', desc: 'יעילות' },
  { key: 'Phase3', label: 'Phase 3', shortLabel: 'P3', color: 'blue', desc: 'ניסוי מתקדם' },
  { key: 'NDA', label: 'NDA/BLA', shortLabel: 'NDA', color: 'green', desc: 'הגשה לFDA' },
  { key: 'PDUFA', label: 'PDUFA', shortLabel: 'PDUFA', color: 'red', desc: 'תאריך החלטה' },
  { key: 'Approved', label: 'Approved', shortLabel: '✓', color: 'emerald', desc: 'מאושר' },
];

const STAGE_ORDER = { 'Phase1': 0, 'Phase 1': 0, 'Phase2': 1, 'Phase 2': 1, 'Phase3': 2, 'Phase 3': 2, 'NDA': 3, 'BLA': 3, 'NDA/BLA': 3, 'PDUFA': 4, 'AdCom': 4, 'Approval': 5, 'Approved': 5, 'CRL': -1 };

function StagePipeline({ event }) {
  const catType = event.catalyst_type || '';
  const phase = event.phase || '';
  const status = (event.status || '').toLowerCase();

  // Determine current stage index
  let currentStage = STAGE_ORDER[catType] ?? STAGE_ORDER[phase] ?? -1;
  if (status.includes('approved')) currentStage = 5;
  if (status.includes('crl') || status.includes('rejected')) currentStage = -1;

  const isCRL = status.includes('crl') || status.includes('rejected') || catType === 'CRL';

  return (
    <div className="flex items-center gap-0.5 w-full" dir="ltr">
      {PIPELINE_STAGES.map((stage, idx) => {
        const isCompleted = idx < currentStage;
        const isCurrent = idx === currentStage;
        const isFuture = idx > currentStage;

        let bgClass, textClass, borderClass;
        if (isCRL && idx === 4) {
          bgClass = 'bg-red-900/60';
          textClass = 'text-red-400';
          borderClass = 'border-red-500/50';
        } else if (isCompleted) {
          bgClass = `bg-${stage.color}-900/40`;
          textClass = `text-${stage.color}-400`;
          borderClass = `border-${stage.color}-500/30`;
        } else if (isCurrent) {
          bgClass = `bg-${stage.color}-800/60`;
          textClass = `text-${stage.color}-300 font-bold`;
          borderClass = `border-${stage.color}-400/60`;
        } else {
          bgClass = 'bg-slate-800/30';
          textClass = 'text-slate-600';
          borderClass = 'border-slate-700/30';
        }

        // Use inline styles for dynamic colors since Tailwind can't handle dynamic class names
        const colorMap = {
          teal: { completed: { bg: 'rgba(20,184,166,0.15)', text: '#2dd4bf', border: 'rgba(20,184,166,0.3)' }, current: { bg: 'rgba(20,184,166,0.25)', text: '#5eead4', border: 'rgba(20,184,166,0.6)' } },
          cyan: { completed: { bg: 'rgba(6,182,212,0.15)', text: '#22d3ee', border: 'rgba(6,182,212,0.3)' }, current: { bg: 'rgba(6,182,212,0.25)', text: '#67e8f9', border: 'rgba(6,182,212,0.6)' } },
          blue: { completed: { bg: 'rgba(59,130,246,0.15)', text: '#60a5fa', border: 'rgba(59,130,246,0.3)' }, current: { bg: 'rgba(59,130,246,0.25)', text: '#93c5fd', border: 'rgba(59,130,246,0.6)' } },
          green: { completed: { bg: 'rgba(34,197,94,0.15)', text: '#4ade80', border: 'rgba(34,197,94,0.3)' }, current: { bg: 'rgba(34,197,94,0.25)', text: '#86efac', border: 'rgba(34,197,94,0.6)' } },
          red: { completed: { bg: 'rgba(239,68,68,0.15)', text: '#f87171', border: 'rgba(239,68,68,0.3)' }, current: { bg: 'rgba(239,68,68,0.25)', text: '#fca5a5', border: 'rgba(239,68,68,0.6)' } },
          emerald: { completed: { bg: 'rgba(16,185,129,0.15)', text: '#34d399', border: 'rgba(16,185,129,0.3)' }, current: { bg: 'rgba(16,185,129,0.25)', text: '#6ee7b7', border: 'rgba(16,185,129,0.6)' } },
        };

        const palette = colorMap[stage.color] || colorMap.blue;
        const style = isCRL && idx === 4
          ? { background: 'rgba(239,68,68,0.2)', color: '#f87171', borderColor: 'rgba(239,68,68,0.5)' }
          : isCompleted
            ? { background: palette.completed.bg, color: palette.completed.text, borderColor: palette.completed.border }
            : isCurrent
              ? { background: palette.current.bg, color: palette.current.text, borderColor: palette.current.border }
              : { background: 'rgba(30,41,59,0.3)', color: '#475569', borderColor: 'rgba(51,65,85,0.3)' };

        return (
          <div key={stage.key} className="flex items-center flex-1 min-w-0">
            <div
              className={`flex-1 text-center py-1 px-0.5 rounded border text-[9px] leading-tight transition-all ${isCurrent ? 'ring-1' : ''}`}
              style={{ ...style, ...(isCurrent ? { boxShadow: `0 0 6px ${style.borderColor}` } : {}) }}
              title={stage.desc}
            >
              <div className="font-bold" style={{ color: style.color }}>
                {isCRL && idx === 4 ? 'CRL' : stage.shortLabel}
              </div>
              {isCurrent && (
                <div className="text-[7px] opacity-70" style={{ color: style.color }}>◄ כאן</div>
              )}
            </div>
            {idx < PIPELINE_STAGES.length - 1 && (
              <ArrowRight size={8} className="shrink-0 mx-0.5" style={{ color: isCompleted ? style.color : '#334155' }} />
            )}
          </div>
        );
      })}
    </div>
  );
}


// ─── FDA Movers Section ──────────────────────────────────

function FDAMoversSection({ movers, loading: moversLoading }) {
  const [showAll, setShowAll] = useState(false);

  if (moversLoading) {
    return (
      <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Flame size={16} className="text-orange-400" />
          <span className="text-sm font-bold text-white" dir="rtl">מעקב מניות FDA — תנועות אחרונות</span>
        </div>
        <div className="text-center py-4 text-slate-500 text-sm">Loading movers data...</div>
      </div>
    );
  }

  if (!movers || movers.length === 0) return null;

  const displayMovers = showAll ? movers : movers.slice(0, 5);

  // Pattern summary
  const bigMovers = movers.filter(m => Math.abs(m.catalyst_day_move || 0) >= 10);
  const avgMove = movers.reduce((sum, m) => sum + Math.abs(m.catalyst_day_move || 0), 0) / movers.length;
  const approvals = movers.filter(m => m.catalyst_type === 'Approval' || (m.status || '').toLowerCase().includes('approved'));
  const crls = movers.filter(m => m.catalyst_type === 'CRL' || (m.status || '').toLowerCase().includes('crl'));

  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Flame size={16} className="text-orange-400" />
          <span className="text-sm font-bold text-white" dir="rtl">מעקב מניות FDA — תנועות אחרונות</span>
        </div>
        <span className="text-[10px] text-slate-500">{movers.length} events tracked</span>
      </div>

      {/* Pattern Summary */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <div className="bg-slate-900/60 rounded p-2 text-center">
          <div className="text-lg font-bold text-white">{movers.length}</div>
          <div className="text-[9px] text-slate-500" dir="rtl">אירועים שהתרחשו</div>
        </div>
        <div className="bg-slate-900/60 rounded p-2 text-center">
          <div className={`text-lg font-bold ${bigMovers.length > 0 ? 'text-orange-400' : 'text-slate-400'}`}>{bigMovers.length}</div>
          <div className="text-[9px] text-slate-500" dir="rtl">תנועות מעל 10%</div>
        </div>
        <div className="bg-slate-900/60 rounded p-2 text-center">
          <div className="text-lg font-bold text-yellow-400">{avgMove.toFixed(1)}%</div>
          <div className="text-[9px] text-slate-500" dir="rtl">תנועה ממוצעת (abs)</div>
        </div>
        <div className="bg-slate-900/60 rounded p-2 text-center">
          <div className="text-lg font-bold text-green-400">{approvals.length}</div>
          <div className="text-[9px] text-slate-500" dir="rtl">
            אישורים {crls.length > 0 ? ` / ${crls.length} CRL` : ''}
          </div>
        </div>
      </div>

      {/* Insight box */}
      <div className="bg-amber-950/30 border border-amber-500/20 rounded-lg p-3 mb-3" dir="rtl">
        <div className="text-xs font-bold text-amber-400 mb-1">תובנות מהשבועות האחרונים:</div>
        <div className="space-y-1 text-[11px] text-amber-300/80">
          {bigMovers.length > 0 ? (
            bigMovers.slice(0, 3).map((m, i) => (
              <div key={i}>
                • <span className="font-bold text-white">{m.ticker}</span> ({m.catalyst_type}) זזה{' '}
                <span className={m.catalyst_day_move > 0 ? 'text-green-400' : 'text-red-400'}>
                  {m.catalyst_day_move > 0 ? '+' : ''}{m.catalyst_day_move?.toFixed(1)}%
                </span>
                {m.volume_ratio >= 2 ? ` בנפח ${m.volume_ratio}x` : ''}
                {Math.abs(m.gap_pct || 0) >= 3 ? ` (גאפ ${m.gap_pct > 0 ? '+' : ''}${m.gap_pct?.toFixed(1)}%)` : ''}
              </div>
            ))
          ) : (
            <div>• רוב האירועים האחרונים הראו תגובה מתונה — השוק כבר תמחר את התוצאות</div>
          )}
          {avgMove < 3 && <div>• תנועות מתונות — ייתכן שהשוק "מתמחר" אישורים מראש. חפש מניות עם PoA נמוך יותר לתנועות גדולות</div>}
          {bigMovers.filter(m => m.catalyst_day_move > 10).length > 0 && (
            <div>• תבנית: מניות קטנות עם אישור PDUFA נוטות לתנועות הגדולות ביותר</div>
          )}
        </div>
      </div>

      <div className="space-y-2">
        {displayMovers.map((m, idx) => {
          const move = m.catalyst_day_move || 0;
          const isUp = move >= 0;
          const moveAbs = Math.abs(move);
          const analysis = m.analysis || {};
          const signals = analysis.signals || [];
          const takeaways = analysis.takeaways || [];

          return (
            <div key={idx} className={`rounded-lg border p-3 ${
              moveAbs >= 20 ? (isUp ? 'bg-green-950/40 border-green-500/30' : 'bg-red-950/40 border-red-500/30') :
              moveAbs >= 10 ? (isUp ? 'bg-green-950/20 border-green-500/20' : 'bg-red-950/20 border-red-500/20') :
              'bg-slate-900/40 border-slate-700/50'
            }`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-2">
                    <span className="text-lg font-bold text-white">{m.ticker}</span>
                    <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold text-white ${
                      getCatalystStyle(m.catalyst_type).bg
                    }`}>{m.catalyst_type}</span>
                  </div>
                  <span className="text-xs text-slate-500">{formatDate(m.catalyst_date)}</span>
                  {m.drug_name && <span className="text-xs text-slate-400">{m.drug_name}</span>}
                </div>

                <div className="flex items-center gap-3">
                  {/* Price move */}
                  <div className="text-right">
                    <div className={`text-lg font-bold ${isUp ? 'text-green-400' : 'text-red-400'}`}>
                      {isUp ? '+' : ''}{move.toFixed(1)}%
                    </div>
                    <div className="text-[10px] text-slate-500" dir="ltr">
                      ${m.price_before} → ${m.price_after}
                    </div>
                  </div>

                  {/* Volume */}
                  {m.volume_ratio >= 2 && (
                    <div className="text-right">
                      <div className="text-sm font-bold text-orange-400">{m.volume_ratio}x</div>
                      <div className="text-[10px] text-slate-500">vol</div>
                    </div>
                  )}
                </div>
              </div>

              {/* Gap + Intraday + Post move */}
              <div className="flex items-center gap-4 mt-2 text-[11px]">
                {m.gap_pct !== 0 && (
                  <span className={m.gap_pct > 0 ? 'text-green-500' : 'text-red-500'}>
                    Gap: {m.gap_pct > 0 ? '+' : ''}{m.gap_pct.toFixed(1)}%
                  </span>
                )}
                <span className="text-slate-500">Intraday range: {m.intraday_range?.toFixed(1)}%</span>
                {m.week_move !== undefined && (
                  <span className={m.week_move > 0 ? 'text-green-500' : 'text-red-500'}>
                    Week: {m.week_move > 0 ? '+' : ''}{m.week_move.toFixed(1)}%
                  </span>
                )}
                {m.post_catalyst_move !== undefined && m.post_catalyst_move !== 0 && (
                  <span className={m.post_catalyst_move > 0 ? 'text-green-500' : 'text-red-500'}>
                    After: {m.post_catalyst_move > 0 ? '+' : ''}{m.post_catalyst_move.toFixed(1)}%
                  </span>
                )}
              </div>

              {/* Analysis signals */}
              {signals.length > 0 && (
                <div className="mt-2 space-y-0.5">
                  {signals.map((s, si) => (
                    <div key={si} className="text-[11px] text-slate-400 flex items-start gap-1">
                      <Eye size={10} className="text-slate-600 mt-0.5 shrink-0" />
                      <span>{s}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Takeaways */}
              {takeaways.length > 0 && (
                <div className="mt-1.5 pt-1.5 border-t border-slate-700/50">
                  {takeaways.map((t, ti) => (
                    <div key={ti} className="text-[11px] text-amber-400/80 flex items-start gap-1" dir="rtl">
                      <span className="text-amber-500 shrink-0">💡</span>
                      <span>{t}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {movers.length > 5 && (
        <button
          onClick={() => setShowAll(!showAll)}
          className="w-full mt-2 py-1.5 text-xs text-slate-400 hover:text-white bg-slate-900/50 rounded transition-colors"
        >
          {showAll ? 'Show less' : `Show all ${movers.length} movers`}
        </button>
      )}
    </div>
  );
}


// ─── Today's Biotech Movers ──────────────────────────────

function RsiBlock({ rsi_hourly, rsi_daily, rsi_monthly }) {
  const hasAny = rsi_hourly != null || rsi_daily != null || rsi_monthly != null;
  if (!hasAny) return null;

  const hourlyAlert = rsi_hourly != null && (
    rsi_hourly > 70 ||
    (rsi_daily != null && rsi_hourly - rsi_daily > 20)
  );

  const rsiColor = (v) => {
    if (v == null) return 'text-slate-600';
    if (v > 70) return 'text-red-400';
    if (v < 30) return 'text-green-400';
    return 'text-slate-300';
  };

  return (
    <div className={`flex flex-col items-end gap-0.5 ${hourlyAlert ? 'bg-orange-950/40 rounded px-1.5 py-1 ring-1 ring-orange-500/40' : ''}`}>
      <div className="text-[8px] text-slate-500 font-semibold tracking-wide uppercase">RSI</div>
      <div className="flex gap-1.5 items-center">
        {rsi_hourly != null && (
          <span className={`text-[11px] font-bold font-mono ${rsiColor(rsi_hourly)}`}>
            {hourlyAlert && <span className="text-orange-400">⚡</span>}H:{rsi_hourly}
          </span>
        )}
        {rsi_daily != null && (
          <span className={`text-[10px] font-mono ${rsiColor(rsi_daily)}`}>D:{rsi_daily}</span>
        )}
        {rsi_monthly != null && (
          <span className={`text-[10px] font-mono ${rsiColor(rsi_monthly)}`}>M:{rsi_monthly}</span>
        )}
      </div>
    </div>
  );
}

function MoverCard({ m, idx }) {
  const changeNum = parseFloat(String(m.change_pct || '0').replace('%', '').replace('+', '')) || 0;
  const isUp = m.direction === 'up';
  const absChange = Math.abs(changeNum);
  const reasons = m.move_reason || {};

  const hourlyAlert = m.rsi_hourly != null && (
    m.rsi_hourly > 70 || (m.rsi_daily != null && m.rsi_hourly - m.rsi_daily > 20)
  );

  return (
    <div className={`rounded-lg border p-3 ${
      absChange >= 15 ? (isUp ? 'bg-green-950/40 border-green-500/30' : 'bg-red-950/40 border-red-500/30') :
      absChange >= 7  ? (isUp ? 'bg-green-950/20 border-green-500/20' : 'bg-red-950/20 border-red-500/20') :
                        'bg-slate-900/40 border-slate-700/50'
    } ${hourlyAlert ? 'ring-1 ring-orange-500/30' : ''}`}>

      {/* TOP ROW: ticker + badges (left) | RSI + change (right) */}
      <div className="flex items-start justify-between mb-1.5">
        <div className="flex items-center gap-1.5 flex-wrap">
          <a href={`https://finance.yahoo.com/quote/${m.ticker}`} target="_blank" rel="noopener noreferrer"
            className="text-base font-bold text-white hover:text-blue-400 transition-colors">
            {m.ticker}
          </a>
          {m.has_fda_catalyst && (
            <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold text-white ${
              getCatalystStyle(m.catalyst_type).bg
            }`}>{m.catalyst_type}</span>
          )}
          <span className="text-[10px] text-slate-500 max-w-[130px] truncate">{m.company !== m.ticker ? m.company : ''}</span>
        </div>

        {/* Right side: RSI block + change + price + vol */}
        <div className="flex items-start gap-3 shrink-0">
          {/* RSI — most prominent position, top-right */}
          <RsiBlock rsi_hourly={m.rsi_hourly} rsi_daily={m.rsi_daily} rsi_monthly={m.rsi_monthly} />

          <div className="flex items-start gap-2">
            <div className="text-right">
              <div className={`text-lg font-bold leading-tight ${isUp ? 'text-green-400' : 'text-red-400'}`}>
                {m.change_pct}
              </div>
              {m.price && <div className="text-[10px] text-slate-500">${m.price}</div>}
            </div>
            {m.volume && (
              <div className="text-right">
                <div className="text-xs text-slate-400">{m.volume}</div>
                <div className="text-[10px] text-slate-600">vol</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {m.has_fda_catalyst && (
        <div className="mb-1.5">
          <StagePipeline event={{
            catalyst_type: m.catalyst_type,
            phase: m.phase || '',
            status: m.status || '',
          }} />
        </div>
      )}

      <div dir="rtl" className="mt-1">
        {(reasons.reasons_he || []).map((reason, ri) => (
          <div key={ri} className="text-[11px] text-amber-400/80 flex items-start gap-1">
            <span className="text-amber-500 shrink-0">→</span>
            <span>{reason}</span>
          </div>
        ))}
      </div>

      {m.has_fda_catalyst && (
        <div className="mt-1.5 pt-1.5 border-t border-slate-700/30 flex items-center gap-3 flex-wrap text-[10px] text-slate-500">
          {m.drug_name && <span>Drug: <span className="text-slate-300">{m.drug_name}</span></span>}
          {m.indication && <span>Indication: <span className="text-slate-300">{m.indication}</span></span>}
          {m.catalyst_date && <span>Date: <span className="text-slate-300">{m.catalyst_date}</span></span>}
          {m.approval_probability?.probability && (
            <span>PoA: <span className="text-green-400 font-bold">{m.approval_probability.probability}%</span></span>
          )}
        </div>
      )}

      <div className="flex items-center gap-3 mt-1 text-[10px] text-slate-600">
        {m.industry && <span>{m.industry}</span>}
        {m.market_cap && <span>MCap: {m.market_cap}</span>}
      </div>
    </div>
  );
}

function MoversSection({ movers, sessionDate, isToday, isMarketOpen }) {
  const [showAll, setShowAll] = useState(false);

  const formatSessionDate = (dateStr) => {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr + 'T12:00:00');
      const heDay = ['ראשון', 'שני', 'שלישי', 'רביעי', 'חמישי', 'שישי', 'שבת'][d.getDay()];
      return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} (${heDay})`;
    } catch { return dateStr; }
  };

  const fdaRelated = movers.filter(m => m.has_fda_catalyst);
  const upMovers = movers.filter(m => m.direction === 'up');
  const downMovers = movers.filter(m => m.direction === 'down');
  const displayMovers = showAll ? movers : movers.slice(0, 10);

  // RSI alerts: stocks with elevated hourly RSI
  const rsiAlerts = movers.filter(m =>
    (m.rsi_hourly != null && m.rsi_hourly > 70) ||
    (m.rsi_hourly != null && m.rsi_daily != null && m.rsi_hourly - m.rsi_daily > 20)
  );

  const borderColor = isToday ? 'border-green-500/30' : 'border-slate-600/40';
  const headerColor = isToday ? 'text-green-400' : 'text-blue-400';

  return (
    <div className={`bg-slate-800/60 border ${borderColor} rounded-lg p-4 mb-4`}>
      {/* Section Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Activity size={15} className={headerColor} />
          <span className={`text-sm font-bold ${headerColor}`} dir="rtl">
            זינוקים {isToday ? 'של היום' : 'של אתמול'}
          </span>
          {sessionDate && (
            <span className="text-[10px] text-slate-500">{formatSessionDate(sessionDate)}</span>
          )}
          {isToday && isMarketOpen && (
            <span className="px-1.5 py-0.5 bg-green-600/30 text-green-400 text-[9px] rounded font-bold">LIVE</span>
          )}
          {isToday && !isMarketOpen && (
            <span className="px-1.5 py-0.5 bg-slate-700 text-slate-400 text-[9px] rounded">סגור</span>
          )}
        </div>
        <span className="text-[10px] text-slate-500">{movers.length} stocks</span>
      </div>

      {movers.length === 0 ? (
        <div className="text-center py-4">
          <p className="text-slate-500 text-xs" dir="rtl">
            {isToday && !isMarketOpen ? 'השוק סגור — אין נתוני מסחר עדיין' : 'אין מניות עם תנועה >3%'}
          </p>
        </div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-3 gap-2 mb-3">
            <div className="bg-slate-900/60 rounded p-2 text-center">
              <div className="text-base font-bold text-green-400">{upMovers.length}</div>
              <div className="text-[9px] text-slate-500" dir="rtl">עולות</div>
            </div>
            <div className="bg-slate-900/60 rounded p-2 text-center">
              <div className="text-base font-bold text-red-400">{downMovers.length}</div>
              <div className="text-[9px] text-slate-500" dir="rtl">יורדות</div>
            </div>
            <div className="bg-slate-900/60 rounded p-2 text-center">
              <div className={`text-base font-bold ${fdaRelated.length > 0 ? 'text-orange-400' : 'text-slate-400'}`}>{fdaRelated.length}</div>
              <div className="text-[9px] text-slate-500" dir="rtl">FDA</div>
            </div>
          </div>

          {/* FDA highlights */}
          {fdaRelated.length > 0 && (
            <div className="bg-orange-950/30 border border-orange-500/20 rounded-lg p-2 mb-3" dir="rtl">
              <div className="text-[10px] font-bold text-orange-400 mb-1">קשורות ל-FDA:</div>
              <div className="space-y-0.5 text-[10px] text-orange-300/80">
                {fdaRelated.slice(0, 3).map((m, i) => (
                  <div key={i}>
                    • <span className="font-bold text-white">{m.ticker}</span>{' '}
                    <span className={m.direction === 'up' ? 'text-green-400' : 'text-red-400'}>{m.change_pct}</span>
                    {' — '}{m.move_reason?.reasons_he?.[0] || m.catalyst_type}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* RSI Alert Banner */}
          {rsiAlerts.length > 0 && (
            <div className="bg-orange-950/30 border border-orange-500/30 rounded-lg p-2 mb-3" dir="rtl">
              <div className="text-[10px] font-bold text-orange-300 mb-0.5">⚡ RSI שעתי גבוה מהרגיל:</div>
              <div className="text-[10px] text-orange-300/80 flex flex-wrap gap-2">
                {rsiAlerts.map((m, i) => (
                  <span key={i}>
                    <span className="font-bold text-white">{m.ticker}</span>
                    {m.rsi_hourly != null && <span className="text-orange-400"> H:{m.rsi_hourly}</span>}
                    {m.rsi_daily != null && <span className="text-slate-400"> D:{m.rsi_daily}</span>}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Mover cards */}
          <div className="space-y-2">
            {displayMovers.map((m, idx) => <MoverCard key={`${m.ticker}-${idx}`} m={m} idx={idx} />)}
          </div>

          {movers.length > 10 && (
            <button
              onClick={() => setShowAll(!showAll)}
              className="w-full mt-2 py-1.5 text-xs text-slate-400 hover:text-white bg-slate-900/50 rounded transition-colors"
            >
              {showAll ? 'הצג פחות' : `הצג את כל ${movers.length} המניות`}
            </button>
          )}
        </>
      )}
    </div>
  );
}

function TodaysBiotechMovers({ data, loading: moversLoading }) {
  if (moversLoading) {
    return (
      <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-4 mb-4">
        <div className="flex items-center gap-2 mb-3">
          <Activity size={16} className="text-green-400 animate-pulse" />
          <span className="text-sm font-bold text-white" dir="rtl">סורק זינוקים של היום ואתמול...</span>
        </div>
        <div className="flex justify-center py-6">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-green-500"></div>
        </div>
      </div>
    );
  }

  const today = data?.today || { movers: [], session_date: '', is_market_open: false };
  const yesterday = data?.yesterday || { movers: [], session_date: '' };

  return (
    <div>
      <MoversSection
        movers={today.movers || []}
        sessionDate={today.session_date}
        isToday={true}
        isMarketOpen={today.is_market_open}
      />
      <MoversSection
        movers={yesterday.movers || []}
        sessionDate={yesterday.session_date}
        isToday={false}
        isMarketOpen={false}
      />
    </div>
  );
}


// ─── Catalyst Event Card (expandable) ────────────────────

function RsiCircle({ rsi }) {
  const val = parseFloat(rsi);
  if (!val || isNaN(val)) return null;
  const pct = Math.min(val / 100, 1);
  const color = val >= 70 ? '#f87171' : val <= 30 ? '#4ade80' : '#22d3ee';
  const label = val >= 70 ? '⚡ RSI' : val <= 30 ? '↓ RSI' : 'RSI';
  const circumference = 2 * Math.PI * 22;
  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: 56, height: 56 }}>
        <svg className="transform -rotate-90" width="56" height="56">
          <circle cx="28" cy="28" r="22" stroke="#334155" strokeWidth="4" fill="transparent" />
          <circle cx="28" cy="28" r="22" stroke={color} strokeWidth="4" fill="transparent"
            strokeDasharray={circumference}
            strokeDashoffset={circumference * (1 - pct)}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm font-bold" style={{ color }}>{Math.round(val)}</span>
        </div>
      </div>
      <span className="text-[10px] font-semibold" style={{ color: val >= 70 || val <= 30 ? color : '#64748b' }}>{label}</span>
    </div>
  );
}

function CatalystEventCard({ event, rank, viewMode, isWatchlisted, onToggleWatchlist }) {
  const [expanded, setExpanded] = useState(false);
  const catStyle = getCatalystStyle(event.catalyst_type);
  const daysBadge = getDaysUntilBadge(event.days_until);
  const fundamentals = event.fundamentals || {};
  const score = event.catalyst_score || 0;

  // Price/change from fundamentals
  const price = fundamentals.price;
  const changePct = fundamentals.change_pct;

  // Urgency glow for imminent events
  const urgentClass = daysBadge.urgency >= 3 ? `ring-1 ${catStyle.ring}` : '';

  return (
    <div className={`rounded-lg border transition-all ${urgentClass} ${
      rank <= 3 ? `${catStyle.border} bg-slate-800/80` : 'border-slate-700 bg-slate-800/50'
    }`}>
      {/* Header row */}
      <div className="p-4 cursor-pointer hover:bg-slate-700/20 transition-colors" onClick={() => setExpanded(!expanded)}>
        <div className="flex items-start justify-between gap-3">
          {/* Left: Days + Ticker + Drug + Type */}
          <div className="flex items-start gap-3 flex-1 min-w-0">
            {/* Days until badge */}
            <div className={`px-2.5 py-1.5 rounded-lg text-center font-bold text-sm shrink-0 ${daysBadge.color}`}>
              {daysBadge.label}
            </div>

            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                {/* Watchlist star */}
                <button
                  onClick={(e) => { e.stopPropagation(); onToggleWatchlist(event.ticker); }}
                  className={`transition-colors ${isWatchlisted ? 'text-yellow-400' : 'text-slate-600 hover:text-yellow-400'}`}
                  title={isWatchlisted ? 'Remove from watchlist' : 'Add to watchlist'}
                >
                  <Star size={16} fill={isWatchlisted ? 'currentColor' : 'none'} />
                </button>

                <span className="text-xl font-bold text-white">{event.ticker}</span>
                {price && (
                  <span className="text-sm text-slate-300 font-mono">${price}</span>
                )}
                {changePct && (
                  <span className={`text-sm font-bold ${changeColor(changePct)}`}>
                    {parseFloat(changePct) > 0 ? '+' : ''}{changePct}
                  </span>
                )}
                {/* Catalyst type badge + Hebrew explanation */}
                <span className={`px-2 py-0.5 rounded text-[10px] font-bold text-white ${catStyle.bg}`}>
                  {event.catalyst_type}
                </span>
                {catalystTypeHebrew[event.catalyst_type] && (
                  <span className="text-[10px] text-slate-500" dir="rtl">
                    {catalystTypeHebrew[event.catalyst_type]}
                  </span>
                )}
                {/* Phase badge */}
                {event.phase && (
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold text-slate-300 bg-slate-700">
                    {event.phase}
                  </span>
                )}
                {/* Multi-source badge */}
                {(event.sources || []).length >= 2 && (
                  <span className="px-1.5 py-0.5 rounded text-[9px] font-bold text-green-400 bg-green-900/40 border border-green-500/30">
                    {event.sources.length} sources
                  </span>
                )}
              </div>

              <div className="text-xs text-slate-400 mt-1">
                {event.company && <span>{event.company}</span>}
              </div>

              {/* Drug + Indication */}
              {(event.drug_name || event.indication) && (
                <div className="text-xs text-slate-300 mt-1">
                  {event.drug_name && <span className="font-semibold text-white">{event.drug_name}</span>}
                  {event.drug_name && event.indication && <span className="text-slate-500"> - </span>}
                  {event.indication && <span>{event.indication}</span>}
                </div>
              )}

              {/* Hebrew description: what the company does + stage */}
              {getHebrewDescription(event) && (
                <div className="text-[11px] text-amber-400/80 mt-1" dir="rtl">
                  {getHebrewDescription(event)}
                </div>
              )}

              {/* Stage Pipeline */}
              <div className="mt-2 mb-1">
                <StagePipeline event={event} />
              </div>

              {/* Date + Status */}
              <div className="flex items-center gap-3 mt-1.5">
                <div className="flex items-center gap-1 text-xs text-slate-500">
                  <Calendar size={11} />
                  <span>{formatDate(event.catalyst_date)}</span>
                </div>
                {event.status && event.status !== 'Upcoming' && (
                  <span className={`text-[10px] px-2 py-0.5 rounded ${
                    event.status.includes('Approved') ? 'text-green-400 bg-green-900/40' :
                    event.status.includes('Rejected') || event.status.includes('CRL') ? 'text-red-400 bg-red-900/40' :
                    'text-slate-400 bg-slate-700/50'
                  }`}>
                    {event.status}
                  </span>
                )}
              </div>

              {/* Key fundamentals preview */}
              <div className="flex items-center gap-2 mt-2 flex-wrap">
                {fundamentals.market_cap && (
                  <span className="px-2 py-0.5 rounded bg-indigo-900/50 border border-indigo-500/30 text-indigo-300 text-[10px] font-bold">
                    MCap: {fundamentals.market_cap}
                  </span>
                )}
                {fundamentals.inst_own && (
                  <span className="px-2 py-0.5 rounded bg-slate-700 text-slate-300 text-[10px]">
                    Inst: {fundamentals.inst_own}
                  </span>
                )}
                {fundamentals.short_float && (
                  <span className={`px-2 py-0.5 rounded text-[10px] ${
                    parseFloat(String(fundamentals.short_float).replace('%', '')) > 15
                      ? 'bg-orange-900/50 border border-orange-500/30 text-orange-300'
                      : 'bg-slate-700 text-slate-300'
                  }`}>
                    Short: {fundamentals.short_float}
                  </span>
                )}
                {fundamentals.analyst_recom && (
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    fundamentals.analyst_recom.includes('Buy') ? 'bg-green-900/50 text-green-300'
                    : fundamentals.analyst_recom.includes('Sell') ? 'bg-red-900/50 text-red-300'
                    : 'bg-slate-700 text-slate-300'
                  }`}>
                    {fundamentals.analyst_recom}
                  </span>
                )}
                {fundamentals.rel_volume && parseFloat(fundamentals.rel_volume) >= 1.5 && (
                  <span className="px-2 py-0.5 rounded bg-orange-900/50 text-orange-300 text-[10px] font-bold">
                    {fundamentals.rel_volume}x Vol
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Right: Probability + Score + RSI + Expand */}
          <div className="flex flex-col items-end gap-1 shrink-0">
            <div className="flex items-center gap-2">
              {/* Approval probability */}
              {event.approval_probability && (
                <div className="flex flex-col items-center">
                  <div className="relative">
                    <svg className="transform -rotate-90 w-14 h-14">
                      <circle cx="28" cy="28" r="22" stroke="currentColor" strokeWidth="4" fill="transparent" className="text-slate-700" />
                      <circle cx="28" cy="28" r="22" stroke="currentColor" strokeWidth="4" fill="transparent"
                        strokeDasharray={`${2 * Math.PI * 22}`}
                        strokeDashoffset={`${2 * Math.PI * 22 * (1 - event.approval_probability.probability / 100)}`}
                        className={
                          event.approval_probability.probability >= 85 ? 'text-green-400' :
                          event.approval_probability.probability >= 60 ? 'text-yellow-400' :
                          event.approval_probability.probability >= 30 ? 'text-orange-400' : 'text-red-400'
                        }
                      />
                    </svg>
                    <div className="absolute inset-0 flex items-center justify-center">
                      <span className={`text-sm font-bold ${
                        event.approval_probability.probability >= 85 ? 'text-green-400' :
                        event.approval_probability.probability >= 60 ? 'text-yellow-300' :
                        event.approval_probability.probability >= 30 ? 'text-orange-400' : 'text-red-400'
                      }`}>{event.approval_probability.probability}%</span>
                    </div>
                  </div>
                  <span className="text-[10px] text-slate-500" dir="rtl">סיכוי</span>
                </div>
              )}

              {/* Score circle */}
              <div className="flex flex-col items-center">
                <div className="relative">
                  <svg className="transform -rotate-90 w-14 h-14">
                    <circle cx="28" cy="28" r="22" stroke="currentColor" strokeWidth="4" fill="transparent" className="text-slate-700" />
                    <circle cx="28" cy="28" r="22" stroke="currentColor" strokeWidth="4" fill="transparent"
                      strokeDasharray={`${2 * Math.PI * 22}`}
                      strokeDashoffset={`${2 * Math.PI * 22 * (1 - score / 100)}`}
                      className={score >= 70 ? 'text-green-400' : score >= 50 ? 'text-yellow-400' : 'text-blue-400'}
                    />
                  </svg>
                  <div className="absolute inset-0 flex items-center justify-center">
                    <span className="text-sm font-bold text-white">{score}</span>
                  </div>
                </div>
                <span className="text-[10px] text-slate-500" dir="rtl">ציון</span>
              </div>

              {/* RSI circle (from Finviz fundamentals) */}
              <RsiCircle rsi={fundamentals.rsi} />
            </div>

            <div className="mt-1 flex items-center gap-1">
              <span className="text-[10px] text-slate-600">{expanded ? 'Less' : 'More'}</span>
              {expanded ? <ChevronUp size={14} className="text-slate-500" /> : <ChevronDown size={14} className="text-slate-500" />}
            </div>
          </div>
        </div>
      </div>

      {/* Expanded section */}
      {expanded && (
        <div className="border-t border-slate-700 p-4 space-y-4">
          {/* Countdown bar */}
          {event.days_until !== null && event.days_until !== undefined && event.days_until >= 0 && (
            <div className="bg-slate-900/60 rounded-lg border border-slate-700 p-3">
              <div className="flex items-center justify-between mb-2">
                <span className="text-xs text-slate-400 font-semibold">COUNTDOWN TO {event.catalyst_type}</span>
                <span className={`text-sm font-bold ${event.days_until <= 7 ? 'text-red-400' : event.days_until <= 30 ? 'text-orange-400' : 'text-green-400'}`}>
                  {event.days_until === 0 ? 'TODAY!' : `${event.days_until} days`}
                </span>
              </div>
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
                <div className={`h-full rounded-full transition-all ${
                  event.days_until <= 7 ? 'bg-red-500' : event.days_until <= 30 ? 'bg-orange-500' : 'bg-green-500'
                }`}
                  style={{ width: `${Math.max(5, 100 - (event.days_until / 90 * 100))}%` }}
                />
              </div>
            </div>
          )}

          {/* Approval Probability */}
          {event.approval_probability && (
            <div className={`rounded-lg border p-3 ${
              event.approval_probability.probability >= 85 ? 'bg-green-950/40 border-green-500/30' :
              event.approval_probability.probability >= 60 ? 'bg-yellow-950/40 border-yellow-500/30' :
              event.approval_probability.probability >= 30 ? 'bg-orange-950/40 border-orange-500/30' :
              'bg-red-950/40 border-red-500/30'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Activity size={14} className={
                    event.approval_probability.probability >= 85 ? 'text-green-400' :
                    event.approval_probability.probability >= 60 ? 'text-yellow-400' :
                    event.approval_probability.probability >= 30 ? 'text-orange-400' : 'text-red-400'
                  } />
                  <span className="text-xs font-bold text-slate-300" dir="rtl">הערכת סיכוי לאישור</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-lg font-bold ${
                    event.approval_probability.probability >= 85 ? 'text-green-400' :
                    event.approval_probability.probability >= 60 ? 'text-yellow-300' :
                    event.approval_probability.probability >= 30 ? 'text-orange-400' : 'text-red-400'
                  }`}>{event.approval_probability.probability}%</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                    event.approval_probability.confidence === 'Confirmed' ? 'bg-green-600 text-white' :
                    event.approval_probability.confidence === 'High' ? 'bg-green-900/50 text-green-300' :
                    event.approval_probability.confidence === 'Medium' ? 'bg-yellow-900/50 text-yellow-300' :
                    'bg-slate-700 text-slate-400'
                  }`}>{event.approval_probability.confidence}</span>
                </div>
              </div>
              {/* Progress bar */}
              <div className="h-2 bg-slate-700 rounded-full overflow-hidden mb-2">
                <div className={`h-full rounded-full transition-all ${
                  event.approval_probability.probability >= 85 ? 'bg-green-500' :
                  event.approval_probability.probability >= 60 ? 'bg-yellow-500' :
                  event.approval_probability.probability >= 30 ? 'bg-orange-500' : 'bg-red-500'
                }`}
                  style={{ width: `${event.approval_probability.probability}%` }}
                />
              </div>
              {/* Factors */}
              {event.approval_probability.factors && event.approval_probability.factors.length > 0 && (
                <div className="space-y-0.5">
                  {event.approval_probability.factors.map((factor, idx) => (
                    <div key={idx} className="text-[11px] text-slate-400 flex items-start gap-1.5">
                      <span className="text-slate-600 mt-0.5">&#8226;</span>
                      <span>{factor}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Score Factors */}
          {event.score_factors && event.score_factors.length > 0 && (
            <div className={`rounded-lg border p-3 ${
              score >= 70 ? 'bg-green-950/30 border-green-500/20' :
              score >= 50 ? 'bg-yellow-950/30 border-yellow-500/20' :
              'bg-blue-950/30 border-blue-500/20'
            }`}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <Layers size={14} className={
                    score >= 70 ? 'text-green-400' : score >= 50 ? 'text-yellow-400' : 'text-blue-400'
                  } />
                  <span className="text-xs font-bold text-slate-300" dir="rtl">ציון מסחר — פירוט</span>
                </div>
                <span className={`text-lg font-bold ${
                  score >= 70 ? 'text-green-400' : score >= 50 ? 'text-yellow-300' : 'text-blue-400'
                }`}>{score}/100</span>
              </div>
              <div className="space-y-0.5">
                {event.score_factors.map((factor, idx) => (
                  <div key={idx} className="text-[11px] text-slate-400 flex items-start gap-1.5">
                    <span className={`mt-0.5 ${
                      factor.includes('(-') ? 'text-red-500' : 'text-green-500'
                    }`}>&#8226;</span>
                    <span>{factor}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Chart */}
          {event.ticker && (
            <CandleChart ticker={event.ticker} />
          )}

          {/* Fundamentals */}
          <FundamentalsPanel fundamentals={fundamentals} />

          {/* News */}
          <EventNewsPanel news={event.latest_news} />

          {/* Trial info */}
          {event.trial_title && (
            <div className="bg-slate-900/60 rounded-lg border border-slate-700 p-3">
              <div className="flex items-center gap-2 mb-1">
                <FileText size={14} className="text-blue-400" />
                <span className="text-xs font-bold text-slate-300">Clinical Trial</span>
              </div>
              <p className="text-sm text-slate-300">{event.trial_title}</p>
              {event.nct_id && (
                <a href={event.source_url} target="_blank" rel="noopener noreferrer"
                  className="text-xs text-blue-400 hover:text-blue-300 mt-1 inline-block" dir="ltr">
                  {event.nct_id} →
                </a>
              )}
            </div>
          )}

          {/* Action links */}
          <div className="flex items-center gap-2 flex-wrap">
            <a href={`https://finviz.com/quote.ashx?t=${event.ticker}`} target="_blank" rel="noopener noreferrer"
              className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded text-xs flex items-center gap-1">
              <BarChart3 size={12} /> Finviz
            </a>
            <a href={`https://www.tradingview.com/chart/?symbol=${event.ticker}`} target="_blank" rel="noopener noreferrer"
              className="px-3 py-1 bg-purple-600 hover:bg-purple-700 text-white rounded text-xs flex items-center gap-1">
              <Activity size={12} /> TradingView
            </a>
            <a href={`https://finance.yahoo.com/quote/${event.ticker}`} target="_blank" rel="noopener noreferrer"
              className="px-3 py-1 bg-slate-600 hover:bg-slate-500 text-white rounded text-xs flex items-center gap-1">
              <ExternalLink size={12} /> Yahoo
            </a>
            {event.source_url && (
              <a href={event.source_url} target="_blank" rel="noopener noreferrer"
                className="px-3 py-1 bg-teal-600 hover:bg-teal-700 text-white rounded text-xs flex items-center gap-1">
                <ExternalLink size={12} /> Source
              </a>
            )}
          </div>
        </div>
      )}
    </div>
  );
}


// ─── Calendar View ───────────────────────────────────────

function CatalystCalendarView({ events, onDayClick }) {
  const [currentMonth, setCurrentMonth] = useState(new Date());

  const year = currentMonth.getFullYear();
  const month = currentMonth.getMonth();

  // First day of month and total days
  const firstDay = new Date(year, month, 1).getDay(); // 0=Sun
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;

  // Current week range
  const dayOfWeek = today.getDay();
  const weekStart = new Date(today);
  weekStart.setDate(today.getDate() - dayOfWeek);
  const weekEnd = new Date(today);
  weekEnd.setDate(today.getDate() + (6 - dayOfWeek));

  const isInCurrentWeek = (dayNum) => {
    const d = new Date(year, month, dayNum);
    return d >= weekStart && d <= weekEnd;
  };

  // Group events by date
  const eventsByDate = useMemo(() => {
    const map = {};
    (events || []).forEach(e => {
      const date = e.catalyst_date;
      if (date) {
        if (!map[date]) map[date] = [];
        map[date].push(e);
      }
    });
    return map;
  }, [events]);

  const prevMonth = () => setCurrentMonth(new Date(year, month - 1, 1));
  const nextMonth = () => setCurrentMonth(new Date(year, month + 1, 1));
  const goToday = () => setCurrentMonth(new Date());

  const monthName = currentMonth.toLocaleDateString('en-US', { month: 'long', year: 'numeric' });

  // Build calendar grid cells
  const cells = [];
  for (let i = 0; i < firstDay; i++) {
    cells.push(<div key={`empty-${i}`} className="p-1 min-h-[80px]" />);
  }
  for (let day = 1; day <= daysInMonth; day++) {
    const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
    const dayEvents = eventsByDate[dateStr] || [];
    const isToday = dateStr === todayStr;
    const isThisWeek = isInCurrentWeek(day);

    cells.push(
      <div key={day}
        className={`p-1 min-h-[80px] border rounded cursor-pointer transition-all hover:bg-slate-700/30 ${
          isToday ? 'border-blue-500 bg-blue-900/20' :
          isThisWeek ? 'border-blue-500/30 bg-blue-950/20' :
          dayEvents.length > 0 ? 'border-slate-600 bg-slate-800/50' : 'border-slate-700/30'
        }`}
        onClick={() => dayEvents.length > 0 && onDayClick && onDayClick(dateStr, dayEvents)}
      >
        <div className={`text-xs font-semibold mb-1 ${isToday ? 'text-blue-400' : isThisWeek ? 'text-blue-300' : 'text-slate-400'}`}>
          {day}
        </div>
        <div className="space-y-0.5">
          {dayEvents.slice(0, 3).map((e, i) => {
            const style = getCatalystStyle(e.catalyst_type);
            const prob = e.approval_probability?.probability;
            return (
              <div key={i} className="flex items-center gap-1">
                <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${style.dot}`} />
                <span className="text-[9px] text-slate-300 truncate font-bold">{e.ticker}</span>
                {prob !== undefined && (
                  <span className={`text-[8px] ${prob >= 80 ? 'text-green-500' : prob >= 50 ? 'text-yellow-500' : 'text-orange-500'}`}>
                    {prob}%
                  </span>
                )}
              </div>
            );
          })}
          {dayEvents.length > 3 && (
            <span className="text-[9px] text-slate-500">+{dayEvents.length - 3} more</span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="mb-4">
      {/* Month navigation */}
      <div className="flex items-center justify-between mb-3" dir="ltr">
        <button onClick={prevMonth} className="p-2 hover:bg-slate-700 rounded-lg transition-colors">
          <ChevronLeft size={20} className="text-slate-400" />
        </button>
        <div className="flex items-center gap-3">
          <h3 className="text-lg font-bold text-white">{monthName}</h3>
          <button onClick={goToday} className="px-2 py-1 text-[10px] text-blue-400 hover:bg-blue-900/30 rounded border border-blue-500/30">
            Today
          </button>
        </div>
        <button onClick={nextMonth} className="p-2 hover:bg-slate-700 rounded-lg transition-colors">
          <ChevronRight size={20} className="text-slate-400" />
        </button>
      </div>

      {/* Day headers */}
      <div className="grid grid-cols-7 gap-1 mb-1">
        {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => (
          <div key={d} className="text-center text-[10px] font-bold text-slate-500 py-1">{d}</div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7 gap-1">
        {cells}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-3 flex-wrap">
        {Object.entries(catalystColors).slice(0, 8).map(([type, style]) => (
          <div key={type} className="flex items-center gap-1" title={catalystTypeHebrew[type] || type}>
            <span className={`w-2 h-2 rounded-full ${style.dot}`} />
            <span className="text-[10px] text-slate-500">{type}</span>
            {catalystTypeHebrew[type] && (
              <span className="text-[9px] text-slate-600" dir="rtl">({catalystTypeHebrew[type]})</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}


// ─── Market Cap Parser ────────────────────────────────────

function parseMcapStr(str) {
  if (!str) return 0;
  const s = str.replace(/[$,\s]/g, '');
  const num = parseFloat(s);
  if (isNaN(num)) return 0;
  if (s.endsWith('T')) return num * 1e12;
  if (s.endsWith('B')) return num * 1e9;
  if (s.endsWith('M')) return num * 1e6;
  if (s.endsWith('K')) return num * 1e3;
  return num;
}

// ─── Filters ─────────────────────────────────────────────

function CatalystFilters({ filters, setFilters, eventCount, viewMode, watchlistCount }) {
  return (
    <div className="space-y-3 mb-4">
      {/* Quick filter buttons */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setFilters(f => ({
            ...f,
            timeframe: f.timeframe === '7' ? '90' : '7',
            quickFilter: f.timeframe === '7' ? '' : 'week'
          }))}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
            filters.timeframe === '7' ? 'bg-red-600 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
          }`}>
          <span dir="rtl">השבוע</span>
        </button>
        <button
          onClick={() => setFilters(f => ({
            ...f,
            minProb: f.minProb === 80 ? 0 : 80,
            quickFilter: f.minProb === 80 ? '' : 'highprob'
          }))}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
            filters.minProb === 80 ? 'bg-green-600 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
          }`}>
          <span dir="rtl">סיכוי גבוה (80%+)</span>
        </button>
        {viewMode === 'fda' && (
          <button
            onClick={() => setFilters(f => ({
              ...f,
              catalystType: f.catalystType === 'PDUFA' ? 'all' : 'PDUFA',
              quickFilter: f.catalystType === 'PDUFA' ? '' : 'pdufa'
            }))}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
              filters.catalystType === 'PDUFA' ? 'bg-red-700 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
            }`}>
            PDUFA Only
          </button>
        )}
        <button
          onClick={() => setFilters(f => ({
            ...f,
            watchlistOnly: !f.watchlistOnly,
            quickFilter: !f.watchlistOnly ? 'watchlist' : ''
          }))}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1 ${
            filters.watchlistOnly ? 'bg-yellow-600 text-black' : 'bg-slate-700 text-slate-400 hover:text-white'
          }`}>
          <Star size={12} fill={filters.watchlistOnly ? 'currentColor' : 'none'} />
          Watchlist {watchlistCount > 0 ? `(${watchlistCount})` : ''}
        </button>
        <button
          onClick={() => setFilters(f => ({ ...f, earningsBeat: !f.earningsBeat }))}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
            filters.earningsBeat ? 'bg-emerald-700 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
          }`}>
          📈 Earnings Beat
        </button>
        <button
          onClick={() => setFilters({
            catalystType: 'all', timeframe: '90', sortBy: 'score',
            minScore: 0, minProb: 0, searchTicker: '', watchlistOnly: false, quickFilter: '', marketCap: 'any', earningsBeat: false
          })}
          className="px-3 py-1.5 rounded-lg text-xs font-bold bg-slate-800 text-slate-500 hover:text-white transition-all">
          <X size={12} className="inline" /> Reset
        </button>
      </div>

      {/* Search + Advanced Filters row */}
      <div className="flex items-center gap-3 flex-wrap bg-slate-800/50 border border-slate-700 rounded-lg p-3">
        {/* Ticker search */}
        <div className="relative">
          <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            type="text"
            placeholder="Search ticker..."
            value={filters.searchTicker || ''}
            onChange={e => setFilters(f => ({ ...f, searchTicker: e.target.value.toUpperCase() }))}
            className="pl-7 pr-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded w-32 placeholder-slate-600 focus:border-blue-500 focus:outline-none"
          />
        </div>

        {/* Catalyst type */}
        <select value={filters.catalystType}
          onChange={e => setFilters(f => ({ ...f, catalystType: e.target.value }))}
          className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded">
          <option value="all">All Types</option>
          {viewMode === 'fda' ? (
            <>
              <option value="PDUFA">PDUFA</option>
              <option value="AdCom">Advisory Committee</option>
              <option value="Phase3">Phase 3</option>
              <option value="Phase2">Phase 2</option>
              <option value="NDA">NDA</option>
              <option value="BLA">BLA</option>
              <option value="CRL">CRL</option>
              <option value="Approval">Approval</option>
            </>
          ) : (
            <>
              <option value="Earnings">Earnings</option>
              <option value="Dividend">Dividend</option>
            </>
          )}
        </select>

        {/* Timeframe */}
        <select value={filters.timeframe}
          onChange={e => setFilters(f => ({ ...f, timeframe: e.target.value }))}
          className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded">
          <option value="7">Next 7 days</option>
          <option value="14">Next 14 days</option>
          <option value="30">Next 30 days</option>
          <option value="60">Next 60 days</option>
          <option value="90">Next 90 days</option>
          <option value="180">Next 180 days</option>
          <option value="all">All dates</option>
        </select>

        {/* Sort */}
        <select value={filters.sortBy}
          onChange={e => setFilters(f => ({ ...f, sortBy: e.target.value }))}
          className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded">
          <option value="score">Sort: Score</option>
          <option value="date">Sort: Date (soonest)</option>
          <option value="probability">Sort: Probability</option>
          <option value="market_cap">Sort: Market Cap</option>
          <option value="change">Sort: Change %</option>
        </select>

        {/* Min score */}
        <select value={filters.minScore}
          onChange={e => setFilters(f => ({ ...f, minScore: parseInt(e.target.value) }))}
          className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded">
          <option value={0}>Any Score</option>
          <option value={40}>Score 40+</option>
          <option value={60}>Score 60+</option>
          <option value={80}>Score 80+</option>
        </select>

        {/* Market Cap */}
        <select value={filters.marketCap}
          onChange={e => setFilters(f => ({ ...f, marketCap: e.target.value }))}
          className="px-2 py-1 bg-slate-900 text-white text-xs border border-slate-600 rounded">
          <option value="any">Market Cap: Any</option>
          <option value="mega">Mega ($200B+)</option>
          <option value="large">Large ($10B–$200B)</option>
          <option value="mid">Mid ($2B–$10B)</option>
          <option value="small">Small ($300M–$2B)</option>
          <option value="micro">Micro ($50M–$300M)</option>
          <option value="nano">Nano (under $50M)</option>
          <option disabled>──────────</option>
          <option value="+large">+Large (over $10B)</option>
          <option value="+mid">+Mid (over $2B)</option>
          <option value="+small">+Small (over $300M)</option>
          <option value="+micro">+Micro (over $50M)</option>
          <option disabled>──────────</option>
          <option value="-large">-Large (under $200B)</option>
          <option value="-mid">-Mid (under $10B)</option>
          <option value="-small">-Small (under $2B)</option>
          <option value="-micro">-Micro (under $300M)</option>
        </select>

        <div className="flex-1" />
        <span className="text-xs text-slate-500">{eventCount} events</span>
      </div>
    </div>
  );
}


// ─── Day Detail Modal ────────────────────────────────────

function DayDetailPanel({ date, events, onClose }) {
  if (!events || events.length === 0) return null;

  return (
    <div className="bg-slate-800/80 backdrop-blur-sm border border-slate-600 rounded-lg p-4 mb-4">
      <div className="flex items-center justify-between mb-3">
        <h4 className="text-sm font-bold text-white flex items-center gap-2">
          <Calendar size={16} className="text-blue-400" />
          {formatDate(date)} — {events.length} event{events.length > 1 ? 's' : ''}
        </h4>
        <button onClick={onClose} className="text-slate-400 hover:text-white text-xs px-2 py-1 bg-slate-700 rounded">
          Close
        </button>
      </div>
      <div className="space-y-2">
        {events.map((e, i) => {
          const style = getCatalystStyle(e.catalyst_type);
          const prob = e.approval_probability?.probability;
          return (
            <div key={i} className={`rounded border p-3 ${style.border} bg-slate-900/40`}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-white">{e.ticker}</span>
                  <span className={`px-2 py-0.5 rounded text-[10px] font-bold text-white ${style.bg}`}>{e.catalyst_type}</span>
                  {e.phase && <span className="text-[10px] text-slate-400">{e.phase}</span>}
                </div>
                {prob !== undefined && (
                  <span className={`text-sm font-bold ${
                    prob >= 80 ? 'text-green-400' : prob >= 50 ? 'text-yellow-400' : 'text-orange-400'
                  }`}>{prob}%</span>
                )}
              </div>
              {e.drug_name && <div className="text-xs text-slate-300 mt-1">{e.drug_name}</div>}
              {e.indication && <div className="text-xs text-slate-400">{e.indication}</div>}
              {e.company && <div className="text-xs text-slate-500 mt-1">{e.company}</div>}
              {getHebrewDescription(e) && (
                <div className="text-[10px] text-amber-400/70 mt-1" dir="rtl">{getHebrewDescription(e)}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}


// ─── Export Button ────────────────────────────────────────

function ExportButton({ events }) {
  const [copied, setCopied] = useState(false);

  const handleExport = useCallback(() => {
    if (!events || events.length === 0) return;

    const header = 'Ticker\tDate\tType\tDrug\tIndication\tCompany\tProb%\tScore\tDays';
    const rows = events.map(e => [
      e.ticker,
      e.catalyst_date || 'TBD',
      e.catalyst_type,
      e.drug_name || '',
      e.indication || '',
      e.company || '',
      e.approval_probability?.probability ?? '',
      e.catalyst_score || '',
      e.days_until ?? '',
    ].join('\t'));

    const text = [header, ...rows].join('\n');
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [events]);

  return (
    <button
      onClick={handleExport}
      className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
        copied ? 'bg-green-600 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
      }`}
      title="Copy to clipboard (TSV format - paste into Excel/Sheets)"
    >
      {copied ? <Check size={14} /> : <Copy size={14} />}
      {copied ? 'Copied!' : 'Export'}
    </button>
  );
}


// ─── Main Component ──────────────────────────────────────

export default function FDACatalystTracker({ events, loading, viewMode = 'fda' }) {
  const [displayMode, setDisplayMode] = useState('table'); // 'table', 'calendar', or 'movers'
  const [filters, setFilters] = useState({
    catalystType: 'all',
    timeframe: '90',
    sortBy: 'score',
    minScore: 0,
    minProb: 0,
    searchTicker: '',
    watchlistOnly: false,
    quickFilter: '',
    marketCap: 'any',
    earningsBeat: false,
  });
  const [selectedDay, setSelectedDay] = useState(null);
  const [selectedDayEvents, setSelectedDayEvents] = useState([]);
  const [watchlist, setWatchlist] = useState(getWatchlist);

  // FDA Movers state
  const [movers, setMovers] = useState([]);
  const [moversLoading, setMoversLoading] = useState(false);
  const moversLoadedRef = useRef(false);

  // Today's + Yesterday's Biotech Movers state
  const [biotechData, setBiotechData] = useState({ today: { movers: [], session_date: '' }, yesterday: { movers: [], session_date: '' } });
  const [biotechLoading, setBiotechLoading] = useState(false);
  const biotechLoadedRef = useRef(false);

  // Fetch movers when tab is selected
  useEffect(() => {
    if (displayMode === 'movers' && !moversLoadedRef.current && viewMode === 'fda') {
      moversLoadedRef.current = true;
      setMoversLoading(true);
      fetch('/api/catalyst/fda-movers?days_back=30')
        .then(r => r.json())
        .then(data => {
          setMovers(data.movers || []);
          setMoversLoading(false);
        })
        .catch(() => setMoversLoading(false));
    }
  }, [displayMode, viewMode]);

  // Fetch today's + yesterday's biotech movers when tab is selected
  useEffect(() => {
    if (displayMode === 'today' && !biotechLoadedRef.current && viewMode === 'fda') {
      biotechLoadedRef.current = true;
      setBiotechLoading(true);
      fetch('/api/catalyst/biotech-movers-today')
        .then(r => r.json())
        .then(data => {
          setBiotechData({
            today: data.today || { movers: data.movers || [], session_date: '' },
            yesterday: data.yesterday || { movers: [], session_date: '' },
          });
          setBiotechLoading(false);
        })
        .catch(() => setBiotechLoading(false));
    }
  }, [displayMode, viewMode]);

  const handleToggleWatchlist = useCallback((ticker) => {
    const newList = toggleWatchlist(ticker);
    setWatchlist([...newList]);
  }, []);

  // Count watchlisted events
  const watchlistCount = useMemo(() => {
    return (events || []).filter(e => watchlist.includes(e.ticker)).length;
  }, [events, watchlist]);

  // Apply filters
  const filteredEvents = useMemo(() => {
    let result = [...(events || [])];

    // Ticker search
    if (filters.searchTicker) {
      result = result.filter(e =>
        e.ticker?.includes(filters.searchTicker) ||
        (e.company || '').toUpperCase().includes(filters.searchTicker) ||
        (e.drug_name || '').toUpperCase().includes(filters.searchTicker)
      );
    }

    // Watchlist filter
    if (filters.watchlistOnly) {
      result = result.filter(e => watchlist.includes(e.ticker));
    }

    // Catalyst type filter
    if (filters.catalystType !== 'all') {
      result = result.filter(e => e.catalyst_type === filters.catalystType);
    }

    // Timeframe filter
    if (filters.timeframe !== 'all') {
      const maxDays = parseInt(filters.timeframe);
      result = result.filter(e => {
        const days = e.days_until;
        if (days === null || days === undefined) return true;
        return days >= -7 && days <= maxDays;
      });
    }

    // Min score filter
    if (filters.minScore > 0) {
      result = result.filter(e => (e.catalyst_score || 0) >= filters.minScore);
    }

    // Min probability filter
    if (filters.minProb > 0) {
      result = result.filter(e => (e.approval_probability?.probability || 0) >= filters.minProb);
    }

    // Market Cap filter
    if (filters.marketCap !== 'any') {
      const mc = e => parseMcapStr(e.fundamentals?.market_cap);
      if      (filters.marketCap === 'mega')    result = result.filter(e => mc(e) >= 200e9);
      else if (filters.marketCap === 'large')   result = result.filter(e => mc(e) >= 10e9  && mc(e) < 200e9);
      else if (filters.marketCap === 'mid')     result = result.filter(e => mc(e) >= 2e9   && mc(e) < 10e9);
      else if (filters.marketCap === 'small')   result = result.filter(e => mc(e) >= 300e6 && mc(e) < 2e9);
      else if (filters.marketCap === 'micro')   result = result.filter(e => mc(e) >= 50e6  && mc(e) < 300e6);
      else if (filters.marketCap === 'nano')    result = result.filter(e => mc(e) > 0      && mc(e) < 50e6);
      else if (filters.marketCap === '+large')  result = result.filter(e => mc(e) >= 10e9);
      else if (filters.marketCap === '+mid')    result = result.filter(e => mc(e) >= 2e9);
      else if (filters.marketCap === '+small')  result = result.filter(e => mc(e) >= 300e6);
      else if (filters.marketCap === '+micro')  result = result.filter(e => mc(e) >= 50e6);
      else if (filters.marketCap === '-large')  result = result.filter(e => mc(e) < 200e9);
      else if (filters.marketCap === '-mid')    result = result.filter(e => mc(e) < 10e9);
      else if (filters.marketCap === '-small')  result = result.filter(e => mc(e) < 2e9);
      else if (filters.marketCap === '-micro')  result = result.filter(e => mc(e) < 300e6);
    }

    // Earnings Beat filter — eps_qq > 5% (recent strong quarter)
    if (filters.earningsBeat) {
      result = result.filter(e => {
        const epsQQ = parseFloat(e.fundamentals?.eps_qq || '0');
        return epsQQ > 5;
      });
    }

    // Sort
    switch (filters.sortBy) {
      case 'date':
        result.sort((a, b) => {
          const aDays = a.days_until ?? 9999;
          const bDays = b.days_until ?? 9999;
          return aDays - bDays;
        });
        break;
      case 'probability':
        result.sort((a, b) => {
          const aProb = a.approval_probability?.probability || 0;
          const bProb = b.approval_probability?.probability || 0;
          return bProb - aProb;
        });
        break;
      case 'market_cap':
        result.sort((a, b) => {
          const aMcap = a.fundamentals?.market_cap || '';
          const bMcap = b.fundamentals?.market_cap || '';
          return bMcap.localeCompare(aMcap);
        });
        break;
      case 'change':
        result.sort((a, b) => {
          const aChg = Math.abs(parseFloat(a.fundamentals?.change_pct || '0'));
          const bChg = Math.abs(parseFloat(b.fundamentals?.change_pct || '0'));
          return bChg - aChg;
        });
        break;
      default: // score
        result.sort((a, b) => (b.catalyst_score || 0) - (a.catalyst_score || 0));
    }

    return result;
  }, [events, filters, watchlist]);

  const handleDayClick = (date, dayEvents) => {
    setSelectedDay(date);
    setSelectedDayEvents(dayEvents);
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-12 gap-3">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-green-500"></div>
        <span className="text-slate-400 text-sm" dir="rtl">
          {viewMode === 'fda' ? 'סורק לוחות שנה של FDA ומעשיר עם נתוני Finviz...' : 'סורק לוחות שנה של דוחות טכנולוגיה...'}
        </span>
        <span className="text-slate-500 text-xs">
          {viewMode === 'fda' ? 'BioPharmCatalyst | RTTNews | Drugs.com | ClinicalTrials.gov | CheckRare | FDATracker' : 'Yahoo Finance | yfinance'}
        </span>
      </div>
    );
  }

  if (!events || events.length === 0) {
    return (
      <div className="text-center py-12 text-slate-400">
        <Target size={48} className="mx-auto mb-4 opacity-50" />
        <p dir="rtl">{viewMode === 'fda' ? 'לא נמצאו אירועי FDA' : 'לא נמצאו אירועי קטליסט טכנולוגי'}</p>
        <p className="text-sm mt-2 text-slate-500" dir="rtl">המידע נאסף ממספר מקורות. נסה לרענן.</p>
      </div>
    );
  }

  return (
    <div>
      {/* Stats Header */}
      <StatsHeader events={events} viewMode={viewMode} />

      {/* This Week Banner */}
      <ThisWeekBanner events={events} />

      {/* View mode toggle + Export */}
      <div className="flex items-center gap-2 mb-4">
        <button
          onClick={() => setDisplayMode('table')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
            displayMode === 'table' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
          }`}>
          <Table2 size={14} /> Table
        </button>
        <button
          onClick={() => setDisplayMode('calendar')}
          className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
            displayMode === 'calendar' ? 'bg-blue-600 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
          }`}>
          <Calendar size={14} /> Calendar
        </button>
        {viewMode === 'fda' && (
          <>
            <button
              onClick={() => setDisplayMode('today')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                displayMode === 'today' ? 'bg-green-600 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
              }`}>
              <Activity size={14} />
              <span dir="rtl">זינוקים היום</span>
            </button>
            <button
              onClick={() => setDisplayMode('movers')}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold flex items-center gap-1.5 transition-all ${
                displayMode === 'movers' ? 'bg-orange-600 text-white' : 'bg-slate-700 text-slate-400 hover:text-white'
              }`}>
              <Flame size={14} />
              <span dir="rtl">מעקב תנועות</span>
            </button>
          </>
        )}

        <ExportButton events={filteredEvents} />

        <div className="flex-1" />

        {/* Stats badges */}
        <div className="flex items-center gap-3">
          {viewMode === 'fda' && (
            <>
              <span className="text-xs text-slate-500">
                PDUFA: <span className="text-red-400 font-bold">{events.filter(e => e.catalyst_type === 'PDUFA').length}</span>
              </span>
              <span className="text-xs text-slate-500">
                Phase 3: <span className="text-blue-400 font-bold">{events.filter(e => e.catalyst_type === 'Phase3').length}</span>
              </span>
            </>
          )}
          <span className="text-xs text-slate-500">
            Next 7d: <span className="text-orange-400 font-bold">
              {events.filter(e => e.days_until !== null && e.days_until >= 0 && e.days_until <= 7).length}
            </span>
          </span>
        </div>
      </div>

      {/* Filters */}
      <CatalystFilters
        filters={filters}
        setFilters={setFilters}
        eventCount={filteredEvents.length}
        viewMode={viewMode}
        watchlistCount={watchlistCount}
      />

      {/* Calendar view */}
      {displayMode === 'calendar' && (
        <>
          <CatalystCalendarView events={filteredEvents} onDayClick={handleDayClick} />
          {selectedDay && (
            <DayDetailPanel
              date={selectedDay}
              events={selectedDayEvents}
              onClose={() => { setSelectedDay(null); setSelectedDayEvents([]); }}
            />
          )}
        </>
      )}

      {/* Today's Biotech Movers view */}
      {displayMode === 'today' && viewMode === 'fda' && (
        <TodaysBiotechMovers data={biotechData} loading={biotechLoading} />
      )}

      {/* Historical Movers view */}
      {displayMode === 'movers' && viewMode === 'fda' && (
        <FDAMoversSection movers={movers} loading={moversLoading} />
      )}

      {/* Table view */}
      {displayMode !== 'movers' && displayMode !== 'today' && (
        <div className="space-y-3">
          {filteredEvents.map((event, idx) => (
            <CatalystEventCard
              key={`${event.ticker}-${event.catalyst_date}-${idx}`}
              event={event}
              rank={idx + 1}
              viewMode={viewMode}
              isWatchlisted={watchlist.includes(event.ticker)}
              onToggleWatchlist={handleToggleWatchlist}
            />
          ))}
        </div>
      )}

      {/* Footer - data sources */}
      {filteredEvents.length > 0 && (
        <div className="mt-4 text-center text-[10px] text-slate-600" dir="rtl">
          מקורות: BioPharmCatalyst | RTTNews | Drugs.com | ClinicalTrials.gov | CheckRare | FDATracker
        </div>
      )}
    </div>
  );
}
