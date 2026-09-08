"""Stage behaviour under the normative-tree contract, through real entry points.

Spec: docs/specs/Requirement-Normative-Tree-Binding-v0.1.md §§6-11.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from apply_fake import build_apply_workspace, proposal
from processor_fake import FakeModelRuntime, build_workspace, reserialize_like_fibery
from ready_fake import build_ready_workspace, mutations_since
from review_fake import (
    add_process_iteration,
    build_review_workspace,
    review_output,
    review_results,
    stored_review,
    tree_manifest,
    verify_relation,
)
from sdlc.fibery_workspace import FiberyError
from sdlc.model_runtime import ModelResponse
from sdlc.process_result import parse_process_result, render_process_result
from sdlc.raw_processor import process_raw_requirement
from sdlc.ready_decision import (
    approve_standard_requirement,
    rework_standard_requirement,
)
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.results import ApplyResultCode as ApplyCode
from sdlc.results import ProcessResultCode as RawCode
from sdlc.results import ReadyDecisionResultCode as ReadyCode
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.review_result import render_review_result
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import (
    REQUIREMENT_ID,
    analysis_output,
    build_standard_workspace,
    process_results,
    set_state,
)
from test_empty_result_recovery import PROCESS, REVIEW, leave_a_shell, model_for
from tree_fake import add_child, edit, remove_node, replace_node

CHILD_TEXT = "The child states the retry budget: three attempts."
GRANDCHILD_TEXT = "The grandchild states the backoff: one second, then two."


def with_children(ws, root):
    child = add_child(ws, root, "Retry budget", CHILD_TEXT + "\n", document_id="c1")
    grandchild = add_child(
        ws, child, "Backoff", GRANDCHILD_TEXT + "\n", document_id="c1-1"
    )
    return child, grandchild


def run_process(ws, requirement, responses=None, **options):
    model = FakeModelRuntime(responses or [analysis_output()])
    return process_standard_requirement(ws, model, requirement.id, **options), model


def run_review(ws, requirement, responses=None, **options):
    model = FakeModelRuntime(responses or [review_output()])
    return review_standard_requirement(ws, model, requirement.id, **options), model


def stored_process(ws, index=-1):
    node = process_results(ws)[index]
    return parse_process_result(reserialize_like_fibery(ws.content[node.secret]))


def make_legacy_process(ws, index=-1):
    """Rewrite a persisted Process Result as a 0.1 Root-only artifact."""
    node = process_results(ws)[index]
    result = stored_process(ws, index)
    ws.content[node.secret] = render_process_result(
        replace(result, version="0.1", input_tree=None, output_tree=None)
    )


def make_legacy_review(ws, index=-1):
    node = review_results(ws)[index]
    result = stored_review(ws, index)
    ws.content[node.secret] = render_review_result(
        replace(result, version="0.1", reviewed_tree=None)
    )


# -- Process: the tree is the input --------------------------------------------


def test_process_sends_every_normative_descendant_with_its_marker():
    ws, requirement, root = build_standard_workspace()
    child, grandchild = with_children(ws, root)
    add_child(ws, root, f"{REQUIREMENT_ID} — Review Result 0001", "PRIOR-VERDICT")
    result, model = run_process(ws, requirement)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    context = model.calls[0]["context"]
    assert CHILD_TEXT in context and GRANDCHILD_TEXT in context
    assert f"| id: {child.id} | parent: {root.id} | depth: 1 -->" in context
    assert f"| id: {grandchild.id} | parent: {child.id} | depth: 2 -->" in context
    assert "PRIOR-VERDICT" not in context


def test_process_persists_a_tree_bound_result_over_the_tree_it_read():
    ws, requirement, root = build_standard_workspace()
    with_children(ws, root)
    before = tree_manifest(ws, root)
    result, _ = run_process(ws, requirement)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED
    stored = stored_process(ws)
    assert stored.is_tree_bound and stored.version == "0.3"
    assert stored.input_tree == before
    assert stored.output_tree == tree_manifest(ws, root)
    assert stored.output_tree.document_ids == before.document_ids


@pytest.mark.parametrize("change", ["edit", "add", "remove", "rename", "reparent"])
def test_a_child_only_change_is_a_new_iteration_not_a_no_change(change):
    ws, requirement, root = build_standard_workspace()
    child, grandchild = with_children(ws, root)
    first, _ = run_process(ws, requirement)
    assert first.code is ProcessCode.REQUIREMENT_PROCESSED
    set_state(ws, requirement, "Process")
    unchanged, model = run_process(ws, requirement)
    assert unchanged.code is ProcessCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked

    if change == "edit":
        edit(ws, grandchild, "The backoff is now exponential.\n")
    elif change == "add":
        add_child(ws, root, "Scope", "A new normative section.\n", document_id="c2")
    elif change == "remove":
        remove_node(ws, grandchild)
    elif change == "rename":
        replace_node(ws, child, name="Retry budget (revised)")
    else:
        replace_node(ws, grandchild, parent_document_id=root.id)
    result, model = run_process(ws, requirement)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert result.iteration == 2 and model.was_invoked
    assert stored_process(ws).input_tree == stored_process(ws).output_tree or (
        stored_process(ws).input_tree.fingerprint
        != stored_process(ws, 0).output_tree.fingerprint
    )


def test_a_tree_bound_iteration_is_resumed_only_over_its_own_input_tree():
    """The output was never applied; the Root still holds the input."""
    ws, requirement, root = build_standard_workspace()
    child, _ = with_children(ws, root)
    original_root = ws.content[root.secret]
    first, _ = run_process(ws, requirement)
    assert first.code is ProcessCode.REQUIREMENT_PROCESSED
    set_state(ws, requirement, "Process")
    ws.content[root.secret] = original_root  # the rewrite was lost
    refused, model = run_process(ws, requirement)  # A11: ambiguous, refused
    assert refused.code is ProcessCode.PROCESSING_STATE_CONFLICT
    assert not model.was_invoked
    model = FakeModelRuntime([analysis_output()])
    resumed = process_standard_requirement(
        ws, model, requirement.id, resume_result=process_results(ws)[0].id
    )
    assert resumed.code is ProcessCode.REQUIREMENT_PROCESSED
    assert resumed.iteration == 1 and not model.was_invoked

    set_state(ws, requirement, "Process")
    ws.content[root.secret] = original_root
    edit(ws, child, "A child edit between the runs.\n")
    fresh, model = run_process(ws, requirement)
    assert fresh.code is ProcessCode.REQUIREMENT_PROCESSED
    assert fresh.iteration == 2 and model.was_invoked


def test_a_legacy_root_only_result_is_never_replayed():
    """A 0.1 result binds no tree, so even an unchanged Root gets a fresh,
    tree-bound iteration; the legacy artifact stays as history."""
    ws, requirement, root = build_standard_workspace()
    with_children(ws, root)
    first, _ = run_process(ws, requirement)
    assert first.code is ProcessCode.REQUIREMENT_PROCESSED
    make_legacy_process(ws)
    legacy_text = ws.content[process_results(ws)[0].secret]
    set_state(ws, requirement, "Process")

    result, model = run_process(ws, requirement)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert result.iteration == 2 and model.was_invoked
    assert "Older-format Process Result 1 (version 0.1)" in result.message
    assert ws.content[process_results(ws)[0].secret] == legacy_text
    assert stored_process(ws).is_tree_bound
    assert not stored_process(ws, 0).is_tree_bound


class MutatesTreeDuringProcess:
    """A model runtime that, while 'thinking', changes the tree in Fibery."""

    def __init__(self, ws, mutate, response):
        self.ws, self.mutate, self.response = ws, mutate, response
        self.calls = []

    def run(self, prompt, context=""):
        self.calls.append({"prompt": prompt, "context": context})
        self.mutate(self.ws)
        return ModelResponse(text=self.response, runtime="fake", model=None)


@pytest.mark.parametrize(
    "mutation",
    ["edit", "add", "remove", "rename", "reparent"],
)
def test_a_tree_change_during_the_model_call_drops_the_output(mutation):
    ws, requirement, root = build_standard_workspace()
    child, grandchild = with_children(ws, root)

    def mutate(ws):
        if mutation == "edit":
            edit(ws, grandchild, "changed under the model\n")
        elif mutation == "add":
            add_child(ws, root, "Late", "late\n", document_id="late")
        elif mutation == "remove":
            remove_node(ws, grandchild)
        elif mutation == "rename":
            replace_node(ws, child, name="Renamed under the model")
        else:
            replace_node(ws, grandchild, parent_document_id=root.id)

    root_before = ws.content[root.secret]
    before = len(ws.mutations)
    result = process_standard_requirement(
        ws, MutatesTreeDuringProcess(ws, mutate, analysis_output()), requirement.id
    )
    assert result.code is ProcessCode.PROCESSING_STATE_CONFLICT, result
    assert "while the model was running" in result.message
    assert ws.mutations[before:] == []
    assert process_results(ws) == []
    assert ws.content[root.secret] == root_before
    assert ws.requirements[requirement.id].state == "Process"


@pytest.mark.parametrize(
    "broken",
    ["foreign", "misplaced", "nested-under-artifact", "unreadable"],
)
def test_an_invalid_tree_refuses_process_before_the_model(broken):
    ws, requirement, root = build_standard_workspace()
    child, _ = with_children(ws, root)
    if broken == "foreign":
        add_child(ws, root, "SDLC-FR-0099 — Process Result 0001", "x")
    elif broken == "misplaced":
        add_child(ws, child, f"{REQUIREMENT_ID} — Process Result 0001", "x")
    elif broken == "nested-under-artifact":
        artifact = add_child(ws, root, f"{REQUIREMENT_ID} — Review Result 0001", "")
        add_child(ws, artifact, "Hidden", "x")
    else:
        ws.failures["read_document_content"] = FiberyError("timeout")
    before = len(ws.mutations)
    result, model = run_process(ws, requirement)
    assert result.code is (
        ProcessCode.FIBERY_READ_FAILED
        if broken == "unreadable"
        else ProcessCode.NORMATIVE_TREE_INVALID
    ), result
    assert not model.was_invoked and ws.mutations[before:] == []


# -- Review: the same tree, against Process evidence that produced it -----------


def test_review_sends_the_normative_children_to_the_reviewer():
    ws, requirement, root = build_standard_workspace()
    with_children(ws, root)
    processed, _ = run_process(ws, requirement)
    assert processed.code is ProcessCode.REQUIREMENT_PROCESSED
    result, model = run_review(ws, requirement)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    context = model.calls[0]["context"]
    assert "# Normative child documents" in context
    assert CHILD_TEXT in context and GRANDCHILD_TEXT in context
    assert stored_review(ws).reviewed_tree == tree_manifest(ws, root)
    assert stored_review(ws).reviewed_tree == stored_process(ws).output_tree


def test_review_refuses_legacy_process_evidence():
    ws, requirement, _, _ = build_review_workspace()
    make_legacy_process(ws)
    before = len(ws.mutations)
    result, model = run_review(ws, requirement)
    assert result.code is ReviewCode.NORMATIVE_TREE_EVIDENCE_REQUIRED, result
    assert "older format (version 0.1)" in result.message
    assert not model.was_invoked and ws.mutations[before:] == []
    assert review_results(ws) == []


@pytest.mark.parametrize("change", ["child-edit", "child-add"])
def test_review_refuses_a_tree_process_did_not_produce(change):
    ws, requirement, root, _ = build_review_workspace()
    child = add_child(ws, root, "Child", "before Process\n", document_id="c")
    add_process_iteration(ws, root, 2)  # coherent over Root + child
    if change == "child-edit":
        edit(ws, child, "edited after Process\n")
    else:
        add_child(ws, root, "Another", "added after Process\n", document_id="c2")
    before = len(ws.mutations)
    result, model = run_review(ws, requirement)
    assert result.code is ReviewCode.NORMATIVE_TREE_EVIDENCE_REQUIRED, result
    assert "run Process again" in result.message
    assert not model.was_invoked and ws.mutations[before:] == []


def test_a_child_edited_during_the_review_makes_it_stale():
    ws, requirement, root, _ = build_review_workspace()
    child = add_child(ws, root, "Child", "reviewed\n", document_id="c")
    add_process_iteration(ws, root, 2)

    def mutate(ws):
        edit(ws, child, "changed under the reviewer\n")

    result = review_standard_requirement(
        ws, MutatesTreeDuringProcess(ws, mutate, review_output()), requirement.id
    )
    assert result.code is ReviewCode.REVIEW_RESULT_STALE, result
    assert "A normative child Document changed after the review." in result.details
    assert any("content changed" in line for line in result.details)
    assert ws.requirements[requirement.id].state == "Review"
    assert len(review_results(ws)) == 1  # kept as evidence, not certified


def test_an_unchanged_tree_reviewed_by_a_tree_bound_review_is_no_change():
    ws, requirement, root, _ = build_review_workspace()
    add_child(ws, root, "Child", "c\n", document_id="c")
    add_process_iteration(ws, root, 2)
    first, _ = run_review(ws, requirement)
    assert first.code is ReviewCode.REQUIREMENT_REVIEWED
    set_state(ws, requirement, "Review")
    again, model = run_review(ws, requirement)
    assert again.code is ReviewCode.NO_CHANGES_TO_REVIEW, again
    assert not model.was_invoked


def test_a_legacy_review_is_not_reused_a_new_review_iteration_runs():
    ws, requirement, _, _ = build_review_workspace()
    first, _ = run_review(ws, requirement)
    assert first.code is ReviewCode.REQUIREMENT_REVIEWED
    make_legacy_review(ws)
    legacy_text = ws.content[review_results(ws)[0].secret]
    set_state(ws, requirement, "Review")
    result, model = run_review(ws, requirement)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert result.iteration == 2 and model.was_invoked
    assert ws.content[review_results(ws)[0].secret] == legacy_text
    assert stored_review(ws).is_tree_bound


# -- Ready and Apply: the fourth binding -------------------------------------


def ready_with_child():
    ws, requirement, root, _ = build_review_workspace()
    child = add_child(ws, root, "Child", "reviewed content\n", document_id="c")
    add_process_iteration(ws, root, 2)
    reviewed, _ = run_review(ws, requirement)
    assert reviewed.code is ReviewCode.REQUIREMENT_REVIEWED
    assert ws.requirements[requirement.id].state == "Ready"
    return ws, ws.requirements[requirement.id], root, child, len(ws.mutations)


@pytest.mark.parametrize("change", ["edit", "add", "remove", "reparent"])
def test_approval_refuses_a_child_change_after_the_review(change):
    ws, requirement, root, child, before = ready_with_child()
    if change == "edit":
        edit(ws, child, "edited after the review\n")
    elif change == "add":
        add_child(ws, root, "Late", "late\n", document_id="late")
    elif change == "remove":
        remove_node(ws, child)
    else:
        other = add_child(ws, root, "Other", "o\n", document_id="o")
        replace_node(ws, child, parent_document_id=other.id)
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is ReadyCode.REVIEW_RESULT_STALE, result
    assert any("child Document" in line for line in result.details) or change == "add"
    assert mutations_since(ws, before) == []
    assert ws.requirements[requirement.id].state == "Ready"


def test_approval_certifies_an_unchanged_tree():
    ws, requirement, _, _, before = ready_with_child()
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is ReadyCode.REQUIREMENT_APPROVED, result
    assert mutations_since(ws, before) == [
        f"set_requirement_state {requirement.id} Apply"
    ]


@pytest.mark.parametrize("legacy", ["process", "review", "both"])
def test_approval_refuses_legacy_evidence_even_without_children(legacy):
    ws, requirement, _, before = build_ready_workspace()
    if legacy in ("process", "both"):
        make_legacy_process(ws)
    if legacy in ("review", "both"):
        make_legacy_review(ws)
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is ReadyCode.NORMATIVE_TREE_EVIDENCE_REQUIRED, result
    assert "older-format evidence" in result.message and "rework" in result.message
    assert mutations_since(ws, before) == []


def test_rework_reads_no_evidence_and_works_over_legacy_or_invalid_trees():
    ws, requirement, root, before = build_ready_workspace()
    make_legacy_process(ws)
    make_legacy_review(ws)
    add_child(ws, root, "SDLC-FR-0099 — Process Result 0001", "foreign")
    result = rework_standard_requirement(ws, requirement.id)
    assert result.code is ReadyCode.REQUIREMENT_SENT_FOR_REWORK, result
    assert mutations_since(ws, before) == [
        f"set_requirement_state {requirement.id} Process"
    ]


def test_apply_refuses_a_child_edited_after_approval():
    ws, requirement, _, child, _ = ready_with_child()
    approved = approve_standard_requirement(ws, requirement.id)
    assert approved.code is ReadyCode.REQUIREMENT_APPROVED
    before = len(ws.mutations)
    edit(ws, child, "edited after approval\n")
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is ApplyCode.REVIEW_RESULT_STALE, result
    assert "A normative child Document changed after the review." in result.details
    assert ws.mutations[before:] == []
    assert ws.requirements[requirement.id].state == "Apply"


def test_apply_refuses_legacy_evidence():
    ws, requirement, _, before = build_apply_workspace()
    make_legacy_review(ws)
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is ApplyCode.NORMATIVE_TREE_EVIDENCE_REQUIRED, result
    assert mutations_since(ws, before) == []
    assert ws.requirements[requirement.id].state == "Apply"


def test_apply_rechecks_the_tree_before_applied():
    """A child edited after the first normative write is caught by the second
    checkpoint: the relation stays, Applied is refused."""
    ws, requirement, root, _ = build_apply_workspace(proposals=(proposal(),))
    child = add_child(ws, root, "Child", "reviewed\n", document_id="c")
    # Re-run the chain so the evidence covers the child.
    set_state(ws, requirement, "Review")
    add_process_iteration(ws, root, 2, relations=(proposal(),))
    reviewed, _ = run_review(
        ws, requirement, [review_output(relation_verifications=[verify_relation()])]
    )
    assert reviewed.code is ReviewCode.REQUIREMENT_REVIEWED, reviewed
    assert approve_standard_requirement(ws, requirement.id).code is (
        ReadyCode.REQUIREMENT_APPROVED
    )
    original = ws.add_depends_on

    def add_depends_on(entity_id, target_entity_id):
        edit(ws, child, "edited between the checkpoints\n")
        return original(entity_id, target_entity_id)

    ws.add_depends_on = add_depends_on
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is ApplyCode.PARTIAL_APPLY, result
    assert "A normative child Document changed after the review." in result.details
    assert ws.requirements[requirement.id].state == "Apply"
    assert any(m.startswith("add_depends_on") for m in ws.mutations)


# -- A3 recovery produces tree-bound evidence ---------------------------------


def test_process_recovery_fills_the_shell_with_a_tree_bound_result():
    ws, requirement, root, shell, _ = leave_a_shell(PROCESS)
    ws.failures.clear()
    add_child(ws, root, "Child", "normative child\n", document_id="c")
    before = tree_manifest(ws, root)
    result = process_standard_requirement(
        ws, model_for(PROCESS), requirement.id, recover_empty_result=shell.id
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    stored = parse_process_result(reserialize_like_fibery(ws.content[shell.secret]))
    assert stored.is_tree_bound and stored.input_tree == before


def test_review_recovery_fills_the_shell_with_a_tree_bound_result():
    ws, requirement, root, shell, _ = leave_a_shell(REVIEW)
    ws.failures.clear()
    result = review_standard_requirement(
        ws, model_for(REVIEW), requirement.id, recover_empty_result=shell.id
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert stored_review(ws).is_tree_bound
    assert stored_review(ws).reviewed_tree == tree_manifest(ws, root)


# -- A6 peers and RAW ---------------------------------------------------------


def test_a_peer_child_document_reaches_the_comparison_context():
    ws, requirement, _, _ = build_review_workspace()
    from sdlc.fibery_workspace import RequirementRecord

    peer = RequirementRecord(
        id="std-peer-41",
        public_id="41",
        requirement_id="SDLC-FR-0041",
        title="Fast responses",
        type_name="Standard",
        state="Applied",
        revision=1,
        project_id="p-1",
        source_fingerprint=None,
    )
    ws.requirements[peer.id] = peer
    from processor_fake import attach_peer_roots

    attach_peer_roots(ws, [peer])
    [peer_root] = [d for d in ws.documents if d.entity_public_id == "41"]
    add_child(ws, peer_root, "Latency detail", "PEER-CHILD-DETAIL p95 200 ms\n")
    result, model = run_review(ws, requirement)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert "PEER-CHILD-DETAIL" in model.calls[0]["context"]


def test_a_peer_with_an_invalid_tree_refuses_the_comparison_context():
    ws, requirement, _ = build_standard_workspace()
    from sdlc.fibery_workspace import RequirementRecord

    peer = RequirementRecord(
        id="std-peer-41",
        public_id="41",
        requirement_id="SDLC-FR-0041",
        title="Fast responses",
        type_name="Standard",
        state="Applied",
        revision=1,
        project_id="p-1",
        source_fingerprint=None,
    )
    ws.requirements[peer.id] = peer
    from processor_fake import attach_peer_roots

    attach_peer_roots(ws, [peer])
    [peer_root] = [d for d in ws.documents if d.entity_public_id == "41"]
    add_child(ws, peer_root, "SDLC-FR-0099 — Review Result 0001", "foreign")
    before = len(ws.mutations)
    result, model = run_process(ws, requirement)
    assert result.code is ProcessCode.COMPARISON_CONTEXT_INCOMPLETE, result
    assert "SDLC-FR-0041" in result.message
    assert not model.was_invoked and ws.mutations[before:] == []


def test_raw_skips_only_its_own_direct_processing_result():
    from sdlc.raw_processor import _read_document_tree

    ws, raw, root = build_workspace()
    add_child(ws, root, "SDLC-RAW-0007 — Processing Result", "OWN-OUTPUT")
    notes = add_child(ws, root, "Notes", "RAW-CHILD-NOTES\n", document_id="n")
    add_child(ws, notes, "Deeper", "RAW-GRANDCHILD\n", document_id="n-1")
    body = _read_document_tree(ws, raw, root)
    assert "RAW-CHILD-NOTES" in body and "RAW-GRANDCHILD" in body
    assert "OWN-OUTPUT" not in body


@pytest.mark.parametrize(
    "name, parent",
    [
        ("SDLC-RAW-0008 — Processing Result", "root"),
        ("SDLC-FR-0031 — Process Result 0001", "root"),
        ("SDLC-RAW-0007 — Processing Result", "child"),
    ],
    ids=["foreign-raw", "standard-artifact", "misplaced-own"],
)
def test_raw_refuses_foreign_or_misplaced_artifact_names(name, parent):
    ws, raw, root = build_workspace()
    child = add_child(ws, root, "Notes", "notes\n", document_id="n")
    add_child(ws, child if parent == "child" else root, name, "x", document_id="art")
    from processor_fake import candidate, model_output

    model = FakeModelRuntime([model_output([candidate()])])
    before = len(ws.mutations)
    result = process_raw_requirement(ws, model, raw.id)
    assert result.code is RawCode.NORMATIVE_TREE_INVALID, result
    assert result.details == ("art",)
    assert not model.was_invoked and ws.mutations[before:] == []
