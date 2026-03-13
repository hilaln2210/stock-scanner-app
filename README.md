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

### 3 כללים גלובליים

| כלל | ערך | הסבר |
|---|---|---|
| **SPY Regime** | SPY < -0.5% ביום | אוסר על כניסות חדשות בשוק אדום (regular session בלבד) |
| **Entry Window** | per strategy | כל אסטרטגיה סוגרת כניסות בשעה מסוימת (Scalper 10:00, Balanced 11:00) |
| **Max 2 Positions** | כל האסטרטגיות | מקסימום 2 פוזיציות פתוחות בו-זמנית |

### 8 האסטרטגיות

| אסטרטגיה | Python key | רעיון | Stop | Target | מה מיוחד |
|---|---|---|---|---|---|
| ⚖️ **Balanced** | `Balanced` | health > 30, rvol ≥ 1.2, כניסה לפני 11:00 ET | 6% | 18% | ברירת מחדל, כל שוק |
| 🎯 **High Conviction** | `HighConviction` | health > 45, confidence > 48 | 5% | 15% | partial TP 8% (50%), trail 0.91 |
| ⚡ **Scalper** | `Scalper` | rvol ≥ 1.5, כניסה 9:30–10:00 ET בלבד | 6% | 20% | partial TP 10%, trail 0.92 |
| 🚀 **Momentum Breaker** | `MomentumBreaker` | rvol ≥ 1.5x + תנועה ≥ 1.5%, לפני 10:30 ET | 5% | 16% | אישור נפח חזק |
| 🔥 **Hard Squeeze** | `SqueezeHunter` | short float ≥ 20%, Small Cap, rvol 1.5x | 8% | 40% | partial TP 15% (50%), trail 12% trigger |
| ⚡ **Lightning Squeeze** | `SwingSetup` | float < 50M, gap up, short ≥ 10%, rvol 2x, price < $50 | 8% | 35% | partial TP 10%, trail 0.87 (רחב) |
| 🌪️ **Gap & Squeeze** | `SeasonalityTrader` | float < 30M, gap up, short ≥ 20%, rvol 5x, price < $20 | 10% | 60% | dual TP: 20% (30%) + 40% (30%), runner ל-60% |
| 💥 **Nano Squeeze** | `PatternTrader` | short ≥ 15%, Small Cap, rvol 2x | 6% | 50% | half position size (לוטרי) |

### Exit Logic (ברירות מחדל — כל האסטרטגיות)

| פרמטר | ערך | הסבר |
|---|---|---|
| `partial_tp_trigger` | **6%** | מוכר 40% מהפוזיציה ב-+6% (catch gains לפני reversal) |
| `trailing_trigger` | **8%** | מפעיל trailing stop ב-+8% |
| `trail_pct` | **0.91** | trailing ב-91% מהשיא — 9% מרווח לתנודתיות |
| Stale exit | **1 יום** | סוגר אם מוחזק 1+ יום עם < 2% רווח (dead money) |
| Stop loss | per strategy | קבוע בכניסה |
| Target | per strategy | יציאה מלאה |

> אסטרטגיות עם override: HighConviction (partial 8%), Hard Squeeze (partial 15%), Lightning Squeeze (trail 0.87), Gap & Squeeze (dual TP 20%+40%), Scalper (trail 0.92)

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
- **Auto-follows leaderboard** (`__auto__` mode) — עוקב אחרי #1
- **Heartbeat real** — `reqCurrentTime()` כל 60s (לא רק `isConnected()`)
- **Telegram disconnect alert** — התראה מיידית בניתוק + זמן downtime בהתחברות מחדש
- **Smart backoff** — aggressive בשלושת הכשלונות הראשונים → כל 2 ticks → כל 5 ticks
- **leader_switch disabled** — שינוי מוביל הוא display-only, לא מוכר פוזיציות
- **price=0 SELL blocked** — כל sell ללא מחיר חסום hard ב-execute
- Telegram report כל 2 שעות: leaderboard + positions + smart suggestions
- IBC (Interactive Brokers Controller) — auto-restart Gateway ב-06:30 ET
- SMS 2FA relay — בקשת SMS מגיעה ל-Telegram, תשובה נכנסת ל-Gateway דרך xdotool

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
│       │   ├── ib_service.py          # IB connector (heartbeat, port 4002, thread-safe)
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
├── backend/data/                      # 9 JSON state files
│   ├── strategy_arena.json            # Arena state (positions, trades, ticks)
│   ├── arena_ib_trader.json           # IB trader state (positions, trade log)
│   ├── ai_learning.json               # Brain v5 — learning from arena winner
│   ├── ib_trade_history.json          # IB paper trade log
│   ├── smart_portfolio.json           # Smart portfolio state
│   ├── pattern_portfolio.json         # Pattern autotrader state
│   ├── demo_portfolio.json            # Manual demo portfolio
│   ├── trade_history.json             # Trade log
│   └── market_regime.json             # Market regime (bullish/bearish/neutral)
└── ibc/                               # IBC (Interactive Brokers Controller)
    ├── config.ini                     # IBC config (paper, port 4002, auto-restart 06:30)
    ├── start-gateway.sh               # Direct Java launcher (IBC + Gateway classpath)
    ├── ibc_sms_bot.py                 # SMS 2FA relay via Telegram + xdotool
    └── remind-ib-login.sh             # Sunday 08:50 Telegram reminder
```

| Layer | Tech |
|---|---|
| Backend | Python 3.12 · FastAPI · APScheduler · uvicorn |
| Frontend | React 18 · Vite · TanStack Query · i18next (EN/עב) |
| Broker | Interactive Brokers (ib_insync, port 4002) · IBC auto-restart |
| Data | Finviz Elite · yfinance · ClinicalTrials.gov API · 6 FDA sources |
| Notifications | Telegram Bot API · Groq LLM (llama-4-scout) |
| Automation | IBC v3.23 · xdotool · systemd user services |

---

## ⚙️ Scheduler Jobs

| Job ID | Interval | מה עושה | סטטוס |
|---|---|---|---|
| `arena_tick_job` | **כל 10 שניות** | Finviz(20s) + yfinance live prices + SPY regime + think() + IB | ✅ פעיל |
| `smallcap_squeeze_job` | כל 2 דקות | מרענן SmallCap cache (o20 + o10) | ✅ פעיל |
| `arena_eod_job` | כל דקה (15:45–16:09 ET) | preview 15:45, winner 16:05 | ✅ פעיל |
| `eod_replace_job` | כל דקה (16:15–16:19 ET) | מחליף אסטרטגיות מפסידות | ✅ פעיל |
| `arena_report_job` | כל 2 שעות | Telegram leaderboard + IB + suggestions | ✅ פעיל |
| `ib_reconnect_job` | כל 60s | heartbeat + auto-reconnect + Telegram alert | ✅ פעיל |
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
GET  /api/ib/status                   Connection status + heartbeat + disconnect_for_seconds
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
| `_SPY_PREV_CLOSE_CACHE` | **5 דקות** | SPY prev close לregime filter |
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
