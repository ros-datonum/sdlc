"""I07 — the Architect prompt: its sources, its labels and its input bound.

The pure builder is checked on hand-made material; the sources the stage
actually reads are checked on a full stage run over the I05 world, by reading
back the exact `prompt` and `context` the fake runtime received. Nothing calls
a real model or Fibery, so every claim here is D-class only.
"""

from __future__ import annotations

import inspect

import pytest

from architect_fake import RecordingModel, accepted_scene, reset_trace, response_text
from sdlc import tsa_architect_prompt
from sdlc.model_runtime import assemble_model_input
from sdlc.tsa_admission import SELECTION_LIMIT
from sdlc.tsa_architect import ArchitectRefused, run_architect_stage
from sdlc.tsa_architect_prompt import (
    ASSEMBLED_INPUT_LIMIT,
    ArchitectInputTooLarge,
    ArchitectPrompt,
    ArchitectPromptInput,
    RequirementMaterial,
    ReworkMaterial,
    architect_instructions,
    build_architect_prompt,
    require_within_input_bound,
)
from sdlc.tsa_architecture import HEADINGS
from standard_fake import REQUIREMENT_ID
from test_tsa_admission import (
    APPLICABLE,
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


def material(**changes) -> ArchitectPromptInput:
    base = {
        "project_code": "SDLC",
        "project_name": "Delivery Lifecycle",
        "manifest_body": {"requirements": [], "ux": NOT_APPLICABLE_UX},
        "requirements": (
            RequirementMaterial(
                "SDLC-FR-0001", "e-1", "f" * 64, "<!-- document: Root -->\nROOT-BODY"
            ),
        ),
        "ux_content": None,
        "rework": None,
    }
    return ArchitectPromptInput(**{**base, **changes})


def run_stage(scene, model):
    return run_architect_stage(
        scene.tsa, scene.req, model, PROJECT_ID, CYCLE, clock=fixed_clock
    )


# --------------------------------------------------------------------------
# The instructions (spec 9.1, 16.1; contract 7.1, 7.4, 8.2)
# --------------------------------------------------------------------------


def test_the_instructions_ask_for_one_integrated_recommended_how():
    text = architect_instructions()

    assert "exactly one integrated, recommended architecture" in text
    assert "Do not present a catalogue of alternatives" in text
    assert "must not\nchange WHAT" in text


def test_the_instructions_keep_unresolved_what_as_product_questions():
    text = architect_instructions()

    assert "do not answer it and do not assume an answer" in text
    assert "product_questions" in text and '"material": true' in text


def test_the_instructions_ask_for_the_final_json_only_not_a_reasoning_trace():
    text = " ".join(architect_instructions().lower().split())

    assert "return only one json object" in text
    assert "no explanation of how you reached it" in text
    assert "step by step" not in text and "chain of thought" not in text


def test_the_instructions_carry_the_exact_response_shape_and_every_anchor():
    text = architect_instructions()

    for key in (
        "architecture",
        "traceability",
        "assumptions",
        "risks",
        "open_architecture_questions",
        "product_questions",
        "LOW|MEDIUM|HIGH",
    ):
        assert key in text
    for heading in HEADINGS:
        assert f"{heading.anchor}: {heading.number}. {heading.title}" in text


def test_the_instructions_forbid_code_blocks_and_fence_marker_lines():
    text = architect_instructions()

    assert "no code block of any kind, fenced or indented, including" in text
    assert "three or more\n  backticks or three or more tildes" in text


# --------------------------------------------------------------------------
# The context: allowed sources only, labelled (spec 16.1)
# --------------------------------------------------------------------------


def test_the_context_carries_identity_manifest_and_full_trees():
    prompt = build_architect_prompt(material())

    assert "Project code: SDLC" in prompt.context
    assert "Project name: Delivery Lifecycle" in prompt.context
    assert "identity only; not a source of requirements" in prompt.context
    assert '"reason": "No user-facing surface."' in prompt.context
    assert "ROOT-BODY" in prompt.context
    assert "--- Requirement SDLC-FR-0001 (entity e-1" in prompt.context
    assert prompt.prompt == architect_instructions()


def test_not_applicable_carries_no_ux_content_and_says_so():
    prompt = build_architect_prompt(material())

    assert "recorded NOT_APPLICABLE by the human" in prompt.context
    assert "none is supplied" in prompt.context
    assert "UX DOCUMENT (APPLICABLE" not in prompt.context


def test_applicable_carries_the_ux_content_with_its_bound_identity():
    prompt = build_architect_prompt(
        material(
            manifest_body={"requirements": [], "ux": APPLICABLE_UX},
            ux_content="UX-CONTENT-MARKER",
        )
    )

    assert "UX DOCUMENT (APPLICABLE" in prompt.context
    assert "UX-CONTENT-MARKER" in prompt.context
    assert f"content digest {'b' * 64}" in prompt.context


@pytest.mark.parametrize(
    ("ux", "content"),
    [(NOT_APPLICABLE_UX, "invented"), (APPLICABLE_UX, None)],
    ids=["content-for-not-applicable", "no-content-for-applicable"],
)
def test_ux_content_against_the_recorded_branch_is_refused(ux, content):
    with pytest.raises(ValueError, match="exactly when"):
        build_architect_prompt(
            material(manifest_body={"requirements": [], "ux": ux}, ux_content=content)
        )


def test_rework_material_is_labelled_as_material_to_revise_not_authority():
    rework = ReworkMaterial(
        previous_iteration=1,
        architecture_document="PREVIOUS-ARCHITECTURE-MARKER",
        review_findings={"new_findings": [{"detail": "FINDING-MARKER"}]},
    )

    context = build_architect_prompt(material(rework=rework)).context

    assert "MATERIAL TO REVISE (iteration 1; not authority" in context
    assert "PREVIOUS-ARCHITECTURE-MARKER" in context
    assert "FINDING-MARKER" in context
    assert context.index("SELECTED REQUIREMENTS") < context.index("MATERIAL TO REVISE")


def test_a_first_iteration_carries_no_rework_material():
    assert "MATERIAL TO REVISE" not in build_architect_prompt(material()).context


# --------------------------------------------------------------------------
# The bound: 400,000 code points of assembled input, 100 Requirements (15)
# --------------------------------------------------------------------------


def test_the_bound_is_measured_on_the_exact_text_the_runtime_sends():
    prompt = build_architect_prompt(material())

    assert prompt.assembled_length == len(
        assemble_model_input(prompt.prompt, prompt.context)
    )


def test_an_input_of_exactly_the_bound_passes_and_one_more_is_refused_whole():
    prompt = build_architect_prompt(material())
    filler = ASSEMBLED_INPUT_LIMIT - prompt.assembled_length
    at_limit = ArchitectPrompt(prompt.prompt, prompt.context + "é" * filler)
    over = ArchitectPrompt(prompt.prompt, at_limit.context + "x")

    require_within_input_bound(at_limit)
    with pytest.raises(ArchitectInputTooLarge, match="Nothing was truncated"):
        require_within_input_bound(over)
    assert at_limit.assembled_length == ASSEMBLED_INPUT_LIMIT
    assert over.context.endswith("x"), "the refused input is left whole"


def test_a_selection_above_the_limit_is_refused_before_assembly():
    row = RequirementMaterial("SDLC-FR-0001", "e-1", "f" * 64, "body")

    with pytest.raises(ArchitectInputTooLarge, match=str(SELECTION_LIMIT)):
        build_architect_prompt(material(requirements=(row,) * (SELECTION_LIMIT + 1)))


def test_the_prompt_module_reads_nothing_and_calls_no_model():
    source = inspect.getsource(tsa_architect_prompt)

    for forbidden in ("workspace", "read_document_content", ".run(", "subprocess"):
        assert forbidden not in source


# --------------------------------------------------------------------------
# What a real stage run actually sends (spec 16.1)
# --------------------------------------------------------------------------


def test_the_stage_sends_the_selected_tree_and_no_unselected_requirement():
    scene = accepted_scene()
    add_applied_requirement(scene.req)
    model = RecordingModel(scene)

    run_stage(scene, model)

    context = model.calls[0]["context"]
    root_body = scene.req.content[scene.root.secret]
    assert root_body in context
    assert f"--- Requirement {REQUIREMENT_ID} (entity " in context
    assert SECOND_ID not in context
    assert "Second requirement" not in context


def test_the_stage_reads_no_ux_document_under_not_applicable():
    scene = accepted_scene()
    model = RecordingModel(scene)

    run_stage(scene, model)

    assert ("resolve_document", UX_DOCUMENT_ID) not in scene.tsa.log
    assert UX_CONTENT not in model.calls[0]["context"]
    assert "recorded NOT_APPLICABLE by the human" in model.calls[0]["context"]


def test_the_stage_sends_the_bound_ux_content_under_applicable():
    scene = accepted_scene(ux=APPLICABLE)
    model = RecordingModel(scene)

    run_stage(scene, model)

    assert UX_CONTENT in model.calls[0]["context"]


def test_an_oversized_assembled_input_is_refused_before_any_model_call():
    """A UX Document accepted at full size pushes the input over the bound."""
    scene = world()
    scene.tsa.set_content(UX_DOCUMENT_ID, "# UX\n\n" + "u" * ASSEMBLED_INPUT_LIMIT)
    start(scene, ux=APPLICABLE)
    reset_trace(scene)
    model = RecordingModel(scene, responses=[response_text()])

    with pytest.raises(ArchitectRefused) as refused:
        run_stage(scene, model)

    assert refused.value.code == "INPUT_TOO_LARGE"
    assert "Nothing was truncated" in str(refused.value)
    assert model.calls == []
    assert scene.tsa.mutations == []
