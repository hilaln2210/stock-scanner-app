# Prediction-Market Arbitrage Scanner (Educational)

פרויקט לימוד בלבד: סורק ארביטראז' בשוקי חיזוי עם נתוני mock ו־paper trading. **אין חיבור לפלטפורמות כסף אמיתי, אין פקודות אמיתיות, אין ארנקים.**

---

## מתמטיקה של ארביטראז'

### שוק בינארי (YES/NO)

- בכל תוצאה תקבל 1 יחידה (למשל 1$): או YES משלם 1 ו־NO אפס, או להפך.
- אם **yes_price + no_price < 1**, אפשר לקנות את שני הצדדים במחיר נמוך מ־1 ולקבל 1 בוודאות.
- **רווח נעול (אחוז):**
  \[
  \text{profit}\% = \frac{1 - (p_{yes} + p_{no})}{p_{yes} + p_{no}} \times 100
  \]
  לדוגמה: YES=0.45, NO=0.52 → סה"כ 0.97 → רווח ≈ 3.09%.

### שוק רב־תוצאות (מצ互אי בלעדי)

- יש תוצאות A, B, C… שמכסות את כל האפשרויות, וכל אחת משלמת 1 אם היא מתממשת.
- אם **סכום כל המחירים < 1**, קניית כל התוצאות עולה פחות מ־1 ומחזירה 1 → ארביטראז'.
- **רווח נעול:** אותו עיקרון:  
  \(\text{profit}\% = (1 - \sum p_i) / \sum p_i \times 100\).

---

## זרימת Paper Trading

1. **סריקה:** טעינת `binary_markets.json` ו־`multi_outcome_markets.json`, זיהוי הזדמנויות (סכום מחירים < 1).
2. **סינון:** לפי נזילות מינימלית, spread מקסימלי, ו־edge מינימלי (אחוז רווח צפוי).
3. **בקרת סיכון:** מגבלת הון למסחר בודד, מגבלת מספר פוזיציות פתוחות, ועצירת כניסות חדשות אם ה־drawdown היומי חורג.
4. **סימולציה:** כניסה וירטואלית (הורדת יתרה), רישום פוזיציה; יציאה וירטואלית (החזרת הון + רווח משוער), עדכון PnL.
5. **דשבורד:** הצגת הזדמנויות, כניסות, יציאות ו־PnL נוכחי ב־CLI.

אין שום שליחה של פקודות אמיתיות או חיבור לארנק/API.

---

## מגבלות הפרויקט

- **נתונים:** רק קבצי JSON מקומיים (mock). אין חיבור ל־API של בורסות אמיתיות.
- **מסחר:** רק סימולציה. אין פקודות אמיתיות, אין ארנק, אין blockchain.
- **מימוש רווח:** בסימולציה מניחים שכל ארביטראז' ממומש ברווח הצפוי (מודל מפושט).
- **עלויות/סליפ:** לא מודלינג של עמלות או החלקה.
- **שימוש:** לימוד ומחקר בלבד. לא לשימוש עם כסף אמיתי.

---

## התקנה והרצה

```bash
cd /path/to/Stocks
python3 -m venv arbitrage_scanner/venv
arbitrage_scanner/venv/bin/pip install -r arbitrage_scanner/requirements.txt
```

### ממשק ווב (מומלץ)

**הפעלה רגילה (השרת ייעצר כשסוגרים את הטרמינל):**
```bash
cd /path/to/Stocks
./arbitrage_scanner/run_server.sh
```
או:
```bash
cd /path/to/Stocks
PYTHONPATH=. arbitrage_scanner/venv/bin/uvicorn arbitrage_scanner.api:app --host 127.0.0.1 --port 8765
```

**הפעלה ברקע (השרת ממשיך לרוץ גם אחרי סגירת הטרמינל):**
```bash
cd /path/to/Stocks
nohup env PYTHONPATH=. arbitrage_scanner/venv/bin/uvicorn arbitrage_scanner.api:app --host 127.0.0.1 --port 8765 >> /tmp/arbitrage_scanner.log 2>&1 &
```

ואז לפתוח בדפדפן: **http://127.0.0.1:8765**

בממשק: סריקת שווקים, הרצת סימולציה, איפוס סימולטור, טבלאות הזדמנויות/כניסות/יציאות ו-PnL.

**סריקה אוטומטית ברקע:** השרת סורק את הפולימרקט כל ~90 שניות (ניתן להגדרה ב־config). כשנמצאות הזדמנויות ארביטראז' – נכנס אליהן אוטומטית (כסף דמו) וסוגר; הכניסות והיציאות מופיעות ב"כניסות סימולציה" ו"יציאות סימולציה". הממשק מתעדכן כל 12 שניות. לבדיקה עם נתוני הדגמה: `ARB_BACKGROUND_SOURCE=mock` לפני ההרצה.

### CLI

הרצת הסורק (בלי סימולציה):

```bash
PYTHONPATH=. arbitrage_scanner/venv/bin/python -m arbitrage_scanner.main
```

הרצה עם סימולציה:

```bash
PYTHONPATH=. arbitrage_scanner/venv/bin/python -m arbitrage_scanner.main --simulate --max-entries 3
```

טסטים:

```bash
PYTHONPATH=. arbitrage_scanner/venv/bin/python -m pytest arbitrage_scanner/tests -v
```

---

## מבנה הפרויקט

```
arbitrage_scanner/
├── __init__.py
├── api.py          # FastAPI + מגיש frontend
├── config.py       # סינונים ובקרת סיכון
├── models.py       # BinaryMarket, MultiOutcomeMarket, ArbitrageOpportunity
├── utils.py        # טעינת JSON, לוגינג
├── scanner.py      # זיהוי ארביטראז' בינארי ורב־תוצאות
├── risk.py         # מגבלות סיכון (הון למסחר, פוזיציות, drawdown)
├── simulator.py    # paper trading: יתרה, פוזיציות, PnL
├── main.py         # CLI
├── static/         # ממשק ווב
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── data/
│   ├── binary_markets.json
│   └── multi_outcome_markets.json
├── tests/
│   └── ...
├── requirements.txt
└── README.md
```

---

## רישיון ושימוש

למטרות לימוד בלבד. אין אחריות; אל תשתמש עם כסף אמיתי.
