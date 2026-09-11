# RW-O03 Implementation Boundary v0.1

**Status:** FROZEN  
**Work item:** `RW-O03 — Implement state-change trigger entrypoint`  
**Derived from:** verified `RW-C04` Requirement State-Worker Contract v0.1 and verified `RW-O02`  
**Semantic change to RW-C04:** NONE  
**Date:** 2026-09-11

## Purpose

RW-C04 already selected the v0.1 transport: one sequential local polling runner, started as `sdlc worker run`, using Fibery `Type + State + Processing Status` as durable eligibility. This sidecar freezes the repository boundary and the status-finalization details needed to compose the already-verified RW-O02 dispatcher without inventing a second orchestration model.

## Exact primary modules

RW-O03 owns:

```text
src/sdlc/requirement_runner.py
src/sdlc/worker_runner_guard.py
```

Primary tests:

```text
tests/test_requirement_runner.py
tests/test_worker_runner_guard.py
tests/test_cli_worker.py
```

Narrow supporting edits are allowed in:

```text
src/sdlc/cli.py
src/sdlc/fibery_workspace.py
src/sdlc/fibery_http.py
docs/fibery/Fibery-Schema-v0.1.md
README.md
```

A small dedicated Fibery worker-setup document may be added under `docs/fibery/` for the one-time field/automation configuration and verification checklist.

Do not change worker semantic code, the RW-O02 route table, model prompts, Process/Review/Apply evidence contracts, or downstream lifecycle.

## Processing Status integration

The visible Fibery field remains exactly:

```text
SDLC/Processing Status
Single Select
Default: Not Processed

Not Processed
Processing
Succeeded
Failed
```

Runtime code must resolve the field from schema rather than assume a prefixed API name. Existing non-runner capabilities must remain usable through the same adapter; adding runner support must not make unrelated commands depend on Processing Status when they do not use it.

The runner must fail clearly at startup if the field is absent or its allowed option names are not exactly the four frozen values. If the public schema representation does not expose the configured default reliably, do not invent validation for it; document the default as a one-time workspace configuration requirement.

The reset automation is one-time workspace configuration, not project bootstrap and not programmatically created by RW-O03. The repository must document the exact trigger/conditions/action from RW-C04 and how an operator verifies it. Runtime must not call undocumented automation endpoints merely to claim automatic verification.

## Poll/query boundary

The runner watches the configured workspace across Projects.

One iteration:

```text
query current eligible work
-> choose lowest fibery/public-id
-> re-read current Requirement + Processing Status
-> if no longer eligible: no claim, no worker, query again
-> set Processing Status = Processing
-> read back and confirm the same Type + State + Project binding and Status = Processing
-> execute the already-selected RW-O02 route
-> finalize visible status safely
-> query again immediately
```

When no eligible work exists, sleep the configured idle interval.

Default idle interval = 5 seconds; minimum = 1 second. The query must be bounded to the four RW-O02/C04 machine routes at `Not Processed`; RW-O02 route selection remains semantic defense in depth. Deterministic selection is `fibery/public-id` ascending. Do not add a priority model.

No trigger/event payload is trusted as product truth: every route and claim comes from fresh Fibery reads.

## Claim race / no CAS

Fibery provides no distributed compare-and-set guarantee here. Therefore a poll/query result is only a candidate.

Immediately before the claim, re-read and confirm eligibility. After writing `Processing`, read back again and confirm:

- same entity;
- same Type;
- same State;
- same Project binding;
- Processing Status = Processing.

Only then call RW-O02 `dispatch` with the route selected from the pre-claim `Not Processed` snapshot. RW-O02 performs its own Type/State re-read again before the worker call.

If a human/external actor changes State during this window, do not repair or force the old route. Report the claim conflict. Do not overwrite the new State's status merely to make the old claim look atomic.

## Status finalization after dispatch

`Processing Status` describes the machine cycle of the **current State**. Existing workers own their lifecycle transition, so status finalization must not overwrite a reset that belongs to the destination State.

### Terminal/human destination states

For completed routes whose destination does not start another machine cycle:

```text
Raw Process      -> Raw Review
Standard Review -> Ready
Standard Apply  -> Applied
```

on `ROUTE_COMPLETED`, set the Requirement's Processing Status to `Succeeded` and confirm it by read-back, provided the current State still equals the verified destination.

### Standard Process -> Review

This is different:

```text
Standard Process worker succeeds
-> worker moves State to Review
-> Fibery reset automation owns Processing Status = Not Processed
   for the NEW Review cycle
```

After the worker returns, RW-O03 must **not write `Succeeded` over the destination Review cycle**. Re-read the Requirement:

- if State = Review and Processing Status = Not Processed, the completed Process cycle has handed off correctly to the next machine cycle; return to the poll loop immediately so Review may run;
- if State = Review but the reset has not been observed, do not overwrite the status with `Succeeded` or fabricate the reset. Report a partial/configuration problem and leave durable state untouched; the automation may still converge later;
- if State differs, report current-state conflict and do not rewrite it.

This rule avoids the race where the reset automation fires before the runner's post-worker write and the runner would otherwise change the new Review cycle back to `Succeeded`, permanently making Review ineligible.

### Failure outcomes

For a typed dispatch failure whose Requirement is still in the claimed machine State and still carries `Processing`, set `Failed` and confirm it. Do not auto-retry.

RAW candidate-progression failure is a special truthful partial: the RAW worker may already have moved the RAW to `Review`. Raw Review is not a reset target, so if the dispatch outcome is one of the RAW candidate progression conflict/failure/partial outcomes, set the RAW Processing Status to `Failed` only after confirming the RAW is still in Review and the status still belongs to this claimed cycle.

For outcomes where the current State/status cannot be safely established (`STALE_ROUTE`, post-worker read failure, failed status read-back, or another concurrent State change), do not guess a final status. Report partial orchestration and leave what is durable in place. A stuck `Processing` value then follows the accepted RW-C04 recovery limitation rather than being silently stolen/retried.

## Workspace-scoped runner guard

Only one cooperating `sdlc worker run` process may own a workspace on one host/user.

`src/sdlc/worker_runner_guard.py` uses the same OS-managed `flock` design principles as `raw_execution_guard.py`, but the key is workspace-scoped rather than Requirement-scoped. The lock file contains no lifecycle state, no owner metadata and no lease/TTL; kernel release on process exit is the recovery mechanism.

Do not refactor the already-verified per-RAW guard merely to share a few lines unless a concrete correctness problem requires it.

## Runner command

The only normal runner entrypoint is:

```bash
sdlc worker run
```

Optional:

```bash
--poll-interval-seconds <N>
```

with minimum 1 and default 5.

The command uses the configured Fibery workspace and project runtime configuration. It does not accept per-invocation Requirement IDs, State, Type, Processing Status, model output, approval intent or a trigger payload.

The three model-backed worker callables are composed from the existing configured roles; Apply remains model-free. RW-O03 must not change model/runtime/auth semantics.

The runner is foreground/sequential. No daemon manager, background scheduler, queue, webhook server or multi-worker pool is added.

## Abrupt termination

If the process exits after a successful `Processing` claim, status may remain `Processing`. Do not add heartbeat, TTL, stale-lock stealing or automatic retry. Startup/polling treats `Processing` as ineligible. Recovery remains explicit/admin work outside this item, exactly as RW-C04 froze.

## Workspace setup / production readiness

The repository must document exact one-time Fibery setup:

1. add the `Processing Status` single-select field with the exact four values and default;
2. add one Requirement automation triggered by State update;
3. reset to `Not Processed` only for:
   - Raw + Process;
   - Standard + Process;
   - Standard + Review;
   - Standard + Apply;
4. do not reset Raw Draft/Review or Standard Draft/Ready/Applied;
5. verify the rule in the Fibery UI/workspace before treating `sdlc worker run` as production-ready.

Automatic creation of the automation is not part of RW-O03. Do not depend on undocumented automation HTTP endpoints.

## O04 boundary

RW-O03 unit/integration tests prove runner mechanics and the state/status handoff. RW-O04 remains the owner of the complete normal lifecycle end-to-end scenario from RAW Draft through candidate processing, Ready boundaries, rework, approval and Applied completion.
