"""`sdlc` command line entry point."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

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

PROGRAM_NAME = "sdlc"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1

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
        "requirement", help="Requirement level commands."
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
        "process", help="Decompose a RAW Requirement into Standard candidates."
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
        help="Normalize and analyze a Standard Requirement in Process.",
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
        help="Independently review a Standard Requirement in Review.",
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
        help="Record a human approval of a Standard Requirement in Ready.",
    )
    approve.add_argument(
        "--requirement", required=True, help="Standard Requirement entity id."
    )
    approve.add_argument(
        "--acknowledge-verdict",
        choices=[verdict.value for verdict in ReviewVerdict],
        help=(
            "Name the current Review verdict being approved despite. Required "
            "for NEEDS_WORK and BLOCKING; never for PASS."
        ),
    )
    approve.set_defaults(handler=_run_requirement_approve)

    rework = requirement_commands.add_parser(
        "rework",
        help="Send a Standard Requirement in Ready back to Process.",
    )
    rework.add_argument(
        "--requirement", required=True, help="Standard Requirement entity id."
    )
    rework.set_defaults(handler=_run_requirement_rework)

    apply = requirement_commands.add_parser(
        "apply",
        help="Deterministically apply an approved Standard Requirement in Apply.",
    )
    apply.add_argument(
        "--requirement", required=True, help="Standard Requirement entity id."
    )
    apply.set_defaults(handler=_run_requirement_apply)

    return parser


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
    """A human decision. No model runtime is configured, selected or invoked."""
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
    """A human decision. No model runtime is configured, selected or invoked."""
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
        print(f"\nRoot Document: Requirements/{result.root_folder}", file=stream)
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
        print("Document:", file=stream)
        print(f"{result.document_path}\n", file=stream)
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
    print("Documents:", file=stream)
    for path in result.documents:
        print(f"✓ {path}", file=stream)
    print("\nNext:", file=stream)
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
