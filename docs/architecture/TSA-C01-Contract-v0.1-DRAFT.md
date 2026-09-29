# TSA-C01 — Technical Solution Architecture Contract v0.1 DRAFT

**Status:** DRAFT. Not APPROVED, not VERIFIED.
**Implementation authorized:** NO.
**Rewrite/work item:** `TSA-C01`.
**Repository baseline:** `ros-datonum/sdlc`, `main` at `a38d2c3b446961d1a8cf53770d998819d27e5480`.

This document converts the proposed design into one bounded, internally
consistent contract for the **first Technical Solution Architecture vertical
slice**. It is not an implementation specification, and it authorizes no engine.
A separate bounded implementation work item may be created only after this
contract is independently reviewed and approved.

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
  not unique — Fibery API constraint 2a).

### 5.1.1 Rediscovery after an unknown create outcome

**FROZEN.** A name or cycle id **MAY** be used to **discover candidates** after a
create whose outcome is unknown. A candidate **MUST NOT** be accepted as machine
identity until it is validated on all three of:

1. containment by the expected **Project entity**;
2. the expected **cycle metadata** in its payload;
3. **uniqueness** among the candidates found.

Outcomes, and only these:

| Candidates for the cycle | Action |
|---|---|
| zero valid | Create is permitted. |
| exactly one valid | Adopt its Fibery id as the cycle's Architecture identity. |
| more than one plausible or valid | **Refuse.** Do not pick one, do not create another. |
| any candidate owned by a different Project | **Refuse.** |

### 5.2 Writability

**FROZEN.**

- The Architecture Document is writable **only** through an authorized
  application of an Architect output for that cycle. After APPROVE it is
  **frozen**: a future consumer reads it, and the engine **MUST NOT** write it.
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

**FROZEN.** The Architecture Document has exactly these headings, in this order:

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
  resolves to one of the bootstrap states in section 14.4;
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
| **Bootstrap gate** | No valid accepted Input Manifest yet — states A–C of section 14.4 | Section 14.1.2 |
| **Normal gate** | A valid accepted Input Manifest exists — state D onward | Section 14.1.1 |

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

**FROZEN.** Applies to states A–C of section 14.4, **before** a valid accepted
Input Manifest exists.

**FROZEN.** The absence of an Input Manifest, or of human acceptance, is **not**
a gate failure at this stage: those artifacts are precisely what bootstrap is
creating. Criteria 7, 8, 9, 10 and 11 of the normal gate are therefore not yet
applicable.

**FROZEN.** Everything that already exists **MUST** still be validated. The
bootstrap gate **MUST** check at least:

1. a stable cycle id;
2. exact Project ownership;
3. Architecture candidate uniqueness;
4. candidate containment by that Project entity;
5. cycle metadata consistency;
6. no conflicting or malformed non-empty bootstrap artifact;
7. no evidence that this cycle was already completed under another state.

**FROZEN.** **Once the bootstrap gate has succeeded**, only the **minimum
bootstrap write** needed to advance A → B → C → accepted Manifest is permitted
at this stage. A failed bootstrap gate permits **zero** writes.

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
- **after** the write, read back and validate the intended result;
- if drift is observed on read-back, the engine **MUST NOT** report a successful
  or current transition.

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
| 9 | Create or write returned an unknown outcome (timeout, dropped connection) | Re-read before any further write. Classify into cases 1–8 from what is actually there. **MUST NOT** retry the mutation blind. |
| 10 | Restart at a human boundary (`Review` complete, no decision) | Present the exact iteration's evidence again. Do not re-invoke any model. Do not assume the previous presentation implies a decision. |

### 14.4 Initial bootstrap states

**FROZEN.** A cycle is classified by its cycle id into one of these durable
states. States A–C precede a valid accepted Input Manifest and are reached
through the bootstrap gate (section 14.1.2); state D leaves bootstrap entirely.

| | Durable state | Required behaviour |
|---|---|---|
| **A** | No Architecture Document for this cycle id | Create the Architecture Document, contained directly by the Project entity. |
| **B** | Exactly one valid Architecture shell for this cycle, no valid Input Manifest | Resume bootstrap for that **same** cycle, only after validating Project ownership and cycle identity. |
| **C** | Architecture shell exists, Input Manifest or human acceptance never completed | The shell's existence **MUST NOT** imply acceptance. Explicit human manifest acceptance is still required before any Architect call. |
| **D** | Valid, accepted Input Manifest exists | **Bootstrap is complete.** Run the **normal recovery classification** of section 14.3 under the normal gate (14.1.1). State D **MUST NOT** be read as "case 1". |
| **E** | Multiple candidates, wrong Project ownership, conflicting metadata, or malformed non-empty bootstrap state | **Refuse.** Do not create a second cycle under the same cycle id. |

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

**FROZEN.** After an unknown create or write outcome during bootstrap, the
engine **MUST** first rediscover and re-read by cycle id (section 5.1.1), then
classify one of A–E. **No blind duplicate create.**

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
| 39 | Zero valid Architecture candidates for a cycle id → create permitted; more than one plausible candidate, or one owned by another Project → refusal | §5.1.1 | D |
| 40 | Bootstrap states A–C without an accepted Input Manifest → the missing Manifest is not a gate failure; only the minimum bootstrap write advances A→B→C; no Architect call, no Process replay, no Reviewer call, no `APPROVE`. Shell existence never implies acceptance | §14.1.2, §14.4 | D |
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
mismatch (37, 38), Architecture candidate resolution (39), partial bootstrap
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
