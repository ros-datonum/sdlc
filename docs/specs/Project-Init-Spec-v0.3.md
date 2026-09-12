# Project Init Specification v0.3

**Status:** Approved MVP contract, amended 2026-09-09 (Type/State navigation
model: no Document folder tree)  
**Supersedes:** `Project-Init-Spec-v0.2.md`

## 1. Purpose

`project init` creates the minimum Fibery structure required for a new SDLC
Project: the Project entity itself.

The command is intentionally deterministic and narrow.

It does **not** analyze requirements, create Project Phases, ingest requirements, create backlog items, or make product/technical decisions.

### Current positioning

```text
project init remains a supported deterministic primitive;
the verified outer new-project path is project bootstrap;
bootstrap resolves identity and reuses project init;
direct invocation remains valid within this primitive's contract.
```

`sdlc project bootstrap` is the normal entry point when both exported artifacts
(RAW requirements and project context) are available: it resolves the Project
identity and Code, then invokes this primitive unchanged. Direct invocation
stays valid for admin and incremental workflows. Nothing in this specification's
behavior or result codes changes. See
`docs/architecture/Project-Bootstrap-Contract-v0.1.md`.

## 2. Command

```bash
sdlc project init --name "<Project Name>"
```

Optional:

```bash
--code <PROJECT_CODE>
--description "<Project Description>"
```

## 3. Responsibility

`project init` has exactly two normal outcomes:

```text
Project does not exist
→ create the Project entity

Project already exists
→ do nothing
→ return PROJECT_ALREADY_EXISTS
```

It is not a repair, update, or synchronization command.

## 4. Existing Project Check

Before creating anything, the command must search Fibery for an existing Project.

If the Project already exists:

```text
PROJECT_ALREADY_EXISTS
```

The command must:
- create nothing;
- update nothing;
- repair nothing;
- regenerate nothing;
- leave Project Code unchanged;
- leave Project relations unchanged.

Recommended result:

```text
Project "<Project Name>" already exists.

No changes were made.

Use:
sdlc project requirement add
to add requirements.
```

## 5. Inputs

### Required

```text
Project Name
```

### Optional

```text
Project Code
Project Description
```

If Project Code is omitted, it is generated automatically.

## 6. Project Code

Project Code is the global namespace prefix for SDLC identifiers.

Examples:

```text
SDLC
DES
MEM
RBH
```

Requirements:
- globally unique across all Projects;
- immutable after successful Project creation;
- uppercase alphanumeric;
- human-readable;
- short enough to use in Requirement, Milestone, Epic, User Story, and Task IDs.

Recommended length:

```text
3–6 characters
```

This is a recommendation, not a hard architectural constraint.

## 7. Project Code Generation

If the user provides `--code`, validate it before creation.

If no code is supplied:

```text
Project Name
→ derive candidate code
→ normalize
→ validate format
→ check global uniqueness
→ resolve collision
→ assign final code
```

Example:

```text
SDLC
→ SDLC
```

Possible future identifiers using the code:

```text
SDLC-RAW-0001
SDLC-FR-0001
SDLC-NFR-0001
SDLC-CON-0001

SDLC-MIL-0001
SDLC-EPIC-0001
SDLC-US-0001
SDLC-TASK-0001
```

The exact code-generation and collision-resolution algorithm is an implementation detail.

## 8. Project Entity

Create one entity in the Fibery `Project` Database.

Minimum initial values:

```text
Name        = <Project Name>
Code        = <generated or provided Project Code>
State       = Planned
Description = <optional>
```

The command must not create Project Phases.

The command must not populate Requirements, Milestones, Epics, User Stories, or Tasks.

## 9. No Project Document Structure

`project init` creates **no** Document folder tree. The physical
`<Project>/Requirements/{Raw,Draft,Approved}` hierarchy that v0.3 originally
required is retired: Fibery does not show entity-contained Documents in a
Folder's sidebar listing, so the tree never functioned as human navigation,
and it duplicated a lifecycle signal the Requirement already carries.

Historical note: Projects initialized before 2026-09-09 still have that tree
and a populated `Documents Root Folder ID`. They remain readable; the folders
and the field are inert. Nothing repairs, deletes or migrates them, and the
Fibery schema field is left in place for manual cleanup.

## 10. Documents

`project init` creates no Document. `Project.Documents` is left for genuine
Project documents. A Requirement's Root Document is contained by the
Requirement entity (`fibery/container-type: "object"`) and is created by the
requirement commands, never here. The command reads and writes no Folder,
sends no `fibery/Folder`, and does not read, write or require the legacy
`Documents Root Folder ID` field.

## 11. Requirement Lifecycle Placement

Lifecycle placement is defined by Requirement Database fields, not by where a
Document sits:

```text
RAW                 Type = Raw
STANDARD CURRENT    Type = Standard, State in Draft / Process / Review / Ready / Apply
STANDARD APPLIED    Type = Standard, State = Applied
```

`Applied` on the Requirement is the only approved-placement signal. No stage
moves a Document to express it.

### Human navigation

Human navigation is workspace-level Fibery UI configuration, made once per
workspace and shared by every Project:

```text
Smart Folder over Projects
-> Requirements relation
-> mirrored context views:
     RAW        Type = Raw
     Draft      Type = Standard AND State != Applied
     Approved   Type = Standard AND State = Applied
```

SDLC runtime neither creates nor validates it. It is not a prerequisite of
any command: if a user deletes or changes those views, every lifecycle
command still behaves correctly and only navigation UX is affected.

## 12. Requirement Document Invariant

This command does not create Requirement Documents. The SDLC Requirement
contract, enforced by the requirement commands, is:

```text
1 Requirement Entity
→ exactly 1 directly associated Root Document
→ zero or more nested child Documents
```

If a requirement appears to require several independent Root Documents, it should normally be reconsidered as multiple Requirements connected through relations.

## 13. Idempotency

`project init` is idempotent through **existence detection**, not reconciliation.

If the Project already exists:

```text
PROJECT_ALREADY_EXISTS
```

and the command exits without mutation.

It does **not**:
- fix missing fields;
- repair Project relations;
- recreate the Project;
- update Project metadata.

A future explicit repair/update command may handle these use cases if needed.

## 14. Post-Create Validation

Before reporting successful initialization, verify:

### Project

```text
Project entity exists
Project Name matches requested name
Project Code exists
Project Code is globally unique
Project State = Planned
```

No Document or Folder is validated, because none is created.

The command must read the created state back from Fibery rather than assume successful writes.

## 15. Success Result

Successful initialization returns:

```text
PROJECT_INITIALIZED
```

Recommended output:

```text
Project initialized.

Name: SDLC
Code: SDLC
State: Planned

Next:
Use `sdlc project requirement add`
to add the first RAW requirement.
```

## 16. Already Exists Result

If the Project exists:

```text
PROJECT_ALREADY_EXISTS
```

Recommended output:

```text
Project "SDLC" already exists.

No changes were made.

Use:
sdlc project requirement add
to add requirements.
```

## 17. Failure Classes

Possible failure results:

```text
INVALID_INPUT
INVALID_PROJECT_CODE
PROJECT_CODE_COLLISION
FIBERY_READ_FAILED
FIBERY_WRITE_FAILED
VALIDATION_FAILED
PARTIAL_INIT
```

### 17.1 `PARTIAL_INIT` versus `VALIDATION_FAILED`

These two are distinguished by whether the write sequence finished, because
that is what changes the operator's next action.

```text
PARTIAL_INIT
  the write sequence did not complete
  expected durable objects are missing
```

```text
VALIDATION_FAILED
  the intended write sequence completed
  read-back verification disagreed with the expected final state
  nothing is known to be missing
```

Both must report the durable state that was created, so either can be
diagnosed without querying Fibery by hand.

Read-back must identify the Project this run created by its own Fibery id,
never by a name lookup that could return a pre-existing object.

## 18. Partial Initialization

If creation fails after some durable objects were created:

```text
PARTIAL_INIT
```

The command must:
- not report success;
- report exactly what was created;
- report exactly what failed;
- not silently delete already-created Fibery state.

Because an existing Project causes future `project init` calls to exit without mutation, recovery from `PARTIAL_INIT` is **not** handled by rerunning `project init`.

A separate explicit recovery/repair capability may be designed later if real usage requires it.

## 19. Explicit Non-Goals

`project init v0.3` does not:
- create Project Phases;
- decide which Project Phases are required;
- configure phase transition graphs;
- create RAW Requirements;
- create Standard Requirements;
- ingest Markdown requirements;
- create Requirement Documents;
- create Milestones;
- create Epics;
- create User Stories;
- create Tasks;
- create or connect GitHub repositories;
- analyze project scope;
- choose technologies;
- create UX/Product Design;
- create Technical Solution Architecture;
- create delivery plans;
- configure agent runtime;
- create deployment infrastructure.

## 20. Downstream Boundary

After successful initialization, requirements are added separately.

```text
requirements-export skill
        ↓
raw-requirements.md
        ↓
sdlc project requirement add
        ↓
Requirement
Type = RAW
State = Draft
```

This separation keeps `project init` responsible for Project bootstrap only, and `project requirement add` responsible for requirements ingestion.

## 21. Definition of Done

`project init v0.3` is complete when, for a previously nonexistent Project:

```text
Project entity exists
+
unique immutable Project Code exists
+
Project State = Planned
+
post-create validation succeeds
```

No Project Phases or Requirements need to exist.

The Project is then ready for:

```bash
sdlc project requirement add
```
