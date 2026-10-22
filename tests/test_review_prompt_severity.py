"""The Reviewer prompt teaches the same severity contract the validators enforce.

Severity is conditional and the condition differs by list: a finding
verification carries one exactly when it CONFIRMS a Process finding; a
dependency, rework or resolution verification exactly when it REJECTS (there
CONFIRMED asserts that no defect remains); every new finding carries one; a
relation verification never does. The first live review of a resolved Rework
Brief item was refused as INVALID_MODEL_OUTPUT because the prompt showed the
rework severity unconditionally and stated the finding rule without scoping
it, so the model graded a CONFIRMED rework verification.

The prompt is read from a real review: the production reviewer builds it and
the fake model runtime records exactly what it received.
"""

from __future__ import annotations

import re

import pytest

from sdlc.results import StandardReviewResultCode as ReviewCode
from test_rework_brief import review_again, reviews, reworked, verify


@pytest.fixture(scope="module")
def rework_review():
    """A real review of a RESOLVED rework response: (result, instructions, context)."""
    ws, requirement, _ = reworked()
    result, model = review_again(
        ws, requirement, rework_verifications=[verify("R0001.F0")]
    )
    call = model.calls[0]
    return ws, result, call["prompt"], call["context"]


def shape_entry(prompt: str, key: str) -> str:
    """The JSON shape's entry for `key`: its lines up to the closing bracket."""
    match = re.search(
        rf'^  "{key}": \[\n(.*?)^  \],?$', prompt, re.MULTILINE | re.DOTALL
    )
    assert match, f"the prompt shape has no {key} entry"
    return match.group(1)


def severity_line(entry: str) -> str | None:
    lines = [line for line in entry.splitlines() if '"severity"' in line]
    assert len(lines) <= 1
    return lines[0].strip() if lines else None


def rule(prompt: str, opening: str) -> str:
    """The `Rules:` bullet that starts with `opening`, joined onto one line."""
    match = re.search(
        rf"^- {re.escape(opening)}(.*?)(?=^- |\Z)", prompt, re.MULTILINE | re.DOTALL
    )
    assert match, f"no rule starting {opening!r}"
    return " ".join((opening + match.group(1)).split())


def outcome_clause(text: str, outcome: str) -> str:
    """What `text` says about `outcome`, up to the next outcome it names."""
    match = re.search(
        rf"{outcome}:(.*?)(?=(?:CONFIRMED|REJECTED|UNRESOLVED):|$)", text, re.DOTALL
    )
    assert match, f"no {outcome} clause in {text!r}"
    return match.group(1)


# -- the exact live failure -----------------------------------------------------


def test_a_confirmed_rework_verification_of_a_resolved_item_omits_severity(
    rework_review,
):
    ws, result, prompt, context = rework_review
    assert "Answer: RESOLVED" in context and "[R0001.F0]" in context
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    latest = reviews(ws)[-1][1]
    assert latest.iteration == 2 and latest.rework_verifications[0].severity is None
    entry = shape_entry(prompt, "rework_verifications")
    assert (
        severity_line(entry)
        == '"severity": "REJECTED only: INFO" | "WARNING" | "BLOCKING",'
    )
    rework = rule(prompt, "Rework responses (only when the context lists them)")
    confirmed = outcome_clause(rework, "CONFIRMED")
    assert "no severity" in confirmed
    assert "give" not in confirmed.lower().replace("given", "")


# -- the shape marks each conditional severity next to its object ----------------


@pytest.mark.parametrize(
    "key, expected",
    [
        (
            "finding_verifications",
            '"severity": "CONFIRMED only: INFO" | "WARNING" | "BLOCKING",',
        ),
        (
            "dependency_verifications",
            '"severity": "REJECTED only: INFO" | "WARNING" | "BLOCKING",',
        ),
        (
            "rework_verifications",
            '"severity": "REJECTED only: INFO" | "WARNING" | "BLOCKING",',
        ),
        (
            "resolution_verifications",
            '"severity": "REJECTED only: INFO" | "WARNING" | "BLOCKING",',
        ),
        ("new_findings", '"severity": "INFO" | "WARNING" | "BLOCKING",'),
        ("relation_verifications", None),
        ("question_verifications", None),
    ],
)
def test_the_shape_states_each_severity_condition(rework_review, key, expected):
    _, _, prompt, _ = rework_review
    assert severity_line(shape_entry(prompt, key)) == expected


def test_an_absent_severity_is_an_omitted_key(rework_review):
    _, _, prompt, _ = rework_review
    legend = " ".join(prompt.split("\nSeverity: ", 1)[1].split("\n\n", 1)[0].split())
    assert "is given exactly when the outcome is that one" in legend
    assert (
        'omit the "severity" key entirely (no null, no empty string, no placeholder)'
        in legend
    )
    assert "Every new finding carries its own severity" in legend
    assert (
        "relation_verifications and question_verifications carry no severity" in legend
    )


# -- each list's rule, per outcome ------------------------------------------------


def test_the_finding_rule_is_scoped_to_finding_verifications(rework_review):
    _, _, prompt, _ = rework_review
    findings = rule(prompt, "In finding_verifications, give a severity")
    assert (
        "give a severity only when you CONFIRM a Process finding, and always when you do"
        in findings
    )
    assert (
        "REJECTED and UNRESOLVED assert no defect there, so they must carry no severity"
        in findings
    )
    assert "This rule is for finding_verifications only" in findings
    assert (
        "in dependency_verifications, rework_verifications and resolution_verifications "
        "CONFIRMED asserts that no defect remains, so there only REJECTED carries a severity"
    ) in findings
    assert "\n- Give a severity only when you CONFIRM" not in prompt


def test_new_findings_always_carry_their_own_severity(rework_review):
    _, _, prompt, _ = rework_review
    assert (
        "Report anything the earlier analysis missed as a new finding, with its own\n  severity."
        in prompt
    )


@pytest.mark.parametrize(
    "opening, required, absent",
    [
        (
            "Verify every existing DEPENDS_ON edge exactly once",
            {"REJECTED": "always give a severity"},
            {"CONFIRMED": "no severity", "UNRESOLVED": "no severity"},
        ),
        (
            "Rework responses (only when the context lists them)",
            {"REJECTED": "Always give the severity"},
            {"CONFIRMED": "no severity", "UNRESOLVED": "No severity"},
        ),
    ],
)
def test_dependency_and_rework_rules_grade_only_a_rejection(
    rework_review, opening, required, absent
):
    _, _, prompt, _ = rework_review
    text = rule(prompt, opening)
    for outcome, phrase in required.items():
        assert phrase in outcome_clause(text, outcome)
    for outcome, phrase in absent.items():
        clause = outcome_clause(text, outcome)
        assert phrase in clause
        assert (
            "give a severity" not in clause.lower()
            and "give the severity" not in clause.lower()
        )


def test_the_resolution_rule_grades_only_a_rejection(rework_review):
    _, _, prompt, _ = rework_review
    text = rule(prompt, "Resolutions (only when the context lists them)")
    assert "CONFIRMED requires every check to PASS" in text
    assert "NOT_APPLICABLE as above), with no severity." in text
    assert (
        "Any FAIL is REJECTED, with the severity of the unsupported or unauthorized decision."
        in text
    )
    assert "Otherwise any UNCERTAIN is UNRESOLVED, with no severity." in text


def test_relation_verifications_are_never_graded(rework_review):
    _, _, prompt, _ = rework_review
    assert severity_line(shape_entry(prompt, "relation_verifications")) is None
    relations = rule(prompt, "Verify every listed proposed relation exactly once")
    assert "severity" not in relations
