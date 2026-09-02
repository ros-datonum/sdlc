"""Fixtures for Standard Requirement Process tests."""

from __future__ import annotations

import json

from processor_fake import FakeProcessorWorkspace, reserialize_like_fibery
from sdlc.fibery_workspace import (
    DocumentNode,
    FolderNode,
    ProjectRecord,
    RequirementRecord,
)
from sdlc.process_result import document_fingerprint
from sdlc.standard_analysis import NormalizedRequirement

REQUIREMENT_ID = "SDLC-FR-0031"
RAW_ID = "SDLC-RAW-0007"


def normalized(**changes) -> dict:
    base = {
        "title": "Reject unauthenticated model execution",
        "requirement": "The runtime must refuse to execute a model without login.",
        "detailed_behavior": "Preflight runs the auth check before any call.",
        "rationale": "Credentials stay with the local CLI.",
        "acceptance_verification": "An unauthenticated CLI errors explicitly.",
        "constraints_edge_cases": "Applies to every configured runtime.",
        "non_goals": "Does not cover credential rotation.",
        "open_questions": "None.",
    }
    return {**base, **changes}


def analysis_output(normalized_changes=None, findings=(), relations=(), analysis=None):
    body = {"normalized_requirement": normalized(**(normalized_changes or {}))}
    if analysis is not None:
        body["analysis"] = analysis
    if findings:
        body["findings"] = list(findings)
    if relations:
        body["proposed_relations"] = list(relations)
    return json.dumps(body)


def rendered_document(requirement_id=REQUIREMENT_ID, **changes) -> str:
    return NormalizedRequirement(**normalized(**changes)).document(requirement_id)


def build_standard_workspace(
    state="Process", type_name="Standard", others=(), with_raw=True
):
    """A Project with one Standard Requirement in Process and its Root Document."""
    root = FolderNode(id="f-root", name="SDLC", parent_id=None)
    reqs = FolderNode(id="f-reqs", name="Requirements", parent_id=root.id)
    stages = [
        FolderNode(id=f"f-{s.lower()}", name=s, parent_id=reqs.id)
        for s in ("Raw", "Draft", "Approved")
    ]
    project = ProjectRecord(
        id="p-1",
        name="SDLC",
        code="SDLC",
        state="Planned",
        documents_root_folder_id=root.id,
    )
    standard = RequirementRecord(
        id="std-uuid-1",
        public_id="31",
        requirement_id=REQUIREMENT_ID,
        title="Reject unauthenticated model execution",
        type_name=type_name,
        state=state,
        revision=1,
        project_id=project.id,
        source_fingerprint=None,
    )
    records = [standard, *others]
    raw = None
    if with_raw:
        raw = RequirementRecord(
            id="raw-uuid-1",
            public_id="7",
            requirement_id=RAW_ID,
            title="Initial SDLC Requirements",
            type_name="Raw",
            state="Review",
            revision=1,
            project_id=project.id,
            source_fingerprint="fp",
        )
        records.append(raw)

    ws = FakeProcessorWorkspace(project, [root, reqs, *stages], records)
    doc = DocumentNode(
        id="std-doc-1",
        name=f"{REQUIREMENT_ID} — {standard.title}",
        folder_id="f-draft",
        entity_public_id=standard.public_id,
        secret="std-secret",
    )
    ws.documents.append(doc)
    ws.content["std-secret"] = (
        f"# {REQUIREMENT_ID} — {standard.title}\n\n## Requirement\n\nA draft statement.\n"
    )
    if raw is not None:
        raw_doc = DocumentNode(
            id="raw-doc-1",
            name=f"{RAW_ID} — Initial SDLC Requirements",
            folder_id="f-raw",
            entity_public_id=raw.public_id,
            secret="raw-secret",
        )
        ws.documents.append(raw_doc)
        ws.content["raw-secret"] = "# Initial SDLC Requirements\n\nSource material.\n"
        ws.derived_from_ids[standard.id] = [raw.id]
    return ws, standard, doc


def set_state(ws, record, state):
    ws.requirements[record.id] = RequirementRecord(
        **{**ws.requirements[record.id].__dict__, "state": state}
    )


def stored_fingerprint(ws, secret="std-secret") -> str:
    """The fingerprint of what Fibery would return for the Root Document."""
    return document_fingerprint(reserialize_like_fibery(ws.content[secret]))


def process_results(ws) -> list[DocumentNode]:
    return [d for d in ws.documents if "Process Result" in d.name]
