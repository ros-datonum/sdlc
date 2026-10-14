"""I08 — the Reviewer stage: output contract, derived status, persist, read-back.

Every scene is a real cycle whose iteration N holds an accepted I07 output:
the I04 bootstrap carrier, a Requirement the frozen chain applied, the real
I05 Manifest, and the real `run_architect_stage` writing the Process Result
and applying it through the I06 renderer. Only Fibery and the model are fakes,
so every claim below is D-class only; live Review writes stay behind gate I-3
(spec 19.3), and no test here shows a live model finding a real defect.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import replace
from pathlib import Path

import pytest

from architect_fake import (
    LATER_TIMESTAMP,
    RecordingModel,
    architect_response,
    architecture_writes,
    human_decision,
    mutation_trace,
    payload_of,
    place_child,
    process_id,
    resealed_carrier,
    reset_trace,
    response_text,
    review_result,
    secret_of,
    with_section,
)
from reviewer_fake import (
    applied_scene,
    apply_architect,
    claims,
    decision_id,
    finding,
    review_id,
    review_writes,
    reviewer_model,
    reviewer_response,
    verification,
    writes_other_than_review,
)
from sdlc import tsa_reviewer
from sdlc.fibery_workspace import FiberyError
from sdlc.model_runtime import (
    RUNTIME_ISOLATION_UNAVAILABLE,
    LocalCliModelRuntime,
    ModelRuntimeError,
)
from sdlc.model_runtime_config import TSA_REVIEWER_ROLE, load_model_runtime_config
from sdlc.tsa_architect import (
    ArchitectCase,
    ArchitectRefused,
    ArchitectStageOutcome,
    derive_review_status,
    run_architect_stage,
)
from sdlc.tsa_artifacts import REVIEWER_ROLE, sealed_artifact, validate_artifact
from sdlc.tsa_cycle import DocumentKind
from sdlc.tsa_reviewer import (
    ArchitectStageRequired,
    ReviewerRefused,
    ReviewerStageOutcome,
    run_reviewer_stage,
    select_reviewer_runtime,
    validate_reviewer_output,
)
from standard_fake import REQUIREMENT_ID
from test_model_runtime import CLAUDE_OK, Runner
from test_tsa_admission import (
    APPLICABLE,
    ARCHITECTURE_ID,
    CYCLE,
    MANIFEST_ID,
    PROJECT_ID,
    SECOND_ID,
    UX_DOCUMENT_ID,
    child_added_after_review,
    fail,
    root_edited_after_review,
)
from test_tsa_architect import (
    FIBERY_DOWN,
    accepted_by_i01,
    architecture_envelope,
    failing_clock,
    other_architecture,
    persisted_but_not_applied,
    replace_accepted_manifest,
    reseal,
)
from test_tsa_cycle import fixed_clock

REVIEW_ID = review_id(1)
PROCESS_ID = process_id(1)
REVIEW_HEADING = f"# TSA {CYCLE} — Review Result"


def review(scene, model=None, *, clock=fixed_clock):
    return run_reviewer_stage(
        scene.tsa,
        scene.req,
        reviewer_model(scene) if model is None else model,
        PROJECT_ID,
        CYCLE,
        clock=clock,
    )


def refusal(scene, model=None, *, clock=fixed_clock) -> ReviewerRefused:
    with pytest.raises(ReviewerRefused) as caught:
        review(scene, model, clock=clock)
    return caught.value


def no_model(scene) -> RecordingModel:
    """A runtime any call to which fails the test outright."""
    return RecordingModel(scene, error=AssertionError("no model call was expected"))


def review_payload(scene, iteration: int = 1) -> dict:
    return payload_of(scene, review_id(iteration))


def architect_reads_back(scene) -> ArchitectStageOutcome:
    """I07 on the same durable state: no model, no clock, nothing to apply."""
    result = run_architect_stage(
        scene.tsa, scene.req, no_model(scene), PROJECT_ID, CYCLE, clock=failing_clock
    )
    return result.outcome


def drift_requirement(scene) -> None:
    root_edited_after_review(scene)


def material_question_scene():
    """Iteration 1 applied with one material Architect product question."""
    question = {
        "detail": "May a logged-out user keep a draft?",
        "requirement_id": REQUIREMENT_ID,
        "material": True,
    }
    return applied_scene(
        architect=response_text(architect_response(product_questions=[question]))
    )


def is_review_carrier(markdown: str) -> bool:
    return markdown.startswith(REVIEW_HEADING)


# --------------------------------------------------------------------------
# A. The happy path and its trace (spec 14.1, 2.2.1, 4.6.4)
# --------------------------------------------------------------------------


def test_a_review_is_persisted_at_its_derived_id_and_stops_at_the_boundary():
    scene = applied_scene()
    architecture = scene.tsa.content_of(ARCHITECTURE_ID)
    model = reviewer_model(scene)

    result = review(scene, model)

    assert result.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert (result.iteration, result.review_result_document_id) == (1, REVIEW_ID)
    assert len(model.calls) == 1
    assert scene.tsa.mutations == [
        f"create:{REVIEW_ID}",
        f"write:{secret_of(scene, REVIEW_ID)}",
    ]
    assert scene.tsa.content_of(ARCHITECTURE_ID) == architecture
    assert scene.req.mutations == []
    assert decision_id(1) not in scene.tsa.documents


def test_the_persisted_review_carries_exactly_the_frozen_body():
    scene = applied_scene()
    response = reviewer_response(scene)
    process = payload_of(scene, PROCESS_ID)
    envelope = validate_artifact(payload_of(scene, MANIFEST_ID))

    result = review(scene, reviewer_model(scene, response))

    stored = review_payload(scene)
    artifact = validate_artifact(stored)
    body = artifact.body
    assert artifact.iteration == 1
    assert body["manifest_digest"] == envelope.body["manifest_digest"]
    assert body["process_result_document_id"] == PROCESS_ID
    assert body["process_result_digest"] == process["artifact_digest"]
    assert body["architecture_document_id"] == ARCHITECTURE_ID
    assert body["architecture_fingerprint"] == result.architecture_fingerprint
    assert body["reviewer_response"] == response
    assert body["derived_status"] == result.derived_status == "REVIEW_PASS"
    assert body["runtime"] == {"role": REVIEWER_ROLE}
    assert body["created_at"] == "2026-10-10T12:00:00Z"
    assert result.review_result_digest == stored["artifact_digest"]
    assert scene.tsa.content_of(REVIEW_ID).startswith(REVIEW_HEADING)


def test_the_reviewed_fingerprint_is_the_applied_outputs():
    scene = applied_scene()
    applied = json.loads(
        scene.tsa.content_of(ARCHITECTURE_ID).split("```json\n")[1].split("\n```")[0]
    )

    result = review(scene)

    assert result.architecture_fingerprint == applied["body"]["content_fingerprint"]


def test_the_trace_calls_once_then_creates_then_writes_the_review_only():
    scene = applied_scene()

    review(scene)

    assert mutation_trace(scene) == [
        ("model.run", ""),
        ("create_tsa_child_document", REVIEW_ID),
        ("write_document_content", secret_of(scene, REVIEW_ID)),
    ]


def test_the_last_calls_before_the_body_write_are_child_then_root_placement():
    scene = applied_scene()

    review(scene)

    log = scene.tsa.log
    write = log.index(("write_document_content", secret_of(scene, REVIEW_ID)))
    assert log[write - 2 : write] == [
        ("resolve_placement", REVIEW_ID),
        ("resolve_placement", ARCHITECTURE_ID),
    ]


def test_the_model_runtime_records_the_model_it_reports():
    scene = applied_scene()

    review(scene, reviewer_model(scene, model="claude-opus-5-5"))

    assert review_payload(scene)["body"]["runtime"] == {
        "role": REVIEWER_ROLE,
        "model": "claude-opus-5-5",
    }


# --------------------------------------------------------------------------
# B. The raw response contract (spec 10.1)
# --------------------------------------------------------------------------


def contract_refusals(scene) -> dict[str, str]:
    """Responses that fail 10.1 itself, each as the raw text the model sent."""
    valid = reviewer_response(scene)
    text = json.dumps(valid)
    refs = claims(scene)

    def with_items(*items) -> str:
        return json.dumps({**valid, "claim_verifications": list(items)})

    return {
        "fenced": f"```json\n{text}\n```",
        "prose-before": f"Here is my review.\n{text}",
        "two-objects": f"{text}\n{text}",
        "array": json.dumps([valid]),
        "duplicate-key": text.replace("{", '{"new_findings": [], ', 1),
        "nested-duplicate-key": text.replace(
            '"traceability_verification": {',
            '"traceability_verification": {"outcome": "REJECTED", ',
            1,
        ),
        "nan": text.replace('"new_findings": []', '"new_findings": NaN', 1),
        "verdict": json.dumps({**valid, "verdict": "APPROVE"}),
        "approval": json.dumps({**valid, "approved": True}),
        "recommendation": json.dumps(
            {
                **valid,
                "assessment": {**valid["assessment"], "recommendation": "Approve."},
            }
        ),
        "replacement-architecture": json.dumps(
            {**valid, "architecture": {"solution_structure": "Use mine instead."}}
        ),
        "confirmed-without-severity": with_items(
            verification(refs[0], "CONFIRMED"), verification(refs[1])
        ),
        "rejected-with-severity": with_items(
            verification(refs[0], "REJECTED", "INFO"), verification(refs[1])
        ),
        "unresolved-with-severity": with_items(
            verification(refs[0], "UNRESOLVED", "WARNING"), verification(refs[1])
        ),
        "finding-without-severity": json.dumps(
            {
                **valid,
                "new_findings": [
                    {"kind": "gap", "detail": "x", "requirement_id": REQUIREMENT_ID}
                ],
            }
        ),
        "missing-key": json.dumps(
            {key: value for key, value in valid.items() if key != "assessment"}
        ),
        "claim-ref-outside-the-grammar": with_items(
            {**verification(refs[0]), "claim_ref": "risk 0"}, verification(refs[1])
        ),
    }


CONTRACT_CASES = (
    "fenced",
    "prose-before",
    "two-objects",
    "array",
    "duplicate-key",
    "nested-duplicate-key",
    "nan",
    "verdict",
    "approval",
    "recommendation",
    "replacement-architecture",
    "confirmed-without-severity",
    "rejected-with-severity",
    "unresolved-with-severity",
    "finding-without-severity",
    "missing-key",
    "claim-ref-outside-the-grammar",
)


@pytest.mark.parametrize("case", CONTRACT_CASES)
def test_a_response_outside_the_closed_contract_is_refused_and_not_persisted(case):
    scene = applied_scene()
    model = reviewer_model(scene, contract_refusals(scene)[case])

    error = refusal(scene, model)

    assert error.code == "INVALID_MODEL_OUTPUT"
    assert "not repaired, re-requested or persisted" in str(error)
    assert len(model.calls) == 1
    assert scene.tsa.mutations == []


def test_whitespace_around_the_one_object_is_the_only_allowance():
    scene = applied_scene()
    text = f"\n  {json.dumps(reviewer_response(scene))}\n\n"

    assert validate_reviewer_output(text) == reviewer_response(scene)


def test_ordinary_words_and_code_in_findings_are_evidence_not_refused():
    """No keyword ban, and Rule S/X stays the Architect's (spec 9.2, not 10)."""
    scene = applied_scene()
    detail = (
        "The Epic and Task wording, the estimate and the approval flow are "
        "absent.\n```\nretry()\n```"
    )
    response = reviewer_response(scene, new_findings=[finding("INFO", detail)])

    result = review(scene, reviewer_model(scene, response))

    assert result.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    stored = review_payload(scene)["body"]["reviewer_response"]
    assert stored["new_findings"][0]["detail"] == detail


# --------------------------------------------------------------------------
# B. Coverage and the derived status (spec 6.3, 10.2; row 45)
# --------------------------------------------------------------------------


def status_cases(scene) -> dict[str, tuple[dict, str]]:
    refs = claims(scene)
    risk, question = refs
    what = [
        {"detail": "Who may log in is undecided.", "requirement_id": REQUIREMENT_ID}
    ]
    return {
        "pass": (reviewer_response(scene), "REVIEW_PASS"),
        "info": (
            reviewer_response(
                scene,
                verifications=[
                    verification(risk, "CONFIRMED", "INFO"),
                    verification(question, "CONFIRMED", "INFO"),
                ],
                new_findings=[finding("INFO")],
            ),
            "REVIEW_PASS",
        ),
        "warning": (
            reviewer_response(scene, new_findings=[finding("WARNING")]),
            "REVIEW_NEEDS_WORK",
        ),
        "blocking": (
            reviewer_response(
                scene,
                verifications=[
                    verification(risk, "CONFIRMED", "BLOCKING"),
                    verification(question),
                ],
                new_findings=[finding("WARNING")],
            ),
            "REVIEW_BLOCKING",
        ),
        "what-over-blocking": (
            reviewer_response(
                scene,
                new_findings=[finding("BLOCKING")],
                material_unresolved_what=what,
            ),
            "REVIEW_BLOCKED_ON_WHAT",
        ),
        "structure-over-what": (
            reviewer_response(
                scene,
                verifications=[verification(risk)],
                new_findings=[finding("BLOCKING")],
                material_unresolved_what=what,
            ),
            "REVIEW_STRUCTURALLY_INVALID",
        ),
        "traceability-rejected-is-not-structural": (
            reviewer_response(
                scene,
                traceability_verification={
                    "outcome": "REJECTED",
                    "reason": "The row for the gate names the wrong anchor.",
                },
            ),
            "REVIEW_PASS",
        ),
    }


STATUS_CASES = (
    "pass",
    "info",
    "warning",
    "blocking",
    "what-over-blocking",
    "structure-over-what",
    "traceability-rejected-is-not-structural",
)


@pytest.mark.parametrize("case", STATUS_CASES)
def test_the_status_is_derived_in_its_frozen_precedence_and_i07_reads_it_back(case):
    scene = applied_scene()
    response, expected = status_cases(scene)[case]

    result = review(scene, reviewer_model(scene, response))

    assert result.derived_status == expected
    assert review_payload(scene)["body"]["derived_status"] == expected
    assert architect_reads_back(scene) is ArchitectStageOutcome.ALREADY_APPLIED
    assert review(scene, no_model(scene), clock=failing_clock).derived_status == (
        expected
    )


@pytest.mark.parametrize(
    ("outcome", "severity", "expected"),
    [
        ("REJECTED", None, "REVIEW_PASS"),
        ("CONFIRMED", "INFO", "REVIEW_BLOCKED_ON_WHAT"),
        ("UNRESOLVED", None, "REVIEW_BLOCKED_ON_WHAT"),
    ],
)
def test_a_material_question_stays_open_unless_rejected_by_its_exact_ref(
    outcome, severity, expected
):
    scene = material_question_scene()
    risk, question = claims(scene)
    response = reviewer_response(
        scene,
        verifications=[verification(risk), verification(question, outcome, severity)],
    )

    result = review(scene, reviewer_model(scene, response))

    assert result.derived_status == expected
    assert architect_reads_back(scene) is ArchitectStageOutcome.ALREADY_APPLIED


def test_a_non_material_question_confirmed_blocks_nothing():
    scene = applied_scene()
    risk, question = claims(scene)
    response = reviewer_response(
        scene,
        verifications=[verification(risk), verification(question, "CONFIRMED", "INFO")],
    )

    assert review(scene, reviewer_model(scene, response)).derived_status == (
        "REVIEW_PASS"
    )


def coverage_cases(scene) -> dict[str, tuple[list, tuple[str, ...]]]:
    risk, question = claims(scene)
    digest = payload_of(scene, PROCESS_ID)["artifact_digest"]
    foreign = f"{'1' * 64}#risks/0"
    assumption = f"{digest}#assumptions/0"
    out_of_range = f"{digest}#risks/5"
    return {
        "missing": (
            [verification(risk)],
            (f"REVIEW_COVERAGE_INCOMPLETE {question}",),
        ),
        "duplicate": (
            [verification(risk), verification(question), verification(risk)],
            (f"REVIEW_COVERAGE_DUPLICATE {risk}",),
        ),
        "foreign-digest": (
            [verification(foreign), verification(question)],
            (
                f"DISPOSITION_UNKNOWN_REFERENCE {foreign}",
                f"REVIEW_COVERAGE_INCOMPLETE {risk}",
            ),
        ),
        "assumption-is-not-a-claim": (
            [verification(risk), verification(question), verification(assumption)],
            (f"DISPOSITION_UNKNOWN_REFERENCE {assumption}",),
        ),
        "out-of-range": (
            [verification(risk), verification(question), verification(out_of_range)],
            (f"DISPOSITION_UNKNOWN_REFERENCE {out_of_range}",),
        ),
        "none-at-all": (
            [],
            (
                f"REVIEW_COVERAGE_INCOMPLETE {question}",
                f"REVIEW_COVERAGE_INCOMPLETE {risk}",
            ),
        ),
    }


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "duplicate",
        "foreign-digest",
        "assumption-is-not-a-claim",
        "out-of-range",
        "none-at-all",
    ],
)
def test_defective_coverage_is_kept_as_evidence_with_its_diagnostics(case):
    """Row 45 and 10.2: schema-valid evidence is stored, never repaired."""
    scene = applied_scene()
    verifications, defects = coverage_cases(scene)[case]
    response = reviewer_response(scene, verifications=verifications)
    architecture = scene.tsa.content_of(ARCHITECTURE_ID)
    model = reviewer_model(scene, response)

    result = review(scene, model)

    assert result.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert result.derived_status == "REVIEW_STRUCTURALLY_INVALID"
    assert sorted(result.coverage_defects) == sorted(defects)
    stored = review_payload(scene)["body"]["reviewer_response"]
    assert stored["claim_verifications"] == verifications, "nothing filled in"
    assert scene.tsa.content_of(ARCHITECTURE_ID) == architecture
    assert len(model.calls) == 1, "no second call to fix the coverage"
    assert architect_reads_back(scene) is ArchitectStageOutcome.ALREADY_APPLIED


def test_complete_coverage_reports_no_diagnostics():
    scene = applied_scene()

    assert review(scene).coverage_defects == ()


def test_the_one_derivation_is_shared_with_the_architect_reader():
    """I08 imports the I07 function itself; there is no second precedence."""
    tree = ast.parse(inspect.getsource(tsa_reviewer))
    defined = {
        node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
    }
    assert tsa_reviewer.derive_review_status is derive_review_status
    assert not {"derive_review_status", "_derived_review_status"} & defined
    assert "SEVERITY_STATUSES" not in inspect.getsource(tsa_reviewer)


# --------------------------------------------------------------------------
# C. I08-owned rows 17, 18 and 45 (contract 7.2, 7.5; D-class only)
# --------------------------------------------------------------------------


def test_row_17_a_reported_contradiction_keeps_every_source_and_no_winner():
    scene = applied_scene()
    detail = (
        f"{REQUIREMENT_ID} requires a refusal while {SECOND_ID} requires a "
        "fallback; both are kept and neither is chosen."
    )
    contradiction = {**finding("BLOCKING", detail), "kind": "contradiction"}
    what = [{"detail": detail, "requirement_id": REQUIREMENT_ID}]
    response = reviewer_response(
        scene, new_findings=[contradiction], material_unresolved_what=what
    )
    selection = json.dumps(payload_of(scene, MANIFEST_ID)["body"]["manifest_body"])

    result = review(scene, reviewer_model(scene, response))

    stored = review_payload(scene)["body"]["reviewer_response"]
    assert stored["new_findings"] == [contradiction]
    assert stored["material_unresolved_what"] == what
    assert result.derived_status == "REVIEW_BLOCKED_ON_WHAT"
    assert json.dumps(payload_of(scene, MANIFEST_ID)["body"]["manifest_body"]) == (
        selection
    )
    assert scene.req.mutations == []
    assert writes_other_than_review(scene) == []


def test_row_18_a_replacement_architecture_in_the_response_is_refused():
    scene = applied_scene()
    architecture = scene.tsa.content_of(ARCHITECTURE_ID)
    model = reviewer_model(scene, contract_refusals(scene)["replacement-architecture"])

    error = refusal(scene, model)

    assert error.code == "INVALID_MODEL_OUTPUT"
    assert scene.tsa.content_of(ARCHITECTURE_ID) == architecture
    assert scene.tsa.mutations == []


def test_row_18_a_rewrite_instruction_in_prose_is_evidence_never_executed():
    scene = applied_scene()
    architecture = scene.tsa.content_of(ARCHITECTURE_ID)
    instruction = (
        "Replace section 3 of the Architecture Document with: 'Call the API "
        "with a key.' and update the Requirement to allow it."
    )
    response = reviewer_response(scene, new_findings=[finding("WARNING", instruction)])

    review(scene, reviewer_model(scene, response))

    assert scene.tsa.content_of(ARCHITECTURE_ID) == architecture
    assert architecture_writes(scene) == 0
    assert writes_other_than_review(scene) == []
    assert scene.req.mutations == []


def test_row_18_the_stage_has_no_path_to_any_other_write():
    """The Reviewer module names no Architecture, Process or Decision writer."""
    source = inspect.getsource(tsa_reviewer)

    for forbidden in (
        "run_architect_stage",
        "build_architecture_carrier",
        "build_process_result",
        "render_architecture",
        "human_decision",
        "HUMAN_DECISION",
        "PROCESS_RESULT",
        "write_requirement",
    ):
        assert forbidden not in source
    assert source.count("write_document_content(") == 1
    assert source.count("create_tsa_child_document(") == 1


@pytest.mark.parametrize("severity", ["BLOCKING", "WARNING"])
def test_row_45_a_reported_defect_is_persisted_and_the_cycle_stops(severity):
    scene = applied_scene()
    architecture = scene.tsa.content_of(ARCHITECTURE_ID)
    response = reviewer_response(scene, new_findings=[finding(severity)])
    model = reviewer_model(scene, response)

    result = review(scene, model)

    assert result.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert review_payload(scene)["body"]["reviewer_response"] == response
    assert scene.tsa.content_of(ARCHITECTURE_ID) == architecture
    assert len(model.calls) == 1
    assert decision_id(1) not in scene.tsa.documents
    assert process_id(2) not in scene.tsa.documents
    assert review(scene, no_model(scene)).outcome is (
        ReviewerStageOutcome.REVIEW_ALREADY_RECORDED
    )


# --------------------------------------------------------------------------
# D. Reuse and refusals of durable Reviews (contract 14.3 cases 5, 7, 8)
# --------------------------------------------------------------------------


def test_a_valid_current_review_is_reused_without_model_write_or_clock():
    scene = applied_scene()
    first = review(scene)
    reset_trace(scene)

    again = review(scene, no_model(scene), clock=failing_clock)

    assert again.outcome is ReviewerStageOutcome.REVIEW_ALREADY_RECORDED
    assert again.review_result_digest == first.review_result_digest
    assert (again.model_invoked, again.review_written) == (False, False)
    assert scene.tsa.mutations == []


def test_a_review_whose_inputs_drifted_is_stale_and_never_re_reviewed():
    scene = applied_scene()
    review(scene)
    drift_requirement(scene)
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "INPUTS_STALE"
    assert scene.tsa.mutations == []


def test_a_malformed_review_is_refused_and_never_repaired():
    scene = applied_scene()
    scene.tsa.seed_child(REVIEW_ID, ARCHITECTURE_ID, "# notes\n\nnot a carrier\n")

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert scene.tsa.content_of(REVIEW_ID) == "# notes\n\nnot a carrier\n"
    assert scene.tsa.mutations == []


def test_a_valid_review_at_a_non_derived_id_is_a_duplicate():
    other = applied_scene()
    review(other)
    scene = applied_scene()
    scene.tsa.seed_child(
        "rogue-review", ARCHITECTURE_ID, other.tsa.content_of(REVIEW_ID)
    )

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_DUPLICATE"
    assert error.details == ("rogue-review",)
    assert scene.tsa.mutations == []


def test_a_review_bound_to_another_process_result_is_refused():
    scene = applied_scene()
    fingerprint = architecture_envelope(scene)["body"]["content_fingerprint"]
    bound = review_result(scene, 1, fingerprint)
    bound["body"]["process_result_digest"] = "0" * 64
    place_child(scene, DocumentKind.REVIEW_RESULT, 1, sealed_artifact(bound))
    accepted_by_i01(scene, REVIEW_ID)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert scene.tsa.mutations == []


def test_a_tampered_stored_status_is_refused_by_both_stages():
    scene = applied_scene()
    review(scene, reviewer_model(scene, status_cases(scene)["warning"][0]))
    reseal(
        scene,
        REVIEW_ID,
        lambda payload: payload["body"].update(derived_status="REVIEW_PASS"),
    )
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert "derived_status" in str(error)
    with pytest.raises(ArchitectRefused) as architect:
        architect_reads_back(scene)
    assert architect.value.code == "ARTIFACT_MALFORMED"
    assert scene.tsa.mutations == []


def test_an_empty_review_shell_is_completed_by_one_fresh_call_in_place():
    scene = applied_scene()
    scene.tsa.seed_child(REVIEW_ID, ARCHITECTURE_ID, "")
    model = reviewer_model(scene)

    result = review(scene, model)

    assert result.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert len(model.calls) == 1
    assert scene.tsa.count("create_tsa_child_document") == 0
    assert review_writes(scene) == 1


def test_a_review_shell_left_by_a_lost_write_is_completed_by_the_next_run():
    scene = applied_scene()
    scene.tsa.before("write_document_content", 1, fail(FIBERY_DOWN))
    first = reviewer_model(scene)

    error = refusal(scene, first)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert "Nothing was retried" in str(error)
    assert (len(first.calls), review_writes(scene)) == (1, 1)
    assert scene.tsa.content_of(REVIEW_ID) == "", "the shell stays"
    reset_trace(scene)
    second = reviewer_model(scene)

    result = review(scene, second)

    assert result.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert len(second.calls) == 1
    assert scene.tsa.count("create_tsa_child_document") == 0


# --------------------------------------------------------------------------
# D. Unknown outcomes and read-back (spec 14.1, 14.4.1 window E)
# --------------------------------------------------------------------------


def test_an_unknown_create_that_landed_is_completed_in_place_not_recreated():
    scene = applied_scene()
    scene.tsa.after("create_tsa_child_document", 1, fail(FIBERY_DOWN))
    model = reviewer_model(scene)

    result = review(scene, model)

    assert result.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert scene.tsa.count("create_tsa_child_document") == 1
    assert len(model.calls) == 1
    assert review_writes(scene) == 1


def test_an_unknown_create_that_did_not_land_is_retried_once_at_the_same_id():
    scene = applied_scene()
    scene.tsa.before("create_tsa_child_document", 1, fail(FIBERY_DOWN))
    model = reviewer_model(scene)

    result = review(scene, model)

    assert result.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    creates = [e for e in scene.tsa.log if e[0] == "create_tsa_child_document"]
    assert creates == [("create_tsa_child_document", REVIEW_ID)] * 2
    assert scene.tsa.mutations.count(f"create:{REVIEW_ID}") == 1, "one durable"
    assert (len(model.calls), review_writes(scene)) == (1, 1)
    assert writes_other_than_review(scene) == []


def test_a_create_that_never_becomes_durable_is_refused_without_a_new_id():
    scene = applied_scene()
    scene.tsa.before("create_tsa_child_document", 1, fail(FIBERY_DOWN))
    scene.tsa.before("create_tsa_child_document", 2, fail(FIBERY_DOWN))

    error = refusal(scene)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert scene.tsa.count("create_tsa_child_document") == 2
    assert scene.tsa.mutations == []


def test_a_landed_write_whose_response_was_lost_is_confirmed_once():
    scene = applied_scene()
    scene.tsa.after("write_document_content", 1, fail(FIBERY_DOWN))
    model = reviewer_model(scene)

    result = review(scene, model)

    assert result.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert (len(model.calls), review_writes(scene)) == (1, 1)


def later_review(markdown: str) -> str:
    """The same Review, I01-valid and correctly bound, written at another time."""
    return resealed_carrier(
        markdown, lambda payload: payload["body"].update(created_at=LATER_TIMESTAMP)
    )


def foreign_process_review(markdown: str) -> str:
    return resealed_carrier(
        markdown,
        lambda payload: payload["body"].update(process_result_digest="0" * 64),
    )


def foreign_architecture_review(markdown: str) -> str:
    return resealed_carrier(
        markdown,
        lambda payload: payload["body"].update(architecture_document_id="elsewhere"),
    )


def status_tampered_review(markdown: str) -> str:
    return resealed_carrier(
        markdown,
        lambda payload: payload["body"].update(derived_status="REVIEW_BLOCKING"),
    )


READ_BACKS = {
    "another-valid-review": (later_review, "FIBERY_WRITE_FAILED"),
    "foreign-process-digest": (foreign_process_review, "ARTIFACT_MALFORMED"),
    "foreign-architecture-id": (foreign_architecture_review, "ARTIFACT_MALFORMED"),
    "tampered-status": (status_tampered_review, "ARTIFACT_MALFORMED"),
}


@pytest.mark.parametrize("lost", [False, True], ids=["normal-return", "lost-response"])
@pytest.mark.parametrize("stored", READ_BACKS)
def test_the_read_back_must_be_the_intended_review_and_keeps_specific_codes(
    stored, lost
):
    scene = applied_scene()
    change, code = READ_BACKS[stored]
    scene.tsa.store_as = lambda md: change(md) if is_review_carrier(md) else md
    if lost:
        scene.tsa.after("write_document_content", 1, fail(FIBERY_DOWN))
    model = reviewer_model(scene)

    error = refusal(scene, model)

    assert error.code == code
    validate_artifact(review_payload(scene))
    assert (len(model.calls), review_writes(scene)) == (1, 1), "never written twice"
    assert writes_other_than_review(scene) == []
    assert "undone" not in str(error) and "rolled back" not in str(error)


def test_a_write_that_read_back_empty_is_no_success_and_not_retried():
    scene = applied_scene()
    scene.tsa.store_as = lambda md: "" if is_review_carrier(md) else md

    error = refusal(scene)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert review_writes(scene) == 1


# --------------------------------------------------------------------------
# E. Mutation windows: fixed bindings and currentness (contract 10, 14.2)
# --------------------------------------------------------------------------


def test_a_manifest_replaced_during_the_call_is_never_persisted():
    """Once a Process binds the Manifest, replacing it breaks durable lineage."""
    scene = applied_scene()
    model = reviewer_model(scene, during=lambda: replace_accepted_manifest(scene))

    error = refusal(scene, model)

    assert error.code == "ARTIFACT_MALFORMED"
    assert "A different recorded UX decision." not in model.calls[0]["context"]
    assert len(model.calls) == 1
    assert scene.tsa.mutations == []


def same_output_other_process(scene) -> None:
    """The Process Result resealed at another time: same output, other digest."""
    reseal(
        scene,
        PROCESS_ID,
        lambda payload: payload["body"].update(created_at=LATER_TIMESTAMP),
    )


def test_a_process_replaced_by_the_same_output_is_not_the_reviewed_one():
    scene = applied_scene()
    model = reviewer_model(scene, during=lambda: same_output_other_process(scene))

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert error.details == (PROCESS_ID,)
    assert architect_reads_back(scene) is ArchitectStageOutcome.ALREADY_APPLIED
    assert len(model.calls) == 1
    assert scene.tsa.mutations == []


def test_an_architecture_replaced_during_the_call_is_divergent():
    scene = applied_scene()
    divergent = other_architecture(scene, "Replaced while the Reviewer ran.")
    model = reviewer_model(
        scene,
        during=lambda: scene.tsa.set_content(ARCHITECTURE_ID, divergent.text),
    )

    error = refusal(scene, model)

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert scene.tsa.mutations == []


def evidence_stops_being_admissible(scene) -> None:
    entity_id = payload_of(scene, MANIFEST_ID)["body"]["manifest_body"]["requirements"][
        0
    ]["entity_id"]
    record = scene.req.requirements[entity_id]
    scene.req.requirements[entity_id] = replace(record, state="Process")


@pytest.mark.parametrize(
    "drift",
    [
        root_edited_after_review,
        child_added_after_review,
        evidence_stops_being_admissible,
    ],
    ids=["root", "child", "evidence"],
)
def test_requirement_drift_during_the_call_is_never_persisted(drift):
    scene = applied_scene()
    model = reviewer_model(scene, during=lambda: drift(scene))

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert len(model.calls) == 1
    assert scene.tsa.mutations == []


def test_requirement_drift_before_the_call_refuses_without_a_model_call():
    scene = applied_scene()
    drift_requirement(scene)
    model = reviewer_model(scene)

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert model.calls == []
    assert scene.tsa.mutations == []


def test_ux_drift_during_the_call_is_stale_under_applicable():
    scene = applied_scene(ux=APPLICABLE)
    model = reviewer_model(
        scene, during=lambda: scene.tsa.set_content(UX_DOCUMENT_ID, "# Changed UX\n")
    )

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert scene.tsa.mutations == []


def test_not_applicable_never_reads_a_ux_document_on_any_revalidation():
    scene = applied_scene()

    review(scene)

    assert not [entry for entry in scene.tsa.log if entry[1] == UX_DOCUMENT_ID]


def test_drift_after_the_create_leaves_only_the_empty_shell():
    scene = applied_scene()
    scene.tsa.after("create_tsa_child_document", 1, lambda: drift_requirement(scene))

    error = refusal(scene)

    assert error.code == "INPUTS_STALE"
    assert scene.tsa.content_of(REVIEW_ID) == "", "the shell stays, unfilled"
    assert review_writes(scene) == 0


def test_a_process_replaced_after_the_create_refuses_before_the_body_write():
    scene = applied_scene()
    scene.tsa.after(
        "create_tsa_child_document", 1, lambda: same_output_other_process(scene)
    )

    error = refusal(scene)

    assert error.code == "INPUTS_STALE"
    assert error.details == (PROCESS_ID,)
    assert review_writes(scene) == 0


def trace_requirement_reads(scene) -> None:
    """Put Requirement content reads into the one ordered TSA trace."""
    original = scene.req.read_document_content

    def traced(secret):
        scene.tsa.log.append(("requirement.read_document_content", secret))
        return original(secret)

    scene.req.read_document_content = traced


def test_drift_before_a_lost_create_is_refused_before_the_retry():
    scene = applied_scene()
    trace_requirement_reads(scene)

    def drift_then_lose() -> None:
        drift_requirement(scene)
        raise FiberyError(FIBERY_DOWN)

    scene.tsa.before("create_tsa_child_document", 1, drift_then_lose)
    model = reviewer_model(scene)

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert len(model.calls) == 1
    assert scene.tsa.count("create_tsa_child_document") == 1, "no second attempt"
    assert REVIEW_ID not in scene.tsa.documents
    assert scene.tsa.mutations == []
    after_create = scene.tsa.log[
        scene.tsa.log.index(("create_tsa_child_document", REVIEW_ID)) + 1 :
    ]
    assert ("requirement.read_document_content", scene.root.secret) in after_create


def test_a_process_replaced_before_a_lost_create_is_refused_before_the_retry():
    """Only the fixed bindings see this: the fresh gate itself is clean."""
    scene = applied_scene()

    def replace_then_lose() -> None:
        same_output_other_process(scene)
        raise FiberyError(FIBERY_DOWN)

    scene.tsa.before("create_tsa_child_document", 1, replace_then_lose)
    model = reviewer_model(scene)

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert error.details == (PROCESS_ID,)
    assert len(model.calls) == 1
    assert scene.tsa.count("create_tsa_child_document") == 1, "no second attempt"
    assert REVIEW_ID not in scene.tsa.documents
    assert scene.tsa.mutations == []


def reads_before_the_body_write() -> int:
    """How many content reads one clean run makes before its Review write."""
    probe = applied_scene()
    review(probe)
    log = probe.tsa.log
    write = log.index(("write_document_content", secret_of(probe, REVIEW_ID)))
    return [name for name, _ in log[:write]].count("read_document_content")


def test_placement_drift_during_the_last_content_reads_refuses_the_write():
    last_read = reads_before_the_body_write()
    scene = applied_scene()

    def move() -> None:
        scene.tsa.documents[REVIEW_ID].parent_document_id = "elsewhere"

    scene.tsa.after("read_document_content", last_read, move)

    error = refusal(scene)

    assert error.code == "CYCLE_FOREIGN_PROJECT"
    assert scene.tsa.mutations == [f"create:{REVIEW_ID}"]
    assert review_writes(scene) == 0
    assert scene.tsa.log[-2:] == [
        ("resolve_placement", REVIEW_ID),
        ("resolve_placement", ARCHITECTURE_ID),
    ], "refused at the final child-then-root pair, nothing read after"


# --------------------------------------------------------------------------
# F. Boundaries: the Architect stage, lifecycle, runtime
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("setup", "case"),
    [
        ("no process", ArchitectCase.NO_PROCESS),
        ("process shell", ArchitectCase.PROCESS_SHELL),
        ("recorded input", ArchitectCase.RECORDED_INPUT),
    ],
)
def test_without_an_applied_output_the_reviewer_neither_applies_nor_calls(setup, case):
    from architect_fake import accepted_scene

    scene = accepted_scene()
    if setup == "process shell":
        scene.tsa.seed_child(PROCESS_ID, ARCHITECTURE_ID, "")
    elif setup == "recorded input":
        persisted_but_not_applied(scene)
    architecture = scene.tsa.content_of(ARCHITECTURE_ID)
    reset_trace(scene)
    model = no_model(scene)

    with pytest.raises(ArchitectStageRequired) as required:
        review(scene, model)

    assert (required.value.case, required.value.iteration) == (case, 1)
    assert model.calls == []
    assert scene.tsa.mutations == []
    assert scene.tsa.content_of(ARCHITECTURE_ID) == architecture
    assert REVIEW_ID not in scene.tsa.documents


def test_a_divergent_architecture_is_refused_without_a_model_call():
    scene = applied_scene()
    divergent = other_architecture(scene, "Edited by hand after the apply.")
    scene.tsa.set_content(ARCHITECTURE_ID, divergent.text)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert scene.tsa.mutations == []


def record_decision(scene, decision: str) -> None:
    record = human_decision(scene, 1, review_payload(scene), decision)
    place_child(scene, DocumentKind.HUMAN_DECISION, 1, record)
    reset_trace(scene)


def test_an_approved_cycle_is_closed_to_the_reviewer():
    scene = applied_scene()
    review(scene)
    record_decision(scene, "APPROVE")

    error = refusal(scene, no_model(scene))

    assert error.code == "CYCLE_APPROVED"
    assert scene.tsa.mutations == []


def test_a_rework_opens_nothing_for_the_reviewer_until_the_architect_ran():
    scene = applied_scene()
    review(scene)
    record_decision(scene, "REWORK")

    with pytest.raises(ArchitectStageRequired) as required:
        review(scene, no_model(scene))

    assert (required.value.case, required.value.iteration) == (
        ArchitectCase.NO_PROCESS,
        2,
    )
    assert scene.tsa.mutations == []
    assert decision_id(2) not in scene.tsa.documents


def test_a_reworked_iteration_is_reviewed_into_its_own_slot():
    scene = applied_scene()
    first = review(scene)
    record_decision(scene, "REWORK")
    apply_architect(
        scene, json.dumps(with_section(solution_structure="A revised structure."))
    )
    model = reviewer_model(scene, reviewer_response(scene, 2))

    result = review(scene, model)

    assert result.iteration == 2
    assert result.review_result_document_id == review_id(2)
    assert review_payload(scene)["artifact_digest"] == first.review_result_digest
    assert scene.tsa.mutations == [
        f"create:{review_id(2)}",
        f"write:{secret_of(scene, review_id(2))}",
    ]


def test_row_33_shape_a_model_failure_is_no_success_and_a_retry_works():
    scene = applied_scene()
    failing = reviewer_model(scene, error=ModelRuntimeError("timed out after 900s"))

    error = refusal(scene, failing)

    assert error.code == "MODEL_RUNTIME_FAILED"
    assert len(failing.calls) == 1
    assert scene.tsa.mutations == []
    retry = reviewer_model(scene)
    assert review(scene, retry).outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert len(retry.calls) == 1


def test_an_invalid_response_starts_no_repair_loop():
    scene = applied_scene()
    model = RecordingModel(
        scene,
        responses=["Sorry, prose.", json.dumps(reviewer_response(scene))],
    )

    error = refusal(scene, model)

    assert error.code == "INVALID_MODEL_OUTPUT"
    assert len(model.calls) == 1
    assert scene.tsa.mutations == []


def test_the_reviewer_role_comes_from_i09_through_the_unchanged_selection():
    config = load_model_runtime_config(Path("config/sdlc.toml"))

    selection = select_reviewer_runtime(config)

    assert selection.role == TSA_REVIEWER_ROLE == REVIEWER_ROLE
    assert (selection.definition.name, selection.model) == ("claude", None)


def test_claude_runs_through_the_real_runtime_without_a_model_flag():
    scene = applied_scene()
    text = json.dumps(reviewer_response(scene))
    runner = Runner([(0, CLAUDE_OK, ""), (0, text, "")])
    runtime = LocalCliModelRuntime(
        select_reviewer_runtime(load_model_runtime_config(Path("config/sdlc.toml"))),
        runner=runner,
        which=lambda name: f"/opt/bin/{name}",
        environment={"PATH": "/usr/bin", "HOME": "/home/someone"},
    )

    result = review(scene, runtime)

    assert result.outcome is ReviewerStageOutcome.REVIEW_RECORDED
    assert runner.calls[0].argv[1:] == ("auth", "status", "--json")
    assert "--model" not in runner.calls[1].argv
    assert review_payload(scene)["body"]["runtime"] == {"role": REVIEWER_ROLE}


def test_codex_stays_blocked_with_no_subprocess_and_no_fallback():
    scene = applied_scene()
    runner = Runner([(0, CLAUDE_OK, ""), (0, "{}", "")])
    runtime = LocalCliModelRuntime(
        select_reviewer_runtime(
            load_model_runtime_config(Path("config/sdlc.toml")),
            runtime_override="codex",
        ),
        runner=runner,
        which=lambda name: f"/opt/bin/{name}",
        environment={"PATH": "/usr/bin"},
    )

    error = refusal(scene, runtime)

    assert error.code == "MODEL_RUNTIME_FAILED"
    assert any(RUNTIME_ISOLATION_UNAVAILABLE in detail for detail in error.details)
    assert runner.calls == []
    assert scene.tsa.mutations == []


def test_the_stage_neither_takes_the_command_guard_nor_reaches_real_processes():
    """The guard is the command's (I12); the model arrives as a runtime port."""
    tree = ast.parse(inspect.getsource(tsa_reviewer))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    for forbidden in (
        "subprocess",
        "sdlc.cli",
        "sdlc.worker_runner_guard",
        "sdlc.raw_execution_guard",
        "sdlc.requirement_runner",
        "sdlc.fibery_http",
        "sdlc.fibery_client",
    ):
        assert forbidden not in imported
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "hold_workspace" not in called
    assert "LocalCliModelRuntime" not in called
