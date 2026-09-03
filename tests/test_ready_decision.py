"""`STANDARD Requirement + Ready Decision`: entry, verdict authority, mutation boundary.

The hard boundary under test is that a decision writes one thing, the workflow
State, and only after every check has passed. Nothing else in Fibery may
change on any path, including refusals and idempotent retries.
"""

from __future__ import annotations

import inspect

import pytest

from ready_fake import (
    REQUIREMENT_ID,
    build_ready_workspace,
    document_snapshot,
    mutations_since,
    only_state_transition,
)
from review_fake import relation_state
from sdlc.fibery_workspace import FiberyError, RequirementRecord
from sdlc.ready_decision import (
    approve_standard_requirement,
    rework_standard_requirement,
)
from sdlc.results import ReadyDecisionResultCode as Code
from sdlc.standard_review import ReviewVerdict
from standard_fake import set_state

PASS = ReviewVerdict.PASS
NEEDS_WORK = ReviewVerdict.NEEDS_WORK
BLOCKING = ReviewVerdict.BLOCKING


def approve(ws, requirement, acknowledged=None):
    return approve_standard_requirement(ws, requirement.id, acknowledged)


def rework(ws, requirement):
    return rework_standard_requirement(ws, requirement.id)


def state_of(ws, requirement):
    return ws.requirements[requirement.id].state


# -- entry ------------------------------------------------------------------


def test_an_unknown_requirement_is_refused():
    ws, _, _, before = build_ready_workspace()
    result = approve_standard_requirement(ws, "no-such-entity")
    assert result.code is Code.REQUIREMENT_NOT_FOUND
    assert mutations_since(ws, before) == []


def test_a_raw_requirement_is_refused_by_both_decisions():
    ws, _, _, before = build_ready_workspace()
    raw = next(r for r in ws.requirements.values() if r.type_name == "Raw")
    set_state(ws, raw, "Ready")
    assert approve_standard_requirement(ws, raw.id).code is (
        Code.NOT_A_STANDARD_REQUIREMENT
    )
    assert rework_standard_requirement(ws, raw.id).code is (
        Code.NOT_A_STANDARD_REQUIREMENT
    )
    assert mutations_since(ws, before) == []


@pytest.mark.parametrize("state", ["Draft", "Process", "Review", "Applied"])
def test_approve_refuses_any_state_but_ready(state):
    ws, requirement, _, before = build_ready_workspace()
    set_state(ws, requirement, state)
    result = approve(ws, requirement)
    assert result.code is Code.REQUIREMENT_NOT_IN_READY
    assert state_of(ws, requirement) == state
    assert mutations_since(ws, before) == []


@pytest.mark.parametrize("state", ["Draft", "Review", "Apply", "Applied"])
def test_rework_refuses_any_state_but_ready(state):
    ws, requirement, _, before = build_ready_workspace()
    set_state(ws, requirement, state)
    result = rework(ws, requirement)
    assert result.code is Code.REQUIREMENT_NOT_IN_READY
    assert state_of(ws, requirement) == state
    assert mutations_since(ws, before) == []


def test_a_fibery_read_failure_is_reported_without_mutation():
    ws, requirement, _, before = build_ready_workspace()
    ws.failures["read_requirement"] = FiberyError("connection reset")
    result = approve(ws, requirement)
    assert result.code is Code.FIBERY_READ_FAILED
    assert "connection reset" in result.details
    assert mutations_since(ws, before) == []


# -- APPROVE at PASS --------------------------------------------------------


def test_pass_is_approved_without_acknowledgement():
    ws, requirement, _, before = build_ready_workspace("PASS")
    result = approve(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPROVED
    assert result.is_normal
    assert result.verdict == "PASS"
    assert state_of(ws, requirement) == "Apply"
    assert only_state_transition(ws, before, requirement, "Apply")


def test_pass_may_be_acknowledged_as_pass():
    ws, requirement, _, before = build_ready_workspace("PASS")
    result = approve(ws, requirement, PASS)
    assert result.code is Code.REQUIREMENT_APPROVED
    assert only_state_transition(ws, before, requirement, "Apply")


@pytest.mark.parametrize("acknowledged", [NEEDS_WORK, BLOCKING])
def test_pass_refuses_an_acknowledgement_of_another_verdict(acknowledged):
    ws, requirement, _, before = build_ready_workspace("PASS")
    result = approve(ws, requirement, acknowledged)
    assert result.code is Code.INVALID_VERDICT_ACKNOWLEDGEMENT
    assert not result.is_normal
    assert state_of(ws, requirement) == "Ready"
    assert mutations_since(ws, before) == []


# -- APPROVE at NEEDS_WORK --------------------------------------------------


def test_needs_work_requires_an_acknowledgement():
    ws, requirement, _, before = build_ready_workspace("NEEDS_WORK")
    result = approve(ws, requirement)
    assert result.code is Code.VERDICT_ACKNOWLEDGEMENT_REQUIRED
    assert result.verdict == "NEEDS_WORK"
    assert result.warnings
    assert state_of(ws, requirement) == "Ready"
    assert mutations_since(ws, before) == []


def test_needs_work_is_approved_when_acknowledged_by_name():
    ws, requirement, _, before = build_ready_workspace("NEEDS_WORK")
    result = approve(ws, requirement, NEEDS_WORK)
    assert result.code is Code.REQUIREMENT_APPROVED
    assert state_of(ws, requirement) == "Apply"
    assert only_state_transition(ws, before, requirement, "Apply")


@pytest.mark.parametrize("acknowledged", [BLOCKING, PASS])
def test_needs_work_refuses_the_wrong_acknowledgement(acknowledged):
    ws, requirement, _, before = build_ready_workspace("NEEDS_WORK")
    result = approve(ws, requirement, acknowledged)
    assert result.code is Code.VERDICT_ACKNOWLEDGEMENT_MISMATCH
    assert state_of(ws, requirement) == "Ready"
    assert mutations_since(ws, before) == []


# -- APPROVE at BLOCKING ----------------------------------------------------


def test_blocking_requires_an_acknowledgement_and_shows_the_findings():
    ws, requirement, _, before = build_ready_workspace("BLOCKING")
    result = approve(ws, requirement)
    assert result.code is Code.VERDICT_ACKNOWLEDGEMENT_REQUIRED
    assert result.verdict == "BLOCKING"
    assert result.blocking
    assert "BLOCKING" in result.message
    assert state_of(ws, requirement) == "Ready"
    assert mutations_since(ws, before) == []


def test_blocking_is_approved_when_acknowledged_by_name():
    """The human is the final authority; Review is not a quality gate."""
    ws, requirement, _, before = build_ready_workspace("BLOCKING")
    result = approve(ws, requirement, BLOCKING)
    assert result.code is Code.REQUIREMENT_APPROVED
    assert result.is_normal
    assert result.verdict == "BLOCKING"
    assert state_of(ws, requirement) == "Apply"
    assert only_state_transition(ws, before, requirement, "Apply")


@pytest.mark.parametrize("acknowledged", [NEEDS_WORK, PASS])
def test_blocking_refuses_the_wrong_acknowledgement(acknowledged):
    ws, requirement, _, before = build_ready_workspace("BLOCKING")
    result = approve(ws, requirement, acknowledged)
    assert result.code is Code.VERDICT_ACKNOWLEDGEMENT_MISMATCH
    assert state_of(ws, requirement) == "Ready"
    assert mutations_since(ws, before) == []


def test_the_acknowledgement_is_checked_after_the_bindings():
    """A stale Requirement is stale whatever the human is willing to accept."""
    ws, requirement, root, before = build_ready_workspace("BLOCKING")
    ws.content[root.secret] += "\n## Extra\n\nEdited after review.\n"
    result = approve(ws, requirement, BLOCKING)
    assert result.code is Code.REVIEW_RESULT_STALE
    assert mutations_since(ws, before) == []


# -- the single mutation and its read-back ----------------------------------


def test_the_transition_is_confirmed_by_reading_the_entity_back():
    ws, requirement, _, _ = build_ready_workspace()
    approve(ws, requirement)
    reads_after_write = ws.calls[ws.calls.index("set_requirement_state") :]
    assert "read_requirement" in reads_after_write


def test_a_silently_ignored_approve_write_is_never_reported_as_approval():
    ws, requirement, _, _ = build_ready_workspace()
    ws.set_requirement_state = lambda entity_id, state: None
    result = approve(ws, requirement)
    assert result.code is Code.VALIDATION_FAILED
    assert not result.is_normal
    assert state_of(ws, requirement) == "Ready"


def test_a_silently_ignored_rework_write_is_never_reported_as_rework():
    ws, requirement, _, _ = build_ready_workspace()
    ws.set_requirement_state = lambda entity_id, state: None
    result = rework(ws, requirement)
    assert result.code is Code.VALIDATION_FAILED
    assert state_of(ws, requirement) == "Ready"


def test_a_failed_state_write_is_an_explicit_failure():
    ws, requirement, _, _ = build_ready_workspace()
    ws.failures["set_requirement_state"] = FiberyError("update rejected")
    result = approve(ws, requirement)
    assert result.code is Code.FIBERY_WRITE_FAILED
    assert "update rejected" in result.details
    assert state_of(ws, requirement) == "Ready"


def test_a_revision_that_moved_during_the_transition_fails_validation():
    ws, requirement, _, _ = build_ready_workspace()
    original = ws.set_requirement_state

    def bump_revision_too(entity_id, state):
        original(entity_id, state)
        current = ws.requirements[entity_id]
        ws.requirements[entity_id] = RequirementRecord(
            **{**current.__dict__, "revision": current.revision + 1}
        )

    ws.set_requirement_state = bump_revision_too
    result = approve(ws, requirement)
    assert result.code is Code.VALIDATION_FAILED
    assert "Revision" in result.message


# -- REWORK -----------------------------------------------------------------


def test_rework_moves_ready_to_process_and_reads_it_back():
    ws, requirement, _, before = build_ready_workspace()
    result = rework(ws, requirement)
    assert result.code is Code.REQUIREMENT_SENT_FOR_REWORK
    assert result.is_normal
    assert result.state == "Process"
    assert state_of(ws, requirement) == "Process"
    assert only_state_transition(ws, before, requirement, "Process")
    reads_after_write = ws.calls[ws.calls.index("set_requirement_state") :]
    assert "read_requirement" in reads_after_write


def test_rework_reads_no_evidence_at_all():
    """REWORK certifies nothing, so it has no reason to look at the artifacts."""
    ws, requirement, _, _ = build_ready_workspace()
    calls_before = len(ws.calls)
    rework(ws, requirement)
    assert "read_document_content" not in ws.calls[calls_before:]
    assert "child_documents" not in ws.calls[calls_before:]


def test_rework_needs_no_acknowledgement_at_blocking():
    ws, requirement, _, before = build_ready_workspace("BLOCKING")
    assert rework(ws, requirement).code is Code.REQUIREMENT_SENT_FOR_REWORK
    assert only_state_transition(ws, before, requirement, "Process")


def test_rework_keeps_every_artifact_byte_for_byte():
    ws, requirement, _, _ = build_ready_workspace("NEEDS_WORK", with_relation=True)
    documents = document_snapshot(ws)
    names = [d.name for d in ws.documents]
    rework(ws, requirement)
    assert ws.content == documents
    assert [d.name for d in ws.documents] == names


# -- idempotency ------------------------------------------------------------


def test_approve_when_already_apply_is_a_normal_result_with_no_mutation():
    ws, requirement, _, _ = build_ready_workspace()
    approve(ws, requirement)
    before = len(ws.mutations)
    result = approve(ws, requirement)
    assert result.code is Code.REQUIREMENT_ALREADY_APPROVED
    assert result.is_normal
    assert result.state == "Apply"
    assert state_of(ws, requirement) == "Apply"
    assert mutations_since(ws, before) == []


def test_already_approved_does_not_claim_the_content_is_still_safe():
    ws, requirement, root, _ = build_ready_workspace()
    approve(ws, requirement)
    ws.content[root.secret] += "\nEdited after approval.\n"
    result = approve(ws, requirement)
    assert result.code is Code.REQUIREMENT_ALREADY_APPROVED
    assert "does not certify" in result.message
    assert result.verdict is None


def test_already_approved_reads_no_evidence():
    ws, requirement, _, _ = build_ready_workspace()
    approve(ws, requirement)
    calls_before = len(ws.calls)
    approve(ws, requirement)
    assert "read_document_content" not in ws.calls[calls_before:]


def test_rework_when_already_process_is_a_normal_result_with_no_mutation():
    ws, requirement, _, _ = build_ready_workspace()
    rework(ws, requirement)
    before = len(ws.mutations)
    result = rework(ws, requirement)
    assert result.code is Code.REQUIREMENT_ALREADY_IN_REWORK
    assert result.is_normal
    assert state_of(ws, requirement) == "Process"
    assert mutations_since(ws, before) == []


def test_apply_is_never_moved_by_rework_and_process_never_by_approve():
    ws, requirement, _, _ = build_ready_workspace()
    approve(ws, requirement)
    assert rework(ws, requirement).code is Code.REQUIREMENT_NOT_IN_READY
    assert state_of(ws, requirement) == "Apply"

    ws, requirement, _, _ = build_ready_workspace()
    rework(ws, requirement)
    assert approve(ws, requirement).code is Code.REQUIREMENT_NOT_IN_READY
    assert state_of(ws, requirement) == "Process"


# -- hard immutability ------------------------------------------------------


PATHS = [
    ("PASS", None, Code.REQUIREMENT_APPROVED),
    ("NEEDS_WORK", None, Code.VERDICT_ACKNOWLEDGEMENT_REQUIRED),
    ("NEEDS_WORK", NEEDS_WORK, Code.REQUIREMENT_APPROVED),
    ("NEEDS_WORK", BLOCKING, Code.VERDICT_ACKNOWLEDGEMENT_MISMATCH),
    ("BLOCKING", None, Code.VERDICT_ACKNOWLEDGEMENT_REQUIRED),
    ("BLOCKING", BLOCKING, Code.REQUIREMENT_APPROVED),
    ("BLOCKING", NEEDS_WORK, Code.VERDICT_ACKNOWLEDGEMENT_MISMATCH),
    ("PASS", BLOCKING, Code.INVALID_VERDICT_ACKNOWLEDGEMENT),
]


@pytest.mark.parametrize(("verdict", "acknowledged", "expected"), PATHS)
def test_approve_never_writes_anything_but_the_state(verdict, acknowledged, expected):
    """Asserted on the mutation log: no write is even attempted."""
    ws, requirement, _, before = build_ready_workspace(verdict, with_relation=True)
    documents = document_snapshot(ws)
    relations = relation_state(ws)
    revision = ws.requirements[requirement.id].revision
    others = {k: v for k, v in ws.requirements.items() if k != requirement.id}

    result = approve(ws, requirement, acknowledged)
    assert result.code is expected

    added = mutations_since(ws, before)
    assert all(m.startswith("set_requirement_state") for m in added)
    assert len(added) <= 1
    assert ws.content == documents
    assert relation_state(ws) == relations
    assert ws.requirements[requirement.id].revision == revision
    assert {k: v for k, v in ws.requirements.items() if k != requirement.id} == others


def test_rework_never_writes_anything_but_the_state():
    ws, requirement, _, before = build_ready_workspace("BLOCKING", with_relation=True)
    documents = document_snapshot(ws)
    relations = relation_state(ws)
    revision = ws.requirements[requirement.id].revision
    others = {k: v for k, v in ws.requirements.items() if k != requirement.id}

    rework(ws, requirement)

    assert only_state_transition(ws, before, requirement, "Process")
    assert ws.content == documents
    assert relation_state(ws) == relations
    assert ws.requirements[requirement.id].revision == revision
    assert {k: v for k, v in ws.requirements.items() if k != requirement.id} == others


@pytest.mark.parametrize("decide", [approve, rework])
def test_confirmed_relation_proposals_stay_unapplied(decide):
    ws, requirement, _, _ = build_ready_workspace("PASS", with_relation=True)
    relations = relation_state(ws)
    result = decide(ws, requirement)
    assert result.is_normal
    assert relation_state(ws) == relations
    assert ws.depends_on_ids.get(requirement.id, []) == []


def test_approval_reports_confirmed_relations_as_still_unwritten():
    ws, requirement, _, _ = build_ready_workspace("PASS", with_relation=True)
    result = approve(ws, requirement)
    assert result.relations == ("DEPENDS_ON SDLC-FR-0002: The dependency is real.",)


def test_no_model_runtime_can_reach_either_decision():
    """The capability has no model parameter; there is nothing to invoke."""
    for decision in (approve_standard_requirement, rework_standard_requirement):
        parameters = inspect.signature(decision).parameters
        assert not any("model" in name or "runtime" in name for name in parameters)


def test_requirement_id_travels_in_every_result():
    ws, requirement, _, _ = build_ready_workspace("BLOCKING")
    assert approve(ws, requirement).requirement_id == REQUIREMENT_ID
    assert rework(ws, requirement).requirement_id == REQUIREMENT_ID
