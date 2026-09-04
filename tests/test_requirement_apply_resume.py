"""Partial application, resume, and drift detected mid-application.

The Requirement stays in Apply until every step has succeeded. Nothing that
became durable is rolled back, and a retry completes only what is missing,
never duplicating an edge and never recreating the Root Document.
"""

from __future__ import annotations

from apply_fake import (
    OTHER_ENTITY,
    OTHER_ID,
    TARGET_ENTITY,
    TARGET_ID,
    build_apply_workspace,
    edges,
    mutations_since,
    normative_writes,
    proposal,
    root_node,
    standard,
)
from sdlc.fibery_workspace import FiberyError, RequirementRecord
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.results import ApplyResultCode as Code
from sdlc.standard_analysis import RelationKind

DEPENDS = RelationKind.DEPENDS_ON
AFFECTS = RelationKind.AFFECTS
TWO_EDGES = (proposal(DEPENDS, TARGET_ID), proposal(AFFECTS, OTHER_ID))
TWO_TARGETS = (standard(), standard(OTHER_ID, OTHER_ENTITY))


def apply(ws, requirement):
    return apply_standard_requirement(ws, requirement.id)


def state_of(ws, requirement):
    return ws.requirements[requirement.id].state


def build_two_edge_workspace():
    return build_apply_workspace(proposals=TWO_EDGES, others=TWO_TARGETS)


def fail_after(ws, method, calls=1):
    """Make `method` raise on its Nth call, then behave normally again."""
    original = getattr(ws, method)
    counter = {"n": 0}

    def flaky(*args, **kwargs):
        counter["n"] += 1
        if counter["n"] == calls:
            raise FiberyError(f"{method} failed")
        return original(*args, **kwargs)

    setattr(ws, method, flaky)


def assert_partial(result, ws, requirement):
    assert result.code is Code.PARTIAL_APPLY, result
    assert not result.is_normal
    assert state_of(ws, requirement) == "Apply"


# -- failures after the first write -----------------------------------------


def test_failure_after_the_first_edge_keeps_it_and_stays_in_apply():
    ws, requirement, root, _ = build_two_edge_workspace()
    ws.failures["add_affects"] = FiberyError("add_affects failed")
    result = apply(ws, requirement)
    assert_partial(result, ws, requirement)
    assert result.created == (f"relation DEPENDS_ON {TARGET_ID}",)
    assert "FIBERY_WRITE_FAILED" in result.details
    assert edges(ws, requirement.id) == {(DEPENDS, TARGET_ID)}
    assert root_node(ws, root).folder_id == "f-draft"


def test_failure_after_all_edges_before_the_move():
    ws, requirement, root, _ = build_two_edge_workspace()
    ws.failures["set_document_folder"] = FiberyError("move failed")
    result = apply(ws, requirement)
    assert_partial(result, ws, requirement)
    assert edges(ws, requirement.id) == {(DEPENDS, TARGET_ID), (AFFECTS, OTHER_ID)}
    assert root_node(ws, root).folder_id == "f-draft"
    assert "Root Document Folder" not in " ".join(result.created)


def test_failure_during_the_move_read_back():
    ws, requirement, root, _ = build_two_edge_workspace()
    ws.failures["resolve_document"] = FiberyError("read-back failed")
    result = apply(ws, requirement)
    assert_partial(result, ws, requirement)
    # The move went through but was never confirmed, so it is not claimed;
    # the retry inspects the Folder and treats the step as already done.
    assert root_node(ws, root).folder_id == "f-approved"
    assert "Root Document Folder = Approved" not in result.created
    assert "FIBERY_WRITE_FAILED" in result.details


def test_failure_during_the_applied_write():
    ws, requirement, root, _ = build_two_edge_workspace()
    ws.failures["set_requirement_state"] = FiberyError("state write failed")
    result = apply(ws, requirement)
    assert_partial(result, ws, requirement)
    assert "FIBERY_WRITE_FAILED" in result.details
    assert root_node(ws, root).folder_id == "f-approved"
    assert edges(ws, requirement.id) == {(DEPENDS, TARGET_ID), (AFFECTS, OTHER_ID)}


def test_failure_during_the_applied_read_back():
    ws, requirement, _, _ = build_two_edge_workspace()
    fail_after(ws, "read_requirement", calls=2)
    result = apply(ws, requirement)
    assert result.code is Code.PARTIAL_APPLY
    assert not result.is_normal
    # The State write was durable; the retry sees Applied and stops.
    assert state_of(ws, requirement) == "Applied"
    assert apply(ws, requirement).code is Code.REQUIREMENT_ALREADY_APPLIED


def test_an_edge_that_does_not_read_back_is_a_validation_failure():
    ws, requirement, _, _ = build_apply_workspace(proposals=(proposal(DEPENDS),))
    ws.add_depends_on = lambda entity_id, target_id: ws.mutations.append("ignored add")
    result = apply(ws, requirement)
    assert result.code is Code.PARTIAL_APPLY
    assert "VALIDATION_FAILED" in result.details
    assert state_of(ws, requirement) == "Apply"


# -- resume -----------------------------------------------------------------


def test_retry_after_a_relation_partial_writes_only_the_missing_edge():
    ws, requirement, root, _ = build_two_edge_workspace()
    ws.failures["add_affects"] = FiberyError("add_affects failed")
    apply(ws, requirement)
    before = len(ws.mutations)

    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert result.relations_present == (f"DEPENDS_ON {TARGET_ID}",)
    assert result.relations_added == (f"AFFECTS {OTHER_ID}",)
    assert normative_writes(ws, before) == [
        f"add_affects {requirement.id} -> {OTHER_ENTITY}",
        f"set_document_folder {root.id} f-approved",
        f"set_requirement_state {requirement.id} Applied",
    ]
    assert ws.depends_on_ids[requirement.id] == [TARGET_ENTITY]
    assert ws.affects_ids[requirement.id] == [OTHER_ENTITY]


def test_retry_after_the_root_moved_only_transitions():
    ws, requirement, root, _ = build_two_edge_workspace()
    ws.failures["set_requirement_state"] = FiberyError("state write failed")
    apply(ws, requirement)
    before = len(ws.mutations)

    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert normative_writes(ws, before) == [
        f"set_requirement_state {requirement.id} Applied"
    ]
    assert root_node(ws, root).folder_id == "f-approved"
    assert (
        len([d for d in ws.documents if d.entity_public_id == requirement.public_id])
        == 1
    )


def test_retry_after_a_move_read_back_failure_does_not_move_twice():
    ws, requirement, root, _ = build_two_edge_workspace()
    ws.failures["resolve_document"] = FiberyError("read-back failed")
    apply(ws, requirement)
    before = len(ws.mutations)
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert not any(
        m.startswith("set_document_folder") for m in mutations_since(ws, before)
    )
    assert root_node(ws, root).id == root.id


def test_retry_revalidates_the_binding_before_resuming():
    ws, requirement, root, _ = build_two_edge_workspace()
    ws.failures["add_affects"] = FiberyError("add_affects failed")
    apply(ws, requirement)
    ws.content[root.secret] += "\nEdited between attempts.\n"
    before = len(ws.mutations)
    result = apply(ws, requirement)
    assert result.code is Code.REVIEW_RESULT_STALE
    assert mutations_since(ws, before) == []
    assert edges(ws, requirement.id) == {(DEPENDS, TARGET_ID)}
    assert state_of(ws, requirement) == "Apply"


def test_no_apply_result_artifact_is_ever_created():
    ws, requirement, _, before = build_two_edge_workspace()
    ws.failures["set_document_folder"] = FiberyError("move failed")
    apply(ws, requirement)
    apply(ws, requirement)
    assert not any(
        m.startswith("create_child_document") for m in mutations_since(ws, before)
    )
    assert not any(m.startswith("write_content") for m in mutations_since(ws, before))


# -- drift after the first write --------------------------------------------


def test_drift_before_the_first_write_is_refused_without_mutation():
    """The binding is re-read immediately before the first write."""
    ws, requirement, root, before = build_two_edge_workspace()
    original = ws.find_requirements_by_requirement_id

    def edit_during_preflight(requirement_id):
        ws.content[root.secret] += "\nConcurrent edit.\n"
        return original(requirement_id)

    ws.find_requirements_by_requirement_id = edit_during_preflight
    result = apply(ws, requirement)
    assert result.code is Code.REVIEW_RESULT_STALE
    assert mutations_since(ws, before) == []


def test_drift_after_edges_are_written_keeps_them_and_never_reaches_applied():
    ws, requirement, root, before = build_two_edge_workspace()
    original = ws.add_affects

    def edit_after_adding(entity_id, target_id):
        original(entity_id, target_id)
        ws.content[root.secret] += "\nConcurrent edit.\n"

    ws.add_affects = edit_after_adding
    result = apply(ws, requirement)
    assert_partial(result, ws, requirement)
    assert "REVIEW_RESULT_STALE" in result.details
    assert edges(ws, requirement.id) == {(DEPENDS, TARGET_ID), (AFFECTS, OTHER_ID)}
    assert root_node(ws, root).folder_id == "f-approved", "the move as reached stays"
    assert not any(
        m.startswith("set_requirement_state") for m in mutations_since(ws, before)
    )
    assert "State = Applied" not in result.created


def test_drift_detected_mid_apply_does_not_move_the_root_back():
    ws, requirement, root, _ = build_two_edge_workspace()
    original = ws.set_document_folder

    def edit_after_moving(document_id, folder_id):
        original(document_id, folder_id)
        ws.content[root.secret] += "\nConcurrent edit.\n"

    ws.set_document_folder = edit_after_moving
    result = apply(ws, requirement)
    assert_partial(result, ws, requirement)
    assert root_node(ws, root).folder_id == "f-approved"
    assert [m for m in ws.mutations if m.startswith("set_document_folder")] == [
        f"set_document_folder {root.id} f-approved"
    ]


def test_revision_is_unchanged_across_partial_and_resume():
    ws, requirement, _, _ = build_two_edge_workspace()
    ws.failures["add_affects"] = FiberyError("add_affects failed")
    apply(ws, requirement)
    assert ws.requirements[requirement.id].revision == 1
    apply(ws, requirement)
    assert ws.requirements[requirement.id].revision == 1


# -- the final read-back guards Revision on its own -------------------------


def test_an_applied_write_that_also_moves_revision_is_not_reported_as_applied():
    """Freeze review N2: the Revision read-back must stand on its own.

    The State write lands durably, but the entity reads back with a changed
    Revision. Every normative step is complete, so the honest answer is a
    partial application that names the validation failure, never success.
    """
    ws, requirement, root, _ = build_two_edge_workspace()
    original = ws.set_requirement_state

    def applied_with_a_bumped_revision(entity_id, state):
        original(entity_id, state)
        current = ws.requirements[entity_id]
        ws.requirements[entity_id] = RequirementRecord(
            **{**current.__dict__, "revision": current.revision + 1}
        )

    ws.set_requirement_state = applied_with_a_bumped_revision
    result = apply(ws, requirement)

    assert result.code is Code.PARTIAL_APPLY
    assert not result.is_normal
    assert "VALIDATION_FAILED" in result.details
    assert "Revision" in " ".join(result.details)
    assert "State = Applied" not in result.created
    # Durable state is reported as it is: the State write landed, the edges
    # and the Root move stay, and nothing is rolled back.
    assert state_of(ws, requirement) == "Applied"
    assert ws.requirements[requirement.id].revision == requirement.revision + 1
    assert edges(ws, requirement.id) == {(DEPENDS, TARGET_ID), (AFFECTS, OTHER_ID)}
    assert root_node(ws, root).folder_id == "f-approved"
    assert apply(ws, requirement).code is Code.REQUIREMENT_ALREADY_APPLIED
