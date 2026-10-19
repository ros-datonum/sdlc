"""WI-2 — the evidence-bound Rework Brief (Requirement-Rework-Brief-v0.1).

A Standard Requirement sent back from Ready to Process receives the actionable
items of its latest completed Review as a code-built, non-normative Brief.
Process answers every item exactly once; the next independent Review verifies
every answer; only that Review can clear a material WHAT item, and the WI-1
gates keep their authority.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from processor_fake import FakeModelRuntime, reserialize_like_fibery
from review_fake import (
    build_review_workspace,
    confirm,
    finding,
    new_finding,
    payload_of,
    reject,
    relation,
    relation_state,
    review_output,
    rewrite_payload,
    verify_relation,
)
from sdlc.fibery_workspace import DocumentNode, FiberyError
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
from sdlc.requirement_runner import CycleOutcome, run_cycle
from sdlc.results import ApplyResultCode, ReadyDecisionResultCode
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.review_result import (
    InvalidReviewResult,
    build_rework_brief,
    parse_review_result,
    render_review_result,
    what_clearance,
)
from sdlc.rework_brief import (
    BriefCategory,
    InvalidReworkBrief,
    ReworkBrief,
    run_input_identity,
)
from sdlc.standard_analysis import (
    FindingKind,
    InvalidAnalysisOutput,
    ProductQuestion,
    RelationKind,
    ReworkExpectation,
    parse_analysis_output,
)
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_prompt import INSTRUCTIONS, REWORK_HEADING
from sdlc.standard_review import (
    InvalidReviewOutput,
    ReviewVerdict,
    WhatStatus,
    parse_review_output,
)
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import (
    analysis_output,
    build_standard_workspace,
    rendered_document,
    resolved,
)
from test_requirement_dispatcher import NOT_PROCESSED, real_workers
from test_requirement_runner import SUCCEEDED, StatusWorkspace

WHAT = {"detail": "Must an oversized valid request still succeed?", "material": True}
MINOR = {"detail": "Should the error body name the endpoint?", "material": False}
THRESHOLD = "Acceptance names no measurable threshold."
THRESHOLD_FINDING = finding(detail=THRESHOLD)


def answer(item, outcome="RESOLVED", explanation="Corrected from the source.", **kw):
    return {"item": item, "outcome": outcome, "explanation": explanation, **kw}


def verify(item, outcome="CONFIRMED", reason="Checked against the source.", **kw):
    return {"item": item, "outcome": outcome, "reason": reason, **kw}


def question(index, outcome="CONFIRMED", reason="Checked.", **fields):
    body = {"question_index": index, "outcome": outcome, "reason": reason}
    if outcome == "CONFIRMED":
        body.setdefault("material", True)
    return {**body, **fields}


def processes(ws):
    nodes = [d for d in ws.documents if "Process Result" in d.name]
    return [
        (node, parse_process_result(reserialize_like_fibery(ws.content[node.secret])))
        for node in nodes
    ]


def reviews(ws):
    nodes = [d for d in ws.documents if "Review Result" in d.name]
    return [
        (node, parse_review_result(reserialize_like_fibery(ws.content[node.secret])))
        for node in nodes
    ]


def at_ready(findings=(THRESHOLD_FINDING,), questions=(), **review):
    """Process iteration 1 and Review Result 1 done: the human is at Ready."""
    ws, requirement, root, _ = build_review_workspace(
        findings=findings,
        relations=review.pop("relations", ()),
        questions=tuple(ProductQuestion(**q) for q in questions),
    )
    if findings and "finding_verifications" not in review:
        review["finding_verifications"] = [confirm()]
    result = review_standard_requirement(
        ws, FakeModelRuntime([review_output(**review)]), requirement.id
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    return ws, requirement, root


def rework(ws, requirement, *outputs, authorized=True):
    """REWORK at Ready, then one Process run over the model's `outputs`."""
    if ws.requirements[requirement.id].state == "Ready":
        rework_standard_requirement(ws, requirement.id)
    model = FakeModelRuntime(list(outputs))
    result = process_standard_requirement(
        ws, model, requirement.id, authorized_new_cycle=authorized
    )
    return result, model


def review_again(ws, requirement, **response):
    model = FakeModelRuntime([review_output(**response)])
    return review_standard_requirement(ws, model, requirement.id), model


# -- A. the first Process: no Brief, existing behaviour ----------------------


def test_a_first_process_has_no_brief_and_no_feedback_section():
    ws, requirement, _ = build_standard_workspace()
    model = FakeModelRuntime([analysis_output()])
    result = process_standard_requirement(ws, model, requirement.id)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert REWORK_HEADING not in model.calls[0]["context"]
    _, stored = processes(ws)[-1]
    assert stored.version == "0.5" and stored.rework_brief is None
    assert stored.rework_responses == ()


def test_a_first_process_may_not_answer_feedback_it_never_received():
    ws, requirement, _ = build_standard_workspace()
    before = len(ws.mutations)
    model = FakeModelRuntime([analysis_output(rework=[resolved()])])
    result = process_standard_requirement(ws, model, requirement.id)
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert "no previous review feedback" in " ".join(result.details)
    assert ws.mutations[before:] == []


# -- B. Ready -> Process supplies the Brief ------------------------------------


def test_the_rework_receives_the_brief_in_its_own_non_normative_section():
    ws, requirement, _ = at_ready()
    result, model = rework(ws, requirement, analysis_output(rework=[resolved()]))
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    context = model.calls[0]["context"]
    normative, feedback = context.split(f"# {REWORK_HEADING}")
    assert THRESHOLD in feedback and "[R0001.F0]" in feedback
    assert "Independently reproduced." in feedback
    assert "Review Result 1" in feedback
    assert "R0001" not in normative
    _, stored = processes(ws)[-1]
    assert stored.rework_brief.source.review_iteration == 1
    assert stored.rework_brief.source.process_iteration == 1
    assert stored.rework_brief.item_refs == ("R0001.F0",)
    assert stored.rework_responses[0].item == "R0001.F0"


def test_the_brief_keeps_every_actionable_item_with_its_source():
    ws, _, _ = at_ready(
        findings=(finding(detail=THRESHOLD), finding(FindingKind.INCOMPLETE, "Lost.")),
        questions=(WHAT, MINOR),
        relations=(relation(), relation(RelationKind.AFFECTS, "SDLC-FR-0003")),
        finding_verifications=[confirm(0), reject(1)],
        relation_verifications=[
            verify_relation(),
            verify_relation("AFFECTS", "SDLC-FR-0003", "REJECTED", "No impact."),
        ],
        new_findings=[new_finding()],
        question_verifications=[
            question(0, "UNRESOLVED"),
            question(1, "REJECTED", basis="TECHNICAL_HOW"),
        ],
        material_unresolved_what=[{"detail": "What is the maximum length?"}],
    )
    (_, process), (_, review) = processes(ws)[-1], reviews(ws)[-1]

    brief = build_rework_brief(review, process)

    by_ref = {item.ref: item for item in brief.items}
    assert list(by_ref) == [
        "R0001.F0",
        "R0001.F1",
        "R0001.N0",
        "R0001.L1",
        "R0001.Q0",
        "R0001.Q1",
        "R0001.W0",
    ], "a confirmed relation is not actionable; nothing else is dropped"
    assert by_ref["R0001.F0"].severity.value == "WARNING"
    assert by_ref["R0001.F1"].outcome.value == "REJECTED"
    assert by_ref["R0001.L1"].requirement_id == "SDLC-FR-0003"
    assert brief.what_refs == {"R0001.Q0", "R0001.W0"}
    assert {item.category for item in brief.items} == set(BriefCategory) - {
        BriefCategory.REWORK_CLAIM
    }
    assert brief == build_rework_brief(review, process), "deterministic"


# -- C. an unchanged Root with new feedback is a legitimate new iteration ----


def test_an_unedited_rework_with_new_feedback_is_a_new_iteration():
    ws, requirement, _ = at_ready()
    result, model = rework(ws, requirement, analysis_output(rework=[resolved()]))
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED and result.iteration == 2
    assert len(model.calls) == 1


def test_an_ordinary_call_keeps_the_cr_002_no_change_behaviour():
    ws, requirement, _ = at_ready()
    result, model = rework(ws, requirement, analysis_output(), authorized=False)
    assert result.code is ProcessCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked


# -- D and E. exactly one response per Brief item ------------------------------


TWO_ITEMS = {
    "findings": (finding(detail=THRESHOLD), finding(FindingKind.INCOMPLETE, "Lost.")),
    "finding_verifications": [confirm(0), confirm(1)],
}


def test_every_item_is_answered_exactly_once_and_persisted():
    ws, requirement, _ = at_ready(**TWO_ITEMS)
    responses = [answer("R0001.F1", "REBUTTED", "The RAW keeps it."), resolved()]
    result, _ = rework(ws, requirement, analysis_output(rework=responses))
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    _, stored = processes(ws)[-1]
    assert [r.item for r in stored.rework_responses] == ["R0001.F1", "R0001.F0"]
    assert stored.rework_responses[0].explanation == "The RAW keeps it."


@pytest.mark.parametrize(
    "responses, message",
    [
        ([resolved()], "unanswered: R0001.F1"),
        ([resolved(), resolved(), resolved("R0001.F1")], "more than once"),
        ([resolved(), resolved("R0001.F1"), resolved("R0001.F9")], "answers no"),
        ([resolved(), answer("R0001.F1", explanation=" ")], "non-empty"),
        ([resolved(), answer("R0001.F1", "DONE")], "expected one of"),
        ([{"outcome": "RESOLVED", "explanation": "All of them were fixed."}], "item"),
        ([resolved(), answer("R0001.F1", product_question_index=0)], "only ESCALATED"),
    ],
    ids=["missing", "duplicate", "invented", "empty", "bad-outcome", "blanket", "pqi"],
)
def test_a_response_list_that_does_not_cover_the_brief_is_refused(responses, message):
    ws, requirement, _ = at_ready(**TWO_ITEMS)
    rework_standard_requirement(ws, requirement.id)
    before = len(ws.mutations)
    model = FakeModelRuntime([analysis_output(rework=responses)])
    result = process_standard_requirement(
        ws, model, requirement.id, authorized_new_cycle=True
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert message in " ".join(result.details)
    assert ws.mutations[before:] == [], "no Process Result, Root or State write"
    assert len(processes(ws)) == 1


def test_omitting_the_responses_answers_nothing():
    ws, requirement, _ = at_ready()
    rework_standard_requirement(ws, requirement.id)
    body = json.loads(analysis_output())
    del body["rework_responses"]
    result = process_standard_requirement(
        ws,
        FakeModelRuntime([json.dumps(body)]),
        requirement.id,
        authorized_new_cycle=True,
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "its absence answers none" in " ".join(result.details)


@pytest.mark.parametrize(
    "response, questions, message",
    [
        (answer("R0001.W0", "ESCALATED"), [], "must name the product question"),
        (
            answer("R0001.W0", "ESCALATED", product_question_index=0),
            [MINOR],
            "is not material",
        ),
        (
            answer("R0001.W0", "ESCALATED", product_question_index=3),
            [WHAT],
            "but the output has 1",
        ),
    ],
)
def test_escalating_a_material_what_item_must_keep_it_a_material_question(
    response, questions, message
):
    expectation = ReworkExpectation(("R0001.W0",), frozenset({"R0001.W0"}))
    with pytest.raises(InvalidAnalysisOutput, match=message):
        parse_analysis_output(
            analysis_output(rework=[response], questions=questions), expectation
        )


# -- F, G, H. the next Review verifies every response --------------------------


def reworked(*responses, findings=(THRESHOLD_FINDING,), **review):
    ws, requirement, root = at_ready(findings=findings, **review)
    result, _ = rework(
        ws, requirement, analysis_output(rework=list(responses or [resolved()]))
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    return ws, requirement, root


def test_the_reviewer_rejects_an_incorrect_resolved_claim():
    ws, requirement, _ = reworked()
    result, model = review_again(
        ws,
        requirement,
        rework_verifications=[verify("R0001.F0", "REJECTED", severity="WARNING")],
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert result.verdict == "NEEDS_WORK", "a remaining defect counts"
    context = model.calls[0]["context"]
    assert "[R0001.F0]" in context and "Answer: RESOLVED" in context
    _, review = reviews(ws)[-1]
    assert review.version == "0.5" and review.what_status is WhatStatus.CLEAR


def test_a_rejected_claim_is_carried_into_the_next_brief():
    ws, requirement, _ = reworked()
    review_again(
        ws,
        requirement,
        rework_verifications=[verify("R0001.F0", "REJECTED", severity="WARNING")],
    )
    (_, process), (_, review) = processes(ws)[-1], reviews(ws)[-1]
    [claim] = build_rework_brief(review, process).items
    assert claim.ref == "R0002.C0" and claim.category is BriefCategory.REWORK_CLAIM
    assert THRESHOLD in claim.detail and "answered RESOLVED" in claim.detail


def test_the_reviewer_confirms_a_justified_rebuttal():
    ws, requirement, _ = reworked(answer("R0001.F0", "REBUTTED", "The RAW says so."))
    result, _ = review_again(ws, requirement, rework_verifications=[verify("R0001.F0")])
    assert result.verdict == "PASS", result
    _, review = reviews(ws)[-1]
    assert review.what_status is WhatStatus.CLEAR


@pytest.mark.parametrize(
    "rework_verifications, message",
    [
        (None, "its absence verifies none"),
        ([], "unverified: rework response R0001.F0"),
        ([verify("R0001.F0"), verify("R0001.F0")], "more than once"),
        ([verify("R0001.F0"), verify("R0001.F7")], "did not claim"),
        ([verify("R0001.F0", "REJECTED")], "severity must be graded"),
        ([verify("R0001.F0", severity="INFO")], "must not carry a severity"),
    ],
)
def test_a_review_that_does_not_verify_each_response_once_is_refused(
    rework_verifications, message
):
    ws, requirement, _ = reworked()
    body = json.loads(review_output(rework_verifications=rework_verifications or []))
    if rework_verifications is None:
        del body["rework_verifications"]
    before = len(ws.mutations)
    result = review_standard_requirement(
        ws, FakeModelRuntime([json.dumps(body)]), requirement.id
    )
    assert result.code is ReviewCode.INVALID_MODEL_OUTPUT, result
    assert message in " ".join(result.details)
    assert ws.mutations[before:] == []


def what_reworked(*responses, questions=()):
    """Review 1 found one material WHAT question; Process 2 answered it."""
    ws, requirement, _ = at_ready(
        findings=(), material_unresolved_what=[{"detail": "Maximum length?"}]
    )
    result, _ = rework(
        ws, requirement, analysis_output(rework=list(responses), questions=questions)
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    return ws, requirement


def test_an_escalated_material_what_stays_blocked():
    ws, requirement = what_reworked(
        answer("R0001.W0", "ESCALATED", "No source.", product_question_index=0),
        questions=[WHAT],
    )
    review_again(
        ws,
        requirement,
        rework_verifications=[verify("R0001.W0")],
        question_verifications=[question(0)],
    )
    _, review = reviews(ws)[-1]
    assert review.what_status is WhatStatus.BLOCKED_ON_WHAT
    refused = approve_standard_requirement(ws, requirement.id, ReviewVerdict.PASS)
    assert refused.code is ReadyDecisionResultCode.MATERIAL_WHAT_UNRESOLVED


@pytest.mark.parametrize("outcome", ["REJECTED", "UNRESOLVED"])
def test_a_resolved_claim_cannot_clear_a_material_what(outcome):
    """Q: only a confirmed resolution clears it; WI-1 gates keep authority."""
    ws, requirement = what_reworked(answer("R0001.W0", "RESOLVED", "Now stated."))
    severity = {"severity": "BLOCKING"} if outcome == "REJECTED" else {}
    review_again(
        ws, requirement, rework_verifications=[verify("R0001.W0", outcome, **severity)]
    )
    (_, process), (_, review) = processes(ws)[-1], reviews(ws)[-1]
    assert review.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert what_clearance(review, process) is WhatStatus.BLOCKED_ON_WHAT
    approval = approve_standard_requirement(ws, requirement.id, ReviewVerdict.BLOCKING)
    assert approval.code is ReadyDecisionResultCode.MATERIAL_WHAT_UNRESOLVED
    assert "R0001.W0: Now stated." in approval.details
    ws.set_requirement_state(requirement.id, "Apply")  # a direct Fibery move
    applied = apply_standard_requirement(ws, requirement.id)
    assert applied.code is ApplyResultCode.MATERIAL_WHAT_UNRESOLVED


def test_only_a_confirmed_resolution_clears_a_material_what():
    ws, requirement = what_reworked(answer("R0001.W0", "RESOLVED", "Now stated."))
    review_again(ws, requirement, rework_verifications=[verify("R0001.W0")])
    _, review = reviews(ws)[-1]
    assert review.what_status is WhatStatus.CLEAR
    assert approve_standard_requirement(ws, requirement.id).is_normal


# -- I and J. source authority and contradictions ------------------------------


def test_the_process_instructions_keep_the_brief_non_normative():
    for rule in (
        "It is feedback, not Requirement truth and not source",
        "Do not add\n  product behavior, invent business or product decisions",
        '"everything resolved" is not an answer',
        "Never drop\n  a genuinely open material question",
    ):
        assert rule in INSTRUCTIONS


def test_a_contradiction_introduced_by_rework_is_found_by_the_review():
    ws, requirement, _ = reworked()
    result, model = review_again(
        ws,
        requirement,
        rework_verifications=[verify("R0001.F0", "REJECTED", severity="BLOCKING")],
        new_findings=[
            new_finding(
                "INCONSISTENT", "BLOCKING", "The threshold contradicts the RAW."
            )
        ],
    )
    assert result.verdict == "BLOCKING"
    assert "Do your own full\n  review" in model.calls[0]["prompt"]


def test_the_reviewer_never_sees_the_previous_review_result():
    ws, requirement, _ = reworked()
    _, model = review_again(ws, requirement, rework_verifications=[verify("R0001.F0")])
    context = model.calls[0]["context"]
    assert "Independently reproduced." not in context, "earlier reason not sent"
    item = context.split("[R0001.F0]")[1].split("\n#")[0]
    assert "severity" not in item and "review outcome" not in item
    assert "derived_verdict" not in context and "NEEDS_WORK" not in item


# -- K. historical Review feedback ---------------------------------------------


def make_legacy(ws):
    (pnode, process), (rnode, review) = processes(ws)[-1], reviews(ws)[-1]
    ws.content[pnode.secret] = render_process_result(
        replace(process, version="0.3", product_questions=None)
    )
    ws.content[rnode.secret] = render_review_result(replace(review, version="0.3"))


def test_a_historical_review_is_feedback_but_never_what_clearance():
    ws, requirement, _ = at_ready()
    make_legacy(ws)
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is ReadyDecisionResultCode.PRODUCT_QUESTION_EVIDENCE_REQUIRED
    result, _ = rework(ws, requirement, analysis_output(rework=[resolved()]))
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    _, stored = processes(ws)[-1]
    assert stored.rework_brief.source.review_version == "0.3"
    assert stored.rework_brief.what_refs == frozenset()
    assert stored.has_question_evidence, "the new iteration is WI-1 evidence"
    review_again(ws, requirement, rework_verifications=[verify("R0001.F0")])
    _, review = reviews(ws)[-1]
    assert review.version == "0.5" and review.what_status is WhatStatus.CLEAR


# -- L. lineage refusals --------------------------------------------------------


def add_review_copy(ws, number, **payload_changes):
    node, _ = reviews(ws)[0]
    copy = DocumentNode(
        id=f"review-copy-{number}",
        name=node.name.replace("0001", f"{number:04d}"),
        folder_id=None,
        entity_public_id=None,
        secret=f"review-copy-secret-{number}",
        parent_document_id=node.parent_document_id,
    )
    ws.documents.append(copy)
    ws.content[copy.secret] = ws.content[node.secret]
    rewrite_payload(ws, copy, **payload_changes)


@pytest.mark.parametrize(
    "corrupt, detail",
    [
        (
            lambda ws: rewrite_payload(
                ws, reviews(ws)[0][0], reviewed_process_iteration=7
            ),
            "not a persisted Process Result",
        ),
        (
            lambda ws: rewrite_payload(
                ws, reviews(ws)[0][0], reviewed_process_output_fingerprint="moved"
            ),
            "not a persisted Process Result",
        ),
        (
            lambda ws: ws.content.__setitem__(reviews(ws)[0][0].secret, "# garbage\n"),
            "cannot be read",
        ),
        (lambda ws: add_review_copy(ws, 1), "more than one Review Result"),
        (lambda ws: add_review_copy(ws, 2, iteration=2), "already reviewed"),
        (
            lambda ws: rewrite_payload(
                ws,
                reviews(ws)[0][0],
                process_finding_verifications=[{**confirm(5), "severity": "WARNING"}],
            ),
            "not coherent",
        ),
        (
            lambda ws: rewrite_payload(
                ws,
                reviews(ws)[0][0],
                process_finding_verifications=[confirm(reason="")],
            ),
            "feedback is empty",
        ),
        (
            lambda ws: rewrite_payload(
                ws, reviews(ws)[0][0], assessment={"clarity": " "}
            ),
            "assessment is malformed",
        ),
    ],
    ids=[
        "no-process",
        "other-output",
        "malformed",
        "duplicate",
        "twice",
        "index",
        "empty-reason",
        "blank-assessment",
    ],
)
def test_an_invalid_review_lineage_refuses_before_any_model_call(corrupt, detail):
    ws, requirement, _ = at_ready()
    corrupt(ws)
    rework_standard_requirement(ws, requirement.id)
    before = len(ws.mutations)
    result, model = rework(ws, requirement, analysis_output(rework=[resolved()]))
    assert result.code is ProcessCode.REVIEW_LINEAGE_INVALID, result
    assert detail in " ".join(result.details)
    assert not model.was_invoked
    assert ws.mutations[before:] == []


# -- M, N, P. recovery keeps the Brief it was produced with --------------------


def failing_root_write(ws, root):
    original = ws.write_document_content

    def write(secret, markdown):
        if secret == root.secret:
            ws.write_document_content = original
            raise FiberyError("Root write failed")
        return original(secret, markdown)

    ws.write_document_content = write


def partially_reworked():
    """Process Result 2 persisted with its Brief; the Root rewrite failed."""
    ws, requirement, root = at_ready()
    rework_standard_requirement(ws, requirement.id)
    failing_root_write(ws, root)
    output = analysis_output(
        rework=[resolved()], normalized_changes={"acceptance_verification": "p95 < 2s."}
    )
    result, _ = rework(ws, requirement, output)
    assert result.code is ProcessCode.PARTIAL_PROCESSING, result
    node, stored = processes(ws)[-1]
    assert stored.iteration == 2 and stored.rework_brief is not None
    return ws, requirement, node, stored


def test_a_resume_replays_the_persisted_brief_without_the_model():
    ws, requirement, node, stored = partially_reworked()
    model = FakeModelRuntime()
    result = process_standard_requirement(
        ws, model, requirement.id, resume_result=node.id
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert not model.was_invoked
    _, after = processes(ws)[-1]
    assert after.brief_identity == stored.brief_identity
    assert ws.requirements[requirement.id].state == "Review"


def test_a_resume_refuses_when_the_source_review_changed():
    ws, requirement, node, _ = partially_reworked()
    review_node, _ = reviews(ws)[0]
    rewrite_payload(
        ws, review_node, process_finding_verifications=[confirm(reason="Edited later.")]
    )
    before = len(ws.mutations)
    model = FakeModelRuntime()
    result = process_standard_requirement(
        ws, model, requirement.id, resume_result=node.id
    )
    assert result.code is ProcessCode.PROCESSING_STATE_CONFLICT, result
    assert "no longer gives" in result.message
    assert not model.was_invoked and ws.mutations[before:] == []


def test_a_review_changed_while_the_model_ran_is_not_persisted():
    ws, requirement, _ = at_ready()
    rework_standard_requirement(ws, requirement.id)
    review_node, _ = reviews(ws)[0]

    class EditingModel(FakeModelRuntime):
        def run(self, prompt, context=""):
            rewrite_payload(
                ws, review_node, process_finding_verifications=[confirm(reason="New.")]
            )
            return super().run(prompt, context)

    model = EditingModel([analysis_output(rework=[resolved()])])
    result = process_standard_requirement(
        ws, model, requirement.id, authorized_new_cycle=True
    )
    assert result.code is ProcessCode.PROCESSING_STATE_CONFLICT, result
    assert len(processes(ws)) == 1


def test_an_empty_shell_is_completed_with_the_same_brief():
    """An edited rework, so the shell is reachable: over an unchanged tree an
    ordinary call reports no changes first, as it did before WI-2."""
    ws, requirement, root = at_ready()
    rework_standard_requirement(ws, requirement.id)
    ws.content[root.secret] += "\nThe human narrowed the scope.\n"
    original = ws.write_document_content

    def body_write_fails(secret, markdown):
        if secret != root.secret:
            ws.write_document_content = original
            raise FiberyError("Body write failed")
        return original(secret, markdown)

    ws.write_document_content = body_write_fails
    failed, _ = rework(ws, requirement, analysis_output(rework=[resolved()]))
    assert failed.code is ProcessCode.PARTIAL_PROCESSING, failed
    [shell] = [d for d in ws.documents if d.name.endswith("Process Result 0002")]
    assert ws.content.get(shell.secret, "") == ""
    model = FakeModelRuntime([analysis_output(rework=[resolved()])])
    result = process_standard_requirement(
        ws, model, requirement.id, recover_empty_result=shell.id
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert "[R0001.F0]" in model.calls[0]["context"]
    _, stored = processes(ws)[-1]
    assert stored.iteration == 2 and stored.rework_brief.item_refs == ("R0001.F0",)


def test_a_failed_state_write_keeps_the_durable_brief_bound_result():
    ws, requirement, _ = at_ready()
    rework_standard_requirement(ws, requirement.id)
    ws.failures["set_requirement_state"] = FiberyError("State write failed")
    result, _ = rework(ws, requirement, analysis_output(rework=[resolved()]))
    assert result.code is ProcessCode.PARTIAL_PROCESSING, result
    _, stored = processes(ws)[-1]
    assert stored.iteration == 2 and stored.rework_brief.item_refs == ("R0001.F0",)
    assert stored.rework_responses[0].item == "R0001.F0"


# -- O. the same run input never calls the model twice --------------------------


def test_an_exactly_repeated_run_input_makes_no_model_call():
    ws, requirement, root = build_standard_workspace()
    ws.content[root.secret] = rendered_document()  # Process is a fixpoint here
    first = process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), requirement.id
    )
    assert first.code is ProcessCode.REQUIREMENT_PROCESSED
    _, stored = processes(ws)[-1]
    assert stored.input_tree == stored.output_tree
    ws.set_requirement_state(requirement.id, "Process")  # Review -> Process, unreviewed
    before = len(ws.mutations)
    model = FakeModelRuntime([analysis_output()])
    again = process_standard_requirement(
        ws, model, requirement.id, authorized_new_cycle=True
    )
    assert again.code is ProcessCode.NO_CHANGES_TO_PROCESS, again
    assert "same normative input and review feedback" in again.message
    assert not model.was_invoked and ws.mutations[before:] == []
    assert stored.run_input_identity == run_input_identity(
        stored.input_tree.fingerprint, None
    )


def test_new_feedback_over_the_same_tree_is_a_different_run_input():
    ws, requirement, root = build_standard_workspace()
    ws.content[root.secret] = rendered_document()
    process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), requirement.id
    )
    review_standard_requirement(
        ws,
        FakeModelRuntime([review_output(new_findings=[new_finding()])]),
        requirement.id,
    )
    result, model = rework(
        ws, requirement, analysis_output(rework=[resolved("R0001.N0")])
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED and len(model.calls) == 1


# -- persisted-evidence integrity ------------------------------------------------


def test_a_tampered_brief_or_run_identity_is_refused_on_read():
    ws, _, _ = reworked()
    node, _ = processes(ws)[-1]
    payload, _, _ = payload_of(ws, node)
    payload["rework_brief"]["items"][0]["detail"] = "Something the review never said."
    rewrite_payload(ws, node, rework_brief=payload["rework_brief"])
    with pytest.raises(InvalidProcessResult, match="identity does not match"):
        parse_process_result(ws.content[node.secret])


def test_a_brief_whose_content_changed_does_not_keep_its_identity():
    ws, _, _ = reworked()
    _, stored = processes(ws)[-1]
    payload = stored.rework_brief.to_payload()
    payload["items"][0]["feedback"] = "A reason the review never gave."
    with pytest.raises(InvalidReworkBrief, match="identity does not match its content"):
        ReworkBrief.from_payload(payload)


def test_a_persisted_review_must_verify_each_reviewed_response_once():
    ws, requirement, _ = reworked()
    review_again(ws, requirement, rework_verifications=[verify("R0001.F0")])
    node, _ = reviews(ws)[-1]
    rewrite_payload(ws, node, rework_verifications=[])
    with pytest.raises(InvalidReviewResult, match="exactly once"):
        parse_review_result(ws.content[node.secret])


def test_a_confirmed_response_is_not_carried_into_the_next_brief():
    ws, requirement, _ = reworked()
    review_again(ws, requirement, rework_verifications=[verify("R0001.F0")])
    (_, process), (_, review) = processes(ws)[-1], reviews(ws)[-1]
    assert build_rework_brief(review, process).items == ()


def test_a_tampered_run_input_identity_is_refused_on_read():
    ws, _, _ = reworked()
    node, _ = processes(ws)[-1]
    rewrite_payload(ws, node, run_input_identity="0" * 64)
    with pytest.raises(InvalidProcessResult, match="run_input_identity"):
        parse_process_result(ws.content[node.secret])


def test_persisted_responses_are_held_to_the_same_coverage():
    ws, _, _ = reworked()
    node, _ = processes(ws)[-1]
    rewrite_payload(ws, node, rework_responses=[])
    with pytest.raises(InvalidProcessResult, match="unanswered: R0001.F0"):
        parse_process_result(ws.content[node.secret])


def test_an_older_process_result_cannot_carry_rework_evidence():
    ws, _, _ = reworked()
    node, _ = processes(ws)[-1]
    rewrite_payload(ws, node, process_result_version="0.4")
    with pytest.raises(InvalidProcessResult, match="cannot carry rework evidence"):
        parse_process_result(ws.content[node.secret])


def test_a_brief_item_out_of_its_category_shape_is_refused():
    ws, _, _ = reworked()
    _, stored = processes(ws)[-1]
    payload = stored.rework_brief.to_payload()
    payload["items"][0]["blocks_what"] = True
    with pytest.raises(InvalidReworkBrief, match="shape its category"):
        ReworkBrief.from_payload(payload)


def test_a_downgraded_review_of_a_rework_bound_process_is_incoherent():
    ws, requirement, _ = reworked()
    review_again(ws, requirement, rework_verifications=[verify("R0001.F0")])
    (_, process), (_, review) = processes(ws)[-1], reviews(ws)[-1]
    downgraded = replace(
        review,
        version="0.4",
        reviewed_brief_identity=None,
        reviewed_rework_responses=(),
        rework_verifications=(),
    )
    reread = parse_review_result(render_review_result(downgraded))
    with pytest.raises(InvalidReviewResult, match="carries no rework evidence"):
        what_clearance(reread, process)


def test_a_review_of_other_rework_responses_is_incoherent():
    ws, requirement, _ = reworked()
    review_again(ws, requirement, rework_verifications=[verify("R0001.F0")])
    (_, process), (node, _) = processes(ws)[-1], reviews(ws)[-1]
    payload, _, _ = payload_of(ws, node)
    payload["reviewed_rework_responses"][0]["explanation"] = "Something else."
    rewrite_payload(
        ws, node, reviewed_rework_responses=payload["reviewed_rework_responses"]
    )
    with pytest.raises(InvalidReviewResult, match="not those of Process Result"):
        what_clearance(parse_review_result(ws.content[node.secret]), process)


def test_a_forged_clear_over_an_open_what_item_is_refused_on_read():
    ws, requirement = what_reworked(answer("R0001.W0", "RESOLVED", "Now stated."))
    review_again(
        ws,
        requirement,
        rework_verifications=[verify("R0001.W0", "UNRESOLVED")],
    )
    node, _ = reviews(ws)[-1]
    rewrite_payload(ws, node, derived_what_status="CLEAR")
    with pytest.raises(InvalidReviewResult, match="contradicts the verified"):
        parse_review_result(ws.content[node.secret])


def test_a_review_of_a_process_without_a_brief_verifies_no_rework():
    with pytest.raises(InvalidReviewOutput, match="received no Rework Brief"):
        parse_review_output(
            review_output(rework_verifications=[verify("R0001.F0")]), (), (), ()
        )


# -- R. a Review never becomes normative content ---------------------------------


def test_review_feedback_never_enters_the_root_or_the_normative_tree():
    ws, _, root = reworked()
    root_text = ws.content[root.secret]
    assert "Independently reproduced." not in root_text
    assert "R0001" not in root_text
    _, stored = processes(ws)[-1]
    names = {entry.name for entry in stored.output_tree.entries}
    assert not any("Review Result" in name for name in names)
    assert not any("Process Result" in name for name in names)


# -- 14. offline end-to-end: incomplete -> review -> rework -> corrected ---------


def test_the_complete_rework_loop_offline():
    """Process 1 -> Review 1 -> REWORK -> Process 2 with the Brief -> Review 2.

    The runner and the real workers drive every machine step; the human only
    sends the Requirement back. Exactly one model call per new iteration, no
    automatic Ready decision, history preserved, no relation written.
    """
    inner, requirement, root = build_standard_workspace()
    ws = StatusWorkspace(inner, {requirement.id: NOT_PROCESSED}, default=SUCCEEDED)
    process_model = FakeModelRuntime(
        [
            analysis_output(
                normalized_changes={"acceptance_verification": "Requests are fast."},
                findings=[{"kind": "NOT_TESTABLE", "detail": THRESHOLD}],
            ),
            analysis_output(
                normalized_changes={
                    "acceptance_verification": "The RAW's 2 s limit holds at p95."
                },
                rework=[resolved(explanation="Took the 2 s limit from the RAW.")],
            ),
        ]
    )
    review_model = FakeModelRuntime(
        [
            review_output(finding_verifications=[confirm()]),
            review_output(rework_verifications=[verify("R0001.F0")]),
        ]
    )
    workers = real_workers(ws, process_model=process_model, review_model=review_model)
    relations_before = relation_state(inner)
    states = []

    def cycle(expected):
        report = run_cycle(ws, workers)
        assert report.outcome is expected, report
        states.append(inner.requirements[requirement.id].state)

    cycle(CycleOutcome.HANDED_OFF)  # Process 1
    cycle(CycleOutcome.SUCCEEDED)  # Review 1
    cycle(CycleOutcome.IDLE)  # Ready: nothing decides for the human
    first = {node.secret: inner.content[node.secret] for node, _ in processes(inner)}
    first |= {node.secret: inner.content[node.secret] for node, _ in reviews(inner)}
    assert reviews(inner)[-1][1].verdict is ReviewVerdict.NEEDS_WORK

    rework_standard_requirement(ws, requirement.id)  # the human's decision
    cycle(CycleOutcome.HANDED_OFF)  # Process 2, with the Brief
    cycle(CycleOutcome.SUCCEEDED)  # Review 2
    cycle(CycleOutcome.IDLE)

    assert len(process_model.calls) == 2 and len(review_model.calls) == 2
    assert REWORK_HEADING not in process_model.calls[0]["context"]
    assert THRESHOLD in process_model.calls[1]["context"].split(REWORK_HEADING)[1]
    _, review = reviews(inner)[-1]
    assert review.iteration == 2 and review.verdict is ReviewVerdict.PASS
    assert review.what_status is WhatStatus.CLEAR
    assert "The RAW's 2 s limit holds at p95." in inner.content[root.secret]
    assert {secret: inner.content[secret] for secret in first} == first
    assert states == ["Review", "Ready", "Ready", "Review", "Ready", "Ready"]
    assert set(states) <= {"Process", "Review", "Ready"}
    assert relation_state(inner) == relations_before
