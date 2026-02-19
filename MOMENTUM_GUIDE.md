# 🚀 Momentum Scanner - מדריך שימוש

## מה חדש? 🎯

המערכת עודכנה **לגמרי** להיות ממוקדת במומנטום גבוה ומסחר פעיל!

### תכונות חדשות:

1. **Market Pulse Scanner** 📊
   - סריקה חיה של Finviz Elite Market Pulse
   - זיהוי מניות עם מומנטום גבוה (ציון 0-100)
   - סינון אוטומטי של מניות עם מומנטום **אקסטרים** (80+)

2. **Real-Time Momentum Scanner** ⚡
   - סריקה ממקורות מרובים
   - זיהוי הזדמנויות מסחר בזמן אמת
   - דירוג לפי ציון מומנטום

3. **תצוגה חדשה לגמרי** 🎨
   - ממשק מודרני וקל לשימוש
   - סטטיסטיקות מהירות (Extreme Momentum, Gainers, Losers)
   - עדכון אוטומטי כל 30 שניות - 5 דקות
   - חיפוש לפי טיקר
   - סינון לפי ציון מומנטום מינימלי

---

## 🚀 איך להריץ את המערכת המעודכנת

### שלב 1: עצור שרתים קיימים
```bash
# עצור את השרתים הישנים
pkill -9 -f uvicorn
pkill -9 -f vite
pkill -9 -f node
```

### שלב 2: הרץ Backend
```bash
cd ~/Desktop/Stocks/backend
source venv/bin/activate
uvicorn app.main:app --reload
```

**או בטרמינל נפרד:**
```bash
cd ~/Desktop/Stocks/backend
source venv/bin/activate
uvicorn app.main:app --reload > /tmp/backend.log 2>&1 &
```

### שלב 3: הרץ Frontend
```bash
cd ~/Desktop/Stocks/frontend
npm run dev
```

**או בטרמינל נפרד:**
```bash
cd ~/Desktop/Stocks/frontend
npm run dev > /tmp/frontend.log 2>&1 &
```

### שלב 4: גש לממשק
פתח דפדפן וגש ל:
```
http://localhost:3000
```

---

## 📊 איך להשתמש במערכת החדשה

### 1. **Market Pulse vs Momentum Scanner**
- **Market Pulse** - מניות מ-Finviz Elite בעלות מומנטום גבוה
- **Momentum Scanner** - סריקה רחבה ממקורות מרובים

בחר בכפתור בחלק העליון של המסך.

### 2. **סינון מניות**
- **חיפוש טיקר**: הקלד טיקר בשדה החיפוש
- **ציון מינימלי**: בחר 60+, 70+, או 80+ (אקסטרים)
- **רענון אוטומטי**: בחר 30s, 1m, 2m, 5m, או Manual

### 3. **הבנת ציוני המומנטום**

| ציון | רמה | משמעות |
|------|-----|---------|
| 80-100 | 🔥 EXTREME | מומנטום אקסטרים - הזדמנות חמה! |
| 65-79 | ⚡ HIGH | מומנטום גבוה - שווה תשומת לב |
| 60-64 | 📈 MODERATE | מומנטום בינוני |
| <60 | - | לא מוצג (מסונן) |

### 4. **מה משפיע על ציון המומנטום?**

הציון מחושב לפי:
- ✅ **מילות מפתח חיוביות**: surge, soar, breakout, rally, spike
- ✅ **נפח מסחר**: unusual volume, heavy volume
- ✅ **קטליזטורים**: beat, upgrade, approval, partnership
- ❌ **מילות מפתח שליליות**: fall, drop, crash (מורידות ציון)

### 5. **פרטי מניה**
לחץ על כל מניה כדי לראות:
- כותרת מלאה
- ציון מומנטום מפורט
- שינוי מחיר (אם זמין)
- קישור למאמר המלא

---

## 🔧 API Endpoints החדשים

### 1. Market Pulse
```bash
curl "http://localhost:8000/api/momentum/market-pulse?limit=50"
```

### 2. Momentum Scanner
```bash
curl "http://localhost:8000/api/momentum/scanner"
```

### 3. פרטי מניה ספציפית
```bash
curl "http://localhost:8000/api/momentum/stock/AAPL"
```

### 4. תמיכה בעברית
הוסף `?lang=he` לכל endpoint:
```bash
curl "http://localhost:8000/api/momentum/market-pulse?limit=10&lang=he"
```

---

## 📈 דוגמאות שימוש

### תרחיש 1: מחפש מניות עם מומנטום אקסטרים
1. פתח http://localhost:3000
2. בחר **Market Pulse**
3. הגדר סינון **Min Score: 80+**
4. רענון אוטומטי כל **30s**

### תרחיש 2: עוקב אחרי מניה ספציפית
1. הקלד טיקר בחיפוש (למשל: NVDA)
2. המערכת תציג רק חדשות ומומנטום של המניה הזו
3. ראה גם בפאנל החדשות מה קורה עם המניה

### תרחיש 3: מעקב יומי
1. השאר את המערכת פתוחה עם רענון אוטומטי
2. המערכת תעדכן כל הזמן
3. מניות עם ציון גבוה יופיעו בראש

---

## ⚙️ התאמה אישית

### עדכן את Finviz Elite credentials
ערוך את `/home/hila/Desktop/Stocks/backend/.env`:
```bash
FINVIZ_EMAIL=your-email@gmail.com
FINVIZ_PASSWORD=your-password
```

### שנה זמן רענון ברירת מחדל
ב-AppMomentum.jsx שורה 22:
```javascript
const [autoRefresh, setAutoRefresh] = useState(60); // שניות
```

### שנה ציון מינימלי ברירת מחדל
ב-AppMomentum.jsx שורה 24:
```javascript
const [minMomentum, setMinMomentum] = useState(60); // 0-100
```

---

## 🐛 פתרון בעיות

### שרת לא עולה
```bash
# בדוק אם הפורט תפוס
lsof -ti:8000
lsof -ti:3000

# הרוג תהליכים
kill -9 $(lsof -ti:8000)
kill -9 $(lsof -ti:3000)
```

### לא רואה מניות
1. ודא שהשרת רץ: http://localhost:8000/api/health
2. בדוק לוגים: `tail -f /tmp/backend.log`
3. נסה רענון ידני (כפתור Refresh)
4. ודא חיבור אינטרנט (הסורק צריך לגשת לאתרים חיצוניים)

### הממשק לא מתעדכן
1. נקה cache של הדפדפן (Ctrl+Shift+R)
2. בדוק שהפרונטאנד רץ: http://localhost:3000
3. ראה לוגים: `tail -f /tmp/frontend.log`

---

## 🎯 טיפים למסחר

1. **מומנטום אקסטרים (80+)** - דרוש מעקב צמוד, תנועות מהירות
2. **מומנטום גבוה (65-79)** - הזדמנויות טובות, פחות וולטיליות
3. **שלב חדשות עם מומנטום** - קרא את החדשות בפאנל הימני להבנת ההקשר
4. **עקוב אחר שינוי מחיר** - ירוק (+) = עלייה, אדום (-) = ירידה
5. **השתמש ברענון אוטומטי** - אל תפספס הזדמנויות

---

## 📞 תמיכה

נתקלת בבעיה? בדוק:
1. הלוגים ב-`/tmp/backend.log` ו-`/tmp/frontend.log`
2. וודא שכל התלויות מותקנות (`pip install -r requirements.txt`)
3. נקה והתקן מחדש: `rm -rf node_modules && npm install`

---

## 🚀 העתיד

תכונות מתוכננות:
- [ ] אינטגרציה עם API של מחירים בזמן אמת
- [ ] התראות דחיפה למובייל
- [ ] ניתוח טכני אוטומטי
- [ ] רשימת מעקב אישית (Watchlist)
- [ ] היסטוריית מומנטום (גרפים)

---

**בהצלחה במסחר! 📈🚀**
