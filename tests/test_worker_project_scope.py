"""Requirement-Worker-Project-Scope-v0.1: `sdlc worker run --project CODE`.

The real runner, dispatcher, Ready decider and workers run over the Fibery
fakes of test_requirement_runner.py, with a second Project whose eligible
work has lower public ids than the scoped one's: exactly the TSAP1 / ARP1
situation of the live workspace. `Projects` gives a fake the Project table a
live workspace has, so the scope is resolved and re-read as it is live.
None of this is evidence of how Fibery evaluates the Project filter.
"""

from __future__ import annotations

import dataclasses
import functools

import pytest

from processor_fake import (
    FakeModelRuntime,
    FakeProcessorWorkspace,
    build_workspace,
    candidate,
    model_output,
)
from review_fake import confirm, review_output
from sdlc import cli
from sdlc.autonomous_ready import ReadyDecider, ReadyDecisionKind, Transition
from sdlc.autonomy_policy import load_autonomy_policies
from sdlc.fibery_http import ELIGIBLE_QUERY_LIMIT
from sdlc.fibery_workspace import FiberyError, ProjectRecord, RequirementRecord
from sdlc.raw_processor import process_raw_requirement
from sdlc.ready_delegation import load_ready_delegation
from sdlc.requirement_dispatcher import (
    DispatchOutcome,
    RequirementWorkers,
)
from sdlc.requirement_runner import (
    MACHINE_ROUTES,
    CycleOutcome,
    ProjectScope,
    ProjectScopeError,
    RunnerCode,
    check_project_scope,
    resolve_project_scope,
    run_cycle,
    run_requirement_runner,
)
from sdlc.worker_runner_guard import hold_workspace
from standard_fake import analysis_output
from test_autonomous_ready import (
    CLEARER,
    FINDING,
    PASS_REVIEW,
    READY_DISABLED,
    authorization,
    crowd,
    ready_at,
    ready_decisions,
    ready_table,
    state_of,
)
from test_autonomous_resolution import scene
from test_cli_worker import run_worker as run_cli_worker
from test_fibery_http import ok
from test_requirement_runner import (
    NO_WORKERS,
    NOT_PROCESSED,
    PROCESSING,
    SUCCEEDED,
    CompletingWorkers,
    StatusWorkspace,
    http_workspace,
    requirement_row,
    sent,
    unexpected,
)
from test_worker_policy_lifetime import DISABLED_TABLE, Models, Operator
from test_worker_policy_lifetime import run_worker as run_policy_worker

ARP1 = ProjectRecord(
    id="p-arp1",
    name="Autonomous Requirements Pilot 1",
    code="ARP1",
    state="Planned",
    public_id="501",
)
TSAP1 = ProjectRecord(
    id="p-tsap1",
    name="TSA P-1 SCRATCH",
    code="TSAP1",
    state="Planned",
    public_id="502",
)
# (Type, State) of the four machine routes, with the State a success leaves.
ROUTE_STATES = [
    ("Raw", "Process"),
    ("Standard", "Process"),
    ("Standard", "Review"),
    ("Standard", "Apply"),
]


class Projects:
    """The workspace's Project table, installed on a fake; edits are live.

    `failing` makes every Project read raise, as an unavailable Fibery does.
    """

    def __init__(self, *projects):
        self.by_id = {project.id: project for project in projects}
        self.failing = False
        self.reads = 0

    def install(self, monkeypatch, inner):
        monkeypatch.setattr(inner, "read_project", self.read_project, raising=False)
        monkeypatch.setattr(
            inner, "find_project_by_code", self.find_project_by_code, raising=False
        )
        monkeypatch.setattr(
            inner,
            "count_projects_with_code",
            self.count_projects_with_code,
            raising=False,
        )
        return self

    def _read(self):
        self.reads += 1
        if self.failing:
            raise FiberyError("Fibery is unavailable")

    def read_project(self, project_id):
        self._read()
        return self.by_id.get(project_id)

    def find_project_by_code(self, code):
        self._read()
        return next((p for p in self.by_id.values() if p.code == code), None)

    def count_projects_with_code(self, code):
        """Bounded to two, as the live query is: enough to see ambiguity."""
        self._read()
        return min(2, sum(p.code == code for p in self.by_id.values()))

    def recode(self, project_id, code):
        self.by_id[project_id] = dataclasses.replace(self.by_id[project_id], code=code)


def req(entity_id, public_id, type_name, state, project, prefix=None):
    code = prefix or project.code
    kind = "RAW" if type_name == "Raw" else "FR"
    return RequirementRecord(
        id=entity_id,
        public_id=str(public_id),
        requirement_id=f"{code}-{kind}-{int(public_id):04d}",
        title=None,
        type_name=type_name,
        state=state,
        revision=1,
        project_id=project.id,
        source_fingerprint=None,
    )


def two_projects(monkeypatch, routes=ROUTE_STATES):
    """TSAP1 work at public ids 1.., ARP1 work at 50..; all Not Processed."""
    records = [
        req(f"t-{n}", n + 1, type_name, state, TSAP1)
        for n, (type_name, state) in enumerate(routes)
    ] + [
        req(f"a-{n}", n + 50, type_name, state, ARP1)
        for n, (type_name, state) in enumerate(routes)
    ]
    inner = FakeProcessorWorkspace(ARP1, records)
    projects = Projects(ARP1, TSAP1).install(monkeypatch, inner)
    return StatusWorkspace(inner), projects


def foreign(ws):
    return {e: r for e, r in ws.inner.requirements.items() if r.project_id == TSAP1.id}


def naming(mutations, ids):
    """The mutations whose log line names one of these entities."""
    return [m for m in mutations if set(m.replace("->", " ").split()) & set(ids)]


def untouched(ws, before):
    """No TSAP1 State, status, Document or relation was written."""
    ids = set(before)
    assert {e: ws.inner.requirements[e] for e in ids} == before
    assert all(ws.status_of(e) == NOT_PROCESSED for e in ids)
    assert naming(ws.inner.mutations, ids) == []


def drive_until_stopped(ws, workers, cycles, **options):
    reports, sleeps = [], []
    remaining = iter(range(cycles))
    stopped = None
    try:
        run_requirement_runner(
            ws,
            workers,
            sleep=sleeps.append,
            report=reports.append,
            should_continue=lambda: next(remaining, None) is not None,
            **options,
        )
    except ProjectScopeError as error:
        stopped = error
    return reports, sleeps, stopped


# -- L, Y: resolving the scope ------------------------------------------------------------


def test_an_exact_code_resolves_to_the_entity_code_and_workspace(monkeypatch):
    ws, _ = two_projects(monkeypatch)

    scope = resolve_project_scope(ws, "ARP1")

    assert scope == ProjectScope("p-arp1", "ARP1", ws.lock_scope)


@pytest.mark.parametrize(
    "selector",
    ["arp1", " ARP1", "ARP1 ", "ARP", "Autonomous Requirements Pilot 1", "", "ZZZ9"],
    ids=[
        "lowercase",
        "leading-space",
        "trailing-space",
        "partial",
        "name",
        "empty",
        "unknown",
    ],
)
def test_anything_but_one_exact_code_is_refused(monkeypatch, selector):
    ws, _ = two_projects(monkeypatch)

    with pytest.raises(ProjectScopeError):
        resolve_project_scope(ws, selector)
    assert ws.polls == 0 and ws.inner.mutations == []


def test_an_ambiguous_code_is_refused(monkeypatch):
    ws, projects = two_projects(monkeypatch)
    projects.by_id["p-twin"] = dataclasses.replace(ARP1, id="p-twin")

    with pytest.raises(ProjectScopeError, match="More than one"):
        resolve_project_scope(ws, "ARP1")


def test_a_project_that_does_not_read_back_the_same_is_refused(monkeypatch):
    ws, _ = two_projects(monkeypatch)
    recoded_project = dataclasses.replace(ARP1, code="ARP2")
    monkeypatch.setattr(ws.inner, "read_project", lambda _id: recoded_project)
    monkeypatch.setattr(ws.inner, "find_project_by_code", lambda _code: ARP1)

    with pytest.raises(ProjectScopeError, match="same Project"):
        resolve_project_scope(ws, "ARP1")


def test_a_read_failure_never_falls_back_to_the_whole_workspace(monkeypatch):
    ws, projects = two_projects(monkeypatch)
    projects.failing = True

    with pytest.raises(ProjectScopeError, match="could not be resolved"):
        resolve_project_scope(ws, "ARP1")


@pytest.mark.parametrize("failure", ["unknown", "lowercase", "unreadable", "ambiguous"])
def test_the_command_refuses_an_invalid_scope_before_any_poll(monkeypatch, failure):
    ws, projects = two_projects(monkeypatch)
    selector = {"lowercase": "arp1"}.get(failure, "ARP1")
    if failure == "unknown":
        del projects.by_id["p-arp1"]
    if failure == "unreadable":
        projects.failing = True
    if failure == "ambiguous":
        projects.by_id["p-twin"] = dataclasses.replace(ARP1, id="p-twin")

    code, out, error_out, sleeps, _, _ = run_cli_worker(
        monkeypatch, ws, "--project", selector
    )

    assert code == cli.EXIT_FAILURE
    assert error_out.startswith(f"{RunnerCode.WORKER_RUNNER_PROJECT_INVALID.value}\n")
    assert RunnerCode.WORKER_RUNNER_STARTED.value not in out
    assert ws.polls == 0 and ws.project_filters == [] and sleeps == []
    assert ws.inner.mutations == []


def test_the_command_reports_the_scope_it_runs_under(monkeypatch):
    ws, _ = two_projects(monkeypatch, routes=[])

    code, out, _, _, _, _ = run_cli_worker(monkeypatch, ws, "--project", "ARP1")

    assert code == cli.EXIT_INTERRUPTED
    assert "Watching only Project ARP1 (entity p-arp1)" in out
    assert ws.project_filters == ["p-arp1"]


def test_the_workspace_lock_is_unchanged_under_a_scope(monkeypatch):
    ws, _ = two_projects(monkeypatch)

    with hold_workspace(ws.lock_scope):
        code, _, error_out, _, _, _ = run_cli_worker(
            monkeypatch, ws, "--project", "ARP1"
        )

    assert code == cli.EXIT_FAILURE
    assert error_out.startswith(f"{RunnerCode.WORKER_RUNNER_BUSY.value}\n")
    assert ws.polls == 0 and ws.inner.mutations == []


# -- A-F, U: machine routes -----------------------------------------------------------------


def test_a_scoped_runner_works_only_on_its_project(monkeypatch):
    ws, _ = two_projects(monkeypatch)
    before = foreign(ws)
    workers = CompletingWorkers(ws)
    scope = resolve_project_scope(ws, "ARP1")

    reports, _, stopped = drive_until_stopped(ws, workers.bound(), 12, scope=scope)

    assert stopped is None
    assert {entity for _, entity, _ in workers.calls} == {"a-0", "a-1", "a-2", "a-3"}
    assert all(
        r.requirement is None or r.requirement.project_id == ARP1.id for r in reports
    )
    assert set(ws.project_filters) == {"p-arp1"}
    untouched(ws, before)


def test_an_unscoped_runner_still_takes_the_lowest_id_of_every_project(monkeypatch):
    ws, _ = two_projects(monkeypatch)
    workers = CompletingWorkers(ws)

    run_cycle(ws, workers.bound())

    assert workers.calls[0][1] == "t-0"
    assert ws.project_filters == [None]


# -- R, T: pages ------------------------------------------------------------------------------


def test_more_than_a_page_of_scoped_work_behind_foreign_work_is_all_done(monkeypatch):
    """150 lower-id TSAP1 rows fill the global first page; Fibery filters
    before the limit, so all 150 ARP1 rows are reached."""
    count = ELIGIBLE_QUERY_LIMIT + 50
    records = [
        req(f"t-{n:04d}", n + 1, "Standard", "Apply", TSAP1) for n in range(count)
    ]
    records += [
        req(f"a-{n:04d}", n + 1000, "Standard", "Apply", ARP1) for n in range(count)
    ]
    inner = FakeProcessorWorkspace(ARP1, records)
    Projects(ARP1, TSAP1).install(monkeypatch, inner)
    ws = StatusWorkspace(inner)
    before = foreign(ws)
    workers = CompletingWorkers(ws)

    reports, _, stopped = drive_until_stopped(
        ws, workers.bound(), count + 1, scope=resolve_project_scope(ws, "ARP1")
    )

    assert stopped is None
    assert len(workers.calls) == count
    assert {e for _, e, _ in workers.calls} == {f"a-{n:04d}" for n in range(count)}
    assert reports[-1].outcome is CycleOutcome.IDLE
    untouched(ws, before)


# -- M-Q: the Project, and the Requirement, before claim and before dispatch -----------------


def scoped_cycle(monkeypatch, at, change):
    """One ARP1 Apply candidate behind a TSAP1 one; `change` runs before `at`."""
    ws, projects = two_projects(monkeypatch, routes=[("Standard", "Apply")])
    ws.on_call[at] = functools.partial(change, ws, projects)
    workers = CompletingWorkers(ws)
    scope = resolve_project_scope(ws, "ARP1")
    reports, _, stopped = drive_until_stopped(ws, workers.bound(), 3, scope=scope)
    return ws, workers, reports, stopped


def recoded(ws, projects):
    projects.recode("p-arp1", "ARP2")


def removed(ws, projects):
    del projects.by_id["p-arp1"]


def unreadable(ws, projects):
    projects.failing = True


def moved(ws, projects):
    ws.inner.requirements["a-0"] = dataclasses.replace(
        ws.inner.requirements["a-0"], project_id=TSAP1.id
    )


# The fresh re-read is the cycle's first read_requirement; the claim is its
# first status write, and its read-back the second read_requirement.
BEFORE_CLAIM = ("read_requirement", 1)
BEFORE_CLAIM_READBACK = ("read_requirement", 2)
BEFORE_DISPATCHER_READ = ("read_requirement", 3)


@pytest.mark.parametrize("change", [recoded, removed, unreadable])
def test_a_project_change_before_the_claim_stops_the_runner_unclaimed(
    monkeypatch, change
):
    ws, workers, reports, stopped = scoped_cycle(monkeypatch, BEFORE_CLAIM, change)

    assert isinstance(stopped, ProjectScopeError)
    assert [r.outcome for r in reports] == [CycleOutcome.SCOPE_INVALID]
    assert workers.calls == []
    assert ws.inner.mutations == []


@pytest.mark.parametrize("change", [recoded, removed, unreadable])
def test_a_project_change_before_the_dispatch_stops_the_runner_undispatched(
    monkeypatch, change
):
    ws, workers, reports, stopped = scoped_cycle(
        monkeypatch, ("set_processing_status", 1), change
    )

    assert isinstance(stopped, ProjectScopeError)
    [report] = reports
    assert report.outcome is CycleOutcome.SCOPE_INVALID
    assert "explicit recovery" in report.message
    assert workers.calls == []
    # Only this cycle's own claim was written, on an ARP1 Requirement.
    assert ws.inner.mutations == ["set_processing_status a-0 Processing"]
    assert ws.status_of("a-0") == PROCESSING


def test_a_requirement_moved_out_before_the_claim_is_left_alone(monkeypatch):
    ws, workers, reports, stopped = scoped_cycle(monkeypatch, BEFORE_CLAIM, moved)

    assert stopped is None
    assert reports[0].outcome is CycleOutcome.CANDIDATE_CHANGED
    assert "outside the scope" in " ".join(reports[0].details)
    assert workers.calls == []
    assert ws.inner.mutations == []
    # It is TSAP1's now: no later cycle of this runner sees it.
    assert [r.outcome for r in reports[1:]] == [CycleOutcome.IDLE] * 2


def test_a_requirement_moved_out_before_the_claim_read_back_is_not_dispatched(
    monkeypatch,
):
    ws, workers, reports, stopped = scoped_cycle(
        monkeypatch, BEFORE_CLAIM_READBACK, moved
    )

    assert stopped is None
    assert reports[0].outcome is CycleOutcome.CLAIM_NOT_CONFIRMED
    assert workers.calls == []
    assert ws.inner.mutations == ["set_processing_status a-0 Processing"]


@pytest.mark.parametrize("scoped", [True, False], ids=["scoped", "unscoped"])
def test_a_requirement_moved_before_the_dispatchers_read_runs_no_worker(
    monkeypatch, scoped
):
    """V: the dispatcher's own last read refuses Project drift, scoped or not."""
    ws, projects = two_projects(monkeypatch, routes=[("Standard", "Apply")])
    del ws.inner.requirements["t-0"]
    ws.on_call[BEFORE_DISPATCHER_READ] = functools.partial(moved, ws, projects)
    workers = CompletingWorkers(ws)
    scope = resolve_project_scope(ws, "ARP1") if scoped else None

    report = run_cycle(ws, workers.bound(), scope=scope)

    assert report.dispatch_result.outcome is DispatchOutcome.STALE_ROUTE
    assert "Project" in " ".join(report.dispatch_result.details)
    assert workers.calls == []


def test_a_scope_check_reads_the_project_only_when_there_is_work(monkeypatch):
    ws, projects = two_projects(monkeypatch, routes=[])
    scope = resolve_project_scope(ws, "ARP1")
    reads = projects.reads

    drive_until_stopped(ws, NO_WORKERS, 5, scope=scope)

    assert projects.reads == reads


def test_another_workspace_never_satisfies_the_scope(monkeypatch):
    ws, _ = two_projects(monkeypatch)
    scope = dataclasses.replace(
        resolve_project_scope(ws, "ARP1"), workspace_identity="other.fibery.io/x"
    )

    with pytest.raises(ProjectScopeError, match="workspace"):
        check_project_scope(ws, scope)


# -- G, W: RAW decomposition -------------------------------------------------------------------


def raw_scene(monkeypatch):
    """The fixture RAW in Process, now in ARP1, behind lower-id TSAP1 work."""
    inner, raw, _ = build_workspace()
    inner.project = dataclasses.replace(ARP1, id=raw.project_id)
    for n, (type_name, state) in enumerate(ROUTE_STATES):
        inner.requirements[f"t-{n}"] = req(f"t-{n}", n + 1, type_name, state, TSAP1)
    Projects(inner.project, TSAP1).install(monkeypatch, inner)
    return StatusWorkspace(inner), raw


def test_a_scoped_raw_creates_and_progresses_only_its_own_candidates(monkeypatch):
    ws, raw = raw_scene(monkeypatch)
    before = foreign(ws)
    model = FakeModelRuntime([model_output([candidate(), candidate(title="Second")])])
    workers = RequirementWorkers(
        functools.partial(process_raw_requirement, ws, model),
        unexpected,
        unexpected,
        unexpected,
    )

    report = run_cycle(ws, workers, scope=resolve_project_scope(ws, "ARP1"))

    assert report.outcome is CycleOutcome.SUCCEEDED, report
    produced = ws.inner.produces(raw.id)
    assert len(produced) == 2
    for entity in produced:
        created = ws.inner.requirements[entity]
        assert created.project_id == raw.project_id
        assert created.state == "Process"
        assert [r.id for r in ws.inner.derived_from(entity)] == [raw.id]
    untouched(ws, before)


def test_a_candidate_of_another_project_is_never_progressed(monkeypatch):
    """W: progression refuses a named candidate that is not in the RAW's Project."""
    ws, raw = raw_scene(monkeypatch)
    model = FakeModelRuntime([model_output([candidate(), candidate(title="Second")])])

    def process_then_move(entity_id):
        result = process_raw_requirement(ws, model, entity_id)
        [first, *_] = ws.inner.produces(raw.id)
        ws.inner.requirements[first] = dataclasses.replace(
            ws.inner.requirements[first], project_id=TSAP1.id
        )
        return result

    workers = RequirementWorkers(process_then_move, unexpected, unexpected, unexpected)

    report = run_cycle(ws, workers, scope=resolve_project_scope(ws, "ARP1"))

    assert report.dispatch_result.outcome is (
        DispatchOutcome.CANDIDATE_PROGRESSION_CONFLICT
    )
    assert "belongs to Project" in " ".join(report.dispatch_result.details)
    assert all(
        ws.inner.requirements[e].state == "Draft" for e in ws.inner.produces(raw.id)
    )


# -- H-K, X: Standard Process, Review, Ready and Apply with the real workers ------------------


def pilot_scene(tmp_path, ready):
    """The Ready e2e fixture (Project SDLC, entity p-1) beside TSAP1, whose
    machine work and Ready + Succeeded rows all have lower ids."""
    operator = Operator(tmp_path)
    operator.configure(DISABLED_TABLE + "\n" + ready)
    inner, requirement, _ = scene()
    pilot = ProjectRecord(
        id="p-1", name="SDLC", code="SDLC", state="Planned", public_id="9"
    )
    ws = StatusWorkspace(inner, {requirement.id: NOT_PROCESSED}, default=SUCCEEDED)
    for n, (type_name, state) in enumerate([*ROUTE_STATES, ("Standard", "Ready")]):
        inner.requirements[f"t-{n}"] = req(f"t-{n}", n + 1, type_name, state, TSAP1)
        ws.statuses[f"t-{n}"] = SUCCEEDED if state == "Ready" else NOT_PROCESSED
    return operator, ws, requirement, pilot


def test_scoped_process_review_rework_approve_and_apply_reach_applied(
    monkeypatch, tmp_path
):
    """H-K: both Projects are delegated; only the scoped one is ever touched."""
    ready = ready_table(
        authorization(),
        authorization(project="TSAP1", authorization_id="TSAP1-READY-1"),
    )
    operator, ws, requirement, pilot = pilot_scene(tmp_path, ready)
    Projects(pilot, TSAP1).install(monkeypatch, ws.inner)
    before = foreign(ws)
    models = Models(
        process=[
            analysis_output(findings=[FINDING]),
            analysis_output(
                normalized_changes=CLEARER,
                rework=[
                    {
                        "item": "R0001.F0",
                        "outcome": "RESOLVED",
                        "explanation": "Corrected from the source.",
                    }
                ],
            ),
        ],
        review=[
            review_output(finding_verifications=[confirm(0, "WARNING")]),
            review_output(
                rework_verifications=[
                    {
                        "item": "R0001.F0",
                        "outcome": "CONFIRMED",
                        "reason": "Checked against the source.",
                    }
                ]
            ),
        ],
    )

    code, reports, errors = run_policy_worker(
        monkeypatch, operator, ws, models, extra=("--project", "SDLC")
    )

    assert code == cli.EXIT_INTERRUPTED, errors
    assert state_of(ws, requirement) == "Applied"
    kinds = [r.ready_decision.decision for r in reports if r.ready_decision]
    assert kinds == [ReadyDecisionKind.AUTO_REWORK, ReadyDecisionKind.AUTO_APPROVE]
    assert all(
        r.ready_decision.transition is Transition.CONFIRMED
        for r in reports
        if r.ready_decision
    )
    assert all(
        r.requirement is None or r.requirement.project_id == "p-1" for r in reports
    )
    assert set(ws.project_filters) == {"p-1"}
    assert {e: ws.inner.requirements[e] for e in before} == before
    assert all(ws.status_of(e) == ws.statuses[e] for e in before)
    assert naming(ws.inner.mutations, before) == []


def test_a_scoped_runner_with_ready_disabled_makes_no_ready_query(
    monkeypatch, tmp_path
):
    operator, ws, requirement, pilot = pilot_scene(tmp_path, READY_DISABLED)
    Projects(pilot, TSAP1).install(monkeypatch, ws.inner)
    models = Models(
        process=[analysis_output(findings=[FINDING])],
        review=[review_output(finding_verifications=[confirm(0, "INFO")])],
    )

    code, reports, errors = run_policy_worker(
        monkeypatch, operator, ws, models, extra=("--project", "SDLC")
    )

    assert code == cli.EXIT_INTERRUPTED, errors
    assert state_of(ws, requirement) == "Ready"
    assert ws.inner.calls.count("find_eligible_requirements_after") == 0
    assert not [r for r in reports if r.ready_decision]


# -- S: Ready pages and the Ready scope ---------------------------------------------------------


def scoped_decider(operator, ws):
    scope = resolve_project_scope(ws, "SDLC")
    return ReadyDecider(
        lambda: load_ready_delegation(operator.path),
        lambda: load_autonomy_policies(operator.path),
        scope,
    )


def test_more_than_a_page_of_scoped_ready_candidates_behind_foreign_ones(
    monkeypatch, tmp_path
):
    ready = ready_table(
        authorization(),
        authorization(project="TSAP1", authorization_id="TSAP1-READY-1"),
    )
    operator, ws, requirement = ready_at(
        monkeypatch, tmp_path, PASS_REVIEW, ready=ready
    )
    pilot = ProjectRecord(
        id="p-1", name="SDLC", code="SDLC", state="Planned", public_id="9"
    )
    Projects(pilot, TSAP1).install(monkeypatch, ws.inner)
    crowd(ws, ELIGIBLE_QUERY_LIMIT + 50, TSAP1.id, "a0")
    crowd(ws, ELIGIBLE_QUERY_LIMIT + 50, "p-1", "b0")
    ws.project_filters.clear()  # the unscoped setup run's own queries
    decider = scoped_decider(operator, ws)
    workers = CompletingWorkers(ws)
    count = ELIGIBLE_QUERY_LIMIT + 50

    reports, _, stopped = drive_until_stopped(
        ws,
        workers.bound(),
        count + 6,
        ready_decider=decider,
        scope=resolve_project_scope(ws, "SDLC"),
    )

    assert stopped is None
    decided = ready_decisions(reports)
    assert len(decided) == len(set(decided)) == count + 1
    assert not [e for e in decided if e.startswith("a0-")]
    assert requirement.id in decided
    assert state_of(ws, requirement) == "Applied"
    assert set(ws.project_filters) == {"p-1"}


def test_a_ready_candidate_moved_out_of_the_scope_is_never_decided(
    monkeypatch, tmp_path
):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    pilot = ProjectRecord(
        id="p-1", name="SDLC", code="SDLC", state="Planned", public_id="9"
    )
    Projects(pilot, TSAP1).install(monkeypatch, ws.inner)
    decider = scoped_decider(operator, ws)
    before = len(ws.inner.mutations)

    def move():
        ws.inner.requirements[requirement.id] = dataclasses.replace(
            ws.inner.requirements[requirement.id], project_id=TSAP1.id
        )

    ws.on_call[("read_requirement", ws.inner.calls.count("read_requirement") + 1)] = (
        move
    )
    report = decider(ws)

    assert report.outcome is CycleOutcome.CANDIDATE_CHANGED
    assert "outside the scope" in " ".join(report.details)
    assert ws.inner.mutations[before:] == []


def test_a_project_code_change_stops_ready_decisions(monkeypatch, tmp_path):
    operator, ws, requirement = ready_at(monkeypatch, tmp_path, PASS_REVIEW)
    pilot = ProjectRecord(
        id="p-1", name="SDLC", code="SDLC", state="Planned", public_id="9"
    )
    projects = Projects(pilot, TSAP1).install(monkeypatch, ws.inner)
    decider = scoped_decider(operator, ws)
    projects.recode("p-1", "SDLC2")
    before = len(ws.inner.mutations)

    reports, _, stopped = drive_until_stopped(
        ws,
        NO_WORKERS,
        3,
        ready_decider=decider,
        scope=ProjectScope("p-1", "SDLC", ws.lock_scope),
    )

    assert isinstance(stopped, ProjectScopeError)
    assert [r.outcome for r in reports] == [CycleOutcome.SCOPE_INVALID]
    assert ws.inner.mutations[before:] == []
    assert state_of(ws, requirement) == "Ready"


# -- the live adapter's query shape, against a stub transport ------------------------------


@pytest.mark.parametrize("method", ["machine", "ready"])
def test_http_a_scoped_query_adds_one_exact_project_clause_to_the_same_filter(method):
    """The unscoped query is pinned in test_requirement_runner.py; the scoped
    one is that query plus exactly one Project clause, filtered by Fibery."""
    workspace, opener = http_workspace([ok([]), ok([requirement_row()])])
    routes = MACHINE_ROUTES if method == "machine" else (("Standard", "Ready"),)
    status = NOT_PROCESSED if method == "machine" else SUCCEEDED

    if method == "machine":
        workspace.find_eligible_requirements(routes, status)
        workspace.find_eligible_requirements(routes, status, project_id="p-arp1")
    else:
        workspace.find_eligible_requirements_after(routes, status, "r0")
        workspace.find_eligible_requirements_after(
            routes, status, "r0", project_id="p-arp1"
        )

    unscoped, scoped = sent(opener, 1)["args"], sent(opener, 2)["args"]
    clause = ["=", ["SDLC/Project", "fibery/id"], "$project"]
    connective, *clauses = scoped["query"]["q/where"]
    assert connective == unscoped["query"]["q/where"][0] == "q/and"
    assert clauses.count(clause) == 1
    assert [c for c in clauses if c != clause] == unscoped["query"]["q/where"][1:]
    assert scoped["params"] == {**unscoped["params"], "$project": "p-arp1"}
    for key in ("q/from", "q/select", "q/order-by", "q/limit"):
        assert scoped["query"][key] == unscoped["query"][key]
    assert scoped["query"]["q/limit"] == ELIGIBLE_QUERY_LIMIT
    assert clause not in unscoped["query"]["q/where"]


def test_a_rename_after_the_scope_check_never_borrows_another_codes_authority(
    monkeypatch, tmp_path
):
    """The Project is renamed, to a Code with its own Ready authorization,
    between the scope check and the decision's own Project read."""
    ready = ready_table(
        authorization(),
        authorization(project="OTHER", authorization_id="OTHER-READY-1"),
    )
    operator, ws, requirement = ready_at(
        monkeypatch, tmp_path, PASS_REVIEW, ready=ready
    )
    pilot = ProjectRecord(
        id="p-1", name="SDLC", code="SDLC", state="Planned", public_id="9"
    )
    projects = Projects(pilot, TSAP1).install(monkeypatch, ws.inner)
    decider = scoped_decider(operator, ws)
    reads = projects.reads
    real = projects.read_project

    def renamed_after_the_check(project_id):
        found = real(project_id)
        if projects.reads == reads + 1:
            projects.recode("p-1", "OTHER")
        return found

    monkeypatch.setattr(ws.inner, "read_project", renamed_after_the_check)
    before = len(ws.inner.mutations)

    report = decider(ws)

    assert report.outcome is CycleOutcome.SCOPE_INVALID
    assert report.ready_decision is None
    assert ws.inner.mutations[before:] == []
    assert state_of(ws, requirement) == "Ready"
