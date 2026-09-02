"""`STANDARD Requirement + Review` — independently verify, confirm or reject.

Implements Standard-Requirement-Review-Spec-v0.1. Review checks what Process
produced and certifies nothing else: it never normalizes, never rewrites the
Root Document, and never writes a dependency or impact relation. The action
that writes Requirement content must not be the action that certifies it.

Two invariants shape the code:

- **a Requirement reaches Ready only after a durable, valid, non-stale Review
  Result exists.** The artifact is written and read back before the state
  moves, so a human at Ready always has the evidence behind the verdict;
- **a review certifies one exact input.** The Root Document fingerprint, the
  Process Result iteration and that iteration's output fingerprint are captured
  up front and re-checked immediately before the transition. If any moved, the
  certification no longer describes reality and is refused rather than applied.

Every completed review reaches Ready regardless of its verdict, including
BLOCKING: Ready means the independent agent review is complete and the human
decision is due, not that the Requirement is good.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    ProjectRecord,
    RawProcessorWorkspace,
    RequirementRecord,
    RequirementRelations,
)
from sdlc.model_runtime import ModelRuntime, ModelRuntimeError
from sdlc.process_result import (
    InvalidProcessResult,
    ProcessResult,
    document_fingerprint,
    parse_process_result,
    parse_process_result_name,
)
from sdlc.results import StandardReviewResult, StandardReviewResultCode
from sdlc.review_prompt import build_review_prompt
from sdlc.review_result import (
    FIRST_ITERATION,
    InvalidReviewResult,
    ReviewResult,
    build_review_result,
    parse_review_result,
    parse_review_result_name,
    render_review_result,
    review_result_name,
)
from sdlc.standard_review import (
    InvalidReviewOutput,
    ReviewSeverity,
    parse_review_output,
)

STANDARD_TYPE = "Standard"
REVIEW_STATE = "Review"
READY_STATE = "Ready"


class _StageFailed(Exception):
    """A stage of the review could not complete."""

    def __init__(
        self,
        code: StandardReviewResultCode,
        message: str,
        causes: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.causes = causes


@dataclass
class _Journal:
    """Durable Fibery changes this run made."""

    created: list[str] = field(default_factory=list)

    @property
    def has_durable_state(self) -> bool:
        return bool(self.created)


@dataclass(frozen=True)
class _Bindings:
    """Exactly what a review certifies."""

    document_fingerprint: str
    process_iteration: int
    process_output_fingerprint: str


@dataclass(frozen=True)
class _Context:
    """Everything read from Fibery before the reviewer is consulted."""

    requirement: RequirementRecord
    project: ProjectRecord
    root_document: DocumentNode
    root_content: str
    process_result: ProcessResult
    relations: RequirementRelations
    existing_standards: tuple[RequirementRecord, ...]
    reviews: tuple[tuple[DocumentNode, ReviewResult], ...]

    @property
    def bindings(self) -> _Bindings:
        return _Bindings(
            document_fingerprint=document_fingerprint(self.root_content),
            process_iteration=self.process_result.iteration,
            process_output_fingerprint=self.process_result.output_fingerprint,
        )

    @property
    def latest_review(self) -> ReviewResult | None:
        return self.reviews[-1][1] if self.reviews else None


def review_standard_requirement(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    entity_id: str,
) -> StandardReviewResult:
    """Independently review one Standard Requirement in Review."""
    journal = _Journal()
    model_invoked = False
    try:
        context = _load_context(workspace, entity_id)
        bindings = context.bindings

        if _already_reviewed(context, bindings):
            return _no_changes_result(context)

        result, model_invoked = _produce_review(
            workspace, model, context, bindings, journal
        )
        _recheck_bindings(workspace, context, bindings)
        _transition_to_ready(workspace, context, journal)
    except _StageFailed as failure:
        return _failure_result(failure, journal, model_invoked)

    return _reviewed_result(result, model_invoked, journal)


def _already_reviewed(context: _Context, bindings: _Bindings) -> bool:
    """Whether the latest review already certifies exactly this input."""
    latest = context.latest_review
    return latest is not None and latest.reviews(
        bindings.document_fingerprint,
        bindings.process_iteration,
        bindings.process_output_fingerprint,
    )


def _reviewed_result(
    result: ReviewResult, model_invoked: bool, journal: _Journal
) -> StandardReviewResult:
    """Report a successful run. The verdict travels in the payload.

    A BLOCKING verdict is a successful execution: the reviewer did its job and
    the human at Ready now has what they need to decide.
    """
    return StandardReviewResult(
        code=StandardReviewResultCode.REQUIREMENT_REVIEWED,
        message=(
            f"{result.requirement_id} reviewed, iteration {result.iteration}; "
            f"verdict {result.verdict.value}."
        ),
        requirement_id=result.requirement_id,
        iteration=result.iteration,
        verdict=result.verdict.value,
        blocking=_severity_lines(result, ReviewSeverity.BLOCKING),
        warnings=_severity_lines(result, ReviewSeverity.WARNING),
        verifications=tuple(
            f"[{verification.process_finding_index}] {verification.outcome.value}"
            + (
                f" ({verification.severity.value})"
                if verification.severity is not None
                else ""
            )
            + f": {verification.reason}"
            for verification in result.finding_verifications
        ),
        relations=tuple(
            f"{verification.outcome.value} {verification.kind.value} "
            f"{verification.requirement_id}: {verification.reason}"
            for verification in result.relation_verifications
        ),
        model_invoked=model_invoked,
        created=tuple(journal.created),
    )


def _severity_lines(result: ReviewResult, severity: ReviewSeverity) -> tuple[str, ...]:
    """Everything asserted at one severity, from both sources.

    A confirmed Process finding and a newly discovered one are the same kind of
    thing to the human reading them, so they are reported together.
    """
    confirmed = [
        f"confirmed Process finding [{verification.process_finding_index}]: "
        f"{verification.reason}"
        for verification in result.finding_verifications
        if verification.severity is severity
    ]
    discovered = [
        f"{finding.kind.value}"
        + (f" {finding.requirement_id}" if finding.requirement_id else "")
        + f": {finding.detail}"
        for finding in result.new_findings
        if finding.severity is severity
    ]
    return tuple(confirmed + discovered)


def _no_changes_result(context: _Context) -> StandardReviewResult:
    """Nothing to review, and nothing is mutated - including the State.

    Two histories produce this snapshot: a completed review that a human then
    deliberately returned to Review, and a review whose only failure was the
    final transition. Unlike Process, whose rewritten Root Document is its own
    applied-marker, Review writes nothing to the document and so has no
    intrinsic evidence of which happened.

    It does not guess and it does not add a marker to make guessing possible.
    It preserves the workflow state it was given, so a deliberate return to
    Review is never silently undone. Recovering the rarer failed-transition
    case is manual; that invocation reported the failure explicitly at the time.
    """
    latest = context.latest_review
    assert latest is not None  # _already_reviewed established this
    return StandardReviewResult(
        code=StandardReviewResultCode.NO_CHANGES_TO_REVIEW,
        message=(
            f"{context.requirement.requirement_id} is unchanged since review "
            f"iteration {latest.iteration}; nothing to review."
        ),
        requirement_id=context.requirement.requirement_id,
        iteration=latest.iteration,
        verdict=latest.verdict.value,
        model_invoked=False,
    )


def _failure_result(
    failure: _StageFailed, journal: _Journal, model_invoked: bool
) -> StandardReviewResult:
    """Durable state means PARTIAL_REVIEW, never a normal completion.

    A failed transition to Ready is reported as a failure even though the
    Review Result is intact, because reporting it as success would tell the
    human a decision is due when the workflow never moved.
    """
    if journal.has_durable_state and failure.code not in {
        StandardReviewResultCode.REVIEW_STATE_CONFLICT,
        StandardReviewResultCode.INVALID_REVIEW_RESULT,
        StandardReviewResultCode.REVIEW_RESULT_STALE,
    }:
        return StandardReviewResult(
            code=StandardReviewResultCode.PARTIAL_REVIEW,
            message=(
                "The review did not complete; the Requirement stays in Review "
                "and the Review Result is left in place."
            ),
            model_invoked=model_invoked,
            created=tuple(journal.created),
            details=(failure.code.value, failure.message, *failure.causes),
        )
    return StandardReviewResult(
        code=failure.code,
        message=failure.message,
        model_invoked=model_invoked,
        created=tuple(journal.created),
        details=failure.causes,
    )


# -- context ----------------------------------------------------------------


def _load_context(workspace: RawProcessorWorkspace, entity_id: str) -> _Context:
    """Read the Requirement and everything needed to review it."""
    requirement = _load_requirement(workspace, entity_id)
    try:
        project = workspace.read_project(requirement.project_id or "")
        attached = workspace.documents_attached_to_requirement(requirement.public_id)
        standards = workspace.standard_requirements_in_project(
            requirement.project_id or ""
        )
        relations = workspace.requirement_relations(requirement.id)
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            f"Could not read the context of {requirement.requirement_id}.",
            (str(error),),
        ) from error
    if project is None:
        raise _StageFailed(
            StandardReviewResultCode.PROJECT_STRUCTURE_INVALID,
            f"{requirement.requirement_id} has no resolvable Project.",
        )
    if len(attached) != 1:
        raise _StageFailed(
            StandardReviewResultCode.PROJECT_STRUCTURE_INVALID,
            f"{requirement.requirement_id} has {len(attached)} attached "
            "Documents; exactly one Root Document is required.",
        )

    root = attached[0]
    process_results, reviews = _read_children(workspace, requirement, root)
    if not process_results:
        raise _StageFailed(
            StandardReviewResultCode.NO_PROCESS_RESULT,
            f"{requirement.requirement_id} has no Process Result; there is "
            "nothing to review against.",
        )
    try:
        root_content = workspace.read_document_content(root.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            "Could not read the Root Document.",
            (str(error),),
        ) from error

    return _Context(
        requirement=requirement,
        project=project,
        root_document=root,
        root_content=root_content,
        process_result=process_results[-1],
        relations=relations,
        existing_standards=tuple(
            record
            for record in standards
            if record.id != requirement.id and record.requirement_id
        ),
        reviews=reviews,
    )


def _load_requirement(
    workspace: RawProcessorWorkspace, entity_id: str
) -> RequirementRecord:
    """Read the Requirement and refuse anything this stage does not handle."""
    try:
        requirement = workspace.read_requirement(entity_id)
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            f"Could not read Requirement {entity_id}.",
            (str(error),),
        ) from error
    if requirement is None:
        raise _StageFailed(
            StandardReviewResultCode.REQUIREMENT_NOT_FOUND,
            f"No Requirement with id {entity_id}.",
        )
    if requirement.type_name != STANDARD_TYPE:
        raise _StageFailed(
            StandardReviewResultCode.NOT_A_STANDARD_REQUIREMENT,
            f"{requirement.requirement_id} has Type {requirement.type_name!r}; "
            f"this reviewer handles only {STANDARD_TYPE!r}.",
        )
    if requirement.state != REVIEW_STATE:
        raise _StageFailed(
            StandardReviewResultCode.REQUIREMENT_NOT_IN_REVIEW,
            f"{requirement.requirement_id} is in State {requirement.state!r}; "
            f"this reviewer handles only {REVIEW_STATE!r}.",
        )
    return requirement


def _read_children(
    workspace: RawProcessorWorkspace,
    requirement: RequirementRecord,
    root: DocumentNode,
) -> tuple[tuple[ProcessResult, ...], tuple[tuple[DocumentNode, ReviewResult], ...]]:
    """Split the Root Document's children into Process and Review history.

    Both capabilities write numbered children under the same Root Document, so
    they are told apart by name. Anything else nested there is neither, and is
    ignored: the reviewer's source material is the Root Document, not whatever
    else happens to sit beneath it.
    """
    try:
        children = workspace.child_documents(root.id)
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            "Could not list the Requirement's child Documents.",
            (str(error),),
        ) from error

    process: list[ProcessResult] = []
    reviews: list[tuple[DocumentNode, ReviewResult]] = []
    seen_process: dict[int, str] = {}
    seen_reviews: dict[int, str] = {}
    for child in children:
        process_name = parse_process_result_name(child.name)
        if process_name is not None and process_name[0] == requirement.requirement_id:
            iteration = process_name[1]
            if iteration in seen_process:
                raise _StageFailed(
                    StandardReviewResultCode.INVALID_PROCESS_RESULT,
                    f"{requirement.requirement_id} has more than one Process "
                    f"Result for iteration {iteration}. Refusing to review "
                    "against ambiguous history.",
                    (seen_process[iteration], child.id),
                )
            seen_process[iteration] = child.id
            process.append(
                _read_process_result(workspace, child, requirement, iteration)
            )
            continue

        review_name = parse_review_result_name(child.name)
        if review_name is None or review_name[0] != requirement.requirement_id:
            continue
        iteration = review_name[1]
        if iteration in seen_reviews:
            raise _StageFailed(
                StandardReviewResultCode.REVIEW_STATE_CONFLICT,
                f"{requirement.requirement_id} has more than one Review Result "
                f"for iteration {iteration}. Refusing to guess which is "
                "authoritative.",
                (seen_reviews[iteration], child.id),
            )
        seen_reviews[iteration] = child.id
        reviews.append(
            (child, _read_review_result(workspace, child, requirement, iteration))
        )

    process.sort(key=lambda result: result.iteration)
    reviews.sort(key=lambda pair: pair[1].iteration)
    return tuple(process), tuple(reviews)


def _read_process_result(
    workspace: RawProcessorWorkspace,
    node: DocumentNode,
    requirement: RequirementRecord,
    iteration: int,
) -> ProcessResult:
    """Read one Process Result. It is evidence, and it is never written to."""
    try:
        content = workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            f"Could not read Process Result {iteration}.",
            (str(error),),
        ) from error
    try:
        result = parse_process_result(content)
    except InvalidProcessResult as error:
        raise _StageFailed(
            StandardReviewResultCode.INVALID_PROCESS_RESULT,
            f"Process Result {iteration} of {requirement.requirement_id} cannot "
            "be reviewed against.",
            (str(error),),
        ) from error
    if result.iteration != iteration or result.requirement_id != (
        requirement.requirement_id
    ):
        raise _StageFailed(
            StandardReviewResultCode.INVALID_PROCESS_RESULT,
            f"Process Result {node.name!r} describes "
            f"{result.requirement_id!r} iteration {result.iteration}.",
        )
    return result


def _read_review_result(
    workspace: RawProcessorWorkspace,
    node: DocumentNode,
    requirement: RequirementRecord,
    iteration: int,
) -> ReviewResult:
    try:
        content = workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            f"Could not read Review Result {iteration}.",
            (str(error),),
        ) from error
    try:
        result = parse_review_result(content)
    except InvalidReviewResult as error:
        raise _StageFailed(
            StandardReviewResultCode.INVALID_REVIEW_RESULT,
            f"Review Result {iteration} of {requirement.requirement_id} cannot "
            "be trusted.",
            (str(error),),
        ) from error
    if result.iteration != iteration or result.requirement_id != (
        requirement.requirement_id
    ):
        raise _StageFailed(
            StandardReviewResultCode.INVALID_REVIEW_RESULT,
            f"Review Result {node.name!r} describes "
            f"{result.requirement_id!r} iteration {result.iteration}.",
        )
    return result


# -- reviewing and applying -------------------------------------------------


def _produce_review(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    context: _Context,
    bindings: _Bindings,
    journal: _Journal,
) -> tuple[ReviewResult, bool]:
    """Invoke the reviewer once and persist the iteration before mutating."""
    latest = context.latest_review
    iteration = latest.iteration + 1 if latest else FIRST_ITERATION

    prompt, model_context = build_review_prompt(
        requirement=context.requirement,
        project_name=context.project.name,
        root_content=context.root_content,
        process_result=context.process_result,
        relations=context.relations,
        existing_standards=context.existing_standards,
    )
    try:
        response = model.run(prompt, model_context)
    except ModelRuntimeError as error:
        raise _StageFailed(
            StandardReviewResultCode.MODEL_RUNTIME_FAILED,
            "The configured local model runtime could not run the review.",
            (str(error),),
        ) from error

    try:
        review = parse_review_output(
            response.text,
            context.process_result.findings,
            context.process_result.proposed_relations,
        )
    except InvalidReviewOutput as error:
        raise _StageFailed(
            StandardReviewResultCode.INVALID_MODEL_OUTPUT,
            "The reviewer's response does not satisfy the review contract.",
            (str(error),),
        ) from error

    result = build_review_result(
        requirement_id=context.requirement.requirement_id or "",
        iteration=iteration,
        reviewed_document_fingerprint=bindings.document_fingerprint,
        reviewed_process_iteration=bindings.process_iteration,
        reviewed_process_output_fingerprint=bindings.process_output_fingerprint,
        review=review,
    )
    _persist_result(workspace, context, result, journal)
    return result, True


def _persist_result(
    workspace: RawProcessorWorkspace,
    context: _Context,
    result: ReviewResult,
    journal: _Journal,
) -> None:
    """Write the iteration and read it back before trusting it."""
    name = review_result_name(result.requirement_id, result.iteration)
    try:
        node = workspace.create_child_document(name, context.root_document.id)
        if not node.secret:
            raise _StageFailed(
                StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
                "The Review Result document exposes no content secret.",
            )
        workspace.write_document_content(node.secret, render_review_result(result))
        stored = workspace.read_document_content(node.secret)
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"Could not persist {name}.",
            (str(error),),
        ) from error

    try:
        read_back = parse_review_result(stored)
    except InvalidReviewResult as error:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"{name} does not read back as valid.",
            (str(error),),
        ) from error
    if not read_back.reviews(
        result.reviewed_document_fingerprint,
        result.reviewed_process_iteration,
        result.reviewed_process_output_fingerprint,
    ):
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"{name} reads back bound to a different reviewed state.",
        )
    journal.created.append(f"{name} ({node.id})")


def _recheck_bindings(
    workspace: RawProcessorWorkspace, context: _Context, bindings: _Bindings
) -> None:
    """Re-read what was reviewed, immediately before certifying it.

    The window between reading the Requirement and moving it to Ready is small
    but real. If the Root Document was edited or Process ran again inside it,
    the persisted review describes a state that no longer exists, and applying
    it would certify content nobody reviewed.
    """
    try:
        current_content = workspace.read_document_content(
            context.root_document.secret or ""
        )
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            "Could not re-read the Root Document before the transition.",
            (str(error),),
        ) from error

    process_results, _ = _read_children(
        workspace, context.requirement, context.root_document
    )
    if not process_results:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_STALE,
            f"The Process Result {context.requirement.requirement_id} was "
            "reviewed against is gone.",
        )
    latest = process_results[-1]
    current = _Bindings(
        document_fingerprint=document_fingerprint(current_content),
        process_iteration=latest.iteration,
        process_output_fingerprint=latest.output_fingerprint,
    )
    if current == bindings:
        return

    raise _StageFailed(
        StandardReviewResultCode.REVIEW_RESULT_STALE,
        f"{context.requirement.requirement_id} changed while it was being "
        "reviewed; the Review Result certifies a state that no longer exists.",
        _describe_drift(bindings, current),
    )


def _describe_drift(reviewed: _Bindings, current: _Bindings) -> tuple[str, ...]:
    """Name exactly which binding moved, so the human knows what happened."""
    drift = []
    if reviewed.document_fingerprint != current.document_fingerprint:
        drift.append("The Root Document was edited after the review.")
    if reviewed.process_iteration != current.process_iteration:
        drift.append(
            f"Process ran again: iteration {current.process_iteration} now "
            f"exists, but {reviewed.process_iteration} was reviewed."
        )
    elif reviewed.process_output_fingerprint != current.process_output_fingerprint:
        drift.append(
            f"Process Result {reviewed.process_iteration} no longer produces "
            "the output that was reviewed."
        )
    return tuple(drift)


def _transition_to_ready(
    workspace: RawProcessorWorkspace, context: _Context, journal: _Journal
) -> None:
    """Move to Ready, and confirm it by reading the entity back."""
    requirement = context.requirement
    try:
        workspace.set_requirement_state(requirement.id, READY_STATE)
        stored = workspace.read_requirement(requirement.id)
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_WRITE_FAILED,
            f"Could not move {requirement.requirement_id} to {READY_STATE}.",
            (str(error),),
        ) from error

    if stored is None or stored.state != READY_STATE:
        raise _StageFailed(
            StandardReviewResultCode.VALIDATION_FAILED,
            f"{requirement.requirement_id} is still in State "
            f"{stored.state!r} after the transition to {READY_STATE}."
            if stored
            else f"{requirement.requirement_id} could not be read back.",
        )
    if stored.revision != requirement.revision:
        raise _StageFailed(
            StandardReviewResultCode.VALIDATION_FAILED,
            f"Revision changed from {requirement.revision!r} to "
            f"{stored.revision!r}; Review must not alter it.",
        )
    journal.created.append(f"State = {READY_STATE}")
