# Stock Scanner Dashboard

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A real-time stock market intelligence platform built with **FastAPI** + **React**. Combines technical analysis, FDA catalyst tracking, social trending data, and AI-assisted briefings into a single Hebrew/English dashboard.

**📱 זמין לנייד כ־PWA · 🚀 ניתן לפריסה 24/7** – ראה [DEPLOY.md](DEPLOY.md)

---

## Screenshots

### ☀️ Daily Briefing
Morning digest — top movers, sector heatmap, market status, live news feed.

![Daily Briefing](screenshots/briefing.png)

---

### 💊 FDA Catalyst Tracker
Tracks upcoming PDUFA dates, NDA/BLA submissions, and Phase 3 trial results. Enriched with RSI, short interest, institutional ownership, and approval probability.

![FDA Catalyst Tracker](screenshots/fda.png)

---

### 🎯 Daily Analysis — Composite Score
Scans 79+ stocks with MACD + RSI + MA deviation. Scores each stock 0–100 with entry/stop/target levels.

![Daily Analysis](screenshots/daily-analysis.png)

---

### 📈 Technical Signals
MACD crossover + RSI + Bollinger Bands scanner. Filters by sector and signal strength.

![Technical Signals](screenshots/tech-signals.png)

---

### 🔥 Trending Stocks
Social sentiment scanner — most discussed tickers across Reddit, StockTwits, and financial media.

![Trending Stocks](screenshots/trending.png)

---

### 📋 Basic Scanner (Finviz)
Finviz-powered fundamental screener with custom filters.

![Basic Scanner](screenshots/finviz-table.png)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11 · FastAPI · uvicorn |
| Frontend | React 18 · Vite · TailwindCSS · TanStack Query |
| Data | yfinance · Finviz · ClinicalTrials.gov · FDA sources |
| Broker | Interactive Brokers (IB Gateway) |
| Cache | In-memory (per-ticker 120s · full scan 90s · API 60s) |

---

## Tabs

| Tab | Description |
|-----|-------------|
| ☀️ בריפינג | Daily morning briefing — top 5 stocks by earnings beat + RSI |
| 💼 תיק דמו | Demo portfolio tracker |
| 🔥 הכי מדוברות | Social trending stocks |
| 💊 FDA | FDA catalyst calendar — PDUFA dates, NDA/BLA, Phase 3 |
| 🖥️ קטליסטים | Tech catalyst tracker (earnings events) |
| 📈 סיגנלים | Technical signals — MACD + RSI + Bollinger Bands |
| 🎯 ניתוח יומי | Daily composite analysis — score 0–100, entry/stop/target |
| 🏦 IB חשבון | Interactive Brokers live account / positions |
| 📋 סורק בסיסי | Finviz fundamental screener |

---

## Running Locally

### Backend
```bash
cd backend
source venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend
```bash
# Requires Node via nvm
export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh"
cd frontend
npx vite --host 0.0.0.0
```

- Frontend: http://localhost:3000
- API docs: http://localhost:8000/docs

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/briefing/daily` | Daily briefing (3h cache) |
| `GET /api/catalyst/fda` | FDA catalyst calendar |
| `GET /api/catalyst/tech` | Tech catalyst calendar |
| `GET /api/signals/technical` | Technical signals (MACD+RSI+BB) |
| `GET /api/analysis/daily` | Daily composite analysis |
| `GET /api/trending/social` | Social trending stocks |
| `GET /api/screener/vwap-momentum` | VWAP momentum screener |
| `GET /api/momentum/scanner` | Momentum scanner |

---

## FDA Data Sources

Data aggregated from 6 sources:
**BioPharmCatalyst** · **RTTNews** · **Drugs.com** · **ClinicalTrials.gov** · **CheckRare** · **FDATracker**

---

## Disclaimer

For educational and informational purposes only. Not financial advice.

---

## 🇮🇱 תיעוד בעברית

### מה הפרויקט עושה

פלטפורמת מודיעין שוק מניות בזמן אמת, המשלבת ניתוח טכני, מעקב אחר קטליסטים (FDA, רווחים), נתוני סנטימנט חברתי ובריפינג בוקר יומי — הכול בממשק אחד.

האפליקציה מיועדת לטריידרים פעילים ומאפשרת סריקת מניות, זיהוי הזדמנויות מסחר, ומעקב אחר אירועים קטליטיים חשובים.

**טאבים ראשיים בממשק:**
- **☀️ בריפינג יומי** — סיכום בוקר: 5 המניות המובילות לפי ביצועי רווחים + RSI
- **🔥 הכי מדוברות** — מניות טרנדיות ברשתות חברתיות (Reddit, StockTwits)
- **💊 FDA** — לוח קטליסטים של FDA: תאריכי PDUFA, הגשות NDA/BLA, תוצאות ניסויי שלב 3
- **📈 סיגנלים טכניים** — סריקת MACD + RSI + Bollinger Bands
- **🎯 ניתוח יומי** — ניקוד 0–100 לכל מניה עם רמות כניסה/עצירה/מטרה
- **🏦 חשבון IB** — חיבור ל-Interactive Brokers לצפייה בפוזיציות בזמן אמת

### טכנולוגיות

| שכבה | טכנולוגיה |
|------|-----------|
| Backend | Python 3.11, FastAPI, uvicorn |
| Frontend | React 18, Vite, TailwindCSS, TanStack Query |
| נתוני שוק | yfinance, Finviz, ClinicalTrials.gov, מקורות FDA |
| ברוקר | Interactive Brokers (IB Gateway) |
| Cache | זיכרון פנימי (per-ticker 120s, סריקה מלאה 90s, API 60s) |

### הוראות התקנה והפעלה

**הרצת ה-Backend:**

```bash
cd backend
source venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

**הרצת ה-Frontend:**

```bash
# דרוש Node דרך nvm
export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh"
cd frontend
npx vite --host 0.0.0.0
```

- ממשק משתמש: `http://localhost:3000`
- תיעוד API: `http://localhost:8000/docs`

### מבנה הפרויקט

```
stock-scanner-app/
├── backend/
│   └── app/
│       ├── main.py           # נקודת כניסה FastAPI + כל ה-endpoints
│       ├── momentum/         # סורק מומנטום
│       ├── screener/         # סורק VWAP
│       ├── catalyst/         # FDA וקטליסטים טכנולוגיים
│       ├── signals/          # סיגנלים טכניים (MACD+RSI+BB)
│       ├── analysis/         # ניתוח יומי מרוכב
│       ├── trending/         # מגמות חברתיות
│       └── briefing/         # בריפינג בוקר
└── frontend/
    └── src/
        ├── components/       # רכיבי React לכל טאב
        └── App.jsx           # ניתוב ראשי בין הטאבים
```

**מקורות נתוני FDA (6 מקורות):**
BioPharmCatalyst, RTTNews, Drugs.com, ClinicalTrials.gov, CheckRare, FDATracker
