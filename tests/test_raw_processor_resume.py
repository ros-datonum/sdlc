"""Resume semantics: a retry never re-invokes the model and never duplicates."""

import pytest

from processor_fake import FakeModelRuntime, build_workspace, candidate, model_output
from sdlc.fibery_workspace import FiberyError, RequirementRecord
from sdlc.processing_result import candidate_fibery_id, processing_result_name
from sdlc.raw_processor import process_raw_requirement
from sdlc.results import ProcessResultCode

ONE = model_output([candidate()])


def reset_to_process(ws, raw):
    """Fibery leaves the RAW in Process when a run does not complete."""
    ws.requirements[raw.id] = RequirementRecord(
        **{**ws.requirements[raw.id].__dict__, "state": "Process"}
    )


def standards(ws):
    return [r for r in ws.requirements.values() if r.type_name == "Standard"]


# -- deterministic candidate identity ---------------------------------------


def test_the_same_raw_and_key_always_give_the_same_entity_id():
    first = candidate_fibery_id("raw-uuid-1", "C001")
    again = candidate_fibery_id("raw-uuid-1", "C001")

    assert first == again


def test_different_candidate_keys_give_different_entity_ids():
    assert candidate_fibery_id("raw-uuid-1", "C001") != candidate_fibery_id(
        "raw-uuid-1", "C002"
    )


def test_different_raws_give_different_entity_ids():
    assert candidate_fibery_id("raw-a", "C001") != candidate_fibery_id("raw-b", "C001")


def test_the_candidate_entity_uses_the_deterministic_id():
    ws, raw, _ = build_workspace()

    process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)

    [std] = standards(ws)
    assert std.id == candidate_fibery_id(raw.id, "C001")


# -- failure after each meaningful step -------------------------------------


FAILURE_POINTS = [
    "set_requirement_id",
    "add_derived_from",
    "create_requirement_document",
]


def fail_candidate_content(ws):
    """Fail the candidate's content write, after the Processing Result's."""
    original = ws.write_document_content
    seen = {"n": 0}

    def guarded(secret, markdown):
        seen["n"] += 1
        if seen["n"] > 1:
            raise FiberyError("induced")
        return original(secret, markdown)

    ws.write_document_content = guarded
    return original


@pytest.mark.parametrize("failing_call", FAILURE_POINTS)
def test_a_failure_after_the_processing_result_leaves_raw_in_process(failing_call):
    ws, raw, _ = build_workspace()
    ws.failures[failing_call] = FiberyError("induced")

    result = process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)

    assert result.code is ProcessResultCode.PARTIAL_PROCESSING
    assert ws.requirements[raw.id].state == "Process"


@pytest.mark.parametrize("failing_call", FAILURE_POINTS)
def test_retry_after_any_failure_point_neither_calls_the_model_nor_duplicates(
    failing_call,
):
    ws, raw, _ = build_workspace()
    ws.failures[failing_call] = FiberyError("induced")
    process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)
    reset_to_process(ws, raw)

    model = FakeModelRuntime([ONE])
    result = process_raw_requirement(ws, model, raw.id)

    assert not model.was_invoked, "resume must never re-invoke the model"
    assert len(standards(ws)) == 1, "resume must not duplicate the candidate"
    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert ws.requirements[raw.id].state == "Review"


@pytest.mark.parametrize("failing_call", FAILURE_POINTS)
def test_resume_completes_the_candidate_fully(failing_call):
    ws, raw, _ = build_workspace()
    ws.failures[failing_call] = FiberyError("induced")
    process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)
    reset_to_process(ws, raw)

    process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)

    [std] = standards(ws)
    assert std.requirement_id and std.requirement_id.startswith("SDLC-FR-")
    assert ws.derived_from_ids[std.id] == [raw.id]
    [doc] = ws.documents_attached_to_requirement(std.public_id)
    assert doc.folder_id == "f-draft"
    assert "## Requirement" in ws.content[doc.secret]


def test_a_failure_before_the_processing_result_creates_no_candidate():
    """Retry may call the model again, because nothing durable exists yet."""
    ws, raw, _ = build_workspace()
    ws.failures["create_child_document"] = FiberyError("induced")

    result = process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)

    assert result.code is ProcessResultCode.PROCESSING_RESULT_WRITE_FAILED
    assert standards(ws) == []
    assert ws.requirements[raw.id].state == "Process"

    model = FakeModelRuntime([ONE])
    process_raw_requirement(ws, model, raw.id)
    assert model.was_invoked


def test_only_the_missing_step_is_redone_on_resume():
    ws, raw, _ = build_workspace()
    ws.failures["write_document_content"] = FiberyError("induced")
    process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)
    reset_to_process(ws, raw)
    ws.mutations.clear()

    process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)

    created_again = [m for m in ws.mutations if m.startswith("create_requirement ")]
    assert created_again == [], "the entity already existed and must be adopted"


def test_a_content_write_failure_leaves_raw_in_process_and_resumes():
    ws, raw, _ = build_workspace()
    original = fail_candidate_content(ws)

    result = process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)

    assert result.code is ProcessResultCode.PARTIAL_PROCESSING
    assert ws.requirements[raw.id].state == "Process"

    ws.write_document_content = original
    reset_to_process(ws, raw)
    model = FakeModelRuntime([ONE])
    resumed = process_raw_requirement(ws, model, raw.id)

    assert not model.was_invoked
    assert len(standards(ws)) == 1
    assert resumed.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    [doc] = ws.documents_attached_to_requirement(standards(ws)[0].public_id)
    assert "## Requirement" in ws.content[doc.secret]


def test_a_partial_run_reports_the_durable_state_it_created():
    ws, raw, _ = build_workspace()
    ws.failures["create_requirement_document"] = FiberyError("induced")

    result = process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)

    assert any("Processing Result" in item for item in result.created)
    assert any("Standard candidate" in item for item in result.created)


def test_partial_state_is_never_deleted():
    ws, raw, _ = build_workspace()
    ws.failures["add_derived_from"] = FiberyError("induced")

    process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)

    assert len(standards(ws)) == 1
    assert [d for d in ws.documents if d.name.endswith("Processing Result")]


def test_resume_of_a_multi_candidate_run_completes_the_remainder():
    ws, raw, _ = build_workspace()
    three = model_output([candidate(title=f"T{i}") for i in range(3)])
    # Fail while applying the second candidate's document.
    calls = {"n": 0}
    original = ws.create_requirement_document

    def fail_second(name, folder_id, requirement_public_id):
        calls["n"] += 1
        if calls["n"] == 2:
            raise FiberyError("induced")
        return original(name, folder_id, requirement_public_id)

    ws.create_requirement_document = fail_second
    process_raw_requirement(ws, FakeModelRuntime([three]), raw.id)
    reset_to_process(ws, raw)
    ws.create_requirement_document = original

    model = FakeModelRuntime([three])
    result = process_raw_requirement(ws, model, raw.id)

    assert not model.was_invoked
    assert len(standards(ws)) == 3
    assert len(result.candidates) == 3
    assert len({s.requirement_id for s in standards(ws)}) == 3


def test_an_entity_at_the_candidate_id_from_another_project_is_a_conflict():
    """Never silently reuse an unrelated entity that happens to share the id."""
    ws, raw, _ = build_workspace()
    stolen = candidate_fibery_id(raw.id, "C001")
    ws.requirements[stolen] = RequirementRecord(
        id=stolen,
        public_id="500",
        requirement_id="OTHER-FR-0500",
        title="Someone else's requirement",
        type_name="Standard",
        state="Applied",
        revision=1,
        project_id="another-project",
        source_fingerprint=None,
    )

    result = process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)

    assert result.code is ProcessResultCode.PROCESSING_STATE_CONFLICT
    assert len(standards(ws)) == 1, "the foreign entity must be left untouched"
    assert ws.requirements[stolen].title == "Someone else's requirement"


def test_a_completed_run_rerun_is_refused_because_raw_left_process():
    """The RAW is in Review, so the entry condition stops a second run."""
    ws, raw, _ = build_workspace()
    process_raw_requirement(ws, FakeModelRuntime([ONE]), raw.id)

    model = FakeModelRuntime([ONE])
    result = process_raw_requirement(ws, model, raw.id)

    assert result.code is ProcessResultCode.REQUIREMENT_NOT_IN_PROCESS
    assert not model.was_invoked
    assert len(standards(ws)) == 1


def test_the_processing_result_name_is_derived_from_the_raw_id():
    assert processing_result_name("SDLC-RAW-0007") == (
        "SDLC-RAW-0007 — Processing Result"
    )
