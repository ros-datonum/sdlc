#!/usr/bin/env bash
set -u

status=0

echo "== Claude Code =="
if command -v claude >/dev/null 2>&1; then
  if ! claude auth status --text; then
    echo "Claude Code is installed but not authenticated."
    status=1
  fi
else
  echo "claude executable not found."
  status=1
fi

echo
echo "== Codex =="
if command -v codex >/dev/null 2>&1; then
  if ! codex login status; then
    echo "Codex is installed but not authenticated."
    status=1
  fi
else
  echo "codex executable not found."
  status=1
fi

echo
echo "Note: SDLC runtime requires subscription/OAuth CLI authentication."
echo "It must not fall back to API keys or OpenRouter."
echo "Authenticated is not the same as eligible: Codex is currently blocked for"
echo "SDLC reasoning execution (RUNTIME_ISOLATION_UNAVAILABLE) because its tool"
echo "boundary failed review on codex-cli 0.146.0. Claude Code executes."

exit "$status"
