# Requirement Lifecycle v0.1 — Architecture Checkpoint

**Status:** Checkpoint. Records what the frozen Requirement lifecycle guarantees
and selects the next vertical slice. It does not replace
`SDLC-MVP-v0.4-Frozen-Architecture.md` and does not redesign any frozen
capability.

## 1. Lifecycle overview

The implemented lifecycle, in the workflow terms the frozen specifications use:

```text
requirements-export (outside this repository)
-> project requirement add           RAW Requirement, State Draft, Root under Requirements/Raw
-> human: RAW Draft -> Process
-> RAW Requirement Processor         Processing Result; 0..N Standard candidates in Draft,
                                     Root Documents under Requirements/Draft,
                                     Produces / Derived From; RAW -> Review
-> human: Standard Draft -> Process
-> STANDARD Process                  normalized Root Document; Process Result NNNN; -> Review
-> STANDARD Review                   independent Review Result NNNN; -> Ready, whatever the verdict
-> human Ready Decision              APPROVE (Ready -> Apply) with verdict acknowledgement,
                                     or REWORK (Ready -> Process)
-> STANDARD Apply                    confirmed relations written; Root Draft -> Approved; -> Applied
```

Every model-backed stage writes a numbered, immutable artifact before it moves
the workflow, and every stage confirms its transition by reading the entity
back. The three human transitions are `RAW Draft -> Process`,
`Standard Draft -> Process`, and the Ready Decision.

## 2. Frozen capabilities

| Capability | Specification | Merge | Implementation |
|---|---|---|---|
| project init | `Project-Init-Spec-v0.3.md` | `74c0899` | `c71fe95`, `91cb26b`, `b056daf` |
| project requirement add | `Project-Requirement-Add-Spec-v0.3.md` | `36af44a` | `5082a12`, `4fd2650` |
| RAW Requirement Processor | `RAW-Requirement-Processor-Decision-v0.1.md`, `RAW-Processor-Processing-Result-v0.1.md`, `Standard-Requirement-Document-Schema-v0.1.md` | `84d7a3b` | `ed26887`, `d6fe0c7`, `26d3bd6`, `67433ac` |
| STANDARD Process | `Standard-Requirement-Process-Spec-v0.1.md` | `c9803f6` | `1ce5109`, `b93e6bf` |
| STANDARD Review | `Standard-Requirement-Review-Spec-v0.1.md` | `8d3d7aa` | `c495f5d` |
| Ready Decision | `Standard-Requirement-Ready-Spec-v0.1.md` | `cf5327b` | `9257504`, `0214ddc` |
| STANDARD Apply | `Standard-Requirement-Apply-Spec-v0.1.md` | `40e5c97` | `cd9f4d5`, tests `640983f` |

Fibery behaviour these rest on is recorded as constraints 1–26 in
`docs/fibery/Fibery-API-Constraints-v0.1.md`; the schema is
`docs/fibery/Fibery-Schema-v0.1.md`.

## 3. The `Applied Requirement` contract

### Guaranteed by normal lifecycle completion

When a Requirement reached `Applied` through the frozen capabilities:

- it is a Standard Requirement with a Category, created by the RAW Processor
  and linked to its RAW source through `Derived From` / `Produces`;
- its Root Document has the frozen seven-section structure and was last
  rewritten by STANDARD Process; Review, Ready and Apply wrote nothing to it;
- at least one `Process Result NNNN` and one `Review Result NNNN` exist as
  nested children of the Root Document, immutable, the newest of each being
  the one that was applied;
- an independent Review certified the exact Root content and the exact
  Process iteration it read, and derived its verdict from findings by code;
- a human recorded the approval through `Ready -> Apply`, acknowledging any
  non-`PASS` verdict by name;
- immediately before the first normative Apply write, and again immediately
  before `Applied`, the current Root fingerprint, latest Process iteration and
  latest Process output fingerprint equalled what the applied Review Result
  reviewed;
- every relation the applied Review Result confirmed exists as a forward
  `Depends On` or `Affects` edge, written additively; no pre-existing edge was
  removed; the Fibery-maintained inverses are present on the targets;
- the same Root Document entity, with the same content secret and body, is
  under `Requirements/Approved`, and its child artifacts moved with it;
- `Revision` is the value it had at creation;
- no model was invoked by Ready or Apply, and `Applied` was written only after
  every other step had been read back.

### Not guaranteed by observing State = Applied alone

Fibery allows any workflow State to be set by hand. Observing `Applied`
therefore proves only that the State is `Applied`. It does not prove:

- that the transition was made by Apply rather than by a person;
- that the Root Document is under `Approved`, or that the confirmed edges
  exist, for a manually placed `Applied`;
- that the Root Document has not been edited since the application;
- who approved, or when, beyond what Fibery's own history shows.

The same boundary was accepted for `Apply` at Ready and is not closed here.
**State is a workflow signal, not provenance proof.** No ledger, signature or
approval artifact is introduced to change that; a later stage that needs
provenance must ask for it explicitly rather than infer it.

## 4. Normative and supporting artifacts

```text
Applied Standard Root Document        normative Requirement content
Requirement fields                    normative structured metadata:
                                      Requirement ID, Title, Type, Category, State, Revision, Project
Depends On / Blocks, Affects / Impacted By
                                      normative Requirement graph
Derived From / Produces               provenance, normative for traceability only
Review Result NNNN                    review and approval evidence; the source of the
                                      confirmed proposals Apply wrote
Process Result NNNN                   processing history and analysis evidence
RAW Requirement + Root Document       source and provenance
RAW Processing Result                 decomposition history
```

Evidence artifacts inform reasoning. They never override an Applied Root
Document: a Review finding, a Process analysis or a RAW paragraph that
disagrees with the Applied text is a reason to reopen the Requirement, not an
alternative reading of it.

## 5. Downstream consumption contract

UX / Product Design, Technical Solution Architecture and Delivery Planning may
consume, as approved requirements:

- Root Documents of Standard Requirements in `Applied`, read from Fibery;
- their metadata fields and the `Depends On` / `Affects` graph, including the
  inverse sides;
- `Derived From` when a downstream artifact must trace back to a RAW source.

They may read Process Results, Review Results and RAW sources as supporting
evidence, for example to see an open question or a rejected relation proposal,
and must present them as such.

They must not consume Requirements in `Draft`, `Process`, `Review`, `Ready` or
`Apply` as approved, and must not write to any Requirement artifact. The
repository stores no requirement mirror; Fibery remains the only source.

## 6. Accepted limitations

Standing items, recorded so they are not mistaken for guarantees:

- Fibery rate-limits at three requests per second per token; the client paces
  every request at least 0.5 s apart and retries only known read-only requests
  after HTTP 429, at most three attempts. A rate-limited mutation is reported
  once and resumed from durable state on rerun; nothing coordinates
  simultaneous SDLC processes, so one command runs at a time per workspace.
- Document fingerprints of current evidence (Process/Review 0.3, manifest v2)
  are SHA-256 over the exact canonical bytes (audit A8); 0.2/manifest v1
  evidence hashed through a second normalization that missed fenced trailing
  whitespace and Unicode form, and is readable history only. Fresh Process
  and Review produce current evidence; nothing is rewritten.
- A tree equal to the latest Process Result's input but not its output is
  ambiguous between an unfinished rewrite and a deliberate return to that
  input (audit A11); Standard Process refuses it and the operator chooses
  `--resume-result` or `--new-iteration-after` explicitly.
- A failed final transition can be indistinguishable from a deliberate manual
  return to the previous State; the frozen capabilities preserve the observed
  State rather than guess, and recovery is manual.
- A manual workflow mutation cannot be distinguished from a validated
  transition (section 3).
- Human identity is not persisted for the Ready Decision.
- Process and Review may run on the same underlying model; independence is
  structural, not model-diverse.
- No editing UX or path exists; a human edits the Root Document in Fibery and
  the canonical fingerprints decide whether anything changed.
- The normative tree (Root plus normative descendants) is what Process reads,
  Review certifies and Ready and Apply bind, per
  `docs/specs/Requirement-Normative-Tree-Binding-v0.1.md` (audit finding A5).
  Legacy Root-only Process and Review Results stay as history: never replayed,
  never certified, never applied; Process runs a fresh current-format iteration
  over them.
- Relation removal and replacement semantics are undesigned; Apply is additive
  only.
- Requirement material revision, update and supersession are undesigned;
  `Revision` is never changed by the lifecycle.
- Apply recovery after a partial application is resume-only: durable steps
  stay, nothing is rolled back, and a stale Requirement left in `Apply` is
  returned to `Process` by an operator.
- The validate-then-write race in Apply may leave an approved edge attached to
  a Requirement whose content drifted a moment later; the Requirement stays in
  `Apply` and is never marked `Applied`.
- N3, implementation reporting only: Apply journals a relation edge before its
  read-back, so a silently ignored add is listed as durable in `PARTIAL_APPLY`.
  Resume and idempotency are unaffected. A bounded cleanup item.

## 7. Fibery integration engineering rule

Every capability so far found at least one live behaviour the fake did not
model. The rule, now project-level:

```text
new Fibery read or write semantics
-> deterministic fake plus tests
-> narrow live probe on temporary state
-> compare fake against live
-> a regression for every discrepancy, in the fake and in the canonicalizer
-> only then freeze
```

`fake green` is never integration proof. This rule applies to Fibery
integration only.

## 8. Completeness assessment

**Can downstream stages consume Applied Requirements without more Requirement
workflow first? Yes.**

The contract in section 3 is sufficient for a downstream stage to read approved
content, metadata and graph and to trace provenance. None of the undesigned
capabilities is a prerequisite for the first downstream slice: revision and
supersession matter only once a downstream artifact exists that a changed
Requirement would invalidate; relation deletion matters only when a confirmed
edge proves wrong; an editing UX is convenience. Each should be designed when
its first real consumer appears, from evidence, in the same design-then-freeze
cadence.

## 9. UX / Product Design routing principle

The frozen architecture makes UX optional and places it before Technical
Solution Architecture "when meaningful human interaction exists". The routing
rule is a human declaration, not a classifier:

```text
a Project declares whether it has meaningful human interaction
  (customer UI, operator UI, admin dashboard)
yes -> UX / Product Design runs before Technical Solution Architecture
no  -> Technical Solution Architecture consumes Applied Requirements directly
```

The declaration is made once per Project by a person, may be revised, and is
the only input to the routing. How it is recorded in Fibery is decided when the
UX capability is designed; the Technical Solution Architecture design must not
depend on it beyond "an approved UX artifact may or may not exist".

## 10. Technical Solution Architecture boundary

Consumes Applied Requirements and, when the Project declared human
interaction, the approved UX artifact. Produces one approved architecture for
the Project, developed through the frozen internal loop of draft, review
findings, revision and approval, with one owner integrating findings.

Expected content, at the level of the frozen architecture and not designed
here: technology choices; system and component boundaries; data and storage
architecture; external integrations; API and interface contracts; auth and
security boundaries; observability; deployment and hosting approach;
high-level data flow; implementation targets and adapters; major technical
constraints and risks; traceability from each decision to the Requirements it
serves.

It writes no Requirement artifact and does not reinterpret Requirement text.
Its output is the second normative input to Delivery Planning.

## 11. Delivery Planning boundary

```text
Applied Requirements
+ approved UX artifact, when the Project declared human interaction
+ approved Technical Solution Architecture
-> Delivery Planning
-> Milestones, Epics, User Stories, Tasks
```

Delivery Planning derives work from those three inputs. It does not make
architecture decisions, does not choose technology or implementation targets
beyond assigning the ones the architecture defined, and does not consume
Requirements below `Applied`. Nothing of it is designed or implemented now.

## 12. Selected next vertical slice

```text
NEXT_VERTICAL_SLICE = Technical Solution Architecture
```

Rationale:

- it is the mandatory stage between Applied Requirements and Delivery
  Planning for every Project; UX is conditional, and a platform that can only
  route UI projects would still be unable to reach Delivery Planning for any
  project;
- its inputs are complete today: the Applied Requirement contract of section 3
  and the graph of section 5, with UX as an optional additional input;
- it establishes the second normative artifact class of the SDLC, reusing the
  proven pattern of a model-backed writer, an independent reviewer, immutable
  numbered artifacts, a human decision boundary and deterministic application;
- the first downstream slice will surface, from evidence, whether Requirement
  revision or relation removal is actually needed, before either is designed.

UX / Product Design follows as its own slice once the architecture stage
exists to consume it; the routing declaration of section 9 is then given a
concrete home.

## 13. Non-goals for the next step

```text
Delivery Planning                 Epic, Story, Task or Milestone generation
work-item dependency graphs       GitHub or coding, testing or deployment agents
a generic Phase or workflow engine
Requirement revision, supersession, editing UX or relation deletion
UX / Product Design design (beyond the routing principle above)
any change to a frozen Requirement capability
```

The existing `Project Phase` Database is reused minimally if the architecture
stage needs phase state; no orchestration layer is built.
