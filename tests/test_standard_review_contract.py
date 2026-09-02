"""The structured reviewer contract and the derived verdict.

The two properties under test here are the ones that make review meaningful
rather than decorative: the model cannot state a verdict, and it cannot quietly
drop a Process claim it would rather not address.
"""

from __future__ import annotations

import json

import pytest

from review_fake import (
    confirm,
    finding,
    new_finding,
    reject,
    relation,
    review_output,
    unresolved,
    verify_relation,
)
from sdlc.standard_analysis import FindingKind, RelationKind
from sdlc.standard_review import (
    FindingVerification,
    InvalidReviewOutput,
    NewFinding,
    ReviewSeverity,
    ReviewVerdict,
    VerificationOutcome,
    derive_verdict,
    parse_review_output,
)

ONE_FINDING = (finding(),)
ONE_RELATION = (relation(),)


def parse(text, findings=(), relations=()):
    return parse_review_output(text, tuple(findings), tuple(relations))


# -- the model cannot author a verdict --------------------------------------


def test_the_contract_has_no_verdict_field_at_all():
    """The strongest guarantee available: a verdict is not expressible."""
    with pytest.raises(InvalidReviewOutput, match="does not define"):
        parse(json.dumps({"verdict": "PASS"}))


def test_a_claimed_verdict_is_rejected_even_alongside_valid_content():
    payload = json.loads(review_output(finding_verifications=[confirm()]))
    payload["derived_verdict"] = "PASS"
    with pytest.raises(InvalidReviewOutput, match="does not define"):
        parse(json.dumps(payload), ONE_FINDING)


def test_a_response_cannot_pass_while_confirming_a_blocking_finding():
    """The contradiction the derivation exists to prevent."""
    review = parse(
        review_output(finding_verifications=[confirm(severity="BLOCKING")]),
        ONE_FINDING,
    )
    verdict = derive_verdict(review.finding_verifications, review.new_findings)
    assert verdict is ReviewVerdict.BLOCKING


# -- verdict derivation -----------------------------------------------------


def confirmed(severity):
    return FindingVerification(
        process_finding_index=0,
        outcome=VerificationOutcome.CONFIRMED,
        reason="r",
        severity=severity,
    )


def discovered(severity):
    return NewFinding(kind=FindingKind.NOT_TESTABLE, severity=severity, detail="d")


@pytest.mark.parametrize(
    ("severities", "expected"),
    [
        ((), ReviewVerdict.PASS),
        ((ReviewSeverity.INFO,), ReviewVerdict.PASS),
        ((ReviewSeverity.INFO, ReviewSeverity.INFO), ReviewVerdict.PASS),
        ((ReviewSeverity.WARNING,), ReviewVerdict.NEEDS_WORK),
        ((ReviewSeverity.INFO, ReviewSeverity.WARNING), ReviewVerdict.NEEDS_WORK),
        ((ReviewSeverity.BLOCKING,), ReviewVerdict.BLOCKING),
        (
            (ReviewSeverity.INFO, ReviewSeverity.WARNING, ReviewSeverity.BLOCKING),
            ReviewVerdict.BLOCKING,
        ),
    ],
)
def test_verdict_is_the_worst_severity_asserted(severities, expected):
    assert derive_verdict(tuple(confirmed(s) for s in severities), ()) is expected


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        (ReviewSeverity.INFO, ReviewVerdict.PASS),
        (ReviewSeverity.WARNING, ReviewVerdict.NEEDS_WORK),
        (ReviewSeverity.BLOCKING, ReviewVerdict.BLOCKING),
    ],
)
def test_a_new_finding_drives_the_verdict_exactly_as_a_confirmed_one(
    severity, expected
):
    assert derive_verdict((), (discovered(severity),)) is expected


def test_a_confirmed_process_finding_contributes_its_severity():
    """Without this a confirmed blocking Process finding would derive PASS.

    Process findings carry no severity of their own, so the grade the reviewer
    assigns when confirming one is the only thing that can drive the verdict.
    """
    review = parse(
        review_output(finding_verifications=[confirm(severity="BLOCKING")]),
        ONE_FINDING,
    )
    assert derive_verdict(review.finding_verifications, ()) is ReviewVerdict.BLOCKING


def test_a_rejected_process_finding_contributes_nothing():
    review = parse(review_output(finding_verifications=[reject()]), ONE_FINDING)
    assert derive_verdict(review.finding_verifications, ()) is ReviewVerdict.PASS


def test_an_unresolved_process_finding_contributes_nothing():
    """Uncertainty is not a defect claim; it stays visible instead."""
    review = parse(review_output(finding_verifications=[unresolved()]), ONE_FINDING)
    assert derive_verdict(review.finding_verifications, ()) is ReviewVerdict.PASS
    assert review.finding_verifications[0].outcome is VerificationOutcome.UNRESOLVED


# -- coverage of every Process claim ----------------------------------------


def test_every_process_finding_must_be_verified():
    with pytest.raises(InvalidReviewOutput, match="leaves a Process claim unverified"):
        parse(review_output(finding_verifications=[]), (finding(), finding()))


def test_a_process_finding_cannot_be_verified_twice():
    with pytest.raises(InvalidReviewOutput, match="more than once"):
        parse(review_output(finding_verifications=[confirm(), reject()]), ONE_FINDING)


def test_a_verification_cannot_address_a_finding_that_does_not_exist():
    with pytest.raises(InvalidReviewOutput, match="but the Process Result has 1"):
        parse(review_output(finding_verifications=[confirm(index=3)]), ONE_FINDING)


def test_a_negative_finding_index_is_rejected():
    with pytest.raises(InvalidReviewOutput, match="addresses Process finding -1"):
        parse(review_output(finding_verifications=[confirm(index=-1)]), ONE_FINDING)


def test_every_proposed_relation_must_be_verified():
    with pytest.raises(InvalidReviewOutput, match="leaves a Process claim unverified"):
        parse(review_output(), (), ONE_RELATION)


def test_a_relation_verification_cannot_invent_a_proposal():
    with pytest.raises(InvalidReviewOutput, match="did not claim"):
        parse(
            review_output(relation_verifications=[verify_relation()]),
            (),
            (relation(kind=RelationKind.AFFECTS),),
        )


def test_a_relation_cannot_be_verified_twice():
    with pytest.raises(InvalidReviewOutput, match="more than once"):
        parse(
            review_output(
                relation_verifications=[verify_relation(), verify_relation()]
            ),
            (),
            ONE_RELATION,
        )


def test_the_same_edge_proposed_twice_needs_one_verification():
    """A relation is identified by its edge, so a repeat is the same claim."""
    review = parse(
        review_output(relation_verifications=[verify_relation()]),
        (),
        (relation(), relation()),
    )
    assert len(review.relation_verifications) == 1


# -- severity is tied to asserting a defect ---------------------------------


def test_confirming_a_finding_requires_a_severity():
    with pytest.raises(InvalidReviewOutput, match="must grade its severity"):
        parse(
            review_output(
                finding_verifications=[
                    {"process_finding_index": 0, "outcome": "CONFIRMED", "reason": "r"}
                ]
            ),
            ONE_FINDING,
        )


@pytest.mark.parametrize("outcome", ["REJECTED", "UNRESOLVED"])
def test_a_non_confirming_verification_must_not_carry_a_severity(outcome):
    with pytest.raises(InvalidReviewOutput, match="must not"):
        parse(
            review_output(
                finding_verifications=[
                    {
                        "process_finding_index": 0,
                        "outcome": outcome,
                        "severity": "BLOCKING",
                        "reason": "r",
                    }
                ]
            ),
            ONE_FINDING,
        )


# -- closed vocabularies ----------------------------------------------------


@pytest.mark.parametrize("value", ["CRITICAL", "MINOR", "pass", ""])
def test_an_unknown_severity_is_rejected(value):
    with pytest.raises(InvalidReviewOutput):
        parse(
            review_output(finding_verifications=[confirm(severity=value)]), ONE_FINDING
        )


@pytest.mark.parametrize("value", ["MAYBE", "AGREED", "confirmed"])
def test_an_unknown_outcome_is_rejected(value):
    with pytest.raises(InvalidReviewOutput):
        parse(
            review_output(
                finding_verifications=[
                    {"process_finding_index": 0, "outcome": value, "reason": "r"}
                ]
            ),
            ONE_FINDING,
        )


def test_an_unknown_finding_kind_is_rejected():
    with pytest.raises(InvalidReviewOutput):
        parse(review_output(new_findings=[new_finding(kind="SLOPPY")]))


# -- mutation vocabulary is structurally inexpressible ----------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"operation": "UPDATE"},
        {"operations": [{"kind": "RETIRE"}]},
        {"apply": True},
        {"supersede": "SDLC-FR-0002"},
        {"actions": ["APPLY"]},
    ],
)
def test_a_mutation_instruction_has_nowhere_to_appear(payload):
    """Closed key sets, so an instruction cannot be smuggled in at top level."""
    with pytest.raises(InvalidReviewOutput, match="does not define"):
        parse(json.dumps(payload))


@pytest.mark.parametrize("key", ["operation", "action", "apply", "supersede"])
def test_a_mutation_key_is_rejected_inside_a_verification(key):
    entry = {**confirm(), key: "UPDATE"}
    with pytest.raises(InvalidReviewOutput, match="does not define"):
        parse(review_output(finding_verifications=[entry]), ONE_FINDING)


@pytest.mark.parametrize("kind", ["UPDATE", "RETIRE", "SUPERSEDE", "APPLY"])
def test_mutation_words_are_not_finding_kinds(kind):
    with pytest.raises(InvalidReviewOutput):
        parse(review_output(new_findings=[new_finding(kind=kind)]))


def test_an_unknown_key_in_a_new_finding_is_rejected():
    entry = {**new_finding(), "confidence": 0.9}
    with pytest.raises(InvalidReviewOutput, match="does not define"):
        parse(review_output(new_findings=[entry]))


def test_an_unknown_assessment_key_is_rejected():
    with pytest.raises(InvalidReviewOutput, match="does not define"):
        parse(review_output(assessment={"vibes": "good"}))


def test_reasoning_prose_instead_of_json_is_rejected():
    with pytest.raises(InvalidReviewOutput, match="not valid JSON"):
        parse("Let me think about this step by step. First,")


# -- new findings -----------------------------------------------------------


def test_a_comparison_finding_must_name_the_requirement_it_is_about():
    with pytest.raises(InvalidReviewOutput, match="must name the Requirement"):
        parse(review_output(new_findings=[new_finding(kind="POSSIBLE_DUPLICATE")]))


def test_a_quality_finding_must_not_name_another_requirement():
    entry = {**new_finding(), "requirement_id": "SDLC-FR-0002"}
    with pytest.raises(InvalidReviewOutput, match="must not"):
        parse(review_output(new_findings=[entry]))


def test_a_comparison_finding_needs_a_real_requirement_id():
    entry = {**new_finding(kind="POSSIBLE_CONFLICT"), "requirement_id": "the other one"}
    with pytest.raises(InvalidReviewOutput, match="not a Requirement ID"):
        parse(review_output(new_findings=[entry]))


def test_the_review_may_discover_a_finding_process_never_reported():
    review = parse(review_output(new_findings=[new_finding(severity="BLOCKING")]))
    assert review.new_findings[0].kind is FindingKind.NOT_TESTABLE
    assert review.new_findings[0].severity is ReviewSeverity.BLOCKING


# -- confirmed relations ----------------------------------------------------


def test_only_confirmed_proposals_are_offered_to_a_future_apply():
    review = parse(
        review_output(
            relation_verifications=[
                verify_relation(requirement_id="SDLC-FR-0002"),
                verify_relation(
                    kind="AFFECTS", requirement_id="SDLC-FR-0003", outcome="REJECTED"
                ),
            ]
        ),
        (),
        (
            relation(requirement_id="SDLC-FR-0002"),
            relation(kind=RelationKind.AFFECTS, requirement_id="SDLC-FR-0003"),
        ),
    )
    assert [r.requirement_id for r in review.confirmed_relations] == ["SDLC-FR-0002"]
    # The rejected one is still recorded: a human at Ready sees both.
    assert len(review.relation_verifications) == 2


def test_an_empty_review_of_an_empty_process_result_is_valid():
    review = parse(review_output())
    assert review.finding_verifications == ()
    assert derive_verdict((), ()) is ReviewVerdict.PASS
