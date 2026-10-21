# Requirement Worker Project Scope — v0.1 (delta)

**Status:** IMPLEMENTED ON BRANCH `impl/requirements-worker-project-scope`. Verified offline. The scoped query shape was read live and read-only (§9). No live worker has run.
**Authorization:** human instruction "Implement Project-Scoped Requirement Worker for the ARP1 Pilot", for baseline `9da898a096d7e4de8af98ee6a7fef0f0dbd7d19c`. The approval record is that instruction; no signature is claimed.
**Amends, narrowly and only as stated here:**
- Requirement-State-Worker-Contract-v0.1 (RW-C04) §8, where the runner "watches all Projects": that stays the default, and an operator may narrow it to one Project (§2);
- RW-O03's command surface: `sdlc worker run` gains exactly one argument, `--project CODE`;
- the RW-O02 dispatcher, in both modes: route drift now includes the Project, and RAW candidate progression requires the RAW's own Project (§6).

Those documents are unchanged on disk. Where this delta and they disagree, this delta governs for the listed points only.

This is an operational execution constraint, not a workflow. There is no new State, database, model role, scheduler, lock or relation. Processing Status, the reset automation, routes, priorities, claims, postconditions, recovery and WI-1 to WI-6 are unchanged. The committed configuration keeps `[autonomy]` and `[ready_decisions]` disabled.

## 1. Purpose

A workspace can hold eligible machine work in Projects that must not be touched. On 2026-10-21 three historical TSAP1 Requirements were at `Standard + Process + Not Processed`, and their public ids were lower than the pilot's. An unscoped runner would process them first. A scoped runner works only on the one Project its operator names.

## 2. Command

```text
sdlc worker run [--poll-interval-seconds N] [--project CODE]
```

- **Without `--project`:** every Project of the configured workspace, exactly as before, except for the two dispatcher invariants of §6.
- **With `--project CODE`:** only the Project whose Project Code is exactly `CODE`.
- Nothing else is configurable: no Name selector, no allow-list, no runtime or model override.

## 3. Resolution (once, before the workspace lock)

The selector must already be a valid Project Code exactly as written. A Name, a different case, surrounding whitespace or a partial Code is refused. Nothing is normalized for the operator.

Then, in this order:
1. the number of Projects with that Code must be exactly one (Fibery does not enforce uniqueness, API constraint 14);
2. that Project is read by Code;
3. it is re-read by its entity id and must carry the same entity and Code.

The scope is then bound as `(Project entity id, Project Code, workspace identity)`. The workspace identity is the runner lock's identity (host and Space UUID).

Any failure refuses the command with `WORKER_RUNNER_PROJECT_INVALID` and exit 1, before the lock, the preflight or any poll. This covers an unknown Code, an ambiguous Code, an inconsistent read-back and a Fibery read failure. Nothing falls back to the whole workspace. A Fibery Project is never created.

## 4. Scope lifetime

The scope holds for the whole run, and is checked against fresh Fibery data, never against an earlier poll row.

| When | Check | On failure |
|---|---|---|
| before every claim | the same workspace identity; the Project read by entity id exists, is that entity and has the bound Code | `SCOPE_INVALID`: nothing written; the runner stops |
| before every dispatch, after the claim is confirmed | the same | `SCOPE_INVALID`: the claim stays as written (`Processing`) for explicit recovery (RW-C04 §25), nothing more is written; the runner stops |
| before every Ready decision | the same | `SCOPE_INVALID`: no decision, nothing written; the runner stops |

The runner reports the `SCOPE_INVALID` cycle, then ends with `WORKER_RUNNER_PROJECT_INVALID` and exit 1. A Project whose Code changed is not followed under its new Code: the operator restarts the runner with the Code they intend.

Idle cycles read no Project. A check costs one Project read, made only when there is a candidate.

## 5. Filtering

Both eligible-work queries take an optional Project entity id. When it is given, Fibery applies the same filter plus one clause, `["=", ["<Requirement Project field>", "fibery/id"], "$project"]`. This is the clause `requirement add` already uses for duplicate detection.

- **Machine query** (`find_eligible_requirements`): the four routes at `Not Processed`, ordered by `fibery/public-id`. Its limit (`ELIGIBLE_QUERY_LIMIT`, 100) applies within the Project. Other Projects' work, however low its ids, can therefore never fill the page and starve the scoped work. Rows are never filtered in Python after a global page.
- **Ready query** (`find_eligible_requirements_after`): the WI-6 cursor pagination by `fibery/id`, inside the Project. The cursor, page bound, remembered decisions, budgets, oscillation stops and HUMAN_REQUIRED handling are unchanged. A scoped decider never reads, decides or reports another Project's Ready Requirement.
- **Unscoped:** both queries are sent exactly as before, with no Project clause.

## 6. Requirement ownership

- **Pre-claim re-read and claim read-back:** a scoped runner requires the fresh Requirement's Project to be the bound entity, compared with the scope itself and not with the poll row. A Requirement that moved out is `CANDIDATE_CHANGED` before the claim, or `CLAIM_NOT_CONFIRMED` after it. No worker runs. Because this is a single Requirement and not the scope, the runner continues.
- **Dispatcher route drift (both modes):** the dispatcher's last read before the worker now compares the Project as well as Requirement ID, Type and State. A move gives `STALE_ROUTE`, and no worker is called.
- **RAW candidate progression (both modes):** a candidate the RAW result names is progressed `Draft -> Process` only if it is that RAW's own Standard Draft, derives from it, and belongs to the RAW's Project. Anything else gives `CANDIDATE_PROGRESSION_CONFLICT`, and no candidate is moved.
- **Unchanged:** RAW decomposition already creates every candidate in the RAW's Project and verifies it on read-back (RAW processor).
- **Ready decisions:** the WI-6 final guard is unchanged. It binds the Requirement, its Project entity and Code, `Ready + Succeeded`, the evidence, and the authorization for that Code. An authorization is never reused across Projects.

## 7. Unscoped compatibility

An unscoped runner differs from v0.1 of RW-O03 only in §6's two dispatcher invariants. Both fail closed, and neither changes a valid route: a Requirement whose Project did not change, and a candidate in its RAW's Project, behave exactly as before.

## 8. Concurrency

Fibery has no compare-and-set. Every check here is a read just before a write: it narrows the window but does not close it.

- A Requirement can move to another Project, or a Project can change Code, between the last check and the claim write, between the claim read-back and the worker's own reads, or during a worker run. The claim write itself can therefore land on a Requirement that has just moved. Its read-back then refuses the dispatch.
- A worker that has started is not interrupted. Its own preconditions, such as Apply's dependency, source and policy checks, still apply.
- The workspace lock is unchanged: one cooperating runner per workspace on one host, scoped or not. Two scoped runners for different Projects cannot run at the same time on one host. Multi-host operation stays unsupported.

## 9. Evidence

**Offline:** `tests/test_worker_project_scope.py` uses the real runner, dispatcher, decider and workers on the Fibery fakes, with a second Project whose work has lower ids. It covers:
- resolution refusals and command refusals before any poll;
- Project and Requirement changes before the claim and before the dispatch;
- RAW decomposition and candidate ownership;
- more than one page of scoped machine and Ready work behind more than one page of foreign work;
- Process, Review, AUTO_REWORK, AUTO_APPROVE and Apply under a scope;
- no Ready query when delegation is disabled;
- unchanged locking and the scoped query shape.

The unscoped query shape stays pinned in `tests/test_requirement_runner.py`.

**Live, read-only** (2026-10-21; only `fibery.schema/query` and `fibery.entity/query`):
- **Projects:** the production adapter resolved and re-checked the scope of every one of the workspace's six Projects.
- **Ready query:** run per Project, cursor-paged at page sizes 100, 7, 3 and 1.
- **Machine query:** run per Project at limits 100, 2 and 1. A correct limit-1 result proves the filter applies before the limit.
- **Same method across states:** run over every route and status present, at page sizes 100 and 4.
- **Results:** every result equalled an independently read reference set for that Project, with no duplicate and no row of another Project. A non-existent Project entity id returned no rows from either query. A lowercase Code and a Project Name were refused.
- **Not observed live:** more than 100 scoped rows at the production page size. No live worker was started.

## 10. Codes

| Code | Where | Meaning |
|---|---|---|
| `WORKER_RUNNER_PROJECT_INVALID` (new) | `sdlc worker run` | The scope could not be resolved at start, or stopped holding during the run (§3, §4). |
| `SCOPE_INVALID` (new) | runner cycle | The bound Project no longer holds; nothing more was written; the runner stops (§4). |
| `CANDIDATE_CHANGED`, `CLAIM_NOT_CONFIRMED`, `STALE_ROUTE`, `CANDIDATE_PROGRESSION_CONFLICT` | existing | Now also raised for a Requirement or candidate outside its Project (§6). |
