# RAW Requirement Processor — Decision Note v0.1

**Status:** Approved design decision  
**Purpose:** Freeze the current boundary for RAW Requirement processing before designing Standard Requirement revision/change semantics.  
**Amended by:** `RW-R02` (SDLC Rewrite v0.2), fixing the decomposition level in
section 2. The amendment's status is tracked in
`docs/rewrite/SDLC-Rewrite-Plan-v0.2.md`.

## 1. Current Requirement Relations

The existing Requirement relations are sufficient for RAW-to-Standard provenance:

```text
RAW Requirement
    └── Produces → Standard Requirement

Standard Requirement
    └── Derived From → RAW Requirement
```

These relations are many-to-many.

Examples:

```text
SDLC-RAW-0007
├── Produces → SDLC-FR-0012
├── Produces → SDLC-NFR-0008
└── Produces → SDLC-CON-0003
```

and:

```text
SDLC-FR-0012
└── Derived From → SDLC-RAW-0007
```

## 2. RAW Processor Responsibility

When a Requirement has:

```text
Type = RAW
State = Process
```

the RAW Requirement Processor may:

- read the RAW Requirement Root Document and its child-document tree;
- normalize and decompose the RAW input;
- identify candidate Standard Requirements;
- classify Standard Requirements as:
  - Functional Requirement;
  - Non-Functional Requirement;
  - Constraint;
- create Standard Requirement candidates in `Draft`;
- create their Root Documents, contained by each candidate, with no Folder
  (placement is `Type = Standard`, `State = Draft`; amended 2026-09-09);
- establish `Produces / Derived From` provenance relations;
- identify possible duplication, conflict, overlap, or change to existing Standard Requirements;
- record such cases as findings for Review.

### Decomposition level

Candidates are Requirement-level obligations as defined by
`Standard-Requirement-Abstraction-v0.2.md` (sections 2–7 and 12), rendered under
`Standard-Requirement-Document-Schema-v0.1.md`:

- one candidate is one independently meaningful product/system obligation — a
  capability, required outcome, observable behavior, business or system
  constraint, or invariant — not one sentence, source bullet, field, parameter,
  error case, or implementation decision;
- one capability described together with many technical details of one proposed
  implementation is one candidate; genuinely independent obligations stay
  separate even when they share a paragraph, a source section, or an
  implementation;
- technical detail in the RAW source (abstraction contract, section 5) stays
  source context for later Architecture and is never by itself a candidate;
- a technical mechanism is candidate content only when the source explicitly
  mandates that exact mechanism, and it may then remain a Constraint; a
  mechanism seen only in an example, the current implementation, background
  discussion, an existing architecture, or a suggested approach is not
  mandated, and an unclear mandate is an Open Question;
- Acceptance / Verification describes observable satisfaction, never test
  implementation;
- source gaps and product-level open questions are preserved, never answered;
  architecture-only questions stay downstream;
- candidate count is an outcome of source semantics: zero, one, and many are
  all valid, and there is no target.

This is a semantic decision the model makes under the RAW decomposition prompt
(`raw_prompt.py`). Deterministic code validates only the bounded output shape
and the document structure (`raw_processing.py`; schema section 5). It does not
classify prose, split or merge candidates, or check their number.

## 3. No `Target Requirement` Relation

Do **not** add a `Target Requirement` field/relation to the `Requirement` Database at this stage.

The term would refer to a possible existing Applied Standard Requirement that a new RAW input may modify, replace, supersede, or conflict with.

That concept belongs to the future Standard Requirement revision/change model, which has not yet been designed.

Adding the relation now would prematurely constrain that future design.

## 4. No `Operation` Field Yet

Do **not** add an `Operation` field such as:

```text
CREATE
UPDATE
RETIRE
SUPERSEDE
```

to the `Requirement` Database at this stage.

The system has not yet defined:

- how an Applied Standard Requirement is revised;
- whether changes create a new entity or reuse the existing entity;
- how revisions are represented;
- how supersession works;
- how change proposals are linked to existing Applied Requirements.

Those decisions must be designed separately before introducing fields that encode them.

## 5. Existing Standard Requirement Impact

If the RAW Processor detects that a candidate may affect an existing Standard Requirement, it records a finding rather than mutating or formally linking the existing Requirement.

The existing Standard Requirements are comparison evidence, not authority: they
never override what the RAW source states, and one that is not `Applied` is a
candidate under review, not approved truth.

Examples:

```text
POSSIBLE_DUPLICATE
POSSIBLE_CONFLICT
POSSIBLE_CHANGE
POSSIBLE_SUPERSESSION
```

Example finding:

```text
Possible existing requirement impact:

Existing Requirement:
SDLC-FR-0012

Finding:
The candidate appears to modify the existing behavior rather than
introduce an independent new requirement.

Recommendation:
Review this as a potential change to the existing requirement.
```

## 6. RAW Processor Must Not

The RAW Requirement Processor must not:

- modify an existing Applied Standard Requirement;
- retire an existing Applied Standard Requirement;
- supersede an existing Applied Standard Requirement;
- create revision semantics;
- invent a `Target Requirement` relation;
- assign a formal change operation;
- resolve requirement-change behavior before the revision model exists.

## 7. Current Boundary

For RAW processing v0:

```text
RAW + Process
        ↓
normalize / decompose at Requirement level (section 2)
        ↓
0..N Standard Requirement candidates (no target count)
        ↓
State = Draft
        ↓
Root Documents contained by the candidates (no Folder)
        ↓
Produces / Derived From relations
        ↓
RAW → Review
```

If interaction with an existing Applied Standard Requirement is suspected:

```text
record finding
→ human/agent review later
```

not:

```text
mutate existing requirement
```

## 8. Deferred Design Decision

A separate design step will define:

> How changes to existing Applied Standard Requirements are represented, revised, reviewed, applied, and traced.

Only after that model is agreed should the SDLC consider adding fields or relations for:

- target/current requirement;
- change operation;
- revision identity;
- supersession;
- replacement;
- retirement.

## 9. Final Decision

For the current MVP:

```text
Keep:
Produces / Derived From

Do not add:
Target Requirement
Operation
```

This keeps the RAW Processor focused on decomposition and provenance while preserving flexibility for the later Standard Requirement change/revision model.
