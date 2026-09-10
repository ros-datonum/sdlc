# Standard Requirement Abstraction Contract v0.2

**Status:** DRAFT — RW-C01 HUMAN/REVIEWER CONTRACT  
**Implementation authorization:** NONE  
**Rewrite item:** `RW-C01`  
**Primary product requirements:** `docs/rewrite/SDLC-Corrected-Product-Functional-Requirements-v0.2.md`

## 1. Purpose

This contract defines the abstraction boundary of a Standard Requirement in SDLC.

Its purpose is to preserve product and system intent without prematurely choosing the technical solution or decomposing that solution into implementation work.

The central rule is:

```text
Requirement
= WHAT must be true

Technical Solution Architecture
= HOW the approved Requirement will be satisfied

Delivery Planning
= how the chosen solution is decomposed into executable work

Task implementation
= concrete code, configuration, migration, test, or deployment work
```

A Standard Requirement is therefore not a miniature architecture document, implementation specification, task, or test plan.

---

## 2. What a Standard Requirement may define

A Standard Requirement may define one independently meaningful obligation of one of these forms:

1. **Capability** — something a user, operator, integration, or the system must be able to do.
2. **Outcome** — a result that must be achieved or made true.
3. **Observable behavior** — how the system must behave under a meaningful condition or event.
4. **Business or system constraint** — a boundary that a valid solution must respect.
5. **Invariant** — a property that must continue to hold across valid operation or lifecycle changes.

The Requirement may contain enough behavioral detail to remove ambiguity about **what is required**. It must stop before prescribing **how the solution is internally constructed**, unless the source explicitly requires that mechanism.

---

## 3. Implementation independence is the default

A valid Standard Requirement should normally remain true if the implementation is replaced by a different valid technical solution.

Use this test:

> If the implementation technology, internal module structure, algorithm, process topology, storage mechanism, integration mechanism, or test framework changed, would this statement still describe the same required product/system behavior?

- **YES** usually indicates Requirement-level content.
- **NO** usually indicates Architecture, Delivery Planning, Task, or test-implementation content.

This is a diagnostic rule, not a requirement that every sentence be visible to an end user. Internal system guarantees such as security, reliability, consistency, privacy, recoverability, and lifecycle invariants may still be valid Requirements when they constrain the delivered system rather than prescribe one implementation.

---

## 4. The source-mandated mechanism exception

A technical mechanism may be normative Requirement content only when the source explicitly makes that mechanism part of the required obligation or constraint.

Examples:

- Source says only that caller-controlled input must not be interpreted as executable command syntax. The Requirement states that security outcome; the choice of process invocation mechanism belongs to Architecture.
- Source explicitly requires that a specific externally mandated protocol or platform be used. That mechanism may remain a Constraint because changing it would violate source intent.

The processor must not infer that a technical detail is mandatory merely because it appears in background discussion, an existing implementation, an example, or a previously proposed architecture.

When it is unclear whether a mechanism is mandatory, preserve the uncertainty as an Open Question instead of promoting the mechanism to a Requirement.

---

## 5. What must not become a separate Standard Requirement by itself

Do not create a Standard Requirement merely because the source mentions any of the following:

- a class, function, module, package, library, framework, programming language, or source file;
- an algorithm or internal execution sequence;
- a queue, webhook, polling loop, scheduler, worker topology, process model, or other internal triggering mechanism;
- a database table, schema field, serialization format, internal config file, hash, manifest, lock, retry algorithm, or transport call;
- a branch, worktree, commit, pull request, or merge technique;
- a test fixture, mock, unit-test arrangement, assertion sequence, test framework, or exact test implementation;
- a deployment command or platform-specific deployment procedure;
- an implementation-specific edge case whose meaning exists only because a particular technical solution was chosen;
- an individual field or flag that has no independently meaningful product/system obligation.

Such material may be useful source context for later Architecture or Delivery Planning. Its presence in RAW input does not automatically make it Requirement truth.

---

## 6. Field-level details

A field-level concept is a separate Requirement only when it represents an independently meaningful obligation from the product/system perspective.

Examples:

- **Requirement-level:** “Every processing attempt must have a stable identity that lets the user trace its result to the originating request.”
- **Not automatically Requirement-level:** “Add a `request_id: UUID` field to class `ModelRequest`.”

The second statement may become Architecture/Task detail unless the external contract itself, including that exact field, is an explicitly mandated product interface.

Do not decompose one meaningful capability into one Requirement per field merely to make each statement atomic.

---

## 7. Atomicity at the Requirement level

“One Requirement = one obligation” means **one independently reviewable product/system obligation**, not one sentence, field, parameter, branch, failure case, or implementation rule.

A Requirement is too broad when it combines obligations that:

- can be accepted or rejected independently;
- can change independently without changing the other;
- represent materially different outcomes or constraints;
- would naturally have different downstream solution ownership.

A Requirement is over-fragmented when multiple candidates are merely technical facets of one meaningful capability and do not have independent product/system value.

When a source contains one capability plus many technical details explaining one proposed implementation, prefer one Requirement for the capability and leave the implementation detail downstream.

---

## 8. Requirement sections and their abstraction boundary

This contract does not itself change the deterministic Standard Requirement document schema. `RW-R01` owns any schema change.

Until then, interpret existing semantic sections under these boundaries:

### Requirement

The normative WHAT: capability, outcome, observable behavior, constraint, or invariant that must be true.

### Detailed Behavior

Only behavior needed to interpret the normative WHAT correctly.

Allowed examples:

- lifecycle behavior visible in system state;
- conditions under which the obligation applies;
- meaningful success/failure outcomes;
- externally or system-observable rules needed to disambiguate the Requirement.

Not allowed:

- architecture;
- algorithm choice;
- module/function design;
- worker/process topology;
- implementation sequence;
- exact test implementation;
- deployment mechanics.

If no behavioral clarification is needed, the section must not be used as a place to preserve technical source detail.

### Rationale

Why the Requirement exists, only when established by the source. Rationale does not authorize new obligations.

### Acceptance / Verification

Observable evidence that would demonstrate the Requirement is satisfied.

It may describe states, outcomes, properties, boundaries, or externally observable scenarios.

It must not prescribe:

- test framework;
- exact unit/integration test code;
- mocks/fixtures;
- internal function calls;
- a specific technical verification path unless the source explicitly mandates it.

### Constraints & Edge Cases

Only product/system boundaries that remain meaningful regardless of valid implementation, plus explicitly source-mandated technical constraints.

Implementation-specific corner cases discovered because of a chosen design belong downstream.

### Non-Goals

Explicit product/system scope exclusions. Do not use Non-Goals as a dump for every implementation alternative not selected.

### Open Questions

Unresolved source decisions that affect WHAT must be true.

An unresolved HOW question belongs to Technical Solution Architecture, not the Requirement, unless resolving it could materially change product intent.

---

## 9. Product questions versus architecture questions

Use the following distinction when an unresolved point is discovered.

### Product / Requirement question

A question whose answer can change what outcome, capability, behavior, constraint, or invariant the system must provide.

Examples:

- What should the user observe when automated processing fails repeatedly?
- Is an operator allowed to override this decision?
- Which external behavior is required when capacity is exhausted?

Keep these visible in Requirements until answered.

### Architecture question

A question about how to implement an already understood obligation without changing its meaning.

Examples:

- Which event-delivery mechanism observes a state change?
- Which library performs serialization?
- Which persistence technology stores worker state?
- Which process model runs background work?

Do not promote these to missing Requirement content merely because they are unanswered.

---

## 10. Acceptance versus test implementation

Requirement-level Acceptance answers:

> What observable evidence would convince us that this Requirement is satisfied?

Task/test implementation answers:

> What exact test code, fixture, command, environment, or procedure will we build/run to obtain that evidence for the chosen solution?

Example:

**Requirement Acceptance:**

> When a human sends a Ready Requirement back for rework, prior processing outcome is no longer presented as the result of the new processing cycle, and the new cycle exposes its own eventual success or failure.

**Downstream test implementation:**

> Create fixture X, mutate field Y through adapter Z, run worker Q, and assert database field W equals enum V.

Only the first belongs in the Requirement.

---

## 11. Source preservation and non-invention

Processors and reviewers may clarify wording but must not create new product semantics to make a Requirement appear complete or testable.

When the source does not establish an answer:

- preserve the gap if it is a Requirement-level product question;
- leave it to Technical Architecture if it is a HOW decision;
- never import an answer from the current implementation merely because code already behaves one way;
- never treat another non-Applied candidate as authority over source intent.

An existing implementation is evidence about current behavior, not proof of desired behavior.

---

## 12. Decomposition rules

When deriving Standard Requirement candidates from RAW source:

1. Identify the meaningful capabilities, outcomes, observable behaviors, constraints, and invariants.
2. Separate genuinely independent obligations.
3. Keep technical implementation detail as context unless source mandates it.
4. Do not create one Requirement per implementation detail, field, test case, or source bullet.
5. Do not merge independent obligations merely because they share a source section or implementation.
6. Preserve product-level open questions without answering them.
7. Leave architecture-level questions downstream.
8. Candidate count is an outcome of the source semantics, never a target metric.

---

## 13. Analysis and review rules

Standard Process and Standard Review must evaluate abstraction correctness in addition to the existing quality dimensions.

They must be able to flag:

- implementation detail presented as Requirement truth;
- architecture disguised as a Requirement;
- Task/test mechanics disguised as Requirement Acceptance;
- over-fragmentation of one meaningful capability;
- genuine non-atomic product obligations;
- missing product constraints actually established by the source;
- invented product semantics;
- product questions incorrectly resolved as architecture assumptions.

They must **not** penalize a valid Requirement merely because it lacks:

- technology choices;
- module design;
- algorithm choice;
- internal interface shape;
- exact test design;
- deployment mechanics;
- answers to architecture-only questions.

---

## 14. Relationship to categories

This contract preserves the current category distinction.

### Functional

A required capability, behavior, or outcome.

### Non-functional

A required quality or operating property such as performance, reliability, security, privacy, scalability, usability, or recoverability when that property is part of what the delivered system must satisfy.

### Constraint

A mandatory boundary on valid solutions or operation.

A Constraint is not a license to promote every technical implementation decision into a Requirement. The source-mandated-mechanism rule still applies.

---

## 15. Worked classification examples

### Example 1 — automated lifecycle processing

**Requirement:**

> After the human authorizes RAW processing, Standard Requirement candidates proceed through machine-owned processing and review until the Ready human decision boundary without requiring one manual command per candidate.

**Architecture:**

> Observe Fibery state changes through the selected trigger mechanism and dispatch the matching worker.

**Task:**

> Implement the trigger adapter and dispatcher mapping for RAW/Standard states.

**Why:** The Requirement defines user-visible workflow and authority. Trigger and dispatcher design are HOW.

---

### Example 2 — processing status

**Requirement:**

> A Requirement exposes the outcome of its current automated processing cycle separately from lifecycle State, and starting a new cycle resets the previous processing outcome.

**Architecture:**

> Represent processing outcome using the selected Fibery field and state-update rules.

**Task:**

> Add the field mapping, reset/update logic, and tests for success/failure/rework cycles.

**Why:** Visibility/reset semantics are required behavior. Field name and code are implementation.

---

### Example 3 — project bootstrap

**Requirement:**

> The user can prepare a new project for SDLC participation through one explicit project-setup action, and rerunning setup does not silently duplicate the project or overwrite valid existing state.

**Architecture:**

> Define the bootstrap composition, project template, local descriptor, and calls to deterministic project/requirement primitives.

**Task:**

> Implement the bootstrap entrypoint and safe template-copy behavior.

**Why:** One-action setup and safe rerun are product behavior. File layout and call sequence are HOW.

---

### Example 4 — command injection protection

**Requirement:**

> Caller-controlled input must not be interpreted as executable command syntax during provider execution.

**Architecture:**

> Use a process invocation design that does not pass caller-controlled content through shell interpretation.

**Task:**

> Implement the selected invocation path and verification cases.

**Why:** The security property survives different technical implementations.

If the authoritative source explicitly says “provider commands must be executed as argv and never through a shell,” that exact mechanism may instead be retained as a Constraint under section 4.

---

### Example 5 — timeout

**Requirement:**

> Provider execution must stop within the configured execution time limit and report the timeout outcome to the caller.

**Architecture:**

> Select the timeout clock, cancellation model, process cleanup strategy, and failure mapping.

**Task:**

> Implement timeout enforcement and cleanup for the selected runtime adapter.

**Why:** The required outcome is bounded execution; exact timing/cleanup mechanics are architecture/task detail unless explicitly mandated by source.

---

### Example 6 — external request contract

**Requirement:**

> A consumer can submit the information required to request model execution and can correlate the returned result with that request.

If an exact externally consumed request schema is itself a committed product interface, its mandatory fields may be Requirement-level contract detail.

**Architecture:**

> Choose the internal data model, serialization and adapter representation that satisfy the external contract.

**Task:**

> Implement model/request types, parsing/validation and adapter mapping.

**Why:** External contract semantics may be WHAT; internal representation remains HOW.

---

### Example 7 — test coverage statement

**Not a standalone Requirement by default:**

> Add unit tests for timeout, malformed JSON, and retry behavior.

This is normally Delivery Planning / Task work.

A valid Requirement would instead state the behavior that those tests are meant to prove, if that behavior is required by the source.

---

### Example 8 — non-functional requirement

**Requirement:**

> Normal project initialization must complete without exposing stored credentials to project artifacts or user-visible diagnostics.

**Architecture:**

> Define secret boundaries and runtime/config handling.

**Task:**

> Implement redaction, environment filtering, and regression tests for the chosen design.

**Why:** Privacy/security outcome is WHAT; mechanisms are HOW.

---

## 16. Quick classification test

Before accepting content as a Standard Requirement, answer these questions:

1. **Meaning:** Does this describe an independently meaningful product/system obligation?
2. **WHAT:** Does it primarily say what must be true rather than how code must do it?
3. **Replacement:** Would it usually remain valid under a different correct implementation?
4. **Source:** Is the obligation established by source rather than inferred from current implementation or reviewer preference?
5. **Atomicity:** Can it be accepted/rejected as one meaningful obligation?
6. **Granularity:** Is it more than a technical field/function/test/task detail?
7. **Acceptance:** Does verification describe observable satisfaction rather than exact test implementation?
8. **Open questions:** Are unresolved product decisions preserved and architecture-only questions left downstream?

If questions 1, 2, 4, 5, 6, or 7 fail, the content must not be accepted as a valid Standard Requirement without correction.

Question 3 may fail only under the explicit source-mandated mechanism exception.

---

## 17. Relationship to downstream phases

This contract intentionally leaves real design work for downstream phases.

A healthy Requirements corpus should allow Technical Solution Architecture to decide, where relevant:

- technical structure and boundaries;
- technology choices;
- internal interfaces and data flows;
- integrations;
- storage/runtime/hosting mechanisms;
- security and recovery mechanisms;
- implementation targets;
- deployment/operational design.

Delivery Planning then converts the approved Requirements and Architecture into executable Epics, Stories, and Tasks, including solution-specific acceptance detail and Definition of Done.

If the Requirements corpus has already fixed most of those choices without explicit source mandate, the corpus is too implementation-specific.

---

## 18. Acceptance of RW-C01

`RW-C01` is satisfied when an independent reviewer confirms all of the following:

1. the WHAT / HOW / executable-decomposition / implementation boundary is explicit;
2. capability, outcome, observable behavior, business/system constraint, and invariant are all allowed Requirement forms;
3. implementation independence is the default;
4. source-mandated technical mechanism is the explicit exception;
5. field-level detail is Requirement content only when independently meaningful or part of an explicitly mandated external contract;
6. Requirement Acceptance is separated from test implementation;
7. source gaps and product-level open questions are preserved without invention;
8. architecture-only questions are not treated as missing Requirement content;
9. the contract prevents fragmentation caused solely by technical source detail;
10. the contract does not force genuinely independent obligations to be merged;
11. the eight examples can be classified without adding another rule;
12. nothing in this contract selects a particular technical architecture for SDLC.

Until that independent review is complete, this document remains `DRAFT` and `RW-C01` must not be marked `VERIFIED`.
