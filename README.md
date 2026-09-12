# SDLC

Fibery-backed SDLC tooling. This repository implements the corrected Requirement
foundation, the state-driven Requirement lifecycle, and project bootstrap.

## Current implementation scope

Implemented and independently verified:

```text
project bootstrap                     sdlc project bootstrap
RAW Requirement ingestion             sdlc project requirement add
corrected RAW decomposition           RAW Requirement Processor
Standard Requirement Process
Standard Requirement Review
Ready human decision boundary
deterministic Standard Apply
state-driven dispatcher/runner        sdlc worker run
Processing Status / reset semantics
```

Architecture, delivery planning, development, verification, release, deployment
and post-deploy validation remain the product roadmap in
`docs/architecture/SDLC-MVP-v0.5-Current-Architecture.md`. **No engine exists for
any of them**, and nothing here generates architecture, backlogs, Epics,
Stories, Tasks, releases or deployments.

Do not expand the implementation scope unless a current approved specification,
an observed failure, or a necessary interface constraint requires it.

## Requirement abstraction

```text
Requirement
= WHAT must be true

Technical Solution Architecture
= HOW the approved Requirement is satisfied

Delivery Planning
= solution-specific executable decomposition

Task
= concrete code / configuration / test / deployment work
```

Authority: `docs/specs/Standard-Requirement-Abstraction-v0.2.md`.

A Requirement normally stays true when the implementation is replaced by a
different valid solution. The one exception, which is not simplified away: **a
technical mechanism explicitly mandated by the source may remain
Requirement-level truth**, recorded as a Constraint. "Requirements can never
contain technical detail" is the wrong rule.

## System boundaries

- Fibery owns canonical Requirements, Requirement Documents and lifecycle State.
- Source repositories contain code and code-native artifacts, plus project-local
  SDLC participation metadata and non-canonical project context.
- Global `requirements-export` is installed outside this repository and produces
  RAW Markdown transport artifacts.
- `sdlc` must use locally authenticated model CLIs through OAuth/subscription
  login. No provider SDK/API calls, API keys or OpenRouter.
- Model/runtime choice is configurable; OAuth credentials are never stored here.

## Starting a new project

The normal entry point is one command:

```bash
sdlc project bootstrap \
  --name "<Project Name>" \
  --requirements <RAW_REQUIREMENTS_FILE.md> \
  --context <PROJECT_CONTEXT_FILE.md> \
  [--target <PROJECT_DIRECTORY>] \
  [--code <PROJECT_CODE>] \
  [--description "..."]
```

Both exported artifacts come from one `requirements-export` session. `--target`
defaults to the current directory.

Verified result:

```text
consumer repository:
  .sdlc/project.yaml
  .sdlc/project-context.md
  AGENTS.md
  .claude/CLAUDE.md

Fibery:
  Project
  initial Raw Requirement
  State = Draft
```

**Bootstrap stops there.** It does not process the Requirement, invoke a model,
or start any worker. A human decides when the RAW moves `Draft -> Process`.

Rerunning the same command with the same inputs is safe: compatible managed
files are reused byte-for-byte and the result is
`PROJECT_ALREADY_BOOTSTRAPPED` with no duplicate Project or Requirement. An
incompatible existing managed file stops the attempt before anything is
created.

### Consumer project template

Bootstrap manages exactly four paths:

```text
.sdlc/project.yaml
.sdlc/project-context.md
AGENTS.md
.claude/CLAUDE.md
```

It does **not** create:

```text
.codex/config.toml
.claude/settings.json
.agents/
.claude/agents/
.claude/skills/
.agents/skills/
.env
a copy of the RAW requirements artifact
a local canonical Requirements mirror
```

The descriptor and context are project-local metadata and non-canonical
context. They never compete with Fibery as Requirement truth, and bootstrap
never overrides the user's global model, authentication, approval, sandbox or
edit-policy settings.

Contracts: `docs/architecture/Project-Bootstrap-Contract-v0.1.md`,
`docs/rewrite/RW-B01-Template-Manifest-v0.1.md`.

### Inner primitives

These remain directly supported deterministic primitives, and bootstrap reuses
them internally:

```bash
sdlc project init --name "<Project Name>" [--code <CODE>] [--description "..."]
sdlc project requirement add --project <CODE_OR_NAME> --source <RAW_FILE.md>
```

Use them for admin and incremental work. `project requirement add` is the
normal primitive for adding **another** RAW source to an existing Project —
re-bootstrapping is not required for that. When you have both exported
artifacts and are starting a new project, use `project bootstrap` rather than
running these two by hand.

Both are deterministic and invoke no model.

## Requirement lifecycle control

Lifecycle decisions are Requirement State transitions in Fibery
(`docs/architecture/Requirement-Lifecycle-Ownership-v0.2.md`). The human, or an
authorized assistant acting on the human's explicit instruction, makes exactly
these:

```text
RAW       Draft -> Process    start processing this RAW source
Standard  Ready -> Process    rework: start a new Standard Process cycle
Standard  Ready -> Apply      approve: apply the exact reviewed state
```

Every other normal transition is machine-owned: RAW `Process -> Review`, the
inherited Standard `Draft -> Process` for candidates of an authorized RAW cycle,
Standard `Process -> Review -> Ready`, and `Apply -> Applied`. A Review verdict,
`BLOCKING` included, is evidence for the human at `Ready`, never a decision.
`State = Apply` is the only approval signal Apply consumes, and Apply
revalidates the reviewed evidence however that State was reached.

The complete current flow, Processing Status values, reset targets and the
Process → Review handoff are in
`docs/architecture/Requirement-Lifecycle-v0.2-Current.md`.

### Running the worker

State-driven execution of the machine-owned stages is `sdlc worker run`
(`docs/architecture/Requirement-State-Worker-Contract-v0.1.md`).

```text
sdlc worker run [--poll-interval-seconds N]   default 5, minimum 1; Ctrl-C stops
```

Before normal runner operation the Fibery workspace must already have the
verified `Processing Status` field and its reset automation configured
(`docs/fibery/Worker-Runner-Setup-v0.1.md`). The runner validates the field and
its options at startup; **it does not create the automation**, so the operator
must verify that rule in the workspace before production use.

The runner is one foreground process per workspace. It polls every Project for
Requirements at a machine route (`Raw + Process`, `Standard + Process`,
`Standard + Review`, `Standard + Apply`) whose Processing Status is
`Not Processed`, and runs the dispatcher
(`src/sdlc/requirement_dispatcher.py`) for one of them at a time. It is an
executor, not lifecycle authority, and it is not a distributed orchestration
system.

Without the runner, automatic machine progression simply stops. Requirements
stay where they are and nothing is lost. An operator may deliberately use the
bounded admin/recovery capabilities below, but doing so does not change
lifecycle ownership: the human State transition is still the decision, and the
worker still owns the machine stage.

The end-to-end lifecycle is independently verified in
`docs/rewrite/RW-O04-Verification-v0.1.md`.

## Admin / diagnosis / recovery commands

These exist for development, diagnosis, recovery and explicit admin use. They
are **not** a parallel normal workflow and they create no lifecycle authority:

```text
sdlc project requirement process   --requirement <RAW id>        RAW in Process
sdlc project requirement normalize --requirement <Standard id>   Standard in Process
sdlc project requirement review    --requirement <Standard id>   Standard in Review
sdlc project requirement apply     --requirement <Standard id>   Standard in Apply
```

`sdlc project requirement approve` and `rework` are admin/compatibility
shortcuts for the two Ready transitions. Neither is required: a direct
`Ready -> Apply` or `Ready -> Process` in Fibery means the same thing and needs
no command. `approve` checks the reviewed evidence first and requires
`--acknowledge-verdict` for a `NEEDS_WORK` or `BLOCKING` verdict; that is a
safety check of the command, not approval authority, and it cannot make stale
evidence applicable.

## Configuration and verification

```bash
uv sync

export FIBERY_HOST=<workspace>.fibery.io
export FIBERY_TOKEN=<api token>
export FIBERY_SPACE=<Space holding the SDLC Databases>
export FIBERY_SPACE_ID=<UUID of that Space>
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

## Current specs and contracts

```text
docs/architecture/SDLC-MVP-v0.5-Current-Architecture.md
docs/architecture/Requirement-Lifecycle-v0.2-Current.md
docs/architecture/Requirement-Lifecycle-Ownership-v0.2.md
docs/architecture/Requirement-State-Worker-Contract-v0.1.md
docs/architecture/Project-Bootstrap-Contract-v0.1.md
docs/specs/Standard-Requirement-Abstraction-v0.2.md
docs/specs/Project-Init-Spec-v0.3.md
docs/specs/Project-Requirement-Add-Spec-v0.3.md
docs/specs/Standard-Requirement-Process-Spec-v0.1.md
docs/specs/Standard-Requirement-Review-Spec-v0.1.md
docs/specs/Standard-Requirement-Ready-Spec-v0.1.md
docs/specs/Standard-Requirement-Apply-Spec-v0.1.md
docs/specs/RAW-Requirement-Processor-Decision-v0.1.md
docs/fibery/Fibery-Schema-v0.1.md
docs/fibery/Worker-Runner-Setup-v0.1.md
docs/runtime/Local-OAuth-Model-Runtime-Spec-v0.1.md
```

`docs/specs/Requirement-Normative-Tree-Binding-v0.1.md` (audit finding A5:
normative child Documents reach Process and Review and are bound by Review,
Ready and Apply; legacy Root-only evidence is never replayed or certified).

Historical, retained and not rewritten:
`docs/architecture/SDLC-MVP-v0.4-Frozen-Architecture.md`,
`docs/architecture/Requirement-Lifecycle-v0.1-Checkpoint.md`.

## Fibery interface notes

`docs/fibery/Fibery-API-Constraints-v0.1.md` records the Fibery interface
behaviour verified against the workspace.

Requirement lifecycle placement is the Requirement's Type and State. Root
Documents are contained by their Requirement and carry no `fibery/Folder`;
no command creates, resolves or moves a Folder (the earlier
`Requirements/{Raw,Draft,Approved}` tree is retired, and Documents that still
carry a Folder from that time are treated as inert). Human navigation is a
one-time workspace configuration in the Fibery UI: a Smart Folder over
Projects with mirrored context views RAW (`Type = Raw`), Draft
(`Type = Standard AND State != Applied`) and Approved
(`Type = Standard AND State = Applied`). The runtime neither creates nor
requires it.

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

The reasoning stages — RAW Process, Standard Process and Standard Review — are
the capabilities allowed to invoke a model. Execution goes through the user's
locally authenticated `claude` or `codex` CLI; there is no API-key,
provider-SDK or OpenRouter path, and no fallback. Apply is deterministic and
model-free.

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

The worker runner has its own workspace-scoped guard: one cooperating
`sdlc worker run` per workspace on one host/user. Multi-host exclusion is
unsupported.

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
