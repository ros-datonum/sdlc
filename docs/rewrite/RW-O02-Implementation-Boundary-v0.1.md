# RW-O02 Implementation Boundary v0.1

**Status:** FROZEN  
**Work item:** `RW-O02 — Implement bounded Requirement worker dispatcher`  
**Derived from:** verified `RW-C04` Requirement State-Worker Contract v0.1 and verified `RW-O01`  
**Semantic change to RW-C04:** NONE  
**Date:** 2026-09-11

## Purpose

The frozen rewrite plan requires RW-O02 to use the module/file boundary frozen before implementation. RW-C04 froze the routing semantics but allowed implementation to split code into reasonable modules and did not name a repository path. This sidecar removes that remaining implementation ambiguity without changing lifecycle semantics.

## Exact primary module

RW-O02 owns one new production module:

```text
src/sdlc/requirement_dispatcher.py
```

Primary tests:

```text
tests/test_requirement_dispatcher.py
```

Narrow supporting edits are allowed only where required for typed interfaces:

```text
src/sdlc/results.py
src/sdlc/fibery_workspace.py
src/sdlc/standard_processor.py       # CR-002 bounded new-cycle entry only
```

No other production module is an O02 design surface unless a concrete compile/test dependency requires it.

## Boundary between O02 and O03

RW-O02 owns:

- the closed `Type + State + pre-claim Processing Status` route table;
- a typed route/dispatch result;
- invocation of exactly one existing Requirement worker for an authorized route;
- revalidation that the Requirement still has the selected Type + State before worker invocation;
- typed worker-result classification;
- exact successful RAW-result candidate `Draft -> Process` inherited progression;
- the bounded CR-002 new-Process-cycle invocation described below.

RW-O02 does **not** own:

- querying/polling Fibery for eligible work;
- writing `Processing Status = Processing/Succeeded/Failed`;
- the Fibery Processing Status field/schema wiring;
- runner locking;
- sleep/poll cadence;
- `sdlc worker run`;
- reset automation configuration.

Those belong to RW-O03.

The O02 route selector therefore accepts the current/pre-claim Processing Status as an input supplied by the future O03 runner. It must select a machine route only for `Not Processed`. O03 will re-read eligibility, select the route, claim the cycle by writing `Processing`, and then execute the already selected O02 route; O02 must re-read Type + State before invoking the worker so a stale route cannot override a human State change.

## Closed routes

The only machine routes are the RW-C04 table:

```text
Raw      + Process + Not Processed -> RAW Requirement Processor
Standard + Process + Not Processed -> Standard Requirement Process
Standard + Review  + Not Processed -> Standard Requirement Review
Standard + Apply   + Not Processed -> Standard Requirement Apply
```

All other combinations are no-op/unsupported diagnostics and invoke no worker.

## Worker injection / runtime ownership

O02 must not select models, credentials, or runtime configuration. The dispatcher may receive already-bound worker callables/adapters for the four existing capabilities. O03/CLI composition owns concrete runtime construction later.

Worker preconditions remain authoritative defense in depth.

## RAW candidate progression

After and only after an exact `RAW_REQUIREMENT_PROCESSED` result, O02 may progress the Standard candidates named by that exact typed result.

Before each candidate is eligible for `Draft -> Process`, O02 must verify against current Fibery state at minimum:

```text
candidate Requirement ID is named by this successful RAW result
Type = Standard
State = Draft
Derived From includes the RAW entity processed by this invocation
```

Resolve candidates from the exact returned Requirement IDs; do not enumerate arbitrary Draft Standards and do not infer inherited authority from `Derived From` alone.

Prefer preflighting the complete returned candidate set before the first progression write so a discovered ownership conflict does not partially progress an otherwise untouched set. A write failure after writes begin must be reported truthfully as partial orchestration; do not roll back or demote candidates.

## CR-002 — unchanged-tree rework

Verified lifecycle semantics are:

```text
HUMAN Ready -> Process
= authorization for a NEW Standard Process cycle
```

An edit is not required.

The current ordinary Standard Process path treats:

```text
current tree == latest Process output tree
```

as `NO_CHANGES_TO_PROCESS`, which is correct for an ordinary/manual re-entry but cannot complete a newly authorized Ready-rework cycle.

RW-O02 therefore owns a **bounded internal new-cycle entry** into the existing Standard Process capability.

Required semantics:

- the ordinary/manual Standard Process call keeps its existing no-change/idempotency behavior;
- the O02 dispatcher may explicitly tell Standard Process that this invocation represents a newly authorized machine cycle;
- under that explicit new-cycle invocation, an unchanged current tree may produce the next Process iteration instead of returning `NO_CHANGES_TO_PROCESS`;
- changed-tree behavior remains the existing normal new-iteration behavior;
- this is not exposed as a generic `force` or evidence bypass;
- O02 may request it only for the selected `Standard + Process + Not Processed` machine route;
- worker State/evidence/concurrency checks remain unchanged;
- a re-dispatch of `Processing`, `Succeeded`, or `Failed` is not eligible, which is the orchestration boundary preventing the new-cycle path from duplicating a previously claimed/completed cycle.

A narrow keyword/internal mode on `process_standard_requirement` is allowed if needed. Existing CLI behavior must remain unchanged unless a later explicit admin contract says otherwise.

## Typed-result rule

O02 classifies success/failure from existing typed result sets, never text output:

- RAW: `RAW_REQUIREMENT_PROCESSED` only;
- Standard Process: existing normal Standard outcomes, except an O02-authorized new cycle must not treat the old unchanged-tree `NO_CHANGES_TO_PROCESS` stall as completion of that requested cycle;
- Standard Review: existing normal Review outcomes;
- Apply: existing normal Apply outcomes.

The dispatcher itself must not fabricate lifecycle transitions already owned by the bounded workers. When a worker already performs its system-owned transition, O02 validates the resulting State rather than writing a redundant competing transition.

## No hidden authority

This module may hold ephemeral route objects/results only. It must not create durable local lifecycle state, infer human approval from Review verdict, auto-retry Failed cycles, or cross Ready/Draft human boundaries outside the exact inherited RAW candidate progression above.
