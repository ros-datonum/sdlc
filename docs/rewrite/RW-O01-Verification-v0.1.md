# RW-O01 Verification v0.1

**Status:** VERIFIED  
**Work item:** `RW-O01 — Separate normal lifecycle control from admin CLI invocation`  
**Frozen plan:** `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Verified implementation commit:** `5433c3c676a9326a31621ba1493367dd4d562cb3`  
**Implementation evidence commit:** `97d82b68d38be77ffefa72dd4b133fb5ee63e4c3`  
**Verification date:** 2026-09-11

## Verdict

`RW-O01` satisfies its frozen acceptance criteria and is approved for merge.

The implementation correctly separates lifecycle authority from control surface:

- human-owned `Ready -> Apply` is the durable approval signal;
- human-owned `Ready -> Process` is the durable rework signal;
- direct Fibery State transitions require no `approve`/`rework` CLI invocation;
- the existing CLI commands remain bounded admin/compatibility conveniences and create no second semantic authority;
- Apply independently revalidates the exact reviewed state regardless of how State reached `Apply`;
- existing Ready/Apply/Process validation behavior remains intact.

## Acceptance criteria

### AC1 — direct human Ready -> Apply

PASS.

The real Apply capability accepts a Standard Requirement already moved directly to `Apply`, without an `approve` command or verdict acknowledgement, for `PASS`, `NEEDS_WORK`, and `BLOCKING`. Apply still refuses stale reviewed evidence before normative mutation.

### AC2 — direct human Ready -> Process

PASS.

A direct `Ready -> Process` State transition is sufficient rework authority without the `rework` command, artifact, flag, or marker. Existing Process/Review history is preserved. The Standard Process capability still owns its own State precondition.

The reviewed correction makes explicit that an edit is **not** a precondition of rework. An unchanged-tree rework is valid human authorization even though today's manual Standard Process path returns `NO_CHANGES_TO_PROCESS`; that stall is a known orchestration gap, not a completed rework cycle.

### AC3 — approve/rework CLI is admin/compatibility behavior

PASS.

CLI help and documentation identify `approve` and `rework` as admin/compatibility surfaces. The `approve` command retains its evidence validation and non-PASS acknowledgement as command-specific safety UX; neither is durable approval authority. `rework` still makes only the State transition.

### AC4 — existing validation preserved

PASS.

Ready and Apply decision logic was not weakened. Existing stale-evidence, tree/fingerprint, malformed/ambiguous history, mutation-boundary and Apply revalidation suites remain green. The RW-O01 correction changed no production Process/dispatcher/Processing-Status code.

## CR-002 review decision

`CR-002` is **non-blocking for RW-O01** but constrains the next orchestration work.

Rejected semantic option:

```text
Require a human edit before Ready -> Process counts as rework.
```

That would contradict verified `RW-C02`, where `Ready -> Process` itself authorizes a new Standard Process cycle.

Accepted semantic requirement:

```text
A human Ready -> Process authorizes a new Standard Process cycle even when the
current normative tree is byte-identical to the latest Process output.
```

Current implementation gap:

```text
unchanged tree
+ Ready -> Process
-> current manual Standard Process returns NO_CHANGES_TO_PROCESS
-> State remains Process
```

That is not a valid completion of the rework chain.

Implementation ownership is deferred to `RW-O02` / `RW-O03`: the state-driven worker path must have a bounded, non-general-force way to start the newly authorized Process iteration over the current tree. The exact dispatcher/processor interface is not designed by RW-O01.

## Evidence

Implementation report records:

- focused suites: `344 passed`;
- full gate: `1731 passed`;
- correction-only commit changed the Ready spec and lifecycle-control tests;
- `src/` and `config/` were unchanged by the review correction;
- worktree was clean at handoff.

Independent inspection confirmed the corrected Ready spec distinguishes human authorization from the current unchanged-tree worker gap and the tests pin that distinction.
