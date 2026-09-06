# Standard Requirement Process Specification v0.1

**Status:** Approved contract. Not yet implemented.

Defines `Requirement.Type = Standard` + `Requirement.State = Process`.

## 1. Lifecycle position

```text
Draft -> Process -> Review -> Ready -> Apply -> Applied
```

A Standard Requirement reaches `Draft` from the RAW Requirement Processor. This
capability performs `Process -> Review`.

## 2. Stage boundary

| Stage | Meaning |
|---|---|
| `Draft` | the candidate as produced by decomposition |
| `Process` | normalize + analyze + propose |
| `Review` | independently verify and confirm findings/relations |
| `Ready` | agent review complete; awaiting a human decision |
| `Apply` | the human-approved application step begins |
| `Applied` | successfully applied |

`Ready` does **not** mean already human-approved. It means independent agent
review is finished and the Requirement is ready for a human to decide, either

```text
Ready -> Apply
```

or return it for further work.

The rule the separation rests on:

> The action that rewrites a Requirement must not be the action that certifies
> it.

`Process` normalizes and proposes. `Review` verifies and confirms. Neither
`Review` nor `Apply` is designed here.

## 3. Responsibility

`Process` takes a Standard Requirement candidate and:

- normalizes it;
- improves clarity;
- checks completeness;
- checks atomicity;
- checks internal consistency;
- checks testability;
- identifies missing constraints and edge cases;
- analyzes relevant existing Standard Requirements;
- proposes dependency and change-impact relations.

It does **not** certify the Requirement. On successful execution it transitions

```text
Process -> Review
```

**regardless of whether the analysis produced findings.** A Requirement whose
analysis is unflattering still moves to `Review` carrying that analysis; the
independent Review stage decides whether it is acceptable.

## 4. Entry condition

```text
Requirement.Type  = Standard
Requirement.State = Process
```

Anything else is refused with zero model calls and zero Fibery mutations.

## 5. Input context

Bounded:

```text
the Requirement entity (Requirement ID, Title, Category, Revision, Project)
its Root Document
its child Documents, recursively, excluding this capability's own artifacts
the Project
the RAW Requirement it derives from, and that RAW's Root Document
existing Standard Requirements in the Project: ID, Title, requirement text
```

The originating RAW is included so Process can distinguish "the source never
said this" from "decomposition dropped it".

No Milestones, Epics, Stories, Tasks, or unrelated project state.

## 6. Model boundary

Reuses the frozen `ModelRuntime` / `LocalCliModelRuntime` and `config/sdlc.toml`
with the role:

```text
standard_requirement_processor
```

No change to authentication or routing. The model returns structured data only:
it never writes to Fibery, never chooses an identifier, and is never asked for
reasoning traces. Unknown fields are rejected, as in the RAW contract.

Output shape:

```text
normalized_requirement:
  title
  requirement
  detailed_behavior
  rationale
  acceptance_verification
  constraints_edge_cases
  non_goals
  open_questions

analysis:
  completeness
  clarity
  atomicity
  testability
  internal_consistency

proposed_relations:
  - kind: DEPENDS_ON | BLOCKS | AFFECTS | IMPACTED_BY
    requirement_id
    rationale

findings:
  - kind: POSSIBLE_DUPLICATE | POSSIBLE_CONFLICT | POSSIBLE_CHANGE
          | POSSIBLE_SUPERSESSION | NON_ATOMIC
    requirement_id      (omitted for NON_ATOMIC)
    detail
```

`normalized_requirement` reuses the sections of
`Standard-Requirement-Document-Schema-v0.1` exactly, so the document is still
rendered deterministically by code.

## 7. Permitted Fibery mutations

Process may:

1. create one **Process Result** child Document for the current iteration;
2. rewrite the Requirement's Root Document from that persisted result;
3. set `Requirement.State = Review`.

Process may **not**:

- create, split or delete Requirement entities;
- write `Depends On` / `Blocks` / `Affects` / `Impacted By`;
- modify any other Requirement, in any state;
- change `Requirement ID`, `Type`, `Category`, `Project`;
- change `Revision` (section 10);
- delete or overwrite an earlier Process Result;
- add Fibery Fields, relations or Databases.

## 8. Process Result iterations

Standard Requirements support multiple explicit processing iterations. Each is a
child Document of the Root Document, named:

```text
<Requirement ID> — Process Result 0001
<Requirement ID> — Process Result 0002
...
```

Iteration numbers are monotonic, zero padded to four digits, and never reused.
Earlier Process Results are **process history** and are never deleted or
overwritten during normal operation.

Each contains at minimum:

```text
process_result_version
iteration
input_fingerprint      the Root Document content this iteration consumed
output_fingerprint     the Root Document content this iteration produced
analysis / findings
normalized Requirement content
proposed relations
```

No chain-of-thought. Serialization is JSON inside the child Document, as with
the RAW Processing Result.

The persisted result must be sufficient to reproduce the normalized Root
Document **without another model call**.

Fingerprints use the normalization already frozen for content comparison, so
Fibery's Markdown re-serialization does not register as a change.

## 9. Same-iteration retry

The Root Document fingerprint decides what a run does. Three cases, and the
input fingerprint is what separates the second from the third:

```text
current == latest.input_fingerprint
  the normalized rewrite never landed
  -> resume that iteration, without the model

current == latest.output_fingerprint
  the normalized output is already applied
  -> NO_CHANGES_TO_PROCESS, zero mutations, State stays Process

current differs from both
  the content genuinely changed
  -> a new iteration
```

Resuming an unfinished application invokes no model: the persisted result is
read, the Root Document rewritten, validated, and the transition performed.
Rewriting from a persisted result is naturally idempotent, and the canonical
comparison accepts the re-serialized read-back.

Fingerprints are taken over the same canonical representation that
`content_equivalent` compares, so the two agree by construction. A fingerprint
computed any other way would let Fibery's Markdown re-serialization look like an
edit and force a spurious iteration.

## 10. New processing iteration

A new model invocation is allowed only when the Requirement has been
intentionally returned to `State = Process` **and** its current Root Document
content differs from the `output_fingerprint` of the latest successfully applied
Process Result:

```text
latest = Process Result 0001
current Root Document changed
-> create Process Result 0002
-> invoke the model once
-> persist, verify, apply deterministically
```

The Requirement's `Revision` is **not** incremented. Process iteration number
and Requirement material revision are separate concepts; the material revision
model is undesigned and out of scope.

## 11. No-change reprocessing

If the Requirement is in `Process` but

```text
current Root Document fingerprint == latest Process Result.output_fingerprint
```

the result is:

```text
NO_CHANGES_TO_PROCESS
```

with **zero mutations**: no model call, no Process Result, no document rewrite,
no relation write, and **no state change**. The Requirement stays in `Process`.

This stops status toggling from causing uncontrolled model drift, and it leaves
the workflow state the operator chose.

### The ambiguity this deliberately does not resolve

Two histories produce exactly this snapshot:

```text
A  the run applied its output but failed to reach Review
B  the run completed, and someone later returned Review -> Process unedited
```

Persisted state cannot tell them apart, and v0.1 adds no field, relation,
marker or ledger to make it distinguishable. The processor therefore does not
guess: it preserves the current workflow state rather than inferring historical
intent, so a deliberate `Review -> Process` is never silently undone.

The consequence for history A is accepted: a later invocation returns
`NO_CHANGES_TO_PROCESS` and the Requirement stays in `Process`. That failure was
reported explicitly at the time it happened (section 14), and recovery is
manual — an operator moves it to `Review`, or edits it and processes again.
There is no automatic repair.

Producing a genuinely new iteration therefore requires the Draft to change
through an allowed human or future editing path. That editing capability is not
designed here; this spec only defines how Process *detects* a new input.

## 12. Relations — proposed, not written

Process does **not** write `Depends On` / `Blocks` / `Affects` / `Impacted By`.
Writing them would let Process certify its own inferences into canonical
structure, which section 2 forbids. Proposals live in the Process Result, keyed
by Requirement ID — no proposal Database and no new Field.

Independent Review verifies those proposals and confirms or rejects them; it
writes no relations either. Actual relation mutation is deferred to the future
`Apply` capability, after human approval, because a relation is normative shared
state and `Ready` has not yet received that approval. When `Apply` is designed
its writes must be **additive** (`fibery.entity/add-collection-items`), must not
destructively replace existing valid relations merely because a later iteration
stopped proposing them, and must not duplicate an edge on re-application.

Corrected for consistency with `Standard-Requirement-Review-Spec-v0.1` section 9.
This is a cross-spec consistency correction, not a change to Process behaviour:
Process still writes no relations, and no Process implementation code changes.

Each pair shares one Fibery relation id, so writing one side populates the
inverse:

```text
Depends On   <-> Blocks         a0353ff0-...
Affects      <-> Impacted By    ba1ae370-...
Derived From <-> Produces       8002c1d0-...   (written by the RAW Processor)
```

## 13. Findings about existing Requirements

These remain informational:

```text
POSSIBLE_DUPLICATE
POSSIBLE_CONFLICT
POSSIBLE_CHANGE
POSSIBLE_SUPERSESSION
NON_ATOMIC
```

Process records them with evidence and never mutates the referenced Requirement,
its Documents, or its State. Revision, update, retirement and supersession
semantics are not designed here.

A Requirement that should not exist is represented as a blocking
finding/recommendation. No `Rejected` state is added to the workflow; a human
resolves it at `Ready` or through a later workflow decision.

### Atomicity

A non-atomic Requirement produces a `NON_ATOMIC` finding only. Process does not
split it or create additional Requirement entities, so no identity or
`Derived From` fan-out semantics are introduced.

## 14. Ordering and idempotency

```text
model runs once
-> validated structured result
-> Process Result persisted and re-read as valid   <- before any mutation
-> Root Document rewritten from the persisted result
-> post-write validation with the canonical comparison
-> State -> Review, confirmed by reading the entity back
```

The invariant:

```text
the Root Document was rewritten  =>  a valid Process Result already exists
```

Failure **after** the Process Result is persisted: the Requirement stays in
`Process`, the Process Result and any partial writes remain, and a retry resumes
deterministically without invoking the model — except where the only remaining
step was the transition, which section 11 leaves to an operator. A run that
fails to reach `Review` reports that explicitly and never claims success.

Failure **before** it is persisted: no durable normalized output exists, so a
retry may invoke the model again.

Duplicate Process Results for the same iteration are never guessed between:

```text
PROCESSING_STATE_CONFLICT
```

### Within-run write preconditions

Clarification, added after the source audit found a run overwriting a Root
Document edited while its model call was in flight. The run captures its input
once, at the start; every normative write is preceded by a **fresh read** of
the target and refused unless that read still matches the captured input:

```text
immediately before persisting the Process Result
immediately before rewriting the Root Document   (new and resumed iterations)
immediately before Process -> Review             (Root must hold the applied output)
```

Protected by the comparison: the entity itself, its Requirement ID, Title,
Project, Revision and public id; Type `Standard`; State `Process`; exactly one
attached Root Document with the same identity, content secret and Folder; and
Root content canonically equivalent to the captured input (or, before the
transition, to the output just applied). A Folder change is a conflict, never
adopted as permission to write elsewhere.

Any drift is `PROCESSING_STATE_CONFLICT`: the stale model output is not
persisted, no Root is rewritten, no State is written, nothing already durable
is rolled back, and the change made outside the run stands. A conflict found
after the Process Result was persisted reports that result's identity in
`created` and makes no claim that the Requirement "remains in Process" or that
a retry will resume. A failed fresh read fails the write it guards. A conflict
discovered after the model ran reports the model as invoked.

These are fresh reads within one invocation, not a compare-and-set
transaction: a change that lands between a guard's read and the write it
protects is not detected. The cross-run `current == latest.input_fingerprint`
resume rule of section 9 is unchanged.

### Empty Result Documents

A Result is created as a child Document before its body is written. If the
body write fails after the create returned, the empty Document remains; the
run reports it as *created*, never *persisted*, with its id. It is not a
Result: an ordinary retry refuses it by id, invokes no model and writes
nothing. It may be completed in place only when named explicitly through
`--recover-empty-result <document id>`, which runs the model again on the
current input, writes into the same Document under its reserved name and
iteration after fresh reads, taken immediately before the write, prove the
Requirement is still in this stage's Type and State with the same attached
Root Document and the shell is still the single, still-empty shell under it,
and reads the body back through the strict parser before any downstream
step. A change visible at that check is refused; a change that lands between
the check and the write is outside any atomic guarantee. Recovery refuses any
non-empty body, any Document that is not this Requirement's terminal
unfinished Result, and any evidence that the iteration was already consumed
downstream. Explicit selection is not multi-writer safety.

## 15. Process -> Review transition

`State = Review` only when all of:

```text
Process Result persisted and re-read as valid
Root Document rewritten and verified by canonical read-back
proposals and findings recorded
```

The transition is confirmed by reading the entity back. It is not conditional on
the Requirement being judged good.

## 16. Failure states

```text
REQUIREMENT_NOT_FOUND
NOT_A_STANDARD_REQUIREMENT
REQUIREMENT_NOT_IN_PROCESS
NO_CHANGES_TO_PROCESS
PROCESSING_STATE_CONFLICT
INVALID_PROCESS_RESULT
MODEL_RUNTIME_FAILED
INVALID_MODEL_OUTPUT
PROCESS_RESULT_WRITE_FAILED
CONTENT_WRITE_FAILED
FIBERY_READ_FAILED
FIBERY_WRITE_FAILED
VALIDATION_FAILED
PARTIAL_PROCESSING
```

Durable state is always reported and never silently deleted.

## 17. Non-goals

This capability does not implement:

- the Review agent;
- `Ready` behaviour;
- `Apply` / `Applied`;
- Applied Requirement revision, update, retirement or supersession;
- Requirement splitting;
- Project Phase planning;
- backlog generation;
- Epic, User Story or Task creation;
- GitHub workflow;
- automatic status-triggered orchestration.

## 18. Required tests

Deterministic, with a fake model runtime:

```text
entry: only Standard + Process; anything else refused with no model call
context: RAW ancestry and child Documents assembled; own artifacts excluded
model output: unknown fields, bad relation kinds, bad finding kinds rejected
Process Result written before any document mutation
  none exists                  -> model runs
  current iteration incomplete -> model must NOT run, application resumes
  duplicate for one iteration  -> PROCESSING_STATE_CONFLICT
  malformed / wrong version    -> explicit failure, no model call
iteration numbering is monotonic; earlier results are never modified
unchanged Root Document on re-entry -> NO_CHANGES_TO_PROCESS, no new result
changed Root Document on re-entry   -> new iteration, one model call
input_fingerprint / output_fingerprint recorded and used as specified
document rewritten from the persisted result, verified canonically
proposed relations are NOT written to Fibery
findings do not mutate the referenced Requirement
NON_ATOMIC produces a finding and creates no Requirement
Revision is never changed
partial failure leaves State = Process with durable state intact
retry resumes without a model call and without drift
State -> Review only on complete success, confirmed by read-back
```

## 19. Fibery fake fidelity and live acceptance

A standing project engineering rule for Fibery integrations, adopted because
fake fidelity has already hidden two real defects:

1. for every new Fibery read/write behaviour a capability introduces, the
   fake/test double must reflect the verified Fibery behaviour relevant to
   correctness — including Markdown re-serialization on read-back;
2. before freeze, run one narrow live acceptance covering the new write path;
3. if live behaviour differs from the fake, fix the fake and add regression
   coverage **before** freeze.

For this capability the new write paths are: creating an iterated Process Result
child Document, and rewriting an existing Root Document in place.

### Live acceptance before freeze

On a temporary Project: create a RAW, process it, take one produced Standard
Draft to `Process`, run this capability, then verify independently in Fibery
that the Root Document was rewritten, exactly one Process Result exists for the
iteration, no relations were written, no other Requirement changed, `Revision`
is unchanged, and `State` is `Review`. Then re-enter `Process` without editing
and confirm `NO_CHANGES_TO_PROCESS` with no new Process Result.

## 20. Schema drift resolved

The workspace previously carried a `Requirement.Operation` Field with values
`CREATE`, `UPDATE`, `RETIRE`, `SUPERSEDE`, which is not part of the approved
Fibery schema and which `RAW-Requirement-Processor-Decision-v0.1` section 4
explicitly defers.

It was verified unused — no Requirement held a value and no implementation
referenced it — and has been removed, together with its option entities and the
option database Fibery kept for it. `Fibery-Schema-v0.1.md` never listed it, so
no schema documentation changed.

If the revision model later needs such a concept it should be introduced
deliberately, with the semantics designed first.

## 21. Open questions

Not blocking implementation of this capability, but they need answers before the
stages that follow it.

1. **Who writes confirmed relations — Review or Ready?** This spec assumes
   Review. Confirm when the Review agent is designed.
2. **Re-entry from Review.** Returning a Requirement from `Review` to `Process`
   is handled by section 10 and 11 as an input-change question. Whether Review
   is allowed to make that transition is a Review design decision.
3. **The editing path** that lets a human change a Draft between iterations is
   assumed to exist and is not designed here.
