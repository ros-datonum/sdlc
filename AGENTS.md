# SDLC — Codex Project Instructions

## Scope

Implement only approved specifications under `docs/specs/` and the frozen architecture under `docs/architecture/`.

Current implementation scope:

1. `sdlc project init`
2. `sdlc project requirement add`
3. RAW Requirement Processor

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
