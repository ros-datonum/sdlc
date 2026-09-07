"""APPROVE validates the evidence, freshly, before it records anything.

Everything here is about refusing to approve a Requirement whose latest Review
Result no longer describes reality, and about never guessing when the history
itself is ambiguous or unreadable.
"""

from __future__ import annotations

import json

import pytest

from ready_fake import (
    REQUIREMENT_ID,
    build_ready_workspace,
    mutations_since,
    process_result_nodes,
    review_result_nodes,
)
from review_fake import add_process_iteration, move_process_output
from sdlc.fibery_workspace import DocumentNode, FiberyError
from sdlc.process_result import (
    process_result_name,
)
from sdlc.ready_decision import (
    approve_standard_requirement,
    rework_standard_requirement,
)
from sdlc.results import ReadyDecisionResultCode as Code
from sdlc.review_result import review_result_name
from sdlc.standard_review import ReviewVerdict


def approve(ws, requirement, acknowledged=None):
    return approve_standard_requirement(ws, requirement.id, acknowledged)


def state_of(ws, requirement):
    return ws.requirements[requirement.id].state


def add_document(ws, root, name, content, secret=None):
    secret = secret or f"secret-{name}"
    ws.documents.append(
        DocumentNode(
            id=f"doc-{name}",
            name=name,
            folder_id=None,
            entity_public_id=None,
            secret=secret,
            parent_document_id=root.id,
        )
    )
    ws.content[secret] = content


def rewrite_payload(ws, node, **changes):
    """Edit the JSON payload of a persisted artifact in place."""
    text = ws.content[node.secret]
    start = text.index("```json\n") + len("```json\n")
    end = text.index("\n```", start)
    payload = json.loads(text[start:end])
    payload.update(changes)
    ws.content[node.secret] = text[:start] + json.dumps(payload, indent=2) + text[end:]


# -- the three bindings -----------------------------------------------------


def test_an_edited_root_document_is_stale():
    ws, requirement, root, before = build_ready_workspace()
    ws.content[root.secret] += "\n## Extra\n\nAdded by a human after review.\n"
    result = approve(ws, requirement)
    assert result.code is Code.REVIEW_RESULT_STALE
    assert not result.is_normal
    assert "Root Document was edited" in " ".join(result.details)
    assert state_of(ws, requirement) == "Ready"
    assert mutations_since(ws, before) == []


def test_a_new_process_iteration_is_stale():
    ws, requirement, root, before = build_ready_workspace()
    add_process_iteration(ws, root, 2)
    result = approve(ws, requirement)
    assert result.code is Code.REVIEW_RESULT_STALE
    assert "iteration 2 now exists" in " ".join(result.details)
    assert mutations_since(ws, before) == []


def test_a_changed_process_output_fingerprint_is_stale():
    """The Process binding is re-read from Fibery, not trusted from the review."""
    ws, requirement, _, before = build_ready_workspace()
    move_process_output(ws, process_result_nodes(ws)[-1])
    result = approve(ws, requirement)
    assert result.code is Code.REVIEW_RESULT_STALE
    assert "no longer produces the output" in " ".join(result.details)
    assert mutations_since(ws, before) == []


def test_fibery_reserialization_is_not_a_change():
    """The fixture stores raw Markdown and reads it back re-serialized."""
    ws, requirement, _, _ = build_ready_workspace()
    assert ws.reserializes
    assert approve(ws, requirement).code is Code.REQUIREMENT_APPROVED


def test_staleness_is_checked_before_the_acknowledgement():
    ws, requirement, root, before = build_ready_workspace("BLOCKING")
    ws.content[root.secret] += "\nEdited.\n"
    assert approve(ws, requirement).code is Code.REVIEW_RESULT_STALE
    assert approve(ws, requirement, ReviewVerdict.BLOCKING).code is (
        Code.REVIEW_RESULT_STALE
    )
    assert mutations_since(ws, before) == []


def test_a_stale_requirement_may_still_be_sent_for_rework():
    ws, requirement, root, before = build_ready_workspace()
    ws.content[root.secret] += "\nEdited.\n"
    result = rework_standard_requirement(ws, requirement.id)
    assert result.code is Code.REQUIREMENT_SENT_FOR_REWORK
    assert mutations_since(ws, before) == [
        f"set_requirement_state {requirement.id} Process"
    ]


# -- Review Result history --------------------------------------------------


def test_no_review_result_refuses_approval():
    ws, requirement, _, before = build_ready_workspace()
    for node in review_result_nodes(ws):
        ws.documents.remove(node)
    result = approve(ws, requirement)
    assert result.code is Code.NO_REVIEW_RESULT
    assert mutations_since(ws, before) == []


def test_a_malformed_latest_review_result_refuses_approval():
    ws, requirement, _, before = build_ready_workspace()
    ws.content[review_result_nodes(ws)[-1].secret] = "# Not a review\n\nprose only\n"
    result = approve(ws, requirement)
    assert result.code is Code.INVALID_REVIEW_RESULT
    assert mutations_since(ws, before) == []


def test_an_unsupported_review_result_version_refuses_approval():
    ws, requirement, _, before = build_ready_workspace()
    rewrite_payload(ws, review_result_nodes(ws)[-1], review_result_version="9.9")
    result = approve(ws, requirement)
    assert result.code is Code.INVALID_REVIEW_RESULT
    assert mutations_since(ws, before) == []


def test_a_review_result_naming_another_requirement_is_invalid():
    ws, requirement, _, before = build_ready_workspace()
    rewrite_payload(ws, review_result_nodes(ws)[-1], requirement_id="SDLC-FR-0099")
    result = approve(ws, requirement)
    assert result.code is Code.INVALID_REVIEW_RESULT
    assert mutations_since(ws, before) == []


def test_a_review_result_whose_iteration_disagrees_with_its_name_is_invalid():
    ws, requirement, _, before = build_ready_workspace()
    rewrite_payload(ws, review_result_nodes(ws)[-1], iteration=7)
    result = approve(ws, requirement)
    assert result.code is Code.INVALID_REVIEW_RESULT
    assert mutations_since(ws, before) == []


def test_a_review_result_contradicting_its_own_verdict_is_invalid():
    ws, requirement, _, before = build_ready_workspace("BLOCKING")
    rewrite_payload(ws, review_result_nodes(ws)[-1], derived_verdict="PASS")
    result = approve(ws, requirement)
    assert result.code is Code.INVALID_REVIEW_RESULT
    assert mutations_since(ws, before) == []


def test_duplicate_review_iterations_are_a_conflict():
    ws, requirement, root, before = build_ready_workspace()
    original = review_result_nodes(ws)[-1]
    add_document(
        ws, root, original.name, ws.content[original.secret], secret="dup-secret"
    )
    result = approve(ws, requirement)
    assert result.code is Code.REVIEW_STATE_CONFLICT
    assert mutations_since(ws, before) == []


def test_an_older_valid_review_result_is_never_used_as_a_fallback():
    """The newest artifact is current history even when it cannot be read."""
    ws, requirement, root, before = build_ready_workspace()
    add_document(
        ws,
        root,
        review_result_name(REQUIREMENT_ID, 2),
        "# Review Result 0002\n\nunreadable\n",
    )
    result = approve(ws, requirement)
    assert result.code is Code.INVALID_REVIEW_RESULT
    assert state_of(ws, requirement) == "Ready"
    assert mutations_since(ws, before) == []


def test_the_newest_review_result_is_the_one_the_verdict_comes_from():
    """An acknowledgement copied from an older review cannot approve a newer one."""
    ws, requirement, root, before = build_ready_workspace("NEEDS_WORK")
    older = review_result_nodes(ws)[-1]
    newer_name = review_result_name(REQUIREMENT_ID, 2)
    add_document(ws, root, newer_name, ws.content[older.secret], secret="newer")
    rewrite_payload(
        ws,
        ws.documents[-1],
        iteration=2,
        derived_verdict="BLOCKING",
        process_finding_verifications=[
            {
                "process_finding_index": 0,
                "outcome": "CONFIRMED",
                "severity": "BLOCKING",
                "reason": "Worse on second look.",
            }
        ],
    )
    result = approve(ws, requirement, ReviewVerdict.NEEDS_WORK)
    assert result.code is Code.VERDICT_ACKNOWLEDGEMENT_MISMATCH
    assert result.iteration == 2
    assert result.verdict == "BLOCKING"
    assert mutations_since(ws, before) == []

    assert approve(ws, requirement, ReviewVerdict.BLOCKING).code is (
        Code.REQUIREMENT_APPROVED
    )


# -- Process Result history -------------------------------------------------


def test_no_process_result_refuses_approval():
    ws, requirement, _, before = build_ready_workspace()
    for node in process_result_nodes(ws):
        ws.documents.remove(node)
    result = approve(ws, requirement)
    assert result.code is Code.NO_PROCESS_RESULT
    assert mutations_since(ws, before) == []


def test_a_malformed_latest_process_result_refuses_approval():
    ws, requirement, _, before = build_ready_workspace()
    ws.content[process_result_nodes(ws)[-1].secret] = "# broken\n"
    result = approve(ws, requirement)
    assert result.code is Code.INVALID_PROCESS_RESULT
    assert mutations_since(ws, before) == []


def test_a_process_result_naming_another_requirement_is_invalid():
    ws, requirement, _, before = build_ready_workspace()
    rewrite_payload(ws, process_result_nodes(ws)[-1], requirement_id="SDLC-FR-0099")
    result = approve(ws, requirement)
    assert result.code is Code.INVALID_PROCESS_RESULT
    assert mutations_since(ws, before) == []


def test_duplicate_process_iterations_are_invalid_history():
    ws, requirement, root, before = build_ready_workspace()
    original = process_result_nodes(ws)[-1]
    add_document(
        ws, root, original.name, ws.content[original.secret], secret="dup-process"
    )
    result = approve(ws, requirement)
    assert result.code is Code.INVALID_PROCESS_RESULT
    assert mutations_since(ws, before) == []


def test_only_the_latest_process_result_is_compared():
    """Older iterations are history; the review binds to the latest one."""
    ws, requirement, _, _ = build_ready_workspace(process_iterations=3)
    ws.content[process_result_nodes(ws)[0].secret] = "# older, unreadable\n"
    assert approve(ws, requirement).code is Code.REQUIREMENT_APPROVED


def test_artifacts_of_other_requirements_under_the_root_are_refused():
    """A foreign artifact name under the Root is neither content nor history;
    the normative tree cannot be established around it (A5 §5)."""
    ws, requirement, root, before = build_ready_workspace()
    add_document(ws, root, review_result_name("SDLC-FR-0099", 5), "# other\n")
    add_document(ws, root, process_result_name("SDLC-FR-0099", 5), "# other\n")
    result = approve(ws, requirement)
    assert result.code is Code.NORMATIVE_TREE_INVALID
    assert "SDLC-FR-0099" in " ".join((result.message, *result.details))
    assert mutations_since(ws, before) == []


# -- structure and reads ----------------------------------------------------


def test_a_missing_root_document_is_a_structure_failure():
    ws, requirement, root, before = build_ready_workspace()
    ws.documents.remove(root)
    result = approve(ws, requirement)
    assert result.code is Code.PROJECT_STRUCTURE_INVALID
    assert mutations_since(ws, before) == []


@pytest.mark.parametrize(
    "call", ["documents_attached_to_requirement", "child_documents"]
)
def test_an_evidence_read_failure_is_reported_without_mutation(call):
    ws, requirement, _, before = build_ready_workspace()
    ws.failures[call] = FiberyError("timeout")
    result = approve(ws, requirement)
    assert result.code is Code.FIBERY_READ_FAILED
    assert "timeout" in result.details
    assert mutations_since(ws, before) == []


def test_every_check_happens_before_the_state_write():
    """The write is the last call; every read precedes it."""
    ws, requirement, _, _ = build_ready_workspace("BLOCKING", with_relation=True)
    calls_before = len(ws.calls)
    approve(ws, requirement, ReviewVerdict.BLOCKING)
    calls = ws.calls[calls_before:]
    write = calls.index("set_requirement_state")
    assert set(calls[:write]) >= {
        "read_requirement",
        "documents_attached_to_requirement",
        "child_documents",
        "read_document_content",
    }
    assert calls[write + 1 :] == ["read_requirement"]


# -- fenced content is literal --------------------------------------------

FENCED_EXAMPLE = 'Example:\n\n```json\n{\n    "timeout": 30\n}\n```'


def test_an_indentation_change_inside_a_fenced_example_is_stale():
    """Freeze review B1: a fenced edit must not slip past the document binding."""
    ws, requirement, root, before = build_ready_workspace(
        normalized_changes={"detailed_behavior": FENCED_EXAMPLE}
    )
    assert '    "timeout"' in ws.content[root.secret]
    ws.content[root.secret] = ws.content[root.secret].replace(
        '    "timeout"', '  "timeout"'
    )
    result = approve(ws, requirement)
    assert result.code is Code.REVIEW_RESULT_STALE
    assert "Root Document was edited" in " ".join(result.details)
    assert state_of(ws, requirement) == "Ready"
    assert mutations_since(ws, before) == []


def test_an_unedited_fenced_example_still_approves():
    ws, requirement, _, before = build_ready_workspace(
        normalized_changes={"detailed_behavior": FENCED_EXAMPLE}
    )
    assert approve(ws, requirement).code is Code.REQUIREMENT_APPROVED
    assert mutations_since(ws, before) == [
        f"set_requirement_state {requirement.id} Apply"
    ]
