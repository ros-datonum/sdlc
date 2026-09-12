# RW-B03 Verification v0.1

**Work item:** `RW-B03 — Implement project descriptor contract`  
**Verdict:** VERIFIED  
**Frozen plan:** `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Implementation base:** `916d14169f6ac49dbac969dfe8ee08542aeb6a3f`  
**Implementation commit:** `4189f2c273799d44286ef8f7f135cd9099705c01`  
**Implementation evidence commit:** `94bce32a14122784964a6d052137a6a626b726fd`  
**Descriptor contract:** `docs/rewrite/RW-B03-Project-Descriptor-Contract-v0.1.md`  
**Implementation boundary:** `docs/rewrite/RW-B03-Implementation-Boundary-v0.1.md`  
**Date:** 2026-09-12

## Independent review

The actual branch diff from the frozen B03 baseline contains only:

- `src/sdlc/project_descriptor.py`;
- `tests/test_project_descriptor.py`;
- the moving RW-B03 implementation record in the rewrite plan.

No filesystem, Fibery, CLI bootstrap, environment, model/runtime, check execution, policy execution or standards execution behavior was introduced.

The implementation is a closed pure descriptor contract:

- frozen immutable value model for project identity, Fibery Project-Code mapping, repository policy identifiers, deterministic checks and standards metadata;
- exact schema version 1 with six mandatory top-level groups and no unknown-key retention;
- existing `validate_project_code` reused for Project Code semantics;
- deterministic default construction from normalized Project Name plus already-resolved Project Code only;
- canonical UTF-8/LF/one-final-LF renderer with frozen key order and JSON-compatible quoted strings;
- bounded deterministic parser for the frozen descriptor grammar rather than a general YAML subsystem;
- semantic compatibility by complete parsed-value equality, with invalid or differing existing descriptors treated as conflict;
- no credential, canonical Requirement, lifecycle State, runtime/provider/auth or Fibery workspace/account surface.

## Frozen acceptance criteria

### AC1 — reject missing mandatory identity/config

PASS.

The parser requires all six top-level groups and every frozen nested key, rejects duplicates/unknown keys/wrong structure, validates Project Name/Code, exact Fibery Project-Code equality, repository root and identifiers, checks and standards invariants, and refuses unsupported descriptor versions.

### AC2 — generate descriptor for a new project from bootstrap inputs

PASS.

`new_project_descriptor(project_name, project_code)` accepts exactly those two identity values, trims Project Name, validates the already-resolved Project Code through the existing Project Code contract and produces the frozen default descriptor. It performs no Project-Code collision lookup or repository/environment inspection.

### AC3 — stable unchanged-input/rerun semantics

PASS.

Generation is deterministic; `parse(render(value)) == value` and `render(parse(render(value))) == render(value)` are covered for default and populated valid descriptors. Accepted harmless formatting differences parse to equal semantics, so an existing semantically equal descriptor is compatible without requiring a rewrite.

### AC4 — no credentials or canonical Requirements

PASS.

The closed schema provides no field for credentials, Fibery host/Space/token, model/provider/auth/approval/sandbox/edit settings, Requirement prose/source/State/Processing Status or downstream Architecture/Planning/Task content. Explicit shadow-key tests prove those values fail as unknown keys.

## Scope and preservation

PASS.

- no filesystem I/O or path materialization;
- no Fibery I/O or workspace mapping beyond the stable Project Code string;
- no environment/config read;
- no model/runtime interaction;
- no Project Code collision resolution;
- no B02 guidance materialization;
- no bootstrap CLI/composition;
- no check, branch/worktree/merge-policy or standards execution;
- no new runtime dependency.

Public dataclasses can, as normal Python values, be manually instantiated directly. The frozen renderer/round-trip obligation applies to valid descriptor values; the normal construction/parsing entrypoints enforce the contract. This does not provide a bootstrap bypass because B04 is required to use the validated B03 entrypoints.

## Test evidence

Implementation evidence reports:

- dedicated B03 suite: `126 passed`;
- focused B02 / Project Code / Project Init / CLI regressions: `156 passed`;
- full gate: `uv sync --locked`, `ruff check .`, `ruff format --check .`, `pytest -q` → `2192 passed`;
- red check against the pre-B03 baseline fails at collection because `sdlc.project_descriptor` does not yet exist.

The reviewed tests directly cover the frozen default bytes, parser rejection classes, duplicate/unknown/missing keys, value invariants, round-trips, semantic compatibility, closed authority surface and purity boundary.

## Administrative note

RW-B03 historically showed `BLOCKED` while RW-B01 was unresolved. B01 was independently VERIFIED and the exact B03 contract/boundary were frozen before implementation. The implementation-agent `BLOCKED -> IMPLEMENTING` record is therefore treated as reviewer-authorized dependency clearance; it changes no B03 normative semantics.

## Conclusion

`RW-B03` satisfies all frozen acceptance criteria and preserves its scope boundaries.

**Classification: VERIFIED.**
