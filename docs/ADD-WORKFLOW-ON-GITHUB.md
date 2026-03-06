# הוספת Workflow ל-GitHub (דיפלוי אוטומטי ל-Render)

בגלל מגבלת הרשאות, קובץ ה-Action לא נדחף אוטומטית. כדי ש-**בכל push ל-master** יופעל דיפלוי ב-Render:

## שלב 1: Deploy Hook ב-Render

1. [dashboard.render.com](https://dashboard.render.com) → **stock-scanner-app** → **Settings**
2. גללי ל־**Deploy Hook** → **Create Deploy Hook** (או העתיקי את ה-URL הקיים)
3. העתיקי את ה-URL (במבנה: `https://api.render.com/deploy/srv/...?key=...`)

## שלב 2: סוד ב-GitHub

1. [github.com/hilaln2210/stock-scanner-app](https://github.com/hilaln2210/stock-scanner-app) → **Settings** → **Secrets and variables** → **Actions**
2. **New repository secret**: Name = `RENDER_DEPLOY_HOOK_URL`, Value = ה-URL מ-Render

## שלב 3: יצירת קובץ ה-Workflow ב-GitHub

1. ב-GitHub: **Add file** → **Create new file**
2. בשם הקובץ הקלידי: `.github/workflows/deploy-render.yml`
3. הדביקי את התוכן הבא (כולל השורות מההתחלה עד הסוף):

```yaml
name: Deploy to Render

on:
  push:
    branches: [master]
  workflow_dispatch:

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger Render Deploy
        run: |
          if [ -z "$RENDER_DEPLOY_HOOK_URL" ]; then
            echo "::warning::RENDER_DEPLOY_HOOK_URL not set."
            exit 0
          fi
          echo "Triggering Render deploy..."
          curl -f -X POST "$RENDER_DEPLOY_HOOK_URL"
          echo "Deploy triggered."
        env:
          RENDER_DEPLOY_HOOK_URL: ${{ secrets.RENDER_DEPLOY_HOOK_URL }}
```

4. **Commit new file**

מעכשיו בכל push ל-**master** ה-Action ירוץ ויפעיל דיפלוי ב-Render.
