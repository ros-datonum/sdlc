"""Fixtures for Standard Requirement Ready Decision tests.

A Ready Requirement is produced by running the frozen Reviewer over a Review
workspace, so every fixture here is exactly the state the real chain leaves
behind: one Process Result, one Review Result bound to it, State = Ready.
"""

from __future__ import annotations

from processor_fake import FakeModelRuntime
from review_fake import (
    build_review_workspace,
    confirm,
    finding,
    relation,
    review_output,
    verify_relation,
)
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import REQUIREMENT_ID

STATE_TRANSITION = "set_requirement_state"


def build_ready_workspace(
    verdict="PASS", with_relation=False, process_iterations=1, normalized_changes=None
):
    """A Standard Requirement in Ready, reviewed to the requested verdict.

    Returns the workspace, the Requirement record, its Root Document and the
    number of mutations the chain made, so a test can assert on what the
    decision adds beyond that point.
    """
    findings = () if verdict == "PASS" else (finding(),)
    relations = (relation(),) if with_relation else ()
    ws, requirement, root, _ = build_review_workspace(
        findings=findings,
        relations=relations,
        process_iterations=process_iterations,
        normalized_changes=normalized_changes,
    )
    response = review_output(
        finding_verifications=[confirm(severity=_severity(verdict))]
        if findings
        else [],
        relation_verifications=[verify_relation()] if with_relation else [],
    )
    reviewed = review_standard_requirement(
        ws, FakeModelRuntime(responses=[response]), requirement.id
    )
    assert reviewed.verdict == verdict, reviewed
    assert ws.requirements[requirement.id].state == "Ready"
    return ws, ws.requirements[requirement.id], root, len(ws.mutations)


def _severity(verdict):
    return "BLOCKING" if verdict == "BLOCKING" else "WARNING"


def mutations_since(ws, before):
    return ws.mutations[before:]


def only_state_transition(ws, before, requirement, state):
    """The one mutation a decision is allowed to make, and nothing else."""
    return mutations_since(ws, before) == [
        f"{STATE_TRANSITION} {requirement.id} {state}"
    ]


def document_snapshot(ws):
    """Every stored document body, for byte-for-byte comparison."""
    return dict(ws.content)


def review_result_nodes(ws):
    return [d for d in ws.documents if "Review Result" in d.name]


def process_result_nodes(ws):
    return [d for d in ws.documents if "Process Result" in d.name]


__all__ = [
    "REQUIREMENT_ID",
    "build_ready_workspace",
    "document_snapshot",
    "mutations_since",
    "only_state_transition",
    "process_result_nodes",
    "review_result_nodes",
]
