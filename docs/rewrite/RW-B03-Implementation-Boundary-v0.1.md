# RW-B03 Implementation Boundary v0.1

**Status:** FROZEN  
**Work item:** `RW-B03 — Implement project descriptor contract`  
**Derived from:** `RW-B03-Project-Descriptor-Contract-v0.1.md`, verified RW-B01/B02, verified RW-C03  
**Semantic change to RW-C03:** NONE  
**Date:** 2026-09-12

## Exact primary module

RW-B03 owns one new production module:

```text
src/sdlc/project_descriptor.py
```

Primary tests:

```text
tests/test_project_descriptor.py
```

No other production file is an expected B03 design surface.

## Pure boundary

The module is pure:

- descriptor value objects;
- schema validation;
- default descriptor construction from resolved Project Name + Project Code;
- deterministic canonical renderer;
- parser for the frozen descriptor YAML subset;
- semantic equality/compatibility.

It performs no filesystem or Fibery I/O and invokes no model.

`src/sdlc/project_code.py` is reused for Project Code validation; its behavior is not changed by B03.

## Dependency boundary

Do not add a YAML/runtime dependency merely for this descriptor. The parser only needs the bounded grammar frozen by the descriptor contract. Standard-library modules are sufficient.

## Construction boundary

A default bootstrap descriptor constructor receives:

```text
project_name
resolved_project_code
```

The code is already resolved under Project Init semantics by its caller. B03 validates it but does not query Fibery uniqueness.

Default generated values are exactly:

```text
repository.root = "."
branch_policy = null
worktree_policy = null
merge_policy = null
checks = []
standards.profile = null
standards.extensions = []
```

## Parsing/rendering boundary

Parsing must reject unknown/missing/duplicate structure rather than preserve it as opaque data.

Canonical rendering uses UTF-8/LF/final-LF, frozen key order and JSON-compatible double-quoted string scalars as defined by the contract.

The parser may accept semantically equivalent descriptor formatting only where the implementation can do so deterministically without becoming a general YAML parser. It must at least parse its own canonical output and the explicitly tested compatible formatting cases.

## Compatibility boundary

Expose a pure compatibility decision equivalent to:

```text
existing descriptor bytes/text
+ requested ProjectDescriptor
-> COMPATIBLE | CONFLICT
```

A valid parsed descriptor equal to the requested descriptor is compatible and must not require rewriting. Invalid or unequal content conflicts.

Do not introduce merge/patch behavior.

## Non-goals

RW-B03 does not implement:

- target path resolution;
- symlink safety;
- file writes;
- B02 managed-block materialization;
- context copying;
- Project Code uniqueness resolution;
- Fibery workspace/project lookup;
- `sdlc project bootstrap`;
- check execution;
- policy execution;
- standards-profile execution.

These remain downstream responsibilities.
