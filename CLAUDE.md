# Stock Scanner — Project Guide

## Quick Start

```bash
# Backend
cd backend && source venv/bin/activate
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (use nvm — snap npm is broken)
export NVM_DIR="$HOME/.nvm" && . "$NVM_DIR/nvm.sh"
cd frontend && npx vite --host 0.0.0.0
```

## Architecture

| Layer | Path | Notes |
|---|---|---|
| Backend | `backend/app/` | FastAPI, Python 3.12 |
| Frontend | `frontend/src/` | React + Vite, port 3000 |
| Data | `backend/data/` | JSON state files |
| Venv | `backend/venv/` | Python dependencies |

## Key Files

| קובץ | תפקיד |
|---|---|
| `backend/app/services/strategy_arena.py` | לוגיקת הארנה — 8 אסטרטגיות, MiniPortfolio, exit logic |
| `backend/app/services/arena_ib_trader.py` | חיבור IB Gateway + Telegram reports |
| `backend/app/api/routes.py` | כל ה-API endpoints, cache layers |
| `backend/app/main.py` | Scheduler: ticks, smallcap scan, EOD, watchdog |
| `backend/data/strategy_arena.json` | State שנשמר בין restarts (פוזיציות, עסקאות, tick count) |
| `frontend/src/AppMomentum.jsx` | Main UI — tabs, ArenaIBWidget בheader |

---

## Strategy Arena

8 מיני-תיקים ($1,000 כל אחד) מתחרים אוטונומית. טיק כל **10 שניות**.
מחירים חיים מ-Finviz + yfinance מוזרקים בכל טיק.

### זרימת נתונים — כל 10 שניות

```
1. Finviz scan  →  אם cache > 20s ישן: סריקה מחודשת (TTL=18s)
2. Live prices  →  yfinance לכל הפוזיציות הפתוחות → מוזרק ל-cache
3. SmallCap     →  _FV_SMALLCAP_CACHE ממוזג לרשימת המניות (מרענן כל 2 דקות)
4. Arena think  →  כל 10 האסטרטגיות מריצות לוגיקת כניסה/יציאה
5. IB Trader    →  אם מחובר — מבצע פקודות בחשבון demo DU3788776
```

### מקורות מניות

| מקור | תדירות | מניות | לאיזה אסטרטגיה |
|---|---|---|---|
| Finviz Momentum Scanner | כל 18 שניות (cache TTL) | ~50-80 מניות מומנטום | כולן |
| SmallCap Squeeze — o20 | כל 2 דקות | cap_small, sh_short_o20 | Hard/Gap/Nano Squeeze |
| SmallCap Squeeze — o10 | כל 2 דקות | cap_small, sh_short_o10 | Lightning Squeeze |

**Floor values בSmallCap cache:**
- מ-o20: `short_float=22`, `health_score=20`, `squeeze_total_score=55`
- מ-o10: `short_float=11`, `health_score=20`, `squeeze_total_score=55`
- `rel_volume` = מחושב מ-change_pct: `max(1.5, min(chg * 0.8, 8.0))`

---

### Exit Logic — ברירות מחדל לכל האסטרטגיות

| פרמטר | ערך | הסבר |
|---|---|---|
| `partial_tp_trigger` | **12%** | מוכר 40% מהפוזיציה ב-+12% (היה 5% — הרג רווחים) |
| `trailing_trigger` | **8%** | מפעיל trailing stop רק אחרי +8% (היה 4%) |
| `trail_pct` | **0.91** | trailing ב-91% מהשיא — 9% מרווח לתנודתיות (היה 0.97) |
| Stale exit | 2 ימים | סוגר אם מוחזק 2+ ימים עם פחות מ-2% רווח |
| Stop loss | per strategy | קבוע בכניסה |
| Target | per strategy | יציאה מלאה |

אסטרטגיות עם override מותאם אישית: Scalper, Lightning Squeeze (ראה למטה).

---

### 10 האסטרטגיות

#### ⚖️ Balanced (`Balanced`)

| פרמטר | ערך |
|---|---|
| min_health | 30 |
| min_conf | 35 |
| min_rvol | 0.4x |
| Stop / Target | 6% / 18% |
| max_positions | 3 |
| short_float | לא נדרש |

**פילוסופיה:** קונה מניות עם health score > 30 ונפח סביר. האסטרטגיה הכי שמרנית — ברירת מחדל לשוק נורמלי. מצליח בימים רגועים עם מניות כמו CF, SMCI.

---

#### 🎯 High Conviction (`HighConviction`)

| פרמטר | ערך |
|---|---|
| min_health | 45 |
| min_conf | 48 |
| min_rvol | 0.6x |
| Stop / Target | 5% / 25% |
| max_positions | 2 |

**פילוסופיה:** מחכה לסיגנלים חזקים מאוד. עושה מעט עסקאות אבל R:R גבוה. מתאים לימים עם מניות ברורות.

---

#### 🔥 Hard Squeeze (`SqueezeHunter`)

| פרמטר | ערך |
|---|---|
| min_health | 12 |
| min_conf | 15 |
| min_rvol | 1.5x |
| min_chg | 2% |
| short_float | ≥ 20% |
| Stop / Target | 8% / 40% |
| max_positions | 2 |
| small_cap_only | ✅ |

**פילוסופיה:** מחפש Small/Micro Cap עם לחץ שורט גבוה (≥20%). כשנפח עולה 1.5x — נכנס. מצפה שהשורטסטים ייאלצו לכסות ויקפיצו. יעד +40%.

---

#### ⚡ Scalper (`Scalper`)

| פרמטר | ערך |
|---|---|
| min_health | 18 |
| min_conf | 20 |
| min_rvol | 0.5x |
| min_chg | 0.1% |
| Stop / Target | 6% / 20% |
| max_positions | 3 |
| partial_tp_trigger | **10%** (override) |
| trailing_trigger | **8%** (override) |
| trail_pct | **0.95** (override) |

**פילוסופיה:** נכנס לכמעט כל מניה שזזה. 3 פוזיציות במקביל. מנהל trailing stop הדוק. **בדרך כלל המוביל בארנה** — עובד טוב בשוק עם מומנטום חזק.

---

#### 🚀 Momentum Breaker (`MomentumBreaker`)

| פרמטר | ערך |
|---|---|
| min_health | 22 |
| min_conf | 28 |
| min_rvol | 1.5x |
| min_chg | 0.8% |
| Stop / Target | 5% / 16% |
| max_positions | 3 |

**פילוסופיה:** נכנס רק עם אישור נפח חזק (1.5x) + תנועה של 0.8%. יעד שמרני (16%) אבל stop הדוק (5%). פחות עסקאות מהScalper.

---

#### ⚡ Lightning Squeeze (`SwingSetup`)

| פרמטר | ערך |
|---|---|
| min_health | 10 |
| min_conf | 12 |
| min_rvol | 2x |
| min_chg | 1% |
| short_float | ≥ 10% |
| float_shares | < 50M |
| max_price | $50 |
| requires_gap | ✅ |
| Stop / Target | 8% / 35% |
| max_positions | 3 |
| partial_tp_trigger | **10%** (override) |
| trailing_trigger | **8%** (override) |
| trail_pct | **0.93** (override) |

**פילוסופיה:** Float קטן (< 50M מניות) + gap up + שורט ≥ 10% + נפח 2x. כשכל התנאים מתקיימים יש פוטנציאל לסקוויז מהיר. לוקח חלק ב-+10% ומנהל trailing הדוק. יעד +35%.

**Gap detection:** בודק `gap_pct` מ-Finviz. Fallback: `change_pct > 3%`.

---

#### 🌪️ Gap & Squeeze (`SeasonalityTrader`)

| פרמטר | ערך |
|---|---|
| min_health | 8 |
| min_conf | 10 |
| min_rvol | 5x |
| min_chg | 1% |
| short_float | ≥ 20% |
| float_shares | < 30M |
| max_price | $20 |
| requires_gap | ✅ |
| Stop / Target | 10% / 60% |
| max_positions | 2 |
| small_cap_only | ✅ |

**פילוסופיה:** הפילטרים הכי קשים — מחיר < $20, float < 30M, שורט ≥ 20%, נפח פי 5, gap up. כשכל התנאים מתחברים — מניות שיכולות לעשות +50-100% ביום. Stop רחב (10%) לתנודתיות, יעד +60%.

---

#### 💥 Nano Squeeze (`PatternTrader`)

| פרמטר | ערך |
|---|---|
| min_health | 10 |
| min_conf | 12 |
| min_rvol | 2x |
| min_chg | 1% |
| short_float | ≥ 15% |
| Stop / Target | 10% / 50% |
| max_positions | 2 |
| small_cap_only | ✅ |

**פילוסופיה:** ביניים בין Hard Squeeze ל-Gap & Squeeze. שורט ≥ 15% (נמוך יותר) אבל נפח 2x. יעד +50% עם stop רחב 10%. Small Cap בלבד.

---

#### 🚀 Premarket Gap (`GapScanner`)

| פרמטר | ערך |
|---|---|
| min_rvol | 2x |
| min_chg | 8% (gap) |
| float_shares | < 50M |
| min/max_price | $2 / $20 |
| entry_window | 9:30–9:45 ET |
| Stop / Target | 8% / 30% |
| max_positions | 2 |

**פילוסופיה:** Gap > 8% premarket על float קטן = daily runner. חלון כניסה צר 15 דקות בלבד. TP חלקי 12% + trail 0.88.

---

#### 💣 Gap Explosion (`GapExplosion`)

| פרמטר | ערך |
|---|---|
| min_rvol | 2x |
| min_gap_pct | 20% |
| short_float | ≥ 10% |
| float_shares | < 50M |
| min/max_price | $1 / $30 |
| entry_window | 9:30–9:50 ET |
| Stop / Target | 12% / 60% |
| max_positions | 2 |
| partial_tp | 15% (50% מהפוז') |
| trail_pct | 0.88 |

**פילוסופיה:** הפילטר הקשה ביותר לגאפ — gap > 20% + שורט ≥ 10% + float < 50M. כשכל התנאים מתחברים בחלון 9:30–9:50 ET — פוטנציאל לריצה של +50-100%. Stop רחב (12%) לתנודתיות של הפתיחה.

---

### Scheduler Jobs

| Job | תדירות | מה עושה |
|---|---|---|
| `arena_tick_job` | **כל 10 שניות** | Finviz refresh + live prices + arena.think() + IB sync |
| `smallcap_squeeze_job` | כל 2 דקות | מרענן _FV_SMALLCAP_CACHE (o20 + o10) |
| `arena_eod_job` | כל דקה (15:45–16:09 ET) | preview 15:45, daily winner 16:05 |
| `eod_replace_job` | כל דקה (16:15–16:19 ET) | auto_replace_losers() — מחליף אסטרטגיות שליליות |
| `arena_report_job` | כל 2 שעות | send_arena_report() — Telegram leaderboard + IB + suggestions |
| `ib_reconnect_job` | כל 60 שניות | auto-reconnect IB אם מנותק |
| `watchdog_job` | כל 5 דקות | self-healing — מאלץ tick אם stale, מנקה zombie processes |
| `arena_aux_cache_job` | כל 30 דקות | seasonal + pattern signals cache |

---

### EOD Auto-Replace (16:15 ET)

כל יום ב-16:15 ET:
1. מדרג את כל 10 האסטרטגיות לפי P&L
2. אסטרטגיות עם P&L שלילי → מקבלות קונפיג חדש (clone של המנצח + וריאציה)
3. **פוזיציות ברווח — לא נסגרות** (לא הורגים winners)
4. פוזיציות הפסדיות בלבד נסגרות ב-market price

### Weekly Winner (שישי 16:05)

המנצח השבועי → פרמטרים שלו מועברים ל-`ai_learning.json` (Brain v5).

---

## IB Gateway Integration

- Port 4002 (paper trading), clientId=20
- חשבון demo: DU3788776
- Auto-reconnect כל 60 שניות
- עוקב אחרי האסטרטגיה המובילה (`__auto__` mode)
- Telegram report כל 2 שעות: leaderboard + IB positions + suggestions

## Frontend — Tabs

```javascript
const TABS = [
  { key: 'arena',          label: '🏆 ארנה' },
  { key: 'tech-signals',   label: '📈 סיגנלים' },
  { key: 'daily-analysis', label: '🎯 ניתוח יומי' },
  { key: 'ib',             label: '🏦 IB חשבון' },
  { key: 'pattern-bot',    label: '🤖 Pattern Bot' },
  { key: 'seasonality',    label: '📅 עונתיות' },
  { key: 'finviz-table',   label: '📋 סורק בסיסי' },
]
```

**ArenaIBWidget** (header) — מציג: LIVE/OFFLINE + אסטרטגיה פעילה + P&L + מספר פוזיציות. מתרענן כל 30 שניות.

## Cache TTLs

| Cache | TTL | מה |
|---|---|---|
| `_FV_TABLE_CACHE_TTL` | 18 שניות | Finviz momentum scan |
| `_FV_SMALLCAP_CACHE_TTL` | 120 שניות | SmallCap squeeze stocks |
| Response cache | 120 שניות | API responses general |
| Briefing cache | 30 דקות | Daily briefing |
| Signals cache | 15 דקות | Tech signals / daily analysis |
