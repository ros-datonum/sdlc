# Requirement Lifecycle v0.2 — Current

**Status:** CURRENT. The operational Requirement lifecycle as implemented and independently verified.  
**Supersedes for current operations:** `Requirement-Lifecycle-v0.1-Checkpoint.md` (retained as historical checkpoint)  
**Authority:** `Requirement-Lifecycle-Ownership-v0.2.md` (RW-C02), `Requirement-State-Worker-Contract-v0.1.md` (RW-C04)  
**Verification:** `docs/rewrite/RW-O04-Verification-v0.1.md`  
**Date:** 2026-09-13

## 1. The normal path

```text
requirements-export (external)
→ sdlc project bootstrap
→ Project + initial Raw Draft + consumer project SDLC metadata/context

HUMAN:
Raw Draft -> Process

MACHINE:
RAW Process
→ Processing Result
→ 0..N Standard candidates
→ exact produced candidates Draft -> Process automatically

MACHINE:
Standard Process
→ Review

AUTOMATION:
State enters Standard Review
→ Processing Status reset to Not Processed

MACHINE:
Standard Review
→ Ready
→ Processing Status Succeeded
→ STOP

HUMAN:
Ready -> Process    REWORK
or
Ready -> Apply      APPROVE

MACHINE after REWORK:
new immutable Process iteration
→ Review
→ new immutable Review iteration
→ Ready
→ STOP

MACHINE after APPROVE:
deterministic Apply
→ Applied
```

Bootstrap stops at `Raw + Draft`. It starts no processing.

## 2. Human authority

The only normal human-owned Requirement transitions are:

```text
Raw Draft -> Process        authorize processing of this RAW source
Standard Ready -> Process   REWORK
Standard Ready -> Apply     APPROVE
```

`Standard Draft -> Process` is **not** a per-candidate human transition.
Candidates produced by an authorized RAW processing cycle inherit that
authorization and are progressed to `Process` by the verified dispatcher, which
re-reads each candidate and confirms it belongs to that exact successful RAW
Processing Result before moving it. A `Standard + Draft` Requirement is never
auto-promoted merely because it exists.

The human makes these transitions in Fibery, or an authorized assistant makes
one on the human's explicit instruction. No approval or rework artifact, flag,
field or ledger exists: the State transition **is** the decision.

### Review verdict is evidence, not authority

```text
PASS | NEEDS_WORK | BLOCKING
```

A verdict never approves, rejects or reworks anything. Review always moves a
successfully reviewed Requirement to `Ready` whatever the verdict, and a human
decides there. `Processing Status = Succeeded` with `Review Verdict = BLOCKING`
is a normal, non-contradictory state: the worker completed correctly and
reported a blocking assessment for the human.

## 3. State-driven execution

```text
normal human intent      = State transition in Fibery
normal machine execution = sdlc worker run → poll → dispatcher → real worker
worker routing           != lifecycle authority
```

`sdlc worker run` is one foreground local process. It polls the configured
workspace for eligible Requirements, claims one at a time, and invokes exactly
one existing bounded worker per cycle. It is an executor: it never creates
authority, never crosses a human boundary, and holds no lifecycle truth of its
own. Durable lifecycle truth is Fibery's `Type`, `State`, `Processing Status`,
Requirement content, relations and evidence artifacts.

This is not a distributed orchestration system. There is no queue, no broker,
no scheduler, no public webhook, no multi-host coordination and no
exactly-once delivery claim.

### Runner prerequisite

Before normal runner operation the Fibery workspace must already have the
verified `Processing Status` field and its reset automation configured, per
`docs/fibery/Worker-Runner-Setup-v0.1.md`. The runner validates the field and
its option set at startup. **It does not create the automation**, and a green
startup does not prove the automation rule is correctly configured; the
operator verifies that in the workspace.

### Eligible routes

Only these combinations invoke a worker:

| Type | State | Required Processing Status | Worker |
|---|---|---|---|
| Raw | Process | Not Processed | RAW Requirement Processor |
| Standard | Process | Not Processed | Standard Requirement Process |
| Standard | Review | Not Processed | Standard Requirement Review |
| Standard | Apply | Not Processed | deterministic Apply |

No other `Type + State` combination invokes machine work. `Raw + Draft`,
`Raw + Review`, `Standard + Draft`, `Standard + Ready` and `Standard + Applied`
are explicit no-ops for the runner.

## 4. Processing Status

Exactly four values:

```text
Not Processed
Processing
Succeeded
Failed
```

`Processing Status` answers "what happened in the machine cycle for the current
State". It is **not** lifecycle State and is not an approval signal.

### Reset targets

Workspace automation resets `Processing Status` to `Not Processed` when a
Requirement enters:

```text
Raw + Process
Standard + Process
Standard + Review
Standard + Apply
```

There is **no** reset at:

```text
Raw + Review
Standard + Ready
Standard + Applied
```

Those are terminal or human-boundary states, so the last worker's `Succeeded`
stays visible there until a human starts a new cycle.

## 5. The Standard Process → Review handoff

This is the subtle part and is documented exactly:

```text
Standard Process claimed at Processing

worker succeeds
→ State becomes Review

Fibery reset automation
→ Processing Status becomes Not Processed
  for the new Review cycle

runner must NOT write Succeeded for the old Process cycle
after that reset

Review is then claimed and processed independently
```

Process and Review are **two** processing cycles, not one. Writing `Succeeded`
for the completed Process cycle after the reset would overwrite the destination
Review cycle's `Not Processed` and make the Review ineligible. The verified
runner therefore reports the handoff instead of writing status, and the
successful Process outcome remains recoverable from its durable Process Result.

## 6. Failure and recovery boundary

Verified behavior only:

- a failed worker leaves `State` unchanged and `Processing Status = Failed`;
- `Failed` is **not** automatically retried;
- a stale or stuck `Processing` is **not** automatically stolen or recovered;
- there is no TTL, heartbeat, lease or stale-owner recovery in this version;
- failure is never represented by advancing to the success State;
- the runner guard prevents a second cooperating local runner for the same
  workspace on the same host/user; multi-host exclusion is unsupported;
- explicit admin/recovery commands remain available where already supported,
  and are used deliberately rather than automatically.

If the runner process is killed after claiming work, the Requirement may remain
`Processing`. That requires explicit operator handling; the runner never assumes
an old `Processing` value is stale and re-executes it.

## 7. Rework preserves history

A human `Ready -> Process` starts a new Standard Process cycle over the current
content. Prior Process and Review Results remain immutable history: they are
never overwritten or deleted, and the new cycle adds a new numbered iteration.

## 8. Apply

`Ready -> Apply` is the durable approval signal, and `State = Apply` is the only
approval signal Apply consumes. Apply is deterministic and model-free. It
independently revalidates the exact reviewed binding before any canonical
mutation, however the Requirement reached `Apply`, and moves `Apply -> Applied`
only after its work is verified. A stale or drifted binding leaves the
Requirement in `Apply`; it is never falsely marked `Applied`.

## 9. Requirement placement

```text
Requirement Type + State        = lifecycle placement
Requirement-contained Documents = canonical Requirement documents
fibery/Folder                   != lifecycle authority
```

The historical physical `Requirements/{Raw,Draft,Approved}` folder tree is
retired historical behavior. No command creates, resolves or moves a Folder.
Smart Folder / context views are optional human navigation and are not runtime
dependencies.

## 10. What this lifecycle does not do

It does not produce architecture, delivery plans, Epics, Stories, Tasks, code,
releases or deployments. Those phases exist in the product architecture
(`SDLC-MVP-v0.5-Current-Architecture.md`) and have no implementation.
