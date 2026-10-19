"""WI-4 — normative dependency bindings (Requirement-Dependency-Bindings-v0.1).

Every test drives the production stages over the fake Fibery and fake model
runtimes: Process, Review, Ready approve, Apply and TSA admission, with no
mocked acceptance. The Uppercase Service example uses the saved FR-0124
normalized text from the historical TSAP1 evidence, offline only.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from processor_fake import FakeModelRuntime, reserialize_like_fibery
from review_fake import (
    build_review_workspace,
    give_reviewed_evidence,
    relation,
    review_output,
    rewrite_payload,
    verify_relation,
)
from sdlc import dependency_evidence
from sdlc.fibery_workspace import FiberyError, RequirementRecord
from sdlc.process_result import parse_process_result
from sdlc.ready_decision import (
    approve_standard_requirement,
    rework_standard_requirement,
)
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.results import ApplyResultCode as Apply
from sdlc.results import ReadyDecisionResultCode as Ready
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.review_result import (
    DependencyBinding,
    DependencyOrigin,
    InvalidReviewResult,
    build_review_result,
    build_rework_brief,
    parse_review_result,
    render_review_result,
)
from sdlc.rework_brief import BriefCategory
from sdlc.standard_analysis import NormalizedRequirement, ProductQuestion, RelationKind
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_review import (
    DependencyVerification,
    MaterialWhat,
    ReviewOutput,
    VerificationOutcome,
    WhatStatus,
)
from sdlc.standard_reviewer import review_standard_requirement
from sdlc.tsa_admission import AdmissionResultCode
from standard_fake import REQUIREMENT_ID, analysis_output
from test_tsa_admission import clean_refusal, start, world

FR_0124_EVIDENCE = (
    Path(__file__).parent
    / "fixtures"
    / "requirements_autonomy"
    / "tsap1_fr0124_process_result_0001.md"
)
DEPENDS = RelationKind.DEPENDS_ON
AFFECTS = RelationKind.AFFECTS
VALIDITY = "What makes a request to GET /v1/uppercase valid?"


def peer(number, state="Applied", project_id="p-1", title=None):
    return RequirementRecord(
        id=f"std-peer-{number}",
        public_id=str(number),
        requirement_id=f"SDLC-FR-{number:04d}",
        title=title or f"Peer {number}",
        type_name="Standard",
        state=state,
        revision=1,
        project_id=project_id,
        source_fingerprint=None,
    )


D1, D2, D3 = peer(41), peer(42), peer(43)


def dep(target, outcome="CONFIRMED", reason="It owns the definition.", **fields):
    return {
        "requirement_id": target.requirement_id,
        "outcome": outcome,
        "reason": reason,
        **fields,
    }


def world_with(
    peers=(D1,),
    existing=(),
    proposals=(),
    evidence=None,
    questions=(),
    normalized_changes=None,
):
    """R in Review over its Process Result, with peers as reviewed authority.

    `evidence` maps a peer to the peers it already DEPENDS_ON; peers are
    given evidence in order, so dependencies come first. `existing` are R's
    DEPENDS_ON edges in Fibery.
    """
    ws, requirement, root, _ = build_review_workspace(
        others=tuple(peers),
        relations=tuple(
            relation(kind, target.requirement_id) for kind, target in proposals
        ),
        questions=tuple(ProductQuestion(**question) for question in questions),
        normalized_changes=normalized_changes,
    )
    for record, depends_on in (evidence or {p: () for p in peers}).items():
        give_reviewed_evidence(ws, record, depends_on=tuple(depends_on))
    if existing:
        ws.depends_on_ids[requirement.id] = [target.id for target in existing]
    return ws, requirement, root


def review(ws, requirement, **response):
    model = FakeModelRuntime([review_output(**response)])
    return review_standard_requirement(ws, model, requirement.id), model


def stored_review(ws):
    nodes = [d for d in ws.documents if d.name.startswith(f"{REQUIREMENT_ID} — Review")]
    node = nodes[-1]
    return node, parse_review_result(reserialize_like_fibery(ws.content[node.secret]))


def peer_root(ws, record):
    return next(d for d in ws.documents if d.entity_public_id == record.public_id)


def edit_peer(ws, record, text="\nA changed rule.\n"):
    ws.content[peer_root(ws, record).secret] += text


def reviewed_with(peers=(D1,), existing=(D1,), **response):
    ws, requirement, root = world_with(peers=peers, existing=existing)
    response.setdefault("dependency_verifications", [dep(p) for p in existing])
    result, _ = review(ws, requirement, **response)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    return ws, requirement, root


def bind_by_hand(ws, record, target):
    """A peer whose Review binds `target` and whose edge points at it.

    The binding's fingerprints are placeholders: a cycle is found before any
    currentness comparison, so they are never consulted.
    """
    node = next(
        d
        for d in ws.documents
        if d.parent_document_id == peer_root(ws, record).id
        and "Review Result" in d.name
    )
    stored = parse_review_result(ws.content[node.secret])
    ws.content[node.secret] = render_review_result(
        replace(
            stored,
            dependency_verifications=(
                DependencyVerification(
                    target.requirement_id, VerificationOutcome.CONFIRMED, "Cycle."
                ),
            ),
            dependency_bindings=(
                DependencyBinding(
                    target.requirement_id,
                    target.id,
                    DependencyOrigin.EXISTING,
                    "0" * 64,
                    1,
                    "0" * 64,
                ),
            ),
        )
    )
    ws.depends_on_ids[record.id] = [target.id]


def rewrite_peer_review(ws, record, **output):
    """Replace a peer's Review Result with one carrying `output`."""
    root = peer_root(ws, record)
    node = next(
        d
        for d in ws.documents
        if d.parent_document_id == root.id and "Review" in d.name
    )
    stored = parse_review_result(ws.content[node.secret])
    rebuilt = build_review_result(
        stored.requirement_id,
        stored.iteration,
        stored.reviewed_document_fingerprint,
        stored.reviewed_process_iteration,
        stored.reviewed_process_output_fingerprint,
        ReviewOutput((), (), (), {}, **output),
        stored.reviewed_tree,
        reviewed_product_questions=(),
    )
    ws.content[node.secret] = render_review_result(rebuilt)


def approved(ws, requirement):
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is Ready.REQUIREMENT_APPROVED, result
    return result


def tsa_scene(ws):
    scene = world()
    scene.req = ws
    ws.calls.clear()
    return scene


# -- relation semantics reach both stages ---------------------------------------


def test_process_reads_the_existing_relations_with_their_direction():
    ws, requirement, _ = world_with(peers=(D1, D2), existing=(D1,))
    ws.affects_ids[requirement.id] = [D2.id]
    ws._replace(requirement.id, state="Process")
    model = FakeModelRuntime([analysis_output()])
    process_standard_requirement(ws, model, requirement.id, authorized_new_cycle=True)
    context, prompt = model.calls[0]["context"], model.calls[0]["prompt"]
    assert f"- DEPENDS_ON {D1.requirement_id}" in context
    assert f"- AFFECTS {D2.requirement_id}" in context
    assert (
        "AFFECTS does not establish" in prompt
        or "never in place of DEPENDS_ON" in prompt
    )


def test_review_receives_the_interpretation_set():
    ws, requirement, _ = world_with(
        peers=(D2, D1), existing=(D1,), evidence={D2: (), D1: (D2,)}
    )
    _, model = review(ws, requirement, dependency_verifications=[dep(D1)])
    context = model.calls[0]["context"]
    section = context.split("# Interpretation set (normative dependencies)")[1]
    assert f"- {D1.requirement_id} (existing DEPENDS_ON edge; Applied)" in section
    assert f"- {D2.requirement_id} (transitive dependency; Applied)" in section


# -- bindings --------------------------------------------------------------------


def test_no_dependencies_bind_nothing():
    ws, requirement, _ = world_with(peers=())
    result, _ = review(ws, requirement)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    _, stored = stored_review(ws)
    assert stored.version == "0.6" and stored.dependency_bindings == ()


def test_one_direct_dependency_is_bound_to_its_exact_version():
    ws, requirement, _ = reviewed_with()
    _, stored = stored_review(ws)
    [binding] = stored.dependency_bindings
    members = dependency_evidence.resolve_interpretation_set(
        ws, ws.requirements[requirement.id], (D1.requirement_id,)
    )
    assert binding == members[D1.requirement_id].binding(DependencyOrigin.EXISTING)
    assert binding.entity_id == D1.id and binding.review_iteration == 1


def test_multiple_and_transitive_dependencies_are_bound():
    ws, requirement, _ = world_with(
        peers=(D3, D2, D1),
        existing=(D1, D2),
        evidence={D3: (), D2: (), D1: (D3,)},
    )
    result, _ = review(ws, requirement, dependency_verifications=[dep(D1), dep(D2)])
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    _, stored = stored_review(ws)
    assert [(b.requirement_id, b.origin) for b in stored.dependency_bindings] == [
        (D1.requirement_id, DependencyOrigin.EXISTING),
        (D2.requirement_id, DependencyOrigin.EXISTING),
        (D3.requirement_id, DependencyOrigin.TRANSITIVE),
    ]


def test_an_altered_binding_is_refused_on_read():
    ws, _, _ = reviewed_with()
    node, _ = stored_review(ws)
    payload = json.loads(
        ws.content[node.secret].split("```json\n")[1].split("\n```")[0]
    )
    payload["dependency_bindings"][0]["origin"] = "PROPOSED"
    rewrite_payload(ws, node, dependency_bindings=payload["dependency_bindings"])
    with pytest.raises(InvalidReviewResult, match="disagree with the verified"):
        parse_review_result(ws.content[node.secret])


def test_an_altered_binding_fingerprint_is_stale_at_ready():
    ws, requirement, _ = reviewed_with()
    node, _ = stored_review(ws)
    payload = json.loads(
        ws.content[node.secret].split("```json\n")[1].split("\n```")[0]
    )
    payload["dependency_bindings"][0]["tree_fingerprint"] = "0" * 64
    rewrite_payload(ws, node, dependency_bindings=payload["dependency_bindings"])
    before = len(ws.mutations)
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is Ready.DEPENDENCY_EVIDENCE_STALE, result
    assert ws.mutations[before:] == []


# -- the reviewer verifies existing dependencies exactly once --------------------


@pytest.mark.parametrize(
    "verifications, message",
    [
        (None, "its absence verifies none"),
        ([dep(D1), dep(D1)], "more than once"),
        ([dep(D1), dep(D2)], "did not claim"),
        ([dep(D1, "REJECTED")], "if and only if"),
    ],
)
def test_existing_dependencies_are_verified_exactly_once(verifications, message):
    ws, requirement, _ = world_with(peers=(D1, D2), existing=(D1,))
    body = json.loads(review_output(dependency_verifications=verifications or []))
    if verifications is None:
        body.pop("dependency_verifications", None)
    result = review_standard_requirement(
        ws, FakeModelRuntime([json.dumps(body)]), requirement.id
    )
    assert result.code is ReviewCode.INVALID_MODEL_OUTPUT, result
    assert message in " ".join(result.details)


def test_a_false_or_misdirected_dependency_is_a_graded_defect():
    ws, requirement, _ = world_with(
        existing=(D1,), questions=({"detail": VALIDITY, "material": True},)
    )
    result, _ = review(
        ws,
        requirement,
        dependency_verifications=[
            dep(
                D1,
                "REJECTED",
                "D1 depends on this one, not the reverse.",
                severity="WARNING",
            )
        ],
        question_verifications=[
            {
                "question_index": 0,
                "outcome": "REJECTED",
                "basis": "ANSWERED_BY_OTHER_REQUIREMENT",
                "requirement_id": D1.requirement_id,
                "reason": "D1 states it.",
            }
        ],
    )
    assert result.verdict == "NEEDS_WORK", result
    _, stored = stored_review(ws)
    assert stored.what_status is WhatStatus.BLOCKED_ON_WHAT, (
        "a rejected edge answers nothing"
    )


# -- proposed versus written relations -------------------------------------------


def test_a_rejected_proposal_is_neither_bound_nor_written():
    ws, requirement, _ = world_with(proposals=((DEPENDS, D1),))
    review(
        ws,
        requirement,
        relation_verifications=[
            verify_relation(requirement_id=D1.requirement_id, outcome="REJECTED")
        ],
    )
    _, stored = stored_review(ws)
    assert stored.dependency_bindings == ()
    approved(ws, requirement)
    assert (
        apply_standard_requirement(ws, requirement.id).code is Apply.REQUIREMENT_APPLIED
    )
    assert ws.depends_on_ids.get(requirement.id, []) == []


def test_a_confirmed_proposal_is_bound_and_written_only_by_apply():
    ws, requirement, _ = world_with(
        peers=(D1, D2), existing=(D1,), proposals=((DEPENDS, D2),)
    )
    review(
        ws,
        requirement,
        dependency_verifications=[dep(D1)],
        relation_verifications=[verify_relation(requirement_id=D2.requirement_id)],
    )
    _, stored = stored_review(ws)
    assert {(b.requirement_id, b.origin) for b in stored.dependency_bindings} == {
        (D1.requirement_id, DependencyOrigin.EXISTING),
        (D2.requirement_id, DependencyOrigin.PROPOSED),
    }
    approved(ws, requirement)
    assert ws.depends_on_ids[requirement.id] == [D1.id], "not written before Apply"
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is Apply.REQUIREMENT_APPLIED, result
    assert ws.depends_on_ids[requirement.id] == [D1.id, D2.id], "existing edge kept"


def test_an_interrupted_apply_resumes_with_a_partially_written_graph():
    ws, requirement, _ = world_with(
        peers=(D1, D2), proposals=((DEPENDS, D1), (DEPENDS, D2))
    )
    review(
        ws,
        requirement,
        relation_verifications=[
            verify_relation(requirement_id=D1.requirement_id),
            verify_relation(requirement_id=D2.requirement_id),
        ],
    )
    approved(ws, requirement)
    original = ws.add_depends_on
    calls = []

    def second_fails(entity_id, target):
        calls.append(target)
        if len(calls) == 2:
            raise FiberyError("write failed")
        return original(entity_id, target)

    ws.add_depends_on = second_fails
    partial = apply_standard_requirement(ws, requirement.id)
    assert partial.code is Apply.PARTIAL_APPLY, partial
    assert ws.depends_on_ids[requirement.id] == [D1.id]
    ws.add_depends_on = original
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is Apply.REQUIREMENT_APPLIED, result
    assert sorted(ws.depends_on_ids[requirement.id]) == [D1.id, D2.id]


def test_a_dependency_not_yet_applied_blocks_apply_but_not_review_or_approval():
    pending = peer(44, state="Ready")
    ws, requirement, _ = world_with(peers=(pending,), existing=(pending,))
    result, model = review(ws, requirement, dependency_verifications=[dep(pending)])
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert "(existing DEPENDS_ON edge; Ready)" in model.calls[0]["context"]
    approved(ws, requirement)
    before = len(ws.mutations)
    applied = apply_standard_requirement(ws, requirement.id)
    assert applied.code is Apply.DEPENDENCY_NOT_APPLIED, applied
    assert pending.requirement_id in applied.details
    assert ws.mutations[before:] == []


# -- staleness at Ready, Apply and TSA --------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        lambda ws: edit_peer(ws, D1),
        lambda ws: ws.content.__setitem__(
            ws.create_child_document("Shared rule", peer_root(ws, D1).id).secret,
            "A new normative child.\n",
        ),
        lambda ws: give_reviewed_evidence(ws, ws.requirements[D1.id], iteration=2),
        lambda ws: ws._replace(D1.id, requirement_id="SDLC-FR-0999"),
        lambda ws: ws.requirements.__setitem__(
            "std-dup", replace(D1, id="std-dup", public_id="99")
        ),
    ],
    ids=["root", "normative-child", "review", "vanished", "ambiguous"],
)
def test_a_changed_dependency_is_stale_at_ready_and_apply(change):
    ws, requirement, _ = reviewed_with()
    change(ws)
    before = len(ws.mutations)
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is Ready.DEPENDENCY_EVIDENCE_STALE, refused
    assert ws.mutations[before:] == []
    ws.set_requirement_state(requirement.id, "Apply")  # a direct Fibery move
    before = len(ws.mutations)
    applied = apply_standard_requirement(ws, requirement.id)
    assert applied.code is Apply.DEPENDENCY_EVIDENCE_STALE, applied
    assert ws.mutations[before:] == [], "no relation or State write"


def test_a_dependency_changed_between_approval_and_apply_writes_nothing():
    ws, requirement, _ = world_with(peers=(D1,), proposals=((DEPENDS, D1),))
    review(
        ws,
        requirement,
        relation_verifications=[verify_relation(requirement_id=D1.requirement_id)],
    )
    approved(ws, requirement)
    edit_peer(ws, D1)
    before = len(ws.mutations)
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is Apply.DEPENDENCY_EVIDENCE_STALE, result
    assert (
        ws.mutations[before:] == [] and ws.requirements[requirement.id].state == "Apply"
    )


def test_an_edge_added_after_review_is_stale():
    ws, requirement, _ = reviewed_with(peers=(D1, D2))
    ws.depends_on_ids[requirement.id].append(D2.id)
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is Ready.DEPENDENCY_EVIDENCE_STALE, result


def test_an_unrelated_affects_change_does_not_invalidate_evidence():
    ws, requirement, _ = reviewed_with(peers=(D1, D2))
    ws.affects_ids[requirement.id] = [D2.id]
    edit_peer(ws, D2)
    assert (
        approve_standard_requirement(ws, requirement.id).code
        is Ready.REQUIREMENT_APPROVED
    )


# -- cycles -----------------------------------------------------------------------


def test_an_existing_cycle_refuses_review_before_the_model():
    ws, requirement, _ = world_with(peers=(D1,), existing=(D1,))
    bind_by_hand(ws, D1, ws.requirements[requirement.id])
    result, model = review(ws, requirement, dependency_verifications=[dep(D1)])
    assert result.code is ReviewCode.DEPENDENCY_CYCLE, result
    assert not model.was_invoked


def test_a_self_dependency_refuses_review_before_the_model():
    ws, requirement, _ = world_with(peers=())
    ws.depends_on_ids[requirement.id] = [requirement.id]
    result, model = review(ws, requirement)
    assert result.code is ReviewCode.DEPENDENCY_CYCLE, result
    assert not model.was_invoked


def test_a_cyclic_proposal_cannot_be_confirmed():
    ws, requirement, _ = world_with(peers=(D1,), proposals=((DEPENDS, D1),))
    bind_by_hand(ws, D1, ws.requirements[requirement.id])
    confirming, model = review(
        ws,
        requirement,
        relation_verifications=[verify_relation(requirement_id=D1.requirement_id)],
    )
    assert confirming.code is ReviewCode.INVALID_MODEL_OUTPUT, confirming
    assert "cannot be confirmed" in model.calls[0]["context"]
    rejecting, _ = review(
        ws,
        requirement,
        relation_verifications=[
            verify_relation(requirement_id=D1.requirement_id, outcome="REJECTED")
        ],
    )
    assert rejecting.code is ReviewCode.REQUIREMENT_REVIEWED, rejecting


def test_apply_refuses_a_cycle_that_appeared_after_approval():
    ws, requirement, _ = world_with(peers=(D1,), proposals=((DEPENDS, D1),))
    review(
        ws,
        requirement,
        relation_verifications=[verify_relation(requirement_id=D1.requirement_id)],
    )
    approved(ws, requirement)
    bind_by_hand(ws, D1, ws.requirements[requirement.id])
    before = len(ws.mutations)
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is Apply.DEPENDENCY_CYCLE, result
    assert ws.mutations[before:] == []


# -- invalid dependencies -----------------------------------------------------------


@pytest.mark.parametrize(
    "spoil, reason",
    [
        (
            lambda ws: ws.requirements.__setitem__(
                D1.id, replace(ws.requirements[D1.id], project_id="p-2")
            ),
            "another Project",
        ),
        (
            lambda ws: rewrite_peer_review(
                ws, D1, material_unresolved_what=(MaterialWhat("Open?"),)
            ),
            "WHAT CLEAR",
        ),
        (lambda ws: _downgrade_peer_review(ws, D1), "predates dependency evidence"),
        (lambda ws: edit_peer(ws, D1), "does not review its current"),
    ],
    ids=[
        "other-project",
        "blocked-on-what",
        "legacy-review",
        "stale-review",
    ],
)
def test_an_inadmissible_existing_dependency_refuses_review(spoil, reason):
    ws, requirement, _ = world_with(peers=(D1,), existing=(D1,))
    spoil(ws)
    result, model = review(ws, requirement, dependency_verifications=[dep(D1)])
    assert result.code is ReviewCode.DEPENDENCY_EVIDENCE_INVALID, result
    assert reason in result.message
    assert not model.was_invoked


def _downgrade_peer_review(ws, record):
    root = peer_root(ws, record)
    node = next(
        d
        for d in ws.documents
        if d.parent_document_id == root.id and "Review" in d.name
    )
    stored = parse_review_result(ws.content[node.secret])
    ws.content[node.secret] = render_review_result(replace(stored, version="0.5"))


def test_the_interpretation_set_is_bounded_not_truncated(monkeypatch):
    monkeypatch.setattr(dependency_evidence, "INTERPRETATION_SET_LIMIT", 1)
    ws, requirement, _ = world_with(peers=(D1, D2), existing=(D1, D2))
    result, model = review(ws, requirement, dependency_verifications=[dep(D1), dep(D2)])
    assert result.code is ReviewCode.DEPENDENCY_EVIDENCE_INVALID, result
    assert "refused, not cut" in result.message and not model.was_invoked


# -- legacy evidence ---------------------------------------------------------------


def test_legacy_evidence_without_bindings_is_not_dependency_verified():
    ws, requirement, _ = reviewed_with()
    node, stored = stored_review(ws)
    ws.content[node.secret] = render_review_result(
        replace(
            stored, version="0.5", dependency_verifications=(), dependency_bindings=()
        )
    )
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is Ready.DEPENDENCY_EVIDENCE_REQUIRED, refused
    ws.set_requirement_state(requirement.id, "Apply")
    assert apply_standard_requirement(ws, requirement.id).code is (
        Apply.DEPENDENCY_EVIDENCE_REQUIRED
    )
    ws.set_requirement_state(requirement.id, "Applied")
    error = clean_refusal(
        tsa_scene(ws), requirement_ids=(REQUIREMENT_ID, D1.requirement_id)
    )
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert "unknown, not absent" in " ".join([str(error), *error.details])


# -- peer-based WHAT clearance --------------------------------------------------------


def answered_by(target):
    return [
        {
            "question_index": 0,
            "outcome": "REJECTED",
            "basis": "ANSWERED_BY_OTHER_REQUIREMENT",
            "requirement_id": target.requirement_id,
            "reason": f"{target.requirement_id} defines it.",
        }
    ]


QUESTION = ({"detail": VALIDITY, "material": True},)


def test_a_verified_bound_dependency_answers_a_material_question():
    ws, requirement, _ = world_with(existing=(D1,), questions=QUESTION)
    review(
        ws,
        requirement,
        dependency_verifications=[dep(D1)],
        question_verifications=answered_by(D1),
    )
    _, stored = stored_review(ws)
    assert stored.what_status is WhatStatus.CLEAR
    assert approve_standard_requirement(ws, requirement.id).is_normal


@pytest.mark.parametrize(
    "how", ["affects", "unrelated", "transitive", "unconfirmed-proposal"]
)
def test_a_peer_that_is_not_a_verified_dependency_answers_nothing(how):
    peers = (D2, D1)
    if how == "affects":
        ws, requirement, _ = world_with(peers=peers, questions=QUESTION)
        ws.affects_ids[requirement.id] = [D1.id]
        response = {}
    elif how == "unrelated":
        ws, requirement, _ = world_with(peers=peers, questions=QUESTION)
        response = {}
    elif how == "transitive":
        ws, requirement, _ = world_with(
            peers=peers,
            existing=(D2,),
            evidence={D1: (), D2: (D1,)},
            questions=QUESTION,
        )
        response = {"dependency_verifications": [dep(D2)]}
    else:
        ws, requirement, _ = world_with(
            peers=peers, proposals=((DEPENDS, D1),), questions=QUESTION
        )
        response = {
            "relation_verifications": [
                verify_relation(requirement_id=D1.requirement_id, outcome="UNRESOLVED")
            ]
        }
    result, _ = review(
        ws, requirement, question_verifications=answered_by(D1), **response
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    _, stored = stored_review(ws)
    assert stored.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert (
        approve_standard_requirement(ws, requirement.id).code
        is Ready.MATERIAL_WHAT_UNRESOLVED
    )


def test_a_forged_peer_clearance_is_refused_on_read():
    ws, requirement, _ = world_with(existing=(D1,), questions=QUESTION)
    review(
        ws,
        requirement,
        dependency_verifications=[dep(D1)],
        question_verifications=answered_by(D1),
    )
    node, _ = stored_review(ws)
    rewrite_payload(ws, node, dependency_verifications=[], dependency_bindings=[])
    ws.depends_on_ids[requirement.id] = []
    with pytest.raises(InvalidReviewResult):
        parse_review_result(ws.content[node.secret])


def test_a_stale_answering_dependency_no_longer_clears():
    ws, requirement, _ = world_with(existing=(D1,), questions=QUESTION)
    review(
        ws,
        requirement,
        dependency_verifications=[dep(D1)],
        question_verifications=answered_by(D1),
    )
    edit_peer(ws, D1, "\nThe rule now says something else.\n")
    result = approve_standard_requirement(ws, requirement.id)
    assert result.code is Ready.DEPENDENCY_EVIDENCE_STALE, result


# -- TSA selection closure -------------------------------------------------------------


def applied_chain():
    """R -> D1 -> D2, every one Applied with current evidence."""
    ws, requirement, _ = world_with(
        peers=(D2, D1), existing=(D1,), evidence={D2: (), D1: (D2,)}
    )
    review(ws, requirement, dependency_verifications=[dep(D1)])
    approved(ws, requirement)
    assert (
        apply_standard_requirement(ws, requirement.id).code is Apply.REQUIREMENT_APPLIED
    )
    return ws


def test_tsa_admits_a_selection_closed_under_depends_on():
    scene = tsa_scene(applied_chain())
    result = start(
        scene, requirement_ids=(REQUIREMENT_ID, D1.requirement_id, D2.requirement_id)
    )
    assert result.is_newly_written


def test_tsa_refuses_a_selection_missing_a_transitive_dependency():
    scene = tsa_scene(applied_chain())
    error = clean_refusal(scene, requirement_ids=(REQUIREMENT_ID, D1.requirement_id))
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert f"{REQUIREMENT_ID} -> {D2.requirement_id}" in error.details
    assert f"{D1.requirement_id} -> {D2.requirement_id}" in error.details


def test_tsa_refuses_a_stale_dependency_with_nothing_written():
    ws = applied_chain()
    edit_peer(ws, D2)
    error = clean_refusal(
        tsa_scene(ws),
        requirement_ids=(REQUIREMENT_ID, D1.requirement_id, D2.requirement_id),
    )
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE


def test_tsa_never_requires_an_affects_peer():
    ws = applied_chain()
    ws.affects_ids[ws.requirements["std-uuid-1"].id] = [D3.id]
    result = start(
        tsa_scene(ws),
        requirement_ids=(REQUIREMENT_ID, D1.requirement_id, D2.requirement_id),
    )
    assert result.is_newly_written


# -- rework keeps dependency feedback ----------------------------------------------------


def test_a_rejected_existing_dependency_reaches_the_rework_with_its_identity():
    ws, requirement, _ = world_with(existing=(D1,))
    review(
        ws,
        requirement,
        dependency_verifications=[
            dep(D1, "REJECTED", "Not needed.", severity="WARNING")
        ],
    )
    _, stored = stored_review(ws)
    process = parse_process_result(
        ws.content[
            next(
                d
                for d in ws.documents
                if d.name == f"{REQUIREMENT_ID} — Process Result 0001"
            ).secret
        ]
    )
    [item] = build_rework_brief(stored, process).items
    assert item.category is BriefCategory.EXISTING_DEPENDENCY
    assert (item.kind, item.requirement_id) == ("DEPENDS_ON", D1.requirement_id)
    rework_standard_requirement(ws, requirement.id)
    model = FakeModelRuntime(
        [
            analysis_output(
                rework=[
                    {
                        "item": item.ref,
                        "outcome": "REBUTTED",
                        "explanation": "It is needed: it owns the rule.",
                    }
                ]
            )
        ]
    )
    result = process_standard_requirement(
        ws, model, requirement.id, authorized_new_cycle=True
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    feedback = model.calls[0]["context"].split("PREVIOUS REVIEW FEEDBACK")[1]
    assert (
        f"[{item.ref}] (EXISTING_DEPENDENCY, DEPENDS_ON, review outcome REJECTED"
        in feedback
    )
    assert f"about {D1.requirement_id}" in feedback


# -- the Uppercase Service example (offline; historical evidence) ---------------------


FR_0124 = peer(24, title="Uniform 400 error response for invalid uppercase requests")


def uppercase_world(with_dependency=True, conflicting=False):
    """FR-0123 (here the reviewed Requirement) and FR-0124 (here SDLC-FR-0024).

    FR-0124's normative text is the saved historical normalization; FR-0123
    refers to its query-validation rule instead of restating it.
    """
    fr_0124 = parse_process_result(FR_0124_EVIDENCE.read_text()).normalized
    rule = "the query-validation rule of SDLC-FR-0024"
    ws, requirement, _ = world_with(
        peers=(FR_0124,),
        existing=(FR_0124,) if with_dependency else (),
        evidence={FR_0124: ()},
        questions=QUESTION,
        normalized_changes={
            "title": "Uppercase a valid query on GET /v1/uppercase",
            "requirement": (
                f"Every request to GET /v1/uppercase that is valid under {rule} "
                'receives HTTP 200 and the JSON body {"text": <the value in upper case>}.'
                + (" A valid value has 1 to 64 characters." if conflicting else "")
            ),
        },
    )
    give_reviewed_evidence(
        ws,
        ws.requirements[FR_0124.id],
        content=NormalizedRequirement(**fr_0124.__dict__),
    )
    return ws, requirement


def test_uppercase_a_and_f_fr_0123_with_its_dependency_is_clear_and_admissible():
    ws, requirement = uppercase_world()
    result, model = review(
        ws,
        requirement,
        dependency_verifications=[
            dep(FR_0124, reason="FR-0124 owns the validity rule.")
        ],
        question_verifications=answered_by(FR_0124),
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED and result.verdict == "PASS"
    assert "1 to 32 ASCII letters" in model.calls[0]["context"], (
        "FR-0124 text is read with it"
    )
    _, stored = stored_review(ws)
    assert stored.what_status is WhatStatus.CLEAR
    approved(ws, requirement)
    assert (
        apply_standard_requirement(ws, requirement.id).code is Apply.REQUIREMENT_APPLIED
    )
    scene = tsa_scene(ws)
    assert start(
        scene, requirement_ids=(REQUIREMENT_ID, FR_0124.requirement_id)
    ).is_newly_written


def test_uppercase_b_and_g_without_depends_on_the_validity_question_stays_open():
    ws, requirement = uppercase_world(with_dependency=False)
    ws.affects_ids[requirement.id] = [FR_0124.id]  # the historical AFFECTS edge
    review(ws, requirement, question_verifications=answered_by(FR_0124))
    _, stored = stored_review(ws)
    assert stored.what_status is WhatStatus.BLOCKED_ON_WHAT


def test_uppercase_c_a_contradicting_rule_is_reported_by_the_review():
    ws, requirement = uppercase_world(conflicting=True)
    result, model = review(
        ws,
        requirement,
        dependency_verifications=[dep(FR_0124)],
        question_verifications=answered_by(FR_0124),
        new_findings=[
            {
                "kind": "POSSIBLE_CONFLICT",
                "severity": "BLOCKING",
                "requirement_id": FR_0124.requirement_id,
                "detail": "64 characters contradicts FR-0124's 1 to 32 letters.",
            }
        ],
    )
    assert "POSSIBLE_CONFLICT" in model.calls[0]["prompt"]
    assert result.verdict == "BLOCKING"


def test_uppercase_d_an_updated_fr_0124_makes_fr_0123_evidence_stale():
    ws, requirement = uppercase_world()
    review(
        ws,
        requirement,
        dependency_verifications=[dep(FR_0124)],
        question_verifications=answered_by(FR_0124),
    )
    edit_peer(ws, FR_0124, "\nValues may now hold digits.\n")
    assert (
        approve_standard_requirement(ws, requirement.id).code
        is Ready.DEPENDENCY_EVIDENCE_STALE
    )


def test_uppercase_e_selecting_only_fr_0123_is_refused():
    ws, requirement = uppercase_world()
    review(
        ws,
        requirement,
        dependency_verifications=[dep(FR_0124)],
        question_verifications=answered_by(FR_0124),
    )
    approved(ws, requirement)
    apply_standard_requirement(ws, requirement.id)
    error = clean_refusal(tsa_scene(ws), requirement_ids=(REQUIREMENT_ID,))
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert error.details == (f"{REQUIREMENT_ID} -> {FR_0124.requirement_id}",)


# -- guards found missing by mutation testing -----------------------------------


def test_a_dependency_whose_own_evidence_is_stale_is_not_authority():
    """D2 was re-reviewed after D1 bound it: D1 itself must be reviewed again."""
    ws, requirement, _ = world_with(
        peers=(D2, D1), existing=(D1,), evidence={D2: (), D1: (D2,)}
    )
    give_reviewed_evidence(ws, ws.requirements[D2.id], iteration=2)
    result, model = review(ws, requirement, dependency_verifications=[dep(D1)])
    assert result.code is ReviewCode.DEPENDENCY_EVIDENCE_INVALID, result
    assert "dependency evidence of SDLC-FR-0041 is stale" in result.message
    assert not model.was_invoked


def test_a_dependency_with_an_unbound_edge_is_not_authority():
    ws, requirement, _ = world_with(peers=(D2, D1), existing=(D1,))
    ws.depends_on_ids[D1.id] = [D2.id]  # added after D1 was reviewed
    result, model = review(ws, requirement, dependency_verifications=[dep(D1)])
    assert result.code is ReviewCode.DEPENDENCY_EVIDENCE_INVALID, result
    assert "disagree with the dependencies" in result.message
    assert not model.was_invoked


def test_a_confirmed_affects_proposal_answers_nothing():
    ws, requirement, _ = world_with(proposals=((AFFECTS, D1),), questions=QUESTION)
    review(
        ws,
        requirement,
        relation_verifications=[verify_relation("AFFECTS", D1.requirement_id)],
        question_verifications=answered_by(D1),
    )
    _, stored = stored_review(ws)
    assert stored.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert stored.dependency_bindings == ()


def test_a_pre_dependency_review_never_makes_a_new_review_redundant():
    ws, requirement, _ = reviewed_with()
    node, stored = stored_review(ws)
    ws.content[node.secret] = render_review_result(
        replace(
            stored, version="0.5", dependency_verifications=(), dependency_bindings=()
        )
    )
    ws.set_requirement_state(requirement.id, "Review")
    result, model = review(ws, requirement, dependency_verifications=[dep(D1)])
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    assert model.was_invoked and stored_review(ws)[1].version == "0.6"


def test_an_edge_written_concurrently_during_apply_stops_before_applied():
    ws, requirement, _ = world_with(peers=(D1, D2), proposals=((DEPENDS, D1),))
    review(
        ws,
        requirement,
        relation_verifications=[verify_relation(requirement_id=D1.requirement_id)],
    )
    approved(ws, requirement)
    original = ws.add_depends_on

    def and_someone_else_adds_one(entity_id, target):
        original(entity_id, target)
        ws.depends_on_ids[requirement.id].append(D2.id)

    ws.add_depends_on = and_someone_else_adds_one
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is Apply.PARTIAL_APPLY, result
    assert Apply.DEPENDENCY_EVIDENCE_STALE.value in result.details
    assert ws.requirements[requirement.id].state == "Apply"


# -- review findings: older evidence and duplicated proposals ---------------------


def test_an_older_review_keeps_the_what_rule_it_was_written_under():
    """A 0.5 result that stored BLOCKED for a confirmed DEPENDS_ON peer answer
    stays readable and BLOCKED: it never had dependency clearance."""
    ws, requirement, _ = world_with(proposals=((DEPENDS, D1),), questions=QUESTION)
    review(
        ws,
        requirement,
        relation_verifications=[verify_relation(requirement_id=D1.requirement_id)],
        question_verifications=answered_by(D1),
    )
    node, stored = stored_review(ws)
    assert stored.what_status is WhatStatus.CLEAR
    older = replace(
        stored,
        version="0.5",
        dependency_verifications=(),
        dependency_bindings=(),
        what_status=WhatStatus.BLOCKED_ON_WHAT,
    )
    ws.content[node.secret] = render_review_result(older)
    reread = parse_review_result(ws.content[node.secret])
    assert reread.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert reread.verified_dependencies == frozenset()
    assert approve_standard_requirement(ws, requirement.id).code is (
        Ready.MATERIAL_WHAT_UNRESOLVED
    )


def test_a_rejected_edge_cannot_be_cleared_again_as_a_proposal():
    ws, requirement, _ = world_with(
        existing=(D1,), proposals=((DEPENDS, D1),), questions=QUESTION
    )
    result, _ = review(
        ws,
        requirement,
        dependency_verifications=[
            dep(D1, "REJECTED", "Not needed.", severity="WARNING")
        ],
        relation_verifications=[verify_relation(requirement_id=D1.requirement_id)],
        question_verifications=answered_by(D1),
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    _, stored = stored_review(ws)
    assert stored.verified_dependencies == frozenset()
    assert stored.what_status is WhatStatus.BLOCKED_ON_WHAT
