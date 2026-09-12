# RW-B02 Implementation Boundary v0.1

**Status:** FROZEN — READY FOR IMPLEMENTATION  
**Work item:** `RW-B02 — Implement reusable consumer project template`  
**Depends on:** `RW-B01`, satisfied by `docs/rewrite/RW-B01-Verification-v0.1.md`  
**Semantic change to RW-B01/RW-C03:** NONE  
**Date:** 2026-09-12

## 1. Purpose

`RW-B02` implements the reusable **static** portion of the consumer-project template frozen by RW-B01 without implementing bootstrap composition.

B02 does not write a consumer repository or Fibery. It provides one reusable, deterministic, testable contract that B04 can call later.

## 2. Exact production module

B02 owns one new module:

```text
src/sdlc/consumer_template.py
```

Primary tests:

```text
tests/test_consumer_template.py
```

No static template resource directory is required. The exact frozen agent-guidance block may live as an immutable module constant so packaging cannot omit a resource file.

## 3. Closed manifest represented by B02

The module must expose the closed RW-B01 managed consumer path set:

```text
.sdlc/project.yaml
.sdlc/project-context.md
AGENTS.md
.claude/CLAUDE.md
```

It must separately identify the only two **static B02 template paths**:

```text
AGENTS.md
.claude/CLAUDE.md
```

The distinction is mandatory:

- `.sdlc/project.yaml` is generated under B03, never by a B02 placeholder;
- `.sdlc/project-context.md` is copied from the bootstrap input under B04, never embedded by B02;
- only the two agent-guidance files have static template content in B02.

Optional managed/static paths are none.

## 4. Exact managed block

B02 must expose the exact markers and managed block from `RW-B01-Template-Manifest-v0.1.md` without alteration.

There are no dynamic placeholders.

Do not add project name, project code, repository name, model, provider, auth or path placeholders to the block.

## 5. Pure template API

B02 should expose a small pure API over existing file bytes. Exact names may vary modestly, but the capability boundary is frozen:

```text
closed manifest constants
static guidance path constants
managed marker/block constants

classify existing agent-guidance content
plan/materialize the resulting agent-guidance bytes
```

The implementation may use an enum/dataclass for disposition/results.

At minimum callers must be able to distinguish:

```text
ABSENT
APPENDABLE_FOREIGN_CONTENT
COMPATIBLE
CONFLICT
```

and obtain deterministic output bytes for the two non-conflict materialization cases that require output.

A conflict must carry a bounded reason suitable for B04 diagnostics without including arbitrary file content.

## 6. No filesystem ownership in B02

B02 must not:

- create directories;
- open/write target repository files;
- resolve symlinks;
- choose a target directory;
- read bootstrap arguments;
- call `project init`;
- call `project requirement add`;
- contact Fibery.

Those operations belong to B04.

B02 is therefore safe to exercise entirely with bytes in unit tests.

## 7. Agent-guidance merge semantics

Implement the RW-B01 policy exactly.

### Absent file

Return bytes containing only the exact managed block plus one terminating LF.

### Existing empty regular-file content

Treat an empty byte sequence equivalently to an absent-content body for materialization: resulting file is only the exact managed block plus one terminating LF.

The filesystem distinction absent vs present-empty may still be retained in the disposition for B04 reporting.

### Existing UTF-8 content with no marker

Preserve all existing bytes exactly.

Append enough newline bytes to ensure at least one blank-line separation before the managed block:

- if content is empty: no prefix separator;
- if content ends in at least two newline sequences: append the block directly;
- if content ends in exactly one newline sequence: append one additional newline sequence;
- otherwise append two newline sequences.

Use CRLF for appended material only when the existing content uses CRLF and contains no lone LF line endings. Otherwise use LF.

Never rewrite existing foreign line endings.

### Current managed block

Normalize only CRLF to LF while inspecting the managed block.

A single exact current block under that line-ending normalization is `COMPATIBLE`; return/reuse the original bytes unchanged.

Foreign bytes before or after it remain irrelevant to managed-block compatibility and are never rewritten.

### Conflicts

Return `CONFLICT` for all RW-B01 conflict cases:

- invalid UTF-8;
- one missing marker;
- markers reversed;
- multiple BEGIN/END markers;
- managed block differs beyond LF/CRLF equivalence.

Filesystem-type and symlink conflicts are B04 because B02 receives bytes only.

## 8. Exact-content discipline

Do not make managed-block matching fuzzy.

Forbidden compatibility shortcuts include:

- trimming arbitrary whitespace;
- case-insensitive comparison;
- ignoring bullet order;
- Markdown semantic comparison;
- accepting an older or partial block;
- regex replacement of a differing block.

The only compatibility normalization is `CRLF -> LF` inside the candidate managed block.

## 9. Security/configuration constraints

The module/template must contain no:

- token/key/credential value;
- host/account id;
- model/provider choice;
- runtime endpoint;
- approval policy;
- permission mode;
- sandbox/edit mode;
- environment variable value.

It may contain instructional text saying such settings must not be overridden.

## 10. Tests

B02 tests must cover at least:

1. closed four-path managed manifest exactly equals RW-B01;
2. static template paths are exactly `AGENTS.md` and `.claude/CLAUDE.md`;
3. optional paths are none;
4. exact frozen BEGIN/END markers;
5. exact frozen managed block;
6. no placeholder substitution exists;
7. absent content materializes exact block + LF;
8. empty content materializes exact block + LF;
9. LF foreign file appends with correct blank separation and preserves original bytes;
10. CRLF foreign file appends CRLF block and preserves original bytes;
11. mixed-line-ending foreign content is preserved and appended material uses LF;
12. current LF block is compatible/no-op;
13. current CRLF block is compatible/no-op;
14. foreign content before/after a valid block survives byte-for-byte;
15. one missing marker conflicts;
16. reversed markers conflict;
17. duplicate markers conflict;
18. modified managed wording conflicts;
19. whitespace/bullet modification conflicts;
20. invalid UTF-8 conflicts;
21. conflict diagnostics do not echo arbitrary input file content;
22. output contains no undeclared consumer path or runtime/auth override artifact.

## 11. Must not

B02 must not implement or create:

```text
.sdlc/project.yaml contents
.sdlc/project-context.md contents
.codex/config.toml
.claude/settings.json
.agents/
.claude/agents/
.claude/skills/
.agents/skills/
filesystem bootstrap
Fibery bootstrap
```

No B03/B04 behavior is pulled into this item.

## 12. Dependency/plan disposition

The moving rewrite plan may still show RW-B02 as `BLOCKED` because its historical blocker was RW-B01. This sidecar is the reviewer-owned dependency disposition: RW-B01 is now VERIFIED and the B02 blocker is cleared.

Implementation may proceed. If the implementation agent records `BLOCKED -> IMPLEMENTING` in the moving plan, it must explicitly note that the transition is reviewer-authorized dependency clearance rather than a semantic plan change; frozen B02 text remains unchanged.