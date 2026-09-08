"""RAW Requirement Processor: entry conditions, decomposition and resume."""

import pytest

from processor_fake import (
    FakeModelRuntime,
    build_workspace,
    candidate,
    model_output,
)
from sdlc.fibery_workspace import RequirementRecord
from sdlc.processing_result import (
    parse_processing_result,
    processing_result_name,
)
from sdlc.raw_processor import process_raw_requirement
from sdlc.results import ProcessResultCode

ONE = model_output([candidate()])


def run(ws, raw, model):
    return process_raw_requirement(ws, model, raw.id)


# -- entry conditions -------------------------------------------------------


def test_processes_a_raw_requirement_in_process():
    ws, raw, _ = build_workspace()
    model = FakeModelRuntime([ONE])

    result = run(ws, raw, model)

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert model.was_invoked


@pytest.mark.parametrize("state", ["Draft", "Review", "Ready", "Apply", "Applied"])
def test_only_the_process_state_is_accepted(state):
    ws, raw, _ = build_workspace(raw_state=state)
    model = FakeModelRuntime([ONE])

    result = run(ws, raw, model)

    assert result.code is ProcessResultCode.REQUIREMENT_NOT_IN_PROCESS
    assert not model.was_invoked
    assert ws.mutations == []


def test_a_standard_requirement_is_refused():
    """The processor must never touch Standard Requirements."""
    ws, raw, _ = build_workspace(raw_type="Standard")
    model = FakeModelRuntime([ONE])

    result = run(ws, raw, model)

    assert result.code is ProcessResultCode.NOT_A_RAW_REQUIREMENT
    assert not model.was_invoked
    assert ws.mutations == []


def test_a_missing_requirement_is_reported():
    ws, _raw, _ = build_workspace()
    model = FakeModelRuntime([ONE])

    result = process_raw_requirement(ws, model, "nope")

    assert result.code is ProcessResultCode.REQUIREMENT_NOT_FOUND
    assert not model.was_invoked


# -- processing result ------------------------------------------------------


def test_the_processing_result_is_persisted_as_a_raw_child_document():
    ws, raw, doc = build_workspace()

    run(ws, raw, FakeModelRuntime([ONE]))

    [artifact] = [d for d in ws.documents if d.parent_document_id == doc.id]
    assert artifact.name == processing_result_name("SDLC-RAW-0007")
    assert parse_processing_result(ws.content[artifact.secret]).candidates


def test_the_processing_result_is_written_before_any_candidate_exists():
    """Retry must never need the model to reconstruct candidate identity."""
    ws, raw, _ = build_workspace()

    run(ws, raw, FakeModelRuntime([ONE]))

    order = [m.split()[0] for m in ws.mutations]
    assert order.index("create_child_document") < order.index("create_requirement")


def test_candidate_keys_are_assigned_deterministically_by_code():
    ws, raw, doc = build_workspace()
    three = model_output([candidate(title=f"T{i}") for i in range(3)])

    run(ws, raw, FakeModelRuntime([three]))

    [artifact] = [d for d in ws.documents if d.parent_document_id == doc.id]
    persisted = parse_processing_result(ws.content[artifact.secret])
    assert [k.key for k in persisted.candidates] == ["C001", "C002", "C003"]


def test_no_chain_of_thought_is_persisted():
    ws, raw, doc = build_workspace()

    run(ws, raw, FakeModelRuntime([ONE]))

    [artifact] = [d for d in ws.documents if d.parent_document_id == doc.id]
    body = ws.content[artifact.secret].lower()
    assert "reasoning" not in body and "thinking" not in body


def test_a_malformed_processing_result_refuses_to_resume():
    ws, raw, doc = build_workspace()
    run(ws, raw, FakeModelRuntime([ONE]))
    [artifact] = [d for d in ws.documents if d.parent_document_id == doc.id]
    ws.content[artifact.secret] = "# Processing Result\n\nnot json\n"
    ws.requirements[raw.id] = RequirementRecord(**{**raw.__dict__, "state": "Process"})

    model = FakeModelRuntime([ONE])
    result = run(ws, raw, model)

    assert result.code is ProcessResultCode.INVALID_PROCESSING_RESULT
    assert not model.was_invoked


def test_two_processing_results_are_a_conflict():
    ws, raw, doc = build_workspace()
    run(ws, raw, FakeModelRuntime([ONE]))
    ws.create_child_document(processing_result_name("SDLC-RAW-0007"), doc.id)
    ws.requirements[raw.id] = RequirementRecord(**{**raw.__dict__, "state": "Process"})

    model = FakeModelRuntime([ONE])
    result = run(ws, raw, model)

    assert result.code is ProcessResultCode.PROCESSING_STATE_CONFLICT
    assert not model.was_invoked


def test_a_model_runtime_failure_creates_nothing():
    ws, raw, _ = build_workspace()
    model = FakeModelRuntime(
        error=__import__("sdlc.model_runtime", fromlist=["x"]).ModelRuntimeError(
            "no cli"
        )
    )

    result = run(ws, raw, model)

    assert result.code is ProcessResultCode.MODEL_RUNTIME_FAILED
    assert ws.mutations == []


def test_malformed_model_output_creates_nothing():
    ws, raw, _ = build_workspace()

    result = run(ws, raw, FakeModelRuntime(["I think it needs auth."]))

    assert result.code is ProcessResultCode.INVALID_MODEL_OUTPUT
    assert ws.mutations == []


# -- results ----------------------------------------------------------------


def test_zero_candidates_is_a_successful_outcome():
    ws, raw, _ = build_workspace()
    empty = model_output([], reason="The source records only open questions.")

    result = run(ws, raw, FakeModelRuntime([empty]))

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    assert result.candidates == ()
    assert result.no_candidate_reason
    assert ws.requirements[raw.id].state == "Review"
    assert not [r for r in ws.requirements.values() if r.type_name == "Standard"]


def test_many_candidates_are_all_created():
    ws, raw, _ = build_workspace()
    many = model_output([candidate(title=f"T{i}") for i in range(4)])

    result = run(ws, raw, FakeModelRuntime([many]))

    assert len(result.candidates) == 4
    standards = [r for r in ws.requirements.values() if r.type_name == "Standard"]
    assert len(standards) == 4


@pytest.mark.parametrize(
    ("category", "infix"),
    [("FUNCTIONAL", "FR"), ("NON_FUNCTIONAL", "NFR"), ("CONSTRAINT", "CON")],
)
def test_every_category_maps_to_its_requirement_id_prefix(category, infix):
    ws, raw, _ = build_workspace()

    result = run(
        ws, raw, FakeModelRuntime([model_output([candidate(category=category)])])
    )

    assert result.candidates[0].startswith(f"SDLC-{infix}-")


def test_requirement_ids_come_from_the_fibery_public_id():
    ws, raw, _ = build_workspace()

    result = run(ws, raw, FakeModelRuntime([ONE]))

    [std] = [r for r in ws.requirements.values() if r.type_name == "Standard"]
    assert result.candidates[0] == f"SDLC-FR-{int(std.public_id):04d}"


def test_candidates_are_standard_and_draft():
    ws, raw, _ = build_workspace()

    run(ws, raw, FakeModelRuntime([ONE]))

    [std] = [r for r in ws.requirements.values() if r.type_name == "Standard"]
    assert (std.type_name, std.state, std.revision) == ("Standard", "Draft", 1)
    assert std.project_id == "p-1"


def test_provenance_is_written_both_ways():
    ws, raw, _ = build_workspace()

    run(ws, raw, FakeModelRuntime([ONE]))

    [std] = [r for r in ws.requirements.values() if r.type_name == "Standard"]
    assert ws.derived_from_ids[std.id] == [raw.id]
    assert ws.produces(raw.id) == [std.id]


def test_root_documents_are_contained_by_the_candidate_with_no_folder():
    """Placement is Type = Standard, State = Draft; the Root has no Folder."""
    ws, raw, _ = build_workspace()

    result = run(ws, raw, FakeModelRuntime([ONE]))

    [std] = [r for r in ws.requirements.values() if r.type_name == "Standard"]
    [doc] = ws.documents_attached_to_requirement(std.public_id)
    assert doc.folder_id is None
    assert (std.type_name, std.state) == ("Standard", "Draft")
    assert doc.name.startswith(result.candidates[0])
    assert not any("folder" in call.lower() for call in ws.calls)
    assert "## Acceptance / Verification" in ws.content[doc.secret]
    assert "Provenance" not in ws.content[doc.secret]


def test_each_candidate_has_exactly_one_attached_root_document():
    ws, raw, _ = build_workspace()
    two = model_output([candidate(title="A"), candidate(title="B")])

    run(ws, raw, FakeModelRuntime([two]))

    for std in [r for r in ws.requirements.values() if r.type_name == "Standard"]:
        assert len(ws.documents_attached_to_requirement(std.public_id)) == 1


def test_raw_moves_to_review_only_on_complete_success():
    ws, raw, _ = build_workspace()

    run(ws, raw, FakeModelRuntime([ONE]))

    assert ws.requirements[raw.id].state == "Review"


# -- findings ---------------------------------------------------------------


def test_findings_are_reported_without_mutating_existing_requirements():
    existing = RequirementRecord(
        id="std-existing",
        public_id="99",
        requirement_id="SDLC-FR-0099",
        title="An applied requirement",
        type_name="Standard",
        state="Applied",
        revision=3,
        project_id="p-1",
        source_fingerprint=None,
    )
    ws, raw, _ = build_workspace(standards=[existing])
    before = ws.requirements["std-existing"]
    finding = {
        "kind": "POSSIBLE_CONFLICT",
        "requirement_id": "SDLC-FR-0099",
        "detail": "overlaps",
    }

    result = run(ws, raw, FakeModelRuntime([model_output([candidate()], [finding])]))

    assert any("POSSIBLE_CONFLICT" in f for f in result.findings)
    assert ws.requirements["std-existing"] == before
    assert "std-existing" not in ws.derived_from_ids


def test_existing_standards_are_offered_to_the_model_as_context():
    existing = RequirementRecord(
        id="std-existing",
        public_id="99",
        requirement_id="SDLC-FR-0099",
        title="An applied requirement",
        type_name="Standard",
        state="Applied",
        revision=3,
        project_id="p-1",
        source_fingerprint=None,
    )
    ws, raw, _ = build_workspace(standards=[existing])
    model = FakeModelRuntime([ONE])

    run(ws, raw, model)

    assert "SDLC-FR-0099" in model.calls[0]["context"]


def test_the_prompt_carries_the_raw_document_tree():
    ws, raw, doc = build_workspace()
    child = ws.create_child_document("Child detail", doc.id)
    ws.content[child.secret] = "Nested requirement detail."
    ws.mutations.clear()
    model = FakeModelRuntime([ONE])

    run(ws, raw, model)

    context = model.calls[0]["context"]
    assert "The CLI must be fast." in context
    assert "Nested requirement detail." in context


def test_the_processing_result_is_not_fed_back_as_source_material():
    ws, raw, _ = build_workspace()
    run(ws, raw, FakeModelRuntime([ONE]))
    ws.requirements[raw.id] = RequirementRecord(**{**raw.__dict__, "state": "Process"})

    # Second run resumes; if it re-read source it must not include its own output.
    model = FakeModelRuntime([ONE])
    run(ws, raw, model)

    assert not model.was_invoked


# -- Type and State are the lifecycle placement; read-back must prove them ----


@pytest.mark.parametrize(
    "silent_write, problem",
    [("set_requirement_type", "Type is"), ("set_requirement_state", "State")],
)
def test_a_type_or_state_write_that_did_not_take_effect_is_never_processed(
    silent_write, problem
):
    """Placement is Type = Standard, State = Draft on the entity, and nothing
    else expresses it, so a write that silently did not land is a validation
    failure (the candidate's Type read-back, or the RAW transition read-back),
    never a processed RAW."""
    ws, raw, _ = build_workspace()
    setattr(ws, silent_write, lambda *_: None)

    result = run(ws, raw, FakeModelRuntime([ONE]))

    assert result.code is ProcessResultCode.PARTIAL_PROCESSING
    assert ProcessResultCode.VALIDATION_FAILED.value in result.details
    assert any(problem in detail for detail in result.details)
    assert ws.requirements[raw.id].state == "Process"
