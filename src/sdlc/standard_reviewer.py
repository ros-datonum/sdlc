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
    RequirementRelations,
)
from sdlc.model_runtime import ModelRuntime, ModelRuntimeError
from sdlc.normative_tree import (
    NormativeTree,
    NormativeTreeError,
    TreeManifest,
    describe_drift,
    read_normative_tree,
    render_descendants,
)
from sdlc.process_result import (
    InvalidProcessResult,
    ProcessResult,
    document_fingerprint,
    parse_process_result,
    parse_process_result_name,
)
from sdlc.result_shell import (
    RECOVERY_OPTION,
    document_label,
    eligibility_drift,
    is_empty_body,
    recovery_hint,
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
    ReviewOutput,
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
    """Durable Fibery changes this run made, and whether the model was asked."""

    created: list[str] = field(default_factory=list)
    model_invoked: bool = False

    @property
    def has_durable_state(self) -> bool:
        return bool(self.created)


@dataclass(frozen=True)
class _Bindings:
    """Exactly what a review certifies."""

    document_fingerprint: str
    process_iteration: int
    process_output_fingerprint: str
    tree_fingerprint: str


@dataclass(frozen=True)
class _Context:
    """Everything read from Fibery before the reviewer is consulted."""

    requirement: RequirementRecord
    project: ProjectRecord
    root_document: DocumentNode
    root_content: str
    tree: NormativeTree
    process_result: ProcessResult
    relations: RequirementRelations
    existing_standards: tuple[RequirementRecord, ...]
    reviews: tuple[tuple[DocumentNode, ReviewResult], ...]
    # An empty Review Result shell the operator named for recovery, with the
    # iteration its name reserves. Never part of `reviews`.
    shell: tuple[DocumentNode, int] | None = None

    @property
    def bindings(self) -> _Bindings:
        return _Bindings(
            document_fingerprint=document_fingerprint(self.root_content),
            process_iteration=self.process_result.iteration,
            process_output_fingerprint=self.process_result.output_fingerprint,
            tree_fingerprint=self.tree.manifest.fingerprint,
        )

    @property
    def latest_review(self) -> ReviewResult | None:
        return self.reviews[-1][1] if self.reviews else None


def review_standard_requirement(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    entity_id: str,
    recover_empty_result: str | None = None,
) -> StandardReviewResult:
    """Independently review one Standard Requirement in Review.

    `recover_empty_result` names one Review Result Document whose body was
    never stored after a failed persistence. It is explicit permission to run
    the reviewer again and complete that exact Document in place, keeping its
    reserved iteration; it never creates another artifact and never
    overwrites a non-empty one.
    """
    journal = _Journal()
    try:
        context = _load_context(workspace, entity_id, recover_empty_result)
        bindings = context.bindings

        if _already_reviewed(context, bindings):
            return _no_changes_result(context)

        if context.shell is not None:
            result = _recover_review(workspace, model, context, bindings, journal)
        else:
            result = _produce_review(workspace, model, context, bindings, journal)
        _recheck_bindings(workspace, context, bindings)
        _transition_to_ready(workspace, context, journal)
    except _StageFailed as failure:
        return _failure_result(failure, journal)

    return _reviewed_result(result, journal.model_invoked, journal)


def _already_reviewed(context: _Context, bindings: _Bindings) -> bool:
    """Whether the latest review already certifies exactly this input."""
    latest = context.latest_review
    return (
        latest is not None
        and latest.is_current
        and latest.reviews(
            bindings.document_fingerprint,
            bindings.process_iteration,
            bindings.process_output_fingerprint,
        )
        and latest.reviews_tree(bindings.tree_fingerprint)
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


def _failure_result(failure: _StageFailed, journal: _Journal) -> StandardReviewResult:
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
                "The review did not complete. What this run made durable is "
                "listed below and left in place; the details say what a retry "
                "can do."
            ),
            model_invoked=journal.model_invoked,
            created=tuple(journal.created),
            details=(failure.code.value, failure.message, *failure.causes),
        )
    return StandardReviewResult(
        code=failure.code,
        message=failure.message,
        model_invoked=journal.model_invoked,
        created=tuple(journal.created),
        details=failure.causes,
    )


# -- context ----------------------------------------------------------------


def _load_context(
    workspace: RawProcessorWorkspace, entity_id: str, recovering: str | None = None
) -> _Context:
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
    process_results, reviews, shell = _read_children(
        workspace, requirement, root, recovering
    )
    if not process_results:
        raise _StageFailed(
            StandardReviewResultCode.NO_PROCESS_RESULT,
            f"{requirement.requirement_id} has no Process Result; there is "
            "nothing to review against.",
        )
    tree = _read_tree(workspace, requirement, root, "loading the Requirement")
    _require_tree_evidence(requirement, process_results[-1], tree.manifest)

    return _Context(
        requirement=requirement,
        project=project,
        root_document=root,
        root_content=tree.root.body,
        tree=tree,
        process_result=process_results[-1],
        relations=relations,
        existing_standards=tuple(
            record for record in standards if record.id != requirement.id
        ),
        reviews=reviews,
        shell=shell,
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


def _read_tree(
    workspace: RawProcessorWorkspace,
    requirement: RequirementRecord,
    root: DocumentNode,
    stage: str,
) -> NormativeTree:
    """The complete normative tree, or an explicit refusal; never a partial one."""
    try:
        return read_normative_tree(workspace, requirement, root)
    except NormativeTreeError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED
            if error.read_failed
            else StandardReviewResultCode.NORMATIVE_TREE_INVALID,
            f"{error.message} ({stage})",
            error.details,
        ) from error


def _require_tree_evidence(
    requirement: RequirementRecord, process: ProcessResult, current: TreeManifest
) -> None:
    """A review certifies a tree only against a Process Result that produced it.

    A 0.1 Process Result binds no tree, a 0.2 result binds manifest v1 under
    the older fingerprint algorithm, and a current result whose intended
    output is not the current tree describes an input that no longer exists:
    all need Process to run again before anything can be reviewed.
    """
    if not process.is_current:
        raise _StageFailed(
            StandardReviewResultCode.NORMATIVE_TREE_EVIDENCE_REQUIRED,
            f"Process Result {process.iteration} of {requirement.requirement_id} "
            f"is history in an older format (version {process.version}); run "
            "Process to produce current-format evidence before reviewing. "
            "Nothing was written.",
        )
    if process.output_tree.fingerprint != current.fingerprint:
        raise _StageFailed(
            StandardReviewResultCode.NORMATIVE_TREE_EVIDENCE_REQUIRED,
            f"The current normative tree of {requirement.requirement_id} is not "
            f"the intended output of Process Result {process.iteration}; run "
            "Process again before reviewing. Nothing was written.",
            describe_drift(process.output_tree, current),
        )


def _read_children(
    workspace: RawProcessorWorkspace,
    requirement: RequirementRecord,
    root: DocumentNode,
    recovering: str | None = None,
) -> tuple[
    tuple[ProcessResult, ...],
    tuple[tuple[DocumentNode, ReviewResult], ...],
    tuple[DocumentNode, int] | None,
]:
    """Split the Root Document's children into Process and Review history.

    Both capabilities write numbered children under the same Root Document, so
    they are told apart by name. Anything else nested there is neither, and is
    ignored: the reviewer's source material is the Root Document, not whatever
    else happens to sit beneath it. When `recovering` names a child, that
    child must be an empty Review Result shell of this Requirement reserving
    the next iteration; it is returned separately and never parsed as history.
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
    shell: tuple[DocumentNode, int] | None = None
    if recovering is not None:
        _require_named_artifact(children, requirement, recovering)
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
        if recovering is not None and child.id == recovering:
            _check_shell(workspace, child)
            shell = (child, iteration)
            continue
        reviews.append(
            (child, _read_review_result(workspace, child, requirement, iteration))
        )

    process.sort(key=lambda result: result.iteration)
    reviews.sort(key=lambda pair: pair[1].iteration)
    if recovering is not None:
        _check_shell_is_terminal(requirement, recovering, shell, reviews)
    return tuple(process), tuple(reviews), shell


def _require_named_artifact(
    children: list[DocumentNode], requirement: RequirementRecord, recovering: str
) -> None:
    """The named Document must be one of this Requirement's Review Results."""
    named = next((child for child in children if child.id == recovering), None)
    parsed = parse_review_result_name(named.name) if named is not None else None
    if parsed is None or parsed[0] != requirement.requirement_id:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_STATE_CONFLICT,
            f"{recovering!r} is not a Review Result Document of "
            f"{requirement.requirement_id} under its Root Document.",
        )


def _check_shell(workspace: RawProcessorWorkspace, node: DocumentNode) -> None:
    """Fail closed: only a genuinely empty, writable Review Result may be filled."""
    if not node.secret:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"Review Result Document {document_label(node)} exposes no content "
            "secret; it cannot be completed in place.",
        )
    try:
        content = workspace.read_document_content(node.secret)
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            f"Could not read Review Result Document {document_label(node)}.",
            (str(error),),
        ) from error
    if is_empty_body(content):
        return
    try:
        parse_review_result(content)
    except InvalidReviewResult as error:
        raise _StageFailed(
            StandardReviewResultCode.INVALID_REVIEW_RESULT,
            f"Review Result Document {document_label(node)} is not empty and "
            "does not parse; it cannot be recovered over.",
            (str(error),),
        ) from error
    raise _StageFailed(
        StandardReviewResultCode.REVIEW_STATE_CONFLICT,
        f"Review Result Document {document_label(node)} already holds a valid "
        f"result. Run the ordinary operation without {RECOVERY_OPTION}.",
    )


def _check_shell_is_terminal(
    requirement: RequirementRecord,
    recovering: str,
    shell: tuple[DocumentNode, int] | None,
    reviews: list[tuple[DocumentNode, ReviewResult]],
) -> None:
    """The shell must reserve exactly the next review iteration."""
    if shell is None:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_STATE_CONFLICT,
            f"{recovering!r} is not a Review Result Document of "
            f"{requirement.requirement_id} under its Root Document.",
        )
    node, iteration = shell
    expected = reviews[-1][1].iteration + 1 if reviews else FIRST_ITERATION
    if iteration != expected:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_STATE_CONFLICT,
            f"Review Result Document {document_label(node)} reserves iteration "
            f"{iteration}, but only the terminal unfinished iteration "
            f"{expected} can be completed in place.",
        )


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
        if is_empty_body(content):
            raise _StageFailed(
                StandardReviewResultCode.INVALID_REVIEW_RESULT,
                f"Review Result Document {document_label(node)} of "
                f"{requirement.requirement_id} is empty. {recovery_hint(node)}",
            ) from error
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
) -> ReviewResult:
    """Invoke the reviewer once and persist the iteration before mutating."""
    latest = context.latest_review
    iteration = latest.iteration + 1 if latest else FIRST_ITERATION
    result = _build_result(
        context, bindings, iteration, _verify(workspace, model, context, journal)
    )
    _persist_result(workspace, context, result, journal)
    return result


def _recover_review(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    context: _Context,
    bindings: _Bindings,
    journal: _Journal,
) -> ReviewResult:
    """Run the reviewer once and complete the named empty shell in place.

    The earlier response is gone; this is a new review of the current input,
    written into the same Document under its reserved iteration only if fresh
    reads show the Requirement is still in Review with the same Root, and the
    shell is still there, still unique and still empty. The usual binding
    re-check before Ready still follows.
    """
    shell, iteration = context.shell
    result = _build_result(
        context, bindings, iteration, _verify(workspace, model, context, journal)
    )
    _require_still_eligible(workspace, context)
    current = _current_shell(workspace, context, shell, iteration)
    _store_result(workspace, current, result, journal)
    return result


def _require_still_eligible(
    workspace: RawProcessorWorkspace, context: _Context
) -> None:
    """Freshly prove the Requirement is still in Review with the same Root.

    Taken immediately before the recovered body is written. The shell is then
    re-listed under a Root that is known to be current, not merely cached.
    """
    requirement = context.requirement
    try:
        current = workspace.read_requirement(requirement.id)
        attached = workspace.documents_attached_to_requirement(requirement.public_id)
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            f"Could not re-read {requirement.requirement_id} before filling the "
            "empty Review Result; nothing was written.",
            (str(error),),
        ) from error
    drift = eligibility_drift(
        requirement,
        context.root_document,
        current,
        attached,
        STANDARD_TYPE,
        REVIEW_STATE,
    )
    if drift:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_STATE_CONFLICT,
            f"{requirement.requirement_id} changed while the model was running. "
            "The empty Review Result was not filled and nothing else was "
            "written; the change made outside this run stands.",
            drift,
        )


def _verify(
    workspace: RawProcessorWorkspace,
    model: ModelRuntime,
    context: _Context,
    journal: _Journal,
) -> ReviewOutput:
    """One reviewer invocation, validated against the review contract.

    The comparison corpus is read here, once a new invocation is certain,
    and every peer the Process claims refer to must be in it with content.
    """
    prompt, model_context = build_review_prompt(
        requirement=context.requirement,
        project_name=context.project.name,
        root_content=context.root_content,
        child_content=render_descendants(context.tree),
        process_result=context.process_result,
        relations=context.relations,
        comparison=_comparison_context(workspace, context),
    )
    try:
        require_input_within_budget("Standard Review", prompt, model_context)
    except ComparisonContextError as error:
        raise _StageFailed(
            StandardReviewResultCode.COMPARISON_CONTEXT_INCOMPLETE, error.message
        ) from error
    journal.model_invoked = True
    try:
        response = model.run(prompt, model_context)
    except ModelRuntimeError as error:
        raise _StageFailed(
            StandardReviewResultCode.MODEL_RUNTIME_FAILED,
            "The configured local model runtime could not run the review.",
            (str(error),),
        ) from error
    try:
        return parse_review_output(
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


def _build_result(
    context: _Context, bindings: _Bindings, iteration: int, review: ReviewOutput
) -> ReviewResult:
    return build_review_result(
        requirement_id=context.requirement.requirement_id or "",
        iteration=iteration,
        reviewed_document_fingerprint=bindings.document_fingerprint,
        reviewed_process_iteration=bindings.process_iteration,
        reviewed_process_output_fingerprint=bindings.process_output_fingerprint,
        review=review,
        reviewed_tree=context.tree.manifest,
    )


def _comparison_context(
    workspace: RawProcessorWorkspace, context: _Context
) -> ComparisonContext:
    """The peers with content, and proof that every claimed target is among them."""
    try:
        comparison = assemble_comparison_context(
            workspace,
            context.project.id,
            context.requirement.id,
            context.existing_standards,
        )
    except ComparisonContextError as error:
        raise _StageFailed(
            StandardReviewResultCode.COMPARISON_CONTEXT_INCOMPLETE,
            error.message,
            error.details,
        ) from error
    resolvable = comparison.requirement_ids | {context.requirement.requirement_id}
    claimed = {
        finding.requirement_id
        for finding in context.process_result.findings
        if finding.requirement_id
    } | {
        relation.requirement_id
        for relation in context.process_result.proposed_relations
    }
    unresolved = sorted(target for target in claimed if target not in resolvable)
    if unresolved:
        raise _StageFailed(
            StandardReviewResultCode.COMPARISON_CONTEXT_INCOMPLETE,
            "The Process Result names Requirements that are not Standard "
            "Requirements of this Project with a readable Root Document; their "
            "claims cannot be verified against evidence, so the reviewer was not "
            "invoked.",
            tuple(unresolved),
        )
    return comparison


def _read_body(workspace: RawProcessorWorkspace, node: DocumentNode) -> str:
    try:
        return workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            f"Could not read Review Result Document {document_label(node)}.",
            (str(error),),
        ) from error


def _current_shell(
    workspace: RawProcessorWorkspace,
    context: _Context,
    shell: DocumentNode,
    iteration: int,
) -> DocumentNode:
    """Freshly prove the shell is still the unique, empty reserved iteration."""
    requirement = context.requirement
    try:
        children = workspace.child_documents(context.root_document.id)
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.FIBERY_READ_FAILED,
            "Could not re-list the Requirement's child Documents before filling "
            "the empty Review Result.",
            (str(error),),
        ) from error
    same_iteration = [
        child
        for child in children
        if parse_review_result_name(child.name)
        == (requirement.requirement_id, iteration)
    ]
    current = next((child for child in same_iteration if child.id == shell.id), None)
    if current is not None and not is_empty_body(_read_body(workspace, current)):
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_STATE_CONFLICT,
            f"Review Result Document {document_label(shell)} was filled by another "
            "actor while the model was running; refusing to overwrite it.",
        )
    if current is None or len(same_iteration) != 1 or current.name != shell.name:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_STATE_CONFLICT,
            f"Review Result Document {document_label(shell)} is no longer the "
            f"single Review Result reserving iteration {iteration}; nothing was "
            "written.",
        )
    _check_shell(workspace, current)
    return current


def _persist_result(
    workspace: RawProcessorWorkspace,
    context: _Context,
    result: ReviewResult,
    journal: _Journal,
) -> None:
    """Create the iteration's Document, then write and read back its body.

    The creation is journaled as soon as the create call returns an identity,
    separately from the body: a created shell is not a persisted result.
    """
    name = review_result_name(result.requirement_id, result.iteration)
    try:
        node = workspace.create_child_document(name, context.root_document.id)
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"Could not create {name}; nothing durable is known to exist.",
            (str(error),),
        ) from error
    journal.created.append(f"Review Result Document {document_label(node)} created")
    if not node.secret:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"Review Result Document {document_label(node)} exposes no content "
            "secret; its body was not written.",
        )
    _store_result(workspace, node, result, journal)


def _store_result(
    workspace: RawProcessorWorkspace,
    node: DocumentNode,
    result: ReviewResult,
    journal: _Journal,
) -> None:
    """Write the body into an existing Document and prove it stored."""
    try:
        workspace.write_document_content(
            node.secret or "", render_review_result(result)
        )
        stored = workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"The body of Review Result Document {document_label(node)} was not "
            "confirmed stored. A retry reads the Document: a valid body is used "
            f"normally; an empty one needs {RECOVERY_OPTION} {node.id}.",
            (str(error),),
        ) from error
    try:
        read_back = parse_review_result(stored)
    except InvalidReviewResult as error:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"Review Result Document {document_label(node)} does not read back as "
            "valid.",
            (str(error),),
        ) from error
    if read_back.requirement_id != result.requirement_id:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"Review Result Document {document_label(node)} reads back for "
            f"{read_back.requirement_id!r}, not {result.requirement_id!r}; it "
            "was left as found and the Requirement was not moved.",
        )
    if read_back.reviewed_tree != result.reviewed_tree:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"Review Result Document {document_label(node)} reads back bound to a "
            "different normative tree.",
        )
    if read_back.iteration != result.iteration or not read_back.reviews(
        result.reviewed_document_fingerprint,
        result.reviewed_process_iteration,
        result.reviewed_process_output_fingerprint,
    ):
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_WRITE_FAILED,
            f"Review Result Document {document_label(node)} reads back bound to a "
            "different reviewed state.",
        )
    journal.created.append(f"Review Result {document_label(node)} persisted")


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

    process_results, _, _ = _read_children(
        workspace, context.requirement, context.root_document
    )
    if not process_results:
        raise _StageFailed(
            StandardReviewResultCode.REVIEW_RESULT_STALE,
            f"The Process Result {context.requirement.requirement_id} was "
            "reviewed against is gone.",
        )
    latest = process_results[-1]
    tree = _read_tree(
        workspace, context.requirement, context.root_document, "before Ready"
    ).manifest
    current = _Bindings(
        document_fingerprint=document_fingerprint(current_content),
        process_iteration=latest.iteration,
        process_output_fingerprint=latest.output_fingerprint,
        tree_fingerprint=tree.fingerprint,
    )
    if current == bindings and (
        latest.is_current and latest.output_tree.fingerprint == tree.fingerprint
    ):
        return

    raise _StageFailed(
        StandardReviewResultCode.REVIEW_RESULT_STALE,
        f"{context.requirement.requirement_id} changed while it was being "
        "reviewed; the Review Result certifies a state that no longer exists.",
        _describe_drift(bindings, current)
        + tuple(describe_drift(context.tree.manifest, tree)),
    )


def _describe_drift(reviewed: _Bindings, current: _Bindings) -> tuple[str, ...]:
    """Name exactly which binding moved, so the human knows what happened."""
    drift = []
    if reviewed.document_fingerprint != current.document_fingerprint:
        drift.append("The Root Document was edited after the review.")
    elif reviewed.tree_fingerprint != current.tree_fingerprint:
        drift.append("A normative child Document changed after the review.")
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
