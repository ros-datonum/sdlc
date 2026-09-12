"""RW-O03: one `sdlc worker run` per workspace, enforced by an OS lock.

The lock underneath is the real `flock`, in the private directory
tests/conftest.py provides. Real-process tests drive harmless local Python
subprocesses with pipes and bounded deadlines, never sleeps.
"""

from __future__ import annotations

import errno
import subprocess
import sys
import textwrap

import pytest

from sdlc import worker_runner_guard
from sdlc.model_runtime import ChildInvocation, _run_command
from sdlc.raw_execution_guard import LOCK_DIRECTORY_ENVIRONMENT, hold, lock_path
from sdlc.worker_runner_guard import (
    RUNNER_LOCK_PREFIX,
    WorkerRunnerBusy,
    WorkerRunnerGuardUnavailable,
    hold_workspace,
    runner_lock_key,
    runner_lock_path,
)
from test_raw_single_writer import DEADLINE_SECONDS, FD_SCAN, python_env, read_line

SCOPE = "example.fibery.io/space-1"
OTHER_SCOPE = "example.fibery.io/space-2"

HOLDER = textwrap.dedent(
    """
    import sys
    from sdlc.worker_runner_guard import hold_workspace

    with hold_workspace(sys.argv[1]):
        print("held", flush=True)
        sys.stdin.readline()
    print("released", flush=True)
    """
)
PROBE = textwrap.dedent(
    """
    import sys
    from sdlc.worker_runner_guard import WorkerRunnerBusy, hold_workspace

    try:
        with hold_workspace(sys.argv[1]):
            print("acquired")
    except WorkerRunnerBusy:
        print("busy")
    """
)


def probe(scope):
    completed = subprocess.run(
        [sys.executable, "-c", PROBE, scope],
        capture_output=True,
        text=True,
        timeout=DEADLINE_SECONDS,
        env=python_env(),
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


def refused(error, match, scope=SCOPE):
    """Taking the lock fails with `error`, and the guarded block never runs."""
    with pytest.raises(error, match=match), hold_workspace(scope):
        pytest.fail("the runner ran without its lock")


@pytest.fixture
def holder():
    processes = []

    def start(scope):
        process = subprocess.Popen(
            [sys.executable, "-c", HOLDER, scope],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=python_env(),
        )
        processes.append(process)
        assert read_line(process.stdout) == "held"
        return process

    yield start
    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=DEADLINE_SECONDS)


# -- one runner per workspace ------------------------------------------------------


def test_the_first_runner_takes_the_workspace_lock():
    with hold_workspace(SCOPE) as path:
        assert path == runner_lock_path(SCOPE)
        assert path.exists()


def test_a_second_runner_fails_immediately_while_the_first_holds_it():
    with hold_workspace(SCOPE):
        refused(WorkerRunnerBusy, "nothing was read or written")


def test_another_process_cannot_take_a_held_workspace(holder):
    holder(SCOPE)

    assert probe(SCOPE) == "busy"
    assert probe(OTHER_SCOPE) == "acquired"


def test_different_workspaces_do_not_collide():
    with hold_workspace(SCOPE) as first, hold_workspace(OTHER_SCOPE) as second:
        assert first != second


def test_the_key_is_the_workspace_host_case_insensitively_and_its_exact_space():
    assert runner_lock_key("Example.Fibery.IO/space-1 ") == runner_lock_key(SCOPE)
    assert runner_lock_key(SCOPE) != runner_lock_key(OTHER_SCOPE)
    assert runner_lock_key(SCOPE) != runner_lock_key("other.fibery.io/space-1")


def test_the_runner_lock_is_independent_of_every_per_raw_lock():
    """The RAW processor takes its own per-RAW lock while the runner holds its."""
    assert runner_lock_path(SCOPE) != lock_path(SCOPE, "raw-uuid-1")
    with hold_workspace(SCOPE), hold(SCOPE, "raw-uuid-1"):
        pass


def test_an_empty_workspace_identity_is_refused():
    refused(WorkerRunnerGuardUnavailable, "empty", scope="  ")


# -- release ------------------------------------------------------------------------


def test_the_lock_is_released_on_normal_exit():
    with hold_workspace(SCOPE):
        pass
    with hold_workspace(SCOPE):
        pass


def test_the_lock_is_released_when_the_runner_raises():
    with pytest.raises(KeyboardInterrupt), hold_workspace(SCOPE):
        raise KeyboardInterrupt
    with hold_workspace(SCOPE):
        pass


def test_release_by_the_holding_process_permits_the_next_runner(holder):
    process = holder(SCOPE)
    assert probe(SCOPE) == "busy"

    process.stdin.write("release\n")
    process.stdin.flush()
    assert read_line(process.stdout) == "released"
    process.wait(timeout=DEADLINE_SECONDS)

    assert probe(SCOPE) == "acquired"


def test_a_killed_runner_leaves_no_permanent_busy_condition(holder):
    """No lease or stale timer: the kernel releases the lock with the process."""
    process = holder(SCOPE)
    assert probe(SCOPE) == "busy"

    process.kill()
    process.wait(timeout=DEADLINE_SECONDS)

    assert probe(SCOPE) == "acquired"


def test_the_lock_descriptor_is_not_inherited_by_a_worker_child_process():
    """A model CLI started by a worker cannot keep the runner's lock alive."""
    with hold_workspace(SCOPE) as path:
        completed = _run_command(
            ChildInvocation(
                argv=(sys.executable, "-c", FD_SCAN, str(path)),
                stdin_text="",
                timeout=DEADLINE_SECONDS,
                env=python_env(),
                cwd=str(path.parent),
            )
        )
        assert completed.returncode == 0, completed.stderr
        assert completed.stdout.strip() == "clean"
        assert probe(SCOPE) == "busy"
    assert probe(SCOPE) == "acquired"


# -- the lock file carries nothing ----------------------------------------------------


def test_the_lock_file_holds_no_payload_and_names_no_workspace():
    with hold_workspace(SCOPE) as path:
        assert path.read_bytes() == b""
    assert path.exists(), "the rendezvous file stays"
    assert path.read_bytes() == b""
    assert path.name.startswith(RUNNER_LOCK_PREFIX)
    assert "fibery" not in path.name and "space" not in path.name


# -- failing closed -------------------------------------------------------------------


def test_a_platform_without_flock_fails_closed(monkeypatch):
    monkeypatch.setattr(worker_runner_guard, "fcntl", None)

    refused(WorkerRunnerGuardUnavailable, "unguarded")


def test_an_unusable_lock_directory_fails_closed(monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    monkeypatch.setenv(LOCK_DIRECTORY_ENVIRONMENT, str(blocker / "locks"))

    refused(WorkerRunnerGuardUnavailable, "Could not prepare")


def test_an_unexpected_lock_error_fails_closed(monkeypatch):
    class BrokenFlock:
        LOCK_EX = LOCK_NB = LOCK_UN = 0

        @staticmethod
        def flock(descriptor, operation):
            raise OSError(errno.EBADF, "bad descriptor")

    monkeypatch.setattr(worker_runner_guard, "fcntl", BrokenFlock)

    refused(WorkerRunnerGuardUnavailable, "OSError")
