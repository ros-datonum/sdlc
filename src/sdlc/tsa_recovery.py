"""TSA-C01 I10 — the normal recovery gate, cases 1-10, and stage orchestration.

Contract 14.1.1, 14.2 and 14.3; implementation spec v0.3 sections 3.5, 13.6,
13.7 and 14, with the v0.5 delta for an in-flight Reviewer operation. For one
cycle with a valid accepted Input Manifest (durable state D) this item owns:

- the normal gate: every recovery decision is taken on one fresh, read-only,
  fully validated snapshot (`read_cycle_state`), never on an earlier one;
- the case table: which of contract 14.3 cases 1-10 that snapshot is, and the
  one action each case permits;
- the order of delegation: the Architect stage (I07) for case 1 and an
  empty Process shell, and its model-free replay for case 2, which reads an
  empty Review shell as no Review evidence (spec 14.4) so the shell is
  completed after the apply rather than blocking it; the Reviewer stage (I08)
  for case 3 and an empty Review shell; nothing for cases 5, 6 and 10; a refusal for every gate
  failure, including cases 4 and 8 and the empty Decision shell.

Nothing here writes. Every mutation is the delegated stage's own, behind its
own stage-local gate, and the full gate runs again after each stage returns
(contract 14.2): a stage result is never taken as proof of the state that
follows it. Unknown transport outcomes (case 9) are resolved inside the
stages, at both levels of spec 3.5; what they leave behind is classified by
the next fresh gate, here or in a later invocation.

Not owned here: writing a Human Decision, its idempotency and dispositions
(I11); commands, the workspace guard, result-code mapping and exit classes
(I12); bootstrap states A, B and E and the empty Architecture shell (I04).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sdlc.model_runtime import ModelRuntime
from sdlc.tsa_admission import RequirementEvidenceWorkspace
from sdlc.tsa_architect import (
    ArchitectCase,
    ArchitectRefused,
    ArchitectStageResult,
    CycleState,
    ResultCode,
    SlotState,
    read_cycle_state,
    replay_recorded_output,
    run_architect_stage,
)
from sdlc.tsa_cycle import Clock, CycleWorkspace
from sdlc.tsa_reviewer import (
    ArchitectStageRequired,
    ReviewerRefused,
    ReviewerResultCode,
    ReviewerStageResult,
    run_reviewer_stage,
)

__all__ = [
    "RecoveryBoundary",
    "RecoveryCase",
    "RecoveryRefused",
    "RecoveryResult",
    "classify_recovery_case",
    "recover_architecture_cycle",
]


class RecoveryCase(StrEnum):
    """Contract 14.3 as one validated snapshot shows it. Not a result code."""

    #: Case 1: no Process Result for the current iteration.
    DRAFT = "DRAFT"
    #: Case 7: an empty Process Result shell.
    PROCESS_SHELL = "PROCESS_SHELL"
    #: Case 2: the Architecture holds the input the Process Result recorded.
    RECORDED_INPUT = "RECORDED_INPUT"
    #: Case 3: the Architecture holds the recorded output, no Review yet.
    OUTPUT_APPLIED = "OUTPUT_APPLIED"
    #: Case 7: an empty Review Result shell beside the applied output.
    REVIEW_SHELL = "REVIEW_SHELL"
    #: Cases 5 and 10: a valid current Review Result and no Decision.
    REVIEW_RECORDED = "REVIEW_RECORDED"
    #: Case 6: a verified APPROVE; the cycle is closed to writes.
    APPROVED = "APPROVED"


class RecoveryBoundary(StrEnum):
    """Where one invocation stopped. Not a result code (spec 13.8)."""

    #: A valid current Review, no Decision: a human decides (cases 5, 10).
    HUMAN_DECISION = "HUMAN_DECISION"
    #: A verified APPROVE (case 6): nothing more is done.
    APPROVED = "APPROVED"
    #: Durable state still needs the Architect stage, which this invocation
    #: already delegated or may no longer reach; a later invocation decides.
    ARCHITECT_REQUIRED = "ARCHITECT_REQUIRED"
    #: Durable state still needs the Reviewer stage, already delegated once.
    REVIEWER_REQUIRED = "REVIEWER_REQUIRED"


class _Stage(StrEnum):
    ARCHITECT = "ARCHITECT"
    REVIEWER = "REVIEWER"


#: The stage each acting case is delegated to; the rest are boundaries.
_STAGE_OF = {
    RecoveryCase.DRAFT: _Stage.ARCHITECT,
    RecoveryCase.PROCESS_SHELL: _Stage.ARCHITECT,
    RecoveryCase.RECORDED_INPUT: _Stage.ARCHITECT,
    RecoveryCase.OUTPUT_APPLIED: _Stage.REVIEWER,
    RecoveryCase.REVIEW_SHELL: _Stage.REVIEWER,
}
_BOUNDARY_OF = {
    RecoveryCase.REVIEW_RECORDED: RecoveryBoundary.HUMAN_DECISION,
    RecoveryCase.APPROVED: RecoveryBoundary.APPROVED,
}
_REQUIRED = {
    _Stage.ARCHITECT: RecoveryBoundary.ARCHITECT_REQUIRED,
    _Stage.REVIEWER: RecoveryBoundary.REVIEWER_REQUIRED,
}


class RecoveryRefused(Exception):
    """A controlled refusal with the frozen code the gate or a stage decided.

    The code is the one I04, I05, I06, I07 or I08 raised, unchanged, including
    `REVIEW_INPUT_CHANGED` from an in-flight Reviewer operation (spec v0.5).
    """

    def __init__(
        self,
        code: ResultCode | ReviewerResultCode,
        message: str,
        details: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class RecoveryResult:
    """The durable boundary one invocation reached, read from its last gate.

    Every id and digest is the one that final gate validated, so a later
    decision command (I11) can name its exact target from it. Not persisted
    and not an artifact. `architect` and `reviewer` are what each delegated
    stage reported, None when it was not delegated or a replay found no
    Process Result left to apply.
    """

    boundary: RecoveryBoundary
    case: RecoveryCase
    iteration: int
    architecture_document_id: str
    architecture_fingerprint: str | None
    process_result_document_id: str
    process_result_digest: str | None
    review_result_document_id: str
    review_result_digest: str | None
    derived_review_status: str | None
    human_decision_document_id: str
    human_decision_digest: str | None
    architect: ArchitectStageResult | None
    reviewer: ReviewerStageResult | None


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _gate(
    workspace: CycleWorkspace,
    evidence: RequirementEvidenceWorkspace,
    project_id: str,
    cycle_id: object,
) -> CycleState:
    """The full normal gate of contract 14.1.1, fresh: read-only, or refused."""
    try:
        return read_cycle_state(workspace, evidence, project_id, cycle_id)
    except ArchitectRefused as refused:
        raise RecoveryRefused(refused.code, str(refused), refused.details) from refused


def classify_recovery_case(state: CycleState) -> RecoveryCase:
    """Contract 14.3 over one snapshot that already passed the whole gate.

    Cases 4 and 8, conflicting and duplicate artifacts, stale inputs and the
    empty Decision shell never reach here: the gate refused them. A REWORK
    (case 6) already made the next iteration current inside the gate.
    """
    target = state.target
    if state.decision is not None:
        return RecoveryCase.APPROVED
    if target.case is ArchitectCase.NO_PROCESS:
        return RecoveryCase.DRAFT
    if target.case is ArchitectCase.PROCESS_SHELL:
        return RecoveryCase.PROCESS_SHELL
    if target.case is ArchitectCase.RECORDED_INPUT:
        return RecoveryCase.RECORDED_INPUT
    if target.review_state is SlotState.VALID:
        return RecoveryCase.REVIEW_RECORDED
    if target.review_state is SlotState.EMPTY:
        return RecoveryCase.REVIEW_SHELL
    return RecoveryCase.OUTPUT_APPLIED


def _delegated[StageResult](run: Callable[[], StageResult]) -> StageResult:
    """One stage run; its refusal is propagated with its code, never retried."""
    try:
        return run()
    except (ArchitectRefused, ReviewerRefused) as refused:
        raise RecoveryRefused(refused.code, str(refused), refused.details) from refused


def _result(
    state: CycleState,
    case: RecoveryCase,
    boundary: RecoveryBoundary,
    architect: ArchitectStageResult | None,
    reviewer: ReviewerStageResult | None,
) -> RecoveryResult:
    target = state.target
    process = target.process
    review = target.review
    decision = state.decision
    return RecoveryResult(
        boundary=boundary,
        case=case,
        iteration=target.iteration,
        architecture_document_id=target.context.architecture_document_id,
        architecture_fingerprint=target.architecture_fingerprint,
        process_result_document_id=target.process_document_id,
        process_result_digest=None if process is None else process.artifact_digest,
        review_result_document_id=target.review_document_id,
        review_result_digest=None if review is None else review.artifact_digest,
        derived_review_status=(
            None if review is None else str(review.body["derived_status"])
        ),
        human_decision_document_id=state.decision_document_id,
        human_decision_digest=None if decision is None else decision.artifact_digest,
        architect=architect,
        reviewer=reviewer,
    )


def recover_architecture_cycle(
    workspace: CycleWorkspace,
    evidence: RequirementEvidenceWorkspace,
    architect_model: ModelRuntime,
    reviewer_model: ModelRuntime,
    project_id: str,
    cycle_id: object,
    *,
    clock: Clock = _utc_now,
) -> RecoveryResult:
    """Carry a cycle in state D forward to its next durable boundary.

    An internal orchestration, not a command: the caller (I12) holds the
    workspace guard around it, maps its outcome and refusals to result codes
    and exit classes, and prints nothing from it. No Human Decision is written
    here, and no CLI exit semantics are claimed.

    Each pass runs the full normal gate fresh, classifies the snapshot, and
    acts only as its case permits:

    - case 1 or an empty Process shell: the Architect stage (I07), one model
      call; case 2: its replay of the recorded output, no model call, beside
      an empty Review shell too;
    - case 3 or an empty Review shell: the Reviewer stage (I08);
    - cases 5 and 10: the Human Decision boundary, no model call;
    - case 6: an APPROVE is the closed cycle, no model call and no write; a
      REWORK already opened the next iteration inside the gate;
    - every gate failure — cases 4 and 8, duplicates and conflicting
      Decisions, stale inputs, the empty Decision shell — `RecoveryRefused`
      before any model call or mutation.

    The order is Architect, then Reviewer, each delegated at most once per
    invocation. A stage's refusal, a model runtime failure or
    `REVIEW_INPUT_CHANGED` among them, is propagated and never retried here.
    When the fresh gate after a stage still asks for a stage this invocation
    may not run again, it stops at `ARCHITECT_REQUIRED` or `REVIEWER_REQUIRED`
    and leaves the decision to a later invocation.
    """
    architect: ArchitectStageResult | None = None
    reviewer: ReviewerStageResult | None = None
    delegated: set[_Stage] = set()
    while True:
        state = _gate(workspace, evidence, project_id, cycle_id)
        case = classify_recovery_case(state)
        boundary = _BOUNDARY_OF.get(case)
        if boundary is not None:
            return _result(state, case, boundary, architect, reviewer)
        stage = _STAGE_OF[case]
        # Each stage at most once, never the Architect after the Reviewer: at
        # most three gate passes per invocation.
        if stage in delegated or _Stage.REVIEWER in delegated:
            return _result(state, case, _REQUIRED[stage], architect, reviewer)
        delegated.add(stage)
        if case is RecoveryCase.RECORDED_INPUT:
            architect = _delegated(
                lambda: replay_recorded_output(
                    workspace, evidence, project_id, cycle_id
                )
            )
            continue
        if stage is _Stage.ARCHITECT:
            architect = _delegated(
                lambda: run_architect_stage(
                    workspace,
                    evidence,
                    architect_model,
                    project_id,
                    cycle_id,
                    clock=clock,
                )
            )
            continue
        try:
            reviewer = _delegated(
                lambda: run_reviewer_stage(
                    workspace,
                    evidence,
                    reviewer_model,
                    project_id,
                    cycle_id,
                    clock=clock,
                )
            )
        except ArchitectStageRequired:
            continue
