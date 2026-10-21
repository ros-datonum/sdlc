"""WI-6: autonomous Ready decisions (Requirement-Autonomous-Ready-v0.1).

Every end-to-end scenario runs `sdlc worker run` itself — the production
composition, runner, dispatcher, Standard Process, Review, the Ready decider
and Apply — over the Fibery and model fakes. The operator's configuration is
a real `config/sdlc.toml` in a temporary working directory, read by the real
loaders, and a scenario may edit it while the worker runs. Every Ready
authorization here is a TEST-ONLY fixture; the repository ships none.
"""

from __future__ import annotations

import dataclasses
import io
import json

import pytest

from review_fake import (
    add_process_iteration,
    confirm,
    review_output,
    rewrite_payload,
    verify_resolution,
)
from sdlc import autonomous_ready, cli
from sdlc.autonomous_ready import (
    HumanReason,
    ReadyDecider,
    ReadyDecisionKind,
    Transition,
)
from sdlc.autonomy_policy import load_autonomy_policies
from sdlc.fibery_http import ELIGIBLE_QUERY_LIMIT
from sdlc.fibery_workspace import FiberyError, ProjectRecord, RequirementRecord
from sdlc.model_runtime_config import load_model_runtime_config
from sdlc.ready_decision import (
    approve_standard_requirement,
    rework_standard_requirement,
)
from sdlc.ready_delegation import (
    MAX_ISSUE_REPEATS_CEILING,
    MAX_REWORK_ROUNDS_CEILING,
    NOT_DELEGATED,
    ReadyAuthorization,
    ReadyDelegationError,
    load_ready_delegation,
    parse_ready_delegation,
)
from sdlc.ready_progress import ProgressStop
from sdlc.requirement_dispatcher import Worker
from sdlc.requirement_runner import MACHINE_ROUTES, CycleOutcome
from sdlc.results import ApplyResultCode as Apply
from sdlc.results import ReadyDecisionResultCode as ReadyCode
from sdlc.standard_review import ReviewVerdict
from standard_fake import analysis_output, citation
from test_autonomous_resolution import (
    D1,
    LIMIT_QUOTE,
    limit_resolution,
    peer_resolution,
    scene,
)
from test_requirement_runner import (
    NO_WORKERS,
    NOT_PROCESSED,
    SUCCEEDED,
    CompletingWorkers,
    StatusWorkspace,
    drive,
    only_eligible,
    outcomes,
)
from test_worker_policy_lifetime import (
    CONFIRMED_D1,
    DISABLED_TABLE,
    P1,
    P2,
    REPOSITORY_CONFIG,
    Models,
    Operator,
    delegated_resolution,
    run_worker,
    worker_results,
)
from tree_fake import add_child

FINDING = {"kind": "NOT_TESTABLE", "detail": "No measurable threshold is given."}
OTHER = {"kind": "AMBIGUOUS", "detail": "Which runtimes are meant is unclear."}
CLEARER = {"acceptance_verification": "An unauthenticated CLI exits with code 2."}
CLEAREST = {"acceptance_verification": "An unauthenticated CLI exits with code 3."}
WHAT = {"detail": "Must an oversized valid request still succeed?", "material": True}


def authorization(
    project="SDLC",
    authorization_id="SDLC-READY-1",
    auto_approve=True,
    auto_rework=True,
    max_rework_rounds=2,
    max_issue_repeats=0,
):
    return ReadyAuthorization(
        project_code=project,
        authorization_id=authorization_id,
        approved_by="Test operator",
        auto_approve=auto_approve,
        auto_rework=auto_rework,
        max_rework_rounds=max_rework_rounds,
        max_issue_repeats=max_issue_repeats,
    )


def ready_table(*authorizations, fingerprint=None, mode="enabled"):
    """An enabled `[ready_decisions]` table; approved as written unless told otherwise."""
    authorizations = authorizations or (authorization(),)
    lines = ["[ready_decisions]", f"mode = {json.dumps(mode)}"]
    for item in authorizations:
        lines += [
            "",
            f"[ready_decisions.projects.{item.project_code}]",
            f"authorization_id = {json.dumps(item.authorization_id)}",
            f"approved_by = {json.dumps(item.approved_by)}",
            f"approved_fingerprint = {json.dumps(fingerprint or item.fingerprint)}",
            f"auto_approve = {json.dumps(item.auto_approve)}",
            f"auto_rework = {json.dumps(item.auto_rework)}",
            f"max_rework_rounds = {item.max_rework_rounds}",
            f"max_issue_repeats = {item.max_issue_repeats}",
        ]
    return "\n".join(lines) + "\n"


READY = ready_table()
READY_DISABLED = '[ready_decisions]\nmode = "disabled"\n'


def started(tmp_path, ready=READY, autonomy=DISABLED_TABLE):
    """One Standard Requirement in Process, its worker cycle at Not Processed."""
    operator = Operator(tmp_path)
    operator.configure(autonomy + "\n" + ready)
    inner, requirement, _ = scene()
    return operator, only_eligible(inner, requirement.id), requirement


def verify(item, outcome="CONFIRMED", reason="Checked against the source.", **kw):
    return {"item": item, "outcome": outcome, "reason": reason, **kw}


def answer(item, outcome="RESOLVED", explanation="Corrected from the source.", **kw):
    return {"item": item, "outcome": outcome, "explanation": explanation, **kw}


def decisions(reports):
    return [report.ready_decision for report in reports if report.ready_decision]


def state_of(ws, requirement):
    return ws.inner.requirements[requirement.id].state


def human_moves(ws):
    """State writes no worker or decider made: none in these scenarios."""
    return [m for m in ws.inner.mutations if m.startswith("set_requirement_state")]


# -- 16. the successful offline end-to-end path ------------------------------------


def test_offline_end_to_end_auto_rework_then_auto_approve_reaches_applied(
    monkeypatch, tmp_path
):
    """RAW source -> Process -> Review -> Ready -> AUTO_REWORK -> Process ->
    Review -> Ready -> AUTO_APPROVE -> Apply -> Applied, with no human step."""
    operator, ws, requirement = started(tmp_path)
    models = Models(
        process=[
            analysis_output(findings=[FINDING]),
            analysis_output(normalized_changes=CLEARER, rework=[answer("R0001.F0")]),
        ],
        review=[
            review_output(finding_verifications=[confirm(0, "WARNING")]),
            review_output(rework_verifications=[verify("R0001.F0")]),
        ],
    )

    code, reports, errors = run_worker(monkeypatch, operator, ws, models)

    assert code == cli.EXIT_INTERRUPTED, errors
    assert state_of(ws, requirement) == "Applied"
    assert [r.outcome for r in reports] == [
        CycleOutcome.HANDED_OFF,  # Process 1 -> Review
        CycleOutcome.SUCCEEDED,  # Review 1 -> Ready
        CycleOutcome.READY_DECIDED,  # AUTO_REWORK: Ready -> Process
        CycleOutcome.HANDED_OFF,  # Process 2 -> Review
        CycleOutcome.SUCCEEDED,  # Review 2 -> Ready
        CycleOutcome.READY_DECIDED,  # AUTO_APPROVE: Ready -> Apply
        CycleOutcome.SUCCEEDED,  # Apply -> Applied
        CycleOutcome.IDLE,
    ]
    rework, approval = decisions(reports)
    assert rework.decision is ReadyDecisionKind.AUTO_REWORK
    assert rework.transition is Transition.CONFIRMED
    assert rework.state_after == "Process"
    assert rework.evidence.review_iteration == 1
    assert rework.verdict == "NEEDS_WORK" and rework.what_status == "CLEAR"
    assert rework.reasons == ("actionable R0001.F0",)
    assert approval.decision is ReadyDecisionKind.AUTO_APPROVE
    assert approval.transition is Transition.CONFIRMED
    assert approval.state_after == "Apply"
    assert approval.evidence.review_iteration == 2
    assert approval.evidence.process_iteration == 2
    assert approval.verdict == "PASS" and approval.what_status == "CLEAR"
    assert approval.progress[0] == "rework rounds used 1 of 2"
    for record in (rework, approval):
        assert record.requirement_id == requirement.requirement_id
        assert record.entity_id == requirement.id
        assert record.project_code == "SDLC"
        assert record.authorization == authorization().binding
        assert record.checks and record.next_action is None
    # Exactly one model call per Process and per Review; none at Ready.
    assert len(models.process.calls) == 2 and len(models.review.calls) == 2
    # The rework carried WI-2's Brief; the Applied result is Apply's own.
    assert "R0001.F0" in models.process.calls[1]["context"]
    [applied] = worker_results(reports, Worker.STANDARD_APPLY)
    assert applied.code is Apply.REQUIREMENT_APPLIED
    # The only State writes are the workers' own and the two decisions.
    assert human_moves(ws) == [
        f"set_requirement_state {requirement.id} Review",
        f"set_requirement_state {requirement.id} Ready",
        f"set_requirement_state {requirement.id} Process",
        f"set_requirement_state {requirement.id} Review",
        f"set_requirement_state {requirement.id} Ready",
        f"set_requirement_state {requirement.id} Apply",
        f"set_requirement_state {requirement.id} Applied",
    ]


# -- helpers for Ready scenarios -----------------------------------------------------


def to_ready(
    monkeypatch,
    tmp_path,
    process,
    review,
    ready=READY,
    autonomy=DISABLED_TABLE,
    **scene_options,
):
    """Process and Review by the real worker with delegation off: at Ready + Succeeded.

    Returns the operator (still configured without Ready delegation), the
    workspace and the Requirement. The caller then configures delegation and
    starts a worker, exactly like an operator restarting the runner.
    """
    operator = Operator(tmp_path)
    operator.configure(autonomy + "\n" + READY_DISABLED)
    inner, requirement, _ = scene(**scene_options)
    ws = only_eligible(inner, requirement.id)
    models = Models(process=process, review=review)
    run_worker(monkeypatch, operator, ws, models)
    assert state_of(ws, requirement) == "Ready"
    assert ws.status_of(requirement.id) == SUCCEEDED
    operator.configure(autonomy + "\n" + ready)
    return operator, ws, requirement


def ready_at(monkeypatch, tmp_path, review, process=None, **options):
    return to_ready(
        monkeypatch,
        tmp_path,
        process or [analysis_output(findings=[FINDING])],
        [review],
        **options,
    )


PASS_REVIEW = review_output(finding_verifications=[confirm(0, "INFO")])
NEEDS_WORK_REVIEW = review_output(finding_verifications=[confirm(0, "WARNING")])
BLOCKING_REVIEW = review_output(finding_verifications=[confirm(0, "BLOCKING")])


def decide_once(monkeypatch, operator, ws, models=None, at_poll=None):
    """A (re)started worker: its decisions, reports and output.

    `at_poll[n]` runs before this worker's own n-th eligible-work query.
    """
    base = ws.polls
    code, reports, errors = run_worker(
        monkeypatch,
        operator,
        ws,
        models or Models(),
        at_poll={base + n: action for n, action in (at_poll or {}).items()},
    )
    assert code == cli.EXIT_INTERRUPTED, errors
    return decisions(reports), reports, errors


def only_decision(monkeypatch, operator, ws, **options):
    found, reports, _ = decide_once(monkeypatch, operator, ws, **options)
    [record] = found
    return record, reports


def decider_for(operator):
    return ReadyDecider(
        lambda: load_ready_delegation(operator.path),
        lambda: load_autonomy_policies(operator.path),
    )


def state_writes_since(ws, before):
    return [
        m for m in ws.inner.mutations[before:] if m.startswith("set_requirement_state")
    ]


def status_writes_since(ws, before):
    return [
        m for m in ws.inner.mutations[before:] if m.startswith("set_processing_status")
    ]


# -- 17. human escalation after one automatic rework ----------------------------------


def test_escalation_after_auto_rework_leaves_a_still_unresolved_issue_at_ready(
    monkeypatch, tmp_path
):
    """Process -> Review -> Ready -> AUTO_REWORK -> Process -> Review -> Ready ->
    HUMAN_REQUIRED: the reworked defect is independently rejected again."""
    operator, ws, requirement = started(tmp_path)
    models = Models(
        process=[
            analysis_output(findings=[FINDING]),
            analysis_output(normalized_changes=CLEARER, rework=[answer("R0001.F0")]),
        ],
        review=[
            NEEDS_WORK_REVIEW,
            review_output(
                rework_verifications=[
                    verify("R0001.F0", "REJECTED", severity="WARNING")
                ]
            ),
        ],
    )

    code, reports, errors = run_worker(monkeypatch, operator, ws, models)

    assert code == cli.EXIT_INTERRUPTED
    rework, stop = decisions(reports)
    assert rework.decision is ReadyDecisionKind.AUTO_REWORK
    assert stop.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert stop.transition is Transition.NOT_ATTEMPTED
    assert stop.evidence.review_iteration == 2 and stop.verdict == "NEEDS_WORK"
    codes = [reason.split(":")[0] for reason in stop.reasons]
    assert ProgressStop.REPEATED_ISSUE.value in codes
    assert ProgressStop.NO_INDEPENDENT_PROGRESS.value in codes
    assert any("R0001.F0" in reason for reason in stop.reasons)
    assert stop.next_action and "Ready -> Process" in stop.next_action
    assert state_of(ws, requirement) == "Ready"
    assert ws.status_of(requirement.id) == SUCCEEDED
    # No automatic approval and no further loop: two Process and two Review calls.
    assert len(models.process.calls) == 2 and len(models.review.calls) == 2
    assert reports[-1].outcome is CycleOutcome.IDLE
    assert reports[-2].outcome is CycleOutcome.READY_ESCALATED
    assert errors == ""


def test_escalation_when_rework_escalates_a_material_product_question(
    monkeypatch, tmp_path
):
    """A rejected source-grounded resolution is reworked once; the rework
    escalates it as a human product decision, and automation stops there."""
    escalated = answer(
        "R0001.A0", "ESCALATED", "No source settles it.", product_question_index=0
    )
    operator, ws, requirement = started(tmp_path)
    models = Models(
        process=[
            analysis_output(resolutions=[limit_resolution()]),
            analysis_output(
                normalized_changes=CLEARER, rework=[escalated], questions=[WHAT]
            ),
        ],
        review=[
            review_output(
                resolution_verifications=[
                    verify_resolution(
                        outcome="REJECTED", failing=("source_supports_answer",)
                    )
                ]
            ),
            review_output(
                rework_verifications=[verify("R0001.A0")],
                question_verifications=[
                    {
                        "question_index": 0,
                        "outcome": "CONFIRMED",
                        "material": True,
                        "reason": "Open.",
                    }
                ],
            ),
        ],
    )

    _, reports, _ = run_worker(monkeypatch, operator, ws, models)

    rework, stop = decisions(reports)
    assert rework.decision is ReadyDecisionKind.AUTO_REWORK
    assert rework.what_status == "BLOCKED_ON_WHAT"
    assert rework.reasons == ("actionable R0001.A0",)
    assert stop.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert stop.what_status == "BLOCKED_ON_WHAT"
    assert stop.reasons[0] == HumanReason.HUMAN_PRODUCT_DECISION.value
    assert "R0002.Q0 confirmed open by the Review" in stop.reasons
    assert "R0001.A0 escalated by Process" in stop.reasons
    assert state_of(ws, requirement) == "Ready"
    assert len(models.process.calls) == 2


# -- authority: default deny, separate permissions -------------------------------------


def test_the_repository_ships_no_ready_delegation():
    assert load_ready_delegation(REPOSITORY_CONFIG) == NOT_DELEGATED
    text = REPOSITORY_CONFIG.read_text(encoding="utf-8")
    assert '[ready_decisions]\nmode = "disabled"' in text
    assert "[ready_decisions.projects" not in text
    assert (
        cli._ready_decider(
            lambda: load_ready_delegation(REPOSITORY_CONFIG),
            lambda: load_autonomy_policies(REPOSITORY_CONFIG),
        )
        is None
    )


def test_an_approved_authorization_loads_exactly_as_approved(tmp_path):
    operator = Operator(tmp_path)
    operator.configure(READY)
    delegation = load_ready_delegation(operator.path)
    assert delegation.authorizations == (authorization(),)
    assert delegation.for_project("SDLC") == authorization()
    assert (
        delegation.for_project("OTHER") is None and delegation.for_project(None) is None
    )


def entry(**changes):
    item = authorization()
    body = {
        "authorization_id": item.authorization_id,
        "approved_by": item.approved_by,
        "approved_fingerprint": item.fingerprint,
        "auto_approve": True,
        "auto_rework": True,
        "max_rework_rounds": 2,
        "max_issue_repeats": 0,
    }
    return {**body, **changes}


MALFORMED = {
    "not-a-table": ("enabled", "must be a table"),
    "unknown-mode": ({"mode": "on"}, "mode must be"),
    "missing-mode": ({}, "mode must be"),
    "unknown-key": ({"mode": "disabled", "extra": 1}, "does not define"),
    "disabled-with-projects": (
        {"mode": "disabled", "projects": {"SDLC": entry()}},
        "delegates nothing",
    ),
    "enabled-without-projects": ({"mode": "enabled"}, "authorizes no project"),
    "content-changed": (
        {"mode": "enabled", "projects": {"SDLC": entry(max_rework_rounds=3)}},
        "not the content that was approved",
    ),
    "approval-changed": (
        {"mode": "enabled", "projects": {"SDLC": entry(approved_fingerprint="0" * 64)}},
        "not the content that was approved",
    ),
    "approval-malformed": (
        {"mode": "enabled", "projects": {"SDLC": entry(approved_fingerprint="x")}},
        "64 lowercase hex",
    ),
    "missing-limit": (
        {
            "mode": "enabled",
            "projects": {
                "SDLC": {k: v for k, v in entry().items() if k != "max_issue_repeats"}
            },
        },
        "is missing: max_issue_repeats",
    ),
    "unknown-entry-key": (
        {"mode": "enabled", "projects": {"SDLC": entry(auto_ready=True)}},
        "does not define",
    ),
    "nothing-delegated": (
        {
            "mode": "enabled",
            "projects": {"SDLC": entry(auto_approve=False, auto_rework=False)},
        },
        "delegates neither",
    ),
    "no-rounds": (
        {"mode": "enabled", "projects": {"SDLC": entry(max_rework_rounds=0)}},
        "max_rework_rounds must be",
    ),
    "too-many-rounds": (
        {
            "mode": "enabled",
            "projects": {
                "SDLC": entry(max_rework_rounds=MAX_REWORK_ROUNDS_CEILING + 1)
            },
        },
        "max_rework_rounds must be",
    ),
    "too-many-repeats": (
        {
            "mode": "enabled",
            "projects": {
                "SDLC": entry(max_issue_repeats=MAX_ISSUE_REPEATS_CEILING + 1)
            },
        },
        "max_issue_repeats must be",
    ),
    "boolean-limit": (
        {"mode": "enabled", "projects": {"SDLC": entry(max_rework_rounds=True)}},
        "max_rework_rounds must be",
    ),
    "string-flag": (
        {"mode": "enabled", "projects": {"SDLC": entry(auto_approve="yes")}},
        "must be true or false",
    ),
    "bad-project-code": (
        {"mode": "enabled", "projects": {"not a code": entry()}},
        "ready_decisions.projects.not a code",
    ),
    "shared-authorization-id": (
        {
            "mode": "enabled",
            "projects": {
                "SDLC": entry(),
                "OTHER": entry(
                    approved_fingerprint=authorization(project="OTHER").fingerprint
                ),
            },
        },
        "more than one project",
    ),
}


@pytest.mark.parametrize(
    ("section", "message"), MALFORMED.values(), ids=list(MALFORMED)
)
def test_a_malformed_ready_delegation_is_refused_whole(section, message):
    with pytest.raises(ReadyDelegationError, match=message):
        parse_ready_delegation(section)


def test_an_absent_or_disabled_table_delegates_nothing():
    assert parse_ready_delegation(None) == NOT_DELEGATED
    assert parse_ready_delegation({"mode": "disabled"}) == NOT_DELEGATED


def test_approved_by_is_a_record_outside_the_fingerprint():
    renamed = dataclasses.replace(authorization(), approved_by="Someone else")
    assert renamed.fingerprint == authorization().fingerprint
    assert renamed.binding == authorization().binding


@pytest.mark.parametrize("table", [READY_DISABLED, ""], ids=["disabled", "absent"])
def test_disabled_delegation_leaves_the_runner_exactly_as_before(
    monkeypatch, tmp_path, table
):
    operator, ws, requirement = started(tmp_path, ready=table)
    models = Models(process=[analysis_output(findings=[FINDING])], review=[PASS_REVIEW])

    code, reports, _ = run_worker(monkeypatch, operator, ws, models)

    assert code == cli.EXIT_INTERRUPTED
    assert [r.outcome for r in reports] == [
        CycleOutcome.HANDED_OFF,
        CycleOutcome.SUCCEEDED,
        CycleOutcome.IDLE,
    ]
    assert decisions(reports) == []
    # Only the machine routes were ever queried: no Ready query at all.
    assert {routes for routes, _ in ws.queries} == {MACHINE_ROUTES}
    assert state_of(ws, requirement) == "Ready"
    assert ws.status_of(requirement.id) == SUCCEEDED


def test_a_wi5_policy_alone_never_transitions_at_ready(monkeypatch, tmp_path):
    """A product-decision policy is not Ready authority: delegated defaults
    are confirmed, yet the Requirement stops at Ready for a human."""
    operator, ws, requirement = started(tmp_path, ready=READY_DISABLED, autonomy=P1)
    models = Models(
        process=[analysis_output(resolutions=[delegated_resolution()])],
        review=[
            review_output(resolution_verifications=[verify_resolution(delegated=True)])
        ],
    )

    _, reports, _ = run_worker(monkeypatch, operator, ws, models)

    assert decisions(reports) == []
    assert state_of(ws, requirement) == "Ready"


def test_ready_delegation_needs_no_wi5_policy(monkeypatch, tmp_path):
    """A source-grounded resolution, no autonomy policy: AUTO_APPROVE applies it."""
    operator, ws, requirement = started(tmp_path)
    models = Models(
        process=[analysis_output(resolutions=[limit_resolution()])],
        review=[review_output(resolution_verifications=[verify_resolution()])],
    )

    _, reports, _ = run_worker(monkeypatch, operator, ws, models)

    [approval] = decisions(reports)
    assert approval.decision is ReadyDecisionKind.AUTO_APPROVE
    assert approval.autonomy_policy is None
    assert state_of(ws, requirement) == "Applied"


def test_a_project_without_authorization_stays_at_ready(monkeypatch, tmp_path):
    other = ready_table(authorization(project="OTHER", authorization_id="OTHER-READY"))
    operator, ws, requirement = ready_at(
        monkeypatch, tmp_path, PASS_REVIEW, ready=other
    )
    before = len(ws.inner.mutations)

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons[0] == HumanReason.NOT_DELEGATED.value
    assert record.authorization is None and record.evidence is None
    assert state_of(ws, requirement) == "Ready"
    assert state_writes_since(ws, before) == []


def test_unauthorized_auto_approval_is_left_to_a_human(monkeypatch, tmp_path):
    rework_only = ready_table(authorization(auto_approve=False))
    operator, ws, requirement = ready_at(
        monkeypatch, tmp_path, PASS_REVIEW, ready=rework_only
    )

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons == (HumanReason.APPROVAL_NOT_DELEGATED.value,)
    assert record.verdict == "PASS" and record.what_status == "CLEAR"
    assert state_of(ws, requirement) == "Ready"


def test_pass_and_what_clear_is_approved_automatically(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)

    found, _, _ = decide_once(monkeypatch, operator, ws)

    [approval] = found
    assert approval.decision is ReadyDecisionKind.AUTO_APPROVE
    assert approval.transition is Transition.CONFIRMED
    assert approval.transition_code == "REQUIREMENT_APPROVED"
    assert state_of(ws, requirement) == "Applied"


@pytest.mark.parametrize(
    ("review", "verdict"),
    [(NEEDS_WORK_REVIEW, "NEEDS_WORK"), (BLOCKING_REVIEW, "BLOCKING")],
    ids=["NEEDS_WORK", "BLOCKING"],
)
def test_a_non_pass_verdict_is_never_approved(monkeypatch, tmp_path, review, verdict):
    approve_only = ready_table(authorization(auto_rework=False))
    operator, ws, requirement = ready_at(
        monkeypatch, tmp_path, review, ready=approve_only
    )

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.verdict == verdict
    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons[0] == HumanReason.REWORK_NOT_DELEGATED.value
    assert state_of(ws, requirement) == "Ready"


@pytest.mark.parametrize(
    "review", [NEEDS_WORK_REVIEW, BLOCKING_REVIEW], ids=["NEEDS_WORK", "BLOCKING"]
)
def test_a_non_pass_verdict_with_actionable_feedback_is_reworked(
    monkeypatch, tmp_path, review
):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, review)

    found, _, _ = decide_once(
        monkeypatch,
        operator,
        ws,
        models=Models(
            process=[
                analysis_output(normalized_changes=CLEARER, rework=[answer("R0001.F0")])
            ],
            review=[review_output(rework_verifications=[verify("R0001.F0")])],
        ),
    )

    assert [record.decision for record in found] == [
        ReadyDecisionKind.AUTO_REWORK,
        ReadyDecisionKind.AUTO_APPROVE,
    ]
    assert state_of(ws, requirement) == "Applied"


def test_a_confirmed_open_question_keeps_pass_from_auto_approval(monkeypatch, tmp_path):
    """PASS but BLOCKED_ON_WHAT: the open material question is a human's."""
    operator, ws, requirement = ready_at(
        monkeypatch,
        tmp_path,
        review_output(
            question_verifications=[
                {
                    "question_index": 0,
                    "outcome": "CONFIRMED",
                    "material": True,
                    "reason": "Open.",
                }
            ]
        ),
        process=[analysis_output(questions=[WHAT])],
    )

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.verdict == "PASS" and record.what_status == "BLOCKED_ON_WHAT"
    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons == (
        HumanReason.HUMAN_PRODUCT_DECISION.value,
        "R0001.Q0 confirmed open by the Review",
    )
    assert state_of(ws, requirement) == "Ready"


def test_a_review_added_material_what_question_is_a_humans(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(
        monkeypatch,
        tmp_path,
        review_output(material_unresolved_what=[{"detail": "Maximum length?"}]),
        process=[analysis_output()],
    )

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons[0] == HumanReason.HUMAN_PRODUCT_DECISION.value
    assert state_of(ws, requirement) == "Ready"


def test_an_unresolved_verification_is_ambiguous_evidence(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(
        monkeypatch,
        tmp_path,
        review_output(
            finding_verifications=[
                {
                    "process_finding_index": 0,
                    "outcome": "UNRESOLVED",
                    "reason": "Unclear.",
                }
            ]
        ),
    )

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.verdict == "PASS"
    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons == (HumanReason.AMBIGUOUS_REVIEW.value, "R0001.F0")
    assert state_of(ws, requirement) == "Ready"


def test_an_unconfirmed_resolution_is_never_approved(monkeypatch, tmp_path):
    """A rejected resolution graded INFO leaves the verdict PASS but is open."""
    operator, ws, requirement = ready_at(
        monkeypatch,
        tmp_path,
        review_output(
            resolution_verifications=[
                verify_resolution(
                    outcome="REJECTED",
                    failing=("source_supports_answer",),
                    severity="INFO",
                )
            ]
        ),
        process=[analysis_output(resolutions=[limit_resolution()])],
        ready=ready_table(authorization(auto_rework=False)),
    )

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.verdict == "PASS" and record.what_status == "BLOCKED_ON_WHAT"
    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons == (HumanReason.REWORK_NOT_DELEGATED.value, "R0001.A0")
    assert state_of(ws, requirement) == "Ready"


# -- currentness: stale or revoked evidence goes to a human ---------------------------


def root_of(ws):
    return next(d for d in ws.inner.documents if d.id == "std-doc-1")


def edit_root(ws):
    ws.inner.content["std-secret"] += "\nEdited by a human after the review.\n"


def add_child_document(ws):
    add_child(ws.inner, root_of(ws), "Late rule", "A late normative rule.\n", "late")


def run_process_again(ws):
    add_process_iteration(ws.inner, root_of(ws), 2)


STALE_EVIDENCE = {
    "root-edited": (edit_root, "REVIEW_RESULT_STALE"),
    "child-added": (add_child_document, "REVIEW_RESULT_STALE"),
    "process-ran-again": (run_process_again, "REVIEW_RESULT_STALE"),
}


@pytest.mark.parametrize(
    ("change", "code"), STALE_EVIDENCE.values(), ids=list(STALE_EVIDENCE)
)
def test_stale_reviewed_evidence_is_never_decided_automatically(
    monkeypatch, tmp_path, change, code
):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    change(ws)
    before = len(ws.inner.mutations)

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons == (HumanReason.EVIDENCE_NOT_CURRENT.value, code)
    assert record.transition is Transition.NOT_ATTEMPTED
    assert state_of(ws, requirement) == "Ready"
    assert state_writes_since(ws, before) == []


def test_a_stale_dependency_is_never_decided_automatically(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(
        monkeypatch,
        tmp_path,
        review_output(
            dependency_verifications=[CONFIRMED_D1],
            resolution_verifications=[verify_resolution()],
        ),
        process=[analysis_output(resolutions=[peer_resolution()])],
        peers=(D1,),
        depends_on=(D1,),
    )
    peer_root = next(
        d for d in ws.inner.documents if d.entity_public_id == D1.public_id
    )
    ws.inner.content[peer_root.secret] += "\nThe dependency changed after the review.\n"

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons[0] == HumanReason.EVIDENCE_NOT_CURRENT.value
    assert record.reasons[1] in {
        "DEPENDENCY_EVIDENCE_STALE",
        "RESOLUTION_EVIDENCE_STALE",
    }
    assert state_of(ws, requirement) == "Ready"


def test_a_changed_dependency_alone_is_never_decided_automatically(
    monkeypatch, tmp_path
):
    """No resolution cites the dependency: only WI-4's binding can see it moved."""
    operator, ws, requirement = ready_at(
        monkeypatch,
        tmp_path,
        review_output(dependency_verifications=[CONFIRMED_D1]),
        process=[analysis_output()],
        peers=(D1,),
        depends_on=(D1,),
    )
    peer_root = next(
        d for d in ws.inner.documents if d.entity_public_id == D1.public_id
    )
    ws.inner.content[peer_root.secret] += "\nThe dependency changed after the review.\n"

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons == (
        HumanReason.EVIDENCE_NOT_CURRENT.value,
        "DEPENDENCY_EVIDENCE_STALE",
    )
    assert state_of(ws, requirement) == "Ready"


def test_a_current_dependency_is_approved(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(
        monkeypatch,
        tmp_path,
        review_output(
            dependency_verifications=[CONFIRMED_D1],
            resolution_verifications=[verify_resolution()],
        ),
        process=[analysis_output(resolutions=[peer_resolution()])],
        peers=(D1,),
        depends_on=(D1,),
    )

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.decision is ReadyDecisionKind.AUTO_APPROVE
    assert state_of(ws, requirement) == "Applied"


def delegated_at_ready(monkeypatch, tmp_path):
    return ready_at(
        monkeypatch,
        tmp_path,
        review_output(resolution_verifications=[verify_resolution(delegated=True)]),
        process=[analysis_output(resolutions=[delegated_resolution()])],
        autonomy=P1,
    )


@pytest.mark.parametrize(
    "autonomy", [DISABLED_TABLE, P2, ""], ids=["disabled", "replaced", "removed"]
)
def test_a_revoked_wi5_policy_is_never_approved_on(monkeypatch, tmp_path, autonomy):
    operator, ws, requirement = delegated_at_ready(monkeypatch, tmp_path)
    operator.configure(autonomy + "\n" + READY)

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.reasons == (
        HumanReason.EVIDENCE_NOT_CURRENT.value,
        "RESOLUTION_EVIDENCE_STALE",
    )
    assert state_of(ws, requirement) == "Ready"


def test_a_current_wi5_policy_and_ready_delegation_approve_together(
    monkeypatch, tmp_path
):
    operator, ws, requirement = delegated_at_ready(monkeypatch, tmp_path)

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.decision is ReadyDecisionKind.AUTO_APPROVE
    assert record.autonomy_policy.policy_id == "SDLC-DEFAULTS-1"
    assert state_of(ws, requirement) == "Applied"


# -- bounded iterations, progress and oscillation ---------------------------------------


def reworks(*rounds, ready=READY):
    """Process outputs and Reviews for successive rounds, round 1 first."""
    return Models(
        process=[output for output, _ in rounds],
        review=[review for _, review in rounds],
    )


def stop_codes(record):
    return [reason.split(":")[0] for reason in record.reasons]


def run_rounds(monkeypatch, tmp_path, *rounds, ready=READY):
    operator, ws, requirement = started(tmp_path, ready=ready)
    models = reworks(*rounds)
    code, reports, errors = run_worker(monkeypatch, operator, ws, models)
    assert code == cli.EXIT_INTERRUPTED, errors
    return ws, requirement, decisions(reports), models


FIRST = (analysis_output(findings=[FINDING]), NEEDS_WORK_REVIEW)


def fixed_with(changes, item="R0001.F0", **review):
    return (
        analysis_output(normalized_changes=changes, rework=[answer(item)]),
        review_output(rework_verifications=[verify(item)], **review),
    )


def test_finite_useful_rework_stops_at_the_round_budget(monkeypatch, tmp_path):
    """Each round fixes its defect and the Review finds a new one; the budget
    of one round then stops automation however useful the rework was."""
    one_round = ready_table(authorization(max_rework_rounds=1))
    ws, requirement, found, models = run_rounds(
        monkeypatch,
        tmp_path,
        FIRST,
        fixed_with(CLEARER, new_findings=[{**OTHER, "severity": "WARNING"}]),
        ready=one_round,
    )

    rework, stop = found
    assert rework.decision is ReadyDecisionKind.AUTO_REWORK
    assert stop.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert stop_codes(stop) == [ProgressStop.REWORK_BUDGET_EXHAUSTED.value]
    assert stop.progress[0] == "rework rounds used 1 of 1"
    assert state_of(ws, requirement) == "Ready"
    assert len(models.process.calls) == 2


def test_two_useful_rounds_within_budget_continue(monkeypatch, tmp_path):
    ws, requirement, found, models = run_rounds(
        monkeypatch,
        tmp_path,
        FIRST,
        fixed_with(CLEARER, new_findings=[{**OTHER, "severity": "WARNING"}]),
        fixed_with(CLEAREST, item="R0002.N0"),
    )

    assert [record.decision for record in found] == [
        ReadyDecisionKind.AUTO_REWORK,
        ReadyDecisionKind.AUTO_REWORK,
        ReadyDecisionKind.AUTO_APPROVE,
    ]
    assert state_of(ws, requirement) == "Applied"
    assert len(models.process.calls) == 3 and len(models.review.calls) == 3


def test_repeated_identical_findings_stop_automation(monkeypatch, tmp_path):
    """The rework is confirmed, yet the Review reports exactly the same defect."""
    ws, requirement, found, _ = run_rounds(
        monkeypatch,
        tmp_path,
        FIRST,
        fixed_with(CLEARER, new_findings=[{**FINDING, "severity": "WARNING"}]),
    )

    stop = found[-1]
    assert stop.decision is ReadyDecisionKind.HUMAN_REQUIRED
    codes = stop_codes(stop)
    assert ProgressStop.REPEATED_ISSUE_SET.value in codes
    assert ProgressStop.REPEATED_ISSUE.value in codes
    assert state_of(ws, requirement) == "Ready"


def test_oscillating_findings_stop_automation(monkeypatch, tmp_path):
    """Issue A, then A fixed and B introduced, then B fixed and A reintroduced."""
    three_rounds = ready_table(authorization(max_rework_rounds=3))
    ws, requirement, found, models = run_rounds(
        monkeypatch,
        tmp_path,
        FIRST,
        fixed_with(CLEARER, new_findings=[{**OTHER, "severity": "WARNING"}]),
        fixed_with(
            CLEAREST, item="R0002.N0", new_findings=[{**FINDING, "severity": "WARNING"}]
        ),
        ready=three_rounds,
    )

    stop = found[-1]
    assert [record.decision for record in found][:2] == [
        ReadyDecisionKind.AUTO_REWORK,
        ReadyDecisionKind.AUTO_REWORK,
    ]
    assert stop.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert ProgressStop.REINTRODUCED_ISSUE.value in stop_codes(stop)
    assert any("R0001.F0" in reason for reason in stop.reasons)
    assert state_of(ws, requirement) == "Ready"
    assert len(models.process.calls) == 3


def test_a_rework_that_changes_no_normative_output_stops_automation(
    monkeypatch, tmp_path
):
    ws, requirement, found, _ = run_rounds(
        monkeypatch,
        tmp_path,
        FIRST,
        (
            analysis_output(
                rework=[
                    answer(
                        "R0001.F0", "REBUTTED", evidence=[citation(quote=LIMIT_QUOTE)]
                    )
                ]
            ),
            review_output(
                rework_verifications=[verify("R0001.F0")],
                new_findings=[{**OTHER, "severity": "WARNING"}],
            ),
        ),
    )

    stop = found[-1]
    assert stop.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert ProgressStop.UNCHANGED_NORMATIVE_OUTPUT.value in stop_codes(stop)
    assert state_of(ws, requirement) == "Ready"


def test_a_pass_over_output_an_earlier_review_sent_back_is_not_approved(
    monkeypatch, tmp_path
):
    """Identical content, two independent Reviews, two conclusions: the
    decider does not pick the convenient one."""
    ws, requirement, found, _ = run_rounds(
        monkeypatch,
        tmp_path,
        FIRST,
        (
            analysis_output(
                rework=[
                    answer(
                        "R0001.F0", "REBUTTED", evidence=[citation(quote=LIMIT_QUOTE)]
                    )
                ]
            ),
            review_output(rework_verifications=[verify("R0001.F0")]),
        ),
    )

    stop = found[-1]
    assert stop.verdict == "PASS" and stop.what_status == "CLEAR"
    assert stop.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert stop_codes(stop) == [ProgressStop.CONFLICTING_REVIEWS.value]
    assert state_of(ws, requirement) == "Ready"


def test_a_rework_that_restores_an_earlier_output_stops_automation(
    monkeypatch, tmp_path
):
    three_rounds = ready_table(authorization(max_rework_rounds=3, max_issue_repeats=1))
    ws, requirement, found, _ = run_rounds(
        monkeypatch,
        tmp_path,
        FIRST,
        fixed_with(CLEARER, new_findings=[{**OTHER, "severity": "WARNING"}]),
        (
            analysis_output(rework=[answer("R0002.N0")]),
            review_output(
                rework_verifications=[verify("R0002.N0")],
                new_findings=[{**FINDING, "kind": "AMBIGUOUS", "severity": "WARNING"}],
            ),
        ),
        ready=three_rounds,
    )

    stop = found[-1]
    assert stop.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert ProgressStop.RETURNED_TO_EARLIER_OUTPUT.value in stop_codes(stop)
    assert state_of(ws, requirement) == "Ready"


# -- runner integration: restart, idling, configuration lifetime -------------------------


ONE_ROUND = ready_table(authorization(max_rework_rounds=1))


def exhausted(monkeypatch, tmp_path):
    """One automatic rework done; its Review found a new defect: budget spent."""
    ws, requirement, found, _ = run_rounds(
        monkeypatch,
        tmp_path,
        FIRST,
        fixed_with(CLEARER, new_findings=[{**OTHER, "severity": "WARNING"}]),
        ready=ONE_ROUND,
    )
    assert stop_codes(found[-1]) == [ProgressStop.REWORK_BUDGET_EXHAUSTED.value]
    operator = Operator.__new__(Operator)
    operator.path = tmp_path / "config" / "sdlc.toml"
    return operator, ws, requirement


def test_a_restarted_worker_does_not_reset_the_rework_budget(monkeypatch, tmp_path):
    operator, ws, requirement = exhausted(monkeypatch, tmp_path)
    before = len(ws.inner.mutations)
    models = Models()

    record, _ = only_decision(monkeypatch, operator, ws, models=models)

    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert stop_codes(record) == [ProgressStop.REWORK_BUDGET_EXHAUSTED.value]
    assert record.progress[0] == "rework rounds used 1 of 1"
    assert not models.process.was_invoked and not models.review.was_invoked
    assert ws.inner.mutations[before:] == []
    assert state_of(ws, requirement) == "Ready"


def test_an_escalated_requirement_does_not_spin_the_runner(monkeypatch, tmp_path):
    operator, ws, _requirement = exhausted(monkeypatch, tmp_path)
    reads = ws.inner.calls.count("read_document_content")

    reports, sleeps = drive(ws, NO_WORKERS, 6, ready_decider=decider_for(operator))

    assert [r.outcome for r in reports] == [
        CycleOutcome.READY_ESCALATED,
        *[CycleOutcome.IDLE] * 5,
    ]
    assert len(sleeps) == 5
    # The evidence was read for the one decision; idle cycles read none.
    after_first = ws.inner.calls.count("read_document_content")
    assert after_first > reads
    reports, _ = drive(ws, NO_WORKERS, 1, ready_decider=decider_for(operator))
    assert [r.outcome for r in reports] == [CycleOutcome.READY_ESCALATED]


def test_a_configuration_change_reopens_an_escalated_decision(monkeypatch, tmp_path):
    rework_only = ready_table(authorization(auto_approve=False))
    operator, ws, requirement = ready_at(
        monkeypatch, tmp_path, PASS_REVIEW, ready=rework_only
    )

    found, _, _ = decide_once(
        monkeypatch,
        operator,
        ws,
        at_poll={3: lambda: operator.configure(DISABLED_TABLE + "\n" + READY)},
    )

    assert [(r.decision, r.reasons[:1]) for r in found] == [
        (
            ReadyDecisionKind.HUMAN_REQUIRED,
            (HumanReason.APPROVAL_NOT_DELEGATED.value,),
        ),
        (ReadyDecisionKind.AUTO_APPROVE, found[1].reasons[:1]),
    ]
    assert found[1].authorization == authorization().binding
    assert state_of(ws, requirement) == "Applied"


def test_disabling_delegation_while_running_returns_ready_to_the_human(
    monkeypatch, tmp_path
):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    before = len(ws.inner.mutations)

    found, reports, _ = decide_once(
        monkeypatch,
        operator,
        ws,
        at_poll={1: lambda: operator.configure(DISABLED_TABLE + "\n" + READY_DISABLED)},
    )

    assert found == []
    assert [r.outcome for r in reports] == [CycleOutcome.IDLE]
    assert ws.inner.mutations[before:] == []
    assert state_of(ws, requirement) == "Ready"


@pytest.mark.parametrize(
    "broken",
    [
        DISABLED_TABLE + "\n" + ready_table(fingerprint="0" * 64),
        DISABLED_TABLE + "\n[ready_decisions]\nmode = \n",
        '[autonomy]\nmode = "on"\n\n' + READY,
        None,
    ],
    ids=["approval-changed", "malformed", "autonomy-broken", "unreadable"],
)
def test_a_broken_configuration_while_running_never_falls_back(
    monkeypatch, tmp_path, broken
):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    before = len(ws.inner.mutations)

    found, reports, errors = decide_once(
        monkeypatch, operator, ws, at_poll={1: lambda: operator.configure(broken)}
    )

    assert found == []
    assert [r.outcome for r in reports] == [CycleOutcome.READY_FAILED]
    assert "no earlier configuration is reused" in errors
    assert ws.inner.mutations[before:] == []
    assert state_of(ws, requirement) == "Ready"


def test_a_decider_that_once_read_a_good_configuration_never_falls_back_to_it(
    monkeypatch, tmp_path
):
    rework_only = ready_table(authorization(auto_approve=False))
    operator, ws, requirement = ready_at(
        monkeypatch, tmp_path, PASS_REVIEW, ready=rework_only
    )
    broken = DISABLED_TABLE + "\n" + ready_table(fingerprint="0" * 64)

    found, reports, _ = decide_once(
        monkeypatch, operator, ws, at_poll={3: lambda: operator.configure(broken)}
    )

    assert [r.outcome for r in reports] == [
        CycleOutcome.READY_ESCALATED,
        CycleOutcome.READY_FAILED,
    ]
    assert [r.decision for r in found] == [ReadyDecisionKind.HUMAN_REQUIRED]
    assert state_of(ws, requirement) == "Ready"


def test_a_broken_ready_table_stops_the_runner_before_any_claim(monkeypatch, tmp_path):
    operator, ws, _requirement = started(
        tmp_path, ready=ready_table(fingerprint="0" * 64)
    )

    code, reports, errors = run_worker(monkeypatch, operator, ws, Models())

    assert code == cli.EXIT_FAILURE
    assert errors.startswith("WORKER_RUNNER_CONFIGURATION_INVALID")
    assert reports == [] and ws.inner.mutations == []


def test_composition_follows_the_start_time_configuration(tmp_path):
    operator = Operator(tmp_path)

    def compose():
        return cli._ready_decider(
            lambda: load_ready_delegation(operator.path),
            lambda: load_autonomy_policies(operator.path),
        )

    operator.configure(DISABLED_TABLE + "\n" + READY_DISABLED)
    assert compose() is None
    operator.configure(DISABLED_TABLE)
    assert compose() is None
    operator.configure(DISABLED_TABLE + "\n" + READY)
    assert isinstance(compose(), ReadyDecider)
    operator.configure(DISABLED_TABLE + "\n" + ready_table(fingerprint="0" * 64))
    with pytest.raises(ReadyDelegationError):
        compose()


def test_the_production_composition_and_a_direct_runner_decide_alike(
    monkeypatch, tmp_path
):
    """The CLI path and the runner driven directly with the same decider make
    the same decisions over the same evidence."""
    (tmp_path / "cli").mkdir()
    (tmp_path / "direct").mkdir()
    via_cli = run_rounds(monkeypatch, tmp_path / "cli", FIRST, fixed_with(CLEARER))
    operator, ws, requirement = started(tmp_path / "direct")
    models = reworks(FIRST, fixed_with(CLEARER))
    monkeypatch.setattr(cli, "LocalCliModelRuntime", lambda s: models.by_role[s.role])
    workers = cli._runner_workers(
        ws,
        load_model_runtime_config(operator.path),
        lambda: load_autonomy_policies(operator.path),
    )

    reports, _ = drive(ws, workers, 9, ready_decider=decider_for(operator))

    direct = decisions(reports)
    assert [(r.decision, r.transition, r.reasons) for r in direct] == [
        (r.decision, r.transition, r.reasons) for r in via_cli[2]
    ]
    assert state_of(ws, requirement) == state_of(via_cli[0], via_cli[1]) == "Applied"


# -- concurrency: a human's later decision is never overwritten ----------------------------


def first_then(change, function):
    """`function`, called after an external `change` lands at that very moment."""

    def run(*arguments, **options):
        change()
        return function(*arguments, **options)

    return run


def test_a_human_rework_during_auto_approval_is_kept(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    monkeypatch.setattr(
        autonomous_ready,
        "approve_standard_requirement",
        first_then(
            lambda: ws.set_requirement_state(requirement.id, "Process"),
            autonomous_ready.approve_standard_requirement,
        ),
    )

    found, reports, _ = decide_once(monkeypatch, operator, ws)

    [withdrawn] = found
    assert withdrawn.decision is ReadyDecisionKind.AUTO_APPROVE
    assert withdrawn.transition is Transition.WITHDRAWN
    assert withdrawn.transition_code == "REQUIREMENT_NOT_IN_READY"
    assert reports[-1].outcome is CycleOutcome.READY_WITHDRAWN
    assert state_of(ws, requirement) == "Process"
    assert ws.status_of(requirement.id) == "Not Processed"


def test_a_human_approval_during_auto_rework_is_kept(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, NEEDS_WORK_REVIEW)
    monkeypatch.setattr(
        autonomous_ready,
        "rework_standard_requirement",
        first_then(
            lambda: ws.set_requirement_state(requirement.id, "Apply"),
            autonomous_ready.rework_standard_requirement,
        ),
    )

    found, _, _ = decide_once(monkeypatch, operator, ws)

    [withdrawn] = found
    assert withdrawn.decision is ReadyDecisionKind.AUTO_REWORK
    assert withdrawn.transition is Transition.WITHDRAWN
    assert state_of(ws, requirement) == "Apply"
    assert f"set_requirement_state {requirement.id} Process" not in ws.inner.mutations


def test_a_root_edited_during_the_decision_refuses_the_transition(
    monkeypatch, tmp_path
):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    before = len(ws.inner.mutations)
    monkeypatch.setattr(
        autonomous_ready,
        "approve_standard_requirement",
        first_then(
            lambda: edit_root(ws), autonomous_ready.approve_standard_requirement
        ),
    )

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert record.transition is Transition.WITHDRAWN
    assert record.transition_code == "REVIEW_RESULT_STALE"
    assert state_writes_since(ws, before) == []
    assert state_of(ws, requirement) == "Ready"


def rewrite_latest_review(ws):
    node = next(d for d in reversed(ws.inner.documents) if "Review Result" in d.name)
    rewrite_payload(ws.inner, node, assessment={"summary": "Rewritten afterwards."})


@pytest.mark.parametrize(
    "change",
    ["review-rewritten", "authorization-changed", "policy-changed"],
)
def test_a_changed_basis_withdraws_the_decision_before_its_write(
    monkeypatch, tmp_path, change
):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    before = len(ws.inner.mutations)
    changes = {
        "review-rewritten": lambda: rewrite_latest_review(ws),
        "authorization-changed": lambda: operator.configure(
            DISABLED_TABLE + "\n" + ready_table(authorization(max_rework_rounds=3))
        ),
        "policy-changed": lambda: operator.configure(P1 + "\n" + READY),
    }
    monkeypatch.setattr(
        autonomous_ready,
        "approve_standard_requirement",
        first_then(changes[change], autonomous_ready.approve_standard_requirement),
    )

    found, reports, _ = decide_once(monkeypatch, operator, ws)

    [withdrawn] = found
    assert withdrawn.transition is Transition.WITHDRAWN
    assert withdrawn.transition_code == "DECISION_BASIS_CHANGED"
    assert reports[-1].outcome is CycleOutcome.READY_WITHDRAWN
    assert state_writes_since(ws, before) == []
    assert state_of(ws, requirement) == "Ready"


# -- the final binding: same Requirement, same Project, same eligible status -----------

OTHER_PROJECT = ProjectRecord(id="p-2", name="Other", code="OTHER", state="Planned")
THIRD_PROJECT = ProjectRecord(id="p-3", name="Third", code="THIRD", state="Planned")
DECIDED = {
    "approve": (
        PASS_REVIEW,
        "approve_standard_requirement",
        ReadyDecisionKind.AUTO_APPROVE,
        HumanReason.APPROVAL_NOT_DELEGATED,
    ),
    "rework": (
        NEEDS_WORK_REVIEW,
        "rework_standard_requirement",
        ReadyDecisionKind.AUTO_REWORK,
        HumanReason.REWORK_NOT_DELEGATED,
    ),
}


def with_projects(monkeypatch, ws, *projects):
    """The fake knows these Projects as well as its own; returns the live map."""
    known = {project.id: project for project in (ws.inner.project, *projects)}

    def read_project(project_id):
        ws.inner._record("read_project")
        return known.get(project_id)

    monkeypatch.setattr(ws.inner, "read_project", read_project)
    return known


def moved_to(ws, requirement, project_id):
    """Someone moves the Requirement to another Project in Fibery."""

    def move():
        current = ws.inner.requirements[requirement.id]
        ws.inner.requirements[requirement.id] = dataclasses.replace(
            current, project_id=project_id
        )

    return move


def withdrawn_before_the_write(monkeypatch, operator, ws, decided, change):
    """`change` lands just as the decided transition starts: nothing is written."""
    _, function, kind, _ = DECIDED[decided]
    before = len(ws.inner.mutations)
    monkeypatch.setattr(
        autonomous_ready,
        function,
        first_then(change, getattr(autonomous_ready, function)),
    )

    found, reports, _ = decide_once(monkeypatch, operator, ws)

    [withdrawn] = found
    assert withdrawn.decision is kind
    assert withdrawn.transition is Transition.WITHDRAWN
    assert withdrawn.transition_code == "DECISION_BASIS_CHANGED"
    assert reports[-1].outcome is CycleOutcome.READY_WITHDRAWN
    assert state_writes_since(ws, before) == []
    monkeypatch.setattr(autonomous_ready, function, getattr(autonomous_ready, function))
    return withdrawn


@pytest.mark.parametrize("decided", ["approve", "rework"])
def test_a_move_to_an_unauthorized_project_refuses_the_transition(
    monkeypatch, tmp_path, decided
):
    review, function, _, _ = DECIDED[decided]
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, review)
    with_projects(monkeypatch, ws, OTHER_PROJECT)
    real = getattr(autonomous_ready, function)

    withdrawn = withdrawn_before_the_write(
        monkeypatch, operator, ws, decided, moved_to(ws, requirement, "p-2")
    )

    assert withdrawn.project_code == "SDLC"
    assert state_of(ws, requirement) == "Ready"
    # Decided afresh, in the Project it is in now: a human's.
    monkeypatch.setattr(autonomous_ready, function, real)
    again, _ = only_decision(monkeypatch, operator, ws)
    assert again.project_code == "OTHER"
    assert again.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert again.reasons[0] == HumanReason.NOT_DELEGATED.value
    assert state_of(ws, requirement) == "Ready"


@pytest.mark.parametrize("decided", ["approve", "rework"])
@pytest.mark.parametrize("change", ["moved", "code-changed"])
def test_a_project_under_another_authorization_never_reuses_the_first(
    monkeypatch, tmp_path, decided, change
):
    """Both Projects are delegated, but differently: the decision made under
    the first Project's authorization is never written for the second."""
    review, function, _, not_delegated = DECIDED[decided]
    ready = ready_table(
        authorization(),
        authorization(
            project="OTHER",
            authorization_id="OTHER-READY-1",
            auto_approve=decided != "approve",
            auto_rework=decided != "rework",
        ),
    )
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, review, ready=ready)
    known = with_projects(monkeypatch, ws, OTHER_PROJECT)
    real = getattr(autonomous_ready, function)

    def recode():
        known["p-1"] = dataclasses.replace(known["p-1"], code="OTHER")

    changes = {"moved": moved_to(ws, requirement, "p-2"), "code-changed": recode}
    withdrawn = withdrawn_before_the_write(
        monkeypatch, operator, ws, decided, changes[change]
    )

    assert withdrawn.authorization.authorization_id == "SDLC-READY-1"
    monkeypatch.setattr(autonomous_ready, function, real)
    again, _ = only_decision(monkeypatch, operator, ws)
    assert again.authorization.authorization_id == "OTHER-READY-1"
    assert again.decision is ReadyDecisionKind.HUMAN_REQUIRED
    assert again.reasons[0] == not_delegated.value
    assert state_of(ws, requirement) == "Ready"


@pytest.mark.parametrize("decided", ["approve", "rework"])
def test_a_move_to_another_project_with_the_same_code_refuses_the_transition(
    monkeypatch, tmp_path, decided
):
    """Fibery enforces no Code uniqueness (API constraint 14): the decided
    Project is bound by entity as well as by Code."""
    review, _, _, _ = DECIDED[decided]
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, review)
    twin = ProjectRecord(id="p-4", name="Twin", code="SDLC", state="Planned")
    with_projects(monkeypatch, ws, twin)

    withdrawn_before_the_write(
        monkeypatch, operator, ws, decided, moved_to(ws, requirement, "p-4")
    )

    assert state_of(ws, requirement) == "Ready"


@pytest.mark.parametrize("decided", ["approve", "rework"])
@pytest.mark.parametrize("status", ["Processing", "Failed", "Not Processed"])
def test_a_processing_status_change_refuses_the_transition(
    monkeypatch, tmp_path, decided, status
):
    review, _, _, _ = DECIDED[decided]
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, review)

    def set_status():
        ws.statuses[requirement.id] = status

    withdrawn_before_the_write(monkeypatch, operator, ws, decided, set_status)

    assert state_of(ws, requirement) == "Ready"
    assert ws.status_of(requirement.id) == status


@pytest.mark.parametrize("decided", ["approve", "rework"])
@pytest.mark.parametrize("failure", ["removed", "unreadable"])
def test_a_project_that_cannot_be_established_refuses_the_transition(
    monkeypatch, tmp_path, decided, failure
):
    review, _, _, _ = DECIDED[decided]
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, review)
    known = with_projects(monkeypatch, ws)

    def unreadable(project_id):
        raise FiberyError("Fibery is unavailable")

    changes = {
        "removed": lambda: known.pop("p-1"),
        "unreadable": lambda: monkeypatch.setattr(ws.inner, "read_project", unreadable),
    }
    withdrawn_before_the_write(monkeypatch, operator, ws, decided, changes[failure])

    assert state_of(ws, requirement) == "Ready"


# -- recovery: failed, lost and unconfirmed writes ------------------------------------------


def fail_once(monkeypatch, ws, method, error="Fibery is unavailable"):
    """The fake's next `method` call raises; later calls behave normally."""
    real = getattr(ws.inner, method)
    calls = []

    def flaky(*arguments, **options):
        calls.append(arguments)
        if len(calls) == 1:
            raise FiberyError(error)
        return real(*arguments, **options)

    monkeypatch.setattr(ws.inner, method, flaky)


def fail_next(ws, method, error="Fibery is unavailable"):
    def fail():
        raise FiberyError(error)

    ws.on_call[(method, ws.inner.calls.count(method) + 1)] = fail


def test_a_failed_state_write_is_uncertain_and_never_repeated_by_this_worker(
    monkeypatch, tmp_path
):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    fail_next(ws, "set_requirement_state")

    found, reports, errors = decide_once(monkeypatch, operator, ws)

    [uncertain] = found
    assert uncertain.decision is ReadyDecisionKind.AUTO_APPROVE
    assert uncertain.transition is Transition.UNCERTAIN
    assert uncertain.transition_code == "FIBERY_WRITE_FAILED"
    assert "will not repeat this decision" in uncertain.next_action
    assert [r.outcome for r in reports] == [
        CycleOutcome.READY_UNCERTAIN,
        CycleOutcome.IDLE,
    ]
    assert "READY_UNCERTAIN" in errors
    assert state_of(ws, requirement) == "Ready"

    # A restart decides afresh from Fibery: the State is still Ready.
    again, _, _ = decide_once(monkeypatch, operator, ws)
    assert again[0].decision is ReadyDecisionKind.AUTO_APPROVE
    assert again[0].transition is Transition.CONFIRMED
    assert state_of(ws, requirement) == "Applied"


def test_a_lost_response_after_the_write_does_not_transition_twice(
    monkeypatch, tmp_path
):
    """The write lands but its read-back fails: uncertain, never repeated."""
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    real = ws.inner.set_requirement_state

    def write_then_lose_the_response(entity_id, state):
        real(entity_id, state)
        fail_next(ws, "read_requirement")

    monkeypatch.setattr(ws.inner, "set_requirement_state", write_then_lose_the_response)
    found, _, _ = decide_once(monkeypatch, operator, ws)
    monkeypatch.setattr(ws.inner, "set_requirement_state", real)

    # Reported as uncertain and not repeated; the State it did reach is then
    # an ordinary Apply cycle, which revalidates everything itself.
    assert found[0].transition is Transition.UNCERTAIN
    assert found[0].state_after is None
    assert state_of(ws, requirement) == "Applied"

    again, _, _ = decide_once(monkeypatch, operator, ws)
    assert again == []
    assert (
        ws.inner.mutations.count(f"set_requirement_state {requirement.id} Apply") == 1
    )


def test_an_incomplete_read_back_is_uncertain(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    monkeypatch.setattr(
        ws.inner, "set_requirement_state", lambda entity_id, state: None
    )

    record, _ = only_decision(monkeypatch, operator, ws)

    assert record.transition is Transition.UNCERTAIN
    assert record.transition_code == "VALIDATION_FAILED"
    assert record.state_after is None
    assert state_of(ws, requirement) == "Ready"


@pytest.mark.parametrize(
    "method", ["read_document_content", "child_documents", "read_project"]
)
def test_a_failed_evidence_read_decides_nothing_and_retries_after_the_wait(
    monkeypatch, tmp_path, method
):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    before = len(ws.inner.mutations)

    found, reports, errors = decide_once(
        monkeypatch,
        operator,
        ws,
        at_poll={1: lambda: fail_once(monkeypatch, ws, method)},
    )

    assert found == []
    assert [r.outcome for r in reports] == [CycleOutcome.READY_FAILED]
    assert "no Ready decision was made" in errors
    assert "Reject unauthenticated model execution" not in errors
    assert ws.inner.mutations[before:] == []
    assert state_of(ws, requirement) == "Ready"


def test_resumed_processing_after_auto_rework_is_an_ordinary_process_cycle(
    monkeypatch, tmp_path
):
    """A worker stopped right after AUTO_REWORK: the restart runs Process from
    the reset status, with the Brief, and decides the next Ready afresh."""
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, NEEDS_WORK_REVIEW)

    def ctrl_c():
        raise KeyboardInterrupt

    # Poll 1 finds no machine work, poll 2 is the decision, poll 3 never runs.
    found, _, _ = decide_once(monkeypatch, operator, ws, at_poll={3: ctrl_c})
    assert [r.decision for r in found] == [ReadyDecisionKind.AUTO_REWORK]
    assert state_of(ws, requirement) == "Process"
    assert ws.status_of(requirement.id) == "Not Processed"

    models = reworks(fixed_with(CLEARER))
    again, _, _ = decide_once(monkeypatch, operator, ws, models=models)
    assert [r.decision for r in again] == [ReadyDecisionKind.AUTO_APPROVE]
    assert "R0001.F0" in models.process.calls[0]["context"]
    assert state_of(ws, requirement) == "Applied"


# -- Processing Status, eligibility and the unchanged routes ----------------------------------


def test_machine_work_always_comes_before_a_ready_decision(monkeypatch, tmp_path):
    """A decidable Ready Requirement waits while any machine route has work."""
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    other = dataclasses.replace(
        ws.inner.requirements[requirement.id],
        id="std-uuid-2",
        public_id="32",
        requirement_id="SDLC-FR-0032",
        state="Process",
    )
    ws.inner.requirements[other.id] = other
    ws.statuses[other.id] = NOT_PROCESSED
    workers = CompletingWorkers(ws)

    reports, _ = drive(ws, workers.bound(), 1, ready_decider=decider_for(operator))

    assert workers.calls == [(Worker.STANDARD_PROCESS, other.id, "Processing")]
    assert reports[0].ready_decision is None
    assert state_of(ws, requirement) == "Ready"


def test_the_decider_never_writes_processing_status(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, NEEDS_WORK_REVIEW)
    before = len(ws.inner.mutations)

    found, _, _ = decide_once(
        monkeypatch,
        operator,
        ws,
        at_poll={3: lambda: operator.configure(DISABLED_TABLE + "\n" + READY_DISABLED)},
        models=reworks(fixed_with(CLEARER)),
    )

    assert [r.decision for r in found] == [ReadyDecisionKind.AUTO_REWORK]
    # The reset belongs to the automation; the claims and settles to the runner.
    assert ws.resets[-2:] == [(requirement.id, "Process"), (requirement.id, "Review")]
    assert status_writes_since(ws, before) == [
        f"set_processing_status {requirement.id} Processing",
        f"set_processing_status {requirement.id} Processing",
        f"set_processing_status {requirement.id} Succeeded",
    ]
    assert state_of(ws, requirement) == "Ready"
    assert ws.status_of(requirement.id) == SUCCEEDED


@pytest.mark.parametrize("status", ["Not Processed", "Processing", "Failed"])
def test_only_a_ready_whose_review_cycle_succeeded_is_a_candidate(
    monkeypatch, tmp_path, status
):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    ws.statuses[requirement.id] = status
    before = len(ws.inner.mutations)

    found, _reports, _ = decide_once(monkeypatch, operator, ws)

    assert found == []
    assert ws.inner.mutations[before:] == []
    assert state_of(ws, requirement) == "Ready"


def test_a_ready_row_the_query_should_not_return_is_never_decided(
    monkeypatch, tmp_path
):
    """The candidate filter does not trust the query: a Ready row whose Review
    cycle did not succeed under this worker stays with a human."""
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    ws.statuses[requirement.id] = NOT_PROCESSED
    ws.poll_rows = [ws.read_requirement(requirement.id)]
    before = len(ws.inner.mutations)

    found, reports, _ = decide_once(monkeypatch, operator, ws)

    assert found == []
    assert [r.outcome for r in reports] == [CycleOutcome.IDLE]
    assert ws.inner.mutations[before:] == []
    assert state_of(ws, requirement) == "Ready"


# -- discovery: every Ready candidate is reached, one bounded page per call ------------

DELEGATED_PROJECTS = ready_table(
    authorization(), authorization(project="THIRD", authorization_id="THIRD-READY-1")
)


def crowd(ws, count, project_id, prefix):
    """`count` Ready + Succeeded Standard Requirements ahead of the fixture's in
    `fibery/id` order, none with evidence: each is decided once, to a human."""
    for number in range(1, count + 1):
        entity = f"{prefix}-{number:04d}"
        ws.inner.requirements[entity] = RequirementRecord(
            id=entity,
            public_id=str(5000 + len(ws.inner.requirements)),
            requirement_id=None,
            title=None,
            type_name="Standard",
            state="Ready",
            revision=1,
            project_id=project_id,
            source_fingerprint=None,
        )


def ready_decisions(reports):
    return [r.requirement.id for r in reports if r.ready_decision is not None]


CROWDS = {
    "unauthorized-first-page": (("p-2", 100),),
    "more-authorized-than-a-page": (("p-1", 150),),
    "several-projects": (("p-2", 70), ("p-1", 70), ("p-3", 70)),
}


@pytest.mark.parametrize("crowd_name", list(CROWDS))
def test_a_candidate_beyond_the_first_page_is_reached(
    monkeypatch, tmp_path, crowd_name
):
    operator, ws, requirement = ready_at(
        monkeypatch, tmp_path, PASS_REVIEW, ready=DELEGATED_PROJECTS
    )
    with_projects(monkeypatch, ws, OTHER_PROJECT, THIRD_PROJECT)
    for index, (project_id, count) in enumerate(CROWDS[crowd_name]):
        crowd(ws, count, project_id, f"a{index}")
    ahead = sum(count for _, count in CROWDS[crowd_name])
    assert ahead >= ELIGIBLE_QUERY_LIMIT
    # Pages wholly ahead of the fixture: each costs one idle cycle once decided.
    passed = ahead // ELIGIBLE_QUERY_LIMIT
    decider = decider_for(operator)
    workers = CompletingWorkers(ws)
    queries = ws.inner.calls.count("find_eligible_requirements_after")

    # Every Ready row is decided exactly once, the fixture's approval is
    # applied by the ordinary Apply route, and nothing is left to decide.
    cycles = ahead + 1 + passed + 1
    reports, sleeps = drive(ws, workers.bound(), cycles, ready_decider=decider)

    decided = ready_decisions(reports)
    assert len(decided) == len(set(decided)) == ahead + 1
    [approved] = [
        record
        for record in (r.ready_decision for r in reports)
        if record is not None and record.entity_id == requirement.id
    ]
    assert approved.decision is ReadyDecisionKind.AUTO_APPROVE
    assert approved.transition is Transition.CONFIRMED
    others = [r.ready_decision for r in reports if r.ready_decision is not None]
    assert sum(r.decision is ReadyDecisionKind.HUMAN_REQUIRED for r in others) == ahead
    assert [call[0] for call in workers.calls] == [Worker.STANDARD_APPLY]
    assert len(sleeps) == passed
    # One bounded Ready query per idle-of-machine-work cycle, never a scan.
    assert ws.inner.calls.count("find_eligible_requirements_after") - queries == (
        cycles - 1
    )
    assert state_of(ws, requirement) == "Applied"


def test_a_candidate_that_arrives_after_a_full_sweep_is_reached(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    with_projects(monkeypatch, ws, OTHER_PROJECT)
    crowd(ws, ELIGIBLE_QUERY_LIMIT, "p-2", "a0")
    ws.inner.requirements[requirement.id] = dataclasses.replace(
        ws.inner.requirements[requirement.id], state="Draft"
    )
    decider = decider_for(operator)
    reports, _ = drive(ws, NO_WORKERS, ELIGIBLE_QUERY_LIMIT + 4, ready_decider=decider)
    assert len(ready_decisions(reports)) == ELIGIBLE_QUERY_LIMIT
    assert outcomes(reports)[-4:] == [CycleOutcome.IDLE] * 4

    # Back at Ready + Succeeded, beyond the remembered first page.
    ws.inner.requirements[requirement.id] = dataclasses.replace(
        ws.inner.requirements[requirement.id], state="Ready"
    )
    workers = CompletingWorkers(ws)
    reports, _ = drive(ws, workers.bound(), 4, ready_decider=decider)

    [approved] = [r.ready_decision for r in reports if r.ready_decision is not None]
    assert approved.entity_id == requirement.id
    assert approved.decision is ReadyDecisionKind.AUTO_APPROVE
    assert state_of(ws, requirement) == "Applied"


def test_a_full_page_of_decided_candidates_never_spins(monkeypatch, tmp_path):
    operator, ws, _requirement = exhausted(monkeypatch, tmp_path)
    with_projects(monkeypatch, ws, OTHER_PROJECT)
    crowd(ws, ELIGIBLE_QUERY_LIMIT, "p-2", "a0")
    decider = decider_for(operator)
    first, _ = drive(ws, NO_WORKERS, ELIGIBLE_QUERY_LIMIT + 2, ready_decider=decider)
    assert len(ready_decisions(first)) == ELIGIBLE_QUERY_LIMIT + 1

    reports, sleeps = drive(ws, NO_WORKERS, 6, ready_decider=decider)

    assert outcomes(reports) == [CycleOutcome.IDLE] * 6
    assert len(sleeps) == 6


def test_raw_processing_is_unaffected(monkeypatch, tmp_path):
    from processor_fake import FakeModelRuntime, build_workspace, model_output

    operator = Operator(tmp_path)
    operator.configure(DISABLED_TABLE + "\n" + READY)
    inner, raw, _ = build_workspace()
    ws = StatusWorkspace(inner)
    models = Models(
        raw=FakeModelRuntime([model_output([], reason="The source asks for nothing.")])
    )

    _, reports, _ = run_worker(monkeypatch, operator, ws, models)

    assert reports[0].dispatch_result.selection.route.worker is Worker.RAW_PROCESS
    assert reports[0].outcome is CycleOutcome.SUCCEEDED
    assert decisions(reports) == []
    assert ws.status_of(raw.id) == SUCCEEDED
    assert ((("Standard", "Ready"),), SUCCEEDED) in ws.queries


def test_the_human_admin_decisions_keep_their_established_behavior(
    monkeypatch, tmp_path
):
    _operator, ws, requirement = ready_at(monkeypatch, tmp_path, NEEDS_WORK_REVIEW)
    # A human may still approve NEEDS_WORK by acknowledging it by name.
    approved = approve_standard_requirement(
        ws.inner, requirement.id, ReviewVerdict.NEEDS_WORK
    )
    assert approved.code is ReadyCode.REQUIREMENT_APPROVED
    ws.inner.set_requirement_state(requirement.id, "Ready")
    # And send stale evidence back: rework certifies nothing.
    edit_root(ws)
    sent = rework_standard_requirement(ws.inner, requirement.id)
    assert sent.code is ReadyCode.REQUIREMENT_SENT_FOR_REWORK


def test_a_delegated_approval_can_never_acknowledge_a_verdict(monkeypatch, tmp_path):
    """The safety net under the classification: with a guard and no
    acknowledgement, the existing approval refuses anything but PASS."""
    _operator, ws, requirement = ready_at(monkeypatch, tmp_path, NEEDS_WORK_REVIEW)
    seen = []

    result = approve_standard_requirement(
        ws.inner, requirement.id, None, guard=lambda evidence: seen.append(evidence)
    )

    assert result.code is ReadyCode.VERDICT_ACKNOWLEDGEMENT_REQUIRED
    assert seen == []
    assert state_of(ws, requirement) == "Ready"


# -- auditability ------------------------------------------------------------------------------


def test_the_decision_report_is_complete_and_content_free(monkeypatch, tmp_path):
    operator, ws, requirement = started(tmp_path)
    models = reworks(FIRST, fixed_with(CLEARER))
    render = cli.render_cycle  # run_worker records through it from here on

    _, reports, _ = run_worker(monkeypatch, operator, ws, models)

    out, error_out = io.StringIO(), io.StringIO()
    for report in reports:
        render(report, out, error_out)
    text = out.getvalue() + error_out.getvalue()
    for line in (
        "Ready decision: AUTO_REWORK; transition CONFIRMED (REQUIREMENT_SENT_FOR_REWORK); State Process",
        "Ready decision: AUTO_APPROVE; transition CONFIRMED (REQUIREMENT_APPROVED); State Apply",
        f"Requirement: {requirement.requirement_id} (entity {requirement.id})",
        "Project: SDLC (entity p-1)",
        f"Authorization: SDLC-READY-1 {authorization().fingerprint}",
        "Evidence: Review Result 1 ",
        "Evidence: Review Result 2 ",
        "Verdict NEEDS_WORK; WHAT CLEAR",
        "Verdict PASS; WHAT CLEAR",
        "Progress: rework rounds used 1 of 2",
        "Reason: actionable R0001.F0",
        "Checked: every bound dependency is the version reviewed (WI-4)",
    ):
        assert line in text, line
    for secret in (
        FINDING["detail"],
        requirement.title,
        "The runtime must refuse",
        CLEARER["acceptance_verification"],
    ):
        assert secret not in text
