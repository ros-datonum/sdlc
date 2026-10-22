"""Local-OAuth-Model-Runtime-Claude-2.1.306-Amendment-v0.1, offline.

Executable identity, the fixed child environment and the stream-json session
validation of the Claude reasoning child. Identity and early termination run
against real files and real child processes (harmless stand-ins); session
validation runs the production parser on synthetic streams. No model runs.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sys
import time
from pathlib import Path

import pytest

from sdlc.claude_session import (
    ExpectedSession,
    SessionRejected,
    validate_stream,
)
from sdlc.model_runtime import (
    LocalCliModelRuntime,
    ModelRuntimeError,
    ModelSessionRejected,
    RuntimeIsolationUnavailable,
)
from sdlc.model_runtime_config import (
    ModelRuntimeConfigError,
    QualifiedBinary,
    RuntimeDefinition,
    RuntimeSelection,
    load_model_runtime_config,
    runtime_definition,
)
from sdlc.model_runtime_environment import (
    FIXED_CHILD_ENVIRONMENT,
    DeniedEnvironmentName,
    child_environment,
    require_allowed,
)
from test_model_runtime import (
    CLAUDE,
    CLAUDE_OK,
    CODEX,
    PARENT_ENV,
    QUALIFIED_CAPABILITIES,
    QUALIFIED_PLUGINS,
    QUALIFIED_SHA256,
    QUALIFIED_VERSION,
    Runner,
    answer,
    build,
    claude_stream,
    ok,
)

SECRET_ANSWER = "ANSWER-8f2c-private-model-text"
CAPS_LINE = "\nprotocol_capabilities = []"
SECRET_PROMPT = "PROMPT-41d0-private-requirement"
CWD = "/private/tmp/sdlc-model-x"
EXPECTED = ExpectedSession(
    cwd=CWD,
    version=QUALIFIED_VERSION,
    builtin_plugins=QUALIFIED_PLUGINS,
    protocol_capabilities=QUALIFIED_CAPABILITIES,
)


def stream(text=SECRET_ANSWER, **init_changes):
    return claude_stream(CWD, text, **init_changes)


def events_of(text):
    return [json.loads(line) for line in text.splitlines()]


def lines_of(events):
    return "".join(json.dumps(event) + "\n" for event in events)


def refused(stdout, code):
    with pytest.raises(SessionRejected) as caught:
        validate_stream(stdout, EXPECTED)
    assert caught.value.code == code, caught.value
    assert SECRET_ANSWER not in str(caught.value)
    return caught.value


# -- P, G: the qualified session ------------------------------------------------------


def test_a_qualified_stream_yields_exactly_the_answer_text():
    assert (
        validate_stream(stream("the answer\nline 2"), EXPECTED) == "the answer\nline 2"
    )


def test_the_runtime_returns_only_the_answer_never_the_event_stream():
    runtime, _ = build(CLAUDE, results=[ok(CLAUDE), answer("plain answer")])

    response = runtime.run("p")

    assert response.text == "plain answer"
    assert (response.runtime, response.model) == ("claude", None)


def test_the_exact_plugin_set_in_any_order_is_accepted():
    plugins = [
        {"name": name, "path": "builtin", "source": f"{name}@builtin"}
        for name in sorted(QUALIFIED_PLUGINS, reverse=True)
    ]
    assert validate_stream(stream(plugins=plugins), EXPECTED) == SECRET_ANSWER


def test_lifecycle_notices_and_thinking_are_accepted():
    init, assistant, result = events_of(stream())
    assistant["message"]["content"].insert(0, {"type": "thinking", "thinking": "..."})
    events = [
        init,
        {"type": "system", "subtype": "thinking_tokens", "session_id": "s-1"},
        {"type": "rate_limit_event", "session_id": "s-1"},
        assistant,
        result,
    ]
    assert validate_stream(lines_of(events), EXPECTED) == SECRET_ANSWER


# -- H, I: plugins -----------------------------------------------------------------------


def plugin(name, path="builtin"):
    return {"name": name, "path": path, "source": f"{name}@{path}"}


@pytest.mark.parametrize(
    "plugins",
    [
        [plugin(n) for n in sorted(QUALIFIED_PLUGINS)]
        + [plugin("cc-plugin-telemetry")],
        [plugin(n) for n in sorted(QUALIFIED_PLUGINS)]
        + [plugin("cc-plugin-mods-guide")],
        [plugin("cc-plugin-agents-md")],
        [],
        [plugin(n) for n in sorted(QUALIFIED_PLUGINS)]
        + [plugin("cc-plugin-agents-md")],
        [plugin("cc-plugin-agents-md"), plugin("cc-plugin-plugin-authoring", "user")],
        [
            plugin("cc-plugin-agents-md"),
            {
                "name": "cc-plugin-plugin-authoring",
                "path": "/tmp/a-plugin-dir",
                "source": "cc-plugin-plugin-authoring@builtin",
            },
        ],
        [plugin("cc-plugin-agents-md"), {"name": "cc-plugin-plugin-authoring"}],
        "not-a-list",
    ],
    ids=[
        "telemetry-present",
        "unexpected-builtin",
        "one-missing",
        "none",
        "duplicate",
        "not-builtin",
        "path-not-builtin",
        "no-source",
        "malformed",
    ],
)
def test_anything_but_the_exact_qualified_plugin_set_is_refused(plugins):
    error = refused(
        stream(plugins=plugins),
        "PLUGIN_NOT_QUALIFIED" if plugins != "not-a-list" else "INIT_INVALID",
    )
    assert "@" not in str(error) or "builtin" in str(error)


# -- J, K, L and the rest of the init record -------------------------------------------


@pytest.mark.parametrize("field", ["tools", "mcp_servers", "skills", "slash_commands"])
def test_a_nonempty_capability_list_is_refused(field):
    refused(stream(**{field: ["Read"]}), "CAPABILITY_EXPOSED")


@pytest.mark.parametrize("field", ["tools", "mcp_servers", "skills", "slash_commands"])
def test_a_missing_capability_list_is_refused(field):
    init, *rest = events_of(stream())
    del init[field]
    refused(lines_of([init, *rest]), "CAPABILITY_EXPOSED")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("memory_paths", {"auto": "/home/someone/.claude/projects/x/memory"}),
        ("additional_directories", ["/home/someone"]),
        ("plugin_errors", [{"plugin": "x"}]),
        ("plugin_warnings", [{"plugin": "x"}]),
        ("mcp_server_errors", [{"name": "x"}]),
        ("terminal_slash_commands", ["x"]),
    ],
)
def test_an_optional_capability_field_is_refused_when_present(field, value):
    refused(stream(**{field: value}), "CAPABILITY_EXPOSED")


def test_an_api_key_source_is_refused():
    refused(stream(apiKeySource="ANTHROPIC_API_KEY"), "AUTHENTICATION_NOT_QUALIFIED")


@pytest.mark.parametrize("value", [False, None, "true"])
def test_analytics_not_reported_disabled_is_refused(value):
    refused(stream(analytics_disabled=value), "TELEMETRY_NOT_DISABLED")


def test_another_build_version_is_refused():
    refused(stream(claude_code_version="9.9.10"), "BINARY_NOT_QUALIFIED")


def test_an_init_for_another_directory_is_refused():
    refused(claude_stream("/home/someone/project", SECRET_ANSWER), "INIT_INVALID")


# -- M, N, O: the event stream -------------------------------------------------------------


@pytest.mark.parametrize("kind", ["tool_use", "server_tool_use", "mcp_tool_use"])
def test_a_tool_use_is_refused(kind):
    init, assistant, result = events_of(stream())
    assistant["message"]["content"].append({"type": kind, "name": "Read", "input": {}})
    refused(lines_of([init, assistant, result]), "TOOL_USE_ATTEMPTED")


@pytest.mark.parametrize(
    "event",
    [
        {"type": "user", "session_id": "s-1", "message": {"content": []}},
        {"type": "stream_event", "session_id": "s-1"},
        {"type": "tool_progress", "session_id": "s-1"},
        {"type": "system", "subtype": "hook_started", "session_id": "s-1"},
        {"type": "system", "subtype": "hook_response", "session_id": "s-1"},
        {"type": "system", "subtype": "memory_recall", "session_id": "s-1"},
        {"type": "system", "subtype": "file_attachments_missing", "session_id": "s-1"},
        {"type": "system", "subtype": "task_started", "session_id": "s-1"},
        {"type": "system", "subtype": "model_fallback", "session_id": "s-1"},
        {"type": "system", "subtype": "permission_denied", "session_id": "s-1"},
    ],
    ids=lambda e: f"{e['type']}/{e.get('subtype')}",
)
def test_an_event_outside_the_closed_schema_is_refused(event):
    init, assistant, result = events_of(stream())
    refused(lines_of([init, event, assistant, result]), "UNEXPECTED_EVENT")


def test_a_missing_init_is_refused():
    _, assistant, result = events_of(stream())
    refused(lines_of([assistant, result]), "INIT_MISSING")


def test_an_empty_stream_is_refused():
    refused("", "INIT_MISSING")


def test_a_system_event_before_init_is_refused():
    init, assistant, result = events_of(stream())
    status = {"type": "system", "subtype": "status", "session_id": "s-1"}
    refused(lines_of([status, init, assistant, result]), "INIT_MISSING")


def test_a_second_init_is_refused():
    init, assistant, result = events_of(stream())
    refused(lines_of([init, init, assistant, result]), "INIT_DUPLICATED")


def test_an_event_of_another_session_is_refused():
    init, assistant, result = events_of(stream())
    assistant["session_id"] = "s-2"
    refused(lines_of([init, assistant, result]), "SESSION_MISMATCH")


@pytest.mark.parametrize("text", ["plain text answer", "[1, 2]", "{not json"])
def test_malformed_output_is_refused(text):
    refused(text + "\n", "MALFORMED_EVENT")


def test_plain_text_answer_without_a_stream_is_refused_by_the_runtime():
    runtime, _ = build(CLAUDE, results=[ok(CLAUDE), (0, SECRET_ANSWER, "")])

    with pytest.raises(ModelSessionRejected) as caught:
        runtime.run("p")

    assert caught.value.code == "MALFORMED_EVENT"
    assert SECRET_ANSWER not in str(caught.value)


def test_a_missing_result_is_refused():
    init, assistant, _ = events_of(stream())
    refused(lines_of([init, assistant]), "RESULT_MISSING")


def test_an_event_after_the_result_is_refused():
    init, assistant, result = events_of(stream())
    refused(lines_of([init, assistant, result, assistant]), "EVENT_AFTER_RESULT")


@pytest.mark.parametrize(
    "change",
    [{"subtype": "error_during_execution"}, {"is_error": True}, {"is_error": None}],
)
def test_an_unsuccessful_result_is_refused(change):
    init, assistant, result = events_of(stream())
    refused(lines_of([init, assistant, {**result, **change}]), "RESULT_NOT_SUCCESS")


@pytest.mark.parametrize("value", ["", "   ", None, 7])
def test_an_empty_answer_is_refused(value):
    init, assistant, result = events_of(stream())
    refused(lines_of([init, assistant, {**result, "result": value}]), "RESULT_EMPTY")


# -- R: no model output or prompt in any diagnostic ------------------------------------------


def test_a_refused_session_never_reports_the_answer_or_the_prompt(caplog):
    bad = lambda inv: (
        0,
        claude_stream(inv.cwd, SECRET_ANSWER, plugins=[plugin("evil-plugin")]),
        SECRET_ANSWER,
    )
    runtime, _ = build(CLAUDE, results=[ok(CLAUDE), bad])

    with caplog.at_level(logging.DEBUG), pytest.raises(ModelSessionRejected) as caught:
        runtime.run(SECRET_PROMPT, context=SECRET_PROMPT)

    text = f"{caught.value} {caught.value!r} {caplog.text}"
    assert caught.value.code == "PLUGIN_NOT_QUALIFIED"
    assert "evil-plugin" in str(caught.value)
    for secret in (SECRET_ANSWER, SECRET_PROMPT):
        assert secret not in text


def test_an_unreportable_received_name_is_not_quoted():
    error = refused(
        stream(
            plugins=[plugin(n) for n in sorted(QUALIFIED_PLUGINS)]
            + [
                {
                    "name": SECRET_ANSWER + " x",
                    "path": "builtin",
                    "source": SECRET_ANSWER + " x@builtin",
                }
            ]
        ),
        "PLUGIN_NOT_QUALIFIED",
    )
    assert "(unrecognized)" in str(error)


# -- A-D, S: executable identity ------------------------------------------------------------


@pytest.fixture
def install(tmp_path):
    """Two builds of a stand-in CLI and the `claude` symlink naming one."""
    versions = tmp_path / "versions"
    versions.mkdir()
    builds = {}
    for name in ("v1", "v2"):
        path = versions / name
        path.write_text(f"#!/bin/sh\n# stand-in build {name}\n")
        path.chmod(0o755)
        builds[name] = path
    link = tmp_path / "bin" / "claude"
    link.parent.mkdir()
    link.symlink_to(builds["v1"])
    return link, builds


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def runtime_on(link, qualified_sha, results):
    definition = RuntimeDefinition(
        name="claude",
        executable="claude",
        invocation_mode="print",
        qualified_binary=QualifiedBinary(
            qualified_sha, QUALIFIED_VERSION, QUALIFIED_PLUGINS, QUALIFIED_CAPABILITIES
        ),
    )
    runner = Runner(results)
    runtime = LocalCliModelRuntime(
        RuntimeSelection(role="r", definition=definition, model=None),
        runner=runner,
        which=lambda name: str(link),
        environment=PARENT_ENV,
    )
    return runtime, runner


def test_the_qualified_build_runs_through_its_resolved_file(install):
    link, builds = install
    runtime, runner = runtime_on(link, sha256(builds["v1"]), [ok(CLAUDE), answer("ok")])

    assert runtime.run("p").text == "ok"

    auth, inference = runner.calls
    assert auth.argv[0] == inference.argv[0] == os.path.realpath(builds["v1"])
    assert auth.argv[0] != str(link)


def test_a_build_with_another_hash_is_refused_before_any_process(install):
    link, builds = install
    runtime, runner = runtime_on(link, sha256(builds["v2"]), [ok(CLAUDE), answer("ok")])

    with pytest.raises(RuntimeIsolationUnavailable, match="not the qualified build"):
        runtime.run("p")

    assert runner.calls == []


def test_a_symlink_repointed_after_resolution_changes_nothing(install):
    """The auto-updater moves `claude` to a new build between the login check
    and the inference: the inference still runs the file that was verified."""
    link, builds = install

    def repoint_then_ok(invocation):
        link.unlink()
        link.symlink_to(builds["v2"])
        return (0, CLAUDE_OK, "")

    runtime, runner = runtime_on(
        link, sha256(builds["v1"]), [repoint_then_ok, answer("ok")]
    )

    runtime.run("p")

    auth, inference = runner.calls
    assert inference.argv[0] == auth.argv[0] == os.path.realpath(builds["v1"])
    # The next invocation resolves again and refuses the new build.
    with pytest.raises(RuntimeIsolationUnavailable):
        runtime.run("p")


def test_an_unreadable_executable_is_refused(install):
    link, builds = install
    builds["v1"].unlink()
    runtime, runner = runtime_on(link, QUALIFIED_SHA256, [])

    with pytest.raises(RuntimeIsolationUnavailable, match="could not be read"):
        runtime.run("p")
    assert runner.calls == []


def test_no_qualified_build_means_no_claude_execution_and_no_fallback():
    unqualified = RuntimeDefinition(
        name="claude", executable="claude", invocation_mode="print"
    )
    runtime, runner = build(unqualified, results=[ok(CLAUDE), answer("ok")])

    with pytest.raises(
        RuntimeIsolationUnavailable, match="no build of this CLI is qualified"
    ):
        runtime.run("p")
    assert runner.calls == []


def test_codex_remains_refused_before_any_process():
    runtime, runner = build(CODEX, results=[ok(CODEX), answer("ok")])

    with pytest.raises(RuntimeIsolationUnavailable):
        runtime.run("p")
    assert runner.calls == []


def test_the_diagnostic_reports_an_unqualified_build_as_not_eligible():
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE)])
    runtime._fingerprint = lambda path: "b" * 64

    summary = runtime.preflight()

    assert "logged in via claude.ai (firstParty)" in summary
    assert "not eligible" in summary and "not the qualified build" in summary
    assert len(runner.calls) == 1


# -- E, F: the fixed child environment --------------------------------------------------------


@pytest.mark.parametrize("parent_value", ["0", "", "false"])
def test_the_parent_cannot_override_the_fixed_telemetry_switch(parent_value):
    environment = {**PARENT_ENV, "DISABLE_TELEMETRY": parent_value, "DO_NOT_TRACK": "0"}
    runtime, runner = build(
        CLAUDE, results=[ok(CLAUDE), answer("ok")], environment=environment
    )

    runtime.run("p")

    for invocation in runner.calls:
        assert invocation.env["DISABLE_TELEMETRY"] == "1"
        assert "DO_NOT_TRACK" not in invocation.env


def test_parent_credentials_and_provider_overrides_stay_out_of_the_child():
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), answer("ok")])

    runtime.run("p")

    for invocation in runner.calls:
        assert set(invocation.env) == {
            "PATH",
            "HOME",
            *FIXED_CHILD_ENVIRONMENT["print"],
        }


def test_the_fixed_value_cannot_be_named_for_passthrough():
    with pytest.raises(DeniedEnvironmentName):
        require_allowed(["DISABLE_TELEMETRY"])
    with pytest.raises(DeniedEnvironmentName):
        child_environment({"DISABLE_TELEMETRY": "0"}, ["DISABLE_TELEMETRY"], "print")


def test_the_configuration_cannot_pass_the_fixed_value_through(tmp_path):
    config = tmp_path / "sdlc.toml"
    config.write_text(
        'version = 1\n[model_runtime]\ntransport = "local_cli_oauth"\n'
        '[model_runtime.runtimes.claude]\nexecutable = "claude"\n'
        'invocation_mode = "print"\nenvironment_passthrough = ["DISABLE_TELEMETRY"]\n'
    )
    with pytest.raises(ModelRuntimeConfigError):
        runtime_definition(load_model_runtime_config(config), "claude")


def test_the_fixed_child_values_are_exactly_the_three_switches():
    assert FIXED_CHILD_ENVIRONMENT == {
        "print": {
            "DISABLE_TELEMETRY": "1",
            "CLAUDE_CODE_DISABLE_ATTACHMENTS": "1",
            "CLAUDE_CODE_DISABLE_FILE_MENTIONS": "1",
        },
        "exec": {},
    }


# -- the configured contract ------------------------------------------------------------------


def test_the_shipped_configuration_qualifies_exactly_one_build():
    qualified = runtime_definition(
        load_model_runtime_config(Path("config/sdlc.toml")), "claude"
    ).qualified_binary
    assert qualified == QualifiedBinary(
        "b5d795b7760032d79954b55a9cd1876dcf3a8dc9608fd6bb9f618593f69fd44b",
        "2.1.306",
        frozenset({"cc-plugin-agents-md", "cc-plugin-plugin-authoring"}),
        QUALIFIED_CAPABILITIES,
    )


@pytest.mark.parametrize(
    "table",
    [
        'sha256 = "abc"\nversion = "1"\nbuiltin_plugins = []' + CAPS_LINE,
        f'sha256 = "{"A" * 64}"\nversion = "1"\nbuiltin_plugins = []' + CAPS_LINE,
        f'sha256 = "{"a" * 64}"\nversion = ""\nbuiltin_plugins = []' + CAPS_LINE,
        f'sha256 = "{"a" * 64}"\nversion = "1"\nbuiltin_plugins = ["x", "x"]'
        + CAPS_LINE,
        f'sha256 = "{"a" * 64}"\nversion = "1"\nbuiltin_plugins = []',
        f'sha256 = "{"a" * 64}"\nversion = "1"\nbuiltin_plugins = []'
        + CAPS_LINE
        + "\nextra = 1",
        f'sha256 = "{"a" * 64}"\nversion = "1"\nbuiltin_plugins = []'
        + '\nprotocol_capabilities = ["x", "x"]',
        f'sha256 = "{"a" * 64}"\nversion = "1"\nbuiltin_plugins = []'
        + '\nprotocol_capabilities = "x"',
    ],
    ids=[
        "short-hash",
        "uppercase-hash",
        "empty-version",
        "duplicate-plugin",
        "missing-capabilities",
        "unknown-key",
        "duplicate-capability",
        "capabilities-not-a-list",
    ],
)
def test_a_malformed_qualification_is_refused_when_the_file_loads(tmp_path, table):
    config = tmp_path / "sdlc.toml"
    config.write_text(
        'version = 1\n[model_runtime]\ntransport = "local_cli_oauth"\n'
        '[model_runtime.runtimes.claude]\nexecutable = "claude"\ninvocation_mode = "print"\n'
        f"[model_runtime.runtimes.claude.qualified_binary]\n{table}\n"
    )
    with pytest.raises(ModelRuntimeConfigError):
        runtime_definition(load_model_runtime_config(config), "claude")


# -- Q: real child processes: early termination, timeout, exit -------------------------------


CHILD = """#!{python}
import json, os, sys, time
if sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}}))
    sys.exit(0)
mode = {mode!r}
sys.stdin.read()
init = {{"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": "s",
        "tools": [], "mcp_servers": [], "skills": [], "slash_commands": [],
        "apiKeySource": "none", "analytics_disabled": True,
        "claude_code_version": {version!r},
        "capabilities": {capabilities!r},
        "plugins": [{{"name": n, "path": "builtin", "source": n + "@builtin"}} for n in {plugins!r}]}}
if mode == "bad-init":
    init["tools"] = ["Read"]
print(json.dumps(init), flush=True)
if mode in ("bad-init", "hang"):
    time.sleep(60)
if mode == "exit":
    sys.exit(3)
"""


def real_child(tmp_path, mode, timeout=30):
    script = tmp_path / f"child-{mode}"
    script.write_text(
        CHILD.format(
            python=sys.executable,
            mode=mode,
            version=QUALIFIED_VERSION,
            plugins=sorted(QUALIFIED_PLUGINS),
            capabilities=sorted(QUALIFIED_CAPABILITIES),
        )
    )
    script.chmod(0o755)
    definition = RuntimeDefinition(
        name="claude",
        executable=str(script),
        invocation_mode="print",
        qualified_binary=QualifiedBinary(
            sha256(script), QUALIFIED_VERSION, QUALIFIED_PLUGINS, QUALIFIED_CAPABILITIES
        ),
    )
    return LocalCliModelRuntime(
        RuntimeSelection(role="r", definition=definition, model=None),
        timeout_seconds=timeout,
    )


def test_a_bad_init_stops_the_child_at_once(tmp_path):
    runtime = real_child(tmp_path, "bad-init")
    started = time.monotonic()

    with pytest.raises(ModelSessionRejected) as caught:
        runtime.run("p")

    assert caught.value.code == "CAPABILITY_EXPOSED"
    assert time.monotonic() - started < 20, "the child was stopped, not waited for"


def test_a_child_that_hangs_times_out_and_is_stopped(tmp_path):
    runtime = real_child(tmp_path, "hang", timeout=2)
    started = time.monotonic()

    with pytest.raises(ModelRuntimeError, match="timed out"):
        runtime.run("p")

    assert time.monotonic() - started < 20


def test_a_nonzero_exit_after_a_good_init_is_a_runtime_error(tmp_path):
    runtime = real_child(tmp_path, "exit")

    with pytest.raises(ModelRuntimeError) as caught:
        runtime.run("p")

    assert caught.value.exit_code == 3
    assert not isinstance(caught.value, ModelSessionRejected)


# -- @path and instruction files: what the runtime hands the child -----------------------------


def test_at_path_text_reaches_the_child_only_as_literal_stdin():
    text = "See @./notes.md and @/etc/hosts and @~/.ssh/id_rsa"
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), answer("ok")])

    runtime.run(text)

    inference = runner.calls[1]
    assert inference.stdin_text == text
    assert not any("@" in arg for arg in inference.argv)
    for flag in (
        "--add-dir",
        "--settings",
        "--mcp-config",
        "--plugin-dir",
        "--append-system-prompt",
    ):
        assert flag not in inference.argv


# -- the captured 2.1.306 init record, against the shipped qualification ------------------

REAL_INIT = json.loads(
    (
        Path(__file__).parent / "fixtures/claude_runtime/init-2.1.306-hardened.json"
    ).read_text()
)
SHIPPED_QUALIFIED = runtime_definition(
    load_model_runtime_config(Path("config/sdlc.toml")), "claude"
).qualified_binary
SHIPPED_EXPECTED = ExpectedSession(
    cwd=CWD,
    version=SHIPPED_QUALIFIED.version,
    builtin_plugins=SHIPPED_QUALIFIED.builtin_plugins,
    protocol_capabilities=SHIPPED_QUALIFIED.protocol_capabilities,
)


def real_stream(text=SECRET_ANSWER, init_changes=None, drop=()):
    init = {**REAL_INIT, "cwd": CWD, "session_id": "s-real", **(init_changes or {})}
    for field in drop:
        init.pop(field)
    return lines_of(
        [
            init,
            {"type": "system", "subtype": "thinking_tokens", "session_id": "s-real"},
            {
                "type": "assistant",
                "session_id": "s-real",
                "message": {"content": [{"type": "text", "text": text}]},
            },
            {"type": "rate_limit_event", "session_id": "s-real"},
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "session_id": "s-real",
                "result": text,
            },
        ]
    )


def real_refused(stdout, code):
    with pytest.raises(SessionRejected) as caught:
        validate_stream(stdout, SHIPPED_EXPECTED)
    assert caught.value.code == code, caught.value
    assert SECRET_ANSWER not in str(caught.value)


def test_the_captured_init_record_is_accepted_by_the_shipped_qualification():
    assert REAL_INIT["claude_code_version"] == "2.1.306"
    assert len(REAL_INIT["capabilities"]) == 11
    assert (
        validate_stream(real_stream("final answer"), SHIPPED_EXPECTED) == "final answer"
    )


def test_the_shipped_capability_allowlist_is_exactly_the_captured_set():
    assert SHIPPED_QUALIFIED.protocol_capabilities == frozenset(
        REAL_INIT["capabilities"]
    )


def test_the_captured_set_in_another_order_is_accepted():
    shuffled = list(reversed(REAL_INIT["capabilities"]))
    assert (
        validate_stream(
            real_stream(init_changes={"capabilities": shuffled}), SHIPPED_EXPECTED
        )
        == SECRET_ANSWER
    )


@pytest.mark.parametrize(
    "capabilities",
    [
        [*REAL_INIT["capabilities"], "task_list_restore_v1"],
        [*REAL_INIT["capabilities"], "register_repo_root_v1"],
        REAL_INIT["capabilities"][1:],
        [c for c in REAL_INIT["capabilities"] if c != "mcp_read_resource_v1"],
        [*REAL_INIT["capabilities"], REAL_INIT["capabilities"][0]],
        [],
    ],
    ids=[
        "unknown-added",
        "another-unknown",
        "one-missing",
        "mcp-read-missing",
        "duplicate",
        "empty",
    ],
)
def test_any_other_capability_set_is_refused(capabilities):
    real_refused(
        real_stream(init_changes={"capabilities": capabilities}),
        "CAPABILITY_NOT_QUALIFIED",
    )


@pytest.mark.parametrize(
    "capabilities",
    [
        "interrupt_receipt_v1",
        {"interrupt_receipt_v1": True},
        [*REAL_INIT["capabilities"][:-1], 7],
        [*REAL_INIT["capabilities"][:-1], {"name": "ui_surface_v1"}],
        None,
    ],
    ids=["string", "object", "non-string-value", "object-value", "null"],
)
def test_a_malformed_capability_field_is_refused(capabilities):
    real_refused(
        real_stream(init_changes={"capabilities": capabilities}), "INIT_INVALID"
    )


def test_a_missing_capability_field_is_refused():
    real_refused(real_stream(drop=("capabilities",)), "INIT_INVALID")


def test_the_telemetry_plugin_in_the_captured_record_is_refused():
    plugins = [
        *REAL_INIT["plugins"],
        {
            "name": "cc-plugin-telemetry",
            "path": "builtin",
            "source": "cc-plugin-telemetry@builtin",
        },
    ]
    real_refused(real_stream(init_changes={"plugins": plugins}), "PLUGIN_NOT_QUALIFIED")


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"tools": ["Read"]}, "CAPABILITY_EXPOSED"),
        (
            {"mcp_servers": [{"name": "fibery", "status": "connected"}]},
            "CAPABILITY_EXPOSED",
        ),
        ({"skills": ["plugin-authoring"]}, "CAPABILITY_EXPOSED"),
        ({"slash_commands": ["plugin-authoring"]}, "CAPABILITY_EXPOSED"),
        ({"analytics_disabled": False}, "TELEMETRY_NOT_DISABLED"),
        ({"apiKeySource": "ANTHROPIC_API_KEY"}, "AUTHENTICATION_NOT_QUALIFIED"),
        ({"claude_code_version": "2.1.307"}, "BINARY_NOT_QUALIFIED"),
        ({"additional_directories": ["/Users/someone"]}, "CAPABILITY_EXPOSED"),
    ],
    ids=[
        "tools",
        "mcp",
        "skills",
        "slash",
        "analytics",
        "api-key",
        "version",
        "add-dir",
    ],
)
def test_the_captured_record_with_one_deviation_is_refused(changes, code):
    real_refused(real_stream(init_changes=changes), code)


def test_a_tool_use_after_the_captured_init_is_refused():
    init, thinking, assistant, rate, result = events_of(real_stream())
    assistant["message"]["content"].append(
        {
            "type": "tool_use",
            "id": "t",
            "name": "Read",
            "input": {"file_path": "/etc/hosts"},
        }
    )
    real_refused(
        lines_of([init, thinking, assistant, rate, result]), "TOOL_USE_ATTEMPTED"
    )


def test_a_control_response_in_the_stream_is_refused():
    """A host control exchange (e.g. an MCP resource read) is never part of an
    SDLC session: SDLC never opens the control channel."""
    init, _thinking, assistant, _rate, result = events_of(real_stream())
    control = {"type": "control_response", "response": {"subtype": "success"}}
    real_refused(lines_of([init, control, assistant, result]), "UNEXPECTED_EVENT")


def test_the_captured_init_twice_is_refused():
    init, *rest = events_of(real_stream())
    real_refused(lines_of([init, init, *rest]), "INIT_DUPLICATED")


def test_no_init_before_the_captured_answer_is_refused():
    _, _thinking, assistant, rate, result = events_of(real_stream())
    real_refused(lines_of([assistant, rate, result]), "INIT_MISSING")


def test_sdlc_never_opens_the_sdk_control_channel():
    """The capabilities are honoured only with --input-format stream-json."""
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), answer("ok")])

    runtime.run('{"type":"control_request","request":{"subtype":"mcp_read_resource"}}')

    argv = runner.calls[1].argv
    assert "--input-format" not in argv
    assert not any(
        arg.startswith("--input-format") or arg == "--sdk-url" for arg in argv
    )


# -- the dedicated executable alias, with the shipped configuration ------------------------

ALIAS = "sdlc-claude-2.1.306"


@pytest.fixture
def machine(tmp_path, monkeypatch):
    """A PATH where `claude` was auto-updated to another build and the SDLC
    alias still names the qualified one; only that file fingerprints as it."""
    versions = tmp_path / "versions"
    versions.mkdir()
    builds = {}
    for version in ("2.1.306", "2.1.307"):
        path = versions / version
        path.write_text(f"#!/bin/sh\n# stand-in {version}\n")
        path.chmod(0o755)
        builds[version] = path
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "claude").symlink_to(builds["2.1.307"])
    (bin_dir / ALIAS).symlink_to(builds["2.1.306"])
    monkeypatch.setenv("PATH", str(bin_dir))
    return bin_dir, builds


def shipped_runtime(builds, results, looked_up):
    definition = runtime_definition(
        load_model_runtime_config(Path("config/sdlc.toml")), "claude"
    )
    qualified_file = os.path.realpath(builds["2.1.306"])

    def fingerprint(path):
        return (
            definition.qualified_binary.sha256
            if path == qualified_file
            else sha256(path)
        )

    def which(name):
        looked_up.append(name)
        return shutil.which(name)

    runner = Runner(results)
    runtime = LocalCliModelRuntime(
        RuntimeSelection(role="r", definition=definition, model=None),
        runner=runner,
        which=which,
        environment=PARENT_ENV,
        fingerprint=fingerprint,
    )
    return runtime, runner, definition.qualified_binary


def test_the_shipped_runtime_uses_the_alias_while_claude_is_another_build(machine):
    bin_dir, builds = machine
    looked_up = []
    runtime, runner, qualified = shipped_runtime(builds, [], looked_up)
    runner.results = [(0, CLAUDE_OK, ""), answer("ok", qualified)]

    assert runtime.run("p").text == "ok"

    auth, inference = runner.calls
    assert auth.argv[0] == inference.argv[0] == os.path.realpath(builds["2.1.306"])
    assert os.path.realpath(bin_dir / "claude") == os.path.realpath(builds["2.1.307"])
    assert set(looked_up) == {ALIAS}


def test_a_missing_alias_refuses_and_never_falls_back_to_claude(machine):
    bin_dir, builds = machine
    (bin_dir / ALIAS).unlink()
    looked_up = []
    runtime, runner, _ = shipped_runtime(builds, [(0, CLAUDE_OK, "")], looked_up)

    with pytest.raises(ModelRuntimeError, match="not on PATH"):
        runtime.run("p")

    assert runner.calls == []
    assert set(looked_up) == {ALIAS}


def test_an_alias_naming_another_build_is_refused(machine):
    bin_dir, builds = machine
    (bin_dir / ALIAS).unlink()
    (bin_dir / ALIAS).symlink_to(builds["2.1.307"])
    runtime, runner, _ = shipped_runtime(builds, [(0, CLAUDE_OK, "")], [])

    with pytest.raises(RuntimeIsolationUnavailable, match="not the qualified build"):
        runtime.run("p")

    assert runner.calls == []


def test_an_alias_whose_build_was_removed_is_refused(machine):
    _bin_dir, builds = machine
    builds["2.1.306"].unlink()
    runtime, runner, _ = shipped_runtime(builds, [(0, CLAUDE_OK, "")], [])

    with pytest.raises(ModelRuntimeError):
        runtime.run("p")

    assert runner.calls == []


def test_the_shipped_configuration_names_the_alias_not_claude():
    definition = runtime_definition(
        load_model_runtime_config(Path("config/sdlc.toml")), "claude"
    )
    assert definition.executable == ALIAS
    assert "/" not in definition.executable
    assert "/Users/" not in Path("config/sdlc.toml").read_text()


# -- the 2026-10-22 @-mention disclosure: fixed attachment switches ------------------------

ATTACHMENT_SWITCHES = {
    "CLAUDE_CODE_DISABLE_ATTACHMENTS": "1",
    "CLAUDE_CODE_DISABLE_FILE_MENTIONS": "1",
}


def test_both_attachment_switches_reach_auth_and_inference():
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), answer("ok")])

    runtime.run("p")

    auth, inference = runner.calls
    assert auth.env == inference.env
    for name, value in {**ATTACHMENT_SWITCHES, "DISABLE_TELEMETRY": "1"}.items():
        assert inference.env[name] == value


@pytest.mark.parametrize("parent_value", ["0", "", "false", "no"])
def test_the_parent_cannot_turn_attachments_back_on(parent_value):
    environment = {**PARENT_ENV, **{name: parent_value for name in ATTACHMENT_SWITCHES}}
    runtime, runner = build(
        CLAUDE, results=[ok(CLAUDE), answer("ok")], environment=environment
    )

    runtime.run("p")

    for invocation in runner.calls:
        for name, value in ATTACHMENT_SWITCHES.items():
            assert invocation.env[name] == value


@pytest.mark.parametrize("name", sorted(ATTACHMENT_SWITCHES))
def test_configuration_cannot_name_an_attachment_switch(tmp_path, name):
    with pytest.raises(DeniedEnvironmentName):
        require_allowed([name])
    with pytest.raises(DeniedEnvironmentName):
        child_environment({name: "0"}, [name], "print")
    config = tmp_path / "sdlc.toml"
    config.write_text(
        'version = 1\n[model_runtime]\ntransport = "local_cli_oauth"\n'
        '[model_runtime.runtimes.claude]\nexecutable = "claude"\n'
        f'invocation_mode = "print"\nenvironment_passthrough = ["{name}"]\n'
    )
    with pytest.raises(ModelRuntimeConfigError):
        runtime_definition(load_model_runtime_config(config), "claude")


@pytest.mark.parametrize(
    "text",
    [
        "Contact ops@example.com or ops+alerts@example.co.uk about the outage.",
        "See @notes.md and @./docs/spec.md and @/etc/hosts and @../secret and @~/.ssh/id_rsa",
        'Quoted @"a file.md", an @agent-x mention and a trailing @',
        "Line one\n@CLAUDE.md\n\tindented @AGENTS.md\n",
    ],
    ids=["emails", "paths", "quoted-and-agent", "multiline"],
)
def test_the_prompt_reaches_the_child_byte_for_byte(text):
    runtime, runner = build(CLAUDE, results=[ok(CLAUDE), answer("ok")])

    runtime.run(text, context=f"CONTEXT {text}")

    assert runner.calls[1].stdin_text == f"CONTEXT {text}\n\n{text}"


MENTION_CHILD = """#!{python}
import json, os, re, sys
if sys.argv[1:3] == ["auth", "status"]:
    print(json.dumps({{"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty"}}))
    sys.exit(0)
prompt = sys.stdin.read()
with open("inside-secret.txt", "w") as f:
    f.write({marker!r})
# The 2.1.306 behaviour this models: unless attachments are switched off, an
# @path in the input pulls that file from the working directory into context.
if os.environ.get("CLAUDE_CODE_DISABLE_ATTACHMENTS") != "1":
    for name in re.findall(r"@(?:\\./)?([\\w.-]+)", prompt):
        if os.path.isfile(name):
            prompt += "\\n[attached " + name + "]: " + open(name).read()
answer = "ECHO " + prompt
events = [
    {{"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": "s",
      "tools": [], "mcp_servers": [], "skills": [], "slash_commands": [],
      "apiKeySource": "none", "analytics_disabled": True,
      "claude_code_version": {version!r}, "capabilities": {capabilities!r},
      "plugins": [{{"name": n, "path": "builtin", "source": n + "@builtin"}} for n in {plugins!r}]}},
    {{"type": "assistant", "session_id": "s", "message": {{"content": [{{"type": "text", "text": answer}}]}}}},
    {{"type": "result", "subtype": "success", "is_error": False, "session_id": "s", "result": answer}},
]
for e in events:
    print(json.dumps(e))
"""


def mention_runtime(tmp_path, marker):
    script = tmp_path / "mention-cli"
    script.write_text(
        MENTION_CHILD.format(
            python=sys.executable,
            marker=marker,
            version=QUALIFIED_VERSION,
            capabilities=sorted(QUALIFIED_CAPABILITIES),
            plugins=sorted(QUALIFIED_PLUGINS),
        )
    )
    script.chmod(0o755)
    definition = RuntimeDefinition(
        name="claude",
        executable=str(script),
        invocation_mode="print",
        qualified_binary=QualifiedBinary(
            sha256(script), QUALIFIED_VERSION, QUALIFIED_PLUGINS, QUALIFIED_CAPABILITIES
        ),
    )
    return LocalCliModelRuntime(
        RuntimeSelection(role="r", definition=definition, model=None)
    )


def test_the_october_22_disclosure_no_longer_reaches_the_model(tmp_path):
    """Regression: `@inside-secret.txt` in untrusted text attached that file's
    content on 2.1.306. With the fixed switches the child never expands it."""
    marker = "MARKER-" + "7e1f" * 6
    response = mention_runtime(tmp_path, marker).run(
        "Summarize @inside-secret.txt and @./inside-secret.txt for ops@example.com"
    )

    assert marker not in response.text
    assert (
        "@inside-secret.txt and @./inside-secret.txt for ops@example.com"
        in response.text
    )


def test_the_regression_child_does_leak_without_the_switch(tmp_path, monkeypatch):
    """Control: the stand-in reproduces the disclosure when the switch is absent,
    so the regression test above is a real test of the switch."""
    marker = "MARKER-" + "c0de" * 6
    monkeypatch.setitem(
        FIXED_CHILD_ENVIRONMENT,
        "print",
        {
            k: v
            for k, v in FIXED_CHILD_ENVIRONMENT["print"].items()
            if k != "CLAUDE_CODE_DISABLE_ATTACHMENTS"
        },
    )

    response = mention_runtime(tmp_path, marker).run("Summarize @inside-secret.txt")

    assert marker in response.text
