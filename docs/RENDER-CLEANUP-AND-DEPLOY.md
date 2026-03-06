# Render: מחיקת כפילויות ועדכון האפליקציה

## אם ב-Render מופיעה "אפליקציה אחרת"

אם בכתובת כמו `https://stock-scanner-app-dmeb.onrender.com/` אתה רואה:
- **רק 2 טאבים** (סורק בסיסי, חדשות) במקום 7
- **כפתור "AI Trading Assistant"** בתחתית

זו **גרסה ישנה**. האפליקציה הנוכחית בפרויקט כוללת 7 טאבים (בריפינג, FDA, סיגנלים, ניתוח יומי, IB, סורק בסיסי, חדשות) ואין בה AI Assistant. כדי ש-Render יציג את **אותה אפליקציה**:

1. **חיבור ל-repo הנכון:** ב-Render → השירות → Settings → Build & Deploy → **Repository** חייב להיות ה-repo של הפרויקט הזה (Stocks), והענף **main** (או ה-branch שאתה עובד עליו).
2. **דיפלוי מחדש:** Manual Deploy → **Clear build cache & deploy** (או דחיפת קומיט ל-GitHub אם יש auto-deploy).
3. **אימות:** אחרי הדיפלוי בדף יופיע **"STOCK SCANNER v2"** בכותרת, 7 טאבים בתפריט, ואין כפתור AI Trading Assistant.

---

## 1. מחיקת כפילויות

ב־Render יש לך **Active (2)** ו־**Suspended (3)** — סה״כ 5 שירותים.

- **למחוק שירות:** Dashboard → Projects → Ungrouped Services → לחץ על **שם השירות** → Settings (או תפריט ⋮) → **Delete Web Service**. אשר מחיקה.
- **כפילויות של Stock Scanner:** אם יש יותר משירות Docker אחד של הסורק (למשל `stock-scanner` ו־`stock-scanner-app` או גרסאות מושעות), השאר **רק אחד** (העדכני) ומחק את השאר.
- **Suspended:** אם בין ה־3 המושעים יש כפילויות או שירותים שלא צריכים — מחק אותם כדי לנקות.

אחרי המחיקה נשאר לך שירות אחד פעיל ל־Stock Scanner (Docker).

---

## 2. עדכון האפליקציה הקיימת (Stock Scanner) — תהליך דיפלוי

**בפרויקט יש GitHub Action** שמפעיל דיפלוי ב-Render בכל push ל־`master`. כדי שזה יעבוד:

### שלב 1: Deploy Hook ב-Render

1. היכנסי ל־[dashboard.render.com](https://dashboard.render.com) → בחרי את השירות **stock-scanner-app**.
2. **Settings** → גללי ל־**Deploy Hook**.
3. לחצי **Create Deploy Hook** (או העתיקי את ה-URL אם כבר קיים).
4. **העתיקי את ה-URL** (נראה כמו `https://api.render.com/deploy/srv/...?key=...`).

### שלב 2: סוד ב-GitHub

1. ב-GitHub: הפרויקט **Stocks** → **Settings** → **Secrets and variables** → **Actions**.
2. **New repository secret**:
   - Name: `RENDER_DEPLOY_HOOK_URL`
   - Value: ה-URL שהעתקת מ-Render (Deploy Hook).

### שלב 3: וידוא ש-Render מחובר ל-repo

1. ב-Render → השירות → **Settings** → **Build & Deploy**.
2. **Repository** חייב להיות ה-repo של הפרויקט (אותו repo ב-GitHub).
3. **Branch:** `master` (או הענף שאת עובדת עליו).
4. מומלץ: **Auto-Deploy** = **Yes** (אז גם Render יבנה מחדש כשיש push, בנוסף ל-Deploy Hook).

### מעכשיו: דיפלוי בתהליך

- **בכל `git push origin master`** — ה-GitHub Action ירוץ ויפעיל את ה-Deploy Hook, ו-Render יתחיל דיפלוי.
- אפשר גם להריץ ידנית: GitHub → **Actions** → **Deploy to Render** → **Run workflow**.

### אם עדיין אין דיפלוי (גיבוי ידני)

1. ב-Render → השירות **stock-scanner-app** → **Manual Deploy** → **Clear build cache & deploy**.
2. או דחיפת קומיט ל־master (אם Auto-Deploy מופעל ב-Render).

---

## 3. וידוא הגדרות השירות

ב־**Environment** של השירות ב־Render וודא שיש את כל משתני הסביבה מ־`backend/.env` (למשל `GROQ_API_KEY`, `GEMINI_API_key`, `FINVIZ_*`, `TELEGRAM_*` וכו'). בלי זה הבוט והסורק לא יעבדו כמו שצריך.

---

**סיכום:** מחק כפילויות/שירותים מיותרים ב־Settings → Delete; לעדכון האפליקציה — דחוף ל־Git ו־Render יעשה deploy, או Manual Deploy מהדאשבורד.
