"""Local OAuth CLI runtime, exercised without invoking a real model."""

import subprocess

import pytest

from sdlc.model_runtime import (
    LocalCliModelRuntime,
    ModelAuthenticationError,
    ModelRuntimeError,
    redact,
)
from sdlc.model_runtime_config import RuntimeDefinition, RuntimeSelection

CLAUDE = RuntimeDefinition(
    name="claude",
    executable="claude",
    auth_check_args=("auth", "status"),
    invocation_mode="print",
    forbid_console_api_auth=True,
)
CODEX = RuntimeDefinition(
    name="codex",
    executable="codex",
    auth_check_args=("login", "status"),
    invocation_mode="exec",
    require_chatgpt_oauth=True,
)

CLAUDE_OK = '{"loggedIn": true, "authMethod": "claude.ai", "subscriptionType": "max"}'
CODEX_OK = "Logged in using ChatGPT"


class Runner:
    """Records invocations and replays canned CLI results."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, argv, stdin_text, timeout):
        self.calls.append({"argv": list(argv), "stdin": stdin_text, "timeout": timeout})
        if not self.results:
            raise AssertionError(f"unexpected invocation: {argv}")
        outcome = self.results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        code, out, err = outcome
        return subprocess.CompletedProcess(list(argv), code, out, err)


def build(definition, model=None, results=(), installed=True):
    selection = RuntimeSelection(role="r", definition=definition, model=model)
    runner = Runner(results)
    runtime = LocalCliModelRuntime(
        selection, runner=runner, which=lambda _: "/usr/bin/x" if installed else None
    )
    return runtime, runner


# -- invocation shape -------------------------------------------------------


def test_claude_is_invoked_in_print_mode():
    runtime, runner = build(CLAUDE, results=[(0, CLAUDE_OK, ""), (0, "hello", "")])

    runtime.run("do the thing")

    assert runner.calls[1]["argv"] == ["claude", "-p"]
    assert runner.calls[1]["stdin"] == "do the thing"


def test_codex_is_invoked_in_exec_mode_reading_stdin():
    runtime, runner = build(CODEX, results=[(0, CODEX_OK, ""), (0, "hello", "")])

    runtime.run("do the thing")

    assert runner.calls[1]["argv"] == ["codex", "exec", "-"]


def test_a_configured_model_is_passed_as_a_flag():
    runtime, runner = build(
        CLAUDE, model="some-model", results=[(0, CLAUDE_OK, ""), (0, "ok", "")]
    )

    runtime.run("p")

    assert runner.calls[1]["argv"] == ["claude", "-p", "--model", "some-model"]


def test_no_model_flag_is_sent_when_the_cli_should_choose():
    runtime, runner = build(CLAUDE, results=[(0, CLAUDE_OK, ""), (0, "ok", "")])

    response = runtime.run("p")

    assert "--model" not in runner.calls[1]["argv"]
    assert response.used_cli_default_model


def test_no_permission_or_sandbox_flags_are_ever_sent():
    """The runtime spec forbids SDLC passing these."""
    forbidden = {
        "--dangerously-bypass-approvals-and-sandbox",
        "--sandbox",
        "--permission-mode",
        "--allowedTools",
        "--api-key",
        "--base-url",
    }
    for definition in (CLAUDE, CODEX):
        status = CLAUDE_OK if definition is CLAUDE else CODEX_OK
        runtime, runner = build(definition, results=[(0, status, ""), (0, "ok", "")])
        runtime.run("p")
        assert not forbidden & set(runner.calls[1]["argv"])


def test_context_is_prepended_to_the_prompt_on_stdin():
    runtime, runner = build(CLAUDE, results=[(0, CLAUDE_OK, ""), (0, "ok", "")])

    runtime.run("PROMPT", context="CONTEXT")

    assert runner.calls[1]["stdin"] == "CONTEXT\n\nPROMPT"


def test_the_response_reports_the_runtime_and_model():
    runtime, _ = build(CLAUDE, model="m", results=[(0, CLAUDE_OK, ""), (0, "text", "")])

    response = runtime.run("p")

    assert (response.runtime, response.model, response.text) == ("claude", "m", "text")


# -- preflight --------------------------------------------------------------


def test_a_missing_executable_is_an_authentication_error():
    runtime, _ = build(CLAUDE, installed=False)

    with pytest.raises(ModelAuthenticationError, match="not on PATH"):
        runtime.preflight()


def test_a_failing_auth_check_is_an_authentication_error():
    runtime, _ = build(CLAUDE, results=[(1, "", "not logged in")])

    with pytest.raises(ModelAuthenticationError, match="not authenticated"):
        runtime.preflight()


def test_the_auth_check_uses_the_configured_command():
    runtime, runner = build(CODEX, results=[(0, CODEX_OK, "")])

    runtime.preflight()

    assert runner.calls[0]["argv"] == ["codex", "login", "status"]


def test_claude_console_or_api_key_auth_is_refused():
    runtime, _ = build(CLAUDE, results=[(0, '{"authMethod": "console"}', "")])

    with pytest.raises(ModelAuthenticationError, match="subscription login"):
        runtime.preflight()


def test_codex_without_chatgpt_oauth_is_refused():
    runtime, _ = build(CODEX, results=[(0, "Logged in using an API key", "")])

    with pytest.raises(ModelAuthenticationError, match="ChatGPT OAuth"):
        runtime.preflight()


def test_a_run_will_not_proceed_when_authentication_is_unusable():
    """No API-key fallback exists; the call simply fails."""
    runtime, runner = build(CODEX, results=[(0, "Logged in using an API key", "")])

    with pytest.raises(ModelAuthenticationError):
        runtime.run("p")

    assert len(runner.calls) == 1


def test_preflight_redacts_credential_shaped_lines():
    status = "Logged in using ChatGPT\naccess_token: abc123\nplan: pro"

    assert "abc123" not in build(CODEX, results=[(0, status, "")])[0].preflight()


# -- failures ---------------------------------------------------------------


def test_a_non_zero_exit_is_a_runtime_error():
    runtime, _ = build(CLAUDE, results=[(0, CLAUDE_OK, ""), (2, "", "boom")])

    with pytest.raises(ModelRuntimeError, match="exited 2"):
        runtime.run("p")


def test_a_timeout_is_a_runtime_error():
    expired = subprocess.TimeoutExpired(cmd="claude", timeout=1)
    runtime, _ = build(CLAUDE, results=[(0, CLAUDE_OK, ""), expired])

    with pytest.raises(ModelRuntimeError, match="timed out"):
        runtime.run("p")


def test_an_os_error_is_a_runtime_error():
    runtime, _ = build(CLAUDE, results=[(0, CLAUDE_OK, ""), OSError("no exec")])

    with pytest.raises(ModelRuntimeError, match="Could not execute"):
        runtime.run("p")


def test_an_unknown_invocation_mode_is_reported():
    odd = RuntimeDefinition(
        name="odd", executable="odd", auth_check_args=(), invocation_mode="telepathy"
    )
    runtime, _ = build(odd, results=[])

    with pytest.raises(ModelRuntimeError, match="unknown invocation mode"):
        runtime.run("p")


def test_redaction_keeps_ordinary_lines():
    assert redact("plan: max\napi_key: secret-value") == "plan: max"
