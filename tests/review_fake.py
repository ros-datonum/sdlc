"""Fixtures for independent Standard Requirement Review tests."""

from __future__ import annotations

import json
from dataclasses import replace

from processor_fake import reserialize_like_fibery
from sdlc.dependency_evidence import bind, resolve_interpretation_set
from sdlc.fibery_workspace import DocumentNode, RequirementRecord
from sdlc.normative_tree import TreeManifest, read_normative_tree
from sdlc.process_result import (
    build_process_result,
    document_fingerprint,
    process_result_name,
    render_process_result,
)
from sdlc.review_result import (
    DependencyOrigin,
    build_review_result,
    parse_review_result,
    render_review_result,
    review_result_name,
)
from sdlc.standard_analysis import (
    AnalysisResult,
    Finding,
    FindingKind,
    NormalizedRequirement,
    ProposedRelation,
    RelationKind,
    render_open_questions,
)
from sdlc.standard_review import (
    DependencyVerification,
    ReviewOutput,
    VerificationOutcome,
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
    questions=(),
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
    for target in sorted(
        {r.requirement_id for r in relations if r.kind is RelationKind.DEPENDS_ON}
    ):
        record = next(
            (r for r in ws.requirements.values() if r.requirement_id == target), None
        )
        if record is not None and record.id != requirement.id:
            give_reviewed_evidence(ws, record)
    content = normalized(**(normalized_changes or {}))
    if questions:
        content["open_questions"] = render_open_questions(tuple(questions))
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
                product_questions=tuple(questions),
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


def give_reviewed_evidence(
    ws,
    record,
    iteration=1,
    title=None,
    keep_content=False,
    content=None,
    depends_on=(),
):
    """A peer as admissible dependency authority (Dependency Bindings v0.1).

    Its Root holds what a Process Result produced, and a dependency-bound
    Review Result of that output derives CLEAR. `depends_on` are records the
    peer already DEPENDS_ON, each verified and bound by the production
    resolver (they need evidence first). The peer's State is left as the
    fixture set it.
    """
    root = next(
        (d for d in ws.documents if d.entity_public_id == record.public_id), None
    )
    if root is None:
        return None  # a peer with no Root is not authority; Review refuses it
    # Replace, never add to, any evidence the peer already had.
    ws.documents = [
        d
        for d in ws.documents
        if not (d.parent_document_id == root.id and " Result " in d.name)
    ]
    content = content or NormalizedRequirement(
        **normalized(title=title or record.title)
    )
    if not keep_content:
        ws.content[root.secret] = content.document(record.requirement_id)
    process = tree_bound_process_result(
        ws,
        root,
        iteration=iteration,
        analysis=AnalysisResult(content, {}, (), ()),
        requirement_id=record.requirement_id,
    )
    if keep_content:
        # The peer's own text stays; its Process Result produced exactly that.
        current = tree_manifest(ws, root, record.requirement_id).root_entry
        process = replace(
            process,
            output_fingerprint=current.content_fingerprint,
            output_tree=process.input_tree.with_root_fingerprint(
                current.content_fingerprint
            ),
        )
    reviewed = tree_manifest(ws, root, record.requirement_id)
    if depends_on:
        ws.depends_on_ids[record.id] = [dependency.id for dependency in depends_on]
    targets = tuple(dependency.requirement_id for dependency in depends_on)
    review = build_review_result(
        record.requirement_id,
        iteration,
        reviewed.root_entry.content_fingerprint,
        iteration,
        process.output_fingerprint,
        ReviewOutput(
            (),
            (),
            (),
            {},
            dependency_verifications=tuple(
                DependencyVerification(
                    target, VerificationOutcome.CONFIRMED, "Owns it."
                )
                for target in targets
            ),
        ),
        reviewed,
        reviewed_product_questions=(),
        dependency_bindings=bind(
            resolve_interpretation_set(ws, record, targets),
            {target: DependencyOrigin.EXISTING for target in targets},
        ),
    )
    for name, body in (
        (process_result_name(record.requirement_id, iteration), process),
        (review_result_name(record.requirement_id, iteration), review),
    ):
        node = DocumentNode(
            id=f"{record.id}-{name[-18:].replace(' ', '-')}",
            name=name,
            folder_id=None,
            entity_public_id=None,
            secret=f"{record.id}-secret-{name[-18:].replace(' ', '-')}",
            parent_document_id=root.id,
        )
        ws.documents.append(node)
        ws.content[node.secret] = (
            render_process_result(body)
            if name.endswith(f"Process Result {iteration:04d}")
            else render_review_result(body)
        )
    return review


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
    question_verifications=(),
    material_unresolved_what=(),
    rework_verifications=(),
    dependency_verifications=(),
):
    """A reviewer response. There is deliberately no verdict field.

    `rework_verifications` is always stated: a review of a Process Result
    that answered a Rework Brief must verify it (Requirement-Rework-Brief-v0.1).
    """
    body = {"rework_verifications": list(rework_verifications)}
    if dependency_verifications:
        body["dependency_verifications"] = list(dependency_verifications)
    if question_verifications:
        body["question_verifications"] = list(question_verifications)
    # Always stated: an absent list is refused (Material-WHAT Gate v0.1 §4).
    body["material_unresolved_what"] = list(material_unresolved_what)
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
