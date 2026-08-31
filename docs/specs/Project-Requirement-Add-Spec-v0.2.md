# Project Requirement Add Specification v0.2

**Status:** Approved MVP contract  
**Supersedes:** `Project-Requirement-Add-Spec-v0.1.md`

## 1. Purpose

`project requirement add` ingests one standardized RAW requirements Markdown artifact into an existing Fibery Project.

The command is intentionally deterministic and narrow.

It does **not** analyze requirements, create Standard Requirements, classify FR/NFR/CON, establish dependencies, or invoke an LLM.

---

## 2. Command

```bash
sdlc project requirement add \
  --project <PROJECT_CODE_OR_NAME> \
  --source <RAW_REQUIREMENTS_FILE.md>
```

Example:

```bash
sdlc project requirement add \
  --project SDLC \
  --source AI-First-SDLC-raw-requirements.md
```

---

## 3. Responsibility

The command performs exactly this transformation:

```text
standard RAW Markdown artifact
        ↓
validate transport structure
        ↓
resolve existing Project
        ↓
allocate RAW Requirement ID
        ↓
create Requirement entity
        ↓
create Root Document in Requirements/Raw
        ↓
attach Root Document to Requirement
        ↓
write Markdown content
        ↓
post-write validation
        ↓
RAW_REQUIREMENT_ADDED
```

---

## 4. Inputs

### Required

```text
--project <Project Code or Project Name>
--source <Markdown file path>
```

### Project resolution

Resolution order:

```text
1. Exact Project Code
2. Exact Project Name
```

If Project Name is ambiguous:

```text
PROJECT_AMBIGUOUS
```

The command must not guess.

If Project does not exist:

```text
PROJECT_NOT_FOUND
```

Recommended response:

```text
Project "<value>" does not exist.

Run:
sdlc project init --name "<Project Name>"
```

Before ingesting the RAW Requirement, verify that the initialized Project document structure contains:

```text
Requirements/Raw/
Requirements/Draft/
Requirements/Approved/
```

If the expected structure is incomplete:

```text
PROJECT_STRUCTURE_INVALID
```

The command must not silently create or repair missing Project folders.

---

## 5. Source Contract

The source file must be produced according to the global `requirements-export` skill contract.

One Markdown file represents:

```text
one RAW Requirement input
```

The command does not split one file into multiple Requirement entities.

That decomposition happens later during RAW Requirement processing.

---

## 6. Source Validation

The command validates only deterministic transport/schema concerns.

At minimum:

```text
file exists
file is readable
content is non-empty
supported format/schema version
required title exists
required structural sections are valid according to the export schema
```

The command must not:

- reinterpret ambiguous product meaning;
- invent missing requirements;
- repair semantic gaps with an LLM;
- classify formal Requirement types.

Invalid source:

```text
INVALID_REQUIREMENT_SOURCE
```

---

## 7. Requirement ID Allocation

The Requirement ID is derived from the Project Code.

Format:

```text
<PROJECT_CODE>-RAW-<SEQUENCE>
```

Recommended sequence formatting:

```text
0001
0002
0003
...
```

Examples:

```text
SDLC-RAW-0001
SDLC-RAW-0002
DES-RAW-0001
```

### Requirements

The allocated Requirement ID must be:

- globally unique;
- unique within the Project namespace;
- immutable after creation.

The exact sequence allocation mechanism is an implementation detail, but it must be concurrency-safe.

---

## 8. Requirement Title

The title is read from the standardized Markdown artifact.

Example:

```text
Repository Handoff and Development Workflow
```

The command must not generate the title using an LLM.

If no valid title exists:

```text
INVALID_REQUIREMENT_SOURCE
```

---

## 9. Requirement Entity

Create one entity in the Fibery `Requirement` Database.

Initial values:

```text
Requirement ID = <PROJECT>-RAW-0001
Title          = <source title>
Type           = RAW
State          = Draft
Revision       = 1
Project        = <resolved Project>
Category       = empty
```

Entity display name follows the project naming convention:

```text
<Requirement ID> — <Title>
```

Example:

```text
SDLC-RAW-0001 — Repository Handoff and Development Workflow
```

---

## 10. Relations

At ingest time set only:

```text
Project
```

Leave requirement-analysis relations empty:

```text
Produces
Derived From
Depends On
Blocks
Affects
Impacted By
```

These are populated later by the appropriate processing/analysis agents.

---

## 11. Root Document Creation

Resolve:

```text
Project.Documents
```

Then create the Requirement Root Document under:

```text
<Project Name>/
└── Requirements/
    └── Raw/
        └── <Requirement ID> — <Title>
```

Example:

```text
SDLC/
└── Requirements/
    └── Raw/
        └── SDLC-RAW-0001 — Repository Handoff and Development Workflow
```

---

## 12. Requirements Folder Boundary

This command creates only:

```text
Requirement.Type = RAW
```

and therefore always stores the new Root Document under:

```text
<Project Name>/Requirements/Raw/
```

The presence of:

```text
Requirements/Draft/
Requirements/Approved/
```

is validated as part of the Project structure, but this command does not write to either folder.

Those folders are used later by Standard Requirement processing:

```text
STANDARD + State != Applied
→ Requirements/Draft/

STANDARD + State = Applied
→ Requirements/Approved/
```

---

## 13. Requirement Document Invariant

Each Requirement entity has:

```text
exactly one directly associated Root Document
```

That Root Document may contain nested child Documents later.

```text
Requirement
   ↓
Root Document
   ├── Child Document
   └── Child Document
        └── Child Document
```

The ingest command creates only the Root Document.

---

## 14. Document Attachment

Attach the created Root Document through the Fibery `Requirement.Documents` field.

After creation:

```text
Requirement.Documents count = 1
```

If the command cannot create or attach exactly one Root Document:

```text
DOCUMENT_ATTACHMENT_FAILED
```

---

## 15. Writing Source Content

The command writes the requirements-export Markdown content into the Root Document.

The command must preserve the semantic content produced by the export skill.

It may remove transport-only metadata if the export schema explicitly marks it as metadata rather than requirement body.

Examples of possible transport metadata:

```text
Format Version
Project Name
Project Code
Export Timestamp
```

Content sections such as:

```text
Intent
Context
Desired Outcomes
Functional Ideas and Behaviors
Non-Functional Expectations
Constraints
Decisions Already Made
Dependencies and Relationships Noted
Open Questions
Out of Scope / Deferred
```

remain part of the Root Document.

The command must not semantically rewrite the content.

---

## 16. Source Fingerprint

To prevent accidental duplicate ingestion, add a technical field to the `Requirement` Database:

```text
Source Fingerprint
```

Recommended Fibery type:

```text
Text
```

The fingerprint is generated deterministically from the normalized source Markdown.

Recommended algorithm:

```text
SHA-256
```

Exact normalization rules are an implementation detail, but must be deterministic.

---

## 17. Duplicate Detection

Before creating a new Requirement, compute the source fingerprint.

Check:

```text
same Project
+
same Source Fingerprint
```

If found:

```text
REQUIREMENT_ALREADY_ADDED
```

The command must not create another RAW Requirement.

Recommended output:

```text
This requirements artifact has already been added to project SDLC.

Existing Requirement:
SDLC-RAW-0003
```

---

## 18. Source File Ownership After Ingest

The Markdown file is a transport artifact.

After successful ingestion:

```text
Markdown file
= transport artifact

Fibery Requirement + Root Document
= active SDLC working state
```

The source file is not stored in the project repository and is not treated as the ongoing requirements source.

---

## 19. Post-Write Validation

Before reporting success, read the created Fibery state back and verify:

```text
Requirement entity exists
Requirement ID matches allocation
Type = RAW
State = Draft
Revision = 1
Project relation is correct
Source Fingerprint matches
Requirement.Documents count = 1
Root Document exists
Root Document is under Requirements/Raw
Root Document title is correct
Root Document content was written successfully
```

Do not report success based only on successful write calls.

---

## 20. Success Result

Successful ingestion returns:

```text
RAW_REQUIREMENT_ADDED
```

Recommended output:

```text
RAW requirement added.

Project: SDLC
Project Code: SDLC

Requirement:
SDLC-RAW-0001 — Repository Handoff and Development Workflow

State: Draft
Revision: 1

Document:
SDLC/Requirements/Raw/
SDLC-RAW-0001 — Repository Handoff and Development Workflow

Next:
Review the RAW Requirement in Fibery.
When ready, move it from Draft → Process.
```

---

## 21. Failure Classes

Possible results:

```text
INVALID_INPUT
PROJECT_NOT_FOUND
PROJECT_AMBIGUOUS
PROJECT_STRUCTURE_INVALID
SOURCE_FILE_NOT_FOUND
SOURCE_FILE_UNREADABLE
INVALID_REQUIREMENT_SOURCE
UNSUPPORTED_REQUIREMENTS_FORMAT
REQUIREMENT_ALREADY_ADDED
REQUIREMENT_ID_ALLOCATION_FAILED
FIBERY_READ_FAILED
FIBERY_WRITE_FAILED
DOCUMENT_CREATE_FAILED
DOCUMENT_ATTACHMENT_FAILED
CONTENT_WRITE_FAILED
VALIDATION_FAILED
PARTIAL_ADD
```

---

## 22. Partial Add

If failure occurs after durable Fibery state was created:

```text
PARTIAL_ADD
```

The command must:

- not report success;
- report the Requirement entity if created;
- report the Document if created;
- report which step failed;
- not silently delete durable Fibery state;
- avoid creating a second Requirement on retry if the first entity can be safely resolved.

A dedicated repair/reconciliation capability may be added later if required by real failures.

---

## 23. Explicit Non-Goals

`project requirement add v0.2` does not:

- create Projects;
- create Project Phases;
- normalize RAW Requirements;
- split RAW into Standard Requirements;
- classify FR/NFR/CON;
- validate product semantics;
- identify gaps;
- resolve contradictions;
- establish Requirement dependencies;
- establish Affects relations;
- modify existing Approved Requirements;
- create Milestones;
- create Epics;
- create User Stories;
- create Tasks;
- change Project state;
- invoke an LLM;
- write requirement files into a Git repository.

---

## 24. Downstream Boundary

After successful ingestion:

```text
Requirement
Type = RAW
State = Draft
```

The human reviews the Requirement in Fibery.

When ready:

```text
Draft → Process
```

That transition is handled by a separate RAW Requirement processing capability.

The responsibility boundary is:

```text
requirements-export
= conversational context → standardized RAW Markdown

project requirement add
= RAW Markdown → Fibery RAW Requirement

RAW Processor
= RAW Requirement → normalized Standard Requirement candidates
```

---

## 25. Definition of Done

`project requirement add v0.2` is complete when:

```text
existing Project is resolved
+
source artifact validates
+
duplicate source is not already present
+
unique RAW Requirement ID is allocated
+
Requirement entity exists
+
Type = RAW
+
State = Draft
+
Revision = 1
+
Project relation is correct
+
Source Fingerprint is stored
+
exactly one Root Document is created and attached
+
Document is stored under Requirements/Raw
+
source content is preserved
+
post-write validation passes
```

At that point the Requirement is ready for human review and later transition:

```text
Draft → Process
```
