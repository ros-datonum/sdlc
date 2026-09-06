"""`STANDARD Requirement + Process` — normalize, analyze and propose.

Implements Standard-Requirement-Process-Spec-v0.1. Process improves the
requirement and reports what it found; it never certifies it, and it never
writes a dependency or impact relation. Review does that.

The model runs at most once per iteration. Its validated output is persisted as
a numbered Process Result before the Root Document is touched, so a retry
resumes deterministically instead of asking the model again, and re-entering
Process without editing the document is recognised as nothing to do.

A run writes only over the input it captured. The Requirement, its single Root
Document and that Root's content are re-read from Fibery immediately before
each normative write - persisting the Process Result, rewriting the Root, and
moving to Review - and compared with what this invocation read at the start.
Any drift is a processing-state conflict: nothing further is written, nothing
already durable is rolled back, and the change made by a human or another
writer stands. These are fresh reads, not a transaction; a change that lands
between a guard's read and the write it protects is still not detected.
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
from sdlc.process_result import (
    FIRST_ITERATION,
    InvalidProcessResult,
    ProcessResult,
    build_process_result,
    document_fingerprint,
    parse_process_result,
    parse_process_result_name,
    process_result_name,
    render_process_result,
)
from sdlc.raw_source import content_equivalent
from sdlc.results import StandardProcessResult, StandardProcessResultCode
from sdlc.review_result import parse_review_result_name
from sdlc.standard_analysis import InvalidAnalysisOutput, parse_analysis_output
from sdlc.standard_prompt import build_analysis_prompt

STANDARD_TYPE = "Standard"
PROCESS_STATE = "Process"
REVIEW_STATE = "Review"


class _StageFailed(Exception):
    """A stage of processing could not complete."""

    def __init__(
        self,
        code: StandardProcessResultCode,
        message: str,
        causes: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.causes = causes


@dataclass
class _Journal:
    """Durable Fibery changes this run made, and whether the model was asked."""

    created: list[str] = field(default_factory=list)
    model_invoked: bool = False

    @property
    def has_durable_state(self) -> bool:
        return bool(self.created)


@dataclass(frozen=True)
class _Observed:
    """A fresh read of the target, taken immediately before a normative write."""

    requirement: RequirementRecord | None
    attached: tuple[DocumentNode, ...]
    root_content: str | None


@dataclass(frozen=True)
class _Context:
    """Everything read from Fibery before the model is consulted."""

    requirement: RequirementRecord
    project: ProjectRecord
    root_document: DocumentNode
    root_content: str
    input_fingerprint: str
    child_content: str
    raw_ancestry: str
    existing_standards: tuple[RequirementRecord, ...]
    results: tuple[tuple[DocumentNode, ProcessResult], ...]

    @property
    def latest(self) -> tuple[DocumentNode, ProcessResult] | None:
        return self.results[-1] if self.results else None


def process_standard_requirement(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    entity_id: str,
) -> StandardProcessResult:
    """Normalize and analyze one Standard Requirement in Process."""
    journal = _Journal()
    try:
        context = _load_context(workspace, entity_id)

        resumable = _resumable_result(context)
        if resumable is None and _is_unchanged(context):
            return _no_changes_result(context)

        if resumable is not None:
            result = resumable
        else:
            result = _produce_result(workspace, model, context, journal)

        _apply_document(workspace, context, result, journal)
        _transition_to_review(workspace, context, result, journal)
    except _StageFailed as failure:
        return _failure_result(failure, journal)

    return StandardProcessResult(
        code=StandardProcessResultCode.REQUIREMENT_PROCESSED,
        message=(f"{result.requirement_id} processed, iteration {result.iteration}."),
        requirement_id=result.requirement_id,
        iteration=result.iteration,
        findings=tuple(
            f"{f.kind.value}"
            + (f" {f.requirement_id}" if f.requirement_id else "")
            + f": {f.detail}"
            for f in result.findings
        ),
        proposed_relations=tuple(
            f"{r.kind.value} {r.requirement_id}: {r.rationale}"
            for r in result.proposed_relations
        ),
        model_invoked=journal.model_invoked,
        created=tuple(journal.created),
    )


def _no_changes_result(context: _Context) -> StandardProcessResult:
    """Nothing to process, and nothing is mutated - including the State.

    Two histories produce this snapshot: a completed run that a human then
    deliberately returned to Process, and a run whose only failure was the
    final transition. Persisted state cannot tell them apart, so the processor
    does not guess. It preserves the workflow state it was given rather than
    inferring intent, which means a deliberate Review -> Process is never
    silently undone. Recovering the rarer failed-transition case is manual;
    that invocation reported the failure explicitly at the time.
    """
    latest = context.latest
    return StandardProcessResult(
        code=StandardProcessResultCode.NO_CHANGES_TO_PROCESS,
        message=(
            f"{context.requirement.requirement_id} is unchanged since iteration "
            f"{latest[1].iteration}; nothing to process."
        ),
        requirement_id=context.requirement.requirement_id,
        iteration=latest[1].iteration,
        model_invoked=False,
    )


def _failure_result(failure: _StageFailed, journal: _Journal) -> StandardProcessResult:
    """Durable state means PARTIAL_PROCESSING; a retry resumes it.

    A processing-state conflict is reported as itself even when this run
    already made something durable: the durable steps are listed and left in
    place, but the Requirement was changed by someone else, so no promise
    about its State or about a resuming retry is made.
    """
    if journal.has_durable_state and failure.code not in {
        StandardProcessResultCode.PROCESSING_STATE_CONFLICT,
        StandardProcessResultCode.INVALID_PROCESSING_RESULT,
    }:
        return StandardProcessResult(
            code=StandardProcessResultCode.PARTIAL_PROCESSING,
            message=(
                "Processing did not complete; the Requirement stays in Process "
                "and a retry will resume."
            ),
            model_invoked=journal.model_invoked,
            created=tuple(journal.created),
            details=(failure.code.value, failure.message, *failure.causes),
        )
    return StandardProcessResult(
        code=failure.code,
        message=failure.message,
        model_invoked=journal.model_invoked,
        created=tuple(journal.created),
        details=failure.causes,
    )


# -- context ----------------------------------------------------------------


def _load_context(workspace: RawProcessorWorkspace, entity_id: str) -> _Context:
    """Read the Requirement and everything needed to process it."""
    try:
        requirement = workspace.read_requirement(entity_id)
    except FiberyError as error:
        raise _StageFailed(
            StandardProcessResultCode.FIBERY_READ_FAILED,
            f"Could not read Requirement {entity_id}.",
            (str(error),),
        ) from error
    if requirement is None:
        raise _StageFailed(
            StandardProcessResultCode.REQUIREMENT_NOT_FOUND,
            f"No Requirement with id {entity_id}.",
        )
    if requirement.type_name != STANDARD_TYPE:
        raise _StageFailed(
            StandardProcessResultCode.NOT_A_STANDARD_REQUIREMENT,
            f"{requirement.requirement_id} has Type {requirement.type_name!r}; "
            f"this processor handles only {STANDARD_TYPE!r}.",
        )
    if requirement.state != PROCESS_STATE:
        raise _StageFailed(
            StandardProcessResultCode.REQUIREMENT_NOT_IN_PROCESS,
            f"{requirement.requirement_id} is in State {requirement.state!r}; "
            f"this processor handles only {PROCESS_STATE!r}.",
        )

    try:
        project = workspace.read_project(requirement.project_id or "")
        attached = workspace.documents_attached_to_requirement(requirement.public_id)
        standards = workspace.standard_requirements_in_project(
            requirement.project_id or ""
        )
    except FiberyError as error:
        raise _StageFailed(
            StandardProcessResultCode.FIBERY_READ_FAILED,
            f"Could not read the context of {requirement.requirement_id}.",
            (str(error),),
        ) from error
    if project is None:
        raise _StageFailed(
            StandardProcessResultCode.PROJECT_STRUCTURE_INVALID,
            f"{requirement.requirement_id} has no resolvable Project.",
        )
    if len(attached) != 1:
        raise _StageFailed(
            StandardProcessResultCode.PROJECT_STRUCTURE_INVALID,
            f"{requirement.requirement_id} has {len(attached)} attached "
            "Documents; exactly one Root Document is required.",
        )

    root = attached[0]
    results, child_content = _read_children(workspace, requirement, root)
    try:
        root_content = workspace.read_document_content(root.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            StandardProcessResultCode.FIBERY_READ_FAILED,
            "Could not read the Root Document.",
            (str(error),),
        ) from error

    return _Context(
        requirement=requirement,
        project=project,
        root_document=root,
        root_content=root_content,
        input_fingerprint=document_fingerprint(root_content),
        child_content=child_content,
        raw_ancestry=_read_raw_ancestry(workspace, requirement),
        existing_standards=tuple(
            record
            for record in standards
            if record.id != requirement.id and record.requirement_id
        ),
        results=results,
    )


def _read_children(
    workspace: RawProcessorWorkspace,
    requirement: RequirementRecord,
    root: DocumentNode,
) -> tuple[tuple[tuple[DocumentNode, ProcessResult], ...], str]:
    """Split the Root Document's children into Process Results and source.

    A previous Process Result is this processor's own output and must never be
    fed back to the model as requirement content.
    """
    try:
        children = workspace.child_documents(root.id)
    except FiberyError as error:
        raise _StageFailed(
            StandardProcessResultCode.FIBERY_READ_FAILED,
            "Could not list the Requirement's child Documents.",
            (str(error),),
        ) from error

    results: list[tuple[DocumentNode, ProcessResult]] = []
    seen_iterations: dict[int, str] = {}
    sections: list[str] = []
    for child in children:
        if _is_review_artifact(child.name, requirement.requirement_id):
            continue
        parsed_name = parse_process_result_name(child.name)
        if parsed_name is None or parsed_name[0] != requirement.requirement_id:
            try:
                sections.append(
                    f"<!-- document: {child.name} -->\n"
                    + workspace.read_document_content(child.secret or "")
                )
            except FiberyError as error:
                raise _StageFailed(
                    StandardProcessResultCode.FIBERY_READ_FAILED,
                    f"Could not read the child Document {child.name!r}.",
                    (str(error),),
                ) from error
            continue

        iteration = parsed_name[1]
        if iteration in seen_iterations:
            raise _StageFailed(
                StandardProcessResultCode.PROCESSING_STATE_CONFLICT,
                f"{requirement.requirement_id} has more than one Process Result "
                f"for iteration {iteration}. Refusing to guess which is "
                "authoritative.",
                (seen_iterations[iteration], child.id),
            )
        seen_iterations[iteration] = child.id
        results.append((child, _read_result(workspace, child, requirement, iteration)))

    results.sort(key=lambda pair: pair[1].iteration)
    return tuple(results), "\n\n".join(sections)


def _is_review_artifact(name: str, requirement_id: str | None) -> bool:
    """Whether a child Document is the independent Reviewer's own output.

    Review writes numbered children under the same Root Document. They are this
    Requirement's review history, not requirement content, so feeding one back
    to the model as source material would let a reviewer's findings be read as
    something the requirement says.
    """
    parsed = parse_review_result_name(name)
    return parsed is not None and parsed[0] == requirement_id


def _read_result(
    workspace: RawProcessorWorkspace,
    node: DocumentNode,
    requirement: RequirementRecord,
    iteration: int,
) -> ProcessResult:
    try:
        content = workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            StandardProcessResultCode.FIBERY_READ_FAILED,
            f"Could not read Process Result {iteration}.",
            (str(error),),
        ) from error
    try:
        result = parse_process_result(content)
    except InvalidProcessResult as error:
        raise _StageFailed(
            StandardProcessResultCode.INVALID_PROCESSING_RESULT,
            f"Process Result {iteration} of {requirement.requirement_id} cannot "
            "be resumed from.",
            (str(error),),
        ) from error
    if result.iteration != iteration or result.requirement_id != (
        requirement.requirement_id
    ):
        raise _StageFailed(
            StandardProcessResultCode.PROCESSING_STATE_CONFLICT,
            f"Process Result {node.name!r} describes "
            f"{result.requirement_id!r} iteration {result.iteration}.",
        )
    return result


def _read_raw_ancestry(
    workspace: RawProcessorWorkspace, requirement: RequirementRecord
) -> str:
    """The originating RAW Requirement's document, when it can be resolved.

    Included so the model can tell "the source never said this" from
    "decomposition dropped it". Absence is not an error: a Standard Requirement
    need not have come from a RAW.
    """
    try:
        raws = workspace.derived_from(requirement.id)
        if not raws:
            return ""
        sections = []
        for raw in raws:
            documents = workspace.documents_attached_to_requirement(raw.public_id)
            for document in documents:
                sections.append(
                    f"<!-- RAW {raw.requirement_id} -->\n"
                    + workspace.read_document_content(document.secret or "")
                )
        return "\n\n".join(sections)
    except FiberyError as error:
        raise _StageFailed(
            StandardProcessResultCode.FIBERY_READ_FAILED,
            "Could not read the originating RAW Requirement.",
            (str(error),),
        ) from error


# -- iteration selection ----------------------------------------------------


def _resumable_result(context: _Context) -> ProcessResult | None:
    """The latest Process Result, when its application never completed.

    Three cases are distinguished by fingerprint, and the input fingerprint is
    what separates the last two:

    - the document matches the latest output  -> that iteration was applied
    - the document matches the latest input   -> the rewrite never landed, so
                                                 resume it without the model
    - the document matches neither            -> its content changed, so this is
                                                 a new iteration
    """
    latest = context.latest
    if latest is None:
        return None
    result = latest[1]
    if context.input_fingerprint == result.output_fingerprint:
        return None
    return result if context.input_fingerprint == result.input_fingerprint else None


def _is_unchanged(context: _Context) -> bool:
    """Whether the Root Document still matches the last applied output."""
    latest = context.latest
    return (
        latest is not None and context.input_fingerprint == latest[1].output_fingerprint
    )


# -- write preconditions ----------------------------------------------------


def _observe(
    workspace: RawProcessorWorkspace, context: _Context, stage: str
) -> _Observed:
    """Freshly read the target. Never reuses the context or an earlier read."""
    requirement = context.requirement
    try:
        current = workspace.read_requirement(requirement.id)
        attached = tuple(
            workspace.documents_attached_to_requirement(requirement.public_id)
        )
        root = next((d for d in attached if d.id == context.root_document.id), None)
        content = (
            workspace.read_document_content(root.secret or "")
            if root is not None
            else None
        )
    except FiberyError as error:
        raise _StageFailed(
            StandardProcessResultCode.FIBERY_READ_FAILED,
            f"Could not re-read {requirement.requirement_id} {stage}; refusing "
            "to write without a fresh read.",
            (str(error),),
        ) from error
    return _Observed(requirement=current, attached=attached, root_content=content)


def _require_unchanged(
    workspace: RawProcessorWorkspace,
    context: _Context,
    expected_content: str,
    stage: str,
) -> None:
    """Refuse the next write unless the target still matches this invocation.

    Protected: the entity itself, its Requirement ID, Title, Project, Revision
    and public id, Type Standard, State Process, exactly one attached Root
    Document with the same identity, secret and Folder, and Root content
    canonically equivalent to `expected_content`.
    """
    observed = _observe(workspace, context, stage)
    drift = _identity_drift(context, observed) + _root_drift(
        context, observed, expected_content
    )
    if not drift:
        return
    raise _StageFailed(
        StandardProcessResultCode.PROCESSING_STATE_CONFLICT,
        f"{context.requirement.requirement_id} changed {stage}. Nothing further "
        "was written; whatever this run had already made durable is listed and "
        "left in place, and the change made outside this run stands.",
        tuple(drift),
    )


def _identity_drift(context: _Context, observed: _Observed) -> list[str]:
    captured, current = context.requirement, observed.requirement
    if current is None:
        return ["the Requirement can no longer be read"]
    drift: list[str] = []
    if current.type_name != STANDARD_TYPE:
        drift.append(f"Type is now {current.type_name!r}")
    if current.state != PROCESS_STATE:
        drift.append(f"State is now {current.state!r}")
    protected = (
        ("Requirement ID", captured.requirement_id, current.requirement_id),
        ("Title", captured.title, current.title),
        ("Revision", captured.revision, current.revision),
        ("Project", captured.project_id, current.project_id),
        ("public id", captured.public_id, current.public_id),
    )
    drift.extend(
        f"{label} changed from {before!r} to {after!r}"
        for label, before, after in protected
        if before != after
    )
    return drift


def _root_drift(
    context: _Context, observed: _Observed, expected_content: str
) -> list[str]:
    root = context.root_document
    if len(observed.attached) != 1 or observed.attached[0].id != root.id:
        return [
            (
                "the Root Document is no longer the single attached Document "
                f"({len(observed.attached)} attached now)"
            )
        ]
    current = observed.attached[0]
    drift: list[str] = []
    if current.secret != root.secret:
        drift.append("the Root Document's content secret changed")
    if current.folder_id != root.folder_id:
        drift.append(f"the Root Document moved to Folder {current.folder_id!r}")
    if observed.root_content is None or not content_equivalent(
        observed.root_content, expected_content
    ):
        drift.append("the Root Document content changed")
    return drift


# -- producing and applying -------------------------------------------------


def _produce_result(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    context: _Context,
    journal: _Journal,
) -> ProcessResult:
    """Invoke the model once and persist the iteration before mutating."""
    latest = context.latest
    iteration = latest[1].iteration + 1 if latest else FIRST_ITERATION

    prompt, model_context = build_analysis_prompt(
        requirement=context.requirement,
        project_name=context.project.name,
        root_content=context.root_content,
        child_content=context.child_content,
        raw_ancestry=context.raw_ancestry,
        existing_standards=context.existing_standards,
    )
    journal.model_invoked = True
    try:
        response = model.run(prompt, model_context)
    except ModelRuntimeError as error:
        raise _StageFailed(
            StandardProcessResultCode.MODEL_RUNTIME_FAILED,
            "The configured local model runtime could not run the analysis.",
            (str(error),),
        ) from error

    try:
        analysis = parse_analysis_output(response.text)
    except InvalidAnalysisOutput as error:
        raise _StageFailed(
            StandardProcessResultCode.INVALID_MODEL_OUTPUT,
            "The model's response does not satisfy the analysis contract.",
            (str(error),),
        ) from error

    result = build_process_result(
        requirement_id=context.requirement.requirement_id or "",
        iteration=iteration,
        input_fingerprint=context.input_fingerprint,
        analysis=analysis,
    )
    # The model reasoned over the captured input; persist only if it is still
    # the input. A stale output is dropped, never recorded as an iteration.
    _require_unchanged(
        workspace, context, context.root_content, "while the model was running"
    )
    _persist_result(workspace, context, result, journal)
    return result


def _persist_result(
    workspace: RawProcessorWorkspace,
    context: _Context,
    result: ProcessResult,
    journal: _Journal,
) -> None:
    """Write the iteration and read it back before trusting it."""
    name = process_result_name(result.requirement_id, result.iteration)
    try:
        node = workspace.create_child_document(name, context.root_document.id)
        if not node.secret:
            raise _StageFailed(
                StandardProcessResultCode.PROCESS_RESULT_WRITE_FAILED,
                "The Process Result document exposes no content secret.",
            )
        workspace.write_document_content(node.secret, render_process_result(result))
        stored = workspace.read_document_content(node.secret)
    except FiberyError as error:
        raise _StageFailed(
            StandardProcessResultCode.PROCESS_RESULT_WRITE_FAILED,
            f"Could not persist {name}.",
            (str(error),),
        ) from error

    try:
        parse_process_result(stored)
    except InvalidProcessResult as error:
        raise _StageFailed(
            StandardProcessResultCode.PROCESS_RESULT_WRITE_FAILED,
            f"{name} does not read back as valid.",
            (str(error),),
        ) from error
    journal.created.append(f"{name} ({node.id})")


def _apply_document(
    workspace: RawProcessorWorkspace,
    context: _Context,
    result: ProcessResult,
    journal: _Journal,
) -> None:
    """Rewrite the Root Document from the persisted iteration, then verify."""
    document = context.root_document
    expected = result.normalized.document(result.requirement_id)
    if not document.secret:
        raise _StageFailed(
            StandardProcessResultCode.CONTENT_WRITE_FAILED,
            f"The Root Document of {result.requirement_id} exposes no secret.",
        )
    # Persisting the result took time too. Re-read immediately before the
    # rewrite, for a new iteration and for a resumed one alike.
    _require_unchanged(
        workspace, context, context.root_content, "before the Root Document rewrite"
    )
    try:
        workspace.write_document_content(document.secret, expected)
        stored = workspace.read_document_content(document.secret)
    except FiberyError as error:
        raise _StageFailed(
            StandardProcessResultCode.CONTENT_WRITE_FAILED,
            f"Could not rewrite the Root Document of {result.requirement_id}.",
            (str(error),),
        ) from error

    # Fibery re-serializes stored Markdown, so the comparison is canonical.
    if not content_equivalent(stored, expected):
        raise _StageFailed(
            StandardProcessResultCode.VALIDATION_FAILED,
            f"The Root Document of {result.requirement_id} does not match the "
            "persisted Process Result after the rewrite.",
        )
    journal.created.append(f"Root Document rewritten for {result.requirement_id}")


def _transition_to_review(
    workspace: RawProcessorWorkspace,
    context: _Context,
    result: ProcessResult,
    journal: _Journal,
) -> None:
    """Move to Review, and confirm it by reading the entity back.

    The State is written only if a fresh read still shows the Requirement in
    Process, unchanged in identity, with its Root holding the output this
    run just applied.
    """
    requirement = context.requirement
    _require_unchanged(
        workspace,
        context,
        result.normalized.document(result.requirement_id),
        "after the Root Document rewrite",
    )
    try:
        workspace.set_requirement_state(requirement.id, REVIEW_STATE)
        stored = workspace.read_requirement(requirement.id)
    except FiberyError as error:
        raise _StageFailed(
            StandardProcessResultCode.FIBERY_WRITE_FAILED,
            f"Could not move {requirement.requirement_id} to {REVIEW_STATE}.",
            (str(error),),
        ) from error

    if stored is None or stored.state != REVIEW_STATE:
        raise _StageFailed(
            StandardProcessResultCode.VALIDATION_FAILED,
            f"{requirement.requirement_id} is still in State "
            f"{stored.state!r} after the transition to {REVIEW_STATE}."
            if stored
            else f"{requirement.requirement_id} could not be read back.",
        )
    if stored.revision != requirement.revision:
        raise _StageFailed(
            StandardProcessResultCode.VALIDATION_FAILED,
            f"Revision changed from {requirement.revision!r} to "
            f"{stored.revision!r}; Process must not alter it.",
        )
    journal.created.append(f"State = {REVIEW_STATE}")
