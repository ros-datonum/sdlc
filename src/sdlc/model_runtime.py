"""Model execution through locally authenticated CLIs.

Implements Local-OAuth-Model-Runtime-Spec-v0.1. The SDLC application never
authenticates with a model provider: it shells out to the user's own `claude`
or `codex` CLI, which already holds a subscription/OAuth session.

There is deliberately no API-key path, no provider SDK, and no fallback. When
local authentication cannot be positively established the call fails.

The child is a reasoning process, not a coding agent. The processors hand it
everything it needs on stdin and want only its answer back, so it runs with
the CLI's supported per-invocation restrictions: no tools, no MCP servers, no
hooks, plugins or skills, no web retrieval, no subagents, a minimal explicit
environment and an empty temporary working directory. The user's interactive
CLI settings are not touched; these controls exist only on the spawned
process's command line.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from sdlc.model_runtime_config import RuntimeDefinition, RuntimeSelection
from sdlc.model_runtime_environment import child_environment

# The CLI family. "print" is Claude Code (`claude -p`), "exec" is Codex
# (`codex exec`). The authentication protocol and the restriction policy
# follow the family; configuration cannot alter them.
INVOCATION_MODE_PRINT = "print"
INVOCATION_MODE_EXEC = "exec"

MODEL_FLAG = "--model"
PRINT_FLAG = "-p"
EXEC_SUBCOMMAND = "exec"
STDIN_ARGUMENT = "-"

DEFAULT_TIMEOUT_SECONDS = 900
AUTH_CHECK_TIMEOUT_SECONDS = 60
CHILD_DIRECTORY_PREFIX = "sdlc-model-"

# -- positive authentication evidence ----------------------------------------
#
# Claude Code: `claude auth status --json` (verified on 2.1.260) reports
# loggedIn, authMethod, apiProvider and subscriptionType. A subscription login
# is authMethod "claude.ai" routed through the first-party API. Anything else
# (console/API-key auth, Bedrock/Vertex/Foundry routing, unknown values) fails.
CLAUDE_AUTH_STATUS_ARGS = ("auth", "status", "--json")
CLAUDE_LOGGED_IN_KEY = "loggedIn"
CLAUDE_AUTH_METHOD_KEY = "authMethod"
CLAUDE_API_PROVIDER_KEY = "apiProvider"
CLAUDE_SUBSCRIPTION_KEY = "subscriptionType"
CLAUDE_ALLOWED_AUTH_METHODS = frozenset({"claude.ai"})
CLAUDE_ALLOWED_API_PROVIDERS = frozenset({"firstParty"})

# Codex: `codex login status` (verified on codex-cli 0.146.0) prints exactly
# one status line. Only the ChatGPT login line is accepted, and only as a whole
# line: text that merely mentions ChatGPT proves nothing.
CODEX_AUTH_STATUS_ARGS = ("login", "status")
CODEX_LOGIN_LINE_PREFIX = "Logged in"
CODEX_CHATGPT_LOGIN_LINE = "Logged in using ChatGPT"
CODEX_LOGGED_OUT_LINE = "Not logged in"

# -- reasoning-child restrictions ------------------------------------------
#
# Claude Code 2.1.260, verified live: --safe-mode disables CLAUDE.md, skills,
# plugins, hooks and MCP while auth and model selection work normally;
# --restricted drops the command/code tools and WebFetch, ignores user,
# project and local settings files (managed settings still apply), confines
# file tools to the working directory and refuses bypassPermissions;
# --tools "" removes every built-in tool, including the file tools and the
# Agent tool; --strict-mcp-config with no --mcp-config leaves no MCP servers;
# --permission-prompts none denies anything that would still prompt.
CLAUDE_RESTRICTIONS = (
    "--safe-mode",
    "--restricted",
    "--tools",
    "",
    "--strict-mcp-config",
    "--disable-slash-commands",
    "--permission-prompts",
    "none",
    "--no-session-persistence",
)

# Codex 0.146.0, verified live: --ignore-user-config skips ~/.codex/config.toml
# (its MCP servers, plugins, hooks, providers) while login still uses
# CODEX_HOME; --ignore-rules skips execpolicy rules; --ephemeral persists no
# session; --sandbox read-only is the strictest sandbox for anything that
# still executes; the feature switches remove the shell tool itself and every
# other capability surface; web_search "disabled" turns off the native search
# that is otherwise on by default; project_doc_max_bytes 0 loads no project
# AGENTS.md from the working directory. The user's global ~/.codex/AGENTS.md
# is still prepended as instructions: no per-invocation switch removes it on
# this version without relocating CODEX_HOME, which would relocate the login.
CODEX_DISABLED_FEATURES = (
    "shell_tool",
    "plugins",
    "hooks",
    "multi_agent",
    "apps",
    "browser_use",
    "computer_use",
    "image_generation",
    "memories",
    "skill_search",
    "code_mode_host",
    "in_app_browser",
    "remote_plugin",
)
CODEX_CONFIG_OVERRIDES = ('web_search="disabled"', "project_doc_max_bytes=0")
CODEX_RESTRICTIONS = (
    "--ignore-user-config",
    "--ignore-rules",
    "--ephemeral",
    "--skip-git-repo-check",
    "--sandbox",
    "read-only",
    *(flag for feature in CODEX_DISABLED_FEATURES for flag in ("--disable", feature)),
    *(flag for override in CODEX_CONFIG_OVERRIDES for flag in ("-c", override)),
)
CODEX_WORKDIR_FLAG = "-C"

# Never echoed back to the caller: CLI output can name the account.
CREDENTIAL_MARKERS = ("token", "key", "secret", "bearer")


class ModelRuntimeError(Exception):
    """A model could not be executed through the local CLI."""


class ModelAuthenticationError(ModelRuntimeError):
    """The local CLI is missing or not positively authenticated in an allowed mode."""


@dataclass(frozen=True)
class ModelResponse:
    """One completed model invocation."""

    text: str
    runtime: str
    model: str | None

    @property
    def used_cli_default_model(self) -> bool:
        return self.model is None


class ModelRuntime(Protocol):
    """Executes one prompt and returns the model's text.

    `project_requirement add` and `project init` need no model at all; this
    exists so the processors' reasoning step can be replaced in tests.
    """

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        """Execute the prompt and return the response text."""


@dataclass(frozen=True)
class ChildInvocation:
    """Exactly what one child process is started with."""

    argv: tuple[str, ...]
    stdin_text: str
    timeout: int
    env: Mapping[str, str]
    cwd: str


CommandRunner = Callable[[ChildInvocation], subprocess.CompletedProcess[str]]


def _run_command(invocation: ChildInvocation) -> subprocess.CompletedProcess[str]:
    # argv is built from constants and configuration, never from a shell string.
    return subprocess.run(
        list(invocation.argv),
        input=invocation.stdin_text,
        capture_output=True,
        text=True,
        timeout=invocation.timeout,
        check=False,
        env=dict(invocation.env),
        cwd=invocation.cwd,
    )


@dataclass(frozen=True)
class _Session:
    """One resolved executable, environment and working directory.

    The authentication check and the model invocation of a run share one
    session, so the login that was verified is the login that is used.
    """

    executable: str
    env: Mapping[str, str]
    cwd: str


class LocalCliModelRuntime:
    """Runs a prompt through a locally authenticated `claude` or `codex` CLI."""

    def __init__(
        self,
        selection: RuntimeSelection,
        runner: CommandRunner = _run_command,
        which: Callable[[str], str | None] = shutil.which,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._selection = selection
        self._run = runner
        self._which = which
        self._timeout = timeout_seconds
        self._environment = environment

    @property
    def selection(self) -> RuntimeSelection:
        return self._selection

    def preflight(self) -> str:
        """Check the executable exists and is authenticated in an allowed mode.

        Returns a short sanitized summary of the login method, never the
        CLI's account output.
        """
        with self._session() as session:
            return self._check_authentication(session)

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        """Verify the login, then execute the prompt under the same session."""
        with self._session() as session:
            self._check_authentication(session)
            return self._invoke(
                session, f"{context}\n\n{prompt}" if context else prompt
            )

    # -- session -------------------------------------------------------------

    def _session(self) -> _SessionScope:
        return _SessionScope(self)

    def _open_session(self) -> tuple[_Session, tempfile.TemporaryDirectory[str]]:
        definition = self._selection.definition
        executable = self._which(definition.executable)
        if executable is None:
            raise ModelAuthenticationError(
                f"The {definition.name!r} runtime needs the {definition.executable!r} "
                "executable, which is not on PATH."
            )
        parent = os.environ if self._environment is None else self._environment
        try:
            env = child_environment(parent, definition.environment_passthrough)
        except ValueError as error:
            raise ModelRuntimeError(str(error)) from error
        directory = tempfile.TemporaryDirectory(prefix=CHILD_DIRECTORY_PREFIX)
        cwd = Path(directory.name).resolve()
        if cwd.is_relative_to(Path.cwd().resolve()):
            directory.cleanup()
            raise ModelRuntimeError(
                "The temporary directory lies inside the current working directory; "
                "refusing to run the model child there."
            )
        return _Session(executable=executable, env=env, cwd=str(cwd)), directory

    # -- authentication --------------------------------------------------------

    def _check_authentication(self, session: _Session) -> str:
        definition = self._selection.definition
        if definition.invocation_mode == INVOCATION_MODE_PRINT:
            args, summarize = CLAUDE_AUTH_STATUS_ARGS, _claude_login_summary
        elif definition.invocation_mode == INVOCATION_MODE_EXEC:
            args, summarize = CODEX_AUTH_STATUS_ARGS, _codex_login_summary
        else:
            raise ModelRuntimeError(
                f"Runtime {definition.name!r} has unknown invocation mode "
                f"{definition.invocation_mode!r}."
            )
        invocation = ChildInvocation(
            argv=(session.executable, *args),
            stdin_text="",
            timeout=min(self._timeout, AUTH_CHECK_TIMEOUT_SECONDS),
            env=session.env,
            cwd=session.cwd,
        )
        try:
            result = self._run(invocation)
        except subprocess.TimeoutExpired as error:
            raise ModelAuthenticationError(
                f"{definition.executable} {' '.join(args)} did not answer within "
                f"{invocation.timeout}s; authentication could not be established."
            ) from error
        except OSError as error:
            raise ModelAuthenticationError(
                f"Could not run {definition.executable} {' '.join(args)}: "
                f"{type(error).__name__}."
            ) from error
        if result.returncode != 0:
            raise ModelAuthenticationError(
                f"{definition.executable} is not authenticated ({' '.join(args)} "
                f"exited {result.returncode}). Log in with the local CLI; SDLC will "
                "not fall back to an API key."
            )
        return summarize(definition, result.stdout, result.stderr)

    # -- invocation ------------------------------------------------------------

    def _invoke(self, session: _Session, stdin_text: str) -> ModelResponse:
        definition = self._selection.definition
        invocation = ChildInvocation(
            argv=tuple(self._build_argv(session)),
            stdin_text=stdin_text,
            timeout=self._timeout,
            env=session.env,
            cwd=session.cwd,
        )
        try:
            result = self._run(invocation)
        except subprocess.TimeoutExpired as error:
            raise ModelRuntimeError(
                f"{definition.executable} timed out after {self._timeout}s."
            ) from error
        except OSError as error:
            raise ModelRuntimeError(
                f"Could not execute {definition.executable}: {type(error).__name__}."
            ) from error

        if result.returncode != 0:
            raise ModelRuntimeError(
                f"{definition.executable} exited {result.returncode}: "
                f"{redact(result.stderr)[:500]}"
            )
        return ModelResponse(
            text=result.stdout, runtime=definition.name, model=self._selection.model
        )

    def _build_argv(self, session: _Session) -> list[str]:
        """The restricted reasoning-child command line for the CLI family.

        The restrictions are constants of the family and come before any
        configured model, so no selection can add, remove or reorder them.
        """
        definition = self._selection.definition
        model = self._selection.model
        if definition.invocation_mode == INVOCATION_MODE_PRINT:
            argv = [session.executable, PRINT_FLAG, *CLAUDE_RESTRICTIONS]
        elif definition.invocation_mode == INVOCATION_MODE_EXEC:
            argv = [
                session.executable,
                EXEC_SUBCOMMAND,
                *CODEX_RESTRICTIONS,
                CODEX_WORKDIR_FLAG,
                session.cwd,
            ]
        else:
            raise ModelRuntimeError(
                f"Runtime {definition.name!r} has unknown invocation mode "
                f"{definition.invocation_mode!r}."
            )
        if model:
            argv += [MODEL_FLAG, model]
        if definition.invocation_mode == INVOCATION_MODE_EXEC:
            argv.append(STDIN_ARGUMENT)
        return argv


class _SessionScope:
    """Context manager that removes the child's working directory afterwards."""

    def __init__(self, runtime: LocalCliModelRuntime) -> None:
        self._runtime = runtime
        self._directory: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> _Session:
        session, self._directory = self._runtime._open_session()
        return session

    def __exit__(self, *exc_info: object) -> None:
        if self._directory is not None:
            self._directory.cleanup()


# -- login summaries ----------------------------------------------------------


def _claude_login_summary(
    definition: RuntimeDefinition, stdout: str, stderr: str
) -> str:
    """Accept only an explicit claude.ai login routed through the first-party API."""
    try:
        status = json.loads(stdout)
    except ValueError as error:
        raise ModelAuthenticationError(
            f"{definition.executable} auth status did not return the expected JSON "
            "document; authentication could not be established."
        ) from error
    if not isinstance(status, dict):
        raise ModelAuthenticationError(
            f"{definition.executable} auth status returned an unexpected document."
        )
    if status.get(CLAUDE_LOGGED_IN_KEY) is not True:
        raise ModelAuthenticationError(
            f"{definition.executable} reports it is logged out. Log in with the "
            "local CLI; SDLC will not fall back to an API key."
        )
    method = status.get(CLAUDE_AUTH_METHOD_KEY)
    if method not in CLAUDE_ALLOWED_AUTH_METHODS:
        raise ModelAuthenticationError(
            f"{definition.executable} is authenticated through {_label(method)}, "
            "which is not a subscription login. SDLC requires the claude.ai account "
            "login and never uses API-key or Console billing authentication."
        )
    provider = status.get(CLAUDE_API_PROVIDER_KEY)
    if provider not in CLAUDE_ALLOWED_API_PROVIDERS:
        raise ModelAuthenticationError(
            f"{definition.executable} routes requests through {_label(provider)}, "
            "not the first-party API. SDLC does not use third-party provider routes."
        )
    subscription = status.get(CLAUDE_SUBSCRIPTION_KEY)
    tier = f", subscription {subscription}" if isinstance(subscription, str) else ""
    return f"{definition.executable}: logged in via {method} ({provider}{tier})"


def _codex_login_summary(
    definition: RuntimeDefinition, stdout: str, stderr: str
) -> str:
    """Accept only the CLI's own ChatGPT login line, as a whole line."""
    lines = [
        line.strip() for line in f"{stdout}\n{stderr}".splitlines() if line.strip()
    ]
    login_lines = [line for line in lines if line.startswith(CODEX_LOGIN_LINE_PREFIX)]
    logged_out = any(line.startswith(CODEX_LOGGED_OUT_LINE) for line in lines)
    if logged_out or login_lines != [CODEX_CHATGPT_LOGIN_LINE]:
        raise ModelAuthenticationError(
            f"{definition.executable} did not report a ChatGPT login. SDLC requires "
            "the ChatGPT account login and never uses API-key authentication."
        )
    return f"{definition.executable}: {CODEX_CHATGPT_LOGIN_LINE}"


def _label(value: object) -> str:
    return repr(value) if isinstance(value, str) else "an unknown method"


def redact(text: str) -> str:
    """Drop lines that look like they carry a credential."""
    return "\n".join(
        line
        for line in text.splitlines()
        if not any(marker in line.lower() for marker in CREDENTIAL_MARKERS)
    ).strip()
