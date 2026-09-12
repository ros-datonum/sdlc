"""RW-O04: the complete state-driven Requirement lifecycle, end to end.

Every stage runs the real production stack:

    requirement_runner.run_cycle
        -> RW-O02 dispatcher
            -> real RAW Processor / Standard Process / Standard Review / Apply

Nothing here mocks the runner, the dispatcher or a worker. The only doubles
are the existing Fibery fake, `FakeModelRuntime` with bounded structured
responses, and the reset automation that RW-O03/CR-003 verified live.

A human appears exactly as a State write in Fibery: `Raw Draft -> Process`,
`Ready -> Process` and `Ready -> Apply`. No processor, review, approve, rework
or apply command is invoked anywhere in the journey, and the machine performs
every other transition itself.
"""

from __future__ import annotations

import functools

from processor_fake import FakeModelRuntime, build_workspace, candidate, model_output
from review_fake import review_output, review_results
from sdlc.process_result import parse_process_result_name
from sdlc.raw_processor import process_raw_requirement
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.requirement_dispatcher import DispatchOutcome, RequirementWorkers
from sdlc.requirement_runner import CycleOutcome, run_cycle
from sdlc.results import (
    ApplyResultCode,
    ProcessResultCode,
    StandardProcessResultCode,
    StandardReviewResultCode,
)
from sdlc.review_result import parse_review_result_name
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import analysis_output, build_standard_workspace, process_results
from test_requirement_runner import (
    FAILED_STATUS,
    NOT_PROCESSED,
    PROCESSING,
    SUCCEEDED,
    StatusWorkspace,
)

PROCESSING_RESULT_SUFFIX = "Processing Result"
# The two mutation kinds that change the visible Processing Status: the Fibery
# automation's reset, and the runner's own write.
STATUS_EVENTS = ("automation_reset", "set_processing_status")


class LifecycleWorkspace(StatusWorkspace):
    """The RW-O03 status fake, with the automation reset in the mutation log.

    RW-O03's fake records resets separately, which is enough to assert that
    one happened. RW-O04 has to prove the *order* of

        State transition -> automation reset -> Processing claim -> final status

    so the reset is appended to the same ordered history as every other write.
    Nothing else changes: the reset targets, the workers' own transitions and
    the runner's writes are exactly RW-O03's.
    """

    def set_requirement_state(self, entity_id, state):
        before = len(self.resets)
        super().set_requirement_state(entity_id, state)
        if len(self.resets) > before:
            self.inner.mutations.append(f"automation_reset {entity_id} {NOT_PROCESSED}")


def bound_workers(ws, raw_model, process_model, review_model):
    """The four real capabilities, bound to one workspace and its runtimes."""
    return RequirementWorkers(
        process_raw=functools.partial(process_raw_requirement, ws, raw_model),
        process_standard=functools.partial(
            process_standard_requirement, ws, process_model
        ),
        review_standard=functools.partial(
            review_standard_requirement, ws, review_model
        ),
        apply_standard=functools.partial(apply_standard_requirement, ws),
    )


def status_history(ws, entity_id):
    """Every visible Processing Status value of one Requirement, in order."""
    prefixes = tuple(f"{event} {entity_id} " for event in STATUS_EVENTS)
    return [
        mutation.split(" ", 2)[2]
        for mutation in ws.mutations
        if mutation.startswith(prefixes)
    ]


def documents(ws):
    """Every durable Document: id -> (name, parent, body)."""
    return {
        node.id: (node.name, node.parent_document_id, ws.content.get(node.secret, ""))
        for node in ws.inner.documents
    }


def requirements(ws):
    """Every durable Requirement record, by entity id."""
    return dict(ws.inner.requirements)


def edges_of(ws, entity_id):
    relations = ws.inner.requirement_relations(entity_id)
    return (relations.depends_on, relations.affects)


def processing_results(ws):
    return [d for d in ws.inner.documents if d.name.endswith(PROCESSING_RESULT_SUFFIX)]


def iterations(nodes, parse_name):
    return sorted(parse_name(node.name)[1] for node in nodes)


def human_moves(ws, entity_id, state):
    """A person editing State in Fibery: one State write, nothing else."""
    ws.set_requirement_state(entity_id, state)


# -- the complete journey ---------------------------------------------------------


def test_the_complete_state_driven_requirement_lifecycle():
    inner, raw, _raw_root = build_workspace(raw_state="Draft")
    ws = LifecycleWorkspace(inner)
    raw_model = FakeModelRuntime([model_output([candidate()])])
    process_model = FakeModelRuntime([analysis_output(), analysis_output()])
    review_model = FakeModelRuntime([review_output(), review_output()])
    workers = bound_workers(ws, raw_model, process_model, review_model)

    # -- Phase 1: RAW Draft waits for the human ---------------------------------
    quiet = list(ws.mutations)
    assert run_cycle(ws, workers).outcome is CycleOutcome.IDLE
    assert ws.mutations == quiet, "the runner may not touch a RAW in Draft"
    assert not raw_model.was_invoked
    assert inner.requirements[raw.id].state == "Draft"
    assert ws.status_of(raw.id) == NOT_PROCESSED

    # -- Phase 2: the human starts RAW processing -------------------------------
    human_moves(ws, raw.id, "Process")
    assert ws.status_of(raw.id) == NOT_PROCESSED, "the automation reset the cycle"

    mark = len(ws.mutations)
    report = run_cycle(ws, workers)

    assert report.outcome is CycleOutcome.SUCCEEDED, report
    assert report.dispatch_result.outcome is DispatchOutcome.ROUTE_COMPLETED
    assert report.dispatch_result.worker_result.code is (
        ProcessResultCode.RAW_REQUIREMENT_PROCESSED
    )
    during = ws.mutations[mark:]
    assert during[0] == f"set_processing_status {raw.id} {PROCESSING}", (
        "the claim precedes every worker write"
    )
    assert during.index(f"set_requirement_state {raw.id} Review") > 0
    assert inner.requirements[raw.id].state == "Review"
    assert ws.status_of(raw.id) == SUCCEEDED
    assert status_history(ws, raw.id) == [NOT_PROCESSED, PROCESSING, SUCCEEDED]
    assert len(processing_results(ws)) == 1
    assert len(raw_model.calls) == 1

    # the exact candidate of that RAW result, progressed by RW-O02 only
    [standard_id] = inner.produces(raw.id)
    standard = inner.requirements[standard_id]
    assert standard.type_name == "Standard"
    assert standard.state == "Process"
    assert ws.status_of(standard_id) == NOT_PROCESSED
    assert report.dispatch_result.progressed == (standard.requirement_id,)
    assert status_history(ws, standard_id) == [NOT_PROCESSED]

    # what the RAW cycle made durable, to compare against at the end
    raw_processing_result = processing_results(ws)[0]
    raw_processing_body = inner.content[raw_processing_result.secret]
    raw_candidates = inner.produces(raw.id)

    # -- Phase 3: Standard Process runs automatically ---------------------------
    mark = len(ws.mutations)
    report = run_cycle(ws, workers)

    assert report.outcome is CycleOutcome.HANDED_OFF, report
    assert report.dispatch_result.outcome is DispatchOutcome.ROUTE_COMPLETED
    assert report.dispatch_result.worker_result.code is (
        StandardProcessResultCode.REQUIREMENT_PROCESSED
    )
    assert report.dispatch_result.worker_result.iteration == 1
    during = ws.mutations[mark:]
    assert during[0] == f"set_processing_status {standard_id} {PROCESSING}"
    assert during[-1] == f"automation_reset {standard_id} {NOT_PROCESSED}", (
        "the worker's Process -> Review is the last write, and the automation's "
        "reset of the new Review cycle follows it"
    )
    assert f"set_processing_status {standard_id} {SUCCEEDED}" not in during, (
        "the runner must not write Succeeded over the Review cycle's reset"
    )
    assert len(process_results(inner)) == 1
    assert inner.requirements[standard_id].state == "Review"
    assert ws.status_of(standard_id) == NOT_PROCESSED
    assert status_history(ws, standard_id) == [
        NOT_PROCESSED,
        PROCESSING,
        NOT_PROCESSED,
    ]

    # -- Phase 4: Standard Review runs automatically ----------------------------
    report = run_cycle(ws, workers)

    assert report.outcome is CycleOutcome.SUCCEEDED, report
    assert report.dispatch_result.worker_result.code is (
        StandardReviewResultCode.REQUIREMENT_REVIEWED
    )
    assert inner.requirements[standard_id].state == "Ready"
    assert ws.status_of(standard_id) == SUCCEEDED
    assert len(review_results(inner)) == 1

    # Ready is a human boundary: the verdict does not open it
    ready_documents, ready_requirements = documents(ws), requirements(ws)
    assert run_cycle(ws, workers).outcome is CycleOutcome.IDLE
    assert run_cycle(ws, workers).outcome is CycleOutcome.IDLE
    assert documents(ws) == ready_documents
    assert requirements(ws) == ready_requirements
    assert len(process_model.calls) == 1
    assert len(review_model.calls) == 1

    # -- Phase 5: the human asks for rework, without editing anything -----------
    process_one = process_results(inner)[0]
    review_one = review_results(inner)[0]
    process_one_body = inner.content[process_one.secret]
    review_one_body = inner.content[review_one.secret]

    human_moves(ws, standard_id, "Process")
    assert ws.status_of(standard_id) == NOT_PROCESSED

    report = run_cycle(ws, workers)

    assert report.outcome is CycleOutcome.HANDED_OFF, report
    assert report.dispatch_result.worker_result.code is (
        StandardProcessResultCode.REQUIREMENT_PROCESSED
    )
    assert report.dispatch_result.worker_result.iteration == 2, (
        "an unedited rework still starts the authorized new cycle (CR-002)"
    )
    assert len(process_model.calls) == 2, "the model ran once for iteration 2"
    assert inner.requirements[standard_id].state == "Review"
    assert ws.status_of(standard_id) == NOT_PROCESSED
    assert status_history(ws, standard_id)[-3:] == [
        NOT_PROCESSED,
        PROCESSING,
        NOT_PROCESSED,
    ], "the rework cycle handed off without writing Succeeded"

    # iteration 1 history survives the rework, by identity and by content
    assert process_one.id in documents(ws)
    assert review_one.id in documents(ws)
    assert inner.content[process_one.secret] == process_one_body
    assert inner.content[review_one.secret] == review_one_body
    assert iterations(process_results(inner), parse_process_result_name) == [1, 2]

    report = run_cycle(ws, workers)

    assert report.outcome is CycleOutcome.SUCCEEDED, report
    assert inner.requirements[standard_id].state == "Ready"
    assert ws.status_of(standard_id) == SUCCEEDED
    assert iterations(review_results(inner), parse_review_result_name) == [1, 2]
    assert inner.content[process_one.secret] == process_one_body
    assert inner.content[review_one.secret] == review_one_body

    assert run_cycle(ws, workers).outcome is CycleOutcome.IDLE

    # -- Phase 6: the human approves --------------------------------------------
    human_moves(ws, standard_id, "Apply")
    assert ws.status_of(standard_id) == NOT_PROCESSED

    report = run_cycle(ws, workers)

    assert report.outcome is CycleOutcome.SUCCEEDED, report
    assert report.dispatch_result.worker_result.code is (
        ApplyResultCode.REQUIREMENT_APPLIED
    )
    assert inner.requirements[standard_id].state == "Applied"
    assert ws.status_of(standard_id) == SUCCEEDED

    # -- replay: repeated observation duplicates nothing durable ----------------
    applied_documents = documents(ws)
    applied_requirements = requirements(ws)
    applied_edges = edges_of(ws, standard_id)
    for _ in range(3):
        assert run_cycle(ws, workers).outcome is CycleOutcome.IDLE
    assert documents(ws) == applied_documents
    assert requirements(ws) == applied_requirements
    assert edges_of(ws, standard_id) == applied_edges

    # the RAW cycle, observed repeatedly since Phase 2, ran exactly once
    assert len(processing_results(ws)) == 1
    assert inner.content[raw_processing_result.secret] == raw_processing_body
    assert inner.produces(raw.id) == raw_candidates
    assert status_history(ws, raw.id) == [NOT_PROCESSED, PROCESSING, SUCCEEDED]
    assert len(process_results(inner)) == 2
    assert len(review_results(inner)) == 2
    assert len(raw_model.calls) == 1
    assert len(process_model.calls) == 2
    assert len(review_model.calls) == 2

    # -- the visible Processing Status story, start to finish -------------------
    assert status_history(ws, standard_id) == [
        NOT_PROCESSED,  # inherited Draft -> Process
        PROCESSING,  # runner claim
        NOT_PROCESSED,  # Process -> Review: the next cycle's reset, kept
        PROCESSING,  # runner claim for Review
        SUCCEEDED,  # Review -> Ready
        NOT_PROCESSED,  # human rework Ready -> Process
        PROCESSING,
        NOT_PROCESSED,  # Process -> Review again
        PROCESSING,
        SUCCEEDED,  # Review -> Ready again
        NOT_PROCESSED,  # human approval Ready -> Apply
        PROCESSING,
        SUCCEEDED,  # Apply -> Applied
    ]


# -- Apply still revalidates the reviewed state -----------------------------------


def reach_ready(ws, workers, entity_id):
    """Drive Process and Review through the runner until the human boundary."""
    assert run_cycle(ws, workers).outcome is CycleOutcome.HANDED_OFF
    assert run_cycle(ws, workers).outcome is CycleOutcome.SUCCEEDED
    assert ws.inner.requirements[entity_id].state == "Ready"
    assert ws.status_of(entity_id) == SUCCEEDED


def test_stale_reviewed_content_fails_closed_on_state_driven_apply():
    inner, requirement, root = build_standard_workspace()
    ws = LifecycleWorkspace(inner)
    workers = bound_workers(
        ws,
        FakeModelRuntime(),
        FakeModelRuntime([analysis_output()]),
        FakeModelRuntime([review_output()]),
    )
    reach_ready(ws, workers, requirement.id)

    human_moves(ws, requirement.id, "Apply")
    assert ws.status_of(requirement.id) == NOT_PROCESSED
    # A human edits the reviewed content after the review and before Apply.
    inner.content[root.secret] += "\n## Added after the review\n\nUnreviewed.\n"
    edges_before = edges_of(ws, requirement.id)
    review_count = len(review_results(inner))

    report = run_cycle(ws, workers)

    assert report.outcome is CycleOutcome.FAILED, report
    assert report.dispatch_result.outcome is DispatchOutcome.WORKER_FAILED
    assert report.dispatch_result.worker_result.code is (
        ApplyResultCode.REVIEW_RESULT_STALE
    )
    assert inner.requirements[requirement.id].state == "Apply", "no false advance"
    assert ws.status_of(requirement.id) == FAILED_STATUS
    assert edges_of(ws, requirement.id) == edges_before, "no fabricated relation"
    assert len(review_results(inner)) == review_count
    assert status_history(ws, requirement.id)[-3:] == [
        NOT_PROCESSED,
        PROCESSING,
        FAILED_STATUS,
    ]

    # Failed work is never retried automatically.
    failed_documents = documents(ws)
    for _ in range(2):
        assert run_cycle(ws, workers).outcome is CycleOutcome.IDLE
    assert documents(ws) == failed_documents
    assert inner.requirements[requirement.id].state == "Apply"
    assert ws.status_of(requirement.id) == FAILED_STATUS
