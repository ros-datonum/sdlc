# Standard Requirement Ready Decision Specification v0.1

**Status:** APPROVED. Frozen contract for implementation. No implementation exists yet.

Design for `Requirement.Type = Standard` + `Requirement.State = Ready`.

## 1. Lifecycle position

```text
Draft -> Process -> Review -> Ready -> Apply -> Applied
```

`Process` and `Review` are frozen. This capability performs the human decision at
`Ready`, and nothing else.

## 2. What Ready is

```text
Process   normalize + analyze + propose        model, writing
Review    independently verify + confirm       model, verifying
Ready     human decision boundary              HUMAN
Apply     human-approved application begins    deterministic
```

`Ready` is **not another autonomous stage**. It is the boundary where the system
stops deciding and a person does. Ready Decision performs no AI reasoning. It
records an explicit human decision through an existing workflow transition, after
deterministically validating that the decision applies to the Requirement state
that was actually reviewed.

Its entire job is one state transition plus the checks that make that transition
honest.

## 3. Entry condition

```text
Requirement.Type  = Standard
Requirement.State = Ready
```

Anything else is refused with zero Fibery mutations. Two states are additionally
accepted as **already-done** rather than errors, for idempotency (section 15):
`Apply` for approve, `Process` for rework.

## 4. The two decisions

```text
APPROVE   Ready -> Apply
REWORK    Ready -> Process
```

That is the whole vocabulary for v0.1. No additional Requirement states and no
additional decision types: no `Rejected`, `Archived`, `Withdrawn` or `Cancelled`.
A Requirement that should not exist is one the human declines to approve, and
disposing of it is outside this capability.

Proposed commands, following the existing one-verb-per-command convention:

```text
sdlc project requirement approve --requirement <entity id>
                                 [--acknowledge-verdict <VERDICT>]
sdlc project requirement rework  --requirement <entity id>
```

## 5. Approval evidence — exactly what workflow State proves

This is the load-bearing distinction of the whole design, and it is deliberately
narrower than "state is enough".

```text
State = Apply
```

**is** sufficient durable evidence that:

> a human approval decision was successfully recorded.

It is **not**, by itself, sufficient evidence of:

> which exact Requirement content remains valid for future normative application.

That second binding never comes from the workflow state. It comes from:

```text
the latest valid Review Result
  + its reviewed_document_fingerprint
  + its reviewed_process_iteration
  + its reviewed_process_output_fingerprint
  + its reviewed_normative_tree (Requirement-Normative-Tree-Binding-v0.1)
```

Ready Decision validates those bindings immediately before `Ready -> Apply`
(section 6). The future `Apply` capability must revalidate the same reviewed
state before performing any normative mutation (section 18). Neither stage trusts
the other's timing, because the Root Document can be edited in Fibery at any
moment by a human.

### Why no additional artifact is needed

Because the decision signal and the content binding are separable, and both are
already durable, **no `Approval Result`, approval ledger, approval field or
approval relation is introduced.**

The content binding stays recoverable because Process and Review history cannot
change underneath a Requirement that has left `Review`. This was verified against
the frozen implementations rather than assumed: `Process` runs only when
`State = Process` and `Review` only when `State = Review`, and both refuse any
other state before touching anything.

```text
State = Ready     Process -> REQUIREMENT_NOT_IN_PROCESS   Review -> REQUIREMENT_NOT_IN_REVIEW
State = Apply     Process -> REQUIREMENT_NOT_IN_PROCESS   Review -> REQUIREMENT_NOT_IN_REVIEW
State = Applied   Process -> REQUIREMENT_NOT_IN_PROCESS   Review -> REQUIREMENT_NOT_IN_REVIEW
                  artifacts unchanged, zero model calls, zero mutations
```

So while a Requirement sits in `Ready` or `Apply`, no capability can add, alter
or remove a Process Result or a Review Result. What `Apply` will need is
therefore stable:

| Apply must know | Where it comes from |
|---|---|
| which content was approved | the Root Document, checked against `reviewed_document_fingerprint` |
| which Review Result was approved | the latest valid Review Result, which cannot have changed since approval |
| which confirmed relations belong to it | `confirmed_relation_proposals` inside that Review Result |
| whether anything changed after review | recompute the three bindings and compare |

The one path that could introduce a newer Review Result is a human moving
`Apply -> Review` by hand. That cannot silently return to `Apply`: `Review` ends
at `Ready`, so reaching `Apply` again requires another approval, which is this
command, which revalidates.

## 6. APPROVE preconditions

`Ready -> Apply` is permitted only when all of the following hold. They are
checked in order, and **no mutation occurs until every required precondition has
passed**.

```text
1.  the Requirement exists
2.  Type = Standard
3.  State = Ready
      (or State = Apply, handled as the idempotent case in section 15)
4.  the latest Review Result resolves unambiguously        (section 7)
5.  it parses and validates
6.  the latest applicable Process Result resolves unambiguously
7.  current canonical Root Document fingerprint
      == Review Result.reviewed_document_fingerprint
8.  current latest Process Result iteration
      == Review Result.reviewed_process_iteration
9.  that Process Result's output_fingerprint
      == Review Result.reviewed_process_output_fingerprint
9a. the Process Result and the Review Result are tree-bound (0.2) and the
      Review Result's reviewed_normative_tree is the Process Result's
      normative_output_tree; otherwise NORMATIVE_TREE_EVIDENCE_REQUIRED
9b. the current normative tree, traversed afresh, has the fingerprint of
      Review Result.reviewed_normative_tree
10. the verdict acknowledgement policy is satisfied         (section 9)
```

Checks 7-9b are the same four bindings the frozen Reviewer re-checks before
its own transition, applied here at approval time. Reusing them exactly is
deliberate: approval and review must mean the same thing by "the reviewed state",
or one of them is certifying something the other did not. Legacy Root-only
evidence proves nothing about the children, whether or not the Requirement has
any today, so it is refused rather than approved; REWORK stays available.

Fingerprints use the frozen `canonical_markdown` representation, so Fibery's
Markdown re-serialization never registers as a change.

If the reviewed-state bindings disagree:

```text
REVIEW_RESULT_STALE
```

with **no auto-review and no auto-process**. Ready Decision never repairs
anything.

## 7. Selecting the latest Review Result

Deterministic, and identical to the rules the frozen Reviewer already applies to
its own history:

```text
children of the Root Document named <Requirement ID> — Review Result NNNN
-> filter to this Requirement ID
-> two artifacts for one iteration           -> REVIEW_STATE_CONFLICT
-> the highest iteration is the latest
-> it must parse                             -> else INVALID_REVIEW_RESULT
-> unsupported version                       -> INVALID_REVIEW_RESULT
-> recorded iteration and Requirement ID must match its name
                                             -> else INVALID_REVIEW_RESULT
-> none found                                -> NO_REVIEW_RESULT
```

**An older Review Result is never used as a fallback when the newest is malformed
or stale.** The newest artifact is part of current history and cannot be silently
ignored; falling back would approve against a review the human was not shown and
that the system itself could not read.

The same rules apply to Process Result selection, so an ambiguous or malformed
Process history also fails explicitly rather than being guessed at, with the
codes the frozen Reviewer already uses for the same conditions:

```text
no Process Result for this Requirement       -> NO_PROCESS_RESULT
two Process Results for one iteration        -> INVALID_PROCESS_RESULT
latest Process Result does not parse         -> INVALID_PROCESS_RESULT
recorded iteration or Requirement ID mismatch -> INVALID_PROCESS_RESULT
```

These rules are normative. Whether the implementation shares code with the
Reviewer or restates it is an implementation decision; the rules may not diverge.

## 8. Process binding is re-read, never trusted

The Review Result carries `reviewed_process_iteration` and
`reviewed_process_output_fingerprint` as recorded copies. **Those copies are not
evidence about the present.** They describe what was true when the review ran.

APPROVE must therefore re-read current Process history from Fibery, resolve the
latest Process Result, parse it, and compare its actual iteration and actual
`output_fingerprint` against the Review Result's recorded values — together with
the recomputed Root Document fingerprint.

Trusting the copied fields would make the staleness check circular: the artifact
would be validating itself.

## 9. Human verdict authority and acknowledgement

The human remains the final authority. A Review verdict of `PASS`, `NEEDS_WORK`
or `BLOCKING` does not by itself forbid approval. Making Review able to refuse a
human would turn `Ready` into a quality gate, which the frozen Review
specification section 10 explicitly says it is not.

Approval at a non-`PASS` verdict instead requires an explicit acknowledgement
**naming the current derived verdict**:

```text
PASS         approve --requirement <id>
NEEDS_WORK   approve --requirement <id> --acknowledge-verdict NEEDS_WORK
BLOCKING     approve --requirement <id> --acknowledge-verdict BLOCKING
```

Missing acknowledgement for a non-`PASS` verdict:

```text
VERDICT_ACKNOWLEDGEMENT_REQUIRED
```

with zero mutation, and output that names the verdict and lists its blocking and
warning findings — so the refusal is itself the moment the human sees what they
were about to approve.

### The acknowledgement must match

There is deliberately no `--force`, `--override` or `--yes-really`. The
acknowledgement names the actual verdict, and a mismatch is refused:

```text
current verdict  = BLOCKING
acknowledgement  = NEEDS_WORK
-> VERDICT_ACKNOWLEDGEMENT_MISMATCH, zero mutation
```

This is the point of naming rather than forcing: an acknowledgement copied from
an older or better Review Result cannot silently approve a newer or worse one,
and the flag cannot become muscle memory.

The verdict used for the acknowledgement check **must come from the same latest
valid Review Result whose bindings were validated in section 6**. It is never
read from an older artifact and never recomputed from anything else.

### PASS

Acknowledgement is not required, and `PASS` workflows are not made verbose:

```text
PASS, no acknowledgement            -> valid
PASS, acknowledgement PASS          -> valid
PASS, acknowledgement NEEDS_WORK    -> INVALID_VERDICT_ACKNOWLEDGEMENT
PASS, acknowledgement BLOCKING      -> INVALID_VERDICT_ACKNOWLEDGEMENT
```

An acknowledgement that names something other than the current verdict is refused
whatever the current verdict is; the `PASS` row is that same rule, not a special
case.

### What is durable

Nothing about the acknowledgement is persisted, and nothing needs to be. The
permanent, readable record is already there: the Requirement reached `Apply`
while its latest Review Result records `BLOCKING`.

## 10. Stale review protection

Any mismatch in:

```text
current Root Document canonical fingerprint
current normative tree fingerprint (a child edited, added, removed, renamed
  or re-parented after the review)
current latest Process Result iteration
current latest Process Result output fingerprint
```

against the latest valid Review Result's recorded bindings returns:

```text
REVIEW_RESULT_STALE
```

and APPROVE then performs:

```text
state mutation     = 0
relation mutation  = 0
document mutation  = 0
model calls        = 0
```

Nothing is repaired automatically and no artifact is deleted. `REWORK` remains
available, because it certifies nothing (section 11).

## 11. REWORK semantics

```text
Ready -> Process
```

means: *a human has decided this needs another processing iteration before it can
be approved.* The transition performs no analysis and asserts nothing about the
content.

**REWORK intentionally does not require a valid or non-stale Review Result.** A
stale Requirement is itself a valid reason to send it back for work. This is a
deliberate asymmetry: only `APPROVE` validates bindings.

Required entry is only:

```text
Type  = Standard
State = Ready
```

Then the single transition, confirmed by reading the entity back. REWORK performs
zero model calls, zero Root Document writes, zero Process Result or Review Result
writes, zero `Revision` writes and zero relation writes. Previous artifacts remain
unchanged as the record of why rework was needed.

What happens next is already frozen behaviour: once the content is edited, the
Standard Processor sees a changed fingerprint and starts a new iteration; if
nothing was edited it returns `NO_CHANGES_TO_PROCESS` and stays in `Process`. Both
outcomes are correct. **Ready Decision does not solve editing.**

## 12. Editing order — not enforced

```text
Flow A   Ready -> REWORK -> human edits -> Standard Process
Flow B   Ready -> human edits -> REWORK -> Standard Process
```

Both are permitted. No artificial ordering is imposed between editing the Root
Document and recording the REWORK decision, unless implementation later finds a
concrete correctness requirement.

Fibery allows editing in any workflow state, and the Standard Processor's
canonical fingerprints already determine whether a real new processing input
exists. This capability only records the decision.

## 13. `Ready -> Review` — excluded

Unsupported in v0.1, resolving the question the Review specification section 18
left open. Every candidate scenario collapses:

- **unchanged input** — the frozen Reviewer returns `NO_CHANGES_TO_REVIEW`, so the
  transition achieves nothing;
- **edited input** — should pass through `Process` before independent review;
- **direct re-review** — would verify content that does not correspond to the
  Process Result the review binds itself to.

The single re-entry path is:

```text
Ready -> REWORK -> Process -> Review -> Ready
```

## 14. Mutation boundary

Permitted mutations, for the whole capability:

```text
APPROVE   set Requirement.State = Apply     then read the entity back, verify Apply
REWORK    set Requirement.State = Process   then read the entity back, verify Process
```

Only after the read-back confirms the new state is a successful decision
reported.

Explicitly forbidden on every path, including refusals and retries:

```text
model calls                     Root Document writes
Process Result writes           Review Result writes
Revision writes                 relation writes
writes to any other Requirement new Fibery Field, relation or Database
```

Read-back must also confirm `Revision` is unchanged, exactly as the frozen
capabilities do.

Because the only mutation is a single state write, **there is no partial state to
report**. If the write fails, nothing durable happened; if it succeeds but reads
back wrong, that is a validation failure with one state to inspect. No `PARTIAL_*`
result code is needed — a real simplification over the preceding capabilities
rather than an omission.

## 15. Idempotency

There is no artifact to resume from, so idempotency comes from the workflow state
itself. No ledger is introduced for it.

```text
APPROVE, State = Ready     validate (section 6), transition, read back
APPROVE, State = Apply     REQUIREMENT_ALREADY_APPROVED, zero mutations
APPROVE, any other state   REQUIREMENT_NOT_IN_READY, zero mutations

REWORK,  State = Ready     transition, read back
REWORK,  State = Process   REQUIREMENT_ALREADY_IN_REWORK, zero mutations
REWORK,  any other state   REQUIREMENT_NOT_IN_READY, zero mutations
```

Both already-done outcomes are **normal results**, not failures: a client that
lost the response gets the same answer on retry. Neither performs any further
mutation, neither moves an already-`Apply` Requirement anywhere else, and neither
invokes the `Apply` capability or the Standard Processor.

`REQUIREMENT_ALREADY_APPROVED` **must not be read as a statement that the current
document is still safe to apply.** It reports only that the transition already
happened. The result may report current binding status alongside it as
information for the human, but that is reporting, not certification — future
`Apply` still owns its own binding revalidation (section 18).

## 16. The boundary of using State as the decision signal

State-based idempotency identifies **that** a transition already happened. It
does not establish **why**, and it cannot distinguish a Requirement this
capability moved to `Apply` after full validation from one a human placed in
`Apply` directly in Fibery.

This is the accepted boundary of using workflow State as the durable decision
signal, and it is documented rather than engineered around: **no approval ledger
is introduced in v0.1 to resolve it.** The mitigation is structural rather than
recorded — `Apply` revalidates the reviewed bindings before any normative
mutation, so a Requirement that arrived in `Apply` by any route is still checked
before anything is applied.

## 17. Concurrency — the validate-then-write race

```text
validate reviewed bindings
-> state write
```

cannot currently be made compare-and-set transactional. Fibery records no
compare-and-set primitive, and constraint 16 establishes that `/api/commands`
batches are not transactional. This leaves a narrow window in which the Root
Document could change between the final validation and the state transition.

**No transaction or locking subsystem is designed.** The mitigation is:

1. Ready Decision validates immediately before the transition, never relying on
   previously displayed state;
2. it writes no normative relations or data — only the workflow state;
3. future `Apply` must revalidate the exact reviewed bindings before any
   normative mutation.

A race may therefore cause an obsolete approval state transition, which costs a
wasted transition and a subsequent refusal. **It cannot permit stale content to
be normatively applied.** Accepted as a v0.1 limitation unless new Fibery
primitives are discovered.

## 18. The invariant this capability places on future Apply

Recorded here only as the interface requirement Ready depends on. `Apply` is not
designed by this specification.

```text
Apply must not assume State = Apply alone is sufficient.
Before any normative mutation it must revalidate the reviewed bindings:

  current canonical Root Document fingerprint
    == latest valid Review Result.reviewed_document_fingerprint
  current latest Process Result iteration
    == ...reviewed_process_iteration
  that Process Result's output_fingerprint
    == ...reviewed_process_output_fingerprint
  current normative tree fingerprint
    == ...reviewed_normative_tree fingerprint
  both artifacts tree-bound and coherent, else NORMATIVE_TREE_EVIDENCE_REQUIRED
```

This invariant is what makes the state-only approval model sound (section 5) and
what contains both the manual-transition boundary (section 16) and the
validate-then-write race (section 17).

## 19. Artifacts remain evidence

Ready Decision must never modify a `Process Result NNNN` or a
`Review Result NNNN`. They are the record of what the processor produced and what
the independent reviewer concluded, and a decision stage that could edit its own
evidence would be worthless. This holds on the rework path too: rework does not
invalidate or delete history, it adds a further iteration ahead of it.

## 20. Confirmed relations stay unapplied

The latest Review Result may carry `confirmed_relation_proposals`. **Ready
Decision does not apply them, on either decision.** APPROVE changes state only;
REWORK does not modify or remove them either.

They remain pending normative changes until `Apply` is designed, which owns
actual relation application after repeating its own stale checks. This is what
keeps *human approval* separate from *deterministic application*: the human
authorises, a later step performs, and the two are separately auditable.

## 21. Revision

`Requirement.Revision` is never written. An approval or rework decision is not a
material Requirement revision. Read-back verifies it did not change.

## 22. Model runtime

```text
model calls = 0
```

No role is added to `config/sdlc.toml`. Human approval is deterministic, and any
future proposal to invoke a model here should be treated as evidence the boundary
has been misunderstood.

## 23. Human identity — not persisted

v0.1 does **not** record `approved_by`, `reviewed_by`, `human_id` or any
equivalent.

The current runtime exposes no trustworthy authenticated human identity.
`FIBERY_TOKEN` identifies a workspace token, not a person, and writing it — or
any supplied string — into an approval field would produce a record that looks
authoritative while being unverifiable. That is worse than no record, because
later work would trust it.

Fibery's workflow state and whatever change history it keeps provide the
currently available audit trail. Human identity may be added later, when it is
backed by a real identity source. No IAM or authority subsystem is introduced.

## 24. Human note — omitted

Neither decision accepts a persisted note in v0.1, and no note field, document or
Database is created.

The verdict acknowledgement (section 9) is the only correctness-sensitive human
annotation v0.1 requires, and it needs no storage. A free-text note would need an
artifact of its own, which section 5 rules out.

## 25. Result vocabulary

Following the existing `results.py` conventions, and keeping the Review quality
verdict strictly out of this capability's execution status.

Normal outcomes, exiting zero:

```text
REQUIREMENT_APPROVED
REQUIREMENT_SENT_FOR_REWORK
REQUIREMENT_ALREADY_APPROVED
REQUIREMENT_ALREADY_IN_REWORK
```

Validation and decision:

```text
REQUIREMENT_NOT_FOUND
NOT_A_STANDARD_REQUIREMENT
REQUIREMENT_NOT_IN_READY
NO_PROCESS_RESULT
INVALID_PROCESS_RESULT
NO_REVIEW_RESULT
INVALID_REVIEW_RESULT
REVIEW_STATE_CONFLICT
REVIEW_RESULT_STALE

VERDICT_ACKNOWLEDGEMENT_REQUIRED
VERDICT_ACKNOWLEDGEMENT_MISMATCH
INVALID_VERDICT_ACKNOWLEDGEMENT
```

Infrastructure:

```text
FIBERY_READ_FAILED
FIBERY_WRITE_FAILED
VALIDATION_FAILED
```

Two names follow established repository convention rather than the wording used
during approval, which explicitly permitted this. Recorded so the difference is
visible rather than silent:

```text
REQUIREMENT_NOT_READY     -> REQUIREMENT_NOT_IN_READY
                             matches REQUIREMENT_NOT_IN_PROCESS / _IN_REVIEW
REVIEW_RESULT_MISSING     -> NO_REVIEW_RESULT
                             matches the frozen NO_PROCESS_RESULT
```

`REVIEW_RESULT_STALE` and `REVIEW_STATE_CONFLICT` reuse the frozen Reviewer's
names because they are the same conditions detected by the same rules. A
`BLOCKING` verdict is never a failure code: it is a property of the Requirement,
reported in the payload.

## 26. Required tests

Deterministic, against the Fibery fake. The capability needs no model runtime;
tests still assert that none is invoked.

### Entry

```text
Standard + Ready accepted for both decisions
Raw rejected
every other State rejected (Draft, Process, Review, Applied)
rejected entry -> zero mutations, zero model calls
```

### APPROVE at PASS

```text
Ready + PASS, no acknowledgement    -> State = Apply
transition independently read back
Revision unchanged
```

### APPROVE at NEEDS_WORK

```text
no acknowledgement                  -> VERDICT_ACKNOWLEDGEMENT_REQUIRED, zero mutations
acknowledgement NEEDS_WORK          -> State = Apply
acknowledgement BLOCKING            -> VERDICT_ACKNOWLEDGEMENT_MISMATCH, zero mutations
```

### APPROVE at BLOCKING

```text
no acknowledgement                  -> VERDICT_ACKNOWLEDGEMENT_REQUIRED, zero mutations
acknowledgement BLOCKING            -> State = Apply
acknowledgement NEEDS_WORK          -> VERDICT_ACKNOWLEDGEMENT_MISMATCH, zero mutations
```

### Acknowledgement at PASS

```text
acknowledgement PASS                -> approved
acknowledgement NEEDS_WORK          -> INVALID_VERDICT_ACKNOWLEDGEMENT, zero mutations
acknowledgement BLOCKING            -> INVALID_VERDICT_ACKNOWLEDGEMENT, zero mutations
```

The acknowledged verdict must come from the latest validated Review Result: a
test must show an acknowledgement matching an *older* Review Result's verdict
being refused against a newer one.

### State and read-back

```text
a successful Apply write requires read-back to report Apply
a silently ignored write must not report approval -> VALIDATION_FAILED
the same for the REWORK transition
```

### Staleness

```text
Root Document fingerprint changed after review  -> REVIEW_RESULT_STALE
normative child changed after review            -> REVIEW_RESULT_STALE
latest Process iteration changed                -> REVIEW_RESULT_STALE
Process output fingerprint changed              -> REVIEW_RESULT_STALE
legacy 0.1 Process or Review Result             -> NORMATIVE_TREE_EVIDENCE_REQUIRED
foreign or misplaced artifact under the Root    -> NORMATIVE_TREE_INVALID
malformed latest Review Result                  -> INVALID_REVIEW_RESULT
unsupported Review Result version               -> INVALID_REVIEW_RESULT
duplicate Review Result iteration               -> REVIEW_STATE_CONFLICT
no Review Result at all                         -> NO_REVIEW_RESULT
an older valid Review Result is never used when the newest is unusable
every case -> no transition, zero mutations
```

A test must also show the Process binding being **re-read**, not taken from the
Review Result: a Process Result whose stored `output_fingerprint` was changed on
disk must be detected.

### REWORK

```text
Ready -> Process, read back
succeeds without any Review Result validation, including when bindings are stale
succeeds with a malformed or missing Review Result
zero model calls
Process Results and Review Results preserved byte for byte
Revision unchanged
relations untouched
```

### Idempotency

```text
APPROVE when already Apply     -> REQUIREMENT_ALREADY_APPROVED, zero mutations
REWORK  when already Process   -> REQUIREMENT_ALREADY_IN_REWORK, zero mutations
a failed state write           -> explicit failure, never a successful decision
```

### Hard immutability

Assert on the mutation log, not on final content equality — the guarantee is that
no write is attempted:

```text
zero Root Document writes
zero Process Result writes
zero Review Result writes
zero relation writes
zero Revision writes
zero writes to any other Requirement
```

on every path: PASS, NEEDS_WORK, BLOCKING, every refusal, stale, rework, and both
idempotent retries.

### Confirmed relations

```text
remain unapplied after APPROVE
remain unapplied after REWORK
```

## 27. Fibery fake fidelity

The standing project rule applies. Any new Fibery behaviour Ready Decision uses
must be represented in the fake, covered by deterministic tests, compared against
known or live behaviour, and exercised once live before freeze.

The behaviour needed is intentionally minimal and already used by the frozen
capabilities:

```text
Ready -> Apply state transition
Ready -> Process state transition
state read-back
Review Result and Process Result discovery and reading
```

Fake behaviour alone is never sufficient evidence for a new integration path.

## 28. Live acceptance before freeze

On a temporary Project, the frozen chain up to `Ready`:

```text
project init -> requirement add -> RAW Process -> Standard Process -> Standard Review
```

Then APPROVE, with a valid Review binding and the appropriate verdict
acknowledgement, verified independently in Fibery:

```text
same Requirement entity
State = Apply
Revision unchanged
Root Document unchanged
Process Results unchanged
Review Results unchanged
actual Depends On / Affects unchanged
model calls = 0
```

Separately, REWORK on a fresh temporary Requirement in `Ready`:

```text
State = Process
all history unchanged
no other mutation
```

And at least one stale-review refusal if safely practical — most cheaply, editing
the Root Document after review and confirming `REVIEW_RESULT_STALE` with no
transition.

Temporary identities only, and only those created by the acceptance run are
cleaned up.

## 29. Non-goals

```text
Apply implementation            relation application
Applied transition              Ready UI or dashboard
Requirement editing UX          revision / update / supersession
a Rejected state                approval ledger
approval artifact               human IAM or authority subsystem
Project Phases                  backlog
Epics                           Stories
Tasks                           GitHub integration
```

Ready Decision also performs no analysis, no normalization and no review.

## 30. Unresolved decisions

1. **Confirmed relations still have no consumer.** `Apply` remains undesigned, so
   an approved Requirement sits in `Apply` with its relations pending. Accepted,
   and explicitly not a reason to start `Apply`.
2. **No approval identity is recorded** (section 23). Acceptable for v0.1;
   becomes a real dependency only if audit identity is later required for
   correctness rather than convenience.
3. **No human note** (section 24). Revisit only if a later capability needs one.
4. **Manual transitions are indistinguishable from validated ones** (section 16).
   Accepted; contained by the Apply invariant in section 18.

No `DESIGN_BLOCKER`: nothing in section 29 turned out to be a prerequisite.
