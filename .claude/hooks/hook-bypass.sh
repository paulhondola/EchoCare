#!/bin/sh
# PreToolUse on Bash: ask before a command that skips lefthook (AGENTS.md "Commit with the hooks on").
# ponytail: substring match; a combined short flag like `git commit -nm` slips through.
cmd=$(jq -r '.tool_input.command // empty')
case "$cmd" in
  *--no-verify*|*LEFTHOOK=0*|*"commit -n "*)
    jq -n '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "ask",
      permissionDecisionReason: "Skips the lefthook checks. AGENTS.md allows this only when the user asks."}}'
    ;;
esac
exit 0
