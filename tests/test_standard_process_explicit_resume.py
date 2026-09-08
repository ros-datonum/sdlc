"""Audit A11: a tree equal to the latest input is ambiguous, not a resume.

An ordinary Standard Process run refuses that snapshot; the operator settles
it with `--resume-result` (apply the persisted output, no model) or
`--new-iteration-after` (process the current tree afresh). Both name exactly
the latest valid Process Result and pass every existing entry, history and
fresh-input guard.
"""

from __future__ import annotations

import io
from argparse import Namespace
from dataclasses import replace

import pytest

from processor_fake import FakeModelRuntime, reserialize_like_fibery
from review_fake import review_output
from sdlc import cli
from sdlc.fibery_workspace import FiberyError
from sdlc.model_runtime import ModelRuntimeError
from sdlc.model_runtime_config import ModelRuntimeConfigError
from sdlc.normative_tree import read_normative_tree
from sdlc.process_result import parse_process_result, render_process_result
from sdlc.ready_decision import rework_standard_requirement
from sdlc.results import StandardProcessResult
from sdlc.results import StandardProcessResultCode as Code
from sdlc.standard_processor import (
    NEW_ITERATION_OPTION,
    RESUME_OPTION,
    process_standard_requirement,
)
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import (
    analysis_output,
    build_standard_workspace,
    process_results,
    set_state,
)
from test_empty_result_recovery import PROCESS, leave_a_shell
from tree_fake import add_child, edit

CHILD_TEXT = "OBLIGATION-CHILD retries are capped at three"


def manifest(ws, requirement, root):
    return read_normative_tree(ws, ws.requirements[requirement.id], root).manifest


def stored(ws, index=-1):
    node = process_results(ws)[index]
    return parse_process_result(reserialize_like_fibery(ws.content[node.secret]))


def completed_then_reverted(with_child=False):
    """X -> Y processed and completed; then X is restored on purpose."""
    ws, requirement, root = build_standard_workspace()
    child = (
        add_child(ws, root, "Retry budget", CHILD_TEXT + "\n") if with_child else None
    )
    x_root = ws.content[root.secret]
    x = manifest(ws, requirement, root)
    first = process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), requirement.id
    )
    assert first.code is Code.REQUIREMENT_PROCESSED
    y = manifest(ws, requirement, root)
    assert x.fingerprint != y.fingerprint
    ws.content[root.secret] = x_root
    set_state(ws, requirement, "Process")
    assert manifest(ws, requirement, root) == x
    [node] = process_results(ws)
    return ws, requirement, root, node, child, x, y


def run(ws, requirement, responses=None, **options):
    model = FakeModelRuntime(responses or [analysis_output()])
    return process_standard_requirement(ws, model, requirement.id, **options), model


# -- ordinary entry ------------------------------------------------------------


def test_an_intentional_revert_is_refused_and_preserved():
    ws, requirement, root, node, _, x, y = completed_then_reverted()
    before = len(ws.mutations)
    result, model = run(ws, requirement)
    assert result.code is Code.PROCESSING_STATE_CONFLICT, result
    assert node.id in result.message and node.name in result.message
    assert RESUME_OPTION in result.message and NEW_ITERATION_OPTION in result.message
    assert "intentional return" in result.message
    assert not model.was_invoked and result.model_invoked is False
    assert ws.mutations[before:] == []
    assert manifest(ws, requirement, root) == x
    assert ws.requirements[requirement.id].state == "Process"
    assert stored(ws).output_tree.fingerprint == y.fingerprint  # history untouched


def test_a_genuine_unfinished_rewrite_also_needs_an_explicit_choice():
    ws, requirement, _root = build_standard_workspace()
    original = ws.write_document_content
    seen = {"n": 0}

    def fail_root_write(secret, markdown):
        seen["n"] += 1
        if seen["n"] == 2:
            raise FiberyError("induced")
        return original(secret, markdown)

    ws.write_document_content = fail_root_write
    first, _ = run(ws, requirement)
    assert first.code is Code.PARTIAL_PROCESSING
    ws.write_document_content = original
    set_state(ws, requirement, "Process")
    before = len(ws.mutations)
    result, model = run(ws, requirement)
    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert not model.was_invoked and ws.mutations[before:] == []


def test_input_equal_to_output_is_a_zero_mutation_no_change():
    """When the model changes nothing, output == input and no-change wins."""
    ws, requirement, root = build_standard_workspace()
    from standard_fake import rendered_document

    ws.content[root.secret] = rendered_document()
    first, _ = run(ws, requirement)
    assert first.code is Code.REQUIREMENT_PROCESSED
    result = stored(ws)
    assert result.input_tree == result.output_tree
    set_state(ws, requirement, "Process")
    before = len(ws.mutations)
    again, model = run(ws, requirement)
    assert again.code is Code.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked and ws.mutations[before:] == []
    refused, model = run(ws, requirement, resume_result=process_results(ws)[0].id)
    assert refused.code is Code.PROCESSING_STATE_CONFLICT
    assert "already applied" in refused.message and ws.mutations[before:] == []


def test_the_revert_stays_protected_after_a_review_rework_cycle():
    ws, requirement, root, node, _, x, _y = completed_then_reverted()
    # Re-apply Y through an explicit resume, review it, rework it, revert again.
    resumed, _ = run(ws, requirement, resume_result=node.id)
    assert resumed.code is Code.REQUIREMENT_PROCESSED
    reviewed = review_standard_requirement(
        ws, FakeModelRuntime([review_output()]), requirement.id
    )
    assert reviewed.code.value == "REQUIREMENT_REVIEWED"
    assert rework_standard_requirement(ws, requirement.id).code.value == (
        "REQUIREMENT_SENT_FOR_REWORK"
    )
    root_x = "# SDLC-FR-0031 — Reject unauthenticated model execution\n\n## Requirement\n\nA draft statement.\n"
    ws.content[root.secret] = root_x
    assert manifest(ws, requirement, root) == x
    before = len(ws.mutations)
    result, model = run(ws, requirement)
    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert not model.was_invoked and ws.mutations[before:] == []
    # Recovery-style replay is refused: the iteration was reviewed already.
    replay, model = run(ws, requirement, resume_result=node.id)
    assert replay.code is Code.PROCESSING_STATE_CONFLICT
    assert "already reviewed iteration 1" in replay.message
    assert NEW_ITERATION_OPTION in replay.message
    assert not model.was_invoked and ws.mutations[before:] == []
    # A new iteration is the way forward.
    fresh, model = run(
        ws,
        requirement,
        [analysis_output({"title": "Reworked"})],
        new_iteration_after=node.id,
    )
    assert fresh.code is Code.REQUIREMENT_PROCESSED and fresh.iteration == 2
    assert model.was_invoked and len(process_results(ws)) == 2


# -- explicit resume ----------------------------------------------------------


def test_an_explicit_resume_applies_the_persisted_output_without_the_model():
    ws, requirement, root, node, _, _x, y = completed_then_reverted()
    body = ws.content[node.secret]
    before = len(ws.mutations)
    result, model = run(ws, requirement, resume_result=node.id)
    assert result.code is Code.REQUIREMENT_PROCESSED, result
    assert result.iteration == 1 and not model.was_invoked
    assert result.model_invoked is False
    assert len(process_results(ws)) == 1 and ws.content[node.secret] == body
    assert manifest(ws, requirement, root) == y
    assert ws.requirements[requirement.id].state == "Review"
    assert ws.mutations[before:] == [
        f"write_content {root.secret}",
        f"set_requirement_state {requirement.id} Review",
    ]


def test_an_explicit_resume_never_calls_a_runtime_even_one_that_would_fail():
    class Unavailable:
        def run(self, prompt, context=""):
            raise ModelRuntimeError("no runtime")

    ws, requirement, root, node, _, _, y = completed_then_reverted()
    result = process_standard_requirement(
        ws, Unavailable(), requirement.id, resume_result=node.id
    )
    assert result.code is Code.REQUIREMENT_PROCESSED
    assert manifest(ws, requirement, root) == y


@pytest.mark.parametrize("option", ["resume_result", "new_iteration_after"])
def test_a_wrong_or_foreign_selection_is_refused_before_anything(option):
    ws, requirement, root, _node, _, x, _ = completed_then_reverted()
    foreign = add_child(
        ws, root, "SDLC-FR-0099 — Process Result 0001", "x", document_id="foreign"
    )
    # A foreign artifact name invalidates the tree itself.
    result, model = run(ws, requirement, **{option: foreign.id})
    assert result.code is Code.NORMATIVE_TREE_INVALID
    ws.documents.remove(foreign)
    for wrong in ("no-such-document", root.id):
        before = len(ws.mutations)
        result, model = run(ws, requirement, **{option: wrong})
        assert result.code is Code.PROCESSING_STATE_CONFLICT, result
        assert "not a Process Result Document" in result.message
        assert not model.was_invoked and ws.mutations[before:] == []
    assert manifest(ws, requirement, root) == x


@pytest.mark.parametrize("option", ["resume_result", "new_iteration_after"])
def test_an_older_result_is_not_a_valid_selection(option):
    ws, requirement, root, first_node, _, _, _ = completed_then_reverted()
    resumed, _ = run(ws, requirement, resume_result=first_node.id)
    assert resumed.code is Code.REQUIREMENT_PROCESSED
    set_state(ws, requirement, "Process")
    edit_root = ws.content[root.secret] + "\n## Extra\n\nMore.\n"
    ws.content[root.secret] = edit_root
    second, _ = run(ws, requirement, [analysis_output({"title": "Second"})])
    assert second.code is Code.REQUIREMENT_PROCESSED and second.iteration == 2
    set_state(ws, requirement, "Process")
    ws.content[root.secret] = edit_root  # revert to iteration 2's input
    before = len(ws.mutations)
    result, model = run(ws, requirement, **{option: first_node.id})
    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert "not the latest" in result.message
    assert process_results(ws)[-1].id in result.message
    assert not model.was_invoked and ws.mutations[before:] == []


@pytest.mark.parametrize("option", ["resume_result", "new_iteration_after"])
def test_legacy_evidence_cannot_be_selected(option):
    ws, requirement, _root, node, _, _, _ = completed_then_reverted()
    legacy = replace(stored(ws), version="0.1", input_tree=None, output_tree=None)
    ws.content[node.secret] = render_process_result(legacy)
    before = len(ws.mutations)
    result, model = run(ws, requirement, **{option: node.id})
    assert result.code is Code.NORMATIVE_TREE_EVIDENCE_REQUIRED
    assert not model.was_invoked and ws.mutations[before:] == []
    # The ordinary run still upgrades legacy history with a fresh iteration.
    fresh, model = run(ws, requirement)
    assert fresh.code is Code.REQUIREMENT_PROCESSED and fresh.iteration == 2
    assert model.was_invoked


@pytest.mark.parametrize("option", ["resume_result", "new_iteration_after"])
def test_an_empty_or_malformed_latest_artifact_is_refused(option):
    ws, requirement, _root, node, _, _, _ = completed_then_reverted()
    for body in ("", "# not a result\n"):
        ws.content[node.secret] = body
        before = len(ws.mutations)
        result, model = run(ws, requirement, **{option: node.id})
        assert result.code is Code.INVALID_PROCESSING_RESULT, result
        assert not model.was_invoked and ws.mutations[before:] == []


@pytest.mark.parametrize("option", ["resume_result", "new_iteration_after"])
def test_unrelated_current_content_is_refused(option):
    ws, requirement, root, node, _, _, _ = completed_then_reverted()
    ws.content[root.secret] += "\n## Extra\n\nUnrelated.\n"
    before = len(ws.mutations)
    result, model = run(ws, requirement, **{option: node.id})
    assert result.code is Code.PROCESSING_STATE_CONFLICT
    assert "neither the input nor the output" in result.message
    assert any("content changed" in line for line in result.details)
    assert not model.was_invoked and ws.mutations[before:] == []


@pytest.mark.parametrize("option", ["resume_result", "new_iteration_after"])
def test_wrong_state_or_type_is_refused_first(option):
    ws, requirement, _root, node, _, _, _ = completed_then_reverted()
    set_state(ws, requirement, "Review")
    result, model = run(ws, requirement, **{option: node.id})
    assert result.code is Code.REQUIREMENT_NOT_IN_PROCESS and not model.was_invoked


def test_contradictory_options_are_refused_before_any_read():
    ws, requirement, _root, node, _, _, _ = completed_then_reverted()
    ws.calls.clear()
    for options in (
        {"resume_result": node.id, "new_iteration_after": node.id},
        {"resume_result": node.id, "recover_empty_result": node.id},
        {"new_iteration_after": node.id, "recover_empty_result": node.id},
    ):
        result, model = run(ws, requirement, **options)
        assert result.code is Code.PROCESSING_STATE_CONFLICT
        assert "mutually exclusive" in result.message
        assert not model.was_invoked
    assert ws.calls == []


def test_a_change_between_the_explicit_resume_read_and_the_write_is_refused():
    ws, requirement, _root, node, child, _x, _y = completed_then_reverted(
        with_child=True
    )
    original = ws.read_document_content
    seen = {"n": 0}

    def edit_after_context(secret):
        content = original(secret)
        seen["n"] += 1
        if seen["n"] == 3:  # Root, child and Process Result read; then the edit
            edit(ws, child, "changed by someone else\n")
        return content

    ws.read_document_content = edit_after_context
    before = len(ws.mutations)
    result, model = run(ws, requirement, resume_result=node.id)
    assert result.code is Code.PROCESSING_STATE_CONFLICT, result
    assert any("content changed" in line for line in result.details)
    assert not model.was_invoked and ws.mutations[before:] == []
    assert ws.content[child.secret] == "changed by someone else\n"


# -- explicit new iteration ---------------------------------------------------


def test_an_explicit_new_iteration_processes_the_current_tree_once():
    ws, requirement, root, node, _child, x, _y = completed_then_reverted(
        with_child=True
    )
    old_body = ws.content[node.secret]
    before = len(ws.mutations)
    result, model = run(
        ws,
        requirement,
        [analysis_output({"title": "Fresh"})],
        new_iteration_after=node.id,
    )
    assert result.code is Code.REQUIREMENT_PROCESSED, result
    assert result.iteration == 2 and model.was_invoked and len(model.calls) == 1
    assert CHILD_TEXT in model.calls[0]["context"]
    assert (
        "# SDLC-FR-0031 — Reject unauthenticated model execution"
        in model.calls[0]["context"]
    )
    assert len(process_results(ws)) == 2
    assert ws.content[node.secret] == old_body
    new = stored(ws)
    assert new.input_tree == x and new.version == "0.2"
    assert "Fresh" in ws.content[root.secret]
    assert ws.requirements[requirement.id].state == "Review"
    assert [m for m in ws.mutations[before:] if m.startswith("write_content")] == [
        f"write_content {process_results(ws)[-1].secret}",
        f"write_content {root.secret}",
    ]


def test_a_repeated_stale_anchor_creates_nothing():
    ws, requirement, _root, node, _, _x, _ = completed_then_reverted()
    first, _ = run(
        ws,
        requirement,
        [analysis_output({"title": "Fresh"})],
        new_iteration_after=node.id,
    )
    assert first.code is Code.REQUIREMENT_PROCESSED and first.iteration == 2
    set_state(ws, requirement, "Process")
    before = len(ws.mutations)
    for option in ("new_iteration_after", "resume_result"):
        again, model = run(ws, requirement, **{option: node.id})
        assert again.code is Code.PROCESSING_STATE_CONFLICT, again
        assert (
            "not the latest" in again.message
            and process_results(ws)[-1].id in again.message
        )
        assert not model.was_invoked
    assert ws.mutations[before:] == [] and len(process_results(ws)) == 2


def test_an_oversized_input_refuses_the_explicit_new_iteration_normally():
    from sdlc.comparison_context import MAX_ASSEMBLED_INPUT_CHARS

    ws, requirement, root, node, _, _, _ = completed_then_reverted()
    x_root = ws.content[root.secret]
    # Grow the input through a peer so the target tree still equals X.
    from processor_fake import attach_peer_roots
    from sdlc.fibery_workspace import RequirementRecord

    peer = RequirementRecord(
        id="std-peer-41",
        public_id="41",
        requirement_id="SDLC-FR-0041",
        title="Peer",
        type_name="Standard",
        state="Applied",
        revision=1,
        project_id="p-1",
        source_fingerprint=None,
    )
    ws.requirements[peer.id] = peer
    attach_peer_roots(ws, [peer])
    ws.content["peer-secret-41"] = (
        "# SDLC-FR-0041 — Peer\n\n## Requirement\n\n"
        + "p" * (MAX_ASSEMBLED_INPUT_CHARS - 2_000)
        + "\n"
    )
    before = len(ws.mutations)
    result, model = run(ws, requirement, new_iteration_after=node.id)
    assert result.code is Code.COMPARISON_CONTEXT_INCOMPLETE, result
    assert not model.was_invoked and ws.mutations[before:] == []
    assert ws.content[root.secret] == x_root


def test_a_failure_after_the_new_result_keeps_history_and_needs_a_choice():
    ws, requirement, _root, node, _, _x, _ = completed_then_reverted()
    original = ws.write_document_content
    seen = {"n": 0}

    def fail_root_write(secret, markdown):
        seen["n"] += 1
        if seen["n"] == 2:
            raise FiberyError("induced")
        return original(secret, markdown)

    ws.write_document_content = fail_root_write
    result, _ = run(
        ws,
        requirement,
        [analysis_output({"title": "Fresh"})],
        new_iteration_after=node.id,
    )
    assert result.code is Code.PARTIAL_PROCESSING
    ws.write_document_content = original
    assert len(process_results(ws)) == 2 and stored(ws).iteration == 2
    newest = process_results(ws)[-1]
    # Ordinary retry: the tree is iteration 2's input -> explicit choice again.
    retry, model = run(ws, requirement)
    assert retry.code is Code.PROCESSING_STATE_CONFLICT and newest.id in retry.message
    assert not model.was_invoked
    done, model = run(ws, requirement, resume_result=newest.id)
    assert done.code is Code.REQUIREMENT_PROCESSED and done.iteration == 2
    assert not model.was_invoked


def test_a_newer_empty_shell_is_neither_skipped_nor_doubled():
    ws, record, _root, shell, _ = leave_a_shell(PROCESS)
    ws.failures.clear()
    before = len(ws.mutations)
    for option in ("new_iteration_after", "resume_result"):
        result, model = run(ws, record, **{option: shell.id})
        assert result.code is Code.INVALID_PROCESSING_RESULT, result
        assert "--recover-empty-result" in result.message
        assert not model.was_invoked
    assert ws.mutations[before:] == [] and ws.content[shell.secret] == ""


# -- unchanged paths ------------------------------------------------------------


def test_first_processing_and_genuine_changes_still_run_normally():
    ws, requirement, root = build_standard_workspace()
    first, model = run(ws, requirement)
    assert first.code is Code.REQUIREMENT_PROCESSED and model.was_invoked
    set_state(ws, requirement, "Process")
    ws.content[root.secret] += "\n## Extra\n\nGenuinely new.\n"
    second, model = run(ws, requirement, [analysis_output({"title": "Second"})])
    assert second.code is Code.REQUIREMENT_PROCESSED and second.iteration == 2
    assert model.was_invoked
    set_state(ws, requirement, "Process")
    third, model = run(ws, requirement)
    assert third.code is Code.NO_CHANGES_TO_PROCESS and not model.was_invoked


# -- CLI -------------------------------------------------------------------------


def parse(*extra):
    return cli.build_parser().parse_args(
        ["project", "requirement", "normalize", "--requirement", "x", *extra]
    )


def test_normalize_accepts_each_option_alone():
    assert parse("--resume-result", "doc-1").resume_result == "doc-1"
    assert parse("--new-iteration-after", "doc-1").new_iteration_after == "doc-1"
    plain = parse()
    assert (plain.resume_result, plain.new_iteration_after) == (None, None)


@pytest.mark.parametrize(
    "extra",
    [
        ("--resume-result", "a", "--new-iteration-after", "b"),
        ("--resume-result", "a", "--recover-empty-result", "b"),
        ("--new-iteration-after", "a", "--recover-empty-result", "b"),
    ],
)
def test_the_options_are_mutually_exclusive(extra):
    with pytest.raises(SystemExit):
        parse(*extra)


@pytest.mark.parametrize("command", ["process", "review", "approve", "rework", "apply"])
@pytest.mark.parametrize("option", ["--resume-result", "--new-iteration-after"])
def test_only_standard_normalization_takes_the_options(command, option):
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            ["project", "requirement", command, "--requirement", "x", option, "d"]
        )


def test_no_generic_force_or_bypass_option_exists():
    for flag in ("--force", "--bypass", "--skip-checks", "--allow-stale"):
        with pytest.raises(SystemExit):
            parse(flag)


def test_a_cli_resume_selects_no_runtime(monkeypatch):
    calls = {}
    monkeypatch.setattr(
        cli, "load_fibery_settings", lambda: Namespace(space="s", space_id="i")
    )
    monkeypatch.setattr(cli, "FiberyClient", lambda settings: object())
    monkeypatch.setattr(cli, "FiberyRawProcessorWorkspace", lambda **kw: object())

    def no_config():
        raise ModelRuntimeConfigError("no runtime configured")

    monkeypatch.setattr(cli, "load_model_runtime_config", no_config)

    def fake_process(workspace, model, entity_id, **options):
        calls["model"] = model
        calls["options"] = options
        return StandardProcessResult(code=Code.NO_CHANGES_TO_PROCESS, message="m")

    monkeypatch.setattr(cli, "process_standard_requirement", fake_process)
    out, err = io.StringIO(), io.StringIO()
    exit_code = cli._run_standard_process(parse("--resume-result", "doc-1"), out, err)
    assert exit_code == 0 and calls["options"]["resume_result"] == "doc-1"
    with pytest.raises(ModelRuntimeError):
        calls["model"].run("prompt")
    # Without the resume option the same missing configuration stops the run.
    assert (
        cli._run_standard_process(parse("--new-iteration-after", "doc-1"), out, err)
        == 1
    )
