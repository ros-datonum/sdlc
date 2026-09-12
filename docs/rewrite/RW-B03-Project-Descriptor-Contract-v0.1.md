# RW-B03 — Project Descriptor Contract v0.1

**Status:** FROZEN  
**Work item:** `RW-B03 — Implement project descriptor contract`  
**Owner of this freeze:** Human + independent design reviewer  
**Implementation actor:** RW-B03 implementation agent  
**Derived from:** verified `RW-C03`, verified `RW-B01`, verified `RW-B02`  
**Semantic change to RW-C03:** NONE  
**Date:** 2026-09-12

## 1. Purpose

This document freezes the exact schema, optionality, invariants and canonical serialization of:

```text
.sdlc/project.yaml
```

The descriptor tells SDLC tools how the consumer repository participates in SDLC. It is project identity/configuration, not product Requirement storage and not a second lifecycle source of truth.

Fibery remains authoritative for product Requirements and lifecycle State. Trusted runtime/workspace configuration remains outside this file.

---

## 2. Exact schema

Schema version 1 contains exactly these top-level keys:

```text
version
project
fibery
repository
checks
standards
```

Unknown top-level or nested keys are invalid.

The semantic structure is:

```yaml
version: 1
project:
  name: <required project name>
  code: <required resolved Project Code>
fibery:
  project_code: <required; exactly equal to project.code>
repository:
  root: "."
  branch_policy: <null or policy identifier>
  worktree_policy: <null or policy identifier>
  merge_policy: <null or policy identifier>
checks:
  - name: <unique check identifier>
    command: <non-empty deterministic command string>
standards:
  profile: <null or profile identifier>
  extensions:
    - <unique extension identifier>
```

All six top-level groups/keys are mandatory, including empty/null groups.

---

## 3. Project identity

### `version`

Required integer, exactly:

```text
1
```

No implicit version and no forward-version guessing.

### `project.name`

Required UTF-8 string.

Validation/normalization is exactly the current `project init` name boundary relevant here:

- trim leading/trailing Unicode whitespace;
- resulting value must be non-empty;
- canonical rendering uses the trimmed value.

The descriptor does not invent an alternate project-name normalization scheme.

### `project.code`

Required resolved Project Code.

It must pass the existing `sdlc.project_code.validate_project_code` contract.

B03 does not resolve Fibery uniqueness. The descriptor receives the code after the bootstrap composition has resolved the final code under the existing Project Init identity rules.

The code is stable project identity and is not changed by descriptor parsing/rendering.

---

## 4. Fibery mapping

The only project-local Fibery mapping in descriptor v1 is:

```text
fibery.project_code
```

It is required and must equal `project.code` exactly after Project Code normalization.

Rationale:

- Project Code is globally unique under the existing inner Project contract and is sufficient to map this repository to its Fibery Project in the configured workspace;
- Fibery host, token, Space name and Space id are runtime/workspace configuration, not consumer-project identity;
- storing those values here would create account/environment coupling and could conflict with trusted runtime configuration.

Descriptor v1 therefore contains no:

```text
fibery host
Fibery token
Space id
Space name
Project entity UUID
Requirement ids/prose/state
```

A caller resolves the configured workspace independently and validates that the Project Code maps to the intended Project there.

---

## 5. Repository group

Required keys:

```text
root
branch_policy
worktree_policy
merge_policy
```

### `repository.root`

Required literal:

```text
.
```

The descriptor is repository-relative and portable. Absolute local paths are invalid.

### Policy identifiers

Each of:

```text
repository.branch_policy
repository.worktree_policy
repository.merge_policy
```

is either:

```text
null
```

or one non-empty policy identifier.

A policy identifier is metadata only in this rewrite. B03/B04 do not execute or interpret branch/worktree/merge behavior from it.

Syntax when non-null:

```text
[A-Za-z][A-Za-z0-9._-]{0,63}
```

`null` means:

> no project-specific policy is declared here; this descriptor does not override a higher-precedence explicit human/tool policy.

The bootstrap-generated v1 descriptor uses `null` for all three policies because the frozen bootstrap CLI has no project-policy inputs.

This preserves the group for later explicitly approved delivery behavior without inventing that behavior in Block D.

---

## 6. Deterministic project checks

`checks` is a required ordered list, possibly empty.

Each item has exactly:

```text
name
command
```

### `checks[].name`

Required unique identifier matching:

```text
[A-Za-z][A-Za-z0-9._-]{0,63}
```

Duplicate names are invalid.

### `checks[].command`

Required non-empty UTF-8 string after trimming outer whitespace.

Rules:

- canonical value is the trimmed command;
- NUL is forbidden;
- CR/LF inside the command are forbidden: one descriptor item is one deterministic command;
- B03 validates/stores this metadata but executes nothing;
- a command may reference environment variables, but credentials/tokens must not be embedded as literal descriptor data.

The bootstrap-generated v1 descriptor uses:

```text
checks: []
```

because the frozen bootstrap CLI has no project-check inputs and bootstrap must not guess commands from repository contents.

---

## 7. Standards group

Required keys:

```text
profile
extensions
```

### `standards.profile`

Either `null` or a non-empty identifier matching:

```text
[A-Za-z][A-Za-z0-9._-]{0,63}
```

### `standards.extensions`

Required ordered list of zero or more unique identifiers using the same identifier syntax.

Duplicate extension identifiers are invalid.

B03 only represents these names. It does not implement a standards-profile registry or extension execution.

The bootstrap-generated v1 descriptor uses:

```text
profile: null
extensions: []
```

because the frozen bootstrap command has no standards-profile inputs.

---

## 8. Bootstrap-generated descriptor

Given only the frozen bootstrap identity inputs, after final Project Code resolution, the generated descriptor is semantically:

```yaml
version: 1
project:
  name: <trimmed --name>
  code: <resolved code>
fibery:
  project_code: <same resolved code>
repository:
  root: "."
  branch_policy: null
  worktree_policy: null
  merge_policy: null
checks: []
standards:
  profile: null
  extensions: []
```

`--description`, RAW Requirement content and project-context content are not descriptor fields.

No repository inspection is used to invent checks, policies, standards, branch names, remote URLs or technology choices.

---

## 9. Canonical serialization

The descriptor is UTF-8 text with LF line endings and one final LF.

Canonical key order is exactly the schema order shown below.

All non-null string scalar values are rendered as double-quoted JSON-compatible string literals. This provides deterministic escaping for quotes, backslashes, Unicode controls and project names without adding a YAML dependency.

Canonical empty bootstrap output shape:

```yaml
version: 1
project:
  name: "Example Project"
  code: "EXAMPL"
fibery:
  project_code: "EXAMPL"
repository:
  root: "."
  branch_policy: null
  worktree_policy: null
  merge_policy: null
checks: []
standards:
  profile: null
  extensions: []
```

When checks exist they render as:

```yaml
checks:
  - name: "test"
    command: "uv run pytest -q"
```

When standards extensions exist:

```yaml
standards:
  profile: "python"
  extensions:
    - "security"
    - "api"
```

List order is preserved. Canonical rendering never sorts user-supplied checks or extensions; uniqueness is validated.

---

## 10. Parsing boundary

B03 need not become a general YAML implementation.

It may implement the deterministic YAML subset defined by this contract only.

A descriptor is valid when it can be parsed into exactly this schema and satisfies all invariants. It must reject rather than guess when syntax/structure is outside the supported descriptor grammar.

Required rejection includes:

- missing mandatory keys/groups;
- unknown keys;
- duplicate keys;
- wrong scalar/list/object type;
- unsupported version;
- invalid/empty project identity;
- invalid Project Code;
- mismatched `fibery.project_code`;
- non-literal repository root;
- invalid policy/check/profile/extension identifiers;
- duplicate check names/extensions;
- empty/multiline/NUL check command;
- credentials or canonical Requirements represented through undeclared fields (unknown keys already fail closed).

The implementation must not silently drop unknown data.

---

## 11. Semantic compatibility for bootstrap rerun

B01 gives `.sdlc/project.yaml` whole-file ownership: never merge and never overwrite.

B03 defines `COMPATIBLE` semantically:

1. parse/validate the existing descriptor;
2. compare the complete parsed descriptor value with the descriptor requested by bootstrap;
3. if equal, it is compatible and B04 reuses the existing bytes unchanged;
4. if unequal or invalid, it is conflict.

Therefore formatting differences that the B03 parser explicitly accepts may still be compatible. B04 must not rewrite a compatible existing descriptor merely to canonicalize it.

For bootstrap-generated descriptors with unchanged inputs, `render(parse(render(value)))` must produce the same canonical bytes.

---

## 12. Precedence and non-authority

The descriptor does not override:

- explicit current human intent;
- canonical product Requirements in Fibery;
- Requirement lifecycle State in Fibery;
- trusted user-global model/provider/authentication configuration;
- higher-precedence approval/permission/sandbox/edit policy.

The descriptor contains no model/provider/authentication/approval/sandbox/edit keys.

Nullable repository policy identifiers are project metadata only and have no execution effect in this rewrite.

---

## 13. Forbidden content/schema

Descriptor v1 has no field for:

- product Requirement prose;
- RAW Requirement source content;
- Requirement lifecycle State;
- Requirement processing status;
- model/model provider;
- API/OAuth/token/password/secret;
- provider endpoint;
- approval/permission/sandbox/edit mode;
- local absolute repository path;
- Fibery account host/token/Space id;
- generated Architecture/Planning/Task content.

Unknown keys are invalid, preventing such fields from becoming a shadow configuration surface.

---

## 14. Implementation ownership

RW-B03 implements only the pure descriptor value/schema/parser/renderer/compatibility contract.

It does not:

- read/write `.sdlc/project.yaml` on disk;
- resolve target/symlink safety;
- resolve Project Code uniqueness from Fibery;
- invoke Project Init;
- invoke Requirement Add;
- copy project context;
- apply B02 agent guidance;
- execute checks;
- interpret repository/standards policies;
- implement `sdlc project bootstrap`.

Those composition/filesystem responsibilities remain RW-B04.

---

## 15. B03 acceptance interpretation

Frozen RW-B03 ACs are satisfied as follows:

1. **Missing mandatory identity/config is rejected:** parser/validation enforces every required group/key and invariant above.
2. **Descriptor can be generated for a new project from bootstrap inputs:** after B04 resolves the final Project Code through existing Project Init semantics, B03 constructs the default descriptor from Project Name + Project Code; all other bootstrap-generated values are frozen defaults.
3. **Rerun is semantically stable:** generation is deterministic and canonical rendering round-trips stably; an equal existing parsed descriptor is compatible and reused unchanged.
4. **No credentials/canonical Requirements:** the schema contains no such fields, unknown keys fail closed, and default generation accepts no such input.
