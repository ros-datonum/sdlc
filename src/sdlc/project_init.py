"""`sdlc project init` — deterministic Project bootstrap.

Implements Project-Init-Spec-v0.3. No model is invoked anywhere in this flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sdlc.fibery_workspace import (
    FiberyError,
    FiberyWorkspace,
    FolderNode,
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
DISPLAY_PATH_SEPARATOR = "/"
REQUIREMENTS_FOLDER_NAME = "Requirements"
REQUIREMENT_STAGE_FOLDER_NAMES = ("Raw", "Draft", "Approved")

ROOT_FOLDER_INDEX = 0
REQUIREMENTS_FOLDER_INDEX = 1


def project_folder_tree(project_name: str) -> tuple[tuple[str, int | None], ...]:
    """Return the folder structure of section 9 as (name, parent index) pairs.

    The parent index refers to an earlier position in this same tuple, so
    walking it in order always creates a parent before its children. The root
    has no parent.
    """
    return (
        (project_name, None),
        (REQUIREMENTS_FOLDER_NAME, ROOT_FOLDER_INDEX),
        *(
            (stage, REQUIREMENTS_FOLDER_INDEX)
            for stage in REQUIREMENT_STAGE_FOLDER_NAMES
        ),
    )


def folder_display_paths(project_name: str) -> tuple[str, ...]:
    """Human readable paths for the same tree, for output only.

    Folder names in Fibery are the leaf names; these joined paths are never
    used to address anything.
    """
    tree = project_folder_tree(project_name)
    paths: list[str] = []
    for name, parent in tree:
        paths.append(
            name if parent is None else f"{paths[parent]}{DISPLAY_PATH_SEPARATOR}{name}"
        )
    return tuple(paths)


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
    """Create a Project and its document structure, or report why not."""
    project_name = name.strip() if name else ""
    if not project_name:
        return InitResult(
            code=ResultCode.INVALID_INPUT,
            message="Project Name is required.",
            project_name=project_name,
        )

    journal = _Journal()
    folders: list[FolderNode] = []
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

        folders = _create_folder_structure(workspace, project_name, journal)

        _link_documents_root_folder(workspace, project_id, folders[ROOT_FOLDER_INDEX])
        journal.created.append(
            f"Project Documents Root Folder ID = {folders[ROOT_FOLDER_INDEX].id}"
        )

        _validate_created_state(
            workspace, project_id, project_name, project_code, folders
        )
    except _StageFailed as failure:
        return _failure_result(failure, journal, project_name, project_code, folders)

    return InitResult(
        code=ResultCode.PROJECT_INITIALIZED,
        message=f"Project {project_name!r} initialized.",
        project_name=project_name,
        project_code=project_code,
        documents=folder_display_paths(project_name),
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
    folders: list[FolderNode],
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
            documents=folder_display_paths(project_name),
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
            documents=folder_display_paths(project_name),
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


def _create_folder_structure(
    workspace: FiberyWorkspace, project_name: str, journal: _Journal
) -> list[FolderNode]:
    """Create every Folder, recording each one as it becomes durable."""
    created: list[FolderNode] = []
    display = folder_display_paths(project_name)
    for index, (name, parent) in enumerate(project_folder_tree(project_name)):
        parent_id = None if parent is None else created[parent].id
        try:
            folder = workspace.create_folder(name, parent_id)
        except FiberyError as error:
            raise _StageFailed(
                ResultCode.DOCUMENT_STRUCTURE_CREATE_FAILED,
                f"Could not create the folder {display[index]!r}.",
                (str(error),),
            ) from error
        created.append(folder)
        journal.created.append(f"Folder {display[index]}")
    return created


def _link_documents_root_folder(
    workspace: FiberyWorkspace, project_id: str, root: FolderNode
) -> None:
    try:
        workspace.set_documents_root_folder(project_id, root.id)
    except FiberyError as error:
        raise _StageFailed(
            ResultCode.FIBERY_WRITE_FAILED,
            f"Could not store the root Folder id for {root.name!r}.",
            (str(error),),
        ) from error


@dataclass(frozen=True)
class _CreatedState:
    """Everything section 14 validation compares against, read back from Fibery."""

    project: ProjectRecord | None
    projects_with_code: int
    folders_by_index: dict[int, FolderNode | None]


def _validate_created_state(
    workspace: FiberyWorkspace,
    project_id: str,
    project_name: str,
    project_code: str,
    folders: list[FolderNode],
) -> None:
    """Read the created state back and fail unless it matches the request."""
    state = _read_created_state(workspace, project_id, project_code, folders)
    problems = _collect_validation_problems(state, project_name, project_code, folders)
    if problems:
        raise _StageFailed(
            ResultCode.VALIDATION_FAILED,
            f"Post-create validation failed for Project {project_name!r}.",
            tuple(problems),
        )


def _read_created_state(
    workspace: FiberyWorkspace,
    project_id: str,
    project_code: str,
    folders: list[FolderNode],
) -> _CreatedState:
    try:
        project = workspace.read_project(project_id)
        projects_with_code = workspace.count_projects_with_code(project_code)
        folders_by_index = {
            index: workspace.resolve_folder(folder.id)
            for index, folder in enumerate(folders)
        }
    except FiberyError as error:
        raise _StageFailed(
            ResultCode.VALIDATION_FAILED,
            "Could not read the created state back from Fibery.",
            (str(error),),
        ) from error
    return _CreatedState(project, projects_with_code, folders_by_index)


def _collect_validation_problems(
    state: _CreatedState,
    project_name: str,
    project_code: str,
    folders: list[FolderNode],
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
    problems.extend(_folder_problems(state, project, project_name, folders))
    return problems


def _folder_problems(
    state: _CreatedState,
    project: ProjectRecord,
    project_name: str,
    folders: list[FolderNode],
) -> list[str]:
    """Check every created Folder reads back intact, and the root link.

    Each Folder is resolved by the id creation returned, never by name:
    Fibery allows sibling Folders with the same name under the same parent,
    so a name lookup can resolve someone else's Folder.
    """
    problems: list[str] = []
    display = folder_display_paths(project_name)
    for index, folder in enumerate(folders):
        found = state.folders_by_index.get(index)
        if found is None:
            problems.append(f"Folder {display[index]!r} ({folder.id}) does not exist.")
            continue
        if found.name != folder.name:
            problems.append(
                f"Folder {folder.id} is named {found.name!r}, expected {folder.name!r}."
            )
        if found.parent_id != folder.parent_id:
            problems.append(
                f"Folder {display[index]!r} has parent {found.parent_id!r}, "
                f"expected {folder.parent_id!r}."
            )

    root = folders[ROOT_FOLDER_INDEX]
    stored = project.documents_root_folder_id
    if not stored:
        problems.append("Documents Root Folder ID is empty.")
    elif stored != root.id:
        problems.append(
            f"Documents Root Folder ID is {stored!r}, expected {root.id!r}."
        )
    elif state.folders_by_index.get(ROOT_FOLDER_INDEX) is None:
        problems.append(
            f"Documents Root Folder ID {stored!r} does not resolve to a Folder."
        )
    return problems
