"""RAW Requirement Processor — the first SDLC capability that invokes a model.

The model reasons once; everything durable is deterministic. Its validated
output is persisted as a Processing Result child Document *before* any candidate
entity exists, and candidate entities take deterministic ids derived from that
result. A retry therefore never asks the model again and never duplicates a
candidate: it reads the Processing Result and completes only the missing steps.

The model never touches Fibery, never chooses an identifier, and never sees a
uuid.

A retry owns only what it left unfinished. Every candidate is inspected, read
only, before the first write of the run: a candidate that has moved past the
processor-owned initial ``Draft`` state, or whose Root Document a human has
already changed, is a processing-state conflict, never something to demote or
overwrite. That inspection covers all candidates first, so an advanced later
candidate cannot leave an earlier one half-rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sdlc.comparison_context import (
    ComparisonContext,
    ComparisonContextError,
    assemble_comparison_context,
    require_input_within_budget,
)
from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    ProjectRecord,
    RawProcessorWorkspace,
    RequirementRecord,
)
from sdlc.model_runtime import ModelRuntime, ModelRuntimeError
from sdlc.normative_tree import classify_artifact_name
from sdlc.processing_result import (
    InvalidProcessingResult,
    KeyedCandidate,
    ProcessingResult,
    build_processing_result,
    parse_processing_result,
    processing_result_name,
    render_processing_result,
)
from sdlc.raw_execution_guard import RawGuardUnavailable, RawProcessingBusy, hold
from sdlc.raw_processing import InvalidModelOutput, parse_model_output
from sdlc.raw_prompt import build_prompt
from sdlc.raw_source import content_equivalent
from sdlc.requirement_id import namespaced_requirement_id
from sdlc.result_shell import (
    RECOVERY_OPTION,
    document_label,
    eligibility_drift,
    is_empty_body,
    recovery_hint,
)
from sdlc.results import ProcessResult, ProcessResultCode

RAW_TYPE = "Raw"
STANDARD_TYPE = "Standard"
PROCESS_STATE = "Process"
REVIEW_STATE = "Review"
DRAFT_STATE = "Draft"
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
    """Durable Fibery objects this run created, and whether the model was asked."""

    created: list[str] = field(default_factory=list)
    model_invoked: bool = False

    @property
    def has_durable_state(self) -> bool:
        return bool(self.created)


@dataclass(frozen=True)
class _Context:
    """Everything read from Fibery before the model is consulted."""

    raw: RequirementRecord
    project: ProjectRecord
    root_document: DocumentNode
    raw_body: str
    existing_standards: tuple[RequirementRecord, ...]


def process_raw_requirement(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    raw_entity_id: str,
    recover_empty_result: str | None = None,
) -> ProcessResult:
    """Decompose one RAW Requirement into Standard Draft candidates.

    `recover_empty_result` names one Processing Result Document whose body was
    never stored after a failed persistence. It is explicit permission to run
    the model again and complete that exact Document in place; it never
    creates a second artifact and never overwrites a non-empty one.
    """
    # Audit A10: one RAW invocation at a time on this host. The lock is taken
    # before any read and held through model execution, persistence, candidate
    # application and the final transition; a competitor returns busy at once.
    try:
        with hold(workspace.lock_scope, raw_entity_id):
            return _process_held(workspace, model, raw_entity_id, recover_empty_result)
    except RawProcessingBusy as busy:
        return ProcessResult(
            code=ProcessResultCode.RAW_PROCESSING_IN_PROGRESS,
            message=f"{raw_entity_id}: {busy}",
        )
    except RawGuardUnavailable as unavailable:
        return ProcessResult(
            code=ProcessResultCode.RAW_PROCESSING_GUARD_UNAVAILABLE,
            message=(
                f"{raw_entity_id}: {unavailable} RAW processing does not run "
                "unguarded; nothing was read or written."
            ),
        )


def _process_held(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    raw_entity_id: str,
    recover_empty_result: str | None,
) -> ProcessResult:
    """The complete invocation, executed while the RAW's lock is held."""
    journal = _Journal()
    try:
        context = _load_context(workspace, raw_entity_id)
        existing, shell = _find_processing_result(
            workspace, context, recover_empty_result
        )

        if shell is not None:
            result = _recover_processing_result(
                workspace, model, context, shell, journal
            )
        elif existing is None:
            result = _produce_processing_result(workspace, model, context, journal)
        else:
            result = existing

        applied = _apply_candidates(workspace, context, result, journal)
        _transition_to_review(workspace, context, journal)
    except _StageFailed as failure:
        return _failure_result(failure, journal)

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
        model_invoked=journal.model_invoked,
        created=tuple(journal.created),
    )


def _failure_result(failure: _StageFailed, journal: _Journal) -> ProcessResult:
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
                "Processing did not complete. What this run made durable is "
                "listed below and left in place; the details say what a retry "
                "can do."
            ),
            model_invoked=journal.model_invoked,
            created=tuple(journal.created),
            details=(failure.code.value, failure.message, *failure.causes),
        )
    return ProcessResult(
        code=failure.code,
        message=failure.message,
        model_invoked=journal.model_invoked,
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
    body = _read_document_tree(workspace, raw, root)
    return _Context(
        raw=raw,
        project=project,
        root_document=root,
        raw_body=body,
        existing_standards=tuple(standards),
    )


def _read_document_tree(
    workspace: RawProcessorWorkspace, raw: RequirementRecord, root: DocumentNode
) -> str:
    """Read the Root Document and every nested child, depth first.

    This RAW's own Processing Result is skipped by the shared artifact
    classifier (name, owning Requirement ID, direct child of the Root), not
    by a name suffix; any other artifact name in the tree is refused rather
    than read as source. RAW binds no tree manifest; that contract belongs to
    Standard Requirements.
    """
    sections: list[str] = []

    def admit(child: DocumentNode, parent: DocumentNode) -> bool:
        classified = classify_artifact_name(child.name)
        if classified is None:
            return True
        owner, kind = classified
        if owner == raw.requirement_id and parent.id == root.id:
            return False
        raise _StageFailed(
            ProcessResultCode.NORMATIVE_TREE_INVALID,
            f"Document {child.name!r} ({child.id}) carries the {kind} artifact "
            f"name of {owner!r} under {parent.name!r} in the tree of "
            f"{raw.requirement_id}; unsupported placement.",
            (child.id,),
        )

    def visit(node: DocumentNode) -> None:
        content = workspace.read_document_content(node.secret or "")
        sections.append(f"<!-- document: {node.name} -->\n{content}")
        for child in workspace.child_documents(node.id):
            if admit(child, node):
                visit(child)

    try:
        visit(root)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            "Could not read the RAW Requirement document tree.",
            (str(error),),
        ) from error
    return "\n\n".join(sections)


# -- processing result ------------------------------------------------------


def _find_processing_result(
    workspace: RawProcessorWorkspace, context: _Context, recovering: str | None
) -> tuple[ProcessingResult | None, DocumentNode | None]:
    """Resolve the existing Processing Result, if this RAW has one.

    This is the idempotency boundary: a Processing Result means the model has
    already run and must not run again. The one exception is an empty shell
    the operator named for recovery: it is returned as the second element and
    the model may run again to fill it.
    """
    node = _processing_result_node(workspace, context)
    if node is None:
        if recovering is not None:
            raise _StageFailed(
                ProcessResultCode.PROCESSING_STATE_CONFLICT,
                f"No Processing Result Document {recovering!r} exists under the "
                f"Root Document of {context.raw.requirement_id}.",
            )
        return None, None
    content = _read_result_body(workspace, node)
    if recovering is not None:
        _check_recoverable(workspace, context, node, content, recovering)
        return None, node

    try:
        result = parse_processing_result(content)
    except InvalidProcessingResult as error:
        if is_empty_body(content):
            raise _StageFailed(
                ProcessResultCode.INVALID_PROCESSING_RESULT,
                f"Processing Result Document {document_label(node)} of "
                f"{context.raw.requirement_id} is empty. {recovery_hint(node)}",
            ) from error
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
    return result, None


def _processing_result_node(
    workspace: RawProcessorWorkspace, context: _Context
) -> DocumentNode | None:
    """The single Processing Result child by name, or None; two is a conflict."""
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
    if len(matches) > 1:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"{context.raw.requirement_id} has {len(matches)} Processing Result "
            "documents. Refusing to guess which one is authoritative.",
            tuple(node.id for node in matches),
        )
    return matches[0] if matches else None


def _read_result_body(workspace: RawProcessorWorkspace, node: DocumentNode) -> str:
    try:
        return workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            f"Could not read Processing Result Document {document_label(node)}.",
            (str(error),),
        ) from error


def _check_recoverable(
    workspace: RawProcessorWorkspace,
    context: _Context,
    node: DocumentNode,
    content: str,
    recovering: str,
) -> None:
    """Fail closed: only the named, empty, unconsumed shell may be filled."""
    if node.id != recovering:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"{recovering!r} is not the Processing Result Document of "
            f"{context.raw.requirement_id}; that is {document_label(node)}.",
        )
    if not node.secret:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_RESULT_WRITE_FAILED,
            f"Processing Result Document {document_label(node)} exposes no "
            "content secret; it cannot be completed in place.",
        )
    if not is_empty_body(content):
        try:
            parse_processing_result(content)
        except InvalidProcessingResult as error:
            raise _StageFailed(
                ProcessResultCode.INVALID_PROCESSING_RESULT,
                f"Processing Result Document {document_label(node)} is not empty "
                "and does not parse; it cannot be recovered over.",
                (str(error),),
            ) from error
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"Processing Result Document {document_label(node)} already holds a "
            f"valid result. Run the ordinary operation without {RECOVERY_OPTION}.",
        )
    produced = _candidates_derived_from(workspace, context)
    if produced:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"{context.raw.requirement_id} already produced Standard candidates "
            "although its Processing Result is empty; a new decomposition would "
            "not correspond to them. Refusing to regenerate.",
            tuple(produced),
        )


def _candidates_derived_from(
    workspace: RawProcessorWorkspace, context: _Context
) -> tuple[str, ...]:
    """Requirement IDs of Standard Requirements that already derive from this RAW."""
    try:
        return tuple(
            standard.requirement_id or standard.id
            for standard in context.existing_standards
            if any(
                raw.id == context.raw.id for raw in workspace.derived_from(standard.id)
            )
        )
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            "Could not read the provenance of existing Standard Requirements.",
            (str(error),),
        ) from error


def _produce_processing_result(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    context: _Context,
    journal: _Journal,
) -> ProcessingResult:
    """Invoke the model once and persist the validated decomposition.

    Persisting comes before any candidate entity exists, so a retry can always
    reconstruct candidate identity without the model.
    """
    prompt, model_context = build_prompt(
        raw_requirement_id=context.raw.requirement_id or "",
        raw_title=context.raw.title or "",
        project_name=context.project.name,
        raw_body=context.raw_body,
        comparison=_comparison_context(workspace, context),
    )
    result = _decompose(model, context, prompt, model_context, journal)
    _persist_processing_result(workspace, context, result, journal)
    return result


def _comparison_context(
    workspace: RawProcessorWorkspace, context: _Context
) -> ComparisonContext:
    """Read the peers' Root Documents only once a new model call is certain."""
    try:
        return assemble_comparison_context(
            workspace, context.project.id, context.raw.id, context.existing_standards
        )
    except ComparisonContextError as error:
        raise _StageFailed(
            ProcessResultCode.COMPARISON_CONTEXT_INCOMPLETE,
            error.message,
            error.details,
        ) from error


def _decompose(
    model: ModelRuntime,
    context: _Context,
    prompt: str,
    model_context: str,
    journal: _Journal,
) -> ProcessingResult:
    """One model invocation, validated against the decomposition contract.

    The complete assembled input is measured here, after every section has
    been added and before the invocation is recorded or made.
    """
    try:
        require_input_within_budget("RAW Process", prompt, model_context)
    except ComparisonContextError as error:
        raise _StageFailed(
            ProcessResultCode.COMPARISON_CONTEXT_INCOMPLETE, error.message
        ) from error
    journal.model_invoked = True
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
    return build_processing_result(context.raw.requirement_id or "", decomposition)


def _recover_processing_result(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    context: _Context,
    shell: DocumentNode,
    journal: _Journal,
) -> ProcessingResult:
    """Run the model once and complete the named empty shell in place.

    The earlier response is gone; this is a new decomposition of the current
    RAW input, written into the same Document only if fresh reads show the
    RAW is still this stage's target with the same Root, and the shell is
    still the single, still-empty Processing Result under it.
    """
    prompt, model_context = build_prompt(
        raw_requirement_id=context.raw.requirement_id or "",
        raw_title=context.raw.title or "",
        project_name=context.project.name,
        raw_body=context.raw_body,
        comparison=_comparison_context(workspace, context),
    )
    result = _decompose(model, context, prompt, model_context, journal)
    _require_still_eligible(workspace, context)
    current = _processing_result_node(workspace, context)
    if current is None or current.id != shell.id or current.name != shell.name:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"Processing Result Document {document_label(shell)} is no longer the "
            "Processing Result under this Root; nothing was written.",
        )
    if not is_empty_body(_read_result_body(workspace, current)):
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"Processing Result Document {document_label(shell)} was filled by "
            "another actor while the model was running; refusing to overwrite it.",
        )
    _store_processing_result(workspace, current, result, journal)
    return result


def _require_still_eligible(
    workspace: RawProcessorWorkspace, context: _Context
) -> None:
    """Freshly prove the RAW is still in Process with the same Root Document.

    Taken immediately before the recovered body is written. The shell is then
    re-listed under a Root that is known to be current, not merely cached.
    """
    raw = context.raw
    try:
        current = workspace.read_requirement(raw.id)
        attached = workspace.documents_attached_to_requirement(raw.public_id)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            f"Could not re-read {raw.requirement_id} before filling the empty "
            "Processing Result; nothing was written.",
            (str(error),),
        ) from error
    drift = eligibility_drift(
        raw, context.root_document, current, attached, RAW_TYPE, PROCESS_STATE
    )
    if drift:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"{raw.requirement_id} changed while the model was running. The empty "
            "Processing Result was not filled and nothing else was written; the "
            "change made outside this run stands.",
            drift,
        )


def _persist_processing_result(
    workspace: RawProcessorWorkspace,
    context: _Context,
    result: ProcessingResult,
    journal: _Journal,
) -> None:
    """Create the artifact Document, then write and read back its body.

    The creation is journaled as soon as the create call returns an identity,
    separately from the body: a created shell is not a persisted result.
    """
    name = processing_result_name(context.raw.requirement_id or "")
    try:
        node = workspace.create_child_document(name, context.root_document.id)
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_RESULT_WRITE_FAILED,
            "Could not create the Processing Result Document; nothing durable "
            "is known to exist.",
            (str(error),),
        ) from error
    journal.created.append(f"Processing Result Document {document_label(node)} created")
    if not node.secret:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_RESULT_WRITE_FAILED,
            f"Processing Result Document {document_label(node)} exposes no "
            "content secret; its body was not written.",
        )
    _store_processing_result(workspace, node, result, journal)


def _store_processing_result(
    workspace: RawProcessorWorkspace,
    node: DocumentNode,
    result: ProcessingResult,
    journal: _Journal,
) -> None:
    """Write the body into an existing Document and prove it stored."""
    try:
        workspace.write_document_content(
            node.secret or "", render_processing_result(result)
        )
        stored = workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_RESULT_WRITE_FAILED,
            f"The body of Processing Result Document {document_label(node)} was "
            "not confirmed stored. A retry reads the Document: a valid body "
            f"resumes normally; an empty one needs {RECOVERY_OPTION} {node.id}.",
            (str(error),),
        ) from error
    try:
        read_back = parse_processing_result(stored)
    except InvalidProcessingResult as error:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_RESULT_WRITE_FAILED,
            f"Processing Result Document {document_label(node)} does not read "
            "back as valid.",
            (str(error),),
        ) from error
    if read_back.raw_requirement_id != result.raw_requirement_id:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_RESULT_WRITE_FAILED,
            f"Processing Result Document {document_label(node)} reads back for "
            f"{read_back.raw_requirement_id!r}.",
        )
    journal.created.append(f"Processing Result {document_label(node)} persisted")


# -- candidate application --------------------------------------------------


@dataclass(frozen=True)
class _CandidateState:
    """What already exists for one candidate, read before anything is written."""

    record: RequirementRecord | None
    document: DocumentNode | None
    content: str | None


def _apply_candidates(
    workspace: RawProcessorWorkspace,
    context: _Context,
    result: ProcessingResult,
    journal: _Journal,
) -> tuple[str, ...]:
    """Create or resume every candidate, one verifiable step at a time.

    Every candidate is inspected before the first write, so a conflict on a
    later candidate is found while nothing has been touched yet.
    """
    states = [
        _inspect_candidate(workspace, context, keyed) for keyed in result.candidates
    ]
    applied: list[str] = []
    for keyed, state in zip(result.candidates, states, strict=True):
        applied.append(_apply_candidate(workspace, context, keyed, state, journal))
    return tuple(applied)


def _inspect_candidate(
    workspace: RawProcessorWorkspace, context: _Context, keyed: KeyedCandidate
) -> _CandidateState:
    """Read what exists for a candidate and refuse anything this run does not own.

    The processor owns a candidate only while it is the unfinished initial
    Draft it created: same Project and title, no Requirement ID other than the
    one this run would assign, still in ``Draft``, and a Root Document that is
    either empty or exactly what the persisted result renders. Anything else
    belongs to a later stage or to a human, and is a conflict.
    """
    entity_id = keyed.fibery_id(context.raw.id)
    try:
        record = workspace.read_requirement(entity_id)
        if record is None:
            return _CandidateState(record=None, document=None, content=None)
        _check_adoptable(record, context, keyed)
        _check_unprogressed(record, keyed)
        requirement_id = _expected_requirement_id(context, keyed, record)
        attached = workspace.documents_attached_to_requirement(record.public_id)
        if len(attached) > 1:
            raise _StageFailed(
                ProcessResultCode.PROCESSING_STATE_CONFLICT,
                f"Candidate {keyed.key} has {len(attached)} attached Documents; "
                "exactly one Root Document is required.",
            )
        if not attached:
            return _CandidateState(record=record, document=None, content=None)
        document = attached[0]
        content = workspace.read_document_content(document.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            ProcessResultCode.FIBERY_READ_FAILED,
            f"Could not inspect candidate {keyed.key}.",
            (str(error),),
        ) from error
    _check_content_owned(keyed, requirement_id, content)
    return _CandidateState(record=record, document=document, content=content)


def _check_unprogressed(record: RequirementRecord, keyed: KeyedCandidate) -> None:
    """A candidate past the initial Draft belongs to a later stage or a human."""
    if record.type_name not in (None, STANDARD_TYPE):
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"Candidate {keyed.key} resolves to an entity of Type "
            f"{record.type_name!r}; refusing to reuse it.",
        )
    if record.state not in (None, DRAFT_STATE):
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"Candidate {keyed.key} ({record.requirement_id or record.id}) has "
            f"moved on to State {record.state!r}. RAW processing never demotes "
            "or rewrites a candidate that left Draft; nothing was changed.",
        )


def _check_content_owned(
    keyed: KeyedCandidate, requirement_id: str, content: str
) -> None:
    """An existing Root is reused only if it is empty or exactly the candidate."""
    if not content.strip():
        return
    if content_equivalent(content, keyed.candidate.document(requirement_id)):
        return
    raise _StageFailed(
        ProcessResultCode.PROCESSING_STATE_CONFLICT,
        f"The Root Document of candidate {keyed.key} ({requirement_id}) no "
        "longer matches the persisted decomposition; refusing to overwrite "
        "content this run did not write.",
    )


def _apply_candidate(
    workspace: RawProcessorWorkspace,
    context: _Context,
    keyed: KeyedCandidate,
    state: _CandidateState,
    journal: _Journal,
) -> str:
    """Bring one candidate to a complete state, skipping finished steps."""
    entity_id = keyed.fibery_id(context.raw.id)
    record = state.record or _create_entity(
        workspace, context, keyed, entity_id, journal
    )
    requirement_id = _ensure_requirement_id(workspace, context, keyed, record, journal)
    _ensure_type_and_state(workspace, keyed, record, journal)
    _ensure_derived_from(workspace, context, record, journal)
    document = state.document or _create_root_document(
        workspace, context, keyed, requirement_id, record, journal
    )
    _ensure_content(
        workspace, keyed, requirement_id, document, state.content or "", journal
    )
    _validate_candidate(workspace, context, keyed, requirement_id, record, document)
    return requirement_id


def _create_entity(
    workspace: RawProcessorWorkspace,
    context: _Context,
    keyed: KeyedCandidate,
    entity_id: str,
    journal: _Journal,
) -> RequirementRecord:
    """Create the candidate entity at its deterministic id.

    An entity already at that id was inspected and adopted before any write;
    only a candidate with no entity reaches this point.
    """
    try:
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
    expected = _expected_requirement_id(context, keyed, record)
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


def _expected_requirement_id(
    context: _Context, keyed: KeyedCandidate, record: RequirementRecord
) -> str:
    expected = namespaced_requirement_id(
        context.project.code or "",
        keyed.candidate.category.id_infix,
        record.public_id,
    )
    if record.requirement_id and record.requirement_id != expected:
        raise _StageFailed(
            ProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"Candidate {keyed.key} already carries Requirement ID "
            f"{record.requirement_id!r}, expected {expected!r}.",
        )
    return expected


def _ensure_type_and_state(
    workspace: RawProcessorWorkspace,
    keyed: KeyedCandidate,
    record: RequirementRecord,
    journal: _Journal,
) -> None:
    """Set the initial Type and State once. A State past Draft is never reset."""
    _check_unprogressed(record, keyed)
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


def _create_root_document(
    workspace: RawProcessorWorkspace,
    context: _Context,
    keyed: KeyedCandidate,
    requirement_id: str,
    record: RequirementRecord,
    journal: _Journal,
) -> DocumentNode:
    """Create the Root Document contained by the candidate, with no Folder.

    An existing Root was inspected and adopted before any write; only a
    candidate with no Root Document reaches this point.
    """
    name = keyed.candidate.document_name(requirement_id)
    try:
        document = workspace.create_requirement_document(
            name=name,
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
    current: str,
    journal: _Journal,
) -> None:
    """Write the approved document, rendered from the persisted result.

    Only an empty Root is written. Content equivalent to the candidate is
    already complete and is left alone; content that differs was refused at
    inspection and is refused again here rather than overwritten.
    """
    if not document.secret:
        raise _StageFailed(
            ProcessResultCode.CONTENT_WRITE_FAILED,
            f"The Root Document of {requirement_id} exposes no content secret.",
        )
    body = keyed.candidate.document(requirement_id)
    if current.strip():
        _check_content_owned(keyed, requirement_id, current)
        return
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
