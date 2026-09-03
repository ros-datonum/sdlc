# Standard Requirement Apply Specification v0.1 — PROPOSED

**Status:** PROPOSED. Not approved. Nothing implements it.

Design pass for `Requirement.Type = Standard` + `Requirement.State = Apply`.

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

`Apply` is **not another reasoning stage and not another approval stage**. The
human approval has already been recorded durably by `Ready -> Apply`. Apply
turns what was reviewed and approved into canonical Fibery state:

1. verify that the Requirement still matches the exact state that was reviewed
   and approved;
2. write the confirmed relation proposals as real `Depends On` / `Affects`
   edges;
3. move the Root Document from `Requirements/Draft` to `Requirements/Approved`;
4. transition `Apply -> Applied`;
5. validate every write by reading it back.

No model invocation, no judgement of Requirement quality, no verdict
acknowledgement, no human input. "Apply" means *apply the approved Standard
Requirement into the authoritative requirements graph and document structure*.
It does not mean implement the software requirement.

Proposed command, following the existing one-verb-per-command convention:

```text
sdlc project requirement apply --requirement <entity id>
```

No `--runtime`, `--model`, `--acknowledge-verdict` or `--force`. No flag is
required: everything Apply needs is durable in Fibery.

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

Apply therefore never asks whether the Requirement should be approved. It does
not re-run or re-read the `PASS` / `NEEDS_WORK` / `BLOCKING` acknowledgement,
does not reinterpret findings, and does not refuse a Requirement because its
verdict was not `PASS`. The human decided; Apply executes.

What Apply does do is **revalidate the exact reviewed binding before any
normative mutation** (section 6). That is the interface invariant Ready
recorded for it, and it is the only correctness check Apply adds.

No `Approval Result`, approval ledger, approval field or approval relation is
introduced. The workflow State plus the latest valid Review Result already
carry everything Apply needs.

## 5. Inputs, and the only relation source of truth

```text
the Requirement entity (Requirement ID, Type, State, Revision, Project)
its Root Document, current content and current Folder
the Project folder structure (Requirements/Draft, Requirements/Approved)
the latest valid Review Result
the latest valid Process Result
the Requirement's existing Depends On / Affects edges
the target Requirements named by confirmed relation proposals
```

The relations Apply may write are exactly the **confirmed relation proposals of
the latest valid Review Result**: the `relation_proposal_verifications` whose
outcome is `CONFIRMED`. The frozen parser derives that set from the
verifications on read-back; the persisted `confirmed_relation_proposals` key is
a rendered mirror written by the same code and is not consulted separately.

Apply must not:

- invoke a model;
- derive relations from the Process Result;
- apply a Process proposal that Review did not confirm;
- apply a `REJECTED` or `UNRESOLVED` proposal;
- apply anything from an older Review Result.

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
```

These are the same three bindings the frozen Reviewer checks before certifying
and the frozen Ready Decision checks before approving. The Process bindings are
re-read from Fibery, never trusted from the Review Result's copies, so the check
cannot be circular. Fingerprints use the frozen `canonical_markdown`
representation, which keeps fenced content literal.

If any binding disagrees:

```text
REVIEW_RESULT_STALE
```

with:

```text
relation writes         = 0
Document folder writes  = 0
State writes            = 0
model calls             = 0
```

Apply does not run Process, Review or Ready Decision, and does not repair
anything. The Requirement stays in `Apply`; the human returns it to work by
moving it to `Process` themselves, exactly as the Ready contract's `REWORK`
does from `Ready`. Whether Apply should expose a rework decision of its own is
an open question (section 27); the smallest design does not.

The same three bindings are checked a second time immediately before the
final `Apply -> Applied` transition (section 12).

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
-> none found                                -> NO_REVIEW_RESULT

Process Result: same rules
-> none found                                -> NO_PROCESS_RESULT
-> duplicate, unparsable, identity mismatch  -> INVALID_PROCESS_RESULT
```

An older artifact is never used when the newest is unusable. The newest
artifact is current history and cannot be silently ignored.

Two structural checks are specific to what Apply consumes, applied after
parsing and before any write:

- two confirmed proposals for the same `(kind, requirement_id)` edge:
  `INVALID_REVIEW_RESULT`. The frozen Reviewer verifies each edge exactly once,
  so a duplicate cannot come from the frozen chain;
- a confirmed proposal naming the Requirement itself:
  `INVALID_RELATION_TARGET` (section 9).

## 8. Confirmed relations — the first normative consumer

Mapping, forward sides only:

```text
DEPENDS_ON  -> Requirement.Depends On   (Fibery maintains Blocks)
AFFECTS     -> Requirement.Affects      (Fibery maintains Impacted By)
```

Each pair shares one Fibery relation id (frozen Process specification section
12), so writing the forward side populates the inverse. Apply never writes
`Blocks` or `Impacted By` separately.

Writes use `fibery.entity/add-collection-items` (constraint 15), one edge per
command. `/api/commands` batches are not transactional (constraint 16), so
batching would buy nothing and would blur which edge failed.

### Policy: additive only

```text
confirmed proposal -> ensure the edge exists
```

Apply must not:

- delete any existing edge;
- treat absence from the latest Review Result as permission to remove an edge;
- replace the Requirement's relation set with the confirmed set;
- prune, diff or reconcile.

Existing edges, related or unrelated to the proposals, remain untouched. This
is what the frozen Process and Review contracts require of Apply, and what
makes a rejected proposal incapable of removing anything.

### Ensure-edge idempotency

Before the first write, Apply reads the Requirement's current `Depends On` and
`Affects` edges and computes the missing subset. Only missing edges are
written. After the writes, the edges are read back and every confirmed edge
must be present.

Whether `add-collection-items` is itself idempotent for an already-present item
is **not known** and must be verified live before freeze (section 27). The
read-then-write design does not depend on the answer for correctness, only for
the narrow race in section 22; the answer must be recorded in the constraints
document either way.

## 9. Relation target preflight

Every confirmed proposal names a target by Requirement ID. Process and Review
only format-check that ID; nothing upstream has resolved it. Apply resolves
**all** targets before the first normative write, and refuses the whole
application if any target is unusable. No edge is written until every target
has passed.

Per target:

```text
resolves to exactly one Requirement by Requirement ID
                                          else RELATION_TARGET_NOT_FOUND
                                          (or INVALID_RELATION_TARGET if ambiguous)
target.Type = Standard                    else INVALID_RELATION_TARGET
target.Project = source.Project           else INVALID_RELATION_TARGET
target != source                          else INVALID_RELATION_TARGET
```

Target workflow State is **not** restricted. Requirements approved in the same
batch legitimately depend on each other before all of them reach `Applied`,
and a dependency on a Requirement still in `Draft` is exactly the kind of edge
the graph exists to show. No invariant requires "target already Applied", so it
is not imposed.

Resolution by Requirement ID must detect ambiguity. The frozen adapter's
`find_requirement_by_requirement_id` queries with a limit of two but returns
only the first row; Apply needs the count. This is an additive interface need,
not a change to frozen behaviour (section 27).

## 10. Root Document move — required by the frozen document contract

The frozen Project Init specification (section 11) fixes the placement:

```text
State != Applied   -> Requirements/Draft/
State  = Applied   -> Requirements/Approved/
```

and states that on successful application the Root Document is **moved** from
`Draft` to `Approved`. Apply therefore changes the Root Document's
`fibery/Folder` from the Project's `Requirements/Draft` Folder to its
`Requirements/Approved` Folder before the final transition.

Rules:

- the **same Root Document entity** moves; no second Root Document is created,
  no copy is placed under `Approved`;
- the Root Document body is not written; the only Document mutation is the
  Folder;
- `Draft` and `Approved` are resolved by real Folder ids from the Project's
  Documents Root Folder through the single-child rule the frozen RAW Processor
  already uses (`PROJECT_STRUCTURE_INVALID` if the tree is ambiguous);
- Process Results and Review Results are nested under the Root through
  `fibery/parent-page-id` and carry no `fibery/Folder` of their own
  (constraint 19). The expected consequence is that moving the Root moves the
  whole hierarchy with it and no child is touched. **This must be verified
  live** before freeze (section 27); if Fibery turns out to require child
  updates, that is a design change, not an implementation detail.

### Folder idempotency

```text
Root in Draft       -> move to Approved
Root in Approved    -> already done; no write
Root anywhere else  -> PROJECT_STRUCTURE_INVALID, no write
```

An unexpected Folder is never silently repaired.

### The API for the move is unverified

`create-views` accepts `fibery/Folder`, and the Folder API exposes
`update-folders` with `{updates: [{id, values}]}` (constraint 1). The
corresponding `update-views` method has not been exercised. Its existence and
shape must be verified by a narrow live probe during implementation; a
Document cannot be moved by deletion and re-creation, because that would change
the Root Document entity and orphan its children.

## 11. Mutation ordering

```text
 1. resolve Requirement              (Type Standard, State Apply | Applied)
 2. resolve Root Document, current Folder, Draft and Approved Folder ids
 3. resolve latest Review Result, latest Process Result, current Root content
 4. validate the three reviewed-state bindings          (section 6)
 5. structural checks on confirmed proposals            (section 7)
 6. preflight every relation target                     (section 9)
 7. read current Depends On / Affects; compute missing edges
 8. inspect Root Folder                                 (section 10)
    ------------------------------ first normative write ------------------
 9. write each missing edge, one command each
10. read edges back; every confirmed edge must be present
11. move Root Draft -> Approved if not already there
12. read Root back; Folder must be Approved
13. revalidate the three reviewed-state bindings        (section 12)
14. set State = Applied
15. read the Requirement back; State must be Applied, Revision unchanged
```

Steps 1–8 perform reads only. If any of them fails, nothing was written and the
result is the specific refusal. Every write from step 9 on is individually
verified by read-back, and `Applied` is written last, so it is a true
completion marker.

Relations are written before the Root move because the move is the more
visible change: a Root under `Approved` with edges still missing would look
finished to a human browsing Fibery, while missing edges under `Draft` do not.

## 12. Revalidation before Applied

Step 13 repeats the section 6 check. If the Root Document or the Process
history moved during the application:

```text
do not transition to Applied
Requirement remains Apply
result: PARTIAL_APPLY with REVIEW_RESULT_STALE in its details
```

Edges written in step 9 are **not** removed (section 15). This is the smallest
protection available without a compare-and-set primitive, and it is what keeps
a Requirement whose content changed mid-application from being marked
`Applied`.

## 13. Applied final invariant

A Requirement that completed Apply normally satisfies:

```text
Type = Standard
State = Applied
Revision unchanged from entry

the same Root Document entity exists
Root Document Folder = Requirements/Approved
Root Document body unchanged from entry

every confirmed relation proposal of the applied Review Result is an edge
existing edges present at entry are still present

Process Results unchanged, Review Results unchanged, hierarchy preserved
the reviewed-state binding was valid immediately before State = Applied
```

After the final transition Apply re-reads the Requirement to confirm `Applied`
and the unchanged `Revision`; the relation and Folder read-backs happened at
steps 10 and 12. Apply does not claim the binding is still valid *after* the
transition: a human may edit the Root Document one second later, and that is a
revision question this specification does not design.

## 14. Partial failure and resume

Apply is the first stage with more than one normative write, so a failure can
leave durable state behind. The principle:

```text
the Requirement remains Apply until every step has succeeded
```

Any failure after the first normative write returns `PARTIAL_APPLY`, listing
exactly what became durable (edges written, Root moved) and the failing step's
code and cause, following the `PARTIAL_PROCESSING` / `PARTIAL_REVIEW`
convention. Failures before the first write return their specific code and
report nothing durable, because nothing is.

A retry performs the whole sequence again. Because every write is an
ensure-state operation, the retry naturally completes only what is missing:

```text
relation 1 written, relation 2 not     -> step 7 finds 1 present; writes only 2
all relations written, move failed     -> step 7 writes nothing; step 11 moves
relations + move done, Applied failed  -> steps 9 and 11 write nothing; step 14
```

The retry revalidates the reviewed binding first (step 4), so a Requirement
edited between the failure and the retry is refused as stale rather than
completed. No relation is duplicated (edges are read before written), no Root
Document is recreated (only its Folder is ever written), and no recovery
subsystem or resume artifact is needed: the durable domain state *is* the
progress record.

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

`REQUIREMENT_ALREADY_APPLIED` is a normal result. It may report, as
information, whether the Root Document is under `Approved`; it performs no
mutation and no repair. A Requirement a human placed in `Applied` by hand looks
the same as one Apply completed, exactly as the Ready contract accepts for
`Apply`. Automatically repairing an arbitrary `Applied` Requirement would mean
writing relations and moving Documents on the strength of a State nobody
validated, so v0.1 does not.

The same boundary applies on entry: State `Apply` cannot distinguish a
validated approval from a manual transition. Apply's answer is the strongest
one available from current state — require `Apply`, require a valid current
reviewed binding, write only what the latest valid Review Result confirmed. No
approval ledger is introduced to close the remaining gap.

## 17. Revision

`Requirement.Revision` is never written. Revision semantics are undesigned in
the frozen architecture, and Apply is not a material revision of the
Requirement's content. Read-back verifies it did not change. Any argument that
`Applied` should be a revision boundary is a design blocker to raise before
implementation, not a default.

## 18. Root content and artifacts

Zero writes to the Root Document body, to any Process Result and to any Review
Result. Apply reads them. It never edits, deletes, rewrites, copies or
independently moves them; they follow their parent Root only as a consequence
of the Root's Folder change, if Fibery navigates that way.

The Root Document's `Open Questions` section is **not** required to be empty
before `Applied` in v0.1. The frozen Document Schema left that possibility
open; imposing it here would add a content gate after the human already
approved the Requirement with its open questions visible in the Review Result.
Recorded as a decision for approval (section 27).

## 19. Model runtime

```text
model calls = 0
```

No role is added to `config/sdlc.toml`, the library entry point takes no
`ModelRuntime`, and the CLI handler never constructs one.

## 20. Workspace protocol

A narrow `ApplyWorkspace` protocol, in the pattern of `ReadyDecisionWorkspace`:

```text
reads   read_requirement, find_requirement_by_requirement_id (with count),
        read_project, resolve_folder, child_folders,
        documents_attached_to_requirement, child_documents,
        read_document_content, requirement_relations
writes  add_requirement_relation(entity_id, kind, target_entity_id)
        set_document_folder(document_id, folder_id)
        set_requirement_state(entity_id, state)
```

No document content write, no document create, no relation removal. What the
protocol omits, the capability structurally cannot do.

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
PROJECT_STRUCTURE_INVALID        folder tree, Root Document count, unexpected Root Folder
NO_PROCESS_RESULT
INVALID_PROCESS_RESULT
NO_REVIEW_RESULT
INVALID_REVIEW_RESULT            includes duplicate confirmed edges
REVIEW_STATE_CONFLICT
REVIEW_RESULT_STALE
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
in `details`, as the frozen partial results do. A binding that moved
mid-application is `PARTIAL_APPLY` whose details name `REVIEW_RESULT_STALE`.

## 22. Concurrency — assessed explicitly

Fibery offers no compare-and-set, no entity version and no conditional update
that this project has found; constraint 16 establishes that even a command
batch is not transactional. Apply cannot make "validate, then write" atomic.

The exposure is larger than Ready's, because Apply writes normative graph data:

```text
step 4 validates the binding
-> a human edits the Root Document
-> steps 9–11 write edges and move the Root
-> step 13 detects the drift
```

Mitigation, in order of effect:

1. every check happens immediately before the first write, never on
   previously displayed state;
2. the binding is revalidated before `Applied` (step 13), so a Requirement
   whose content moved is never marked `Applied`;
3. the writes are additive edges that a human reviewed and approved, and a
   Folder move; neither destroys anything, and the retry after rework
   completes or re-confirms them.

What remains: a narrow window in which approved edges are written for content
that changed a moment later. The Requirement then stays in `Apply` with
`PARTIAL_APPLY`, and the human's next action is rework, after which a new
Process and Review either re-confirm the same edges or stop proposing them. In
the second case the edges persist, because removal is undesigned; that is the
frozen contracts' explicit choice, not a new consequence of the race.

**Assessment: accepted v0.1 limitation, not a design blocker.** The race cannot
mark stale content `Applied`, cannot remove anything, and cannot write an edge
no human approved. If a Fibery primitive for conditional updates is discovered,
it belongs in step 4 → 9 as a single-check replacement, not as a locking
subsystem.

### Relation target races

A target resolved at preflight may be deleted before its edge is written. The
write then fails and the edge read-back proves it absent; the result is
`PARTIAL_APPLY` or `FIBERY_WRITE_FAILED` depending on what preceded it. A
target whose State or content changes after preflight is not re-checked:
relations bind identities, not content, so identity resolved at preflight is
the only thing the write depends on. No locking.

## 23. Fibery fake fidelity

Every new Fibery behaviour must be verified live, reflected in the fake, and
covered by deterministic tests before freeze. Apply introduces four:

```text
add-collection-items for Depends On / Affects, its idempotency, and read-back
Document Folder update, and the child hierarchy after it
Apply -> Applied State transition and read-back
Requirement ID resolution with ambiguity detection
```

The fake must model whatever the live probe shows for a repeated
`add-collection-items` of the same item, and must reproduce the read-back
shape of the inverse side. `fake green != integration proven`.

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
Process iteration changed                 -> REVIEW_RESULT_STALE
Process output fingerprint changed        -> REVIEW_RESULT_STALE
missing / malformed / duplicate Review Result
missing / malformed / duplicate Process Result
older artifact never used as fallback
every case -> zero relation, Folder and State writes
```

### Relations

```text
zero confirmed proposals                  -> no relation write, Root moved, Applied
one DEPENDS_ON; one AFFECTS; several mixed
edge already present                      -> not written again, still Applied
duplicate confirmed edge in the artifact  -> INVALID_REVIEW_RESULT, zero writes
target missing / ambiguous / Raw / other Project / self -> refused, zero writes
one bad target among several good ones    -> zero writes (full preflight)
target in Draft or Ready                  -> accepted
inverse side (Blocks / Impacted By) reads back on the target
REJECTED and UNRESOLVED proposals never written
unconfirmed Process proposals never written
existing unrelated edges never removed
```

### Root Folder

```text
Draft -> Approved, same Document id, body unchanged
already Approved -> no Folder write, application completes
neither Draft nor Approved -> PROJECT_STRUCTURE_INVALID, zero writes
child Process / Review Results keep their parent and their content
```

### Partial failure and resume

```text
fail after the first of two edges         -> PARTIAL_APPLY, State Apply
fail after all edges, before the move
fail during the Folder move
fail after the move, before Applied
fail during the Applied write / read-back
each: retry completes with no duplicate edge, no second Root, one Applied
```

### Stale during Apply

```text
binding moves before the first write      -> zero writes
binding moves after edges were written    -> edges kept, Root move as reached,
                                             no Applied, PARTIAL_APPLY (stale)
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
same Root Document entity, Folder = Requirements/Approved, body unchanged
Process Results and Review Results unchanged and still nested under the Root
only the confirmed proposals became edges; pre-existing edges preserved
the inverse side is visible on the target
model calls = 0
```

Also exercise one bounded partial path if safely practical, most cheaply by
editing the Root Document after Ready and confirming `REVIEW_RESULT_STALE`
with zero writes, and one retry after a completed application returning
`REQUIREMENT_ALREADY_APPLIED`.

Before this acceptance, the narrow probes of section 27 must have answered the
three unverified Fibery questions. Temporary identities only; clean up exactly
what the run created.

## 26. Non-goals

```text
requirement quality reasoning     human approval or acknowledgement
a new Review                      relation deletion, replacement or pruning
Requirement revision / update     supersession, split or merge
a Rejected state                  approval ledger or Apply Result artifact
Open Questions emptiness gate     backlog, Project Phases, Epics, Stories, Tasks
GitHub or implementation mapping  deployment
transactions or locking           automatic rollback
```

## 27. Unresolved questions and blockers

Questions that must be answered by a narrow live probe during implementation,
before freeze. None of them changes the design above unless the answer is
negative:

1. **`update-views` with `fibery/Folder`.** Not yet exercised. If no method can
   change a Document's Folder in place, the Root move cannot be implemented
   without recreating the Document, which this design forbids. That outcome
   would be a `DESIGN_BLOCKER`.
2. **`add-collection-items` for an item already present.** No-op, duplicate,
   or error. The read-then-write design is correct under all three; the fake
   must model the real one.
3. **Child Documents after the Root's Folder changes.** Expected to follow the
   parent with no write (constraint 19). If Fibery requires per-child updates,
   the design must be extended before implementation.

Decisions recorded for approval:

4. Target workflow State is not restricted (section 9).
5. `Open Questions` need not be empty before `Applied` (section 18).
6. Apply exposes no rework decision; a stale Requirement in `Apply` is returned
   to `Process` by the human directly in Fibery. The alternative is a second
   `rework` entry point accepting `Apply`, which is additive and can be decided
   later without changing anything here.
7. Ambiguity-aware resolution by Requirement ID is an additive adapter method;
   frozen callers of the existing method are not changed.
8. The persisted `confirmed_relation_proposals` mirror is not cross-checked
   against the derived set. The frozen Reviewer writes both from one value.

Accepted limitations, documented rather than engineered around:

9. The validate-then-write race (section 22).
10. `State = Apply` and `State = Applied` cannot distinguish validated
    transitions from manual ones (section 16).

No `DESIGN_BLOCKER` is known today. Item 1 is the only question whose negative
answer would create one.
