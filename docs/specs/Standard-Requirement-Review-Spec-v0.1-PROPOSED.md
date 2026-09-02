# Standard Requirement Review Specification v0.1 — PROPOSED

**Status:** PROPOSED. Not approved. Nothing implements it.

Design pass for `Requirement.Type = Standard` + `Requirement.State = Review`.

## 1. Lifecycle position

```text
Draft -> Process -> Review -> Ready -> Apply -> Applied
```

`Process` is frozen. This capability performs `Review -> Ready`.

## 2. Why Review exists

Process normalized the Requirement and proposed things about it. The frozen rule
is that the action which rewrites must not be the action that certifies, so a
second, independent pass has to look at the result.

| Stage | Question | Actor |
|---|---|---|
| `Process` | Is this well-formed, and what does it touch? | model, normalizing |
| `Review` | Is what Process produced actually correct? | model, verifying |
| `Ready` | Do we accept it? | human |

## 3. Responsibility

Review independently assesses the **current** Root Document and checks Process's
own conclusions. It verifies:

```text
clarity, completeness, atomicity, internal consistency, testability
acceptance criteria quality
constraints and edge cases
consistency with existing Standard Requirements
each Process finding                -> confirmed / rejected / unresolved
each proposed relation              -> confirmed / rejected
```

and may raise findings Process missed.

It does **not** normalize, rewrite, or improve anything. A problem becomes a
finding, never a silent fix. `Process = writer, Review = verifier` is a hard
boundary (section 12).

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

- a separate role, `standard_requirement_reviewer`, resolved from
  `config/sdlc.toml`;
- a separate prompt that asks only for verification;
- a separate invocation;
- Process's raw model response is never forwarded. Review receives the
  *validated, persisted* Process Result as claims to check, and must reach its
  own conclusion about each one.

**v0.1 accepts the same underlying model** for both roles, provided role, prompt
and invocation are independent. This is a real limitation, stated plainly: one
model reviewing its own family of output shares blind spots, so Review reduces
error, it does not eliminate it. Multi-model consensus is deliberately not
introduced — `Ready` exists precisely so a human still decides.

## 7. Structured output

The model returns data only; no prose, no reasoning traces, unknown keys
rejected, exactly as in the frozen contracts.

```text
finding_verifications:
  - process_finding_index      which Process finding this addresses
    outcome: CONFIRMED | REJECTED | UNRESOLVED
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
Review and Process talk about the same things.

### The verdict is derived, never authored

The model supplies a **severity** per finding. Deterministic code derives the
overall verdict:

```text
any BLOCKING finding        -> BLOCKING
else any WARNING finding    -> NEEDS_WORK
else                        -> PASS
```

Deriving it prevents a response that claims `PASS` while listing blocking
findings, and keeps one authored vocabulary instead of two that can disagree.

### Execution success is not a quality verdict

```text
review executed successfully   the model answered and the answer validated
requirement verdict            PASS | NEEDS_WORK | BLOCKING
```

A `BLOCKING` verdict is a **successful** review run. Confusing the two would
make the processor fail whenever it did its job well.

## 8. Review Result artifact

A numbered, immutable child Document of the Root Document, mirroring Process
Results:

```text
<Requirement ID> — Review Result 0001
```

Contents:

```text
review_result_version
iteration                          review iteration
requirement_id
reviewed_document_fingerprint      canonical fingerprint of what was reviewed
reviewed_process_iteration         which Process Result was evaluated
reviewed_process_output_fingerprint
verdict                            derived
finding_verifications
relation_verifications
confirmed_relations                the subset a future Apply may write
new_findings
assessment
```

No chain-of-thought. JSON inside the child Document, as with Process Results.

This is enough to re-apply deterministically without a second model call, to
audit what was reviewed, and for a human at `Ready` to read the verdict,
blocking findings, warnings, confirmed and rejected Process findings, confirmed
and rejected relation proposals, and anything newly found.

## 9. Relations — confirmed, still not written

**Review does not write `Depends On` / `Blocks` / `Affects` / `Impacted By`.**
It records `confirmed_relations` in the Review Result, and a future `Apply`
writes them.

The Process spec provisionally assumed Review might write them. Resolving it
against the frozen meaning of `Ready` — *human decision has not happened yet* —
says otherwise:

- a relation is normative domain state, not analysis. It feeds impact analysis
  and planning for everyone, not just this Requirement;
- writing it before human approval puts an unapproved Requirement's edges into
  the shared graph;
- if the human then reworks or discards the Requirement, those edges must come
  back out, and removal/retirement semantics are undesigned. Writing early
  creates a cleanup problem we have no contract for;
- `REJECTED` must never remove an existing relation, and deferring the write
  means that case cannot arise by accident.

So the same discipline as Process: verify and record, let an approved step
mutate. When `Apply` is designed it must write additively, must not remove an
existing relation because a later iteration stopped proposing it, and must not
duplicate an edge on re-application.

**This contradicts one sentence in the frozen Process spec section 12** and
needs an explicit decision (section 17).

## 10. Every completed Review reaches Ready

```text
Review executed successfully -> State = Ready
```

**regardless of verdict**, including `BLOCKING`.

`Ready` is frozen as *independent agent review complete and human decision due*.
It is not a quality gate. The alternative — holding a `BLOCKING` Requirement in
`Review` — would mean the reviewer decides what only the human may decide, hides
the very findings the human needs, and requires a return path nobody has
designed. We also deliberately have no `Rejected` state.

A Requirement Review believes is duplicated, non-atomic, contradictory or simply
should not exist therefore reaches `Ready` carrying a `BLOCKING` verdict and the
findings that justify it. The human decides: Apply, rework, return to Process,
or discard by means outside this capability.

## 11. Review -> Ready criteria

`State = Ready` only when all of:

```text
Review Result persisted and re-read as valid
the reviewed input is still current (section 13)
verdict and verifications recorded
```

confirmed by reading the entity back, as in the frozen capabilities. It is never
conditional on the verdict being good.

## 12. Review never mutates the Requirement

Permitted mutations are exactly:

1. create one Review Result child Document for the current iteration;
2. set `Requirement.State = Ready`.

Review may **not** rewrite the Root Document, create or split Requirements,
change `Requirement ID`, `Type`, `Category`, `Project` or `Revision`, write any
relation, or touch any other Requirement — including Applied ones it inspects
for comparison. No new Fibery Field, relation or Database.

## 13. Stale review prevention

A Review Result certifies one exact input. Before transitioning to `Ready`:

```text
current Root Document canonical fingerprint == reviewed_document_fingerprint
latest Process Result iteration             == reviewed_process_iteration
that Process Result's output_fingerprint    == reviewed_process_output_fingerprint
```

If any differ the Review Result is **stale**:

```text
REVIEW_RESULT_STALE
```

with no certification, no `Ready` transition, no relation record applied, and no
mutation. The content moved on; a new review iteration is required.

Fingerprints use the frozen `canonical_markdown` representation, so Fibery's
Markdown re-serialization never registers as a change. Identity comes entirely
from existing data — no new Requirement Field.

## 14. Retry and idempotency

```text
model runs once
-> validated output
-> derive verdict
-> Review Result persisted and re-read      <- before any other mutation
-> staleness re-checked
-> State -> Ready, confirmed by read-back
```

```text
a Requirement reached Ready  =>  a valid, non-stale Review Result exists
```

- **No Review Result for the current input** → run the model, persist, apply.
- **A Review Result for the current input, not yet applied** → do **not** invoke
  the model; re-validate and complete the transition.
- **More than one for an iteration** → `REVIEW_STATE_CONFLICT`; refuse to guess.
- **Malformed or unsupported version** → `INVALID_REVIEW_RESULT`, no model call.

Failure before persistence leaves nothing durable, so a retry may call the model
again. Failure after leaves the Requirement in `Review` with the artifact
intact; nothing is deleted and no repair is automated.

## 15. Iterations and no-change

Review Results are numbered monotonically and never overwritten. A new iteration
is warranted when the Requirement is in `Review` and either the Root Document
fingerprint or the latest Process Result iteration differs from the latest
Review Result's recorded values.

If both match and the Review Result was already applied:

```text
NO_CHANGES_TO_REVIEW
```

with **zero mutations, including no state change**. The Requirement stays in
`Review`.

This is the same snapshot ambiguity Process resolved: a completed run whose
`Ready` transition failed is indistinguishable from a deliberate `Ready ->
Review`. v0.1 adds nothing to distinguish them and does not guess — it preserves
the workflow state it was given, and recovery of the rarer failed-transition
case is manual, exactly as frozen for Process.

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

## 17. Unresolved decisions

1. **Relation timing (section 9).** This spec defers relation writes to `Apply`.
   That contradicts one provisional sentence in the frozen
   `Standard-Requirement-Process-Spec-v0.1` section 12. Approving this spec
   should carry a one-line correction to that sentence. Flagged rather than
   edited, because that spec is frozen.
2. **Who writes confirmed relations.** This spec says `Apply`. `Apply` is not
   designed, so nothing writes them yet. That is acceptable for v0.1 but means
   confirmed relations accumulate unapplied until `Apply` exists.
3. **Same model for both roles (section 6).** Accepted for v0.1; revisit if
   Review is observed rubber-stamping Process.
4. **Re-review after `Ready`.** Whether a human may return `Ready -> Review`,
   and whether that should behave as `NO_CHANGES_TO_REVIEW`, is a `Ready`
   design question.

## 18. Non-goals

No `Ready` UI, human approval command, `Apply`, `Applied`, revision, update or
supersession semantics, Requirement split or merge, Project Phase planning,
backlog, Epics, User Stories, Tasks, GitHub integration, or automatic
status-triggered orchestration.

Review also does not normalize, rewrite or repair anything.

## 19. Required tests

Deterministic, with a fake model runtime:

```text
entry: only Standard + Review; anything else refused with no model call
       a Requirement with no Process Result -> NO_PROCESS_RESULT
context: current Root Document and latest Process Result assembled;
         earlier Process Results and prior Review Results excluded
output: unknown keys, bad outcomes, bad severities, bad finding kinds rejected
verdict derivation: BLOCKING > NEEDS_WORK > PASS, derived not authored
independence: a Process finding can be REJECTED
              a new finding can be raised that Process did not report
              the Root Document is never rewritten
Review Result written before any other mutation
  none for this input          -> model runs
  present and unapplied        -> model must NOT run, application resumes
  duplicate for one iteration  -> REVIEW_STATE_CONFLICT
  malformed / wrong version    -> explicit failure, no model call
staleness: document changed after persistence      -> REVIEW_RESULT_STALE
           new Process iteration after persistence -> REVIEW_RESULT_STALE
           stale never transitions to Ready
relations: no Depends On / Blocks / Affects / Impacted By write on any path
           confirmed and rejected proposals both recorded
           a REJECTED proposal removes no existing relation
existing Requirements: never mutated in any way
Revision never changed
BLOCKING verdict still reaches Ready
partial failure leaves State = Review with durable state intact
retry resumes without a model call and without drift
unchanged re-entry -> NO_CHANGES_TO_REVIEW, zero mutations, State stays Review
State -> Ready only on complete success, confirmed by read-back
```

## 20. Fibery fake fidelity and live acceptance

The standing project rule applies. For every new Fibery read/write behaviour
this capability introduces: verify the real behaviour where correctness depends
on it, make the fake reflect it — including Markdown re-serialization on
read-back — add regression coverage for any mismatch, and run one narrow live
acceptance before freeze.

The new read path here is discovering and reading Review Result children
alongside Process Result children under the same Root Document; both are child
Documents, so the verified `fibery/parent-page-id` behaviour applies, and the
two must be told apart by name without either capability seeing the other's
artifacts as source material.

### Live acceptance before freeze

On a temporary Project, the full chain: `project init` → `requirement add` → RAW
Process → Standard Process → Standard Review. Verify independently in Fibery
that the Review Result exists once, the Root Document is byte-unchanged by
Review, Process Result history is intact, no relation was written, no other
Requirement changed, `Revision` is unchanged, and `State` is `Ready`. Then
re-enter `Review` unedited and confirm `NO_CHANGES_TO_REVIEW` with no new
artifact and no state change.
