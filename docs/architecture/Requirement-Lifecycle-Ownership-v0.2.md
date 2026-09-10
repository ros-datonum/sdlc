# Requirement Lifecycle Ownership Contract v0.2

**Status:** DRAFT — RW-C02 HUMAN/REVIEWER CONTRACT  
**Implementation authorization:** NONE  
**Rewrite item:** `RW-C02`  
**Depends on:** `RW-C01 — Standard Requirement Abstraction v0.2`  
**Primary product requirements:** `docs/rewrite/SDLC-Corrected-Product-Functional-Requirements-v0.2.md`

## 1. Purpose

This contract defines **who owns each Requirement lifecycle transition and what that transition means**.

It corrects the current manual-command-oriented operating model without changing the Requirement abstraction defined by `RW-C01`.

The central control rule is:

```text
Human State change
= human intent / authority where a human decision is required

System State change
= result of already-authorized machine-owned processing
```

Automation may execute work that has already been authorized by lifecycle state. It may not manufacture a human approval, rework decision, or new product intent.

---

## 2. State and processing status are different concepts

Requirement lifecycle `State` answers:

> Where is this Requirement in its workflow, and whose decision/work is expected here?

Processing status answers:

> What is the outcome of the machine-processing cycle associated with the current machine-owned stage?

They must not be conflated.

A successful processor/reviewer can therefore produce:

```text
Processing Status = SUCCEEDED
Review Verdict     = BLOCKING
```

without contradiction. `SUCCEEDED` means the worker completed correctly; it does **not** mean the Requirement is approved or semantically good.

The exact Fibery field name and concrete allowed values are owned by `RW-C04`. This contract freezes only the required semantics:

```text
RESET / NOT YET PROCESSED FOR THIS CYCLE
PROCESSING
SUCCEEDED
FAILED
```

---

## 3. Human decision boundaries

The Requirement lifecycle has three human-owned decisions in the rewrite scope:

1. **Start RAW processing** — the human decides that a RAW source is ready to be processed.
2. **Rework a Ready Standard Requirement** — the human decides that the current candidate must be revised and processed again.
3. **Approve a Ready Standard Requirement** — the human authorizes deterministic application of the exact reviewed Requirement state.

No model, reviewer verdict, dispatcher, trigger, or successful prior worker may cross one of these boundaries autonomously.

An authorized assistant may perform the corresponding State change only after an explicit human instruction. The authority remains the human's; the assistant is acting as the control surface on the human's behalf.

---

## 4. RAW Requirement lifecycle ownership

The normal RAW flow is:

```text
create RAW
   |
   | SYSTEM
   v
Draft
   |
   | HUMAN — explicit processing intent
   v
Process
   |
   | SYSTEM — RAW processing succeeds
   v
Review
```

### 4.1 RAW creation -> Draft

Owner: **SYSTEM**.

A newly ingested RAW Requirement starts in `Draft`.

`Draft` means:

- source has been preserved;
- no RAW processing cycle is authorized yet;
- no processor may start solely because the RAW entity exists.

### 4.2 RAW Draft -> Process

Owner: **HUMAN**.

This State change means:

> Process this RAW source now.

It is the authorization for the complete machine-owned decomposition flow produced from this RAW cycle.

Entering `Process` starts a new RAW processing cycle:

```text
Processing Status -> RESET
                   -> PROCESSING when worker begins
```

### 4.3 RAW Process success -> Review

Owner: **SYSTEM**.

The RAW processor may move the RAW Requirement to `Review` only after its required durable processing result has been recorded successfully and the processor's own current-state checks pass.

On success:

```text
RAW Processing Status -> SUCCEEDED
RAW State             -> Review
```

`RAW Review` in this rewrite means the RAW source has completed its current decomposition cycle and is retained as source/history. It is **not** a human approval gate and it does not authorize mutation of Standard Requirements already at their own human boundary.

### 4.4 RAW Process failure

On failure:

```text
RAW State             = Process
RAW Processing Status = FAILED
```

The system must not move the RAW Requirement to `Review` as if processing succeeded.

The exact normal-user retry/override UX after a failed worker remains outside `RW-C02`; existing bounded recovery/admin capabilities may continue to exist. Any later retry must still preserve durable prior state and must not fabricate success.

---

## 5. Standard candidates inherit the authorized RAW processing cycle

A human who moved a RAW Requirement `Draft -> Process` has already authorized processing of the Standard candidates produced by that RAW cycle up to the next human decision boundary.

Therefore newly created Standard candidates do **not** require a second human `Draft -> Process` action one by one.

Normal flow:

```text
RAW Process succeeds
       |
       | SYSTEM creates 0..N Standard candidates
       v
Standard Draft
       |
       | SYSTEM — authorization inherited from parent RAW cycle
       v
Standard Process
       |
       | SYSTEM on successful Standard Process
       v
Standard Review
       |
       | SYSTEM on successful Standard Review
       v
Standard Ready
       |
       +-----------------------------+
       |                             |
       | HUMAN REWORK                | HUMAN APPROVE
       v                             v
    Process                         Apply
       |                             |
       | machine flow repeats        | SYSTEM on successful deterministic Apply
       |                             v
       +-----> Review -> Ready      Applied
```

The inherited authorization ends at `Ready`.

---

## 6. Standard candidate creation -> Draft -> Process

### 6.1 Candidate creation -> Draft

Owner: **SYSTEM**.

The RAW processor creates each Standard candidate in `Draft` with its source relationship and required initial content.

`Draft` remains a real lifecycle State even though the normal authorized RAW flow does not pause there for a second human decision.

### 6.2 Standard Draft -> Process after RAW decomposition

Owner: **SYSTEM**, but only for candidates created by the currently authorized successful RAW processing cycle.

The system transition means:

> Continue the machine-owned work already authorized by the parent RAW `Draft -> Process` decision.

It does **not** create new human authority.

Entering Standard `Process` starts that candidate's Standard Process cycle:

```text
Processing Status -> RESET
                   -> PROCESSING when Standard Process begins
```

A Standard Requirement found in `Draft` without a valid currently authorized creation path must not be auto-promoted merely because `Draft` exists. The routing contract in `RW-C04` must define how the system distinguishes normal inherited progression from an arbitrary/stale `Draft` observation without inventing product authority.

---

## 7. Standard Process -> Review

Owner: **SYSTEM**.

There is no human product decision between Standard Process and Standard Review.

After Standard Process succeeds and its durable Process Result/current-state protections are satisfied:

```text
Process Processing Status -> SUCCEEDED
State                     -> Review
```

Entering `Review` starts a new machine-processing cycle for the reviewer:

```text
Review Processing Status -> RESET
                         -> PROCESSING when Review begins
```

Standard Review is invoked automatically. The user must not need to issue a separate review command during normal operation.

If Standard Process fails:

```text
State             = Process
Processing Status = FAILED
```

and Review must not start.

---

## 8. Standard Review -> Ready

Owner: **SYSTEM**.

After Standard Review successfully produces and persists a valid Review Result bound to the current Requirement state:

```text
Review Processing Status -> SUCCEEDED
State                     -> Ready
```

This transition happens regardless of semantic verdict:

```text
PASS
NEEDS_WORK
BLOCKING
```

because the verdict is evidence for the human decision; it is not an autonomous decision.

At `Ready`, all machine-owned chaining stops.

No processor, reviewer, dispatcher, or trigger may choose `Process` or `Apply` from `Ready`.

If Review execution fails:

```text
State             = Review
Processing Status = FAILED
```

and the Requirement must not move to `Ready` as if a valid Review Result exists.

---

## 9. Standard Ready -> Process — REWORK

Owner: **HUMAN**.

The human moves:

```text
Ready -> Process
```

This is the durable rework decision.

It means:

> The current Ready Requirement is not accepted as-is. Start a new Standard Process cycle using the current Requirement content and preserved history.

Entering `Process` starts a new cycle and therefore resets the prior processing status:

```text
Processing Status -> RESET
                   -> PROCESSING when Standard Process begins
```

Prior Process/Review history remains historical evidence and must not be erased merely because rework begins.

After that human decision, the normal machine chain resumes:

```text
Process -> Review -> Ready
```

and stops again at `Ready`.

---

## 10. Standard Ready -> Apply — APPROVE

Owner: **HUMAN**.

The human moves:

```text
Ready -> Apply
```

This State transition is the durable approval signal for the current Requirement.

It means:

> Apply the exact Requirement state that was reviewed, subject to deterministic evidence revalidation.

No separate approval artifact is required merely to duplicate this signal.

No separate normal-flow `approve` command is required to create the authority.

Entering `Apply` starts the deterministic application cycle:

```text
Processing Status -> RESET
                   -> PROCESSING when Apply begins
```

The State transition alone does **not** prove the reviewed content is still valid. Apply must independently revalidate the exact reviewed state before making canonical mutations.

A `BLOCKING` or `NEEDS_WORK` Review verdict does not empower automation to reject the human transition. The human decision is authoritative, while the verdict remains visible evidence. Any additional acknowledgement UX beyond the State transition is not required by this v0.2 ownership contract.

---

## 11. Standard Apply -> Applied

Owner: **SYSTEM**.

Apply is deterministic and model-free.

Only after all required evidence/current-state validation and canonical application work succeeds may the system move:

```text
Apply -> Applied
```

On success:

```text
Processing Status -> SUCCEEDED
State             -> Applied
```

On failure:

```text
State             = Apply
Processing Status = FAILED
```

The system must not mark `Applied` when application did not complete successfully.

`Applied` means the authorized application cycle completed. It remains subject to the already documented limitation that an arbitrary manual Fibery State edit by itself cannot prove provenance; downstream consumers that need stronger provenance must rely on the corresponding durable evidence, not State alone.

---

## 12. Complete ownership table

| Requirement | From | To | Owner | Meaning |
|---|---|---|---|---|
| RAW | create | Draft | SYSTEM | Source preserved; waiting for human processing intent |
| RAW | Draft | Process | HUMAN | Authorize this RAW processing/decomposition cycle |
| RAW | Process | Review | SYSTEM | RAW processing completed successfully |
| Standard | create | Draft | SYSTEM | Candidate created from RAW source |
| Standard | Draft | Process | SYSTEM | Continue processing inherited from authorized parent RAW cycle |
| Standard | Process | Review | SYSTEM | Standard Process completed successfully |
| Standard | Review | Ready | SYSTEM | Standard Review completed successfully; human decision required |
| Standard | Ready | Process | HUMAN | REWORK; start new Standard Process cycle |
| Standard | Ready | Apply | HUMAN | APPROVE; authorize deterministic application of reviewed state |
| Standard | Apply | Applied | SYSTEM | Deterministic application completed successfully |

No other normal-flow transition is authorized by this contract.

---

## 13. Chaining boundary

Machine-owned chaining is permitted only while the flow remains inside an already-authorized machine segment.

### RAW authorization segment

```text
HUMAN: RAW Draft -> Process
SYSTEM: RAW Process
SYSTEM: create Standard candidates
SYSTEM: candidates Draft -> Process
SYSTEM: Standard Process -> Review
SYSTEM: Standard Review -> Ready
STOP
```

Each Standard candidate stops independently at its own `Ready` boundary.

### Rework segment

```text
HUMAN: Ready -> Process
SYSTEM: Process -> Review -> Ready
STOP
```

### Approval segment

```text
HUMAN: Ready -> Apply
SYSTEM: Apply -> Applied
STOP
```

A system stage must never use successful completion as permission to cross the next human-owned boundary.

---

## 14. Processing-status lifecycle semantics

`RW-C04` will freeze the concrete Fibery representation. The behavioral rules are already fixed here.

### 14.1 New machine-processing cycle

Whenever a Requirement enters a State that requires a new machine worker:

```text
prior Processing Status -> RESET
worker starts            -> PROCESSING
worker succeeds           -> SUCCEEDED
worker fails              -> FAILED
```

### 14.2 Immediate machine chaining

If success immediately causes another machine-owned State to begin, the old stage's success remains recoverable from its durable Result/history, while the shared visible Processing Status is reset for the new stage.

Example:

```text
Standard Process succeeds
  -> Process Result persists
  -> Processing Status = SUCCEEDED
  -> State = Review
  -> Review cycle begins
  -> Processing Status = RESET / PROCESSING
```

Thus the visible status always describes the **current machine cycle**, not every historical stage.

### 14.3 Human boundary

At a human boundary such as `Ready`, no new machine cycle begins, so the successful Review status remains visible until the human makes a new transition.

### 14.4 Failure

A failed worker leaves:

```text
State             = worker's current lifecycle State
Processing Status = FAILED
```

Failure must never be represented by advancing to the success State.

---

## 15. Manual edits and invalid transitions

Fibery permits direct State edits. This contract defines the normal semantic path; it cannot make Fibery's UI physically incapable of arbitrary manual changes.

Therefore every worker remains responsible for validating the durable preconditions required by its stage.

Examples:

- A Standard Requirement manually placed in `Review` without valid current Process evidence must not be treated as valid merely because `State = Review`.
- A Requirement manually placed in `Apply` may express human approval intent, but Apply must still refuse stale or missing Review/Process evidence.
- A Requirement manually placed in `Applied` does not retroactively prove that deterministic Apply ran successfully.

State is the workflow/control signal. Durable evidence proves the prerequisites and output of machine work.

---

## 16. Normal user flow versus admin/recovery tools

Normal operation is State-driven.

The user should not need to invoke one internal command per processor/reviewer/apply stage.

Existing or future admin/recovery commands may remain for:

- development;
- diagnosis;
- recovery from a known partial failure;
- controlled manual worker execution;
- testing.

But such tooling:

- must not create a second meaning for approval/rework;
- must not bypass evidence validation;
- must not cross a human boundary autonomously;
- must not become required for the normal lifecycle to advance.

`RW-O01` owns the code/API cleanup that separates those surfaces.

---

## 17. Assistant acting on explicit human instruction

The human may explicitly instruct an authorized assistant to perform a human-owned State transition.

Example:

```text
Human: "Approve AMR-FR-1234"
Assistant: changes Ready -> Apply on the human's behalf
```

Semantically this remains a human approval decision.

The assistant must not infer approval from:

- a PASS verdict;
- absence of findings;
- prior approval of another Requirement;
- the fact that implementation is waiting;
- a general request to "continue" when the requested human decision is ambiguous.

The same rule applies to REWORK and initial RAW processing intent.

---

## 18. Relationship to existing Ready Decision capability

The current `Ready Decision` implementation contains useful validation behavior, but the **normal product authority model changes**.

Current v0.1 operating shape:

```text
Ready
  -> explicit approve/rework capability
  -> capability performs State transition
```

Corrected v0.2 normal shape:

```text
human performs State transition
  Ready -> Apply   or   Ready -> Process
      |
      v
system reacts to the resulting State
```

Useful validation logic may be reused downstream, but implementation must not require the old explicit approval capability merely to make `Ready -> Apply` authoritative.

This contract does not itself delete or rewrite that code. `RW-O01` owns that implementation decision.

---

## 19. Relationship to current evidence protections

This rewrite changes **control ownership**, not the established integrity protections.

The following remain required:

- Standard Process must not overwrite a concurrent human edit with stale model output.
- Review must bind to the exact current Process output/normative tree it reviewed.
- Ready/Apply must not treat stale reviewed evidence as current.
- Apply must revalidate the exact reviewed state before canonical mutation.
- immutable Process/Review history remains preserved through rework.
- partial/failed work must remain recoverable from durable state without fabricating success.

`Ready -> Apply` supplies human approval intent; these protections establish whether the approved reviewed state is still safe to apply.

---

## 20. What this contract does not decide

This contract intentionally does not decide:

- the transport used to detect Fibery State changes;
- webhook versus polling versus another trigger mechanism;
- worker hosting/process topology;
- exact dispatcher module/class/function structure;
- exact Fibery Processing Status field name or concrete enum labels;
- exact retry button/normal-user recovery UX after worker failure;
- generalized orchestration outside the Requirement lifecycle;
- architecture/planning/development worker routing;
- general Requirement revision/supersession mechanics.

Those decisions belong to their later rewrite items or remain product open questions.

---

## 21. Acceptance of RW-C02

`RW-C02` is satisfied when an independent reviewer confirms all of the following:

1. `Ready -> Apply` is the durable human approval signal.
2. `Ready -> Process` is the durable human rework signal.
3. `RAW Draft -> Process` is the explicit human authorization to process the RAW source.
4. Standard candidates from that authorized RAW cycle need no separate per-candidate human activation.
5. Standard Process automatically continues into Standard Review.
6. Standard Review always stops at `Ready` for a human decision, regardless of verdict.
7. Apply remains deterministic/model-free and independently revalidates the exact reviewed state.
8. normal user flow does not require a separate approval/rework capability to create authority.
9. admin/recovery commands remain possible but cannot bypass human boundaries or evidence rules.
10. processing status is separate from lifecycle State and represents the current machine cycle.
11. processing status resets on each new machine cycle and visibly distinguishes processing, success and failure.
12. failed work cannot falsely advance the lifecycle State.
13. old Process/Review history survives rework.
14. the contract does not choose state-trigger transport or worker topology.
15. no downstream Architecture/Planning/Development orchestration is introduced.

Until human review and independent verification complete, this document remains `DRAFT` and implementation is not authorized.
