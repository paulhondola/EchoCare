#!/bin/sh
# PreToolUse on Edit|Write: refuse to change a migration that is already on origin/main.
# Staging has applied it, so an edit would split staging's schema from the code (backend/AGENTS.md).
# ponytail: checks origin/main as last fetched; a teammate's unfetched push slips through until `git fetch`.
f=$(jq -r '.tool_input.file_path // empty')
case "$f" in
  */backend/alembic/versions/*.py)
    rel=${f#"$CLAUDE_PROJECT_DIR"/}
    if git -C "$CLAUDE_PROJECT_DIR" cat-file -e "origin/main:$rel" 2>/dev/null; then
      echo "$rel is on main and frozen: staging has applied it. Write a new migration instead." >&2
      exit 2
    fi
    ;;
esac
exit 0
