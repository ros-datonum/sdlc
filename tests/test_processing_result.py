"""The persisted Processing Result artifact."""

import pytest

from processor_fake import candidate, model_output
from sdlc.processing_result import (
    PROCESSING_RESULT_VERSION,
    InvalidProcessingResult,
    build_processing_result,
    candidate_key,
    parse_processing_result,
    processing_result_name,
    render_processing_result,
)
from sdlc.raw_processing import parse_model_output


def result_of(*candidates, findings=(), reason=None):
    decomposition = parse_model_output(model_output(list(candidates), findings, reason))
    return build_processing_result("SDLC-RAW-0007", decomposition)


# -- keys -------------------------------------------------------------------


def test_keys_are_sequential_and_zero_padded():
    assert [candidate_key(i) for i in range(3)] == ["C001", "C002", "C003"]


def test_keys_follow_the_validated_candidate_order():
    result = result_of(candidate(title="A"), candidate(title="B"))

    assert [(k.key, k.candidate.title) for k in result.candidates] == [
        ("C001", "A"),
        ("C002", "B"),
    ]


def test_the_document_name_is_derived_from_the_raw_id():
    assert processing_result_name("SDLC-RAW-1") == "SDLC-RAW-1 — Processing Result"


# -- round trip -------------------------------------------------------------


def test_a_persisted_result_reads_back_identically():
    original = result_of(candidate(category="NON_FUNCTIONAL", title="Speed"))

    restored = parse_processing_result(render_processing_result(original))

    assert restored.raw_requirement_id == original.raw_requirement_id
    assert [k.key for k in restored.candidates] == ["C001"]
    assert restored.candidates[0].candidate == original.candidates[0].candidate


def test_findings_survive_the_round_trip():
    finding = {
        "kind": "POSSIBLE_DUPLICATE",
        "requirement_id": "SDLC-FR-0009",
        "detail": "same obligation",
    }
    original = result_of(candidate(), findings=[finding])

    restored = parse_processing_result(render_processing_result(original))

    assert restored.findings[0].requirement_id == "SDLC-FR-0009"


def test_a_zero_candidate_result_survives_the_round_trip():
    original = result_of(reason="Only open questions were recorded.")

    restored = parse_processing_result(render_processing_result(original))

    assert restored.is_empty
    assert restored.no_candidate_reason == "Only open questions were recorded."


def test_the_rendered_artifact_is_human_readable():
    rendered = render_processing_result(result_of(candidate()))

    assert rendered.startswith("# SDLC-RAW-0007 — Processing Result")
    assert "not a Requirement" in rendered


def test_rendering_is_deterministic():
    result = result_of(candidate())

    assert render_processing_result(result) == render_processing_result(result)


# -- refusing to resume from a bad artifact ---------------------------------


def test_a_document_without_a_payload_is_refused():
    with pytest.raises(InvalidProcessingResult, match="no JSON payload"):
        parse_processing_result("# Processing Result\n\nnothing here\n")


def test_a_malformed_payload_is_refused():
    with pytest.raises(InvalidProcessingResult, match="not valid JSON"):
        parse_processing_result("```json\n{not json}\n```")


def test_an_unknown_version_is_refused():
    rendered = render_processing_result(result_of(candidate())).replace(
        f'"{PROCESSING_RESULT_VERSION}"', '"9.9"'
    )

    with pytest.raises(InvalidProcessingResult, match="not supported"):
        parse_processing_result(rendered)


def test_a_result_naming_no_raw_is_refused():
    rendered = render_processing_result(result_of(candidate())).replace(
        '"SDLC-RAW-0007"', '""'
    )

    with pytest.raises(InvalidProcessingResult, match="names no RAW"):
        parse_processing_result(rendered)


def test_duplicate_candidate_keys_are_refused():
    """Ambiguous candidate identity would break deterministic resume."""
    rendered = render_processing_result(
        result_of(candidate(title="A"), candidate(title="B"))
    ).replace('"C002"', '"C001"')

    with pytest.raises(InvalidProcessingResult, match="reuses a candidate key"):
        parse_processing_result(rendered)


def test_an_incomplete_persisted_candidate_is_refused():
    rendered = render_processing_result(result_of(candidate())).replace(
        '"rationale"', '"rationale_typo"'
    )

    with pytest.raises(InvalidProcessingResult, match="not a complete"):
        parse_processing_result(rendered)


def test_zero_candidates_without_a_reason_is_refused():
    rendered = render_processing_result(result_of(reason="because")).replace(
        '"because"', "null"
    )

    with pytest.raises(InvalidProcessingResult, match="why none was"):
        parse_processing_result(rendered)
