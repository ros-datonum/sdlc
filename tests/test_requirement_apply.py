"""`STANDARD Requirement + Apply`: entry, relations, the Root move, the invariant.

Apply writes three kinds of thing and nothing else: missing confirmed edges,
the Root Document's Folder, and the final State. Everything here asserts on
the mutation log that those are the only writes, on every path.
"""

from __future__ import annotations

import inspect

import pytest

from apply_fake import (
    OTHER_ENTITY,
    OTHER_ID,
    REQUIREMENT_ID,
    TARGET_ENTITY,
    TARGET_ID,
    build_apply_workspace,
    child_ids,
    confirmed,
    edges,
    mutations_since,
    normative_writes,
    proposal,
    root_node,
    standard,
)
from sdlc.fibery_workspace import FiberyError
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.results import ApplyResultCode as Code
from sdlc.standard_analysis import RelationKind
from standard_fake import set_state

DEPENDS = RelationKind.DEPENDS_ON
AFFECTS = RelationKind.AFFECTS


def apply(ws, requirement):
    return apply_standard_requirement(ws, requirement.id)


def state_of(ws, requirement):
    return ws.requirements[requirement.id].state


# -- entry and idempotency --------------------------------------------------


def test_a_standard_requirement_in_apply_is_applied():
    ws, requirement, root, before = build_apply_workspace()
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert result.is_normal
    assert state_of(ws, requirement) == "Applied"
    assert root_node(ws, root).folder_id == "f-approved"
    assert normative_writes(ws, before) == [
        f"set_document_folder {root.id} f-approved",
        f"set_requirement_state {requirement.id} Applied",
    ]


def test_an_unknown_requirement_is_refused():
    ws, _, _, before = build_apply_workspace()
    assert apply_standard_requirement(ws, "nope").code is Code.REQUIREMENT_NOT_FOUND
    assert mutations_since(ws, before) == []


def test_a_raw_requirement_is_refused():
    ws, _, _, before = build_apply_workspace()
    raw = next(r for r in ws.requirements.values() if r.type_name == "Raw")
    set_state(ws, raw, "Apply")
    assert (
        apply_standard_requirement(ws, raw.id).code is Code.NOT_A_STANDARD_REQUIREMENT
    )
    assert mutations_since(ws, before) == []


@pytest.mark.parametrize("state", ["Draft", "Process", "Review", "Ready"])
def test_any_other_state_is_refused(state):
    ws, requirement, _, before = build_apply_workspace()
    set_state(ws, requirement, state)
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_NOT_IN_APPLY
    assert state_of(ws, requirement) == state
    assert mutations_since(ws, before) == []


def test_already_applied_is_normal_and_changes_nothing():
    ws, requirement, _, _ = build_apply_workspace(proposals=(proposal(),))
    apply(ws, requirement)
    before = len(ws.mutations)
    calls_before = len(ws.calls)
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_ALREADY_APPLIED
    assert result.is_normal
    assert mutations_since(ws, before) == []
    assert ws.calls[calls_before:] == ["read_requirement"]


def test_already_applied_does_not_repair_or_overclaim():
    """A manual Applied with the Root still in Draft is reported, not fixed."""
    ws, requirement, root, before = build_apply_workspace(proposals=(proposal(),))
    set_state(ws, requirement, "Applied")
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_ALREADY_APPLIED
    assert "not that every Apply invariant holds" in result.message
    assert root_node(ws, root).folder_id == "f-draft"
    assert edges(ws, requirement.id) == set()
    assert mutations_since(ws, before) == []


def test_a_read_failure_is_reported_without_mutation():
    ws, requirement, _, before = build_apply_workspace()
    ws.failures["read_requirement"] = FiberyError("reset")
    result = apply(ws, requirement)
    assert result.code is Code.FIBERY_READ_FAILED
    assert mutations_since(ws, before) == []


# -- relations --------------------------------------------------------------


def test_zero_confirmed_proposals_writes_no_relation():
    ws, requirement, _, before = build_apply_workspace()
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert result.relations_added == ()
    assert not any(m.startswith("add_") for m in mutations_since(ws, before))


def test_one_depends_on_is_written_and_the_inverse_appears():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert result.relations_added == (f"DEPENDS_ON {TARGET_ID}",)
    assert edges(ws, requirement.id) == {(DEPENDS, TARGET_ID)}
    assert ws.inverse_relations(TARGET_ENTITY).depends_on == (REQUIREMENT_ID,)
    assert mutations_since(ws, before)[0] == (
        f"add_depends_on {requirement.id} -> {TARGET_ENTITY}"
    )


def test_one_affects_is_written_and_the_inverse_appears():
    ws, requirement, _, _ = build_apply_workspace(proposals=(proposal(AFFECTS),))
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert edges(ws, requirement.id) == {(AFFECTS, TARGET_ID)}
    assert ws.inverse_relations(TARGET_ENTITY).affects == (REQUIREMENT_ID,)


def test_mixed_proposals_are_all_written_once():
    others = (standard(), standard(OTHER_ID, OTHER_ENTITY))
    proposals = (
        proposal(DEPENDS, TARGET_ID),
        proposal(AFFECTS, TARGET_ID),
        proposal(DEPENDS, OTHER_ID),
    )
    ws, requirement, _, before = build_apply_workspace(
        proposals=proposals, others=others
    )
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert edges(ws, requirement.id) == {
        (DEPENDS, TARGET_ID),
        (AFFECTS, TARGET_ID),
        (DEPENDS, OTHER_ID),
    }
    adds = [m for m in mutations_since(ws, before) if m.startswith("add_")]
    assert len(adds) == 3


def test_an_existing_edge_is_satisfied_without_a_write():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(DEPENDS),))
    ws.depends_on_ids[requirement.id] = [TARGET_ENTITY]
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert result.relations_present == (f"DEPENDS_ON {TARGET_ID}",)
    assert result.relations_added == ()
    assert not any(m.startswith("add_") for m in mutations_since(ws, before))
    assert ws.depends_on_ids[requirement.id] == [TARGET_ENTITY]


def test_rejected_and_unresolved_proposals_are_never_written():
    others = (standard(), standard(OTHER_ID, OTHER_ENTITY))
    proposals = (proposal(DEPENDS, TARGET_ID), proposal(AFFECTS, OTHER_ID))
    verifications = [
        confirmed("DEPENDS_ON", TARGET_ID, outcome="REJECTED"),
        confirmed("AFFECTS", OTHER_ID, outcome="UNRESOLVED"),
    ]
    ws, requirement, _, before = build_apply_workspace(
        proposals=proposals, verifications=verifications, others=others
    )
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert edges(ws, requirement.id) == set()
    assert not any(m.startswith("add_") for m in mutations_since(ws, before))


def test_existing_unrelated_edges_are_preserved():
    others = (standard(), standard(OTHER_ID, OTHER_ENTITY))
    ws, requirement, _, _ = build_apply_workspace(
        proposals=(proposal(DEPENDS, TARGET_ID),), others=others
    )
    ws.affects_ids[requirement.id] = [OTHER_ENTITY]
    apply(ws, requirement)
    assert edges(ws, requirement.id) == {(DEPENDS, TARGET_ID), (AFFECTS, OTHER_ID)}
    assert not any(m.startswith("remove") for m in ws.mutations)


def test_targets_in_any_state_are_accepted():
    others = tuple(
        standard(f"SDLC-FR-00{i}", f"std-uuid-{i}", state=state)
        for i, state in enumerate(
            ["Draft", "Process", "Review", "Ready", "Apply", "Applied"], start=10
        )
    )
    proposals = tuple(proposal(DEPENDS, o.requirement_id) for o in others)
    ws, requirement, _, _ = build_apply_workspace(proposals=proposals, others=others)
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert len(edges(ws, requirement.id)) == 6


# -- the Root Document move -------------------------------------------------


def test_the_same_root_moves_from_draft_to_approved_with_its_body():
    ws, requirement, root, _ = build_apply_workspace()
    body = ws.content[root.secret]
    children = child_ids(ws, root)
    apply(ws, requirement)
    moved = root_node(ws, root)
    assert moved.id == root.id
    assert moved.secret == root.secret
    assert moved.folder_id == "f-approved"
    assert ws.content[root.secret] == body
    assert child_ids(ws, root) == children
    assert (
        len([d for d in ws.documents if d.entity_public_id == requirement.public_id])
        == 1
    )


def test_children_keep_their_parent_and_are_never_written():
    ws, requirement, root, before = build_apply_workspace(proposals=(proposal(),))
    children_before = {
        d.id: (d.parent_document_id, d.folder_id, ws.content[d.secret])
        for d in ws.documents
        if d.parent_document_id == root.id
    }
    assert len(children_before) == 2
    apply(ws, requirement)
    children_after = {
        d.id: (d.parent_document_id, d.folder_id, ws.content[d.secret])
        for d in ws.documents
        if d.parent_document_id == root.id
    }
    assert children_after == children_before
    assert not any(
        m.startswith("set_document_folder") and root.id not in m
        for m in mutations_since(ws, before)
    )


def test_a_root_already_in_approved_is_not_moved_again():
    ws, requirement, root, _ = build_apply_workspace()
    ws.set_document_folder(root.id, "f-approved")
    before = len(ws.mutations)
    result = apply(ws, requirement)
    assert result.code is Code.REQUIREMENT_APPLIED
    assert normative_writes(ws, before) == [
        f"set_requirement_state {requirement.id} Applied"
    ]


def test_a_root_in_an_unexpected_folder_is_refused():
    ws, requirement, root, _ = build_apply_workspace(proposals=(proposal(),))
    ws.set_document_folder(root.id, "f-raw")
    before = len(ws.mutations)
    result = apply(ws, requirement)
    assert result.code is Code.PROJECT_STRUCTURE_INVALID
    assert mutations_since(ws, before) == []
    assert root_node(ws, root).folder_id == "f-raw"
    assert state_of(ws, requirement) == "Apply"


def test_a_root_move_that_does_not_read_back_is_not_applied():
    ws, requirement, _, _ = build_apply_workspace()
    ws.set_document_folder = lambda document_id, folder_id: None
    result = apply(ws, requirement)
    assert result.code is Code.VALIDATION_FAILED
    assert state_of(ws, requirement) == "Apply"


# -- the final transition ---------------------------------------------------


def test_applied_is_written_last_and_read_back():
    ws, requirement, _, before = build_apply_workspace(proposals=(proposal(),))
    apply(ws, requirement)
    writes = normative_writes(ws, before)
    assert writes[-1] == f"set_requirement_state {requirement.id} Applied"
    reads_after_write = ws.calls[ws.calls.index("set_requirement_state") :]
    assert "read_requirement" in reads_after_write


def test_a_silently_ignored_applied_write_is_never_reported_as_applied():
    ws, requirement, _, _ = build_apply_workspace()
    ws.set_requirement_state = lambda entity_id, state: None
    result = apply(ws, requirement)
    assert result.code is Code.PARTIAL_APPLY
    assert "VALIDATION_FAILED" in result.details
    assert state_of(ws, requirement) == "Apply"


def test_revision_is_never_changed():
    ws, requirement, _, _ = build_apply_workspace(proposals=(proposal(),))
    apply(ws, requirement)
    assert ws.requirements[requirement.id].revision == requirement.revision
    assert not any("revision" in m.lower() for m in ws.mutations)


# -- hard immutability ------------------------------------------------------


def test_only_the_three_write_kinds_ever_happen():
    others = (standard(), standard(OTHER_ID, OTHER_ENTITY))
    ws, requirement, root, before = build_apply_workspace(
        proposals=(proposal(DEPENDS, TARGET_ID), proposal(AFFECTS, OTHER_ID)),
        others=others,
    )
    documents = dict(ws.content)
    others_before = {k: v for k, v in ws.requirements.items() if k != requirement.id}
    apply(ws, requirement)
    assert mutations_since(ws, before) == [
        f"add_depends_on {requirement.id} -> {TARGET_ENTITY}",
        f"add_affects {requirement.id} -> {OTHER_ENTITY}",
        f"set_document_folder {root.id} f-approved",
        f"set_requirement_state {requirement.id} Applied",
    ]
    assert ws.content == documents, (
        "no Root, Process Result or Review Result body write"
    )
    assert {
        k: v for k, v in ws.requirements.items() if k != requirement.id
    } == others_before


def test_no_model_runtime_can_reach_apply():
    parameters = inspect.signature(apply_standard_requirement).parameters
    assert not any("model" in name or "runtime" in name for name in parameters)


def test_the_final_invariant_holds_after_a_normal_application():
    others = (standard(), standard(OTHER_ID, OTHER_ENTITY))
    ws, requirement, root, _ = build_apply_workspace(
        proposals=(proposal(DEPENDS, TARGET_ID), proposal(AFFECTS, OTHER_ID)),
        others=others,
    )
    body = ws.content[root.secret]
    artifacts = {
        d.name: ws.content[d.secret]
        for d in ws.documents
        if d.parent_document_id == root.id
    }
    result = apply(ws, requirement)
    stored = ws.requirements[requirement.id]
    assert result.code is Code.REQUIREMENT_APPLIED
    assert (stored.type_name, stored.state, stored.revision) == (
        "Standard",
        "Applied",
        1,
    )
    assert root_node(ws, root).folder_id == "f-approved"
    assert ws.content[root.secret] == body
    assert edges(ws, requirement.id) == {(DEPENDS, TARGET_ID), (AFFECTS, OTHER_ID)}
    assert {
        d.name: ws.content[d.secret]
        for d in ws.documents
        if d.parent_document_id == root.id
    } == artifacts
    assert result.created == [
        f"relation DEPENDS_ON {TARGET_ID}",
        f"relation AFFECTS {OTHER_ID}",
        "Root Document Folder = Approved",
        "State = Applied",
    ] or tuple(result.created) == (
        f"relation DEPENDS_ON {TARGET_ID}",
        f"relation AFFECTS {OTHER_ID}",
        "Root Document Folder = Approved",
        "State = Applied",
    )


# -- fake fidelity: the verified Fibery behaviours --------------------------


def test_the_fake_treats_a_repeated_add_as_a_no_op():
    """Constraint 26, verified live: membership is a set."""
    ws, requirement, _, _ = build_apply_workspace()
    ws.add_depends_on(requirement.id, TARGET_ENTITY)
    ws.add_depends_on(requirement.id, TARGET_ENTITY)
    assert ws.depends_on_ids[requirement.id] == [TARGET_ENTITY]
    assert ws.inverse_relations(TARGET_ENTITY).depends_on == (REQUIREMENT_ID,)


def test_the_fake_moves_the_same_document_and_leaves_children_alone():
    """Constraints 24 and 25, verified live."""
    ws, _, root, _ = build_apply_workspace(proposals=(proposal(),))
    children = {
        (d.id, d.parent_document_id, d.folder_id)
        for d in ws.documents
        if d.parent_document_id == root.id
    }
    ws.set_document_folder(root.id, "f-approved")
    moved = root_node(ws, root)
    assert (moved.id, moved.secret, moved.folder_id) == (
        root.id,
        root.secret,
        "f-approved",
    )
    assert {
        (d.id, d.parent_document_id, d.folder_id)
        for d in ws.documents
        if d.parent_document_id == root.id
    } == children
    assert all(folder is None for _, _, folder in children)


def test_the_fake_lookup_reports_ambiguity_with_at_most_two_rows():
    ws, _, _, _ = build_apply_workspace(
        others=(
            standard(),
            standard(TARGET_ID, "std-uuid-dup"),
            standard(TARGET_ID, "std-uuid-dup2"),
        )
    )
    assert len(ws.find_requirements_by_requirement_id(TARGET_ID)) == 2
    assert ws.find_requirements_by_requirement_id("SDLC-FR-9999") == []
