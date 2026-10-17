"""I10 — the normal recovery gate, cases 1-10, and stage orchestration.

Every scene is a real cycle in durable state D: the I04 bootstrap carrier, a
Requirement the frozen chain applied, the real I05 Manifest, and outputs the
real I07 and I08 stages wrote. A Human Decision, which no implemented stage
writes yet (I11), is sealed through I01 and bound to the real Review. Only
Fibery and the models are fakes, so every claim here is D-class: no live
freshness reliance (gate I-2), no live write size (gate I-3).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from architect_fake import (
    RecordingModel,
    architecture_writes,
    payload_of,
    process_id,
    resealed_carrier,
    reset_trace,
)
from architecture_fake import fibery_stored
from recovery_fake import (
    CoveringReviewer,
    carrier,
    decide,
    decided,
    no_model,
    recover,
    reviewed_scene,
)
from reviewer_fake import (
    accepted_scene,
    applied_scene,
    decision_id,
    finding,
    review_id,
    review_writes,
    writes_other_than_review,
)
from sdlc import tsa_recovery
from sdlc.model_runtime import ModelRuntimeError
from sdlc.tsa_architect import (
    ArchitectCase,
    ArchitectRefused,
    ArchitectStageOutcome,
    read_cycle_state,
    run_architect_stage,
)
from sdlc.tsa_artifacts import sealed_artifact, validate_artifact
from sdlc.tsa_recovery import (
    RecoveryBoundary,
    RecoveryCase,
    RecoveryRefused,
    classify_recovery_case,
    message_after_progress,
)
from sdlc.tsa_reviewer import (
    ArchitectStageRequired,
    ReviewerRefused,
    ReviewerStageOutcome,
    run_reviewer_stage,
)
from test_tsa_admission import (
    APPLICABLE,
    ARCHITECTURE_ID,
    CYCLE,
    MANIFEST_ID,
    NOT_APPLICABLE,
    PROJECT_ID,
    UX_DOCUMENT_ID,
    bootstrap_carrier,
    child_added_after_review,
    fail,
    root_edited_after_review,
)
from test_tsa_architect import (
    FIBERY_DOWN,
    accepted_by_i01,
    architecture_envelope,
    other_architecture,
    other_process_carrier,
    persisted_but_not_applied,
    reseal,
    stored_table_response,
)
from test_tsa_cycle import fixed_clock
from test_tsa_reviewer import is_review_carrier

PROCESS_ID = process_id(1)
REVIEW_ID = review_id(1)
DECISION_ID = decision_id(1)
CREATE = "create_tsa_child_document"
WRITE = "write_document_content"


def refusal(scene, architect=None, reviewer=None) -> RecoveryRefused:
    with pytest.raises(RecoveryRefused) as caught:
        recover(scene, architect, reviewer)
    return caught.value


def models(scene, iteration: int = 1) -> tuple[RecordingModel, CoveringReviewer]:
    return RecordingModel(scene), CoveringReviewer(scene, iteration)


def nothing_happened(scene, *runtimes: RecordingModel) -> None:
    """The gate failure rule: no mutation and no model call (contract 14.1)."""
    assert scene.tsa.mutations == []
    assert scene.req.mutations == []
    for runtime in runtimes:
        assert runtime.calls == []


def contents(scene) -> dict[str, str]:
    return {
        document_id: scene.tsa.content_of(document_id)
        for document_id in scene.tsa.documents
    }


def seed_shell(scene, document_id: str) -> None:
    scene.tsa.seed_child(document_id, ARCHITECTURE_ID, "")
    reset_trace(scene)


def case_four(scene, divergent) -> tuple[str, ...]:
    """The three fingerprints of case 4, read before the Architecture changes."""
    return (
        f"input {payload_of(scene, PROCESS_ID)['body']['input_fingerprint']}",
        f"output {architecture_envelope(scene)['body']['content_fingerprint']}",
        f"current {divergent.content_fingerprint}",
    )


def ux_reads(scene) -> list[tuple[str, str]]:
    return [entry for entry in scene.tsa.log if entry[1] == UX_DOCUMENT_ID]


# --------------------------------------------------------------------------
# A. Case 1: Draft -> Architect -> Reviewer -> Human Decision boundary
# --------------------------------------------------------------------------


def test_case_1_runs_one_architect_then_one_reviewer_to_the_boundary():
    scene = accepted_scene()
    architect, reviewer = models(scene)

    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert result.case is RecoveryCase.REVIEW_RECORDED
    assert (len(architect.calls), len(reviewer.calls)) == (1, 1)
    assert scene.tsa.count(CREATE) == 2, "one Process, one Review"
    assert scene.tsa.count(WRITE) == 3, "Process, Architecture, Review"
    assert result.architect.outcome is ArchitectStageOutcome.OUTPUT_APPLIED
    assert result.reviewer.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert DECISION_ID not in scene.tsa.documents, "no Decision is written"


def test_the_boundary_names_the_exact_durable_target_for_a_decision():
    scene = accepted_scene()

    result = recover(scene, *models(scene))

    process = payload_of(scene, PROCESS_ID)
    review = payload_of(scene, REVIEW_ID)
    assert result.iteration == 1
    assert result.architecture_document_id == ARCHITECTURE_ID
    assert result.architecture_fingerprint == review["body"]["architecture_fingerprint"]
    assert (result.process_result_document_id, result.process_result_digest) == (
        PROCESS_ID,
        process["artifact_digest"],
    )
    assert (result.review_result_document_id, result.review_result_digest) == (
        REVIEW_ID,
        review["artifact_digest"],
    )
    assert result.derived_review_status == review["body"]["derived_status"]
    assert result.human_decision_document_id == DECISION_ID
    assert result.human_decision_digest is None


def test_case_1_model_failure_advances_nothing_and_is_not_retried():
    scene = accepted_scene()
    architect = RecordingModel(scene, error=ModelRuntimeError("CLI timed out"))
    reviewer = CoveringReviewer(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "MODEL_RUNTIME_FAILED"
    nothing_happened(scene, reviewer)
    assert len(architect.calls) == 1, "no automatic second call"
    assert PROCESS_ID not in scene.tsa.documents


def test_an_explicit_later_invocation_may_try_again_from_durable_state():
    scene = accepted_scene()
    refusal(scene, RecordingModel(scene, error=ModelRuntimeError("down")))
    reset_trace(scene)
    architect, reviewer = models(scene)

    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert (len(architect.calls), len(reviewer.calls)) == (1, 1)


# --------------------------------------------------------------------------
# B-D. Cases 2 and 3, and output == input (13.7-3)
# --------------------------------------------------------------------------


def test_case_2_applies_the_recorded_output_without_an_architect_call():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    reviewer = CoveringReviewer(scene)

    result = recover(scene, no_model(scene), reviewer)

    assert result.architect.outcome is ArchitectStageOutcome.RECORDED_OUTPUT_APPLIED
    assert scene.tsa.log.count((WRITE, scene.tsa.documents[ARCHITECTURE_ID].secret))
    assert scene.tsa.count(CREATE) == 1, "the Review only; no second Process"
    assert len(reviewer.calls) == 1
    assert result.boundary is RecoveryBoundary.HUMAN_DECISION


def test_case_3_reviews_without_architect_call_or_architecture_write():
    scene = applied_scene()
    architecture = scene.tsa.content_of(ARCHITECTURE_ID)
    reviewer = CoveringReviewer(scene)

    result = recover(scene, no_model(scene), reviewer)

    assert result.architect is None
    assert len(reviewer.calls) == 1
    assert scene.tsa.content_of(ARCHITECTURE_ID) == architecture
    assert writes_other_than_review(scene) == []
    assert result.boundary is RecoveryBoundary.HUMAN_DECISION


def test_when_output_equals_input_case_3_wins_and_nothing_is_reapplied():
    scene = applied_scene()
    output = architecture_envelope(scene)["body"]["content_fingerprint"]
    reseal(scene, PROCESS_ID, lambda p: p["body"].update(input_fingerprint=output))
    reset_trace(scene)
    reviewer = CoveringReviewer(scene)

    result = recover(scene, no_model(scene), reviewer)

    assert result.architect is None, "no apply, no Architect stage"
    assert scene.tsa.count(WRITE) == 1, "the Review body only"
    assert len(reviewer.calls) == 1


# --------------------------------------------------------------------------
# E, T. Case 4, with and without a Review
# --------------------------------------------------------------------------


def test_case_4_reports_all_three_fingerprints_and_does_nothing():
    scene = applied_scene()
    divergent = other_architecture(scene, "Edited by hand after the apply.")
    expected = case_four(scene, divergent)
    scene.tsa.set_content(ARCHITECTURE_ID, divergent.text)
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert error.details == expected
    nothing_happened(scene, architect, reviewer)


def test_a_valid_review_does_not_make_a_divergent_architecture_current():
    scene = reviewed_scene()
    divergent = other_architecture(scene, "Edited by hand after the review.")
    expected = case_four(scene, divergent)
    scene.tsa.set_content(ARCHITECTURE_ID, divergent.text)

    error = refusal(scene)

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert error.details == expected
    nothing_happened(scene)


def test_a_review_beside_an_architecture_reverted_to_its_input_is_malformed():
    """I07's own rule, unchanged: a Review of an output the Architecture lacks."""
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    bootstrap = scene.tsa.content_of(ARCHITECTURE_ID)
    recover(scene, no_model(scene), CoveringReviewer(scene))
    scene.tsa.set_content(ARCHITECTURE_ID, bootstrap)
    reset_trace(scene)

    error = refusal(scene)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene)


def test_case_1_refuses_an_architecture_that_is_not_its_input():
    scene = accepted_scene()
    divergent = other_architecture(scene, "Applied with no Process Result.")
    scene.tsa.set_content(ARCHITECTURE_ID, divergent.text)
    architect = RecordingModel(scene)

    error = refusal(scene, architect)

    assert error.code == "ARCHITECTURE_DIVERGED"
    nothing_happened(scene, architect)


# --------------------------------------------------------------------------
# F-H. Case 7: empty shells, by artifact type (13.7-7)
# --------------------------------------------------------------------------


def test_an_empty_process_shell_is_completed_in_place_by_one_architect_call():
    scene = accepted_scene()
    seed_shell(scene, PROCESS_ID)
    architect, reviewer = models(scene)

    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert len(architect.calls) == 1
    assert f"create:{PROCESS_ID}" not in scene.tsa.mutations, "the same shell"
    assert scene.tsa.count(CREATE) == 1, "the Review only"
    validate_artifact(payload_of(scene, PROCESS_ID))


def test_an_empty_review_shell_is_completed_in_place_by_one_reviewer_call():
    scene = applied_scene()
    seed_shell(scene, REVIEW_ID)
    reviewer = CoveringReviewer(scene)

    result = recover(scene, no_model(scene), reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert result.architect is None
    assert len(reviewer.calls) == 1
    assert scene.tsa.count(CREATE) == 0
    assert review_writes(scene) == 1
    assert writes_other_than_review(scene) == [], "no Architecture write"
    assert result.review_result_document_id == REVIEW_ID


def test_an_empty_decision_shell_is_unrecoverable_and_left_alone():
    scene = reviewed_scene()
    seed_shell(scene, DECISION_ID)
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "DECISION_SHELL_UNRECOVERABLE"
    nothing_happened(scene, architect, reviewer)
    assert scene.tsa.content_of(DECISION_ID) == ""


def test_an_empty_input_manifest_is_not_normal_recovery():
    scene = accepted_scene()
    scene.tsa.set_content(MANIFEST_ID, "")
    reset_trace(scene)
    architect = RecordingModel(scene)

    error = refusal(scene, architect)

    assert error.code == "MANIFEST_SHELL_UNRECOVERABLE"
    nothing_happened(scene, architect)


def test_an_empty_architecture_is_not_normal_recovery():
    scene = accepted_scene()
    scene.tsa.set_content(ARCHITECTURE_ID, "")
    reset_trace(scene)
    architect = RecordingModel(scene)

    error = refusal(scene, architect)

    assert error.code == "ARCHITECTURE_DIVERGED", "I07's refusal, nothing written"
    nothing_happened(scene, architect)


def test_an_empty_document_named_like_an_artifact_decides_nothing():
    scene = applied_scene()
    scene.tsa.seed_child("named-only", ARCHITECTURE_ID, "")
    reset_trace(scene)

    result = recover(scene, no_model(scene), CoveringReviewer(scene))

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION


# --------------------------------------------------------------------------
# Case 2 beside an empty Review shell: replay, fresh gate, then the shell
# --------------------------------------------------------------------------


def pending_beside_review_shell(ux=NOT_APPLICABLE):
    """A durable Process, the Architecture at its input, an empty Review."""
    scene = accepted_scene(ux=ux)
    persisted_but_not_applied(scene)
    seed_shell(scene, REVIEW_ID)
    return scene


def gate_passes(monkeypatch) -> list[str]:
    """Each full recovery gate pass, counted where I10 runs it."""
    passes = []
    real = tsa_recovery.read_cycle_state

    def counted(*args, **kwargs):
        passes.append("gate")
        return real(*args, **kwargs)

    monkeypatch.setattr(tsa_recovery, "read_cycle_state", counted)
    return passes


def boundary_of(result) -> tuple:
    return (
        result.boundary,
        result.case,
        result.iteration,
        result.architecture_document_id,
        result.architecture_fingerprint,
        result.process_result_document_id,
        result.process_result_digest,
        result.review_result_document_id,
        result.review_result_digest,
        result.derived_review_status,
        result.human_decision_document_id,
        result.human_decision_digest,
    )


def without_shell():
    """The same pending output with no Review slot at all, recovered."""
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    return scene, recover(scene, no_model(scene), CoveringReviewer(scene))


def test_a_review_shell_beside_a_pending_output_is_replayed_then_completed(
    monkeypatch,
):
    scene = pending_beside_review_shell()
    process = scene.tsa.content_of(PROCESS_ID)
    manifest = scene.tsa.content_of(MANIFEST_ID)
    shell_secret = scene.tsa.documents[REVIEW_ID].secret
    passes = gate_passes(monkeypatch)
    architect, reviewer = no_model(scene), CoveringReviewer(scene)

    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert result.case is RecoveryCase.REVIEW_RECORDED
    assert passes == ["gate"] * 3, "replay, fresh gate and shell, fresh gate"
    assert (len(architect.calls), len(reviewer.calls)) == (0, 1)
    assert result.architect.outcome is ArchitectStageOutcome.RECORDED_OUTPUT_APPLIED
    assert result.architect.model_invoked is False
    assert result.reviewer.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert architecture_writes(scene) == 1
    assert review_writes(scene) == 1
    assert scene.tsa.count(WRITE) == 2, "no Process and no Decision write"
    assert scene.tsa.count(CREATE) == 0, "the shell is completed, not recreated"
    assert scene.tsa.documents[REVIEW_ID].secret == shell_secret
    assert DECISION_ID not in scene.tsa.documents
    assert scene.tsa.content_of(PROCESS_ID) == process
    assert scene.tsa.content_of(MANIFEST_ID) == manifest
    review = validate_artifact(payload_of(scene, REVIEW_ID))
    assert review.body["process_result_digest"] == result.process_result_digest
    assert result.review_result_document_id == REVIEW_ID
    twin, expected = without_shell()
    assert scene.tsa.content_of(ARCHITECTURE_ID) == twin.tsa.content_of(
        ARCHITECTURE_ID
    ), "exactly the recorded output"
    assert boundary_of(result) == boundary_of(expected)


def test_without_a_review_slot_the_replay_is_followed_by_a_review_create():
    scene, result = without_shell()

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert architecture_writes(scene) == 1
    assert scene.tsa.count(CREATE) == 1, "the Review only"


def test_the_architect_stage_alone_still_refuses_a_review_shell_before_apply():
    """Only recovery's replay opts out; I07's default classification stands."""
    scene = pending_beside_review_shell()

    with pytest.raises(ArchitectRefused) as stage:
        run_architect_stage(scene.tsa, scene.req, no_model(scene), PROJECT_ID, CYCLE)

    assert stage.value.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene)
    assert scene.tsa.content_of(REVIEW_ID) == ""


def test_a_review_shell_does_not_hide_a_divergent_architecture():
    scene = pending_beside_review_shell()
    divergent = other_architecture(scene, "Edited by hand before the apply.")
    scene.tsa.set_content(ARCHITECTURE_ID, divergent.text)
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert error.details[-1] == f"current {divergent.content_fingerprint}"
    nothing_happened(scene, architect, reviewer)


def test_a_non_empty_malformed_review_beside_a_pending_output_blocks_replay():
    scene = pending_beside_review_shell()
    scene.tsa.set_content(REVIEW_ID, "A note someone left here.\n")
    reset_trace(scene)
    before = contents(scene)
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene, architect, reviewer)
    assert contents(scene) == before


def test_stale_inputs_block_replay_beside_a_review_shell():
    scene = pending_beside_review_shell()
    root_edited_after_review(scene)
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "INPUTS_STALE"
    nothing_happened(scene, architect, reviewer)


def test_a_duplicate_review_blocks_replay_beside_a_review_shell():
    twin, _ = without_shell()
    scene = pending_beside_review_shell()
    scene.tsa.seed_child(
        "rogue-review", ARCHITECTURE_ID, twin.tsa.content_of(REVIEW_ID)
    )
    reset_trace(scene)
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "ARTIFACT_DUPLICATE"
    assert error.details == ("rogue-review",)
    nothing_happened(scene, architect, reviewer)


def ux_edited(scene) -> None:
    scene.tsa.set_content(UX_DOCUMENT_ID, "# Checkout flow\n\nTwo screens now.\n")


def process_replaced(scene) -> None:
    reseal(
        scene, PROCESS_ID, lambda p: p["body"].update(created_at="2027-01-02T03:04:05Z")
    )


def review_shell_scribbled(scene) -> None:
    scene.tsa.set_content(REVIEW_ID, "A note someone left here.\n")


#: Durable change right after the replay lands, before the next gate pass.
AFTER_REPLAY = {
    "requirement": (NOT_APPLICABLE, root_edited_after_review, "INPUTS_STALE"),
    "applicable-ux": (APPLICABLE, ux_edited, "INPUTS_STALE"),
    "process-replaced": (NOT_APPLICABLE, process_replaced, "FIBERY_WRITE_FAILED"),
    "review-malformed": (NOT_APPLICABLE, review_shell_scribbled, "ARTIFACT_MALFORMED"),
}


@pytest.mark.parametrize("drift", AFTER_REPLAY)
def test_the_gate_runs_fresh_after_the_replay_before_any_reviewer_call(drift):
    ux, change, code = AFTER_REPLAY[drift]
    scene = pending_beside_review_shell(ux=ux)
    scene.tsa.after(WRITE, 1, lambda: change(scene))
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == code
    assert (len(architect.calls), len(reviewer.calls)) == (0, 0)
    assert architecture_writes(scene) == 1, "the replay landed, nothing more"
    assert review_writes(scene) == 0


def test_a_landed_replay_with_a_lost_response_moves_on_to_the_shell():
    scene = pending_beside_review_shell()
    scene.tsa.after(WRITE, 1, fail(FIBERY_DOWN))
    architect, reviewer = no_model(scene), CoveringReviewer(scene)

    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert architecture_writes(scene) == 1, "confirmed from durable state"
    assert (len(architect.calls), len(reviewer.calls)) == (0, 1)
    assert review_writes(scene) == 1
    assert scene.tsa.count(CREATE) == 0


def test_a_replay_that_never_landed_is_not_retried_and_calls_no_model():
    scene = pending_beside_review_shell()
    scene.tsa.before(WRITE, 1, fail(FIBERY_DOWN))
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)
    assert error.code == "FIBERY_WRITE_FAILED"
    assert architecture_writes(scene) == 1, "attempted once"
    assert (len(architect.calls), len(reviewer.calls)) == (0, 0)
    reset_trace(scene)
    reviewer = CoveringReviewer(scene)

    result = recover(scene, no_model(scene), reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert len(reviewer.calls) == 1
    assert scene.tsa.count(CREATE) == 0


def test_a_replay_finding_no_process_left_writes_nothing(monkeypatch):
    """The Process emptied between the gate and the replay: a later invocation."""
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    real = tsa_recovery.replay_recorded_output

    def process_emptied(*args):
        scene.tsa.set_content(PROCESS_ID, "")
        scene.tsa.mutations.clear()
        return real(*args)

    monkeypatch.setattr(tsa_recovery, "replay_recorded_output", process_emptied)
    architect, reviewer = models(scene)

    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.ARCHITECT_REQUIRED
    assert result.case is RecoveryCase.PROCESS_SHELL
    assert result.architect is None
    nothing_happened(scene, architect, reviewer)


def test_review_input_changed_after_the_replay_is_propagated_not_retried():
    scene = pending_beside_review_shell()
    architect = RecordingModel(scene)
    reviewer = CoveringReviewer(scene, during=lambda: process_replaced(scene))

    error = refusal(scene, architect, reviewer)

    assert error.code == "REVIEW_INPUT_CHANGED"
    assert (len(architect.calls), len(reviewer.calls)) == (0, 1)
    assert architecture_writes(scene) == 1
    assert review_writes(scene) == 0
    assert scene.tsa.content_of(REVIEW_ID) == ""


# --------------------------------------------------------------------------
# I. Case 8: a non-empty malformed artifact is refused, never repaired
# --------------------------------------------------------------------------


MALFORMED_SCENES = {
    "process": (applied_scene, PROCESS_ID),
    "review": (reviewed_scene, REVIEW_ID),
    "decision": (reviewed_scene, DECISION_ID),
}


@pytest.mark.parametrize("artifact", MALFORMED_SCENES)
def test_a_malformed_artifact_is_refused_and_left_as_it_is(artifact):
    build, document_id = MALFORMED_SCENES[artifact]
    scene = build()
    if document_id not in scene.tsa.documents:
        scene.tsa.seed_child(document_id, ARCHITECTURE_ID, "")
    scene.tsa.set_content(document_id, "A note someone left here.\n")
    reset_trace(scene)
    before = contents(scene)
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene, architect, reviewer)
    assert contents(scene) == before


# --------------------------------------------------------------------------
# J, Q. Uniqueness and conflicting decisions (rows 42)
# --------------------------------------------------------------------------


def test_row_42_a_duplicate_process_fails_the_gate_before_any_stage():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    scene.tsa.seed_child("rogue-process", ARCHITECTURE_ID, other_process_carrier())
    reset_trace(scene)
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "ARTIFACT_DUPLICATE"
    assert error.details == ("rogue-process",)
    nothing_happened(scene, architect, reviewer)


def test_row_42_a_duplicate_review_fails_the_gate_before_any_stage():
    scene = reviewed_scene()
    later = resealed_carrier(
        scene.tsa.content_of(REVIEW_ID),
        lambda p: p["body"].update(created_at="2027-01-02T03:04:05Z"),
    )
    scene.tsa.seed_child("rogue-review", ARCHITECTURE_ID, later)
    reset_trace(scene)

    error = refusal(scene)

    assert error.code == "ARTIFACT_DUPLICATE"
    assert error.details == ("rogue-review",)
    nothing_happened(scene)


def test_row_42_conflicting_decisions_fail_the_gate_before_any_action():
    """REWORK at the derived id; a valid APPROVE claims the same iteration."""
    scene = reviewed_scene()
    decide(scene, "REWORK")
    approve = decided(scene, "APPROVE")
    validate_artifact(approve)
    scene.tsa.seed_child("rogue-decision", ARCHITECTURE_ID, carrier("x", approve))
    reset_trace(scene)
    architect, reviewer = models(scene, iteration=2)

    error = refusal(scene, architect, reviewer)

    assert error.code == "ARTIFACT_DUPLICATE"
    assert error.details == ("rogue-decision",)
    nothing_happened(scene, architect, reviewer)
    assert process_id(2) not in scene.tsa.documents


def test_an_artifact_of_an_iteration_no_rework_opened_fails_the_gate():
    scene = applied_scene()
    content = resealed_carrier(
        scene.tsa.content_of(PROCESS_ID), lambda p: p.update(iteration=2)
    )
    scene.tsa.seed_child(process_id(2), ARCHITECTURE_ID, content)
    reset_trace(scene)

    error = refusal(scene)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene)


# --------------------------------------------------------------------------
# Rows 43 and 44: lineage on read
# --------------------------------------------------------------------------


def test_row_43_an_invalid_process_output_digest_blocks_replay():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    bootstrap = scene.tsa.content_of(ARCHITECTURE_ID)
    tampered = scene.tsa.content_of(PROCESS_ID).replace(
        "A runtime gate in front of every model call.",
        "A gate that also writes Tasks.",
    )
    assert tampered != scene.tsa.content_of(PROCESS_ID)
    scene.tsa.set_content(PROCESS_ID, tampered)
    reset_trace(scene)

    error = refusal(scene)

    assert error.code == "ARTIFACT_MALFORMED"
    assert "digest" in str(error)
    nothing_happened(scene)
    assert scene.tsa.content_of(ARCHITECTURE_ID) == bootstrap, "nothing replayed"


def test_row_43_a_resealed_process_bound_to_another_manifest_blocks_replay():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    reseal(scene, PROCESS_ID, lambda p: p["body"].update(manifest_digest="0" * 64))
    reset_trace(scene)

    error = refusal(scene)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene)


def test_row_44_a_review_bound_to_another_process_payload_fails_the_gate():
    scene = reviewed_scene()
    other = payload_of(scene, PROCESS_ID)["artifact_digest"]
    reseal(
        scene, PROCESS_ID, lambda p: p["body"].update(created_at="2027-01-02T03:04:05Z")
    )
    assert payload_of(scene, PROCESS_ID)["artifact_digest"] != other
    accepted_by_i01(scene, REVIEW_ID)
    reset_trace(scene)
    reviewer = CoveringReviewer(scene)

    error = refusal(scene, no_model(scene), reviewer)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene, reviewer)


def test_a_tampered_stored_review_status_fails_the_gate():
    scene = reviewed_scene()
    reseal(
        scene, REVIEW_ID, lambda p: p["body"].update(derived_status="REVIEW_BLOCKING")
    )
    reset_trace(scene)

    error = refusal(scene)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene)


# --------------------------------------------------------------------------
# K-M. Currentness (rows 41, 50; contract 4.4)
# --------------------------------------------------------------------------


def test_row_41_stale_inputs_block_replay_of_a_persisted_output():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    bootstrap = scene.tsa.content_of(ARCHITECTURE_ID)
    root_edited_after_review(scene)
    reviewer = CoveringReviewer(scene)

    error = refusal(scene, no_model(scene), reviewer)

    assert error.code == "INPUTS_STALE"
    nothing_happened(scene, reviewer)
    assert scene.tsa.content_of(ARCHITECTURE_ID) == bootstrap


@pytest.mark.parametrize(
    "build",
    [accepted_scene, applied_scene],
    ids=["before-architect", "before-reviewer"],
)
@pytest.mark.parametrize(
    "drift",
    [root_edited_after_review, child_added_after_review],
    ids=["root", "child"],
)
def test_stale_requirements_block_every_model_call(build, drift):
    scene = build()
    drift(scene)
    scene.req.mutations.clear()
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "INPUTS_STALE"
    nothing_happened(scene, architect, reviewer)


def test_stale_requirements_block_the_restored_human_boundary():
    scene = reviewed_scene()
    root_edited_after_review(scene)

    error = refusal(scene)

    assert error.code == "INPUTS_STALE"
    nothing_happened(scene)


def test_stale_requirements_block_completing_a_review_shell():
    scene = applied_scene()
    seed_shell(scene, REVIEW_ID)
    root_edited_after_review(scene)
    reviewer = CoveringReviewer(scene)

    error = refusal(scene, no_model(scene), reviewer)

    assert error.code == "INPUTS_STALE"
    nothing_happened(scene, reviewer)


def test_row_50_requirement_drift_under_not_applicable_reads_no_ux_document():
    scene = applied_scene()
    root_edited_after_review(scene)
    reviewer = CoveringReviewer(scene)

    error = refusal(scene, no_model(scene), reviewer)

    assert error.code == "INPUTS_STALE"
    assert ux_reads(scene) == []
    nothing_happened(scene, reviewer)


def test_not_applicable_reads_no_ux_document_across_a_whole_recovery():
    scene = accepted_scene()

    recover(scene, *models(scene))

    assert ux_reads(scene) == []


def test_applicable_ux_drift_blocks_recovery():
    scene = applied_scene(ux=APPLICABLE)
    scene.tsa.set_content(UX_DOCUMENT_ID, "# Checkout flow\n\nTwo screens now.\n")
    reviewer = CoveringReviewer(scene)

    error = refusal(scene, no_model(scene), reviewer)

    assert error.code == "INPUTS_STALE"
    nothing_happened(scene, reviewer)


def test_applicable_ux_unchanged_recovers_to_the_boundary():
    scene = applied_scene(ux=APPLICABLE)

    result = recover(scene, no_model(scene), CoveringReviewer(scene))

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert ux_reads(scene), "APPLICABLE currentness reads the UX Document"


# --------------------------------------------------------------------------
# N, row 11. Cases 5 and 10: the Human Decision boundary
# --------------------------------------------------------------------------


def test_case_5_restores_the_boundary_without_any_model_call():
    scene = reviewed_scene()
    architect, reviewer = models(scene)

    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert result.case is RecoveryCase.REVIEW_RECORDED
    assert (result.architect, result.reviewer) == (None, None)
    nothing_happened(scene, architect, reviewer)


def test_row_11_without_a_human_decision_nothing_advances_past_the_boundary():
    scene = reviewed_scene()
    before = contents(scene)

    results = [recover(scene) for _ in range(3)]

    assert len(set(results)) == 1, "case 10: the same evidence each time"
    assert results[0].iteration == 1
    assert DECISION_ID not in scene.tsa.documents
    assert process_id(2) not in scene.tsa.documents
    assert contents(scene) == before
    assert scene.tsa.mutations == []


def test_a_negative_review_is_still_the_boundary_and_not_re_reviewed():
    scene = reviewed_scene(new_findings=[finding("BLOCKING")])
    assert payload_of(scene, REVIEW_ID)["body"]["derived_status"] == "REVIEW_BLOCKING"
    reviewer = CoveringReviewer(scene)

    result = recover(scene, no_model(scene), reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert reviewer.calls == []


# --------------------------------------------------------------------------
# O, P. Case 6: a durable Human Decision is honoured, never written
# --------------------------------------------------------------------------


def test_case_6_approve_is_the_closed_cycle_with_no_write_or_model_call():
    scene = reviewed_scene()
    approve = decide(scene, "APPROVE")
    architect, reviewer = models(scene)

    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.APPROVED
    assert result.case is RecoveryCase.APPROVED
    assert result.human_decision_document_id == DECISION_ID
    assert result.human_decision_digest == approve["artifact_digest"]
    assert (
        result.review_result_digest == approve["body"]["target"]["review_result_digest"]
    )
    nothing_happened(scene, architect, reviewer)


def test_a_historical_approve_over_stale_inputs_is_not_current():
    scene = reviewed_scene()
    decide(scene, "APPROVE")
    root_edited_after_review(scene)

    error = refusal(scene)

    assert error.code == "INPUTS_STALE"
    nothing_happened(scene)
    validate_artifact(payload_of(scene, DECISION_ID))


def test_an_approve_that_binds_another_ux_record_is_not_honoured():
    scene = reviewed_scene()
    approve = decided(scene, "APPROVE")
    approve["body"]["ux_evidence_digest"] = "0" * 64
    approve = sealed_artifact(approve)
    validate_artifact(approve)
    scene.tsa.seed_child(DECISION_ID, ARCHITECTURE_ID, carrier("x", approve))
    reset_trace(scene)

    error = refusal(scene)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene)


def test_an_approved_cycle_stays_closed_after_its_architecture_diverged():
    scene = reviewed_scene()
    decide(scene, "APPROVE")
    divergent = other_architecture(scene, "Edited after the approval.")
    expected = case_four(scene, divergent)
    scene.tsa.set_content(ARCHITECTURE_ID, divergent.text)

    error = refusal(scene)

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert error.details == expected
    nothing_happened(scene)


def test_case_6_rework_opens_exactly_the_next_iteration_on_the_same_manifest():
    scene = reviewed_scene()
    manifest = scene.tsa.content_of(MANIFEST_ID)
    first = {d: scene.tsa.content_of(d) for d in (PROCESS_ID, REVIEW_ID)}
    decide(scene, "REWORK")
    architect, reviewer = models(scene, iteration=2)

    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert result.iteration == 2
    assert (len(architect.calls), len(reviewer.calls)) == (1, 1)
    assert result.process_result_document_id == process_id(2)
    assert result.review_result_document_id == review_id(2)
    assert result.human_decision_document_id == decision_id(2)
    assert scene.tsa.content_of(MANIFEST_ID) == manifest, "no scope rewrite"
    second = payload_of(scene, process_id(2))["body"]
    assert (
        second["manifest_digest"]
        == payload_of(scene, MANIFEST_ID)["body"]["manifest_digest"]
    )
    assert {d: scene.tsa.content_of(d) for d in first} == first, "history intact"
    assert process_id(3) not in scene.tsa.documents


# --------------------------------------------------------------------------
# Row 10 / case 9: an incomplete write is recovered from durable state
# --------------------------------------------------------------------------


#: (fault, first refusal, next case, Architect calls on retry, Reviewer calls)
INCOMPLETE_WRITES = {
    "process-body-lost": (
        accepted_scene,
        lambda s: s.tsa.before(WRITE, 1, fail(FIBERY_DOWN)),
        "FIBERY_WRITE_FAILED",
        1,
        1,
    ),
    "architecture-write-lost": (
        accepted_scene,
        lambda s: s.tsa.before(WRITE, 2, fail(FIBERY_DOWN)),
        "FIBERY_WRITE_FAILED",
        0,
        1,
    ),
    "review-body-lost": (
        applied_scene,
        lambda s: s.tsa.before(WRITE, 1, fail(FIBERY_DOWN)),
        "FIBERY_WRITE_FAILED",
        0,
        1,
    ),
    "process-create-never-durable": (
        accepted_scene,
        lambda s: (
            s.tsa.before(CREATE, 1, fail(FIBERY_DOWN)),
            s.tsa.before(CREATE, 2, fail(FIBERY_DOWN)),
        ),
        "FIBERY_WRITE_FAILED",
        1,
        1,
    ),
}


@pytest.mark.parametrize("window", INCOMPLETE_WRITES)
def test_row_10_an_incomplete_write_is_recovered_by_the_next_invocation(window):
    build, fault, code, architect_calls, reviewer_calls = INCOMPLETE_WRITES[window]
    scene = build()
    fault(scene)

    error = refusal(scene, RecordingModel(scene), CoveringReviewer(scene))
    assert error.code == code
    reset_trace(scene)
    architect, reviewer = models(scene)
    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert (len(architect.calls), len(reviewer.calls)) == (
        architect_calls,
        reviewer_calls,
    )
    validate_artifact(payload_of(scene, PROCESS_ID))
    validate_artifact(payload_of(scene, REVIEW_ID))
    children = [
        d for d in scene.tsa.documents if d not in (ARCHITECTURE_ID, UX_DOCUMENT_ID)
    ]
    assert sorted(children) == sorted([MANIFEST_ID, PROCESS_ID, REVIEW_ID])


def test_case_9_a_landed_write_with_a_lost_response_is_confirmed_not_redone():
    scene = accepted_scene()
    scene.tsa.after(WRITE, 2, fail(FIBERY_DOWN))
    architect, reviewer = models(scene)

    result = recover(scene, architect, reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert len(architect.calls) == 1
    assert scene.tsa.count(WRITE) == 3, "the landed apply is not repeated"


# --------------------------------------------------------------------------
# R, S. Delegated refusals propagate and are never retried in place
# --------------------------------------------------------------------------


def test_a_reviewer_runtime_failure_propagates_without_a_second_call():
    scene = applied_scene()
    reviewer = CoveringReviewer(scene, error=ModelRuntimeError("CLI timed out"))

    error = refusal(scene, no_model(scene), reviewer)

    assert error.code == "MODEL_RUNTIME_FAILED"
    assert len(reviewer.calls) == 1
    assert scene.tsa.mutations == []


def test_review_input_changed_propagates_and_is_not_rebound_in_place():
    scene = applied_scene()

    def replace_process() -> None:
        reseal(
            scene,
            PROCESS_ID,
            lambda p: p["body"].update(created_at="2027-01-02T03:04:05Z"),
        )

    reviewer = CoveringReviewer(scene, during=replace_process)
    architect = RecordingModel(scene)

    error = refusal(scene, architect, reviewer)

    assert error.code == "REVIEW_INPUT_CHANGED"
    assert error.details == (PROCESS_ID,)
    assert (len(architect.calls), len(reviewer.calls)) == (0, 1)
    assert scene.tsa.mutations == []


def test_a_later_invocation_reviews_the_process_then_durable_from_scratch():
    scene = applied_scene()

    def replace_process() -> None:
        reseal(
            scene,
            PROCESS_ID,
            lambda p: p["body"].update(created_at="2027-01-02T03:04:05Z"),
        )

    refusal(scene, no_model(scene), CoveringReviewer(scene, during=replace_process))
    reset_trace(scene)
    reviewer = CoveringReviewer(scene)

    result = recover(scene, no_model(scene), reviewer)

    current = payload_of(scene, PROCESS_ID)["artifact_digest"]
    assert result.process_result_digest == current
    assert payload_of(scene, REVIEW_ID)["body"]["process_result_digest"] == current
    assert len(reviewer.calls) == 1


# --------------------------------------------------------------------------
# Progress discipline: each stage at most once, Architect before Reviewer
# --------------------------------------------------------------------------


def test_a_stage_that_left_its_case_unchanged_is_not_delegated_again(monkeypatch):
    scene = applied_scene()
    calls = []
    monkeypatch.setattr(
        tsa_recovery, "run_reviewer_stage", lambda *a, **k: calls.append(a)
    )

    result = recover(scene)

    assert result.boundary is RecoveryBoundary.REVIEWER_REQUIRED
    assert result.case is RecoveryCase.OUTPUT_APPLIED
    assert len(calls) == 1


def test_an_architect_stage_without_progress_is_not_delegated_again(monkeypatch):
    scene = accepted_scene()
    calls = []
    monkeypatch.setattr(
        tsa_recovery, "run_architect_stage", lambda *a, **k: calls.append(a)
    )

    result = recover(scene)

    assert result.boundary is RecoveryBoundary.ARCHITECT_REQUIRED
    assert result.case is RecoveryCase.DRAFT
    assert len(calls) == 1


def test_recovery_has_no_command_surface_and_no_mutation_of_its_own():
    text = Path(tsa_recovery.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "argparse",
        "hold_workspace",
        "print(",
        "sys.exit",
        ".write_document_content(",
        ".create_tsa_child_document(",
        ".create_project_document(",
    ):
        assert forbidden not in text


def test_case_9_a_landed_review_create_is_rediscovered_not_created_twice():
    scene = applied_scene()
    scene.tsa.after(CREATE, 1, fail(FIBERY_DOWN))
    reviewer = CoveringReviewer(scene)

    result = recover(scene, no_model(scene), reviewer)

    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert scene.tsa.count(CREATE) == 1, "rediscovered at its derived id"
    assert len(reviewer.calls) == 1


def bad_approve(scene, change) -> None:
    """A self-consistent APPROVE at the derived id whose evidence is wrong."""
    approve = decided(scene, "APPROVE")
    change(approve)
    approve = sealed_artifact(approve)
    validate_artifact(approve)
    scene.tsa.seed_child(DECISION_ID, ARCHITECTURE_ID, carrier("x", approve))
    reset_trace(scene)


def test_the_stages_still_refuse_an_approve_without_verifying_it():
    """Recovery verifies an APPROVE; I07 and I08 keep CYCLE_APPROVED unchanged."""
    scene = reviewed_scene()
    bad_approve(scene, lambda a: a["body"].update(ux_evidence_digest="0" * 64))

    with pytest.raises(ArchitectRefused) as stage:
        run_architect_stage(scene.tsa, scene.req, no_model(scene), PROJECT_ID, CYCLE)

    assert stage.value.code == "CYCLE_APPROVED"
    assert refusal(scene).code == "ARTIFACT_MALFORMED"


def test_an_approve_accepting_an_unknown_reference_is_not_honoured():
    scene = reviewed_scene()
    digest = payload_of(scene, PROCESS_ID)["artifact_digest"]
    bad_approve(
        scene,
        lambda a: a["body"].update(
            accepted_dispositions=[{"ref": f"{digest}#risks/9", "reason": "Known."}]
        ),
    )

    error = refusal(scene)

    assert error.code == "ARTIFACT_MALFORMED"
    assert error.details[0] == "DISPOSITION_UNKNOWN_REFERENCE"
    nothing_happened(scene)


def test_the_architect_is_never_delegated_after_the_reviewer(monkeypatch):
    """Durable state moved back to case 2 under the Reviewer: no replay here."""
    scene = applied_scene()

    def architecture_reverted(*_args, **_kwargs):
        scene.tsa.set_content(ARCHITECTURE_ID, bootstrap_carrier())
        raise ArchitectStageRequired(ArchitectCase.RECORDED_INPUT, 1)

    monkeypatch.setattr(tsa_recovery, "run_reviewer_stage", architecture_reverted)
    architect = RecordingModel(scene)

    result = recover(scene, architect)

    assert result.boundary is RecoveryBoundary.ARCHITECT_REQUIRED
    assert result.case is RecoveryCase.RECORDED_INPUT
    assert result.architect is None
    nothing_happened(scene, architect)


# --------------------------------------------------------------------------
# Durable progress inside one invocation (spec v0.6 section 3)
# --------------------------------------------------------------------------

GENERIC_NO_WRITE = ("othing was written", "othing was persisted")


def drift_after_the_review(monkeypatch, scene) -> None:
    """The Reviewer confirms its Review; the Requirement drifts before the gate."""
    real = tsa_recovery.run_reviewer_stage

    def reviewed_then_drifted(*args, **kwargs):
        result = real(*args, **kwargs)
        root_edited_after_review(scene)
        return result

    monkeypatch.setattr(tsa_recovery, "run_reviewer_stage", reviewed_then_drifted)


def test_a_confirmed_review_before_a_later_gate_refusal_is_reported(monkeypatch):
    scene = applied_scene()
    drift_after_the_review(monkeypatch, scene)

    error = refusal(scene, no_model(scene), CoveringReviewer(scene))

    assert error.code == "INPUTS_STALE"
    assert error.after_progress is True
    message = str(error)
    assert f"Review Result {REVIEW_ID!r} of iteration 1 was written and confirmed" in (
        message
    )
    assert "Process Result" not in message.split("The Human Decision")[0]
    assert "nothing was rolled back" in message
    assert "The Human Decision boundary was not reached." in message
    for claim in GENERIC_NO_WRITE:
        assert claim not in message
    validate_artifact(payload_of(scene, REVIEW_ID))


def test_case_1_progress_names_process_architecture_and_review(monkeypatch):
    scene = accepted_scene()
    drift_after_the_review(monkeypatch, scene)
    architect, reviewer = models(scene)

    error = refusal(scene, architect, reviewer)

    message = str(error)
    assert error.code == "INPUTS_STALE"
    assert f"Process Result {PROCESS_ID!r} of iteration 1 was persisted" in message
    assert "was applied to the Architecture Document" in message
    assert f"Review Result {REVIEW_ID!r} of iteration 1 was written and confirmed" in (
        message
    )
    assert error.details, "the gate's own details are kept"
    for claim in GENERIC_NO_WRITE:
        assert claim not in message


def test_a_reviewer_failing_before_its_write_is_never_claimed():
    scene = accepted_scene()
    reviewer = CoveringReviewer(scene, error=ModelRuntimeError("reviewer exited 1"))

    error = refusal(scene, RecordingModel(scene), reviewer)

    assert error.code == "MODEL_RUNTIME_FAILED"
    assert error.after_progress is True, "the Architect stage wrote"
    assert "Review Result" not in str(error).split("could not run")[0]
    assert REVIEW_ID not in scene.tsa.documents
    assert error.details == ("reviewer exited 1",)


def reviewer_truth_of_an_empty_read_back() -> str:
    direct = applied_scene()
    direct.tsa.store_as = lambda md: "" if is_review_carrier(md) else md
    with pytest.raises(ReviewerRefused) as caught:
        run_reviewer_stage(
            direct.tsa, direct.req, CoveringReviewer(direct), PROJECT_ID, CYCLE
        )
    return str(caught.value)


def test_a_review_written_but_not_confirmed_keeps_the_reviewer_own_text():
    truth = reviewer_truth_of_an_empty_read_back()
    alone = applied_scene()
    alone.tsa.store_as = lambda md: "" if is_review_carrier(md) else md
    after_architect = accepted_scene()
    after_architect.tsa.store_as = lambda md: "" if is_review_carrier(md) else md

    unchanged = refusal(alone, no_model(alone), CoveringReviewer(alone))
    wrapped = refusal(after_architect, *models(after_architect))

    assert str(unchanged) == truth and unchanged.after_progress is False
    assert message_after_progress(truth) in str(wrapped)
    assert "was written and confirmed" not in str(wrapped), "no Review claim"


#: (a gate or stage refusal, the same refusal once progress was made)
CLAUSE_CASES = [
    (
        "Gate refused. Nothing was written and no model was called.",
        "Gate refused.",
    ),
    (
        (
            "X is not admissible: y. The whole selection is refused and "
            "nothing was written."
        ),
        "X is not admissible: y. The whole selection is refused.",
    ),
    (
        "Could not run the Architect. Nothing was persisted or applied.",
        "Could not run the Architect.",
    ),
    (
        "Could not run the Reviewer. Nothing was persisted.",
        "Could not run the Reviewer.",
    ),
    (
        (
            "Iteration 1 carries an APPROVE; the cycle is closed to writes "
            "and nothing was written."
        ),
        "Iteration 1 carries an APPROVE; the cycle is closed to writes.",
    ),
    (
        (
            "Matches neither input nor output of iteration 1. Nothing was "
            "overwritten and no model was called; a human decides which is "
            "authoritative."
        ),
        (
            "Matches neither input nor output of iteration 1. a human decides "
            "which is authoritative."
        ),
    ),
]


@pytest.mark.parametrize(("before", "after"), CLAUSE_CASES)
def test_only_generic_no_mutation_clauses_are_removed(before, after):
    assert message_after_progress(before) == after


@pytest.mark.parametrize(
    "kept",
    [
        "Review Result 'r' is not observable after its create; nothing was written.",
        "The Architecture still holds the recorded input; nothing was retried.",
        "A note says nothing was written here, mid-sentence, on purpose.",
    ],
)
def test_scoped_and_mid_sentence_statements_are_kept(kept):
    assert message_after_progress(kept) == kept


def test_without_progress_a_refusal_is_raised_byte_identical():
    scene = applied_scene()
    root_edited_after_review(scene)
    reviewer = CoveringReviewer(scene)

    error = refusal(scene, no_model(scene), reviewer)

    assert error.after_progress is False
    assert str(error).endswith(
        "The whole selection is refused and nothing was written."
    )


#: (message with a generic no-mutation clause, the same message after progress),
#: exact strings: only the clause and its adjacent spacing may change.
EXACT_CASES = {
    "quoted-title-spacing": (
        "Reading 'Checkout  flow' failed. Nothing was written.",
        "Reading 'Checkout  flow' failed.",
    ),
    "error-detail-spacing": (
        "The write failed (HTTP 503:  upstream  busy). Nothing was persisted.",
        "The write failed (HTTP 503:  upstream  busy).",
    ),
    "trailing-newline": (
        "Refused. Nothing was written.\n",
        "Refused.\n",
    ),
    "lowercase-after-semicolon": (
        "Refused. Nothing was written; abc_id is the id.",
        "Refused. abc_id is the id.",
    ),
    "whole-sentence": (
        "Gate refused. Nothing was written and no model was called.",
        "Gate refused.",
    ),
    "leading-clause": (
        (
            "Matches neither. Nothing was overwritten and no model was called; "
            "doc-7f3a decides."
        ),
        "Matches neither. doc-7f3a decides.",
    ),
    "final-conjunct": (
        "The cycle is closed to writes and nothing was written.",
        "The cycle is closed to writes.",
    ),
    "opening-sentence": (
        "Nothing was written. Then  more.",
        "Then  more.",
    ),
}


@pytest.mark.parametrize("case", EXACT_CASES)
def test_only_the_clause_and_its_adjacent_spacing_change(case):
    before, after = EXACT_CASES[case]

    assert message_after_progress(before) == after


@pytest.mark.parametrize(
    "unchanged",
    [
        "A message  with  no clause at all.\n",
        "Review Result 'r' is not observable after its create; nothing was written.",
        "  Leading spaces and a tail; kept.  ",
    ],
)
def test_a_message_without_a_generic_clause_is_byte_identical(unchanged):
    assert message_after_progress(unchanged) == unchanged


# --------------------------------------------------------------------------
# Spec v0.7 — a cycle whose Architecture live Fibery re-serialized
# --------------------------------------------------------------------------


def incident_scene():
    """The first live pilot's durable state (2026-10-17).

    A valid Manifest, a persisted Process Result 0001, the Architecture holding
    that output in the form Fibery stored it, and no Review Result.
    """
    scene = accepted_scene()
    run_architect_stage(
        scene.tsa,
        scene.req,
        RecordingModel(scene, responses=[stored_table_response()]),
        PROJECT_ID,
        CYCLE,
        clock=fixed_clock,
    )
    emitted = scene.tsa.content_of(ARCHITECTURE_ID)
    scene.tsa.set_content(ARCHITECTURE_ID, fibery_stored(emitted))
    reset_trace(scene)
    scene.tsa.store_as = fibery_stored
    return scene


def test_a_fibery_stored_cycle_reaches_the_boundary_with_one_call_each():
    scene = accepted_scene()
    scene.tsa.store_as = fibery_stored
    architect = RecordingModel(scene, responses=[stored_table_response()])
    reviewer = CoveringReviewer(scene)

    result = recover(scene, architect, reviewer)

    output = architecture_envelope(scene)["body"]["content_fingerprint"]
    assert result.boundary is RecoveryBoundary.HUMAN_DECISION
    assert (len(architect.calls), len(reviewer.calls)) == (1, 1)
    assert "| --- | --- |" in scene.tsa.content_of(ARCHITECTURE_ID)
    assert payload_of(scene, REVIEW_ID)["body"]["architecture_fingerprint"] == output
    assert result.architecture_fingerprint == output


def test_the_incident_state_is_case_3_and_continues_at_the_reviewer():
    scene = incident_scene()
    architecture = scene.tsa.content_of(ARCHITECTURE_ID)
    process = scene.tsa.content_of(PROCESS_ID)
    reviewer = CoveringReviewer(scene)

    state = read_cycle_state(scene.tsa, scene.req, PROJECT_ID, CYCLE)
    assert classify_recovery_case(state) is RecoveryCase.OUTPUT_APPLIED
    result = recover(scene, no_model(scene), reviewer)

    assert result.architect is None, "no Architect call, no re-apply"
    assert len(reviewer.calls) == 1
    assert writes_other_than_review(scene) == []
    assert scene.tsa.content_of(ARCHITECTURE_ID) == architecture
    assert scene.tsa.content_of(PROCESS_ID) == process
    assert result.boundary is RecoveryBoundary.HUMAN_DECISION


@pytest.mark.parametrize(
    ("old", "new", "code"),
    [
        (
            "no API key subscription",
            "no key subscription",
            "ARCHITECTURE_RENDER_INVALID",
        ),
        (
            "| --- | --- | --- | --- | --- | --- |",
            "|---|---|---|---|---|---|",
            "ARCHITECTURE_RENDER_INVALID",
        ),
        ("The gate checks the login first.", "The gate checks.", "ARTIFACT_MALFORMED"),
    ],
)
def test_an_edited_incident_architecture_is_refused_before_any_model(old, new, code):
    scene = incident_scene()
    normative, fence, envelope = scene.tsa.content_of(ARCHITECTURE_ID).partition(
        "```json"
    )
    assert normative.count(old) == 1
    scene.tsa.set_content(
        ARCHITECTURE_ID, normative.replace(old, new) + fence + envelope
    )
    reset_trace(scene)
    reviewer = CoveringReviewer(scene)

    error = refusal(scene, no_model(scene), reviewer)

    assert error.code == code
    nothing_happened(scene, reviewer)


def test_an_incident_process_bound_to_another_manifest_is_refused():
    scene = incident_scene()
    reseal(scene, PROCESS_ID, lambda p: p["body"].update(manifest_digest="0" * 64))
    reset_trace(scene)
    reviewer = CoveringReviewer(scene)

    error = refusal(scene, no_model(scene), reviewer)

    assert error.code == "ARTIFACT_MALFORMED"
    nothing_happened(scene, reviewer)
