"""RW-R05: the Requirement abstraction corpus, applied through the real stages.

Each case's reference outputs run through the stages where its property
matters (the RAW processor, Standard Process, Standard Review) on the Fibery
fakes with a fake model runtime, and the semantic checks of
`abstraction_corpus` are applied to what the stage validated and persisted.
Paraphrase controls remove the reference wording and still pass; negative
controls feed structurally valid outputs that break one semantic property and
prove the checks fail on that property, not on the JSON.
"""

import json

import pytest

from abstraction_corpus import (
    ANSWER_INVENTED,
    ARCHITECTURE_UPSTREAM,
    CASES,
    CORPUS,
    FINDING_MISSING,
    FINDING_UNWARRANTED,
    IMPLEMENTATION_PROMOTED,
    MANDATE_DROPPED,
    QUESTION_CLOSED,
    TEST_MECHANICS,
    UNESTABLISHED_CANDIDATE,
    AbstractionCase,
    asserted_kinds,
    decomposition_violations,
    normalization_violations,
    review_violations,
)
from processor_fake import FakeModelRuntime, build_workspace
from review_fake import build_review_workspace, stored_review
from review_fake import finding as process_claim
from sdlc.process_result import parse_process_result
from sdlc.processing_result import parse_processing_result, processing_result_name
from sdlc.raw_processing import (
    MISSING_INFORMATION,
    NO_OPEN_QUESTIONS,
    OPEN_QUESTIONS_KEY,
    SECTION_KEYS,
    Category,
    parse_model_output,
)
from sdlc.raw_processor import process_raw_requirement
from sdlc.results import (
    ProcessResultCode,
    StandardProcessResultCode,
    StandardReviewResultCode,
)
from sdlc.standard_analysis import NormalizedRequirement, parse_analysis_output
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import REQUIREMENT_ID, build_standard_workspace, process_results

# The ten classes, verbatim from the frozen RW-R05 Required Change.
FROZEN_CLASSES = (
    "one product capability with multiple technical implementation details",
    "two truly independent obligations in one RAW source",
    "an explicit source-mandated technical constraint",
    "a technical suggestion that is not a mandatory Requirement",
    "acceptance evidence vs exact test implementation",
    "an unresolved product decision",
    "an unresolved architecture decision",
    "field-level detail that is not independently meaningful",
    "a legitimate non-functional Requirement",
    "a legitimate system constraint",
)
PROCESS_CASES = [case for case in CORPUS if case.process]
REVIEW_CASES = [case for case in CORPUS if case.review]

TIMEOUT_CASE = "C01_one_capability_many_implementation_details"
ACCEPTANCE_CASE = "C05_acceptance_evidence_not_test_implementation"
OVERRIDE_CASE = "C06_unresolved_product_decision"
ARCHITECTURE_CASE = "C07_unresolved_architecture_decision"


def ids(cases):
    return [case.case_id for case in cases]


def rules(violations):
    return {violation.rule for violation in violations}


def with_candidates(case, *candidates):
    return {**case.decomposition, "candidates": list(candidates)}


def first_candidate(case, **changes):
    return {**case.decomposition["candidates"][0], **changes}


def wording(candidate):
    """Every word the candidate states, for proving a marker is absent."""
    return " ".join(str(value) for value in candidate.values()).lower()


def root_sections(sections):
    """Every schema section, with the fixed text for those not given."""
    return {
        key: sections.get(
            key,
            NO_OPEN_QUESTIONS if key == OPEN_QUESTIONS_KEY else MISSING_INFORMATION,
        )
        for key in SECTION_KEYS
    }


# -- meaning-preserving paraphrases that avoid the reference wording ---------------

C01_PARAPHRASE = {
    "category": "FUNCTIONAL",
    "title": "Bound provider run duration",
    "requirement": "Provider execution has a configured maximum duration. "
    "Exceeding it produces a deadline-exceeded outcome for the caller.",
    "acceptance_verification": "A run that goes past its maximum duration "
    "ends, and its caller receives a deadline-exceeded outcome.",
}
C01_SOURCE_MARKERS = ("time limit", "timeout")

C06_PARAPHRASE = first_candidate(
    CASES[OVERRIDE_CASE],
    open_questions="May an operator bypass a failed Review decision? The "
    "source leaves this undecided.",
)
C06_SOURCE_MARKER = "override"

C05_PARAPHRASE = first_candidate(
    CASES[ACCEPTANCE_CASE],
    requirement="When a Ready Requirement is sent back for rework, its previous "
    "processing outcome is no longer presented as the outcome of the next "
    "processing round.",
    acceptance_verification="After rework, the next cycle reports whether it "
    "succeeded or failed, and the earlier outcome is not displayed as that "
    "cycle's result.",
)
C05_SOURCE_MARKERS = ("new cycle", "success or failure")


# -- stage runners: the reference or a supplied output, through the real stage ----


def decompose(case: AbstractionCase, output=None):
    """The candidates the RAW processor validated and persisted for `case`."""
    ws, raw, _ = build_workspace()
    ws.content["raw-secret"] = case.source
    model = FakeModelRuntime([json.dumps(output or case.decomposition)])

    result = process_raw_requirement(ws, model, raw.id)

    assert result.code is ProcessResultCode.RAW_REQUIREMENT_PROCESSED, result
    assert ws.content["raw-secret"] == case.source
    [artifact] = [
        d for d in ws.documents if d.name == processing_result_name(raw.requirement_id)
    ]
    persisted = parse_processing_result(ws.content[artifact.secret])
    assert len(ws.produces(raw.id)) == len(persisted.candidates)
    return [keyed.candidate for keyed in persisted.candidates]


def normalize(case: AbstractionCase, output=None):
    """The Process Result Standard Process persisted for the case's draft."""
    scenario = case.process
    reference = output or scenario.reference
    ws, std, root = build_standard_workspace()
    ws.content[root.secret] = NormalizedRequirement(
        title=reference["normalized_requirement"]["title"],
        **root_sections(scenario.draft),
    ).document(REQUIREMENT_ID)
    ws.content["raw-secret"] = case.source
    model = FakeModelRuntime([json.dumps(reference)])

    result = process_standard_requirement(ws, model, std.id)

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED, result
    [node] = process_results(ws)
    return parse_process_result(ws.content[node.secret])


def review(case: AbstractionCase, output=None):
    """The defects Standard Review asserted about the case's Root."""
    scenario = case.review
    claims = [process_claim(kind, detail) for kind, detail in scenario.process_findings]
    ws, std, _root, _ = build_review_workspace(
        findings=claims, normalized_changes=root_sections(scenario.root)
    )
    ws.content["raw-secret"] = case.source
    model = FakeModelRuntime([json.dumps(output or scenario.reference)])

    result = review_standard_requirement(ws, model, std.id)

    assert result.code is StandardReviewResultCode.REQUIREMENT_REVIEWED, result
    assert case.source.splitlines()[0] in model.calls[0]["context"]
    stored = stored_review(ws)
    return asserted_kinds(
        [kind for kind, _ in scenario.process_findings],
        stored.finding_verifications,
        stored.new_findings,
    )


# -- AC1: every class has explicit expected properties ------------------------------


def test_the_corpus_covers_exactly_the_ten_frozen_classes():
    assert [case.abstraction_class for case in CORPUS] == list(FROZEN_CLASSES)
    assert len(CASES) == len(CORPUS), "case ids are unique"


@pytest.mark.parametrize("case", CORPUS, ids=ids(CORPUS))
def test_every_case_states_its_classification_and_boundary_properties(case):
    assert case.obligations, "the source-established obligations are explicit"
    for obligation in case.obligations:
        assert obligation.category in Category
        assert obligation.concepts
        assert all(concept.alternatives for concept in obligation.concepts)
    boundary = (
        case.implementation_detail,
        case.mandated,
        case.open_question,
        case.architecture_question,
        case.acceptance,
        case.test_mechanics,
        case.never_findings,
    )
    assert any(boundary), "each case pins at least one WHAT/HOW property"
    if case.process:
        assert len(case.obligations) == 1, "one Standard Requirement is processed"


# -- the reference outputs satisfy every property through the real stages --------


@pytest.mark.parametrize("case", CORPUS, ids=ids(CORPUS))
def test_the_reference_decomposition_satisfies_the_case(case):
    assert decomposition_violations(case, decompose(case)) == []


@pytest.mark.parametrize("case", PROCESS_CASES, ids=ids(PROCESS_CASES))
def test_the_reference_normalization_satisfies_the_case(case):
    result = normalize(case)

    assert normalization_violations(case, result.normalized, result.findings) == []


@pytest.mark.parametrize("case", REVIEW_CASES, ids=ids(REVIEW_CASES))
def test_the_reference_review_satisfies_the_case(case):
    assert review_violations(case, review(case)) == []


# -- AC5: any validated structured output can be checked; wording is not golden ---


@pytest.mark.parametrize("case", CORPUS, ids=ids(CORPUS))
def test_a_bare_model_output_can_be_checked_without_running_a_stage(case):
    """How a reviewer or dogfood harness applies a case to a live output."""
    parsed = parse_model_output(json.dumps(case.decomposition))

    assert decomposition_violations(case, parsed.candidates) == []


def test_an_analysis_output_can_be_checked_without_running_a_stage():
    case = CASES[ACCEPTANCE_CASE]
    analysis = parse_analysis_output(json.dumps(case.process.reference))

    assert normalization_violations(case, analysis.normalized, analysis.findings) == []


def test_c01_paraphrase_without_the_source_markers_still_carries_the_obligation():
    case = CASES[TIMEOUT_CASE]
    assert not any(marker in wording(C01_PARAPHRASE) for marker in C01_SOURCE_MARKERS)

    paraphrase = with_candidates(case, C01_PARAPHRASE)

    assert decomposition_violations(case, decompose(case, paraphrase)) == []


def test_c06_open_question_reworded_without_override_stays_open():
    case = CASES[OVERRIDE_CASE]
    assert C06_SOURCE_MARKER not in wording(C06_PARAPHRASE)

    reworded = with_candidates(case, C06_PARAPHRASE)

    assert decomposition_violations(case, decompose(case, reworded)) == []


def test_c05_acceptance_paraphrase_without_the_source_markers_is_still_observable():
    case = CASES[ACCEPTANCE_CASE]
    assert not any(marker in wording(C05_PARAPHRASE) for marker in C05_SOURCE_MARKERS)

    paraphrase = with_candidates(case, C05_PARAPHRASE)

    assert decomposition_violations(case, decompose(case, paraphrase)) == []


def test_c07_reworded_architecture_question_is_still_caught():
    """The architecture question is a meaning too: rewording does not hide it."""
    case = CASES[ARCHITECTURE_CASE]
    reworded = first_candidate(
        case, open_questions="Which enforcement mechanism stops an over-long run?"
    )
    assert "cancellation mechanism" not in wording(reworded)

    violations = decomposition_violations(
        case, decompose(case, with_candidates(case, reworded))
    )

    assert ARCHITECTURE_UPSTREAM in rules(violations), violations


# -- AC2: implementation detail promoted to Requirement is caught -----------------

WATCHDOG_CANDIDATE = {
    "category": "FUNCTIONAL",
    "title": "Escalate a watchdog to SIGKILL",
    "requirement": "A watchdog thread must send SIGTERM and then SIGKILL to the "
    "provider process group.",
}
FIELD_CANDIDATE = {
    "category": "FUNCTIONAL",
    "title": "Add request_id to ModelRequest",
    "requirement": "ModelRequest must carry a request_id: UUID field.",
}


@pytest.mark.parametrize(
    ("case_id", "promoted", "expected"),
    [
        pytest.param(
            TIMEOUT_CASE,
            lambda case: with_candidates(
                case, case.decomposition["candidates"][0], WATCHDOG_CANDIDATE
            ),
            {IMPLEMENTATION_PROMOTED, UNESTABLISHED_CANDIDATE},
            id="C01-watchdog-becomes-a-requirement",
        ),
        pytest.param(
            "C04_technical_suggestion_not_mandatory",
            lambda case: with_candidates(
                case,
                first_candidate(
                    case,
                    constraints_edge_cases="Failures must be delivered through a "
                    "Redis queue read by a notifier worker.",
                ),
            ),
            {IMPLEMENTATION_PROMOTED},
            id="C04-suggestion-becomes-a-constraint",
        ),
        pytest.param(
            ACCEPTANCE_CASE,
            lambda case: with_candidates(
                case,
                first_candidate(
                    case,
                    acceptance_verification="Run pytest with fixture "
                    "`ready_requirement` and a mock of FiberyAdapter.write.",
                ),
            ),
            {TEST_MECHANICS},
            id="C05-test-mechanics-become-acceptance",
        ),
        pytest.param(
            "C08_field_detail_without_independent_meaning",
            lambda case: with_candidates(
                case, case.decomposition["candidates"][0], FIELD_CANDIDATE
            ),
            {IMPLEMENTATION_PROMOTED, UNESTABLISHED_CANDIDATE},
            id="C08-field-becomes-a-requirement",
        ),
    ],
)
def test_promoting_implementation_detail_is_caught(case_id, promoted, expected):
    case = CASES[case_id]

    violations = decomposition_violations(case, decompose(case, promoted(case)))

    assert expected <= rules(violations), violations


def test_normalization_that_keeps_test_mechanics_unreported_is_caught():
    case = CASES[ACCEPTANCE_CASE]
    kept = {
        "normalized_requirement": {
            **case.process.reference["normalized_requirement"],
            "acceptance_verification": case.process.draft["acceptance_verification"],
        },
        "findings": [],
    }
    result = normalize(case, kept)

    violations = normalization_violations(case, result.normalized, result.findings)

    assert {TEST_MECHANICS, FINDING_MISSING} <= rules(violations), violations


# -- AC3: a dropped source-mandated constraint is caught ---------------------------

ARGV_CASE = "C03_source_mandated_technical_constraint"
WITHOUT_ARGV = (
    "Caller-controlled input must never be interpreted as shell command syntax."
)


def test_a_decomposition_that_drops_the_mandate_is_caught():
    case = CASES[ARGV_CASE]
    dropped = with_candidates(case, first_candidate(case, requirement=WITHOUT_ARGV))

    violations = decomposition_violations(case, decompose(case, dropped))

    assert MANDATE_DROPPED in rules(violations), violations


def test_a_normalization_that_drops_the_mandate_is_caught():
    case = CASES[ARGV_CASE]
    dropped = {
        "normalized_requirement": {
            "title": "Never interpret caller input as shell syntax",
            "requirement": WITHOUT_ARGV,
        },
        "findings": [{"kind": "IMPLEMENTATION_LEAKAGE", "detail": "argv removed."}],
    }
    result = normalize(case, dropped)

    violations = normalization_violations(case, result.normalized, result.findings)

    assert {MANDATE_DROPPED, FINDING_UNWARRANTED} <= rules(violations), violations


def test_a_review_that_confirms_leakage_on_the_mandate_is_caught():
    case = CASES[ARGV_CASE]
    confirmed = {
        "finding_verifications": [
            {
                "process_finding_index": 0,
                "outcome": "CONFIRMED",
                "severity": "WARNING",
                "reason": "argv is an implementation choice.",
            }
        ]
    }

    violations = review_violations(case, review(case, confirmed))

    assert FINDING_UNWARRANTED in rules(violations), violations


# -- AC4: an invented answer to an open product question is caught -----------------

ANSWERED = (
    "A failed Review returns the Requirement to the human with its failure "
    "reasons, and an operator can override a failed Review decision."
)
ANSWERED_WITH_BYPASS = (
    "A failed Review returns the Requirement to the human with its failure "
    "reasons, and an operator can bypass a failed Review decision."
)


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param(ANSWERED, id="override-wording"),
        pytest.param(ANSWERED_WITH_BYPASS, id="bypass-wording"),
    ],
)
def test_a_decomposition_that_answers_the_open_question_is_caught(answer):
    case = CASES[OVERRIDE_CASE]
    answered = with_candidates(
        case,
        first_candidate(case, requirement=answer, open_questions=""),
    )

    violations = decomposition_violations(case, decompose(case, answered))

    assert {QUESTION_CLOSED, ANSWER_INVENTED} <= rules(violations), violations


def test_a_normalization_that_answers_the_open_question_is_caught():
    case = CASES[OVERRIDE_CASE]
    answered = {
        "normalized_requirement": {
            "title": "Return failed Reviews to the human",
            "requirement": ANSWERED,
        },
        "findings": [],
    }
    result = normalize(case, answered)

    violations = normalization_violations(case, result.normalized, result.findings)

    assert {QUESTION_CLOSED, ANSWER_INVENTED} <= rules(violations), violations
