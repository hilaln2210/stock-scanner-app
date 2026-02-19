import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

const resources = {
  en: {
    translation: {
      // Header
      'app.title': 'Stock Scanner',
      'app.subtitle': 'Real-time market signals & news',
      'button.enableAlerts': 'Enable Alerts',
      'button.notificationsOn': 'Notifications ON',
      'button.triggerScrape': 'Trigger Scrape',
      'button.refresh': 'Refresh',

      // Stats
      'stats.totalSignals': 'Total Signals',
      'stats.bullish': 'Bullish',
      'stats.bearish': 'Bearish',
      'stats.avgScore': 'Avg Score',

      // Filters
      'filter.searchTicker': 'Search Ticker',
      'filter.minScore': 'Min Score',
      'filter.stance': 'Stance',
      'filter.all': 'All',
      'filter.autoRefresh': 'Auto Refresh',
      'filter.off': 'Off',

      // Signals
      'signals.title': 'Signals',
      'signals.found': 'signals found',
      'signals.loading': 'Loading...',
      'signals.ticker': 'Ticker',
      'signals.signalType': 'Signal Type',
      'signals.score': 'Score',
      'signals.stance': 'Stance',
      'signals.time': 'Time',
      'signals.reason': 'Reason',

      // News
      'news.title': 'Recent News',
      'news.articles': 'articles',
      'news.sentiment': 'Sentiment',

      // Top Movers
      'movers.title': 'Top Movers Today',
      'movers.change': 'Change',
      'movers.volume': 'Volume',
      'movers.price': 'Price',

      // Modal
      'modal.viewDetails': 'View Details',
      'modal.close': 'Close',

      // Time
      'time.minutesAgo': 'm ago',
      'time.hoursAgo': 'h ago',

      // Catalysts
      'catalyst.fda': 'FDA Catalysts',
      'catalyst.tech': 'Tech Catalysts',
      'catalyst.pdufa': 'PDUFA Date',
      'catalyst.adcom': 'Advisory Committee',
      'catalyst.daysUntil': 'days until',
      'catalyst.phase': 'Phase',
      'catalyst.drug': 'Drug',
      'catalyst.indication': 'Indication',
      'catalyst.viewCalendar': 'Calendar View',
      'catalyst.viewTable': 'Table View',
      'catalyst.score': 'Catalyst Score',
      'catalyst.fundamentals': 'Fundamentals',
    }
  },
  he: {
    translation: {
      // Header
      'app.title': 'סורק מניות',
      'app.subtitle': 'סיגנלים וחדשות בזמן אמת',
      'button.enableAlerts': 'הפעל התראות',
      'button.notificationsOn': 'התראות פעילות',
      'button.triggerScrape': 'רענן נתונים',
      'button.refresh': 'רענן',

      // Stats
      'stats.totalSignals': 'סך סיגנלים',
      'stats.bullish': 'עליה',
      'stats.bearish': 'ירידה',
      'stats.avgScore': 'ציון ממוצע',

      // Filters
      'filter.searchTicker': 'חפש מניה',
      'filter.minScore': 'ציון מינימלי',
      'filter.stance': 'כיוון',
      'filter.all': 'הכל',
      'filter.autoRefresh': 'רענון אוטומטי',
      'filter.off': 'כבוי',

      // Signals
      'signals.title': 'סיגנלים',
      'signals.found': 'סיגנלים נמצאו',
      'signals.loading': 'טוען...',
      'signals.ticker': 'סימול',
      'signals.signalType': 'סוג סיגנל',
      'signals.score': 'ציון',
      'signals.stance': 'כיוון',
      'signals.time': 'זמן',
      'signals.reason': 'סיבה',

      // News
      'news.title': 'חדשות אחרונות',
      'news.articles': 'כתבות',
      'news.sentiment': 'סנטימנט',

      // Top Movers
      'movers.title': 'מניות חמות היום',
      'movers.change': 'שינוי',
      'movers.volume': 'נפח',
      'movers.price': 'מחיר',

      // Modal
      'modal.viewDetails': 'צפה בפרטים',
      'modal.close': 'סגור',

      // Time
      'time.minutesAgo': 'דקות',
      'time.hoursAgo': 'שעות',

      // Catalysts
      'catalyst.fda': 'קטליסטים FDA',
      'catalyst.tech': 'קטליסטים טכנולוגיה',
      'catalyst.pdufa': 'תאריך PDUFA',
      'catalyst.adcom': 'ועדה מייעצת',
      'catalyst.daysUntil': 'ימים עד',
      'catalyst.phase': 'שלב',
      'catalyst.drug': 'תרופה',
      'catalyst.indication': 'אינדיקציה',
      'catalyst.viewCalendar': 'תצוגת לוח שנה',
      'catalyst.viewTable': 'תצוגת טבלה',
      'catalyst.score': 'ציון קטליסט',
      'catalyst.fundamentals': 'נתונים פונדמנטליים',
    }
  }
};

i18n
  .use(initReactI18next)
  .init({
    resources,
    lng: 'en', // default language
    fallbackLng: 'en',
    interpolation: {
      escapeValue: false
    }
  });

export default i18n;
