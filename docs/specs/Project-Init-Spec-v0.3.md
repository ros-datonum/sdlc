# Project Init Specification v0.3

**Status:** Approved MVP contract  
**Supersedes:** `Project-Init-Spec-v0.2.md`

## 1. Purpose

`project init` creates the minimum Fibery structure required for a new SDLC Project.

The command is intentionally deterministic and narrow.

It does **not** analyze requirements, create Project Phases, ingest requirements, create backlog items, or make product/technical decisions.

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
→ create Project and required document structure

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
- leave document structure unchanged;
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

## 9. Project Document Structure

Create the following Fibery document/folder hierarchy:

```text
<Project Name>/
└── Requirements/
    ├── Raw/
    ├── Draft/
    └── Approved/
```

Example:

```text
SDLC/
└── Requirements/
    ├── Raw/
    ├── Draft/
    └── Approved/
```

## 10. Documents

After the Project root is created, associate it with the Project through the
Fibery Documents field:

```text
Project.Documents
```

`Documents` holds the Project root Document, which sits at the top of:

```text
<Project Name>/
```

Fibery represents this natively. The document hierarchy is built from Fibery
**Folders** (`fibery/Parent Folder`), Documents join a Folder through
`fibery/Folder`, and a Document is associated with the Project entity by being
contained by it (`fibery/container-type: "object"`).

See `docs/fibery/Fibery-API-Constraints-v0.1.md` for the verified representation.
Slash-delimited names are not a valid substitute for real Folders.

The command must verify that the stored reference resolves correctly before reporting success.

## 11. Requirements Folder Semantics

### `Requirements/Raw`

Contains Root Documents associated with:

```text
Requirement.Type = RAW
```

RAW Requirements are added later through:

```bash
sdlc project requirement add
```

### `Requirements/Draft`

Contains Root Documents for Standard Requirements that have been created but have not yet reached:

```text
State = Applied
```

During:

```text
Draft → Process → Review → Ready → Apply
```

the Standard Requirement Root Document remains under:

```text
Requirements/Draft/
```

### `Requirements/Approved`

Contains Root Documents for Standard Requirements after:

```text
State = Applied
```

When a Standard Requirement is successfully applied, its Root Document is moved from:

```text
Requirements/Draft/
```

to:

```text
Requirements/Approved/
```

`project init` does not create Requirement entities or Requirement Documents.

## 12. Requirement Document Invariant

This command does not create Requirement Documents, but it establishes the folder structure used by later requirements operations.

The SDLC Requirement contract is:

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
- create missing folders;
- fix missing fields;
- restore deleted folders;
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

### Documents

```text
<Project Name>/ exists
<Project Name>/Requirements/ exists
<Project Name>/Requirements/Raw/ exists
<Project Name>/Requirements/Draft/ exists
<Project Name>/Requirements/Approved/ exists
Project.Documents holds the <Project Name>/ root Document
```

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

Documents:
✓ SDLC/
✓ Requirements/
✓ Requirements/Raw/
✓ Requirements/Draft/
✓ Requirements/Approved/

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
DOCUMENT_STRUCTURE_CREATE_FAILED
VALIDATION_FAILED
PARTIAL_INIT
```

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
Project document root exists
+
Requirements/Raw exists
+
Requirements/Draft exists
+
Requirements/Approved exists
+
Project.Documents references the root Document
+
post-create validation succeeds
```

No Project Phases or Requirements need to exist.

The Project is then ready for:

```bash
sdlc project requirement add
```
