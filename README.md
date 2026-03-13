# Stock Scanner — Strategy Arena

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

פלטפורמת מסחר אוטונומית בזמן אמת — **8 אסטרטגיות מתחרות** בארנה, מחוברות ל-Interactive Brokers, עם Telegram reports ו-EOD auto-replace.

**FastAPI + React + IB Gateway**

---

## 🏆 Strategy Arena

הלב של הפרויקט. 8 מיני-תיקים ($1,000 כל אחד) רצים אוטונומית ומתחרים מי מרוויח יותר.

**כל 10 שניות:**
1. רענון נתוני Finviz (TTL=18s)
2. מחירים חיים מ-yfinance לכל הפוזיציות הפתוחות
3. כל 8 האסטרטגיות מריצות לוגיקת כניסה/יציאה
4. IB Gateway מבצע עסקאות בחשבון demo אוטומטית

### 8 האסטרטגיות

| אסטרטגיה | רעיון | Stop | Target | מה מיוחד |
|---|---|---|---|---|
| ⚖️ **Balanced** | health > 30, מומנטום בסיסי | 6% | 18% | ברירת מחדל, שוק רגיל |
| 🎯 **High Conviction** | health > 45, confidence > 48 | 5% | 25% | מעט עסקאות, R:R גבוה |
| ⚡ **Scalper** | כניסה לכל מה שזזה, 3 פוז׳ | 6% | 20% | partial TP 10%, trailing 0.95 |
| 🚀 **Momentum Breaker** | נפח 1.5x + תנועה 0.8% | 5% | 16% | אישור נפח חזק |
| 🔥 **Hard Squeeze** | short float ≥ 20%, Small Cap, rvol 1.5x | 8% | 40% | לוחץ שורטסטים |
| ⚡ **Lightning Squeeze** | float < 50M, gap up, short ≥ 10%, rvol 2x | 8% | 35% | partial TP 10%, trailing 0.93 |
| 🌪️ **Gap & Squeeze** | float < 30M, gap up, short ≥ 20%, rvol 5x, price < $20 | 10% | 60% | הכי אגרסיבי |
| 💥 **Nano Squeeze** | short ≥ 15%, Small Cap, rvol 2x | 10% | 50% | לוטרי |

### Exit Logic (ברירות מחדל)

| פרמטר | ערך | הסבר |
|---|---|---|
| `partial_tp_trigger` | **12%** | מוכר 40% מהפוזיציה ב-+12% |
| `trailing_trigger` | **8%** | מפעיל trailing stop ב-+8% |
| `trail_pct` | **0.91** | trailing ב-91% מהשיא — 9% מרווח |
| Stale exit | 2 ימים | סוגר אם מוחזק 2+ ימים עם < 2% רווח |

### מקורות מניות

| מקור | תדירות | לאיזה אסטרטגיה |
|---|---|---|
| Finviz Momentum Scanner | כל 18 שניות | כולן |
| Finviz SmallCap `sh_short_o20` | כל 2 דקות | Hard / Gap / Nano Squeeze |
| Finviz SmallCap `sh_short_o10` | כל 2 דקות | Lightning Squeeze |

### EOD Auto-Replace (16:15 ET)

כל יום ב-16:15 ET אסטרטגיות עם P&L שלילי מוחלפות אוטומטית ב-clone של המנצח היומי.
פוזיציות ברווח **לא נסגרות** — רק מפסידות.

---

## 🏦 IB Gateway Integration

- Port 4002 (paper trading), account: `DU3788776`
- עוקב אחרי האסטרטגיה המובילה (`__auto__` mode)
- Telegram report כל 2 שעות: leaderboard + positions + suggestions
- Auto-reconnect כל 60 שניות

---

## 📱 Frontend — Tabs

| Tab | תפקיד |
|---|---|
| 🏆 **ארנה** | לוח תוצאות — 8 אסטרטגיות, פוזיציות, עסקאות, events |
| 📈 **סיגנלים** | MACD + RSI + Bollinger Bands scanner |
| 🎯 **ניתוח יומי** | composite score 0–100, entry/stop/target |
| 🏦 **IB חשבון** | פוזיציות ו-P&L חשבון IB בזמן אמת |
| 🤖 **Pattern Bot** | pattern recognition scanner |
| 📅 **עונתיות** | seasonality signals |
| 📋 **סורק בסיסי** | Finviz screener |

**ArenaIBWidget** (בheader) — LIVE/OFFLINE + אסטרטגיה פעילה + P&L + פוזיציות. מתרענן כל 30s.

---

## 🚀 Quick Start

```bash
# Backend
cd backend && source venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (nvm — snap node is broken)
export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh"
cd frontend && npx vite --host 0.0.0.0
```

---

## 🏗️ Architecture

```
stock-scanner-app/
├── backend/
│   └── app/
│       ├── main.py                    # Scheduler: arena tick 10s, EOD, watchdog
│       ├── services/
│       │   ├── strategy_arena.py      # 8 strategies, MiniPortfolio, exit logic
│       │   └── arena_ib_trader.py     # IB Gateway + Telegram reports
│       ├── api/
│       │   └── routes.py              # All endpoints + Finviz cache layers
│       └── scrapers/
│           └── finviz_screener.py     # Finviz Elite scraper
├── frontend/
│   └── src/
│       ├── AppMomentum.jsx            # Main app — tabs + ArenaIBWidget header
│       └── components/
│           └── StrategyArena.jsx      # Arena leaderboard UI
└── backend/data/
    ├── strategy_arena.json            # Arena state (positions, trades, tick count)
    └── arena_ib_trader.json           # IB trader state
```

| Layer | Tech |
|---|---|
| Backend | Python 3.12 · FastAPI · APScheduler |
| Frontend | React 18 · Vite · TanStack Query |
| Broker | Interactive Brokers (ib_insync) |
| Data | Finviz Elite · yfinance |
| Notifications | Telegram Bot API |

---

## ⚙️ Scheduler Jobs

| Job | תדירות | מה עושה |
|---|---|---|
| `arena_tick_job` | **כל 10 שניות** | Finviz + live prices + think() + IB |
| `smallcap_squeeze_job` | כל 2 דקות | מרענן SmallCap cache |
| `arena_eod_job` | כל דקה (15:45–16:09 ET) | winner יומי |
| `eod_replace_job` | כל דקה (16:15–16:19 ET) | מחליף אסטרטגיות מפסידות |
| `arena_report_job` | כל 2 שעות | Telegram leaderboard |
| `ib_reconnect_job` | כל 60 שניות | auto-reconnect IB |
| `watchdog_job` | כל 5 דקות | self-healing |

---

## 📊 API Endpoints

| Endpoint | Description |
|---|---|
| `POST /api/smart-portfolio/arena/think` | Arena tick — run all strategies |
| `GET /api/smart-portfolio/arena/status` | Leaderboard + positions + events |
| `POST /api/smart-portfolio/arena/declare-daily-winner` | EOD winner |
| `POST /api/smart-portfolio/arena/force-reset/{name}` | Force-close strategy positions |
| `GET /api/ib/arena-trader/status` | IB connection + active strategy |
| `GET /api/screener/finviz-table` | Finviz momentum scan (cache 18s) |
| `GET /api/screener/live-prices` | yfinance live prices by tickers |
| `GET /api/signals/technical` | MACD + RSI + BB scanner |
| `GET /api/analysis/daily` | Daily composite score 0–100 |

---

## ⚠️ Disclaimer

For educational and informational purposes only. Not financial advice.

---

*🇮🇱 פרויקט מסחר אוטונומי — ארנה של 8 אסטרטגיות מתחרות בזמן אמת*
