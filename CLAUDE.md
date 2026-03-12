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

---

## Strategy Arena (`strategy_arena.py`)

8 mini-portfolios ($1,000 each) compete autonomously. Each tick runs every **10 seconds**.
Live prices from Finviz + yfinance injected every tick. EOD auto-replace at 16:15 ET.

### Exit Logic (all strategies share this base)

| Parameter | Default | Notes |
|---|---|---|
| `partial_tp_trigger` | **12%** | Take 40% off table at +12% (was 5% — killed profits) |
| `trailing_trigger` | **8%** | Activate trailing stop at +8% gain |
| `trail_pct` | **0.91** | Trail at 91% of highest price (9% room for volatility) |
| Stop loss | per strategy | Fixed on entry |
| Target | per strategy | Full exit |
| Stale exit | 2 days | Close if held 2+ days with < 2% gain |

---

### The 8 Strategies

#### ⚖️ Balanced (`Balanced`)
**פילוסופיה:** כניסות מאוזנות — health טוב + מומנטום בסיסי

| פרמטר | ערך |
|---|---|
| min_health | 30 |
| min_conf | 35 |
| min_rvol | 0.4x |
| Stop / Target | 6% / 18% |
| max_positions | 3 |
| short_float | לא נדרש |

**מה הוא עושה:** קונה מניות עם health score > 30 ונפח סביר. האסטרטגיה הכי שמרנית — ברירת מחדל לשוק נורמלי. מצליח בימים רגועים עם מניות כמו CF, SMCI.

---

#### 🎯 High Conviction (`HighConviction`)
**פילוסופיה:** רק הכי טובים — פחות עסקאות, R:R גבוה

| פרמטר | ערך |
|---|---|
| min_health | 45 |
| min_conf | 48 |
| min_rvol | 0.6x |
| Stop / Target | 5% / 25% |
| max_positions | 2 |

**מה הוא עושה:** מחכה לסיגנלים חזקים מאוד (health > 45, confidence > 48). עושה מעט עסקאות אבל עם R:R טוב יותר. מתאים לימים עם מניות ברורות.

---

#### 🔥 Hard Squeeze (`SqueezeHunter`)
**פילוסופיה:** שורט סקוויז אגרסיבי — לוחץ על שורטסטים

| פרמטר | ערך |
|---|---|
| short_float | ≥ 20% |
| min_rvol | 1.5x |
| min_chg | 2% |
| Stop / Target | 8% / 40% |
| max_positions | 2 |
| small_cap_only | ✅ |

**מה הוא עושה:** מחפש מניות Small/Micro Cap שיש עליהן לחץ שורט גבוה (≥20%) ועדיין זורמות. כשנפח עולה ב-1.5x, הוא נכנס בתקווה שהשורטסטים ייאלצו לכסות ויקפיצו את המחיר. יעד +40%.

**מקור מניות:** Finviz סריקת `cap_small, sh_short_o20` כל 2 דקות.

---

#### ⚡ Scalper (`Scalper`)
**פילוסופיה:** כניסות אגרסיביות — 3 פוזיציות ריכוזיות

| פרמטר | ערך |
|---|---|
| min_health | 18 |
| min_conf | 20 |
| min_rvol | 0.5x |
| min_chg | 0.1% |
| Stop / Target | 6% / 20% |
| max_positions | 3 |
| partial_tp | 10% (מותאם אישית) |
| trailing | מ-8%, trail=0.95 |

**מה הוא עושה:** נכנס כמעט לכל מניה שזזה. 3 פוזיציות במקביל. לוקח partial TP ב-10% ומנהל trailing stop ב-0.95. **כרגע המוביל** (3.7% P&L). עובד טוב במומנטום שוק חזק.

---

#### 🚀 Momentum Breaker (`MomentumBreaker`)
**פילוסופיה:** פורצים עם נפח פנומנלי

| פרמטר | ערך |
|---|---|
| min_health | 22 |
| min_conf | 28 |
| min_rvol | 1.5x |
| min_chg | 0.8% |
| Stop / Target | 5% / 16% |
| max_positions | 3 |

**מה הוא עושה:** נכנס רק כשנפח גבוה במיוחד (1.5x ממוצע) ויש כבר תנועה של 0.8%. פחות עסקאות מהScalper אבל עם אישור נפח חזק. יעד שמרני יותר (16%) אבל stop הדוק (5%).

---

#### ⚡ Lightning Squeeze (`SwingSetup`)
**פילוסופיה:** Float קטן + Gap Up + שורט = פוטנציאל להתפוצצות

| פרמטר | ערך |
|---|---|
| short_float | ≥ 10% |
| float_shares | < 50M |
| max_price | $50 |
| min_rvol | 2x |
| requires_gap | ✅ |
| Stop / Target | 8% / 35% |
| max_positions | 3 |
| partial_tp | 10% |
| trailing | מ-8%, trail=0.93 |

**מה הוא עושה:** מחפש מניות עם float קטן (< 50M מניות בשוק) שגאפו למעלה ועדיין יש עליהן שורט של לפחות 10%. כשהנפח פי 2+ מהרגיל — זה סיגנל שהשורטסטים בבעיה. יעד +35%, לוקח חלק ב-10%.

**Gap detection:** בודק `gap_pct` מ-Finviz, או fallback: `change_pct > 3%`.

---

#### 🌪️ Gap & Squeeze (`SeasonalityTrader`)
**פילוסופיה:** הכי קיצוני — float זעיר + gap + שורט גבוה

| פרמטר | ערך |
|---|---|
| short_float | ≥ 20% |
| float_shares | < 30M |
| max_price | $20 |
| min_rvol | 5x |
| requires_gap | ✅ |
| Stop / Target | 10% / 60% |
| max_positions | 2 |
| small_cap_only | ✅ |

**מה הוא עושה:** הפילטרים הכי קשים — מחיר < $20, float < 30M מניות, שורט ≥ 20%, נפח פי 5 מהרגיל, gap up. כשכל התנאים מתחברים, זה מניות שיכולות לעשות +50-100% ביום. Stop רחב (10%) כי התנודתיות גבוהה, יעד +60%.

---

#### 💥 Nano Squeeze (`PatternTrader`)
**פילוסופיה:** לוטרי Small Cap — סיכון גבוה, תגמול גבוה

| פרמטר | ערך |
|---|---|
| short_float | ≥ 15% |
| min_rvol | 2x |
| min_chg | 1% |
| Stop / Target | 10% / 50% |
| max_positions | 2 |
| small_cap_only | ✅ |

**מה הוא עושה:** ביניים בין Hard Squeeze ל-Gap & Squeeze. דורש שורט ≥ 15% (נמוך יותר מHard) אבל נפח 2x. יעד +50% עם stop רחב 10%. מניות Small Cap בלבד.

---

### מקורות מניות לארנה

1. **Finviz Momentum Scanner** (עדכון כל 18 שניות)
   - רשימה ראשית של ~50-80 מניות בעלות מומנטום
   - כל הסטרטגיות מקבלות את הרשימה הזאת

2. **SmallCap Squeeze Scanner** (עדכון כל 2 דקות)
   - Finviz: `cap_small, sh_short_o20` → ~40 מניות עם short float > 20%
   - Finviz: `cap_small, sh_short_o10` → ~60 מניות עם short float > 10%
   - ייעודי לאסטרטגיות הסקוויז (Hard, Nano, Gap, Lightning)
   - Floor values: `short_float=22` (from o20 scan), `short_float=11` (from o10 scan)

---

### EOD Auto-Replace (16:15 ET)

כל יום ב-16:15 ET:
1. מדרג את כל 8 האסטרטגיות לפי P&L
2. אסטרטגיות עם P&L שלילי → מקבלות קונפיג חדש (clone של המנצח עם וריאציה)
3. **פוזיציות ברווח — לא נסגרות** (תוקן: לא הורגים winners)
4. פוזיציות הפסדיות נסגרות ב-market price

### Weekly Winner (שישי 16:05)

המנצח השבועי → פרמטרים שלו מועברים ל-`ai_learning.json` (Brain v5).

---

## IB Gateway Integration

- Port 4002 (paper), clientId=20
- Auto-reconnect כל 60 שניות
- עוקב אחרי האסטרטגיה המובילה בארנה
- מבצע עסקאות אמיתיות בחשבון demo DU3788776
- Telegram report כל 2 שעות

## Key Files

| קובץ | תפקיד |
|---|---|
| `backend/app/services/strategy_arena.py` | לוגיקת הארנה, 8 אסטרטגיות |
| `backend/app/services/arena_ib_trader.py` | חיבור IB + Telegram |
| `backend/app/api/routes.py` | API endpoints + caches |
| `backend/app/main.py` | Scheduler: ticks, smallcap scan, EOD |
| `backend/data/strategy_arena.json` | State שנשמר (פוזיציות, עסקאות) |
| `frontend/src/AppMomentum.jsx` | Main UI + ArenaIBWidget |
