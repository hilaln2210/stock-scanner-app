# שרתי Stocks — הרצה קבועה (בלי ליפול)

השרתים רצים כ־**systemd user services** עם `Restart=always`: אם תהליך נופל, systemd מפעיל אותו מחדש אוטומטית.

## הפעלה פעם אחת (הגדרה + התחלה)

```bash
./scripts/start-servers-forever.sh
```

אחרי זה:
- **Backend:** http://localhost:8000  
- **Frontend:** http://localhost:3000  

השירותים מופעלים גם בהתחברות הבאה (enable).

## פקודות שימושיות

| פעולה | פקודה |
|--------|--------|
| סטטוס | `systemctl --user status stocks-backend stocks-frontend` |
| עצירה | `systemctl --user stop stocks-backend stocks-frontend` |
| התחלה | `systemctl --user start stocks-backend stocks-frontend` |
| לוגים חיים | `journalctl --user -u stocks-backend -u stocks-frontend -f` |

לוגים נשמרים גם ב־`backend/server.log` ו־`frontend/frontend.log`.

## איך זה עובד

- `Restart=always` — אם השרת קורס, systemd מפעיל אותו שוב אחרי 3 שניות.
- `WantedBy=default.target` — השירותים מופעלים אוטומטית בהתחברות.
- `loginctl enable-linger` — שירותי user ממשיכים לרוץ גם אחרי שהמשתמש מתנתק (logout).
