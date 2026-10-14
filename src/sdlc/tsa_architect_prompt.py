"""TSA-C01 I07 — the Architect prompt and the bound on its assembled input.

Implementation spec v0.3 sections 9.1, 15 and 16.1. This module is pure: it
reads nothing, calls no model and keeps no state. It turns material the stage
has already read and bound to the accepted Input Manifest into the exact
`prompt` and `context` handed to the runtime, and refuses an assembled input
above the frozen bound instead of truncating it.

What the Architect is given, and nothing else (16.1): the Project code and
name as identity; the Input Manifest body; the full normative tree of every
selected Requirement; the UX Document content only when the recorded UX value
is `APPLICABLE`; and, on an authorized rework only, the previous Architecture
Document and the previous Review Result findings, labelled as material to
revise and never as authority.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sdlc.model_runtime import assemble_model_input
from sdlc.tsa_admission import SELECTION_LIMIT
from sdlc.tsa_architecture import HEADINGS
from sdlc.tsa_artifacts import UX_APPLICABLE

#: Spec 15: the assembled model input is capped at this many code points.
ASSEMBLED_INPUT_LIMIT = 400_000

MANIFEST_JSON_INDENT = 2

#: The one response shape of spec 9.1, shown to the model verbatim.
RESPONSE_SHAPE = """\
{
  "architecture": {
    "scope_and_inputs": "...", "solution_structure": "...",
    "components_and_responsibilities": "...", "interfaces_and_data_flows": "...",
    "data_storage": "...", "external_integrations": "...",
    "security_authn_authz": "...", "deployment_runtime_model": "...",
    "failure_recovery": "...", "observability": "...",
    "migration_implications": "...", "architecture_decisions": "..."
  },
  "traceability": [ { "requirement_id": "...", "anchors": ["tsa-s03"],
                      "how_satisfied": "...", "constraints": ["..."],
                      "gaps": ["..."] } ],
  "assumptions": ["..."],
  "risks": [ { "detail": "...", "impact": "LOW|MEDIUM|HIGH" } ],
  "open_architecture_questions": ["..."],
  "product_questions": [ { "detail": "...", "requirement_id": "...",
                           "material": true } ]
}"""

INSTRUCTIONS = """\
You are the Architect of one Technical Solution Architecture cycle.

Authority. The selected Requirements and, where supplied, the UX Document are
the only normative sources. They define WHAT. You define HOW and you must not
change WHAT. The Project code and name identify the Project and are not a
source of requirements. Material labelled as material to revise is the
previous iteration's output and its review; it is not authority.

Produce exactly one integrated, recommended architecture that satisfies the
selected Requirements. Do not present a catalogue of alternatives; state the
trade-offs of the one you recommend in architecture_decisions.

Unresolved product questions. When a correct HOW depends on a product decision
the Requirements do not make, do not answer it and do not assume an answer.
Record it in product_questions with the Requirement it concerns and
"material": true when a correct HOW depends on it, false otherwise.

You must not produce: new product obligations; answers to unresolved WHAT
questions; Epics, Stories or Tasks; estimates, sprints or schedules;
implementation assignments; generated code or configuration; deployment
commands or deployment execution; instructions to change any Requirement or
any Fibery record; Fibery ids you were not given.

Text rules for every string value:
- plain prose; no code block of any kind, fenced or indented, including
  diagrams;
- no line that starts, after at most three spaces, with three or more
  backticks or three or more tildes.

Sections. The twelve architecture keys render as the headings below. Mandatory
sections need substantive content. A Content-or-N/A section that does not
apply holds exactly one line: "N/A — <reason on one line>". Headings 2, 14, 15
and 16 are generated from traceability, assumptions, risks and
open_architecture_questions; leave an array empty when there is nothing to
record.

{headings}

Traceability. Exactly one row per selected Requirement, no other rows. anchors
is a non-empty list of distinct heading anchors, tsa-s01 to tsa-s16 exactly as
written above; several Requirements may share an anchor.

Response. Return only one JSON object with exactly this shape and these keys,
and nothing else: no prose before or after it, no Markdown fence around it, no
explanation of how you reached it. Every key is required; arrays may be empty.

{shape}"""

SECTION_PROJECT = "PROJECT IDENTITY (identity only; not a source of requirements)"
SECTION_MANIFEST = "ACCEPTED INPUT MANIFEST BODY (immutable; JSON)"
SECTION_REQUIREMENTS = "SELECTED REQUIREMENTS (normative sources; full trees)"
SECTION_UX = "UX DOCUMENT (APPLICABLE; normative for its recorded scope)"
SECTION_UX_NOT_APPLICABLE = "UX (recorded NOT_APPLICABLE by the human)"
SECTION_REWORK = (
    "MATERIAL TO REVISE (iteration {iteration}; not authority; revise the "
    "architecture against the normative sources above)"
)
SECTION_PREVIOUS_ARCHITECTURE = "Previous Architecture Document"
SECTION_PREVIOUS_REVIEW = "Previous Review Result findings (JSON)"
UX_NOT_APPLICABLE_NOTE = (
    "No UX Document applies to this cycle and none is supplied; the recorded "
    "decision and reason are in the Input Manifest body."
)


class ArchitectInputTooLarge(ValueError):
    """The assembled input, or the selection, exceeds the bound of spec 15.

    Nothing was truncated and the model was not invoked.
    """


@dataclass(frozen=True)
class RequirementMaterial:
    """One selected Requirement's full normative tree, as read and bound."""

    requirement_id: str
    entity_id: str
    tree_fingerprint: str
    rendered_tree: str


@dataclass(frozen=True)
class ReworkMaterial:
    """What an authorized rework revises: never authority (spec 16.1)."""

    previous_iteration: int
    architecture_document: str
    review_findings: dict[str, object]


@dataclass(frozen=True)
class ArchitectPromptInput:
    """Everything the Architect is given. `ux_content` exists only for APPLICABLE."""

    project_code: str
    project_name: str
    manifest_body: dict[str, object]
    requirements: tuple[RequirementMaterial, ...]
    ux_content: str | None
    rework: ReworkMaterial | None


@dataclass(frozen=True)
class ArchitectPrompt:
    """The exact two strings handed to `ModelRuntime.run`."""

    prompt: str
    context: str

    @property
    def assembled_length(self) -> int:
        return len(assemble_model_input(self.prompt, self.context))


def _heading_lines() -> str:
    lines = []
    for heading in HEADINGS:
        if heading.section_key is not None:
            source = f"architecture.{heading.section_key}"
        else:
            source = f"generated from {heading.generated_from}"
        kind = "Mandatory" if heading.is_mandatory else "Content-or-N/A"
        lines.append(
            f"- {heading.anchor}: {heading.number}. {heading.title} — {kind}; {source}"
        )
    return "\n".join(lines)


def architect_instructions() -> str:
    """The fixed instruction text, including the exact response shape."""
    return INSTRUCTIONS.format(headings=_heading_lines(), shape=RESPONSE_SHAPE)


def _section(title: str, body: str) -> str:
    return f"=== {title} ===\n{body}"


def _requirement_block(material: RequirementMaterial) -> str:
    return (
        f"--- Requirement {material.requirement_id} (entity {material.entity_id}, "
        f"tree fingerprint {material.tree_fingerprint}) ---\n"
        f"{material.rendered_tree}"
    )


def _ux_block(manifest_body: dict[str, object], ux_content: str | None) -> str:
    """APPLICABLE carries the content read now; NOT_APPLICABLE carries none."""
    ux = manifest_body["ux"]
    is_applicable = ux["kind"] == UX_APPLICABLE
    if is_applicable != (ux_content is not None):
        raise ValueError(
            "UX content is supplied exactly when the recorded UX value is "
            f"{UX_APPLICABLE}."
        )
    if not is_applicable:
        return _section(SECTION_UX_NOT_APPLICABLE, UX_NOT_APPLICABLE_NOTE)
    header = (
        f"Document {ux['document_id']}, scope {ux['scope_requirement_ids']}, "
        f"content digest {ux['content_digest']}"
    )
    return _section(SECTION_UX, f"{header}\n\n{ux_content}")


def _rework_block(rework: ReworkMaterial) -> str:
    findings = json.dumps(
        rework.review_findings,
        sort_keys=True,
        ensure_ascii=False,
        indent=MANIFEST_JSON_INDENT,
    )
    return _section(
        SECTION_REWORK.format(iteration=rework.previous_iteration),
        f"--- {SECTION_PREVIOUS_ARCHITECTURE} ---\n{rework.architecture_document}\n\n"
        f"--- {SECTION_PREVIOUS_REVIEW} ---\n{findings}",
    )


def _require_selection_bound(material: ArchitectPromptInput) -> None:
    count = len(material.requirements)
    if count > SELECTION_LIMIT:
        raise ArchitectInputTooLarge(
            f"The selection holds {count} Requirements; the limit is "
            f"{SELECTION_LIMIT}. Nothing was truncated and the model was not "
            "invoked."
        )


def build_architect_prompt(material: ArchitectPromptInput) -> ArchitectPrompt:
    """The instructions as `prompt`, the bound evidence as `context`.

    The manifest body is shown as JSON for reading only; it is not a digest
    input. Requirements appear in manifest order, each as its full rendered
    tree. Raises `ArchitectInputTooLarge` for a selection above the limit and
    `ValueError` when UX content is supplied against the recorded branch.
    """
    _require_selection_bound(material)
    manifest_json = json.dumps(
        material.manifest_body,
        sort_keys=True,
        ensure_ascii=False,
        indent=MANIFEST_JSON_INDENT,
    )
    blocks = [
        _section(
            SECTION_PROJECT,
            f"Project code: {material.project_code}\n"
            f"Project name: {material.project_name}",
        ),
        _section(SECTION_MANIFEST, manifest_json),
        _section(
            SECTION_REQUIREMENTS,
            "\n\n".join(_requirement_block(item) for item in material.requirements),
        ),
        _ux_block(material.manifest_body, material.ux_content),
    ]
    if material.rework is not None:
        blocks.append(_rework_block(material.rework))
    return ArchitectPrompt(prompt=architect_instructions(), context="\n\n".join(blocks))


def require_within_input_bound(prompt: ArchitectPrompt) -> None:
    """Refuse the whole input above the bound; never truncate (spec 15).

    Measured on `assemble_model_input`, the exact text the runtime sends.
    """
    length = prompt.assembled_length
    if length > ASSEMBLED_INPUT_LIMIT:
        raise ArchitectInputTooLarge(
            f"The assembled Architect input is {length} code points, above the "
            f"{ASSEMBLED_INPUT_LIMIT} limit. Nothing was truncated and the model "
            "was not invoked."
        )
