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

Model execution must use local CLI authentication state.

Allowed:

```text
claude auth login
claude auth status

codex login
codex login status
```

The project/runtime may check status, but must not copy OAuth credentials into the repository or application configuration.

Forbidden:

```text
ANTHROPIC_API_KEY based model calls
OPENAI_API_KEY based model calls
provider SDK model execution
OpenRouter
custom proxy/base URL model routing
committed OAuth/access tokens
```

For Claude, subscription/account authentication is required; Console/API-billing authentication is not the intended runtime.

For Codex, ChatGPT OAuth authentication is required; API-key authentication must be rejected for SDLC model execution.

## 3. Invocation

### Claude runtime

Conceptual invocation:

```bash
claude -p --model <MODEL> "<PROMPT>"
```

If no model is configured, omit `--model` and use the local CLI default.

The adapter may pipe large context into stdin.

Do not pass permission-mode/bypass flags from SDLC runtime configuration.

### Codex runtime

Conceptual invocation:

```bash
codex exec --model <MODEL> --cd <WORKSPACE> -
```

Prompt/context may be sent on stdin.

If no model is configured, omit `--model`.

Do not pass:
- `--dangerously-bypass-approvals-and-sandbox`;
- `--sandbox`;
- provider/auth overrides.

Global/local Codex policy remains authoritative.

## 4. Model selection

Configuration lives in:

```text
config/sdlc.yaml
```

Selection precedence:

```text
explicit run/CLI override
→ role-specific runtime/model
→ project default runtime/model
→ local CLI default model when model is null
```

Example:

```yaml
model_runtime:
  default:
    runtime: claude
    model: null

  roles:
    raw_requirement_processor:
      runtime: codex
      model: gpt-5.6-sol
```

Model IDs/aliases are configuration data, not hard-coded into agent logic.

## 5. Preflight

Before invoking a runtime:

1. verify executable exists;
2. execute its auth-status command;
3. verify allowed local authentication mode;
4. resolve configured model/runtime;
5. invoke the CLI;
6. capture exit status/stdout/stderr without exposing credentials.

Authentication failure must produce an explicit runtime error and must not fall back to provider APIs or OpenRouter.

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

`.claude/settings.json` and `.codex/config.toml` must not configure model runtime credentials or override the user's global permission/edit behavior.

The SDLC application's model routing is independent of the interactive coding-tool project configuration.
