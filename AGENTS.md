# SDLC — Codex Project Instructions

## Scope

Implement only approved specifications under `docs/specs/` and the frozen architecture under `docs/architecture/`.

Current implementation scope — implemented and independently verified:

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

Do not invent downstream SDLC architecture while implementing these capabilities.

## Sources of truth

For implementation behavior, use the newest non-superseded specification in `docs/specs/`.

For Fibery structure, use `docs/fibery/Fibery-Schema-v0.1.md`.

For model execution, use `docs/runtime/Local-OAuth-Model-Runtime-Spec-v0.1.md`.

## Model runtime constraint

The application must invoke locally installed/authenticated `codex` or `claude` CLIs.

Forbidden:
- OpenAI API SDK/model calls
- Anthropic API SDK/model calls
- OpenRouter
- committed API keys/tokens
- project-local OAuth credential storage

Do not change `.codex/config.toml` to set model, auth, approval policy, or sandbox mode.

## Git safety

- Treat unexplained working-tree changes as foreign state.
- Never discard them with reset/checkout/clean.
- Keep changes bounded to the current task.
- Inspect the diff before completion.
- Do not rewrite shared history.

## Design discipline

A new mechanism is admitted only because of:
1. an approved requirement/specification;
2. an observed failure;
3. a necessary interface constraint.

If a specification is ambiguous, report the ambiguity instead of silently widening scope.
