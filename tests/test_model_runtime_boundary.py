"""The child-process boundary, proven through the real subprocess wrapper.

A harmless stand-in executable records what it was actually started with:
its argv, working directory and environment names. A mocked runner cannot
prove that inheritance was fixed; a real child can.
"""

import json
import os
import sys
from pathlib import Path

import pytest

from sdlc.model_runtime import LocalCliModelRuntime, RuntimeIsolationUnavailable
from sdlc.model_runtime_config import RuntimeDefinition, RuntimeSelection

CLAUDE_STATUS = {
    "loggedIn": True,
    "authMethod": "claude.ai",
    "apiProvider": "firstParty",
    "subscriptionType": "synthetic",
}

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
    print("RESPONSE:" + sys.stdin.read())
"""


@pytest.fixture
def stand_in(tmp_path):
    """A recording executable plus the log it appends to."""
    log = tmp_path / "calls.jsonl"
    script = tmp_path / "fake-cli"
    script.write_text(
        HELPER.format(python=sys.executable, log=str(log), status=CLAUDE_STATUS)
    )
    script.chmod(0o755)
    return script, log


def calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


def runtime_for(script, mode, passthrough=()):
    definition = RuntimeDefinition(
        name="fake",
        executable=str(script),
        invocation_mode=mode,
        environment_passthrough=passthrough,
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
            for name in record["env"]
        )
        assert {"PATH", "HOME"} <= set(record["env"])
    assert response.text == "RESPONSE:CONTEXT\n\nPROMPT\n"


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
    }

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
