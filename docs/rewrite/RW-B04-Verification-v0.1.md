# RW-B04 Verification v0.1

**Work item:** `RW-B04 — Implement one outer project bootstrap action`  
**Verification:** PASS / VERIFIED  
**Verified implementation commit:** `7a4c6b2d6117545768d56694d4b4827fda7f4684`  
**Implementation evidence commit:** `4df52b234fc6bd03ed5d2fa8c041f9a42b2f3116`  
**Date:** 2026-09-12

## Scope reviewed

Independent review compared the RW-B04 branch against base `425817de8a8edac25ba6194a627a3712d7ce6110`, inspected the composed bootstrap implementation, the narrow read-only Project Code preflight helper, CLI composition, dedicated bootstrap tests, the corrective implementation after CHANGES_REQUIRED, and the final moving-plan evidence.

The final production change remains bounded to the frozen B04 ownership:

- `src/sdlc/project_bootstrap.py`;
- a narrow read-only helper in `src/sdlc/project_init.py`;
- `src/sdlc/cli.py` bootstrap wiring.

`requirement_add.py`, Fibery HTTP/schema behavior, B02 template semantics, and B03 descriptor semantics are unchanged.

## Acceptance criteria

### AC1 — one user action initializes a new target — PASS

The composed action validates both exported inputs, resolves Project identity/code read-only, preflights all four managed local paths, materializes the frozen B01/B02/B03 local state, invokes the existing deterministic Project Init primitive, invokes the existing deterministic Requirement Add primitive, and validates the composed result. Empty existing and absent-final target cases are covered.

### AC2 — current-directory and explicit-target modes — PASS

The CLI supports omitted `--target` as current-directory mode and explicit existing/new-final target directories under the frozen target-safety rules.

### AC3 — unrelated files and explicit merge/reuse/conflict policy preserved — PASS

The only managed files are the four B01 paths. B02 owns guidance append/reuse/conflict behavior, B03 owns descriptor semantic compatibility, context is byte-exact, unrelated files are untouched, and local conflicts stop before Fibery mutation. Managed parents/files and the target refuse symlink traversal. The independent-review correction adds a target-root recheck before each local mutation so an absent target swapped to `symlink -> directory` after preflight is never written through.

### AC4 — existing Fibery Project rerun is idempotent/non-destructive — PASS

An exact existing Project is reused only with compatible stable identity/code. The final Project Code is resolved before local materialization and passed explicitly to Project Init, the descriptor, Requirement Add and validation. A later collision does not trigger code re-derivation. A complete rerun reaches `PROJECT_ALREADY_BOOTSTRAPPED` without Project mutation.

### AC5 — initial RAW added exactly once — PASS

The exact decoded RAW source text, after deterministic transport validation only, is passed to the existing `add_raw_requirement` primitive. Duplicate detection remains owned by Requirement Add, and a rerun resolves `REQUIREMENT_ALREADY_ADDED` without creating a second RAW. Final validation requires the fingerprint-resolved Requirement to belong to the intended Project and remain `Type = Raw`, `State = Draft`.

### AC6 — project context present under frozen contract — PASS

The supplied context is treated as opaque bytes and materialized exactly at `.sdlc/project-context.md`; compatible rerun requires exact byte equality and never normalizes or merges it.

### AC7 — partial failure distinguishable and truthful — PASS

The composed result vocabulary distinguishes complete, already-complete, conflict, partial and clean failure. Durable local/Fibery state is never rolled back to simulate atomicity. Project Init / Requirement Add / final-validation failure paths truthfully expose the durable state and stop later composition. The independent-review correction removes the false message that bootstrap “changed nothing else” after local materialization; the message now states that bootstrap stopped before Requirement Add while local created state remains listed.

## Independent-review correction

Initial implementation `725f30e3e831123319dac8f65ae94be3d0656f28` was classified `CHANGES_REQUIRED` for two bounded defects:

1. `_ensure_target()` accepted a late-created target symlink because `Path.is_dir()` followed it;
2. Project Init failure messaging contradicted already-created local state.

Corrective implementation `7a4c6b2d6117545768d56694d4b4827fda7f4684` fixes both without changing bootstrap architecture:

- target symlink check precedes the `is_dir()` success path;
- `_require_real_target()` rechecks the target root immediately before each managed-directory or managed-file mutation;
- a late target symlink fails at `MATERIALIZE_LOCAL`, is left in place, causes no write into its destination and no Fibery call;
- Project Init failure wording is compatible with `PARTIAL_BOOTSTRAP` and the visible created-path report.

The new regressions were reported red against `725f30e3…` and green after the correction.

## Preserved boundaries

Verified preserved:

- Project Init remains the existing deterministic Fibery Project primitive;
- Requirement Add remains the existing deterministic RAW ingestion primitive;
- no requirement reinterpretation or model invocation occurs;
- bootstrap never starts RAW processing;
- descriptor/context/template contain no canonical Requirements mirror or runtime/auth override;
- no generalized repair, rollback or reconciliation engine was introduced;
- no live Fibery/B05 work occurred during B04 implementation.

## Test evidence

Implementation-reported final gates at `7a4c6b2d6117545768d56694d4b4827fda7f4684`:

- dedicated B04: `79 passed`;
- focused regressions: `445 passed`;
- full suite: `2271 passed`;
- `uv sync --locked`: OK;
- `ruff check .`: clean;
- `ruff format --check .`: 174 files formatted.

The evidence commit changes only the moving plan; the full gate was therefore not repeated after it. Independent review inspected the actual final correction diff and final evidence record.

## Process deviations

Two implementation-process disclosures are retained, not hidden:

- the `IMPLEMENTING` mark was committed after implementation work had already occurred, so the moving plan still showed `BLOCKED` during the work;
- the implementation commit was amended before push to satisfy the project function-length gate.

The late status mark is outside the frozen implementation-agent transition procedure and is an administrative deviation. It does not change the frozen B04 semantics or invalidate the implementation evidence. Git history and Execution Notes retain the disclosure.

## Verdict

`RW-B04` satisfies frozen AC1–AC7 and the verified B01/B02/B03/C03 boundaries after the corrective implementation.

**VERIFIED**
