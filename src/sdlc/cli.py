"""`sdlc` command line entry point."""

from __future__ import annotations

import argparse
import functools
import sys
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from sdlc.autonomy_policy import (
    AutonomyPolicies,
    AutonomyPolicyError,
    load_autonomy_policies,
)
from sdlc.config import ConfigurationError, FiberySettings, load_fibery_settings
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import (
    FiberyArchitectureWorkspace,
    FiberyHttpWorkspace,
    FiberyRawProcessorWorkspace,
    FiberyRequirementWorkspace,
)
from sdlc.model_runtime import (
    LocalCliModelRuntime,
    ModelResponse,
    ModelRuntime,
    ModelRuntimeError,
)
from sdlc.model_runtime_config import (
    RAW_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_REVIEWER_ROLE,
    TSA_ARCHITECT_ROLE,
    TSA_REVIEWER_ROLE,
    ModelRuntimeConfigError,
    load_model_runtime_config,
    select_runtime,
)
from sdlc.project_bootstrap import BootstrapCode, BootstrapResult, bootstrap_project
from sdlc.project_init import initialize_project
from sdlc.raw_processor import process_raw_requirement
from sdlc.ready_decision import (
    approve_standard_requirement,
    rework_standard_requirement,
)
from sdlc.requirement_add import add_raw_requirement
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.requirement_dispatcher import RequirementWorkers
from sdlc.requirement_runner import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    MINIMUM_POLL_INTERVAL_SECONDS,
    CycleOutcome,
    CycleReport,
    RunnerCode,
    RunnerPreflightError,
    require_poll_interval,
    run_requirement_runner,
)
from sdlc.result_shell import RECOVERY_OPTION
from sdlc.results import (
    AddResult,
    AddResultCode,
    ApplyResult,
    ApplyResultCode,
    InitResult,
    ProcessResult,
    ProcessResultCode,
    ReadyDecisionResult,
    ReadyDecisionResultCode,
    ResultCode,
    StandardProcessResult,
    StandardProcessResultCode,
    StandardReviewResult,
    StandardReviewResultCode,
)
from sdlc.standard_processor import (
    NEW_ITERATION_OPTION,
    RESUME_OPTION,
    process_standard_requirement,
)
from sdlc.standard_review import ReviewVerdict
from sdlc.standard_reviewer import review_standard_requirement
from sdlc.tsa_admission import (
    PolicyBoundEvidence,
    RequirementEvidenceWorkspace,
    StartInputs,
    UxApplicable,
    UxNotApplicable,
)
from sdlc.tsa_cli import (
    ArchitectureCommand,
    ArchitectureSession,
    ConfiguredRoleRuntime,
    ProjectCodeLookup,
    approve_cycle,
    exit_code_for,
    inspect_cycle,
    render_architecture_result,
    resume_cycle,
    rework_cycle,
    run_guarded,
    start_cycle,
    workspace_unavailable,
)
from sdlc.tsa_cycle import CycleWorkspace
from sdlc.tsa_decision import AcceptedDisposition
from sdlc.worker_runner_guard import (
    WorkerRunnerBusy,
    WorkerRunnerGuardUnavailable,
    hold_workspace,
)

PROGRAM_NAME = "sdlc"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
# The shell convention for a process ended by Ctrl-C (SIGINT).
EXIT_INTERRUPTED = 130

WORKER_SETUP_DOCUMENT = "docs/fibery/Worker-Runner-Setup-v0.1.md"
POLICY_REFUSAL = (
    "The autonomy policy configuration could not be read or validated as this "
    "stage started, so the stage did not run: it read nothing from Fibery, "
    "no model was invoked and nothing was written. No earlier policy is reused. "
    "Correct [autonomy] in the runtime configuration, then reset Processing "
    "Status."
)
RUNNER_STOPPED_NOTE = (
    "Stopped. A Requirement whose worker was interrupted keeps its Processing "
    "Status: the runner never treats it as stale, retries or resets it, and "
    "recovery is explicit."
)

# The normal lifecycle is driven by Requirement State in Fibery
# (Requirement-Lifecycle-Ownership-v0.2); no command here creates authority.
REQUIREMENT_LIFECYCLE_NOTE = (
    "Human lifecycle decisions are Requirement State transitions made in Fibery: "
    "RAW Draft -> Process starts processing, Standard Ready -> Apply approves and "
    "Standard Ready -> Process requests rework. The worker commands (process, "
    "normalize, review, apply) run one stage manually for development, "
    "diagnosis, recovery or explicit admin use. approve and rework are "
    "admin/compatibility shortcuts for the two Ready transitions and create no "
    "other kind of approval or rework."
)
MANUAL_WORKER = "Manual worker (development, diagnosis, recovery, admin):"
ADMIN_DECISION = "Admin/compatibility; the normal path is the Fibery State change:"
APPROVE_DESCRIPTION = (
    "Admin/compatibility command. In the normal lifecycle a human approves by "
    "moving the Requirement Ready -> Apply in Fibery; this command is not "
    "required and records no other kind of approval. On explicit request it "
    "makes that same State transition, after checking that the latest Review "
    "Result still binds the current content, and it asks for a non-PASS verdict "
    "to be acknowledged by name. The acknowledgement is a safety check of this "
    "command only: a direct Ready -> Apply needs none, and Apply revalidates the "
    "reviewed evidence however the Requirement reached Apply."
)
REWORK_DESCRIPTION = (
    "Admin/compatibility command. In the normal lifecycle a human requests "
    "rework by moving the Requirement Ready -> Process in Fibery; this command "
    "is not required and records no other kind of rework decision. It makes "
    "only that State transition and leaves every Process and Review Result in "
    "place."
)
APPLY_DESCRIPTION = (
    "Apply revalidates the reviewed evidence and applies the exact reviewed "
    "state, however the Requirement reached Apply: a direct human State change "
    "in Fibery, an assistant acting on the human's explicit instruction, or the "
    "approve command. It takes no verdict acknowledgement."
)
BOOTSTRAP_DESCRIPTION = (
    "Prepare one consumer project to participate in SDLC: apply the frozen "
    "project-local template, write the project descriptor and the supplied "
    "project context, create the Fibery Project through the existing project "
    "init primitive, and ingest the exported RAW requirements artifact through "
    "the existing requirement add primitive. Both exported artifacts come from "
    "one requirements-export session and are used exactly as supplied: nothing "
    "is reinterpreted, no model runs, and the initial RAW Requirement stops at "
    "Draft, where a human decides when it moves to Process. Existing managed "
    "files are reused when compatible and never overwritten or merged; an "
    "incompatible one stops the attempt before anything is created."
)
BOOTSTRAP_NEXT_STEP = (
    "Next:\nReview the initial RAW Requirement in Fibery.\nWhen it is ready, "
    "move it from Draft -> Process; bootstrap starts no processing itself."
)
WORKER_DESCRIPTION = "The state-driven Requirement worker runner (RW-C04)."
WORKER_RUN_DESCRIPTION = (
    "Run the state-driven Requirement worker in the foreground until Ctrl-C. It "
    "polls every Project of the configured Fibery workspace for Requirements at "
    "a machine route (Raw + Process, Standard + Process, Standard + Review, "
    "Standard + Apply) whose Processing Status is Not Processed, and runs one "
    "worker at a time with the configured model runtime roles; Apply is "
    "model-free. Fibery State stays the only lifecycle authority: the runner "
    "takes no Requirement, State, Type, status, runtime, model or approval "
    "argument. The Processing Status field and its reset automation must be "
    "configured and verified first (docs/fibery/Worker-Runner-Setup-v0.1.md). "
    "One runner per workspace on this host; a second one exits immediately."
)

NEXT_STEP_HINT = "Use:\nsdlc project requirement add\nto add requirements."

ARCHITECTURE_DESCRIPTION = (
    "The Technical Solution Architecture cycle of TSA-C01: explicit and "
    "synchronous, never dispatched by `sdlc worker run`. Every command names "
    "its cycle with --cycle. start, resume, rework and approve hold the "
    "workspace guard for their whole run; inspect is read-only and takes none. "
    "Each prints its result code first; exit 0 is a normal outcome, 1 a "
    "refusal or failure, 2 a usage error."
)
ARCHITECTURE_START_DESCRIPTION = (
    "Start or continue one cycle with explicitly accepted inputs. "
    "--accept-inputs and --accept-ux are the auditable human acceptance: "
    "without either, nothing is written (HUMAN_ACCEPTANCE_REQUIRED). A repeated "
    "start with the same inputs continues the same cycle; different inputs need "
    "a new cycle id."
)
ARCHITECTURE_APPROVE_DESCRIPTION = (
    "Record APPROVE against the exact cycle, iteration and Review Result. "
    "Deterministic and model-free; --confirm is the explicit approval act. Each "
    "--accept-risk names a disposition reference and is followed by its own "
    "--accept-reason."
)
UX_APPLICABLE_CHOICE = "applicable"
UX_NOT_APPLICABLE_CHOICE = "not-applicable"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROGRAM_NAME, description="SDLC command line interface."
    )
    commands = parser.add_subparsers(dest="group", required=True)

    project = commands.add_parser("project", help="Project level commands.")
    project_commands = project.add_subparsers(dest="command", required=True)

    init = project_commands.add_parser(
        "init", help="Create a Project and its document structure in Fibery."
    )
    init.add_argument("--name", required=True, help="Project Name.")
    init.add_argument("--code", help="Project Code. Generated when omitted.")
    init.add_argument("--description", help="Project Description.")
    init.set_defaults(handler=_run_project_init)

    bootstrap = project_commands.add_parser(
        "bootstrap",
        help="Prepare one consumer project: template, descriptor, context, the "
        "Fibery Project and the initial RAW Requirement.",
        description=BOOTSTRAP_DESCRIPTION,
    )
    bootstrap.add_argument("--name", required=True, help="Project Name.")
    bootstrap.add_argument(
        "--requirements",
        required=True,
        help="Path to the exported RAW requirements Markdown artifact.",
    )
    bootstrap.add_argument(
        "--context",
        required=True,
        help="Path to the project-context.md artifact of the same export session.",
    )
    bootstrap.add_argument(
        "--target",
        help="Consumer project directory. The current directory when omitted.",
    )
    bootstrap.add_argument(
        "--code", help="Project Code. Resolved from the Project Name when omitted."
    )
    bootstrap.add_argument("--description", help="Project Description.")
    bootstrap.set_defaults(handler=_run_project_bootstrap)

    requirement = project_commands.add_parser(
        "requirement",
        help="Requirement level commands.",
        description=REQUIREMENT_LIFECYCLE_NOTE,
    )
    requirement_commands = requirement.add_subparsers(dest="action", required=True)
    add = requirement_commands.add_parser(
        "add", help="Ingest one RAW requirements Markdown artifact."
    )
    add.add_argument("--project", required=True, help="Project Code or Project Name.")
    add.add_argument(
        "--source", required=True, help="Path to the RAW requirements Markdown file."
    )
    add.set_defaults(handler=_run_requirement_add)

    process = requirement_commands.add_parser(
        "process",
        help=f"{MANUAL_WORKER} decompose a RAW Requirement in Process into "
        "Standard candidates.",
    )
    process.add_argument(
        "--requirement", required=True, help="RAW Requirement entity id."
    )
    process.add_argument("--runtime", help="Override the configured model runtime.")
    process.add_argument("--model", help="Override the configured model.")
    _add_recovery_option(process, "Processing Result")
    process.set_defaults(handler=_run_requirement_process)

    normalize = requirement_commands.add_parser(
        "normalize",
        help=f"{MANUAL_WORKER} normalize and analyze a Standard Requirement in "
        "Process.",
    )
    normalize.add_argument(
        "--requirement", required=True, help="Standard Requirement entity id."
    )
    normalize.add_argument("--runtime", help="Override the configured model runtime.")
    normalize.add_argument("--model", help="Override the configured model.")
    choices = normalize.add_mutually_exclusive_group()
    _add_recovery_option(choices, "Process Result")
    choices.add_argument(
        RESUME_OPTION,
        dest="resume_result",
        metavar="DOCUMENT_ID",
        help=(
            "Apply the persisted output of the named latest Process Result when "
            "the current normative tree is still its input. Invokes no model and "
            "creates no artifact."
        ),
    )
    choices.add_argument(
        NEW_ITERATION_OPTION,
        dest="new_iteration_after",
        metavar="DOCUMENT_ID",
        help=(
            "Process the current normative tree as a new iteration after the named "
            "latest Process Result, when the tree is that Result's input. Runs the "
            "model once; the named Result is left unchanged."
        ),
    )
    normalize.set_defaults(handler=_run_standard_process)

    review = requirement_commands.add_parser(
        "review",
        help=f"{MANUAL_WORKER} independently review a Standard Requirement in Review.",
    )
    review.add_argument(
        "--requirement", required=True, help="Standard Requirement entity id."
    )
    review.add_argument("--runtime", help="Override the configured model runtime.")
    review.add_argument("--model", help="Override the configured model.")
    _add_recovery_option(review, "Review Result")
    review.set_defaults(handler=_run_standard_review)

    approve = requirement_commands.add_parser(
        "approve",
        help=f"{ADMIN_DECISION} Ready -> Apply after checking the reviewed evidence.",
        description=APPROVE_DESCRIPTION,
    )
    approve.add_argument(
        "--requirement", required=True, help="Standard Requirement entity id."
    )
    approve.add_argument(
        "--acknowledge-verdict",
        choices=[verdict.value for verdict in ReviewVerdict],
        help=(
            "Name the current Review verdict being approved despite. Required "
            "by this command for NEEDS_WORK and BLOCKING, never for PASS. A "
            "safety check of this command only: not approval authority, and not "
            "needed for a direct Ready -> Apply."
        ),
    )
    approve.set_defaults(handler=_run_requirement_approve)

    rework = requirement_commands.add_parser(
        "rework",
        help=f"{ADMIN_DECISION} Ready -> Process.",
        description=REWORK_DESCRIPTION,
    )
    rework.add_argument(
        "--requirement", required=True, help="Standard Requirement entity id."
    )
    rework.set_defaults(handler=_run_requirement_rework)

    apply = requirement_commands.add_parser(
        "apply",
        help=f"{MANUAL_WORKER} deterministically apply a Standard Requirement in "
        "Apply.",
        description=APPLY_DESCRIPTION,
    )
    apply.add_argument(
        "--requirement", required=True, help="Standard Requirement entity id."
    )
    apply.set_defaults(handler=_run_requirement_apply)

    _add_architecture_commands(project_commands)
    _add_worker_commands(commands)

    return parser


def _add_architecture_commands(
    project_commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """`sdlc project architecture`: exactly five actions (TSA-C01 spec 12)."""
    architecture = project_commands.add_parser(
        "architecture",
        help="Technical Solution Architecture cycle commands.",
        description=ARCHITECTURE_DESCRIPTION,
    )
    actions = architecture.add_subparsers(dest="action", required=True)

    start = actions.add_parser(
        "start",
        allow_abbrev=False,
        help="Start or continue a cycle with explicitly accepted inputs.",
        description=ARCHITECTURE_START_DESCRIPTION,
    )
    _add_cycle_selector(start)
    start.add_argument(
        "--requirement",
        dest="requirements",
        action="append",
        metavar="REQUIREMENT-ID",
        help="A selected Requirement ID. Repeat for each Requirement.",
    )
    start.add_argument(
        "--ux",
        required=True,
        choices=[UX_APPLICABLE_CHOICE, UX_NOT_APPLICABLE_CHOICE],
        help="Whether a UX Document applies to this cycle.",
    )
    start.add_argument(
        "--ux-document",
        metavar="FIBERY-DOC-ID",
        help="The approved UX Document. Required iff --ux applicable.",
    )
    start.add_argument(
        "--ux-scope",
        action="append",
        metavar="REQUIREMENT-ID",
        help="A Requirement the UX Document covers. Repeatable; defaults to "
        "every selected Requirement. Only with --ux applicable.",
    )
    start.add_argument(
        "--ux-reason",
        help="Why no UX Document applies. Required iff --ux not-applicable.",
    )
    start.add_argument(
        "--accept-inputs",
        action="store_true",
        help="Explicitly accept the selected inputs for this cycle.",
    )
    start.add_argument(
        "--accept-ux",
        action="store_true",
        help="Explicitly accept the UX decision for this cycle.",
    )
    start.set_defaults(handler=_run_architecture_start, parser=start)

    resume = actions.add_parser(
        "resume", allow_abbrev=False, help="Continue a cycle from its durable state."
    )
    _add_cycle_selector(resume)
    resume.set_defaults(handler=_run_architecture_resume)

    rework = actions.add_parser(
        "rework",
        allow_abbrev=False,
        help="Record REWORK against the exact Review Result.",
    )
    _add_decision_target(rework)
    rework.add_argument(
        "--reason", type=_non_empty_text, help="Why the iteration is reworked."
    )
    rework.set_defaults(handler=_run_architecture_rework)

    approve = actions.add_parser(
        "approve",
        allow_abbrev=False,
        help="Record APPROVE against the exact Review Result.",
        description=ARCHITECTURE_APPROVE_DESCRIPTION,
    )
    _add_decision_target(approve)
    approve.add_argument(
        "--accept-risk",
        dest="dispositions",
        action=_AcceptRisk,
        metavar="REF",
        help="A disposition reference accepted as a known risk. Repeatable.",
    )
    approve.add_argument(
        "--accept-reason",
        dest="dispositions",
        action=_AcceptReason,
        type=_non_empty_text,
        metavar="TEXT",
        help="The reason for the --accept-risk just before it.",
    )
    approve.add_argument(
        "--confirm",
        required=True,
        action="store_true",
        help="The explicit human approval act.",
    )
    approve.set_defaults(handler=_run_architecture_approve, parser=approve)

    inspect = actions.add_parser(
        "inspect",
        allow_abbrev=False,
        help="Report a cycle's state and freshness. Read-only.",
    )
    _add_cycle_selector(inspect)
    inspect.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="After the result code line, print one JSON object.",
    )
    inspect.set_defaults(handler=_run_architecture_inspect)


def _add_cycle_selector(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--project", required=True, help="Project Code or Project entity id."
    )
    command.add_argument("--cycle", required=True, help="The cycle id.")


def _add_decision_target(command: argparse.ArgumentParser) -> None:
    """The full target triple: none of it is ever inferred (spec 12.2)."""
    _add_cycle_selector(command)
    command.add_argument(
        "--iteration", required=True, type=int, metavar="N", help="The iteration."
    )
    command.add_argument(
        "--review-result-id",
        required=True,
        metavar="FIBERY-DOC-ID",
        help="The exact Review Result Document decided on.",
    )


def _non_empty_text(text: str) -> str:
    """A reason is recorded text: blank is a usage error, never a default."""
    if not text.strip():
        raise argparse.ArgumentTypeError("must not be blank")
    return text


class _AcceptRisk(argparse.Action):
    """Opens one (reference, reason) pair; the previous one must be complete."""

    def __call__(self, parser, namespace, values, option_string=None) -> None:
        pairs = list(getattr(namespace, self.dest) or [])
        if pairs and pairs[-1][1] is None:
            raise argparse.ArgumentError(
                self, f"{pairs[-1][0]!r} has no --accept-reason before this one"
            )
        setattr(namespace, self.dest, [*pairs, (values, None)])


class _AcceptReason(argparse.Action):
    """Completes the one open pair: exactly one reason per reference, in order."""

    def __call__(self, parser, namespace, values, option_string=None) -> None:
        pairs = list(getattr(namespace, self.dest) or [])
        if not pairs or pairs[-1][1] is not None:
            raise argparse.ArgumentError(self, "must follow its own --accept-risk")
        setattr(namespace, self.dest, [*pairs[:-1], (pairs[-1][0], values)])


def _add_worker_commands(
    commands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """`sdlc worker run`, the only normal runner entrypoint (RW-C04 section 8)."""
    worker = commands.add_parser(
        "worker", help="Requirement worker runner.", description=WORKER_DESCRIPTION
    )
    worker_commands = worker.add_subparsers(dest="command", required=True)
    run = worker_commands.add_parser(
        "run",
        help="Run the state-driven Requirement worker in the foreground.",
        description=WORKER_RUN_DESCRIPTION,
    )
    run.add_argument(
        "--poll-interval-seconds",
        type=_poll_interval_seconds,
        default=DEFAULT_POLL_INTERVAL_SECONDS,
        metavar="N",
        help=(
            "Idle poll interval in whole seconds (default "
            f"{DEFAULT_POLL_INTERVAL_SECONDS}, minimum "
            f"{MINIMUM_POLL_INTERVAL_SECONDS}). Changes responsiveness only."
        ),
    )
    run.set_defaults(handler=_run_worker)


def _add_recovery_option(command: argparse._ActionsContainer, artifact: str) -> None:
    """Explicit permission to complete one empty Result Document in place."""
    command.add_argument(
        RECOVERY_OPTION,
        dest="recover_empty_result",
        metavar="DOCUMENT_ID",
        help=(
            f"Complete the named empty {artifact} Document in place after a failed "
            "body write. Runs the model again; never creates a second artifact or "
            "overwrites a non-empty one."
        ),
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    return arguments.handler(arguments, sys.stdout, sys.stderr)


def _run_project_init(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    try:
        settings = load_fibery_settings()
    except ConfigurationError as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    workspace = FiberyHttpWorkspace(client=FiberyClient(settings), space=settings.space)
    result = initialize_project(
        workspace,
        name=arguments.name,
        code=arguments.code,
        description=arguments.description,
    )
    render_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


def _client_with_space_id(settings: FiberySettings) -> FiberyClient:
    """One client for the invocation, with its Space UUID already resolved.

    A command that creates a Document or takes the workspace lock needs the
    Space id. It is read here, before that command's first mutation and before
    the lock, so an unresolvable Space stops the run instead of interrupting a
    half-written Requirement. Resolving on the client that does the rest of the
    work means one lookup per invocation, shared by every adapter built on it.

    A command that creates no Document and takes no lock builds its client
    directly and never makes this call.
    """
    client = FiberyClient(settings)
    client.resolve_space_id()
    return client


def _bootstrap_workspaces(
    settings: FiberySettings,
) -> tuple[FiberyHttpWorkspace, FiberyRequirementWorkspace]:
    """The Project-side and Requirement-side adapters of one workspace.

    Both are built from the same settings and the same client, so bootstrap
    cannot end up composing two different Fibery workspaces.
    """
    client = _client_with_space_id(settings)
    return (
        FiberyHttpWorkspace(client=client, space=settings.space),
        FiberyRequirementWorkspace(client=client, space=settings.space),
    )


def _run_project_bootstrap(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    """`sdlc project bootstrap`: the one outer project setup action.

    No model runtime is selected or loaded: bootstrap composes deterministic
    primitives only.
    """
    try:
        settings = load_fibery_settings()
        project_workspace, requirement_workspace = _bootstrap_workspaces(settings)
    except ConfigurationError as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    result = bootstrap_project(
        project_workspace,
        requirement_workspace,
        name=arguments.name,
        requirements_path=arguments.requirements,
        context_path=arguments.context,
        target=arguments.target,
        code=arguments.code,
        description=arguments.description,
    )
    render_bootstrap_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


def render_bootstrap_result(result: BootstrapResult, stream: TextIO) -> None:
    """Print the outcome code first, then the bounded composition detail.

    Identities, managed paths and inner result codes only: the RAW artifact and
    the project context never appear here.
    """
    print(result.code.value, file=stream)
    print(file=stream)
    print(result.message, file=stream)

    if result.project_name:
        print(f"\nProject: {result.project_name}", file=stream)
    if result.project_code:
        print(f"Project Code: {result.project_code}", file=stream)
    if result.requirement_id:
        print(f"Initial RAW Requirement: {result.requirement_id}", file=stream)
    if result.target:
        print(f"Target: {result.target}", file=stream)

    _render_bootstrap_local(result, stream)
    if result.project_init_code is not None:
        print(f"\nProject Init: {result.project_init_code.value}", file=stream)
    if result.requirement_add_code is not None:
        print(f"Requirement Add: {result.requirement_add_code.value}", file=stream)
    if result.failed_step is not None:
        print(f"\nFailed step: {result.failed_step.value}", file=stream)
    if result.details:
        print("\nDetails:", file=stream)
        for item in result.details:
            print(f"- {item}", file=stream)
    if result.code is BootstrapCode.PROJECT_BOOTSTRAPPED:
        print(f"\n{BOOTSTRAP_NEXT_STEP}", file=stream)


def _render_bootstrap_local(result: BootstrapResult, stream: TextIO) -> None:
    """What this attempt did to the consumer project, path by path."""
    if result.target_created:
        print("\nCreated the target directory.", file=stream)
    for label, paths in (
        ("Created", result.local_created),
        ("Updated", result.local_updated),
        ("Reused", result.local_reused),
    ):
        if paths:
            print(f"\n{label}:", file=stream)
            for item in paths:
                print(f"- {item}", file=stream)


def _run_requirement_add(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    try:
        settings = load_fibery_settings()
    except ConfigurationError as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    source = Path(arguments.source)
    try:
        source_text = source.read_text(encoding="utf-8")
    except FileNotFoundError:
        print(AddResultCode.SOURCE_FILE_NOT_FOUND.value, file=error_out)
        print(f"\nNo such source file: {source}", file=error_out)
        return EXIT_FAILURE
    except (OSError, UnicodeDecodeError) as error:
        print(AddResultCode.SOURCE_FILE_UNREADABLE.value, file=error_out)
        print(f"\nCould not read {source}: {error}", file=error_out)
        return EXIT_FAILURE

    try:
        client = _client_with_space_id(settings)
    except ConfigurationError as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    workspace = FiberyRequirementWorkspace(client=client, space=settings.space)
    result = add_raw_requirement(
        workspace, project=arguments.project, source_text=source_text
    )
    render_add_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


def _run_requirement_process(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    try:
        settings = load_fibery_settings()
        runtime_config = load_model_runtime_config()
        selection = select_runtime(
            runtime_config,
            RAW_REQUIREMENT_PROCESSOR_ROLE,
            runtime_override=arguments.runtime,
            model_override=arguments.model,
        )
        client = _client_with_space_id(settings)
    except (ConfigurationError, ModelRuntimeConfigError) as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    workspace = FiberyRawProcessorWorkspace(client=client, space=settings.space)
    result = process_raw_requirement(
        workspace,
        LocalCliModelRuntime(selection),
        arguments.requirement,
        recover_empty_result=arguments.recover_empty_result,
    )
    render_process_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


class _ResumeWithoutModel:
    """The runtime handed to an explicit resume: it must never be asked.

    A resume applies persisted output only, so no configured runtime is
    selected or launched for it; an unavailable runtime cannot block it.
    """

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        raise ModelRuntimeError(f"An explicit {RESUME_OPTION} never invokes a model.")


def _run_standard_process(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    try:
        settings = load_fibery_settings()
        policies = load_autonomy_policies()
        model: ModelRuntime
        if arguments.resume_result is not None:
            model = _ResumeWithoutModel()
        else:
            selection = select_runtime(
                load_model_runtime_config(),
                STANDARD_REQUIREMENT_PROCESSOR_ROLE,
                runtime_override=arguments.runtime,
                model_override=arguments.model,
            )
            model = LocalCliModelRuntime(selection)
        client = _client_with_space_id(settings)
    except (ConfigurationError, ModelRuntimeConfigError) as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    workspace = FiberyRawProcessorWorkspace(client=client, space=settings.space)
    result = process_standard_requirement(
        workspace,
        model,
        arguments.requirement,
        recover_empty_result=arguments.recover_empty_result,
        resume_result=arguments.resume_result,
        new_iteration_after=arguments.new_iteration_after,
        policies=policies,
    )
    render_standard_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


def _run_standard_review(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    try:
        settings = load_fibery_settings()
        policies = load_autonomy_policies()
        selection = select_runtime(
            load_model_runtime_config(),
            STANDARD_REQUIREMENT_REVIEWER_ROLE,
            runtime_override=arguments.runtime,
            model_override=arguments.model,
        )
        client = _client_with_space_id(settings)
    except (ConfigurationError, ModelRuntimeConfigError) as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    workspace = FiberyRawProcessorWorkspace(client=client, space=settings.space)
    result = review_standard_requirement(
        workspace,
        LocalCliModelRuntime(selection),
        arguments.requirement,
        recover_empty_result=arguments.recover_empty_result,
        policies=policies,
    )
    render_review_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


def _run_requirement_approve(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    """The admin/compatibility approval. No model runtime is configured or invoked."""
    try:
        settings = load_fibery_settings()
        policies = load_autonomy_policies()
    except ConfigurationError as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    acknowledged = (
        ReviewVerdict(arguments.acknowledge_verdict)
        if arguments.acknowledge_verdict
        else None
    )
    result = approve_standard_requirement(
        _ready_workspace(settings),
        arguments.requirement,
        acknowledged,
        policies=policies,
    )
    render_ready_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


def _run_requirement_rework(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    """The admin/compatibility rework. No model runtime is configured or invoked."""
    try:
        settings = load_fibery_settings()
    except ConfigurationError as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    result = rework_standard_requirement(
        _ready_workspace(settings), arguments.requirement
    )
    render_ready_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


def _run_requirement_apply(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    """Deterministic application. No model runtime is configured or invoked."""
    try:
        settings = load_fibery_settings()
        policies = load_autonomy_policies()
    except ConfigurationError as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    result = apply_standard_requirement(
        _ready_workspace(settings), arguments.requirement, policies=policies
    )
    render_apply_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


def _architecture_workspaces(
    settings: FiberySettings,
) -> tuple[ProjectCodeLookup, CycleWorkspace, RequirementEvidenceWorkspace]:
    """The Project, Architecture and Requirement adapters of one workspace.

    All three share one client, so one invocation reads one Fibery workspace
    under one workspace identity, the one the guard is scoped by. The Space id
    is resolved here, before the guard, and nothing else is read. The autonomy
    policies are read first: a broken `[autonomy]` table refuses before any
    Fibery read.
    """
    policies = load_autonomy_policies()
    client = _client_with_space_id(settings)
    return (
        FiberyHttpWorkspace(client=client, space=settings.space),
        FiberyArchitectureWorkspace(client=client, space=settings.space),
        # Admission checks delegated defaults against the policies active now.
        PolicyBoundEvidence(
            FiberyRawProcessorWorkspace(client=client, space=settings.space),
            policies,
        ),
    )


def _tsa_clock() -> datetime:
    return datetime.now(UTC)


def _tsa_role_runtime(role: str) -> ModelRuntime:
    """One TSA role through the unchanged selection; no command overrides it."""
    return LocalCliModelRuntime(select_runtime(load_model_runtime_config(), role))


def _architecture_session(settings: FiberySettings) -> ArchitectureSession:
    """The invocation's adapters; each TSA role is configured only when used."""
    projects, workspace, evidence = _architecture_workspaces(settings)
    return ArchitectureSession(
        projects=projects,
        workspace=workspace,
        evidence=evidence,
        architect_model=ConfiguredRoleRuntime(TSA_ARCHITECT_ROLE, _tsa_role_runtime),
        reviewer_model=ConfiguredRoleRuntime(TSA_REVIEWER_ROLE, _tsa_role_runtime),
        clock=_tsa_clock,
    )


def _run_architecture(
    command: ArchitectureCommand,
    out: TextIO,
    error_out: TextIO,
    *,
    is_mutating: bool,
    as_json: bool = False,
) -> int:
    """Build the session, guard a mutating command, render its one result."""
    try:
        session = _architecture_session(load_fibery_settings())
    except ConfigurationError as error:
        result = workspace_unavailable(error)
    else:
        result = run_guarded(session, command) if is_mutating else command(session)
    stream = out if result.is_normal else error_out
    render_architecture_result(result, stream, as_json=as_json)
    return exit_code_for(result.code)


def _start_inputs(arguments: argparse.Namespace) -> StartInputs:
    """Flag presence decides the UX branch; every value is I05's to validate.

    Requirement ids pass through as given, so I05 normalizes them and reports
    a duplicate; an omitted --ux-scope is every selected Requirement.
    """
    usage_error = arguments.parser.error
    requirements = tuple(arguments.requirements or ())
    if arguments.ux == UX_APPLICABLE_CHOICE:
        if arguments.ux_document is None:
            usage_error("--ux applicable requires --ux-document")
        if arguments.ux_reason is not None:
            usage_error("--ux-reason is only for --ux not-applicable")
        scope = requirements if arguments.ux_scope is None else arguments.ux_scope
        ux: UxApplicable | UxNotApplicable = UxApplicable(
            arguments.ux_document, tuple(scope)
        )
    else:
        if arguments.ux_reason is None:
            usage_error("--ux not-applicable requires --ux-reason")
        if arguments.ux_document is not None or arguments.ux_scope is not None:
            usage_error("--ux-document and --ux-scope are only for --ux applicable")
        ux = UxNotApplicable(arguments.ux_reason)
    return StartInputs(
        requirement_ids=requirements,
        ux=ux,
        accept_inputs=arguments.accept_inputs,
        accept_ux=arguments.accept_ux,
    )


def _run_architecture_start(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    command = functools.partial(
        start_cycle,
        project=arguments.project,
        cycle_id=arguments.cycle,
        inputs=_start_inputs(arguments),
    )
    return _run_architecture(command, out, error_out, is_mutating=True)


def _run_architecture_resume(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    command = functools.partial(
        resume_cycle, project=arguments.project, cycle_id=arguments.cycle
    )
    return _run_architecture(command, out, error_out, is_mutating=True)


def _run_architecture_rework(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    command = functools.partial(
        rework_cycle,
        project=arguments.project,
        cycle_id=arguments.cycle,
        iteration=arguments.iteration,
        review_result_document_id=arguments.review_result_id,
        reason=arguments.reason,
    )
    return _run_architecture(command, out, error_out, is_mutating=True)


def _accepted_dispositions(
    arguments: argparse.Namespace,
) -> tuple[AcceptedDisposition, ...]:
    """Every --accept-risk with its own reason, in the caller's order."""
    pairs = arguments.dispositions or []
    if pairs and pairs[-1][1] is None:
        arguments.parser.error(f"--accept-risk {pairs[-1][0]!r} has no --accept-reason")
    return tuple(AcceptedDisposition(ref, reason) for ref, reason in pairs)


def _run_architecture_approve(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    """Model-free: no TSA role is configured, selected or launched."""
    command = functools.partial(
        approve_cycle,
        project=arguments.project,
        cycle_id=arguments.cycle,
        iteration=arguments.iteration,
        review_result_document_id=arguments.review_result_id,
        dispositions=_accepted_dispositions(arguments),
    )
    return _run_architecture(command, out, error_out, is_mutating=True)


def _run_architecture_inspect(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    """Read-only, unguarded and model-free."""
    command = functools.partial(
        inspect_cycle, project=arguments.project, cycle_id=arguments.cycle
    )
    return _run_architecture(
        command, out, error_out, is_mutating=False, as_json=arguments.as_json
    )


def _poll_interval_seconds(text: str) -> int:
    """`--poll-interval-seconds`: a whole number of seconds, at least the minimum."""
    try:
        return require_poll_interval(int(text))
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            "expected a whole number of seconds, at least "
            f"{MINIMUM_POLL_INTERVAL_SECONDS}; got {text!r}"
        ) from error


def _run_worker(arguments: argparse.Namespace, out: TextIO, error_out: TextIO) -> int:
    """`sdlc worker run`: the foreground state-driven runner, until Ctrl-C.

    Configuration, the Space UUID the lock is scoped by, and every model role
    resolve before the lock is taken, and the lock and the Processing Status
    preflight before the first poll, so none of their failures can leave a
    Requirement claimed.
    """
    try:
        settings = load_fibery_settings()
        workspace = _runner_workspace(settings)
        workers = _runner_workers(
            workspace, load_model_runtime_config(), load_autonomy_policies
        )
    except (ConfigurationError, ModelRuntimeConfigError) as error:
        _render_runner_code(
            RunnerCode.WORKER_RUNNER_CONFIGURATION_INVALID, str(error), error_out
        )
        return EXIT_FAILURE
    return _run_guarded(
        workspace, workers, arguments.poll_interval_seconds, out, error_out
    )


def _run_guarded(
    workspace: FiberyRawProcessorWorkspace,
    workers: RequirementWorkers,
    poll_interval_seconds: int,
    out: TextIO,
    error_out: TextIO,
) -> int:
    """Hold the workspace lock for the runner's whole life; report each refusal."""
    try:
        with hold_workspace(workspace.lock_scope):
            run_requirement_runner(
                workspace,
                workers,
                sleep=_sleep,
                report=functools.partial(render_cycle, out=out, error_out=error_out),
                should_continue=_keep_running,
                poll_interval_seconds=poll_interval_seconds,
                on_started=functools.partial(_render_started, stream=out),
            )
    except WorkerRunnerBusy as error:
        _render_runner_code(RunnerCode.WORKER_RUNNER_BUSY, str(error), error_out)
        return EXIT_FAILURE
    except WorkerRunnerGuardUnavailable as error:
        code = RunnerCode.WORKER_RUNNER_GUARD_UNAVAILABLE
        _render_runner_code(code, str(error), error_out)
        return EXIT_FAILURE
    except RunnerPreflightError as error:
        message = f"{error}\n\nSee {WORKER_SETUP_DOCUMENT}."
        _render_runner_code(
            RunnerCode.WORKER_RUNNER_PREFLIGHT_FAILED, message, error_out
        )
        return EXIT_FAILURE
    except KeyboardInterrupt:
        _render_runner_code(RunnerCode.WORKER_RUNNER_STOPPED, RUNNER_STOPPED_NOTE, out)
        return EXIT_INTERRUPTED
    return EXIT_SUCCESS


def _runner_workspace(settings: FiberySettings) -> FiberyRawProcessorWorkspace:
    """The runner's adapter, on the one client it uses for its whole life.

    The Space UUID is resolved here, before the runner lock scoped by it and
    before the first poll, and is then remembered: no cycle looks it up again.
    """
    return FiberyRawProcessorWorkspace(
        client=_client_with_space_id(settings), space=settings.space
    )


def _runner_workers(
    workspace: FiberyRawProcessorWorkspace,
    # The parsed [model_runtime] table, as load_model_runtime_config returns it.
    runtime_config: dict[str, Any],
    load_policies: Callable[[], AutonomyPolicies],
) -> RequirementWorkers:
    """The four existing workers, bound to the configured roles; Apply is model-free.

    Every role resolves here, before the runner starts, so a configuration
    error stops it before any Requirement is claimed. Nothing overrides a role.
    The autonomy policies are not part of that composition: every Standard
    stage reads them again as it starts, so a policy the operator changed,
    disabled or broke is never the authority for later work
    (Requirement-Autonomous-Resolution-v0.1 §3.4). RAW processing reads none.
    """
    # Read now only so a broken [autonomy] table stops the runner before any
    # claim. What it says authorizes nothing: each stage reads its own.
    load_policies()
    raw, standard, reviewer = (
        LocalCliModelRuntime(select_runtime(runtime_config, role))
        for role in (
            RAW_REQUIREMENT_PROCESSOR_ROLE,
            STANDARD_REQUIREMENT_PROCESSOR_ROLE,
            STANDARD_REQUIREMENT_REVIEWER_ROLE,
        )
    )
    return RequirementWorkers(
        process_raw=functools.partial(process_raw_requirement, workspace, raw),
        process_standard=_under_current_policies(
            functools.partial(process_standard_requirement, workspace, standard),
            load_policies,
            _refused_process,
        ),
        review_standard=_under_current_policies(
            functools.partial(review_standard_requirement, workspace, reviewer),
            load_policies,
            _refused_review,
        ),
        apply_standard=_under_current_policies(
            functools.partial(apply_standard_requirement, workspace),
            load_policies,
            _refused_apply,
        ),
    )


def _under_current_policies[Result](
    stage: Callable[..., Result],
    load_policies: Callable[[], AutonomyPolicies],
    refuse: Callable[[AutonomyPolicyError], Result],
) -> Callable[..., Result]:
    """`stage`, run under the policies the configuration holds as it starts.

    Nothing is cached between stages and nothing falls back: a configuration
    that no longer loads refuses the stage before it reads Fibery or invokes
    a model, and the runner marks the claimed cycle Failed.
    """

    def run(entity_id: str, **options: Any) -> Result:
        try:
            policies = load_policies()
        except AutonomyPolicyError as error:
            return refuse(error)
        return stage(entity_id, policies=policies, **options)

    return run


def _refused_process(error: AutonomyPolicyError) -> StandardProcessResult:
    return StandardProcessResult(
        code=StandardProcessResultCode.AUTONOMY_POLICY_INVALID,
        message=POLICY_REFUSAL,
        details=(str(error),),
    )


def _refused_review(error: AutonomyPolicyError) -> StandardReviewResult:
    return StandardReviewResult(
        code=StandardReviewResultCode.AUTONOMY_POLICY_INVALID,
        message=POLICY_REFUSAL,
        details=(str(error),),
    )


def _refused_apply(error: AutonomyPolicyError) -> ApplyResult:
    return ApplyResult(
        code=ApplyResultCode.AUTONOMY_POLICY_INVALID,
        message=POLICY_REFUSAL,
        details=(str(error),),
    )


def _sleep(seconds: float) -> None:
    """The runner's idle wait on the process clock; tests replace it."""
    time.sleep(seconds)


def _keep_running() -> bool:
    """The runner has no stop condition of its own: Ctrl-C ends it."""
    return True


def _render_started(interval: int, stream: TextIO) -> None:
    _render_runner_code(
        RunnerCode.WORKER_RUNNER_STARTED,
        f"Watching every Project of the configured Fibery workspace; idle poll "
        f"interval {interval} s. Ctrl-C stops the runner.",
        stream,
    )


def _render_runner_code(code: RunnerCode, message: str, stream: TextIO) -> None:
    print(code.value, file=stream)
    print(file=stream)
    print(message, file=stream)
    stream.flush()


def render_cycle(cycle: CycleReport, out: TextIO, error_out: TextIO) -> None:
    """One block per cycle: codes and identity only, never Requirement content.

    An idle cycle prints nothing, so an idle runner does not flood its log.
    The dispatch's own messages are not printed: a worker's message may quote
    Requirement text.
    """
    if cycle.outcome is CycleOutcome.IDLE:
        return
    stream = out if cycle.is_normal else error_out
    print(f"\n{cycle.outcome.value}", file=stream)
    print(cycle.message, file=stream)
    record = cycle.requirement
    if record is not None:
        print(
            f"Requirement: {record.requirement_id} (entity {record.id}); Type "
            f"{record.type_name}; State {record.state}; Processing Status "
            f"{record.processing_status}",
            file=stream,
        )
    dispatched = cycle.dispatch_result
    if dispatched is not None:
        worker = dispatched.worker_result
        print(
            f"Dispatch: {dispatched.outcome.value}; worker result "
            f"{worker.code.value if worker is not None else 'none'}",
            file=stream,
        )
        if dispatched.progressed:
            print(f"Progressed: {', '.join(dispatched.progressed)}", file=stream)
    for item in cycle.details:
        print(f"- {item}", file=stream)
    stream.flush()


def render_apply_result(result: ApplyResult, stream: TextIO) -> None:
    """Print the result code first, then the human readable detail."""
    print(result.code.value, file=stream)
    print(file=stream)
    print(result.message, file=stream)

    if result.code is ApplyResultCode.REQUIREMENT_APPLIED:
        if result.relations_added:
            print("\nRelations written:", file=stream)
            for item in result.relations_added:
                print(f"- {item}", file=stream)
        if result.relations_present:
            print("\nRelations already present:", file=stream)
            for item in result.relations_present:
                print(f"- {item}", file=stream)
        return
    if result.code is ApplyResultCode.REQUIREMENT_ALREADY_APPLIED:
        return

    if result.created:
        print("\nApplied in Fibery (left in place):", file=stream)
        for item in result.created:
            print(f"- {item}", file=stream)
    if result.details:
        print("\nDetails:", file=stream)
        for item in result.details:
            print(f"- {item}", file=stream)


def _ready_workspace(settings: FiberySettings) -> FiberyRawProcessorWorkspace:
    """The adapter for approve, rework and apply.

    None of the three creates a Document or takes a lock, so none resolves a
    Space UUID and none pays for the lookup.
    """
    return FiberyRawProcessorWorkspace(
        client=FiberyClient(settings), space=settings.space
    )


def render_ready_result(result: ReadyDecisionResult, stream: TextIO) -> None:
    """Print the result code first, then the human readable detail.

    The verdict is what the human decided about, not whether the decision was
    recorded: an approval acknowledging BLOCKING is a successful run.
    """
    print(result.code.value, file=stream)
    print(file=stream)
    print(result.message, file=stream)

    if result.code in {
        ReadyDecisionResultCode.REQUIREMENT_APPROVED,
        ReadyDecisionResultCode.VERDICT_ACKNOWLEDGEMENT_REQUIRED,
        ReadyDecisionResultCode.VERDICT_ACKNOWLEDGEMENT_MISMATCH,
        ReadyDecisionResultCode.INVALID_VERDICT_ACKNOWLEDGEMENT,
    }:
        _render_ready_sections(result, stream)
    if result.details:
        print("\nDetails:", file=stream)
        for item in result.details:
            print(f"- {item}", file=stream)


def _render_ready_sections(result: ReadyDecisionResult, stream: TextIO) -> None:
    """What the decision is about. Nothing here was written by the decision."""
    print(f"\nReview Result {result.iteration}: verdict {result.verdict}", file=stream)
    if result.blocking:
        print("\nBlocking:", file=stream)
        for item in result.blocking:
            print(f"- {item}", file=stream)
    if result.warnings:
        print("\nWarnings:", file=stream)
        for item in result.warnings:
            print(f"- {item}", file=stream)
    if result.relations:
        print("\nConfirmed relations (still not written to Fibery):", file=stream)
        for item in result.relations:
            print(f"- {item}", file=stream)


def render_review_result(result: StandardReviewResult, stream: TextIO) -> None:
    """Print the result code first, then the human readable detail.

    The verdict is reported separately from the status: a BLOCKING verdict is a
    successful run, and the exit code says whether the review executed, not
    whether the Requirement is good.
    """
    print(result.code.value, file=stream)
    print(file=stream)
    print(result.message, file=stream)

    if result.code is StandardReviewResultCode.REQUIREMENT_REVIEWED:
        print(
            f"\nModel invoked: {'yes' if result.model_invoked else 'no'}",
            file=stream,
        )
        _render_review_sections(result, stream)
        return
    if result.code is StandardReviewResultCode.NO_CHANGES_TO_REVIEW:
        return

    if result.created:
        print("\nCreated in Fibery (left in place):", file=stream)
        for item in result.created:
            print(f"- {item}", file=stream)
    if result.details:
        print("\nDetails:", file=stream)
        for item in result.details:
            print(f"- {item}", file=stream)


def _render_review_sections(result: StandardReviewResult, stream: TextIO) -> None:
    """What a human at Ready needs to decide, nothing was changed by any of it."""
    if result.blocking:
        print("\nBlocking:", file=stream)
        for item in result.blocking:
            print(f"- {item}", file=stream)
    if result.warnings:
        print("\nWarnings:", file=stream)
        for item in result.warnings:
            print(f"- {item}", file=stream)
    if result.verifications:
        print("\nProcess findings verified:", file=stream)
        for item in result.verifications:
            print(f"- {item}", file=stream)
    if result.relations:
        print("\nRelation proposals (none written to Fibery):", file=stream)
        for item in result.relations:
            print(f"- {item}", file=stream)


def render_standard_result(result: StandardProcessResult, stream: TextIO) -> None:
    """Print the result code first, then the human readable detail."""
    print(result.code.value, file=stream)
    print(file=stream)
    print(result.message, file=stream)

    if result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED:
        print(
            f"\nModel invoked: {'yes' if result.model_invoked else 'no (resumed)'}",
            file=stream,
        )
        if result.findings:
            print("\nFindings for review (nothing was modified):", file=stream)
            for item in result.findings:
                print(f"- {item}", file=stream)
        if result.proposed_relations:
            print("\nProposed relations (not written to Fibery):", file=stream)
            for item in result.proposed_relations:
                print(f"- {item}", file=stream)
        return
    if result.code is StandardProcessResultCode.NO_CHANGES_TO_PROCESS:
        return

    if result.created:
        print("\nCreated in Fibery (left in place):", file=stream)
        for item in result.created:
            print(f"- {item}", file=stream)
    if result.details:
        print("\nDetails:", file=stream)
        for item in result.details:
            print(f"- {item}", file=stream)


def render_process_result(result: ProcessResult, stream: TextIO) -> None:
    """Print the result code first, then the human readable detail."""
    print(result.code.value, file=stream)
    print(file=stream)
    print(result.message, file=stream)

    if result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED:
        print(f"\nModel invoked: {'yes' if result.model_invoked else 'no (resumed)'}")
        if result.candidates:
            print("\nStandard candidates:", file=stream)
            for item in result.candidates:
                print(f"- {item}", file=stream)
        if result.no_candidate_reason:
            print(f"\nNo candidates: {result.no_candidate_reason}", file=stream)
        if result.findings:
            print("\nFindings for review (nothing was modified):", file=stream)
            for item in result.findings:
                print(f"- {item}", file=stream)
        return

    if result.created:
        print("\nCreated in Fibery (left in place):", file=stream)
        for item in result.created:
            print(f"- {item}", file=stream)
    if result.details:
        print("\nDetails:", file=stream)
        for item in result.details:
            print(f"- {item}", file=stream)


def render_add_result(result: AddResult, stream: TextIO) -> None:
    """Print the result code first, then the human readable detail."""
    print(result.code.value, file=stream)
    print(file=stream)

    if result.code is AddResultCode.RAW_REQUIREMENT_ADDED:
        print("RAW requirement added.\n", file=stream)
        print(f"Project: {result.project_name}", file=stream)
        print(f"Project Code: {result.project_code}\n", file=stream)
        print("Requirement:", file=stream)
        print(f"{result.requirement_id} — {result.title}\n", file=stream)
        print("State: Draft", file=stream)
        print("Revision: 1\n", file=stream)
        print("Root Document:", file=stream)
        print(f"{result.document_name}\n", file=stream)
        print("Next:", file=stream)
        print("Review the RAW Requirement in Fibery.", file=stream)
        print("When ready, move it from Draft → Process.", file=stream)
        return

    print(result.message, file=stream)
    if result.code is AddResultCode.REQUIREMENT_ALREADY_ADDED:
        print("\nExisting Requirement:", file=stream)
        print(f"{result.requirement_id}", file=stream)
        return

    _render_add_sections(result, stream)


def _render_add_sections(result: AddResult, stream: TextIO) -> None:
    if result.created:
        print("\nCreated in Fibery (left in place):", file=stream)
        for item in result.created:
            print(f"- {item}", file=stream)
    if result.failed:
        print("\nFailed:", file=stream)
        for item in result.failed:
            print(f"- {item}", file=stream)
    if result.details:
        print("\nDetails:", file=stream)
        for item in result.details:
            print(f"- {item}", file=stream)


def render_result(result: InitResult, stream: TextIO) -> None:
    """Print the result code first, then the human readable detail."""
    print(result.code.value, file=stream)
    print(file=stream)

    if result.code is ResultCode.PROJECT_INITIALIZED:
        _render_initialized(result, stream)
        return

    print(result.message, file=stream)
    if result.code is ResultCode.PROJECT_ALREADY_EXISTS:
        print("\nNo changes were made.\n", file=stream)
        print(NEXT_STEP_HINT, file=stream)
        return

    _render_sections(result, stream)


def _render_initialized(result: InitResult, stream: TextIO) -> None:
    print("Project initialized.\n", file=stream)
    print(f"Name: {result.project_name}", file=stream)
    print(f"Code: {result.project_code}", file=stream)
    print("State: Planned\n", file=stream)
    print("Next:", file=stream)
    print("Use `sdlc project requirement add`", file=stream)
    print("to add the first RAW requirement.", file=stream)


def _render_sections(result: InitResult, stream: TextIO) -> None:
    if result.created:
        print("\nCreated in Fibery (left in place):", file=stream)
        for item in result.created:
            print(f"- {item}", file=stream)
    if result.failed:
        print("\nFailed:", file=stream)
        for item in result.failed:
            print(f"- {item}", file=stream)
    if result.details:
        print("\nDetails:", file=stream)
        for item in result.details:
            print(f"- {item}", file=stream)


if __name__ == "__main__":
    raise SystemExit(main())
