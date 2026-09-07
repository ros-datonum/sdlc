"""The bounded prompt for RAW Requirement decomposition.

Context is deliberately narrow: the RAW Requirement and its document tree, the
Project name, and the Project's other Standard Requirements as comparison
material (entity metadata plus each one's complete current Root Document). No
Milestones, Epics, Stories, Tasks or unrelated project state.

The model is asked for structured data only. It is never asked to explain its
reasoning, never given Fibery identifiers to act on, and never asked to produce
the document itself.
"""

from __future__ import annotations

from sdlc.comparison_context import ComparisonContext, render_comparison_section
from sdlc.raw_processing import Category, FindingKind

INSTRUCTIONS = """\
You are decomposing one RAW requirement artifact into Standard Requirement
candidates for an SDLC system.

Return ONLY a single JSON object. No prose, no explanation of your reasoning, no
markdown outside the JSON.

Shape:

{
  "candidates": [
    {
      "category": "FUNCTIONAL" | "NON_FUNCTIONAL" | "CONSTRAINT",
      "title": "short descriptive title",
      "requirement": "the normative statement: what must be true",
      "detailed_behavior": "behavioural detail needed to interpret it",
      "rationale": "why it exists, from the source only",
      "acceptance_verification": "observable conditions proving satisfaction",
      "constraints_edge_cases": "constraints, boundaries, edge conditions",
      "non_goals": "explicitly excluded behaviour or scope",
      "open_questions": "unresolved points, or omit"
    }
  ],
  "findings": [
    {
      "kind": "POSSIBLE_DUPLICATE" | "POSSIBLE_CONFLICT"
            | "POSSIBLE_CHANGE" | "POSSIBLE_SUPERSESSION",
      "requirement_id": "an existing Standard Requirement ID",
      "detail": "what you observed"
    }
  ],
  "no_candidate_reason": "required only when candidates is empty"
}

Rules:

- One candidate is one independently reviewable obligation. Do not split every
  sentence, and do not merge independent obligations because they share a source.
- Use only what the source states. Do not invent requirements, rationale,
  constraints or acceptance criteria.
- Omit a section, or leave it empty, when the source does not establish it.
  Deterministic code fills those in; inventing content is worse than omitting it.
- Findings are observations about existing Standard Requirements. They never
  modify them. Report a finding instead of proposing a change.
- The other Standard Requirements are supplied with their full Root Documents
  so you can see duplication, conflict, change or supersession. They never
  replace what this source states, and one that is not Applied is a
  candidate under review, not approved authority.
- If the source warrants no Standard Requirement, return an empty candidates
  list and explain why in no_candidate_reason.
- Emit no field that is not listed above. Unknown fields are rejected.
"""


def build_prompt(
    raw_requirement_id: str,
    raw_title: str,
    project_name: str,
    raw_body: str,
    comparison: ComparisonContext,
) -> tuple[str, str]:
    """Return the instruction prompt and the context sent on stdin."""
    context = "\n".join(
        [
            "# Project",
            project_name,
            "",
            "# RAW Requirement",
            f"{raw_requirement_id} — {raw_title}",
            "",
            "# RAW Requirement documents",
            raw_body or "(empty)",
            "",
            render_comparison_section(comparison),
            "",
            f"# Allowed categories\n{', '.join(c.value for c in Category)}",
            f"# Allowed finding kinds\n{', '.join(k.value for k in FindingKind)}",
        ]
    )
    return INSTRUCTIONS, context
