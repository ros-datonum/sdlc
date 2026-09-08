"""The bounded prompt for Standard Requirement normalization and analysis.

Context is the Requirement, its documents, the RAW it came from, and the
Project's other Standard Requirements as comparison material (entity metadata
plus each one's complete current Root Document). No Milestones, Epics,
Stories, Tasks or Project Phases.

The model is asked for structured data only, never for reasoning, never for
Fibery mechanics, and never for permission to change anything.
"""

from __future__ import annotations

from sdlc.comparison_context import (
    ComparisonContext,
    render_comparison_section,
    render_target_metadata,
)
from sdlc.fibery_workspace import RequirementRecord
from sdlc.standard_analysis import FindingKind, RelationKind

INSTRUCTIONS = """\
You are normalizing and analyzing one Standard Requirement in an SDLC system.

Return ONLY a single JSON object. No prose, no explanation of your reasoning, no
markdown outside the JSON.

Shape:

{
  "normalized_requirement": {
    "title": "short descriptive title",
    "requirement": "the normative statement: what must be true",
    "detailed_behavior": "behavioural detail needed to interpret it",
    "rationale": "why it exists",
    "acceptance_verification": "observable conditions proving satisfaction",
    "constraints_edge_cases": "constraints, boundaries, edge conditions",
    "non_goals": "explicitly excluded behaviour or scope",
    "open_questions": "unresolved points, or omit"
  },
  "analysis": {
    "completeness": "...", "clarity": "...", "atomicity": "...",
    "testability": "...", "internal_consistency": "..."
  },
  "findings": [
    { "kind": "<finding kind>", "detail": "what you observed",
      "requirement_id": "see the finding rule below" }
  ],
  "proposed_relations": [
    { "kind": "DEPENDS_ON" | "AFFECTS",
      "requirement_id": "an existing Requirement ID",
      "rationale": "why" }
  ]
}

Rules:

- Improve clarity and completeness using only what the requirement and its
  originating RAW source establish. Do not invent obligations, rationale,
  acceptance criteria or constraints.
- Omit a section, or leave it empty, when the source does not establish it.
  Deterministic code fills those in; inventing content is worse than omitting it.
- Keep the requirement to one obligation. If it contains more than one, report a
  NON_ATOMIC finding rather than splitting it: you cannot create Requirements.
- Two classes of finding exist, and `requirement_id` separates them:
  * A finding ABOUT THIS Requirement (INCOMPLETE, AMBIGUOUS, NON_ATOMIC,
    INCONSISTENT, NOT_TESTABLE, MISSING_CONSTRAINT, MISSING_EDGE_CASE) carries
    no `requirement_id`: omit the key or set it to null. When another
    Requirement is only evidence or context for the point, name it inside
    `detail`, never in `requirement_id`. A finding of one of these kinds that
    carries a `requirement_id` is rejected as a whole, together with the rest
    of this output.
  * A finding ABOUT ANOTHER Requirement (POSSIBLE_DUPLICATE, POSSIBLE_CONFLICT,
    POSSIBLE_CHANGE, POSSIBLE_SUPERSESSION) must name that Requirement in
    `requirement_id`, by its Requirement ID.
  Examples:
    { "kind": "MISSING_CONSTRAINT", "requirement_id": null,
      "detail": "This Requirement does not govern the child process
                 environment. Peer SDLC-FR-0002 does not establish it either." }
    { "kind": "POSSIBLE_CONFLICT", "requirement_id": "SDLC-FR-0002",
      "detail": "SDLC-FR-0002 enumerates a status set that omits INVALID_REQUEST." }
  Findings are observations only. You cannot modify, retire or supersede
  anything.
- Relations are proposals for an independent reviewer to confirm. Proposing one
  does not create it.
- The other Standard Requirements are supplied with their full Root Documents
  so comparison findings and relations rest on what they actually state.
  They never authorize changing this Requirement's intent, and one that is
  not Applied is a candidate under review, not approved authority.
- Emit no field that is not listed above. Unknown fields are rejected.
"""


def build_analysis_prompt(
    requirement: RequirementRecord,
    project_name: str,
    root_content: str,
    child_content: str,
    raw_ancestry: str,
    comparison: ComparisonContext,
) -> tuple[str, str]:
    """Return the instruction prompt and the context sent on stdin."""
    context = "\n".join(
        [
            "# Project",
            project_name,
            "",
            "# Requirement under analysis",
            f"{requirement.requirement_id} — {requirement.title}",
            *render_target_metadata(requirement),
            "",
            "# Current Requirement document",
            root_content or "(empty)",
            "",
            _section("Normative child documents", child_content),
            "",
            _section("Originating RAW requirement source", raw_ancestry),
            "",
            render_comparison_section(comparison),
            "",
            f"# Allowed finding kinds\n{', '.join(k.value for k in FindingKind)}",
            f"# Allowed relation kinds\n{', '.join(k.value for k in RelationKind)}",
        ]
    )
    return INSTRUCTIONS, context


def _section(heading: str, body: str) -> str:
    return f"# {heading}\n{body}" if body.strip() else f"# {heading}\n(none)"
