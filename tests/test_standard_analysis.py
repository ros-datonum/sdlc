"""The structured contract for Standard Requirement analysis."""

import json

import pytest

from sdlc.raw_processing import MISSING_INFORMATION, NO_OPEN_QUESTIONS, SECTION_KEYS
from sdlc.standard_analysis import (
    FindingKind,
    InvalidAnalysisOutput,
    RelationKind,
    parse_analysis_output,
)
from standard_fake import analysis_output, normalized


def test_parses_a_conforming_response():
    result = parse_analysis_output(analysis_output())

    assert result.normalized.title
    assert result.findings == ()
    assert result.proposed_relations == ()


def test_a_fenced_code_block_is_tolerated():
    assert parse_analysis_output(f"```json\n{analysis_output()}\n```").normalized


def test_non_json_is_rejected():
    with pytest.raises(InvalidAnalysisOutput, match="not valid JSON"):
        parse_analysis_output("The requirement looks fine to me.")


def test_an_unknown_top_level_key_is_rejected():
    body = json.loads(analysis_output())
    body["reasoning"] = "first I considered..."

    with pytest.raises(InvalidAnalysisOutput, match="reasoning"):
        parse_analysis_output(json.dumps(body))


def test_an_unknown_normalized_key_is_rejected():
    body = json.loads(analysis_output())
    body["normalized_requirement"]["thinking"] = "step by step"

    with pytest.raises(InvalidAnalysisOutput, match="thinking"):
        parse_analysis_output(json.dumps(body))


def test_a_missing_requirement_statement_is_rejected():
    body = json.loads(analysis_output())
    del body["normalized_requirement"]["requirement"]

    with pytest.raises(InvalidAnalysisOutput, match="requirement"):
        parse_analysis_output(json.dumps(body))


def test_absent_sections_use_the_schema_text():
    body = {"normalized_requirement": {"title": "T", "requirement": "R"}}

    result = parse_analysis_output(json.dumps(body))

    assert result.normalized.rationale == "Not specified in source."
    assert result.normalized.open_questions == "None."


@pytest.mark.parametrize("kind", [k.value for k in FindingKind])
def test_every_approved_finding_kind_is_accepted(kind):
    about_other = FindingKind(kind).is_about_another_requirement
    finding = {"kind": kind, "detail": "observed"}
    if about_other:
        finding["requirement_id"] = "SDLC-FR-0012"

    result = parse_analysis_output(analysis_output(findings=[finding]))

    assert result.findings[0].kind is FindingKind(kind)


def test_an_unknown_finding_kind_is_rejected():
    finding = {"kind": "LOOKS_BAD", "detail": "x"}

    with pytest.raises(InvalidAnalysisOutput, match="expected one of"):
        parse_analysis_output(analysis_output(findings=[finding]))


def test_a_comparison_finding_must_name_a_requirement():
    finding = {"kind": "POSSIBLE_DUPLICATE", "detail": "x"}

    with pytest.raises(InvalidAnalysisOutput, match="must name the Requirement"):
        parse_analysis_output(analysis_output(findings=[finding]))


def test_a_quality_finding_must_not_name_another_requirement():
    finding = {"kind": "NON_ATOMIC", "detail": "x", "requirement_id": "SDLC-FR-0012"}

    with pytest.raises(InvalidAnalysisOutput, match="must not name another"):
        parse_analysis_output(analysis_output(findings=[finding]))


def test_a_malformed_requirement_id_is_rejected():
    finding = {
        "kind": "POSSIBLE_CONFLICT",
        "detail": "x",
        "requirement_id": "the auth one",
    }

    with pytest.raises(InvalidAnalysisOutput, match="not a Requirement ID"):
        parse_analysis_output(analysis_output(findings=[finding]))


@pytest.mark.parametrize("kind", [k.value for k in RelationKind])
def test_every_approved_relation_kind_is_accepted(kind):
    relation = {"kind": kind, "requirement_id": "SDLC-NFR-0004", "rationale": "why"}

    result = parse_analysis_output(analysis_output(relations=[relation]))

    assert result.proposed_relations[0].kind is RelationKind(kind)


def test_a_mutation_operation_is_rejected():
    """The model cannot ask for a change; it can only report one."""
    relation = {"kind": "SUPERSEDE", "requirement_id": "SDLC-FR-0001", "rationale": "x"}

    with pytest.raises(InvalidAnalysisOutput, match="expected one of"):
        parse_analysis_output(analysis_output(relations=[relation]))


def test_a_relation_with_an_operation_field_is_rejected():
    relation = {
        "kind": "DEPENDS_ON",
        "requirement_id": "SDLC-FR-0001",
        "rationale": "x",
        "operation": "UPDATE",
    }

    with pytest.raises(InvalidAnalysisOutput, match="operation"):
        parse_analysis_output(analysis_output(relations=[relation]))


def test_a_relation_carries_no_instruction_to_mutate():
    relation = {"kind": "AFFECTS", "requirement_id": "SDLC-FR-0001", "rationale": "x"}
    parsed = parse_analysis_output(analysis_output(relations=[relation]))

    assert set(vars(parsed.proposed_relations[0])) == {
        "kind",
        "requirement_id",
        "rationale",
    }


def test_an_unknown_analysis_key_is_rejected():
    with pytest.raises(InvalidAnalysisOutput, match="verdict"):
        parse_analysis_output(analysis_output(analysis={"verdict": "approved"}))


def test_the_rendered_document_follows_the_approved_schema():
    document = parse_analysis_output(analysis_output()).normalized.document("SDLC-FR-9")

    headings = [line for line in document.splitlines() if line.startswith("## ")]
    assert headings == [
        "## Requirement",
        "## Detailed Behavior",
        "## Rationale",
        "## Acceptance / Verification",
        "## Constraints & Edge Cases",
        "## Non-Goals",
        "## Open Questions",
    ]
    assert "Provenance" not in document
    assert document.splitlines()[0] == f"# SDLC-FR-9 — {normalized()['title']}"


# -- abstraction boundary ---------------------------------------------------


def test_a_product_level_requirement_may_omit_unestablished_sections():
    product_level = {
        "title": "Bound provider execution time",
        "requirement": (
            "Provider execution must stop within the configured execution time "
            "limit and report the timeout outcome to the caller."
        ),
        "acceptance_verification": (
            "An execution that exceeds the configured limit ends, and its caller "
            "observes a timeout outcome for that request."
        ),
    }

    result = parse_analysis_output(
        json.dumps({"normalized_requirement": product_level})
    )

    assert {key: getattr(result.normalized, key) for key in SECTION_KEYS} == {
        "requirement": product_level["requirement"],
        "detailed_behavior": MISSING_INFORMATION,
        "rationale": MISSING_INFORMATION,
        "acceptance_verification": product_level["acceptance_verification"],
        "constraints_edge_cases": MISSING_INFORMATION,
        "non_goals": MISSING_INFORMATION,
        "open_questions": NO_OPEN_QUESTIONS,
    }


@pytest.mark.parametrize("key", SECTION_KEYS)
def test_normalization_cannot_add_an_architecture_section(key):
    leaking = "Text.\n\n## Architecture\n\nA watchdog thread kills the process."

    with pytest.raises(
        InvalidAnalysisOutput,
        match=f"normalized_requirement {key} contains the heading '## Architecture'",
    ):
        parse_analysis_output(analysis_output(normalized_changes={key: leaking}))
