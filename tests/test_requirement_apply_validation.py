"""Apply validates everything predictable before its first write.

Artifacts, the Review Result's agreement with its own relation mirror, every
relation target and the reviewed-state binding are all checked while nothing
has been written yet. Every refusal here asserts an empty mutation log.
"""

from __future__ import annotations

import json

import pytest

from apply_fake import (
    OTHER_ENTITY,
    OTHER_ID,
    TARGET_ENTITY,
    TARGET_ID,
    build_apply_workspace,
    confirmed,
    mutations_since,
    payload_of,
    process_result_nodes,
    proposal,
    review_result_nodes,
    rewrite_payload,
    standard,
)
from sdlc.fibery_workspace import DocumentNode, FiberyError
from sdlc.process_result import (
    build_process_result,
    process_result_name,
    render_process_result,
)
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.results import ApplyResultCode as Code
from sdlc.review_result import review_result_name
from sdlc.standard_analysis import AnalysisResult, NormalizedRequirement, RelationKind
from standard_fake import REQUIREMENT_ID, normalized

DEPENDS = RelationKind.DEPENDS_ON
AFFECTS = RelationKind.AFFECTS


def apply(ws, requirement):
    return apply_standard_requirement(ws, requirement.id)


def state_of(ws, requirement):
    return ws.requirements[requirement.id].state


def refused(ws, requirement, before, code):
    result = apply(ws, requirement)
    assert result.code is code, result
    assert not result.is_normal
    assert state_of(ws, requirement) == "Apply"
    assert mutations_since(ws, before) == []
    return result


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


def set_mirror(ws, entries):
    node = review_result_nodes(ws)[-1]
    rewrite_payload(ws, node, confirmed_relation_proposals=entries)


# -- the three bindings -----------------------------------------------------


def test_an_edited_root_document_is_stale():
    ws, requirement, root, before = build_apply_workspace(proposals=(proposal(),))
    ws.content[root.secret] += "\n## Extra\n\nEdited after approval.\n"
    result = refused(ws, requirement, before, Code.REVIEW_RESULT_STALE)
    assert "Root Document was edited" in " ".join(result.details)


def test_a_new_process_iteration_is_stale():
    ws, requirement, root, before = build_apply_workspace(proposals=(proposal(),))
    result = build_process_result(
        requirement_id=REQUIREMENT_ID,
        iteration=2,
        input_fingerprint="input-2",
        analysis=AnalysisResult(
            normalized=NormalizedRequirement(**normalized(title="Rewritten")),
            analysis={},
            findings=(),
            proposed_relations=(),
        ),
    )
    add_document(
        ws, root, process_result_name(REQUIREMENT_ID, 2), render_process_result(result)
    )
    refused(ws, requirement, before, Code.REVIEW_RESULT_STALE)


def test_a_changed_process_output_fingerprint_is_stale():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(),))
    rewrite_payload(ws, process_result_nodes(ws)[-1], output_fingerprint="moved")
    result = refused(ws, requirement, before, Code.REVIEW_RESULT_STALE)
    assert "no longer produces" in " ".join(result.details)


def test_fibery_reserialization_is_not_a_change():
    ws, requirement, _, _ = build_apply_workspace()
    assert ws.reserializes
    assert apply(ws, requirement).code is Code.REQUIREMENT_APPLIED


# -- artifacts --------------------------------------------------------------


def test_no_review_result_refuses_application():
    ws, requirement, _, before = build_apply_workspace()
    for node in review_result_nodes(ws):
        ws.documents.remove(node)
    refused(ws, requirement, before, Code.NO_REVIEW_RESULT)


def test_a_malformed_latest_review_result_refuses_application():
    ws, requirement, _, before = build_apply_workspace()
    ws.content[review_result_nodes(ws)[-1].secret] = "# prose only\n"
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)


def test_an_unsupported_review_result_version_refuses_application():
    ws, requirement, _, before = build_apply_workspace()
    rewrite_payload(ws, review_result_nodes(ws)[-1], review_result_version="9.9")
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)


def test_a_review_result_naming_another_requirement_is_invalid():
    ws, requirement, _, before = build_apply_workspace()
    rewrite_payload(ws, review_result_nodes(ws)[-1], requirement_id="SDLC-FR-0099")
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)


def test_duplicate_review_iterations_are_a_conflict():
    ws, requirement, root, before = build_apply_workspace()
    original = review_result_nodes(ws)[-1]
    add_document(ws, root, original.name, ws.content[original.secret], secret="dup")
    refused(ws, requirement, before, Code.REVIEW_STATE_CONFLICT)


def test_an_older_review_result_is_never_used_when_the_newest_is_unusable():
    ws, requirement, root, before = build_apply_workspace()
    add_document(ws, root, review_result_name(REQUIREMENT_ID, 2), "# unreadable\n")
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)


def test_no_process_result_refuses_application():
    ws, requirement, _, before = build_apply_workspace()
    for node in process_result_nodes(ws):
        ws.documents.remove(node)
    refused(ws, requirement, before, Code.NO_PROCESS_RESULT)


def test_a_malformed_process_result_refuses_application():
    ws, requirement, _, before = build_apply_workspace()
    ws.content[process_result_nodes(ws)[-1].secret] = "# broken\n"
    refused(ws, requirement, before, Code.INVALID_PROCESS_RESULT)


def test_duplicate_process_iterations_are_invalid_history():
    ws, requirement, root, before = build_apply_workspace()
    original = process_result_nodes(ws)[-1]
    add_document(ws, root, original.name, ws.content[original.secret], secret="dup-p")
    refused(ws, requirement, before, Code.INVALID_PROCESS_RESULT)


def test_a_missing_root_document_is_a_structure_failure():
    ws, requirement, root, before = build_apply_workspace()
    ws.documents.remove(root)
    refused(ws, requirement, before, Code.PROJECT_STRUCTURE_INVALID)


def test_an_ambiguous_folder_tree_is_a_structure_failure():
    ws, requirement, _, before = build_apply_workspace()
    ws.folders.append(
        type(ws.folders[0])(id="f-approved-2", name="Approved", parent_id="f-reqs")
    )
    refused(ws, requirement, before, Code.PROJECT_STRUCTURE_INVALID)


@pytest.mark.parametrize(
    "call",
    ["documents_attached_to_requirement", "child_documents", "requirement_relations"],
)
def test_a_read_failure_before_the_first_write_mutates_nothing(call):
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(),))
    ws.failures[call] = FiberyError("timeout")
    result = refused(ws, requirement, before, Code.FIBERY_READ_FAILED)
    assert "timeout" in result.details


# -- mirror consistency -----------------------------------------------------


def test_a_consistent_mirror_is_accepted():
    ws, requirement, _, _ = build_apply_workspace(proposals=(proposal(DEPENDS),))
    payload, _, _ = payload_of(ws, review_result_nodes(ws)[-1])
    assert [
        (e["kind"], e["requirement_id"])
        for e in payload["confirmed_relation_proposals"]
    ] == [("DEPENDS_ON", TARGET_ID)]
    assert apply(ws, requirement).code is Code.REQUIREMENT_APPLIED


def test_a_confirmed_verification_missing_from_the_mirror_is_invalid():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    set_mirror(ws, [])
    result = refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)
    assert "disagrees with itself" in result.message


def test_a_mirror_entry_that_was_not_confirmed_is_invalid():
    ws, requirement, _, before = build_apply_workspace(
        proposals=(proposal(DEPENDS),),
        verifications=[confirmed("DEPENDS_ON", TARGET_ID, outcome="REJECTED")],
    )
    set_mirror(ws, [confirmed("DEPENDS_ON", TARGET_ID)])
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)


def test_a_mirror_entry_with_the_wrong_kind_is_invalid():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    set_mirror(ws, [confirmed("AFFECTS", TARGET_ID)])
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)


def test_a_mirror_entry_with_the_wrong_target_is_invalid():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    set_mirror(ws, [confirmed("DEPENDS_ON", OTHER_ID)])
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)


def test_a_mirror_entry_marked_rejected_is_invalid():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    set_mirror(ws, [confirmed("DEPENDS_ON", TARGET_ID, outcome="REJECTED")])
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)


def test_a_duplicate_logical_edge_in_the_verifications_is_invalid():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    node = review_result_nodes(ws)[-1]
    payload, _, _ = payload_of(ws, node)
    twice = payload["relation_proposal_verifications"] * 2
    rewrite_payload(ws, node, relation_proposal_verifications=twice)
    result = refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)
    assert "more than once" in result.message


def test_a_duplicate_logical_edge_in_the_mirror_is_invalid():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    set_mirror(ws, [confirmed("DEPENDS_ON", TARGET_ID)] * 2)
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)


def test_a_malformed_mirror_entry_is_invalid():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    set_mirror(ws, [{"kind": "DEPENDS_ON"}])
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)


def test_the_mirror_check_happens_before_any_target_lookup():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    set_mirror(ws, [])
    calls_before = len(ws.calls)
    refused(ws, requirement, before, Code.INVALID_REVIEW_RESULT)
    assert "find_requirements_by_requirement_id" not in ws.calls[calls_before:]


# -- relation targets -------------------------------------------------------


def test_a_missing_target_is_refused():
    ws, requirement, _, before = build_apply_workspace(
        proposals=(proposal(DEPENDS, "SDLC-FR-0404"),), others=()
    )
    refused(ws, requirement, before, Code.RELATION_TARGET_NOT_FOUND)


def test_an_ambiguous_target_is_refused_not_adopted():
    others = (standard(), standard(TARGET_ID, "std-uuid-dup"))
    ws, requirement, _, before = build_apply_workspace(
        proposals=(proposal(DEPENDS),), others=others
    )
    result = refused(ws, requirement, before, Code.INVALID_RELATION_TARGET)
    assert "more than one" in result.message
    assert set(result.details) == {TARGET_ENTITY, "std-uuid-dup"}


def test_a_raw_target_is_refused():
    others = (standard(type_name="Raw"),)
    ws, requirement, _, before = build_apply_workspace(
        proposals=(proposal(DEPENDS),), others=others
    )
    refused(ws, requirement, before, Code.INVALID_RELATION_TARGET)


def test_a_target_in_another_project_is_refused():
    others = (standard(project_id="p-2"),)
    ws, requirement, _, before = build_apply_workspace(
        proposals=(proposal(DEPENDS),), others=others
    )
    refused(ws, requirement, before, Code.INVALID_RELATION_TARGET)


def test_a_self_relation_is_refused():
    ws, requirement, _, before = build_apply_workspace(
        proposals=(proposal(DEPENDS, REQUIREMENT_ID),)
    )
    result = refused(ws, requirement, before, Code.INVALID_RELATION_TARGET)
    assert "itself" in result.message


def test_one_bad_target_among_good_ones_writes_nothing():
    """The whole preflight completes before the first edge is written."""
    others = (standard(), standard(OTHER_ID, OTHER_ENTITY))
    proposals = (
        proposal(DEPENDS, TARGET_ID),
        proposal(AFFECTS, OTHER_ID),
        proposal(DEPENDS, "SDLC-FR-0404"),
    )
    ws, requirement, _, before = build_apply_workspace(
        proposals=proposals, others=others
    )
    refused(ws, requirement, before, Code.RELATION_TARGET_NOT_FOUND)
    assert ws.depends_on_ids.get(requirement.id, []) == []
    assert ws.affects_ids.get(requirement.id, []) == []


def test_a_target_lookup_failure_mutates_nothing():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    ws.failures["find_requirements_by_requirement_id"] = FiberyError("timeout")
    refused(ws, requirement, before, Code.FIBERY_READ_FAILED)


def test_the_ambiguous_target_entity_is_never_the_one_written():
    """Even a lookup returning the right row first is not adopted."""
    others = (standard(TARGET_ID, "std-uuid-dup"), standard())
    ws, requirement, _, before = build_apply_workspace(
        proposals=(proposal(DEPENDS),), others=others
    )
    refused(ws, requirement, before, Code.INVALID_RELATION_TARGET)
    assert OTHER_ENTITY not in json.dumps(ws.depends_on_ids)


# -- each binding is load-bearing on its own --------------------------------


def test_a_new_process_iteration_with_the_same_output_is_stale():
    """Freeze review N1: the iteration binding must stand on its own.

    A later Process Result whose output fingerprint equals the reviewed one
    moves exactly one binding, the iteration. The Root Document is unchanged
    and the output fingerprint agrees, so only the iteration guard can refuse.
    """
    ws, requirement, root, before = build_apply_workspace(proposals=(proposal(),))
    reviewed = process_result_nodes(ws)[-1]
    reviewed_payload, _, _ = payload_of(ws, reviewed)
    later = build_process_result(
        requirement_id=REQUIREMENT_ID,
        iteration=2,
        input_fingerprint="input-2",
        analysis=AnalysisResult(
            normalized=NormalizedRequirement(**normalized()),
            analysis={},
            findings=(),
            proposed_relations=(),
        ),
    )
    assert later.output_fingerprint == reviewed_payload["output_fingerprint"]
    add_document(
        ws, root, process_result_name(REQUIREMENT_ID, 2), render_process_result(later)
    )

    result = refused(ws, requirement, before, Code.REVIEW_RESULT_STALE)
    assert "iteration 2 now exists, but 1 was reviewed" in " ".join(result.details)
    assert "Root Document was edited" not in " ".join(result.details)
    assert ws.requirements[requirement.id].revision == requirement.revision
