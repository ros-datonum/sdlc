# RW-B05 — Live Bootstrap Evidence v0.1

**Status:** COMPLETE  
**Work item:** `RW-B05 — Bootstrap end-to-end test on disposable project`  
**Frozen plan:** `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Live boundary:** `docs/rewrite/RW-B05-Implementation-Boundary-v0.1.md`  
**Baseline:** `99263693322d43362b7bb8f24d8e046de87e18cc`  
**Branch:** `rewrite/rw-b05-live-bootstrap-e2e`  
**Date:** 2026-09-12

RW-B05 is a live acceptance gate, not an implementation item. No production code
and no test code changed on this branch. The only repository artifact is this
document plus the moving plan's RW-B05 implementation/status fields.

## 1. Disposable identity

```text
Project Name: ZZ RW-B05 Bootstrap Probe 0912
Project Code: ZZB05PROBE
```

Chosen to be unmistakably disposable, with an explicit Code as the boundary
prefers (code generation is already covered by B04 deterministic tests).

Before the first mutation, bounded read-only queries (`q/limit 3`, enough to
distinguish 0, 1 and more than 1) proved both were free:

```text
exact Project Name count = 0
Project Code count       = 0
```

No AMR, no SDLC Project, no other existing Project, no production Requirement
and no existing consumer repository took part at any point.

## 2. Temporary local state

All probe state lived in an OS temporary directory outside the `sdlc`
repository, under a session-scoped scratch root:

```text
<tmp>/b05/inputs/raw-requirements.md     synthetic RAW export
<tmp>/b05/inputs/project-context.md      synthetic project context
<tmp>/b05/consumer                       primary target, empty before bootstrap
<tmp>/b05/conflict                       separate failure-probe target
```

The primary target was an existing empty directory (0 entries before the run).
The RAW input was never placed inside the consumer target.

### Export inputs

The RAW artifact satisfies the currently supported transport contract as
implemented by `parse_raw_requirement`, proven locally before any live call:

```text
parse_raw_requirement: SUCCEEDED
title       : Disposable Probe Service Health Status
fingerprint : ad050c15331592fe20e72c45ff1379d55e94dca20d5dd718e7540398492be2ec
```

Its content is disposable probe material only ("a disposable probe service must
expose a health status"). The project context is synthetic non-secret bytes
carrying one distinctive marker line:

```text
project-context.md  bytes=316
sha256=43d3ea9ba111f4916b59e6844010c4d09536696b0e4353dbe35b0808edc3e2e4
```

## 3. Runtime configuration

Process-scoped configuration **was required**.

The operator's persistent `.env` still carries `FIBERY_SPACE_ID` as an empty
value, exactly the condition recorded in the RW-O03 verification. The
repository also loads no `.env` automatically: `sdlc.config` reads the process
environment only, there is no dotenv dependency, no `env-file` setting and no
`.envrc`.

The configured Space id was therefore discovered read-only and injected into
the verification process environment for the CLI invocations only.

Discovery did not rely on a view-name heuristic. The Space id was bound to real
entities: every Document contained by a sampled `SDLC/Requirement` row
(25 of 25) resolves to one `fibery/container-app`, which is precisely the
container a new Root Document write uses.

```text
FIBERY_SPACE_ID = 19c62a00-7a47-11f1-aba7-67039973deac
```

No `.env` file was edited. No Claude/Codex/user-global configuration was
created or modified. This is verification setup, not a product change.

## 4. First live bootstrap (AC1)

The real user-facing CLI was invoked once, through the normal package
execution form. `bootstrap_project()` was not called directly for the success
proof.

```bash
uv run sdlc project bootstrap \
  --name "ZZ RW-B05 Bootstrap Probe 0912" \
  --code "ZZB05PROBE" \
  --requirements <tmp>/b05/inputs/raw-requirements.md \
  --context <tmp>/b05/inputs/project-context.md \
  --target <tmp>/b05/consumer
```

```text
exit code = 0
PROJECT_BOOTSTRAPPED
Project Init: PROJECT_INITIALIZED
Requirement Add: RAW_REQUIREMENT_ADDED
Initial RAW Requirement: ZZB05PROBE-RAW-0089
Created: AGENTS.md, .claude/CLAUDE.md, .sdlc/project.yaml, .sdlc/project-context.md
```

## 5. Local consumer result (AC1, AC2, AC7)

The complete target tree after bootstrap was exactly the managed set and
nothing else:

```text
.claude/
.claude/CLAUDE.md
.sdlc/
.sdlc/project-context.md
.sdlc/project.yaml
AGENTS.md
total entries: 6
```

### Descriptor, under the real B03 parser

`parse_descriptor` succeeded, and every frozen value holds:

```text
version                = 1
project.name           = "ZZ RW-B05 Bootstrap Probe 0912"   (== disposable Name)
project.code           = "ZZB05PROBE"                        (== disposable Code)
fibery.project_code    = "ZZB05PROBE"                        (== project.code)
repository.root        = "."
branch/worktree/merge  = null, null, null
checks                 = []
standards.profile      = null
standards.extensions   = []
```

### Context

`.sdlc/project-context.md` is byte-identical to the supplied export; SHA-256 of
target and input are equal (`43d3ea9b…`).

### Agent guidance

`AGENTS.md` and `.claude/CLAUDE.md` both classify B02 `COMPATIBLE`.

### Excluded paths

None of the following was created: `.codex/config.toml`,
`.claude/settings.json`, `.agents/`, `.claude/agents/`, `.claude/skills/`,
`.agents/skills/`, `.env`. No RAW requirements copy and no Requirements mirror
appears in the target.

### Credentials (AC7)

The verification process held a Fibery token, so its exact value was checked
programmatically against the bytes of all four managed files. The token itself
was never printed.

```text
managed files containing the token value: NONE
literal b'FIBERY_TOKEN' / b'Authorization' / b'Token ': none
```

## 6. Live Fibery result (AC3, AC4)

Read-only bounded queries after bootstrap:

```text
exact Project Name count = 1
Project Code count       = 1
Name and Code resolve to the same entity: yes
```

```text
matching RAW count in this Project = 1   (bounded query, not a first-match helper)
Requirement ID        = ZZB05PROBE-RAW-0089
Type                  = Raw
State                 = Draft
Project relation      = the disposable Project
Source Fingerprint    = ad050c15…  (equals the parsed export fingerprint)
```

### Root Document

```text
Root Document count = 1
document name       = ZZB05PROBE-RAW-0089 — Disposable Probe Service Health Status
content_equivalent(stored, parsed.body) = True
```

Content was read through the existing authenticated document mechanism. The
document secret and the stored body are not recorded here.

## 7. No automatic processing (AC9)

After the first success the disposable RAW was observed for 14 seconds. No
`Draft -> Process` transition was made, and no processor or worker command was
run against it.

```text
Type = Raw   State = Draft   Processing Status = Not Processed
Requirements in the disposable Project = 1   by Type {Raw: 1}
no Standard Requirement derived/produced : yes
documents contained by the RAW           : 1 (the Root Document)
child documents (a Processing Result would be one): 0
```

No `sdlc worker run` process was active on the host during the probe; this was
checked before the first mutation. Draft remained a human boundary regardless.

## 8. Rerun (AC5)

The **same** CLI command was run a second time with identical name, code,
requirements, context and target.

```text
exit code = 0
PROJECT_ALREADY_BOOTSTRAPPED
Project Init: PROJECT_ALREADY_EXISTS
Requirement Add: REQUIREMENT_ALREADY_ADDED
Reused: AGENTS.md, .claude/CLAUDE.md, .sdlc/project.yaml, .sdlc/project-context.md
```

Verified against the pre-rerun snapshot:

```text
all four managed file digests unchanged
target tree still exactly the managed set (6 entries)
Project Name count = 1, Code count = 1, same Project entity id
matching RAW count = 1, same Requirement entity id, same Requirement ID
Root Document count = 1, same document id, no second canonical RAW
RAW State still Draft; no Standard candidates; no Processing Result
```

## 9. Safe live failure probe (AC8)

A separate temporary target was given one conflicting managed file,
`.sdlc/project-context.md`, with bytes deliberately different from the supplied
context. The real CLI was invoked against it with the same disposable identity
and inputs. No live partial write was induced.

```text
exit code = 1 (non-zero)
BOOTSTRAP_CONFLICT
Failed step: preflight managed paths
Details: .sdlc/project-context.md: the existing project context differs from the supplied export
```

Verified afterwards:

```text
conflicting file byte-identical to before (178 bytes, sha256 c61f5fb8…)
bootstrap did not overwrite it
no managed path created: .sdlc/project.yaml, AGENTS.md, .claude/CLAUDE.md, .claude/ all absent
conflict target tree exactly what existed before the probe
live Project Name count = 1, Code count = 1, same Project id
live RAW count = 1, same Requirement entity id and Requirement ID
Type = Raw, State = Draft: no lifecycle State changed
Root Document count = 1, same document id
```

## 10. User-global configuration (AC6)

Safe metadata only was captured before and after the whole probe. Contents were
never read into evidence.

```text
~/.claude/settings.json : present before and after, SHA-256 equal  -> UNCHANGED
~/.codex/config.toml    : present before and after, SHA-256 equal  -> UNCHANGED
```

The repository `.env` was not modified; `FIBERY_SPACE_ID` remains empty in it,
which is why process-scoped configuration was needed.

## 11. Cleanup

Deletion used only the two entity ids recorded during this run, after
confirming the Project Name matched the disposable identity. No fuzzy name
matching was used, and no pre-existing entity was touched. Deletion ran from an
ephemeral verification script through the existing authenticated Commands API;
no deletion support was added to SDLC production code.

```text
deleted Requirement 01a0969f-a01a-7169-8b1d-09f01e2365d0
deleted Project     01a0969f-8aa3-7ce5-8c58-e37d6379f38b
```

Read-only verification afterwards:

```text
Project exact-name count      = 0
Project Code count            = 0
RAW fingerprint matches       = 0 anywhere in the workspace
recorded Project id absent    : yes
recorded Requirement id absent: yes
recorded Root Document resolves by id : no
documents naming the deleted public id: 0
```

The temporary local input, consumer and failure-probe directories were removed.
No disposable live Fibery state and no temporary local state remain.

## 12. Repository gates

Run after the live evidence was complete:

```text
uv run pytest -q tests/test_project_bootstrap.py tests/test_cli_bootstrap.py  -> 79 passed
uv run ruff check .                                                           -> All checks passed!
uv run ruff format --check .                                                  -> 176 files already formatted
uv run pytest -q                                                              -> 2271 passed
```

No live-model test was required or run.

## 13. Acceptance mapping

| AC | Claim | Evidence | Verdict |
|---|---|---|---|
| AC1 | one real CLI action creates a usable local project structure | section 4, 5 | PASS |
| AC2 | descriptor and context match the frozen B01/B03 contracts | section 5 | PASS |
| AC3 | Fibery Project exists exactly once | section 6 | PASS |
| AC4 | initial RAW exists exactly once | section 6 | PASS |
| AC5 | same CLI rerun is safe and creates no duplicate | section 8 | PASS |
| AC6 | user/global model/auth/edit configuration unchanged | section 10 | PASS |
| AC7 | no credentials written to project files | section 5 | PASS |
| AC8 | real CLI failure gives a truthful non-success result and corrupts nothing | section 9 | PASS |
| AC9 | RAW stays Draft; no processing starts without the human transition | section 7 | PASS |

## 14. Scope confirmation

- no production code changed;
- no test code changed;
- no model was invoked;
- no RAW processing ran;
- no `Draft -> Process` transition occurred;
- no requirements-export ran;
- no live Requirement abstraction dogfood ran;
- AMR was not touched;
- no user-global configuration was created or modified;
- B01/B02/B03/B04 semantics are unchanged;
- Block E (RW-V01/V02/V03) was not started.

## 15. Proposed Change Requests

None. The live gate passed against the verified B04 implementation without
exposing a production defect.

One operational observation, already known and outside the plan: the operator's
persistent `.env` carries an empty `FIBERY_SPACE_ID`, so the real CLI cannot
reach Fibery through that local configuration alone until it is populated. This
is the same condition the RW-O03 verification recorded and is not a code or
plan defect.
