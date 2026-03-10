#!/usr/bin/env bash
# מריץ את שרת האפליקציה (ממשק + API). לפתוח בדפדפן: http://127.0.0.1:8765/
cd "$(dirname "$0")/.."
export PYTHONPATH=.
exec arbitrage_scanner/venv/bin/uvicorn arbitrage_scanner.api:app --host 127.0.0.1 --port 8765
