# Project Requirement Add Specification v0.3

**Status:** Approved MVP contract  
**Supersedes:** `Project-Requirement-Add-Spec-v0.2.md`

v0.3 changes only Requirement ID allocation (section 7). v0.2 specified the
highest sequence in use plus one, which has a read-then-write race: two writers
can read the same highest value and durably store the same Requirement ID.
Post-write duplicate detection cannot close that window, because a collision
created after validation runs is never seen. Allocation now derives the number
from Fibery's atomically allocated `fibery/public-id`.

## 1. Purpose

`project requirement add` ingests one standardized RAW requirements Markdown artifact into an existing Fibery Project.

The command is intentionally deterministic and narrow.

It does **not** analyze requirements, create Standard Requirements, classify FR/NFR/CON, establish dependencies, or invoke an LLM.

### Current positioning

```text
requirement add remains a supported deterministic ingestion primitive;
bootstrap uses it for the initial RAW;
additional RAW sources for an existing Project may still be added directly.
```

`sdlc project bootstrap` invokes this primitive unchanged to ingest the initial
RAW artifact of a new Project. Adding a **further** RAW source to an existing
Project is this command's normal job — re-bootstrapping is not required for
that. Nothing in this specification's transport, fingerprint or duplicate
semantics changes. See `docs/architecture/Project-Bootstrap-Contract-v0.1.md`.

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
create Root Document contained by the Requirement
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

No Project folder structure exists or is checked (Project Init section 9,
amended 2026-09-09). The Project entity is the whole prerequisite.

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

Structure is read from headings outside fenced code blocks. A supported fence
is a backtick fence (three backticks at the start of a line, with or without
an info string) closed by three backticks at the start of a line, or running
to the end of the file when it is never closed; this is the same boundary the
content canonicalizer keeps verbatim. Inside a fence, a line that looks like a
level-1 title, a level-2 section or an Export Metadata entry is literal example
text: it never counts as the title or a section, never satisfies a missing
required section, never opens or duplicates one, and never supplies transport
metadata. Fenced text stays, unchanged, in the section that encloses it. The
first non-blank line of the file must still be the real title, so an example
placed before the title is invalid. Tilde fences, indented code blocks and HTML
blocks are not recognized as fences in this version.

Invalid source:

```text
INVALID_REQUIREMENT_SOURCE
```

---

## 7. Requirement ID Allocation

The Requirement ID is namespaced by the Project Code and numbered by Fibery.

Format:

```text
<PROJECT_CODE>-RAW-<PUBLIC_ID>
```

The numeric component is the entity's `fibery/public-id`, which Fibery allocates
atomically when the entity is created. The identifier is therefore assigned
after creation:

```text
create Requirement entity
→ Fibery allocates public-id
→ derive <PROJECT_CODE>-RAW-<PUBLIC_ID>
→ write Requirement ID onto the entity
```

The public id is zero padded to at least four digits for readability. Larger
values keep every digit:

```text
1      → SDLC-RAW-0001
37     → SDLC-RAW-0037
137    → SDLC-RAW-0137
12045  → SDLC-RAW-12045
```

### Requirements

The allocated Requirement ID must be:

- globally unique;
- unique within the Project namespace;
- immutable after successful assignment;
- human searchable.

### Numbering is sparse

Because the public id is allocated per Fibery Database rather than per Project,
numbering within a Project has gaps. This is valid and expected:

```text
SDLC-RAW-0003
SDLC-RAW-0009
SDLC-RAW-0014
```

Per-project contiguous numbering is **not** required. Identifiers of deleted
Requirements are never reused.

### Concurrency

Uniqueness comes from the allocator, not from checking afterwards. Two
concurrent writers receive different public ids and therefore cannot derive the
same Requirement ID.

An allocator that reads the highest identifier in use and adds one must not be
used. Fibery enforces no uniqueness constraint on the Requirement ID Field on
the current workspace plan, so a lost race there leaves two durable
Requirements sharing an identifier, and post-write detection does not prevent
it. Post-write validation still confirms the created Requirement carries the
expected Requirement ID, but that is validation, not allocation.

### Failure after creation

Because the identifier is assigned after the entity exists, a failure to write
it leaves durable state:

```text
Requirement entity created
→ public-id obtained
→ Requirement ID write fails
→ PARTIAL_ADD
```

The command reports the created Requirement and does not delete it. Recovery is
not part of this capability.

If Fibery returns a public id that is not the expected numeric form, the command
returns `REQUIREMENT_ID_ALLOCATION_FAILED` rather than substituting another
allocation scheme.

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

Create the Requirement Root Document named:

```text
<Requirement ID> — <Title>
```

Example:

```text
SDLC-RAW-0001 — Repository Handoff and Development Workflow
```

The Document is contained by the Requirement entity
(`fibery/container-type: "object"`, `fibery/container-entity-id` = the
Requirement's public id) and carries **no** `fibery/Folder`. Verified live on
2026-09-09: a contained Document created without a Folder is attached,
written, read and nested normally.

---

## 12. Lifecycle Placement Boundary

This command creates only:

```text
Requirement.Type = RAW
State = Draft
```

Placement is those two fields. No Document folder expresses it, and no folder
is read, created or validated. Root Documents created before 2026-09-09 still
carry a `fibery/Folder`; it is inert presentation metadata that no command
reads, checks or strips.

Human navigation is the workspace-level Smart Folder with mirrored context
views described in Project Init section 11; it is not a prerequisite of this
command.

Later Standard Requirement processing distinguishes, by the same fields:

```text
STANDARD + State != Applied   → current (Draft / Process / Review / Ready / Apply)
STANDARD + State = Applied    → applied
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

Root Document:
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

`project requirement add v0.3` does not:

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

`project requirement add v0.3` is complete when:

```text
existing Project is resolved
+
source artifact validates
+
duplicate source is not already present
+
RAW Requirement ID is derived from the Fibery public id
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
exactly one Root Document is created and attached, with no Folder
+
source content is preserved
+
post-write validation passes
```

At that point the Requirement is ready for human review and later transition:

```text
Draft → Process
```
