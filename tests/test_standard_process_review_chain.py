"""Process and Review composed on one Requirement, through one workspace.

They share a Root Document and both write numbered children under it, so this
is where the two capabilities can interfere with each other. The chain is run
deterministically here; the same chain is what the live acceptance exercises.
"""

from __future__ import annotations

from processor_fake import FakeModelRuntime
from review_fake import review_output, review_results, stored_review
from sdlc.process_result import parse_process_result
from sdlc.results import StandardProcessResultCode, StandardReviewResultCode
from sdlc.standard_processor import process_standard_requirement
from sdlc.standard_reviewer import review_standard_requirement
from standard_fake import (
    REQUIREMENT_ID,
    analysis_output,
    build_standard_workspace,
    process_results,
)

FINDING = {"kind": "NOT_TESTABLE", "detail": "No measurable threshold is given."}
RELATION = {
    "kind": "DEPENDS_ON",
    "requirement_id": "SDLC-FR-0002",
    "rationale": "Needs the auth check.",
}


def test_process_then_review_leaves_one_of_each_artifact():
    ws, requirement, _ = build_standard_workspace()

    processed = process_standard_requirement(
        ws,
        FakeModelRuntime(
            responses=[analysis_output(findings=[FINDING], relations=[RELATION])]
        ),
        requirement.id,
    )
    assert processed.code is StandardProcessResultCode.REQUIREMENT_PROCESSED
    assert ws.requirements[requirement.id].state == "Review"

    reviewed = review_standard_requirement(
        ws,
        FakeModelRuntime(
            responses=[
                review_output(
                    finding_verifications=[
                        {
                            "process_finding_index": 0,
                            "outcome": "CONFIRMED",
                            "severity": "BLOCKING",
                            "reason": "The document still gives no threshold.",
                        }
                    ],
                    relation_verifications=[
                        {
                            "kind": "DEPENDS_ON",
                            "requirement_id": "SDLC-FR-0002",
                            "outcome": "CONFIRMED",
                            "reason": "The dependency is real.",
                        }
                    ],
                )
            ]
        ),
        requirement.id,
    )
    assert reviewed.code is StandardReviewResultCode.REQUIREMENT_REVIEWED
    assert reviewed.verdict == "BLOCKING"
    assert ws.requirements[requirement.id].state == "Ready"
    assert len(process_results(ws)) == 1
    assert len(review_results(ws)) == 1


def test_review_binds_to_the_process_result_process_actually_wrote():
    ws, requirement, _ = build_standard_workspace()
    process_standard_requirement(
        ws, FakeModelRuntime(responses=[analysis_output()]), requirement.id
    )
    review_standard_requirement(
        ws, FakeModelRuntime(responses=[review_output()]), requirement.id
    )

    process_node = process_results(ws)[0]
    written = parse_process_result(ws.content[process_node.secret])
    stored = stored_review(ws)

    assert stored.reviewed_process_iteration == written.iteration
    assert stored.reviewed_process_output_fingerprint == written.output_fingerprint


def test_review_does_not_disturb_the_document_process_produced():
    ws, requirement, root = build_standard_workspace()
    process_standard_requirement(
        ws, FakeModelRuntime(responses=[analysis_output()]), requirement.id
    )
    after_process = ws.content[root.secret]

    review_standard_requirement(
        ws, FakeModelRuntime(responses=[review_output()]), requirement.id
    )
    assert ws.content[root.secret] == after_process


def test_a_second_process_run_after_review_ignores_the_review_result():
    """The regression the two capabilities could otherwise cause each other."""
    ws, requirement, root = build_standard_workspace()
    process_standard_requirement(
        ws, FakeModelRuntime(responses=[analysis_output()]), requirement.id
    )
    review_standard_requirement(
        ws,
        FakeModelRuntime(
            responses=[
                review_output(
                    new_findings=[
                        {
                            "kind": "NOT_TESTABLE",
                            "severity": "BLOCKING",
                            "detail": "A reviewer criticism, not requirement text.",
                        }
                    ]
                )
            ]
        ),
        requirement.id,
    )

    ws.requirements[requirement.id] = type(requirement)(
        **{**ws.requirements[requirement.id].__dict__, "state": "Process"}
    )
    ws.content[root.secret] += "\n## Added\n\nA human edit.\n"
    model = FakeModelRuntime(responses=[analysis_output()])
    process_standard_requirement(ws, model, requirement.id)

    context = model.calls[0]["context"]
    assert "A reviewer criticism" not in context
    assert "Review Result" not in context
    assert REQUIREMENT_ID in context
