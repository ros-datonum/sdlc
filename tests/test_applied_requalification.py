"""Bounded requalification of an Applied Requirement.

Requirement-Applied-Requalification-v0.1 adds one human transition,
`Standard Applied -> Process`, and reuses the existing chain after it:
Process -> Review -> Ready -> (human) Apply -> Applied. No production code
changes for it. These tests pin, on the in-memory fakes with fake models only,
that the existing entry points already hold the delta's invariants, and they
pin its stated limits: Revision is unchanged, Apply is additive for relations,
dependents need their own requalification, and an old TSA cycle goes stale.
"""

from __future__ import annotations

import functools
from dataclasses import replace

import pytest

from processor_fake import FakeModelRuntime, reserialize_like_fibery
from ready_fake import build_ready_workspace, process_result_nodes, review_result_nodes
from review_fake import (
    give_reviewed_evidence,
    relation_state,
    review_output,
    verify_resolution,
)
from sdlc import cli
from sdlc.autonomy_policy import DISABLED, load_autonomy_policies
from sdlc.dependency_evidence import (
    DependencyEvidenceError,
    DependencyFailure,
    Phase,
    require_current_dependencies,
)
from sdlc.ready_decision import (
    approve_standard_requirement,
    rework_standard_requirement,
)
from sdlc.ready_delegation import NOT_DELEGATED, load_ready_delegation
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.requirement_dispatcher import (
    DispatchOutcome,
    RouteDecision,
    Worker,
    select_route,
)
from sdlc.results import ApplyResultCode as ApplyCode
from sdlc.results import ReadyDecisionResultCode as ReadyCode
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.review_result import parse_review_result
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from sdlc.tsa_admission import (
    AdmissionRefused,
    AdmissionResultCode,
    start_input_manifest,
)
from standard_fake import REQUIREMENT_ID, analysis_output
from test_autonomous_resolution import admit
from test_autonomous_resolution import processed as attested_processed
from test_autonomous_resolution import review as attested_review
from test_autonomous_resolution import reviewed as attested_reviewed
from test_autonomous_resolution import scene as attestation_scene
from test_dependency_bindings import (
    approved,
    dep,
    edit_peer,
    peer,
    peer_root,
    review,
    tsa_scene,
    world_with,
)
from test_human_attestation import (
    ATTESTED,
    DECISION,
    QUESTION,
    human_decision_at_ready,
    human_edit,
    question_answer,
    second_process,
)
from test_requirement_dispatcher import NOT_PROCESSED, dispatch_current, real_workers
from test_tsa_admission import PROJECT_ID, clean_refusal, start, start_inputs
from test_tsa_lifecycle_e2e import (  # noqa: F401  (the fixture is used by name)
    INSPECT,
    MANIFEST_ID,
    RESUME,
    assert_result,
    decision_argv,
    json_of,
    lifecycle,
    start_argv,
    started,
)
from test_worker_policy_lifetime import REPOSITORY_CONFIG

APPLIED = "Applied"
PROCESS = "Process"
REVIEW = "Review"
READY = "Ready"
APPLY = "Apply"
CLARIFIED = "The operator clarified the boundary after Apply."
CLARIFICATION = f"\n{CLARIFIED}\n"
SECOND_CYCLE = "arch-2026-10-b"


def applied(**ready):
    """A Requirement carried to Applied by the real chain and a human approval."""
    ws, record, root, _ = build_ready_workspace(**ready)
    ws.set_requirement_state(record.id, APPLY)  # the human Ready -> Apply
    result = dispatch_current(ws, real_workers(ws), record.id)
    assert result.worker_result.code is ApplyCode.REQUIREMENT_APPLIED, result
    return ws, ws.requirements[record.id], root


def requalify(ws, record, edit=None):
    """The one new human transition, and an optional human Root edit after it."""
    ws.set_requirement_state(record.id, PROCESS)
    if edit is not None:
        root = next(d for d in ws.documents if d.entity_public_id == record.public_id)
        ws.content[root.secret] += edit


def history(ws):
    nodes = [*process_result_nodes(ws), *review_result_nodes(ws)]
    return {node.secret: ws.content[node.secret] for node in nodes}


def identity(ws, record):
    """Everything requalification must keep, the Root Document included."""
    root = next(d for d in ws.documents if d.entity_public_id == record.public_id)
    return (
        record.id,
        record.public_id,
        record.requirement_id,
        record.type_name,
        record.project_id,
        root.id,
    )


def latest_review(ws, record=None):
    """The highest-iteration Review Result under a Requirement's Root."""
    if record is None:
        node = review_result_nodes(ws)[-1]
    else:
        root = peer_root(ws, record)
        node = [
            d
            for d in ws.documents
            if d.parent_document_id == root.id and "Review Result" in d.name
        ][-1]
    return parse_review_result(reserialize_like_fibery(ws.content[node.secret]))


def recording(workers, calls):
    """The real workers, with the options the dispatcher passed to Process."""

    def process_standard(entity_id, **options):
        calls.append(options)
        return workers.process_standard(entity_id, **options)

    return replace(workers, process_standard=process_standard)


def processed(ws, record, edit=None, output=None):
    requalify(ws, record, edit)
    model = FakeModelRuntime([output or analysis_output()])
    result = dispatch_current(ws, real_workers(ws, process_model=model), record.id)
    assert result.worker_result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    return result


def reviewed(ws, record, **response):
    model = FakeModelRuntime([review_output(**response)])
    result = dispatch_current(ws, real_workers(ws, review_model=model), record.id)
    assert result.worker_result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    return result, model


def reapplied(ws, record):
    ws.set_requirement_state(record.id, APPLY)  # the fresh human approval
    result = dispatch_current(ws, real_workers(ws), record.id)
    assert result.worker_result.code is ApplyCode.REQUIREMENT_APPLIED, result
    return result


# -- A-D, I: the human re-entry runs the next iteration as an authorized cycle ----


@pytest.mark.parametrize("edit", [None, CLARIFICATION], ids=["unedited", "edited"])
def test_a_human_applied_to_process_runs_the_next_iteration(edit):
    ws, record, _ = applied()
    assert select_route(record, NOT_PROCESSED).decision is RouteDecision.NO_MACHINE_WORK
    before, who = history(ws), identity(ws, record)

    requalify(ws, record, edit)
    route = select_route(ws.requirements[record.id], NOT_PROCESSED)
    calls = []
    model = FakeModelRuntime([analysis_output()])
    workers = recording(real_workers(ws, process_model=model), calls)
    result = dispatch_current(ws, workers, record.id)

    assert route.decision is RouteDecision.ROUTE_SELECTED
    assert route.route.worker is Worker.STANDARD_PROCESS
    assert calls == [{"authorized_new_cycle": True}]
    assert result.outcome is DispatchOutcome.ROUTE_COMPLETED, result
    assert result.worker_result.iteration == 2
    assert len(model.calls) == 1
    assert ws.requirements[record.id].state == REVIEW
    assert len(process_result_nodes(ws)) == 2
    assert {secret: history(ws)[secret] for secret in before} == before
    assert identity(ws, ws.requirements[record.id]) == who


def test_an_unedited_requalification_needs_the_dispatcher_route():
    """The manual command is not an authorized new cycle: it reports no changes."""
    ws, record, _ = applied()
    requalify(ws, record)
    mutations = len(ws.mutations)
    model = FakeModelRuntime([analysis_output()])

    result = process_standard_requirement(ws, model, record.id)

    assert result.code is ProcessCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked
    assert ws.mutations[mutations:] == []
    assert ws.requirements[record.id].state == PROCESS


# -- E, F, H: independent Review of the current input, then a human boundary -----


def test_review_judges_the_new_iteration_and_stops_at_ready():
    ws, record, _ = applied()
    first = latest_review(ws)
    kept = analysis_output(normalized_changes={"constraints_edge_cases": CLARIFIED})
    processed(ws, record, edit=CLARIFICATION, output=kept)

    result, model = reviewed(ws, record)

    stored = latest_review(ws)
    assert result.state_after == READY == ws.requirements[record.id].state
    assert stored.iteration == first.iteration + 1
    assert stored.reviewed_process_iteration == 2
    assert CLARIFIED in model.calls[0]["context"]  # the current Root, as processed
    assert len(review_result_nodes(ws)) == 2
    ready = select_route(ws.requirements[record.id], NOT_PROCESSED)
    assert ready.decision is RouteDecision.HUMAN_BOUNDARY
    mutations = len(ws.mutations)
    refused = apply_standard_requirement(ws, record.id)
    assert refused.code is ApplyCode.REQUIREMENT_NOT_IN_APPLY
    assert ws.mutations[mutations:] == []
    assert ws.requirements[record.id].state == READY


# -- G, I, J: a fresh human approval re-Applies; identity and Revision unchanged ----


def test_a_fresh_human_approval_re_applies_with_revision_unchanged():
    ws, record, _ = applied()
    who, revision = identity(ws, record), record.revision
    processed(ws, record, edit=CLARIFICATION)
    reviewed(ws, record)

    reapplied(ws, record)

    stored = ws.requirements[record.id]
    assert stored.state == APPLIED
    assert identity(ws, stored) == who
    # The fake writes no Revision; the guarantee is each stage's read-back.
    assert stored.revision == revision == 1


# -- K, L: Apply is additive; the existing graph must stay valid ------------------


def test_existing_edges_are_reverified_and_kept():
    ws, record, _ = applied(with_relation=True)
    target = ws.depends_on_ids[record.id][0]
    graph = relation_state(ws)
    processed(ws, record)
    target = ws.requirements[target]

    missing = review_standard_requirement(
        ws, FakeModelRuntime([review_output()]), record.id
    )
    assert missing.code is ReviewCode.INVALID_MODEL_OUTPUT, missing
    reviewed(ws, record, dependency_verifications=[dep(target)])
    reapplied(ws, record)

    assert relation_state(ws) == graph
    [verification] = latest_review(ws).dependency_verifications
    assert verification.requirement_id == target.requirement_id


def test_a_rejected_existing_edge_is_never_removed_by_apply():
    """Out of scope: no relation removal exists. The recovery gate must stop at
    Ready; a human who approves anyway gets an Applied Requirement whose edge
    its own latest Review rejected."""
    ws, record, _ = applied(with_relation=True)
    target = ws.depends_on_ids[record.id][0]
    graph = relation_state(ws)
    processed(ws, record)
    rejected = dep(
        ws.requirements[target],
        outcome="REJECTED",
        severity="BLOCKING",
        reason="The definition is no longer owned there.",
    )
    reviewed(ws, record, dependency_verifications=[rejected])

    reapplied(ws, record)

    assert relation_state(ws) == graph
    assert latest_review(ws).dependency_verifications[0].outcome.value == "REJECTED"


# -- M, N: the ARP1 DEPENDS_ON chain FR-0129 <- FR-0130 <- CON-0133 ---------------

FR_0129 = peer(129)
FR_0130 = peer(130)
NFR_0131 = peer(131)
SELECTION = (REQUIREMENT_ID, FR_0129.requirement_id, FR_0130.requirement_id)


def arp1_chain():
    """R (as CON-0133) DEPENDS_ON FR-0130 and FR-0129; FR-0130 on FR-0129."""
    ws, requirement, _ = world_with(
        peers=(FR_0129, FR_0130, NFR_0131),
        existing=(FR_0130, FR_0129),
        evidence={FR_0129: (), FR_0130: (FR_0129,), NFR_0131: ()},
    )
    review(ws, requirement, dependency_verifications=[dep(FR_0129), dep(FR_0130)])
    approved(ws, requirement)
    assert (
        apply_standard_requirement(ws, requirement.id).code
        is ApplyCode.REQUIREMENT_APPLIED
    )
    return ws, ws.requirements[requirement.id]


def requalified_peer(ws, record, depends_on=(), edit=None):
    """A peer's completed requalification: new Root, new evidence, Applied."""
    if edit is not None:
        edit_peer(ws, record, edit)
    give_reviewed_evidence(
        ws,
        ws.requirements[record.id],
        iteration=2,
        keep_content=True,
        depends_on=depends_on,
    )


def stale(ws, record, review_result):
    with pytest.raises(DependencyEvidenceError) as caught:
        require_current_dependencies(ws, record, review_result, Phase.APPLIED)
    return caught.value


def test_a_requalified_fr_0129_makes_fr_0130_and_con_0133_stale():
    ws, requirement = arp1_chain()
    assert start(tsa_scene(ws), requirement_ids=SELECTION).is_newly_written

    ws, requirement = arp1_chain()
    fr_0130_review = latest_review(ws, FR_0130)
    con_0133_review = latest_review(ws)
    requalified_peer(ws, FR_0129, edit=CLARIFICATION)

    assert stale(ws, ws.requirements[FR_0130.id], fr_0130_review).failure is (
        DependencyFailure.STALE
    )
    assert stale(ws, requirement, con_0133_review).failure is DependencyFailure.STALE
    error = clean_refusal(tsa_scene(ws), requirement_ids=SELECTION)
    assert error.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE


def test_dependents_requalify_in_order_and_restore_current_bindings():
    ws, requirement = arp1_chain()
    requalified_peer(ws, FR_0129, edit=CLARIFICATION)

    # No Review-only shortcut: the dependent's own tree is unchanged.
    ws.set_requirement_state(requirement.id, REVIEW)
    shortcut = FakeModelRuntime([review_output()])
    result = review_standard_requirement(ws, shortcut, requirement.id)
    assert result.code is ReviewCode.NO_CHANGES_TO_REVIEW
    assert not shortcut.was_invoked

    # Out of order: FR-0130 is still stale, so CON-0133's Review refuses.
    processed(ws, requirement)
    early = FakeModelRuntime([review_output()])
    result = review_standard_requirement(ws, early, requirement.id)
    assert result.code is ReviewCode.DEPENDENCY_EVIDENCE_INVALID, result
    assert not early.was_invoked
    assert ws.requirements[requirement.id].state == REVIEW

    # In order: FR-0130 requalified first, then CON-0133 is reviewed and Applied.
    requalified_peer(ws, FR_0130, depends_on=(ws.requirements[FR_0129.id],))
    reviewed(ws, requirement, dependency_verifications=[dep(FR_0129), dep(FR_0130)])
    reapplied(ws, requirement)

    bindings = {b.requirement_id: b for b in latest_review(ws).dependency_bindings}
    assert bindings[FR_0129.requirement_id].review_iteration == 2
    assert bindings[FR_0130.requirement_id].review_iteration == 2
    require_current_dependencies(
        ws, ws.requirements[requirement.id], latest_review(ws), Phase.APPLIED
    )
    assert start(tsa_scene(ws), requirement_ids=SELECTION).is_newly_written


# -- O: an AFFECTS peer is not invalidated by a requalification -------------------


def test_an_affects_peer_is_not_invalidated_by_requalification():
    ws, requirement = arp1_chain()
    ws.affects_ids[requirement.id] = [NFR_0131.id]
    ws.affects_ids[NFR_0131.id] = [requirement.id]
    con_0133_review = latest_review(ws)

    requalified_peer(ws, NFR_0131, edit=CLARIFICATION)

    require_current_dependencies(ws, requirement, con_0133_review, Phase.APPLIED)
    selection = (*SELECTION, NFR_0131.requirement_id)
    assert start(tsa_scene(ws), requirement_ids=selection).is_newly_written


# -- P, Q: the old TSA cycle goes stale; a new cycle reselects the identity -------


def tsa_requirement(scene):
    return next(
        r for r in scene.req.requirements.values() if r.requirement_id == REQUIREMENT_ID
    )


def assert_cycle_stale(cycle):
    for argv in (decision_argv("approve"), decision_argv("rework"), RESUME):
        assert_result(cycle(*argv), "INPUTS_STALE", 1)
    assert json_of(cycle(*INSPECT, "--json"))["code"] == "INSPECT_STALE"


def test_leaving_applied_alone_makes_the_bound_cycle_stale(lifecycle):  # noqa: F811
    cycle = lifecycle()
    started(cycle)
    record = tsa_requirement(cycle.scene)
    mark = cycle.mark()

    requalify(cycle.scene.req, record)  # State only: the tree is unchanged

    assert_cycle_stale(cycle)
    assert cycle.mutations_since(mark) == []
    assert cycle.models.counts == (1, 1)


def test_requalification_makes_the_bound_cycle_stale_and_a_new_cycle_admits_it(
    lifecycle,  # noqa: F811
):
    cycle = lifecycle()
    scene = cycle.scene
    started(cycle)
    record = tsa_requirement(scene)
    manifest = scene.tsa.content_of(MANIFEST_ID)
    artifacts = {d: scene.tsa.content_of(d) for d in scene.tsa.documents}
    mark = cycle.mark()

    requalify(scene.req, record, CLARIFICATION)  # left Applied, tree changed
    assert_cycle_stale(cycle)
    model = FakeModelRuntime([analysis_output()])
    dispatch_current(scene.req, real_workers(scene.req, process_model=model), record.id)
    assert_cycle_stale(cycle)  # a new Process Result
    reviewer = FakeModelRuntime([review_output()])
    dispatch_current(
        scene.req, real_workers(scene.req, review_model=reviewer), record.id
    )
    assert_cycle_stale(cycle)  # a new Review Result
    reapplied(scene.req, record)
    assert_cycle_stale(cycle)  # Applied again, on other evidence

    assert cycle.mutations_since(mark) == []
    assert cycle.models.counts == (1, 1)
    assert {d: scene.tsa.content_of(d) for d in artifacts} == artifacts
    second = start_input_manifest(
        scene.tsa, scene.req, PROJECT_ID, SECOND_CYCLE, start_inputs()
    )
    assert second.is_newly_written
    assert scene.tsa.content_of(MANIFEST_ID) == manifest
    assert_result(cycle(*start_argv()), "INPUTS_STALE", 1)  # never re-accepted
    assert scene.tsa.content_of(MANIFEST_ID) == manifest


# -- S: requalification touches only the requalified Requirement ------------------


def test_requalification_writes_only_the_requalified_requirement():
    ws, record, _ = applied(with_relation=True)
    target = ws.requirements[ws.depends_on_ids[record.id][0]]
    others = {k: v for k, v in ws.requirements.items() if k != record.id}
    graph = relation_state(ws)
    mark = len(ws.mutations)

    processed(ws, record, edit=CLARIFICATION)
    reviewed(ws, record, dependency_verifications=[dep(target)])
    reapplied(ws, record)

    own = {d.secret for d in ws.documents if d.name.startswith(REQUIREMENT_ID)}
    for mutation in ws.mutations[mark:]:
        verb, _, subject = mutation.partition(" ")
        if verb == "write_content":
            assert subject in own, mutation
        elif verb == "create_child_document":
            assert subject.startswith(REQUIREMENT_ID), mutation
        else:
            assert subject.split(" ")[0] == record.id, mutation
    assert {k: v for k, v in ws.requirements.items() if k != record.id} == others
    assert relation_state(ws) == graph


# -- T: no autonomous Ready decision in the repository ----------------------------


def test_the_repository_delegates_no_ready_decision_for_requalification():
    ws, record, _ = applied()
    processed(ws, record, edit=CLARIFICATION)
    reviewed(ws, record)

    assert load_ready_delegation(REPOSITORY_CONFIG) == NOT_DELEGATED
    assert (
        cli._ready_decider(
            lambda: load_ready_delegation(REPOSITORY_CONFIG),
            lambda: load_autonomy_policies(REPOSITORY_CONFIG),
        )
        is None
    )
    route = select_route(ws.requirements[record.id], NOT_PROCESSED)
    assert route.decision is RouteDecision.HUMAN_BOUNDARY
    assert ws.requirements[record.id].state == READY


# -- R: attestation currentness is unchanged by requalification -------------------


def attested_scene():
    """An Applied Requirement whose RAW and Root follow the attestation tests."""
    ws, requirement, root = attestation_scene()
    attested_processed(ws, requirement, analysis_output())
    attested_reviewed(ws, requirement)
    ws.set_requirement_state(requirement.id, APPLY)
    assert apply_standard_requirement(ws, requirement.id).is_normal
    return ws, ws.requirements[requirement.id], root


def material_item(iteration):
    return f"R{iteration:04d}.Q0"


def test_an_attested_answer_inside_a_requalification_needs_a_current_attestation():
    """TSA raised a material question; requalification carries it to a human
    answer, and only a current attestation lets that answer stand."""
    ws, requirement, root = attested_scene()
    requalify(ws, requirement)
    question = analysis_output(questions=[{"detail": QUESTION, "material": True}])
    model = FakeModelRuntime([question])
    workers = replace(
        real_workers(ws),
        process_standard=functools.partial(process_standard_requirement, ws, model),
    )
    assert dispatch_current(ws, workers, requirement.id).worker_result.is_normal
    attested_reviewed(
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
    assert rework_standard_requirement(ws, requirement.id).is_normal  # human
    human_edit(ws, root)
    item = material_item(2)
    result, _ = second_process(ws, requirement, rework=[question_answer(item)])
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result

    confirm = {
        "rework_verifications": [
            {"item": item, "outcome": "CONFIRMED", "reason": "Now settled."}
        ],
        "resolution_verifications": [verify_resolution()],
    }
    refused, model = attested_review(ws, requirement, policies=DISABLED, **confirm)
    assert refused.code is ReviewCode.RESOLUTION_EVIDENCE_STALE, refused
    assert not model.was_invoked
    attested_reviewed(ws, requirement, policies=ATTESTED, **confirm)
    ready = approve_standard_requirement(ws, requirement.id, policies=DISABLED)
    assert ready.code is ReadyCode.RESOLUTION_EVIDENCE_STALE, ready
    ws.set_requirement_state(requirement.id, APPLY)  # the fresh human approval
    stale_apply = apply_standard_requirement(ws, requirement.id, policies=DISABLED)
    assert stale_apply.code is ApplyCode.RESOLUTION_EVIDENCE_STALE, stale_apply
    applied_result = apply_standard_requirement(ws, requirement.id, policies=ATTESTED)
    assert applied_result.code is ApplyCode.REQUIREMENT_APPLIED, applied_result
    with pytest.raises(AdmissionRefused) as caught:
        admit(ws, DISABLED)
    assert caught.value.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert admit(ws, ATTESTED).is_newly_written


def test_reliance_is_recomputed_from_the_requalified_evidence():
    """A documented limit, not a guarantee: evidence that no longer cites the
    attested text no longer depends on it, so revoking it then refuses
    nothing. Keeping the attestation is the operator's obligation."""
    ws, requirement, _, _ = human_decision_at_ready()
    ws.set_requirement_state(requirement.id, APPLY)
    assert apply_standard_requirement(ws, requirement.id, policies=ATTESTED).is_normal
    with pytest.raises(AdmissionRefused) as caught:
        admit(ws, DISABLED)  # current evidence relies on the attestation
    assert caught.value.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE

    requalify(ws, ws.requirements[requirement.id])
    # The attested text stays in its section verbatim (Attested-Text-
    # Preservation-v0.1); the new evidence simply no longer cites it.
    model = FakeModelRuntime(
        [analysis_output(normalized_changes={"constraints_edge_cases": DECISION})]
    )
    workers = replace(
        real_workers(ws),
        process_standard=functools.partial(
            process_standard_requirement, ws, model, policies=ATTESTED
        ),
    )
    assert dispatch_current(ws, workers, requirement.id).worker_result.is_normal
    assert "OPERATOR-ATTESTED CLARIFICATIONS" in model.calls[0]["prompt"]
    attested_reviewed(ws, requirement, policies=ATTESTED)
    reapplied(ws, requirement)

    assert admit(ws, DISABLED).is_newly_written
