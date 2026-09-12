# RW-B01 Verification v0.1

**Status:** VERIFIED  
**Work item:** `RW-B01 — Freeze reusable consumer project template contents`  
**Frozen rewrite plan:** `d54db975e5cff73a2522598dfb1bc0727f45a523`  
**Verified manifest:** `docs/rewrite/RW-B01-Template-Manifest-v0.1.md`  
**Manifest commit:** `d08dc613459ba39bdae6b54bb7a4dcd3b872e169`  
**Verification date:** 2026-09-12

## Verdict

`RW-B01` is VERIFIED.

The manifest closes the consumer-project template surface before implementation. It is consistent with verified `RW-C03` and does not broaden bootstrap responsibility.

The complete managed consumer file set is exactly:

```text
.sdlc/project.yaml
.sdlc/project-context.md
AGENTS.md
.claude/CLAUDE.md
```

Optional managed files are explicitly none.

## Acceptance criteria

### AC1 — every template path is explicitly listed

PASS.

The manifest declares a closed four-path managed set and explicitly states that no other path belongs to the reusable consumer template in this rewrite.

### AC2 — overwrite/merge/skip behavior is explicit per path

PASS.

- `.sdlc/project.yaml`: generated under the B03 descriptor contract, compatible reuse only, never merge/overwrite.
- `.sdlc/project-context.md`: exact supplied context bytes, byte-identical reuse only, never merge/overwrite.
- `AGENTS.md`: create/append/reuse one exact delimited SDLC block; foreign content preserved; malformed/different managed block is conflict.
- `.claude/CLAUDE.md`: identical managed-block policy.

Managed parents are preflighted, symlink traversal through managed paths is a conflict, and unsafe local state is refused before Fibery bootstrap mutation.

### AC3 — no secret or user-global setting is included

PASS.

The manifest explicitly excludes `.env*`, tokens/credentials, project-local runtime/model/auth configuration, `.codex/config.toml` and `.claude/settings.json`. The agent-guidance block expressly preserves user-global model/provider/authentication/approval/permission/sandbox/edit-policy configuration.

### AC4 — implementation cannot invent another file

PASS.

The manifest is closed, optional files are none, and responsibility is split explicitly across B02/B03/B04. Adding another managed consumer path, placeholder or merge rule requires a reviewed B01 change.

## Important design dispositions

### No project-scoped runtime override files

The template deliberately does not materialize `.codex/config.toml` or `.claude/settings.json`. Absence is the strongest way to preserve trusted global runtime/auth/permission settings.

### No skills/agent bundle at bootstrap

`.agents/`, `.claude/agents/`, `.agents/skills/` and `.claude/skills/` are excluded. Generic bootstrap establishes SDLC participation; later explicitly designed execution capabilities may add repository-local agent assets if their own contracts require them.

### Context placement

The exported context is materialized at:

```text
.sdlc/project-context.md
```

This keeps project participation artifacts together and keeps repository root application-owned. The context remains explicitly non-canonical.

### RAW source is not copied locally

The initial RAW requirements artifact is consumed by the existing deterministic requirement-add primitive. A second repository copy would create unnecessary ambiguity about Requirement authority, so it is not a template artifact.

## Dependency disposition

This verification satisfies the `RW-B02` and `RW-B03` dependency gate on `RW-B01`.

`RW-B02` may implement only the static reusable agent-guidance template contract. `RW-B03` owns the exact descriptor schema. `RW-B04` later owns filesystem materialization and bootstrap composition.