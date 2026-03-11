# Stock Scanner Dashboard

[![CI](https://github.com/hilaln2210/stock-scanner-app/actions/workflows/ci.yml/badge.svg)](https://github.com/hilaln2210/stock-scanner-app/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A real-time stock market intelligence platform built with **FastAPI** + **React**. Combines technical analysis, FDA catalyst tracking, social trending data, and AI-assisted briefings into a single dashboard.

**📱 Available as PWA · 🚀 Deployable 24/7** — see [DEPLOY.md](DEPLOY.md)

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
| ☀️ Briefing | Daily morning briefing — top 5 stocks by earnings beat + RSI |
| 💼 Demo Portfolio | Demo portfolio tracker |
| 🔥 Trending | Social trending stocks |
| 💊 FDA | FDA catalyst calendar — PDUFA dates, NDA/BLA, Phase 3 |
| 🖥️ Catalysts | Tech catalyst tracker (earnings events) |
| 📈 Signals | Technical signals — MACD + RSI + Bollinger Bands |
| 🎯 Daily Analysis | Daily composite analysis — score 0–100, entry/stop/target |
| 🏦 IB Account | Interactive Brokers live account / positions |
| 📋 Basic Scanner | Finviz fundamental screener |

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

## Project Structure

```
stock-scanner-app/
├── backend/
│   └── app/
│       ├── main.py           # FastAPI entry point + all endpoints
│       ├── momentum/         # Momentum scanner
│       ├── screener/         # VWAP screener
│       ├── catalyst/         # FDA and tech catalysts
│       ├── signals/          # Technical signals (MACD+RSI+BB)
│       ├── analysis/         # Daily composite analysis
│       ├── trending/         # Social trending
│       └── briefing/         # Morning briefing
└── frontend/
    └── src/
        ├── components/       # React components per tab
        └── App.jsx           # Main tab routing
```

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

## 🇮🇱 בעברית

פלטפורמת מודיעין שוק מניות בזמן אמת — סורק מומנטום, VWAP, קטליסטים FDA, מגמות חברתיות ובריפינג בוקר מבוסס AI. FastAPI + React.
