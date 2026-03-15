#!/bin/sh
# Initialize data volume with default files on first run
DATA_DIR=/app/backend/data
DEFAULTS_DIR=/app/backend/data_defaults

if [ -d "$DEFAULTS_DIR" ]; then
  for f in "$DEFAULTS_DIR"/*.json; do
    fname=$(basename "$f")
    if [ ! -f "$DATA_DIR/$fname" ]; then
      echo "[entrypoint] Initializing $fname"
      cp "$f" "$DATA_DIR/$fname"
    fi
  done
fi

exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8080}"
