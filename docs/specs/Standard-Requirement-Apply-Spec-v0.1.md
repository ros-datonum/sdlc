# Standard Requirement Apply Specification v0.1

**Status:** APPROVED. Frozen contract, implemented. Amended 2026-09-09: the
Root Document move (former section 10) is retired; Apply writes no Document.
Amended by `RW-O01` (SDLC Rewrite v0.2): `State = Apply` is the approval signal
whichever control surface set it (section 4).

Design for `Requirement.Type = Standard` + `Requirement.State = Apply`.

## 1. Lifecycle position

```text
Draft -> Process -> Review -> Ready -> Apply -> Applied
```

`Process`, `Review` and `Ready` are frozen. This capability performs
`Apply -> Applied`, and is the last stage of the Standard Requirement workflow.

## 2. What Apply is

```text
Process   normalize + analyze + propose        model, writing
Review    independently verify + confirm       model, verifying
Ready     human decision boundary              HUMAN
Apply     deterministic application            deterministic, writing
```

```text
STANDARD + Apply
= deterministically apply the exact Standard Requirement state
  already reviewed and human-approved
```

`Apply` is **not another reasoning stage and not another approval stage**. The
human approval has already been recorded durably by `Ready -> Apply`. Apply
turns what was reviewed and approved into canonical Fibery state:

```text
revalidate the approved binding
-> apply the confirmed relations
-> verify
-> Apply -> Applied
-> verify
```

No model invocation, no judgement of Requirement quality, no verdict
acknowledgement, no new human decision. "Apply" means *apply the approved
Standard Requirement into the authoritative requirements graph and document
structure*. It does not mean implement the software requirement.

Command, following the existing one-verb-per-command convention:

```text
sdlc project requirement apply --requirement <entity id>
```

No `--runtime`, `--model`, `--acknowledge-verdict` or `--force`. No flag is
needed: everything Apply consumes is durable in Fibery.

## 3. Entry condition

```text
Requirement.Type  = Standard
Requirement.State = Apply
```

Anything else is refused with zero Fibery mutations. `State = Applied` is
accepted as **already-done** for idempotency (section 16). Raw Requirements and
every other State are refused.

## 4. Approval is complete — what State = Apply proves

The frozen Ready specification (section 5) fixes the distinction this
capability depends on:

```text
State = Apply
```

is sufficient durable evidence that a human approval transition was recorded.
It is **not** evidence that the current content is still what was reviewed,
because the Root Document can be edited in Fibery at any moment.

`State = Apply` is the approval signal whichever control surface set it: the
human directly in Fibery (the normal path under
`Requirement-Lifecycle-Ownership-v0.2`), an authorized assistant acting on the
human's explicit instruction, or the admin/compatibility `approve` command.
Apply does not know, and does not need to know, which one was used; it
revalidates identically in every case and does not assume that the `approve`
command's checks ran.

Apply therefore never asks whether the Requirement should be approved. It does
not re-run or re-read the `PASS` / `NEEDS_WORK` / `BLOCKING` acknowledgement,
does not reinterpret findings, and does not refuse a Requirement because its
verdict was not `PASS`. A human may approve at any of the three verdicts, and a
verdict never overrides that decision; the `approve` command's verdict
acknowledgement is a safety check of that command, which Apply neither requires
nor reads. Apply executes the decision.

What Apply does do is **revalidate the exact reviewed binding before any
normative mutation** (section 6). That is the interface invariant Ready
recorded for it, and it is the only correctness check Apply adds.

No `Approval Result`, approval ledger, approval field or approval relation is
introduced. The workflow State plus the latest valid Review Result carry
everything Apply needs.

### No further quality gate

The Root Document's `Open Questions` section is **not** required to be empty
before `Applied`, and no other content condition is imposed. The frozen
Document Schema left that possibility open; the Review verdict plus the human
`Ready -> Apply` decision already form the quality and authority boundary, and Apply must
not silently add another one behind them.

## 5. Inputs, and the only relation source of truth

```text
the Requirement entity (Requirement ID, Type, State, Revision, Project)
its Root Document and current content
the latest valid Review Result
the latest valid Process Result
the Requirement's existing Depends On / Affects edges
the target Requirements named by confirmed relation proposals
```

The relations Apply may write are exactly the **confirmed relation proposals of
the latest valid Review Result**, derived deterministically as:

```text
every relation_proposal_verifications entry with outcome = CONFIRMED
normalized to the logical edge (kind, target Requirement ID)
```

Apply must not:

- invoke a model;
- derive relations from the Process Result or from anything else;
- apply a Process proposal that Review did not confirm;
- apply a `REJECTED` or `UNRESOLVED` proposal;
- apply anything from an older Review Result;
- write inverse sides separately.

### Mirror consistency — the artifact must agree with itself

The Review Result persists both `relation_proposal_verifications` and a
rendered `confirmed_relation_proposals` mirror. Apply is the first normative
consumer of those values, and it must not accept an artifact in which the two
disagree. After parsing, Apply requires:

```text
derived confirmed set (from verifications, normalized)
== persisted confirmed_relation_proposals (normalized the same way)
```

comparing relation kind and target Requirement ID. Any difference — a
`CONFIRMED` verification missing from the mirror, a mirror entry that is not
`CONFIRMED`, a wrong kind or target in the mirror — is:

```text
INVALID_REVIEW_RESULT
```

with no normative mutation. Neither representation is preferred and the
artifact is never repaired. The frozen Reviewer writes both from one value, so
the two can only disagree if the artifact was altered.

### Duplicate logical edges

For one source Requirement a relation's identity is `(kind, target Requirement
ID)`. The frozen Reviewer verifies each proposed edge exactly once, so a
persisted Review Result containing two confirmed entries for the same logical
edge is outside the frozen contract and is rejected as
`INVALID_REVIEW_RESULT`. Apply never writes a duplicate Fibery edge; with
Fibery's set semantics (constraint 26) it could not, but the artifact is
refused before that question arises.

## 6. Reviewed-state revalidation — before any normative mutation

Immediately before the first normative write, Apply resolves the latest Review
Result and the latest Process Result from current Fibery history (section 7),
recomputes the current canonical Root Document fingerprint, and requires:

```text
current canonical Root Document fingerprint
    == Review Result.reviewed_document_fingerprint
current latest Process Result iteration
    == Review Result.reviewed_process_iteration
that Process Result's output_fingerprint
    == Review Result.reviewed_process_output_fingerprint
current normative tree fingerprint (traversed afresh)
    == Review Result.reviewed_normative_tree fingerprint
both artifacts current-format (0.3, manifest v2) and coherent
    else NORMATIVE_TREE_EVIDENCE_REQUIRED, zero writes
```

These are the same four bindings the frozen Reviewer checks before certifying
and the frozen Ready Decision checks before approving
(Requirement-Normative-Tree-Binding-v0.1). The Process bindings are re-read
from Fibery, never trusted from the Review Result's copies, so the check
cannot be circular. Fingerprints use the frozen `canonical_markdown`
representation, which keeps fenced content literal. Legacy Root-only evidence
is never applied; an already `Applied` Requirement is untouched by this rule.

If any binding disagrees before the first write:

```text
REVIEW_RESULT_STALE
State remains Apply
relation writes = 0, Document writes = 0, State writes = 0, model calls = 0
```

Apply does not run Process, Review or Ready Decision, does not repair anything
and does not move the Requirement anywhere. The same three bindings are
checked again immediately before the final `Apply -> Applied` transition
(section 12).

### No Apply-level rework — an accepted operational limitation

Apply exposes no transition out of `Apply` except `Applied`. There is no
`Apply -> Process`, `Apply -> Review` or `Apply -> Ready` in this capability,
automatic or commanded. A Requirement that Apply refuses as stale, or leaves in
`Apply` after a partial application (section 14), stays there until an operator
acts on it directly in Fibery. That recovery workflow is deliberately not
designed here. The result codes and their details give the operator exactly
what moved and what was written, so the manual step is informed, but it is
manual.

## 7. Latest artifact selection

Identical to the frozen Reviewer and Ready Decision rules. Whether the
implementation shares code with Ready's history reader or restates it is an
implementation decision; the rules may not diverge and no separate parser for
the artifact formats is written.

```text
children of the Root Document named <Requirement ID> — Review Result NNNN
-> filter to this Requirement ID
-> two artifacts for one iteration           -> REVIEW_STATE_CONFLICT
-> the highest iteration is the latest
-> it must parse, supported version          -> else INVALID_REVIEW_RESULT
-> recorded iteration and Requirement ID must match its name
                                             -> else INVALID_REVIEW_RESULT
-> mirror consistency and no duplicate edge  -> else INVALID_REVIEW_RESULT
-> none found                                -> NO_REVIEW_RESULT

Process Result: same selection rules
-> none found                                -> NO_PROCESS_RESULT
-> duplicate, unparsable, identity mismatch  -> INVALID_PROCESS_RESULT
```

An older artifact is never used when the newest is unusable. The newest
artifact is current history and cannot be silently ignored.

## 8. Confirmed relations — the first normative consumer

Mapping, forward sides only:

```text
DEPENDS_ON  -> source.Depends On += target   (Fibery maintains target.Blocks)
AFFECTS     -> source.Affects   += target   (Fibery maintains target.Impacted By)
```

Each pair shares one Fibery relation id (frozen Process specification section
12), and constraint 26 verified that writing the forward side populates the
inverse. Apply never writes `Blocks` or `Impacted By` separately.

Writes use `fibery.entity/add-collection-items` (constraint 15), one edge per
command. `/api/commands` batches are not transactional (constraint 16), so
batching would buy nothing and would blur which edge failed.

### Policy: additive only

```text
confirmed edge absent            -> add it
confirmed edge already present   -> already satisfied, no write
existing edge not in the set     -> leave it untouched
```

Apply must not delete, replace, prune, diff or reconcile relations. Existing
edges, related or unrelated to the proposals, remain untouched. This is what
the frozen Process and Review contracts require of Apply, and what makes a
rejected proposal incapable of removing anything.

### Ensure-edge idempotency

Before the first write, Apply reads the Requirement's current `Depends On` and
`Affects` edges and computes the missing subset. Only missing edges are
written, one at a time. After the writes the edges are read back and every
confirmed edge must be present.

Constraint 26 verified that `add-collection-items` is idempotent: a repeated
add of a present item returns `ok` and leaves membership unchanged. Apply does
**not** rely on that for correctness. It reads before it writes so that its
report of what it wrote is exact and so that the design does not depend on a
Fibery property that could change; the verified behaviour is what makes an
accidental repeat harmless and is what the fake must reproduce.

## 9. Relation target preflight

Every confirmed proposal names a target by Requirement ID. Process and Review
only format-check that ID; nothing upstream has resolved it. Apply resolves
**all** targets before the first normative write, and refuses the whole
application if any target is unusable. No edge is written until every target
has passed.

Per target:

```text
Requirement ID resolves to 0 Requirements   -> RELATION_TARGET_NOT_FOUND
Requirement ID resolves to > 1 Requirements -> INVALID_RELATION_TARGET
target.Type = Standard                      else INVALID_RELATION_TARGET
target.Project = source.Project             else INVALID_RELATION_TARGET
target != source                            else INVALID_RELATION_TARGET
```

### Ambiguity-aware lookup

The frozen convenience lookup queries by Requirement ID with a limit of two but
returns only the first row, hiding a duplicate. That is insufficient for a
normative preflight: Apply must know whether there are zero, one or more than
one matches, and must never adopt one row when duplicates exist. The
implementation adds a bounded, count-aware lookup as an additive adapter
capability. The existing frozen lookup and its callers are not changed.

### Target workflow State is not restricted

A target may be in any State, including `Draft`, `Process`, `Review`, `Ready`
or `Apply`. Requirements approved as part of the same evolving project graph
legitimately reference one another before all have individually reached
`Applied`; target validation is about identity and graph validity, not about
the target's workflow completion. No `target must be Applied` rule exists and
none may be inferred.

## 10. No Root Document move — the Type/State placement contract

Amended 2026-09-09. The original contract moved the Root Document's
`fibery/Folder` from `Requirements/Draft` to `Requirements/Approved` because
Project Init section 11 fixed placement by folder. That folder model is
retired: lifecycle placement is the Requirement's Type and State, and
`State = Applied` is the only approved-placement signal.

Apply therefore:

- writes **no** Document: no Folder change, no body write, no create, no
  move, on any path; a successful Apply issues zero Document writes;
- reads no Project folder structure and requires none;
- does not inspect, check or repair the Root's `fibery/Folder`. A Root that
  still carries a legacy Folder (created before the amendment), one whose
  Folder a human later changed, and one with no Folder at all are applied
  identically;
- keeps the same Root Document entity, id, secret, body and nested children,
  and proves it through the reviewed-state bindings (section 6), which cover
  Root content and the normative tree.

Human navigation of Applied Requirements is the workspace-level Smart Folder
context view `Approved` (`Type = Standard AND State = Applied`), configured
once in the Fibery UI and never required by this command.

Historical: the mechanism that was used, `update-views` on `fibery/Folder`
(constraint 24), remains a verified fact and is no longer called.

## 11. Mutation ordering

```text
 1. resolve Requirement                       Type Standard; State Apply | Applied
 2. resolve the one contained Root Document
 3. resolve latest Review Result; parse; mirror consistency; no duplicate edge
 4. resolve latest Process Result; parse
 5. validate the reviewed-state bindings                          (section 6)
 6. preflight every relation target                              (section 9)
 7. read current Depends On / Affects; compute the missing edges
 8. revalidate the bindings immediately before the first write
    ------------------------------ first normative write ------------------
 9. add each missing confirmed edge, one command each; read back after each
10. revalidate the bindings again                                (section 12)
11. set State = Applied
12. read the Requirement back: State Applied, Revision unchanged
13. validate the final invariant                                 (section 13)
```

Steps 1–8 perform reads only. If any of them fails, nothing was written and the
result is the specific refusal. Every write from step 9 on is individually
verified by read-back, and `Applied` is written last, so it is a true
completion marker. No write happens before the complete target preflight.
With no confirmed edges to write, `Applied` is the first and only write; if
it does not take effect nothing durable exists, so the outcome is
`VALIDATION_FAILED`, not `PARTIAL_APPLY`.

## 12. Revalidation before Applied

Step 10 repeats the section 6 check, including a fresh traversal of the
normative tree. If the Root Document, a normative child or the Process
history moved during the application:

```text
do not transition to Applied
State remains Apply
result: PARTIAL_APPLY, details naming REVIEW_RESULT_STALE and what moved
durable completed steps remain
```

Edges written in step 9 are **not** reverted (section 15). This is the smallest protection available without a
compare-and-set primitive, and it is what guarantees a Requirement whose
content changed mid-application is never marked `Applied`.

## 13. Applied final invariant

A Requirement that completed Apply normally satisfies:

```text
Type = Standard
State = Applied
Revision unchanged from entry

the same Root Document entity exists, never written or moved
Root Document body unchanged from entry

every edge in the validated confirmed set exists
no existing edge present at entry was removed

Process Results unchanged, Review Results unchanged, child hierarchy preserved
the reviewed-state binding was valid immediately before State = Applied
```

After the final transition Apply re-reads the Requirement to confirm `Applied`
and the unchanged `Revision`; the edge read-backs happened at step 9. Apply does not claim the binding can never change *after* the
transition: a human may edit the Root Document one second later, and that is a
revision question this specification does not design.

## 14. Partial failure and resume

Apply is the first stage with more than one normative write, so a failure can
leave durable state behind. The principle:

```text
the Requirement remains Apply until every step has succeeded
```

Any failure after the first normative write returns `PARTIAL_APPLY`, listing
exactly what became durable (edges written) and the failing step's
code and cause, following the `PARTIAL_PROCESSING` / `PARTIAL_REVIEW`
convention. Failures before the first write return their specific code and
report nothing durable, because nothing is.

A retry performs the whole sequence again. Because every write is an
ensure-state operation, the retry naturally completes only what is missing:

```text
edge 1 written, edge 2 not             -> step 7 finds 1 present; writes only 2
all edges written, Applied failed      -> step 9 writes nothing; step 11
```

The retry revalidates the reviewed binding first (steps 5 and 9), so a
Requirement edited between the failure and the retry is refused as stale rather
than completed. No edge is duplicated, no Root Document is recreated, and no
recovery subsystem or resume artifact is needed: the durable domain state *is*
the progress record.

## 15. No destructive rollback

If a later step fails after an edge was written, the edge stays. Reasons:

- the edge was reviewed and human-approved; it is not wrong, it is early;
- relation removal semantics are undesigned, and inventing them inside an error
  path is the worst place to do it;
- the Requirement stays in `Apply` and the retry completes the application,
  which is the normal recovery.

This mirrors the partial-state philosophy of every frozen capability: durable
state is reported and left in place, never silently deleted.

## 16. Idempotency and the workflow-state boundary

```text
apply, State = Apply     validate, apply missing steps, transition, read back
apply, State = Applied   REQUIREMENT_ALREADY_APPLIED, zero mutations
apply, any other State   REQUIREMENT_NOT_IN_APPLY, zero mutations
```

`REQUIREMENT_ALREADY_APPLIED` is a normal result. It performs no mutation, no
repair, no edge write and no Document move. It may report, as information,
whether the Root Document is under `Approved`, but it must not claim that an
arbitrary `Applied` Requirement satisfies the full Apply invariant: a
Requirement a human placed in `Applied` by hand looks the same as one Apply
completed. Automatically repairing it would mean writing relations and moving
Documents on the strength of a State nobody validated, so v0.1 does not.

The same boundary applies on entry: State `Apply` does not say which control
surface set it, and under `Requirement-Lifecycle-Ownership-v0.2` a direct human
transition is the normal path (section 4). Apply's answer is the strongest
one available from current state — require `Apply`, require a valid current
reviewed binding, write only what the latest valid Review Result confirmed. No
approval ledger is introduced to close the remaining gap.

## 17. Revision

`Requirement.Revision` is never written. Revision semantics are undesigned in
the frozen architecture, and Apply is not a material revision of the
Requirement's content. Read-back verifies it did not change.

## 18. Root content and artifacts

Zero writes to the Root Document, to any Process Result and to any Review
Result. Apply reads them. It never edits, deletes, rewrites, copies or moves
them.

## 19. Model runtime

```text
model calls = 0
```

No role is added to `config/sdlc.toml`, the library entry point takes no
`ModelRuntime`, and the CLI handler never constructs one.

## 20. Workspace protocol

A narrow `ApplyWorkspace` protocol, in the pattern of `ReadyDecisionWorkspace`:

```text
reads   read_requirement, count-aware lookup by Requirement ID,
        read_project, documents_attached_to_requirement, child_documents,
        read_document_content, requirement_relations
writes  add_depends_on / add_affects(entity_id, target_entity_id)
        set_requirement_state(entity_id, state)
```

No document content write, no document create, no document move, no relation
removal. What the protocol omits, the capability structurally cannot do.

## 21. Result vocabulary

Following the existing `results.py` conventions.

Normal, exiting zero:

```text
REQUIREMENT_APPLIED
REQUIREMENT_ALREADY_APPLIED
```

Validation and decision:

```text
REQUIREMENT_NOT_FOUND
NOT_A_STANDARD_REQUIREMENT
REQUIREMENT_NOT_IN_APPLY
PROJECT_STRUCTURE_INVALID        no resolvable Project, Root Document count
NO_PROCESS_RESULT
INVALID_PROCESS_RESULT
NO_REVIEW_RESULT
INVALID_REVIEW_RESULT            includes mirror mismatch and duplicate logical edge
REVIEW_STATE_CONFLICT
REVIEW_RESULT_STALE              before the first write
RELATION_TARGET_NOT_FOUND
INVALID_RELATION_TARGET          ambiguous, not Standard, other Project, self
```

Partial and infrastructure:

```text
PARTIAL_APPLY                    durable steps exist; the Requirement stays in Apply
FIBERY_READ_FAILED
FIBERY_WRITE_FAILED
VALIDATION_FAILED                a write did not read back as expected
```

`PARTIAL_APPLY` carries the durable steps in `created` and the underlying code
in `details`, as the frozen partial results do. A binding that moved after the
first write is `PARTIAL_APPLY` whose details name `REVIEW_RESULT_STALE`.

## 22. Concurrency — accepted limitation

Fibery offers no compare-and-set, no entity version and no conditional update
that this project has found; constraint 16 establishes that even a command
batch is not transactional. Apply cannot make "validate, then write" atomic
around:

```text
binding validation -> edge writes -> Applied transition
```

The residual race:

```text
validate reviewed state
-> write an approved edge
-> concurrent Root Document edit
-> final revalidation detects drift
```

produces:

```text
PARTIAL_APPLY
State remains Apply
the written approved edge remains
```

Mitigation, in order of effect:

1. every check happens immediately before the first write (step 9), never on
   previously displayed state;
2. the binding is revalidated before `Applied` (step 12), so a Requirement
   whose content moved is never marked `Applied`;
3. the writes are additive edges a human reviewed and approved; nothing is
   destroyed.

This can temporarily leave a normative relation attached to a Requirement whose
content subsequently drifted. For v0.1 that is accepted under the project's
established partial-state philosophy: the race cannot mark stale content
`Applied`, cannot remove anything, and cannot write an edge no human approved.
Relation removal and recovery semantics are not designed here. If a Fibery
primitive for conditional updates is discovered, it belongs between steps 9
and 10 as a single-check replacement, not as a locking subsystem.

### Relation target races

A target resolved at preflight may be deleted before its edge is written. The
write then fails and the edge read-back proves it absent; the result is
`PARTIAL_APPLY` or `FIBERY_WRITE_FAILED` depending on what preceded it. A
target whose State or content changes after preflight is not re-checked:
relations bind identities, not content, so identity resolved at preflight is
the only thing the write depends on. No locking.

## 23. Fibery fake fidelity

The behaviours Apply depends on were verified live on 2026-09-04 and are
recorded as constraint 26 (constraints 24 and 25, the Folder move and its
effect on children, were verified then and are no longer used). The
implementation fake must reproduce them exactly, and deterministic tests must
exercise each:

```text
add-collection-items is idempotent; membership is a set
the inverse side (Blocks / Impacted By) appears on the target
Apply -> Applied State transition and read-back
count-aware lookup by Requirement ID
```

Any behaviour the implementation needs beyond these must itself be verified
live before it enters the fake. `fake green != integration proven`.

## 24. Required tests

Deterministic, against the Fibery fake. Mutation-log assertions, not final
equality, wherever the guarantee is "no write attempted".

### Entry and idempotency

```text
Standard + Apply accepted
Raw refused; every other State refused; zero mutations
Applied -> REQUIREMENT_ALREADY_APPLIED, zero mutations, no repair
```

### Reviewed binding

```text
Root fingerprint changed                  -> REVIEW_RESULT_STALE
normative child changed after review      -> REVIEW_RESULT_STALE
Process iteration changed                 -> REVIEW_RESULT_STALE
Process output fingerprint changed        -> REVIEW_RESULT_STALE
legacy 0.1 Process or Review Result       -> NORMATIVE_TREE_EVIDENCE_REQUIRED
missing / malformed / duplicate Review Result
missing / malformed / duplicate Process Result
older artifact never used as fallback
every case -> zero relation, Document and State writes
```

### Review Result consistency

```text
CONFIRMED verifications == confirmed_relation_proposals   -> accepted
verification CONFIRMED but absent from the mirror          -> INVALID_REVIEW_RESULT
mirror contains an edge that is not CONFIRMED              -> INVALID_REVIEW_RESULT
mirror has the wrong kind or target for an edge            -> INVALID_REVIEW_RESULT
duplicate logical confirmed edge                           -> INVALID_REVIEW_RESULT
every refusal -> zero normative mutation
```

### Relations

```text
zero confirmed proposals                  -> no relation write, no Document write, Applied
one DEPENDS_ON; one AFFECTS; several mixed
edge already present                      -> not written again, still Applied
target missing                            -> RELATION_TARGET_NOT_FOUND, zero writes
two Requirements with the same Requirement ID -> INVALID_RELATION_TARGET, zero writes
target Raw / other Project / self         -> INVALID_RELATION_TARGET, zero writes
one bad target among several good ones    -> zero writes (full preflight)
target in Draft, Process, Review, Ready   -> accepted
inverse side (Blocks / Impacted By) reads back on the target
REJECTED and UNRESOLVED proposals never written
unconfirmed Process proposals never written
existing unrelated edges never removed
repeated add of a present edge is a no-op in the fake, as verified live
```

### Root Document and hierarchy

```text
same Document id, same secret, same legacy Folder, body unchanged
a Root with a legacy Draft, Approved or Raw Folder, or none -> applied identically
child Process / Review Results keep parent-page-id, Folder and content
zero Document writes on the successful path; no write to any child
no folder read of any kind
```

### Partial failure and resume

```text
fail after the first of two edges         -> PARTIAL_APPLY, State Apply
fail after all edges, before Applied
fail during the Applied write / read-back
each: retry completes with no duplicate edge, no second Root, one Applied
```

### Stale during Apply

```text
binding moves before the first write      -> REVIEW_RESULT_STALE, zero writes
binding moves after edges were written    -> edges kept, no Document write,
                                             no Applied, PARTIAL_APPLY (stale)
a child edited between the checkpoints    -> the same, named in the details
```

### Final invariant and hard immutability

```text
State Applied, Root Approved, confirmed edges present, Revision unchanged,
Root body / Process Results / Review Results byte-identical, model = 0
zero Root body writes, artifact writes, relation removals, Revision writes,
writes to any Requirement other than the source's forward relations
```

## 25. Live acceptance before freeze

On a temporary Project, the frozen chain:

```text
project init -> requirement add -> RAW Process -> Standard Process
             -> Standard Review -> Ready APPROVE -> Apply
```

with at least two Standard Requirements so that the Review Result of one can
confirm a relation to the other. Verify independently in Fibery:

```text
same Requirement entity, State = Applied, Revision unchanged
same Root Document entity, same Folder value as before (legacy or none), body unchanged
Process Results and Review Results unchanged and still nested under the Root
only the confirmed proposals became edges; pre-existing edges preserved
the inverse side is visible on the target
model calls = 0
```

Also exercise one bounded partial or refusal path if safely practical, most
cheaply by editing the Root Document after Ready and confirming
`REVIEW_RESULT_STALE` with zero writes, and one retry after a completed
application returning `REQUIREMENT_ALREADY_APPLIED`.

Temporary identities only; clean up exactly what the run created.

## 26. Non-goals

```text
requirement quality reasoning     human approval or acknowledgement
a new Review                      relation deletion, replacement or pruning
Apply-level rework transitions    operator recovery workflow
Requirement revision / update     supersession, split or merge
a Rejected state                  approval ledger or Apply Result artifact
Open Questions emptiness gate     backlog, Project Phases, Epics, Stories, Tasks
GitHub or implementation mapping  deployment
transactions or locking           automatic rollback
```

## 27. Decisions recorded and accepted limitations

Decisions approved with this contract:

1. Relation target workflow State is unrestricted (section 9).
2. `Open Questions` need not be empty before `Applied`; no further quality
   gate exists (section 4).
3. No Apply-level rework; manual operator recovery is the v0.1 path for a
   stale or partially applied Requirement (section 6).
4. A count-aware lookup by Requirement ID is added as an additive adapter
   capability; the frozen lookup and its callers are unchanged (section 9).
5. The persisted `confirmed_relation_proposals` mirror must equal the derived
   confirmed set; disagreement is `INVALID_REVIEW_RESULT` (section 5).
6. No Apply Result artifact; progress is observable from State and edges
   (section 14).
7. Apply reads edges before writing and does not rely on Fibery's verified
   idempotent add for correctness (section 8).

Accepted limitations, documented rather than engineered around:

8. The validate-then-write race and the approved edge it may leave behind
   (section 22).
9. `State = Apply` and `State = Applied` cannot distinguish validated
   transitions from manual ones (section 16).

No `DESIGN_BLOCKER`: the three Fibery capabilities the design depends on were
verified live before this contract was approved.
