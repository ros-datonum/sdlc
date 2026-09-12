# RW-B05 — Live Bootstrap E2E Implementation Boundary v0.1

**Status:** FROZEN  
**Work item:** `RW-B05 — Bootstrap end-to-end test on disposable project`  
**Depends on:** independently verified `RW-B04`  
**Semantic change to RW-C03/B01–B04:** NONE  
**Date:** 2026-09-12

## 1. Purpose

RW-B05 is the live acceptance gate for the already-implemented outer bootstrap. It proves the normal user-facing command against:

- the real CLI and configuration loader;
- a real temporary consumer-project directory;
- the configured live Fibery workspace;
- one disposable Fibery Project and one disposable initial RAW Requirement.

RW-B05 is verification, not another bootstrap implementation item.

On the green path it changes no production code.

If live evidence exposes a B04 or adapter defect, RW-B05 stops and reports the owning defect. It must not silently patch production code inside the E2E gate.

## 2. Normal command under test

The normal action under test is exactly:

```bash
sdlc project bootstrap \
  --name <disposable-name> \
  --requirements <raw-export.md> \
  --context <project-context.md> \
  --target <temporary-consumer-directory> \
  [--code <disposable-code>]
```

The first live run must go through the real CLI handler. Calling `bootstrap_project()` directly is useful for diagnostics only and does not satisfy the main success-path proof.

No model/runtime override flag exists or is added.

## 3. Disposable identity

Use a clearly disposable Project identity that cannot be confused with production data, for example:

```text
Project Name: ZZ RW-B05 Bootstrap Probe <timestamp-or-short-suffix>
Project Code: explicit unique short code conforming to the existing Project Code contract
```

Prefer an explicit code for the live probe so the evidence is easy to identify and cleanup is unambiguous. Code-generation behavior is already covered by B04 deterministic tests.

Before first mutation, prove read-only that neither the disposable exact Project Name nor disposable Project Code currently exists.

If either already exists, choose a new disposable identity rather than deleting unknown pre-existing data.

## 4. Export inputs

Use temporary synthetic artifacts that satisfy the currently supported requirements-export transport contract.

The RAW artifact must be valid for the existing `parse_raw_requirement` contract and contain clearly disposable probe content only.

The project context must be non-secret, synthetic bytes. Include one distinctive benign line so exact-byte materialization can be verified.

Do not use production Requirements or project context.

B05 does not test semantic Requirement decomposition and does not run RAW processing.

## 5. Local target

Use an OS temporary directory outside the `sdlc` repository as the consumer target.

The target may start as an empty existing directory or as an absent final directory with a real existing parent. The primary live journey should use one deterministic choice and record it.

Before bootstrap, capture:

- target path;
- whether it existed;
- complete target tree (expected empty for the primary journey).

After bootstrap, the managed local artifact set must be exactly:

```text
.sdlc/project.yaml
.sdlc/project-context.md
AGENTS.md
.claude/CLAUDE.md
```

plus their parent directories.

No raw-export copy is expected in the target.

## 6. User/global runtime configuration safety

Bootstrap must not modify user-global Claude/Codex configuration.

For common existing user-global files, when present, capture only safe metadata before and after:

- existence;
- SHA-256 digest;
- optionally size/mtime.

Do not print their contents.

At minimum consider the actual user-global configuration files used on the host for Claude/Codex. If their paths are not safely discoverable, record that the stronger hash check was unavailable and rely on target-tree evidence plus production-code ownership.

Inside the consumer target, explicitly prove bootstrap did not create:

```text
.codex/config.toml
.claude/settings.json
.agents/
.claude/agents/
.claude/skills/
.agents/skills/
.env
```

If `FIBERY_TOKEN` is available to the verification process, it may be checked for absence from managed project bytes without ever printing the token itself.

## 7. Runtime configuration preflight

The real CLI requires a complete supported Fibery configuration.

Before live mutation, validate that the process has the required configuration, including `FIBERY_SPACE_ID`.

If the user's persistent `.env` still lacks `FIBERY_SPACE_ID`, B05 may discover the configured SDLC Space id read-only and inject it **only into the verification process environment** for the CLI invocation.

It must not edit `.env` or user-global runtime configuration as part of B05.

Record whether persistent configuration was complete or whether a process-scoped value was used.

This distinction is operational evidence, not a bootstrap product change.

## 8. First live bootstrap

Run the real CLI once.

Expected:

```text
exit code 0
PROJECT_BOOTSTRAPPED
```

Capture the bounded CLI output only. Do not log tokens or API payloads.

After success verify locally:

1. exactly the four managed files exist;
2. `.sdlc/project.yaml` parses under the real B03 parser;
3. descriptor Project Name/Code equal the disposable identity;
4. `fibery.project_code == project.code`;
5. `.sdlc/project-context.md` is byte-identical to the supplied context;
6. AGENTS.md and `.claude/CLAUDE.md` classify B02 `COMPATIBLE`;
7. no excluded runtime/auth/skills file exists;
8. no credential value was written into managed files.

Verify in live Fibery:

1. exactly one Project carries the exact disposable Name;
2. exactly one Project carries the disposable Code;
3. Name and Code resolve to the same entity;
4. exactly one Requirement in that Project carries the supplied RAW source fingerprint;
5. Requirement Type is `Raw`;
6. Requirement State is `Draft`;
7. Requirement belongs to the disposable Project;
8. Root Document exists under the Requirement according to the existing Requirement Add contract;
9. stored Root content is equivalent to the supplied RAW source under the existing `content_equivalent` rule.

## 9. No automatic Requirement processing

Bootstrap itself stops at Raw + Draft.

After the first success, observe the disposable RAW for a bounded period long enough to catch any ordinary state-driven reaction (for example 10–15 seconds):

- State remains Draft;
- no RAW Processing Result appears;
- no Standard Requirement is derived/produced from this RAW;
- bootstrap did not move it to Process.

Do not perform `Draft -> Process` in B05.

Do not run a manual RAW processor command.

A separately running normal worker is harmless because Raw Draft is a human boundary; B05 must nevertheless record whether a runner was known to be active.

## 10. Live rerun

Run the **same real CLI command** again with the same name, code, requirements, context and target.

Expected:

```text
exit code 0
PROJECT_ALREADY_BOOTSTRAPPED
```

Prove the rerun is non-destructive:

- all four managed file bytes are unchanged;
- user/global config hashes, when captured, are unchanged;
- exactly one Project still exists for Name/Code;
- exactly one matching RAW still exists;
- Requirement id is unchanged;
- no second Root Document/canonical RAW is created;
- RAW remains Draft;
- no processing begins.

## 11. Safe live failure probe

RW-B05 AC8 requires a truthful failure/error outcome. Use a failure that does not intentionally create partial Fibery state.

Preferred probe:

1. create a separate temporary target containing a conflicting `.sdlc/project-context.md` or conflicting descriptor;
2. invoke the real bootstrap CLI with the same disposable identity and inputs;
3. expect non-zero exit and `BOOTSTRAP_CONFLICT`;
4. prove the conflicting local file is unchanged;
5. prove live Fibery Project/RAW counts are unchanged from before the failure probe.

An invalid-RAW preflight failure is also acceptable, but a local conflict is preferred because it exercises the B01/B03 conflict surface through the real CLI.

Do not deliberately inject a live Fibery partial-write failure merely to satisfy AC8.

## 12. Live query evidence

Use read-only queries through the existing authenticated Fibery client/workspace or an already-connected Fibery tool.

For exact-once claims, do not rely only on a helper that returns the first match. Use bounded queries/counts sufficient to distinguish:

```text
0
1
>1
```

for Project Name, Project Code and initial RAW fingerprint in the disposable Project.

Do not print unrelated workspace data.

## 13. Cleanup

After all success/rerun/failure evidence is captured:

1. delete only the exact disposable RAW Requirement created by B05;
2. delete only the exact disposable Project created by B05;
3. verify both no longer resolve by id/name/code/fingerprint as applicable;
4. remove the temporary consumer target(s).

Never delete an entity merely because its name resembles the probe identity. Cleanup must use the ids recorded from this B05 run.

If cleanup fails, report it explicitly and stop; do not broaden deletion criteria.

Cleanup is verification hygiene, not bootstrap rollback semantics.

## 14. Repository artifact

On a fully passing green path, no production code or test code change is expected.

Record the live evidence in exactly one new repository document:

```text
docs/rewrite/RW-B05-Live-Bootstrap-Evidence-v0.1.md
```

The evidence document may include:

- date/time;
- disposable Project Name/Code;
- temporary target basename/path in sanitized form;
- CLI result codes;
- resulting Requirement ID/public id if non-sensitive;
- local managed path/digest evidence;
- exact-once counts;
- Raw + Draft/no-processing observations;
- rerun evidence;
- safe failure-probe evidence;
- cleanup confirmation;
- whether process-scoped `FIBERY_SPACE_ID` was needed;
- test/gate results.

It must not include:

- Fibery token;
- document secrets;
- user-global config contents;
- production project data;
- RAW/context bodies beyond short synthetic probe labels.

The moving plan may then record RW-B05 implementation evidence/status in the allowed implementation fields.

## 15. Production defect handling

If the live probe exposes a mismatch in B04 or the existing adapters:

- do not patch production code inside the green-path B05 evidence commit;
- capture the safe failing observation;
- identify the owning work item;
- raise a Proposed Change Request if required by the frozen plan;
- set B05 `BLOCKED` when the acceptance gate cannot truthfully pass.

A later explicitly authorized correction may then be made in the owning item.

## 16. Required repository gates

Before final B05 evidence is committed, rerun at least:

```bash
uv run pytest -q tests/test_project_bootstrap.py tests/test_cli_bootstrap.py
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

No live-model test is required.

## 17. Acceptance mapping

The live probe must provide direct evidence for frozen AC1–AC9:

1. one setup action creates usable local project structure;
2. descriptor/context match frozen contract;
3. Fibery Project exists exactly once;
4. initial RAW exists exactly once;
5. rerun is safe;
6. global/user model/auth/edit settings are not overwritten;
7. no credentials are written to project files;
8. failure produces a truthful partial/error result;
9. no Requirement processing starts without the authorizing lifecycle State.

## 18. Explicit non-goals

RW-B05 does not:

- run requirements-export itself;
- run RAW/Standard processing;
- validate live-model Requirement quality;
- test worker processing after Draft -> Process;
- change Processing Status automation;
- change B01/B02/B03/B04 semantics;
- test project-code generation (use an explicit disposable code);
- test destructive recovery/rollback;
- create persistent user/global runtime configuration.
