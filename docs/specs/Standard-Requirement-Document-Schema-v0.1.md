# Standard Requirement Document Schema v0.1

**Status:** Approved contract for the Standard Requirement Root Document.

Every Standard Requirement has exactly one directly associated Root Document
(`Fibery-Schema-v0.1.md`). This file defines that document's structure.

The document is assembled deterministically by code from structured data. A
model may supply the content of each section, but never emits the document
itself, so the format stays owned by this repository rather than by a prompt.

## 1. Document

Markdown, UTF-8. The title line repeats the Requirement identity so the document
is readable outside Fibery:

```markdown
# <Requirement ID> — <Title>
```

The separator is an em dash, matching the Root Document naming used by
`project requirement add`.

## 2. Sections

All sections are required and appear exactly once, in this order:

| Order | Section |
|---:|---|
| 1 | `## Requirement` |
| 2 | `## Detailed Behavior` |
| 3 | `## Rationale` |
| 4 | `## Acceptance / Verification` |
| 5 | `## Constraints & Edge Cases` |
| 6 | `## Non-Goals` |
| 7 | `## Open Questions` |

### Requirement

The normative core: what must be true.

### Detailed Behavior

Behavioral detail needed to interpret the requirement correctly.

### Rationale

Why the requirement exists.

### Acceptance / Verification

Observable or verifiable conditions that can later be used to determine whether
the requirement is satisfied.

### Constraints & Edge Cases

Known constraints, boundaries, exceptional cases, and relevant edge conditions.

### Non-Goals

Explicitly excluded behavior or scope.

### Open Questions

Unresolved information relevant to this candidate.

This section is valid while a Standard Requirement is in `Draft`, `Process`,
`Review` or `Ready`. A later Apply contract may require it to be empty before
`Applied`; that workflow is not designed yet and must not be assumed here.

## 3. Missing information

A processor must not invent product semantics to fill a section.

Where information required by a section is genuinely absent from the source, the
exact text is:

```text
Not specified in source.
```

For `Open Questions` with no questions, the exact text is:

```text
None.
```

Both are rendered deterministically by code, never generated as prose.

## 4. Provenance is not a document section

The document carries **no** Provenance section.

Provenance is structural, held in Fibery:

```text
RAW.Produces  <->  STANDARD.Derived From
```

Duplicating that relationship as normative document prose would create a second
source of truth that could drift from the relation.

## 5. Relationship to the RAW artifact

The RAW Requirement's Root Document follows a different contract — the global
`requirements-export` interchange schema — and is the conversational source
material. This schema governs only the normalized Standard Requirement produced
from it.
