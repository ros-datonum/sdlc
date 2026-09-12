# RW-O04 Implementation Boundary v0.1

**Status:** FROZEN  
**Work item:** `RW-O04 — Requirement lifecycle end-to-end automation test`  
**Depends on:** verified `RW-O03`  
**Semantic change to frozen lifecycle:** NONE  
**Date:** 2026-09-12

## Purpose

RW-O04 is the independent end-to-end verification gate for Block C. It proves that the already-implemented Requirement lifecycle composes correctly from human State intent through the RW-O03 runner, RW-O02 dispatcher, existing bounded workers, Processing Status semantics, Ready human boundary, rework and Apply.

RW-O04 is a **test-only lifecycle acceptance item**. It does not own new production semantics.

## Exact primary test

```text
tests/test_requirement_lifecycle_e2e.py
```

Keep any O04-only fake/fixture helpers in that test module unless a small reusable test helper is clearly necessary. Do not add a new production orchestration module.

## Production-code rule

Expected production-code change: **none**.

If the E2E test exposes a genuine defect in verified O01/O02/O03 or an existing worker:

1. do not weaken the E2E expectation;
2. do not silently patch production code under RW-O04;
3. capture the failing lifecycle evidence;
4. raise a Proposed Change Request / blocker against the owning prerequisite;
5. leave RW-O04 `BLOCKED` until the prerequisite is corrected and independently re-verified.

Documentation may be amended only to record O04 evidence/status, not to redefine lifecycle behavior.

## Test environment

The O04 acceptance test is deterministic and repository-owned. It must not depend on:

- live Fibery;
- a running `sdlc worker run` process;
- live Claude/Codex/model output;
- wall-clock automation delays;
- manual invocation of every stage CLI command.

Use:

- the real `requirement_runner.run_cycle`;
- the real RW-O02 dispatcher through the runner;
- the real RAW Processor, Standard Process, Standard Review and Apply capabilities;
- existing fake Fibery workspace infrastructure;
- `FakeModelRuntime` with bounded structured outputs appropriate to each stage.

The test validates lifecycle composition, not live-model semantic quality. Live Fibery adapter/automation mechanics were already verified by RW-O03/CR-003; Requirement abstraction/model quality is covered by Block B and later dogfood.

## Reset automation simulation

The deterministic fake workspace used by O04 must faithfully simulate the already-verified Fibery reset automation, and only that automation.

Whenever a Requirement State write results in one of:

```text
Raw      + Process
Standard + Process
Standard + Review
Standard + Apply
```

its `Processing Status` becomes:

```text
Not Processed
```

The fake reset must not fire for:

```text
Raw + Draft
Raw + Review
Standard + Draft
Standard + Ready
Standard + Applied
```

This test-only behavior represents the live Fibery automation verified by CR-003. It must be visible in the fake mutation history so O04 can assert resets rather than silently baking them into initial fixtures.

Do not fake the workers' lifecycle transitions. The real worker functions own those transitions.

## Primary normal-flow scenario

The E2E test must demonstrate the following as one coherent lifecycle using repeated runner cycles.

### 1. RAW human boundary

Start with an ingested RAW Requirement:

```text
Type = Raw
State = Draft
Processing Status = Not Processed
```

A runner cycle must do no worker mutation.

### 2. Human starts RAW processing

Simulate only the human State transition:

```text
Raw Draft -> Process
```

The fake Fibery automation resets status to `Not Processed`.

The next runner cycle must:

- claim `Processing`;
- run the real RAW Processor;
- create/persist its Processing Result and Standard candidate(s);
- move RAW to Review;
- perform only the exact inherited candidate `Draft -> Process` progression owned by RW-O02;
- settle RAW Processing Status to `Succeeded`.

### 3. Automatic Standard Process

The progressed candidate is now:

```text
Standard + Process + Not Processed
```

The next runner cycle must:

- claim Processing;
- run the real Standard Process;
- produce Process Result iteration 1;
- move State to Review;
- observe the fake automation reset of the new Review cycle to `Not Processed`;
- return `HANDED_OFF` without overwriting that reset.

### 4. Automatic Standard Review

The next runner cycle must:

- claim Processing;
- run the real Standard Review;
- persist Review Result;
- move State to Ready;
- settle Processing Status to `Succeeded`;
- stop at the human boundary.

A subsequent runner cycle while Ready must do no worker work.

The semantic Review verdict used in the main scenario may be PASS, but O04 must not encode PASS as authority to cross Ready.

### 5. Human REWORK

Simulate only:

```text
Ready -> Process
```

Use the **unedited** rework path in the main E2E scenario so the test proves the CR-002 integration across the full runner stack.

The reset automation produces `Not Processed`.

The next Process cycle must:

- invoke the RW-O02-authorized new-cycle mode through the runner;
- create Process Result iteration 2 even though the normative tree initially equals iteration 1 output;
- preserve iteration 1 Process and Review history;
- move to Review and hand off with Review `Not Processed`.

The next runner cycle runs Review iteration 2 and stops at Ready/Succeeded.

### 6. Human APPROVE

Simulate only:

```text
Ready -> Apply
```

The automation resets to `Not Processed`.

The next runner cycle must invoke real deterministic Apply, which independently revalidates the exact latest reviewed state and reaches:

```text
State = Applied
Processing Status = Succeeded
```

No `approve` or `apply` CLI command is part of the normal E2E flow.

## Replay / duplicate observation

The acceptance suite must prove repeated runner observation cannot duplicate durable outcomes.

At minimum replay/extra cycles around:

- RAW Review/Succeeded;
- Standard Ready/Succeeded;
- Standard Applied/Succeeded;
- Processing/Succeeded/Failed status gating where useful;

must not recreate Process/Review Results, candidates or Apply relations.

No hidden replay ledger is allowed in the test.

## Stale human edit protection

O04 must explicitly prove Apply still revalidates reviewed state in the state-driven normal path.

Use a separate focused E2E scenario or phase:

1. reach Standard Ready through the runner;
2. human moves Ready -> Apply, causing the reset to Not Processed;
3. modify the reviewed normative content after Review but before the Apply runner cycle;
4. run one runner cycle.

Expected:

- Apply refuses with its existing stale-review typed result;
- State does not falsely become Applied;
- runner reports failure and safely settles Processing Status to Failed when the claimed Apply cycle is still current;
- no canonical Apply relation mutation is fabricated.

Do not alter Apply to make this test pass.

## Failure-state proof

O04 must include at least one state-driven machine failure before a worker-owned success transition and prove:

```text
same machine State
Processing Status = Failed
```

with no false lifecycle advance and no automatic retry on the next runner cycle.

This may reuse the stale-Apply scenario if it fully demonstrates AC7, or use a bounded model/runtime failure earlier in the chain.

## Required assertions by frozen AC

### AC1 — normal state-driven machine processing

The primary flow uses human State changes plus repeated runner cycles, not manual processor/review/apply commands.

### AC2 — human boundary observable

RAW Draft and Standard Ready cannot be crossed by the runner until the human-owned State transition occurs. Review verdict does not cross Ready.

### AC3 — rework history preserved

After unedited Ready -> Process, Process iteration 1 and Review iteration 1 remain immutable while iteration 2 is created and reviewed.

### AC4 — Apply revalidates reviewed state

Normal approval succeeds for unchanged reviewed content; the stale-edit scenario fails closed before canonical application.

### AC5 — replay does not duplicate durable outputs

Extra runner cycles/replayed observations do not create duplicate candidates, Process Results, Review Results or Apply outcomes.

### AC6 — Processing Status semantics visible

The fake automation and runner mutation log must demonstrate:

- State entry reset -> `Not Processed`;
- runner claim -> `Processing`;
- terminal/human-boundary completion -> `Succeeded`;
- Standard Process -> Review destination remains/reset `Not Processed` for the next Review cycle;
- failure -> `Failed`.

### AC7 — failed processing does not falsely advance State

A failed claimed cycle remains at its valid failure State and is not automatically retried.

## Exact test philosophy

Prefer a small number of scenario-style tests with explicit phase assertions over dozens of isolated mocks. O04 exists to verify composition that unit tests cannot prove individually.

The tests should use real durable artifacts from existing fakes and assert counts/identity/history at meaningful milestones.

Do not assert only result codes while ignoring durable Fibery fake state.

## Live workspace boundary

RW-O04 does not need to mutate the live Fibery workspace. CR-003 already verified the real Processing Status field, eligible query and reset automation. O04 proves the full lifecycle composition deterministically.

A separate optional live smoke is not required and must not replace the deterministic E2E test.

## Local runner configuration

The operator's local `FIBERY_SPACE_ID` must be configured before using the real `sdlc worker run` command, but the deterministic RW-O04 test must not depend on `.env`.

## Completion

RW-O04 may become `IMPLEMENTED_UNVERIFIED` only when all seven frozen acceptance criteria are explicitly evidenced and the full repository regression gate passes.
