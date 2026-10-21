"""WI-5 correction: a running worker's autonomy policy lifetime.

Requirement-Autonomous-Resolution-v0.1 §3.4: a long-running worker reads the
policy again as each Standard stage starts, so its start-time policy is never
the authority for later work. Every scenario runs `sdlc worker run` itself —
the production composition, runner, dispatcher and stages — over the Fibery
and model fakes. The operator's configuration is a real `config/sdlc.toml` in
a temporary working directory, read by the real loader; a scenario edits it
while the worker keeps running. The policies are TEST-ONLY fixtures.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import replace
from pathlib import Path

import pytest

from processor_fake import FakeModelRuntime
from review_fake import review_output, verify_resolution
from sdlc import cli
from sdlc.autonomy_policy import (
    AutonomyPolicyError,
    load_autonomy_policies,
    policy_fingerprint,
)
from sdlc.model_runtime_config import (
    RAW_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_PROCESSOR_ROLE,
    STANDARD_REQUIREMENT_REVIEWER_ROLE,
)
from sdlc.requirement_dispatcher import DispatchOutcome, Worker
from sdlc.requirement_runner import CycleOutcome
from sdlc.results import ApplyResultCode as Apply
from sdlc.results import StandardProcessResultCode as ProcessCode
from sdlc.results import StandardReviewResultCode as ReviewCode
from sdlc.tsa_admission import AdmissionRefused, AdmissionResultCode
from standard_fake import analysis_output
from test_autonomous_resolution import (
    D1,
    ERROR_BODY,
    admit,
    artifacts,
    delegated_resolution,
    latest_process,
    latest_review,
    limit_resolution,
    peer_resolution,
    scene,
)
from test_cli_worker import ENVIRONMENT
from test_requirement_runner import (
    FAILED_STATUS,
    NOT_PROCESSED,
    POLL,
    SUCCEEDED,
    StatusWorkspace,
    only_eligible,
)

REPOSITORY_CONFIG = Path(__file__).resolve().parents[1] / "config" / "sdlc.toml"
AUTONOMY_TABLE = re.compile(r"^\[autonomy\]$", re.MULTILINE)
P1_ID = "SDLC-DEFAULTS-1"
P2_ID = "SDLC-DEFAULTS-2"
P2_CLAUSE = replace(ERROR_BODY, clause_id="ERR-BODY-2")
POLICY_FREE_PROMPT = "none approved for this Project"


def autonomy(
    *clauses,
    policy_id=P1_ID,
    project="SDLC",
    approved_by="Test operator",
    fingerprint=None,
):
    """An enabled `[autonomy]` table; approved as written unless told otherwise."""
    clauses = clauses or (ERROR_BODY,)
    approved = fingerprint or policy_fingerprint(project, policy_id, clauses)
    lines = [
        "[autonomy]",
        'mode = "enabled"',
        "",
        f"[autonomy.projects.{project}]",
        f"policy_id = {json.dumps(policy_id)}",
        f"approved_by = {json.dumps(approved_by)}",
        f"approved_fingerprint = {json.dumps(approved)}",
    ]
    for clause in clauses:
        lines += ["", f"[[autonomy.projects.{project}.clauses]]"]
        lines += [
            f"{key} = {json.dumps(list(value) if key == 'exclusions' else value)}"
            for key, value in clause.to_payload().items()
        ]
    return "\n".join(lines) + "\n"


P1 = autonomy()
P1_FINGERPRINT = policy_fingerprint("SDLC", P1_ID, (ERROR_BODY,))
P2 = autonomy(P2_CLAUSE, policy_id=P2_ID)
DISABLED_TABLE = '[autonomy]\nmode = "disabled"\n'

# Each operator change, and what the next stage must do with P1-bound work.
REVOKED = {
    "disabled": DISABLED_TABLE,
    "p2": P2,
    "removed": "",
    "other-project-only": autonomy(project="OTHER", policy_id="OTHER-1"),
}
BROKEN = {
    "malformed-toml": "[autonomy]\nmode = \n",
    "unknown-mode": '[autonomy]\nmode = "on"\n',
    "content-changed": autonomy(
        replace(ERROR_BODY, boundaries="Wording and status codes."),
        fingerprint=P1_FINGERPRINT,
    ),
    "approval-changed": autonomy(fingerprint="0" * 64),
    "unreadable": None,
}
CHANGES = {**REVOKED, **BROKEN}
# P1's id, re-approved over changed content: a new fingerprint, so a new policy.
REAPPROVED = autonomy(replace(ERROR_BODY, boundaries="Wording and status codes."))
STALE_FOR_BOUND_WORK = {**CHANGES, "p1-reapproved-changed": REAPPROVED}


class Operator:
    """The operator's `config/sdlc.toml`: the repository's own, `[autonomy]` swapped."""

    def __init__(self, root: Path):
        text = REPOSITORY_CONFIG.read_text(encoding="utf-8")
        self.runtime = AUTONOMY_TABLE.split(text, maxsplit=1)[0]
        self.path = root / "config" / "sdlc.toml"
        self.path.parent.mkdir()

    def configure(self, table):
        """Write `table` as the `[autonomy]` part; None leaves no readable file.

        A directory stands in its place: unreadable as a file even to root.
        """
        if self.path.is_dir():
            self.path.rmdir()
        if table is None:
            self.path.unlink(missing_ok=True)
            self.path.mkdir()
            return
        self.path.write_text(self.runtime + table, encoding="utf-8")


class Models:
    """One fake runtime per configured role; RAW processing never runs here."""

    def __init__(self, process=(), review=(), raw=None):
        raw = raw or FakeModelRuntime(error=AssertionError("no RAW model here"))
        self.by_role = {
            RAW_REQUIREMENT_PROCESSOR_ROLE: raw,
            STANDARD_REQUIREMENT_PROCESSOR_ROLE: FakeModelRuntime(list(process)),
            STANDARD_REQUIREMENT_REVIEWER_ROLE: FakeModelRuntime(list(review)),
        }

    @property
    def process(self):
        return self.by_role[STANDARD_REQUIREMENT_PROCESSOR_ROLE]

    @property
    def review(self):
        return self.by_role[STANDARD_REQUIREMENT_REVIEWER_ROLE]


def run_worker(monkeypatch, operator, ws, models, at_poll=None, loads=None, extra=()):
    """`sdlc worker run`, started under the current file, until its first idle wait.

    `at_poll[n]` runs just before the n-th eligible-work poll: the operator
    editing the file, or a human moving a Requirement in Fibery, while the
    worker keeps running. `loads`, when given, counts reads of the real loader.
    `extra` are further `worker run` arguments, such as `--project`.
    """
    monkeypatch.chdir(operator.path.parent.parent)
    for name, value in ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(cli, "_runner_workspace", lambda settings: ws)
    monkeypatch.setattr(cli, "LocalCliModelRuntime", lambda s: models.by_role[s.role])

    def stop(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "_sleep", stop)
    reports = []
    render = cli.render_cycle

    def recorded(report, out, error_out):
        reports.append(report)
        render(report, out, error_out)

    monkeypatch.setattr(cli, "render_cycle", recorded)
    if loads is not None:

        def counted(path=None):
            loads.append(path)
            return load_autonomy_policies(path)

        monkeypatch.setattr(cli, "load_autonomy_policies", counted)
    for poll, action in (at_poll or {}).items():
        ws.on_call[(POLL, poll)] = action
    arguments = cli.build_parser().parse_args(["worker", "run", *extra])
    out, error_out = io.StringIO(), io.StringIO()
    code = arguments.handler(arguments, out, error_out)
    return code, reports, error_out.getvalue()


def delegated_models(clause="ERR-BODY"):
    return Models(
        process=[analysis_output(resolutions=[delegated_resolution(clause)])],
        review=[
            review_output(resolution_verifications=[verify_resolution(delegated=True)])
        ],
    )


def to_apply_if_ready(ws, requirement):
    """A human bypassing the admin Ready decision: Ready -> Apply, in Fibery."""

    def act():
        if ws.inner.requirements[requirement.id].state == "Ready":
            ws.set_requirement_state(requirement.id, "Apply")

    return act


def both(*actions):
    def act():
        for action in actions:
            action()

    return act


def worker_results(reports, worker):
    return [
        report.dispatch_result.worker_result
        for report in reports
        if report.dispatch_result is not None
        and report.dispatch_result.selection.route.worker is worker
    ]


def relation_or_applied_writes(ws):
    return [
        m
        for m in ws.inner.mutations
        if m.startswith(("add_depends_on", "add_affects")) or m.endswith(" Applied")
    ]


def started(tmp_path, table=P1):
    operator = Operator(tmp_path)
    operator.configure(table)
    inner, requirement, _ = scene()
    return operator, only_eligible(inner, requirement.id), requirement


def bound_policy(ws):
    """The policy the latest Process Result bound, or None."""
    _, result = latest_process(ws)
    return result.autonomy_policy


def shown(call):
    """Everything one model invocation was shown."""
    return call["prompt"] + call["context"]


# -- the reported bypass, pinned ---------------------------------------------------


def test_regression_a_revoked_policy_never_reaches_applied_through_a_running_worker(
    monkeypatch, tmp_path
):
    """The reported sequence: the worker starts under P1, the operator disables
    delegation, the worker carries on, and a human moves Ready -> Apply in
    Fibery. Before the correction the start-time P1 authorized a new delegated
    default, confirmed it at Review and wrote Applied; TSA alone refused."""
    operator, ws, requirement = started(tmp_path)
    models = delegated_models()

    code, reports, _ = run_worker(
        monkeypatch,
        operator,
        ws,
        models,
        at_poll={
            1: lambda: operator.configure(DISABLED_TABLE),
            3: to_apply_if_ready(ws, requirement),
        },
    )

    assert code == cli.EXIT_INTERRUPTED
    [process] = worker_results(reports, Worker.STANDARD_PROCESS)
    assert process.code is ProcessCode.INVALID_MODEL_OUTPUT, process
    # The model was offered no policy at all, let alone the revoked P1.
    [call] = models.process.calls
    assert POLICY_FREE_PROMPT in shown(call)
    assert "[ERR-BODY]" not in shown(call) and P1_ID not in shown(call)
    assert artifacts(ws.inner, "Process Result") == []
    assert not models.review.was_invoked
    assert worker_results(reports, Worker.STANDARD_REVIEW) == []
    assert worker_results(reports, Worker.STANDARD_APPLY) == []
    assert ws.inner.requirements[requirement.id].state == "Process"
    assert ws.status_of(requirement.id) == FAILED_STATUS
    assert relation_or_applied_writes(ws) == []
    with pytest.raises(AdmissionRefused) as refused:
        admit(ws.inner, load_autonomy_policies(operator.path))
    assert refused.value.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE


# -- each machine stage, after each kind of change ----------------------------------


@pytest.mark.parametrize("change", list(CHANGES), ids=list(CHANGES))
def test_process_never_decides_under_a_policy_changed_before_it_started(
    monkeypatch, tmp_path, change
):
    operator, ws, requirement = started(tmp_path)
    models = delegated_models()

    _, reports, error_out = run_worker(
        monkeypatch,
        operator,
        ws,
        models,
        at_poll={1: lambda: operator.configure(CHANGES[change])},
    )

    [process] = worker_results(reports, Worker.STANDARD_PROCESS)
    if change in BROKEN:
        assert process.code is ProcessCode.AUTONOMY_POLICY_INVALID, process
        assert not models.process.was_invoked
        assert ProcessCode.AUTONOMY_POLICY_INVALID.value in error_out
    else:
        assert process.code is ProcessCode.INVALID_MODEL_OUTPUT, process
        [call] = models.process.calls
        assert "[ERR-BODY]" not in shown(call) and P1_ID not in shown(call)
    assert not process.is_normal
    assert artifacts(ws.inner, "Process Result") == []
    assert ws.inner.requirements[requirement.id].state == "Process"
    assert ws.status_of(requirement.id) == FAILED_STATUS
    # A refusal is one claimed cycle, marked Failed, never retried: one call at most.
    assert len(models.process.calls) <= 1 and not models.review.was_invoked


@pytest.mark.parametrize(
    "change", list(STALE_FOR_BOUND_WORK), ids=list(STALE_FOR_BOUND_WORK)
)
def test_review_never_confirms_a_default_whose_policy_changed_before_it_started(
    monkeypatch, tmp_path, change
):
    operator, ws, requirement = started(tmp_path)
    models = delegated_models()

    _, reports, _ = run_worker(
        monkeypatch,
        operator,
        ws,
        models,
        at_poll={2: lambda: operator.configure(STALE_FOR_BOUND_WORK[change])},
    )

    [process] = worker_results(reports, Worker.STANDARD_PROCESS)
    assert process.code is ProcessCode.REQUIREMENT_PROCESSED, process
    assert bound_policy(ws.inner).policy_id == P1_ID
    [review] = worker_results(reports, Worker.STANDARD_REVIEW)
    expected = (
        ReviewCode.AUTONOMY_POLICY_INVALID
        if change in BROKEN
        else ReviewCode.RESOLUTION_EVIDENCE_STALE
    )
    assert review.code is expected, review
    assert not models.review.was_invoked
    assert artifacts(ws.inner, "Review Result") == []
    assert ws.inner.requirements[requirement.id].state == "Review"
    assert ws.status_of(requirement.id) == FAILED_STATUS
    # The evidence stays bound to P1, exactly as persisted.
    assert bound_policy(ws.inner).fingerprint == P1_FINGERPRINT


@pytest.mark.parametrize(
    "change", list(STALE_FOR_BOUND_WORK), ids=list(STALE_FOR_BOUND_WORK)
)
def test_a_direct_ready_to_apply_move_cannot_apply_under_a_revoked_policy(
    monkeypatch, tmp_path, change
):
    operator, ws, requirement = started(tmp_path)
    models = delegated_models()

    _, reports, _ = run_worker(
        monkeypatch,
        operator,
        ws,
        models,
        at_poll={
            3: both(
                lambda: operator.configure(STALE_FOR_BOUND_WORK[change]),
                to_apply_if_ready(ws, requirement),
            )
        },
    )

    [review] = worker_results(reports, Worker.STANDARD_REVIEW)
    assert review.code is ReviewCode.REQUIREMENT_REVIEWED, review
    [apply] = worker_results(reports, Worker.STANDARD_APPLY)
    expected = (
        Apply.AUTONOMY_POLICY_INVALID
        if change in BROKEN
        else Apply.RESOLUTION_EVIDENCE_STALE
    )
    assert apply.code is expected, apply
    assert relation_or_applied_writes(ws) == []
    assert ws.inner.requirements[requirement.id].state == "Apply"
    assert ws.status_of(requirement.id) == FAILED_STATUS
    # After the human's move, the Apply cycle wrote only its claim and Failed.
    moved = ws.inner.mutations.index(f"set_requirement_state {requirement.id} Apply")
    assert ws.inner.mutations[moved + 1 :] == [
        f"set_processing_status {requirement.id} Processing",
        f"set_processing_status {requirement.id} Failed",
    ]
    if change not in BROKEN:
        with pytest.raises(AdmissionRefused) as refused:
            admit(ws.inner, load_autonomy_policies(operator.path))
        assert refused.value.code is AdmissionResultCode.REQUIREMENT_NOT_ADMISSIBLE


@pytest.mark.parametrize("change", list(BROKEN), ids=list(BROKEN))
def test_a_stage_that_ran_under_p1_never_falls_back_to_it(
    monkeypatch, tmp_path, change
):
    """The same stage, a second time in one worker life: the Process that read
    P1 for the first iteration has nothing to fall back to for the next."""
    operator, ws, requirement = started(tmp_path)
    models = delegated_models()

    def back_to_process():
        operator.configure(BROKEN[change])
        ws.set_requirement_state(requirement.id, "Process")

    _, reports, _ = run_worker(
        monkeypatch, operator, ws, models, at_poll={3: back_to_process}
    )

    first, second = worker_results(reports, Worker.STANDARD_PROCESS)
    assert first.code is ProcessCode.REQUIREMENT_PROCESSED, first
    assert second.code is ProcessCode.AUTONOMY_POLICY_INVALID, second
    assert len(models.process.calls) == 1
    assert len(artifacts(ws.inner, "Process Result")) == 1
    assert ws.inner.requirements[requirement.id].state == "Process"
    assert ws.status_of(requirement.id) == FAILED_STATUS


# -- what stays valid -----------------------------------------------------------------


def test_a_policy_current_throughout_still_applies_its_default(monkeypatch, tmp_path):
    operator, ws, requirement = started(tmp_path)
    models = delegated_models()

    _, reports, _ = run_worker(
        monkeypatch,
        operator,
        ws,
        models,
        at_poll={3: to_apply_if_ready(ws, requirement)},
    )

    assert [r.outcome for r in reports] == [
        CycleOutcome.HANDED_OFF,
        CycleOutcome.SUCCEEDED,
        CycleOutcome.SUCCEEDED,
        CycleOutcome.IDLE,
    ]
    [apply] = worker_results(reports, Worker.STANDARD_APPLY)
    assert apply.code is Apply.REQUIREMENT_APPLIED, apply
    assert ws.inner.requirements[requirement.id].state == "Applied"
    assert ws.status_of(requirement.id) == SUCCEEDED
    assert len(models.process.calls) == len(models.review.calls) == 1


def test_a_valid_new_policy_authorizes_later_work_bound_to_itself(
    monkeypatch, tmp_path
):
    operator, ws, requirement = started(tmp_path)
    models = delegated_models("ERR-BODY-2")

    _, reports, _ = run_worker(
        monkeypatch,
        operator,
        ws,
        models,
        at_poll={
            1: lambda: operator.configure(P2),
            3: to_apply_if_ready(ws, requirement),
        },
    )

    [call] = models.process.calls
    assert "[ERR-BODY-2]" in shown(call) and P2_ID in shown(call)
    bound = bound_policy(ws.inner)
    assert bound.policy_id == P2_ID
    assert bound.fingerprint == policy_fingerprint("SDLC", P2_ID, (P2_CLAUSE,))
    _, reviewed = latest_review(ws.inner)
    assert reviewed.reviewed_autonomy_policy == bound
    [apply] = worker_results(reports, Worker.STANDARD_APPLY)
    assert apply.code is Apply.REQUIREMENT_APPLIED, apply


def test_approved_by_is_a_record_not_authority(monkeypatch, tmp_path):
    """Changing who approved P1 leaves P1's approved content, and its authority,
    exactly as they were: it neither revokes P1 nor grants anything new."""
    operator, ws, requirement = started(tmp_path)
    renamed = autonomy(approved_by="Someone else entirely")

    _, reports, _ = run_worker(
        monkeypatch,
        operator,
        ws,
        delegated_models(),
        at_poll={
            2: lambda: operator.configure(renamed),
            3: to_apply_if_ready(ws, requirement),
        },
    )

    [apply] = worker_results(reports, Worker.STANDARD_APPLY)
    assert apply.code is Apply.REQUIREMENT_APPLIED, apply
    assert bound_policy(ws.inner).fingerprint == P1_FINGERPRINT


CONFIRMED_D1 = {
    "requirement_id": D1.requirement_id,
    "outcome": "CONFIRMED",
    "reason": "It owns the rule.",
}


@pytest.mark.parametrize(
    ("resolution", "peers", "dependencies"),
    [(limit_resolution(), (), []), (peer_resolution(), (D1,), [CONFIRMED_D1])],
    ids=["source-grounded", "dependency-grounded"],
)
def test_without_a_policy_grounded_resolutions_still_pass(
    monkeypatch, tmp_path, resolution, peers, dependencies
):
    operator = Operator(tmp_path)
    operator.configure(P1)
    inner, requirement, _ = scene(peers=peers, depends_on=peers)
    ws = only_eligible(inner, requirement.id)
    models = Models(
        process=[analysis_output(resolutions=[resolution])],
        review=[
            review_output(
                dependency_verifications=dependencies,
                resolution_verifications=[verify_resolution()],
            )
        ],
    )

    _, reports, _ = run_worker(
        monkeypatch,
        operator,
        ws,
        models,
        at_poll={1: lambda: operator.configure(DISABLED_TABLE)},
    )

    [review] = worker_results(reports, Worker.STANDARD_REVIEW)
    assert review.code is ReviewCode.REQUIREMENT_REVIEWED, review
    assert inner.requirements[requirement.id].state == "Ready"
    assert bound_policy(inner) is None


def test_an_idle_worker_reads_the_policy_only_at_start_and_runs_no_model(
    monkeypatch, tmp_path
):
    operator = Operator(tmp_path)
    operator.configure(P1)
    inner, _, _ = scene()
    ws = StatusWorkspace(inner, default=SUCCEEDED)
    models, loads = Models(), []

    _, reports, _ = run_worker(monkeypatch, operator, ws, models, loads=loads)

    assert [r.outcome for r in reports] == [CycleOutcome.IDLE]
    assert loads == [None]
    assert not models.process.was_invoked and not models.review.was_invoked


def test_each_standard_stage_reads_the_policy_once_as_it_starts(monkeypatch, tmp_path):
    operator, ws, requirement = started(tmp_path)
    loads = []

    run_worker(
        monkeypatch,
        operator,
        ws,
        delegated_models(),
        at_poll={3: to_apply_if_ready(ws, requirement)},
        loads=loads,
    )

    # Runner start, then Process, Review and Apply: one read each, no more.
    assert loads == [None] * 4


def test_a_broken_policy_refuses_the_runner_before_any_claim(monkeypatch, tmp_path):
    operator, ws, requirement = started(tmp_path, BROKEN["unknown-mode"])
    models = delegated_models()

    code, reports, error_out = run_worker(monkeypatch, operator, ws, models)

    assert code == cli.EXIT_FAILURE
    assert error_out.startswith("WORKER_RUNNER_CONFIGURATION_INVALID")
    assert reports == [] and ws.inner.mutations == []
    assert ws.status_of(requirement.id) == NOT_PROCESSED


def test_raw_processing_never_reads_the_policy(monkeypatch, tmp_path):
    """A RAW cycle completes under a configuration broken mid-run; the Standard
    candidate it creates is then refused, before its model is ever asked."""
    from processor_fake import build_workspace, candidate, model_output

    operator = Operator(tmp_path)
    operator.configure(P1)
    inner, raw, _ = build_workspace()
    ws = StatusWorkspace(inner)
    models = Models(raw=FakeModelRuntime([model_output([candidate()])]))

    _, reports, _ = run_worker(
        monkeypatch,
        operator,
        ws,
        models,
        at_poll={1: lambda: operator.configure(BROKEN["unknown-mode"])},
    )

    assert reports[0].dispatch_result.outcome is DispatchOutcome.ROUTE_COMPLETED
    assert ws.status_of(raw.id) == SUCCEEDED
    [produced] = inner.produces(raw.id)
    [process] = worker_results(reports, Worker.STANDARD_PROCESS)
    assert process.code is ProcessCode.AUTONOMY_POLICY_INVALID
    assert ws.status_of(produced) == FAILED_STATUS
    assert not models.process.was_invoked


# -- the loader ---------------------------------------------------------------------


def test_an_unreadable_configuration_is_a_policy_error(tmp_path):
    operator = Operator(tmp_path)
    operator.configure(None)
    with pytest.raises(AutonomyPolicyError, match="cannot be read"):
        load_autonomy_policies(operator.path)
    directory = tmp_path / "directory.toml"
    directory.mkdir()
    with pytest.raises(AutonomyPolicyError, match="cannot be read"):
        load_autonomy_policies(directory)


def test_a_refusal_names_no_policy_content(monkeypatch, tmp_path):
    operator, ws, _ = started(tmp_path)

    _, _, error_out = run_worker(
        monkeypatch,
        operator,
        ws,
        delegated_models(),
        at_poll={1: lambda: operator.configure(BROKEN["content-changed"])},
    )

    assert ProcessCode.AUTONOMY_POLICY_INVALID.value in error_out
    for text in (ERROR_BODY.permitted_decision, "Wording and status codes."):
        assert text not in error_out
