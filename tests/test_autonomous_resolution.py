"""WI-5 — autonomous resolution (Requirement-Autonomous-Resolution-v0.1).

Every scenario drives the production stages — Process, Review, Ready approve,
Apply and TSA admission — over the fake Fibery and fake model runtimes. The
delegated-decision policies here are TEST-ONLY fixtures: no policy is
approved in the repository configuration, which ships default deny.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from processor_fake import FakeModelRuntime, reserialize_like_fibery
from review_fake import (
    downgrade_latest_process,
    give_reviewed_evidence,
    payload_of,
    review_output,
    rewrite_payload,
    tree_manifest,
    verify_resolution,
)
from sdlc import cli
from sdlc.autonomy_policy import (
    DISABLED,
    HUMAN_ONLY_DOMAINS,
    AutonomyPolicies,
    AutonomyPolicy,
    AutonomyPolicyError,
    PolicyClause,
    load_autonomy_policies,
    parse_autonomy_policies,
    policy_fingerprint,
)
from sdlc.fibery_workspace import FiberyError, RequirementRecord
from sdlc.process_result import (
    InvalidProcessResult,
    build_process_result,
    parse_process_result,
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
from sdlc.review_result import (
    InvalidReviewResult,
    build_rework_brief,
    open_material_questions,
    parse_review_result,
    render_review_result,
    what_clearance,
)
from sdlc.rework_brief import BriefCategory, run_input_identity
from sdlc.standard_analysis import (
    InvalidAnalysisOutput,
    ResolutionClass,
    SourceKind,
    parse_analysis_output,
)
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_review import (
    RESOLUTION_CHECKS,
    InvalidReviewOutput,
    ReviewVerdict,
    VerificationOutcome,
    WhatStatus,
    parse_review_output,
)
from sdlc.standard_reviewer import review_standard_requirement
from sdlc.tsa_admission import (
    AdmissionRefused,
    AdmissionResultCode,
    PolicyBoundEvidence,
    start_input_manifest,
)
from standard_fake import (
    RAW_ID,
    REQUIREMENT_ID,
    analysis_output,
    build_standard_workspace,
    citation,
    resolution,
)
from test_tsa_admission import CYCLE, PROJECT_ID, fixed_clock, start_inputs, world
from test_tsa_cli import ENVIRONMENT

# The originating RAW: it settles the request-size question verbatim.
SOURCE = (
    "# Uppercase Service\n\n"
    "Requests longer than 1000 characters are rejected with status 413.\n"
)
LIMIT_QUOTE = "Requests longer than 1000 characters are rejected with status 413."
LIMIT_QUESTION = "What happens to a request longer than the size limit?"
DRAFT_QUOTE = "A draft statement."
PEER_QUOTE = "must refuse to execute a model without login"

ERROR_BODY = PolicyClause(
    clause_id="ERR-BODY",
    applies_when="The source names an error response but not its body wording.",
    permitted_decision="The error body carries one human-readable message field.",
    boundaries="Wording only: never status codes or which requests fail.",
    exclusions=("status codes",),
    evidence_required="Cite the text that names the error response.",
)


def approved(*clauses, code="SDLC", policy_id="SDLC-DEFAULTS-1"):
    """A TEST-ONLY approved policy; never configuration."""
    return AutonomyPolicies(
        (AutonomyPolicy(code, policy_id, "Test approver", clauses or (ERROR_BODY,)),)
    )


POLICIES = approved()
CHANGED = approved(replace(ERROR_BODY, boundaries="Wording and status codes."))


def peer(number, state="Applied"):
    return RequirementRecord(
        id=f"std-peer-{number}",
        public_id=str(number),
        requirement_id=f"SDLC-FR-{number:04d}",
        title=f"Peer {number}",
        type_name="Standard",
        state=state,
        revision=1,
        project_id="p-1",
        source_fingerprint=None,
    )


D1 = peer(41)


def scene(peers=(), depends_on=(), affects=()):
    """One Standard Requirement in Process, its RAW holding SOURCE.

    `peers` get reviewed, WHAT-CLEAR evidence; `depends_on` and `affects` are
    the Requirement's existing edges.
    """
    ws, requirement, root = build_standard_workspace(others=tuple(peers))
    ws.content["raw-secret"] = SOURCE
    for record in peers:
        give_reviewed_evidence(ws, record)
    if depends_on:
        ws.depends_on_ids[requirement.id] = [record.id for record in depends_on]
    if affects:
        ws.affects_ids[requirement.id] = [record.id for record in affects]
    return ws, requirement, root


def limit_resolution(**changes):
    fields = {
        "issue": LIMIT_QUESTION,
        "answer": "Requests longer than 1000 characters are rejected with status 413.",
        "sources": [citation(quote=LIMIT_QUOTE)],
        "justification": "The RAW states the limit and its outcome verbatim.",
    }
    return resolution(**{**fields, **changes})


def peer_resolution(target=D1, quote=PEER_QUOTE):
    return resolution(
        "DEPENDENCY_GROUNDED",
        issue="Which login rule applies?",
        answer=f"The login rule {target.requirement_id} owns applies.",
        sources=[citation("DEPENDENCY", quote, target.requirement_id)],
        justification=f"{target.requirement_id} owns the login rule.",
    )


def delegated_resolution(clause="ERR-BODY", **changes):
    fields = {
        "resolution_class": "DELEGATED_DEFAULT",
        "issue": "What does the error body say?",
        "answer": "The error body carries one human-readable message field.",
        "sources": [citation("REQUIREMENT", DRAFT_QUOTE)],
        "clause": clause,
        "justification": "Clause ERR-BODY permits exactly this wording default.",
    }
    return resolution(**{**fields, **changes})


def process(ws, requirement, *outputs, policies=DISABLED, **options):
    model = FakeModelRuntime(list(outputs))
    result = process_standard_requirement(
        ws, model, requirement.id, policies=policies, **options
    )
    return result, model


def review(ws, requirement, policies=DISABLED, **response):
    model = FakeModelRuntime([review_output(**response)])
    result = review_standard_requirement(ws, model, requirement.id, policies=policies)
    return result, model


def artifacts(ws, kind):
    return [d for d in ws.documents if d.name.startswith(f"{REQUIREMENT_ID} — {kind}")]


def latest(ws, kind, parser):
    node = artifacts(ws, kind)[-1]
    return node, parser(reserialize_like_fibery(ws.content[node.secret]))


def latest_process(ws):
    return latest(ws, "Process Result", parse_process_result)


def latest_review(ws):
    return latest(ws, "Review Result", parse_review_result)


def processed(ws, requirement, output, policies=DISABLED):
    result, model = process(ws, requirement, output, policies=policies)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    return model


def reviewed(ws, requirement, policies=DISABLED, **response):
    result, model = review(ws, requirement, policies=policies, **response)
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    return model


def source_grounded_at_ready(**response):
    """Case A through Review: one RAW-grounded resolution, reviewed."""
    ws, requirement, root = scene()
    processed(ws, requirement, analysis_output(resolutions=[limit_resolution()]))
    response.setdefault("resolution_verifications", [verify_resolution()])
    reviewed(ws, requirement, **response)
    return ws, requirement, root


def delegated_at_ready(policies=POLICIES, **response):
    """Case C through Review: one delegated default, reviewed under POLICIES."""
    ws, requirement, root = scene()
    processed(
        ws,
        requirement,
        analysis_output(resolutions=[delegated_resolution()]),
        policies=policies,
    )
    response.setdefault("resolution_verifications", [verify_resolution(delegated=True)])
    reviewed(ws, requirement, policies=policies, **response)
    return ws, requirement, root


def apply_by_hand(ws, requirement):
    ws.set_requirement_state(requirement.id, "Apply")


def admit(ws, policies):
    """TSA admission of the Requirement, with the invocation's policies."""
    tsa = world()
    return start_input_manifest(
        tsa.tsa,
        PolicyBoundEvidence(ws, policies),
        PROJECT_ID,
        CYCLE,
        start_inputs(),
        clock=fixed_clock,
    )


# -- the policy: authority, default deny, fingerprint -------------------------------


def configured(clauses=None, **policy):
    """An `[autonomy]` table approving `clauses`, fingerprinted as approved."""
    clauses = clauses if clauses is not None else [ERROR_BODY.to_payload()]
    body = {
        "policy_id": "SDLC-DEFAULTS-1",
        "approved_by": "Test approver",
        "clauses": clauses,
        **policy,
    }
    if "approved_fingerprint" not in body:
        body["approved_fingerprint"] = policy_fingerprint(
            "SDLC",
            body["policy_id"],
            tuple(
                PolicyClause(**{**c, "exclusions": tuple(c["exclusions"])})
                for c in clauses
            ),
        )
    return {"mode": "enabled", "projects": {"SDLC": body}}


def test_the_repository_ships_default_deny():
    root = Path(__file__).parent.parent
    assert load_autonomy_policies(root / "config" / "sdlc.toml") == DISABLED
    assert parse_autonomy_policies(None) == DISABLED
    assert parse_autonomy_policies({"mode": "disabled"}) == DISABLED
    assert DISABLED.for_project("SDLC") is None


def test_an_approved_policy_loads_exactly_as_approved():
    policies = parse_autonomy_policies(configured())
    policy = policies.for_project("SDLC")
    assert policy.clauses == (ERROR_BODY,) and policy.approved_by == "Test approver"
    assert policies.current(policy.binding) is policy
    assert policies.for_project("OTHER") is None


@pytest.mark.parametrize(
    "section, message",
    [
        ({"mode": "on"}, "must be 'disabled' or 'enabled'"),
        ({}, "must be 'disabled' or 'enabled'"),
        (
            {"mode": "disabled", "projects": {"SDLC": {}}},
            "delegates nothing",
        ),
        ({"mode": "enabled"}, "approves no project policy"),
        ({"mode": "disabled", "override": True}, "does not define"),
    ],
)
def test_a_malformed_autonomy_section_is_refused(section, message):
    with pytest.raises(AutonomyPolicyError, match=message):
        parse_autonomy_policies(section)


def test_edited_policy_content_is_not_the_approved_policy():
    section = configured()
    clause = section["projects"]["SDLC"]["clauses"][0]
    clause["permitted_decision"] = "Any reasonable error body."
    with pytest.raises(AutonomyPolicyError, match="not the content that was approved"):
        parse_autonomy_policies(section)


@pytest.mark.parametrize(
    "change, message",
    [
        ({"approved_fingerprint": "abc"}, "64 lowercase hex"),
        ({"clauses": []}, "at least one clause"),
        ({"policy_id": "has space"}, "identifier"),
        ({"approved_by": " "}, "non-empty text"),
        ({"scope": "everything"}, "does not define"),
    ],
)
def test_a_malformed_policy_is_refused(change, message):
    with pytest.raises(AutonomyPolicyError, match=message):
        parse_autonomy_policies(configured(**change))


def test_a_clause_has_no_key_that_could_lift_the_human_only_domains():
    clause = {**ERROR_BODY.to_payload(), "allows_human_only_domains": True}
    with pytest.raises(AutonomyPolicyError, match="does not define"):
        parse_autonomy_policies(
            configured(clauses=[clause], approved_fingerprint="0" * 64)
        )


def test_a_policy_change_removes_the_bound_authority():
    bound = POLICIES.for_project("SDLC").binding
    assert CHANGED.current(bound) is None
    assert DISABLED.current(bound) is None


# -- the Process contract ------------------------------------------------------------


@pytest.mark.parametrize(
    "question, message",
    [
        ({"detail": "x", "material": True}, "missing: authority"),
        (
            {"detail": "x", "material": True, "authority": "TECHNICAL_HOW"},
            "technical HOW is not a product question",
        ),
        (
            {"detail": "x", "material": True, "authority": "SOURCE_GROUNDED"},
            "belongs in resolutions",
        ),
        (
            {
                "detail": "x",
                "material": True,
                "authority": "INSUFFICIENT_EVIDENCE",
                "alternatives": ["only one"],
            },
            "at least 2 alternatives",
        ),
    ],
)
def test_an_open_question_must_say_why_it_stays_open(question, message):
    body = json.loads(analysis_output())
    body["product_questions"] = [question]
    with pytest.raises(InvalidAnalysisOutput, match=message):
        parse_analysis_output(json.dumps(body))


@pytest.mark.parametrize(
    "entry, message",
    [
        (limit_resolution(resolution_class="HUMAN_REQUIRED"), "not a resolution"),
        (limit_resolution(sources=[]), "cites no source"),
        (
            limit_resolution(sources=[citation(quote="too short")]),
            "shorter than 12",
        ),
        (limit_resolution(sections=["open_questions"]), "affected_sections"),
        (limit_resolution(sections=["requirement", "requirement"]), "each once"),
        (
            limit_resolution(
                sources=[citation("DEPENDENCY", LIMIT_QUOTE, D1.requirement_id)]
            ),
            "SOURCE_GROUNDED and may cite only",
        ),
        (
            resolution("DEPENDENCY_GROUNDED", sources=[citation(quote=LIMIT_QUOTE)]),
            "cites no dependency",
        ),
        (limit_resolution(clause="ERR-BODY"), "policy_clause"),
        (delegated_resolution(clause=None), "policy_clause"),
        (
            limit_resolution(
                sources=[
                    {
                        "kind": "REQUIREMENT",
                        "quote": DRAFT_QUOTE,
                        "requirement_id": RAW_ID,
                    }
                ]
            ),
            "must not name one",
        ),
        ({**limit_resolution(), "confidence": "high"}, "does not define"),
    ],
)
def test_a_malformed_resolution_is_refused(entry, message):
    with pytest.raises(InvalidAnalysisOutput, match=message):
        parse_analysis_output(analysis_output(resolutions=[entry]))


# -- case A: source-grounded ---------------------------------------------------------


def test_a_source_grounded_resolution_is_bound_reviewed_and_clears():
    ws, requirement, _ = scene()
    model = processed(
        ws, requirement, analysis_output(resolutions=[limit_resolution()])
    )
    assert len(model.calls) == 1
    _, stored = latest_process(ws)
    assert stored.version == "0.6" and stored.product_questions == ()
    [bound] = stored.resolutions
    [source] = bound.sources
    assert bound.resolution_class is ResolutionClass.SOURCE_GROUNDED
    assert (source.kind, source.requirement_id, source.entity_id) == (
        SourceKind.RAW,
        RAW_ID,
        "raw-uuid-1",
    )
    assert source.fingerprint and stored.autonomy_policy is None

    result, review_model = review(
        ws, requirement, resolution_verifications=[verify_resolution()]
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    context = review_model.calls[0]["context"]
    assert "[0] SOURCE_GROUNDED: " + LIMIT_QUESTION in context
    assert f'Source RAW {RAW_ID}: "{LIMIT_QUOTE}"' in context
    _, stored_review = latest_review(ws)
    assert stored_review.version == "0.7"
    assert stored_review.reviewed_resolutions == stored.resolutions
    assert stored_review.what_status is WhatStatus.CLEAR
    assert approve_standard_requirement(ws, requirement.id).is_normal


def test_the_prompts_carry_the_authority_rules():
    ws, requirement, _ = scene()
    model = processed(ws, requirement, analysis_output())
    prompt = " ".join(model.calls[0]["prompt"].split())
    for rule in (
        "never choose a silent winner",
        "Never cite your own normalized output",
        (
            "An AFFECTS peer, a merely similar peer, or a peer that is not Applied "
            "is never authority"
        ),
        "never broaden or paraphrase it",
        "Do not resolve something to empty product_questions",
    ):
        assert rule in prompt
    assert (
        "(none approved for this Project: DELEGATED_DEFAULT is unavailable"
        in (model.calls[0]["context"])
    )


# -- case B: dependency-grounded -----------------------------------------------------


def test_a_dependency_grounded_resolution_refers_to_its_owner_and_clears():
    ws, requirement, _ = scene(peers=(D1,), depends_on=(D1,))
    processed(ws, requirement, analysis_output(resolutions=[peer_resolution()]))
    _, stored = latest_process(ws)
    [source] = stored.resolutions[0].sources
    assert (source.kind, source.entity_id) == (SourceKind.DEPENDENCY, D1.id)
    dependency = {"requirement_id": D1.requirement_id, "outcome": "CONFIRMED"}
    reviewed(
        ws,
        requirement,
        dependency_verifications=[{**dependency, "reason": "It owns the rule."}],
        resolution_verifications=[verify_resolution()],
    )
    _, stored_review = latest_review(ws)
    assert stored_review.what_status is WhatStatus.CLEAR
    assert approve_standard_requirement(ws, requirement.id).is_normal


def test_an_unverified_dependency_cannot_ground_a_resolution():
    ws, requirement, _ = scene(peers=(D1,), depends_on=(D1,))
    processed(ws, requirement, analysis_output(resolutions=[peer_resolution()]))
    reviewed(
        ws,
        requirement,
        dependency_verifications=[
            {
                "requirement_id": D1.requirement_id,
                "outcome": "UNRESOLVED",
                "reason": "Cannot tell.",
            }
        ],
        resolution_verifications=[verify_resolution()],
    )
    _, stored_review = latest_review(ws)
    assert stored_review.what_status is WhatStatus.BLOCKED_ON_WHAT
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is Ready.MATERIAL_WHAT_UNRESOLVED


@pytest.mark.parametrize("relation", ["affects", "unrelated"])
def test_an_affects_or_unrelated_peer_is_no_authority(relation):
    ws, requirement, _ = scene(
        peers=(D1,), affects=(D1,) if relation == "affects" else ()
    )
    before = len(ws.mutations)
    result, _ = process(
        ws, requirement, analysis_output(resolutions=[peer_resolution()])
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert "AFFECTS and unrelated peers give no normative authority" in (
        " ".join(result.details)
    )
    assert ws.mutations[before:] == []


# -- cases C, D, E, G: delegated defaults --------------------------------------------


def test_an_authorized_default_is_bound_to_its_policy_and_reviewed_in_scope():
    ws, requirement, _ = scene()
    model = processed(
        ws,
        requirement,
        analysis_output(resolutions=[delegated_resolution()]),
        policies=POLICIES,
    )
    assert "[ERR-BODY]" in model.calls[0]["context"]
    _, stored = latest_process(ws)
    assert stored.autonomy_policy == POLICIES.for_project("SDLC").binding
    assert stored.resolutions[0].policy_clause == "ERR-BODY"
    result, review_model = review(
        ws,
        requirement,
        policies=POLICIES,
        resolution_verifications=[verify_resolution(delegated=True)],
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    context = review_model.calls[0]["context"]
    assert "permitted decision: " + ERROR_BODY.permitted_decision in context
    assert all(domain in context for domain in HUMAN_ONLY_DOMAINS)
    _, stored_review = latest_review(ws)
    assert stored_review.what_status is WhatStatus.CLEAR
    assert approve_standard_requirement(ws, requirement.id, policies=POLICIES).is_normal


@pytest.mark.parametrize(
    "policies, clause, message",
    [
        (DISABLED, "ERR-BODY", "no autonomy policy is approved"),
        (POLICIES, "ERR-WIDE", "does not contain"),
        (approved(code="OTHER"), "ERR-BODY", "no autonomy policy is approved"),
    ],
)
def test_an_unauthorized_default_invents_no_product_answer(policies, clause, message):
    ws, requirement, _ = scene()
    before = len(ws.mutations)
    result, _ = process(
        ws,
        requirement,
        analysis_output(resolutions=[delegated_resolution(clause=clause)]),
        policies=policies,
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert message in " ".join(result.details)
    assert ws.mutations[before:] == [] and artifacts(ws, "Process Result") == []


def test_without_a_default_the_question_stays_open_with_its_alternatives():
    ws, requirement, _ = scene()
    question = {
        "detail": "What does the error body say?",
        "material": True,
        "authority": "INSUFFICIENT_EVIDENCE",
        "alternatives": ["A message field", "An error code and a message"],
    }
    processed(ws, requirement, analysis_output(questions=[question]))
    _, stored = latest_process(ws)
    [kept] = stored.product_questions
    assert kept.authority is ResolutionClass.INSUFFICIENT_EVIDENCE
    assert kept.alternatives == tuple(question["alternatives"])
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
    _, stored_review = latest_review(ws)
    assert stored_review.what_status is WhatStatus.BLOCKED_ON_WHAT


def test_a_critical_decision_stays_with_the_human_even_under_a_policy():
    """E: a clause seems to apply, but the decision is security: HUMAN_REQUIRED."""
    ws, requirement, _ = scene()
    question = {
        "detail": "May the error body echo the request's credentials?",
        "material": True,
        "authority": "HUMAN_REQUIRED",
    }
    processed(ws, requirement, analysis_output(questions=[question]), policies=POLICIES)
    reviewed(
        ws,
        requirement,
        policies=POLICIES,
        question_verifications=[
            {
                "question_index": 0,
                "outcome": "CONFIRMED",
                "material": True,
                "reason": "Open.",
            }
        ],
    )
    _, stored_review = latest_review(ws)
    assert stored_review.what_status is WhatStatus.BLOCKED_ON_WHAT
    refused = approve_standard_requirement(ws, requirement.id, policies=POLICIES)
    assert refused.code is Ready.MATERIAL_WHAT_UNRESOLVED
    assert question["detail"] in refused.details


@pytest.mark.parametrize(
    "failing",
    [
        ("within_policy_clause",),  # G: a narrow clause broadened, or E: critical
        ("source_supports_answer",),  # F: the quote exists but does not justify it
        ("consistent_with_related",),  # H: a silent winner between sources
        ("authority_class_correct",),  # a misclassified authority
    ],
)
def test_a_rejected_resolution_can_never_clear_what(failing):
    delegated = failing == ("within_policy_clause",)
    ws, requirement, _ = (
        delegated_at_ready(
            resolution_verifications=[
                verify_resolution(outcome="REJECTED", delegated=True, failing=failing)
            ]
        )
        if delegated
        else source_grounded_at_ready(
            resolution_verifications=[
                verify_resolution(outcome="REJECTED", failing=failing)
            ]
        )
    )
    node, stored_review = latest_review(ws)
    assert stored_review.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert stored_review.verdict.value == "NEEDS_WORK", "a rejection is graded"
    assert any(
        "unconfirmed resolution [0]" in line
        for line in open_material_questions(stored_review)
    )
    policies = POLICIES if delegated else DISABLED
    refused = approve_standard_requirement(
        ws, requirement.id, ReviewVerdict.NEEDS_WORK, policies=policies
    )
    assert refused.code is Ready.MATERIAL_WHAT_UNRESOLVED
    apply_by_hand(ws, requirement)
    assert apply_standard_requirement(ws, requirement.id, policies=policies).code is (
        Apply.MATERIAL_WHAT_UNRESOLVED
    )
    rewrite_payload(ws, node, derived_what_status="CLEAR")
    with pytest.raises(InvalidReviewResult, match="contradicts the verified"):
        parse_review_result(ws.content[node.secret])


def test_an_unresolved_resolution_keeps_what_blocked():
    ws, _, _ = source_grounded_at_ready(
        resolution_verifications=[
            verify_resolution(
                outcome="UNRESOLVED", uncertain=("source_supports_answer",)
            )
        ]
    )
    _, stored_review = latest_review(ws)
    assert stored_review.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert stored_review.verdict.value == "PASS", "doubt is not a graded defect"


# -- the Review contract: the outcome must follow the checks -------------------------


def resolutions_of(*entries):
    return parse_analysis_output(analysis_output(resolutions=list(entries))).resolutions


@pytest.mark.parametrize(
    "verifications, message",
    [
        (None, "its absence verifies none"),
        ([], "unverified: Process resolution 0"),
        ([verify_resolution(), verify_resolution()], "more than once"),
        ([verify_resolution(index=3)], "has 1"),
        (
            [verify_resolution(failing=("issue_identified",))],
            "a confirmation needs every check to pass",
        ),
        (
            [verify_resolution(outcome="REJECTED")],
            "its checks derive CONFIRMED",
        ),
        (
            [verify_resolution(outcome="UNRESOLVED", failing=("issue_identified",))],
            "its checks derive REJECTED",
        ),
        (
            [verify_resolution(delegated=True)],
            "NOT_APPLICABLE exactly when",
        ),
        (
            [
                verify_resolution(
                    outcome="REJECTED", failing=("issue_identified",), severity=None
                )
            ],
            "severity if and only if",
        ),
    ],
)
def test_a_resolution_verification_that_does_not_hold_is_refused(
    verifications, message
):
    body = json.loads(review_output(resolution_verifications=verifications or []))
    if verifications is None:
        body.pop("resolution_verifications", None)
    elif not verifications:
        body["resolution_verifications"] = []
    for entry in body.get("resolution_verifications", []):
        if entry.get("severity", "") is None:
            del entry["severity"]
    with pytest.raises(InvalidReviewOutput, match=message):
        parse_review_output(
            json.dumps(body), (), (), (), resolutions=resolutions_of(limit_resolution())
        )


def test_every_check_must_be_answered():
    entry = verify_resolution()
    del entry["checks"]["testable_at_what_level"]
    body = json.loads(review_output(resolution_verifications=[entry]))
    with pytest.raises(InvalidReviewOutput, match="checks must answer exactly"):
        parse_review_output(
            json.dumps(body), (), (), (), resolutions=resolutions_of(limit_resolution())
        )
    assert len(RESOLUTION_CHECKS) == 10


def test_no_resolution_may_be_verified_for_a_process_that_made_none():
    body = review_output(resolution_verifications=[verify_resolution()])
    with pytest.raises(InvalidReviewOutput, match="predates them"):
        parse_review_output(body, (), (), (), resolutions=None)


# -- case F at Rework, case I, case M ------------------------------------------------


def test_a_rejected_resolution_returns_as_a_material_brief_item():
    ws, _, _ = source_grounded_at_ready(
        resolution_verifications=[
            verify_resolution(outcome="REJECTED", failing=("source_supports_answer",))
        ]
    )
    (_, stored_process), (_, stored_review) = latest_process(ws), latest_review(ws)
    [item] = build_rework_brief(stored_review, stored_process).items
    assert item.ref == "R0001.A0" and item.category is BriefCategory.RESOLUTION
    assert item.blocks_what and item.kind == "SOURCE_GROUNDED"
    assert item.severity.value == "WARNING" and LIMIT_QUESTION in item.detail


def test_a_resolved_rework_item_must_bind_its_resolution():
    ws, requirement, _ = source_grounded_at_ready(
        resolution_verifications=[
            verify_resolution(outcome="REJECTED", failing=("source_supports_answer",))
        ]
    )
    rework_standard_requirement(ws, requirement.id)
    unsupported = {"item": "R0001.A0", "outcome": "RESOLVED", "explanation": "Fixed."}
    result, _ = process(
        ws,
        requirement,
        analysis_output(rework=[unsupported]),
        authorized_new_cycle=True,
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert "must name the resolution that answers it" in " ".join(result.details)
    rebuttal = {"item": "R0001.A0", "outcome": "REBUTTED", "explanation": "Wrong."}
    result, _ = process(
        ws, requirement, analysis_output(rework=[rebuttal]), authorized_new_cycle=True
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert "REBUTTED response cites evidence" in " ".join(result.details)


def test_one_open_material_question_keeps_the_requirement_blocked():
    """M: a confirmed resolution clears nothing beyond itself."""
    ws, requirement, _ = scene()
    open_question = {
        "detail": "Is the limit per request or per batch?",
        "material": True,
    }
    processed(
        ws,
        requirement,
        analysis_output(resolutions=[limit_resolution()], questions=[open_question]),
    )
    reviewed(
        ws,
        requirement,
        resolution_verifications=[verify_resolution()],
        question_verifications=[
            {
                "question_index": 0,
                "outcome": "CONFIRMED",
                "material": True,
                "reason": "Open.",
            }
        ],
    )
    _, stored_review = latest_review(ws)
    assert stored_review.what_status is WhatStatus.BLOCKED_ON_WHAT
    assert approve_standard_requirement(ws, requirement.id).code is (
        Ready.MATERIAL_WHAT_UNRESOLVED
    )


# -- cases J and K: currentness ------------------------------------------------------


@pytest.mark.parametrize("after", [CHANGED, DISABLED, approved(policy_id="RENAMED")])
def test_a_changed_or_removed_policy_refuses_ready_apply_and_tsa(after):
    ws, requirement, _ = delegated_at_ready()
    before = len(ws.mutations)
    refused = approve_standard_requirement(ws, requirement.id, policies=after)
    assert refused.code is Ready.RESOLUTION_EVIDENCE_STALE, refused
    assert ws.mutations[before:] == []
    assert approve_standard_requirement(ws, requirement.id, policies=POLICIES).is_normal
    applied = apply_standard_requirement(ws, requirement.id, policies=after)
    assert applied.code is Apply.RESOLUTION_EVIDENCE_STALE, applied
    assert ws.requirements[requirement.id].state == "Apply"
    applied = apply_standard_requirement(ws, requirement.id, policies=POLICIES)
    assert applied.code is Apply.REQUIREMENT_APPLIED, applied
    with pytest.raises(AdmissionRefused) as caught:
        admit(ws, after)
    assert caught.value.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE
    assert "no longer active" in " ".join([str(caught.value), *caught.value.details])
    assert admit(ws, POLICIES).is_newly_written


def test_a_policy_changed_after_process_refuses_the_review():
    ws, requirement, _ = scene()
    processed(
        ws,
        requirement,
        analysis_output(resolutions=[delegated_resolution()]),
        policies=POLICIES,
    )
    result, model = review(
        ws,
        requirement,
        policies=CHANGED,
        resolution_verifications=[verify_resolution(delegated=True)],
    )
    assert result.code is ReviewCode.RESOLUTION_EVIDENCE_STALE, result
    assert not model.was_invoked and artifacts(ws, "Review Result") == []


def test_policy_currentness_is_irrelevant_to_evidence_that_relies_on_none():
    ws, requirement, _ = source_grounded_at_ready()
    assert approve_standard_requirement(ws, requirement.id, policies=CHANGED).is_normal


def test_a_changed_raw_makes_the_reviewed_resolution_stale():
    ws, requirement, _ = source_grounded_at_ready()
    ws.content["raw-secret"] += "\nLater, a second rule.\n"
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is Ready.RESOLUTION_EVIDENCE_STALE, refused
    apply_by_hand(ws, requirement)
    assert apply_standard_requirement(ws, requirement.id).code is (
        Apply.RESOLUTION_EVIDENCE_STALE
    )


def test_a_raw_changed_after_process_refuses_the_review():
    ws, requirement, _ = scene()
    processed(ws, requirement, analysis_output(resolutions=[limit_resolution()]))
    ws.content["raw-secret"] += "\nLater, a second rule.\n"
    result, model = review(
        ws, requirement, resolution_verifications=[verify_resolution()]
    )
    assert result.code is ReviewCode.RESOLUTION_EVIDENCE_STALE, result
    assert not model.was_invoked


def test_a_changed_dependency_makes_the_resolution_stale():
    """K: the supporting Requirement changes after Review."""
    ws, requirement, _ = scene(peers=(D1,), depends_on=(D1,))
    processed(ws, requirement, analysis_output(resolutions=[peer_resolution()]))
    reviewed(
        ws,
        requirement,
        dependency_verifications=[
            {
                "requirement_id": D1.requirement_id,
                "outcome": "CONFIRMED",
                "reason": "Owns it.",
            }
        ],
        resolution_verifications=[verify_resolution()],
    )
    root = next(d for d in ws.documents if d.entity_public_id == D1.public_id)
    ws.content[root.secret] += "\nA changed rule.\n"
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code in {
        Ready.DEPENDENCY_EVIDENCE_STALE,
        Ready.RESOLUTION_EVIDENCE_STALE,
    }, refused
    assert ws.requirements[requirement.id].state == "Ready"


def test_a_dependency_changed_after_process_refuses_the_review():
    ws, requirement, _ = scene(peers=(D1,), depends_on=(D1,))
    processed(ws, requirement, analysis_output(resolutions=[peer_resolution()]))
    root = next(d for d in ws.documents if d.entity_public_id == D1.public_id)
    give_reviewed_evidence(ws, D1, title="A retitled peer")
    assert PEER_QUOTE in ws.content[root.secret]
    result, model = review(
        ws,
        requirement,
        dependency_verifications=[
            {
                "requirement_id": D1.requirement_id,
                "outcome": "CONFIRMED",
                "reason": "Owns it.",
            }
        ],
        resolution_verifications=[verify_resolution()],
    )
    assert result.code is ReviewCode.RESOLUTION_EVIDENCE_STALE, result
    assert not model.was_invoked


# -- case L: forged or mismatched citations ------------------------------------------


@pytest.mark.parametrize(
    "entry, message",
    [
        (
            limit_resolution(sources=[citation(quote="Requests are always accepted.")]),
            "quote is not in the text it was given",
        ),
        (
            limit_resolution(
                sources=[citation(quote=LIMIT_QUOTE, requirement_id="SDLC-RAW-0099")]
            ),
            "not an originating RAW",
        ),
        (
            limit_resolution(
                sources=[
                    citation(
                        "REQUIREMENT",
                        "The runtime must refuse to execute a model without login.",
                    )
                ]
            ),
            "its own output cannot be cited",
        ),
    ],
)
def test_a_citation_that_does_not_hold_rejects_the_output(entry, message):
    ws, requirement, _ = scene()
    before = len(ws.mutations)
    result, _ = process(ws, requirement, analysis_output(resolutions=[entry]))
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert message in " ".join(result.details)
    assert ws.mutations[before:] == []


def forge(ws, change):
    node, _ = latest_process(ws)
    payload, _, _ = payload_of(ws, node)
    change(payload["resolutions"][0]["sources"][0])
    rewrite_payload(ws, node, resolutions=payload["resolutions"])


@pytest.mark.parametrize(
    "change, code",
    [
        (
            lambda source: source.update(quote="Requests are always accepted here."),
            ReviewCode.RESOLUTION_EVIDENCE_INVALID,
        ),
        (
            lambda source: source.update(entity_id="std-uuid-1"),
            ReviewCode.RESOLUTION_EVIDENCE_INVALID,
        ),
        (
            lambda source: source.update(fingerprint="0" * 64),
            ReviewCode.RESOLUTION_EVIDENCE_STALE,
        ),
    ],
)
def test_a_forged_persisted_citation_is_refused_before_the_reviewer(change, code):
    ws, requirement, _ = scene()
    processed(ws, requirement, analysis_output(resolutions=[limit_resolution()]))
    forge(ws, change)
    result, model = review(
        ws, requirement, resolution_verifications=[verify_resolution()]
    )
    assert result.code is code, result
    assert not model.was_invoked and artifacts(ws, "Review Result") == []


def test_a_forged_requirement_citation_is_refused_before_the_reviewer():
    ws, requirement, _ = scene()
    processed(
        ws,
        requirement,
        analysis_output(
            resolutions=[
                limit_resolution(sources=[citation("REQUIREMENT", DRAFT_QUOTE)])
            ]
        ),
    )
    forge(ws, lambda source: source.update(fingerprint="1" * 64))
    result, model = review(
        ws, requirement, resolution_verifications=[verify_resolution()]
    )
    assert result.code is ReviewCode.RESOLUTION_EVIDENCE_INVALID, result
    assert not model.was_invoked


def test_a_review_of_other_resolutions_is_incoherent():
    ws, requirement, _ = source_grounded_at_ready()
    node, _ = latest_review(ws)
    payload, _, _ = payload_of(ws, node)
    payload["reviewed_resolutions"][0]["answer"] = (
        "Something the Process never adopted."
    )
    rewrite_payload(ws, node, reviewed_resolutions=payload["reviewed_resolutions"])
    (_, stored_process), (_, stored_review) = latest_process(ws), latest_review(ws)
    with pytest.raises(InvalidReviewResult, match="not those of Process Result"):
        what_clearance(stored_review, stored_process)
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is Ready.INVALID_REVIEW_RESULT, refused


def test_a_persisted_confirmation_against_its_own_checks_is_refused():
    ws, _, _ = source_grounded_at_ready()
    node, _ = latest_review(ws)
    payload, _, _ = payload_of(ws, node)
    payload["resolution_verifications"][0]["checks"]["source_supports_answer"] = "FAIL"
    rewrite_payload(
        ws, node, resolution_verifications=payload["resolution_verifications"]
    )
    with pytest.raises(InvalidReviewResult, match="its checks derive REJECTED"):
        parse_review_result(ws.content[node.secret])


def test_a_downgraded_review_of_a_resolution_bound_process_is_incoherent():
    ws, requirement, _ = source_grounded_at_ready()
    node, stored = latest_review(ws)
    downgraded = replace(
        stored,
        version="0.6",
        reviewed_resolutions=(),
        reviewed_autonomy_policy=None,
        resolution_verifications=(),
        reviewed_product_questions=(),
    )
    ws.content[node.secret] = render_review_result(downgraded)
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is Ready.INVALID_REVIEW_RESULT, refused
    assert "does not match the resolution evidence" in " ".join(refused.details)


def test_a_delegated_default_without_its_policy_binding_is_refused_on_read():
    ws, requirement, _ = scene()
    processed(
        ws,
        requirement,
        analysis_output(resolutions=[delegated_resolution()]),
        policies=POLICIES,
    )
    node, _ = latest_process(ws)
    rewrite_payload(ws, node, autonomy_policy=None)
    with pytest.raises(InvalidProcessResult, match="needs the autonomy policy"):
        parse_process_result(ws.content[node.secret])


def test_an_older_process_result_cannot_carry_resolutions():
    ws, requirement, _ = scene()
    processed(ws, requirement, analysis_output(resolutions=[limit_resolution()]))
    node, _ = latest_process(ws)
    rewrite_payload(ws, node, process_result_version="0.5")
    with pytest.raises(InvalidProcessResult, match="cannot carry resolution evidence"):
        parse_process_result(ws.content[node.secret])


# -- historical compatibility --------------------------------------------------------


def test_older_evidence_is_never_read_as_having_resolutions():
    ws, _, _ = source_grounded_at_ready()
    node = downgrade_latest_process(ws)
    older = parse_process_result(ws.content[node.secret])
    assert older.version == "0.5" and older.resolutions == ()
    assert older.autonomy_policy is None and not older.is_resolution_bound
    assert older.run_input_identity == run_input_identity(
        older.input_tree.fingerprint, None
    ), "without a policy the run identity is the WI-2 one"


# -- case N: no policy ----------------------------------------------------------------


def test_without_a_policy_sources_still_resolve_and_defaults_do_not():
    ws, requirement, _ = source_grounded_at_ready()
    assert approve_standard_requirement(ws, requirement.id, policies=DISABLED).is_normal
    other, other_requirement, _ = scene()
    result, _ = process(
        other,
        other_requirement,
        analysis_output(resolutions=[delegated_resolution()]),
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT


# -- case O: no automatic approval ---------------------------------------------------


def test_a_clear_requirement_with_confirmed_resolutions_stops_at_ready():
    ws, requirement, _ = delegated_at_ready()
    _, stored_review = latest_review(ws)
    assert stored_review.what_status is WhatStatus.CLEAR
    assert stored_review.verdict.value == "PASS"
    assert ws.requirements[requirement.id].state == "Ready"
    assert not any(m.startswith("set_state") and "Apply" in m for m in ws.mutations)


# -- case P: recoverability and run identity -----------------------------------------


def interrupted_process(ws, requirement, output, policies):
    """Process persists its Result, then the Root rewrite fails."""
    original = ws.write_document_content

    def failing(secret, markdown):
        if secret == "std-secret":
            raise FiberyError("write failed")
        original(secret, markdown)

    ws.write_document_content = failing
    result, _ = process(ws, requirement, output, policies=policies)
    ws.write_document_content = original
    assert result.code is ProcessCode.PARTIAL_PROCESSING, result
    return latest_process(ws)


def test_a_resume_replays_the_exact_resolutions_and_policy_without_a_model():
    ws, requirement, _ = scene()
    node, persisted = interrupted_process(
        ws, requirement, analysis_output(resolutions=[delegated_resolution()]), POLICIES
    )
    result, model = process(ws, requirement, policies=POLICIES, resume_result=node.id)
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    assert not model.was_invoked
    _, replayed = latest_process(ws)
    assert replayed.resolutions == persisted.resolutions
    assert replayed.autonomy_policy == persisted.autonomy_policy


def test_a_resume_refuses_a_delegated_default_whose_policy_changed():
    ws, requirement, _ = scene()
    node, _ = interrupted_process(
        ws, requirement, analysis_output(resolutions=[delegated_resolution()]), POLICIES
    )
    before = len(ws.mutations)
    result, model = process(ws, requirement, policies=CHANGED, resume_result=node.id)
    assert result.code is ProcessCode.RESOLUTION_EVIDENCE_STALE, result
    assert not model.was_invoked and ws.mutations[before:] == []


def test_a_changed_policy_is_a_new_run_input():
    """Same tree, same Brief: the policy alone decides whether the model runs."""
    ws, requirement, _ = scene()
    processed(ws, requirement, analysis_output(), policies=POLICIES)
    for expected in (
        ProcessCode.REQUIREMENT_PROCESSED,
        ProcessCode.NO_CHANGES_TO_PROCESS,
    ):
        # The second iteration reaches a fixed point: its input is its output.
        ws.set_requirement_state(requirement.id, "Process")
        result, model = process(
            ws,
            requirement,
            analysis_output(),
            policies=POLICIES,
            authorized_new_cycle=True,
        )
        assert result.code is expected, result
    assert not model.was_invoked
    changed, model = process(
        ws, requirement, analysis_output(), policies=CHANGED, authorized_new_cycle=True
    )
    assert changed.code is ProcessCode.REQUIREMENT_PROCESSED and model.was_invoked


# -- section 16: the complete offline rework loop ------------------------------------


def test_the_complete_autonomous_rework_loop_offline():
    """Process finds an ambiguity, Review records it, a human sends it back,
    Process resolves it under authority, Review confirms, and it stops at Ready.
    """
    bystander = peer(77, state="Applied")
    ws, requirement, _ = scene(peers=(D1, bystander), depends_on=(D1,))
    bystander_root = next(
        d for d in ws.documents if d.entity_public_id == bystander.public_id
    )
    bystander_body = ws.content[bystander_root.secret]
    states = [ws.requirements[requirement.id].state]
    dependency = [
        {
            "requirement_id": D1.requirement_id,
            "outcome": "CONFIRMED",
            "reason": "Owns it.",
        }
    ]
    open_question = {
        "detail": LIMIT_QUESTION,
        "material": True,
        "authority": "INSUFFICIENT_EVIDENCE",
        "alternatives": ["Rejected with 413", "Truncated and accepted"],
    }

    # 1. Process finds a genuine product ambiguity.
    process_model = processed(
        ws, requirement, analysis_output(questions=[open_question])
    )
    states.append(ws.requirements[requirement.id].state)
    # 2. The independent Review records it as actionable and blocking.
    review_model = reviewed(
        ws,
        requirement,
        dependency_verifications=dependency,
        question_verifications=[
            {
                "question_index": 0,
                "outcome": "CONFIRMED",
                "material": True,
                "reason": "Open.",
            }
        ],
    )
    states.append(ws.requirements[requirement.id].state)
    _, first_review = latest_review(ws)
    assert first_review.what_status is WhatStatus.BLOCKED_ON_WHAT
    # 3. The human chooses rework through the existing route.
    assert rework_standard_requirement(ws, requirement.id).is_normal
    states.append(ws.requirements[requirement.id].state)
    # 4. Process receives the Brief and resolves the item from the RAW.
    second_process, second_model = process(
        ws,
        requirement,
        analysis_output(
            resolutions=[limit_resolution()],
            rework=[
                {
                    "item": "R0001.Q0",
                    "outcome": "RESOLVED",
                    "explanation": "The RAW states the limit and its outcome.",
                    "resolution_index": 0,
                }
            ],
        ),
        authorized_new_cycle=True,
    )
    assert second_process.code is ProcessCode.REQUIREMENT_PROCESSED, second_process
    assert "R0001.Q0" in second_model.calls[0]["context"]
    states.append(ws.requirements[requirement.id].state)
    _, reworked = latest_process(ws)
    assert (
        reworked.iteration == 2 and reworked.rework_brief.source.review_iteration == 1
    )
    assert reworked.rework_responses[0].resolution_index == 0
    assert reworked.product_questions == ()
    # 5. The second independent Review confirms the resolution and the answer.
    second_review_model = reviewed(
        ws,
        requirement,
        dependency_verifications=dependency,
        rework_verifications=[
            {"item": "R0001.Q0", "outcome": "CONFIRMED", "reason": "Now settled."}
        ],
        resolution_verifications=[verify_resolution()],
    )
    states.append(ws.requirements[requirement.id].state)
    _, final_review = latest_review(ws)

    assert states == ["Process", "Review", "Ready", "Process", "Review", "Ready"]
    assert ws.requirements[requirement.id].state == "Ready", "no automatic approval"
    assert [len(m.calls) for m in (process_model, second_model)] == [1, 1]
    assert [len(m.calls) for m in (review_model, second_review_model)] == [1, 1]
    assert final_review.what_status is WhatStatus.CLEAR
    assert final_review.reviewed_resolutions == reworked.resolutions
    assert [b.requirement_id for b in final_review.dependency_bindings] == [
        D1.requirement_id
    ]
    assert ws.content[bystander_root.secret] == bystander_body
    assert all(bystander.id not in m for m in ws.mutations)
    assert final_review.resolution_verifications[0].outcome is (
        VerificationOutcome.CONFIRMED
    )
    assert approve_standard_requirement(ws, requirement.id).is_normal


# -- mutation-closing checks: each guards a distinct safety condition ---------------


def test_a_raw_citation_cannot_name_a_dependency():
    ws, requirement, _ = scene(peers=(D1,), depends_on=(D1,))
    entry = limit_resolution(
        sources=[citation(quote=PEER_QUOTE, requirement_id=D1.requirement_id)]
    )
    result, _ = process(ws, requirement, analysis_output(resolutions=[entry]))
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert "not an originating RAW" in " ".join(result.details)


def test_a_raw_that_is_no_longer_an_origin_refuses_the_review():
    ws, requirement, _ = scene()
    processed(ws, requirement, analysis_output(resolutions=[limit_resolution()]))
    ws.derived_from_ids[requirement.id] = []
    result, model = review(
        ws, requirement, resolution_verifications=[verify_resolution()]
    )
    assert result.code is ReviewCode.RESOLUTION_EVIDENCE_INVALID, result
    assert "not an originating RAW" in result.message and not model.was_invoked


def test_a_dependency_edge_removed_after_process_refuses_the_review():
    ws, requirement, _ = scene(peers=(D1,), depends_on=(D1,))
    processed(ws, requirement, analysis_output(resolutions=[peer_resolution()]))
    ws.depends_on_ids[requirement.id] = []
    result, model = review(
        ws, requirement, resolution_verifications=[verify_resolution()]
    )
    assert result.code is ReviewCode.RESOLUTION_EVIDENCE_INVALID, result
    assert "not an existing or proposed DEPENDS_ON target" in result.message
    assert not model.was_invoked


def test_a_consistently_forged_citation_identity_is_refused_at_ready():
    ws, requirement, _ = source_grounded_at_ready()
    for node in (latest_process(ws)[0], latest_review(ws)[0]):
        payload, _, _ = payload_of(ws, node)
        key = "resolutions" if "resolutions" in payload else "reviewed_resolutions"
        payload[key][0]["sources"][0]["entity_id"] = "std-uuid-1"
        rewrite_payload(ws, node, **{key: payload[key]})
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is Ready.INVALID_REVIEW_RESULT, refused
    assert "is 'SDLC-FR-0031', not 'SDLC-RAW-0007'" in refused.message


def test_a_raw_changed_before_apply_refuses_before_any_relation_write():
    ws, requirement, _ = scene(peers=(D1,))
    processed(
        ws,
        requirement,
        analysis_output(
            resolutions=[limit_resolution()],
            relations=[
                {
                    "kind": "DEPENDS_ON",
                    "requirement_id": D1.requirement_id,
                    "rationale": "r",
                }
            ],
        ),
    )
    reviewed(
        ws,
        requirement,
        relation_verifications=[
            {
                "kind": "DEPENDS_ON",
                "requirement_id": D1.requirement_id,
                "outcome": "CONFIRMED",
                "reason": "Owns it.",
            }
        ],
        resolution_verifications=[verify_resolution()],
    )
    assert approve_standard_requirement(ws, requirement.id).is_normal
    ws.content["raw-secret"] += "\nLater, a second rule.\n"
    before = len(ws.mutations)
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is Apply.RESOLUTION_EVIDENCE_STALE, result
    assert ws.mutations[before:] == [] and ws.depends_on_ids.get(requirement.id) in (
        None,
        [],
    )


def test_a_raw_changed_during_apply_stops_before_applied():
    ws, requirement, _ = scene(peers=(D1,))
    processed(
        ws,
        requirement,
        analysis_output(
            resolutions=[limit_resolution()],
            relations=[
                {
                    "kind": "DEPENDS_ON",
                    "requirement_id": D1.requirement_id,
                    "rationale": "r",
                }
            ],
        ),
    )
    reviewed(
        ws,
        requirement,
        relation_verifications=[
            {
                "kind": "DEPENDS_ON",
                "requirement_id": D1.requirement_id,
                "outcome": "CONFIRMED",
                "reason": "Owns it.",
            }
        ],
        resolution_verifications=[verify_resolution()],
    )
    assert approve_standard_requirement(ws, requirement.id).is_normal
    original = ws.add_depends_on

    def and_the_raw_changes(entity_id, target):
        original(entity_id, target)
        ws.content["raw-secret"] += "\nLater, a second rule.\n"

    ws.add_depends_on = and_the_raw_changes
    result = apply_standard_requirement(ws, requirement.id)
    assert result.code is Apply.PARTIAL_APPLY, result
    assert Apply.RESOLUTION_EVIDENCE_STALE.value in result.details
    assert ws.requirements[requirement.id].state == "Apply"


def test_a_process_result_that_reads_back_without_its_resolutions_is_refused():
    ws, requirement, _ = scene()
    original = ws.write_document_content

    def dropping_resolutions(secret, markdown):
        if "Process Result" in markdown and '"resolutions": [' in markdown:
            start = markdown.index("```json\n") + len("```json\n")
            end = markdown.index("\n```", start)
            payload = json.loads(markdown[start:end])
            payload["resolutions"] = []
            markdown = markdown[:start] + json.dumps(payload) + markdown[end:]
        original(secret, markdown)

    ws.write_document_content = dropping_resolutions
    result, _ = process(
        ws, requirement, analysis_output(resolutions=[limit_resolution()])
    )
    assert result.code is ProcessCode.PARTIAL_PROCESSING, result
    assert ProcessCode.PROCESS_RESULT_WRITE_FAILED.value in result.details
    assert ws.requirements[requirement.id].state == "Process"


def test_a_process_result_never_persists_an_unbound_citation():
    ws, _, root = scene()
    unbound = parse_analysis_output(analysis_output(resolutions=[limit_resolution()]))
    manifest = tree_manifest(ws, root)
    with pytest.raises(InvalidProcessResult, match="binds every citation"):
        build_process_result(
            REQUIREMENT_ID,
            1,
            manifest.root_entry.content_fingerprint,
            unbound,
            manifest,
        )


# -- review findings: older questions, self-citation, persisted shapes, load order ---


def test_a_review_of_an_older_process_with_questions_copies_them_as_recorded():
    """B1: a 0.7 review of a 0.5 Process Result invents no question authority."""
    ws, requirement, _ = scene()
    open_question = {
        "detail": "Is the limit per request or per batch?",
        "material": True,
    }
    processed(ws, requirement, analysis_output(questions=[open_question]))
    downgrade_latest_process(ws)
    result, _ = review(
        ws,
        requirement,
        question_verifications=[
            {
                "question_index": 0,
                "outcome": "CONFIRMED",
                "material": False,
                "reason": "Minor.",
            }
        ],
    )
    assert result.code is ReviewCode.REQUIREMENT_REVIEWED, result
    (_, stored_process), (node, stored_review) = latest_process(ws), latest_review(ws)
    payload, _, _ = payload_of(ws, node)
    assert set(payload["reviewed_product_questions"][0]) == {"detail", "material"}
    assert stored_review.version == "0.7" and stored_review.reviewed_resolutions == ()
    assert what_clearance(stored_review, stored_process) is WhatStatus.CLEAR


def test_a_review_cannot_strip_the_authority_of_a_current_question():
    ws, requirement, _ = scene()
    open_question = {
        "detail": "Is the limit per request or per batch?",
        "material": True,
    }
    processed(ws, requirement, analysis_output(questions=[open_question]))
    reviewed(
        ws,
        requirement,
        question_verifications=[
            {
                "question_index": 0,
                "outcome": "CONFIRMED",
                "material": False,
                "reason": "Minor.",
            }
        ],
    )
    node, _ = latest_review(ws)
    payload, _, _ = payload_of(ws, node)
    payload["reviewed_product_questions"] = [open_question]
    rewrite_payload(
        ws, node, reviewed_product_questions=payload["reviewed_product_questions"]
    )
    with pytest.raises(InvalidReviewResult, match="not the questions"):
        what_clearance(
            parse_review_result(ws.content[node.secret]), latest_process(ws)[1]
        )


INVENTED = "Every request is capped at 7 retries per hour."


def rejected_invention():
    """Iteration 1 adopted an invented answer; Review 1 rejected it.

    The invented text stays in iteration 1's output, so it is in the next
    iteration's input: a REQUIREMENT citation of it binds, and only the
    attestation rule stands between it and authority.
    """
    ws, requirement, root = scene()
    ws.content[root.secret] = ws.content[root.secret].replace(DRAFT_QUOTE, INVENTED)
    invented = resolution(
        issue="How often may a request be retried?",
        answer=INVENTED,
        sources=[citation("REQUIREMENT", INVENTED)],
    )
    processed(
        ws,
        requirement,
        analysis_output(
            normalized_changes={"constraints_edge_cases": INVENTED},
            resolutions=[invented],
        ),
    )
    reviewed(
        ws,
        requirement,
        resolution_verifications=[
            verify_resolution(outcome="REJECTED", failing=("source_supports_answer",))
        ],
    )
    rework_standard_requirement(ws, requirement.id)
    return ws, requirement


@pytest.mark.parametrize(
    "response, resolutions",
    [
        (
            {"outcome": "RESOLVED", "resolution_index": 0},
            [
                resolution(
                    issue="How often may a request be retried?",
                    answer=INVENTED,
                    sources=[citation("REQUIREMENT", INVENTED)],
                )
            ],
        ),
        ({"outcome": "REBUTTED", "evidence": [citation("REQUIREMENT", INVENTED)]}, []),
    ],
)
def test_a_rejected_answer_cannot_become_its_own_source(response, resolutions):
    """B2: the earlier model's text in the Requirement is not authority for it."""
    ws, requirement = rejected_invention()
    answer = {"item": "R0001.A0", "explanation": "It is stated.", **response}
    before = len(ws.mutations)
    result, _ = process(
        ws,
        requirement,
        analysis_output(rework=[answer], resolutions=resolutions),
        authorized_new_cycle=True,
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert "no current operator attestation" in " ".join(result.details)
    assert ws.mutations[before:] == []


def test_a_rejected_answer_may_be_resolved_again_from_the_raw():
    ws, requirement = rejected_invention()
    answer = {
        "item": "R0001.A0",
        "outcome": "RESOLVED",
        "explanation": "The RAW states the limit instead.",
        "resolution_index": 0,
    }
    result, _ = process(
        ws,
        requirement,
        analysis_output(rework=[answer], resolutions=[limit_resolution()]),
        authorized_new_cycle=True,
    )
    assert result.code is ProcessCode.REQUIREMENT_PROCESSED, result
    _, stored = latest_process(ws)
    assert stored.rework_brief.resolution_refs == {"R0001.A0"}


@pytest.mark.parametrize(
    "change, message",
    [
        (
            lambda r: r.update(affected_sections=["open_questions"]),
            "Malformed persisted resolution",
        ),
        (
            lambda r: r["sources"][0].update(quote="too short"),
            "Malformed persisted citation",
        ),
    ],
)
def test_persisted_resolutions_are_held_to_the_model_contract(change, message):
    """N2: read-back is as strict as the contract the model answered."""
    ws, requirement, _ = scene()
    processed(ws, requirement, analysis_output(resolutions=[limit_resolution()]))
    node, _ = latest_process(ws)
    payload, _, _ = payload_of(ws, node)
    change(payload["resolutions"][0])
    rewrite_payload(ws, node, resolutions=payload["resolutions"])
    with pytest.raises(InvalidProcessResult, match=message):
        parse_process_result(ws.content[node.secret])


def test_a_persisted_unanswerable_question_keeps_its_alternatives():
    ws, requirement, _ = scene()
    question = {
        "detail": "What does the error body say?",
        "material": True,
        "authority": "INSUFFICIENT_EVIDENCE",
        "alternatives": ["A message field", "An error code and a message"],
    }
    processed(ws, requirement, analysis_output(questions=[question]))
    node, _ = latest_process(ws)
    rewrite_payload(ws, node, product_questions=[{**question, "alternatives": ["One"]}])
    with pytest.raises(
        InvalidProcessResult, match="Malformed persisted product question"
    ):
        parse_process_result(ws.content[node.secret])


def test_tsa_reads_the_policy_before_any_fibery_read(monkeypatch):
    """N1: a broken [autonomy] table refuses before the Space id is resolved."""
    contacted = []

    class Client:
        def __init__(self, settings):
            contacted.append(settings)

        def resolve_space_id(self):
            contacted.append("space read")
            return "space"

    def broken(path=None):
        raise AutonomyPolicyError("[autonomy] mode must be 'disabled' or 'enabled'.")

    monkeypatch.setattr(cli, "FiberyClient", Client)
    monkeypatch.setattr(cli, "load_autonomy_policies", broken)
    with pytest.raises(AutonomyPolicyError):
        cli._architecture_workspaces(cli.load_fibery_settings(ENVIRONMENT))
    assert contacted == []


def test_a_resolved_material_what_item_must_name_its_resolution():
    ws, requirement, _ = scene()
    processed(ws, requirement, analysis_output())
    reviewed(ws, requirement, material_unresolved_what=[{"detail": LIMIT_QUESTION}])
    rework_standard_requirement(ws, requirement.id)
    unsupported = {"item": "R0001.W0", "outcome": "RESOLVED", "explanation": "Fixed."}
    result, _ = process(
        ws,
        requirement,
        analysis_output(rework=[unsupported]),
        authorized_new_cycle=True,
    )
    assert result.code is ProcessCode.INVALID_MODEL_OUTPUT, result
    assert "must name the resolution that answers it, with its evidence" in (
        " ".join(result.details)
    )
