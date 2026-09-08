import io

import pytest

from sdlc import cli
from sdlc.config import (
    ENV_HOST,
    ENV_SPACE,
    ENV_SPACE_ID,
    ENV_TIMEOUT_SECONDS,
    ENV_TOKEN,
    ConfigurationError,
    load_fibery_settings,
)
from sdlc.results import InitResult, ResultCode

COMPLETE_ENVIRONMENT = {
    ENV_HOST: "example.fibery.io",
    ENV_TOKEN: "test-token",
    ENV_SPACE: "SDLC",
    ENV_SPACE_ID: "space-uuid",
}


def render(result):
    stream = io.StringIO()
    cli.render_result(result, stream)
    return stream.getvalue()


# -- argument parsing ------------------------------------------------------


def test_project_init_accepts_the_specified_options():
    arguments = cli.build_parser().parse_args(
        ["project", "init", "--name", "SDLC", "--code", "SDLC", "--description", "x"]
    )

    assert (arguments.name, arguments.code, arguments.description) == (
        "SDLC",
        "SDLC",
        "x",
    )


def test_name_is_required():
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(["project", "init"])


def test_code_and_description_are_optional():
    arguments = cli.build_parser().parse_args(["project", "init", "--name", "SDLC"])

    assert arguments.code is None
    assert arguments.description is None


# -- rendering -------------------------------------------------------------


def test_initialized_output_leads_with_the_result_code_and_names_no_folders():
    output = render(
        InitResult(
            code=ResultCode.PROJECT_INITIALIZED,
            message="ok",
            project_name="SDLC",
            project_code="SDLC",
        )
    )

    assert output.splitlines()[0] == "PROJECT_INITIALIZED"
    assert "Name: SDLC" in output
    assert "State: Planned" in output
    assert "Documents:" not in output
    assert "Requirements/" not in output


def test_already_exists_output_says_nothing_was_changed():
    output = render(
        InitResult(
            code=ResultCode.PROJECT_ALREADY_EXISTS,
            message='Project "SDLC" already exists.',
            project_name="SDLC",
            project_code="SDLC",
        )
    )

    assert output.splitlines()[0] == "PROJECT_ALREADY_EXISTS"
    assert "No changes were made." in output
    assert "sdlc project requirement add" in output


def test_partial_init_output_reports_created_and_failed():
    output = render(
        InitResult(
            code=ResultCode.PARTIAL_INIT,
            message="partial",
            project_name="SDLC",
            created=("Project entity project-1",),
            failed=("DOCUMENT_STRUCTURE_CREATE_FAILED",),
            details=("Could not create 'SDLC/Requirements'.",),
        )
    )

    assert output.splitlines()[0] == "PARTIAL_INIT"
    assert "Project entity project-1" in output
    assert "DOCUMENT_STRUCTURE_CREATE_FAILED" in output
    assert "Could not create 'SDLC/Requirements'." in output


@pytest.mark.parametrize(
    ("code", "normal"),
    [
        (ResultCode.PROJECT_INITIALIZED, True),
        (ResultCode.PROJECT_ALREADY_EXISTS, True),
        (ResultCode.PARTIAL_INIT, False),
        (ResultCode.VALIDATION_FAILED, False),
        (ResultCode.INVALID_INPUT, False),
    ],
)
def test_only_the_two_specified_outcomes_are_normal(code, normal):
    result = InitResult(code=code, message="", project_name="SDLC")

    assert result.is_normal is normal


# -- configuration ---------------------------------------------------------


def test_settings_are_read_from_the_environment():
    settings = load_fibery_settings(COMPLETE_ENVIRONMENT)

    assert settings.base_url == "https://example.fibery.io"
    assert settings.space_id == "space-uuid"


@pytest.mark.parametrize("missing", sorted(COMPLETE_ENVIRONMENT))
def test_missing_configuration_names_the_variable(missing):
    environment = {k: v for k, v in COMPLETE_ENVIRONMENT.items() if k != missing}

    with pytest.raises(ConfigurationError, match=missing):
        load_fibery_settings(environment)


def test_missing_configuration_stops_the_command_before_it_runs(monkeypatch):
    for name in COMPLETE_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)

    assert cli.main(["project", "init", "--name", "SDLC"]) == cli.EXIT_FAILURE


@pytest.mark.parametrize("value", ["not-a-number", "0", "-1"])
def test_invalid_timeout_is_rejected(value):
    with pytest.raises(ConfigurationError, match=ENV_TIMEOUT_SECONDS):
        load_fibery_settings({**COMPLETE_ENVIRONMENT, ENV_TIMEOUT_SECONDS: value})
