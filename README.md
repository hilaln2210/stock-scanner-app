# Stock Scanner — Strategy Arena

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

פלטפורמת מסחר אוטונומית בזמן אמת — **8 אסטרטגיות מתחרות בארנה**, מחוברות ל-Interactive Brokers, עם Telegram reports ו-EOD auto-replace.

**FastAPI + React + IB Gateway · 78 API endpoints · 25 services · 17 scrapers**

---

## 🏆 Strategy Arena

הלב של הפרויקט. 8 מיני-תיקים ($1,000 כל אחד) רצים אוטונומית ומתחרים מי מרוויח יותר.

**כל 10 שניות:**
1. רענון Finviz momentum scan (TTL=18s)
2. מחירים חיים מ-yfinance לכל הפוזיציות הפתוחות
3. SmallCap squeeze cache ממוזג לרשימת המניות
4. כל 8 האסטרטגיות מריצות לוגיקת כניסה/יציאה
5. IB Gateway מבצע עסקאות בחשבון demo אוטומטית

### 8 האסטרטגיות

| אסטרטגיה | Python key | רעיון | Stop | Target | מה מיוחד |
|---|---|---|---|---|---|
| ⚖️ **Balanced** | `Balanced` | health > 30, מומנטום בסיסי | 6% | 18% | ברירת מחדל, כל שוק |
| 🎯 **High Conviction** | `HighConviction` | health > 45, confidence > 48 | 5% | 25% | מעט עסקאות, R:R גבוה |
| ⚡ **Scalper** | `Scalper` | נכנס לכל מה שזזה, 3 פוז׳ | 6% | 20% | partial TP 10%, trail 0.95 |
| 🚀 **Momentum Breaker** | `MomentumBreaker` | rvol ≥ 1.5x + תנועה 0.8% | 5% | 16% | אישור נפח חזק |
| 🔥 **Hard Squeeze** | `SqueezeHunter` | short float ≥ 20%, Small Cap, rvol 1.5x | 8% | 40% | לוחץ שורטסטים |
| ⚡ **Lightning Squeeze** | `SwingSetup` | float < 50M, gap up, short ≥ 10%, rvol 2x, price < $50 | 8% | 35% | partial TP 10%, trail 0.93 |
| 🌪️ **Gap & Squeeze** | `SeasonalityTrader` | float < 30M, gap up, short ≥ 20%, rvol 5x, price < $20 | 10% | 60% | הכי אגרסיבי |
| 💥 **Nano Squeeze** | `PatternTrader` | short ≥ 15%, Small Cap, rvol 2x | 10% | 50% | לוטרי |

### Exit Logic (ברירות מחדל — כל האסטרטגיות)

| פרמטר | ערך | הסבר |
|---|---|---|
| `partial_tp_trigger` | **12%** | מוכר 40% מהפוזיציה ב-+12% |
| `trailing_trigger` | **8%** | מפעיל trailing stop ב-+8% |
| `trail_pct` | **0.91** | trailing ב-91% מהשיא — 9% מרווח לתנודתיות |
| Stale exit | 2 ימים | סוגר אם מוחזק 2+ ימים עם < 2% רווח |

> Scalper ו-Lightning Squeeze מחליפים ברירות מחדל אלה (partial_tp=10%, trail_pct=0.95/0.93)

### מקורות מניות לארנה

| מקור | תדירות | לאיזה אסטרטגיה |
|---|---|---|
| Finviz Momentum Scanner (TTL=18s) | כל 10s (refresh אם > 20s) | כולן |
| Finviz `cap_small, sh_short_o20` | כל 2 דקות | Hard / Gap / Nano Squeeze (floor short_float=22) |
| Finviz `cap_small, sh_short_o10` | כל 2 דקות | Lightning Squeeze (floor short_float=11) |

### EOD Auto-Replace (16:15 ET)

כל יום ב-16:15 ET אסטרטגיות עם P&L שלילי מוחלפות ב-clone של המנצח.
**פוזיציות ברווח לא נסגרות** — רק פוזיציות מפסידות.

שישי 16:05 ET — המנצח השבועי מוזן ל-`ai_learning.json` (Smart Portfolio Brain v5).

---

## 🏦 IB Gateway Integration

- Port 4002 (paper trading) · Account: `DU3788776`
- Auto-follows leaderboard (`__auto__` mode) — עוקב אחרי #1
- Telegram report כל 2 שעות: leaderboard + positions + smart suggestions
- Auto-reconnect כל 60s עם backoff אחרי 5 כשלונות

---

## 📱 Frontend — Tabs

**7 טאבים פעילים:**

| Tab | Component | תפקיד |
|---|---|---|
| 🏆 **ארנה** | `StrategyArena.jsx` | לוח תוצאות — 8 אסטרטגיות, פוזיציות, events, P&L |
| 📈 **סיגנלים** | `TechnicalSignalsScanner.jsx` | MACD + RSI + Bollinger Bands scanner |
| 🎯 **ניתוח יומי** | `DailyAnalysisScanner.jsx` | composite score 0–100, entry/stop/target |
| 🏦 **IB חשבון** | `IBPortfolio.jsx` | פוזיציות IB, orders, executions, P&L |
| 🤖 **Pattern Bot** | `PatternScanner.jsx` | pattern recognition + historical win rates |
| 📅 **עונתיות** | `SeasonalityScanner.jsx` | seasonality patterns (3/5/7/10/15 שנה) |
| 📋 **סורק בסיסי** | `FinvizTableScanner.jsx` | Finviz momentum screener |

**3 טאבים מושבתים זמנית (קיימים בקוד, לא בתפריט):**

| Tab | Component | סיבת הסרה |
|---|---|---|
| ☀️ **בריפינג** | `DailyBriefing.jsx` | עומס משאבים — heavy computation |
| 💊 **FDA** | `FDACatalystTracker.jsx` | עומס משאבים — 6-source scraper |
| 📰 **חדשות** | `NewsPanel.jsx` | הוסר מהתפריט, ticker עדיין גלוי בheader |

**ArenaIBWidget** (header) — LIVE/OFFLINE + אסטרטגיה + P&L + פוזיציות. מתרענן כל 30s.

---

## 🚀 Quick Start

```bash
# Backend
cd backend && source venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (nvm — snap node is broken on Ubuntu)
export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh"
cd frontend && npx vite --host 0.0.0.0
```

- Frontend: `http://localhost:3000`
- API docs: `http://localhost:8000/docs`

---

## 🏗️ Architecture

```
stock-scanner-app/
├── backend/
│   └── app/
│       ├── main.py                    # Scheduler (8 jobs) + lifespan + keep-alive
│       ├── services/                  # 25 services
│       │   ├── strategy_arena.py      # Core arena: 8 strategies, MiniPortfolio, exit logic
│       │   ├── arena_ib_trader.py     # IB Gateway bridge + Telegram reports
│       │   ├── pattern_autotrader.py  # Pattern bot (9:20 AM ET scan, 30m windows)
│       │   ├── ib_service.py          # IB connector (port 4002, thread-safe)
│       │   ├── briefing_service.py    # Daily briefing (disabled — heavy)
│       │   ├── catalyst_tracker.py    # FDA 6-source aggregator
│       │   ├── smart_portfolio.py     # AI brain (ai_learning.json)
│       │   ├── alerts_service.py      # Telegram + email alerts
│       │   └── ...                    # technical_analysis, signals, seasonality, etc.
│       ├── api/
│       │   └── routes.py              # 78 API endpoints + Finviz cache layers
│       └── scrapers/                  # 17 scrapers
│           ├── finviz_screener.py     # CORE — Finviz Elite momentum + smallcap scan
│           ├── finviz_fundamentals.py # Stock fundamentals (P/E, short %, insider)
│           ├── fda_calendar.py        # FDA 6-source: BioPharmCatalyst, RTTNews,
│           │                          #   Drugs.com, ClinicalTrials.gov, CheckRare, FDATracker
│           ├── social_trending.py     # Reddit, StockTwits, Twitter
│           └── ...                    # yahoo, benzinga, cnbc, seeking_alpha, etc.
├── frontend/
│   └── src/
│       ├── AppMomentum.jsx            # PRIMARY APP — tabs, header, news ticker
│       └── components/                # 27 components (7 active, 20 disabled/utility)
└── backend/data/                      # 9 JSON state files
    ├── strategy_arena.json            # Arena state (positions, trades, ticks)
    ├── arena_ib_trader.json           # IB trader state
    ├── ai_learning.json               # Brain v5 — learning from arena winner
    ├── ib_trade_history.json          # IB paper trade log
    ├── smart_portfolio.json           # Smart portfolio state
    ├── pattern_portfolio.json         # Pattern autotrader state
    ├── demo_portfolio.json            # Manual demo portfolio
    ├── trade_history.json             # Trade log
    └── market_regime.json             # Market regime (bullish/bearish/neutral)
```

| Layer | Tech |
|---|---|
| Backend | Python 3.12 · FastAPI · APScheduler · uvicorn |
| Frontend | React 18 · Vite · TanStack Query · i18next (EN/עב) |
| Broker | Interactive Brokers (ib_insync, port 4002) |
| Data | Finviz Elite · yfinance · ClinicalTrials.gov API · 6 FDA sources |
| Notifications | Telegram Bot API · Groq LLM (llama-4-scout) |

---

## ⚙️ Scheduler Jobs

| Job ID | Interval | מה עושה | סטטוס |
|---|---|---|---|
| `arena_tick_job` | **כל 10 שניות** | Finviz(20s) + yfinance live prices + think() + IB | ✅ פעיל |
| `smallcap_squeeze_job` | כל 2 דקות | מרענן SmallCap cache (o20 + o10) | ✅ פעיל |
| `arena_eod_job` | כל דקה (15:45–16:09 ET) | preview 15:45, winner 16:05 | ✅ פעיל |
| `eod_replace_job` | כל דקה (16:15–16:19 ET) | מחליף אסטרטגיות מפסידות | ✅ פעיל |
| `arena_report_job` | כל 2 שעות | Telegram leaderboard + IB + suggestions | ✅ פעיל |
| `ib_reconnect_job` | כל 60s | auto-reconnect IB | ✅ פעיל |
| `watchdog_job` | כל 5 דקות | self-healing, stale check, zombie cleanup | ✅ פעיל |
| `arena_aux_cache_job` | כל 30 דקות | seasonal + pattern signals cache | ✅ פעיל |
| `brain_job` | — | Smart Portfolio brain tick | ⏸️ מושבת (saves resources) |

---

## 📊 API Endpoints (78 total)

### Arena
```
GET  /api/smart-portfolio/arena/status               Leaderboard + positions + events
POST /api/smart-portfolio/arena/think                Run arena tick (all strategies)
POST /api/smart-portfolio/arena/declare-daily-winner EOD winner (16:05 ET)
POST /api/smart-portfolio/arena/force-reset/{name}   Force-close strategy positions
POST /api/ib/arena-trader/enable                     Enable IB auto-trading
GET  /api/ib/arena-trader/status                     IB trader status
```

### Screeners & Prices
```
GET  /api/screener/finviz-table       Finviz momentum table (cache 18s)
GET  /api/screener/live-prices        Live batch prices (yfinance)
GET  /api/screener/vwap-momentum      VWAP momentum screener
GET  /api/analysis/daily              Daily composite score 0–100
GET  /api/signals/technical           MACD + RSI + BB scanner
```

### IB Gateway
```
GET  /api/ib/status                   Connection status
GET  /api/ib/positions                Open positions
GET  /api/ib/account                  Account details + buying power
GET  /api/ib/executions               Execution history
POST /api/ib/order                    Place order
DELETE /api/ib/order/{id}             Cancel order
```

### Catalyst Tracking (disabled tabs, endpoints still live)
```
GET  /api/catalyst/fda               FDA calendar (6 sources, probability scoring)
GET  /api/briefing/daily             Daily briefing (30min cache)
GET  /api/trending/social            Social trending (Reddit, StockTwits)
```

### Pattern Bot
```
GET  /api/pattern/analyze/{ticker}   Analyze patterns
GET  /api/pattern/autotrader/status  Autotrader status
POST /api/pattern/autotrader/enable  Enable pattern autotrader
```

### Seasonality
```
GET  /api/seasonality                Seasonal patterns (3/5/7/10/15yr)
```

---

## 📂 Cache TTLs

| Cache | TTL | מה |
|---|---|---|
| `_FV_TABLE_CACHE_TTL` | **18 שניות** | Finviz momentum scan |
| `_FV_SMALLCAP_CACHE_TTL` | **120 שניות** | SmallCap squeeze stocks |
| Live prices (per ticker) | 120 שניות | yfinance per-ticker cache |
| API response cache | 120 שניות | General endpoint cache |
| Briefing | 30 דקות | Daily briefing (heavy compute) |
| Tech signals / daily analysis | 15 דקות | MACD+RSI+BB / composite |
| Seasonality | 30 דקות | Historical patterns |

---

## ⚠️ Disclaimer

For educational and informational purposes only. Not financial advice.

---

*🇮🇱 פרויקט מסחר אוטונומי — ארנה של 8 אסטרטגיות מתחרות בזמן אמת*
