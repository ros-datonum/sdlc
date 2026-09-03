"""The `sdlc project requirement approve` and `rework` command surfaces.

Two decisions, two commands. The acknowledgement exists only where it can
mean something, and no model runtime is configured or touched on either path.
"""

from __future__ import annotations

import io

import pytest

from ready_fake import build_ready_workspace
from sdlc import cli
from sdlc.config import ENV_HOST, ENV_SPACE, ENV_SPACE_ID, ENV_TOKEN
from sdlc.results import ReadyDecisionResult
from sdlc.results import ReadyDecisionResultCode as Code

ENVIRONMENT = {
    ENV_HOST: "example.fibery.io",
    ENV_TOKEN: "test-token",
    ENV_SPACE: "SDLC",
    ENV_SPACE_ID: "space-uuid",
}


def render(result):
    stream = io.StringIO()
    cli.render_ready_result(result, stream)
    return stream.getvalue()


def approved(**changes):
    base = {
        "code": Code.REQUIREMENT_APPROVED,
        "message": "SDLC-FR-0031 approved at Review Result 1 with verdict BLOCKING.",
        "decision": "APPROVE",
        "requirement_id": "SDLC-FR-0031",
        "state": "Apply",
        "iteration": 1,
        "verdict": "BLOCKING",
    }
    return ReadyDecisionResult(**{**base, **changes})


# -- argument parsing -------------------------------------------------------


def test_approve_takes_a_requirement_and_an_optional_acknowledgement():
    arguments = cli.build_parser().parse_args(
        [
            "project",
            "requirement",
            "approve",
            "--requirement",
            "entity-uuid",
            "--acknowledge-verdict",
            "BLOCKING",
        ]
    )
    assert arguments.requirement == "entity-uuid"
    assert arguments.acknowledge_verdict == "BLOCKING"


def test_the_acknowledgement_is_optional():
    arguments = cli.build_parser().parse_args(
        ["project", "requirement", "approve", "--requirement", "x"]
    )
    assert arguments.acknowledge_verdict is None


@pytest.mark.parametrize("value", ["FORCE", "yes", "pass"])
def test_only_a_real_verdict_can_be_acknowledged(value):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            [
                "project",
                "requirement",
                "approve",
                "--requirement",
                "x",
                "--acknowledge-verdict",
                value,
            ]
        )


@pytest.mark.parametrize("flag", ["--force", "--override"])
def test_there_is_no_force_flag(flag):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            ["project", "requirement", "approve", "--requirement", "x", flag]
        )


def test_rework_takes_only_a_requirement():
    arguments = cli.build_parser().parse_args(
        ["project", "requirement", "rework", "--requirement", "entity-uuid"]
    )
    assert arguments.requirement == "entity-uuid"
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            [
                "project",
                "requirement",
                "rework",
                "--requirement",
                "x",
                "--acknowledge-verdict",
                "BLOCKING",
            ]
        )


@pytest.mark.parametrize("action", ["approve", "rework"])
def test_the_requirement_is_required(action):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["project", "requirement", action])


@pytest.mark.parametrize("action", ["approve", "rework"])
def test_decisions_take_no_runtime_or_model_override(action):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            [
                "project",
                "requirement",
                action,
                "--requirement",
                "x",
                "--runtime",
                "claude",
            ]
        )


def test_approve_and_rework_are_separate_commands():
    parser = cli.build_parser()
    approve = parser.parse_args(
        ["project", "requirement", "approve", "--requirement", "x"]
    )
    rework = parser.parse_args(
        ["project", "requirement", "rework", "--requirement", "x"]
    )
    assert approve.handler is not rework.handler
    assert (
        approve.handler
        is not parser.parse_args(
            ["project", "requirement", "review", "--requirement", "x"]
        ).handler
    )


# -- handlers ---------------------------------------------------------------


def run_command(monkeypatch, ws, argv):
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(cli, "_ready_workspace", lambda settings: ws)

    def no_model(*args, **kwargs):
        raise AssertionError("a Ready decision must not touch the model runtime")

    monkeypatch.setattr(cli, "LocalCliModelRuntime", no_model)
    monkeypatch.setattr(cli, "select_runtime", no_model)
    monkeypatch.setattr(cli, "load_model_runtime_config", no_model)
    out, error_out = io.StringIO(), io.StringIO()
    arguments = cli.build_parser().parse_args(argv)
    return arguments.handler(arguments, out, error_out), out, error_out


def test_approve_records_the_decision_and_exits_zero(monkeypatch):
    ws, requirement, _, _ = build_ready_workspace("BLOCKING")
    code, out, error_out = run_command(
        monkeypatch,
        ws,
        [
            "project",
            "requirement",
            "approve",
            "--requirement",
            requirement.id,
            "--acknowledge-verdict",
            "BLOCKING",
        ],
    )
    assert code == cli.EXIT_SUCCESS
    assert out.getvalue().startswith("REQUIREMENT_APPROVED\n")
    assert error_out.getvalue() == ""
    assert ws.requirements[requirement.id].state == "Apply"


def test_a_refused_approval_goes_to_stderr_and_exits_nonzero(monkeypatch):
    ws, requirement, _, _ = build_ready_workspace("BLOCKING")
    code, out, error_out = run_command(
        monkeypatch,
        ws,
        ["project", "requirement", "approve", "--requirement", requirement.id],
    )
    assert code == cli.EXIT_FAILURE
    assert out.getvalue() == ""
    assert error_out.getvalue().startswith("VERDICT_ACKNOWLEDGEMENT_REQUIRED\n")
    assert "--acknowledge-verdict BLOCKING" in error_out.getvalue()
    assert ws.requirements[requirement.id].state == "Ready"


def test_rework_records_the_decision_and_exits_zero(monkeypatch):
    ws, requirement, _, _ = build_ready_workspace("BLOCKING")
    code, out, _ = run_command(
        monkeypatch,
        ws,
        ["project", "requirement", "rework", "--requirement", requirement.id],
    )
    assert code == cli.EXIT_SUCCESS
    assert out.getvalue().startswith("REQUIREMENT_SENT_FOR_REWORK\n")
    assert ws.requirements[requirement.id].state == "Process"


def test_missing_configuration_stops_the_command_before_it_runs(monkeypatch):
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    ws, requirement, _, before = build_ready_workspace()
    arguments = cli.build_parser().parse_args(
        ["project", "requirement", "approve", "--requirement", requirement.id]
    )
    code = arguments.handler(arguments, io.StringIO(), io.StringIO())
    assert code == cli.EXIT_FAILURE
    assert ws.mutations[before:] == []


# -- output -----------------------------------------------------------------


def test_the_result_code_comes_first():
    assert render(approved()).startswith("REQUIREMENT_APPROVED\n")


def test_an_acknowledged_blocking_approval_is_a_successful_run():
    result = approved()
    assert result.is_normal
    assert "verdict BLOCKING" in render(result)


@pytest.mark.parametrize(
    ("code", "normal"),
    [
        (Code.REQUIREMENT_APPROVED, True),
        (Code.REQUIREMENT_SENT_FOR_REWORK, True),
        (Code.REQUIREMENT_ALREADY_APPROVED, True),
        (Code.REQUIREMENT_ALREADY_IN_REWORK, True),
        (Code.REQUIREMENT_NOT_IN_READY, False),
        (Code.REVIEW_RESULT_STALE, False),
        (Code.VERDICT_ACKNOWLEDGEMENT_REQUIRED, False),
        (Code.VERDICT_ACKNOWLEDGEMENT_MISMATCH, False),
        (Code.INVALID_VERDICT_ACKNOWLEDGEMENT, False),
        (Code.VALIDATION_FAILED, False),
    ],
)
def test_only_the_four_decision_outcomes_are_normal(code, normal):
    result = ReadyDecisionResult(code=code, message="m", decision="APPROVE")
    assert result.is_normal is normal


def test_a_refusal_needing_acknowledgement_shows_the_findings():
    output = render(
        approved(
            code=Code.VERDICT_ACKNOWLEDGEMENT_REQUIRED,
            message="The current Review verdict is BLOCKING.",
            state="Ready",
            blocking=("NOT_TESTABLE: no measurable threshold",),
            warnings=("confirmed Process finding [0]: still ambiguous",),
        )
    )
    assert "Blocking:" in output
    assert "no measurable threshold" in output
    assert "Warnings:" in output


def test_confirmed_relations_are_labelled_as_still_unwritten():
    output = render(approved(relations=("DEPENDS_ON SDLC-FR-0002: real",)))
    assert "still not written to Fibery" in output


def test_a_stale_refusal_lists_what_moved():
    output = render(
        approved(
            code=Code.REVIEW_RESULT_STALE,
            message="stale",
            state="Ready",
            details=("The Root Document was edited after the review.",),
        )
    )
    assert "Details:" in output
    assert "edited after the review" in output
