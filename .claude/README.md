# Claude Code project configuration

This directory contains project-scoped instructions, agents, and skills only.

`settings.json` is intentionally empty.

Do **not** add project overrides for:
- `permissions`
- `defaultMode`
- model selection
- API/auth environment variables
- OAuth tokens
- provider/base URLs

This preserves the user's global Claude Code settings, including the existing edit-approval mode.

Project instructions belong in `.claude/CLAUDE.md`, rules/agents/skills—not in permission/auth overrides.
