"""Fixtures for independent Standard Requirement Review tests."""

from __future__ import annotations

import json

from processor_fake import reserialize_like_fibery
from sdlc.fibery_workspace import DocumentNode, RequirementRecord
from sdlc.normative_tree import TreeManifest, read_normative_tree
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


def tree_manifest(ws, root, requirement_id=REQUIREMENT_ID):
    """The current normative-tree manifest of the fixture Requirement."""
    requirement = next(
        r for r in ws.requirements.values() if r.requirement_id == requirement_id
    )
    return read_normative_tree(ws, requirement, root).manifest


def tree_bound_process_result(
    ws, root, iteration, analysis, input_fingerprint=None, requirement_id=None
):
    """A Process Result 0.2 over the fixture's current tree.

    Its input tree is the current tree with the Root at the placeholder input
    fingerprint; its intended output tree is therefore the current tree only
    when the Root already holds what `analysis` normalizes to.
    """
    requirement_id = requirement_id or REQUIREMENT_ID
    manifest = tree_manifest(ws, root, requirement_id)
    input_fingerprint = input_fingerprint or f"input-{iteration}"
    return build_process_result(
        requirement_id=requirement_id,
        iteration=iteration,
        input_fingerprint=input_fingerprint,
        analysis=analysis,
        input_tree=manifest.with_root_fingerprint(input_fingerprint),
    )


def build_review_workspace(
    state="Review",
    type_name="Standard",
    findings=(),
    relations=(),
    others=(),
    process_iterations=1,
    normalized_changes=None,
    legacy_folders=True,
):
    """A Standard Requirement in Review with its Process history in place.

    The Root Document holds exactly what the last Process iteration produced,
    which is the normal state a review starts from. `normalized_changes`
    alters that content in both places at once.
    """
    others = list(others)
    known = {r.requirement_id for r in others} | {REQUIREMENT_ID}
    for number, target in enumerate(
        sorted({r.requirement_id for r in relations} - known), start=1
    ):
        # A proposal must point at a same-Project Standard with a Root, or
        # Review refuses to run without evidence; give it a plain one.
        others.append(
            RequirementRecord(
                id=f"std-target-{number}",
                public_id=str(300 + number),
                requirement_id=target,
                title=f"Target {target}",
                type_name="Standard",
                state="Applied",
                revision=1,
                project_id="p-1",
                source_fingerprint=None,
            )
        )
    ws, requirement, root = build_standard_workspace(
        state=state, type_name=type_name, others=others, legacy_folders=legacy_folders
    )
    content = normalized(**(normalized_changes or {}))
    document = NormalizedRequirement(**content).document(REQUIREMENT_ID)
    ws.content[root.secret] = document

    results = []
    for iteration in range(1, process_iterations + 1):
        result = tree_bound_process_result(
            ws,
            root,
            iteration=iteration,
            analysis=AnalysisResult(
                normalized=NormalizedRequirement(**content),
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


def add_process_iteration(
    ws, root, iteration, title="Rewritten", relations=(), **changes
):
    """Append a later Process Result and apply its output to the Root, as a
    second Process run would; the Root and the tree evidence stay coherent."""
    analysis = AnalysisResult(
        normalized=NormalizedRequirement(**normalized(title=title, **changes)),
        analysis={},
        findings=(),
        proposed_relations=tuple(relations),
    )
    result = tree_bound_process_result(ws, root, iteration=iteration, analysis=analysis)
    secret = f"process-secret-{iteration}"
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
    ws.content[root.secret] = result.normalized.document(REQUIREMENT_ID)
    return result


def payload_of(ws, node):
    """The JSON payload of a persisted artifact and where it sits in the text."""
    text = ws.content[node.secret]
    start = text.index("```json\n") + len("```json\n")
    end = text.index("\n```", start)
    return json.loads(text[start:end]), start, end


def rewrite_payload(ws, node, **changes):
    """Edit the JSON payload of a persisted artifact in place."""
    payload, start, end = payload_of(ws, node)
    payload.update(changes)
    text = ws.content[node.secret]
    ws.content[node.secret] = text[:start] + json.dumps(payload, indent=2) + text[end:]


def move_process_output(ws, node, fingerprint="moved"):
    """Rewrite a Process Result so it claims another output, consistently:
    the output fingerprint and the output tree's Root entry move together."""
    payload, _, _ = payload_of(ws, node)
    tree = TreeManifest.from_payload(payload["normative_output_tree"])
    rewrite_payload(
        ws,
        node,
        output_fingerprint=fingerprint,
        normative_output_tree=tree.with_root_fingerprint(fingerprint).to_payload(),
    )


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
