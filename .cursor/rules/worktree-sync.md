---
description: CRITICAL — Worktree sync rule for this project
globs: **/*
alwaysApply: true
---

# Worktree Sync Rule

This project uses Cursor git worktrees. Files edited in the workspace (`/home/hila/.cursor/worktrees/Stocks/rwe/`) are NOT the same files the dev servers use (`/home/hila/Desktop/Stocks/`).

## MANDATORY after ANY file edit:

After editing files, ALWAYS sync them to the actual project directory by running:

```bash
bash /home/hila/Desktop/Stocks/sync-worktree.sh
```

Or manually copy the specific edited file:
```bash
cp /home/hila/.cursor/worktrees/Stocks/rwe/<path> /home/hila/Desktop/Stocks/<path>
```

## Servers run from:
- **Backend**: `/home/hila/Desktop/Stocks/backend/` (uvicorn on port 8000)
- **Frontend**: `/home/hila/Desktop/Stocks/frontend/` (vite dev on port 3000)

## Key directories to sync:
- `backend/app/` — all Python source code
- `backend/app/services/` — AI brain, portfolio, alerts, telegram bot
- `backend/app/api/` — API routes
- `backend/app/scrapers/` — Finviz scrapers
- `backend/data/` — portfolio state (smart_portfolio.json, etc.)
- `frontend/src/` — all React components
- `frontend/vite.config.js` — build configuration
