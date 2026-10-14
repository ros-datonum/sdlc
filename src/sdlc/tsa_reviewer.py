"""TSA-C01 I08 — the Reviewer stage: output contract, derived status, persist.

Implementation spec v0.3 sections 4.6.4, 6, 10, 13.7, 14 and 16.2, with
contract v0.2 sections 6, 7.2, 10 and 14. For one cycle in durable state D,
whose current iteration N already holds the applied Architect output, this
stage owns exactly:

- one independent Reviewer call, given only the sources of 16.2;
- the response contract of 10.1, checked on the raw response: one JSON
  object, no repeated key, the closed I01 schema, no verdict field;
- the status of 10.2, derived by code (`derive_review_status`, the one
  derivation the Architect stage also revalidates stored statuses with);
- the `tsa.review_result` artifact, persisted at its deterministic id and
  confirmed by read-back, then the stop at the Human Decision boundary.

Schema-valid evidence is persisted as it is, whatever it says: incomplete,
duplicated or foreign claim coverage makes the stored status
`REVIEW_STRUCTURALLY_INVALID` with the 6.3 diagnostics reported beside it, and
negative findings are a normal outcome. Nothing is repaired, re-requested or
continued automatically. The only mutations are the create and the body write
of iteration N's own Review child: the Reviewer never writes the
Architecture, a Process Result, the Manifest, a Decision, a Requirement or
anything else.

The boundary with other work items, stated so it cannot be mistaken:

- **I07** owns the Architect call, persist-before-apply and replay. When the
  Architect stage has not finished iteration N — no Process Result, an empty
  Process shell, or a recorded output not applied yet — this stage raises
  `ArchitectStageRequired` and does neither of those things itself.
- **I10** owns the complete recovery dispatcher; the gate run here is the
  Architect stage's own stage-local gate (`read_review_target`), re-run fresh
  at every boundary of this stage, with nothing assumed checked elsewhere.
- **I11** owns Human Decisions; **I12** owns commands, exit classes and the
  workspace guard `hold_workspace(lock_scope)`, which the caller holds for the
  whole command. This stage does not take it. No Fibery transaction and no
  multi-host exclusion is claimed (contract 10, 13).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from sdlc.fibery_workspace import FiberyError
from sdlc.model_runtime import ModelResponse, ModelRuntime, ModelRuntimeError
from sdlc.model_runtime_config import (
    TSA_REVIEWER_ROLE,
    RuntimeSelection,
    select_runtime,
)
from sdlc.tsa_admission import AdmissionResultCode, RequirementEvidenceWorkspace
from sdlc.tsa_architect import (
    ArchitectCase,
    ArchitectRefused,
    ArchitectResultCode,
    ResultCode,
    ReviewTarget,
    SlotState,
    decode_one_json_object,
    derive_review_status,
    read_bound_sources,
    read_review_target,
    resolve_child_placement,
    resolve_root_placement,
    review_coverage_defects,
)
from sdlc.tsa_artifacts import (
    FENCE_MARKER,
    JSON_FENCE_OPENER,
    REVIEW_RESULT,
    REVIEWER_ROLE,
    SCHEMA_VERSION,
    InvalidTsaArtifact,
    canonical_artifact_json,
    canonical_json,
    sealed_artifact,
    validate_artifact,
    validate_reviewer_response,
)
from sdlc.tsa_cycle import (
    BootstrapContext,
    Clock,
    CycleResultCode,
    CycleWorkspace,
    DocumentKind,
    created_at_now,
    derive_document_id,
)
from sdlc.tsa_reviewer_prompt import (
    ReviewerInputTooLarge,
    ReviewerPrompt,
    ReviewerPromptInput,
    build_reviewer_prompt,
    require_within_input_bound,
)

__all__ = [
    "ArchitectStageRequired",
    "ReviewerRefused",
    "ReviewerStageOutcome",
    "ReviewerStageResult",
    "build_review_result",
    "render_review_result_carrier",
    "review_result_document_name",
    "run_reviewer_stage",
    "select_reviewer_runtime",
    "validate_reviewer_output",
]

#: Contract 5: the Review Result's navigation name. Never identity.
REVIEW_NAME_TEMPLATE = "TSA {cycle_id} — Review Result {iteration:04d}"
REVIEW_HEADING_TEMPLATE = "# {name}"
#: One line on purpose: Fibery stores a soft line break as a literal `<br>`.
REVIEW_PROSE = (
    "Immutable TSA artifact written by the Reviewer stage. It records one "
    "iteration's independent review evidence and the status code derived from "
    "it; it is not an approval and not a decision."
)
#: The first create, then at most one retry at the same deterministic id, and
#: only after rediscovery showed the child absent (spec 3.5, 14.4.1 window E).
REVIEW_CREATE_ATTEMPTS = 2


class ReviewerRefused(Exception):
    """A controlled refusal with one frozen result code of spec 13.8.

    A refusal raised by the shared gate (I04-I07) keeps the code it was given.
    `details` names Documents, fingerprints and Requirements by id; it never
    carries model output.
    """

    def __init__(
        self, code: ResultCode, message: str, details: tuple[str, ...] = ()
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


class ArchitectStageRequired(Exception):
    """Iteration N has no applied Architect output to review yet.

    Not a result code and not a success: the Architect stage must run first
    (case 1, an empty Process shell, or case 2). Nothing was written and no
    model was called; the Reviewer neither applies a Process Result nor calls
    the Architect.
    """

    def __init__(self, case: ArchitectCase, iteration: int) -> None:
        super().__init__(
            f"Iteration {iteration} is at {case}: the Architect stage has not "
            "applied its output, so there is nothing to review. Nothing was "
            "written and no model was called."
        )
        self.case = case
        self.iteration = iteration


class ReviewerStageOutcome(StrEnum):
    """What the stage established. None of these is a result code (13.8)."""

    #: One fresh Reviewer call; its Review Result persisted and confirmed.
    REVIEW_RECORDED = "REVIEW_RECORDED"
    #: Case 5: a valid current Review Result exists; nothing was done.
    REVIEW_ALREADY_RECORDED = "REVIEW_ALREADY_RECORDED"


@dataclass(frozen=True)
class ReviewerStageResult:
    """Iteration N's Review Result is durable and current. Nothing more.

    The cycle is at the Human Decision boundary: this is not a decision, not
    an approval, and not the outcome of any command, whatever the status.
    `coverage_defects` carries the 6.3 diagnostics behind a structurally
    invalid status; it is empty otherwise.
    """

    outcome: ReviewerStageOutcome
    iteration: int
    architecture_document_id: str
    architecture_fingerprint: str
    process_result_document_id: str
    process_result_digest: str
    review_result_document_id: str
    review_result_digest: str
    derived_status: str
    coverage_defects: tuple[str, ...]
    model_invoked: bool
    review_written: bool


@dataclass(frozen=True)
class _Operation:
    """What one stage run started from, held as values (contract 10, 14.1.1).

    Fixed once, from the first gate pass, before the model call, and never
    re-read from a later pass: a later gate shows what is durable now, these
    say what this run reviewed and what its Review Result binds. The only
    transition this run makes is its own Review slot filling.
    """

    project_entity_id: str
    cycle_id: str
    iteration: int
    manifest_document_id: str
    manifest_artifact_digest: str
    process_document_id: str
    process_artifact_digest: str
    architecture_document_id: str
    architecture_fingerprint: str
    review_document_id: str


@dataclass(frozen=True)
class _Stage:
    workspace: CycleWorkspace
    evidence: RequirementEvidenceWorkspace
    project_id: str
    cycle_id: object


def _utc_now() -> datetime:
    return datetime.now(UTC)


def select_reviewer_runtime(
    config: dict[str, object],
    runtime_override: str | None = None,
    model_override: str | None = None,
) -> RuntimeSelection:
    """The I09 role through the unchanged selection precedence."""
    return select_runtime(config, TSA_REVIEWER_ROLE, runtime_override, model_override)


# ---------------------------------------------------------------------------
# Refusal plumbing
# ---------------------------------------------------------------------------


@contextmanager
def _shared() -> Iterator[None]:
    """A refusal of the shared gate keeps its code, message and details."""
    try:
        yield
    except ArchitectRefused as refused:
        raise ReviewerRefused(refused.code, str(refused), refused.details) from refused


def _write_failed(message: str, details: tuple[str, ...] = ()) -> ReviewerRefused:
    return ReviewerRefused(CycleResultCode.FIBERY_WRITE_FAILED, message, details)


def _stale(message: str, details: tuple[str, ...]) -> ReviewerRefused:
    return ReviewerRefused(AdmissionResultCode.INPUTS_STALE, message, details)


def _invalid_output(message: str) -> ReviewerRefused:
    return ReviewerRefused(
        ArchitectResultCode.INVALID_MODEL_OUTPUT,
        f"The Reviewer response does not satisfy its closed contract: {message} "
        "It was not repaired, re-requested or persisted.",
    )


def _occupied(operation: _Operation) -> ReviewerRefused:
    return ReviewerRefused(
        ArchitectResultCode.ARTIFACT_DUPLICATE,
        f"Review Result {operation.review_document_id!r} already holds a review "
        f"for iteration {operation.iteration}; this review was not persisted, "
        "and the durable one was not overwritten.",
        (operation.review_document_id,),
    )


# ---------------------------------------------------------------------------
# The raw response contract (spec 10.1)
# ---------------------------------------------------------------------------


def validate_reviewer_output(text: str) -> dict[str, object]:
    """The raw response against 10.1, in the canonical form it is stored in.

    Exactly one JSON object with no repeated key and no non-JSON constant,
    then I01's closed Reviewer schema: required keys and nested types, no
    unknown field — so no verdict, approval or replacement field — and
    severity exactly on CONFIRMED verifications and on every new finding.
    Claim coverage is not checked here: a schema-valid payload is evidence and
    is kept, and coverage decides its derived status. Pure.
    """
    response = decode_one_json_object(text, _invalid_output)
    try:
        validate_reviewer_response(response, ("response",))
        return json.loads(canonical_json(response))
    except InvalidTsaArtifact as error:
        raise _invalid_output(str(error)) from error


# ---------------------------------------------------------------------------
# The gate and this run's fixed bindings
# ---------------------------------------------------------------------------


def _gate(stage: _Stage) -> ReviewTarget:
    """The Architect stage's gate, fresh: discovery to iteration N's lineage."""
    with _shared():
        return read_review_target(
            stage.workspace, stage.evidence, stage.project_id, stage.cycle_id
        )


def _require_reviewable(target: ReviewTarget) -> None:
    """Only an applied output is reviewed; the Architect stage owns the rest."""
    if target.case is not ArchitectCase.OUTPUT_APPLIED:
        raise ArchitectStageRequired(target.case, target.iteration)


def _manifest_document_id(context: BootstrapContext) -> str:
    return derive_document_id(
        context.workspace_identity,
        context.project_entity_id,
        context.cycle_id,
        DocumentKind.INPUT_MANIFEST,
        None,
    )


def _operation(target: ReviewTarget) -> _Operation:
    assert target.process is not None and target.output_fingerprint is not None
    context = target.context
    return _Operation(
        project_entity_id=context.project_entity_id,
        cycle_id=context.cycle_id,
        iteration=target.iteration,
        manifest_document_id=_manifest_document_id(context),
        manifest_artifact_digest=target.manifest.artifact_digest,
        process_document_id=target.process_document_id,
        process_artifact_digest=target.process.artifact_digest,
        architecture_document_id=context.architecture_document_id,
        architecture_fingerprint=target.output_fingerprint,
        review_document_id=target.review_document_id,
    )


def _require_same_operation(operation: _Operation, target: ReviewTarget) -> None:
    """A fresh gate pass still describes the review this run started.

    Nothing is re-bound to the fresh pass, however valid it is internally.
    Another iteration means another run's Review and Decision closed this
    slot: `ARTIFACT_DUPLICATE`. Another accepted Manifest, or another Process
    Result than the one reviewed — even one with the same output — means the
    evidence this run was given is no longer current: `INPUTS_STALE`. An
    Architecture no longer holding the reviewed output is
    `ARCHITECTURE_DIVERGED`, with both fingerprints.
    """
    context = target.context
    if (
        context.project_entity_id != operation.project_entity_id
        or context.cycle_id != operation.cycle_id
        or target.iteration != operation.iteration
        or target.review_document_id != operation.review_document_id
    ):
        raise _occupied(operation)
    if target.manifest.artifact_digest != operation.manifest_artifact_digest:
        raise _stale(
            "The accepted Input Manifest changed during this run; the review is "
            "bound to the Manifest it was given and is not persisted against "
            "another.",
            (operation.manifest_document_id,),
        )
    current = target.process.artifact_digest if target.process else None
    if current != operation.process_artifact_digest:
        raise _stale(
            "The Process Result this run reviewed is no longer the durable one; "
            "the review is not persisted against another.",
            (operation.process_document_id,),
        )
    if target.output_fingerprint != operation.architecture_fingerprint:
        raise ReviewerRefused(
            ArchitectResultCode.ARCHITECTURE_DIVERGED,
            f"Architecture Document {operation.architecture_document_id!r} no "
            "longer holds the output this run reviewed; the review was not "
            "persisted.",
            (
                f"reviewed {operation.architecture_fingerprint}",
                f"current {target.architecture_fingerprint}",
            ),
        )


# ---------------------------------------------------------------------------
# The Review Result artifact (4.6.4)
# ---------------------------------------------------------------------------


def review_result_document_name(context: BootstrapContext, iteration: int) -> str:
    """The navigation name of one Review Result Document. Never identity."""
    return REVIEW_NAME_TEMPLATE.format(cycle_id=context.cycle_id, iteration=iteration)


def render_review_result_carrier(
    context: BootstrapContext, iteration: int, sealed: dict[str, object]
) -> str:
    """The immutable carrier of 4.1: heading, one paragraph, one JSON fence."""
    heading = REVIEW_HEADING_TEMPLATE.format(
        name=review_result_document_name(context, iteration)
    )
    return (
        f"{heading}\n"
        "\n"
        f"{REVIEW_PROSE}\n"
        "\n"
        f"{JSON_FENCE_OPENER}\n"
        f"{canonical_artifact_json(sealed)}\n"
        f"{FENCE_MARKER}\n"
    )


def build_review_result(
    target: ReviewTarget,
    reviewer_response: dict[str, object],
    response: ModelResponse,
    created_at: str,
) -> dict[str, object]:
    """The sealed `tsa.review_result` of 4.6.4 for the reviewed iteration.

    Bound to the exact Process Result and the applied output fingerprint in
    `target`; `derived_status` is computed here, never taken from the model.
    """
    process = target.process
    assert process is not None and target.output_fingerprint is not None
    runtime: dict[str, object] = {"role": REVIEWER_ROLE}
    if response.model is not None:
        runtime["model"] = response.model
    context = target.context
    sealed = sealed_artifact(
        {
            "artifact_type": REVIEW_RESULT,
            "schema_version": SCHEMA_VERSION,
            "workspace_identity": context.workspace_identity,
            "project_entity_id": context.project_entity_id,
            "project_code": context.project_code,
            "cycle_id": context.cycle_id,
            "iteration": target.iteration,
            "body": {
                "manifest_digest": target.manifest.body["manifest_digest"],
                "process_result_document_id": target.process_document_id,
                "process_result_digest": process.artifact_digest,
                "architecture_document_id": context.architecture_document_id,
                "architecture_fingerprint": target.output_fingerprint,
                "reviewer_response": reviewer_response,
                "derived_status": derive_review_status(reviewer_response, process),
                "runtime": runtime,
                "created_at": created_at,
            },
        }
    )
    try:
        validate_artifact(sealed)
    except InvalidTsaArtifact as error:
        raise _invalid_output(str(error)) from error
    return sealed


# ---------------------------------------------------------------------------
# Persisting the Review Result (4.6.4, 13.7-7, 14.1, 14.4.1 window E)
# ---------------------------------------------------------------------------


def _create_review_shell(
    stage: _Stage, target: ReviewTarget, operation: _Operation
) -> None:
    """Create the deterministic child; an unknown outcome is rediscovered first.

    Both levels of 3.5: the gate (cycle-level, with currentness and lineage)
    runs before the slot is looked at again, and must still describe this run
    before a retry is allowed; a retry reuses the same id. A child that
    appeared holding an artifact is never written over.
    """
    context = target.context
    name = review_result_document_name(context, operation.iteration)
    for _ in range(REVIEW_CREATE_ATTEMPTS):
        with _shared():
            root = resolve_root_placement(stage.workspace, context)
        try:
            stage.workspace.create_tsa_child_document(
                operation.review_document_id, name, root.document_id
            )
        except FiberyError:
            after = _gate(stage)
            _require_same_operation(operation, after)
            if after.review_state is SlotState.EMPTY:
                return
            if after.review_state is SlotState.VALID:
                raise _occupied(operation) from None
            continue
        return
    raise _write_failed(
        f"The Review Result create did not become durable in "
        f"{REVIEW_CREATE_ATTEMPTS} attempts at the same id "
        f"{operation.review_document_id!r}.",
        (operation.review_document_id,),
    )


def _confirm_review(
    stage: _Stage, operation: _Operation, emitted: str, outcome: str
) -> dict[str, object]:
    """Read back through the full gate, then require the exact artifact.

    The gate validates the slot first — schema, identity, lineage and the
    stored status — so a specific durable refusal keeps its own code; only
    then is a valid but different artifact `FIBERY_WRITE_FAILED`.
    """
    after = _gate(stage)
    _require_same_operation(operation, after)
    document_id = operation.review_document_id
    if after.review_payload is None:
        raise _write_failed(
            f"{outcome}; Review Result {document_id!r} reads back "
            f"{after.review_state}, so the review is not durable. Nothing was "
            "retried.",
            (document_id,),
        )
    if canonical_artifact_json(after.review_payload) != emitted:
        raise _write_failed(
            f"{outcome}; Review Result {document_id!r} holds a different artifact "
            "than the one written. It was not overwritten.",
            (document_id,),
        )
    return after.review_payload


def _persist_review(
    stage: _Stage,
    target: ReviewTarget,
    operation: _Operation,
    sealed: dict[str, object],
) -> dict[str, object]:
    """Create if absent, fill the empty shell, then confirm the exact artifact.

    After the create the gate runs again and must still describe this run, so
    nothing read before a mutation authorizes the body write. The last remote
    calls before the write are the child and root placement resolutions with
    their local predicates (2.2.1); no content is read between them and it.
    """
    emitted = canonical_artifact_json(sealed)
    if target.review_state is SlotState.ABSENT:
        _create_review_shell(stage, target, operation)
    current = _gate(stage)
    _require_same_operation(operation, current)
    if current.review_state is SlotState.VALID:
        raise _occupied(operation)
    document_id = operation.review_document_id
    if current.review_state is SlotState.ABSENT:
        raise _write_failed(
            f"Review Result {document_id!r} is not observable after its create; "
            "nothing was written.",
            (document_id,),
        )
    carrier = render_review_result_carrier(current.context, operation.iteration, sealed)
    with _shared():
        shell = resolve_child_placement(stage.workspace, current.context, document_id)
    if shell is None or not shell.secret:
        raise _write_failed(
            f"Review Result {document_id!r} has no writable body.", (document_id,)
        )
    try:
        stage.workspace.write_document_content(shell.secret, carrier)
    except FiberyError as error:
        return _confirm_review(
            stage, operation, emitted, f"The Review write outcome was unknown ({error})"
        )
    return _confirm_review(stage, operation, emitted, "The Review write returned")


# ---------------------------------------------------------------------------
# One fresh Reviewer call (case 3, or the Review shell of 13.7-7)
# ---------------------------------------------------------------------------


def _prompt_material(stage: _Stage, target: ReviewTarget) -> ReviewerPromptInput:
    """Exactly the sources of 16.2, each bound to what the gate validated.

    The Architecture and the Process claims are the ones the gate read and
    bound; the trees and UX content are read now and refused unless they
    still carry the fingerprints the Manifest bound.
    """
    assert target.process is not None
    with _shared():
        requirements, ux_content = read_bound_sources(
            stage.workspace,
            stage.evidence,
            stage.project_id,
            stage.cycle_id,
            target.manifest_body,
        )
    return ReviewerPromptInput(
        manifest_body=target.manifest_body,
        requirements=requirements,
        ux_content=ux_content,
        architecture_document=target.architecture_content,
        process_digest=target.process.artifact_digest,
        architect_response=target.process.body["architect_response"],
    )


def _invoke(model: ModelRuntime, prompt: ReviewerPrompt) -> ModelResponse:
    """Exactly one call. A runtime failure is reported, never retried elsewhere."""
    try:
        return model.run(prompt.prompt, prompt.context)
    except ModelRuntimeError as error:
        raise ReviewerRefused(
            ArchitectResultCode.MODEL_RUNTIME_FAILED,
            "The configured local model runtime could not run the Reviewer. "
            "Nothing was persisted.",
            (str(error),),
        ) from error


def _review(
    stage: _Stage, target: ReviewTarget, model: ModelRuntime, clock: Clock
) -> ReviewerStageResult:
    """One fresh call, its contract, the gate again, then persist and confirm."""
    operation = _operation(target)
    prompt = build_reviewer_prompt(_prompt_material(stage, target))
    require_within_input_bound(prompt)
    response = _invoke(model, prompt)
    reviewer_response = validate_reviewer_output(response.text)
    after = _gate(stage)
    _require_same_operation(operation, after)
    if after.review_state is SlotState.VALID:
        raise _occupied(operation)
    sealed = build_review_result(
        target, reviewer_response, response, created_at_now(clock)
    )
    persisted = _persist_review(stage, after, operation, sealed)
    return _result(
        ReviewerStageOutcome.REVIEW_RECORDED,
        target,
        persisted,
        model_invoked=True,
        review_written=True,
    )


def _result(
    outcome: ReviewerStageOutcome,
    target: ReviewTarget,
    review: dict[str, object],
    *,
    model_invoked: bool,
    review_written: bool,
) -> ReviewerStageResult:
    process = target.process
    assert process is not None and target.output_fingerprint is not None
    body = review["body"]
    return ReviewerStageResult(
        outcome=outcome,
        iteration=target.iteration,
        architecture_document_id=target.context.architecture_document_id,
        architecture_fingerprint=target.output_fingerprint,
        process_result_document_id=target.process_document_id,
        process_result_digest=process.artifact_digest,
        review_result_document_id=target.review_document_id,
        review_result_digest=str(review["artifact_digest"]),
        derived_status=str(body["derived_status"]),
        coverage_defects=review_coverage_defects(body["reviewer_response"], process),
        model_invoked=model_invoked,
        review_written=review_written,
    )


def run_reviewer_stage(
    workspace: CycleWorkspace,
    evidence: RequirementEvidenceWorkspace,
    model: ModelRuntime,
    project_id: str,
    raw_cycle_id: object,
    *,
    clock: Clock = _utc_now,
) -> ReviewerStageResult:
    """Carry iteration N from its applied Architect output to a durable review.

    An internal stage, not a command: the caller (I12) holds the workspace
    guard around it and maps refusals to exit classes. From a fresh gate:

    - the Architecture holds iteration N's applied output and no Review
      exists, or only an empty Review shell: one fresh Reviewer call, its
      Review Result persisted at the deterministic id and confirmed (case 3,
      13.7-7);
    - a valid current Review Result exists: nothing is written, no model is
      called and no clock is read (case 5);
    - the output is not applied yet: `ArchitectStageRequired`, nothing done.

    Every gate failure — stale inputs, a malformed, foreign or wrongly bound
    artifact, a divergent Architecture, an approved cycle — raises
    `ReviewerRefused` with its frozen code before any model call or mutation.
    The clock is read once, for the `created_at` of a fresh Review Result.
    """
    stage = _Stage(workspace, evidence, project_id, raw_cycle_id)
    target = _gate(stage)
    _require_reviewable(target)
    if target.review_state is SlotState.VALID:
        assert target.review_payload is not None
        return _result(
            ReviewerStageOutcome.REVIEW_ALREADY_RECORDED,
            target,
            target.review_payload,
            model_invoked=False,
            review_written=False,
        )
    try:
        return _review(stage, target, model, clock)
    except ReviewerInputTooLarge as error:
        raise ReviewerRefused(
            AdmissionResultCode.INPUT_TOO_LARGE, str(error)
        ) from error
