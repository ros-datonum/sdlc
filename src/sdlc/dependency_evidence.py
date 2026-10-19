"""Normative dependency evidence: interpretation sets, bindings, currentness.

Implements Requirement-Dependency-Bindings-v0.1. A Standard Requirement R
DEPENDS_ON D when understanding or evaluating an obligation of R needs a
definition, rule, constraint or behaviour that D owns; R is interpreted with
its whole transitive DEPENDS_ON closure, its interpretation set. AFFECTS is
change impact and never enters it.

Every member of an interpretation set is read fresh from Fibery and must be
admissible authority: exactly one Standard Requirement of the same Project,
a valid normative tree, and a dependency-bound (0.6) Review Result that is
current for that tree and its latest Process Result and derives WHAT CLEAR.
A member's own DEPENDS_ON edges are followed through what its Review bound,
and its edges in Fibery must agree with that. Anything else is refused, never
skipped, and a cycle anywhere in the set is refused.

The reviewer stage binds the set to the versions it read; Ready, Apply and
TSA admission recompute it from current Fibery state and refuse when it no
longer matches. Fingerprints detect change; they are not signatures.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sdlc.comparison_context import COMPARISON_RECORD_LIMIT
from sdlc.fibery_workspace import (
    DocumentNode,
    FiberyError,
    RequirementRecord,
    RequirementRelations,
)
from sdlc.normative_tree import (
    NormativeTreeError,
    document_fingerprint,
    read_normative_tree,
)
from sdlc.process_result import (
    InvalidProcessResult,
    ProcessResult,
    parse_process_result,
    parse_process_result_name,
)
from sdlc.review_result import (
    DependencyBinding,
    DependencyOrigin,
    InvalidReviewResult,
    ReviewResult,
    parse_review_result,
    parse_review_result_name,
    what_clearance,
)
from sdlc.standard_review import WhatStatus

STANDARD_TYPE = "Standard"
APPLIED_STATE = "Applied"
#: The interpretation set is bounded like the comparison corpus it lives in.
INTERPRETATION_SET_LIMIT = COMPARISON_RECORD_LIMIT


class DependencyFailure(StrEnum):
    """Why dependency evidence does not hold. Consumers map it to their codes."""

    # A member is missing, ambiguous, foreign, or lacks admissible evidence.
    INVALID = "INVALID"
    # The DEPENDS_ON graph has a cycle, or the Requirement depends on itself.
    CYCLE = "CYCLE"
    # Bound evidence no longer matches current Fibery state.
    STALE = "STALE"
    # A direct dependency is not Applied, so it is not yet approved authority.
    NOT_APPLIED = "NOT_APPLIED"
    # Fibery could not be read; nothing is known either way.
    READ_FAILED = "READ_FAILED"


class DependencyEvidenceError(Exception):
    """Dependency evidence cannot be established; nothing may act on it."""

    def __init__(
        self, failure: DependencyFailure, message: str, details: tuple[str, ...] = ()
    ) -> None:
        super().__init__(message)
        self.failure = failure
        self.message = message
        self.details = details


class DependencyWorkspace(Protocol):
    """The reads dependency evidence needs. It has no write method."""

    def find_requirements_by_requirement_id(
        self, requirement_id: str
    ) -> list[RequirementRecord]:
        """Every Requirement carrying this Requirement ID, bounded to two."""

    def documents_attached_to_requirement(self, public_id: str) -> list[DocumentNode]:
        """Documents attached to this Requirement entity."""

    def child_documents(self, parent_document_id: str) -> list[DocumentNode]:
        """Documents nested directly under this Document."""

    def read_document_content(self, secret: str) -> str:
        """Read a Document's Markdown content."""

    def requirement_relations(self, entity_id: str) -> RequirementRelations:
        """The Depends On and Affects edges this Requirement already has."""


class Phase(StrEnum):
    """Which DEPENDS_ON edges of the reviewed Requirement must exist now."""

    # Ready: exactly the edges it had when reviewed; nothing applied yet.
    REVIEWED = "REVIEWED"
    # Apply, before and between writes: the reviewed edges, plus any
    # confirmed proposal a partial earlier Apply already wrote.
    APPLYING = "APPLYING"
    # Apply after its writes, and TSA admission: exactly the bound edges.
    APPLIED = "APPLIED"


@dataclass(frozen=True)
class DependencyMember:
    """One member of an interpretation set, as read now."""

    record: RequirementRecord
    tree_fingerprint: str
    review: ReviewResult
    review_digest: str

    @property
    def requirement_id(self) -> str:
        return self.record.requirement_id or ""

    @property
    def direct_ids(self) -> tuple[str, ...]:
        return tuple(
            binding.requirement_id
            for binding in self.review.dependency_bindings
            if binding.is_direct
        )

    def binding(self, origin: DependencyOrigin) -> DependencyBinding:
        return DependencyBinding(
            requirement_id=self.requirement_id,
            entity_id=self.record.id,
            origin=origin,
            tree_fingerprint=self.tree_fingerprint,
            review_iteration=self.review.iteration,
            review_digest=self.review_digest,
        )


def resolve_interpretation_set(
    workspace: DependencyWorkspace,
    requirement: RequirementRecord,
    direct_ids: Iterable[str],
) -> dict[str, DependencyMember]:
    """Every member reachable from `direct_ids`, validated, or a refusal.

    Depth-first along each member's bound direct dependencies. Reaching the
    Requirement itself, or a member already on the path, is a cycle.
    """
    members: dict[str, DependencyMember] = {}
    for requirement_id in sorted(set(direct_ids)):
        _visit(workspace, requirement, requirement_id, (), members)
    _require_members_current(members)
    return members


def _visit(
    workspace: DependencyWorkspace,
    requirement: RequirementRecord,
    requirement_id: str,
    path: tuple[str, ...],
    members: dict[str, DependencyMember],
) -> None:
    if requirement_id == requirement.requirement_id or requirement_id in path:
        cycle = " -> ".join((requirement.requirement_id or "", *path, requirement_id))
        raise DependencyEvidenceError(
            DependencyFailure.CYCLE,
            f"The DEPENDS_ON graph of {requirement.requirement_id} has a cycle: "
            f"{cycle}. A Requirement cannot depend on itself, directly or not.",
            (cycle,),
        )
    if requirement_id in members:
        return
    if len(members) >= INTERPRETATION_SET_LIMIT:
        raise DependencyEvidenceError(
            DependencyFailure.INVALID,
            f"The interpretation set of {requirement.requirement_id} exceeds "
            f"{INTERPRETATION_SET_LIMIT} Requirements; it was refused, not cut.",
        )
    member = _read_member(workspace, requirement, requirement_id)
    members[requirement_id] = member
    for dependency in member.direct_ids:
        _visit(workspace, requirement, dependency, (*path, requirement_id), members)


def _require_members_current(members: Mapping[str, DependencyMember]) -> None:
    """Each member's own bindings must still describe the members read now."""
    for member in members.values():
        for bound in member.review.dependency_bindings:
            current = members.get(bound.requirement_id)
            if current is None or bound != current.binding(bound.origin):
                raise DependencyEvidenceError(
                    DependencyFailure.STALE,
                    f"The dependency evidence of {member.requirement_id} is stale: "
                    f"{bound.requirement_id} changed after Review Result "
                    f"{member.review.iteration} of {member.requirement_id}.",
                    (f"{member.requirement_id} -> {bound.requirement_id}",),
                )


def _read_failed(requirement_id: str, error: FiberyError) -> DependencyEvidenceError:
    return DependencyEvidenceError(
        DependencyFailure.READ_FAILED,
        f"Dependency {requirement_id} could not be read from Fibery.",
        (str(error),),
    )


def _invalid(requirement_id: str, reason: str) -> DependencyEvidenceError:
    return DependencyEvidenceError(
        DependencyFailure.INVALID,
        f"Dependency {requirement_id} is not admissible normative authority: {reason}",
        (requirement_id,),
    )


def _read_member(
    workspace: DependencyWorkspace,
    requirement: RequirementRecord,
    requirement_id: str,
) -> DependencyMember:
    """One member, read fresh and validated as admissible authority."""
    try:
        matches = workspace.find_requirements_by_requirement_id(requirement_id)
    except FiberyError as error:
        raise _read_failed(requirement_id, error) from error
    if len(matches) != 1:
        raise _invalid(
            requirement_id,
            "no Requirement carries that ID."
            if not matches
            else "more than one Requirement carries that ID.",
        )
    record = matches[0]
    if record.type_name != STANDARD_TYPE:
        raise _invalid(requirement_id, f"it has Type {record.type_name!r}.")
    if record.project_id != requirement.project_id:
        raise _invalid(requirement_id, "it belongs to another Project.")
    root = _single_root(workspace, record)
    try:
        tree = read_normative_tree(workspace, record, root)
    except NormativeTreeError as error:
        if error.read_failed:
            raise DependencyEvidenceError(
                DependencyFailure.READ_FAILED, error.message, error.details
            ) from error
        raise _invalid(
            requirement_id, f"its normative tree is invalid ({error.message})."
        ) from error
    process = _latest(workspace, record, tree.artifacts, parse_process_result_name)
    review_node = _latest_node(record, tree.artifacts, parse_review_result_name)
    if process is None or review_node is None:
        raise _invalid(requirement_id, "it has no Process and Review evidence.")
    review_content = _read(workspace, requirement_id, review_node)
    try:
        review = parse_review_result(review_content)
        status = what_clearance(review, process) if review.is_dependency_bound else None
    except InvalidReviewResult as error:
        raise _invalid(
            requirement_id, f"its Review Result cannot be trusted ({error})."
        ) from error
    _require_admissible_review(record, tree.manifest.fingerprint, process, review)
    if status is not WhatStatus.CLEAR:
        raise _invalid(
            requirement_id,
            "its latest Review Result does not establish WHAT CLEAR "
            "under the dependency-bound contract.",
        )
    member = DependencyMember(
        record=record,
        tree_fingerprint=tree.manifest.fingerprint,
        review=review,
        review_digest=document_fingerprint(review_content),
    )
    _require_edges_agree(workspace, member)
    return member


def _single_root(
    workspace: DependencyWorkspace, record: RequirementRecord
) -> DocumentNode:
    try:
        attached = workspace.documents_attached_to_requirement(record.public_id)
    except FiberyError as error:
        raise _read_failed(record.requirement_id or "", error) from error
    if len(attached) != 1:
        raise _invalid(
            record.requirement_id or "",
            f"it has {len(attached)} attached Documents, not one Root.",
        )
    return attached[0]


def _latest_node(
    record: RequirementRecord,
    artifacts: tuple[DocumentNode, ...],
    parse_name: Callable[[str], tuple[str, int] | None],
) -> DocumentNode | None:
    nodes: dict[int, DocumentNode] = {}
    for node in artifacts:
        parsed = parse_name(node.name)
        if parsed is None or parsed[0] != record.requirement_id:
            continue
        if parsed[1] in nodes:
            raise _invalid(
                record.requirement_id or "",
                f"it has more than one artifact for iteration {parsed[1]}.",
            )
        nodes[parsed[1]] = node
    return nodes[max(nodes)] if nodes else None


def _latest(
    workspace: DependencyWorkspace,
    record: RequirementRecord,
    artifacts: tuple[DocumentNode, ...],
    parse_name: Callable[[str], tuple[str, int] | None],
) -> ProcessResult | None:
    node = _latest_node(record, artifacts, parse_name)
    if node is None:
        return None
    try:
        return parse_process_result(_read(workspace, record.requirement_id, node))
    except InvalidProcessResult as error:
        raise _invalid(
            record.requirement_id or "",
            f"its Process Result cannot be trusted ({error}).",
        ) from error


def _read(
    workspace: DependencyWorkspace, requirement_id: str | None, node: DocumentNode
) -> str:
    try:
        return workspace.read_document_content(node.secret or "")
    except FiberyError as error:
        raise _read_failed(requirement_id or "", error) from error


def _require_admissible_review(
    record: RequirementRecord,
    tree_fingerprint: str,
    process: ProcessResult,
    review: ReviewResult,
) -> None:
    requirement_id = record.requirement_id or ""
    if not review.is_dependency_bound:
        raise _invalid(
            requirement_id,
            f"its latest Review Result (version {review.version}) predates "
            "dependency evidence; it needs a new Process and Review.",
        )
    if not (
        review.requirement_id == requirement_id
        and process.requirement_id == requirement_id
        and review.reviewed_process_iteration == process.iteration
        and review.reviewed_process_output_fingerprint == process.output_fingerprint
        and review.reviews_tree(tree_fingerprint)
    ):
        raise _invalid(
            requirement_id,
            "its latest Review Result does not review its current normative "
            "tree and latest Process Result.",
        )


def _require_edges_agree(
    workspace: DependencyWorkspace, member: DependencyMember
) -> None:
    """A member's DEPENDS_ON edges in Fibery are those its Review bound.

    A confirmed proposal may still await the member's own Apply, so before
    it is Applied its edges may be a subset; once Applied, exactly the set.
    """
    actual = set(_depends_on(workspace, member.record))
    bound = set(member.direct_ids)
    is_applied = member.record.state == APPLIED_STATE
    if not actual <= bound or (is_applied and actual != bound):
        raise _invalid(
            member.requirement_id,
            "its DEPENDS_ON edges in Fibery disagree with the dependencies its "
            "Review Result bound.",
        )


def _depends_on(
    workspace: DependencyWorkspace, record: RequirementRecord
) -> tuple[str, ...]:
    try:
        return workspace.requirement_relations(record.id).depends_on
    except FiberyError as error:
        raise _read_failed(record.requirement_id or "", error) from error


def bind(
    members: Mapping[str, DependencyMember],
    direct: Mapping[str, DependencyOrigin],
) -> tuple[DependencyBinding, ...]:
    """The bindings of `direct` and of everything they reach, in ID order."""
    reachable: set[str] = set()
    pending = list(direct)
    while pending:
        current = pending.pop()
        if current in reachable:
            continue
        reachable.add(current)
        pending.extend(members[current].direct_ids)
    return tuple(
        members[requirement_id].binding(
            direct.get(requirement_id, DependencyOrigin.TRANSITIVE)
        )
        for requirement_id in sorted(reachable)
    )


def require_current_dependencies(
    workspace: DependencyWorkspace,
    requirement: RequirementRecord,
    review: ReviewResult,
    phase: Phase,
) -> dict[str, DependencyMember]:
    """Refuse unless the review's dependency bindings describe Fibery now.

    The interpretation set is recomputed from the bound direct dependencies
    and must equal the bindings exactly; the Requirement's own DEPENDS_ON
    edges must be those `phase` allows; from Apply on, every direct
    dependency must be Applied. Returns the members read.
    """
    if not review.is_dependency_bound:
        raise DependencyEvidenceError(
            DependencyFailure.INVALID,
            f"Review Result {review.iteration} (version {review.version}) of "
            f"{requirement.requirement_id} predates dependency evidence, so its "
            "dependencies are unknown, not absent.",
        )
    direct = {
        binding.requirement_id: binding.origin
        for binding in review.dependency_bindings
        if binding.is_direct
    }
    try:
        members = resolve_interpretation_set(workspace, requirement, direct)
    except DependencyEvidenceError as error:
        if error.failure in {DependencyFailure.CYCLE, DependencyFailure.READ_FAILED}:
            raise
        raise DependencyEvidenceError(
            DependencyFailure.STALE, error.message, error.details
        ) from error
    current = bind(members, direct)
    if current != review.dependency_bindings:
        changed = sorted(
            {
                binding.requirement_id
                for binding in set(current) ^ set(review.dependency_bindings)
            }
        )
        raise DependencyEvidenceError(
            DependencyFailure.STALE,
            f"The dependencies of {requirement.requirement_id} changed after "
            f"Review Result {review.iteration} bound them.",
            tuple(changed),
        )
    _require_own_edges(workspace, requirement, review, phase)
    if phase is not Phase.REVIEWED:
        unapplied = sorted(
            requirement_id
            for requirement_id in direct
            if members[requirement_id].record.state != APPLIED_STATE
        )
        if unapplied:
            raise DependencyEvidenceError(
                DependencyFailure.NOT_APPLIED,
                f"{requirement.requirement_id} depends on Requirements that are "
                "not Applied, so they are not yet approved authority.",
                tuple(unapplied),
            )
    return members


def _require_own_edges(
    workspace: DependencyWorkspace,
    requirement: RequirementRecord,
    review: ReviewResult,
    phase: Phase,
) -> None:
    actual = set(_depends_on(workspace, requirement))
    existing = {
        binding.requirement_id
        for binding in review.dependency_bindings
        if binding.origin is DependencyOrigin.EXISTING
    }
    intended = {
        binding.requirement_id
        for binding in review.dependency_bindings
        if binding.is_direct
    }
    agrees = {
        Phase.REVIEWED: actual == existing,
        Phase.APPLYING: existing <= actual <= intended,
        Phase.APPLIED: actual == intended,
    }[phase]
    if not agrees:
        raise DependencyEvidenceError(
            DependencyFailure.STALE,
            f"The DEPENDS_ON edges of {requirement.requirement_id} no longer agree "
            f"with the dependencies Review Result {review.iteration} verified.",
            tuple(sorted(actual ^ (intended if phase is Phase.APPLIED else existing))),
        )
