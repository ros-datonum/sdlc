"""Local OAuth CLI runtime, exercised without invoking a real model.

Authentication must be positively proven, the reasoning child must run under
the CLI family's restrictions, both must happen under one session, a family
without a verified boundary must be refused before any subprocess, and
failure diagnostics must never carry subprocess output.
"""

import json
import logging
import subprocess
from pathlib import Path

import pytest

from processor_fake import FakeModelRuntime, build_workspace, candidate, model_output
from sdlc.model_runtime import (
    CLAUDE_RESTRICTIONS,
    RUNTIME_ISOLATION_UNAVAILABLE,
    LocalCliModelRuntime,
    ModelAuthenticationError,
    ModelRuntimeError,
    RuntimeIsolationUnavailable,
)
from sdlc.model_runtime_config import (
    RAW_REQUIREMENT_PROCESSOR_ROLE,
    RuntimeDefinition,
    RuntimeSelection,
    load_model_runtime_config,
    runtime_definition,
    select_runtime,
)
from sdlc.raw_processor import process_raw_requirement
from sdlc.results import ProcessResultCode
from standard_fake import set_state

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


def build(
    definition, model=None, results=(), installed=True, environment=None, which=None
):
    selection = RuntimeSelection(role="r", definition=definition, model=model)
    return build_from(selection, results, installed, environment, which)


def build_from(selection, results=(), installed=True, environment=None, which=None):
    runner = Runner(results)
    runtime = LocalCliModelRuntime(
        selection,
        runner=runner,
        which=which or (lambda name: f"/opt/bin/{name}" if installed else None),
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


def test_the_required_claude_restrictions_are_present():
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), (0, "ok", "")])

    runtime.run("p")

    argv = list(runner.calls[1].argv)
    for flag in ("--safe-mode", "--restricted", "--strict-mcp-config"):
        assert flag in argv
    assert argv[argv.index("--tools") + 1] == ""
    assert argv[argv.index("--permission-prompts") + 1] == "none"


@pytest.mark.parametrize("definition", [CLAUDE], ids=["claude"])
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


@pytest.mark.parametrize("definition", [CLAUDE], ids=["claude"])
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


@pytest.mark.parametrize("definition", [CLAUDE], ids=["claude"])
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

    assert summary == "claude: logged in via claude.ai (firstParty)"
    assert "max" not in summary, "account fields are not reported"
    assert "someone@example.com" not in summary and "org-1" not in summary


def test_a_codex_chatgpt_login_is_accepted_but_reported_as_not_eligible():
    summary = build(CODEX, results=[ok(CODEX)])[0].preflight()

    assert summary.startswith("codex: Logged in using ChatGPT")
    assert "not eligible for SDLC reasoning execution" in summary
    assert RUNTIME_ISOLATION_UNAVAILABLE in summary


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

    with pytest.raises(ModelAuthenticationError, match="unrecognized login method"):
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

    with pytest.raises(ModelAuthenticationError, match="unrecognized provider route"):
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
    status = '{"loggedIn": true, "authMethod": "console", "apiProvider": "firstParty"}'
    runtime, runner = build(CLAUDE, results=[(0, status, "")])

    with pytest.raises(ModelAuthenticationError):
        runtime.run("p")

    assert len(runner.calls) == 1


def test_an_auth_check_timeout_is_reported_without_status_or_secrets():
    expired = subprocess.TimeoutExpired(
        cmd="claude auth status", timeout=1, output="synthetic-status", stderr="s"
    )
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


# -- Codex execution is refused before any subprocess --------------------------


def assert_refused(runtime, runner, which_calls=None):
    with pytest.raises(RuntimeIsolationUnavailable) as info:
        runtime.run("PROMPT", context="CONTEXT")
    message = str(info.value)
    assert message.startswith(RUNTIME_ISOLATION_UNAVAILABLE)
    assert "Codex" in message and "not currently established" in message
    assert "codex-cli 0.146.0" in message and "local-file" in message
    assert "No model was invoked" in message and "select a supported runtime" in message
    assert "not authenticated" not in message and "not on PATH" not in message
    assert runner.calls == [], "no auth or inference subprocess"
    if which_calls is not None:
        assert which_calls == [], "the executable is not even looked up"
    assert (info.value.runtime, info.value.stage) == ("codex", "inference")
    return info.value


def test_a_direct_codex_library_invocation_is_refused_without_any_subprocess():
    looked_up = []
    runtime, runner = build(
        CODEX,
        results=[ok(CODEX), (0, "hello", "")],
        which=lambda n: looked_up.append(n),
    )

    assert_refused(runtime, runner, looked_up)
    assert isinstance(assert_refused(runtime, runner), ModelRuntimeError)


def test_codex_is_refused_even_when_no_executable_is_installed():
    """The refusal is not a missing-executable or authentication failure."""
    runtime, runner = build(CODEX, installed=False)

    assert_refused(runtime, runner)


CONFIG_WITH_CODEX_DEFAULT = {
    "transport": "local_cli_oauth",
    "default": {"runtime": "codex", "model": "some-codex-model"},
    "runtimes": {
        "claude": {"executable": "claude", "invocation_mode": "print"},
        "codex": {"executable": "codex", "invocation_mode": "exec"},
    },
    "roles": {"reviewer": {"runtime": "codex"}, "processor": {}},
}


@pytest.mark.parametrize(
    ("role", "override"),
    [("processor", None), ("reviewer", None), ("processor", "codex")],
    ids=["project-default", "role", "explicit-override"],
)
def test_every_configuration_path_to_codex_is_refused(role, override):
    selection = select_runtime(
        CONFIG_WITH_CODEX_DEFAULT, role, runtime_override=override
    )
    assert selection.definition.name == "codex", "the selection stays representable"
    runtime, runner = build_from(selection, results=[ok(CODEX), (0, "hello", "")])

    assert_refused(runtime, runner)


def test_the_shipped_configuration_still_lets_codex_be_selected_but_not_executed():
    config = load_model_runtime_config(Path("config/sdlc.toml"))
    selection = select_runtime(
        config, RAW_REQUIREMENT_PROCESSOR_ROLE, runtime_override="codex"
    )
    runtime, runner = build_from(selection, results=[ok(CODEX), (0, "hello", "")])

    assert_refused(runtime, runner)


def test_no_fallback_runtime_is_attempted_when_codex_is_refused():
    looked_up = []
    runtime, runner = build(
        CODEX,
        results=[ok(CLAUDE), (0, "hello", "")],
        which=lambda n: looked_up.append(n),
    )

    assert_refused(runtime, runner, looked_up)
    assert "claude" not in looked_up


def test_a_newer_reported_codex_version_does_not_bypass_the_gate():
    newer = RuntimeDefinition(
        name="codex", executable="codex-9.9.9", invocation_mode="exec"
    )
    runtime, runner = build(
        newer,
        results=[(0, "codex-cli 9.9.9", ""), ok(CODEX), (0, "hello", "")],
        which=lambda n: f"/opt/bin/{n}",
    )

    assert_refused(runtime, runner)


def test_ordinary_configuration_cannot_disable_the_gate():
    config = {
        **CONFIG_WITH_CODEX_DEFAULT,
        "runtimes": {
            "codex": {
                "executable": "codex",
                "invocation_mode": "exec",
                "isolation_verified": True,
                "allow_unsafe": True,
                "force": True,
                "environment_passthrough": ["HTTPS_PROXY"],
            }
        },
    }
    selection = RuntimeSelection(
        role="r", definition=runtime_definition(config, "codex"), model="m"
    )
    runtime, runner = build_from(selection, results=[ok(CODEX), (0, "hello", "")])

    assert_refused(runtime, runner)


def test_a_codex_backed_runtime_does_not_block_a_resume_that_needs_no_model():
    """The gate sits where a model is invoked, not where the runtime is built."""
    ws, raw, _ = build_workspace()
    first = process_raw_requirement(
        ws, FakeModelRuntime([model_output([candidate()])]), raw.id
    )
    assert first.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    set_state(ws, raw, "Process")
    runtime, runner = build(CODEX, results=[])

    resumed = process_raw_requirement(ws, runtime, raw.id)

    assert resumed.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert not resumed.model_invoked
    assert runner.calls == []


def test_a_codex_backed_processor_run_that_needs_the_model_reports_the_refusal():
    ws, raw, _ = build_workspace()
    runtime, runner = build(CODEX, results=[])

    result = process_raw_requirement(ws, runtime, raw.id)

    assert result.code is ProcessResultCode.MODEL_RUNTIME_FAILED
    assert any(RUNTIME_ISOLATION_UNAVAILABLE in detail for detail in result.details)
    assert runner.calls == []
    assert ws.requirements[raw.id].state == "Process"


# -- failure diagnostics carry no subprocess output --------------------------

PROMPT_MARKER = "REQ-PRIVATE-TEXT-7f21c"
TOKEN_MARKER = "tok-synthetic-3b9c4d5e"
EMAIL_MARKER = "someone.private@example.com"
STATUS_MARKER = '{"loggedIn": false, "email": "someone.private@example.com"}'
MARKERS = (PROMPT_MARKER, TOKEN_MARKER, EMAIL_MARKER, STATUS_MARKER)
NOISE = f"user\n{PROMPT_MARKER}\n{TOKEN_MARKER}\n{EMAIL_MARKER}\n{STATUS_MARKER}"


def assert_private(error, caplog):
    text = str(error) + repr(error) + caplog.text
    for marker in MARKERS:
        assert marker not in text, marker
    assert error.runtime == "claude"
    assert error.stage in {"authentication", "inference"}


def test_a_nonzero_inference_exit_reports_only_the_classification(caplog):
    caplog.set_level(logging.DEBUG)
    runtime, _ = build(CLAUDE, results=[ok(CLAUDE), (2, NOISE, NOISE)])

    with pytest.raises(ModelRuntimeError, match="exited 2") as info:
        runtime.run(PROMPT_MARKER, context=TOKEN_MARKER)

    assert_private(info.value, caplog)
    assert (info.value.stage, info.value.exit_code) == ("inference", 2)


def test_a_nonzero_auth_exit_reports_only_the_classification(caplog):
    caplog.set_level(logging.DEBUG)
    runtime, _ = build(CLAUDE, results=[(1, NOISE, NOISE)])

    with pytest.raises(ModelAuthenticationError, match="exited 1") as info:
        runtime.run(PROMPT_MARKER)

    assert_private(info.value, caplog)
    assert (info.value.stage, info.value.exit_code) == ("authentication", 1)


def test_a_rejected_status_document_is_never_quoted(caplog):
    caplog.set_level(logging.DEBUG)
    status = json.dumps(
        {"loggedIn": True, "authMethod": EMAIL_MARKER, "apiProvider": PROMPT_MARKER}
    )
    runtime, _ = build(CLAUDE, results=[(0, status, NOISE)])

    with pytest.raises(ModelAuthenticationError, match="unrecognized login") as info:
        runtime.run(PROMPT_MARKER)

    assert_private(info.value, caplog)


@pytest.mark.parametrize("stage", ["authentication", "inference"])
def test_a_timeout_reports_only_the_classification(caplog, stage):
    caplog.set_level(logging.DEBUG)
    expired = subprocess.TimeoutExpired(
        cmd=["claude", PROMPT_MARKER], timeout=1, output=NOISE, stderr=NOISE
    )
    results = [expired] if stage == "authentication" else [ok(CLAUDE), expired]
    runtime, _ = build(CLAUDE, results=results)

    with pytest.raises(ModelRuntimeError, match="did not answer|timed out") as info:
        runtime.run(PROMPT_MARKER, context=TOKEN_MARKER)

    assert_private(info.value, caplog)
    assert info.value.stage == stage


@pytest.mark.parametrize("stage", ["authentication", "inference"])
def test_an_os_error_reports_only_its_type(caplog, stage):
    caplog.set_level(logging.DEBUG)
    failure = PermissionError(13, NOISE, PROMPT_MARKER)
    results = [failure] if stage == "authentication" else [ok(CLAUDE), failure]
    runtime, _ = build(CLAUDE, results=results)

    with pytest.raises(ModelRuntimeError, match="PermissionError") as info:
        runtime.run(PROMPT_MARKER, context=TOKEN_MARKER)

    assert_private(info.value, caplog)
    assert info.value.stage == stage


# -- short, plain unknown status values are never echoed -----------------------

SHORT_MARKER = "zq7private"


def _refusing_status(field):
    status = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}
    status[field] = SHORT_MARKER
    return json.dumps(status)


@pytest.mark.parametrize(
    ("field", "category"),
    [("authMethod", "login method"), ("apiProvider", "provider route")],
)
def test_a_short_unknown_status_value_is_rejected_without_being_echoed(
    caplog, field, category
):
    caplog.set_level(logging.DEBUG)
    runtime, runner = build(CLAUDE, results=[(0, _refusing_status(field), "")])

    with pytest.raises(ModelAuthenticationError) as info:
        runtime.run("p")

    assert f"unsupported or unrecognized {category}" in str(info.value)
    assert SHORT_MARKER not in str(info.value) + repr(info.value) + caplog.text
    assert len(runner.calls) == 1, "rejected before inference"


@pytest.mark.parametrize("field", ["authMethod", "apiProvider"])
def test_a_short_unknown_status_value_stays_out_of_results_and_cli_output(
    caplog, field
):
    import io

    from sdlc import cli

    caplog.set_level(logging.DEBUG)
    ws, raw, _ = build_workspace()
    runtime, _ = build(CLAUDE, results=[(0, _refusing_status(field), "")])

    result = process_raw_requirement(ws, runtime, raw.id)
    rendered = io.StringIO()
    cli.render_process_result(result, rendered)

    assert result.code is ProcessResultCode.MODEL_RUNTIME_FAILED
    surfaces = " ".join((*result.details, result.message, rendered.getvalue()))
    assert SHORT_MARKER not in surfaces + caplog.text
    assert "unsupported or unrecognized" in surfaces


def test_the_known_valid_status_is_still_accepted_as_a_control():
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), (0, "answer", "")])

    assert runtime.run("p").text == "answer"
    assert len(runner.calls) == 2
