"""`sdlc project requirement add` — deterministic RAW Requirement ingest.

Implements Project-Requirement-Add-Spec-v0.3. No model is invoked anywhere in
this flow.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    FolderNode,
    ProjectRecord,
    RequirementRecord,
    RequirementWorkspace,
)
from sdlc.project_init import (
    REQUIREMENT_STAGE_FOLDER_NAMES,
    REQUIREMENTS_FOLDER_NAME,
)
from sdlc.raw_source import (
    InvalidRequirementSource,
    RawRequirementSource,
    UnsupportedRequirementsFormat,
    content_equivalent,
    parse_raw_requirement,
)
from sdlc.requirement_id import InvalidPublicId, raw_requirement_id
from sdlc.results import AddResult, AddResultCode

REQUIREMENT_TYPE_RAW = "Raw"
REQUIREMENT_INITIAL_STATE = "Draft"
INITIAL_REVISION = 1
RAW_FOLDER_NAME = "Raw"
DOCUMENT_NAME_SEPARATOR = " — "


def requirement_document_name(requirement_id: str, title: str) -> str:
    """`<Requirement ID> — <Title>`, per spec section 11."""
    return f"{requirement_id}{DOCUMENT_NAME_SEPARATOR}{title}"


class _StageFailed(Exception):
    """A stage of ingest could not complete."""

    def __init__(
        self, code: AddResultCode, message: str, causes: tuple[str, ...] = ()
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


@dataclass(frozen=True)
class _RawFolders:
    """The Project folders this command needs, resolved to real ids."""

    root: FolderNode
    requirements: FolderNode
    raw: FolderNode


def add_raw_requirement(
    workspace: RequirementWorkspace,
    project: str,
    source_text: str,
) -> AddResult:
    """Ingest one RAW requirements artifact, or report why not."""
    selector = project.strip() if project else ""
    if not selector:
        return AddResult(
            code=AddResultCode.INVALID_INPUT,
            message="A Project Code or Project Name is required.",
        )

    journal = _Journal()
    resolved: ProjectRecord | None = None
    allocated_id: str | None = None
    parsed: RawRequirementSource | None = None

    try:
        parsed = _parse_source(source_text)
        resolved = _resolve_project(workspace, selector)
        folders = _resolve_folders(workspace, resolved)

        duplicate = _find_duplicate(workspace, resolved, parsed.fingerprint)
        if duplicate is not None:
            return _already_added_result(resolved, duplicate)

        requirement = _create_requirement(workspace, resolved, parsed, journal)
        allocated_id = _assign_requirement_id(workspace, resolved, requirement, journal)
        _apply_type_and_state(workspace, requirement, journal)

        document = _create_document(
            workspace, allocated_id, parsed.title, folders.raw, requirement, journal
        )
        _write_content(workspace, document, parsed.body, journal)

        _validate(
            workspace, resolved, requirement, allocated_id, parsed, folders, document
        )
    except _StageFailed as failure:
        return _failure_result(failure, journal, resolved, allocated_id, parsed)

    return AddResult(
        code=AddResultCode.RAW_REQUIREMENT_ADDED,
        message=f"RAW requirement {allocated_id} added.",
        project_name=resolved.name,
        project_code=resolved.code,
        requirement_id=allocated_id,
        title=parsed.title,
        document_path=_document_path(resolved, allocated_id, parsed.title),
        created=tuple(journal.created),
    )


def _document_path(project: ProjectRecord, requirement_id: str, title: str) -> str:
    return (
        f"{project.name}/{REQUIREMENTS_FOLDER_NAME}/{RAW_FOLDER_NAME}/"
        f"{requirement_document_name(requirement_id, title)}"
    )


def _already_added_result(
    project: ProjectRecord, duplicate: RequirementRecord
) -> AddResult:
    return AddResult(
        code=AddResultCode.REQUIREMENT_ALREADY_ADDED,
        message=(
            f"This requirements artifact has already been added to project "
            f"{project.code}."
        ),
        project_name=project.name,
        project_code=project.code,
        requirement_id=duplicate.requirement_id,
        title=duplicate.title,
    )


def _failure_result(
    failure: _StageFailed,
    journal: _Journal,
    project: ProjectRecord | None,
    requirement_id: str | None,
    parsed: RawRequirementSource | None,
) -> AddResult:
    """Map a stage failure onto a spec result code.

    Once anything durable exists the outcome is PARTIAL_ADD and the original
    failure class is reported as the cause, except for VALIDATION_FAILED, which
    means the write sequence completed but read-back disagreed. Nothing is
    deleted either way.
    """
    common = {
        "project_name": project.name if project else None,
        "project_code": project.code if project else None,
        "requirement_id": requirement_id,
        "title": parsed.title if parsed else None,
    }
    if failure.code is AddResultCode.VALIDATION_FAILED:
        return AddResult(
            code=AddResultCode.VALIDATION_FAILED,
            message=failure.message,
            created=tuple(journal.created),
            details=failure.causes,
            **common,
        )
    if journal.has_durable_state:
        return AddResult(
            code=AddResultCode.PARTIAL_ADD,
            message=(
                f"RAW requirement {requirement_id} was partially added and left "
                "in place."
            ),
            created=tuple(journal.created),
            failed=(failure.code.value,),
            details=(failure.message, *failure.causes),
            **common,
        )
    return AddResult(
        code=failure.code,
        message=failure.message,
        details=failure.causes,
        **common,
    )


def _parse_source(source_text: str) -> RawRequirementSource:
    try:
        return parse_raw_requirement(source_text)
    except UnsupportedRequirementsFormat as error:
        raise _StageFailed(
            AddResultCode.UNSUPPORTED_REQUIREMENTS_FORMAT, str(error)
        ) from error
    except InvalidRequirementSource as error:
        raise _StageFailed(
            AddResultCode.INVALID_REQUIREMENT_SOURCE, str(error)
        ) from error


def _resolve_project(workspace: RequirementWorkspace, selector: str) -> ProjectRecord:
    """Exact Code first, then exact Name. Never guesses, never creates."""
    try:
        by_code = workspace.find_project_by_code(selector)
        if by_code is not None:
            return by_code
        by_name = workspace.find_projects_by_name(selector)
    except FiberyError as error:
        raise _StageFailed(
            AddResultCode.FIBERY_READ_FAILED,
            f"Could not look up Project {selector!r}.",
            (str(error),),
        ) from error

    if not by_name:
        raise _StageFailed(
            AddResultCode.PROJECT_NOT_FOUND,
            f"Project {selector!r} does not exist.",
            (f'Run: sdlc project init --name "{selector}"',),
        )
    if len(by_name) > 1:
        raise _StageFailed(
            AddResultCode.PROJECT_AMBIGUOUS,
            f"Project Name {selector!r} matches {len(by_name)} Projects.",
            tuple(f"{p.code} ({p.id})" for p in by_name),
        )
    return by_name[0]


def _resolve_folders(
    workspace: RequirementWorkspace, project: ProjectRecord
) -> _RawFolders:
    """Walk the real Folder tree by id, never by name alone.

    Every stage folder required by Project-Init-Spec-v0.3 section 9 must be
    present. This command never creates or repairs them.
    """
    root_id = project.documents_root_folder_id
    if not root_id:
        raise _StageFailed(
            AddResultCode.PROJECT_STRUCTURE_INVALID,
            f"Project {project.name!r} has no Documents Root Folder ID.",
        )
    try:
        root = workspace.resolve_folder(root_id)
        if root is None:
            raise _StageFailed(
                AddResultCode.PROJECT_STRUCTURE_INVALID,
                f"Documents Root Folder ID {root_id!r} does not resolve to a Folder.",
            )
        requirements = _single_child(workspace, root, REQUIREMENTS_FOLDER_NAME, project)
        stages = {
            name: _single_child(workspace, requirements, name, project)
            for name in REQUIREMENT_STAGE_FOLDER_NAMES
        }
    except FiberyError as error:
        raise _StageFailed(
            AddResultCode.FIBERY_READ_FAILED,
            f"Could not read the folder structure of Project {project.name!r}.",
            (str(error),),
        ) from error
    return _RawFolders(
        root=root, requirements=requirements, raw=stages[RAW_FOLDER_NAME]
    )


def _single_child(
    workspace: RequirementWorkspace,
    parent: FolderNode,
    name: str,
    project: ProjectRecord,
) -> FolderNode:
    """The one child folder with this name, or an invalid-structure failure.

    Fibery permits sibling Folders sharing a name. Two candidates make the
    structure ambiguous, and this command must not guess which one is real.
    """
    matches = [
        folder for folder in workspace.child_folders(parent.id) if folder.name == name
    ]
    if not matches:
        raise _StageFailed(
            AddResultCode.PROJECT_STRUCTURE_INVALID,
            f"Project {project.name!r} is missing the folder "
            f"{name!r} under {parent.name!r}.",
        )
    if len(matches) > 1:
        raise _StageFailed(
            AddResultCode.PROJECT_STRUCTURE_INVALID,
            f"Project {project.name!r} has {len(matches)} folders named {name!r} "
            f"under {parent.name!r}; the structure is ambiguous.",
            tuple(folder.id for folder in matches),
        )
    return matches[0]


def _find_duplicate(
    workspace: RequirementWorkspace, project: ProjectRecord, fingerprint: str
) -> RequirementRecord | None:
    try:
        return workspace.find_requirement_by_fingerprint(project.id, fingerprint)
    except FiberyError as error:
        raise _StageFailed(
            AddResultCode.FIBERY_READ_FAILED,
            "Could not check whether this artifact was already added.",
            (str(error),),
        ) from error


def _create_requirement(
    workspace: RequirementWorkspace,
    project: ProjectRecord,
    parsed: RawRequirementSource,
    journal: _Journal,
) -> RequirementRecord:
    """Create the entity so Fibery allocates its public id."""
    if not project.code:
        raise _StageFailed(
            AddResultCode.REQUIREMENT_ID_ALLOCATION_FAILED,
            f"Project {project.name!r} has no Code to build a Requirement ID from.",
        )
    try:
        record = workspace.create_requirement(
            project_id=project.id,
            title=parsed.title,
            revision=INITIAL_REVISION,
            fingerprint=parsed.fingerprint,
        )
    except FiberyError as error:
        raise _StageFailed(
            AddResultCode.FIBERY_WRITE_FAILED,
            f"Could not create the Requirement entity for {parsed.title!r}.",
            (str(error),),
        ) from error
    journal.created.append(f"Requirement entity {record.id}")
    if not record.public_id:
        raise _StageFailed(
            AddResultCode.REQUIREMENT_ID_ALLOCATION_FAILED,
            "Fibery allocated no public id for the created Requirement.",
        )
    return record


def _assign_requirement_id(
    workspace: RequirementWorkspace,
    project: ProjectRecord,
    requirement: RequirementRecord,
    journal: _Journal,
) -> str:
    """Derive the Requirement ID from the public id and write it.

    The entity already exists at this point, so any failure here leaves durable
    state and is reported as PARTIAL_ADD rather than a clean failure.
    """
    try:
        requirement_id = raw_requirement_id(project.code or "", requirement.public_id)
    except InvalidPublicId as error:
        raise _StageFailed(
            AddResultCode.REQUIREMENT_ID_ALLOCATION_FAILED, str(error)
        ) from error
    try:
        workspace.set_requirement_id(requirement.id, requirement_id)
    except FiberyError as error:
        raise _StageFailed(
            AddResultCode.FIBERY_WRITE_FAILED,
            f"Could not write Requirement ID {requirement_id} onto the entity.",
            (str(error),),
        ) from error
    journal.created.append(f"Requirement ID {requirement_id}")
    return requirement_id


def _apply_type_and_state(
    workspace: RequirementWorkspace, requirement: RequirementRecord, journal: _Journal
) -> None:
    try:
        workspace.set_requirement_type(requirement.id, REQUIREMENT_TYPE_RAW)
        journal.created.append(f"Requirement Type = {REQUIREMENT_TYPE_RAW}")
        workspace.set_requirement_state(requirement.id, REQUIREMENT_INITIAL_STATE)
        journal.created.append(f"Requirement State = {REQUIREMENT_INITIAL_STATE}")
    except FiberyError as error:
        raise _StageFailed(
            AddResultCode.FIBERY_WRITE_FAILED,
            "Could not set the Requirement Type and State.",
            (str(error),),
        ) from error


def _create_document(
    workspace: RequirementWorkspace,
    requirement_id: str,
    title: str,
    raw_folder: FolderNode,
    requirement: RequirementRecord,
    journal: _Journal,
) -> DocumentNode:
    name = requirement_document_name(requirement_id, title)
    try:
        document = workspace.create_requirement_document(
            name=name,
            folder_id=raw_folder.id,
            requirement_public_id=requirement.public_id,
        )
    except FiberyError as error:
        raise _StageFailed(
            AddResultCode.DOCUMENT_CREATE_FAILED,
            f"Could not create the Root Document {name!r}.",
            (str(error),),
        ) from error
    journal.created.append(f"Root Document {name} ({document.id})")
    if document.entity_public_id != requirement.public_id:
        raise _StageFailed(
            AddResultCode.DOCUMENT_ATTACHMENT_FAILED,
            f"Root Document {name!r} is not attached to Requirement {requirement_id}.",
            (
                (
                    f"attached to public id {document.entity_public_id!r}, "
                    f"expected {requirement.public_id!r}"
                ),
            ),
        )
    return document


def _write_content(
    workspace: RequirementWorkspace,
    document: DocumentNode,
    body: str,
    journal: _Journal,
) -> None:
    if not document.secret:
        raise _StageFailed(
            AddResultCode.CONTENT_WRITE_FAILED,
            f"Document {document.name!r} exposes no content secret to write to.",
        )
    try:
        workspace.write_document_content(document.secret, body)
    except FiberyError as error:
        raise _StageFailed(
            AddResultCode.CONTENT_WRITE_FAILED,
            f"Could not write the content of {document.name!r}.",
            (str(error),),
        ) from error
    journal.created.append("Root Document content")


@dataclass(frozen=True)
class _CreatedState:
    """Everything section 19 validation compares against, read from Fibery."""

    requirement: RequirementRecord | None
    document: DocumentNode | None
    attached: list[DocumentNode]
    content: str


def _validate(
    workspace: RequirementWorkspace,
    project: ProjectRecord,
    requirement: RequirementRecord,
    requirement_id: str,
    parsed: RawRequirementSource,
    folders: _RawFolders,
    document: DocumentNode,
) -> None:
    """Read the created state back and fail unless it matches the request."""
    try:
        state = _CreatedState(
            requirement=workspace.read_requirement(requirement.id),
            document=workspace.resolve_document(document.id),
            attached=workspace.documents_attached_to_requirement(requirement.public_id),
            content=workspace.read_document_content(document.secret or ""),
        )
    except FiberyError as error:
        raise _StageFailed(
            AddResultCode.VALIDATION_FAILED,
            "Could not read the created state back from Fibery.",
            (str(error),),
        ) from error

    problems = _validation_problems(
        state, project, requirement_id, parsed, folders, document
    )
    if problems:
        raise _StageFailed(
            AddResultCode.VALIDATION_FAILED,
            f"Post-write validation failed for {requirement_id}.",
            tuple(problems),
        )


def _validation_problems(
    state: _CreatedState,
    project: ProjectRecord,
    requirement_id: str,
    parsed: RawRequirementSource,
    folders: _RawFolders,
    document: DocumentNode,
) -> list[str]:
    record = state.requirement
    if record is None:
        return ["Requirement entity could not be read back."]

    problems: list[str] = []
    if record.requirement_id != requirement_id:
        problems.append(
            f"Requirement ID is {record.requirement_id!r}, expected {requirement_id!r}."
        )
    if record.title != parsed.title:
        problems.append(f"Title is {record.title!r}, expected {parsed.title!r}.")
    if record.type_name != REQUIREMENT_TYPE_RAW:
        problems.append(
            f"Type is {record.type_name!r}, expected {REQUIREMENT_TYPE_RAW!r}."
        )
    if record.state != REQUIREMENT_INITIAL_STATE:
        problems.append(
            f"State is {record.state!r}, expected {REQUIREMENT_INITIAL_STATE!r}."
        )
    if record.revision != INITIAL_REVISION:
        problems.append(
            f"Revision is {record.revision!r}, expected {INITIAL_REVISION}."
        )
    if record.project_id != project.id:
        problems.append(
            f"Project relation is {record.project_id!r}, expected {project.id!r}."
        )
    if record.source_fingerprint != parsed.fingerprint:
        problems.append("Source Fingerprint does not match the ingested artifact.")
    problems.extend(_document_problems(state, parsed, folders, document))
    return problems


def _document_problems(
    state: _CreatedState,
    parsed: RawRequirementSource,
    folders: _RawFolders,
    document: DocumentNode,
) -> list[str]:
    problems: list[str] = []
    found = state.document
    if found is None:
        problems.append(f"Root Document {document.id!r} does not exist.")
    else:
        if found.name != document.name:
            problems.append(
                f"Root Document is named {found.name!r}, expected {document.name!r}."
            )
        if found.folder_id != folders.raw.id:
            problems.append(
                f"Root Document is in folder {found.folder_id!r}, expected the "
                f"Requirements/Raw folder {folders.raw.id!r}."
            )

    attached_ids = [node.id for node in state.attached]
    if attached_ids != [document.id]:
        problems.append(
            f"Requirement.Documents holds {attached_ids!r}, expected exactly "
            f"[{document.id!r}]."
        )
    if not content_equivalent(state.content, parsed.body):
        problems.append("Root Document content does not match the source artifact.")
    return problems
