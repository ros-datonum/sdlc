"""Iterations, no-change detection and same-attempt resume."""

import pytest

from processor_fake import FakeModelRuntime
from sdlc.fibery_workspace import FiberyError
from sdlc.process_result import parse_process_result
from sdlc.results import StandardProcessResultCode
from sdlc.standard_processor import process_standard_requirement
from standard_fake import (
    REQUIREMENT_ID,
    analysis_output,
    build_standard_workspace,
    process_results,
    set_state,
)

OUTPUT = analysis_output()
CHANGED = analysis_output({"requirement": "The runtime must refuse anonymous calls."})


def run(ws, record, model):
    return process_standard_requirement(ws, model, record.id)


# -- no-change --------------------------------------------------------------


def test_reentering_process_unchanged_does_no_work():
    """Status toggling must not shake out a different answer."""
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([OUTPUT]))
    set_state(ws, std, "Process")
    document = ws.content["std-secret"]
    mutations = list(ws.mutations)

    model = FakeModelRuntime([CHANGED])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked
    assert len(process_results(ws)) == 1, "no new Process Result"
    assert ws.content["std-secret"] == document, "no document rewrite"
    assert ws.mutations == mutations, "no Fibery mutation of any kind"
    assert ws.requirements[std.id].state == "Process", "State is preserved"


def test_no_change_leaves_the_document_and_state_alone():
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([OUTPUT]))
    set_state(ws, std, "Process")
    document = ws.content["std-secret"]

    result = run(ws, std, FakeModelRuntime([CHANGED]))

    assert ws.content["std-secret"] == document
    assert result.iteration == 1
    # A deliberate return to Process is never silently undone.
    assert ws.requirements[std.id].state == "Process"


def test_no_change_is_a_normal_outcome():
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([OUTPUT]))
    set_state(ws, std, "Process")

    assert run(ws, std, FakeModelRuntime([CHANGED])).is_normal


# -- second iteration -------------------------------------------------------


def test_an_edited_document_starts_a_second_iteration():
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([OUTPUT]))
    ws.content["std-secret"] += "\nA deliberate human edit.\n"
    set_state(ws, std, "Process")

    model = FakeModelRuntime([CHANGED])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert model.was_invoked
    assert result.iteration == 2
    assert [d.name for d in process_results(ws)] == [
        f"{REQUIREMENT_ID} — Process Result 0001",
        f"{REQUIREMENT_ID} — Process Result 0002",
    ]


def test_a_second_iteration_leaves_the_first_untouched():
    """Earlier iterations are immutable process history."""
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([OUTPUT]))
    first = process_results(ws)[0]
    original = ws.content[first.secret]
    ws.content["std-secret"] += "\nAn edit.\n"
    set_state(ws, std, "Process")

    run(ws, std, FakeModelRuntime([CHANGED]))

    assert ws.content[first.secret] == original


def test_iteration_numbers_are_monotonic():
    ws, std, _ = build_standard_workspace()
    for index in range(3):
        run(ws, std, FakeModelRuntime([analysis_output({"rationale": f"r{index}"})]))
        ws.content["std-secret"] += f"\nedit {index}\n"
        set_state(ws, std, "Process")

    persisted = [
        parse_process_result(ws.content[d.secret]).iteration
        for d in process_results(ws)
    ]
    assert persisted == [1, 2, 3]


def test_the_second_iteration_records_the_edited_input():
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([OUTPUT]))
    first = parse_process_result(ws.content[process_results(ws)[0].secret])
    ws.content["std-secret"] += "\nAn edit.\n"
    set_state(ws, std, "Process")

    run(ws, std, FakeModelRuntime([CHANGED]))

    second = parse_process_result(ws.content[process_results(ws)[1].secret])
    assert second.input_fingerprint != first.output_fingerprint
    assert second.iteration == 2


def test_revision_is_unchanged_across_iterations():
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([OUTPUT]))
    ws.content["std-secret"] += "\nAn edit.\n"
    set_state(ws, std, "Process")

    run(ws, std, FakeModelRuntime([CHANGED]))

    assert ws.requirements[std.id].revision == 1


# -- same-attempt resume ----------------------------------------------------

FAILURE_POINTS = ["write_document_content", "set_requirement_state"]


def fail_after_process_result(ws, call):
    """Fail a call, but only after the Process Result has been written."""
    original = getattr(ws, call)
    seen = {"n": 0}

    def guarded(*args, **kwargs):
        seen["n"] += 1
        if call == "write_document_content" and seen["n"] <= 1:
            return original(*args, **kwargs)
        raise FiberyError("induced")

    setattr(ws, call, guarded)
    return original


@pytest.mark.parametrize("call", FAILURE_POINTS)
def test_a_failure_after_the_process_result_leaves_the_requirement_in_process(call):
    ws, std, _ = build_standard_workspace()
    fail_after_process_result(ws, call)

    result = run(ws, std, FakeModelRuntime([OUTPUT]))

    assert result.code is StandardProcessResultCode.PARTIAL_PROCESSING
    assert ws.requirements[std.id].state == "Process"
    assert len(process_results(ws)) == 1


def test_retry_after_a_failed_root_rewrite_resumes_and_completes():
    """The unambiguous case: the normalized document never landed."""
    ws, std, _ = build_standard_workspace()
    original = fail_after_process_result(ws, "write_document_content")
    first = run(ws, std, FakeModelRuntime([OUTPUT]))
    assert first.code is StandardProcessResultCode.PARTIAL_PROCESSING
    ws.write_document_content = original
    set_state(ws, std, "Process")

    model = FakeModelRuntime([CHANGED])
    result = run(ws, std, model)

    assert not model.was_invoked, "resume must not re-invoke the model"
    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert result.iteration == 1
    assert len(process_results(ws)) == 1, "no second iteration for the same input"
    assert ws.requirements[std.id].state == "Review", "the run is completed"


def test_a_failure_before_the_process_result_may_retry_the_model():
    ws, std, _ = build_standard_workspace()
    ws.failures["create_child_document"] = FiberyError("induced")

    result = run(ws, std, FakeModelRuntime([OUTPUT]))

    assert result.code is StandardProcessResultCode.PROCESS_RESULT_WRITE_FAILED
    assert process_results(ws) == []
    assert ws.content["std-secret"].startswith(f"# {REQUIREMENT_ID}")

    model = FakeModelRuntime([OUTPUT])
    assert run(ws, std, model).code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert model.was_invoked


def test_a_model_failure_creates_nothing():
    from sdlc.model_runtime import ModelRuntimeError

    ws, std, _ = build_standard_workspace()

    result = run(ws, std, FakeModelRuntime(error=ModelRuntimeError("no cli")))

    assert result.code is StandardProcessResultCode.MODEL_RUNTIME_FAILED
    assert ws.mutations == []


def test_malformed_model_output_creates_nothing():
    ws, std, _ = build_standard_workspace()

    result = run(ws, std, FakeModelRuntime(["I think it needs auth."]))

    assert result.code is StandardProcessResultCode.INVALID_MODEL_OUTPUT
    assert ws.mutations == []
    assert ws.requirements[std.id].state == "Process"
