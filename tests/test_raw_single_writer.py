"""Audit A10: one local RAW invocation at a time, enforced by an OS lock.

Deterministic interleavings run the real RAW entry point with recording fake
runtimes; the lock underneath is the real `flock` in a private directory
(tests/conftest.py). Real-process tests drive harmless local Python
subprocesses with pipes and bounded deadlines, never sleeps.
"""

from __future__ import annotations

import os
import select
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from processor_fake import (
    FakeModelRuntime,
    build_workspace,
    candidate,
    model_output,
)
from sdlc.fibery_workspace import FiberyError
from sdlc.model_runtime import ChildInvocation, ModelResponse, _run_command
from sdlc.raw_execution_guard import (
    LOCK_DIRECTORY_ENVIRONMENT,
    RawGuardUnavailable,
    RawProcessingBusy,
    hold,
    lock_key,
    lock_path,
)
from sdlc.raw_processor import process_raw_requirement
from sdlc.results import ProcessResultCode as Code
from test_empty_result_recovery import RAW, leave_a_shell

OUTPUT = model_output([candidate()])
DEADLINE_SECONDS = 20
SCOPE = "fake.fibery.io/space-1"


def processing_results(ws):
    return [d for d in ws.documents if d.name.endswith("Processing Result")]


def standards(ws):
    return [r for r in ws.requirements.values() if r.type_name == "Standard"]


class NestsAnotherRun:
    """A model runtime that, while 'thinking', starts run B on the same RAW."""

    def __init__(self, ws, raw_id, **options):
        self.ws, self.raw_id, self.options = ws, raw_id, options
        self.calls = []
        self.inner = None
        self.inner_model = FakeModelRuntime([OUTPUT])
        self.reads_during_inner = None
        self.mutations_during_inner = None

    def run(self, prompt, context=""):
        self.calls.append(1)
        reads, mutations = len(self.ws.calls), len(self.ws.mutations)
        self.inner = process_raw_requirement(
            self.ws, self.inner_model, self.raw_id, **self.options
        )
        self.reads_during_inner = self.ws.calls[reads:]
        self.mutations_during_inner = self.ws.mutations[mutations:]
        return ModelResponse(text=OUTPUT, runtime="fake", model=None)


def assert_refused_untouched(model):
    assert model.inner.code is Code.RAW_PROCESSING_IN_PROGRESS, model.inner
    assert not model.inner_model.was_invoked
    assert model.inner.model_invoked is False
    assert model.reads_during_inner == [] and model.mutations_during_inner == []


# -- deterministic interleavings through the real entry point ------------------


def test_a_competing_run_during_the_model_call_is_refused_before_anything():
    ws, raw, _root = build_workspace()
    model = NestsAnotherRun(ws, raw.id)
    result = process_raw_requirement(ws, model, raw.id)
    assert_refused_untouched(model)
    assert result.code is Code.RAW_REQUIREMENT_PROCESSED, result
    assert len(processing_results(ws)) == 1
    assert len(standards(ws)) == 1
    assert ws.requirements[raw.id].state == "Review"


def test_a_competing_recovery_request_is_refused_the_same_way():
    ws, raw, _root = build_workspace()
    model = NestsAnotherRun(ws, raw.id, recover_empty_result="anything")
    result = process_raw_requirement(ws, model, raw.id)
    assert_refused_untouched(model)
    assert result.code is Code.RAW_REQUIREMENT_PROCESSED


def test_a_persisted_result_resume_holds_the_same_guard():
    """A resume invokes no model, so B is nested into its history read."""
    ws, raw, _root = build_workspace()
    ws.failures["create_requirement_with_id"] = FiberyError("induced")
    partial = process_raw_requirement(ws, FakeModelRuntime([OUTPUT]), raw.id)
    assert partial.code is Code.PARTIAL_PROCESSING
    ws.failures.clear()
    original = ws.read_document_content
    inner = {}

    def nest_once(secret):
        content = original(secret)
        if "inner" not in inner:
            inner["model"] = FakeModelRuntime([OUTPUT])
            reads, mutations = len(ws.calls), len(ws.mutations)
            inner["result"] = process_raw_requirement(ws, inner["model"], raw.id)
            inner["reads"] = ws.calls[reads:]
            inner["mutations"] = ws.mutations[mutations:]
            inner["inner"] = True
        return content

    ws.read_document_content = nest_once
    model = FakeModelRuntime([OUTPUT])
    resumed = process_raw_requirement(ws, model, raw.id)
    assert inner["result"].code is Code.RAW_PROCESSING_IN_PROGRESS
    assert not inner["model"].was_invoked
    assert inner["reads"] == [] and inner["mutations"] == []
    assert resumed.code is Code.RAW_REQUIREMENT_PROCESSED and not model.was_invoked
    assert len(processing_results(ws)) == 1 and len(standards(ws)) == 1


def test_an_explicit_shell_recovery_holds_the_same_guard():
    ws, raw, _root, shell, _ = leave_a_shell(RAW)
    ws.failures.clear()
    model = NestsAnotherRun(ws, raw.id)
    result = process_raw_requirement(ws, model, raw.id, recover_empty_result=shell.id)
    assert_refused_untouched(model)
    assert result.code is Code.RAW_REQUIREMENT_PROCESSED, result
    assert [d.id for d in processing_results(ws)] == [shell.id]


def test_after_a_shell_failure_the_next_invocation_follows_a3_not_the_lock():
    ws, raw, _root, shell, failure = leave_a_shell(RAW)
    assert failure.code is Code.PARTIAL_PROCESSING
    ws.failures.clear()
    model = FakeModelRuntime([OUTPUT])
    retry = process_raw_requirement(ws, model, raw.id)
    assert retry.code is Code.INVALID_PROCESSING_RESULT, retry
    assert "--recover-empty-result" in retry.message and shell.id in retry.message
    assert not model.was_invoked
    assert [d.id for d in processing_results(ws)] == [shell.id]
    assert ws.content[shell.secret] == ""


def test_after_a_partial_candidate_failure_the_next_invocation_resumes_once():
    ws, raw, _root = build_workspace()
    ws.failures["set_requirement_id"] = FiberyError("induced")
    partial = process_raw_requirement(ws, FakeModelRuntime([OUTPUT]), raw.id)
    assert partial.code is Code.PARTIAL_PROCESSING
    ws.failures.clear()
    model = FakeModelRuntime([OUTPUT])
    resumed = process_raw_requirement(ws, model, raw.id)
    assert resumed.code is Code.RAW_REQUIREMENT_PROCESSED and not model.was_invoked
    assert len(processing_results(ws)) == 1 and len(standards(ws)) == 1


def test_a_different_raw_is_not_blocked_by_this_raw():
    ws, raw, _root = build_workspace()
    other = {}

    class RunsAnotherRaw:
        def __init__(self):
            self.calls = []

        def run(self, prompt, context=""):
            self.calls.append(1)
            other["result"] = process_raw_requirement(
                ws, FakeModelRuntime([OUTPUT]), "raw-uuid-other"
            )
            return ModelResponse(text=OUTPUT, runtime="fake", model=None)

    result = process_raw_requirement(ws, RunsAnotherRaw(), raw.id)
    assert result.code is Code.RAW_REQUIREMENT_PROCESSED
    # The other RAW does not exist in the fake; what matters is that the
    # guard let its invocation proceed to its own entry checks.
    assert other["result"].code is Code.REQUIREMENT_NOT_FOUND


def test_a_direct_library_call_is_guarded_without_the_cli(monkeypatch):
    ws, raw, _root = build_workspace()
    with hold(ws.lock_scope, raw.id):
        model = FakeModelRuntime([OUTPUT])
        result = process_raw_requirement(ws, model, raw.id)
    assert result.code is Code.RAW_PROCESSING_IN_PROGRESS
    assert not model.was_invoked and ws.calls == [] and ws.mutations == []
    assert result.is_normal is False


def test_a_lock_that_cannot_be_prepared_fails_closed(monkeypatch, tmp_path):
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("")
    monkeypatch.setenv(LOCK_DIRECTORY_ENVIRONMENT, str(blocker / "locks"))
    ws, raw, _root = build_workspace()
    model = FakeModelRuntime([OUTPUT])
    result = process_raw_requirement(ws, model, raw.id)
    assert result.code is Code.RAW_PROCESSING_GUARD_UNAVAILABLE, result
    assert not model.was_invoked and ws.calls == [] and ws.mutations == []
    assert "unguarded" in result.message


# -- the lock itself, in this process ---------------------------------------------


def test_the_key_is_stable_across_cwd_scope_case_and_distinct_per_raw(
    tmp_path, monkeypatch
):
    here = lock_path(SCOPE, "raw-1")
    monkeypatch.chdir(tmp_path)
    assert lock_path(SCOPE, "raw-1") == here
    assert lock_path(SCOPE.upper(), "raw-1") == here
    assert lock_path(SCOPE, "raw-2") != here
    assert lock_path("other.fibery.io/space-1", "raw-1") != here
    assert lock_key(SCOPE, "raw-1") == Path(here.name).stem
    assert "raw-1" not in here.name and "fibery" not in here.name
    with pytest.raises(RawGuardUnavailable):
        lock_key(SCOPE, "  ")


def test_a_second_hold_in_the_same_process_is_busy_not_reentrant():
    with hold(SCOPE, "raw-same"):
        with pytest.raises(RawProcessingBusy), hold(SCOPE, "raw-same"):
            pass
        with hold(SCOPE, "raw-other"):
            pass  # independent key
    with hold(SCOPE, "raw-same"):
        pass  # released on exit


def test_a_leftover_rendezvous_file_is_not_busy_and_release_keeps_it():
    path = lock_path(SCOPE, "raw-leftover")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("")
    with hold(SCOPE, "raw-leftover") as held:
        assert held == path
    assert path.exists() and path.read_text() == ""
    with hold(SCOPE, "raw-leftover"):
        pass


def test_the_lock_file_and_directory_are_private_to_the_user():
    with hold(SCOPE, "raw-private") as path:
        assert oct(path.stat().st_mode & 0o777) == "0o600"
        assert path.stat().st_size == 0
    assert oct(path.parent.stat().st_mode & 0o777) == "0o700"


# -- real local processes -------------------------------------------------------------

HOLDER = textwrap.dedent(
    """
    import sys
    from sdlc.raw_execution_guard import hold
    scope, raw = sys.argv[1], sys.argv[2]
    with hold(scope, raw):
        print("held", flush=True)
        sys.stdin.readline()
    print("released", flush=True)
    """
)
PROBE = textwrap.dedent(
    """
    import sys
    from sdlc.raw_execution_guard import RawProcessingBusy, hold
    scope, raw = sys.argv[1], sys.argv[2]
    try:
        with hold(scope, raw):
            print("acquired")
    except RawProcessingBusy:
        print("busy")
    """
)
FD_SCAN = textwrap.dedent(
    """
    import fcntl, os, sys
    target = sys.argv[1]
    found = []
    for fd in range(0, 256):
        try:
            path = fcntl.fcntl(fd, fcntl.F_GETPATH, bytes(1024)).rstrip(b"\\0").decode()
        except OSError:
            continue
        if path == target:
            found.append(fd)
    print("inherited" if found else "clean")
    """
)


def python_env():
    return {
        **{k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "PYTHONPATH")},
        LOCK_DIRECTORY_ENVIRONMENT: os.environ[LOCK_DIRECTORY_ENVIRONMENT],
        "PYTHONPATH": os.pathsep.join(
            p
            for p in (os.environ.get("PYTHONPATH", ""), str(Path("src").resolve()))
            if p
        ),
        "PYTHONDONTWRITEBYTECODE": "1",
    }


def read_line(stream, deadline=DEADLINE_SECONDS):
    ready, _, _ = select.select([stream], [], [], deadline)
    assert ready, "the child did not answer within the deadline"
    return stream.readline().strip()


def probe(scope, raw, cwd=None):
    completed = subprocess.run(
        [sys.executable, "-c", PROBE, scope, raw],
        capture_output=True,
        text=True,
        timeout=DEADLINE_SECONDS,
        env=python_env(),
        cwd=cwd,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout.strip()


@pytest.fixture
def holder():
    processes = []

    def start(scope, raw):
        process = subprocess.Popen(
            [sys.executable, "-c", HOLDER, scope, raw],
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


def test_another_process_cannot_take_a_held_key_but_can_take_another(holder, tmp_path):
    holder(SCOPE, "raw-proc")
    assert probe(SCOPE, "raw-proc") == "busy"
    assert probe(SCOPE, "raw-proc", cwd=tmp_path) == "busy", (
        "cwd does not split the key"
    )
    assert probe(SCOPE, "raw-proc-other") == "acquired"
    assert probe("other.fibery.io/space-1", "raw-proc") == "acquired"


def test_release_by_the_holder_permits_acquisition(holder):
    process = holder(SCOPE, "raw-release")
    assert probe(SCOPE, "raw-release") == "busy"
    process.stdin.write("release\n")
    process.stdin.flush()
    assert read_line(process.stdout) == "released"
    process.wait(timeout=DEADLINE_SECONDS)
    assert probe(SCOPE, "raw-release") == "acquired"


def test_a_terminated_holder_leaves_no_permanent_busy_condition(holder):
    process = holder(SCOPE, "raw-crash")
    assert probe(SCOPE, "raw-crash") == "busy"
    process.kill()
    process.wait(timeout=DEADLINE_SECONDS)
    assert probe(SCOPE, "raw-crash") == "acquired"
    assert lock_path(SCOPE, "raw-crash").exists(), "the rendezvous file stays"


def test_the_lock_descriptor_is_not_inherited_by_a_runtime_child_process():
    with hold(SCOPE, "raw-inherit") as path:
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
        # And the child could not have kept the lock alive: the key is still
        # ours, and another process still sees it busy.
        assert probe(SCOPE, "raw-inherit") == "busy"
    assert probe(SCOPE, "raw-inherit") == "acquired"
