# סנכרון הפרויקט המקומי עם GitHub ו-Render

## מה בדקתי

### ב-GitHub ([hilaln2210/stock-scanner-app](https://github.com/hilaln2210/stock-scanner-app))

- **ענף `master`** מכיל גרסה **מצומצמת**:
  - בקוד: `const tabs = APP_TABS` — רק **2 טאבים** (סורק בסיסי + חדשות)
  - **AIAssistant** עדיין מיובא ומוצג
  - קומיט אחרון: "App: only סורק בסיסי + חדשות (remove all other tabs)"

### ב-Render

- השירות **stock-scanner-app** מחובר ל־**hilaln2210/stock-scanner-app**, ענף **master**
- כל דיפלוי בונה את הקוד מ-GitHub — ולכן האתר מציג את הגרסה עם 2 טאבים + AI Assistant

### בפרויקט המקומי (Desktop/Stocks)

- **7 טאבים**, **בלי** AI Assistant, **עם** SmartPortfolioDashboard, גרסה v2
- הקוד הזה **לא** נמצא ב־`hilaln2210/stock-scanner-app` — הוא רק אצלך במחשב

---

## איך לגרום ל-Render להציג את אותה אפליקציה

צריך שהקוד **המקומי** יהיה ב־GitHub, כדי ש-Render יבנה ממנו.

### אופציה א: הפרויקט המקומי מחובר כבר ל־stock-scanner-app

**בפרויקט שלך** ה-remote הוא כבר `hilaln2210/stock-scanner-app` והענף הוא **master**. אז:

```bash
cd /home/hila/Desktop/Stocks
git add .
git commit -m "Full app: 7 tabs, no AI Assistant, v2, SmartPortfolio"
git push origin master
```

אחרי ה-push: אם ב-Render מופעל **Auto-Deploy**, הדיפלוי יתחיל אוטומטית. אחרת — Render → Manual Deploy.

### אופציה ב: הפרויקט המקומי לא מחובר ל־stock-scanner-app

אם ה-remote הוא repo אחר (או אין remote):

```bash
cd /home/hila/Desktop/Stocks
git remote -v
# אם צריך להוסיף:
git remote add origin https://github.com/hilaln2210/stock-scanner-app.git
git push -u origin main
# אם Render צופה ב-master:
git push origin main:master
```

---

## אימות

אחרי דיפלוי מוצלח ב-Render:

- פתחי את https://stock-scanner-app-dmeb.onrender.com/
- אמורים להופיע: **STOCK SCANNER v2**, **7 טאבים**, **בלי** כפתור AI Trading Assistant.
