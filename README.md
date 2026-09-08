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

- `docs/specs/Requirement-Normative-Tree-Binding-v0.1.md` (audit finding A5:
  normative child Documents reach Process and Review and are bound by Review,
  Ready and Apply; legacy Root-only evidence is never replayed or certified)

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

### Request pacing and rate limits

Fibery allows 3 requests per second per token and 7 per workspace and answers
HTTP 429 beyond that. Every request the CLI sends, reads and writes on every
endpoint, goes through one client that spaces request starts at least 0.5 s
apart on a monotonic clock, including the first request of each process, so
sequential commands never open with a burst. Only requests explicitly known to
be read-only (schema and entity queries, folder and view queries, document
reads) are retried after a 429, at most 3 attempts in total with bounded
backoff inside a 10 s wait budget, honouring a valid `Retry-After` and failing
rather than retrying early when the server asks for more. A mutation that
receives a 429, a timeout or a dropped connection is attempted once and
reported; rerunning the command resumes from durable state through the
existing recovery paths, because the transport cannot prove a rejected write
was never applied.

Pacing is per process. Simultaneous SDLC commands and unrelated clients share
the workspace limits without coordination: run one SDLC command at a time per
workspace. Pacing adds waits; it does not make read-then-write checks atomic.

Transport diagnostics name the endpoint family, HTTP status, operation
category and attempt count, or a JSON-RPC integer code. Response bodies,
vendor error names and messages, request paths, headers and exception text
are never relayed, because they can echo requirement prose or a document
secret. Result codes, created object ids and the confirmed-versus-uncertain
distinction that the recovery paths rely on are unaffected.

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

The script runs each runtime's status command through the runtime's own
validator and prints SDLC-authored summaries only, never the account, email,
organization or raw CLI output. It marks Codex as authenticated but not
eligible for SDLC reasoning execution and launches no model.

Before every model call the runtime proves the login positively: Claude must
report a `claude.ai` login on the first-party API from `claude auth status
--json`; Codex must print its own `Logged in using ChatGPT` line from
`codex login status`. Anything else, including a logged-out status with exit
code 0, an API-key or Console login, third-party provider routing, or
unreadable output, fails the run. No configuration key can relax this.

The model runs as a reasoning child, not a coding agent: the processors send
it everything it needs on stdin and take only its answer back. The child gets
an explicit minimal environment (never `FIBERY_TOKEN`, provider API keys or
base-URL overrides), an empty temporary working directory outside the
repository, and the CLI's own per-invocation restrictions. The user's
interactive Claude Code and Codex settings are not changed.

Support matrix, as independently reviewed:

| Runtime | Login check | Reasoning execution |
|---|---|---|
| Claude Code 2.1.260 | verified | supported: tools, MCP, hooks, plugins, skills, web retrieval and subagents removed by supported CLI controls; managed (policy) settings still apply |
| codex-cli 0.146.0 | verified | blocked: the tool boundary failed review, an exec-hosted file reader kept reading local files despite every disabling flag |

A Codex selection still parses, but any model call through it fails with
`RUNTIME_ISOLATION_UNAVAILABLE` before a subprocess starts, and no other
runtime is substituted. This does not make Codex safe; it stops SDLC from
using a path that failed the required boundary. Interactive use of Codex
outside SDLC is unaffected. The restrictions are CLI controls, not OS-level
isolation.

Because the child ignores the user's own CLI settings, an omitted `model` in
`config/sdlc.toml` means the CLI build's default model, not the one chosen
in the user's interactive settings; reproducible runs should set `model`
explicitly. Failure diagnostics name the runtime, the stage and an exit code
or timeout, never the child's output, the prompt or the login status
document. See the runtime specification for the exact policy.

## Comparison context for reasoning

RAW Process, Standard Process and Standard Review send the model the
Project's other Standard Requirements as comparison material: each one's
Requirement ID, Title, Type, State, actual Category (`unspecified` when
unset) and complete current Root Document, in Requirement ID order, with
only Applied peers labelled as approved comparisons. The corpus is bounded
at 100 peers, and the complete assembled model input (instructions, target,
sources, persisted claims, peers and schemas, exactly the text handed to the
runtime, counted in Unicode code points) is bounded at 400,000 characters;
the peer section is checked against the same number early, but the final
check runs on the whole input immediately before the model call. Nothing is
truncated: more than that, or a peer whose identity or Root Document cannot
be established, refuses the run with `COMPARISON_CONTEXT_INCOMPLETE` before
any model call, and a resume that needs no model call is not affected. The
character bound is an application limit, not a token-capacity guarantee.
Review additionally refuses when a Process finding or relation names a
Requirement that is not an included peer. This is Root-Document comparison;
details that live only in child Documents are not covered.

## One RAW invocation at a time

`sdlc project requirement process` holds an OS advisory lock for the RAW it
works on, from before its first read until it finishes or fails. A second
invocation for the same RAW on the same host and OS user returns
`RAW_PROCESSING_IN_PROGRESS` at once, with no model call and no Fibery
access; run it again after the first finishes. The lock files are empty
rendezvous objects under `~/.sdlc/locks` (or `SDLC_LOCK_DIR`), keyed by
workspace and RAW entity id, never by branch or working directory; a process
that dies releases its lock automatically and nothing needs manual cleanup.
This covers cooperating local invocations only: other machines, other OS
users, direct Fibery edits and the other pipeline stages are not coordinated.

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
