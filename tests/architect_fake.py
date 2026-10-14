"""I07 test helper: a cycle in durable state D, and a recording Architect.

Composition only; it adds no Fibery behaviour. The scene is the I05 test world
carried through the real `start` — real I04 bootstrap carrier, real admission
of a Requirement the frozen chain applied, a real accepted Input Manifest. The
model is `processor_fake.FakeModelRuntime`, with every call also logged into
the workspace's own operation log, so one ordered trace shows Fibery
operations and model calls together. Review Result and Human Decision
artifacts, which no implemented stage writes yet, are sealed through I01 so a
REWORK lineage can be put in place by hand.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable

from processor_fake import FakeModelRuntime
from sdlc.model_runtime import ModelResponse
from sdlc.tsa_artifacts import (
    HUMAN_DECISION,
    REVIEW_RESULT,
    SCHEMA_VERSION,
    canonical_artifact_json,
    extract_architecture_envelope,
    extract_artifact_payload,
    sealed_artifact,
    ux_evidence_digest,
)
from sdlc.tsa_cycle import DocumentKind, derive_document_id
from standard_fake import REQUIREMENT_ID
from test_tsa_admission import (
    ARCHITECTURE_ID,
    CONTEXT,
    CYCLE,
    MANIFEST_ID,
    NOT_APPLICABLE,
    PROJECT_ID,
    World,
    start,
    world,
)

TRACE_MODEL_CALL = "model.run"
LATER_TIMESTAMP = "2026-10-11T09:00:00Z"


def accepted_scene(ux=NOT_APPLICABLE) -> World:
    """A cycle in state D, with every trace and occurrence counter reset."""
    scene = world()
    start(scene, ux=ux)
    reset_trace(scene)
    return scene


def reset_trace(scene: World) -> None:
    """Forget what set the scene up: trace, counters and scripted effects."""
    scene.tsa.log.clear()
    scene.tsa.mutations.clear()
    scene.tsa.written.clear()
    scene.tsa._seen.clear()
    scene.tsa._before.clear()
    scene.tsa._after.clear()
    scene.tsa.store_as = None
    scene.req.mutations.clear()


def child_id(kind: DocumentKind, iteration: int | None = None) -> str:
    return derive_document_id(
        CONTEXT.workspace_identity,
        CONTEXT.project_entity_id,
        CYCLE,
        kind,
        iteration,
    )


def process_id(iteration: int = 1) -> str:
    return child_id(DocumentKind.PROCESS_RESULT, iteration)


def secret_of(scene: World, document_id: str) -> str:
    return scene.tsa.documents[document_id].secret


def mutation_trace(scene: World) -> list[tuple[str, str]]:
    """Creates, writes and model calls, in the order they happened."""
    kept = {
        "create_tsa_child_document",
        "create_project_document",
        "write_document_content",
        TRACE_MODEL_CALL,
    }
    return [entry for entry in scene.tsa.log if entry[0] in kept]


def architecture_writes(scene: World) -> int:
    secret = secret_of(scene, ARCHITECTURE_ID)
    return scene.tsa.log.count(("write_document_content", secret))


def architect_response(**changes) -> dict:
    """A response the closed contract of spec 9.1 accepts for the selection."""
    base = {
        "architecture": {
            "scope_and_inputs": "One Requirement about model execution guards.",
            "solution_structure": "A runtime gate in front of every model call.",
            "components_and_responsibilities": "The gate checks the login first.",
            "interfaces_and_data_flows": "The caller passes a prompt; the gate "
            "returns a refusal or the answer.",
            "data_storage": "N/A — nothing is stored.",
            "external_integrations": "The locally installed CLI.",
            "security_authn_authz": "Only the subscription login is accepted.",
            "deployment_runtime_model": "Runs inside the existing process.",
            "failure_recovery": "A refused login stops before any model call.",
            "observability": "Refusals carry a controlled message.",
            "migration_implications": "N/A — no existing data.",
            "architecture_decisions": "Refuse rather than fall back to a key; the "
            "trade-off is no service when logged out.",
        },
        "traceability": [
            {
                "requirement_id": REQUIREMENT_ID,
                "anchors": ["tsa-s03", "tsa-s08"],
                "how_satisfied": "The gate refuses an unauthenticated call.",
                "constraints": ["no API key"],
                "gaps": [],
            }
        ],
        "assumptions": ["The CLI reports its login method."],
        "risks": [{"detail": "The CLI output format changes.", "impact": "MEDIUM"}],
        "open_architecture_questions": [],
        "product_questions": [
            {
                "detail": "Should a logged-out user see a prompt to log in?",
                "requirement_id": REQUIREMENT_ID,
                "material": False,
            }
        ],
    }
    return {**base, **changes}


def with_section(**sections) -> dict:
    response = architect_response()
    response["architecture"] = {**response["architecture"], **sections}
    return response


def response_text(response: dict | None = None) -> str:
    return json.dumps(architect_response() if response is None else response)


class RecordingModel:
    """`FakeModelRuntime`, plus a trace entry and an optional effect per call.

    `model` is what the runtime reports it used; None means the CLI default.
    `during` runs inside the call, standing in for anything that changes while
    the Architect is thinking.
    """

    def __init__(
        self,
        scene: World,
        responses: list[str] | None = None,
        error: Exception | None = None,
        model: str | None = None,
        during: Callable[[], None] | None = None,
    ) -> None:
        self.scene = scene
        self.fake = FakeModelRuntime(
            responses=[response_text()] if responses is None else responses,
            error=error,
        )
        self.model = model
        self.during = during

    @property
    def calls(self) -> list[dict[str, str]]:
        return self.fake.calls

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        self.scene.tsa.log.append((TRACE_MODEL_CALL, ""))
        if self.during is not None:
            self.during()
        response = self.fake.run(prompt, context)
        return ModelResponse(text=response.text, runtime="fake", model=self.model)


def payload_of(scene: World, document_id: str) -> dict:
    return extract_artifact_payload(scene.tsa.content_of(document_id))


def manifest_payload(scene: World) -> dict:
    return payload_of(scene, MANIFEST_ID)


def resealed_carrier(content: str, change: Callable[[dict], None]) -> str:
    """The same immutable carrier with its payload changed and sealed again."""
    payload = extract_artifact_payload(content)
    changed = copy.deepcopy(payload)
    change(changed)
    sealed = sealed_artifact(changed)
    prefix = content.split("```json")[0]
    return f"{prefix}```json\n{canonical_artifact_json(sealed)}\n```\n"


def _envelope(artifact_type: str, iteration: int, body: dict) -> dict:
    return sealed_artifact(
        {
            "artifact_type": artifact_type,
            "schema_version": SCHEMA_VERSION,
            "workspace_identity": CONTEXT.workspace_identity,
            "project_entity_id": PROJECT_ID,
            "project_code": CONTEXT.project_code,
            "cycle_id": CYCLE,
            "iteration": iteration,
            "body": body,
        }
    )


def _carrier(name: str, sealed: dict) -> str:
    return (
        f"# {name}\n\nHand-placed TSA artifact for a test.\n\n"
        f"```json\n{canonical_artifact_json(sealed)}\n```\n"
    )


def review_result(scene: World, iteration: int, architecture_fingerprint: str) -> dict:
    """A sealed Review Result bound to that iteration's durable Process Result."""
    process = payload_of(scene, process_id(iteration))
    return _envelope(
        REVIEW_RESULT,
        iteration,
        {
            "manifest_digest": manifest_payload(scene)["body"]["manifest_digest"],
            "process_result_document_id": process_id(iteration),
            "process_result_digest": process["artifact_digest"],
            "architecture_document_id": ARCHITECTURE_ID,
            "architecture_fingerprint": architecture_fingerprint,
            "reviewer_response": {
                "claim_verifications": [],
                "traceability_verification": {
                    "outcome": "CONFIRMED",
                    "reason": "Every Requirement is covered.",
                },
                "new_findings": [
                    {
                        "kind": "gap",
                        "severity": "WARNING",
                        "detail": "REVIEW-FINDING-MARKER: name the refusal message.",
                        "requirement_id": REQUIREMENT_ID,
                    }
                ],
                "material_unresolved_what": [],
                "assessment": {
                    "completeness": "Adequate.",
                    "internal_consistency": "Consistent.",
                    "source_fidelity": "Faithful.",
                    "traceability": "Complete.",
                    "implementability": "Implementable.",
                },
            },
            "derived_status": "REVIEW_NEEDS_WORK",
            "runtime": {"role": "tsa_reviewer"},
            "created_at": LATER_TIMESTAMP,
        },
    )


def human_decision(
    scene: World,
    iteration: int,
    review: dict,
    decision: str = "REWORK",
) -> dict:
    """A sealed Human Decision bound to that iteration's Review and Process."""
    process = payload_of(scene, process_id(iteration))
    review_id = child_id(DocumentKind.REVIEW_RESULT, iteration)
    manifest = manifest_payload(scene)["body"]
    return _envelope(
        HUMAN_DECISION,
        iteration,
        {
            "decision": decision,
            "target": {
                "iteration": iteration,
                "review_result_document_id": review_id,
                "review_result_digest": review["artifact_digest"],
            },
            "architecture_document_id": ARCHITECTURE_ID,
            "architecture_fingerprint": review["body"]["architecture_fingerprint"],
            "manifest_digest": manifest["manifest_digest"],
            "ux_evidence_digest": ux_evidence_digest(manifest["manifest_body"]["ux"]),
            "process_result": {
                "document_id": process_id(iteration),
                "payload_digest": process["artifact_digest"],
            },
            "review_result": {
                "document_id": review_id,
                "payload_digest": review["artifact_digest"],
            },
            "accepted_dispositions": [],
            "recorded_at": LATER_TIMESTAMP,
        },
    )


def place_child(scene: World, kind: DocumentKind, iteration: int, sealed: dict) -> str:
    """Nest a hand-sealed artifact under the Architecture at its derived id."""
    document_id = child_id(kind, iteration)
    scene.tsa.seed_child(document_id, ARCHITECTURE_ID, _carrier(document_id, sealed))
    return document_id


def place_rework(scene: World, iteration: int, decision: str = "REWORK") -> None:
    """A Review Result and a Human Decision for an applied iteration."""
    envelope = extract_architecture_envelope(scene.tsa.content_of(ARCHITECTURE_ID))
    review = review_result(scene, iteration, envelope["body"]["content_fingerprint"])
    place_child(scene, DocumentKind.REVIEW_RESULT, iteration, review)
    place_child(
        scene,
        DocumentKind.HUMAN_DECISION,
        iteration,
        human_decision(scene, iteration, review, decision),
    )
