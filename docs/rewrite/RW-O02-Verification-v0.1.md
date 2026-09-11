# RW-O02 Verification v0.1

**Status:** VERIFIED  
**Work item:** `RW-O02 — Implement bounded Requirement worker dispatcher`  
**Frozen plan:** `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Implementation boundary:** `docs/rewrite/RW-O02-Implementation-Boundary-v0.1.md`  
**Verified implementation commit:** `a1ee1fb849d668222ebbf0213c97e8076eef03df`  
**Implementation evidence commit:** `80c21ab094ba0bd779698395ca1ad81240a771bc`  
**Verification date:** 2026-09-11

## Verdict

`RW-O02` satisfies frozen AC1–AC5 and is approved for merge.

The dispatcher remains a bounded routing layer: it selects only the four RW-C04 machine routes from `Type + State + pre-claim Processing Status`, revalidates current identity/Type/State before invoking exactly one bound worker, classifies typed worker results, and requires the worker-owned lifecycle post-State before reporting route completion. It does not poll, persist Processing Status, select model runtimes, or create a hidden lifecycle ledger.

## Acceptance criteria

### AC1 — closed authorized routes

PASS.

The route table contains exactly:

- Raw + Process + Not Processed -> RAW Requirement Processor;
- Standard + Process + Not Processed -> Standard Process;
- Standard + Review + Not Processed -> Standard Review;
- Standard + Apply + Not Processed -> Standard Apply.

Each dispatch invokes exactly one selected worker. Existing workers retain their own preconditions and integrity checks.

### AC2 — human boundaries do not advance

PASS.

Raw Draft and Standard Ready are explicit human boundaries and select no worker. Generic Standard Draft, settled states and unsupported RAW states select no worker and are not repaired. Review verdict never participates in route authority. A route selected from stale identity/Type/State is refused before worker invocation.

### AC3 — replay/idempotency

PASS.

After successful worker-owned State transitions, the same worker is no longer selectable from current State; replay of the old selection is stale. Processing/Succeeded/Failed are ineligible for a new automatic dispatch. Existing durable worker history is left untouched and no dispatcher ledger is introduced.

### AC4 — failures do not falsely complete lifecycle work

PASS.

Non-normal typed worker results are `WORKER_FAILED`. A normal typed result is not enough: the dispatcher re-reads the Requirement and requires the route's worker-owned post-State. `NO_CHANGES_TO_PROCESS` while still in Process and `NO_CHANGES_TO_REVIEW` while still in Review are therefore not reported as completed cycles. The dispatcher never fabricates Process->Review, Review->Ready or Apply->Applied.

RAW candidate progression is separately classified: complete-set preflight conflict causes zero progression writes; first-write failure and partial later-write failure are reported truthfully without rollback or demotion.

### AC5 — route coverage

PASS.

`tests/test_requirement_dispatcher.py` covers all four routes, all Processing Status gates, human/no-op/unsupported states, stale selections, all nine dispatch outcomes, worker failures, lifecycle postconditions, CR-002, exact RAW candidate progression and replay.

## CR-002 closure at O02 level

PASS.

The ordinary/manual Standard Process call retains its idempotent unchanged-tree behavior:

```text
current tree == latest Process output
-> NO_CHANGES_TO_PROCESS
```

The dispatcher alone invokes Standard Process with the bounded internal `authorized_new_cycle=True` mode for a selected `Standard + Process + Not Processed` machine cycle. In that mode an unchanged reviewed tree can produce the next Process iteration and reach Review. This mode is not exposed as a CLI flag or generic force.

The A11 ambiguity remains protected: `current tree == latest input != latest output` still returns `PROCESSING_STATE_CONFLICT` with no model call or mutation. Existing recovery/resume options remain mutually exclusive with the new-cycle mode.

The eventual O03 Processing Status claim is the cycle-level replay boundary: once status is Processing/Succeeded/Failed, the same route is not selectable again.

## RAW inherited candidate progression

PASS.

Progression occurs only after `RAW_REQUIREMENT_PROCESSED` and only for Requirement IDs named by that exact typed result. Every named candidate is preflighted as a unique Standard Draft deriving from the exact RAW invocation. Unrelated or merely-derived Draft Standards do not move. The complete returned set is preflighted before the first State write; conflicts leave untouched candidates in place. Write failures are reported as failed/partial orchestration without rollback.

## Scope / regression evidence

Independent inspection confirmed:

- `src/sdlc/requirement_dispatcher.py` is the primary O02 module;
- `standard_processor.py` changes only the bounded new-cycle entry and preserves ordinary no-change/A11/recovery behavior;
- no `sdlc worker run`, polling, sleep, runner lock, Processing Status Fibery read/write, schema wiring or reset automation was implemented;
- RAW/Review/Apply internal business logic was not duplicated into the dispatcher;
- evidence report records `690 passed` focused and `1834 passed` full, with lint/format clean;
- evidence commit changes only the RW-O02 implementation record;
- worktree was clean at handoff.

## Non-blocking note

`RequirementWorkers` are typed callable boundaries. An injected callable that violates the existing worker contract by raising unexpectedly would propagate; the production workers already convert their expected execution failures into typed result objects. This does not weaken the frozen worker-result contract and is not an RW-O02 blocker.
