# SDLC

Clean bootstrap repository for implementing the first working slice of the SDLC.

## Current implementation scope

Only three capabilities are approved for the first implementation cycle:

1. `sdlc project init`
2. `sdlc project requirement add`
3. RAW Requirement Processor

Do not expand the implementation scope unless a current approved specification, an observed failure, or a necessary interface constraint requires it.

## System boundaries

- Fibery owns project, requirements, planning, design, and delivery state.
- Source repositories contain code and code-native artifacts only.
- Global `requirements-export` is installed outside this repository and produces RAW Markdown transport artifacts.
- `sdlc` must use locally authenticated model CLIs through OAuth/subscription login.
- Do not use provider SDK/API calls, direct API keys, or OpenRouter for model execution.
- Model/runtime choice is configurable; OAuth credentials are never stored in this repository.

## Current specs

- `docs/specs/Project-Init-Spec-v0.3.md`
- `docs/specs/Project-Requirement-Add-Spec-v0.2.md`
- `docs/specs/RAW-Requirement-Processor-Decision-v0.1.md`
- `docs/architecture/SDLC-MVP-v0.4-Frozen-Architecture.md`
- `docs/fibery/Fibery-Schema-v0.1.md`
- `docs/runtime/Local-OAuth-Model-Runtime-Spec-v0.1.md`

## Running `sdlc project init`

```bash
uv sync

export FIBERY_HOST=<workspace>.fibery.io
export FIBERY_TOKEN=<api token>
export FIBERY_SPACE=<Space holding the SDLC Databases>
export FIBERY_SPACE_ID=<UUID of that Space>

sdlc project init --name "SDLC" [--code SDLC] [--description "..."]
```

Configuration is read from the environment only; no credentials are stored in
this repository.

Verification:

```bash
uv sync --locked
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

`.python-version` pins 3.12.13 rather than the 3.12.14 named by the shared
Python standard, because the pinned uv (0.11.21) publishes no 3.12.14 download.

## Fibery interface notes

`docs/fibery/Fibery-API-Constraints-v0.1.md` records the Fibery API limits that
shape the implementation, including the fact that sidebar Documents cannot be
nested through the public API.

## Development agents

Claude Code project agents live in `.claude/agents/`.

Project skills:
- Claude Code: `.claude/skills/`
- Codex: `.agents/skills/`

The global `requirements-export` skill is intentionally **not copied into this repository**.

## Project-level Claude/Codex settings

This repository intentionally does not set model, authentication, permission mode, sandbox mode, or edit-approval policy.

- `.claude/settings.json` is empty.
- `.codex/config.toml` contains comments only.

Therefore user/global settings remain in control, including your existing allow-edits behavior.
