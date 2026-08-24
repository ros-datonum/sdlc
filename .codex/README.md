# Codex project configuration

`config.toml` intentionally contains no effective settings so global Codex configuration remains authoritative.

In particular this repository must not override:
- model/model provider;
- ChatGPT OAuth authentication;
- approval policy;
- sandbox mode;
- edit permissions.

Project behavior is expressed through root `AGENTS.md` and repo-scoped `.agents/skills/`.

Current Codex repo skill discovery uses `.agents/skills`; skills are not duplicated under `.codex/`.
