# Worker Runner Setup v0.1

One-time Fibery workspace configuration for `sdlc worker run`, and how to
verify it before production use.

Authority: `docs/architecture/Requirement-State-Worker-Contract-v0.1.md`
(RW-C04) sections 4, 6, 8–9, 20–22 and 27, and
`docs/rewrite/RW-O03-Implementation-Boundary-v0.1.md`. This document adds no
lifecycle semantics.

**The runner validates the field/options, but supported runtime code does not
prove or create the Fibery automation. The operator must verify that rule
before production use.**

## 1. The Processing Status field

Add one field to the `SDLC/Requirement` database:

```text
Field:   Processing Status   (API name SDLC/Processing Status)
Type:    Single Select
Default: Not Processed

Options, exactly:
  Not Processed
  Processing
  Succeeded
  Failed
```

No fifth option. The runner resolves the field from the workspace schema by
its name (`processing status`, preferring the SDLC Space), not from a
hard-coded API name.

At startup the runner checks that the field exists, that the schema shows it
as a single-select (an enum option database, not a collection), and that its
options are exactly the four above. Otherwise it stops with
`WORKER_RUNNER_PREFLIGHT_FAILED` before polling or writing anything.

The runner does not check the default. The public schema does not reliably
show a configured default, so setting it to `Not Processed` is a one-time
workspace setting the operator confirms (section 3, step 2).

Every other command (`project init`, `requirement add`, `process`,
`normalize`, `review`, `approve`, `rework`, `apply`) works whether or not the
field exists.

Requirements that existed before the field was added may show an empty value.
An empty value is not `Not Processed`, so the runner leaves those Requirements
alone. Their next State change into a machine State resets the value
(section 2), and from then on they take part normally.

## 2. The reset automation

Add exactly one automation rule on the `SDLC/Requirement` database. It is
workspace-global: not per Project, and not part of project bootstrap.

```text
Trigger:   Requirement updated — the State (workflow/state) field changed
Condition: (Type = Raw      AND State = Process)
           OR (Type = Standard AND State = Process)
           OR (Type = Standard AND State = Review)
           OR (Type = Standard AND State = Apply)
Action:    set Processing Status = Not Processed
```

The rule must not fire for any other combination, in particular:

```text
Raw + Draft        Raw + Review
Standard + Draft   Standard + Ready   Standard + Applied
```

That keeps `Succeeded` visible at the human boundaries (`Ready`) and at the
settled states (`Raw Review`, `Applied`).

The rule does nothing else: no State change, no other field, no model call, no
web request.

If the rule editor cannot express this condition in one rule, stop and raise a
plan change. Splitting or approximating the rule is a deviation from RW-C04.

RW-O03 does not create this rule programmatically and calls no undocumented
Fibery automation endpoint. Set it up in the Fibery UI.

## 3. Verify before production use

Run the checks with **no `sdlc worker run` process running** against the
workspace. Use a scratch Project and scratch Requirements, never live work. A
Requirement moved into a machine State while a runner is running is real work,
and the runner will execute it.

1. **Field and options.** Start `sdlc worker run` briefly. It must print
   `WORKER_RUNNER_STARTED` and not `WORKER_RUNNER_PREFLIGHT_FAILED`. Stop it
   with Ctrl-C.
2. **Default.** Create a scratch RAW Requirement
   (`sdlc project requirement add` into the scratch Project). In Fibery its
   Processing Status reads `Not Processed`.
3. **Reset targets.** For each of the four combinations, set the scratch
   Requirement's Processing Status to `Failed` by hand, then move its State
   into the combination:
   - RAW: Draft → Process;
   - Standard (a scratch Requirement whose Type is Standard): Draft → Process,
     Process → Review, Ready → Apply.

   Each time, within the automation's delay, Processing Status reads
   `Not Processed`.
4. **Non-targets.** With Processing Status set to `Failed`, move the scratch
   Requirements into Raw Draft, Raw Review, Standard Draft, Standard Ready and
   Standard Applied. Each time it still reads `Failed`.
5. **Clean up.** Leave no scratch Requirement in a machine State at
   `Not Processed`: move it back to a non-machine State or delete the scratch
   Project. Otherwise the next runner start picks it up.
6. **Record** who verified the rule and when, in the workspace's own operating
   notes.

Repository tests prove the runner's mechanics against fakes. They are not
evidence that the live field or rule exists or is configured correctly.

## 4. Running

```bash
sdlc worker run
sdlc worker run --poll-interval-seconds 10
```

- Idle poll interval: default 5 seconds, minimum 1 second, whole seconds. It
  changes only responsiveness, never semantics.
- Foreground and sequential: one Requirement worker at a time. Stop with
  Ctrl-C.
- It watches every Project of the configured workspace. It uses the same
  `FIBERY_*` environment and `config/sdlc.toml` roles as the manual commands,
  and takes no Requirement, State, Type, status, runtime, model or approval
  argument.
- One runner per workspace on one host for one OS user. A second one exits
  with `WORKER_RUNNER_BUSY`. The lock is an empty `flock` file in the SDLC
  lock directory (`~/.sdlc/locks`, or `SDLC_LOCK_DIR`), released by the kernel
  when the runner ends. Runners on different machines are not coordinated and
  are unsupported.
- Output is result codes, Requirement IDs, entity ids, Type, State and
  Processing Status. Requirement content, prompts, model output and
  credentials are never printed.

What the runner writes, per route:

| Route | Worker completes | Worker fails |
|---|---|---|
| Raw + Process | RAW → Review, candidates Draft → Process; RAW `Succeeded` | `Failed` in Process; a candidate-progression failure is `Failed` in Review, nothing rolled back |
| Standard + Process | nothing: the worker moved it to Review, and the reset automation owns the new Review cycle's `Not Processed` | `Failed` in Process |
| Standard + Review | Ready, `Succeeded`, whatever the verdict | `Failed` in Review |
| Standard + Apply | Applied, `Succeeded` | `Failed` in Apply |

Before it runs a worker, the runner re-reads the Requirement and claims it
with `Processing`, confirmed by reading it back. If the claim cannot be
written or confirmed, no worker starts.

After Standard Process, `RESET_NOT_OBSERVED` means the Requirement is in
Review but its status is not yet `Not Processed`. The runner wrote nothing
and Review has not started. The automation may still apply the reset;
otherwise its configuration needs checking (section 3).

## 5. Accepted v0.1 limitations

- Fibery offers no compare-and-set. The workspace lock excludes a second
  cooperating runner on the same host only.
- A Requirement can stay in `Processing`: after a killed or interrupted
  runner, after a status write that could not be confirmed, or after a cycle
  the runner reported as `PARTIAL`. The runner never treats an old
  `Processing` as stale, retries it or steals it. Recovery is an explicit
  admin decision taken after inspecting the Requirement's durable results
  (RW-C04 sections 21, 22 and 25). The runner provides none.
- `Failed` is never retried automatically.
