"""TSA-C01 I11 — Human Decision, approval binding, dispositions, idempotency.

Implementation spec v0.3 sections 4.6.5, 6, 10.2, 11, 13.3, 13.4, 13.7 and
14, with contract v0.2 sections 6, 7.4, 9 and 10. For one cycle in durable
state D this item owns exactly:

- the explicit decision target `(cycle, N, Review Result id)`, resolved and
  validated through the normal gate before anything else (11.1.1 steps 1-2);
- the one deterministic Human Decision slot of `(cycle, N)` and the semantic
  comparison against a Decision already durable there (11.1.1 steps 3-4,
  11.2, 11.3): `DECISION_ALREADY_RECORDED` or `DECISION_CONFLICT`, nothing
  written and no model called;
- at the boundary itself (11.1.1 step 5): approval availability from the
  Review's derived status (10.2), every accepted disposition reference
  resolved against the exact Process and Review of N (6.4), then one
  immutable `tsa.human_decision` created at its deterministic id, written,
  and confirmed by a fresh read-back through the same gate (14.1, 14.4.1 F).

I11 decides; I10 recovers. Target resolution is the I10 recovery read
(`read_cycle_state`, classified by `classify_recovery_case`), run fresh and
read-only: no gate, currentness, lineage or status rule is copied here, and
resolving a target never runs a stage. Only after a new REWORK is confirmed
durable does `record_rework` hand the cycle to `recover_architecture_cycle`,
which opens N+1 and runs Architect, Reviewer and the next boundary (13.3).
`record_approve` takes no model runtime at all: approval is model-free.

The only mutations this module makes are the create and the body write of
iteration N's own Human Decision child. It never writes the Architecture, a
Process or Review Result, the Manifest, a Requirement, a Project or a Project
Phase, and creates no downstream work item.

Not owned here: the workspace guard `hold_workspace(lock_scope)`, which the
command (I12) holds around a whole decision command, so none is taken here
and none is nested; argv parsing, `--confirm` and exit classes (I12). No
authenticated approver identity is recorded or claimed (contract 9.4).
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum

from sdlc.fibery_workspace import FiberyError
from sdlc.model_runtime import ModelRuntime
from sdlc.tsa_admission import RequirementEvidenceWorkspace
from sdlc.tsa_architect import (
    APPROVE,
    REVIEW_BLOCKED_ON_WHAT,
    REVIEW_STRUCTURALLY_INVALID,
    REWORK,
    ArchitectRefused,
    ArchitectResultCode,
    CycleState,
    ResultCode,
    VerifiedDecision,
    open_material_question_refs,
    read_cycle_state,
    reference_sources,
    resolve_child_placement,
    resolve_root_placement,
)
from sdlc.tsa_artifacts import (
    FENCE_MARKER,
    HUMAN_DECISION,
    ITERATION_MAX,
    JSON_FENCE_OPENER,
    NON_WAIVABLE_COLLECTION,
    SCHEMA_VERSION,
    ArtifactReference,
    InvalidTsaArtifact,
    TsaArtifact,
    canonical_artifact_json,
    parse_reference,
    reference_allows_collection,
    sealed_artifact,
    ux_evidence_digest,
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
from sdlc.tsa_recovery import (
    RecoveryCase,
    RecoveryRefused,
    RecoveryResult,
    classify_recovery_case,
    recover_architecture_cycle,
)

__all__ = [
    "AcceptedDisposition",
    "DecisionRefused",
    "DecisionResult",
    "DecisionResultCode",
    "ResolvedDisposition",
    "decision_document_name",
    "decisions_equivalent",
    "record_approve",
    "record_rework",
    "render_human_decision_carrier",
    "validate_accepted_dispositions",
]

#: Contract 5: the Human Decision's navigation name. Never identity.
DECISION_NAME_TEMPLATE = "TSA {cycle_id} — Human Decision {iteration:04d}"
DECISION_HEADING_TEMPLATE = "# {name}"
#: One line on purpose: Fibery stores a soft line break as a literal `<br>`.
DECISION_PROSE = (
    "Immutable TSA artifact recording one human REWORK or APPROVE decision "
    "against one exact Review Result; it names no approver identity."
)
#: The first create, then at most one retry at the same deterministic id, and
#: only after rediscovery showed the slot absent (spec 14.4.1 window F).
DECISION_CREATE_ATTEMPTS = 2

#: Statuses of spec 10.2 under which approval is unavailable, never waivable.
UNAPPROVABLE_STATUSES = (REVIEW_STRUCTURALLY_INVALID, REVIEW_BLOCKED_ON_WHAT)
CLAIM_VERIFICATIONS = "claim_verifications"
#: Truthful consequences, by whether this call has mutated anything yet.
NOTHING_WRITTEN = " Nothing was written and no model was called."
SHELL_KEPT = (
    "Human Decision {document_id!r} was created and remains an empty shell; its "
    "body was not written and nothing was rolled back. "
)


class DecisionResultCode(StrEnum):
    """Frozen codes of spec 13.8 this item decides that no earlier item owns."""

    ARCHITECTURE_REWORK_RECORDED = "ARCHITECTURE_REWORK_RECORDED"
    ARCHITECTURE_APPROVED = "ARCHITECTURE_APPROVED"
    DECISION_ALREADY_RECORDED = "DECISION_ALREADY_RECORDED"
    DECISION_CONFLICT = "DECISION_CONFLICT"
    REVIEW_NOT_CURRENT = "REVIEW_NOT_CURRENT"
    REVIEW_STRUCTURALLY_INVALID = REVIEW_STRUCTURALLY_INVALID
    REVIEW_BLOCKED_ON_WHAT = REVIEW_BLOCKED_ON_WHAT
    DISPOSITION_UNKNOWN_REFERENCE = "DISPOSITION_UNKNOWN_REFERENCE"
    DISPOSITION_DUPLICATE_REFERENCE = "DISPOSITION_DUPLICATE_REFERENCE"
    DISPOSITION_FOREIGN_ITERATION = "DISPOSITION_FOREIGN_ITERATION"
    DISPOSITION_NOT_WAIVABLE = "DISPOSITION_NOT_WAIVABLE"


class DecisionRefused(Exception):
    """A controlled refusal with one frozen result code of spec 13.8.

    A refusal of the gate (I04-I07, through the I10 recovery read) keeps the
    code it was given. `details` names Documents and references by id.
    """

    def __init__(
        self,
        code: ResultCode | DecisionResultCode,
        message: str,
        details: tuple[str, ...] = (),
    ) -> None:
        super().__init__(message)
        self.code = code
        self.details = details


@dataclass(frozen=True)
class AcceptedDisposition:
    """One caller-supplied acceptance: a reference of spec 6.1 and its reason."""

    ref: str
    reason: str


@dataclass(frozen=True)
class ResolvedDisposition:
    """One accepted reference resolved against iteration N's exact artifacts."""

    reference: ArtifactReference
    artifact_type: str
    item: dict[str, object] | str


@dataclass(frozen=True)
class DecisionResult:
    """What one decision call established. Not persisted, not an artifact.

    `outcome` is `ARCHITECTURE_REWORK_RECORDED` or `ARCHITECTURE_APPROVED` for
    a Decision this call wrote and confirmed, `DECISION_ALREADY_RECORDED` for
    an equivalent one already durable. Every id, digest and `recorded_at` is
    the durable Decision's. For a new REWORK, `recovery` is what the delegated
    I10 recovery reached and `recovery_refusal` its refusal, if any: the
    REWORK stays durable either way and is never rolled back.
    """

    outcome: DecisionResultCode
    decision: str
    iteration: int
    decision_document_id: str
    decision_digest: str
    review_result_document_id: str
    review_result_digest: str
    architecture_fingerprint: str
    recorded_at: str
    decision_written: bool
    recovery: RecoveryResult | None = None
    recovery_refusal: RecoveryRefused | None = None


@dataclass(frozen=True)
class _Call:
    """One decision command's caller inputs, held as values."""

    workspace: CycleWorkspace
    evidence: RequirementEvidenceWorkspace
    project_id: str
    cycle_id: object
    decision: str
    iteration: object
    review_result_document_id: str
    accepted: tuple[AcceptedDisposition, ...]
    reason: str | None


@dataclass(frozen=True)
class _Target:
    """The exact target triple resolved by one fresh gate pass. Read-only."""

    context: BootstrapContext
    manifest: TsaArtifact
    iteration: int
    review_document_id: str
    review: TsaArtifact
    process_document_id: str
    process: TsaArtifact
    decision_document_id: str
    #: The verified durable Decision at `(cycle, N)`, or None.
    durable: TsaArtifact | None
    #: Process and Review digests of every other iteration of this cycle.
    other_iterations: frozenset[str]
    #: The Decision slot is this call's own just-created empty shell.
    own_shell: bool = False


def _utc_now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Refusal plumbing
# ---------------------------------------------------------------------------


#: The exact trailing no-write claims a gate refusal can end with, each with
#: what stays true of it once this call has mutated something.
NO_WRITE_CLAIMS = (
    (" Nothing was written and no model was called.", ""),
    (
        " The whole selection is refused and nothing was written.",
        " The whole selection is refused.",
    ),
    (" Nothing was written.", ""),
)
#: After the body write: what the call did, whatever the read-back says.
BODY_WRITE_KEPT = (
    "{outcome}; it is neither repeated nor rolled back, and no success is "
    "reported because its read-back did not validate. "
)


def _message_after_mutation(message: str) -> str:
    """A gate refusal without its own trailing no-write claim, which this call
    can no longer make once it has created or written the Decision.

    Only an exact known trailing sentence is changed; the gate's diagnosis,
    code and details are kept as they are.
    """
    for claim, remains in NO_WRITE_CLAIMS:
        if message.endswith(claim):
            return f"{message[: -len(claim)]}{remains}"
    return message


@contextmanager
def _shared(prefix: str = "", *, mutated: bool = False) -> Iterator[None]:
    """A refusal of the shared gate keeps its code and details.

    `prefix` says what this call already did; once it has mutated anything,
    the gate's own "nothing was written" sentence is no longer true and is
    dropped (`_message_after_mutation`).
    """
    try:
        yield
    except ArchitectRefused as refused:
        message = str(refused)
        if mutated:
            message = _message_after_mutation(message)
        raise DecisionRefused(
            refused.code, f"{prefix}{message}", refused.details
        ) from refused


def _write_failed(message: str, details: tuple[str, ...] = ()) -> DecisionRefused:
    return DecisionRefused(CycleResultCode.FIBERY_WRITE_FAILED, message, details)


def _not_current(message: str, prefix: str, *, mutated: bool) -> DecisionRefused:
    """`REVIEW_NOT_CURRENT`, saying truthfully whether anything was written."""
    consequence = "" if mutated else NOTHING_WRITTEN
    return DecisionRefused(
        DecisionResultCode.REVIEW_NOT_CURRENT, f"{prefix}{message}{consequence}"
    )


# ---------------------------------------------------------------------------
# Steps 1-2: resolve and validate the exact target triple (11.1, 11.1.1)
# ---------------------------------------------------------------------------


def _child_id(context: BootstrapContext, kind: DocumentKind, iteration: int) -> str:
    return derive_document_id(
        context.workspace_identity,
        context.project_entity_id,
        context.cycle_id,
        kind,
        iteration,
    )


def _resolve(
    call: _Call,
    prefix: str = "",
    *,
    mutated: bool = False,
    reads_own_shell: bool = False,
) -> _Target:
    """The exact target, from one fresh, read-only pass of the I10 recovery read.

    The gate decides every specific refusal first, with its own code: cycle
    resolution, a malformed, duplicate or foreign artifact, stale inputs, a
    divergent Architecture, an empty Decision shell, an unverifiable durable
    Decision. Only then is the triple matched: iteration N must be the current
    iteration at the Human Decision boundary or already decided, or an earlier
    iteration carrying a verified REWORK, and the supplied id must be N's own
    Review Result. Anything else is `REVIEW_NOT_CURRENT`. Nothing is inferred
    and nothing slides to another iteration.

    A cycle without a valid accepted Input Manifest — bootstrap state B or an
    empty Architecture shell — resolves but has no Review Result, so it is
    `REVIEW_NOT_CURRENT` (13.6, rows B and `EMPTY_ARCHITECTURE_SHELL`), not the
    `resume`-only `MANIFEST_INPUTS_REQUIRED` the gate reports, and nothing is
    repaired.

    `prefix` and `mutated` keep every refusal message truthful about what this
    call already wrote. `reads_own_shell` is passed only after this call's own
    known create, so that empty shell is read instead of refused.
    """
    try:
        with _shared(prefix, mutated=mutated):
            state = read_cycle_state(
                call.workspace,
                call.evidence,
                call.project_id,
                call.cycle_id,
                reads_own_decision_shell=reads_own_shell,
            )
    except DecisionRefused as refused:
        if refused.code is not ArchitectResultCode.MANIFEST_INPUTS_REQUIRED:
            raise
        raise _not_current(
            f"Cycle {call.cycle_id!r} has no valid accepted Input Manifest, so it "
            "has no Review Result to decide; nothing is repaired.",
            prefix,
            mutated=mutated,
        ) from refused
    current = state.target
    context = current.context
    iteration = call.iteration
    is_iteration = isinstance(iteration, int) and not isinstance(iteration, bool)
    if not is_iteration or not 1 <= iteration <= current.iteration:
        raise _not_current(
            f"Iteration {iteration!r} has no Review Result of cycle "
            f"{context.cycle_id!r} to decide; the current iteration is "
            f"{current.iteration}.",
            prefix,
            mutated=mutated,
        )
    if iteration == current.iteration:
        decided = _current_target(state, prefix, mutated=mutated)
    else:
        decided = _earlier_target(state, iteration, prefix, mutated=mutated)
    review_document_id = _child_id(context, DocumentKind.REVIEW_RESULT, iteration)
    if call.review_result_document_id != review_document_id:
        raise _not_current(
            f"Review Result {call.review_result_document_id!r} is not the Review "
            f"Result of iteration {iteration} of cycle {context.cycle_id!r}.",
            prefix,
            mutated=mutated,
        )
    return _Target(
        context=context,
        manifest=current.manifest,
        iteration=iteration,
        review_document_id=review_document_id,
        review=decided.review,
        process_document_id=_child_id(context, DocumentKind.PROCESS_RESULT, iteration),
        process=decided.process,
        decision_document_id=_child_id(context, DocumentKind.HUMAN_DECISION, iteration),
        durable=decided.decision,
        other_iterations=_other_iterations(state, decided),
        own_shell=iteration == current.iteration and state.decision_shell,
    )


@dataclass(frozen=True)
class _Bound:
    """One iteration's Review and Process, and its durable Decision if any."""

    review: TsaArtifact
    process: TsaArtifact
    decision: TsaArtifact | None


def _current_target(state: CycleState, prefix: str, *, mutated: bool) -> _Bound:
    """The current iteration: a valid current Review, decided or not (I10)."""
    current = state.target
    case = classify_recovery_case(state)
    review, process = current.review, current.process
    if (
        case not in (RecoveryCase.REVIEW_RECORDED, RecoveryCase.APPROVED)
        or review is None
        or process is None
    ):
        raise _not_current(
            f"Iteration {current.iteration} of cycle {current.context.cycle_id!r} "
            f"is at {case}, not at a valid current Review Result.",
            prefix,
            mutated=mutated,
        )
    return _Bound(review, process, state.decision)


def _earlier_target(
    state: CycleState, iteration: int, prefix: str, *, mutated: bool
) -> _Bound:
    """An earlier iteration: only one the gate verified a REWORK for."""
    decided: VerifiedDecision | None = next(
        (item for item in state.reworks if item.iteration == iteration), None
    )
    if decided is None:
        raise _not_current(
            f"Iteration {iteration} carries no verified REWORK.",
            prefix,
            mutated=mutated,
        )
    return _Bound(decided.review, decided.process, decided.decision)


def _other_iterations(state: CycleState, bound: _Bound) -> frozenset[str]:
    """Process and Review digests of every iteration but the target's."""
    current = state.target
    digests = {
        artifact.artifact_digest
        for decided in state.reworks
        for artifact in (decided.process, decided.review)
    }
    digests |= {
        artifact.artifact_digest
        for artifact in (current.process, current.review)
        if artifact is not None
    }
    return frozenset(
        digests - {bound.process.artifact_digest, bound.review.artifact_digest}
    )


# ---------------------------------------------------------------------------
# Step 4: semantic equivalence (11.3)
# ---------------------------------------------------------------------------


def _semantic_key(body: dict[str, object]) -> tuple[object, ...]:
    """Every field 11.3 compares; `recorded_at` and every reason excluded."""
    target = body["target"]
    process = body["process_result"]
    review = body["review_result"]
    return (
        body["decision"],
        target["iteration"],
        target["review_result_document_id"],
        target["review_result_digest"],
        body["architecture_document_id"],
        body["architecture_fingerprint"],
        body["manifest_digest"],
        body["ux_evidence_digest"],
        process["document_id"],
        process["payload_digest"],
        review["document_id"],
        review["payload_digest"],
    )


def decisions_equivalent(first: dict[str, object], second: dict[str, object]) -> bool:
    """Spec 11.3 over two Human Decision bodies. Pure.

    The twelve bound fields must match and the accepted references must be
    the same multiset, so their order never creates a conflict. `recorded_at`,
    `reason` and every `accepted_dispositions[*].reason` are excluded.
    """

    def references(body: dict[str, object]) -> Counter[str]:
        return Counter(item["ref"] for item in body["accepted_dispositions"])

    return _semantic_key(first) == _semantic_key(second) and references(
        first
    ) == references(second)


def _proposed_body(call: _Call, target: _Target, recorded_at: str) -> dict[str, object]:
    """The exact 4.6.5 body for this call against the resolved target.

    Every bound value is the one the gate validated; accepted dispositions
    keep the caller's order and reasons verbatim (no frozen ordering exists).
    """
    review_pair = {
        "document_id": target.review_document_id,
        "payload_digest": target.review.artifact_digest,
    }
    body: dict[str, object] = {
        "decision": call.decision,
        "target": {
            "iteration": target.iteration,
            "review_result_document_id": target.review_document_id,
            "review_result_digest": target.review.artifact_digest,
        },
        "architecture_document_id": target.context.architecture_document_id,
        "architecture_fingerprint": target.review.body["architecture_fingerprint"],
        "manifest_digest": target.manifest.body["manifest_digest"],
        "ux_evidence_digest": ux_evidence_digest(
            target.manifest.body["manifest_body"]["ux"]
        ),
        "process_result": {
            "document_id": target.process_document_id,
            "payload_digest": target.process.artifact_digest,
        },
        "review_result": review_pair,
        "accepted_dispositions": [
            {"ref": item.ref, "reason": item.reason} for item in call.accepted
        ],
        "recorded_at": recorded_at,
    }
    if call.reason is not None:
        body["reason"] = call.reason
    return body


def _compared(call: _Call, target: _Target, durable: TsaArtifact) -> DecisionResult:
    """11.1.1 step 4: the durable Decision decides; nothing is written."""
    proposed = _proposed_body(call, target, durable.body["recorded_at"])
    if not decisions_equivalent(proposed, durable.body):
        raise DecisionRefused(
            DecisionResultCode.DECISION_CONFLICT,
            f"Iteration {target.iteration} already carries a durable "
            f"{durable.body['decision']} that this {call.decision} does not match. "
            "Nothing was written and no model was called.",
            (target.decision_document_id,),
        )
    return _result(
        DecisionResultCode.DECISION_ALREADY_RECORDED, durable, decision_written=False
    )


def _result(
    outcome: DecisionResultCode, decision: TsaArtifact, *, decision_written: bool
) -> DecisionResult:
    body = decision.body
    return DecisionResult(
        outcome=outcome,
        decision=str(body["decision"]),
        iteration=int(body["target"]["iteration"]),
        decision_document_id=_decision_id_of(decision),
        decision_digest=decision.artifact_digest,
        review_result_document_id=str(body["target"]["review_result_document_id"]),
        review_result_digest=str(body["target"]["review_result_digest"]),
        architecture_fingerprint=str(body["architecture_fingerprint"]),
        recorded_at=str(body["recorded_at"]),
        decision_written=decision_written,
    )


def _decision_id_of(decision: TsaArtifact) -> str:
    return derive_document_id(
        decision.workspace_identity,
        decision.project_entity_id,
        decision.cycle_id,
        DocumentKind.HUMAN_DECISION,
        decision.iteration,
    )


# ---------------------------------------------------------------------------
# Step 5: dispositions (6.1-6.4) and approval availability (10.2)
# ---------------------------------------------------------------------------


def _disposition_refused(
    code: DecisionResultCode, ref: object, message: str
) -> DecisionRefused:
    return DecisionRefused(
        code, f"Accepted disposition {ref!r} {message}{NOTHING_WRITTEN}", (str(ref),)
    )


def _parse_references(
    accepted: tuple[AcceptedDisposition, ...],
) -> list[ArtifactReference]:
    """Grammar (6.1) and a known collection; then no reference twice (6.4)."""
    parsed: list[ArtifactReference] = []
    for index, item in enumerate(accepted):
        try:
            parsed.append(
                parse_reference(item.ref, ("accepted_dispositions", str(index)))
            )
        except InvalidTsaArtifact as error:
            raise _disposition_refused(
                DecisionResultCode.DISPOSITION_UNKNOWN_REFERENCE,
                item.ref,
                f"is not a reference of spec 6.1: {error}",
            ) from error
    spelled = [str(reference) for reference in parsed]
    for reference in spelled:
        if spelled.count(reference) > 1:
            raise _disposition_refused(
                DecisionResultCode.DISPOSITION_DUPLICATE_REFERENCE,
                reference,
                "is named more than once in this decision.",
            )
    return parsed


def _resolve_disposition(
    reference: ArtifactReference,
    sources: dict[str, tuple[str, dict[str, object]]],
    other_iterations: frozenset[str],
) -> ResolvedDisposition:
    """The source artifact, the collection for its type, the item in range."""
    source = sources.get(reference.digest)
    if source is None:
        if reference.digest in other_iterations:
            raise _disposition_refused(
                DecisionResultCode.DISPOSITION_FOREIGN_ITERATION,
                str(reference),
                "names an artifact of another iteration of this cycle.",
            )
        raise _disposition_refused(
            DecisionResultCode.DISPOSITION_UNKNOWN_REFERENCE,
            str(reference),
            "names no Process or Review Result of this cycle.",
        )
    artifact_type, arrays = source
    if not reference_allows_collection(artifact_type, reference.collection):
        raise _disposition_refused(
            DecisionResultCode.DISPOSITION_UNKNOWN_REFERENCE,
            str(reference),
            f"names collection {reference.collection!r}, which a {artifact_type} "
            "does not carry (spec 6.2).",
        )
    items = arrays[reference.collection]
    if reference.index >= len(items):
        raise _disposition_refused(
            DecisionResultCode.DISPOSITION_UNKNOWN_REFERENCE,
            str(reference),
            f"is out of range: {reference.collection} holds {len(items)} items.",
        )
    return ResolvedDisposition(reference, artifact_type, items[reference.index])


def _require_waivable(
    disposition: ResolvedDisposition, open_questions: set[str]
) -> None:
    """A material unresolved WHAT is never accepted (6.4; contract 7.4, 9.3).

    That is a Reviewer `material_unresolved_what`, an Architect material
    product question still open (`open_material_question_refs`, the one
    definition 10.2 also derives from), or the claim verification of one.
    """
    reference = disposition.reference
    item = disposition.item
    is_material_what = (
        reference.collection == NON_WAIVABLE_COLLECTION
        or str(reference) in open_questions
        or (
            reference.collection == CLAIM_VERIFICATIONS
            and isinstance(item, dict)
            and item["claim_ref"] in open_questions
        )
    )
    if is_material_what:
        raise _disposition_refused(
            DecisionResultCode.DISPOSITION_NOT_WAIVABLE,
            str(reference),
            "is a material unresolved WHAT, which is not waivable inside TSA "
            "(contract 7.4, 9.3).",
        )


def validate_accepted_dispositions(
    accepted: tuple[AcceptedDisposition, ...],
    process: TsaArtifact,
    review: TsaArtifact,
    other_iterations: frozenset[str],
) -> tuple[ResolvedDisposition, ...]:
    """Every accepted reference, resolved against iteration N's exact artifacts.

    Deterministic, read-free and model-free. In this order, refusing the first
    failure with its frozen code (6.4):

    1. grammar (6.1) and a known collection — `DISPOSITION_UNKNOWN_REFERENCE`;
    2. the same reference twice — `DISPOSITION_DUPLICATE_REFERENCE`;
    3. the digest names N's Process or Review Result; a Process or Review of
       another iteration of this cycle is `DISPOSITION_FOREIGN_ITERATION`,
       anything else `DISPOSITION_UNKNOWN_REFERENCE`;
    4. the collection is allowed for that artifact type (6.2) and the index is
       in range — else `DISPOSITION_UNKNOWN_REFERENCE`;
    5. waivability: a material unresolved WHAT is `DISPOSITION_NOT_WAIVABLE`.

    Every other resolved item — a technical risk or finding of any severity,
    an open architecture question, an assumption, a non-material or rejected
    product question — may be accepted individually (contract 9.2). Nothing
    is required to be accepted: the frozen policy makes acceptance a MAY.
    """
    parsed = _parse_references(accepted)
    sources = reference_sources(process, review)
    open_questions = open_material_question_refs(
        review.body["reviewer_response"], process
    )
    resolved = []
    for reference in parsed:
        disposition = _resolve_disposition(reference, sources, other_iterations)
        _require_waivable(disposition, open_questions)
        resolved.append(disposition)
    return tuple(resolved)


def _require_approvable(target: _Target) -> None:
    """Spec 10.2: two derived statuses make approval unavailable, never waived."""
    status = target.review.body["derived_status"]
    if status in UNAPPROVABLE_STATUSES:
        raise DecisionRefused(
            DecisionResultCode(status),
            f"Review Result {target.review_document_id!r} of iteration "
            f"{target.iteration} derives {status}; approval is unavailable and "
            "is not waivable. Nothing was written and no model was called.",
            (target.review_document_id,),
        )


def _require_iteration_available(call: _Call, target: _Target) -> None:
    """A REWORK of the last permitted iteration would open one beyond it (4.5)."""
    if call.decision == REWORK and target.iteration >= ITERATION_MAX:
        raise DecisionRefused(
            ArchitectResultCode.ITERATION_LIMIT,
            f"A REWORK of iteration {target.iteration} would open iteration "
            f"{target.iteration + 1}; the limit is {ITERATION_MAX}. Nothing was "
            "written.",
        )


# ---------------------------------------------------------------------------
# The Human Decision artifact (4.6.5, 11)
# ---------------------------------------------------------------------------


def decision_document_name(context: BootstrapContext, iteration: int) -> str:
    """The navigation name of one Human Decision Document. Never identity."""
    return DECISION_NAME_TEMPLATE.format(cycle_id=context.cycle_id, iteration=iteration)


def render_human_decision_carrier(
    context: BootstrapContext, iteration: int, sealed: dict[str, object]
) -> str:
    """The immutable carrier of 4.1: heading, one paragraph, one JSON fence."""
    heading = DECISION_HEADING_TEMPLATE.format(
        name=decision_document_name(context, iteration)
    )
    return (
        f"{heading}\n"
        "\n"
        f"{DECISION_PROSE}\n"
        "\n"
        f"{JSON_FENCE_OPENER}\n"
        f"{canonical_artifact_json(sealed)}\n"
        f"{FENCE_MARKER}\n"
    )


def _sealed_decision(target: _Target, body: dict[str, object]) -> dict[str, object]:
    context = target.context
    return sealed_artifact(
        {
            "artifact_type": HUMAN_DECISION,
            "schema_version": SCHEMA_VERSION,
            "workspace_identity": context.workspace_identity,
            "project_entity_id": context.project_entity_id,
            "project_code": context.project_code,
            "cycle_id": context.cycle_id,
            "iteration": target.iteration,
            "body": body,
        }
    )


# ---------------------------------------------------------------------------
# Persisting the Decision (14.1, 14.4.1 window F)
# ---------------------------------------------------------------------------


def _require_same_target(
    prepared: _Target, fresh: _Target, prefix: str = "", *, mutated: bool = False
) -> None:
    """Immediately before a mutation the target still binds the same tuple.

    A fresh pass that validates a different Review, Process, Manifest (and so
    UX evidence) or Architecture binding for N is not the boundary this
    Decision was prepared for: nothing is re-bound to it.
    """
    bound = (
        (prepared.iteration, fresh.iteration),
        (prepared.review_document_id, fresh.review_document_id),
        (prepared.review.artifact_digest, fresh.review.artifact_digest),
        (prepared.process_document_id, fresh.process_document_id),
        (prepared.process.artifact_digest, fresh.process.artifact_digest),
        (prepared.manifest.artifact_digest, fresh.manifest.artifact_digest),
        (
            prepared.context.architecture_document_id,
            fresh.context.architecture_document_id,
        ),
        (
            prepared.review.body["architecture_fingerprint"],
            fresh.review.body["architecture_fingerprint"],
        ),
    )
    if any(before != now for before, now in bound):
        raise _not_current(
            f"Review Result {prepared.review_document_id!r} no longer binds the "
            f"tuple this decision was prepared against for iteration "
            f"{prepared.iteration}.",
            prefix,
            mutated=mutated,
        )


def _settled(call: _Call, prepared: _Target, fresh: _Target) -> DecisionResult | None:
    """A Decision durable now decides by 11.3; otherwise the tuple must hold."""
    if fresh.durable is not None:
        return _compared(call, fresh, fresh.durable)
    _require_same_target(prepared, fresh)
    return None


def _create_decision_shell(call: _Call, prepared: _Target) -> DecisionResult | None:
    """Create the deterministic child, rediscovering after an unknown outcome.

    Each attempt is preceded by a fresh target resolution — the revalidation
    immediately before the mutation (14.1). After an unknown outcome that
    resolution is the rediscovery of window F at both levels: the gate first,
    then the slot. An empty shell it finds is `DECISION_SHELL_UNRECOVERABLE`
    (the gate's own refusal) and is never completed, a durable Decision is
    compared (11.3), and an absent slot permits one retry at the same id.
    Returns a result only when a durable Decision settled the call; None
    means this call's own create returned normally.
    """
    context = prepared.context
    name = decision_document_name(context, prepared.iteration)
    current = _resolve(call)
    for _ in range(DECISION_CREATE_ATTEMPTS):
        settled = _settled(call, prepared, current)
        if settled is not None:
            return settled
        with _shared():
            root = resolve_root_placement(call.workspace, context)
        try:
            call.workspace.create_tsa_child_document(
                prepared.decision_document_id, name, root.document_id
            )
        except FiberyError:
            current = _resolve(
                call, "After an unknown Decision create outcome: ", mutated=True
            )
            continue
        return None
    settled = _settled(call, prepared, current)
    if settled is not None:
        return settled
    raise _write_failed(
        f"The Human Decision create did not become durable in "
        f"{DECISION_CREATE_ATTEMPTS} attempts at the same id "
        f"{prepared.decision_document_id!r}.",
        (prepared.decision_document_id,),
    )


def _revalidate_own_shell(call: _Call, prepared: _Target) -> DecisionResult | None:
    """After this call's own known create: the full target again, then the slot.

    The pre-create pass is no authority for the body write (contract 10,
    14.2): the whole gate runs again — discovery, Manifest, Architecture,
    lineage, Requirement and UX currentness — reading the new shell rather
    than refusing it, and the tuple must still be the prepared one. A Decision
    found in the slot instead is compared and never written over; a slot that
    is no longer this call's empty shell is a write failure. Every refusal
    says the shell exists and stays empty.
    """
    document_id = prepared.decision_document_id
    prefix = SHELL_KEPT.format(document_id=document_id)
    fresh = _resolve(call, prefix, mutated=True, reads_own_shell=True)
    if fresh.durable is not None:
        return _compared(call, fresh, fresh.durable)
    if not fresh.own_shell:
        raise _write_failed(
            f"The Decision create returned, but Human Decision {document_id!r} is "
            "not observable as its empty shell now; its body was not written.",
            (document_id,),
        )
    _require_same_target(prepared, fresh, prefix, mutated=True)
    return None


def _write_decision_body(call: _Call, prepared: _Target, carrier: str) -> str:
    """The body write, preceded only by the fresh child and root placement.

    The last remote calls before the write are the Decision child and the
    Architecture root placement with their local predicates (2.2.1); no
    content is read between them and it. Returns how the write went, for the
    read-back's message.
    """
    document_id = prepared.decision_document_id
    with _shared(SHELL_KEPT.format(document_id=document_id), mutated=True):
        shell = resolve_child_placement(call.workspace, prepared.context, document_id)
    if shell is None or not shell.secret:
        raise _write_failed(
            f"The Decision create returned, but Human Decision {document_id!r} "
            "has no writable body now; its body was not written.",
            (document_id,),
        )
    try:
        call.workspace.write_document_content(shell.secret, carrier)
    except FiberyError as error:
        return f"The Decision body write outcome was unknown ({error})"
    return "The Decision body was written"


def _confirm(
    call: _Call, prepared: _Target, sealed: dict[str, object], outcome: str
) -> DecisionResult:
    """Read back through a fresh target resolution, then require the artifact.

    The gate validates the Decision first — schema, digest, identity, and for
    an APPROVE or REWORK all seven lineage invariants — so a specific durable
    refusal keeps its code: an empty shell is `DECISION_SHELL_UNRECOVERABLE`
    and stale inputs `INPUTS_STALE`, the Decision already written standing
    either way. Then: exactly the artifact written is success; another valid
    Decision is compared (11.3); an absent slot is `FIBERY_WRITE_FAILED`.
    """
    after = _resolve(
        call,
        BODY_WRITE_KEPT.format(outcome=outcome),
        mutated=True,
    )
    durable = after.durable
    if durable is None:
        raise _write_failed(
            f"{outcome}, but Human Decision {prepared.decision_document_id!r} "
            "reads back no Decision, so it is not durable. Nothing was retried.",
            (prepared.decision_document_id,),
        )
    if durable.artifact_digest != sealed["artifact_digest"]:
        return _compared(call, after, durable)
    code = (
        DecisionResultCode.ARCHITECTURE_APPROVED
        if call.decision == APPROVE
        else DecisionResultCode.ARCHITECTURE_REWORK_RECORDED
    )
    return _result(code, durable, decision_written=True)


def _decide(call: _Call, clock: Clock) -> DecisionResult:
    """11.1.1, in its frozen order, then the 14.1 mutation cycle."""
    target = _resolve(call)
    if target.durable is not None:
        return _compared(call, target, target.durable)
    if call.decision == APPROVE:
        _require_approvable(target)
    validate_accepted_dispositions(
        call.accepted, target.process, target.review, target.other_iterations
    )
    _require_iteration_available(call, target)
    sealed = _sealed_decision(
        target, _proposed_body(call, target, created_at_now(clock))
    )
    carrier = render_human_decision_carrier(target.context, target.iteration, sealed)
    settled = _create_decision_shell(call, target)
    if settled is not None:
        return settled
    settled = _revalidate_own_shell(call, target)
    if settled is not None:
        return settled
    outcome = _write_decision_body(call, target, carrier)
    return _confirm(call, target, sealed, outcome)


def _call(
    decision: str,
    workspace: CycleWorkspace,
    evidence: RequirementEvidenceWorkspace,
    project_id: str,
    cycle_id: object,
    iteration: object,
    review_result_document_id: str,
    accepted: tuple[AcceptedDisposition, ...],
    reason: str | None,
) -> _Call:
    return _Call(
        workspace=workspace,
        evidence=evidence,
        project_id=project_id,
        cycle_id=cycle_id,
        decision=decision,
        iteration=iteration,
        review_result_document_id=review_result_document_id,
        accepted=tuple(accepted),
        reason=reason,
    )


def record_approve(
    workspace: CycleWorkspace,
    evidence: RequirementEvidenceWorkspace,
    project_id: str,
    cycle_id: object,
    iteration: object,
    review_result_document_id: str,
    *,
    accepted_dispositions: tuple[AcceptedDisposition, ...] = (),
    reason: str | None = None,
    clock: Clock = _utc_now,
) -> DecisionResult:
    """Record APPROVE against the exact target `(cycle, N, Review Result id)`.

    Deterministic and model-free (13.4): no model runtime is taken, so none is
    reachable. In the frozen order of 11.1.1 — the target resolved and
    validated fresh; a durable Decision at `(cycle, N)` compared and nothing
    written; otherwise approval availability (10.2), every disposition
    reference (6.4), one APPROVE created, written, read back and revalidated.
    Success is reported only after that read-back, as `ARCHITECTURE_APPROVED`.

    The caller (I12) holds the workspace guard for the whole command and owns
    the explicit `--confirm` act; this function takes no lock and infers no
    approver. The clock is read once, and only for a new Decision. `reason`
    and every disposition reason must be non-empty text (4.6.5): the caller
    guarantees it, and I01 refuses a violation before anything is written.
    """
    call = _call(
        APPROVE,
        workspace,
        evidence,
        project_id,
        cycle_id,
        iteration,
        review_result_document_id,
        accepted_dispositions,
        reason,
    )
    return _decide(call, clock)


def record_rework(
    workspace: CycleWorkspace,
    evidence: RequirementEvidenceWorkspace,
    architect_model: ModelRuntime,
    reviewer_model: ModelRuntime,
    project_id: str,
    cycle_id: object,
    iteration: object,
    review_result_document_id: str,
    *,
    accepted_dispositions: tuple[AcceptedDisposition, ...] = (),
    reason: str | None = None,
    clock: Clock = _utc_now,
) -> DecisionResult:
    """Record REWORK against the exact target, then carry the cycle on (13.3).

    The same 11.1.1 order as `record_approve`, without the approval status
    check: a REWORK is a human instruction to revise, available at any
    derived status, bound to the same Input Manifest, and it authorizes N+1
    only. A durable Decision at `(cycle, N)` — this REWORK retried, or any
    other — is answered by comparison alone: nothing is written, no model is
    called and no recovery runs, so a retry never opens N+2.

    Only after a NEW REWORK is confirmed durable by read-back does this hand
    the cycle to `recover_architecture_cycle` (I10), from fresh durable state:
    N+1 is opened there, the Architect and the Reviewer run at most once each,
    and it stops at the next boundary. A recovery refusal is returned in
    `recovery_refusal`; the REWORK is never rolled back.

    The caller (I12) holds the workspace guard for the whole command; none is
    taken here. The clock is read once for a new Decision's `recorded_at`, and
    is passed on to the recovery for the artifacts it creates.
    """
    call = _call(
        REWORK,
        workspace,
        evidence,
        project_id,
        cycle_id,
        iteration,
        review_result_document_id,
        accepted_dispositions,
        reason,
    )
    result = _decide(call, clock)
    if not result.decision_written:
        return result
    try:
        recovery = recover_architecture_cycle(
            workspace,
            evidence,
            architect_model,
            reviewer_model,
            project_id,
            cycle_id,
            clock=clock,
        )
    except RecoveryRefused as refused:
        return _with_recovery(result, None, refused)
    return _with_recovery(result, recovery, None)


def _with_recovery(
    result: DecisionResult,
    recovery: RecoveryResult | None,
    refused: RecoveryRefused | None,
) -> DecisionResult:
    return replace(result, recovery=recovery, recovery_refusal=refused)
