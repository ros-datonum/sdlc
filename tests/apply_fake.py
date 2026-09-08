"""Fixtures for Standard Requirement Apply tests.

An Apply Requirement is produced by the frozen chain: the Reviewer writes the
Review Result and reaches Ready, then the Ready Decision approves it. Every
fixture is therefore exactly the state a real approval leaves behind.
"""

from __future__ import annotations

import json

from processor_fake import FakeModelRuntime
from ready_fake import mutations_since
from review_fake import build_review_workspace, review_output
from sdlc.fibery_workspace import RequirementRecord
from sdlc.ready_decision import approve_standard_requirement
from sdlc.standard_analysis import ProposedRelation, RelationKind
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import REQUIREMENT_ID

TARGET_ID = "SDLC-FR-0002"
TARGET_ENTITY = "std-uuid-2"
OTHER_ID = "SDLC-FR-0003"
OTHER_ENTITY = "std-uuid-3"
PROJECT_ID = "p-1"


def standard(
    requirement_id=TARGET_ID,
    entity_id=TARGET_ENTITY,
    state="Ready",
    type_name="Standard",
    project_id=PROJECT_ID,
    public_id=None,
):
    return RequirementRecord(
        id=entity_id,
        public_id=public_id or entity_id.rsplit("-", 1)[-1],
        requirement_id=requirement_id,
        title=f"Target {requirement_id}",
        type_name=type_name,
        state=state,
        revision=1,
        project_id=project_id,
        source_fingerprint=None,
    )


def proposal(kind=RelationKind.DEPENDS_ON, requirement_id=TARGET_ID):
    return ProposedRelation(kind=kind, requirement_id=requirement_id, rationale="r")


def confirmed(kind="DEPENDS_ON", requirement_id=TARGET_ID, outcome="CONFIRMED"):
    return {
        "kind": kind,
        "requirement_id": requirement_id,
        "outcome": outcome,
        "reason": "Verified.",
    }


def build_apply_workspace(
    proposals=(), verifications=None, others=None, legacy_folders=True
):
    """A Standard Requirement in Apply, approved through the frozen chain.

    `proposals` are what Process proposed; `verifications` are what Review
    concluded (every proposal CONFIRMED by default). `others` are the other
    Requirements in the Project, one Standard target by default.
    `legacy_folders` selects a Root carrying the retired Draft Folder (B) or
    none (A).
    """
    if others is None:
        others = (standard(),)
    if verifications is None:
        verifications = [
            confirmed(kind=p.kind.value, requirement_id=p.requirement_id)
            for p in proposals
        ]
    ws, requirement, root, _ = build_review_workspace(
        relations=tuple(proposals), others=tuple(others), legacy_folders=legacy_folders
    )
    reviewed = review_standard_requirement(
        ws,
        FakeModelRuntime(
            responses=[review_output(relation_verifications=verifications)]
        ),
        requirement.id,
    )
    assert reviewed.verdict == "PASS", reviewed
    approved = approve_standard_requirement(ws, requirement.id)
    assert approved.code.value == "REQUIREMENT_APPROVED", approved
    assert ws.requirements[requirement.id].state == "Apply"
    return ws, ws.requirements[requirement.id], root, len(ws.mutations)


def edges(ws, entity_id):
    relations = ws.requirement_relations(entity_id)
    return {(RelationKind.DEPENDS_ON, t) for t in relations.depends_on} | {
        (RelationKind.AFFECTS, t) for t in relations.affects
    }


def root_node(ws, root):
    return next(d for d in ws.documents if d.id == root.id)


def child_ids(ws, root):
    return {d.id for d in ws.documents if d.parent_document_id == root.id}


def review_result_nodes(ws):
    return [d for d in ws.documents if "Review Result" in d.name]


def process_result_nodes(ws):
    return [d for d in ws.documents if "Process Result" in d.name]


def payload_of(ws, node):
    text = ws.content[node.secret]
    start = text.index("```json\n") + len("```json\n")
    end = text.index("\n```", start)
    return json.loads(text[start:end]), text[:start], text[end:]


def rewrite_payload(ws, node, **changes):
    """Edit the JSON payload of a persisted artifact in place."""
    payload, head, tail = payload_of(ws, node)
    payload.update(changes)
    ws.content[node.secret] = head + json.dumps(payload, indent=2) + tail


def normative_writes(ws, before):
    """Every mutation a decision is allowed to make, in order."""
    return [
        m
        for m in mutations_since(ws, before)
        if m.startswith(
            (
                "add_depends_on",
                "add_affects",
                "set_requirement_state",
            )
        )
    ]


__all__ = [
    "OTHER_ENTITY",
    "OTHER_ID",
    "PROJECT_ID",
    "REQUIREMENT_ID",
    "TARGET_ENTITY",
    "TARGET_ID",
    "build_apply_workspace",
    "child_ids",
    "confirmed",
    "edges",
    "mutations_since",
    "normative_writes",
    "payload_of",
    "process_result_nodes",
    "proposal",
    "review_result_nodes",
    "rewrite_payload",
    "root_node",
    "standard",
]
