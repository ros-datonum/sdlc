"""I08 — the Reviewer prompt: its sources, its independence and its input bound.

The pure builder is checked on hand-made material; the sources the stage
actually sends are checked on full stage runs over accepted I07 output, by
reading back the exact `prompt` and `context` the fake runtime received.
Nothing calls a real model or Fibery, so every claim here is D-class only.
"""

from __future__ import annotations

import inspect

import pytest

from architect_fake import (
    RecordingModel,
    accepted_scene,
    human_decision,
    payload_of,
    place_child,
    process_id,
    reset_trace,
    response_text,
    with_section,
)
from reviewer_fake import (
    applied_scene,
    apply_architect,
    finding,
    review_id,
    reviewer_model,
    reviewer_response,
)
from sdlc import tsa_reviewer_prompt
from sdlc.model_runtime import assemble_model_input
from sdlc.tsa_admission import SELECTION_LIMIT
from sdlc.tsa_architect import review_coverage_defects
from sdlc.tsa_architect_prompt import ASSEMBLED_INPUT_LIMIT, RequirementMaterial
from sdlc.tsa_artifacts import validate_artifact
from sdlc.tsa_cycle import DocumentKind
from sdlc.tsa_reviewer import ReviewerRefused, run_reviewer_stage
from sdlc.tsa_reviewer_prompt import (
    ReviewerInputTooLarge,
    ReviewerPrompt,
    ReviewerPromptInput,
    build_reviewer_prompt,
    claim_references,
    require_within_input_bound,
    reviewer_instructions,
)
from standard_fake import REQUIREMENT_ID
from test_tsa_admission import (
    APPLICABLE,
    ARCHITECTURE_ID,
    CYCLE,
    PROJECT_ID,
    SECOND_ID,
    UX_CONTENT,
    UX_DOCUMENT_ID,
    add_applied_requirement,
    start,
    world,
)
from test_tsa_cycle import fixed_clock

CANARY = "PREVIOUS-REVIEW-CANARY-7f3a"
NOT_APPLICABLE_UX = {
    "kind": "NOT_APPLICABLE",
    "reason": "No user-facing surface.",
    "requirement_input_digest": "a" * 64,
    "decision": {"accepted": True, "recorded_at": "2026-10-10T12:00:00Z"},
}
APPLICABLE_UX = {
    "kind": "APPLICABLE",
    "document_id": "ux-1",
    "content_digest": "b" * 64,
    "scope_requirement_ids": ["SDLC-FR-0001"],
    "approval": {"accepted": True, "recorded_at": "2026-10-10T12:00:00Z"},
}
DIGEST = "c" * 64


def claims_response(**changes) -> dict:
    base = {
        "assumptions": ["ASSUMPTION-MARKER"],
        "risks": [{"detail": "RISK-MARKER", "impact": "HIGH"}],
        "open_architecture_questions": ["QUESTION-MARKER"],
        "product_questions": [
            {
                "detail": "PRODUCT-MARKER",
                "requirement_id": "SDLC-FR-0001",
                "material": True,
            }
        ],
    }
    return {**base, **changes}


def material(**changes) -> ReviewerPromptInput:
    base = {
        "manifest_body": {"requirements": [], "ux": NOT_APPLICABLE_UX},
        "requirements": (
            RequirementMaterial(
                "SDLC-FR-0001", "e-1", "f" * 64, "<!-- document: Root -->\nROOT-BODY"
            ),
        ),
        "ux_content": None,
        "architecture_document": "# SDLC — TSA — Architecture\n\nARCH-BODY\n",
        "process_digest": DIGEST,
        "architect_response": claims_response(),
    }
    return ReviewerPromptInput(**{**base, **changes})


def review(scene, model):
    return run_reviewer_stage(
        scene.tsa, scene.req, model, PROJECT_ID, CYCLE, clock=fixed_clock
    )


# --------------------------------------------------------------------------
# The instructions (spec 10.1, 16.2; contract 7.2)
# --------------------------------------------------------------------------


def test_the_instructions_ask_for_independent_verification_of_evidence():
    text = " ".join(reviewer_instructions().split())

    assert "separate, independent invocation" in text
    assert "you are given no earlier review of it" in text
    assert "evidence to verify, not authority" in text
    for dimension in (
        "completeness",
        "internal consistency",
        "source fidelity",
        "traceability",
        "implementability",
    ):
        assert dimension in text


def test_the_instructions_forbid_verdicts_actions_and_replacement_wording():
    text = " ".join(reviewer_instructions().split())

    assert "approve or reject the architecture as a whole" in text
    assert "state a verdict, score or recommendation" in text
    assert "propose replacement wording or a rewritten architecture" in text
    assert "instruct any change to the Architecture Document" in text
    assert "derived by code" in text


def test_the_instructions_ask_for_the_final_json_only_not_a_reasoning_trace():
    text = " ".join(reviewer_instructions().lower().split())

    assert "return only one json object" in text
    assert "no explanation of how you reached it" in text
    assert "step by step" not in text and "chain of thought" not in text
    for key in (
        "claim_verifications",
        "traceability_verification",
        "new_findings",
        "material_unresolved_what",
        "assessment",
    ):
        assert key in text


def test_the_instructions_keep_severity_and_material_question_rules():
    text = " ".join(reviewer_instructions().split())

    assert "Give a severity only when you CONFIRM a claim" in text
    assert "stays open unless you REJECT it" in text
    assert "do not choose which one wins" in text


# --------------------------------------------------------------------------
# The context: the 16.2 sources only, labelled
# --------------------------------------------------------------------------


def test_the_context_carries_the_exact_architecture_trees_and_manifest():
    material_in = material()
    prompt = build_reviewer_prompt(material_in)

    assert material_in.architecture_document in prompt.context
    assert "ROOT-BODY" in prompt.context
    assert "--- Requirement SDLC-FR-0001 (entity e-1" in prompt.context
    assert '"reason": "No user-facing surface."' in prompt.context
    assert prompt.prompt == reviewer_instructions()


def test_every_claim_is_listed_with_its_exact_reference_and_assumptions_as_context():
    context = build_reviewer_prompt(material()).context

    for ref, marker in (
        (f"{DIGEST}#risks/0", "RISK-MARKER"),
        (f"{DIGEST}#open_architecture_questions/0", "QUESTION-MARKER"),
        (f"{DIGEST}#product_questions/0", "PRODUCT-MARKER"),
    ):
        assert f"- claim_ref {ref}\n" in context
        assert marker in context
    assert "Assumptions (context only; not verified)" in context
    assert "ASSUMPTION-MARKER" in context
    assert f"{DIGEST}#assumptions/" not in context


def test_the_listed_references_are_exactly_the_claims_coverage_requires():
    scene = applied_scene()
    process = validate_artifact(payload_of(scene, process_id(1)))
    required = {
        defect.split(" ", 1)[1]
        for defect in review_coverage_defects({"claim_verifications": []}, process)
    }

    listed = claim_references(
        process.artifact_digest, process.body["architect_response"]
    )

    assert set(listed) == required
    assert len(listed) == len(required)


def test_no_project_identity_and_no_rework_material_is_supplied():
    context = build_reviewer_prompt(material()).context

    assert "PROJECT IDENTITY" not in context
    assert "MATERIAL TO REVISE" not in context


@pytest.mark.parametrize(
    ("ux", "content"),
    [(NOT_APPLICABLE_UX, "invented"), (APPLICABLE_UX, None)],
    ids=["content-for-not-applicable", "no-content-for-applicable"],
)
def test_ux_content_against_the_recorded_branch_is_refused(ux, content):
    with pytest.raises(ValueError, match="exactly when"):
        build_reviewer_prompt(
            material(manifest_body={"requirements": [], "ux": ux}, ux_content=content)
        )


# --------------------------------------------------------------------------
# The bound: 400,000 code points of assembled input, 100 Requirements (15)
# --------------------------------------------------------------------------


def test_the_bound_is_measured_on_the_exact_text_the_runtime_sends():
    prompt = build_reviewer_prompt(material())

    assert prompt.assembled_length == len(
        assemble_model_input(prompt.prompt, prompt.context)
    )


def test_an_input_of_exactly_the_bound_passes_and_one_more_is_refused_whole():
    prompt = build_reviewer_prompt(material())
    filler = ASSEMBLED_INPUT_LIMIT - prompt.assembled_length
    at_limit = ReviewerPrompt(prompt.prompt, prompt.context + "é" * filler)
    over = ReviewerPrompt(prompt.prompt, at_limit.context + "x")

    require_within_input_bound(at_limit)
    with pytest.raises(ReviewerInputTooLarge, match="Nothing was truncated"):
        require_within_input_bound(over)
    assert at_limit.assembled_length == ASSEMBLED_INPUT_LIMIT
    assert over.context.endswith("x"), "the refused input is left whole"


def test_a_selection_above_the_limit_is_refused_before_assembly():
    row = RequirementMaterial("SDLC-FR-0001", "e-1", "f" * 64, "body")

    with pytest.raises(ReviewerInputTooLarge, match=str(SELECTION_LIMIT)):
        build_reviewer_prompt(material(requirements=(row,) * (SELECTION_LIMIT + 1)))


def test_the_prompt_module_reads_nothing_and_calls_no_model():
    source = inspect.getsource(tsa_reviewer_prompt)

    for forbidden in ("workspace", "read_document_content", ".run(", "subprocess"):
        assert forbidden not in source


def ux_padded_scene(padding: int):
    """Iteration 1 applied over an APPLICABLE UX Document grown by `padding`."""
    scene = world()
    scene.tsa.set_content(UX_DOCUMENT_ID, UX_CONTENT + "u" * padding)
    start(scene, ux=APPLICABLE)
    reset_trace(scene)
    architect = RecordingModel(scene, responses=[response_text()])
    apply_architect_with(scene, architect)
    return scene, architect


def apply_architect_with(scene, model) -> None:
    from sdlc.tsa_architect import run_architect_stage

    run_architect_stage(
        scene.tsa, scene.req, model, PROJECT_ID, CYCLE, clock=fixed_clock
    )
    reset_trace(scene)


def assembled(call: dict[str, str]) -> int:
    return len(assemble_model_input(call["prompt"], call["context"]))


def test_an_oversized_reviewer_input_is_refused_before_the_model_call():
    """An input the Architect could take, plus the Architecture, is too large."""
    probe, architect = ux_padded_scene(0)
    reviewer = reviewer_model(probe)
    review(probe, reviewer)
    growth = assembled(reviewer.calls[0]) - assembled(architect.calls[0])
    assert growth > 0, "the Reviewer input carries the Architecture on top"
    padding = ASSEMBLED_INPUT_LIMIT - assembled(architect.calls[0])
    scene, architect = ux_padded_scene(padding)
    assert assembled(architect.calls[0]) == ASSEMBLED_INPUT_LIMIT
    model = reviewer_model(scene)

    with pytest.raises(ReviewerRefused) as refused:
        review(scene, model)

    assert refused.value.code == "INPUT_TOO_LARGE"
    assert "Nothing was truncated" in str(refused.value)
    assert model.calls == []
    assert scene.tsa.mutations == []


# --------------------------------------------------------------------------
# What a real stage run actually sends (spec 16.2)
# --------------------------------------------------------------------------


def test_the_stage_sends_the_exact_current_architecture_and_the_full_tree():
    scene = applied_scene()
    add_applied_requirement(scene.req)
    model = reviewer_model(scene)

    review(scene, model)

    context = model.calls[0]["context"]
    assert scene.tsa.content_of(ARCHITECTURE_ID) in context
    assert scene.req.content[scene.root.secret] in context
    assert f"--- Requirement {REQUIREMENT_ID} (entity " in context
    assert SECOND_ID not in context
    assert "Second requirement" not in context


def test_the_stage_sends_the_claims_of_the_exact_persisted_process_result():
    scene = applied_scene()
    process = payload_of(scene, process_id(1))
    model = reviewer_model(scene)

    review(scene, model)

    context = model.calls[0]["context"]
    assert f"persisted Process Result {process['artifact_digest']}" in context
    for ref in claim_references(
        process["artifact_digest"], process["body"]["architect_response"]
    ):
        assert f"- claim_ref {ref}\n" in context


def test_the_stage_reads_no_ux_document_under_not_applicable():
    scene = applied_scene()
    model = reviewer_model(scene)

    review(scene, model)

    assert ("resolve_document", UX_DOCUMENT_ID) not in scene.tsa.log
    assert UX_CONTENT not in model.calls[0]["context"]
    assert "recorded NOT_APPLICABLE by the human" in model.calls[0]["context"]


def test_the_stage_sends_the_bound_ux_content_under_applicable():
    scene = applied_scene(ux=APPLICABLE)
    model = reviewer_model(scene)

    review(scene, model)

    assert UX_CONTENT in model.calls[0]["context"]


def test_a_previous_review_is_never_supplied_after_a_rework():
    scene = applied_scene()
    first = reviewer_response(scene, new_findings=[finding("WARNING", CANARY)])
    review(scene, reviewer_model(scene, first))
    previous = payload_of(scene, review_id(1))
    decision = human_decision(scene, 1, previous, "REWORK")
    place_child(scene, DocumentKind.HUMAN_DECISION, 1, decision)
    reset_trace(scene)
    apply_architect(
        scene, response_text(with_section(solution_structure="A revised structure."))
    )
    model = reviewer_model(scene, reviewer_response(scene, 2))

    result = review(scene, model)

    assert result.iteration == 2
    sent = model.calls[0]["prompt"] + model.calls[0]["context"]
    assert CANARY not in sent
    assert previous["artifact_digest"] not in sent
    assert "MATERIAL TO REVISE" not in sent
    assert "Previous Review" not in sent


def test_the_first_iteration_carries_no_review_either():
    scene = accepted_scene()
    apply_architect(scene)
    model = reviewer_model(scene)

    review(scene, model)

    assert "Review Result" not in model.calls[0]["context"]
