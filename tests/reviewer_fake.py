"""I08 test helper: a cycle whose iteration N holds the applied Architect output.

Composition only; it adds no Fibery behaviour. The scene is the I07 test world
— real I04 bootstrap, real I05 admission and Manifest — carried through the
real `run_architect_stage`, so the Process Result and the applied Architecture
the Reviewer reviews are accepted I07 outputs, never hand-made "valid" ones.
The model is `architect_fake.RecordingModel`, whose calls land in the same
ordered trace as the Fibery operations.
"""

from __future__ import annotations

import json

from architect_fake import (
    CLAIM_COLLECTIONS,
    RecordingModel,
    accepted_scene,
    child_id,
    payload_of,
    process_id,
    reset_trace,
    response_text,
)
from sdlc.tsa_architect import run_architect_stage
from sdlc.tsa_cycle import DocumentKind
from standard_fake import REQUIREMENT_ID
from test_tsa_admission import CYCLE, NOT_APPLICABLE, PROJECT_ID, World
from test_tsa_cycle import fixed_clock

CHECKED = "Checked against the selected Requirement."


def apply_architect(scene: World, architect: str | None = None) -> None:
    """Run the real I07 stage for the current iteration, then forget the trace."""
    model = RecordingModel(scene, responses=[architect or response_text()])
    run_architect_stage(
        scene.tsa, scene.req, model, PROJECT_ID, CYCLE, clock=fixed_clock
    )
    reset_trace(scene)


def applied_scene(ux=NOT_APPLICABLE, architect: str | None = None) -> World:
    """State D, iteration 1 applied by I07 (case 3), every counter reset."""
    scene = accepted_scene(ux=ux)
    apply_architect(scene, architect)
    return scene


def review_id(iteration: int = 1) -> str:
    return child_id(DocumentKind.REVIEW_RESULT, iteration)


def decision_id(iteration: int = 1) -> str:
    return child_id(DocumentKind.HUMAN_DECISION, iteration)


def claims(scene: World, iteration: int = 1) -> list[str]:
    """The claim references of spec 6.3 for that iteration's Process Result."""
    process = payload_of(scene, process_id(iteration))
    response = process["body"]["architect_response"]
    return [
        f"{process['artifact_digest']}#{collection}/{index}"
        for collection in CLAIM_COLLECTIONS
        for index in range(len(response[collection]))
    ]


def verification(ref: str, outcome: str = "REJECTED", severity: str | None = None):
    item = {"claim_ref": ref, "outcome": outcome, "reason": CHECKED}
    if severity is not None:
        item["severity"] = severity
    return item


def finding(severity: str, detail: str = "A gap in the failure handling.") -> dict:
    return {
        "kind": "gap",
        "severity": severity,
        "detail": detail,
        "requirement_id": REQUIREMENT_ID,
    }


def reviewer_response(
    scene: World, iteration: int = 1, *, verifications=None, **changes
) -> dict:
    """A 10.1 payload; by default every claim REJECTED once, nothing raised."""
    base = {
        "claim_verifications": (
            [verification(ref) for ref in claims(scene, iteration)]
            if verifications is None
            else verifications
        ),
        "traceability_verification": {
            "outcome": "CONFIRMED",
            "reason": "Every selected Requirement is covered.",
        },
        "new_findings": [],
        "material_unresolved_what": [],
        "assessment": {
            "completeness": "Adequate.",
            "internal_consistency": "Consistent.",
            "source_fidelity": "Faithful.",
            "traceability": "Complete.",
            "implementability": "Implementable.",
        },
    }
    return {**base, **changes}


def reviewer_model(scene: World, response=None, **options) -> RecordingModel:
    """A recording runtime answering once with `response` (a dict or raw text)."""
    if response is None:
        response = reviewer_response(scene)
    text = response if isinstance(response, str) else json.dumps(response)
    return RecordingModel(scene, responses=[text], **options)


def review_writes(scene: World, iteration: int = 1) -> int:
    """Body writes to that iteration's Review Document, including failed ones."""
    document = scene.tsa.documents.get(review_id(iteration))
    if document is None:
        return 0
    return scene.tsa.log.count(("write_document_content", document.secret))


def writes_other_than_review(scene: World, iteration: int = 1) -> list[str]:
    """Every landed mutation that is not this iteration's own Review child."""
    document = scene.tsa.documents.get(review_id(iteration))
    own = {f"create:{review_id(iteration)}"}
    if document is not None:
        own.add(f"write:{document.secret}")
    return [mutation for mutation in scene.tsa.mutations if mutation not in own]
