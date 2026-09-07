"""`STANDARD Requirement + Ready Decision` — record a human decision, honestly.

Implements Standard-Requirement-Ready-Spec-v0.1. Ready is the boundary where
the system stops deciding and a person does. This capability performs no AI
reasoning and invokes no model: it records an explicit human decision through
one existing workflow transition, after deterministically validating that the
decision applies to the Requirement state that was actually reviewed.

Two decisions exist, and they are deliberately asymmetric:

- **APPROVE** (`Ready -> Apply`) certifies that a human approved *what was
  reviewed*. So before the single State write it re-reads the Root Document
  and the Process history from Fibery and checks all three bindings recorded by
  the latest valid Review Result — document fingerprint, Process iteration and
  Process output fingerprint. Any drift is `REVIEW_RESULT_STALE` with nothing
  mutated. A non-PASS verdict must be acknowledged by name; there is no
  `--force`.
- **REWORK** (`Ready -> Process`) certifies nothing. A stale or badly reviewed
  Requirement is exactly one that ought to go back, so REWORK validates only
  the entry state.

Both write exactly one thing, the workflow State, and confirm it by reading
the entity back. Neither touches the Root Document, any Process Result, any
Review Result, `Revision`, or any relation: the evidence a decision was made
on must outlive the decision unchanged.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    ReadyDecisionWorkspace,
    RequirementRecord,
)
from sdlc.normative_tree import NormativeTreeError, TreeManifest, read_normative_tree
from sdlc.process_result import (
    InvalidProcessResult,
    ProcessResult,
    document_fingerprint,
    parse_process_result,
    parse_process_result_name,
)
from sdlc.results import ReadyDecisionResult, ReadyDecisionResultCode
from sdlc.review_result import (
    InvalidReviewResult,
    ReviewResult,
    parse_review_result,
    parse_review_result_name,
)
from sdlc.standard_review import ReviewSeverity, ReviewVerdict

STANDARD_TYPE = "Standard"
READY_STATE = "Ready"
APPLY_STATE = "Apply"
PROCESS_STATE = "Process"

APPROVE_DECISION = "APPROVE"
REWORK_DECISION = "REWORK"


class _Refused(Exception):
    """The decision could not be recorded. Nothing durable happened."""

    def __init__(
        self,
        code: ReadyDecisionResultCode,
        message: str,
        causes: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.causes = causes


@dataclass(frozen=True)
class _Bindings:
    """Exactly what a Review Result certifies, and what APPROVE re-checks."""

    document_fingerprint: str
    process_iteration: int
    process_output_fingerprint: str
    tree_fingerprint: str


@dataclass(frozen=True)
class _History:
    """The Requirement's current evidence, read fresh from Fibery."""

    root_content: str
    tree: TreeManifest
    latest_process: ProcessResult
    latest_review: ReviewResult

    @property
    def current(self) -> _Bindings:
        return _Bindings(
            document_fingerprint=document_fingerprint(self.root_content),
            process_iteration=self.latest_process.iteration,
            process_output_fingerprint=self.latest_process.output_fingerprint,
            tree_fingerprint=self.tree.fingerprint,
        )

    @property
    def reviewed(self) -> _Bindings:
        review = self.latest_review
        assert review.reviewed_tree is not None  # _require_tree_evidence
        return _Bindings(
            document_fingerprint=review.reviewed_document_fingerprint,
            process_iteration=review.reviewed_process_iteration,
            process_output_fingerprint=review.reviewed_process_output_fingerprint,
            tree_fingerprint=review.reviewed_tree.fingerprint,
        )


# -- the two decisions ------------------------------------------------------


def approve_standard_requirement(
    workspace: ReadyDecisionWorkspace,
    entity_id: str,
    acknowledged_verdict: ReviewVerdict | None = None,
) -> ReadyDecisionResult:
    """Record a human approval: `Ready -> Apply`, only for what was reviewed."""
    requirement: RequirementRecord | None = None
    review: ReviewResult | None = None
    try:
        requirement = _load_requirement(workspace, entity_id)
        if requirement.state == APPLY_STATE:
            return _already_decided(
                requirement,
                ReadyDecisionResultCode.REQUIREMENT_ALREADY_APPROVED,
                APPROVE_DECISION,
                "The approval transition already happened; nothing was changed. "
                "This does not certify that the current content is still what "
                "was reviewed.",
            )
        _require_ready(requirement)
        history = _read_history(workspace, requirement)
        review = history.latest_review
        _check_bindings(requirement, history)
        _check_acknowledgement(review.verdict, acknowledged_verdict)
        _transition(workspace, requirement, APPLY_STATE)
    except _Refused as refusal:
        return _refused_result(refusal, APPROVE_DECISION, requirement, review)

    return ReadyDecisionResult(
        code=ReadyDecisionResultCode.REQUIREMENT_APPROVED,
        message=(
            f"{requirement.requirement_id} approved at Review Result "
            f"{review.iteration} with verdict {review.verdict.value}; "
            f"State is now {APPLY_STATE}."
        ),
        decision=APPROVE_DECISION,
        requirement_id=requirement.requirement_id,
        state=APPLY_STATE,
        **_review_sections(review),
    )


def rework_standard_requirement(
    workspace: ReadyDecisionWorkspace, entity_id: str
) -> ReadyDecisionResult:
    """Record a human rework decision: `Ready -> Process`, certifying nothing."""
    requirement: RequirementRecord | None = None
    try:
        requirement = _load_requirement(workspace, entity_id)
        if requirement.state == PROCESS_STATE:
            return _already_decided(
                requirement,
                ReadyDecisionResultCode.REQUIREMENT_ALREADY_IN_REWORK,
                REWORK_DECISION,
                "The rework transition already happened; nothing was changed "
                "and Process was not run.",
            )
        _require_ready(requirement)
        _transition(workspace, requirement, PROCESS_STATE)
    except _Refused as refusal:
        return _refused_result(refusal, REWORK_DECISION, requirement, None)

    return ReadyDecisionResult(
        code=ReadyDecisionResultCode.REQUIREMENT_SENT_FOR_REWORK,
        message=(
            f"{requirement.requirement_id} sent for rework; State is now "
            f"{PROCESS_STATE}. Previous Process and Review Results are kept as "
            "history."
        ),
        decision=REWORK_DECISION,
        requirement_id=requirement.requirement_id,
        state=PROCESS_STATE,
    )


def _already_decided(
    requirement: RequirementRecord,
    code: ReadyDecisionResultCode,
    decision: str,
    explanation: str,
) -> ReadyDecisionResult:
    """A retry after a lost response. The State says the transition happened.

    It says nothing about why, and nothing about the content: a Requirement a
    human moved by hand looks the same. That is the accepted boundary of using
    State as the decision signal, and the future Apply revalidates anyway.
    """
    return ReadyDecisionResult(
        code=code,
        message=(
            f"{requirement.requirement_id} is already in State "
            f"{requirement.state!r}. {explanation}"
        ),
        decision=decision,
        requirement_id=requirement.requirement_id,
        state=requirement.state,
    )


def _refused_result(
    refusal: _Refused,
    decision: str,
    requirement: RequirementRecord | None,
    review: ReviewResult | None,
) -> ReadyDecisionResult:
    """Nothing was mutated. Show the human what they were deciding about.

    The review sections are included whenever the latest Review Result was
    resolved, so a refusal for a missing acknowledgement is itself the moment
    the human sees the verdict and its findings.
    """
    return ReadyDecisionResult(
        code=refusal.code,
        message=refusal.message,
        decision=decision,
        requirement_id=requirement.requirement_id if requirement else None,
        state=requirement.state if requirement else None,
        details=refusal.causes,
        **(_review_sections(review) if review else {}),
    )


# -- entry ------------------------------------------------------------------


def _load_requirement(
    workspace: ReadyDecisionWorkspace, entity_id: str
) -> RequirementRecord:
    """Read the Requirement and refuse anything this capability does not handle."""
    try:
        requirement = workspace.read_requirement(entity_id)
    except FiberyError as error:
        raise _Refused(
            ReadyDecisionResultCode.FIBERY_READ_FAILED,
            f"Could not read Requirement {entity_id}.",
            (str(error),),
        ) from error
    if requirement is None:
        raise _Refused(
            ReadyDecisionResultCode.REQUIREMENT_NOT_FOUND,
            f"No Requirement with id {entity_id}.",
        )
    if requirement.type_name != STANDARD_TYPE:
        raise _Refused(
            ReadyDecisionResultCode.NOT_A_STANDARD_REQUIREMENT,
            f"{requirement.requirement_id} has Type {requirement.type_name!r}; "
            f"Ready decisions apply only to {STANDARD_TYPE!r}.",
        )
    return requirement


def _require_ready(requirement: RequirementRecord) -> None:
    if requirement.state != READY_STATE:
        raise _Refused(
            ReadyDecisionResultCode.REQUIREMENT_NOT_IN_READY,
            f"{requirement.requirement_id} is in State {requirement.state!r}; "
            f"a decision can be recorded only in {READY_STATE!r}.",
        )


# -- evidence ---------------------------------------------------------------


def _read_history(
    workspace: ReadyDecisionWorkspace, requirement: RequirementRecord
) -> _History:
    """Read the current Root Document and the latest Process and Review Results.

    Everything is re-read from Fibery now. The Process bindings the Review
    Result carries are what was true when the review ran; trusting them would
    make the staleness check circular.
    """
    root = _root_document(workspace, requirement)
    try:
        children = workspace.child_documents(root.id)
    except FiberyError as error:
        raise _Refused(
            ReadyDecisionResultCode.FIBERY_READ_FAILED,
            f"Could not read the evidence of {requirement.requirement_id}.",
            (str(error),),
        ) from error
    try:
        tree = read_normative_tree(workspace, requirement, root)
    except NormativeTreeError as error:
        raise _Refused(
            ReadyDecisionResultCode.FIBERY_READ_FAILED
            if error.read_failed
            else ReadyDecisionResultCode.NORMATIVE_TREE_INVALID,
            error.message,
            error.details,
        ) from error
    root_content = tree.root.body

    process_nodes = _artifacts_by_iteration(
        children,
        requirement,
        parse_process_result_name,
        ReadyDecisionResultCode.INVALID_PROCESS_RESULT,
        "Process Result",
    )
    review_nodes = _artifacts_by_iteration(
        children,
        requirement,
        parse_review_result_name,
        ReadyDecisionResultCode.REVIEW_STATE_CONFLICT,
        "Review Result",
    )
    if not review_nodes:
        raise _Refused(
            ReadyDecisionResultCode.NO_REVIEW_RESULT,
            f"{requirement.requirement_id} has no Review Result; there is "
            "nothing a human could be approving.",
        )
    if not process_nodes:
        raise _Refused(
            ReadyDecisionResultCode.NO_PROCESS_RESULT,
            f"{requirement.requirement_id} has no Process Result; the Review "
            "Result is bound to processing history that does not exist.",
        )
    latest_review_iteration = max(review_nodes)
    latest_process_iteration = max(process_nodes)
    history = _History(
        root_content=root_content,
        tree=tree.manifest,
        latest_review=_read_review_result(
            workspace,
            review_nodes[latest_review_iteration],
            requirement,
            latest_review_iteration,
        ),
        latest_process=_read_process_result(
            workspace,
            process_nodes[latest_process_iteration],
            requirement,
            latest_process_iteration,
        ),
    )
    _require_tree_evidence(requirement, history)
    return history


def _require_tree_evidence(requirement: RequirementRecord, history: _History) -> None:
    """Approval certifies a tree, so only tree-bound, coherent evidence counts.

    Legacy Root-only artifacts stay readable history but prove nothing about
    the children, whether or not the Requirement has any today.
    """
    process, review = history.latest_process, history.latest_review
    if not process.is_tree_bound or not review.is_tree_bound:
        raise _Refused(
            ReadyDecisionResultCode.NORMATIVE_TREE_EVIDENCE_REQUIRED,
            f"{requirement.requirement_id} has only legacy Root-only evidence "
            f"(Process Result {process.iteration} tree-bound: {process.is_tree_bound}, "
            f"Review Result {review.iteration} tree-bound: {review.is_tree_bound}); "
            "approval needs tree-bound Process and Review evidence. Send it for "
            "rework, then run Process and Review. Nothing was written.",
        )


def _root_document(
    workspace: ReadyDecisionWorkspace, requirement: RequirementRecord
) -> DocumentNode:
    try:
        attached = workspace.documents_attached_to_requirement(requirement.public_id)
    except FiberyError as error:
        raise _Refused(
            ReadyDecisionResultCode.FIBERY_READ_FAILED,
            f"Could not read the Documents of {requirement.requirement_id}.",
            (str(error),),
        ) from error
    if len(attached) != 1:
        raise _Refused(
            ReadyDecisionResultCode.PROJECT_STRUCTURE_INVALID,
            f"{requirement.requirement_id} has {len(attached)} attached "
            "Documents; exactly one Root Document is required.",
        )
    return attached[0]


def _artifacts_by_iteration(
    children: list[DocumentNode],
    requirement: RequirementRecord,
    parse_name: Callable[[str], tuple[str, int] | None],
    conflict_code: ReadyDecisionResultCode,
    label: str,
) -> dict[int, DocumentNode]:
    """Index one artifact kind by iteration, refusing an ambiguous history.

    Two artifacts for the same iteration means nobody can say which is the
    record. The latest is never guessed at, and an older one is never used
    instead: the newest artifact is part of current history whatever its state.
    """
    nodes: dict[int, DocumentNode] = {}
    for child in children:
        parsed = parse_name(child.name)
        if parsed is None or parsed[0] != requirement.requirement_id:
            continue
        iteration = parsed[1]
        if iteration in nodes:
            raise _Refused(
                conflict_code,
                f"{requirement.requirement_id} has more than one {label} for "
                f"iteration {iteration}. Refusing to guess which is authoritative.",
                (nodes[iteration].id, child.id),
            )
        nodes[iteration] = child
    return nodes


def _read_review_result(
    workspace: ReadyDecisionWorkspace,
    node: DocumentNode,
    requirement: RequirementRecord,
    iteration: int,
) -> ReviewResult:
    """Read the latest Review Result. It is evidence and is never written to."""
    try:
        content = workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _Refused(
            ReadyDecisionResultCode.FIBERY_READ_FAILED,
            f"Could not read Review Result {iteration}.",
            (str(error),),
        ) from error
    try:
        result = parse_review_result(content)
    except InvalidReviewResult as error:
        raise _Refused(
            ReadyDecisionResultCode.INVALID_REVIEW_RESULT,
            f"Review Result {iteration} of {requirement.requirement_id} cannot "
            "be trusted, and an older one is not used in its place.",
            (str(error),),
        ) from error
    if result.iteration != iteration or result.requirement_id != (
        requirement.requirement_id
    ):
        raise _Refused(
            ReadyDecisionResultCode.INVALID_REVIEW_RESULT,
            f"Review Result {node.name!r} describes "
            f"{result.requirement_id!r} iteration {result.iteration}.",
        )
    return result


def _read_process_result(
    workspace: ReadyDecisionWorkspace,
    node: DocumentNode,
    requirement: RequirementRecord,
    iteration: int,
) -> ProcessResult:
    """Read the latest Process Result. It is evidence and is never written to."""
    try:
        content = workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _Refused(
            ReadyDecisionResultCode.FIBERY_READ_FAILED,
            f"Could not read Process Result {iteration}.",
            (str(error),),
        ) from error
    try:
        result = parse_process_result(content)
    except InvalidProcessResult as error:
        raise _Refused(
            ReadyDecisionResultCode.INVALID_PROCESS_RESULT,
            f"Process Result {iteration} of {requirement.requirement_id} cannot "
            "be trusted.",
            (str(error),),
        ) from error
    if result.iteration != iteration or result.requirement_id != (
        requirement.requirement_id
    ):
        raise _Refused(
            ReadyDecisionResultCode.INVALID_PROCESS_RESULT,
            f"Process Result {node.name!r} describes "
            f"{result.requirement_id!r} iteration {result.iteration}.",
        )
    return result


# -- validation -------------------------------------------------------------


def _check_bindings(requirement: RequirementRecord, history: _History) -> None:
    """The approval must apply to exactly what the latest review certified."""
    if history.current != history.reviewed:
        raise _Refused(
            ReadyDecisionResultCode.REVIEW_RESULT_STALE,
            f"{requirement.requirement_id} no longer matches what Review Result "
            f"{history.latest_review.iteration} reviewed; approving it would "
            "certify content nobody reviewed. Send it for rework instead.",
            _describe_drift(history.reviewed, history.current),
        )
    process, review = history.latest_process, history.latest_review
    if review.reviewed_tree.fingerprint != process.output_tree.fingerprint:
        raise _Refused(
            ReadyDecisionResultCode.NORMATIVE_TREE_EVIDENCE_REQUIRED,
            f"Review Result {review.iteration} of {requirement.requirement_id} does "
            f"not review the intended output tree of Process Result "
            f"{process.iteration}; the evidence is incoherent. Nothing was written.",
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


def _check_acknowledgement(
    verdict: ReviewVerdict, acknowledged: ReviewVerdict | None
) -> None:
    """The human stays the authority, but must name what they are overriding.

    The verdict compared against is the one carried by the same latest Review
    Result whose bindings were just validated. An acknowledgement copied from
    an older or better review therefore cannot approve a newer or worse one.
    """
    if acknowledged is None:
        if verdict is ReviewVerdict.PASS:
            return
        raise _Refused(
            ReadyDecisionResultCode.VERDICT_ACKNOWLEDGEMENT_REQUIRED,
            f"The current Review verdict is {verdict.value}. Approving it "
            f"requires acknowledging that verdict by name: "
            f"--acknowledge-verdict {verdict.value}.",
        )
    if acknowledged is verdict:
        return
    if verdict is ReviewVerdict.PASS:
        raise _Refused(
            ReadyDecisionResultCode.INVALID_VERDICT_ACKNOWLEDGEMENT,
            f"The current Review verdict is PASS, but {acknowledged.value} was "
            "acknowledged. A PASS needs no acknowledgement.",
        )
    raise _Refused(
        ReadyDecisionResultCode.VERDICT_ACKNOWLEDGEMENT_MISMATCH,
        f"The current Review verdict is {verdict.value}, but "
        f"{acknowledged.value} was acknowledged. Re-read the latest Review "
        "Result and acknowledge the verdict it actually derives.",
    )


# -- the single mutation ----------------------------------------------------


def _transition(
    workspace: ReadyDecisionWorkspace, requirement: RequirementRecord, state: str
) -> None:
    """Write the State, then confirm it by independently reading the entity back."""
    try:
        workspace.set_requirement_state(requirement.id, state)
        stored = workspace.read_requirement(requirement.id)
    except FiberyError as error:
        raise _Refused(
            ReadyDecisionResultCode.FIBERY_WRITE_FAILED,
            f"Could not move {requirement.requirement_id} to {state}.",
            (str(error),),
        ) from error

    if stored is None or stored.state != state:
        raise _Refused(
            ReadyDecisionResultCode.VALIDATION_FAILED,
            f"{requirement.requirement_id} is still in State "
            f"{stored.state!r} after the transition to {state}; the decision "
            "was not recorded."
            if stored
            else f"{requirement.requirement_id} could not be read back.",
        )
    if stored.revision != requirement.revision:
        raise _Refused(
            ReadyDecisionResultCode.VALIDATION_FAILED,
            f"Revision changed from {requirement.revision!r} to "
            f"{stored.revision!r}; a Ready decision must not alter it.",
        )


# -- reporting --------------------------------------------------------------


def _review_sections(review: ReviewResult) -> dict[str, object]:
    """What the human was deciding about, none of which was changed."""
    return {
        "iteration": review.iteration,
        "verdict": review.verdict.value,
        "blocking": _severity_lines(review, ReviewSeverity.BLOCKING),
        "warnings": _severity_lines(review, ReviewSeverity.WARNING),
        "relations": tuple(
            f"{verification.kind.value} {verification.requirement_id}: "
            f"{verification.reason}"
            for verification in review.confirmed_relations
        ),
    }


def _severity_lines(review: ReviewResult, severity: ReviewSeverity) -> tuple[str, ...]:
    """Everything the review asserted at one severity, in the Reviewer's words."""
    confirmed = [
        f"confirmed Process finding [{verification.process_finding_index}]: "
        f"{verification.reason}"
        for verification in review.finding_verifications
        if verification.severity is severity
    ]
    discovered = [
        f"{finding.kind.value}"
        + (f" {finding.requirement_id}" if finding.requirement_id else "")
        + f": {finding.detail}"
        for finding in review.new_findings
        if finding.severity is severity
    ]
    return tuple(confirmed + discovered)
