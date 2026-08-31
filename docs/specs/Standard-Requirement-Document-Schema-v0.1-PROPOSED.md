# Standard Requirement Document Schema v0.1 — PROPOSED

**Status:** PROPOSED. Not approved. Not implemented against.

This artifact does not exist in the repository yet, and the RAW Requirement
Processor cannot create Standard Requirements without it: every Requirement must
have exactly one directly associated Root Document
(`Fibery-Schema-v0.1.md`, `RAW-Requirement-Processor-Decision-v0.1.md` section 7).

It is offered for review, revision or rejection. Nothing implements it until it
is approved and renamed without the `-PROPOSED` suffix.

## 1. Why this needs approving rather than inventing

The Root Document is the durable, human-reviewed body of a Standard Requirement.
Its structure will outlive the processor that first writes it: later Review,
Apply, revision and traceability all read it. Choosing that structure silently
inside a model prompt would freeze a long-lived contract by accident, which
`Project-Requirement-Add-Spec-v0.3`'s handling of the RAW artifact deliberately
avoided by deferring to a versioned interchange contract.

## 2. Modelled on the existing RAW contract

The RAW side already has a normative contract — the global `requirements-export`
skill's `schema.md`. That contract works because it is explicit about section
order, cardinality, and the exact text used when information is absent, which is
what makes deterministic validation possible without interpreting meaning.

This proposal follows the same shape for the Standard side.

## 3. Proposed document

The document is Markdown. The title line repeats the Requirement identity so the
document is readable outside Fibery:

```markdown
# <REQUIREMENT_ID> — <Title>
```

### Proposed sections

| Order | Section | Cardinality |
|---:|---|---|
| 1 | `## Requirement` | Required, exactly once |
| 2 | `## Rationale` | Required, exactly once |
| 3 | `## Acceptance Criteria` | Required, exactly once |
| 4 | `## Constraints and Non-Goals` | Required, exactly once |
| 5 | `## Provenance` | Required, exactly once |
| 6 | `## Open Questions` | Optional, at most once |

### Section meanings

- **Requirement** — the single normative statement, in the imperative. One
  independently reviewable obligation, per the atomicity rule.
- **Rationale** — why it exists, only from the source. No invented justification.
- **Acceptance Criteria** — how satisfaction is checked. Observable and testable.
- **Constraints and Non-Goals** — explicit boundaries, including what this
  requirement deliberately does not cover.
- **Provenance** — the RAW Requirement it derives from, by Requirement ID. This
  duplicates the `Derived From` relation in human-readable form.
- **Open Questions** — unresolved points carried forward for Review.

### Absent information

Where a required section has no content from the source, the exact text is:

```text
Not established in the source requirement.
```

Inventing content to fill a section is prohibited, matching the RAW contract.

## 4. Open questions for the approver

1. Are these the right sections, or should Acceptance Criteria be deferred to a
   later validation step?
2. Should `Provenance` be a document section at all, given `Derived From` already
   encodes it as a relation?
3. Should Constraints/Non-Goals be one section or two?
4. Is a `Verification Method` section wanted, distinct from Acceptance Criteria?
5. Should NON_FUNCTIONAL requirements carry a measurable target explicitly?

## 5. What this unblocks

Once approved, the processor can render the model's structured output into this
document deterministically:

```text
LLM reasoning -> structured candidate -> deterministic render -> Fibery write
```

The model would return the section content as data; the document is assembled by
code, never emitted as prose by the model. That keeps the format owned by the
repository rather than by a prompt.
