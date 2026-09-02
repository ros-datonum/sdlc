# Standard Requirement Ready Decision Specification v0.1 — PROPOSED

**Status:** PROPOSED. Not approved. Nothing implements it.

Design pass for `Requirement.Type = Standard` + `Requirement.State = Ready`.

## 1. Lifecycle position

```text
Draft -> Process -> Review -> Ready -> Apply -> Applied
```

`Process` and `Review` are frozen. This capability performs the human decision
at `Ready`, and nothing else.

## 2. What Ready is

```text
Process   normalize + analyze + propose      model, writing
Review    independently verify + confirm     model, verifying
Ready     agent review complete; decision due HUMAN
Apply     human-approved application begins   deterministic
```

`Ready` is **not another autonomous stage**. It is the boundary where the system
stops deciding and a person does. This capability therefore invokes no model,
produces no analysis, and adds no judgement of its own. It records a decision
that has already been made by a human and validates that the decision is being
applied to the thing the human was shown.

Its entire job is one state transition plus the checks that make that transition
honest.

## 3. Entry condition

```text
Requirement.Type  = Standard
Requirement.State = Ready
```

Anything else is refused with zero Fibery mutations. Two states are additionally
accepted as **already-done** rather than errors, for idempotency (section 14):
`Apply` for approve, `Process` for rework.

## 4. The two decisions

```text
APPROVE   Ready -> Apply
REWORK    Ready -> Process
```

That is the whole vocabulary for v0.1. No `Rejected`, `Archived`, `Withdrawn` or
`Cancelled` state is introduced: a Requirement that should not exist is one the
human declines to approve, and disposing of it is outside this capability.

Proposed commands, following the existing one-verb-per-command convention:

```text
sdlc project requirement approve --requirement <entity id>
sdlc project requirement rework  --requirement <entity id>
```

## 5. No new durable artifact — the core finding

**`State = Apply` is sufficient durable evidence of human approval.** No Approval
Result Database, ledger, authority record, approval relation or Requirement Field
is introduced.

This is not an aesthetic preference; it rests on a structural property that was
verified against the frozen implementations rather than assumed. `Process` runs
only when `State = Process`, and `Review` runs only when `State = Review`. Both
refuse any other state before touching anything:

```text
State = Ready    Process -> REQUIREMENT_NOT_IN_PROCESS   Review -> REQUIREMENT_NOT_IN_REVIEW
State = Apply    Process -> REQUIREMENT_NOT_IN_PROCESS   Review -> REQUIREMENT_NOT_IN_REVIEW
                 artifacts unchanged, zero model calls, zero mutations
```

So while a Requirement sits in `Ready` or `Apply`, **its Process and Review
history is frozen**: no capability can add, alter or remove a Process Result or a
Review Result. Everything a future `Apply` needs is therefore already
recoverable and stable:

| Apply must know | Where it comes from |
|---|---|
| which content was approved | the Root Document, checked against the latest Review Result's `reviewed_document_fingerprint` |
| which Review Result was approved | the latest valid Review Result — which cannot have changed since approval |
| which confirmed relations belong to it | `confirmed_relation_proposals` inside that Review Result |
| whether anything changed after Review | recompute the three bindings and compare |

The one path that could introduce a newer Review Result is a human moving
`Apply -> Review` by hand. That path cannot silently reach `Apply` again: `Review`
ends at `Ready`, so returning to `Apply` requires another approval, which is this
command, which revalidates. A human who instead sets `Apply` directly in Fibery
has asserted the decision themselves, exactly as they could for any state.

### What state alone does not do

`State = Apply` records **that** a decision was made. It does not by itself prove
the content still matches what was reviewed, because a human can edit the Root
Document in Fibery at any time. That gap is closed by requiring `Apply` to
revalidate the same three bindings immediately before any normative mutation —
which `Apply` must do regardless. Approval and application therefore each check
the binding at the moment they act, and neither trusts the other's timing.

## 6. APPROVE preconditions

`Ready -> Apply` is permitted only when all of the following hold, checked in
this order, with no mutation until every one has passed:

```text
1. Requirement is Standard and in Ready
2. exactly one latest Review Result resolves (section 7)
3. that Review Result parses and its identity matches the Requirement
4. a latest Process Result resolves and parses
5. current Root Document canonical fingerprint
     == Review Result.reviewed_document_fingerprint
6. latest Process Result iteration
     == Review Result.reviewed_process_iteration
7. that Process Result's output_fingerprint
     == Review Result.reviewed_process_output_fingerprint
8. the verdict policy of section 8 is satisfied
```

Checks 5-7 are the same three bindings the frozen Reviewer re-checks before its
own transition, applied here at approval time. Reusing them exactly is
deliberate: approval and review must agree on what "the reviewed state" means, or
one of them is certifying something the other did not.

Fingerprints use the frozen `canonical_markdown` representation, so Fibery's
Markdown re-serialization never registers as a change.

If any of 2-7 fails:

```text
no transition
no relation mutation
no document mutation
no automatic re-review
```

The human is told exactly which binding moved, and recovers through `REWORK`
plus a fresh Process/Review pass. **Ready never re-reviews anything.**

## 7. Selecting the latest Review Result

Deterministic, and identical to the rules the frozen Reviewer already applies to
its own history:

```text
children of the Root Document named <Requirement ID> — Review Result NNNN
-> filter to this Requirement ID
-> two artifacts for one iteration        -> REVIEW_STATE_CONFLICT
-> the highest iteration is the latest
-> it must parse, and its recorded iteration and Requirement ID must match its name
```

**A malformed or stale latest Review Result is never bypassed in favour of an
older one.** Falling back would approve against a review the human was not shown
and that the system itself could not read. If the newest artifact is unusable the
command fails and says so.

The same rules apply to Process Result selection, so an ambiguous or malformed
Process history also fails explicitly rather than being guessed at.

These rules are normative. Whether the implementation shares code with the
Reviewer or restates it is an implementation decision; the rules may not diverge.

## 8. Verdict versus human authority — decision required

Review produces `PASS`, `NEEDS_WORK` or `BLOCKING`, and all three reach `Ready`.
The frozen Review specification section 10 already settles the principle:

> A Requirement that Review believes is duplicated, non-atomic, contradictory or
> simply should not exist therefore reaches `Ready` carrying a `BLOCKING` verdict
> and the findings that justify it. The human decides.

**Option C — BLOCKING cannot be approved — is therefore rejected**, not on
preference but because it contradicts frozen semantics. It would make Review
authoritative and `Ready` a quality gate, which the frozen spec explicitly says
it is not.

That leaves the real choice:

**Option A — the human is final authority, no ceremony.** `APPROVE` succeeds at
any verdict. Smallest possible, and fully preserves authority. Its weakness is
the failure mode the review stage exists to prevent: an approval issued without
the verdict ever being surfaced — from a script, from habit, or from a mental
model formed before the review ran — silently discards everything Review found.

**Option B — approval at a non-PASS verdict requires naming the verdict.
RECOMMENDED.**

```text
PASS                    approve --requirement <id>
NEEDS_WORK / BLOCKING   approve --requirement <id> --acknowledge-verdict BLOCKING
```

The flag takes the verdict value rather than being a bare `--force`, and the
command refuses if the named verdict is not the current derived verdict. So the
acknowledgement cannot be muscle memory, cannot be pasted from an older run, and
fails loudly if the verdict changed since the human last looked. Without it, the
command refuses **and prints the verdict with its blocking and warning findings**
— so the refusal is itself the moment the human sees what they were about to
approve.

Option B costs no artifact, no field, no state and no persistence: it is purely a
guard at the decision moment. Authority remains entirely with the human, because
the override always succeeds once given. The durable audit record needs nothing
extra either — "the Requirement reached `Apply` while its latest Review Result
records `BLOCKING`" is already a permanent, readable fact.

This section is the one genuine judgement call in the design and needs explicit
approval.

## 9. Human visibility

No separate `ready status` command and no dashboard in v0.1.

Under Option B the information reaches the human at exactly the moment it
matters: a non-PASS approval attempt without acknowledgement refuses and prints
what is being approved. To make that useful without a second command, every
result of this capability — success, refusal or staleness — reports:

```text
Requirement ID and Title
current content identity (whether it still matches the reviewed state)
latest Review Result iteration
derived verdict
blocking findings
warning findings
UNRESOLVED Process finding verifications
confirmed relation proposals (and that none of them are written)
```

The full Review Result also remains readable in Fibery as a child Document. A
read-only status view is a plausible later convenience, not a v0.1 requirement.

## 10. REWORK semantics

```text
Ready -> Process
```

means: *a human has decided this needs another processing iteration before it can
be approved.* The transition performs no analysis and asserts nothing about the
content.

**REWORK requires no binding validation at all.** Nothing is being certified, so
staleness is irrelevant — a stale Requirement is precisely one that ought to go
back. This is a deliberate asymmetry: only `APPROVE` validates bindings.

REWORK must not invoke a model, rewrite the Root Document, delete or alter any
Process Result or Review Result, mutate any relation, or change `Revision`.
Previous artifacts remain immutable history and are the record of why rework was
needed.

What happens next is already frozen behaviour: once the content is edited, the
Standard Processor sees a changed fingerprint and starts a new iteration; if
nothing was edited it returns `NO_CHANGES_TO_PROCESS` and stays in `Process`.
Both outcomes are correct and need nothing from this capability.

## 11. Editing order — not enforced

```text
Flow A   Ready -> REWORK -> human edits -> Standard Process
Flow B   Ready -> human edits -> REWORK -> Standard Process
```

Both are permitted. Fibery allows editing in any workflow state, and the Standard
Processor already detects real content change by fingerprint rather than by
workflow position, so enforcing an order would add a rule that buys no
correctness. Flow A is the suggested convention because it makes the intent
visible in the workflow state first, but nothing depends on it.

## 12. `Ready -> Review` — omitted

Deliberately not defined, resolving the question the Review specification
section 18 left open. Every candidate scenario collapses:

- **content unchanged, re-run the reviewer** — the frozen Reviewer returns
  `NO_CHANGES_TO_REVIEW` and does nothing, so the transition achieves nothing;
- **content changed by hand** — it should go through `Process` first, or Review
  would verify content that was never normalized and the `Process` binding it
  records would describe an iteration that did not produce the document;
- **a better reviewer prompt or model** — still blocked by
  `NO_CHANGES_TO_REVIEW`, so this transition would not deliver it either.

`REWORK` is the single re-entry path, and it routes through `Process` where
normalization belongs. A transition is not added merely to have it.

## 13. Mutation boundary

Permitted mutations, for the whole capability:

```text
APPROVE   set Requirement.State = Apply     then read the entity back
REWORK    set Requirement.State = Process   then read the entity back
```

That is all. Explicitly forbidden on every path, including refusals and retries:

```text
Root Document write             Process Result write
Review Result write             Revision write
relation write (Depends On / Blocks / Affects / Impacted By)
any mutation of any other Requirement
any model invocation
any new Fibery Field, relation or Database
```

Read-back must confirm the new state, and must confirm `Revision` is unchanged,
exactly as the frozen capabilities do.

Because the only mutation is a single state write, **there is no partial state to
report**. If the write fails, nothing durable happened; if it succeeds but reads
back wrong, that is a validation failure with one state to inspect. No
`PARTIAL_*` result code is needed, which is a real simplification over the
preceding capabilities rather than an omission.

## 14. Idempotency and retry

There is no artifact to resume from, so idempotency is derived from the workflow
state itself. No ledger is introduced for it.

```text
APPROVE, State = Ready    validate, transition, read back
APPROVE, State = Apply    REQUIREMENT_ALREADY_APPROVED, zero mutations
APPROVE, any other state  REQUIREMENT_NOT_IN_READY, zero mutations

REWORK,  State = Ready    transition, read back
REWORK,  State = Process  REQUIREMENT_ALREADY_IN_REWORK, zero mutations
REWORK,  any other state  REQUIREMENT_NOT_IN_READY, zero mutations
```

The already-done outcomes are normal results, not failures: a client that lost
the response gets the same answer on retry. They report the current verdict and
binding status informationally (section 9) so a human is not misled about what
the Requirement now contains, but they perform no validation gate of their own —
validating on behalf of `Apply` is not this command's job.

A failed transition or a read-back that disagrees must never be reported as a
successful decision.

## 15. Concurrency

```text
human reads status -> content changes -> human runs approve
```

The command must re-read and revalidate everything at execution time and must
never rely on previously displayed state. Section 6 already requires this.

A narrow window remains between the final validation and the state write. Fibery
records no compare-and-set primitive, and constraint 16 establishes that
`/api/commands` batches are not transactional, so the window cannot be closed
with what the API offers.

It does not need to be. The only consequence is a Requirement entering `Apply`
whose content moved microseconds later, and `Apply` revalidates the same bindings
before any normative mutation (section 5), where it will refuse. The race can
therefore cost a wasted transition; it cannot cause an unreviewed change to be
applied. **Documented and accepted; no transaction subsystem is designed.**

## 16. Artifacts remain evidence

Ready Decision must never modify a `Process Result NNNN` or a
`Review Result NNNN`. They are the record of what the processor produced and what
the independent reviewer concluded, and a decision stage that could edit its own
evidence would be worthless. This holds on the rework path too: rework does not
invalidate or delete history, it adds a further iteration ahead of it.

## 17. Confirmed relations stay unapplied

The latest Review Result may carry `confirmed_relation_proposals`. **Ready
Decision does not apply them, on either decision.** `APPROVE` changes state only.
They remain pending normative changes until `Apply` is designed, exactly as the
frozen Review specification section 9 requires.

This is what keeps *human approval* separate from *deterministic application*:
the human authorises, and a later step performs, and the two are separately
auditable.

## 18. Revision

`Requirement.Revision` is never written. Material revision semantics are outside
this capability, and read-back verifies it did not change.

## 19. Model runtime

```text
model calls = 0
```

No role is added to `config/sdlc.toml`. A human decision needs no model, and any
future proposal to invoke one here should be treated as evidence the boundary has
been misunderstood.

## 20. Human identity — not persisted

v0.1 does **not** record who approved.

The CLI has no authenticated human identity to record. `FIBERY_TOKEN` identifies
a workspace token, not a person, and writing it — or any supplied string — into
an `approved_by` field would produce a record that looks authoritative while
being unverified. That is worse than no record, because later work would trust
it.

The durable facts are the workflow state and whatever change history Fibery keeps
of its own accord; this specification makes no claim about the latter and does
not depend on it. No IAM, authority subsystem or approval ledger is introduced.

If verified approval identity is later required for correctness rather than
convenience, that is a real dependency to be designed deliberately — not
approximated now.

## 21. Human note — omitted

Neither decision accepts a persisted note in v0.1.

A note has no home: there is no Requirement Field for it, and creating an
artifact solely to hold one contradicts section 5. Under Option B the override is
already deliberate and the reasoning is reconstructible from the Review Result
plus the state, so a note is not required by the approval semantics. Left out
until something needs it.

## 22. Result vocabulary

Following the existing `results.py` conventions, and keeping the human's quality
verdict strictly out of the processor's execution status:

```text
REQUIREMENT_APPROVED               Ready -> Apply, decision recorded
REQUIREMENT_SENT_FOR_REWORK        Ready -> Process
REQUIREMENT_ALREADY_APPROVED       already in Apply; nothing changed
REQUIREMENT_ALREADY_IN_REWORK      already in Process; nothing changed

REQUIREMENT_NOT_FOUND
NOT_A_STANDARD_REQUIREMENT
REQUIREMENT_NOT_IN_READY
NO_PROCESS_RESULT
INVALID_PROCESS_RESULT
NO_REVIEW_RESULT
INVALID_REVIEW_RESULT
REVIEW_STATE_CONFLICT
REVIEW_RESULT_STALE                content or Process binding moved since review
VERDICT_NOT_ACKNOWLEDGED           non-PASS verdict, no matching acknowledgement
FIBERY_READ_FAILED
FIBERY_WRITE_FAILED
VALIDATION_FAILED                  transition did not read back as expected
```

Normal outcomes, exiting zero:

```text
REQUIREMENT_APPROVED
REQUIREMENT_SENT_FOR_REWORK
REQUIREMENT_ALREADY_APPROVED
REQUIREMENT_ALREADY_IN_REWORK
```

`REVIEW_RESULT_STALE` reuses the frozen Reviewer's name because it is the same
condition detected by the same three bindings. A `BLOCKING` verdict is not a
failure code: it is a property of the Requirement, reported in the payload.

## 23. Required tests

Deterministic, against the Fibery fake. No model runtime is needed by the
capability; tests still assert that none is invoked.

### Entry

```text
Standard + Ready accepted for both decisions
Raw rejected
every other State rejected (Draft, Process, Review, Applied)
rejected entry -> zero mutations, zero model calls
```

### APPROVE

```text
valid latest Review Result -> State = Apply
transition independently read back
Revision unchanged
zero model calls
no write to the Root Document, any Process Result, or any Review Result
no relation mutation on any path
no other Requirement mutated
```

### Verdict policy (section 8)

```text
PASS                        -> approved without acknowledgement
NEEDS_WORK, no flag         -> VERDICT_NOT_ACKNOWLEDGED, zero mutations
BLOCKING,   no flag         -> VERDICT_NOT_ACKNOWLEDGED, zero mutations
NEEDS_WORK / BLOCKING + matching acknowledgement -> approved
acknowledgement naming the wrong verdict          -> refused
acknowledgement supplied when the verdict is PASS -> refused as unnecessary
the refusal output names the verdict and its blocking findings
```

### Stale review

```text
Root Document changed after review        -> REVIEW_RESULT_STALE
latest Process iteration changed          -> REVIEW_RESULT_STALE
Process output fingerprint changed        -> REVIEW_RESULT_STALE
malformed latest Review Result            -> INVALID_REVIEW_RESULT
duplicate Review Result iteration         -> REVIEW_STATE_CONFLICT
no Review Result at all                   -> NO_REVIEW_RESULT
an older valid Review Result is never used when the newest is unusable
every stale or invalid case -> no transition, zero mutations
```

### REWORK

```text
Ready -> Process, read back
succeeds without any binding validation, including when content is stale
zero model calls
Process Results and Review Results preserved byte for byte
Revision unchanged
relations untouched
```

### Idempotency

```text
APPROVE when already Apply    -> REQUIREMENT_ALREADY_APPROVED, zero mutations
REWORK when already Process   -> REQUIREMENT_ALREADY_IN_REWORK, zero mutations
failed state write            -> explicit failure, never a successful decision
read-back disagreeing with the write -> VALIDATION_FAILED
```

### Immutability and relations

```text
no write issued to the Root Document on any path, asserted on the mutation log
no write issued to any Process Result or Review Result
confirmed relation proposals remain unapplied after APPROVE
confirmed relation proposals remain unapplied after REWORK
```

Mutation-log assertions are required rather than final-content comparison: the
guarantee is that no write is attempted, not merely that content happens to match.

## 24. Fibery fake fidelity

The standing project rule applies. Ready Decision introduces no new Fibery
operation — state transition, state read-back, and child Document discovery and
reading are all already used and live-verified by the frozen capabilities. For
any behaviour that nevertheless turns out to be new:

1. verify the real behaviour;
2. reproduce it faithfully in the fake;
3. add deterministic regression coverage;
4. run one narrow live acceptance before freeze.

Fake behaviour alone is never sufficient evidence for a new integration path.

## 25. Live acceptance before freeze

On a temporary Project, the full chain:

```text
project init -> requirement add -> RAW Process -> Standard Process
             -> Standard Review -> Ready Decision
```

Verify APPROVE independently in Fibery:

```text
State = Apply
Revision unchanged
Root Document unchanged
Process Result unchanged
Review Result unchanged
actual Depends On / Affects unchanged
model calls = 0
```

Then verify one REWORK path on a second Requirement:

```text
State = Process
all history intact
no other mutation
```

And at least one refusal path — most cheaply, editing the Root Document after
review and confirming `REVIEW_RESULT_STALE` with no transition.

Temporary identities only, and only those created by the acceptance run are
cleaned up.

## 26. Non-goals

```text
Apply implementation            relation application
Applied transition              Ready UI or dashboard
Requirement editing UX          revision / update / supersession
a Rejected state                human IAM or authority subsystem
approval ledger                 Project Phases
backlog                         Epics
Stories                         Tasks
GitHub integration              multi-model consensus
```

Ready Decision also performs no analysis, no normalization and no review.

## 27. Unresolved decisions

1. **The verdict policy (section 8) needs an explicit choice.** Option B is
   recommended; Option A is defensible and smaller; Option C is ruled out by
   frozen semantics. Everything else in this specification is unaffected by the
   choice except the `VERDICT_NOT_ACKNOWLEDGED` result and its tests.
2. **Confirmed relations still have no consumer.** `Apply` remains undesigned, so
   an approved Requirement sits in `Apply` with its relations pending. Accepted,
   and explicitly not a reason to start `Apply`.
3. **No approval identity is recorded** (section 20). Acceptable for v0.1;
   becomes a real dependency only if audit identity is later required for
   correctness.
4. **No human note** (section 21). Revisit only if a chosen verdict policy or a
   later capability needs one.

No `DESIGN_BLOCKER`: nothing in section 26 turned out to be a prerequisite.
