"""The child-process boundary, proven through the real subprocess wrapper.

A harmless stand-in executable records what it was actually started with:
its argv, working directory and environment names. A mocked runner cannot
prove that inheritance was fixed; a real child can.
"""

import hashlib
import json
import os
import sys
from pathlib import Path

import pytest

from sdlc.model_runtime import LocalCliModelRuntime, RuntimeIsolationUnavailable
from sdlc.model_runtime_config import (
    QualifiedBinary,
    RuntimeDefinition,
    RuntimeSelection,
)
from sdlc.model_runtime_environment import FIXED_CHILD_ENVIRONMENT

CLAUDE_STATUS = {
    "loggedIn": True,
    "authMethod": "claude.ai",
    "apiProvider": "firstParty",
    "subscriptionType": "synthetic",
}

# What the runtime itself sets in every Claude child (amendment §3, §7).
FIXED_NAMES = set(FIXED_CHILD_ENVIRONMENT["print"])
STAND_IN_VERSION = "0.0.0-stand-in"
STAND_IN_PLUGINS = ["cc-plugin-agents-md", "cc-plugin-plugin-authoring"]
STAND_IN_CAPABILITIES = ["interrupt_receipt_v1", "msg_lifecycle_v1"]

# A stand-in CLI: it records how it was started, answers the status command,
# and otherwise emits the stream-json session a qualified build would, for its
# own working directory, answering with what it read on stdin.
HELPER = """#!{python}
import json, os, sys
argv = sys.argv[1:]
with open({log!r}, "a") as log:
    log.write(json.dumps({{"argv": argv, "cwd": os.getcwd(), "env": sorted(os.environ)}}) + "\\n")
if argv[:2] == ["auth", "status"]:
    print(json.dumps({status!r}))
elif argv[:2] == ["login", "status"]:
    print("Logged in using ChatGPT", file=sys.stderr)
else:
    answer = "RESPONSE:" + sys.stdin.read()
    for event in (
        {{"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": "s",
          "tools": [], "mcp_servers": [], "skills": [], "slash_commands": [],
          "agents": [], "apiKeySource": "none",
          "analytics_disabled": os.environ.get("DISABLE_TELEMETRY") == "1",
          "claude_code_version": {version!r},
          "capabilities": {capabilities!r},
          "plugins": [{{"name": n, "path": "builtin", "source": n + "@builtin"}}
                      for n in {plugins!r}]}},
        {{"type": "assistant", "session_id": "s",
          "message": {{"content": [{{"type": "text", "text": answer}}]}}}},
        {{"type": "result", "subtype": "success", "is_error": False,
          "session_id": "s", "result": answer}},
    ):
        print(json.dumps(event))
"""


@pytest.fixture
def stand_in(tmp_path):
    """A recording executable plus the log it appends to."""
    log = tmp_path / "calls.jsonl"
    script = tmp_path / "fake-cli"
    script.write_text(
        HELPER.format(
            python=sys.executable,
            log=str(log),
            status=CLAUDE_STATUS,
            version=STAND_IN_VERSION,
            plugins=STAND_IN_PLUGINS,
            capabilities=STAND_IN_CAPABILITIES,
        )
    )
    script.chmod(0o755)
    return script, log


def calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def qualified(script):
    """The stand-in file itself, qualified by its real SHA-256."""
    return QualifiedBinary(
        sha256=hashlib.sha256(Path(script).read_bytes()).hexdigest(),
        version=STAND_IN_VERSION,
        builtin_plugins=frozenset(STAND_IN_PLUGINS),
        protocol_capabilities=frozenset(STAND_IN_CAPABILITIES),
    )


def runtime_for(script, mode, passthrough=(), executable=None):
    definition = RuntimeDefinition(
        name="fake",
        executable=str(executable or script),
        invocation_mode=mode,
        environment_passthrough=passthrough,
        qualified_binary=qualified(script),
    )
    return LocalCliModelRuntime(
        RuntimeSelection(role="r", definition=definition, model=None)
    )


@pytest.mark.parametrize("mode", ["print"])
def test_parent_secrets_never_reach_either_child(stand_in, monkeypatch, mode):
    script, log = stand_in
    monkeypatch.setenv("FIBERY_TOKEN", "synthetic-fibery-secret")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "synthetic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-key")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://redirect.invalid")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://redirect.invalid")
    monkeypatch.setenv("CLAUDE_CODE_USE_BEDROCK", "1")

    response = runtime_for(script, mode).run("PROMPT", context="CONTEXT")

    auth, inference = calls(log)
    for record in (auth, inference):
        assert "FIBERY_TOKEN" not in record["env"]
        assert not any(
            name.startswith(("ANTHROPIC_", "OPENAI_", "CLAUDE_CODE_", "CLAUDECODE"))
            for name in set(record["env"]) - FIXED_NAMES
        )
        assert {"PATH", "HOME"} <= set(record["env"])
    assert response.text == "RESPONSE:CONTEXT\n\nPROMPT"


@pytest.mark.parametrize("mode", ["print"])
def test_both_children_run_in_the_same_temporary_directory_outside_the_repo(
    stand_in, mode
):
    script, log = stand_in

    runtime_for(script, mode).run("p")

    auth, inference = calls(log)
    assert auth["cwd"] == inference["cwd"]
    cwd = Path(auth["cwd"])
    assert Path("sdlc-model-") and cwd.name.startswith("sdlc-model-")
    assert not cwd.is_relative_to(Path.cwd().resolve())
    assert not cwd.exists()
    assert auth["argv"][0:2] in (["auth", "status"], ["login", "status"])
    if mode == "exec":
        assert inference["argv"][inference["argv"].index("-C") + 1] == auth["cwd"]
    assert "--add-dir" not in inference["argv"]


def test_credential_store_locations_and_configured_names_pass_through(
    stand_in, monkeypatch
):
    script, log = stand_in
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(Path.home() / ".claude"))
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.local:3128")
    monkeypatch.setenv("FIBERY_TOKEN", "synthetic-fibery-secret")

    runtime_for(script, "print", passthrough=("HTTPS_PROXY",)).run("p")

    for record in calls(log):
        assert {"CLAUDE_CONFIG_DIR", "HTTPS_PROXY"} <= set(record["env"])
        assert "FIBERY_TOKEN" not in record["env"]


def test_the_environment_seen_by_the_child_is_exactly_the_allowlist(stand_in):
    script, log = stand_in
    expected = {
        name
        for name in (
            "PATH",
            "HOME",
            "USER",
            "LOGNAME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "TERM",
            "CLAUDE_CONFIG_DIR",
            "CODEX_HOME",
        )
        if name in os.environ
    } | FIXED_NAMES

    runtime_for(script, "print").run("p")

    for record in calls(log):
        # Python itself adds nothing on POSIX; what the child saw is the allowlist.
        assert set(record["env"]) - {"__CF_USER_TEXT_ENCODING"} == expected


def test_the_exec_family_never_reaches_the_stand_in(stand_in, monkeypatch):
    """A Codex-family request is refused before any real process starts."""
    script, log = stand_in
    monkeypatch.setenv("FIBERY_TOKEN", "synthetic-fibery-secret")

    with pytest.raises(RuntimeIsolationUnavailable):
        runtime_for(script, "exec").run("PROMPT")

    assert not log.exists(), "no auth check and no inference process was started"
