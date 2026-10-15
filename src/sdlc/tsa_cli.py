"""TSA-C01 I12 — the `sdlc project architecture` commands, as results.

I12 wires; I04-I11 decide. Each command here resolves the Project, calls the
domain entry points that own every decision — I04 discovery and the bootstrap
gate, I05 admission and the Input Manifest, the I10 normal gate and recovery,
the I11 Human Decision — and maps what they established, or the frozen code
they refused with, onto the command x durable-state table (spec 13.6) and the
result-code catalogue (spec 13.8, plus the v0.5 delta). It discovers nothing,
admits nothing, runs no stage and resolves no Decision target of its own.

What only this layer owns: the outer workspace guard around a mutating
command (contract 13), the lazy TSA model roles (spec 15), the mapping of a
domain outcome to one result code and its exit class (spec 12.3), and the
rendering. `cli.py` owns argparse and builds the adapters.

Approved additions to the catalogue, recorded by the human instruction of
2026-10-15 for this item (no spec file carries them yet):

- `WORKSPACE_GUARD_UNAVAILABLE`, exit 1: the workspace guard could not be set
  up, so the command did not run, rather than run unguarded;
- a recovery that stops short of the Human Decision boundary (I10
  `ARCHITECT_REQUIRED` / `REVIEWER_REQUIRED`) reports
  `ARCHITECTURE_CYCLE_RESUMED` and says so;
- a Fibery workspace that cannot be established before any engine runs is
  `FIBERY_READ_FAILED`; a TSA role that cannot be configured fails when it is
  first asked to run, inside its stage, as `MODEL_RUNTIME_FAILED`;
- `inspect --json` prints the code line, a blank line, then one JSON object.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, TextIO

from sdlc.fibery_workspace import FiberyError, ProjectRecord
from sdlc.model_runtime import ModelResponse, ModelRuntime, ModelRuntimeError
from sdlc.model_runtime_config import ModelRuntimeConfigError
from sdlc.tsa_admission import (
    AdmissionRefused,
    RequirementEvidenceWorkspace,
    StartInputs,
    start_input_manifest,
)
from sdlc.tsa_architect import (
    ArchitectRefused,
    CycleState,
    read_cycle_state,
    read_input_currentness,
)
from sdlc.tsa_cycle import (
    Clock,
    CycleDiscovery,
    CycleOutcome,
    CycleRefused,
    CycleWorkspace,
    discover_cycle,
    ensure_bootstrap_architecture,
)
from sdlc.tsa_decision import (
    AcceptedDisposition,
    DecisionRefused,
    DecisionResult,
    DecisionResultCode,
    record_approve,
    record_rework,
)
from sdlc.tsa_recovery import (
    RecoveryBoundary,
    RecoveryCase,
    RecoveryRefused,
    RecoveryResult,
    classify_recovery_case,
    recover_architecture_cycle,
)
from sdlc.worker_runner_guard import (
    WorkerRunnerBusy,
    WorkerRunnerGuardUnavailable,
    hold_workspace,
)

EXIT_NORMAL = 0
EXIT_REFUSED = 1


class TsaResultCode(StrEnum):
    """Spec 13.8 complete, the v0.5 addition, and the one approved addition."""

    ARCHITECTURE_CYCLE_STARTED = "ARCHITECTURE_CYCLE_STARTED"
    ARCHITECTURE_CYCLE_RESUMED = "ARCHITECTURE_CYCLE_RESUMED"
    ARCHITECTURE_REVIEW_READY = "ARCHITECTURE_REVIEW_READY"
    ARCHITECTURE_REWORK_RECORDED = "ARCHITECTURE_REWORK_RECORDED"
    ARCHITECTURE_APPROVED = "ARCHITECTURE_APPROVED"
    DECISION_ALREADY_RECORDED = "DECISION_ALREADY_RECORDED"
    CYCLE_APPROVED = "CYCLE_APPROVED"
    CYCLE_NOT_FOUND = "CYCLE_NOT_FOUND"
    CYCLE_AMBIGUOUS = "CYCLE_AMBIGUOUS"
    CYCLE_FOREIGN_PROJECT = "CYCLE_FOREIGN_PROJECT"
    INVALID_CYCLE_ID = "INVALID_CYCLE_ID"
    ITERATION_LIMIT = "ITERATION_LIMIT"
    SELECTION_EMPTY = "SELECTION_EMPTY"
    SELECTION_DUPLICATE = "SELECTION_DUPLICATE"
    REQUIREMENT_NOT_ADMISSIBLE = "REQUIREMENT_NOT_ADMISSIBLE"
    UX_EVIDENCE_INVALID = "UX_EVIDENCE_INVALID"
    UX_SCOPE_FOREIGN = "UX_SCOPE_FOREIGN"
    HUMAN_ACCEPTANCE_REQUIRED = "HUMAN_ACCEPTANCE_REQUIRED"
    MANIFEST_ACCEPTANCE_MISMATCH = "MANIFEST_ACCEPTANCE_MISMATCH"
    MANIFEST_INPUTS_REQUIRED = "MANIFEST_INPUTS_REQUIRED"
    MANIFEST_SHELL_UNRECOVERABLE = "MANIFEST_SHELL_UNRECOVERABLE"
    MANIFEST_INPUTS_CONFLICT = "MANIFEST_INPUTS_CONFLICT"
    INPUTS_STALE = "INPUTS_STALE"
    INPUT_TOO_LARGE = "INPUT_TOO_LARGE"
    ARCHITECTURE_DIVERGED = "ARCHITECTURE_DIVERGED"
    ARCHITECTURE_RENDER_INVALID = "ARCHITECTURE_RENDER_INVALID"
    ARTIFACT_MALFORMED = "ARTIFACT_MALFORMED"
    ARTIFACT_DUPLICATE = "ARTIFACT_DUPLICATE"
    TRACEABILITY_MISSING_REQUIREMENT = "TRACEABILITY_MISSING_REQUIREMENT"
    TRACEABILITY_UNKNOWN_REQUIREMENT = "TRACEABILITY_UNKNOWN_REQUIREMENT"
    TRACEABILITY_DUPLICATE_REQUIREMENT = "TRACEABILITY_DUPLICATE_REQUIREMENT"
    TRACEABILITY_UNKNOWN_ANCHOR = "TRACEABILITY_UNKNOWN_ANCHOR"
    TRACEABILITY_DUPLICATE_ANCHOR = "TRACEABILITY_DUPLICATE_ANCHOR"
    SECTION_MANDATORY_EMPTY = "SECTION_MANDATORY_EMPTY"
    REVIEW_COVERAGE_INCOMPLETE = "REVIEW_COVERAGE_INCOMPLETE"
    REVIEW_COVERAGE_DUPLICATE = "REVIEW_COVERAGE_DUPLICATE"
    REVIEW_STRUCTURALLY_INVALID = "REVIEW_STRUCTURALLY_INVALID"
    REVIEW_BLOCKED_ON_WHAT = "REVIEW_BLOCKED_ON_WHAT"
    DISPOSITION_UNKNOWN_REFERENCE = "DISPOSITION_UNKNOWN_REFERENCE"
    DISPOSITION_DUPLICATE_REFERENCE = "DISPOSITION_DUPLICATE_REFERENCE"
    DISPOSITION_FOREIGN_ITERATION = "DISPOSITION_FOREIGN_ITERATION"
    DISPOSITION_NOT_WAIVABLE = "DISPOSITION_NOT_WAIVABLE"
    DECISION_CONFLICT = "DECISION_CONFLICT"
    MODEL_RUNTIME_FAILED = "MODEL_RUNTIME_FAILED"
    INVALID_MODEL_OUTPUT = "INVALID_MODEL_OUTPUT"
    INSPECT_CURRENT = "INSPECT_CURRENT"
    INSPECT_STALE = "INSPECT_STALE"
    INSPECT_INCOMPLETE = "INSPECT_INCOMPLETE"
    DECISION_SHELL_UNRECOVERABLE = "DECISION_SHELL_UNRECOVERABLE"
    REVIEW_NOT_CURRENT = "REVIEW_NOT_CURRENT"
    WORKSPACE_BUSY = "WORKSPACE_BUSY"
    FIBERY_READ_FAILED = "FIBERY_READ_FAILED"
    FIBERY_WRITE_FAILED = "FIBERY_WRITE_FAILED"
    #: Spec v0.5 section 2.
    REVIEW_INPUT_CHANGED = "REVIEW_INPUT_CHANGED"
    #: Approved addition (module docstring): the guard could not be set up.
    WORKSPACE_GUARD_UNAVAILABLE = "WORKSPACE_GUARD_UNAVAILABLE"


#: Spec 13.8 exit class 0: a normal outcome, a correct no-op included. Every
#: other code is exit class 1; exit 2 is argparse's alone.
NORMAL_CODES = frozenset(
    {
        TsaResultCode.ARCHITECTURE_CYCLE_STARTED,
        TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
        TsaResultCode.ARCHITECTURE_REVIEW_READY,
        TsaResultCode.ARCHITECTURE_REWORK_RECORDED,
        TsaResultCode.ARCHITECTURE_APPROVED,
        TsaResultCode.DECISION_ALREADY_RECORDED,
        TsaResultCode.CYCLE_APPROVED,
        TsaResultCode.INSPECT_CURRENT,
        TsaResultCode.INSPECT_STALE,
        TsaResultCode.INSPECT_INCOMPLETE,
    }
)


def exit_code_for(code: TsaResultCode) -> int:
    """The one exit-class mapping of spec 12.3 and 13.8."""
    return EXIT_NORMAL if code in NORMAL_CODES else EXIT_REFUSED


class InputCurrentness(StrEnum):
    """What `inspect` established about the bound inputs (contract 4.4)."""

    CURRENT = "CURRENT"
    STALE = "STALE"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


class Command(StrEnum):
    START = "start"
    RESUME = "resume"


#: Spec 13.6, column `start`, for a cycle already in state D, by the case the
#: first gate read (I10 `classify_recovery_case`). A REWORK-opened iteration
#: with nothing in it yet is case 6 and is decided before this table.
START_CODES = {
    RecoveryCase.DRAFT: TsaResultCode.ARCHITECTURE_REVIEW_READY,
    RecoveryCase.RECORDED_INPUT: TsaResultCode.ARCHITECTURE_REVIEW_READY,
    RecoveryCase.OUTPUT_APPLIED: TsaResultCode.ARCHITECTURE_REVIEW_READY,
    RecoveryCase.PROCESS_SHELL: TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
    RecoveryCase.REVIEW_SHELL: TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
    RecoveryCase.REVIEW_RECORDED: TsaResultCode.ARCHITECTURE_REVIEW_READY,
    RecoveryCase.APPROVED: TsaResultCode.CYCLE_APPROVED,
}
#: Spec 13.6, column `resume`, for state D.
RESUME_CODES = {
    RecoveryCase.DRAFT: TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
    RecoveryCase.RECORDED_INPUT: TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
    RecoveryCase.OUTPUT_APPLIED: TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
    RecoveryCase.PROCESS_SHELL: TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
    RecoveryCase.REVIEW_SHELL: TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
    RecoveryCase.REVIEW_RECORDED: TsaResultCode.ARCHITECTURE_REVIEW_READY,
    RecoveryCase.APPROVED: TsaResultCode.CYCLE_APPROVED,
}
CONTINUING_CODES = {Command.START: START_CODES, Command.RESUME: RESUME_CODES}

#: Gate refusals that spec 13.6 still reports as a derived, current state in
#: the `inspect` column, once currentness is established on its own.
INSPECTED_AS_DERIVED = frozenset(
    {TsaResultCode.ARTIFACT_DUPLICATE, TsaResultCode.DECISION_SHELL_UNRECOVERABLE}
)
#: Refusals that say nothing about the cycle: `inspect` reports them as is.
INSPECT_PASSES_THROUGH = frozenset(
    {
        TsaResultCode.FIBERY_READ_FAILED,
        TsaResultCode.INVALID_CYCLE_ID,
        TsaResultCode.CYCLE_NOT_FOUND,
    }
)
STOPPED_SHORT = frozenset(
    {RecoveryBoundary.ARCHITECT_REQUIRED, RecoveryBoundary.REVIEWER_REQUIRED}
)

NEXT_DECISION = (
    "Nothing is approved: a human decides with `sdlc project architecture "
    "approve` or `rework` against this exact iteration and Review Result."
)
BUSY_MESSAGE = (
    "Another cooperating SDLC command holds this Fibery workspace on this host "
    "(same OS user, same lock directory). Nothing was read or written and no "
    "model was called."
)
GUARD_UNAVAILABLE_MESSAGE = (
    "The workspace guard could not be set up ({error}), so the command did not "
    "run unguarded. Nothing was read or written and no model was called."
)
WORKSPACE_UNAVAILABLE_MESSAGE = (
    "The Fibery workspace could not be established ({error}). No cycle was "
    "read and nothing was written."
)

#: The human label of each fact, in the order facts are built.
FACT_LABELS = {
    "project_id": "Project",
    "cycle_id": "Cycle",
    "state": "Durable state",
    "case": "Recovery case",
    "inputs": "Inputs",
    "iteration": "Iteration",
    "architecture": "Architecture",
    "process_result": "Process Result",
    "review_result": "Review Result",
    "human_decision": "Human Decision",
    "architect_stage": "Architect stage",
    "reviewer_stage": "Reviewer stage",
    "continued_iteration": "Continued at iteration",
    "continued_review_result": "Continued Review Result",
}

Fact = tuple[str, object]


@dataclass(frozen=True)
class ArchitectureCommandResult:
    """One command's outcome: a frozen code, a truthful message, its facts.

    `facts` are identities and digests only — never Requirement content,
    architecture prose, prompts, model output or credentials.
    """

    code: TsaResultCode
    message: str
    details: tuple[str, ...] = ()
    facts: tuple[Fact, ...] = field(default_factory=tuple)

    @property
    def is_normal(self) -> bool:
        return self.code in NORMAL_CODES

    def record(self) -> dict[str, object]:
        """The machine-readable form of `inspect --json`."""
        return {
            "code": self.code.value,
            "message": self.message,
            "details": list(self.details),
            **dict(self.facts),
        }


class ProjectCodeLookup(Protocol):
    """The existing exact Project Code lookup of the Project adapter."""

    def find_project_by_code(self, code: str) -> ProjectRecord | None:
        """The Project with this exact Code, or None."""


@dataclass(frozen=True)
class ArchitectureSession:
    """One invocation: adapters on one Fibery client, the two TSA roles, a clock."""

    projects: ProjectCodeLookup
    workspace: CycleWorkspace
    evidence: RequirementEvidenceWorkspace
    architect_model: ModelRuntime
    reviewer_model: ModelRuntime
    clock: Clock


ArchitectureCommand = Callable[[ArchitectureSession], ArchitectureCommandResult]


class ConfiguredRoleRuntime:
    """A TSA model role, configured only when it is first asked to run.

    Durable state decides whether a model is needed at all, so a path that
    needs none — an approved cycle, the boundary re-presented, `approve`,
    `inspect` — never depends on the runtime configuration. The first `run`
    selects the role's runtime with the unchanged precedence and keeps it for
    the rest of the invocation. A configuration that cannot be resolved is a
    `ModelRuntimeError` there, which the calling stage reports as
    `MODEL_RUNTIME_FAILED`; nothing is substituted for it.
    """

    def __init__(self, role: str, configure: Callable[[str], ModelRuntime]) -> None:
        self.role = role
        self._configure = configure
        self._runtime: ModelRuntime | None = None

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        if self._runtime is None:
            try:
                self._runtime = self._configure(self.role)
            except ModelRuntimeConfigError as error:
                raise ModelRuntimeError(
                    f"The {self.role} model runtime could not be configured: {error}"
                ) from error
        return self._runtime.run(prompt, context)


class _Refused(Exception):
    """A refusal this layer decides itself, before any domain entry point."""

    def __init__(self, code: TsaResultCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.details: tuple[str, ...] = ()


#: Every controlled refusal the entry points called here raise. Anything else
#: is a defect and stays visible.
REFUSALS = (
    _Refused,
    CycleRefused,
    AdmissionRefused,
    ArchitectRefused,
    RecoveryRefused,
    DecisionRefused,
)
Refusal = (
    _Refused
    | CycleRefused
    | AdmissionRefused
    | ArchitectRefused
    | RecoveryRefused
    | DecisionRefused
)


def _refused(error: Refusal, facts: tuple[Fact, ...] = ()) -> ArchitectureCommandResult:
    """The domain's own frozen code and message, mapped by value, unchanged."""
    if isinstance(error, CycleRefused):
        details = (
            ()
            if error.rediscovered is None
            else (f"Rediscovered durable state: {error.rediscovered.outcome}",)
        )
    else:
        details = tuple(error.details)
    return ArchitectureCommandResult(
        TsaResultCode(str(error.code)), str(error), details, facts
    )


def _bootstrap_refusal(
    found: CycleDiscovery, facts: tuple[Fact, ...]
) -> ArchitectureCommandResult:
    """Durable state E: the code I04 set for its refusing condition, unchanged."""
    return ArchitectureCommandResult(
        TsaResultCode(str(found.refusal_code)), found.detail, facts=facts
    )


# ---------------------------------------------------------------------------
# Guard and workspace (contract 13, spec 13)
# ---------------------------------------------------------------------------


def run_guarded(
    session: ArchitectureSession, command: ArchitectureCommand
) -> ArchitectureCommandResult:
    """Hold the workspace guard around the whole command, or refuse at once.

    The lock scope is the workspace identity, known from configuration and the
    Space lookup alone; no Project, Requirement or Document is read before the
    guard is held. Only acquiring the guard is mapped here: a refusal inside
    the command is the command's own.
    """
    with ExitStack() as guard:
        try:
            guard.enter_context(hold_workspace(session.workspace.lock_scope))
        except WorkerRunnerBusy:
            return ArchitectureCommandResult(TsaResultCode.WORKSPACE_BUSY, BUSY_MESSAGE)
        except WorkerRunnerGuardUnavailable as error:
            return ArchitectureCommandResult(
                TsaResultCode.WORKSPACE_GUARD_UNAVAILABLE,
                GUARD_UNAVAILABLE_MESSAGE.format(error=error),
            )
        return command(session)


def workspace_unavailable(error: Exception) -> ArchitectureCommandResult:
    """No trusted workspace context could be obtained; no engine ran."""
    return ArchitectureCommandResult(
        TsaResultCode.FIBERY_READ_FAILED,
        WORKSPACE_UNAVAILABLE_MESSAGE.format(error=error),
    )


def _resolve_project(session: ArchitectureSession, selector: str) -> str:
    """`--project <CODE|entity-id>`: an exact Project Code, else an entity id.

    The id is handed to the domain unchanged, whose fresh Project read refuses
    it as `FIBERY_READ_FAILED` when it names no Project. A Project Name is not
    accepted.
    """
    try:
        project = session.projects.find_project_by_code(selector)
    except FiberyError as error:
        raise _Refused(
            TsaResultCode.FIBERY_READ_FAILED,
            f"Looking up Project {selector!r} failed: {error}. Nothing was written.",
        ) from error
    return selector if project is None else project.id


# ---------------------------------------------------------------------------
# Facts: identities and digests only
# ---------------------------------------------------------------------------


def _target(project: str, cycle_id: str) -> tuple[Fact, ...]:
    return (("project_id", project), ("cycle_id", cycle_id))


def _state_facts(state: CycleState) -> tuple[Fact, ...]:
    target = state.target
    review = target.review
    decision = state.decision
    return (
        ("iteration", target.iteration),
        (
            "architecture",
            {
                "document_id": target.context.architecture_document_id,
                "fingerprint": target.architecture_fingerprint,
            },
        ),
        (
            "process_result",
            {
                "document_id": target.process_document_id,
                "digest": None
                if target.process is None
                else (target.process.artifact_digest),
            },
        ),
        (
            "review_result",
            {
                "document_id": target.review_document_id,
                "digest": None if review is None else review.artifact_digest,
                "derived_status": None
                if review is None
                else (review.body["derived_status"]),
            },
        ),
        (
            "human_decision",
            {
                "document_id": state.decision_document_id,
                "decision": None if decision is None else decision.body["decision"],
                "digest": None if decision is None else decision.artifact_digest,
            },
        ),
    )


def _recovery_facts(result: RecoveryResult) -> tuple[Fact, ...]:
    is_approved = result.boundary is RecoveryBoundary.APPROVED
    return (
        ("iteration", result.iteration),
        (
            "architecture",
            {
                "document_id": result.architecture_document_id,
                "fingerprint": result.architecture_fingerprint,
            },
        ),
        (
            "process_result",
            {
                "document_id": result.process_result_document_id,
                "digest": result.process_result_digest,
            },
        ),
        (
            "review_result",
            {
                "document_id": result.review_result_document_id,
                "digest": result.review_result_digest,
                "derived_status": result.derived_review_status,
            },
        ),
        (
            "human_decision",
            {
                "document_id": result.human_decision_document_id,
                "decision": "APPROVE" if is_approved else None,
                "digest": result.human_decision_digest,
            },
        ),
        (
            "architect_stage",
            None
            if result.architect is None
            else (
                f"{result.architect.outcome}, model "
                f"{'invoked' if result.architect.model_invoked else 'not invoked'}"
            ),
        ),
        (
            "reviewer_stage",
            None
            if result.reviewer is None
            else (
                f"{result.reviewer.outcome}, model "
                f"{'invoked' if result.reviewer.model_invoked else 'not invoked'}"
            ),
        ),
    )


def _decision_facts(result: DecisionResult) -> tuple[Fact, ...]:
    return (
        ("iteration", result.iteration),
        ("architecture", {"fingerprint": result.architecture_fingerprint}),
        (
            "review_result",
            {
                "document_id": result.review_result_document_id,
                "digest": result.review_result_digest,
            },
        ),
        (
            "human_decision",
            {
                "document_id": result.decision_document_id,
                "decision": result.decision,
                "digest": result.decision_digest,
                "recorded_at": result.recorded_at,
            },
        ),
    )


# ---------------------------------------------------------------------------
# start and resume: the bootstrap gate, then I10 recovery (spec 13.1, 13.2)
# ---------------------------------------------------------------------------


def _first_case_code(command: Command, state: CycleState) -> TsaResultCode:
    """Spec 13.6 for state D, from the case the first gate read.

    A REWORK that opened the next iteration, with nothing in it yet, is case 6
    (continue at N+1). Every other case is the current iteration's own row.
    """
    case = classify_recovery_case(state)
    if case is RecoveryCase.DRAFT and state.reworks:
        return TsaResultCode.ARCHITECTURE_CYCLE_RESUMED
    return CONTINUING_CODES[command][case]


def _continued(
    code: TsaResultCode, recovery: RecoveryResult, facts: tuple[Fact, ...]
) -> ArchitectureCommandResult:
    cycle_facts = (*facts, *_recovery_facts(recovery))
    iteration = recovery.iteration
    if recovery.boundary in STOPPED_SHORT:
        stage = (
            "Architect"
            if (recovery.boundary is RecoveryBoundary.ARCHITECT_REQUIRED)
            else "Reviewer"
        )
        return ArchitectureCommandResult(
            TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
            f"The cycle stopped before the Human Decision boundary of iteration "
            f"{iteration}: durable state changed under this command and still "
            f"needs the {stage} stage, which one invocation runs at most once. "
            "Run `sdlc project architecture resume` to continue from durable state.",
            facts=cycle_facts,
        )
    messages = {
        TsaResultCode.ARCHITECTURE_CYCLE_STARTED: (
            f"The cycle started: its Input Manifest is accepted and iteration "
            f"{iteration} stopped at the Human Decision boundary. {NEXT_DECISION}"
        ),
        TsaResultCode.ARCHITECTURE_CYCLE_RESUMED: (
            f"The cycle advanced to the Human Decision boundary of iteration "
            f"{iteration}. {NEXT_DECISION}"
        ),
        TsaResultCode.ARCHITECTURE_REVIEW_READY: (
            f"Iteration {iteration} is at the Human Decision boundary. {NEXT_DECISION}"
        ),
        TsaResultCode.CYCLE_APPROVED: (
            f"The cycle is approved at iteration {iteration} and closed to "
            "writes. Nothing was written and no model was called."
        ),
    }
    return ArchitectureCommandResult(code, messages[code], facts=cycle_facts)


def _read_state(
    session: ArchitectureSession, project_id: str, cycle_id: str
) -> CycleState:
    return read_cycle_state(session.workspace, session.evidence, project_id, cycle_id)


def _recover(
    session: ArchitectureSession, project_id: str, cycle_id: str
) -> RecoveryResult:
    return recover_architecture_cycle(
        session.workspace,
        session.evidence,
        session.architect_model,
        session.reviewer_model,
        project_id,
        cycle_id,
        clock=session.clock,
    )


def start_cycle(
    session: ArchitectureSession,
    project: str,
    cycle_id: str,
    inputs: StartInputs,
) -> ArchitectureCommandResult:
    """`start`: I05 carries the cycle to an accepted Manifest, I10 onward.

    A Manifest this command wrote is a new cycle (rows A, B and the empty
    Architecture shell). An existing one was compared with the caller's
    inputs by I05 and never rewritten; the first gate then names the row.
    """
    facts = _target(project, cycle_id)
    try:
        project_id = _resolve_project(session, project)
        manifest = start_input_manifest(
            session.workspace,
            session.evidence,
            project_id,
            cycle_id,
            inputs,
            clock=session.clock,
        )
        code = TsaResultCode.ARCHITECTURE_CYCLE_STARTED
        if not manifest.is_newly_written:
            code = _first_case_code(
                Command.START, _read_state(session, project_id, cycle_id)
            )
        recovery = _recover(session, project_id, cycle_id)
    except REFUSALS as error:
        return _refused(error, facts)
    return _continued(code, recovery, facts)


def _resume_bootstrap(
    session: ArchitectureSession,
    project_id: str,
    cycle_id: str,
    outcome: CycleOutcome,
    facts: tuple[Fact, ...],
) -> ArchitectureCommandResult:
    """`resume` before state D: spec 13.7-1 and 13.7-1a."""
    if outcome is CycleOutcome.A:
        return ArchitectureCommandResult(
            TsaResultCode.CYCLE_NOT_FOUND,
            "No Architecture Document exists for this cycle: the deterministic "
            "Document is physically absent. Nothing was written; `start` "
            "creates a cycle.",
            facts=facts,
        )
    if outcome is CycleOutcome.B:
        return ArchitectureCommandResult(
            TsaResultCode.MANIFEST_INPUTS_REQUIRED,
            "The cycle has no Input Manifest yet, and `resume` carries no "
            "inputs. Run `sdlc project architecture start` with the same "
            "--cycle and its inputs. Nothing was written.",
            facts=facts,
        )
    completed = ensure_bootstrap_architecture(
        session.workspace,
        project_id,
        cycle_id,
        create_if_absent=False,
        clock=session.clock,
    )
    if completed.outcome is CycleOutcome.E:
        return _bootstrap_refusal(completed, facts)
    return ArchitectureCommandResult(
        TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
        f"The empty Architecture shell {completed.context.architecture_document_id!r}"
        f" was completed in place with its bootstrap carrier; the cycle is now "
        f"in durable state {completed.outcome}. No model was called. Supply its "
        "inputs with `sdlc project architecture start` and the same --cycle.",
        facts=(*facts, ("state", str(completed.outcome))),
    )


def resume_cycle(
    session: ArchitectureSession, project: str, cycle_id: str
) -> ArchitectureCommandResult:
    """`resume`: classify durable state, then the bootstrap or normal gate."""
    facts = _target(project, cycle_id)
    try:
        project_id = _resolve_project(session, project)
        found = discover_cycle(session.workspace, project_id, cycle_id)
        if found.outcome is CycleOutcome.E:
            return _bootstrap_refusal(found, facts)
        if found.outcome is not CycleOutcome.D:
            return _resume_bootstrap(
                session, project_id, cycle_id, found.outcome, facts
            )
        code = _first_case_code(
            Command.RESUME, _read_state(session, project_id, cycle_id)
        )
        recovery = _recover(session, project_id, cycle_id)
    except REFUSALS as error:
        return _refused(error, facts)
    return _continued(code, recovery, facts)


# ---------------------------------------------------------------------------
# rework and approve: I11 decides everything (spec 11.1.1, 13.3, 13.4)
# ---------------------------------------------------------------------------


def _decided(
    result: DecisionResult, facts: tuple[Fact, ...]
) -> ArchitectureCommandResult:
    facts = (*facts, *_decision_facts(result))
    where = f"Human Decision {result.decision_document_id!r}"
    if result.outcome is DecisionResultCode.DECISION_ALREADY_RECORDED:
        return ArchitectureCommandResult(
            TsaResultCode.DECISION_ALREADY_RECORDED,
            f"An equivalent {result.decision} of iteration {result.iteration} is "
            f"already durable at {where}, recorded at {result.recorded_at}. "
            "Nothing was written and no model was called.",
            facts=facts,
        )
    if result.outcome is DecisionResultCode.ARCHITECTURE_APPROVED:
        return ArchitectureCommandResult(
            TsaResultCode.ARCHITECTURE_APPROVED,
            f"APPROVE of iteration {result.iteration} was persisted at {where} "
            "and read back. Nothing downstream was written: no Epic, Story, "
            "Task, Requirement, Project or Project Phase.",
            facts=facts,
        )
    return _reworked(result, facts, where)


def _reworked(
    result: DecisionResult, facts: tuple[Fact, ...], where: str
) -> ArchitectureCommandResult:
    """A new durable REWORK, and what carrying the cycle on to N+1 reached."""
    durable = (
        f"REWORK of iteration {result.iteration} is durable at {where} and is "
        "not rolled back."
    )
    recovery = result.recovery
    if recovery is None:
        # I11 returns exactly one of the two for a new REWORK.
        refusal = result.recovery_refusal
        return ArchitectureCommandResult(
            TsaResultCode(str(refusal.code)),
            f"{durable} Continuing to iteration {result.iteration + 1} was "
            f"refused: {refusal}",
            tuple(refusal.details),
            facts,
        )
    continued = (
        *facts,
        ("continued_iteration", recovery.iteration),
        (
            "continued_review_result",
            {
                "document_id": recovery.review_result_document_id,
                "digest": recovery.review_result_digest,
                "derived_status": recovery.derived_review_status,
            },
        ),
    )
    if recovery.boundary in STOPPED_SHORT:
        return ArchitectureCommandResult(
            TsaResultCode.ARCHITECTURE_CYCLE_RESUMED,
            f"{durable} Iteration {recovery.iteration} stopped before its Human "
            "Decision boundary: durable state changed under this command. Run "
            "`sdlc project architecture resume` to continue from durable state.",
            facts=continued,
        )
    return ArchitectureCommandResult(
        TsaResultCode.ARCHITECTURE_REWORK_RECORDED,
        f"{durable} Iteration {recovery.iteration} was opened on the same Input "
        f"Manifest and stopped at its Human Decision boundary. {NEXT_DECISION}",
        facts=continued,
    )


def rework_cycle(
    session: ArchitectureSession,
    project: str,
    cycle_id: str,
    iteration: int,
    review_result_document_id: str,
    reason: str | None,
) -> ArchitectureCommandResult:
    """`rework` against the exact target triple; I11 then hands over to I10."""
    facts = _target(project, cycle_id)
    try:
        project_id = _resolve_project(session, project)
        result = record_rework(
            session.workspace,
            session.evidence,
            session.architect_model,
            session.reviewer_model,
            project_id,
            cycle_id,
            iteration,
            review_result_document_id,
            reason=reason,
            clock=session.clock,
        )
    except REFUSALS as error:
        return _refused(error, facts)
    return _decided(result, facts)


def approve_cycle(
    session: ArchitectureSession,
    project: str,
    cycle_id: str,
    iteration: int,
    review_result_document_id: str,
    dispositions: tuple[AcceptedDisposition, ...],
) -> ArchitectureCommandResult:
    """`approve --confirm` against the exact target triple. Model-free.

    `--confirm` is checked by argparse before this runs; no model runtime is
    handed to I11, so none is reachable.
    """
    facts = _target(project, cycle_id)
    try:
        project_id = _resolve_project(session, project)
        result = record_approve(
            session.workspace,
            session.evidence,
            project_id,
            cycle_id,
            iteration,
            review_result_document_id,
            accepted_dispositions=dispositions,
            clock=session.clock,
        )
    except REFUSALS as error:
        return _refused(error, facts)
    return _decided(result, facts)


# ---------------------------------------------------------------------------
# inspect: read-only, unguarded, model-free (spec 13.5)
# ---------------------------------------------------------------------------


def _inspected(
    code: TsaResultCode,
    message: str,
    facts: tuple[Fact, ...],
    *,
    state: str,
    case: str | None,
    inputs: InputCurrentness,
    cycle: tuple[Fact, ...] = (),
    details: tuple[str, ...] = (),
) -> ArchitectureCommandResult:
    """Every inspect result carries the same keys, so `--json` is one shape."""
    unknown = (
        ("iteration", None),
        ("architecture", None),
        ("process_result", None),
        ("review_result", None),
        ("human_decision", None),
    )
    return ArchitectureCommandResult(
        code,
        message,
        details,
        (
            *facts,
            ("state", state),
            ("case", case),
            ("inputs", inputs.value),
            *(cycle or unknown),
        ),
    )


def _inspect_refusal(
    session: ArchitectureSession,
    project_id: str,
    cycle_id: str,
    refused: ArchitectRefused,
    facts: tuple[Fact, ...],
) -> ArchitectureCommandResult:
    """Spec 13.6 `inspect` for a state D whose normal gate refused."""
    code = TsaResultCode(str(refused.code))
    found = f"{code}: {refused}"
    if code in INSPECT_PASSES_THROUGH:
        return _refused(refused, facts)
    if code is TsaResultCode.INPUTS_STALE:
        return _inspected(
            TsaResultCode.INSPECT_STALE,
            "At least one bound input drifted since the Input Manifest was "
            "accepted. Any durable decision of this cycle is historical, not a "
            f"current approval. {refused}",
            facts,
            state=CycleOutcome.D,
            case=None,
            inputs=InputCurrentness.STALE,
            details=tuple(refused.details),
        )
    if code in INSPECTED_AS_DERIVED:
        try:
            read_input_currentness(
                session.workspace, session.evidence, project_id, cycle_id
            )
        except ArchitectRefused as again:
            return _inspect_refusal(session, project_id, cycle_id, again, facts)
        return _inspected(
            TsaResultCode.INSPECT_CURRENT,
            f"The lifecycle state is derived and every bound input is current; "
            f"the cycle cannot advance as it is. {found}",
            facts,
            state=CycleOutcome.D,
            case=None,
            inputs=InputCurrentness.CURRENT,
            details=tuple(refused.details),
        )
    return _inspected(
        TsaResultCode.INSPECT_INCOMPLETE,
        f"The cycle is in durable state D, but its state is incomplete, "
        f"malformed or diverged, so currentness was not established. {found}",
        facts,
        state=CycleOutcome.D,
        case=None,
        inputs=InputCurrentness.NOT_ESTABLISHED,
        details=tuple(refused.details),
    )


def inspect_cycle(
    session: ArchitectureSession, project: str, cycle_id: str
) -> ArchitectureCommandResult:
    """Derive lifecycle state and freshness from durable artifacts alone."""
    facts = _target(project, cycle_id)
    try:
        project_id = _resolve_project(session, project)
        found = discover_cycle(session.workspace, project_id, cycle_id)
    except REFUSALS as error:
        return _refused(error, facts)
    if found.outcome is CycleOutcome.A:
        return ArchitectureCommandResult(
            TsaResultCode.CYCLE_NOT_FOUND,
            "No Architecture Document exists for this cycle: the deterministic "
            "Document is physically absent.",
            facts=facts,
        )
    if found.outcome is not CycleOutcome.D:
        refusal = () if found.refusal_code is None else (str(found.refusal_code),)
        return _inspected(
            TsaResultCode.INSPECT_INCOMPLETE,
            f"The cycle is in durable state {found.outcome}, before or outside "
            "a valid accepted Input Manifest, so the complete bound-input "
            f"currentness cannot be determined. {found.detail}".rstrip(),
            facts,
            state=found.outcome,
            case=None,
            inputs=InputCurrentness.NOT_ESTABLISHED,
            details=refusal,
        )
    try:
        state = _read_state(session, project_id, cycle_id)
    except ArchitectRefused as refused:
        return _inspect_refusal(session, project_id, cycle_id, refused, facts)
    case = classify_recovery_case(state)
    return _inspected(
        TsaResultCode.INSPECT_CURRENT,
        f"The cycle is in durable state D, case {case}, and every bound input "
        "is current.",
        facts,
        state=CycleOutcome.D,
        case=case,
        inputs=InputCurrentness.CURRENT,
        cycle=_state_facts(state),
    )


# ---------------------------------------------------------------------------
# Rendering (spec 12.3)
# ---------------------------------------------------------------------------


def _human_value(value: object) -> str:
    if not isinstance(value, Mapping):
        return str(value)
    named = {key: item for key, item in value.items() if key != "document_id"}
    parts = ", ".join(
        f"{key.replace('_', ' ')} {'none' if item is None else item}"
        for key, item in named.items()
    )
    document_id = value.get("document_id")
    if document_id is None:
        return parts
    return f"{document_id} ({parts})" if parts else str(document_id)


def render_architecture_result(
    result: ArchitectureCommandResult, stream: TextIO, *, as_json: bool = False
) -> None:
    """The result code first, a blank line, then the human or JSON detail."""
    print(result.code.value, file=stream)
    print(file=stream)
    if as_json:
        print(json.dumps(result.record(), sort_keys=True, indent=2), file=stream)
        return
    print(result.message, file=stream)
    lines = [
        f"{FACT_LABELS[key]}: {_human_value(value)}"
        for key, value in result.facts
        if value is not None
    ]
    if lines:
        print(file=stream)
        for line in lines:
            print(line, file=stream)
    if result.details:
        print("\nDetails:", file=stream)
        for item in result.details:
            print(f"- {item}", file=stream)
