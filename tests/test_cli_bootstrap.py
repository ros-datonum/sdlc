"""RW-B04: the `sdlc project bootstrap` command surface.

The handler runs the real composition over the in-memory Fibery fakes and a
real temporary directory, so these tests prove the CLI wiring rather than a
second copy of the bootstrap semantics. No model runtime is constructed and no
live workspace is touched.
"""

from __future__ import annotations

import io
import pathlib

import pytest

from sdlc import cli
from sdlc.config import ENV_HOST, ENV_SPACE, ENV_SPACE_ID, ENV_TOKEN
from sdlc.consumer_template import MANAGED_PATHS
from sdlc.project_bootstrap import BootstrapCode, BootstrapResult
from test_project_bootstrap import (
    CODE,
    CONTEXT_BYTES,
    NAME,
    RAW_SOURCE,
    linked_workspaces,
)

ENVIRONMENT = {
    ENV_HOST: "example.fibery.io",
    ENV_TOKEN: "test-token",
    ENV_SPACE: "SDLC",
    ENV_SPACE_ID: "space-uuid",
}


@pytest.fixture
def exports(tmp_path):
    requirements = tmp_path / "raw-requirements.md"
    requirements.write_text(RAW_SOURCE, encoding="utf-8")
    context = tmp_path / "project-context.md"
    context.write_bytes(CONTEXT_BYTES)
    return requirements, context


def parse(*arguments):
    return cli.build_parser().parse_args(["project", "bootstrap", *arguments])


def run_command(monkeypatch, exports, *extra, workspaces=None, chdir=None):
    """Invoke the real handler with the Fibery adapters replaced by fakes."""
    requirements, context = exports
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    pair = workspaces or linked_workspaces()
    monkeypatch.setattr(cli, "_bootstrap_workspaces", lambda settings: pair)

    def no_model(*args, **options):
        raise AssertionError("bootstrap must not touch the model runtime")

    monkeypatch.setattr(cli, "LocalCliModelRuntime", no_model)
    monkeypatch.setattr(cli, "load_model_runtime_config", no_model)
    if chdir is not None:
        monkeypatch.chdir(chdir)
    out, error_out = io.StringIO(), io.StringIO()
    arguments = parse(
        "--name",
        NAME,
        "--requirements",
        str(requirements),
        "--context",
        str(context),
        *extra,
    )
    code = arguments.handler(arguments, out, error_out)
    return code, out.getvalue(), error_out.getvalue(), pair


# -- the command surface -------------------------------------------------------------


def test_bootstrap_takes_the_three_required_and_three_optional_arguments():
    arguments = parse(
        "--name",
        NAME,
        "--requirements",
        "raw.md",
        "--context",
        "context.md",
        "--target",
        "somewhere",
        "--code",
        CODE,
        "--description",
        "A project.",
    )

    assert arguments.handler is cli._run_project_bootstrap
    assert arguments.name == NAME
    assert arguments.requirements == "raw.md"
    assert arguments.context == "context.md"
    assert arguments.target == "somewhere"
    assert arguments.code == CODE
    assert arguments.description == "A project."


@pytest.mark.parametrize("missing", ["--name", "--requirements", "--context"])
def test_every_export_argument_is_required(missing):
    supplied = {
        "--name": NAME,
        "--requirements": "raw.md",
        "--context": "context.md",
    }
    del supplied[missing]
    flat = [item for pair in supplied.items() for item in pair]

    with pytest.raises(SystemExit):
        parse(*flat)


def test_the_optional_arguments_default_to_none():
    arguments = parse(
        "--name", NAME, "--requirements", "raw.md", "--context", "context.md"
    )

    assert arguments.target is None
    assert arguments.code is None
    assert arguments.description is None


@pytest.mark.parametrize(
    "extra",
    [
        ["--model", "x"],
        ["--runtime", "claude"],
        ["--force"],
        ["--overwrite"],
        ["--repair"],
        ["--process"],
        ["--start"],
        ["--retry"],
        ["--cleanup"],
        ["--approve"],
        ["--state", "Process"],
    ],
)
def test_no_override_or_lifecycle_flag_exists(extra):
    with pytest.raises(SystemExit):
        parse(
            "--name",
            NAME,
            "--requirements",
            "raw.md",
            "--context",
            "context.md",
            *extra,
        )


def test_the_help_states_that_nothing_is_reinterpreted_and_raw_stops_at_draft(capsys):
    with pytest.raises(SystemExit):
        cli.main(["project", "bootstrap", "--help"])

    text = " ".join(capsys.readouterr().out.split())
    assert "no model runs" in text
    assert "stops at Draft" in text


# -- running -------------------------------------------------------------------------


def test_an_explicit_target_is_bootstrapped_and_exits_zero(
    monkeypatch, exports, tmp_path
):
    target = tmp_path / "consumer"
    target.mkdir()

    code, out, error_out, _ = run_command(monkeypatch, exports, "--target", str(target))

    assert code == cli.EXIT_SUCCESS
    assert out.startswith(f"{BootstrapCode.PROJECT_BOOTSTRAPPED.value}\n")
    assert error_out == ""
    assert {
        str(path.relative_to(target)) for path in target.rglob("*") if path.is_file()
    } == set(MANAGED_PATHS)


def test_the_current_directory_is_used_when_no_target_is_given(
    monkeypatch, exports, tmp_path
):
    target = tmp_path / "cwd-consumer"
    target.mkdir()

    code, _out, _, _ = run_command(monkeypatch, exports, chdir=target)

    assert code == cli.EXIT_SUCCESS
    assert (target / ".sdlc/project.yaml").is_file()
    assert (target / "AGENTS.md").is_file()


def test_a_rerun_exits_zero_and_reports_already_bootstrapped(
    monkeypatch, exports, tmp_path
):
    target = tmp_path / "consumer"
    target.mkdir()
    pair = linked_workspaces()
    run_command(monkeypatch, exports, "--target", str(target), workspaces=pair)

    code, out, _, _ = run_command(
        monkeypatch, exports, "--target", str(target), workspaces=pair
    )

    assert code == cli.EXIT_SUCCESS
    assert out.startswith(f"{BootstrapCode.PROJECT_ALREADY_BOOTSTRAPPED.value}\n")


def test_a_conflict_exits_non_zero_and_reports_on_stderr(
    monkeypatch, exports, tmp_path
):
    target = tmp_path / "consumer"
    (target / ".sdlc").mkdir(parents=True)
    (target / ".sdlc/project.yaml").write_bytes(
        b'version: 1\nproject:\n  name: "Other"\n'
    )

    code, out, error_out, _ = run_command(monkeypatch, exports, "--target", str(target))

    assert code == cli.EXIT_FAILURE
    assert out == ""
    assert error_out.startswith(f"{BootstrapCode.BOOTSTRAP_CONFLICT.value}\n")


def test_missing_fibery_configuration_stops_before_any_work(
    monkeypatch, exports, tmp_path
):
    for name in ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    requirements, context = exports
    built = []
    monkeypatch.setattr(
        cli, "_bootstrap_workspaces", lambda settings: built.append(settings)
    )
    out, error_out = io.StringIO(), io.StringIO()
    arguments = parse(
        "--name", NAME, "--requirements", str(requirements), "--context", str(context)
    )

    assert arguments.handler(arguments, out, error_out) == cli.EXIT_FAILURE
    assert built == []


def test_both_workspace_adapters_share_one_client_and_settings(monkeypatch, exports):
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    clients, adapters = [], []

    class RecordingClient:
        def __init__(self, settings):
            self.settings = settings
            clients.append(self)

    def project_adapter(client, space, space_id):
        adapters.append(("project", client, space, space_id))
        return "project-workspace"

    def requirement_adapter(client, space, space_id):
        adapters.append(("requirement", client, space, space_id))
        return "requirement-workspace"

    monkeypatch.setattr(cli, "FiberyClient", RecordingClient)
    monkeypatch.setattr(cli, "FiberyHttpWorkspace", project_adapter)
    monkeypatch.setattr(cli, "FiberyRequirementWorkspace", requirement_adapter)
    captured = {}

    def record_bootstrap(project_workspace, requirement_workspace, **options):
        captured["workspaces"] = (project_workspace, requirement_workspace)
        return BootstrapResult(BootstrapCode.PROJECT_BOOTSTRAPPED, "done")

    monkeypatch.setattr(cli, "bootstrap_project", record_bootstrap)
    requirements, context = exports
    arguments = parse(
        "--name", NAME, "--requirements", str(requirements), "--context", str(context)
    )

    assert (
        arguments.handler(arguments, io.StringIO(), io.StringIO()) == cli.EXIT_SUCCESS
    )
    assert len(clients) == 1, "one client for both adapters"
    assert [kind for kind, *_ in adapters] == ["project", "requirement"]
    assert {client for _, client, *_ in adapters} == {clients[0]}
    assert {(space, space_id) for *_, space, space_id in adapters} == {
        (ENVIRONMENT[ENV_SPACE], ENVIRONMENT[ENV_SPACE_ID])
    }
    assert captured["workspaces"] == ("project-workspace", "requirement-workspace")


# -- output ---------------------------------------------------------------------------


def test_the_report_names_the_identity_and_the_managed_paths(
    monkeypatch, exports, tmp_path
):
    target = tmp_path / "consumer"
    target.mkdir()

    _, out, _, _ = run_command(monkeypatch, exports, "--target", str(target))

    assert NAME in out
    assert CODE in out
    for relative in MANAGED_PATHS:
        assert relative in out


def test_the_report_never_prints_the_raw_or_context_body(
    monkeypatch, exports, tmp_path
):
    target = tmp_path / "consumer"
    target.mkdir()

    _, out, error_out, _ = run_command(monkeypatch, exports, "--target", str(target))

    printed = out + error_out
    assert "Ship a thing" not in printed
    assert "What this project is about" not in printed
    assert ENVIRONMENT[ENV_TOKEN] not in printed


def test_a_partial_outcome_is_rendered_with_its_failed_step():
    result = BootstrapResult(
        code=BootstrapCode.PARTIAL_BOOTSTRAP,
        message="Project Init reported FIBERY_WRITE_FAILED.",
        target="/tmp/consumer",
        project_name=NAME,
        project_code=CODE,
        local_created=("AGENTS.md",),
        details=("Could not create the Project entity.",),
    )
    stream = io.StringIO()

    cli.render_bootstrap_result(result, stream)

    printed = stream.getvalue()
    assert printed.startswith(f"{BootstrapCode.PARTIAL_BOOTSTRAP.value}\n")
    assert "AGENTS.md" in printed
    assert "Could not create the Project entity." in printed


def test_only_the_two_normal_outcomes_are_normal():
    for code in BootstrapCode:
        result = BootstrapResult(code=code, message="m")
        assert result.is_normal is (
            code
            in (
                BootstrapCode.PROJECT_BOOTSTRAPPED,
                BootstrapCode.PROJECT_ALREADY_BOOTSTRAPPED,
            )
        )


def test_the_bootstrap_command_is_not_the_init_command():
    parser = cli.build_parser()
    bootstrap = parser.parse_args(
        [
            "project",
            "bootstrap",
            "--name",
            NAME,
            "--requirements",
            "r.md",
            "--context",
            "c.md",
        ]
    )
    init = parser.parse_args(["project", "init", "--name", NAME])

    assert bootstrap.handler is not init.handler
    assert pathlib.Path(str(bootstrap.requirements)).name == "r.md"
