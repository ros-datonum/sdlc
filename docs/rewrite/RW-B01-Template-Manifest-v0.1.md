# RW-B01 — Consumer Project Template Manifest v0.1

**Status:** FROZEN  
**Work item:** `RW-B01 — Freeze reusable consumer project template contents`  
**Owner:** Human + independent design reviewer  
**Implementation actor:** NONE  
**Derived from:** verified `RW-C03 — Project Bootstrap Contract v0.1`  
**Semantic change to RW-C03:** NONE  
**Date:** 2026-09-12

## 1. Purpose

This document freezes the complete project-local artifact manifest that an SDLC bootstrap may manage in a consumer repository.

After this freeze, `RW-B02`, `RW-B03` and `RW-B04` may implement these artifacts and policies, but may not invent another consumer-project file, merge rule, placeholder or local Requirement source.

The consumer project remains subordinate to the already-frozen ownership model:

```text
Fibery
= canonical product Requirements
+ Requirement lifecycle State

consumer repository
= project participation configuration
+ non-canonical project context
+ project-local agent guidance
```

The template contains no product Requirement mirror and no runtime/authentication override.

---

## 2. Complete managed consumer manifest

There are exactly four managed file paths:

| Path | Kind | Materialization owner | Required | Existing-path policy |
|---|---|---|---|---|
| `.sdlc/project.yaml` | generated project descriptor | `RW-B03` schema; `RW-B04` materializes it | yes | whole-file compatibility; never merge or overwrite |
| `.sdlc/project-context.md` | exported project context | `RW-B04` copies the supplied `--context` artifact | yes | exact source-content compatibility; never merge or overwrite |
| `AGENTS.md` | project-local agent guidance | `RW-B02` freezes the static SDLC managed block; `RW-B04` materializes it | yes | bounded managed-block append/reuse; foreign content preserved |
| `.claude/CLAUDE.md` | Claude Code project guidance | `RW-B02` freezes the same static SDLC managed block; `RW-B04` materializes it | yes | bounded managed-block append/reuse; foreign content preserved |

**Optional managed files: none.**

No other path belongs to the reusable consumer template in this rewrite.

Directories such as `.sdlc/` and `.claude/` are containers required by the managed files, not additional template artifacts.

---

## 3. Explicitly excluded paths

Bootstrap/template implementation must not create or manage any of these paths merely as part of SDLC participation:

```text
.codex/config.toml
.claude/settings.json
.agents/
.claude/agents/
.claude/skills/
.agents/skills/
.env
.env.*
project-local model/runtime configuration
project-local authentication/token files
local canonical Requirements files or directories
copies of the RAW requirements artifact
```

Rationale:

- absence of a project runtime override preserves trusted user-global Claude/Codex model, provider, authentication, approval, sandbox and edit-policy configuration;
- repository-local skills/agents belong to later explicitly designed execution capabilities, not to generic bootstrap participation;
- the RAW input is ingested through the existing deterministic `project requirement add` boundary and its canonical source representation belongs to the Fibery Requirement, not to a second repository mirror.

An existing excluded path in a consumer repository is foreign state. Bootstrap neither validates nor edits it unless a later explicit contract gives it ownership.

---

## 4. Managed path safety

Before creating any managed file, bootstrap must preflight **all four** managed paths and their parent components.

For the four managed paths:

- a managed path must resolve inside the selected target repository;
- bootstrap must not follow a symlink at a managed path or through a managed parent directory;
- if `.sdlc`, `.claude`, `AGENTS.md`, or another managed path component is a symlink where bootstrap would need to traverse/write it, the path is `CONFLICT`;
- if a required parent exists as a regular directory, it is reusable;
- if a required parent is absent, bootstrap may create the directory;
- if a required parent exists as a non-directory, it is `CONFLICT`;
- bootstrap never deletes, replaces or renames foreign filesystem state to make the manifest fit.

The complete local preflight happens before the bootstrap attempt creates Fibery state.

---

## 5. `.sdlc/project.yaml`

### Ownership

`RW-B03` owns the exact descriptor schema, required keys, value semantics, validation and canonical serialization.

`RW-B01` freezes only its placement and whole-file ownership policy:

```text
.sdlc/project.yaml
```

### Existing-path policy

```text
ABSENT
-> safe for RW-B04 to create from the B03 descriptor contract

COMPATIBLE
-> reuse unchanged

CONFLICT
-> stop bootstrap; never merge, patch or overwrite
```

`COMPATIBLE` is decided only by the exact `RW-B03` descriptor contract. Filename existence alone is never compatibility.

The descriptor is configuration/identity only. It must not contain canonical product Requirement prose or a local Requirement lifecycle state.

There is no B02 static placeholder version of `.sdlc/project.yaml`; B02 must not invent descriptor keys before B03 freezes them.

---

## 6. `.sdlc/project-context.md`

### Source

The content comes from the `project-context.md` artifact supplied through the bootstrap `--context` input and produced by the same `requirements-export` session as the initial RAW requirements artifact.

### Materialization

Bootstrap copies the supplied context content without semantic transformation, augmentation, summarization or model invocation.

No template placeholder substitution occurs inside the context.

### Existing-path policy

```text
ABSENT
-> create with exactly the supplied context bytes

COMPATIBLE
-> existing regular file is byte-identical to the supplied context bytes; reuse unchanged

CONFLICT
-> any other existing content; stop and do not overwrite or merge
```

The context is explicitly non-canonical. It may inform project-local agents/tools but never competes with Fibery as the source of product Requirement truth.

---

## 7. Agent guidance managed block

`AGENTS.md` and `.claude/CLAUDE.md` use the same exact SDLC managed block.

### Exact markers

```text
<!-- SDLC:BEGIN -->
<!-- SDLC:END -->
```

### Exact managed block content

```markdown
<!-- SDLC:BEGIN -->
## SDLC participation

This repository participates in SDLC.

- Project descriptor: `.sdlc/project.yaml`
- Project context: `.sdlc/project-context.md`
- Canonical product Requirements and Requirement lifecycle State live in Fibery.
- Do not create or maintain a local canonical Requirements mirror.
- Treat `.sdlc/project-context.md` as non-canonical project context, not as competing Requirement truth.
- Human lifecycle authority is the Requirement State in Fibery; do not infer approval or rework from model output or Review verdict alone.
- Project-local guidance must not set or override the user's global model/provider, authentication, approval, permission, sandbox, or edit-policy configuration.
<!-- SDLC:END -->
```

There are **no dynamic placeholders** in this block.

B02 therefore has no project-name/code/model/auth placeholder substitution to implement for these static assets.

---

## 8. Managed-block merge policy

The following policy is identical for `AGENTS.md` and `.claude/CLAUDE.md`.

### 8.1 File absent

Create the file containing only the exact managed block followed by one terminating newline.

### 8.2 File exists without either SDLC marker

The existing regular UTF-8 file is foreign content and must remain unchanged.

Append one blank-line separation followed by the managed block.

The implementation must preserve every pre-existing byte before the appended separator. It may choose the existing file's newline convention for the appended block; line-ending differences inside the managed block are not semantic differences.

### 8.3 File contains exactly one well-formed current SDLC block

If there is exactly one BEGIN marker and one END marker, in that order, and the normalized managed-block content between them equals the frozen block above, the file is `COMPATIBLE` and is reused byte-for-byte.

Compatibility normalization for the managed block is limited to line-ending equivalence (`LF` versus `CRLF`). No wording, whitespace-line, bullet or semantic fuzzy matching is allowed.

Foreign content before and after the block is ignored for compatibility and remains untouched.

### 8.4 Conflict cases

The path is `CONFLICT` and bootstrap stops before local/Fibery mutation when any of these is true:

- only one marker exists;
- END appears before BEGIN;
- more than one BEGIN or END marker exists;
- the single managed block differs from the frozen content other than line endings;
- the file cannot be decoded as UTF-8;
- the managed path is not a regular file;
- a symlink would be followed.

Bootstrap does not silently upgrade, replace or repair an old/different SDLC block in this rewrite.

---

## 9. Path-by-path ownership summary

### `.sdlc/project.yaml`

```text
content source: B03 deterministic generation
merge: never
reuse: B03-compatible descriptor only
overwrite: never
placeholder ownership: B03 only
```

### `.sdlc/project-context.md`

```text
content source: supplied --context artifact
merge: never
reuse: byte-identical only
overwrite: never
placeholders: none
```

### `AGENTS.md`

```text
content source: frozen B01 static block
merge: append/reuse exact managed block only
foreign content: preserved
overwrite: never
placeholders: none
```

### `.claude/CLAUDE.md`

```text
content source: frozen B01 static block
merge: append/reuse exact managed block only
foreign content: preserved
overwrite: never
placeholders: none
```

---

## 10. Rerun semantics

A completed bootstrap rerun is locally compatible only when all four managed paths classify as `COMPATIBLE` under the rules above.

A rerun must not:

- rewrite an identical file merely to update timestamps;
- replace a differing context file;
- rewrite a compatible descriptor;
- duplicate the managed block;
- repair malformed markers;
- add a second local Requirement representation.

This allows `RW-B04` to converge to `PROJECT_ALREADY_BOOTSTRAPPED` without destructive local changes when Fibery identity/source are also compatible.

---

## 11. Responsibility split across Block D

```text
RW-B01
= this exact consumer manifest and local-file policy

RW-B02
= implement the reusable static template assets/contracts for the two managed agent-guidance blocks
+ tests proving the frozen manifest contains no undeclared static template file or placeholder

RW-B03
= freeze/implement the exact `.sdlc/project.yaml` descriptor schema and validator/renderer

RW-B04
= compose B01 + B02 + B03 with supplied context + existing project init + existing requirement add
+ execute complete preflight/materialization/rerun/partial-result behavior

RW-B05
= disposable end-to-end bootstrap verification
```

B02 must not generate `.sdlc/project.yaml`, because its schema belongs to B03.

B02 must not embed `.sdlc/project-context.md`, because its content is a per-bootstrap export input, not a static template asset.

---

## 12. Acceptance criteria mapping

### AC1 — every template path explicitly listed

PASS by design: the complete managed consumer manifest is exactly four paths in section 2, with optional files explicitly set to none.

### AC2 — per-path overwrite/merge/skip behavior explicit

PASS by design: sections 5–9 define create, compatible reuse, bounded block append, conflict and never-overwrite behavior for every managed path.

### AC3 — no secret or user-global setting included

PASS by design: section 3 excludes credentials, environment files, model/runtime/auth configuration, `.codex/config.toml` and `.claude/settings.json`; the static block explicitly preserves trusted global runtime policy.

### AC4 — implementation cannot invent another file

PASS by design: sections 2 and 11 define the closed manifest and assign B02/B03/B04 responsibilities. Any additional consumer-managed path requires a reviewed plan/manifest change rather than implementation discretion.

---

## 13. Freeze rule

Any later proposal to add or manage another consumer-project file, change marker text, alter managed-block content, add a placeholder, change context placement, or change a create/reuse/conflict rule is a change to `RW-B01` and requires explicit human/reviewer approval.

Implementation agents are not authorized to broaden this manifest.