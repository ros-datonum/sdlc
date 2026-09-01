"""`sdlc` command line entry point.

Currently exposes one capability: `sdlc project init`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TextIO

from sdlc.config import ConfigurationError, load_fibery_settings
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import (
    FiberyHttpWorkspace,
    FiberyRawProcessorWorkspace,
    FiberyRequirementWorkspace,
)
from sdlc.model_runtime import LocalCliModelRuntime
from sdlc.model_runtime_config import (
    RAW_REQUIREMENT_PROCESSOR_ROLE,
    ModelRuntimeConfigError,
    load_model_runtime_config,
    select_runtime,
)
from sdlc.project_init import initialize_project
from sdlc.raw_processor import process_raw_requirement
from sdlc.requirement_add import add_raw_requirement
from sdlc.results import (
    AddResult,
    AddResultCode,
    InitResult,
    ProcessResult,
    ProcessResultCode,
    ResultCode,
)

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
    process.set_defaults(handler=_run_requirement_process)

    return parser


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
        workspace, LocalCliModelRuntime(selection), arguments.requirement
    )
    render_process_result(result, out if result.is_normal else error_out)
    return EXIT_SUCCESS if result.is_normal else EXIT_FAILURE


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
