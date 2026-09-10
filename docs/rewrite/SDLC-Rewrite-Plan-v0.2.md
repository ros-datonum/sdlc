# SDLC Rewrite Plan v0.2

**Status:** DRAFT — HUMAN REVIEW REQUIRED  
**Implementation authorization:** NOT GRANTED  
**Target repository:** `ros-datonum/sdlc`  
**Implementation baseline:** `e15e59f8ed8d36f00e86e94dfca2b643215ab641`  
**Primary requirements input:** `SDLC-Corrected-Product-Functional-Requirements-v0.2.md`  
**Requirements input SHA-256:** `0eec181a2e80410d9bfe260d4e1fd83286245ba3e4e9647f715aa8c887b9d53c`

---

## 0. Purpose

This file is the execution source of truth for correcting the currently implemented SDLC foundation.

The rewrite has four goals:

1. restore the correct Requirement abstraction boundary: **Requirements define WHAT must be true; Technical Solution Architecture defines HOW; Delivery Planning and Tasks define solution-specific execution detail**;
2. restore the intended lifecycle control model: **human intent is expressed through explicit lifecycle state changes; machine-owned processing reacts to state and does not require the user to invoke every internal step manually**;
3. implement the previously agreed **project bootstrap + reusable project template + per-project SDLC context/configuration** around the existing deterministic Fibery primitives;
4. preserve proven infrastructure unless a work item below explicitly authorizes changing it.

This is a bounded rewrite of the current implemented foundation. It is **not** authorization to implement the remaining full SDLC lifecycle.

---

# 1. Authority and source precedence

When sources disagree, use this precedence:

1. **Explicit current human decision recorded in this plan after review.**
2. **`SDLC-Corrected-Product-Functional-Requirements-v0.2.md`** identified by the SHA-256 above.
3. **This frozen rewrite plan** after `PLAN_FROZEN`.
4. Final accepted architectural decisions from the Slice 0.4 baseline that were not later superseded.
5. Later verified corrections already merged into `main`:
   - Requirement `Type + State` are lifecycle placement;
   - Requirement-contained Documents are canonical;
   - physical `Raw/Draft/Approved` Folder semantics are retired;
   - Smart Folder + Context Views are human navigation only;
   - local OAuth model runtime and its verified isolation rules;
   - observed A1–A11 integrity/recovery fixes within their documented boundaries.
6. Current code, tests, and docs as evidence of current behavior only.

The current implementation does **not** become correct merely because tests pass.

---

# 2. Explicitly superseded / non-authoritative ideas

The following must not be reintroduced unless a new approved requirement explicitly requires them:

- generalized Claim / Evidence / Commitment subsystem inside SDLC;
- generalized authority-provenance subsystem;
- long-term Memory subsystem inside SDLC;
- EGDG control-surface governance machinery;
- ledger supremacy or a universal SDLC knowledge graph;
- standing Steward / Gate Authority / Reducer roles;
- swarm orchestration as a default;
- physical Fibery `Requirements/{Raw,Draft,Approved}` Document folders;
- a single generic Work Item database when Epic / Story / Task need distinct workflows;
- repository copies of canonical Fibery product Requirements;
- manual invocation of every internal requirement lifecycle capability as the normal user workflow;
- implementation-level detail being promoted to Standard Requirements merely because it appears in RAW source material.

---

# 3. Plan integrity contract

After the human changes this document to:

```text
Status: FROZEN
Implementation authorization: GRANTED
```

the normative content of this plan is frozen.

## 3.1 Fields an implementation agent MAY change

Inside an individual work item, Claude/Codex may change only:

- `Status`
- `Implementation Commit`
- `Implementation Evidence`
- `Blocker`
- `Execution Notes`

Allowed implementation status transitions:

```text
PLANNED
→ IMPLEMENTING
→ IMPLEMENTED_UNVERIFIED
```

or:

```text
PLANNED / IMPLEMENTING
→ BLOCKED
```

## 3.2 Fields an implementation agent MUST NOT change

Claude/Codex must not change:

- Purpose;
- source precedence;
- scope;
- work-item set;
- work-item IDs;
- dependencies;
- Required Change;
- Affected Areas;
- Must Preserve;
- Must Not;
- Acceptance Criteria;
- Verification Procedure;
- Human Decision Gates;
- completion criteria;
- any work item already marked `VERIFIED`.

Claude/Codex must not add a new work item.

## 3.3 Reviewer-owned fields

Only the human or the independent reviewer may change:

- `Verification`
- `Review Evidence`
- `Verified Commit`
- work-item status from `IMPLEMENTED_UNVERIFIED` to `VERIFIED` or `CHANGES_REQUIRED`.

## 3.4 Out-of-scope discoveries

If implementation exposes a missing decision, contradiction, or apparently useful improvement that is not authorized by the current work item:

1. do not implement it;
2. add one entry under `Proposed Change Requests`;
3. set the current item to `BLOCKED` only if the current item cannot truthfully complete without it;
4. otherwise finish the authorized item without the extra improvement.

A Proposed Change Request has no authority until the human explicitly accepts it and updates this plan.

---

# 4. Work-item status model

| Status | Meaning |
|---|---|
| `PLANNED` | frozen scope exists but work has not started |
| `BLOCKED` | cannot continue without a named unresolved decision/dependency |
| `IMPLEMENTING` | implementation agent is modifying only this item |
| `IMPLEMENTED_UNVERIFIED` | agent claims acceptance criteria are met and supplied evidence |
| `CHANGES_REQUIRED` | independent review found mismatch with this item |
| `VERIFIED` | independent review confirmed implementation matches this item |
| `CANCELLED` | human explicitly removed the item from the rewrite |

`IMPLEMENTED_UNVERIFIED` is **not done**.

---

# 5. Independent verification protocol

For every implementation item:

1. read this exact work item;
2. inspect the actual Git diff from the item's base to `Implementation Commit`;
3. read all changed files, not only the agent summary;
4. run or inspect the exact targeted tests listed by the item;
5. run the project regression suite when required;
6. inspect Fibery behavior when the item changes Fibery-visible behavior;
7. compare behavior against every Acceptance Criterion;
8. verify every `Must Preserve`;
9. verify every `Must Not`;
10. classify:
   - `VERIFIED`;
   - `CHANGES_REQUIRED`;
   - `BLOCKED`.

Passing tests alone cannot produce `VERIFIED`.

---

# 6. Rewrite boundary

## 6.1 In scope

This rewrite may change:

- canonical architecture/spec documentation needed to remove known contradictions;
- Requirement content standard and abstraction rules;
- RAW decomposition behavior;
- Standard Requirement normalization/analysis behavior;
- Standard Requirement review behavior;
- requirement lifecycle control ownership;
- requirement worker invocation/orchestration;
- normal-vs-admin CLI behavior;
- project bootstrap;
- reusable project template;
- per-project SDLC descriptor/context;
- tests and dogfood fixtures needed to verify the above;
- README/current-operating documentation.

## 6.2 Out of scope

Do not implement in this rewrite:

- UX/Product Design engine;
- Technical Solution Architecture engine;
- Delivery Planner / Backlog Builder;
- production Epic/Story/Task implementation workflow;
- coding/test/review GitHub automation;
- generalized Implementation Target adapters;
- System Verification engine;
- Release Preparation engine;
- Deployment engine;
- Post-Deploy Validation engine;
- generalized analytics;
- generalized distributed orchestration;
- long-term Memory;
- full requirement revision/supersession implementation unless a blocker proves it is necessary for this rewrite;
- migration/destruction of the existing AMR dogfood corpus before the explicit validation gate.

---

# 7. Protected existing behavior

The following are presumed correct and must be preserved unless a work item explicitly states otherwise:

- Fibery is the source of truth for project/requirement/design/planning/delivery state.
- Repositories contain code and code-native artifacts, not canonical Requirement mirrors.
- Requirement lifecycle placement uses Requirement `Type + State`.
- Requirement Root Documents are entity-contained; lifecycle correctness does not depend on `fibery/Folder`.
- Existing legacy Folder values are inert.
- Project initialization is deterministic and invokes no model.
- RAW requirement ingestion is deterministic and invokes no model.
- Requirement source preservation and RAW Source Fingerprint behavior.
- Model-backed processing uses locally authenticated runtime rules already verified by the project.
- No provider API key/OpenRouter fallback is introduced.
- Current model-execution privacy/isolation constraints.
- Fibery pacing, safe read retry behavior, write-uncertainty handling, and sanitized diagnostics.
- Root/child normative-tree binding where normative child Documents exist.
- current-format evidence binding and stale-input protection.
- immutable Process/Review history.
- explicit empty-Result recovery rules.
- human edits must not be silently overwritten by stale model output.
- current successful state must be recoverable after an interrupted run.
- applied relation writes are additive and must not silently rewrite peer Requirement content.
- a model finding is evidence for review, not autonomous authority to mutate product intent.

---

# 8. Human Decision Gates

All four decisions raised during the first review are now resolved by the human.
The normalized decisions below are normative for this rewrite. The quoted Human
Answer is retained for traceability; the Resolved Decision is the implementation
contract derived from it.

## HD-01 — Candidate auto-progression

**Question:** After RAW processing creates Standard Requirement candidates in Draft, should each candidate automatically enter machine-owned Standard Process/Review until the next human decision boundary, or wait for an explicit human transition?

**Human Answer:** "Option A"

**Resolved Decision:**

- Standard Requirement candidates created by an authorized RAW processing cycle automatically continue into Standard Process.
- No additional per-candidate human `Draft → Process` action is required.
- The authorization comes from the human action that started processing of the parent RAW Requirement.
- Automation must still stop at the next Standard Requirement human decision boundary (`Ready`).

**Status:** RESOLVED

---

## HD-02 — Process to Review chaining

**Question:** After Standard Process succeeds, should the system automatically move the Requirement to Review and invoke Review?

**Human Answer:** "Move automatically to Review and invoke Review"

**Resolved Decision:**

- Successful Standard Process automatically moves the Standard Requirement to `Review`.
- Standard Review is then invoked automatically.
- There is no human decision boundary between Standard Process and Standard Review.
- Successful Standard Review moves the Requirement to `Ready`.
- Automation stops at `Ready`; it may not approve or rework on behalf of the human.

**Status:** RESOLVED

---

## HD-03 — Existing AMR dogfood corpus handling

**Question:** How should the current 28 AMR Standard Requirements be handled after the corrected pipeline is verified?

**Human Answer:** "I would keep them temporarily until implementation is fixed, later on gradually remove all unneeded to keep data clean, so agents just have less items to process and spare computing and tokens and context"

**Resolved Decision:**

- Keep the current AMR Standard Requirements unchanged while the rewrite is being implemented and verified.
- Preserve a compact baseline record of the old corpus and its dogfood results before cleanup.
- After the corrected pipeline has been dogfooded successfully, compare the corrected corpus with the old corpus.
- Identify old AMR Standard Requirements that are no longer needed because they are obsolete, redundant, over-decomposed, or replaced by the corrected requirements.
- Remove those unnecessary items from the active Fibery corpus gradually and only as an explicit human-reviewed cleanup action.
- The purpose of cleanup is to keep active project data small and relevant so later agents do not spend context, tokens, and compute processing obsolete requirements.
- Cleanup of this dogfood corpus does not require implementing the general product-level Requirement revision/supersession workflow as part of this rewrite.

**Status:** RESOLVED

---

## HD-04 — Automated processing status visibility

**Question:** What user-visible behavior is required when automated processing succeeds, fails, or a ticket is moved back for another processing cycle?

**Human Answer:** "Ticket in Fibery should indicated if process was successful or not by changing a field or property. And it should be updated after each status change, e.g. If I move ticket from Review back to In Progress, I should reset processing status."

**Resolved Decision:**

- A processable Requirement in Fibery must expose a visible processing-status property separate from lifecycle State.
- When the Requirement enters or re-enters a state that requires a new machine-processing cycle, the previous processing result must be reset before the new cycle begins.
- The current cycle must visibly distinguish:
  - waiting/not yet processed for the current cycle;
  - processing in progress;
  - processing succeeded;
  - processing failed.
- A failed worker must leave a visible failed processing status and must not advance the lifecycle State as if processing succeeded.
- A successful worker must leave a visible successful processing outcome when it reaches a human boundary.
- If the next lifecycle state immediately starts another machine-owned worker, the processing status is reset for that new processing cycle.
- A human rework transition that sends an item back into machine processing resets the previous processing status.
- `RW-C04` must freeze the exact Fibery field name, allowed values, and reset/update rules before the routing implementation starts. Claude/Codex may not choose those details independently.

**Status:** RESOLVED

---

# 9. Execution sequence

```text
A. RE-FREEZE CONTRACTS
   ↓
B. REQUIREMENT ABSTRACTION REWRITE
   ↓
C. REQUIREMENT LIFECYCLE ORCHESTRATION
   ↓
D. PROJECT BOOTSTRAP
   ↓
E. CLEAN DOGFOOD / VERIFICATION
   ↓
F. DOCUMENTATION FREEZE
```

Implementation items in a later block must not start until all prerequisite items from earlier blocks are `VERIFIED`, except where an item explicitly states otherwise.

---

# BLOCK A — RE-FREEZE CONTRACTS

These items are **human/reviewer authored**. Claude/Codex may not make architectural decisions in this block unless explicitly asked to draft text from already frozen decisions.

---

## RW-C01 — Freeze Standard Requirement abstraction v0.2

**Status:** PLANNED  
**Owner:** Human + independent design reviewer  
**Implementation Actor:** NONE  
**Depends On:** none

### Required Change

Create a canonical Requirement abstraction contract that makes these boundaries explicit:

```text
Requirement
= WHAT must be true

Technical Solution Architecture
= HOW the approved Requirement will be satisfied

Delivery Planning
= solution-specific executable decomposition

Task implementation
= concrete code/configuration/test work
```

The contract must define:

- allowed Requirement content:
  - capability;
  - outcome;
  - observable behavior;
  - business/system constraint;
  - invariant;
- implementation independence as the default;
- source-mandated technical mechanism as the only exception;
- field-level details are Requirements only when independently meaningful product/system obligations;
- Requirement Acceptance describes observable satisfaction, not test implementation;
- source gaps remain open;
- no product invention;
- no fragmentation solely because a source has many technical details;
- no merging of genuinely independent obligations;
- examples of `Requirement vs Architecture vs Task`.

### Affected Areas

At minimum:

- new or revised canonical Requirement-standard document;
- `docs/architecture/SDLC-MVP-v0.4-Frozen-Architecture.md` cross-reference if necessary.

### Must Preserve

- Functional / Non-functional / Constraint distinction unless separately changed by human decision.
- Fibery ownership boundary.
- Requirements analysis for completeness, ambiguity, conflict, duplication, testability, dependencies and impact.

### Must Not

- prescribe model prompts;
- prescribe parser code;
- prescribe test framework;
- choose trigger transport;
- define Technical Architecture for SDLC itself.

### Acceptance Criteria

1. A reviewer can classify at least five examples as Requirement/Architecture/Task using the contract without inventing a new rule.
2. The contract explicitly rejects implementation leakage.
3. The contract explicitly preserves source-mandated technical constraints.
4. The contract explicitly distinguishes Requirement acceptance evidence from test implementation.
5. Nothing in the contract requires one particular technical architecture for SDLC.

### Verification

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-C02 — Freeze corrected Requirement lifecycle ownership

**Status:** PLANNED  
**Owner:** Human + independent design reviewer  
**Implementation Actor:** NONE  
**Depends On:** `RW-C01`

### Required Change

Create/revise the canonical Requirement lifecycle contract so that:

- human-owned lifecycle decisions are expressed through explicit Requirement State changes;
- machine-owned work reacts to lifecycle state;
- a user does not need to invoke each internal processor/reviewer/apply worker manually during normal operation;
- automation cannot manufacture a human approval/rework decision;
- an authorized assistant may make the same State change only after explicit human instruction;
- internal/admin commands do not become a second independent approval authority.

Confirmed Requirement lifecycle ownership:

```text
RAW create → Draft                    SYSTEM
RAW Draft → Process                   HUMAN — starts the RAW processing cycle
RAW Process → Review                  SYSTEM after successful RAW processing

Standard candidate create → Draft     SYSTEM
Standard Draft → Process              SYSTEM — inherited from the authorized parent RAW cycle
Standard Process → Review             SYSTEM after successful Standard Process
Standard Review → Ready               SYSTEM after successful Standard Review

Standard Ready → Process              HUMAN — REWORK
Standard Ready → Apply                HUMAN — APPROVE
Standard Apply → Applied              SYSTEM after successful deterministic Apply
```

The parent RAW processing authorization is sufficient to carry newly created Standard candidates through Standard Process and Standard Review. Automation stops at each Standard Requirement's `Ready` boundary.

### Affected Areas

- `docs/architecture/Requirement-Lifecycle-v0.1-Checkpoint.md`
- `docs/specs/Standard-Requirement-Ready-Spec-v0.1.md`
- `docs/specs/Standard-Requirement-Apply-Spec-v0.1.md`
- architecture overview as needed.

### Must Preserve

- evidence revalidation before canonical mutation;
- stale reviewed state must not be applied;
- human edits after review invalidate stale evidence;
- Apply remains deterministic and model-free.

### Must Not

- add a new approval artifact merely to replace State;
- give a model authority to approve;
- choose the state-trigger transport.

### Acceptance Criteria

1. `Ready → Apply` itself is documented as the durable human approval signal.
2. `Ready → Process` itself is documented as human rework intent.
3. Normal user flow does not require a separate `approve` capability to create authority.
4. Apply still revalidates the exact reviewed state.
5. Admin/recovery invocation is explicitly distinguished from normal lifecycle control.
6. Standard candidates created by an authorized RAW cycle require no per-candidate human activation before Process/Review.
7. Standard Process automatically continues into Standard Review and stops at Ready.

### Verification

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-C03 — Freeze project bootstrap contract

**Status:** PLANNED  
**Owner:** Human + independent design reviewer  
**Implementation Actor:** NONE  
**Depends On:** `RW-C01`

### Required Change

Freeze the already agreed bootstrap behavior:

- user starts project setup through one explicit action;
- setup can target the current directory or a user-selected directory;
- setup prepares the consumer project to participate in SDLC;
- setup uses a reusable project template;
- setup establishes the project-local SDLC descriptor/context;
- setup preserves user/global Claude/Codex authentication, model, permission and edit policies unless the human explicitly changes them;
- setup invokes the existing deterministic Fibery project initialization primitive;
- setup can ingest the initial exported RAW requirements through the existing deterministic requirement-add primitive;
- setup consumes the project context produced by `requirements-export`;
- rerun must not silently duplicate a Fibery Project or overwrite unrelated existing project files;
- partial setup must be reported truthfully.

### Already-agreed project-local artifacts

The contract must preserve the concept of:

- `.sdlc/project.yaml` as project execution/configuration descriptor, not Requirement storage;
- project-local AI/agent instructions/configuration;
- `project-context.md` generated from the same requirements-export session;
- reusable template content;
- no canonical product Requirement mirror in the repository.

Exact bootstrap command/script name may be frozen in this contract before implementation.

### Must Preserve

- existing inner `sdlc project init`;
- existing inner `sdlc project requirement add`;
- no model call in either deterministic primitive;
- no global setting override.

### Must Not

- merge project bootstrap into product Requirement canonical storage;
- regenerate product requirements inside bootstrap;
- make the template itself the source of product truth.

### Acceptance Criteria

1. Contract defines one normal setup journey from exported context to ready project.
2. It clearly separates outer bootstrap from inner Fibery `project init`.
3. It clearly states how initial RAW input enters the project.
4. Rerun/partial behavior is explicit.
5. No implementation algorithm is left for Claude to invent during the later bootstrap code item.

### Verification

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-C04 — Freeze state-trigger worker contract

**Status:** PLANNED  
**Owner:** Human + independent design reviewer  
**Implementation Actor:** NONE  
**Depends On:** `RW-C02`

### Required Change

Define the exact worker-routing contract for the currently implemented Requirement lifecycle only.

It must define:

- which Requirement `Type + State` combinations request which worker;
- which transitions are human-owned;
- which transitions are worker-owned;
- success output/state for each worker;
- no-op/idempotent behavior for repeated observation of already-completed work;
- visible failure behavior;
- the exact Fibery processing-status field name and allowed values for the four required semantics: waiting/not-yet-processed, processing, succeeded, failed;
- reset rules when a Requirement enters or re-enters a machine-processed state;
- status-update rules when one machine-owned stage chains directly into another;
- how existing recovery/admin capabilities relate to normal state-triggered processing;
- that worker routing has no independent authority to alter product intent.

### Must Preserve

- current model runtime boundary;
- current evidence/history behavior;
- current deterministic Apply behavior;
- current `Type + State` lifecycle placement.

### Must Not

- implement downstream architecture/planning/development routing;
- introduce generalized orchestration;
- choose distributed infrastructure not required by this bounded Requirement flow;
- treat a State observation as permission to cross the next human decision boundary.

### Acceptance Criteria

1. Every current Requirement lifecycle State has exactly one defined ownership meaning.
2. Every machine-owned worker entry has an unambiguous State predicate.
3. Repeated observation semantics are explicit.
4. Human boundaries cannot be crossed by chaining.
5. Claude can implement the router without deciding lifecycle semantics.
6. The exact processing-status property contract is frozen and covers reset, processing, success, and failure.
7. RAW-created Standard candidates automatically reach Standard Process/Review without per-candidate human activation.
8. Standard Process automatically chains into Standard Review and automation stops at Ready.

### Verification

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

# BLOCK B — REQUIREMENT ABSTRACTION REWRITE

No implementation item in this block starts before `RW-C01 = VERIFIED`.

---

## RW-R01 — Update Standard Requirement Document Schema

**Status:** PLANNED  
**Owner:** Implementation Agent  
**Depends On:** `RW-C01`

### Required Change

Update the Standard Requirement document/schema contract to enforce the v0.2 abstraction boundary.

Expected semantic sections remain only where useful:

- Requirement;
- externally observable / interpretation behavior only;
- Rationale;
- Acceptance / Verification at Requirement level;
- Constraints / Edge Cases at Requirement level;
- Non-Goals;
- Open Questions.

If `Detailed Behavior` remains, its definition must explicitly forbid solution design and implementation mechanics.

### Affected Areas

At minimum:

- `docs/specs/Standard-Requirement-Document-Schema-v0.1.md`
- code that renders/parses Standard Requirement documents;
- schema-specific tests.

### Must Preserve

- deterministic document structure;
- empty/not-specified behavior where source does not establish content;
- Requirement ID/title binding;
- existing Root/child normative tree behavior.

### Must Not

- add architecture sections to Requirement documents;
- add Task-level implementation steps;
- add test-code instructions.

### Acceptance Criteria

1. Schema text itself states the WHAT/HOW boundary.
2. A Requirement can omit sections not established by source.
3. `Detailed Behavior`, if retained, cannot legitimately contain architecture or task mechanics under the schema.
4. Existing normative-tree/fingerprint machinery still accepts valid documents.
5. Tests cover at least one valid product-level Requirement and one rejected/flagged implementation-leaking example.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** —  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-R02 — Correct RAW decomposition contract

**Status:** PLANNED  
**Owner:** Implementation Agent  
**Depends On:** `RW-R01`

### Required Change

Change RAW decomposition so Standard candidates are created at Requirement level, not delivery-implementation level.

The model instructions and deterministic output contract must enforce:

- one candidate = one independently meaningful required capability/outcome/constraint/invariant;
- do not split every technical statement;
- do not create candidates merely for implementation components/mechanisms;
- source-mandated mechanisms may remain constraints;
- acceptance is observable satisfaction, not test implementation;
- source gaps remain gaps;
- technical source detail may remain source context without becoming a candidate;
- comparison findings remain observations only.

### Affected Areas

At minimum inspect/change as required:

- `src/sdlc/raw_prompt.py`
- `src/sdlc/raw_processing.py`
- `src/sdlc/raw_processor.py`
- `docs/specs/RAW-Requirement-Processor-Decision-v0.1.md`
- `docs/specs/RAW-Processor-Processing-Result-v0.1.md`
- RAW processor tests.

### Must Preserve

- RAW source preservation;
- zero/one/many candidate behavior;
- candidate categories;
- peer comparison findings;
- no mutation of existing peer Requirements;
- model output remains bounded/structured;
- no Fibery write before output validation;
- recovery/idempotency behavior.

### Must Not

- encode an expected candidate count;
- force one candidate per paragraph/field;
- solve open product questions;
- turn architecture/test mechanics into Requirements to improve "testability".

### Acceptance Criteria

1. Fixture with one capability plus several implementation details produces no candidate solely for those details.
2. Fixture with two independent product obligations can still produce two candidates.
3. Fixture with an explicitly mandated technical constraint preserves that constraint.
4. Fixture with an unresolved source decision preserves it as open.
5. Current comparison finding behavior still works.
6. No regression in RAW source binding/recovery tests.
7. Model prompt contains an explicit anti-implementation-leakage rule.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** —  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-R03 — Correct Standard Process normalization and analysis

**Status:** PLANNED  
**Owner:** Implementation Agent  
**Depends On:** `RW-R01`, `RW-R02`

### Required Change

Change Standard Process so normalization improves clarity **without pulling downstream design into the Requirement**.

It must:

- preserve the Requirement-level obligation;
- detect implementation leakage;
- detect when a supposed Requirement is actually architecture/task detail;
- keep source gaps open;
- avoid manufacturing acceptance criteria from implementation assumptions;
- still analyze completeness, clarity, atomicity, testability, consistency, peer conflict/duplication/change/supersession, and candidate relations.

### Affected Areas

At minimum:

- `src/sdlc/standard_prompt.py`
- `src/sdlc/standard_analysis.py`
- `src/sdlc/standard_processor.py`
- `docs/specs/Standard-Requirement-Process-Spec-v0.1.md`
- Standard Process tests.

### Must Preserve

- current explicit resume/new-iteration semantics;
- concurrent human-edit protection;
- current-format Result evidence;
- comparison context;
- relation proposals remain non-canonical;
- findings do not mutate peer Requirements.

### Must Not

- split a Requirement autonomously during Standard Process;
- create new Requirements;
- rewrite product intent to make a Requirement easier to implement;
- convert a missing architecture decision into a product Requirement.

### Acceptance Criteria

1. An implementation-leaking candidate receives a clear finding instead of being normalized into more implementation detail.
2. A valid high-level Requirement remains high-level after normalization.
3. Source-mandated constraints remain intact.
4. Open product decisions are not invented.
5. Existing stale-input, resume, iteration, and recovery tests remain green.
6. New tests cover WHAT→HOW leakage detection.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** —  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-R04 — Correct Standard Review abstraction checks

**Status:** PLANNED  
**Owner:** Implementation Agent  
**Depends On:** `RW-R03`

### Required Change

Update Review so it evaluates Requirement quality at the corrected abstraction level.

Review must be able to confirm or flag:

- implementation leakage;
- architecture disguised as Requirement;
- Task/test mechanics disguised as Requirement acceptance;
- unjustified fragmentation;
- genuinely non-atomic product obligations;
- source invention;
- ambiguity/incompleteness;
- conflicts/duplicates/change/supersession;
- dependency/impact proposals.

### Affected Areas

At minimum:

- `src/sdlc/review_prompt.py`
- `src/sdlc/standard_review.py`
- `src/sdlc/standard_reviewer.py`
- `docs/specs/Standard-Requirement-Review-Spec-v0.1.md`
- review tests.

### Must Preserve

- independent review behavior;
- Process finding verification;
- strict self-vs-cross finding reference contract;
- reviewed tree/fingerprint binding;
- verdict is evidence for human decision, not autonomous approval;
- no Requirement mutation by reviewer.

### Must Not

- demand technical design merely to produce PASS;
- classify an intentional architecture open question as missing Requirement content unless the source requires the product decision;
- rewrite the Requirement.

### Acceptance Criteria

1. Review can explicitly flag architecture/task leakage.
2. Review does not penalize a valid Requirement for lacking downstream implementation choices.
3. Review still catches genuine source gaps and contradictions.
4. Existing finding-reference regression remains green.
5. Review remains model-output-only before deterministic validation/persistence.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** —  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-R05 — Build Requirement abstraction regression corpus

**Status:** PLANNED  
**Owner:** Implementation Agent  
**Depends On:** `RW-R02`, `RW-R03`, `RW-R04`

### Required Change

Create a deterministic regression corpus that tests the abstraction boundary independently of the live AMR project.

The corpus must include cases for:

1. one product capability with multiple technical implementation details;
2. two truly independent obligations in one RAW source;
3. an explicit source-mandated technical constraint;
4. a technical suggestion that is not a mandatory Requirement;
5. acceptance evidence vs exact test implementation;
6. an unresolved product decision;
7. an unresolved architecture decision;
8. field-level detail that is not independently meaningful;
9. a legitimate non-functional Requirement;
10. a legitimate system constraint.

### Affected Areas

Tests/fixtures only, plus supporting documentation if needed.

### Must Preserve

- no expected "ideal number" of candidates;
- semantic properties, not exact model prose, are the pass condition where model output is involved.

### Must Not

- use the live AMR corpus as mutable test state;
- encode current wrong 19/9 candidate counts as desired output.

### Acceptance Criteria

1. All ten classes have explicit expected classification/properties.
2. Regression fails when implementation detail is promoted to Requirement incorrectly.
3. Regression fails when a source-mandated constraint is dropped.
4. Regression fails when open product questions are invented.
5. Regression is usable by an independent reviewer to verify future prompt changes.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** —  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

# BLOCK C — REQUIREMENT LIFECYCLE ORCHESTRATION

No code item in this block starts before `RW-C02` and `RW-C04` are `VERIFIED`.

---

## RW-O01 — Separate normal lifecycle control from admin CLI invocation

**Status:** PLANNED  
**Owner:** Implementation Agent  
**Depends On:** `RW-C02`

### Required Change

Make the product contract clear in code/docs:

- normal user approval/rework intent is a Fibery Requirement State transition;
- internal processing commands are not the normal lifecycle UX;
- existing CLI worker commands may remain for development, recovery, diagnosis, or explicit admin operation;
- an admin command must not create a second semantic source of approval authority;
- `Ready → Apply` and `Ready → Process` remain the human signals.

### Affected Areas

At minimum inspect/change as required:

- `src/sdlc/cli.py`
- `src/sdlc/ready_decision.py`
- Ready/Apply specs
- CLI tests
- README.

### Must Preserve

- useful validation functions may be reused;
- admin/recovery capability remains possible where needed;
- Apply still refuses stale reviewed state.

### Must Not

- delete recovery/debug tooling merely because it is not normal UX;
- make CLI approval mandatory for state-triggered Apply;
- auto-approve based on Review verdict.

### Acceptance Criteria

1. A direct valid human `Ready → Apply` state change can be handled by the normal system path without first invoking `sdlc ... approve`.
2. A direct valid human `Ready → Process` state change can be handled as rework intent.
3. Any remaining `approve/rework` CLI behavior is explicitly admin/compatibility behavior and cannot bypass normal evidence rules.
4. Existing validation logic is reused or deliberately replaced with equivalent verified behavior.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** —  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-O02 — Implement bounded Requirement worker dispatcher

**Status:** PLANNED  
**Owner:** Implementation Agent  
**Depends On:** `RW-C04`, `RW-O01`

### Required Change

Implement one bounded dispatch layer for the Requirement lifecycle defined by `RW-C04`.

The dispatcher must:

- resolve the Requirement's current `Type + State`;
- invoke only the worker authorized for that combination;
- invoke no worker for a human decision state that has not yet been decided;
- treat already-completed durable work idempotently;
- return a clear result for unsupported/no-op states;
- use existing processing/apply functions rather than duplicating their internal logic.

### Affected Areas

Exact module/file location must be the one frozen in `RW-C04` before this item becomes READY.

### Must Preserve

- current worker precondition checks remain defense in depth;
- dispatcher cannot weaken worker validation;
- no model/runtime change.

### Must Not

- contain Requirement business logic duplicated from processors;
- implement scheduling infrastructure;
- route downstream Architecture/Task lifecycle.

### Acceptance Criteria

1. Each authorized `Type + State` maps to exactly one current Requirement worker.
2. Human boundary states do not advance without the human-owned transition.
3. Re-dispatch after successful durable completion does not duplicate outputs.
4. Worker failure does not falsely advance state.
5. Unit tests cover every routing branch.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** —  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-O03 — Implement state-change trigger entrypoint

**Status:** BLOCKED  
**Owner:** Implementation Agent  
**Depends On:** `RW-O02`

### Blocker

Exact state-trigger contract and transport entrypoint must first be frozen by `RW-C04`.

### Required Change

Implement the bounded entrypoint that causes the Requirement dispatcher to run as a consequence of a relevant Fibery State change.

The technical transport/mechanism must come from the frozen `RW-C04` technical contract. Claude/Codex must not choose webhook vs polling vs another mechanism here.

### Must Preserve

- human Fibery State is source of lifecycle intent;
- state-trigger delivery may repeat without duplicate canonical outcomes;
- worker validation remains authoritative for whether work is actually safe to execute.

### Must Not

- add a generalized event platform;
- assume exactly-once delivery unless explicitly guaranteed by the chosen mechanism;
- let trigger receipt itself create human approval.

### Acceptance Criteria

1. Relevant state change causes the correct dispatcher invocation without a manual processor CLI command.
2. Irrelevant state change causes no worker mutation.
3. Duplicate/replayed trigger does not duplicate a successful durable outcome.
4. Failed worker execution does not falsely report lifecycle completion.
5. Trigger payload does not become trusted product truth when current Fibery state disagrees.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** `RW-C04`  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-O04 — Requirement lifecycle end-to-end automation test

**Status:** BLOCKED  
**Owner:** Implementation Agent  
**Depends On:** `RW-O03`

### Required Change

Add an end-to-end test of the corrected normal Requirement lifecycle using the frozen human/system transition ownership.

The test must cover at least:

- RAW Draft waiting for the appropriate human intent;
- RAW processing;
- Standard candidate creation;
- automatic candidate `Draft → Process` progression inherited from the authorized RAW cycle;
- Standard Process;
- automatic `Process → Review` chaining and Standard Review;
- stop at human Ready boundary;
- human REWORK path;
- human APPROVE/Apply path;
- deterministic Applied completion;
- duplicate/replayed automation event;
- stale human edit protection.

### Must Preserve

- no test depends on manually calling every internal CLI command as the normal flow.

### Acceptance Criteria

1. Normal flow demonstrates state-driven machine processing.
2. Human boundary is observable and cannot be crossed automatically.
3. Rework history is preserved.
4. Apply revalidates reviewed state.
5. Replay does not duplicate durable outputs.
6. Processing status resets on a new machine-processing cycle and visibly reports processing, success, or failure.
7. Failed processing does not falsely advance lifecycle State.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** `RW-O03`  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

# BLOCK D — PROJECT BOOTSTRAP

No bootstrap code starts before `RW-C03 = VERIFIED`.

---

## RW-B01 — Freeze reusable consumer project template contents

**Status:** PLANNED  
**Owner:** Human + independent design reviewer  
**Implementation Actor:** NONE  
**Depends On:** `RW-C03`

### Required Change

Freeze the exact reusable template file set before Claude copies/creates anything.

The template must cover only already-agreed project-local SDLC participation:

- `.sdlc/project.yaml`;
- project context produced by requirements-export;
- project-local Claude/Codex/agent guidance required by the SDLC;
- no embedded credentials;
- no forced model/auth/permission/edit-policy override;
- no canonical Requirement mirror.

Exact files, merge/copy behavior, placeholders, and optional files must be listed in this item before it becomes VERIFIED.

### Acceptance Criteria

1. Every template path is explicitly listed.
2. For every path, overwrite/merge/skip behavior is explicit.
3. No secret or user-global setting is included.
4. Claude can implement template creation without inventing another file.

### Verification

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-B02 — Implement reusable consumer project template

**Status:** BLOCKED  
**Owner:** Implementation Agent  
**Depends On:** `RW-B01`

### Blocker

`RW-B01` must define the exact template manifest.

### Required Change

Add exactly the template frozen in `RW-B01`.

### Must Preserve

- global/user Claude/Codex configuration remains in control where explicitly preserved by the contract;
- template is reusable across projects;
- no credentials;
- no canonical Requirements.

### Must Not

- add convenience files not named by `RW-B01`;
- modify the `sdlc` repository's own development agent configuration as a substitute for a consumer template.

### Acceptance Criteria

1. Template manifest equals `RW-B01`.
2. No undeclared template files exist.
3. Placeholder substitution points are explicit and tested.
4. No secrets or account-specific values exist.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** `RW-B01`  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-B03 — Implement project descriptor contract

**Status:** BLOCKED  
**Owner:** Implementation Agent  
**Depends On:** `RW-B01`

### Required Change

Implement the project-local descriptor exactly as frozen by `RW-C03/RW-B01`.

It must describe how the consumer repository participates in SDLC and must not own product Requirements.

At minimum the frozen descriptor is expected to cover the previously agreed groups:

- project identity;
- Fibery project/workspace mappings needed by SDLC;
- repository identity/policy;
- branch/worktree/merge policy where applicable;
- deterministic project checks;
- standards profile/extensions.

Exact keys and optionality must be frozen before implementation.

### Must Not

- store credentials;
- store canonical product Requirement prose;
- override higher-precedence explicit human or approved requirement intent.

### Acceptance Criteria

1. Schema/validation rejects missing mandatory identity/config.
2. Descriptor can be generated for a new project from bootstrap inputs.
3. Rerun produces semantically stable output for unchanged inputs.
4. No credentials/canonical Requirements appear in descriptor.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** `RW-B01`  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-B04 — Implement one outer project bootstrap action

**Status:** BLOCKED  
**Owner:** Implementation Agent  
**Depends On:** `RW-B02`, `RW-B03`, `RW-C03`

### Required Change

Implement the one user-facing project-setup action frozen in `RW-C03`.

The bootstrap must perform only the frozen sequence:

1. resolve target/current directory;
2. safely apply the reusable project template;
3. materialize project-local descriptor/context from supplied setup inputs;
4. invoke the existing deterministic Fibery project-init primitive;
5. when an initial RAW export is supplied, invoke the existing deterministic requirement-add primitive;
6. validate the resulting setup;
7. report complete/partial/already-existing outcomes truthfully.

### Must Preserve

- `project_init.py` remains the inner deterministic Fibery Project primitive unless a specific verified defect requires change;
- `requirement_add.py` remains the inner deterministic RAW ingestion primitive unless a specific verified defect requires change;
- no model is needed merely to initialize Fibery or ingest already-exported RAW source;
- unrelated existing consumer-project files are not silently overwritten.

### Must Not

- re-run requirements interpretation during bootstrap;
- invoke RAW/Standard processing merely because setup completed unless a separately authorized lifecycle State requests it;
- duplicate an existing Fibery Project;
- create hidden local-only lifecycle truth.

### Acceptance Criteria

1. Empty/new target can be initialized through one user action.
2. Current directory and explicit target-directory modes both work if frozen in `RW-C03`.
3. Existing unrelated files follow the explicit merge/skip/error policy.
4. Existing Fibery Project rerun is idempotent/non-destructive.
5. Initial RAW requirement is added exactly once when supplied.
6. Project context is present as defined by the template contract.
7. Partial failure is distinguishable from full success.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** `RW-B02`, `RW-B03`, `RW-C03`  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-B05 — Bootstrap end-to-end test on disposable project

**Status:** BLOCKED  
**Owner:** Implementation Agent  
**Depends On:** `RW-B04`

### Required Change

Create an end-to-end bootstrap verification that proves the normal user setup behavior on a disposable project/environment.

### Acceptance Criteria

The verification must demonstrate:

1. one setup action creates a usable local project structure;
2. project descriptor/context matches frozen contract;
3. Fibery Project exists exactly once;
4. initial RAW Requirement exists exactly once when supplied;
5. rerun is safe;
6. global/user model/auth/edit settings are not overwritten;
7. no credentials are written to project files;
8. failure produces a truthful partial/error result;
9. no Requirement processing starts without the lifecycle state that authorizes it.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** `RW-B04`  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

# BLOCK E — CLEAN DOGFOOD / VALIDATION

---

## RW-V01 — Preserve old AMR corpus as baseline evidence

**Status:** PLANNED  
**Owner:** Human + independent reviewer  
**Implementation Actor:** NONE  
**Depends On:** none

### Required Change

Before any live AMR mutation:

- record the two RAW inputs used in dogfood:
  - `AMR-RAW-0053`;
  - `AMR-RAW-0077`;
- record old decomposition outcome:
  - first RAW → 19 Standard Requirements;
  - second RAW → 9 Standard Requirements;
- record that this is **baseline evidence, not the target candidate count**;
- preserve the old corpus unchanged through corrected-pipeline implementation and dogfood;
- create a compact baseline record sufficient to compare the old and corrected corpora without keeping obsolete old Standard Requirements permanently active.

### Acceptance Criteria

1. Baseline inputs are reproducibly identifiable.
2. No live AMR Standard Requirement is deleted or rewritten.
3. The comparison criteria are semantic, not "produce fewer Requirements."

### Verification

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-V02 — Re-run the two AMR RAW sources through corrected Requirement pipeline

**Status:** BLOCKED  
**Owner:** Human-operated dogfood + independent reviewer  
**Implementation Actor:** System under test; Claude/Codex do not make human approvals  
**Depends On:** `RW-R05`, `RW-O04`, `RW-V01`

### Required Change

Run both real RAW sources through the corrected pipeline in an isolated/disposable corpus or other human-approved non-destructive setup.

### Required evaluation

For every produced Standard Requirement ask:

1. Is it independently meaningful as WHAT must be true?
2. Could multiple valid technical implementations satisfy it unless the source mandates one?
3. Did implementation mechanics remain downstream?
4. Did acceptance remain observable rather than test-code-specific?
5. Were source-mandated constraints preserved?
6. Were product open questions preserved?
7. Did the system avoid unnecessary fragmentation?
8. Did it avoid collapsing independent product obligations?
9. Did Process/Review add useful quality evidence without demanding architecture detail?

### Must Not

- approve Requirements automatically;
- mutate old AMR Applied Requirements;
- use candidate count alone as pass/fail.

### Acceptance Criteria

1. No confirmed implementation-leakage blocker remains.
2. No source-mandated obligation is lost merely because it is technical.
3. Reviewer can explain the boundary of every candidate without ad hoc exceptions.
4. Technical Solution Architecture would still have meaningful HOW decisions left.
5. Lifecycle works through the state-driven normal path.
6. Dogfood produces no new BLOCKING lifecycle defect.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** `RW-R05`, `RW-O04`, `RW-V01`  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-V03 — Human-reviewed cleanup of obsolete AMR dogfood requirements

**Status:** BLOCKED  
**Owner:** Human-operated cleanup + independent reviewer  
**Implementation Actor:** NONE unless a bounded cleanup helper is explicitly authorized  
**Depends On:** `RW-V02`

### Required Change

After `RW-V02` verifies the corrected Requirement pipeline:

1. compare each old AMR Standard Requirement against the corrected corpus;
2. classify whether the old item is still needed, obsolete, redundant, over-decomposed, or replaced;
3. produce an explicit cleanup set for human review;
4. remove only human-approved unnecessary items from the active Fibery Standard Requirement corpus;
5. perform cleanup gradually so each removal can be checked;
6. retain the compact baseline evidence created by `RW-V01` so the dogfood history remains inspectable without forcing active agents to process obsolete Requirement entities.

### Must Preserve

- both original RAW source Requirements;
- corrected active Standard Requirements;
- enough baseline evidence to explain the old 19 + 9 decomposition and why cleanup occurred;
- no automatic deletion based solely on model judgment.

### Must Not

- delete old requirements before corrected dogfood is verified;
- delete an item merely because the new corpus has fewer items;
- treat cleanup as implementation of the general product-level revision/supersession workflow;
- leave obsolete active Requirements merely to preserve history when equivalent compact baseline evidence has already been recorded and the human approved cleanup.

### Acceptance Criteria

1. Every removed old AMR Requirement has an explicit human-reviewed cleanup classification.
2. No corrected Requirement needed by the project is removed.
3. Both RAW sources remain intact.
4. The active AMR Requirement corpus contains only requirements judged relevant after correction.
5. Baseline evidence remains available outside the active Requirement set.
6. Cleanup reduces obsolete active context without losing the ability to audit why the rewrite changed the corpus.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

# BLOCK F — FINAL DOCUMENTATION FREEZE

---

## RW-D01 — Reconcile canonical docs and README

**Status:** BLOCKED  
**Owner:** Implementation Agent  
**Depends On:** all implementation items in Blocks B–D `VERIFIED`, `RW-V03`

### Required Change

Update repository documentation so it describes the verified system, not obsolete implementation history.

At minimum reconcile:

- `README.md`;
- `docs/architecture/SDLC-MVP-v0.4-Frozen-Architecture.md` or its explicitly versioned successor;
- Requirement lifecycle checkpoint;
- Standard Requirement Process/Review/Ready/Apply specs;
- Project Init / Requirement Add docs only where the outer bootstrap changes how they are positioned;
- any obsolete text claiming only three implemented capabilities;
- any text teaching manual worker CLI invocation as the normal production Requirement flow.

### Must Preserve

- historical design documents may remain if clearly marked superseded/history;
- current supported admin/recovery commands remain documented as such.

### Must Not

- rewrite history to pretend the wrong implementation never existed;
- describe unimplemented downstream Architecture/Planning/Development engines as complete.

### Acceptance Criteria

1. README and canonical specs agree on current normal user flow.
2. Requirement WHAT/HOW boundary is explicit.
3. Fibery State is documented as human lifecycle control.
4. Worker automation is documented only to the level actually verified.
5. Bootstrap docs match verified implementation.
6. No current doc points to physical Folder lifecycle semantics.
7. No current doc claims unimplemented downstream phases are implemented.

### Implementation Record

**Implementation Commit:** —  
**Implementation Evidence:** —  
**Blocker:** prerequisite verification  
**Execution Notes:** —

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

# 10. External dependency — requirements-export skill

The global `requirements-export` skill is outside this repository, but the corrected project flow depends on it.

Before the final bootstrap/dogfood gate, verify that the active skill follows the same boundary:

- RAW requirements export contains business/product/system behavior and constraints;
- it does not promote technical implementation decisions into product Requirements;
- technical implementation context is not mislabeled as Requirement truth;
- it can produce the project context artifact agreed for bootstrap without duplicating canonical Fibery Requirements;
- it does not invent requirements from implementation discussion.

If the installed skill does not satisfy this, update it as a separate explicitly authorized artifact. Do not silently change it from a repository implementation work item.

---

# 11. Proposed Change Requests

Implementation agents append proposals here only when required by section 3.4.

Format:

```text
CR-XXX
Discovered In: RW-...
Observation:
Why current item cannot/should not absorb it:
Proposed decision:
Blocking: YES | NO
Status: PROPOSED
```

No proposed change is approved merely by appearing here.

---

# 12. Rewrite completion criteria

The rewrite is complete only when:

- `RW-C01` through `RW-C04` are verified;
- all Block B Requirement abstraction items are verified;
- the normal Requirement lifecycle is state-driven and verified end to end;
- human approval/rework boundaries cannot be crossed automatically;
- project bootstrap works through one verified user action;
- current deterministic Fibery project-init and requirement-add primitives are reused unless a documented defect required change;
- old AMR corpus is preserved through corrected dogfood and then cleaned only through `RW-V03` human-reviewed cleanup;
- both AMR RAW sources have been dogfooded through the corrected pipeline without a confirmed abstraction/lifecycle blocker;
- obsolete old AMR Standard Requirements have been reviewed and cleaned from the active corpus under `RW-V03`;
- repository docs match verified behavior;
- full project regression suite passes;
- no accepted Proposed Change Request remains unrepresented in a frozen work item;
- no implementation work item remains `IMPLEMENTED_UNVERIFIED`.

Completion marker:

```text
SDLC_REWRITE_V0_1_VERIFIED
```

Only the human/independent reviewer may record that marker.

---

# 13. Initial work-item index

| ID | Title | Owner | Initial Status | Depends On |
|---|---|---|---|---|
| RW-C01 | Standard Requirement abstraction v0.2 | Human/Reviewer | PLANNED | — |
| RW-C02 | Requirement lifecycle ownership | Human/Reviewer | PLANNED | C01 |
| RW-C03 | Project bootstrap contract | Human/Reviewer | PLANNED | C01 |
| RW-C04 | State-trigger worker contract | Human/Reviewer | PLANNED | C02 |
| RW-R01 | Standard Requirement document schema | Agent | PLANNED | C01 |
| RW-R02 | RAW decomposition contract | Agent | PLANNED | R01 |
| RW-R03 | Standard Process correction | Agent | PLANNED | R01 + R02 |
| RW-R04 | Standard Review correction | Agent | PLANNED | R03 |
| RW-R05 | Abstraction regression corpus | Agent | PLANNED | R02 + R03 + R04 |
| RW-O01 | Normal state control vs admin CLI | Agent | PLANNED | C02 |
| RW-O02 | Requirement worker dispatcher | Agent | PLANNED | C04 + O01 |
| RW-O03 | State-change trigger entrypoint | Agent | BLOCKED | O02 |
| RW-O04 | Requirement lifecycle E2E automation | Agent | BLOCKED | O03 |
| RW-B01 | Consumer template manifest | Human/Reviewer | PLANNED | C03 |
| RW-B02 | Consumer template implementation | Agent | BLOCKED | B01 |
| RW-B03 | Project descriptor implementation | Agent | BLOCKED | B01 |
| RW-B04 | Outer project bootstrap | Agent | BLOCKED | B02 + B03 + C03 |
| RW-B05 | Bootstrap E2E | Agent | BLOCKED | B04 |
| RW-V01 | Preserve AMR baseline evidence | Human/Reviewer | PLANNED | — |
| RW-V02 | Corrected AMR dogfood | Human/System/Reviewer | BLOCKED | R05 + O04 + V01 |
| RW-V03 | Cleanup obsolete AMR dogfood requirements | Human/Reviewer | BLOCKED | V02 |
| RW-D01 | Reconcile docs/README | Agent | BLOCKED | verified implementation + V03 |

---

# 14. Freeze procedure

Before any Claude/Codex implementation run:

1. Human reviews this entire plan.
2. Confirm the normalized Resolved Decisions in section 8 and complete/freeze Block A contracts.
3. Correct the plan itself if needed.
4. Change header to:

```text
Status: FROZEN
Implementation authorization: GRANTED
```

5. Commit this exact file to `main`.
6. Record its commit SHA here:

```text
Plan Commit: <SHA>
```

7. Every implementation prompt must name exactly one `RW-*` item and the frozen Plan Commit.
8. Implementation agent must read that item from the repository before modifying code.
9. No implementation item starts from a prose summary supplied in chat when the repository plan is available.

