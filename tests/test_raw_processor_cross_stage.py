"""A RAW retry must never claim candidates that moved on without it.

Reproduced from the source audit: a partial RAW run leaves candidate A in
Draft, A legitimately completes Standard Process, Review, Ready APPROVE and
Apply, and the RAW retry then adopts A by its deterministic id, demotes it to
Draft and overwrites its Approved Root Document with the old decomposition.

Every scenario here drives the real capability entry points on the shared
fake. Nothing bypasses Ready or Apply.
"""

from __future__ import annotations

import pytest

from processor_fake import FakeModelRuntime, build_workspace, candidate, model_output
from review_fake import review_output
from sdlc.fibery_workspace import FiberyError
from sdlc.processing_result import candidate_fibery_id
from sdlc.raw_processor import process_raw_requirement
from sdlc.ready_decision import approve_standard_requirement
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.results import ProcessResultCode
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import analysis_output, set_state

TWO = model_output([candidate(title="First"), candidate(title="Second")])
THREE = model_output([candidate(title=f"T{i}") for i in range(3)])
PROGRESSED_STATES = ["Process", "Review", "Ready", "Apply", "Applied"]


def reset_to_process(ws, raw):
    set_state(ws, raw, "Process")


def standards(ws):
    return [r for r in ws.requirements.values() if r.type_name == "Standard"]


def root_of(ws, record):
    [doc] = ws.documents_attached_to_requirement(record.public_id)
    return next(d for d in ws.documents if d.id == doc.id)


def fail_nth(ws, method, n):
    """Make `method` raise on its Nth call only."""
    original = getattr(ws, method)
    calls = {"n": 0}

    def flaky(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == n:
            raise FiberyError("induced")
        return original(*args, **kwargs)

    setattr(ws, method, flaky)
    return original


def partial_run(ws, raw, output, fail_on_candidate):
    """Run RAW processing so that candidate `fail_on_candidate` is not created."""
    original = fail_nth(ws, "create_requirement_with_id", fail_on_candidate)
    result = process_raw_requirement(ws, FakeModelRuntime([output]), raw.id)
    assert result.code is ProcessResultCode.PARTIAL_PROCESSING
    ws.create_requirement_with_id = original
    reset_to_process(ws, raw)
    return result


def complete_standard_chain(ws, record):
    """Draft -> Process -> Review -> Ready -> Apply -> Applied, for real."""
    set_state(ws, record, "Process")
    processed = process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), record.id
    )
    assert processed.code.value == "REQUIREMENT_PROCESSED", processed
    reviewed = review_standard_requirement(
        ws, FakeModelRuntime([review_output()]), record.id
    )
    assert reviewed.code.value == "REQUIREMENT_REVIEWED", reviewed
    approved = approve_standard_requirement(ws, record.id)
    assert approved.code.value == "REQUIREMENT_APPROVED", approved
    applied = apply_standard_requirement(ws, record.id)
    assert applied.code.value == "REQUIREMENT_APPLIED", applied
    assert ws.requirements[record.id].state == "Applied"
    return ws.requirements[record.id]


def snapshot(ws, record):
    root = root_of(ws, record)
    children = {
        d.id: ws.content[d.secret]
        for d in ws.documents
        if d.parent_document_id == root.id
    }
    return {
        "record": ws.requirements[record.id],
        "root_id": root.id,
        "folder": root.folder_id,
        "body": ws.content[root.secret],
        "children": children,
    }


# -- the audited defect -----------------------------------------------------


def test_a_retry_never_demotes_or_rewrites_an_applied_candidate():
    ws, raw, _ = build_workspace()
    partial_run(ws, raw, TWO, fail_on_candidate=2)
    [first] = standards(ws)
    applied = complete_standard_chain(ws, first)
    before = snapshot(ws, applied)
    mutations_before = len(ws.mutations)

    model = FakeModelRuntime([TWO])
    result = process_raw_requirement(ws, model, raw.id)

    assert result.code is ProcessResultCode.PROCESSING_STATE_CONFLICT
    assert not model.was_invoked
    assert ws.mutations[mutations_before:] == []
    assert snapshot(ws, applied) == before
    assert ws.requirements[applied.id].state == "Applied"
    assert before["folder"] == "f-approved"
    assert ws.requirements[raw.id].state == "Process"
    assert len(standards(ws)) == 1, "the retry must not create the second candidate"


@pytest.mark.parametrize("state", PROGRESSED_STATES)
def test_a_candidate_in_any_progressed_state_is_never_touched(state):
    ws, raw, _ = build_workspace()
    partial_run(ws, raw, TWO, fail_on_candidate=2)
    [first] = standards(ws)
    set_state(ws, first, state)
    before = snapshot(ws, first)
    mutations_before = len(ws.mutations)

    result = process_raw_requirement(ws, FakeModelRuntime([TWO]), raw.id)

    assert result.code is ProcessResultCode.PROCESSING_STATE_CONFLICT
    assert ws.mutations[mutations_before:] == []
    assert snapshot(ws, first) == before
    assert ws.requirements[first.id].state == state


def test_a_draft_candidate_with_an_edited_root_is_not_overwritten():
    ws, raw, _ = build_workspace()
    partial_run(ws, raw, TWO, fail_on_candidate=2)
    [first] = standards(ws)
    root = root_of(ws, first)
    edited = ws.content[root.secret] + "\n## Human note\n\nEdited by hand in Draft.\n"
    ws.content[root.secret] = edited
    mutations_before = len(ws.mutations)

    result = process_raw_requirement(ws, FakeModelRuntime([TWO]), raw.id)

    assert result.code is ProcessResultCode.PROCESSING_STATE_CONFLICT
    assert ws.mutations[mutations_before:] == []
    assert ws.content[root.secret] == edited
    assert ws.requirements[first.id].state == "Draft"


def test_equivalent_completed_content_is_not_written_again():
    ws, raw, _ = build_workspace()
    partial_run(ws, raw, TWO, fail_on_candidate=2)
    [first] = standards(ws)
    root = root_of(ws, first)
    mutations_before = len(ws.mutations)

    model = FakeModelRuntime([TWO])
    result = process_raw_requirement(ws, model, raw.id)

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert not model.was_invoked
    added = ws.mutations[mutations_before:]
    assert f"write_content {root.secret}" not in added
    assert not any(m.startswith(f"set_requirement_state {first.id}") for m in added)
    assert not any(m.startswith(f"set_requirement_type {first.id}") for m in added)
    assert len(standards(ws)) == 2
    assert ws.requirements[raw.id].state == "Review"


def test_a_conflict_in_a_later_candidate_is_found_before_an_earlier_one_is_written():
    """Every candidate is preflighted before the first write of the run."""
    ws, raw, _ = build_workspace()
    partial_run(ws, raw, THREE, fail_on_candidate=3)
    first, second = sorted(standards(ws), key=lambda r: r.public_id)
    # The first candidate's content was lost: a genuine incomplete Draft.
    ws.content[root_of(ws, first).secret] = ""
    # The second candidate moved on without the RAW.
    complete_standard_chain(ws, second)
    mutations_before = len(ws.mutations)

    result = process_raw_requirement(ws, FakeModelRuntime([THREE]), raw.id)

    assert result.code is ProcessResultCode.PROCESSING_STATE_CONFLICT
    assert ws.mutations[mutations_before:] == [], "nothing may be written"
    assert ws.content[root_of(ws, first).secret] == ""
    assert len(standards(ws)) == 2, "the third candidate must not be created"


# -- the safe resume that must keep working ---------------------------------


def test_a_genuinely_incomplete_draft_still_resumes_without_the_model():
    ws, raw, _ = build_workspace()
    partial_run(ws, raw, TWO, fail_on_candidate=2)
    [first] = standards(ws)
    root = root_of(ws, first)
    ws.content[root.secret] = ""  # the content write was lost
    mutations_before = len(ws.mutations)

    model = FakeModelRuntime([TWO])
    result = process_raw_requirement(ws, model, raw.id)

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert not model.was_invoked
    assert f"write_content {root.secret}" in ws.mutations[mutations_before:]
    assert "## Requirement" in ws.content[root.secret]
    assert {r.id for r in standards(ws)} == {
        candidate_fibery_id(raw.id, "C001"),
        candidate_fibery_id(raw.id, "C002"),
    }
    assert ws.requirements[raw.id].state == "Review"


def test_a_candidate_missing_id_provenance_and_document_still_resumes():
    ws, raw, _ = build_workspace()
    ws.failures["set_requirement_id"] = FiberyError("induced")
    process_raw_requirement(ws, FakeModelRuntime([TWO]), raw.id)
    reset_to_process(ws, raw)

    model = FakeModelRuntime([TWO])
    result = process_raw_requirement(ws, model, raw.id)

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert not model.was_invoked
    assert len(standards(ws)) == 2
    for record in standards(ws):
        assert record.requirement_id
        assert ws.derived_from_ids[record.id] == [raw.id]
        assert "## Requirement" in ws.content[root_of(ws, record).secret]
