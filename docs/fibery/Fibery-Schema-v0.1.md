# Fibery Schema v0.1

This file records the currently approved Fibery databases and their core fields/relations.

## Project

Workflow:

```text
Planned
Active
Paused
Cancelled
Completed
```

Fields:
- Name — Name
- Code — Text, globally unique, immutable after creation
- State — Workflow
- Description — Rich Text
- Documents — Fibery Documents field; holds the Project root Document

Relations:
- Phases — 1:N Project Phase
- Requirements — 1:N Requirement
- Milestones — 1:N Milestone
- Epics — 1:N Epic
- User Stories — 1:N User Story
- Tasks — 1:N Task

## Project Phase

Workflow:

```text
Planned
Active
Paused
Completed
```

Fields:
- Name — Name
- State — Workflow
- Description — Rich Text
- Entry Criteria — Rich Text
- Work Cycle — Rich Text
- Expected Outputs — Rich Text
- Completion Criteria — Rich Text

Relations:
- Project — N:1 Project
- Allowed Next Phases — N:N self relation
- Allowed Previous Phases — inverse
- Tasks — 1:N Task

## Requirement

Workflow:

```text
Draft
Process
Review
Ready
Apply
Applied
```

Fields:
- Name — Name
- Requirement ID — Text, globally unique
- Title — Text
- State — Workflow
- Type — Single Select: RAW | STANDARD
- Category — Single Select: FUNCTIONAL | NON_FUNCTIONAL | CONSTRAINT; empty for RAW
- Revision — Integer
- Documents — Fibery Documents field; exactly one directly associated Root Document
- Source Fingerprint — Text, used by deterministic RAW ingest duplicate detection
- Processing Status — Single Select: Not Processed | Processing | Succeeded | Failed;
  default Not Processed. What happened in the machine-processing cycle of the
  current State; it is not lifecycle State
  (`docs/architecture/Requirement-State-Worker-Contract-v0.1.md` section 4).
  Only `sdlc worker run` requires it; every other command works without it

Relations:
- Project — N:1 Project
- Produces / Derived From — N:N self
- Depends On / Blocks — N:N self dependency relation
- Affects / Impacted By — N:N self
- Epics — N:N Epic
- User Stories — N:N User Story
- Tasks — N:N Task

Document invariant:

```text
Requirement
→ exactly one Root Document
→ zero or more nested child Documents
```

Lifecycle placement (amended 2026-09-09) is defined by Requirement fields,
never by Document folders:

```text
RAW                 Type = Raw
STANDARD CURRENT    Type = Standard, State != Applied
STANDARD APPLIED    Type = Standard, State = Applied
```

Root Documents are contained by their Requirement and carry no `fibery/Folder`
(Documents created before the amendment still carry one; it is inert). Human
navigation is a workspace-level Smart Folder over Projects with mirrored
context views RAW / Draft / Approved using those filters; SDLC runtime neither
creates nor requires it. The Project Text Field `Documents Root Folder ID` is
legacy: unused by runtime, kept for manual cleanup.

Processing Status reset (added 2026-09-11 for `RW-O03`): one workspace-global
Requirement automation, triggered when State changes, sets Processing Status to
`Not Processed` for exactly Raw + Process, Standard + Process, Standard + Review
and Standard + Apply, and for no other Type/State combination. Neither SDLC
runtime nor project bootstrap creates it. Setup and the verification checklist
are in `docs/fibery/Worker-Runner-Setup-v0.1.md`. The runner validates the
field/options, but supported runtime code does not prove or create the Fibery
automation. The operator must verify that rule before production use.

## Milestone

Workflow:

```text
Planned
Active
Paused
Completed
Cancelled
```

Fields:
- Name — Name
- Milestone ID — Text, unique
- State — Workflow
- Description — Rich Text
- Completion Criteria — Rich Text
- Target Date — Date, optional

Relations:
- Project — N:1 Project
- Epics — N:N Epic
- User Stories — N:N User Story

## Epic

Workflow:

```text
Draft
Ready
In Progress
Paused
Completed
Cancelled
```

Fields:
- Name — Name
- Epic ID — Text, unique
- State — Workflow
- Objective — Rich Text
- Scope — Rich Text
- Completion Criteria — Rich Text

Relations:
- Project — N:1 Project
- Requirements — N:N Requirement
- Milestones — N:N Milestone
- User Stories — 1:N User Story
- Tasks — 1:N Task for collapsed hierarchy
- Depends On / Blocks — N:N self dependency relation
- Affects / Impacted By — N:N self

## User Story

Workflow:

```text
Draft
Ready
In Progress
Validation
Paused
Completed
Cancelled
```

Fields:
- Name — Name
- User Story ID — Text, unique
- Title — Text
- State — Workflow
- Description — Rich Text
- Acceptance Criteria — Rich Text

Relations:
- Project — N:1 Project
- Epic — N:1 Epic, optional
- Requirements — N:N Requirement
- Milestones — N:N Milestone
- Tasks — 1:N Task
- Depends On / Blocks — N:N self dependency relation
- Affects / Impacted By — N:N self

## Task

Workflow:

```text
Draft
Validation
Ready
In Progress
Ready for Test
Testing
Ready for Review
Review
Needs Fix
Needs Human
Impact Review
Paused
Completed
Cancelled
```

Fields:
- Name — Name
- Task ID — Text, unique
- Title — Text
- State — Workflow
- Objective — Rich Text
- Scope — Rich Text
- Acceptance Criteria — Rich Text
- Definition of Done — Rich Text
- Relevant Contracts — Rich Text, optional

Relations:
- Project — N:1 Project, required
- Project Phase — N:1 Project Phase, required
- User Story — N:1 User Story, optional
- Epic — N:1 Epic, optional; used for collapsed Epic → Task hierarchy
- Requirements — N:N Requirement
- Depends On / Blocks — N:N self dependency relation
- Affects / Impacted By — N:N self

No implementation revision/URL fields are currently part of Task.
