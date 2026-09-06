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
- `docs/specs/Project-Requirement-Add-Spec-v0.3.md`
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

sdlc project requirement add --project SDLC --source raw-requirements-topic.md
```

`project requirement add` ingests one artifact produced by the global
`requirements-export` skill. It is deterministic and invokes no model.

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

`docs/fibery/Fibery-API-Constraints-v0.1.md` records the Fibery interface
behaviour verified against the workspace.

Folders are real and nestable. `/api/views/json-rpc` exposes `query-folders`,
`create-folders`, `update-folders` and `delete-folders`; a Folder nests under
another through `fibery/Parent Folder`, and a Document is placed in a Folder
through `fibery/Folder`. These Folder methods are not covered by the published
Views API reference.

Folder names are not unique: siblings may share a name. Folders created by a
run are therefore read back by their own id, never by name.

## Model runtime

The RAW Requirement Processor is the first capability allowed to invoke a model.
Execution goes through the user's locally authenticated `claude` or `codex` CLI;
there is no API-key, provider-SDK or OpenRouter path, and no fallback.

Runtime and model selection live in `config/sdlc.toml` (TOML, read with stdlib
`tomllib`, so the project keeps zero runtime dependencies). Precedence:

```text
explicit run override -> role config -> project default -> local CLI default model
```

Check local authentication with:

```bash
bash scripts/check-local-model-auth.sh
```

## Recovering an empty Result Document

Each model-backed command creates its Result as a child Document first and
writes the body second. If the body write fails after the create succeeded,
Fibery holds a named, correctly placed, empty Document. The failing run
reports it: its `created` list names the Document as *created*, not
*persisted*, and the details give the exact id. An ordinary retry refuses
that shell with `INVALID_PROCESSING_RESULT` or `INVALID_REVIEW_RESULT`,
names it, and calls no model.

To complete the shell in place, name it explicitly:

```bash
sdlc project requirement process   --requirement <RAW id>      --recover-empty-result <document id>
sdlc project requirement normalize --requirement <Standard id> --recover-empty-result <document id>
sdlc project requirement review    --requirement <Standard id> --recover-empty-result <document id>
```

This runs the model again on the current input and writes into the same
Document, keeping its name, parent and reserved iteration. It does not
reconstruct the earlier response. It refuses, without writing, when the
Document is not that Requirement's own current Result shell, when its body is
not empty, when a newer Result already exists above it, when a Review Result
already reviewed that iteration, when a RAW Requirement already produced
candidates, or when the Requirement's Type, State, Requirement ID or attached
Root Document changed, or another actor filled or renamed the shell, while the
model was running. Those are fresh reads taken immediately before the write: a
change visible then is refused; a change that lands between that check and the
write is not detected. A valid Result named by mistake is never overwritten:
run the ordinary command instead.

This is for an observed create-success, body-write-failure. Emptiness alone
cannot prove a Document was never completed and cleared later, and explicit
selection is not multi-writer safety: do not recover while another run may be
working on the same item.

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
