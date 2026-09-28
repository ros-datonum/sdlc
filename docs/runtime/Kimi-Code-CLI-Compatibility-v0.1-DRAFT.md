# Kimi Code CLI Compatibility v0.1 — DRAFT

**Status:** Bounded compatibility spike. Not an implementation, not a support
declaration, not an approved specification. Nothing in `src/`, `config/` or the
runtime contract was changed.

**Question:** can `kimi` execute SDLC reasoning roles (RAW Process, Standard
Process, Standard Review) under
`docs/runtime/Local-OAuth-Model-Runtime-Spec-v0.1.md` without weakening it?

**Short answer:** no, on either surface, in **both reviewed versions** (0.33.0
and 2.1.1 — see the delta section), and the reason is the same one on
both surfaces: neither exposes a way to bind a restricted agent to a run. Two
surfaces were examined — print mode (`kimi -p`) and native ACP (`kimi acp`).
Print mode can empty the tool set but cannot suppress MCP, hooks or plugins,
and delivers the prompt only through argv. Native ACP delivers the prompt
properly over stdio but has **no tool or profile surface at all**, and
withholding client capabilities makes execution local rather than absent.

The execution-boundary blocker (B3) is therefore structural, not a property of
any particular machine's configuration. It is the one to resolve first; until
it is, the authentication and transport questions are moot and were
deliberately left unfinished (see `Auth and transport: not investigated`).

## Subject under review

```text
installed executable   /Users/ros/.kimi-code/bin/kimi      (reported by the user)
installed version      0.33.0                              (reported by the user)
upstream repository    MoonshotAI/kimi-code                (public)
upstream tag           @moonshot-ai/kimi-code@0.33.0
upstream commit        53c832dfdf9566afd59a8b3d54ebd36d3cb03d72
```

The tag object `4e43d6fb5ddd2e774e2fd7a006906a5bd41715c2` resolves to that
commit, and `apps/kimi-code/package.json:3` at that commit reads
`"version": "0.33.0"`, so the reviewed tree is the installed build's source.

The installed binary was never executed for this review. No inference, no
login, no upgrade, no Fibery, no worker. Every claim below is either read from
that tree (`CONFIRMED_IN_SOURCE`) or explicitly marked as unverified.

Default engine: `apps/kimi-code/src/cli/experimental-v2.ts:31-35` —
`isKimiV2Enabled` is `!isLegacyEnabled`, so **agent-core-v2 is the default**
and `KIMI_CODE_LEGACY_FLAG` selects the legacy engine. Both entry points
follow it: `runPrompt` dispatches to the v2 runner before any v1 code runs
(`apps/kimi-code/src/cli/run-prompt.ts:103-110`), and `registerAcpCommand`
delegates to the native ACP command and returns before the legacy adapter body
is reached (`apps/kimi-code/src/cli/sub/acp.ts:40-44`). Only the v2 / native
paths are analysed here; `@moonshot-ai/acp-adapter` is the legacy host and is
out of scope.

**Two surfaces, analysed separately.** `C1`–`C13` cover print mode. `A1`–`A8`
cover native ACP. Where a finding is engine-level rather than surface-level it
is stated once and referenced.

---

## Delta review — Kimi Code CLI 2.1.1 (execution boundary only)

Bounded re-check of the recorded blockers after the user upgraded. **Source
review at a pinned commit, not live certification**: the installed binary was
not run, and nothing below is evidence about the user's machine.

```text
previous   0.33.0   53c832dfdf9566afd59a8b3d54ebd36d3cb03d72
current    2.1.1    f67e6398fb3210ad8ace970e2dfd5bcc984ed61f
```

Tag `@moonshot-ai/kimi-code@2.1.1` → `a00639d0…` → that commit;
`apps/kimi-code/package.json:3` there reads `"version": "2.1.1"`.

**Successors located, as required.** `acp-native.ts` and `experimental-v2.ts`
no longer exist: the legacy/v2 fork is gone and `apps/kimi-code/src/cli/sub/acp.ts`
is now the single ACP entry point (the former `acp-native.ts` body). Hooks moved
to `packages/agent-core-v2/src/features/externalHooks/` under a new `Feature`
registry. Neither move introduced a control.

### Prior blockers

| # | Blocker | 2.1.1 |
|---|---|---|
| B3-print | `-p`: tools removable, MCP/hooks/plugins not | **STILL_PRESENT** |
| B3-acp | ACP: no tool/profile surface at all | **STILL_PRESENT** |
| A3 | `mcpServers: []` suppresses nothing | **STILL_PRESENT** |
| A4 | `session/new` spawns MCP + runs SessionStart hooks | **STILL_PRESENT** |
| A5 | plugins load at App scope before `initialize` | **STILL_PRESENT** |
| A6 | capability withheld → local execution | **STILL_PRESENT** |
| C7 | `KIMI_CODE_HOME` moves config *and* credentials | **STILL_PRESENT** |
| B1 | no positive OAuth / route evidence | **NOT_RECHECKED** (gated) |
| B2 | `-p` prompt in argv | **NOT_RECHECKED** (gated) |
| C9 | session persistence | **NOT_RECHECKED** (gated) |
| C10/C12/C13 | stream framing, update check, env surface | **NOT_RECHECKED** (gated) |

Nothing moved to `RESOLVED_IN_SOURCE`.

### Shortest sufficient evidence (all at `f67e6398`)

**`kimi acp` — no isolation input exists.**

```text
apps/kimi-code/src/cli/sub/acp.ts:61-68     runAcpServer({ homeDir, agentInfo, terminalAuth* })
packages/acp-server/src/start.ts:53-65      RunAcpServerOptions: homeDir|configPath|input|output|extraSeeds
packages/acp-server/src/server.ts:107-130   AcpServerOptions: agentInfo|disableAuth|terminalAuth*|resolveOriginalsDir
packages/acp-server/src/server.ts:242-253   newSession honours cwd | additionalDirectories | mcpServers only
packages/acp-server/src/config-options.ts:7-19   session config surface is model | thinking | mode
```

`--region` was added to `acp`; no restriction flag was. `configPath` still
exists and is still not passed by the CLI. No agent-file, tool-policy,
`--no-mcp` / `--no-hooks` / `--no-plugins` parameter appears on any of these
interfaces.

**`kimi -p` — unchanged shape.**

```text
apps/kimi-code/src/cli/options.ts:37-50     CLIOptions unchanged (no tools/mcp/hooks field)
apps/kimi-code/src/cli/commands.ts:65,77,98 -p | --skills-dir | --agent-file survive; nothing added
packages/agent-core-v2/src/agent/toolPolicy/evaluate.ts:10-29   isToolActive unchanged → tools:[] still empties the tool set
```

So print mode keeps exactly half the boundary it had, and gains nothing.

**Engine — the startup paths are intact.**

```text
features/externalHooks/externalHooksFeature.ts:18-28   hooks runner at App scope, session service at Session scope
features/externalHooks/session/sessionExternalHooksService.ts:63-69,109-110
                                                       onDidCreateSession → trigger('SessionStart', …)
features/featureRegistry.ts:3-11                       static recipe list; no gate, no per-run disable
app/plugin/pluginService.ts:368-374                    plugins still App scope, OnScopeCreated
packages/acp-server/src/acp-terminal/acpTerminalRunner.ts:58-59
    if (!this.connection.terminalEnabled || !isBashToolInvocation(...))
      return this.local.spawn(command, args, {...});
packages/acp-server/src/acp-fs/acpFsService.ts:61,69,81,122   node-local HostFileSystem fallback per operation
```

The new `Runtime` / `RuntimeProvider` layer in 2.1.1 routes *where* a process
runs and registers `'local'` as the default provider
(`workspace/workspaceInstance/workspaceInstanceManagerService.ts:83`); the ACP
runtime attaches only when the client advertises terminals
(`acp-terminal/acpTerminalRunner.ts:213-263`). It is a routing abstraction, not
an isolation one, and it reinforces A6 rather than relieving it.

**No new control anywhere.** An environment-variable diff of
`agent-core-v2`, `oauth`, `acp-server` and `apps/kimi-code` between the two
commits yields eleven new names — region marker, TUI/terminal detection,
update re-exec, share dir, subagent scope cache, watch — and none of them
disables tools, MCP, hooks or plugins. Per-plugin MCP toggles exist
(`app/plugin/manager.ts:653`) but are persistent global configuration, which is
out of bounds.

### Verdict and stop

The answer to the gating question is still **no**, on both surfaces: there is
no reachable way to remove all model-callable tools *and* keep MCP, hooks and
plugin contributions from starting, without editing global configuration or
relocating the credential store — and on ACP, withholding client capabilities
still produces local execution rather than refusal.

Investigation stops here, as instructed. Section 3 (OAuth/route evidence,
stdin transport, cancellation/error semantics, session persistence) was **not**
performed for 2.1.1: it is gated on this blocker, and clearing it would not by
itself make the integration ready. No adapter was designed and no local probe
is proposed — no probe can change this conclusion, since the finding is
structural rather than machine-specific.

---

## CONFIRMED_IN_SOURCE

> Findings `C1`-`C13` and `A1`-`A8` below are **version-specific evidence
> for 0.33.0** (`53c832d`). The 2.1.1 delta above records which of them
> were re-checked and which were not.

### C1. There is no login-status command. `doctor` proves nothing about auth

`kimi login` registers one action — start the device-code flow — and no
`status` subcommand (`apps/kimi-code/src/cli/sub/login.ts:13-19`).

`kimi doctor` validates TOML files only: it reads `config.toml` and `tui.toml`,
parses them, and exits non-zero on a parse error
(`apps/kimi-code/src/cli/sub/doctor.ts:67-80`, `:83-106`). It never touches
the auth domain. Its exit code carries no authentication meaning, exactly as
the task assumed.

The auth state itself exists in-process: `IAuthSummaryService.summarize()`
returns `AuthStatus[]` and `ensureReady()` is the readiness gate
(`packages/agent-core-v2/src/app/auth/auth.ts:82-87`;
`packages/agent-core-v2/src/app/auth/authService.ts:603`, `:626`). Neither is
exposed on any CLI surface in this version.

### C2. A successful run does not imply an OAuth route

`ensureReady` accepts an API key and returns before ever consulting OAuth:

```text
packages/agent-core-v2/src/app/auth/authService.ts:660
    if (auth.apiKey !== undefined) return;
```

The precedence that produces `auth` is
`packages/agent-core-v2/src/kosong/model/modelAuth.ts:48-84`: model-level
`apiKey` wins, then model-level `oauth`, then provider-level `apiKey` — where
the provider-level key may come from the provider's own `env` bag
(`modelAuth.ts:64-69`), i.e. from environment variables. A model/provider pair
carrying both an `apiKey` and an `oauth` ref is rejected as a conflict
(`:49-51`, `:70-72`), but a pure API-key route is a first-class, supported
path.

Consequence: "the prompt returned text" and "a credential file exists" are
both compatible with an API-key route to a non-first-party endpoint. This is
precisely what spec §2 forbids treating as proof.

### C3. The only machine-readable auth-adjacent surface is `provider list --json`

```text
apps/kimi-code/src/cli/sub/provider.ts:495-497   kimi provider list --json
apps/kimi-code/src/cli/sub/provider.ts:176-180   writes {providers, models} as JSON
```

That document contains, per provider, the fields `resolveModelAuthMaterial`
reads: `oauth`, `apiKey`, `baseUrl`, `env`, `type`. It is therefore sufficient
to decide *statically* whether the provider bound to a pinned model alias is
OAuth-routed and where it points.

Two properties limit it, and both matter:

- it is **configuration**, not a live token check — it cannot show that the
  stored OAuth token is present, unexpired or accepted;
- it may **contain secrets**: a provider's `apiKey` value is printed verbatim.
  Reading it conflicts with the project rule against reading token contents
  unless the check inspects key *presence* only and never the value.

`provider add` accepts `--api-key` and falls back to `KIMI_REGISTRY_API_KEY`
(`provider.ts:532`), so API-key providers are an ordinary, expected state of a
user's config, not an exotic one.

### C4. In print mode the prompt is an argv element — this does not generalise

```text
apps/kimi-code/src/cli/commands.ts:57-62    -p, --prompt <prompt>   (required value)
apps/kimi-code/src/cli/options.ts:68-71     promptMode = opts.prompt !== undefined
apps/kimi-code/src/cli/v2/run-v2-print.ts:216,233   opts.prompt! is the turn input
```

`apps/kimi-code/src/utils/process/stdin.ts` defines `readStdinText()` and
`createStdinLineReader()`, but a repository-wide search finds **no caller**
outside that module's own test. There is no `--prompt -` convention and no
"read stdin when not a TTY" branch on the print path.

This collides head-on with the SDLC transport: `assemble_model_input` builds
one string and `ChildInvocation.stdin_text` carries it
(`src/sdlc/model_runtime.py`). Under `kimi -p` the same text would become a
command-line argument, visible to `ps` and to anything that reads
`/proc`-equivalent process state for the lifetime of the call. Requirement text
is exactly what spec §8 keeps out of diagnostics.

**Correction to the first draft of this document.** This finding is
*print-mode-specific*, and the earlier wording over-generalised it. Native ACP
carries the prompt in the JSON-RPC request body on stdin
(`packages/acp-server/src/server.ts:386-392`, `session/prompt` →
`params.prompt`), so the argv exposure is an artefact of the `-p` surface, not
of Kimi. A stdin→argv contract change is therefore **not** the only way to
reach this CLI, and it remains unapproved; neither argv nor an input temporary
file is used as a workaround anywhere in this analysis. What ACP costs instead
is a different transport shape, examined in `A1`–`A8`.

### C5. `tools: []` in an agent file does disable every tool — and only tools

Parsing: `tools` is read as a string list; a lone `*` means "unrestricted",
an empty list stays an empty list
(`packages/agent-core-v2/src/workspace/workspaceAgentProfileLoader/internal/agentFile.ts:87-88`,
list branch at `:150-165`). The profile carries it through unchanged, and an
`--agent-file` profile is `source: 'explicit'`, which forces `override`
(`.../internal/agentProfileFromFile.ts:44-45`).

Evaluation: `packages/agent-core-v2/src/agent/toolPolicy/evaluate.ts:35-54`.
With `policy.tools = []`, the builtin branch evaluates `[].includes(name)` and
the MCP branch evaluates `[].filter(...).some(...)`; both are `false`, so
`isToolActive` returns `false` for every name and every source. Activation
skips each contribution before constructing it
(`packages/agent-core-v2/src/agent/toolActivation/toolActivationService.ts:56-77`).
Skill injection also switches off, because `skillActive` requires `tools` to
be absent or to contain `Skill`
(`.../internal/agentProfileFromFile.ts:37-39`).

Note the asymmetry, which is easy to get backwards: the **global `[tools]`
config** layer treats an explicit empty `enabled` list as *unconstrained*
(`evaluate.ts:78`, and the module docstring at `:9-11` says so). Only the
**profile** layer gives `[]` its restrictive meaning. A Kimi boundary must
therefore rest on the agent file, never on global config.

### C6. Disabling tools does not disable MCP startup, hooks or plugins

The task's warning is correct, and the scopes show why.

- **MCP** is bound at *Workspace* scope and connects from the config snapshot
  independently of any tool policy
  (`packages/agent-core-v2/src/workspace/workspaceMcp/workspaceMcpService.ts:194-200`).
  Its docstring is explicit that the manager "and its stdio child processes,
  whose cwd is the handler root" live as long as the process. Tool visibility
  is decided later and elsewhere.
- **Hooks** are bound at *App* scope, indexed from `IConfigService` `[[hooks]]`
  plus `IPluginService.enabledHooks()`
  (`packages/agent-core-v2/src/app/externalHooksRunner/externalHooksRunnerService.ts:139-145`,
  docstring `:1-15`). A `HookDef` is an arbitrary `command` string
  (`packages/agent-core-v2/src/agent/externalHooks/types.ts:28-35`).
- The hook event list includes `SessionStart`, `UserPromptSubmit`,
  `TurnStarted`, `Stop` and `SessionEnd`
  (`.../agent/externalHooks/types.ts:3-24`), none of which requires a tool
  call. `SessionStart` is triggered from session scope
  (`packages/agent-core-v2/src/session/externalHooks/externalHooksService.ts:137`).

So a `kimi -p` run with `tools: []` still starts the user's MCP stdio servers
and still executes the user's hook commands, and a `UserPromptSubmit` hook
receives the submitted prompt. For SDLC that is both an execution boundary
failure and a confidentiality failure.

### C7. Config and credentials share one root, so config cannot be isolated

```text
packages/agent-core-v2/src/app/bootstrap/bootstrap.ts:203-208
    resolveKimiHome = homeDir ?? env['KIMI_CODE_HOME'] ?? join(osHomeDir, '.kimi-code')
packages/oauth/src/toolkit.ts:128-129
    credentialsDir = options.credentialsDir ?? join(this.homeDir, 'credentials')
packages/agent-core-v2/src/app/auth/authService.ts:860-863
    OAuthToolkitService passes homeDir: bootstrap.homeDir and no credentialsDir
```

`KIMI_CODE_HOME` is the one per-invocation switch that would relocate
`config.toml` (and with it hooks, MCP servers, plugins), but it relocates
`credentials/` too, and nothing overrides the credentials directory
separately. Pointing the child at an empty home yields a child that is not
logged in.

**Isolating the user's configuration and using the user's login are mutually
exclusive in 0.33.0**, unless credentials are copied — which the task forbids
and which the spec forbids independently.

### C8. Global instruction files always reach the child

`loadAgentsMdForRoots` collects `<kimiHome>/AGENTS.md` and
`~/.agents/AGENTS.md` from the OS home, then walks each workDir from its git
work-tree root to the leaf collecting `.kimi-code/AGENTS.md` and `AGENTS.md`
(`packages/agent-core-v2/src/agent/profile/context.ts:186-210`).

An empty temporary working directory outside any repository suppresses the
project half. The two home-rooted files are not suppressible by any flag, and
`HOME` must be passed through for the login to be found. This mirrors the
`~/.codex/AGENTS.md` property the spec already records for Codex (§3), so it
is a disclosed property rather than a new class of problem — but it is not
equivalent to Claude's `--safe-mode`.

### C9. Every run creates a persisted session; there is no ephemeral mode

Sessions and logs live under the Kimi home
(`packages/agent-core-v2/src/app/bootstrap/bootstrapService.ts:56`, `:60`;
`packages/agent-core-v2/src/_base/log/logConfig.ts:41-42`). The print runner
emits a resume hint carrying the session id after the turn
(`apps/kimi-code/src/cli/v2/run-v2-print.ts:239`), which is only meaningful
because the session was written. No `--no-session-persistence` equivalent
exists on the print path.

Consequence: prompt and context are written to `~/.kimi-code/sessions/`
by the CLI itself. Claude's `--no-session-persistence` has no counterpart.

### C10. `stream-json` framing in this version

Line-delimited JSON on stdout, three shapes, written by
`apps/kimi-code/src/cli/prompt-render.ts`:

```text
{"role":"meta","type":"system.version","version":"<v>"}          :372-388  first line
{"role":"assistant","content":"...","tool_calls":[...]}          :229-235
{"role":"tool","tool_call_id":"...","content":"..."}             :200-207
{"role":"meta","type":"turn.step.retrying",...}                  :209-225
{"role":"meta","type":"session.resume_hint","session_id":...}    :390-408  last line
```

Serialisation is one `JSON.stringify` per line (`:262-266`).

Reading the result:

- the **final answer** is the concatenation of `content` from `role:"assistant"`
  lines, which are flushed when a tool call interleaves and once at `finish()`;
- **completion** is marked by the `session.resume_hint` meta line, written
  after the turn returns (`run-v2-print.ts:229-239`). Its absence is the
  reliable signal of a truncated or aborted stream;
- **tool activity** is visible as `role:"tool"` lines and `tool_calls` — under
  an intended text-only boundary any such line is a boundary violation and
  should fail the call, not be parsed;
- **errors** are not part of this schema. Startup failures print a formatted
  message to stderr and exit 1 (`apps/kimi-code/src/main.ts:192-212`);
- there is **no** model, provider or route field anywhere in the stream, so the
  stream cannot answer C1/C2.

`text` format is unsuitable for SDLC regardless: the transcript writer prefixes
the answer with `"• "` and indents every subsequent line by two spaces
(`prompt-render.ts:269-327`, constants `:48-49`), and thinking output goes to
stderr (`:105-107`, `:122-124`). Taking stdout verbatim as the model's text —
what `LocalCliModelRuntime._invoke` does today — would ingest that decoration.

### C11. Print mode has no internal turn bound

`applyPrintModeConfigDefaults` raises task timeouts, the loop step cap and the
subagent timeout for print runs (`run-v2-print.ts:152-155`), with
`PRINT_WAIT_CEILING_S_DEFAULT = 315_360_000` and
`PRINT_MAX_TURNS_DEFAULT = 100_000`
(`packages/agent-core-v2/src/agent/task/printDefaults.ts:23`, `:25`).

SDLC's own `DEFAULT_TIMEOUT_SECONDS` is therefore the only real bound. Note
that `subprocess.run(timeout=...)` kills the direct child only; Kimi's MCP
stdio children are spawned by the CLI and are not in SDLC's process group, so
a timeout can leave grandchildren behind. This is a general property of the
current transport, made concrete by C6.

### C12. Every main-command run performs an update check

`handleMainCommand` runs `runUpdatePreflight` before dispatching, passing
`isTTY: false` for print mode (`apps/kimi-code/src/main.ts:72-85`).

- Non-interactive runs never install: `decideUpdateAction` returns `'none'`
  whenever `!isInteractive` (`apps/kimi-code/src/cli/update/preflight.ts:660-668`),
  and the background path returns before installing for the same reason
  (`:254-256`).
- It still performs a **network refresh** of the update cache (`:255`).
- Both are skipped entirely when `KIMI_CODE_NO_AUTO_UPDATE` or
  `KIMI_CLI_NO_AUTO_UPDATE` is truthy (`:415-419`, `:679-681`).

Subcommands (`provider`, `doctor`, `login`, `acp`) are registered separately
(`apps/kimi-code/src/cli/commands.ts:116-120`) and do not go through
`handleMainCommand`, so they run no update preflight.

### C13. Environment variables that can redirect this CLI

Collected from `process.env` reads across `apps/kimi-code/src`,
`packages/agent-core-v2/src`, `packages/oauth/src`:

```text
KIMI_CODE_HOME            relocates config + credentials      bootstrap.ts:208
KIMI_CODE_OAUTH_HOST      OAuth host override                 oauth/constants.ts:8
KIMI_OAUTH_HOST           OAuth host override                 oauth/constants.ts:9
KIMI_CODE_BASE_URL        API base override
KIMI_BASE_URL             API base override
KIMI_API_KEY              API-key route
KIMI_REGISTRY_API_KEY     registry key                        provider.ts:480,532
KIMI_CODE_CUSTOM_HEADERS  injected request headers
KIMI_CODE_LEGACY_FLAG     switches engine to v1               experimental-v2.ts:14
KIMI_PLUGIN_ROOT          plugin discovery root
KIMI_MODEL_OUTPUT_FORMAT  default -p output format            options.ts:5
KIMI_DISABLE_OAUTH_LOCK   disables the OAuth lock
KIMI_CODE_NO_AUTO_UPDATE  suppresses the update channel       preflight.ts:418
```

Checked against `src/sdlc/model_runtime_environment.py`: today's child
environment is a strict allowlist (`BASE_PASSTHROUGH` + `CLAUDE_CONFIG_DIR`,
`CODEX_HOME` + configured passthrough), so **none of these reaches a child by
default**. The denylist, however, would not stop several of them if they were
ever added to `environment_passthrough`: `DENIED_PREFIXES` has no `KIMI`/
`MOONSHOT` entry, and `KIMI_CODE_OAUTH_HOST`, `KIMI_OAUTH_HOST`,
`KIMI_CODE_CUSTOM_HEADERS`, `KIMI_CODE_HOME`, `KIMI_CODE_LEGACY_FLAG` and
`KIMI_PLUGIN_ROOT` match no denied prefix or suffix. (`KIMI_API_KEY`,
`KIMI_BASE_URL`, `KIMI_CODE_BASE_URL` and `KIMI_REGISTRY_API_KEY` are already
caught by the `_API_KEY` / `_BASE_URL` suffix rules.)

---

## CONFIRMED_IN_SOURCE — native ACP (`kimi acp`)

Native ACP was examined because it is the only other interface this build
exposes to a programmatic caller, and because it removes the argv problem. It
does not remove the boundary problem; it makes it worse.

### A1. The CLI forwards no restriction knob to the ACP server

`registerNativeAcpCommand` constructs the server with exactly four inputs:

```text
apps/kimi-code/src/cli/sub/acp-native.ts:57-65
    const { runAcpServer } = await import('@moonshot-ai/acp-server');
    await runAcpServer({
      homeDir: getDataDir(),
      agentInfo: { name: 'Kimi Code CLI', version: getVersion() },
      ...terminalAuthEnv, ...terminalAuthLegacyCommand
    });
```

No `--agent-file`, no `--skills-dir`, no `--model`, no `--agent`. The `acp`
subcommand declares one option, `--login`
(`apps/kimi-code/src/cli/sub/acp-native.ts:34-38`). `getDataDir()` reads
`KIMI_CODE_HOME` or falls back to `~/.kimi-code`
(`apps/kimi-code/src/utils/paths.ts:34-40`), and `RunAcpServerOptions.configPath`
exists (`packages/acp-server/src/start.ts:46`) but the CLI never passes it, so
the config path is `<homeDir>/config.toml`
(`packages/acp-server/src/start.ts:91-92`).

Consequence: everything that could restrict the agent would have to arrive
through the ACP protocol itself.

### A2. The ACP protocol surface carries no tool or profile control

`session/new` honours exactly three request fields:

```text
packages/acp-server/src/server.ts:228-239
    async newSession(params) {
      await this.ensureAuthed();
      const meta = await this.klient.global.sessions.create({
        workDir: params.cwd,
        additionalDirs: params.additionalDirectories,
        mcpServers: acpMcpServersToConfigRecord(params.mcpServers),
      });
```

The per-session config surface advertised afterwards is `model`, `thinking`
and `mode` only (`packages/acp-server/src/config-options.ts:6-19`), and `mode`
is the fixed four-value permission taxonomy `default | plan | auto | yolo`
(`packages/acp-server/src/modes.ts:22-43`), whose default is `default` —
"Manual approvals; tools execute normally".

A repository-wide search of `packages/acp-server/src` finds no agent-file,
agent-profile or tool-policy parameter anywhere. **The `tools: []` lever that
print mode has through `--agent-file` (C5) has no ACP equivalent.**

`plan` mode ("Read-only planning; no tool execution") is a *permission* mode.
It does not empty the tool registry, does not stop MCP connecting, and is not
the initial mode.

### A3. `mcpServers: []` means "no client-supplied servers", not "no servers"

This was the specific ambiguity to resolve, and the code is unambiguous:

```text
packages/acp-server/src/server.ts:14-16
    ACP `mcpServers` on `session/new` / `/load` / `/resume` are converted to the
    engine's name-keyed record (see `./convert`) and injected as ephemeral
    per-session MCP servers.
```

The engine side confirms the relationship is additive: the workspace service
"builds per-session overlays (`sessionOverlay`): a session-owned manager for a
session's ephemeral (caller-injected, never persisted) servers, presented
through a `MergedMcpConnectionView` **over the shared manager**"
(`packages/agent-core-v2/src/workspace/workspaceMcp/workspaceMcpService.ts:1-27`).
The shared manager is the one holding the user's configured servers.

So an empty `mcpServers` array adds nothing and suppresses nothing. There is no
"disable all MCP" value in this protocol surface.

### A4. `session/new` alone starts MCP servers and runs SessionStart hooks

The engine "mints the session id and registers the workspace for the cwd
implicitly" (`packages/acp-server/src/server.ts:230-232`). That registration
creates the Workspace scope, and `WorkspaceMcpService` is bound there with
`ScopeActivation.OnScopeCreated`
(`.../workspaceMcp/workspaceMcpService.ts:194-200`), connecting every server
found by the config loader — user `<KIMI_CODE_HOME>/mcp.json`, project-root
`<git root>/.mcp.json`, project-local `<cwd>/.kimi-code/mcp.json`
(`.../workspaceMcpConfig/internal/config-loader.ts:47-49`) — plus any server a
plugin contributes (A5). Its stdio servers are spawned as child processes.

The Session scope then activates `SessionExternalHooksService`
(`packages/agent-core-v2/src/session/externalHooks/externalHooksService.ts:212-216`),
which registers on session creation and fires the user's `SessionStart` hook
commands for every non-fork creation (`:92-97`, `:136-143`).

**`session/new` is therefore an execution event, not a bookkeeping one.** It
spawns processes the caller did not choose, before any prompt is sent. The
task's instruction not to assume `session/new` is safe because it runs no
inference is correct.

### A5. Plugins load at App scope, before `initialize`

`bootstrap()` runs inside `runAcpServerWithStream`
(`packages/acp-server/src/start.ts:103-114`), i.e. at process start, before the
first ACP message is read. `PluginService` is App-scope `OnScopeCreated`
(`packages/agent-core-v2/src/app/plugin/pluginService.ts:282-288`) and
"exposes plugin contributions through the **hook, MCP, skill, and
system-prompt** contracts" (`:1-10`). `ExternalHooksRunnerService` is likewise
App-scope `OnScopeCreated` and builds its event→hooks index from
`IConfigService` `[[hooks]]` **plus** `IPluginService.enabledHooks()`
(`packages/agent-core-v2/src/app/externalHooksRunner/externalHooksRunnerService.ts:1-15`,
`:139-145`).

Plugin state lives at `<KIMI_CODE_HOME>/plugins/installed.json`
(`packages/agent-core-v2/src/app/plugin/store.ts:8`, `:59-61`) and
`<KIMI_CODE_HOME>/plugins/managed/<id>`
(`packages/agent-core-v2/src/app/plugin/manager.ts:531`).

Consequence for any inventory: hooks and MCP servers can be contributed by
plugins, so reading `config.toml` alone cannot establish that none exist.

### A6. Withholding client capabilities causes local execution, not refusal

This is the decisive finding, and it mirrors exactly why Codex is blocked in
the current spec (§3: "the shell binding was gone; local file reading was not").

**Terminal.** The ACP-backed process runner is registered at Agent scope, and
its own contract states:

```text
packages/acp-server/src/acp-terminal/acpTerminalRunner.ts:12-18
    Capability gating: when the client did not advertise
    `clientCapabilities.terminal` (`IAcpConnection.terminalEnabled`), or the
    invocation does not look like a Bash-tool shell command, `exec` delegates
    to a local spawn with the exact semantics of the engine's
    `SessionProcessRunner` ... Behavior with the capability off is therefore
    identical to today's.
```

**Filesystem.** The ACP-backed `IHostFileSystem` keeps a node-local backend and
falls back to it per operation:

```text
packages/acp-server/src/acp-fs/acpFsService.ts:61   private readonly inner = new HostFileSystem();
packages/acp-server/src/acp-fs/acpFsService.ts:68-70  readText  → inner when !fsReadTextFile
packages/acp-server/src/acp-fs/acpFsService.ts:80-82  writeText → inner when !fsWriteTextFile
```

So a minimal ACP client that advertises no filesystem and no terminal
capability does not get an agent that cannot touch the machine — it gets an
agent that touches the machine **directly**, bypassing the client entirely. The
capability flags choose the *route*, not the *permission*.

### A7. Permission refusal is not a boundary for startup actions

Denying every `session/request_permission` constrains tool calls the agent
chooses to make during a turn. It does not reach any of the following, all of
which happen before or outside that path:

- plugin loading and hook indexing at App scope (A5);
- MCP stdio server spawning at workspace registration (A4);
- `SessionStart` hook commands at session creation (A4);
- `Agent`-scope `exec` callers that are not Bash-tool invocations — the runner
  doc names "profile prompt-prefix commands" as one
  (`packages/acp-server/src/acp-terminal/acpTerminalRunner.ts:57-61`).

A permission denial is a turn-time control. The blocker is at startup time.

### A8. ACP does solve the argv problem

Stated for completeness, because it is the one thing ACP improves: the prompt
travels as `params.prompt` in the JSON-RPC request body over stdin
(`packages/acp-server/src/server.ts:386-392`), with stdout reserved for the
protocol stream and `console.*` redirected to stderr
(`packages/acp-server/src/start.ts:69-77`, `:188`). No requirement text would
reach argv or an input temporary file.

This does not rescue the surface: A2 and A6 mean there is no configuration of a
minimal ACP client that yields a text-only agent.

---

## The first confirmed blocker

Both surfaces stop at the same missing capability, reached by different paths.

**Native ACP call path:**

```text
apps/kimi-code/src/cli/sub/acp.ts:40-44          native ACP chosen (v2 default)
apps/kimi-code/src/cli/sub/acp-native.ts:57-65   only homeDir + agentInfo + terminalAuth* forwarded
packages/acp-server/src/start.ts:187-194         runAcpServer → runAcpServerWithStream
packages/acp-server/src/start.ts:103-114         bootstrap() builds the App scope at process start
  → app/plugin/pluginService.ts:282-288                  plugins load; contribute hooks + MCP
  → app/externalHooksRunner/externalHooksRunnerService.ts:139-145   hook index built
packages/acp-server/src/server.ts:228-239        session/new honours cwd | additionalDirectories | mcpServers
  → workspace/workspaceMcp/workspaceMcpService.ts:194-200           configured MCP servers connect (stdio children)
     sources: workspaceMcpConfig/internal/config-loader.ts:47-49
  → session/externalHooks/externalHooksService.ts:92-97, :136-143   SessionStart hook commands run
packages/acp-server/src/acp-terminal/acpTerminalRunner.ts:12-18     no terminal capability → local spawn
packages/acp-server/src/acp-fs/acpFsService.ts:61,68-70,80-82       no fs capability → local filesystem
```

**Minimum missing capability**, stated as narrowly as the evidence allows:

> A per-session (ACP) or per-invocation (CLI) parameter that binds an agent
> profile / tool policy **and** suppresses configured MCP servers, hooks and
> plugins for that session — without relocating `KIMI_CODE_HOME`, which would
> also relocate the credential store (C7).

Print mode has half of it (`--agent-file` with `tools: []`, C5) and ACP has
none of it. Neither has the other half on any surface.

Investigation of the Kimi adapter stops here, as instructed. Nothing further
was designed, and no ACP client was sketched.

## Auth and transport: not investigated

Section 3 of the task was conditional on the execution boundary being
establishable. It is not, so the following were **not** analysed and no claim
about them appears in this document:

- what ACP `authenticate` actually verifies, and whether it can distinguish an
  allowed OAuth login from a cached token of any kind;
- whether any auth evidence is bound to the provider/endpoint of the selected
  model (C2 shows the print path cannot do this; the ACP path is unexamined);
- the exact `session/prompt` payload beyond A8, streamed-event framing, final-
  answer determination, cancellation and error separation;
- long multi-line input handling, timeouts, and termination of descendants;
- ACP session-file and log retention.

Two of these carry a standing caveat that must not be lost if the work resumes:
`ensureAuthed()` is called on `session/new`
(`packages/acp-server/src/server.ts:229`) but its contents were not read, and
**C2 already establishes at engine level that a satisfied readiness check is
compatible with an API-key route** (`authService.ts:660`). Session persistence
(C9) is an engine-level property and applies to ACP sessions too; it is an open
item against spec §8, not something this document treats as acceptable.

---

## DOCUMENTED_NOT_LOCALLY_TESTED

### D1. `--agent-file` is parsed before any turn and binds the profile

`resolveNativeSession` reads and parses the file eagerly and treats a parse
failure as fatal (`run-v2-print.ts:270-299`), and the file is registered with
the highest-precedence source for the process (`:136-144`). An `--agent-file`
profile cannot be combined with `--session`/`--continue`
(`apps/kimi-code/src/cli/options.ts:100-107`).

The code path is unambiguous; that the effective tool set is empty at runtime
has not been observed on the installed build.

### D2. `--skills-dir` replaces discovery rather than adding to it

`run-v2-print.ts:136-138` passes `skillDirs` as "explicit skill dirs replace
default user / project discovery for this process". Pointing it at an empty
directory is therefore a per-invocation control over skills specifically —
independent of, and weaker than, the `tools: []` effect in C5.

### D3. ACP transport shape (superseded in part by A1-A8)

The first draft listed ACP as unexamined. Its execution boundary has since
been read in source (`A1`-`A8`) and is blocked. What remains untested rather
than unexamined is the transport behaviour of a real session: a JSON-RPC
session protocol replaces the process-per-call model, and an adapter for it
would be a different shape of client from `LocalCliModelRuntime` — larger, and
stateful across calls. That comparison is deliberately not developed here,
because A2 and A6 make it moot for this version.

The `terminal-auth` advertisement (`packages/acp-server/src/auth-methods.ts:29-56`)
initiates a login flow; it reports no login state, and SDLC never runs login.

---

## REQUIRES_LOCAL_PROBE

### Correction: the probe proposed in the first draft was wrong

The first draft suggested `grep -nE '^[[:space:]]*\[' ~/.kimi-code/config.toml`
as evidence that no hooks, MCP servers or plugins are configured. **That is not
sound and it is withdrawn.** `config.toml` is one of at least six sources:

```text
hooks        <KIMI_CODE_HOME>/config.toml  [[hooks]]     agent/externalHooks/configSection.ts:17
             + plugin contributions                      app/plugin/pluginService.ts:1-10
MCP          <KIMI_CODE_HOME>/mcp.json                   workspaceMcpConfig/internal/config-loader.ts:47
             <git work-tree root>/.mcp.json              config-loader.ts:48
             <cwd>/.kimi-code/mcp.json                   config-loader.ts:49
             + plugin contributions                      app/plugin/pluginService.ts:1-10
plugins      <KIMI_CODE_HOME>/plugins/installed.json     app/plugin/store.ts:8, :59-61
             <KIMI_CODE_HOME>/plugins/managed/<id>       app/plugin/manager.ts:531
root         KIMI_CODE_HOME relocates all of the above   bootstrap.ts:208, utils/paths.ts:34-40
```

A section grep of one TOML file inspects one of these and would report a clean
result on a machine with plugin-contributed hooks and three MCP files. Nothing
in this document should be read as suggesting that an inference run may follow
an empty grep.

### Is a local probe needed at all right now? No

The blocker is **structural**: A2 shows there is no ACP parameter that binds a
tool policy, and A6 shows that withholding capabilities relocates execution
rather than removing it. Neither statement depends on what this machine has
configured. An inventory showing zero hooks, zero MCP servers and zero plugins
would not make the boundary establishable — it would only mean this machine
currently has nothing to suppress, which is an accident of configuration, not a
control SDLC holds. Spec §2's principle applies to the boundary as well as to
authentication: absence of an observed problem is not proof.

The next step is therefore a **decision**, not a measurement (see the
Assessment). No probe is recommended at this time.

### If an inventory is wanted anyway, these are its terms

An inventory would inform exactly one decision, and only for print mode: the
B3 option-2 posture, in which "this machine declares no hooks, no MCP servers
and no plugins" is re-verified by SDLC before every run and the call is refused
otherwise. That posture is only coherent if B2 (argv) is separately approved,
and B2 is not approved. So this is optional and not on the critical path.

Terms it would have to meet:

- read-only, and it must start no `kimi` process — a run of `kimi -p`,
  `kimi acp` or `kimi doctor` is excluded, because the first two execute the
  very hooks and MCP servers being inventoried (A4, A5) and the third creates
  `config.toml` if absent (`ensureConfigFile`, `provider.ts:100-101`);
- it must cover all six sources above, not one;
- it must print **statuses and counts only** — never a hook `command`, never an
  MCP server's URL, command or headers, never a provider `apiKey` or `baseUrl`,
  never a whole file;
- a missing file, an unreadable file or a parse failure must be reported as
  `UNKNOWN`, never folded into zero. "No file" is not "no servers": it is one
  of several sources being unreadable, and the `KIMI_CODE_HOME` indirection
  means the file may simply be elsewhere.

## BLOCKED_BY_CONTRACT

Each item states the guarantee, why 0.33.0 cannot meet it, and the smallest
change that would. **None of these changes is proposed for adoption here.**

### B1. Positive authentication evidence before every call — spec §2

**Blocked, and currently moot.** No CLI surface reports login state (C1), and
success does not imply OAuth (C2). The runtime's contract is explicit that
absence of an error is not proof. The ACP `authenticate` surface was *not*
investigated, because B3 gates it — see `Auth and transport: not investigated`.
Nothing below should be read as a finding about ACP auth.

Smallest changes, least invasive first:

1. *Upstream*: a `kimi auth status --json` (or `kimi login status`) that
   reports at least `{loggedIn, provider, authMethod}`. This is the only option
   that reaches parity with the Claude check. It is a feature request, not
   something SDLC can supply.
2. *Local, weaker*: a family check that reads `kimi provider list --json`,
   resolves the pinned `--model` alias through the same precedence as
   `resolveModelAuthMaterial` (`modelAuth.ts:48-84`), and requires the bound
   provider to have an `oauth` ref, no `apiKey`, and a `baseUrl` on an
   allowlisted first-party host. This proves *configuration*, not a live
   token, and requires reading a document that may contain an API key — so it
   needs an explicit decision that presence-only inspection (never value
   reading, never echoing) is acceptable. It is weaker than the Claude check
   and must be documented as such rather than presented as equivalent.

### B2. Prompt and context on stdin — spec §3

**Blocked for print mode only.** C4. Under `kimi -p` the text would have to
move into argv. Native ACP does not have this problem (A8): the prompt travels
in a JSON-RPC body on stdin. The proposal below therefore applies to a
print-mode family and **is not required to reach this CLI at all** — it is
listed because it was the first draft's assumption and must be explicitly
retired rather than silently carried forward. It remains unapproved, and no
part of this analysis relies on it.

Smallest change, stated as a contract proposal for approval:

> Extend `ChildInvocation` so a runtime family declares how the model input is
> delivered: `stdin` (Claude, Codex — unchanged) or `argument` (Kimi). For an
> `argument` family the assembled input becomes one argv element placed after
> the restrictions and after `--model`, exactly like the model id today.

Consequences to weigh before approving, not after:

- requirement text becomes visible in the host's process list for the duration
  of the call, to any local user who can see the process table;
- it is captured by anything that records command lines (audit daemons, shell
  history if ever invoked manually, crash reporters);
- argv has an OS length limit (`ARG_MAX`); large RAW requirements or context
  bundles can exceed it, producing a failure mode Claude does not have, so the
  family would need an input-size bound tied to `assemble_model_input`;
- it makes the spec's promise that "the prompt … never appear[s] in an
  exception, a result detail or a log" narrower than it reads today, because
  the CLI's own session store already holds the text (C9).

A temporary-file variant is *not* an improvement: it trades the process table
for a filesystem artefact and still leaves the path in argv.

### B3. No tools, no MCP, no hooks in the reasoning child — spec §3, §8

**Blocked on both surfaces. This is the first and decisive blocker.**

Print mode: tools can be emptied (C5) but MCP servers still start and hook
commands still run (C6), and the one lever that would neutralise them removes
the login as well (C7).

Native ACP: worse — there is no tool or profile parameter at all (A2),
`mcpServers: []` suppresses nothing (A3), `session/new` itself spawns MCP
children and runs `SessionStart` hooks (A4), plugins load before the first
message (A5), withholding client capabilities relocates execution to the local
host instead of denying it (A6), and permission refusal does not reach any of
the startup paths (A7).

Smallest changes:

1. *Upstream*: per-invocation switches equivalent to Claude's
   `--strict-mcp-config` and `--safe-mode` — e.g. `--no-mcp`, `--no-hooks`,
   `--no-plugins` — reachable from **both** `kimi -p` and `kimi acp`; or an ACP
   `session/new` parameter binding an agent profile; or a separate credentials
   path so `KIMI_CODE_HOME` can isolate configuration while the login stays
   reachable. Any one of the three would unblock; none exists in 0.33.0.
2. *Local, narrow, and honest about what it is*: treat "this machine declares
   no hooks, no MCP servers and no plugins" as a **precondition verified per
   run** across all six sources listed under `REQUIRES_LOCAL_PROBE`, and refuse
   the call otherwise. This is a property of the user's machine, not a boundary
   SDLC establishes, so it would have to be named that way in the spec — closer
   to Codex's `RUNTIME_ISOLATION_UNAVAILABLE` posture than to Claude's. It is
   coherent only for print mode; for ACP, A6 defeats it regardless, because the
   local-execution fallback does not depend on configuration.

### B4. A new invocation mode — spec §3, §4

Not a conflict, just work that cannot happen inside this spike:
`invocation_mode` currently admits `print` and `exec`
(`src/sdlc/model_runtime.py`), and each maps to a fixed auth protocol and a
fixed restriction tuple. Kimi needs a third family with its own constants. The
existing design accommodates this cleanly; adding it is an `src/` change and is
therefore out of scope here.

### B5. Environment denylist coverage

Not blocking today — the allowlist keeps all of C13 out of the child. But
`DENIED_PREFIXES` in `src/sdlc/model_runtime_environment.py` should gain
`KIMI` and `MOONSHOT_` before any Kimi runtime exists, so that a later
`environment_passthrough` entry cannot smuggle in `KIMI_CODE_OAUTH_HOST`,
`KIMI_CODE_CUSTOM_HEADERS`, `KIMI_CODE_HOME` or `KIMI_CODE_LEGACY_FLAG`. A
Kimi family would also need its credential-store location added to
`CREDENTIAL_STORE_LOCATIONS` only if the user relocates it; the default lives
under `HOME`, which is already passed.

---

## Assessment

A Kimi adapter that preserves the current guarantees is **not possible in
0.33.0 on either surface**.

Separate conclusions, as the two surfaces really do differ:

```text
print mode (kimi -p)
  tool boundary      partial   tools:[] empties the tool set (C5)
                               MCP, hooks, plugins unaffected (C6)
  prompt transport   blocked   argv only (C4); contract change unapproved
  auth evidence      blocked   no status surface (C1); API-key route possible (C2)

native ACP (kimi acp)
  tool boundary      none      no tool/profile parameter exists (A2)
                               mcpServers:[] suppresses nothing (A3)
                               session/new spawns MCP + runs hooks (A4, A5)
                               capability withholding → local execution (A6)
                               permission refusal misses startup (A7)
  prompt transport   OK        JSON-RPC body on stdin (A8)
  auth evidence      unknown   not investigated; gated by the boundary
```

The single first blocker is **B3, the execution boundary**, and it is
structural rather than machine-specific. Neither surface can be made text-only
by any documented per-invocation or per-session control in this version.

Print mode is the closer of the two: it is one upstream switch away
(`--no-mcp` / `--no-hooks` / `--no-plugins`, or a config-only `KIMI_CODE_HOME`),
whereas ACP would additionally need a session-level agent-profile parameter
that does not exist. If the boundary is ever solved upstream, ACP is the better
transport (A8) and print mode is the better isolated agent (C5) — a future
adapter would likely want ACP's transport with print mode's profile control,
which is precisely the combination this version does not offer.

The order that matters is unchanged: B3, then B1, then — only if print mode is
still the chosen surface — B2. There is no point designing an auth check for a
child that can still run arbitrary hook commands, and no point weighing an
argv trade-off for a surface that may not be the one used.

Nothing here justifies adding Kimi to the support matrix, and nothing here
changes Codex's status.

## Scope of a future integration, if the blockers clear

Unchanged by anything above: Claude stays the default; selection stays in
`config/sdlc.toml` under the existing precedence; the three roles
(`raw_requirement_processor`, `standard_requirement_processor`,
`standard_requirement_reviewer`) become explicitly selectable; no automatic
fallback, no lifecycle change, no new orchestrator, no provider SDK, no
direct API.
