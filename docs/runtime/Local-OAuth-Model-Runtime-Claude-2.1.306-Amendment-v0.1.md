# Local OAuth Model Runtime — Claude Code 2.1.306 Amendment v0.1

**Status:** IMPLEMENTED ON BRANCH `impl/runtime-claude-2-1-306-qualification`. Offline-verified.
- **Live requalification:** passed on 2026-10-22 (§11), for the exact build in §2, after the `@`-mention disclosure fix (§7).
- **Independent security review:** pending on the committed candidate.
- **The pre-fix runtime is not qualified.**
**Amends:** `Local-OAuth-Model-Runtime-Spec-v0.1.md` §3 (Claude runtime) and §8 (what the boundary is), for the Claude family only. Where they disagree, this amendment governs. Codex stays blocked, unchanged.
**Evidence:** `pilots/ARP1/diagnostics/` holds the plugin source extracted from the installed binary, the canaries, the boundary classification and the independent review notes.

## 1. Why

On Claude Code 2.1.306 the restricted reasoning child still loads built-in plugins, and their hooks run under `--safe-mode`. The CLI help says so too: built-in tools and plugins "work normally". The 2.1.260 record (`plugins: []`, "safe mode disables plugins and hooks") no longer holds. This amendment replaces that invariant with a version-bound contract that is checked on every call.

## 2. Executable identity

### 2.1 The dedicated alias

`executable = "sdlc-claude-2.1.306"`: a machine-local symlink set up once by the operator, outside the repository, in a PATH directory:

```
ln -s <claude versions dir>/2.1.306 <a PATH dir>/sdlc-claude-2.1.306
```

- It never replaces the interactive `claude`, which the auto-updater repoints.
- A missing alias refuses every call ("not on PATH"); nothing falls back to `claude`.
- An alias naming any other file, or a target that has been removed, is refused at identity.

### 2.2 Identity checks

- `config/sdlc.toml` `[model_runtime.runtimes.claude.qualified_binary]` names the one qualified build:
  - `sha256`: the SHA-256 of the executable file;
  - `version`;
  - `builtin_plugins`;
  - `protocol_capabilities`.
  The table is operator-controlled and holds no home-directory path.
- On every call the runtime resolves `executable` (symlinks followed), hashes the file, and refuses with `RUNTIME_ISOLATION_UNAVAILABLE`, before any process starts, unless it is the qualified build.
- The resolved file, never the symlink, runs both the login check and the inference. A symlink repointed afterwards changes nothing.
- Any other build, an auto-updated one included, needs its own qualification. The version string is never trusted alone.
- `claude auth status` as a standalone diagnostic still reports the login, and reports an unqualified build as "authenticated but not eligible".
- **Residual:** the file could be replaced in place between the hash and the exec. A compare-and-exec binding is not available.

## 3. Fixed child environment

The Claude child gets three values: `DISABLE_TELEMETRY=1`, `CLAUDE_CODE_DISABLE_ATTACHMENTS=1` and `CLAUDE_CODE_DISABLE_FILE_MENTIONS=1`. They are:
- code constants, set last, after the allowlist;
- never copied from the parent;
- never overridden by a parent value;
- refused if named for passthrough, in configuration or in code.

They apply only to the spawned child: the interactive CLI and global settings are untouched. The allowlist is otherwise unchanged. The two attachment switches are covered in §7. On 2.1.306 `DISABLE_TELEMETRY`:
- sets `analytics_disabled` (`Vy()`);
- keeps the built-in telemetry plugin unregistered, because its availability is `!Vy()`, so its probe (`sh -c uname/command -v`, a working-directory listing, `~/.claude.json` IDs) never runs;
- turns off the core first-party event logger.

Observed live:
- **every qualifying call:** the telemetry plugin was absent from init, and `analytics_disabled` was `true`;
- **2026-10-21, under a diagnostic debug log:** no telemetry send line and no `event_logging`.

The final calls ran the exact production argv, without a debug log, so transmission suppression in them rests on that earlier run and on the code.

## 4. Session validation (`claude_session.py`)

The child runs `claude -p <restrictions> --output-format stream-json --verbose`. The restrictions are unchanged from §3 of v0.1, and stdin carries the prompt as plain text; `--input-format` is never passed. Stdout is validated line by line as it arrives, and the child is killed at the first violation. The complete stdout is then validated again, and that check is authoritative. Only the final answer text is returned. `ModelRuntime.run` and `ModelResponse` are unchanged, so Process and Review never see event records.

### 4.1 The init record

There must be exactly one init record, before any assistant or result event, and:
- **binding:** `cwd` is this call's temporary directory, and `claude_code_version` is the qualified version;
- **must be empty:** `tools`, `mcp_servers`, `skills`, `slash_commands`;
- **must be absent or empty:** `memory_paths`, `additional_directories`, `plugin_errors`, `plugin_warnings`, `mcp_server_errors`, `terminal_slash_commands`;
- **must equal exact values:** `apiKeySource` = `none`, and `analytics_disabled` = `true`;
- **`plugins`:** exactly the qualified set, each with `path: builtin` and `source: <name>@builtin`, and no duplicates;
- **`capabilities`:** exactly the qualified set (§6), as a list of distinct strings.

`agents` may list registered agent types: with `tools: []` there is no Agent tool to call them.

### 4.2 The stream

- **Events:** a closed allowlist: `system/init`, `system/thinking_tokens`, `system/api_retry`, `system/status`, `system/turn_duration`, `assistant`, `rate_limit_event`, and one final `result`.
- **Refused:** everything else, including `user` (tool results, attachments), `stream_event`, `control_request`/`control_response`, and the hook, memory, attachment, permission, task, tool-host, model-fallback and command subtypes.
- **Assistant content:** `text`, `thinking` or `redacted_thinking` only. Any `*tool_use` gives `TOOL_USE_ATTEMPTED`.
- **Binding:** every event carrying a `session_id` must carry init's.
- **The result:** must be `subtype: success`, `is_error: false`, with non-empty text, and must be last.
- **Refusals:** raise `ModelSessionRejected` with a fixed code. The message names at most field names and identifier-shaped plugin or capability names, never the prompt, the answer, a file or a secret.

## 5. Built-in plugins on 2.1.306, under these controls

| Plugin | Status | What it can do here |
|---|---|---|
| `cc-plugin-agents-md` | registered; hooks run | Its `prompt.context` hook would add `AGENTS.md` / `.claude/AGENTS.md` from the working directory's ancestors, but the CLI's own `fs.ancestors` refuses ("project memory is off") when instruction files are disabled (`--safe-mode`) or project settings are ignored (`--restricted`). Observed live: 6 refusals in the debug log, and no planted marker reached the model. |
| `cc-plugin-plugin-authoring` | registered; inert | Its only tool (`scan_secrets`) is registered inside its own `skill.prompt` hook, which needs a skill invocation; `skills: []`, slash commands are disabled, and there is no Skill tool. |
| `cc-plugin-telemetry` | **not registered** | Its availability is `!Vy()`, and §3 makes `Vy()` true. Its presence would be refused. |
| any other plugin | refused | Plugin availability is set partly by remote feature flags and account tier, so the exact set is checked on every call. |

**Pre-validation execution (not prevented):** built-in plugins load, and their `session.start` hooks run, before the init line exists. Validation refuses the answer and kills the child, but cannot undo what a hook already did. The fixed environment values (§3) are the controls that act before execution.

## 6. SDK control-protocol capabilities

`init.capabilities` lists the SDK control-protocol features the CLI would honour from a host that drives it with `--input-format stream-json`. They are protocol support, not model tools:

| Capability | Meaning |
|---|---|
| `interrupt_receipt_v1`, `interrupt_cancel_queued_v1`, `interrupt_send_now_v1` | host interrupt and queue control |
| `msg_lifecycle_v1`, `request_marker_lists_v1` | message-lifecycle and marker protocol |
| `sdk_mcp_tools_list_changed`, `sdk_mcp_manifests` | host-registered in-process SDK MCP servers (remote flag `tengu_sdk_mcp_manifests`) |
| `mcp_read_resource_v1` | host-requested read of a resource from a connected MCP server |
| `mcp_tool_ui_meta_v1`, `mcp_call_result_not_for_model_v1` | MCP result and UI metadata conventions |
| `ui_surface_v1` | host UI-surface protocol |

**Why none of them can be exercised here:**
- SDLC never passes `--input-format`, and writes the prompt as plain text, so no control channel exists.
- There is no MCP server (`mcp_servers: []`) and no tool.
- A `control_request`/`control_response` event in the stream is refused.

The exact set of these 11 is required. A remote flag or a new build that changes it is refused until it is requalified.

## 7. Instruction files and `@path`

### 7.1 The disclosure (2026-10-22)

A print-mode stdin prompt **does** raise `@` mentions on 2.1.306:
- Content of `inside-secret.txt`, referenced only as `@inside-secret.txt` / `@./inside-secret.txt`, reached the model with no tool and no stream event.
- `CLAUDE.md` / `CLAUDE.local.md` content also reached it. They were referenced as `@CLAUDE.md` too, so that call could not separate mention expansion from instruction-file loading.
- An absolute path outside the working directory was not attached.
- Session validation cannot see this, because the stream has no attachment event.

So untrusted Fibery text could pull local file content into the model's context. That runtime is not qualified.

### 7.2 Root cause

In the installed binary, the per-input attachment builder:
- extracts `@` references from the input text (`XDr`/`wTn`: `@name`, `@./x`, `@/abs`, `@../x`, `@~/x`, quoted `@"…"`, as path strings);
- builds `at_mentioned_files` from them, reading each file through `vDr`;
- also builds `mcp_resources` and `agent_mentions`.

None of this is restricted by `--safe-mode`, `--restricted` or `--tools ""`. Mentions are read by the engine, not through a tool.

### 7.3 Fix: fixed switches, input unchanged

- **`CLAUDE_CODE_DISABLE_ATTACHMENTS=1`:** the builder's guard `QXe` (`DISABLE_ATTACHMENTS || SIMPLE || bareFork`) returns **before** any mention is extracted, and before `at_mentioned_files`, `mcp_resources` or `agent_mentions` are built. This covers every reference form, including symlinks and directories, because all of them reach the reader only after that return. It also turns off agents-md's nested Read and mention path (its `Te()` check).
- **`CLAUDE_CODE_DISABLE_FILE_MENTIONS=1`:** defence in depth. Should the reader be reached, it uses `kDr` in place of `vDr`. `kDr` gives a path reference instead of a fresh read, but still attaches content that is already in the session's upload cache. That cache is empty for an SDLC child. On its own it is therefore not the boundary.
- **No input change:** the requirement and prompt text are passed byte for byte (tests cover emails and every `@` form). Nothing is escaped or sanitized.
- **Side effect:** `DISABLE_ATTACHMENTS` also drops other engine-added context (token-count reminders, MCP instructions, deferred-tool notes). None of it is SDLC input.

### 7.4 Live evidence (2026-10-22, two calls, the production configuration)

- **Planted for each call**, with unguessable markers:
  - `@inside-secret.txt`, `@./inside-secret.txt`, `@<absolute outside file>`, `@../<file in the parent directory>`, `@~/<file in HOME>`;
  - a symlink in the working directory pointing outside it;
  - `@subdir` and `@subdir/dir-secret.txt`.
- **Per call:**
  - call 1 added `AGENTS.md` and `.claude/AGENTS.md`, with no `CLAUDE.md`;
  - call 2 added `CLAUDE.md` and `CLAUDE.local.md`, each also referenced by `@`;
  - both carried an ordinary email address, and synthetic secrets in the parent environment, including parent values of `0` for all three switches.
- **Result:** no marker appeared anywhere in stdout. The model echoed the references and the email address literally. Init was exact, there was no tool use, no write and no session, and the answer was complete.
- **Limitation:** the absence is shown by the model's output and the code path, not by an engine-internal trace. A non-quoted marker alone would not prove the path disabled; here it is corroborated by the code (§7.3) and by the 2026-10-22 failure's reversal under the same probes.

### 7.5 Instruction files

- **`CLAUDE.md`, `CLAUDE.local.md`:** not loaded under `--safe-mode` (`gA()`). Observed: not reaching the model in call 2.
- **`AGENTS.md`:** §5. Observed: not reaching the model in call 1.
- **Runtime:** SDLC passes untrusted text only as literal stdin, with no `--add-dir`. Any `user`/attachment-class event is refused.

## 8. Model and authentication

- Unchanged: claude.ai login on the first-party API, checked before each call, and `apiKeySource: none` in init.
- The model is the CLI default (observed: `claude-opus-5-5`); no model flag is set.

## 9. Upgrades

A new build fails closed at identity (§2). Qualifying it means:
1. inspecting its built-in plugins and protocol capabilities;
2. a canary;
3. a new `qualified_binary` entry, with independent review.

`claude` resolving to an unqualified build stops all Claude model calls until then.

## 10. Fail-closed summary

| Condition | Result |
|---|---|
| No qualified build configured | `RUNTIME_ISOLATION_UNAVAILABLE` before any process |
| Build hash differs | `RUNTIME_ISOLATION_UNAVAILABLE` before any process |
| Init missing, duplicated, malformed, or any field deviating | `ModelSessionRejected`; child killed; nothing returned |
| An event outside the closed schema, or a tool use | `ModelSessionRejected`; child killed; nothing returned |
| No successful, non-empty result | `ModelSessionRejected`; nothing returned |
| Timeout or non-zero exit | `ModelRuntimeError`, as before |

## 11. Live requalification record

| Date (UTC) | Calls | Result |
|---|---|---|
| 2026-10-21 | 2 | Both refused at init: `capabilities` was then required to be absent. Corrected (§6). |
| 2026-10-22 | 1 of 2 | Production validation accepted the session. The instrument crashed before recording evidence; the call is inconclusive. The second call was not run. |
| 2026-10-22 | 1 (one-call mode, alias `sdlc-claude-2.1.306`) | Session accepted: exact plugins and capabilities, OAuth, telemetry disabled, a correct `ModelResponse`, no tool use, no secret or outside-file disclosure, no write, no session. **Failed:** working-directory file content reached the model through `@relative` references (and/or `CLAUDE.md` loading). Stopped. |
| 2026-10-22 | 2 (after the §7.3 fix, production configuration) | **Passed:** both calls accepted, with no marker disclosed for any reference form, instruction file or secret; references and the email echoed literally; init exact; one turn; no tool, write or session. Evidence: `mention-requal-canary-2026-10-22T092157+0000.json`. |

## 12. Limitations

- Built-in plugin hooks run before init can be inspected; validation detects deviations but cannot undo earlier side effects.
- The hash check leaves a narrow file-replacement window before exec.
- Remote feature flags can change the plugin or capability set. That is refused, not prevented.
- The `@`-mention protection rests on an engine switch of this build; a new build must be requalified (§9) with the §7.4 probes.
- `DISABLE_FILE_MENTIONS` alone would not prevent content from the session upload cache (§7.3).
- The final calls did not observe outbound telemetry directly (§3).
- The qualification covers this exact build and the environment observed, and nothing else.
