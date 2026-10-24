"""Requirement-Human-Attestation-v0.1: an operator-decided text as authority.

The scenario is the one ARP1-CON-0132 met live: Process 1 leaves a material
question open, Review 1 confirms it, the operator writes the decision into
the Root between iterations, and Process 2 cites that text. Only an operator
attestation of exactly that text, for exactly that Requirement, lets the
Requirement's own text answer a material item; the Reviewer still judges
whether it is right.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest

from review_fake import verify_resolution
from sdlc.autonomous_ready import _guard
from sdlc.autonomy_policy import (
    DISABLED,
    AutonomyPolicies,
    AutonomyPolicyError,
    load_autonomy_policies,
)
from sdlc.human_attestation import (
    HumanAttestation,
    HumanAttestationError,
    HumanAttestations,
    attestation_fingerprint,
    parse_human_attestations,
)
from sdlc.ready_decision import (
    approve_standard_requirement,
    rework_standard_requirement,
)
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.results import ApplyResultCode as Apply
from sdlc.results import ReadyDecisionResultCode as Ready
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.review_prompt import INSTRUCTIONS as REVIEW_INSTRUCTIONS
from sdlc.review_result import WhatStatus, build_rework_brief
from sdlc.standard_review import VerificationOutcome
from sdlc.tsa_admission import AdmissionRefused, AdmissionResultCode
from standard_fake import (
    REQUIREMENT_ID,
    analysis_output,
    citation,
    resolution,
)
from test_autonomous_resolution import (
    DRAFT_QUOTE,
    INVENTED,
    LIMIT_QUOTE,
    POLICIES,
    SOURCE,
    admit,
    artifacts,
    delegated_resolution,
    latest_process,
    latest_review,
    process,
    processed,
    rejected_invention,
    review,
    reviewed,
    scene,
)

ENTITY = "std-uuid-1"
QUESTION = "Does the prohibition on persistence also forbid persisted logs?"
ORIGINAL = "Applies to every configured runtime."
DECISION = (
    "The prohibition includes service-generated logs and request records, "
    "whether or not they contain request data."
)
# Text an earlier iteration wrote: present in the input, attested by nobody.
MODEL_TEXT = "Logs may be kept for seven days when they hold no request data."
# The live ARP1 Requirements the shipped configuration attests (Requirement ID, entity).
CON_0132 = ("ARP1-CON-0132", "7355aefe-25c0-5188-aba7-dbb81b91b919")
FR_0129 = ("ARP1-FR-0129", "d13970e6-a090-5f20-bdb9-6c91f19f3981")
FR_0130 = ("ARP1-FR-0130", "30171077-3f8b-5da5-adfc-4305eef70c49")


def attested(*attestations):
    """A TEST-ONLY attestation snapshot; never configuration."""
    return AutonomyPolicies(
        attestations=HumanAttestations(
            attestations
            or (HumanAttestation("SDLC", REQUIREMENT_ID, ENTITY, DECISION, "Operator"),)
        )
    )


ATTESTED = attested()


def decision_resolution(quote=DECISION, extra_sources=()):
    return resolution(
        issue=QUESTION,
        answer="Yes: persisted logs and request records are forbidden.",
        sources=[citation("REQUIREMENT", quote), *extra_sources],
        justification="The operator's clarification in this Requirement says so.",
    )


def question_answer(item="R0001.Q0"):
    return {
        "item": item,
        "outcome": "RESOLVED",
        "explanation": "The clarification in the document answers it.",
        "resolution_index": 0,
    }


def open_question_reviewed():
    """Process 1 keeps the material question open; Review 1 confirms it."""
    ws, requirement, root = scene()
    processed(
        ws,
        requirement,
        analysis_output(questions=[{"detail": QUESTION, "material": True}]),
    )
    reviewed(
        ws,
        requirement,
        question_verifications=[
            {
                "question_index": 0,
                "outcome": "CONFIRMED",
                "material": True,
                "reason": "Open.",
            }
        ],
    )
    _, first = latest_review(ws)
    assert first.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert rework_standard_requirement(ws, requirement.id).is_normal
    return ws, requirement, root


def human_edit(ws, root, text=DECISION):
    """The operator writes the decision into the Root, outside any Process."""
    ws.content[root.secret] = ws.content[root.secret].replace(ORIGINAL, text)


def second_process(ws, requirement, policies=ATTESTED, **output):
    output.setdefault("normalized_changes", {"constraints_edge_cases": DECISION})
    output.setdefault("resolutions", [decision_resolution()])
    output.setdefault("rework", [question_answer()])
    return process(ws, requirement, analysis_output(**output), policies=policies)


def confirming_review(ws, requirement, policies=ATTESTED):
    return review(
        ws,
        requirement,
        policies=policies,
        rework_verifications=[
            {"item": "R0001.Q0", "outcome": "CONFIRMED", "reason": "Now settled."}
        ],
        resolution_verifications=[verify_resolution()],
    )


def human_decision_at_ready():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    result, _ = second_process(ws, requirement)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    result, model = confirming_review(ws, requirement)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    return ws, requirement, root, model


# -- case A: an attested human clarification can clear the material question ------


def test_an_attested_clarification_clears_the_material_question():
    ws, requirement, _, review_model = human_decision_at_ready()
    _, stored = latest_process(ws)
    assert stored.iteration == 2
    assert stored.resolutions[0].sources[0].fingerprint == stored.input_tree.fingerprint
    context = review_model.calls[0]["context"]
    listed = context.split("# OPERATOR-ATTESTED CLARIFICATIONS", 1)[1]
    assert listed.split("\n# ", 1)[0].count(DECISION) == 1
    assert "[attested by Operator, fingerprint" in listed
    _, final = latest_review(ws)
    assert final.what_status is WhatStatus.CLEAR
    assert final.resolution_verifications[0].outcome is VerificationOutcome.CONFIRMED
    assert ws.requirements[requirement.id].state == "Ready", "no automatic approval"
    assert approve_standard_requirement(ws, requirement.id, policies=ATTESTED).is_normal
    applied = apply_standard_requirement(ws, requirement.id, policies=ATTESTED)
    assert applied.code is Apply.REQUIREMENT_APPLIED, applied


def test_process_is_shown_only_this_requirements_attestations():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    other = HumanAttestation("SDLC", "SDLC-FR-0099", ENTITY, "Elsewhere decided.", "Op")
    _, model = second_process(
        ws,
        requirement,
        policies=attested(ATTESTED.attestations.attestations[0], other),
    )
    listed = model.calls[0]["context"].split("# OPERATOR-ATTESTED CLARIFICATIONS", 1)
    assert listed[1].split("\n# ", 1)[0].count(DECISION) == 1
    assert "Elsewhere decided." not in listed[1]


# -- cases B and H: no attestation, no authority ------------------------------------


def test_an_unattested_clarification_cannot_answer_the_material_question():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    before = len(ws.mutations)
    result, model = second_process(ws, requirement, policies=DISABLED)
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert "no current operator attestation" in " ".join(result.details)
    assert "R0001.Q0" in " ".join(result.details)
    assert len(model.calls) == 1 and ws.mutations[before:] == []


def test_earlier_model_text_cannot_answer_the_material_question():
    """Text in the input is not a human decision because it is in the input."""
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root, MODEL_TEXT)
    result, _ = second_process(
        ws,
        requirement,
        normalized_changes={"constraints_edge_cases": MODEL_TEXT},
        resolutions=[decision_resolution(MODEL_TEXT)],
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result


def test_a_raw_citation_beside_it_does_not_exempt_unattested_text():
    ws, requirement, root = open_question_reviewed()
    ws.content["raw-secret"] = SOURCE
    human_edit(ws, root, MODEL_TEXT)
    result, _ = second_process(
        ws,
        requirement,
        normalized_changes={"constraints_edge_cases": MODEL_TEXT},
        resolutions=[decision_resolution(MODEL_TEXT, [citation(quote=LIMIT_QUOTE)])],
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert "no current operator attestation" in " ".join(result.details)


def test_a_rebuttal_of_the_material_question_needs_attested_text_too():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root, MODEL_TEXT)
    rebuttal = {
        "item": "R0001.Q0",
        "outcome": "REBUTTED",
        "explanation": "The document already says so.",
        "evidence": [citation("REQUIREMENT", MODEL_TEXT)],
    }
    result, _ = second_process(
        ws,
        requirement,
        normalized_changes={"constraints_edge_cases": MODEL_TEXT},
        resolutions=[],
        rework=[rebuttal],
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result


def test_a_quote_beyond_the_attested_text_is_not_covered():
    ws, requirement, root = open_question_reviewed()
    widened = f"{DECISION} Analytics are exempt."
    human_edit(ws, root, widened)
    result, _ = second_process(
        ws,
        requirement,
        normalized_changes={"constraints_edge_cases": widened},
        resolutions=[decision_resolution(widened)],
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result


def test_a_non_material_item_is_governed_by_the_earlier_rules():
    """The rule binds only answers to material items; nothing else changes."""
    ws, requirement, _ = scene()
    processed(
        ws, requirement, analysis_output(resolutions=[decision_resolution(DRAFT_QUOTE)])
    )
    assert latest_process(ws)[1].resolutions[0].sources[0].quote == DRAFT_QUOTE


# -- case C: recovery from a review that rejected the human decision -----------------


def rejected_human_decision():
    """Review 2 rejected the attested answer, as ARP1-CON-0132's did."""
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    result, _ = second_process(ws, requirement)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    reviewed(
        ws,
        requirement,
        policies=ATTESTED,
        rework_verifications=[
            {
                "item": "R0001.Q0",
                "outcome": "REJECTED",
                "severity": "BLOCKING",
                "reason": "Not authority.",
            }
        ],
        resolution_verifications=[
            verify_resolution(
                outcome="REJECTED",
                failing=("authority_class_correct",),
                severity="BLOCKING",
            )
        ],
    )
    _, second = latest_review(ws)
    assert second.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert rework_standard_requirement(ws, requirement.id).is_normal
    brief = build_rework_brief(second, latest_process(ws)[1])
    return ws, requirement, brief


def third_process(ws, requirement, brief, resolutions, policies=ATTESTED):
    answers = [
        question_answer(ref)
        if ref in brief.what_refs | brief.resolution_refs
        else {"item": ref, "outcome": "RESOLVED", "explanation": "Settled."}
        for ref in brief.item_refs
    ]
    return process(
        ws,
        requirement,
        analysis_output(
            normalized_changes={"constraints_edge_cases": DECISION},
            resolutions=resolutions,
            rework=answers,
        ),
        policies=policies,
        authorized_new_cycle=True,
    )


def test_a_rejected_attested_decision_stays_recoverable():
    ws, requirement, brief = rejected_human_decision()
    assert brief.resolution_refs, "the rejected resolution is carried as an item"
    result, _ = third_process(ws, requirement, brief, [decision_resolution()])
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    _, third = latest_process(ws)
    assert third.iteration == 3 and third.rework_brief.source.review_iteration == 2


# The Requirement section Process 1 wrote: in the input, attested by nobody.
REQUIREMENT_TEXT = "The runtime must refuse to execute a model without login."


@pytest.mark.parametrize(
    "policies, quote",
    [(DISABLED, DECISION), (ATTESTED, REQUIREMENT_TEXT)],
    ids=["attestation-removed", "unattested-text"],
)
def test_recovery_never_lets_unattested_text_answer_the_rejected_item(policies, quote):
    ws, requirement, brief = rejected_human_decision()
    before = len(ws.mutations)
    result, _ = third_process(
        ws, requirement, brief, [decision_resolution(quote)], policies=policies
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert "no current operator attestation" in " ".join(result.details)
    assert ws.mutations[before:] == []


# -- case D: a changed or revoked attestation is stale, never silently reused --------


def test_an_attestation_changed_after_process_refuses_the_review():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    assert second_process(ws, requirement)[0].code is ProcessCode.REQUIREMENT_PROCESSED
    changed = attested(
        HumanAttestation(
            "SDLC", REQUIREMENT_ID, ENTITY, "Logs are allowed.", "Operator"
        )
    )
    result, model = confirming_review(ws, requirement, policies=changed)
    assert result.code is ReviewCode.RESOLUTION_EVIDENCE_STALE, result
    assert not model.was_invoked and len(artifacts(ws, "Review Result")) == 1


@pytest.mark.parametrize(
    "after",
    [
        DISABLED,
        attested(
            HumanAttestation(
                "SDLC", REQUIREMENT_ID, ENTITY, "Logs are allowed.", "Operator"
            )
        ),
    ],
    ids=["revoked", "changed"],
)
def test_a_revoked_attestation_refuses_ready_apply_and_tsa(after):
    ws, requirement, _, _ = human_decision_at_ready()
    before = len(ws.mutations)
    refused = approve_standard_requirement(ws, requirement.id, policies=after)
    assert refused.code is Ready.RESOLUTION_EVIDENCE_STALE, refused
    assert ws.mutations[before:] == []
    assert approve_standard_requirement(ws, requirement.id, policies=ATTESTED).is_normal
    applied = apply_standard_requirement(ws, requirement.id, policies=after)
    assert applied.code is Apply.RESOLUTION_EVIDENCE_STALE, applied
    assert ws.requirements[requirement.id].state == "Apply"
    applied = apply_standard_requirement(ws, requirement.id, policies=ATTESTED)
    assert applied.code is Apply.REQUIREMENT_APPLIED, applied
    with pytest.raises(AdmissionRefused) as caught:
        admit(ws, after)
    assert caught.value.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert admit(ws, ATTESTED).is_newly_written


def test_a_root_edited_after_review_is_stale_whatever_is_attested():
    ws, requirement, root, _ = human_decision_at_ready()
    ws.content[root.secret] += "\nA later edit.\n"
    refused = approve_standard_requirement(ws, requirement.id, policies=ATTESTED)
    assert not refused.is_normal, refused


# -- case E: an attestation authorizes exactly one Requirement -----------------------


@pytest.mark.parametrize(
    "wrong",
    [
        HumanAttestation("SDLC", REQUIREMENT_ID, "std-uuid-2", DECISION, "Operator"),
        HumanAttestation("SDLC", "SDLC-FR-0032", ENTITY, DECISION, "Operator"),
    ],
    ids=["other-entity", "other-requirement-id"],
)
def test_an_attestation_of_another_requirement_authorizes_nothing(wrong):
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    result, _ = second_process(ws, requirement, policies=attested(wrong))
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result


# -- case F: the RAW is never touched -----------------------------------------------


def test_the_raw_is_unchanged_through_the_whole_human_decision_cycle():
    ws, _, _, _ = human_decision_at_ready()
    assert ws.content["raw-secret"] == SOURCE
    assert all("raw-uuid-1" not in mutation for mutation in ws.mutations)


# -- case G: the Reviewer still judges the attested decision -------------------------


def test_the_reviewer_may_reject_an_attested_decision():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    assert second_process(ws, requirement)[0].code is ProcessCode.REQUIREMENT_PROCESSED
    result, _ = review(
        ws,
        requirement,
        policies=ATTESTED,
        rework_verifications=[
            {
                "item": "R0001.Q0",
                "outcome": "REJECTED",
                "severity": "BLOCKING",
                "reason": "It contradicts the RAW.",
            }
        ],
        resolution_verifications=[
            verify_resolution(
                outcome="REJECTED",
                failing=("consistent_with_raw",),
                severity="BLOCKING",
            )
        ],
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    _, stored = latest_review(ws)
    assert stored.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert approve_standard_requirement(ws, requirement.id, policies=ATTESTED).code is (
        Ready.MATERIAL_WHAT_UNRESOLVED
    )


def test_the_reviewer_is_not_told_all_requirement_text_is_model_output():
    assert "current content was written by the earlier analysis" not in (
        REVIEW_INSTRUCTIONS
    )
    assert "OPERATOR-ATTESTED CLARIFICATIONS" in REVIEW_INSTRUCTIONS
    assert "It does\n  not make the decision correct" in REVIEW_INSTRUCTIONS


def test_an_unattested_requirement_says_so_to_the_reviewer():
    ws, requirement, _ = scene()
    processed(ws, requirement, analysis_output())
    _, model = review(ws, requirement)
    assert (
        "(none: no text of this Requirement is attested" in (model.calls[0]["context"])
    )


# -- the configuration: exact content, exact Requirement, refused whole -------------


def clarification(**changes):
    entry = {
        "project_code": "ARP1",
        "requirement_id": "ARP1-CON-0132",
        "entity_id": "7355aefe-25c0-5188-aba7-dbb81b91b919",
        "text": DECISION,
        "approved_by": "Operator",
    }
    entry.update(changes)
    if "approved_fingerprint" not in entry:
        entry["approved_fingerprint"] = attestation_fingerprint(
            entry["project_code"],
            entry["requirement_id"],
            entry["entity_id"],
            entry["text"],
        )
    return entry


def test_an_absent_table_attests_nothing():
    assert parse_human_attestations(None) == HumanAttestations()


def test_an_approved_clarification_loads_exactly():
    loaded = parse_human_attestations({"clarifications": [clarification()]})
    (entry,) = loaded.attestations
    assert entry.text == DECISION
    assert loaded.for_requirement(
        "7355aefe-25c0-5188-aba7-dbb81b91b919", "ARP1-CON-0132"
    ) == (entry,)
    assert loaded.for_requirement("7355aefe-25c0-5188-aba7-dbb81b91b919", "X") == ()


@pytest.mark.parametrize(
    "entry, message",
    [
        (
            {**clarification(), "text": DECISION + " Except analytics."},
            "not the content",
        ),
        (clarification(signed_by="x"), "does not define"),
        (clarification(requirement_id="TSAP1-CON-0132"), "not a Requirement of"),
        (clarification(entity_id="std-uuid-1"), "lowercase UUID"),
        (clarification(project_code="arp1"), "exactly"),
        (clarification(project_code=7), "must be text"),
        (clarification(text="  "), "non-empty"),
        ({k: v for k, v in clarification().items() if k != "approved_by"}, "missing"),
        (clarification(approved_fingerprint="abc"), "64 lowercase hex"),
    ],
)
def test_a_broken_clarification_is_refused(entry, message):
    with pytest.raises(HumanAttestationError, match=message):
        parse_human_attestations({"clarifications": [entry]})


def test_a_repeated_attestation_is_refused():
    with pytest.raises(HumanAttestationError, match="repeats"):
        parse_human_attestations({"clarifications": [clarification(), clarification()]})


def test_the_snapshot_refuses_whole_on_a_broken_table(tmp_path):
    path = tmp_path / "sdlc.toml"
    path.write_text(
        '[autonomy]\nmode = "disabled"\n\n'
        '[[attestations.clarifications]]\nproject_code = "ARP1"\n',
        encoding="utf-8",
    )
    with pytest.raises(AutonomyPolicyError, match="missing"):
        load_autonomy_policies(path)


def test_the_snapshot_carries_attestations_and_delegates_nothing(tmp_path):
    entry = clarification()
    lines = "\n".join(f"{key} = {value!r}" for key, value in entry.items())
    path = tmp_path / "sdlc.toml"
    path.write_text(
        '[autonomy]\nmode = "disabled"\n\n[[attestations.clarifications]]\n'
        + lines.replace("'", '"')
        + "\n",
        encoding="utf-8",
    )
    loaded = load_autonomy_policies(path)
    assert loaded.policies == () and loaded.for_project("ARP1") is None
    assert [a.fingerprint for a in loaded.attestations.attestations] == [
        entry["approved_fingerprint"]
    ]


def test_the_repository_ships_exactly_the_approved_attestations():
    """The attestations are exactly the operator-approved ARP1 decisions: the
    ARP1-CON-0132 logging decision (ARP1 Gate 2T) and decisions A, B, C and D
    (ARP1 Gate 3F1). Any other, changed or extra attestation fails here."""
    shipped = load_autonomy_policies().attestations.attestations
    assert [
        (a.project_code, a.requirement_id, a.entity_id, a.approved_by, a.fingerprint)
        for a in shipped
    ] == [
        ("ARP1", *requirement, "Rostyslav Bachyk", fingerprint)
        for requirement, fingerprint in (
            (
                CON_0132,
                "e09cae68cb3db460170b1f00458931733c90af0a0960473336a77e1b42b56974",
            ),
            (
                CON_0132,
                "75b83c900bc9349363e88f648a8275940edc5b4089e20ebd304f0e45d3a4c31d",
            ),
            (
                FR_0129,
                "7f9bf51f8564190d03dae882b7ae2e21b8945f217689f4aafb568c7f76ef86e2",
            ),
            (
                CON_0132,
                "ab2ea09f0de1ad63778152bc67a7818cdc73881dad37c2849b4cd75cbb61f9d0",
            ),
            (
                FR_0129,
                "4f2e1e4b0b5030715e19566e133c1d3db99ad4ee67e813dae5652d6442351218",
            ),
            (
                FR_0130,
                "d0ff533b0304ebd047a1da134edf8bf151490bdb6aafad5d02d0049b670a2d25",
            ),
        )
    ]


def test_each_shipped_attestation_binds_only_its_own_requirement():
    """Two decisions for one Requirement stay two attestations, and none
    attests another Requirement, nor the same ID under another entity."""
    shipped = load_autonomy_policies().attestations
    counts = {
        CON_0132: 3,
        FR_0129: 2,
        FR_0130: 1,
        ("ARP1-NFR-0131", "a5792537-2fdf-5716-ac1d-4b590765e4a8"): 0,
        ("ARP1-CON-0133", "2be6e169-8e75-5171-9dbe-7740cc63e1b0"): 0,
        ("ARP1-CON-0132", FR_0129[1]): 0,
    }
    for (requirement_id, entity_id), count in counts.items():
        assert len(shipped.for_requirement(entity_id, requirement_id)) == count


def test_an_attestation_is_not_part_of_policy_identity():
    with_attestation = replace(DISABLED, attestations=ATTESTED.attestations)
    assert with_attestation.policies == DISABLED.policies


# -- review findings on b258865 ------------------------------------------------------


def test_a_delegated_default_keeps_its_clause_authority_on_rework():
    """Its REQUIREMENT source is applicability evidence, not attested authority."""
    ws, requirement = rejected_invention()
    answer = {
        "item": "R0001.A0",
        "outcome": "RESOLVED",
        "explanation": "Clause ERR-BODY permits it.",
        "resolution_index": 0,
    }
    result, _ = process(
        ws,
        requirement,
        analysis_output(
            normalized_changes={"constraints_edge_cases": INVENTED},
            rework=[answer],
            resolutions=[
                delegated_resolution(sources=[citation("REQUIREMENT", INVENTED)])
            ],
        ),
        policies=POLICIES,
        authorized_new_cycle=True,
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result


def test_the_reviewer_is_shown_only_this_requirements_attestations():
    ws, requirement, root = open_question_reviewed()
    human_edit(ws, root)
    assert second_process(ws, requirement)[0].code is ProcessCode.REQUIREMENT_PROCESSED
    other = HumanAttestation("SDLC", "SDLC-FR-0099", ENTITY, "Elsewhere decided.", "Op")
    _, model = confirming_review(
        ws,
        requirement,
        policies=attested(ATTESTED.attestations.attestations[0], other),
    )
    listed = model.calls[0]["context"].split("# OPERATOR-ATTESTED CLARIFICATIONS", 1)
    assert listed[1].split("\n# ", 1)[0].count(DECISION) == 1
    assert "Elsewhere decided." not in listed[1]


def test_the_process_prompt_lets_a_rejected_item_cite_attested_text():
    from sdlc.standard_prompt import INSTRUCTIONS

    assert "never cite it (kind\n  REQUIREMENT) for this item" not in INSTRUCTIONS
    assert "even when the rejected answer itself\n  came from that text" in (
        INSTRUCTIONS
    )


def test_autonomous_ready_refuses_when_attestations_change_before_its_write():
    ws, requirement, _, _ = human_decision_at_ready()
    project = ws.read_project(requirement.project_id)
    current = ws.read_requirement(requirement.id)
    evidence = SimpleNamespace(identity="evidence", requirement=current)
    delegation = SimpleNamespace(
        for_project=lambda code: SimpleNamespace(binding="authorization")
    )
    record = SimpleNamespace(project_code=project.code, authorization="authorization")

    def guard(after):
        return _guard(
            ws, current, record, evidence, ATTESTED, lambda: (delegation, after)
        )

    assert guard(ATTESTED)(evidence) is None
    assert guard(DISABLED)(evidence) == (
        "The operator attestations changed after the decision was made."
    )
