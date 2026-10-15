# TSA-C01 — Implementation Specification v0.6 (delta to v0.3 + v0.4 + v0.5)

**Status:** FROZEN.
**Human approval:** explicit instructions approving the four I12 decisions and
the bounded I12 correction below, given for repository snapshot
`8590176772e398d07675b6809907c687924f573e`.
**Implementation authorization:** GRANTED ONLY FOR THE BOUNDED I12 CORRECTION
DESCRIBED IN SECTION 7.
**Authority source:** `docs/architecture/TSA-C01-Contract-v0.2.md` (frozen),
unchanged.
**Base:** `docs/specs/TSA-C01-Implementation-Spec-v0.3.md`,
`docs/specs/TSA-C01-Implementation-Spec-v0.4.md` and
`docs/specs/TSA-C01-Implementation-Spec-v0.5.md` (all frozen), unchanged.

The approval record is those instructions. No signature or authenticated
identity is claimed for them.

## 1. Relation to v0.3, v0.4 and v0.5

**SPEC.** This document is a **delta**. v0.3, v0.4 and v0.5 remain
authoritative and apply in full, except for the additions below. Nothing in
them is restated, amended or replaced, and their files are unchanged. Every
cell of the command × durable-state table (v0.3 13.6) and every meaning and
exit class of the result-code catalogue (v0.3 13.8, v0.5 section 2) is kept.

## 2. New result code `WORKSPACE_GUARD_UNAVAILABLE`

**SPEC — addition to the result-code catalogue of v0.3 13.8.**

| Code | Meaning | Exit |
|---|---|---|
| `WORKSPACE_GUARD_UNAVAILABLE` | The required same-host, same-user workspace guard (contract 13) could not be established; the command did not run unguarded | 1 |

**SPEC.** A mutating command (`start`, `resume`, `rework`, `approve`) that
cannot establish the guard **MUST NOT** run unguarded: it reads no Project or
cycle data, makes no lifecycle mutation and calls no model.

**SPEC.** It is distinct from `WORKSPACE_BUSY`, which keeps its meaning: the
guard is currently held by another cooperating command.

## 3. Recovery stopped before the Human Decision boundary

**SPEC.** When `start`, `resume` or `rework` has made durable progress and
downstream recovery then refuses before the intended boundary, the **specific
downstream refusal code remains authoritative** (exit 1). Partial progress is
never reported with a success code.

**SPEC — truthful progress.** Such a refusal states the durable progress that
is established, and it no longer carries a trailing claim that nothing was
persisted or written. Each layer states only the progress it owns:

- recovery (I10) states what its own delegated stages made durable within the
  same invocation, from the stage results: a persisted Process Result, an
  output applied to the Architecture Document, a written and confirmed Review
  Result;
- the command (I12) states only what it made durable before recovery ran: the
  Input Manifest that `start` wrote, and for `rework` the REWORK Decision that
  I11 recorded;
- a stage's own mutation-aware message, and the refusal's code and details,
  are kept.

**SPEC.** Each such fact is stated only where read-back or a domain result
established it — after an unknown write outcome, only where rediscovery found
the very artifact this command emitted. A generic statement that nothing was
written, persisted or overwritten is then no longer made; the refusal's
diagnosis is otherwise unchanged.

**SPEC.** Where no more specific failure is returned and recovery reports
that it stopped before the boundary, the command reports
`ARCHITECTURE_CYCLE_RESUMED` (exit 0). Its message **MUST NOT** claim that
the Human Decision boundary was reached, **MUST NOT** claim causes it cannot
show, and directs the operator to `resume` to re-read durable state. For
`rework`, where the REWORK Decision is established as durable, the message
may say so.

## 4. `inspect --json` framing

**SPEC.** With `--json`, the output of `inspect` is exactly: the result code
on the first line, one blank line, then one JSON object. The object also
contains `"code"` with the same result code. There is no other prose. The
stream and the exit class follow v0.3 12.3 unchanged.

## 5. Failures before any command engine runs

**SPEC.** Fibery settings, or the workspace or Space identity a command
requires, that are unavailable before the command executes:
`FIBERY_READ_FAILED`, exit 1.

**SPEC.** A TSA model role (`tsa_architect`, `tsa_reviewer`) whose runtime
configuration cannot be resolved: `MODEL_RUNTIME_FAILED`, exit 1, raised only
when that role is first actually needed. A path that needs no model never
requires the runtime configuration.

## 6. No other change

**SPEC.** No other result code, command, flag, durable state, table cell or
command semantics is added or changed. No persisted artifact is migrated,
rewritten or re-sealed, and no wire schema changes.

## 7. Bounded authorization

**Authorized:** the I12 correction that implements sections 2 to 5 in
`src/sdlc/tsa_cli.py` and `src/sdlc/cli.py`; the truthful progress statement
of I10 in `src/sdlc/tsa_recovery.py`; the read-only per-input currentness
read (v0.3 13.5) in `src/sdlc/tsa_architect.py`, over the I05 admission
halves exposed in `src/sdlc/tsa_admission.py`; the I05 fact that the durable
Input Manifest is this call's own confirmed write; and their tests.

**Not authorized:** any other work item; worker integration; changes to
dependencies, runtime configuration or settings; live Fibery or model runs;
merge.
