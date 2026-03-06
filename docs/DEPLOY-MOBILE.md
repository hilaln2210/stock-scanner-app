# אפליקציה בנייד בלי תלות במחשב

**האפליקציה לנייד היא אותה אפליקציה** — הפרונט (React) שמוגדר כ־PWA. כשפותחים מהטלפון או מוסיפים למסך הבית, זה אותו קוד ואותו ממשק.

כדי שהאפליקציה בנייד תעבוד **בלי שהמחשב האישי יהיה דלוק**, צריך לפרוס אותה לשרת שתמיד זמין (ענן או VPS). אחרי הפריסה — פותחים מהנייד את הכתובת של השרת, ומוסיפים למסך הבית (PWA).

## איך זה עובד

| סוג הרצה | נייד עובד בלי מחשב? |
|----------|----------------------|
| הכל רץ על המחשב (localhost) | ❌ לא — כשהמחשב כבוי הנייד לא מגיע לשרת |
| פריסה ל־Render / Railway / VPS | ✅ כן — השרת בענן דלוק 24/7, הנייד מתחבר אליו |

## אפשרויות פריסה

### 1. Render.com (מומלץ להתחלה)

1. צור חשבון ב־[render.com](https://render.com).
2. **New → Web Service**, חבר את ה-repo של הפרויקט.
3. הגדר:
   - **Build Command:** (השאר ריק — משתמשים ב־Docker)
   - **Dockerfile Path:** `./Dockerfile`
   - **Instance Type:** Free (או בתשלום אם צריך יותר משאבים)
4. ב־**Environment** הוסף את משתני הסביבה מהמחשב (מפתחות API, Finviz, Telegram וכו') — העתק מ־`backend/.env`.
5. אחרי ה־deploy תקבל כתובת כמו: `https://stock-scanner-xxxx.onrender.com`.
6. **בנייד:** פתח בדפדפן את הכתובת הזו → תפריט → "הוסף למסך הבית". מעכשיו האפליקציה זמינה מהנייד בלי שהמחשב דלוק.

קובץ `render.yaml` בפרויקט מתאים ל־Render; אפשר גם לייבא אותו כ־Blueprint.

### 2. Railway

1. [railway.app](https://railway.app) → New Project → Deploy from GitHub.
2. בחר את ה-repo; Railway יזהה את ה־Dockerfile.
3. הוסף Environment Variables (כמו ב־`.env`).
4. אחרי הפריסה תקבל URL — פתח אותו בנייד והוסף למסך הבית.

### 3. שרת משלך (VPS) עם Docker

```bash
# על השרת (למשל Ubuntu)
git clone <your-repo> && cd Stocks
# העתק .env ל-backend/.env והגדר משתנים
docker compose up -d --build
```

אחר כך הגדר דומיין (או IP) שמצביע לשרת, ופתח מהנייד את `https://your-domain.com`.

## משתני סביבה חשובים בפריסה

העתק מהמחשב את כל מה ש־`backend/.env` משתמש בו, ובפרט:

- `GROQ_API_KEY` (בוט טלגרם)
- `GEMINI_API_KEY` (Smart Portfolio Brain)
- `FINVIZ_EMAIL` / `FINVIZ_PASSWORD` (אם יש Elite)
- `TELEGRAM_BOT_TOKEN` / `TELEGRAM_CHAT_ID` (התראות)
- כל מפתח נוסף שהאפליקציה צריכה

ב־Render/Railway מוסיפים אותם ב־Environment / Secrets.

## סיכום

- **במחשב:** מתאים לפיתוח ובדיקות; הנייד יכול להתחבר רק כשהמחשב דלוק ובאותה רשת.
- **בענן (Render/Railway/VPS):** השרת דלוק 24/7 → **האפליקציה בנייד לא תלויה במחשב** — פותחים את כתובת השרת בנייד ומוסיפים למסך הבית.
