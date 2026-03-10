#!/bin/bash
# Sync worktree edits to the actual project directory
# Run this after any code changes to ensure servers pick up updates

WORKTREE="/home/hila/.cursor/worktrees/Stocks/rwe"
PROJECT="/home/hila/Desktop/Stocks"

echo "🔄 Syncing worktree → project..."

# Backend app code
rsync -av --delete \
  --exclude="__pycache__" --exclude="*.pyc" --exclude=".env" \
  "$WORKTREE/backend/app/" "$PROJECT/backend/app/"

# Backend data files (portfolio state — don't delete, only update newer)
rsync -av "$WORKTREE/backend/data/" "$PROJECT/backend/data/" 2>/dev/null

# Frontend source
rsync -av --delete \
  --exclude="node_modules" --exclude="dist" --exclude=".env" \
  "$WORKTREE/frontend/src/" "$PROJECT/frontend/src/"

# Frontend config files
cp "$WORKTREE/frontend/vite.config.js" "$PROJECT/frontend/vite.config.js" 2>/dev/null

echo "✅ Sync complete!"
