"""The bounded prompt for independent Standard Requirement review.

Context is the Requirement, its current Root Document, the persisted claims of
the latest Process Result, the relations it already has, and the Project's
other Standard Requirements as comparison material (entity metadata plus each
one's complete current Root Document). No Milestones, Epics, Stories, Tasks or
Project Phases, and no earlier iteration of anything.

Two exclusions carry the independence of this stage:

- the Process model's raw response is never available here. What the reviewer
  sees is the *validated, persisted* Process Result, presented as claims to
  check rather than as conclusions to agree with;
- previous Review Results are never sent, so a reviewer cannot anchor on its
  own earlier verdict.

The model is asked for structured data only, never for reasoning, never for
Fibery mechanics, and never for a verdict: deriving that is the code's job.
"""

from __future__ import annotations

from sdlc.comparison_context import (
    ComparisonContext,
    render_comparison_section,
    render_target_metadata,
)
from sdlc.fibery_workspace import RequirementRecord, RequirementRelations
from sdlc.process_result import ProcessResult
from sdlc.standard_analysis import FindingKind
from sdlc.standard_review import ReviewSeverity, VerificationOutcome

INSTRUCTIONS = """\
You are independently reviewing one Standard Requirement in an SDLC system.

Another agent normalized this Requirement and recorded findings and proposed
relations. You are not that agent. Your job is to check its work against the
current requirement document and to report anything it missed. You do not
improve, rewrite or repair the requirement: a problem is a finding.

Return ONLY a single JSON object. No prose, no explanation of your reasoning, no
markdown outside the JSON.

Shape:

{
  "finding_verifications": [
    { "process_finding_index": 0,
      "outcome": "CONFIRMED" | "REJECTED" | "UNRESOLVED",
      "severity": "INFO" | "WARNING" | "BLOCKING",
      "reason": "concise justification" }
  ],
  "relation_verifications": [
    { "kind": "DEPENDS_ON" | "AFFECTS",
      "requirement_id": "the proposed Requirement ID",
      "outcome": "CONFIRMED" | "REJECTED" | "UNRESOLVED",
      "reason": "concise justification" }
  ],
  "new_findings": [
    { "kind": "<finding kind>",
      "severity": "INFO" | "WARNING" | "BLOCKING",
      "detail": "what you observed",
      "requirement_id": "only for findings about another Requirement" }
  ],
  "assessment": {
    "clarity": "...", "completeness": "...", "atomicity": "...",
    "testability": "...", "internal_consistency": "...",
    "acceptance_criteria": "..."
  }
}

Rules:

- Verify every listed Process finding exactly once, by its index. Do not skip
  one, do not verify one twice, and do not invent an index.
- Verify every listed proposed relation exactly once, by its kind and
  Requirement ID. Confirming a relation does not create it; a human decides
  later whether it is ever applied.
- Reach your own conclusion. CONFIRMED means you independently agree the
  finding is real. REJECTED means you do not. UNRESOLVED means the available
  context cannot settle it. Rejecting a finding is a normal outcome.
- Give a severity only when you CONFIRM a finding, and always when you do.
  REJECTED and UNRESOLVED assert no defect, so they must carry no severity.
- Report anything the earlier analysis missed as a new finding, with its own
  severity.
- Do not state an overall verdict, score or recommendation. There is no field
  for one: it is derived from the severities you assign.
- Do not propose changes, rewrites, updates, retirement or supersession of any
  Requirement, and do not describe an action to take. You are reporting, not
  instructing.
- Every other Standard Requirement named by a claim is supplied with its full
  Root Document; verify comparison claims against that text, not the title.
  A peer that is not Applied is a candidate under review, not approved
  authority, and nothing here approves it.
- Emit no field that is not listed above. Unknown fields are rejected.
"""


def build_review_prompt(
    requirement: RequirementRecord,
    project_name: str,
    root_content: str,
    process_result: ProcessResult,
    relations: RequirementRelations,
    comparison: ComparisonContext,
) -> tuple[str, str]:
    """Return the instruction prompt and the context sent on stdin."""
    context = "\n".join(
        [
            "# Project",
            project_name,
            "",
            "# Requirement under review",
            f"{requirement.requirement_id} — {requirement.title}",
            *render_target_metadata(requirement),
            "",
            "# Current Requirement document",
            root_content or "(empty)",
            "",
            _findings_section(process_result),
            "",
            _relations_section(process_result),
            "",
            _analysis_section(process_result),
            "",
            _existing_relations_section(relations),
            "",
            render_comparison_section(comparison),
            "",
            f"# Allowed finding kinds\n{', '.join(k.value for k in FindingKind)}",
            f"# Allowed severities\n{', '.join(s.value for s in ReviewSeverity)}",
            f"# Allowed outcomes\n{', '.join(o.value for o in VerificationOutcome)}",
        ]
    )
    return INSTRUCTIONS, context


def _findings_section(result: ProcessResult) -> str:
    """The Process findings, indexed, as claims to check."""
    header = (
        "# Findings claimed by the earlier analysis\n"
        "Verify each by its index. These are claims, not conclusions."
    )
    lines = [
        f"[{index}] {finding.kind.value}"
        + (f" about {finding.requirement_id}" if finding.requirement_id else "")
        + f": {finding.detail}"
        for index, finding in enumerate(result.findings)
    ]
    return "\n".join([header, *lines]) if lines else f"{header}\n(none)"


def _relations_section(result: ProcessResult) -> str:
    header = (
        "# Relations proposed by the earlier analysis\n"
        "Verify each. Confirming one does not create it."
    )
    lines = [
        f"- {relation.kind.value} {relation.requirement_id}: {relation.rationale}"
        for relation in result.proposed_relations
    ]
    return "\n".join([header, *lines]) if lines else f"{header}\n(none)"


def _analysis_section(result: ProcessResult) -> str:
    header = "# Assessment claimed by the earlier analysis"
    lines = [f"- {key}: {value}" for key, value in sorted(result.analysis.items())]
    return "\n".join([header, *lines]) if lines else f"{header}\n(none)"


def _existing_relations_section(relations: RequirementRelations) -> str:
    """What this Requirement is already related to.

    Sent so the reviewer can tell a genuinely new proposal from one that merely
    restates an edge that already exists.
    """
    header = "# Relations this Requirement already has"
    lines = [f"- DEPENDS_ON {value}" for value in relations.depends_on]
    lines += [f"- AFFECTS {value}" for value in relations.affects]
    return "\n".join([header, *lines]) if lines else f"{header}\n(none)"
