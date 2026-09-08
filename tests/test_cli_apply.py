"""The `sdlc project requirement apply` command surface."""

from __future__ import annotations

import io

import pytest

from apply_fake import build_apply_workspace, proposal
from sdlc import cli
from sdlc.config import ENV_HOST, ENV_SPACE, ENV_SPACE_ID, ENV_TOKEN
from sdlc.results import ApplyResult
from sdlc.results import ApplyResultCode as Code

ENVIRONMENT = {
    ENV_HOST: "example.fibery.io",
    ENV_TOKEN: "test-token",
    ENV_SPACE: "SDLC",
    ENV_SPACE_ID: "space-uuid",
}


def render(result):
    stream = io.StringIO()
    cli.render_apply_result(result, stream)
    return stream.getvalue()


def applied(**changes):
    base = {
        "code": Code.REQUIREMENT_APPLIED,
        "message": "SDLC-FR-0031 applied from Review Result 1; State is now Applied.",
        "requirement_id": "SDLC-FR-0031",
        "state": "Applied",
    }
    return ApplyResult(**{**base, **changes})


# -- argument parsing -------------------------------------------------------


def test_apply_takes_only_a_requirement():
    arguments = cli.build_parser().parse_args(
        ["project", "requirement", "apply", "--requirement", "entity-uuid"]
    )
    assert arguments.requirement == "entity-uuid"


def test_the_requirement_is_required():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["project", "requirement", "apply"])


@pytest.mark.parametrize(
    "extra",
    [
        ["--force"],
        ["--acknowledge-verdict", "PASS"],
        ["--runtime", "claude"],
        ["--model", "x"],
    ],
)
def test_no_force_acknowledgement_runtime_or_model_flag_exists(extra):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            ["project", "requirement", "apply", "--requirement", "x", *extra]
        )


def test_apply_is_its_own_command():
    parser = cli.build_parser()
    apply = parser.parse_args(["project", "requirement", "apply", "--requirement", "x"])
    approve = parser.parse_args(
        ["project", "requirement", "approve", "--requirement", "x"]
    )
    assert apply.handler is not approve.handler


# -- handler ----------------------------------------------------------------


def run_command(monkeypatch, ws, argv):
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(cli, "_ready_workspace", lambda settings: ws)

    def no_model(*args, **kwargs):
        raise AssertionError("Apply must not touch the model runtime")

    monkeypatch.setattr(cli, "LocalCliModelRuntime", no_model)
    monkeypatch.setattr(cli, "select_runtime", no_model)
    monkeypatch.setattr(cli, "load_model_runtime_config", no_model)
    out, error_out = io.StringIO(), io.StringIO()
    arguments = cli.build_parser().parse_args(argv)
    return arguments.handler(arguments, out, error_out), out, error_out


def test_apply_runs_and_exits_zero(monkeypatch):
    ws, requirement, _, _ = build_apply_workspace(proposals=(proposal(),))
    code, out, error_out = run_command(
        monkeypatch,
        ws,
        ["project", "requirement", "apply", "--requirement", requirement.id],
    )
    assert code == cli.EXIT_SUCCESS
    assert out.getvalue().startswith("REQUIREMENT_APPLIED\n")
    assert "DEPENDS_ON SDLC-FR-0002" in out.getvalue()
    assert "Requirements/" not in out.getvalue()
    assert error_out.getvalue() == ""
    assert ws.requirements[requirement.id].state == "Applied"


def test_a_refusal_goes_to_stderr_and_exits_nonzero(monkeypatch):
    ws, requirement, root, _ = build_apply_workspace()
    ws.content[root.secret] += "\nEdited.\n"
    code, out, error_out = run_command(
        monkeypatch,
        ws,
        ["project", "requirement", "apply", "--requirement", requirement.id],
    )
    assert code == cli.EXIT_FAILURE
    assert out.getvalue() == ""
    assert error_out.getvalue().startswith("REVIEW_RESULT_STALE\n")


def test_missing_configuration_stops_the_command_before_it_runs(monkeypatch):
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    ws, requirement, _, before = build_apply_workspace()
    arguments = cli.build_parser().parse_args(
        ["project", "requirement", "apply", "--requirement", requirement.id]
    )
    assert (
        arguments.handler(arguments, io.StringIO(), io.StringIO()) == cli.EXIT_FAILURE
    )
    assert ws.mutations[before:] == []


# -- output -----------------------------------------------------------------


def test_the_result_code_comes_first():
    assert render(applied()).startswith("REQUIREMENT_APPLIED\n")


@pytest.mark.parametrize(
    ("code", "normal"),
    [
        (Code.REQUIREMENT_APPLIED, True),
        (Code.REQUIREMENT_ALREADY_APPLIED, True),
        (Code.PARTIAL_APPLY, False),
        (Code.REVIEW_RESULT_STALE, False),
        (Code.INVALID_REVIEW_RESULT, False),
        (Code.RELATION_TARGET_NOT_FOUND, False),
        (Code.INVALID_RELATION_TARGET, False),
        (Code.VALIDATION_FAILED, False),
    ],
)
def test_only_the_two_completed_outcomes_are_normal(code, normal):
    assert ApplyResult(code=code, message="m").is_normal is normal


def test_a_partial_apply_lists_what_was_left_in_place():
    output = render(
        ApplyResult(
            code=Code.PARTIAL_APPLY,
            message="did not complete",
            created=("relation DEPENDS_ON SDLC-FR-0002",),
            details=("FIBERY_WRITE_FAILED", "Could not add AFFECTS SDLC-FR-0003."),
        )
    )
    assert "left in place" in output
    assert "relation DEPENDS_ON SDLC-FR-0002" in output
    assert "FIBERY_WRITE_FAILED" in output
