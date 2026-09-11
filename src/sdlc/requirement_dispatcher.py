"""The bounded Requirement worker dispatcher (RW-O02).

Implements the routing of Requirement-State-Worker-Contract-v0.1 (RW-C04)
inside the boundary frozen by RW-O02-Implementation-Boundary-v0.1. Fibery
State is the authority (Requirement-Lifecycle-Ownership-v0.2): the dispatcher
executes machine work that State has already authorized, and nothing else.

The only machine routes:

    Raw      + Process + Not Processed -> RAW Requirement Processor
    Standard + Process + Not Processed -> Standard Requirement Process
    Standard + Review  + Not Processed -> Standard Requirement Review
    Standard + Apply   + Not Processed -> Standard Requirement Apply

Every other combination selects no worker: the human boundaries Raw Draft and
Standard Ready, the settled Raw Review and Standard Applied, a generic
Standard Draft (its existence is not inherited authority), unsupported states,
and any Processing Status but Not Processed, so a claimed, completed or failed
cycle never runs again automatically.

Selection and execution are separate so the RW-O03 runner can claim the cycle
between them. `select_route` is pure over a Requirement the runner has read
and the status it supplies. `dispatch` re-reads the Requirement, refuses a
selection whose identity, Type or State moved, runs exactly one already-bound
worker, and classifies that worker's typed result. A normal result completes
the route only when the worker's own lifecycle postcondition holds; the
dispatcher never writes those transitions. One dispatch runs one worker and
never chains Process into Review.

The single State the dispatcher writes is the inherited `Draft -> Process` of
the Standard candidates named by a successful RAW result, and only after every
one of them is confirmed as that RAW's Standard Draft. Standard Process is
invoked as an authorized new machine cycle (CR-002), so a human rework over an
unchanged tree produces the next iteration.

Polling, the Processing Status field, runner locking and `sdlc worker run`
belong to RW-O03. No model runtime is chosen here: workers arrive bound.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sdlc.fibery_workspace import DispatchWorkspace, FiberyError, RequirementRecord
from sdlc.results import (
    ApplyResult,
    ProcessResult,
    StandardProcessResult,
    StandardReviewResult,
)

RAW_TYPE = "Raw"
STANDARD_TYPE = "Standard"
DRAFT_STATE = "Draft"
PROCESS_STATE = "Process"
REVIEW_STATE = "Review"
READY_STATE = "Ready"
APPLY_STATE = "Apply"
APPLIED_STATE = "Applied"


class ProcessingStatus(StrEnum):
    """The RW-C04 Processing Status vocabulary, as supplied by the runner.

    Route semantics only: this module neither reads nor writes the field.
    """

    NOT_PROCESSED = "Not Processed"
    PROCESSING = "Processing"
    SUCCEEDED = "Succeeded"
    FAILED = "Failed"


class Worker(StrEnum):
    """The four existing Requirement workers a route can run."""

    RAW_PROCESS = "RAW_PROCESS"
    STANDARD_PROCESS = "STANDARD_PROCESS"
    STANDARD_REVIEW = "STANDARD_REVIEW"
    STANDARD_APPLY = "STANDARD_APPLY"


@dataclass(frozen=True)
class Route:
    """Where a worker runs and the State its success must leave behind."""

    type_name: str
    state: str
    worker: Worker
    completed_state: str


ROUTES = {
    (RAW_TYPE, PROCESS_STATE): Route(
        RAW_TYPE, PROCESS_STATE, Worker.RAW_PROCESS, REVIEW_STATE
    ),
    (STANDARD_TYPE, PROCESS_STATE): Route(
        STANDARD_TYPE, PROCESS_STATE, Worker.STANDARD_PROCESS, REVIEW_STATE
    ),
    (STANDARD_TYPE, REVIEW_STATE): Route(
        STANDARD_TYPE, REVIEW_STATE, Worker.STANDARD_REVIEW, READY_STATE
    ),
    (STANDARD_TYPE, APPLY_STATE): Route(
        STANDARD_TYPE, APPLY_STATE, Worker.STANDARD_APPLY, APPLIED_STATE
    ),
}


class RouteDecision(StrEnum):
    """Why a route was, or was not, selected."""

    ROUTE_SELECTED = "ROUTE_SELECTED"
    HUMAN_BOUNDARY = "HUMAN_BOUNDARY"
    NO_MACHINE_WORK = "NO_MACHINE_WORK"
    STATUS_NOT_ELIGIBLE = "STATUS_NOT_ELIGIBLE"
    UNSUPPORTED_STATE = "UNSUPPORTED_STATE"


# RW-C04 section 11: the explicit no-worker states and the reason for each.
NO_ROUTE_STATES = {
    (RAW_TYPE, DRAFT_STATE): (
        RouteDecision.HUMAN_BOUNDARY,
        "the human has not authorized RAW processing",
    ),
    (RAW_TYPE, REVIEW_STATE): (
        RouteDecision.NO_MACHINE_WORK,
        "the RAW decomposition cycle is complete and kept as source and history",
    ),
    (STANDARD_TYPE, DRAFT_STATE): (
        RouteDecision.NO_MACHINE_WORK,
        "a Draft observed on its own is not inherited authorization",
    ),
    (STANDARD_TYPE, READY_STATE): (
        RouteDecision.HUMAN_BOUNDARY,
        "the human approval or rework decision is due",
    ),
    (STANDARD_TYPE, APPLIED_STATE): (
        RouteDecision.NO_MACHINE_WORK,
        "application already completed",
    ),
}
UNSUPPORTED_REASON = (
    "no machine route exists for this Type and State; nothing is repaired"
)


@dataclass(frozen=True)
class RouteSelection:
    """The route chosen for one Requirement as read, or why there is none."""

    requirement: RequirementRecord
    status: ProcessingStatus
    decision: RouteDecision
    reason: str
    route: Route | None = None


class RawWorker(Protocol):
    def __call__(self, entity_id: str) -> ProcessResult: ...


class StandardProcessWorker(Protocol):
    def __call__(
        self, entity_id: str, *, authorized_new_cycle: bool
    ) -> StandardProcessResult: ...


class StandardReviewWorker(Protocol):
    def __call__(self, entity_id: str) -> StandardReviewResult: ...


class StandardApplyWorker(Protocol):
    def __call__(self, entity_id: str) -> ApplyResult: ...


@dataclass(frozen=True)
class RequirementWorkers:
    """The four existing capabilities, already bound to a workspace and runtime."""

    process_raw: RawWorker
    process_standard: StandardProcessWorker
    review_standard: StandardReviewWorker
    apply_standard: StandardApplyWorker


class DispatchOutcome(StrEnum):
    """Everything one dispatch can report. Only ROUTE_COMPLETED is a finished cycle."""

    ROUTE_COMPLETED = "ROUTE_COMPLETED"
    NO_ROUTE = "NO_ROUTE"
    STALE_ROUTE = "STALE_ROUTE"
    WORKER_FAILED = "WORKER_FAILED"
    POSTCONDITION_NOT_REACHED = "POSTCONDITION_NOT_REACHED"
    CANDIDATE_PROGRESSION_CONFLICT = "CANDIDATE_PROGRESSION_CONFLICT"
    CANDIDATE_PROGRESSION_FAILED = "CANDIDATE_PROGRESSION_FAILED"
    PARTIAL_CANDIDATE_PROGRESSION = "PARTIAL_CANDIDATE_PROGRESSION"
    FIBERY_READ_FAILED = "FIBERY_READ_FAILED"


WorkerResult = (
    ProcessResult | StandardProcessResult | StandardReviewResult | ApplyResult
)


@dataclass(frozen=True)
class DispatchResult:
    """The outcome of one dispatch, with the worker's own typed result when it ran.

    `progressed` names the RAW candidates confirmed in Process; after a
    failed progression write they stay there, and the failing candidate is
    named in `details`.
    """

    outcome: DispatchOutcome
    message: str
    selection: RouteSelection
    worker_result: WorkerResult | None = None
    state_after: str | None = None
    progressed: tuple[str, ...] = ()
    details: tuple[str, ...] = ()

    @property
    def is_completed(self) -> bool:
        return self.outcome is DispatchOutcome.ROUTE_COMPLETED


# -- selection ----------------------------------------------------------------


def select_route(
    requirement: RequirementRecord, status: ProcessingStatus
) -> RouteSelection:
    """The worker this Type + State + pre-claim Processing Status authorizes, if any.

    Pure: the runner reads the Requirement and supplies its status.
    """
    key = (requirement.type_name, requirement.state)
    route = ROUTES.get(key)
    label = _label(requirement)
    if route is None:
        decision, reason = NO_ROUTE_STATES.get(
            key, (RouteDecision.UNSUPPORTED_STATE, UNSUPPORTED_REASON)
        )
        return RouteSelection(requirement, status, decision, f"{label}: {reason}.")
    if status is not ProcessingStatus.NOT_PROCESSED:
        return RouteSelection(
            requirement,
            status,
            RouteDecision.STATUS_NOT_ELIGIBLE,
            f"{label}: Processing Status is {status.value}; only Not Processed "
            "starts a machine cycle, and failed work is not retried automatically.",
        )
    return RouteSelection(
        requirement,
        status,
        RouteDecision.ROUTE_SELECTED,
        f"{label}: {route.worker.value}.",
        route,
    )


# -- execution ----------------------------------------------------------------


def dispatch(
    workspace: DispatchWorkspace,
    workers: RequirementWorkers,
    selection: RouteSelection,
) -> DispatchResult:
    """Run the one worker of an already selected route and classify its result."""
    route = selection.route
    if route is None:
        return DispatchResult(DispatchOutcome.NO_ROUTE, selection.reason, selection)
    selected = selection.requirement
    try:
        current = workspace.read_requirement(selected.id)
    except FiberyError as error:
        return DispatchResult(
            DispatchOutcome.FIBERY_READ_FAILED,
            f"Could not re-read {_label(selected)} before {route.worker.value}; "
            "no worker was called.",
            selection,
            details=(str(error),),
        )
    drift = _route_drift(selected, current)
    if drift:
        return DispatchResult(
            DispatchOutcome.STALE_ROUTE,
            f"{_label(selected)} changed after its route was selected; no worker "
            "was called and nothing was written.",
            selection,
            details=drift,
        )

    worker_result = _run(workers, route, selected.id)
    if not worker_result.is_normal:
        return DispatchResult(
            DispatchOutcome.WORKER_FAILED,
            f"{route.worker.value} returned {worker_result.code.value}; the "
            "Requirement is left where the worker left it.",
            selection,
            worker_result,
            details=(worker_result.message, *worker_result.details),
        )
    return _check_postcondition(workspace, selection, route, worker_result)


def _run(workers: RequirementWorkers, route: Route, entity_id: str) -> WorkerResult:
    if route.worker is Worker.RAW_PROCESS:
        return workers.process_raw(entity_id)
    if route.worker is Worker.STANDARD_PROCESS:
        # CR-002: this route exists only for a cycle the State just authorized.
        return workers.process_standard(entity_id, authorized_new_cycle=True)
    if route.worker is Worker.STANDARD_REVIEW:
        return workers.review_standard(entity_id)
    return workers.apply_standard(entity_id)


def _check_postcondition(
    workspace: DispatchWorkspace,
    selection: RouteSelection,
    route: Route,
    worker_result: WorkerResult,
) -> DispatchResult:
    """A normal result completes the cycle only in the State its worker owns."""
    selected = selection.requirement
    code = worker_result.code.value
    try:
        after = workspace.read_requirement(selected.id)
    except FiberyError as error:
        return DispatchResult(
            DispatchOutcome.FIBERY_READ_FAILED,
            f"{route.worker.value} returned {code}, but {_label(selected)} could "
            f"not be re-read to confirm {route.completed_state}.",
            selection,
            worker_result,
            details=(str(error),),
        )
    state_after = after.state if after is not None else None
    if state_after != route.completed_state:
        return DispatchResult(
            DispatchOutcome.POSTCONDITION_NOT_REACHED,
            f"{route.worker.value} returned {code}, but {_label(selected)} is in "
            f"{state_after!r}, not {route.completed_state!r}; this cycle is not "
            "complete and the dispatcher wrote nothing.",
            selection,
            worker_result,
            state_after,
        )
    if route.worker is Worker.RAW_PROCESS:
        return _progress_candidates(workspace, selection, worker_result, state_after)
    return DispatchResult(
        DispatchOutcome.ROUTE_COMPLETED,
        f"{route.worker.value} completed; {_label(selected)} is now {state_after}.",
        selection,
        worker_result,
        state_after,
    )


def _route_drift(
    selected: RequirementRecord, current: RequirementRecord | None
) -> tuple[str, ...]:
    if current is None:
        return (f"entity {selected.id} no longer exists",)
    return tuple(
        f"{name} {getattr(selected, field)!r} -> {getattr(current, field)!r}"
        for field, name in (
            ("requirement_id", "Requirement ID"),
            ("type_name", "Type"),
            ("state", "State"),
        )
        if getattr(selected, field) != getattr(current, field)
    )


def _label(requirement: RequirementRecord) -> str:
    identity = requirement.requirement_id or requirement.id
    return f"{identity} ({requirement.type_name} + {requirement.state})"


# -- inherited candidate progression ------------------------------------------


def _progress_candidates(
    workspace: DispatchWorkspace,
    selection: RouteSelection,
    raw_result: ProcessResult,
    state_after: str,
) -> DispatchResult:
    """Move exactly the Standard candidates of this RAW result Draft -> Process.

    Every named candidate is preflighted before the first write, so a conflict
    anywhere leaves the whole set untouched. A write failure after writes
    began is reported as it is: nothing is rolled back or demoted.
    """
    raw = selection.requirement
    try:
        candidates, conflicts = _preflight(workspace, raw, raw_result.candidates)
    except FiberyError as error:
        return DispatchResult(
            DispatchOutcome.FIBERY_READ_FAILED,
            f"{_label(raw)} was processed, but its candidates could not be read; "
            "no candidate was progressed.",
            selection,
            raw_result,
            state_after,
            details=(str(error),),
        )
    if conflicts:
        return DispatchResult(
            DispatchOutcome.CANDIDATE_PROGRESSION_CONFLICT,
            f"{_label(raw)} was processed, but not every candidate it names is its "
            "own Standard Draft; no candidate was progressed.",
            selection,
            raw_result,
            state_after,
            details=conflicts,
        )
    progressed: list[str] = []
    for candidate in candidates:
        failure = _progress(workspace, candidate)
        if failure is not None:
            return DispatchResult(
                DispatchOutcome.PARTIAL_CANDIDATE_PROGRESSION
                if progressed
                else DispatchOutcome.CANDIDATE_PROGRESSION_FAILED,
                f"{_label(raw)} was processed, but candidate progression stopped; "
                "candidates listed as progressed stay in Process and nothing was "
                "rolled back.",
                selection,
                raw_result,
                state_after,
                progressed=tuple(progressed),
                details=(failure,),
            )
        progressed.append(candidate.requirement_id or candidate.id)
    return DispatchResult(
        DispatchOutcome.ROUTE_COMPLETED,
        f"{_label(raw)} processed; {len(progressed)} candidate(s) moved "
        f"{DRAFT_STATE} -> {PROCESS_STATE}.",
        selection,
        raw_result,
        state_after,
        progressed=tuple(progressed),
    )


def _preflight(
    workspace: DispatchWorkspace,
    raw: RequirementRecord,
    requirement_ids: Sequence[str],
) -> tuple[list[RequirementRecord], tuple[str, ...]]:
    """Resolve every candidate the RAW result names; nothing is written here.

    Cost: one lookup and at most one provenance read per candidate of one RAW
    result, a set the RAW decomposition bounds. No other Requirement is read.
    """
    candidates: list[RequirementRecord] = []
    conflicts: list[str] = []
    for requirement_id in requirement_ids:
        matches = workspace.find_requirements_by_requirement_id(requirement_id)
        if len(matches) != 1:
            count = "no Requirement" if not matches else "more than one Requirement"
            conflicts.append(f"{requirement_id}: resolves to {count}")
            continue
        [candidate] = matches
        problem = _candidate_problem(workspace, raw, candidate)
        if problem is None:
            candidates.append(candidate)
        else:
            conflicts.append(f"{requirement_id}: {problem}")
    return candidates, tuple(conflicts)


def _candidate_problem(
    workspace: DispatchWorkspace, raw: RequirementRecord, candidate: RequirementRecord
) -> str | None:
    if candidate.type_name != STANDARD_TYPE:
        return f"Type is {candidate.type_name!r}, not {STANDARD_TYPE}"
    if candidate.state != DRAFT_STATE:
        return f"State is {candidate.state!r}, not {DRAFT_STATE}; it is left as it is"
    if raw.id not in {source.id for source in workspace.derived_from(candidate.id)}:
        return f"does not derive from {raw.requirement_id or raw.id}"
    return None


def _progress(workspace: DispatchWorkspace, candidate: RequirementRecord) -> str | None:
    """Write one candidate's State and confirm it; the failure, if any."""
    identity = candidate.requirement_id or candidate.id
    try:
        workspace.set_requirement_state(candidate.id, PROCESS_STATE)
        back = workspace.read_requirement(candidate.id)
    except FiberyError as error:
        return (
            f"{identity}: {error}; whether its {PROCESS_STATE} write took effect "
            "is not confirmed"
        )
    if back is None or back.state != PROCESS_STATE:
        observed = back.state if back is not None else None
        return f"{identity}: State reads back as {observed!r}, not {PROCESS_STATE}"
    return None
