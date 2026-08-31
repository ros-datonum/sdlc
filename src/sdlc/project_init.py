"""`sdlc project init` — deterministic Project bootstrap.

Implements Project-Init-Spec-v0.3. No model is invoked anywhere in this flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sdlc.fibery_workspace import (
    DocumentNode,
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
DOCUMENT_PATH_SEPARATOR = "/"
REQUIREMENTS_FOLDER_NAME = "Requirements"
REQUIREMENT_STAGE_FOLDER_NAMES = ("Raw", "Draft", "Approved")


def name_is_addressable(project_name: str) -> bool:
    """Reject Project Names that would corrupt the document addressing scheme.

    Fibery cannot nest sidebar Documents (Fibery-API-Constraints-v0.1,
    constraint 1), so the hierarchy of section 9 is encoded as a path in the
    document name. A Project Name containing the separator would therefore
    address nodes inside another Project's structure.
    """
    return DOCUMENT_PATH_SEPARATOR not in project_name


def project_document_paths(project_name: str) -> tuple[str, ...]:
    """Return the document structure of section 9, root first.

    Paths are ordered so that every node appears after its parent.
    """
    root = project_name
    requirements = f"{root}{DOCUMENT_PATH_SEPARATOR}{REQUIREMENTS_FOLDER_NAME}"
    stages = tuple(
        f"{requirements}{DOCUMENT_PATH_SEPARATOR}{stage}"
        for stage in REQUIREMENT_STAGE_FOLDER_NAMES
    )
    return (root, requirements, *stages)


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
    if not name_is_addressable(project_name):
        return InitResult(
            code=ResultCode.INVALID_INPUT,
            message=(
                f"Project Name {project_name!r} must not contain "
                f"{DOCUMENT_PATH_SEPARATOR!r}, which separates document path "
                "segments."
            ),
            project_name=project_name,
        )

    journal = _Journal()
    documents: list[DocumentNode] = []
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

        documents = _create_document_structure(workspace, project_name, journal)

        _link_documents_root(workspace, project_id, documents[0])
        journal.created.append(f"Project Documents Root -> {documents[0].id}")

        _validate_created_state(
            workspace, project_id, project_name, project_code, documents
        )
    except _StageFailed as failure:
        return _failure_result(failure, journal, project_name, project_code, documents)

    return InitResult(
        code=ResultCode.PROJECT_INITIALIZED,
        message=f"Project {project_name!r} initialized.",
        project_name=project_name,
        project_code=project_code,
        documents=tuple(node.path for node in documents),
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
    documents: list[DocumentNode],
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
            documents=tuple(node.path for node in documents),
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
            documents=tuple(node.path for node in documents),
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


def _create_document_structure(
    workspace: FiberyWorkspace, project_name: str, journal: _Journal
) -> list[DocumentNode]:
    """Create every document node, recording each one as it becomes durable."""
    created: list[DocumentNode] = []
    for path in project_document_paths(project_name):
        try:
            node = workspace.create_document(path)
        except FiberyError as error:
            raise _StageFailed(
                ResultCode.DOCUMENT_STRUCTURE_CREATE_FAILED,
                f"Could not create the document {path!r}.",
                (str(error),),
            ) from error
        created.append(node)
        journal.created.append(f"Document {path}")
    return created


def _link_documents_root(
    workspace: FiberyWorkspace, project_id: str, root: DocumentNode
) -> None:
    try:
        workspace.set_documents_root(project_id, root.id)
    except FiberyError as error:
        raise _StageFailed(
            ResultCode.FIBERY_WRITE_FAILED,
            f"Could not store the Documents Root reference to {root.path!r}.",
            (str(error),),
        ) from error


@dataclass(frozen=True)
class _CreatedState:
    """Everything section 14 validation compares against, read back from Fibery."""

    project: ProjectRecord | None
    projects_with_code: int
    documents_by_path: dict[str, DocumentNode | None]
    documents_root: DocumentNode | None


def _validate_created_state(
    workspace: FiberyWorkspace,
    project_id: str,
    project_name: str,
    project_code: str,
    documents: list[DocumentNode],
) -> None:
    """Read the created state back and fail unless it matches the request."""
    state = _read_created_state(workspace, project_id, project_code, documents)
    problems = _collect_validation_problems(
        state, project_name, project_code, documents
    )
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
    documents: list[DocumentNode],
) -> _CreatedState:
    try:
        project = workspace.read_project(project_id)
        projects_with_code = workspace.count_projects_with_code(project_code)
        documents_by_path = {
            node.path: workspace.find_document(node.path) for node in documents
        }
        reference = project.documents_root if project else None
        root = workspace.resolve_document(reference) if reference else None
    except FiberyError as error:
        raise _StageFailed(
            ResultCode.VALIDATION_FAILED,
            "Could not read the created state back from Fibery.",
            (str(error),),
        ) from error
    return _CreatedState(project, projects_with_code, documents_by_path, root)


def _collect_validation_problems(
    state: _CreatedState,
    project_name: str,
    project_code: str,
    documents: list[DocumentNode],
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
    problems.extend(_document_problems(state, documents))
    return problems


def _document_problems(
    state: _CreatedState, documents: list[DocumentNode]
) -> list[str]:
    problems: list[str] = []
    for node in documents:
        found = state.documents_by_path.get(node.path)
        if found is None:
            problems.append(f"Document {node.path!r} does not exist.")
        elif found.id != node.id:
            problems.append(
                f"Document {node.path!r} resolves to {found.id!r}, expected "
                f"{node.id!r}."
            )

    root_path = documents[0].path
    if state.documents_root is None:
        problems.append(
            f"Documents Root does not resolve to the document {root_path!r}."
        )
    elif state.documents_root.path != root_path:
        problems.append(
            f"Documents Root resolves to {state.documents_root.path!r}, "
            f"expected {root_path!r}."
        )
    return problems
