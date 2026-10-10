# TSA-C01 — Technical Solution Architecture Contract v0.2

**Status:** FROZEN.
**Implementation authorized:** NO.
**Rewrite/work item:** `TSA-C01`.
**Repository baseline:** `ros-datonum/sdlc`, `main` at `0c790816ce862a4c2fa873885bf13958bd21ace9`.
**Supersedes:** `docs/architecture/TSA-C01-Contract-v0.1.md`.

This document converts the proposed design into one bounded, internally
consistent contract for the **first Technical Solution Architecture vertical
slice**. It is not an implementation specification, and it authorizes no engine.
A separate bounded implementation work item may be created only after this
contract is independently reviewed and approved.

## Version and supersession

**v0.2 supersedes v0.1 for TSA-C01 implementation work starting with I04.**

Reason: the pre-I04 independent review found contradictions in the
bootstrap-state, Architecture bootstrap-carrier and discovery semantics that
required amendment of FROZEN contract text. Section 0 requires a new contract
version for that, so the amendments are made here and v0.1 is left unchanged as
the historical record.

Status of completed work, which this version does not reopen:

- **I01, I02 and I03 remain accepted** implementation and evidence.
- **I02 remains VERIFIED** from the `P-1` live probe.
- **The I03 live evidence remains valid.**
- v0.2 clarifies the pre-I04 semantics **without changing the completed
  mechanisms** of I01–I03. It closes authority/specification contradictions
  discovered before I04 and governs I04 and every later work item.

Sections amended relative to v0.1, and only these: 3.3 (what "treated as absent"
does not mean), 5.1 and 5.1.1 (deterministic Architecture identity and
discovery), 5.2 (the pre-apply bootstrap write), 8 (the pre-first-apply lifecycle
boundary; the bootstrap emission form and the accepted read-back form), 12.1
(what a retried `start` resolves to), 14.1, 14.1.2, 14.2, 14.3 case 9 and 14.4 (durable
states A, B, D and E; the `EMPTY_ARCHITECTURE_SHELL` recovery condition;
command-local `C`; the Input Manifest refusal states; the two-level rule after an
unknown bootstrap mutation outcome), and section 16 rows 39 and 40 with the
matching sentence of 16.1. The facts recorded in sections 0.1, 17 and 19 keep the
baselines at which they were verified.

Result-code names used in this version (`CYCLE_NOT_FOUND`, `CYCLE_AMBIGUOUS`,
`CYCLE_FOREIGN_PROJECT`, `ARTIFACT_MALFORMED`, `MANIFEST_SHELL_UNRECOVERABLE`,
`MANIFEST_ACCEPTANCE_MISMATCH`, `ARCHITECTURE_CYCLE_STARTED`,
`ARCHITECTURE_CYCLE_RESUMED`, `REVIEW_NOT_CURRENT`, `INSPECT_INCOMPLETE`,
`FIBERY_WRITE_FAILED`, `FIBERY_READ_FAILED`) are those of the result-code
catalogue in
`docs/specs/TSA-C01-Implementation-Spec-v0.2.md`; this contract freezes the
classification each one names, not its spelling.

`EMPTY_ARCHITECTURE_SHELL` is **not** a result code. It names the bootstrap
recovery condition of section 14.4 and is never returned as a command outcome.

## 0. How to read this document

Three kinds of statement are kept apart on purpose.

| Marker | Meaning |
|---|---|
| **FROZEN** | A decision this contract settles. An implementation MUST follow it; changing it requires a new contract version. |
| **OBLIGATION** | Work an implementation MUST perform to satisfy a FROZEN decision. The mechanism is bounded here, the code is not written here. |
| **DEFERRED** | An authority, policy or semantics question this contract does not decide. It needs a human decision or a new contract version; an implementation agent MUST NOT choose it unilaterally. |
| **IMPLEMENTATION-SPEC** | The authority is frozen here; only the mechanism is open. It belongs in the implementation specification a bounded work item would carry, and an implementation agent MUST NOT choose it silently. |

`MUST`, `MUST NOT` and `MAY` are used in the RFC-2119 sense. `MUST NOT` is a
prohibition on the engine, not advice.

### 0.1 Inputs to this contract, and one missing input

| Input | Status |
|---|---|
| `TSA-C01-Design-Brief-v0.1-DRAFT.md` | Read in full (203 lines, baseline `91c2697`). |
| Current repository `main` | Read at `a38d2c3`; verified facts in section 17. |
| `TSA-C01-Independent-Design-Review-v0.1.md`, verdict `DESIGN_DIRECTION_SUPPORTED` | Read in full (354 lines). Its section 5 is reconciled against section 16 in section 16.1. |

All three inputs have now been read. The review reviewed baseline `a38d2c3`,
the same baseline as this contract, and returned `DESIGN_DIRECTION_SUPPORTED`
with three groups of decisions to freeze and no blocking objection.

Section 16 was reconciled scenario by scenario against the review's section 5
(28 scenarios) on 2026-09-28. The mapping is recorded in section 16.1, including
the cases where several review scenarios share one acceptance row and the cases
where one review scenario needs more than one. This closed `U-1`.

## 1. Scope of the first slice

**FROZEN.** One TSA cycle covers exactly this path:

```text
a human explicitly starts an architecture cycle for an explicitly selected
   set of Applied Standard Requirements in one Project
→ the system admits the inputs and freezes an Input Manifest
→ the Architect produces one integrated recommended architecture
→ an independent Reviewer returns findings on that exact output
→ the system stops at a human decision boundary
→ the human chooses REWORK or APPROVE
→ an approved architecture becomes available to a future Delivery Planning phase
```

**MUST NOT** be part of this slice: a UX engine, a Delivery Planning engine, a
handoff engine, a general orchestration framework, a new authority or memory
system, or any automatic start of the next phase. A positive Reviewer result
**MUST NOT** trigger anything.

## 2. Input authority

**FROZEN.** A TSA cycle operates only on an **explicit, non-empty, human-selected
set** of Applied Standard Requirements belonging to **one** Project. The engine
**MUST NOT** derive the set, widen it, narrow it, or drop a member.

### 2.1 Admission checks

**OBLIGATION.** Before an Input Manifest is frozen, admission MUST verify, for
every selected Requirement:

1. **Exact identity** — the Requirement ID *and* the Fibery entity ID resolve to
   one entity. A name or Requirement-ID-only match is not identity.
2. **Project ownership** — the entity's Project is the cycle's Project.
3. **Type** = `Standard`.
4. **State** = `Applied`.
5. **Complete current normative tree** — the Root Document and every normative
   child Document at every supported depth, read under
   `docs/specs/Requirement-Normative-Tree-Binding-v0.1.md`.
6. **Current Process Result** at version `0.3` carrying a manifest at version
   `2`.
7. **Current Review Result** at version `0.3`.
8. **Exact bindings** — the Review Result's `reviewed_document_fingerprint` and
   tree manifest match the current tree; the Process Result's tree binding
   matches the same tree; Process and Review refer to the same iteration
   lineage of the same Requirement.

Admission failure for any selected Requirement **MUST** fail the start of the
cycle. The engine **MUST NOT** admit a partial set, and **MUST NOT** substitute
an older Result.

### 2.2 What admission does and does not prove

**FROZEN.** Admission proves that the Requirement's **current** content is
internally consistent with its **current** Process and Review evidence.

Admission **MUST NOT** be described, in code, in output or in an artifact, as
proof that this content is what a human historically approved at Apply time.
`State = Applied`, the integer `Revision`, and an unchanged Root are **not**
provenance evidence, individually or together. Section 17.2 records why: the
Apply implementation persists no artifact of its own.

**FROZEN.** The provenance gap is closed at the start of the cycle by a human,
not by inference: the human **MUST** explicitly accept the exact verified
Requirement input manifest as the normative input of this TSA cycle
(section 3.3). Nothing else in this contract claims historical Apply provenance.

**DEFERRED.** Any future mechanism that would make Apply itself provable — an
Apply Result artifact, a signed approval record, or an equivalent — is out of
scope here and **MUST NOT** be invented by an implementation agent.

## 3. Input Manifest

**FROZEN.** There is **no** separate Baseline entity. The cycle's scope is an
immutable **Input Manifest**.

### 3.1 Content

**OBLIGATION.** The Input Manifest MUST record, at minimum:

| Field | Note |
|---|---|
| Workspace identity | Host and Space id, as the runtime already derives it. |
| Project entity ID and Project Code | Both; the code alone is not identity. |
| Cycle UUID | Generated once, at start. |
| Manifest schema version | This artifact's own version (section 11.2). |
| Requirement IDs **and** entity IDs | For every included Requirement. |
| Full normative-tree manifest v2 and fingerprints | Per Requirement, exactly as read. |
| Process Result identity, iteration and payload digest | Per Requirement. |
| Review Result identity and payload digest | Per Requirement. |
| UX prerequisite evidence | Section 4 in full: for `APPLICABLE`, the Document id, content digest, exact scope and human approval of that digest for that scope; for `NOT_APPLICABLE`, the decision, reason and input binding. |
| Creation timestamp | |
| Digest of the complete manifest | Section 11.2. |
| Explicit human input acceptance | Bound to that digest (section 3.3). |

### 3.2 Immutability

**FROZEN.** The Input Manifest is immutable once valid. The Architect **MUST
NOT** modify it, and no model output **MAY** modify it.

**FROZEN.** A change to the Requirement set, or to the version of any included
Requirement, **MUST** start a **new TSA cycle**. It **MUST NOT** be handled as a
rework of the existing cycle. REWORK (section 6) is authorized only for the same
Input Manifest.

### 3.3 Human input acceptance

**FROZEN.** The human acceptance is bound to the manifest digest. An acceptance
recorded against a different digest is not acceptance of this manifest and
**MUST** be treated as absent.

**FROZEN.** "Treated as absent" means it **authorizes nothing**: no Architect
call and no later lifecycle step. It does **not** return the cycle to an ordinary
bootstrap state. A persisted, non-empty Input Manifest Document whose acceptance
is missing or bound to a different digest is a **refusing** state (section 14.4,
state E), never state B, never the command-local `C` phase and never state D.

## 4. UX prerequisite

**FROZEN.** The UX prerequisite has exactly two admissible values.

### 4.1 `APPLICABLE` — the admissible evidence interface

**FROZEN.** The UX source is **one exact readable Fibery Document**, supplied or
resolved by its **Fibery Document ID**. The engine **MUST** read that Document's
complete supported content; it **MUST NOT** accept a reference it cannot read.

**FROZEN.** The Input Manifest **MUST** bind all four of:

| Bound value | Rule |
|---|---|
| UX Fibery Document ID | The machine identity. A name or URL is not identity. |
| Current content digest | Computed over the content actually read. |
| Exact Requirement-scope coverage | Which of this cycle's Requirements the UX covers. |
| Explicit human approval | Of **this** content digest for **this** scope. |

**FROZEN.** An arbitrary version label **MUST NOT** substitute for a content
digest. A URL, a document name or a version string without readable content is
**insufficient** and **MUST** fail admission.

**FROZEN.** UX that is missing, unreadable, deleted, replaced,
digest-mismatched or scope-mismatched **MUST** fail admission **before the
Architect is invoked**. This is an admission check, not only a later drift
check.

**FROZEN.** Revalidation (section 10) **MUST** detect later content change,
deletion, replacement and scope drift of that Document, under the single
definition in section 4.4.

**FROZEN.** The approval TSA records is **TSA-local evidence** with exactly this
meaning: *this exact UX content digest is approved for this exact Requirement
scope*. It **MUST NOT** be described, in code, output or artifact, as proof that
the UX artifact was historically approved through any UX process. This mirrors
the input-acceptance limit in section 2.2.

### 4.2 `NOT_APPLICABLE`

**FROZEN.** The manifest MUST carry an explicit human decision, a reason, and a
binding to the exact Requirement input digest it was decided against.

**FROZEN.** This branch **MUST NOT** require a UX Document. The absence of a UX
Document under `NOT_APPLICABLE` is the **expected** state, never missing
evidence, and **MUST NOT** be reported as an unreadable or deleted UX artifact.

### 4.3 Authority and boundaries

**FROZEN.** A model **MUST NOT** write `NOT_APPLICABLE`, and **MUST NOT** record
an `APPLICABLE` approval. A model **MAY** propose a classification as evidence
for the human; every recorded value **MUST** come from a human decision. The
absence of a graphical UI is **not** evidence that UX does not apply.

**FROZEN.** No separate UX entity and no UX engine is created for TSA-C01. This
contract does not remove UX from the product lifecycle or permit skipping it
silently.

**OBLIGATION.** Reading a UX Document by id, and computing its content digest,
reuse the existing document read and canonical-fingerprint mechanisms. The
physical adapter work is **IMPLEMENTATION-SPEC**, tracked with `U-3`; the
**authority semantics above are frozen here** and are not an open question.

### 4.4 UX currentness — one discriminator-aware definition

**FROZEN.** UX currentness is defined **once**, here, and the recorded
prerequisite value is the authoritative discriminator. Every consumer — admission
(section 2), freshness revalidation (section 10), the Recovery Validation Gate
(section 14.1), approval (section 9) and a downstream consumer's currentness
check — **MUST** apply this definition and **MUST NOT** define a competing one.

**When the recorded value is `APPLICABLE`**, UX is current only when **all** of:

1. the bound UX Fibery Document **identity** is unchanged;
2. that Document is still **readable**;
3. its **complete supported content** can be read;
4. the **current content digest equals the bound digest**;
5. the **exact Requirement-scope coverage** still matches;
6. the **human approval evidence is still bound to this digest for this scope**.

Missing, unreadable, deleted or replaced Document, digest mismatch, or scope
mismatch ⇒ **stale or invalid**.

**When the recorded value is `NOT_APPLICABLE`**, UX is current only when **all**
of:

1. the **same explicit human `NOT_APPLICABLE` decision** is present;
2. the **same reason and evidence record** is present;
3. its binding still matches the **exact current Requirement-input digest**.

**FROZEN.** Under `NOT_APPLICABLE` the checks of the `APPLICABLE` branch
**MUST NOT** be applied: there is no Document to read, no digest to compare and
no scope coverage to match. Drift of the **Requirement input** is what makes a
`NOT_APPLICABLE` decision stale.

## 5. Canonical storage

**FROZEN.** The canonical location is Fibery **Project-contained Documents**:

```text
Project entity  (Project.Documents containment)
└── <Project Code> — TSA <cycle-id> — Architecture
    ├── TSA <cycle-id> — Input Manifest
    ├── TSA <cycle-id> — Process Result NNNN
    ├── TSA <cycle-id> — Review Result NNNN
    └── TSA <cycle-id> — Human Decision NNNN
```

**FROZEN.** There is **no additional canonical Project Root Document concept**
in TSA-C01. The Architecture Document is contained **directly** by the Project
entity through `Project.Documents`. The **Project entity id** is the
authoritative container identity.

### 5.1 Ownership, uniqueness, parentage

**FROZEN.**

- The **Architecture Document** is the single canonical architecture for its
  cycle. Exactly one exists per cycle, contained directly by the Project entity.
- **Input Manifest**: exactly one per cycle, parented under that cycle's
  Architecture Document.
- **Process Result NNNN**, **Review Result NNNN**, **Human Decision NNNN**:
  zero or more per cycle, `NNNN` a zero-padded iteration ordinal, unique within
  the cycle, parented under that cycle's Architecture Document.
- A cycle's children **MUST NOT** be parented under another cycle's Architecture
  Document, and **MUST NOT** be attached to a Requirement entity.
- Document names are human and navigation metadata, never machine identity.
  The engine **MUST** resolve documents by their Fibery ids (document names are
  not unique — Fibery API constraint 2a). A name aids human navigation and
  **MAY** be reported diagnostically. A name **never** establishes identity,
  **never** authorizes adoption, **never** authorizes a create, and **never**
  causes ambiguity by itself.

### 5.1.1 Architecture discovery, and rediscovery after an unknown create outcome

**FROZEN — the authority rule.** Every TSA Document id is **deterministic**:
derived from the workspace identity, the Project entity id, the canonical cycle
id and the artifact type. The derivation is IMPLEMENTATION-SPEC and is fixed in
`docs/specs/TSA-C01-Implementation-Spec-v0.2.md` §3.5. The deterministic
Architecture Document id derived for a cycle is the **only adoptable machine
identity** for that cycle's Architecture.

**FROZEN.** Listing Project-contained Documents is **diagnostic and refusal
support only**. It **never** authorizes adoption, **never** authorizes a create,
and **never** substitutes another Document id for the derived id.

**FROZEN — one ordered algorithm.** Discovery, and rediscovery of the
Architecture after a create or a bootstrap write whose outcome is unknown, are
the **same** procedure, run in full each time:

```text
 1  canonicalize the cycle id
 2  derive the expected Architecture Document id
 3  resolve the expected derived id
 4  if the derived id exists, validate ROOT PLACEMENT FIRST
 5  wrong Project, or wrong Project Database placement
      -> CYCLE_FOREIGN_PROJECT, refuse
 6  correct placement, empty body
      -> EMPTY_ARCHITECTURE_SHELL recovery condition (section 14.4);
         the Document exists, so this is NOT state A
 7  correct placement, non-empty, and malformed / schema-invalid /
    digest-invalid / identity-inconsistent
      -> ARTIFACT_MALFORMED, refuse
 8  independently list Project-contained Documents, ONLY to detect additional
    VALID tsa.architecture artifacts carrying the expected project_entity_id,
    the expected canonical cycle_id, valid root placement, and a NON-DERIVED
    Document id
 9  one or more such non-derived same-cycle valid Architecture artifacts exist
      -> CYCLE_AMBIGUOUS, refuse
         (whether the derived id is absent, an empty shell, or valid)
10  derived id physically absent, and none exists
      -> state A; create is permitted at the DERIVED id only
11  derived id valid, and no extra same-cycle candidate exists
      -> adopt the DERIVED id only
```

**FROZEN.** A valid non-derived same-cycle Architecture is **never** adopted,
including when it is the only Architecture artifact that exists for the cycle.
**One** such artifact is sufficient for `CYCLE_AMBIGUOUS`: it conflicts with the
required deterministic identity.

**FROZEN — what counts toward ambiguity.** This contract does not use
"plausible" as a criterion. A non-derived Document counts as a same-cycle
candidate **only** when **all** of these hold:

```text
valid root placement under the expected Project        AND
a non-empty body                                       AND
a valid TSA carrier                                    AND
a valid tsa.architecture schema and digest             AND
project_entity_id == the expected Project entity id    AND
cycle_id          == the expected canonical cycle id   AND
document id       != the expected deterministic id
```

A name match alone is diagnostic only. A malformed Document does **not** become
an ambiguity candidate merely because its name resembles the expected
Architecture name.

**FROZEN — the recoverable empty Architecture shell.** A correctly placed
derived-id Document with an empty body (step 6) is not a refusal, is not yet a
valid Architecture, and is **not state A**: the Document physically exists. It
is the `EMPTY_ARCHITECTURE_SHELL` recovery condition of section 14.4. Steps 8
and 9 still apply to it; only when no non-derived same-cycle candidate exists
may the shell be completed in place, at that same derived id.

Outcomes, and only these:

| Observation | Outcome |
|---|---|
| derived id physically absent; no valid non-derived same-cycle Architecture | State A. Create is permitted, at the derived id only. |
| derived id is a correctly placed empty shell; no valid non-derived same-cycle Architecture | `EMPTY_ARCHITECTURE_SHELL` recovery condition — **not** state A. Complete that shell in place; never create a second Document. |
| derived id valid; no valid non-derived same-cycle Architecture | Adopt the derived id. |
| a valid same-cycle Architecture exists at a non-derived id — alone, or beside the derived id | **Refuse**, `CYCLE_AMBIGUOUS`. Do not adopt it, do not create another. |
| derived id occupied under another Project or the wrong Project Database | **Refuse**, `CYCLE_FOREIGN_PROJECT`. |
| derived id correctly placed, non-empty, malformed or identity-inconsistent | **Refuse**, `ARTIFACT_MALFORMED`. |

**FROZEN — child artifacts.** Rediscovery of a child artifact (Input Manifest,
Process Result, Review Result, Human Decision) after an unknown create or write
outcome has **two levels, both required**. First, cycle-level revalidation
re-establishes the Architecture and cycle identity and the gate preconditions.
Then the child itself is rediscovered by its own deterministic id together with
its expected parent, type and iteration. The Project Architecture listing rules
above **MUST NOT** be used as the test of whether the child mutation landed, and
a direct lookup of the child id **MUST NOT** replace the cycle-level
revalidation. Section 14.4 freezes the rule for bootstrap; the mechanism is
IMPLEMENTATION-SPEC.

### 5.2 Writability

**FROZEN.**

- The Architecture Document is writable **only** through an authorized
  application of an Architect output for that cycle. After APPROVE it is
  **frozen**: a future consumer reads it, and the engine **MUST NOT** write it.
  The one write that precedes any Architect output is the **bootstrap write** of
  section 14.1.2: creating the Document with its bootstrap carrier, or completing
  an empty shell in place with that same carrier (section 8). It carries no
  architecture content.
- The Input Manifest, every Process Result, every Review Result and every Human
  Decision are **immutable once valid**. The engine **MUST NOT** rewrite one.
  A superseding record is a new numbered artifact, never an edit.

**FROZEN.** The Process Result **MUST** carry enough structured output and
history for deterministic recovery (section 14), and **MUST NOT** be treated as
an independent canonical architecture. Where the two disagree, the Architecture
Document is canonical for content and the Process Result is canonical for what
the model returned.

**OBLIGATION / IMPLEMENTATION-SPEC (`U-3`).** Creating a Project-contained
Document is **not** supported by the current adapter (section 17.3). An
implementation MUST add it, and MUST verify the container semantics against the
live workspace before relying on them. The containment authority above is frozen;
only the adapter mechanism is open.

## 6. TSA-local lifecycle

**FROZEN.** The cycle's lifecycle is **derived from its artifacts**. No Fibery
workflow field is added for TSA-C01, and none is required.

Semantic states, and the artifact pattern that defines each:

| State | Holds when |
|---|---|
| `Draft` | Architecture Document exists; no valid Process Result for the current iteration. |
| `Architect Processing` | A Process Result for the current iteration is being produced; recovery rules in section 14 decide what a partial observation means. |
| `Review` | A valid Process Result for the current iteration exists; no valid Review Result for it. |
| `Human Decision` | A valid Review Result for the current iteration exists; no Human Decision for it. |
| `Approved` | A valid APPROVE Human Decision exists, bound as in section 9. |

**FROZEN.**

- **REWORK** is an immutable human decision that authorizes the next iteration
  **for the same Input Manifest**. It does not change scope (section 3.2).
- **APPROVE** is an immutable human decision bound to the exact Architecture,
  Review and inputs (section 9). It **closes the cycle to writes**: after it,
  the engine **MUST NOT** write the Architecture Document or any further
  artifact for that cycle, and a `REWORK` for that cycle **MUST** be refused.
  Further architecture work needs a new cycle (section 3.2).
- `Project.State` and `Project Phase.State` are **not** TSA lifecycle authority
  and **not** approval authority. The engine **MUST NOT** read them as such and
  **MUST NOT** write them.

## 7. Roles and authority

### 7.1 Architect

**FROZEN.** The Architect owns HOW. It produces **one integrated recommended
architecture** — not a catalogue of alternatives. It writes its assumptions,
risks and open architecture questions. It **MUST NOT** change WHAT.

### 7.2 Reviewer

**FROZEN.** The Reviewer is a **separate model invocation**. It independently
verifies the exact Architect output for that iteration. It **MUST NOT** rewrite
the canonical Architecture Document, and **MUST NOT** approve on behalf of a
human. Its output is evidence.

### 7.3 Human

**FROZEN.** The human selects and accepts scope, holds the authority over UX
applicability, decides REWORK or APPROVE, and resolves product semantics outside
TSA.

### 7.4 Unresolved product questions

**FROZEN.** When the Architect finds an unresolved product question:

- it **MUST** preserve the question as evidence;
- it **MUST NOT** answer it;
- if the question is **material to a correct HOW**, approval is **unavailable**
  for that cycle — it is not a risk the human may accept away (section 9.3);
- TSA **MUST NOT** mutate the Requirement workflow, content, state or relations
  to resolve it;
- after the Requirement is separately changed and approved through the existing
  Requirement lifecycle, a **new TSA cycle** is started (section 3.2).

### 7.5 Contradiction between Applied Requirements

**FROZEN.** When admitted Requirements contradict each other:

- every source of the contradiction **MUST** be surfaced;
- the engine **MUST NOT** pick a silent winner;
- a model **MUST NOT** remove a Requirement from scope;
- if no valid common HOW exists, usable approval **MUST** be blocked.

## 8. Architecture content schema

**FROZEN — the lifecycle boundary.** The Architecture Document has two lifecycle
points, separated by the first application of an Architect output.

**Before the first Architect output is applied**, the Architecture Document is a
**bootstrap identity and recovery carrier**. It is **exempt** from:

- the 16-heading representation below;
- the *Mandatory*-section substantive-content rules;
- the traceability rendering rules of section 8.1.

It **MUST NOT** be interpreted as approved or applied Architecture content, and
it **MUST NOT** fabricate placeholder or N/A sections in order to appear to
satisfy this section.

**After the first Architect output is applied**, the Architecture Document
**MUST** use all 16 frozen headings, and every section, content and traceability
rule of this section applies in full.

The exact pre-apply bytes the writer emits, and the one accepted read-back form,
are specified by `docs/specs/TSA-C01-Implementation-Spec-v0.2.md` §4.1.1. This
exemption amends text that v0.1 froze unconditionally, which is why it is made in
a new contract version rather than in the implementation specification.

**FROZEN — bootstrap emission form and accepted read-back form.** These are two
distinct concepts, and neither is defined by the other.

- **Emission form.** The writer **MUST** emit the bootstrap carrier exactly,
  ending in exactly one final newline.
- **Accepted read-back form.** Let `W` be the exact text emitted and `R` the
  Markdown Fibery returns on read-back. The read-back is conforming **iff**
  `R == W`, **or** `W` ends with one final `\n` and `R` equals `W` with that
  **one** final `\n` removed.

**No other difference is accepted** by bootstrap lifecycle validation: no heading
rewrite, no sentence rewrite, no extra or missing blank line, no change of any
kind inside the JSON fence — whose payload **MUST** remain byte-for-byte
identical — no envelope change, no second fence and no additional Markdown.

This single allowance reflects verified transport behaviour and nothing wider.
The accepted I03 live evidence observed that the emitted final LF was removed,
that the JSON fence was preserved byte for byte, and that the document
fingerprint was stable. It did **not** observe whole-Markdown byte identity, and
this contract does not claim it.

**FROZEN.** Passing the low-level envelope parser is **not** sufficient
bootstrap validation. Bootstrap lifecycle validation requires **both** the
read-back equivalence above **and** envelope parse, schema, digest and identity
validation. A read-back may parse successfully and still fail it.

**FROZEN — bootstrap identity and context are never self-asserted.** The
identity and context of a bootstrap Architecture **MUST NOT** be accepted from
the Document's own metadata. Before a non-empty pre-apply Architecture Document
is classified B, every externally knowable value it carries — the workspace
identity, the Project entity id, the Project Code, the cycle id in the envelope
and in the body, and the Project Code and cycle id shown in its level-1 heading
— **MUST** equal a **trusted expected** value obtained independently of that
Document: the engine's current workspace identity, the freshly resolved target
Project, and the canonical cycle id supplied to discovery. The expected text
against which a read-back is compared **MUST** be built from those trusted
values, never from values parsed out of the read-back itself.

A valid artifact digest proves only that the artifact is internally consistent.
It proves **nothing** about ownership or context, and a self-consistent artifact
carrying the wrong workspace identity, Project entity id, Project Code or cycle
id **MUST NOT** be accepted because its digest recomputes correctly. At the
correctly placed derived id such content is `ARTIFACT_MALFORMED` (section 14.4,
state E): no overwrite, no repair, no model call, and no second Architecture
Document. Placement precedence is unchanged — a wrongly placed derived id is
still `CYCLE_FOREIGN_PROJECT`, never malformed.

**FROZEN — Project Code is conformance, not machine identity.** The Project
entity id participates in machine identity; the Project Code does **not**, and
the deterministic Document id does not include it (section 5.1). The Project
Code is nevertheless validated carrier metadata and human-navigation content: a
conforming bootstrap carrier **MUST** carry the freshly resolved Project's code,
in the envelope and in the heading. Where the target Project has no code, no
bootstrap carrier can conform; the engine refuses before accepting B and
**MUST NOT** invent a code.

**FROZEN — required Project metadata before any bootstrap mutation.** Before any
Architecture bootstrap create or write that requires the canonical Architecture
name or carrier, the engine **MUST** hold a freshly resolved, non-empty Project
Code for the target Project. Where that required trusted Project metadata
cannot be established, the engine:

- **MUST NOT** create an Architecture Document;
- **MUST NOT** write into an existing `EMPTY_ARCHITECTURE_SHELL`;
- **MUST NOT** invent, default or derive a Project Code;
- **MUST NOT** call a model;
- **MUST** return a controlled refusal **before** the remote mutation.

This applies at least to state A, before the Architecture Document is created —
the command already knows it could not complete the carrier, so it does not
deliberately leave an empty shell behind — and to `EMPTY_ARCHITECTURE_SHELL`,
before the bootstrap carrier is written, for both `start` and `resume`. In the
second case the Document remains `EMPTY_ARCHITECTURE_SHELL`: no transition to B
and no automatic retry.

The refusal is that required Fibery data could not be obtained in usable form,
`FIBERY_READ_FAILED`. It is **not** `ARTIFACT_MALFORMED`: on the state A path no
Architecture artifact exists yet. It is **not** `FIBERY_WRITE_FAILED`: no write
was attempted. It is **not** `CYCLE_NOT_FOUND`: nothing about cycle identity is
absent.

This is intentionally different from the durable case, which is unchanged:

```text
PRE-WRITE                   no conforming artifact can be constructed, because
                            required trusted Project metadata is unavailable
                            -> controlled refusal, FIBERY_READ_FAILED;
                               no bootstrap mutation
DURABLE NON-EMPTY DOCUMENT  the artifact exists but cannot satisfy the required
                            external carrier binding
                            -> ARTIFACT_MALFORMED; no overwrite, no repair,
                               no model call
```

`rework`, `approve` and `inspect` attempt no bootstrap write and keep their
frozen behaviour (section 14.4).

**FROZEN.** The one persisted value a restarted process may reuse when it
rebuilds the expected carrier is the bootstrap creation timestamp, because no
journal or local intent record exists from which it could be recovered. It may
be reused **only after** the artifact has passed schema and digest validation
and every externally knowable field has been checked against its trusted
expected value. The timestamp establishes no workspace, Project, Project Code,
cycle or Document identity. The mechanism is IMPLEMENTATION-SPEC (§4.1.1 of the
implementation specification).

**FROZEN.** After the first Architect output is applied, the Architecture
Document has exactly these headings, in this order:

| # | Heading | Class |
|---|---|---|
| 1 | Scope & Inputs | Mandatory |
| 2 | Requirement Traceability | Mandatory |
| 3 | Solution Structure | Mandatory |
| 4 | Components & Responsibilities | Mandatory |
| 5 | Interfaces & Data Flows | Mandatory |
| 6 | Data / Storage | Content-or-N/A |
| 7 | External Integrations | Content-or-N/A |
| 8 | Security / Authentication / Authorization | Content-or-N/A |
| 9 | Deployment / Runtime Model | Content-or-N/A |
| 10 | Failure / Recovery | Content-or-N/A |
| 11 | Observability | Content-or-N/A |
| 12 | Migration Implications | Content-or-N/A |
| 13 | Architecture Decisions / Trade-offs | Mandatory |
| 14 | Assumptions | Content-or-N/A |
| 15 | Risks | Content-or-N/A |
| 16 | Open Architecture Questions | Content-or-N/A |

**FROZEN.** *Mandatory* means the section MUST hold substantive content; N/A is
not an admissible value. *Content-or-N/A* means the section MUST hold either
substantive content or an explicit, briefly reasoned N/A.

### 8.1 Traceability

**FROZEN.** Requirement Traceability MUST cover **every** included Requirement
exactly once, or under a one-to-many representation that is explicitly declared
and deterministically validated so that each included Requirement is still
reachable exactly once through it.

**FROZEN.** No included Requirement may disappear through an Architect N/A.
Removing a Requirement from coverage is a human scope decision (section 2), never
an Architect classification.

### 8.2 Prohibited content

**FROZEN.** The Architect **MUST NOT** produce:

- new product obligations;
- answers to unresolved WHAT questions;
- Epics, Stories or Tasks;
- estimates, sprints or schedules;
- implementation assignments;
- generated code or configuration;
- deployment execution;
- any mutation of Requirement state, content or relations.

## 9. Approval binding

**FROZEN.** An APPROVE Human Decision binds exactly:

- Project entity id **and** cycle id;
- iteration ordinal;
- Architecture Document identity **and** content fingerprint;
- Input Manifest digest;
- UX evidence digest — the content digest of section 4.1 with its scope binding, or the `NOT_APPLICABLE` record digest;
- Process Result identity and payload digest;
- Review Result identity and payload digest;
- the accepted finding and risk dispositions, each named individually.

### 9.1 What cannot be waived

**FROZEN.** Missing, stale or structurally invalid evidence **MUST NOT** be
accepted as a risk. Specifically, approval is unavailable when any bound artifact
is absent, fails validation, or belongs to a different iteration, manifest or
cycle. This is a structural block, not a severity judgement.

### 9.2 What may be accepted

**FROZEN.** Technical risks and trade-offs **MAY** be explicitly accepted by the
human, individually, and the acceptance is recorded in the decision.

### 9.3 What may not be accepted

**FROZEN.** A **material unresolved WHAT** question (section 7.4) **MUST NOT** be
accepted away inside TSA. It is resolved in the Requirement lifecycle, and the
cycle is restarted.

### 9.4 Identity of the approver

**FROZEN.** The engine **MUST NOT** claim an authenticated human identity that
the runtime does not provide. A decision records that a human operating this
command made it; it **MUST NOT** assert who, unless and until the runtime
supplies authenticated identity.

**DEFERRED.** Authenticated approver identity.

## 10. Freshness and revalidation

**FROZEN.** Requirement-side content reuses the **current canonical Markdown
fingerprint semantics** (`document_fingerprint`, manifest v2) where applicable.
An implementation **MUST NOT** introduce a second fingerprint algorithm for
Requirement documents.

**FROZEN.** TSA-specific JSON artifacts (Input Manifest, Process Result, Review
Result, Human Decision) get **their own versioned canonical digest**. They
**MUST NOT** be presented as, compared with, or stored as Requirement
normative-tree manifests.

**OBLIGATION.** Revalidation MUST run:

1. before the Input Manifest is frozen;
2. before each model call;
3. after each model call, before its output is applied;
4. before a human approval is recorded;
5. after approval is recorded;
6. whenever a downstream consumer validates an approval.

**FROZEN.** UX currentness is **not** defined here. Section 4.4 holds the one
discriminator-aware definition, and revalidation **MUST** apply it as written:
the `APPLICABLE` checks when the recorded value is `APPLICABLE`, the
`NOT_APPLICABLE` checks when it is `NOT_APPLICABLE`. A recovery path **MUST NOT**
use a weaker definition, and no path **MUST** demand a UX Document under
`NOT_APPLICABLE`.

**FROZEN.** This is **optimistic validation, not an atomic transaction**. Several
Fibery reads do not form a snapshot. The engine **MUST NOT** claim protection
against all concurrent external edits; it detects a changed input and refuses,
it does not prevent the change.

## 11. Artifact versioning

### 11.1 Reused, unchanged

**FROZEN.** Requirement normative tree manifest **v2**, Process Result **0.3**,
Review Result **0.3** and `document_fingerprint` are consumed as they exist. This
contract does not extend, reinterpret or re-version them.

### 11.2 New, TSA-owned

**OBLIGATION.** Each TSA artifact carries its own schema version and its own
canonical digest definition, declared in the implementation specification.

**IMPLEMENTATION-SPEC (`U-4`).** The exact digest algorithm, field ordering and
serialization of the TSA JSON artifacts. That each artifact carries its own
version and its own canonical digest is frozen above; only the mechanism is
open, and an implementation agent **MUST NOT** choose it silently.

## 12. Execution commands

**FROZEN.** The proposed first-slice interface is:

```text
sdlc project architecture start
sdlc project architecture resume   --cycle <id>
sdlc project architecture rework   --cycle <id>
sdlc project architecture approve  --cycle <id>
sdlc project architecture inspect  --cycle <id>
```

**These MUST NOT be implemented now.** They are recorded so the contract is
reviewed against a concrete surface.

**FROZEN.** Execution is **explicit and synchronous**. `sdlc worker run`
**MUST NOT** be extended for TSA-C01, and no TSA work is dispatched by the
state-driven runner.

### 12.1 Start idempotency

**FROZEN.** The semantic identity of a start operation is fixed **before the
first Fibery mutation**:

- every start **MUST** carry a stable, caller-supplied **cycle id**, known
  before the first remote mutation;
- the cycle id **is** the start idempotency key;
- retrying `start` with the same cycle id refers to **the same** TSA cycle, and
  resolves to one of the bootstrap states in section 14.4, or to the
  `EMPTY_ARCHITECTURE_SHELL` recovery condition defined there;
- starting another cycle **MUST** use a different cycle id, even when the
  Requirement scope is identical;
- the engine **MUST NOT** generate a local-only cycle identity after it has
  begun remote mutations, because such an identity cannot be recovered.

**IMPLEMENTATION-SPEC (`U-7`).** Exact flags, scope-selection syntax for
`start`, and output rendering. The command set and the start idempotency key are
frozen above and in section 12.1; only the spelling is open.

## 13. Single writer

**FROZEN.** The existing workspace guard is reused where valid. The guarantee is
exactly:

- cooperating SDLC commands in the **same workspace**, on the **same host**, as
  the **same OS user**, sharing the standard lock directory, mutually exclude;
- this is **not** a distributed lock, and **MUST NOT** be described as one;
- the Fibery UI, another host, and another OS user **can** race;
- unsupported external concurrency is handled by optimistic revalidation
  (section 10), which detects and refuses — it does not prevent.

## 14. Recovery

### 14.1 The Recovery Validation Gate

**FROZEN.** Before **any** of the cases in section 14.3 is applied, the engine
**MUST** establish a Recovery Validation Gate. The cases are the action table
**after** the gate, never an alternative to it.

**FROZEN — the gate failure rule.** This rule governs both stages below and
admits no exception. If **either** the bootstrap validation gate (14.1.2) or the
normal recovery validation gate (14.1.1) fails, the engine:

- **MUST** perform **no mutation** — not a recovery write, not a bootstrap
  write, not any other write;
- **MUST** perform **no model call**;
- **MUST** return a controlled refusal, naming the offending artifact by
  controlled identity.

A bootstrap write is permitted **only after the bootstrap gate succeeds**. No
clause elsewhere in this contract authorizes a mutation once a gate has failed.

**FROZEN.** The gate has **two stages**, selected by whether a valid accepted
Input Manifest exists. The distinction is not a relaxation: each stage validates
every fact that already exists at that point.

| Stage | When | Gate |
|---|---|---|
| **Bootstrap gate** | No valid accepted Input Manifest yet — durable states A and B and the `EMPTY_ARCHITECTURE_SHELL` recovery condition of section 14.4, plus the command-local `C` phase inside one `start` invocation | Section 14.1.2 |
| **Normal gate** | A valid accepted Input Manifest exists — state D onward | Section 14.1.1 |

State E of section 14.4 is not a third stage: it is what a **failed** bootstrap
gate classifies, and the gate failure rule above governs it.

#### 14.1.1 Normal gate

**FROZEN.** Applies to every recovery **after** a valid accepted Input Manifest
exists. It **MUST** validate at least:

1. exact cycle identity;
2. expected Project ownership;
3. artifact uniqueness;
4. required parentage and containment;
5. schema and payload parsing;
6. declared payload digests;
7. Input Manifest integrity and its human-acceptance binding;
8. exact Process / Review / Decision lineage;
9. Requirement input currentness;
10. UX input currentness, under the discriminator-aware definition of
    section 4.4 — and only the branch the recorded value selects;
11. the Architecture fingerprint the candidate case needs;
12. absence of conflicting Human Decisions.

**FROZEN.** A failure of this gate is governed by the gate failure rule in
section 14.1: no mutation, no model call, controlled refusal.

**FROZEN.** Three consequences that follow from the gate and are stated so they
cannot be argued away case by case:

- A persisted Process output **MUST NOT** be replayed when the current
  Requirement or UX inputs are stale. Recovery **MUST NOT** bypass freshness.
- A Review Result **MUST NOT** restore the `Human Decision` state unless it is
  bound to the exact current Process, Architecture and input tuple.
- An `APPROVE` decision **MAY** remain as history while currentness is stale.
  `resume` **MUST NOT** make a stale historical approval current.

**FROZEN.** Duplicate Process Results or duplicate Review Results for one
iteration, and conflicting `REWORK`/`APPROVE` decisions for one iteration, fail
the gate (criteria 3, 8 and 12) **before** any recovery action is chosen.

#### 14.1.2 Bootstrap gate

**FROZEN.** Applies to durable states **A and B** of section 14.4, to the
`EMPTY_ARCHITECTURE_SHELL` recovery condition of that section, and to the
command-local `C` phase within one `start` invocation, **before** a valid
accepted Input Manifest exists.

**FROZEN.** The absence of an Input Manifest **Document** — and therefore of the
human acceptance that Document carries — is **not** a gate failure at this
stage: that artifact is precisely what bootstrap is creating. Criteria 7, 8, 9,
10 and 11 of the normal gate are therefore not yet applicable.

**FROZEN.** That exemption covers **absence only**. An Input Manifest Document
that **exists** but is empty, or is non-empty without valid acceptance, or
otherwise fails its schema, **is** a gate failure (section 14.4, state E).

**FROZEN.** Everything that already exists **MUST** still be validated. The
bootstrap gate **MUST** check at least:

1. a stable cycle id;
2. exact Project ownership;
3. Architecture deterministic identity under section 5.1.1, including the
   absence of any valid non-derived same-cycle Architecture;
4. root placement of the derived Architecture id under that Project entity;
5. cycle metadata consistency;
6. no conflicting or malformed non-empty bootstrap artifact, and no empty Input
   Manifest shell;
7. no evidence that this cycle was already completed under another state.

**FROZEN.** **Once the bootstrap gate has succeeded**, only the **minimum
bootstrap write** needed to advance A → B → accepted Manifest is permitted at
this stage. From the `EMPTY_ARCHITECTURE_SHELL` condition the first step is the
in-place carrier write into the existing Document, never a create, and it too
ends at B. A failed bootstrap gate permits **zero** writes. The step from B to
an accepted Manifest passes through the command-local `C` phase, which commits
nothing of its own: the Manifest create is the single atomic write that carries
the cycle from B to D.

**FROZEN.** Before a valid accepted Input Manifest exists, the engine **MUST
NOT**:

- make an Architect model call;
- replay a persisted Process output;
- make a Reviewer call;
- record a human `APPROVE`;
- enter any normal recovery case that requires accepted inputs.

**FROZEN.** Once a valid accepted Input Manifest exists, bootstrap classification
**ends** and the normal gate of section 14.1.1 applies in full.

**FROZEN.** A failure of this gate is governed by the gate failure rule in
section 14.1: no mutation, no model call, controlled refusal. Neither stage
introduces a second state store or a journal — both classify from durable Fibery
state alone.

### 14.2 Mutation discipline

**FROZEN.** Around every recovery mutation:

- **before** the write, revalidate the preconditions immediately, not once at
  the start of the command;
- **after** the write, read back immediately and validate that the **intended
  durable result** was established;
- if drift is observed on read-back, the engine **MUST NOT** report a successful
  or current transition.

**FROZEN.** The order is: prepare → pre-write revalidation → mutate → immediate
read-back → validate the intended durable result → success **only if** that
validation passes. A write call that returned normally is **not** evidence that
its result is durable. A read-back that does not establish the intended durable
result is not success, and the engine **MUST NOT** retry the mutation blind
within the same command.

### 14.3 Case table

**FROZEN.** Every case below is defined, and each is reached only through the
gate. In all of them the engine **MUST NOT** blindly retry a mutation after an
unknown transport result (case 9).

| # | Observed state | Required behaviour |
|---|---|---|
| 1 | Input Manifest exists, no valid Process Result | Resume at `Draft`: the Architect call for the current iteration may be made. |
| 2 | Process Result exists, Architecture Document content equals the **input** it recorded | The output was not applied. Apply the recorded output; do not re-invoke the model. |
| 3 | Process Result exists, Architecture Document content equals the **output** it recorded | Application completed. Advance to `Review`; do not re-apply, do not re-invoke. |
| 4 | Architecture Document content matches **neither** input nor output | Refuse. Report the divergence with all three fingerprints. Do not overwrite, do not guess which is authoritative, do not re-invoke. Human decision required. |
| 5 | A Review Result already exists for the current iteration | Do not re-invoke the Reviewer. Advance to `Human Decision`. |
| 6 | A Human Decision already exists for the current iteration | Honour it. REWORK opens iteration N+1 for the same manifest; APPROVE means the cycle is `Approved` and closed to further writes. |
| 7 | An empty Result shell exists (document created, body never written) | Complete that shell in place for its own iteration, or refuse with the shell named. Never silently create a second numbered artifact for the same iteration. |
| 8 | A non-empty Result exists but is malformed | Refuse. Do not repair it, do not overwrite it, do not treat it as absent. Report its identity. |
| 9 | Create or write returned an unknown outcome (timeout, dropped connection) | Re-read before any further write, at **both** levels: cycle-level revalidation through the gate, **then** rediscovery of the specific mutation target by its own artifact class's deterministic identity and placement rules. The procedure of one artifact class **MUST NOT** be substituted for another. Classify into cases 1–8 from what is actually there. **MUST NOT** retry the mutation blind. During bootstrap, section 14.4 governs. |
| 10 | Restart at a human boundary (`Review` complete, no decision) | Present the exact iteration's evidence again. Do not re-invoke any model. Do not assume the previous presentation implies a decision. |

### 14.4 Initial bootstrap states

**FROZEN.** A cycle is classified by its cycle id. The durable lifecycle state
set is exactly **{A, B, D, E}**. Discovery first produces **either** the
`EMPTY_ARCHITECTURE_SHELL` recovery condition defined below **or** exactly one of
those lifecycle states; it never returns command-local `C`.
`EMPTY_ARCHITECTURE_SHELL` is a recovery observation that precedes B, not a fifth
state: after the empty shell has been completed in place and its read-back
validated, the condition resolves to **B**. States A and B precede a valid
accepted Input Manifest and are reached through the bootstrap gate (section
14.1.2); state D leaves bootstrap entirely.

| | Durable state | Required behaviour |
|---|---|---|
| **A** | The deterministic Architecture Document **does not exist**: the derived Architecture id (section 5.1.1) is physically absent, and no valid non-derived same-cycle Architecture exists | Create the Architecture Document at the derived id, contained directly by the Project entity. Creation alone does **not** establish B: the created Document is an `EMPTY_ARCHITECTURE_SHELL` until its bootstrap carrier is written and validated. Never create a second Document. |
| **B** | Exactly one valid derived-id Architecture **bootstrap** Document exists for this cycle — its bootstrap carrier is durable — and **no Input Manifest Document exists** that causes a more specific bootstrap refusal (E) or a valid accepted Manifest transition (D) | Resume bootstrap for that **same** cycle, only after validating Project ownership and cycle identity. The Document's existence **MUST NOT** imply acceptance: explicit human manifest acceptance is still required before any Architect call. |
| **D** | A **valid, accepted** Input Manifest exists | **Bootstrap is complete.** Run the **normal recovery classification** of section 14.3 under the normal gate (14.1.1). State D **MUST NOT** be read as "case 1". |
| **E** | A refusing bootstrap state — exactly one of the conditions listed below | **Refuse.** No mutation, no model call. Do not create a second cycle under the same cycle id. |

**FROZEN — what A is and is not.** State A means exactly that the expected
deterministic Architecture Document is **physically absent**. It **never** means
"no valid Architecture", missing valid Architecture content, an empty
Architecture body or an invalid Architecture body:

```text
derived Architecture Document physically absent     -> A
derived Architecture Document present, body empty   -> EMPTY_ARCHITECTURE_SHELL
derived Architecture Document present, non-empty,
  malformed or identity-inconsistent                -> E, ARTIFACT_MALFORMED
```

**FROZEN — `CYCLE_NOT_FOUND`.** `CYCLE_NOT_FOUND` means that no Architecture
Document exists for this cycle id. It **MAY** be returned only when the
deterministic Architecture Document is physically absent, under the applicable
command semantics. It **MUST NOT** be returned for an empty Architecture shell, a
malformed Architecture, a foreign Architecture or an ambiguous identity — by any
command.

**FROZEN — the `EMPTY_ARCHITECTURE_SHELL` recovery condition.** It means exactly:
the deterministic Architecture Document exists at the expected id, has valid root
placement under the expected Project, and
`read_document_content(...).strip() == ""`.

It is an observable recovery condition **before B**. It is **not** A, **not** B,
**not** `C`, **not** D and **not** E; it is not a new persisted marker, not a new
artifact type and not a new lifecycle state letter. The Document **identity** is
durable; its lifecycle state has not yet reached B, because the bootstrap
metadata and carrier have not become durable.

Steps 8 and 9 of section 5.1.1 still run against it: where a valid non-derived
same-cycle Architecture exists, the outcome is state E, `CYCLE_AMBIGUOUS`, and
the shell is not completed.

**FROZEN — recovery of the empty Architecture shell.** The engine adopts **that
same** Document id. After the bootstrap gate succeeds, it **MAY** write the exact
bootstrap carrier into that same Document, through exactly this mutation cycle:

```text
fresh placement validation
-> write the exact bootstrap carrier
-> read back
-> validate the accepted bootstrap read-back form   (section 8)
-> only then B
```

No second Architecture Document may be created. No model call is made merely to
recover the shell.

**FROZEN — creation alone does not establish B.** In state A, after the bootstrap
gate succeeds, creating the deterministic Architecture Document does **not**
establish B. Before its content is written, the newly created Document is
durably observable as `EMPTY_ARCHITECTURE_SHELL`, and the engine **MUST** write
and validate the exact bootstrap carrier before B exists:

```text
A
-> create the deterministic Architecture Document
-> EMPTY_ARCHITECTURE_SHELL
-> bootstrap carrier write and read-back validation
-> B
```

No second Document id is ever used. A successful create response alone **MUST
NOT** open the success path of `start`: `ARCHITECTURE_CYCLE_STARTED` is returned
only when the complete command later reaches its normal Review boundary.

**FROZEN — one bootstrap carrier write contract.** There is exactly **one**
bootstrap carrier write contract. It applies identically whether the target
`EMPTY_ARCHITECTURE_SHELL` is a Document just created by the current state A
invocation, or an empty deterministic Architecture Document rediscovered from an
earlier invocation or crash. The origin of the empty shell changes **none** of:
the emitted carrier, the trusted-context validation, the read-back equivalence
and its single terminal-newline allowance, the result classification, the retry
discipline, and the rule for the transition to B. No separate "new-create" and
"recovery" write semantics exist.

Where the create landed but the process stopped before a validated carrier
write, a restart discovers `EMPTY_ARCHITECTURE_SHELL` — not A, B, `C`, D or E —
and the recovery above completes the **same** deterministic Document in place.

**FROZEN — an unsuccessful bootstrap carrier write is never success.** For a
bootstrap carrier write to an `EMPTY_ARCHITECTURE_SHELL` of either origin, after
the carrier write call has returned normally, the immediate read-back decides
the outcome, and these cases **MUST NOT** be collapsed:

| Immediate read-back | Durable observation | Outcome of the current command |
|---|---|---|
| The read itself fails | Not established by this read | The read-failure and unknown-outcome rules already frozen (section 14.3 case 9, and the two-level rule below). Not redefined here. |
| The read succeeds and returns empty or whitespace-only content | Still `EMPTY_ARCHITECTURE_SHELL` | `FIBERY_WRITE_FAILED`, exit 1. The intended bootstrap write has **not** been validated as durable. No transition to B, no model call, no second write and no retry in the same command. |
| The read succeeds and returns non-empty content that fails carrier, schema, digest, external-binding or read-back-form validation (section 8) | State E, malformed | `ARTIFACT_MALFORMED`, exit 1. No overwrite, no repair, no model call, no transition to B. |
| The read succeeds and the content passes all of section 8 | B | The transition is validated; the command continues. |

An empty immediate read-back is **not** `ARTIFACT_MALFORMED`, because an empty
body is a class of its own, and it is **not** a read failure, because the read
succeeded. A later command may rediscover `EMPTY_ARCHITECTURE_SHELL` and apply
the same in-place recovery again, after the bootstrap gate. `FIBERY_WRITE_FAILED`
here is an execution failure inside the attempted transition of `start` or
`resume`; it is not a durable state and adds no row to the table below. Nor
does the pre-write refusal of section 8: where the required Project Code cannot
be established, `start` and `resume` refuse before the carrier write, the
Document remains `EMPTY_ARCHITECTURE_SHELL`, and the table below is unchanged.

**FROZEN — command semantics under `EMPTY_ARCHITECTURE_SHELL`.** The condition is
**not** routed through state A:

| Command | Behaviour | Result |
|---|---|---|
| `start` | The bootstrap gate validates the existing shell; the bootstrap carrier is completed **in place**; the cycle is then B; the normal `start` bootstrap continues with the caller-supplied inputs. No Architect call occurs until a valid accepted Manifest exists. | The normal `start` result — `ARCHITECTURE_CYCLE_STARTED` when the command reaches the Review boundary. The shell repair introduces no final result code of its own. |
| `resume` | The bootstrap gate validates the existing shell; the bootstrap carrier is completed **in place**; the command stops at B. No model call. | `ARCHITECTURE_CYCLE_RESUMED`, exit 0: the existing durable cycle advanced from an empty shell to recoverable B. |
| `rework` | No shell recovery write, no model call. The exact Review target cannot be current. | `REVIEW_NOT_CURRENT`, exit 1. |
| `approve` | No shell recovery write, no model call. The exact Review target cannot be current. | `REVIEW_NOT_CURRENT`, exit 1. |
| `inspect` | Read-only. | `INSPECT_INCOMPLETE`, exit 0. |

No command returns `CYCLE_NOT_FOUND` while the deterministic Architecture
Document physically exists.

**FROZEN — an empty Architecture is not an empty Manifest.** The two empty
bootstrap Documents are completely distinct and **MUST NOT** be merged under
generic "empty shell" wording:

```text
empty Architecture Document    -> EMPTY_ARCHITECTURE_SHELL: recoverable in place,
                                  a recovery condition before B
empty Input Manifest Document  -> E, MANIFEST_SHELL_UNRECOVERABLE: not
                                  recoverable, no write, no model call
```

**FROZEN — what B is and is not.** The Input Manifest Document decides between
B, D and E, and "no valid accepted Manifest" **MUST NOT** be read as swallowing
a malformed or unrecoverable Manifest into ordinary B:

```text
no Input Manifest Document at all                  -> B
an empty Input Manifest shell                      -> E, MANIFEST_SHELL_UNRECOVERABLE
a non-empty malformed Input Manifest, including
  one missing its required acceptance              -> E, ARTIFACT_MALFORMED
a valid accepted Input Manifest                    -> D
```

**FROZEN — what D is and is not.** State D holds **only** when a valid accepted
Input Manifest exists. Then bootstrap ends and the normal recovery
classification applies. State D **never** means merely that a Manifest Document
exists, that acceptance is missing, that the Manifest is an empty shell, or that
it is malformed.

**FROZEN — the conditions of E.** State E is not only "ambiguous or foreign".
Each condition has its own classification:

| Condition | Classification |
|---|---|
| A valid same-cycle Architecture exists at a non-derived id (section 5.1.1) | `CYCLE_AMBIGUOUS` |
| The derived Architecture id is occupied under another Project or the wrong Project Database | `CYCLE_FOREIGN_PROJECT` |
| A non-empty bootstrap artifact — the derived Architecture, or the Input Manifest — is malformed, identity-inconsistent, missing required acceptance, or carries conflicting bootstrap metadata | `ARTIFACT_MALFORMED` |
| The Input Manifest carries an acceptance bound to a different manifest digest (section 3.3) | `MANIFEST_ACCEPTANCE_MISMATCH` |
| The Input Manifest Document exists but is empty | `MANIFEST_SHELL_UNRECOVERABLE` |

A malformed bootstrap state is refused **as state E**. It **MUST NOT** be routed
through state D and case 8 of section 14.3 to obtain its classification: without
a valid accepted Manifest the durable state is not D. Case 8 keeps its meaning
for a malformed artifact discovered after bootstrap has completed.

**FROZEN — `inspect` in state E.** For `inspect`, **every** condition of E —
ambiguous identity, foreign derived placement, a malformed non-empty bootstrap
artifact, an acceptance mismatch and an empty Input Manifest shell — reports
`INSPECT_INCOMPLETE`, exit 0, read-only, with no mutation and no model call. The
lifecycle state can be reported, but discovery has failed before the complete
bound-input currentness can be established, so no E condition is reported as
current.

**FROZEN — the empty Input Manifest shell.** An empty Input Manifest Document is
**unrecoverable**. It is **not** the command-local `C` phase, it is **not**
completed from the current command arguments, and it permits **no write and no
model call**. Recovery requires a new cycle id and manual inspection of the
shell, which is left untouched. It is nevertheless **not** called malformed: an
empty shell stays structurally distinct from non-empty malformed content.

**FROZEN — C is command-local, never durable.** `C` names one phase *inside a
single live `start` invocation*: **after** the caller's Manifest inputs and the
required explicit acceptance flags have been validated, and **before** the
atomic valid Input Manifest artifact becomes durable.

No command can **begin** in `C`. No recovery process rediscovers `C`. No
persisted artifact denotes `C`.

There is no conforming persisted artifact that represents "manifest complete,
acceptance incomplete". The Input Manifest is **atomic**: a `tsa.input_manifest`
requires `manifest_body`, `manifest_digest` and `acceptance` together, and
`acceptance` requires `accepted = true`. A non-empty Manifest Document lacking
acceptance is malformed (state E), not a state of its own.

Therefore:

- `C` is **not** persisted;
- `C` is **never** returned by durable discovery;
- `C` is **never** reconstructed after a restart;
- `C` is **never** a command entry point.

What rediscovery sees instead:

```text
process stopped before the atomic Manifest create landed  -> B
the atomic Manifest create landed and validates           -> D
the Manifest Document exists but is empty                 -> E, unrecoverable
                                                             empty Manifest
                                                             shell
the Manifest Document is non-empty but lacks acceptance,
  or otherwise fails its schema                           -> E, malformed
```

Acceptance is **not** made optional, `accepted = false` is **not** introduced,
acceptance is **not** split into a second artifact, and no new durable marker is
created.

**FROZEN.** In state D, section 14.3 decides the case from durable state, not
from the fact that a command was re-issued: case 1 **only** when no valid
Process Result exists; cases 2 or 3 when a Process Result exists; case 5 when a
Review Result exists; case 6 when a Human Decision exists; cases 4, 7, 8 and 9
on the divergences they name.

**FROZEN.** A repeated `start` for the same cycle id **MUST** therefore recover
the **actual durable state**, never assume `Draft`. In particular:

- retry after Review ⇒ the `Human Decision` boundary, and **no model call**;
- retry after `APPROVE` ⇒ approved / historical-currentness handling, with **no
  writes and no rework**;
- retry **never** creates a second cycle for the same cycle id.

**FROZEN — after an unknown bootstrap mutation outcome: two levels.** After
**any** unknown bootstrap mutation outcome — a create or a write, of the
Architecture Document or of the Input Manifest — the engine **MUST**, before any
further mutation:

1. perform cycle-level rediscovery/revalidation sufficient to establish the
   current Architecture/cycle identity and bootstrap gate preconditions;
2. rediscover the specific mutation target using that artifact class's
   deterministic identity and placement rules;
3. classify durable state;
4. only then decide whether retry with the **same** deterministic id is
   permitted.

Every unknown bootstrap mutation outcome requires the cycle-level revalidation;
the artifact whose mutation outcome is unknown is rediscovered by the procedure
of **its** artifact class. The procedure of one artifact class **MUST NOT** be
substituted for another. Classification yields the `EMPTY_ARCHITECTURE_SHELL`
condition or one of **A, B, D or E** — never command-local `C`. **No blind
duplicate create.**

**FROZEN — Architecture target.** For an unknown outcome affecting the
Architecture Document itself — the root create, or the bootstrap carrier write —
the engine reruns the **full** discovery of section 5.1.1, never a direct lookup
of the derived id alone: the deterministic derived id, root placement, the
empty / bootstrap / malformed classification, non-derived same-cycle conflict
detection and foreign detection. For this target that one procedure is **both**
the cycle-level revalidation and the artifact-specific rediscovery; no separate
child procedure applies. A retried Architecture create is permitted only in
state A, and only at the same derived id. A retried carrier write is permitted
only under `EMPTY_ARCHITECTURE_SHELL`, and only into that same Document.

The two windows stay distinct. After an **unknown create** outcome in state A,
the full discovery may observe the derived Document absent, an
`EMPTY_ARCHITECTURE_SHELL`, a valid B, or a malformed, foreign or ambiguous
state, and recovery follows that durable state. After a **known** create success
followed by an **unknown carrier write** outcome, the Document is already known
to exist: the same full rediscovery is performed, and the engine **MUST NOT**
issue another Document create.

**FROZEN — Input Manifest target.** For an unknown outcome affecting the Input
Manifest child, **first** the engine reruns cycle-level Architecture and
bootstrap validation sufficient to prove that:

- the deterministic Architecture identity is still unambiguous;
- the expected root placement is still valid;
- no new foreign or non-derived Architecture conflict exists;
- the cycle has not moved into a conflicting state.

**Then** it rediscovers the Input Manifest itself by its deterministic **child**
id, validating the exact deterministic Input Manifest id, the expected
Architecture parent, child placement, empty versus non-empty, carrier, schema and
digest, and the acceptance binding. It then classifies:

```text
child absent                                -> the original child create did not
                                               become durable; a retry MAY be
                                               permitted only after the gate and
                                               revalidation, and only with the
                                               SAME deterministic child id
child present and empty                     -> E, MANIFEST_SHELL_UNRECOVERABLE
child present, non-empty, malformed         -> E, ARTIFACT_MALFORMED
child present with an acceptance mismatch   -> E, MANIFEST_ACCEPTANCE_MISMATCH
child present, valid and accepted           -> D
```

The Project Architecture listing **MUST NOT** be used as the artifact-specific
test of whether the Manifest create landed, and the child create **MUST NOT** be
retried blind.

**FROZEN.** Recovery is driven by **reading durable state**, never by a local
journal or remembered intent.

## 15. Runtime

**FROZEN.** The current `LocalCliModelRuntime` isolation contract
(`docs/runtime/Local-OAuth-Model-Runtime-Spec-v0.1.md`) is reused unchanged: the
restricted reasoning child, the explicit environment allowlist, the empty
temporary working directory, positive authentication evidence before every call,
and no provider SDK or API-key path.

**FROZEN.** Two new logical roles are defined:

```text
tsa_architect
tsa_reviewer
```

**FROZEN.** The Codex family **MUST NOT** be enabled for TSA reasoning: it
remains blocked at the execution boundary with `RUNTIME_ISOLATION_UNAVAILABLE`.
There is **no** fallback to provider APIs, and no relaxation of the reasoning
child's restrictions for TSA.

**OBLIGATION.** The two roles are added to the runtime configuration as roles,
with Claude as the runtime, following the existing selection precedence.

## 16. Acceptance matrix

This matrix covers every scenario of the independent design review's section 5
(28 scenarios), reconciled row by row in section 16.1, plus the recovery cases
frozen in section 14 and obligations this contract adds. Rows 36–49 were added
by the `CONTRACT_CHANGES_REQUIRED` review of candidate `5d7f609`; they are
corrections to this matrix, not further section 5 scenarios.

Three evidence classes are kept apart, because they prove different things.

- **D** — deterministic test with a fake model and a fake Fibery transport.
  Proves plumbing, validation and refusals. Proves nothing about model quality.
- **M** — model semantic live probe. Proves what a real model actually produces.
- **F** — Fibery integration or live probe. Proves the workspace actually
  behaves as assumed.

| # | Scenario | Source | Class |
|---|---|---|---|
| 1 | Valid cycle end to end: admit → architect → review → approve | brief §8 | D, then M + F |
| 2 | UX applicable but missing or unapproved → refused **before the Architect call** | review §5 | D |
| 3 | UX `NOT_APPLICABLE` written by a model → refused | §4 | D |
| 4 | Duplicate id in the selection, or a set spanning two Projects → admission refusal **before any model call** | review §5, §2.1 | D |
| 5 | Selected Requirement not `Applied` → refused | §2.1 | D |
| 6 | Requirement Root **or** child changed, added, deleted, renamed or reparented after freeze → tree mismatch; refused at the next revalidation; inputs are never auto-refreshed | review §5 | D |
| 7 | `APPLICABLE` UX content, Document identity or scope changed after freeze → stale under §4.4; approval unavailable | brief §5, §4.4 | D |
| 8 | Architecture Document changed after review → approval unavailable | brief §8 | D |
| 9 | Repeat `start`, `resume` or `approve` for one cycle id → the actual durable state is recovered, never assumed `Draft`: after Process, cases 2/3; after Review, the human boundary with no model call; after `APPROVE`, no write and no rework. Same cycle, no duplicate artifacts | review §5, §14.4 | D |
| 10 | Incomplete write / partial persistence → recovery cases 1–9 | brief §8, §14 | D |
| 11 | No human decision recorded → nothing advances, nothing is inferred | brief §8, §14 case 10 | D |
| 12 | Requirement set changed → new cycle required, REWORK refused | §3.2 | D |
| 13 | Architect omits an included Requirement from traceability → refused | §8.1 | D |
| 14 | Architect marks an included Requirement N/A → refused | §8.1 | D |
| 15 | Architect emits a structurally recognisable Task, Epic, estimate or code block → refused by the validator | §8.2 | D |
| 16 | Material unresolved WHAT → approval unavailable, not waivable | §7.4, §9.3 | D |
| 17 | Contradiction between admitted Requirements → all sources surfaced, no silent winner | §7.5 | D for surfacing; M for detection |
| 18 | Reviewer attempts to rewrite the Architecture Document → refused | §7.2 | D |
| 19 | Approval with a stale Review Result digest → refused | §9.1 | D |
| 20 | Approval with an accepted technical risk → recorded, approval proceeds | §9.2 | D |
| 21 | Two cooperating commands, same host and user → mutual exclusion | §13 | D |
| 22 | External Fibery UI edit during a cycle → detected at revalidation, refused | §13, §10 | F |
| 23 | Project-contained Document creation and nesting behave as assumed | §5.2, §17.3 | F |
| 24 | Architect produces one integrated architecture, not a catalogue | §7.1 | M |
| 25 | Reviewer independently disagrees with a real Architect output | §7.2 | M |
| 26 | Only the selected ids enter the manifest; no other Applied or Draft Requirement is added | review §5 | D |
| 27 | Admitted Requirement carries missing, legacy (Result 0.1/0.2, manifest v1) or incoherent evidence → refusal; no backfill and no Requirement processing is triggered | review §5 | D |
| 28 | `Applied` set by hand, with otherwise matching Process/Review → admitted only on explicit human input acceptance; no output or artifact claims historical Apply | review §5, §2.2 | D |
| 29 | UX `NOT_APPLICABLE` carrying a human decision, a reason and the input binding → accepted and **current with no UX Document present**; absence of a Document is not missing evidence | review §5, §4.2, §4.4 | D |
| 30 | Architect answers a product question instead of producing HOW → the invention is visible in evidence, no Requirement changes, approval unavailable | review §5 | D for the refusal; M for detection |
| 31 | Human REWORK → immutable decision, iteration N+1 on the same manifest, earlier iterations intact | review §5, §6 | D |
| 32 | Human APPROVE → the exact bound tuple is revalidated at decision time, then an immutable Decision is written | review §5, §9 | D |
| 33 | Model invocation fails → no false success; exactly one explicit retry, and only after the inputs are rechecked | review §5 | D |
| 34 | Approval persisted, then a bound input drifts → the approval stays as history, is not current, and a downstream consumer refuses it | review §5, §10 | D |
| 35 | Whole cycle leaves zero downstream side effects: no Epic, Story or Task, no code, no deployment, no Requirement, Project or Project Phase state mutation | review §5, §8.2 | D |
| 36 | Task, Epic or product invention embedded in otherwise allowed prose → detected | §8.2 | M |
| 37 | UX content digest or scope already mismatched **at admission** → refused before the Architect call | §4.1 | D |
| 38 | UX Document id unreadable, deleted or replaced at admission → refused | §4.1 | D |
| 39 | Deterministic Architecture discovery, decided by machine identity and never by a name alone: (a) derived id physically absent, no valid non-derived same-cycle Architecture → state A, create permitted at the derived id; (b) valid derived Architecture only → adopt; (c) a valid same-cycle Architecture under a non-derived id, **even when it is the only Architecture artifact that exists** → `CYCLE_AMBIGUOUS`; (d) valid derived plus valid non-derived same-cycle Architecture → `CYCLE_AMBIGUOUS`; (e) derived id occupied under a foreign Project or the wrong Project Database → `CYCLE_FOREIGN_PROJECT`; (f) correctly placed derived id with malformed non-empty content → `ARTIFACT_MALFORMED`; (g) correctly placed derived id with an empty body, no valid non-derived same-cycle Architecture → the `EMPTY_ARCHITECTURE_SHELL` recovery condition, never state A. A name-only match, or a malformed Document with a resembling name, changes none of (a)–(g) | §5.1.1 | D |
| 40 | Bootstrap states A and B without an Input Manifest Document → the missing Manifest is not a gate failure; only the minimum bootstrap write advances A→B→accepted Manifest; no Architect call, no Process replay, no Reviewer call, no `APPROVE`. The Architecture Document's existence never implies acceptance, and `C` is never rediscovered. An empty Input Manifest shell → state E, `MANIFEST_SHELL_UNRECOVERABLE`; a non-empty Manifest missing acceptance → state E, `ARTIFACT_MALFORMED`; neither is B, `C` or D, and neither permits a write or a model call. `EMPTY_ARCHITECTURE_SHELL` — the deterministic Architecture Document exists, correctly placed, with an empty body — is never state A and never `CYCLE_NOT_FOUND`: `start` completes that same id in place and continues; `resume` completes that same id to B and returns `ARCHITECTURE_CYCLE_RESUMED` with no model call; `rework` and `approve` do not repair it and return `REVIEW_NOT_CURRENT`; `inspect` returns `INSPECT_INCOMPLETE`; no second Architecture Document is created; the completing write is accepted only when its read-back equals the emitted carrier, or that carrier less its one final newline; when that immediate read-back succeeds but is empty or whitespace-only, `start` and `resume` return `FIBERY_WRITE_FAILED`, the Document remains `EMPTY_ARCHITECTURE_SHELL`, and there is no B, no model call and no second write; when it is non-empty but non-conforming → `ARTIFACT_MALFORMED`. A correctly placed derived-id bootstrap Architecture whose digest is valid but whose workspace identity, Project entity id, Project Code, envelope or body cycle id, or heading Project Code or cycle id differs from the trusted expected value → `ARTIFACT_MALFORMED`, never B. Required Project Code unavailable before a bootstrap mutation: in state A → `FIBERY_READ_FAILED`, no Document create, no write, no model call; under `EMPTY_ARCHITECTURE_SHELL` with `start` or `resume` → `FIBERY_READ_FAILED`, the same empty Document remains, no write, no model call; for a non-empty derived Architecture → `ARTIFACT_MALFORMED`, no repair, no model call. Creation alone never establishes B, and one carrier write contract governs both origins of the shell: state A → create succeeds → read-back exactly the emitted carrier → B; → read-back the carrier less its one final newline → B; → empty or whitespace-only immediate read-back → `FIBERY_WRITE_FAILED`, `EMPTY_ARCHITECTURE_SHELL` remains; → non-empty non-conforming read-back → `ARTIFACT_MALFORMED`; create lands and the process stops before content → a restart discovers `EMPTY_ARCHITECTURE_SHELL` and completes the same id in place, with no second create; a rediscovered `EMPTY_ARCHITECTURE_SHELL` follows the identical outcomes | §8, §14.1.2, §14.2, §14.4 | D |
| 41 | Persisted Process output present but Requirement or UX inputs stale → replay refused | §14.1 | D |
| 42 | Duplicate Process Results, duplicate Review Results, or conflicting `REWORK`/`APPROVE` for one iteration → gate failure before any recovery action | §14.1 | D |
| 43 | Process output payload digest invalid → gate failure, no replay, no overwrite | §14.1 | D |
| 44 | Review Result bound to a different Process payload → does not restore the human boundary | §14.1 | D |
| 45 | Reviewer reports a defect on a valid cycle → Review evidence persisted, Architecture Document unchanged, cycle stops at the human boundary | review §5, §7.2 | D |
| 46 | Human manifest acceptance missing, or bound to a different manifest digest → treated as absent; Architect call refused | §3.3 | D |
| 47 | `resume` on an approved cycle → no write, no model call; a stale historical approval is not made current | §14.1 | D |
| 48 | `REWORK` after `APPROVE` → refused; the cycle is closed to writes | §6, §9 | D |
| 49 | Accepted finding or risk disposition references an unknown or duplicated id → refused | §9.2 | D |
| 50 | Requirement input digest drifts while UX is `NOT_APPLICABLE` → the N/A decision goes stale under §4.4; approval unavailable, with no UX Document ever consulted | §4.2, §4.4 | D |

**FROZEN.** A `D` test **MUST NOT** be reported as evidence for an `M` or `F`
row. An implementation is not complete on `D` alone.

**FROZEN.** Rows 15 and 36 split one prohibition on purpose. A deterministic
validator proves only **structural** rejection: an output shaped as a Task, an
Epic, an estimate or a code block. A Task, an Epic or an invented product
obligation expressed inside otherwise allowed prose is a **semantic** defect;
only `M` evidence can show it is detected. An implementation **MUST NOT** claim
that the row 15 validator proves the row 36 recognition.

**OBLIGATION.** Row 49 becomes testable once the finding and risk disposition
identifier schema exists. That schema is implementation-spec work under `U-4`;
the row is stated now so it is not forgotten, and it **MUST NOT** be reported as
passing before that schema is defined.

### 16.1 Review section 5 → contract section 16

All 28 scenarios of the independent design review's section 5 are covered. The
mapping is not one-to-one in both directions, and the two asymmetries are
recorded here rather than resolved by duplicating rows.

| Review §5 scenario | Row(s) |
|---|---|
| Valid TSA cycle | 1 |
| Explicit selected Applied scope | 26 |
| Duplicate / foreign / non-Applied id | 4, 5 |
| Applied with missing / legacy / incoherent evidence | 27 |
| Manual `Applied` with matching Process/Review | 28 |
| Requirement changed after start | 6 |
| Normative child changed, added, deleted, renamed, reparented | 6 |
| UX required but missing / unapproved | 2 |
| UX changed, or scope/version mismatch | 7 |
| UX explicitly N/A | 29 |
| Model chose the UX skip itself | 3 |
| Architect invented a product decision instead of HOW | 30 |
| Architect found a product question | 16 |
| Applied Requirements contradict each other | 17 |
| Reviewer found a defect | 18, 25 |
| Architecture changed after Review | 8, 19 |
| Human rework | 31 |
| Human approve | 32 |
| Repeat start / resume / approve | 9 |
| Model failure | 33 |
| Process persisted, Root write unfinished | 10 (§14 cases 2, 3) |
| Review persisted before restart | 10 (§14 case 5) |
| Empty shell / malformed partial result | 10 (§14 cases 7, 8) |
| Unknown mutation outcome | 10 (§14 case 9) |
| Restart without human approval | 11 (§14 case 10) |
| Approval persisted, then input drift | 34 |
| Concurrent cooperating local writer | 21, 22 |
| No Delivery Planning side effects | 35 |

**One review scenario needing more than one row.** Three cases split because the
assertions are proved by different means and would otherwise hide a gap behind a
single pass:

- *Duplicate / foreign / non-Applied id* → rows 4 and 5: row 4 refuses on the
  shape of the **selection** (a duplicate id, or ids from two Projects), row 5
  refuses on the **state** of an individually valid id. A single row would let
  one refusal path stand in for the other.
- *Reviewer found a defect* → rows 18 and 25: row 18 is the deterministic
  authority boundary (a Reviewer write to the Architecture Document is refused);
  row 25 is a live-model probe (a real Reviewer actually disagrees). `D`
  evidence can never satisfy the second.
- *Concurrent cooperating local writer* → rows 21 and 22: row 21 is the guard's
  positive guarantee inside its scope (`D`); row 22 is the explicitly
  unguaranteed case outside it — an external Fibery UI edit caught only by
  revalidation (`F`).

**Several review scenarios sharing one row.** *Requirement changed after start*
and *normative child changed / added / deleted / renamed / reparented* both map
to row 6: the tree fingerprint covers Root and children alike, so one
revalidation refusal is the same assertion for both. Four recovery scenarios map
to row 10, which is itself defined by the ten cases of section 14 — row 10 is a
pointer to that table, not a summary of it.

**Rows without a direct §5 counterpart.** Rows 12, 13, 14, 15, 19, 20, 23 and 24
come from other parts of the same review. Throughout this paragraph the section
numbers are the **review's**, not this contract's: review §3 group 1 (a changed
Requirement set starts a new cycle), review §4.3 (deterministic coverage
validation, the forbidden-output list), review §4.4 (approval binding and
explicit risk acceptance), review §4.2 (one integrated architecture) and review
§7 STILL UNVERIFIED (live Project-document containment). No row is orphaned.

**Live-probe caveat.** The review closes §5 by noting that fake tests prove
contract handling and authority boundaries, while a live model's ability to
detect product invention, coverage gaps and conflicts needs separate controlled
probes. That caveat is carried by rows 24, 25, 30 and 36, and by the `M` half of
row 17. Row 15 no longer carries an `M` half: the second review split it, and
the semantic case is row 36.

**Rows added by the second review.** Rows 36–49 close gaps the
`CONTRACT_CHANGES_REQUIRED` review found in this matrix: admission-time UX
mismatch (37, 38), deterministic Architecture discovery (39), partial bootstrap
(40), freshness before replay (41), duplicate and conflicting artifacts (42, 44),
invalid output digest (43), the ordinary Reviewer-defect path (45), manifest
acceptance binding (46), approved-cycle `resume` (47), `REWORK` after `APPROVE`
(48), and disposition-reference validity (49). They map to sections 4.1, 5.1.1,
14.1 and 14.4 rather than to review §5.

## 17. Verified repository facts

Checked at `a38d2c3`. These are facts, not decisions.

**17.1 Artifact versions exist as assumed.** `PROCESS_RESULT_VERSION = "0.3"`
(`src/sdlc/process_result.py:41`), `REVIEW_RESULT_VERSION = "0.3"`
(`src/sdlc/review_result.py:47`), `NORMATIVE_TREE_VERSION = 2`
(`src/sdlc/normative_tree.py:33`), `document_fingerprint` = SHA-256 over
canonical Markdown bytes (`src/sdlc/normative_tree.py:89-97`). A Review Result
0.3 binds `reviewed_document_fingerprint` to the tree's Root entry
(`src/sdlc/review_result.py:181`).

**17.2 Apply persists no artifact.** `requirement_apply.py` writes relations and
`State = Applied` (`src/sdlc/requirement_apply.py:785`), reads the entity back,
and creates **no** Apply Result document — a search for `create_child_document`
in that module returns nothing. This is the evidential basis for section 2.2: no
durable record binds the approved content to the Apply transition.

**17.3 Project-contained Documents are not implemented.** The only
entity-contained document creator hard-codes the Requirement type id
(`src/sdlc/fibery_http.py:508-510`), and `project init` deliberately creates no
Project Document — "`Project.Documents` is left for genuine Project documents"
(`docs/specs/Project-Init-Spec-v0.3.md:206`). The Fibery schema does define the
Project `Documents` field (`docs/fibery/Fibery-Schema-v0.1.md:22`). Section 5
therefore rests on a capability that exists in the schema but not in the adapter,
and whose nesting behaviour is unverified — matrix row 23.

**17.4 The guard's scope is exactly as claimed in section 13.** "cooperating
runners on the same host, as the same OS user, sharing the standard lock
directory, against the same Fibery workspace. Different machines and different
OS users are not coordinated here" (`src/sdlc/worker_runner_guard.py:9-12`).

**17.5 Three model roles exist today** — `raw_requirement_processor`,
`standard_requirement_processor`, `standard_requirement_reviewer`
(`src/sdlc/model_runtime_config.py:37-39`, `config/sdlc.toml:49-61`). The two TSA
roles do not exist and are an obligation, not a fact.

**17.6 Codex remains blocked** at the execution boundary with
`RUNTIME_ISOLATION_UNAVAILABLE` (`src/sdlc/model_runtime.py`,
`docs/runtime/Local-OAuth-Model-Runtime-Spec-v0.1.md` §3).

## 18. Unresolved items

Two classes are kept apart, because they carry different risk. An
implementation agent **MUST NOT** decide either alone, but only the first is an
open **authority** question.

- **DEFERRED** — an authority, policy or semantics question this contract does
  not answer. It **MUST** be answered by a human decision or a new contract
  version before the affected behaviour is built.
- **IMPLEMENTATION-SPEC** — the authority is frozen here; what remains is the
  mechanism, and it belongs in the implementation specification that a bounded
  work item would carry. It is not an open question about *what is allowed*.

### 18.1 Closed

`U-1` (reconcile section 16 with the review's section 5) was closed on
2026-09-28: the review was read in full and all 28 of its section 5 scenarios
are mapped in section 16.1.

`U-5` (admissible UX evidence) was closed on 2026-09-29 by the
`CONTRACT_CHANGES_REQUIRED` review of candidate `5d7f609`. Section 4.1 now
freezes the interface: one readable Fibery Document resolved by id, complete
content read, a manifest binding of id + content digest + exact scope + explicit
human approval of that digest for that scope, no version label as a substitute,
admission failure before the Architect call, and drift detection on
revalidation. The remaining adapter mechanics are tracked as
IMPLEMENTATION-SPEC under `U-3`, not as an open authority question.

Identifiers keep their original numbers so earlier references stay valid.

### 18.2 Open

| # | Item | Class | Why |
|---|---|---|---|
| `U-2` | Apply-time provenance | DEFERRED | No artifact binds approved content to the Apply transition (17.2). Section 2.2 works around it with explicit human acceptance; no historical Apply proof is added by this contract. |
| `U-3` | Project-contained Document adapter, nesting API semantics, read-back verification, live Fibery probe | IMPLEMENTATION-SPEC | Containment authority is frozen in section 5; the adapter does not exist and the behaviour is unprobed (17.3). |
| `U-4` | Canonical TSA JSON serialization and digest algorithm | IMPLEMENTATION-SPEC | Section 11.2. Row 49 of section 16 depends on the disposition identifier schema this settles. |
| `U-6` | Authenticated approver identity | DEFERRED | Section 9.4. The runtime supplies none; the contract forbids claiming one. |
| `U-7` | Exact CLI flags and scope-selection syntax | IMPLEMENTATION-SPEC | Section 12. The command semantics and the start idempotency key are frozen in 12.1; only the spelling is open. |
| `U-8` | Whether `Project Phase` is written at all by a future slice | DEFERRED | This contract only forbids using it as TSA authority (section 6); it does not decide its future use. |

The first review closed none of these; its own STILL UNVERIFIED list
independently names `U-2`, `U-3` and live model and runtime behaviour. The
second review closed `U-5` and reclassified `U-3`, `U-4` and `U-7` as mechanism
rather than authority. No item was closed silently.

## 19. Sources

Repository, at `a38d2c3`:

```text
docs/architecture/SDLC-MVP-v0.5-Current-Architecture.md
docs/specs/Requirement-Normative-Tree-Binding-v0.1.md
docs/specs/Standard-Requirement-Apply-Spec-v0.1.md
docs/specs/Standard-Requirement-Review-Spec-v0.1.md
docs/specs/Project-Init-Spec-v0.3.md
docs/fibery/Fibery-Schema-v0.1.md
docs/fibery/Fibery-API-Constraints-v0.1.md
docs/runtime/Local-OAuth-Model-Runtime-Spec-v0.1.md
src/sdlc/process_result.py, review_result.py, normative_tree.py
src/sdlc/requirement_apply.py, fibery_http.py, worker_runner_guard.py
src/sdlc/model_runtime.py, model_runtime_config.py, config/sdlc.toml
```

External: `TSA-C01-Design-Brief-v0.1-DRAFT.md` (baseline `91c2697`) and
`TSA-C01-Independent-Design-Review-v0.1.md` (reviewed baseline `a38d2c3`,
verdict `DESIGN_DIRECTION_SUPPORTED`), both read outside the repository.

No code, test, configuration or Fibery data was changed to produce this
document. No model was invoked and no Fibery call was made.

**Implementation authorized: NO.**
