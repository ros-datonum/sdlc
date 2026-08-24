# SDLC — Claude Code Project Instructions

Implement the project from approved specifications; do not redesign the whole SDLC during coding.

## Current implementation scope

1. `sdlc project init`
2. `sdlc project requirement add`
3. RAW Requirement Processor

## Required references

Before implementing a capability, read:
- the corresponding file in `docs/specs/`;
- `docs/fibery/Fibery-Schema-v0.1.md`;
- `docs/runtime/Local-OAuth-Model-Runtime-Spec-v0.1.md` when model execution is involved.

## Runtime constraint

Model calls from the SDLC application must go through locally installed Claude Code or Codex CLI sessions authenticated locally via subscription/OAuth.

Do not introduce:
- Anthropic API calls or SDK model execution;
- OpenAI API calls or SDK model execution;
- OpenRouter;
- project API keys/tokens;
- provider base URL overrides.

Model selection belongs to the SDLC runtime config and per-run overrides, not `.claude/settings.json`.

## Project settings

Do not modify project settings to override the user's global permission/edit mode.

In particular, do not add `permissions`, `defaultMode`, or bypass-permission flags to project config.

## Git safety

Unrecognized changes are foreign state. Never discard, reset, clean, or overwrite them.

## Scope discipline

Prefer the smallest implementation satisfying the current approved spec. If the spec is insufficient, surface the gap instead of inventing architecture.
