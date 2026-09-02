"""Fixtures for independent Standard Requirement Review tests."""

from __future__ import annotations

import json

from processor_fake import reserialize_like_fibery
from sdlc.fibery_workspace import DocumentNode
from sdlc.process_result import (
    build_process_result,
    document_fingerprint,
    process_result_name,
    render_process_result,
)
from sdlc.review_result import parse_review_result
from sdlc.standard_analysis import (
    AnalysisResult,
    Finding,
    FindingKind,
    NormalizedRequirement,
    ProposedRelation,
    RelationKind,
)
from standard_fake import REQUIREMENT_ID, build_standard_workspace, normalized

PROCESS_SECRET = "process-secret"


def build_review_workspace(
    state="Review",
    type_name="Standard",
    findings=(),
    relations=(),
    others=(),
    process_iterations=1,
):
    """A Standard Requirement in Review with its Process history in place.

    The Root Document holds exactly what the last Process iteration produced,
    which is the normal state a review starts from.
    """
    ws, requirement, root = build_standard_workspace(
        state=state, type_name=type_name, others=others
    )
    document = NormalizedRequirement(**normalized()).document(REQUIREMENT_ID)
    ws.content[root.secret] = document

    results = []
    for iteration in range(1, process_iterations + 1):
        result = build_process_result(
            requirement_id=REQUIREMENT_ID,
            iteration=iteration,
            input_fingerprint=f"input-{iteration}",
            analysis=AnalysisResult(
                normalized=NormalizedRequirement(**normalized()),
                analysis={"clarity": "adequate"},
                findings=tuple(findings),
                proposed_relations=tuple(relations),
            ),
        )
        secret = f"{PROCESS_SECRET}-{iteration}"
        ws.documents.append(
            DocumentNode(
                id=f"process-doc-{iteration}",
                name=process_result_name(REQUIREMENT_ID, iteration),
                folder_id=None,
                entity_public_id=None,
                secret=secret,
                parent_document_id=root.id,
            )
        )
        ws.content[secret] = render_process_result(result)
        results.append(result)
    return ws, requirement, root, results[-1] if results else None


def finding(kind=FindingKind.AMBIGUOUS, detail="Unclear scope.", requirement_id=None):
    return Finding(kind=kind, detail=detail, requirement_id=requirement_id)


def relation(
    kind=RelationKind.DEPENDS_ON, requirement_id="SDLC-FR-0002", rationale="r"
):
    return ProposedRelation(
        kind=kind, requirement_id=requirement_id, rationale=rationale
    )


def review_output(
    finding_verifications=(),
    relation_verifications=(),
    new_findings=(),
    assessment=None,
):
    """A reviewer response. There is deliberately no verdict field."""
    body = {}
    if finding_verifications:
        body["finding_verifications"] = list(finding_verifications)
    if relation_verifications:
        body["relation_verifications"] = list(relation_verifications)
    if new_findings:
        body["new_findings"] = list(new_findings)
    if assessment is not None:
        body["assessment"] = assessment
    return json.dumps(body)


def confirm(index=0, severity="WARNING", reason="Independently reproduced."):
    return {
        "process_finding_index": index,
        "outcome": "CONFIRMED",
        "severity": severity,
        "reason": reason,
    }


def reject(index=0, reason="The document does state this."):
    return {
        "process_finding_index": index,
        "outcome": "REJECTED",
        "reason": reason,
    }


def unresolved(index=0, reason="Not decidable from the given context."):
    return {
        "process_finding_index": index,
        "outcome": "UNRESOLVED",
        "reason": reason,
    }


def verify_relation(
    kind="DEPENDS_ON",
    requirement_id="SDLC-FR-0002",
    outcome="CONFIRMED",
    reason="The dependency is real.",
):
    return {
        "kind": kind,
        "requirement_id": requirement_id,
        "outcome": outcome,
        "reason": reason,
    }


def new_finding(
    kind="NOT_TESTABLE", severity="INFO", detail="No measurable threshold."
):
    return {"kind": kind, "severity": severity, "detail": detail}


def review_results(ws) -> list[DocumentNode]:
    return [d for d in ws.documents if "Review Result" in d.name]


def stored_review(ws, index=-1):
    """Parse a persisted Review Result exactly as the reviewer reads it back."""
    node = review_results(ws)[index]
    return parse_review_result(reserialize_like_fibery(ws.content[node.secret]))


def root_fingerprint(ws, root) -> str:
    return document_fingerprint(reserialize_like_fibery(ws.content[root.secret]))


def relation_state(ws):
    """A snapshot of every actual relation, for before/after comparison."""
    return (
        {key: list(value) for key, value in ws.depends_on_ids.items()},
        {key: list(value) for key, value in ws.affects_ids.items()},
    )
