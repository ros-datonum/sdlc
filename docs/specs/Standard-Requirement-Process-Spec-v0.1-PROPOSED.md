# Standard Requirement Process Specification v0.1 — PROPOSED

**Status:** PROPOSED. Not approved. Nothing implements it.

Design pass for `Requirement.Type = Standard` + `Requirement.State = Process`.
Written to settle the contract before implementation, following the pattern that
`project init`, `project requirement add` and the RAW Requirement Processor were
each frozen against a specification first.

## 1. Where this sits

```text
Draft -> Process -> Review -> Ready -> Apply -> Applied
```

A Standard Requirement enters `Draft` from the RAW Requirement Processor. This
capability is the transition `Process -> Review`.

## 2. Stage boundary

The lifecycle only works if each stage answers a different question. The
proposed split:

| Stage | Question | Who acts |
|---|---|---|
| `Draft` | What did decomposition produce? | RAW Processor (frozen) |
| `Process` | Is this requirement well-formed, and what does it touch? | reasoning model, normalizing |
| `Review` | Is what Process produced actually correct? | an independent reviewing agent |
| `Ready` | Do we accept this? | human |

The load-bearing rule:

> The action that rewrites a requirement must not be the action that certifies
> it.

So `Process` **normalizes and proposes**. `Review` **verifies and confirms**.
`Ready` is human acceptance. This separation is achieved by the workflow itself,
not by any new authority mechanism.

### What Process owns

```text
completeness        is anything required to interpret it missing?
clarity             is it unambiguous?
atomicity           is it exactly one obligation?
internal consistency does it contradict itself?
testability         can satisfaction be observed?
missing constraints / edge cases
dependency discovery      -> proposed, not written
change-impact discovery   -> proposed, not written
duplication / conflict with existing Standard Requirements -> findings
```

### What Process does NOT own

Judging whether the normalized requirement is *right*. That is `Review`. Process
may say "this is now well-formed"; only Review may say "this is correct".

## 3. Entry condition

```text
Requirement.Type  = Standard
Requirement.State = Process
```

Anything else is refused with zero model calls and zero mutations, matching the
RAW Processor's entry behaviour.

## 4. Input context

Bounded, as with RAW processing:

```text
the Requirement entity (Requirement ID, Title, Category, Revision, Project)
its Root Document
its child Documents, recursively, excluding this capability's own artifacts
the Project
the RAW Requirement it derives from, and that RAW's Root Document
existing Standard Requirements in the Project: ID, Title, and requirement text
```

The originating RAW is included because Process must be able to tell "the source
never said this" from "the decomposition dropped it".

No Milestones, Epics, Stories, Tasks, or unrelated project state.

## 5. Model boundary

Reuses the frozen `ModelRuntime` / `LocalCliModelRuntime` and
`config/sdlc.toml`, with a new role:

```text
standard_requirement_processor
```

No runtime redesign. The model returns structured data only; it never writes to
Fibery, never chooses an identifier, and is never asked for reasoning traces.
Unknown fields are rejected, as in the RAW contract.

Proposed output shape:

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
  - kind: POSSIBLE_DUPLICATE | POSSIBLE_CONFLICT
          | POSSIBLE_CHANGE | POSSIBLE_SUPERSESSION
    requirement_id
    detail
```

`normalized_requirement` reuses the approved
`Standard-Requirement-Document-Schema-v0.1` sections exactly, so the document is
still rendered deterministically by code.

## 6. Permitted Fibery mutations

Process may:

1. create exactly one **Process Result** child Document under the Requirement's
   Root Document;
2. rewrite the Requirement's Root Document content from that persisted result;
3. set `Requirement.State = Review`.

Process may **not**:

- create or delete Requirement entities;
- write `Depends On` / `Blocks` / `Affects` / `Impacted By`;
- modify any other Requirement, in any state;
- change `Requirement ID`, `Type`, `Category`, `Project`, `Revision`;
- add Fibery Fields, relations or Databases;
- use `SDLC/Operation` (see section 12).

## 7. The Process Result artifact

Same shape as the frozen RAW Processing Result, for the same reason: it is what
makes retry safe.

```text
<Requirement ID> — Process Result
```

created as a child of the Root Document through `fibery/parent-page-id`.

It records the validated model output **and the Root Document content as it was
before normalization**, so nothing the RAW Processor produced is lost when
Process rewrites it.

Ordering, and the invariant it buys:

```text
model runs once
-> validated output
-> Process Result persisted and read back      <- before any mutation
-> Root Document rewritten from the persisted result
-> State -> Review
```

```text
the Root Document was rewritten  =>  a valid Process Result already exists
```

## 8. Relations — proposed, not written

Process **does not write** `Depends On` / `Blocks` / `Affects` / `Impacted By`.

Reasons:

- writing them would make Process self-certify its own inferences into canonical
  structure, which section 2 forbids;
- these relations are graph-wide facts; a wrong edge is expensive to find later;
- Review exists precisely to confirm them.

Proposals live inside the Process Result, keyed by Requirement ID. No new
"relation proposal" Database, and no new Field — the artifact already exists for
retry, and carrying proposals in it costs nothing.

When Review later writes a confirmed relation it uses
`fibery.entity/add-collection-items`, which is **additive**: existing valid
relations are never replaced, so reprocessing cannot destroy them. Each pair
shares one Fibery relation id, so writing one side populates the inverse:

```text
Depends On <-> Blocks          a0353ff0-...
Affects    <-> Impacted By     ba1ae370-...
Derived From <-> Produces      8002c1d0-...   (written by the RAW Processor)
```

## 9. Existing Standard Requirements

The four finding kinds stay **informational**, exactly as in RAW processing.
Process records them with evidence; it never modifies the referenced
Requirement, its Documents, or its State.

This is deliberate: acting on `POSSIBLE_SUPERSESSION` or `POSSIBLE_CHANGE`
requires the Applied-Requirement revision model, which is not designed. Process
does **not** need that model to function — it only needs to be able to say
"a human or Review should look at this". So this is not a blocker for Process.

It *is* a blocker for anything that wants to act on those findings, and that
should be recorded when the revision model is designed.

## 10. Process -> Review transition

`State = Review` only when all of:

```text
Process Result persisted and re-read as valid
Root Document rewritten and verified by canonical read-back
proposals and findings recorded in the Process Result
```

Read-back uses `content_equivalent`, because Fibery re-serializes stored
Markdown (constraint 11).

The transition is **not** conditional on the requirement being judged good.
A requirement Process considers weak still moves to `Review`, carrying its
analysis. Quality gating belongs to Review and Ready.

The state write is confirmed by reading the entity back, matching the frozen
RAW Processor.

## 11. Retry and idempotency

The RAW pattern applies unchanged:

```text
no Process Result  -> run the model, persist, then mutate
one Process Result -> DO NOT run the model; resume deterministic application
many               -> PROCESSING_STATE_CONFLICT, refuse to guess
malformed / wrong version -> explicit failure, no model call
```

Rewriting the Root Document from a persisted result is naturally idempotent: the
same bytes are written, and the canonical comparison accepts the re-serialized
read-back. Because the model runs at most once per Process attempt, repeated
retries cannot cause drift.

A failure after the Process Result is persisted leaves the Requirement in
`Process` with durable state intact. Nothing is deleted.

No new deterministic-UUID mechanism is needed: Process creates no entities.

## 12. `SDLC/Operation` — do not use

The live workspace has an `SDLC/Operation` Field with values
`CREATE`, `UPDATE`, `RETIRE`, `SUPERSEDE`. **No Requirement uses it.**

`RAW-Requirement-Processor-Decision-v0.1` section 4 explicitly defers this
concept until the revision model exists. Its presence in the workspace does not
approve it. Process must not read or write it, and the discrepancy between the
workspace and the approved design should be resolved deliberately, not by a
capability quietly starting to populate it.

## 13. Failure states

```text
REQUIREMENT_NOT_FOUND
NOT_A_STANDARD_REQUIREMENT
REQUIREMENT_NOT_IN_PROCESS
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

## 14. Non-goals

Process does not implement the Review agent, `Ready`, `Apply`, `Applied`,
Applied-Requirement revision or supersession, Project Phase planning, backlog
generation, Epics, Stories, Tasks, GitHub workflow, or automatic
status-triggered orchestration.

It also does not split one Draft into several Requirements (section 16).

## 15. Required tests

Deterministic, with a fake model runtime:

```text
entry: only Standard + Process; anything else refused with no model call
context: RAW ancestry and child Documents assembled; own artifacts excluded
model output: unknown fields, bad relation kinds, bad finding kinds rejected
Process Result: written before any document mutation
                absent -> model runs; present -> model must not run
                duplicate -> conflict; malformed -> explicit failure
original content preserved inside the Process Result
document rewritten from the persisted result, verified with content_equivalent
proposed relations are NOT written to Fibery
findings do not mutate the referenced Requirement
partial failure leaves State = Process and durable state intact
retry resumes without a model call and without drift
State -> Review only on complete success, confirmed by read-back
```

### Fake fidelity rule

Carried forward as a standing requirement, because it has now hidden two real
defects:

> For every new Fibery read/write pattern this capability introduces, the fake
> must model the verified Fibery behaviour for that pattern — including
> Markdown re-serialization on read-back — and one narrow live acceptance must
> be run before freeze.

### Live acceptance before freeze

On a temporary Project: create a RAW, process it, take one produced Standard
Draft to `Process`, run this capability, then verify independently in Fibery
that the Root Document was rewritten, the Process Result exists once, no
relations were written, no other Requirement changed, and State is `Review`.

## 16. Unresolved questions

These need decisions before implementation.

1. **Atomicity when a Draft is not atomic.** If Process finds two obligations in
   one Draft, does it split into two Requirements, or only flag it?
   *Recommendation:* flag only in v0.1. Splitting means creating entities, which
   drags in deterministic identity, `Derived From` fan-out from the RAW, and the
   question of what happens to the original — a materially larger capability.
2. **Revision.** Does rewriting the Root Document increment `Revision`?
   *Recommendation:* no in v0.1. `Revision` belongs to the undesigned revision
   model, and Process would be guessing its semantics.
3. **Who writes confirmed relations — Review or Ready?** This spec assumes
   Review. It needs confirming when the Review agent is designed.
4. **A Draft that should not exist.** If Process concludes a candidate is not a
   real requirement, is there a terminal state? The workflow has no `Rejected`
   or `Cancelled` for Requirements. *Recommendation:* record a finding and let a
   human decide; do not invent a state.
5. **Re-processing after Review.** Can a Requirement return from `Review` to
   `Process`? If so, the existing Process Result must be superseded rather than
   conflicting. Not designed here.
6. **`SDLC/Operation`** exists in the workspace but is deferred by approved
   design (section 12). Decide whether to remove it, or to design the revision
   model that gives it meaning.
