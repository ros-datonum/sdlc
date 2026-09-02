"""Standard Requirement Process: entry, normalization, findings, transition."""

import pytest

from processor_fake import FakeModelRuntime
from sdlc.fibery_workspace import DocumentNode, RequirementRecord
from sdlc.process_result import parse_process_result
from sdlc.raw_source import content_equivalent
from sdlc.results import StandardProcessResultCode
from sdlc.standard_processor import process_standard_requirement
from standard_fake import (
    REQUIREMENT_ID,
    analysis_output,
    build_standard_workspace,
    process_results,
    rendered_document,
)

OUTPUT = analysis_output()


def run(ws, record, model):
    return process_standard_requirement(ws, model, record.id)


# -- entry ------------------------------------------------------------------


def test_processes_a_standard_requirement_in_process():
    ws, std, _ = build_standard_workspace()
    model = FakeModelRuntime([OUTPUT])

    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert model.was_invoked
    assert result.iteration == 1


def test_a_raw_requirement_is_refused():
    """This processor must never touch RAW Requirements."""
    ws, std, _ = build_standard_workspace(type_name="Raw")
    model = FakeModelRuntime([OUTPUT])

    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.NOT_A_STANDARD_REQUIREMENT
    assert not model.was_invoked
    assert ws.mutations == []


@pytest.mark.parametrize("state", ["Draft", "Review", "Ready", "Apply", "Applied"])
def test_only_the_process_state_is_accepted(state):
    ws, std, _ = build_standard_workspace(state=state)
    model = FakeModelRuntime([OUTPUT])

    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.REQUIREMENT_NOT_IN_PROCESS
    assert not model.was_invoked
    assert ws.mutations == []


def test_a_missing_requirement_is_reported():
    ws, _, _ = build_standard_workspace()
    model = FakeModelRuntime([OUTPUT])

    result = process_standard_requirement(ws, model, "nope")

    assert result.code is StandardProcessResultCode.REQUIREMENT_NOT_FOUND
    assert not model.was_invoked


# -- process result ---------------------------------------------------------


def test_the_first_iteration_is_numbered_0001():
    ws, std, doc = build_standard_workspace()

    run(ws, std, FakeModelRuntime([OUTPUT]))

    [artifact] = process_results(ws)
    assert artifact.name == f"{REQUIREMENT_ID} — Process Result 0001"
    assert artifact.parent_document_id == doc.id


def test_the_process_result_is_written_before_the_document_is_rewritten():
    ws, std, _ = build_standard_workspace()

    run(ws, std, FakeModelRuntime([OUTPUT]))

    order = [m for m in ws.mutations]
    created = next(
        i for i, m in enumerate(order) if m.startswith("create_child_document")
    )
    rewritten = next(i for i, m in enumerate(order) if m == "write_content std-secret")
    assert created < rewritten


def test_the_process_result_records_both_fingerprints():
    ws, std, _ = build_standard_workspace()
    before = ws.content["std-secret"]

    run(ws, std, FakeModelRuntime([OUTPUT]))

    [artifact] = process_results(ws)
    persisted = parse_process_result(ws.content[artifact.secret])
    assert persisted.input_fingerprint and persisted.output_fingerprint
    assert persisted.input_fingerprint != persisted.output_fingerprint
    assert before != ws.content["std-secret"]


def test_no_chain_of_thought_is_persisted():
    ws, std, _ = build_standard_workspace()

    run(ws, std, FakeModelRuntime([OUTPUT]))

    body = ws.content[process_results(ws)[0].secret].lower()
    assert "reasoning" not in body and "thinking" not in body


def test_a_malformed_process_result_refuses_to_resume():
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([OUTPUT]))
    artifact = process_results(ws)[0]
    ws.content[artifact.secret] = "# Process Result 0001\n\nnot json\n"
    ws.requirements[std.id] = RequirementRecord(
        **{**ws.requirements[std.id].__dict__, "state": "Process"}
    )

    model = FakeModelRuntime([OUTPUT])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.INVALID_PROCESSING_RESULT
    assert not model.was_invoked


def test_two_results_for_one_iteration_are_a_conflict():
    ws, std, doc = build_standard_workspace()
    run(ws, std, FakeModelRuntime([OUTPUT]))
    duplicate = ws.create_child_document(
        f"{REQUIREMENT_ID} — Process Result 0001", doc.id
    )
    ws.content[duplicate.secret] = ws.content[process_results(ws)[0].secret]
    ws.requirements[std.id] = RequirementRecord(
        **{**ws.requirements[std.id].__dict__, "state": "Process"}
    )

    model = FakeModelRuntime([OUTPUT])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.PROCESSING_STATE_CONFLICT
    assert not model.was_invoked


# -- document ---------------------------------------------------------------


def test_the_root_document_is_rewritten_to_the_approved_schema():
    ws, std, _ = build_standard_workspace()

    run(ws, std, FakeModelRuntime([OUTPUT]))

    stored = ws.content["std-secret"]
    for heading in (
        "## Requirement",
        "## Detailed Behavior",
        "## Rationale",
        "## Acceptance / Verification",
        "## Constraints & Edge Cases",
        "## Non-Goals",
        "## Open Questions",
    ):
        assert heading in stored
    assert "Provenance" not in stored
    assert stored.splitlines()[0].startswith(f"# {REQUIREMENT_ID} — ")


def test_the_document_matches_the_persisted_result():
    ws, std, _ = build_standard_workspace()

    run(ws, std, FakeModelRuntime([OUTPUT]))

    assert content_equivalent(ws.content["std-secret"], rendered_document())


def test_a_content_mismatch_after_the_rewrite_fails_validation():
    ws, std, _ = build_standard_workspace()
    original = ws.read_document_content

    def lose_a_section(secret):
        text = original(secret)
        return (
            text.replace("Does not cover credential rotation.", "")
            if secret == "std-secret"
            else text
        )

    ws.read_document_content = lose_a_section

    result = run(ws, std, FakeModelRuntime([OUTPUT]))

    assert result.code is StandardProcessResultCode.PARTIAL_PROCESSING
    assert ws.requirements[std.id].state == "Process"


def test_bullet_lists_survive_fibery_reserialization():
    """The fake re-serializes like Fibery; canonical comparison must accept it."""
    ws, std, _ = build_standard_workspace()
    bulleted = analysis_output(
        {"requirement": "The runtime must:\n- refuse API keys\n- refuse OpenRouter"}
    )

    result = run(ws, std, FakeModelRuntime([bulleted]))

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert ws.requirements[std.id].state == "Review"


# -- findings and relations -------------------------------------------------


def test_proposed_relations_are_persisted_but_never_written():
    ws, std, _ = build_standard_workspace()
    relations = [
        {
            "kind": "DEPENDS_ON",
            "requirement_id": "SDLC-FR-0009",
            "rationale": "needs it",
        },
        {
            "kind": "AFFECTS",
            "requirement_id": "SDLC-NFR-0012",
            "rationale": "touches it",
        },
    ]

    result = run(ws, std, FakeModelRuntime([analysis_output(relations=relations)]))

    persisted = parse_process_result(ws.content[process_results(ws)[0].secret])
    assert [r.requirement_id for r in persisted.proposed_relations] == [
        "SDLC-FR-0009",
        "SDLC-NFR-0012",
    ]
    assert len(result.proposed_relations) == 2
    # Nothing was written to Fibery.
    assert ws.derived_from_ids.get(std.id) == ["raw-uuid-1"]
    assert not any("add_derived_from" in m for m in ws.mutations)


def test_findings_do_not_mutate_the_referenced_requirement():
    other = RequirementRecord(
        id="std-other",
        public_id="99",
        requirement_id="SDLC-FR-0099",
        title="An applied requirement",
        type_name="Standard",
        state="Applied",
        revision=3,
        project_id="p-1",
        source_fingerprint=None,
    )
    ws, std, _ = build_standard_workspace(others=[other])
    before = ws.requirements["std-other"]
    findings = [
        {"kind": "POSSIBLE_CONFLICT", "requirement_id": "SDLC-FR-0099", "detail": "x"}
    ]

    result = run(ws, std, FakeModelRuntime([analysis_output(findings=findings)]))

    assert any("POSSIBLE_CONFLICT" in f for f in result.findings)
    assert ws.requirements["std-other"] == before


def test_a_non_atomic_finding_creates_no_requirement():
    ws, std, _ = build_standard_workspace()
    before = set(ws.requirements)
    findings = [{"kind": "NON_ATOMIC", "detail": "two obligations"}]

    result = run(ws, std, FakeModelRuntime([analysis_output(findings=findings)]))

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert set(ws.requirements) == before
    assert any("NON_ATOMIC" in f for f in result.findings)


def test_findings_do_not_block_the_transition():
    """Process reports; Review decides acceptability."""
    ws, std, _ = build_standard_workspace()
    findings = [
        {"kind": "INCOMPLETE", "detail": "missing acceptance"},
        {"kind": "NOT_TESTABLE", "detail": "no observable outcome"},
    ]

    result = run(ws, std, FakeModelRuntime([analysis_output(findings=findings)]))

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert ws.requirements[std.id].state == "Review"


# -- state ------------------------------------------------------------------


def test_state_moves_to_review_and_is_read_back():
    ws, std, _ = build_standard_workspace()

    run(ws, std, FakeModelRuntime([OUTPUT]))

    assert ws.requirements[std.id].state == "Review"


def test_a_silently_ignored_transition_is_not_success():
    ws, std, _ = build_standard_workspace()
    real = ws.set_requirement_state
    ws.set_requirement_state = lambda e, s: (
        None if (e == std.id and s == "Review") else real(e, s)
    )

    result = run(ws, std, FakeModelRuntime([OUTPUT]))

    assert result.code is not StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert ws.requirements[std.id].state == "Process"


def test_revision_is_never_changed():
    ws, std, _ = build_standard_workspace()

    run(ws, std, FakeModelRuntime([OUTPUT]))

    assert ws.requirements[std.id].revision == 1
    assert not any("revision" in m.lower() for m in ws.mutations)


# -- context ----------------------------------------------------------------


def test_the_prompt_carries_the_raw_ancestry_and_other_standards():
    other = RequirementRecord(
        id="std-other",
        public_id="99",
        requirement_id="SDLC-FR-0099",
        title="Another requirement",
        type_name="Standard",
        state="Applied",
        revision=1,
        project_id="p-1",
        source_fingerprint=None,
    )
    ws, std, _ = build_standard_workspace(others=[other])
    model = FakeModelRuntime([OUTPUT])

    run(ws, std, model)

    context = model.calls[0]["context"]
    assert "Source material." in context
    assert "SDLC-FR-0099" in context
    assert REQUIREMENT_ID in context


def test_previous_process_results_are_not_fed_back_as_source():
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([OUTPUT]))
    ws.content["std-secret"] += "\nAn edit.\n"
    ws.requirements[std.id] = RequirementRecord(
        **{**ws.requirements[std.id].__dict__, "state": "Process"}
    )

    model = FakeModelRuntime([OUTPUT])
    run(ws, std, model)

    assert "Process Result" not in model.calls[0]["context"]


def test_process_never_reads_a_review_result_as_requirement_content():
    """Review writes numbered children under the same Root Document.

    Without this, a reviewer's findings would reach the Process model as
    something the requirement itself says, and Process would normalize its own
    reviewer's criticism into the document.
    """
    ws, requirement, doc = build_standard_workspace()
    ws.documents.append(
        DocumentNode(
            id="review-doc-1",
            name=f"{REQUIREMENT_ID} — Review Result 0001",
            folder_id=None,
            entity_public_id=None,
            secret="review-secret",
            parent_document_id=doc.id,
        )
    )
    ws.content["review-secret"] = (
        "# Review Result 0001\n\nBLOCKING: this requirement is untestable.\n"
    )

    model = FakeModelRuntime(responses=[analysis_output()])
    result = process_standard_requirement(ws, model, requirement.id)

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    context = model.calls[0]["context"]
    assert "Review Result" not in context
    assert "untestable" not in context
