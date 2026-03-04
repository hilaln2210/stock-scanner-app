# פריסה לענן (24/7)

## PWA + נייד

האפליקציה מוכנה כ־PWA:
- **התקנה על הטלפון:** Chrome → תפריט → "התקן אפליקציה" / Safari → שיתוף → "הוסף למסך הבית"
- **מסך מלא** בלי סרגל דפדפן
- **Service Worker** לעדכונים אוטומטיים

## פריסה ל־Render (חינמי)

1. צור חשבון ב־[render.com](https://render.com)
2. "New" → "Blueprint"
3. חבר את ה־repo (GitHub)
4. Render יזהה את `render.yaml` ויבנה מהדוקר
5. תקבל קישור כמו `stock-scanner.onrender.com`

**הערה:** ה־free tier נרדם אחרי ~15 דקות חוסר פעילות. הפעלה ראשונה תיקח ~30 שניות.

## פריסה ל־Railway

1. צור חשבון ב־[railway.app](https://railway.app)
2. "New Project" → "Deploy from GitHub repo"
3. בחר את הפרויקט – Railway יזהה את ה־Dockerfile
4. הוסף משתנה סביבה: `PORT` (Railway מגדיר אוטומטית)

## הרצה מקומית (לפני פריסה)

```bash
# 1. בניית פרונטנד
cd frontend && npm run build && cd ..

# 2. הרצת backend (משרת גם את הפרונטנד)
cd backend && python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

פתח: http://localhost:8000
