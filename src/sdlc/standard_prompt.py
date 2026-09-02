"""The bounded prompt for Standard Requirement normalization and analysis.

Context is the Requirement, its documents, the RAW it came from, and a concise
index of the Project's other Standard Requirements. No Milestones, Epics,
Stories, Tasks or Project Phases.

The model is asked for structured data only, never for reasoning, never for
Fibery mechanics, and never for permission to change anything.
"""

from __future__ import annotations

from sdlc.fibery_workspace import RequirementRecord
from sdlc.standard_analysis import FindingKind, RelationKind

EXISTING_STANDARD_LIMIT = 100

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
      "requirement_id": "only for findings about another Requirement" }
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
- Findings about another Requirement must name it by Requirement ID, and are
  observations only. You cannot modify, retire or supersede anything.
- Relations are proposals for an independent reviewer to confirm. Proposing one
  does not create it.
- Emit no field that is not listed above. Unknown fields are rejected.
"""


def build_analysis_prompt(
    requirement: RequirementRecord,
    project_name: str,
    root_content: str,
    child_content: str,
    raw_ancestry: str,
    existing_standards: tuple[RequirementRecord, ...],
) -> tuple[str, str]:
    """Return the instruction prompt and the context sent on stdin."""
    context = "\n".join(
        [
            "# Project",
            project_name,
            "",
            "# Requirement under analysis",
            f"{requirement.requirement_id} — {requirement.title}",
            f"Category: {requirement.type_name or 'unknown'}",
            "",
            "# Current Requirement document",
            root_content or "(empty)",
            "",
            _section("Additional child documents", child_content),
            "",
            _section("Originating RAW requirement source", raw_ancestry),
            "",
            _existing_section(existing_standards),
            "",
            f"# Allowed finding kinds\n{', '.join(k.value for k in FindingKind)}",
            f"# Allowed relation kinds\n{', '.join(k.value for k in RelationKind)}",
        ]
    )
    return INSTRUCTIONS, context


def _section(heading: str, body: str) -> str:
    return f"# {heading}\n{body}" if body.strip() else f"# {heading}\n(none)"


def _existing_section(existing: tuple[RequirementRecord, ...]) -> str:
    """A concise index of the Project's other Standard Requirements."""
    header = "# Other Standard Requirements in this Project"
    lines = [
        f"- {record.requirement_id}: {record.title}"
        for record in existing[:EXISTING_STANDARD_LIMIT]
        if record.requirement_id
    ]
    if not lines:
        return f"{header}\n(none)"
    if len(existing) > EXISTING_STANDARD_LIMIT:
        lines.append(f"- ... and {len(existing) - EXISTING_STANDARD_LIMIT} more")
    return "\n".join([header, *lines])
