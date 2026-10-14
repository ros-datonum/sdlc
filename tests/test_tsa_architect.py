"""I07 — the Architect stage: output contract, persist-before-apply, replay.

Every scene is a real cycle in durable state D: the I04 bootstrap carrier, a
Requirement the frozen chain applied, the real I05 admission and accepted
Input Manifest, the real I06 renderer. Only Fibery and the model are fakes, so
every claim below is D-class only; live artifact writes stay behind gate I-3
(spec 19.3).
"""

from __future__ import annotations

import ast
import inspect
import json
import unicodedata
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pytest

from architect_fake import (
    LATER_TIMESTAMP,
    RecordingModel,
    accepted_scene,
    architect_response,
    architecture_writes,
    child_id,
    mutation_trace,
    payload_of,
    place_child,
    place_rework,
    process_id,
    resealed_carrier,
    reset_trace,
    response_text,
    review_result,
    secret_of,
    with_section,
)
from sdlc import tsa_architect, tsa_markdown
from sdlc.fibery_workspace import FiberyError
from sdlc.model_runtime import (
    RUNTIME_ISOLATION_UNAVAILABLE,
    LocalCliModelRuntime,
    ModelRuntimeError,
)
from sdlc.model_runtime_config import TSA_ARCHITECT_ROLE, load_model_runtime_config
from sdlc.normative_tree import document_fingerprint
from sdlc.tsa_architect import (
    ArchitectRefused,
    ArchitectStageOutcome,
    run_architect_stage,
    select_architect_runtime,
    validate_architect_output,
)
from sdlc.tsa_architecture import (
    ArchitectureBinding,
    build_architecture_carrier,
    escape_markdown,
)
from sdlc.tsa_artifacts import (
    ARCHITECT_ROLE,
    ArtifactIdentity,
    extract_architecture_envelope,
    manifest_digest,
    sealed_artifact,
    validate_artifact,
)
from sdlc.tsa_cycle import DocumentKind
from standard_fake import REQUIREMENT_ID
from test_model_runtime import CLAUDE_OK, Runner
from test_tsa_admission import (
    APPLICABLE,
    ARCHITECTURE_ID,
    CONTEXT,
    CYCLE,
    MANIFEST_ID,
    PROJECT_ID,
    SECOND_ID,
    UX_DOCUMENT_ID,
    add_applied_requirement,
    fail,
    start,
    world,
)
from test_tsa_cycle import fixed_clock

PROCESS_ID = process_id(1)
FIBERY_DOWN = "connection reset"


def run(scene, model=None, *, clock=fixed_clock):
    return run_architect_stage(
        scene.tsa,
        scene.req,
        RecordingModel(scene) if model is None else model,
        PROJECT_ID,
        CYCLE,
        clock=clock,
    )


def no_model(scene) -> RecordingModel:
    """A runtime any call to which fails the test outright."""
    return RecordingModel(scene, error=AssertionError("no model call was expected"))


def refusal(scene, model=None, *, clock=fixed_clock) -> ArchitectRefused:
    with pytest.raises(ArchitectRefused) as caught:
        run(scene, model, clock=clock)
    return caught.value


def later_clock() -> datetime:
    return datetime(2027, 1, 2, 3, 4, 5, tzinfo=UTC)


def failing_clock() -> datetime:
    raise AssertionError("the clock was read")


def manifest_body(scene) -> dict:
    return payload_of(scene, MANIFEST_ID)["body"]["manifest_body"]


def process_payload(scene, iteration: int = 1) -> dict:
    return payload_of(scene, process_id(iteration))


def architecture_envelope(scene) -> dict:
    return extract_architecture_envelope(scene.tsa.content_of(ARCHITECTURE_ID))


def is_process_carrier(markdown: str) -> bool:
    return markdown.startswith(f"# TSA {CYCLE} — Process Result")


def other_process_carrier() -> str:
    """A valid Process Result for the same cycle, written at another time."""
    other = accepted_scene()
    run(other, clock=later_clock)
    return other.tsa.content_of(PROCESS_ID)


def persisted_but_not_applied(scene) -> None:
    """Process Result durable, the Architecture write lost before it landed."""
    scene.tsa.before("write_document_content", 2, fail(FIBERY_DOWN))
    error = refusal(scene)
    assert error.code == "FIBERY_WRITE_FAILED"
    assert architecture_writes(scene) == 1, "attempted once, never landed"
    reset_trace(scene)


def drift_requirement(scene) -> None:
    scene.req.content[scene.root.secret] += "\nA sentence added after acceptance.\n"


# --------------------------------------------------------------------------
# B. The raw response contract (spec 9.1, 9.2; v0.4 sections 4-5)
# --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def selection() -> dict:
    return manifest_body(accepted_scene())


def invalid(text: str, body: dict) -> ArchitectRefused:
    with pytest.raises(ArchitectRefused) as caught:
        validate_architect_output(text, body)
    assert caught.value.code == "INVALID_MODEL_OUTPUT"
    return caught.value


def test_a_valid_response_becomes_the_complete_intended_output(selection):
    output = validate_architect_output(response_text(), selection)

    assert set(output.intended_output) == {
        "sections",
        "traceability",
        "assumptions",
        "risks",
        "open_architecture_questions",
        "product_questions",
    }
    assert output.intended_output["sections"] == architect_response()["architecture"]
    assert output.architect_response == architect_response()


@pytest.mark.parametrize(
    "text",
    [
        "not json at all",
        "```json\n" + response_text() + "\n```",
        "Here is the architecture:\n" + response_text(),
        response_text() + "\nThat is my answer.",
        json.dumps([architect_response()]),
        response_text() + response_text(),
    ],
    ids=["prose", "fenced", "prose-before", "prose-after", "array", "two-objects"],
)
def test_anything_but_exactly_one_json_object_is_refused(text, selection):
    invalid(text, selection)


def test_whitespace_around_the_one_object_is_the_only_allowance(selection):
    validate_architect_output("\n  " + response_text() + "\n\n", selection)


def test_a_key_named_twice_is_refused_rather_than_silently_collapsed(selection):
    text = response_text()[:-1] + ', "assumptions": []}'

    error = invalid(text, selection)
    assert "more than once" in str(error)


def test_a_non_json_constant_is_refused(selection):
    response = architect_response()
    text = json.dumps(response).replace('"MEDIUM"', "NaN")

    invalid(text, selection)


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.pop("risks"),
        lambda r: r["architecture"].pop("observability"),
        lambda r: r.update(findings=[]),
        lambda r: r["risks"][0].update(impact="SEVERE"),
        lambda r: r["product_questions"][0].update(material="yes"),
        lambda r: r["traceability"][0].update(anchors=[]),
        lambda r: r["architecture"].update(observability=""),
    ],
    ids=[
        "missing-array",
        "missing-section",
        "unknown-top-key",
        "impact-enum",
        "material-type",
        "empty-anchors",
        "empty-section",
    ],
)
def test_the_closed_schema_refuses_and_fills_no_default(change, selection):
    response = architect_response()
    change(response)

    invalid(json.dumps(response), selection)


# -- row 15: structurally recognisable prohibited output ---------------------


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(tasks=[{"title": "Build the gate"}]),
        lambda r: r.update(epics=["Runtime"]),
        lambda r: r.update(estimates={"gate": "3 days"}),
        lambda r: r["risks"][0].update(estimate="2 sprints"),
        lambda r: r["traceability"][0].update(assignee="team-a"),
    ],
    ids=["tasks", "epics", "estimates", "nested-estimate", "assignment"],
)
def test_row_15_structured_tasks_epics_and_estimates_are_refused(change, selection):
    response = architect_response()
    change(response)

    error = invalid(json.dumps(response), selection)
    assert "unknown keys" in str(error)


def test_row_15_a_code_block_is_refused_by_the_validator(selection):
    text = json.dumps(with_section(solution_structure="```\ngraph TD\n```"))

    invalid(text, selection)


def test_row_15_prose_that_merely_mentions_tasks_code_or_estimates_passes(selection):
    response = with_section(
        solution_structure="Task scheduling is out of scope; the code path stays "
        "small and no estimate is given here.",
    )

    validate_architect_output(json.dumps(response), selection)


# -- rules S and X on every decoded string value, before strip ----------------


def _at(path: str, value: str) -> dict:
    response = architect_response()
    if path == "section":
        response["architecture"]["solution_structure"] = value
    elif path == "how_satisfied":
        response["traceability"][0]["how_satisfied"] = value
    elif path == "constraint":
        response["traceability"][0]["constraints"] = ["fine", value]
    elif path == "gap":
        response["traceability"][0]["gaps"] = [value]
    elif path == "risk":
        response["risks"][0]["detail"] = value
    elif path == "assumption":
        response["assumptions"] = [value]
    elif path == "question":
        response["product_questions"][0]["detail"] = value
    return response


@pytest.mark.parametrize(
    ("path", "value", "rule"),
    [
        ("section", "```\ngraph TD\n```", "rule S"),
        ("how_satisfied", "```\ngraph TD", "rule S"),
        ("risk", "~~~\ngraph TD\n~~~", "rule S"),
        ("assumption", "Structure follows.\n~~~mermaid\ngraph TD\n~~~", "rule S"),
        ("question", "Structure follows.\n\n    graph TD", "rule S"),
        ("constraint", "- ~~~\n    ordinary text\n    ~~~", "rule S"),
        ("gap", "~~~", "rule S"),
        ("section", "```inline``` then text", "rule X"),
    ],
    ids=["E01", "E02", "E03", "E05", "E06", "E08", "E12", "E13"],
)
def test_rules_s_and_x_refuse_on_nested_string_values(path, value, rule, selection):
    error = invalid(json.dumps(_at(path, value)), selection)

    assert rule in str(error)


def test_an_indented_value_is_judged_before_strip(selection):
    """Stripping would turn this into a plain line; the raw value is code."""
    error = invalid(json.dumps(_at("section", "    graph TD")), selection)

    assert "rule S" in str(error)


@pytest.mark.parametrize(
    "value",
    ["Structure follows.\n    continued text", "- ordinary ~~~ marker"],
    ids=["E07", "E10"],
)
def test_text_rule_s_reads_as_no_code_block_passes(value, selection):
    validate_architect_output(json.dumps(_at("section", value)), selection)


def test_an_unclassifiable_value_is_refused_without_claiming_code(selection):
    deep = "> " * 25 + "plain text"

    error = invalid(json.dumps(_at("section", deep)), selection)

    assert "could not be classified (NESTING_LIMIT)" in str(error)
    assert "contains a code block" not in str(error)


def test_a_parser_error_is_refused_without_claiming_code(selection, monkeypatch):
    class BrokenParser:
        def __init__(self, *_: object) -> None:
            raise RuntimeError("parser exploded")

    monkeypatch.setattr(tsa_markdown, "MarkdownIt", BrokenParser)

    error = invalid(response_text(), selection)

    assert "could not be classified (PARSER_ERROR)" in str(error)
    assert "contains a code block" not in str(error)
    assert "parser exploded" not in str(error)


def test_a_product_question_naming_an_unselected_requirement_is_refused(selection):
    response = architect_response()
    response["product_questions"][0]["requirement_id"] = "SDLC-FR-9999"

    invalid(json.dumps(response), selection)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (
            lambda r: r["traceability"].clear(),
            "TRACEABILITY_MISSING_REQUIREMENT",
        ),
        (
            lambda r: r["traceability"][0].update(anchors=["section-3"]),
            "TRACEABILITY_UNKNOWN_ANCHOR",
        ),
        (
            lambda r: r["architecture"].update(solution_structure="N/A — later"),
            "SECTION_MANDATORY_EMPTY",
        ),
    ],
    ids=["missing", "anchor", "mandatory"],
)
def test_render_refusals_keep_their_specific_codes(change, code, selection):
    response = architect_response()
    change(response)

    with pytest.raises(ArchitectRefused) as caught:
        validate_architect_output(json.dumps(response), selection)

    assert caught.value.code == code


def test_traceability_is_ordered_by_requirement_id_and_the_response_kept_verbatim():
    scene = world()
    add_applied_requirement(scene.req)
    start(scene, requirement_ids=(SECOND_ID, REQUIREMENT_ID))
    body = manifest_body(scene)
    second = {**architect_response()["traceability"][0], "requirement_id": SECOND_ID}
    response = architect_response(
        traceability=[second, architect_response()["traceability"][0]]
    )

    output = validate_architect_output(json.dumps(response), body)

    ordered = [row["requirement_id"] for row in output.intended_output["traceability"]]
    assert ordered == sorted([SECOND_ID, REQUIREMENT_ID])
    assert output.architect_response["traceability"][0]["requirement_id"] == SECOND_ID


def test_strings_take_the_nfc_form_the_persisted_artifact_carries(selection):
    decomposed = "Café gate"

    output = validate_architect_output(
        json.dumps(with_section(solution_structure=decomposed)), selection
    )

    stored = output.intended_output["sections"]["solution_structure"]
    assert stored == unicodedata.normalize("NFC", decomposed) != decomposed


# --------------------------------------------------------------------------
# The applied output: P1 vectors, product questions (spec 8.3, 8.3.1, 4.6.1)
# --------------------------------------------------------------------------


def test_p1_vectors_reach_the_applied_document_through_escape_markdown():
    scene = accepted_scene()
    response = architect_response()
    response["traceability"][0]["how_satisfied"] = "a|b\\c||d"

    run(scene, RecordingModel(scene, responses=[json.dumps(response)]))

    document = scene.tsa.content_of(ARCHITECTURE_ID)
    assert escape_markdown("a|b\\c||d") == "a\\|b\\\\c\\|\\|d"
    assert f"| {escape_markdown('a|b\\c||d')} |" in document


def test_product_questions_survive_as_evidence_and_are_not_rendered():
    scene = accepted_scene()
    question = architect_response()["product_questions"]

    run(scene)

    process = process_payload(scene)["body"]
    assert process["intended_output"]["product_questions"] == question
    assert process["architect_response"]["product_questions"] == question
    assert architecture_envelope(scene)["body"]["product_questions"] == question
    normative = scene.tsa.content_of(ARCHITECTURE_ID).split("```json")[0]
    assert question[0]["detail"] not in normative


def test_the_process_result_carries_exactly_the_frozen_body():
    scene = accepted_scene()

    result = run(scene, RecordingModel(scene, model="synthetic-architect-model"))

    payload = process_payload(scene)
    artifact = validate_artifact(payload)
    body = artifact.body
    assert artifact.iteration == 1
    assert (
        body["manifest_digest"]
        == payload_of(scene, MANIFEST_ID)["body"]["manifest_digest"]
    )
    assert body["architecture_document_id"] == ARCHITECTURE_ID
    assert body["runtime"] == {
        "role": ARCHITECT_ROLE,
        "model": "synthetic-architect-model",
    }
    assert body["created_at"] == "2026-10-10T12:00:00Z"
    assert result.process_result_digest == artifact.artifact_digest


def test_the_input_fingerprint_is_the_bootstrap_carriers_real_normative_content():
    scene = accepted_scene()
    bootstrap = scene.tsa.content_of(ARCHITECTURE_ID)

    run(scene)

    expected = document_fingerprint(bootstrap.split("\n```json")[0])
    assert process_payload(scene)["body"]["input_fingerprint"] == expected


def test_an_omitted_cli_model_is_omitted_from_the_runtime_record():
    scene = accepted_scene()

    run(scene)

    assert process_payload(scene)["body"]["runtime"] == {"role": ARCHITECT_ROLE}


# --------------------------------------------------------------------------
# C. Persist before apply (spec 14.2, 14.1)
# --------------------------------------------------------------------------


def test_the_operation_trace_persists_and_confirms_before_it_applies():
    scene = accepted_scene()

    result = run(scene)

    process_secret = secret_of(scene, PROCESS_ID)
    architecture_secret = secret_of(scene, ARCHITECTURE_ID)
    assert mutation_trace(scene) == [
        ("model.run", ""),
        ("create_tsa_child_document", PROCESS_ID),
        ("write_document_content", process_secret),
        ("write_document_content", architecture_secret),
    ]
    log = scene.tsa.log
    process_write = log.index(("write_document_content", process_secret))
    architecture_write = log.index(("write_document_content", architecture_secret))
    assert ("read_document_content", process_secret) in log[
        process_write:architecture_write
    ], "the Process Result is read back before the Architecture is written"
    assert ("read_document_content", architecture_secret) in log[architecture_write:]
    assert result.outcome is ArchitectStageOutcome.OUTPUT_APPLIED
    assert (result.model_invoked, result.process_written) == (True, True)
    assert result.architecture_written is True


def test_the_applied_document_is_exactly_the_i06_carrier_of_the_persisted_output():
    scene = accepted_scene()
    created_at = architecture_envelope(scene)["body"]["created_at"]

    result = run(scene)

    expected = build_architecture_carrier(
        process_payload(scene)["body"]["intended_output"],
        manifest_body(scene),
        ArchitectureBinding(
            ArtifactIdentity(CONTEXT.workspace_identity, PROJECT_ID, "SDLC", CYCLE),
            created_at,
            1,
        ),
    )
    assert scene.tsa.content_of(ARCHITECTURE_ID) == expected.text
    assert result.output_fingerprint == expected.content_fingerprint
    assert architecture_envelope(scene)["body"]["created_at"] == created_at


def test_a_failed_process_write_leaves_the_architecture_unwritten():
    scene = accepted_scene()
    scene.tsa.before("write_document_content", 1, fail(FIBERY_DOWN))

    error = refusal(scene)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert architecture_writes(scene) == 0
    assert scene.tsa.count("write_document_content") == 1, "no blind retry"


def test_a_process_write_that_landed_with_an_unknown_outcome_is_confirmed():
    scene = accepted_scene()
    scene.tsa.after("write_document_content", 1, fail(FIBERY_DOWN))

    result = run(scene)

    assert result.outcome is ArchitectStageOutcome.OUTPUT_APPLIED
    assert scene.tsa.count("write_document_content") == 2


@pytest.mark.parametrize(
    ("stored", "code"),
    [
        (lambda _: "", "FIBERY_WRITE_FAILED"),
        (lambda _: "   \n", "FIBERY_WRITE_FAILED"),
        (lambda _: "# junk\n\nnot a carrier\n", "ARTIFACT_MALFORMED"),
    ],
    ids=["empty", "whitespace", "malformed"],
)
def test_a_process_read_back_that_is_not_the_artifact_blocks_the_apply(stored, code):
    scene = accepted_scene()
    scene.tsa.store_as = lambda md: stored(md) if is_process_carrier(md) else md

    error = refusal(scene)

    assert error.code == code
    assert architecture_writes(scene) == 0


def test_another_valid_process_result_is_not_proof_of_the_intended_write():
    scene = accepted_scene()
    other = other_process_carrier()
    scene.tsa.store_as = lambda md: other if is_process_carrier(md) else md

    error = refusal(scene)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert "different artifact" in str(error)
    assert architecture_writes(scene) == 0


def test_an_unknown_create_that_landed_is_completed_in_place_not_recreated():
    scene = accepted_scene()
    scene.tsa.after("create_tsa_child_document", 1, fail(FIBERY_DOWN))
    model = RecordingModel(scene)

    result = run(scene, model)

    assert result.outcome is ArchitectStageOutcome.OUTPUT_APPLIED
    assert scene.tsa.count("create_tsa_child_document") == 1
    assert len(model.calls) == 1, "the output in hand fills the shell"


def test_an_unknown_create_that_did_not_land_is_retried_once_at_the_same_id():
    scene = accepted_scene()
    scene.tsa.before("create_tsa_child_document", 1, fail(FIBERY_DOWN))

    result = run(scene)

    creates = [
        entry for entry in scene.tsa.log if entry[0] == "create_tsa_child_document"
    ]
    assert creates == [("create_tsa_child_document", PROCESS_ID)] * 2
    assert result.outcome is ArchitectStageOutcome.OUTPUT_APPLIED


def test_a_create_that_never_becomes_durable_is_refused_without_a_new_id():
    scene = accepted_scene()
    scene.tsa.before("create_tsa_child_document", 1, fail(FIBERY_DOWN))
    scene.tsa.before("create_tsa_child_document", 2, fail(FIBERY_DOWN))

    error = refusal(scene)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert scene.tsa.mutations == []
    assert scene.tsa.count("create_tsa_child_document") == 2


def test_inputs_are_read_again_after_the_create_before_the_body_write():
    scene = accepted_scene()
    scene.tsa.after("create_tsa_child_document", 1, lambda: drift_requirement(scene))

    error = refusal(scene)

    assert error.code == "INPUTS_STALE"
    assert scene.tsa.content_of(PROCESS_ID) == "", "the shell stays empty"
    assert scene.tsa.count("write_document_content") == 0


def test_a_slot_filled_by_someone_else_after_the_create_is_never_written_over():
    scene = accepted_scene()
    other = other_process_carrier()
    scene.tsa.after(
        "create_tsa_child_document", 1, lambda: scene.tsa.set_content(PROCESS_ID, other)
    )

    error = refusal(scene)

    assert error.code == "ARTIFACT_DUPLICATE"
    assert scene.tsa.content_of(PROCESS_ID) == other
    assert scene.tsa.count("write_document_content") == 0


# --------------------------------------------------------------------------
# D. Replay (contract 14.3 cases 2-4; spec 4.6.3.1, 13.7-3, 14.4.1)
# --------------------------------------------------------------------------


def test_an_already_applied_output_is_a_no_op_without_a_model_call():
    scene = accepted_scene()
    run(scene)
    reset_trace(scene)

    result = run(scene, no_model(scene), clock=failing_clock)

    assert result.outcome is ArchitectStageOutcome.ALREADY_APPLIED
    assert scene.tsa.mutations == []
    assert (result.model_invoked, result.architecture_written) == (False, False)


def test_a_persisted_output_is_applied_without_a_model_call_or_a_clock():
    scene = accepted_scene()
    persisted_but_not_applied(scene)

    result = run(scene, no_model(scene), clock=failing_clock)

    assert result.outcome is ArchitectStageOutcome.RECORDED_OUTPUT_APPLIED
    assert mutation_trace(scene) == [
        ("write_document_content", secret_of(scene, ARCHITECTURE_ID))
    ]


def test_a_replay_reproduces_the_bytes_and_fingerprint_of_a_direct_apply():
    direct = accepted_scene()
    first = run(direct)
    replayed = accepted_scene()
    persisted_but_not_applied(replayed)

    second = run(replayed, no_model(replayed))

    assert replayed.tsa.content_of(ARCHITECTURE_ID) == direct.tsa.content_of(
        ARCHITECTURE_ID
    )
    assert second.output_fingerprint == first.output_fingerprint


def test_a_replay_reads_intended_output_and_never_architect_response():
    scene = accepted_scene()
    persisted_but_not_applied(scene)

    def change(payload: dict) -> None:
        payload["body"]["architect_response"]["architecture"]["solution_structure"] = (
            "ARCHITECT-RESPONSE-ONLY"
        )

    scene.tsa.set_content(
        PROCESS_ID, resealed_carrier(scene.tsa.content_of(PROCESS_ID), change)
    )

    run(scene, no_model(scene))

    document = scene.tsa.content_of(ARCHITECTURE_ID)
    assert "ARCHITECT-RESPONSE-ONLY" not in document
    assert architect_response()["architecture"]["solution_structure"] in document


def test_when_input_equals_output_case_3_wins_and_nothing_is_written():
    scene = accepted_scene()
    applied = run(scene)

    def same_input(payload: dict) -> None:
        payload["body"]["input_fingerprint"] = applied.output_fingerprint

    scene.tsa.set_content(
        PROCESS_ID, resealed_carrier(scene.tsa.content_of(PROCESS_ID), same_input)
    )
    reset_trace(scene)

    result = run(scene, no_model(scene))

    assert result.input_fingerprint == result.output_fingerprint
    assert result.outcome is ArchitectStageOutcome.ALREADY_APPLIED
    assert scene.tsa.mutations == []


def test_a_divergent_architecture_is_refused_with_all_three_fingerprints():
    scene = accepted_scene()
    applied = run(scene)
    other = validate_architect_output(
        json.dumps(with_section(solution_structure="A different structure.")),
        manifest_body(scene),
    )
    divergent = build_architecture_carrier(
        other.intended_output,
        manifest_body(scene),
        ArchitectureBinding(
            ArtifactIdentity(CONTEXT.workspace_identity, PROJECT_ID, "SDLC", CYCLE),
            architecture_envelope(scene)["body"]["created_at"],
            1,
        ),
    )
    scene.tsa.set_content(ARCHITECTURE_ID, divergent.text)
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert error.details == (
        f"input {applied.input_fingerprint}",
        f"output {applied.output_fingerprint}",
        f"current {divergent.content_fingerprint}",
    )
    assert scene.tsa.mutations == []


def test_stale_inputs_block_the_replay_of_a_persisted_output():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    drift_requirement(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "INPUTS_STALE"
    assert scene.tsa.mutations == []


def test_an_unknown_architecture_write_that_landed_is_classified_as_applied():
    scene = accepted_scene()
    scene.tsa.after("write_document_content", 2, fail(FIBERY_DOWN))

    result = run(scene)

    assert result.outcome is ArchitectStageOutcome.OUTPUT_APPLIED
    assert architecture_writes(scene) == 1, "no second apply"


def test_an_architecture_read_back_still_at_the_input_is_a_failed_write():
    scene = accepted_scene()
    bootstrap = scene.tsa.content_of(ARCHITECTURE_ID)
    scene.tsa.store_as = lambda md: bootstrap if "## 1. Scope" in md else md

    error = refusal(scene)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert architecture_writes(scene) == 1


# --------------------------------------------------------------------------
# E. Mutation windows and durable-state refusals (spec 3.5, 13.7, 14.4.1)
# --------------------------------------------------------------------------


def test_requirement_drift_before_the_call_refuses_without_a_model_call():
    scene = accepted_scene()
    drift_requirement(scene)
    model = RecordingModel(scene)

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert error.details[0] == "REQUIREMENT_NOT_ADMISSIBLE"
    assert any("content changed" in detail for detail in error.details)
    assert model.calls == []
    assert scene.tsa.mutations == []


def test_requirement_drift_during_the_call_is_never_persisted_or_applied():
    scene = accepted_scene()
    model = RecordingModel(scene, during=lambda: drift_requirement(scene))

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert len(model.calls) == 1
    assert scene.tsa.mutations == []


def test_requirement_evidence_that_stops_being_admissible_is_stale():
    scene = accepted_scene()
    entity_id = manifest_body(scene)["requirements"][0]["entity_id"]
    record = scene.req.requirements[entity_id]
    scene.req.requirements[entity_id] = replace(record, state="Process")

    error = refusal(scene)

    assert error.code == "INPUTS_STALE"
    assert error.details[0] == "REQUIREMENT_NOT_ADMISSIBLE"


def test_drift_after_the_process_is_persisted_blocks_the_apply_and_keeps_history():
    scene = accepted_scene()
    scene.tsa.after("write_document_content", 1, lambda: drift_requirement(scene))

    error = refusal(scene)

    assert error.code == "INPUTS_STALE"
    assert validate_artifact(process_payload(scene)).iteration == 1
    assert architecture_writes(scene) == 0


def test_ux_drift_during_the_call_is_stale_under_applicable():
    scene = accepted_scene(ux=APPLICABLE)
    model = RecordingModel(
        scene,
        during=lambda: scene.tsa.set_content(UX_DOCUMENT_ID, "# Changed UX\n"),
    )

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert scene.tsa.mutations == []


def test_not_applicable_never_reads_a_ux_document_on_any_revalidation():
    scene = accepted_scene()

    run(scene)

    assert not [entry for entry in scene.tsa.log if entry[1] == UX_DOCUMENT_ID]


def test_placement_drift_during_the_call_refuses_before_any_write():
    scene = accepted_scene()

    def move() -> None:
        scene.tsa.documents[ARCHITECTURE_ID].container_entity_id = "99"

    error = refusal(scene, RecordingModel(scene, during=move))

    assert error.code == "CYCLE_FOREIGN_PROJECT"
    assert scene.tsa.mutations == []


def test_an_empty_process_shell_is_completed_by_one_fresh_call_in_place():
    scene = accepted_scene()
    scene.tsa.seed_child(PROCESS_ID, ARCHITECTURE_ID, "")
    model = RecordingModel(scene)

    result = run(scene, model)

    assert len(model.calls) == 1
    assert scene.tsa.count("create_tsa_child_document") == 0
    assert result.outcome is ArchitectStageOutcome.OUTPUT_APPLIED


def test_a_process_shell_left_by_a_lost_write_is_completed_by_the_next_run():
    scene = accepted_scene()
    scene.tsa.before("write_document_content", 1, fail(FIBERY_DOWN))
    assert refusal(scene).code == "FIBERY_WRITE_FAILED"
    reset_trace(scene)
    model = RecordingModel(scene)

    result = run(scene, model)

    assert len(model.calls) == 1
    assert result.outcome is ArchitectStageOutcome.OUTPUT_APPLIED


def test_an_applied_architecture_without_its_process_result_is_not_an_input():
    scene = accepted_scene()
    run(scene)
    del scene.tsa.documents[PROCESS_ID]
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert scene.tsa.mutations == []


def test_an_architecture_changed_after_its_rework_decision_is_not_an_input():
    scene = accepted_scene()
    run(scene)
    place_rework(scene, 1)
    other = validate_architect_output(
        json.dumps(with_section(solution_structure="Edited after the decision.")),
        manifest_body(scene),
    )
    edited = build_architecture_carrier(
        other.intended_output,
        manifest_body(scene),
        ArchitectureBinding(
            ArtifactIdentity(CONTEXT.workspace_identity, PROJECT_ID, "SDLC", CYCLE),
            architecture_envelope(scene)["body"]["created_at"],
            1,
        ),
    )
    scene.tsa.set_content(ARCHITECTURE_ID, edited.text)
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert scene.tsa.mutations == []


def test_a_malformed_process_result_is_refused_and_never_repaired():
    scene = accepted_scene()
    scene.tsa.seed_child(PROCESS_ID, ARCHITECTURE_ID, "# junk\n\nnot a carrier\n")

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert scene.tsa.content_of(PROCESS_ID) == "# junk\n\nnot a carrier\n"
    assert scene.tsa.mutations == []


def test_a_valid_process_result_at_a_non_derived_id_is_a_duplicate():
    scene = accepted_scene()
    scene.tsa.seed_child("rogue-process", ARCHITECTURE_ID, other_process_carrier())

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_DUPLICATE"
    assert error.details == ("rogue-process",)


def test_a_foreign_document_at_the_process_id_is_refused():
    scene = accepted_scene()
    scene.tsa.place_foreign_document(PROCESS_ID, parent_document_id="elsewhere")

    error = refusal(scene, no_model(scene))

    assert error.code == "CYCLE_FOREIGN_PROJECT"


def test_a_process_result_for_an_iteration_no_rework_opened_is_refused():
    scene = accepted_scene()

    def to_iteration_2(payload: dict) -> None:
        payload["iteration"] = 2

    second = resealed_carrier(other_process_carrier(), to_iteration_2)
    scene.tsa.seed_child(process_id(2), ARCHITECTURE_ID, second)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert "no REWORK opened" in str(error)


@pytest.mark.parametrize(
    ("setup", "code"),
    [
        ("absent", "CYCLE_NOT_FOUND"),
        ("no manifest", "MANIFEST_INPUTS_REQUIRED"),
        ("empty manifest", "MANIFEST_SHELL_UNRECOVERABLE"),
        ("tampered bootstrap", "ARTIFACT_MALFORMED"),
    ],
)
def test_no_architect_call_before_a_valid_accepted_manifest(setup, code):
    if setup == "absent":
        scene = world("absent")
    else:
        scene = world()
        if setup == "empty manifest":
            scene.tsa.seed_child(MANIFEST_ID, ARCHITECTURE_ID, "")
        elif setup == "tampered bootstrap":
            start(scene)
            content = scene.tsa.content_of(ARCHITECTURE_ID)
            scene.tsa.set_content(ARCHITECTURE_ID, content.replace("SDLC —", "XYZ —"))
    reset_trace(scene)
    model = RecordingModel(scene)

    error = refusal(scene, model)

    assert error.code == code
    assert model.calls == []
    assert scene.tsa.mutations == []


# --------------------------------------------------------------------------
# F. Boundaries: model failure, runtime, lifecycle, downstream effects
# --------------------------------------------------------------------------


def test_row_33_a_model_failure_is_no_success_and_one_explicit_retry_works():
    scene = accepted_scene()
    failing = RecordingModel(scene, error=ModelRuntimeError("timed out after 900s"))

    error = refusal(scene, failing)

    assert error.code == "MODEL_RUNTIME_FAILED"
    assert len(failing.calls) == 1
    assert scene.tsa.mutations == []
    retry = RecordingModel(scene)
    assert run(scene, retry).outcome is ArchitectStageOutcome.OUTPUT_APPLIED
    assert len(retry.calls) == 1


def test_an_invalid_response_starts_no_repair_loop_and_persists_nothing():
    scene = accepted_scene()
    model = RecordingModel(scene, responses=["Sorry, here is prose.", response_text()])

    error = refusal(scene, model)

    assert error.code == "INVALID_MODEL_OUTPUT"
    assert len(model.calls) == 1
    assert scene.tsa.mutations == []


def test_the_architect_role_comes_from_i09_through_the_unchanged_selection():
    config = load_model_runtime_config(Path("config/sdlc.toml"))

    selection = select_architect_runtime(config)

    assert selection.role == TSA_ARCHITECT_ROLE == ARCHITECT_ROLE
    assert (selection.definition.name, selection.model) == ("claude", None)


def test_claude_runs_through_the_real_runtime_without_a_model_flag():
    scene = accepted_scene()
    runner = Runner([(0, CLAUDE_OK, ""), (0, response_text(), "")])
    runtime = LocalCliModelRuntime(
        select_architect_runtime(load_model_runtime_config(Path("config/sdlc.toml"))),
        runner=runner,
        which=lambda name: f"/opt/bin/{name}",
        environment={"PATH": "/usr/bin", "HOME": "/home/someone"},
    )

    result = run(scene, runtime)

    assert result.outcome is ArchitectStageOutcome.OUTPUT_APPLIED
    assert runner.calls[0].argv[1:] == ("auth", "status", "--json")
    assert "--model" not in runner.calls[1].argv
    assert process_payload(scene)["body"]["runtime"] == {"role": ARCHITECT_ROLE}


def test_codex_stays_blocked_with_no_subprocess_and_no_fallback():
    scene = accepted_scene()
    runner = Runner([(0, CLAUDE_OK, ""), (0, response_text(), "")])
    runtime = LocalCliModelRuntime(
        select_architect_runtime(
            load_model_runtime_config(Path("config/sdlc.toml")),
            runtime_override="codex",
        ),
        runner=runner,
        which=lambda name: f"/opt/bin/{name}",
        environment={"PATH": "/usr/bin"},
    )

    error = refusal(scene, runtime)

    assert error.code == "MODEL_RUNTIME_FAILED"
    assert any(RUNTIME_ISOLATION_UNAVAILABLE in detail for detail in error.details)
    assert runner.calls == []
    assert scene.tsa.mutations == []


def test_the_stage_writes_nothing_downstream_and_no_requirement():
    scene = accepted_scene()

    run(scene)

    assert scene.tsa.mutations == [
        f"create:{PROCESS_ID}",
        f"write:{secret_of(scene, PROCESS_ID)}",
        f"write:{secret_of(scene, ARCHITECTURE_ID)}",
    ]
    assert scene.req.mutations == []
    for kind in (DocumentKind.REVIEW_RESULT, DocumentKind.HUMAN_DECISION):
        assert child_id(kind, 1) not in scene.tsa.documents


def test_re_running_never_opens_the_next_iteration():
    scene = accepted_scene()
    run(scene)

    for _ in range(2):
        assert run(scene, no_model(scene)).iteration == 1
    assert process_id(2) not in scene.tsa.documents


def test_a_bound_rework_opens_the_next_iteration_with_labelled_material():
    scene = accepted_scene()
    first = run(scene)
    place_rework(scene, 1)
    reset_trace(scene)
    revised = with_section(solution_structure="A revised gate structure.")
    model = RecordingModel(scene, responses=[json.dumps(revised)])

    result = run(scene, model)

    assert result.iteration == 2
    assert result.input_fingerprint == first.output_fingerprint
    context = model.calls[0]["context"]
    assert "MATERIAL TO REVISE (iteration 1; not authority" in context
    assert "REVIEW-FINDING-MARKER" in context
    assert architecture_envelope(scene)["body"]["current_iteration"] == 2
    assert "A revised gate structure." in scene.tsa.content_of(ARCHITECTURE_ID)
    assert mutation_trace(scene)[1] == ("create_tsa_child_document", process_id(2))


def test_an_approved_cycle_is_closed_to_the_architect():
    scene = accepted_scene()
    run(scene)
    place_rework(scene, 1, decision="APPROVE")
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "CYCLE_APPROVED"
    assert scene.tsa.mutations == []


def test_an_empty_decision_shell_is_unrecoverable_here():
    scene = accepted_scene()
    run(scene)
    scene.tsa.seed_child(child_id(DocumentKind.HUMAN_DECISION, 1), ARCHITECTURE_ID, "")
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "DECISION_SHELL_UNRECOVERABLE"


def test_a_rework_bound_to_another_architecture_opens_nothing():
    scene = accepted_scene()
    run(scene)
    place_rework(scene, 1)
    decision_id = child_id(DocumentKind.HUMAN_DECISION, 1)

    def elsewhere(payload: dict) -> None:
        payload["body"]["process_result"]["payload_digest"] = "0" * 64

    scene.tsa.set_content(
        decision_id, resealed_carrier(scene.tsa.content_of(decision_id), elsewhere)
    )
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert scene.tsa.mutations == []


def test_a_review_without_the_applied_output_blocks_the_architect():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    scene.tsa.seed_child(child_id(DocumentKind.REVIEW_RESULT, 1), ARCHITECTURE_ID, "")
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert scene.tsa.mutations == []


def test_the_stage_neither_takes_the_command_guard_nor_reaches_real_processes():
    """The guard is the command's (I12); the model arrives as a runtime port."""
    tree = ast.parse(inspect.getsource(tsa_architect))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    for forbidden in (
        "subprocess",
        "sdlc.cli",
        "sdlc.worker_runner_guard",
        "sdlc.raw_execution_guard",
        "sdlc.requirement_runner",
        "sdlc.fibery_http",
        "sdlc.fibery_client",
    ):
        assert forbidden not in imported
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "hold_workspace" not in called
    assert "LocalCliModelRuntime" not in called


# --------------------------------------------------------------------------
# G. Lineage and operation bindings (review F1-F5; spec 4.6.3-4.6.5, 6, 10.2,
#    14.1-14.3; contract 10, 14.1.1)
#
# Every altered artifact below is resealed through I01 with its dependent
# digests recomputed, and I01 is shown to accept it, so each refusal is the
# binding check under test and never a stale digest.
# --------------------------------------------------------------------------


def accepted_by_i01(scene, document_id: str) -> dict:
    payload = payload_of(scene, document_id)
    validate_artifact(payload)
    return payload


def reseal(scene, document_id: str, change) -> dict:
    scene.tsa.set_content(
        document_id, resealed_carrier(scene.tsa.content_of(document_id), change)
    )
    return accepted_by_i01(scene, document_id)


def other_architecture(scene, solution: str):
    """A valid applied Architecture carrying an output no Process recorded."""
    other = validate_architect_output(
        json.dumps(with_section(solution_structure=solution)), manifest_body(scene)
    )
    return build_architecture_carrier(
        other.intended_output,
        manifest_body(scene),
        ArchitectureBinding(
            ArtifactIdentity(CONTEXT.workspace_identity, PROJECT_ID, "SDLC", CYCLE),
            architecture_envelope(scene)["body"]["created_at"],
            1,
        ),
    )


def replace_accepted_manifest(scene) -> None:
    """Another accepted Manifest, self-consistent: digests and acceptance agree."""

    def other_reason(payload: dict) -> None:
        body = payload["body"]
        body["manifest_body"]["ux"]["reason"] = "A different recorded UX decision."
        body["manifest_digest"] = manifest_digest(body["manifest_body"])
        body["acceptance"]["manifest_digest"] = body["manifest_digest"]

    reseal(scene, MANIFEST_ID, other_reason)


def review_id(iteration: int = 1) -> str:
    return child_id(DocumentKind.REVIEW_RESULT, iteration)


def place_review(scene, change) -> None:
    """A Review Result of iteration 1 over the applied output, then `change`."""
    fingerprint = architecture_envelope(scene)["body"]["content_fingerprint"]
    review = review_result(scene, 1, fingerprint)
    change(review)
    place_child(scene, DocumentKind.REVIEW_RESULT, 1, sealed_artifact(review))
    accepted_by_i01(scene, review_id())


# F1 — the current Process Result and Review Result bind this cycle's lineage.


@pytest.mark.parametrize(
    ("field", "value"),
    [("manifest_digest", "0" * 64), ("architecture_document_id", "another-document")],
)
def test_a_process_result_bound_elsewhere_is_malformed_before_any_replay(field, value):
    scene = accepted_scene()
    persisted_but_not_applied(scene)

    def elsewhere(payload: dict) -> None:
        payload["body"][field] = value

    reseal(scene, PROCESS_ID, elsewhere)
    model = no_model(scene)

    error = refusal(scene, model)

    assert error.code == "ARTIFACT_MALFORMED"
    assert model.calls == []
    assert scene.tsa.mutations == []


def test_a_review_bound_to_another_process_result_is_malformed():
    scene = accepted_scene()
    run(scene)
    place_review(
        scene,
        lambda review: review["body"].update(process_result_digest="0" * 64),
    )
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert scene.tsa.mutations == []


def test_a_review_of_another_architecture_fingerprint_is_malformed():
    scene = accepted_scene()
    run(scene)
    place_review(
        scene,
        lambda review: review["body"].update(architecture_fingerprint="0" * 64),
    )
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert scene.tsa.mutations == []


def test_a_review_bound_to_the_applied_output_keeps_case_3():
    scene = accepted_scene()
    run(scene)
    place_review(scene, lambda review: None)
    reset_trace(scene)

    result = run(scene, no_model(scene), clock=failing_clock)

    assert result.outcome is ArchitectStageOutcome.ALREADY_APPLIED
    assert scene.tsa.mutations == []


def test_a_correctly_bound_pending_apply_still_replays():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    accepted_by_i01(scene, PROCESS_ID)

    result = run(scene, no_model(scene), clock=failing_clock)

    assert result.outcome is ArchitectStageOutcome.RECORDED_OUTPUT_APPLIED
    assert architecture_writes(scene) == 1


# F2 — the REWORK evidence that opens N + 1 satisfies its read invariants.


def test_a_disposition_outside_its_collection_opens_no_iteration():
    scene = accepted_scene()
    run(scene)
    place_rework(
        scene,
        1,
        accept=lambda review: [f"{review['artifact_digest']}#new_findings/999"],
    )
    accepted_by_i01(scene, child_id(DocumentKind.HUMAN_DECISION, 1))
    reset_trace(scene)
    model = no_model(scene)

    error = refusal(scene, model)

    assert error.code == "ARTIFACT_MALFORMED"
    assert error.details[0] == "DISPOSITION_UNKNOWN_REFERENCE"
    assert model.calls == []
    assert scene.tsa.mutations == []


def test_a_disposition_of_an_unknown_artifact_opens_no_iteration():
    scene = accepted_scene()
    run(scene)
    place_rework(scene, 1, accept=lambda review: [f"{'1' * 64}#risks/0"])
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert error.details[0] == "DISPOSITION_UNKNOWN_REFERENCE"
    assert scene.tsa.mutations == []


def test_a_disposition_of_an_earlier_iteration_opens_no_iteration():
    scene = accepted_scene()
    run(scene)
    place_rework(scene, 1)
    first_review = payload_of(scene, review_id(1))["artifact_digest"]
    run(scene, RecordingModel(scene, responses=[response_text()]))
    place_rework(scene, 2, accept=lambda review: [f"{first_review}#new_findings/0"])
    reset_trace(scene)

    error = refusal(scene, no_model(scene))

    assert error.code == "ARTIFACT_MALFORMED"
    assert error.details[0] == "DISPOSITION_FOREIGN_ITERATION"
    assert scene.tsa.mutations == []


def test_valid_dispositions_still_open_exactly_the_next_iteration():
    scene = accepted_scene()
    run(scene)
    place_rework(
        scene,
        1,
        accept=lambda review: [
            f"{review['artifact_digest']}#new_findings/0",
            f"{payload_of(scene, PROCESS_ID)['artifact_digest']}#risks/0",
        ],
    )
    reset_trace(scene)
    model = RecordingModel(scene)

    result = run(scene, model)

    assert result.iteration == 2
    assert len(model.calls) == 1
    assert process_id(3) not in scene.tsa.documents


def without_coverage(review: dict) -> None:
    review["body"]["reviewer_response"]["claim_verifications"] = []


def material_what(review: dict) -> None:
    review["body"]["reviewer_response"]["material_unresolved_what"] = [
        {"detail": "Who may log in is undecided.", "requirement_id": REQUIREMENT_ID}
    ]


@pytest.mark.parametrize(
    ("change", "stored"),
    [
        (lambda review: None, "REVIEW_PASS"),
        (lambda review: None, "REVIEW_BLOCKING"),
        (without_coverage, "REVIEW_NEEDS_WORK"),
        (material_what, "REVIEW_NEEDS_WORK"),
    ],
    ids=["warning-stored-pass", "warning-stored-blocking", "uncovered", "what"],
)
def test_a_stored_status_the_evidence_does_not_derive_opens_no_iteration(
    change, stored
):
    scene = accepted_scene()
    run(scene)

    def mismatched(review: dict) -> None:
        change(review)
        review["body"]["derived_status"] = stored

    place_rework(scene, 1, change_review=mismatched)
    accepted_by_i01(scene, review_id())
    accepted_by_i01(scene, child_id(DocumentKind.HUMAN_DECISION, 1))
    reset_trace(scene)
    model = no_model(scene)

    error = refusal(scene, model)

    assert error.code == "ARTIFACT_MALFORMED"
    assert "derived_status" in str(error)
    assert model.calls == []
    assert scene.tsa.mutations == []


@pytest.mark.parametrize(
    ("change", "stored"),
    [
        (without_coverage, "REVIEW_STRUCTURALLY_INVALID"),
        (material_what, "REVIEW_BLOCKED_ON_WHAT"),
    ],
    ids=["uncovered", "what"],
)
def test_a_stored_status_the_evidence_derives_is_accepted(change, stored):
    scene = accepted_scene()
    run(scene)

    def derived(review: dict) -> None:
        change(review)
        review["body"]["derived_status"] = stored

    place_rework(scene, 1, change_review=derived)
    reset_trace(scene)

    assert run(scene).iteration == 2


# F3 — the operation's bindings are fixed at its start; a fresh gate never
# re-binds them.


def test_a_manifest_replaced_during_the_call_is_never_persisted_or_applied():
    scene = accepted_scene()
    model = RecordingModel(scene, during=lambda: replace_accepted_manifest(scene))

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert MANIFEST_ID in error.details
    assert "A different recorded UX decision." not in model.calls[0]["context"]
    assert scene.tsa.mutations == []


def test_a_manifest_replaced_after_the_create_leaves_only_the_shell():
    scene = accepted_scene()
    scene.tsa.after(
        "create_tsa_child_document", 1, lambda: replace_accepted_manifest(scene)
    )

    error = refusal(scene)

    assert error.code == "INPUTS_STALE"
    assert scene.tsa.content_of(PROCESS_ID) == "", "the shell stays, unfilled"
    assert scene.tsa.count("write_document_content") == 0


def test_an_architecture_replaced_after_the_create_refuses_before_the_body_write():
    scene = accepted_scene()
    divergent = other_architecture(scene, "Replaced after the create.")
    scene.tsa.after(
        "create_tsa_child_document",
        1,
        lambda: scene.tsa.set_content(ARCHITECTURE_ID, divergent.text),
    )

    error = refusal(scene)

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert scene.tsa.content_of(PROCESS_ID) == "", "the shell stays, unfilled"
    assert scene.tsa.count("write_document_content") == 0


def test_a_manifest_replaced_before_a_lost_create_is_refused_before_the_retry():
    scene = accepted_scene()

    def replace_then_lose() -> None:
        replace_accepted_manifest(scene)
        raise FiberyError(FIBERY_DOWN)

    scene.tsa.before("create_tsa_child_document", 1, replace_then_lose)
    manifest_secret = secret_of(scene, MANIFEST_ID)
    model = RecordingModel(scene)

    error = refusal(scene, model)

    assert error.code == "INPUTS_STALE"
    assert MANIFEST_ID in error.details
    assert len(model.calls) == 1
    assert scene.tsa.count("create_tsa_child_document") == 1, "no second attempt"
    assert PROCESS_ID not in scene.tsa.documents, "no durable Process Document"
    assert scene.tsa.count("write_document_content") == 0
    assert architecture_writes(scene) == 0
    after_create = scene.tsa.log[
        scene.tsa.log.index(("create_tsa_child_document", PROCESS_ID)) + 1 :
    ]
    assert ("read_document_content", manifest_secret) in after_create, (
        "the replaced Manifest was read where the retry used to be made"
    )


def test_an_unchanged_lost_create_is_retried_once_and_applied_exactly_once():
    scene = accepted_scene()
    scene.tsa.before("create_tsa_child_document", 1, fail(FIBERY_DOWN))
    model = RecordingModel(scene)

    result = run(scene, model)

    assert result.outcome is ArchitectStageOutcome.OUTPUT_APPLIED
    assert len(model.calls) == 1
    assert scene.tsa.count("create_tsa_child_document") == 2
    assert scene.tsa.mutations.count(f"create:{PROCESS_ID}") == 1, "one durable"
    process_writes = ("write_document_content", secret_of(scene, PROCESS_ID))
    assert scene.tsa.log.count(process_writes) == 1
    assert architecture_writes(scene) == 1
    accepted_by_i01(scene, PROCESS_ID)


# F4 — after an Architecture write, the Process Result is still the one applied.


def replaced_process(scene):
    """Swap the Process Result for another sealed one with a different output."""

    def other_output(payload: dict) -> None:
        text = "A materially different intended output."
        payload["body"]["intended_output"]["sections"]["solution_structure"] = text
        payload["body"]["architect_response"]["architecture"]["solution_structure"] = (
            text
        )

    def effect() -> None:
        reseal(scene, PROCESS_ID, other_output)

    return effect


def test_a_process_replaced_before_a_lost_apply_response_is_no_success():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    swap = replaced_process(scene)

    def swap_then_lose() -> None:
        swap()
        raise FiberyError(FIBERY_DOWN)

    scene.tsa.after("write_document_content", 1, swap_then_lose)
    model = no_model(scene)

    error = refusal(scene, model)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert PROCESS_ID in error.details
    assert architecture_writes(scene) == 1, "the landed write stays; no second one"
    assert model.calls == []


def test_a_process_replaced_before_a_normal_apply_read_back_is_no_success():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    scene.tsa.after("write_document_content", 1, replaced_process(scene))

    error = refusal(scene, no_model(scene))

    assert error.code == "FIBERY_WRITE_FAILED"
    assert architecture_writes(scene) == 1


def lose_response(effect):
    def effect_then_lose() -> None:
        effect()
        raise FiberyError(FIBERY_DOWN)

    return effect_then_lose


TRANSPORTS = {"normal-return": lambda effect: effect, "lost-response": lose_response}


def resealed_process(scene, field: str, value: str):
    """After the Architecture write, the Process Result changes only `field`."""

    def effect() -> None:
        reseal(
            scene, PROCESS_ID, lambda payload: payload["body"].update({field: value})
        )

    return effect


def replay_with(scene, transport: str, effect) -> RecordingModel:
    persisted_but_not_applied(scene)
    scene.tsa.after("write_document_content", 1, TRANSPORTS[transport](effect))
    return no_model(scene)


@pytest.mark.parametrize("transport", TRANSPORTS)
@pytest.mark.parametrize(
    ("field", "value"),
    [("manifest_digest", "0" * 64), ("architecture_document_id", "another-document")],
)
def test_a_process_lineage_broken_after_the_apply_is_malformed(field, value, transport):
    scene = accepted_scene()
    model = replay_with(scene, transport, resealed_process(scene, field, value))

    error = refusal(scene, model)

    assert error.code == "ARTIFACT_MALFORMED"
    assert payload_of(scene, PROCESS_ID)["body"][field] == value
    accepted_by_i01(scene, PROCESS_ID)
    assert architecture_writes(scene) == 1, "the landed write stays; no second one"
    assert model.calls == []


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_a_validly_bound_but_other_process_after_the_apply_is_unconfirmed(transport):
    scene = accepted_scene()
    model = replay_with(
        scene, transport, resealed_process(scene, "created_at", LATER_TIMESTAMP)
    )

    error = refusal(scene, model)

    assert error.code == "FIBERY_WRITE_FAILED"
    assert PROCESS_ID in error.details
    assert "stands and was neither retried nor undone" in str(error)
    assert architecture_writes(scene) == 1
    assert model.calls == []


@pytest.mark.parametrize("transport", TRANSPORTS)
def test_an_unchanged_process_after_the_apply_is_confirmed_once(transport):
    scene = accepted_scene()
    model = replay_with(scene, transport, lambda: None)

    result = run(scene, model, clock=failing_clock)

    assert result.outcome is ArchitectStageOutcome.RECORDED_OUTPUT_APPLIED
    assert architecture_writes(scene) == 1
    assert model.calls == []


def test_a_replay_whose_landed_write_lost_its_response_is_confirmed_once():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    scene.tsa.after("write_document_content", 1, fail(FIBERY_DOWN))

    result = run(scene, no_model(scene), clock=failing_clock)

    assert result.outcome is ArchitectStageOutcome.RECORDED_OUTPUT_APPLIED
    assert architecture_writes(scene) == 1


# F5 — every divergence reports the recorded input, the intended output and
# the current Architecture.


def test_a_divergent_read_back_reports_all_three_fingerprints():
    scene = accepted_scene()
    persisted_but_not_applied(scene)
    recorded = process_payload(scene)["body"]
    intended = build_architecture_carrier(
        recorded["intended_output"],
        manifest_body(scene),
        ArchitectureBinding(
            ArtifactIdentity(CONTEXT.workspace_identity, PROJECT_ID, "SDLC", CYCLE),
            architecture_envelope(scene)["body"]["created_at"],
            1,
        ),
    )
    divergent = other_architecture(scene, "Stored instead of the intended output.")
    scene.tsa.store_as = lambda md: divergent.text if "## 1. Scope" in md else md

    error = refusal(scene, no_model(scene))

    assert error.code == "ARCHITECTURE_DIVERGED"
    assert error.details == (
        f"input {recorded['input_fingerprint']}",
        f"output {intended.content_fingerprint}",
        f"current {divergent.content_fingerprint}",
    )
    assert architecture_writes(scene) == 1, "nothing overwritten or retried"
