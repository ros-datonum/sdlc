"""The structured contract between the model and deterministic Fibery writes."""

import json

import pytest

from sdlc.raw_processing import (
    MISSING_INFORMATION,
    NO_OPEN_QUESTIONS,
    Candidate,
    Category,
    FindingKind,
    InvalidModelOutput,
    parse_model_output,
)

FULL_CANDIDATE = {
    "category": "FUNCTIONAL",
    "title": "Reject unauthenticated model execution",
    "requirement": "The runtime must refuse to execute a model without local login.",
    "detailed_behavior": "Preflight runs the CLI auth check before any invocation.",
    "rationale": "Credentials must never be held by the application.",
    "acceptance_verification": "An unauthenticated CLI produces an explicit error.",
    "constraints_edge_cases": "Applies to every configured runtime.",
    "non_goals": "Does not cover credential rotation.",
    "open_questions": "None.",
}


def output(**changes):
    body = {"candidates": [FULL_CANDIDATE], "findings": [], **changes}
    return json.dumps(body)


# -- candidates -------------------------------------------------------------


def test_parses_a_single_candidate():
    result = parse_model_output(output())

    [candidate] = result.candidates
    assert candidate.category is Category.FUNCTIONAL
    assert candidate.title == "Reject unauthenticated model execution"
    assert not result.is_empty


def test_parses_many_candidates():
    second = {**FULL_CANDIDATE, "category": "CONSTRAINT", "title": "Second"}
    third = {**FULL_CANDIDATE, "category": "NON_FUNCTIONAL", "title": "Third"}

    result = parse_model_output(output(candidates=[FULL_CANDIDATE, second, third]))

    assert len(result.candidates) == 3
    assert [c.category for c in result.candidates] == [
        Category.FUNCTIONAL,
        Category.CONSTRAINT,
        Category.NON_FUNCTIONAL,
    ]


def test_zero_candidates_is_valid_with_an_explanation():
    """A RAW input may warrant no Standard Requirement at all."""
    result = parse_model_output(
        json.dumps(
            {
                "candidates": [],
                "findings": [],
                "no_candidate_reason": "The source records only open questions.",
            }
        )
    )

    assert result.is_empty
    assert result.no_candidate_reason == "The source records only open questions."


def test_zero_candidates_without_an_explanation_is_rejected():
    """Silence is not a valid decomposition."""
    with pytest.raises(InvalidModelOutput, match="explain why none is warranted"):
        parse_model_output(json.dumps({"candidates": [], "findings": []}))


@pytest.mark.parametrize(
    ("value", "expected", "infix"),
    [
        ("FUNCTIONAL", Category.FUNCTIONAL, "FR"),
        ("NON_FUNCTIONAL", Category.NON_FUNCTIONAL, "NFR"),
        ("CONSTRAINT", Category.CONSTRAINT, "CON"),
    ],
)
def test_every_category_maps_to_its_id_infix(value, expected, infix):
    result = parse_model_output(
        output(candidates=[{**FULL_CANDIDATE, "category": value}])
    )

    assert result.candidates[0].category is expected
    assert result.candidates[0].category.id_infix == infix


def test_the_misspelled_workspace_category_is_not_accepted():
    """The Fibery option was corrected; no mapping table survives."""
    with pytest.raises(InvalidModelOutput, match="expected one of"):
        parse_model_output(
            output(candidates=[{**FULL_CANDIDATE, "category": "NON-FONCTIONAL"}])
        )


# -- malformed output -------------------------------------------------------


def test_non_json_is_rejected():
    with pytest.raises(InvalidModelOutput, match="not valid JSON"):
        parse_model_output("I think the requirement is about authentication.")


def test_a_json_array_is_rejected():
    with pytest.raises(InvalidModelOutput, match="must be a JSON object"):
        parse_model_output("[]")


def test_a_fenced_code_block_is_tolerated():
    """CLIs commonly wrap JSON in a fence; nothing else is guessed at."""
    result = parse_model_output(f"```json\n{output()}\n```")

    assert len(result.candidates) == 1


def test_an_unknown_top_level_key_is_rejected():
    """Guards against chain-of-thought or invented fields leaking in."""
    with pytest.raises(InvalidModelOutput, match="reasoning"):
        parse_model_output(output(reasoning="first I considered..."))


def test_an_unknown_candidate_key_is_rejected():
    with pytest.raises(InvalidModelOutput, match="thinking"):
        parse_model_output(
            output(candidates=[{**FULL_CANDIDATE, "thinking": "step by step"}])
        )


@pytest.mark.parametrize("missing", ["category", "title", "requirement"])
def test_a_candidate_missing_a_required_field_is_rejected(missing):
    incomplete = {k: v for k, v in FULL_CANDIDATE.items() if k != missing}

    with pytest.raises(InvalidModelOutput, match=missing):
        parse_model_output(output(candidates=[incomplete]))


def test_a_blank_requirement_is_rejected():
    with pytest.raises(InvalidModelOutput, match="non-empty"):
        parse_model_output(output(candidates=[{**FULL_CANDIDATE, "title": "   "}]))


def test_candidates_must_be_a_list():
    with pytest.raises(InvalidModelOutput, match="'candidates' must be a list"):
        parse_model_output(json.dumps({"candidates": {}, "findings": []}))


def test_a_non_string_section_is_rejected():
    with pytest.raises(InvalidModelOutput, match="must be a string"):
        parse_model_output(output(candidates=[{**FULL_CANDIDATE, "rationale": 42}]))


# -- absent sections --------------------------------------------------------


def test_an_absent_section_uses_the_schema_text():
    sparse = {"category": "FUNCTIONAL", "title": "T", "requirement": "R"}

    candidate = parse_model_output(output(candidates=[sparse])).candidates[0]

    assert candidate.rationale == MISSING_INFORMATION
    assert candidate.non_goals == MISSING_INFORMATION


def test_absent_open_questions_uses_none():
    sparse = {"category": "FUNCTIONAL", "title": "T", "requirement": "R"}

    candidate = parse_model_output(output(candidates=[sparse])).candidates[0]

    assert candidate.open_questions == NO_OPEN_QUESTIONS


# -- findings ---------------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        "POSSIBLE_DUPLICATE",
        "POSSIBLE_CONFLICT",
        "POSSIBLE_CHANGE",
        "POSSIBLE_SUPERSESSION",
    ],
)
def test_every_finding_kind_is_accepted(kind):
    finding = {"kind": kind, "requirement_id": "SDLC-FR-0012", "detail": "overlaps"}

    result = parse_model_output(output(findings=[finding]))

    assert result.findings[0].kind is FindingKind(kind)
    assert result.findings[0].requirement_id == "SDLC-FR-0012"


def test_an_unknown_finding_kind_is_rejected():
    finding = {"kind": "SUPERSEDES", "requirement_id": "X", "detail": "d"}

    with pytest.raises(InvalidModelOutput, match="expected one of"):
        parse_model_output(output(findings=[finding]))


def test_a_finding_carries_no_instruction_to_mutate():
    """Findings are observations; the contract has no field to act on one."""
    finding = {"kind": "POSSIBLE_CHANGE", "requirement_id": "X", "detail": "d"}
    parsed = parse_model_output(output(findings=[finding])).findings[0]

    assert set(vars(parsed)) == {"kind", "requirement_id", "detail"}


def test_a_finding_with_an_operation_field_is_rejected():
    finding = {
        "kind": "POSSIBLE_CHANGE",
        "requirement_id": "X",
        "detail": "d",
        "operation": "SUPERSEDE",
    }

    with pytest.raises(InvalidModelOutput, match="operation"):
        parse_model_output(output(findings=[finding]))


# -- document rendering -----------------------------------------------------


def candidate_of(**changes) -> Candidate:
    return parse_model_output(
        output(candidates=[{**FULL_CANDIDATE, **changes}])
    ).candidates[0]


def test_the_document_follows_the_approved_section_order():
    document = candidate_of().document("SDLC-FR-0031")

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


def test_the_document_title_carries_the_requirement_identity():
    document = candidate_of().document("SDLC-FR-0031")

    assert document.splitlines()[0] == (
        "# SDLC-FR-0031 — Reject unauthenticated model execution"
    )


def test_the_document_has_no_provenance_section():
    """Provenance is the Derived From relation, never document prose."""
    assert "Provenance" not in candidate_of().document("SDLC-FR-0031")


def test_the_document_contains_every_section_body():
    document = candidate_of().document("SDLC-FR-0031")

    for value in FULL_CANDIDATE.values():
        if value not in {"FUNCTIONAL"}:
            assert value in document


def test_the_document_name_matches_the_root_document_convention():
    assert candidate_of(title="A Title").document_name("SDLC-NFR-0007") == (
        "SDLC-NFR-0007 — A Title"
    )


def test_rendering_is_deterministic():
    assert candidate_of().document("SDLC-FR-1") == candidate_of().document("SDLC-FR-1")
