# RW-O04 Verification v0.1

**Status:** VERIFIED  
**Work item:** `RW-O04 — Requirement lifecycle end-to-end automation test`  
**Frozen plan:** `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Verified implementation commit:** `ce3aad07feb32a698ab908a3575ccb0263ce9cc6`  
**Implementation evidence commit:** `b6d3663b3912a62d2e5d0009892cf3dab45500cf`  
**Verification date:** 2026-09-12

## Verdict

`RW-O04` satisfies all seven frozen acceptance criteria and is approved for merge.

The implementation is test-only and proves the composed Requirement lifecycle through the real production stack:

```text
requirement_runner.run_cycle
-> RW-O02 dispatcher
-> real RAW Processor / Standard Process / Standard Review / deterministic Apply
```

The only test doubles are the existing Fibery fake, bounded deterministic model responses, and a test-only representation of the reset automation already verified live by RW-O03 / CR-003. No production lifecycle code was modified to make the test pass.

## Acceptance criteria

### AC1 — state-driven normal machine processing

PASS.

The main scenario starts with Raw Draft waiting, then uses only human State writes for Raw Draft -> Process, Standard Ready -> Process, and Standard Ready -> Apply. Every machine stage is entered through `run_cycle`; no manual process/normalize/review/apply CLI call advances the normal flow.

RAW processing creates the candidate and RW-O02 progresses exactly that candidate Draft -> Process. Standard Process hands off to Review, Standard Review stops at Ready, rework creates Process/Review iteration 2, and deterministic Apply reaches Applied.

### AC2 — human boundary is observable and cannot be crossed automatically

PASS.

Raw Draft returns `IDLE` with no mutation and no model call. Standard Ready returns `IDLE` repeatedly with stable Requirements/Documents until the test performs the human-owned State transition. Review verdict is not used as lifecycle authority.

### AC3 — rework history preserved

PASS.

The unedited Ready -> Process path creates Process iteration 2 through the bounded CR-002 new-cycle path. Process Result 1 and Review Result 1 retain their original Document identities and byte-identical bodies after the second Process and Review cycles. Iteration histories are `[1, 2]` without overwriting or deleting prior evidence.

### AC4 — Apply revalidates reviewed state

PASS.

The normal unchanged reviewed state reaches `REQUIREMENT_APPLIED` / `Applied` / `Succeeded` through the runner.

The separate stale-Apply scenario reaches Ready through state-driven Process + Review, changes Ready -> Apply, edits the reviewed normative Root before the Apply cycle, and the real Apply capability returns `REVIEW_RESULT_STALE`. State remains Apply, no relation is fabricated, and Processing Status settles Failed.

### AC5 — replay does not duplicate durable outputs

PASS.

Repeated cycles at Ready and after Applied return `IDLE` and preserve complete durable snapshots. The RAW cycle remains exactly one Processing Result, one candidate and one RAW model invocation. Final durable history is one RAW Processing Result, one candidate, two Standard Process Results and two Review Results; no replay marker or dispatcher ledger exists.

### AC6 — Processing Status lifecycle is visible

PASS.

The test records the already-verified reset automation in the same ordered mutation log as runner status writes. It explicitly proves:

```text
new machine State -> Not Processed
runner claim       -> Processing
Raw Review         -> Succeeded
Process -> Review  -> Not Processed retained for the Review cycle
Review -> Ready    -> Succeeded
Ready -> Process   -> Not Processed
Process -> Review  -> Not Processed
Review -> Ready    -> Succeeded
Ready -> Apply     -> Not Processed
Apply -> Applied   -> Succeeded
```

The Process -> Review slices contain no runner `Succeeded` write after the destination-cycle reset.

### AC7 — failed processing does not falsely advance lifecycle State

PASS.

The stale Apply cycle ends at State Apply / Processing Status Failed, creates no canonical relation or new artifact, and two further runner cycles are idle. Failed work is not automatically retried and State is not falsely advanced to Applied.

## Scope and regression evidence

Independent inspection confirms the branch changes only:

- `tests/test_requirement_lifecycle_e2e.py` — implementation;
- `docs/rewrite/SDLC-Rewrite-Plan-v0.2.md` — implementation status/evidence metadata.

No production file changed.

Implementation report records:

- dedicated E2E: `2 passed`;
- focused Block C gate: `977 passed`;
- full gate: `1996 passed`, ruff clean, format clean, locked dependencies up to date.

Red checks were run only on scratch copies and confirm both critical protections are meaningful: writing `Succeeded` after Standard Process breaks the E2E, and disabling Apply stale-review validation breaks the stale-Apply scenario.

## Administrative transition note

RW-O04 was frozen as `BLOCKED` on RW-O03. RW-O03 was independently verified and merged before O04 implementation began, but the implementation agent moved the item directly `BLOCKED -> IMPLEMENTING`, which is not one of the frozen implementation-agent transitions.

This is the same administrative deviation class recorded for RW-O03. It changed no normative work-item text, authority rule, lifecycle semantics, implementation scope or verification evidence. Reviewer disposition: non-blocking process deviation; do not rewrite Git history.

## Dependency gate

With this verification, **Block C — Requirement Lifecycle Orchestration is complete**:

- RW-O01 VERIFIED
- RW-O02 VERIFIED
- RW-O03 VERIFIED
- RW-O04 VERIFIED

The next rewrite block may proceed according to its own frozen dependency gates.
