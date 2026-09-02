"""Canonical fingerprints and the three-way iteration state machine.

These pin the two defects found at freeze review:

B1  document_fingerprint used a different normalization from content_equivalent,
    so Fibery's Markdown re-serialization forged new iterations.
B2  an unchanged deliberate re-entry was transitioned back to Review, silently
    undoing a human's move to Process.
"""

import pytest

from processor_fake import FakeModelRuntime, reserialize_like_fibery
from sdlc.process_result import document_fingerprint, parse_process_result
from sdlc.raw_source import content_equivalent
from sdlc.results import StandardProcessResultCode
from sdlc.standard_processor import process_standard_requirement
from standard_fake import (
    analysis_output,
    build_standard_workspace,
    process_results,
    set_state,
)

BULLETED = analysis_output(
    {
        "requirement": "The runtime must:\n- refuse API keys\n- refuse OpenRouter",
        "constraints_edge_cases": "Applies when:\n- offline\n- rate limited",
    }
)
EDITED = analysis_output({"requirement": "The runtime must refuse anonymous calls."})


def run(ws, record, model):
    return process_standard_requirement(ws, model, record.id)


# -- B1: fingerprints agree with content equivalence ------------------------

SERIALIZATION_CASES = [
    ("bullet marker", "- one\n- two\n"),
    ("paragraph then list", "Intro:\n- one\n- two\n"),
    ("nested list", "- one\n  - nested\n"),
    ("document", "# X — T\n\n## Requirement\n\nThe runtime must:\n- a\n- b\n"),
]


@pytest.mark.parametrize(("label", "written"), SERIALIZATION_CASES)
def test_fingerprints_follow_content_equivalence(label, written):
    """The invariant: equivalent content must fingerprint identically."""
    stored = reserialize_like_fibery(written)

    assert content_equivalent(stored, written)
    assert document_fingerprint(stored) == document_fingerprint(written)


SEMANTIC_CHANGES = [
    ("removed text", "A.\n\nB.\n", "A.\n"),
    ("added normative text", "- alpha\n", "- alpha\n- beta\n"),
    ("changed wording", "must refuse keys\n", "must allow keys\n"),
    ("changed value", "timeout is 30s\n", "timeout is 60s\n"),
    ("changed list item", "- alpha\n- beta\n", "- alpha\n- gamma\n"),
    ("missing section", "## A\n\nx\n\n## B\n\ny\n", "## A\n\nx\n"),
    ("changed heading", "## Non-Goals\n\nx\n", "## Non Goals\n\nx\n"),
    ("negation flipped", "must not fall back\n", "must fall back\n"),
    ("truncation", "line one\nline two\n", "line one\n"),
]


@pytest.mark.parametrize(("label", "before", "after"), SEMANTIC_CHANGES)
def test_semantic_changes_still_change_the_fingerprint(label, before, after):
    """Only known serialization differences may collapse."""
    assert document_fingerprint(before) != document_fingerprint(after)
    assert not content_equivalent(after, before)


def test_reserialization_does_not_forge_a_new_iteration():
    """B1 end to end: the defect burned a model call on every re-entry."""
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([BULLETED]))
    set_state(ws, std, "Process")

    model = FakeModelRuntime([EDITED])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked
    assert len(process_results(ws)) == 1


def test_a_real_edit_to_a_bulleted_requirement_still_starts_an_iteration():
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([BULLETED]))
    ws.content["std-secret"] += "\nA deliberate human edit.\n"
    set_state(ws, std, "Process")

    model = FakeModelRuntime([EDITED])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert result.iteration == 2
    assert len(model.calls) == 1


# -- B2: a deliberate return to Process is preserved -------------------------


def test_unchanged_re_entry_mutates_nothing_at_all():
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([analysis_output()]))
    assert ws.requirements[std.id].state == "Review"

    set_state(ws, std, "Process")
    document = ws.content["std-secret"]
    mutations = list(ws.mutations)
    relations = dict(ws.derived_from_ids)

    model = FakeModelRuntime([EDITED])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked
    assert len(process_results(ws)) == 1
    assert ws.content["std-secret"] == document
    assert ws.derived_from_ids == relations
    assert ws.requirements[std.id].revision == 1
    assert ws.mutations == mutations, "zero Fibery mutations"
    assert ws.requirements[std.id].state == "Process", "the human's move stands"


def test_repeated_unchanged_re_entry_stays_stable():
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([analysis_output()]))
    set_state(ws, std, "Process")

    for _ in range(3):
        model = FakeModelRuntime([EDITED])
        result = run(ws, std, model)
        assert result.code is StandardProcessResultCode.NO_CHANGES_TO_PROCESS
        assert not model.was_invoked

    assert len(process_results(ws)) == 1
    assert ws.requirements[std.id].state == "Process"


# -- B2: failed final transition, and its accepted consequence ---------------


def silently_drop_transition(ws, record):
    real = ws.set_requirement_state

    def guarded(entity_id, state):
        if entity_id == record.id and state == "Review":
            return
        return real(entity_id, state)

    ws.set_requirement_state = guarded
    return real


def test_a_failed_transition_is_reported_and_not_claimed_as_review():
    ws, std, _ = build_standard_workspace()
    silently_drop_transition(ws, std)

    result = run(ws, std, FakeModelRuntime([analysis_output()]))

    assert result.code is StandardProcessResultCode.PARTIAL_PROCESSING
    assert not result.is_normal, "must not claim the Requirement reached Review"
    assert ws.requirements[std.id].state == "Process"
    assert len(process_results(ws)) == 1


def test_retry_after_a_failed_transition_is_conservative():
    """Accepted v0.1 behaviour.

    The snapshot is indistinguishable from a deliberate unchanged re-entry, so
    the processor does not guess. Recovery is manual; the first invocation
    reported the failure explicitly.
    """
    ws, std, _ = build_standard_workspace()
    real = silently_drop_transition(ws, std)
    run(ws, std, FakeModelRuntime([analysis_output()]))
    ws.set_requirement_state = real

    model = FakeModelRuntime([EDITED])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked
    assert len(process_results(ws)) == 1
    assert ws.requirements[std.id].state == "Process"


# -- the three-way state machine --------------------------------------------


def test_branch_a_unfinished_rewrite_resumes_the_same_iteration():
    """current == latest.input_fingerprint"""
    ws, std, _ = build_standard_workspace()
    real = ws.write_document_content
    seen = {"n": 0}

    def fail_the_root_rewrite(secret, markdown):
        seen["n"] += 1
        if seen["n"] > 1:
            raise __import__("sdlc.fibery_workspace", fromlist=["x"]).FiberyError(
                "induced"
            )
        return real(secret, markdown)

    ws.write_document_content = fail_the_root_rewrite
    run(ws, std, FakeModelRuntime([analysis_output()]))
    ws.write_document_content = real
    set_state(ws, std, "Process")

    persisted = parse_process_result(ws.content[process_results(ws)[0].secret])
    assert document_fingerprint(ws.content["std-secret"]) == persisted.input_fingerprint

    model = FakeModelRuntime([EDITED])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert not model.was_invoked
    assert result.iteration == 1
    assert len(process_results(ws)) == 1


def test_branch_b_output_already_applied_does_nothing():
    """current == latest.output_fingerprint"""
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([analysis_output()]))
    set_state(ws, std, "Process")
    persisted = parse_process_result(ws.content[process_results(ws)[0].secret])
    assert (
        document_fingerprint(ws.content["std-secret"]) == persisted.output_fingerprint
    )

    model = FakeModelRuntime([EDITED])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked


def test_branch_c_edited_content_starts_a_new_iteration():
    """current differs from both fingerprints"""
    ws, std, _ = build_standard_workspace()
    run(ws, std, FakeModelRuntime([analysis_output()]))
    ws.content["std-secret"] += "\nA deliberate human edit.\n"
    set_state(ws, std, "Process")
    persisted = parse_process_result(ws.content[process_results(ws)[0].secret])
    current = document_fingerprint(ws.content["std-secret"])
    assert current not in {persisted.input_fingerprint, persisted.output_fingerprint}

    model = FakeModelRuntime([EDITED])
    result = run(ws, std, model)

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert result.iteration == 2
    assert len(model.calls) == 1
    assert ws.requirements[std.id].revision == 1
