"""The state-driven Requirement runner behind `sdlc worker run` (RW-O03).

Implements the transport Requirement-State-Worker-Contract-v0.1 (RW-C04)
selected, inside the boundary frozen by RW-O03-Implementation-Boundary-v0.1:
one sequential local poller over the configured Fibery workspace that turns
`Type + State + Processing Status` into at most one RW-O02 dispatch at a time.

One cycle:

    query the eligible work: the four machine routes at Not Processed
    -> take the lowest fibery/public-id
    -> re-read it and select its route again from the fresh values
    -> claim it: Processing Status = Processing, confirmed by reading it back
    -> run the already selected RW-O02 dispatch, which runs one worker
    -> finalize the visible status without overwriting the next cycle's reset

A poll row is only a candidate. Every route and every claim comes from a
fresh read, and `select_route` stays the semantic authority. When nothing is
eligible the runner sleeps the idle interval; after a worker ran it queries
again at once.

Fibery has no compare-and-set. The workspace runner guard excludes a second
cooperating runner on this host, and every status write is confirmed by
reading it back. Where the current State or status cannot be established the
runner writes nothing more and reports a partial cycle. A Requirement left in
Processing (a killed runner, an unconfirmed write) stays there: it is never
treated as stale, retried or stolen, and recovery is explicit admin work.

The runner keeps no lifecycle state of its own; Fibery is the only record.

Requirement-Autonomous-Ready-v0.1 adds one opt-in step: when no machine route
has work, an optional `ready_decider` may decide one `Standard + Ready`
Requirement, inside the same lock and cycle. Without it — the default, and
whenever Ready delegation is disabled at start — a cycle is exactly as above.

Requirement-Worker-Project-Scope-v0.1 adds an optional `ProjectScope`: the
eligible-work query is filtered to that Project by Fibery, and the bound
Project is read again before every claim and every dispatch. A scope that no
longer holds ends the runner; it never widens to the whole workspace.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from sdlc.fibery_workspace import (
    FiberyError,
    RequirementRecord,
    RunnerWorkspace,
    ScopedRunnerWorkspace,
)
from sdlc.project_code import InvalidProjectCode, validate_project_code
from sdlc.requirement_dispatcher import (
    ROUTES,
    DispatchOutcome,
    DispatchResult,
    ProcessingStatus,
    RequirementWorkers,
    RouteDecision,
    RouteSelection,
    Worker,
    dispatch,
    select_route,
)

if TYPE_CHECKING:
    from sdlc.autonomous_ready import ReadyDecisionRecord

DEFAULT_POLL_INTERVAL_SECONDS = 5
MINIMUM_POLL_INTERVAL_SECONDS = 1

# The frozen option set, in RW-C04 order; the runner refuses any other.
PROCESSING_STATUS_OPTIONS = tuple(status.value for status in ProcessingStatus)
# The (Type, State) pairs of the four machine routes. The eligible-work query
# filters on them; `select_route` still decides every row it returns.
MACHINE_ROUTES = tuple(ROUTES)

# What a Requirement's machine cycle is bound to. A difference in any of these
# between two reads means the cycle observed first is not the one now.
BINDING_FIELDS = (
    ("requirement_id", "Requirement ID"),
    ("type_name", "Type"),
    ("state", "State"),
    ("project_id", "Project"),
)
CYCLE_FIELDS = (*BINDING_FIELDS, ("processing_status", "Processing Status"))


class RunnerCode(StrEnum):
    """What `sdlc worker run` reports about itself, outside any cycle."""

    WORKER_RUNNER_STARTED = "WORKER_RUNNER_STARTED"
    WORKER_RUNNER_CONFIGURATION_INVALID = "WORKER_RUNNER_CONFIGURATION_INVALID"
    WORKER_RUNNER_BUSY = "WORKER_RUNNER_BUSY"
    WORKER_RUNNER_GUARD_UNAVAILABLE = "WORKER_RUNNER_GUARD_UNAVAILABLE"
    WORKER_RUNNER_PREFLIGHT_FAILED = "WORKER_RUNNER_PREFLIGHT_FAILED"
    WORKER_RUNNER_PROJECT_INVALID = "WORKER_RUNNER_PROJECT_INVALID"
    WORKER_RUNNER_STOPPED = "WORKER_RUNNER_STOPPED"


class CycleOutcome(StrEnum):
    """Everything one runner cycle can report."""

    # No Requirement is eligible; the runner sleeps the idle interval.
    IDLE = "IDLE"
    # The eligible-work query failed; nothing was claimed.
    POLL_FAILED = "POLL_FAILED"
    # The polled candidate could not be re-read; nothing was written.
    CANDIDATE_READ_FAILED = "CANDIDATE_READ_FAILED"
    # The fresh read no longer selects the polled route; nothing was written.
    CANDIDATE_CHANGED = "CANDIDATE_CHANGED"
    # The Processing claim could not be written; no worker was started.
    CLAIM_FAILED = "CLAIM_FAILED"
    # The Processing claim did not read back as written; no worker was started.
    CLAIM_NOT_CONFIRMED = "CLAIM_NOT_CONFIRMED"
    # A route ending at a human or terminal State completed; Succeeded confirmed.
    SUCCEEDED = "SUCCEEDED"
    # Standard Process reached Review and the new Review cycle's reset to
    # Not Processed is observed; nothing was written.
    HANDED_OFF = "HANDED_OFF"
    # Standard Process reached Review but the reset is not observed; nothing
    # was written and Review does not start.
    RESET_NOT_OBSERVED = "RESET_NOT_OBSERVED"
    # The worker did not complete its cycle; Failed confirmed.
    FAILED = "FAILED"
    # The final status cannot be safely established; left as observed.
    PARTIAL = "PARTIAL"
    # Requirement-Autonomous-Ready-v0.1: the opt-in Ready step.
    # AUTO_APPROVE or AUTO_REWORK, its State transition confirmed.
    READY_DECIDED = "READY_DECIDED"
    # HUMAN_REQUIRED: the Requirement stays at Ready; nothing was written.
    READY_ESCALATED = "READY_ESCALATED"
    # A decision withdrawn before its write: the State, evidence or authority moved.
    READY_WITHDRAWN = "READY_WITHDRAWN"
    # The decided State write failed or did not read back; not repeated.
    READY_UNCERTAIN = "READY_UNCERTAIN"
    # The configuration or a Fibery read failed; no decision, nothing written.
    READY_FAILED = "READY_FAILED"
    # Requirement-Worker-Project-Scope-v0.1: the bound Project no longer holds
    # (unreadable, gone, or another Code); nothing more is written and the
    # runner stops.
    SCOPE_INVALID = "SCOPE_INVALID"


# The runner waits the idle interval after a cycle that started no worker for
# a reason an immediate query would not change: no work, or Fibery refusing a
# read or the claim. After any other cycle it queries again at once.
WAITING_OUTCOMES = frozenset(
    {
        CycleOutcome.IDLE,
        CycleOutcome.POLL_FAILED,
        CycleOutcome.CANDIDATE_READ_FAILED,
        CycleOutcome.CLAIM_FAILED,
        CycleOutcome.CLAIM_NOT_CONFIRMED,
        CycleOutcome.READY_WITHDRAWN,
        CycleOutcome.READY_FAILED,
    }
)
# Cycles whose result is the contract working as designed.
NORMAL_OUTCOMES = frozenset(
    {
        CycleOutcome.IDLE,
        CycleOutcome.CANDIDATE_CHANGED,
        CycleOutcome.SUCCEEDED,
        CycleOutcome.HANDED_OFF,
        CycleOutcome.READY_DECIDED,
        CycleOutcome.READY_ESCALATED,
        CycleOutcome.READY_WITHDRAWN,
    }
)

# Worker failures that leave the Requirement in the State it was claimed in.
FAILED_IN_CLAIMED_STATE = frozenset(
    {DispatchOutcome.WORKER_FAILED, DispatchOutcome.POSTCONDITION_NOT_REACHED}
)
# RAW candidate progression failures. The RAW is already in Review, which is
# not a reset target, so this cycle's Processing is still there to mark Failed.
FAILED_AFTER_RAW_REVIEW = frozenset(
    {
        DispatchOutcome.CANDIDATE_PROGRESSION_CONFLICT,
        DispatchOutcome.CANDIDATE_PROGRESSION_FAILED,
        DispatchOutcome.PARTIAL_CANDIDATE_PROGRESSION,
    }
)


class ReadyStep(Protocol):
    """The opt-in Ready step (Requirement-Autonomous-Ready-v0.1 §9)."""

    def __call__(self, workspace: RunnerWorkspace) -> CycleReport | None:
        """One decision, or None when there is nothing to decide."""

    def forget(self, entity_id: str) -> None:
        """A machine cycle was claimed for it: its next Ready is a new one."""


class RunnerPreflightError(Exception):
    """The workspace cannot host the runner; nothing was polled or written."""


class ProjectScopeError(Exception):
    """The Project scope cannot be established, or no longer holds.

    Nothing may run under it, and nothing falls back to the whole workspace.
    """


@dataclass(frozen=True)
class ProjectScope:
    """The one Project a scoped runner is bound to, as it was resolved at start."""

    project_id: str
    project_code: str
    workspace_identity: str


@dataclass(frozen=True)
class CycleReport:
    """What one cycle did, for the operator: identity and codes only.

    `requirement` is the Requirement as last read in the cycle, and
    `dispatch_result` the RW-O02 result when a worker ran. `details` name
    observed differences and Fibery failures, never Requirement content.
    `ready_decision` is the decision record of an opt-in Ready step.
    """

    outcome: CycleOutcome
    message: str
    requirement: RequirementRecord | None = None
    dispatch_result: DispatchResult | None = None
    details: tuple[str, ...] = ()
    ready_decision: ReadyDecisionRecord | None = None

    @property
    def should_wait(self) -> bool:
        return self.outcome in WAITING_OUTCOMES

    @property
    def is_normal(self) -> bool:
        return self.outcome in NORMAL_OUTCOMES


# -- the runner -------------------------------------------------------------------


def require_poll_interval(seconds: int) -> int:
    """The idle interval in whole seconds, refused below the RW-C04 minimum."""
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise TypeError(
            f"The poll interval must be a whole number of seconds, got {seconds!r}."
        )
    if seconds < MINIMUM_POLL_INTERVAL_SECONDS:
        raise ValueError(
            f"The poll interval must be at least {MINIMUM_POLL_INTERVAL_SECONDS} "
            f"second, got {seconds}."
        )
    return seconds


def preflight(workspace: RunnerWorkspace) -> None:
    """Refuse to start unless Processing Status is exactly RW-C04's single-select.

    The configured default and the reset automation are workspace settings the
    schema does not prove; the operator verifies them
    (docs/fibery/Worker-Runner-Setup-v0.1.md).
    """
    try:
        workspace.validate_processing_status_field(PROCESSING_STATUS_OPTIONS)
    except FiberyError as error:
        raise RunnerPreflightError(str(error)) from error


def resolve_project_scope(
    workspace: ScopedRunnerWorkspace, selector: str
) -> ProjectScope:
    """Bind the runner to the one Project whose Code is exactly `selector`.

    Only an exact Project Code is accepted: no Name, no case or whitespace
    normalization, no partial match. The Code must name exactly one Project,
    and that Project, read again by its entity id, must carry it. Any failure,
    a Fibery read failure included, raises ProjectScopeError. Cost: three
    reads, once per runner start.
    """
    try:
        code = validate_project_code(selector)
    except InvalidProjectCode as error:
        raise ProjectScopeError(
            f"--project takes one exact Project Code: {error}"
        ) from error
    if code != selector:
        raise ProjectScopeError(
            f"--project takes one exact Project Code; {selector!r} is not one "
            f"(did you mean {code!r}?)."
        )
    try:
        count = workspace.count_projects_with_code(code)
        project = workspace.find_project_by_code(code) if count == 1 else None
        current = workspace.read_project(project.id) if project is not None else None
    except FiberyError as error:
        raise ProjectScopeError(
            f"Project {code} could not be resolved: {error}"
        ) from error
    if count == 0:
        raise ProjectScopeError(f"No Project has the Code {code}.")
    if count != 1:
        raise ProjectScopeError(
            f"More than one Project has the Code {code}; the scope is ambiguous."
        )
    if (
        project is None
        or current is None
        or current.id != project.id
        or current.code != code
    ):
        raise ProjectScopeError(
            f"Project {code} did not read back as the same Project."
        )
    return ProjectScope(project.id, code, workspace.lock_scope)


def check_project_scope(workspace: ScopedRunnerWorkspace, scope: ProjectScope) -> None:
    """Raise ProjectScopeError unless the bound Project is still what was bound.

    Read fresh from Fibery: the same workspace, the same Project entity, the
    same Code. Cost: one Project read.
    """
    if workspace.lock_scope != scope.workspace_identity:
        raise ProjectScopeError(
            f"The workspace is {workspace.lock_scope!r}, not the "
            f"{scope.workspace_identity!r} Project {scope.project_code} was "
            "bound in."
        )
    try:
        current = workspace.read_project(scope.project_id)
    except FiberyError as error:
        raise ProjectScopeError(
            f"Project {scope.project_code} could not be read: {error}"
        ) from error
    if current is None or current.id != scope.project_id:
        raise ProjectScopeError(
            f"Project {scope.project_code} (entity {scope.project_id}) no longer "
            "exists."
        )
    if current.code != scope.project_code:
        raise ProjectScopeError(
            f"Project entity {scope.project_id} now has the Code "
            f"{current.code!r}, not {scope.project_code}."
        )


def run_requirement_runner(
    workspace: RunnerWorkspace,
    workers: RequirementWorkers,
    *,
    sleep: Callable[[float], None],
    report: Callable[[CycleReport], None],
    should_continue: Callable[[], bool],
    poll_interval_seconds: int = DEFAULT_POLL_INTERVAL_SECONDS,
    on_started: Callable[[int], None] | None = None,
    ready_decider: ReadyStep | None = None,
    scope: ProjectScope | None = None,
) -> None:
    """Run cycles one at a time for as long as `should_continue` answers True.

    Preflight comes first, so a workspace that cannot host the runner is
    refused before anything is polled or claimed; `on_started` hears the
    interval once it has passed. `sleep`, `report` and `should_continue` are
    the process's clock, output and stop condition, injected so a test drives
    exact cycles without waiting. A SCOPE_INVALID cycle is reported, then
    ends the runner with ProjectScopeError.
    """
    interval = require_poll_interval(poll_interval_seconds)
    preflight(workspace)
    if on_started is not None:
        on_started(interval)
    while should_continue():
        cycle = run_cycle(workspace, workers, ready_decider, scope)
        report(cycle)
        if cycle.outcome is CycleOutcome.SCOPE_INVALID:
            raise ProjectScopeError(cycle.message)
        if cycle.should_wait:
            sleep(interval)


def run_cycle(
    workspace: RunnerWorkspace,
    workers: RequirementWorkers,
    ready_decider: ReadyStep | None = None,
    scope: ProjectScope | None = None,
) -> CycleReport:
    """One poll, then at most one claimed and dispatched Requirement.

    Machine work always comes first; only a cycle that finds none offers the
    optional Ready step its turn, so it can never starve Process, Review or
    Apply. Under a `scope`, Fibery returns only that Project's work, and the
    Project is read again before the claim and before the dispatch.
    """
    try:
        polled = workspace.find_eligible_requirements(
            MACHINE_ROUTES,
            ProcessingStatus.NOT_PROCESSED.value,
            project_id=scope.project_id if scope is not None else None,
        )
    except FiberyError as error:
        return CycleReport(
            CycleOutcome.POLL_FAILED,
            "The eligible-work query failed; nothing was claimed.",
            details=(str(error),),
        )
    candidate = _lowest_eligible(polled)
    if candidate is None:
        decided = ready_decider(workspace) if ready_decider is not None else None
        return decided or CycleReport(
            CycleOutcome.IDLE, "No Requirement is eligible for machine work."
        )
    selection = _fresh_selection(workspace, candidate, scope)
    if isinstance(selection, CycleReport):
        return selection
    refused = _scope_refusal(workspace, scope, candidate, "its claim", claimed=False)
    if refused is not None:
        return refused
    claimed = _claim(workspace, selection.requirement, scope)
    if isinstance(claimed, CycleReport):
        return claimed
    refused = _scope_refusal(workspace, scope, claimed, "its dispatch", claimed=True)
    if refused is not None:
        return refused
    if ready_decider is not None:
        ready_decider.forget(claimed.id)
    return finalize_cycle(workspace, claimed, dispatch(workspace, workers, selection))


def _scope_refusal(
    workspace: ScopedRunnerWorkspace,
    scope: ProjectScope | None,
    requirement: RequirementRecord,
    before: str,
    *,
    claimed: bool,
) -> CycleReport | None:
    """SCOPE_INVALID when the bound Project no longer holds; None otherwise."""
    if scope is None:
        return None
    try:
        check_project_scope(workspace, scope)
    except ProjectScopeError as error:
        left = (
            "Its Processing claim stays as written for explicit recovery; "
            if claimed
            else ""
        )
        return CycleReport(
            CycleOutcome.SCOPE_INVALID,
            f"{_label(requirement)}: the Project scope no longer holds before "
            f"{before}. {left}nothing more was written and the runner stops.",
            requirement,
            details=(str(error),),
        )
    return None


# -- selection and claim ------------------------------------------------------------


def _lowest_eligible(polled: Sequence[RequirementRecord]) -> RequirementRecord | None:
    """The lowest public id among the rows whose own values select a route.

    Cost: one pass over one bounded poll page; no Fibery call.
    """
    return min(
        (record for record in polled if _selected(record) is not None),
        key=_public_id_order,
        default=None,
    )


def _selected(record: RequirementRecord) -> RouteSelection | None:
    """The route this record's Type, State and Processing Status select, if any."""
    try:
        status = ProcessingStatus(record.processing_status)
    except ValueError:
        return None
    selection = select_route(record, status)
    return selection if selection.decision is RouteDecision.ROUTE_SELECTED else None


def _public_id_order(record: RequirementRecord) -> tuple[bool, int, str]:
    """Numeric `fibery/public-id` order; a non-numeric id, never expected, sorts last."""
    numeric = record.public_id.isdigit()
    return (not numeric, int(record.public_id) if numeric else 0, record.public_id)


def _fresh_selection(
    workspace: RunnerWorkspace,
    candidate: RequirementRecord,
    scope: ProjectScope | None = None,
) -> RouteSelection | CycleReport:
    """Re-read the candidate and select its route again from what Fibery holds now.

    Under a scope the fresh record must also be in the bound Project, judged
    against the scope itself and not against the poll row.
    """
    try:
        fresh = workspace.read_requirement(candidate.id)
    except FiberyError as error:
        return CycleReport(
            CycleOutcome.CANDIDATE_READ_FAILED,
            f"{_label(candidate)} could not be re-read before its claim; nothing "
            "was written.",
            candidate,
            details=(str(error),),
        )
    changes = (*_differences(candidate, fresh, CYCLE_FIELDS), *_outside(fresh, scope))
    selection = None if fresh is None or changes else _selected(fresh)
    if selection is None:
        return CycleReport(
            CycleOutcome.CANDIDATE_CHANGED,
            f"{_label(candidate)} changed after the poll; no claim and no worker.",
            fresh or candidate,
            details=changes,
        )
    return selection


def _claim(
    workspace: RunnerWorkspace,
    requirement: RequirementRecord,
    scope: ProjectScope | None = None,
) -> RequirementRecord | CycleReport:
    """Processing Status = Processing, confirmed by read-back before any worker.

    Under a scope the read-back must also still be in the bound Project.
    """
    try:
        workspace.set_processing_status(
            requirement.id, ProcessingStatus.PROCESSING.value
        )
    except FiberyError as error:
        return CycleReport(
            CycleOutcome.CLAIM_FAILED,
            f"{_label(requirement)}: the Processing claim could not be written; no "
            "worker was started.",
            requirement,
            details=(str(error),),
        )
    claimed, conflicts = _observe(
        workspace, requirement, requirement.state, ProcessingStatus.PROCESSING
    )
    conflicts = (*conflicts, *_outside(claimed, scope))
    if claimed is None or conflicts:
        return CycleReport(
            CycleOutcome.CLAIM_NOT_CONFIRMED,
            f"{_label(requirement)}: the Processing claim was not confirmed; no "
            "worker was started and nothing else was written.",
            claimed or requirement,
            details=conflicts,
        )
    return claimed


# -- status finalization ------------------------------------------------------------


def finalize_cycle(
    workspace: RunnerWorkspace, claimed: RequirementRecord, result: DispatchResult
) -> CycleReport:
    """Leave the visible status true after the dispatch of a confirmed claim.

    Succeeded or Failed is written only over this cycle's own Processing, in
    the State the outcome must have left, and confirmed by reading it back.
    Standard Process -> Review is only observed: the new Review cycle's reset
    belongs to the Fibery automation, and writing Succeeded after it would
    make Review ineligible for good. Any other outcome leaves the current State
    unestablished, so nothing is written.
    """
    route = result.selection.route
    if route is None:
        return _partial(claimed, result, ("no route was dispatched",))
    if result.outcome is DispatchOutcome.ROUTE_COMPLETED:
        if route.worker is Worker.STANDARD_PROCESS:
            return _observe_handoff(workspace, claimed, result, route.completed_state)
        return _settle(
            workspace,
            claimed,
            result,
            route.completed_state,
            ProcessingStatus.SUCCEEDED,
        )
    if result.outcome in FAILED_IN_CLAIMED_STATE:
        return _settle(workspace, claimed, result, route.state, ProcessingStatus.FAILED)
    if result.outcome in FAILED_AFTER_RAW_REVIEW:
        return _settle(
            workspace, claimed, result, route.completed_state, ProcessingStatus.FAILED
        )
    return _partial(
        claimed,
        result,
        (f"{result.outcome.value} leaves the current State unestablished",),
    )


def _settle(
    workspace: RunnerWorkspace,
    claimed: RequirementRecord,
    result: DispatchResult,
    state: str,
    final: ProcessingStatus,
) -> CycleReport:
    """Write `final` over this claimed cycle only, then confirm it by reading back."""
    current, conflicts = _observe(
        workspace, claimed, state, ProcessingStatus.PROCESSING
    )
    if current is None or conflicts:
        return _partial(current or claimed, result, conflicts)
    try:
        workspace.set_processing_status(claimed.id, final.value)
    except FiberyError as error:
        return _partial(current, result, (f"the {final.value} write failed: {error}",))
    settled, conflicts = _observe(workspace, claimed, state, final)
    if settled is None or conflicts:
        return _partial(settled or current, result, conflicts)
    return CycleReport(
        CycleOutcome.SUCCEEDED
        if final is ProcessingStatus.SUCCEEDED
        else CycleOutcome.FAILED,
        f"{_label(settled)}: {result.outcome.value}; Processing Status is "
        f"{final.value}.",
        settled,
        result,
    )


def _observe_handoff(
    workspace: RunnerWorkspace,
    claimed: RequirementRecord,
    result: DispatchResult,
    review_state: str,
) -> CycleReport:
    """Standard Process -> Review: look at the new Review cycle, write nothing."""
    current, conflicts = _observe(
        workspace,
        claimed,
        review_state,
        ProcessingStatus.NOT_PROCESSED,
        BINDING_FIELDS,
    )
    if current is None or conflicts:
        return _partial(current or claimed, result, conflicts)
    if current.processing_status != ProcessingStatus.NOT_PROCESSED.value:
        return CycleReport(
            CycleOutcome.RESET_NOT_OBSERVED,
            f"{_label(current)}: Standard Process moved it to {review_state}, but "
            f"Processing Status reads {current.processing_status!r}, not "
            f"{ProcessingStatus.NOT_PROCESSED.value}. Nothing was written and "
            f"{review_state} does not start. The reset belongs to the Fibery "
            "automation, which may still apply it; if it does not, check the "
            "automation's configuration.",
            current,
            result,
        )
    return CycleReport(
        CycleOutcome.HANDED_OFF,
        f"{_label(current)}: Standard Process handed off to a new {review_state} "
        f"cycle at {ProcessingStatus.NOT_PROCESSED.value}; nothing was written.",
        current,
        result,
    )


def _partial(
    requirement: RequirementRecord,
    result: DispatchResult,
    conflicts: tuple[str, ...],
) -> CycleReport:
    return CycleReport(
        CycleOutcome.PARTIAL,
        f"{_label(requirement)}: {result.outcome.value}, but this cycle's final "
        "Processing Status cannot be safely established. Status and State are "
        "left as observed, the worker is not run again, and recovery is explicit "
        "(RW-C04 section 25).",
        requirement,
        result,
        conflicts,
    )


# -- reads ----------------------------------------------------------------------


def _observe(
    workspace: RunnerWorkspace,
    cycle: RequirementRecord,
    state: str,
    status: ProcessingStatus,
    fields: tuple[tuple[str, str], ...] = CYCLE_FIELDS,
) -> tuple[RequirementRecord | None, tuple[str, ...]]:
    """Read the Requirement again and name every way it differs from the
    expected cycle: the same binding, in `state`, at `status`."""
    try:
        current = workspace.read_requirement(cycle.id)
    except FiberyError as error:
        return None, (f"read failed: {error}",)
    expected = replace(cycle, state=state, processing_status=status.value)
    return current, _differences(expected, current, fields)


def _outside(
    record: RequirementRecord | None, scope: ProjectScope | None
) -> tuple[str, ...]:
    """Why `record` is not in the bound Project; empty when it is, or unscoped."""
    if scope is None or record is None or record.project_id == scope.project_id:
        return ()
    return (
        (
            f"Project: {record.project_id!r} is outside the scope of Project "
            f"{scope.project_code} ({scope.project_id})"
        ),
    )


def _differences(
    expected: RequirementRecord,
    current: RequirementRecord | None,
    fields: tuple[tuple[str, str], ...],
) -> tuple[str, ...]:
    if current is None:
        return (f"entity {expected.id} no longer exists",)
    return tuple(
        f"{name}: expected {getattr(expected, field)!r}, read "
        f"{getattr(current, field)!r}"
        for field, name in fields
        if getattr(expected, field) != getattr(current, field)
    )


def _label(requirement: RequirementRecord) -> str:
    identity = requirement.requirement_id or requirement.id
    return f"{identity} ({requirement.type_name} + {requirement.state})"
