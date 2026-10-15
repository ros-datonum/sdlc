"""I11 — Human Decision, approval binding, dispositions and idempotency.

Every scene is a real cycle in durable state D: the I04 bootstrap carrier, a
Requirement the frozen chain applied, the real I05 Manifest, and Process and
Review Results the real I07 and I08 stages wrote. A Decision is written only
by I11 itself, except where a test needs a durable state no command can reach
(a malformed or duplicated Decision), which is sealed through I01 by hand.
Only Fibery and the models are fakes, so every claim here is D-class: no live
replacement or deletion reliance (gate I-2), no live large write (gate I-3).
"""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

import pytest

from architect_fake import (
    TRACE_MODEL_CALL,
    RecordingModel,
    architect_response,
    architecture_writes,
    mutation_trace,
    payload_of,
    process_id,
    reset_trace,
    response_text,
    secret_of,
)
from recovery_fake import (
    CoveringReviewer,
    carrier,
    decided,
    no_model,
    recover,
    reviewed_scene,
)
from reviewer_fake import (
    applied_scene,
    claims,
    decision_id,
    finding,
    review_id,
    verification,
)
from sdlc import tsa_decision
from sdlc.fibery_workspace import FiberyError
from sdlc.model_runtime import ModelRuntimeError
from sdlc.tsa_architect import open_material_question_refs
from sdlc.tsa_artifacts import (
    canonical_artifact_json,
    compute_artifact_digest,
    extract_architecture_envelope,
    manifest_digest,
    sealed_artifact,
    validate_artifact,
)
from sdlc.tsa_decision import (
    AcceptedDisposition,
    DecisionRefused,
    DecisionResultCode,
    decisions_equivalent,
    record_approve,
    record_rework,
    render_human_decision_carrier,
    validate_accepted_dispositions,
)
from sdlc.tsa_recovery import RecoveryBoundary, RecoveryRefused
from sdlc.tsa_reviewer import run_reviewer_stage
from standard_fake import REQUIREMENT_ID
from test_tsa_admission import (
    APPLICABLE,
    ARCHITECTURE_ID,
    CONTEXT,
    CYCLE,
    MANIFEST_ID,
    NOT_APPLICABLE,
    PROJECT_ID,
    UX_DOCUMENT_ID,
    child_added_after_review,
    fail,
    root_edited_after_review,
    world,
)
from test_tsa_architect import other_architecture, other_process_carrier, reseal
from test_tsa_cycle import fixed_clock

DECISION_ID = decision_id(1)
REVIEW_ID = review_id(1)
PROCESS_ID = process_id(1)
CREATE = "create_tsa_child_document"
WRITE = "write_document_content"
READ = "read_document_content"
ACCEPTED = "Accepted as a known trade-off."
DOWN = "connection reset"
FIRST_RECORDED_AT = "2026-10-12T08:00:00Z"


class TickingClock:
    """A clock that returns a later instant on every read, and counts reads."""

    def __init__(self) -> None:
        self.reads = 0

    def __call__(self) -> datetime:
        self.reads += 1
        return datetime(2026, 10, 12, 8, 0, 0, tzinfo=UTC) + timedelta(
            seconds=self.reads - 1
        )


@pytest.fixture(autouse=True)
def recovery_only_after_a_new_rework(monkeypatch):
    """Every delegated recovery is counted; APPROVE paths must never reach one."""
    calls: list[str] = []
    real = tsa_decision.recover_architecture_cycle

    def counted(*args, **kwargs):
        calls.append("recover")
        return real(*args, **kwargs)

    monkeypatch.setattr(tsa_decision, "recover_architecture_cycle", counted)
    return calls


# --------------------------------------------------------------------------
# Scenes and calls
# --------------------------------------------------------------------------


def approve(scene, iteration=1, review=None, *, accept=(), reason=None, clock=None):
    return record_approve(
        scene.tsa,
        scene.req,
        PROJECT_ID,
        CYCLE,
        iteration,
        review_id(iteration) if review is None else review,
        accepted_dispositions=tuple(accept),
        reason=reason,
        clock=clock or TickingClock(),
    )


def rework(
    scene,
    iteration=1,
    review=None,
    *,
    architect=None,
    reviewer=None,
    accept=(),
    reason=None,
    clock=None,
    cycle=CYCLE,
):
    return record_rework(
        scene.tsa,
        scene.req,
        no_model(scene) if architect is None else architect,
        no_model(scene) if reviewer is None else reviewer,
        PROJECT_ID,
        cycle,
        iteration,
        review_id(iteration) if review is None else review,
        accepted_dispositions=tuple(accept),
        reason=reason,
        clock=clock or TickingClock(),
    )


def refused(action, *args, **kwargs) -> DecisionRefused:
    with pytest.raises(DecisionRefused) as caught:
        action(*args, **kwargs)
    return caught.value


def accept(*refs: str, reason: str = ACCEPTED) -> tuple[AcceptedDisposition, ...]:
    return tuple(AcceptedDisposition(ref, reason) for ref in refs)


def process_ref(scene, collection: str, index: int = 0, iteration: int = 1) -> str:
    digest = payload_of(scene, process_id(iteration))["artifact_digest"]
    return f"{digest}#{collection}/{index}"


def review_ref(scene, collection: str, index: int = 0, iteration: int = 1) -> str:
    digest = payload_of(scene, review_id(iteration))["artifact_digest"]
    return f"{digest}#{collection}/{index}"


def status_of(scene, iteration: int = 1) -> str:
    return payload_of(scene, review_id(iteration))["body"]["derived_status"]


def contents(scene) -> dict[str, str]:
    return {
        document_id: scene.tsa.content_of(document_id)
        for document_id in scene.tsa.documents
    }


def models_called(scene) -> int:
    return [name for name, _ in scene.tsa.log].count(TRACE_MODEL_CALL)


def nothing_happened(scene) -> None:
    """No mutation anywhere and no model call (11.1.1 steps 2 and 4)."""
    assert scene.tsa.mutations == []
    assert scene.req.mutations == []
    assert models_called(scene) == 0


def only_the_decision_written(scene, iteration: int = 1) -> None:
    """Write confinement, from the operation log: the Decision child only."""
    document_id = decision_id(iteration)
    assert scene.tsa.mutations == [
        f"create:{document_id}",
        f"write:{secret_of(scene, document_id)}",
    ]
    assert scene.req.mutations == []


def decision_payload(scene, iteration: int = 1) -> dict:
    payload = payload_of(scene, decision_id(iteration))
    validate_artifact(payload)
    return payload


def acceptance_bound_elsewhere(scene) -> None:
    """The Manifest's acceptance names another digest; hand-sealed (I01 refuses)."""
    manifest = payload_of(scene, MANIFEST_ID)
    manifest["body"]["acceptance"]["manifest_digest"] = "0" * 64
    del manifest["artifact_digest"]
    manifest["artifact_digest"] = compute_artifact_digest(manifest)
    prefix = scene.tsa.content_of(MANIFEST_ID).split("```json")[0]
    scene.tsa.set_content(
        MANIFEST_ID, f"{prefix}```json\n{canonical_artifact_json(manifest)}\n```\n"
    )


def manifest_resealed(scene) -> None:
    """Another Manifest I01 accepts on its own, which nothing else binds."""

    def change(payload: dict) -> None:
        body = payload["body"]
        body["manifest_body"]["ux"]["reason"] = "Re-decided after the Review."
        digest = manifest_digest(body["manifest_body"])
        body["manifest_digest"] = digest
        body["acceptance"]["manifest_digest"] = digest

    reseal(scene, MANIFEST_ID, change)


def review_resealed(scene) -> None:
    """Another valid Review Result for the same slot, with another digest."""
    reseal(
        scene,
        REVIEW_ID,
        lambda payload: payload["body"]["reviewer_response"]["assessment"].update(
            completeness="Rewritten after the decision was prepared."
        ),
    )


def body_writes(scene, iteration: int = 1) -> int:
    """Body writes attempted to that iteration's Decision Document."""
    document = scene.tsa.documents.get(decision_id(iteration))
    if document is None:
        return 0
    return scene.tsa.log.count((WRITE, document.secret))


def ux_reads(scene) -> list[tuple[str, str]]:
    return [entry for entry in scene.tsa.log if entry[1] == UX_DOCUMENT_ID]


def place_decision(scene, record: dict, document_id: str = DECISION_ID) -> None:
    scene.tsa.seed_child(document_id, ARCHITECTURE_ID, carrier(document_id, record))
    reset_trace(scene)


def product_question(material: bool = True) -> dict:
    return {
        "detail": "Must a logged-out user be shown a login prompt?",
        "requirement_id": REQUIREMENT_ID,
        "material": material,
    }


def question_scene(outcome: str, severity: str | None = None):
    """An Architect material product question, verified with `outcome`."""
    response = architect_response(product_questions=[product_question()])
    scene = applied_scene(architect=response_text(response))
    question = process_ref(scene, "product_questions")
    verifications = [
        verification(ref, outcome, severity) if ref == question else verification(ref)
        for ref in claims(scene)
    ]
    run_reviewer_stage(
        scene.tsa,
        scene.req,
        CoveringReviewer(scene, changes={"verifications": verifications}),
        PROJECT_ID,
        CYCLE,
        clock=fixed_clock,
    )
    reset_trace(scene)
    return scene


def material_what() -> dict:
    return {
        "detail": "Which users may log in at all?",
        "requirement_id": REQUIREMENT_ID,
    }


def reworked_to_iteration_two(scene):
    """A real REWORK of iteration 1, carried by I10 to the next boundary."""
    result = rework(
        scene,
        architect=RecordingModel(scene),
        reviewer=CoveringReviewer(scene, 2),
    )
    reset_trace(scene)
    return result


# --------------------------------------------------------------------------
# A. Target triple (11.1 steps 1-4; 11.1.1 step 2)
# --------------------------------------------------------------------------


def test_a_cycle_with_no_architecture_document_is_cycle_not_found():
    scene = reviewed_scene()

    error = refused(rework, scene, cycle="arch-2026-09-z")

    assert error.code == "CYCLE_NOT_FOUND"
    nothing_happened(scene)


@pytest.mark.parametrize("architecture", ["bootstrapped", "empty shell"])
@pytest.mark.parametrize("action", [approve, rework], ids=["approve", "rework"])
def test_a_cycle_without_an_accepted_manifest_is_review_not_current(
    architecture, action
):
    """13.6 rows B and EMPTY_ARCHITECTURE_SHELL: no Review, and no repair."""
    scene = world(architecture)
    reset_trace(scene)
    before = scene.tsa.content_of(ARCHITECTURE_ID)

    error = refused(action, scene)

    assert error.code == "REVIEW_NOT_CURRENT"
    assert str(error).endswith("Nothing was written and no model was called.")
    nothing_happened(scene)
    assert scene.tsa.content_of(ARCHITECTURE_ID) == before
    assert MANIFEST_ID not in scene.tsa.documents


def test_an_invalid_cycle_id_keeps_its_own_code():
    scene = reviewed_scene()

    error = refused(rework, scene, cycle="Not A Cycle")

    assert error.code == "INVALID_CYCLE_ID"
    nothing_happened(scene)


@pytest.mark.parametrize("iteration", [0, 2, 1000, -1, True, "1"])
def test_an_iteration_without_a_review_of_that_iteration_is_not_current(iteration):
    scene = reviewed_scene()

    error = refused(approve, scene, iteration, REVIEW_ID)

    assert error.code == "REVIEW_NOT_CURRENT"
    nothing_happened(scene)


@pytest.mark.parametrize(
    "review", [PROCESS_ID, MANIFEST_ID, ARCHITECTURE_ID, review_id(2), "doc-x"]
)
def test_a_review_id_that_is_not_iterations_own_review_is_not_current(review):
    scene = reviewed_scene()

    error = refused(approve, scene, 1, review)

    assert error.code == "REVIEW_NOT_CURRENT"
    nothing_happened(scene)


def test_no_review_yet_is_not_current_and_never_runs_the_reviewer():
    scene = applied_scene()
    reviewer = CoveringReviewer(scene)

    error = refused(rework, scene, reviewer=reviewer)

    assert error.code == "REVIEW_NOT_CURRENT"
    assert reviewer.calls == []
    nothing_happened(scene)


def test_an_empty_review_shell_is_not_current_and_is_not_completed():
    scene = applied_scene()
    scene.tsa.seed_child(REVIEW_ID, ARCHITECTURE_ID, "")
    reset_trace(scene)

    error = refused(approve, scene)

    assert error.code == "REVIEW_NOT_CURRENT"
    nothing_happened(scene)
    assert scene.tsa.content_of(REVIEW_ID) == ""


def test_the_right_review_id_over_a_replaced_process_is_malformed_not_decided():
    scene = reviewed_scene()
    scene.tsa.set_content(PROCESS_ID, other_process_carrier())
    reset_trace(scene)

    error = refused(approve, scene)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene)


def test_row_8_architecture_changed_after_review_makes_approval_unavailable():
    scene = reviewed_scene()
    scene.tsa.set_content(ARCHITECTURE_ID, other_architecture(scene, "Edited.").text)
    reset_trace(scene)

    error = refused(approve, scene)

    assert error.code == "ARCHITECTURE_DIVERGED"
    nothing_happened(scene)
    assert DECISION_ID not in scene.tsa.documents


def test_a_manifest_acceptance_bound_elsewhere_keeps_its_specific_code():
    scene = reviewed_scene()
    acceptance_bound_elsewhere(scene)
    reset_trace(scene)

    error = refused(approve, scene)

    assert error.code == "MANIFEST_ACCEPTANCE_MISMATCH"
    nothing_happened(scene)


@pytest.mark.parametrize(
    "drift", [root_edited_after_review, child_added_after_review], ids=["root", "child"]
)
@pytest.mark.parametrize("action", [approve, rework], ids=["approve", "rework"])
def test_stale_requirements_refuse_the_target(drift, action):
    scene = reviewed_scene()
    drift(scene)
    scene.req.mutations.clear()

    error = refused(action, scene)

    assert error.code == "INPUTS_STALE"
    nothing_happened(scene)


def test_stale_applicable_ux_refuses_the_target():
    scene = reviewed_scene(ux=APPLICABLE)
    scene.tsa.set_content(UX_DOCUMENT_ID, "# Checkout flow\n\nTwo screens now.\n")
    reset_trace(scene)

    error = refused(approve, scene)

    assert error.code == "INPUTS_STALE"
    nothing_happened(scene)


# --------------------------------------------------------------------------
# B. Precedence (11.1.1), and the decision slot
# --------------------------------------------------------------------------


def test_target_failure_is_decided_before_an_existing_decision_is_compared():
    scene = reviewed_scene()
    approve(scene)
    reset_trace(scene)

    error = refused(approve, scene, 1, PROCESS_ID)

    assert error.code == "REVIEW_NOT_CURRENT"
    nothing_happened(scene)


def test_an_existing_equivalent_decision_is_already_recorded():
    scene = reviewed_scene()
    first = approve(scene)
    reset_trace(scene)

    again = approve(scene)

    assert again.outcome is DecisionResultCode.DECISION_ALREADY_RECORDED
    assert again.decision_digest == first.decision_digest
    assert not again.decision_written
    nothing_happened(scene)


def test_an_existing_different_decision_is_a_conflict():
    scene = reviewed_scene(new_findings=[finding("WARNING")])
    approve(scene, accept=accept(review_ref(scene, "new_findings")))
    reset_trace(scene)

    error = refused(approve, scene)

    assert error.code == "DECISION_CONFLICT"
    nothing_happened(scene)


def test_an_empty_decision_shell_is_unrecoverable_and_never_filled():
    scene = reviewed_scene()
    scene.tsa.seed_child(DECISION_ID, ARCHITECTURE_ID, "")
    reset_trace(scene)

    for action in (approve, rework):
        error = refused(action, scene)
        assert error.code == "DECISION_SHELL_UNRECOVERABLE"
    nothing_happened(scene)
    assert scene.tsa.content_of(DECISION_ID) == ""
    assert decision_id(1) in scene.tsa.documents


@pytest.mark.parametrize(
    "content",
    [
        "Someone typed here.\n",
        '# Human Decision\n\nProse.\n\n```json\n{"artifact_type": 1}\n```\n',
    ],
)
def test_a_malformed_decision_is_refused_and_never_overwritten(content):
    scene = reviewed_scene()
    scene.tsa.seed_child(DECISION_ID, ARCHITECTURE_ID, content)
    reset_trace(scene)

    error = refused(approve, scene)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene)
    assert scene.tsa.content_of(DECISION_ID) == content


def test_a_resealed_lineage_invalid_decision_is_malformed():
    scene = reviewed_scene()
    record = decided(scene, "APPROVE")
    record["body"]["ux_evidence_digest"] = "0" * 64
    place_decision(scene, sealed_artifact(record))

    error = refused(approve, scene)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene)


def test_a_valid_decision_at_a_non_derived_id_is_a_duplicate_not_a_conflict():
    scene = reviewed_scene()
    place_decision(scene, decided(scene, "REWORK"), "stray-decision-document")

    error = refused(approve, scene)

    assert error.code == "ARTIFACT_DUPLICATE"
    nothing_happened(scene)
    assert DECISION_ID not in scene.tsa.documents


# --------------------------------------------------------------------------
# C. Semantic equivalence (11.3)
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def body() -> dict:
    scene = reviewed_scene(new_findings=[finding("WARNING"), finding("INFO")])
    approve(scene, accept=accept(review_ref(scene, "new_findings", 0)))
    payload = decision_payload(scene)["body"]
    payload["accepted_dispositions"].append(
        {"ref": review_ref(scene, "new_findings", 1), "reason": "Second."}
    )
    payload["reason"] = "Ship it."
    return payload


def changed(body: dict, path: tuple[str, ...], value) -> dict:
    other = copy.deepcopy(body)
    holder = other
    for key in path[:-1]:
        holder = holder[key]
    holder[path[-1]] = value
    return other


BOUND_FIELDS = [
    ("decision",),
    ("target", "iteration"),
    ("target", "review_result_document_id"),
    ("target", "review_result_digest"),
    ("architecture_document_id",),
    ("architecture_fingerprint",),
    ("manifest_digest",),
    ("ux_evidence_digest",),
    ("process_result", "document_id"),
    ("process_result", "payload_digest"),
    ("review_result", "document_id"),
    ("review_result", "payload_digest"),
]


@pytest.mark.parametrize("path", BOUND_FIELDS, ids=".".join)
def test_every_bound_field_takes_part_in_the_comparison(body, path):
    value = 7 if path == ("target", "iteration") else "REWORK-or-other"
    assert decisions_equivalent(body, body)
    assert not decisions_equivalent(body, changed(body, path, value))


def test_recorded_at_and_every_reason_are_excluded(body):
    other = changed(body, ("recorded_at",), "2030-01-01T00:00:00Z")
    other["reason"] = "Another explanation."
    for item in other["accepted_dispositions"]:
        item["reason"] = "Reworded."
    del other["reason"]

    assert decisions_equivalent(body, other)


def test_accepted_references_compare_as_a_multiset(body):
    reordered = copy.deepcopy(body)
    reordered["accepted_dispositions"].reverse()
    one_changed = copy.deepcopy(body)
    one_changed["accepted_dispositions"][0]["ref"] = "f" * 64 + "#new_findings/0"
    repeated = copy.deepcopy(body)
    repeated["accepted_dispositions"].append(body["accepted_dispositions"][0])
    dropped = copy.deepcopy(body)
    dropped["accepted_dispositions"].pop()

    assert decisions_equivalent(body, reordered)
    assert not decisions_equivalent(body, one_changed)
    assert not decisions_equivalent(body, repeated)
    assert not decisions_equivalent(body, dropped)


def test_a_retry_with_reordered_refs_and_new_reasons_is_already_recorded():
    scene = reviewed_scene(new_findings=[finding("WARNING")])
    refs = (process_ref(scene, "risks"), review_ref(scene, "new_findings"))
    first = approve(scene, accept=accept(*refs), reason="First words.")
    stored = scene.tsa.content_of(DECISION_ID)
    reset_trace(scene)

    again = approve(
        scene, accept=accept(*reversed(refs), reason="Other words."), reason="Later."
    )

    assert again.outcome is DecisionResultCode.DECISION_ALREADY_RECORDED
    assert again.recorded_at == first.recorded_at
    assert scene.tsa.content_of(DECISION_ID) == stored, "reasons never rewritten"
    nothing_happened(scene)


def test_a_retry_with_one_ref_changed_is_a_conflict():
    scene = reviewed_scene(new_findings=[finding("WARNING")])
    approve(scene, accept=accept(review_ref(scene, "new_findings")))
    reset_trace(scene)

    error = refused(approve, scene, accept=accept(process_ref(scene, "risks")))

    assert error.code == "DECISION_CONFLICT"
    nothing_happened(scene)


# --------------------------------------------------------------------------
# D. Dispositions (spec 6; row 49)
# --------------------------------------------------------------------------


def unknown_refs(scene) -> dict[str, str]:
    process = payload_of(scene, PROCESS_ID)["artifact_digest"]
    review = payload_of(scene, REVIEW_ID)["artifact_digest"]
    return {
        "not-a-reference": "not-a-reference",
        "uppercase-digest": f"{process.upper()}#risks/0",
        "leading-zero-index": f"{process}#risks/00",
        "negative-index": f"{process}#risks/-1",
        "unknown-collection": f"{process}#findings/0",
        "unknown-digest": f"{'f' * 64}#risks/0",
        "manifest-digest": f"{payload_of(scene, MANIFEST_ID)['artifact_digest']}#risks/0",
        "review-collection-on-process": f"{process}#new_findings/0",
        "process-collection-on-review": f"{review}#risks/0",
        "out-of-range": f"{process}#risks/1",
        "empty-collection-index": f"{process}#open_architecture_questions/0",
    }


@pytest.mark.parametrize(
    "case",
    [
        "not-a-reference",
        "uppercase-digest",
        "leading-zero-index",
        "negative-index",
        "unknown-collection",
        "unknown-digest",
        "manifest-digest",
        "review-collection-on-process",
        "process-collection-on-review",
        "out-of-range",
        "empty-collection-index",
    ],
)
@pytest.mark.parametrize("action", [approve, rework], ids=["approve", "rework"])
def test_row_49_an_unknown_reference_is_refused_with_zero_writes(case, action):
    scene = reviewed_scene()

    error = refused(action, scene, accept=accept(unknown_refs(scene)[case]))

    assert error.code == "DISPOSITION_UNKNOWN_REFERENCE"
    nothing_happened(scene)
    assert DECISION_ID not in scene.tsa.documents


@pytest.mark.parametrize("action", [approve, rework], ids=["approve", "rework"])
def test_row_49_the_same_reference_twice_is_refused_with_zero_writes(action):
    scene = reviewed_scene()
    risk = process_ref(scene, "risks")

    error = refused(
        action,
        scene,
        accept=(AcceptedDisposition(risk, "a"), AcceptedDisposition(risk, "b")),
    )

    assert error.code == "DISPOSITION_DUPLICATE_REFERENCE"
    nothing_happened(scene)


def test_row_49_a_reference_of_another_iteration_is_foreign():
    scene = reviewed_scene()
    reworked_to_iteration_two(scene)

    for ref in (process_ref(scene, "risks"), review_ref(scene, "claim_verifications")):
        error = refused(approve, scene, 2, accept=accept(ref))
        assert error.code == "DISPOSITION_FOREIGN_ITERATION"
    nothing_happened(scene)


def test_row_49_a_digest_no_artifact_of_this_cycle_carries_is_unknown():
    other = reviewed_scene()
    scene = reviewed_scene(new_findings=[finding("WARNING")])
    foreign = review_ref(other, "claim_verifications")
    assert foreign != review_ref(scene, "claim_verifications")

    error = refused(approve, scene, accept=accept(foreign))

    assert error.code == "DISPOSITION_UNKNOWN_REFERENCE"
    nothing_happened(scene)


def test_a_reviewer_material_unresolved_what_is_never_waivable():
    scene = reviewed_scene(material_unresolved_what=[material_what()])

    error = refused(
        rework, scene, accept=accept(review_ref(scene, "material_unresolved_what"))
    )

    assert error.code == "DISPOSITION_NOT_WAIVABLE"
    nothing_happened(scene)


@pytest.mark.parametrize("collection", ["product_questions", "claim_verifications"])
def test_an_open_material_product_question_is_never_waivable(collection):
    scene = question_scene("UNRESOLVED")
    question = process_ref(scene, "product_questions")
    ref = (
        question
        if collection == "product_questions"
        else review_ref(scene, "claim_verifications", claims(scene).index(question))
    )

    error = refused(rework, scene, accept=accept(ref))

    assert error.code == "DISPOSITION_NOT_WAIVABLE"
    nothing_happened(scene)


def test_validation_resolves_existence_collection_item_and_waivability():
    scene = reviewed_scene(new_findings=[finding("WARNING")])
    process = payload_of(scene, PROCESS_ID)
    review = payload_of(scene, REVIEW_ID)
    refs = (
        process_ref(scene, "assumptions"),
        process_ref(scene, "risks"),
        process_ref(scene, "product_questions"),
        review_ref(scene, "claim_verifications"),
        review_ref(scene, "new_findings"),
    )

    resolved = validate_accepted_dispositions(
        accept(*refs),
        validate_artifact(process),
        validate_artifact(review),
        frozenset(),
    )

    assert [str(item.reference) for item in resolved] == list(refs)
    assert [item.artifact_type for item in resolved] == [
        "tsa.process_result",
        "tsa.process_result",
        "tsa.process_result",
        "tsa.review_result",
        "tsa.review_result",
    ]
    assert resolved[1].item == process["body"]["architect_response"]["risks"][0]
    assert resolved[4].item == review["body"]["reviewer_response"]["new_findings"][0]


# --------------------------------------------------------------------------
# E. REWORK (rows 31, 48; spec 13.3)
# --------------------------------------------------------------------------


def test_row_31_rework_is_immutable_opens_n_plus_1_and_keeps_history():
    scene = reviewed_scene()
    history = {
        document_id: scene.tsa.content_of(document_id)
        for document_id in (PROCESS_ID, REVIEW_ID, MANIFEST_ID)
    }
    architect, reviewer = RecordingModel(scene), CoveringReviewer(scene, 2)

    result = rework(
        scene, architect=architect, reviewer=reviewer, reason="Name the refusal."
    )

    assert result.outcome is DecisionResultCode.ARCHITECTURE_REWORK_RECORDED
    assert result.decision_written and result.recovery_refusal is None
    trace = mutation_trace(scene)
    assert trace[:2] == [
        (CREATE, DECISION_ID),
        (WRITE, secret_of(scene, DECISION_ID)),
    ], "the Decision is durable before any model call"
    assert [name for name, _ in trace].count(TRACE_MODEL_CALL) == 2
    assert len(architect.calls) == 1 and len(reviewer.calls) == 1
    assert result.recovery.boundary is RecoveryBoundary.HUMAN_DECISION
    assert result.recovery.iteration == 2
    assert result.recovery.process_result_document_id == process_id(2)
    assert result.recovery.review_result_document_id == review_id(2)
    assert process_id(2) != PROCESS_ID and review_id(2) != REVIEW_ID
    for document_id, content in history.items():
        assert scene.tsa.content_of(document_id) == content, document_id
    stored = decision_payload(scene)
    assert stored["body"]["decision"] == "REWORK"
    assert stored["body"]["reason"] == "Name the refusal."
    assert (
        stored["body"]["manifest_digest"]
        == (payload_of(scene, MANIFEST_ID)["body"]["manifest_digest"])
    )
    assert scene.req.mutations == []


def test_a_rework_retry_after_the_cycle_advanced_is_a_no_op_and_opens_no_n_plus_2():
    scene = reviewed_scene()
    clock = TickingClock()
    first = rework(
        scene,
        architect=RecordingModel(scene),
        reviewer=CoveringReviewer(scene, 2),
        clock=clock,
    )
    stored = scene.tsa.content_of(DECISION_ID)
    reset_trace(scene)
    reads = clock.reads

    again = rework(scene, clock=clock, reason="Retried with another reason.")

    assert again.outcome is DecisionResultCode.DECISION_ALREADY_RECORDED
    assert again.iteration == 1
    assert again.recorded_at == first.recorded_at
    assert again.recovery is None and again.recovery_refusal is None
    assert clock.reads == reads, "a retry never reads the clock"
    assert scene.tsa.content_of(DECISION_ID) == stored
    assert process_id(3) not in scene.tsa.documents
    assert decision_id(2) not in scene.tsa.documents
    nothing_happened(scene)


def test_a_rework_retry_runs_no_recovery_even_when_n_plus_1_is_unfinished(
    recovery_only_after_a_new_rework,
):
    scene = reviewed_scene()
    failing = RecordingModel(scene, error=ModelRuntimeError("down"))
    first = rework(scene, architect=failing)
    assert first.outcome is DecisionResultCode.ARCHITECTURE_REWORK_RECORDED
    assert first.recovery is None
    assert first.recovery_refusal.code == "MODEL_RUNTIME_FAILED"
    assert recovery_only_after_a_new_rework == ["recover"]
    reset_trace(scene)

    again = rework(scene)

    assert again.outcome is DecisionResultCode.DECISION_ALREADY_RECORDED
    assert recovery_only_after_a_new_rework == ["recover"]
    assert process_id(2) not in scene.tsa.documents
    nothing_happened(scene)


def test_a_recovery_failure_after_rework_leaves_the_rework_durable():
    scene = reviewed_scene()
    architect = RecordingModel(scene, during=lambda: root_edited_after_review(scene))

    result = rework(scene, architect=architect)

    assert result.outcome is DecisionResultCode.ARCHITECTURE_REWORK_RECORDED
    assert result.recovery_refusal is not None
    assert result.recovery_refusal.code == "INPUTS_STALE"
    assert decision_payload(scene)["body"]["decision"] == "REWORK"


def test_row_48_rework_after_approve_is_a_conflict_and_the_cycle_stays_closed():
    scene = reviewed_scene()
    approve(scene)
    stored = contents(scene)
    reset_trace(scene)

    error = refused(
        rework,
        scene,
        architect=RecordingModel(scene),
        reviewer=CoveringReviewer(scene, 2),
    )

    assert error.code == "DECISION_CONFLICT"
    nothing_happened(scene)
    assert contents(scene) == stored
    assert process_id(2) not in scene.tsa.documents
    assert recover(scene).boundary is RecoveryBoundary.APPROVED


def test_row_48_symmetric_approve_after_rework_is_a_conflict(
    recovery_only_after_a_new_rework,
):
    scene = reviewed_scene()
    reworked_to_iteration_two(scene)
    stored = contents(scene)
    recovery_only_after_a_new_rework.clear()

    error = refused(approve, scene, 1, REVIEW_ID)

    assert error.code == "DECISION_CONFLICT"
    assert recovery_only_after_a_new_rework == []
    nothing_happened(scene)
    assert contents(scene) == stored


def test_the_same_approve_retried_is_already_recorded():
    scene = reviewed_scene()
    approve(scene)
    reset_trace(scene)

    assert approve(scene).outcome is DecisionResultCode.DECISION_ALREADY_RECORDED
    nothing_happened(scene)


def test_a_rework_of_the_last_permitted_iteration_is_refused(monkeypatch):
    scene = reviewed_scene()
    monkeypatch.setattr(tsa_decision, "ITERATION_MAX", 1)

    error = refused(rework, scene, architect=RecordingModel(scene))

    assert error.code == "ITERATION_LIMIT"
    nothing_happened(scene)


# --------------------------------------------------------------------------
# F. APPROVE (rows 16, 19, 20, 30, 32, 34; spec 13.4)
# --------------------------------------------------------------------------


def test_row_32_approve_binds_the_exact_tuple_revalidated_and_read_back(
    recovery_only_after_a_new_rework,
):
    scene = reviewed_scene()
    clock = TickingClock()
    process = payload_of(scene, PROCESS_ID)
    review = payload_of(scene, REVIEW_ID)
    manifest = payload_of(scene, MANIFEST_ID)["body"]

    result = approve(scene, clock=clock)

    assert result.outcome is DecisionResultCode.ARCHITECTURE_APPROVED
    stored = decision_payload(scene)
    assert stored["iteration"] == 1 and stored["cycle_id"] == CYCLE
    assert stored["body"] == {
        "decision": "APPROVE",
        "target": {
            "iteration": 1,
            "review_result_document_id": REVIEW_ID,
            "review_result_digest": review["artifact_digest"],
        },
        "architecture_document_id": ARCHITECTURE_ID,
        "architecture_fingerprint": review["body"]["architecture_fingerprint"],
        "manifest_digest": manifest["manifest_digest"],
        "ux_evidence_digest": tsa_decision.ux_evidence_digest(
            manifest["manifest_body"]["ux"]
        ),
        "process_result": {
            "document_id": PROCESS_ID,
            "payload_digest": process["artifact_digest"],
        },
        "review_result": {
            "document_id": REVIEW_ID,
            "payload_digest": review["artifact_digest"],
        },
        "accepted_dispositions": [],
        "recorded_at": FIRST_RECORDED_AT,
    }
    assert result.decision_digest == stored["artifact_digest"]
    assert result.recorded_at == FIRST_RECORDED_AT and clock.reads == 1
    assert "approved_by" not in stored["body"]
    assert scene.tsa.content_of(DECISION_ID) == render_human_decision_carrier(
        CONTEXT, 1, stored
    )
    only_the_decision_written(scene)
    assert models_called(scene) == 0
    assert recovery_only_after_a_new_rework == []
    assert architecture_writes(scene) == 0
    reset_trace(scene)
    assert recover(scene).boundary is RecoveryBoundary.APPROVED


def test_approve_revalidates_fresh_after_the_first_read_before_the_create():
    scene = reviewed_scene()

    approve(scene)

    gate_reads = [
        entry for entry in scene.tsa.log if entry == ("read_project", PROJECT_ID)
    ]
    assert len(gate_reads) == 4, (
        "resolve, revalidate before create, revalidate after create, read back"
    )


@pytest.mark.parametrize(
    "findings",
    [[], [finding("INFO")]],
    ids=["pass", "confirmed-info"],
)
def test_review_pass_needs_no_disposition(findings):
    scene = reviewed_scene(new_findings=findings)
    assert status_of(scene) == "REVIEW_PASS"

    assert approve(scene).outcome is DecisionResultCode.ARCHITECTURE_APPROVED


@pytest.mark.parametrize(
    ("severity", "status"),
    [("WARNING", "REVIEW_NEEDS_WORK"), ("BLOCKING", "REVIEW_BLOCKING")],
)
def test_row_20_an_accepted_technical_risk_is_recorded_and_approval_proceeds(
    severity, status
):
    scene = reviewed_scene(new_findings=[finding(severity)])
    assert status_of(scene) == status
    refs = (review_ref(scene, "new_findings"), process_ref(scene, "risks"))

    result = approve(
        scene,
        accept=(
            AcceptedDisposition(refs[0], "Known gap, tracked."),
            AcceptedDisposition(refs[1], "Format changes are rare."),
        ),
    )

    assert result.outcome is DecisionResultCode.ARCHITECTURE_APPROVED
    assert decision_payload(scene)["body"]["accepted_dispositions"] == [
        {"ref": refs[0], "reason": "Known gap, tracked."},
        {"ref": refs[1], "reason": "Format changes are rare."},
    ], "caller order and reasons kept verbatim"
    only_the_decision_written(scene)
    assert scene.tsa.content_of(REVIEW_ID), "acceptance never deletes the finding"


@pytest.mark.parametrize("severity", ["WARNING", "BLOCKING"])
def test_technical_findings_are_not_required_to_be_accepted(severity):
    """Spec 10.2: a human MAY accept; 13.8 has no code for not accepting."""
    scene = reviewed_scene(new_findings=[finding(severity)])

    result = approve(scene)

    assert result.outcome is DecisionResultCode.ARCHITECTURE_APPROVED
    assert decision_payload(scene)["body"]["accepted_dispositions"] == []


def test_row_16_a_material_unresolved_what_makes_approval_unavailable():
    scene = reviewed_scene(material_unresolved_what=[material_what()])
    assert status_of(scene) == "REVIEW_BLOCKED_ON_WHAT"

    for offered in ((), accept(review_ref(scene, "material_unresolved_what"))):
        error = refused(approve, scene, accept=offered)
        assert error.code == "REVIEW_BLOCKED_ON_WHAT"
    nothing_happened(scene)


def test_a_structurally_invalid_review_is_never_approvable():
    scene = applied_scene()
    run_reviewer_stage(
        scene.tsa,
        scene.req,
        CoveringReviewer(scene, changes={"verifications": []}),
        PROJECT_ID,
        CYCLE,
        clock=fixed_clock,
    )
    reset_trace(scene)
    assert status_of(scene) == "REVIEW_STRUCTURALLY_INVALID"

    error = refused(approve, scene, accept=accept(process_ref(scene, "risks")))

    assert error.code == "REVIEW_STRUCTURALLY_INVALID"
    nothing_happened(scene)


def test_row_30_product_question_evidence_preserved_approval_unavailable():
    scene = question_scene("UNRESOLVED")
    question = product_question()
    process_before = scene.tsa.content_of(PROCESS_ID)
    architecture_before = scene.tsa.content_of(ARCHITECTURE_ID)
    requirement_before = dict(scene.req.content)
    assert status_of(scene) == "REVIEW_BLOCKED_ON_WHAT"

    error = refused(approve, scene)

    assert error.code == "REVIEW_BLOCKED_ON_WHAT"
    intended = payload_of(scene, PROCESS_ID)["body"]["intended_output"]
    assert intended["product_questions"] == [question]
    envelope = extract_architecture_envelope(scene.tsa.content_of(ARCHITECTURE_ID))
    assert envelope["body"]["product_questions"] == [question]
    assert scene.tsa.content_of(PROCESS_ID) == process_before
    assert scene.tsa.content_of(ARCHITECTURE_ID) == architecture_before
    assert scene.req.content == requirement_before
    nothing_happened(scene)
    assert DECISION_ID not in scene.tsa.documents


def test_row_30_a_product_question_the_reviewer_rejected_no_longer_blocks():
    scene = question_scene("REJECTED")
    assert status_of(scene) == "REVIEW_PASS"

    result = approve(scene)

    assert result.outcome is DecisionResultCode.ARCHITECTURE_APPROVED
    assert payload_of(scene, PROCESS_ID)["body"]["intended_output"][
        "product_questions"
    ] == [product_question()]


def test_row_19_a_review_replaced_after_preparation_is_refused_before_the_create():
    scene = reviewed_scene()

    def replace_review_while_reading_the_clock() -> datetime:
        review_resealed(scene)
        return fixed_clock()

    error = refused(approve, scene, clock=replace_review_while_reading_the_clock)

    assert error.code == "REVIEW_NOT_CURRENT"
    assert scene.tsa.mutations == []
    assert DECISION_ID not in scene.tsa.documents


def test_row_19_a_review_of_a_superseded_iteration_cannot_be_approved():
    scene = reviewed_scene()
    reworked_to_iteration_two(scene)

    error = refused(approve, scene, 2, REVIEW_ID)

    assert error.code == "REVIEW_NOT_CURRENT"
    nothing_happened(scene)


def test_inputs_drifting_before_the_create_refuse_with_zero_writes():
    scene = reviewed_scene()

    def drift_while_reading_the_clock() -> datetime:
        root_edited_after_review(scene)
        return fixed_clock()

    error = refused(approve, scene, clock=drift_while_reading_the_clock)

    assert error.code == "INPUTS_STALE"
    assert scene.tsa.mutations == []


@pytest.mark.parametrize(
    "drift",
    [
        ("requirement", root_edited_after_review),
        ("applicable-ux", None),
    ],
    ids=["not-applicable-requirement", "applicable-ux"],
)
def test_row_34_approval_then_drift_is_historical_never_current(drift):
    name, change = drift
    scene = reviewed_scene(ux=APPLICABLE if name == "applicable-ux" else NOT_APPLICABLE)
    approve(scene)
    stored = scene.tsa.content_of(DECISION_ID)
    if change is None:
        scene.tsa.set_content(UX_DOCUMENT_ID, "# Checkout flow\n\nTwo screens now.\n")
    else:
        change(scene)
    reset_trace(scene)

    error = refused(approve, scene)

    assert error.code == "INPUTS_STALE", "target resolution outranks idempotency"
    with pytest.raises(RecoveryRefused) as recovering:
        recover(scene)
    assert recovering.value.code == "INPUTS_STALE"
    nothing_happened(scene)
    assert scene.tsa.content_of(DECISION_ID) == stored, "kept as history"
    validate_artifact(payload_of(scene, DECISION_ID))


# --------------------------------------------------------------------------
# G. Unknown outcomes (14.1, 14.4.1 window F)
# --------------------------------------------------------------------------


def test_an_unknown_create_that_did_not_land_is_retried_once_at_the_same_id():
    scene = reviewed_scene()
    scene.tsa.before(CREATE, 1, fail(DOWN))

    result = approve(scene)

    assert result.outcome is DecisionResultCode.ARCHITECTURE_APPROVED
    assert scene.tsa.log.count((CREATE, DECISION_ID)) == 2
    only_the_decision_written(scene)


def test_a_create_that_never_lands_is_a_write_failure_without_a_new_id():
    scene = reviewed_scene()
    scene.tsa.before(CREATE, 1, fail(DOWN))
    scene.tsa.before(CREATE, 2, fail(DOWN))

    error = refused(approve, scene)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert scene.tsa.log.count((CREATE, DECISION_ID)) == 2
    assert scene.tsa.mutations == []


def test_an_unknown_create_that_landed_empty_is_an_unrecoverable_shell():
    scene = reviewed_scene()
    scene.tsa.after(CREATE, 1, fail(DOWN))

    error = refused(approve, scene)

    assert error.code == "DECISION_SHELL_UNRECOVERABLE"
    assert scene.tsa.mutations == [f"create:{DECISION_ID}"]
    assert scene.tsa.content_of(DECISION_ID) == ""


def test_an_unknown_create_beside_an_equivalent_durable_decision_adopts_it():
    scene = reviewed_scene()
    other = reviewed_scene()
    approve(other, clock=lambda: datetime(2026, 10, 1, tzinfo=UTC))
    landed = other.tsa.content_of(DECISION_ID)

    def someone_else_landed() -> None:
        scene.tsa.seed_child(DECISION_ID, ARCHITECTURE_ID, landed)
        raise FiberyError(DOWN)

    scene.tsa.before(CREATE, 1, someone_else_landed)

    result = approve(scene)

    assert result.outcome is DecisionResultCode.DECISION_ALREADY_RECORDED
    assert result.recorded_at == "2026-10-01T00:00:00Z"
    assert scene.tsa.content_of(DECISION_ID) == landed
    assert scene.tsa.count(WRITE) == 0


def test_an_unknown_write_that_landed_is_confirmed_by_read_back():
    scene = reviewed_scene()
    scene.tsa.after(WRITE, 1, fail(DOWN))

    result = approve(scene)

    assert result.outcome is DecisionResultCode.ARCHITECTURE_APPROVED
    assert scene.tsa.count(WRITE) == 1, "never blindly rewritten"
    only_the_decision_written(scene)


def test_an_unknown_write_that_did_not_land_leaves_an_unrecoverable_shell():
    scene = reviewed_scene()
    scene.tsa.before(WRITE, 1, fail(DOWN))

    error = refused(approve, scene)

    assert error.code == "DECISION_SHELL_UNRECOVERABLE"
    assert scene.tsa.count(WRITE) == 1, "no retry write"
    assert scene.tsa.content_of(DECISION_ID) == ""


@pytest.mark.parametrize(
    ("landed", "code"),
    [
        ("APPROVE", DecisionResultCode.DECISION_ALREADY_RECORDED),
        ("REWORK", DecisionResultCode.DECISION_CONFLICT),
    ],
)
def test_a_write_that_stored_another_valid_decision_is_compared_never_rewritten(
    landed, code
):
    scene = reviewed_scene()
    record = decided(scene, landed)
    record["body"]["reason"] = "Written by someone else."
    other = carrier(DECISION_ID, sealed_artifact(record))
    scene.tsa.store_as = lambda markdown: other

    if code is DecisionResultCode.DECISION_CONFLICT:
        assert refused(approve, scene).code == code
    else:
        result = approve(scene)
        assert result.outcome is code
        assert result.recorded_at == record["body"]["recorded_at"]
    assert scene.tsa.content_of(DECISION_ID) == other
    assert scene.tsa.count(WRITE) == 1


def test_a_lost_read_back_is_a_read_failure_and_a_retry_adopts_the_decision():
    scene = reviewed_scene()
    clock = TickingClock()

    def reads_go_down() -> None:
        scene.tsa.failures[READ] = FiberyError(DOWN)

    scene.tsa.after(WRITE, 1, reads_go_down)

    error = refused(approve, scene, clock=clock)

    assert error.code == "FIBERY_READ_FAILED"
    del scene.tsa.failures[READ]
    reset_trace(scene)
    again = approve(scene, clock=clock)
    assert again.outcome is DecisionResultCode.DECISION_ALREADY_RECORDED
    assert again.recorded_at == FIRST_RECORDED_AT and clock.reads == 1
    nothing_happened(scene)


def test_after_an_unknown_write_stale_inputs_win_before_any_adoption():
    scene = reviewed_scene()

    def drift_then_fail() -> None:
        root_edited_after_review(scene)
        fail(DOWN)()

    scene.tsa.after(WRITE, 1, drift_then_fail)

    error = refused(approve, scene)

    assert error.code == "INPUTS_STALE"
    validate_artifact(payload_of(scene, DECISION_ID))  # durable, but not current
    reset_trace(scene)
    assert refused(approve, scene).code == "INPUTS_STALE"


def test_a_shell_filled_by_someone_else_after_the_create_is_not_written_over():
    scene = reviewed_scene()
    record = decided(scene, "REWORK")
    other = carrier(DECISION_ID, record)
    scene.tsa.after(CREATE, 1, lambda: scene.tsa.set_content(DECISION_ID, other))

    error = refused(approve, scene)

    assert error.code == "DECISION_CONFLICT"
    assert scene.tsa.count(WRITE) == 0
    assert scene.tsa.content_of(DECISION_ID) == other


# --------------------------------------------------------------------------
# H. After a known create, before the body write (contract 10, 14.2)
# --------------------------------------------------------------------------


def moved_to_another_parent(scene) -> None:
    scene.tsa.documents[DECISION_ID].parent_document_id = "another-parent"


def architecture_emptied(scene) -> None:
    scene.tsa.set_content(ARCHITECTURE_ID, "")


def applicable_ux_edited(scene) -> None:
    scene.tsa.set_content(UX_DOCUMENT_ID, "# Checkout flow\n\nTwo screens now.\n")


AFTER_CREATE = {
    "requirement": (NOT_APPLICABLE, root_edited_after_review, {"INPUTS_STALE"}),
    "requirement-child": (NOT_APPLICABLE, child_added_after_review, {"INPUTS_STALE"}),
    "applicable-ux": (APPLICABLE, applicable_ux_edited, {"INPUTS_STALE"}),
    "review-replaced": (NOT_APPLICABLE, review_resealed, {"REVIEW_NOT_CURRENT"}),
    "process-replaced": (
        NOT_APPLICABLE,
        lambda scene: scene.tsa.set_content(PROCESS_ID, other_process_carrier()),
        {"ARTIFACT_MALFORMED"},
    ),
    "architecture-changed": (
        NOT_APPLICABLE,
        lambda scene: scene.tsa.set_content(
            ARCHITECTURE_ID, other_architecture(scene, "Edited.").text
        ),
        {"ARCHITECTURE_DIVERGED"},
    ),
    "architecture-emptied": (
        NOT_APPLICABLE,
        architecture_emptied,
        {"ARCHITECTURE_DIVERGED"},
    ),
    "manifest-resealed": (NOT_APPLICABLE, manifest_resealed, {"ARTIFACT_MALFORMED"}),
    "manifest-acceptance": (
        NOT_APPLICABLE,
        acceptance_bound_elsewhere,
        {"MANIFEST_ACCEPTANCE_MISMATCH"},
    ),
    "shell-moved": (NOT_APPLICABLE, moved_to_another_parent, {"CYCLE_FOREIGN_PROJECT"}),
}


@pytest.mark.parametrize("drift", list(AFTER_CREATE))
@pytest.mark.parametrize("action", [approve, rework], ids=["approve", "rework"])
def test_drift_after_a_known_create_is_refused_before_the_body_write(
    drift, action, recovery_only_after_a_new_rework
):
    ux, change, codes = AFTER_CREATE[drift]
    scene = reviewed_scene(ux=ux)

    def drift_after_the_create() -> None:
        change(scene)
        scene.req.mutations.clear()  # the drift itself; I11 must add none

    scene.tsa.after(CREATE, 1, drift_after_the_create)
    clock = TickingClock()

    error = refused(
        action,
        scene,
        clock=clock,
        **(
            {"architect": RecordingModel(scene), "reviewer": CoveringReviewer(scene, 2)}
            if action is rework
            else {}
        ),
    )

    assert error.code in codes
    assert body_writes(scene) == 0, "no Decision is written against a changed tuple"
    assert scene.tsa.content_of(DECISION_ID) == "", "the shell stays empty"
    assert scene.tsa.mutations == [f"create:{DECISION_ID}"]
    assert scene.req.mutations == []
    assert models_called(scene) == 0
    assert recovery_only_after_a_new_rework == []
    assert clock.reads == 1, "one timestamp per attempt, never regenerated"
    assert f"{DECISION_ID!r} was created and remains an empty shell" in str(error)
    assert "its body was not written and nothing was rolled back" in str(error)
    assert "othing was written" not in str(error)


def test_requirement_drift_after_create_under_not_applicable_reads_no_ux_document():
    scene = reviewed_scene()
    scene.tsa.after(CREATE, 1, lambda: root_edited_after_review(scene))

    error = refused(approve, scene)

    assert error.code == "INPUTS_STALE"
    assert ux_reads(scene) == []
    assert body_writes(scene) == 0


def test_the_last_calls_before_the_body_write_are_the_placement_pair():
    scene = reviewed_scene()

    approve(scene)

    secret = secret_of(scene, DECISION_ID)
    write = scene.tsa.log.index((WRITE, secret))
    last_read = max(
        index for index, (call, _) in enumerate(scene.tsa.log[:write]) if call == READ
    )
    assert scene.tsa.log[last_read + 1 : write] == [
        ("resolve_placement", DECISION_ID),
        ("resolve_placement", ARCHITECTURE_ID),
    ]
    create = scene.tsa.log.index((CREATE, DECISION_ID))
    assert (READ, secret) in scene.tsa.log[create:write], (
        "the shell is read again, inside the full gate, after the create"
    )


def test_a_shell_that_vanished_after_the_create_is_a_write_failure_stated_truly():
    scene = reviewed_scene()
    scene.tsa.after(CREATE, 1, lambda: scene.tsa.documents.pop(DECISION_ID))

    error = refused(approve, scene)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert "Nothing was written" not in str(error)
    assert "create returned" in str(error)
    assert scene.tsa.count(WRITE) == 0


# --------------------------------------------------------------------------
# I. One definition of an open material product question (10.2, 7.4)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("outcome", "severity", "is_open"),
    [
        ("UNRESOLVED", None, True),
        ("CONFIRMED", "INFO", True),
        ("CONFIRMED", "BLOCKING", True),
        ("REJECTED", None, False),
    ],
)
def test_status_and_waivability_agree_on_an_open_material_question(
    outcome, severity, is_open
):
    scene = question_scene(outcome, severity)
    question = process_ref(scene, "product_questions")

    assert (status_of(scene) == "REVIEW_BLOCKED_ON_WHAT") is is_open
    if is_open:
        assert refused(approve, scene).code == "REVIEW_BLOCKED_ON_WHAT"
        error = refused(rework, scene, accept=accept(question))
        assert error.code == "DISPOSITION_NOT_WAIVABLE"
        nothing_happened(scene)
    else:
        result = approve(scene, accept=accept(question))
        assert result.outcome is DecisionResultCode.ARCHITECTURE_APPROVED


def test_the_shared_helper_is_the_one_status_derivation_uses():
    scene = question_scene("UNRESOLVED")
    process = validate_artifact(payload_of(scene, PROCESS_ID))
    review = validate_artifact(payload_of(scene, REVIEW_ID))

    refs = open_material_question_refs(review.body["reviewer_response"], process)

    assert refs == {process_ref(scene, "product_questions")}
    assert tsa_decision.open_material_question_refs is open_material_question_refs


# --------------------------------------------------------------------------
# J. Confirmed approval policy, pinned
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("findings", "status"),
    [
        ([], "REVIEW_PASS"),
        ([finding("WARNING")], "REVIEW_NEEDS_WORK"),
        ([finding("BLOCKING"), finding("WARNING")], "REVIEW_BLOCKING"),
    ],
)
def test_approval_needs_no_disposition_for_any_technical_status(findings, status):
    scene = reviewed_scene(new_findings=findings)
    assert status_of(scene) == status

    result = approve(scene)

    assert result.outcome is DecisionResultCode.ARCHITECTURE_APPROVED
    only_the_decision_written(scene)


# --------------------------------------------------------------------------
# K. Refusal messages stay truthful about what this call already wrote
# --------------------------------------------------------------------------


def test_a_refusal_after_the_body_write_acknowledges_the_durable_write():
    scene = reviewed_scene()
    scene.tsa.after(WRITE, 1, lambda: architecture_emptied(scene))

    error = refused(approve, scene)

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert body_writes(scene) == 1
    assert decision_payload(scene)["body"]["decision"] == "APPROVE", (
        "the written Decision stays durable"
    )
    message = str(error)
    assert message.startswith("The Decision body was written; it is neither ")
    assert "neither repeated nor rolled back" in message
    assert "no success is reported" in message
    assert "is empty although an accepted Manifest exists" in message, (
        "the gate's own diagnosis is kept"
    )
    assert "othing was written" not in message
    assert models_called(scene) == 0


def test_an_unknown_body_write_refusal_does_not_claim_the_write_landed_or_not():
    scene = reviewed_scene()

    def empty_then_fail() -> None:
        architecture_emptied(scene)
        fail(DOWN)()

    scene.tsa.after(WRITE, 1, empty_then_fail)

    error = refused(approve, scene)

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert str(error).startswith("The Decision body write outcome was unknown")
    assert "othing was written" not in str(error)
    assert body_writes(scene) == 1


def test_before_any_mutation_the_gate_message_is_kept_as_it_is():
    scene = reviewed_scene()
    architecture_emptied(scene)
    reset_trace(scene)

    error = refused(approve, scene)

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert str(error).endswith("Nothing was written.")
    assert "was created" not in str(error)
    nothing_happened(scene)
