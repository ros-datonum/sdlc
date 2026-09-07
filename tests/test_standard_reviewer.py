"""`STANDARD Requirement + Review`: entry, execution, and what it may touch.

The hard boundary under test throughout is that Review is a verifier. It reads
the Root Document and the Process Result, writes exactly one Review Result, and
moves the workflow state. Nothing else in Fibery may change on any path.
"""

from __future__ import annotations

import pytest

from processor_fake import FakeModelRuntime
from review_fake import (
    add_process_iteration,
    build_review_workspace,
    confirm,
    finding,
    new_finding,
    reject,
    relation,
    relation_state,
    review_output,
    review_results,
    root_fingerprint,
    stored_review,
    unresolved,
    verify_relation,
)
from sdlc.results import StandardReviewResultCode as Code
from sdlc.standard_analysis import FindingKind
from sdlc.standard_review import VerificationOutcome
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import set_state

REQUIREMENT_ID = "SDLC-FR-0031"


def run(ws, requirement, responses):
    model = FakeModelRuntime(responses=responses)
    return review_standard_requirement(ws, model, requirement.id), model


def document_writes(ws, secret):
    return [m for m in ws.mutations if m == f"write_content {secret}"]


# -- entry condition --------------------------------------------------------


def test_a_standard_requirement_in_review_is_accepted():
    ws, requirement, _, _ = build_review_workspace()
    result, model = run(ws, requirement, [review_output()])
    assert result.code is Code.REQUIREMENT_REVIEWED
    assert result.is_normal
    assert model.was_invoked


@pytest.mark.parametrize("state", ["Draft", "Process", "Ready", "Apply", "Applied"])
def test_any_other_state_is_refused(state):
    ws, requirement, _, _ = build_review_workspace(state=state)
    result, model = run(ws, requirement, [review_output()])
    assert result.code is Code.REQUIREMENT_NOT_IN_REVIEW
    assert not model.was_invoked
    assert ws.mutations == []


def test_a_raw_requirement_is_refused():
    ws, requirement, _, _ = build_review_workspace(type_name="Raw")
    result, model = run(ws, requirement, [review_output()])
    assert result.code is Code.NOT_A_STANDARD_REQUIREMENT
    assert not model.was_invoked
    assert ws.mutations == []


def test_an_unknown_requirement_is_refused():
    ws, _, _, _ = build_review_workspace()
    model = FakeModelRuntime(responses=[review_output()])
    result = review_standard_requirement(ws, model, "no-such-entity")
    assert result.code is Code.REQUIREMENT_NOT_FOUND
    assert not model.was_invoked
    assert ws.mutations == []


def test_a_requirement_that_was_never_processed_is_refused():
    """There is nothing to verify without a Process Result."""
    ws, requirement, _, _ = build_review_workspace(process_iterations=0)
    result, model = run(ws, requirement, [review_output()])
    assert result.code is Code.NO_PROCESS_RESULT
    assert not model.was_invoked
    assert ws.mutations == []


def test_a_refused_entry_leaves_the_state_untouched():
    ws, requirement, _, _ = build_review_workspace(state="Ready")
    run(ws, requirement, [review_output()])
    assert ws.requirements[requirement.id].state == "Ready"


# -- the Root Document is never written -------------------------------------


@pytest.mark.parametrize(
    ("severity", "verdict"),
    [("INFO", "PASS"), ("WARNING", "NEEDS_WORK"), ("BLOCKING", "BLOCKING")],
)
def test_the_root_document_is_never_written_at_any_verdict(severity, verdict):
    ws, requirement, root, _ = build_review_workspace(findings=(finding(),))
    before = ws.content[root.secret]
    result, _ = run(
        ws,
        requirement,
        [review_output(finding_verifications=[confirm(severity=severity)])],
    )
    assert result.verdict == verdict
    assert ws.content[root.secret] == before
    assert document_writes(ws, root.secret) == []


def test_no_document_write_is_even_attempted_on_the_root():
    """Final equality is not enough: the write must never be issued."""
    ws, requirement, root, _ = build_review_workspace()
    run(ws, requirement, [review_output()])
    assert document_writes(ws, root.secret) == []


def test_the_process_result_is_never_written():
    ws, requirement, _, _ = build_review_workspace(findings=(finding(),))
    secret = "process-secret-1"
    before = ws.content[secret]
    run(ws, requirement, [review_output(finding_verifications=[confirm()])])
    assert ws.content[secret] == before
    assert document_writes(ws, secret) == []


def test_only_the_review_result_and_the_state_are_mutated():
    ws, requirement, _, _ = build_review_workspace()
    run(ws, requirement, [review_output()])
    kinds = {m.split()[0] for m in ws.mutations}
    assert kinds == {"create_child_document", "write_content", "set_requirement_state"}
    assert len([m for m in ws.mutations if m.startswith("create_child")]) == 1


# -- relations are confirmed, never written ---------------------------------


def test_no_relation_is_written_when_a_proposal_is_confirmed():
    ws, requirement, _, _ = build_review_workspace(relations=(relation(),))
    before = relation_state(ws)
    result, _ = run(
        ws, requirement, [review_output(relation_verifications=[verify_relation()])]
    )
    assert result.code is Code.REQUIREMENT_REVIEWED
    assert relation_state(ws) == before
    assert not any("depends" in m or "affects" in m for m in ws.mutations)


def test_a_confirmed_proposal_is_persisted_in_the_review_result_only():
    ws, requirement, _, _ = build_review_workspace(relations=(relation(),))
    run(ws, requirement, [review_output(relation_verifications=[verify_relation()])])
    stored = stored_review(ws)
    assert [r.requirement_id for r in stored.confirmed_relations] == ["SDLC-FR-0002"]
    assert relation_state(ws) == ({}, {})


def test_a_rejected_proposal_removes_no_existing_relation():
    """The reason deferring the write matters: rejection cannot destroy state."""
    ws, requirement, _, _ = build_review_workspace(relations=(relation(),))
    ws.depends_on_ids[requirement.id] = ["other-uuid"]
    before = relation_state(ws)
    run(
        ws,
        requirement,
        [review_output(relation_verifications=[verify_relation(outcome="REJECTED")])],
    )
    assert relation_state(ws) == before
    stored = stored_review(ws)
    assert stored.confirmed_relations == ()
    assert stored.relation_verifications[0].outcome is VerificationOutcome.REJECTED


def test_existing_relations_are_read_into_the_review_context():
    ws, requirement, _, _ = build_review_workspace()
    ws.depends_on_ids[requirement.id] = [requirement.id]
    _, model = run(ws, requirement, [review_output()])
    assert "Relations this Requirement already has" in model.calls[0]["context"]


# -- other Requirements are never touched -----------------------------------


def test_a_comparison_finding_mutates_nothing_about_the_other_requirement():
    ws, requirement, _, _ = build_review_workspace()
    before = {k: v for k, v in ws.requirements.items()}
    run(
        ws,
        requirement,
        [
            review_output(
                new_findings=[
                    {
                        "kind": "POSSIBLE_DUPLICATE",
                        "severity": "BLOCKING",
                        "requirement_id": "SDLC-FR-0002",
                        "detail": "Says the same thing.",
                    }
                ]
            )
        ],
    )
    others = {k: v for k, v in ws.requirements.items() if k != requirement.id}
    assert others == {k: v for k, v in before.items() if k != requirement.id}


# -- independence -----------------------------------------------------------


def test_the_reviewer_may_reject_a_process_finding():
    ws, requirement, _, _ = build_review_workspace(findings=(finding(),))
    result, _ = run(ws, requirement, [review_output(finding_verifications=[reject()])])
    assert result.verdict == "PASS"
    stored = stored_review(ws)
    assert stored.finding_verifications[0].outcome is VerificationOutcome.REJECTED


def test_the_reviewer_may_leave_a_process_finding_unresolved():
    ws, requirement, _, _ = build_review_workspace(findings=(finding(),))
    result, _ = run(
        ws, requirement, [review_output(finding_verifications=[unresolved()])]
    )
    assert result.verdict == "PASS"
    assert (
        stored_review(ws).finding_verifications[0].outcome
        is VerificationOutcome.UNRESOLVED
    )


def test_the_reviewer_may_discover_a_finding_process_missed():
    ws, requirement, _, _ = build_review_workspace()
    result, _ = run(
        ws,
        requirement,
        [review_output(new_findings=[new_finding(severity="BLOCKING")])],
    )
    assert result.verdict == "BLOCKING"
    stored = stored_review(ws)
    assert stored.new_findings[0].kind is FindingKind.NOT_TESTABLE


def test_the_process_result_is_presented_as_claims_to_check():
    ws, requirement, _, _ = build_review_workspace(
        findings=(finding(detail="Scope is unclear."),)
    )
    _, model = run(ws, requirement, [review_output(finding_verifications=[confirm()])])
    context = model.calls[0]["context"]
    assert "claims, not conclusions" in context
    assert "[0] AMBIGUOUS: Scope is unclear." in context


def test_a_previous_review_is_never_shown_to_the_reviewer():
    """A reviewer must not anchor on its own earlier verdict."""
    ws, requirement, root, _ = build_review_workspace()
    run(ws, requirement, [review_output()])
    # A human returns it, edits the document and Process runs again, so a
    # second review iteration runs.
    set_state(ws, requirement, "Review")
    ws.content[root.secret] = ws.content[root.secret] + "\nEdited.\n"
    add_process_iteration(ws, root, 2)
    _, model = run(ws, requirement, [review_output()])
    assert "Review Result" not in model.calls[0]["context"]
    assert "PASS" not in model.calls[0]["context"]


def test_the_reviewer_uses_its_own_role_prompt():
    ws, requirement, _, _ = build_review_workspace()
    _, model = run(ws, requirement, [review_output()])
    prompt = model.calls[0]["prompt"]
    assert "independently reviewing" in prompt
    assert "You are not that agent" in prompt
    assert "Do not state an overall verdict" in prompt


# -- context is bounded -----------------------------------------------------


def test_no_planning_artifacts_reach_the_reviewer():
    ws, requirement, _, _ = build_review_workspace()
    _, model = run(ws, requirement, [review_output()])
    context = model.calls[0]["context"]
    for term in ("Epic", "Milestone", "User Story", "Task", "Phase", "backlog"):
        assert term not in context


# -- state transition -------------------------------------------------------


@pytest.mark.parametrize(
    ("severity", "verdict"),
    [("INFO", "PASS"), ("WARNING", "NEEDS_WORK"), ("BLOCKING", "BLOCKING")],
)
def test_every_completed_review_reaches_ready(severity, verdict):
    """Ready means the review is done, not that the Requirement is good."""
    ws, requirement, _, _ = build_review_workspace(findings=(finding(),))
    result, _ = run(
        ws,
        requirement,
        [review_output(finding_verifications=[confirm(severity=severity)])],
    )
    assert result.code is Code.REQUIREMENT_REVIEWED
    assert result.verdict == verdict
    assert ws.requirements[requirement.id].state == "Ready"


def test_the_transition_is_confirmed_by_reading_the_entity_back():
    ws, requirement, _, _ = build_review_workspace()
    run(ws, requirement, [review_output()])
    reads_after_write = ws.calls[ws.calls.index("set_requirement_state") :]
    assert "read_requirement" in reads_after_write


def test_the_review_result_exists_before_the_state_moves():
    ws, requirement, _, _ = build_review_workspace()
    run(ws, requirement, [review_output()])
    created = ws.mutations.index(
        "create_child_document " + f"{REQUIREMENT_ID} — Review Result 0001"
    )
    moved = next(
        i for i, m in enumerate(ws.mutations) if m.startswith("set_requirement_state")
    )
    assert created < moved


def test_revision_is_never_changed():
    ws, requirement, _, _ = build_review_workspace()
    before = ws.requirements[requirement.id].revision
    run(ws, requirement, [review_output()])
    assert ws.requirements[requirement.id].revision == before


# -- the artifact records the reviewed state --------------------------------


def test_the_review_result_binds_to_what_was_reviewed():
    ws, requirement, root, process = build_review_workspace(process_iterations=2)
    run(ws, requirement, [review_output()])
    stored = stored_review(ws)
    assert stored.reviews(
        root_fingerprint(ws, root), process.iteration, process.output_fingerprint
    )
    assert stored.reviewed_process_iteration == 2


def test_the_latest_process_result_is_the_one_reviewed():
    ws, requirement, _, _ = build_review_workspace(process_iterations=3)
    _, _ = run(ws, requirement, [review_output()])
    assert stored_review(ws).reviewed_process_iteration == 3


def test_exactly_one_review_result_is_created():
    ws, requirement, _, _ = build_review_workspace()
    run(ws, requirement, [review_output()])
    assert len(review_results(ws)) == 1
    assert review_results(ws)[0].name == f"{REQUIREMENT_ID} — Review Result 0001"
