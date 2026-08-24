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

exit "$status"
