"""Model execution through locally authenticated CLIs.

Implements Local-OAuth-Model-Runtime-Spec-v0.1. The SDLC application never
authenticates with a model provider: it shells out to the user's own `claude`
or `codex` CLI, which already holds a subscription/OAuth session.

There is deliberately no API-key path, no provider SDK, and no fallback. When
local authentication is unusable the call fails.
"""

from __future__ import annotations

import shutil
import subprocess
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from sdlc.model_runtime_config import RuntimeDefinition, RuntimeSelection

INVOCATION_MODE_PRINT = "print"
INVOCATION_MODE_EXEC = "exec"

MODEL_FLAG = "--model"
PRINT_FLAG = "-p"
EXEC_SUBCOMMAND = "exec"
STDIN_ARGUMENT = "-"

DEFAULT_TIMEOUT_SECONDS = 900

# Substrings that mark an unusable authentication mode. The spec requires
# subscription/ChatGPT OAuth login and forbids API-key or Console billing auth.
CONSOLE_API_AUTH_MARKERS = ("api key", "console", "api-billing", "billing account")
CHATGPT_OAUTH_MARKERS = ("chatgpt",)

# Never echoed back to the caller: CLI auth output can name the account.
CREDENTIAL_MARKERS = ("token", "key", "secret", "bearer")


class ModelRuntimeError(Exception):
    """A model could not be executed through the local CLI."""


class ModelAuthenticationError(ModelRuntimeError):
    """The local CLI is missing or not authenticated in an allowed mode."""


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
    exists so the RAW processor's reasoning step can be replaced in tests.
    """

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        """Execute the prompt and return the response text."""


CommandRunner = Callable[[Sequence[str], str, int], subprocess.CompletedProcess[str]]


def _run_command(
    argv: Sequence[str], stdin_text: str, timeout: int
) -> subprocess.CompletedProcess[str]:
    # argv is built from configuration, never from a shell string.
    return subprocess.run(
        list(argv),
        input=stdin_text,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


class LocalCliModelRuntime:
    """Runs a prompt through a locally authenticated `claude` or `codex` CLI."""

    def __init__(
        self,
        selection: RuntimeSelection,
        runner: CommandRunner = _run_command,
        which: Callable[[str], str | None] = shutil.which,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._selection = selection
        self._run = runner
        self._which = which
        self._timeout = timeout_seconds

    @property
    def selection(self) -> RuntimeSelection:
        return self._selection

    def preflight(self) -> str:
        """Check the executable exists and is authenticated in an allowed mode.

        Returns the auth status text with anything credential-shaped removed.
        """
        definition = self._selection.definition
        if self._which(definition.executable) is None:
            raise ModelAuthenticationError(
                f"The {definition.name!r} runtime needs the {definition.executable!r} "
                "executable, which is not on PATH."
            )
        if not definition.auth_check_args:
            return ""

        result = self._run(
            [definition.executable, *definition.auth_check_args], "", self._timeout
        )
        status = f"{result.stdout}\n{result.stderr}".strip()
        if result.returncode != 0:
            raise ModelAuthenticationError(
                f"{definition.executable} is not authenticated "
                f"({' '.join(definition.auth_check_args)} exited "
                f"{result.returncode}). Log in with the local CLI; SDLC will not "
                "fall back to an API key."
            )
        _check_auth_mode(definition, status)
        return redact(status)

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        """Execute the prompt through the local CLI."""
        self.preflight()
        argv = self._build_argv()
        stdin_text = f"{context}\n\n{prompt}" if context else prompt
        try:
            result = self._run(argv, stdin_text, self._timeout)
        except subprocess.TimeoutExpired as error:
            raise ModelRuntimeError(
                f"{self._selection.definition.executable} timed out after "
                f"{self._timeout}s."
            ) from error
        except OSError as error:
            raise ModelRuntimeError(
                f"Could not execute {self._selection.definition.executable}: {error}"
            ) from error

        if result.returncode != 0:
            raise ModelRuntimeError(
                f"{self._selection.definition.executable} exited "
                f"{result.returncode}: {redact(result.stderr)[:500]}"
            )
        return ModelResponse(
            text=result.stdout,
            runtime=self._selection.definition.name,
            model=self._selection.model,
        )

    def _build_argv(self) -> list[str]:
        """Build the CLI invocation.

        The spec forbids passing permission-mode, sandbox or approval flags from
        SDLC configuration, so none are ever added here.
        """
        definition = self._selection.definition
        model = self._selection.model
        if definition.invocation_mode == INVOCATION_MODE_PRINT:
            argv = [definition.executable, PRINT_FLAG]
        elif definition.invocation_mode == INVOCATION_MODE_EXEC:
            argv = [definition.executable, EXEC_SUBCOMMAND]
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


def _check_auth_mode(definition: RuntimeDefinition, status: str) -> None:
    """Reject authentication modes the runtime spec disallows."""
    lowered = status.lower()
    if definition.forbid_console_api_auth and any(
        marker in lowered for marker in CONSOLE_API_AUTH_MARKERS
    ):
        raise ModelAuthenticationError(
            f"{definition.executable} appears to be authenticated through an API "
            "key or Console billing account. SDLC requires subscription login."
        )
    if definition.require_chatgpt_oauth and not any(
        marker in lowered for marker in CHATGPT_OAUTH_MARKERS
    ):
        raise ModelAuthenticationError(
            f"{definition.executable} is not logged in with ChatGPT OAuth. SDLC "
            "will not use API-key authentication."
        )


def redact(text: str) -> str:
    """Drop lines that look like they carry a credential."""
    return "\n".join(
        line
        for line in text.splitlines()
        if not any(marker in line.lower() for marker in CREDENTIAL_MARKERS)
    ).strip()
