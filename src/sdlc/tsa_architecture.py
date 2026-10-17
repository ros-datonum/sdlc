"""TSA-C01 I06 — the applied Architecture Document: template, render, validate.

After the first Architect output is applied, the Architecture Document is the
sixteen frozen headings of contract 8 followed by one trailing JSON envelope
(implementation spec 4.1, 4.6.1, 8). This module owns three pure calculations
and nothing else:

- `render_architecture`: the replay identity of 4.6.3.1,
  `render(intended_output, manifest_body) -> Markdown -> content_fingerprint`;
- `build_architecture_carrier`: the local assembly of the post-apply carrier
  from that Markdown and an explicitly supplied binding;
- `validate_architecture_document`: structural validation of a post-apply
  Document somebody else hands in.

Nothing here reads or writes a workspace, calls a model, reads a clock or keeps
state. Persisting and applying are I07; the pre-apply bootstrap carrier is I04
and never passes through this module (spec 4.1.1).

A successful validation is structural agreement only. It is not evidence that
the architecture satisfies a Requirement, and it is not human approval
(contract 8.1, spec 8.2).
"""

from __future__ import annotations

import copy
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from sdlc.normative_tree import document_fingerprint
from sdlc.tsa_artifacts import (
    ARCHITECTURE,
    FENCE_MARKER,
    JSON_FENCE_OPENER,
    SCHEMA_VERSION,
    ArtifactIdentity,
    InvalidTsaArtifact,
    TsaArtifact,
    canonical_artifact_json,
    extract_architecture_envelope,
    manifest_digest,
    sealed_artifact,
    validate_artifact,
    validate_intended_output,
    validate_manifest_body,
)
from sdlc.tsa_markdown import (
    BlockClassification,
    classify_code_blocks,
    has_fence_marker_line,
)

__all__ = [
    "ANCHOR_PATTERN",
    "HEADINGS",
    "ArchitectureBinding",
    "ArchitectureCarrier",
    "ArchitectureHeading",
    "ArchitectureRefused",
    "ArchitectureResultCode",
    "RenderedArchitecture",
    "build_architecture_carrier",
    "escape_markdown",
    "render_architecture",
    "validate_architecture_document",
]


class ArchitectureResultCode(StrEnum):
    """The frozen result codes this module's validators own (spec 13.8)."""

    ARCHITECTURE_RENDER_INVALID = "ARCHITECTURE_RENDER_INVALID"
    SECTION_MANDATORY_EMPTY = "SECTION_MANDATORY_EMPTY"
    TRACEABILITY_MISSING_REQUIREMENT = "TRACEABILITY_MISSING_REQUIREMENT"
    TRACEABILITY_UNKNOWN_REQUIREMENT = "TRACEABILITY_UNKNOWN_REQUIREMENT"
    TRACEABILITY_DUPLICATE_REQUIREMENT = "TRACEABILITY_DUPLICATE_REQUIREMENT"
    TRACEABILITY_UNKNOWN_ANCHOR = "TRACEABILITY_UNKNOWN_ANCHOR"
    TRACEABILITY_DUPLICATE_ANCHOR = "TRACEABILITY_DUPLICATE_ANCHOR"


class ArchitectureRefused(Exception):
    """A render or traceability rule of spec 8 refuses, with its frozen code.

    Carrier, schema, digest and lineage refusals are not this exception: they
    stay I01's `InvalidTsaArtifact` and keep the code that carries.
    """

    def __init__(self, code: ArchitectureResultCode, message: str) -> None:
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------
# The frozen template (contract 8, spec 8.1, 8.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArchitectureHeading:
    """One of the sixteen frozen headings and where its content comes from.

    `section_key` names the Architect section a prose heading renders;
    `generated_from` names the `intended_output` array a generated heading
    renders. Exactly one of the two is set.
    """

    number: int
    title: str
    is_mandatory: bool
    section_key: str | None = None
    generated_from: str | None = None

    @property
    def anchor(self) -> str:
        return ANCHOR_TEMPLATE.format(number=self.number)

    @property
    def line(self) -> str:
        return HEADING_TEMPLATE.format(
            number=self.number, title=self.title, anchor=self.anchor
        )


ANCHOR_TEMPLATE = "tsa-s{number:02d}"
ANCHOR_PATTERN = re.compile(r"tsa-s(0[1-9]|1[0-6])")
HEADING_TEMPLATE = "## {number}. {title} <!-- anchor: {anchor} -->"

HEADINGS = (
    ArchitectureHeading(1, "Scope & Inputs", True, "scope_and_inputs"),
    ArchitectureHeading(
        2, "Requirement Traceability", True, generated_from="traceability"
    ),
    ArchitectureHeading(3, "Solution Structure", True, "solution_structure"),
    ArchitectureHeading(
        4, "Components & Responsibilities", True, "components_and_responsibilities"
    ),
    ArchitectureHeading(
        5, "Interfaces & Data Flows", True, "interfaces_and_data_flows"
    ),
    ArchitectureHeading(6, "Data / Storage", False, "data_storage"),
    ArchitectureHeading(7, "External Integrations", False, "external_integrations"),
    ArchitectureHeading(
        8, "Security / Authentication / Authorization", False, "security_authn_authz"
    ),
    ArchitectureHeading(
        9, "Deployment / Runtime Model", False, "deployment_runtime_model"
    ),
    ArchitectureHeading(10, "Failure / Recovery", False, "failure_recovery"),
    ArchitectureHeading(11, "Observability", False, "observability"),
    ArchitectureHeading(12, "Migration Implications", False, "migration_implications"),
    ArchitectureHeading(
        13, "Architecture Decisions / Trade-offs", True, "architecture_decisions"
    ),
    ArchitectureHeading(14, "Assumptions", False, generated_from="assumptions"),
    ArchitectureHeading(15, "Risks", False, generated_from="risks"),
    ArchitectureHeading(
        16,
        "Open Architecture Questions",
        False,
        generated_from="open_architecture_questions",
    ),
)

TRACEABILITY_SOURCE = "traceability"
RISKS_SOURCE = "risks"
PRODUCT_QUESTIONS_KEY = "product_questions"

TABLE_HEADER = (
    "| Requirement ID | Source | Architecture anchors | How satisfied "
    "| Constraints honoured | Gaps |"
)
TABLE_SEPARATOR = "|---|---|---|---|---|---|"
#: Spec v0.7: the canonical separator exactly as Fibery stores it (live
#: TSA pilot, 2026-10-17). The only other separator a read-back may carry.
FIBERY_TABLE_SEPARATOR = "| --- | --- | --- | --- | --- | --- |"
#: Spec v0.7: Fibery stores each literal `<br>` of a table row as one space.
FIBERY_TABLE_LINE_BREAK = " "
TABLE_COLUMN_COUNT = 6
CELL_DELIMITER = "|"
ESCAPE_CHARACTER = "\\"
SOURCE_TEMPLATE = "{requirement_id} @ {fingerprint_prefix}"
SOURCE_FINGERPRINT_LENGTH = 12

LIST_ITEM_TEMPLATE = "- {item}"
RISK_ITEM_TEMPLATE = "- {detail} — Impact: {impact}"
NONE_IDENTIFIED = "None identified."
CANONICAL_BULLET = "- "
FIBERY_BULLETS = ("* ", "+ ")

#: The Content-or-N/A form of 8.1, on one line.
NOT_APPLICABLE_FORM = re.compile(r"N/A — \S[^\r\n]*")
#: A value that presents itself as N/A at all, conforming or not.
NOT_APPLICABLE_CLAIM = re.compile(r"N/A(?!\w)")

LINE_BREAK = "<br>"
#: 8.3.1. One table, applied once to the original text. The pipe replacement
#: is backslash + pipe. The frozen cell reads ambiguously in Markdown; which
#: reading is normative is an open question that this module does not settle.
ESCAPE_REPLACEMENTS = {
    "\\": "\\\\",
    "|": "\\|",
    "\r\n": LINE_BREAK,
    "\r": LINE_BREAK,
    "\n": LINE_BREAK,
    "<": "&lt;",
    ">": "&gt;",
}
ESCAPED_SOURCE = re.compile(r"\r\n|[\\|\r\n<>]")

HEADING_LIKE = re.compile(r" {0,3}#{1,6}(?:\s|$)")
#: A tilde fence: its opener may carry any text after the run, its closer none.
TILDE_FENCE = re.compile(r" {0,3}(~{3,})(.*)")
#: A line that opens an HTML comment block; the frozen anchor comments follow
#: their heading on its own line and never open one.
COMMENT_BLOCK_OPENER = re.compile(r" {0,3}<!--")
COMMENT_CLOSER = "-->"


def escape_markdown(value: str) -> str:
    """The one escaping function of spec 8.3.1.

    Leading and trailing whitespace is stripped, then every source character
    is mapped once. `re.sub` walks the original text and never re-scans a
    replacement, so the `<` and `>` of a `<br>` it emits stay as they are, and
    `\\r\\n` is one source sequence yielding one `<br>`.
    """
    return ESCAPED_SOURCE.sub(
        lambda found: ESCAPE_REPLACEMENTS[found.group()], value.strip()
    )


def _escaped_cell(items: Sequence[str]) -> str:
    """An array-valued cell: each element escaped alone, joined by `<br>`."""
    return LINE_BREAK.join(escape_markdown(item) for item in items)


# ---------------------------------------------------------------------------
# Input rules a validator can decide (spec 8.1, 8.2)
# ---------------------------------------------------------------------------


def _refuse(code: ArchitectureResultCode, message: str) -> ArchitectureRefused:
    return ArchitectureRefused(code, message)


def _require_section_values(sections: dict[str, str]) -> None:
    """A Mandatory section may not be N/A; an N/A must use the frozen form."""
    for heading in HEADINGS:
        if heading.section_key is None:
            continue
        _require_not_applicable_rule(heading, sections[heading.section_key].strip())


def _require_not_applicable_rule(heading: ArchitectureHeading, text: str) -> None:
    if not NOT_APPLICABLE_CLAIM.match(text):
        return
    if heading.is_mandatory:
        raise _refuse(
            ArchitectureResultCode.SECTION_MANDATORY_EMPTY,
            f"Section {heading.number} ({heading.title}) is Mandatory and holds "
            "an N/A form; N/A is not an admissible value there.",
        )
    if not NOT_APPLICABLE_FORM.fullmatch(text):
        raise _refuse(
            ArchitectureResultCode.ARCHITECTURE_RENDER_INVALID,
            f"Section {heading.number} ({heading.title}) presents itself as N/A "
            "but is not exactly 'N/A — <reason on one line>'.",
        )


def _selected_requirement_ids(manifest_body: dict[str, object]) -> list[str]:
    return [row["requirement_id"] for row in manifest_body["requirements"]]


def _require_exact_coverage(
    rows: Sequence[dict[str, object]], manifest_body: dict[str, object]
) -> None:
    """Every selected Requirement exactly once, on frozen anchors (spec 8.2)."""
    selected = _selected_requirement_ids(manifest_body)
    covered: set[str] = set()
    for row in rows:
        requirement_id = row["requirement_id"]
        if requirement_id not in selected:
            raise _refuse(
                ArchitectureResultCode.TRACEABILITY_UNKNOWN_REQUIREMENT,
                f"Traceability names {requirement_id!r}, which the Input "
                "Manifest did not select.",
            )
        if requirement_id in covered:
            raise _refuse(
                ArchitectureResultCode.TRACEABILITY_DUPLICATE_REQUIREMENT,
                f"Traceability covers {requirement_id!r} in more than one row.",
            )
        covered.add(requirement_id)
        _require_row_anchors(requirement_id, row["anchors"])
    missing = [item for item in selected if item not in covered]
    if missing:
        raise _refuse(
            ArchitectureResultCode.TRACEABILITY_MISSING_REQUIREMENT,
            f"Traceability has no row for selected Requirement(s) {missing}. An "
            "N/A section never removes a Requirement from coverage.",
        )


def _require_ascending_rows(rows: Sequence[dict[str, object]]) -> None:
    """Persisted rows are in `requirement_id` order (spec 4.6.3.1, 8.2).

    Sorting them for the expected table would hide a persisted representation
    that is out of order, so the order actually stored is what is checked.
    """
    stored = [row["requirement_id"] for row in rows]
    if stored != sorted(stored):
        raise _refuse(
            ArchitectureResultCode.ARCHITECTURE_RENDER_INVALID,
            f"Envelope traceability is ordered {stored}, not by requirement_id "
            "ascending.",
        )


def _require_row_anchors(requirement_id: str, anchors: Sequence[str]) -> None:
    seen: set[str] = set()
    for anchor in anchors:
        if not ANCHOR_PATTERN.fullmatch(anchor):
            raise _refuse(
                ArchitectureResultCode.TRACEABILITY_UNKNOWN_ANCHOR,
                f"{requirement_id!r} maps to {anchor!r}, which is not one of "
                "tsa-s01 … tsa-s16. Heading text is never an anchor.",
            )
        if anchor in seen:
            raise _refuse(
                ArchitectureResultCode.TRACEABILITY_DUPLICATE_ANCHOR,
                f"{requirement_id!r} maps to {anchor!r} twice in one row.",
            )
        seen.add(anchor)


# ---------------------------------------------------------------------------
# Rendering (spec 8.3)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderedArchitecture:
    """The sixteen normative sections and the fingerprint that covers them.

    `markdown` ends with exactly one newline and carries no envelope, so
    `content_fingerprint` cannot depend on itself (spec 4.6.1).
    """

    markdown: str
    content_fingerprint: str


def _source_cell(requirement_id: str, tree_fingerprint: str) -> str:
    """Column 2: generated from the Manifest, never supplied by the model."""
    return SOURCE_TEMPLATE.format(
        requirement_id=escape_markdown(requirement_id),
        fingerprint_prefix=tree_fingerprint[:SOURCE_FINGERPRINT_LENGTH],
    )


def _ordered_rows(rows: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(rows, key=lambda row: row["requirement_id"])


def _traceability_lines(
    rows: Sequence[dict[str, object]], manifest_body: dict[str, object]
) -> list[str]:
    fingerprints = {
        row["requirement_id"]: row["tree_fingerprint"]
        for row in manifest_body["requirements"]
    }
    lines = [TABLE_HEADER, TABLE_SEPARATOR]
    for row in _ordered_rows(rows):
        requirement_id = row["requirement_id"]
        cells = (
            escape_markdown(requirement_id),
            _source_cell(requirement_id, fingerprints[requirement_id]),
            _escaped_cell(row["anchors"]),
            escape_markdown(row["how_satisfied"]),
            _escaped_cell(row["constraints"]),
            _escaped_cell(row["gaps"]),
        )
        lines.append(f"{CELL_DELIMITER} {' | '.join(cells)} {CELL_DELIMITER}")
    return lines


def _list_lines(source: str, items: Sequence[object]) -> list[str]:
    """One item per entry in array order, or the explicit "none" (spec 8.3)."""
    if not items:
        return [NONE_IDENTIFIED]
    if source == RISKS_SOURCE:
        return [
            RISK_ITEM_TEMPLATE.format(
                detail=escape_markdown(item["detail"]),
                impact=escape_markdown(item["impact"]),
            )
            for item in items
        ]
    return [LIST_ITEM_TEMPLATE.format(item=escape_markdown(item)) for item in items]


def _generated_lines(
    heading: ArchitectureHeading,
    arrays: dict[str, object],
    manifest_body: dict[str, object],
) -> list[str]:
    source = heading.generated_from
    if source == TRACEABILITY_SOURCE:
        return _traceability_lines(arrays[source], manifest_body)
    return _list_lines(source, arrays[source])


def _section_lines(
    heading: ArchitectureHeading,
    intended_output: dict[str, object],
    manifest_body: dict[str, object],
) -> list[str]:
    if heading.section_key is not None:
        return [escape_markdown(intended_output["sections"][heading.section_key])]
    return _generated_lines(heading, intended_output, manifest_body)


def render_architecture(
    intended_output: dict[str, object], manifest_body: dict[str, object]
) -> RenderedArchitecture:
    """The replay identity of spec 4.6.3.1. Pure: same pair, same bytes.

    `intended_output` is the complete normalized renderer input and is read as
    given: nothing is defaulted, reordered in place or invented, and no other
    source — in particular no `architect_response` — is consulted.
    `manifest_body` contributes the selection and the `Source` column only.

    Raises `InvalidTsaArtifact` for a shape I01's closed schemas refuse and
    `ArchitectureRefused` for a rule of spec 8. Cost is linear in the text and
    in the number of selected Requirements, which spec 15 bounds at 100.
    """
    validate_intended_output(intended_output)
    validate_manifest_body(manifest_body)
    _require_section_values(intended_output["sections"])
    _require_exact_coverage(intended_output["traceability"], manifest_body)
    blocks = [
        "\n".join(
            [heading.line, "", *_section_lines(heading, intended_output, manifest_body)]
        )
        for heading in HEADINGS
    ]
    markdown = "\n\n".join(blocks) + "\n"
    _require_visible_headings(markdown)
    _require_no_fence_marker_line(markdown)
    _section_bodies(markdown)
    _require_no_code_block(markdown)
    return RenderedArchitecture(markdown, document_fingerprint(markdown))


# ---------------------------------------------------------------------------
# Reading a rendered Document back into its sixteen sections (spec 8.1)
# ---------------------------------------------------------------------------


def _render_invalid(message: str) -> ArchitectureRefused:
    return _refuse(ArchitectureResultCode.ARCHITECTURE_RENDER_INVALID, message)


def _require_visible_headings(normative_markdown: str) -> None:
    """No tilde fence and no HTML comment block may take a heading out.

    Markdown reads every line after an open fence, or after a line that opens
    a comment block, as that block's content, so sixteen heading-shaped lines
    are no evidence of sixteen sections. Only a bare run of tildes at least as
    long as the opener closes a fence; a comment block ends with the first
    line holding its closer, and a closer later on a heading's own line does
    not bring that heading back. This decides structure alone: a block that
    ends inside its own section is not judged here, and the text is only
    read, never changed.
    """
    open_run = 0
    is_in_comment = False
    for raw in normative_markdown.split("\n"):
        line = raw.rstrip()
        if is_in_comment:
            _require_not_hidden_heading(line)
            is_in_comment = COMMENT_CLOSER not in line
        elif open_run:
            if HEADING_LIKE.match(line):
                break
            open_run = 0 if _closes_tilde_fence(line, open_run) else open_run
        elif fence := TILDE_FENCE.fullmatch(line):
            open_run = len(fence.group(1))
        else:
            is_in_comment = _opens_comment_block(line)
    if open_run:
        raise _render_invalid(
            "A tilde fence opened in the normative sections is not closed "
            "before the next heading or the envelope, so it would take them "
            "out of the Document's structure."
        )


def _closes_tilde_fence(line: str, open_run: int) -> bool:
    fence = TILDE_FENCE.fullmatch(line)
    return bool(fence) and not fence.group(2) and len(fence.group(1)) >= open_run


def _opens_comment_block(line: str) -> bool:
    """A line that starts a comment and does not also end it."""
    return bool(COMMENT_BLOCK_OPENER.match(line)) and COMMENT_CLOSER not in line


def _require_not_hidden_heading(line: str) -> None:
    if HEADING_LIKE.match(line):
        raise _render_invalid(
            f"Heading line {line!r} lies inside an HTML comment opened on an "
            "earlier line, so it is not a heading of the Document."
        )


def _require_no_fence_marker_line(normative_markdown: str) -> None:
    """Rule X of spec v0.3 8.3: backticks and tildes alike, line by line."""
    if has_fence_marker_line(normative_markdown):
        raise _render_invalid(
            "A line of the normative sections opens with three or more "
            "backticks or tildes (rule X); the only fence an Architecture "
            "Document holds is its trailing envelope."
        )


def _require_no_code_block(normative_markdown: str) -> None:
    """Rule S of spec v0.3 8.3, by the mechanism of spec v0.4.

    Given the normative Markdown only, never the envelope, which is itself a
    fence. Both a code block and a classification that could not be completed
    refuse with `ARCHITECTURE_RENDER_INVALID`; the message says which.
    """
    result = classify_code_blocks(normative_markdown)
    if result.outcome is BlockClassification.CODE_BLOCK:
        where = f" starting on line {result.line}" if result.line else ""
        raise _render_invalid(
            f"The normative sections contain a code block{where} (rule S); "
            "code blocks, illustrative diagrams included, are not supported."
        )
    if result.outcome is BlockClassification.UNCLASSIFIABLE:
        raise _render_invalid(
            "The block structure of the normative sections could not be "
            f"classified ({result.reason}), so rule S cannot be shown to hold."
        )


def _section_bodies(normative_markdown: str) -> list[list[str]]:
    """The non-blank content lines under each of the sixteen headings.

    The headings must be exactly the frozen lines, in the frozen order, with
    nothing before the first one and no other heading. Lines that open with a
    fence-marker run are refused before this runs (rule X).
    """
    bodies: list[list[str]] = []
    for raw in normative_markdown.split("\n"):
        line = raw.rstrip()
        if not line:
            continue
        if HEADING_LIKE.match(line):
            _require_next_heading(line, len(bodies))
            bodies.append([])
        elif not bodies:
            raise _render_invalid(f"Content precedes heading 1 ({HEADINGS[0].line!r}).")
        else:
            bodies[-1].append(line)
    if len(bodies) != len(HEADINGS):
        raise _render_invalid(
            f"The Document has {len(bodies)} of the {len(HEADINGS)} frozen headings."
        )
    return bodies


def _require_next_heading(line: str, position: int) -> None:
    if position >= len(HEADINGS):
        raise _render_invalid(f"Heading {line!r} follows the sixteenth heading.")
    expected = HEADINGS[position].line
    if line != expected:
        raise _render_invalid(
            f"Heading {position + 1} must be exactly {expected!r}, not {line!r}."
        )


def _split_cells(row: str) -> list[str]:
    """The cells of one table row; an escaped character never delimits."""
    if not (row.startswith(CELL_DELIMITER) and row.endswith(CELL_DELIMITER)):
        raise _render_invalid(f"Traceability row {row!r} is not a table row.")
    cells: list[str] = []
    current: list[str] = []
    is_escaped = False
    for character in row[1:]:
        if not is_escaped and character == CELL_DELIMITER:
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(character)
        is_escaped = not is_escaped and character == ESCAPE_CHARACTER
    if current:
        raise _render_invalid(f"Traceability row {row!r} ends inside a cell.")
    return cells


def _fibery_table_lines(canonical: list[str]) -> list[str]:
    """The canonical table exactly as Fibery stores it (spec v0.7 section 3).

    The header is unchanged, the separator is spaced, and within each row
    every literal `<br>` becomes one space. A row's `<br>` can only be the
    renderer's own (8.3.1 escapes the `<` and `>` of model text), so this
    touches the array joins and escaped line breaks of the cells and nothing
    else. Nothing is collapsed, unescaped or trimmed.
    """
    header, _separator, *rows = canonical
    return [
        header,
        FIBERY_TABLE_SEPARATOR,
        *(FIBERY_TABLE_LINE_BREAK.join(row.split(LINE_BREAK)) for row in rows),
    ]


def _require_fibery_table(body: list[str], canonical: list[str]) -> None:
    """The stored table is the canonical one as Fibery stores it, line for line.

    Every expected line comes from the envelope and the Manifest; the stored
    text is only compared with it, never read for values.
    """
    expected = _fibery_table_lines(canonical)
    if body[0] != expected[0] or len(body) != len(expected):
        raise _render_invalid(
            "The Fibery-stored Requirement Traceability table does not have the "
            "frozen header and one row per envelope traceability row."
        )
    for position, (actual, wanted) in enumerate(zip(body, expected, strict=True)):
        if actual != wanted:
            raise _render_invalid(
                f"Line {position + 1} of the Fibery-stored Requirement "
                f"Traceability table is {actual!r}, which is not the stored form "
                f"{wanted!r} of the envelope's table (spec v0.7)."
            )


def _require_table_agreement(
    body: list[str],
    rows: Sequence[dict[str, object]],
    manifest_body: dict[str, object],
) -> bool:
    """Every cell is the rendering of its envelope row (spec 8.2, 8.3.1).

    `Source` is generated from the Manifest. This is equality of two
    representations of the same data, not a judgement of satisfaction.
    Returns whether the table is in the Fibery-stored form of spec v0.7,
    which is accepted only as a whole and only exactly.
    """
    expected = _traceability_lines(rows, manifest_body)
    if len(body) > 1 and body[1] == FIBERY_TABLE_SEPARATOR:
        _require_fibery_table(body, expected)
        return True
    if body[:2] != expected[:2] or len(body) != len(expected):
        raise _render_invalid(
            "The Requirement Traceability table does not have the frozen "
            "header and one row per envelope traceability row."
        )
    for actual_row, expected_row in zip(body[2:], expected[2:], strict=True):
        actual, wanted = _split_cells(actual_row), _split_cells(expected_row)
        if len(actual) != TABLE_COLUMN_COUNT:
            raise _render_invalid(
                f"Traceability row {actual_row!r} does not have "
                f"{TABLE_COLUMN_COUNT} cells."
            )
        for column in range(TABLE_COLUMN_COUNT):
            if actual[column] != wanted[column]:
                raise _render_invalid(
                    f"Traceability row {actual_row!r} disagrees with the "
                    f"envelope: expected {wanted[column]!r} in column "
                    f"{column + 1}."
                )
    return False


def _canonical_bullet(line: str) -> str:
    """Fibery returns a `-` bullet as `*`; that is not a difference."""
    for bullet in FIBERY_BULLETS:
        if line.startswith(bullet):
            return CANONICAL_BULLET + line[len(bullet) :]
    return line


def _require_prose_body(heading: ArchitectureHeading, body: list[str]) -> None:
    if not body:
        raise _render_invalid(
            f"Section {heading.number} ({heading.title}) holds no content."
        )
    if not NOT_APPLICABLE_CLAIM.match(body[0]):
        return
    _require_not_applicable_rule(heading, "\n".join(body))


def _require_rendered_sections(
    bodies: list[list[str]], artifact: TsaArtifact, manifest_body: dict[str, object]
) -> bool:
    """Every section body agrees with its class and with the envelope.

    Returns whether the traceability table is in its Fibery-stored form.
    """
    is_fibery_table = False
    for heading, body in zip(HEADINGS, bodies, strict=True):
        if heading.section_key is not None:
            _require_prose_body(heading, body)
        elif heading.generated_from == TRACEABILITY_SOURCE:
            is_fibery_table = _require_table_agreement(
                body, artifact.body[TRACEABILITY_SOURCE], manifest_body
            )
        else:
            expected = _generated_lines(heading, artifact.body, manifest_body)
            if [_canonical_bullet(line) for line in body] != expected:
                raise _render_invalid(
                    f"Section {heading.number} ({heading.title}) does not "
                    f"render the envelope's {heading.generated_from}."
                )
    return is_fibery_table


# ---------------------------------------------------------------------------
# The post-apply carrier: local assembly and validation (spec 4.1, 4.6.1)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArchitectureBinding:
    """Everything the envelope carries that the renderer cannot know.

    Supplied by the caller from durable state: the trusted identity, the
    bootstrap `created_at` already persisted on this Document, and the
    iteration being applied. Nothing here is defaulted or generated.
    """

    identity: ArtifactIdentity
    created_at: str
    current_iteration: int


@dataclass(frozen=True)
class ArchitectureCarrier:
    """A post-apply Architecture Document, assembled locally and not written."""

    text: str
    content_fingerprint: str
    artifact: TsaArtifact


def _normative_markdown(document: str) -> str:
    """Everything before the trailing envelope fence (spec 4.6.1).

    Called only after I01 accepted the carrier, which guarantees exactly one
    `json` fence opener in the whole Document.
    """
    lines = document.split("\n")
    opener = next(
        index for index, line in enumerate(lines) if line.strip() == JSON_FENCE_OPENER
    )
    return "\n".join(lines[:opener])


def _heading_position(lines: list[str], heading: ArchitectureHeading) -> int:
    """The one line holding this frozen heading; `_section_bodies` proved it."""
    return next(
        index for index, line in enumerate(lines) if line.rstrip() == heading.line
    )


def _with_canonical_table(normative: str, table: list[str]) -> str:
    """The normative Markdown with section 2 rebuilt as the canonical table.

    Spec v0.7: only after the stored table was proved to be the Fibery-stored
    form of `table`. Every other line is kept exactly as read, so an edit
    anywhere else still changes the fingerprint. In memory only.
    """
    lines = normative.split("\n")
    start = _heading_position(lines, HEADINGS[1])
    end = _heading_position(lines, HEADINGS[2])
    return "\n".join([*lines[: start + 1], "", *table, "", *lines[end:]])


def _require_post_apply(artifact: TsaArtifact) -> None:
    if artifact.artifact_type != ARCHITECTURE:
        raise InvalidTsaArtifact(
            f"The envelope is {artifact.artifact_type!r}, not {ARCHITECTURE!r}."
        )
    if TRACEABILITY_SOURCE not in artifact.body:
        raise _render_invalid(
            "The Document is a pre-apply bootstrap carrier: no Architect output "
            "has been applied, so it has no sixteen-heading representation."
        )


def validate_architecture_document(
    document: str | None, manifest_body: dict[str, object]
) -> TsaArtifact:
    """Structural validation of a post-apply Architecture Document.

    Checked separately, in this order: the carrier, closed schema and
    `artifact_digest` through I01; that the envelope binds this Manifest; the
    sixteen headings and their content classes, with no fence left open across
    them and no heading inside an HTML comment; traceability coverage and stored row order; the agreement of the
    rendered generated sections with the envelope, cell for cell; and that
    `content_fingerprint` is the fingerprint of the normative Markdown with
    the envelope excluded; and last, that the normative Markdown carries no
    code block and no fence-marker line (rules S and X, spec v0.3 8.3, v0.4).

    Spec v0.7: a traceability table in the exact Fibery-stored form of the
    envelope's canonical table is accepted, and the fingerprint is then taken
    over the normative Markdown with that one table rebuilt canonically from
    the envelope and the Manifest. The Document itself is never changed.

    Raises `EmptyTsaCarrier` or `InvalidTsaArtifact` (I01's taxonomy) and
    `ArchitectureRefused`. Returns the validated artifact.
    """
    artifact = validate_artifact(extract_architecture_envelope(document))
    _require_post_apply(artifact)
    validate_manifest_body(manifest_body, identity=artifact.identity)
    if artifact.body["manifest_digest"] != manifest_digest(manifest_body):
        raise InvalidTsaArtifact(
            "The Architecture envelope binds another Input Manifest than the "
            "one supplied."
        )
    normative = _normative_markdown(document)
    _require_visible_headings(normative)
    _require_no_fence_marker_line(normative)
    bodies = _section_bodies(normative)
    _require_exact_coverage(artifact.body[TRACEABILITY_SOURCE], manifest_body)
    _require_ascending_rows(artifact.body[TRACEABILITY_SOURCE])
    canonical = normative
    if _require_rendered_sections(bodies, artifact, manifest_body):
        canonical = _with_canonical_table(
            normative,
            _traceability_lines(artifact.body[TRACEABILITY_SOURCE], manifest_body),
        )
    if artifact.body["content_fingerprint"] != document_fingerprint(canonical):
        raise InvalidTsaArtifact(
            "The envelope's content_fingerprint is not the fingerprint of the "
            "sixteen sections it accompanies."
        )
    _require_no_code_block(normative)
    return artifact


def build_architecture_carrier(
    intended_output: dict[str, object],
    manifest_body: dict[str, object],
    binding: ArchitectureBinding,
) -> ArchitectureCarrier:
    """Assemble the post-apply Document for one iteration. Writes nothing.

    The sixteen sections are `render_architecture` of the pair; the envelope
    copies the five renderer-owned arrays verbatim (spec 4.6.1), binds the
    Manifest by its recomputed digest and the sections by their fingerprint,
    and is sealed by I01. The Markdown already ends with the one newline that
    precedes the envelope fence (spec 8.3). The result is validated as any
    other Document is, so rows that are not in `requirement_id` order are
    refused, never re-sorted.
    """
    rendered = render_architecture(intended_output, manifest_body)
    identity = binding.identity
    arrays = {
        heading.generated_from: copy.deepcopy(intended_output[heading.generated_from])
        for heading in HEADINGS
        if heading.generated_from is not None
    }
    sealed = sealed_artifact(
        {
            "artifact_type": ARCHITECTURE,
            "schema_version": SCHEMA_VERSION,
            "workspace_identity": identity.workspace_identity,
            "project_entity_id": identity.project_entity_id,
            "project_code": identity.project_code,
            "cycle_id": identity.cycle_id,
            "body": {
                "cycle_id": identity.cycle_id,
                "created_at": binding.created_at,
                "manifest_digest": manifest_digest(manifest_body),
                "content_fingerprint": rendered.content_fingerprint,
                "current_iteration": binding.current_iteration,
                PRODUCT_QUESTIONS_KEY: copy.deepcopy(
                    intended_output[PRODUCT_QUESTIONS_KEY]
                ),
                **arrays,
            },
        }
    )
    text = (
        f"{rendered.markdown}"
        f"{JSON_FENCE_OPENER}\n{canonical_artifact_json(sealed)}\n{FENCE_MARKER}\n"
    )
    artifact = validate_architecture_document(text, manifest_body)
    return ArchitectureCarrier(text, rendered.content_fingerprint, artifact)
