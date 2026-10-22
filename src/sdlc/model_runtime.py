"""Model execution through locally authenticated CLIs.

Implements Local-OAuth-Model-Runtime-Spec-v0.1. The SDLC application never
authenticates with a model provider: it shells out to the user's own `claude`
or `codex` CLI, which already holds a subscription/OAuth session.

There is deliberately no API-key path, no provider SDK, and no fallback. When
local authentication cannot be positively established the call fails.

Only CLI families whose reasoning-child boundary has been verified may
execute a model. Codex is currently refused at the execution boundary: the
reviewed codex-cli 0.146.0 kept an exec-hosted local-file reader despite every
disabling flag, so a request for it fails before any subprocess starts and no
other runtime is substituted. Re-enabling it needs a separately reviewed,
capability-verified policy, not a version bump.

Failure diagnostics carry only controlled fields: the runtime, the stage, an
exit code or timeout classification and a message written here. Subprocess
output, the prompt, the status document and the environment never appear in
an exception.

The child is a reasoning process, not a coding agent. The processors hand it
everything it needs on stdin and want only its answer back, so it runs with
the CLI's supported per-invocation restrictions: no tools, no MCP servers, no
skills or slash commands, no web retrieval, no subagents, a minimal explicit
environment and an empty temporary working directory. The user's interactive
CLI settings are not touched; these controls exist only on the spawned
process's command line and environment.

Local-OAuth-Model-Runtime-Claude-2.1.306-Amendment-v0.1 adds three Claude
controls. The resolved executable file must be the operator-qualified build
(its SHA-256), and that file, never the symlink that named it, runs both the
login check and the inference. Fixed environment values switch off the
child's analytics and its implicit `@` file attachments. And the answer is
taken only from a stream-json
session whose own init record shows exactly the qualified built-in plugins
and no capability (claude_session.py). Built-in plugins do load and their
hooks do run under --safe-mode on that build; the amendment states what they
can and cannot do there.
"""

from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Protocol

from sdlc.claude_session import (
    STREAM_OUTPUT_FLAGS,
    ExpectedSession,
    SessionRejected,
    SessionValidator,
    validate_stream,
)
from sdlc.model_runtime_config import (
    QualifiedBinary,
    RuntimeDefinition,
    RuntimeSelection,
)
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
# How long a stopped child may take to exit, and its output readers to drain.
CHILD_EXIT_GRACE_SECONDS = 5
FINGERPRINT_CHUNK_BYTES = 1 << 20

STAGE_AUTHENTICATION = "authentication"
STAGE_INFERENCE = "inference"

# -- execution support -------------------------------------------------------
#
# The tool boundary of the Codex family failed independent verification on
# codex-cli 0.146.0: with --disable shell_tool, --disable code_mode_host,
# --disable unified_exec and --sandbox read-only, an exec-hosted file viewer
# still returned the bytes of files inside and outside the working directory.
# Until a separately reviewed policy verifies a boundary, Codex is not
# eligible for SDLC reasoning execution. The decision keys on the family, not
# on a version number.
RUNTIME_ISOLATION_UNAVAILABLE = "RUNTIME_ISOLATION_UNAVAILABLE"
EXECUTION_UNAVAILABLE_FAMILIES = {
    INVOCATION_MODE_EXEC: (
        "the Codex CLI was requested, but the tool boundary SDLC requires for "
        "its reasoning child is not currently established: the reviewed "
        "installed version, codex-cli 0.146.0, kept an exec-hosted local-file "
        "reader despite every disabling flag. No model was invoked and no other "
        "runtime was tried; select a supported runtime explicitly, for example "
        "the project default or --runtime claude."
    ),
}

# -- positive authentication evidence ----------------------------------------
#
# Claude Code: `claude auth status --json` (verified on 2.1.260) reports
# loggedIn, authMethod and apiProvider among other fields. A subscription
# login is authMethod "claude.ai" routed through the first-party API. Anything
# else (console/API-key auth, Bedrock/Vertex/Foundry routing, unknown values)
# fails, and the received value is never reported: only these allowlisted
# labels ever appear in a summary.
CLAUDE_AUTH_STATUS_ARGS = ("auth", "status", "--json")
CLAUDE_LOGGED_IN_KEY = "loggedIn"
CLAUDE_AUTH_METHOD_KEY = "authMethod"
CLAUDE_API_PROVIDER_KEY = "apiProvider"
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
# installed plugins, settings hooks and MCP while auth and model selection
# work normally; --restricted drops the command/code tools and WebFetch,
# ignores user, project and local settings files (managed settings still
# apply), confines file tools to the working directory and refuses
# bypassPermissions; --tools "" removes every built-in tool, including the
# file tools and the Agent tool; --strict-mcp-config with no --mcp-config
# leaves no MCP servers; --permission-prompts none denies anything that would
# still prompt. On 2.1.306 --safe-mode leaves built-in plugins loaded and
# their hooks running; the qualified plugin set and what it can do are fixed
# by the amendment and checked on every call (claude_session.py).
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

# Codex 0.146.0: the invocation below is what SDLC would use, and it is NOT
# sufficient. Independent review showed that --ignore-user-config,
# --sandbox read-only and every feature switch (shell_tool, code_mode_host,
# unified_exec, plugins, hooks, multi_agent, apps, ...) still left an
# exec-hosted file viewer that returned the bytes of files inside and
# outside the working directory. The family is therefore refused at the
# execution boundary (EXECUTION_UNAVAILABLE_FAMILIES); these constants stay
# only so the selection remains representable and the shape is documented.
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


class ModelRuntimeError(Exception):
    """A model could not be executed through the local CLI.

    The message is authored here from controlled fields. It never carries
    subprocess output, the prompt, a status document or the environment.
    """

    def __init__(
        self,
        message: str,
        *,
        runtime: str | None = None,
        stage: str | None = None,
        exit_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.runtime = runtime
        self.stage = stage
        self.exit_code = exit_code


class ModelAuthenticationError(ModelRuntimeError):
    """The local CLI is missing or not positively authenticated in an allowed mode."""


class RuntimeIsolationUnavailable(ModelRuntimeError):
    """The selected CLI family, or the installed build, may not execute a model.

    Raised before any subprocess starts. Not an authentication failure and
    not a missing executable: the CLI may be installed and logged in.
    """


class ModelSessionRejected(ModelRuntimeError):
    """The child ran, but its session was not the qualified one.

    Its answer is discarded. `code` is the fixed reason from claude_session.
    """

    def __init__(self, message: str, *, code: str, runtime: str | None) -> None:
        super().__init__(message, runtime=runtime, stage=STAGE_INFERENCE)
        self.code = code


@dataclass(frozen=True)
class ModelResponse:
    """One completed model invocation."""

    text: str
    runtime: str
    model: str | None

    @property
    def used_cli_default_model(self) -> bool:
        return self.model is None


def assemble_model_input(prompt: str, context: str) -> str:
    """The exact text a runtime hands to its CLI on stdin.

    Every runtime and every input-size check measure this same string, so a
    bound on it is a bound on what SDLC actually sends. Hidden CLI or system
    instructions are outside it.
    """
    return f"{context}\n\n{prompt}" if context else prompt


class ModelRuntime(Protocol):
    """Executes one prompt and returns the model's text.

    `project_requirement add` and `project init` need no model at all; this
    exists so the processors' reasoning step can be replaced in tests.
    """

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        """Execute the prompt and return the response text."""


@dataclass(frozen=True)
class ChildInvocation:
    """Exactly what one child process is started with.

    `on_stdout_line`, when given, sees each stdout line as it arrives; if it
    raises, the child is stopped at once and the exception propagates. A
    runner that cannot stream may ignore it: the complete stdout is validated
    again afterwards.
    """

    argv: tuple[str, ...]
    stdin_text: str
    timeout: int
    env: Mapping[str, str]
    cwd: str
    on_stdout_line: Callable[[str], None] | None = None


CommandRunner = Callable[[ChildInvocation], subprocess.CompletedProcess[str]]


def _run_command(invocation: ChildInvocation) -> subprocess.CompletedProcess[str]:
    # argv is built from constants and configuration, never from a shell string.
    if invocation.on_stdout_line is not None:
        return _run_streaming(invocation, invocation.on_stdout_line)
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


def _run_streaming(
    invocation: ChildInvocation, on_line: Callable[[str], None]
) -> subprocess.CompletedProcess[str]:
    """Run the child, handing each stdout line to `on_line` as it arrives.

    Same contract as subprocess.run: TimeoutExpired after the timeout, the
    child killed. If `on_line` raises, the child is killed and the exception
    propagates. Stdin is written, and stderr drained, on their own threads so
    neither pipe can stall the other.
    """
    process = subprocess.Popen(
        list(invocation.argv),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=dict(invocation.env),
        cwd=invocation.cwd,
    )
    lines: queue.Queue[str | None] = queue.Queue()
    stderr_parts: list[str] = []
    threads = [
        threading.Thread(target=_feed_stdin, args=(process, invocation.stdin_text)),
        threading.Thread(target=_drain_lines, args=(process.stdout, lines)),
        threading.Thread(target=_drain_text, args=(process.stderr, stderr_parts)),
    ]
    for thread in threads:
        thread.daemon = True
        thread.start()
    deadline = time.monotonic() + invocation.timeout
    stdout_parts: list[str] = []
    try:
        while (line := _next_line(lines, deadline, invocation)) is not None:
            stdout_parts.append(line)
            on_line(line)
        returncode = process.wait(timeout=max(0.0, deadline - time.monotonic()))
    except BaseException:
        process.kill()
        process.wait(timeout=CHILD_EXIT_GRACE_SECONDS)
        raise
    finally:
        for thread in threads:
            thread.join(timeout=CHILD_EXIT_GRACE_SECONDS)
    return subprocess.CompletedProcess(
        list(invocation.argv), returncode, "".join(stdout_parts), "".join(stderr_parts)
    )


def _next_line(
    lines: queue.Queue[str | None], deadline: float, invocation: ChildInvocation
) -> str | None:
    remaining = deadline - time.monotonic()
    try:
        if remaining <= 0:
            raise queue.Empty
        return lines.get(timeout=remaining)
    except queue.Empty:
        raise subprocess.TimeoutExpired(
            list(invocation.argv), invocation.timeout
        ) from None


def _feed_stdin(process: subprocess.Popen[str], text: str) -> None:
    stdin = process.stdin
    if stdin is None:
        return
    try:
        stdin.write(text)
        stdin.close()
    except OSError:
        # The child exited or was stopped before reading all its input; its
        # exit status and output are what the caller judges.
        return


def _drain_lines(stream: IO[str] | None, lines: queue.Queue[str | None]) -> None:
    for line in stream or ():
        lines.put(line)
    lines.put(None)


def _drain_text(stream: IO[str] | None, parts: list[str]) -> None:
    if stream is not None:
        parts.append(stream.read())


def _file_sha256(path: str) -> str:
    """SHA-256 of the executable file. Cost: one sequential read of the binary."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while chunk := handle.read(FINGERPRINT_CHUNK_BYTES):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class _Session:
    """One resolved executable, environment and working directory.

    The authentication check and the model invocation of a run share one
    session, so the login that was verified is the login that is used.
    """

    executable: str
    env: Mapping[str, str]
    cwd: str


# The CLI families whose build must be operator-qualified before they run.
QUALIFIED_BUILD_FAMILIES = frozenset({INVOCATION_MODE_PRINT})


class LocalCliModelRuntime:
    """Runs a prompt through a locally authenticated `claude` or `codex` CLI."""

    def __init__(
        self,
        selection: RuntimeSelection,
        runner: CommandRunner = _run_command,
        which: Callable[[str], str | None] = shutil.which,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        environment: Mapping[str, str] | None = None,
        resolve: Callable[[str], str] = os.path.realpath,
        fingerprint: Callable[[str], str] = _file_sha256,
    ) -> None:
        self._selection = selection
        self._run = runner
        self._which = which
        self._timeout = timeout_seconds
        self._environment = environment
        self._resolve = resolve
        self._fingerprint = fingerprint

    @property
    def selection(self) -> RuntimeSelection:
        return self._selection

    def preflight(self) -> str:
        """Check the executable exists and is authenticated in an allowed mode.

        Returns a short sanitized summary of the login method, never the
        CLI's account output. Being authenticated is not the same as being
        eligible to execute: a family whose boundary is unverified, or a build
        that is not the qualified one, is reported as authenticated but not
        eligible. This diagnostic runs no model; `run` enforces eligibility
        before any process starts.
        """
        with self._session(qualify=False) as session:
            summary = self._check_authentication(session)
        definition = self._selection.definition
        reason = EXECUTION_UNAVAILABLE_FAMILIES.get(definition.invocation_mode)
        if reason is not None:
            return (
                f"{summary}; authenticated but not eligible for SDLC reasoning "
                f"execution ({RUNTIME_ISOLATION_UNAVAILABLE})"
            )
        if definition.invocation_mode in QUALIFIED_BUILD_FAMILIES:
            try:
                self._qualified_executable(session.executable)
            except RuntimeIsolationUnavailable as refusal:
                return (
                    f"{summary}; authenticated but not eligible for SDLC reasoning "
                    f"execution ({refusal})"
                )
        return summary

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        """Verify the login, then execute the prompt under the same session.

        A family without a verified boundary is refused here, before the
        executable is looked up and before any subprocess starts.
        """
        self._require_execution_supported()
        with self._session() as session:
            self._check_authentication(session)
            return self._invoke(session, assemble_model_input(prompt, context))

    def _require_execution_supported(self) -> None:
        definition = self._selection.definition
        reason = EXECUTION_UNAVAILABLE_FAMILIES.get(definition.invocation_mode)
        if reason is not None:
            raise RuntimeIsolationUnavailable(
                f"{RUNTIME_ISOLATION_UNAVAILABLE}: runtime {definition.name!r}: "
                f"{reason}",
                runtime=definition.name,
                stage=STAGE_INFERENCE,
            )

    # -- session -------------------------------------------------------------

    def _session(self, qualify: bool = True) -> _SessionScope:
        return _SessionScope(self, qualify)

    def _open_session(
        self, qualify: bool = True
    ) -> tuple[_Session, tempfile.TemporaryDirectory[str]]:
        definition = self._selection.definition
        executable = self._which(definition.executable)
        if executable is None:
            raise ModelAuthenticationError(
                f"The {definition.name!r} runtime needs the {definition.executable!r} "
                "executable, which is not on PATH.",
                runtime=definition.name,
                stage=STAGE_AUTHENTICATION,
            )
        if qualify and definition.invocation_mode in QUALIFIED_BUILD_FAMILIES:
            executable = self._qualified_executable(executable)
        parent = os.environ if self._environment is None else self._environment
        try:
            env = child_environment(
                parent,
                definition.environment_passthrough,
                fixed_for=definition.invocation_mode,
            )
        except ValueError as error:
            raise ModelRuntimeError(str(error), runtime=definition.name) from error
        directory = tempfile.TemporaryDirectory(prefix=CHILD_DIRECTORY_PREFIX)
        cwd = Path(directory.name).resolve()
        if cwd.is_relative_to(Path.cwd().resolve()):
            directory.cleanup()
            raise ModelRuntimeError(
                "The temporary directory lies inside the current working directory; "
                "refusing to run the model child there."
            )
        return _Session(executable=executable, env=env, cwd=str(cwd)), directory

    def _qualified_executable(self, found: str) -> str:
        """The resolved executable file, refused unless it is the qualified build.

        Resolved once per session: the login check and the inference both run
        this file, so a symlink repointed afterwards changes nothing. The
        version string is not trusted; the file's SHA-256 is the identity.
        """
        definition = self._selection.definition
        qualified = definition.qualified_binary
        if qualified is None:
            raise self._not_qualified(
                "no build of this CLI is qualified in the runtime configuration "
                "(qualified_binary)."
            )
        resolved = self._resolve(found)
        if not os.path.isabs(resolved):
            raise self._not_qualified("the executable did not resolve to a file.")
        try:
            digest = self._fingerprint(resolved)
        except OSError as error:
            raise self._not_qualified(
                f"the resolved executable could not be read ({type(error).__name__})."
            ) from error
        if digest != qualified.sha256:
            raise self._not_qualified(
                f"the resolved executable {resolved} is not the qualified build "
                f"{qualified.version}; a new build needs its own qualification."
            )
        return resolved

    def _not_qualified(self, reason: str) -> RuntimeIsolationUnavailable:
        definition = self._selection.definition
        return RuntimeIsolationUnavailable(
            f"{RUNTIME_ISOLATION_UNAVAILABLE}: runtime {definition.name!r}: {reason} "
            "No model was invoked.",
            runtime=definition.name,
            stage=STAGE_AUTHENTICATION,
        )

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
                f"{invocation.timeout}s; authentication could not be established.",
                runtime=definition.name,
                stage=STAGE_AUTHENTICATION,
            ) from error
        except OSError as error:
            raise ModelAuthenticationError(
                f"Could not run {definition.executable} {' '.join(args)}: "
                f"{type(error).__name__}.",
                runtime=definition.name,
                stage=STAGE_AUTHENTICATION,
            ) from error
        if result.returncode != 0:
            raise ModelAuthenticationError(
                f"{definition.executable} is not authenticated ({' '.join(args)} "
                f"exited {result.returncode}; its output is not reported). Log in "
                "with the local CLI; SDLC will not fall back to an API key.",
                runtime=definition.name,
                stage=STAGE_AUTHENTICATION,
                exit_code=result.returncode,
            )
        return summarize(definition, result.stdout, result.stderr)

    # -- invocation ------------------------------------------------------------

    def _invoke(self, session: _Session, stdin_text: str) -> ModelResponse:
        definition = self._selection.definition
        expected = self._expected_session(session)
        invocation = ChildInvocation(
            argv=tuple(self._build_argv(session)),
            stdin_text=stdin_text,
            timeout=self._timeout,
            env=session.env,
            cwd=session.cwd,
            on_stdout_line=(
                SessionValidator(expected).feed if expected is not None else None
            ),
        )
        try:
            result = self._run(invocation)
        except SessionRejected as rejected:
            raise self._rejected(rejected) from rejected
        except subprocess.TimeoutExpired as error:
            raise ModelRuntimeError(
                f"{definition.executable} timed out after {self._timeout}s during "
                "inference; no response was produced.",
                runtime=definition.name,
                stage=STAGE_INFERENCE,
            ) from error
        except OSError as error:
            raise ModelRuntimeError(
                f"Could not execute {definition.executable} for inference: "
                f"{type(error).__name__}.",
                runtime=definition.name,
                stage=STAGE_INFERENCE,
            ) from error

        if result.returncode != 0:
            raise ModelRuntimeError(
                f"{definition.executable} exited {result.returncode} during "
                "inference; its output is not reported.",
                runtime=definition.name,
                stage=STAGE_INFERENCE,
                exit_code=result.returncode,
            )
        text = result.stdout
        if expected is not None:
            try:
                text = validate_stream(result.stdout, expected)
            except SessionRejected as rejected:
                raise self._rejected(rejected) from rejected
        return ModelResponse(
            text=text, runtime=definition.name, model=self._selection.model
        )

    def _expected_session(self, session: _Session) -> ExpectedSession | None:
        """What a qualified build's session must report; None for other families."""
        qualified: QualifiedBinary | None = self._selection.definition.qualified_binary
        if self._selection.definition.invocation_mode not in QUALIFIED_BUILD_FAMILIES:
            return None
        if qualified is None:
            raise self._not_qualified("no build of this CLI is qualified.")
        return ExpectedSession(
            cwd=session.cwd,
            version=qualified.version,
            builtin_plugins=qualified.builtin_plugins,
            protocol_capabilities=qualified.protocol_capabilities,
        )

    def _rejected(self, rejected: SessionRejected) -> ModelSessionRejected:
        definition = self._selection.definition
        return ModelSessionRejected(
            f"{definition.executable}: the reasoning session was refused "
            f"({rejected}); its answer was discarded and nothing was returned.",
            code=rejected.code,
            runtime=definition.name,
        )

    def _build_argv(self, session: _Session) -> list[str]:
        """The restricted reasoning-child command line for the CLI family.

        The restrictions are constants of the family and come before any
        configured model, so no selection can add, remove or reorder them.
        """
        definition = self._selection.definition
        model = self._selection.model
        if definition.invocation_mode == INVOCATION_MODE_PRINT:
            argv = [
                session.executable,
                PRINT_FLAG,
                *CLAUDE_RESTRICTIONS,
                *STREAM_OUTPUT_FLAGS,
            ]
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

    def __init__(self, runtime: LocalCliModelRuntime, qualify: bool) -> None:
        self._runtime = runtime
        self._qualify = qualify
        self._directory: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> _Session:
        session, self._directory = self._runtime._open_session(self._qualify)
        return session

    def __exit__(self, *exc_info: object) -> None:
        if self._directory is not None:
            self._directory.cleanup()


# -- login summaries ----------------------------------------------------------


def _claude_login_summary(
    definition: RuntimeDefinition, stdout: str, stderr: str
) -> str:
    """Accept only an explicit claude.ai login routed through the first-party API."""

    def refuse(message: str) -> ModelAuthenticationError:
        return ModelAuthenticationError(
            message, runtime=definition.name, stage=STAGE_AUTHENTICATION
        )

    try:
        status = json.loads(stdout)
    except ValueError as error:
        raise refuse(
            f"{definition.executable} auth status did not return the expected JSON "
            "document; authentication could not be established."
        ) from error
    if not isinstance(status, dict):
        raise refuse(
            f"{definition.executable} auth status returned an unexpected document."
        )
    if status.get(CLAUDE_LOGGED_IN_KEY) is not True:
        raise refuse(
            f"{definition.executable} reports it is logged out. Log in with the "
            "local CLI; SDLC will not fall back to an API key."
        )
    # Received values are never quoted, transformed or partially shown: only
    # the fixed rejection category and the allowlisted labels appear.
    method = status.get(CLAUDE_AUTH_METHOD_KEY)
    if method not in CLAUDE_ALLOWED_AUTH_METHODS:
        raise refuse(
            f"{definition.executable}: authentication rejected: unsupported or "
            "unrecognized login method. SDLC requires the claude.ai account login "
            "and never uses API-key or Console billing authentication."
        )
    provider = status.get(CLAUDE_API_PROVIDER_KEY)
    if provider not in CLAUDE_ALLOWED_API_PROVIDERS:
        raise refuse(
            f"{definition.executable}: authentication rejected: unsupported or "
            "unrecognized provider route. SDLC uses only the first-party API."
        )
    return f"{definition.executable}: logged in via {method} ({provider})"


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
            "the ChatGPT account login and never uses API-key authentication.",
            runtime=definition.name,
            stage=STAGE_AUTHENTICATION,
        )
    return f"{definition.executable}: {CODEX_CHATGPT_LOGIN_LINE}"
