"""WI-1 — the material-WHAT safety gate (Requirement-Material-WHAT-Gate-v0.1).

Process records structured product questions; Review verifies each exactly
once and may add the material WHAT questions Process missed; code alone
derives CLEAR or BLOCKED_ON_WHAT. Ready, Apply and TSA admission each admit
only CLEAR on their own: pre-0.4 evidence is UNKNOWN, refused as missing
evidence, and never read as CLEAR or reported as a confirmed defect.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from processor_fake import FakeModelRuntime
from ready_fake import mutations_since, only_state_transition
from review_fake import (
    build_review_workspace,
    confirm,
    finding,
    payload_of,
    review_output,
    rewrite_payload,
)
from sdlc.process_result import (
    InvalidProcessResult,
    parse_process_result,
    render_process_result,
)
from sdlc.ready_decision import (
    approve_standard_requirement,
    rework_standard_requirement,
)
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.requirement_dispatcher import RouteDecision, select_route
from sdlc.requirement_runner import CycleOutcome, run_cycle
from sdlc.results import ApplyResultCode, ReadyDecisionResultCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.review_result import (
    InvalidReviewResult,
    build_review_result,
    parse_review_result,
    render_review_result,
    review_result_name,
    what_clearance,
)
from sdlc.standard_analysis import (
    InvalidAnalysisOutput,
    ProductQuestion,
    ResolutionClass,
    parse_analysis_output,
)
from sdlc.standard_review import (
    InvalidReviewOutput,
    MaterialWhat,
    ReviewOutput,
    ReviewVerdict,
    WhatStatus,
    parse_review_output,
)
from sdlc.standard_reviewer import review_standard_requirement
from sdlc.tsa_admission import AdmissionResultCode
from standard_fake import REQUIREMENT_ID, analysis_output
from test_requirement_dispatcher import NOT_PROCESSED, real_workers
from test_requirement_runner import (
    FAILED_STATUS,
    PROCESSING,
    SUCCEEDED,
    StatusWorkspace,
)
from test_tsa_admission import (
    REQUIREMENT_ID as TSA_REQUIREMENT_ID,
)
from test_tsa_admission import (
    SECOND_ID,
    add_applied_requirement,
    clean_refusal,
    start,
    world,
)

FIXTURES = Path(__file__).parent / "fixtures" / "requirements_autonomy"
ORIGINAL_RAW = FIXTURES / "uppercase_original_raw.md"
ORIGINAL_RAW_SHA256 = "b9116514a3fa4c52093894c16c7d371f5c07fba181f36e4932a4605588a7cc12"
ORIGINAL_RAW_BYTES = 3413
TSAP1_REVIEW = FIXTURES / "tsap1_fr0124_review_result_0001.md"
TSAP1_PROCESS = FIXTURES / "tsap1_fr0124_process_result_0001.md"

MATERIAL = {
    "detail": "Must an oversized valid request still succeed?",
    "material": True,
}
MINOR = {"detail": "Should the error body name the endpoint?", "material": False}


def material_question(**changes):
    return ProductQuestion(**{**MATERIAL, **changes})


def verify_question(outcome="CONFIRMED", index=0, **fields):
    body = {"question_index": index, "outcome": outcome, "reason": "Checked."}
    if outcome == "CONFIRMED":
        body.setdefault("material", True)
    body.update(fields)
    return body


# -- the reviewed Requirement, through the frozen chain ----------------------


def reviewed(questions=(), findings=(), **response):
    """A Requirement reviewed by the real Reviewer over `questions`."""
    ws, requirement, root, _ = build_review_workspace(
        findings=findings, questions=tuple(ProductQuestion(**q) for q in questions)
    )
    result = review_standard_requirement(
        ws, FakeModelRuntime(responses=[review_output(**response)]), requirement.id
    )
    return ws, requirement, root, result


def latest_review(ws):
    [node] = [
        d
        for d in ws.documents
        if d.name.startswith(f"{REQUIREMENT_ID} — Review Result")
    ]
    return node, parse_review_result(ws.content[node.secret])


def latest_process(ws):
    node = [
        d
        for d in ws.documents
        if d.name.startswith(f"{REQUIREMENT_ID} — Process Result")
    ][-1]
    return node, parse_process_result(ws.content[node.secret])


def make_legacy(ws):
    """Rewrite both artifacts as the pre-gate code wrote them (0.3, no questions)."""
    process_node, process = latest_process(ws)
    ws.content[process_node.secret] = render_process_result(
        replace(process, version="0.3", product_questions=None)
    )
    review_node, review = latest_review(ws)
    ws.content[review_node.secret] = render_review_result(
        replace(review, version="0.3")
    )


def move_to_apply_in_fibery(ws, requirement):
    """A human moves the State in the Fibery UI, past the approve command."""
    ws.set_requirement_state(requirement.id, "Apply")
    return len(ws.mutations)


# -- A. Process records structured product questions -----------------------


def test_process_renders_open_questions_from_the_structured_questions():
    result = parse_analysis_output(analysis_output(questions=[MATERIAL, MINOR]))
    assert result.product_questions == (
        ProductQuestion(MATERIAL["detail"], True, ResolutionClass.HUMAN_REQUIRED),
        ProductQuestion(MINOR["detail"], False, ResolutionClass.HUMAN_REQUIRED),
    )
    assert result.normalized.open_questions == (
        f"- {MATERIAL['detail']}\n- {MINOR['detail']}"
    )
    assert parse_analysis_output(analysis_output()).normalized.open_questions == "None."


@pytest.mark.parametrize(
    ("question", "message"),
    [
        ({"detail": "x"}, "is missing: material"),
        ({"detail": "x", "material": "yes"}, "material must be true or false"),
        ({"detail": "x", "material": 1}, "material must be true or false"),
        ({"detail": "a\nb", "material": True}, "single line"),
        ({"detail": "x", "material": True, "answer": "y"}, "does not define"),
    ],
)
def test_a_malformed_product_question_is_refused(question, message):
    with pytest.raises(InvalidAnalysisOutput, match=message):
        parse_analysis_output(analysis_output(questions=[question]))


def test_the_model_cannot_write_open_questions_prose_itself():
    body = json.loads(analysis_output())
    body["normalized_requirement"]["open_questions"] = "Any question?"
    with pytest.raises(InvalidAnalysisOutput, match="rendered from product_questions"):
        parse_analysis_output(json.dumps(body))


def test_a_process_result_persists_its_questions_and_older_ones_carry_none():
    ws, _, _, _ = build_review_workspace(questions=(material_question(),))
    _, process = latest_process(ws)
    assert process.version == "0.6" and process.has_question_evidence
    assert process.product_questions == (
        material_question(authority=ResolutionClass.HUMAN_REQUIRED),
    )
    older = replace(process, version="0.3")
    reread = parse_process_result(render_process_result(older))
    assert reread.product_questions is None and not reread.has_question_evidence


def test_an_older_process_result_carrying_questions_is_incoherent():
    ws, _, _, _ = build_review_workspace(questions=(material_question(),))
    node, _ = latest_process(ws)
    rewrite_payload(ws, node, process_result_version="0.3")
    with pytest.raises(InvalidProcessResult, match="cannot carry product questions"):
        parse_process_result(ws.content[node.secret])
    rewrite_payload(ws, node, process_result_version="0.4", product_questions=None)
    with pytest.raises(InvalidProcessResult, match="must carry its"):
        parse_process_result(ws.content[node.secret])


# -- B/C/D. independent verification and the derived status ----------------


def test_clear_and_pass():
    ws, _, _, result = reviewed()
    _, review = latest_review(ws)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED
    assert (review.verdict, review.what_status) == (
        ReviewVerdict.PASS,
        WhatStatus.CLEAR,
    )


def test_clear_with_needs_work_is_a_separate_axis():
    ws, _, _, _ = reviewed(
        questions=[MINOR],
        findings=(finding(),),
        finding_verifications=[confirm(severity="WARNING")],
        question_verifications=[verify_question(material=False)],
    )
    _, review = latest_review(ws)
    assert review.verdict is ReviewVerdict.NEEDS_WORK
    assert review.what_status is WhatStatus.CLEAR


def test_pass_does_not_guarantee_clearance():
    ws, _, _, _ = reviewed(
        questions=[MATERIAL], question_verifications=[verify_question()]
    )
    _, review = latest_review(ws)
    assert review.verdict is ReviewVerdict.PASS
    assert review.what_status is WhatStatus.BLOCKED_ON_WHAT


@pytest.mark.parametrize(
    ("questions", "verification", "status"),
    [
        ([MATERIAL], verify_question(), WhatStatus.BLOCKED_ON_WHAT),
        ([MINOR], verify_question(material=True), WhatStatus.BLOCKED_ON_WHAT),
        ([MATERIAL], verify_question(material=False), WhatStatus.CLEAR),
        ([MATERIAL], verify_question("UNRESOLVED"), WhatStatus.BLOCKED_ON_WHAT),
        ([MINOR], verify_question("UNRESOLVED"), WhatStatus.BLOCKED_ON_WHAT),
        (
            [MATERIAL],
            verify_question("REJECTED", basis="ANSWERED_IN_THIS_REQUIREMENT"),
            WhatStatus.CLEAR,
        ),
        (
            [MATERIAL],
            verify_question("REJECTED", basis="TECHNICAL_HOW"),
            WhatStatus.CLEAR,
        ),
        (
            [MATERIAL],
            verify_question(
                "REJECTED",
                basis="ANSWERED_BY_OTHER_REQUIREMENT",
                requirement_id="SDLC-FR-0002",
            ),
            WhatStatus.BLOCKED_ON_WHAT,
        ),
        (
            [MINOR],
            verify_question(
                "REJECTED",
                basis="ANSWERED_BY_OTHER_REQUIREMENT",
                requirement_id="SDLC-FR-0002",
            ),
            WhatStatus.CLEAR,
        ),
    ],
    ids=[
        "confirmed material",
        "reviewer upgrades to material",
        "reviewer judges not material",
        "unresolved material",
        "unresolved blocks whatever Process claimed",
        "answered in this Requirement",
        "genuine HOW question",
        "peer-only answer does not clear",
        "peer answer on a non-material question",
    ],
)
def test_the_status_follows_each_verified_question(questions, verification, status):
    ws, _, _, result = reviewed(
        questions=questions, question_verifications=[verification]
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert latest_review(ws)[1].what_status is status


def test_a_reviewer_added_material_question_blocks():
    ws, _, _, _ = reviewed(material_unresolved_what=[{"detail": "Who may retry?"}])
    _, review = latest_review(ws)
    assert review.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert review.material_unresolved_what == (MaterialWhat("Who may retry?"),)


@pytest.mark.parametrize(
    ("verifications", "message"),
    [
        ([], "leaves a Process claim unverified"),
        ([verify_question(), verify_question()], "verified more than once"),
        ([verify_question(index=1)], "has 1"),
        ([verify_question(material=None)], "must judge material"),
        ([verify_question("REJECTED")], "needs a basis"),
        (
            [verify_question("REJECTED", basis="ANSWERED_BY_OTHER_REQUIREMENT")],
            "must name it",
        ),
        (
            [
                verify_question(
                    "REJECTED", basis="TECHNICAL_HOW", requirement_id="SDLC-FR-0002"
                )
            ],
            "must not name a Requirement",
        ),
        ([verify_question("UNRESOLVED", material=True)], "only a CONFIRMED"),
        ([verify_question(status="CLEAR")], "does not define"),
    ],
    ids=[
        "missing verification",
        "duplicate verification",
        "invented index",
        "confirmed without materiality",
        "rejected without basis",
        "peer basis without peer",
        "peer named without peer basis",
        "unresolved with materiality",
        "model states a status",
    ],
)
def test_a_review_that_does_not_verify_each_question_once_is_refused(
    verifications, message
):
    with pytest.raises(InvalidReviewOutput, match=message):
        parse_review_output(
            review_output(question_verifications=verifications),
            (),
            (),
            (material_question(),),
        )


def test_the_stage_writes_nothing_for_an_incomplete_question_verification():
    ws, requirement, _, result = reviewed(questions=[MATERIAL])
    assert result.code is ReviewCode.INVALID_MODEL_OUTPUT, result
    assert [
        d
        for d in ws.documents
        if d.name.startswith(f"{REQUIREMENT_ID} — Review Result")
    ] == []
    assert ws.requirements[requirement.id].state == "Review"


def test_review_refuses_process_evidence_without_questions_before_any_model_call():
    ws, requirement, _, _ = build_review_workspace()
    node, process = latest_process(ws)
    ws.content[node.secret] = render_process_result(
        replace(process, version="0.3", product_questions=None)
    )
    model = FakeModelRuntime(responses=[review_output()])
    result = review_standard_requirement(ws, model, requirement.id)
    assert result.code is ReviewCode.PRODUCT_QUESTION_EVIDENCE_REQUIRED, result
    assert model.calls == [] and not result.model_invoked
    assert [
        d
        for d in ws.documents
        if d.name.startswith(f"{REQUIREMENT_ID} — Review Result")
    ] == []


def test_the_prompt_shows_each_question_with_its_claimed_materiality():
    ws, requirement, _, _ = build_review_workspace(questions=(material_question(),))
    model = FakeModelRuntime(
        responses=[review_output(question_verifications=[verify_question()])]
    )
    review_standard_requirement(ws, model, requirement.id)
    [call] = model.calls
    assert (
        f"[0] material=true, HUMAN_REQUIRED: {MATERIAL['detail']}" in (call["context"])
    )
    assert "A question answered only by" in " ".join(call["prompt"].split())


# -- E. the status is bound and recomputed ----------------------------------


def test_a_forged_clear_status_is_refused_on_read():
    ws, _, _, _ = reviewed(
        questions=[MATERIAL], question_verifications=[verify_question()]
    )
    node, _ = latest_review(ws)
    rewrite_payload(ws, node, derived_what_status="CLEAR")
    with pytest.raises(InvalidReviewResult, match="contradicts the verified"):
        parse_review_result(ws.content[node.secret])


@pytest.mark.parametrize(
    "missing",
    [
        "reviewed_product_questions",
        "product_question_verifications",
        "material_unresolved_what",
        "derived_what_status",
    ],
)
def test_a_0_4_review_without_its_what_evidence_is_refused(missing):
    ws, _, _, _ = reviewed()
    node, _ = latest_review(ws)
    payload, _, _ = payload_of(ws, node)
    del payload[missing]
    text = ws.content[node.secret]
    start = text.index("```json\n") + len("```json\n")
    end = text.index("\n```", start)
    ws.content[node.secret] = text[:start] + json.dumps(payload) + text[end:]
    with pytest.raises(InvalidReviewResult, match="missing its WHAT evidence"):
        parse_review_result(ws.content[node.secret])


def test_an_older_review_carrying_what_evidence_is_refused():
    ws, _, _, _ = reviewed()
    node, _ = latest_review(ws)
    rewrite_payload(ws, node, review_result_version="0.3")
    with pytest.raises(InvalidReviewResult, match="cannot carry WHAT evidence"):
        parse_review_result(ws.content[node.secret])


def test_clearance_requires_the_exact_reviewed_process_questions():
    ws, _, _, _ = reviewed()
    _, review = latest_review(ws)
    _, process = latest_process(ws)
    assert what_clearance(review, process) is WhatStatus.CLEAR
    with pytest.raises(InvalidReviewResult, match="not the questions"):
        what_clearance(
            review, replace(process, product_questions=(material_question(),))
        )
    with pytest.raises(InvalidReviewResult, match="not the questions"):
        what_clearance(review, replace(process, version="0.3", product_questions=None))


def test_legacy_review_evidence_establishes_no_status():
    ws, _, _, _ = reviewed()
    make_legacy(ws)
    _, review = latest_review(ws)
    _, process = latest_process(ws)
    assert review.what_status is None and review.is_current
    assert what_clearance(review, process) is None


def test_a_pre_gate_review_of_a_question_bound_process_is_incoherent():
    """A downgraded Review cannot drop the WHAT evidence of a 0.4 Process."""
    ws, requirement, _, _ = reviewed(
        questions=[MATERIAL], question_verifications=[verify_question()]
    )
    node, review = latest_review(ws)
    ws.content[node.secret] = render_review_result(replace(review, version="0.3"))
    before = len(ws.mutations)
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is ReadyDecisionResultCode.INVALID_REVIEW_RESULT, result
    move_to_apply_in_fibery(ws, requirement)
    applied = apply_standard_requirement(ws, requirement.id)
    assert applied.code is ApplyResultCode.INVALID_REVIEW_RESULT, applied
    assert mutations_since(ws, before) == [
        f"set_requirement_state {requirement.id} Apply"
    ]


# -- F. Ready approval -----------------------------------------------------


@pytest.mark.parametrize("acknowledged", [None, *ReviewVerdict])
def test_approval_refuses_blocked_on_what_whatever_is_acknowledged(acknowledged):
    ws, requirement, _, _ = reviewed(
        questions=[MATERIAL], question_verifications=[verify_question()]
    )
    before = len(ws.mutations)
    result = approve_standard_requirement(ws, requirement.id, acknowledged)
    assert result.code is ReadyDecisionResultCode.MATERIAL_WHAT_UNRESOLVED, result
    assert MATERIAL["detail"] in result.details
    assert mutations_since(ws, before) == []
    assert ws.requirements[requirement.id].state == "Ready"


def test_approval_of_needs_work_still_needs_and_accepts_the_acknowledgement():
    ws, requirement, _, _ = reviewed(
        findings=(finding(),), finding_verifications=[confirm(severity="WARNING")]
    )
    before = len(ws.mutations)
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is ReadyDecisionResultCode.VERDICT_ACKNOWLEDGEMENT_REQUIRED
    approved = approve_standard_requirement(
        ws, requirement.id, ReviewVerdict.NEEDS_WORK
    )
    assert approved.code is ReadyDecisionResultCode.REQUIREMENT_APPROVED, approved
    assert "predates" not in approved.message
    assert only_state_transition(ws, before, requirement, "Apply")


def test_approval_refuses_a_forged_status():
    ws, requirement, _, _ = reviewed(
        questions=[MATERIAL], question_verifications=[verify_question()]
    )
    node, _ = latest_review(ws)
    rewrite_payload(ws, node, derived_what_status="CLEAR")
    before = len(ws.mutations)
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is ReadyDecisionResultCode.INVALID_REVIEW_RESULT, result
    assert mutations_since(ws, before) == []


def legacy_needs_work():
    ws, requirement, root, _ = reviewed(
        findings=(finding(),), finding_verifications=[confirm(severity="WARNING")]
    )
    make_legacy(ws)
    return ws, requirement, root


@pytest.mark.parametrize("acknowledged", [None, *ReviewVerdict])
def test_approval_of_legacy_evidence_is_refused_as_unknown(acknowledged):
    """The pre-correction warning-only approval is no longer possible."""
    ws, requirement, _, _ = reviewed()
    make_legacy(ws)
    before = len(ws.mutations)
    result = approve_standard_requirement(ws, requirement.id, acknowledged)
    assert result.code is ReadyDecisionResultCode.PRODUCT_QUESTION_EVIDENCE_REQUIRED
    assert not result.is_normal
    assert "unknown" in result.message
    assert "BLOCKED_ON_WHAT" not in result.message and result.details == ()
    assert mutations_since(ws, before) == []
    assert ws.requirements[requirement.id].state == "Ready"


@pytest.mark.parametrize("acknowledged", [None, ReviewVerdict.NEEDS_WORK])
def test_acknowledging_a_legacy_needs_work_verdict_does_not_waive_unknown(
    acknowledged,
):
    """UNKNOWN is reported first: no acknowledgement is asked for in vain."""
    ws, requirement, _ = legacy_needs_work()
    before = len(ws.mutations)
    result = approve_standard_requirement(ws, requirement.id, acknowledged)
    assert result.code is ReadyDecisionResultCode.PRODUCT_QUESTION_EVIDENCE_REQUIRED
    assert result.verdict == "NEEDS_WORK"
    assert mutations_since(ws, before) == []
    assert ws.requirements[requirement.id].state == "Ready"


def test_stale_legacy_evidence_is_refused_as_stale_first():
    ws, requirement, root, _ = reviewed()
    make_legacy(ws)
    ws.content[root.secret] += "\nA new obligation.\n"
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is ReadyDecisionResultCode.REVIEW_RESULT_STALE, result


def test_changed_normative_content_is_stale_before_the_gate_is_reached():
    ws, requirement, root, _ = reviewed()
    ws.content[root.secret] += "\nA new obligation.\n"
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is ReadyDecisionResultCode.REVIEW_RESULT_STALE, result


def test_changed_process_questions_make_the_evidence_incoherent():
    ws, requirement, _, _ = reviewed()
    node, _ = latest_process(ws)
    rewrite_payload(
        ws,
        node,
        product_questions=[
            {**MATERIAL, "authority": "HUMAN_REQUIRED", "alternatives": []}
        ],
    )
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is ReadyDecisionResultCode.INVALID_REVIEW_RESULT, result
    assert "not the questions" in " ".join(result.details)


# -- G. Apply, however State reached Apply ----------------------------------


def blocked_in_apply():
    ws, requirement, root, _ = reviewed(
        questions=[MATERIAL], question_verifications=[verify_question()]
    )
    before = move_to_apply_in_fibery(ws, requirement)
    return ws, requirement, root, before


def test_apply_refuses_a_direct_fibery_move_past_the_gate():
    ws, requirement, _, before = blocked_in_apply()
    snapshot = dict(ws.content)

    result = apply_standard_requirement(ws, requirement.id)

    assert result.code is ApplyResultCode.MATERIAL_WHAT_UNRESOLVED, result
    assert MATERIAL["detail"] in result.details
    assert mutations_since(ws, before) == [], "no relation, State or Document write"
    assert ws.content == snapshot
    assert ws.requirements[requirement.id].state == "Apply"


def test_apply_refuses_a_forged_status():
    ws, requirement, _, before = blocked_in_apply()
    node, _ = latest_review(ws)
    rewrite_payload(ws, node, derived_what_status="CLEAR")
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is ApplyResultCode.INVALID_REVIEW_RESULT, result
    assert mutations_since(ws, before) == []


def test_apply_of_a_clear_requirement_is_unchanged():
    ws, requirement, _, _ = reviewed(
        questions=[MINOR], question_verifications=[verify_question(material=False)]
    )
    assert approve_standard_requirement(ws, requirement.id).is_normal
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is ApplyResultCode.REQUIREMENT_APPLIED, result
    assert "predates" not in result.message


def test_apply_of_a_clear_needs_work_requirement_after_acknowledgement():
    ws, requirement, _, _ = reviewed(
        findings=(finding(),), finding_verifications=[confirm(severity="WARNING")]
    )
    approved = approve_standard_requirement(
        ws, requirement.id, ReviewVerdict.NEEDS_WORK
    )
    assert approved.is_normal, approved
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is ApplyResultCode.REQUIREMENT_APPLIED, result


@pytest.mark.parametrize("make", [reviewed, legacy_needs_work])
def test_apply_refuses_legacy_evidence_before_any_write(make):
    """However it reached Apply: a Fibery move, or an approval made before WI-1.

    The pre-correction warning-only application is no longer possible.
    """
    ws, requirement, *_ = make()
    make_legacy(ws)
    before = move_to_apply_in_fibery(ws, requirement)
    snapshot = dict(ws.content)

    result = apply_standard_requirement(ws, requirement.id)

    assert result.code is ApplyResultCode.PRODUCT_QUESTION_EVIDENCE_REQUIRED, result
    assert not result.is_normal
    assert "unknown" in result.message and "BLOCKED_ON_WHAT" not in result.message
    assert mutations_since(ws, before) == [], "no relation, State or Document write"
    assert ws.content == snapshot
    assert ws.requirements[requirement.id].state == "Apply"


def test_stale_legacy_evidence_in_apply_is_refused_as_stale_first():
    ws, requirement, root, _ = reviewed()
    make_legacy(ws)
    before = move_to_apply_in_fibery(ws, requirement)
    ws.content[root.secret] += "\nA new obligation.\n"
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is ApplyResultCode.REVIEW_RESULT_STALE, result
    assert mutations_since(ws, before) == []


def test_a_legacy_applied_requirement_is_preserved_untouched():
    ws, requirement, _, _ = reviewed()
    make_legacy(ws)
    ws.set_requirement_state(requirement.id, "Applied")  # applied before WI-1
    before = len(ws.mutations)
    snapshot = dict(ws.content)

    applied = apply_standard_requirement(ws, requirement.id)
    approval = approve_standard_requirement(ws, requirement.id)

    assert applied.code is ApplyResultCode.REQUIREMENT_ALREADY_APPLIED, applied
    assert approval.code is ReadyDecisionResultCode.REQUIREMENT_NOT_IN_READY
    route = select_route(ws.requirements[requirement.id], NOT_PROCESSED)
    assert route.decision is RouteDecision.NO_MACHINE_WORK
    assert mutations_since(ws, before) == [] and ws.content == snapshot
    assert ws.requirements[requirement.id].state == "Applied"
    assert latest_review(ws)[1].version == "0.3"
    assert latest_process(ws)[1].version == "0.3"


# -- the worker path, and recovery through existing lifecycle stages ---------


def review_results(ws):
    nodes = sorted(
        (
            d
            for d in ws.documents
            if d.name.startswith(f"{REQUIREMENT_ID} — Review Result")
        ),
        key=lambda d: d.name,
    )
    return [parse_review_result(ws.content[node.secret]) for node in nodes]


def runner_over(inner, requirement, status):
    """The runner's Fibery view, with the RW-C04 reset automation modelled."""
    ws = StatusWorkspace(inner, {requirement.id: status}, default=SUCCEEDED)
    workers = real_workers(
        ws,
        process_model=FakeModelRuntime([analysis_output()]),
        review_model=FakeModelRuntime([review_output()]),
    )
    return ws, workers


def requalify(ws, workers, requirement):
    """Process then Review, by the runner alone, from a reset Process cycle."""
    assert ws.status_of(requirement.id) == NOT_PROCESSED
    assert run_cycle(ws, workers).outcome is CycleOutcome.HANDED_OFF
    assert latest_process(ws)[1].version == "0.6"
    assert run_cycle(ws, workers).outcome is CycleOutcome.SUCCEEDED
    assert ws.requirements[requirement.id].state == "Ready"
    review = review_results(ws)[-1]
    assert review.version == "0.7" and review.what_status is WhatStatus.CLEAR


def test_the_worker_fails_legacy_apply_with_only_its_processing_status():
    inner, requirement, _, _ = reviewed()
    make_legacy(inner)
    ws, workers = runner_over(inner, requirement, SUCCEEDED)
    ws.set_requirement_state(requirement.id, "Apply")  # direct Fibery move
    before = len(ws.mutations)
    snapshot = dict(ws.content)

    report = run_cycle(ws, workers)

    assert report.outcome is CycleOutcome.FAILED, report
    worker_result = report.dispatch_result.worker_result
    assert worker_result.code is ApplyResultCode.PRODUCT_QUESTION_EVIDENCE_REQUIRED
    assert mutations_since(ws, before) == [
        f"set_processing_status {requirement.id} {PROCESSING}",
        f"set_processing_status {requirement.id} {FAILED_STATUS}",
    ]
    assert ws.content == snapshot
    assert ws.requirements[requirement.id].state == "Apply"


def test_a_legacy_requirement_refused_at_ready_requalifies_through_rework():
    inner, requirement, _, _ = reviewed()
    make_legacy(inner)
    legacy = dict(inner.content)
    ws, workers = runner_over(inner, requirement, SUCCEEDED)
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is ReadyDecisionResultCode.PRODUCT_QUESTION_EVIDENCE_REQUIRED

    rework = rework_standard_requirement(ws, requirement.id)
    assert rework.code is ReadyDecisionResultCode.REQUIREMENT_SENT_FOR_REWORK
    requalify(ws, workers, requirement)

    assert approve_standard_requirement(ws, requirement.id).is_normal
    assert run_cycle(ws, workers).outcome is CycleOutcome.SUCCEEDED
    assert ws.requirements[requirement.id].state == "Applied"
    assert {secret: ws.content[secret] for secret in legacy} == legacy


def test_a_legacy_requirement_refused_in_apply_requalifies_after_a_human_move():
    inner, requirement, _, _ = reviewed()
    make_legacy(inner)
    legacy = dict(inner.content)
    ws, workers = runner_over(inner, requirement, SUCCEEDED)
    ws.set_requirement_state(requirement.id, "Apply")
    assert run_cycle(ws, workers).outcome is CycleOutcome.FAILED
    assert ws.status_of(requirement.id) == FAILED_STATUS

    ws.set_requirement_state(requirement.id, "Process")  # the human, in Fibery
    assert ws.resets[-1] == (requirement.id, "Process")
    requalify(ws, workers, requirement)

    assert {secret: ws.content[secret] for secret in legacy} == legacy


# -- H. TSA admission ------------------------------------------------------


def with_second_review(scene, review_output_value=None, version=None):
    """Replace the second Requirement's Review Result, bound to its Process."""
    add_applied_requirement(scene.req)
    process = parse_process_result(scene.req.content["process-secret-40"])
    stored = parse_review_result(scene.req.content["review-secret-40"])
    review = build_review_result(
        SECOND_ID,
        1,
        stored.reviewed_document_fingerprint,
        1,
        process.output_fingerprint,
        review_output_value or ReviewOutput((), (), (), {}),
        stored.reviewed_tree,
        reviewed_product_questions=process.product_questions,
    )
    if version is not None:
        review = replace(review, version=version)
        scene.req.content["process-secret-40"] = render_process_result(
            replace(process, version=version, product_questions=None)
        )
    scene.req.content["review-secret-40"] = render_review_result(review)
    assert review_result_name(SECOND_ID, 1) in [d.name for d in scene.req.documents]


def test_admission_admits_clear_evidence():
    scene = world()
    with_second_review(scene)
    start(scene, requirement_ids=(TSA_REQUIREMENT_ID, SECOND_ID))


def test_admission_refuses_blocked_on_what_and_writes_nothing():
    scene = world()
    with_second_review(
        scene, ReviewOutput((), (), (), {}, (), (MaterialWhat("Max length?"),))
    )
    error = clean_refusal(scene, requirement_ids=(TSA_REQUIREMENT_ID, SECOND_ID))
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert "BLOCKED_ON_WHAT" in str(error) and "Max length?" in error.details


def test_admission_refuses_legacy_evidence_without_clearance():
    scene = world()
    with_second_review(scene, version="0.3")
    error = clean_refusal(scene, requirement_ids=(TSA_REQUIREMENT_ID, SECOND_ID))
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert "establishes no WHAT clearance" in str(error)
    assert "BLOCKED_ON_WHAT" not in str(error), "UNKNOWN is not a confirmed defect"


# -- historical TSAP1 evidence, offline only --------------------------------


def test_the_historical_tsap1_review_parses_and_establishes_no_clearance():
    review = parse_review_result(TSAP1_REVIEW.read_text())
    process = parse_process_result(TSAP1_PROCESS.read_text())
    assert (review.version, review.verdict) == ("0.3", ReviewVerdict.NEEDS_WORK)
    assert review.is_current and review.what_status is None
    assert process.version == "0.3" and not process.has_question_evidence
    assert what_clearance(review, process) is None


# -- the original RAW fixture for the future clean-Project test --------------


def test_the_original_raw_fixture_is_byte_exact():
    data = ORIGINAL_RAW.read_bytes()
    assert len(data) == ORIGINAL_RAW_BYTES
    assert hashlib.sha256(data).hexdigest() == ORIGINAL_RAW_SHA256


def test_a_legacy_review_of_the_same_input_never_makes_a_new_review_redundant():
    ws, requirement, _, _ = reviewed()
    node, review = latest_review(ws)
    ws.content[node.secret] = render_review_result(replace(review, version="0.3"))
    ws.set_requirement_state(requirement.id, "Review")

    result = review_standard_requirement(
        ws, FakeModelRuntime(responses=[review_output()]), requirement.id
    )

    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert result.iteration == 2 and result.model_invoked


def test_a_review_that_does_not_state_material_unresolved_what_is_refused():
    with pytest.raises(
        InvalidReviewOutput, match="must state material_unresolved_what"
    ):
        parse_review_output(json.dumps({}), (), (), ())


@pytest.mark.parametrize(
    "change",
    [
        {"material_unresolved_what": None},
        {"product_question_verifications": None},
        {"reviewed_product_questions": None},
    ],
    ids=["null material list", "null verifications", "null questions"],
)
def test_a_persisted_0_4_review_with_a_null_what_list_is_refused(change):
    ws, _, _, _ = reviewed()
    node, _ = latest_review(ws)
    rewrite_payload(ws, node, **change)
    with pytest.raises(InvalidReviewResult, match="must be a list"):
        parse_review_result(ws.content[node.secret])


@pytest.mark.parametrize(
    "change",
    [{"override": "CLEAR"}, {"reason": 42}],
    ids=["unknown key", "non-text reason"],
)
def test_a_persisted_question_verification_keeps_its_closed_shape(change):
    ws, _, _, _ = reviewed(
        questions=[MATERIAL], question_verifications=[verify_question()]
    )
    node, _ = latest_review(ws)
    payload, _, _ = payload_of(ws, node)
    [entry] = payload["product_question_verifications"]
    rewrite_payload(ws, node, product_question_verifications=[{**entry, **change}])
    with pytest.raises(InvalidReviewResult):
        parse_review_result(ws.content[node.secret])
