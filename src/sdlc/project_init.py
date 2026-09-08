"""`sdlc project init` — deterministic Project bootstrap.

Implements Project-Init-Spec-v0.3. No model is invoked anywhere in this flow.

The Project entity is the whole contract. Requirement lifecycle placement is
defined by each Requirement's Type and State, and Root Documents are contained
by their Requirement, so no Document folder tree is created here. Human
navigation is a one-time Fibery workspace configuration (a Smart Folder with
mirrored context views) that this command neither creates nor validates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sdlc.fibery_workspace import (
    FiberyError,
    FiberyWorkspace,
    ProjectRecord,
)
from sdlc.project_code import (
    InvalidProjectCode,
    UnusableProjectName,
    candidate_project_codes,
    validate_project_code,
)
from sdlc.results import InitResult, ResultCode

PROJECT_INITIAL_STATE = "Planned"


class _StageFailed(Exception):
    """A stage of initialization could not complete."""

    def __init__(
        self, code: ResultCode, message: str, causes: tuple[str, ...] = ()
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.causes = causes


@dataclass
class _Journal:
    """Durable Fibery objects this invocation has already created."""

    created: list[str] = field(default_factory=list)

    @property
    def has_durable_state(self) -> bool:
        return bool(self.created)


def initialize_project(
    workspace: FiberyWorkspace,
    name: str,
    code: str | None = None,
    description: str | None = None,
) -> InitResult:
    """Create a Project entity, or report why not."""
    project_name = name.strip() if name else ""
    if not project_name:
        return InitResult(
            code=ResultCode.INVALID_INPUT,
            message="Project Name is required.",
            project_name=project_name,
        )

    journal = _Journal()
    project_code: str | None = None

    try:
        existing = _find_existing_project(workspace, project_name)
        if existing is not None:
            return _already_exists_result(existing, project_name)

        project_code = _resolve_project_code(workspace, project_name, code)
        project_id = _create_project_entity(workspace, project_name, project_code)
        journal.created.append(f"Project entity {project_id}")

        _apply_initial_state(workspace, project_id)
        journal.created.append(f"Project State = {PROJECT_INITIAL_STATE}")

        if description:
            _apply_description(workspace, project_id, description)
            journal.created.append("Project Description")

        _validate_created_state(workspace, project_id, project_name, project_code)
    except _StageFailed as failure:
        return _failure_result(failure, journal, project_name, project_code)

    return InitResult(
        code=ResultCode.PROJECT_INITIALIZED,
        message=f"Project {project_name!r} initialized.",
        project_name=project_name,
        project_code=project_code,
        created=tuple(journal.created),
    )


def _already_exists_result(existing: ProjectRecord, project_name: str) -> InitResult:
    return InitResult(
        code=ResultCode.PROJECT_ALREADY_EXISTS,
        message=f"Project {project_name!r} already exists.",
        project_name=project_name,
        project_code=existing.code,
    )


def _failure_result(
    failure: _StageFailed,
    journal: _Journal,
    project_name: str,
    project_code: str | None,
) -> InitResult:
    """Map a stage failure onto a spec result code.

    Once anything durable exists in Fibery the outcome is PARTIAL_INIT, and the
    original failure class is reported as the cause. Nothing is deleted.
    """
    if failure.code is ResultCode.VALIDATION_FAILED:
        return InitResult(
            code=ResultCode.VALIDATION_FAILED,
            message=failure.message,
            project_name=project_name,
            project_code=project_code,
            created=tuple(journal.created),
            details=failure.causes,
        )
    if journal.has_durable_state:
        return InitResult(
            code=ResultCode.PARTIAL_INIT,
            message=(
                f"Project {project_name!r} was partially initialized and left in place."
            ),
            project_name=project_name,
            project_code=project_code,
            created=tuple(journal.created),
            failed=(failure.code.value,),
            details=(failure.message, *failure.causes),
        )
    return InitResult(
        code=failure.code,
        message=failure.message,
        project_name=project_name,
        project_code=project_code,
        details=failure.causes,
    )


def _find_existing_project(
    workspace: FiberyWorkspace, project_name: str
) -> ProjectRecord | None:
    try:
        return workspace.find_project_by_name(project_name)
    except FiberyError as error:
        raise _StageFailed(
            ResultCode.FIBERY_READ_FAILED,
            f"Could not check whether Project {project_name!r} exists.",
            (str(error),),
        ) from error


def _resolve_project_code(
    workspace: FiberyWorkspace, project_name: str, requested: str | None
) -> str:
    """Validate a supplied Code, or derive a free one from the Project Name."""
    if requested is not None:
        return _validate_requested_code(workspace, requested)

    try:
        candidates = list(candidate_project_codes(project_name))
    except UnusableProjectName as error:
        raise _StageFailed(
            ResultCode.INVALID_INPUT,
            f"No Project Code can be derived from {project_name!r}.",
        ) from error

    for candidate in candidates:
        if _count_projects_with_code(workspace, candidate) == 0:
            return candidate

    raise _StageFailed(
        ResultCode.PROJECT_CODE_COLLISION,
        f"Every Project Code derived from {project_name!r} is already taken.",
        tuple(candidates[:1]),
    )


def _validate_requested_code(workspace: FiberyWorkspace, requested: str) -> str:
    try:
        code = validate_project_code(requested)
    except InvalidProjectCode as error:
        raise _StageFailed(ResultCode.INVALID_PROJECT_CODE, str(error)) from error

    if _count_projects_with_code(workspace, code) > 0:
        raise _StageFailed(
            ResultCode.PROJECT_CODE_COLLISION,
            f"Project Code {code!r} is already used by another Project.",
        )
    return code


def _count_projects_with_code(workspace: FiberyWorkspace, code: str) -> int:
    try:
        return workspace.count_projects_with_code(code)
    except FiberyError as error:
        raise _StageFailed(
            ResultCode.FIBERY_READ_FAILED,
            f"Could not check global uniqueness of Project Code {code!r}.",
            (str(error),),
        ) from error


def _create_project_entity(
    workspace: FiberyWorkspace, project_name: str, project_code: str
) -> str:
    try:
        return workspace.create_project(project_name, project_code)
    except FiberyError as error:
        raise _StageFailed(
            ResultCode.FIBERY_WRITE_FAILED,
            f"Could not create the Project entity for {project_name!r}.",
            (str(error),),
        ) from error


def _apply_initial_state(workspace: FiberyWorkspace, project_id: str) -> None:
    try:
        workspace.set_project_state(project_id, PROJECT_INITIAL_STATE)
    except FiberyError as error:
        raise _StageFailed(
            ResultCode.FIBERY_WRITE_FAILED,
            f"Could not set Project State to {PROJECT_INITIAL_STATE}.",
            (str(error),),
        ) from error


def _apply_description(
    workspace: FiberyWorkspace, project_id: str, description: str
) -> None:
    try:
        workspace.set_project_description(project_id, description)
    except FiberyError as error:
        raise _StageFailed(
            ResultCode.FIBERY_WRITE_FAILED,
            "Could not write the Project Description.",
            (str(error),),
        ) from error


@dataclass(frozen=True)
class _CreatedState:
    """Everything section 14 validation compares against, read back from Fibery."""

    project: ProjectRecord | None
    projects_with_code: int


def _validate_created_state(
    workspace: FiberyWorkspace,
    project_id: str,
    project_name: str,
    project_code: str,
) -> None:
    """Read the created state back and fail unless it matches the request."""
    state = _read_created_state(workspace, project_id, project_code)
    problems = _collect_validation_problems(state, project_name, project_code)
    if problems:
        raise _StageFailed(
            ResultCode.VALIDATION_FAILED,
            f"Post-create validation failed for Project {project_name!r}.",
            tuple(problems),
        )


def _read_created_state(
    workspace: FiberyWorkspace, project_id: str, project_code: str
) -> _CreatedState:
    try:
        project = workspace.read_project(project_id)
        projects_with_code = workspace.count_projects_with_code(project_code)
    except FiberyError as error:
        raise _StageFailed(
            ResultCode.VALIDATION_FAILED,
            "Could not read the created state back from Fibery.",
            (str(error),),
        ) from error
    return _CreatedState(project, projects_with_code)


def _collect_validation_problems(
    state: _CreatedState, project_name: str, project_code: str
) -> list[str]:
    project = state.project
    if project is None:
        return ["Project entity could not be read back."]

    problems: list[str] = []
    if project.name != project_name:
        problems.append(f"Project Name is {project.name!r}, expected {project_name!r}.")
    if not project.code:
        problems.append("Project Code is empty.")
    elif project.code != project_code:
        problems.append(f"Project Code is {project.code!r}, expected {project_code!r}.")
    if state.projects_with_code != 1:
        problems.append(
            f"Project Code {project_code!r} is used by "
            f"{state.projects_with_code} Projects, expected exactly 1."
        )
    if project.state != PROJECT_INITIAL_STATE:
        problems.append(
            f"Project State is {project.state!r}, expected {PROJECT_INITIAL_STATE!r}."
        )
    return problems
