"""The authentication diagnostic script, run for real against stand-in CLIs.

The stand-ins answer only the status commands, record every argument they
receive, and fail loudly if anything else is asked of them. Their synthetic
account details must never reach the script's stdout or stderr.
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "scripts" / "check-local-model-auth.sh"

EMAIL = "private.person@example.com"
ORG = "Org-Private-Ltd-4471"
SHORT = "zq7private"
STDERR_MARKER = "stderr-private-9c1e"

VALID_CLAUDE = {
    "loggedIn": True,
    "authMethod": "claude.ai",
    "apiProvider": "firstParty",
    "subscriptionType": "max",
    "email": EMAIL,
    "orgName": ORG,
    "orgId": "org-4471",
}
MARKERS = (EMAIL, ORG, SHORT, STDERR_MARKER, "org-4471", "max")

STAND_IN = """#!{python}
import json, os, sys
argv = sys.argv[1:]
with open({log!r}, "a") as log:
    log.write(json.dumps(argv) + "\\n")
if argv == ["auth", "status", "--json"]:
    sys.stdout.write({stdout!r}); sys.stderr.write({stderr!r}); sys.exit({code})
if argv == ["login", "status"]:
    sys.stdout.write({stdout!r}); sys.stderr.write({stderr!r}); sys.exit({code})
sys.stderr.write("FORBIDDEN " + " ".join(argv)); sys.exit(99)
"""


def install(bin_dir, log, name, stdout="", stderr="", code=0):
    script = bin_dir / name
    script.write_text(
        STAND_IN.format(
            python=sys.executable, log=str(log), stdout=stdout, stderr=stderr, code=code
        )
    )
    script.chmod(0o755)


@pytest.fixture
def stand_ins(tmp_path):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.jsonl"
    return bin_dir, log


def run_script(bin_dir, script=SCRIPT):
    """Run the script with only the stand-ins, uv and the base system on PATH."""
    uv_dir = str(Path(shutil.which("uv")).parent)
    env = {
        **{k: v for k, v in os.environ.items() if k in ("HOME", "TMPDIR", "LANG")},
        "PATH": os.pathsep.join([str(bin_dir), uv_dir, "/usr/bin", "/bin"]),
    }
    return subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        env=env,
        cwd=REPO,
        check=False,
    )


def received(log):
    return (
        [json.loads(line) for line in log.read_text().splitlines()]
        if log.exists()
        else []
    )


def assert_private_and_status_only(result, log):
    for stream in (result.stdout, result.stderr):
        for marker in MARKERS:
            assert marker not in stream, (marker, stream)
    for argv in received(log):
        assert argv in (["auth", "status", "--json"], ["login", "status"]), argv


def test_a_valid_claude_login_is_summarized_without_account_details(stand_ins):
    bin_dir, log = stand_ins
    install(bin_dir, log, "claude", stdout=json.dumps(VALID_CLAUDE))
    install(bin_dir, log, "codex", stderr="Logged in using ChatGPT\n")

    result = run_script(bin_dir)

    assert result.returncode == 0, result
    assert "OK   claude: logged in via claude.ai (firstParty)" in result.stdout
    assert_private_and_status_only(result, log)


def test_codex_is_reported_authenticated_but_not_eligible(stand_ins):
    bin_dir, log = stand_ins
    install(bin_dir, log, "claude", stdout=json.dumps(VALID_CLAUDE))
    install(bin_dir, log, "codex", stderr="Logged in using ChatGPT\n")

    result = run_script(bin_dir)

    assert "OK   codex: Logged in using ChatGPT" in result.stdout
    assert "not eligible for SDLC reasoning execution" in result.stdout
    assert "RUNTIME_ISOLATION_UNAVAILABLE" in result.stdout
    assert all("exec" not in argv for argv in received(log)), "no inference"
    assert_private_and_status_only(result, log)


@pytest.mark.parametrize("field", ["authMethod", "apiProvider"])
def test_a_short_unknown_status_value_is_rejected_and_not_echoed(stand_ins, field):
    bin_dir, log = stand_ins
    install(bin_dir, log, "claude", stdout=json.dumps({**VALID_CLAUDE, field: SHORT}))
    install(bin_dir, log, "codex", stderr="Logged in using ChatGPT\n")

    result = run_script(bin_dir)

    assert result.returncode == 1
    assert "FAIL claude: authentication could not be verified" in result.stdout
    assert "unsupported or unrecognized" in result.stdout
    assert "OK   claude" not in result.stdout
    assert_private_and_status_only(result, log)


@pytest.mark.parametrize(
    "stdout",
    [json.dumps({**VALID_CLAUDE, "loggedIn": False}), "", "not json at all " + EMAIL],
    ids=["logged-out-exit-0", "empty", "malformed"],
)
def test_logged_out_empty_or_malformed_status_never_verifies(stand_ins, stdout):
    bin_dir, log = stand_ins
    install(bin_dir, log, "claude", stdout=stdout)
    install(bin_dir, log, "codex", stderr="Logged in using ChatGPT\n")

    result = run_script(bin_dir)

    assert result.returncode == 1
    assert "FAIL claude" in result.stdout and "OK   claude" not in result.stdout
    assert_private_and_status_only(result, log)


def test_a_nonzero_status_exit_reports_the_exit_without_its_output(stand_ins):
    bin_dir, log = stand_ins
    install(
        bin_dir, log, "claude", stdout=f"Email: {EMAIL}\n", stderr=STDERR_MARKER, code=3
    )
    install(bin_dir, log, "codex", stdout=EMAIL, stderr=STDERR_MARKER, code=2)

    result = run_script(bin_dir)

    assert result.returncode == 1
    assert "FAIL claude" in result.stdout and "exited 3" in result.stdout
    assert "FAIL codex" in result.stdout and "exited 2" in result.stdout
    assert_private_and_status_only(result, log)


def test_a_missing_executable_is_reported_without_verification(stand_ins):
    bin_dir, log = stand_ins
    install(bin_dir, log, "codex", stderr="Logged in using ChatGPT\n")

    result = run_script(bin_dir)

    assert result.returncode == 1
    assert "FAIL claude" in result.stdout and "not on PATH" in result.stdout
    assert "OK   claude" not in result.stdout
    assert_private_and_status_only(result, log)


def test_the_script_parses():
    assert subprocess.run(["bash", "-n", str(SCRIPT)], check=False).returncode == 0
