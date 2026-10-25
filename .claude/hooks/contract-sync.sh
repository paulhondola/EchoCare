#!/bin/sh
# Stop: endpoint code changed but 04-interfaces.md did not (AGENTS.md "Contract changes move together").
# Exit 2 sends Claude back once to update the spec and clients, or to say why not.
# ponytail: checks uncommitted and untracked files only; a change committed mid-session slips through.
in=$(cat)
[ "$(printf '%s' "$in" | jq -r '.stop_hook_active')" = true ] && exit 0
cd "$CLAUDE_PROJECT_DIR" || exit 0
changed=$(git diff --name-only HEAD; git ls-files -o --exclude-standard)
printf '%s\n' "$changed" | grep -qE '^backend/app/.*/(router|schemas)\.py$' || exit 0
printf '%s\n' "$changed" | grep -qx 'docs/specs/echocare/04-interfaces.md' && exit 0
echo "Endpoint code changed but docs/specs/echocare/04-interfaces.md did not. Update it and the clients that call it (android/app/.../Api.kt, dashboard/src/) in this change, or tell the user why the contract is unchanged." >&2
exit 2
