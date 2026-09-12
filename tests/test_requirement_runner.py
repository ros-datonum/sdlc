"""RW-O03: the state-driven Requirement runner behind `sdlc worker run`.

The runner composes the verified RW-O02 dispatcher. These tests pin what it
adds: the bounded poll, the fresh re-read, the confirmed Processing claim and
the status finalization, including the Standard Process -> Review handoff to
the Fibery reset automation. `StatusWorkspace` adds the Processing Status
field and a model of the RW-C04 reset rule to the existing Fibery fakes, so
the real workers run on them unchanged. The Fibery HTTP adapter's Processing
Status operations are pinned at the end against a stub transport.

None of this is evidence that a live workspace has the field or the rule.
"""

from __future__ import annotations

import copy
import dataclasses
import functools

import pytest

from apply_fake import build_apply_workspace, proposal
from processor_fake import (
    FakeModelRuntime,
    FakeProcessorWorkspace,
    build_workspace,
    candidate,
    model_output,
)
from review_fake import build_review_workspace, confirm, finding, review_output
from sdlc.fibery_client import FiberyClient
from sdlc.fibery_http import ELIGIBLE_QUERY_LIMIT, FiberyRawProcessorWorkspace
from sdlc.fibery_workspace import FiberyError, ProjectRecord, RequirementRecord
from sdlc.raw_processor import process_raw_requirement
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.requirement_dispatcher import (
    ROUTES,
    DispatchOutcome,
    DispatchResult,
    ProcessingStatus,
    RequirementWorkers,
    Worker,
    select_route,
)
from sdlc.requirement_runner import (
    DEFAULT_POLL_INTERVAL_SECONDS,
    MACHINE_ROUTES,
    MINIMUM_POLL_INTERVAL_SECONDS,
    PROCESSING_STATUS_OPTIONS,
    CycleOutcome,
    RunnerPreflightError,
    finalize_cycle,
    run_cycle,
    run_requirement_runner,
)
from sdlc.results import ProcessResult, ProcessResultCode
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import analysis_output, build_standard_workspace
from test_fibery_http import SETTINGS, StubOpener, ok, unpaced
from test_fibery_requirement_http import REQUIREMENT_SCHEMA
from test_requirement_dispatcher import FAILED, NORMAL, FakeWorkers

NOT_PROCESSED = "Not Processed"
PROCESSING = "Processing"
SUCCEEDED = "Succeeded"
FAILED_STATUS = "Failed"
FOUR_OPTIONS = (NOT_PROCESSED, PROCESSING, SUCCEEDED, FAILED_STATUS)
# RW-C04 section 6, written out here independently of the route table.
RESET_TARGETS = {
    ("Raw", "Process"),
    ("Standard", "Process"),
    ("Standard", "Review"),
    ("Standard", "Apply"),
}
PROJECT = ProjectRecord(id="p-1", name="SDLC", code="SDLC", state="Planned")
TITLE = "Secret requirement prose"

# (Type, State, worker, the State its success leaves behind)
ROUTE_CASES = [
    ("Raw", "Process", Worker.RAW_PROCESS, "Review"),
    ("Standard", "Process", Worker.STANDARD_PROCESS, "Review"),
    ("Standard", "Review", Worker.STANDARD_REVIEW, "Ready"),
    ("Standard", "Apply", Worker.STANDARD_APPLY, "Applied"),
]
ROUTE_IDS = [f"{t}+{s}" for t, s, _, _ in ROUTE_CASES]
NO_ROUTE_STATES = [
    ("Raw", "Draft"),
    ("Raw", "Review"),
    ("Standard", "Draft"),
    ("Standard", "Ready"),
    ("Standard", "Applied"),
    ("Raw", "Ready"),
    ("Raw", "Apply"),
    ("Raw", "Applied"),
]


class StatusWorkspace:
    """The runner's Processing Status operations over an existing Fibery fake.

    Everything else delegates to the wrapped fake, so real workers run on the
    same records, Documents and mutation log. `automation` models the RW-C04
    reset rule: a State write into one of the four machine combinations sets
    the status to Not Processed. `options` is the Field's option set, None
    when the Field is absent; `default` is its configured default.

    `on_call[(method, n)]` runs just before the n-th call of `method`, which
    is how a test interleaves a concurrent change or a Fibery failure at an
    exact point of a cycle. `poll_rows` replaces what the eligible-work query
    returns, to model a query that disagrees with current Fibery state.
    """

    def __init__(
        self,
        inner,
        statuses=None,
        *,
        automation=True,
        options=FOUR_OPTIONS,
        default=NOT_PROCESSED,
    ):
        self.inner = inner
        self.statuses = dict(statuses or {})
        self.automation = automation
        self.options = options
        self.default = default
        self.resets = []
        self.queries = []
        self.poll_rows = None
        self.on_call = {}

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def status_of(self, entity_id):
        return self.statuses.get(entity_id, self.default)

    def with_status(self, record):
        return dataclasses.replace(record, processing_status=self.status_of(record.id))

    def _before(self, method):
        action = self.on_call.pop((method, self.inner.calls.count(method) + 1), None)
        if action is not None:
            action()

    # -- the dispatcher's and workers' operations, carrying the status -----------

    def read_requirement(self, entity_id):
        self._before("read_requirement")
        record = self.inner.read_requirement(entity_id)
        return None if record is None else self.with_status(record)

    def set_requirement_state(self, entity_id, state):
        self._before("set_requirement_state")
        self.inner.set_requirement_state(entity_id, state)
        record = self.inner.requirements[entity_id]
        if self.automation and (record.type_name, state) in RESET_TARGETS:
            self.statuses[entity_id] = NOT_PROCESSED
            self.resets.append((entity_id, state))

    # -- the runner's own operations ------------------------------------------------

    def validate_processing_status_field(self, options):
        self._before("validate_processing_status_field")
        self.inner._record("validate_processing_status_field")
        if self.options is None:
            raise FiberyError("SDLC/Requirement has no 'Processing Status' Field")
        if sorted(self.options) != sorted(options):
            raise FiberyError(f"Processing Status has the options {self.options!r}")

    def find_eligible_requirements(self, routes, status):
        self._before("find_eligible_requirements")
        self.inner._record("find_eligible_requirements")
        self.queries.append((tuple(routes), status))
        if self.poll_rows is not None:
            return list(self.poll_rows)
        rows = [self.with_status(r) for r in self.inner.requirements.values()]
        return sorted(
            (
                r
                for r in rows
                if (r.type_name, r.state) in set(routes)
                and r.processing_status == status
            ),
            key=lambda r: int(r.public_id),
        )

    def set_processing_status(self, entity_id, status):
        self._before("set_processing_status")
        self.inner._record("set_processing_status")
        if status not in (self.options or ()):
            raise FiberyError(f"Processing Status has no option {status!r}")
        self.inner.mutations.append(f"set_processing_status {entity_id} {status}")
        self.statuses[entity_id] = status


def record(entity_id, public_id, type_name, state, **changes):
    base = {
        "id": entity_id,
        "public_id": str(public_id),
        "requirement_id": f"SDLC-FR-{int(public_id):04d}",
        "title": TITLE,
        "type_name": type_name,
        "state": state,
        "revision": 1,
        "project_id": PROJECT.id,
        "source_fingerprint": None,
    }
    return RequirementRecord(**{**base, **changes})


def workspace_of(*records, **options):
    return StatusWorkspace(FakeProcessorWorkspace(PROJECT, list(records)), **options)


def only_eligible(inner, entity_id, **options):
    """Wrap a built fixture so only this Requirement is at Not Processed."""
    return StatusWorkspace(
        inner, {entity_id: NOT_PROCESSED}, default=SUCCEEDED, **options
    )


def unexpected(*_args, **_options):
    raise AssertionError("no worker may run here")


NO_WORKERS = RequirementWorkers(unexpected, unexpected, unexpected, unexpected)


class CompletingWorkers:
    """Every worker performs its route's own transition and returns a normal result.

    Each call records the worker, the entity and the status it saw.
    """

    def __init__(self, ws):
        self.ws = ws
        self.calls = []

    def bound(self):
        return RequirementWorkers(
            process_raw=self._worker(Worker.RAW_PROCESS),
            process_standard=self._worker(Worker.STANDARD_PROCESS),
            review_standard=self._worker(Worker.STANDARD_REVIEW),
            apply_standard=self._worker(Worker.STANDARD_APPLY),
        )

    def _worker(self, worker):
        completed = next(
            r.completed_state for r in ROUTES.values() if r.worker is worker
        )

        def run(entity_id, **_options):
            self.calls.append((worker, entity_id, self.ws.status_of(entity_id)))
            self.ws.set_requirement_state(entity_id, completed)
            return NORMAL[worker]

        return run


def drive(ws, workers, cycles, **options):
    """Run exactly `cycles` runner cycles; return the reports and the sleeps."""
    reports, sleeps = [], []
    remaining = iter(range(cycles))
    run_requirement_runner(
        ws,
        workers,
        sleep=sleeps.append,
        report=reports.append,
        should_continue=lambda: next(remaining, None) is not None,
        **options,
    )
    return reports, sleeps


def outcomes(reports):
    return [report.outcome for report in reports]


def status_writes(ws):
    return [m for m in ws.mutations if m.startswith("set_processing_status")]


def changes_to(ws, entity_id, status=None, **fields):
    """Someone else changing the Requirement in Fibery, directly."""

    def act():
        if status is not None:
            ws.statuses[entity_id] = status
        if fields:
            ws.inner.requirements[entity_id] = dataclasses.replace(
                ws.inner.requirements[entity_id], **fields
            )

    return act


def raiser(error):
    def act():
        raise error

    return act


# -- preflight ---------------------------------------------------------------------


def test_the_runner_polls_the_four_rw_c04_routes_and_validates_the_four_options():
    assert PROCESSING_STATUS_OPTIONS == FOUR_OPTIONS
    assert set(MACHINE_ROUTES) == RESET_TARGETS
    assert len(MACHINE_ROUTES) == len(RESET_TARGETS)


@pytest.mark.parametrize(
    "options",
    [
        None,
        FOUR_OPTIONS[:3],
        (*FOUR_OPTIONS, "Queued"),
        (NOT_PROCESSED, PROCESSING, "Done", FAILED_STATUS),
    ],
    ids=["absent", "missing-one", "a-fifth", "renamed"],
)
def test_the_runner_refuses_to_start_without_exactly_the_frozen_field(options):
    ws = workspace_of(record("r-1", 1, "Raw", "Process"), options=options)
    started = []

    with pytest.raises(RunnerPreflightError):
        drive(ws, NO_WORKERS, cycles=1, on_started=started.append)

    assert ws.calls == ["validate_processing_status_field"]
    assert ws.mutations == []
    assert started == []


def test_the_start_is_announced_only_after_the_preflight_passed():
    ws = workspace_of()
    started = []

    drive(ws, NO_WORKERS, cycles=1, on_started=started.append)

    assert started == [DEFAULT_POLL_INTERVAL_SECONDS]
    assert ws.calls[:2] == [
        "validate_processing_status_field",
        "find_eligible_requirements",
    ]


# -- idle polling -------------------------------------------------------------------


def test_no_eligible_work_dispatches_nothing_and_sleeps_the_default_interval():
    ws = workspace_of(
        *(
            record(f"r-{n}", n, type_name, state)
            for n, (type_name, state) in enumerate(NO_ROUTE_STATES, start=1)
        )
    )

    reports, sleeps = drive(ws, NO_WORKERS, cycles=1)

    assert outcomes(reports) == [CycleOutcome.IDLE]
    assert sleeps == [DEFAULT_POLL_INTERVAL_SECONDS] == [5]
    assert ws.mutations == []


@pytest.mark.parametrize("interval", [MINIMUM_POLL_INTERVAL_SECONDS, 7])
def test_an_explicit_interval_is_the_idle_sleep(interval):
    _, sleeps = drive(
        workspace_of(), NO_WORKERS, cycles=2, poll_interval_seconds=interval
    )

    assert sleeps == [interval, interval]


@pytest.mark.parametrize(
    ("interval", "error"),
    [(0, ValueError), (-5, ValueError), (1.5, TypeError), (True, TypeError)],
)
def test_an_interval_below_the_minimum_or_not_whole_is_refused_first(interval, error):
    ws = workspace_of(record("r-1", 1, "Raw", "Process"))

    with pytest.raises(error):
        drive(ws, NO_WORKERS, cycles=1, poll_interval_seconds=interval)

    assert ws.calls == []
    assert MINIMUM_POLL_INTERVAL_SECONDS == 1


def test_the_poll_asks_for_exactly_the_machine_routes_at_not_processed():
    ws = workspace_of()

    drive(ws, NO_WORKERS, cycles=1)

    [(routes, status)] = ws.queries
    assert set(routes) == RESET_TARGETS
    assert status == NOT_PROCESSED


@pytest.mark.parametrize(("type_name", "state"), NO_ROUTE_STATES)
def test_a_polled_row_whose_own_values_select_no_route_is_never_claimed(
    type_name, state
):
    """The query is only a filter; `select_route` decides every row."""
    stored = record("r-1", 1, type_name, state)
    ws = workspace_of(stored)
    ws.poll_rows = [ws.with_status(stored)]

    reports, _ = drive(ws, NO_WORKERS, cycles=1)

    assert outcomes(reports) == [CycleOutcome.IDLE]
    assert ws.calls == [
        "validate_processing_status_field",
        "find_eligible_requirements",
    ]
    assert ws.mutations == []


@pytest.mark.parametrize("status", [PROCESSING, SUCCEEDED, FAILED_STATUS, None])
def test_a_polled_row_at_any_other_status_is_never_claimed(status):
    stored = record("r-1", 1, "Standard", "Apply")
    ws = workspace_of(stored)
    ws.poll_rows = [dataclasses.replace(stored, processing_status=status)]

    assert run_cycle(ws, NO_WORKERS).outcome is CycleOutcome.IDLE
    assert ws.mutations == []


# -- selection ----------------------------------------------------------------------


def test_the_lowest_public_id_runs_first_and_work_drains_without_an_idle_sleep():
    ws = workspace_of(
        record("r-100", 100, "Standard", "Apply"),
        record("r-10", 10, "Standard", "Review"),
        record("r-9", 9, "Raw", "Process"),
        record("r-draft", 1, "Standard", "Draft"),
    )
    workers = CompletingWorkers(ws)

    reports, sleeps = drive(ws, workers.bound(), cycles=4)

    assert [call[1] for call in workers.calls] == ["r-9", "r-10", "r-100"]
    assert outcomes(reports) == [CycleOutcome.SUCCEEDED] * 3 + [CycleOutcome.IDLE]
    assert sleeps == [DEFAULT_POLL_INTERVAL_SECONDS], "no sleep while work remained"


def test_the_numerically_lowest_public_id_wins_whatever_order_the_page_has():
    rows = [
        record("r-10", 10, "Standard", "Apply"),
        record("r-100", 100, "Standard", "Apply"),
        record("r-9", 9, "Standard", "Apply"),
    ]
    ws = workspace_of(*rows)
    ws.poll_rows = [ws.with_status(row) for row in rows]  # a text sort's order
    workers = CompletingWorkers(ws)

    run_cycle(ws, workers.bound())

    assert [call[1] for call in workers.calls] == ["r-9"]


def test_one_cycle_dispatches_exactly_one_worker_and_asks_to_query_again():
    ws = workspace_of(
        record("r-1", 1, "Standard", "Apply"), record("r-2", 2, "Standard", "Apply")
    )
    workers = CompletingWorkers(ws)

    report = run_cycle(ws, workers.bound())

    assert report.outcome is CycleOutcome.SUCCEEDED
    assert not report.should_wait
    assert [call[1] for call in workers.calls] == ["r-1"]
    assert ws.status_of("r-2") == NOT_PROCESSED


# -- the fresh re-read before the claim ---------------------------------------------

FRESH_CHANGES = {
    "state": {"state": "Draft"},
    "state-to-another-route": {"state": "Review"},
    "type": {"type_name": "Raw"},
    "status": {"status": PROCESSING},
    "project": {"project_id": "p-2"},
    "requirement-id": {"requirement_id": "SDLC-FR-9999"},
}


@pytest.mark.parametrize("change", FRESH_CHANGES.values(), ids=FRESH_CHANGES.keys())
def test_a_change_between_the_poll_and_the_claim_starts_no_worker(change):
    ws = workspace_of(record("r-1", 1, "Standard", "Process"))
    ws.on_call[("read_requirement", 1)] = changes_to(ws, "r-1", **change)

    report = run_cycle(ws, NO_WORKERS)

    assert report.outcome is CycleOutcome.CANDIDATE_CHANGED
    assert not report.should_wait, "the runner queries again at once"
    assert report.details
    assert ws.mutations == []
    assert "set_processing_status" not in ws.calls


def test_a_candidate_that_no_longer_exists_is_not_claimed():
    ws = workspace_of(record("r-1", 1, "Raw", "Process"))
    ws.on_call[("read_requirement", 1)] = lambda: ws.inner.requirements.pop("r-1")

    report = run_cycle(ws, NO_WORKERS)

    assert report.outcome is CycleOutcome.CANDIDATE_CHANGED
    assert ws.mutations == []


def test_a_candidate_that_cannot_be_re_read_is_not_claimed_and_the_runner_waits():
    ws = workspace_of(record("r-1", 1, "Raw", "Process"))
    ws.failures["read_requirement"] = FiberyError("Fibery timed out")

    report = run_cycle(ws, NO_WORKERS)

    assert report.outcome is CycleOutcome.CANDIDATE_READ_FAILED
    assert report.should_wait
    assert ws.mutations == []


def test_a_failed_poll_claims_nothing_and_the_runner_waits():
    ws = workspace_of(record("r-1", 1, "Raw", "Process"))
    ws.failures["find_eligible_requirements"] = FiberyError("Fibery timed out")

    reports, sleeps = drive(ws, NO_WORKERS, cycles=1)

    assert outcomes(reports) == [CycleOutcome.POLL_FAILED]
    assert sleeps == [DEFAULT_POLL_INTERVAL_SECONDS]
    assert ws.mutations == []


# -- the claim ----------------------------------------------------------------------


def test_processing_is_written_and_confirmed_before_the_worker_starts():
    ws = workspace_of(record("r-1", 1, "Standard", "Apply"))
    workers = CompletingWorkers(ws)

    run_cycle(ws, workers.bound())

    assert workers.calls == [(Worker.STANDARD_APPLY, "r-1", PROCESSING)]
    worker_write = ws.mutations.index("set_requirement_state r-1 Applied")
    assert ws.mutations[:worker_write] == ["set_processing_status r-1 Processing"]
    assert ws.calls[:4] == [
        "find_eligible_requirements",
        "read_requirement",
        "set_processing_status",
        "read_requirement",
    ]


def test_a_claim_that_cannot_be_written_starts_no_worker():
    ws = workspace_of(record("r-1", 1, "Standard", "Review"))
    ws.failures["set_processing_status"] = FiberyError("refused")

    report = run_cycle(ws, NO_WORKERS)

    assert report.outcome is CycleOutcome.CLAIM_FAILED
    assert report.should_wait
    assert ws.mutations == []


@pytest.mark.parametrize("interference", ["write-lost", "read-fails", "state-changed"])
def test_a_claim_that_is_not_confirmed_starts_no_worker_and_writes_nothing_else(
    interference,
):
    ws = workspace_of(record("r-1", 1, "Standard", "Review"))
    ws.on_call[("read_requirement", 2)] = {
        "write-lost": changes_to(ws, "r-1", status=NOT_PROCESSED),
        "read-fails": raiser(FiberyError("Fibery timed out")),
        "state-changed": changes_to(ws, "r-1", state="Draft"),
    }[interference]

    report = run_cycle(ws, NO_WORKERS)

    assert report.outcome is CycleOutcome.CLAIM_NOT_CONFIRMED
    assert report.should_wait
    assert ws.mutations == ["set_processing_status r-1 Processing"]
    if interference == "state-changed":
        # Not repaired: the new State's status is left as the claim left it.
        assert ws.status_of("r-1") == PROCESSING
        assert ws.inner.requirements["r-1"].state == "Draft"


# -- completed routes, with the real workers ------------------------------------------


def test_raw_process_completes_with_its_candidates_progressed_and_succeeds():
    inner, raw, _ = build_workspace()
    ws = StatusWorkspace(inner)
    model = FakeModelRuntime([model_output([candidate()])])
    workers = RequirementWorkers(
        process_raw=functools.partial(process_raw_requirement, ws, model),
        process_standard=unexpected,
        review_standard=unexpected,
        apply_standard=unexpected,
    )

    report = run_cycle(ws, workers)

    assert report.outcome is CycleOutcome.SUCCEEDED, report
    assert report.dispatch_result.outcome is DispatchOutcome.ROUTE_COMPLETED
    assert inner.requirements[raw.id].state == "Review"
    assert ws.status_of(raw.id) == SUCCEEDED
    [produced] = inner.produces(raw.id)
    assert inner.requirements[produced].state == "Process"
    assert ws.status_of(produced) == NOT_PROCESSED
    assert status_writes(ws) == [
        f"set_processing_status {raw.id} Processing",
        f"set_processing_status {raw.id} Succeeded",
    ]


@pytest.mark.parametrize("verdict", ["PASS", "NEEDS_WORK", "BLOCKING"])
def test_review_reaches_ready_and_succeeds_whatever_the_verdict(verdict):
    findings = () if verdict == "PASS" else (finding(),)
    inner, requirement, _root, _ = build_review_workspace(findings=findings)
    ws = only_eligible(inner, requirement.id)
    severity = "BLOCKING" if verdict == "BLOCKING" else "WARNING"
    response = review_output(
        finding_verifications=[confirm(severity=severity)] if findings else []
    )
    workers = RequirementWorkers(
        unexpected,
        unexpected,
        functools.partial(
            review_standard_requirement, ws, FakeModelRuntime([response])
        ),
        unexpected,
    )

    report = run_cycle(ws, workers)

    assert report.dispatch_result.worker_result.verdict == verdict
    assert report.outcome is CycleOutcome.SUCCEEDED, report
    assert inner.requirements[requirement.id].state == "Ready"
    assert ws.status_of(requirement.id) == SUCCEEDED


def test_apply_reaches_applied_and_succeeds():
    inner, requirement, _root, _ = build_apply_workspace(proposals=(proposal(),))
    ws = only_eligible(inner, requirement.id)
    workers = RequirementWorkers(
        unexpected,
        unexpected,
        unexpected,
        functools.partial(apply_standard_requirement, ws),
    )

    report = run_cycle(ws, workers)

    assert report.outcome is CycleOutcome.SUCCEEDED, report
    assert inner.requirements[requirement.id].state == "Applied"
    assert ws.status_of(requirement.id) == SUCCEEDED


# -- Standard Process -> Review: the reset belongs to the automation ------------------


def standard_process_workers(ws, review=unexpected):
    model = FakeModelRuntime([analysis_output()])
    return RequirementWorkers(
        unexpected,
        functools.partial(process_standard_requirement, ws, model),
        review,
        unexpected,
    )


def test_standard_process_hands_off_to_review_and_leaves_the_reset_intact():
    inner, requirement, _ = build_standard_workspace()
    ws = only_eligible(inner, requirement.id)

    report = run_cycle(ws, standard_process_workers(ws))

    assert report.outcome is CycleOutcome.HANDED_OFF, report
    assert not report.should_wait
    assert report.dispatch_result.outcome is DispatchOutcome.ROUTE_COMPLETED
    assert inner.requirements[requirement.id].state == "Review"
    assert ws.status_of(requirement.id) == NOT_PROCESSED
    assert ws.resets == [(requirement.id, "Review")]
    assert status_writes(ws) == [f"set_processing_status {requirement.id} Processing"]


def test_regression_succeeded_is_never_written_over_the_review_cycle_reset():
    """The race RW-O03 closes: the automation resets Review to Not Processed as
    the worker moves it; a Succeeded written after that would make Review
    ineligible for good. Review must run next, at once."""
    inner, requirement, _ = build_standard_workspace()
    ws = only_eligible(inner, requirement.id)
    review = CompletingWorkers(ws)
    workers = standard_process_workers(ws, review=review.bound().review_standard)

    reports, sleeps = drive(ws, workers, cycles=3)

    assert outcomes(reports) == [
        CycleOutcome.HANDED_OFF,
        CycleOutcome.SUCCEEDED,
        CycleOutcome.IDLE,
    ]
    assert review.calls == [(Worker.STANDARD_REVIEW, requirement.id, PROCESSING)]
    assert status_writes(ws) == [
        f"set_processing_status {requirement.id} Processing",
        f"set_processing_status {requirement.id} Processing",
        f"set_processing_status {requirement.id} Succeeded",
    ]
    assert inner.requirements[requirement.id].state == "Ready"
    assert sleeps == [DEFAULT_POLL_INTERVAL_SECONDS]


def test_a_reset_not_observed_after_the_handoff_is_reported_and_never_written():
    inner, requirement, _ = build_standard_workspace()
    ws = only_eligible(inner, requirement.id, automation=False)

    report = run_cycle(ws, standard_process_workers(ws))

    assert report.outcome is CycleOutcome.RESET_NOT_OBSERVED, report
    assert not report.is_normal
    assert inner.requirements[requirement.id].state == "Review"
    assert ws.status_of(requirement.id) == PROCESSING
    assert status_writes(ws) == [f"set_processing_status {requirement.id} Processing"]
    # Review does not start on a status the runner has not seen reset...
    assert run_cycle(ws, NO_WORKERS).outcome is CycleOutcome.IDLE
    # ...and once the automation's reset arrives, the Review cycle runs.
    ws.statuses[requirement.id] = NOT_PROCESSED
    review = CompletingWorkers(ws)
    assert run_cycle(ws, review.bound()).outcome is CycleOutcome.SUCCEEDED
    assert review.calls == [(Worker.STANDARD_REVIEW, requirement.id, PROCESSING)]


# -- failures -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("type_name", "state", "worker", "_"), ROUTE_CASES, ids=ROUTE_IDS
)
def test_a_worker_failure_is_failed_in_the_claimed_state(type_name, state, worker, _):
    ws = workspace_of(record("r-1", 1, type_name, state))
    workers = FakeWorkers(ws, FAILED[worker])

    report = run_cycle(ws, workers.bound())

    assert report.dispatch_result.outcome is DispatchOutcome.WORKER_FAILED
    assert report.outcome is CycleOutcome.FAILED
    assert ws.inner.requirements["r-1"].state == state
    assert ws.status_of("r-1") == FAILED_STATUS
    assert status_writes(ws) == [
        "set_processing_status r-1 Processing",
        "set_processing_status r-1 Failed",
    ]
    assert len(workers.calls) == 1


@pytest.mark.parametrize(
    ("type_name", "state", "worker", "_"), ROUTE_CASES, ids=ROUTE_IDS
)
def test_a_normal_result_without_its_transition_is_failed_not_completed(
    type_name, state, worker, _
):
    ws = workspace_of(record("r-1", 1, type_name, state))

    report = run_cycle(ws, FakeWorkers(ws, NORMAL[worker]).bound())

    assert report.dispatch_result.outcome is DispatchOutcome.POSTCONDITION_NOT_REACHED
    assert report.outcome is CycleOutcome.FAILED
    assert ws.inner.requirements["r-1"].state == state
    assert ws.status_of("r-1") == FAILED_STATUS


def test_failed_work_is_never_retried_automatically():
    ws = workspace_of(record("r-1", 1, "Standard", "Apply"))
    workers = FakeWorkers(ws, FAILED[Worker.STANDARD_APPLY])

    reports, sleeps = drive(ws, workers.bound(), cycles=3)

    assert outcomes(reports) == [
        CycleOutcome.FAILED,
        CycleOutcome.IDLE,
        CycleOutcome.IDLE,
    ]
    assert len(workers.calls) == 1
    assert sleeps == [DEFAULT_POLL_INTERVAL_SECONDS] * 2


def raw_with_candidates(*candidate_states):
    """A RAW in Process whose worker names Standard candidates deriving from it."""
    raw = record("raw-1", 5, "Raw", "Process", requirement_id="SDLC-RAW-0005")
    candidates = [
        record(f"std-{n}", 40 + n, "Standard", state)
        for n, state in enumerate(candidate_states, start=1)
    ]
    ws = workspace_of(raw, *candidates)
    for standard in candidates:
        ws.inner.derived_from_ids[standard.id] = [raw.id]

    def process_raw(entity_id):
        ws.set_requirement_state(entity_id, "Review")
        return ProcessResult(
            ProcessResultCode.RAW_REQUIREMENT_PROCESSED,
            "ok",
            candidates=tuple(c.requirement_id for c in candidates),
        )

    workers = RequirementWorkers(process_raw, unexpected, unexpected, unexpected)
    return ws, candidates, workers


PROGRESSION_FAILURES = {
    "conflict": (
        ("Draft", "Ready"),
        None,
        DispatchOutcome.CANDIDATE_PROGRESSION_CONFLICT,
    ),
    "first-write": (
        ("Draft", "Draft"),
        2,
        DispatchOutcome.CANDIDATE_PROGRESSION_FAILED,
    ),
    "later-write": (
        ("Draft", "Draft"),
        3,
        DispatchOutcome.PARTIAL_CANDIDATE_PROGRESSION,
    ),
}


@pytest.mark.parametrize(
    ("states", "failing_write", "dispatched"),
    PROGRESSION_FAILURES.values(),
    ids=PROGRESSION_FAILURES.keys(),
)
def test_a_raw_progression_failure_is_failed_in_review_and_nothing_rolls_back(
    states, failing_write, dispatched
):
    ws, candidates, workers = raw_with_candidates(*states)
    if failing_write is not None:
        # Write 1 is the RAW's own Process -> Review; then one per candidate.
        ws.on_call[("set_requirement_state", failing_write)] = raiser(
            FiberyError("refused")
        )

    report = run_cycle(ws, workers)

    assert report.dispatch_result.outcome is dispatched
    assert report.outcome is CycleOutcome.FAILED
    assert ws.inner.requirements["raw-1"].state == "Review"
    assert ws.status_of("raw-1") == FAILED_STATUS
    progressed = report.dispatch_result.progressed
    in_process = tuple(
        c.requirement_id
        for c in candidates
        if ws.inner.requirements[c.id].state == "Process"
    )
    assert in_process == progressed
    if dispatched is DispatchOutcome.PARTIAL_CANDIDATE_PROGRESSION:
        assert progressed == (candidates[0].requirement_id,)


def test_a_read_failure_after_the_worker_guesses_no_final_status():
    ws = workspace_of(record("r-1", 1, "Standard", "Apply"))

    def apply(entity_id):
        ws.set_requirement_state(entity_id, "Applied")
        ws.failures["read_requirement"] = FiberyError("Fibery timed out")
        return NORMAL[Worker.STANDARD_APPLY]

    report = run_cycle(
        ws, RequirementWorkers(unexpected, unexpected, unexpected, apply)
    )

    assert report.dispatch_result.outcome is DispatchOutcome.FIBERY_READ_FAILED
    assert report.outcome is CycleOutcome.PARTIAL
    assert not report.is_normal
    assert ws.status_of("r-1") == PROCESSING
    assert status_writes(ws) == ["set_processing_status r-1 Processing"]


def test_a_route_gone_stale_after_the_claim_runs_nothing_and_guesses_nothing():
    ws = workspace_of(record("r-1", 1, "Standard", "Apply"))
    # Read 1 re-reads the candidate, read 2 confirms the claim, read 3 is the
    # dispatcher's own revalidation.
    ws.on_call[("read_requirement", 3)] = changes_to(ws, "r-1", state="Ready")

    report = run_cycle(ws, NO_WORKERS)

    assert report.dispatch_result.outcome is DispatchOutcome.STALE_ROUTE
    assert report.outcome is CycleOutcome.PARTIAL
    assert ws.status_of("r-1") == PROCESSING
    assert status_writes(ws) == ["set_processing_status r-1 Processing"]


def test_a_failed_final_status_write_does_not_run_the_worker_again():
    ws = workspace_of(record("r-1", 1, "Standard", "Apply"))
    ws.on_call[("set_processing_status", 2)] = raiser(FiberyError("refused"))
    workers = CompletingWorkers(ws)

    reports, _ = drive(ws, workers.bound(), cycles=3)

    assert outcomes(reports) == [
        CycleOutcome.PARTIAL,
        CycleOutcome.IDLE,
        CycleOutcome.IDLE,
    ]
    assert len(workers.calls) == 1
    assert ws.inner.requirements["r-1"].state == "Applied"
    assert ws.status_of("r-1") == PROCESSING


# Reads 1-4 are the re-read, the claim confirmation and the dispatcher's two;
# read 5 precedes the final write and read 6 confirms it.
FINAL_INTERFERENCE = {
    "status-changed-before-the-write": (5, "status", False),
    "read-before-the-write-fails": (5, "raise", False),
    "read-back-fails": (6, "raise", True),
    "read-back-differs": (6, "status", True),
}


@pytest.mark.parametrize(
    ("read", "kind", "written"),
    FINAL_INTERFERENCE.values(),
    ids=FINAL_INTERFERENCE.keys(),
)
def test_a_final_status_that_cannot_be_confirmed_is_partial(read, kind, written):
    ws = workspace_of(record("r-1", 1, "Standard", "Apply"))
    ws.on_call[("read_requirement", read)] = (
        raiser(FiberyError("Fibery timed out"))
        if kind == "raise"
        else changes_to(ws, "r-1", status=NOT_PROCESSED)
    )

    report = run_cycle(ws, CompletingWorkers(ws).bound())

    assert report.outcome is CycleOutcome.PARTIAL
    assert ("set_processing_status r-1 Succeeded" in ws.mutations) is written


def claimed_cycle(ws, entity_id):
    """The selection and the confirmed claim of the Requirement's current route."""
    selection = select_route(
        ws.read_requirement(entity_id), ProcessingStatus.NOT_PROCESSED
    )
    ws.set_processing_status(entity_id, PROCESSING)
    return selection, ws.read_requirement(entity_id)


def test_a_handoff_into_an_unexpected_state_is_partial_and_writes_nothing():
    ws = workspace_of(record("r-1", 1, "Standard", "Process"))
    selection, claimed = claimed_cycle(ws, "r-1")
    ws.set_requirement_state("r-1", "Review")
    changes_to(ws, "r-1", state="Ready")()
    before = list(ws.mutations)

    report = finalize_cycle(
        ws, claimed, DispatchResult(DispatchOutcome.ROUTE_COMPLETED, "m", selection)
    )

    assert report.outcome is CycleOutcome.PARTIAL
    assert ws.mutations == before


def test_a_dispatch_without_a_route_is_partial_and_writes_nothing():
    ws = workspace_of(record("r-1", 1, "Standard", "Ready"))
    selection = select_route(ws.read_requirement("r-1"), ProcessingStatus.NOT_PROCESSED)

    report = finalize_cycle(
        ws,
        ws.read_requirement("r-1"),
        DispatchResult(DispatchOutcome.NO_ROUTE, "m", selection),
    )

    assert report.outcome is CycleOutcome.PARTIAL
    assert ws.mutations == []


# -- replay and abrupt termination ----------------------------------------------------


@pytest.mark.parametrize("status", [PROCESSING, SUCCEEDED, FAILED_STATUS])
@pytest.mark.parametrize(("type_name", "state", "_w", "_c"), ROUTE_CASES, ids=ROUTE_IDS)
def test_a_claimed_or_settled_cycle_is_never_run_again(
    type_name, state, _w, _c, status
):
    ws = workspace_of(record("r-1", 1, type_name, state), statuses={"r-1": status})

    reports, _ = drive(ws, NO_WORKERS, cycles=2)

    assert outcomes(reports) == [CycleOutcome.IDLE, CycleOutcome.IDLE]
    assert ws.mutations == []


def test_an_abruptly_terminated_cycle_is_never_stolen():
    """A runner killed after its claim leaves Processing; no later runner takes it."""
    ws = workspace_of(record("r-1", 1, "Raw", "Process"), statuses={"r-1": PROCESSING})

    reports, sleeps = drive(ws, NO_WORKERS, cycles=3)

    assert outcomes(reports) == [CycleOutcome.IDLE] * 3
    assert sleeps == [DEFAULT_POLL_INTERVAL_SECONDS] * 3
    assert ws.mutations == []
    assert ws.status_of("r-1") == PROCESSING


@pytest.mark.parametrize(
    ("type_name", "state", "expected"),
    [
        ("Raw", "Process", [Worker.RAW_PROCESS]),
        ("Standard", "Process", [Worker.STANDARD_PROCESS, Worker.STANDARD_REVIEW]),
        ("Standard", "Review", [Worker.STANDARD_REVIEW]),
        ("Standard", "Apply", [Worker.STANDARD_APPLY]),
    ],
    ids=ROUTE_IDS,
)
def test_a_worker_owned_transition_never_replays_its_worker(type_name, state, expected):
    ws = workspace_of(record("r-1", 1, type_name, state))
    workers = CompletingWorkers(ws)

    reports, _ = drive(ws, workers.bound(), cycles=4)

    assert [call[0] for call in workers.calls] == expected
    assert outcomes(reports)[-1] is CycleOutcome.IDLE


# -- the acceptance criteria, end to end over the fake --------------------------------

HUMAN_DECISIONS = [
    ("Raw", "Draft", NOT_PROCESSED, "Process", Worker.RAW_PROCESS),
    ("Standard", "Ready", SUCCEEDED, "Process", Worker.STANDARD_PROCESS),
    ("Standard", "Ready", SUCCEEDED, "Apply", Worker.STANDARD_APPLY),
]


@pytest.mark.parametrize(
    ("type_name", "before", "status", "after", "worker"),
    HUMAN_DECISIONS,
    ids=["raw-draft-to-process", "ready-to-process", "ready-to-apply"],
)
def test_a_human_state_change_alone_starts_the_right_worker(
    type_name, before, status, after, worker
):
    """AC1: no manual worker command; the State change and its reset suffice."""
    ws = workspace_of(record("r-1", 1, type_name, before), statuses={"r-1": status})
    workers = CompletingWorkers(ws)
    assert run_cycle(ws, workers.bound()).outcome is CycleOutcome.IDLE

    ws.set_requirement_state("r-1", after)  # the human's decision in Fibery
    run_cycle(ws, workers.bound())

    assert workers.calls == [(worker, "r-1", PROCESSING)]


def test_a_poll_row_the_current_fibery_state_contradicts_is_not_trusted():
    """AC5: a stale or forged eligibility never becomes product truth."""
    stored = record("r-1", 1, "Standard", "Applied")
    ws = workspace_of(stored, statuses={"r-1": SUCCEEDED})
    ws.poll_rows = [
        dataclasses.replace(stored, state="Apply", processing_status=NOT_PROCESSED)
    ]

    report = run_cycle(ws, NO_WORKERS)

    assert report.outcome is CycleOutcome.CANDIDATE_CHANGED
    assert ws.mutations == []


def test_cycle_reports_carry_identity_and_codes_never_requirement_content():
    inner, raw, _ = build_workspace()
    ws = StatusWorkspace(inner)
    output = model_output(
        [candidate(title="Candidate prose title", requirement="A secret sentence.")]
    )
    workers = RequirementWorkers(
        functools.partial(process_raw_requirement, ws, FakeModelRuntime([output])),
        unexpected,
        unexpected,
        unexpected,
    )

    reports, _ = drive(ws, workers, cycles=1)

    text = " ".join(" ".join([r.message, *r.details]) for r in reports)
    assert raw.requirement_id in text
    for forbidden in (
        raw.title,
        "The CLI must be fast",
        "Candidate prose title",
        "A secret sentence",
        "raw-secret",
    ):
        assert forbidden not in text


# -- the Fibery HTTP adapter's Processing Status operations ---------------------------

STATUS_FIELD = {
    "fibery/name": "SDLC/Processing Status",
    "fibery/type": "SDLC/Processing Status_SDLC/Requirement",
    "fibery/meta": {"fibery/collection?": False},
}
STATUS_OPTION_TYPE = {
    "fibery/name": "SDLC/Processing Status_SDLC/Requirement",
    "fibery/meta": {"fibery/enum?": True},
    "fibery/fields": [],
}
OPTION_ROWS = [
    {"fibery/id": f"opt-{n}", "enum/name": name} for n, name in enumerate(FOUR_OPTIONS)
]
FROZEN_SELECT = [
    "fibery/id",
    "fibery/public-id",
    "SDLC/Requirement ID",
    "SDLC/Title",
    "SDLC/Revision",
    "SDLC/Source Fingerprint",
    {"SDLC/Type": ["enum/name"]},
    {"workflow/state": ["enum/name"]},
    {"SDLC/Project": ["fibery/id"]},
]


def schema_with(field=STATUS_FIELD, option_type=STATUS_OPTION_TYPE):
    requirement = copy.deepcopy(REQUIREMENT_SCHEMA["fibery/types"][0])
    if field is not None:
        requirement["fibery/fields"].append(field)
    return {"fibery/types": [requirement, *([option_type] if option_type else [])]}


def http_workspace(payloads, schema=None):
    opener = StubOpener([ok(schema_with() if schema is None else schema), *payloads])
    workspace = FiberyRawProcessorWorkspace(
        FiberyClient(SETTINGS, url_opener=opener, **unpaced()), "SDLC", "space-uuid"
    )
    return workspace, opener


def sent(opener, index):
    return opener.requests[index]["body"][0]


def requirement_row(status=NOT_PROCESSED, field="SDLC/Processing Status"):
    row = {
        "fibery/id": "r1",
        "fibery/public-id": "7",
        "SDLC/Requirement ID": "SDLC-FR-0007",
        "SDLC/Type": {"enum/name": "Standard"},
        "workflow/state": {"enum/name": "Apply"},
        "SDLC/Project": {"fibery/id": "p1"},
    }
    if status is not None:
        row[field] = {"enum/name": status}
    return row


def test_http_processing_status_is_resolved_from_the_schema_and_read_back():
    workspace, opener = http_workspace([ok([requirement_row(PROCESSING)])])

    record_read = workspace.read_requirement("r1")

    assert record_read.processing_status == PROCESSING
    select = sent(opener, 1)["args"]["query"]["q/select"]
    assert {"SDLC/Processing Status": ["enum/name"]} in select


def test_http_the_field_is_found_by_its_name_not_by_an_assumed_prefix():
    field = {
        **STATUS_FIELD,
        "fibery/name": "Ops/Processing Status",
        "fibery/type": "Ops/Processing Status_SDLC/Requirement",
    }
    option_type = {
        **STATUS_OPTION_TYPE,
        "fibery/name": "Ops/Processing Status_SDLC/Requirement",
    }
    workspace, opener = http_workspace(
        [ok([requirement_row(SUCCEEDED, field="Ops/Processing Status")])],
        schema=schema_with(field, option_type),
    )

    assert workspace.read_requirement("r1").processing_status == SUCCEEDED
    select = sent(opener, 1)["args"]["query"]["q/select"]
    assert {"Ops/Processing Status": ["enum/name"]} in select


def test_http_the_option_set_is_read_from_the_fields_option_database():
    workspace, opener = http_workspace([ok(OPTION_ROWS)])

    workspace.validate_processing_status_field(FOUR_OPTIONS)

    assert sent(opener, 1)["args"]["query"] == {
        "q/from": "SDLC/Processing Status_SDLC/Requirement",
        "q/select": ["fibery/id", "enum/name"],
        "q/limit": len(FOUR_OPTIONS) + 1,
    }


@pytest.mark.parametrize(
    "names",
    [
        FOUR_OPTIONS[:3],
        (*FOUR_OPTIONS, "Queued"),
        (NOT_PROCESSED, PROCESSING, "Done", FAILED_STATUS),
        (NOT_PROCESSED, PROCESSING, SUCCEEDED, SUCCEEDED),
    ],
    ids=["missing-one", "a-fifth", "renamed", "duplicated"],
)
def test_http_a_wrong_option_set_is_rejected(names):
    rows = [
        {"fibery/id": f"opt-{n}", "enum/name": name} for n, name in enumerate(names)
    ]
    workspace, _ = http_workspace([ok(rows)])

    with pytest.raises(FiberyError, match="needs exactly"):
        workspace.validate_processing_status_field(FOUR_OPTIONS)


def test_http_a_missing_field_fails_only_the_runner_preflight():
    workspace, opener = http_workspace(
        [ok([requirement_row(status=None)])],
        schema=schema_with(field=None, option_type=None),
    )

    record_read = workspace.read_requirement("r1")

    assert record_read.processing_status is None
    assert sent(opener, 1)["args"]["query"]["q/select"] == FROZEN_SELECT
    with pytest.raises(FiberyError, match="no 'Processing Status' Field"):
        workspace.validate_processing_status_field(FOUR_OPTIONS)
    with pytest.raises(FiberyError, match="Processing Status"):
        workspace.set_processing_status("r1", PROCESSING)
    assert len(opener.requests) == 2, "neither refusal sent a request"


@pytest.mark.parametrize(
    ("field", "option_type"),
    [
        (
            {**STATUS_FIELD, "fibery/meta": {"fibery/collection?": True}},
            STATUS_OPTION_TYPE,
        ),
        ({**STATUS_FIELD, "fibery/type": "fibery/text"}, None),
        (STATUS_FIELD, {**STATUS_OPTION_TYPE, "fibery/meta": {}}),
    ],
    ids=["multi-select", "text", "not-an-enum"],
)
def test_http_a_field_that_is_not_a_single_select_is_never_read_or_written(
    field, option_type
):
    workspace, opener = http_workspace(
        [ok([requirement_row(status=None)])], schema=schema_with(field, option_type)
    )

    assert workspace.read_requirement("r1").processing_status is None
    assert sent(opener, 1)["args"]["query"]["q/select"] == FROZEN_SELECT
    with pytest.raises(FiberyError, match="single-select"):
        workspace.validate_processing_status_field(FOUR_OPTIONS)
    with pytest.raises(FiberyError, match="single-select"):
        workspace.set_processing_status("r1", PROCESSING)
    assert len(opener.requests) == 2


def test_http_the_eligible_query_filters_routes_and_status_in_public_id_order():
    workspace, opener = http_workspace([ok([requirement_row()])])

    records = workspace.find_eligible_requirements(MACHINE_ROUTES, NOT_PROCESSED)

    args = sent(opener, 1)["args"]
    query, params = args["query"], args["params"]
    assert query["q/from"] == "SDLC/Requirement"
    assert query["q/order-by"] == [[["fibery/public-id"], "q/asc"]]
    assert query["q/limit"] == ELIGIBLE_QUERY_LIMIT
    connective, status_clause, routes_clause = query["q/where"]
    assert connective == "q/and"
    assert status_clause == ["=", ["SDLC/Processing Status", "enum/name"], "$status"]
    assert params["$status"] == NOT_PROCESSED
    assert routes_clause[0] == "q/or"
    pairs = set()
    for clause in routes_clause[1:]:
        assert clause[0] == "q/and"
        assert clause[1][1] == ["SDLC/Type", "enum/name"]
        assert clause[2][1] == ["workflow/state", "enum/name"]
        pairs.add((params[clause[1][2]], params[clause[2][2]]))
    assert pairs == RESET_TARGETS
    assert len(routes_clause) == 1 + len(RESET_TARGETS)
    assert [r.processing_status for r in records] == [NOT_PROCESSED]


def test_http_a_status_write_resolves_the_option_entity_then_updates_the_field():
    workspace, opener = http_workspace(
        [ok([{"fibery/id": "opt-1", "enum/name": PROCESSING}]), ok({"fibery/id": "r1"})]
    )

    workspace.set_processing_status("r1", PROCESSING)

    lookup = sent(opener, 1)["args"]
    assert lookup["query"]["q/from"] == "SDLC/Processing Status_SDLC/Requirement"
    assert lookup["query"]["q/where"] == ["=", ["enum/name"], "$name"]
    assert lookup["params"] == {"$name": PROCESSING}
    update = sent(opener, 2)
    assert update["command"] == "fibery.entity/update"
    assert update["args"] == {
        "type": "SDLC/Requirement",
        "entity": {"fibery/id": "r1", "SDLC/Processing Status": {"fibery/id": "opt-1"}},
    }


def test_http_an_unknown_status_option_is_refused_before_any_write():
    workspace, opener = http_workspace([ok([])])

    with pytest.raises(FiberyError, match="no option named"):
        workspace.set_processing_status("r1", "Queued")

    assert len(opener.requests) == 2


def test_http_existing_reads_are_unchanged_without_the_field():
    workspace, opener = http_workspace(
        [ok([requirement_row(status=None)])], schema=REQUIREMENT_SCHEMA
    )

    workspace.read_requirement("r1")

    query = sent(opener, 1)["args"]["query"]
    assert query["q/select"] == FROZEN_SELECT
    assert "q/order-by" not in query
