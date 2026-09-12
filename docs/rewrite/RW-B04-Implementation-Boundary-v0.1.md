# RW-B04 Implementation Boundary v0.1

**Status:** FROZEN  
**Work item:** `RW-B04 — Implement one outer project bootstrap action`  
**Owner of boundary:** Human + independent design reviewer  
**Derived from:** verified `RW-C03`, `RW-B01`, `RW-B02`, `RW-B03`  
**Semantic change to RW-C03:** NONE  
**Date:** 2026-09-12

## 1. Purpose

RW-B04 is composition. It creates the one normal project bootstrap action from the already-frozen local template/descriptor contracts and the existing deterministic Fibery Project Init and Requirement Add primitives.

It must not become a new requirements processor, project-repair engine, runtime configurator or generalized filesystem templater.

The normal command remains exactly:

```bash
sdlc project bootstrap \
  --name "<Project Name>" \
  --requirements <RAW_REQUIREMENTS_FILE.md> \
  --context <PROJECT_CONTEXT_FILE.md> \
  [--target <PROJECT_DIRECTORY>] \
  [--code <PROJECT_CODE>] \
  [--description "<Project Description>"]
```

`--requirements` and `--context` are both required in this rewrite. `--target` defaults to the current directory.

---

## 2. Primary implementation surface

Primary production module:

```text
src/sdlc/project_bootstrap.py
```

Primary tests:

```text
tests/test_project_bootstrap.py
tests/test_cli_bootstrap.py
```

Narrow supporting production edits are permitted only in:

```text
src/sdlc/project_init.py
src/sdlc/cli.py
```

`project_init.py` may add one read-only Project-Code preflight helper that reuses its existing Project-Code resolution logic; the behavior of `initialize_project` itself must remain unchanged.

No Fibery HTTP/schema change is expected. No Requirement Add semantic change is expected. `results.py` need not change: B04 result types may live in `project_bootstrap.py` to keep the composed result contract local.

---

## 3. Why Project Code must be resolved before local materialization

B03 makes the final Project Code part of `.sdlc/project.yaml`.

C03 also requires every managed local path to be preflighted and conflicts refused before Fibery mutation.

Therefore B04 must know the exact Project Code before deciding whether an existing descriptor is compatible, but must not create the Fibery Project merely to discover that code.

The frozen solution is:

```text
read-only Fibery identity/code preflight
        ↓
exact requested B03 descriptor known
        ↓
preflight all four managed local paths
        ↓
local materialization
        ↓
inner Project Init with the already-resolved code explicitly supplied
```

For a new Project, the later call to `initialize_project` must receive the preflight-resolved code explicitly even when the user omitted `--code`. This prevents a later collision race from causing Project Init to silently choose a different generated code than the descriptor already contains.

If the resolved code becomes unavailable before Project Init, Project Init fails normally; bootstrap reports the truthful partial/failure outcome and never rewrites the descriptor to a new code.

---

## 4. Read-only Project identity/code preflight

B04 may add one public helper to `project_init.py`, equivalent to:

```python
preflight_project_code(
    workspace: FiberyWorkspace,
    project_name: str,
    requested_code: str | None,
) -> str | InitResult
```

Exact naming may vary modestly.

The helper:

- performs no mutation;
- assumes B04 has already established that no exact-name Project exists when it is used for a new Project;
- reuses the exact existing Project Init code validation/derivation/collision logic;
- on success returns the exact code Project Init would attempt;
- on invalid input/Fibery read/collision returns the same bounded `InitResult` failure semantics that Project Init already uses;
- invokes no model.

It must not create a second Project-Code algorithm.

### Existing exact-name Project

Before code generation B04 queries exact Project Name through the existing Requirement-side project lookup (`find_projects_by_name`) because that API can expose ambiguity.

Rules:

```text
0 exact-name Projects
-> resolve a new code through the read-only Project Init preflight helper

1 exact-name Project
-> reuse its existing Project Code after validating it

>1 exact-name Projects
-> BOOTSTRAP_CONFLICT; no local/Fibery mutation
```

For one existing Project:

- Project Code must exist and already satisfy the current Project Code contract;
- if `--code` is supplied, its normalized/validated value must equal the existing Project Code;
- a mismatch is `BOOTSTRAP_CONFLICT`;
- bootstrap never changes an existing Project Code.

The optional Project Description is not project identity and is not rewritten on an existing Project merely because bootstrap was rerun.

---

## 5. Export input preflight

Both input artifacts are read before any local or Fibery mutation.

### RAW requirements

- path must be readable as UTF-8 text;
- the text is validated with the same `parse_raw_requirement` transport/parser used by Requirement Add;
- validation is only an early fail-fast check; bootstrap does not transform, normalize, split, summarize or reinterpret the source;
- the exact decoded source text is later passed to `add_raw_requirement`.

An invalid/unsupported RAW export produces `BOOTSTRAP_FAILED` with no bootstrap mutation.

### Project context

- path must be readable as bytes;
- bytes are opaque to bootstrap;
- no semantic parsing, placeholder substitution or model call occurs;
- the exact bytes are the requested content for `.sdlc/project-context.md`.

The requirements-export contract says the two artifacts come from the same export session. The current repository transport contains no shared session identifier, so B04 must not invent provenance inference from filenames/content. It enforces that both artifacts are explicitly supplied; export-session pairing remains the upstream requirements-export responsibility.

Input file contents must not be echoed in error diagnostics.

---

## 6. Target-directory boundary

`--target` omitted means the current working directory.

An explicit target may be:

```text
existing real directory
or
one absent final directory whose parent already exists as a real directory
```

B04 does not recursively create missing ancestors outside the requested target.

Conflict/failure rules:

- target exists as a file/non-directory -> conflict;
- target itself is a symlink -> conflict;
- absent target with absent/non-directory parent -> failure/conflict before mutation;
- existing non-empty target is allowed when all four managed paths preflight safely.

The target directory is the consumer project directory. B04 does not create or select a remote repository.

---

## 7. Closed managed local paths

B04 manages exactly the four B01 paths:

```text
.sdlc/project.yaml
.sdlc/project-context.md
AGENTS.md
.claude/CLAUDE.md
```

No fifth path is created or managed.

Excluded project-local files/directories from B01 remain foreign state and are neither validated nor edited by bootstrap.

---

## 8. Symlink and parent safety

Before any local write, preflight all four managed paths and the managed parent directories `.sdlc` and `.claude`.

Rules:

- a managed file path must not be a symlink;
- `.sdlc` and `.claude`, when present, must be real directories and not symlinks;
- target itself must not be a symlink;
- an absent managed parent may be created;
- a managed parent existing as a non-directory is conflict;
- an existing managed file must be a regular file;
- bootstrap does not follow a managed symlink to inspect or write its destination;
- bootstrap never deletes/renames foreign state to make the manifest fit.

Because the four managed relative paths are frozen constants with no `..` segments, they must remain lexically inside the selected target. B04 must not accept a caller-supplied managed path.

Preflight of **all four** managed paths happens before target-directory/file creation or any Fibery mutation.

---

## 9. Requested local content and compatibility

After Project identity/code preflight B04 constructs the requested local state:

### `.sdlc/project.yaml`

Requested value:

```python
new_project_descriptor(trimmed_project_name, resolved_project_code)
```

Absent -> create canonical `render_descriptor(...)` bytes.  
Existing -> `descriptor_compatible(existing_bytes, requested_descriptor)` must be true; reuse existing bytes unchanged.  
Anything else -> conflict.

No descriptor merge or rewrite.

### `.sdlc/project-context.md`

Absent -> create exact supplied context bytes.  
Existing exact byte equality -> reuse unchanged.  
Any difference -> conflict.

No text normalization or merge.

### `AGENTS.md` and `.claude/CLAUDE.md`

Use B02 `plan_agent_guidance` exactly.

- absent/empty -> write frozen block according to B02;
- foreign content with no marker -> append B02 planned block while preserving existing bytes;
- compatible current block -> reuse byte-for-byte;
- malformed/different block -> conflict.

B04 must not reproduce B02's marker/newline logic itself.

---

## 10. Full local preflight before mutation

B04 computes a local plan for every managed path before changing the target.

Each path plan is one of:

```text
CREATE
UPDATE   # only B02 append/empty agent-guidance materialization
REUSE
CONFLICT
```

If any path is conflict:

```text
BOOTSTRAP_CONFLICT
no local mutation
no Project Init
no Requirement Add
```

The preflight plan records enough original bytes/type/existence information to detect a path that changed before it is written.

No local artifact is modified merely to canonicalize a compatible file.

---

## 11. Local materialization

After the full preflight succeeds:

1. create the target directory if it was absent;
2. create missing `.sdlc` / `.claude` directories as needed;
3. materialize B02 static guidance paths;
4. materialize `.sdlc/project.yaml`;
5. materialize `.sdlc/project-context.md`;
6. read back every required local artifact and validate it against B01/B02/B03.

Before each write B04 rechecks that the path still has the preflighted type/existence/current bytes. An absent path is created exclusively; an existing guidance path is modified only when its current bytes still equal the bytes preflighted. B04 does not intentionally overwrite an intervening foreign edit.

Filesystem write/read-back failure does not trigger rollback. Report what became durable.

Local reporting distinguishes at least:

```text
created
updated
reused
```

A target/directory created by this attempt is also durable partial state even though it is not a template artifact.

---

## 12. Inner Project Init composition

Only after local materialization/read-back succeeds, invoke the existing deterministic:

```python
initialize_project(...)
```

Pass:

- normalized requested Project Name;
- the exact preflight-resolved Project Code explicitly;
- optional description unchanged.

Normal inner outcomes:

```text
PROJECT_INITIALIZED
PROJECT_ALREADY_EXISTS
```

For `PROJECT_ALREADY_EXISTS`, bootstrap validates that the existing Fibery Project is the exact intended identity: one exact-name Project, one global Project carrying the resolved code, and they are the same entity.

Bootstrap never repairs `PARTIAL_INIT` and never rewrites an existing Project Code/Description.

A non-normal Project Init result cannot be translated to full bootstrap success.

---

## 13. Inner Requirement Add composition

After compatible Project Init, invoke existing deterministic:

```python
add_raw_requirement(
    requirement_workspace,
    project=resolved_project_code,
    source_text=exact_preflighted_source_text,
)
```

Normal inner outcomes:

```text
RAW_REQUIREMENT_ADDED
REQUIREMENT_ALREADY_ADDED
```

Bootstrap does not duplicate Requirement creation, Source Fingerprint, Requirement-ID or Root Document business logic.

For either normal result, the Requirement returned/resolved by the source fingerprint must be compatible with the composed outcome:

- belongs to the intended Project;
- `Type = Raw`;
- `State = Draft`;
- Source Fingerprint equals the parsed input artifact;
- Requirement ID agrees with the Requirement Add result when present.

B04 does not start RAW processing and does not change Draft -> Process.

Sequential rerun safety relies on the existing Source Fingerprint duplicate guard. Distributed concurrent bootstrap exclusion is not introduced here.

---

## 14. Final composed validation

Bootstrap reports a normal success only after validating:

### Local

- target is a real directory;
- all four managed paths are real regular non-symlink files;
- descriptor parses and is semantically equal to the requested B03 descriptor;
- context bytes equal the supplied bytes;
- both agent-guidance files classify as B02 `COMPATIBLE`;
- no extra bootstrap-managed path exists because the managed set is closed in B01.

### Fibery Project

- exactly one exact-name Project exists;
- exactly one Project carries the resolved Project Code;
- both lookups identify the same Project entity;
- name/code equal requested resolved identity.

### Initial RAW

- the source fingerprint resolves to a Requirement in that Project;
- Requirement ID agrees with the normal Requirement Add result when supplied;
- Type is `Raw`;
- State is `Draft`;
- Source Fingerprint matches the input.

The Requirement Add primitive remains responsible for Root Document/content validation. B04 does not reopen or rewrite canonical Requirement content merely to validate bootstrap composition.

No Standard Requirement, Processing Result or worker execution is part of bootstrap success.

---

## 15. Bootstrap result vocabulary

B04 exposes exactly these top-level composed outcome codes from C03:

```text
PROJECT_BOOTSTRAPPED
PROJECT_ALREADY_BOOTSTRAPPED
BOOTSTRAP_CONFLICT
PARTIAL_BOOTSTRAP
BOOTSTRAP_FAILED
```

A bootstrap result should report bounded metadata such as:

- target;
- Project Name/Code;
- initial RAW Requirement ID when known;
- local created/updated/reused managed paths;
- whether target/managed directories were created;
- inner Project Init result code when invoked;
- inner Requirement Add result code when invoked;
- failed bounded step;
- sanitized details.

No source/context body, model content, token or credential is printed.

### `PROJECT_ALREADY_BOOTSTRAPPED`

Only when all required local state was already compatible/reused **and** Project Init reports the compatible Project already exists **and** Requirement Add reports the same source already exists. No durable mutation by this attempt.

### `PROJECT_BOOTSTRAPPED`

Complete validated outcome where at least one required bootstrap artifact/entity was newly materialized by this attempt.

### `BOOTSTRAP_CONFLICT`

An incompatible existing identity/path/content is found before this attempt creates durable bootstrap state. Nothing is overwritten/repaired.

### `PARTIAL_BOOTSTRAP`

The attempt created/updated any durable local artifact/directory or an inner primitive reports durable partial Fibery state, but the complete composed contract did not finish or validate.

No rollback/deletion is attempted.

### `BOOTSTRAP_FAILED`

The attempt did not complete and no durable bootstrap mutation by this attempt is known. This covers invalid/unreadable inputs and non-conflict operational failures before durable state exists.

---

## 16. Failure classification

Track whether this attempt produced durable state.

Rules:

- local preflight conflict before writes -> `BOOTSTRAP_CONFLICT`;
- exact-name Project ambiguity or supplied-code mismatch before local writes -> `BOOTSTRAP_CONFLICT`;
- invalid/unreadable export input -> `BOOTSTRAP_FAILED`;
- Fibery read/code-resolution operational failure before local writes -> `BOOTSTRAP_FAILED` unless it is an explicit identity collision/conflict;
- local write/read-back failure after any target/directory/file mutation -> `PARTIAL_BOOTSTRAP`;
- non-normal Project Init after local mutation -> `PARTIAL_BOOTSTRAP`;
- `PARTIAL_INIT` -> `PARTIAL_BOOTSTRAP` regardless;
- non-normal Requirement Add after local/Project mutation -> `PARTIAL_BOOTSTRAP`;
- `PARTIAL_ADD` -> `PARTIAL_BOOTSTRAP` regardless;
- final validation failure after this attempt mutated anything -> `PARTIAL_BOOTSTRAP`;
- an incompatible pre-existing state discovered with no mutation by this attempt -> `BOOTSTRAP_CONFLICT`.

Do not delete local/Fibery durable state to manufacture atomicity.

---

## 17. CLI surface

Add exactly:

```bash
sdlc project bootstrap \
  --name NAME \
  --requirements RAW.md \
  --context project-context.md \
  [--target DIR] \
  [--code CODE] \
  [--description TEXT]
```

No model/runtime flags.

No lifecycle/approval flags.

No `--force`, `--overwrite`, `--repair`, `--process`, `--start`, retry or cleanup flag.

CLI reads the same configured Fibery workspace as existing Project Init / Requirement Add, constructs the two existing workspace adapters from the same settings/client, and delegates composition to B04.

Normal exit code `0` only for:

```text
PROJECT_BOOTSTRAPPED
PROJECT_ALREADY_BOOTSTRAPPED
```

Every other bootstrap outcome exits non-zero.

---

## 18. Requirements-export session boundary

B04 does not run requirements-export.

Both exported artifact paths are required, but B04 cannot prove they came from the same export session because the currently frozen repository transport has no shared session identifier. It must not infer provenance from names, timestamps or prose.

Before the final bootstrap/dogfood gate, the external requirements-export skill remains subject to the rewrite plan section 10 verification.

---

## 19. Not part of RW-B04

Do not implement:

- requirements-export;
- RAW semantic processing;
- `sdlc worker run` startup/service management;
- lifecycle State transitions beyond inner Requirement Add's existing `Raw + Draft` creation;
- model calls;
- descriptor policy/check/standards execution;
- repository creation/remotes/commits/branches/worktrees;
- generalized repair/reconciliation;
- generalized template engine;
- credentials/runtime config generation;
- bootstrap rollback;
- B05 live/disposable E2E acceptance.

---

## 20. Required implementation evidence

B04 tests must prove at minimum:

1. empty existing target bootstraps successfully through one composition call;
2. absent explicit target with existing real parent is created and bootstraps;
3. current-directory mode works without a target argument;
4. non-empty target with unrelated files preserves them;
5. B02 foreign guidance is appended exactly and current block reused;
6. descriptor/context conflicts stop before any local/Fibery mutation;
7. symlink/non-directory managed path/parent conflicts stop safely;
8. invalid RAW/unreadable inputs stop before target/Fibery mutation;
9. omitted Project Code is resolved read-only and the exact code is used in descriptor + explicit inner Project Init call;
10. existing compatible Project is reused; supplied mismatching code conflicts before local mutation;
11. full rerun returns `PROJECT_ALREADY_BOOTSTRAPPED` with no writes/duplicates;
12. initial RAW is added once and remains `Raw + Draft`;
13. no Requirement processor/runner is invoked;
14. local materialization failure before Fibery produces truthful partial and no Fibery writes;
15. Project Init partial/failure after local state is truthful partial and no Requirement Add follows;
16. Requirement Add partial/failure is truthful partial and no rollback occurs;
17. final local/Project/RAW validation is required for success;
18. a race that invalidates the preflight-resolved Project Code does not cause silent descriptor/code drift;
19. result/CLI diagnostics never print RAW/context bodies or credentials;
20. no fifth managed consumer path is written.

RW-B05 remains the owner of the live/disposable end-to-end bootstrap acceptance against real Fibery.
