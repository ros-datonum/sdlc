"""Local OAuth CLI runtime, exercised without invoking a real model.

Authentication must be positively proven, the reasoning child must run under
the CLI family's restrictions, and both must happen under one session.
"""

import subprocess
from pathlib import Path

import pytest

from sdlc.model_runtime import (
    CLAUDE_RESTRICTIONS,
    CODEX_RESTRICTIONS,
    LocalCliModelRuntime,
    ModelAuthenticationError,
    ModelRuntimeError,
    redact,
)
from sdlc.model_runtime_config import RuntimeDefinition, RuntimeSelection

CLAUDE = RuntimeDefinition(name="claude", executable="claude", invocation_mode="print")
CODEX = RuntimeDefinition(name="codex", executable="codex", invocation_mode="exec")

CLAUDE_OK = (
    '{"loggedIn": true, "authMethod": "claude.ai", "apiProvider": "firstParty", '
    '"subscriptionType": "max", "email": "someone@example.com", "orgId": "org-1"}'
)
CODEX_OK = ("", "Logged in using ChatGPT")  # the real CLI prints it on stderr

PARENT_ENV = {
    "PATH": "/usr/bin",
    "HOME": "/home/someone",
    "FIBERY_TOKEN": "synthetic-fibery-secret",
    "ANTHROPIC_API_KEY": "synthetic-anthropic-key",
    "OPENAI_API_KEY": "synthetic-openai-key",
    "ANTHROPIC_BASE_URL": "https://proxy.invalid",
    "OPENAI_BASE_URL": "https://proxy.invalid",
    "CLAUDE_CODE_USE_BEDROCK": "1",
    "CLAUDECODE": "1",
    "NODE_OPTIONS": "--inspect",
}


class Runner:
    """Records invocations and replays canned CLI results."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, invocation):
        self.calls.append(invocation)
        if not self.results:
            raise AssertionError(f"unexpected invocation: {invocation.argv}")
        outcome = self.results.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        code, out, err = outcome
        return subprocess.CompletedProcess(list(invocation.argv), code, out, err)


def ok(definition):
    return (0, CLAUDE_OK, "") if definition is CLAUDE else (0, *CODEX_OK)


def build(definition, model=None, results=(), installed=True, environment=None):
    selection = RuntimeSelection(role="r", definition=definition, model=model)
    runner = Runner(results)
    runtime = LocalCliModelRuntime(
        selection,
        runner=runner,
        which=lambda name: f"/opt/bin/{name}" if installed else None,
        environment=PARENT_ENV if environment is None else environment,
    )
    return runtime, runner


# -- invocation shape -------------------------------------------------------


def test_claude_is_invoked_in_restricted_print_mode():
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), (0, "hello", "")])

    runtime.run("do the thing")

    argv = runner.calls[1].argv
    assert argv[:2] == ("/opt/bin/claude", "-p")
    assert argv[2:] == CLAUDE_RESTRICTIONS
    assert runner.calls[1].stdin_text == "do the thing"


def test_codex_is_invoked_in_restricted_exec_mode_reading_stdin():
    runtime, runner = build(CODEX, results=[ok(CODEX), (0, "hello", "")])

    runtime.run("do the thing")

    argv = runner.calls[1].argv
    assert argv[:2] == ("/opt/bin/codex", "exec")
    assert argv[2 : 2 + len(CODEX_RESTRICTIONS)] == CODEX_RESTRICTIONS
    assert argv[-3:-1] == ("-C", runner.calls[1].cwd)
    assert argv[-1] == "-"


@pytest.mark.parametrize("definition", [CLAUDE, CODEX], ids=["claude", "codex"])
def test_the_required_restrictions_are_present(definition):
    runtime, runner = build(definition, results=[ok(definition), (0, "ok", "")])

    runtime.run("p")

    argv = list(runner.calls[1].argv)
    if definition is CLAUDE:
        for flag in ("--safe-mode", "--restricted", "--strict-mcp-config"):
            assert flag in argv
        assert argv[argv.index("--tools") + 1] == ""
        assert argv[argv.index("--permission-prompts") + 1] == "none"
    else:
        for flag in ("--ignore-user-config", "--ignore-rules", "--ephemeral"):
            assert flag in argv
        assert argv[argv.index("--sandbox") + 1] == "read-only"
        disabled = {argv[i + 1] for i, a in enumerate(argv) if a == "--disable"}
        assert {"shell_tool", "plugins", "hooks", "multi_agent", "apps"} <= disabled
        overrides = {argv[i + 1] for i, a in enumerate(argv) if a == "-c"}
        assert 'web_search="disabled"' in overrides


@pytest.mark.parametrize("definition", [CLAUDE, CODEX], ids=["claude", "codex"])
def test_no_bypass_or_provider_flags_are_ever_sent(definition):
    forbidden = {
        "--dangerously-skip-permissions",
        "--allow-dangerously-skip-permissions",
        "--dangerously-bypass-approvals-and-sandbox",
        "--dangerously-bypass-hook-trust",
        "--permission-mode",
        "--add-dir",
        "--mcp-config",
        "--api-key",
        "--base-url",
        "--bare",
        "--oss",
        "--search",
        "--settings",
    }
    runtime, runner = build(definition, results=[ok(definition), (0, "ok", "")])

    runtime.run("p")

    assert not forbidden & set(runner.calls[1].argv)
    assert "danger-full-access" not in runner.calls[1].argv


def test_a_configured_model_is_passed_after_the_restrictions():
    runtime, runner = build(
        CLAUDE, model="some-model", results=[ok(CLAUDE), (0, "ok", "")]
    )

    runtime.run("p")

    argv = runner.calls[1].argv
    assert argv[-2:] == ("--model", "some-model")
    assert argv[2:-2] == CLAUDE_RESTRICTIONS


def test_a_model_selection_cannot_alter_the_restrictions():
    """A model string is one argv element; it cannot inject or remove flags."""
    hostile = "opus --tools default --dangerously-skip-permissions"
    runtime, runner = build(CLAUDE, model=hostile, results=[ok(CLAUDE), (0, "", "")])

    runtime.run("p")

    argv = runner.calls[1].argv
    assert argv[argv.index("--model") + 1] == hostile
    assert argv[2:-2] == CLAUDE_RESTRICTIONS
    assert "--dangerously-skip-permissions" not in argv


def test_no_model_flag_is_sent_when_the_cli_should_choose():
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), (0, "ok", "")])

    response = runtime.run("p")

    assert "--model" not in runner.calls[1].argv
    assert response.used_cli_default_model


def test_context_is_prepended_to_the_prompt_on_stdin():
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), (0, "ok", "")])

    runtime.run("PROMPT", context="CONTEXT")

    assert runner.calls[1].stdin_text == "CONTEXT\n\nPROMPT"


def test_the_response_reports_the_runtime_and_model():
    runtime, _ = build(CLAUDE, model="m", results=[ok(CLAUDE), (0, "text", "")])

    response = runtime.run("p")

    assert (response.runtime, response.model, response.text) == ("claude", "m", "text")


# -- one session for the auth check and the model call ------------------------


@pytest.mark.parametrize("definition", [CLAUDE, CODEX], ids=["claude", "codex"])
def test_auth_check_and_inference_share_executable_environment_and_cwd(definition):
    runtime, runner = build(definition, results=[ok(definition), (0, "ok", "")])

    runtime.run("p")

    auth, inference = runner.calls
    assert auth.argv[0] == inference.argv[0] == f"/opt/bin/{definition.executable}"
    assert auth.env == inference.env
    assert auth.cwd == inference.cwd


def test_the_auth_check_uses_the_cli_family_protocol():
    claude, claude_runner = build(CLAUDE, results=[ok(CLAUDE)])
    codex, codex_runner = build(CODEX, results=[ok(CODEX)])

    claude.preflight()
    codex.preflight()

    assert claude_runner.calls[0].argv == (
        "/opt/bin/claude",
        "auth",
        "status",
        "--json",
    )
    assert codex_runner.calls[0].argv == ("/opt/bin/codex", "login", "status")


@pytest.mark.parametrize("definition", [CLAUDE, CODEX], ids=["claude", "codex"])
def test_the_child_environment_is_an_explicit_allowlist(definition):
    runtime, runner = build(definition, results=[ok(definition), (0, "ok", "")])

    runtime.run("p")

    for invocation in runner.calls:
        assert dict(invocation.env) == {"PATH": "/usr/bin", "HOME": "/home/someone"}


def test_credential_store_locations_are_passed_through():
    environment = {**PARENT_ENV, "CLAUDE_CONFIG_DIR": "/cfg", "CODEX_HOME": "/cdx"}
    runtime, runner = build(
        CLAUDE, results=[ok(CLAUDE), (0, "ok", "")], environment=environment
    )

    runtime.run("p")

    env = runner.calls[1].env
    assert env["CLAUDE_CONFIG_DIR"] == "/cfg" and env["CODEX_HOME"] == "/cdx"
    assert "CLAUDECODE" not in env and "ANTHROPIC_API_KEY" not in env


def test_configured_passthrough_adds_only_allowed_names():
    definition = RuntimeDefinition(
        name="claude",
        executable="claude",
        invocation_mode="print",
        environment_passthrough=("HTTPS_PROXY",),
    )
    environment = {**PARENT_ENV, "HTTPS_PROXY": "http://proxy.local:3128"}
    runtime, runner = build(
        definition, results=[ok(CLAUDE), (0, "ok", "")], environment=environment
    )

    runtime.run("p")

    assert runner.calls[1].env["HTTPS_PROXY"] == "http://proxy.local:3128"


def test_a_hand_built_definition_cannot_pass_a_provider_override_through():
    definition = RuntimeDefinition(
        name="claude",
        executable="claude",
        invocation_mode="print",
        environment_passthrough=("ANTHROPIC_BASE_URL",),
    )
    runtime, runner = build(definition, results=[])

    with pytest.raises(ModelRuntimeError, match="ANTHROPIC_BASE_URL"):
        runtime.run("p")

    assert runner.calls == []


def test_the_working_directory_is_a_fresh_temporary_directory_outside_the_repo():
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), (0, "ok", "")])

    runtime.run("p")

    cwd = Path(runner.calls[1].cwd)
    assert not cwd.is_relative_to(Path.cwd())
    assert cwd.name.startswith("sdlc-model-")
    assert not cwd.exists(), "removed once the run is over"


# -- positive authentication ------------------------------------------------


def test_a_claude_subscription_login_on_the_first_party_api_is_accepted():
    summary = build(CLAUDE, results=[ok(CLAUDE)])[0].preflight()

    assert summary == "claude: logged in via claude.ai (firstParty, subscription max)"
    assert "someone@example.com" not in summary and "org-1" not in summary


def test_a_codex_chatgpt_login_is_accepted():
    assert build(CODEX, results=[ok(CODEX)])[0].preflight() == (
        "codex: Logged in using ChatGPT"
    )


def test_a_codex_login_reported_on_stdout_is_also_accepted():
    runtime, _ = build(CODEX, results=[(0, "Logged in using ChatGPT\n", "")])

    assert "ChatGPT" in runtime.preflight()


def test_a_missing_executable_is_an_authentication_error():
    runtime, runner = build(CLAUDE, installed=False)

    with pytest.raises(ModelAuthenticationError, match="not on PATH"):
        runtime.preflight()
    assert runner.calls == []


def test_a_failing_auth_check_is_an_authentication_error():
    runtime, _ = build(CLAUDE, results=[(1, "", "not logged in")])

    with pytest.raises(ModelAuthenticationError, match="not authenticated"):
        runtime.preflight()


def test_claude_logged_out_with_exit_zero_is_rejected():
    status = (
        '{"loggedIn": false, "authMethod": "claude.ai", "apiProvider": "firstParty"}'
    )
    runtime, _ = build(CLAUDE, results=[(0, status, "")])

    with pytest.raises(ModelAuthenticationError, match="logged out"):
        runtime.preflight()


@pytest.mark.parametrize(
    "status",
    ["", "   ", "Logged in as someone", "[]", "42", '{"loggedIn": "true"}'],
    ids=["empty", "blank", "text", "list", "number", "string-bool"],
)
def test_claude_empty_or_malformed_status_is_rejected(status):
    runtime, _ = build(CLAUDE, results=[(0, status, "")])

    with pytest.raises(ModelAuthenticationError):
        runtime.preflight()


@pytest.mark.parametrize(
    "method",
    ["console", "apiKey", "api-key", "oauth-unknown", None],
    ids=["console", "apiKey", "api-key", "unknown", "missing"],
)
def test_claude_non_subscription_login_methods_are_rejected(method):
    import json

    status = json.dumps(
        {"loggedIn": True, "authMethod": method, "apiProvider": "firstParty"}
    )
    runtime, _ = build(CLAUDE, results=[(0, status, "")])

    with pytest.raises(ModelAuthenticationError, match="not a subscription login"):
        runtime.preflight()


@pytest.mark.parametrize(
    "provider",
    ["bedrock", "vertex", "foundry", "thirdParty", None],
    ids=["bedrock", "vertex", "foundry", "thirdParty", "missing"],
)
def test_claude_non_first_party_routing_is_rejected(provider):
    import json

    status = json.dumps(
        {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": provider}
    )
    runtime, _ = build(CLAUDE, results=[(0, status, "")])

    with pytest.raises(ModelAuthenticationError, match="first-party"):
        runtime.preflight()


@pytest.mark.parametrize(
    "output",
    [
        "Logged in using an API key",
        "Not logged in",
        "",
        "Please log in to ChatGPT",
        "chatgpt",
        "Logged in using ChatGPT plan: none. Actually using an API key",
        "Logged in using an API key\nLogged in using ChatGPT",
        "Not logged in\nLogged in using ChatGPT",
    ],
    ids=[
        "api-key",
        "logged-out",
        "empty",
        "mentions-chatgpt",
        "bare-word",
        "prefix-only",
        "contradictory",
        "contradictory-order",
    ],
)
def test_codex_output_without_a_positive_chatgpt_login_line_is_rejected(output):
    runtime, _ = build(CODEX, results=[(0, "", output)])

    with pytest.raises(ModelAuthenticationError, match="ChatGPT login"):
        runtime.preflight()


def test_a_rejected_preflight_launches_no_inference_process():
    runtime, runner = build(CODEX, results=[(0, "", "Logged in using an API key")])

    with pytest.raises(ModelAuthenticationError):
        runtime.run("p")

    assert len(runner.calls) == 1


def test_an_auth_check_timeout_is_reported_without_status_or_secrets():
    expired = subprocess.TimeoutExpired(cmd="claude auth status", timeout=1)
    runtime, _ = build(CLAUDE, results=[expired])

    with pytest.raises(ModelAuthenticationError, match="did not answer") as info:
        runtime.preflight()
    assert "synthetic" not in str(info.value)


def test_an_auth_check_os_error_is_reported_without_details():
    runtime, _ = build(CLAUDE, results=[OSError("token=abc in path")])

    with pytest.raises(ModelAuthenticationError, match="Could not run") as info:
        runtime.preflight()
    assert "abc" not in str(info.value)


def test_authentication_errors_never_quote_the_status_document():
    status = '{"loggedIn": false, "email": "someone@example.com", "token": "abc"}'
    runtime, _ = build(CLAUDE, results=[(0, status, "")])

    with pytest.raises(ModelAuthenticationError) as info:
        runtime.preflight()
    assert "someone@example.com" not in str(info.value)
    assert "abc" not in str(info.value)


def test_an_auth_check_gets_a_short_timeout():
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE)])

    runtime.preflight()

    assert runner.calls[0].timeout == 60


# -- failures ---------------------------------------------------------------


def test_a_non_zero_exit_is_a_runtime_error():
    runtime, _ = build(CLAUDE, results=[ok(CLAUDE), (2, "", "boom")])

    with pytest.raises(ModelRuntimeError, match="exited 2"):
        runtime.run("p")


def test_a_timeout_is_a_runtime_error():
    expired = subprocess.TimeoutExpired(cmd="claude", timeout=1)
    runtime, _ = build(CLAUDE, results=[ok(CLAUDE), expired])

    with pytest.raises(ModelRuntimeError, match="timed out"):
        runtime.run("p")


def test_an_os_error_is_a_runtime_error():
    runtime, _ = build(CLAUDE, results=[ok(CLAUDE), OSError("no exec")])

    with pytest.raises(ModelRuntimeError, match="Could not execute"):
        runtime.run("p")


def test_an_unknown_invocation_mode_is_reported_before_any_process():
    odd = RuntimeDefinition(name="odd", executable="odd", invocation_mode="telepathy")
    runtime, runner = build(odd, results=[])

    with pytest.raises(ModelRuntimeError, match="unknown invocation mode"):
        runtime.run("p")
    assert runner.calls == []


def test_redaction_keeps_ordinary_lines():
    assert redact("plan: max\napi_key: secret-value") == "plan: max"
