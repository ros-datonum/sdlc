"""Attested-Text-Preservation-v0.1: an attested text in the input comes back verbatim.

The live case is ARP1 Gate 3L3: FR-0129's Root held the operator-attested
D6-A paragraph, and Process 4's normalization split its last sentence ("…
segments, does not permit …" became "… segments. It does not permit …"). The
output still passed every check, so a paraphrase of a human decision became
the Requirement's text. Code now compares the input with the normalized output
and refuses before anything is written.
"""

from __future__ import annotations

import pytest

from processor_fake import FakeModelRuntime
from sdlc.autonomy_policy import DISABLED, AutonomyPolicies
from sdlc.human_attestation import HumanAttestation, HumanAttestations
from sdlc.process_result import parse_process_result
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.standard_processor import process_standard_requirement
from standard_fake import REQUIREMENT_ID, analysis_output, rendered_document
from test_autonomous_resolution import artifacts, latest_process, scene
from test_human_attestation import (
    DECISION,
    human_decision_at_ready,
    human_edit,
    open_question_reviewed,
    second_process,
)

ENTITY = "std-uuid-1"
# The approved ARP1 D6-A text, byte for byte (Gate 3L1).
D6A = (
    "For GET /v1/uppercase, rejection before application-handler dispatch because "
    "the encoded request-target exceeds the deployment's single effective maximum "
    "supported request-target length, which must be at least 8,000 octets, is a "
    "protocol-level length failure outside this Requirement's HTTP 200 JSON response "
    "guarantee. Such a request may receive HTTP 414 URI Too Long even when its query "
    "parameters would otherwise satisfy this Requirement's valid-request definition "
    "under the WHATWG application/x-www-form-urlencoded parsing algorithm. This "
    "clarification does not change the valid-request definition, including the "
    "treatment of empty ampersand-delimited segments, does not permit HTTP 414 for "
    "request-targets at or below the effective maximum solely because of their "
    "length, and does not weaken the HTTP 200 guarantee for valid requests that "
    "reach the application handler."
)
# Exactly what Gate 3L3's Process 4 wrote in its place.
D6A_AS_NORMALIZED = D6A.replace(
    "segments, does not permit", "segments. It does not permit"
).replace("length, and does not weaken", "length. It does not weaken")
D1 = (
    "The HTTP 200 JSON response guarantee applies to syntactically well-formed HTTP "
    "requests that reach the application handler."
)
FIRST = "Value length boundaries are 1 and 32 characters inclusive."
CONSTRAINTS = f"{FIRST}\n\n{D1}\n\n{D6A}"


def attested(*texts, entity=ENTITY, requirement_id=REQUIREMENT_ID):
    """A TEST-ONLY attestation snapshot; never configuration."""
    return AutonomyPolicies(
        attestations=HumanAttestations(
            tuple(
                HumanAttestation("SDLC", requirement_id, entity, text, "Operator")
                for text in texts
            )
        )
    )


D6A_ONLY = attested(D6A)
BOTH = attested(D1, D6A)


def rooted(constraints=CONSTRAINTS, **sections):
    """A Requirement in Process whose Root already holds the given sections."""
    ws, requirement, root = scene()
    ws.content[root.secret] = rendered_document(
        constraints_edge_cases=constraints, **sections
    )
    return ws, requirement, root


def run(ws, record, policies, /, **sections):
    model = FakeModelRuntime([analysis_output(normalized_changes=sections)])
    result = process_standard_requirement(ws, model, record.id, policies=policies)
    return result, model


def refused(policies, /, **sections):
    """Run once against CONSTRAINTS; require a refusal that wrote nothing."""
    ws, requirement, _ = rooted()
    before = (dict(ws.content), list(ws.documents), dict(ws.requirements))
    mutations = list(ws.mutations)
    result, model = run(ws, requirement, policies, **sections)
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert len(model.calls) == 1
    assert ws.mutations == mutations
    assert (dict(ws.content), list(ws.documents), dict(ws.requirements)) == before
    assert artifacts(ws, "Process Result") == []
    assert ws.requirements[requirement.id].state == "Process"
    return " ".join(result.details)


def processed(policies, constraints=CONSTRAINTS, /, **sections):
    ws, requirement, root = rooted(constraints)
    result, _ = run(ws, requirement, policies, **sections)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    return ws, requirement, root


# -- the Gate 3L3 regression ---------------------------------------------------


def test_the_gate_3l3_punctuation_change_is_refused_before_anything_is_written():
    detail = refused(
        D6A_ONLY,
        constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A_AS_NORMALIZED}",
    )
    fingerprint = D6A_ONLY.attestations.attestations[0].fingerprint[:12]
    assert (
        f"attestation {fingerprint} ALTERED_OR_DELETED (Constraints & Edge Cases)"
        in detail
    )
    assert REQUIREMENT_ID in detail
    # Diagnostics name the attestation and section, never the text.
    assert D6A not in detail and D6A_AS_NORMALIZED not in detail


def test_the_exact_d6a_still_produces_a_valid_process_result():
    ws, requirement, root = processed(D6A_ONLY, constraints_edge_cases=CONSTRAINTS)
    assert ws.requirements[requirement.id].state == "Review"
    assert ws.content[root.secret].count(D6A) == 1
    _, result = latest_process(ws)
    assert result.iteration == 1 and D6A in result.normalized.constraints_edge_cases


# -- what counts as a change ---------------------------------------------------


@pytest.mark.parametrize(
    ("constraints", "category"),
    [
        (
            f"{FIRST}\n\n{D1}\n\n{D6A.replace('dispatch because', 'dispatch since')}",
            "ALTERED_OR_DELETED",
        ),  # an equivalent paraphrase
        (
            f"{FIRST}\n\n{D1}\n\n{D6A.rsplit(' This clarification', 1)[0]}",
            "ALTERED_OR_DELETED",
        ),  # shortened
        (f"{FIRST}\n\n{D1}", "ALTERED_OR_DELETED"),  # deleted
        (f"{FIRST}\n\n{D1}\n\n{D6A}\n\n{D6A}", "DUPLICATED"),
        (
            f"{FIRST}\n\n{D1}\n\n{D6A} Proxies may also answer 431.",
            "PARAGRAPH_CHANGED",
        ),  # extended within its paragraph
        (f"{FIRST}\n\n{D1} {D6A}", "PARAGRAPH_CHANGED"),  # merged into D1's paragraph
    ],
    ids=["paraphrased", "shortened", "deleted", "duplicated", "extended", "merged"],
)
def test_any_change_to_the_attested_paragraph_is_refused(constraints, category):
    detail = refused(D6A_ONLY, constraints_edge_cases=constraints)
    assert f"{category} (Constraints & Edge Cases)" in detail


def test_moving_it_to_another_section_is_refused():
    detail = refused(
        D6A_ONLY,
        constraints_edge_cases=f"{FIRST}\n\n{D1}",
        detailed_behavior=f"Preflight runs the auth check before any call.\n\n{D6A}",
    )
    assert "MOVED (Constraints & Edge Cases, Detailed Behavior)" in detail


def test_unattested_wording_around_it_is_still_normalized():
    ws, _, root = processed(
        D6A_ONLY,
        constraints_edge_cases=f"Values are 1 to 32 characters long.\n\n{D1}\n\n{D6A}",
        requirement="The service must answer every valid request.",
    )
    assert "Values are 1 to 32 characters long." in ws.content[root.secret]
    assert ws.content[root.secret].count(D6A) == 1


def test_two_attestations_in_one_section_are_protected_independently():
    processed(BOTH, constraints_edge_cases=CONSTRAINTS)
    detail = refused(
        BOTH, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A_AS_NORMALIZED}"
    )
    d1, d6a = (a.fingerprint[:12] for a in BOTH.attestations.attestations)
    assert f"attestation {d6a} ALTERED_OR_DELETED" in detail and d1 not in detail
    detail = refused(BOTH, constraints_edge_cases=f"{FIRST}\n\n{D6A}")
    assert f"attestation {d1} ALTERED_OR_DELETED" in detail and d6a not in detail


# -- scope -----------------------------------------------------------------------


@pytest.mark.parametrize(
    "policies",
    [
        attested(D6A, entity="std-uuid-2"),  # another entity, same Requirement ID
        attested(D6A, requirement_id="SDLC-FR-0032"),  # same entity, another ID
        DISABLED,  # nothing attested
    ],
    ids=["other-entity", "other-requirement", "none"],
)
def test_text_attested_for_no_one_here_is_ordinary_wording(policies):
    ws, _, root = processed(
        policies, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A_AS_NORMALIZED}"
    )
    assert D6A_AS_NORMALIZED in ws.content[root.secret]


def test_an_attestation_absent_from_the_input_is_not_injected():
    ws, _, root = processed(
        D6A_ONLY,
        f"{FIRST}\n\n{D1}",
        constraints_edge_cases=f"{FIRST}\n\n{D1}",
    )
    assert D6A not in ws.content[root.secret]


def test_the_model_may_not_insert_an_attestation_the_input_lacks():
    ws, requirement, root = rooted(f"{FIRST}\n\n{D1}")
    content = ws.content[root.secret]
    result, _ = run(
        ws, requirement, D6A_ONLY, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A}"
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "INSERTED (Constraints & Edge Cases)" in " ".join(result.details)
    assert ws.content[root.secret] == content


# -- the authority rules are unchanged -------------------------------------------


def test_a_material_answer_citing_the_preserved_attested_text_still_passes():
    ws, requirement, _, _ = human_decision_at_ready()
    assert ws.requirements[requirement.id].state == "Ready"


def test_a_material_answer_citing_unattested_text_is_still_refused_as_before():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    result, _ = second_process(ws, requirement, policies=DISABLED)
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "Unattested items: R0001.Q0" in " ".join(result.details)


def test_a_rework_that_alters_the_attested_decision_leaves_history_untouched():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    history = {
        d.secret: ws.content[d.secret] for d in ws.documents if d.secret != root.secret
    }
    content, documents, mutations = (
        ws.content[root.secret],
        list(ws.documents),
        list(ws.mutations),
    )
    result, model = second_process(
        ws,
        requirement,
        normalized_changes={
            "constraints_edge_cases": DECISION.replace(", whether", "; whether")
        },
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT
    assert "ALTERED_OR_DELETED" in " ".join(result.details)
    assert len(model.calls) == 1 and ws.mutations == mutations
    assert ws.content[root.secret] == content and ws.documents == documents
    assert {s: ws.content[s] for s in history} == history
    assert len(artifacts(ws, "Process Result")) == 1
    second_process(ws, requirement)  # the verbatim answer still goes through
    assert len(artifacts(ws, "Process Result")) == 2


def test_an_earlier_result_that_paraphrased_an_attested_text_stays_readable():
    """History is never re-certified: a Process Result persisted before the text
    was attested, or before this rule, parses exactly as it did."""
    ws, _, _ = processed(
        DISABLED, constraints_edge_cases=f"{FIRST}\n\n{D1}\n\n{D6A_AS_NORMALIZED}"
    )
    node, result = latest_process(ws)
    assert result.iteration == 1
    assert parse_process_result(ws.content[node.secret]).normalized == result.normalized
