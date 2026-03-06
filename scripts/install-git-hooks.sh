#!/bin/bash
# מתקין את ה-git hooks מהפרויקט (דחיפה אוטומטית אחרי commit)
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
HOOKS_SRC="$SCRIPT_DIR/git-hooks"
HOOKS_DEST="$REPO_ROOT/.git/hooks"
cp "$HOOKS_SRC/post-commit.sample" "$HOOKS_DEST/post-commit"
chmod +x "$HOOKS_DEST/post-commit"
echo "✓ הותקן: post-commit (דחיפה אוטומטית ל-origin master אחרי כל commit)"
