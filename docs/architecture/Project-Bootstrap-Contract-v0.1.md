# Project Bootstrap Contract v0.1

**Status:** DRAFT — RW-C03 HUMAN/REVIEWER CONTRACT  
**Implementation authorization:** NONE  
**Rewrite item:** `RW-C03`  
**Depends on:** `RW-C01 — Standard Requirement Abstraction v0.2`  
**Primary product requirements:** `docs/rewrite/SDLC-Corrected-Product-Functional-Requirements-v0.2.md`

## 1. Purpose

This contract defines the normal user-facing bootstrap journey for preparing a consumer project to participate in SDLC.

It deliberately separates two responsibilities:

```text
OUTER PROJECT BOOTSTRAP
= prepare the consumer repository/project context
+ establish project-local SDLC participation
+ invoke existing deterministic Fibery primitives

INNER `sdlc project init`
= create only the Fibery Project entity
```

The outer bootstrap is composition. It must not expand `project init` into a model-driven or requirement-processing capability.

---

## 2. Normal user journey

The normal new-project journey is:

```text
conversation / project definition
        ↓
requirements-export
        ↓
RAW requirements artifact + project-context.md
        ↓
one explicit bootstrap action
        ↓
consumer project prepared locally
        +
project-local SDLC descriptor/context established
        +
Fibery Project established
        +
initial RAW Requirement ingested
        ↓
RAW Requirement in Draft
        ↓
human reviews it in Fibery
```

After bootstrap completes, no Requirement processor starts merely because bootstrap completed.

The first Requirement processing cycle still requires the human lifecycle decision defined by `RW-C02`:

```text
RAW Draft -> Process
```

---

## 3. User-facing bootstrap action

The proposed normal command contract for this rewrite is:

```bash
sdlc project bootstrap \
  --name "<Project Name>" \
  --requirements <RAW_REQUIREMENTS_FILE.md> \
  --context <PROJECT_CONTEXT_FILE.md> \
  [--target <PROJECT_DIRECTORY>] \
  [--code <PROJECT_CODE>] \
  [--description "<Project Description>"]
```

`--target` defaults to the current directory.

For the outer bootstrap flow, both exported artifacts are required:

- one standardized RAW requirements artifact;
- one `project-context.md` artifact from the same requirements-export session.

This does not remove the existing narrower commands. A user who intentionally needs only a Fibery Project may still use `sdlc project init`; additional RAW requirements may still be added later with `sdlc project requirement add`.

Human approval of `RW-C03` also approves the external name `sdlc project bootstrap` and this input shape for the rewrite scope.

---

## 4. Bootstrap inputs and ownership

### 4.1 Project identity

Inputs:

```text
Project Name        required
Project Code        optional
Project Description optional
```

Identity semantics remain owned by the existing `Project-Init-Spec-v0.3` contract.

Bootstrap must not invent a competing Project Code or Project identity scheme.

### 4.2 RAW requirements artifact

The RAW requirements artifact:

- is produced before bootstrap by the global `requirements-export` skill;
- follows the supported requirements-export transport contract;
- represents one initial RAW Requirement input;
- is passed unchanged in meaning to the existing deterministic requirement-add primitive;
- is not semantically reprocessed by bootstrap.

### 4.3 Project context artifact

`project-context.md`:

- is produced by the same requirements-export session;
- provides project-level context needed by project-local agents/tools;
- is not a canonical mirror of Fibery product Requirements;
- may be used to materialize the project-local agent/instruction files frozen later by `RW-B01`;
- must not be silently augmented with new product requirements by bootstrap.

### 4.4 Target directory

Bootstrap can target:

- the current directory when `--target` is omitted;
- an explicit existing or new directory when `--target` is supplied.

The target is the consumer project directory, not the SDLC tool repository.

---

## 5. Responsibility boundary

Bootstrap is responsible only for establishing a project that can participate in the already-defined SDLC flow.

It may:

- preflight bootstrap inputs and target safety;
- apply the reusable consumer-project template frozen by `RW-B01`;
- establish the project-local descriptor defined by `RW-B03`;
- materialize the project context/instruction artifacts defined by `RW-B01`;
- invoke the existing deterministic `project init` primitive;
- invoke the existing deterministic `project requirement add` primitive for the initial RAW artifact;
- validate and report the final bootstrap outcome.

It must not:

- run requirements-export;
- reinterpret the exported requirements;
- split RAW into Standard Requirements;
- start RAW processing automatically;
- call a model merely to perform bootstrap;
- choose product requirements, UX, architecture, backlog, technologies, or implementation design;
- create a second source of lifecycle truth outside Fibery.

---

## 6. Frozen composition sequence

The bootstrap implementation must follow this responsibility order:

```text
1. Validate arguments and exported input files.
2. Resolve target directory and preflight every managed local path.
3. Refuse unsafe/conflicting local state before making bootstrap mutations.
4. Apply the exact reusable project template frozen by RW-B01.
5. Materialize the project-local descriptor/context defined by RW-B01/RW-B03.
6. Invoke existing deterministic `sdlc project init` behavior.
7. Invoke existing deterministic `sdlc project requirement add` behavior for the initial RAW artifact.
8. Validate the resulting local + Fibery bootstrap state.
9. Report COMPLETE, ALREADY_COMPLETE, CONFLICT, or PARTIAL/FAILED truthfully.
```

Steps 4–7 are composition of separately bounded capabilities. Bootstrap must not duplicate their internal business logic when an existing primitive already owns it.

---

## 7. Reusable consumer project template boundary

`RW-B01` owns the exact template manifest.

This contract requires the template to establish only already-agreed project-local SDLC participation, including the concepts of:

- `.sdlc/project.yaml`;
- project-local `project-context.md` or the exact context placement frozen by `RW-B01`;
- project-local Claude/Codex/agent instructions required for SDLC participation;
- repository-local SDLC skills/configuration where explicitly frozen by `RW-B01`.

The template must not contain:

- credentials;
- API keys/tokens;
- account-specific secrets;
- canonical Fibery Requirement prose;
- user-global model choice;
- user-global authentication settings;
- forced permission/approval policy;
- forced edit/sandbox policy unless the human explicitly chooses such a project-specific policy later.

The existing repository pattern is the intended inheritance principle: project-scoped configuration must not silently replace trusted user-global runtime configuration.

---

## 8. Project-local descriptor boundary

The project-local descriptor is:

```text
.sdlc/project.yaml
```

Its purpose is to tell SDLC tools/agents **how this repository participates in SDLC**.

It is configuration and project identity, not product Requirement storage.

`RW-B03` owns its exact schema, but the descriptor must be capable of expressing the previously agreed semantic groups where applicable:

- project identity;
- Fibery project/workspace mappings needed by SDLC;
- repository identity/policy;
- branch/worktree/merge policy where relevant;
- deterministic project checks;
- standards profile/extensions.

It must not contain:

- credentials;
- canonical product Requirement prose;
- a hidden local lifecycle state that competes with Fibery;
- lower-precedence configuration that silently overrides explicit human or canonical Requirement intent.

---

## 9. Existing deterministic primitives are preserved

### 9.1 `sdlc project init`

Bootstrap invokes the existing project initialization behavior rather than absorbing it.

`project init` remains:

- deterministic;
- model-free;
- Fibery-only;
- responsible for the Project entity;
- idempotent by existence detection;
- non-repairing.

Bootstrap must not reinterpret `PROJECT_ALREADY_EXISTS` as a failure when the existing Project is compatible with the requested bootstrap identity.

Bootstrap must not silently repair a `PARTIAL_INIT` condition that the inner contract explicitly does not repair.

### 9.2 `sdlc project requirement add`

Bootstrap invokes the existing RAW ingestion behavior for the initial export rather than duplicating it.

`project requirement add` remains:

- deterministic;
- model-free;
- one RAW artifact -> one RAW Requirement;
- source-preserving;
- duplicate-protected by its existing source identity/fingerprint contract;
- responsible for creating the contained Requirement Root Document.

Bootstrap treats `REQUIREMENT_ALREADY_ADDED` as compatible with a safe rerun when it resolves to the same Project/source artifact.

---

## 10. No requirements reinterpretation during bootstrap

Bootstrap consumes already-exported artifacts.

It must not transform:

```text
RAW requirements artifact
        ↓
"improved" requirements
```

or:

```text
project-context.md
        ↓
new product decisions
```

Any later semantic Requirement processing occurs only after the Requirement exists in Fibery and the human authorizes `Draft -> Process`.

This keeps the boundaries:

```text
requirements-export
= conversational source -> standardized artifacts

bootstrap
= standardized artifacts -> prepared project + Fibery initial state

Requirement lifecycle
= later semantic processing under Fibery State control
```

---

## 11. Local-file safety and rerun behavior

Bootstrap must be safe on a non-empty target directory.

Before writing any managed project-local path, it must preflight the full template/descriptor manifest frozen by `RW-B01/RW-B03`.

For each managed path, the frozen implementation policy must reduce to one of these outcomes:

```text
ABSENT      -> safe to create
COMPATIBLE  -> safe to keep/reuse
CONFLICT    -> stop; do not overwrite silently
```

A file is not `COMPATIBLE` merely because it has the expected filename.

Exact content/merge rules for each path are frozen in `RW-B01` before implementation.

Bootstrap must never overwrite an unrelated existing file as a convenience.

If preflight detects a conflict, it must stop before creating Fibery state for that bootstrap attempt.

---

## 12. Fibery rerun behavior

A safe rerun may encounter:

```text
Project already exists
initial RAW already exists
```

These are compatible no-op outcomes when they refer to the same requested identity/source.

Therefore a fully completed bootstrap rerun should converge to:

```text
PROJECT_ALREADY_BOOTSTRAPPED
No destructive changes made.
```

A rerun must not:

- create another Project because the first exists;
- create a second copy of the same RAW artifact;
- change immutable Project Code;
- rewrite an existing canonical Requirement;
- repair an incompatible/partial object by guessing.

---

## 13. Partial bootstrap behavior

Bootstrap spans local state and Fibery state, so partial completion is possible.

The system must distinguish at least:

```text
PROJECT_BOOTSTRAPPED
PROJECT_ALREADY_BOOTSTRAPPED
BOOTSTRAP_CONFLICT
PARTIAL_BOOTSTRAP
BOOTSTRAP_FAILED
```

### `PROJECT_BOOTSTRAPPED`

All required local and Fibery bootstrap state validates.

### `PROJECT_ALREADY_BOOTSTRAPPED`

All required state already exists and is compatible; no destructive mutation was needed.

### `BOOTSTRAP_CONFLICT`

Preflight or later validation found existing state that conflicts with the requested project identity/template/descriptor and cannot be changed safely under this contract.

### `PARTIAL_BOOTSTRAP`

Some durable bootstrap state was created, but the complete contract did not finish.

The result must report:

- which local artifacts were created/reused;
- whether the Fibery Project exists and its identity;
- whether the initial RAW Requirement exists and its identity;
- the exact bounded step that failed;
- the next safe action when known.

### `BOOTSTRAP_FAILED`

No successful complete bootstrap occurred and no durable partial state requiring partial reporting is known to have been created by this attempt.

Bootstrap must not roll back or delete durable state merely to simulate atomicity across local files and Fibery.

---

## 14. Recovery boundary

A rerun may continue only where already-created state is demonstrably compatible with the frozen bootstrap contract.

It must not guess repairs.

Examples:

- existing identical/compatible managed files -> reuse;
- existing same Fibery Project -> accept the inner `PROJECT_ALREADY_EXISTS` no-op;
- existing same RAW source -> accept the inner `REQUIREMENT_ALREADY_ADDED` no-op;
- conflicting `.sdlc/project.yaml` identity -> stop;
- inner `PARTIAL_INIT` requiring repair -> stop and report the underlying condition;
- unknown ownership of an existing managed file -> stop rather than overwrite.

A generalized repair/reconciliation engine is not introduced by this rewrite.

---

## 15. Validation before success

Bootstrap may report success only after validating the composed outcome.

At minimum the validated outcome must establish:

### Local

- target directory exists;
- every required template artifact from `RW-B01` is present and compatible;
- `.sdlc/project.yaml` satisfies the descriptor contract from `RW-B03`;
- project context/instruction artifacts match the frozen materialization rules;
- no bootstrap step wrote credentials or forbidden runtime overrides.

### Fibery

- the intended Project exists exactly once under the inner Project identity contract;
- Project identity/code are compatible with the bootstrap request;
- the initial RAW Requirement exists exactly once for the supplied source artifact;
- the RAW Requirement belongs to that Project;
- it is `Type = Raw`, `State = Draft` after bootstrap;
- its existing requirement-add validation contract succeeded or the same already-added source was safely resolved.

Bootstrap success does not require RAW Processing, Standard Requirements, Architecture, Epics, Stories, or Tasks to exist.

---

## 16. Post-bootstrap state

The expected normal result is:

```text
LOCAL CONSUMER PROJECT
  reusable SDLC project-local artifacts ready
  descriptor/context ready

FIBERY
  Project exists
  initial RAW Requirement exists
  RAW Type = Raw
  RAW State = Draft

AUTOMATION
  no RAW processing starts yet
```

The next product action is human review of the RAW source followed, when ready, by:

```text
RAW Draft -> Process
```

After that transition, `RW-C02` lifecycle ownership applies.

---

## 17. Additional requirements after bootstrap

Bootstrap owns only the initial project setup.

Additional source requirements later use the existing bounded flow:

```text
requirements-export
        ↓
sdlc project requirement add
        ↓
RAW Draft
        ↓
human Draft -> Process
```

The user must not need to re-bootstrap a project merely to add another Requirement.

---

## 18. Relationship to project-local Claude/Codex configuration

Bootstrap prepares project-local guidance but must preserve the user's trusted runtime configuration.

Project-local files may define:

- repository-specific instructions;
- repository-specific skills/workflows;
- project context;
- SDLC participation rules.

They must not silently force:

- model/model provider;
- authentication/provider credentials;
- approval policy;
- sandbox/edit policy;
- provider endpoint;
- another user-global execution preference.

`RW-B01` freezes the exact files and their copy/materialization policy before template implementation begins.

---

## 19. Explicit non-goals

This bootstrap contract does not implement or authorize:

- RAW semantic processing;
- Standard Requirement processing/review/application;
- UX/Product Design;
- Technical Solution Architecture;
- Delivery Planning;
- Epic/Story/Task generation;
- coding-agent execution;
- repository creation on a hosting provider;
- CI/CD creation;
- deployment infrastructure;
- generalized project repair;
- synchronization of canonical Requirements into repository files;
- automatic model/auth configuration;
- automatic requirements-export execution from inside SDLC.

---

## 20. Downstream ownership

This contract freezes **bootstrap composition and external behavior**.

The remaining concrete implementation details are deliberately assigned to bounded later work items rather than to Claude discretion:

```text
RW-B01
= exact reusable template manifest
+ exact per-path create/reuse/conflict policy
+ exact project-context/instruction materialization

RW-B03
= exact `.sdlc/project.yaml` schema and validation

RW-B04
= implement this frozen composition using B01 + B03 + existing inner primitives

RW-B05
= end-to-end verification on a disposable project
```

Therefore `RW-B04` may not invent a new template path, descriptor key, merge rule, or bootstrap lifecycle behavior.

---

## 21. Acceptance of RW-C03

`RW-C03` is satisfied when an independent reviewer confirms all of the following:

1. one normal user-facing bootstrap action is defined from exported artifacts to a ready consumer project;
2. the external bootstrap command/input contract is explicit;
3. current-directory and explicit-target modes are explicit;
4. outer bootstrap is clearly separated from inner `sdlc project init`;
5. the existing deterministic `project init` and `project requirement add` responsibilities are preserved;
6. bootstrap does not invoke a model or reinterpret product Requirements;
7. the initial RAW artifact enters Fibery through the existing requirement-add boundary and ends in `Raw + Draft`;
8. bootstrap completion does not automatically authorize RAW processing;
9. project-local context/configuration cannot silently override trusted user-global model/auth/permission/edit settings;
10. `.sdlc/project.yaml` is configuration/identity, not Requirement storage;
11. local target conflict behavior is preflighted and non-destructive;
12. safe rerun converges without duplicate Fibery Project or duplicate initial RAW Requirement;
13. partial outcomes are reported truthfully and no generalized repair behavior is invented;
14. exact template manifest and descriptor schema remain owned by `RW-B01` and `RW-B03`, so `RW-B04` cannot invent them;
15. no downstream Requirements processing, Architecture, Planning, Development, or deployment capability is introduced.

Until human review and independent verification complete, this document remains `DRAFT` and implementation is not authorized.
