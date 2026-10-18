"""I06 — the applied Architecture Document: template, render and validation.

Everything here is a pure calculation over in-memory values. Expected Markdown
is written out by hand, never produced by the renderer under test. Envelopes
are parsed and validated by the real I01 code; nothing stubs "schema valid".
No Fibery and no model is involved, so every claim below is D-class only.
"""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest

from architecture_fake import fibery_stored
from sdlc import tsa_architecture, tsa_cycle
from sdlc.normative_tree import TreeEntry, TreeManifest, document_fingerprint
from sdlc.tsa_architecture import (
    ANCHOR_PATTERN,
    HEADINGS,
    ArchitectureBinding,
    ArchitectureRefused,
    ArchitectureResultCode,
    build_architecture_carrier,
    escape_markdown,
    render_architecture,
    validate_architecture_document,
)
from sdlc.tsa_artifacts import (
    ARCHITECTURE_SECTION_KEYS,
    ArtifactIdentity,
    EmptyTsaCarrier,
    InvalidTsaArtifact,
    canonical_artifact_json,
    compute_artifact_digest,
    extract_architecture_envelope,
    extract_artifact_payload,
    manifest_digest,
    requirement_input_digest,
    validate_artifact,
)
from sdlc.tsa_markdown import BlockClassification, classify_code_blocks
from test_tsa_admission import CONTEXT, MANIFEST_ID, start, world
from test_tsa_artifacts import CYCLE_ID, TIMESTAMP, requirement_row
from test_tsa_cycle import bootstrap_carrier

FIRST_ID = "SDLC-FR-0007"
SECOND_ID = "SDLC-FR-0031"
# sha256 of each id, first twelve hex characters, computed outside this module.
FIRST_SOURCE = "SDLC-FR-0007 @ b564c12dbeab"
SECOND_SOURCE = "SDLC-FR-0031 @ 0882b21e2e5c"

IDENTITY = ArtifactIdentity(
    workspace_identity="example.fibery.io/11111111-2222-4333-8444-555555555555",
    project_entity_id="proj-1",
    project_code="SDLC",
    cycle_id=CYCLE_ID,
)
BINDING = ArchitectureBinding(
    identity=IDENTITY, created_at=TIMESTAMP, current_iteration=1
)

CODE = ArchitectureResultCode

FROZEN_HEADING_LINES = [
    "## 1. Scope & Inputs <!-- anchor: tsa-s01 -->",
    "## 2. Requirement Traceability <!-- anchor: tsa-s02 -->",
    "## 3. Solution Structure <!-- anchor: tsa-s03 -->",
    "## 4. Components & Responsibilities <!-- anchor: tsa-s04 -->",
    "## 5. Interfaces & Data Flows <!-- anchor: tsa-s05 -->",
    "## 6. Data / Storage <!-- anchor: tsa-s06 -->",
    "## 7. External Integrations <!-- anchor: tsa-s07 -->",
    "## 8. Security / Authentication / Authorization <!-- anchor: tsa-s08 -->",
    "## 9. Deployment / Runtime Model <!-- anchor: tsa-s09 -->",
    "## 10. Failure / Recovery <!-- anchor: tsa-s10 -->",
    "## 11. Observability <!-- anchor: tsa-s11 -->",
    "## 12. Migration Implications <!-- anchor: tsa-s12 -->",
    "## 13. Architecture Decisions / Trade-offs <!-- anchor: tsa-s13 -->",
    "## 14. Assumptions <!-- anchor: tsa-s14 -->",
    "## 15. Risks <!-- anchor: tsa-s15 -->",
    "## 16. Open Architecture Questions <!-- anchor: tsa-s16 -->",
]
MANDATORY_KEYS = (
    "scope_and_inputs",
    "solution_structure",
    "components_and_responsibilities",
    "interfaces_and_data_flows",
    "architecture_decisions",
)
OPTIONAL_KEYS = (
    "data_storage",
    "external_integrations",
    "security_authn_authz",
    "deployment_runtime_model",
    "failure_recovery",
    "observability",
    "migration_implications",
)
TABLE_HEADER = (
    "| Requirement ID | Source | Architecture anchors | How satisfied "
    "| Constraints honoured | Gaps |"
)
TABLE_SEPARATOR = "|---|---|---|---|---|---|"


def refingerprinted(row: dict[str, object], fingerprint: str) -> dict[str, object]:
    """The same Manifest row over a normative tree with another fingerprint."""
    root_id = row["tree_manifest"]["root_document_id"]
    tree = TreeManifest(
        requirement_id=row["requirement_id"],
        root_document_id=root_id,
        entries=(TreeEntry(root_id, None, "Root", fingerprint),),
    )
    return {**row, "tree_manifest": tree.to_payload(), "tree_fingerprint": fingerprint}


def manifest(*requirement_ids: str, fingerprints=None) -> dict[str, object]:
    ids = requirement_ids or (FIRST_ID, SECOND_ID)
    rows = [requirement_row(item, f"e-{item[-4:]}") for item in sorted(ids)]
    for requirement_id, fingerprint in (fingerprints or {}).items():
        index = sorted(ids).index(requirement_id)
        rows[index] = refingerprinted(rows[index], fingerprint)
    return {
        "workspace_identity": IDENTITY.workspace_identity,
        "project_code": IDENTITY.project_code,
        "project_entity_id": IDENTITY.project_entity_id,
        "cycle_id": CYCLE_ID,
        "created_at": TIMESTAMP,
        "requirements": rows,
        "ux": {
            "kind": "NOT_APPLICABLE",
            "reason": "No user-facing surface.",
            "requirement_input_digest": requirement_input_digest(rows),
            "decision": {"accepted": True, "recorded_at": TIMESTAMP},
        },
    }


def row(requirement_id: str, **changes: object) -> dict[str, object]:
    return {
        "requirement_id": requirement_id,
        "anchors": ["tsa-s03"],
        "how_satisfied": "Structure.",
        "constraints": [],
        "gaps": [],
        **changes,
    }


def sections(**changes: str) -> dict[str, str]:
    return {
        **{key: f"Prose for {key}." for key in ARCHITECTURE_SECTION_KEYS},
        **changes,
    }


def output(**changes: object) -> dict[str, object]:
    return {
        "sections": sections(),
        "traceability": [row(FIRST_ID), row(SECOND_ID)],
        "assumptions": [],
        "risks": [],
        "open_architecture_questions": [],
        "product_questions": [],
        **changes,
    }


def refused(call) -> ArchitectureResultCode:
    with pytest.raises(ArchitectureRefused) as caught:
        call()
    return caught.value.code


def render_refusal(
    intended: dict[str, object], selected=None
) -> ArchitectureResultCode:
    return refused(lambda: render_architecture(intended, selected or manifest()))


def section_bodies(markdown: str) -> dict[int, list[str]]:
    """The content lines under each numbered heading, read independently."""
    bodies: dict[int, list[str]] = {}
    current = 0
    for line in markdown.split("\n"):
        if line.startswith("## "):
            current = int(line[3:].split(".", 1)[0])
            bodies[current] = []
        elif line:
            bodies[current].append(line)
    return bodies


# --------------------------------------------------------------------------
# A. Golden rendering (contract 8, spec 8.1, 8.3)
# --------------------------------------------------------------------------

GOLDEN_OUTPUT = {
    "sections": {
        "scope_and_inputs": "Covers checkout.\nTwo services.",
        "solution_structure": "  API | worker  ",
        "components_and_responsibilities": "Gateway <edge> routes.",
        "interfaces_and_data_flows": "HTTP then queue.",
        "data_storage": "N/A — No persistent state.",
        "external_integrations": "Payment provider over HTTPS.",
        "security_authn_authz": "N/A — Inherited from the platform.",
        "deployment_runtime_model": "One container.",
        "failure_recovery": "Retry with backoff.",
        "observability": "N/A — Out of scope for this cycle.",
        "migration_implications": "N/A — Greenfield.",
        "architecture_decisions": "Queue over RPC: decoupling beats latency.",
    },
    "traceability": [
        {
            "requirement_id": FIRST_ID,
            "anchors": ["tsa-s03", "tsa-s05"],
            "how_satisfied": "API\r\nplus worker.",
            "constraints": ["Existing runtime.", "No new store."],
            "gaps": [],
        },
        {
            "requirement_id": SECOND_ID,
            "anchors": ["tsa-s03"],
            "how_satisfied": "Structure.",
            "constraints": [],
            "gaps": ["Load unknown.", "Cost | unknown"],
        },
    ],
    "assumptions": ["Fibery is reachable.", "Path C:\\data exists."],
    "risks": [{"detail": "Schema drift.", "impact": "MEDIUM"}],
    "open_architecture_questions": [],
    "product_questions": [
        {
            "detail": "Is offline supported?",
            "requirement_id": FIRST_ID,
            "material": True,
        }
    ],
}

GOLDEN_LINES = (
    "## 1. Scope & Inputs <!-- anchor: tsa-s01 -->",
    "",
    "Covers checkout.<br>Two services.",
    "",
    "## 2. Requirement Traceability <!-- anchor: tsa-s02 -->",
    "",
    "| Requirement ID | Source | Architecture anchors | How satisfied | Constraints honoured | Gaps |",
    "|---|---|---|---|---|---|",
    "| SDLC-FR-0007 | SDLC-FR-0007 @ b564c12dbeab | tsa-s03<br>tsa-s05 | API<br>plus worker. | Existing runtime.<br>No new store. |  |",
    "| SDLC-FR-0031 | SDLC-FR-0031 @ 0882b21e2e5c | tsa-s03 | Structure. |  | Load unknown.<br>Cost \\| unknown |",
    "",
    "## 3. Solution Structure <!-- anchor: tsa-s03 -->",
    "",
    "API \\| worker",
    "",
    "## 4. Components & Responsibilities <!-- anchor: tsa-s04 -->",
    "",
    "Gateway &lt;edge&gt; routes.",
    "",
    "## 5. Interfaces & Data Flows <!-- anchor: tsa-s05 -->",
    "",
    "HTTP then queue.",
    "",
    "## 6. Data / Storage <!-- anchor: tsa-s06 -->",
    "",
    "N/A — No persistent state.",
    "",
    "## 7. External Integrations <!-- anchor: tsa-s07 -->",
    "",
    "Payment provider over HTTPS.",
    "",
    "## 8. Security / Authentication / Authorization <!-- anchor: tsa-s08 -->",
    "",
    "N/A — Inherited from the platform.",
    "",
    "## 9. Deployment / Runtime Model <!-- anchor: tsa-s09 -->",
    "",
    "One container.",
    "",
    "## 10. Failure / Recovery <!-- anchor: tsa-s10 -->",
    "",
    "Retry with backoff.",
    "",
    "## 11. Observability <!-- anchor: tsa-s11 -->",
    "",
    "N/A — Out of scope for this cycle.",
    "",
    "## 12. Migration Implications <!-- anchor: tsa-s12 -->",
    "",
    "N/A — Greenfield.",
    "",
    "## 13. Architecture Decisions / Trade-offs <!-- anchor: tsa-s13 -->",
    "",
    "Queue over RPC: decoupling beats latency.",
    "",
    "## 14. Assumptions <!-- anchor: tsa-s14 -->",
    "",
    "- Fibery is reachable.",
    "- Path C:\\\\data exists.",
    "",
    "## 15. Risks <!-- anchor: tsa-s15 -->",
    "",
    "- Schema drift. — Impact: MEDIUM",
    "",
    "## 16. Open Architecture Questions <!-- anchor: tsa-s16 -->",
    "",
    "None identified.",
    "",
)
GOLDEN_MARKDOWN = "\n".join(GOLDEN_LINES)


def test_the_golden_document_is_rendered_byte_for_byte():
    assert render_architecture(GOLDEN_OUTPUT, manifest()).markdown == GOLDEN_MARKDOWN


def test_the_sixteen_headings_are_the_frozen_lines_in_the_frozen_order():
    assert [heading.line for heading in HEADINGS] == FROZEN_HEADING_LINES
    rendered = render_architecture(output(), manifest()).markdown
    headings = [line for line in rendered.split("\n") if line.startswith("#")]
    assert headings == FROZEN_HEADING_LINES


def test_the_anchors_are_two_digit_and_unique():
    anchors = [heading.anchor for heading in HEADINGS]
    assert anchors == [f"tsa-s{number:02d}" for number in range(1, 17)]
    assert all(ANCHOR_PATTERN.fullmatch(anchor) for anchor in anchors)
    assert not ANCHOR_PATTERN.fullmatch("tsa-s1")
    assert not ANCHOR_PATTERN.fullmatch("tsa-s17")
    assert not ANCHOR_PATTERN.fullmatch("tsa-s00")


def test_the_twelve_sections_map_to_their_frozen_headings():
    mapping = {h.number: h.section_key for h in HEADINGS if h.section_key}
    assert mapping == {
        1: "scope_and_inputs",
        3: "solution_structure",
        4: "components_and_responsibilities",
        5: "interfaces_and_data_flows",
        6: "data_storage",
        7: "external_integrations",
        8: "security_authn_authz",
        9: "deployment_runtime_model",
        10: "failure_recovery",
        11: "observability",
        12: "migration_implications",
        13: "architecture_decisions",
    }
    assert set(mapping.values()) == set(ARCHITECTURE_SECTION_KEYS)
    generated = {h.number: h.generated_from for h in HEADINGS if h.generated_from}
    assert generated == {
        2: "traceability",
        14: "assumptions",
        15: "risks",
        16: "open_architecture_questions",
    }
    assert {h.number for h in HEADINGS if h.is_mandatory} == {1, 2, 3, 4, 5, 13}


def test_each_section_text_lands_under_its_own_heading_only():
    rendered = render_architecture(output(), manifest()).markdown
    bodies = section_bodies(rendered)
    for heading in HEADINGS:
        if heading.section_key:
            assert bodies[heading.number] == [f"Prose for {heading.section_key}."]


def test_sections_are_separated_by_one_blank_line_and_the_text_ends_with_one_newline():
    rendered = render_architecture(GOLDEN_OUTPUT, manifest()).markdown
    assert rendered.endswith("None identified.\n")
    assert "\n\n\n" not in rendered
    assert not rendered.startswith("\n")
    lines = rendered.split("\n")
    for index, line in enumerate(lines):
        if line.startswith("## ") and index:
            assert lines[index - 1] == ""
            assert lines[index - 2] != ""


@pytest.mark.parametrize("key", OPTIONAL_KEYS)
def test_a_content_or_na_section_renders_the_na_form(key):
    intended = output(sections=sections(**{key: "N/A — Not in this cycle."}))
    bodies = section_bodies(render_architecture(intended, manifest()).markdown)
    number = next(h.number for h in HEADINGS if h.section_key == key)
    assert bodies[number] == ["N/A — Not in this cycle."]


def test_all_three_empty_lists_render_the_explicit_none():
    bodies = section_bodies(render_architecture(output(), manifest()).markdown)
    assert bodies[14] == bodies[15] == bodies[16] == ["None identified."]


def test_the_none_sentinel_is_not_used_for_any_other_section():
    rendered = render_architecture(output(), manifest()).markdown
    assert rendered.count("None identified.") == 3


def test_generated_lists_keep_array_order_and_the_frozen_item_templates():
    intended = output(
        assumptions=["Zulu.", "Alpha."],
        risks=[
            {"detail": "Second.", "impact": "HIGH"},
            {"detail": "First.", "impact": "LOW"},
        ],
        open_architecture_questions=["Why?", "How?"],
    )
    bodies = section_bodies(render_architecture(intended, manifest()).markdown)
    assert bodies[14] == ["- Zulu.", "- Alpha."]
    assert bodies[15] == ["- Second. — Impact: HIGH", "- First. — Impact: LOW"]
    assert bodies[16] == ["- Why?", "- How?"]


def test_product_questions_never_become_architecture_prose():
    question = {"detail": "Must it work offline?", "requirement_id": FIRST_ID}
    intended = output(product_questions=[{**question, "material": True}])
    rendered = render_architecture(intended, manifest())
    assert "offline" not in rendered.markdown
    assert rendered.markdown == render_architecture(output(), manifest()).markdown


# --------------------------------------------------------------------------
# Section classes (contract 8, spec 8.1) — row 14
# --------------------------------------------------------------------------


@pytest.mark.parametrize("key", MANDATORY_KEYS)
@pytest.mark.parametrize("value", ["N/A — Nothing to say.", "N/A", " N/A — x "])
def test_a_mandatory_section_holding_an_na_form_is_refused(key, value):
    intended = output(sections=sections(**{key: value}))
    assert render_refusal(intended) is CODE.SECTION_MANDATORY_EMPTY


@pytest.mark.parametrize("key", [*MANDATORY_KEYS, *OPTIONAL_KEYS])
@pytest.mark.parametrize("value", ["", "   ", "\n"])
def test_an_empty_section_is_refused_by_the_closed_schema_never_filled(key, value):
    with pytest.raises(InvalidTsaArtifact):
        render_architecture(output(sections=sections(**{key: value})), manifest())


@pytest.mark.parametrize(
    "value", ["N/A", "N/A —", "N/A — ", "N/A — first\nsecond", "N/A: no reason form"]
)
def test_a_malformed_na_in_an_optional_section_is_render_invalid(value):
    intended = output(sections=sections(data_storage=value))
    assert render_refusal(intended) is CODE.ARCHITECTURE_RENDER_INVALID


def test_prose_that_merely_starts_with_those_letters_is_content():
    intended = output(sections=sections(scope_and_inputs="N/Aware routing is used."))
    bodies = section_bodies(render_architecture(intended, manifest()).markdown)
    assert bodies[1] == ["N/Aware routing is used."]


def test_every_optional_section_na_keeps_every_requirement_in_coverage():
    na_everywhere = sections(**dict.fromkeys(OPTIONAL_KEYS, "N/A — Not applicable."))
    rendered = render_architecture(output(sections=na_everywhere), manifest())
    table = section_bodies(rendered.markdown)[2][2:]
    assert [line.split(" | ")[0] for line in table] == [
        f"| {FIRST_ID}",
        f"| {SECOND_ID}",
    ]


def test_an_na_does_not_excuse_an_omitted_requirement():
    na_everywhere = sections(**dict.fromkeys(OPTIONAL_KEYS, "N/A — Not applicable."))
    intended = output(sections=na_everywhere, traceability=[row(FIRST_ID)])
    assert render_refusal(intended) is CODE.TRACEABILITY_MISSING_REQUIREMENT


def test_a_row_answered_with_na_text_still_counts_as_that_requirements_row():
    rows = [row(FIRST_ID, how_satisfied="N/A — not addressed."), row(SECOND_ID)]
    rendered = render_architecture(output(traceability=rows), manifest())
    assert "| N/A — not addressed. |" in rendered.markdown


# --------------------------------------------------------------------------
# B. Traceability (contract 8.1, spec 8.2, 8.3.1) — row 13
# --------------------------------------------------------------------------


@pytest.mark.parametrize("kept", [FIRST_ID, SECOND_ID])
def test_traceability_that_omits_a_selected_requirement_is_refused(kept):
    intended = output(traceability=[row(kept)])
    assert render_refusal(intended) is CODE.TRACEABILITY_MISSING_REQUIREMENT


def test_empty_traceability_is_a_missing_requirement():
    assert (
        render_refusal(output(traceability=[])) is CODE.TRACEABILITY_MISSING_REQUIREMENT
    )


def test_a_row_for_an_unselected_requirement_is_refused():
    rows = [row(FIRST_ID), row(SECOND_ID), row("SDLC-FR-9999")]
    assert (
        render_refusal(output(traceability=rows))
        is CODE.TRACEABILITY_UNKNOWN_REQUIREMENT
    )


@pytest.mark.parametrize("variant", ["sdlc-fr-0007", " SDLC-FR-0007", "SDLC-FR-7"])
def test_a_requirement_id_is_matched_exactly_not_normalised(variant):
    rows = [row(variant), row(SECOND_ID)]
    assert (
        render_refusal(output(traceability=rows))
        is CODE.TRACEABILITY_UNKNOWN_REQUIREMENT
    )


def test_a_requirement_in_two_rows_is_refused():
    rows = [row(FIRST_ID), row(SECOND_ID), row(FIRST_ID, anchors=["tsa-s05"])]
    assert (
        render_refusal(output(traceability=rows))
        is CODE.TRACEABILITY_DUPLICATE_REQUIREMENT
    )


@pytest.mark.parametrize(
    "anchor",
    [
        "tsa-s1",
        "tsa-s00",
        "tsa-s17",
        "TSA-S03",
        "tsa-s03 ",
        "s03",
        "Solution Structure",
        "## 3. Solution Structure",
        "tsa-s03\n",
    ],
)
def test_an_anchor_outside_the_frozen_grammar_is_refused(anchor):
    rows = [row(FIRST_ID, anchors=["tsa-s05", anchor]), row(SECOND_ID)]
    assert render_refusal(output(traceability=rows)) is CODE.TRACEABILITY_UNKNOWN_ANCHOR


def test_the_same_anchor_twice_in_one_row_is_refused():
    rows = [row(FIRST_ID, anchors=["tsa-s03", "tsa-s05", "tsa-s03"]), row(SECOND_ID)]
    assert (
        render_refusal(output(traceability=rows)) is CODE.TRACEABILITY_DUPLICATE_ANCHOR
    )


@pytest.mark.parametrize("anchors", [[], [""], ["  "], "tsa-s03", None])
def test_empty_anchors_are_refused_by_the_closed_schema(anchors):
    rows = [row(FIRST_ID, anchors=anchors), row(SECOND_ID)]
    with pytest.raises(InvalidTsaArtifact):
        render_architecture(output(traceability=rows), manifest())


def test_one_anchor_shared_by_different_requirements_is_allowed():
    rows = [row(FIRST_ID, anchors=["tsa-s03"]), row(SECOND_ID, anchors=["tsa-s03"])]
    table = section_bodies(
        render_architecture(output(traceability=rows), manifest()).markdown
    )[2]
    assert len(table) == 4
    assert all(" | tsa-s03 | " in line for line in table[2:])


def test_every_one_of_the_sixteen_anchors_is_accepted():
    anchors = [f"tsa-s{number:02d}" for number in range(1, 17)]
    rows = [row(FIRST_ID, anchors=anchors), row(SECOND_ID)]
    rendered = render_architecture(output(traceability=rows), manifest()).markdown
    assert "<br>".join(anchors) in rendered


def test_table_rows_are_ordered_by_requirement_id_whatever_the_input_order():
    ascending = output(traceability=[row(FIRST_ID), row(SECOND_ID)])
    descending = output(traceability=[row(SECOND_ID), row(FIRST_ID)])
    first = render_architecture(ascending, manifest()).markdown
    assert first == render_architecture(descending, manifest()).markdown
    table = section_bodies(first)[2]
    assert table[:2] == [TABLE_HEADER, TABLE_SEPARATOR]
    assert [line.split(" | ")[0] for line in table[2:]] == [
        f"| {FIRST_ID}",
        f"| {SECOND_ID}",
    ]


def test_the_source_column_comes_from_the_manifest_fingerprint():
    table = section_bodies(render_architecture(output(), manifest()).markdown)[2]
    assert [line.split(" | ")[1] for line in table[2:]] == [FIRST_SOURCE, SECOND_SOURCE]


def test_the_source_column_follows_the_manifest_and_nothing_the_model_says():
    selected = manifest(fingerprints={FIRST_ID: "1234567890ab" + "c" * 52})
    rows = [row(FIRST_ID, how_satisfied="SDLC-FR-0007 @ ffffffffffff"), row(SECOND_ID)]
    table = section_bodies(
        render_architecture(output(traceability=rows), selected).markdown
    )[2]
    assert table[2].split(" | ")[1] == "SDLC-FR-0007 @ 1234567890ab"


def test_a_row_cannot_carry_a_source_of_its_own():
    rows = [{**row(FIRST_ID), "source": "elsewhere"}, row(SECOND_ID)]
    with pytest.raises(InvalidTsaArtifact):
        render_architecture(output(traceability=rows), manifest())


def test_only_the_manifest_selection_and_the_intended_output_reach_the_document():
    selected = manifest(FIRST_ID)
    rendered = render_architecture(output(traceability=[row(FIRST_ID)]), selected)
    assert "No user-facing surface." not in rendered.markdown
    assert IDENTITY.project_code + " —" not in rendered.markdown
    assert SECOND_ID not in rendered.markdown


def test_a_real_accepted_i05_manifest_drives_coverage_and_source():
    accepted = start(world()).artifact
    body = accepted.body["manifest_body"]
    [selected] = body["requirements"]
    intended = output(traceability=[row(selected["requirement_id"])])
    table = section_bodies(render_architecture(intended, body).markdown)[2]
    source = f"{selected['requirement_id']} @ {selected['tree_fingerprint'][:12]}"
    assert table[2].split(" | ")[1] == source
    carrier = build_architecture_carrier(
        intended, body, ArchitectureBinding(accepted.identity, TIMESTAMP, 1)
    )
    assert carrier.artifact.body["manifest_digest"] == accepted.body["manifest_digest"]
    assert accepted.cycle_id == CONTEXT.cycle_id


# --------------------------------------------------------------------------
# C. Escaping (spec 8.3.1)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "escaped"),
    [
        ("plain text", "plain text"),
        ("  padded \t\n", "padded"),
        ("a\\b", "a\\\\b"),
        ("a|b", "a\\|b"),
        ("a\\|b", "a\\\\\\|b"),
        ("a\r\nb", "a<br>b"),
        ("a\rb", "a<br>b"),
        ("a\nb", "a<br>b"),
        ("a\n\r\nb", "a<br><br>b"),
        ("a\r\rb", "a<br><br>b"),
        ("a<b", "a&lt;b"),
        ("a>b", "a&gt;b"),
        ("a<br>b", "a&lt;br&gt;b"),
        ("<br>\n<br>", "&lt;br&gt;<br>&lt;br&gt;"),
        ("&lt; &amp; stay", "&lt; &amp; stay"),
        ("Café — ‘цикл’ 日本 🧭", "Café — ‘цикл’ 日本 🧭"),
        ("e\u0301 decomposed", "e\u0301 decomposed"),
        ("", ""),
        ("   ", ""),
    ],
)
def test_escape_markdown_maps_each_source_character_once(source, escaped):
    assert escape_markdown(source) == escaped


def test_escaping_is_single_pass_over_the_original_text():
    once = escape_markdown("a\nb")
    assert once == "a<br>b"
    assert escape_markdown(once) == "a&lt;br&gt;b"
    assert escape_markdown("\\<") == "\\\\&lt;"


def test_the_module_does_not_chain_whole_string_replacements():
    source = inspect.getsource(tsa_architecture)
    assert ".replace(" not in source


NASTY = "a|b\\c\r\n<d> <br> é"
NASTY_ESCAPED = "a\\|b\\\\c<br>&lt;d&gt; &lt;br&gt; é"


def test_array_cells_are_escaped_element_by_element_then_joined():
    rows = [
        row(
            FIRST_ID,
            how_satisfied=NASTY,
            constraints=[NASTY, "plain"],
            gaps=["x\ny", " z "],
        ),
        row(SECOND_ID),
    ]
    table = section_bodies(
        render_architecture(output(traceability=rows), manifest()).markdown
    )[2]
    assert table[2] == (
        f"| {FIRST_ID} | {FIRST_SOURCE} | tsa-s03 | {NASTY_ESCAPED} "
        f"| {NASTY_ESCAPED}<br>plain | x<br>y<br>z |"
    )


def test_an_empty_array_renders_an_empty_cell():
    table = section_bodies(render_architecture(output(), manifest()).markdown)[2]
    assert table[2] == f"| {FIRST_ID} | {FIRST_SOURCE} | tsa-s03 | Structure. |  |  |"


def test_escaping_applies_to_prose_and_to_every_generated_list():
    intended = output(
        sections=sections(scope_and_inputs=NASTY, data_storage="N/A — a|b\\c"),
        assumptions=[NASTY],
        risks=[{"detail": NASTY, "impact": "LOW"}],
        open_architecture_questions=[NASTY],
    )
    bodies = section_bodies(render_architecture(intended, manifest()).markdown)
    assert bodies[1] == [NASTY_ESCAPED]
    assert bodies[6] == ["N/A — a\\|b\\\\c"]
    assert bodies[14] == [f"- {NASTY_ESCAPED}"]
    assert bodies[15] == [f"- {NASTY_ESCAPED} — Impact: LOW"]
    assert bodies[16] == [f"- {NASTY_ESCAPED}"]


def test_multi_line_model_text_never_adds_a_line_to_the_document():
    noisy = output(
        sections=sections(solution_structure="one\n\n## 99. Injected\n\ntwo"),
        assumptions=["first\n- second\n## 3. Fake"],
    )
    rendered = render_architecture(noisy, manifest()).markdown
    assert len(rendered.split("\n")) == len(
        render_architecture(output(assumptions=["x"]), manifest()).markdown.split("\n")
    )
    assert [line for line in rendered.split("\n") if line.startswith("#")] == (
        FROZEN_HEADING_LINES
    )


@pytest.mark.parametrize(
    "value",
    [
        "# A title",
        "## 3. Solution Structure",
        "###### deep",
        "```mermaid\ngraph TD\n```",
    ],
)
def test_prose_that_would_add_a_heading_or_open_a_fence_is_render_invalid(value):
    intended = output(sections=sections(solution_structure=value))
    assert render_refusal(intended) is CODE.ARCHITECTURE_RENDER_INVALID


def test_a_json_fence_in_prose_cannot_forge_a_second_envelope():
    intended = output(sections=sections(solution_structure="```json"))
    assert render_refusal(intended) is CODE.ARCHITECTURE_RENDER_INVALID
    inline = output(sections=sections(solution_structure="see ```json\n{}\n``` here"))
    carrier = build_architecture_carrier(inline, manifest(), BINDING)
    assert validate_artifact(extract_architecture_envelope(carrier.text))


# --------------------------------------------------------------------------
# D. Replay and fingerprint (spec 4.6.1, 4.6.3.1)
# --------------------------------------------------------------------------


def test_the_same_pair_renders_the_same_bytes_and_fingerprint_every_time():
    first = render_architecture(GOLDEN_OUTPUT, manifest())
    render_architecture(output(), manifest(FIRST_ID, SECOND_ID))
    with pytest.raises(ArchitectureRefused):
        render_architecture(output(traceability=[]), manifest())
    again = render_architecture(copy.deepcopy(GOLDEN_OUTPUT), manifest())
    assert again == first
    assert again.markdown.encode() == first.markdown.encode()


def test_the_fingerprint_is_document_fingerprint_of_the_rendered_markdown():
    rendered = render_architecture(GOLDEN_OUTPUT, manifest())
    assert rendered.content_fingerprint == document_fingerprint(GOLDEN_MARKDOWN)


def test_rendering_and_assembly_do_not_mutate_their_inputs():
    intended, selected = copy.deepcopy(GOLDEN_OUTPUT), manifest()
    before = (copy.deepcopy(intended), copy.deepcopy(selected))
    render_architecture(intended, selected)
    carrier = build_architecture_carrier(intended, selected, BINDING)
    validate_architecture_document(carrier.text, selected)
    assert (intended, selected) == before
    unordered = output(traceability=[row(SECOND_ID), row(FIRST_ID)])
    render_architecture(unordered, selected)
    assert unordered["traceability"][0]["requirement_id"] == SECOND_ID


def test_the_envelope_arrays_are_copies_not_aliases_of_the_input():
    intended = copy.deepcopy(GOLDEN_OUTPUT)
    carrier = build_architecture_carrier(intended, manifest(), BINDING)
    intended["assumptions"].append("Added later.")
    intended["risks"][0]["impact"] = "HIGH"
    assert carrier.artifact.body["assumptions"] == GOLDEN_OUTPUT["assumptions"]
    assert carrier.artifact.body["risks"] == GOLDEN_OUTPUT["risks"]


def test_the_renderer_takes_the_intended_output_and_the_manifest_and_nothing_else():
    assert list(inspect.signature(render_architecture).parameters) == [
        "intended_output",
        "manifest_body",
    ]


def test_an_architect_response_is_neither_needed_nor_accepted():
    with pytest.raises(InvalidTsaArtifact):
        render_architecture({**output(), "architect_response": {}}, manifest())
    response_shaped = {key: value for key, value in output().items()}
    response_shaped["architecture"] = response_shaped.pop("sections")
    with pytest.raises(InvalidTsaArtifact):
        render_architecture(response_shaped, manifest())


def test_replay_reads_only_intended_output_from_a_process_result_body():
    process_body = {
        "intended_output": copy.deepcopy(GOLDEN_OUTPUT),
        "architect_response": {
            "architecture": sections(scope_and_inputs="A contradicting response."),
            "traceability": [],
            "assumptions": ["Different."],
            "risks": [],
            "open_architecture_questions": [],
            "product_questions": [],
        },
    }
    replayed = render_architecture(process_body["intended_output"], manifest())
    assert replayed.markdown == GOLDEN_MARKDOWN


@pytest.mark.parametrize(
    "change",
    [
        {"sections": sections(scope_and_inputs="Another scope.")},
        {"assumptions": ["One assumption."]},
        {"risks": [{"detail": "A risk.", "impact": "LOW"}]},
        {"open_architecture_questions": ["A question?"]},
        {"traceability": [row(FIRST_ID, anchors=["tsa-s05"]), row(SECOND_ID)]},
        {"traceability": [row(FIRST_ID, gaps=["A gap."]), row(SECOND_ID)]},
    ],
)
def test_a_change_to_normative_markdown_changes_the_fingerprint(change):
    base = render_architecture(output(), manifest())
    changed = render_architecture(output(**change), manifest())
    assert changed.markdown != base.markdown
    assert changed.content_fingerprint != base.content_fingerprint


def test_a_changed_manifest_tree_fingerprint_changes_the_source_and_the_fingerprint():
    selected = manifest(fingerprints={SECOND_ID: "9" * 64})
    base = render_architecture(output(), manifest())
    assert (
        render_architecture(output(), selected).content_fingerprint
        != base.content_fingerprint
    )


def test_the_envelope_is_outside_the_content_fingerprint():
    question = {"detail": "Offline?", "requirement_id": FIRST_ID, "material": True}
    plain = build_architecture_carrier(output(), manifest(), BINDING)
    other = build_architecture_carrier(
        output(product_questions=[question]),
        manifest(),
        ArchitectureBinding(IDENTITY, "2027-01-02T03:04:05Z", 7),
    )
    assert plain.content_fingerprint == other.content_fingerprint
    assert plain.artifact.artifact_digest != other.artifact.artifact_digest
    assert plain.text != other.text


def test_the_stored_fingerprint_covers_exactly_the_text_before_the_fence():
    carrier = build_architecture_carrier(GOLDEN_OUTPUT, manifest(), BINDING)
    prefix, fence, _ = carrier.text.partition("```json\n")
    assert fence
    assert prefix == GOLDEN_MARKDOWN
    assert carrier.content_fingerprint == document_fingerprint(prefix)
    assert carrier.artifact.body["content_fingerprint"] == carrier.content_fingerprint
    assert carrier.content_fingerprint != document_fingerprint(carrier.text)
    assert carrier.content_fingerprint not in prefix


# --------------------------------------------------------------------------
# E. The post-apply carrier and the lifecycle boundary (spec 4.1, 4.1.1, 4.6.1)
# --------------------------------------------------------------------------


def golden_carrier():
    return build_architecture_carrier(GOLDEN_OUTPUT, manifest(), BINDING)


def reseal(text: str, mutate) -> str:
    """The same Document with its envelope changed and its digest recomputed."""
    prefix, _, _ = text.partition("```json\n")
    payload = extract_architecture_envelope(text)
    mutate(payload["body"])
    unsealed = {k: v for k, v in payload.items() if k != "artifact_digest"}
    sealed = {**unsealed, "artifact_digest": compute_artifact_digest(unsealed)}
    return f"{prefix}```json\n{json.dumps(sealed)}\n```\n"


def edit_markdown(text: str, old: str, new: str) -> str:
    assert text.count(old) == 1, old
    return text.replace(old, new)


def document_refusal(text: str, selected=None) -> ArchitectureResultCode:
    return refused(lambda: validate_architecture_document(text, selected or manifest()))


def test_the_assembled_carrier_passes_the_real_i01_parser_and_validator():
    carrier = golden_carrier()
    artifact = validate_artifact(extract_architecture_envelope(carrier.text))
    assert artifact == carrier.artifact
    assert artifact.artifact_type == "tsa.architecture"
    assert artifact.iteration is None
    assert carrier.text.endswith("\n```\n")
    assert carrier.text.count("```json") == 1


def test_the_envelope_carries_the_binding_exactly_as_supplied():
    body = golden_carrier().artifact.body
    assert body["cycle_id"] == CYCLE_ID
    assert body["created_at"] == TIMESTAMP
    assert body["current_iteration"] == 1
    assert body["manifest_digest"] == manifest_digest(manifest())
    assert golden_carrier().artifact.identity == IDENTITY


def test_the_five_renderer_owned_arrays_are_copied_verbatim():
    body = golden_carrier().artifact.body
    for key in (
        "traceability",
        "assumptions",
        "risks",
        "open_architecture_questions",
        "product_questions",
    ):
        assert body[key] == GOLDEN_OUTPUT[key]
    assert body["product_questions"][0]["material"] is True
    assert set(body) == {
        "cycle_id",
        "created_at",
        "manifest_digest",
        "content_fingerprint",
        "current_iteration",
        "traceability",
        "assumptions",
        "risks",
        "open_architecture_questions",
        "product_questions",
    }


def test_empty_arrays_stay_present_as_arrays():
    body = build_architecture_carrier(output(), manifest(), BINDING).artifact.body
    assert body["assumptions"] == body["risks"] == body["product_questions"] == []
    assert body["open_architecture_questions"] == []


def test_assembly_is_deterministic_for_one_binding():
    assert golden_carrier() == golden_carrier()


@pytest.mark.parametrize(
    "binding",
    [
        ArchitectureBinding(IDENTITY, "2026-09-29 18:00", 1),
        ArchitectureBinding(IDENTITY, TIMESTAMP, 0),
        ArchitectureBinding(IDENTITY, TIMESTAMP, 1000),
        ArchitectureBinding(
            ArtifactIdentity(IDENTITY.workspace_identity, "proj-2", "SDLC", CYCLE_ID),
            TIMESTAMP,
            1,
        ),
        ArchitectureBinding(
            ArtifactIdentity(IDENTITY.workspace_identity, "proj-1", "", CYCLE_ID),
            TIMESTAMP,
            1,
        ),
    ],
)
def test_a_binding_the_closed_schema_refuses_is_never_repaired(binding):
    with pytest.raises(InvalidTsaArtifact):
        build_architecture_carrier(output(), manifest(), binding)


def test_a_valid_document_validates_and_returns_its_artifact():
    carrier = golden_carrier()
    assert validate_architecture_document(carrier.text, manifest()) == carrier.artifact


def test_validation_accepts_what_fibery_is_known_to_re_serialize():
    text = golden_carrier().text
    stored = text.replace("\n- ", "\n* ").removesuffix("\n")
    assert stored != text
    assert (
        validate_architecture_document(stored, manifest()) == golden_carrier().artifact
    )


HEADING_DEFECTS = {
    "renamed": ("## 3. Solution Structure <!--", "## 3. Solution Shape <!--"),
    "renumbered": ("## 3. Solution", "## 03. Solution"),
    "one-digit anchor": ("anchor: tsa-s03 -->", "anchor: tsa-s3 -->"),
    "another anchor": ("anchor: tsa-s03 -->", "anchor: tsa-s04 -->"),
    "no anchor": (
        "## 3. Solution Structure <!-- anchor: tsa-s03 -->",
        "## 3. Solution Structure",
    ),
    "another level": ("## 3. Solution", "### 3. Solution"),
    "missing": ("## 3. Solution Structure <!-- anchor: tsa-s03 -->\n\n", ""),
    "added level 1": ("## 1. Scope", "# Architecture\n\n## 1. Scope"),
    "added level 2": (
        "## 16. Open",
        "## 17. Extra <!-- anchor: tsa-s17 -->\n\n## 16. Open",
    ),
    "added after sixteen": (
        "None identified.\n",
        "None identified.\n\n## 17. Extra <!-- anchor: tsa-s17 -->\n\nMore.\n",
    ),
    "introduction": ("## 1. Scope", "An introduction.\n\n## 1. Scope"),
    "fenced block": ("HTTP then queue.", "```text\nHTTP then queue.\n```"),
}


@pytest.mark.parametrize("label", sorted(HEADING_DEFECTS))
def test_a_document_with_wrong_headings_or_anchors_is_render_invalid(label):
    old, new = HEADING_DEFECTS[label]
    text = edit_markdown(golden_carrier().text, old, new)
    assert validate_artifact(extract_architecture_envelope(text))
    assert document_refusal(text) is CODE.ARCHITECTURE_RENDER_INVALID


def test_two_swapped_sections_are_render_invalid():
    text = golden_carrier().text
    third = "## 3. Solution Structure <!-- anchor: tsa-s03 -->\n\nAPI \\| worker\n\n"
    fourth = (
        "## 4. Components & Responsibilities <!-- anchor: tsa-s04 -->\n\n"
        "Gateway &lt;edge&gt; routes.\n\n"
    )
    swapped = edit_markdown(text, third + fourth, fourth + third)
    assert document_refusal(swapped) is CODE.ARCHITECTURE_RENDER_INVALID


def test_a_mandatory_section_reduced_to_na_in_the_document_is_refused():
    text = edit_markdown(golden_carrier().text, "HTTP then queue.", "N/A — Later.")
    assert document_refusal(text) is CODE.SECTION_MANDATORY_EMPTY


@pytest.mark.parametrize("old", ["HTTP then queue.\n\n", "One container.\n\n"])
def test_a_section_with_no_content_in_the_document_is_render_invalid(old):
    text = edit_markdown(golden_carrier().text, old, "")
    assert document_refusal(text) is CODE.ARCHITECTURE_RENDER_INVALID


def test_a_malformed_na_in_the_document_is_render_invalid():
    text = edit_markdown(golden_carrier().text, "N/A — Greenfield.", "N/A")
    assert document_refusal(text) is CODE.ARCHITECTURE_RENDER_INVALID


TABLE_DEFECTS = {
    "another id": (
        "| SDLC-FR-0007 | SDLC-FR-0007 @",
        "| SDLC-FR-0008 | SDLC-FR-0007 @",
    ),
    "another source": ("@ b564c12dbeab", "@ ffffffffffff"),
    "another anchor": ("| tsa-s03<br>tsa-s05 |", "| tsa-s03<br>tsa-s06 |"),
    "anchor dropped": ("| tsa-s03<br>tsa-s05 |", "| tsa-s03 |"),
    "row dropped": (
        "| SDLC-FR-0031 | SDLC-FR-0031 @ 0882b21e2e5c | tsa-s03 | Structure. |  | Load unknown.<br>Cost \\| unknown |\n",
        "",
    ),
    "row repeated": (
        "|---|---|---|---|---|---|\n",
        "|---|---|---|---|---|---|\n| SDLC-FR-0007 | SDLC-FR-0007 @ b564c12dbeab | tsa-s03<br>tsa-s05 | x |  |  |\n",
    ),
    "header renamed": ("| Requirement ID | Source |", "| Requirement | Source |"),
    "separator missing": ("|---|---|---|---|---|---|\n", ""),
    "cell missing": ("| Existing runtime.<br>No new store. |  |", "|  |"),
    "unescaped pipe": ("Cost \\| unknown", "Cost | unknown"),
    "not a table row": (
        "| SDLC-FR-0031 | SDLC-FR-0031 @",
        "SDLC-FR-0031 | SDLC-FR-0031 @",
    ),
}


@pytest.mark.parametrize("label", sorted(TABLE_DEFECTS))
def test_a_table_that_disagrees_with_the_envelope_is_render_invalid(label):
    old, new = TABLE_DEFECTS[label]
    text = edit_markdown(golden_carrier().text, old, new)
    assert document_refusal(text) is CODE.ARCHITECTURE_RENDER_INVALID


def test_rows_in_another_order_than_requirement_id_are_render_invalid():
    text = golden_carrier().text
    lines = text.split("\n")
    first = next(i for i, line in enumerate(lines) if line.startswith("| SDLC-FR-0007"))
    lines[first], lines[first + 1] = lines[first + 1], lines[first]
    assert document_refusal("\n".join(lines)) is CODE.ARCHITECTURE_RENDER_INVALID


def drop_second_row(body: dict) -> None:
    body["traceability"] = [
        r for r in body["traceability"] if r["requirement_id"] != SECOND_ID
    ]


def repeat_first_row(body: dict) -> None:
    body["traceability"].append(copy.deepcopy(body["traceability"][1]))


def name_unselected(body: dict) -> None:
    body["traceability"].append(row("SDLC-FR-9999"))


def unknown_anchor(body: dict) -> None:
    body["traceability"][0]["anchors"] = ["tsa-s3"]


def duplicate_anchor(body: dict) -> None:
    body["traceability"][0]["anchors"] = ["tsa-s03", "tsa-s03"]


ENVELOPE_COVERAGE_DEFECTS = {
    "missing": (drop_second_row, CODE.TRACEABILITY_MISSING_REQUIREMENT),
    "duplicate": (repeat_first_row, CODE.TRACEABILITY_DUPLICATE_REQUIREMENT),
    "unknown": (name_unselected, CODE.TRACEABILITY_UNKNOWN_REQUIREMENT),
    "unknown anchor": (unknown_anchor, CODE.TRACEABILITY_UNKNOWN_ANCHOR),
    "duplicate anchor": (duplicate_anchor, CODE.TRACEABILITY_DUPLICATE_ANCHOR),
}


@pytest.mark.parametrize("label", sorted(ENVELOPE_COVERAGE_DEFECTS))
def test_envelope_traceability_is_held_to_the_same_coverage_rules(label):
    mutate, code = ENVELOPE_COVERAGE_DEFECTS[label]
    text = reseal(golden_carrier().text, mutate)
    assert validate_artifact(extract_architecture_envelope(text))
    assert document_refusal(text) is code


def test_a_valid_envelope_whose_anchors_differ_from_the_table_is_render_invalid():
    def other_anchor(body: dict) -> None:
        body["traceability"][0]["anchors"] = ["tsa-s09"]

    text = reseal(golden_carrier().text, other_anchor)
    assert document_refusal(text) is CODE.ARCHITECTURE_RENDER_INVALID


LIST_DEFECTS = {
    "assumption dropped": lambda body: body["assumptions"].pop(),
    "assumption reworded": lambda body: body["assumptions"].__setitem__(0, "Other."),
    "risk impact": lambda body: body["risks"][0].__setitem__("impact", "HIGH"),
    "risks emptied": lambda body: body["risks"].clear(),
    "question added": lambda body: body["open_architecture_questions"].append("Why?"),
}


@pytest.mark.parametrize("label", sorted(LIST_DEFECTS))
def test_a_generated_list_that_disagrees_with_the_envelope_is_render_invalid(label):
    text = reseal(golden_carrier().text, LIST_DEFECTS[label])
    assert validate_artifact(extract_architecture_envelope(text))
    assert document_refusal(text) is CODE.ARCHITECTURE_RENDER_INVALID


def test_product_questions_live_in_the_envelope_and_survive_a_round_trip():
    carrier = golden_carrier()
    read_back = validate_architecture_document(carrier.text, manifest())
    assert read_back.body["product_questions"] == GOLDEN_OUTPUT["product_questions"]
    assert "Is offline supported?" not in carrier.text.partition("```json")[0]


def test_edited_prose_is_caught_by_the_fingerprint_not_by_the_structure():
    text = edit_markdown(golden_carrier().text, "One container.", "Two containers.")
    assert validate_artifact(extract_architecture_envelope(text))
    with pytest.raises(InvalidTsaArtifact, match="content_fingerprint"):
        validate_architecture_document(text, manifest())


def test_a_wrong_stored_fingerprint_with_a_valid_digest_is_refused():
    text = reseal(
        golden_carrier().text,
        lambda body: body.__setitem__("content_fingerprint", "0" * 64),
    )
    assert validate_artifact(extract_architecture_envelope(text))
    with pytest.raises(InvalidTsaArtifact, match="content_fingerprint"):
        validate_architecture_document(text, manifest())


def test_a_tampered_envelope_fails_the_i01_digest_before_any_render_rule():
    text = golden_carrier().text.replace(
        '"current_iteration":1', '"current_iteration":2'
    )
    with pytest.raises(InvalidTsaArtifact, match="digest"):
        validate_architecture_document(text, manifest())


def test_render_validation_and_envelope_validation_are_separate_checks():
    structurally_wrong = edit_markdown(
        golden_carrier().text, "anchor: tsa-s03 -->", "anchor: tsa-s3 -->"
    )
    assert validate_artifact(extract_architecture_envelope(structurally_wrong))
    assert document_refusal(structurally_wrong) is CODE.ARCHITECTURE_RENDER_INVALID
    render_architecture(GOLDEN_OUTPUT, manifest())
    schema_wrong = golden_carrier().text.replace(
        '"schema_version":1', '"schema_version":2'
    )
    with pytest.raises(InvalidTsaArtifact):
        validate_architecture_document(schema_wrong, manifest())


def test_an_envelope_bound_to_another_manifest_is_refused():
    with pytest.raises(InvalidTsaArtifact, match="another Input Manifest"):
        validate_architecture_document(golden_carrier().text, manifest(FIRST_ID))


def test_a_manifest_of_another_project_is_refused():
    foreign = {**manifest(), "project_entity_id": "proj-2"}
    with pytest.raises(InvalidTsaArtifact):
        validate_architecture_document(golden_carrier().text, foreign)


CARRIER_DEFECTS = {
    "no envelope": lambda text: text.partition("```json")[0],
    "second envelope": lambda text: text + "\n```json\n{}\n```\n",
    "content after the fence": lambda text: text + "\nTrailing prose.\n",
    "unclosed fence": lambda text: text.removesuffix("```\n"),
    "payload not json": lambda text: (
        text.partition("```json\n")[0] + "```json\nnot json\n```\n"
    ),
    "envelope only": lambda text: "```json\n" + text.partition("```json\n")[2],
}


@pytest.mark.parametrize("label", sorted(CARRIER_DEFECTS))
def test_a_malformed_carrier_keeps_the_i01_refusal(label):
    text = CARRIER_DEFECTS[label](golden_carrier().text)
    with pytest.raises(InvalidTsaArtifact) as caught:
        validate_architecture_document(text, manifest())
    assert caught.value.code == "ARTIFACT_MALFORMED"


@pytest.mark.parametrize("text", ["", "  \n", None])
def test_an_empty_document_is_an_empty_carrier_not_a_render_defect(text):
    with pytest.raises(EmptyTsaCarrier):
        validate_architecture_document(text, manifest())


def test_another_artifact_type_under_sixteen_headings_is_refused():
    scene = world()
    accepted = start(scene).artifact
    manifest_payload = extract_artifact_payload(scene.tsa.content_of(MANIFEST_ID))
    text = f"{GOLDEN_MARKDOWN}\n```json\n{json.dumps(manifest_payload)}\n```\n"
    assert validate_artifact(extract_architecture_envelope(text)) == accepted
    with pytest.raises(InvalidTsaArtifact, match="tsa.input_manifest"):
        validate_architecture_document(text, accepted.body["manifest_body"])


def test_the_i04_bootstrap_carrier_is_not_a_sixteen_heading_document():
    bootstrap = bootstrap_carrier()
    assert validate_artifact(extract_architecture_envelope(bootstrap))
    assert "## " not in bootstrap
    selected = {
        **manifest(),
        "workspace_identity": CONTEXT.workspace_identity,
        "project_entity_id": CONTEXT.project_entity_id,
        "project_code": CONTEXT.project_code,
        "cycle_id": CONTEXT.cycle_id,
    }
    assert document_refusal(bootstrap, selected) is CODE.ARCHITECTURE_RENDER_INVALID


def test_bootstrap_stays_on_the_i04_path_and_never_reaches_the_renderer():
    assert "tsa_architecture" not in inspect.getsource(tsa_cycle)
    source = inspect.getsource(tsa_architecture)
    assert "tsa_cycle" not in source
    assert "Bootstrap shell" not in source


def test_the_module_has_no_workspace_model_clock_or_random_dependency():
    source = inspect.getsource(tsa_architecture)
    imports = [
        line for line in source.split("\n") if line.startswith(("import ", "from "))
    ]
    assert imports == [
        "from __future__ import annotations",
        "import copy",
        "import re",
        "from collections.abc import Sequence",
        "from dataclasses import dataclass",
        "from enum import StrEnum",
        "from sdlc.normative_tree import document_fingerprint",
        "from sdlc.tsa_artifacts import (",
        "from sdlc.tsa_markdown import (",
    ]
    for forbidden in (
        "workspace.",
        "datetime",
        "uuid",
        "random",
        "subprocess",
        "open(",
    ):
        assert forbidden not in source


def test_the_result_codes_are_the_frozen_names():
    assert {code.value for code in ArchitectureResultCode} == {
        "ARCHITECTURE_RENDER_INVALID",
        "SECTION_MANDATORY_EMPTY",
        "TRACEABILITY_MISSING_REQUIREMENT",
        "TRACEABILITY_UNKNOWN_REQUIREMENT",
        "TRACEABILITY_DUPLICATE_REQUIREMENT",
        "TRACEABILITY_UNKNOWN_ANCHOR",
        "TRACEABILITY_DUPLICATE_ANCHOR",
    }


# --------------------------------------------------------------------------
# F. Corrections after the independent review of I06 (F1-F4)
# --------------------------------------------------------------------------

ENVELOPE_OPENER = "```json\n"
RENDER_INVALID = CODE.ARCHITECTURE_RENDER_INVALID
PLAIN_PROSE = "Prose for solution_structure."
LATER_PROSE = "Prose for interfaces_and_data_flows."
THIRD_ID = "SDLC-FR-0042"


def assembled(intended: dict[str, object], selected=None):
    return build_architecture_carrier(intended, selected or manifest(), BINDING)


def rebound(text: str, edit=None, mutate=None) -> str:
    """The Document after a change, with both digests recomputed.

    The result is a carrier I01 accepts: its `content_fingerprint` is the
    fingerprint of the changed Markdown and its `artifact_digest` is fresh, so
    a refusal that follows is never the refusal of a stale digest.
    """
    prefix, _, _ = text.partition(ENVELOPE_OPENER)
    payload = extract_architecture_envelope(text)
    if edit is not None:
        prefix = edit(prefix)
    if mutate is not None:
        mutate(payload["body"])
    payload["body"]["content_fingerprint"] = document_fingerprint(prefix)
    unsealed = {k: v for k, v in payload.items() if k != "artifact_digest"}
    sealed = {**unsealed, "artifact_digest": compute_artifact_digest(unsealed)}
    result = f"{prefix}{ENVELOPE_OPENER}{canonical_artifact_json(sealed)}\n```\n"
    stored = validate_artifact(extract_architecture_envelope(result))
    assert stored.body["content_fingerprint"] == document_fingerprint(prefix)
    return result


def headings_outside_fences(text: str) -> list[str]:
    """The heading lines Markdown sees, by CommonMark's fence rules.

    Written independently of the module under test: a fence opens on a run of
    three or more backticks or tildes indented at most three spaces, and only
    a bare run of the same character, at least as long, closes it.
    """
    headings: list[str] = []
    fence: tuple[str, int] | None = None
    for line in text.split("\n"):
        stripped = line.lstrip(" ")
        marker = stripped[:1]
        is_fence_marker = marker in ("`", "~") and len(line) - len(stripped) <= 3
        run = len(stripped) - len(stripped.lstrip(marker)) if is_fence_marker else 0
        rest = stripped[run:]
        if fence is None:
            if run >= 3 and not (marker == "`" and "`" in rest):
                fence = (marker, run)
            elif line.startswith("## "):
                headings.append(line)
        elif marker == fence[0] and run >= fence[1] and not rest.strip():
            fence = None
    return headings


# F1 - a fence that swallows the later sections ------------------------------

TILDE_REPRODUCER = "~~~mermaid\ngraph TD; A-->B\n~~~"


@pytest.mark.parametrize("key", ["solution_structure", "data_storage"])
@pytest.mark.parametrize(
    "value", [TILDE_REPRODUCER, "~~~", "~~~~ wide", "~~~mermaid", "~~~ a ~~~"]
)
def test_prose_that_opens_a_tilde_fence_is_neither_rendered_nor_assembled(key, value):
    intended = output(sections=sections(**{key: value}))
    assert render_refusal(intended) is RENDER_INVALID
    assert refused(lambda: assembled(intended)) is RENDER_INVALID


SWALLOWING_FENCES = {
    "the rendered reproducer": "~~~mermaid<br>graph TD; A--&gt;B<br>~~~",
    "never closed": "~~~mermaid\ngraph TD; A-->B",
    "indented opener": "   ~~~\ngraph TD",
    "closer shorter than opener": "~~~~\ngraph TD\n~~~",
    "closer followed by text": "~~~\ngraph TD\n~~~ end",
    "closer indented as code": "~~~\ngraph TD\n    ~~~",
}


@pytest.mark.parametrize("label", sorted(SWALLOWING_FENCES))
def test_a_handed_in_document_whose_fence_swallows_later_sections_is_refused(label):
    text = rebound(
        assembled(output()).text,
        lambda prefix: edit_markdown(prefix, PLAIN_PROSE, SWALLOWING_FENCES[label]),
    )
    assert len(headings_outside_fences(text)) < len(FROZEN_HEADING_LINES)
    assert document_refusal(text) is RENDER_INVALID


def test_a_fence_closed_only_in_a_later_section_is_refused():
    def across_sections(prefix: str) -> str:
        opened = edit_markdown(prefix, PLAIN_PROSE, "~~~\ngraph TD")
        return edit_markdown(opened, LATER_PROSE, "~~~")

    text = rebound(assembled(output()).text, across_sections)
    assert len(headings_outside_fences(text)) == len(FROZEN_HEADING_LINES) - 2
    assert document_refusal(text) is RENDER_INVALID


@pytest.mark.parametrize(
    "value",
    [
        "~5 ms at p99",
        "~~struck~~ then text",
        "A ~~~ marker mid-sentence",
        "Mentions a ~~~mermaid block inline",
        "~ ~ ~",
    ],
)
def test_tildes_that_open_no_fence_get_no_refusal(value):
    # Under P2 an assumption "~~~x" renders as "- ~~~x", a fence inside a list
    # item, and is refused (section H); it no longer belongs here.
    intended = output(sections=sections(solution_structure=value), assumptions=[value])
    carrier = assembled(intended)
    assert validate_architecture_document(carrier.text, manifest()) == carrier.artifact
    assert headings_outside_fences(carrier.text) == FROZEN_HEADING_LINES


@pytest.mark.parametrize("block", ["~~~mermaid\ngraph TD\n~~~", "~~~\ngraph TD\n~~~~~"])
def test_a_closed_tilde_block_that_swallows_nothing_is_refused_as_a_block(block):
    # Policy-dependent control (spec v0.3 P2): accepted before P2, refused now.
    # The block leaves every heading visible, so this is not the F1 rule.
    text = rebound(
        assembled(output()).text,
        lambda prefix: edit_markdown(prefix, PLAIN_PROSE, block),
    )
    assert headings_outside_fences(text) == FROZEN_HEADING_LINES
    assert document_refusal(text) is RENDER_INVALID


def test_a_normal_document_keeps_sixteen_sections_and_a_separate_envelope():
    text = golden_carrier().text
    assert headings_outside_fences(text) == FROZEN_HEADING_LINES
    assert text.count("```json") == 1
    assert validate_artifact(extract_architecture_envelope(text))


# F2 - the whole table agrees with the envelope ------------------------------

AGREEMENT_ROW = {
    "how_satisfied": "Queue.",
    "constraints": ["No new store.", "Existing runtime."],
    "gaps": ["Load unknown.", "Cost unknown."],
}
MARKDOWN_ONLY_CHANGES = {
    "how_satisfied": ("| Queue. |", "| Polling. |"),
    "constraints": ("| No new store.<br>Existing runtime. |", "| No new store. |"),
    "gaps": ("Load unknown.<br>Cost unknown.", "Load known.<br>Cost unknown."),
    "constraints order": (
        "No new store.<br>Existing runtime.",
        "Existing runtime.<br>No new store.",
    ),
    "gaps order": ("Load unknown.<br>Cost unknown.", "Cost unknown.<br>Load unknown."),
}
ENVELOPE_ONLY_CHANGES = {
    "how_satisfied": ("how_satisfied", "Polling."),
    "constraints": ("constraints", ["No new store."]),
    "gaps": ("gaps", ["Load known.", "Cost unknown."]),
    "constraints order": ("constraints", ["Existing runtime.", "No new store."]),
    "gaps order": ("gaps", ["Cost unknown.", "Load unknown."]),
}


def agreement_carrier():
    rows = [row(FIRST_ID, **AGREEMENT_ROW), row(SECOND_ID)]
    return assembled(output(traceability=rows))


def assert_only_the_representations_disagree(text: str) -> None:
    with pytest.raises(ArchitectureRefused, match="disagrees with the envelope") as (
        caught
    ):
        validate_architecture_document(text, manifest())
    assert caught.value.code is RENDER_INVALID


@pytest.mark.parametrize("label", sorted(MARKDOWN_ONLY_CHANGES))
def test_a_cell_changed_only_in_the_markdown_disagrees_with_the_envelope(label):
    old, new = MARKDOWN_ONLY_CHANGES[label]
    text = rebound(
        agreement_carrier().text, lambda prefix: edit_markdown(prefix, old, new)
    )
    assert_only_the_representations_disagree(text)


@pytest.mark.parametrize("label", sorted(ENVELOPE_ONLY_CHANGES))
def test_a_value_changed_only_in_the_envelope_disagrees_with_the_table(label):
    key, value = ENVELOPE_ONLY_CHANGES[label]
    text = rebound(
        agreement_carrier().text,
        mutate=lambda body: body["traceability"][0].__setitem__(key, value),
    )
    assert_only_the_representations_disagree(text)


AGREEING_ROWS = {
    "empty arrays": {},
    "several elements": AGREEMENT_ROW,
    "pipes and backslashes": {
        "how_satisfied": "a|b\\c",
        "constraints": ["x|y", "\\|"],
        "gaps": ["||", "\\\\"],
    },
    "literal br and line breaks": {
        "how_satisfied": "one<br>two\r\nthree",
        "constraints": ["a<br>b", "c\nd"],
        "gaps": ["e\rf"],
    },
}


@pytest.mark.parametrize("label", sorted(AGREEING_ROWS))
def test_unchanged_values_agree_also_after_known_read_back_changes(label):
    rows = [row(FIRST_ID, **AGREEING_ROWS[label]), row(SECOND_ID)]
    carrier = assembled(output(traceability=rows, assumptions=["Reachable."]))
    assert validate_architecture_document(carrier.text, manifest()) == carrier.artifact
    stored = (
        carrier.text.replace("\n- ", "\n* ")
        .replace("\n\n", "\n\n\n")
        .removesuffix("\n")
    )
    assert stored != carrier.text
    assert validate_architecture_document(stored, manifest()) == carrier.artifact


# F3 - the order of the persisted traceability -------------------------------


def reverse_rows(body: dict) -> None:
    body["traceability"].reverse()


def test_persisted_rows_out_of_requirement_id_order_are_refused_not_sorted():
    carrier = assembled(output())
    text = rebound(carrier.text, mutate=reverse_rows)
    stored = validate_artifact(extract_architecture_envelope(text))
    assert [r["requirement_id"] for r in stored.body["traceability"]] == [
        SECOND_ID,
        FIRST_ID,
    ]
    with pytest.raises(ArchitectureRefused, match="ascending") as caught:
        validate_architecture_document(text, manifest())
    assert caught.value.code is RENDER_INVALID


def test_sorted_rows_and_a_single_row_pass():
    both = assembled(output())
    assert validate_architecture_document(both.text, manifest()) == both.artifact
    only = manifest(FIRST_ID)
    single = assembled(output(traceability=[row(FIRST_ID)]), only)
    assert validate_architecture_document(single.text, only) == single.artifact


def test_the_builder_refuses_unordered_rows_and_leaves_the_callers_data_alone():
    intended = output(traceability=[row(SECOND_ID), row(FIRST_ID)])
    selected = manifest()
    before = copy.deepcopy((intended, selected))
    assert refused(lambda: assembled(intended, selected)) is RENDER_INVALID
    assert (intended, selected) == before


UNORDERED_COVERAGE_DEFECTS = {
    "missing": ([THIRD_ID, FIRST_ID], CODE.TRACEABILITY_MISSING_REQUIREMENT),
    "duplicate": (
        [THIRD_ID, FIRST_ID, SECOND_ID, FIRST_ID],
        CODE.TRACEABILITY_DUPLICATE_REQUIREMENT,
    ),
    "unknown": (
        [THIRD_ID, "SDLC-FR-9999", FIRST_ID, SECOND_ID],
        CODE.TRACEABILITY_UNKNOWN_REQUIREMENT,
    ),
}


@pytest.mark.parametrize("label", sorted(UNORDERED_COVERAGE_DEFECTS))
def test_the_order_rule_does_not_mask_a_coverage_refusal(label):
    ids, code = UNORDERED_COVERAGE_DEFECTS[label]
    selected = manifest(FIRST_ID, SECOND_ID, THIRD_ID)
    rows = [row(FIRST_ID), row(SECOND_ID), row(THIRD_ID)]
    text = rebound(
        assembled(output(traceability=rows), selected).text,
        mutate=lambda body: body.__setitem__("traceability", [row(i) for i in ids]),
    )
    assert document_refusal(text, selected) is code


def test_an_unknown_anchor_in_unordered_rows_keeps_its_own_code():
    def unordered_with_unknown_anchor(body: dict) -> None:
        body["traceability"] = [row(SECOND_ID), row(FIRST_ID, anchors=["tsa-s3"])]

    text = rebound(assembled(output()).text, mutate=unordered_with_unknown_anchor)
    assert document_refusal(text) is CODE.TRACEABILITY_UNKNOWN_ANCHOR


def test_a_shared_anchor_still_passes_the_document_validator():
    rows = [row(FIRST_ID, anchors=["tsa-s03"]), row(SECOND_ID, anchors=["tsa-s03"])]
    carrier = assembled(output(traceability=rows))
    assert validate_architecture_document(carrier.text, manifest()) == carrier.artifact


# F4 - exactly one newline before the envelope -------------------------------


def test_exactly_one_newline_separates_the_last_section_from_the_envelope():
    text = assembled(output()).text
    assert "None identified.\n```json\n" in text
    assert "\n\n```json" not in text


def test_the_golden_carrier_is_the_golden_markdown_then_the_envelope():
    carrier = golden_carrier()
    assert GOLDEN_MARKDOWN.endswith("-->\n\nNone identified.\n")
    payload = extract_architecture_envelope(carrier.text)
    assert carrier.text == (
        f"{GOLDEN_MARKDOWN}```json\n{canonical_artifact_json(payload)}\n```\n"
    )
    assert carrier.text.encode() == golden_carrier().text.encode()
    assert validate_artifact(payload) == carrier.artifact


@pytest.mark.parametrize(
    "read_back",
    [
        lambda text: text.replace("\n```json", "\n\n```json"),
        lambda text: text.replace("\n```json", "\n\n\n```json"),
        lambda text: text.removesuffix("\n"),
    ],
)
def test_read_back_blank_lines_around_the_envelope_stay_acceptable(read_back):
    carrier = golden_carrier()
    stored = read_back(carrier.text)
    assert stored != carrier.text
    assert validate_architecture_document(stored, manifest()) == carrier.artifact


# --------------------------------------------------------------------------
# G. Correction after the re-review of I06 (F5): headings an HTML comment hides
# --------------------------------------------------------------------------

HEADING_FOUR = FROZEN_HEADING_LINES[3]
BEFORE_HEADING_FOUR = f"{PLAIN_PROSE}\n\n{HEADING_FOUR}"
HIDDEN_HEADING_FOUR = f"{PLAIN_PROSE}\n\n<!--\n\n{HEADING_FOUR}"


def with_section_three(replacement: str) -> str:
    """A valid carrier whose section 3 text is replaced, both digests rebound."""
    return rebound(
        assembled(output()).text,
        lambda prefix: edit_markdown(prefix, BEFORE_HEADING_FOUR, replacement),
    )


def test_a_heading_hidden_by_an_html_comment_is_not_counted_as_a_heading():
    selected = manifest()
    before = copy.deepcopy(selected)
    text = with_section_three(HIDDEN_HEADING_FOUR)
    # The comment opens on its own line and closes on the `-->` of heading 4's
    # own anchor: Markdown shows fifteen headings, and heading 4 is not one.
    assert HIDDEN_HEADING_FOUR in text
    assert [line for line in text.split("\n") if line.startswith("## ")] == (
        FROZEN_HEADING_LINES
    )
    kept = str(text)
    with pytest.raises(ArchitectureRefused, match="HTML comment") as caught:
        validate_architecture_document(text, selected)
    assert caught.value.code is RENDER_INVALID
    assert (text, selected) == (kept, before)


HIDING_COMMENTS = {
    "with comment text": f"{PLAIN_PROSE}\n\n<!-- hidden\n\n{HEADING_FOUR}",
    "indented three spaces": f"{PLAIN_PROSE}\n\n   <!--\n\n{HEADING_FOUR}",
    "interrupting the paragraph": f"{PLAIN_PROSE}\n<!--\n{HEADING_FOUR}",
}


@pytest.mark.parametrize("label", sorted(HIDING_COMMENTS))
def test_every_form_of_comment_block_that_hides_a_heading_is_refused(label):
    assert document_refusal(with_section_three(HIDING_COMMENTS[label])) is (
        RENDER_INVALID
    )


def test_the_sixteen_frozen_anchor_comments_stay_valid():
    carrier = assembled(output())
    assert validate_architecture_document(carrier.text, manifest()) == carrier.artifact
    golden = golden_carrier()
    assert validate_architecture_document(golden.text, manifest()) == golden.artifact
    lines = golden.text.split("\n")
    for number, heading in enumerate(FROZEN_HEADING_LINES, start=1):
        assert heading.endswith(f"<!-- anchor: tsa-s{number:02d} -->")
        assert heading in lines


@pytest.mark.parametrize("value", ["<!--", "<!-- note", "a <!-- b --> c", "-->"])
def test_a_raw_comment_marker_in_model_input_is_escaped_and_gets_no_refusal(value):
    intended = output(
        sections=sections(solution_structure=value),
        assumptions=[value],
        traceability=[row(FIRST_ID, how_satisfied=value), row(SECOND_ID)],
    )
    carrier = assembled(intended)
    normative = carrier.text.partition(ENVELOPE_OPENER)[0]
    assert normative.count("<!--") == len(FROZEN_HEADING_LINES)
    assert validate_architecture_document(carrier.text, manifest()) == carrier.artifact


VISIBLE_HEADING_FOUR = {
    "comment closed on its own line": f"{PLAIN_PROSE}\n\n<!-- note -->\n\n{HEADING_FOUR}",
    "comment closed before the heading": f"{PLAIN_PROSE}\n\n<!--\nnote\n-->\n\n{HEADING_FOUR}",
    "marker in mid-sentence": f"See <!-- for details.\n\n{HEADING_FOUR}",
}


@pytest.mark.parametrize("label", sorted(VISIBLE_HEADING_FOUR))
def test_a_comment_marker_that_hides_no_heading_keeps_being_accepted(label):
    # Each of these was accepted before F5 and leaves heading 4 visible.
    text = with_section_three(VISIBLE_HEADING_FOUR[label])
    assert validate_architecture_document(text, manifest())


# Policy-dependent controls (spec v0.3 P2): accepted before P2 because their
# heading stays visible, refused now because the marker sits in a code block.
MARKER_IN_A_CODE_BLOCK = {
    "marker inside a closed tilde block": f"~~~\n<!--\n~~~\n\n{HEADING_FOUR}",
    "marker indented as code": f"{PLAIN_PROSE}\n\n    <!--\n\n{HEADING_FOUR}",
}


@pytest.mark.parametrize("label", sorted(MARKER_IN_A_CODE_BLOCK))
def test_a_comment_marker_inside_a_code_block_gets_the_block_refusal(label):
    text = with_section_three(MARKER_IN_A_CODE_BLOCK[label])
    assert headings_outside_fences(text) == FROZEN_HEADING_LINES
    with pytest.raises(ArchitectureRefused, match="code block|rule X") as caught:
        validate_architecture_document(text, manifest())
    assert caught.value.code is RENDER_INVALID
    assert "HTML comment" not in str(caught.value)


def test_comment_characters_in_the_envelope_do_not_reach_the_structural_analysis():
    question = {"detail": "<!--", "requirement_id": FIRST_ID, "material": True}
    carrier = assembled(output(product_questions=[question]))
    envelope = carrier.text.partition(ENVELOPE_OPENER)[2]
    assert "<!--" in envelope
    assert "-->" not in envelope
    stored = validate_architecture_document(carrier.text, manifest())
    assert stored.body["product_questions"] == [question]


# --------------------------------------------------------------------------
# H. Rule S and rule X in I06 (spec v0.3 8.3, mechanism of spec v0.4)
# --------------------------------------------------------------------------

# Hand-written from the frozen acceptance matrix, as section 3 of an
# otherwise valid handed-in Document: True means I06 refuses.
HANDED_IN_EXAMPLES = {
    "E01": ("```\ngraph TD\n```", True),
    "E02": ("```\ngraph TD", True),
    "E03": ("~~~\ngraph TD\n~~~", True),
    "E04": ("~~~\ngraph TD", True),
    "E05": ("Structure follows.\n~~~mermaid\ngraph TD\n~~~", True),
    "E06": ("Structure follows.\n\n    graph TD", True),
    "E07": ("Structure follows.\n    continued text", False),
    "E08": ("- ~~~\n    ordinary text\n    ~~~", True),
    "E09": ("- ~~~\n  ordinary text", True),
    "E10": ("- ordinary ~~~ marker", False),
    "E11": ("| Requirement ID | Gaps |\n|---|---|\n| SDLC-FR-0007 | ~~~ |", False),
    "E12": ("~~~", True),
    "E13": ("```inline``` then text", True),
}


def handed_in(section_three: str) -> str:
    return with_section_three(f"{section_three}\n\n{HEADING_FOUR}")


@pytest.mark.parametrize(
    "key", sorted(key for key, (_, refused) in HANDED_IN_EXAMPLES.items() if refused)
)
def test_a_handed_in_document_with_a_refused_example_is_render_invalid(key):
    selected = manifest()
    before = copy.deepcopy(selected)
    text = handed_in(HANDED_IN_EXAMPLES[key][0])
    kept = str(text)
    assert document_refusal(text, selected) is RENDER_INVALID
    assert (text, selected) == (kept, before)


@pytest.mark.parametrize(
    "key",
    sorted(key for key, (_, refused) in HANDED_IN_EXAMPLES.items() if not refused),
)
def test_a_handed_in_document_with_a_supported_example_is_accepted(key):
    text = handed_in(HANDED_IN_EXAMPLES[key][0])
    assert validate_architecture_document(text, manifest())


CODE_BLOCKS_RULE_X_MISSES = {
    "E06 indented code": "Structure follows.\n\n    graph TD",
    "E08 closed fence in a list item": "- ~~~\n    ordinary text\n    ~~~",
    "E09 unclosed fence in a list item": "- ~~~\n  ordinary text",
    "fence in a block quote": "> ~~~\n> graph TD\n> ~~~",
    "indented code in a list item": "- item\n\n      graph TD",
}


@pytest.mark.parametrize("label", sorted(CODE_BLOCKS_RULE_X_MISSES))
def test_a_code_block_no_line_prefix_shows_is_refused_as_a_code_block(label):
    text = handed_in(CODE_BLOCKS_RULE_X_MISSES[label])
    assert headings_outside_fences(text) == FROZEN_HEADING_LINES
    with pytest.raises(ArchitectureRefused, match="code block") as caught:
        validate_architecture_document(text, manifest())
    assert caught.value.code is RENDER_INVALID


@pytest.mark.parametrize(
    "value",
    [
        "- ~~~",
        "1. ```",
        "-     indented code",
        "* ~~~mermaid",
    ],
)
def test_prose_that_forms_a_contained_code_block_is_not_rendered(value):
    intended = output(sections=sections(solution_structure=value))
    with pytest.raises(ArchitectureRefused, match="code block") as caught:
        render_architecture(intended, manifest())
    assert caught.value.code is RENDER_INVALID


@pytest.mark.parametrize("value", ["~~~x", "```", "    code"])
def test_a_list_item_that_forms_a_code_block_is_not_rendered(value):
    # Escaping strips the item, so "    code" becomes plain text; the other
    # two open a fence inside the rendered list item.
    intended = output(assumptions=[value])
    if value.strip() == "code":
        assert render_architecture(intended, manifest())
    else:
        assert render_refusal(intended) is RENDER_INVALID


@pytest.mark.parametrize("value", ["~~~ closed ~~~", "~~~~", "   ~~~ x"])
def test_rule_x_refuses_tildes_and_backticks_alike_in_rendered_prose(value):
    for marker in ("~", "`"):
        prose = value.replace("~", marker)
        assert render_refusal(output(sections=sections(solution_structure=prose))) is (
            RENDER_INVALID
        )


QUOTE_PREFIX = "> "


def quoted(depth: int, text: str) -> str:
    return f"{QUOTE_PREFIX * depth}{text}"


@pytest.mark.parametrize(
    ("section_three", "reason"),
    [
        (quoted(25, "~~~\n") + quoted(25, "hidden"), "NESTING_LIMIT"),
        (quoted(19, "plain words"), "NESTING_LIMIT"),
    ],
)
def test_a_document_too_deeply_nested_to_classify_is_refused(section_three, reason):
    text = handed_in(section_three)
    with pytest.raises(ArchitectureRefused) as caught:
        validate_architecture_document(text, manifest())
    assert caught.value.code is RENDER_INVALID
    assert reason in str(caught.value)
    assert "code block was found" not in str(caught.value)


def test_nesting_below_the_threshold_is_classified_and_accepted():
    assert validate_architecture_document(
        handed_in(quoted(18, "plain words")), manifest()
    )


def test_formed_markdown_too_deeply_nested_to_classify_is_not_rendered():
    intended = output(sections=sections(solution_structure="- " * 10 + "deep"))
    with pytest.raises(ArchitectureRefused, match="NESTING_LIMIT") as caught:
        render_architecture(intended, manifest())
    assert caught.value.code is RENDER_INVALID
    assert render_architecture(
        output(sections=sections(solution_structure="- " * 9 + "deep")), manifest()
    )


class BrokenParser:
    def __init__(self, preset: str) -> None:
        self.options = {"maxNesting": 20}

    def parse(self, markdown: str) -> list[object]:
        raise RuntimeError("parser internals with model text")


def test_a_parser_error_is_a_controlled_render_refusal(monkeypatch):
    monkeypatch.setattr("sdlc.tsa_markdown.MarkdownIt", BrokenParser)
    for call in (
        lambda: validate_architecture_document(golden_carrier().text, manifest()),
        lambda: render_architecture(output(), manifest()),
    ):
        with pytest.raises(ArchitectureRefused, match="PARSER_ERROR") as caught:
            call()
        assert caught.value.code is RENDER_INVALID
        assert "parser internals" not in str(caught.value)
        assert caught.value.__cause__ is None


def test_a_parser_error_does_not_hide_an_earlier_defect(monkeypatch):
    unknown = rebound(assembled(output()).text, mutate=name_unselected)
    tampered = golden_carrier().text.replace("Covers checkout.", "Covers more.")
    monkeypatch.setattr("sdlc.tsa_markdown.MarkdownIt", BrokenParser)
    assert document_refusal(unknown) is CODE.TRACEABILITY_UNKNOWN_REQUIREMENT
    with pytest.raises(InvalidTsaArtifact):
        validate_architecture_document(tampered, manifest())
    assert render_refusal(output(traceability=[row(FIRST_ID)])) is (
        CODE.TRACEABILITY_MISSING_REQUIREMENT
    )


def test_the_envelope_fence_is_never_classified_as_normative_markdown():
    carrier = golden_carrier()
    normative = carrier.text.partition(ENVELOPE_OPENER)[0]
    assert classify_code_blocks(carrier.text).outcome is (
        BlockClassification.CODE_BLOCK
    )
    assert classify_code_blocks(normative).outcome is (
        BlockClassification.NO_CODE_BLOCK
    )
    assert validate_architecture_document(carrier.text, manifest()) == carrier.artifact


def test_supported_documents_keep_their_bytes_and_fingerprint():
    rendered = render_architecture(GOLDEN_OUTPUT, manifest())
    assert rendered.markdown == GOLDEN_MARKDOWN
    assert rendered.content_fingerprint == document_fingerprint(GOLDEN_MARKDOWN)
    carrier = golden_carrier()
    assert carrier.text.startswith(GOLDEN_MARKDOWN + ENVELOPE_OPENER)


# The four normative vectors of spec v0.3 8.3.1, in code points.
P1_VECTORS = [
    ([124], [92, 124]),
    ([92], [92, 92]),
    ([92, 124], [92, 92, 92, 124]),
    ([124, 124], [92, 124, 92, 124]),
]


@pytest.mark.parametrize(("source", "expected"), P1_VECTORS)
def test_the_four_pipe_vectors_hold(source, expected):
    escaped = escape_markdown("".join(map(chr, source)))
    assert [ord(character) for character in escaped] == expected


# --------------------------------------------------------------------------
# Spec v0.7 — the traceability table as live Fibery stores it
#
# The intended_output is the first live TSA pilot's (2026-10-17), with its
# workspace ids replaced. `fibery_stored` reproduces that pilot's stored
# Architecture byte for byte from the emitted one; it changes nothing else.
# --------------------------------------------------------------------------

PILOT_ID = "TSAP1-FR-0123"
PILOT_OUTPUT = json.loads(
    (
        Path(__file__).parents[1]
        / "docs/specs/TSA-C01-v0.7-evidence/pilot-intended-output.json"
    ).read_text()
)
STORED_SEPARATOR = "| --- | --- | --- | --- | --- | --- |"


def pilot_manifest() -> dict[str, object]:
    return manifest(PILOT_ID)


def pilot_carrier():
    return build_architecture_carrier(PILOT_OUTPUT, pilot_manifest(), BINDING)


def pilot_stored() -> str:
    return fibery_stored(pilot_carrier().text)


def pilot_row(text: str) -> str:
    (line,) = [line for line in text.split("\n") if line.startswith(f"| {PILOT_ID}")]
    return line


def with_cells(text: str, change) -> str:
    """The stored Document with the pilot row's cells changed by `change`."""
    row = pilot_row(text)
    cells = row[2:-2].split(" | ")
    assert len(cells) == 6 and "\\|" not in row
    change(cells)
    return text.replace(row, f"| {' | '.join(cells)} |")


def normative_part(text: str) -> str:
    return text.partition("```json")[0]


def test_the_canonical_pilot_document_still_validates():
    carrier = pilot_carrier()
    assert TABLE_SEPARATOR in carrier.text and "<br>" in pilot_row(carrier.text)
    assert validate_architecture_document(carrier.text, pilot_manifest()) == (
        carrier.artifact
    )


def test_the_stored_pilot_differs_only_by_the_observed_fibery_rules():
    emitted, stored = pilot_carrier().text, pilot_stored()
    assert stored != emitted
    assert STORED_SEPARATOR in stored and TABLE_SEPARATOR not in stored
    assert "<br>" not in pilot_row(stored)
    assert pilot_row(stored) == " ".join(pilot_row(emitted).split("<br>"))
    assert "\n* " in stored and "\n- " not in normative_part(stored)
    assert "\n\n```json" in stored and not stored.endswith("\n")
    assert extract_architecture_envelope(stored) == extract_architecture_envelope(
        emitted
    )


def test_the_stored_pilot_validates_to_the_emitted_artifact_and_fingerprint():
    carrier, stored = pilot_carrier(), pilot_stored()
    assert document_fingerprint(normative_part(stored)) != carrier.content_fingerprint

    artifact = validate_architecture_document(stored, pilot_manifest())

    assert artifact == carrier.artifact
    assert artifact.body["content_fingerprint"] == carrier.content_fingerprint


def test_reading_the_same_stored_document_twice_gives_the_same_result():
    stored = pilot_stored()
    first = validate_architecture_document(stored, pilot_manifest())
    assert validate_architecture_document(stored, pilot_manifest()) == first


def test_canonical_emission_keeps_the_frozen_table_form():
    rendered = render_architecture(PILOT_OUTPUT, pilot_manifest())
    body = section_bodies(rendered.markdown)[2]
    assert body[1] == TABLE_SEPARATOR
    assert body[2].count("<br>") == 8
    assert rendered.content_fingerprint == document_fingerprint(rendered.markdown)


def set_cell(column: int, value: str):
    return lambda cells: cells.__setitem__(column, value)


def edit_cell(column: int, old: str, new: str):
    def change(cells: list[str]) -> None:
        assert cells[column].count(old) == 1, old
        cells[column] = cells[column].replace(old, new)

    return change


STORED_TABLE_DEFECTS = {
    "another requirement id": lambda t: with_cells(t, set_cell(0, "TSAP1-FR-0124")),
    "another source": lambda t: with_cells(t, edit_cell(1, "@ ", "@ 0")),
    "another anchor": lambda t: with_cells(t, edit_cell(2, "tsa-s13", "tsa-s12")),
    "anchor dropped": lambda t: with_cells(t, edit_cell(2, " tsa-s13", "")),
    "how satisfied": lambda t: with_cells(t, edit_cell(3, "only GET", "GET")),
    "constraint": lambda t: with_cells(t, edit_cell(4, "1 to 32", "1 to 33")),
    "gap": lambda t: with_cells(t, edit_cell(5, "not defined", "defined")),
    "extra column": lambda t: with_cells(t, lambda cells: cells.append("x")),
    "missing column": lambda t: with_cells(t, lambda cells: cells.pop()),
    "unescaped pipe": lambda t: with_cells(t, edit_cell(3, "only GET", "only | GET")),
    "row repeated": lambda t: t.replace(
        pilot_row(t), f"{pilot_row(t)}\n{pilot_row(t)}"
    ),
    "row missing": lambda t: t.replace(f"{pilot_row(t)}\n", ""),
    "header renamed": lambda t: edit_markdown(t, "| Gaps |", "| Gap |"),
    "canonical separator": lambda t: edit_markdown(
        t, STORED_SEPARATOR, TABLE_SEPARATOR
    ),
    "aligned separator": lambda t: edit_markdown(
        t, STORED_SEPARATOR, "| :--- | --- | --- | --- | --- | --- |"
    ),
    "half-spaced separator": lambda t: edit_markdown(
        t, STORED_SEPARATOR, "|--- | --- | --- | --- | --- | --- |"
    ),
    "longer separator": lambda t: edit_markdown(
        t, STORED_SEPARATOR, "| ---- | --- | --- | --- | --- | --- |"
    ),
    "five-column separator": lambda t: edit_markdown(
        t, STORED_SEPARATOR, "| --- | --- | --- | --- | --- |"
    ),
    "line break kept": lambda t: t.replace(
        pilot_row(t), pilot_row(pilot_carrier().text)
    ),
    "line break as two spaces": lambda t: with_cells(
        t, edit_cell(2, "tsa-s03 tsa-s04", "tsa-s03  tsa-s04")
    ),
    "line break as self-closing tag": lambda t: with_cells(
        t, edit_cell(2, "tsa-s03 tsa-s04", "tsa-s03<br/>tsa-s04")
    ),
    "line break dropped": lambda t: with_cells(
        t, edit_cell(2, "tsa-s03 tsa-s04", "tsa-s03tsa-s04")
    ),
    "line break as comma": lambda t: with_cells(
        t, edit_cell(2, "tsa-s03 tsa-s04", "tsa-s03, tsa-s04")
    ),
    "line break as a new line": lambda t: with_cells(
        t, edit_cell(2, "tsa-s03 tsa-s04", "tsa-s03\ntsa-s04")
    ),
    "padded cell": lambda t: with_cells(t, set_cell(0, f" {PILOT_ID}")),
}


@pytest.mark.parametrize("label", sorted(STORED_TABLE_DEFECTS))
def test_a_stored_table_that_is_not_exactly_the_fibery_form_is_refused(label):
    text = STORED_TABLE_DEFECTS[label](pilot_stored())
    assert text != pilot_stored()
    assert validate_artifact(extract_architecture_envelope(text))
    assert document_refusal(text, pilot_manifest()) is CODE.ARCHITECTURE_RENDER_INVALID


def test_edited_prose_beside_a_stored_table_is_caught_by_the_fingerprint():
    text = edit_markdown(
        pilot_stored(), "A single stateless service process", "A stateful process"
    )
    with pytest.raises(InvalidTsaArtifact, match="content_fingerprint"):
        validate_architecture_document(text, pilot_manifest())


def test_an_edited_generated_list_beside_a_stored_table_is_render_invalid():
    text = edit_markdown(
        pilot_stored(), "* Request headers and any", "* Request headers and no"
    )
    assert document_refusal(text, pilot_manifest()) is CODE.ARCHITECTURE_RENDER_INVALID


def test_a_stored_document_whose_envelope_was_edited_without_resealing_is_refused():
    text = pilot_stored().replace('"tsa-s13"', '"tsa-s12"', 1)
    with pytest.raises(InvalidTsaArtifact):
        validate_architecture_document(text, pilot_manifest())


def test_a_resealed_wrong_fingerprint_is_refused_for_a_stored_table():
    text = reseal(
        pilot_stored(), lambda body: body.__setitem__("content_fingerprint", "0" * 64)
    )
    assert validate_artifact(extract_architecture_envelope(text))
    with pytest.raises(InvalidTsaArtifact, match="content_fingerprint"):
        validate_architecture_document(text, pilot_manifest())


def test_regrouped_array_elements_that_display_the_same_are_still_refused():
    """A valid digest and an equal display never prove the canonical content."""

    def merge_constraints(body: dict) -> None:
        row = body["traceability"][0]
        row["constraints"] = [" ".join(row["constraints"])]

    text = reseal(pilot_stored(), merge_constraints)
    assert pilot_row(text) == pilot_row(pilot_stored()), "the display is unchanged"
    with pytest.raises(InvalidTsaArtifact, match="content_fingerprint"):
        validate_architecture_document(text, pilot_manifest())


def test_an_envelope_row_the_stored_table_does_not_show_is_render_invalid():
    def other_text(body: dict) -> None:
        body["traceability"][0]["how_satisfied"] = "Something else."

    text = reseal(pilot_stored(), other_text)
    assert document_refusal(text, pilot_manifest()) is CODE.ARCHITECTURE_RENDER_INVALID


def test_a_stored_table_bound_to_another_manifest_is_refused():
    other = manifest(PILOT_ID, fingerprints={PILOT_ID: "f" * 64})
    with pytest.raises(InvalidTsaArtifact, match="another Input Manifest"):
        validate_architecture_document(pilot_stored(), other)


def test_stored_envelope_rows_out_of_order_are_render_invalid():
    def reverse(body: dict) -> None:
        body["traceability"].reverse()

    text = reseal(fibery_stored(golden_carrier().text), reverse)
    assert document_refusal(text) is CODE.ARCHITECTURE_RENDER_INVALID


@pytest.mark.parametrize("label", sorted(ENVELOPE_COVERAGE_DEFECTS))
def test_stored_envelope_traceability_keeps_the_coverage_rules(label):
    mutate, code = ENVELOPE_COVERAGE_DEFECTS[label]
    text = reseal(fibery_stored(golden_carrier().text), mutate)
    assert document_refusal(text) is code


EVIDENCE = Path(__file__).parents[1] / "docs/specs/TSA-C01-v0.7-evidence"


def test_the_fake_reproduces_the_live_stored_pilot_byte_for_byte():
    """Fake versus live: both pilot Documents, sanitized identically."""
    emitted = (EVIDENCE / "pilot-architecture-emitted.md").read_text()
    stored = (EVIDENCE / "pilot-architecture-stored.md").read_text()
    assert stored != emitted
    assert fibery_stored(emitted) == stored


def test_cells_fibery_keeps_verbatim_are_accepted_only_as_the_canonical_text():
    """Empty and escaped cells take no v0.7 transformation; they stay exact."""
    stored = fibery_stored(golden_carrier().text)
    assert "|  |" in stored and "Cost \\| unknown" in stored
    assert validate_architecture_document(stored, manifest()) == (
        golden_carrier().artifact
    )
    unescaped = edit_markdown(stored, "Cost \\| unknown |", "Cost | unknown |")
    assert document_refusal(unescaped) is CODE.ARCHITECTURE_RENDER_INVALID


def test_trailing_whitespace_on_a_stored_table_line_is_not_content():
    text = pilot_stored()
    padded = text.replace(STORED_SEPARATOR, STORED_SEPARATOR + "  ", 1)
    assert validate_architecture_document(padded, pilot_manifest()) == (
        pilot_carrier().artifact
    )


def test_an_extra_line_inside_a_stored_traceability_section_is_render_invalid():
    text = pilot_stored()
    extra = text.replace(
        f"{pilot_row(text)}\n", f"{pilot_row(text)}\nAn added sentence.\n", 1
    )
    assert document_refusal(extra, pilot_manifest()) is CODE.ARCHITECTURE_RENDER_INVALID


# --------------------------------------------------------------------------
# Spec v0.8 — escaped `<` and `>` of a prose section as live Fibery stores them
#
# The intended_output is the second live TSA pilot's (2026-10-18), with its
# workspace ids and tree fingerprints replaced. Its section 3 holds the model
# text `<result>`, which 8.3.1 emits as `&lt;result&gt;` and Fibery stored as
# `<result>`.
# --------------------------------------------------------------------------

PILOT2_EVIDENCE = Path(__file__).parents[1] / "docs/specs/TSA-C01-v0.8-evidence"
PILOT2_IDS = ("TSAP1-FR-0123", "TSAP1-FR-0124")
PILOT2_FINGERPRINTS = {"TSAP1-FR-0123": "0" * 64, "TSAP1-FR-0124": "1" * 64}
PILOT2_OUTPUT = json.loads(
    (PILOT2_EVIDENCE / "pilot2-intended-output.json").read_text()
)
EMITTED_ENTITY = '{"uppercase": &lt;result&gt;}'
STORED_ENTITY = '{"uppercase": <result>}'


def pilot2_manifest() -> dict[str, object]:
    return manifest(*PILOT2_IDS, fingerprints=PILOT2_FINGERPRINTS)


def pilot2_carrier():
    return build_architecture_carrier(PILOT2_OUTPUT, pilot2_manifest(), BINDING)


def pilot2_stored() -> str:
    return fibery_stored(pilot2_carrier().text)


def pilot2_refusal(text: str) -> ArchitectureResultCode:
    return document_refusal(text, pilot2_manifest())


def entity_carrier(**section_text: str):
    """A carrier whose prose sections carry the given model text."""
    return assembled(output(sections=sections(**section_text)))


def test_the_second_pilot_is_emitted_byte_identically_with_its_entity():
    rendered = render_architecture(PILOT2_OUTPUT, pilot2_manifest())
    emitted = (PILOT2_EVIDENCE / "pilot2-architecture-emitted.md").read_text()
    assert "<result>" in PILOT2_OUTPUT["sections"]["solution_structure"]
    assert rendered.markdown == normative_part(emitted)
    assert EMITTED_ENTITY in rendered.markdown and "<result>" not in rendered.markdown
    assert rendered.content_fingerprint == document_fingerprint(rendered.markdown)
    assert render_architecture(PILOT2_OUTPUT, pilot2_manifest()) == rendered


def test_the_fake_reproduces_the_second_live_stored_pilot_byte_for_byte():
    """Fake versus live: both second-pilot Documents, sanitized identically."""
    emitted = (PILOT2_EVIDENCE / "pilot2-architecture-emitted.md").read_text()
    stored = (PILOT2_EVIDENCE / "pilot2-architecture-stored.md").read_text()
    differing = [
        (old, new)
        for old, new in zip(emitted.split("\n"), stored.split("\n"), strict=False)
        if old != new and EMITTED_ENTITY in old
    ]
    assert [new for _, new in differing] == [
        differing[0][0].replace(EMITTED_ENTITY, STORED_ENTITY)
    ]
    assert fibery_stored(emitted) == stored


def test_the_stored_second_pilot_validates_to_the_emitted_artifact_and_fingerprint():
    carrier, stored = pilot2_carrier(), pilot2_stored()
    assert STORED_ENTITY in stored and "&lt;" not in normative_part(stored)
    assert document_fingerprint(normative_part(stored)) != carrier.content_fingerprint

    artifact = validate_architecture_document(stored, pilot2_manifest())

    assert artifact == carrier.artifact
    assert artifact.body["content_fingerprint"] == carrier.content_fingerprint


def test_without_the_v08_rule_the_second_pilot_is_the_live_refusal(monkeypatch):
    monkeypatch.setattr(
        tsa_architecture, "_with_canonical_prose", lambda normative, _: normative
    )
    with pytest.raises(InvalidTsaArtifact) as caught:
        validate_architecture_document(pilot2_stored(), pilot2_manifest())
    assert str(caught.value) == (
        "The envelope's content_fingerprint is not the fingerprint of the "
        "sixteen sections it accompanies."
    )


def test_the_first_pilot_and_canonical_documents_are_read_as_before():
    for carrier, selected in (
        (pilot_carrier(), pilot_manifest()),
        (pilot2_carrier(), pilot2_manifest()),
        (golden_carrier(), manifest()),
    ):
        assert validate_architecture_document(carrier.text, selected) == (
            carrier.artifact
        )
    assert validate_architecture_document(pilot_stored(), pilot_manifest()) == (
        pilot_carrier().artifact
    )


def test_every_decoded_character_of_a_line_is_re_escaped_and_br_is_kept():
    carrier = entity_carrier(solution_structure="a <b> c > d\n\ne < f")
    stored = fibery_stored(carrier.text)
    assert "a <b> c > d<br><br>e < f" in stored
    assert validate_architecture_document(stored, manifest()) == carrier.artifact


def with_table_of(text: str, source: str) -> str:
    """`text` with every table line replaced by the same line of `source`."""
    table = [line for line in source.split("\n") if line.startswith("|")]
    lines = text.split("\n")
    positions = [index for index, line in enumerate(lines) if line.startswith("|")]
    assert len(positions) == len(table)
    for index, line in zip(positions, table, strict=True):
        lines[index] = line
    return "\n".join(lines)


PILOT2_DEFECTS = {
    "altered literal tag content": (
        lambda t: edit_markdown(t, STORED_ENTITY, '{"uppercase": <value>}'),
        "ARTIFACT_MALFORMED",
    ),
    "tag removed": (
        lambda t: edit_markdown(t, STORED_ENTITY, '{"uppercase": }'),
        "ARTIFACT_MALFORMED",
    ),
    "injected HTML tag": (
        lambda t: edit_markdown(
            t, "one small, stateless", "one <b>small</b>, stateless"
        ),
        "ARTIFACT_MALFORMED",
    ),
    "injected script": (
        lambda t: edit_markdown(t, STORED_ENTITY, STORED_ENTITY + "<script>x</script>"),
        "ARTIFACT_MALFORMED",
    ),
    "altered prose": (
        lambda t: edit_markdown(t, "one small, stateless", "one large, stateful"),
        "ARTIFACT_MALFORMED",
    ),
    "entity kept beside a decoded one": (
        lambda t: edit_markdown(
            t, "one small, stateless", "one &lt;small&gt;, stateless"
        ),
        "ARCHITECTURE_RENDER_INVALID",
    ),
    "angle bracket backslash-escaped": (
        lambda t: edit_markdown(t, STORED_ENTITY, '{"uppercase": \\<result\\>}'),
        "ARTIFACT_MALFORMED",
    ),
    "angle bracket double-escaped": (
        lambda t: edit_markdown(
            t, STORED_ENTITY, '{"uppercase": &amp;lt;result&amp;gt;}'
        ),
        "ARTIFACT_MALFORMED",
    ),
    "canonical table beside decoded prose": (
        lambda t: with_table_of(t, pilot2_carrier().text),
        "ARTIFACT_MALFORMED",
    ),
    "canonical separator beside decoded prose": (
        lambda t: edit_markdown(t, STORED_SEPARATOR, TABLE_SEPARATOR),
        "ARCHITECTURE_RENDER_INVALID",
    ),
    "altered table cell": (
        lambda t: edit_markdown(t, "@ 000000000000", "@ 000000000001"),
        "ARCHITECTURE_RENDER_INVALID",
    ),
    "altered generated list": (
        lambda t: edit_markdown(
            t, "* This is a greenfield", "* This is not a greenfield"
        ),
        "ARCHITECTURE_RENDER_INVALID",
    ),
}


def refusal_code(text: str, selected) -> str:
    try:
        validate_architecture_document(text, selected)
    except ArchitectureRefused as error:
        return str(error.code)
    except InvalidTsaArtifact as error:
        return str(error.code)
    raise AssertionError("accepted")


@pytest.mark.parametrize("label", sorted(PILOT2_DEFECTS))
def test_a_changed_second_pilot_document_is_refused(label):
    change, code = PILOT2_DEFECTS[label]
    text = change(pilot2_stored())
    assert text != pilot2_stored()
    assert validate_artifact(extract_architecture_envelope(text))
    assert refusal_code(text, pilot2_manifest()) == code


def test_a_resealed_wrong_fingerprint_is_refused_for_decoded_prose():
    text = reseal(
        pilot2_stored(), lambda body: body.__setitem__("content_fingerprint", "0" * 64)
    )
    with pytest.raises(InvalidTsaArtifact, match="content_fingerprint"):
        validate_architecture_document(text, pilot2_manifest())


def test_a_resealed_traceability_change_is_refused_for_decoded_prose():
    def other(body: dict) -> None:
        body["traceability"][1]["gaps"] = []

    assert pilot2_refusal(reseal(pilot2_stored(), other)) is (
        CODE.ARCHITECTURE_RENDER_INVALID
    )


def test_an_unsealed_envelope_edit_is_refused_for_decoded_prose():
    text = pilot2_stored().replace('"tsa-s13"', '"tsa-s12"', 1)
    with pytest.raises(InvalidTsaArtifact):
        validate_architecture_document(text, pilot2_manifest())


def test_decoded_prose_bound_to_another_manifest_is_refused():
    other = manifest(
        *PILOT2_IDS, fingerprints={**PILOT2_FINGERPRINTS, PILOT2_IDS[0]: "f" * 64}
    )
    with pytest.raises(InvalidTsaArtifact, match="another Input Manifest"):
        validate_architecture_document(pilot2_stored(), other)


def test_another_decoded_entity_is_never_accepted():
    """Only `&lt;` and `&gt;`: an `&amp;` Fibery decoded too is a change."""
    carrier = entity_carrier(solution_structure="a &amp; b <c>")
    stored = fibery_stored(carrier.text)
    assert validate_architecture_document(stored, manifest()) == carrier.artifact
    decoded = edit_markdown(stored, "a &amp; b", "a & b")
    with pytest.raises(InvalidTsaArtifact, match="content_fingerprint"):
        validate_architecture_document(decoded, manifest())


def test_model_text_holding_a_br_tag_is_refused_once_decoded():
    """A decoded `<br>` cannot be told from the renderer's; it is not guessed."""
    carrier = entity_carrier(solution_structure="a <br> b")
    stored = fibery_stored(carrier.text)
    assert "a <br> b" in stored
    with pytest.raises(InvalidTsaArtifact, match="content_fingerprint"):
        validate_architecture_document(stored, manifest())


@pytest.mark.parametrize(
    "value",
    ["<div>block</div>", "> quoted text", "<!-- hidden -->", "<script>x()</script>"],
    ids=["html block", "block quote", "comment block", "script block"],
)
def test_a_decoded_character_that_opens_a_block_is_refused(value):
    carrier = entity_carrier(failure_recovery=value)
    stored = fibery_stored(carrier.text)
    assert value in stored
    assert document_refusal(stored) is CODE.ARCHITECTURE_RENDER_INVALID


@pytest.mark.parametrize("where", ["assumptions", "traceability"])
def test_a_decoded_entity_outside_prose_stays_unaccepted(where):
    """Seen in a prose paragraph only; a list item or cell keeps v0.7's rule."""
    intended = output(sections=sections(solution_structure="see <x>"))
    if where == "assumptions":
        intended["assumptions"] = ["an <item>"]
    else:
        intended["traceability"] = [
            row(FIRST_ID, how_satisfied="a <cell>"),
            row(SECOND_ID),
        ]
    stored = fibery_stored(assembled(intended).text)
    entity = "an &lt;item&gt;" if where == "assumptions" else "a &lt;cell&gt;"
    decoded = edit_markdown(
        stored, entity, entity.replace("&lt;", "<").replace("&gt;", ">")
    )
    assert document_refusal(decoded) is CODE.ARCHITECTURE_RENDER_INVALID


def test_a_code_block_is_refused_beside_decoded_prose_with_a_true_fingerprint():
    """Rule S still runs: a matching fingerprint never admits a code block."""
    text = rebound(
        entity_carrier(solution_structure="see <x>").text,
        edit=lambda prefix: prefix.replace(
            "see &lt;x&gt;", "see &lt;x&gt;\n\n    indented code", 1
        ),
    )
    stored = fibery_stored(text)
    assert "see <x>" in stored and "\n    indented code" in stored
    assert document_refusal(stored) is CODE.ARCHITECTURE_RENDER_INVALID
