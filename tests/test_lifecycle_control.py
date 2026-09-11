"""RW-O01: the human State transition is the decision; the CLI is admin.

Under Requirement-Lifecycle-Ownership-v0.2 (RW-C02) the two human decisions at
Ready are Fibery State transitions. These tests make those transitions
directly on the Fibery fake, exactly as a person editing State in Fibery
would, never through the admin `approve` or `rework` capability, and then
drive the real deterministic capabilities that act on the resulting State.
They also pin that the remaining commands are labelled admin/compatibility and
keep their own checks. No dispatcher, trigger or Processing Status exists here.
"""

import inspect

import pytest

from processor_fake import FakeModelRuntime
from ready_fake import (
    build_ready_workspace,
    document_snapshot,
    mutations_since,
    only_state_transition,
    process_result_nodes,
    review_result_nodes,
)
from sdlc import cli
from sdlc.ready_decision import (
    approve_standard_requirement,
    rework_standard_requirement,
)
from sdlc.requirement_apply import apply_standard_requirement
from sdlc.results import (
    ApplyResultCode,
    ReadyDecisionResultCode,
    StandardProcessResultCode,
)
from sdlc.standard_processor import process_standard_requirement
from standard_fake import analysis_output

VERDICTS = ["PASS", "NEEDS_WORK", "BLOCKING"]


def human_moves(ws, requirement, state):
    """A person changing the State in Fibery: one State write and nothing else."""
    before = len(ws.mutations)
    ws.set_requirement_state(requirement.id, state)
    assert mutations_since(ws, before) == [
        f"set_requirement_state {requirement.id} {state}"
    ]


def edit_root(ws, root, text):
    ws.content[root.secret] += f"\n{text}\n"


def help_of(capsys, *command):
    """The normalized `--help` text of a command, as argparse prints it."""
    with pytest.raises(SystemExit) as exited:
        cli.main([*command, "--help"])
    assert exited.value.code == 0
    return " ".join(capsys.readouterr().out.split())


def normalized(text):
    return " ".join(text.split())


# -- AC1: a direct human Ready -> Apply is the approval ----------------------------


@pytest.mark.parametrize("verdict", VERDICTS)
def test_a_direct_ready_to_apply_is_applied_without_the_approve_command(verdict):
    """No approve call, no acknowledgement: State = Apply is the approval."""
    ws, requirement, _root, _ = build_ready_workspace(verdict=verdict)
    human_moves(ws, requirement, "Apply")

    result = apply_standard_requirement(ws, requirement.id)

    assert result.code is ApplyResultCode.REQUIREMENT_APPLIED, result
    assert ws.requirements[requirement.id].state == "Applied"


@pytest.mark.parametrize("verdict", VERDICTS)
def test_a_direct_ready_to_apply_is_still_refused_on_stale_reviewed_content(verdict):
    ws, requirement, root, _ = build_ready_workspace(verdict=verdict)
    human_moves(ws, requirement, "Apply")
    edit_root(ws, root, "Edited after the review.")
    before = len(ws.mutations)

    result = apply_standard_requirement(ws, requirement.id)

    assert result.code is ApplyResultCode.REVIEW_RESULT_STALE, result
    assert mutations_since(ws, before) == []
    assert ws.requirements[requirement.id].state == "Apply"


def test_apply_takes_no_verdict_acknowledgement():
    assert list(inspect.signature(apply_standard_requirement).parameters) == [
        "workspace",
        "entity_id",
    ]
    with pytest.raises(SystemExit):
        cli.build_parser().parse_args(
            [
                "project",
                "requirement",
                "apply",
                "--requirement",
                "entity-uuid",
                "--acknowledge-verdict",
                "BLOCKING",
            ]
        )


def test_the_admin_approve_leads_to_the_same_apply_as_a_direct_transition():
    """The command records no different kind of approval."""
    direct, direct_requirement, _root, _ = build_ready_workspace()
    human_moves(direct, direct_requirement, "Apply")
    admin, admin_requirement, _root, _ = build_ready_workspace()
    approved = approve_standard_requirement(admin, admin_requirement.id)
    assert approved.code is ReadyDecisionResultCode.REQUIREMENT_APPROVED

    assert (
        admin.requirements[admin_requirement.id]
        == direct.requirements[direct_requirement.id]
    )
    applied = [
        apply_standard_requirement(ws, requirement.id)
        for ws, requirement in (
            (direct, direct_requirement),
            (admin, admin_requirement),
        )
    ]
    assert [result.code for result in applied] == [
        ApplyResultCode.REQUIREMENT_APPLIED,
        ApplyResultCode.REQUIREMENT_APPLIED,
    ]


# -- AC2: a direct human Ready -> Process is the rework decision -------------------


def test_ready_is_a_human_boundary_standard_process_does_not_start_from():
    ws, requirement, _root, before = build_ready_workspace()
    model = FakeModelRuntime([analysis_output()])

    result = process_standard_requirement(ws, model, requirement.id)

    assert result.code is StandardProcessResultCode.REQUIREMENT_NOT_IN_PROCESS
    assert not model.was_invoked
    assert mutations_since(ws, before) == []


@pytest.mark.parametrize("edited", [True, False], ids=["edited", "unedited"])
def test_a_direct_ready_to_process_is_the_rework_authority_edited_or_not(edited):
    """RW-C02 section 9: an edit is not a precondition of rework.

    The human State write alone, with no rework command, artifact or marker,
    puts the Requirement into Standard Process's stage, and its history
    survives either way.
    """
    ws, requirement, root, _ = build_ready_workspace(verdict="NEEDS_WORK")
    history = [*process_result_nodes(ws), *review_result_nodes(ws)]
    evidence = {node.secret: ws.content[node.secret] for node in history}
    human_moves(ws, requirement, "Process")
    if edited:
        edit_root(ws, root, "The human narrowed the scope for this rework.")

    result = process_standard_requirement(
        ws, FakeModelRuntime([analysis_output()]), requirement.id
    )

    assert result.code is not StandardProcessResultCode.REQUIREMENT_NOT_IN_PROCESS
    assert result.is_normal, result
    assert {secret: ws.content[secret] for secret in evidence} == evidence


def test_an_edited_rework_already_completes_a_new_process_iteration():
    ws, requirement, root, _ = build_ready_workspace(verdict="NEEDS_WORK")
    reviews = review_result_nodes(ws)
    human_moves(ws, requirement, "Process")
    edit_root(ws, root, "The human narrowed the scope for this rework.")
    model = FakeModelRuntime([analysis_output()])

    result = process_standard_requirement(ws, model, requirement.id)

    assert result.code is StandardProcessResultCode.REQUIREMENT_PROCESSED, result
    assert result.iteration == 2 and model.was_invoked
    assert ws.requirements[requirement.id].state == "Review"
    assert len(process_result_nodes(ws)) == 2
    assert review_result_nodes(ws) == reviews


def test_an_unedited_rework_is_authorized_but_not_yet_processed_known_gap():
    """The known orchestration gap owned by RW-O02/RW-O03 (CR-002).

    A human Ready -> Process with no edit is valid rework authority and owes a
    new Standard Process cycle. Today's processor sees its latest output as the
    current tree, returns NO_CHANGES_TO_PROCESS and stays in Process with no
    model call and no new iteration. That is NOT a correct completion of the
    rework cycle: it pins current behavior until the state-driven worker path
    can start a new iteration over the unchanged tree, at which point this test
    is expected to change. RW-O01 changes no Standard Process semantics.
    """
    ws, requirement, _root, _ = build_ready_workspace()
    human_moves(ws, requirement, "Process")
    before = len(ws.mutations)
    model = FakeModelRuntime([analysis_output()])

    result = process_standard_requirement(ws, model, requirement.id)

    assert result.code is StandardProcessResultCode.NO_CHANGES_TO_PROCESS
    assert not model.was_invoked
    assert mutations_since(ws, before) == []
    assert ws.requirements[requirement.id].state == "Process", "the gap: no Review"
    assert len(process_result_nodes(ws)) == 1, "the gap: no new iteration yet"


# -- AC3: approve and rework are admin/compatibility only ------------------------


def test_the_requirement_commands_state_the_normal_lifecycle(capsys):
    text = help_of(capsys, "project", "requirement")

    assert normalized(cli.REQUIREMENT_LIFECYCLE_NOTE) in text
    for command in ("process", "normalize", "review", "apply"):
        assert f"{command} {cli.MANUAL_WORKER}" in text
    for command in ("approve", "rework"):
        assert f"{command} {cli.ADMIN_DECISION}" in text


@pytest.mark.parametrize(
    ("command", "description"),
    [
        ("approve", cli.APPROVE_DESCRIPTION),
        ("rework", cli.REWORK_DESCRIPTION),
    ],
)
def test_approve_and_rework_remain_available_as_admin_commands(
    capsys, command, description
):
    text = help_of(capsys, "project", "requirement", command)

    assert normalized(description) in text
    assert "Admin/compatibility command." in text
    assert "is not required" in text


def test_the_acknowledgement_is_a_safety_check_of_the_command_only(capsys):
    text = help_of(capsys, "project", "requirement", "approve")
    assert "not approval authority" in text
    assert "not needed for a direct Ready -> Apply" in text

    ws, requirement, _root, before = build_ready_workspace(verdict="BLOCKING")
    refused = approve_standard_requirement(ws, requirement.id)
    assert refused.code is ReadyDecisionResultCode.VERDICT_ACKNOWLEDGEMENT_REQUIRED
    assert mutations_since(ws, before) == []

    human_moves(ws, requirement, "Apply")
    applied = apply_standard_requirement(ws, requirement.id)
    assert applied.code is ApplyResultCode.REQUIREMENT_APPLIED


def test_the_admin_approve_cannot_bypass_the_evidence_checks():
    ws, requirement, root, _ = build_ready_workspace()
    edit_root(ws, root, "Edited after the review.")
    before = len(ws.mutations)

    result = approve_standard_requirement(ws, requirement.id)

    assert result.code is ReadyDecisionResultCode.REVIEW_RESULT_STALE
    assert mutations_since(ws, before) == []
    assert ws.requirements[requirement.id].state == "Ready"


def test_the_admin_rework_makes_only_the_state_transition():
    ws, requirement, _root, before = build_ready_workspace()
    documents = document_snapshot(ws)

    result = rework_standard_requirement(ws, requirement.id)

    assert result.code is ReadyDecisionResultCode.REQUIREMENT_SENT_FOR_REWORK
    assert only_state_transition(ws, before, requirement, "Process")
    assert document_snapshot(ws) == documents
