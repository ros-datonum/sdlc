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
- Documents Root — URL/reference

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

Project folder structure:

```text
<Project Name>/
└── Requirements/
    ├── Raw/
    ├── Draft/
    └── Approved/
```

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
