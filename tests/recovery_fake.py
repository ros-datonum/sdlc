"""I10 test helper: recovery scenes built by the real stages, and two models.

Composition only; it adds no Fibery behaviour. Every durable state is left by
the real I04/I05 start, the real I07 and I08 stages, or a hand-sealed I01
artifact where no implemented stage writes one yet (a Human Decision, I11).
The Reviewer model answers with full claim coverage of the Process Result that
is durable when it is called, so one recovery can run Architect then Reviewer
with no response prepared in advance.
"""

from __future__ import annotations

import json

from architect_fake import (
    RecordingModel,
    human_decision,
    payload_of,
    place_child,
    reset_trace,
)
from reviewer_fake import applied_scene, review_id, reviewer_response
from sdlc.model_runtime import ModelResponse
from sdlc.tsa_artifacts import canonical_artifact_json
from sdlc.tsa_cycle import DocumentKind
from sdlc.tsa_recovery import recover_architecture_cycle
from sdlc.tsa_reviewer import run_reviewer_stage
from test_tsa_admission import CYCLE, NOT_APPLICABLE, PROJECT_ID, World
from test_tsa_cycle import fixed_clock


class CoveringReviewer(RecordingModel):
    """A Reviewer verifying every claim of the Process durable at call time."""

    def __init__(
        self, scene: World, iteration: int = 1, *, changes=None, **options
    ) -> None:
        super().__init__(scene, responses=[], **options)
        self.iteration = iteration
        self.changes = changes or {}

    def run(self, prompt: str, context: str = "") -> ModelResponse:
        if self.fake.error is None:
            response = reviewer_response(self.scene, self.iteration, **self.changes)
            self.fake.responses = [json.dumps(response)]
        return super().run(prompt, context)


def no_model(scene: World) -> RecordingModel:
    """A runtime any call to which fails the test outright."""
    return RecordingModel(scene, error=AssertionError("no model call was expected"))


def recover(scene: World, architect=None, reviewer=None, *, clock=fixed_clock):
    return recover_architecture_cycle(
        scene.tsa,
        scene.req,
        no_model(scene) if architect is None else architect,
        no_model(scene) if reviewer is None else reviewer,
        PROJECT_ID,
        CYCLE,
        clock=clock,
    )


def reviewed_scene(ux=NOT_APPLICABLE, **changes) -> World:
    """Iteration 1 applied by I07 and reviewed by I08; every counter reset.

    `changes` alter the Reviewer response, e.g. to raise a finding.
    """
    scene = applied_scene(ux=ux)
    run_reviewer_stage(
        scene.tsa,
        scene.req,
        CoveringReviewer(scene, changes=changes),
        PROJECT_ID,
        CYCLE,
        clock=fixed_clock,
    )
    reset_trace(scene)
    return scene


def decided(scene: World, decision: str, iteration: int = 1) -> dict:
    """A sealed Decision bound to that iteration's durable, real Review."""
    return human_decision(
        scene, iteration, payload_of(scene, review_id(iteration)), decision
    )


def decide(scene: World, decision: str, iteration: int = 1) -> dict:
    """Place that Decision at its derived id, as I11 would, then reset."""
    record = decided(scene, decision, iteration)
    place_child(scene, DocumentKind.HUMAN_DECISION, iteration, record)
    reset_trace(scene)
    return record


def carrier(name: str, sealed: dict) -> str:
    """A complete TSA carrier for a hand-placed Document at any id."""
    return (
        f"# {name}\n\nHand-placed TSA artifact for a test.\n\n"
        f"```json\n{canonical_artifact_json(sealed)}\n```\n"
    )
