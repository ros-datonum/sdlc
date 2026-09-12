# SDLC — Claude Code Project Instructions

Implement the project from approved specifications; do not redesign the whole SDLC during coding.

## Current implementation scope

Implemented and independently verified:

1. `sdlc project bootstrap` (outer new-project entry point)
2. `sdlc project init` and `sdlc project requirement add` (deterministic inner primitives)
3. RAW Requirement Processor / corrected RAW decomposition
4. Standard Requirement Process, Review, Ready boundary, deterministic Apply
5. `sdlc worker run` — state-driven dispatcher/runner, Processing Status and reset semantics

Downstream phases (UX/Product Design, Technical Solution Architecture, Delivery
Planning, Development workflow, System Verification, Release Preparation,
Deployment, Post-Deploy Validation) are product roadmap only. **No engine exists
for any of them.**

Current architecture: `docs/architecture/SDLC-MVP-v0.5-Current-Architecture.md`.
Current lifecycle: `docs/architecture/Requirement-Lifecycle-v0.2-Current.md`.

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

## Fibery integration

New Fibery read or write semantics are frozen only after: a deterministic fake plus
tests, a narrow live probe on temporary state, a fake-versus-live comparison, and a
regression for every discrepancy. A green fake is never integration proof.

## Git safety

Unrecognized changes are foreign state. Never discard, reset, clean, or overwrite them.

## Scope discipline

Prefer the smallest implementation satisfying the current approved spec. If the spec is insufficient, surface the gap instead of inventing architecture.
