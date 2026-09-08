"""Standard Process must not overwrite changes made after it captured its input.

Reproduced from the source audit: the processor reads Root content X, a human
changes the Root to Y while the model runs on X, and the processor persists
its output Z, rewrites Y with Z and reports success. Every scenario here runs
the real `process_standard_requirement` entry point; the external changes are
made by test doubles standing in for a human or another writer, never by the
processor, and the assertions separate the two.
"""

from __future__ import annotations

import pytest

from processor_fake import FakeModelRuntime
from sdlc.fibery_workspace import DocumentNode, FiberyError, RequirementRecord
from sdlc.model_runtime import ModelResponse
from sdlc.results import StandardProcessResultCode as Code
from sdlc.standard_processor import process_standard_requirement
from standard_fake import (
    analysis_output,
    build_standard_workspace,
    process_results,
    rendered_document,
    set_state,
)

OUTPUT = analysis_output()
BULLETED = analysis_output(
    {"requirement": "The runtime must:\n- refuse API keys\n- refuse OpenRouter"}
)
HUMAN_EDIT = "\n## Human note\n\nEdited while the model was running.\n"


def run(ws, record, model):
    return process_standard_requirement(ws, model, record.id)


def root_of(ws, record):
    [doc] = ws.documents_attached_to_requirement(record.public_id)
    return next(d for d in ws.documents if d.id == doc.id)


def processor_writes(ws, before):
    """Every write the processor issued after `before`, by kind."""
    return [
        m
        for m in ws.mutations[before:]
        if m.split(" ")[0]
        in {
            "write_content",
            "create_child_document",
            "set_requirement_state",
            "set_requirement_type",
            "set_requirement_id",
            "create_requirement_document",
        }
    ]


class ChangingModelRuntime:
    """A model stub that changes the workspace while it 'runs'.

    Stands in for a human or another writer acting during the model call.
    Those changes are made through the fake's data directly, so they never
    appear in the fake's mutation log, which records processor writes only.
    """

    def __init__(self, response, change):
        self.response = response
        self.change = change
        self.calls = 0

    @property
    def was_invoked(self):
        return self.calls > 0

    def run(self, prompt, context=""):
        self.calls += 1
        self.change()
        return ModelResponse(text=self.response, runtime="fake", model=None)


def after_nth_call(ws, method, n, change):
    """Run `change` right after the Nth call of a workspace read."""
    original = getattr(ws, method)
    seen = {"n": 0}

    def wrapped(*args, **kwargs):
        value = original(*args, **kwargs)
        seen["n"] += 1
        if seen["n"] == n:
            change()
        return value

    setattr(ws, method, wrapped)


def fail_nth_call(ws, method, n):
    original = getattr(ws, method)
    seen = {"n": 0}

    def wrapped(*args, **kwargs):
        seen["n"] += 1
        if seen["n"] == n:
            raise FiberyError("induced read failure")
        return original(*args, **kwargs)

    setattr(ws, method, wrapped)


# -- 1. the audited defect: a human edit during model.run -------------------


def test_a_human_edit_during_the_model_call_is_preserved():
    ws, std, root = build_standard_workspace()
    original_body = ws.content[root.secret]
    edited = original_body + HUMAN_EDIT
    before = len(ws.mutations)

    def human_edits_root():
        ws.content[root.secret] = edited

    model = ChangingModelRuntime(OUTPUT, human_edits_root)
    result = run(ws, std, model)

    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert not result.is_normal
    assert model.calls == 1, "one invocation, no automatic retry"
    assert result.model_invoked, "the conflict must not claim no model ran"
    assert ws.content[root.secret] == edited, "the human edit is preserved"
    assert process_results(ws) == [], "the stale output is not persisted"
    assert processor_writes(ws, before) == []
    assert ws.requirements[std.id].state == "Process"
    assert (
        "Root Document" in " ".join(result.details) or "Root Document" in result.message
    )


# -- 2. external State change during model.run ------------------------------


@pytest.mark.parametrize("state", ["Draft", "Review", "Ready", "Applied"])
def test_an_external_state_change_during_the_model_call_is_kept(state):
    ws, std, root = build_standard_workspace()
    body = ws.content[root.secret]
    before = len(ws.mutations)

    model = ChangingModelRuntime(OUTPUT, lambda: set_state(ws, std, state))
    result = run(ws, std, model)

    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert ws.requirements[std.id].state == state, "the external State stands"
    assert ws.content[root.secret] == body
    assert process_results(ws) == []
    assert processor_writes(ws, before) == []


# -- 3. Root replacement or detachment during model.run ---------------------


def test_a_replaced_root_during_the_model_call_is_not_overwritten():
    ws, std, root = build_standard_workspace()
    old_body = ws.content[root.secret]
    replacement = DocumentNode(
        id="std-doc-2",
        name=root.name,
        folder_id=root.folder_id,
        entity_public_id=std.public_id,
        secret="replacement-secret",
    )
    before = len(ws.mutations)

    def human_replaces_root():
        ws.documents.remove(next(d for d in ws.documents if d.id == root.id))
        ws.documents.append(replacement)
        ws.content[replacement.secret] = "# Replacement\n\nWritten by hand.\n"

    result = run(ws, std, ChangingModelRuntime(OUTPUT, human_replaces_root))

    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert ws.content[root.secret] == old_body
    assert ws.content[replacement.secret] == "# Replacement\n\nWritten by hand.\n"
    assert process_results(ws) == []
    assert processor_writes(ws, before) == []


def test_a_detached_root_during_the_model_call_is_a_conflict():
    ws, std, root = build_standard_workspace()
    old_body = ws.content[root.secret]
    before = len(ws.mutations)

    def human_detaches_root():
        ws.documents.remove(next(d for d in ws.documents if d.id == root.id))

    result = run(ws, std, ChangingModelRuntime(OUTPUT, human_detaches_root))

    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert ws.content[root.secret] == old_body
    assert processor_writes(ws, before) == []


def test_a_legacy_folder_change_during_the_model_call_is_not_drift():
    """`fibery/Folder` is presentation metadata: moving it is not a conflict."""
    ws, std, root = build_standard_workspace()

    result = run(
        ws,
        std,
        ChangingModelRuntime(
            OUTPUT, lambda: ws.relocate_legacy_folder(root.id, "f-approved")
        ),
    )

    assert result.code is Code.REQUIREMENT_PROCESSED
    assert root_of(ws, std).folder_id == "f-approved"
    assert len(process_results(ws)) == 1
    assert ws.requirements[std.id].state == "Review"


# -- metadata drift during model.run ----------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        {"revision": 2},
        {"title": "Renamed by hand"},
        {"requirement_id": "SDLC-FR-9999"},
        {"project_id": "p-2"},
    ],
)
def test_protected_metadata_drift_during_the_model_call_is_a_conflict(change):
    ws, std, root = build_standard_workspace()
    body = ws.content[root.secret]
    before = len(ws.mutations)

    def human_changes_metadata():
        ws.requirements[std.id] = RequirementRecord(
            **{**ws.requirements[std.id].__dict__, **change}
        )

    result = run(ws, std, ChangingModelRuntime(OUTPUT, human_changes_metadata))

    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert ws.content[root.secret] == body
    assert process_results(ws) == []
    assert processor_writes(ws, before) == []


# -- 4. edit after the Process Result is persisted, before the rewrite ------


def test_an_edit_after_result_persistence_keeps_the_result_and_the_edit():
    ws, std, root = build_standard_workspace()
    original_body = ws.content[root.secret]
    edited = original_body + HUMAN_EDIT
    # The Process Result is the first child Document created; edit right after.
    after_nth_call(
        ws,
        "create_child_document",
        1,
        lambda: ws.content.__setitem__(root.secret, edited),
    )
    before = len(ws.mutations)

    result = run(ws, std, FakeModelRuntime([OUTPUT]))

    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert ws.content[root.secret] == edited
    assert len(process_results(ws)) == 1, "the persisted result is retained"
    assert any("Process Result 0001" in item for item in result.created)
    assert f"write_content {root.secret}" not in ws.mutations[before:]
    assert not any(m.startswith("set_requirement_state") for m in ws.mutations[before:])
    assert ws.requirements[std.id].state == "Process"


# -- 5. resumed invocation with a change after its context read -------------


def test_a_resume_detects_a_change_made_after_its_context_read():
    ws, std, root = build_standard_workspace()
    original = ws.write_document_content
    seen = {"n": 0}

    def fail_root_write(secret, markdown):
        seen["n"] += 1
        if seen["n"] == 2:
            raise FiberyError("induced")
        return original(secret, markdown)

    ws.write_document_content = fail_root_write
    first = run(ws, std, FakeModelRuntime([OUTPUT]))
    assert first.code is Code.PARTIAL_PROCESSING
    ws.write_document_content = original
    set_state(ws, std, "Process")
    edited = ws.content[root.secret] + HUMAN_EDIT
    # Content reads while loading the context: 1 the Process Result, 2 the
    # Root. The edit lands right after the Root was captured, so only the
    # pre-rewrite guard's own fresh read can see it.
    after_nth_call(
        ws,
        "read_document_content",
        2,
        lambda: ws.content.__setitem__(root.secret, edited),
    )
    before = len(ws.mutations)

    # A11: the resume is explicit; the drift guard still runs inside it.
    model = FakeModelRuntime([analysis_output({"title": "Different"})])
    result = process_standard_requirement(
        ws, model, std.id, resume_result=process_results(ws)[0].id
    )

    assert not model.was_invoked, "the existing result is reused"
    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert "the Root Document content changed" in result.details
    assert ws.content[root.secret] == edited
    assert len(process_results(ws)) == 1
    assert processor_writes(ws, before) == []


# -- 6. change after the rewrite verification, before the transition --------


def test_an_edit_after_the_rewrite_blocks_the_transition_without_rollback():
    ws, std, root = build_standard_workspace()
    edited_after = {"done": False}

    def human_edits_after_rewrite():
        ws.content[root.secret] = ws.content[root.secret] + HUMAN_EDIT
        edited_after["done"] = True

    # Requirement reads: 1 context, 2 pre-persist guard, 3 pre-rewrite guard,
    # 4 pre-transition guard. The edit lands right after the fourth, so the
    # rewrite has completed and only that guard's content read can see it.
    after_nth_call(ws, "read_requirement", 4, human_edits_after_rewrite)

    result = run(ws, std, FakeModelRuntime([OUTPUT]))

    assert edited_after["done"]
    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert not any(m.startswith("set_requirement_state") for m in ws.mutations)
    assert ws.requirements[std.id].state == "Process"
    assert HUMAN_EDIT.strip() in ws.content[root.secret], "no rollback"
    assert any("Process Result 0001" in item for item in result.created)
    assert any("Root Document rewritten" in item for item in result.created)


def test_a_state_change_after_the_rewrite_blocks_the_transition():
    ws, std, _ = build_standard_workspace()
    # The State changes right after the pre-rewrite guard captured the entity,
    # so the rewrite proceeds and the pre-transition guard is what sees it.
    after_nth_call(ws, "read_requirement", 3, lambda: set_state(ws, std, "Ready"))

    result = run(ws, std, FakeModelRuntime([OUTPUT]))

    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert ws.requirements[std.id].state == "Ready", "the external State stands"
    assert not any(m.startswith("set_requirement_state") for m in ws.mutations)
    assert any("Root Document rewritten" in item for item in result.created)


# -- 7. no concurrent change: normal and resume behaviour unchanged ---------


def test_normal_processing_still_reaches_review():
    ws, std, root = build_standard_workspace()
    model = FakeModelRuntime([OUTPUT])
    result = run(ws, std, model)
    assert result.code is Code.REQUIREMENT_PROCESSED
    assert result.model_invoked
    assert ws.requirements[std.id].state == "Review"
    assert ws.content[root.secret] == rendered_document()


def test_a_legitimate_incomplete_rewrite_still_resumes():
    ws, std, _ = build_standard_workspace()
    original = ws.write_document_content
    seen = {"n": 0}

    def fail_root_write(secret, markdown):
        seen["n"] += 1
        if seen["n"] == 2:
            raise FiberyError("induced")
        return original(secret, markdown)

    ws.write_document_content = fail_root_write
    run(ws, std, FakeModelRuntime([OUTPUT]))
    ws.write_document_content = original
    set_state(ws, std, "Process")

    model = FakeModelRuntime([OUTPUT])
    result = process_standard_requirement(
        ws, model, std.id, resume_result=process_results(ws)[0].id
    )

    assert not model.was_invoked
    assert result.code is Code.REQUIREMENT_PROCESSED
    assert len(process_results(ws)) == 1
    assert ws.requirements[std.id].state == "Review"


# -- 8. Fibery formatting-only re-serialization is not a conflict -----------


def test_fibery_reserialization_never_looks_like_a_concurrent_edit():
    ws, std, _ = build_standard_workspace()
    assert ws.reserializes
    ws.content["std-secret"] = "# SDLC-FR-0031 — T\n\n## Requirement\n\n- one\n- two\n"
    result = run(ws, std, FakeModelRuntime([BULLETED]))
    assert result.code is Code.REQUIREMENT_PROCESSED
    assert ws.requirements[std.id].state == "Review"


# -- 9. a fresh read that fails at a guard stops the write ------------------


def test_a_failed_fresh_read_before_the_rewrite_writes_nothing_more():
    ws, std, root = build_standard_workspace()
    # Requirement reads: 1 context, 2 pre-persist guard, 3 pre-rewrite guard.
    fail_nth_call(ws, "read_requirement", 3)

    result = run(ws, std, FakeModelRuntime([OUTPUT]))

    assert result.code is Code.PARTIAL_PROCESSING
    assert "FIBERY_READ_FAILED" in result.details
    assert f"write_content {root.secret}" not in ws.mutations
    assert not any(m.startswith("set_requirement_state") for m in ws.mutations)
    assert len(process_results(ws)) == 1


def test_a_failed_fresh_read_before_persistence_persists_nothing():
    ws, std, root = build_standard_workspace()
    fail_nth_call(ws, "read_requirement", 2)

    result = run(ws, std, FakeModelRuntime([OUTPUT]))

    assert result.code is Code.FIBERY_READ_FAILED
    assert process_results(ws) == []
    assert f"write_content {root.secret}" not in ws.mutations
