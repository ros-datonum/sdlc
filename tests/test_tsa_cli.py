"""I12 — `sdlc project architecture` through the real `cli.main`.

Every command runs the real I04-I11 code over the in-memory workspaces the
domain suites already use: the scenes are left by the real I04 bootstrap, the
real I05 start, the real I07 and I08 stages, and the real I11 decisions, or a
hand-sealed I01 artifact where a test needs a durable state no command
reaches. Only Fibery and the two models are fakes, and the model runtime
factory only hands out the scene's recording models, so nothing here touches
live Fibery, a model, authentication or the worker: every claim is D-class.

Expected codes come from constants transcribed from the frozen spec (13.6,
13.8, v0.5 section 2) and the approved addition, never from the mapping under
test.
"""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from architect_fake import (
    RecordingModel,
    payload_of,
    process_id,
    resealed_carrier,
    reset_trace,
)
from architecture_fake import PROJECT_TYPE_ID
from recovery_fake import CoveringReviewer, decide, reviewed_scene
from reviewer_fake import (
    accepted_scene,
    applied_scene,
    decision_id,
    finding,
    review_id,
)
from sdlc import cli, requirement_dispatcher, requirement_runner, tsa_cli, tsa_recovery
from sdlc.config import ENV_HOST, ENV_SPACE, ENV_TOKEN
from sdlc.fibery_workspace import FiberyError, ProjectRecord
from sdlc.model_runtime import ModelRuntimeError
from sdlc.model_runtime_config import (
    TSA_ARCHITECT_ROLE,
    TSA_REVIEWER_ROLE,
    ModelRuntimeConfigError,
    load_model_runtime_config,
    select_runtime,
)
from sdlc.raw_execution_guard import LOCK_DIRECTORY_ENVIRONMENT
from sdlc.tsa_admission import AdmissionResultCode
from sdlc.tsa_architect import (
    REVIEW_BLOCKED_ON_WHAT,
    REVIEW_COVERAGE_DUPLICATE,
    REVIEW_COVERAGE_INCOMPLETE,
    REVIEW_STRUCTURALLY_INVALID,
    ArchitectResultCode,
)
from sdlc.tsa_architecture import ArchitectureResultCode
from sdlc.tsa_cli import TsaResultCode, exit_code_for
from sdlc.tsa_cycle import CycleResultCode
from sdlc.tsa_decision import DecisionResultCode
from sdlc.tsa_recovery import message_after_progress
from sdlc.tsa_reviewer import ReviewerRefused, ReviewerResultCode, run_reviewer_stage
from sdlc.worker_runner_guard import hold_workspace
from standard_fake import REQUIREMENT_ID
from test_tsa_admission import (
    APPLICABLE,
    ARCHITECTURE_ID,
    CYCLE,
    MANIFEST_ID,
    PROJECT_CODE,
    PROJECT_ID,
    PUBLIC_ID,
    UX_DOCUMENT_ID,
    UX_REASON,
    accepted_manifest_carrier,
    bootstrap_carrier,
    child_added_after_review,
    fail,
    landed_with,
    root_edited_after_review,
    world,
)
from test_tsa_architect import other_architecture, persisted_but_not_applied, reseal
from test_tsa_cycle import fixed_clock
from test_tsa_decision import acceptance_bound_elsewhere, process_ref, review_ref
from test_tsa_reviewer import is_review_carrier

REPOSITORY = Path(__file__).resolve().parents[1]
SPEC_V03 = REPOSITORY / "docs/specs/TSA-C01-Implementation-Spec-v0.3.md"
SPEC_V05 = REPOSITORY / "docs/specs/TSA-C01-Implementation-Spec-v0.5.md"
SPEC_V06 = REPOSITORY / "docs/specs/TSA-C01-Implementation-Spec-v0.6.md"

ENVIRONMENT = {
    ENV_HOST: "example.fibery.io",
    ENV_TOKEN: "test-token",
    ENV_SPACE: "SDLC",
}
PROJECT = ProjectRecord(
    id=PROJECT_ID, name="SDLC", code=PROJECT_CODE, state="Planned", public_id=PUBLIC_ID
)
PROCESS_ID = process_id(1)
REVIEW_ID = review_id(1)
DECISION_ID = decision_id(1)
CREATE = "create_tsa_child_document"
WRITE = "write_document_content"

#: Spec 13.8 exit class 0, transcribed. Everything else is exit 1.
SPEC_NORMAL = {
    "ARCHITECTURE_CYCLE_STARTED",
    "ARCHITECTURE_CYCLE_RESUMED",
    "ARCHITECTURE_REVIEW_READY",
    "ARCHITECTURE_REWORK_RECORDED",
    "ARCHITECTURE_APPROVED",
    "DECISION_ALREADY_RECORDED",
    "CYCLE_APPROVED",
    "INSPECT_CURRENT",
    "INSPECT_STALE",
    "INSPECT_INCOMPLETE",
}


def expected_exit(code: str) -> int:
    return 0 if code in SPEC_NORMAL else 1


# --------------------------------------------------------------------------
# The harness: real cli.main, fake adapters and models
# --------------------------------------------------------------------------


class Projects:
    """The Project Code lookup the CLI reuses, over the scene's one Project."""

    def __init__(self, error: FiberyError | None = None) -> None:
        self.lookups: list[str] = []
        self.error = error

    def find_project_by_code(self, code: str) -> ProjectRecord | None:
        self.lookups.append(code)
        if self.error is not None:
            raise self.error
        return PROJECT if code == PROJECT_CODE else None


@dataclass
class Run:
    exit_code: int
    out: str
    err: str
    roles: list[str]

    @property
    def stream(self) -> str:
        return self.out if self.exit_code == 0 else self.err

    @property
    def code(self) -> str:
        return self.stream.splitlines()[0]


@dataclass
class Cli:
    """One scene, the models it hands out, and every TSA role configured."""

    scene: object
    capsys: pytest.CaptureFixture[str]
    architect: RecordingModel
    reviewer: CoveringReviewer
    projects: Projects = field(default_factory=Projects)
    roles: list[str] = field(default_factory=list)
    built: int = 0

    def runtime(self, selection) -> RecordingModel:
        self.roles.append(selection.role)
        return {TSA_ARCHITECT_ROLE: self.architect, TSA_REVIEWER_ROLE: self.reviewer}[
            selection.role
        ]

    def workspaces(self, settings):
        self.built += 1
        return self.projects, self.scene.tsa, self.scene.req

    def __call__(self, *argv: str) -> Run:
        exit_code = cli.main(["project", "architecture", *argv])
        captured = self.capsys.readouterr()
        return Run(exit_code, captured.out, captured.err, list(self.roles))

    @property
    def model_calls(self) -> tuple[int, int]:
        return len(self.architect.calls), len(self.reviewer.calls)


@pytest.fixture
def make_cli(monkeypatch, capsys):
    def make(scene, *, architect=None, reviewer=None, iteration: int = 1) -> Cli:
        harness = Cli(
            scene,
            capsys,
            RecordingModel(scene) if architect is None else architect,
            CoveringReviewer(scene, iteration) if reviewer is None else reviewer,
        )
        for name, value in ENVIRONMENT.items():
            monkeypatch.setenv(name, value)
        monkeypatch.setattr(cli, "_architecture_workspaces", harness.workspaces)
        monkeypatch.setattr(cli, "_tsa_clock", fixed_clock)
        monkeypatch.setattr(cli, "LocalCliModelRuntime", harness.runtime)
        return harness

    return make


@pytest.fixture
def broken_runtime_config(monkeypatch):
    """Any TSA role that is configured fails: no runtime config can be read."""

    def unreadable(path=None):
        raise ModelRuntimeConfigError("No runtime configuration at /nowhere.")

    monkeypatch.setattr(cli, "load_model_runtime_config", unreadable)


def selector(*extra: str) -> list[str]:
    return ["--project", PROJECT_CODE, "--cycle", CYCLE, *extra]


def start_argv(*extra: str, requirements=(REQUIREMENT_ID,), accept=True) -> list[str]:
    argv = ["start", *selector()]
    for requirement in requirements:
        argv += ["--requirement", requirement]
    argv += ["--ux", "not-applicable", "--ux-reason", UX_REASON]
    if accept:
        argv += ["--accept-inputs", "--accept-ux"]
    return [*argv, *extra]


def target(iteration: int = 1, review: str | None = None) -> list[str]:
    return selector(
        "--iteration",
        str(iteration),
        "--review-result-id",
        review_id(iteration) if review is None else review,
    )


RESUME = ["resume", *selector()]
INSPECT = ["inspect", *selector()]


def rework_argv(*extra: str, iteration: int = 1, review: str | None = None):
    return ["rework", *target(iteration, review), *extra]


def approve_argv(*extra: str, iteration: int = 1, review: str | None = None):
    return ["approve", *target(iteration, review), "--confirm", *extra]


def nothing_changed(harness: Cli) -> None:
    assert harness.scene.tsa.mutations == []
    assert harness.scene.req.mutations == []
    assert harness.model_calls == (0, 0)


def assert_result(run: Run, code: str) -> None:
    """The first line is the code, then a blank line; one stream only."""
    assert run.exit_code == expected_exit(code), run.stream
    lines = run.stream.splitlines()
    assert lines[0] == code, run.stream
    assert lines[1] == ""
    assert (run.err if run.exit_code == 0 else run.out) == ""


# --------------------------------------------------------------------------
# A. The result-code catalogue and its exit classes (spec 12.3, 13.8, v0.5)
# --------------------------------------------------------------------------


def catalogue_rows(path: Path, heading: str) -> dict[str, int]:
    """`| `CODE` | meaning | exit |` rows of the table after one heading."""
    text = path.read_text(encoding="utf-8")
    section = text[text.index(heading) :]
    section = section[: section.index("\n## ", 1)]
    return {
        code: int(exit_class)
        for code, exit_class in re.findall(
            r"^\| `([A-Z_]+)` \| .* \| ([0-9]) \|$", section, re.MULTILINE
        )
    }


def frozen_catalogue() -> dict[str, int]:
    v03 = catalogue_rows(SPEC_V03, "### 13.8 Result-code catalogue")
    v05 = catalogue_rows(SPEC_V05, "## 2. New result code")
    v06 = catalogue_rows(SPEC_V06, "## 2. New result code")
    assert len(v03) == 53
    assert v05 == {"REVIEW_INPUT_CHANGED": 1}
    assert v06 == {"WORKSPACE_GUARD_UNAVAILABLE": 1}
    return {**v03, **v05, **v06}


def test_the_catalogue_is_exactly_the_frozen_one_with_its_exit_classes():
    implemented = {code.value: exit_code_for(code) for code in TsaResultCode}

    assert implemented == frozen_catalogue()


def test_the_transcribed_normal_codes_are_the_spec_exit_zero_rows():
    frozen = frozen_catalogue()

    assert {code for code, exit_class in frozen.items() if exit_class == 0} == (
        SPEC_NORMAL
    )


@pytest.mark.parametrize("code", sorted(frozen_catalogue()))
def test_no_engine_code_exits_with_the_argparse_class(code):
    assert exit_code_for(TsaResultCode(code)) in (0, 1)


def test_every_code_the_domain_layers_raise_is_in_the_catalogue():
    raised = {
        *CycleResultCode,
        *AdmissionResultCode,
        *ArchitectResultCode,
        *ArchitectureResultCode,
        *ReviewerResultCode,
        *DecisionResultCode,
    }
    extra = {
        REVIEW_STRUCTURALLY_INVALID,
        REVIEW_BLOCKED_ON_WHAT,
        REVIEW_COVERAGE_INCOMPLETE,
        REVIEW_COVERAGE_DUPLICATE,
    }

    assert {str(code) for code in raised} | extra <= {c.value for c in TsaResultCode}


def test_inspect_stale_and_cycle_approved_are_normal_outcomes():
    assert exit_code_for(TsaResultCode.INSPECT_STALE) == 0
    assert exit_code_for(TsaResultCode.CYCLE_APPROVED) == 0
    assert exit_code_for(TsaResultCode.DECISION_ALREADY_RECORDED) == 0
    assert exit_code_for(TsaResultCode.REVIEW_INPUT_CHANGED) == 1


# --------------------------------------------------------------------------
# B. The parser surface (spec 12)
# --------------------------------------------------------------------------


def parse(*argv: str):
    return cli.build_parser().parse_args(["project", "architecture", *argv])


def usage_error(capsys, *argv: str) -> str:
    with pytest.raises(SystemExit) as exited:
        cli.main(["project", "architecture", *argv])
    assert exited.value.code == 2
    return capsys.readouterr().err


def test_exactly_five_actions_exist():
    actions = cli.build_parser()._subparsers._group_actions[0]
    project = actions.choices["project"]._subparsers._group_actions[0]
    architecture = project.choices["architecture"]._subparsers._group_actions[0]

    assert list(architecture.choices) == [
        "start",
        "resume",
        "rework",
        "approve",
        "inspect",
    ]


@pytest.mark.parametrize(
    "argv",
    [
        start_argv(),
        RESUME,
        rework_argv(),
        approve_argv(),
        INSPECT,
    ],
    ids=["start", "resume", "rework", "approve", "inspect"],
)
def test_the_cycle_flag_is_cycle_and_nothing_else(argv, capsys):
    assert parse(*argv).cycle == CYCLE
    for spelling in ("--cycle-id", "--cyc", "--Cycle"):
        changed = [spelling if item == "--cycle" else item for item in argv]
        error = usage_error(capsys, *changed)
        assert "the following arguments are required: --cycle" in error, spelling


@pytest.mark.parametrize(
    ("argv", "missing"),
    [
        (RESUME, "--project"),
        (RESUME, "--cycle"),
        (INSPECT, "--project"),
        (INSPECT, "--cycle"),
        (start_argv(), "--project"),
        (start_argv(), "--cycle"),
        (rework_argv(), "--iteration"),
        (rework_argv(), "--review-result-id"),
        (rework_argv(), "--cycle"),
        (approve_argv(), "--iteration"),
        (approve_argv(), "--review-result-id"),
        (approve_argv(), "--cycle"),
    ],
)
def test_a_missing_required_flag_is_a_usage_error(argv, missing, capsys):
    index = argv.index(missing)
    without = argv[:index] + argv[index + 2 :]

    assert "required" in usage_error(capsys, *without)


def test_approve_without_confirm_is_a_usage_error(make_cli, capsys):
    harness = make_cli(reviewed_scene())
    argv = approve_argv()
    argv.remove("--confirm")

    assert "--confirm" in usage_error(capsys, *argv)
    nothing_changed(harness)
    assert DECISION_ID not in harness.scene.tsa.documents
    assert harness.built == 0, "no workspace was even built"


def test_a_non_integer_iteration_is_a_usage_error(capsys):
    argv = ["rework", *selector("--iteration", "one", "--review-result-id", "r")]

    assert "--iteration" in usage_error(capsys, *argv)


@pytest.mark.parametrize(
    ("argv", "message"),
    [
        (
            ["start", *selector(), "--ux", "applicable", "--accept-inputs"],
            "--ux applicable requires --ux-document",
        ),
        (
            [
                "start",
                *selector(),
                "--ux",
                "applicable",
                "--ux-document",
                UX_DOCUMENT_ID,
                "--ux-reason",
                "x",
            ],
            "--ux-reason is only for --ux not-applicable",
        ),
        (
            ["start", *selector(), "--ux", "not-applicable"],
            "--ux not-applicable requires --ux-reason",
        ),
        (
            [
                "start",
                *selector(),
                "--ux",
                "not-applicable",
                "--ux-reason",
                "x",
                "--ux-document",
                UX_DOCUMENT_ID,
            ],
            "--ux-document and --ux-scope are only for --ux applicable",
        ),
        (
            [
                "start",
                *selector(),
                "--ux",
                "not-applicable",
                "--ux-reason",
                "x",
                "--ux-scope",
                REQUIREMENT_ID,
            ],
            "--ux-document and --ux-scope are only for --ux applicable",
        ),
        (["start", *selector(), "--ux", "maybe"], "invalid choice"),
        (["start", *selector()], "--ux"),
    ],
)
def test_a_ux_flag_contradiction_is_a_usage_error(argv, message, make_cli, capsys):
    harness = make_cli(fresh_world("absent"))

    assert message in usage_error(capsys, *argv)
    assert harness.built == 0
    assert harness.scene.tsa.log == []


def test_requirement_and_ux_scope_repeat_in_caller_order():
    arguments = parse(
        *start_argv(requirements=("b-2", "A-1")),
    )
    assert arguments.requirements == ["b-2", "A-1"]

    applicable = parse(
        "start",
        *selector(),
        "--ux",
        "applicable",
        "--ux-document",
        UX_DOCUMENT_ID,
        "--ux-scope",
        "X",
        "--ux-scope",
        "Y",
    )
    assert applicable.ux_scope == ["X", "Y"]


def test_accept_risk_and_reason_pair_one_to_one_in_order():
    arguments = parse(
        *approve_argv(
            "--accept-risk",
            "r1",
            "--accept-reason",
            "one",
            "--accept-risk",
            "r2",
            "--accept-reason",
            "two",
            "--accept-risk",
            "r1",
            "--accept-reason",
            "again",
        )
    )

    assert cli._accepted_dispositions(arguments) == (
        tsa_cli.AcceptedDisposition("r1", "one"),
        tsa_cli.AcceptedDisposition("r2", "two"),
        tsa_cli.AcceptedDisposition("r1", "again"),
    ), "order kept, the duplicate kept for I11 to refuse"


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (("--accept-risk", "r1"), "has no --accept-reason"),
        (("--accept-reason", "why"), "must follow its own --accept-risk"),
        (
            ("--accept-risk", "r1", "--accept-risk", "r2", "--accept-reason", "x"),
            "has no --accept-reason before this one",
        ),
        (
            ("--accept-risk", "r1", "--accept-reason", "x", "--accept-reason", "y"),
            "must follow its own --accept-risk",
        ),
        (("--accept-risk", "r1", "--accept-reason", "  "), "must not be blank"),
    ],
)
def test_malformed_disposition_pairing_is_refused_before_any_write(
    extra, message, make_cli, capsys
):
    harness = make_cli(reviewed_scene())

    assert message in usage_error(capsys, *approve_argv(*extra))
    nothing_changed(harness)
    assert DECISION_ID not in harness.scene.tsa.documents


def test_a_blank_rework_reason_is_a_usage_error(make_cli, capsys):
    harness = make_cli(reviewed_scene())

    assert "must not be blank" in usage_error(capsys, *rework_argv("--reason", " "))
    nothing_changed(harness)


def test_inspect_accepts_json():
    assert parse(*INSPECT, "--json").as_json is True
    assert parse(*INSPECT).as_json is False


@pytest.mark.parametrize("flag", ["--runtime", "--model"])
@pytest.mark.parametrize(
    "argv",
    [start_argv(), RESUME, rework_argv(), approve_argv(), INSPECT],
    ids=["start", "resume", "rework", "approve", "inspect"],
)
def test_no_tsa_command_takes_a_runtime_or_model_override(argv, flag, capsys):
    assert "unrecognized arguments" in usage_error(capsys, *argv, flag, "claude")


# --------------------------------------------------------------------------
# C. The command x durable-state table (spec 13.6), cell by cell
# --------------------------------------------------------------------------

NONE, BOTH, REVIEWER = (0, 0), (1, 1), (0, 1)
COMMANDS = ("start", "resume", "rework", "approve", "inspect")


def refusal_row(code: str, inspect: str) -> dict:
    """Every mutating command refuses with `code`; nothing is written."""
    return {
        **{command: (code, False, NONE) for command in COMMANDS[:4]},
        "inspect": (inspect, False, NONE),
    }


def fresh_world(architecture: str):
    """The I05 world with the setup of its Requirement side forgotten."""
    scene = world(architecture)
    reset_trace(scene)
    return scene


def scene_a():
    return fresh_world("absent")


def scene_shell():
    return fresh_world("empty shell")


def scene_b():
    return fresh_world("bootstrapped")


def scene_case_2():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    return scene


def scene_case_4():
    scene = applied_scene()
    scene.tsa.set_content(
        ARCHITECTURE_ID, other_architecture(scene, "Edited by hand.").text
    )
    reset_trace(scene)
    return scene


def scene_decided(decision: str):
    def build():
        scene = reviewed_scene()
        decide(scene, decision)
        return scene

    return build


def scene_shell_at(build, document_id: str):
    def shelled():
        scene = build()
        scene.tsa.seed_child(document_id, ARCHITECTURE_ID, "")
        reset_trace(scene)
        return scene

    return shelled


def scene_malformed_process():
    scene = applied_scene()
    scene.tsa.set_content(PROCESS_ID, "A note someone left here.\n")
    reset_trace(scene)
    return scene


def scene_ambiguous():
    scene = fresh_world("bootstrapped")
    scene.tsa.seed_root("stray-architecture", bootstrap_carrier())
    reset_trace(scene)
    return scene


def scene_foreign():
    scene = fresh_world("absent")
    scene.tsa.place_foreign_document(
        ARCHITECTURE_ID,
        container_entity_type=PROJECT_TYPE_ID,
        container_entity_id="99",
    )
    scene.tsa.set_content(ARCHITECTURE_ID, bootstrap_carrier())
    reset_trace(scene)
    return scene


def scene_malformed_bootstrap():
    scene = fresh_world("absent")
    scene.tsa.seed_root(ARCHITECTURE_ID, "A note, not a carrier.\n")
    reset_trace(scene)
    return scene


def scene_acceptance_mismatch():
    scene = accepted_scene()
    acceptance_bound_elsewhere(scene)
    reset_trace(scene)
    return scene


def scene_manifest_shell():
    scene = accepted_scene()
    scene.tsa.set_content(MANIFEST_ID, "")
    reset_trace(scene)
    return scene


def scene_stale():
    scene = reviewed_scene()
    root_edited_after_review(scene)
    reset_trace(scene)
    return scene


def scene_duplicate():
    scene = reviewed_scene()
    later = resealed_carrier(
        scene.tsa.content_of(REVIEW_ID),
        lambda p: p["body"].update(created_at="2027-01-02T03:04:05Z"),
    )
    scene.tsa.seed_child("rogue-review", ARCHITECTURE_ID, later)
    reset_trace(scene)
    return scene


def scene_restarted_at_boundary():
    """Case 10: the boundary was already presented once before this restart."""
    scene = reviewed_scene()
    reset_trace(scene)
    return scene


#: Spec 13.6, transcribed: per row, per command, (code, mutates, (Architect
#: calls, Reviewer calls)). The `rework` cell of a new REWORK runs N+1.
TABLE = {
    "A": (
        scene_a,
        {
            "start": ("ARCHITECTURE_CYCLE_STARTED", True, BOTH),
            "resume": ("CYCLE_NOT_FOUND", False, NONE),
            "rework": ("CYCLE_NOT_FOUND", False, NONE),
            "approve": ("CYCLE_NOT_FOUND", False, NONE),
            "inspect": ("CYCLE_NOT_FOUND", False, NONE),
        },
    ),
    "EMPTY_ARCHITECTURE_SHELL": (
        scene_shell,
        {
            "start": ("ARCHITECTURE_CYCLE_STARTED", True, BOTH),
            "resume": ("ARCHITECTURE_CYCLE_RESUMED", True, NONE),
            "rework": ("REVIEW_NOT_CURRENT", False, NONE),
            "approve": ("REVIEW_NOT_CURRENT", False, NONE),
            "inspect": ("INSPECT_INCOMPLETE", False, NONE),
        },
    ),
    "B": (
        scene_b,
        {
            "start": ("ARCHITECTURE_CYCLE_STARTED", True, BOTH),
            "resume": ("MANIFEST_INPUTS_REQUIRED", False, NONE),
            "rework": ("REVIEW_NOT_CURRENT", False, NONE),
            "approve": ("REVIEW_NOT_CURRENT", False, NONE),
            "inspect": ("INSPECT_INCOMPLETE", False, NONE),
        },
    ),
    "D1": (
        accepted_scene,
        {
            "start": ("ARCHITECTURE_REVIEW_READY", True, BOTH),
            "resume": ("ARCHITECTURE_CYCLE_RESUMED", True, BOTH),
            "rework": ("REVIEW_NOT_CURRENT", False, NONE),
            "approve": ("REVIEW_NOT_CURRENT", False, NONE),
            "inspect": ("INSPECT_CURRENT", False, NONE),
        },
    ),
    "D2": (
        scene_case_2,
        {
            "start": ("ARCHITECTURE_REVIEW_READY", True, REVIEWER),
            "resume": ("ARCHITECTURE_CYCLE_RESUMED", True, REVIEWER),
            "rework": ("REVIEW_NOT_CURRENT", False, NONE),
            "approve": ("REVIEW_NOT_CURRENT", False, NONE),
            "inspect": ("INSPECT_CURRENT", False, NONE),
        },
    ),
    "D3": (
        applied_scene,
        {
            "start": ("ARCHITECTURE_REVIEW_READY", True, REVIEWER),
            "resume": ("ARCHITECTURE_CYCLE_RESUMED", True, REVIEWER),
            "rework": ("REVIEW_NOT_CURRENT", False, NONE),
            "approve": ("REVIEW_NOT_CURRENT", False, NONE),
            "inspect": ("INSPECT_CURRENT", False, NONE),
        },
    ),
    "D4": (scene_case_4, refusal_row("ARCHITECTURE_DIVERGED", "INSPECT_INCOMPLETE")),
    "D5": (
        reviewed_scene,
        {
            "start": ("ARCHITECTURE_REVIEW_READY", False, NONE),
            "resume": ("ARCHITECTURE_REVIEW_READY", False, NONE),
            "rework": ("ARCHITECTURE_REWORK_RECORDED", True, BOTH),
            "approve": ("ARCHITECTURE_APPROVED", True, NONE),
            "inspect": ("INSPECT_CURRENT", False, NONE),
        },
    ),
    "D6-REWORK": (
        scene_decided("REWORK"),
        {
            "start": ("ARCHITECTURE_CYCLE_RESUMED", True, BOTH),
            "resume": ("ARCHITECTURE_CYCLE_RESUMED", True, BOTH),
            "rework": ("DECISION_ALREADY_RECORDED", False, NONE),
            "approve": ("DECISION_CONFLICT", False, NONE),
            "inspect": ("INSPECT_CURRENT", False, NONE),
        },
    ),
    "D6-APPROVE": (
        scene_decided("APPROVE"),
        {
            "start": ("CYCLE_APPROVED", False, NONE),
            "resume": ("CYCLE_APPROVED", False, NONE),
            "rework": ("DECISION_CONFLICT", False, NONE),
            "approve": ("DECISION_ALREADY_RECORDED", False, NONE),
            "inspect": ("INSPECT_CURRENT", False, NONE),
        },
    ),
    "D7-process-shell": (
        scene_shell_at(accepted_scene, PROCESS_ID),
        {
            "start": ("ARCHITECTURE_CYCLE_RESUMED", True, BOTH),
            "resume": ("ARCHITECTURE_CYCLE_RESUMED", True, BOTH),
            "rework": ("REVIEW_NOT_CURRENT", False, NONE),
            "approve": ("REVIEW_NOT_CURRENT", False, NONE),
            "inspect": ("INSPECT_CURRENT", False, NONE),
        },
    ),
    "D7-review-shell": (
        scene_shell_at(applied_scene, REVIEW_ID),
        {
            "start": ("ARCHITECTURE_CYCLE_RESUMED", True, REVIEWER),
            "resume": ("ARCHITECTURE_CYCLE_RESUMED", True, REVIEWER),
            "rework": ("REVIEW_NOT_CURRENT", False, NONE),
            "approve": ("REVIEW_NOT_CURRENT", False, NONE),
            "inspect": ("INSPECT_CURRENT", False, NONE),
        },
    ),
    "D7-decision-shell": (
        scene_shell_at(reviewed_scene, DECISION_ID),
        refusal_row("DECISION_SHELL_UNRECOVERABLE", "INSPECT_CURRENT"),
    ),
    "D8": (
        scene_malformed_process,
        refusal_row("ARTIFACT_MALFORMED", "INSPECT_INCOMPLETE"),
    ),
    "D10": (
        scene_restarted_at_boundary,
        {
            "start": ("ARCHITECTURE_REVIEW_READY", False, NONE),
            "resume": ("ARCHITECTURE_REVIEW_READY", False, NONE),
            "rework": ("ARCHITECTURE_REWORK_RECORDED", True, BOTH),
            "approve": ("ARCHITECTURE_APPROVED", True, NONE),
            "inspect": ("INSPECT_CURRENT", False, NONE),
        },
    ),
    "E-ambiguous": (
        scene_ambiguous,
        refusal_row("CYCLE_AMBIGUOUS", "INSPECT_INCOMPLETE"),
    ),
    "E-foreign": (
        scene_foreign,
        refusal_row("CYCLE_FOREIGN_PROJECT", "INSPECT_INCOMPLETE"),
    ),
    "E-malformed": (
        scene_malformed_bootstrap,
        refusal_row("ARTIFACT_MALFORMED", "INSPECT_INCOMPLETE"),
    ),
    "E-acceptance": (
        scene_acceptance_mismatch,
        refusal_row("MANIFEST_ACCEPTANCE_MISMATCH", "INSPECT_INCOMPLETE"),
    ),
    "E-manifest-shell": (
        scene_manifest_shell,
        refusal_row("MANIFEST_SHELL_UNRECOVERABLE", "INSPECT_INCOMPLETE"),
    ),
    "stale": (scene_stale, refusal_row("INPUTS_STALE", "INSPECT_STALE")),
    "duplicate": (
        scene_duplicate,
        refusal_row("ARTIFACT_DUPLICATE", "INSPECT_CURRENT"),
    ),
}

ARGV = {
    "start": start_argv(),
    "resume": RESUME,
    "rework": rework_argv(),
    "approve": approve_argv(),
    "inspect": INSPECT,
}
CELLS = [(row, command) for row in TABLE for command in COMMANDS]


@pytest.mark.parametrize(("row", "command"), CELLS, ids=[f"{r}-{c}" for r, c in CELLS])
def test_command_by_durable_state(row, command, make_cli):
    build, cells = TABLE[row]
    code, mutates, (architect_calls, reviewer_calls) = cells[command]
    scene = build()
    opens_next = command == "rework" and mutates
    continues_next = row == "D6-REWORK" and command in ("start", "resume")
    is_next_iteration = opens_next or continues_next
    harness = make_cli(scene, iteration=2 if is_next_iteration else 1)

    run = harness(*ARGV[command])

    assert_result(run, code)
    assert bool(scene.tsa.mutations) is mutates, scene.tsa.mutations
    assert scene.req.mutations == [], "no Requirement is ever written"
    assert harness.model_calls == (architect_calls, reviewer_calls)
    expected_roles = [
        role
        for role, calls in (
            (TSA_ARCHITECT_ROLE, architect_calls),
            (TSA_REVIEWER_ROLE, reviewer_calls),
        )
        if calls
    ]
    assert run.roles == expected_roles, "a role is configured only when it runs"


def test_case_9_an_unknown_outcome_is_rediscovered_then_the_resolved_row(make_cli):
    """The Review create landed but its response was lost: no second create."""
    scene = applied_scene()
    scene.tsa.after(CREATE, 1, fail("response lost"))
    harness = make_cli(scene)

    run = harness(*RESUME)

    assert_result(run, "ARCHITECTURE_CYCLE_RESUMED")
    assert scene.tsa.count(CREATE) == 1
    assert harness.model_calls == REVIEWER
    assert harness(*RESUME).code == "ARCHITECTURE_REVIEW_READY"
    assert harness.model_calls == REVIEWER, "the boundary needs no model"


def test_rework_and_approve_never_repair_an_empty_architecture_shell(make_cli):
    scene = scene_shell()
    harness = make_cli(scene)

    for argv in (rework_argv(), approve_argv()):
        assert harness(*argv).code == "REVIEW_NOT_CURRENT"

    assert scene.tsa.content_of(ARCHITECTURE_ID) == ""
    nothing_changed(harness)


def test_resume_stops_the_empty_shell_at_b_and_says_so(make_cli):
    scene = scene_shell()
    harness = make_cli(scene)

    run = harness(*RESUME)

    assert_result(run, "ARCHITECTURE_CYCLE_RESUMED")
    assert "durable state B" in run.out
    assert scene.tsa.count("create_project_document") == 0, "same id, in place"
    assert MANIFEST_ID not in scene.tsa.documents
    assert harness(*RESUME).code == "MANIFEST_INPUTS_REQUIRED"


# --------------------------------------------------------------------------
# D. start vs resume, acceptance, repeated start (rows 9, 12; spec 13.7)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing", ["--accept-inputs", "--accept-ux"], ids=["inputs", "ux"]
)
@pytest.mark.parametrize("build", [scene_a, scene_shell, scene_b])
def test_missing_acceptance_is_an_engine_refusal_not_a_usage_error(
    build, missing, make_cli
):
    scene = build()
    harness = make_cli(scene)
    argv = start_argv()
    argv.remove(missing)

    run = harness(*argv)

    assert_result(run, "HUMAN_ACCEPTANCE_REQUIRED")
    assert run.exit_code == 1
    nothing_changed(harness)
    assert run.roles == []


def test_acceptance_is_never_inferred_from_running_start(make_cli):
    harness = make_cli(scene_b())

    run = harness(*start_argv(accept=False))

    assert_result(run, "HUMAN_ACCEPTANCE_REQUIRED")
    assert MANIFEST_ID not in harness.scene.tsa.documents


def test_no_requirement_is_selection_empty_not_a_usage_error(make_cli):
    harness = make_cli(scene_b())

    run = harness(*start_argv(requirements=()))

    assert_result(run, "SELECTION_EMPTY")
    nothing_changed(harness)


def test_a_duplicate_after_trim_and_case_is_reported_not_collapsed(make_cli):
    harness = make_cli(scene_b())

    run = harness(
        *start_argv(requirements=(REQUIREMENT_ID, f"  {REQUIREMENT_ID.lower()} "))
    )

    assert_result(run, "SELECTION_DUPLICATE")
    nothing_changed(harness)


def test_row_9_a_repeated_start_at_the_boundary_writes_and_calls_nothing(make_cli):
    scene = scene_a()
    harness = make_cli(scene)
    first = harness(*start_argv())
    assert_result(first, "ARCHITECTURE_CYCLE_STARTED")
    documents = dict(scene.tsa.documents)
    contents = {d: scene.tsa.content_of(d) for d in documents}
    manifest = scene.tsa.content_of(MANIFEST_ID)
    reset_trace(scene)
    calls = harness.model_calls

    again = harness(*start_argv())

    assert_result(again, "ARCHITECTURE_REVIEW_READY")
    assert scene.tsa.mutations == []
    assert dict(scene.tsa.documents) == documents, "no duplicate artifact"
    assert {d: scene.tsa.content_of(d) for d in documents} == contents
    assert scene.tsa.content_of(MANIFEST_ID) == manifest, "the Manifest is reused"
    assert harness.model_calls == calls, "no duplicate model call"


def test_a_repeated_start_compares_inputs_regardless_of_wall_clock(
    make_cli, monkeypatch
):
    scene = accepted_scene()
    manifest = scene.tsa.content_of(MANIFEST_ID)
    harness = make_cli(scene)
    monkeypatch.setattr(cli, "_tsa_clock", lambda: datetime(2031, 5, 6, tzinfo=UTC))

    run = harness(*start_argv())

    assert_result(run, "ARCHITECTURE_REVIEW_READY")
    assert scene.tsa.content_of(MANIFEST_ID) == manifest


@pytest.mark.parametrize(
    "argv",
    [
        start_argv(requirements=(REQUIREMENT_ID, "SDLC-FR-0040")),
        [
            "start",
            *selector(),
            "--requirement",
            REQUIREMENT_ID,
            "--ux",
            "not-applicable",
            "--ux-reason",
            "Another reason.",
            "--accept-inputs",
            "--accept-ux",
        ],
        [
            "start",
            *selector(),
            "--requirement",
            REQUIREMENT_ID,
            "--ux",
            "applicable",
            "--ux-document",
            UX_DOCUMENT_ID,
            "--accept-inputs",
            "--accept-ux",
        ],
    ],
    ids=["selection", "ux-reason", "ux-branch"],
)
def test_row_12_a_repeated_start_with_other_inputs_conflicts(argv, make_cli):
    scene = reviewed_scene()
    manifest = scene.tsa.content_of(MANIFEST_ID)
    harness = make_cli(scene)

    run = harness(*argv)

    assert_result(run, "MANIFEST_INPUTS_CONFLICT")
    nothing_changed(harness)
    assert scene.tsa.content_of(MANIFEST_ID) == manifest


def test_row_9_resume_replays_a_persisted_process_without_the_architect(make_cli):
    scene = scene_case_2()
    harness = make_cli(scene, architect=RecordingModel(scene, error=AssertionError()))

    run = harness(*RESUME)

    assert_result(run, "ARCHITECTURE_CYCLE_RESUMED")
    assert harness.model_calls == REVIEWER
    assert "RECORDED_OUTPUT_APPLIED, model not invoked" in run.out
    assert run.roles == [TSA_REVIEWER_ROLE], "the Architect role is never configured"
    assert scene.tsa.count(CREATE) == 1, "the Review only; no second Process"


def test_row_9_a_repeated_approve_is_already_recorded_with_its_first_time(
    make_cli, monkeypatch
):
    scene = reviewed_scene()
    harness = make_cli(scene)
    first = harness(*approve_argv())
    assert_result(first, "ARCHITECTURE_APPROVED")
    stored = scene.tsa.content_of(DECISION_ID)
    recorded_at = payload_of(scene, DECISION_ID)["body"]["recorded_at"]
    reset_trace(scene)
    monkeypatch.setattr(cli, "_tsa_clock", lambda: datetime(2031, 5, 6, tzinfo=UTC))

    again = harness(*approve_argv())

    assert_result(again, "DECISION_ALREADY_RECORDED")
    assert scene.tsa.mutations == []
    assert scene.tsa.content_of(DECISION_ID) == stored
    assert f"recorded at {recorded_at}" in again.out
    assert again.roles == []


def test_a_repeated_rework_is_already_recorded_and_opens_nothing(make_cli):
    scene = reviewed_scene()
    harness = make_cli(scene, iteration=2)
    assert_result(
        harness(*rework_argv("--reason", "Split the API.")),
        ("ARCHITECTURE_REWORK_RECORDED"),
    )
    reset_trace(scene)
    calls = harness.model_calls

    again = harness(*rework_argv("--reason", "Reworded."))

    assert_result(again, "DECISION_ALREADY_RECORDED")
    assert scene.tsa.mutations == []
    assert harness.model_calls == calls
    assert process_id(3) not in scene.tsa.documents


# --------------------------------------------------------------------------
# E. Decisions: I11 precedence through the CLI (spec 11.1.1, 13.3, 13.4)
# --------------------------------------------------------------------------


def test_rework_after_approve_is_a_conflict_and_the_cycle_stays_closed(make_cli):
    scene = reviewed_scene()
    harness = make_cli(scene)
    assert_result(harness(*approve_argv()), "ARCHITECTURE_APPROVED")
    reset_trace(scene)

    run = harness(*rework_argv())

    assert_result(run, "DECISION_CONFLICT")
    nothing_changed(harness)
    assert process_id(2) not in scene.tsa.documents


def test_a_wrong_review_id_is_target_resolution_first_even_beside_a_decision(
    make_cli,
):
    scene = scene_decided("APPROVE")()
    harness = make_cli(scene)

    run = harness(*approve_argv(review="not-the-review"))

    assert_result(run, "REVIEW_NOT_CURRENT")
    nothing_changed(harness)


def test_approve_never_configures_a_model_even_with_a_broken_config(
    make_cli, broken_runtime_config
):
    scene = reviewed_scene()
    harness = make_cli(scene)

    run = harness(*approve_argv())

    assert_result(run, "ARCHITECTURE_APPROVED")
    assert run.roles == []
    assert payload_of(scene, DECISION_ID)["body"]["decision"] == "APPROVE"
    assert scene.req.mutations == []


def test_approve_records_dispositions_in_caller_order(make_cli):
    scene = reviewed_scene(new_findings=[finding("WARNING")])
    risk = process_ref(scene, "risks")
    warning = review_ref(scene, "new_findings")
    harness = make_cli(scene)

    run = harness(
        *approve_argv(
            "--accept-risk",
            warning,
            "--accept-reason",
            "Known warning.",
            "--accept-risk",
            risk,
            "--accept-reason",
            "Known risk.",
        )
    )

    assert_result(run, "ARCHITECTURE_APPROVED")
    assert payload_of(scene, DECISION_ID)["body"]["accepted_dispositions"] == [
        {"ref": warning, "reason": "Known warning."},
        {"ref": risk, "reason": "Known risk."},
    ]


def test_a_duplicate_disposition_reaches_i11_and_is_refused(make_cli):
    scene = reviewed_scene()
    risk = process_ref(scene, "risks")
    harness = make_cli(scene)

    run = harness(
        *approve_argv(
            "--accept-risk",
            risk,
            "--accept-reason",
            "a",
            "--accept-risk",
            risk,
            "--accept-reason",
            "b",
        )
    )

    assert_result(run, "DISPOSITION_DUPLICATE_REFERENCE")
    nothing_changed(harness)
    assert DECISION_ID not in scene.tsa.documents


def test_a_new_rework_whose_continuation_fails_reports_the_durable_rework(
    make_cli,
):
    scene = reviewed_scene()
    architect = RecordingModel(scene, error=ModelRuntimeError("claude exited 1"))
    harness = make_cli(scene, architect=architect, iteration=2)

    run = harness(*rework_argv("--reason", "Split the API."))

    assert_result(run, "MODEL_RUNTIME_FAILED")
    assert "REWORK of iteration 1 was recorded" in run.err
    assert "nothing was rolled back" in run.err
    assert payload_of(scene, DECISION_ID)["body"]["decision"] == "REWORK"


def test_review_input_changed_is_rendered_as_its_own_refusal(make_cli):
    """Spec v0.5: the fixed Process replaced while the Reviewer ran."""
    scene = applied_scene()

    def replace_process() -> None:
        reseal(
            scene,
            PROCESS_ID,
            lambda p: p["body"].update(created_at="2027-01-02T03:04:05Z"),
        )

    harness = make_cli(scene, reviewer=CoveringReviewer(scene, during=replace_process))

    run = harness(*RESUME)

    assert_result(run, "REVIEW_INPUT_CHANGED")
    assert f"- {PROCESS_ID}" in run.err
    assert harness.model_calls == REVIEWER
    assert REVIEW_ID not in scene.tsa.documents


def stage_without_progress(monkeypatch, stage: str) -> list[tuple]:
    calls: list[tuple] = []
    monkeypatch.setattr(tsa_recovery, stage, lambda *a, **k: calls.append(a))
    return calls


def test_a_recovery_stopped_short_reports_resumed_and_says_so(make_cli, monkeypatch):
    """Approved mapping: I10 ARCHITECT_REQUIRED is RESUMED, never the boundary."""
    scene = accepted_scene()
    calls = stage_without_progress(monkeypatch, "run_architect_stage")

    run = make_cli(scene)(*start_argv())

    assert_result(run, "ARCHITECTURE_CYCLE_RESUMED")
    assert "The Human Decision boundary was not reached." in run.out
    assert "sdlc project architecture resume" in run.out
    assert "re-read durable state" in run.out
    assert "changed under this command" not in run.out
    assert "This start wrote" not in run.out, "the Manifest was reused"
    assert len(calls) == 1


def test_a_rework_whose_continuation_stopped_short_reports_the_durable_rework(
    make_cli, monkeypatch
):
    scene = reviewed_scene()
    stage_without_progress(monkeypatch, "run_architect_stage")

    run = make_cli(scene, iteration=2)(*rework_argv())

    assert_result(run, "ARCHITECTURE_CYCLE_RESUMED")
    assert "REWORK of iteration 1 is durable" in run.out
    assert "It was recorded before downstream recovery stopped." in run.out
    assert "The Human Decision boundary was not reached." in run.out
    assert "changed under this command" not in run.out
    assert payload_of(scene, DECISION_ID)["body"]["decision"] == "REWORK"


# --------------------------------------------------------------------------
# F. Row 47 and lazy model roles (spec 13.2, 15)
# --------------------------------------------------------------------------


def test_row_47_resume_on_an_approved_cycle_is_read_only(
    make_cli, broken_runtime_config
):
    scene = scene_decided("APPROVE")()
    decision = scene.tsa.content_of(DECISION_ID)
    harness = make_cli(scene)

    run = harness(*RESUME)

    assert_result(run, "CYCLE_APPROVED")
    assert run.exit_code == 0 and run.err == ""
    nothing_changed(harness)
    assert run.roles == []
    assert scene.tsa.content_of(DECISION_ID) == decision


def test_resume_at_the_boundary_needs_no_model_configuration(
    make_cli, broken_runtime_config
):
    harness = make_cli(reviewed_scene())

    run = harness(*RESUME)

    assert_result(run, "ARCHITECTURE_REVIEW_READY")
    nothing_changed(harness)


def test_inspect_needs_no_model_configuration(make_cli, broken_runtime_config):
    harness = make_cli(reviewed_scene())

    assert_result(harness(*INSPECT), "INSPECT_CURRENT")
    assert harness.roles == []


def test_a_needed_role_that_cannot_be_configured_fails_in_its_stage(
    make_cli, broken_runtime_config
):
    scene = accepted_scene()
    harness = make_cli(scene)

    run = harness(*RESUME)

    assert_result(run, "MODEL_RUNTIME_FAILED")
    assert "tsa_architect model runtime could not be configured" in run.err
    assert PROCESS_ID not in scene.tsa.documents
    assert scene.tsa.mutations == []


def test_each_role_is_configured_once_per_invocation(make_cli):
    scene = scene_a()
    harness = make_cli(scene)

    run = harness(*start_argv())

    assert_result(run, "ARCHITECTURE_CYCLE_STARTED")
    assert run.roles == [TSA_ARCHITECT_ROLE, TSA_REVIEWER_ROLE]


def test_the_configured_roles_come_from_the_repository_config():
    config = load_model_runtime_config()

    for role in (TSA_ARCHITECT_ROLE, TSA_REVIEWER_ROLE):
        assert select_runtime(config, role).role == role


# --------------------------------------------------------------------------
# G. Row 21: the workspace guard (contract 13, spec 13)
# --------------------------------------------------------------------------

MUTATING = {
    "start": start_argv(),
    "resume": RESUME,
    "rework": rework_argv(),
    "approve": approve_argv(),
}


@pytest.mark.parametrize("command", MUTATING)
def test_row_21_a_second_cooperating_command_is_workspace_busy(command, make_cli):
    scene = reviewed_scene()
    harness = make_cli(scene)

    with hold_workspace(scene.tsa.lock_scope):
        run = harness(*MUTATING[command])

    assert_result(run, "WORKSPACE_BUSY")
    assert run.out == ""
    assert scene.tsa.log == [], "no lifecycle read after the lock attempt"
    assert harness.projects.lookups == [], "not even the Project is resolved"
    nothing_changed(harness)
    assert run.roles == []


def test_inspect_runs_while_the_workspace_is_held(make_cli):
    scene = reviewed_scene()
    harness = make_cli(scene)

    with hold_workspace(scene.tsa.lock_scope):
        run = harness(*INSPECT)

    assert_result(run, "INSPECT_CURRENT")


def test_inspect_never_takes_the_workspace_guard(make_cli, monkeypatch):
    harness = make_cli(reviewed_scene())
    taken = []
    monkeypatch.setattr(tsa_cli, "hold_workspace", lambda scope: taken.append(scope))

    harness(*INSPECT)

    assert taken == []


def test_the_guard_is_held_around_the_whole_command(make_cli, monkeypatch):
    """Every Fibery call and model call happens inside the guard, none outside."""
    scene = scene_a()
    harness = make_cli(scene)
    events: list[str] = []
    real = tsa_cli.hold_workspace

    @contextmanager
    def traced(scope):
        with real(scope):
            events.append(f"lock:{len(scene.tsa.log)}")
            yield
            events.append(f"unlock:{len(scene.tsa.log)}")

    monkeypatch.setattr(tsa_cli, "hold_workspace", traced)

    run = harness(*start_argv())

    assert_result(run, "ARCHITECTURE_CYCLE_STARTED")
    assert events == ["lock:0", f"unlock:{len(scene.tsa.log)}"]
    assert harness.model_calls == BOTH


def test_the_tsa_guard_excludes_a_running_worker_on_the_same_workspace(make_cli):
    """One guard for cooperating SDLC commands: `worker run` holds the same key."""
    scene = reviewed_scene()
    harness = make_cli(scene)

    with hold_workspace(scene.tsa.lock_scope):
        assert harness(*RESUME).code == "WORKSPACE_BUSY"
    assert harness(*RESUME).code == "ARCHITECTURE_REVIEW_READY"


def test_an_unavailable_guard_refuses_and_never_runs_unguarded(
    make_cli, monkeypatch, tmp_path
):
    not_a_directory = tmp_path / "lock-dir-is-a-file"
    not_a_directory.write_text("")
    monkeypatch.setenv(LOCK_DIRECTORY_ENVIRONMENT, str(not_a_directory / "locks"))
    scene = reviewed_scene()
    harness = make_cli(scene)

    run = harness(*approve_argv())

    assert_result(run, "WORKSPACE_GUARD_UNAVAILABLE")
    assert "did not run unguarded" in run.err
    assert scene.tsa.log == []
    nothing_changed(harness)


# --------------------------------------------------------------------------
# H. inspect: staleness, rendering, JSON (spec 12.3, 13.5)
# --------------------------------------------------------------------------


def test_applicable_ux_edited_after_approval_is_inspect_stale(make_cli):
    scene = reviewed_scene(ux=APPLICABLE)
    decide(scene, "APPROVE")
    scene.tsa.set_content(UX_DOCUMENT_ID, "# Checkout flow\n\nTwo screens now.\n")
    reset_trace(scene)
    harness = make_cli(scene)

    run = harness(*INSPECT)

    assert_result(run, "INSPECT_STALE")
    assert "historical, not a current approval" in run.out
    assert "Inputs: STALE" in run.out
    nothing_changed(harness)


@pytest.mark.parametrize("drift", [root_edited_after_review, child_added_after_review])
def test_not_applicable_requirement_drift_is_stale_with_no_ux_read(drift, make_cli):
    scene = reviewed_scene()
    decide(scene, "APPROVE")
    drift(scene)
    reset_trace(scene)
    harness = make_cli(scene)

    run = harness(*INSPECT)

    assert_result(run, "INSPECT_STALE")
    assert [e for e in scene.tsa.log if e[1] == UX_DOCUMENT_ID] == []
    assert "Inputs: STALE" in run.out
    assert "Human Decision:" not in run.out, "no approval is presented as current"


def test_approved_and_current_is_inspect_current_with_the_decision(make_cli):
    scene = scene_decided("APPROVE")()
    harness = make_cli(scene)

    run = harness(*INSPECT)

    assert_result(run, "INSPECT_CURRENT")
    assert f"Human Decision: {DECISION_ID} (decision APPROVE" in run.out


def test_a_stale_duplicate_is_inspect_stale_not_current(make_cli):
    scene = scene_duplicate()
    root_edited_after_review(scene)
    reset_trace(scene)

    assert_result(make_cli(scene)(*INSPECT), "INSPECT_STALE")


def test_inspect_prints_identities_never_content(make_cli):
    scene = reviewed_scene()
    harness = make_cli(scene)

    run = harness(*INSPECT)

    lines = run.out.splitlines()
    assert lines[:2] == ["INSPECT_CURRENT", ""]
    assert f"Project: {PROJECT_ID}" in lines
    assert f"Project Code: {PROJECT_CODE}" in lines
    assert f"Cycle: {CYCLE}" in lines
    assert "Durable state: D" in lines
    assert "Recovery case: REVIEW_RECORDED" in lines
    assert "Iteration: 1" in lines
    review = payload_of(scene, REVIEW_ID)
    assert (
        f"Review Result: {REVIEW_ID} (digest {review['artifact_digest']}, "
        f"derived status {review['body']['derived_status']})" in lines
    )
    for content in (
        scene.tsa.content_of(ARCHITECTURE_ID),
        scene.req.content[scene.root.secret],
        ENVIRONMENT[ENV_TOKEN],
    ):
        for line in content.splitlines():
            if len(line) > 20:
                assert line not in run.out


def json_of(run: Run) -> dict:
    lines = run.stream.split("\n", 2)
    assert lines[0] == run.code and lines[1] == ""
    return json.loads(lines[2])


INSPECT_KEYS = {
    "architecture",
    "case",
    "code",
    "cycle_id",
    "details",
    "human_decision",
    "inputs",
    "iteration",
    "message",
    "process_result",
    "project_code",
    "project_id",
    "review_result",
    "state",
}


@pytest.mark.parametrize(
    ("build", "code"),
    [
        (reviewed_scene, "INSPECT_CURRENT"),
        (scene_stale, "INSPECT_STALE"),
        (scene_b, "INSPECT_INCOMPLETE"),
        (scene_duplicate, "INSPECT_CURRENT"),
    ],
)
def test_inspect_json_is_one_object_after_the_code_line(build, code, make_cli):
    harness = make_cli(build())

    human = harness(*INSPECT)
    machine = harness(*INSPECT, "--json")

    assert machine.code == human.code == code
    assert machine.exit_code == human.exit_code == 0
    assert machine.err == ""
    record = json_of(machine)
    assert set(record) == INSPECT_KEYS
    assert record["code"] == code
    assert machine.out == harness(*INSPECT, "--json").out, "deterministic"
    keys = re.findall(r'^  "([a-z_]+)":', machine.out, re.MULTILINE)
    assert keys == sorted(keys)
    assert ENVIRONMENT[ENV_TOKEN] not in machine.out


def test_inspect_json_carries_the_current_identities(make_cli):
    scene = scene_decided("APPROVE")()
    harness = make_cli(scene)

    record = json_of(harness(*INSPECT, "--json"))

    assert record["project_id"] == PROJECT_ID
    assert record["project_code"] == PROJECT_CODE
    assert record["cycle_id"] == CYCLE
    assert record["state"] == "D"
    assert record["case"] == "APPROVED"
    assert record["inputs"]["status"] == "CURRENT"
    assert record["iteration"] == 1
    assert record["human_decision"] == {
        "decision": "APPROVE",
        "digest": payload_of(scene, DECISION_ID)["artifact_digest"],
        "document_id": DECISION_ID,
    }


def test_inspect_json_for_a_missing_cycle_is_a_refusal_on_stderr(make_cli):
    run = make_cli(scene_a())(*INSPECT, "--json")

    assert run.exit_code == 1 and run.out == ""
    assert json_of(run)["code"] == "CYCLE_NOT_FOUND"


# --------------------------------------------------------------------------
# I. Workspace, Project resolution and configuration
# --------------------------------------------------------------------------


def test_the_project_resolves_by_entity_id_as_well_as_code(make_cli):
    harness = make_cli(reviewed_scene())

    run = harness("inspect", "--project", PROJECT_ID, "--cycle", CYCLE)

    assert_result(run, "INSPECT_CURRENT")


def test_an_unknown_project_is_a_read_refusal(make_cli):
    harness = make_cli(reviewed_scene())

    run = harness("resume", "--project", "Nope", "--cycle", CYCLE)

    assert_result(run, "FIBERY_READ_FAILED")
    nothing_changed(harness)


def test_a_failed_project_lookup_is_a_read_refusal(make_cli):
    harness = make_cli(reviewed_scene())
    harness.projects.error = FiberyError("connection reset")

    run = harness(*RESUME)

    assert_result(run, "FIBERY_READ_FAILED")
    assert harness.scene.tsa.log == []


def test_missing_fibery_settings_are_a_read_refusal_with_the_code_first(
    make_cli, monkeypatch
):
    harness = make_cli(reviewed_scene())
    monkeypatch.delenv(ENV_TOKEN)

    run = harness(*RESUME)

    assert_result(run, "FIBERY_READ_FAILED")
    assert ENV_TOKEN in run.err
    assert harness.built == 0


def test_an_invalid_cycle_id_is_refused(make_cli):
    harness = make_cli(reviewed_scene())

    run = harness("resume", "--project", PROJECT_CODE, "--cycle", "Not A Cycle!")

    assert_result(run, "INVALID_CYCLE_ID")
    nothing_changed(harness)


def test_one_invocation_builds_one_set_of_adapters(make_cli):
    harness = make_cli(scene_a())

    harness(*start_argv())

    assert harness.built == 1


def test_the_live_adapters_share_one_client(monkeypatch):
    clients = []

    class Client:
        def __init__(self, settings):
            clients.append(self)

        def resolve_space_id(self):
            return "space"

    monkeypatch.setattr(cli, "FiberyClient", Client)
    projects, workspace, evidence = cli._architecture_workspaces(
        cli.load_fibery_settings(ENVIRONMENT)
    )

    assert len(clients) == 1
    assert (
        projects._client is workspace._client is evidence.reader._client is clients[0]
    )


# --------------------------------------------------------------------------
# J. Scope: no worker integration, existing commands unchanged
# --------------------------------------------------------------------------


def test_the_worker_has_no_architecture_route():
    for module in (requirement_dispatcher, requirement_runner):
        text = Path(module.__file__).read_text(encoding="utf-8")
        assert "tsa" not in text.lower()


def test_requirement_approve_and_architecture_approve_do_not_collide():
    requirement = cli.build_parser().parse_args(
        ["project", "requirement", "approve", "--requirement", "r-1"]
    )
    architecture = parse(*approve_argv())

    assert requirement.handler is cli._run_requirement_approve
    assert architecture.handler is cli._run_architecture_approve


# --------------------------------------------------------------------------
# K. Truthful partial progress (spec v0.6 section 3)
# --------------------------------------------------------------------------

FALSE_CLAIMS = ("Nothing was persisted.", "Nothing was persisted or applied.")
REVIEWER_DOWN = "reviewer exited 1"
ARCHITECT_DOWN = "architect exited 1"


def failing(scene, role: str, iteration: int = 1):
    if role == TSA_ARCHITECT_ROLE:
        return RecordingModel(scene, error=ModelRuntimeError(ARCHITECT_DOWN))
    return CoveringReviewer(scene, iteration, error=ModelRuntimeError(REVIEWER_DOWN))


def assert_no_false_claim(text: str) -> None:
    for claim in FALSE_CLAIMS:
        assert claim not in text, text


def test_the_major_reproducer_start_from_b_then_the_reviewer_fails(make_cli):
    scene = scene_b()
    harness = make_cli(scene, reviewer=failing(scene, TSA_REVIEWER_ROLE))

    run = harness(*start_argv())

    assert_result(run, "MODEL_RUNTIME_FAILED")
    assert_no_false_claim(run.err)
    assert f"This start wrote the cycle's accepted Input Manifest '{MANIFEST_ID}'" in (
        run.err
    )
    assert "This recovery already made durable progress" in run.err
    assert f"Process Result '{PROCESS_ID}' of iteration 1 was persisted" in run.err
    assert "was applied to the Architecture Document" in run.err
    assert "The Human Decision boundary was not reached." in run.err
    assert "sdlc project architecture resume" in run.err
    assert f"- {REVIEWER_DOWN}" in run.err, "the original failure reason is kept"
    assert harness.model_calls == (1, 1)
    assert scene.tsa.count(CREATE) == 2, "the Manifest and the Process only"
    assert scene.tsa.count(WRITE) == 3, "Manifest, Process and Architecture"
    payload_of(scene, MANIFEST_ID)
    payload_of(scene, PROCESS_ID)
    assert REVIEW_ID not in scene.tsa.documents
    reset_trace(scene)
    harness.reviewer = CoveringReviewer(scene)

    again = harness(*RESUME)

    assert_result(again, "ARCHITECTURE_CYCLE_RESUMED")
    assert harness.model_calls == (1, 1), "case 3: no new Architect call"
    assert scene.tsa.count(CREATE) == 1, "the Review only; nothing redone"


def test_resume_case_1_architect_then_failing_reviewer_reports_i10_progress(
    make_cli,
):
    scene = accepted_scene()
    harness = make_cli(scene, reviewer=failing(scene, TSA_REVIEWER_ROLE))

    run = harness(*RESUME)

    assert_result(run, "MODEL_RUNTIME_FAILED")
    assert_no_false_claim(run.err)
    assert "This recovery already made durable progress" in run.err
    assert "This start wrote" not in run.err, "resume owns no write of its own"
    assert "The Human Decision boundary was not reached." in run.err
    assert run.err.count("The Human Decision boundary was not reached.") == 1
    assert harness.model_calls == (1, 1)
    assert (scene.tsa.count(CREATE), scene.tsa.count(WRITE)) == (1, 2)


def test_an_architect_failure_with_no_progress_keeps_the_stage_message(make_cli):
    scene = accepted_scene()
    harness = make_cli(scene, architect=failing(scene, TSA_ARCHITECT_ROLE))

    run = harness(*start_argv())

    assert_result(run, "MODEL_RUNTIME_FAILED")
    assert "Nothing was persisted or applied." in run.err, "true: nothing was"
    assert "This recovery already made durable progress" not in run.err
    assert "This start wrote" not in run.err
    assert scene.tsa.mutations == []


def test_an_architect_failure_after_start_wrote_the_manifest(make_cli):
    scene = scene_b()
    harness = make_cli(scene, architect=failing(scene, TSA_ARCHITECT_ROLE))

    run = harness(*start_argv())

    assert_result(run, "MODEL_RUNTIME_FAILED")
    assert_no_false_claim(run.err)
    assert "This start wrote the cycle's accepted Input Manifest" in run.err
    assert "This recovery already made durable progress" not in run.err
    assert "Process Result" not in run.err, "no Process is claimed"
    assert "The Human Decision boundary was not reached." in run.err
    assert PROCESS_ID not in scene.tsa.documents
    assert harness.model_calls == (1, 0)


def test_a_failed_apply_keeps_the_architect_stage_own_truth(make_cli):
    """I07 raised itself after persisting the Process: its message is kept."""
    scene = accepted_scene()
    scene.tsa.before(WRITE, 2, fail("connection reset"))
    harness = make_cli(scene)

    run = harness(*start_argv())

    assert_result(run, "FIBERY_WRITE_FAILED")
    assert_no_false_claim(run.err)
    message = run.err.splitlines()[2]
    assert not message.startswith(("This recovery", "This start"))
    payload_of(scene, PROCESS_ID)
    assert harness.model_calls == (1, 0)


def test_resume_case_2_replay_progress_is_acknowledged(make_cli):
    scene = scene_case_2()
    harness = make_cli(scene, reviewer=failing(scene, TSA_REVIEWER_ROLE))

    run = harness(*RESUME)

    assert_result(run, "MODEL_RUNTIME_FAILED")
    assert_no_false_claim(run.err)
    assert "was applied to the Architecture Document" in run.err
    assert "RECORDED_OUTPUT_APPLIED" in run.err
    assert "was persisted (" not in run.err, "the replay persisted no Process"
    assert harness.model_calls == (0, 1)


def test_a_review_written_but_not_confirmed_keeps_the_reviewer_own_truth(
    make_cli,
):
    """I08's post-write message survives inside I10's progress statement."""
    direct = applied_scene()
    direct.tsa.store_as = lambda md: "" if is_review_carrier(md) else md
    with pytest.raises(ReviewerRefused) as caught:
        run_reviewer_stage(
            direct.tsa, direct.req, CoveringReviewer(direct), PROJECT_ID, CYCLE
        )
    reviewer_truth = message_after_progress(str(caught.value))
    scene = accepted_scene()
    scene.tsa.store_as = lambda md: "" if is_review_carrier(md) else md
    harness = make_cli(scene)

    run = harness(*RESUME)

    assert_result(run, "FIBERY_WRITE_FAILED")
    assert "This recovery already made durable progress" in run.err
    assert reviewer_truth in run.err
    assert_no_false_claim(run.err)


# --------------------------------------------------------------------------
# L. Canonical identities in every output (spec 12.3)
# --------------------------------------------------------------------------

NONCANONICAL_CYCLE = f"  {CYCLE.upper()} "


def noncanonical(argv: list[str]) -> list[str]:
    return [NONCANONICAL_CYCLE if item == CYCLE else item for item in argv]


@pytest.mark.parametrize(
    ("build", "command"),
    [
        (scene_a, "start"),
        (reviewed_scene, "resume"),
        (reviewed_scene, "rework"),
        (reviewed_scene, "approve"),
        (reviewed_scene, "inspect"),
    ],
)
def test_outputs_carry_the_resolved_project_and_canonical_cycle(
    build, command, make_cli
):
    harness = make_cli(build(), iteration=2 if command == "rework" else 1)

    run = harness(*noncanonical(ARGV[command]))

    lines = run.stream.splitlines()
    assert run.exit_code == 0, run.stream
    assert f"Project: {PROJECT_ID}" in lines
    assert f"Project Code: {PROJECT_CODE}" in lines
    assert f"Cycle: {CYCLE}" in lines
    assert f"Project: {PROJECT_CODE}" not in lines
    assert NONCANONICAL_CYCLE.strip() not in run.stream


def test_inspect_json_carries_the_entity_id_and_canonical_cycle(make_cli):
    harness = make_cli(reviewed_scene())

    by_code = json_of(harness(*noncanonical(INSPECT), "--json"))
    by_id = json_of(
        harness("inspect", "--project", PROJECT_ID, "--cycle", CYCLE, "--json")
    )

    for record in (by_code, by_id):
        assert record["project_id"] == PROJECT_ID
        assert record["project_code"] == PROJECT_CODE
        assert record["cycle_id"] == CYCLE


def test_an_unresolved_project_is_never_reported_as_an_id(make_cli):
    harness = make_cli(reviewed_scene())
    harness.projects.error = FiberyError("connection reset")

    run = harness(*INSPECT, "--json")

    record = json_of(run)
    assert record["code"] == "FIBERY_READ_FAILED"
    assert record["project_id"] is None and record["project_code"] is None
    assert record["cycle_id"] == CYCLE


def test_no_document_secret_is_printed(make_cli):
    scene = reviewed_scene()
    harness = make_cli(scene)

    outputs = harness(*INSPECT).out + harness(*INSPECT, "--json").out
    outputs += harness(*approve_argv()).out

    for document in scene.tsa.documents.values():
        assert document.secret not in outputs


# --------------------------------------------------------------------------
# M. inspect: per-input currentness (spec 13.5)
# --------------------------------------------------------------------------


def requirement_entity(scene):
    return next(
        record
        for record in scene.req.requirements.values()
        if record.requirement_id == REQUIREMENT_ID
    )


def test_not_applicable_current_reports_each_input_and_reads_no_ux(make_cli):
    scene = reviewed_scene()
    harness = make_cli(scene)

    human = harness(*INSPECT)
    record = json_of(harness(*INSPECT, "--json"))

    assert record["inputs"] == {
        "status": "CURRENT",
        "requirements": [{"requirement_id": REQUIREMENT_ID, "current": True}],
        "ux": {"kind": "NOT_APPLICABLE", "current": True},
        "selection_refusal": None,
    }
    assert f"- Requirement {REQUIREMENT_ID}: current" in human.out
    assert "- UX NOT_APPLICABLE: current" in human.out
    assert [e for e in scene.tsa.log if e[1] == UX_DOCUMENT_ID] == []


def test_requirement_drift_under_not_applicable_names_both_stale_inputs(make_cli):
    scene = scene_stale()
    harness = make_cli(scene)

    human = harness(*INSPECT)
    record = json_of(harness(*INSPECT, "--json"))

    assert_result(human, "INSPECT_STALE")
    assert record["inputs"] == {
        "status": "STALE",
        "requirements": [{"requirement_id": REQUIREMENT_ID, "current": False}],
        "ux": {"kind": "NOT_APPLICABLE", "current": False},
        "selection_refusal": "REQUIREMENT_NOT_ADMISSIBLE",
    }
    assert f"- Requirement {REQUIREMENT_ID}: stale" in human.out
    assert "- UX NOT_APPLICABLE: stale" in human.out
    assert [e for e in scene.tsa.log if e[1] == UX_DOCUMENT_ID] == []


def test_an_edited_applicable_ux_is_the_one_stale_input(make_cli):
    scene = reviewed_scene(ux=APPLICABLE)
    scene.tsa.set_content(UX_DOCUMENT_ID, "# Checkout flow\n\nTwo screens now.\n")
    reset_trace(scene)
    harness = make_cli(scene)

    record = json_of(harness(*INSPECT, "--json"))

    assert record["code"] == "INSPECT_STALE"
    assert record["inputs"]["requirements"] == [
        {"requirement_id": REQUIREMENT_ID, "current": True}
    ]
    assert record["inputs"]["ux"] == {
        "kind": "APPLICABLE",
        "document_id": UX_DOCUMENT_ID,
        "current": False,
    }


def test_an_inadmissible_requirement_is_stale_and_the_selection_refused(make_cli):
    scene = reviewed_scene()
    record = requirement_entity(scene)
    scene.req.requirements[record.id] = replace(record, state="Draft")
    reset_trace(scene)

    inputs = json_of(make_cli(scene)(*INSPECT, "--json"))["inputs"]

    assert inputs["status"] == "STALE"
    assert inputs["requirements"] == [
        {"requirement_id": REQUIREMENT_ID, "current": False}
    ]
    assert inputs["selection_refusal"] == "REQUIREMENT_NOT_ADMISSIBLE"
    assert inputs["ux"] == {"kind": "NOT_APPLICABLE", "current": False}


@pytest.mark.parametrize("build", [scene_b, scene_case_4, scene_malformed_process])
def test_an_incomplete_state_never_claims_its_inputs_current(build, make_cli):
    record = json_of(make_cli(build())(*INSPECT, "--json"))

    assert record["code"] == "INSPECT_INCOMPLETE"
    assert record["inputs"] == {
        "status": "NOT_ESTABLISHED",
        "requirements": [],
        "ux": None,
        "selection_refusal": None,
    }


def test_a_duplicate_with_current_inputs_stays_inspect_current(make_cli):
    record = json_of(make_cli(scene_duplicate())(*INSPECT, "--json"))

    assert record["code"] == "INSPECT_CURRENT"
    assert record["inputs"]["status"] == "CURRENT"
    assert record["inputs"]["requirements"][0]["current"] is True


# --------------------------------------------------------------------------
# N. Busy and empty-shell wording (spec v0.6 sections 2, 3)
# --------------------------------------------------------------------------


def test_the_busy_message_claims_only_what_held(make_cli):
    scene = reviewed_scene()
    harness = make_cli(scene)

    with hold_workspace(scene.tsa.lock_scope):
        run = harness(*RESUME)

    assert "No Project or cycle data was read after the lock attempt" in run.err
    assert "no lifecycle mutation was made and no model was called" in run.err
    assert "Nothing was read" not in run.err


def test_resume_on_an_empty_shell_states_only_the_read_back_state(make_cli):
    run = make_cli(scene_shell())(*RESUME)

    assert_result(run, "ARCHITECTURE_CYCLE_RESUMED")
    assert "discovered as an empty shell" in run.out
    assert "the read-back confirms durable state B" in run.out
    assert (
        f"sdlc project architecture start --project {PROJECT_CODE} --cycle {CYCLE}"
        in run.out
    )
    assert "--requirement, --ux and acceptance flags" in run.out


# --------------------------------------------------------------------------
# O. start: an unknown Manifest outcome (spec v0.6 section 3)
# --------------------------------------------------------------------------

MANIFEST_CLAIM = "This start wrote the cycle's accepted Input Manifest"


def test_an_unknown_manifest_write_that_landed_exact_is_start_progress(make_cli):
    scene = scene_b()
    scene.tsa.after(WRITE, 1, fail("response lost"))
    harness = make_cli(scene, architect=failing(scene, TSA_ARCHITECT_ROLE))

    run = harness(*start_argv())

    assert_result(run, "MODEL_RUNTIME_FAILED")
    assert MANIFEST_CLAIM in run.err
    assert_no_false_claim(run.err)
    assert "The Human Decision boundary was not reached." in run.err
    assert scene.tsa.count(WRITE) == 1, "confirmed, never written twice"
    payload_of(scene, MANIFEST_ID)


def test_an_unknown_manifest_write_that_did_not_land_is_not_claimed(make_cli):
    scene = scene_b()
    scene.tsa.before(WRITE, 1, fail("connection reset"))
    harness = make_cli(scene, architect=failing(scene, TSA_ARCHITECT_ROLE))

    run = harness(*start_argv())

    assert run.exit_code == 1
    assert MANIFEST_CLAIM not in run.err
    assert scene.tsa.content_of(MANIFEST_ID) == ""
    assert harness.model_calls == (0, 0)


@pytest.mark.parametrize(
    "stored",
    [
        "A note, not a Manifest.\n",
        accepted_manifest_carrier(ux=APPLICABLE),
    ],
    ids=["malformed", "another-manifest"],
)
def test_an_unknown_manifest_write_that_landed_otherwise_is_not_claimed(
    stored, make_cli
):
    scene = scene_b()
    scene.tsa.after(WRITE, 1, landed_with(scene, stored))
    harness = make_cli(scene, architect=failing(scene, TSA_ARCHITECT_ROLE))

    run = harness(*start_argv())

    assert run.exit_code == 1
    assert run.code in ("ARTIFACT_MALFORMED", "FIBERY_WRITE_FAILED")
    assert MANIFEST_CLAIM not in run.err
    assert scene.tsa.content_of(MANIFEST_ID) == stored, "never overwritten"
    assert harness.model_calls == (0, 0)


# --------------------------------------------------------------------------
# P. rework: a durable REWORK whose continuation is refused (v0.6 section 3)
# --------------------------------------------------------------------------

REWORK_CLAIM = "REWORK of iteration 1 was recorded at Human Decision"


def drifting_after_review(monkeypatch, scene) -> None:
    real = tsa_recovery.run_reviewer_stage

    def reviewed_then_drifted(*args, **kwargs):
        result = real(*args, **kwargs)
        root_edited_after_review(scene)
        return result

    monkeypatch.setattr(tsa_recovery, "run_reviewer_stage", reviewed_then_drifted)


def test_rework_then_the_architect_fails_before_any_write(make_cli):
    scene = reviewed_scene()
    harness = make_cli(scene, architect=failing(scene, TSA_ARCHITECT_ROLE))

    run = harness(*rework_argv())

    assert_result(run, "MODEL_RUNTIME_FAILED")
    assert REWORK_CLAIM in run.err
    assert "This recovery already made durable progress" not in run.err
    assert "The Human Decision boundary of iteration 2 was not reached." in run.err
    assert "sdlc project architecture resume" in run.err
    assert_no_false_claim(run.err)
    assert process_id(2) not in scene.tsa.documents


def test_rework_then_the_reviewer_fails_before_its_write(make_cli):
    scene = reviewed_scene()
    harness = make_cli(scene, reviewer=failing(scene, TSA_REVIEWER_ROLE, 2))

    run = harness(*rework_argv())

    assert_result(run, "MODEL_RUNTIME_FAILED")
    assert REWORK_CLAIM in run.err
    assert f"Process Result {process_id(2)!r} of iteration 2 was persisted" in run.err
    assert "was applied to the Architecture Document" in run.err
    assert "was written and confirmed" not in run.err, "no Review is claimed"
    assert "sdlc project architecture resume" in run.err
    assert_no_false_claim(run.err)
    assert review_id(2) not in scene.tsa.documents


def test_rework_then_a_review_then_a_later_gate_refusal(make_cli, monkeypatch):
    scene = reviewed_scene()
    drifting_after_review(monkeypatch, scene)
    harness = make_cli(scene, iteration=2)

    run = harness(*rework_argv())

    assert_result(run, "INPUTS_STALE")
    assert REWORK_CLAIM in run.err
    assert f"Process Result {process_id(2)!r} of iteration 2 was persisted" in run.err
    assert "was applied to the Architecture Document" in run.err
    assert (
        f"Review Result {review_id(2)!r} of iteration 2 was written and confirmed"
        in run.err
    )
    assert "othing was written" not in run.err
    assert run.err.count("The Human Decision boundary") == 1
    assert harness.model_calls == (1, 1)


def test_an_idempotent_rework_retry_runs_no_recovery(make_cli, monkeypatch):
    scene = scene_decided("REWORK")()
    harness = make_cli(scene)
    readings: list[datetime] = []
    monkeypatch.setattr(cli, "_tsa_clock", lambda: readings.append(fixed_clock()))

    run = harness(*rework_argv())

    assert_result(run, "DECISION_ALREADY_RECORDED")
    nothing_changed(harness)
    assert harness.roles == []
    assert readings == [], "no clock read for an equivalent durable Decision"


# --------------------------------------------------------------------------
# Q. An unmatched --project value is never reported as an id
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [
        ["inspect", "--project", "Nope", "--cycle", CYCLE],
        ["resume", "--project", "Nope", "--cycle", CYCLE],
        [
            "approve",
            "--project",
            "Nope",
            "--cycle",
            CYCLE,
            "--iteration",
            "1",
            "--review-result-id",
            REVIEW_ID,
            "--confirm",
        ],
    ],
    ids=["inspect", "resume", "approve"],
)
def test_an_unmatched_project_value_is_never_shown_as_its_id(argv, make_cli):
    run = make_cli(reviewed_scene())(*argv)

    assert_result(run, "FIBERY_READ_FAILED")
    assert "Project: Nope" not in run.err
    assert f"Cycle: {CYCLE}" in run.err


def test_an_unmatched_project_value_is_null_in_inspect_json(make_cli):
    run = make_cli(reviewed_scene())(
        "inspect", "--project", "Nope", "--cycle", CYCLE, "--json"
    )

    record = json_of(run)
    assert record["code"] == "FIBERY_READ_FAILED"
    assert record["project_id"] is None and record["project_code"] is None


# --------------------------------------------------------------------------
# R. start provenance after a Manifest write whose response was lost
# --------------------------------------------------------------------------


def drifting_after_the_manifest(monkeypatch, scene) -> None:
    """The Requirement drifts right after I05 returns its confirmed Manifest."""
    real = tsa_cli.start_input_manifest

    def confirmed_then_drifted(*args, **kwargs):
        result = real(*args, **kwargs)
        root_edited_after_review(scene)
        return result

    monkeypatch.setattr(tsa_cli, "start_input_manifest", confirmed_then_drifted)


def test_a_landed_manifest_then_drift_is_stale_and_names_the_manifest(
    make_cli, monkeypatch
):
    scene = scene_b()
    scene.tsa.after(WRITE, 1, fail("response lost"))
    drifting_after_the_manifest(monkeypatch, scene)
    harness = make_cli(scene)

    run = harness(*start_argv())

    assert_result(run, "INPUTS_STALE")
    assert MANIFEST_CLAIM in run.err
    assert "The Human Decision boundary was not reached." in run.err
    assert "sdlc project architecture resume" in run.err
    assert "is not admissible" in run.err, "the stale-input reason is kept"
    assert "othing was written" not in run.err
    assert "othing was persisted" not in run.err
    assert (scene.tsa.count(CREATE), scene.tsa.count(WRITE)) == (1, 1)
    payload_of(scene, MANIFEST_ID)
    assert harness.model_calls == (0, 0)
    assert run.roles == []


@pytest.mark.parametrize("response", ["returned", "lost"])
def test_a_start_that_wrote_its_manifest_is_started_however_it_returned(
    response, make_cli
):
    scene = scene_b()
    if response == "lost":
        scene.tsa.after(WRITE, 1, fail("response lost"))
    harness = make_cli(scene)

    run = harness(*start_argv())

    assert_result(run, "ARCHITECTURE_CYCLE_STARTED")
    assert scene.tsa.count(CREATE) == 3, "Manifest, Process and Review once each"
    assert harness.model_calls == (1, 1)


def test_a_repeated_start_on_an_existing_manifest_is_never_started(make_cli):
    scene = reviewed_scene()
    manifest = scene.tsa.content_of(MANIFEST_ID)
    harness = make_cli(scene)

    run = harness(*start_argv())

    assert_result(run, "ARCHITECTURE_REVIEW_READY")
    assert scene.tsa.mutations == []
    assert scene.tsa.content_of(MANIFEST_ID) == manifest
    assert MANIFEST_CLAIM not in run.out
