"""`sdlc` command line entry point."""

from __future__ import annotations

import argparse
import functools
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any, TextIO

from sdlc.config import ConfigurationError, FiberySettings, load_fibery_settings
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import (
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
    ModelRuntimeConfigError,
    load_model_runtime_config,
    select_runtime,
)
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

    _add_worker_commands(commands)

    return parser


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

    workspace = FiberyHttpWorkspace(
        client=FiberyClient(settings),
        space=settings.space,
        space_id=settings.space_id,
    )
    result = initialize_project(
        workspace,
        name=arguments.name,
        code=arguments.code,
        description=arguments.description,
    )
    render_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


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

    workspace = FiberyRequirementWorkspace(
        client=FiberyClient(settings),
        space=settings.space,
        space_id=settings.space_id,
    )
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
    except (ConfigurationError, ModelRuntimeConfigError) as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    workspace = FiberyRawProcessorWorkspace(
        client=FiberyClient(settings),
        space=settings.space,
        space_id=settings.space_id,
    )
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
    except (ConfigurationError, ModelRuntimeConfigError) as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    workspace = FiberyRawProcessorWorkspace(
        client=FiberyClient(settings),
        space=settings.space,
        space_id=settings.space_id,
    )
    result = process_standard_requirement(
        workspace,
        model,
        arguments.requirement,
        recover_empty_result=arguments.recover_empty_result,
        resume_result=arguments.resume_result,
        new_iteration_after=arguments.new_iteration_after,
    )
    render_standard_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


def _run_standard_review(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    try:
        settings = load_fibery_settings()
        selection = select_runtime(
            load_model_runtime_config(),
            STANDARD_REQUIREMENT_REVIEWER_ROLE,
            runtime_override=arguments.runtime,
            model_override=arguments.model,
        )
    except (ConfigurationError, ModelRuntimeConfigError) as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    workspace = FiberyRawProcessorWorkspace(
        client=FiberyClient(settings),
        space=settings.space,
        space_id=settings.space_id,
    )
    result = review_standard_requirement(
        workspace,
        LocalCliModelRuntime(selection),
        arguments.requirement,
        recover_empty_result=arguments.recover_empty_result,
    )
    render_review_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


def _run_requirement_approve(
    arguments: argparse.Namespace, out: TextIO, error_out: TextIO
) -> int:
    """The admin/compatibility approval. No model runtime is configured or invoked."""
    try:
        settings = load_fibery_settings()
    except ConfigurationError as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    acknowledged = (
        ReviewVerdict(arguments.acknowledge_verdict)
        if arguments.acknowledge_verdict
        else None
    )
    result = approve_standard_requirement(
        _ready_workspace(settings), arguments.requirement, acknowledged
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
    except ConfigurationError as error:
        print(str(error), file=error_out)
        return EXIT_FAILURE

    result = apply_standard_requirement(
        _ready_workspace(settings), arguments.requirement
    )
    render_apply_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


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

    Configuration and every model role resolve before the lock is taken, and
    the lock and the Processing Status preflight before the first poll, so
    none of their failures can leave a Requirement claimed.
    """
    try:
        settings = load_fibery_settings()
        workspace = _runner_workspace(settings)
        workers = _runner_workers(workspace, load_model_runtime_config())
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
    return FiberyRawProcessorWorkspace(
        client=FiberyClient(settings),
        space=settings.space,
        space_id=settings.space_id,
    )


def _runner_workers(
    workspace: FiberyRawProcessorWorkspace,
    # The parsed [model_runtime] table, as load_model_runtime_config returns it.
    runtime_config: dict[str, Any],
) -> RequirementWorkers:
    """The four existing workers, bound to the configured roles; Apply is model-free.

    Every role resolves here, before the runner starts, so a configuration
    error stops it before any Requirement is claimed. Nothing overrides a role.
    """
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
        process_standard=functools.partial(
            process_standard_requirement, workspace, standard
        ),
        review_standard=functools.partial(
            review_standard_requirement, workspace, reviewer
        ),
        apply_standard=functools.partial(apply_standard_requirement, workspace),
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
    return FiberyRawProcessorWorkspace(
        client=FiberyClient(settings),
        space=settings.space,
        space_id=settings.space_id,
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
