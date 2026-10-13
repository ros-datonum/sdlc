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

import pytest

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
    compute_artifact_digest,
    extract_architecture_envelope,
    extract_artifact_payload,
    manifest_digest,
    requirement_input_digest,
    validate_artifact,
)
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
            "requirement_id": SECOND_ID,
            "anchors": ["tsa-s03"],
            "how_satisfied": "Structure.",
            "constraints": [],
            "gaps": ["Load unknown.", "Cost | unknown"],
        },
        {
            "requirement_id": FIRST_ID,
            "anchors": ["tsa-s03", "tsa-s05"],
            "how_satisfied": "API\r\nplus worker.",
            "constraints": ["Existing runtime.", "No new store."],
            "gaps": [],
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
    assert intended["traceability"][0]["requirement_id"] == SECOND_ID


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
    assert prefix == GOLDEN_MARKDOWN + "\n"
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
