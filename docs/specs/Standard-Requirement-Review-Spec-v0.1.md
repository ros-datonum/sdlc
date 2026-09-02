# Standard Requirement Review Specification v0.1

**Status:** APPROVED. Frozen contract for implementation. No implementation exists yet.

Design for `Requirement.Type = Standard` + `Requirement.State = Review`.

## 1. Lifecycle position

```text
Draft -> Process -> Review -> Ready -> Apply -> Applied
```

`Process` is frozen. This capability performs `Review -> Ready`.

## 2. Why Review exists

Process normalized the Requirement and proposed things about it. The frozen rule
is that the action which writes Requirement content must not be the action that
certifies it, so a second, independent pass has to look at the result.

| Stage | Question | Actor |
|---|---|---|
| `Process` | normalize + analyze + propose | model, writing |
| `Review` | independently verify + confirm/reject | model, verifying |
| `Ready` | independent agent review complete; human decision due | human |

## 3. Responsibility

Review independently assesses the **current** Standard Requirement and checks
Process's own conclusions. It:

```text
independently assesses the current Root Document
verifies each Process finding             -> CONFIRMED / REJECTED / UNRESOLVED
verifies each Process relation proposal   -> CONFIRMED / REJECTED / UNRESOLVED
may discover new findings
derives an overall quality verdict
```

covering clarity, completeness, atomicity, internal consistency, testability,
acceptance criteria quality, constraints and edge cases, and consistency with
existing Standard Requirements.

Review **never** normalizes, **never** rewrites, and **never** repairs the
Requirement Root Document. A problem becomes a finding, never a silent fix.
`Process = writer, Review = verifier` is a hard boundary (section 12).

## 4. Entry condition

```text
Requirement.Type  = Standard
Requirement.State = Review
```

Anything else is refused with zero model calls and zero Fibery mutations.

## 5. Input context

```text
the Requirement entity (Requirement ID, Title, Category, Revision, Project)
its current Root Document
the latest Process Result: findings, proposed relations, analysis
existing Standard Requirements in the Project: ID, Title, requirement text
the Requirement's existing real Depends On / Affects relations
```

Earlier Process Result iterations are history and are not sent. Previous Review
Results are not sent either: a reviewer must not anchor on its own prior verdict.

## 6. Independence

Independence is structural, not a subsystem:

- a separate runtime role, `standard_requirement_reviewer`, resolved from
  `config/sdlc.toml`;
- a separate prompt that asks only for verification;
- a separate invocation;
- a separate persisted Review Result;
- Process's raw model response is never forwarded. Review receives the
  *validated, persisted* Process Result as claims to check, and must reach its
  own conclusion about each one.

**v0.1 accepts the same underlying Claude/Codex model** configured for both
roles, provided role, prompt, invocation and artifact are independent. The
limitation is stated plainly:

> separate roles reduce correlated reasoning bias but do not provide true model
> diversity.

Not introduced: multi-model consensus, voting, adversarial swarms, authority
infrastructure. Model diversity may be evaluated later from evidence. `Ready`
exists precisely so a human still decides.

## 7. Structured output

The model returns data only; no prose, no reasoning traces, unknown keys
rejected, exactly as in the frozen contracts. The schema can express findings
and verdictless verifications and nothing else — no Fibery command, no document
content, no state change is representable in it.

```text
finding_verifications:
  - process_finding_index      which Process finding this addresses
    outcome: CONFIRMED | REJECTED | UNRESOLVED
    severity: INFO | WARNING | BLOCKING     (required iff CONFIRMED)
    reason

relation_verifications:
  - kind: DEPENDS_ON | AFFECTS
    requirement_id
    outcome: CONFIRMED | REJECTED | UNRESOLVED
    reason

new_findings:
  - kind: <the frozen Process finding vocabulary>
    severity: INFO | WARNING | BLOCKING
    requirement_id   (only for comparison kinds)
    detail

assessment:
  clarity, completeness, atomicity, testability,
  internal_consistency, acceptance_criteria
```

The finding vocabulary is reused unchanged from the frozen Process contract, so
Review and Process talk about the same things. Every `process_finding_index`
must address exactly one finding of the reviewed Process Result, and every
finding must be addressed exactly once.

### The verdict is derived, never authored

The model never emits an overall verdict; it supplies a **severity** per finding
it asserts is real. Deterministic code derives the verdict over the union of
`CONFIRMED` finding verifications and `new_findings`:

```text
any BLOCKING     -> BLOCKING
else any WARNING -> NEEDS_WORK
else             -> PASS
```

Frozen Process findings carry no severity of their own, so a confirmed Process
finding contributes the severity Review assigns when confirming it. Without this
a confirmed blocking Process finding would derive `PASS`.

`REJECTED` contributes nothing: Review is asserting there is no defect.
`UNRESOLVED` also contributes nothing to the derivation — it is an admission of
uncertainty, not a defect claim, and letting uncertainty silently downgrade
every Requirement would make the verdict meaningless. Unresolved items are
recorded in full and shown to the human at `Ready` (section 14). This is the
whole derivation; there is no other rule.

Deriving the verdict makes it impossible for a response to claim `PASS` while
separately emitting a blocking finding, and keeps one authored vocabulary
instead of two that can disagree.

### Execution success is not a quality verdict

```text
review execution status   !=   Requirement quality verdict
```

```text
review executed successfully   the model answered and the answer validated
requirement verdict            PASS | NEEDS_WORK | BLOCKING
```

A `BLOCKING` verdict is a **successful** review run. A processor, runtime or
Fibery failure is a different thing entirely and must never transition to
`Ready`.

## 8. Review Result artifact

A numbered, immutable child Document of the Root Document, mirroring Process
Results:

```text
<Requirement ID> — Review Result 0001
<Requirement ID> — Review Result 0002
```

Contents:

```text
review_result_version
iteration                          review iteration
requirement_id
reviewed_document_fingerprint      canonical fingerprint of what was reviewed
reviewed_process_iteration         which Process Result was evaluated
reviewed_process_output_fingerprint
derived_verdict                    derived by code, never authored
process_finding_verifications
relation_proposal_verifications
confirmed_relation_proposals       the subset a future Apply may write
new_findings
assessment
```

No chain-of-thought. JSON inside the child Document, as with Process Results.
Previous Review Results are immutable history: never overwritten, never reused,
never deleted.

This is enough to re-apply deterministically without a second model call and to
audit exactly what was reviewed.

## 9. Relations — confirmed, still not written

**`STANDARD + Review` writes zero actual Requirement relations.** It must not
mutate `Depends On` / `Blocks` or `Affects` / `Impacted By` on any path.

```text
Process  -> proposes DEPENDS_ON / AFFECTS
Review   -> confirms / rejects proposals
Ready    -> human decision
Apply    -> future normative relation mutation
```

Confirmed proposals are persisted only in the Review Result, as
`confirmed_relation_proposals`. Reasons:

- a relation is normative shared domain state, not analysis. It feeds impact
  analysis and planning for everyone, not just this Requirement;
- `Ready` has not yet received human approval, and writing before approval puts
  an unapproved Requirement's edges into the shared graph;
- removal and reversal semantics are undesigned, so an early write creates a
  cleanup problem with no contract;
- **a rejected proposal must never remove an already existing relation**, and
  deferring the write means that case cannot arise by accident.

Same discipline as Process: verify and record, let an approved step mutate. When
`Apply` is designed its writes must be additive, must not remove an existing
valid relation because a later iteration stopped proposing it, and must not
duplicate an edge on re-application.

`Standard-Requirement-Process-Spec-v0.1` section 12 has been corrected to match.

## 10. Every completed Review reaches Ready

```text
Review executed successfully -> State = Ready
```

**regardless of the derived verdict**, including `BLOCKING`.

`Ready` is frozen as *independent agent review complete and human decision due*.
It is not a quality gate. The alternative — holding a `BLOCKING` Requirement in
`Review` — would mean the reviewer decides what only the human may decide, hides
the very findings the human needs, and requires a return path nobody has
designed. There is deliberately no `Rejected` state.

A Requirement that Review believes is duplicated, non-atomic, contradictory or
simply should not exist therefore reaches `Ready` carrying a `BLOCKING` verdict
and the findings that justify it. The human decides: Apply, rework, return to
Process, or discard by means outside this capability.

## 11. Review -> Ready criteria

`State = Ready` only when all of:

```text
Review Result persisted and re-read as valid
the reviewed input is still current (section 13)
derived verdict and all verifications recorded
```

confirmed by reading the entity back, as in the frozen capabilities. It is never
conditional on the verdict being good.

## 12. Review never mutates the Requirement

Permitted mutations are exactly:

1. create one Review Result child Document for the current iteration;
2. set `Requirement.State = Ready`.

Review must **never** rewrite the Standard Requirement Root Document — not on
`PASS`, `NEEDS_WORK`, `BLOCKING`, retry, or re-review. Review findings exist
only in the Review Result. This preserves `Process = writer, Review = verifier`.

Review may **not** create, split or delete Requirements, change
`Requirement ID`, `Type`, `Category`, `Project` or `Revision`, write any
relation, modify a Process Result, or add a Fibery Field, relation or Database.

### Existing Requirement safety

Review may inspect other Standard and Applied Requirements for comparison, and
must not mutate them in any way:

```text
no State change
no Revision change
no Document rewrite
no retirement
no supersession
no relation mutation
```

Existing-Requirement comparison is analysis only.

## 13. Stale review prevention

A Review Result certifies one exact input. It is bound at the start of the run
to the current canonical Root Document fingerprint, the latest Process Result
iteration, and that Process Result's output fingerprint. Before any final state
transition all of that identity is re-read and recomputed, and all of:

```text
current Root Document canonical fingerprint == reviewed_document_fingerprint
latest Process Result iteration             == reviewed_process_iteration
that Process Result's output_fingerprint    == reviewed_process_output_fingerprint
```

must hold. If any differ the Review Result is **stale**:

```text
REVIEW_RESULT_STALE
```

Then: do not transition to `Ready`; do not mutate relations; do not certify
stale content; do not automatically invoke the model again for that stale
result. Nothing is deleted — the stale Review Result remains as history, and a
new review iteration is required (section 15).

Fingerprints use the frozen `canonical_markdown` representation, so Fibery's
Markdown re-serialization never registers as a change. Identity comes entirely
from existing data — **no new Requirement Field is needed**.

## 14. Persistence order, retry and idempotency

```text
assemble bounded review context
-> invoke reviewer
-> validate structured output
-> derive verdict deterministically
-> persist Review Result
-> read back and validate Review Result
-> re-check stale bindings
-> transition Review -> Ready
-> read Requirement back
-> verify Ready
```

A state transition may happen only after a durable, valid, non-stale Review
Result exists:

```text
a Requirement reached Ready  =>  a valid, non-stale Review Result exists
```

**Failure before Review Result persistence** leaves no durable review output, so
a retry may invoke the model again.

**Failure after Review Result persistence** leaves the artifact intact. A retry
must not invoke the model. Within the same run the remaining deterministic steps
are resumed from the persisted result. Nothing is deleted and no repair is
automated.

Across a later re-entry the Requirement is in `Review` with a Review Result
whose bindings match the current input, which is exactly the ambiguous case of
section 15: the run returns `NO_CHANGES_TO_REVIEW` with zero mutations and no
model call, and recovery of a failed final transition is manual.

Other cases:

- **No Review Result for the current input** → run the model, persist, apply.
- **More than one Review Result for an iteration** → `REVIEW_STATE_CONFLICT`;
  refuse to guess.
- **Malformed or unsupported version** → `INVALID_REVIEW_RESULT`, no model call.

A failed `Ready` transition is always reported as a failure and never as normal
completion.

## 15. Iterations and no-change

Review Result iterations are monotonic — `0001`, `0002`, `0003` — never
overwritten and never reused. Previous history remains untouched.

A new Review iteration is allowed when the reviewed input changed, meaning at
least one of:

```text
current document fingerprint changed
latest Process Result iteration changed
latest Process Result output fingerprint changed
```

If `Requirement.State = Review` and the current document fingerprint, Process
iteration and Process output fingerprint all exactly match the latest
successfully reviewed input:

```text
NO_CHANGES_TO_REVIEW
```

with

```text
model calls        = 0
new Review Results = 0
document mutations = 0
relation mutations = 0
state mutations    = 0
```

Final `State` remains `Review`.

### The ambiguity, documented

That situation has two indistinguishable causes: a deliberate `Ready -> Review`
by a human, or an earlier run whose final transition failed after the Review
Result was fully persisted and validated. Unlike Process — whose rewritten Root
Document is itself the applied-marker — Review writes nothing to the document,
so it has no intrinsic evidence of which happened.

v0.1 **does not infer** which it was and **does not add** a completion marker,
ledger or schema field solely to distinguish it. It preserves the workflow state
it was given. Manual state recovery for the rarer failed-transition case is
accepted for v0.1, exactly as frozen for Process.

## 16. Failure states

```text
REQUIREMENT_NOT_FOUND
NOT_A_STANDARD_REQUIREMENT
REQUIREMENT_NOT_IN_REVIEW
NO_PROCESS_RESULT              nothing has processed this Requirement yet
NO_CHANGES_TO_REVIEW
REVIEW_RESULT_STALE
REVIEW_STATE_CONFLICT
INVALID_REVIEW_RESULT
MODEL_RUNTIME_FAILED
INVALID_MODEL_OUTPUT
REVIEW_RESULT_WRITE_FAILED
FIBERY_READ_FAILED
FIBERY_WRITE_FAILED
VALIDATION_FAILED
PARTIAL_REVIEW
```

Durable state is always reported and never silently deleted.

## 17. Human visibility at Ready

The Review Result is structured so a human at `Ready` can inspect, without
reading model prose:

```text
the overall derived verdict
blocking findings
warnings
confirmed / rejected / unresolved Process findings, each with its reason
confirmed / rejected relation proposals, each with its reason
new findings
the concise assessment
```

No UI is designed here.

## 18. Unresolved decisions

1. **Who writes confirmed relations.** `Apply`, which is not designed. Nothing
   writes them yet, so confirmed relation proposals accumulate as pending
   normative changes until `Apply` exists. This is explicitly acceptable and is
   **not a blocker**; `Apply` must not be implemented prematurely merely to
   consume them.
2. **Same underlying model for both roles (section 6).** Accepted for v0.1;
   revisit from evidence if Review is observed rubber-stamping Process.
3. **`Ready -> Review`.** Whether a human may move a Requirement back is
   deliberately undefined here; it belongs to `Ready` / human workflow design.
   This spec defines Review's behaviour only for a Requirement already
   legitimately in `Review`.

## 19. Non-goals

```text
Ready UI                     human approval command
Apply                        Applied
actual relation application  revision / update / supersession
Requirement split / merge    Project Phases
backlog                      Epics
Stories                      Tasks
GitHub integration           multi-model consensus
```

Also out of scope: automatic status-triggered orchestration. Review does not
normalize, rewrite or repair anything.

## 20. Required tests

Deterministic, with a fake model runtime and the Fibery fake.

### Entry

```text
Standard + Review accepted
wrong Type rejected
wrong State rejected
no Process Result -> NO_PROCESS_RESULT
rejected entry causes zero model calls and zero mutations
```

### Structured output

```text
finding severities validated
Process finding verification status validated
relation proposal verification validated
every Process finding addressed exactly once
unknown fields rejected
mutation commands are inexpressible in the schema
```

### Verdict

```text
INFO only                   -> PASS
any WARNING                 -> NEEDS_WORK
any BLOCKING                -> BLOCKING
CONFIRMED Process finding contributes its severity
REJECTED and UNRESOLVED contribute nothing
verdict derived by code, never supplied by the model
```

### Independence

```text
a Process finding can be REJECTED
a Process finding can remain UNRESOLVED
Review can discover a new finding Process did not report
the Root Document remains semantically unchanged on every path
earlier Process Results and prior Review Results are excluded from context
```

### Review Result

```text
persisted before the Ready transition
malformed / wrong version rejected, no model call
duplicate iteration -> REVIEW_STATE_CONFLICT
previous iterations immutable
```

### Staleness

```text
Root Document changed after persistence     -> REVIEW_RESULT_STALE
Process iteration changed                   -> REVIEW_RESULT_STALE
Process output fingerprint mismatch         -> REVIEW_RESULT_STALE
a stale result can never transition to Ready
```

### Relations

```text
confirmed proposals persisted in the Review Result
rejected proposals recorded with their reason
no Depends On / Blocks / Affects / Impacted By write on any path
a REJECTED proposal removes no existing relation
```

### Retry

```text
failure after Review Result persistence does not call the model again
a failed Ready transition never reports normal completion
partial failure leaves State = Review with durable state intact
retry resumes without drift
```

### No-change and iterations

```text
identical reviewed input -> NO_CHANGES_TO_REVIEW, zero mutations, State = Review
changed reviewed input   -> next Review Result iteration
iteration numbering monotonic; earlier results never modified
```

### State and safety

```text
normal successful execution -> Ready
BLOCKING verdict still reaches Ready
the Ready transition is independently read back
Revision never changed
existing Requirements never mutated in any way
```

## 21. Fibery fake fidelity

The standing project rule applies without exception. For every new Fibery
read/write pattern introduced during Review implementation:

1. verify the relevant real Fibery behaviour;
2. reproduce it faithfully in the fake;
3. add deterministic regression coverage;
4. perform one narrow live acceptance before freeze.

Do not rely on fake behaviour alone for a new Fibery integration path.

The new read path here is discovering and reading Review Result children
alongside Process Result children under the same Root Document. Both are child
Documents, so the verified `fibery/parent-page-id` behaviour applies, and the
two must be told apart by name without either capability treating the other's
artifacts as source material.

## 22. Live acceptance before freeze

On a temporary Project, the full chain:

```text
project init -> requirement add -> RAW Process -> Standard Process -> Standard Review
```

Verify independently in Fibery, at minimum:

```text
Review Result exists (exactly once)
the review binds to the correct Process iteration and output fingerprint
Root Document unchanged
Process Result unchanged
derived verdict correct for the recorded findings
findings and verifications persisted
confirmed relation proposals persisted
actual Depends On / Affects unchanged
State = Ready
Revision unchanged
```

Also exercise one bounded stale, no-change or retry case if practical — for
example re-entering `Review` unedited and confirming `NO_CHANGES_TO_REVIEW` with
no new artifact and no state change.
