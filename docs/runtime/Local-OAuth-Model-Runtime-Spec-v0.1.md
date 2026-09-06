# Local OAuth Model Runtime Specification v0.1

**Status:** Project runtime constraint for the first SDLC implementation.

## 1. Goal

Allow SDLC components to invoke reasoning/coding models through the user's already installed and locally authenticated CLI tools.

Supported runtimes for MVP:

```text
claude
codex
```

The SDLC application does not authenticate directly with model-provider APIs.

## 2. Mandatory authentication boundary

Model execution must use local CLI authentication state, and that state must
be **positively proven** before every invocation. Absence of an error is not
proof; exit code 0 is not proof; text that mentions a login method is not
proof.

Allowed logins:

```text
claude   claude.ai account login, requests routed through the first-party API
codex    ChatGPT account login
```

Evidence the runtime requires (verified on Claude Code 2.1.260 and codex-cli
0.146.0):

```text
claude auth status --json   loggedIn == true
                            authMethod  in {"claude.ai"}
                            apiProvider in {"firstParty"}
codex login status          a whole line equal to "Logged in using ChatGPT"
                            and no "Not logged in" line
```

Everything else fails closed: a non-zero status exit; `loggedIn: false` with
exit 0; empty, malformed or non-object status output; a missing or unknown
`authMethod` or `apiProvider`; Console/API-key login; Bedrock, Vertex, Foundry
or any other provider route; Codex output whose login line names an API key,
that contradicts itself, or that merely contains the word ChatGPT. A status
check that times out or cannot be started is an authentication failure.

The guard is a property of the CLI family, not of configuration. No
configuration key can omit the status command, relax the accepted values or
turn the check off. The status document is never echoed: the runtime returns
a short summary naming the login method and route, never the account.

The project/runtime may check status, but must not copy OAuth credentials into
the repository or application configuration, read token contents, export
tokens, run login/logout, or create project-local credential storage.

Forbidden:

```text
ANTHROPIC_API_KEY based model calls
OPENAI_API_KEY based model calls
provider SDK model execution
OpenRouter
custom proxy/base URL model routing
committed OAuth/access tokens
```

## 3. Invocation

### One session for the check and the call

The executable is resolved on PATH once, before anything else, and the same
resolved path, the same child environment and the same working directory are
used for the status check and for the model call. What was verified is what
runs.

### Child environment

The child receives an explicit allowlist, never the parent environment:

```text
PATH HOME USER LOGNAME TMPDIR LANG LC_ALL LC_CTYPE TERM
CLAUDE_CONFIG_DIR CODEX_HOME        (where the CLI keeps its login, if relocated)
+ names listed in environment_passthrough
```

`environment_passthrough` may add names such as `HTTPS_PROXY`. It can never
add a name beginning with `ANTHROPIC_`, `OPENAI_`, `CLAUDE`, `CODEX_`,
`AWS_`, `GOOGLE_`, `AZURE_` or `FIBERY_`, or ending in `_API_KEY`, `_TOKEN`,
`_SECRET` or `_BASE_URL`; such a configuration fails to load. `FIBERY_TOKEN`,
provider keys, base-URL overrides and the variables of an enclosing Claude
Code session therefore never reach the child.

### Working directory

Each run creates an empty temporary directory outside the repository, runs
both children in it, and removes it afterwards. The repository is never the
child's working directory and is never exposed through additional-directory
flags. The directory is not a security boundary on its own; it matters only
together with the restrictions below.

### Claude runtime

```bash
claude -p --safe-mode --restricted --tools "" --strict-mcp-config \
       --disable-slash-commands --permission-prompts none \
       --no-session-persistence [--model <MODEL>]
```

Prompt and context arrive on stdin. Verified on 2.1.260: `--safe-mode`
disables CLAUDE.md, skills, plugins, hooks and MCP servers while login and
model selection work normally; `--restricted` removes the command and code
tools and WebFetch, ignores user, project and local settings files (managed
settings still apply), confines file tools to the working directory and
refuses `bypassPermissions`; `--tools ""` removes every built-in tool,
including the file tools and the Agent tool, so no subagent can restore
anything; `--strict-mcp-config` with no `--mcp-config` leaves no MCP server;
`--permission-prompts none` denies anything that would still prompt. The
session init reports `tools: []`, `mcp_servers: []`, `plugins: []` and
`apiKeySource: none`.

`--bare` is not used: it skips OAuth and keychain authentication entirely.

### Codex runtime

```bash
codex exec --ignore-user-config --ignore-rules --ephemeral \
           --skip-git-repo-check --sandbox read-only \
           --disable shell_tool --disable plugins --disable hooks \
           --disable multi_agent --disable apps --disable browser_use \
           --disable computer_use --disable image_generation \
           --disable memories --disable skill_search --disable code_mode_host \
           --disable in_app_browser --disable remote_plugin \
           -c 'web_search="disabled"' -c project_doc_max_bytes=0 \
           -C <temporary directory> [--model <MODEL>] -
```

Verified on 0.146.0: `--ignore-user-config` skips `~/.codex/config.toml`, so
its MCP servers, plugins, hooks and provider settings do not load while login
still uses `CODEX_HOME`; `--disable shell_tool` removes command execution
itself, so `--sandbox read-only` only bounds what could not otherwise be
removed; `web_search` defaults to `cached` and is turned off explicitly;
`project_doc_max_bytes=0` loads no project `AGENTS.md` from the working
directory. The final message is the only stdout content.

Known residual on 0.146.0: the user's global `~/.codex/AGENTS.md` is still
prepended to the child's instructions. It is the user's own instruction text,
not a tool or a secret, and no per-invocation switch removes it without
relocating `CODEX_HOME`, which would also relocate the login. The Claude
runtime's `--safe-mode` does drop `CLAUDE.md`.

### Contract correction

The earlier ban on runtime permission, tool and sandbox flags confused the
user's interactive development settings with SDLC's reasoning child. The
distinction now is:

- restrictive controls scoped to the spawned reasoning process are required;
- permission-bypass flags (`--dangerously-skip-permissions`,
  `--allow-dangerously-skip-permissions`,
  `--dangerously-bypass-approvals-and-sandbox`,
  `--dangerously-bypass-hook-trust`, `--permission-mode`, `--sandbox
  danger-full-access`) remain forbidden;
- managed (policy) settings are never bypassed;
- global and project Claude/Codex settings files and the user's interactive
  allow-edits behaviour are never changed by SDLC.

Provider and auth overrides (`--api-key`, base URLs, `--oss`,
`--local-provider`, `--settings` carrying credentials) are never passed.

## 4. Model selection

Configuration lives in:

```text
config/sdlc.toml
```

Selection precedence:

```text
explicit run/CLI override
→ role-specific runtime/model
→ project default runtime/model
→ local CLI default model when no model is configured
```

TOML has no null, so "use the local CLI default model" is expressed by omitting
the `model` key. Because the reasoning child ignores the user's own settings
files, that default is the installed CLI build's default model, not the model
set in `~/.claude/settings.json` or `~/.codex/config.toml`. Configure `model`
to pin one. The runtime never substitutes a model or a runtime on its own.

Model IDs/aliases are configuration data, not hard-coded into agent logic. A
configured model is one argv element placed after the restrictions; it can
neither add nor remove them.

## 5. Preflight

Before invoking a runtime:

1. resolve the executable on PATH;
2. build the explicit child environment and the temporary working directory;
3. execute the family's auth-status command under them;
4. positively verify the allowed login and route, as in section 2;
5. resolve the configured model/runtime;
6. invoke the restricted child under the same session;
7. capture exit status, stdout and stderr without exposing credentials or
   private input in error messages.

Authentication failure must produce an explicit runtime error and must not
fall back to provider APIs or OpenRouter. A rejected preflight starts no
inference process.

## 6. No credential fallback

If local OAuth/subscription authentication is unavailable:

```text
FAIL
```

not:

```text
try API key
try OpenRouter
try another remote provider
```

## 7. Project tool settings

`.claude/settings.json` and `.codex/config.toml` must not configure model
runtime credentials or override the user's global permission/edit behavior.

The SDLC application's model routing is independent of the interactive
coding-tool project configuration, and the restrictions of section 3 live only
on the spawned process's command line.

## 8. What the boundary is and is not

The reasoning child cannot, by construction of the command line, run shell
commands, read or edit local files, call MCP servers or connectors (Fibery
included), fetch the web, or delegate to subagents; it cannot see the
application's secrets or provider overrides; it starts in an empty directory.
Its CLI still performs its normal login refresh and internal bookkeeping,
which is required, and managed (policy) settings still apply.

It does not remove the user's own instruction files from every CLI (see the
Codex residual above), and it does not change what the CLI reports to its
vendor as part of normal operation.

This is not a hermetic OS sandbox. The restrictions are the CLI's supported
per-invocation controls, verified on the versions above by inspecting the
effective session configuration and by observed behaviour with canary files
and synthetic environment values. A CLI upgrade that changes a flag's meaning
must be re-verified; a flag that the installed CLI rejects makes the run fail,
it does not degrade the boundary.
