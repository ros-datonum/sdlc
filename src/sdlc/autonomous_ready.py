"""The deterministic Ready decider: AUTO_APPROVE, AUTO_REWORK or HUMAN_REQUIRED.

Implements Requirement-Autonomous-Ready-v0.1. Where the operator delegated it
for a Project (`[ready_decisions]`, ready_delegation.py), the runner may make
the two existing Ready transitions itself:

    AUTO_APPROVE    Ready -> Apply     only what the existing approval accepts
                                       with no acknowledgement, and more
    AUTO_REWORK     Ready -> Process   only for actionable, current feedback,
                                       within budget, while progress is shown
    HUMAN_REQUIRED  stays at Ready     with the reason and the next human step

It invokes no model and writes nothing but the one State, through the same
`approve_standard_requirement` / `rework_standard_requirement` a human admin
uses, each given a guard that re-reads the evidence and the configuration
immediately before the write. Disabled delegation, or a Project without an
authorization, leaves Ready exactly the human boundary it was.

The runner calls `ReadyDecider` only when no machine route has work, inside
its workspace lock. The decider keeps, in memory, which Ready Requirements it
already decided under the current configuration, so a Requirement left at
Ready is not decided again in a loop. That memory is no lifecycle state: an
entry is dropped when the runner claims a machine cycle for the Requirement
(only such a cycle returns it to `Ready + Succeeded`), when the Ready page
covering it no longer returns it, or when the configuration changes; a
restarted runner decides every Ready Requirement once more from Fibery alone.
Candidates are read one bounded `fibery/id` page per call, so every one is
reached however many were decided ahead of it.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Protocol

from sdlc.autonomy_policy import AutonomyPolicies, PolicyBinding
from sdlc.config import ConfigurationError
from sdlc.fibery_http import ELIGIBLE_QUERY_LIMIT
from sdlc.fibery_workspace import (
    FiberyError,
    ProjectRecord,
    ReadyDecisionWorkspace,
    RequirementRecord,
    RunnerWorkspace,
)
from sdlc.ready_decision import (
    DecisionGuard,
    EvidenceIdentity,
    ReadyEvidence,
    ReadyEvidenceError,
    approve_standard_requirement,
    read_ready_evidence,
    read_review_lineage,
    rework_standard_requirement,
)
from sdlc.ready_delegation import (
    ReadyAuthorization,
    ReadyAuthorizationBinding,
    ReadyDelegation,
)
from sdlc.ready_progress import (
    Lineage,
    ProgressAssessment,
    ProgressStop,
    ProgressUnknown,
    assess_rework,
    conflicting_reviews,
)
from sdlc.requirement_dispatcher import (
    READY_STATE,
    STANDARD_TYPE,
    ProcessingStatus,
)
from sdlc.requirement_runner import (
    CycleOutcome,
    CycleReport,
    ProjectScope,
    ProjectScopeError,
    check_project_scope,
)
from sdlc.results import ReadyDecisionResult, ReadyDecisionResultCode
from sdlc.review_result import ReviewResult
from sdlc.rework_brief import BriefCategory, item_ref
from sdlc.standard_analysis import ReworkOutcome
from sdlc.standard_review import (
    ReviewSeverity,
    ReviewVerdict,
    VerificationOutcome,
    WhatStatus,
    question_blocks,
)

#: The only candidates: a Standard Requirement whose Review cycle the runner
#: completed (RW-C04: Review leaves `Ready + Succeeded`).
READY_ROUTE = ((STANDARD_TYPE, READY_STATE),)
READY_STATUS = ProcessingStatus.SUCCEEDED
REWORK_SEVERITIES = frozenset({ReviewSeverity.WARNING, ReviewSeverity.BLOCKING})
# Fields a Ready candidate is bound to between its poll row and its decision.
CANDIDATE_FIELDS = (
    ("requirement_id", "Requirement ID"),
    ("type_name", "Type"),
    ("state", "State"),
    ("project_id", "Project"),
    ("processing_status", "Processing Status"),
)


class ReadyDecisionKind(StrEnum):
    """The three decisions; nothing else is ever made at Ready."""

    AUTO_APPROVE = "AUTO_APPROVE"
    AUTO_REWORK = "AUTO_REWORK"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"


class Transition(StrEnum):
    """What became of the State, as distinct from what was decided."""

    # HUMAN_REQUIRED: no transition is attempted.
    NOT_ATTEMPTED = "NOT_ATTEMPTED"
    # Written and read back as the decided State.
    CONFIRMED = "CONFIRMED"
    # Refused before any write: the State, evidence or authority moved.
    WITHDRAWN = "WITHDRAWN"
    # The write failed or did not read back: the State is not established.
    UNCERTAIN = "UNCERTAIN"


class HumanReason(StrEnum):
    """Why a decision was left to a human (besides the progress stops)."""

    NOT_DELEGATED = "NOT_DELEGATED"
    APPROVAL_NOT_DELEGATED = "APPROVAL_NOT_DELEGATED"
    REWORK_NOT_DELEGATED = "REWORK_NOT_DELEGATED"
    EVIDENCE_NOT_CURRENT = "EVIDENCE_NOT_CURRENT"
    HISTORY_INVALID = "HISTORY_INVALID"
    HUMAN_PRODUCT_DECISION = "HUMAN_PRODUCT_DECISION"
    AMBIGUOUS_REVIEW = "AMBIGUOUS_REVIEW"
    NOTHING_ACTIONABLE = "NOTHING_ACTIONABLE"
    TRANSITION_REFUSED = "TRANSITION_REFUSED"


NEXT_ACTION = {
    HumanReason.NOT_DELEGATED: (
        "Decide at Ready as before: Ready -> Apply to approve, Ready -> Process "
        "to rework."
    ),
    HumanReason.APPROVAL_NOT_DELEGATED: (
        "The Review is PASS and WHAT CLEAR, but approval is not delegated for "
        "this Project: a human approves (Ready -> Apply) or reworks."
    ),
    HumanReason.REWORK_NOT_DELEGATED: (
        "Rework is not delegated for this Project: read the latest Review Result "
        "and decide (Ready -> Process to rework)."
    ),
    HumanReason.EVIDENCE_NOT_CURRENT: (
        "The evidence is not current: `sdlc requirement approve` names the "
        "refusal; usually Ready -> Process for a fresh Process and Review."
    ),
    HumanReason.HISTORY_INVALID: (
        "The Process/Review history cannot establish progress: inspect the "
        "Requirement's Process and Review Results, then decide."
    ),
    HumanReason.HUMAN_PRODUCT_DECISION: (
        "A product decision is needed: answer it in the Requirement's normative "
        "content (or in its source), then Ready -> Process."
    ),
    HumanReason.AMBIGUOUS_REVIEW: (
        "The Review left items unresolved: read the latest Review Result, settle "
        "them, then decide."
    ),
    HumanReason.NOTHING_ACTIONABLE: (
        "No automatic decision applies: read the latest Review Result and decide."
    ),
    HumanReason.TRANSITION_REFUSED: (
        "The existing Ready validation refused the transition on a fresh read: "
        "`sdlc requirement approve` names the refusal; decide at Ready."
    ),
}
STOPPED_NEXT_ACTION = (
    "Automatic rework stopped: read the Review Results of the stopped rounds "
    "and decide at Ready (Ready -> Process with a human correction, or Ready -> "
    "Apply if acceptable)."
)


@dataclass(frozen=True)
class ReadyDecisionRecord:
    """The structured, content-free account of one Ready decision.

    It identifies the Requirement, the exact evidence, the authority and the
    checks, the budget, and — separately — what the decision was and what
    became of the State. It quotes no Requirement text: reasons name codes,
    item references, iterations and counts only.
    """

    requirement_id: str | None
    entity_id: str
    project_id: str
    project_code: str | None
    decision: ReadyDecisionKind
    reasons: tuple[str, ...]
    transition: Transition
    state_after: str | None = None
    transition_code: str | None = None
    next_action: str | None = None
    evidence: EvidenceIdentity | None = None
    verdict: str | None = None
    what_status: str | None = None
    authorization: ReadyAuthorizationBinding | None = None
    autonomy_policy: PolicyBinding | None = None
    checks: tuple[str, ...] = ()
    progress: tuple[str, ...] = ()


class ReadyDeciderWorkspace(RunnerWorkspace, ReadyDecisionWorkspace, Protocol):
    """The runner's adapter, which also reads Ready evidence and the Project."""

    def read_project(self, project_id: str) -> ProjectRecord | None: ...

    def find_eligible_requirements_after(
        self,
        routes: Sequence[tuple[str, str]],
        status: str,
        after_id: str | None,
        project_id: str | None = None,
    ) -> list[RequirementRecord]: ...

    def find_project_by_code(self, code: str) -> ProjectRecord | None: ...

    def count_projects_with_code(self, code: str) -> int: ...


# What a configured decider is given: the two loaders it reads on every cycle.
LoadDelegation = Callable[[], ReadyDelegation]
LoadPolicies = Callable[[], AutonomyPolicies]
# The configuration a decision depends on; a change re-opens every decision.
Basis = tuple[tuple[ReadyAuthorizationBinding, ...], tuple[PolicyBinding, ...]]

CURRENTNESS_CHECKS = (
    "Requirement is Standard, in Ready, with the runner's Review cycle Succeeded",
    (
        "latest Review Result binds the current Root, normative tree and latest "
        "Process Result"
    ),
    "Process and Review Results are current-format and their WHAT evidence is coherent",
    "every bound dependency is the version reviewed (WI-4)",
    "every cited source and the bound autonomy policy are current (WI-5)",
)
# Outcomes the decider will not decide again under the same configuration.
SETTLED_OUTCOMES = frozenset(
    {
        CycleOutcome.READY_DECIDED,
        CycleOutcome.READY_ESCALATED,
        CycleOutcome.READY_UNCERTAIN,
    }
)


class ReadyDecider:
    """The runner's opt-in Ready step: at most one decision per call."""

    def __init__(
        self,
        load_delegation: LoadDelegation,
        load_policies: LoadPolicies,
        scope: ProjectScope | None = None,
    ) -> None:
        self._load_delegation = load_delegation
        self._load_policies = load_policies
        # Requirement-Worker-Project-Scope-v0.1: only this Project's Ready
        # Requirements are read, and none other is ever decided.
        self._scope = scope
        self._decided: dict[str, Basis] = {}
        # The last `fibery/id` of the page before the one being read; None is
        # the first page. Memory only: a restart reads from the first page.
        self._cursor: str | None = None

    def __call__(self, workspace: ReadyDeciderWorkspace) -> CycleReport | None:
        """Decide one undecided Ready candidate of the current page, or None.

        The configuration is read afresh first: disabled delegation returns
        None, so the cycle is idle and Ready is the human boundary. Candidates
        are read one `fibery/id`-ordered page at a time: a page with nothing
        left to decide moves the cursor to the next page, and the last page
        back to the first, so every Ready candidate is reached within as many
        idle cycles as there are pages, however many were decided before it.
        Cost: one configuration read and one bounded Fibery query per call.
        """
        try:
            delegation = self._load_delegation()
            policies = self._load_policies()
        except ConfigurationError as error:
            return CycleReport(
                CycleOutcome.READY_FAILED,
                "The Ready delegation or autonomy configuration could not be read "
                "or validated; no Ready decision was made and no earlier "
                "configuration is reused.",
                details=(str(error),),
            )
        if not delegation.is_enabled:
            self._decided.clear()
            self._cursor = None
            return None
        try:
            page = workspace.find_eligible_requirements_after(
                READY_ROUTE,
                READY_STATUS.value,
                self._cursor,
                project_id=self._scope.project_id if self._scope is not None else None,
            )
        except FiberyError as error:
            return CycleReport(
                CycleOutcome.READY_FAILED,
                "The Ready query failed; no Ready decision was made.",
                details=(str(error),),
            )
        basis = _basis(delegation, policies)
        is_last_page = len(page) < ELIGIBLE_QUERY_LIMIT
        self._forget_absent(page, is_last_page)
        candidate = min(
            (
                record
                for record in page
                if self._decided.get(record.id) != basis and _is_candidate(record)
            ),
            key=_public_id_order,
            default=None,
        )
        if candidate is None:
            self._cursor = None if is_last_page else page[-1].id
            return None
        report = decide(
            workspace,
            candidate,
            delegation,
            policies,
            reload=lambda: (self._load_delegation(), self._load_policies()),
            scope=self._scope,
        )
        if report.outcome in SETTLED_OUTCOMES:
            self._decided[candidate.id] = basis
        return report

    def _forget_absent(self, page: list[RequirementRecord], is_last_page: bool) -> None:
        """Drop the decisions of Requirements this page's range no longer holds.

        The range is every `fibery/id` after the cursor, up to the page's last
        row unless this is the last page; entries outside it are kept until
        their own page is read.
        """
        present = {record.id for record in page}
        end = None if is_last_page else page[-1].id
        self._decided = {
            entity: settled
            for entity, settled in self._decided.items()
            if entity in present
            or (self._cursor is not None and entity <= self._cursor)
            or (end is not None and entity > end)
        }

    def forget(self, entity_id: str) -> None:
        """The runner claimed a machine cycle for it: decide its next Ready afresh."""
        self._decided.pop(entity_id, None)


# -- one decision -------------------------------------------------------------------


def decide(
    workspace: ReadyDeciderWorkspace,
    candidate: RequirementRecord,
    delegation: ReadyDelegation,
    policies: AutonomyPolicies,
    reload: Callable[[], tuple[ReadyDelegation, AutonomyPolicies]],
    scope: ProjectScope | None = None,
) -> CycleReport:
    """Decide one Ready candidate under one configuration snapshot.

    Under a `scope` the bound Project is read again first, and a candidate
    outside it is never decided.
    """
    if scope is not None:
        try:
            check_project_scope(workspace, scope)
        except ProjectScopeError as error:
            return CycleReport(
                CycleOutcome.SCOPE_INVALID,
                f"{_label(candidate)}: the Project scope no longer holds; no "
                "decision, nothing written, and the runner stops.",
                candidate,
                details=(str(error),),
            )
    try:
        fresh = workspace.read_requirement(candidate.id)
        changes = (*_differences(candidate, fresh), *_outside(fresh, scope))
        project = workspace.read_project(candidate.project_id) if not changes else None
    except FiberyError as error:
        return _failed(candidate, "could not be re-read", error)
    if fresh is None or changes:
        return CycleReport(
            CycleOutcome.CANDIDATE_CHANGED,
            f"{_label(candidate)} changed after the Ready query; no decision.",
            fresh or candidate,
            details=changes,
        )
    code = project.code if project is not None else None
    base = ReadyDecisionRecord(
        requirement_id=fresh.requirement_id,
        entity_id=fresh.id,
        project_id=fresh.project_id,
        project_code=code,
        decision=ReadyDecisionKind.HUMAN_REQUIRED,
        reasons=(),
        transition=Transition.NOT_ATTEMPTED,
        state_after=fresh.state,
    )
    authorization = delegation.for_project(code)
    if authorization is None:
        return _escalated(
            fresh,
            base,
            HumanReason.NOT_DELEGATED,
            (f"Project {code!r} has no Ready delegation.",),
        )
    base = replace(base, authorization=authorization.binding)
    try:
        evidence = read_ready_evidence(workspace, fresh.id, policies)
    except ReadyEvidenceError as error:
        return _evidence_refused(fresh, base, error)
    base = _with_evidence(base, evidence)
    try:
        lineage = read_review_lineage(workspace, evidence)
        progress = assess_rework(
            lineage, authorization.max_rework_rounds, authorization.max_issue_repeats
        )
    except ReadyEvidenceError as error:
        if error.code is ReadyDecisionResultCode.FIBERY_READ_FAILED:
            return _failed(fresh, "history could not be read", error)
        return _escalated(
            fresh, base, HumanReason.HISTORY_INVALID, (f"{error.code.value}",)
        )
    except ProgressUnknown:
        return _escalated(
            fresh,
            base,
            HumanReason.HISTORY_INVALID,
            ("an item of the Review history cannot be traced to its origin",),
        )
    base = replace(base, progress=progress.summary())
    decision, reasons, next_action = classify(
        evidence, lineage, authorization, progress
    )
    base = replace(base, decision=decision, reasons=reasons, next_action=next_action)
    if decision is ReadyDecisionKind.HUMAN_REQUIRED:
        return _report(fresh, base, CycleOutcome.READY_ESCALATED)
    return _transition(workspace, fresh, base, evidence, policies, reload)


def classify(
    evidence: ReadyEvidence,
    lineage: Lineage,
    authorization: ReadyAuthorization,
    progress: ProgressAssessment,
) -> tuple[ReadyDecisionKind, tuple[str, ...], str | None]:
    """The decision current evidence supports. Pure; nothing is read or written.

    Approval needs PASS, CLEAR and nothing left open, ambiguous or for a human,
    and no conflicting earlier review of the same output. Rework needs
    actionable feedback, nothing for a human, and the history's permission.
    """
    review = evidence.latest_review
    human = human_only_items(review)
    ambiguous = unresolved_items(review)
    actionable = actionable_items(evidence)
    if (
        review.verdict is ReviewVerdict.PASS
        and evidence.what_status is WhatStatus.CLEAR
        and not human
        and not ambiguous
        and not actionable
    ):
        conflicts = conflicting_reviews(lineage)
        if conflicts:
            return _human_stops(conflicts)
        if not authorization.auto_approve:
            return _human(HumanReason.APPROVAL_NOT_DELEGATED, ())
        return (
            ReadyDecisionKind.AUTO_APPROVE,
            (
                (
                    f"Review Result {review.iteration}: PASS, WHAT CLEAR, nothing left "
                    "open, ambiguous or for a human."
                ),
            ),
            None,
        )
    if evidence.what_status is None:
        return _human(
            HumanReason.EVIDENCE_NOT_CURRENT,
            ("the Review establishes no WHAT status (pre-WHAT-gate evidence)",),
        )
    if human:
        return _human(HumanReason.HUMAN_PRODUCT_DECISION, human)
    if ambiguous:
        return _human(HumanReason.AMBIGUOUS_REVIEW, ambiguous)
    if not actionable:
        return _human(HumanReason.NOTHING_ACTIONABLE, ())
    if not authorization.auto_rework:
        return _human(HumanReason.REWORK_NOT_DELEGATED, actionable)
    if not progress.permits_rework:
        return _human_stops(progress.stops)
    return (
        ReadyDecisionKind.AUTO_REWORK,
        tuple(f"actionable {item}" for item in actionable),
        None,
    )


def human_only_items(review: ReviewResult) -> tuple[str, ...]:
    """What only a human can settle: open product questions and escalations."""
    escalated = [
        f"{reviewed.response.item} escalated by Process"
        for reviewed in review.reviewed_rework_responses
        if reviewed.response.outcome is ReworkOutcome.ESCALATED
    ]
    confirmed_open = [
        f"{_ref(review, BriefCategory.PRODUCT_QUESTION, item.question_index)} "
        "confirmed open by the Review"
        for item in review.question_verifications
        if item.outcome is VerificationOutcome.CONFIRMED
    ]
    raised = [
        f"{_ref(review, BriefCategory.MATERIAL_WHAT, index)} material WHAT question "
        "raised by the Review"
        for index, _ in enumerate(review.material_unresolved_what)
    ]
    return (*confirmed_open, *raised, *escalated)


def unresolved_items(review: ReviewResult) -> tuple[str, ...]:
    """Every verification the Reviewer could not settle: ambiguous evidence."""
    unresolved = VerificationOutcome.UNRESOLVED
    return (
        *(
            _ref(review, BriefCategory.PROCESS_FINDING, item.process_finding_index)
            for item in review.finding_verifications
            if item.outcome is unresolved
        ),
        *(
            _ref(review, BriefCategory.RELATION_PROPOSAL, index)
            for index, item in enumerate(review.relation_verifications)
            if item.outcome is unresolved
        ),
        *(
            _ref(review, BriefCategory.PRODUCT_QUESTION, item.question_index)
            for item in review.question_verifications
            if item.outcome is unresolved
        ),
        *(
            _ref(review, BriefCategory.REWORK_CLAIM, index)
            for index, item in enumerate(review.rework_verifications)
            if item.outcome is unresolved
        ),
        *(
            _ref(review, BriefCategory.EXISTING_DEPENDENCY, index)
            for index, item in enumerate(review.dependency_verifications)
            if item.outcome is unresolved
        ),
        *(
            _ref(review, BriefCategory.RESOLUTION, item.resolution_index)
            for item in review.resolution_verifications
            if item.outcome is unresolved
        ),
    )


def actionable_items(evidence: ReadyEvidence) -> tuple[str, ...]:
    """Defects the Reviewer asserts that another Process iteration can address.

    A confirmed or newly found defect graded WARNING or BLOCKING; a rejected
    relation proposal, rework answer, existing dependency or resolution; and
    a product question rejected as answered by another Requirement that is
    not yet a verified, bound dependency.
    """
    review = evidence.latest_review
    rejected = VerificationOutcome.REJECTED
    questions = review.reviewed_product_questions or ()
    return (
        *(
            _ref(review, BriefCategory.PROCESS_FINDING, item.process_finding_index)
            for item in review.finding_verifications
            if item.outcome is VerificationOutcome.CONFIRMED
            and item.severity in REWORK_SEVERITIES
        ),
        *(
            _ref(review, BriefCategory.NEW_FINDING, index)
            for index, item in enumerate(review.new_findings)
            if item.severity in REWORK_SEVERITIES
        ),
        *(
            _ref(review, BriefCategory.RELATION_PROPOSAL, index)
            for index, item in enumerate(review.relation_verifications)
            if item.outcome is rejected
        ),
        *(
            _ref(review, BriefCategory.PRODUCT_QUESTION, item.question_index)
            for item in review.question_verifications
            if item.outcome is rejected
            and question_blocks(
                questions[item.question_index], item, review.verified_dependencies
            )
        ),
        *(
            _ref(review, BriefCategory.REWORK_CLAIM, index)
            for index, item in enumerate(review.rework_verifications)
            if item.outcome is rejected
        ),
        *(
            _ref(review, BriefCategory.EXISTING_DEPENDENCY, index)
            for index, item in enumerate(review.dependency_verifications)
            if item.outcome is rejected
        ),
        *(
            _ref(review, BriefCategory.RESOLUTION, item.resolution_index)
            for item in review.resolution_verifications
            if item.outcome is rejected
        ),
    )


# -- the transition -----------------------------------------------------------------


def _transition(
    workspace: ReadyDeciderWorkspace,
    requirement: RequirementRecord,
    record: ReadyDecisionRecord,
    evidence: ReadyEvidence,
    policies: AutonomyPolicies,
    reload: Callable[[], tuple[ReadyDelegation, AutonomyPolicies]],
) -> CycleReport:
    """Make the decided transition through the existing decision, guarded."""
    guard = _guard(workspace, requirement, record, evidence, policies, reload)
    if record.decision is ReadyDecisionKind.AUTO_APPROVE:
        # No acknowledgement: anything but PASS refuses inside the approval.
        result = approve_standard_requirement(
            workspace, requirement.id, None, policies=policies, guard=guard
        )
        done = ReadyDecisionResultCode.REQUIREMENT_APPROVED
    else:
        result = rework_standard_requirement(
            workspace, requirement.id, policies=policies, guard=guard
        )
        done = ReadyDecisionResultCode.REQUIREMENT_SENT_FOR_REWORK
    return _outcome(requirement, record, result, done)


def _guard(
    workspace: ReadyDeciderWorkspace,
    requirement: RequirementRecord,
    record: ReadyDecisionRecord,
    evidence: ReadyEvidence,
    policies: AutonomyPolicies,
    reload: Callable[[], tuple[ReadyDelegation, AutonomyPolicies]],
) -> DecisionGuard:
    """The decision's basis, re-checked on the fresh evidence just before the write.

    The same Requirement, in the same Project under the same Code, still
    `Ready + Succeeded`, with the same evidence, delegation and policies.
    """

    def still_holds(fresh: ReadyEvidence) -> str | None:
        if fresh.identity != evidence.identity:
            return "The evidence changed after the decision was made."
        if _differences(requirement, fresh.requirement):
            return (
                "The Requirement's Project or Processing Status changed after the "
                "decision was made."
            )
        try:
            project = workspace.read_project(fresh.requirement.project_id)
        except FiberyError:
            return "The Requirement's Project can no longer be read."
        if project is None or project.code != record.project_code:
            return "The Requirement's Project changed after the decision was made."
        try:
            delegation, current = reload()
        except ConfigurationError:
            return "The configuration can no longer be read."
        authorization = delegation.for_project(record.project_code)
        if authorization is None or authorization.binding != record.authorization:
            return "The Ready delegation changed after the decision was made."
        if _policy_identity(current) != _policy_identity(policies):
            return "The autonomy policies changed after the decision was made."
        return None

    return still_holds


def _outcome(
    requirement: RequirementRecord,
    record: ReadyDecisionRecord,
    result: ReadyDecisionResult,
    done: ReadyDecisionResultCode,
) -> CycleReport:
    code = result.code
    record = replace(record, transition_code=code.value, state_after=result.state)
    if code is done:
        return _report(
            requirement,
            replace(record, transition=Transition.CONFIRMED),
            CycleOutcome.READY_DECIDED,
        )
    if code in {
        ReadyDecisionResultCode.FIBERY_WRITE_FAILED,
        ReadyDecisionResultCode.VALIDATION_FAILED,
    }:
        return _report(
            requirement,
            replace(
                record,
                transition=Transition.UNCERTAIN,
                state_after=None,
                next_action=(
                    "The State write is not confirmed: read the Requirement's State "
                    "in Fibery. The runner will not repeat this decision; decide "
                    "at Ready if it is still there."
                ),
            ),
            CycleOutcome.READY_UNCERTAIN,
        )
    if code is ReadyDecisionResultCode.FIBERY_READ_FAILED:
        return _report(
            requirement,
            replace(record, transition=Transition.WITHDRAWN),
            CycleOutcome.READY_FAILED,
        )
    if code in {
        ReadyDecisionResultCode.DECISION_BASIS_CHANGED,
        ReadyDecisionResultCode.REQUIREMENT_NOT_IN_READY,
        ReadyDecisionResultCode.REQUIREMENT_ALREADY_APPROVED,
        ReadyDecisionResultCode.REQUIREMENT_ALREADY_IN_REWORK,
    }:
        return _report(
            requirement,
            replace(record, transition=Transition.WITHDRAWN),
            CycleOutcome.READY_WITHDRAWN,
        )
    return _report(
        requirement,
        replace(
            record,
            decision=ReadyDecisionKind.HUMAN_REQUIRED,
            transition=Transition.WITHDRAWN,
            reasons=(
                *record.reasons,
                f"{HumanReason.TRANSITION_REFUSED.value}: {code.value}",
            ),
            next_action=NEXT_ACTION[HumanReason.TRANSITION_REFUSED],
        ),
        CycleOutcome.READY_ESCALATED,
    )


# -- reporting ----------------------------------------------------------------------


def _report(
    requirement: RequirementRecord,
    record: ReadyDecisionRecord,
    outcome: CycleOutcome,
) -> CycleReport:
    return CycleReport(
        outcome,
        f"{_label(requirement)}: {record.decision.value}; transition "
        f"{record.transition.value}.",
        requirement,
        ready_decision=record,
    )


def _escalated(
    requirement: RequirementRecord,
    record: ReadyDecisionRecord,
    reason: HumanReason,
    details: tuple[str, ...],
) -> CycleReport:
    kind, reasons, next_action = _human(reason, details)
    return _report(
        requirement,
        replace(record, decision=kind, reasons=reasons, next_action=next_action),
        CycleOutcome.READY_ESCALATED,
    )


def _evidence_refused(
    requirement: RequirementRecord,
    record: ReadyDecisionRecord,
    error: ReadyEvidenceError,
) -> CycleReport:
    if error.code is ReadyDecisionResultCode.FIBERY_READ_FAILED:
        return _failed(requirement, "evidence could not be read", error)
    if error.code is ReadyDecisionResultCode.REQUIREMENT_NOT_IN_READY:
        return CycleReport(
            CycleOutcome.CANDIDATE_CHANGED,
            f"{_label(requirement)} left Ready before its evidence was read; no "
            "decision.",
            requirement,
        )
    return _escalated(
        requirement, record, HumanReason.EVIDENCE_NOT_CURRENT, (error.code.value,)
    )


def _failed(
    requirement: RequirementRecord,
    what: str,
    error: FiberyError | ReadyEvidenceError,
) -> CycleReport:
    """A read failed: nothing was decided. Only codes and Fibery's own causes are
    reported; an evidence message may name a Document, and so quote its title.
    """
    details = (
        (error.code.value, *error.causes)
        if isinstance(error, ReadyEvidenceError)
        else (str(error),)
    )
    return CycleReport(
        CycleOutcome.READY_FAILED,
        f"{_label(requirement)}: {what}; no Ready decision was made.",
        requirement,
        details=details,
    )


def _human(
    reason: HumanReason, details: tuple[str, ...]
) -> tuple[ReadyDecisionKind, tuple[str, ...], str]:
    return (
        ReadyDecisionKind.HUMAN_REQUIRED,
        (reason.value, *details),
        NEXT_ACTION[reason],
    )


def _human_stops(
    stops: tuple[tuple[ProgressStop, str], ...],
) -> tuple[ReadyDecisionKind, tuple[str, ...], str]:
    return (
        ReadyDecisionKind.HUMAN_REQUIRED,
        tuple(f"{stop.value}: {detail}" for stop, detail in stops),
        STOPPED_NEXT_ACTION,
    )


def _with_evidence(
    record: ReadyDecisionRecord, evidence: ReadyEvidence
) -> ReadyDecisionRecord:
    review = evidence.latest_review
    return replace(
        record,
        evidence=evidence.identity,
        verdict=review.verdict.value,
        what_status=evidence.what_status.value if evidence.what_status else None,
        autonomy_policy=review.reviewed_autonomy_policy,
        checks=CURRENTNESS_CHECKS,
    )


# -- small helpers --------------------------------------------------------------------


def _ref(review: ReviewResult, category: BriefCategory, index: int) -> str:
    """The item's reference, exactly as the Rework Brief would name it."""
    return item_ref(review.iteration, category, index)


def _basis(delegation: ReadyDelegation, policies: AutonomyPolicies) -> Basis:
    return (delegation.identity, _policy_identity(policies))


def _policy_identity(policies: AutonomyPolicies) -> tuple[PolicyBinding, ...]:
    return tuple(policy.binding for policy in policies.policies)


def _is_candidate(record: RequirementRecord) -> bool:
    return (
        record.type_name == STANDARD_TYPE
        and record.state == READY_STATE
        and record.processing_status == READY_STATUS.value
    )


def _differences(
    expected: RequirementRecord, current: RequirementRecord | None
) -> tuple[str, ...]:
    if current is None:
        return (f"entity {expected.id} no longer exists",)
    return tuple(
        f"{name}: expected {getattr(expected, field)!r}, read "
        f"{getattr(current, field)!r}"
        for field, name in CANDIDATE_FIELDS
        if getattr(expected, field) != getattr(current, field)
    )


def _outside(
    record: RequirementRecord | None, scope: ProjectScope | None
) -> tuple[str, ...]:
    if scope is None or record is None or record.project_id == scope.project_id:
        return ()
    return (
        (
            f"Project: {record.project_id!r} is outside the scope of Project "
            f"{scope.project_code} ({scope.project_id})"
        ),
    )


def _public_id_order(record: RequirementRecord) -> tuple[bool, int, str]:
    numeric = record.public_id.isdigit()
    return (not numeric, int(record.public_id) if numeric else 0, record.public_id)


def _label(requirement: RequirementRecord) -> str:
    identity = requirement.requirement_id or requirement.id
    return f"{identity} ({requirement.type_name} + {requirement.state})"
