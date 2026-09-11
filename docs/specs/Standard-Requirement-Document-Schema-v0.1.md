# Standard Requirement Document Schema v0.1

**Status:** Approved contract for the Standard Requirement Root Document.  
**Amended by:** `RW-R01` (SDLC Rewrite v0.2), binding the document to
`Standard-Requirement-Abstraction-v0.2.md`. The amendment's status is tracked in
`docs/rewrite/SDLC-Rewrite-Plan-v0.2.md`. The rendered structure is unchanged
(section 7).

Every Standard Requirement has exactly one directly associated Root Document
(`Fibery-Schema-v0.1.md`). This file defines that document's structure.

The document is assembled deterministically by code from structured data. A
model may supply the content of each section, but never emits the document
itself, so the format stays owned by this repository rather than by a prompt.

## 1. Abstraction boundary

A Standard Requirement document states **WHAT must be true**. It follows the
boundary fixed by `Standard-Requirement-Abstraction-v0.2.md`:

```text
Requirement                      = WHAT must be true
Technical Solution Architecture  = HOW the approved Requirement will be satisfied
Delivery Planning                = how the chosen solution is decomposed into
                                   executable work
Task implementation              = concrete code, configuration, migration, test,
                                   or deployment work
```

The document is therefore not an architecture document, an implementation
specification, a Task, or a test plan.

Its content may express a capability, an outcome, observable behavior, a
business or system constraint, or an invariant. Implementation independence is
the default: the content should remain true if the implementation were replaced
by a different valid technical solution.

A technical mechanism is Requirement content only when the authoritative source
explicitly mandates it (abstraction contract, section 4). A mechanism that is
merely mentioned in background discussion, an existing implementation, an
example, or a previously proposed architecture stays downstream. When it is
unclear whether a mechanism is mandatory, that uncertainty is an Open Question,
not Requirement content.

Every section below carries this boundary. No section is a container for
solution design, implementation steps, or test implementation.

## 2. Document

Markdown, UTF-8. The title line repeats the Requirement identity so the document
is readable outside Fibery:

```markdown
# <Requirement ID> — <Title>
```

The separator is an em dash, matching the Root Document naming used by
`project requirement add`.

## 3. Sections

All section headings are required and appear exactly once, in this order:

| Order | Section |
|---:|---|
| 1 | `## Requirement` |
| 2 | `## Detailed Behavior` |
| 3 | `## Rationale` |
| 4 | `## Acceptance / Verification` |
| 5 | `## Constraints & Edge Cases` |
| 6 | `## Non-Goals` |
| 7 | `## Open Questions` |

The set is closed. A Requirement document has no section for architecture,
technical design, implementation steps, Tasks, test code, or deployment, and
section content can never add one (section 5).

### Requirement

The normative core: the capability, outcome, observable behavior, business or
system constraint, or invariant that must be true. It says what must hold, not
how the solution is internally constructed, unless the source explicitly
mandates that mechanism.

### Detailed Behavior

Only the externally or system-observable behavior needed to interpret the
Requirement correctly. It clarifies WHAT; it never holds HOW.

Allowed:

- lifecycle behavior visible in system state;
- conditions under which the obligation applies;
- meaningful success and failure outcomes;
- externally or system-observable rules needed to disambiguate the Requirement.

Not allowed — this is solution design or implementation mechanics, and belongs
to Technical Solution Architecture, Delivery Planning, or a Task:

- architecture;
- algorithm choice;
- module, class, or function design;
- worker or process topology;
- implementation sequence or implementation steps;
- exact test implementation;
- deployment mechanics;
- any other technical mechanism listed in section 5 of the abstraction
  contract.

A technical mechanism the source explicitly mandates is a constraint and is
stated in `Requirement` or `Constraints & Edge Cases`, never here. When no
behavioral clarification is needed, the section is omitted (section 4); it is
never a place to preserve technical source detail.

### Rationale

Why the requirement exists, only when the source establishes it. Rationale does
not authorize new obligations.

### Acceptance / Verification

Observable evidence that would demonstrate the requirement is satisfied: states,
outcomes, properties, boundaries, or externally observable scenarios. It answers
"what observable evidence would convince us this Requirement is satisfied?", not
"what test will we build to obtain that evidence?".

It must not prescribe:

- a test framework;
- exact unit or integration test code;
- mocks or fixtures;
- internal function calls;
- a specific technical verification path, unless the source explicitly
  mandates it.

Solution-specific test design belongs to Delivery Planning and Tasks.

### Constraints & Edge Cases

Product and system boundaries that remain meaningful under any valid
implementation, plus technical constraints the source explicitly mandates.

An edge case that exists only because a particular technical solution was
chosen belongs downstream.

### Non-Goals

Explicitly excluded product or system behavior or scope. Not a list of the
implementation alternatives that were not selected.

### Open Questions

Unresolved source decisions that affect WHAT must be true.

A question about how to satisfy an already understood obligation is an
architecture question. It belongs to Technical Solution Architecture and is not
recorded here, unless resolving it could materially change product intent.

This section is valid while a Standard Requirement is in `Draft`, `Process`,
`Review` or `Ready`. A later Apply contract may require it to be empty before
`Applied`; that workflow is not designed yet and must not be assumed here.

## 4. Missing information

A processor must not invent product semantics to fill a section.

A Requirement can omit any section its source does not establish. Only the title
and the `Requirement` section must have content. Omitting a section's content
never removes its heading: the section is rendered with fixed text, so the
document structure stays deterministic.

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

A section is omitted on the same terms when the only material available for it
is technical detail the section may not hold under section 3. That material
stays source context for downstream phases.

## 5. Structural boundary enforced by code

Code owns the document's structure: the level-1 title heading and the level-2
section headings. Section content is body text inside its section and cannot
add structure at those levels.

Model output for a section — from RAW decomposition or from Standard Process
normalization — is invalid (`INVALID_MODEL_OUTPUT`) when its content, outside a
fenced code block, contains a line Markdown reads as a level-1 or level-2
heading:

- an ATX heading: `#` or `##` followed by a space, a tab, or the end of the
  line, indented at most three spaces;
- a setext heading: a line of only `=` or only `-` characters, indented at most
  three spaces, directly below a non-blank line. It is refused even where a
  list item above would make it a thematic break; a blank line before a
  thematic break keeps it content.

Level-3 and deeper headings are allowed as structure within a section. A fenced
code block (the backtick fence grammar that `raw_source` uses to decide document
structure) is literal example text, so a heading quoted inside one is content.

The title is model output from the same two producers and is rendered into the
level-1 title line and the Root Document name. After its surrounding whitespace
is trimmed, it must be exactly one line: a title containing a line feed (`\n`)
or a carriage return (`\r`) is invalid (`INVALID_MODEL_OUTPUT`), because the
rest of it would render as document structure, such as a level-2 section.

This keeps a Requirement document from gaining an architecture,
implementation-steps, Task, or test-code section.

It is a structural check only. Code does not classify prose: whether section
content states WHAT or leaks HOW is a semantic judgement made by Standard
Process and Standard Review under the abstraction contract, not by this
deterministic schema.

## 6. Provenance is not a document section

The document carries **no** Provenance section.

Provenance is structural, held in Fibery:

```text
RAW.Produces  <->  STANDARD.Derived From
```

Duplicating that relationship as normative document prose would create a second
source of truth that could drift from the relation.

## 7. Existing documents and evidence

The `RW-R01` amendment changes no heading, section order, fixed text, title line,
or rendering rule.

Documents rendered before it, and the sections recorded in persisted Processing
Results and Process Results, therefore render, compare, and fingerprint exactly
as before. They are read as recorded: they are neither migrated nor re-validated
against section 5, which applies only when new model output is validated.

Root/child normative-tree binding (`Requirement-Normative-Tree-Binding-v0.1.md`)
is unaffected.

## 8. Relationship to the RAW artifact

The RAW Requirement's Root Document follows a different contract — the global
`requirements-export` interchange schema — and is the conversational source
material. This schema governs only the normalized Standard Requirement produced
from it.
