#!/bin/bash
# מפעיל את שרתי Stocks כ־systemd user services — עם אתחול אוטומטי במקרה של קריסה.
# הרצה: ./scripts/start-servers-forever.sh
# אחרי ההרצה: השרתים יופעלו וימשיכו לרוץ (ויתחילו מחדש אם ייפלו).

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
USER_SYSTEMD="$HOME/.config/systemd/user"
NODE_DIR="$(dirname "$(command -v npm 2>/dev/null || echo '/usr/bin')")"
NPM_FULL="${NODE_DIR}/npm"
mkdir -p "$USER_SYSTEMD"

# יצירת קבצי service עם נתיבי הפרויקט
sed "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" "$PROJECT_ROOT/scripts/systemd/stocks-backend.service" > "$USER_SYSTEMD/stocks-backend.service"
sed -e "s|{{PROJECT_ROOT}}|$PROJECT_ROOT|g" -e "s|{{NODE_DIR}}|$NODE_DIR|g" -e "s|{{NPM_FULL}}|$NPM_FULL|g" "$PROJECT_ROOT/scripts/systemd/stocks-frontend.service" > "$USER_SYSTEMD/stocks-frontend.service"

# lingering = שירותי user ימשיכו לרוץ אחרי התנתקות מהמערכת
if command -v loginctl &>/dev/null; then
  loginctl enable-linger "$USER" 2>/dev/null || true
fi

systemctl --user daemon-reload
systemctl --user enable stocks-backend.service stocks-frontend.service
systemctl --user start stocks-backend.service stocks-frontend.service

echo ""
echo "✅ שרתי Stocks רצים כ־systemd (עם אתחול אוטומטי במקרה של קריסה)."
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:3000"
echo ""
echo "פקודות שימושיות:"
echo "   סטטוס:    systemctl --user status stocks-backend stocks-frontend"
echo "   עצירה:    systemctl --user stop stocks-backend stocks-frontend"
echo "   התחלה:    systemctl --user start stocks-backend stocks-frontend"
echo "   לוגים:    journalctl --user -u stocks-backend -u stocks-frontend -f"
echo ""
