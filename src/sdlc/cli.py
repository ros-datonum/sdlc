"""`sdlc` command line entry point.

Currently exposes one capability: `sdlc project init`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from sdlc.config import ConfigurationError, load_fibery_settings
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import FiberyHttpWorkspace
from sdlc.project_init import initialize_project
from sdlc.results import InitResult, ResultCode

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
