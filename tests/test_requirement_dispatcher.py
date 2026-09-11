"""RW-O02: the bounded Requirement worker dispatcher.

Route selection is pure over a Requirement and the Processing Status the
future runner supplies; dispatch revalidates the Requirement, runs exactly one
already-bound worker, and classifies its typed result against the lifecycle
postcondition that worker owns. Fake workers pin every routing branch; the
real workers on the Fibery fakes prove CR-002, the RAW inherited candidate
progression and replay.
"""

import functools
from dataclasses import replace

import pytest

from processor_fake import (
    FakeModelRuntime,
    FakeProcessorWorkspace,
    build_workspace,
    candidate,
    model_output,
)
from ready_fake import build_ready_workspace, process_result_nodes, review_result_nodes
from review_fake import build_review_workspace, review_output
from sdlc import cli
from sdlc.fibery_workspace import FiberyError, ProjectRecord, RequirementRecord
from sdlc.raw_processor import process_raw_requirement
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.requirement_dispatcher import (
    ROUTES,
    DispatchOutcome,
    ProcessingStatus,
    RequirementWorkers,
    RouteDecision,
    Worker,
    dispatch,
    select_route,
)
from sdlc.results import (
    ApplyResult,
    ApplyResultCode,
    ProcessResult,
    ProcessResultCode,
    StandardProcessResult,
    StandardProcessResultCode,
    StandardReviewResult,
    StandardReviewResultCode,
)
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import analysis_output
from test_standard_process_explicit_resume import completed_then_reverted

NOT_PROCESSED = ProcessingStatus.NOT_PROCESSED
CLAIMED_OR_SETTLED = [
    ProcessingStatus.PROCESSING,
    ProcessingStatus.SUCCEEDED,
    ProcessingStatus.FAILED,
]
PROJECT = ProjectRecord(id="p-1", name="SDLC", code="SDLC", state="Planned")

# (Type, State, worker, the State the worker's success leaves behind)
AUTHORIZED = [
    ("Raw", "Process", Worker.RAW_PROCESS, "Review"),
    ("Standard", "Process", Worker.STANDARD_PROCESS, "Review"),
    ("Standard", "Review", Worker.STANDARD_REVIEW, "Ready"),
    ("Standard", "Apply", Worker.STANDARD_APPLY, "Applied"),
]
AUTHORIZED_IDS = [f"{t}+{s}" for t, s, _, _ in AUTHORIZED]
WORKER_NAME = {
    Worker.RAW_PROCESS: "process_raw",
    Worker.STANDARD_PROCESS: "process_standard",
    Worker.STANDARD_REVIEW: "review_standard",
    Worker.STANDARD_APPLY: "apply_standard",
}
NORMAL = {
    Worker.RAW_PROCESS: ProcessResult(
        ProcessResultCode.RAW_REQUIREMENT_PROCESSED, "ok"
    ),
    Worker.STANDARD_PROCESS: StandardProcessResult(
        StandardProcessResultCode.REQUIREMENT_PROCESSED, "ok"
    ),
    Worker.STANDARD_REVIEW: StandardReviewResult(
        StandardReviewResultCode.REQUIREMENT_REVIEWED, "ok"
    ),
    Worker.STANDARD_APPLY: ApplyResult(ApplyResultCode.REQUIREMENT_APPLIED, "ok"),
}
FAILED = {
    Worker.RAW_PROCESS: ProcessResult(ProcessResultCode.INVALID_MODEL_OUTPUT, "bad"),
    Worker.STANDARD_PROCESS: StandardProcessResult(
        StandardProcessResultCode.MODEL_RUNTIME_FAILED, "bad"
    ),
    Worker.STANDARD_REVIEW: StandardReviewResult(
        StandardReviewResultCode.REVIEW_RESULT_STALE, "bad"
    ),
    Worker.STANDARD_APPLY: ApplyResult(ApplyResultCode.REVIEW_RESULT_STALE, "bad"),
}


def requirement(type_name, state, entity_id="req-1", requirement_id="SDLC-FR-0001"):
    return RequirementRecord(
        id=entity_id,
        public_id="1",
        requirement_id=requirement_id,
        title="T",
        type_name=type_name,
        state=state,
        revision=1,
        project_id=PROJECT.id,
        source_fingerprint=None,
    )


def workspace_with(record):
    return FakeProcessorWorkspace(PROJECT, [record])


class FakeWorkers:
    """Records which worker ran and returns a canned typed result.

    `moves_to` makes the worker perform the State transition the real worker
    owns, so a completed route can be told apart from a stalled one.
    """

    def __init__(self, ws, result=None, moves_to=None):
        self.ws = ws
        self.result = result
        self.moves_to = moves_to
        self.calls = []

    def _worker(self, name):
        def run(entity_id, **options):
            self.calls.append((name, entity_id, options))
            if self.moves_to is not None:
                self.ws.set_requirement_state(entity_id, self.moves_to)
            return self.result

        return run

    def bound(self):
        return RequirementWorkers(
            process_raw=self._worker("process_raw"),
            process_standard=self._worker("process_standard"),
            review_standard=self._worker("review_standard"),
            apply_standard=self._worker("apply_standard"),
        )


def never(*_args, **_options):
    raise AssertionError("one dispatch runs exactly one worker")


def real_workers(ws, raw_model=None, process_model=None, review_model=None):
    return RequirementWorkers(
        process_raw=functools.partial(
            process_raw_requirement, ws, raw_model or FakeModelRuntime()
        ),
        process_standard=functools.partial(
            process_standard_requirement, ws, process_model or FakeModelRuntime()
        ),
        review_standard=functools.partial(
            review_standard_requirement, ws, review_model or FakeModelRuntime()
        ),
        apply_standard=functools.partial(apply_standard_requirement, ws),
    )


def dispatch_current(ws, workers, entity_id, status=NOT_PROCESSED):
    return dispatch(ws, workers, select_route(ws.requirements[entity_id], status))


# -- the route table -----------------------------------------------------------


def test_the_route_table_is_closed_to_the_four_rw_c04_routes():
    assert {(r.type_name, r.state, r.worker) for r in ROUTES.values()} == {
        (t, s, w) for t, s, w, _ in AUTHORIZED
    }


@pytest.mark.parametrize(
    ("type_name", "state", "worker", "after"), AUTHORIZED, ids=AUTHORIZED_IDS
)
def test_each_authorized_route_runs_exactly_its_one_worker(
    type_name, state, worker, after
):
    record = requirement(type_name, state)
    ws = workspace_with(record)
    workers = FakeWorkers(ws, NORMAL[worker], moves_to=after)

    selection = select_route(record, NOT_PROCESSED)
    result = dispatch(ws, workers.bound(), selection)

    assert selection.decision is RouteDecision.ROUTE_SELECTED
    assert selection.route.worker is worker
    assert result.outcome is DispatchOutcome.ROUTE_COMPLETED, result
    assert result.state_after == after
    assert [(name, entity) for name, entity, _ in workers.calls] == [
        (WORKER_NAME[worker], record.id)
    ]


@pytest.mark.parametrize(
    ("type_name", "state", "worker", "after"), AUTHORIZED, ids=AUTHORIZED_IDS
)
def test_only_standard_process_is_invoked_as_an_authorized_new_cycle(
    type_name, state, worker, after
):
    record = requirement(type_name, state)
    ws = workspace_with(record)
    workers = FakeWorkers(ws, NORMAL[worker], moves_to=after)

    dispatch(ws, workers.bound(), select_route(record, NOT_PROCESSED))

    [(_, _, options)] = workers.calls
    expected = (
        {"authorized_new_cycle": True} if worker is Worker.STANDARD_PROCESS else {}
    )
    assert options == expected


# -- status gating -------------------------------------------------------------


@pytest.mark.parametrize("status", CLAIMED_OR_SETTLED)
@pytest.mark.parametrize(
    ("type_name", "state", "worker", "after"), AUTHORIZED, ids=AUTHORIZED_IDS
)
def test_a_claimed_completed_or_failed_cycle_runs_no_worker(
    type_name, state, worker, after, status
):
    record = requirement(type_name, state)
    ws = workspace_with(record)
    workers = FakeWorkers(ws, NORMAL[worker], moves_to=after)

    selection = select_route(record, status)
    result = dispatch(ws, workers.bound(), selection)

    assert selection.decision is RouteDecision.STATUS_NOT_ELIGIBLE
    assert selection.route is None
    assert result.outcome is DispatchOutcome.NO_ROUTE
    assert workers.calls == [] and ws.mutations == []


# -- human boundaries, settled and unsupported states ------------------------

NO_WORKER_STATES = [
    ("Raw", "Draft", RouteDecision.HUMAN_BOUNDARY),
    ("Raw", "Review", RouteDecision.NO_MACHINE_WORK),
    ("Standard", "Draft", RouteDecision.NO_MACHINE_WORK),
    ("Standard", "Ready", RouteDecision.HUMAN_BOUNDARY),
    ("Standard", "Applied", RouteDecision.NO_MACHINE_WORK),
    ("Raw", "Ready", RouteDecision.UNSUPPORTED_STATE),
    ("Raw", "Apply", RouteDecision.UNSUPPORTED_STATE),
    ("Raw", "Applied", RouteDecision.UNSUPPORTED_STATE),
    ("Standard", "Archived", RouteDecision.UNSUPPORTED_STATE),
    (None, "Process", RouteDecision.UNSUPPORTED_STATE),
    ("Standard", None, RouteDecision.UNSUPPORTED_STATE),
]


@pytest.mark.parametrize("status", list(ProcessingStatus))
@pytest.mark.parametrize(
    ("type_name", "state", "decision"),
    NO_WORKER_STATES,
    ids=[f"{t}+{s}" for t, s, _ in NO_WORKER_STATES],
)
def test_no_worker_runs_outside_the_four_routes(type_name, state, decision, status):
    record = requirement(type_name, state)
    ws = workspace_with(record)
    workers = FakeWorkers(ws, NORMAL[Worker.STANDARD_PROCESS], moves_to="Review")

    selection = select_route(record, status)
    result = dispatch(ws, workers.bound(), selection)

    assert selection.decision is decision and selection.route is None
    assert result.outcome is DispatchOutcome.NO_ROUTE
    assert workers.calls == [] and ws.mutations == []
    assert ws.requirements[record.id] == record, "nothing is repaired or advanced"


def test_the_ready_verdict_plays_no_part_in_route_selection():
    for verdict in ("PASS", "NEEDS_WORK", "BLOCKING"):
        ws, record, _root, _ = build_ready_workspace(verdict=verdict)
        selection = select_route(ws.requirements[record.id], NOT_PROCESSED)
        assert selection.decision is RouteDecision.HUMAN_BOUNDARY


# -- stale selection -----------------------------------------------------------


@pytest.mark.parametrize(
    "change",
    [
        pytest.param({"state": "Ready"}, id="human-moved-state"),
        pytest.param({"type_name": "Raw"}, id="type-changed"),
        pytest.param({"requirement_id": "SDLC-FR-0999"}, id="identity-changed"),
        pytest.param(None, id="entity-gone"),
    ],
)
def test_a_stale_selection_runs_no_worker_and_corrects_nothing(change):
    record = requirement("Standard", "Process")
    ws = workspace_with(record)
    workers = FakeWorkers(ws, NORMAL[Worker.STANDARD_PROCESS], moves_to="Review")
    selection = select_route(record, NOT_PROCESSED)
    if change is None:
        del ws.requirements[record.id]
    else:
        ws.requirements[record.id] = replace(record, **change)
    changed = ws.requirements.get(record.id)

    result = dispatch(ws, workers.bound(), selection)

    assert result.outcome is DispatchOutcome.STALE_ROUTE, result
    assert workers.calls == [] and ws.mutations == []
    assert ws.requirements.get(record.id) == changed


def test_a_failed_revalidation_read_runs_no_worker():
    record = requirement("Standard", "Apply")
    ws = workspace_with(record)
    workers = FakeWorkers(ws, NORMAL[Worker.STANDARD_APPLY], moves_to="Applied")
    selection = select_route(record, NOT_PROCESSED)
    ws.failures["read_requirement"] = FiberyError("Fibery read timed out")

    result = dispatch(ws, workers.bound(), selection)

    assert result.outcome is DispatchOutcome.FIBERY_READ_FAILED
    assert workers.calls == [] and ws.mutations == []


# -- worker failure and lifecycle postconditions ------------------------------


@pytest.mark.parametrize(
    ("type_name", "state", "worker", "after"), AUTHORIZED, ids=AUTHORIZED_IDS
)
def test_a_failed_worker_never_advances_the_lifecycle(type_name, state, worker, after):
    record = requirement(type_name, state)
    ws = workspace_with(record)
    workers = FakeWorkers(ws, FAILED[worker])

    result = dispatch(ws, workers.bound(), select_route(record, NOT_PROCESSED))

    assert result.outcome is DispatchOutcome.WORKER_FAILED
    assert result.worker_result is FAILED[worker]
    assert ws.mutations == [] and ws.requirements[record.id].state == state


@pytest.mark.parametrize(
    ("type_name", "state", "worker", "after"), AUTHORIZED, ids=AUTHORIZED_IDS
)
def test_a_normal_result_that_leaves_the_state_is_not_a_completed_cycle(
    type_name, state, worker, after
):
    record = requirement(type_name, state)
    ws = workspace_with(record)
    workers = FakeWorkers(ws, NORMAL[worker])

    result = dispatch(ws, workers.bound(), select_route(record, NOT_PROCESSED))

    assert result.outcome is DispatchOutcome.POSTCONDITION_NOT_REACHED
    assert result.state_after == state
    assert ws.mutations == [], "the dispatcher writes no worker-owned transition"


def test_no_changes_to_process_in_process_is_not_a_completed_cycle():
    record = requirement("Standard", "Process")
    ws = workspace_with(record)
    stalled = StandardProcessResult(
        StandardProcessResultCode.NO_CHANGES_TO_PROCESS, "same"
    )
    workers = FakeWorkers(ws, stalled)

    result = dispatch(ws, workers.bound(), select_route(record, NOT_PROCESSED))

    assert result.outcome is DispatchOutcome.POSTCONDITION_NOT_REACHED
    assert result.worker_result.is_normal and result.state_after == "Process"
    assert ws.mutations == []


def test_no_changes_to_review_in_review_is_not_a_completed_cycle():
    ws, record, _root, _ = build_review_workspace()
    first = dispatch_current(
        ws,
        real_workers(ws, review_model=FakeModelRuntime([review_output()])),
        record.id,
    )
    assert first.outcome is DispatchOutcome.ROUTE_COMPLETED, first
    ws.set_requirement_state(record.id, "Review")  # a human sends it back unedited
    before = len(ws.mutations)
    model = FakeModelRuntime([review_output()])

    result = dispatch_current(ws, real_workers(ws, review_model=model), record.id)

    assert result.outcome is DispatchOutcome.POSTCONDITION_NOT_REACHED
    assert result.worker_result.code is StandardReviewResultCode.NO_CHANGES_TO_REVIEW
    assert result.state_after == "Review" and not model.was_invoked
    assert ws.mutations[before:] == [] and len(review_result_nodes(ws)) == 1


def test_a_failed_raw_worker_progresses_no_candidate():
    ws, raw, _ = build_workspace()
    workers = real_workers(ws, raw_model=FakeModelRuntime(["not json"]))

    result = dispatch_current(ws, workers, raw.id)

    assert result.outcome is DispatchOutcome.WORKER_FAILED
    assert result.worker_result.code is ProcessResultCode.INVALID_MODEL_OUTPUT
    assert ws.requirements[raw.id].state == "Process"
    assert not [r for r in ws.requirements.values() if r.type_name == "Standard"]


# -- CR-002: an unedited human rework is a new Standard Process cycle ----------


def ready_sent_back_unedited():
    ws, record, root, _ = build_ready_workspace(verdict="NEEDS_WORK")
    ws.set_requirement_state(record.id, "Process")  # the human rework, no edit
    return ws, ws.requirements[record.id], root


def test_an_ordinary_call_over_the_unchanged_tree_still_reports_no_changes():
    ws, record, _root = ready_sent_back_unedited()
    model = FakeModelRuntime([analysis_output()])

    result = process_standard_requirement(ws, model, record.id)

    assert result.code is StandardProcessResultCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked
    assert ws.requirements[record.id].state == "Process"


def test_the_dispatcher_turns_an_unedited_rework_into_the_next_iteration():
    ws, record, _root = ready_sent_back_unedited()
    history = [*process_result_nodes(ws), *review_result_nodes(ws)]
    evidence = {node.secret: ws.content[node.secret] for node in history}
    model = FakeModelRuntime([analysis_output()])

    result = dispatch_current(ws, real_workers(ws, process_model=model), record.id)

    assert result.outcome is DispatchOutcome.ROUTE_COMPLETED, result
    assert result.worker_result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert result.worker_result.iteration == 2
    assert len(model.calls) == 1
    assert result.state_after == "Review" == ws.requirements[record.id].state
    assert {secret: ws.content[secret] for secret in evidence} == evidence
    assert len(process_result_nodes(ws)) == 2
    assert review_result_nodes(ws) == [n for n in history if "Review Result" in n.name]


def test_an_edited_rework_keeps_the_existing_new_iteration_behavior():
    ws, record, root = ready_sent_back_unedited()
    ws.content[root.secret] += "\nThe human narrowed the scope.\n"
    model = FakeModelRuntime([analysis_output()])

    result = dispatch_current(ws, real_workers(ws, process_model=model), record.id)

    assert result.outcome is DispatchOutcome.ROUTE_COMPLETED, result
    assert result.worker_result.iteration == 2 and len(model.calls) == 1


def test_the_input_equality_ambiguity_is_not_bypassed():
    """Audit A11: tree == latest input != latest output still refuses."""
    ws, std, _root, node, _child, _x, _y = completed_then_reverted()
    before = len(ws.mutations)
    model = FakeModelRuntime([analysis_output()])

    result = dispatch_current(ws, real_workers(ws, process_model=model), std.id)
    direct = process_standard_requirement(ws, model, std.id, authorized_new_cycle=True)

    assert result.outcome is DispatchOutcome.WORKER_FAILED
    for outcome in (result.worker_result, direct):
        assert outcome.code is StandardProcessResultCode.PROCESSING_STATE_CONFLICT
        assert node.id in outcome.message
    assert not model.was_invoked
    assert ws.mutations[before:] == [] and process_result_nodes(ws) == [node]


@pytest.mark.parametrize("status", CLAIMED_OR_SETTLED)
def test_only_a_not_processed_cycle_can_request_a_new_iteration(status):
    ws, record, _root = ready_sent_back_unedited()
    model = FakeModelRuntime([analysis_output()])

    result = dispatch_current(
        ws, real_workers(ws, process_model=model), record.id, status
    )

    assert result.outcome is DispatchOutcome.NO_ROUTE
    assert not model.was_invoked and len(process_result_nodes(ws)) == 1


def test_the_new_cycle_entry_takes_no_explicit_option_and_has_no_cli_flag():
    ws, record, _root = ready_sent_back_unedited()
    [node] = process_result_nodes(ws)

    combined = process_standard_requirement(
        ws,
        FakeModelRuntime(),
        record.id,
        resume_result=node.id,
        authorized_new_cycle=True,
    )

    assert combined.code is StandardProcessResultCode.PROCESSING_STATE_CONFLICT
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            [
                "project",
                "requirement",
                "normalize",
                "--requirement",
                "x",
                "--authorized-new-cycle",
            ]
        )


# -- RAW inherited candidate progression ---------------------------------------

TWO = model_output([candidate(title="First"), candidate(title="Second")])
UNRELATED = RequirementRecord(
    id="std-unrelated",
    public_id="90",
    requirement_id="SDLC-FR-0090",
    title="Unrelated draft",
    type_name="Standard",
    state="Draft",
    revision=1,
    project_id="p-1",
    source_fingerprint=None,
)


def dispatch_raw(after_worker=None, response=TWO, standards=()):
    """Dispatch a RAW in Process through the real RAW processor.

    `after_worker(ws, result)` changes Fibery after the worker returned and
    before the dispatcher preflights, as a concurrent actor could.
    """
    ws, raw, _ = build_workspace(standards=standards)
    real = functools.partial(process_raw_requirement, ws, FakeModelRuntime([response]))
    marks = {}

    def raw_worker(entity_id):
        result = real(entity_id)
        if after_worker is not None:
            after_worker(ws, result)
        marks["after_worker"] = len(ws.mutations)
        return result

    workers = RequirementWorkers(
        process_raw=raw_worker,
        process_standard=never,
        review_standard=never,
        apply_standard=never,
    )
    result = dispatch_current(ws, workers, raw.id)
    return ws, raw, result, ws.mutations[marks.get("after_worker", 0) :]


def record_of(ws, requirement_id):
    return next(
        r for r in ws.requirements.values() if r.requirement_id == requirement_id
    )


def test_the_exact_candidates_of_a_successful_raw_result_move_to_process():
    ws, raw, result, writes = dispatch_raw(standards=[UNRELATED])

    assert result.outcome is DispatchOutcome.ROUTE_COMPLETED, result
    assert result.state_after == "Review" == ws.requirements[raw.id].state
    assert result.progressed == result.worker_result.candidates
    assert len(result.progressed) == 2
    for requirement_id in result.progressed:
        progressed = record_of(ws, requirement_id)
        assert (progressed.type_name, progressed.state) == ("Standard", "Process")
        assert raw.id in ws.derived_from_ids[progressed.id]
    assert writes == [
        f"set_requirement_state {record_of(ws, rid).id} Process"
        for rid in result.progressed
    ]
    assert ws.requirements[UNRELATED.id].state == "Draft", "generic Draft never moves"


def test_a_standard_merely_derived_from_the_raw_is_not_progressed():
    extra = replace(
        UNRELATED, id="std-extra", public_id="91", requirement_id="SDLC-FR-0091"
    )

    def also_derive(ws, _result):
        ws.requirements[extra.id] = extra
        ws.derived_from_ids[extra.id] = ["raw-uuid-1"]

    ws, _raw, result, _ = dispatch_raw(also_derive)

    assert result.outcome is DispatchOutcome.ROUTE_COMPLETED, result
    assert extra.requirement_id not in result.progressed
    assert ws.requirements[extra.id].state == "Draft"


def mutate_first(**changes):
    def change(ws, result):
        target = record_of(ws, result.candidates[0])
        ws.requirements[target.id] = replace(target, **changes)

    return change


@pytest.mark.parametrize(
    ("after_worker", "problem"),
    [
        pytest.param(mutate_first(state="Ready"), "not Draft", id="already-past-draft"),
        pytest.param(mutate_first(type_name="Raw"), "not Standard", id="wrong-type"),
        pytest.param(
            lambda ws, result: ws.derived_from_ids.update(
                {record_of(ws, result.candidates[0]).id: []}
            ),
            "does not derive from",
            id="missing-provenance",
        ),
        pytest.param(
            lambda ws, result: ws.requirements.update(
                {
                    "std-twin": replace(
                        record_of(ws, result.candidates[0]), id="std-twin"
                    )
                }
            ),
            "more than one Requirement",
            id="ambiguous-id",
        ),
    ],
)
def test_a_preflight_conflict_progresses_no_candidate_and_demotes_nothing(
    after_worker, problem
):
    ws, _raw, result, writes = dispatch_raw(after_worker)

    assert result.outcome is DispatchOutcome.CANDIDATE_PROGRESSION_CONFLICT, result
    assert writes == [], "no candidate State write, not even for valid peers"
    assert result.progressed == ()
    assert any(problem in detail for detail in result.details), result.details
    first, second = (record_of(ws, rid) for rid in result.worker_result.candidates)
    assert second.state == "Draft", "the untouched valid peer is not progressed"
    if problem == "not Draft":
        assert first.state == "Ready", "never demoted"


def test_a_failed_first_progression_write_is_reported_and_nothing_moves():
    def fail_writes(ws, _result):
        ws.failures["set_requirement_state"] = FiberyError("rate limited")

    ws, _raw, result, _ = dispatch_raw(fail_writes)

    assert result.outcome is DispatchOutcome.CANDIDATE_PROGRESSION_FAILED
    assert result.progressed == ()
    assert all(
        record_of(ws, rid).state == "Draft" for rid in result.worker_result.candidates
    )


def test_a_later_progression_write_failure_is_partial_and_never_rolled_back():
    def fail_second_write(ws, _result):
        real = ws.set_requirement_state
        attempts = []

        def flaky(entity_id, state):
            attempts.append(entity_id)
            if len(attempts) == 2:
                raise FiberyError("connection dropped")
            real(entity_id, state)

        ws.set_requirement_state = flaky

    ws, _raw, result, _ = dispatch_raw(fail_second_write)

    first, second = result.worker_result.candidates
    assert result.outcome is DispatchOutcome.PARTIAL_CANDIDATE_PROGRESSION
    assert result.progressed == (first,)
    assert record_of(ws, first).state == "Process", "not rolled back"
    assert record_of(ws, second).state == "Draft"
    assert second in result.details[0]


def test_a_raw_result_without_candidates_completes_with_nothing_to_progress():
    empty = model_output([], reason="The source records only open questions.")

    _ws, _raw, result, writes = dispatch_raw(response=empty)

    assert result.outcome is DispatchOutcome.ROUTE_COMPLETED
    assert result.progressed == () and writes == []


# -- replay: completed durable work is never redone ----------------------------


def durable(ws):
    return (len(ws.documents), dict(ws.content), dict(ws.requirements))


def test_redispatching_a_completed_raw_duplicates_nothing():
    ws, raw, first, _ = dispatch_raw()
    assert first.outcome is DispatchOutcome.ROUTE_COMPLETED
    before = durable(ws)
    workers = RequirementWorkers(
        process_raw=never,
        process_standard=never,
        review_standard=never,
        apply_standard=never,
    )

    again = select_route(ws.requirements[raw.id], NOT_PROCESSED)
    replayed = dispatch(ws, workers, first.selection)

    assert again.decision is RouteDecision.NO_MACHINE_WORK
    assert dispatch(ws, workers, again).outcome is DispatchOutcome.NO_ROUTE
    assert replayed.outcome is DispatchOutcome.STALE_ROUTE
    assert durable(ws) == before


def test_after_standard_process_only_a_new_review_cycle_is_selectable():
    ws, record, _root = ready_sent_back_unedited()
    first = dispatch_current(
        ws,
        real_workers(ws, process_model=FakeModelRuntime([analysis_output()])),
        record.id,
    )
    assert first.outcome is DispatchOutcome.ROUTE_COMPLETED
    before = durable(ws)
    workers = RequirementWorkers(
        process_raw=never,
        process_standard=never,
        review_standard=never,
        apply_standard=never,
    )
    current = ws.requirements[record.id]

    assert select_route(current, NOT_PROCESSED).route.worker is Worker.STANDARD_REVIEW
    for status in CLAIMED_OR_SETTLED:
        assert select_route(current, status).route is None
    assert dispatch(ws, workers, first.selection).outcome is DispatchOutcome.STALE_ROUTE
    assert durable(ws) == before and len(process_result_nodes(ws)) == 2


def test_review_stops_at_ready_and_ready_selects_no_worker():
    ws, record, _root, _ = build_review_workspace()
    first = dispatch_current(
        ws,
        real_workers(ws, review_model=FakeModelRuntime([review_output()])),
        record.id,
    )
    assert first.outcome is DispatchOutcome.ROUTE_COMPLETED
    before = durable(ws)
    workers = RequirementWorkers(
        process_raw=never,
        process_standard=never,
        review_standard=never,
        apply_standard=never,
    )

    ready = select_route(ws.requirements[record.id], NOT_PROCESSED)

    assert ready.decision is RouteDecision.HUMAN_BOUNDARY
    assert dispatch(ws, workers, first.selection).outcome is DispatchOutcome.STALE_ROUTE
    assert durable(ws) == before


def test_an_applied_requirement_selects_no_worker_and_is_not_reapplied():
    ws, record, _root, _ = build_ready_workspace()
    ws.set_requirement_state(record.id, "Apply")  # the human approval
    first = dispatch_current(ws, real_workers(ws), record.id)
    assert first.outcome is DispatchOutcome.ROUTE_COMPLETED, first
    before = durable(ws)
    workers = RequirementWorkers(
        process_raw=never,
        process_standard=never,
        review_standard=never,
        apply_standard=never,
    )

    applied = select_route(ws.requirements[record.id], NOT_PROCESSED)

    assert applied.decision is RouteDecision.NO_MACHINE_WORK
    assert dispatch(ws, workers, first.selection).outcome is DispatchOutcome.STALE_ROUTE
    assert durable(ws) == before
