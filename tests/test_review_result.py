"""The Review Result artifact: naming, bindings, and self-consistency.

A Review Result is the evidence a human at Ready decides on, so reading one
back is not a formality. The verdict it stores is recomputed from the findings
it stores, because an artifact that disagrees with itself cannot be acted on.
"""

from __future__ import annotations

import json

import pytest

from review_fake import confirm, finding, new_finding, reject, review_output
from sdlc.normative_tree import TreeEntry, TreeManifest
from sdlc.review_result import (
    InvalidReviewResult,
    build_review_result,
    parse_review_result,
    parse_review_result_name,
    render_review_result,
    review_result_name,
)
from sdlc.standard_review import ReviewVerdict, parse_review_output

REQUIREMENT_ID = "SDLC-FR-0031"


def build(text=None, findings=(), relations=(), iteration=1, **bindings):
    review = parse_review_output(
        text if text is not None else review_output(),
        tuple(findings),
        tuple(relations),
    )
    return build_review_result(
        requirement_id=REQUIREMENT_ID,
        iteration=iteration,
        reviewed_document_fingerprint=bindings.get("document", "doc-fp"),
        reviewed_process_iteration=bindings.get("process_iteration", 1),
        reviewed_process_output_fingerprint=bindings.get("process_output", "out-fp"),
        review=review,
        reviewed_tree=root_only_manifest(bindings.get("document", "doc-fp")),
    )


def root_only_manifest(root_fingerprint, root_id="root-doc"):
    return TreeManifest(
        requirement_id=REQUIREMENT_ID,
        root_document_id=root_id,
        entries=(
            TreeEntry(
                document_id=root_id,
                parent_document_id=None,
                name="Root",
                content_fingerprint=root_fingerprint,
            ),
        ),
    )


def roundtrip(result):
    return parse_review_result(render_review_result(result))


# -- naming -----------------------------------------------------------------


def test_the_name_is_numbered_and_zero_padded():
    assert (
        review_result_name(REQUIREMENT_ID, 1)
        == f"{REQUIREMENT_ID} — Review Result 0001"
    )
    assert (
        review_result_name(REQUIREMENT_ID, 42)
        == f"{REQUIREMENT_ID} — Review Result 0042"
    )


def test_a_name_round_trips():
    name = review_result_name(REQUIREMENT_ID, 7)
    assert parse_review_result_name(name) == (REQUIREMENT_ID, 7)


def test_a_process_result_is_not_mistaken_for_a_review_result():
    """The two capabilities share a Root Document and are told apart by name."""
    assert parse_review_result_name(f"{REQUIREMENT_ID} — Process Result 0001") is None


@pytest.mark.parametrize(
    "name",
    [
        "SDLC-FR-0031 — Review Result 1",
        "SDLC-FR-0031 - Review Result 0001",
        "Review Result 0001",
        "SDLC-FR-0031 — Review Results 0001",
        "SDLC-FR-0031 — Review Result",
    ],
)
def test_a_name_that_is_not_the_artifact_is_not_parsed(name):
    assert parse_review_result_name(name) is None


# -- bindings ---------------------------------------------------------------


def test_the_result_records_exactly_what_it_reviewed():
    result = build(document="d1", process_iteration=3, process_output="o3")
    assert result.reviews("d1", 3, "o3")


@pytest.mark.parametrize(
    "bindings",
    [("other", 3, "o3"), ("d1", 4, "o3"), ("d1", 3, "other")],
)
def test_any_moved_binding_means_it_reviewed_something_else(bindings):
    result = build(document="d1", process_iteration=3, process_output="o3")
    assert not result.reviews(*bindings)


def test_bindings_survive_a_round_trip():
    result = build(document="d1", process_iteration=3, process_output="o3")
    assert roundtrip(result).reviews("d1", 3, "o3")


# -- the verdict is derived, and re-derived on read-back --------------------


def test_the_verdict_is_derived_when_the_artifact_is_built():
    result = build(
        review_output(finding_verifications=[confirm(severity="BLOCKING")]),
        (finding(),),
    )
    assert result.verdict is ReviewVerdict.BLOCKING


def test_a_persisted_verdict_that_contradicts_its_findings_is_rejected():
    """The artifact grades itself; neither half can be preferred over the other."""
    result = build(
        review_output(finding_verifications=[confirm(severity="BLOCKING")]),
        (finding(),),
    )
    tampered = render_review_result(result).replace('"BLOCKING",', '"PASS",', 1)
    with pytest.raises(InvalidReviewResult, match="contradicts the findings"):
        parse_review_result(tampered)


def test_a_tampered_severity_is_caught_by_the_recalculation():
    result = build(
        review_output(finding_verifications=[confirm(severity="INFO")]), (finding(),)
    )
    tampered = render_review_result(result).replace('"INFO"', '"BLOCKING"', 1)
    with pytest.raises(InvalidReviewResult, match="contradicts the findings"):
        parse_review_result(tampered)


def test_a_consistent_artifact_round_trips_unchanged():
    result = build(
        review_output(
            finding_verifications=[confirm(severity="WARNING"), reject(index=1)],
            new_findings=[new_finding(severity="INFO")],
            assessment={"clarity": "adequate"},
        ),
        (finding(), finding()),
    )
    stored = roundtrip(result)
    assert stored.verdict is ReviewVerdict.NEEDS_WORK
    assert stored == result


# -- what the artifact must carry -------------------------------------------


def test_unresolved_verifications_stay_visible_for_the_human():
    from review_fake import unresolved

    result = build(review_output(finding_verifications=[unresolved()]), (finding(),))
    stored = roundtrip(result)
    assert stored.verdict is ReviewVerdict.PASS
    assert stored.finding_verifications[0].reason


def test_confirmed_relations_are_persisted_for_a_future_apply():
    from review_fake import relation, verify_relation

    result = build(
        review_output(
            relation_verifications=[
                verify_relation(requirement_id="SDLC-FR-0002"),
                verify_relation(requirement_id="SDLC-FR-0003", outcome="REJECTED"),
            ]
        ),
        (),
        (
            relation(requirement_id="SDLC-FR-0002"),
            relation(requirement_id="SDLC-FR-0003"),
        ),
    )
    payload = json.loads(
        render_review_result(result).split("```json\n")[1].split("\n```")[0]
    )
    assert [r["requirement_id"] for r in payload["confirmed_relation_proposals"]] == [
        "SDLC-FR-0002"
    ]
    assert len(payload["relation_proposal_verifications"]) == 2


def test_no_chain_of_thought_field_exists_in_the_payload():
    result = build(review_output(assessment={"clarity": "fine"}))
    payload = json.loads(
        render_review_result(result).split("```json\n")[1].split("\n```")[0]
    )
    assert set(payload) == {
        "review_result_version",
        "iteration",
        "requirement_id",
        "reviewed_document_fingerprint",
        "reviewed_process_iteration",
        "reviewed_process_output_fingerprint",
        "reviewed_normative_tree",
        "derived_verdict",
        "process_finding_verifications",
        "relation_proposal_verifications",
        "confirmed_relation_proposals",
        "new_findings",
        "assessment",
    }


# -- refusing to trust a bad artifact ---------------------------------------


def test_a_document_without_a_payload_is_rejected():
    with pytest.raises(InvalidReviewResult, match="no JSON payload"):
        parse_review_result("# SDLC-FR-0031 — Review Result 0001\n\nNothing here.\n")


def test_invalid_json_is_rejected():
    with pytest.raises(InvalidReviewResult, match="not valid JSON"):
        parse_review_result("```json\n{not json}\n```")


def test_an_unsupported_version_is_rejected():
    result = build()
    tampered = render_review_result(result).replace('"0.3"', '"9.9"', 1)
    with pytest.raises(InvalidReviewResult, match="is not supported"):
        parse_review_result(tampered)


@pytest.mark.parametrize("value", ["0", "-1", "null", '"1"', "true"])
def test_a_non_positive_iteration_is_rejected(value):
    result = build()
    tampered = render_review_result(result).replace(
        '"iteration": 1,', f'"iteration": {value},', 1
    )
    with pytest.raises(InvalidReviewResult, match="not a positive integer"):
        parse_review_result(tampered)


def test_a_missing_binding_is_rejected():
    result = build()
    tampered = render_review_result(result).replace('"doc-fp"', '""', 1)
    with pytest.raises(InvalidReviewResult, match="reviewed_document_fingerprint"):
        parse_review_result(tampered)


def test_an_unknown_persisted_verdict_is_rejected():
    result = build()
    tampered = render_review_result(result).replace('"PASS"', '"MOSTLY_FINE"', 1)
    with pytest.raises(InvalidReviewResult, match="Unknown persisted verdict"):
        parse_review_result(tampered)


def test_a_persisted_verification_must_grade_iff_it_confirms():
    result = build(
        review_output(finding_verifications=[confirm(severity="INFO")]), (finding(),)
    )
    tampered = render_review_result(result).replace('"CONFIRMED"', '"REJECTED"', 1)
    with pytest.raises(InvalidReviewResult, match="if and only if"):
        parse_review_result(tampered)


# -- the persisted confirmed-relation mirror --------------------------------


def relation(kind="DEPENDS_ON", requirement_id="SDLC-FR-0002"):
    from sdlc.standard_analysis import ProposedRelation, RelationKind

    return ProposedRelation(
        kind=RelationKind(kind), requirement_id=requirement_id, rationale="r"
    )


def verified(kind="DEPENDS_ON", requirement_id="SDLC-FR-0002", outcome="CONFIRMED"):
    return {
        "kind": kind,
        "requirement_id": requirement_id,
        "outcome": outcome,
        "reason": "checked",
    }


def test_the_mirror_reads_back_the_confirmed_edges_the_reviewer_wrote():
    from sdlc.review_result import read_confirmed_relation_mirror
    from sdlc.standard_analysis import RelationKind

    result = build(
        review_output(
            relation_verifications=[
                verified(),
                verified("AFFECTS", "SDLC-FR-0003", outcome="REJECTED"),
            ]
        ),
        relations=(relation(), relation("AFFECTS", "SDLC-FR-0003")),
    )
    mirror = read_confirmed_relation_mirror(render_review_result(result))
    assert mirror == ((RelationKind.DEPENDS_ON, "SDLC-FR-0002"),)
    assert mirror == tuple(
        (v.kind, v.requirement_id) for v in result.confirmed_relations
    )


def test_an_absent_mirror_reads_as_empty():
    from sdlc.review_result import read_confirmed_relation_mirror

    text = render_review_result(build()).replace(
        '"confirmed_relation_proposals": []', '"confirmed_relation_proposals": null'
    )
    assert read_confirmed_relation_mirror(text) == ()


def test_a_mirror_entry_that_is_not_confirmed_is_rejected():
    from sdlc.review_result import read_confirmed_relation_mirror

    payload = json.loads(
        render_review_result(build()).split("```json\n")[1].split("\n```")[0]
    )
    payload["confirmed_relation_proposals"] = [verified(outcome="REJECTED")]
    text = "# x\n\n```json\n" + json.dumps(payload) + "\n```\n"
    with pytest.raises(InvalidReviewResult):
        read_confirmed_relation_mirror(text)


def test_a_malformed_mirror_entry_is_rejected():
    from sdlc.review_result import read_confirmed_relation_mirror

    payload = json.loads(
        render_review_result(build()).split("```json\n")[1].split("\n```")[0]
    )
    payload["confirmed_relation_proposals"] = [{"kind": "DEPENDS_ON"}]
    text = "# x\n\n```json\n" + json.dumps(payload) + "\n```\n"
    with pytest.raises(InvalidReviewResult):
        read_confirmed_relation_mirror(text)


def test_the_mirror_reader_refuses_a_document_without_a_payload():
    from sdlc.review_result import read_confirmed_relation_mirror

    with pytest.raises(InvalidReviewResult):
        read_confirmed_relation_mirror("# prose only\n")
