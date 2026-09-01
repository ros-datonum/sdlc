"""RAW Requirement Processor — the first SDLC capability that invokes a model.

The model reasons once; everything durable is deterministic. Its validated
output is persisted as a Processing Result child Document *before* any candidate
entity exists, and candidate entities take deterministic ids derived from that
result. A retry therefore never asks the model again and never duplicates a
candidate: it reads the Processing Result and completes only the missing steps.

The model never touches Fibery, never chooses an identifier, and never sees a
uuid.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    ProjectRecord,
    RawProcessorWorkspace,
    RequirementRecord,
)
from sdlc.model_runtime import ModelRuntime, ModelRuntimeError
from sdlc.processing_result import (
    InvalidProcessingResult,
    KeyedCandidate,
    ProcessingResult,
    build_processing_result,
    parse_processing_result,
    processing_result_name,
    render_processing_result,
)
from sdlc.project_init import REQUIREMENT_STAGE_FOLDER_NAMES, REQUIREMENTS_FOLDER_NAME
from sdlc.raw_processing import InvalidModelOutput, parse_model_output
from sdlc.raw_prompt import build_prompt
from sdlc.raw_source import content_equivalent
from sdlc.requirement_id import namespaced_requirement_id
from sdlc.results import ProcessResult, ProcessResultCode

RAW_TYPE = "Raw"
STANDARD_TYPE = "Standard"
PROCESS_STATE = "Process"
REVIEW_STATE = "Review"
DRAFT_STATE = "Draft"
DRAFT_FOLDER_NAME = "Draft"
INITIAL_REVISION = 1


class _StageFailed(Exception):
    """A stage of processing could not complete."""

    def __init__(
        self, code: ProcessResultCode, message: str, causes: tuple[str, ...] = ()
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.causes = causes


@dataclass
class _Journal:
    """Durable Fibery objects this run created."""

    created: list[str] = field(default_factory=list)

    @property
    def has_durable_state(self) -> bool:
        return bool(self.created)


@dataclass(frozen=True)
class _Context:
    """Everything read from Fibery before the model is consulted."""

    raw: RequirementRecord
    project: ProjectRecord
    root_document: DocumentNode
    draft_folder_id: str
    raw_body: str
    existing_standards: tuple[RequirementRecord, ...]


def process_raw_requirement(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    raw_entity_id: str,
) -> ProcessResult:
    """Decompose one RAW Requirement into Standard Draft candidates."""
    journal = _Journal()
    model_invoked = False
    try:
        context = _load_context(workspace, raw_entity_id)
        existing = _find_processing_result(workspace, context)

        if existing is None:
            result, model_invoked = _produce_processing_result(
                workspace, model, context, journal
            )
        else:
            result = existing

        applied = _apply_candidates(workspace, context, result, journal)
        _transition_to_review(workspace, context, journal)
    except _StageFailed as failure:
        return _failure_result(failure, journal, model_invoked)

    return ProcessResult(
        code=ProcessResultCode.RAW_REQUIREMENT_PROCESSED,
        message=(
            f"{context.raw.requirement_id} processed into {len(applied)} "
            "Standard candidate(s)."
        ),
        raw_requirement_id=context.raw.requirement_id,
        candidates=applied,
        findings=tuple(
            f"{f.kind.value} {f.requirement_id}: {f.detail}" for f in result.findings
        ),
        no_candidate_reason=result.no_candidate_reason,
        model_invoked=model_invoked,
        created=tuple(journal.created),
    )


def _failure_result(
    failure: _StageFailed, journal: _Journal, model_invoked: bool
) -> ProcessResult:
    """Map a stage failure onto a result code.

    Once anything durable exists the run is PARTIAL_PROCESSING: the RAW stays in
    Process and a retry resumes from the Processing Result. Nothing is deleted.
    """
    if journal.has_durable_state and failure.code not in {
        ProcessResultCode.PROCESSING_STATE_CONFLICT,
        ProcessResultCode.INVALID_PROCESSING_RESULT,
    }:
        return ProcessResult(
            code=ProcessResultCode.PARTIAL_PROCESSING,
            message=(
                "Processing did not complete; the RAW Requirement stays in "
                "Process and a retry will resume."
            ),
            model_invoked=model_invoked,
            created=tuple(journal.created),
            details=(failure.code.value, failure.message, *failure.causes),
        )
    return ProcessResult(
        code=failure.code,
        message=failure.message,
        model_invoked=model_invoked,
        created=tuple(journal.created),
        details=failure.causes,
    )


# -- context ----------------------------------------------------------------


def _load_context(workspace: RawProcessorWorkspace, raw_entity_id: str) -> _Context:
    """Read the RAW Requirement and everything needed to process it."""
    try:
        raw = workspace.read_requirement(raw_entity_id)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            f"Could not read Requirement {raw_entity_id}.",
            (str(error),),
        ) from error
    if raw is None:
        raise _StageFailed(
            ProcessResultCode.REQUIREMENT_NOT_FOUND,
            f"No Requirement with id {raw_entity_id}.",
        )
    if raw.type_name != RAW_TYPE:
        raise _StageFailed(
            ProcessResultCode.NOT_A_RAW_REQUIREMENT,
            f"{raw.requirement_id} has Type {raw.type_name!r}; the processor "
            f"handles only {RAW_TYPE!r}.",
        )
    if raw.state != PROCESS_STATE:
        raise _StageFailed(
            ProcessResultCode.REQUIREMENT_NOT_IN_PROCESS,
            f"{raw.requirement_id} is in State {raw.state!r}; the processor "
            f"handles only {PROCESS_STATE!r}.",
        )

    try:
        project = workspace.read_project(raw.project_id or "")
        documents = workspace.documents_attached_to_requirement(raw.public_id)
        standards = workspace.standard_requirements_in_project(raw.project_id or "")
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            f"Could not read the context of {raw.requirement_id}.",
            (str(error),),
        ) from error
    if project is None:
        raise _StageFailed(
            ProcessResultCode.PROJECT_STRUCTURE_INVALID,
            f"{raw.requirement_id} has no resolvable Project.",
        )
    if len(documents) != 1:
        raise _StageFailed(
            ProcessResultCode.PROJECT_STRUCTURE_INVALID,
            f"{raw.requirement_id} has {len(documents)} attached Documents; "
            "exactly one Root Document is required.",
        )

    root = documents[0]
    body = _read_document_tree(workspace, root)
    draft_folder = _draft_folder_id(workspace, project)
    return _Context(
        raw=raw,
        project=project,
        root_document=root,
        draft_folder_id=draft_folder,
        raw_body=body,
        existing_standards=tuple(standards),
    )


def _read_document_tree(workspace: RawProcessorWorkspace, root: DocumentNode) -> str:
    """Read the Root Document and every nested child, depth first.

    The Processing Result child is skipped: it is this processor's own output,
    not requirement source material.
    """
    sections: list[str] = []

    def visit(node: DocumentNode, depth: int) -> None:
        if node.name.endswith(processing_result_name("").strip()):
            return
        content = workspace.read_document_content(node.secret or "")
        sections.append(f"<!-- document: {node.name} -->\n{content}")
        for child in workspace.child_documents(node.id):
            visit(child, depth + 1)

    try:
        visit(root, 0)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            "Could not read the RAW Requirement document tree.",
            (str(error),),
        ) from error
    return "\n\n".join(sections)


def _draft_folder_id(workspace: RawProcessorWorkspace, project: ProjectRecord) -> str:
    """Resolve `<Project>/Requirements/Draft` by real Folder ids."""
    root_id = project.documents_root_folder_id
    if not root_id:
        raise _StageFailed(
            ProcessResultCode.PROJECT_STRUCTURE_INVALID,
            f"Project {project.name!r} has no Documents Root Folder ID.",
        )
    try:
        root = workspace.resolve_folder(root_id)
        if root is None:
            raise _StageFailed(
                ProcessResultCode.PROJECT_STRUCTURE_INVALID,
                f"Documents Root Folder ID {root_id!r} does not resolve.",
            )
        requirements = _single_child(workspace, root.id, REQUIREMENTS_FOLDER_NAME)
        for stage in REQUIREMENT_STAGE_FOLDER_NAMES:
            found = _single_child(workspace, requirements, stage)
            if stage == DRAFT_FOLDER_NAME:
                draft = found
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            "Could not read the Project folder structure.",
            (str(error),),
        ) from error
    return draft


def _single_child(workspace: RawProcessorWorkspace, parent_id: str, name: str) -> str:
    matches = [f for f in workspace.child_folders(parent_id) if f.name == name]
    if len(matches) != 1:
        raise _StageFailed(
            ProcessResultCode.PROJECT_STRUCTURE_INVALID,
            f"Expected exactly one {name!r} folder, found {len(matches)}.",
        )
    return matches[0].id


# -- processing result ------------------------------------------------------


def _find_processing_result(
    workspace: RawProcessorWorkspace, context: _Context
) -> ProcessingResult | None:
    """Resolve the existing Processing Result, if this RAW has one.

    This is the idempotency boundary: a Processing Result means the model has
    already run and must not run again.
    """
    expected = processing_result_name(context.raw.requirement_id or "")
    try:
        children = workspace.child_documents(context.root_document.id)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            "Could not list the RAW Requirement's child Documents.",
            (str(error),),
        ) from error

    matches = [child for child in children if child.name == expected]
    if not matches:
        return None
    if len(matches) > 1:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"{context.raw.requirement_id} has {len(matches)} Processing Result "
            "documents. Refusing to guess which one is authoritative.",
            tuple(node.id for node in matches),
        )

    node = matches[0]
    try:
        content = workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            "Could not read the Processing Result document.",
            (str(error),),
        ) from error
    try:
        result = parse_processing_result(content)
    except InvalidProcessingResult as error:
        raise _StageFailed(
            ProcessResultCode.INVALID_PROCESSING_RESULT,
            f"The Processing Result of {context.raw.requirement_id} cannot be "
            "resumed from.",
            (str(error),),
        ) from error
    if result.raw_requirement_id != context.raw.requirement_id:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"The Processing Result names {result.raw_requirement_id!r} but is "
            f"attached to {context.raw.requirement_id!r}.",
        )
    return result


def _produce_processing_result(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    context: _Context,
    journal: _Journal,
) -> tuple[ProcessingResult, bool]:
    """Invoke the model once and persist the validated decomposition.

    Persisting comes before any candidate entity exists, so a retry can always
    reconstruct candidate identity without the model.
    """
    prompt, model_context = build_prompt(
        raw_requirement_id=context.raw.requirement_id or "",
        raw_title=context.raw.title or "",
        project_name=context.project.name,
        raw_body=context.raw_body,
        existing_standards=context.existing_standards,
    )
    try:
        response = model.run(prompt, model_context)
    except ModelRuntimeError as error:
        raise _StageFailed(
            ProcessResultCode.MODEL_RUNTIME_FAILED,
            "The configured local model runtime could not run the decomposition.",
            (str(error),),
        ) from error

    try:
        decomposition = parse_model_output(response.text)
    except InvalidModelOutput as error:
        raise _StageFailed(
            ProcessResultCode.INVALID_MODEL_OUTPUT,
            "The model's response does not satisfy the decomposition contract.",
            (str(error),),
        ) from error

    result = build_processing_result(context.raw.requirement_id or "", decomposition)
    _persist_processing_result(workspace, context, result, journal)
    return result, True


def _persist_processing_result(
    workspace: RawProcessorWorkspace,
    context: _Context,
    result: ProcessingResult,
    journal: _Journal,
) -> None:
    """Write the artifact and read it back before trusting it."""
    name = processing_result_name(context.raw.requirement_id or "")
    try:
        node = workspace.create_child_document(name, context.root_document.id)
        if not node.secret:
            raise _StageFailed(
                ProcessResultCode.PROCESSING_RESULT_WRITE_FAILED,
                "The Processing Result document exposes no content secret.",
            )
        workspace.write_document_content(node.secret, render_processing_result(result))
        stored = workspace.read_document_content(node.secret)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_RESULT_WRITE_FAILED,
            "Could not persist the Processing Result.",
            (str(error),),
        ) from error

    try:
        parse_processing_result(stored)
    except InvalidProcessingResult as error:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_RESULT_WRITE_FAILED,
            "The persisted Processing Result does not read back as valid.",
            (str(error),),
        ) from error
    journal.created.append(f"Processing Result {name} ({node.id})")


# -- candidate application --------------------------------------------------


def _apply_candidates(
    workspace: RawProcessorWorkspace,
    context: _Context,
    result: ProcessingResult,
    journal: _Journal,
) -> tuple[str, ...]:
    """Create or resume every candidate, one verifiable step at a time."""
    applied: list[str] = []
    for keyed in result.candidates:
        applied.append(_apply_candidate(workspace, context, keyed, journal))
    return tuple(applied)


def _apply_candidate(
    workspace: RawProcessorWorkspace,
    context: _Context,
    keyed: KeyedCandidate,
    journal: _Journal,
) -> str:
    """Bring one candidate to a complete state, skipping finished steps."""
    entity_id = keyed.fibery_id(context.raw.id)
    record = _ensure_entity(workspace, context, keyed, entity_id, journal)
    requirement_id = _ensure_requirement_id(workspace, context, keyed, record, journal)
    _ensure_type_and_state(workspace, record, journal)
    _ensure_derived_from(workspace, context, record, journal)
    document = _ensure_root_document(
        workspace, context, keyed, requirement_id, record, journal
    )
    _ensure_content(workspace, keyed, requirement_id, document, journal)
    _validate_candidate(workspace, context, keyed, requirement_id, record, document)
    return requirement_id


def _ensure_entity(
    workspace: RawProcessorWorkspace,
    context: _Context,
    keyed: KeyedCandidate,
    entity_id: str,
    journal: _Journal,
) -> RequirementRecord:
    """Create the candidate entity at its deterministic id, or adopt it.

    An entity already at that id is this candidate from an earlier attempt,
    because the id derives from the RAW uuid and the candidate key. It is still
    checked before adoption rather than reused blindly.
    """
    try:
        existing = workspace.read_requirement(entity_id)
        if existing is not None:
            _check_adoptable(existing, context, keyed)
            return existing
        created = workspace.create_requirement_with_id(
            entity_id=entity_id,
            project_id=context.project.id,
            title=keyed.candidate.title,
            revision=INITIAL_REVISION,
            category=keyed.candidate.category.value,
        )
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_WRITE_FAILED,
            f"Could not create candidate {keyed.key}.",
            (str(error),),
        ) from error
    journal.created.append(f"Standard candidate {keyed.key} ({entity_id})")
    return created


def _check_adoptable(
    existing: RequirementRecord, context: _Context, keyed: KeyedCandidate
) -> None:
    """Refuse to reuse an entity that is not this candidate."""
    if existing.project_id and existing.project_id != context.project.id:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"Candidate {keyed.key} resolves to an entity in another Project.",
        )
    if existing.title and existing.title != keyed.candidate.title:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"Candidate {keyed.key} resolves to an entity titled "
            f"{existing.title!r}, expected {keyed.candidate.title!r}.",
        )


def _ensure_requirement_id(
    workspace: RawProcessorWorkspace,
    context: _Context,
    keyed: KeyedCandidate,
    record: RequirementRecord,
    journal: _Journal,
) -> str:
    """Derive the Requirement ID from the Fibery public id and write it once."""
    expected = namespaced_requirement_id(
        context.project.code or "",
        keyed.candidate.category.id_infix,
        record.public_id,
    )
    if record.requirement_id == expected:
        return expected
    if record.requirement_id:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"Candidate {keyed.key} already carries Requirement ID "
            f"{record.requirement_id!r}, expected {expected!r}.",
        )
    try:
        workspace.set_requirement_id(record.id, expected)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_WRITE_FAILED,
            f"Could not write Requirement ID {expected}.",
            (str(error),),
        ) from error
    journal.created.append(f"Requirement ID {expected}")
    return expected


def _ensure_type_and_state(
    workspace: RawProcessorWorkspace, record: RequirementRecord, journal: _Journal
) -> None:
    try:
        if record.type_name != STANDARD_TYPE:
            workspace.set_requirement_type(record.id, STANDARD_TYPE)
            journal.created.append(f"Type = {STANDARD_TYPE} ({record.id})")
        if record.state != DRAFT_STATE:
            workspace.set_requirement_state(record.id, DRAFT_STATE)
            journal.created.append(f"State = {DRAFT_STATE} ({record.id})")
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_WRITE_FAILED,
            "Could not set candidate Type and State.",
            (str(error),),
        ) from error


def _ensure_derived_from(
    workspace: RawProcessorWorkspace,
    context: _Context,
    record: RequirementRecord,
    journal: _Journal,
) -> None:
    """Link the candidate to its RAW; Fibery populates Produces in return."""
    try:
        workspace.add_derived_from(record.id, context.raw.id)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_WRITE_FAILED,
            f"Could not link {record.id} to its RAW Requirement.",
            (str(error),),
        ) from error
    journal.created.append(f"Derived From -> {context.raw.requirement_id}")


def _ensure_root_document(
    workspace: RawProcessorWorkspace,
    context: _Context,
    keyed: KeyedCandidate,
    requirement_id: str,
    record: RequirementRecord,
    journal: _Journal,
) -> DocumentNode:
    """Create the Root Document under Requirements/Draft, or reuse it."""
    name = keyed.candidate.document_name(requirement_id)
    try:
        attached = workspace.documents_attached_to_requirement(record.public_id)
        if len(attached) > 1:
            raise _StageFailed(
                ProcessResultCode.PROCESSING_STATE_CONFLICT,
                f"{requirement_id} has {len(attached)} attached Documents; "
                "exactly one Root Document is required.",
            )
        if attached:
            return attached[0]
        document = workspace.create_requirement_document(
            name=name,
            folder_id=context.draft_folder_id,
            requirement_public_id=record.public_id,
        )
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.DOCUMENT_CREATE_FAILED,
            f"Could not create the Root Document for {requirement_id}.",
            (str(error),),
        ) from error
    journal.created.append(f"Root Document {name} ({document.id})")
    return document


def _ensure_content(
    workspace: RawProcessorWorkspace,
    keyed: KeyedCandidate,
    requirement_id: str,
    document: DocumentNode,
    journal: _Journal,
) -> None:
    """Write the approved document, rendered from the persisted result."""
    if not document.secret:
        raise _StageFailed(
            ProcessResultCode.CONTENT_WRITE_FAILED,
            f"The Root Document of {requirement_id} exposes no content secret.",
        )
    body = keyed.candidate.document(requirement_id)
    try:
        workspace.write_document_content(document.secret, body)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.CONTENT_WRITE_FAILED,
            f"Could not write the Root Document of {requirement_id}.",
            (str(error),),
        ) from error
    journal.created.append(f"Root Document content {requirement_id}")


def _validate_candidate(
    workspace: RawProcessorWorkspace,
    context: _Context,
    keyed: KeyedCandidate,
    requirement_id: str,
    record: RequirementRecord,
    document: DocumentNode,
) -> None:
    """Read the candidate back and fail unless every step landed."""
    try:
        stored = workspace.read_requirement(record.id)
        found = workspace.resolve_document(document.id)
        attached = workspace.documents_attached_to_requirement(record.public_id)
        content = workspace.read_document_content(document.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.VALIDATION_FAILED,
            f"Could not read {requirement_id} back from Fibery.",
            (str(error),),
        ) from error

    problems: list[str] = []
    if stored is None:
        problems.append("the Requirement could not be read back")
    else:
        if stored.requirement_id != requirement_id:
            problems.append(f"Requirement ID is {stored.requirement_id!r}")
        if stored.type_name != STANDARD_TYPE:
            problems.append(f"Type is {stored.type_name!r}")
        if stored.state != DRAFT_STATE:
            problems.append(f"State is {stored.state!r}")
        if stored.revision != INITIAL_REVISION:
            problems.append(f"Revision is {stored.revision!r}")
        if stored.project_id != context.project.id:
            problems.append("the Project relation is wrong")
    if found is None:
        problems.append("the Root Document does not exist")
    elif found.folder_id != context.draft_folder_id:
        problems.append("the Root Document is not in Requirements/Draft")
    if [node.id for node in attached] != [document.id]:
        problems.append("Requirement.Documents does not hold exactly this Document")
    # Fibery re-serializes stored Markdown (constraint 11): "-" bullets read
    # back as "*". Comparing the full rendered document canonically is what the
    # frozen `project requirement add` already does; a substring check would
    # reject ordinary bullet lists forever, because a retry rewrites the same
    # content and fails identically.
    if not content_equivalent(content, keyed.candidate.document(requirement_id)):
        problems.append("the Root Document content does not match the candidate")

    if problems:
        raise _StageFailed(
            ProcessResultCode.VALIDATION_FAILED,
            f"Post-write validation failed for {requirement_id}.",
            tuple(problems),
        )


def _transition_to_review(
    workspace: RawProcessorWorkspace, context: _Context, journal: _Journal
) -> None:
    """Move the RAW to Review, only once every candidate is complete."""
    try:
        workspace.set_requirement_state(context.raw.id, REVIEW_STATE)
        stored = workspace.read_requirement(context.raw.id)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_WRITE_FAILED,
            f"Could not move {context.raw.requirement_id} to {REVIEW_STATE}.",
            (str(error),),
        ) from error

    # A write that returns success but does not apply would otherwise be
    # reported as a completed run while the RAW never left Process.
    if stored is None or stored.state != REVIEW_STATE:
        raise _StageFailed(
            ProcessResultCode.VALIDATION_FAILED,
            f"{context.raw.requirement_id} is still in State "
            f"{stored.state!r} after the transition to {REVIEW_STATE}."
            if stored
            else f"{context.raw.requirement_id} could not be read back.",
        )
    journal.created.append(f"RAW State = {REVIEW_STATE}")
