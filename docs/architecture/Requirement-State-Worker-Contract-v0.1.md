# Requirement State-Worker Contract v0.1

**Status:** DRAFT — RW-C04 HUMAN/REVIEWER CONTRACT  
**Implementation authorization:** NONE  
**Rewrite item:** `RW-C04`  
**Depends on:** `RW-C02 — Requirement Lifecycle Ownership Contract v0.2`  
**Primary product requirements:** `docs/rewrite/SDLC-Corrected-Product-Functional-Requirements-v0.2.md`

## 1. Purpose

This contract freezes the concrete Requirement state-to-worker routing and the minimum trigger/runtime mechanism for the rewrite.

It exists so implementation agents do not decide:

- which lifecycle states run which worker;
- which state transitions are human or system owned;
- how a new processing cycle is marked;
- what Processing Status values mean;
- whether failed work retries automatically;
- whether a public webhook service, queue, scheduler, or other orchestration platform must be introduced.

The central runtime rule is:

```text
Fibery State
+ Requirement Type
+ Processing Status
= whether machine work is eligible
```

Fibery remains lifecycle truth. The worker runner is an executor, not an authority source.

---

## 2. Selected v0.1 trigger architecture

For this rewrite, Requirement automation uses two bounded pieces:

```text
FIBERY AUTOMATION RULE
State enters a machine-owned processing state
        ↓
Processing Status = Not Processed

LOCAL SDLC WORKER RUNNER
polls Fibery for eligible Requirements
        ↓
sets Processing Status = Processing
        ↓
invokes exactly one existing bounded worker
        ↓
Succeeded or Failed
        ↓
on success, performs only the system-owned lifecycle transition
```

The local runner is selected because the currently verified model execution boundary uses local CLI OAuth. A Fibery-to-public-webhook execution service would require an additional externally reachable worker host/tunnel and operational/security configuration that is not required to prove the state-driven lifecycle.

This is a replaceable transport choice. The state/worker semantics in this contract must remain valid if a later architecture replaces polling with Fibery `Send Web Request`, a queue, or another event transport.

---

## 3. Explicitly not selected in this rewrite

Do not introduce merely for Requirement routing:

- a public callback service;
- Cloudflare/Tailscale/ngrok-style tunnel requirements;
- n8n/Make/Zapier/Windmill as an orchestration dependency;
- a message broker;
- a distributed job queue;
- GitHub Actions as the Requirement reasoning worker host;
- provider API credentials to replace the verified local OAuth runtime;
- exactly-once delivery claims;
- multi-machine worker coordination.

These may be reconsidered later if a real deployment requirement justifies them.

---

## 4. Fibery Processing Status field

Add one single-select field to `SDLC/Requirement`:

```text
Field: SDLC/Processing Status
Type:  Single Select
Default: Not Processed
```

Allowed values are exactly:

```text
Not Processed
Processing
Succeeded
Failed
```

No fifth value is introduced in this rewrite.

### Meaning

#### `Not Processed`

No machine worker has started for the current processing cycle.

This value is also the reset state when a Requirement enters or re-enters a machine-owned lifecycle State.

It does **not** mean the Requirement is approved, queued globally, or semantically incomplete.

#### `Processing`

The local SDLC worker runner has claimed the current cycle and invoked or is invoking the corresponding bounded worker.

It does not imply success.

#### `Succeeded`

The corresponding machine worker completed its bounded responsibility successfully for the current cycle.

For Standard Review this may coexist with any semantic verdict, including `NEEDS_WORK` or `BLOCKING`.

#### `Failed`

The corresponding machine worker did not complete successfully for the current cycle.

The lifecycle State remains at the failed worker's State; the runner does not auto-retry it.

---

## 5. Processing Status is not lifecycle State

These two fields answer different questions:

```text
State
= where the Requirement is in the workflow

Processing Status
= what happened in the machine-processing cycle for that State
```

Examples:

```text
State = Ready
Processing Status = Succeeded
Review Verdict = BLOCKING
```

is valid: Review executed successfully and produced a blocking semantic assessment for the human.

```text
State = Process
Processing Status = Failed
```

means processing failed and the Requirement did not falsely advance.

---

## 6. Fibery reset automation

The workspace must have one Requirement automation rule whose responsibility is only to reset `Processing Status` when a new machine cycle is requested.

### Trigger

```text
Database: SDLC/Requirement
When: workflow/state is updated
```

### Reset condition

Reset to `Not Processed` when the resulting Requirement is any of:

```text
Type = Raw      AND State = Process
Type = Standard AND State = Process
Type = Standard AND State = Review
Type = Standard AND State = Apply
```

Do not reset merely for:

```text
Raw + Draft
Raw + Review
Standard + Draft
Standard + Ready
Standard + Applied
```

### Action

```text
Processing Status = Not Processed
```

The automation performs no model call and no Requirement semantic mutation.

It does not choose the next State.

It does not itself invoke the worker.

---

## 7. Why reset is state-selective

The rule intentionally does **not** reset after every State change.

Example:

```text
Standard Review worker succeeds
Processing Status = Succeeded
State -> Ready
```

`Ready` is a human boundary, so `Succeeded` remains visible.

If the human chooses rework:

```text
Ready -> Process
```

that transition requests a new cycle, so the Fibery automation resets:

```text
Processing Status -> Not Processed
```

The same principle applies to `Ready -> Apply`.

---

## 8. Worker runner external contract

The normal Requirement worker host for this rewrite is one long-running local command:

```bash
sdlc worker run
```

It uses the configured Fibery workspace and the existing local model-runtime configuration.

The runner watches all Projects in that configured SDLC workspace. Human State changes remain the authorization mechanism, so a separate project allow-list is not required for the Requirement stage.

The runner is started once as an operating service/process. The user does not invoke it once per Requirement stage.

### Poll cadence

Default idle poll interval:

```text
5 seconds
```

The implementation may expose:

```bash
--poll-interval-seconds <N>
```

for development/operation, with:

```text
minimum = 1 second
default = 5 seconds
```

Changing the poll interval changes responsiveness only; it must not change lifecycle semantics.

---

## 9. Single-runner execution boundary

The v0.1 runner is sequential.

Only one cooperating `sdlc worker run` process may own the configured Fibery workspace on one host.

The implementation must use a workspace-scoped local execution guard so a second cooperating runner fails fast instead of processing in parallel.

This rewrite does not claim multi-host exclusion. Multi-machine runner coordination remains unsupported.

Within one runner:

```text
one Requirement worker at a time
```

This preserves the current project's conservative one-command-at-a-time workspace operating boundary while automation is introduced.

Parallel Requirement execution is not part of this rewrite.

---

## 10. Eligible routing table

Only the following combinations are machine-runnable:

| Type | State | Required Processing Status | Worker |
|---|---|---|---|
| Raw | Process | Not Processed | RAW Requirement Processor |
| Standard | Process | Not Processed | Standard Requirement Process |
| Standard | Review | Not Processed | Standard Requirement Review |
| Standard | Apply | Not Processed | Standard Requirement Apply |

No other `Type + State` combination invokes a worker.

---

## 11. Explicit no-op states

The runner must not invoke machine work for:

| Type | State | Reason |
|---|---|---|
| Raw | Draft | human has not authorized RAW processing |
| Raw | Review | RAW decomposition cycle is complete; retained as source/history |
| Standard | Draft | candidate exists but generic Draft observation alone is not inherited authorization |
| Standard | Ready | human approval/rework boundary |
| Standard | Applied | application already completed |

Unexpected Raw states such as `Ready`, `Apply`, or `Applied` are invalid for the normal RAW flow and must not be auto-corrected by the runner.

The runner may report diagnostics but must not invent a repair transition.

---

## 12. Standard Draft auto-progression ownership

`RW-C02` requires Standard candidates produced by an authorized RAW processing cycle to proceed automatically into Standard Process.

Generic polling of `Standard + Draft` is **not** allowed to create that authority.

Instead, after a RAW worker returns a successful `RAW_REQUIREMENT_PROCESSED` result, the orchestration layer must transition only the Standard candidates produced/confirmed by that exact successful RAW processing result:

```text
Standard Draft -> Process
```

Before changing each candidate, the orchestration layer must re-read it and confirm at minimum:

```text
Type = Standard
State = Draft
Derived From includes the RAW Requirement processed by this invocation
candidate identity belongs to the successful durable RAW Processing Result
```

If any candidate no longer satisfies those conditions, the orchestration layer must not demote, overwrite, or force it into Process.

The system must report the progression conflict and leave the conflicting candidate unchanged.

This is the only normal system-owned `Standard Draft -> Process` path in this rewrite.

---

## 13. RAW routing

### Entry

```text
Type = Raw
State = Process
Processing Status = Not Processed
```

### Runner sequence

```text
1. re-read Requirement and validate eligibility
2. set Processing Status = Processing
3. invoke existing RAW Requirement Processor
4. inspect its typed result
```

### Success

Success means:

```text
ProcessResult.code = RAW_REQUIREMENT_PROCESSED
```

The existing RAW processor already owns its durable Processing Result, candidate creation/recovery, validation, and RAW `Process -> Review` transition.

After that successful result, orchestration performs the bounded Standard-candidate auto-progression described in section 12.

When the complete runner-owned RAW cycle finishes successfully:

```text
Raw Processing Status = Succeeded
Raw State = Review
```

If the existing RAW processor has already moved State to Review, the runner must validate that state rather than write a redundant competing transition.

### Failure

Any non-normal RAW result:

```text
Processing Status = Failed
```

The runner must not pretend success or auto-retry.

Existing RAW recovery options remain admin/recovery surfaces.

---

## 14. Standard Process routing

### Entry

```text
Type = Standard
State = Process
Processing Status = Not Processed
```

### Runner sequence

```text
1. re-read and validate eligibility
2. set Processing Status = Processing
3. invoke existing Standard Process capability
4. inspect typed result
```

### Success

Normal outcomes are the existing Standard Process normal result codes.

On successful completion:

```text
Processing Status = Succeeded
State = Review
```

If the current bounded capability already performs `Process -> Review`, validate the resulting State instead of duplicating the transition.

The Fibery reset automation then resets Processing Status to `Not Processed` because `Standard + Review` begins a new machine cycle.

The next runner iteration may invoke Review immediately; it need not wait one idle poll interval while work is already eligible.

### Failure

```text
State = Process
Processing Status = Failed
```

Review must not run.

---

## 15. Standard Review routing

### Entry

```text
Type = Standard
State = Review
Processing Status = Not Processed
```

### Runner sequence

```text
1. re-read and validate eligibility/evidence
2. set Processing Status = Processing
3. invoke existing Standard Review capability
4. inspect typed result
```

### Success

A successful Review execution is defined by the existing normal Review result codes, not by the semantic Review Verdict.

On successful execution:

```text
Processing Status = Succeeded
State = Ready
```

This happens for:

```text
PASS
NEEDS_WORK
BLOCKING
```

The runner stops. `Ready` is a human boundary.

### Failure

```text
State = Review
Processing Status = Failed
```

The runner must not move the Requirement to Ready without a valid Review Result.

---

## 16. Standard Apply routing

### Entry

```text
Type = Standard
State = Apply
Processing Status = Not Processed
```

The State itself is the human approval signal under `RW-C02`.

### Runner sequence

```text
1. re-read Requirement
2. set Processing Status = Processing
3. invoke existing deterministic Apply capability
4. Apply independently revalidates the exact reviewed state
5. inspect typed result
```

### Success

On successful deterministic application:

```text
Processing Status = Succeeded
State = Applied
```

### Failure

```text
State = Apply
Processing Status = Failed
```

No model retry or automatic return to Process is performed by the runner.

Existing bounded Apply recovery/admin behavior remains separate.

---

## 17. Human transitions observed by the runner

### Initial RAW processing

```text
HUMAN: Raw Draft -> Process
FIBERY AUTOMATION: Processing Status -> Not Processed
RUNNER: RAW worker
```

### Standard rework

```text
HUMAN: Standard Ready -> Process
FIBERY AUTOMATION: Processing Status -> Not Processed
RUNNER: Standard Process -> Review -> Ready
```

### Standard approval

```text
HUMAN: Standard Ready -> Apply
FIBERY AUTOMATION: Processing Status -> Not Processed
RUNNER: deterministic Apply -> Applied
```

No explicit normal-flow `approve`, `rework`, `normalize`, `review`, or `apply` CLI command is required to advance these flows.

---

## 18. Poll loop behavior

One runner iteration does:

```text
1. query eligible Requirements
2. if none -> sleep configured idle interval
3. if one or more -> choose one deterministically
4. execute it synchronously
5. immediately query again
```

After successful work, the runner does not sleep while another eligible Requirement is already available.

### Deterministic selection

Eligible Requirements are ordered by:

```text
fibery/public-id ascending
```

The order is an execution policy only. It does not create priority semantics in the Requirement model.

If future product requirements need priorities, that must be designed explicitly rather than inferred here.

---

## 19. Re-read before execution

A poll result is only a candidate for work.

Immediately before setting `Processing Status = Processing`, the runner must re-read the Requirement and confirm that the same machine eligibility still holds.

If Type, State, Processing Status, Project binding, or worker prerequisites changed:

```text
NO MUTATION
NO WORKER CALL
```

The runner returns to selection/query.

This prevents a stale poll result from overriding a human action that occurred after the query.

---

## 20. Processing claim and duplicate runner behavior

The runner sets:

```text
Processing Status: Not Processed -> Processing
```

before calling a worker.

A Requirement already in:

```text
Processing
Succeeded
Failed
```

is not eligible for automatic execution in the same State.

This prevents a normal poll loop from repeatedly rerunning completed or failed work.

The workspace-scoped local runner guard is the v0.1 protection against two cooperating local runners racing to claim the same `Not Processed` item.

This is **not** a distributed compare-and-set guarantee. Multi-host automation remains unsupported.

---

## 21. Failure and retry policy

The runner does not automatically retry a Requirement whose current Processing Status is `Failed`.

Reason:

- repeated model/runtime failure can consume unbounded tokens/compute;
- a semantic or evidence failure may require human inspection;
- current recovery capabilities already contain explicit resume/recovery semantics for known partial states.

The exact normal-user Retry UX remains outside this contract.

A bounded admin/recovery operation may later reset the same machine State's Processing Status to `Not Processed` only when that operation explicitly owns the corresponding recovery semantics.

A human rework transition `Ready -> Process` is already a new cycle and is reset by the Fibery automation automatically.

---

## 22. Abrupt runner termination

If the local worker process is terminated after setting `Processing Status = Processing`, the status may remain `Processing`.

This rewrite does not introduce a heartbeat, lease timeout, or distributed stale-worker recovery mechanism.

Such an item requires explicit recovery/admin handling before rerun; the runner must not blindly assume an old `Processing` value is stale and execute again.

This is an accepted v0.1 limitation and must be documented in normal operating instructions.

---

## 23. Existing worker contracts remain authoritative internally

The runner does not replace worker preconditions.

Each current capability remains responsible for its established integrity checks, including where applicable:

- correct Requirement Type/State;
- source/document identity;
- normative-tree binding;
- current Process/Review evidence;
- stale-input detection;
- concurrent human-edit detection;
- explicit empty-Result recovery boundaries;
- deterministic Apply revalidation.

The runner's eligibility check is routing defense. It must not weaken or bypass worker validation.

---

## 24. Typed result handling

The runner must decide success/failure from existing typed result contracts, not from stdout text matching.

At minimum:

```text
RAW Processor
  normal: RAW_REQUIREMENT_PROCESSED

Standard Process
  normal: existing NORMAL_STANDARD_OUTCOMES

Standard Review
  normal: existing NORMAL_REVIEW_OUTCOMES

Standard Apply
  normal: existing Apply normal outcome contract
```

If a worker returns a non-normal typed result, Processing Status becomes `Failed` unless the existing contract explicitly classifies the result as an idempotent already-completed normal outcome.

Claude/Codex may not redefine worker success codes inside routing implementation merely to make orchestration pass.

---

## 25. Processing Status update failures

Processing Status is part of the visible orchestration contract.

If the runner cannot safely set `Processing` before a worker starts:

```text
DO NOT START WORKER
```

If worker execution succeeds but the runner cannot persist the final Processing Status or confirm the resulting lifecycle State:

- do not rerun the worker blindly;
- report a partial orchestration failure;
- rely on existing durable worker result/state for diagnosis;
- require bounded recovery/reconciliation rather than guessing.

The runner must never erase a durable worker result in an attempt to make the status field look atomic.

---

## 26. No hidden lifecycle truth

The runner may keep ordinary ephemeral process state needed to execute its loop, but it must not create a local database/file that becomes an alternative source of Requirement lifecycle truth.

Durable lifecycle truth remains in Fibery:

```text
Type
State
Processing Status
Requirement content/relations
Process/Review/Apply evidence artifacts
```

OS lock files used only as execution guards are not lifecycle truth.

---

## 27. Workspace automation is one-time configuration

The Processing Status reset rule is configured once for the `SDLC/Requirement` database and applies to all Projects.

It is not created per Project and is not part of `project bootstrap`.

The bootstrap contract therefore remains project-local and does not mutate workspace-global automation rules.

The implementation must document how to verify the workspace rule exists and is configured correctly before `sdlc worker run` is considered production-ready.

Automatic programmatic creation of Fibery automation rules is not required by this rewrite unless a later explicit work item adds it.

---

## 28. Interaction with current Fibery schema

At contract freeze time the live `SDLC/Requirement` database already contains:

```text
Type: Raw | Standard
State: Draft | Process | Review | Ready | Apply | Applied
```

and does not yet contain `Processing Status`.

The implementation work must add only the single-select field defined in section 4 for this contract's new visible orchestration state.

No additional orchestration database is introduced.

---

## 29. Relationship to `RW-O01`–`RW-O04`

This contract assigns bounded implementation responsibilities:

```text
RW-O01
= separate normal State control from admin/manual lifecycle commands

RW-O02
= implement the state/type/status dispatcher
+ candidate Draft -> Process inherited progression after successful RAW processing
+ typed result handling

RW-O03
= implement `sdlc worker run`
+ workspace-scoped local runner guard
+ polling/query/re-read loop
+ Processing Status integration
+ document/verify the one-time Fibery reset automation

RW-O04
= prove the complete normal state-driven Requirement lifecycle end to end
```

Implementation items may split code into reasonable modules, but they may not change the lifecycle semantics or introduce a different transport without a plan change.

---

## 30. End-to-end expected flows

### 30.1 New RAW source

```text
requirement add
-> Raw Draft / Not Processed

HUMAN Draft -> Process
-> Fibery reset automation: Not Processed
-> runner: Processing
-> RAW Processor
-> RAW Review / Succeeded
-> produced Standard candidates Draft
-> orchestration validates exact produced candidates
-> SYSTEM candidates Draft -> Process
-> reset automation: Not Processed
-> runner: Standard Process
-> SYSTEM Review
-> reset automation: Not Processed
-> runner: Standard Review
-> SYSTEM Ready / Succeeded
-> STOP
```

### 30.2 Rework

```text
Standard Ready / Succeeded
HUMAN -> Process
reset -> Not Processed
runner -> Processing
Standard Process succeeds
-> Review
reset -> Not Processed
Standard Review succeeds
-> Ready / Succeeded
STOP
```

### 30.3 Approval

```text
Standard Ready / Succeeded
HUMAN -> Apply
reset -> Not Processed
runner -> Processing
Apply validates exact reviewed state
Apply succeeds
-> Applied / Succeeded
STOP
```

### 30.4 Failure

```text
machine State / Not Processed
runner -> Processing
worker fails
-> same State / Failed
STOP automatic retry
```

---

## 31. Acceptance of RW-C04

`RW-C04` is satisfied when an independent reviewer confirms all of the following:

1. every current Requirement lifecycle State has one unambiguous ownership/processing meaning consistent with `RW-C02`;
2. only `Raw+Process`, `Standard+Process`, `Standard+Review`, and `Standard+Apply` are generic machine-worker entry states;
3. `Standard+Draft` is not generically auto-processed merely because it exists;
4. Standard candidates from a successful authorized RAW cycle have one explicit bounded inherited `Draft -> Process` path;
5. `Standard+Ready` remains a hard human boundary;
6. `Processing Status` is exactly one single-select field with `Not Processed`, `Processing`, `Succeeded`, and `Failed`;
7. reset semantics occur only when a new machine cycle is requested, preserving `Succeeded` at Ready/Applied boundaries;
8. the selected v0.1 execution transport is one sequential local `sdlc worker run` poller using the existing local OAuth runtime boundary;
9. no public webhook, queue, distributed worker platform, or model API credential is required by this rewrite;
10. the runner re-reads current Fibery state before execution and does not trust stale poll data;
11. worker success/failure is determined from typed result contracts, not console prose;
12. failed work remains visible and is not retried automatically;
13. abrupt-process stale `Processing` recovery is explicitly not invented in this rewrite;
14. existing worker evidence/concurrency/recovery protections remain defense in depth;
15. one-time Fibery reset automation is workspace-global, state-selective, and does not become project bootstrap responsibility;
16. the runner contains no hidden durable lifecycle source of truth;
17. machine chaining stops at human boundaries;
18. the contract does not introduce downstream Architecture/Planning/Development orchestration.

Until human review and independent verification complete, this document remains `DRAFT` and implementation is not authorized.
