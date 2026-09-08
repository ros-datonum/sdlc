"""`STANDARD Requirement + Apply` — apply what was reviewed and approved.

Implements Standard-Requirement-Apply-Spec-v0.1. Apply is deterministic
execution of an already-approved Requirement: no model, no quality judgement,
no new human decision. It writes exactly three kinds of thing, each verified
by read-back, and writes `Applied` last so the State is a true completion
marker:

- the confirmed relation proposals of the latest valid Review Result, as
  additive `Depends On` / `Affects` edges (Fibery maintains the inverses);
- the Root Document's Folder, from `Requirements/Draft` to
  `Requirements/Approved`, as the same Document entity;
- the workflow State, `Apply -> Applied`.

Two invariants shape the code:

- **nothing normative is written until every predictable check has passed**:
  the reviewed-state binding, the Review Result's agreement with its own
  relation mirror, every relation target, the existing edges and the Root
  Folder are all validated first, and the binding is checked again immediately
  before the first write;
- **the Requirement stays in Apply until every step has succeeded**. A failure
  after the first write is PARTIAL_APPLY naming what became durable; nothing
  is rolled back, and a retry completes only the missing ensure-state steps.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sdlc.fibery_workspace import (
    ApplyWorkspace,
    DocumentNode,
    FiberyError,
    FolderNode,
    ProjectRecord,
    RequirementRecord,
)
from sdlc.normative_tree import (
    NormativeTree,
    NormativeTreeError,
    TreeManifest,
    read_normative_tree,
)
from sdlc.process_result import (
    InvalidProcessResult,
    ProcessResult,
    document_fingerprint,
    parse_process_result,
    parse_process_result_name,
)
from sdlc.project_init import REQUIREMENT_STAGE_FOLDER_NAMES, REQUIREMENTS_FOLDER_NAME
from sdlc.results import ApplyResult, ApplyResultCode
from sdlc.review_result import (
    InvalidReviewResult,
    ReviewResult,
    parse_review_result,
    parse_review_result_name,
    read_confirmed_relation_mirror,
)
from sdlc.standard_analysis import RelationKind
from sdlc.standard_review import VerificationOutcome

STANDARD_TYPE = "Standard"
APPLY_STATE = "Apply"
APPLIED_STATE = "Applied"
DRAFT_FOLDER_NAME = "Draft"
APPROVED_FOLDER_NAME = "Approved"

Edge = tuple[RelationKind, str]


class _StageFailed(Exception):
    """A step could not complete. Whether anything durable happened is the journal's."""

    def __init__(
        self,
        code: ApplyResultCode,
        message: str,
        causes: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.causes = causes


@dataclass
class _Journal:
    """Normative steps this run made durable, in order."""

    created: list[str] = field(default_factory=list)

    @property
    def has_durable_state(self) -> bool:
        return bool(self.created)


@dataclass(frozen=True)
class _Bindings:
    """Exactly what the Review Result certifies, and what Apply re-checks."""

    document_fingerprint: str
    process_iteration: int
    process_output_fingerprint: str
    tree_fingerprint: str


@dataclass(frozen=True)
class _Structure:
    """The Requirement's Project, Root Document and stage Folders."""

    project: ProjectRecord
    root: DocumentNode
    draft_folder_id: str
    approved_folder_id: str


@dataclass(frozen=True)
class _Evidence:
    """The latest artifacts and the current Root content, read fresh."""

    root_content: str
    tree: TreeManifest
    latest_review: ReviewResult
    latest_process: ProcessResult
    confirmed: tuple[Edge, ...]

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


@dataclass(frozen=True)
class _Plan:
    """Everything decided before the first write."""

    targets: dict[Edge, RequirementRecord]
    present: tuple[Edge, ...]
    missing: tuple[Edge, ...]
    root_in_approved: bool


def apply_standard_requirement(
    workspace: ApplyWorkspace, entity_id: str
) -> ApplyResult:
    """Apply one approved Standard Requirement in Apply."""
    journal = _Journal()
    requirement: RequirementRecord | None = None
    try:
        requirement = _load_requirement(workspace, entity_id)
        if requirement.state == APPLIED_STATE:
            return _already_applied(requirement)
        _require_apply(requirement)

        structure = _resolve_structure(workspace, requirement)
        evidence = _read_evidence(workspace, requirement, structure.root)
        _check_bindings(requirement, evidence)
        plan = _plan(workspace, requirement, structure, evidence)
        # Immediately before the first write, never on state read earlier.
        _recheck_bindings(workspace, requirement, structure.root, evidence)

        _ensure_edges(workspace, requirement, plan, journal)
        _ensure_root_folder(workspace, requirement, structure, plan, journal)
        _recheck_bindings(workspace, requirement, structure.root, evidence)
        _transition_to_applied(workspace, requirement, journal)
    except _StageFailed as failure:
        return _failure_result(failure, requirement, journal)

    return ApplyResult(
        code=ApplyResultCode.REQUIREMENT_APPLIED,
        message=(
            f"{requirement.requirement_id} applied from Review Result "
            f"{evidence.latest_review.iteration}; State is now {APPLIED_STATE}."
        ),
        requirement_id=requirement.requirement_id,
        state=APPLIED_STATE,
        relations_added=tuple(_describe(edge) for edge in plan.missing),
        relations_present=tuple(_describe(edge) for edge in plan.present),
        root_folder=APPROVED_FOLDER_NAME,
        created=tuple(journal.created),
    )


def _already_applied(requirement: RequirementRecord) -> ApplyResult:
    """A retry after a completed application, or a manual Applied.

    State cannot tell the two apart and nothing here validates the manual
    case, so the message claims only what the State proves.
    """
    return ApplyResult(
        code=ApplyResultCode.REQUIREMENT_ALREADY_APPLIED,
        message=(
            f"{requirement.requirement_id} is already in State "
            f"{APPLIED_STATE!r}; nothing was changed. This reports the recorded "
            "State only, not that every Apply invariant holds."
        ),
        requirement_id=requirement.requirement_id,
        state=requirement.state,
    )


def _failure_result(
    failure: _StageFailed, requirement: RequirementRecord | None, journal: _Journal
) -> ApplyResult:
    """Durable normative state means PARTIAL_APPLY; a retry resumes it."""
    if journal.has_durable_state:
        return ApplyResult(
            code=ApplyResultCode.PARTIAL_APPLY,
            message=(
                "The application did not complete; the Requirement stays in "
                f"{APPLY_STATE} and the steps listed below are left in place. "
                "A retry completes only what is missing."
            ),
            requirement_id=requirement.requirement_id if requirement else None,
            state=requirement.state if requirement else None,
            created=tuple(journal.created),
            details=(failure.code.value, failure.message, *failure.causes),
        )
    return ApplyResult(
        code=failure.code,
        message=failure.message,
        requirement_id=requirement.requirement_id if requirement else None,
        state=requirement.state if requirement else None,
        details=failure.causes,
    )


def _describe(edge: Edge) -> str:
    return f"{edge[0].value} {edge[1]}"


# -- entry ------------------------------------------------------------------


def _load_requirement(workspace: ApplyWorkspace, entity_id: str) -> RequirementRecord:
    try:
        requirement = workspace.read_requirement(entity_id)
    except FiberyError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_READ_FAILED,
            f"Could not read Requirement {entity_id}.",
            (str(error),),
        ) from error
    if requirement is None:
        raise _StageFailed(
            ApplyResultCode.REQUIREMENT_NOT_FOUND,
            f"No Requirement with id {entity_id}.",
        )
    if requirement.type_name != STANDARD_TYPE:
        raise _StageFailed(
            ApplyResultCode.NOT_A_STANDARD_REQUIREMENT,
            f"{requirement.requirement_id} has Type {requirement.type_name!r}; "
            f"Apply handles only {STANDARD_TYPE!r}.",
        )
    return requirement


def _require_apply(requirement: RequirementRecord) -> None:
    if requirement.state != APPLY_STATE:
        raise _StageFailed(
            ApplyResultCode.REQUIREMENT_NOT_IN_APPLY,
            f"{requirement.requirement_id} is in State {requirement.state!r}; "
            f"Apply handles only {APPLY_STATE!r}.",
        )


# -- structure --------------------------------------------------------------


def _resolve_structure(
    workspace: ApplyWorkspace, requirement: RequirementRecord
) -> _Structure:
    """The Project, its Draft and Approved Folders, and the one Root Document."""
    try:
        project = workspace.read_project(requirement.project_id or "")
        attached = workspace.documents_attached_to_requirement(requirement.public_id)
    except FiberyError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_READ_FAILED,
            f"Could not read the structure of {requirement.requirement_id}.",
            (str(error),),
        ) from error
    if project is None:
        raise _StageFailed(
            ApplyResultCode.PROJECT_STRUCTURE_INVALID,
            f"{requirement.requirement_id} has no resolvable Project.",
        )
    if len(attached) != 1:
        raise _StageFailed(
            ApplyResultCode.PROJECT_STRUCTURE_INVALID,
            f"{requirement.requirement_id} has {len(attached)} attached "
            "Documents; exactly one Root Document is required.",
        )
    draft, approved = _stage_folders(workspace, project)
    return _Structure(
        project=project,
        root=attached[0],
        draft_folder_id=draft.id,
        approved_folder_id=approved.id,
    )


def _stage_folders(
    workspace: ApplyWorkspace, project: ProjectRecord
) -> tuple[FolderNode, FolderNode]:
    """Resolve `<Project>/Requirements/{Draft,Approved}` by real Folder ids.

    The same single-child rule the frozen RAW Processor applies: a name that
    resolves to zero or several Folders is a structure the capability cannot
    act on.
    """
    root_id = project.documents_root_folder_id
    if not root_id:
        raise _StageFailed(
            ApplyResultCode.PROJECT_STRUCTURE_INVALID,
            f"Project {project.name!r} has no Documents Root Folder ID.",
        )
    try:
        root = workspace.resolve_folder(root_id)
        if root is None:
            raise _StageFailed(
                ApplyResultCode.PROJECT_STRUCTURE_INVALID,
                f"Documents Root Folder ID {root_id!r} does not resolve.",
            )
        requirements = _single_child(workspace, root.id, REQUIREMENTS_FOLDER_NAME)
        stages = {
            name: _single_child(workspace, requirements.id, name)
            for name in REQUIREMENT_STAGE_FOLDER_NAMES
        }
    except FiberyError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_READ_FAILED,
            "Could not read the Project folder structure.",
            (str(error),),
        ) from error
    return stages[DRAFT_FOLDER_NAME], stages[APPROVED_FOLDER_NAME]


def _single_child(workspace: ApplyWorkspace, parent_id: str, name: str) -> FolderNode:
    matches = [f for f in workspace.child_folders(parent_id) if f.name == name]
    if len(matches) != 1:
        raise _StageFailed(
            ApplyResultCode.PROJECT_STRUCTURE_INVALID,
            f"Expected exactly one {name!r} folder, found {len(matches)}.",
        )
    return matches[0]


# -- evidence ---------------------------------------------------------------


def _read_evidence(
    workspace: ApplyWorkspace, requirement: RequirementRecord, root: DocumentNode
) -> _Evidence:
    """The latest Review and Process Results and the current Root content.

    Everything is read from Fibery now; the Process bindings the Review Result
    carries are what was true when the review ran, and are never trusted.
    """
    try:
        children = workspace.child_documents(root.id)
    except FiberyError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_READ_FAILED,
            f"Could not read the evidence of {requirement.requirement_id}.",
            (str(error),),
        ) from error
    tree = _read_tree(workspace, requirement, root)
    root_content = tree.root.body
    review_node = _latest_artifact(
        children,
        requirement,
        parse_review_result_name,
        ApplyResultCode.REVIEW_STATE_CONFLICT,
        "Review Result",
    )
    if review_node is None:
        raise _StageFailed(
            ApplyResultCode.NO_REVIEW_RESULT,
            f"{requirement.requirement_id} has no Review Result; there is "
            "nothing approved to apply.",
        )
    process_node = _latest_artifact(
        children,
        requirement,
        parse_process_result_name,
        ApplyResultCode.INVALID_PROCESS_RESULT,
        "Process Result",
    )
    if process_node is None:
        raise _StageFailed(
            ApplyResultCode.NO_PROCESS_RESULT,
            f"{requirement.requirement_id} has no Process Result; the Review "
            "Result is bound to processing history that does not exist.",
        )
    review, confirmed = _read_review_result(workspace, requirement, *review_node)
    process = _read_process_result(workspace, requirement, *process_node)
    evidence = _Evidence(
        root_content=root_content,
        tree=tree.manifest,
        latest_review=review,
        latest_process=process,
        confirmed=confirmed,
    )
    _require_tree_evidence(requirement, evidence)
    return evidence


def _read_tree(
    workspace: ApplyWorkspace, requirement: RequirementRecord, root: DocumentNode
) -> NormativeTree:
    try:
        return read_normative_tree(workspace, requirement, root)
    except NormativeTreeError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_READ_FAILED
            if error.read_failed
            else ApplyResultCode.NORMATIVE_TREE_INVALID,
            error.message,
            error.details,
        ) from error


def _require_tree_evidence(requirement: RequirementRecord, evidence: _Evidence) -> None:
    """Only current-format, coherent evidence may be applied; older is history."""
    process, review = evidence.latest_process, evidence.latest_review
    if not process.is_current or not review.is_current:
        raise _StageFailed(
            ApplyResultCode.NORMATIVE_TREE_EVIDENCE_REQUIRED,
            f"{requirement.requirement_id} has only older-format evidence "
            f"(Process Result {process.iteration} version {process.version}, "
            f"Review Result {review.iteration} version {review.version}); "
            "application needs current-format Process and Review evidence. "
            "Nothing was written.",
        )


def _latest_artifact(
    children: list[DocumentNode],
    requirement: RequirementRecord,
    parse_name: Callable[[str], tuple[str, int] | None],
    conflict_code: ApplyResultCode,
    label: str,
) -> tuple[DocumentNode, int] | None:
    """The newest artifact of one kind, refusing an ambiguous history.

    The newest artifact is current history whatever its state; an older one
    is never used in its place.
    """
    nodes: dict[int, DocumentNode] = {}
    for child in children:
        parsed = parse_name(child.name)
        if parsed is None or parsed[0] != requirement.requirement_id:
            continue
        iteration = parsed[1]
        if iteration in nodes:
            raise _StageFailed(
                conflict_code,
                f"{requirement.requirement_id} has more than one {label} for "
                f"iteration {iteration}. Refusing to guess which is authoritative.",
                (nodes[iteration].id, child.id),
            )
        nodes[iteration] = child
    if not nodes:
        return None
    latest = max(nodes)
    return nodes[latest], latest


def _read_review_result(
    workspace: ApplyWorkspace,
    requirement: RequirementRecord,
    node: DocumentNode,
    iteration: int,
) -> tuple[ReviewResult, tuple[Edge, ...]]:
    """Parse the latest Review Result and its normative confirmed edge set."""
    try:
        content = workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_READ_FAILED,
            f"Could not read Review Result {iteration}.",
            (str(error),),
        ) from error
    try:
        result = parse_review_result(content)
        mirror = read_confirmed_relation_mirror(content)
    except InvalidReviewResult as error:
        raise _StageFailed(
            ApplyResultCode.INVALID_REVIEW_RESULT,
            f"Review Result {iteration} of {requirement.requirement_id} cannot "
            "be applied, and an older one is not used in its place.",
            (str(error),),
        ) from error
    if result.iteration != iteration or result.requirement_id != (
        requirement.requirement_id
    ):
        raise _StageFailed(
            ApplyResultCode.INVALID_REVIEW_RESULT,
            f"Review Result {node.name!r} describes "
            f"{result.requirement_id!r} iteration {result.iteration}.",
        )
    return result, _confirmed_edges(requirement, result, mirror)


def _confirmed_edges(
    requirement: RequirementRecord, result: ReviewResult, mirror: tuple[Edge, ...]
) -> tuple[Edge, ...]:
    """The normative set: CONFIRMED verifications, agreeing with the mirror.

    Apply is the first consumer that acts on these values, so an artifact
    whose two representations disagree, or that names one logical edge twice,
    is refused rather than reconciled.
    """
    derived = [
        (verification.kind, verification.requirement_id)
        for verification in result.relation_verifications
        if verification.outcome is VerificationOutcome.CONFIRMED
    ]
    for label, edges in (
        ("relation_proposal_verifications", derived),
        ("confirmed_relation_proposals", mirror),
    ):
        duplicates = sorted({_describe(e) for e in edges if edges.count(e) > 1})
        if duplicates:
            raise _StageFailed(
                ApplyResultCode.INVALID_REVIEW_RESULT,
                f"Review Result {result.iteration} of {requirement.requirement_id} "
                f"confirms the same edge more than once in {label}: "
                + ", ".join(duplicates),
            )
    if set(derived) != set(mirror):
        only_derived = sorted(_describe(e) for e in set(derived) - set(mirror))
        only_mirror = sorted(_describe(e) for e in set(mirror) - set(derived))
        raise _StageFailed(
            ApplyResultCode.INVALID_REVIEW_RESULT,
            f"Review Result {result.iteration} of {requirement.requirement_id} "
            "disagrees with itself about the confirmed relations.",
            (
                *(f"confirmed by verification only: {e}" for e in only_derived),
                *(f"listed in the mirror only: {e}" for e in only_mirror),
            ),
        )
    return tuple(derived)


def _read_process_result(
    workspace: ApplyWorkspace,
    requirement: RequirementRecord,
    node: DocumentNode,
    iteration: int,
) -> ProcessResult:
    try:
        content = workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_READ_FAILED,
            f"Could not read Process Result {iteration}.",
            (str(error),),
        ) from error
    try:
        result = parse_process_result(content)
    except InvalidProcessResult as error:
        raise _StageFailed(
            ApplyResultCode.INVALID_PROCESS_RESULT,
            f"Process Result {iteration} of {requirement.requirement_id} cannot "
            "be trusted.",
            (str(error),),
        ) from error
    if result.iteration != iteration or result.requirement_id != (
        requirement.requirement_id
    ):
        raise _StageFailed(
            ApplyResultCode.INVALID_PROCESS_RESULT,
            f"Process Result {node.name!r} describes "
            f"{result.requirement_id!r} iteration {result.iteration}.",
        )
    return result


# -- validation -------------------------------------------------------------


def _check_bindings(requirement: RequirementRecord, evidence: _Evidence) -> None:
    """The application must apply to exactly what the latest review certified."""
    if evidence.current != evidence.reviewed:
        raise _StageFailed(
            ApplyResultCode.REVIEW_RESULT_STALE,
            f"{requirement.requirement_id} no longer matches what Review Result "
            f"{evidence.latest_review.iteration} reviewed; applying it would "
            "make content nobody reviewed canonical.",
            _describe_drift(evidence.reviewed, evidence.current),
        )
    process, review = evidence.latest_process, evidence.latest_review
    if review.reviewed_tree.fingerprint != process.output_tree.fingerprint:
        raise _StageFailed(
            ApplyResultCode.NORMATIVE_TREE_EVIDENCE_REQUIRED,
            f"Review Result {review.iteration} of {requirement.requirement_id} does "
            f"not review the intended output tree of Process Result "
            f"{process.iteration}; the evidence is incoherent. Nothing was written.",
        )


def _recheck_bindings(
    workspace: ApplyWorkspace,
    requirement: RequirementRecord,
    root: DocumentNode,
    evidence: _Evidence,
) -> None:
    """Re-read the Root Document and the Process history, and compare again.

    Called immediately before the first write and again immediately before
    Applied. The Review Result under application stays the one validated at
    the start: the question is whether reality still matches it.
    """
    try:
        children = workspace.child_documents(root.id)
    except FiberyError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_READ_FAILED,
            "Could not re-read the Requirement before a normative write.",
            (str(error),),
        ) from error
    tree = _read_tree(workspace, requirement, root)
    current_content = tree.root.body
    process_node = _latest_artifact(
        children,
        requirement,
        parse_process_result_name,
        ApplyResultCode.INVALID_PROCESS_RESULT,
        "Process Result",
    )
    if process_node is None:
        raise _StageFailed(
            ApplyResultCode.REVIEW_RESULT_STALE,
            f"The Process Result {requirement.requirement_id} was reviewed "
            "against is gone.",
        )
    process = _read_process_result(workspace, requirement, *process_node)
    _check_bindings(
        requirement,
        _Evidence(
            root_content=current_content,
            tree=tree.manifest,
            latest_review=evidence.latest_review,
            latest_process=process,
            confirmed=evidence.confirmed,
        ),
    )


def _describe_drift(reviewed: _Bindings, current: _Bindings) -> tuple[str, ...]:
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


# -- planning: everything decided before the first write -------------------


def _plan(
    workspace: ApplyWorkspace,
    requirement: RequirementRecord,
    structure: _Structure,
    evidence: _Evidence,
) -> _Plan:
    targets = _preflight_targets(workspace, requirement, evidence.confirmed)
    present, missing = _partition_edges(workspace, requirement, evidence.confirmed)
    return _Plan(
        targets=targets,
        present=present,
        missing=missing,
        root_in_approved=_root_in_approved(requirement, structure),
    )


def _preflight_targets(
    workspace: ApplyWorkspace,
    requirement: RequirementRecord,
    confirmed: tuple[Edge, ...],
) -> dict[Edge, RequirementRecord]:
    """Resolve every target before any edge is written.

    A target is an identity: it must resolve to exactly one Standard
    Requirement of the same Project that is not the source. Its workflow
    State is deliberately unrestricted.
    """
    targets: dict[Edge, RequirementRecord] = {}
    for edge in confirmed:
        kind, target_id = edge
        if target_id == requirement.requirement_id:
            raise _StageFailed(
                ApplyResultCode.INVALID_RELATION_TARGET,
                f"{requirement.requirement_id} cannot {kind.value} itself.",
            )
        try:
            matches = workspace.find_requirements_by_requirement_id(target_id)
        except FiberyError as error:
            raise _StageFailed(
                ApplyResultCode.FIBERY_READ_FAILED,
                f"Could not resolve relation target {target_id}.",
                (str(error),),
            ) from error
        targets[edge] = _validate_target(requirement, kind, target_id, matches)
    return targets


def _validate_target(
    requirement: RequirementRecord,
    kind: RelationKind,
    target_id: str,
    matches: list[RequirementRecord],
) -> RequirementRecord:
    if not matches:
        raise _StageFailed(
            ApplyResultCode.RELATION_TARGET_NOT_FOUND,
            f"Confirmed relation {kind.value} {target_id} names a Requirement "
            "that does not exist.",
        )
    if len(matches) > 1:
        raise _StageFailed(
            ApplyResultCode.INVALID_RELATION_TARGET,
            f"Requirement ID {target_id} resolves to more than one Requirement; "
            "refusing to guess which one the review meant.",
            tuple(match.id for match in matches),
        )
    target = matches[0]
    if target.id == requirement.id:
        raise _StageFailed(
            ApplyResultCode.INVALID_RELATION_TARGET,
            f"{requirement.requirement_id} cannot {kind.value} itself.",
        )
    if target.type_name != STANDARD_TYPE:
        raise _StageFailed(
            ApplyResultCode.INVALID_RELATION_TARGET,
            f"Relation target {target_id} has Type {target.type_name!r}; only "
            f"{STANDARD_TYPE!r} Requirements may be related.",
        )
    if target.project_id != requirement.project_id:
        raise _StageFailed(
            ApplyResultCode.INVALID_RELATION_TARGET,
            f"Relation target {target_id} belongs to another Project.",
        )
    return target


def _partition_edges(
    workspace: ApplyWorkspace,
    requirement: RequirementRecord,
    confirmed: tuple[Edge, ...],
) -> tuple[tuple[Edge, ...], tuple[Edge, ...]]:
    """Which confirmed edges already exist, and which must be written."""
    existing = _existing_edges(workspace, requirement)
    present = tuple(edge for edge in confirmed if edge in existing)
    missing = tuple(edge for edge in confirmed if edge not in existing)
    return present, missing


def _existing_edges(
    workspace: ApplyWorkspace, requirement: RequirementRecord
) -> set[Edge]:
    try:
        relations = workspace.requirement_relations(requirement.id)
    except FiberyError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_READ_FAILED,
            f"Could not read the relations of {requirement.requirement_id}.",
            (str(error),),
        ) from error
    return {(RelationKind.DEPENDS_ON, target) for target in relations.depends_on} | {
        (RelationKind.AFFECTS, target) for target in relations.affects
    }


def _root_in_approved(requirement: RequirementRecord, structure: _Structure) -> bool:
    """Draft means move; Approved means already done; anything else is refused."""
    folder_id = structure.root.folder_id
    if folder_id == structure.approved_folder_id:
        return True
    if folder_id == structure.draft_folder_id:
        return False
    raise _StageFailed(
        ApplyResultCode.PROJECT_STRUCTURE_INVALID,
        f"The Root Document of {requirement.requirement_id} is in Folder "
        f"{folder_id!r}, neither {DRAFT_FOLDER_NAME} nor {APPROVED_FOLDER_NAME}; "
        "refusing to move a Document from an unexpected location.",
    )


# -- normative writes -------------------------------------------------------


def _ensure_edges(
    workspace: ApplyWorkspace,
    requirement: RequirementRecord,
    plan: _Plan,
    journal: _Journal,
) -> None:
    """Write each missing confirmed edge once, then prove all of them exist."""
    for edge in plan.missing:
        kind, _ = edge
        target = plan.targets[edge]
        try:
            if kind is RelationKind.DEPENDS_ON:
                workspace.add_depends_on(requirement.id, target.id)
            else:
                workspace.add_affects(requirement.id, target.id)
        except FiberyError as error:
            raise _StageFailed(
                ApplyResultCode.FIBERY_WRITE_FAILED,
                f"Could not add {_describe(edge)} to {requirement.requirement_id}.",
                (str(error),),
            ) from error
        journal.created.append(f"relation {_describe(edge)}")
        if edge not in _existing_edges(workspace, requirement):
            raise _StageFailed(
                ApplyResultCode.VALIDATION_FAILED,
                f"{_describe(edge)} does not read back on "
                f"{requirement.requirement_id} after being added.",
            )


def _ensure_root_folder(
    workspace: ApplyWorkspace,
    requirement: RequirementRecord,
    structure: _Structure,
    plan: _Plan,
    journal: _Journal,
) -> None:
    """Move the same Root Document to Approved, and prove it moved intact."""
    if plan.root_in_approved:
        return
    root = structure.root
    try:
        children_before = {child.id for child in workspace.child_documents(root.id)}
        workspace.set_document_folder(root.id, structure.approved_folder_id)
        stored = workspace.resolve_document(root.id)
        children_after = {child.id for child in workspace.child_documents(root.id)}
    except FiberyError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_WRITE_FAILED,
            f"Could not move the Root Document of {requirement.requirement_id} "
            f"to {APPROVED_FOLDER_NAME}.",
            (str(error),),
        ) from error
    if stored is None or stored.folder_id != structure.approved_folder_id:
        raise _StageFailed(
            ApplyResultCode.VALIDATION_FAILED,
            f"The Root Document of {requirement.requirement_id} does not read "
            f"back under {APPROVED_FOLDER_NAME}.",
        )
    if stored.secret != root.secret or children_after != children_before:
        raise _StageFailed(
            ApplyResultCode.VALIDATION_FAILED,
            f"The Root Document of {requirement.requirement_id} changed identity "
            "or lost nested Documents while moving.",
        )
    journal.created.append(f"Root Document Folder = {APPROVED_FOLDER_NAME}")


def _transition_to_applied(
    workspace: ApplyWorkspace, requirement: RequirementRecord, journal: _Journal
) -> None:
    """Write Applied last, and confirm it by reading the entity back."""
    try:
        workspace.set_requirement_state(requirement.id, APPLIED_STATE)
        stored = workspace.read_requirement(requirement.id)
    except FiberyError as error:
        raise _StageFailed(
            ApplyResultCode.FIBERY_WRITE_FAILED,
            f"Could not move {requirement.requirement_id} to {APPLIED_STATE}.",
            (str(error),),
        ) from error
    if stored is None or stored.state != APPLIED_STATE:
        raise _StageFailed(
            ApplyResultCode.VALIDATION_FAILED,
            f"{requirement.requirement_id} is still in State "
            f"{stored.state!r} after the transition to {APPLIED_STATE}."
            if stored
            else f"{requirement.requirement_id} could not be read back.",
        )
    if stored.revision != requirement.revision:
        raise _StageFailed(
            ApplyResultCode.VALIDATION_FAILED,
            f"Revision changed from {requirement.revision!r} to "
            f"{stored.revision!r}; Apply must not alter it.",
        )
    journal.created.append(f"State = {APPLIED_STATE}")
