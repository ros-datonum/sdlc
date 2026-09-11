"""RW-O03: the `sdlc worker run` command surface.

The handler runs the real runner and the real workspace lock over the Fibery
fakes of tests/test_requirement_runner.py. The idle sleep is replaced by one
that stops the run the way an operator does, with Ctrl-C, so no test loops or
waits. No model runtime is ever launched: the runtime factory is replaced by
one that only records the configured role it was built for.
"""

from __future__ import annotations

import io

import pytest

from apply_fake import build_apply_workspace, proposal
from sdlc import cli
from sdlc.config import ENV_HOST, ENV_SPACE, ENV_SPACE_ID, ENV_TOKEN
from sdlc.model_runtime_config import (
    RAW_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_REVIEWER_ROLE,
    ModelRuntimeConfigError,
)
from sdlc.requirement_runner import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    CycleOutcome,
    CycleReport,
    RunnerCode,
)
from sdlc.worker_runner_guard import hold_workspace
from test_requirement_runner import (
    PROCESSING,
    SUCCEEDED,
    only_eligible,
    record,
    workspace_of,
)

ENVIRONMENT = {
    ENV_HOST: "example.fibery.io",
    ENV_TOKEN: "test-token",
    ENV_SPACE: "SDLC",
    ENV_SPACE_ID: "space-uuid",
}


def parse(*extra):
    return cli.build_parser().parse_args(["worker", "run", *extra])


class RecordedModel:
    """Stands in for a configured model runtime; it must never be asked."""

    def __init__(self, selection):
        self.selection = selection

    def run(self, prompt, context=""):
        raise AssertionError("no model may run in these tests")


class CtrlCAtIdle:
    """The idle sleep, replaced: the first idle wait is the operator's Ctrl-C."""

    def __init__(self):
        self.calls = []

    def __call__(self, seconds):
        self.calls.append(seconds)
        raise KeyboardInterrupt


def run_worker(monkeypatch, ws, *extra):
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    built, models = [], []

    def workspace(settings):
        built.append(settings)
        return ws

    def model(selection):
        models.append(RecordedModel(selection))
        return models[-1]

    sleep = CtrlCAtIdle()
    monkeypatch.setattr(cli, "_runner_workspace", workspace)
    monkeypatch.setattr(cli, "LocalCliModelRuntime", model)
    monkeypatch.setattr(cli, "_sleep", sleep)
    out, error_out = io.StringIO(), io.StringIO()
    arguments = parse(*extra)
    code = arguments.handler(arguments, out, error_out)
    return code, out.getvalue(), error_out.getvalue(), sleep.calls, built, models


# -- the command surface -------------------------------------------------------------


def test_worker_run_exists_with_the_default_interval():
    arguments = parse()

    assert arguments.handler is cli._run_worker
    assert arguments.poll_interval_seconds == DEFAULT_POLL_INTERVAL_SECONDS == 5


@pytest.mark.parametrize("value", ["1", "7", "3600"])
def test_a_whole_interval_at_or_above_the_minimum_is_accepted(value):
    assert parse("--poll-interval-seconds", value).poll_interval_seconds == int(value)


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "five", "", "1e1"])
def test_every_other_interval_is_rejected(value, capsys):
    with pytest.raises(SystemExit) as exited:
        parse("--poll-interval-seconds", value)

    assert exited.value.code == 2
    assert "whole number of seconds" in capsys.readouterr().err


@pytest.mark.parametrize(
    "extra",
    [
        ["--runtime", "claude"],
        ["--model", "x"],
        ["--requirement", "entity-uuid"],
        ["--project", "SDLC"],
        ["--type", "Raw"],
        ["--state", "Process"],
        ["--status", "Not Processed"],
        ["--processing-status", "Failed"],
        ["--acknowledge-verdict", "PASS"],
        ["--approve"],
        ["--payload", "{}"],
        ["--force"],
        ["--daemon"],
    ],
)
def test_no_override_flag_exists(extra):
    with pytest.raises(SystemExit):
        parse(*extra)


def test_the_help_states_the_one_time_setup(capsys):
    with pytest.raises(SystemExit):
        cli.main(["worker", "run", "--help"])

    text = " ".join(capsys.readouterr().out.split())
    assert "docs/fibery/Worker-Runner-Setup-v0.1.md" in text
    assert "One runner per workspace" in text


# -- running ------------------------------------------------------------------------


def test_the_runner_uses_the_configured_workspace_and_stops_on_ctrl_c(monkeypatch):
    ws = workspace_of()

    code, out, error_out, sleeps, built, _ = run_worker(monkeypatch, ws)

    assert code == cli.EXIT_INTERRUPTED
    assert out.startswith(f"{RunnerCode.WORKER_RUNNER_STARTED.value}\n")
    assert RunnerCode.WORKER_RUNNER_STOPPED.value in out
    assert error_out == ""
    assert sleeps == [DEFAULT_POLL_INTERVAL_SECONDS]
    [settings] = built
    assert (settings.host, settings.space, settings.space_id) == (
        "example.fibery.io",
        "SDLC",
        "space-uuid",
    )
    assert ws.mutations == []


def test_the_explicit_interval_reaches_the_idle_sleep(monkeypatch):
    _, _, _, sleeps, _, _ = run_worker(
        monkeypatch, workspace_of(), "--poll-interval-seconds", "9"
    )

    assert sleeps == [9]


def test_the_model_roles_are_the_configured_ones_and_no_model_runs(monkeypatch):
    _, _, _, _, _, models = run_worker(monkeypatch, workspace_of())

    assert [m.selection.role for m in models] == [
        RAW_REQUIREMENT_PROCESSOR_ROLE,
        STANDARD_REQUIREMENT_PROCESSOR_ROLE,
        STANDARD_REQUIREMENT_REVIEWER_ROLE,
    ]


def test_a_state_driven_apply_runs_without_a_manual_command(monkeypatch):
    inner, requirement, root, _ = build_apply_workspace(proposals=(proposal(),))
    ws = only_eligible(inner, requirement.id)

    code, out, error_out, sleeps, _, _ = run_worker(monkeypatch, ws)

    assert code == cli.EXIT_INTERRUPTED
    assert f"\n{CycleOutcome.SUCCEEDED.value}\n" in out
    assert "Dispatch: ROUTE_COMPLETED; worker result REQUIREMENT_APPLIED" in out
    assert f"(entity {requirement.id})" in out
    assert error_out == ""
    assert sleeps == [DEFAULT_POLL_INTERVAL_SECONDS], "idle only after the work"
    assert inner.requirements[requirement.id].state == "Applied"
    assert ws.status_of(requirement.id) == SUCCEEDED
    # Output safety: identity and codes, never Requirement content or secrets.
    printed = out + error_out
    assert requirement.requirement_id in printed
    assert requirement.title not in printed
    prose = [line for line in inner.content[root.secret].splitlines() if len(line) > 20]
    assert prose and not any(line in printed for line in prose)
    assert ENVIRONMENT[ENV_TOKEN] not in printed


def test_ctrl_c_during_a_worker_leaves_its_claim_as_it_is(monkeypatch):
    ws = workspace_of(record("r-1", 1, "Standard", "Apply"))

    def interrupted(workspace, entity_id):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "apply_standard_requirement", interrupted)
    code, out, _, sleeps, _, _ = run_worker(monkeypatch, ws)

    assert code == cli.EXIT_INTERRUPTED
    assert RunnerCode.WORKER_RUNNER_STOPPED.value in out
    assert sleeps == []
    assert ws.status_of("r-1") == PROCESSING, "not rewritten, not reset"
    assert ws.mutations == ["set_processing_status r-1 Processing"]
    with hold_workspace(ws.lock_scope):
        pass  # the kernel released the lock with the handler's block


# -- refusals -----------------------------------------------------------------------


def test_a_second_runner_is_refused_visibly_and_touches_nothing(monkeypatch):
    ws = workspace_of(record("r-1", 1, "Raw", "Process"))

    with hold_workspace(ws.lock_scope):
        code, out, error_out, sleeps, _, _ = run_worker(monkeypatch, ws)

    assert code == cli.EXIT_FAILURE
    assert error_out.startswith(f"{RunnerCode.WORKER_RUNNER_BUSY.value}\n")
    assert out == ""
    assert ws.calls == [] and ws.mutations == [] and sleeps == []


def test_a_preflight_failure_starts_no_worker(monkeypatch):
    ws = workspace_of(record("r-1", 1, "Raw", "Process"), options=None)

    code, out, error_out, sleeps, _, _ = run_worker(monkeypatch, ws)

    assert code == cli.EXIT_FAILURE
    assert error_out.startswith(f"{RunnerCode.WORKER_RUNNER_PREFLIGHT_FAILED.value}\n")
    assert "docs/fibery/Worker-Runner-Setup-v0.1.md" in error_out
    assert RunnerCode.WORKER_RUNNER_STARTED.value not in out
    assert ws.calls == ["validate_processing_status_field"]
    assert ws.mutations == [] and sleeps == []
    with hold_workspace(ws.lock_scope):
        pass  # released on the refusal too


def test_a_runtime_configuration_error_claims_nothing(monkeypatch):
    ws = workspace_of(record("r-1", 1, "Raw", "Process"))

    def broken():
        raise ModelRuntimeConfigError("No runtime configured for role 'x'.")

    monkeypatch.setattr(cli, "load_model_runtime_config", broken)
    code, _, error_out, sleeps, _, _ = run_worker(monkeypatch, ws)

    assert code == cli.EXIT_FAILURE
    assert error_out.startswith(
        f"{RunnerCode.WORKER_RUNNER_CONFIGURATION_INVALID.value}\n"
    )
    assert ws.calls == [] and sleeps == []


def test_missing_fibery_configuration_builds_no_workspace(monkeypatch):
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    built = []
    monkeypatch.setattr(cli, "_runner_workspace", built.append)
    out, error_out = io.StringIO(), io.StringIO()
    arguments = parse()

    assert arguments.handler(arguments, out, error_out) == cli.EXIT_FAILURE
    assert error_out.getvalue().startswith(
        RunnerCode.WORKER_RUNNER_CONFIGURATION_INVALID.value
    )
    assert built == []


# -- rendering ----------------------------------------------------------------------


def test_an_idle_cycle_prints_nothing():
    out, error_out = io.StringIO(), io.StringIO()

    cli.render_cycle(CycleReport(CycleOutcome.IDLE, "idle"), out, error_out)

    assert out.getvalue() == error_out.getvalue() == ""


def test_an_abnormal_cycle_goes_to_stderr_with_its_identity():
    requirement = record("r-1", 1, "Standard", "Review", processing_status=PROCESSING)
    out, error_out = io.StringIO(), io.StringIO()

    cli.render_cycle(
        CycleReport(CycleOutcome.PARTIAL, "left as observed", requirement),
        out,
        error_out,
    )

    assert out.getvalue() == ""
    printed = error_out.getvalue()
    assert printed.startswith(f"\n{CycleOutcome.PARTIAL.value}\n")
    assert "SDLC-FR-0001 (entity r-1)" in printed
    assert "Processing Status Processing" in printed
    assert requirement.title not in printed
