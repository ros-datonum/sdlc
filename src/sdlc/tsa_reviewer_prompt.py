"""TSA-C01 I08 — the Reviewer prompt and the bound on its assembled input.

Implementation spec v0.3 sections 10.1, 15 and 16.2. This module is pure: it
reads nothing, calls no model and keeps no state. It turns material the stage
has already read and bound — to the accepted Input Manifest, to the exact
persisted Process Result and to the Architecture that holds its output — into
the exact `prompt` and `context` handed to the runtime, and refuses an
assembled input above the frozen bound instead of truncating it.

What the Reviewer is given, and nothing else (16.2): the exact current
Architecture Document content; the same Input Manifest body and full normative
Requirement trees the Architect saw; the UX Document content only when the
recorded UX value is `APPLICABLE`; and the claims of the persisted Architect
Process Result. A previous Review Result is never supplied, on any iteration,
and neither is Project prose or the Architect's rework material.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from sdlc.model_runtime import assemble_model_input
from sdlc.tsa_admission import SELECTION_LIMIT
from sdlc.tsa_architect import CLAIM_COLLECTIONS
from sdlc.tsa_architect_prompt import ASSEMBLED_INPUT_LIMIT, RequirementMaterial
from sdlc.tsa_artifacts import UX_APPLICABLE, ArtifactReference

JSON_INDENT = 2
#: Context, not claims: shown to the Reviewer, never required to be verified.
CONTEXT_COLLECTION = "assumptions"

#: The one response shape of spec 10.1, shown to the model verbatim.
RESPONSE_SHAPE = """\
{
  "claim_verifications": [
    { "claim_ref": "<exactly one claim reference listed below>",
      "outcome": "CONFIRMED|REJECTED|UNRESOLVED",
      "severity": "INFO|WARNING|BLOCKING",
      "reason": "..." }
  ],
  "traceability_verification": {
    "outcome": "CONFIRMED|REJECTED|UNRESOLVED", "reason": "..." },
  "new_findings": [
    { "kind": "...", "severity": "INFO|WARNING|BLOCKING",
      "detail": "...", "requirement_id": "..." }
  ],
  "material_unresolved_what": [
    { "detail": "...", "requirement_id": "..." } ],
  "assessment": {
    "completeness": "...", "internal_consistency": "...",
    "source_fidelity": "...", "traceability": "...",
    "implementability": "..." }
}"""

INSTRUCTIONS = """\
You are the Reviewer of one Technical Solution Architecture cycle. You are a
separate, independent invocation: you did not write this architecture and you
are given no earlier review of it.

Authority. The selected Requirements and, where supplied, the UX Document are
the only normative sources; they define WHAT. The Architecture Document and
the Architect claims are evidence to verify, not authority. Verify them
independently against the normative sources.

Assess the architecture for completeness, internal consistency, source
fidelity, traceability and implementability, one assessment text each.

Claims. Verify every Architect claim listed under ARCHITECT CLAIMS TO VERIFY
exactly once in claim_verifications, by its exact claim reference. Do not skip
one, do not verify one twice, and do not invent or alter a reference.
Assumptions are listed as context only and are not verified.
- CONFIRMED means you independently agree the claim stands: the risk or
  question is real. REJECTED means you do not. UNRESOLVED means the supplied
  sources cannot settle it. Rejecting a claim is a normal outcome.
- Give a severity only when you CONFIRM a claim, and always when you do.
  REJECTED and UNRESOLVED assert no defect, so they carry no severity.
- A product question marked "material": true stays open unless you REJECT it,
  for example because a selected Requirement already answers it. Do not answer
  it yourself and do not assume an answer.

Traceability. Verify the architecture's traceability rows against the
selected Requirements and record the result in traceability_verification.

New findings. Report anything the Architect missed as a new finding with its
own kind and severity, naming the selected Requirement it concerns. When
selected Requirements contradict each other, report the contradiction and name
every Requirement involved in its detail; do not choose which one wins.
Material unresolved WHAT. When a correct HOW depends on a product decision the
Requirements do not make, record it in material_unresolved_what with the
Requirement it concerns; do not answer it.

You must not: approve or reject the architecture as a whole; state a verdict,
score or recommendation; recommend an action; propose replacement wording or a
rewritten architecture; instruct any change to the Architecture Document, a
Requirement or any Fibery record. There is no field for any of these; the
overall status is derived by code from your evidence.

Response. Return only one JSON object with exactly this shape and these keys,
and nothing else: no prose before or after it, no Markdown fence around it, no
explanation of how you reached it. Every key is required; arrays may be empty.
Emit no field that is not shown. Unknown fields are rejected.

{shape}"""

SECTION_MANIFEST = "ACCEPTED INPUT MANIFEST BODY (immutable; JSON)"
SECTION_REQUIREMENTS = "SELECTED REQUIREMENTS (normative sources; full trees)"
SECTION_UX = "UX DOCUMENT (APPLICABLE; normative for its recorded scope)"
SECTION_UX_NOT_APPLICABLE = "UX (recorded NOT_APPLICABLE by the human)"
SECTION_ARCHITECTURE = (
    "ARCHITECTURE DOCUMENT UNDER REVIEW (exact current content; evidence to "
    "verify, not authority)"
)
SECTION_CLAIMS = (
    "ARCHITECT CLAIMS TO VERIFY (persisted Process Result {digest}; evidence, "
    "not authority)"
)
UX_NOT_APPLICABLE_NOTE = (
    "No UX Document applies to this cycle and none is supplied; the recorded "
    "decision and reason are in the Input Manifest body."
)
NO_CLAIMS_NOTE = "The Architect recorded no claim that requires verification."


class ReviewerInputTooLarge(ValueError):
    """The assembled input, or the selection, exceeds the bound of spec 15.

    Nothing was truncated and the model was not invoked.
    """


@dataclass(frozen=True)
class ReviewerPromptInput:
    """Everything the Reviewer is given. `ux_content` exists only for APPLICABLE.

    `architect_response` is the persisted Process Result's own, and
    `process_digest` its `artifact_digest`, which prefixes every claim
    reference.
    """

    manifest_body: dict[str, object]
    requirements: tuple[RequirementMaterial, ...]
    ux_content: str | None
    architecture_document: str
    process_digest: str
    architect_response: dict[str, object]


@dataclass(frozen=True)
class ReviewerPrompt:
    """The exact two strings handed to `ModelRuntime.run`."""

    prompt: str
    context: str

    @property
    def assembled_length(self) -> int:
        return len(assemble_model_input(self.prompt, self.context))


def reviewer_instructions() -> str:
    """The fixed instruction text, including the exact response shape."""
    return INSTRUCTIONS.format(shape=RESPONSE_SHAPE)


def _section(title: str, body: str) -> str:
    return f"=== {title} ===\n{body}"


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=JSON_INDENT)


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


def claim_references(process_digest: str, response: dict[str, object]) -> list[str]:
    """Every claim reference to verify, in collection then index order (6.3)."""
    return [
        str(ArtifactReference(process_digest, collection, index))
        for collection in CLAIM_COLLECTIONS
        for index in range(len(response[collection]))
    ]


def _claims_block(material: ReviewerPromptInput) -> str:
    response = material.architect_response
    lines = []
    for collection in CLAIM_COLLECTIONS:
        for index, item in enumerate(response[collection]):
            ref = ArtifactReference(material.process_digest, collection, index)
            lines.append(f"- claim_ref {ref}\n{_json(item)}")
    claims = "\n".join(lines) if lines else NO_CLAIMS_NOTE
    assumptions = _json(response[CONTEXT_COLLECTION])
    return _section(
        SECTION_CLAIMS.format(digest=material.process_digest),
        f"{claims}\n\n--- Assumptions (context only; not verified) ---\n{assumptions}",
    )


def _require_selection_bound(material: ReviewerPromptInput) -> None:
    count = len(material.requirements)
    if count > SELECTION_LIMIT:
        raise ReviewerInputTooLarge(
            f"The selection holds {count} Requirements; the limit is "
            f"{SELECTION_LIMIT}. Nothing was truncated and the model was not "
            "invoked."
        )


def build_reviewer_prompt(material: ReviewerPromptInput) -> ReviewerPrompt:
    """The instructions as `prompt`, the bound evidence as `context`.

    Requirements appear in manifest order, each as its full rendered tree; the
    Architecture is the exact content given, unchanged. Raises
    `ReviewerInputTooLarge` for a selection above the limit and `ValueError`
    when UX content is supplied against the recorded branch.
    """
    _require_selection_bound(material)
    blocks = [
        _section(SECTION_MANIFEST, _json(material.manifest_body)),
        _section(
            SECTION_REQUIREMENTS,
            "\n\n".join(_requirement_block(item) for item in material.requirements),
        ),
        _ux_block(material.manifest_body, material.ux_content),
        _section(SECTION_ARCHITECTURE, material.architecture_document),
        _claims_block(material),
    ]
    return ReviewerPrompt(prompt=reviewer_instructions(), context="\n\n".join(blocks))


def require_within_input_bound(prompt: ReviewerPrompt) -> None:
    """Refuse the whole input above the bound; never truncate (spec 15).

    Measured on `assemble_model_input`, the exact text the runtime sends.
    """
    length = prompt.assembled_length
    if length > ASSEMBLED_INPUT_LIMIT:
        raise ReviewerInputTooLarge(
            f"The assembled Reviewer input is {length} code points, above the "
            f"{ASSEMBLED_INPUT_LIMIT} limit. Nothing was truncated and the model "
            "was not invoked."
        )
