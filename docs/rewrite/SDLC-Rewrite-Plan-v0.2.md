# SDLC Rewrite Plan v0.2

**Status:** FROZEN  
**Implementation authorization:** GRANTED  
**Target repository:** `ros-datonum/sdlc`  
**Implementation baseline:** `e15e59f8ed8d36f00e86e94dfca2b643215ab641`  
**Primary requirements input:** `SDLC-Corrected-Product-Functional-Requirements-v0.2.md`  
**Requirements input SHA-256:** `0eec181a2e80410d9bfe260d4e1fd83286245ba3e4e9647f715aa8c887b9d53c`
**Frozen Plan Commit:** recorded in `docs/rewrite/SDLC-Rewrite-Freeze-v0.2.md`  
**Block A verification:** `docs/rewrite/Block-A-Verification-v0.1.md` — C01–C04 human-approved and independently verified on 2026-09-10.

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

**Status:** VERIFIED  
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

**Verification:** PASS  
**Review Evidence:** Human approved; independent review confirmed all acceptance criteria against product requirements and dependent contracts.  
**Verified Commit:** `546ac6c574eb0460ebb3bf9f2c8d64177c1772ed`

---

## RW-C02 — Freeze corrected Requirement lifecycle ownership

**Status:** VERIFIED  
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

**Verification:** PASS  
**Review Evidence:** Human approved; independent review confirmed all acceptance criteria against product requirements and dependent contracts.  
**Verified Commit:** `a3c8b0d2e57c4412a004f285f9c89143f285da70`

---

## RW-C03 — Freeze project bootstrap contract

**Status:** VERIFIED  
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

**Verification:** PASS  
**Review Evidence:** Human approved; independent review confirmed all acceptance criteria against product requirements and dependent contracts.  
**Verified Commit:** `a940527a892c6e74059d613952ee52de05aba92c`

---

## RW-C04 — Freeze state-trigger worker contract

**Status:** VERIFIED  
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

**Verification:** PASS  
**Review Evidence:** Human approved; independent review confirmed all acceptance criteria against product requirements and dependent contracts.  
**Verified Commit:** `08f64c20dd059a7222aa8211d0dbaed434e8be09`

---

# BLOCK B — REQUIREMENT ABSTRACTION REWRITE

No implementation item in this block starts before `RW-C01 = VERIFIED`.

---

## RW-R01 — Update Standard Requirement Document Schema

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `22f00894c05b5d5281adf428486a5d41e65c7ffd`  
**Implementation Evidence:**

- AC1 — `Standard-Requirement-Document-Schema-v0.1.md` §1 states Requirement = WHAT / Architecture = HOW / Delivery Planning / Task, implementation independence as default, and the source-mandated mechanism exception; every §3 section definition is bounded by it.
- AC2 — Schema §4: only title and `Requirement` need content; any other section may be omitted, keeps its heading, and renders `Not specified in source.` / `None.`. Tests: `test_every_section_but_the_requirement_may_be_omitted`, `test_a_product_level_requirement_renders_under_the_schema` (exact golden document), `test_a_product_level_requirement_may_omit_unestablished_sections`.
- AC3 — Schema §3 `Detailed Behavior` lists allowed WHAT clarifications and forbids architecture, algorithm, module/function design, worker/process topology, implementation sequence/steps, test implementation, deployment mechanics; source-mandated mechanisms go to `Requirement`/`Constraints & Edge Cases`, never here. Schema §5 + `raw_processing.reserved_heading`: section content adding a level-1/2 heading outside a fence is `INVALID_MODEL_OUTPUT` in both RAW decomposition and Standard Process parsing.
- AC4 — Renderer, headings, order, fixed texts and title line unchanged. `test_a_schema_rendered_product_level_root_binds_as_a_valid_tree`: Fibery-reserialized schema document is read by `read_normative_tree`, fingerprints as `document_fingerprint(document)`, manifest round-trips, Process Result output tree equals the observed tree and round-trips. Existing normative-tree, fingerprint-versioning, processor and review suites green.
- AC5 — Valid: product-level timeout Requirement (abstraction contract example 5) renders exactly. Rejected: `test_an_implementation_leaking_section_is_rejected` (architecture section in Detailed Behavior, Task steps as H1 in Acceptance, setext test-code section in Constraints, indented deployment section in Requirement), `test_no_section_can_add_a_document_section`, `test_normalization_cannot_add_an_architecture_section`. Still content: `test_subheadings_fences_and_spaced_rules_remain_section_content`.
- Review correction (independent review `CHANGES_REQUIRED`: multiline-title bypass of the closed section set) — `22f0089`: `raw_processing.is_single_line` + `MULTILINE_TITLE_MESSAGE`, applied by `_read_title` in `raw_processing` (RAW candidate `title`) and `standard_analysis` (`normalized_requirement.title`). A title that still contains `\n` or `\r` after the existing surrounding-whitespace trim is `INVALID_MODEL_OUTPUT`. Schema §5 states the rule. Tests: `test_a_multiline_title_is_rejected`, `test_a_multiline_normalized_title_is_rejected` (`"T\n## Architecture"`, `"T\r## Architecture"`, CRLF, CR inside prose); `test_a_single_line_title_renders_exactly_as_before` (padded title → exact golden `PRODUCT_LEVEL_DOCUMENT` and document name), `test_a_single_line_normalized_title_renders_exactly_as_before`; `test_a_title_cannot_add_document_structure`, `test_a_normalized_title_cannot_add_document_structure` (level-1/2 headings = title line + the seven fixed sections). The 8 rejection cases fail against `07a4e0c` and pass at `22f0089`; on `07a4e0c` both parsers rendered an extra `## Architecture` for `"T\n## Architecture"` and `"T\r## Architecture"`. A valid title renders byte-identically at both commits.
- Targeted: `uv run pytest -q tests/test_raw_processing.py tests/test_standard_analysis.py tests/test_normative_tree.py tests/test_fingerprint_versioning.py` → 204 passed (188 at `07a4e0c`).
- Full: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → All checks passed; 132 files already formatted; 1595 passed (1579 at `07a4e0c`; baseline 1556 at `1919850`).

**Blocker:** —  
**Execution Notes:**

- Base `1919850`; IMPLEMENTING mark `370d62a`; implementation `07a4e0c`; first evidence `2ce7956`; review correction `22f0089` (the Implementation Commit: complete implemented tree).
- `Detailed Behavior` retained under its existing heading/key and redefined; renaming or dropping headings would stop existing Root Documents matching persisted evidence (`content_equivalent` recovery checks).
- "Omit" is implemented as omitted content rendered with the fixed text; headings are always present (deterministic structure preserved).
- The structural check runs only on new model output (`parse_model_output`, `parse_analysis_output`). Persisted Processing/Process Results build `Candidate`/`NormalizedRequirement` directly and are neither re-validated nor migrated.
- Behavior change: model output with a level-1/2 heading inside a section now fails through the existing `INVALID_MODEL_OUTPUT` path. `raw_prompt.py`, `standard_prompt.py`, `review_prompt.py` were not changed; RW-R02/RW-R03 prompt work should state this rule to the model.
- Prose-level implementation leakage is a semantic judgement and is not deterministically detected; no keyword/regex classifier was added. It remains for model-backed Process/Review (RW-R03/RW-R04).
- Existing structural fixtures (`FULL_CANDIDATE`, `standard_fake.normalized()`) still carry mechanism-flavoured Detailed Behavior text; left unchanged.
- No Fibery schema/live state, lifecycle, model-runtime, decomposition or Review semantics changed.
- Environment: `.python-version` is `3.12.13` (global default `3.12.14`); repository has no Dockerfile or CI config. Reported, not changed.
- Out-of-scope discovery recorded as `CR-001` (section 11). Independent review rejected its deferral to RW-R02/RW-R03; the defect is fixed within RW-R01 by `22f0089`. The `CR-001` entry text was not edited.
- Review correction scope: title parsing only. The line-break check runs after the existing trim, so a leading or trailing line ending is still normalized away as before; only `\n`/`\r` are refused, with no wider character set. Reserved-heading logic unchanged. No change to prompts (`raw_prompt.py`, `standard_prompt.py`, `review_prompt.py`), Requirement ID format, lifecycle, Fibery schema/state, model runtime, decomposition/Standard Process/Review semantics, normative-tree format, fingerprints, or persisted evidence contracts; persisted Processing/Process Results are not re-validated against the title rule.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-R02 — Correct RAW decomposition contract

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `ce76831b8196b73b4413faecdfa8b6c21ec6f402`  
**Implementation Evidence:**

- AC1 — `raw_prompt.INSTRUCTIONS` "Decomposition" + "Anti-implementation-leakage rule": one capability described with many technical details of one proposed implementation is one candidate; the details are facets, not candidates. `test_one_capability_with_many_implementation_details_is_one_candidate`: a source carrying `run_model()`, watchdog/SIGKILL, `ModelRequest.deadline` and `ExecutionStatus.TIMEOUT` yields exactly one FR candidate whose Root Document holds none of them, while all remain in the model context and the RAW source is unchanged. Also `test_an_implementation_suggestion_does_not_become_a_candidate` (Redis queue / polling suggestion) and `test_a_field_without_independent_meaning_is_no_standalone_candidate` (`request_id: UUID` on `ModelRequest`).
- AC2 — the prompt separates obligations that can be accepted/rejected, change, differ in outcome, or be owned independently, and forbids merging them because they share a paragraph, section or implementation. `test_two_independent_obligations_in_one_paragraph_stay_two_candidates`: CSV export and export auditing in one paragraph → two candidates, distinct IDs, each Derived From the RAW.
- AC3 — prompt "Source-mandated mechanisms": an exact mechanism only when the source explicitly mandates it, then possibly a CONSTRAINT; an example, current implementation, background, existing architecture or suggestion is no mandate; an unclear mandate goes to `open_questions`; includes the abstraction contract's shell-outcome vs argv-mandate contrast. `test_an_explicitly_mandated_mechanism_remains_a_constraint` ("must use argv and must never use a shell" → `SDLC-CON-*`, Requirement section verbatim, so no deterministic filter strips mechanism words); `test_an_unmandated_mechanism_leaves_only_the_outcome`; `test_a_legitimate_system_constraint_stays_requirement_level`; `test_a_legitimate_non_functional_requirement_stays_requirement_level`.
- AC4 — prompt `open_questions` + source-preservation rules: preserve each product question and never answer it; architecture-only questions stay out unless they could change product intent. `test_an_unresolved_source_decision_stays_open_and_is_not_answered`: the override question renders verbatim under `## Open Questions`, unestablished sections render `Not specified in source.`, and the queue-library architecture question is absent. Zero candidates: `test_no_candidate_warranted_is_zero_candidates_with_a_reason`.
- AC5 — findings/peer rules kept; `FindingKind`, finding parsing and processor unchanged. `test_a_finding_about_a_non_applied_peer_stays_an_observation` (Ready peer: finding reported; peer record, Root Document content, Derived From and Produces unchanged; peer present in context) plus existing `test_findings_are_reported_without_mutating_existing_requirements`, `test_existing_standards_are_offered_to_the_model_as_context`, and the comparison-context and finding-reference suites.
- AC6 — `git diff df21567 ce76831 -- src/` changes only `raw_prompt.py`; `raw_processing.py`, `raw_processor.py`, `processing_result.py`, comparison context and the RAW lock are untouched. Green: `test_raw_processor_resume.py`, `test_empty_result_recovery.py`, `test_processing_result.py`, `test_raw_single_writer.py`, `test_raw_processor_cross_stage.py`, `test_raw_processor_validation.py`, `test_raw_source.py`, `test_raw_source_fences.py`. Every RW-R02 case asserts the RAW Root Document is byte-identical after processing.
- AC7 — `INSTRUCTIONS` section "Anti-implementation-leakage rule:" lists every abstraction-contract §5 trigger. `test_the_prompt_states_the_anti_implementation_leakage_rule`; also `test_the_prompt_encodes_no_candidate_count`, `test_the_prompt_keeps_structured_output_without_reasoning`, `test_the_prompt_states_the_document_structure_rules`, `test_the_prompt_shape_lists_exactly_the_candidate_contract_fields`.
- Red check: run against the `df21567` source, 15 of the 17 new tests fail (all on the new prompt rules); the 2 preservation tests (non-Applied peer finding, output shape) pass on both.
- Targeted: `uv run pytest -q tests/test_raw_decomposition_contract.py tests/test_raw_processing.py tests/test_raw_processor.py tests/test_raw_processor_resume.py tests/test_raw_processor_validation.py tests/test_raw_processor_cross_stage.py tests/test_raw_single_writer.py tests/test_raw_source.py tests/test_raw_source_fences.py tests/test_processing_result.py tests/test_empty_result_recovery.py tests/test_comparison_context.py tests/test_finding_reference_contract.py tests/test_standard_analysis.py tests/test_normative_tree.py tests/test_fingerprint_versioning.py` → 630 passed (613 at `df21567`); includes the RW-R01 schema suites.
- Full: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → All checks passed; 134 files already formatted; 1612 passed (1595 at `df21567`).

**Blocker:** —  
**Execution Notes:**

- Base `df21567`; IMPLEMENTING mark `b3e0bf1`; implementation `ce76831`.
- Changed: `src/sdlc/raw_prompt.py` (instructions and docstring only; `build_prompt` and its context unchanged); `docs/specs/RAW-Requirement-Processor-Decision-v0.1.md` (§2 "Decomposition level", §5 peer-evidence sentence, §7 flow labels); `docs/specs/RAW-Processor-Processing-Result-v0.1.md` (§2 pointer: keys, order and counts are execution facts, not candidate semantics); new `tests/test_raw_decomposition_contract.py`.
- Deterministic output contract unchanged. The semantic items of Required Change are carried by the model instructions; `raw_processing.py` already enforces the closed shape, categories, operation-free findings, zero-with-reason, reserved H1/H2 and the single-line title. No regex/keyword prose classifier was added.
- The tests use bounded fake-model decompositions: they prove the prompt carries each rule and that deterministic code never splits, merges, completes or counts candidates. They do not prove what a live model decides.
- Prompt grew from 2,197 to 8,447 characters (about 1.6% of the 400,000-character assembled-input bound); budget and refusal behavior and their tests unchanged.
- The prompt now tells the model the existing structural rules (single-line title, no level-1/2 heading in section content); enforcement remains the unchanged parser.
- Not changed: `standard_prompt.py`, `review_prompt.py`, Fibery schema/live state, lifecycle and state-transition ownership, model runtime/auth, Ready/Apply, A1–A11 hardening, the AMR dogfood corpus.
- No Proposed Change Request.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-R03 — Correct Standard Process normalization and analysis

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `a4243ba03a99608d591439907aa8d217e78c8c20`  
**Implementation Evidence:**

- AC1 — New self finding `IMPLEMENTATION_LEAKAGE` in the closed `FindingKind`; `standard_prompt.INSTRUCTIONS` "Implementation leakage": keep the WHAT, remove or omit non-mandated HOW, report the finding describing the leaked material, never move the HOW into another section or turn it into a product constraint; a Requirement that is itself HOW is reported, not rescued with an invented WHAT, and goes to Review defective. Tests: `test_partial_leakage_keeps_the_what_and_reports_the_how` (watchdog/SIGKILL/`run_model()` Detailed Behavior → Requirement verbatim, Detailed Behavior `Not specified in source.`, no mechanism word anywhere in the rewritten Root, finding persisted with null `requirement_id` and naming the watchdog); `test_a_candidate_that_is_entirely_how_is_reported_not_rescued` (Task statement verbatim, no fabricated WHAT, no Requirement created or split, State `Review`); `test_observable_acceptance_is_kept_and_test_mechanics_are_not`; `test_test_mechanics_alone_are_omitted_not_turned_into_acceptance`.
- AC2 — prompt "What normalization is": keep a valid high-level Requirement high-level; never add technical design to make it concrete; Process need not turn every input into a valid Requirement. `test_a_valid_high_level_requirement_stays_high_level` (Root rewritten from exactly the model's sections, unestablished sections keep the fixed text, no mechanism added, no finding); `test_an_observable_requirement_is_not_penalized_for_absent_test_design`; `test_technical_facets_of_one_obligation_are_not_non_atomic`.
- AC3 — prompt "Source-mandated mechanisms": an explicitly mandated mechanism is legitimate and is not leakage; current implementation, example, background, existing architecture or suggested solution is no mandate; an unclear mandate that changes WHAT stays an open question. `test_a_source_mandated_constraint_stays_intact_and_is_not_leakage` ("must use argv and must never use a shell" verbatim, no finding, so no deterministic filter touches mechanism words).
- AC4 — prompt `open_questions`, source-preservation and completeness rules. `test_an_open_product_decision_stays_open_and_unanswered` (question verbatim under `## Open Questions`, no answer in any other section); `test_an_architecture_only_question_is_not_missing_requirement_content` (queue-library question not kept, `None.` rendered, no `INCOMPLETE`).
- AC5 — `git diff 49e858c a4243ba -- src/` touches only `standard_analysis.py` (one enum member, docstring), `standard_prompt.py`, and the self-kind list in `review_prompt.py`. `standard_processor.py`, `process_result.py`, `standard_review.py`, `review_result.py`, `standard_reviewer.py`, comparison context and normative tree are unchanged; the Process Result format and version are unchanged and existing results parse as before. Green: `test_standard_processor.py`, `test_standard_processor_iterations.py`, `test_standard_processor_state_machine.py`, `test_standard_processor_concurrency.py`, `test_standard_process_explicit_resume.py`, `test_standard_process_review_chain.py`, `test_empty_result_recovery.py`, `test_normative_tree.py`, `test_normative_tree_stages.py`, `test_fingerprint_versioning.py`, `test_comparison_context.py`.
- AC6 — `tests/test_standard_process_abstraction.py` (17 tests over the real Process stage boundary: the ten semantic classes plus prompt/contract pins, including `test_independent_obligations_yield_non_atomic_without_a_split` and `test_peer_findings_and_relation_proposals_stay_non_mutating`) and four pinned tests in `test_finding_reference_contract.py`: `test_implementation_leakage_is_pinned_as_a_self_finding`, `test_process_persists_implementation_leakage_without_a_requirement_id`, `test_process_rejects_implementation_leakage_that_names_a_peer`, `test_review_ingests_and_verifies_a_process_leakage_finding`.
- Red check against the `49e858c` source: the RW-R03 module (scratch copy with a `getattr` fallback for the absent enum member) → 14 failed, 3 passed (preservation: independent-obligation `NON_ATOMIC`, peer/relation non-mutation, prompt shape); the four leakage finding-reference tests fail; the two prompt-partition tests pass on both trees.
- Targeted: `uv run pytest -q tests/test_standard_process_abstraction.py tests/test_comparison_context.py tests/test_empty_result_recovery.py tests/test_finding_reference_contract.py tests/test_fingerprint_versioning.py tests/test_normative_tree_stages.py tests/test_normative_tree.py tests/test_raw_decomposition_contract.py tests/test_raw_processing.py tests/test_standard_analysis.py tests/test_standard_process_explicit_resume.py tests/test_standard_process_review_chain.py tests/test_standard_processor_concurrency.py tests/test_standard_processor_iterations.py tests/test_standard_processor_state_machine.py tests/test_standard_processor.py tests/test_standard_review_contract.py tests/test_standard_reviewer_state.py tests/test_standard_reviewer.py` → 751 passed (728 at `49e858c`).
- Full: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → All checks passed; 136 files already formatted; 1635 passed (1612 at `49e858c`).

**Blocker:** —  
**Execution Notes:**

- Base `49e858c`; IMPLEMENTING mark `1d7dd5f`; implementation `a4243ba`.
- Changed: `src/sdlc/standard_prompt.py` (instructions and docstring; `build_analysis_prompt` and its context unchanged); `src/sdlc/standard_analysis.py` (`IMPLEMENTATION_LEAKAGE` member, docstring); `src/sdlc/review_prompt.py` (self-kind list only); `docs/specs/Standard-Requirement-Process-Spec-v0.1.md` (amendment line, §3.1, §6 finding list and note); `tests/test_finding_reference_contract.py`; new `tests/test_standard_process_abstraction.py`.
- `standard_processor.py` (frozen Affected Area) inspected and left unchanged: findings travel as validated data, so carrying the new kind needed no protocol change.
- Review compatibility only: `FindingKind` is shared, so the Review parser now also accepts `IMPLEMENTATION_LEAKAGE` as a self new finding under the unchanged strict rule, and the Review prompt's self-kind list names it so both prompts stay mechanically consistent with the parser. No Review abstraction instruction, verdict, or severity logic was added; that remains RW-R04.
- Deterministic contract: only the closed finding vocabulary grew. Unknown-field rejection, self/cross validation, single-line title, reserved H1/H2, missing-information text and rendering are unchanged; no prose classifier was added.
- The tests use bounded fake-model outputs through the real `process_standard_requirement`; they prove the prompt rules and the deterministic pipeline, not what a live model decides.
- Prompt grew from 3,317 to 9,896 characters (about 2.5% of the 400,000-character assembled-input bound); budget and refusal behavior unchanged.
- Not changed: `raw_prompt.py`, RAW processing, Ready/Apply, lifecycle and state-transition ownership, Processing Status, worker routing, bootstrap, Fibery schema/live state, model runtime/auth, A1–A11 hardening, the AMR dogfood corpus.
- No Proposed Change Request.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-R04 — Correct Standard Review abstraction checks

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `ef918f2e9b0b766236dc760d96bc9db91c1b5fe1`  
**Implementation Evidence:**

- AC1 — `review_prompt.INSTRUCTIONS` "Defects to flag": `IMPLEMENTATION_LEAKAGE` for downstream HOW presented as Requirement truth, including Task/test mechanics disguised as Acceptance / Verification; `INCONSISTENT` for source invention, stated as unsupported by or inconsistent with the originating source; `INCOMPLETE` for unjustified fragmentation of one source obligation; `NON_ATOMIC` only for the opposite shape. Tests: `test_review_confirms_a_process_leakage_finding`, `test_review_reports_leakage_the_process_missed`, `test_test_mechanics_in_acceptance_are_reported_as_leakage`, `test_review_rejects_a_leakage_claim_when_the_source_mandates_it`, `test_source_invention_is_reported_as_inconsistent_with_the_source`, `test_a_fragment_of_one_source_obligation_is_incomplete_not_non_atomic`, `test_independent_product_obligations_are_still_non_atomic`. No finding kind added: `test_the_finding_vocabulary_is_unchanged`.
- AC2 — prompt "Not defects": missing downstream design is not `INCOMPLETE`/`MISSING_CONSTRAINT`/`MISSING_EDGE_CASE`/`NOT_TESTABLE`; no test design needed to pass; a mandated mechanism, an open product decision and an unanswered architecture question are not defects. `test_a_valid_high_level_requirement_is_not_penalized_and_passes` (no finding, `PASS`), `test_a_source_mandated_constraint_is_not_flagged`, `test_an_open_product_question_is_not_a_defect_merely_for_being_open`, `test_a_missing_architecture_decision_is_not_incomplete`, `test_a_requirement_without_raw_ancestry_is_still_reviewable` (`(none)` section, `PASS`).
- AC3 — the reviewer now receives the originating RAW source (`standard_reviewer._raw_ancestry`, under `# Originating RAW requirement source`). `test_genuine_source_gaps_and_contradictions_are_still_caught` (`MISSING_CONSTRAINT` WARNING + `INCONSISTENT` BLOCKING → `BLOCKING`, still reaches `Ready`); the source-invention test asserts the `<!-- RAW SDLC-RAW-0007 -->` source text is in the reviewer context; `test_peer_comparison_findings_are_verified_and_reported_without_mutation`; `test_relation_verifications_stay_evidence_and_are_never_written`.
- AC4 — `tests/test_finding_reference_contract.py` unchanged and green: both prompts' self-kind lists still equal the parser's partition, the examples parse, and self/cross references stay strict in Process and Review.
- AC5 — `standard_review.py`, `review_result.py` and `results.py` unchanged: the closed output contract, exact finding and relation coverage, severity rule, derived verdict and persisted bindings are as before. `test_a_raw_source_read_failure_refuses_before_the_model_and_any_write` (`FIBERY_READ_FAILED`, model not invoked, zero mutations, no Review Result, State `Review`); every successful case asserts that only the Review Result create/write and `Review -> Ready` occurred, the Root is byte-identical, and peers, Revision and relations are unchanged; `test_a_no_change_review_neither_reads_nor_binds_the_raw_source` (`NO_CHANGES_TO_REVIEW` with no `derived_from` call; RAW text not persisted). Existing reviewer, reviewer-state, review-contract, Review Result, CLI review, Process→Review chain, Ready/Apply, normative-tree, fingerprint, comparison-context and empty-result recovery suites green.
- Red check against the `4a6c067` source: 15 of the 20 new tests fail; the 5 preservation tests (confirmed Process leakage, peer comparison, relation verification, no-change without a RAW read, unchanged vocabulary) pass on both trees.
- Targeted: `uv run pytest -q tests/test_standard_review_abstraction.py tests/test_standard_review_contract.py tests/test_standard_reviewer.py tests/test_standard_reviewer_state.py tests/test_finding_reference_contract.py tests/test_standard_process_review_chain.py tests/test_review_result.py tests/test_cli_review.py tests/test_ready_decision.py tests/test_ready_decision_validation.py tests/test_cli_ready.py tests/test_requirement_apply.py tests/test_requirement_apply_resume.py tests/test_requirement_apply_validation.py tests/test_cli_apply.py tests/test_normative_tree.py tests/test_normative_tree_stages.py tests/test_fingerprint_versioning.py tests/test_comparison_context.py tests/test_empty_result_recovery.py tests/test_standard_process_abstraction.py tests/test_standard_analysis.py tests/test_raw_decomposition_contract.py tests/test_raw_processing.py` → 907 passed (887 at `4a6c067`).
- Full: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → All checks passed; 138 files already formatted; 1655 passed (1635 at `4a6c067`).

**Blocker:** —  
**Execution Notes:**

- Base `4a6c067`; IMPLEMENTING mark `d2ab348`; implementation `ef918f2`.
- Changed: `src/sdlc/review_prompt.py` (docstring, instructions, `raw_ancestry` parameter and its context section); `src/sdlc/standard_reviewer.py` (`_verify` reads the RAW source; new `_raw_ancestry`); `docs/specs/Standard-Requirement-Review-Spec-v0.1.md` (amendment line, §3.1, §5 input and RAW paragraph, §20 abstraction tests); new `tests/test_standard_review_abstraction.py`.
- `standard_review.py` (frozen Affected Area) inspected and left unchanged: the existing closed vocabulary and output contract express every RW-R04 judgement.
- RAW ancestry is a reviewer-local mirror of Standard Process `_read_raw_ancestry` (same `Derived From` → attached Root boundary, `<!-- RAW id -->` marker and join). It was not extracted into a shared helper so `standard_processor.py` stays byte-identical; this is the second occurrence. It is read in `_verify` after the comparison context, so existing comparison refusals keep precedence, and only on paths that invoke the model (a new review, explicit empty-result recovery), never on no-change. The final whole-input budget covers it automatically.
- No new Fibery read or write pattern: it uses `derived_from`, `documents_attached_to_requirement` and `read_document_content`, already verified for Process, so the fake needed no change. Cost is one attached-document read per RAW ancestor, normally one.
- The RAW source is evidence, not reviewed input: it is neither bound nor persisted, so Review Result format, version and bindings are unchanged. Consequently an edit to the RAW alone does not make an existing Review Result stale.
- The tests use bounded fake-model outputs through the real `review_standard_requirement`; they prove the prompt contract and the deterministic Review boundary, not what a live model decides.
- Review prompt grew from 3,957 to 8,530 characters (about 2.1% of the 400,000-character assembled-input bound).
- Not changed: Standard Process code and prompt, `standard_analysis.py`, verdict derivation, Ready/Apply, lifecycle and state-transition ownership, Processing Status, worker routing, bootstrap, Fibery schema/live state, model runtime/auth, A1–A11 hardening, the AMR dogfood corpus.
- No new finding kind; no Proposed Change Request.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-R05 — Build Requirement abstraction regression corpus

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `4dfa8d1450b9560c79924c1d8ee945192c805d01`  
**Implementation Evidence:**

- Review correction (independent review `CHANGES_REQUIRED`: meaning was checked as one literal string per concept) — `4dfa8d1`: a `Concept` holds a bounded, case-specific list of equivalent expressions and is present when any one of them appears; an `Obligation` still requires every one of its concepts. Concepts carry obligation recognition, observable acceptance, the open product question and its forbidden answers, and the architecture question. Exact identity remains only where identity is the property: mandated `argv`/`shell` and the forbidden implementation and test identifiers. Red demonstration, with the same paraphrases checked by the `c60ac7b` module and by the corrected one: C01 without "time limit"/"timeout" → `source-obligation-lost` and `candidate-without-source-obligation` under `c60ac7b`, no violations now; C06 using "bypass" and no "override" → `open-product-question-closed` under `c60ac7b`, no violations now; C05 acceptance without "new cycle"/"success or failure" → two `observable-acceptance-lost` under `c60ac7b`, no violations now.
- AC1 — `tests/abstraction_corpus.py` `CORPUS`: ten `AbstractionCase`s whose `abstraction_class` is the frozen class text verbatim (`test_the_corpus_covers_exactly_the_ten_frozen_classes`). Each states its source obligations as concepts (each a bounded list of equivalents) plus `Category`, and at least one WHAT/HOW property (`test_every_case_states_its_classification_and_boundary_properties`): C01 one FR plus six implementation identifiers; C02 two independent FRs; C03 a `CONSTRAINT` with mandated `argv`/`shell` that must never draw `IMPLEMENTATION_LEAKAGE`; C04 one FR with Redis/queue/poll suggestion identifiers; C05 observable-acceptance concepts and six test-mechanics identifiers, where a leaky Root must draw `IMPLEMENTATION_LEAKAGE` in Process and Review; C06 the override/bypass open question and its forbidden answers; C07 the cancellation/enforcement architecture question, never `INCOMPLETE`/`MISSING_*`/`NOT_TESTABLE`; C08 field identifiers; C09 an NFR; C10 a system `CONSTRAINT`. Reference outputs satisfy every property through the real stages: `test_the_reference_decomposition_satisfies_the_case` (all ten), `test_the_reference_normalization_satisfies_the_case` (C03, C05, C06, C07), `test_the_reference_review_satisfies_the_case` (C03, C05, C06, C07, C09, C10).
- AC2 — `test_promoting_implementation_detail_is_caught`: the C01 watchdog and C08 field as standalone candidates (`implementation-detail-as-requirement`, `candidate-without-source-obligation`), the C04 Redis suggestion as a constraint (`implementation-detail-as-requirement`), and C05 test mechanics as acceptance (`test-mechanics-as-acceptance`); `test_normalization_that_keeps_test_mechanics_unreported_is_caught` (`test-mechanics-as-acceptance`, `expected-finding-missing`). Every defective output first passes the real stage, so detection is semantic, not structural. All remain caught after the correction.
- AC3 — `test_a_decomposition_that_drops_the_mandate_is_caught` and `test_a_normalization_that_drops_the_mandate_is_caught` (`mandated-mechanism-dropped`; the latter also `unwarranted-finding` for leakage on the mandate); `test_a_review_that_confirms_leakage_on_the_mandate_is_caught` (`unwarranted-finding`).
- AC4 — `test_a_decomposition_that_answers_the_open_question_is_caught` (override and bypass wording) and `test_a_normalization_that_answers_the_open_question_is_caught` (`open-product-question-closed`, `open-product-question-answered`).
- AC5 — the module docstring states that the corpus is a deterministic, case-specific semantic proxy; that concepts are bounded equivalent expressions; that whole model sentences are not golden output; that exact identity is required only where identity is the property; that it is not a general semantic or NLP classifier; and that a novel valid paraphrase outside the configured equivalents calls for reviewer judgement and an explicit fixture update, not a conclusion that product behavior is wrong. Cases are plain data with descriptive ids and cardinality notes; checks return named `Violation`s; the module imports no prompt. `test_a_bare_model_output_can_be_checked_without_running_a_stage` (all ten via `parse_model_output`), `test_an_analysis_output_can_be_checked_without_running_a_stage`. Paraphrase controls assert the reference markers are absent and still pass: `test_c01_paraphrase_without_the_source_markers_still_carries_the_obligation`, `test_c06_open_question_reworded_without_override_stays_open`, `test_c05_acceptance_paraphrase_without_the_source_markers_is_still_observable`; `test_c07_reworded_architecture_question_is_still_caught` shows rewording does not hide the architecture question.
- Corpus: `uv run pytest -q tests/test_abstraction_corpus.py` → 57 passed, including 11 negative controls and 4 paraphrase controls.
- R01–R04 abstraction suites and the stage suites the corpus drives: `uv run pytest -q tests/test_abstraction_corpus.py tests/test_raw_processing.py tests/test_raw_decomposition_contract.py tests/test_standard_analysis.py tests/test_standard_process_abstraction.py tests/test_standard_review_abstraction.py tests/test_finding_reference_contract.py tests/test_normative_tree.py tests/test_fingerprint_versioning.py tests/test_raw_processor.py tests/test_standard_processor.py tests/test_standard_reviewer.py` → 447 passed (390 at `542372b` without the corpus).
- Full: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → All checks passed; 141 files already formatted; 1712 passed (1655 at `542372b`).

**Blocker:** —  
**Execution Notes:**

- Base `542372b`; IMPLEMENTING mark `be0ca1f`; implementation `c60ac7b`; first evidence `5f792e5`; review correction `4dfa8d1` (the Implementation Commit: complete implemented tree).
- Changed: `tests/abstraction_corpus.py` (cases, reference outputs, checks) and `tests/test_abstraction_corpus.py` (stage runners on the Fibery fakes, reference, paraphrase and negative controls). `git diff 542372b 4dfa8d1 -- src config` is empty: no prompt, parser, processor, reviewer, persistence, lifecycle or runtime change.
- The data-and-checks module is separate from the stage runners so it can be applied to live output without the fakes. The reviewer guide lives in its docstring rather than a separate document, next to the data it describes.
- Concept alternatives are equivalents chosen for each synthetic source, compared as case-insensitive substrings; they are not a general synonym model. The C05 paraphrase control first failed its own marker-absence proof because it reused a requirement containing "new cycle"; the requirement was reworded so the proof covers the whole candidate.
- Cardinality is exact per case only from fixture semantics (one capability; two independent obligations). No global or ideal count exists, and no historical AMR count is encoded.
- No live AMR, live Fibery or live model is used; the fixtures are repository-owned synthetic text.
- The corpus exposed no defect in the verified R02–R04 behavior. Deterministic fixtures do not prove live-model semantic quality; that remains dogfood evidence (RW-V02).
- No Proposed Change Request.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

# BLOCK C — REQUIREMENT LIFECYCLE ORCHESTRATION

No code item in this block starts before `RW-C02` and `RW-C04` are `VERIFIED`.

---

## RW-O01 — Separate normal lifecycle control from admin CLI invocation

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `5433c3c676a9326a31621ba1493367dd4d562cb3`  
**Implementation Evidence:**

- Review correction (independent review `CHANGES_REQUIRED`: the Ready spec called an unedited rework that stays in Process a correct outcome) — `5433c3c`: Ready spec §11 now states that `Ready -> Process` always authorizes a new Standard Process cycle, edited or not (`RW-C02` §9); that with a changed tree today's processor already completes it; and that the unchanged-tree `NO_CHANGES_TO_PROCESS` is a known gap of the current worker path for RW-O02/RW-O03 (`CR-002`), not a completed rework. Ready Decision still neither runs Process nor decides how a worker starts the iteration. §12 keeps both edit orders and adds rework with no edit (Flow C) as equally valid. "Require an edit before rework" is rejected; the review decision is recorded in `CR-002`.
- AC1 — `tests/test_lifecycle_control.py`: `test_a_direct_ready_to_apply_is_applied_without_the_approve_command` (PASS, NEEDS_WORK and BLOCKING: the human State write is the only mutation before Apply, and the real `apply_standard_requirement` returns `REQUIREMENT_APPLIED` with State `Applied`); `test_a_direct_ready_to_apply_is_still_refused_on_stale_reviewed_content` (all three verdicts: `REVIEW_RESULT_STALE`, zero writes, State stays `Apply`); `test_apply_takes_no_verdict_acknowledgement` (signature `(workspace, entity_id)`; `apply --acknowledge-verdict` is rejected by the parser); `test_the_admin_approve_leads_to_the_same_apply_as_a_direct_transition` (the admin command yields an identical Requirement record and the same Apply outcome). Apply logic unchanged; docstring only.
- AC2 — `test_ready_is_a_human_boundary_standard_process_does_not_start_from` (at Ready: `REQUIREMENT_NOT_IN_PROCESS`, no model call, zero mutations); `test_a_direct_ready_to_process_is_the_rework_authority_edited_or_not` (edited and unedited: the human State write alone, with no rework command, artifact or marker, puts the Requirement into Standard Process's stage with a normal result, and Process/Review history stays byte-identical); `test_an_edited_rework_already_completes_a_new_process_iteration` (`REQUIREMENT_PROCESSED` iteration 2, model invoked, State `Review`, Review Result set unchanged); `test_an_unedited_rework_is_authorized_but_not_yet_processed_known_gap` (`NO_CHANGES_TO_PROCESS`, no model call, zero mutations, State stays `Process`, no new iteration; pinned as the known RW-O02/RW-O03 gap of `CR-002`, not as a completed rework). Ready spec §0, §11 and §12 and the README state that `State = Process` reached from Ready is the durable rework signal whether or not the content was edited.
- AC3 — `cli.py`: `REQUIREMENT_LIFECYCLE_NOTE` on the requirement group; the `MANUAL_WORKER` label on process, normalize, review and apply; the `ADMIN_DECISION` label and admin/compatibility descriptions on approve and rework; the `--acknowledge-verdict` help describes a safety check of the command, not approval authority. Tests: `test_the_requirement_commands_state_the_normal_lifecycle`, `test_approve_and_rework_remain_available_as_admin_commands`, `test_the_acknowledgement_is_a_safety_check_of_the_command_only` (the command still returns `VERDICT_ACKNOWLEDGEMENT_REQUIRED` at BLOCKING with zero mutations, while a direct `Ready -> Apply` at BLOCKING is applied), `test_the_admin_approve_cannot_bypass_the_evidence_checks` (`REVIEW_RESULT_STALE`, zero mutations, State stays Ready), `test_the_admin_rework_makes_only_the_state_transition`. Ready spec §0 scopes §§6–10 to the command; Apply spec §4 and §16 no longer assume the command's checks ran.
- AC4 — `ready_decision.py` and `requirement_apply.py` changed only in docstrings, so the validation logic is reused unchanged. Existing suites green: `test_ready_decision.py`, `test_ready_decision_validation.py`, `test_cli_ready.py`, `test_requirement_apply.py`, `test_requirement_apply_resume.py`, `test_requirement_apply_validation.py`, `test_cli_apply.py` (stale refusal, tree and fingerprint binding, malformed or ambiguous evidence, no false State write, no peer or relation mutation, independent Apply revalidation).
- Red check, run at `33104cc` against the `849e3da` source (scratch copy with a `getattr` fallback for the two new description constants): the 13 AC1/AC2 behavior tests of that version passed, because Apply already consumed `State = Apply` and Standard Process already entered on `State = Process`; the 4 AC3 contract and help tests failed. It was not re-run after the review correction.
- Targeted: `uv run pytest -q tests/test_lifecycle_control.py tests/test_ready_decision.py tests/test_ready_decision_validation.py tests/test_cli_ready.py tests/test_requirement_apply.py tests/test_requirement_apply_resume.py tests/test_requirement_apply_validation.py tests/test_cli_apply.py tests/test_cli.py tests/test_cli_review.py tests/test_cli_end_to_end.py tests/test_standard_processor.py tests/test_standard_processor_state_machine.py tests/test_standard_processor_iterations.py tests/test_standard_process_review_chain.py` → 344 passed (325 at `849e3da`).
- Full: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → All checks passed; 143 files already formatted; 1731 passed (1712 at `849e3da`).

**Blocker:** —  
**Execution Notes:**

- Base `849e3da`; IMPLEMENTING mark `e58c479`; implementation `33104cc`; first evidence `5c5e142`; review correction `5433c3c` (the Implementation Commit: complete implemented tree), which changed only Ready spec §§11–12 and `tests/test_lifecycle_control.py` (`git diff 33104cc 5433c3c -- src config` is empty).
- Changed: `src/sdlc/cli.py` (help text, descriptions and their constants, handler docstrings); `src/sdlc/ready_decision.py` and `src/sdlc/requirement_apply.py` (module docstrings only); `docs/specs/Standard-Requirement-Ready-Spec-v0.1.md` (amendment line, new §0, §§2, 4, 6, 9, 11, 16); `docs/specs/Standard-Requirement-Apply-Spec-v0.1.md` (amendment line, §4, §16); `README.md` (Requirement lifecycle control section); new `tests/test_lifecycle_control.py`.
- Direct transitions needed no code change: Apply's entry already required only `State = Apply` plus evidence revalidation, and Standard Process's entry is `State = Process`. RW-O01 changes contract text, CLI help, docstrings and tests, not Ready, Apply or Process logic.
- The `approve` command keeps every check, including `--acknowledge-verdict`, as optional admin UX, and records the same `State = Apply`. No approval or rework artifact, flag, field or ledger was added.
- The README says state-driven execution is not implemented yet; the dispatcher and trigger belong to RW-O02 and RW-O03.
- Not implemented, by design: `sdlc worker run`, Type+State routing, Processing Status, the Fibery reset automation, polling or other triggers, the inherited Standard `Draft -> Process` progression.
- Unedited rework: a human `Ready -> Process` authorizes a new Standard Process cycle even when the tree is unchanged. Today's processor returns `NO_CHANGES_TO_PROCESS` for it, stays in Process and runs no model, and no existing Process mode forces a new cycle. The Ready spec and the tests present this as the known gap, not as correct fulfilment. Independent review rejected requiring an edit before rework and assigned a bounded, non-bypass way to start that iteration to RW-O02/RW-O03; recorded in `CR-002`. RW-O01 designs no dispatcher or processor interface and changes no Standard Process semantics.
- The Ready spec's "No implementation exists yet" status line is historical and was left as is.
- Not changed: Standard Process, Review and RAW code, `results.py`, the Fibery workspace and schema, model runtime/auth, bootstrap, A1–A11 hardening, the AMR dogfood corpus.
- Proposed Change Request: `CR-002`, with the independent-review decision recorded; its status stays `PROPOSED` until the human updates the plan.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-O02 — Implement bounded Requirement worker dispatcher

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `a1ee1fb849d668222ebbf0213c97e8076eef03df`  
**Implementation Evidence:**

- AC1 — `src/sdlc/requirement_dispatcher.py` `ROUTES` holds exactly the RW-C04 table: Raw+Process → RAW Processor, Standard+Process → Standard Process, Standard+Review → Standard Review, Standard+Apply → Standard Apply, each at `Not Processed`. `tests/test_requirement_dispatcher.py`: `test_the_route_table_is_closed_to_the_four_rw_c04_routes`; `test_each_authorized_route_runs_exactly_its_one_worker` (each route calls its one worker once, and completes only on its postcondition Review/Review/Ready/Applied); `test_only_standard_process_is_invoked_as_an_authorized_new_cycle`. The real workers run through the dispatcher in the RAW progression, CR-002, Review and Apply tests. Workers are the existing capabilities injected already bound (`RequirementWorkers`); no processor, review, evidence or Apply logic is duplicated.
- AC2 — `test_no_worker_runs_outside_the_four_routes`: Raw Draft and Standard Ready are `HUMAN_BOUNDARY`; Raw Review, Standard Draft and Standard Applied are `NO_MACHINE_WORK`; Raw Ready/Apply/Applied and unknown Type or State are `UNSUPPORTED_STATE`, at every Processing Status, with no worker call, no mutation and nothing repaired. `test_the_ready_verdict_plays_no_part_in_route_selection` (PASS, NEEDS_WORK, BLOCKING at Ready all stop). `test_a_stale_selection_runs_no_worker_and_corrects_nothing` (human State change, Type change, identity change, deleted entity). A generic Standard Draft never progresses: the unrelated Draft in `test_the_exact_candidates_of_a_successful_raw_result_move_to_process` and `test_a_standard_merely_derived_from_the_raw_is_not_progressed`.
- AC3 — `test_redispatching_a_completed_raw_duplicates_nothing`, `test_after_standard_process_only_a_new_review_cycle_is_selectable`, `test_review_stops_at_ready_and_ready_selects_no_worker`, `test_an_applied_requirement_selects_no_worker_and_is_not_reapplied`: after a worker-owned transition, selection from the current State never selects the same worker again; the old selection replays as `STALE_ROUTE`; Documents, contents and Requirements are unchanged. `test_a_claimed_completed_or_failed_cycle_runs_no_worker` (Processing, Succeeded, Failed × four routes) and `test_only_a_not_processed_cycle_can_request_a_new_iteration`. No dispatcher ledger exists.
- AC4 — `test_a_failed_worker_never_advances_the_lifecycle` (four routes: `WORKER_FAILED`, zero dispatcher writes, State unchanged); `test_a_normal_result_that_leaves_the_state_is_not_a_completed_cycle` (four routes: `POSTCONDITION_NOT_REACHED`); `test_no_changes_to_process_in_process_is_not_a_completed_cycle`; `test_no_changes_to_review_in_review_is_not_a_completed_cycle` (real reviewer); `test_a_failed_raw_worker_progresses_no_candidate`; `test_a_failed_revalidation_read_runs_no_worker`; progression failures: `test_a_preflight_conflict_progresses_no_candidate_and_demotes_nothing` (already past Draft, wrong Type, missing provenance, ambiguous ID: zero writes, valid peers untouched, nothing demoted), `test_a_failed_first_progression_write_is_reported_and_nothing_moves`, `test_a_later_progression_write_failure_is_partial_and_never_rolled_back`.
- AC5 — `tests/test_requirement_dispatcher.py` (103 tests) covers every selection branch (4 routes; 12 status-gated route cases; 11 no-worker states at all four statuses), stale selection, and every `DispatchOutcome`: `ROUTE_COMPLETED`, `NO_ROUTE`, `STALE_ROUTE`, `WORKER_FAILED`, `POSTCONDITION_NOT_REACHED`, `CANDIDATE_PROGRESSION_CONFLICT`, `CANDIDATE_PROGRESSION_FAILED`, `PARTIAL_CANDIDATE_PROGRESSION`, `FIBERY_READ_FAILED`.
- CR-002 — `test_an_ordinary_call_over_the_unchanged_tree_still_reports_no_changes`; `test_the_dispatcher_turns_an_unedited_rework_into_the_next_iteration` (iteration 2, model called once, Process and Review history byte-identical, State Review); `test_an_edited_rework_keeps_the_existing_new_iteration_behavior`; `test_the_input_equality_ambiguity_is_not_bypassed` (through the dispatcher and a direct call with the keyword: `PROCESSING_STATE_CONFLICT`, no model call, no mutation); `test_the_new_cycle_entry_takes_no_explicit_option_and_has_no_cli_flag`. The RW-O01 lifecycle test still pins the ordinary call at `NO_CHANGES_TO_PROCESS`.
- Focused: `uv run pytest -q tests/test_requirement_dispatcher.py tests/test_raw_processor.py tests/test_raw_processor_resume.py tests/test_raw_processor_cross_stage.py tests/test_raw_single_writer.py tests/test_empty_result_recovery.py tests/test_standard_processor.py tests/test_standard_processor_state_machine.py tests/test_standard_processor_iterations.py tests/test_standard_process_explicit_resume.py tests/test_standard_processor_concurrency.py tests/test_standard_process_review_chain.py tests/test_standard_reviewer.py tests/test_standard_reviewer_state.py tests/test_requirement_apply.py tests/test_requirement_apply_resume.py tests/test_requirement_apply_validation.py tests/test_lifecycle_control.py tests/test_ready_decision.py tests/test_cli.py tests/test_cli_ready.py tests/test_cli_apply.py` → 690 passed.
- Full: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → All checks passed; 147 files already formatted; 1834 passed (1731 at `c7609fb`).

**Blocker:** —  
**Execution Notes:**

- Base `c7609fb`; IMPLEMENTING mark `3af90e6`; implementation `a1ee1fb`.
- Changed: new `src/sdlc/requirement_dispatcher.py`; `src/sdlc/standard_processor.py` (keyword-only `authorized_new_cycle`, its exclusivity with the three explicit options, and one condition on the no-change branch); `src/sdlc/fibery_workspace.py` (`DispatchWorkspace` protocol); new `tests/test_requirement_dispatcher.py`; docs: Process spec (header and §11 "Authorized new machine cycle"), Ready spec §11 (one paragraph), README (lifecycle paragraph), and one docstring in `tests/test_lifecycle_control.py`.
- Interface: `select_route(requirement, status) -> RouteSelection` (pure); `dispatch(workspace, workers, selection) -> DispatchResult`. `ProcessingStatus` models the RW-C04 vocabulary for route input only. `results.py` is unchanged: `DispatchOutcome` and `DispatchResult` live in the dispatcher module, which avoids a results → dispatcher dependency.
- `DispatchWorkspace` needs only `read_requirement`, `find_requirements_by_requirement_id` (count-aware uniqueness), `derived_from` and `set_requirement_state`, all already implemented by `FiberyRawProcessorWorkspace`; no HTTP code changed.
- The dispatcher validates each worker's postcondition by re-reading State and writes no worker-owned transition. RAW candidate progression runs only after `RAW_REQUIREMENT_PROCESSED` with the RAW read back in Review, over exactly the Requirement IDs in that result. Cost: one lookup and at most one provenance read per candidate, then one write and read-back each, bounded by one RAW result. There is no compare-and-set, so a change landing between preflight and a write is not detected; an unconfirmed write is reported as such.
- CR-002 closed at O02 level: the dispatcher's Standard+Process route invokes Standard Process with `authorized_new_cycle=True`, which turns an unchanged tree into the next iteration. Ordinary and manual calls, A11 ambiguity, empty shells and all checks are unchanged, and no CLI flag exposes it. Automatic invocation still needs the RW-O03 runner, whose Processing Status claim keeps one authorized cycle from being requested twice.
- An exception raised by a worker, rather than a typed result, propagates unhandled; the workers already convert their failures into typed results.
- No red check: the dispatcher module and the keyword did not exist at the base.
- Not implemented, by design (RW-O03): `sdlc worker run`, polling, sleep, the runner lock, Processing Status field reads and writes, the reset automation, the eligible-Requirement query, CLI composition of real workers.
- No Proposed Change Request.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-O03 — Implement state-change trigger entrypoint

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `38f702d3c2bae189192c9db343ac8789aceb4fb9`  
**Implementation Evidence:**

- AC1 — a relevant State change causes the correct dispatcher invocation, with no manual command.
  - `tests/test_requirement_runner.py`: `test_a_human_state_change_alone_starts_the_right_worker`. A human Raw Draft → Process, Standard Ready → Process and Standard Ready → Apply, with the modelled Fibery reset, start exactly the RAW Processor, Standard Process and Apply on the next cycle. Before the change the same Requirement is `IDLE`.
  - Real workers through the runner:
    - `test_raw_process_completes_with_its_candidates_progressed_and_succeeds`: RAW Review / `Succeeded`; the produced candidate is in Process at `Not Processed`.
    - `test_review_reaches_ready_and_succeeds_whatever_the_verdict`: PASS, NEEDS_WORK and BLOCKING all reach Ready / `Succeeded`.
    - `test_apply_reaches_applied_and_succeeds`.
    - `test_standard_process_hands_off_to_review_and_leaves_the_reset_intact`.
    - `test_regression_succeeded_is_never_written_over_the_review_cycle_reset`: Process → Review → Ready in consecutive cycles, with no idle sleep between them.
  - Selection:
    - `test_the_lowest_public_id_runs_first_and_work_drains_without_an_idle_sleep`;
    - `test_the_numerically_lowest_public_id_wins_whatever_order_the_page_has`;
    - `test_one_cycle_dispatches_exactly_one_worker_and_asks_to_query_again`.
  - CLI: `tests/test_cli_worker.py::test_a_state_driven_apply_runs_without_a_manual_command`. `sdlc worker run` applies a Requirement in Apply through the real handler, runner, lock and Apply worker.
- AC2 — an irrelevant State change causes no worker mutation.
  - `test_no_eligible_work_dispatches_nothing_and_sleeps_the_default_interval` covers the 8 no-route Type/State pairs.
  - `test_a_polled_row_whose_own_values_select_no_route_is_never_claimed`: the same 8 pairs forged into the poll get no read, no write and no worker, because `select_route` decides every row.
  - `test_a_polled_row_at_any_other_status_is_never_claimed`.
  - `test_a_change_between_the_poll_and_the_claim_starts_no_worker`: a change to State, to State of another route, to Type, status, Project or Requirement ID gives `CANDIDATE_CHANGED` and zero writes.
  - `test_a_candidate_that_no_longer_exists_is_not_claimed`.
- AC3 — a duplicate or replayed trigger does not duplicate a durable outcome.
  - Replay:
    - `test_a_claimed_or_settled_cycle_is_never_run_again`: 4 routes × Processing, Succeeded and Failed are idle with zero writes.
    - `test_a_worker_owned_transition_never_replays_its_worker`: each route's worker runs once, and Standard Process hands off to one Review.
    - `test_failed_work_is_never_retried_automatically`.
    - `test_an_abruptly_terminated_cycle_is_never_stolen`.
    - `test_a_failed_final_status_write_does_not_run_the_worker_again`.
  - Claim:
    - `test_processing_is_written_and_confirmed_before_the_worker_starts`;
    - `test_a_claim_that_cannot_be_written_starts_no_worker`;
    - `test_a_claim_that_is_not_confirmed_starts_no_worker_and_writes_nothing_else`: a lost write, a read-back failure, or a concurrent State change, which is left unrepaired.
  - Guard: `tests/test_worker_runner_guard.py`, 16 tests.
    - The first runner holds the lock; a second fails immediately, in-process and cross-process.
    - Different workspaces and the per-RAW locks do not collide.
    - The lock is released on normal exit, on an exception, on release by the holder and on SIGKILL.
    - A worker's child process does not inherit it.
    - The file is empty and names no workspace.
    - No flock, an unusable directory, or an unexpected flock error fails closed.
  - CLI: `tests/test_cli_worker.py::test_a_second_runner_is_refused_visibly_and_touches_nothing`.
- AC4 — failed worker execution never reports lifecycle completion.
  - `test_a_worker_failure_is_failed_in_the_claimed_state` and `test_a_normal_result_without_its_transition_is_failed_not_completed`: 4 routes each; `Failed` is confirmed in the claimed State.
  - `test_a_raw_progression_failure_is_failed_in_review_and_nothing_rolls_back`: for a conflict, a failed first write and a failed later write, the RAW is `Failed` in Review, progressed candidates stay, and nothing is demoted.
  - These give `PARTIAL`, with the status left as observed:
    - `test_a_read_failure_after_the_worker_guesses_no_final_status`;
    - `test_a_route_gone_stale_after_the_claim_runs_nothing_and_guesses_nothing`;
    - `test_a_final_status_that_cannot_be_confirmed_is_partial` (4 interleavings);
    - `test_a_handoff_into_an_unexpected_state_is_partial_and_writes_nothing`;
    - `test_a_dispatch_without_a_route_is_partial_and_writes_nothing`.
  - `test_a_reset_not_observed_after_the_handoff_is_reported_and_never_written`: `RESET_NOT_OBSERVED`, no Succeeded, and Review does not start until the reset arrives.
  - Red check on a scratch copy of `src` that writes Succeeded after Standard Process: `test_standard_process_hands_off_to_review_and_leaves_the_reset_intact` and the regression test fail (`RESET_NOT_OBSERVED` ≠ `HANDED_OFF`). Both pass on `38f702d`.
- AC5 — trigger or poll data never becomes product truth when current Fibery state disagrees.
  - `test_a_poll_row_the_current_fibery_state_contradicts_is_not_trusted`: a poll row claiming Apply / `Not Processed` for an Applied Requirement gives `CANDIDATE_CHANGED` and zero writes.
  - The fresh re-read and claim read-back tests above; the dispatcher's own revalidation in `test_a_route_gone_stale_after_the_claim_runs_nothing_and_guesses_nothing`.
  - `sdlc worker run` takes no payload, Requirement, Project, Type, State, status, runtime, model, approval, force or daemon argument: `test_no_override_flag_exists`, 13 cases.
- Processing Status adapter (`FiberyRawProcessorWorkspace`, stub transport):
  - `test_http_processing_status_is_resolved_from_the_schema_and_read_back`;
  - `test_http_the_field_is_found_by_its_name_not_by_an_assumed_prefix`;
  - `test_http_the_option_set_is_read_from_the_fields_option_database`;
  - `test_http_a_wrong_option_set_is_rejected`: missing, fifth, renamed, duplicated;
  - `test_http_a_missing_field_fails_only_the_runner_preflight`;
  - `test_http_a_field_that_is_not_a_single_select_is_never_read_or_written`: multi-select, text, non-enum;
  - `test_http_the_eligible_query_filters_routes_and_status_in_public_id_order`;
  - `test_http_a_status_write_resolves_the_option_entity_then_updates_the_field`;
  - `test_http_an_unknown_status_option_is_refused_before_any_write`;
  - `test_http_existing_reads_are_unchanged_without_the_field`.
  - The existing `tests/test_fibery_requirement_http.py` and `tests/test_fibery_http.py` pass unchanged.
- CLI (`tests/test_cli_worker.py`):
  - The interval defaults to 5, the minimum is 1, and `0`, `-1`, `1.5`, `five`, empty and `1e1` are rejected.
  - The configured workspace is used.
  - The three model roles are resolved from `config/sdlc.toml` before the lock is taken, and no model is launched.
  - A preflight failure, a runtime configuration error and missing Fibery configuration claim nothing.
  - Ctrl-C exits 130 and leaves an in-flight claim at Processing.
  - Output carries identity and codes: not the title, not the Root Document prose, not the token.
  - Idle cycles print nothing.
  - Every test ends the loop through an injected stop, never a wait.
- Focused: `uv run pytest -q` over 27 files → 819 passed:
  - `tests/test_requirement_runner.py tests/test_worker_runner_guard.py tests/test_cli_worker.py tests/test_cli_apply.py`
  - `tests/test_fibery_http.py tests/test_fibery_requirement_http.py`
  - `tests/test_lifecycle_control.py tests/test_requirement_dispatcher.py`
  - `tests/test_raw_processor.py tests/test_raw_processor_cross_stage.py tests/test_raw_processor_resume.py tests/test_raw_processor_validation.py tests/test_raw_single_writer.py`
  - `tests/test_requirement_apply.py tests/test_requirement_apply_resume.py tests/test_requirement_apply_validation.py`
  - `tests/test_standard_processor.py tests/test_standard_processor_concurrency.py tests/test_standard_processor_iterations.py tests/test_standard_processor_state_machine.py tests/test_standard_process_abstraction.py tests/test_standard_process_explicit_resume.py tests/test_standard_process_review_chain.py`
  - `tests/test_standard_reviewer.py tests/test_standard_reviewer_state.py tests/test_standard_review_abstraction.py tests/test_standard_review_contract.py`
- Full: `uv sync --locked && uv run ruff check . && uv run ruff format --check . && uv run pytest -q` → All checks passed; 155 files already formatted; 1994 passed. The 160 new tests account for the difference from RW-O02's recorded 1834.

**Blocker:** —  
**Execution Notes:**

- Base `fdfa391`; IMPLEMENTING mark `73efeab`; implementation `38f702d`. Status moved from `BLOCKED` to `IMPLEMENTING` because the blocker `RW-C04` is verified and the RW-O03 boundary is frozen at `fdfa391`. The frozen normative text is unchanged.
- Changed files:
  - New: `src/sdlc/requirement_runner.py`, `src/sdlc/worker_runner_guard.py`, `docs/fibery/Worker-Runner-Setup-v0.1.md`, `tests/test_requirement_runner.py`, `tests/test_worker_runner_guard.py`, `tests/test_cli_worker.py`.
  - Supporting edits: `src/sdlc/cli.py`, `src/sdlc/fibery_http.py`, `src/sdlc/fibery_workspace.py`, `docs/fibery/Fibery-Schema-v0.1.md`, `README.md`.
  - Unchanged: no dispatcher, worker, prompt, evidence-format, Review or Apply code. `tests/processor_fake.py` is untouched; the status fake wraps it.
- Runner interface:
  - Functions: `run_requirement_runner(workspace, workers, *, sleep, report, should_continue, poll_interval_seconds=5, on_started=None)`, `run_cycle(workspace, workers) -> CycleReport`, `finalize_cycle(workspace, claimed, dispatch_result) -> CycleReport`, `preflight(workspace)` and `require_poll_interval(seconds)`.
  - `CycleOutcome`: `IDLE`, `POLL_FAILED`, `CANDIDATE_READ_FAILED`, `CANDIDATE_CHANGED`, `CLAIM_FAILED`, `CLAIM_NOT_CONFIRMED`, `SUCCEEDED`, `HANDED_OFF`, `RESET_NOT_OBSERVED`, `FAILED`, `PARTIAL`.
  - `RunnerCode`: `WORKER_RUNNER_STARTED`, `WORKER_RUNNER_CONFIGURATION_INVALID`, `WORKER_RUNNER_BUSY`, `WORKER_RUNNER_GUARD_UNAVAILABLE`, `WORKER_RUNNER_PREFLIGHT_FAILED`, `WORKER_RUNNER_STOPPED`.
- Workspace interface: `RunnerWorkspace(DispatchWorkspace)` adds `lock_scope`, `validate_processing_status_field(options)`, `find_eligible_requirements(routes, status)` and `set_processing_status(entity_id, status)`.
  - The status is read back through `read_requirement` into the new optional `RequirementRecord.processing_status`, which defaults to None.
  - The HTTP adapter resolves the Field from the schema by its label, `processing status`.
  - It selects and writes the Field only when the schema shows a single-select: the option type carries `fibery/enum?` and the Field is not `fibery/collection?`. Otherwise every existing read is byte-identical.
- Poll and query:
  - One `fibery.entity/query` on the Requirement Database per cycle: `q/where` is status `= Not Processed` AND a `q/or` of the four Type+State pairs, `q/order-by` is `fibery/public-id` ascending, and `q/limit` is 100 (`ELIGIBLE_QUERY_LIMIT`).
  - The runner filters the page through `select_route` and takes the numerically lowest public id.
  - It sleeps the idle interval only after `IDLE`, `POLL_FAILED`, `CANDIDATE_READ_FAILED`, `CLAIM_FAILED` and `CLAIM_NOT_CONFIRMED`. After any other cycle it queries again at once.
  - Cost of a worker cycle: the poll, the re-read, the claim write and its read-back, the dispatcher's own reads, one read before the final write, the final write and its read-back. The client paces every request.
- Guard: `worker_runner_guard.hold_workspace(scope)`.
  - Key: SHA-256 of the normalized workspace identity plus the fixed purpose `sdlc worker run`.
  - File: `worker-runner-<key>.lock` in the per-RAW guard's lock directory (`~/.sdlc/locks`, or `SDLC_LOCK_DIR`). It is opened with `O_CLOEXEC` and locked with `LOCK_EX|LOCK_NB`, stays empty and is never unlinked.
  - `raw_execution_guard.py` is not modified; its constants and directory function are imported.
- Live Fibery, at this implementation commit: NOT configured and NOT verified. No live probe had been run, and the tests use fakes and a stub transport only.
- Live Fibery, verified afterwards on 2026-09-12 by the CR-003 probe (evidence commit of that probe; RW-O03 runtime code unchanged): the field, its four options, the default, the eligible query and the reset automation all behave as the stub tests assume. Recorded in `docs/fibery/Fibery-API-Constraints-v0.1.md` constraint 28 and under `CR-003`.
  - The probe ran on a disposable Project and two disposable Requirements, deleted afterwards and confirmed absent. No production Requirement took part.
  - One correction: the schema does expose the configured default as `fibery/default-value`, which resolved to `Not Processed`. RW-O03 still does not validate the default, which its boundary allows; `docs/fibery/Worker-Runner-Setup-v0.1.md` no longer claims the schema hides it.
  - `FIBERY_SPACE_ID` is empty in the local `.env`, so `sdlc worker run` cannot start from that configuration until the operator sets it. The probe built settings directly and discovered the Space id read-only from existing Requirement Document views.
- Verified live by that probe, having been assumed from Fibery's public schema representation:
  - single-select detection by `fibery/enum?` and `fibery/collection?`;
  - `q/or` inside `q/where`;
  - `q/order-by` on `fibery/public-id`, honoured in both directions.

  Ordering was exercised with two-digit public ids only, so numeric versus text ordering of the public id remains unknown. The runner re-orders the page numerically anyway. With more than 100 eligible rows the lowest id could fall outside the page; it is drained on a later poll. A wrong schema assumption fails closed at preflight.
- Existing Requirements whose Processing Status is empty are not eligible until a State change into a machine State triggers the reset. The setup document says so.
- Two functions that were already over 40 lines grow slightly and are not refactored here:
  - `cli.build_parser`, by 2 lines, because the worker parser lives in `_add_worker_commands`;
  - `FiberyRequirementWorkspace._resolve_requirement_schema`, by 6 lines.
- Not implemented, by design:
  - the RW-O04 end-to-end lifecycle test;
  - any retry, reset, lease, heartbeat, TTL or stale detection;
  - automatic creation of the Fibery automation;
  - daemonizing.
- Proposed Change Request: `CR-003`, a live probe of the Processing Status adapter semantics before production use.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-O04 — Requirement lifecycle end-to-end automation test

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `ce3aad07feb32a698ab908a3575ccb0263ce9cc6`  
**Implementation Evidence:**

Both scenarios live in `tests/test_requirement_lifecycle_e2e.py` and drive the real stack only: `requirement_runner.run_cycle` -> RW-O02 dispatcher -> the real RAW Processor, Standard Process, Standard Review and deterministic Apply. The doubles are the existing Fibery fake, one bounded `FakeModelRuntime` per role, and the RW-O03/CR-003 reset automation. No CLI command is invoked anywhere in the journey.

- AC1 — state-driven machine processing. `test_the_complete_state_driven_requirement_lifecycle` runs the whole journey as repeated `run_cycle` calls, with the human appearing only as three State writes (`Raw Draft -> Process`, `Ready -> Process`, `Ready -> Apply`). Each stage is asserted through its own typed result: `RAW_REQUIREMENT_PROCESSED` (RAW claimed, Processing Result persisted, candidate created, `Process -> Review`, `Succeeded`), the RW-O02 inherited progression of exactly that result's candidate (`progressed == (candidate,)`, `Draft -> Process`), `REQUIREMENT_PROCESSED` iteration 1, `REQUIREMENT_REVIEWED`, and `REQUIREMENT_APPLIED`. The claim precedes every worker write: the first mutation of each cycle is `set_processing_status <id> Processing`.
- AC2 — human boundary observable and uncrossable. Phase 1: a cycle at Raw Draft returns `IDLE` with a byte-identical mutation log and no model call. Phase 4: two consecutive cycles at Ready return `IDLE` with identical Document and Requirement snapshots, and Ready advances only after the test performs the human State write. The scenario never inspects the Review verdict as authority; `PASS` is the incidental outcome of the bounded review response.
- AC3 — rework history preserved. Process Result 1 and Review Result 1 are captured by node id and body before the unedited `Ready -> Process`. After iteration 2 of both stages, those ids still exist and their bodies are byte-identical, and artifact names parse to iterations `[1, 2]` for Process and Review. This is CR-002 proven across the full runner stack: `worker_result.iteration == 2` with the model invoked exactly once for it, although the normative tree still equalled iteration 1's output.
- AC4 — Apply revalidates the reviewed state. Unchanged reviewed content reaches `REQUIREMENT_APPLIED` / `Applied` / `Succeeded`. `test_stale_reviewed_content_fails_closed_on_state_driven_apply` reaches Ready through runner cycles, performs `Ready -> Apply`, edits the reviewed Root content, and the next cycle returns `WORKER_FAILED` with `REVIEW_RESULT_STALE`; State stays `Apply` and no relation edge is written. Red check B (Apply's staleness comparison disabled on a scratch copy of `src`) fails that scenario, proving it is gated on Apply's own validation.
- AC5 — replay duplicates nothing. Extra cycles at Ready (two) and after Applied (three) all return `IDLE` and leave Document, Requirement and relation snapshots identical. Across the journey the RAW cycle stays singular: one Processing Result with an unchanged body, `produces(raw)` unchanged, and one RAW model call. Final durable counts: 1 Processing Result, 1 candidate, 2 Process Results, 2 Review Results, unchanged edges.
- AC6 — Processing Status semantics visible. The O04 fake appends `automation_reset <id> Not Processed` to the same ordered mutation log as the runner's writes, so the sequence `State transition -> automation reset -> Processing claim -> final status` is assertable. The Standard's full history is asserted exactly: `[Not Processed, Processing, Not Processed, Processing, Succeeded, Not Processed, Processing, Not Processed, Processing, Succeeded, Not Processed, Processing, Succeeded]`; the RAW's is `[Not Processed, Processing, Succeeded]`; the stale scenario ends `[Not Processed, Processing, Failed]`. The Process -> Review cycle is pinned further: its slice starts with the claim, ends with the automation reset, and contains no `Succeeded` write.
- AC7 — failure does not advance State. The stale Apply cycle settles `Failed` while the Requirement stays in `Apply`, writes no relation and creates no artifact; two further cycles return `IDLE` with identical Documents, so `Failed` is never retried.

**Blocker:** — (`RW-O03` is reviewer-verified: `docs/rewrite/RW-O03-Verification-v0.1.md`, 2026-09-12)  
**Execution Notes:**

- Base `7ab2a5d`; IMPLEMENTING mark `be6fe07`; implementation `ce3aad0`.
- Status moved `BLOCKED -> IMPLEMENTING` because the blocker `RW-O03` was verified and merged before work began. That transition is outside the frozen implementation-agent list, the same administrative deviation class the RW-O03 verification recorded; no frozen normative text changed.
- Changed files: `tests/test_requirement_lifecycle_e2e.py` only. No production file changed, which is the boundary's expectation; the composed lifecycle satisfied the frozen contract with no correction.
- Two scenarios, 382 lines: `test_the_complete_state_driven_requirement_lifecycle` and `test_stale_reviewed_content_fails_closed_on_state_driven_apply`.
- The O04-only `LifecycleWorkspace` subclasses RW-O03's `StatusWorkspace` purely to append the automation reset to the ordered mutation log. Reset targets and non-targets are RW-O03's, which CR-003 verified live. No worker transition is faked and no replay marker exists in the fake.
- Model use is bounded and deterministic: RAW 1 call, Standard Process 2, Standard Review 2, Apply model-free. No live Fibery, runner process, `.env`, wall-clock delay or live model is involved.
- Red checks on scratch copies of `src`, with the repository untouched: (A) the runner writing `Succeeded` after Standard Process fails both scenarios; (B) disabling Apply's staleness check fails the stale scenario. The unpatched control passes.
- Gates: dedicated E2E `2 passed`; focused Block C over 32 files `977 passed`; full `uv sync --locked`, `ruff check .`, `ruff format --check .` (158 files), `pytest -q` `1996 passed`.
- Not claimed here, by design: live Fibery and live model behaviour (RW-O03/CR-003 owns that evidence), CLI surfaces, multi-candidate RAW decomposition, and Block B abstraction quality.
- No Proposed Change Request.

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

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `a686beb312059405a9b229ffb7a679badb9bb946`  
**Implementation Evidence:**

All evidence is in `tests/test_consumer_template.py` (70 tests) over `src/sdlc/consumer_template.py`. The suite reads the frozen block back out of `docs/rewrite/RW-B01-Template-Manifest-v0.1.md`, so the module is compared against RW-B01 itself rather than against a second copy of the same typing.

- AC1 — the manifest equals RW-B01. `test_the_managed_manifest_is_exactly_the_four_b01_paths` pins `MANAGED_PATHS` to `.sdlc/project.yaml`, `.sdlc/project-context.md`, `AGENTS.md`, `.claude/CLAUDE.md`; `test_the_static_template_paths_are_the_two_agent_guidance_files` pins the static pair as a strict subset and keeps the descriptor (RW-B03) and the context (RW-B04) out of it; `test_there_are_no_optional_paths` pins the empty optional set; `test_the_markers_are_exactly_the_frozen_ones` and `test_the_managed_block_is_exactly_the_block_rw_b01_froze` compare the markers and the whole block against the manifest text.
- AC2 — no undeclared template file. `test_the_module_declares_no_path_outside_the_manifest` collects every module constant whose name ends in `_PATH`/`_PATHS` and requires the set to equal `MANAGED_PATHS`. The seven RW-B01 section 3 excluded paths are asserted absent from the managed and static sets, from the block, and from every materialized output (`test_no_excluded_runtime_or_agent_path_is_managed`, `test_the_block_never_points_at_an_excluded_runtime_path`, `test_no_materialization_introduces_an_excluded_path_or_placeholder`). The module creates nothing at all: `test_the_module_imports_nothing_that_could_reach_the_world` parses its AST and requires imports to be a subset of `__future__`, `dataclasses`, `enum`, so there is no filesystem, Fibery or bootstrap reach.
- AC3 — placeholder substitution points are explicit and tested, and the frozen answer is none. `TEMPLATE_PLACEHOLDERS == ()` (`test_the_frozen_placeholder_set_is_empty`), `test_the_static_block_carries_no_dynamic_placeholder` rejects `{`, `}`, `${`, `%s`, `%(`, `<<` and `{{` inside the block, and no materialized output introduces one. No placeholder was invented to satisfy the criterion.
- AC4 — no secret or account-specific value. `test_the_block_carries_no_credential_or_account_value` rejects `token`, `api_key`, `apikey`, `password`, `secret`, `bearer`, `sk-` and `fibery_` in the block. The module contains no host, account id, model, provider, endpoint, approval, permission, sandbox or environment value; its only mention of such settings is the RW-B01 instruction that project-local guidance must not override the user's global configuration.
- Merge semantics, each pinned by tests: absent and empty materialize the block plus one terminating LF; foreign UTF-8 content is preserved byte for byte with a one-blank-line separation (`no final newline`, `one`, `two` and `three` trailing newline cases); CRLF is used for appended material only when the file is CRLF throughout, and mixed endings keep LF; an exact block is `COMPATIBLE` and the supplied bytes are returned unchanged, including the CRLF rendering and with foreign content before, after or both sides preserved; a rerun over an appended file classifies `COMPATIBLE` with exactly one BEGIN marker, so nothing doubles.
- Conflicts fail closed with no bytes: BEGIN only, END only, reversed markers, duplicate BEGIN, duplicate END, invalid UTF-8, and six near-miss blocks (changed wording, whitespace-only, removed blank line, reordered bullets, dropped bullet, changed capitalization). `test_a_conflict_reason_names_the_class_and_never_echoes_the_file` proves the reason names only the class, stays under 80 characters and does not echo file prose.
- Red check: against `src` from the pre-B02 baseline `ef287f0`, the suite fails at collection with `ImportError: cannot import name 'consumer_template' from 'sdlc'`; on `a686beb` it passes. No test was weakened to manufacture a red count.
- Gates: dedicated `70 passed`; unrelated CLI/project-init/requirement-add/project-code suites `111 passed`; full `uv sync --locked`, `ruff check .`, `ruff format --check .` (164 files), `pytest -q` `2066 passed`.

**Blocker:** — (reviewer-authorized dependency clearance: `RW-B01` is VERIFIED in `docs/rewrite/RW-B01-Verification-v0.1.md`, and `docs/rewrite/RW-B02-Implementation-Boundary-v0.1.md` section 12 authorizes implementation)  
**Execution Notes:**

- Base `ef287f0`; IMPLEMENTING mark `90b6b4b`; implementation `a686beb`.
- The `BLOCKED -> IMPLEMENTING` transition is the reviewer-authorized dependency clearance above, not a semantic plan change; the frozen RW-B02 text is unchanged.
- Changed files: new `src/sdlc/consumer_template.py` (221 lines) and `tests/test_consumer_template.py` (391 lines). No other production file changed and no documentation change was needed.
- Public API: the path constants `DESCRIPTOR_PATH`, `CONTEXT_PATH`, `AGENTS_GUIDANCE_PATH`, `CLAUDE_GUIDANCE_PATH`, the sets `MANAGED_PATHS`, `STATIC_TEMPLATE_PATHS`, `OPTIONAL_PATHS`, `TEMPLATE_PLACEHOLDERS`, the template constants `BEGIN_MARKER`, `END_MARKER`, `MANAGED_BLOCK`, the vocabularies `GuidanceDisposition` (`ABSENT`, `APPENDABLE_FOREIGN_CONTENT`, `COMPATIBLE`, `CONFLICT`) and `ConflictReason` (seven bounded classes), the frozen dataclasses `GuidanceClassification` and `GuidancePlan` (`disposition`, `content`, `reason`, `is_conflict`, `requires_write`), and the functions `managed_block_bytes`, `classify_agent_guidance`, `plan_agent_guidance`.
- Empty existing content is reported as `ABSENT` because its materialization is identical to an absent file; RW-B04 keeps the filesystem distinction it can see. No fifth disposition was invented.
- The appended form is existing bytes plus the separator plus the block, exactly as RW-B01 section 8.2 states; only the absent and empty cases add the terminating LF that RW-B01 section 8.1 requires.
- Nothing in the repository imports the module yet. RW-B04 is its first caller by design, and RW-B02 adds no call site of its own.
- No Proposed Change Request.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-B03 — Implement project descriptor contract

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `4189f2c273799d44286ef8f7f135cd9099705c01`  
**Implementation Evidence:**

All evidence is in `tests/test_project_descriptor.py` (126 tests) over `src/sdlc/project_descriptor.py`. Everything is exercised as values and bytes; the module has no filesystem, Fibery, environment or model reach.

- AC1 — validation rejects missing mandatory identity and configuration. Every one of the six frozen top-level groups is removed in turn and refused as `MISSING_KEY` (`test_a_missing_mandatory_group_is_refused`), as is each nested key of the multi-key groups (`project.name`, `project.code`, `repository.root`, `repository.branch_policy`, `standards.profile`, `standards.extensions`). The single-key `fibery` group is covered by both of its failure shapes: substituting the key gives `MISSING_KEY`, emptying the block gives `INVALID_SYNTAX` (`test_the_single_key_fibery_group_refuses_both_of_its_failure_shapes`). Identity invariants are refused individually: blank name, invalid Project Code, `PROJECT_CODE_MISMATCH` for a `fibery.project_code` that differs, a root other than `.` including absolute and sub-paths, invalid policy/profile/extension/check identifiers, duplicate check names and extensions, and blank, multiline or NUL commands. Structure is refused too: unknown keys at top level and in every nested group, duplicate keys at top level, nested and inside a check item, wrong scalar/list/mapping types, an unsupported `version`, and ten malformed-syntax shapes (`test_malformed_syntax_is_refused_rather_than_guessed`).
- AC2 — the descriptor is generated from bootstrap inputs. `new_project_descriptor(project_name, project_code)` produces exactly the frozen default (`test_the_default_descriptor_is_exactly_the_frozen_bootstrap_value`): version 1, trimmed name, validated Code mirrored into `fibery.project_code`, `repository.root = "."` with all three policies null, no checks, and null profile with no extensions. The name is trimmed (`test_the_project_name_is_trimmed`), a blank name is refused, and the Code goes through the existing `sdlc.project_code.validate_project_code` rather than a second format rule (`test_the_project_code_follows_the_existing_validator`). `test_generation_accepts_no_input_beyond_name_and_code` pins the signature, so no description, context, RAW source, repository inspection or environment value can enter.
- AC3 — reruns are semantically stable. Generation is deterministic, `parse(render(x)) == x` and `render(parse(render(x))) == render(x)` hold for the default and a fully populated descriptor, and unchanged inputs render byte-identically even when supplied with different surrounding whitespace or casing of the Code (`test_unchanged_inputs_generate_byte_identical_descriptors`). Compatibility is a pure comparison: the canonical bytes are compatible, and so are the accepted formatting variants (CRLF, blank lines, no final newline) without any rewrite, which is what lets RW-B04 reuse an existing file (`test_accepted_formatting_differences_stay_compatible`, `test_compatibility_never_rewrites_or_merges`). Any semantic difference — name, Code and its mapping, repository policy, checks, standards — and any invalid descriptor conflicts.
- AC4 — no credential or canonical Requirement surface exists. The schema is closed, so twenty shadow keys are refused as `UNKNOWN_KEY`, covering tokens, API keys, passwords, secrets, OAuth, model and provider selection, provider endpoint, approval/permission/sandbox/edit modes, `requirements`, `raw_source`, `state`, `processing_status`, architecture, epics and tasks (`test_every_shadow_configuration_key_fails_as_unknown`). The `fibery` group accepts nothing but `project_code`: host, space id, token and project UUID are all refused (`test_the_fibery_group_accepts_nothing_but_the_project_code`). Diagnostics name a key path or line and never echo a value, proven with a descriptor carrying sensitive prose in its project name (`test_a_diagnostic_names_the_location_and_never_the_content`).
- Red check: against `src` from the pre-B03 baseline `916d1416`, the suite fails at collection with `ImportError: cannot import name 'project_descriptor' from 'sdlc'`; on `4189f2c` it passes. No test was weakened to manufacture a red count.
- Gates: dedicated `126 passed`; focused regressions over `test_consumer_template`, `test_project_code`, `test_project_init`, `test_project_init_failures` and `test_cli` `156 passed`; full `uv sync --locked`, `ruff check .`, `ruff format --check .` (169 files), `pytest -q` `2192 passed`.

**Blocker:** — (reviewer-authorized dependency clearance: `RW-B01` is VERIFIED in `docs/rewrite/RW-B01-Verification-v0.1.md`, and the exact schema and boundary are frozen in `docs/rewrite/RW-B03-Project-Descriptor-Contract-v0.1.md` and `docs/rewrite/RW-B03-Implementation-Boundary-v0.1.md`)  
**Execution Notes:**

- Base `916d1416`; IMPLEMENTING mark `9b80fd6`; implementation `4189f2c`.
- The `BLOCKED -> IMPLEMENTING` transition is the reviewer-authorized dependency clearance above, not a semantic plan change; the frozen RW-B03 text is unchanged.
- Changed files: new `src/sdlc/project_descriptor.py` (578 lines) and `tests/test_project_descriptor.py` (607 lines). No other production file changed and no documentation change was needed.
- Public API: the value objects `ProjectDescriptor`, `ProjectIdentity`, `FiberyMapping`, `RepositoryConfig`, `ProjectCheck` and `StandardsConfig`, all frozen dataclasses so descriptor equality is semantic equality; the constants `DESCRIPTOR_VERSION`, `REPOSITORY_ROOT`, `IDENTIFIER_PATTERN`, `TOP_LEVEL_KEYS` and the per-group key tuples; the vocabularies `DescriptorProblem` (`invalid encoding`, `invalid syntax`, `missing key`, `unknown key`, `duplicate key`, `invalid value`, `unsupported version`, `project code mismatch`) and `InvalidProjectDescriptor(problem, location)`; and the functions `new_project_descriptor`, `render_descriptor`, `parse_descriptor` and `descriptor_compatible`.
- Grammar boundary: the parser reads the canonical form plus three harmless variations that are explicitly tested — CRLF line endings, blank lines and a missing final newline. Scalars are only a JSON-compatible double-quoted string, `null`, a non-negative integer or `[]`. Tabs, non-two-space indentation, comments, unquoted scalars, a key with both an inline value and an indented block, and a key with no value at all are refused as `INVALID_SYNTAX`. It is not a general YAML implementation and adds no runtime dependency: `json` and `re` from the standard library plus `sdlc.project_code` are the only imports, pinned by `test_the_module_imports_only_the_standard_library_and_project_code`.
- Canonical serialization: UTF-8, LF, exactly one final LF, frozen key order, JSON-compatible quoted string scalars for escaping without a YAML dependency, `[]` for empty lists, and check and extension order preserved rather than sorted.
- Compatibility returns a plain bool, since RW-B01 gives the descriptor whole-file ownership and a conflict stops bootstrap; a caller wanting the class of problem calls `parse_descriptor` directly and reads `InvalidProjectDescriptor.problem`.
- `consumer_template.DESCRIPTOR_PATH` is deliberately not imported: RW-B03 never touches a path, so the coupling would buy nothing. B02 and B03 remain separate pure contracts.
- Not implemented, by design: file materialization, target preflight, symlink safety, Project Code collision resolution, Fibery lookup, project-context copying, `sdlc project bootstrap`, B04 composition, B05, and any execution of a check, policy or standards profile.
- No Proposed Change Request.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-B04 — Implement one outer project bootstrap action

**Status:** IMPLEMENTED_UNVERIFIED  
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

**Implementation Commit:** `7a4c6b2d6117545768d56694d4b4827fda7f4684`  
**Implementation Evidence:**

All evidence is in `tests/test_project_bootstrap.py` (50 tests) and `tests/test_cli_bootstrap.py` (29 tests), which run the real composition — real `project_init`, real `requirement_add`, the real B02 template and the real B03 descriptor — over the existing in-memory Fibery fakes and real temporary directories. No model, live Fibery or subprocess is involved.

- AC1 — one user action initializes an empty or new target. `test_an_empty_existing_target_is_bootstrapped_completely` drives one `bootstrap_project` call and asserts the whole composition: the four managed artifacts exist and nothing else, the descriptor parses equal to `new_project_descriptor(name, code)`, the context is byte-identical, both guidance files carry the frozen block, Project Init reports `PROJECT_INITIALIZED`, Requirement Add reports `RAW_REQUIREMENT_ADDED`, and Fibery holds one Project and one Requirement in `Raw + Draft`. `test_an_absent_final_target_directory_is_created` covers the absent final directory, and `test_an_absent_target_parent_fails_before_any_mutation` proves ancestors are never created recursively.
- AC2 — both target modes. `test_the_current_directory_is_the_target_when_none_is_given` bootstraps into the process working directory with no target argument, and `test_an_explicit_target_is_bootstrapped_and_exits_zero` plus `test_the_current_directory_is_used_when_no_target_is_given` prove the same two modes through the real CLI handler.
- AC3 — unrelated files and the frozen per-path policy. `test_unrelated_files_are_untouched_and_guidance_is_appended` keeps `README.md` and `src/example.py` byte-identical while B02 appends the block after existing guidance prose. Reuse is proven for a CRLF-formatted compatible descriptor, an identical context file and an existing frozen block, each reused byte-for-byte. Conflicts stop before any mutation: a differing descriptor, a differing context and two malformed guidance blocks (`test_an_incompatible_managed_file_conflicts_with_zero_mutation`), a symlinked managed file, `.sdlc` or `.claude` (never followed, verified by the link target staying empty), a non-directory managed parent, and a non-directory or symlinked target. `test_no_excluded_runtime_or_agent_path_is_ever_created` proves no `.codex/config.toml`, `.claude/settings.json`, agents/skills directory or `.env` appears, and that the target holds exactly the four managed paths.
- AC4 — rerun is idempotent and non-destructive. `test_a_complete_rerun_changes_nothing_and_reports_already_bootstrapped` reruns the identical inputs and asserts `PROJECT_ALREADY_BOOTSTRAPPED`, all four paths reused, byte-identical local tree, no Fibery mutation on either workspace, one Project, one Requirement and the same Requirement ID. `test_an_existing_compatible_project_is_reused` proves `create_project` is never called when a compatible Project exists.
- AC5 — the initial RAW is added exactly once. The rerun test proves no duplicate Requirement; `test_the_initial_raw_is_validated_against_the_parsed_fingerprint` ties the stored Requirement to the fingerprint parsed in phase 1; `test_bootstrap_never_moves_the_requirement_out_of_draft` proves the only State write in the whole composition is `Draft`.
- AC6 — the exported context is present as the template contract defines. The complete-bootstrap test asserts `.sdlc/project-context.md` is byte-identical to the supplied export, and `test_an_identical_context_file_is_reused_unchanged` proves an existing identical file is reused rather than rewritten. The context is read as opaque bytes and never decoded or normalized.
- AC7 — partial failure is distinguishable and nothing is rolled back. `test_a_project_init_failure_after_local_state_is_partial_and_adds_nothing` gives `PARTIAL_BOOTSTRAP` with the local files left in place and Requirement Add never invoked, and additionally pins the message against the state it reports: all four managed paths are listed in `local_created`, both managed directories are recorded as created, the message does not contain `changed nothing else`, and it does say bootstrap stopped before Requirement Add. `test_a_partial_report_never_claims_that_nothing_local_changed` proves the same of the rendered CLI output, which prints the created paths and the message together; `test_a_requirement_add_failure_is_partial_and_nothing_is_rolled_back` keeps both the Project and the local state; `test_a_local_write_that_does_not_read_back_is_reported_truthfully` fails the read-back guard, reports exactly the three artifacts that became durable and makes no Fibery call. Clean failures with no durable state stay `BOOTSTRAP_FAILED` (invalid RAW export, unreadable input, blank name, absent target parent, Fibery read failure during identity resolution), and pre-existing incompatibility stays `BOOTSTRAP_CONFLICT`.
- Target stability under a race (correction regression): `test_a_target_that_becomes_a_symlink_after_preflight_is_never_written_through` lets the full local preflight see an absent target with a real parent and judge it safe, then replaces it with a symlink to a separate outside directory before materialization. The run completes to a non-normal result with `failed_step = MATERIALIZE_LOCAL`; the symlink is left exactly as found and is never removed; the outside directory holds no `.sdlc`, `.claude`, `AGENTS.md` or any managed file; and neither workspace records a mutation, so Project Init and Requirement Add never ran.
- Code stability under a race (mandatory regression): `test_the_resolved_code_is_never_re_derived_when_it_is_taken_before_init` claims the preflight-resolved Code between preflight and Project Init. The result is `PARTIAL_BOOTSTRAP` with `PROJECT_CODE_COLLISION`, the descriptor still carries the originally resolved Code, Requirement Add never runs, and no Project is created under another Code.
- The read-only Project-Code preflight added to `project_init.py` is covered by nine tests: a supplied free Code is returned, an omitted Code follows the existing derivation and collision walk exactly, invalid/taken Codes and a Fibery read failure map onto the existing `InitResult` codes with an empty journal, a blank Name is `INVALID_INPUT`, the helper writes and creates nothing, and `initialize_project` still resolves its own Code when none is supplied.
- CLI: the command takes exactly `--name`, `--requirements`, `--context`, `--target`, `--code`, `--description`; eleven forbidden flags (model, runtime, force, overwrite, repair, process, start, retry, cleanup, approve, state) are rejected; exit code is zero only for the two normal outcomes; a conflict exits non-zero on stderr; `test_both_workspace_adapters_share_one_client_and_settings` proves one `FiberyClient` builds both adapters from the same settings; the model runtime is never constructed or loaded; and diagnostics carry no RAW body, context body or token.
- Red check: against `src` from the pre-B04 baseline `425817de`, both suites fail at collection with `ModuleNotFoundError: No module named 'sdlc.project_bootstrap'`; on `725f30e` they pass.
- Red check for the correction: against `src` from the reviewed implementation `725f30e3`, the three new or extended regressions give `3 failed, 76 deselected` — the target-race test, the Project Init partial test and the CLI partial report test. The old module contains no `_require_real_target` (0 occurrences) and carries `bootstrap changed nothing else.` at line 832; the corrected module carries `bootstrap stopped before Requirement Add.` at line 861. The old implementation accepts the late-created target symlink because `_ensure_target` opened with `Path.is_dir()`, which follows it.
- Gates: dedicated `79 passed` (50 bootstrap + 29 CLI); focused regressions over consumer template, project descriptor, project code, project init, project init failures, requirement add, requirement add failures and the five CLI suites `445 passed`; full `uv sync --locked`, `ruff check .`, `ruff format --check .` (174 files), `pytest -q` `2271 passed`.

**Blocker:** — (reviewer-authorized dependency clearance: `RW-B02`, `RW-B03` and `RW-C03` are independently VERIFIED, and `docs/rewrite/RW-B04-Implementation-Boundary-v0.1.md` freezes this composition)  
**Execution Notes:**

- Base `425817de`; first implementation `725f30e`; IMPLEMENTING mark `61049ea`; first evidence `54d55ac`; corrective implementation `7a4c6b2` after independent review returned `CHANGES_REQUIRED` on `725f30e`. The original implementation history is preserved; nothing was rewritten or squashed.
- Process deviation, disclosed: the `IMPLEMENTING` mark was overlooked during pre-flight and recorded only after the implementation commit, so the plan carried `BLOCKED` while the work was done. No frozen text was changed and every gate was satisfied before the evidence commit. This is an administrative deviation for reviewer disposition; it was left recorded rather than repaired.
- Correction (`7a4c6b2`), two review findings, no other semantics touched. One: `_ensure_target` began with `Path.is_dir()`, which follows a symlink, so a target that was absent at preflight and became `symlink -> directory` before materialization was accepted and every managed path would have been written through it. The symlink test now precedes the `is_dir()` success path, and `_require_real_target` re-checks the target root before each managed directory and file mutation; a changed target fails closed at `MATERIALIZE_LOCAL`, is never followed or removed, and stops the composition before Project Init and Requirement Add, with the existing `_stopped_result` classification still upgrading the outcome to `PARTIAL_BOOTSTRAP` when durable state from the same attempt exists. Two: the Project Init failure message claimed `bootstrap changed nothing else` even after the normal ordering had created the target, the managed directories and the managed files, contradicting the result payload and the CLI's own created-path report; it now says bootstrap stopped before Requirement Add and that the local state this attempt created is listed and left in place. The inner Project Init result code, the local created/updated/reused fields, the `PARTIAL_BOOTSTRAP` classification and the absence of rollback are all unchanged.
- Changed files: new `src/sdlc/project_bootstrap.py` (988 lines, 1018 after the correction), `tests/test_project_bootstrap.py` (923, 972) and `tests/test_cli_bootstrap.py` (376, 401); narrow supporting edits in `src/sdlc/project_init.py` (+28: one read-only helper) and `src/sdlc/cli.py` (+141: the command, its handler, the shared-client adapters and the renderer). The correction changed exactly the three B04 files and nothing else: `project_init.py`, `cli.py`, `requirement_add.py`, `consumer_template.py`, `project_descriptor.py` and `fibery_http.py` are untouched by it, as are B02 and B03.
- Public API: `bootstrap_project(project_workspace, requirement_workspace, *, name, requirements_path, context_path, target=None, code=None, description=None) -> BootstrapResult`, with `BootstrapCode` (`PROJECT_BOOTSTRAPPED`, `PROJECT_ALREADY_BOOTSTRAPPED`, `BOOTSTRAP_CONFLICT`, `PARTIAL_BOOTSTRAP`, `BOOTSTRAP_FAILED`; only the first two normal), `BootstrapStep` for the bounded failed step, `PathPlan` (`CREATE`, `UPDATE`, `REUSE`, `CONFLICT`) and `ManagedPathPlan`.
- `BootstrapResult` carries target, Project Name/Code, Requirement ID, created/updated/reused managed paths, whether the target and managed directories were created, the inner Project Init and Requirement Add codes, the failed step and sanitized details. It never carries the RAW body, the context body, a document secret or a credential.
- Sequence: read and validate both exports; resolve identity read-only (`find_projects_by_name`, then either the existing Project's validated Code or `preflight_project_code`); resolve the target; build the B03 descriptor; preflight `.sdlc` and `.claude` plus all four managed paths; materialize in the frozen order (target, directories, `AGENTS.md`, `.claude/CLAUDE.md`, descriptor, context); validate locally; invoke Project Init with the resolved Code explicitly; validate the Project identity; invoke Requirement Add with the exact source text; validate the initial RAW.
- Safety: a symlinked target, managed path or managed parent is refused and never followed or removed; every write rechecks the preflighted type, existence and bytes, creates absent files exclusively with `open(path, "xb")`, and is confirmed by read-back; an intervening foreign edit is never overwritten; nothing is ever rolled back. The target root is the ancestor of every managed path, so it is re-checked for symlink-ness before the `is_dir()` success path in `_ensure_target` and again, through `_require_real_target`, immediately before each managed directory creation and each managed file write. That is the whole of the correction: two bounded checks on the target root, not a generalized secure-filesystem or directory-fd layer.
- Not implemented, by design: requirements-export, RAW semantic processing, lifecycle transitions beyond Requirement Add's own `Raw + Draft` creation, model calls, descriptor policy/check/standards execution, repository/remote/branch work, generalized repair or rollback, and the RW-B05 live disposable end-to-end acceptance.
- No Proposed Change Request.

### Verification Record

**Verification:** NOT_RUN  
**Review Evidence:** —  
**Verified Commit:** —

---

## RW-B05 — Bootstrap end-to-end test on disposable project

**Status:** IMPLEMENTING  
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

```text
CR-001
Discovered In: RW-R01
Observation: A model-supplied Standard Requirement title is rendered into the
  document's level-1 title line and the Root Document name, but title
  validation in raw_processing/standard_analysis accepts line breaks. A title
  "T\n## Architecture" renders an extra `## Architecture` section, bypassing
  the structural boundary RW-R01 enforces for section content (verified by
  running parse_model_output(...).document() on such a title).
Why current item cannot/should not absorb it: RW-R01 must preserve Requirement
  ID/title binding and authorizes no change to the title contract of RAW
  decomposition or Standard Process output.
Proposed decision: Reject a model-supplied title containing a line break as
  invalid model output, with tests, in the items that own those output
  contracts (RW-R02 for RAW decomposition, RW-R03 for Standard Process).
Blocking: NO
Status: PROPOSED
```

```text
CR-002
Discovered In: RW-O01
Observation: After a completed Process -> Review -> Ready cycle the current
  normative tree equals the latest Process Result's output tree. A human
  Ready -> Process without an edit therefore reaches Standard Process as
  NO_CHANGES_TO_PROCESS, a normal outcome: no model call, no new iteration,
  State stays Process. --new-iteration-after cannot force a new cycle either,
  because it requires the tree to equal the latest Result's input and differ
  from its output. So the RW-C02 section 9 chain "Process -> Review -> Ready"
  after rework is not reachable for an unedited rework through any existing
  Standard Process mode (pinned by
  test_an_unedited_direct_rework_currently_finds_nothing_to_process).
Why current item cannot/should not absorb it: RW-O01 fixes the authority
  contract only and must not change Standard Process semantics, dispatcher
  routing or Processing Status. The frozen owners are RW-O02 (dispatcher and
  typed result handling) and RW-O03 (runner); RW-O04 proves rework end to end.
Proposed decision: Before RW-O02 fixes its typed-result handling, the human
  decides what an unedited rework means. Options include requiring an edit
  before rework, with the dispatcher reporting NO_CHANGES_TO_PROCESS after a
  rework as a visible non-advancing outcome, or adding an explicit Standard
  Process mode that reprocesses the current tree as a new iteration when it
  is entered from a Ready rework.
Review decision (independent review of RW-O01, CHANGES_REQUIRED):
  Rejected option: require an edit before rework. It contradicts RW-C02
    section 9, under which Ready -> Process means "start a new Standard
    Process cycle using the current Requirement content and preserved
    history"; an edit is not a prerequisite of that authorization.
  Accepted semantic requirement: a human Ready -> Process authorizes a new
    Standard Process cycle even when the normative tree is unchanged.
  Implementation owner: RW-O02/RW-O03. They must provide a bounded way for
    the state-driven worker path to start a new Process iteration over the
    current tree when that cycle was authorized by the human rework
    transition, and it must not become a general force or bypass mechanism.
    RW-O01 designs no dispatcher or processor interface for it.
O02 implementation note (RW-O02, `a1ee1fb`): the dispatcher's
  Standard + Process + Not Processed route invokes Standard Process with the
  keyword-only `authorized_new_cycle`, which processes a tree equal to the
  latest current-format output as the next iteration. The A11 ambiguity,
  empty shells and all checks are unchanged; ordinary and manual calls still
  return NO_CHANGES_TO_PROCESS; no CLI flag exposes it. Automatic invocation
  awaits the RW-O03 runner and its Processing Status claim.
O03 implementation note (RW-O03, `38f702d`): `sdlc worker run` now reaches
  that route automatically. A human Ready -> Process plus the Fibery reset
  makes the Requirement eligible; the runner claims it with Processing and
  dispatches it once, and the claim stops the same authorized cycle from
  being requested twice. The end-to-end rework proof remains RW-O04's.
Blocking: NO
Status: PROPOSED
```

```text
CR-003
Discovered In: RW-O03
Observation: The Processing Status adapter added by RW-O03 relies on Fibery
  behaviour this repository has not probed live:
  - single-select detection by the option type's `fibery/enum?` and the
    Field's `fibery/collection?` schema flags;
  - a `q/or` of Type + State pairs inside `q/where`;
  - `q/order-by` on `fibery/public-id`, whose order (numeric or text) is
    unconfirmed;
  - the option-entity write of the new Field.
  These are pinned only against fakes and a stub transport. The project's
  Fibery integration rule requires, before such semantics are frozen, a
  narrow live probe on temporary state, a fake-versus-live comparison and a
  regression for every discrepancy. No live workspace has the Processing
  Status field or the reset automation yet.
Why current item cannot/should not absorb it: RW-O03 authorizes no live
  workspace change. The field and the reset automation are one-time operator
  configuration (RW-C04 section 27, RW-O03 boundary), and the probe needs
  the field to exist.
Proposed decision: Before RW-O04 relies on the live runner:
  1. The operator adds the field and the automation
     (docs/fibery/Worker-Runner-Setup-v0.1.md).
  2. Run a narrow live probe of the four adapter operations (validate the
     field, find eligible work, set status, read back) on temporary
     Requirements.
  3. Compare the results with the stub expectations in
     tests/test_requirement_runner.py and add a regression for any
     discrepancy.
  4. Record the results in docs/fibery/Fibery-API-Constraints-v0.1.md.
Live probe result (2026-09-12; RW-O03 runtime code unchanged): the probe ran
  and passed. The evidence is constraint 28 of
  docs/fibery/Fibery-API-Constraints-v0.1.md.
  - Field and options: SDLC/Processing Status resolved from the schema by its
    label; option Database SDLC/Processing Status_SDLC/Requirement; options
    exactly Not Processed, Processing, Succeeded and Failed; the real runner
    preflight accepted the workspace.
  - Single-select representation: the option Database carries
    fibery/enum?: true and the Field has no fibery/collection? key, which is
    what the stub tests assume.
  - Read, write and read-back: all four option names round-tripped exactly on
    a disposable Requirement in Draft, and no other Field of it changed.
  - Eligible query: the four-arm q/or, the enum-name status filter and
    q/order-by on fibery/public-id all work live; q/asc and q/desc returned
    the two scratch rows in opposite orders. Numeric versus text ordering of
    the public id stays unknown, and the runner re-sorts numerically anyway.
  - Reset automation: every machine target reset an intentional Failed to
    Not Processed within 0.5 to 2.7 s, while Raw + Review, Standard + Ready
    and Standard + Applied each kept Failed over a 15 s window.
  - One real model-free runner cycle on the Apply route confirmed Processing
    before the worker ran, and Failed after the worker's typed refusal.
  - Correction to the earlier assumption: the schema does expose the
    configured default, as fibery/default-value, which resolved to
    Not Processed. RW-O03 still does not validate the default, which its
    boundary allows, and the setup document no longer claims otherwise.
  - Probe data: a disposable Project and two disposable Requirements, deleted
    afterwards and confirmed absent. No production Requirement took part.
  - Local configuration gap: FIBERY_SPACE_ID is empty in the operator's .env,
    so sdlc worker run cannot start from that configuration until it is set.
    The probe built settings directly and discovered the Space id read-only
    from existing Requirement Document views.
  No adapter correction was needed, so no code changed. Whether this CR is now
  closed remains the human's decision.
Blocking: NO
Status: PROPOSED
```

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
| RW-C01 | Standard Requirement abstraction v0.2 | Human/Reviewer | VERIFIED | — |
| RW-C02 | Requirement lifecycle ownership | Human/Reviewer | VERIFIED | C01 |
| RW-C03 | Project bootstrap contract | Human/Reviewer | VERIFIED | C01 |
| RW-C04 | State-trigger worker contract | Human/Reviewer | VERIFIED | C02 |
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

5. Commit the frozen normative plan to `main`.
6. Record that exact commit SHA in `docs/rewrite/SDLC-Rewrite-Freeze-v0.2.md`. The freeze record is metadata only and does not modify the frozen normative plan.

7. Every implementation prompt must name exactly one `RW-*` item and the frozen Plan Commit from the freeze record.
8. Implementation agent must read that item from the repository at the frozen Plan Commit before modifying code.
9. No implementation item starts from a prose summary supplied in chat when the repository plan is available.

